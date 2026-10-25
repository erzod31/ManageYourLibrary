"""Exercise the real Tk workspace with isolated state and synthetic books."""
from __future__ import annotations

import argparse
import gc
import json
import re
import statistics
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))


def process_metrics():
    if sys.platform == 'win32':
        import ctypes
        from ctypes import wintypes
        class Counters(ctypes.Structure):
            _fields_ = [('cb', wintypes.DWORD), ('faults', wintypes.DWORD)] + [
                (name, ctypes.c_size_t) for name in ('peak_rss', 'rss', 'peak_paged', 'paged',
                                                   'peak_nonpaged', 'nonpaged', 'pagefile', 'peak_pagefile')]
        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        call = ctypes.WinDLL('psapi').GetProcessMemoryInfo
        call.argtypes = (wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD)
        if call(wintypes.HANDLE(-1), ctypes.byref(counters), counters.cb):
            return {'rss_mib': round(counters.rss/1024**2, 2), 'peak_rss_mib': round(counters.peak_rss/1024**2, 2)}
    return {'rss_mib': None, 'peak_rss_mib': None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--size", type=int, default=4158)
    parser.add_argument("--preview", action="store_true")
    parser.add_argument('--theme', choices=('system', 'light', 'dark', 'contrast'),
                        help='Initial theme in the disposable QA profile only.')
    parser.add_argument('--geometry', help='Initial QA window size, for example 760x560.')
    parser.add_argument('--repetitions', type=int, default=5)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.geometry and not re.fullmatch(r'[1-9][0-9]{2,3}x[1-9][0-9]{2,3}', args.geometry):
        parser.error('--geometry must be WIDTHxHEIGHT')
    with tempfile.TemporaryDirectory(prefix="myl_ui_qa_") as directory:
        base = Path(directory)
        from core import config_store
        # Override before importing the app, so no real catalog/config is used.
        config_store.app_data_dir = lambda: base / "state"
        import tkinter as tk
        from tkinter import messagebox
        from PIL import Image, ImageDraw
        import library_core as core
        from library_app import App
        from tools.benchmark_catalog import synthetic_catalog

        if args.theme is not None:
            core.guardar_configuracion_operacion({'theme': args.theme})
        rows = synthetic_catalog(args.size)
        titles = ("El jardín invisible", "Mapas del silencio", "La ciudad de otro sol", "El eco de la marea")
        colors = ("#557859", "#577f96", "#bc9357", "#597f7a")
        covers = []
        for index, color in enumerate(colors):
            path = base / f"cover_{index}.png"
            image = Image.new("RGB", (144, 206), color)
            draw = ImageDraw.Draw(image)
            draw.rectangle((10, 10, 133, 195), outline="#eadfc5", width=2)
            draw.text((22, 65), f"LIBRO {index + 1}", fill="#fff8e8")
            image.save(path)
            covers.append(path)
        for index, row in enumerate(rows):
            row.update(titulo=f"{titles[index % 4]} {index}", autor=f"Autora {index % 40}",
                       ruta=str(base / "books" / f"book_{index}.epub"), isbn="", cover_url="")
        core.guardar_indice({"archivos": rows, "library": "", "creado": None})
        cold_start = time.perf_counter()
        root = tk.Tk()
        app = App(root)
        if args.geometry:
            root.geometry(args.geometry)
        construct_ms = (time.perf_counter() - cold_start) * 1000
        root.title("ManageYourLibrary — QA aislada")
        workspace = app.workspace
        workspace.cover_service.thumbnail_path = lambda source, remote_url="": covers[int(Path(source).stem.split("_")[-1]) % 4]
        workspace.refresh_library()
        errors = []
        messagebox.showerror = lambda title, message, **kwargs: errors.append(f'{title}: {message}')
        root.report_callback_exception = lambda kind, value, tb: errors.append(f"{kind.__name__}: {value}")
        samples = {}
        heartbeats = []
        last = time.perf_counter()
        def heartbeat():
            nonlocal last
            now = time.perf_counter()
            heartbeats.append((now - last) * 1000)
            last = now
            root.after(16, heartbeat)
        root.after(16, heartbeat)
        if args.preview:
            root.mainloop()
            # Keep manual QA callback failures observable without serializing
            # the disposable catalog or screen contents in the report.
            if args.output:
                args.output.write_text(json.dumps({
                    'mode': 'manual_preview', 'size': args.size,
                    'initial_theme': args.theme, 'errors': errors,
                    'initial_geometry': args.geometry,
                }, indent=2) + '\n', encoding='utf-8')
            return int(bool(errors))

        tasks = []
        for _ in range(args.repetitions):
            tasks.extend([
                ("cover_refresh", lambda: workspace.refresh_library()),
                ("next_page", lambda: workspace.change_page(1)),
                ("previous_page", lambda: workspace.change_page(-1)),
                ("relayout", lambda: workspace._relayout_cover_cards(3 if workspace._cover_columns != 3 else 4)),
                ("sash", lambda: workspace.library_panes.sash_place(0, 470 if workspace.library_panes.sash_coord(0)[0] != 470 else 550, 0)),
                ("table_render", lambda: workspace.set_view("table")),
                ("covers_view", lambda: workspace.set_view("covers")),
                ("theme", lambda: app.alternar_tema()),
                ("selection", lambda: workspace.select_item(workspace.filtered_items[0])),
                ('favorite_dispatch', workspace.toggle_selected_favorite),
            ])
        warmed_up = False
        startup_max = 0
        finish_wait_started = None
        favorite_started = None
        gc_started = {}
        gc_pauses = []
        slow_callbacks = []
        def measure_gc(phase, info):
            generation = info['generation']
            if phase == 'start':
                gc_started[generation] = time.perf_counter()
            elif generation in gc_started:
                duration = (time.perf_counter() - gc_started.pop(generation)) * 1000
                if duration > 5:
                    gc_pauses.append({'generation': generation, 'ms': round(duration, 2)})
        gc.callbacks.append(measure_gc)
        cpu_start = time.process_time()
        interaction_start = time.perf_counter()
        def run_next():
            nonlocal warmed_up, startup_max, last, finish_wait_started, favorite_started
            if not warmed_up:
                startup_max = max(heartbeats, default=0)
                heartbeats.clear()
                last = time.perf_counter()
                warmed_up = True
            if favorite_started is not None:
                elapsed = time.perf_counter() - favorite_started
                if app.trabajando and elapsed < 10:
                    root.after(5, run_next)
                    return
                if app.trabajando:
                    errors.append('Favorite edit did not complete within 10s')
                samples.setdefault('favorite_end_to_end', []).append(elapsed * 1000)
                favorite_started = None
            if not tasks:
                if getattr(workspace, "_table_after", None) is not None:
                    if finish_wait_started is None:
                        finish_wait_started = time.perf_counter()
                    if time.perf_counter() - finish_wait_started < 10:
                        root.after(50, run_next)
                        return
                    errors.append("Table did not finish within 10s after interactions")
                report = {"size": args.size, "callbacks": {}, "errors": errors,
                          "heartbeat_max_ms": round(max(heartbeats, default=0), 2),
                          "startup_heartbeat_max_ms": round(startup_max, 2),
                          "registered_frames": len(workspace.frames)}
                report.update({'repetitions': args.repetitions, 'construct_ms': round(construct_ms, 2),
                               'memory': process_metrics(), 'process_cpu_seconds': round(time.process_time()-cpu_start, 2),
                               'interaction_seconds': round(time.perf_counter()-interaction_start, 2)})
                report['gc_pauses_over_5ms'] = gc_pauses
                report['callbacks_over_50ms'] = slow_callbacks
                report['catalog_gc_owned'] = app.catalog_gc.owned
                report['gc_enabled'] = gc.isenabled()
                report['frozen_object_count'] = gc.get_freeze_count()
                report["cover_pool_size"] = len(getattr(workspace, "_cover_card_pool", []))
                report["table_rows_loaded"] = len(workspace.tree.get_children())
                for name, measurements in samples.items():
                    report["callbacks"][name] = {"median_ms": round(statistics.median(measurements), 2),
                                                   'p95_ms': round(sorted(measurements)[int((len(measurements)-1)*.95)], 2),
                                                   "max_ms": round(max(measurements), 2)}
                print(json.dumps(report, ensure_ascii=True), flush=True)
                if args.output:
                    args.output.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
                workspace.shutdown()
                root.destroy()
                return
            name, callback = tasks.pop(0)
            started = time.perf_counter()
            try:
                callback()
            except Exception as exc:
                errors.append(f"{name}: {exc}")
            elapsed_ms = (time.perf_counter() - started) * 1000
            samples.setdefault(name, []).append(elapsed_ms)
            if elapsed_ms > 50:
                slow_callbacks.append({'name': name, 'ms': round(elapsed_ms, 2)})
            if name == 'favorite_dispatch':
                favorite_started = started
                root.after(5, run_next)
            else:
                root.after(120, run_next)
        root.after(750, run_next)
        root.mainloop()
        gc.callbacks.remove(measure_gc)
        with app.worker_threads_lock:
            workers = list(app.worker_threads)
        for worker in workers:
            worker.join(timeout=10)
        return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())

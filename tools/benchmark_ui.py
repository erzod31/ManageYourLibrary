"""Exercise the real Tk workspace with isolated state and synthetic books."""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--size", type=int, default=4158)
    parser.add_argument("--preview", action="store_true")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="myl_ui_qa_") as directory:
        base = Path(directory)
        from core import config_store
        # Override before importing the app, so no real catalog/config is used.
        config_store.app_data_dir = lambda: base / "state"
        import tkinter as tk
        from PIL import Image, ImageDraw
        import library_core as core
        from library_app import App
        from tools.benchmark_catalog import synthetic_catalog

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
        root = tk.Tk()
        app = App(root)
        root.title("ManageYourLibrary — QA aislada")
        workspace = app.workspace
        workspace.cover_service.thumbnail_path = lambda source, remote_url="": covers[int(Path(source).stem.split("_")[-1]) % 4]
        workspace.refresh_library()
        errors = []
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
            return 0

        tasks = []
        for _ in range(5):
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
            ])
        warmed_up = False
        startup_max = 0
        finish_wait_started = None
        def run_next():
            nonlocal warmed_up, startup_max, last, finish_wait_started
            if not warmed_up:
                startup_max = max(heartbeats, default=0)
                heartbeats.clear()
                last = time.perf_counter()
                warmed_up = True
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
                report["cover_pool_size"] = len(getattr(workspace, "_cover_card_pool", []))
                report["table_rows_loaded"] = len(workspace.tree.get_children())
                for name, measurements in samples.items():
                    report["callbacks"][name] = {"median_ms": round(statistics.median(measurements), 2),
                                                   "max_ms": round(max(measurements), 2)}
                print(json.dumps(report, ensure_ascii=True), flush=True)
                workspace.shutdown()
                root.destroy()
                return
            name, callback = tasks.pop(0)
            started = time.perf_counter()
            try:
                callback()
            except Exception as exc:
                errors.append(f"{name}: {exc}")
            samples.setdefault(name, []).append((time.perf_counter() - started) * 1000)
            root.after(120, run_next)
        root.after(750, run_next)
        root.mainloop()
        with app.worker_threads_lock:
            workers = list(app.worker_threads)
        for worker in workers:
            worker.join(timeout=10)
        return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())

"""Check Tk widget geometry in a disposable profile (not OS DPI/accessibility certification)."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def visible_rectangle(widget):
    if not widget.winfo_ismapped():
        return False
    left, top = widget.winfo_rootx(), widget.winfo_rooty()
    right, bottom = left + widget.winfo_width(), top + widget.winfo_height()
    ancestor = widget.master
    while ancestor is not None:
        x, y = ancestor.winfo_rootx(), ancestor.winfo_rooty()
        if left < x or top < y or right > x + ancestor.winfo_width() or bottom > y + ancestor.winfo_height():
            return False
        ancestor = ancestor.master
    return widget.winfo_width() > 2 and widget.winfo_height() > 2


def wait_for_ui(root, condition, timeout=3):
    """Wait for the actual debounced result and layout, within a fixed deadline."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        root.after(20, root.quit)
        root.mainloop()
    return bool(condition())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--captures', type=Path, help='Synthetic previews in the private Linux CI Xvfb session only')
    parser.add_argument('--scale', type=float, choices=(1.0, 1.25, 1.5, 2.0), help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.captures:
        if not (sys.platform == 'linux' and os.environ.get('GITHUB_ACTIONS') == 'true'
                and os.environ.get('MYL_ISOLATED_VISUAL_CI') == '1' and os.environ.get('DISPLAY')):
            parser.error('--captures requires the explicitly isolated Linux CI display')
        args.captures.mkdir(parents=True, exist_ok=False)
    if args.scale is None:
        return run_matrix(args)
    captured = []

    def capture(root, name):
        from PIL import ImageGrab
        left, top = root.winfo_rootx(), root.winfo_rooty()
        bounds = (left, top, left + root.winfo_width(), top + root.winfo_height())
        if left < 0 or top < 0 or bounds[2] > root.winfo_screenwidth() or bounds[3] > root.winfo_screenheight():
            raise RuntimeError('Synthetic preview does not fit the private CI display')
        ImageGrab.grab(bbox=bounds, xdisplay=os.environ['DISPLAY']).save(args.captures / (name + '.png'))
        captured.append(name + '.png')
    results, errors, interactions = [], [], {}
    with tempfile.TemporaryDirectory(prefix='myl_geometry_') as directory:
        os.environ['MANAGE_YOUR_LIBRARY_PROFILE'] = str(Path(directory) / 'profile')
        import tkinter as tk
        from tkinter import ttk
        from unittest.mock import patch
        import library_core as core
        from library_app import App
        rows = [{'ruta': str(Path(directory) / f'book_{i}.epub'), 'titulo': f'Libro sintético {i}',
                 'autor': 'Autora de ejemplo', 'extension': '.epub', 'tags': ['Prueba'], 'serie': 'Serie'}
                for i in range(12)]
        rows[0]['read_status'] = 'reading'
        from PIL import Image
        cover = Path(directory) / 'synthetic-cover.png'
        Image.new('RGB', (144, 206), '#587964').save(cover)
        # Native platform providers initialize per process, as in the app.
        for scale in (args.scale,):
            root = tk.Tk()
            root.tk.call('tk', 'scaling', (96 / 72) * scale)
            app = App(root, initial_index={'archivos': rows})
            workspace = app.workspace
            root.report_callback_exception = lambda kind, value, tb: errors.append(f'{kind.__name__}: {value}')
            workspace.select_item(workspace.filtered_items[0])
            if scale == 1:
                root.update()
                # Exercise menu lifetime/commands without waiting in the native
                # Windows popup loop; real popup colors are checked visually.
                with patch.object(tk.Menu, 'tk_popup', return_value=None):
                    workspace._show_filters_menu()
                root.update()
                interactions['filter_menu_survives_posting'] = bool(workspace._filters_menu.winfo_exists())
                workspace._filters_menu.invoke(2)
                workspace._filters_menu.unpost()
                interactions['reading_filter'] = len(workspace.filtered_items) == 1
                with patch('ui.workspace.simpledialog.askstring', return_value='Synthetic reading view'):
                    workspace._save_filter()
                saved = core.cargar_json(core.APP_DATA / 'saved_views.json', {})
                workspace._set_read_filter('all')
                workspace._load_filter(saved['Synthetic reading view'])
                interactions['saved_filter_round_trip'] = workspace.read_filter == 'reading' and len(workspace.filtered_items) == 1
                workspace._set_read_filter('all')
                workspace.show_page('authors')
                root.update()
                groups = workspace.entity_tree.get_children()
                interactions['authors_entity_directory'] = len(groups) == 1 and workspace.entity_view.winfo_ismapped()
                workspace.entity_tree.selection_set(groups[0])
                workspace._open_entity()
                root.update()
                interactions['author_exact_membership'] = len(workspace.filtered_items) == 12 and bool(workspace.entity_key)
                workspace.show_page('library')
                app.establecer_preferencia_tema('contrast')
                root.update()
                interactions['high_contrast'] = app.tema_actual['bg'] == '#000000' and app.tema_actual['text'] == '#ffffff'
                app.establecer_preferencia_tema('light')
                plan = {'metadata': {'library': str(Path(directory) / 'library'), 'prepared_metadata': {}},
                        'items': [{'source': str(Path(directory) / f'preview-{i}.epub'), 'state': 'pending'} for i in range(1005)]}
                preview = app._mostrar_previsualizacion(plan)
                root.update()
                def descendants(widget):
                    for child in widget.winfo_children():
                        yield child
                        yield from descendants(child)
                children = list(descendants(preview))
                table = next(child for child in children if isinstance(child, ttk.Treeview))
                following = next(child for child in children if getattr(child, 'text', None) == 'Siguiente')
                for _ in range(10):
                    following.command()
                interactions['preview_all_pages_accessible'] = len(table.get_children()) == 5 and table.get_children()[-1] == '1004'
                interactions['preview_originals_untouched'] = not (Path(directory) / 'library').exists()
                compare = next(child for child in children if getattr(child, 'text', None) == 'Comparar campos…')
                compare.command()
                root.update()
                comparison = next(child for child in descendants(preview) if isinstance(child, ttk.Treeview) and child is not table)
                interactions['field_comparison_eight_fields'] = len(comparison.get_children()) == 8
                preview.destroy()
                workspace.search_placeholder_active = False
                workspace.search_var.set('No-matching-synthetic-book-xyz')
                interactions['filtered_empty_state'] = wait_for_ui(root, lambda: (not workspace.filtered_items
                    and workspace._empty_library_action.winfo_ismapped()
                    and workspace.selected_item is None and workspace.open_button.state == 'disabled'))
                interactions['clear_search_visible'] = workspace.search_clear_button.winfo_ismapped()
                workspace._empty_library_action.invoke()
                root.update()
                interactions['clear_filters_restores_catalog'] = len(workspace.filtered_items) == len(rows)
                workspace._set_details_visible(True)
                workspace.toggle_details()
                for geometry in ('760x560', '1366x768'):
                    root.geometry(geometry)
                    root.after(160, root.quit)
                    root.mainloop()
                interactions['hidden_details_survive_resize'] = not workspace.details_visible
                workspace.toggle_details()
                root.update()
                workspace.cover_service.thumbnail_path = lambda *args, **kwargs: None
                bad_cover = Path(directory) / 'invalid-cover.png'
                bad_cover.write_bytes(b'not an image')
                first = workspace._cover_card_pool[0][1]
                first._cover_loaded = False
                workspace._apply_cover(first, first._item_path, bad_cover, workspace.cover_generation)
                interactions['invalid_cover_keeps_placeholder_retryable'] = not first._cover_loaded
                for item in workspace.filtered_items:
                    workspace.select_item(item)
                    workspace._apply_cover(workspace.details_cover, item['ruta'], cover, workspace.cover_generation)
                interactions['one_selected_cover_retained'] = (
                    sum(key[0] == 'details' for key in workspace.cover_images) == 1
                    and not any(key[0] == str(workspace.details_cover) for key in workspace.cover_images))
                interactions['full_path_selectable'] = workspace.detail_path_var.get() == str(Path(workspace.selected_item['ruta']).resolve())
                for mode in ('light', 'dark', 'contrast'):
                    app.establecer_preferencia_tema(mode)
                    root.update()
                    interactions['disabled_combo_' + mode] = app.style.lookup(
                        'Library.TCombobox', 'foreground', ('readonly', 'disabled')) == app.tema_actual['disabled_text']
                app.establecer_preferencia_tema('light')
            for width, height in ((760, 560), (1024, 768), (1366, 768), (1920, 1080)):
                root.geometry(f'{width}x{height}+0+0')
                root.update()
                workspace._apply_responsive_layout()
                if width >= 1024:
                    workspace._set_details_visible(True)
                root.update()
                root.after(250, root.quit)
                root.mainloop()
                widgets = {key: getattr(workspace, key) for key in (
                    'search_entry', 'page_next', 'filters_button', 'details_button')}
                widgets.update({'nav_' + key: button for key, button in workspace.nav_buttons.items()})
                widgets['theme_button'] = app.btn_tema
                widgets.update({'voice_status': workspace.speech_controls.status,
                                'voice_activate': workspace.speech_controls.activate_button,
                                'voice_deactivate': workspace.speech_controls.deactivate_button,
                                'operation_status': app.label_estado,
                                'operation_cancel': app.btn_cancelar_operacion})
                if workspace.details_visible:
                    widgets.update({key: getattr(workspace, key) for key in (
                    'detail_path_entry', 'copy_path_button', 'show_folder_button',
                    'open_button', 'metadata_button', 'lookup_metadata_button', 'detail_author',
                    'read_status_combo', 'detail_favorite', 'details_heading')})
                    relations = ('compact_series', 'compact_tags') if workspace.detail_compact_relations.winfo_manager() else ('detail_series', 'detail_tags')
                    widgets.update({key: getattr(workspace, key) for key in relations})
                    # Collapsed metadata groups remain accessible through Details….
                    widgets.update({key: widget for key, widget in workspace.detail_group_headings.items()
                                    if widget.winfo_manager()})
                checks = {name: visible_rectangle(widget) for name, widget in widgets.items()}
                from tkinter import font as tkfont
                for name in ('voice_activate', 'voice_deactivate', 'operation_cancel'):
                    widget = widgets[name]
                    font = tkfont.Font(root=root, font=widget.font)
                    checks[name + '_text'] = (font.measure(widget.text) + 20 <= widget.winfo_width()
                                             and font.metrics('linespace') + 10 <= widget.winfo_height())
                voice_status = workspace.speech_controls.status
                checks['voice_status_height'] = voice_status.winfo_height() >= voice_status.winfo_reqheight()
                if workspace.brand_copy.winfo_ismapped():
                    brand = workspace.brand_label
                    font = tkfont.Font(root=root, font=brand.cget('font'))
                    checks['brand_text'] = font.measure(brand.cget('text')) + 4 <= brand.winfo_width()
                if workspace.cover_view.winfo_ismapped() and workspace._cover_card_pool:
                    first_cover = workspace._cover_card_pool[0][1]
                    left = first_cover.winfo_rootx() - workspace.cover_canvas.winfo_rootx()
                    checks['cover_pixel_size'] = (first_cover.winfo_width() <= 156
                        and first_cover.winfo_height() <= 220 and left >= 0
                        and left + first_cover.winfo_width() <= workspace.cover_canvas.winfo_width())
                results.append({'requested': [width, height], 'actual': [root.winfo_width(), root.winfo_height()],
                                'tk_scale_percent': int(scale * 100), 'checks': checks,
                                'failed_geometry': {name: {'actual': [widget.winfo_x(), widget.winfo_y(),
                                    widget.winfo_width(), widget.winfo_height()],
                                    'requested': [widget.winfo_reqwidth(), widget.winfo_reqheight()],
                                    'parent': [widget.master.winfo_width(), widget.master.winfo_height()]}
                                    for name, widget in widgets.items() if not checks[name]}})
                if args.captures and ((scale == 1 and width == 1366) or (scale == 2 and width == 760)):
                    workspace.cover_service.thumbnail_path = lambda *args, **kwargs: cover
                    workspace.refresh_library()
                    workspace.select_item(workspace.filtered_items[0])
                    root.after(250, root.quit)
                    root.mainloop()
                    capture(root, 'library-light' if scale == 1 else 'library-compact-200')
                    if scale == 1:
                        app.establecer_preferencia_tema('dark')
                        root.after(180, root.quit)
                        root.mainloop()
                        capture(root, 'library-dark')
                        app.establecer_preferencia_tema('light')
            root.geometry('760x560+0+0')
            workspace.show_page('settings')
            root.after(180, root.quit)
            root.mainloop()
            for name, widget in (('settings_theme', workspace.theme_combo), ('settings_ocr', workspace.ocr_spinbox)):
                workspace._reveal_pane_focus_target(widget)
                root.after(100, root.quit)
                root.mainloop()
                results.append({'page': 'settings', 'tk_scale_percent': int(scale * 100),
                                'checks': {name: visible_rectangle(widget)},
                                'failed_geometry': {} if visible_rectangle(widget) else {
                                    name: {'actual': [widget.winfo_x(), widget.winfo_y(), widget.winfo_width(), widget.winfo_height()],
                                           'parent': [widget.master.winfo_width(), widget.master.winfo_height()],
                                           'canvas_yview': workspace.page_scroll_canvases['settings'].yview()}}})
            for page in ('import', 'reviews', 'activity', 'settings'):
                workspace.show_page(page)
                root.update()
                root.after(100, root.quit)
                root.mainloop()
                results.append({'page': page, 'tk_scale_percent': int(scale * 100),
                                'checks': {'heading': visible_rectangle(app.label_titulo),
                                           'language': visible_rectangle(app.btn_idioma),
                                           'theme': visible_rectangle(app.btn_tema)}})
                if args.captures and scale == 1:
                    capture(root, page + '-compact')
                controls = {
                    'import': (app.entry_biblioteca, app.btn_elegir_biblioteca, app.btn_agregar_import, app.btn_biblioteca),
                    'reviews': (workspace.scan_button, workspace.resume_reviews_button, app.btn_dobles_carpeta, app.btn_metadatos),
                    'activity': (app.btn_undo,),
                }.get(page, ())
                for position, widget in enumerate(controls):
                    workspace._reveal_pane_focus_target(widget)
                    root.after(80, root.quit)
                    root.mainloop()
                    results.append({'page': page, 'tk_scale_percent': int(scale * 100),
                                    'checks': {'action_' + str(position): visible_rectangle(widget)}})
            if scale in (1.0, 2.0):
                for language in ('en', 'es', 'fr', 'zh'):
                    app.seleccionar_idioma(language)
                    workspace.show_page('library')
                    root.geometry('1366x768+0+0' if scale == 1.0 else '760x560+0+0')
                    root.after(200, root.quit)
                    root.mainloop()
                    checks = {}
                    for name, button in workspace.nav_buttons.items():
                        font = tkfont.Font(root=root, font=button.font)
                        checks[name] = (font.measure(button.text) <= button.winfo_width() - 58
                                        and font.metrics('linespace') <= button.winfo_height() - 6)
                    for name, button in (('voice_activate', workspace.speech_controls.activate_button),
                                         ('voice_deactivate', workspace.speech_controls.deactivate_button)):
                        font = tkfont.Font(root=root, font=button.font)
                        checks[name] = (visible_rectangle(button)
                                        and font.measure(button.text) + 20 <= button.winfo_width()
                                        and font.metrics('linespace') + 10 <= button.winfo_height())
                    brand = workspace.brand_label
                    font = tkfont.Font(root=root, font=brand.cget('font'))
                    checks['brand'] = font.measure(brand.cget('text')) + 4 <= brand.winfo_width()
                    results.append({'page': 'localized_navigation', 'language': language,
                                    'tk_scale_percent': int(scale * 100), 'checks': checks})
                    if args.captures and scale == 1 and language == 'es':
                        capture(root, 'library-spanish-light')
            workspace.shutdown()
            for identifier in root.tk.call('after', 'info'):
                # Child-owned Map annotations own their Python Tcl commands.
                # Cancel schedules only; widget.destroy deletes each command
                # once through the widget which registered it.
                root.tk.call('after', 'cancel', identifier)
            root.destroy()
        report = {'method': 'Tk scaling + geometry, not Windows display settings or a screen reader',
                  'results': results, 'interactions': interactions, 'errors': errors,
                  'synthetic_linux_ci_captures': captured}
        encoded = json.dumps(report, indent=2)
        print(encoded)
        if args.output:
            args.output.write_text(encoded + '\n', encoding='utf-8')
        return int(bool(errors) or not all(interactions.values()) or any(not all(item['checks'].values()) for item in results))


def run_matrix(args):
    reports, failed = [], []
    with tempfile.TemporaryDirectory(prefix='myl_layout_reports_') as directory:
        for scale in (1.0, 1.25, 1.5, 2.0):
            output = Path(directory) / f'{scale}.json'
            command = [sys.executable, '-B', str(Path(__file__).resolve()),
                       '--scale', str(scale), '--output', str(output)]
            if args.captures and scale in (1.0, 2.0):
                command += ['--captures', str(args.captures / f'scale-{int(scale * 100)}')]
            result = subprocess.run(command, capture_output=True, text=True, timeout=90)
            if not output.is_file():
                raise RuntimeError(f'Layout child {scale} produced no report: {result.stderr[-3000:]}')
            report = json.loads(output.read_text(encoding='utf-8'))
            if result.returncode:
                failed.append(int(scale * 100))
            for name in report.get('synthetic_linux_ci_captures', []):
                report.setdefault('_capture_paths', []).append(f'scale-{int(scale * 100)}/{name}')
            reports.append(report)
    combined = {'method': 'Fresh process per Tk text scale; not OS DPI or reader certification',
                'results': [row for report in reports for row in report['results']],
                'interactions': {key: value for report in reports for key, value in report['interactions'].items()},
                'errors': [error for report in reports for error in report['errors']],
                'failed_scales': failed,
                'synthetic_linux_ci_captures': [name for report in reports for name in report.get('_capture_paths', [])]}
    encoded = json.dumps(combined, indent=2)
    print(encoded)
    if args.output:
        args.output.write_text(encoded + '\n', encoding='utf-8')
    return int(bool(failed) or bool(combined['errors']) or not all(combined['interactions'].values())
               or any(not all(row['checks'].values()) for row in combined['results']))


if __name__ == '__main__':
    raise SystemExit(main())

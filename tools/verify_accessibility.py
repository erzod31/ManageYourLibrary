"""Exercise Tk's native accessibility commands in a disposable app profile.

This verifies the live platform provider's properties and registered actions.
Speech output from NVDA/VoiceOver/Orca is a separate manual validation.
"""
import argparse
import json
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def run():
    from core import config_store
    with tempfile.TemporaryDirectory(prefix='myl_accessibility_') as directory, \
            patch.object(config_store, 'app_data_dir', return_value=Path(directory)):
        import tkinter as tk
        import library_core as core
        from library_app import App
        from tools.benchmark_catalog import synthetic_catalog
        from ui.accessibility import available, annotate, name_control
        from ui.workspace import _text
        from rounded_widgets import RoundedButton
        checks, errors = {}, []
        root = tk.Tk()
        root.report_callback_exception = lambda kind, value, tb: errors.append(f'{kind.__name__}: {value}')
        app = None
        try:
            native = available(root)
            if not native:
                return {'passed': False, 'backend': 'unsupported_runtime', 'tk': root.tk.call('package', 'present', 'Tk')}
            app = App(root, initial_index={'archivos': synthetic_catalog(40)})
            workspace = app.workspace
            workspace.cover_service.thumbnail_path = lambda *args, **kwargs: None
            workspace.refresh_library()
            deadline = time.monotonic() + .35
            while time.monotonic() < deadline:
                root.update()
            def prop(widget, name):
                return str(root.tk.call('::tk::accessible::get_acc_' + name, str(widget)))
            for key, button in workspace.nav_buttons.items():
                checks['navigation_' + key] = prop(button, 'role') == 'Button' and bool(prop(button, 'name'))
            checks['search_name'] = prop(workspace.search_entry, 'name') == _text('search')
            checks['icon_button_names'] = all(bool(prop(button, 'name')) for button in (
                workspace.table_button, workspace.cover_button, workspace.details_button))
            root.tk.eval(prop(workspace.nav_buttons['authors'], 'action'))
            root.update()
            checks['registered_navigation_action'] = workspace.library_scope == 'authors'
            workspace.show_page('library')
            workspace.set_view('table')
            root.update()
            rows = workspace.tree.get_children()
            workspace.tree.selection_set(rows[0])
            workspace.tree.event_generate('<<TreeviewSelect>>')
            root.update()
            annotate(workspace.tree)
            checks['selected_row_value'] = bool(prop(workspace.tree, 'value')) and workspace.selected_item is not None
            name_control(workspace.detail_path_entry, _text('path'))
            checks['full_path_value'] = prop(workspace.detail_path_entry, 'value') == workspace.detail_path_var.get()
            invoked = []
            disabled = RoundedButton(root, text='Disabled fixture', command=lambda: invoked.append(True))
            disabled.pack()
            disabled.configure(state='disabled')
            disabled._sync_accessibility()
            root.tk.eval(prop(disabled, 'action'))
            checks['disabled_action_guard'] = not invoked and prop(disabled, 'state') == 'disabled'
            disabled.destroy()
            workspace.edit_selected_metadata()
            root.update()
            dialogs = [child for child in root.winfo_children() if isinstance(child, tk.Toplevel)]
            dialog = dialogs[-1]
            def entries(widget):
                found = []
                for child in widget.winfo_children():
                    if isinstance(child, tk.Entry):
                        found.append(child)
                    found.extend(entries(child))
                return found
            fields = entries(dialog)
            checks['metadata_fields_named'] = len(fields) == 9 and all(bool(prop(field, 'name')) for field in fields)
            checks['metadata_initial_focus'] = dialog.focus_get() is fields[0]
            dialog.destroy()
            checks['native_provider_errors'] = not root._myl_a11y_errors
            checks['no_callback_errors'] = not errors
            return {'passed': all(checks.values()), 'backend': 'tk_native',
                    'tk': root.tk.call('package', 'present', 'Tk'), 'checks': checks,
                    'errors': errors + root._myl_a11y_errors,
                    'screen_reader_speech': 'not_run', 'profile': 'synthetic_disposable',
                    'frozen': bool(getattr(sys, 'frozen', False))}
        finally:
            if app:
                app.workspace.shutdown()
                app.catalog_gc.close()
            for identifier in root.tk.call('after', 'info'):
                root.after_cancel(identifier)
            root.destroy()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = run()
    encoded = json.dumps(result, indent=2)
    print(encoded)
    if args.output:
        args.output.write_text(encoded + '\n', encoding='utf-8')
    raise SystemExit(0 if result['passed'] else 1)

"""Exercise Tk's native accessibility commands in a disposable app profile.

This verifies native API properties and registered actions inside the process.
External assistive-client interoperability and speech output are separate checks.
"""
import argparse
import hashlib
import json
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

BASE_CHECKS = {'navigation_' + key for key in ('library', 'authors', 'series', 'tags', 'favorites', 'import', 'reviews', 'settings')} | {
    'search_name', 'icon_button_names', 'registered_navigation_action', 'selected_row_value',
    'full_path_value', 'disabled_action_guard', 'metadata_fields_named', 'metadata_initial_focus',
    'native_provider_errors', 'no_callback_errors',
    'compact_toolbar_actions_visible', 'compact_status_cancel_visible',
    'voice_controls_visible_all_pages',
}
WINDOWS_CHECKS = BASE_CHECKS | {'platform_provider_label_slot'}


def execution_provenance():
    """Bind source checks to their tree, frozen checks to executable bytes.

    A frozen app has no trustworthy Git checkout. Its executable hash is
    matched to the separately validated build manifest by the packager.
    """
    root = Path(__file__).resolve().parents[1]
    frozen = bool(getattr(sys, 'frozen', False))
    platform = {'darwin': 'macos', 'win32': 'windows'}.get(sys.platform, sys.platform)
    result = {'frozen': frozen, 'platform': platform}
    try:
        result['version'] = (root / 'VERSION').read_text(encoding='utf-8').strip()
    except OSError:
        result['version'] = 'unknown'
    if frozen:
        with Path(sys.executable).open('rb') as handle:
            result['executable_sha256'] = hashlib.file_digest(handle, 'sha256').hexdigest()
    else:
        from tools.write_build_manifest import git_value, source_tree_fingerprint
        result.update(git_commit=git_value('rev-parse', 'HEAD'),
                      git_status=git_value('status', '--short'),
                      source_tree=source_tree_fingerprint())
    return result


def run():
    from core import config_store
    with tempfile.TemporaryDirectory(prefix='myl_accessibility_') as directory, \
            patch.object(config_store, 'app_data_dir', return_value=Path(directory)):
        import tkinter as tk

        from library_app import App
        from rounded_widgets import RoundedButton
        from tools.benchmark_catalog import synthetic_catalog
        from ui.accessibility import annotate, available, name_control
        from ui.workspace import _text
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
            def inside(control, parent):
                if not control.winfo_ismapped():
                    return False
                x = control.winfo_rootx() - parent.winfo_rootx()
                y = control.winfo_rooty() - parent.winfo_rooty()
                return (x >= 0 and y >= 0 and x + control.winfo_width() <= parent.winfo_width()
                        and y + control.winfo_height() <= parent.winfo_height())
            original_geometry = root.geometry()
            root.geometry('760x560')
            deadline = time.monotonic() + .15
            while time.monotonic() < deadline:
                root.update()
            checks['compact_toolbar_actions_visible'] = all(inside(widget, workspace.filter_bar) for widget in (
                workspace.format_combo, workspace.sort_combo, workspace.cover_button,
                workspace.table_button, workspace.details_button, app.btn_agregar))
            checks['compact_status_cancel_visible'] = inside(app.btn_cancelar_operacion, app.btn_cancelar_operacion.master)
            voice = workspace.speech_controls
            visible = True
            for page in ('library', 'authors', 'series', 'tags', 'favorites', 'import', 'reviews', 'activity', 'settings'):
                workspace.show_page(page)
                root.update()
                visible = visible and inside(voice.activate_button, voice.frame) and inside(voice.deactivate_button, voice.frame)
            checks['voice_controls_visible_all_pages'] = visible and voice.session.state == 'off' and voice.session._thread is None
            workspace.show_page('library')
            root.geometry(original_geometry)
            deadline = time.monotonic() + .15
            while time.monotonic() < deadline:
                root.update()
            def prop(widget, name):
                return str(root.tk.call('::tk::accessible::get_acc_' + name, str(widget)))
            for key, button in workspace.nav_buttons.items():
                checks['navigation_' + key] = prop(button, 'role') == 'Button' and bool(prop(button, 'name'))
            checks['search_name'] = prop(workspace.search_entry, 'name') == _text('search')
            if root.tk.call('tk', 'windowingsystem') in {'win32', 'aqua'}:
                checks['platform_provider_label_slot'] = prop(workspace.search_entry, 'description') == _text('search')
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
            expected = WINDOWS_CHECKS if root.tk.call('tk', 'windowingsystem') in {'win32', 'aqua'} else BASE_CHECKS
            return {'passed': set(checks) == expected and all(checks.values()), 'backend': 'tk_native',
                    'tk': root.tk.call('package', 'present', 'Tk'), 'checks': checks,
                    'windowing_system': root.tk.call('tk', 'windowingsystem'),
                    'errors': errors + root._myl_a11y_errors,
                    'external_assistive_client': 'not_run',
                    'screen_reader_speech': 'not_run', 'profile': 'synthetic_disposable',
                    **execution_provenance()}
        finally:
            if app:
                app.workspace.shutdown()
                app.catalog_gc.close()
            for identifier in root.tk.call('after', 'info'):
                # Callbacks can belong to child widgets. Misc.after_cancel on
                # root would delete their commands but leave child ownership
                # records behind, causing a second delete during destruction.
                root.tk.call('after', 'cancel', identifier)
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

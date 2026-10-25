"""Exercise the patched MSAA COM contract, including background calls, locally.

Only this process's synthetic Tk fixture is queried. This is neither an external
assistive client nor a screen-reader/voice certification. No input is injected.
"""
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

REQUIRED_CHECKS = {
    'patch_identity', 'worker_com_calls', 'deep_descendant_discoverable', 'count_matches_enumeration',
    'unique_positive_child_ids', 'simple_child_contract', 'disabled_state_visible_to_com',
    'hidden_descendants_not_enumerated', 'stable_id_after_layout_change', 'registration_idempotent',
    'destroyed_id_not_reassigned', 'dialog_owns_separate_provider', 'dialog_not_in_parent_enumeration',
    'focus_event_does_not_invalidate_ids', 'no_callback_errors', 'no_native_property_errors',
}


def run_fixture():
    if sys.platform != 'win32':
        return {'passed': False, 'reason': 'windows_only'}
    from core import config_store
    with tempfile.TemporaryDirectory(prefix='myl_native_a11y_') as directory, \
            patch.object(config_store, 'app_data_dir', return_value=Path(directory)):
        import tkinter as tk

        from library_app import App
        from tools.benchmark_catalog import synthetic_catalog
        from ui.accessibility import name_control, notify
        from ui.workspace import _text
        errors, checks = [], {}
        root = tk.Tk()
        root.title('MYL synthetic native provider contract')
        root.report_callback_exception = lambda kind, value, _tb: errors.append(f'{kind.__name__}: {value}')
        app = None
        try:
            checks['patch_identity'] = root.tk.call('::tk::accessible::myl_patch_version') == 'myl-tk91-win-msaa-1'
            app = App(root, initial_index={'archivos': synthetic_catalog(12)})
            workspace = app.workspace
            workspace.cover_service.thumbnail_path = lambda *_args, **_kwargs: None
            workspace.refresh_library()
            root.update()

            def snapshot(window):
                root.update()
                data = root.tk.call('::tk::accessible::myl_provider_probe', str(window))
                rows = root.tk.call('dict', 'get', data, 'children')
                children = []
                for row in root.tk.splitlist(rows):
                    values = root.tk.splitlist(row)
                    children.append({'id': int(values[0]), 'name': str(values[1]),
                                     'value': str(values[2]), 'role': int(values[3]),
                                     'state': int(values[4]), 'child_status': int(values[5])})
                return {'declared': int(root.tk.call('dict', 'get', data, 'declared')),
                        'status': int(root.tk.call('dict', 'get', data, 'status')), 'children': children}

            def named(data, name):
                return next((row for row in data['children'] if row['name'] == name), None)

            initial = snapshot(root)
            search = named(initial, _text('search'))
            checks['worker_com_calls'] = initial['status'] == 0
            checks['deep_descendant_discoverable'] = search is not None and search['role'] == 42
            checks['count_matches_enumeration'] = initial['declared'] == len(initial['children']) > len(root.winfo_children())
            checks['unique_positive_child_ids'] = (len({row['id'] for row in initial['children']}) == initial['declared']
                                                   and all(row['id'] > 0 for row in initial['children']))
            checks['simple_child_contract'] = all(row['child_status'] == 1 for row in initial['children'])
            open_button = named(initial, _text('open'))
            checks['disabled_state_visible_to_com'] = open_button is not None and bool(open_button['state'] & 1)
            workspace._set_details_visible(False)
            hidden = snapshot(root)
            checks['hidden_descendants_not_enumerated'] = named(hidden, _text('open')) is None
            checks['stable_id_after_layout_change'] = search is not None and named(hidden, _text('search'))['id'] == search['id']
            workspace._set_details_visible(True)
            root.tk.call('::tk::accessible::add_acc_object', str(root))
            repeated = snapshot(root)
            checks['registration_idempotent'] = search is not None and named(repeated, _text('search'))['id'] == search['id']

            button = tk.Button(root, name='myl_identity_test', text='MYL_QA_identity_before')
            button.pack(side='bottom')
            root.update()
            name_control(button, 'MYL_QA_identity_before')
            before = named(snapshot(root), 'MYL_QA_identity_before')
            button.destroy()
            root.update()
            button = tk.Button(root, name='myl_identity_test', text='MYL_QA_identity_after')
            button.pack(side='bottom')
            root.update()
            name_control(button, 'MYL_QA_identity_after')
            after = named(snapshot(root), 'MYL_QA_identity_after')
            checks['destroyed_id_not_reassigned'] = bool(before and after and after['id'] > before['id'])
            button.destroy()

            workspace.select_item(workspace.filtered_items[0])
            workspace.edit_selected_metadata()
            root.update()
            dialog = next(window for window in root.winfo_children() if isinstance(window, tk.Toplevel))
            pending = list(dialog.winfo_children())
            while pending:
                sentinel = pending.pop()
                if isinstance(sentinel, tk.Entry):
                    break
                pending.extend(sentinel.winfo_children())
            else:
                raise AssertionError('Metadata editor has no visible input fixture')
            name_control(sentinel, 'MYL_QA_dialog_only')
            dialog_data = snapshot(dialog)
            checks['dialog_owns_separate_provider'] = named(dialog_data, 'MYL_QA_dialog_only') is not None
            checks['dialog_not_in_parent_enumeration'] = named(snapshot(root), 'MYL_QA_dialog_only') is None
            dialog.destroy()
            workspace.search_entry.focus_set()
            notify(workspace.search_entry)
            root.update()
            checks['focus_event_does_not_invalidate_ids'] = search is not None and named(snapshot(root), _text('search'))['id'] == search['id']
            checks['no_callback_errors'] = not errors
            checks['no_native_property_errors'] = not root._myl_a11y_errors
            return {'passed': set(checks) == REQUIRED_CHECKS and all(checks.values()), 'checks': checks, 'errors': errors,
                    'scope': 'in_process_msaa_contract_and_background_threads',
                    'external_assistive_client': 'not_run', 'screen_reader_speech': 'not_run',
                    'profile': 'synthetic_disposable', 'tk': root.tk.call('package', 'present', 'Tk')}
        finally:
            if app:
                app.workspace.shutdown()
                app.catalog_gc.close()
            for identifier in root.tk.call('after', 'info'):
                root.tk.call('after', 'cancel', identifier)
            root.destroy()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture-worker', action='store_true')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.fixture_worker:
        report = run_fixture()
    else:
        result = subprocess.run([sys.executable, '-B', str(Path(__file__).resolve()), '--fixture-worker'],
                                capture_output=True, text=True, timeout=90)
        if result.returncode and not result.stdout.lstrip().startswith('{'):
            raise RuntimeError('Native fixture failed: ' + result.stdout[-3000:] + result.stderr[-3000:])
        report = json.loads(result.stdout)
    encoded = json.dumps(report, indent=2)
    if args.output:
        args.output.write_text(encoded + '\n', encoding='utf-8')
    print(encoded)
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())

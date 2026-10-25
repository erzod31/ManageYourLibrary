"""Explicit synthetic fixture for an external reader, never normal app startup.

Only Linux isolated CI may run it. The controller owns the empty command
directory; a separate temporary profile is established before any app imports.
Commands only change focus or open/close an unsaved synthetic metadata editor.
No book is opened, saved, moved or deleted. No speech backend is activated.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

STAGES = ('focus_search', 'focus_authors', 'focus_title', 'focus_author', 'close_editor')
TITLE = 'MYL ORCA synthetic title 42'
AUTHOR = 'MYL ORCA synthetic author 73'
MAX_COMMAND_BYTES = 512


def read_command(path, previous):
    if not path.is_file():
        return None
    if path.is_symlink() or path.stat().st_size > MAX_COMMAND_BYTES:
        raise ValueError('Invalid external-fixture command file')
    command = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(command, dict) or set(command) != {'sequence', 'action'}:
        raise ValueError('Invalid external-fixture command shape')
    sequence = command['sequence']
    if type(sequence) is not int or sequence < 1:
        raise ValueError('Invalid external-fixture sequence')
    if sequence <= previous:
        return None
    if sequence != previous + 1 or command['action'] not in (*STAGES, 'shutdown'):
        raise ValueError('Unsupported external-fixture command')
    return command


def atomic_json(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)


def focus_state(root, target=None):
    actual = root.focus_get()
    top = actual.winfo_toplevel() if actual is not None else None
    return {
        'focus_matches_target': target is not None and actual == target and bool(target.winfo_viewable()),
        'focus_widget': str(actual) if actual is not None else None,
        'requested_focus': str(target) if target is not None else None,
        'focused_toplevel': str(top) if top is not None else None,
        'focused_window_title': top.title() if top is not None else None,
        'root_mapped': bool(root.winfo_ismapped()),
        'focused_toplevel_mapped': bool(top.winfo_ismapped()) if top is not None else False,
        'tk_version': root.tk.call('package', 'present', 'Tk'),
    }


def run_fixture(control, *, version):
    from tools.verify_orca_accessibility import isolated_ci_problem
    problem = isolated_ci_problem(check_reader=False)
    if problem:
        return 2
    if any(name in sys.modules for name in ('library_app', 'library_core')):
        raise RuntimeError('External fixture requires a fresh process before app imports')
    control = Path(control)
    if control.is_symlink():
        raise ValueError('External fixture control directory must not be a symlink')
    control = control.resolve()
    if not control.is_dir() or any(control.iterdir()):
        raise ValueError('External fixture needs an empty existing control directory')
    errors, attempts = [], []
    root = app = None
    current_dialog = None
    entries = []
    sequence = 0
    started = time.monotonic()

    def deny_network(*_args, **_kwargs):
        attempts.append(True)
        raise RuntimeError('Unexpected network access from synthetic fixture')

    with tempfile.TemporaryDirectory(prefix='myl_orca_fixture_') as directory:
        profile = Path(directory) / 'profile'
        profile.mkdir()
        (profile / 'config.json').write_text(json.dumps({
            'language': 'en', 'library': '', 'operation': {'offline_mode': True, 'theme': 'light'},
        }), encoding='utf-8')
        from core import config_store
        with patch.object(config_store, 'app_data_dir', return_value=profile), \
                patch.dict(os.environ, {'MANAGE_YOUR_LIBRARY_PROFILE': str(profile),
                                        'MANAGE_YOUR_LIBRARY_OFFLINE': '1'}), \
                patch('socket.socket.connect', side_effect=deny_network), \
                patch('socket.create_connection', side_effect=deny_network):
            import tkinter as tk
            from library_app import App
            from tools.benchmark_catalog import synthetic_catalog
            from ui.workspace import _text

            root = tk.Tk()
            root.report_callback_exception = lambda kind, value, _tb: errors.append(f'{kind.__name__}: {value}')
            try:
                rows = synthetic_catalog(2)
                for index, row in enumerate(rows):
                    row.update(ruta=str(Path(directory) / f'synthetic-{index}.epub'),
                               titulo=TITLE if index == 0 else 'MYL ORCA other synthetic title',
                               autor=AUTHOR, isbn='', cover_url='')
                app = App(root, initial_index={'archivos': rows})
                root.title('MYL external Orca synthetic fixture')
                root.geometry('1080x840')
                workspace = app.workspace
                workspace.cover_service.thumbnail_path = lambda *_args, **_kwargs: None
                workspace.set_view('table')
                voice = workspace.speech_controls.session
                expected = {
                    'focus_search': {'label': _text('search'), 'role': 'entry'},
                    'focus_authors': {'label': _text('authors'), 'role': 'button'},
                    'focus_title': {'label': _text('title'), 'role': 'entry', 'value': TITLE},
                    'focus_author': {'label': _text('author'), 'role': 'entry', 'value': AUTHOR},
                    'close_editor': {'label': _text('search'), 'role': 'entry'},
                }

                def report_state(action='ready', target=None, retries=25):
                    observed = focus_state(root, target)
                    # Acknowledging a command proves the actual Tk focus,
                    # rather than merely that focus_force was called.
                    if target is not None and not observed['focus_matches_target'] and retries:
                        root.after(40, lambda: report_state(action, target, retries - 1))
                        return
                    atomic_json(control / 'state.json', {
                        'sequence': sequence, 'action': action, 'pid': os.getpid(), 'version': version,
                        'frozen': bool(getattr(sys, 'frozen', False)), 'expected': expected,
                        'voice_off': voice.state == 'off' and voice._thread is None,
                        'no_network': not attempts, 'errors': errors,
                        **observed,
                    })

                def poll():
                    nonlocal sequence, current_dialog, entries
                    if time.monotonic() - started > 85:
                        errors.append('Synthetic external fixture deadline exceeded')
                        root.quit()
                        return
                    try:
                        command = read_command(control / 'command.json', sequence)
                        if command:
                            sequence = command['sequence']
                            action = command['action']
                            target = None
                            if action == 'shutdown':
                                root.quit()
                                return
                            if action in {'focus_search', 'close_editor'}:
                                if current_dialog is not None and current_dialog.winfo_exists():
                                    current_dialog.destroy()
                                current_dialog = None
                                workspace.show_page('library')
                                root.focus_force()
                                root.after(100, workspace.search_entry.focus_force)
                                target = workspace.search_entry
                            elif action == 'focus_authors':
                                target = workspace.nav_buttons['authors']
                                target.focus_force()
                            elif action == 'focus_title':
                                workspace.show_page('library')
                                workspace.set_view('table')
                                workspace.select_item(rows[0])
                                workspace.edit_selected_metadata()
                                current_dialog = next(w for w in root.winfo_children() if isinstance(w, tk.Toplevel))
                                def find_entries(widget):
                                    found = []
                                    for child in widget.winfo_children():
                                        if isinstance(child, tk.Entry):
                                            found.append(child)
                                        found.extend(find_entries(child))
                                    return found
                                entries = find_entries(current_dialog)
                                if len(entries) != 9:
                                    raise RuntimeError('Unexpected synthetic metadata editor fields')
                                target = entries[0]
                                target.focus_force()
                            elif action == 'focus_author':
                                if current_dialog is None or not current_dialog.winfo_exists():
                                    raise RuntimeError('Synthetic metadata editor is not open')
                                target = entries[1]
                                target.focus_force()
                            root.after(180, lambda phase=action, widget=target: report_state(phase, widget))
                    except Exception as exc:
                        errors.append(f'{type(exc).__name__}: {exc}')
                        report_state('error')
                        root.quit()
                        return
                    root.after(40, poll)

                root.after(500, report_state)
                root.after(550, poll)
                root.mainloop()
                report_state('closed')
            finally:
                if app is not None:
                    app.cerrar_aplicacion()
                elif root is not None:
                    root.destroy()
    return 1 if errors or attempts else 0

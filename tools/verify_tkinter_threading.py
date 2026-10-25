"""Exercise the built Tcl 9 bridge in a tiny disposable mainloop.

No library application/profile, reader, speech, network or books are used.
Run in a separate process under the platform build's GUI environment.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

REQUIRED_CHECKS = {'python312_runtime', 'tcl9_runtime', 'tcl9_threaded_pkgconfig',
                   'legacy_threaded_flag_absent', 'foreign_eval_rejected',
                   'worker_call_on_owner', 'stop_callback_on_owner', 'worker_completed',
                   'deadline_not_reached', 'bridge_loaded', 'busywait_unchanged'}


def validate_report(report, *, expected_bridge_sha256=None, expected_contract_sha256=None,
                    expected_platform=None, expected_version=None, expected_frozen=None,
                    expected_executable_sha256=None):
    if (not isinstance(report, dict) or report.get('passed') is not True
            or set(report.get('checks', {})) != REQUIRED_CHECKS
            or any(value is not True for value in report['checks'].values())
            or report.get('python_version') != '3.12.10' or report.get('tcl_version') != '9.1.0'
            or report.get('tk_version') != '9.1.0' or report.get('errors') != []
            or report.get('busywait_interval_ms') != 20
            or report.get('platform') not in {'linux', 'darwin', 'win32'}
            or (expected_platform is not None and report['platform'] != expected_platform)
            or (expected_version is not None and report.get('version') != expected_version)
            or (expected_frozen is not None and report.get('frozen') is not expected_frozen)
            or (expected_executable_sha256 is not None and (
                not re.fullmatch(r'[0-9a-f]{64}', str(report.get('executable_sha256', '')))
                or report['executable_sha256'] != expected_executable_sha256))
            or report.get('reader_started') is not False or report.get('audible_output') != 'not_used'
            or not re.fullmatch(r'[0-9a-f]{64}', str(report.get('bridge_sha256', '')))
            or not re.fullmatch(r'[0-9a-f]{64}', str(report.get('contract_sha256', '')))
            or (expected_bridge_sha256 is not None and report['bridge_sha256'] != expected_bridge_sha256)
            or (expected_contract_sha256 is not None and report['contract_sha256'] != expected_contract_sha256)):
        raise ValueError('Incomplete Tcl 9 bridge threading contract')
    return report


def contract_source():
    if getattr(sys, 'frozen', False):
        # The executing module is in PYZ. Hash the exact source retained as
        # build/runtime evidence, never a nonexistent __file__ inside PYZ.
        return Path(sys._MEIPASS) / 'licenses/tcltk/myl-tkinter-tcl9-repair/verify_tkinter_threading.py'
    return Path(__file__)


def run_checks(expected_bridge_sha256):
    import _tkinter
    import tkinter as tk
    checks = dict.fromkeys(REQUIRED_CHECKS, False)
    report = {'passed': False, 'checks': checks,
              'scope': 'tkinter_tcl9_worker_owner_and_mainloop_not_external_reader_validation',
              'python_version': '.'.join(map(str, sys.version_info[:3])),
              'platform': sys.platform,
              'contract_sha256': '',
              'reader_started': False, 'audible_output': 'not_used', 'errors': []}
    root = None
    worker = None
    commands = ('myl_thread_owner_probe', 'myl_thread_owner_stop')
    samples = []
    try:
        report['contract_sha256'] = hashlib.sha256(contract_source().read_bytes()).hexdigest()
        root = tk.Tk()
        root.withdraw()
        report['tcl_version'] = str(root.tk.call('info', 'patchlevel'))
        report['tk_version'] = str(root.tk.call('package', 'present', 'Tk'))
        checks['python312_runtime'] = report['python_version'] == '3.12.10'
        checks['tcl9_runtime'] = report['tcl_version'] == report['tk_version'] == '9.1.0'
        checks['tcl9_threaded_pkgconfig'] = str(root.tk.call('tcl::pkgconfig', 'get', 'threaded')) == '1'
        checks['legacy_threaded_flag_absent'] = not bool(root.tk.getboolean(
            root.tk.call('info', 'exists', 'tcl_platform(threaded)')))
        bridge = Path(_tkinter.__file__)
        report['bridge_sha256'] = hashlib.sha256(bridge.read_bytes()).hexdigest()
        checks['bridge_loaded'] = report['bridge_sha256'] == expected_bridge_sha256
        report['busywait_interval_ms'] = _tkinter.getbusywaitinterval()
        checks['busywait_unchanged'] = report['busywait_interval_ms'] == 20
        if not all(checks[key] for key in ('python312_runtime', 'tcl9_runtime', 'tcl9_threaded_pkgconfig',
                                          'legacy_threaded_flag_absent', 'bridge_loaded', 'busywait_unchanged')):
            raise RuntimeError('The contract requires the pinned Python 3.12.10 / Tcl-Tk 9.1 bridge')
        owner = threading.get_ident()
        callback_threads = []
        deadline_reached = []

        def called_by_worker():
            callback_threads.append(threading.get_ident())
            return 'synthetic-owner-reply'

        def stop_on_owner():
            checks['stop_callback_on_owner'] = threading.get_ident() == owner
            root.quit()
            return ''

        def deadline():
            deadline_reached.append(True)
            root.quit()

        root.tk.createcommand(commands[0], called_by_worker)
        root.tk.createcommand(commands[1], stop_on_owner)

        def exercise_worker():
            try:
                try:
                    root.tk.eval('expr {1 + 1}')
                except RuntimeError as exc:
                    checks['foreign_eval_rejected'] = 'different apartment' in str(exc)
                for _ in range(20):
                    started = time.perf_counter()
                    result = root.tk.call(commands[0])
                    samples.append((time.perf_counter() - started) * 1000)
                    if result != 'synthetic-owner-reply':
                        raise RuntimeError('Unexpected synthetic worker reply')
                checks['worker_completed'] = True
            except (tk.TclError, RuntimeError, OSError, ValueError) as exc:
                report['errors'].append(type(exc).__name__)
            finally:
                try:
                    root.tk.call(commands[1])
                except (tk.TclError, RuntimeError) as exc:
                    report['errors'].append(type(exc).__name__)

        def start_worker():
            nonlocal worker
            worker = threading.Thread(target=exercise_worker, daemon=True)
            worker.start()

        root.after(0, start_worker)
        guard = root.after(5000, deadline)
        root.mainloop()
        root.after_cancel(guard)
        if worker:
            worker.join(timeout=1)
        checks['worker_completed'] = checks['worker_completed'] and worker is not None and not worker.is_alive()
        checks['worker_call_on_owner'] = len(callback_threads) == 20 and all(value == owner for value in callback_threads)
        checks['deadline_not_reached'] = not deadline_reached
        if samples:
            ordered = sorted(samples)
            report['roundtrip'] = {'scope': 'tkinter_worker_call_not_atspi', 'unit': 'milliseconds',
                                   'samples': len(ordered), 'p50': ordered[len(ordered) // 2],
                                   'p95': ordered[(len(ordered) * 95 - 1) // 100]}
    except (tk.TclError, RuntimeError, OSError, ValueError) as exc:
        report['errors'].append(type(exc).__name__)
    finally:
        if root is not None:
            for name in commands:
                try:
                    root.tk.deletecommand(name)
                except tk.TclError:
                    pass
            try:
                root.destroy()
            except tk.TclError as exc:
                report['errors'].append(type(exc).__name__)
        checks['busywait_unchanged'] = checks['busywait_unchanged'] and _tkinter.getbusywaitinterval() == 20
    report['passed'] = all(checks.values()) and not report['errors']
    return report


def run_and_record(output, *, expected_bridge_sha256, version=None):
    output = Path(output)
    if output.exists():
        raise FileExistsError('Refusing to overwrite earlier bridge evidence')
    if not re.fullmatch(r'[0-9a-f]{64}', expected_bridge_sha256):
        raise ValueError('Expected the built bridge SHA-256 before starting a GUI contract')
    report = run_checks(expected_bridge_sha256)
    if version is not None:
        report.update(version=version, frozen=bool(getattr(sys, 'frozen', False)),
                      executable_sha256=hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest())
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as handle:
        json.dump(report, handle, indent=2)
    print(json.dumps(report))
    return 0 if report['passed'] else 1


def run_application_and_record(output, *, version):
    import _tkinter
    return run_and_record(output, expected_bridge_sha256=hashlib.sha256(Path(_tkinter.__file__).read_bytes()).hexdigest(),
                          version=version)


def run_frozen_process(executable, output):
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise FileExistsError('Refusing to overwrite earlier frozen bridge evidence')
    # The mainloop's own timer cannot bound a broken event notifier or shutdown.
    return subprocess.run([str(executable), '--tkinter-threading-self-test', str(output)],
                          stdin=subprocess.DEVNULL, timeout=15, check=False).returncode


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--expected-bridge-sha256')
    mode.add_argument('--frozen-executable', type=Path)
    args = parser.parse_args()
    if args.frozen_executable is not None:
        raise SystemExit(run_frozen_process(args.frozen_executable, args.output))
    raise SystemExit(run_and_record(args.output, expected_bridge_sha256=args.expected_bridge_sha256))

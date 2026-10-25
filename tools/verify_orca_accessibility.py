"""Exercise unmodified Orca 42.0 in silent, dedicated Linux CI only.

Run inside a fresh D-Bus/Xvfb session with GSETTINGS_BACKEND=memory and
MYL_ISOLATED_A11Y_CI=1. Requires /usr/bin/orca and /usr/bin/openbox from apt.
No reader is installed or run on Windows. Unsupported/preflight conditions
produce not_run and a nonzero exit; they never count as successful evidence.
Orca remains an external QA dependency, never an application dependency.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

MAX_LOG_BYTES = 8 * 1024 * 1024
TOTAL_SECONDS = 75
REVIEWED_VERSION = '42.0'
STAGES = ('focus_search', 'focus_authors', 'focus_title', 'focus_author', 'close_editor')
REQUIRED_CHECKS = {'isolated_ci', 'reviewed_orca', 'output_disabled_at_start',
                   'fixture_frozen_and_isolated', 'fixture_voice_off', 'fixture_no_network',
                   'fixture_no_errors', 'reader_no_exceptions', 'owned_processes_stopped'} | set(STAGES)


def existing_readers(proc_root=Path('/proc')):
    result = []
    for path in proc_root.glob('[0-9]*/comm'):
        try:
            if path.read_text().strip().lower() == 'orca':
                result.append(int(path.parent.name))
        except (OSError, ValueError):
            continue
    return result


def isolated_ci_problem(env=None, *, check_reader=True):
    env = os.environ if env is None else env
    if sys.platform != 'linux':
        return 'linux_only'
    if env.get('GITHUB_ACTIONS') != 'true' or env.get('MYL_ISOLATED_A11Y_CI') != '1':
        return 'requires_dedicated_isolated_ci'
    if env.get('GSETTINGS_BACKEND') != 'memory':
        return 'requires_nonpersistent_settings_backend'
    if not re.fullmatch(r':\d+(?:\.\d+)?', env.get('DISPLAY', '')) or env.get('WAYLAND_DISPLAY'):
        return 'requires_dedicated_xvfb_display'
    bus = env.get('DBUS_SESSION_BUS_ADDRESS', '')
    if not bus.startswith('unix:') or '/tmp/' not in bus or '/run/user/' in bus:
        return 'requires_private_temporary_dbus_session'
    if Path('/dev/snd').exists() or Path('/dev/dsp').exists():
        return 'audio_devices_present_no_silent_run'
    if check_reader and existing_readers():
        return 'existing_reader_will_not_be_replaced'
    return None


def silent_environment(base, directory):
    env = dict(base)
    # HOME is deliberately unchanged. All explicit reader preferences and XDG
    # state live in new temporary directories; no normal profile is imported.
    for key, name in (('XDG_CONFIG_HOME', 'config'), ('XDG_CACHE_HOME', 'cache'),
                      ('XDG_DATA_HOME', 'data'), ('XDG_RUNTIME_DIR', 'runtime')):
        path = directory / name
        path.mkdir(mode=0o700)
        env[key] = str(path)
    env.update(GSETTINGS_BACKEND='memory', LANG='C.UTF-8', LC_ALL='C.UTF-8', LANGUAGE='en',
               PULSE_SERVER='unix:' + str(directory / 'no-pulse.sock'),
               SPEECHD_ADDRESS='unix_socket:' + str(directory / 'no-speech.sock'),
               MANAGE_YOUR_LIBRARY_OFFLINE='1', PYTHONDONTWRITEBYTECODE='1')
    for key in ('PYTHONHOME', 'PYTHONPATH', 'MANAGE_YOUR_LIBRARY_PROFILE'):
        env.pop(key, None)
    alsa = directory / 'alsa-null.conf'
    alsa.write_text('pcm.!default { type null }\n', encoding='utf-8')
    env['ALSA_CONFIG_PATH'] = str(alsa)
    return env


def reader_preferences(directory):
    directory.mkdir()
    general = {'profile': ['QA', 'default'], 'startingProfile': ['QA', 'default'],
               'activeProfile': ['QA', 'default'], 'enableSpeech': False,
               'enableBraille': False, 'enableBrailleMonitor': False,
               'enableSound': False, 'enableMouseReview': False}
    data = {'general': general, 'profiles': {'default': dict(general)},
            'pronunciations': {}, 'keybindings': {}}
    (directory / 'user-settings.conf').write_text(json.dumps(data), encoding='utf-8')


def reader_command(reader, preferences, trace):
    # These options are reviewed against Orca's ORCA_42_0 CLI Settings parser.
    # --replace/--setup are forbidden: never affect an unrelated reader.
    return [str(reader), '--user-prefs=' + str(preferences),
            '--disable=speech,braille,braille-monitor,sound,mouse-review',
            '--debug', '--debug-file=' + str(trace)]


def read_bounded_bytes(path):
    if not path.is_file():
        return b''
    if path.stat().st_size > MAX_LOG_BYTES:
        raise RuntimeError('External reader log exceeded its bound')
    with path.open('rb') as handle:
        raw = handle.read(MAX_LOG_BYTES + 1)
    if len(raw) > MAX_LOG_BYTES:
        raise RuntimeError('External reader log exceeded its bound')
    return raw


def read_bounded(path):
    return read_bounded_bytes(path).decode('utf-8', errors='replace')


def normalize_log(text, directory):
    for value in (str(directory), str(directory).replace('\\', '/'), str(Path.home()), Path.home().as_posix()):
        if value:
            text = text.replace(value, '<QA_ROOT>' if str(directory) in value else '<USER_PROFILE>')
    text = re.sub(r'[A-Za-z]:[\\/]+Users[\\/]+[^\\/\s\'\"]+', '<USER_PROFILE>', text, flags=re.I)
    text = re.sub(r'/(?:home|Users)/[^/\s\'\"]+', '<USER_PROFILE>', text)
    text = re.sub(r'/tmp/myl_orca_[A-Za-z0-9_.-]+', '<QA_ROOT>', text)
    return text[:24000]


def silent_startup(trace):
    forbidden = ('SPEECH: Initializing', 'SPEECH: Using speech server', 'ORCA: About to enable speech')
    return ('ORCA: Speech is not enabled in settings' in trace
            and 'ORCA: Braille is not enabled in settings' in trace
            and 'ORCA: User Settings Loaded' in trace
            and not any(marker in trace for marker in forbidden))


def phase_evidence(trace, expected):
    presentation = [line for line in trace.splitlines() if 'SPEECH OUTPUT:' in line]
    spoken = ' '.join(presentation)
    role = r'\bbutton\b' if expected['role'] == 'button' else r'\b(?:entry|text|edit)\b'
    focus = bool(re.search(r'OBJECT EVENT:\s+(?:object:state-changed:focused|focus:)\s+\(1,', trace))
    label = bool(expected['label']) and expected['label'] in spoken
    value = not expected.get('value') or expected['value'] in spoken
    role_presented = bool(re.search(role, spoken, re.I))
    return {'passed': focus and label and value and role_presented,
            'focus_event_consumed': focus, 'label_presented': label,
            'synthetic_value_presented': value, 'role_presented': role_presented,
            'presentation_lines': presentation[-12:]}


def reader_diagnostic_errors(trace):
    # Orca's debug.println catches failed writes without printing a traceback.
    # Such a log cannot prove that all output-safety diagnostics were retained.
    markers = ('Traceback (most recent call last)', 'Exception when trying to write text',
               'TypeError when trying to write text', 'ERROR: Could not process ',
               'ERROR: Could not set active script ', 'ERROR: Could not get script ')
    return [marker for marker in markers if marker in trace]


def trace_integrity(before_termination, after_termination, *, overflow=False, capture_error=None):
    prefix_preserved = after_termination.startswith(before_termination)
    suffix = after_termination[len(before_termination):] if prefix_preserved else ''
    # Compare actual bytes when available: a PTY read may split a UTF-8
    # character, which must not be mistaken for modified capture contents.
    before_text = before_termination.decode('utf-8', errors='replace') if isinstance(before_termination, bytes) else before_termination
    suffix_text = suffix.decode('utf-8', errors='replace') if isinstance(suffix, bytes) else suffix
    during = reader_diagnostic_errors(before_text)
    after = reader_diagnostic_errors(suffix_text)
    return {'reader_no_exceptions': not during and prefix_preserved and not overflow and not capture_error,
            'during_test_errors': during, 'termination_messages': after,
            'prefix_preserved': prefix_preserved,
            'capture_complete': prefix_preserved and not overflow and not capture_error}


def focus_trace_context(trace):
    """Keep adjacent name/role/state and script decisions, not event headers alone."""
    lines = trace.splitlines()
    selected = set()
    markers = ('OBJECT EVENT:', 'EVENT MANAGER: object:state-changed:focused',
               'EVENT MANAGER: window:', 'active window', 'activeWindow', 'activeScript',
               'locusOfFocus', 'active script', 'SPEECH OUTPUT:', 'ERROR', 'Exception',
               'Speech is not enabled', 'Braille is not enabled')
    for index, line in enumerate(lines):
        if any(marker in line for marker in markers):
            selected.update(range(max(0, index - 1), min(len(lines), index + 14)))
    return '\n'.join(lines[index] for index in sorted(selected))[-22000:]


def api_snapshot(fixture_pid, env):
    """Read the owned synthetic app only; API inspection is never a pass criterion."""
    try:
        result = subprocess.run(['/usr/bin/python3', '-B', str(ROOT / 'tools/inspect_atspi_fixture.py'),
                                 '--pid', str(fixture_pid)], env=env, stdin=subprocess.DEVNULL,
                                capture_output=True, text=True, timeout=4, check=True)
        if len(result.stdout) > 16000:
            return {'error': 'api_diagnostic_exceeded_bound'}
        return json.loads(result.stdout)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        return {'error': type(exc).__name__, 'scope': 'atspi_api_diagnostic_not_reader_certification'}


def stop_owned(process):
    if process is None:
        return True
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)
    return process.poll() is not None


def diagnostic_text(path):
    try:
        return read_bounded(path)
    except (OSError, RuntimeError):
        return '[QA log omitted: unreadable or exceeded size bound]'


class ReaderTrace:
    """Capture real Orca diagnostics via a terminal, without patching Orca.

    Orca opens its debug destination itself. A regular file is block buffered,
    so a controller waiting for one focus presentation could deadlock waiting
    for a flush. A private PTY makes /dev/stderr line buffered. No keyboard
    input or user terminal is attached; only this reader's output is drained.
    """
    def __init__(self, path):
        import pty
        self.master, self.slave = pty.openpty()
        try:
            self.handle = path.open('wb')
        except OSError:
            os.close(self.master)
            os.close(self.slave)
            raise
        self.stop = threading.Event()
        self.overflow = False
        self.capture_error = None
        self.finished = False
        self.thread = threading.Thread(target=self._drain, daemon=True)
        self.thread.start()

    def _drain(self):
        import select
        size = 0
        while not self.stop.is_set():
            try:
                if not select.select([self.master], [], [], .1)[0]:
                    continue
                data = os.read(self.master, 8192)
            except OSError as exc:
                if exc.errno not in {errno.EIO, errno.EBADF}:
                    self.capture_error = 'reader_trace_read_failed'
                break
            if not data:
                break
            size += len(data)
            if size > MAX_LOG_BYTES:
                self.overflow = True
                break
            try:
                self.handle.write(data)
                self.handle.flush()
            except OSError:
                self.capture_error = 'reader_trace_write_failed'
                break

    def release_slave(self):
        if self.slave is not None:
            os.close(self.slave)
            self.slave = None

    def finish(self):
        if self.finished:
            return
        self.release_slave()
        self.thread.join(timeout=1)
        self.stop.set()
        self.thread.join(timeout=1)
        if self.thread.is_alive():
            self.capture_error = 'reader_trace_thread_not_stopped'
        os.close(self.master)
        self.handle.close()
        self.finished = True

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.finish()


def run_checks(executable):
    report = {'passed': False, 'status': 'not_run', 'checks': {},
              'scope': 'external_orca_focus_presentation_not_audible_or_keyboard_certification',
              'reader': 'Orca', 'audible_playback': 'not_run', 'braille_output': 'disabled',
              'profile': 'synthetic_disposable', 'raw_logs_retained': False}
    problem = isolated_ci_problem()
    if problem:
        report['reason'] = problem
        return report
    reader, manager = Path('/usr/bin/orca'), Path('/usr/bin/openbox')
    executable = Path(executable).resolve()
    if not reader.is_file() or not manager.is_file() or not executable.is_file():
        report['reason'] = 'missing_ci_reader_window_manager_or_frozen_application'
        return report
    checks = report['checks']
    checks['isolated_ci'] = True
    deadline = time.monotonic() + TOTAL_SECONDS
    processes = []
    collector = None
    fixture = None
    phase = None
    previous = ''
    ready = None
    with tempfile.TemporaryDirectory(prefix='myl_orca_ci_') as temporary, ExitStack() as stack:
        directory = Path(temporary)
        env = silent_environment(os.environ, directory)
        preferences, trace = directory / 'reader', directory / 'orca-debug.log'
        reader_preferences(preferences)
        try:
            version = subprocess.run([str(reader), '--version'], env=env, capture_output=True,
                                     stdin=subprocess.DEVNULL, text=True, timeout=8, check=True).stdout.strip()
            report['reader_version'] = version[:120]
            if version != REVIEWED_VERSION:
                report['reason'] = 'reader_version_not_reviewed_for_silent_presentation'
                return report
            checks['reviewed_orca'] = True
            report['reader_entry_sha256'] = hashlib.sha256(reader.read_bytes()).hexdigest()
            report['application_sha256'] = hashlib.sha256(executable.read_bytes()).hexdigest()
            wm_log = stack.enter_context((directory / 'wm.log').open('w'))
            wm = subprocess.Popen([str(manager)], env=env, stdin=subprocess.DEVNULL,
                                  stdout=wm_log, stderr=subprocess.STDOUT,
                                  start_new_session=True)
            processes.append(wm)
            collector = stack.enter_context(ReaderTrace(trace))
            orca = subprocess.Popen(reader_command(reader, preferences, Path('/dev/stderr')), env=env,
                                    stdin=subprocess.DEVNULL, stdout=collector.slave, stderr=collector.slave,
                                    start_new_session=True)
            collector.release_slave()
            processes.append(orca)

            def wait_until(predicate, seconds, description):
                end = min(deadline, time.monotonic() + seconds)
                while time.monotonic() < end:
                    if any(process.poll() is not None for process in processes):
                        raise RuntimeError('A QA process exited during ' + description)
                    if predicate():
                        return
                    time.sleep(.05)
                raise TimeoutError('External reader deadline: ' + description)

            wait_until(lambda: silent_startup(read_bounded(trace)), 15, 'silent Orca startup')
            checks['output_disabled_at_start'] = True
            control = directory / 'fixture'
            control.mkdir()
            fixture_log = stack.enter_context((directory / 'fixture.log').open('w'))
            fixture = subprocess.Popen([str(executable), '--external-accessibility-fixture', str(control)],
                                       env=env, stdin=subprocess.DEVNULL, stdout=fixture_log,
                                       stderr=subprocess.STDOUT, start_new_session=True)
            processes.append(fixture)

            def state():
                value = read_bounded(control / 'state.json')
                return json.loads(value) if value else None

            wait_until(lambda: bool(state()), 12, 'synthetic app startup')
            ready = state()
            checks['fixture_frozen_and_isolated'] = (ready.get('frozen') is True
                                                     and ready.get('pid') == fixture.pid)
            checks['fixture_voice_off'] = ready.get('voice_off') is True
            checks['fixture_no_network'] = ready.get('no_network') is True
            if not all(checks.values()):
                raise RuntimeError('Synthetic frozen fixture isolation checks failed')
            report['version'] = ready['version']
            presentations = {}
            report['presentations'] = presentations
            for sequence, phase in enumerate(STAGES, 1):
                previous = read_bounded(trace)
                command = control / 'command.tmp'
                command.write_text(json.dumps({'sequence': sequence, 'action': phase}), encoding='utf-8')
                command.replace(control / 'command.json')
                wait_until(lambda seq=sequence: state().get('sequence') == seq, 4, 'fixture ' + phase)
                acknowledged = state()
                if acknowledged.get('focus_matches_target') is not True:
                    raise RuntimeError('Synthetic fixture did not acquire the requested real Tk focus')
                def presented():
                    current = read_bounded(trace)
                    if not silent_startup(current):
                        raise RuntimeError('Reader output safety contract changed')
                    return phase_evidence(current[len(previous):], ready['expected'][phase])['passed']
                wait_until(presented, 8, 'Orca presentation ' + phase)
                evidence = phase_evidence(read_bounded(trace)[len(previous):], ready['expected'][phase])
                evidence['presentation_lines'] = [normalize_log(line, directory) for line in evidence['presentation_lines']]
                presentations[phase] = evidence
                checks[phase] = evidence['passed']
            final = state()
            checks['fixture_no_errors'] = not final['errors']
            checks['fixture_voice_off'] = checks['fixture_voice_off'] and final['voice_off'] is True
            checks['fixture_no_network'] = checks['fixture_no_network'] and final['no_network'] is True
            report['status'] = 'passed' if all(checks.values()) else 'failed'
        except Exception as exc:
            report['status'] = 'failed'
            report['reason'] = normalize_log(f'{type(exc).__name__}: {exc}', directory)
            # Keep bounded, normalized reader/fixture diagnostics, never raw
            # keystroke or full desktop logs. All fixture values are synthetic.
            before_cleanup = diagnostic_text(trace)
            report['diagnostics'] = {name: normalize_log(diagnostic_text(directory / name)[-12000:], directory)
                                     for name in ('orca-debug.log', 'fixture.log', 'wm.log')}
            report['pre_cleanup_trace_context'] = normalize_log(focus_trace_context(before_cleanup), directory)
            if phase is not None and ready is not None:
                partial = phase_evidence(before_cleanup[len(previous):], ready['expected'][phase])
                partial['presentation_lines'] = [normalize_log(line, directory) for line in partial['presentation_lines']]
                report['failed_phase'] = {'action': phase, 'expected': ready['expected'][phase], 'evidence': partial}
            if fixture is not None and fixture.poll() is None:
                try:
                    report['fixture_state_before_cleanup'] = json.loads(normalize_log(json.dumps(state()), directory))
                except (OSError, ValueError) as state_error:
                    report['fixture_state_before_cleanup'] = {'error': type(state_error).__name__}
                snapshot = api_snapshot(fixture.pid, env)
                report['atspi_before_cleanup'] = json.loads(normalize_log(json.dumps(snapshot), directory))
        finally:
            # Separate reader behavior during the test from diagnostics emitted
            # only after our explicit termination of the synthetic processes.
            try:
                test_trace = read_bounded_bytes(trace)
            except (OSError, RuntimeError):
                test_trace = b''
                report['status'] = 'failed'
                report['reason'] = 'Reader test trace was unreadable or exceeded its bound'
            report['test_trace_sha256'] = hashlib.sha256(test_trace).hexdigest()
            for process in reversed(processes):
                try:
                    stop_owned(process)
                except (OSError, subprocess.TimeoutExpired) as exc:
                    report['cleanup_error'] = normalize_log(type(exc).__name__, directory)
            checks['owned_processes_stopped'] = all(process.poll() is not None for process in processes)
            if collector is not None:
                collector.finish()
                if collector.overflow:
                    report['status'] = 'failed'
                    report['reason'] = 'Reader trace exceeded its capture bound'
                if collector.capture_error:
                    report['status'] = 'failed'
                    report['reason'] = collector.capture_error
            try:
                full_trace_bytes = read_bounded_bytes(trace)
                full_trace = full_trace_bytes.decode('utf-8', errors='replace')
                report['trace_sha256'] = hashlib.sha256(full_trace_bytes).hexdigest()
            except (OSError, RuntimeError):
                full_trace = ''
                full_trace_bytes = b''
                report['trace_sha256'] = None
                report['status'] = 'failed'
                report['reason'] = 'Reader trace was unreadable or exceeded its bound'
            integrity = trace_integrity(test_trace, full_trace_bytes,
                                        overflow=collector.overflow if collector else False,
                                        capture_error=collector.capture_error if collector else None)
            diagnostic_errors = integrity['during_test_errors']
            checks['reader_no_exceptions'] = integrity['reader_no_exceptions']
            cleanup_messages = integrity['termination_messages']
            if cleanup_messages:
                report['cleanup_diagnostic_messages'] = cleanup_messages
            if not integrity['capture_complete']:
                report['status'] = 'failed'
                report['trace_integrity'] = integrity
                report.setdefault('reason', 'Reader trace was incomplete or changed during cleanup')
            if diagnostic_errors:
                report['diagnostic_integrity_errors'] = diagnostic_errors
                if report['status'] == 'passed':
                    report['status'] = 'failed'
                    report['reason'] = 'Reader diagnostics contain an exception or failed capture write'
            if 'output_disabled_at_start' in checks:
                checks['output_disabled_at_start'] = checks['output_disabled_at_start'] and silent_startup(full_trace)
            if report['status'] != 'passed':
                report['normalized_trace_excerpt'] = normalize_log(focus_trace_context(full_trace), directory)
    report['passed'] = report['status'] == 'passed' and set(checks) == REQUIRED_CHECKS and all(checks.values())
    if not report['passed'] and report['status'] == 'passed':
        report['status'] = 'failed'
    return report


def run_and_record(executable, output):
    output = Path(output)
    if output.exists():
        raise FileExistsError('Refusing to overwrite earlier external-reader evidence')
    report = run_checks(executable)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as handle:
        json.dump(report, handle, indent=2)
    print(json.dumps({'passed': report['passed'], 'status': report['status'], 'reason': report.get('reason')}))
    return 0 if report['passed'] else 2 if report['status'] == 'not_run' else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--executable', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(run_and_record(args.executable, args.output))

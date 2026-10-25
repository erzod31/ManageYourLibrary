"""Verify the real Windows voice to a temporary WAV, never an audio device.

Uses only synthetic UI text and a disposable app profile. This is not a hearing
test, external reader test or a change to any system voice/output setting.
"""
from __future__ import annotations

import ctypes as ct
import hashlib
import json
import sys
import tempfile
import threading
import time
import wave
from pathlib import Path
from unittest.mock import patch

from core.sapi_speech import DISPPARAMS, GUID, VARIANT, WindowsVoice, _check

REQUIRED_CHECKS = {
    'off_without_engine_at_start', 'explicit_controls_present', 'activate_button_starts_owned_engine',
    'real_sapi_render_completed', 'focus_loss_purges', 'background_text_rejected',
    'deactivate_closes_engine', 'output_is_verified_file', 'real_nonempty_pcm',
    'no_automatic_reactivation', 'explicit_restart_works', 'close_ends_owned_session',
    'no_callback_errors', 'no_native_property_errors',
}


def _method(pointer, index, result, *arguments):
    table = ct.cast(pointer, ct.POINTER(ct.POINTER(ct.c_void_p))).contents
    return ct.WINFUNCTYPE(result, ct.c_void_p, *arguments)(table[index])


def _release(pointer):
    if pointer:
        _method(pointer, 2, ct.c_uint32)(pointer)


def _member(pointer, name):
    names = (ct.c_wchar_p * 1)(name)
    member = ct.c_int32()
    iid = GUID()
    call = _method(pointer, 5, ct.c_int32, ct.POINTER(GUID), ct.POINTER(ct.c_wchar_p),
                   ct.c_uint32, ct.c_uint32, ct.POINTER(ct.c_int32))
    _check(call(pointer, ct.byref(iid), names, 1, 0, ct.byref(member)))
    return member


def _invoke(pointer, name, arguments=(), *, flags=1):
    values = (VARIANT * len(arguments))()
    for target, (kind, value) in zip(values, reversed(arguments)):
        target.kind = kind
        if kind in {8, 9}:
            target.value.pointer = value.value if isinstance(value, ct.c_void_p) else value
        else:
            target.value.integer = value
    property_put = ct.c_int32(-3)  # DISPID_PROPERTYPUT
    params = DISPPARAMS(values, ct.pointer(property_put) if flags & (4 | 8) else None,
                        len(values), 1 if flags & (4 | 8) else 0)
    result, iid = VARIANT(), GUID()
    call = _method(pointer, 6, ct.c_int32, ct.c_int32, ct.POINTER(GUID), ct.c_uint32,
                   ct.c_uint16, ct.POINTER(DISPPARAMS), ct.POINTER(VARIANT), ct.c_void_p, ct.c_void_p)
    _check(call(pointer, _member(pointer, name), ct.byref(iid), 0, flags,
                ct.byref(params), ct.byref(result), None, None))
    return result


def _identity(pointer):
    iid = GUID.parse('00000000-0000-0000-C000-000000000046')
    result = ct.c_void_p()
    call = _method(pointer, 0, ct.c_int32, ct.POINTER(GUID), ct.POINTER(ct.c_void_p))
    _check(call(pointer, ct.byref(iid), ct.byref(result)))
    try:
        return result.value
    finally:
        _release(result)


class CapturedVoice(WindowsVoice):
    """Use production Speak/Stop, but fail closed unless output is our WAV."""
    def __init__(self, path, evidence):
        self._stream = ct.c_void_p()
        self._capture_ready = False
        self.evidence = evidence
        super().__init__()  # Creates an object only; never calls Speak.
        try:
            clsid = GUID()
            _check(self._ole.CLSIDFromProgID('SAPI.SpFileStream', ct.byref(clsid)))
            iid = GUID.parse('00020400-0000-0000-C000-000000000046')
            _check(self._ole.CoCreateInstance(ct.byref(clsid), None, 1, ct.byref(iid), ct.byref(self._stream)))
            filename = self._automation.SysAllocString(str(path))
            if not filename:
                raise MemoryError('Unable to allocate capture filename')
            try:
                _invoke(self._stream, 'Open', ((8, filename), (3, 3), (11, 0)))
            finally:
                self._automation.SysFreeString(filename)
            _invoke(self._dispatch, 'AudioOutputStream', ((9, self._stream),), flags=8)
            output = _invoke(self._dispatch, 'AudioOutputStream', flags=2)
            try:
                if output.kind != 9 or not output.value.pointer:
                    raise RuntimeError('No file output stream')
                if _identity(ct.c_void_p(output.value.pointer)) != _identity(self._stream):
                    raise RuntimeError('Voice output is not the capture stream')
            finally:
                if output.kind == 9:
                    _release(ct.c_void_p(output.value.pointer))
            self._capture_ready = True
            evidence['file_output_verified'] = True
        except Exception:
            # Absolutely no purge/Speak on an unredirected voice, even on error.
            try:
                self._close_stream()
            finally:
                self._release()
            raise

    def speak(self, text):
        if not self._capture_ready:
            raise RuntimeError('Refusing speech without verified file output')
        super().speak(text)
        if text:
            completed = _invoke(self._dispatch, 'WaitUntilDone', ((3, 5000),))
            if completed.kind != 11 or not completed.value.integer:
                raise TimeoutError('Synthetic speech capture timed out')
            self.evidence['rendered'].set()

    def stop(self):
        super().stop()
        self.evidence['purged'].set()

    def _close_stream(self):
        if self._stream:
            try:
                _invoke(self._stream, 'Close')
            finally:
                _release(self._stream)
                self._stream = ct.c_void_p()

    def close(self):
        self._assert_owner()
        try:
            if self._capture_ready and self._dispatch:
                self.stop()
                _invoke(self._dispatch, 'WaitUntilDone', ((3, 5000),))
        finally:
            try:
                self._close_stream()
            finally:
                self._release()
                self.evidence['closed'].set()


def wave_evidence(path):
    with wave.open(str(path), 'rb') as stream:
        frames = stream.readframes(stream.getnframes())
        return {'frames': stream.getnframes(), 'rate': stream.getframerate(),
                'channels': stream.getnchannels(), 'sample_width': stream.getsampwidth(),
                'nonzero_samples': any(frames), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def run_checks(version):
    report = {'version': version, 'frozen': bool(getattr(sys, 'frozen', False)),
              'audio_destination': 'temporary_wav_only', 'audible_playback': 'not_run',
              'external_screen_reader': 'not_run', 'checks': {}}
    checks = report['checks']
    if sys.platform != 'win32':
        return {**report, 'passed': False, 'error': 'Windows-only local voice'}
    if 'library_core' in sys.modules or 'library_app' in sys.modules:
        return {**report, 'passed': False, 'error': 'Requires a fresh diagnostic process'}
    from core import config_store
    with tempfile.TemporaryDirectory(prefix='myl_local_voice_') as directory, \
            patch.object(config_store, 'app_data_dir', return_value=Path(directory) / 'profile'):
        import tkinter as tk
        from core import app_speech
        from library_app import App
        instances, errors = [], []
        root = tk.Tk()
        root.withdraw()
        root.report_callback_exception = lambda kind, _value, _tb: errors.append(kind.__name__)
        app = None
        def factory():
            data = {'rendered': threading.Event(), 'purged': threading.Event(), 'closed': threading.Event(),
                    'path': Path(directory) / f'capture-{len(instances)}.wav'}
            instances.append(data)
            return CapturedVoice(data['path'], data)
        def wait(predicate, timeout=8):
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                root.update()
                if predicate():
                    return True
                threading.Event().wait(.01)
            return False
        try:
            with patch.object(app_speech, '_windows_backend', factory):
                app = App(root, initial_index={'archivos': []})
            controls = app.workspace.speech_controls
            session = controls.session
            root.update()
            checks['off_without_engine_at_start'] = session.state == 'off' and not instances and session._thread is None
            checks['explicit_controls_present'] = all(button.winfo_manager() == 'grid' for button in (
                controls.activate_button, controls.deactivate_button))
            # Internal fixture only: no external desktop focus/input injection.
            def foreground():
                controls._foreground = True
                session.set_foreground(True)
            with patch.object(controls, '_sync_foreground', side_effect=foreground):
                controls.activate_button.invoke()
                checks['activate_button_starts_owned_engine'] = wait(lambda: session.state in {'on', 'error'}) and session.state == 'on'
                if not checks['activate_button_starts_owned_engine']:
                    raise RuntimeError('Real local voice initialization failed')
                session.say('Library voice verification. Synthetic test only.')
                checks['real_sapi_render_completed'] = wait(lambda: bool(instances) and instances[0]['rendered'].is_set())
                session.set_foreground(False)
                checks['focus_loss_purges'] = wait(lambda: instances[0]['purged'].is_set())
                checks['background_text_rejected'] = not session.say('Must not be rendered')
                controls._poll()
                controls.deactivate_button.invoke()
                checks['deactivate_closes_engine'] = wait(lambda: session.state in {'off', 'error'}) and session.state == 'off'
                report['wave'] = wave_evidence(instances[0]['path'])
                checks['output_is_verified_file'] = instances[0].get('file_output_verified') is True
                checks['real_nonempty_pcm'] = report['wave']['frames'] > 100 and report['wave']['nonzero_samples']
                root.update()
                checks['no_automatic_reactivation'] = len(instances) == 1 and session.state == 'off'
                controls._poll()
                controls.activate_button.invoke()
                checks['explicit_restart_works'] = wait(lambda: len(instances) == 2 and session.state in {'on', 'error'}) and session.state == 'on'
                controls.close()
                checks['close_ends_owned_session'] = wait(lambda: session.state == 'closed') and all(data['closed'].is_set() for data in instances)
            checks['no_callback_errors'] = not errors
            checks['no_native_property_errors'] = not getattr(root, '_myl_a11y_errors', [])
        except Exception as exc:
            report['error'] = f'{type(exc).__name__}: {exc}'
        finally:
            if app is not None:
                thread = app.workspace.speech_controls.session._thread
                app.workspace.shutdown()
                if thread is not None:
                    thread.join(10)
                    if thread.is_alive():
                        report['error'] = 'Local voice worker did not terminate'
            for identifier in root.tk.call('after', 'info'):
                root.tk.call('after', 'cancel', identifier)
            root.destroy()
    report['passed'] = set(checks) == REQUIRED_CHECKS and all(checks.values()) and 'error' not in report
    return report


def run_and_record(output, *, version):
    report = run_checks(version)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return 0 if report['passed'] else 1

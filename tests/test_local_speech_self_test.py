"""Exercise diagnostic guards without creating an OS voice or playing audio."""
import ctypes as ct
import json
import tempfile
import unittest
import wave
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import main
from core.sapi_speech import WindowsVoice
from tools import local_speech_self_test as diagnostic


class LocalSpeechDiagnosticTests(unittest.TestCase):
    def test_cli_delegates_without_loading_a_personal_workspace(self):
        with patch.object(diagnostic, 'run_and_record', return_value=0) as check:
            self.assertEqual(main.cli(['--local-voice-self-test', 'synthetic.json']), 0)
        check.assert_called_once_with(Path('synthetic.json'), version=main._version())

    def test_cli_requires_an_output(self):
        for flag in ('--local-voice-self-test', '--accessibility-self-test', '--windows-provider-self-test'):
            with self.subTest(flag=flag), self.assertRaises(ValueError):
                main.cli([flag])

    def test_refuses_to_redirect_an_existing_app(self):
        with patch.object(diagnostic.sys, 'platform', 'win32'), patch.dict(
                diagnostic.sys.modules, {'library_app': Mock()}):
            report = diagnostic.run_checks('test')
        self.assertFalse(report['passed'])
        self.assertIn('fresh', report['error'])

    def test_unredirected_voice_cannot_speak(self):
        voice = object.__new__(diagnostic.CapturedVoice)
        voice._capture_ready = False
        with patch.object(WindowsVoice, 'speak') as speak:
            with self.assertRaisesRegex(RuntimeError, 'verified file'):
                voice.speak('Must not reach the OS')
        speak.assert_not_called()

    def test_failed_capture_setup_never_speaks_and_releases_even_if_stream_close_fails(self):
        def initialize(voice):
            voice._dispatch = ct.c_void_p(1)
            voice._ole = SimpleNamespace(CLSIDFromProgID=Mock(return_value=0), CoCreateInstance=Mock(return_value=0))
            voice._automation = SimpleNamespace(SysAllocString=Mock(return_value=1), SysFreeString=Mock())
        with patch.object(WindowsVoice, '__init__', initialize), patch.object(WindowsVoice, 'speak') as speak, \
                patch.object(diagnostic, '_invoke', side_effect=OSError('Capture setup failed')), \
                patch.object(diagnostic.CapturedVoice, '_close_stream', side_effect=OSError('Synthetic close error')), \
                patch.object(WindowsVoice, '_release') as release:
            with self.assertRaises(OSError):
                diagnostic.CapturedVoice(Path('synthetic.wav'), {})
        speak.assert_not_called()
        release.assert_called_once()

    def test_wave_evidence_checks_real_frames_not_just_header(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'synthetic.wav'
            with wave.open(str(path), 'wb') as stream:
                stream.setparams((1, 2, 22050, 0, 'NONE', 'not compressed'))
                stream.writeframes(b'\x01\x00' * 1000)
            evidence = diagnostic.wave_evidence(path)
        self.assertEqual(evidence['frames'], 1000)
        self.assertTrue(evidence['nonzero_samples'])
        self.assertEqual(evidence['rate'], 22050)
        self.assertEqual(len(evidence['sha256']), 64)

    def test_failure_is_recorded_not_claimed_passed(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(
                diagnostic, 'run_checks', return_value={'passed': False, 'checks': {}}):
            output = Path(directory) / 'result.json'
            self.assertEqual(diagnostic.run_and_record(output, version='test'), 1)
            self.assertFalse(json.loads(output.read_text())['passed'])

    def test_native_cli_records_the_actual_probe_result(self):
        for flag, target in (('--accessibility-self-test', 'tools.verify_accessibility.run'),
                             ('--windows-provider-self-test', 'tools.verify_windows_accessibility_provider.run_fixture')):
            with self.subTest(flag=flag), tempfile.TemporaryDirectory() as directory, patch(
                    target, return_value={'passed': False, 'checks': {'fixture': False}}):
                path = Path(directory) / 'report.json'
                self.assertEqual(main.cli([flag, str(path)]), 1)
                self.assertFalse(json.loads(path.read_text())['passed'])

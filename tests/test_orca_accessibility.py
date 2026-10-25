"""Offline controller/parser tests, explicitly not a real Orca execution."""
import json
import tempfile
import unittest
from pathlib import Path, PurePosixPath
from unittest.mock import Mock, patch

import main
from tools import external_accessibility_fixture as fixture
from tools import verify_orca_accessibility as orca


ISOLATED = {'GITHUB_ACTIONS': 'true', 'MYL_ISOLATED_A11Y_CI': '1', 'GSETTINGS_BACKEND': 'memory',
            'DISPLAY': ':99', 'DBUS_SESSION_BUS_ADDRESS': 'unix:path=/tmp/dbus-QA,guid=synthetic'}
STARTUP = ('ORCA: Speech is not enabled in settings\n'
           'ORCA: Braille is not enabled in settings\nORCA: User Settings Loaded\n')


class OrcaControllerTests(unittest.TestCase):
    def test_windows_is_not_run_without_any_subprocess_or_reader(self):
        with patch.object(orca.sys, 'platform', 'win32'), patch.object(orca.subprocess, 'run') as run, \
                patch.object(orca.subprocess, 'Popen') as popen:
            report = orca.run_checks(Path('not-an-executable'))
        self.assertFalse(report['passed'])
        self.assertEqual(report['status'], 'not_run')
        self.assertEqual(report['reason'], 'linux_only')
        run.assert_not_called()
        popen.assert_not_called()

    def check_environment(self, env, *, reader_pids=(), devices=False, check_reader=True):
        with patch.object(orca.sys, 'platform', 'linux'), \
                patch.object(orca.Path, 'exists', return_value=devices), \
                patch.object(orca, 'existing_readers', return_value=reader_pids):
            return orca.isolated_ci_problem(env, check_reader=check_reader)

    def test_missing_shared_or_persistent_desktop_conditions_fail_closed(self):
        self.assertIsNone(self.check_environment(ISOLATED))
        for key, value in (('GITHUB_ACTIONS', 'false'), ('MYL_ISOLATED_A11Y_CI', ''),
                           ('GSETTINGS_BACKEND', 'dconf'), ('DISPLAY', 'shared:0'),
                           ('DBUS_SESSION_BUS_ADDRESS', 'unix:path=/run/user/1000/bus'),
                           ('WAYLAND_DISPLAY', 'wayland-0')):
            with self.subTest(key=key):
                self.assertIsNotNone(self.check_environment(dict(ISOLATED, **{key: value})))
        self.assertEqual(self.check_environment(ISOLATED, devices=True), 'audio_devices_present_no_silent_run')
        self.assertEqual(self.check_environment(ISOLATED, reader_pids=[123]), 'existing_reader_will_not_be_replaced')
        self.assertIsNone(self.check_environment(ISOLATED, reader_pids=[123], check_reader=False))

    def test_reader_options_disable_outputs_and_never_replace_other_readers(self):
        command = orca.reader_command(PurePosixPath('/usr/bin/orca'), PurePosixPath('/tmp/qa/reader'), PurePosixPath('/dev/stderr'))
        self.assertIn('--disable=speech,braille,braille-monitor,sound,mouse-review', command)
        self.assertIn('--user-prefs=/tmp/qa/reader', command)
        self.assertIn('--debug-file=/dev/stderr', command)
        self.assertNotIn('--replace', command)
        self.assertNotIn('--setup', command)

    def test_sandbox_preserves_home_and_disables_audio_endpoints(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            environment = orca.silent_environment({'HOME': '/original-home', 'PYTHONPATH': '/untrusted',
                                                   'MANAGE_YOUR_LIBRARY_PROFILE': '/normal-profile'}, root)
            self.assertEqual(environment['HOME'], '/original-home')
            self.assertEqual(environment['GSETTINGS_BACKEND'], 'memory')
            self.assertNotIn('PYTHONPATH', environment)
            self.assertNotIn('MANAGE_YOUR_LIBRARY_PROFILE', environment)
            self.assertIn('no-pulse.sock', environment['PULSE_SERVER'])
            self.assertIn('no-speech.sock', environment['SPEECHD_ADDRESS'])
            self.assertIn('type null', Path(environment['ALSA_CONFIG_PATH']).read_text())
            for key in ('XDG_CONFIG_HOME', 'XDG_CACHE_HOME', 'XDG_DATA_HOME', 'XDG_RUNTIME_DIR'):
                self.assertTrue(Path(environment[key]).is_relative_to(root))
            orca.reader_preferences(root / 'reader')
            data = json.loads((root / 'reader/user-settings.conf').read_text())
            for settings in (data['general'], data['profiles']['default']):
                for key in ('enableSpeech', 'enableBraille', 'enableBrailleMonitor', 'enableSound', 'enableMouseReview'):
                    self.assertIs(settings[key], False)

    def test_output_initialization_or_incomplete_startup_cannot_pass_silence_check(self):
        self.assertTrue(orca.silent_startup(STARTUP))
        for marker in ('SPEECH: Initializing', 'SPEECH: Using speech server', 'ORCA: About to enable speech'):
            self.assertFalse(orca.silent_startup(STARTUP + marker))
        self.assertFalse(orca.silent_startup(STARTUP.replace('ORCA: User Settings Loaded', '')))

    def test_external_event_role_label_and_value_presentation_are_all_required(self):
        expected = {'label': 'MYL QA Search', 'role': 'entry', 'value': 'Synthetic title 42'}
        pieces = ['OBJECT EVENT: object:state-changed:focused (1, 0, )',
                  "SPEECH OUTPUT: 'MYL QA Search'", "SPEECH OUTPUT: 'text'",
                  "SPEECH OUTPUT: 'Synthetic title 42'"]
        self.assertTrue(orca.phase_evidence('\n'.join(pieces), expected)['passed'])
        for index in range(len(pieces)):
            with self.subTest(missing=index):
                self.assertFalse(orca.phase_evidence('\n'.join(pieces[:index] + pieces[index + 1:]), expected)['passed'])
        enumeration_only = "name='MYL QA Search' role='entry' value='Synthetic title 42'"
        self.assertFalse(orca.phase_evidence(enumeration_only, expected)['passed'])
        self.assertFalse(orca.phase_evidence('\n'.join(pieces), dict(expected, role='button'))['passed'])

    def test_report_and_log_limits_and_normalization_hide_profile_paths(self):
        text = r"C:\users\SyntheticOwner\profile /home/SyntheticOwner/config /Users/SyntheticOwner/log /tmp/myl_orca_fixture_abcd/value"
        normalized = orca.normalize_log(text, Path('/tmp/myl_orca_ci_qa'))
        self.assertNotIn('SyntheticOwner', normalized)
        self.assertNotIn('myl_orca_fixture_abcd', normalized)
        with tempfile.TemporaryDirectory() as directory, patch.object(orca, 'MAX_LOG_BYTES', 4):
            path = Path(directory) / 'log'
            path.write_text('too long', encoding='utf-8')
            with self.assertRaises(RuntimeError):
                orca.read_bounded(path)
            self.assertIn('omitted', orca.diagnostic_text(path))

    def test_only_the_owned_subprocess_is_stopped(self):
        process = Mock()
        process.poll.side_effect = [None, 0]
        self.assertTrue(orca.stop_owned(process))
        process.terminate.assert_called_once_with()
        process.wait.assert_called_once_with(timeout=3)
        process.kill.assert_not_called()

    def test_not_run_is_recorded_nonzero_and_previous_evidence_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'report.json'
            report = {'passed': False, 'status': 'not_run', 'reason': 'synthetic unavailable platform'}
            with patch.object(orca, 'run_checks', return_value=report) as run:
                self.assertEqual(orca.run_and_record(Path('synthetic'), output), 2)
                self.assertEqual(json.loads(output.read_text()), report)
                with self.assertRaises(FileExistsError):
                    orca.run_and_record(Path('synthetic'), output)
                self.assertEqual(run.call_count, 1)


class ExternalFixtureTests(unittest.TestCase):
    def test_protocol_is_bounded_sequential_and_cannot_execute_arbitrary_commands(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'command.json'
            self.assertIsNone(fixture.read_command(path, 0))
            fixture.atomic_json(path, {'sequence': 1, 'action': 'focus_search'})
            self.assertEqual(fixture.read_command(path, 0)['action'], 'focus_search')
            self.assertIsNone(fixture.read_command(path, 1))
            for command in ({'sequence': 2, 'action': 'run_shell'}, {'sequence': True, 'action': 'focus_search'},
                            {'sequence': 3, 'action': 'focus_search'}, {'sequence': 2, 'action': 'shutdown', 'path': 'extra'}):
                fixture.atomic_json(path, command)
                with self.assertRaises(ValueError):
                    fixture.read_command(path, 1)
            path.write_text('x' * (fixture.MAX_COMMAND_BYTES + 1))
            with self.assertRaises(ValueError):
                fixture.read_command(path, 1)

    def test_fresh_process_guard_precedes_app_imports_or_profile_use(self):
        with patch.object(orca, 'isolated_ci_problem', return_value=None), \
                patch.dict(fixture.sys.modules, {'library_app': object()}):
            with self.assertRaisesRegex(RuntimeError, 'fresh process'):
                fixture.run_fixture(Path('not-used'), version='0.5.3')

    def test_explicit_cli_is_separate_from_normal_startup_and_profile_selection(self):
        with patch('tools.external_accessibility_fixture.run_fixture', return_value=2) as run:
            self.assertEqual(main.cli(['--external-accessibility-fixture', 'qa-control']), 2)
            run.assert_called_once_with(Path('qa-control'), version=main._version())
            for arguments in (['--external-accessibility-fixture'],
                              ['--profile', 'normal', '--external-accessibility-fixture', 'qa']):
                with self.assertRaises(ValueError):
                    main.cli(arguments)

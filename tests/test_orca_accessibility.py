"""Offline controller/parser tests, explicitly not a real Orca execution."""
import json
import tempfile
import unittest
from pathlib import Path, PurePosixPath
from unittest.mock import Mock, patch

import main
from tools import external_accessibility_fixture as fixture
from tools import verify_orca_accessibility as orca
from tools import inspect_atspi_fixture as atspi


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
        self.assertFalse(orca.phase_evidence('\n'.join(pieces).replace('focused (1,', 'focused (0,'), expected)['passed'])

    def test_failed_debug_writes_are_incomplete_evidence_even_without_traceback(self):
        self.assertEqual(orca.reader_diagnostic_errors(STARTUP), [])
        for marker in ('Exception when trying to write text', 'TypeError when trying to write text',
                       'Traceback (most recent call last)', 'ERROR: Could not process object:focus'):
            self.assertTrue(orca.reader_diagnostic_errors(STARTUP + marker))

    def test_test_errors_are_distinguished_from_deliberate_termination_messages(self):
        marker = 'Exception when trying to write text'
        after_only = orca.trace_integrity(STARTUP, STARTUP + marker)
        self.assertTrue(after_only['reader_no_exceptions'])
        self.assertEqual(after_only['during_test_errors'], [])
        self.assertEqual(after_only['termination_messages'], [marker])
        before = STARTUP + marker
        during = orca.trace_integrity(before, before + '\nowned process terminated')
        self.assertFalse(during['reader_no_exceptions'])
        self.assertEqual(during['during_test_errors'], [marker])
        self.assertEqual(during['termination_messages'], [])

    def test_capture_errors_overflow_or_changed_trace_always_invalidate_evidence(self):
        for options in ({'capture_error': 'reader_trace_write_failed'}, {'overflow': True}):
            result = orca.trace_integrity(STARTUP, STARTUP, **options)
            self.assertFalse(result['reader_no_exceptions'])
            self.assertFalse(result['capture_complete'])
        result = orca.trace_integrity(STARTUP, 'different trace')
        self.assertFalse(result['prefix_preserved'])
        self.assertFalse(result['reader_no_exceptions'])

    def test_split_utf8_does_not_look_like_modified_raw_capture(self):
        raw = (STARTUP + 'Synthetic ▼ control').encode('utf-8')
        offset = raw.index('▼'.encode('utf-8')) + 1
        result = orca.trace_integrity(raw[:offset], raw)
        self.assertTrue(result['prefix_preserved'])
        self.assertTrue(result['capture_complete'])

    def test_focus_context_keeps_object_details_and_active_script_decisions(self):
        text = ('noise\nOBJECT EVENT: object:state-changed:focused (1, 0, 0)\n'
                "name='Synthetic search' role='entry'\nstates='focused active showing'\n"
                'EVENT MANAGER: Change active script: True\nSPEECH OUTPUT: Synthetic search\n')
        result = orca.focus_trace_context(text)
        for wanted in ("role='entry'", "states='focused active showing'", 'Change active script: True', 'SPEECH OUTPUT:'):
            self.assertIn(wanted, result)
        self.assertLessEqual(len(orca.focus_trace_context(text * 1000)), 22000)

    def test_api_snapshot_is_owned_pid_read_only_bounded_and_not_pass_evidence(self):
        evidence = {'scope': 'atspi_api_diagnostic_not_reader_certification', 'status': 'complete', 'applications': []}
        with patch.object(orca.subprocess, 'run', return_value=Mock(stdout=json.dumps(evidence))) as run:
            self.assertEqual(orca.api_snapshot(123, ISOLATED), evidence)
        args, kwargs = run.call_args
        self.assertEqual(args[0][-2:], ['--pid', '123'])
        self.assertIn('--windows-only', args[0])
        self.assertEqual(kwargs['timeout'], 4)
        self.assertEqual(kwargs['env'], ISOLATED)
        with patch.object(orca.subprocess, 'run', side_effect=orca.subprocess.TimeoutExpired('synthetic', 4)):
            self.assertEqual(orca.api_snapshot(123, ISOLATED)['error'], 'TimeoutExpired')
        self.assertNotIn('passed', evidence)

    def test_timeout_retains_last_complete_partial_api_snapshot(self):
        partial = {'scope': 'atspi_api_diagnostic_not_reader_certification', 'status': 'in_progress',
                   'applications': [{'windows': [{'role': 'window', 'states': ['active', 'showing']}]}]}
        output = (json.dumps(partial) + '\n{"unfinished":').encode()
        error = orca.subprocess.TimeoutExpired('synthetic', 4, output=output)
        with patch.object(orca.subprocess, 'run', side_effect=error):
            result = orca.api_snapshot(123, ISOLATED)
        self.assertEqual(result['applications'], partial['applications'])
        self.assertEqual(result['controller_status'], 'timed_out_partial_diagnostic')
        self.assertNotIn('passed', result)
        self.assertIsNone(orca.api_progress('x' * 64001))
        self.assertIsNone(orca.api_progress('{"passed":true}'))
        self.assertIsNone(orca.api_progress(json.dumps({'scope': partial['scope'], 'status': {}})))

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
    def test_focus_acknowledgment_requires_the_requested_mapped_widget(self):
        root, target, other = Mock(), Mock(), Mock()
        root.focus_get.return_value = other
        self.assertFalse(fixture.focus_state(root, target)['focus_matches_target'])
        root.focus_get.return_value = target
        target.winfo_viewable.return_value = False
        self.assertFalse(fixture.focus_state(root, target)['focus_matches_target'])
        target.winfo_viewable.return_value = True
        result = fixture.focus_state(root, target)
        self.assertTrue(result['focus_matches_target'])
        self.assertEqual(result['focus_widget'], result['requested_focus'])
        root.focus_get.return_value = None
        self.assertIsNone(fixture.focus_state(root, target)['focused_toplevel'])

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


class AtspiDiagnosticTests(unittest.TestCase):
    class Node:
        def __init__(self, name='', role='panel', children=(), states=(), pid=123, index=0):
            self.name, self.role, self.children, self.states = name, role, list(children), states
            self.pid, self.index = pid, index

        @property
        def childCount(self):
            return len(self.children)

        def __getitem__(self, index): return self.children[index]
        def __iter__(self): return iter(self.children)
        def get_process_id(self): return self.pid
        def getState(self): return Mock(getStates=lambda: self.states)
        def getRoleName(self): return self.role
        def getIndexInParent(self): return self.index

    def test_diagnostic_only_reads_owned_app_and_retains_actual_active_and_focus_states(self):
        focused = self.Node('Synthetic search', 'entry', states=('focused', 'showing'), index=2)
        window = self.Node('Synthetic window', 'frame', [focused], ('active', 'showing'))
        app = self.Node('Synthetic app', 'application', [window])
        foreign = Mock(get_process_id=lambda: 999)
        result = atspi.inspect_fixture(123, [foreign, app], str)
        self.assertEqual(result['applications'][0]['windows'][0]['states'], ['active', 'showing'])
        self.assertEqual(result['applications'][0]['focused'][0]['index_in_parent'], 2)
        foreign.getState.assert_not_called()
        self.assertNotIn('passed', result)

    def test_api_diagnostic_traversal_is_bounded_and_rejects_non_owned_pid(self):
        root = self.Node('application', children=[self.Node(children=[self.Node() for _ in range(10)]) for _ in range(10)])
        result = atspi.inspect_fixture(123, [root], str, maximum=3)
        self.assertTrue(result['truncated'])
        self.assertLessEqual(result['visited'], 3)
        for pid in (True, 0, -1, '123'):
            with self.assertRaises(ValueError):
                atspi.inspect_fixture(pid, [], str)

    def test_window_only_progress_retains_active_window_without_deep_focus_queries(self):
        hidden_descendant = Mock()
        window = self.Node('Synthetic window', 'window', [hidden_descendant], ('active', 'showing'))
        app = self.Node('application', children=[window])
        updates = []
        result = atspi.inspect_fixture(123, [app], str, maximum=8, depth_limit=0,
                                       progress=lambda report: updates.append(json.loads(json.dumps(report))))
        self.assertEqual(result['visited'], 1)
        self.assertFalse(result['descendant_traversal_enabled'])
        self.assertTrue(result['truncated'])
        self.assertEqual(result['applications'][0]['windows'][0]['states'], ['active', 'showing'])
        self.assertEqual(updates[0]['status'], 'in_progress')
        self.assertEqual(updates[-1]['status'], 'complete')
        self.assertTrue(any(update['applications'] and update['applications'][0]['windows'] for update in updates[:-1]))
        hidden_descendant.getState.assert_not_called()

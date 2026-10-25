"""Offline parsers and guards only; synthetic ELF bytes are never executed."""
import hashlib
import json
import os
import struct
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from tools import verify_linux_library_replacement as verifier


def elf_bytes(flags=0, marker=None):
    names = b'\x00.shstrtab\x00' + verifier.SECTION.encode() + b'\x00'
    marker = verifier.MARKER if marker is None else marker
    table = 64
    names_offset = table + 3 * 64
    marker_offset = names_offset + len(names)
    header = struct.pack('<16sHHIQQQIHHHHHH', b'\x7fELF\x02\x01' + b'\x00' * 10,
                         3, 62, 1, 0, 0, table, 0, 64, 56, 0, 64, 3, 1)
    sections = bytes(64)
    sections += struct.pack('<IIQQQQIIQQ', 1, 3, 0, 0, names_offset, len(names), 0, 0, 1, 0)
    sections += struct.pack('<IIQQQQIIQQ', 11, 1, flags, 0, marker_offset, len(marker), 0, 0, 1, 0)
    return header + sections + names + marker


class LinuxLibraryReplacementTests(unittest.TestCase):
    def test_elf_marker_is_exact_nonallocated_and_nonexecutable(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'synthetic-not-executable.so'
            path.write_bytes(elf_bytes())
            self.assertFalse(verifier.verify_marker_section(path)['allocated'])
            for data in (elf_bytes(flags=2), elf_bytes(flags=4), elf_bytes(marker=b'wrong'),
                         elf_bytes()[:60], elf_bytes().replace(b'\x7fELF', b'NOPE', 1)):
                with self.subTest(data=data[:16]), self.assertRaises(ValueError):
                    path.write_bytes(data)
                    verifier.verify_marker_section(path)

    def test_soname_and_symbols_are_required_and_compared_as_metadata(self):
        dynamic = ' 0x000000000000000e (SONAME) Library soname: [libglib-2.0.so.0]\n'
        symbols = 'Num: Value Size Type Bind Vis Ndx Name\n 1: 000000 10 FUNC GLOBAL DEFAULT 2 g_test@@GLIB_2_0\n'
        identity = verifier.elf_identity(dynamic, symbols)
        self.assertEqual(identity['soname'], verifier.LIBRARY)
        for changed_dynamic, changed_symbols in (('', symbols), (dynamic * 2, symbols), (dynamic, ''),
                                                  (dynamic, '1: malformed')):
            with self.assertRaises(ValueError):
                verifier.elf_identity(changed_dynamic, changed_symbols)

    def test_maps_require_owned_copy_path_device_and_inode(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'lib.so'
            path.write_bytes(b'never executed')
            line = '1000-2000 r-xp 00000000 08:01 12345 ' + str(path) + '\n'
            self.assertTrue(verifier.mapped_copy(line, path, inode=12345, device=(8, 1)))
            for changed in (line.replace('12345', '54321'), line.replace('08:01', '08:02'),
                            line.replace('lib.so', 'other.so'), line.replace('r-xp', 'r--p'),
                            line.rstrip() + ' (deleted)\n'):
                self.assertFalse(verifier.mapped_copy(changed, path, inode=12345, device=(8, 1)))

    def test_original_inventory_detects_changes_without_executing_files(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'inert'
            path.write_bytes(b'original')
            before = verifier.payload_inventory(Path(directory))
            path.write_bytes(b'changed')
            self.assertNotEqual(before, verifier.payload_inventory(Path(directory)))

    def test_diagnostics_require_actual_frozen_version_and_all_checks(self):
        report = {'passed': True, 'frozen': True, 'version': 'test', 'checks': {'one': 'passed'}}
        self.assertTrue(verifier.validate_diagnostic(report, {'one'}, 'test'))
        for changed in ({**report, 'frozen': False}, {**report, 'version': 'other'},
                        {**report, 'checks': {}}, {**report, 'checks': {'one': 'failed'}}):
            self.assertFalse(verifier.validate_diagnostic(changed, {'one'}, 'test'))

    def test_api_uses_real_booleans_not_runtime_status_strings_or_truthiness(self):
        report = {'passed': True, 'frozen': True, 'version': 'test', 'checks': {'one': True},
                  'backend': 'tk_native', 'windowing_system': 'x11', 'errors': []}
        self.assertTrue(verifier.validate_diagnostic(report, {'one'}, 'test', boolean_checks=True))
        for value in (1, 'passed', 'true', False, None):
            with self.subTest(value=value):
                changed = {**report, 'checks': {'one': value}}
                self.assertFalse(verifier.validate_diagnostic(changed, {'one'}, 'test', boolean_checks=True))
        self.assertFalse(verifier.validate_diagnostic(report, {'one'}, 'test'))
        for changed in ({**report, 'backend': 'other'}, {**report, 'windowing_system': 'win32'},
                        {**report, 'errors': ['callback failed']}):
            self.assertFalse(verifier.validate_diagnostic(changed, {'one'}, 'test', boolean_checks=True))

    def test_windows_guard_precedes_any_input_read_copy_or_subprocess(self):
        with patch.object(verifier.sys, 'platform', 'win32'), patch.object(verifier.shutil, 'copytree') as copying, \
                patch.object(verifier.subprocess, 'Popen') as process, patch.object(verifier, '_validate') as validation:
            report = verifier.run_checks(Path('absent'), Path('absent'))
        self.assertEqual(report['status'], 'not_run')
        self.assertFalse(report['passed'])
        copying.assert_not_called()
        process.assert_not_called()
        validation.assert_not_called()

    def test_missing_ci_guards_do_not_count_as_success(self):
        with patch.object(verifier, 'isolated_ci_problem', return_value='requires_dedicated_isolated_ci'):
            report = verifier.run_checks(Path('absent'), Path('absent'))
        self.assertEqual(report['status'], 'not_run')
        self.assertFalse(report['reader_started'])
        self.assertIsNone(report['family_exercised'])
        self.assertEqual(report['target_family'], 'glib2.0')
        self.assertIn('other_library_families', report['not_established'])

    def test_state_reader_bounds_and_output_cannot_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'state.json'
            path.write_text(json.dumps({'sequence': 1}), encoding='utf-8')
            self.assertEqual(verifier.read_json(path)['sequence'], 1)
            with patch.object(verifier, 'MAX_JSON', 2), self.assertRaises(ValueError):
                verifier.read_json(path)
            with self.assertRaises(FileExistsError):
                verifier.run_and_record(Path('absent'), Path('absent'), path)

    def _orchestration(self, *, wrong_inode=False):
        # Every subprocess is mocked; neither the stand-in launcher nor ELF is
        # executed. The real filesystem copy/hash/marker/maps logic is exercised.
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as patches:
            directory = Path(temporary)
            payload, evidence = directory / 'original', directory / 'evidence'
            internal = payload / '_internal'
            internal.mkdir(parents=True)
            evidence.mkdir()
            original = internal / verifier.LIBRARY
            original.write_bytes(b'original inert stand-in')
            (internal / 'VERSION').write_text('test-version', encoding='utf-8')
            (payload / 'ManageYourLibrary').write_bytes(b'not executable')
            before = verifier.payload_inventory(payload)
            origin = {'destination': verifier.LIBRARY, 'source_package': 'glib2.0', 'source_version': '2.72.4-test',
                      'binary_package': 'libglib2.0-0:amd64', 'binary_version': '2.72.4-test',
                      'original_sha256': hashlib.sha256(original.read_bytes()).hexdigest()}
            real_path = Path
            proc = directory / 'proc'
            processes, fixture_state = [], {}

            def path_factory(value):
                return proc if str(value) == '/proc' else real_path(value)

            class FakeProcess:
                def __init__(self, command, **kwargs):
                    self.pid = 400 + len(processes)
                    self.returncode = 0
                    processes.append(self)
                    name = Path(command[0]).name
                    if name == 'readelf':
                        if '--dynamic' in command:
                            kwargs['stdout'].write('(SONAME) Library soname: [' + verifier.LIBRARY + ']\n')
                        else:
                            kwargs['stdout'].write('1: 00000000 8 FUNC GLOBAL DEFAULT 1 synthetic_symbol\n')
                        kwargs['stdout'].flush()
                    elif name == 'objcopy':
                        target = Path(command[-1])
                        if target.is_relative_to(payload):
                            raise AssertionError('Attempt to mutate original')
                        target.write_bytes(elf_bytes())
                    elif name == 'openbox':
                        self.returncode = None
                    elif len(command) > 1 and command[1] == '--external-accessibility-fixture':
                        self.returncode = None
                        control = Path(command[2])
                        fixture_state.update(pid=self.pid, frozen=True, version='test-version', action='ready',
                                             sequence=0, voice_off=True, no_network=True, errors=[])
                        verifier.atomic_json(control / 'state.json', dict(fixture_state))
                        library = Path(command[0]).parent / '_internal' / verifier.LIBRARY
                        maps = proc / str(self.pid) / 'maps'
                        maps.parent.mkdir(parents=True)
                        inode = library.stat().st_ino + int(wrong_inode)
                        maps.write_text('1000-2000 r-xp 0 00:00 ' + str(inode) + ' ' + str(library) + '\n')
                    elif len(command) > 1 and command[1].endswith('-self-test'):
                        flag = command[1][2:-10]
                        required = {'runtime': verifier.RUNTIME_CHECKS, 'first-use': verifier.FIRST_CHECKS,
                                    'accessibility': verifier.BASE_CHECKS}[flag]
                        diagnostic = {'passed': True, 'frozen': True, 'version': 'test-version',
                                      'checks': dict.fromkeys(required, True if flag == 'accessibility' else 'passed')}
                        if flag == 'accessibility':
                            diagnostic.update(backend='tk_native', windowing_system='x11', errors=[])
                        Path(command[2]).write_text(json.dumps(diagnostic))
                    else:
                        raise AssertionError('Unexpected executable in replacement test: ' + name)

                def poll(self):
                    return self.returncode

                def wait(self, timeout=None):
                    self.returncode = 0
                    return 0

                def terminate(self):
                    self.returncode = 0

                def kill(self):
                    self.returncode = 0

            real_atomic = verifier.atomic_json

            def command_json(path, value):
                real_atomic(path, value)
                if path.name == 'command.json':
                    fixture_state.update(value)
                    fixture_state['focus_matches_target'] = True
                    real_atomic(path.parent / 'state.json', dict(fixture_state))

            patches.enter_context(patch.object(verifier, 'isolated_ci_problem', return_value=None))
            patches.enter_context(patch.object(verifier.shutil, 'which', side_effect=lambda value: '/tools/' + value))
            patches.enter_context(patch.object(verifier, '_validate', return_value=({'copied_binary_origins': [origin]}, {}, {})))
            patches.enter_context(patch.object(verifier, 'atomic_json', side_effect=command_json))
            patches.enter_context(patch.object(verifier.subprocess, 'Popen', side_effect=FakeProcess))
            patches.enter_context(patch.object(os, 'major', return_value=0, create=True))
            patches.enter_context(patch.object(os, 'minor', return_value=0, create=True))
            # Only the manager preflight file test needs an installed tool;
            # provide an ordinary inert file instead, not an executable.
            manager = directory / 'openbox'
            manager.write_bytes(b'not executable')
            def patched_path(value):
                return manager if str(value) == '/usr/bin/openbox' else path_factory(value)
            patches.enter_context(patch.object(verifier, 'Path', side_effect=patched_path))
            report = verifier.run_checks(payload, evidence)
            self.assertEqual(report['passed'], not wrong_inode, report)
            self.assertEqual(report['family_exercised'], None if wrong_inode else 'glib2.0')
            self.assertEqual(report['checks']['modified_library_mapped_from_copy'], not wrong_inode)
            self.assertEqual(verifier.payload_inventory(payload), before)
            self.assertTrue(report['checks']['original_payload_unchanged'])
            self.assertTrue(all(process.poll() is not None for process in processes))

    def test_orchestration_uses_only_copy_with_mocked_tools_and_owned_pid(self):
        self._orchestration()

    def test_failed_loaded_inode_still_stops_owned_processes_and_preserves_original(self):
        self._orchestration(wrong_inode=True)

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.windows_dependency_policy import RECEIPT, normalized_destination, select_inputs, verify_payload


class WindowsDependencyPolicyTests(unittest.TestCase):
    def test_os_forwarders_are_not_selected_even_from_an_ambient_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'python.dll').write_bytes(b'controlled')
            binaries, data, report = select_inputs([
                ('python.dll', str(root / 'python.dll'), 'BINARY'),
                ('ucrtbase.dll', 'uncontrolled/location', 'BINARY'),
                ('API-MS-WIN-CRT-RUNTIME-L1-1-0.DLL', 'uncontrolled/location', 'BINARY'),
            ], [], roots={'python': root})
            self.assertEqual(len(binaries), 1)
            self.assertEqual(data, [])
            self.assertEqual(len(report['excluded_os_components']), 2)
            self.assertEqual(report['files'][0]['origin'], {'root': 'python', 'relative': 'python.dll'})
            self.assertNotIn(str(root), json.dumps(report))

    def test_uncontrolled_or_hidden_native_data_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            approved = root / 'approved'
            approved.mkdir()
            foreign = root / 'foreign.dll'
            foreign.write_bytes(b'ambient')
            for binary, data in (([('foreign.dll', foreign, 'BINARY')], []),
                                 ([], [('foreign.dll', foreign, 'DATA')])):
                with self.assertRaisesRegex(ValueError, 'outside controlled'):
                    select_inputs(binary, data, roots={'python': approved})

    def fixture(self, root):
        # Microsoft family semantic/version checks are exercised separately;
        # these tests isolate complete TOC coverage and source/file integrity.
        microsoft = patch('tools.windows_vc_runtime.verify_payload', return_value={'passed': True})
        microsoft.start()
        self.addCleanup(microsoft.stop)
        source = root / 'source'
        source.mkdir()
        (source / 'sample.dll').write_bytes(b'controlled')
        _, _, report = select_inputs([('sample.dll', source / 'sample.dll', 'BINARY')], [], roots={'python': source})
        payload = root / 'payload'
        (payload / RECEIPT).parent.mkdir(parents=True)
        (payload / RECEIPT).write_text(json.dumps(report))
        (payload / '_internal/sample.dll').write_bytes(b'controlled')
        (payload / 'ManageYourLibrary.exe').write_bytes(b'separate executable')
        return payload

    def test_payload_must_match_all_controlled_inputs_without_os_copies(self):
        with tempfile.TemporaryDirectory() as directory:
            payload = self.fixture(Path(directory))
            self.assertTrue(verify_payload(payload)['passed'])
            path = payload / '_internal/ucrtbase.dll'
            path.write_bytes(b'ambient')
            with self.assertRaisesRegex(ValueError, 'must not be bundled'):
                verify_payload(payload)

    def test_modified_or_added_native_file_is_not_approved_by_a_receipt(self):
        for name in ('sample.dll', 'additional.pyd'):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                payload = self.fixture(Path(directory))
                (payload / '_internal' / name).write_bytes(b'different')
                with self.assertRaisesRegex(ValueError, 'inventory differ'):
                    verify_payload(payload)

    def test_direct_build_cli_can_import_its_runtime_verifier(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = self.fixture(root)
            script = Path(__file__).resolve().parents[1] / 'tools/windows_dependency_policy.py'
            result = subprocess.run([sys.executable, '-B', str(script), str(payload)], cwd=root,
                                    text=True, capture_output=True, timeout=15)
            # Deliberately incomplete synthetic Microsoft metadata must be
            # rejected, but only AFTER the command imports its verifier.
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn('ModuleNotFoundError', result.stderr)
            self.assertIn('Microsoft REDIST build receipt', result.stderr)

    def test_duplicate_or_traversal_destinations_are_rejected(self):
        for path in ('../outside.dll', '/absolute.dll', 'C:/absolute.dll'):
            with self.assertRaises(ValueError):
                normalized_destination(path)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'source.dll'
            source.write_bytes(b'controlled')
            with self.assertRaisesRegex(ValueError, 'Repeated'):
                select_inputs([('sample.dll', source, 'BINARY'), ('SAMPLE.DLL', source, 'BINARY')], [], roots={'python': root})

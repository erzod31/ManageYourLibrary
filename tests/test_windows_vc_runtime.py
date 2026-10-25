"""Conservative Microsoft REDIST selection without invoking compilers or UI."""
import json
import copy
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tools import windows_vc_runtime as runtime


class AuthenticodeTransportTests(unittest.TestCase):
    def test_uses_os_shell_builtin_modules_and_environment_path_not_interpolation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shell = root / 'System32/WindowsPowerShell/v1.0/powershell.exe'
            shell.parent.mkdir(parents=True)
            shell.write_bytes(b'synthetic shell; never executed')
            target = Path("quoted' runtime.dll")
            result = SimpleNamespace(stdout='{"status":"Valid","subject":"O=Microsoft Corporation"}')
            with patch.dict(runtime.os.environ, {'SystemRoot': str(root), 'PSModulePath': 'foreign modules'}), \
                    patch.object(runtime.subprocess, 'run', return_value=result) as run:
                self.assertEqual(runtime._authenticode(target)['status'], 'Valid')
            args, kwargs = run.call_args
            self.assertEqual(args[0][0], str(shell))
            self.assertIn('-NoProfile', args[0])
            self.assertNotIn(str(target), args[0][-1])
            self.assertEqual(kwargs['env']['MYL_VC_SIGNATURE_FILE'], str(target))
            self.assertEqual(kwargs['env']['PSModulePath'], str(shell.parent / 'Modules'))


class WindowsVcRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        vc = self.root / 'VC'
        self.toolset = vc / 'Tools/MSVC/14.44.35207'
        self.toolset.mkdir(parents=True)
        self.redist = vc / 'Redist/MSVC/14.44.35112'
        self.crt = self.redist / 'x64/Microsoft.VC143.CRT'
        self.crt.mkdir(parents=True)
        for name in runtime.NAMES:
            (self.crt / name).write_bytes(b'synthetic Microsoft binary ' + name.encode())
        self.env = {'VCINSTALLDIR': str(vc), 'VCTOOLSINSTALLDIR': str(self.toolset),
                    'VCTOOLSREDISTDIR': str(self.redist), 'VCTOOLSVERSION': '14.44.35207',
                    'VSCMD_ARG_TGT_ARCH': 'x64'}
        self.info = {'version': '14.44.35211.0', 'machine': runtime.AMD64,
                     'company': 'Microsoft Corporation', 'linker_version': [14, 44],
                     'imports': ['kernel32.dll', 'vcruntime140.dll']}
        self.signature = {'status': 'Valid', 'subject': 'CN=Microsoft Windows, O=Microsoft Corporation, C=US',
                          'thumbprint': 'synthetic public certificate identifier'}
        for patcher in (patch.object(runtime, '_build_environment', return_value=self.env),
                        patch.object(runtime, '_metadata', side_effect=lambda path: dict(self.info)),
                        patch.object(runtime, '_authenticode', side_effect=lambda path: dict(self.signature))):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_selects_signed_redist_by_file_version_not_older_folder_name(self):
        selection = runtime.select_redist()
        self.assertEqual(selection['roots']['crt'], self.crt)
        self.assertEqual(set(selection['files']), set(runtime.NAMES))
        receipt = selection['receipt']
        self.assertEqual(receipt['compiler_toolset_version'], '14.44.35207')
        self.assertFalse(receipt['global_release_approval'])
        self.assertEqual(receipt['license_eligibility'], 'not_determined')
        self.assertNotIn(str(self.root), json.dumps(receipt))
        for value in receipt['files'].values():
            self.assertEqual(value['version'], '14.44.35211.0')
            self.assertRegex(value['sha256'], r'^[0-9a-f]{64}$')
            self.assertTrue(value['source_relative_to_vc'].startswith('Redist/MSVC/'))

    def test_older_runtime_cannot_be_selected(self):
        self.info['version'] = '14.42.34438.0'
        with self.assertRaisesRegex(ValueError, 'No signed-source x64 REDIST'):
            runtime.select_redist()

    def test_missing_or_outside_redist_never_falls_back_to_path_or_windows(self):
        for value in (str(self.root / 'missing'), str(self.root)):
            self.env['VCTOOLSREDISTDIR'] = value
            with self.assertRaisesRegex(ValueError, 'REDIST directory'):
                runtime.select_redist()

    def test_compiler_and_architecture_metadata_are_required(self):
        self.env['VCTOOLSVERSION'] = 'unknown'
        with self.assertRaisesRegex(ValueError, 'invalid'):
            runtime.select_redist()
        self.env['VCTOOLSVERSION'] = '14.44.35207'
        self.env['VSCMD_ARG_TGT_ARCH'] = 'x86'
        with self.assertRaisesRegex(ValueError, 'v14 x64'):
            runtime.select_redist()

    def test_invalid_or_non_microsoft_signature_is_rejected(self):
        for status, subject in (('NotSigned', 'O=Microsoft Corporation'), ('Valid', 'O=Example Corporation')):
            self.signature.update(status=status, subject=subject)
            with self.assertRaisesRegex(ValueError, 'Authenticode signature'):
                runtime.select_redist()

    def test_wrong_native_architecture_or_company_is_rejected(self):
        self.info['machine'] = 0x14c
        with self.assertRaisesRegex(ValueError, 'architecture or publisher'):
            runtime.select_redist()
        self.info['machine'] = runtime.AMD64
        self.info['company'] = 'Unknown'
        with self.assertRaisesRegex(ValueError, 'architecture or publisher'):
            runtime.select_redist()

    def test_newer_native_linker_is_rejected_even_with_old_environment(self):
        selected = runtime.select_redist()
        self.info['linker_version'] = [14, 51]
        with self.assertRaisesRegex(ValueError, 'below a native binary'):
            runtime.validate_binary_toolsets(selected, [Path('bridge.pyd')])

    def test_other_crt_family_requires_an_explicit_review(self):
        selected = runtime.select_redist()
        self.info['imports'] = ['msvcp140.dll']
        with self.assertRaisesRegex(ValueError, 'Additional Microsoft runtime'):
            runtime.validate_binary_toolsets(selected, [Path('bridge.pyd')])

    def test_current_gui_linker_and_known_imports_pass(self):
        selected = runtime.select_redist()
        report = runtime.validate_binary_toolsets(selected, [Path('bridge.pyd')])
        self.assertTrue(report['bridge.pyd']['selected_v14_runtime_not_older_than_linker'])
        self.assertEqual(report['bridge.pyd']['runtime_imports'], ['vcruntime140.dll'])

    def payload(self):
        selection = runtime.select_redist()
        folder = self.root / 'payload'
        internal = folder / '_internal'
        (internal / 'licenses').mkdir(parents=True)
        rows = []
        for name, source in selection['files'].items():
            (internal / name).write_bytes(source.read_bytes())
            rows.append({'path': '_internal/' + name,
                         'sha256': selection['receipt']['files'][name]['sha256'],
                         'origin': {'root': 'microsoft_redist', 'relative': name}})
        report = {'schema': 1, 'platform': 'windows-x64', 'files': rows, 'msvc_redist': selection['receipt']}
        path = internal / 'licenses/windows-dependency-provenance.json'
        path.write_text(json.dumps(report))
        return folder, path, report

    def test_payload_checks_bytes_version_and_origin_without_rerunning_authenticode(self):
        folder, _path, _report = self.payload()
        with patch.object(runtime, '_authenticode', side_effect=AssertionError('must not run at packaging')):
            report = runtime.verify_payload(folder)
        self.assertTrue(report['passed'])
        self.assertEqual(set(report['files']), set(runtime.NAMES))
        self.assertIn('signature not rerun', report['scope'])

    def test_payload_rejects_missing_or_tampered_runtime(self):
        folder, _path, _report = self.payload()
        target = folder / '_internal/vcruntime140.dll'
        target.write_bytes(b'tampered')
        with self.assertRaisesRegex(ValueError, 'payload size differs'):
            runtime.verify_payload(folder)
        target.unlink()
        with self.assertRaisesRegex(ValueError, 'Missing or repeated'):
            runtime.verify_payload(folder)

    def test_payload_rejects_old_forged_signature_or_wrong_origin_receipts(self):
        folder, path, original = self.payload()
        for mutation in ('version', 'signature', 'origin', 'hash'):
            report = copy.deepcopy(original)
            if mutation == 'version':
                report['msvc_redist']['files']['vcruntime140.dll']['version'] = '14.42.34438.0'
            elif mutation == 'signature':
                report['msvc_redist']['files']['vcruntime140.dll']['authenticode']['status'] = 'NotSigned'
            elif mutation == 'origin':
                report['files'][0]['origin']['root'] = 'python'
            else:
                report['msvc_redist']['files']['vcruntime140.dll']['sha256'] = 'a' * 64
            path.write_text(json.dumps(report))
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                runtime.verify_payload(folder)

    def test_payload_requires_actual_pe_version_and_architecture(self):
        folder, _path, _report = self.payload()
        for version, machine in (('14.42.34438.0', runtime.AMD64), ('14.44.35211.0', 0x14c)):
            self.info.update(version=version, machine=machine)
            with self.subTest(version=version, machine=machine), self.assertRaisesRegex(ValueError, 'bytes/version differ'):
                runtime.verify_payload(folder)

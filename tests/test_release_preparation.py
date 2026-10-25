import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import main
from tools import first_use_self_test, runtime_self_test, write_build_manifest
from tools import package_windows_release as packaging
from tools import verify_tkinter_threading as bridge_contract


class ReleasePreparationTests(unittest.TestCase):
    def setUp(self):
        # Family byte/origin checks have their own real/synthetic tests. Keep
        # these packager fixtures independent of host-specific upstream DLLs.
        self.native_origins = {'passed': True, 'receipt_sha256': 'TEST-NATIVE'}
        self.wheel_notices = {'passed': True, 'catalog_sha256': 'TEST-WHEELS'}
        self.python_notices = {'passed': True, 'receipt_sha256': 'TEST-PYTHON'}
        for name, value in (('verify_native_origins', self.native_origins),
                            ('verify_wheel_notices', self.wheel_notices),
                            ('verify_python_notices', self.python_notices)):
            check = patch.object(packaging, name, return_value=value)
            check.start()
            self.addCleanup(check.stop)

    def payload(self, folder):
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "ManageYourLibrary.exe").write_bytes(b"synthetic executable")
        manifest = {
            "version": "0.5.3", "git_commit": "test-commit", "source_tree": {"sha256": "TEST", "files": 1},
            "sha256": write_build_manifest.sha256(folder / "ManageYourLibrary.exe"),
            "ocr_source_payload": {"sha256": "TEST-OCR"},
            'windows_native_origins': self.native_origins,
            'windows_wheel_notices': self.wheel_notices,
            'windows_python_notices': self.python_notices,
            "validation": {key: "passed" for key in (
                "automated_tests", "source_smoke", "catalog_performance_gate", "frozen_smoke", "runtime_self_test", "first_use_self_test", "redistribution_review", "ocr_libraries_profile", 'windows_accessibility_self_tests', 'tkinter_threading_self_test')},
        }
        runtime = {"version": "0.5.3", "passed": True, "frozen": True,
                   "checks": {key: "passed" for key in ("tk_init", "bundled_languages", "image_ocr", "pdfium_ocr", "reader_isolation")}}
        repairs = folder / '_internal/licenses/tcltk/myl-tkinter-tcl9-repair'
        repairs.mkdir(parents=True)
        script = repairs / 'verify_tkinter_threading.py'
        script.write_bytes(Path(bridge_contract.__file__).read_bytes())
        extension = folder / '_internal/_tkinter.pyd'
        extension.write_bytes(b'synthetic tkinter extension')
        source_contract = {'passed': True, 'checks': dict.fromkeys(bridge_contract.REQUIRED_CHECKS, True),
                           'python_version': '3.12.10', 'tcl_version': '9.1.0', 'tk_version': '9.1.0',
                           'platform': 'win32', 'busywait_interval_ms': 20, 'errors': [],
                           'reader_started': False, 'audible_output': 'not_used',
                           'bridge_sha256': write_build_manifest.sha256(extension).lower(),
                           'contract_sha256': write_build_manifest.sha256(script).lower()}
        (repairs / 'threading-contract.json').write_text(json.dumps(source_contract), encoding='utf-8')
        frozen_contract = {**source_contract, 'version': '0.5.3', 'frozen': True,
                           'executable_sha256': manifest['sha256'].lower()}
        (folder / 'tkinter-threading-self-test.json').write_text(json.dumps(frozen_contract), encoding='utf-8')
        manifest['tkinter_threading_self_test'] = frozen_contract
        (folder / "build-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        (folder / "runtime-self-test.json").write_text(json.dumps(runtime), encoding="utf-8")
        first_use = {"version": "0.5.3", "passed": True, "frozen": True,
                     "checks": {key: "passed" for key in first_use_self_test.REQUIRED_CHECKS}}
        (folder / "first-use-self-test.json").write_text(json.dumps(first_use), encoding="utf-8")
        for name, required in (('accessibility-self-test.json', packaging.ACCESSIBILITY_CHECKS),
                                ('windows-provider-self-test.json', packaging.PROVIDER_CHECKS),
                                ('local-voice-self-test.json', packaging.LOCAL_VOICE_CHECKS)):
            report = {'version': '0.5.3', 'passed': True, 'frozen': True,
                      'checks': {key: True for key in required}}
            if name == 'accessibility-self-test.json':
                report.update(platform='windows', windowing_system='win32', executable_sha256=manifest['sha256'])
            (folder / name).write_text(json.dumps(report), encoding='utf-8')
        return manifest

    def test_origin_and_notice_receipts_must_match_recomputed_results(self):
        for name in ('verify_native_origins', 'verify_wheel_notices', 'verify_python_notices'):
            with self.subTest(check=name), tempfile.TemporaryDirectory() as directory:
                folder = Path(directory)
                manifest = self.payload(folder)
                with patch.object(packaging, name, return_value={'passed': True, 'changed': True}), \
                        self.assertRaisesRegex(ValueError, 'receipt differs'):
                    packaging.validate_payload(folder, version='0.5.3', fingerprint=manifest['source_tree'])

    def test_frozen_threading_contract_rejects_stale_identity_or_incomplete_checks(self):
        for key, value in (('frozen', False), ('frozen', 1), ('version', 'old'),
                           ('executable_sha256', 'a' * 64), ('bridge_sha256', 'a' * 64),
                           ('contract_sha256', 'a' * 64), ('platform', 'linux'), ('checks', {}),
                           ('busywait_interval_ms', 1), ('errors', ['failed'])):
            with self.subTest(key=key, value=value), tempfile.TemporaryDirectory() as directory:
                folder = Path(directory)
                manifest = self.payload(folder)
                path = folder / 'tkinter-threading-self-test.json'
                report = json.loads(path.read_text())
                report[key] = value
                path.write_text(json.dumps(report))
                with self.assertRaisesRegex(ValueError, 'threading contract'):
                    packaging.validate_payload(folder, version='0.5.3', fingerprint=manifest['source_tree'])

    def test_frozen_threading_report_binds_extension_and_packaged_source(self):
        for changed in ('extension', 'source', 'builder', 'extra_extension', 'manifest', 'gate'):
            with self.subTest(changed=changed), tempfile.TemporaryDirectory() as directory:
                folder = Path(directory)
                manifest = self.payload(folder)
                repairs = folder / '_internal/licenses/tcltk/myl-tkinter-tcl9-repair'
                if changed == 'extension':
                    (folder / '_internal/_tkinter.pyd').write_bytes(b'tampered')
                elif changed == 'source':
                    (repairs / 'verify_tkinter_threading.py').write_bytes(b'tampered')
                elif changed == 'builder':
                    (repairs / 'threading-contract.json').write_text('{}')
                elif changed == 'extra_extension':
                    (folder / '_internal/_tkinter_other.pyd').write_bytes(b'ambiguous')
                else:
                    if changed == 'manifest':
                        manifest['tkinter_threading_self_test'] = {'changed': True}
                    else:
                        del manifest['validation']['tkinter_threading_self_test']
                    (folder / 'build-manifest.json').write_text(json.dumps(manifest))
                with self.assertRaises(ValueError):
                    packaging.validate_payload(folder, version='0.5.3', fingerprint=manifest['source_tree'])

    def test_threading_cli_only_runs_the_disposable_contract(self):
        with patch.object(bridge_contract, 'run_application_and_record', return_value=0) as check:
            self.assertEqual(main.cli(['--tkinter-threading-self-test', 'isolated.json']), 0)
            check.assert_called_once_with(Path('isolated.json'), version='0.5.3')
        for argv in (['--tkinter-threading-self-test'],
                     ['--tkinter-threading-self-test', 'out.json', '--profile', 'other']):
            with self.assertRaises(ValueError):
                main.cli(argv)

    def test_frozen_contract_hash_uses_packaged_source_not_pyz_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            expected = root / 'licenses/tcltk/myl-tkinter-tcl9-repair/verify_tkinter_threading.py'
            expected.parent.mkdir(parents=True)
            expected.write_bytes(b'synthetic contract source')
            with patch.object(bridge_contract.sys, 'frozen', True, create=True), \
                    patch.object(bridge_contract.sys, '_MEIPASS', str(root), create=True), \
                    patch.object(bridge_contract, '__file__', str(root / 'nonexistent-PYZ.py')):
                self.assertEqual(bridge_contract.contract_source(), expected)
                self.assertEqual(bridge_contract.contract_source().read_bytes(), b'synthetic contract source')

    def test_application_contract_adds_frozen_executable_binding_without_running_gui(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / 'synthetic.exe'
            executable.write_bytes(b'not executable')
            report = {'passed': True, 'checks': {}}
            with patch.object(bridge_contract, 'run_checks', return_value=report), \
                    patch.object(bridge_contract.sys, 'frozen', True, create=True), \
                    patch.object(bridge_contract.sys, 'executable', str(executable)), patch('builtins.print'):
                self.assertEqual(bridge_contract.run_and_record(root / 'result.json', expected_bridge_sha256='a' * 64,
                                                               version='0.5.3'), 0)
            written = json.loads((root / 'result.json').read_text())
            self.assertEqual(written['executable_sha256'], write_build_manifest.sha256(executable).lower())
            self.assertIs(written['frozen'], True)
            self.assertEqual(written['version'], '0.5.3')

    def test_frozen_bridge_launcher_has_an_external_deadline_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'result.json'
            with patch.object(bridge_contract.subprocess, 'run') as run:
                run.return_value.returncode = 0
                self.assertEqual(bridge_contract.run_frozen_process('inert.exe', output), 0)
                self.assertEqual(run.call_args.args[0], ['inert.exe', '--tkinter-threading-self-test', str(output)])
                self.assertEqual(run.call_args.kwargs['timeout'], 15)
                output.write_text('retain')
                run.reset_mock()
                with self.assertRaises(FileExistsError):
                    bridge_contract.run_frozen_process('inert.exe', output)
                run.assert_not_called()

    def test_payload_rejects_unfrozen_partial_failed_or_misversioned_voice_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            manifest = self.payload(folder)
            report_path = folder / 'local-voice-self-test.json'
            original = json.loads(report_path.read_text())
            mutations = [dict(original, frozen=False), dict(original, version='old'),
                         dict(original, checks={}), dict(original, checks={key: 'passed' for key in original['checks']})]
            for report in mutations:
                report_path.write_text(json.dumps(report), encoding='utf-8')
                with self.assertRaisesRegex(ValueError, 'evidence is incomplete'):
                    packaging.validate_payload(folder, version='0.5.3', fingerprint=manifest['source_tree'])

    def test_accessibility_api_report_is_bound_to_windows_and_the_actual_executable(self):
        for key, value in (('platform', 'linux'), ('windowing_system', 'aqua'), ('executable_sha256', 'old')):
            with self.subTest(key=key), tempfile.TemporaryDirectory() as directory:
                folder = Path(directory)
                manifest = self.payload(folder)
                path = folder / 'accessibility-self-test.json'
                report = json.loads(path.read_text())
                report[key] = value
                path.write_text(json.dumps(report))
                with self.assertRaisesRegex(ValueError, 'does not match this Windows executable'):
                    packaging.validate_payload(folder, version='0.5.3', fingerprint=manifest['source_tree'])

    def test_fingerprint_includes_version_assets_but_not_derived_checksums(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs").mkdir()
            (root / "VERSION").write_text("0.5.3", encoding="utf-8")
            (root / "ocr.traineddata").write_bytes(b"language")
            report = root / "docs/windows_0.5.3_checksums.md"
            report.write_text("pending", encoding="utf-8")
            with patch.object(write_build_manifest, "ROOT", root), patch.object(
                write_build_manifest, "git_value", return_value="VERSION\nocr.traineddata\ndocs/windows_0.5.3_checksums.md",
            ):
                original = write_build_manifest.source_tree_fingerprint()
                report.write_text("complete", encoding="utf-8")
                self.assertEqual(original, write_build_manifest.source_tree_fingerprint())
                (root / "ocr.traineddata").write_bytes(b"updated language")
                self.assertNotEqual(original, write_build_manifest.source_tree_fingerprint())
                self.assertEqual(original["files"], 2)

    def test_runtime_cli_does_not_launch_personal_workspace(self):
        with patch("tools.runtime_self_test.run_and_record", return_value=0) as check:
            self.assertEqual(main.cli(["--runtime-self-test", "isolated-report.json"]), 0)
            check.assert_called_once_with(Path("isolated-report.json"), version="0.5.3")

    def test_fingerprint_includes_native_provider_sources_and_headers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, header = root / 'provider.c', root / 'dispatcher.h'
            source.write_text('original native source', encoding='utf-8')
            header.write_text('original native header', encoding='utf-8')
            with patch.object(write_build_manifest, 'ROOT', root), patch.object(
                    write_build_manifest, 'git_value', return_value='provider.c\ndispatcher.h'):
                original = write_build_manifest.source_tree_fingerprint()
                self.assertEqual(original['files'], 2)
                source.write_text('changed source', encoding='utf-8')
                changed = write_build_manifest.source_tree_fingerprint()
                self.assertNotEqual(changed, original)
                header.write_text('changed header', encoding='utf-8')
                self.assertNotEqual(changed, write_build_manifest.source_tree_fingerprint())

    def test_runtime_cli_requires_explicit_output(self):
        with self.assertRaises(ValueError):
            main.cli(["--runtime-self-test"])

    def test_first_use_cli_launches_only_the_isolated_diagnostic(self):
        with patch("tools.first_use_self_test.run_and_record", return_value=0) as check:
            self.assertEqual(main.cli(["--first-use-self-test", "isolated.json"]), 0)
            check.assert_called_once_with(Path("isolated.json"), version="0.5.3")

    def test_first_use_cli_requires_explicit_output(self):
        with self.assertRaises(ValueError):
            main.cli(["--first-use-self-test"])

    def test_first_use_failure_is_recorded(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(
            first_use_self_test, "run_checks", return_value={"passed": False, "checks": {}},
        ):
            output = Path(tmp) / "report.json"
            self.assertEqual(first_use_self_test.run_and_record(output, version="0.5.3"), 1)
            self.assertFalse(json.loads(output.read_text(encoding="utf-8"))["passed"])

    def test_runtime_failure_is_recorded_and_returns_failure(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(
            runtime_self_test, "run_checks", return_value={"passed": False, "checks": {"image_ocr": "failed"}},
        ):
            output = Path(tmp) / "report.json"
            self.assertEqual(runtime_self_test.run_and_record(output, version="0.5.3"), 1)
            self.assertFalse(json.loads(output.read_text(encoding="utf-8"))["passed"])

    def test_payload_rejects_stale_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            self.payload(folder)
            with self.assertRaisesRegex(ValueError, "fingerprint"):
                packaging.validate_payload(folder, version="0.5.3", fingerprint={"sha256": "OLD"})

    def test_payload_rejects_changed_executable(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            manifest = self.payload(folder)
            (folder / "ManageYourLibrary.exe").write_bytes(b"replacement")
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                packaging.validate_payload(folder, version="0.5.3", fingerprint=manifest["source_tree"])

    def test_payload_rejects_personal_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            manifest = self.payload(folder)
            for name in ("config.json", "library_catalog.sqlite3-wal", "undo_log.jsonl",
                         "metadata_cache-old.json", "ocr_cache.json", "notes.db",
                         "personal.epub", "personal.pdf", "model.gguf.part",
                         "saved_views.json", "profile-manifest.json", ".profile.lock"):
                state = folder / name
                state.write_text("private", encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "Personal state"):
                    packaging.validate_payload(folder, version="0.5.3", fingerprint=manifest["source_tree"])
                self.assertTrue(state.exists(), "Reject contamination without deleting user data")
                state.unlink()

    def test_payload_rejects_personal_state_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            manifest = self.payload(folder)
            for name in ("ui_thumbnails", ".trash_manageyourlibrary", "backups"):
                state = folder / name
                state.mkdir()
                with self.assertRaisesRegex(ValueError, "Personal state"):
                    packaging.validate_payload(folder, version="0.5.3", fingerprint=manifest["source_tree"])
                self.assertTrue(state.exists())
                state.rmdir()

    def test_payload_rejects_embedded_profile_paths_without_mutating_the_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            manifest = self.payload(folder)
            native = folder / 'example.dll'
            data = 'C:\\Users\\SyntheticUser\\build\\native.c'.encode('utf-16-le')
            native.write_bytes(data)
            with self.assertRaisesRegex(ValueError, 'Private profile path.*example.dll'):
                packaging.validate_payload(folder, version='0.5.3', fingerprint=manifest['source_tree'])
            self.assertEqual(native.read_bytes(), data)

    def test_payload_requires_actual_first_use_checks(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            manifest = self.payload(folder)
            (folder / "first-use-self-test.json").write_text(
                json.dumps({"version": "0.5.3", "passed": True, "frozen": True, "checks": {}}), encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "first-use"):
                packaging.validate_payload(folder, version="0.5.3", fingerprint=manifest["source_tree"])

    def test_payload_requires_actual_frozen_runtime_checks(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            manifest = self.payload(folder)
            (folder / "runtime-self-test.json").write_text(
                json.dumps({"version": "0.5.3", "passed": True, "frozen": True, "checks": {}}), encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "incomplete"):
                packaging.validate_payload(folder, version="0.5.3", fingerprint=manifest["source_tree"])

    def test_packaging_generates_portable_installer_and_checksums(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "VERSION").write_text("0.5.3", encoding="utf-8")
            manifest = self.payload(root / "dist/windows/ManageYourLibrary")
            installer = root / "dist/installer/ManageYourLibrary-0.5.3-Setup-x64.exe"
            installer.parent.mkdir()
            installer.write_bytes(b"synthetic installer")
            with patch.object(packaging, "source_tree_fingerprint", return_value=manifest["source_tree"]), patch.object(packaging, 'validate_ocr_payload', return_value=manifest['ocr_source_payload']):
                artifacts = packaging.package(root)
            self.assertEqual(len(artifacts), 4)
            checksums = artifacts[-1].read_text(encoding="utf-8")
            for artifact in artifacts[:-1]:
                self.assertIn(write_build_manifest.sha256(artifact), checksums)
                self.assertTrue(artifact.is_file())

    def test_missing_redistribution_review_requires_explicit_development_label(self):
        import zipfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'VERSION').write_text('0.5.3')
            folder = root / 'dist/windows/ManageYourLibrary'
            manifest = self.payload(folder)
            manifest['validation'].pop('redistribution_review')
            (folder / 'build-manifest.json').write_text(json.dumps(manifest))
            installer = root / 'dist/installer/ManageYourLibrary-0.5.3-Setup-x64.exe'
            installer.parent.mkdir()
            installer.write_bytes(b'synthetic installer')
            with patch.object(packaging, 'source_tree_fingerprint', return_value=manifest['source_tree']), patch.object(packaging, 'validate_ocr_payload', return_value=manifest['ocr_source_payload']):
                with self.assertRaisesRegex(ValueError, 'Redistribution review'):
                    packaging.package(root)
                artifacts = packaging.package(root, development=True)
            self.assertTrue(all('development' in path.name for path in artifacts))
            with zipfile.ZipFile(artifacts[0]) as archive:
                self.assertIn('DEVELOPMENT-ONLY.txt', archive.namelist())


if __name__ == "__main__":
    unittest.main()

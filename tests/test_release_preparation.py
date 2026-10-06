import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import main
from tools import package_windows_release as packaging
from tools import first_use_self_test, runtime_self_test, write_build_manifest


class ReleasePreparationTests(unittest.TestCase):
    def payload(self, folder):
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "ManageYourLibrary.exe").write_bytes(b"synthetic executable")
        manifest = {
            "version": "0.5.3", "git_commit": "test-commit", "source_tree": {"sha256": "TEST", "files": 1},
            "sha256": write_build_manifest.sha256(folder / "ManageYourLibrary.exe"),
            "validation": {key: "passed" for key in (
                "automated_tests", "source_smoke", "catalog_performance_gate", "frozen_smoke", "runtime_self_test", "first_use_self_test")},
        }
        runtime = {"version": "0.5.3", "passed": True, "frozen": True,
                   "checks": {key: "passed" for key in ("tk_init", "bundled_languages", "image_ocr", "pdfium_ocr")}}
        (folder / "build-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        (folder / "runtime-self-test.json").write_text(json.dumps(runtime), encoding="utf-8")
        first_use = {"version": "0.5.3", "passed": True, "frozen": True,
                     "checks": {key: "passed" for key in first_use_self_test.REQUIRED_CHECKS}}
        (folder / "first-use-self-test.json").write_text(json.dumps(first_use), encoding="utf-8")
        return manifest

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
                         "personal.epub", "personal.pdf", "model.gguf.part"):
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
            with patch.object(packaging, "source_tree_fingerprint", return_value=manifest["source_tree"]):
                artifacts = packaging.package(root)
            self.assertEqual(len(artifacts), 4)
            checksums = artifacts[-1].read_text(encoding="utf-8")
            for artifact in artifacts[:-1]:
                self.assertIn(write_build_manifest.sha256(artifact), checksums)
                self.assertTrue(artifact.is_file())


if __name__ == "__main__":
    unittest.main()

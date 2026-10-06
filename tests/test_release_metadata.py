import unittest
from pathlib import Path

from tools import check_manual_release_results as manual_checker


ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.5.3"


class WindowsReleaseMetadataTests(unittest.TestCase):
    def test_version_file_declares_final_release(self):
        self.assertEqual((ROOT / "VERSION").read_text(encoding="utf-8").strip(), VERSION)

    def test_changelog_records_final_release(self):
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

        self.assertIn(f"## {VERSION} - 2026-10-06", changelog)
        self.assertIn(".trash_manageyourlibrary/", changelog)

    def test_release_notes_document_safety_and_local_runtime(self):
        notes = (ROOT / "docs" / f"release_notes_windows_{VERSION}.md").read_text(encoding="utf-8")

        for marker in (
            VERSION,
            ".trash_manageyourlibrary/",
            "Tesseract",
            "pypdfium2",
            "metadata lookup",
            "OCR remains local",
            "does not upload documents",
            "hash-locked",
        ):
            self.assertIn(marker, notes)

    def test_readme_links_final_release_docs(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn(f"Published Windows release: [`{VERSION}`]", readme)
        self.assertNotIn("Current Windows release candidate:", readme)
        for marker in (
            f"docs/release_notes_windows_{VERSION}.md",
            f"docs/windows_{VERSION}_checksums.md",
            "docs/windows_frozen_exe_manual_validation.md",
            "docs/manual_click_validation_form_windows.md",
            "docs/windows_release_checklist.md",
            "docs/manual_test_plan_windows.md",
        ):
            self.assertIn(marker, readme)

    def test_final_checksums_record_artifact_and_sha256(self):
        report = (ROOT / "docs" / f"windows_{VERSION}_checksums.md").read_text(encoding="utf-8")

        self.assertIn(f"Windows {VERSION} checksums", report)
        self.assertIn("dist/windows/ManageYourLibrary/ManageYourLibrary.exe", report)
        self.assertRegex(report, r"SHA256: `(?:[0-9A-Fa-f]{64}|PENDING_LOCAL_BUILD)`")

    def test_frozen_manual_validation_gate_is_documented(self):
        report = (ROOT / "docs" / "windows_frozen_exe_manual_validation.md").read_text(encoding="utf-8")

        for marker in (
            VERSION,
            "dist/windows/ManageYourLibrary/ManageYourLibrary.exe",
            "not performed",
            ".trash_manageyourlibrary/",
            "Tesseract",
            "PDFium",
            "APPDATA",
            "LOCALAPPDATA",
        ):
            self.assertIn(marker, report)

    def test_manual_plan_and_checklist_cover_frozen_ocr(self):
        manual_plan = (ROOT / "docs" / "manual_test_plan_windows.md").read_text(encoding="utf-8")
        checklist = (ROOT / "docs" / "windows_release_checklist.md").read_text(encoding="utf-8")

        self.assertIn("Validate frozen OCR and PDFium", manual_plan)
        self.assertIn("scanned-fixture.pdf", manual_plan)
        self.assertIn("synthetic scanned-PDF fixture", checklist)

    def test_gitignore_keeps_generated_release_artifacts_out_of_git(self):
        gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")

        for marker in ("build/", "dist/", "manual_release_validation/", ".trash_manageyourlibrary/"):
            self.assertIn(marker, gitignore)

    def test_manual_checker_does_not_inherit_historical_ui_approval(self):
        checks = {item.name: item for item in manual_checker._manual_checks_from_form()}

        self.assertEqual(checks["Undo button"].status, "PENDING")
        self.assertEqual(checks["Frozen OCR and PDFium buttons"].status, "PENDING")


if __name__ == "__main__":
    unittest.main()

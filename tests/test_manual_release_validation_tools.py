import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools import check_manual_release_results as checker
from tools import prepare_manual_release_validation as preparer


ROOT = Path(__file__).resolve().parents[1]


def write_manual_form(path: Path, undo="[ ] OK [ ] Fallo", ocr="[ ] OK [ ] Fallo", pdfium="[ ] OK [ ] Fallo"):
    path.write_text(
        "\n".join([
            "| Paso | Acción | Resultado | Validación | Notas |",
            "| --- | --- | --- | --- | --- |",
            f"| 6. Undo | Restore quarantined duplicate | Restored | {undo} | |",
            f"| 8. OCR image | Run local OCR | Completed | {ocr} | |",
            f"| 9. Scanned PDF | Run local PDF OCR | Completed | {pdfium} | |",
        ]) + "\n",
        encoding="utf-8",
    )


class ManualReleaseValidationToolTests(unittest.TestCase):
    def test_preparer_creates_safe_synthetic_fixtures_and_launcher(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            root = Path(tmp)
            manifest = preparer.prepare_validation(root)

            low = root / "input" / "add_books" / "Libro sintético ñ 三体.txt"
            duplicate = root / "input" / "exact_duplicate" / "Libro sintético duplicado ñ 三体.txt"
            unicode_epub = root / "input" / "metadata_search" / "Metadatos Unicode ñ 三体.epub"
            launcher = (root / "launch_frozen_validation.ps1").read_text(encoding="utf-8")

            self.assertEqual(preparer.sha256(low), preparer.sha256(duplicate))
            self.assertTrue(unicode_epub.is_file())
            self.assertTrue((root / "ocr" / "ocr-fixture.png").is_file())
            self.assertTrue((root / "ocr" / "scanned-fixture.pdf").is_file())
            self.assertTrue((root / preparer.MARKER_NAME).is_file())
            self.assertEqual(len(manifest["fixtures"]), 5)
            self.assertIn("APPDATA", launcher)
            self.assertIn("LOCALAPPDATA", launcher)
            self.assertIn("dist/windows/ManageYourLibrary/ManageYourLibrary.exe", launcher.replace("\\", "/"))

    def test_reset_refuses_unmarked_folder(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            root = Path(tmp)
            (root / "unrelated.txt").write_text("keep", encoding="utf-8")

            with self.assertRaises(RuntimeError):
                preparer.prepare_validation(root, reset=True)

            self.assertTrue((root / "unrelated.txt").is_file())

    def test_paths_outside_repository_are_rejected(self):
        # TEMP may intentionally live inside the repository during an isolated
        # build. Use an unambiguously external sibling without creating it.
        with self.assertRaises(ValueError):
            preparer.safe_validation_root(ROOT.parent / "outside-myl-validation-fixture")

    def test_validation_paths_inside_repository_remain_allowed(self):
        candidate = ROOT / "temp_release_validation" / "isolated-fixture"
        self.assertEqual(preparer.safe_validation_root(candidate), candidate.resolve())

    def test_checker_reports_pending_before_click_through(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            root = Path(tmp)
            preparer.prepare_validation(root)

            with mock.patch.object(checker, "_process_running", return_value=False):
                checks = checker.inspect_validation(root)
            report = checker.write_report(root, checks)

            self.assertTrue(report.is_file())
            self.assertFalse(any(item.status == "FAIL" for item in checks))
            self.assertTrue(any(item.status == "PENDING" for item in checks))

    def test_checker_detects_temporary_move_quarantine_and_in_place_rename(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            root = Path(tmp)
            preparer.prepare_validation(root)
            review = root / "library" / "PARA REVISAR NUEVAMENTE"
            trash = root / "library" / ".trash_manageyourlibrary"
            review.mkdir(parents=True)
            trash.mkdir(parents=True)

            low = root / "input" / "add_books" / "Libro sintético ñ 三体.txt"
            duplicate = root / "input" / "exact_duplicate" / "Libro sintético duplicado ñ 三体.txt"
            unicode_epub = root / "input" / "metadata_search" / "Metadatos Unicode ñ 三体.epub"
            low.rename(review / low.name)
            duplicate.rename(trash / duplicate.name)
            (trash / "manifest.jsonl").write_text("{}\n", encoding="utf-8")
            unicode_epub.rename(unicode_epub.with_name("Álvaro Núñez - El niño y 三体 (2026).epub"))

            checks = {item.name: item for item in checker.inspect_validation(root)}

            self.assertEqual(checks["Add books temporary move"].status, "PASS")
            self.assertEqual(checks["Exact duplicate quarantine"].status, "PASS")
            self.assertEqual(checks["Quarantine manifest"].status, "PASS")
            self.assertEqual(checks["Search metadata stays in place"].status, "PASS")

    def test_manual_checks_read_marked_ok_steps(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            form = Path(tmp) / "form.md"
            write_manual_form(form, undo="[x] OK [ ] Fallo", ocr="[x] OK [ ] Fallo", pdfium="[x] OK [ ] Fallo")

            checks = {item.name: item for item in checker._manual_checks_from_form(form)}

            self.assertEqual(checks["Undo button"].status, "PASS")
            self.assertEqual(checks["Frozen OCR and PDFium buttons"].status, "PASS")

    def test_manual_checks_remain_pending_when_unmarked(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            form = Path(tmp) / "form.md"
            write_manual_form(form)

            checks = {item.name: item for item in checker._manual_checks_from_form(form)}

            self.assertEqual(checks["Undo button"].status, "PENDING")
            self.assertEqual(checks["Frozen OCR and PDFium buttons"].status, "PENDING")

    def test_manual_checks_fail_when_step_is_marked_as_failure(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            form = Path(tmp) / "form.md"
            write_manual_form(form, undo="[ ] OK [x] Fallo", ocr="[x] OK [ ] Fallo", pdfium="[ ] OK [x] Fallo")

            checks = {item.name: item for item in checker._manual_checks_from_form(form)}

            self.assertEqual(checks["Undo button"].status, "FAIL")
            self.assertEqual(checks["Frozen OCR and PDFium buttons"].status, "FAIL")

    def test_manual_checks_fail_when_step_is_marked_both_ok_and_failure(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            form = Path(tmp) / "form.md"
            write_manual_form(form, undo="[x] OK [x] Fallo")

            checks = {item.name: item for item in checker._manual_checks_from_form(form)}

            self.assertEqual(checks["Undo button"].status, "FAIL")
            self.assertIn("both OK and Fallo", checks["Undo button"].detail)

    def test_manual_checks_remain_pending_when_form_is_missing(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            form = Path(tmp) / "missing.md"

            checks = {item.name: item for item in checker._manual_checks_from_form(form)}

            self.assertEqual(checks["Undo button"].status, "PENDING")
            self.assertEqual(checks["Frozen OCR and PDFium buttons"].status, "PENDING")
            self.assertIn("not found", checks["Undo button"].detail)

    def test_manual_checks_remain_pending_when_expected_line_is_missing(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            form = Path(tmp) / "form.md"
            form.write_text("| 6. Undo | Restore | Restored | [x] OK [ ] Fallo | |\n", encoding="utf-8")

            checks = {item.name: item for item in checker._manual_checks_from_form(form)}

            self.assertEqual(checks["Undo button"].status, "PASS")
            self.assertEqual(checks["Frozen OCR and PDFium buttons"].status, "PENDING")
            self.assertIn("line not found", checks["Frozen OCR and PDFium buttons"].detail)

    def test_manual_checks_fail_when_expected_line_is_duplicated(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            form = Path(tmp) / "form.md"
            write_manual_form(form)
            with form.open("a", encoding="utf-8") as stream:
                stream.write("| 6. Undo | Duplicate | Restored | [x] OK [ ] Fallo | |\n")

            checks = {item.name: item for item in checker._manual_checks_from_form(form)}

            self.assertEqual(checks["Undo button"].status, "FAIL")
            self.assertIn("multiple lines", checks["Undo button"].detail)


if __name__ == "__main__":
    unittest.main()

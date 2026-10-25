import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class WindowsBuildConfigTests(unittest.TestCase):
    def test_windows_ci_uses_a_neutral_isolated_patched_runtime(self):
        workflow = (ROOT / '.github/workflows/windows.yml').read_text(encoding='utf-8')
        self.assertIn('codex/audit-optimizations', workflow)
        self.assertIn('python -m venv C:/myl-native-build/venv', workflow)
        self.assertIn('MANAGE_YOUR_LIBRARY_PYTHON=C:/myl-native-build/venv/Scripts/python.exe', workflow)
        self.assertIn('build_accessible_tk.py --output C:/myl-native-build/gui', workflow)
        self.assertLess(workflow.index('build_accessible_tk.py'), workflow.index('BUILD_WINDOWS.bat'))

    def test_root_build_shortcut_delegates_to_windows_script(self):
        shortcut = (ROOT / "BUILD_EXE.bat").read_text(encoding="utf-8")

        self.assertIn(r"platforms\windows\BUILD_WINDOWS.bat", shortcut)

    def test_windows_build_bundles_local_ocr_and_pdfium(self):
        script = (ROOT / "platforms" / "windows" / "BUILD_WINDOWS.bat").read_text(encoding="utf-8")
        spec = (ROOT / "platforms" / "windows" / "ManageYourLibrary.spec").read_text(encoding="utf-8")

        self.assertIn('validate_payload(OCR)', spec)
        self.assertIn('(str(OCR), "tesseract")', spec)
        self.assertNotIn('(str(ROOT / "tesseract"), "tesseract")', spec)
        self.assertIn('ROOT / "data"', spec)
        self.assertIn('collect_all(package)', spec)
        self.assertIn('"pefile"', spec)  # Diagnostic PE parser: retain its MIT notice.
        self.assertIn('"pypdfium2"', spec)
        self.assertIn('ROOT / "app_icon.ico"', spec)
        self.assertIn("--require-hashes", script)
        self.assertNotIn("rapidfuzz", (script + spec).lower())
        self.assertNotIn(r"c:\users", script.lower())
        for language in ("eng", "spa", "fra", "nld", "chi_sim"):
            self.assertIn(language, script)

    def test_models_are_tracked_but_legacy_ocr_binaries_are_not(self):
        runtime = ROOT / "tesseract"
        self.assertFalse(list(runtime.glob('*.dll')))
        self.assertFalse((runtime / 'tesseract.exe').exists())
        for language in ("eng", "spa", "fra", "nld", "chi_sim"):
            self.assertTrue((runtime / "tessdata" / f"{language}.traineddata").is_file())

    def test_requirements_do_not_reintroduce_unused_rapidfuzz(self):
        requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8").lower()

        self.assertNotIn("rapidfuzz", requirements)

    def test_source_ocr_keeps_fallback_configs_without_training_residue(self):
        data = ROOT / 'tesseract/tessdata'
        self.assertEqual({path.name for path in (data / 'configs').iterdir()}, {'txt', 'tsv'})
        self.assertFalse((data / 'pdf.ttf').exists())
        self.assertFalse(any((data / 'tessconfigs').glob('*')))

    def test_gitignore_excludes_local_generated_state(self):
        gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")

        for entry in (
            "build/",
            "dist/",
            ".trash_manageyourlibrary/",
            "config.json",
            "library_index.json",
            "library_catalog.sqlite3*",
            "ui_thumbnails/",
            "undo_log.jsonl",
            "file_transactions.jsonl",
            "ai/runtime/",
            "ai/models/",
            "*.gguf",
            "*.gguf.part",
        ):
            self.assertIn(entry, gitignore)

    def test_sources_do_not_reference_prohibited_cloud_services(self):
        checked_extensions = {".py", ".bat", ".sh"}
        source_text = "\n".join(
            path.read_text(encoding="utf-8", errors="ignore").lower()
            for path in ROOT.rglob("*")
            if path.is_file()
            and path.suffix.lower() in checked_extensions
            and ".git" not in path.parts
        )
        prohibited = (
            "google" + " books",
            "books." + "googleapis",
            "google " + "vision",
            "aws " + "textract",
            "".join((
                "azure ",
                "ocr",
            )),
            "document " + "ai",
        )

        for marker in prohibited:
            self.assertNotIn(marker, source_text)


if __name__ == "__main__":
    unittest.main()

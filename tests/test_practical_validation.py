import importlib.util
import tempfile
import unittest
from pathlib import Path

import library_core
import ocr_engine
from core import file_transactions


class PracticalFileWorkflowTests(unittest.TestCase):
    CORE_PATH_NAMES = (
        "FINAL",
        "APP_DATA",
        "CONFIG_JSON",
        "INDICE_JSON",
        "HISTORIAL_CSV",
        "UNDO_JSONL",
        "FILE_TRANSACTION_JOURNAL",
        "TRASH_MANIFEST_JSONL",
        "CATALOG_DB",
    )

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.library = self.root / "library"
        self.input_dir = self.root / "input"
        self.app_data = self.root / "app_data"
        self.library.mkdir()
        self.input_dir.mkdir()
        self.original_core_paths = {name: getattr(library_core, name) for name in self.CORE_PATH_NAMES}
        library_core.FINAL = self.library
        library_core.APP_DATA = self.app_data
        library_core.CONFIG_JSON = self.app_data / "config.json"
        library_core.INDICE_JSON = self.app_data / "library_index.json"
        library_core.HISTORIAL_CSV = self.app_data / "library_history.csv"
        library_core.UNDO_JSONL = self.app_data / "undo_log.jsonl"
        library_core.FILE_TRANSACTION_JOURNAL = self.app_data / "file_transactions.jsonl"
        library_core.TRASH_MANIFEST_JSONL = self.app_data / "trash_manifest.jsonl"
        library_core.CATALOG_DB = self.app_data / "library_catalog.sqlite3"

    def tearDown(self):
        for name, value in self.original_core_paths.items():
            setattr(library_core, name, value)
        self.tmp.cleanup()

    def make_book(self, folder, name, content):
        path = Path(folder) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def undo_latest_batch(self):
        batch, actions = library_core.obtener_ultima_accion_undo()
        self.assertIsNotNone(batch)
        for item in reversed(actions):
            ok, message = library_core.restaurar_accion_undo(item)
            self.assertTrue(ok, message)
        library_core.mark_action_undone(batch)

    def test_quarantine_undo_restores_original_file(self):
        source = self.make_book(self.input_dir, "Duplicado ñ.epub", "contenido")
        batch = library_core.nuevo_batch_id("quarantine")

        quarantined = library_core.descartar_archivo_seguro(source, motivo="duplicate fixture")
        library_core.registrar_undo(batch, "mover", source, quarantined, "duplicate fixture")

        self.assertTrue(quarantined.exists())
        self.assertFalse(source.exists())
        self.undo_latest_batch()
        self.assertTrue(source.exists())
        self.assertFalse(quarantined.exists())

    def test_replacement_undo_restores_both_files(self):
        old_file = self.make_book(self.library, "Autor - Libro.epub", "old")
        incoming = self.make_book(self.input_dir, "Autor - Libro nuevo.epub", "new")
        batch = library_core.nuevo_batch_id("replace")

        destination, quarantined = library_core.mover_a_final_reemplazando(
            incoming,
            old_file.name,
            old_file,
            motivo="replace fixture",
        )
        library_core.registrar_undo(batch, "mover", old_file, quarantined, "restore previous")
        library_core.registrar_undo(batch, "mover", incoming, destination, "restore incoming")

        self.assertEqual(destination.read_text(encoding="utf-8"), "new")
        self.assertEqual(quarantined.read_text(encoding="utf-8"), "old")
        self.undo_latest_batch()
        self.assertEqual(old_file.read_text(encoding="utf-8"), "old")
        self.assertEqual(incoming.read_text(encoding="utf-8"), "new")

    def test_unicode_search_metadata_rename_stays_in_place(self):
        source = self.make_book(self.input_dir, "旧名字 ñ.epub", "unicode")

        destination = library_core.renombrar_en_sitio_seguro(source, "El niño 三体.epub", motivo="metadata")

        self.assertEqual(destination.parent, self.input_dir)
        self.assertTrue(destination.exists())
        self.assertFalse((self.library / destination.name).exists())

    def test_missing_undo_source_returns_clear_error(self):
        ok, message = library_core.restaurar_accion_undo(
            {"origen": str(self.input_dir / "original.epub"), "destino": str(self.input_dir / "missing.epub")}
        )

        self.assertFalse(ok)
        self.assertIn("No existe", message)

    def test_completed_move_is_committed_in_journal(self):
        source = self.make_book(self.input_dir, "Movido.epub", "journal")

        destination = library_core.mover_a_final(source, source.name, motivo="journal fixture")
        journal = file_transactions.leer_jsonl(library_core.FILE_TRANSACTION_JOURNAL)

        self.assertTrue(destination.exists())
        self.assertTrue(any(item.get("type") == "move_to_library" and item.get("state") == "committed" for item in journal))


class LocalOcrSmokeTests(unittest.TestCase):
    def test_local_indra_recovers_a_short_chinese_cover_title(self):
        font_path = Path("C:/Windows/Fonts/msyh.ttc")
        if not ocr_engine.ocr_runtime.available() or not font_path.is_file():
            self.skipTest("Indra models and Chinese font required for the short-title regression")
        from io import BytesIO
        from PIL import Image, ImageDraw, ImageFont

        with Image.new("RGB", (1300, 1700), "white") as image, BytesIO() as output:
            draw = ImageDraw.Draw(image)
            font = ImageFont.truetype(str(font_path), 72)
            draw.text((140, 260), "三体", font=font, fill="black")
            draw.text((140, 550), "刘慈欣", font=font, fill="black")
            image.save(output, format="PNG")
            try:
                result = ocr_engine.extraer_texto_imagen_bytes_ocr(output.getvalue())
            finally:
                ocr_engine.limpiar_cache_ocr()
        self.assertIsNone(result["error"])
        self.assertIn("三体", result["texto"])
        self.assertIn("刘慈欣", result["texto"])

    def test_local_indra_processes_synthetic_image(self):
        if not ocr_engine.ocr_runtime.available():
            self.skipTest("Local Indra runtime/models are not available")
        from PIL import Image, ImageDraw, ImageFont

        with tempfile.TemporaryDirectory() as tmp:
            image_path = Path(tmp) / "ocr-smoke.png"
            image = Image.new("RGB", (1400, 360), "white")
            draw = ImageDraw.Draw(image)
            draw.text((80, 100), "MANAGE YOUR LIBRARY OCR TEST 2026", fill="black", font=ImageFont.load_default(size=38))
            image.save(image_path)

            result = ocr_engine.extraer_texto_documento_ocr(image_path)
            text, error = result["texto"], result["error"]
            ocr_engine.limpiar_cache_ocr()

        self.assertIsNone(error)
        self.assertTrue(text.strip())
        self.assertIn("LIBRARY", text.upper())

    def test_pdfium_renders_synthetic_scanned_pdf_when_available(self):
        if importlib.util.find_spec("pypdfium2") is None:
            self.skipTest("pypdfium2 is not installed in this test interpreter")
        from PIL import Image, ImageDraw

        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "scanned-smoke.pdf"
            image = Image.new("RGB", (900, 300), "white")
            draw = ImageDraw.Draw(image)
            draw.text((60, 100), "SCANNED PDF FIXTURE", fill="black")
            image.save(pdf_path, "PDF", resolution=150.0)

            pages = ocr_engine.render_first_pages(pdf_path, max_paginas=1, dpi=100)

        self.assertEqual(len(pages), 1)
        self.assertTrue(pages[0]["image_bytes"])


if __name__ == "__main__":
    unittest.main()

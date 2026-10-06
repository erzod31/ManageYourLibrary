import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import library_core
import ocr_engine


class OcrEngineEnhancementTests(unittest.TestCase):
    def test_ocr_isbn_confusions_are_corrected_only_when_checksum_is_valid(self):
        text = "ISBN 978-O-3O7-47472-8"

        self.assertEqual(ocr_engine._extraer_isbns(text), ["9780307474728"])

    def test_ocr_language_detection_uses_multilingual_profiles(self):
        self.assertEqual(ocr_engine.detectar_idioma_ocr_rapido("El prólogo de la edición"), "spa+eng")
        self.assertEqual(ocr_engine.detectar_idioma_ocr_rapido("三体 Liu Cixin"), "chi_sim+eng")

    def test_prepare_image_variants_keeps_multiple_safe_preprocessing_options(self):
        from PIL import Image, ImageDraw

        image = Image.new("RGB", (460, 180), "black")
        draw = ImageDraw.Draw(image)
        draw.text((40, 70), "SAND LAND", fill="white")
        with tempfile.TemporaryDirectory() as tmp:
            image_path = Path(tmp) / "dark-cover.png"
            image.save(image_path)
            raw = image_path.read_bytes()

        variants = ocr_engine._prepare_image_variants_raw(raw, include_rotations=True)
        names = {item["name"] for item in variants}

        self.assertIn("normalized", names)
        self.assertIn("binary", names)
        self.assertTrue(any(item["rotation"] in {90, 180, 270} for item in variants))

    def test_best_ocr_attempt_prefers_useful_variant_over_longer_noise(self):
        variants = [
            {"name": "normalized", "image_bytes": b"v1", "rotation": 0},
            {"name": "binary", "image_bytes": b"v2", "rotation": 0},
        ]

        def fake_ocr(image_bytes, lang, psm="6", timeout=45):
            if image_bytes == b"v2":
                return "El nombre de la rosa\nUmberto Eco\n1980", None
            return "@@@ ### === " * 20, None

        with patch.object(ocr_engine, "_prepare_image_variants_raw", return_value=variants), \
                patch.object(ocr_engine, "_run_tesseract_bytes", side_effect=fake_ocr):
            best = ocr_engine._run_best_ocr_image(b"raw", "spa+eng", psms=("6",), allow_variants=True)

        self.assertEqual(best["variant"], "binary")
        self.assertIn("Umberto Eco", best["text"])
        self.assertGreater(best["score"], 40)

    def test_layout_tokens_use_relative_page_geometry(self):
        tokens = [
            {"text": "El", "page": 1, "block": 1, "line": 1, "x": 420, "y": 900, "width": 50, "height": 80, "confidence": 90},
            {"text": "nombre", "page": 1, "block": 1, "line": 1, "x": 480, "y": 900, "width": 180, "height": 80, "confidence": 91},
            {"text": "de", "page": 1, "block": 1, "line": 1, "x": 670, "y": 900, "width": 60, "height": 80, "confidence": 91},
            {"text": "la", "page": 1, "block": 1, "line": 1, "x": 740, "y": 900, "width": 50, "height": 80, "confidence": 91},
            {"text": "rosa", "page": 1, "block": 1, "line": 1, "x": 800, "y": 900, "width": 120, "height": 80, "confidence": 91},
            {"text": "Editorial", "page": 1, "block": 2, "line": 1, "x": 80, "y": 1780, "width": 160, "height": 30, "confidence": 80},
        ]
        with patch.object(ocr_engine, "_run_tesseract_tsv_bytes", return_value=(tokens, None)):
            layout = ocr_engine.extract_layout_tokens(b"image", lang="spa+eng", psm="6")

        title_line = layout["lines"][0]
        self.assertEqual(title_line["relative_position"], "center")
        self.assertTrue(title_line["centered"])

    def test_cbz_cover_images_are_available_for_ocr(self):
        from PIL import Image, ImageDraw

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            cover_path = tmp_path / "cover.png"
            image = Image.new("RGB", (800, 1200), "white")
            draw = ImageDraw.Draw(image)
            draw.text((120, 200), "SAND LAND", fill="black")
            image.save(cover_path)
            cbz_path = tmp_path / "Sand Land.cbz"
            with zipfile.ZipFile(cbz_path, "w") as z:
                z.write(cover_path, "001-cover.png")

            images = library_core.imagenes_portada_cbz(cbz_path)

        self.assertEqual(len(images), 1)
        self.assertGreater(len(images[0]), 6000)

    def test_mislabelled_cbz_rar_uses_tar_fallback_for_cover(self):
        from io import BytesIO
        from PIL import Image, ImageDraw

        image = Image.new("RGB", (900, 1300), "white")
        draw = ImageDraw.Draw(image)
        draw.text((120, 240), "SAND LAND", fill="black")
        out = BytesIO()
        image.save(out, format="JPEG", quality=92)
        cover_bytes = out.getvalue()

        with tempfile.TemporaryDirectory() as tmp:
            archive_path = Path(tmp) / "Sand Land.cbz"
            archive_path.write_bytes(b"Rar!\x1a\x07\x00fake")

            with patch.object(library_core, "_tar_archivo_lista", return_value=["comic/000.jpg"]), \
                    patch.object(library_core, "_tar_extraer_miembro_bytes", return_value=cover_bytes):
                images = library_core.imagenes_portada_cbz(archive_path)

        self.assertEqual(len(images), 1)
        self.assertEqual(images[0], cover_bytes)

    def test_comic_archive_metadata_uses_internal_folder_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive_path = Path(tmp) / "Sand Land (2003) (Goldenagato).cbz"
            archive_path.write_bytes(b"Rar!\x1a\x07\x00fake")

            with patch.object(
                library_core,
                "_tar_archivo_lista",
                return_value=[
                    "Sand Land (2003) (Digital) (BlurPixel-Empire)/000.jpg",
                    "Sand Land (2003) (Digital) (BlurPixel-Empire)/001.jpg",
                ],
            ):
                meta = library_core.extraer_metadatos_comic_archivo(archive_path)

        self.assertEqual(meta["titulo"], "Sand Land")
        self.assertEqual(meta["anio"], "2003")

    def test_comic_queries_include_title_year_and_medium(self):
        queries = library_core.generar_consultas_web(
            {
                "titulo_local": "Sand Land",
                "anio_local": "2003",
                "tipo_documento": "comic_manga",
                "consulta": "Sand Land",
            },
            Path("Sand Land (2003).cbz"),
        )

        self.assertIn("Sand Land 2003", queries)
        self.assertIn("Sand Land manga", queries)

    def test_web_candidate_not_discarded_when_ocr_author_is_really_title(self):
        datos = {
            "titulo_local": "Sand Land",
            "anio_local": "2003",
            "autor_texto": "Sand Land",
            "tipo_documento": "comic_manga",
        }
        candidates = [
            {
                "fuente": "Open Library",
                "titulo": "Sand Land",
                "autor": "鳥山 明 [Akira Toriyama]",
                "anio": "2004",
                "isbn": "9781591161813",
            },
            {
                "fuente": "Open Library",
                "titulo": "Sand's Land Story",
                "autor": "J. R. SF",
                "anio": "2021",
                "isbn": "9798731261654",
            },
        ]

        result = library_core.elegir_mejor_metadato(Path("Sand Land (2003).cbz"), datos, candidates)

        self.assertTrue(result["encontrado"])
        self.assertEqual(result["autor"], "Akira Toriyama")
        self.assertEqual(result["titulo"], "Sand Land")
        self.assertEqual(result["nombre_sugerido"], "Akira Toriyama - Sand Land (2003).cbz")

    def test_author_native_name_with_latin_alias_prefers_alias_for_filename(self):
        self.assertEqual(
            library_core.preferir_alias_latino_autor("鳥山 明 [Akira Toriyama]"),
            "Akira Toriyama",
        )
        self.assertEqual(
            library_core.crear_nombre_sugerido("鳥山 明 [Akira Toriyama]", "Sand Land", "2003", "", ".cbz"),
            "Akira Toriyama - Sand Land (2003).cbz",
        )

    def test_cbz_local_extraction_can_use_cover_ocr_candidates(self):
        ocr_result = {
            "texto": "Sand Land\nAkira Toriyama\n2003",
            "metodo": "image_ocr",
            "ocr_title_candidates": [{"text": "Sand Land", "score": 88}],
            "ocr_author_candidates": [{"text": "Akira Toriyama", "score": 80, "role": "author"}],
            "ocr_year_candidates": ["2003"],
            "ocr_confidence": 88,
        }
        with tempfile.TemporaryDirectory() as tmp:
            cbz_path = Path(tmp) / "Sand Land (2003).cbz"
            with zipfile.ZipFile(cbz_path, "w") as z:
                z.writestr("001-cover.png", b"fake image bytes large enough" * 400)

            with patch.object(library_core, "imagenes_portada_cbz", return_value=[b"cover"]), \
                    patch("ocr_engine.extraer_texto_imagen_bytes_ocr", return_value=ocr_result):
                datos = library_core.extraer_datos_locales(cbz_path, permitir_ocr=True)

        self.assertEqual(datos["titulo_texto"], "Sand Land")
        self.assertEqual(datos["autor_texto"], "Akira Toriyama")
        self.assertEqual(datos["anio_texto"], "2003")
        self.assertEqual(datos["ocr_metodo"], "image_ocr")
        resolved = library_core.elegir_metadatos_locales(cbz_path, datos)
        self.assertTrue(resolved["encontrado"])
        self.assertEqual(resolved["titulo"], "Sand Land")
        self.assertEqual(resolved["autor"], "Akira Toriyama")


if __name__ == "__main__":
    unittest.main()

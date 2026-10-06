import tempfile
import unittest
import hashlib
from pathlib import Path

from core import duplicate_engine


class DuplicateEngineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def make_file(self, name, content="book"):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def item(self, path, *, title=None, author="", size=None, mtime=1000, sha=""):
        title = title or path.stem
        norm_title = duplicate_engine.titulo_normalizado_para_dobles(title)
        return {
            "ruta": str(path),
            "nombre": path.name,
            "extension": path.suffix.lower(),
            "tamano_bytes": size if size is not None else path.stat().st_size,
            "mtime": mtime,
            "sha256": sha,
            "nombre_normalizado": duplicate_engine.normalizar_texto(path.name),
            "autor": author,
            "autor_normalizado": duplicate_engine.normalizar_texto(author),
            "titulo_normalizado": norm_title,
            "titulos_normalizados": [norm_title],
        }

    def test_verificar_libro_detects_exact_duplicate_by_hash(self):
        existing = self.make_file("Autor - Libro.epub", "same")
        incoming = self.make_file("Entrada.epub", "same")
        existing_item = self.item(existing, title="Libro", sha="abc", size=incoming.stat().st_size)

        result = duplicate_engine.verificar_libro(
            incoming,
            {"archivos": [existing_item]},
            calcular_hash_func=lambda _path: "abc",
            es_libro_func=lambda _path: True,
            tr_func=lambda key, **params: key,
        )

        self.assertEqual(result["estado"], "duplicado_exacto")
        self.assertEqual(result["exactos"][0]["ruta"], str(existing))

    def test_verificar_libro_keeps_hash_distinct_books_unique(self):
        existing = self.make_file("Autor - Libro A.epub", "a")
        incoming = self.make_file("Autor - Libro B.epub", "b")
        existing_item = self.item(existing, title="Libro A", sha="hash-a", size=incoming.stat().st_size)

        result = duplicate_engine.verificar_libro(
            incoming,
            {"archivos": [existing_item]},
            calcular_hash_func=lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest(),
            es_libro_func=lambda _path: True,
            tr_func=lambda key, **params: key,
        )

        self.assertNotEqual(result["estado"], "duplicado_exacto")

    def test_possible_duplicate_can_have_different_size(self):
        existing = self.make_file("Isabel Allende - La casa de los espiritus.epub", "small")
        incoming = self.make_file("La casa de los espiritus.pdf", "much larger content")
        existing_item = self.item(existing, title="La casa de los espiritus", author="Isabel Allende", size=10)

        result = duplicate_engine.verificar_libro(
            incoming,
            {"archivos": [existing_item]},
            calcular_hash_func=lambda _path: "different",
            es_libro_func=lambda _path: True,
            tr_func=lambda key, **params: key,
        )

        self.assertEqual(result["estado"], "posible_duplicado")
        self.assertNotEqual(existing_item["tamano_bytes"], incoming.stat().st_size)

    def test_same_book_epub_and_pdf_are_semantic_duplicates(self):
        epub = self.make_file("Ursula K Le Guin - Los desposeidos.epub")
        pdf = self.make_file("Los desposeidos.pdf")
        index = {"archivos": [
            self.item(epub, title="Los desposeidos", author="Ursula K Le Guin", size=100, sha="epub"),
            self.item(pdf, title="Los desposeidos", author="Ursula K Le Guin", size=500, sha="pdf"),
        ]}

        results = duplicate_engine.buscar_dobles_biblioteca(index)

        self.assertTrue(any(item["tipo"] == "duplicado_exacto" for item in results))

    def test_stale_index_hash_cannot_create_false_exact_duplicate(self):
        existing = self.make_file("Autor - Libro.epub", "new!")
        incoming = self.make_file("Entrada.epub", "old!")
        stale_hash = hashlib.sha256(incoming.read_bytes()).hexdigest()
        existing_item = self.item(existing, title="Libro", sha=stale_hash, size=incoming.stat().st_size)

        result = duplicate_engine.verificar_libro(
            incoming,
            {"archivos": [existing_item]},
            calcular_hash_func=lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest(),
            es_libro_func=lambda _path: True,
            tr_func=lambda key, **params: key,
        )

        self.assertNotEqual(result["estado"], "duplicado_exacto")
        self.assertNotEqual(existing_item["sha256"], stale_hash)

    def test_preference_uses_quality_format_before_newer_date(self):
        epub_old = {"extension": ".epub", "mtime": 100}
        pdf_new = {"extension": ".pdf", "mtime": 200}

        self.assertEqual(duplicate_engine.elegir_item_preferido_por_fecha_y_formato(epub_old, pdf_new), "a")

    def test_preference_uses_bibliographic_evidence_before_date(self):
        verified_old = {"extension": ".pdf", "mtime": 100, "isbn": "9780306406157", "autor": "Ada Author"}
        weak_new = {"extension": ".epub", "mtime": 999}

        self.assertEqual(duplicate_engine.elegir_item_preferido_por_fecha_y_formato(verified_old, weak_new), "a")

    def test_preference_epub_wins_format_tie(self):
        epub = {"extension": ".epub", "mtime": 100}
        pdf = {"extension": ".pdf", "mtime": 100}

        self.assertEqual(duplicate_engine.elegir_item_preferido_por_fecha_y_formato(epub, pdf), "a")
        self.assertEqual(duplicate_engine.elegir_item_preferido_por_fecha_y_formato(pdf, epub), "b")

    def test_preference_mobi_after_epub(self):
        mobi = {"extension": ".mobi", "mtime": 100}
        pdf = {"extension": ".pdf", "mtime": 100}
        epub = {"extension": ".epub", "mtime": 100}

        self.assertEqual(duplicate_engine.elegir_item_preferido_por_fecha_y_formato(mobi, pdf), "a")
        self.assertEqual(duplicate_engine.elegir_item_preferido_por_fecha_y_formato(mobi, epub), "b")

    def test_unicode_accents_and_enye_match(self):
        compatible, score = duplicate_engine.titulos_dobles_compatibles("El niño ñandú", "El nino nandu")

        self.assertTrue(compatible)
        self.assertGreaterEqual(score, 0.99)

    def test_non_latin_title_is_not_normalized_to_empty(self):
        normalized = duplicate_engine.titulo_normalizado_para_dobles("三体 刘慈欣")

        self.assertTrue(normalized)

    def test_trash_folder_does_not_participate_in_candidates(self):
        kept = self.make_file("Visible.epub", "same")
        trashed = self.make_file(".trash_manageyourlibrary/Oculto.epub", "same")
        index = {"archivos": [
            self.item(kept, title="Visible", sha="same-hash"),
            self.item(trashed, title="Visible", sha="same-hash"),
        ]}

        results = duplicate_engine.buscar_dobles_biblioteca(
            index,
            ignorar_por_carpeta_func=lambda path: ".trash_manageyourlibrary" in [part.lower() for part in Path(path).parts],
        )

        self.assertEqual(results, [])

    def test_filters_duplicates_between_two_folders_only(self):
        folder_a = self.root / "base"
        folder_b = self.root / "compare"
        a_match = self.make_file("base/Autor - Libro.epub", "a")
        b_match = self.make_file("compare/Autor - Libro.pdf", "b")
        a_internal = self.make_file("base/Autor - Libro copia.mobi", "c")
        b_internal = self.make_file("compare/Otro - Libro.epub", "d")

        cross = {
            "tipo": "duplicado_de_titulo",
            "archivo_a": self.item(a_match, title="Libro", author="Autor"),
            "archivo_b": self.item(b_match, title="Libro", author="Autor"),
        }
        inside_a = {
            "tipo": "duplicado_de_titulo",
            "archivo_a": self.item(a_match, title="Libro", author="Autor"),
            "archivo_b": self.item(a_internal, title="Libro", author="Autor"),
        }
        inside_b = {
            "tipo": "duplicado_de_titulo",
            "archivo_a": self.item(b_match, title="Libro", author="Autor"),
            "archivo_b": self.item(b_internal, title="Libro", author="Autor"),
        }

        filtered = duplicate_engine.filtrar_dobles_entre_carpetas(
            [cross, inside_a, inside_b],
            folder_a,
            folder_b,
        )

        self.assertEqual(filtered, [cross])

    def test_between_folders_filter_accepts_reversed_pair_order(self):
        folder_a = self.root / "base"
        folder_b = self.root / "compare"
        a_match = self.make_file("base/Autor - Libro.epub", "a")
        b_match = self.make_file("compare/Autor - Libro.pdf", "b")
        pair = {
            "tipo": "duplicado_de_titulo",
            "archivo_a": self.item(b_match, title="Libro", author="Autor"),
            "archivo_b": self.item(a_match, title="Libro", author="Autor"),
        }

        self.assertTrue(duplicate_engine.doble_entre_carpetas(pair, folder_a, folder_b))


if __name__ == "__main__":
    unittest.main()

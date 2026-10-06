import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import library_core
from core.catalog_store import CatalogStore


class CatalogStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = CatalogStore(self.root / "catalog.sqlite3")

    def tearDown(self):
        self.temp.cleanup()

    def test_separates_work_edition_and_file(self):
        first = self.root / "Alicia Autor - Libro.epub"
        second = self.root / "Alicia Autor - Libro.pdf"
        first.write_bytes(b"epub")
        second.write_bytes(b"pdf")
        rows = [
            {
                "ruta": str(first), "nombre": first.name, "autor": "Alicia Autor",
                "titulo": "Libro", "isbn": "9780307474728", "extension": ".epub",
                "tamano_bytes": 4, "mtime": 1, "sha256": "a" * 64,
            },
            {
                "ruta": str(second), "nombre": second.name, "autor": "Alicia Autor",
                "titulo": "Libro", "isbn": "9780307474728", "extension": ".pdf",
                "tamano_bytes": 3, "mtime": 2, "sha256": "b" * 64,
            },
        ]

        stats = self.store.sync_index({"archivos": rows})

        self.assertEqual(stats, {"works": 1, "editions": 1, "files": 2, "present_files": 2})
        record = self.store.record_for_path(first)
        self.assertEqual(record["title"], "Libro")
        self.assertEqual(record["author"], "Alicia Autor")
        self.assertEqual(record["isbn"], "9780307474728")

    def test_missing_rows_are_retained_but_marked_not_present(self):
        first = self.root / "Autor - Uno.epub"
        second = self.root / "Autor - Dos.epub"
        first.write_bytes(b"one")
        second.write_bytes(b"two")
        make = lambda path, title: {
            "ruta": str(path), "nombre": path.name, "autor": "Autor", "titulo": title,
            "extension": ".epub", "tamano_bytes": 3, "mtime": 1,
        }
        self.store.sync_index({"archivos": [make(first, "Uno"), make(second, "Dos")]})

        stats = self.store.sync_index({"archivos": [make(first, "Uno")]})

        self.assertEqual(stats["files"], 2)
        self.assertEqual(stats["present_files"], 1)
        self.assertEqual(self.store.record_for_path(second)["present"], 0)

    def test_manual_and_provenance_data_survive_resync(self):
        path = self.root / "Autor - Libro.epub"
        path.write_bytes(b"book")
        row = {
            "ruta": str(path), "nombre": path.name, "autor": "Autor", "titulo": "Libro",
            "extension": ".epub", "manual_lock": True, "confianza_global": 91,
            "provenance": {"titulo": {"source": "EPUB", "confidence": 96}},
        }
        self.store.sync_index({"archivos": [row]})
        self.store.sync_index({"archivos": [{**row, "provenance": {}}]})

        record = self.store.record_for_path(path)
        self.assertEqual(record["manual_lock"], 1)
        self.assertEqual(record["confidence"], 91)
        self.assertEqual(record["provenance"]["titulo"]["source"], "EPUB")

    def test_manual_correction_updates_catalog_without_touching_file(self):
        path = self.root / "Old - Name.epub"
        path.write_bytes(b"unchanged")
        index = {"archivos": [{"ruta": str(path), "nombre": path.name, "extension": ".epub"}]}
        original = path.read_bytes()
        with (
            patch.object(library_core, "INDICE_JSON", self.root / "index.json"),
            patch.object(library_core, "CATALOG_DB", self.root / "manual.sqlite3"),
        ):
            updated = library_core.aplicar_correccion_manual_indice(
                path,
                {"titulo": "Nombre correcto", "autor": "Autora", "tags": "favorito, ensayo"},
                index,
            )
            record = library_core.registro_catalogo_para_ruta(path)

        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(updated["archivos"][0]["titulo"], "Nombre correcto")
        self.assertTrue(updated["archivos"][0]["manual_lock"])
        self.assertEqual(record["title"], "Nombre correcto")
        self.assertEqual(record["provenance"]["titulo"]["source"], "usuario")

    def test_organizing_a_favorite_does_not_lock_book_identity(self):
        path = self.root / "Autor - Libro.epub"
        path.write_bytes(b"unchanged")
        index = {
            "archivos": [{
                "ruta": str(path), "nombre": path.name, "extension": ".epub",
                "confianza_global": 72,
            }]
        }
        with (
            patch.object(library_core, "INDICE_JSON", self.root / "favorite-index.json"),
            patch.object(library_core, "CATALOG_DB", self.root / "favorite.sqlite3"),
        ):
            updated = library_core.aplicar_correccion_manual_indice(path, {"favorite": True}, index)

        row = updated["archivos"][0]
        self.assertTrue(row["favorite"])
        self.assertNotIn("manual_lock", row)
        self.assertEqual(row["confianza_global"], 72)
        self.assertEqual(row["provenance"]["favorite"]["source"], "usuario")


if __name__ == "__main__":
    unittest.main()

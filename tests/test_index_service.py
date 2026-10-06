import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import library_core
from core.document_context import DocumentContext
from core.index_service import merge_persistent_metadata, update_paths


class IncrementalIndexTests(unittest.TestCase):
    def test_only_changed_paths_are_rebuilt_and_removed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            keep = root / "keep.epub"
            changed = root / "changed.epub"
            removed = root / "removed.epub"
            keep.write_bytes(b"keep")
            changed.write_bytes(b"new")
            calls = []

            def build(path, _title):
                calls.append(path)
                return {"ruta": str(path), "nombre": path.name, "sha256": path.read_bytes().hex()}

            index = {"archivos": [
                {"ruta": str(keep), "nombre": keep.name, "sha256": "preserved"},
                {"ruta": str(changed), "nombre": changed.name, "sha256": "old"},
                {"ruta": str(removed), "nombre": removed.name, "sha256": "gone"},
            ]}
            updated = update_paths(
                index, [changed, removed], library_root=root, build_item=build,
            )

            rows = {Path(item["ruta"]).name: item for item in updated["archivos"]}
            self.assertEqual(calls, [changed])
            self.assertEqual(rows["keep.epub"]["sha256"], "preserved")
            self.assertEqual(rows["changed.epub"]["sha256"], b"new".hex())
            self.assertNotIn("removed.epub", rows)

    def test_paths_outside_library_and_ignored_paths_are_not_added(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            root = base / "library"
            root.mkdir()
            outside = base / "outside.epub"
            ignored = root / ".trash_manageyourlibrary" / "trash.epub"
            outside.write_bytes(b"outside")
            ignored.parent.mkdir()
            ignored.write_bytes(b"trash")

            updated = update_paths(
                {"archivos": []}, [outside, ignored], library_root=root,
                build_item=lambda path, _title: {"ruta": str(path)},
                ignore_path=lambda path: ".trash_manageyourlibrary" in path.parts,
            )

            self.assertEqual(updated["archivos"], [])

    def test_refresh_preserves_catalog_metadata_and_manual_corrections(self):
        fresh = {"ruta": "C:/books/book.epub", "nombre": "book.epub", "autor": "Automático"}
        previous = {
            **fresh,
            "titulo": "Título confirmado",
            "autor": "Autora confirmada",
            "isbn": "9780307474728",
            "manual_lock": True,
            "provenance": {"titulo": {"source": "usuario", "confidence": 100}},
        }

        merged = merge_persistent_metadata(
            fresh,
            previous,
            {"titulo": "Otro título", "autor": "Otro autor", "cover_url": "https://example.test/cover.jpg"},
        )

        self.assertEqual(merged["titulo"], "Título confirmado")
        self.assertEqual(merged["autor"], "Autora confirmada")
        self.assertEqual(merged["isbn"], "9780307474728")
        self.assertEqual(merged["cover_url"], "https://example.test/cover.jpg")


class DocumentContextTests(unittest.TestCase):
    def test_cache_key_reuses_one_full_hash_and_detects_changes(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "book.epub"
            path.write_bytes(b"book")
            context = DocumentContext(path)

            with patch(
                "core.document_context.calcular_sha256_archivo",
                wraps=library_core.calcular_hash,
            ) as hasher:
                first = library_core._file_key_para_cache(path, context)
                second = library_core._file_key_para_cache(path, context)
                self.assertEqual(first, second)
                self.assertEqual(hasher.call_count, 1)

            path.write_bytes(b"changed content")
            with self.assertRaises(RuntimeError):
                context.assert_unchanged()


if __name__ == "__main__":
    unittest.main()

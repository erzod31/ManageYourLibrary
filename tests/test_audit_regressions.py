"""Regression coverage for the eight defects reproduced on 2026-09-30."""
import errno
import io
import os
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

import library_core as core
from core import file_transactions as tx
from core.catalog_store import CatalogStore
from core.cover_service import CoverService
from core.index_service import update_paths
from core.library_view_model import LibraryViewIndex, display_item, item_is_favorite
from core.undo_history import registrar_undo
from ui.workspace import Workspace


class AuditRegressionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.library = self.root / "library"
        self.library.mkdir()
        self.data = self.root / "state"
        self.journal = self.data / "journal.jsonl"
        self.book = self.library / "incorrect.epub"
        self.book.write_bytes(b"synthetic book")

    def tearDown(self):
        self.temp.cleanup()

    def scan_context(self):
        return patch.multiple(core, APP_DATA=self.data, FINAL=self.library,
                              INDICE_JSON=self.data / "index.json", CATALOG_DB=self.data / "catalog.sqlite3")

    def move(self, source, name):
        return tx.mover_a_final(source, name, self.library, journal_path=self.journal, app_data=self.data)

    def test_concurrent_destination_is_never_overwritten(self):
        source = self.root / "incoming.epub"
        source.write_bytes(b"incoming")
        target = self.library / "race.epub"
        original_update = tx.actualizar_transaccion_archivo

        def inject(*args, **kwargs):
            if args[3] == "validated":
                target.write_bytes(b"other book")
            return original_update(*args, **kwargs)

        with patch.object(tx, "actualizar_transaccion_archivo", side_effect=inject):
            with self.assertRaises(FileExistsError):
                self.move(source, target.name)
        self.assertEqual(target.read_bytes(), b"other book")
        self.assertEqual(source.read_bytes(), b"incoming")
        self.assertEqual(tx.leer_jsonl(self.journal)[-1]["state"], "failed")

    def test_cross_volume_fallback_copies_exclusively(self):
        source = self.root / "incoming.epub"
        source.write_bytes(b"incoming")
        operation = "rename" if os.name == "nt" else "link"
        with patch.object(tx.os, operation, side_effect=OSError(errno.EXDEV, "cross volume")):
            target = self.move(source, "cross.epub")
        self.assertFalse(source.exists())
        self.assertEqual(target.read_bytes(), b"incoming")

    def test_cross_volume_fallback_rejects_occupied_target(self):
        target = self.library / "occupied.epub"
        target.write_bytes(b"keep me")
        operation = "rename" if os.name == "nt" else "link"
        with patch.object(tx.os, operation, side_effect=OSError(errno.EXDEV, "cross volume")):
            with self.assertRaises(FileExistsError):
                tx._move_no_replace(self.book, target, self.book.stat().st_size, core.calcular_hash(self.book))
        self.assertEqual(target.read_bytes(), b"keep me")
        self.assertTrue(self.book.exists())

    def test_source_changed_during_journaling_is_not_moved(self):
        original_update = tx.actualizar_transaccion_archivo

        def inject(*args, **kwargs):
            if args[3] == "validated":
                self.book.write_bytes(b"replacement content")
            return original_update(*args, **kwargs)

        with patch.object(tx, "actualizar_transaccion_archivo", side_effect=inject):
            with self.assertRaises(tx.FileTransactionError):
                self.move(self.book, "changed.epub")
        self.assertTrue(self.book.exists())
        self.assertFalse((self.library / "changed.epub").exists())

    def make_undo(self):
        destination = self.move(self.book, "moved.epub")
        row = registrar_undo(self.data / "undo.jsonl", self.data, "batch", "move", self.book, destination)
        return destination, row

    def test_undo_rejects_replaced_content_and_keeps_record(self):
        destination, row = self.make_undo()
        destination.write_bytes(b"unrelated replacement")
        ok, _ = tx.restaurar_accion_undo(row, journal_path=self.journal, app_data=self.data)
        self.assertFalse(ok)
        self.assertEqual(destination.read_bytes(), b"unrelated replacement")
        self.assertFalse(self.book.exists())
        self.assertEqual(tx.leer_jsonl(self.journal)[-1]["state"], "needs_review")
        self.assertEqual(tx.leer_jsonl(self.data / "undo.jsonl")[0]["sha256"], row["sha256"])

    def test_verified_undo_succeeds(self):
        destination, row = self.make_undo()
        ok, _ = tx.restaurar_accion_undo(row, journal_path=self.journal, app_data=self.data)
        self.assertTrue(ok)
        self.assertEqual(self.book.read_bytes(), b"synthetic book")
        self.assertFalse(destination.exists())

    def test_legacy_undo_uses_journal_identity(self):
        destination, row = self.make_undo()
        del row["sha256"]
        ok, _ = tx.restaurar_accion_undo(row, journal_path=self.journal, app_data=self.data)
        self.assertTrue(ok)
        self.assertFalse(destination.exists())

    def test_unverifiable_legacy_undo_is_not_automatic(self):
        row = {"origen": str(self.root / "old.epub"), "destino": str(self.book)}
        ok, message = tx.restaurar_accion_undo(row, journal_path=self.journal, app_data=self.data)
        self.assertFalse(ok)
        self.assertIn("revisión", message)
        self.assertTrue(self.book.exists())

    def test_ambiguous_legacy_journal_requires_review(self):
        destination, row = self.make_undo()
        del row["sha256"]
        tx.iniciar_transaccion_archivo(self.journal, self.data, "move", self.book, destination)
        tx.registrar_evento_transaccion(self.journal, self.data, "another", "move", "committed",
                                       self.book, destination, hash_archivo="other digest")
        ok, _ = tx.restaurar_accion_undo(row, journal_path=self.journal, app_data=self.data)
        self.assertFalse(ok)
        self.assertTrue(destination.exists())

    def test_full_rescan_preserves_all_manual_fields_and_explicit_empty_values(self):
        with self.scan_context(), patch.object(core, "biblioteca_configurada", return_value=True), \
                patch.object(core, "buscar_libros_final", return_value=[self.book]):
            initial = core.crear_o_actualizar_indice()
            changes = {"titulo": "Corrected title", "autor": "Corrected author", "serie": "",
                       "tags": [], "favorite": False, "idioma": "es", "isbn": "9780306406157"}
            core.aplicar_correccion_manual_indice(self.book, changes, initial)
            row = core.crear_o_actualizar_indice()["archivos"][0]
        for key, value in changes.items():
            self.assertEqual(row[key], value, key)
        self.assertTrue(row["manual_lock"])
        self.assertEqual(row["provenance"]["titulo"]["source"], "usuario")

    def test_replaced_file_does_not_inherit_confirmed_metadata(self):
        with self.scan_context(), patch.object(core, "biblioteca_configurada", return_value=True), \
                patch.object(core, "buscar_libros_final", return_value=[self.book]):
            initial = core.crear_o_actualizar_indice()
            core.aplicar_correccion_manual_indice(self.book, {"titulo": "Old identity"}, initial)
            stat = self.book.stat()
            self.book.write_bytes(b"different book")
            os.utime(self.book, ns=(stat.st_atime_ns, stat.st_mtime_ns))
            row = core.crear_o_actualizar_indice()["archivos"][0]
        self.assertNotIn("manual_lock", row)
        self.assertNotEqual(row.get("titulo"), "Old identity")

    def test_incremental_replacement_does_not_inherit_metadata(self):
        old = {"ruta": str(self.book), "sha256": "old", "manual_lock": True, "titulo": "Old"}
        updated = update_paths({"archivos": [old]}, [self.book], library_root=self.library,
                               build_item=lambda path, name: {"ruta": str(path), "sha256": "new"})
        self.assertNotIn("manual_lock", updated["archivos"][0])

    def test_display_and_search_use_saved_title(self):
        row = {"ruta": str(self.book), "titulo": "Corrected title", "autor": "Author"}
        self.assertEqual(display_item(row)["titulo"], "Corrected title")
        self.assertEqual(len(LibraryViewIndex([row]).filter("Corrected title")), 1)
        self.assertEqual(display_item({"ruta": str(self.book), "titulo_real": "Extracted title"})["titulo"], "Extracted title")

    def test_catalog_updates_same_isbn_and_protects_locked_identity(self):
        store = CatalogStore(self.data / "catalog.sqlite3")
        row = {"ruta": str(self.book), "titulo": "Title", "autor": "Author", "isbn": "9780306406157",
               "serie": "Old", "idioma": "en", "editorial": "Old", "anio": "2000", "tags": ["old"]}
        store.sync_index({"archivos": [row]})
        corrected = {**row, "serie": "New", "idioma": "es", "editorial": "New", "anio": "2020",
                     "tags": ["new"], "manual_lock": True}
        store.sync_index({"archivos": [corrected]})
        record = store.record_for_path(self.book)
        self.assertEqual((record["series"], record["language"], record["publisher"], record["publication_year"]),
                         ("New", "es", "New", "2020"))
        self.assertEqual(record["tags"], ["new"])
        self.assertEqual(record["manual_lock"], 1)
        store.sync_index({"archivos": [row]})
        record = store.record_for_path(self.book)
        self.assertEqual(record["language"], "es")
        self.assertEqual(record["series"], "New")
        self.assertEqual(record["manual_lock"], 1)

    def test_catalog_accepts_explicit_clear_of_series_and_tags(self):
        store = CatalogStore(self.data / "catalog.sqlite3")
        row = {"ruta": str(self.book), "titulo": "Title", "serie": "Saga", "tags": ["tag"]}
        store.sync_index({"archivos": [row]})
        store.sync_index({"archivos": [{**row, "serie": "", "tags": [], "manual_lock": True}]})
        record = store.record_for_path(self.book)
        self.assertEqual(record["series"], "")
        self.assertEqual(record["tags"], [])

    def test_ui_can_remove_legacy_favorites(self):
        for alias in ("favorito", "is_favorite"):
            workspace = object.__new__(Workspace)
            workspace.selected_item = display_item({"ruta": str(self.book), alias: True})
            workspace.app = SimpleNamespace(trabajando=False, indice={"archivos": [dict(workspace.selected_item)]}, estado=lambda text: None)
            workspace.refresh_library = lambda: None
            workspace.select_item = lambda item: setattr(workspace, "selected_item", item)
            with patch.object(core, "guardar_indice"):
                workspace.toggle_selected_favorite()
            self.assertFalse(item_is_favorite(workspace.selected_item), alias)
            self.assertNotIn(alias, workspace.selected_item)

    def test_offline_cover_is_retried_online_and_then_cached(self):
        source = self.root / "book.mobi"
        source.write_bytes(b"no local cover")
        url = "https://covers.openlibrary.org/b/isbn/9780306406157-M.jpg"
        data = io.BytesIO()
        Image.new("RGB", (8, 8), "red").save(data, "PNG")
        response = SimpleNamespace(status=200, headers={"Content-Type": "image/png"},
                                   geturl=lambda: url, read=lambda limit: data.getvalue())
        class Context:
            def __enter__(self):
                return response
            def __exit__(self, *args):
                return False
        calls = []
        service = CoverService(self.data / "covers", urlopen_func=lambda *args, **kwargs: calls.append(1) or Context())
        with patch.dict(os.environ, {"MANAGE_YOUR_LIBRARY_OFFLINE": "1"}):
            self.assertIsNone(service.thumbnail_path(source, url))
        with patch.dict(os.environ, {"MANAGE_YOUR_LIBRARY_OFFLINE": "0"}):
            result = service.thumbnail_path(source, url)
            self.assertTrue(result.exists())
            self.assertEqual(service.thumbnail_path(source, url), result)
        self.assertEqual(calls, [1])

    def test_new_view_can_request_cover_while_old_view_is_pending(self):
        workspace = object.__new__(Workspace)
        workspace.cover_generation = 0
        workspace.cover_pending_lock = threading.Lock()
        workspace.cover_pending = set()
        jobs, delivered = [], []
        workspace.cover_executor = SimpleNamespace(submit=jobs.append)
        workspace.cover_service = SimpleNamespace(thumbnail_path=lambda *args, **kwargs: "thumbnail.webp")
        workspace.app = SimpleNamespace(_encolar_ui=lambda callback, *args: delivered.append(args[-1]))
        workspace._request_cover(None, self.book)
        workspace._request_cover(None, self.book)
        self.assertEqual(len(jobs), 1)
        workspace.cover_generation = 1
        workspace._request_cover(None, self.book)
        self.assertEqual(len(jobs), 2)
        for job in jobs:
            job()
        # Obsolete jobs are discarded before decoding/downloading a cover.
        self.assertEqual(delivered, [1])
        self.assertEqual(workspace.cover_pending, set())

    def test_old_remote_miss_does_not_block_for_six_hours(self):
        source = self.root / "book.mobi"
        source.write_bytes(b"no local cover")
        calls = []
        def unavailable(*args, **kwargs):
            calls.append(1)
            raise OSError("temporary network failure")
        cache = self.data / "covers"
        service = CoverService(cache, urlopen_func=unavailable)
        url = "https://covers.openlibrary.org/b/isbn/9780306406157-M.jpg"
        with patch.dict(os.environ, {"MANAGE_YOUR_LIBRARY_OFFLINE": "0"}):
            service.thumbnail_path(source, url)
            service.thumbnail_path(source, url)
            self.assertEqual(len(calls), 1)
            marker = next(cache.glob("*.miss"))
            os.utime(marker, (marker.stat().st_mtime - 31, marker.stat().st_mtime - 31))
            service.thumbnail_path(source, url)
        self.assertEqual(len(calls), 2)


if __name__ == "__main__":
    unittest.main()

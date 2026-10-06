import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import library_core
from core import file_transactions, index_store, normalizer, undo_history


class CoreRefactorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.app_data = self.root / "app_data"
        self.journal = self.app_data / "file_transactions.jsonl"
        self.manifest = self.app_data / "trash_manifest.jsonl"

    def tearDown(self):
        self.tmp.cleanup()

    def test_normalizer_keeps_unicode_titles_searchable(self):
        self.assertEqual(normalizer.normalizar_texto("El niño ñandú.epub"), "el nino nandu")
        self.assertEqual(normalizer.normalizar_titulo_para_dobles_texto("El niño ñandú.epub"), "el nino nandu")
        self.assertTrue(normalizer.normalizar_texto("\u4e09\u4f53 \u5218\u6148\u6b23"))

    def test_index_store_writes_json_atomically(self):
        index_path = self.app_data / "library_index.json"
        data = {"creado": "now", "archivos": [{"nombre": "Libro.epub"}]}

        index_store.guardar_indice(index_path, data)

        self.assertEqual(index_store.cargar_indice(index_path), data)
        self.assertEqual(index_store.cargar_indice(self.app_data / "missing.json"), {"creado": None, "archivos": []})

    def test_undo_history_returns_last_open_batch_and_marks_undone(self):
        undo_path = self.app_data / "undo.jsonl"
        batch = undo_history.nuevo_batch_id("test")

        undo_history.registrar_undo(undo_path, self.app_data, batch, "move", "a.epub", "b.epub", "detalle")
        found_batch, actions = undo_history.obtener_ultima_accion_undo(undo_path)
        self.assertEqual(found_batch, batch)
        self.assertEqual(len(actions), 1)

        undo_history.mark_action_undone(undo_path, self.app_data, batch)
        found_batch, actions = undo_history.obtener_ultima_accion_undo(undo_path)
        self.assertIsNone(found_batch)
        self.assertEqual(actions, [])

    def test_quarantine_moves_file_and_writes_manifest(self):
        library = self.root / "library"
        source = library / "Libro.epub"
        source.parent.mkdir(parents=True)
        source.write_text("contenido", encoding="utf-8")

        quarantined = file_transactions.descartar_archivo_seguro(
            source,
            library,
            motivo="duplicate",
            journal_path=self.journal,
            app_data=self.app_data,
            manifest_path=self.manifest,
            library_root=library,
        )

        self.assertFalse(source.exists())
        self.assertTrue(quarantined.exists())
        self.assertTrue((library / ".trash_manageyourlibrary" / "manifest.jsonl").exists())
        self.assertTrue(self.manifest.exists())

    def test_replace_rollback_restores_old_file_when_new_move_fails(self):
        library = self.root / "library"
        library.mkdir()
        old_file = library / "Libro.epub"
        old_file.write_text("old", encoding="utf-8")
        new_file = self.root / "incoming.epub"
        new_file.write_text("new", encoding="utf-8")

        real_move = file_transactions._move_no_replace
        calls = []

        def flaky_move(src, dst, size, digest):
            calls.append((src, dst))
            if len(calls) == 2:
                raise PermissionError("blocked")
            return real_move(src, dst, size, digest)

        with patch.object(file_transactions, "_move_no_replace", side_effect=flaky_move):
            with self.assertRaises(PermissionError):
                file_transactions.reemplazar_archivo_transaccional(
                    new_file,
                    old_file,
                    library,
                    motivo="replace test",
                    journal_path=self.journal,
                    app_data=self.app_data,
                    manifest_path=self.manifest,
                )

        self.assertTrue(old_file.exists())
        self.assertEqual(old_file.read_text(encoding="utf-8"), "old")
        self.assertTrue(new_file.exists())

    def test_rename_in_place_stays_in_original_folder(self):
        folder = self.root / "metadata"
        folder.mkdir()
        source = folder / "old.epub"
        source.write_text("book", encoding="utf-8")

        renamed = file_transactions.renombrar_en_sitio_seguro(
            source,
            "new.epub",
            motivo="metadata",
            journal_path=self.journal,
            app_data=self.app_data,
        )

        self.assertEqual(renamed.parent, folder)
        self.assertFalse(source.exists())
        self.assertTrue(renamed.exists())


class LibraryCoreIsolatedWorkflowTests(unittest.TestCase):
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
        self.library = self.root / "temp_test_library"
        self.input_dir = self.root / "temp_test_input"
        self.app_data = self.root / "temp_test_app_data"
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

    def make_book(self, folder, name, content="contenido"):
        path = Path(folder) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def read_journal_states(self):
        return [
            (item.get("type"), item.get("state"))
            for item in file_transactions.leer_jsonl(library_core.FILE_TRANSACTION_JOURNAL)
        ]

    def test_add_books_primitives_move_to_library_update_index_and_register_undo(self):
        source = self.make_book(self.input_dir, "Autor - Titulo (2024).epub")
        batch = library_core.nuevo_batch_id("agregar")

        destination = library_core.mover_a_final(source, source.name, motivo="validacion add")
        library_core.registrar_undo(batch, "mover", source, destination, "validacion add")
        index = library_core.crear_o_actualizar_indice()

        self.assertFalse(source.exists())
        self.assertTrue(destination.exists())
        self.assertEqual(destination.parent, self.library)
        self.assertTrue(any(item["ruta"] == str(destination) for item in index["archivos"]))
        self.assertEqual(library_core.obtener_ultima_accion_undo()[0], batch)
        self.assertIn(("move_to_library", "committed"), self.read_journal_states())

    def test_add_books_primitives_low_confidence_goes_to_review(self):
        source = self.make_book(self.input_dir, "Dudoso.epub")
        batch = library_core.nuevo_batch_id("agregar")

        destination = library_core.mover_a_revisar_nuevamente(source, motivo="baja confianza")
        library_core.registrar_undo(batch, "mover", source, destination, "baja confianza")

        self.assertFalse(source.exists())
        self.assertEqual(destination.parent, self.library / "PARA REVISAR NUEVAMENTE")
        self.assertTrue(destination.exists())
        self.assertIn(("move_to_review", "committed"), self.read_journal_states())

    def test_exact_duplicate_is_detected_and_discarded_to_quarantine(self):
        existing = self.make_book(self.library, "Autor - Duplicado.epub", "mismo contenido")
        incoming = self.make_book(self.input_dir, "Autor - Duplicado copia.epub", "mismo contenido")
        index = library_core.crear_o_actualizar_indice()

        result = library_core.verificar_libro(incoming, index)
        quarantined = library_core.descartar_archivo_seguro(
            incoming,
            motivo="duplicado exacto fixture",
            conservado=existing,
        )

        self.assertEqual(result["estado"], "duplicado_exacto")
        self.assertFalse(incoming.exists())
        self.assertTrue(quarantined.exists())
        self.assertIn(".trash_manageyourlibrary", [part.lower() for part in quarantined.parts])
        self.assertIn(("quarantine", "committed"), self.read_journal_states())

    def test_index_ignores_quarantine_folder(self):
        kept = self.make_book(self.library, "Autor - Visible.epub", "visible")
        trash = self.library / ".trash_manageyourlibrary"
        discarded = self.make_book(trash, "Autor - Oculto.epub", "oculto")

        index = library_core.crear_o_actualizar_indice()
        indexed_paths = {item["ruta"] for item in index["archivos"]}

        self.assertIn(str(kept), indexed_paths)
        self.assertNotIn(str(discarded), indexed_paths)

    def test_search_metadata_rename_in_place_registers_undo_and_does_not_touch_library(self):
        source = self.make_book(self.input_dir, "viejo.epub")
        batch = library_core.nuevo_batch_id("renombrar")

        renamed = library_core.renombrar_en_sitio_seguro(source, "nuevo.epub", motivo="metadata fixture")
        library_core.registrar_undo(batch, "renombrar", source, renamed, "metadata fixture")

        self.assertEqual(renamed.parent, self.input_dir)
        self.assertTrue(renamed.exists())
        self.assertFalse((self.library / "nuevo.epub").exists())
        self.assertFalse((self.library / ".trash_manageyourlibrary").exists())
        self.assertEqual(library_core.obtener_ultima_accion_undo()[0], batch)

        undo_batch, actions = library_core.obtener_ultima_accion_undo()
        ok, _message = library_core.restaurar_accion_undo(actions[0])
        library_core.mark_action_undone(undo_batch)
        self.assertTrue(ok)
        self.assertTrue(source.exists())
        self.assertFalse(renamed.exists())

    def test_rename_in_place_uses_collision_safe_name(self):
        source = self.make_book(self.input_dir, "viejo.epub", "old")
        existing = self.make_book(self.input_dir, "nuevo.epub", "existing")

        renamed = library_core.renombrar_en_sitio_seguro(source, existing.name, motivo="collision fixture")

        self.assertEqual(existing.read_text(encoding="utf-8"), "existing")
        self.assertEqual(renamed.parent, self.input_dir)
        self.assertEqual(renamed.name, "nuevo_2.epub")

    def test_missing_file_move_fails_and_is_journaled(self):
        missing = self.input_dir / "desaparecido.epub"

        with self.assertRaises(Exception):
            library_core.mover_a_final(missing, missing.name, motivo="missing fixture")

        self.assertIn(("move_to_library", "failed"), self.read_journal_states())

    def test_pending_journal_operation_is_recovered_without_deleting_files(self):
        source = self.make_book(self.input_dir, "pendiente.epub")
        destination = self.library / source.name
        op_id = library_core.iniciar_transaccion_archivo(
            "move_to_library",
            source,
            destination,
            motivo="pending fixture",
        )

        incompletas = library_core.recuperar_transacciones_archivo_pendientes()
        states = self.read_journal_states()

        self.assertTrue(source.exists())
        self.assertTrue(any(item.get("id") == op_id for item in incompletas))
        self.assertIn(("move_to_library", "rolled_back"), states)

    def test_corrupt_index_json_returns_safe_default(self):
        library_core.INDICE_JSON.parent.mkdir(parents=True, exist_ok=True)
        library_core.INDICE_JSON.write_text("{json roto", encoding="utf-8")

        self.assertEqual(library_core.cargar_indice(), {"creado": None, "archivos": []})


if __name__ == "__main__":
    unittest.main()

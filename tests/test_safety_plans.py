import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core import file_transactions, undo_history
from core.cancellation import CancellationToken
from core.operation_plans import OperationPlanStore


class SafetyRegressionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.app_data = self.root / "app"
        self.journal = self.app_data / "journal.jsonl"
        self.manifest = self.app_data / "manifest.jsonl"

    def tearDown(self):
        self.tmp.cleanup()

    def test_journal_failure_prevents_file_move(self):
        source = self.root / "source.epub"
        source.write_bytes(b"book")
        destination = self.root / "library" / source.name

        with (
            patch.object(file_transactions, "append_jsonl_durable", side_effect=OSError("disk full")),
            self.assertRaises(file_transactions.JournalWriteError),
        ):
            file_transactions.mover_a_final(
                source,
                source.name,
                destination.parent,
                journal_path=self.journal,
                app_data=self.app_data,
            )

        self.assertTrue(source.exists())
        self.assertFalse(destination.exists())

    def test_recovery_verifies_completed_physical_move(self):
        source = self.root / "incoming.epub"
        destination = self.root / "library" / source.name
        source.write_bytes(b"content")
        expected_hash = file_transactions.calcular_sha256_archivo(source)
        op_id = file_transactions.iniciar_transaccion_archivo(
            self.journal, self.app_data, "move_to_library", source, destination,
            hash_archivo=expected_hash,
        )
        destination.parent.mkdir()
        source.replace(destination)

        file_transactions.recuperar_transacciones_archivo_pendientes(self.journal, self.app_data)
        latest = [row for row in file_transactions.leer_jsonl(self.journal) if row["id"] == op_id][-1]

        self.assertEqual(latest["state"], "committed_recovered")

    def test_recovery_rejects_destination_with_wrong_hash(self):
        source = self.root / "incoming.epub"
        destination = self.root / "library" / source.name
        source.write_bytes(b"expected-content")
        expected_hash = file_transactions.calcular_sha256_archivo(source)
        op_id = file_transactions.iniciar_transaccion_archivo(
            self.journal,
            self.app_data,
            "move_to_library",
            source,
            destination,
            hash_archivo=expected_hash,
        )
        destination.parent.mkdir()
        source.replace(destination)
        destination.write_bytes(b"different-content")

        file_transactions.recuperar_transacciones_archivo_pendientes(self.journal, self.app_data)
        latest = [row for row in file_transactions.leer_jsonl(self.journal) if row["id"] == op_id][-1]

        self.assertEqual(latest["state"], "needs_review")
        self.assertTrue(destination.exists())

    def test_failed_destination_verification_rolls_move_back(self):
        source = self.root / "incoming.epub"
        destination = self.root / "library" / source.name
        source.write_bytes(b"content")
        expected_hash = file_transactions.calcular_sha256_archivo(source)

        with (
            patch.object(
                file_transactions,
                "_validar_destino",
                side_effect=[file_transactions.FileTransactionError("verification failed"), None],
            ),
            self.assertRaises(file_transactions.VerifiedMoveError),
        ):
            file_transactions.mover_a_final(
                source,
                source.name,
                destination.parent,
                journal_path=self.journal,
                app_data=self.app_data,
            )

        self.assertEqual(source.read_bytes(), b"content")
        self.assertFalse(destination.exists())
        rows = file_transactions.leer_jsonl(self.journal)
        self.assertIn("rolled_back", [row["state"] for row in rows])
        self.assertEqual(rows[-1]["state"], "failed")
        self.assertEqual(rows[-1]["hash"], expected_hash)

    def test_corrupt_journal_line_warns_or_fails_in_strict_mode(self):
        self.journal.parent.mkdir(parents=True)
        self.journal.write_text('{"id": "ok", "state": "pending"}\n{broken-json\n', encoding="utf-8")

        with self.assertWarns(file_transactions.JournalCorruptionWarning):
            rows = file_transactions.leer_jsonl(self.journal)
        self.assertEqual(rows, [{"id": "ok", "state": "pending"}])
        with self.assertRaises(file_transactions.FileTransactionError):
            file_transactions.leer_jsonl(self.journal, strict=True)

    def test_recovery_restores_old_file_after_interrupted_replacement(self):
        incoming = self.root / "incoming.epub"
        destination = self.root / "library" / "book.epub"
        quarantine = self.root / "library" / ".trash_manageyourlibrary" / "book.epub"
        incoming.write_bytes(b"new")
        destination.parent.mkdir()
        destination.write_bytes(b"old")
        quarantine.parent.mkdir()
        destination.replace(quarantine)
        op_id = file_transactions.iniciar_transaccion_archivo(
            self.journal, self.app_data, "replace_existing", incoming, destination,
            cuarentena=quarantine, hash_archivo=file_transactions.calcular_sha256_archivo(incoming),
        )
        file_transactions.actualizar_transaccion_archivo(
            self.journal, self.app_data, op_id, "old_quarantined", "replace_existing",
            incoming, destination, quarantine, hash_archivo=file_transactions.calcular_sha256_archivo(incoming),
        )

        file_transactions.recuperar_transacciones_archivo_pendientes(self.journal, self.app_data)
        latest = [row for row in file_transactions.leer_jsonl(self.journal) if row["id"] == op_id][-1]

        self.assertEqual(latest["state"], "rolled_back_recovered")
        self.assertEqual(destination.read_bytes(), b"old")
        self.assertTrue(incoming.exists())
        self.assertFalse(quarantine.exists())

    def test_partial_undo_keeps_only_failed_items_pending(self):
        undo_path = self.app_data / "undo.jsonl"
        batch = undo_history.nuevo_batch_id("batch")
        first = undo_history.registrar_undo(undo_path, self.app_data, batch, "move", "a", "b")
        second = undo_history.registrar_undo(undo_path, self.app_data, batch, "move", "c", "d")
        undo_history.mark_undo_item_restored(undo_path, self.app_data, batch, second)

        found_batch, pending = undo_history.obtener_ultima_accion_undo(undo_path)

        self.assertEqual(found_batch, batch)
        self.assertEqual([item["action_id"] for item in pending], [first["action_id"]])

    def test_corrupt_undo_line_is_preserved_and_reported(self):
        undo_path = self.app_data / "undo.jsonl"
        undo_path.parent.mkdir(parents=True)
        undo_path.write_text(
            '{"batch_id":"safe","action_id":"one","tipo":"move"}\n{broken\n',
            encoding="utf-8",
        )

        with self.assertWarns(undo_history.UndoHistoryCorruptionWarning):
            batch, pending = undo_history.obtener_ultima_accion_undo(undo_path)

        self.assertEqual(batch, "safe")
        self.assertEqual([item["action_id"] for item in pending], ["one"])
        self.assertIn("{broken", undo_path.read_text(encoding="utf-8"))

    def test_batch_ids_do_not_collide(self):
        self.assertNotEqual(undo_history.nuevo_batch_id("x"), undo_history.nuevo_batch_id("x"))


class OperationPlanTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.store = OperationPlanStore(self.root / "plans.sqlite3")

    def tearDown(self):
        self.tmp.cleanup()

    def test_preview_does_not_modify_source_and_apply_is_resumable(self):
        first = self.root / "first.epub"
        second = self.root / "second.epub"
        first.write_bytes(b"one")
        second.write_bytes(b"two")
        plan = self.store.create_plan("import", [
            {"action": "move", "source": first, "destination": self.root / "out" / first.name},
            {"action": "move", "source": second, "destination": self.root / "out" / second.name},
        ])
        self.assertTrue(first.exists())
        self.assertTrue(second.exists())
        self.assertEqual(plan["state"], "preview")

        calls = []

        def flaky_executor(item, _cancellation):
            calls.append(item["source"])
            if Path(item["source"]).name == "second.epub" and calls.count(item["source"]) == 1:
                raise OSError("temporary")
            destination = Path(item["destination"])
            destination.parent.mkdir(exist_ok=True)
            Path(item["source"]).replace(destination)
            return {"destination": str(destination)}

        failed = self.store.apply(plan["id"], flaky_executor)
        self.assertEqual(failed["state"], "failed")
        self.assertFalse(first.exists())
        self.assertTrue(second.exists())

        completed = self.store.apply(plan["id"], flaky_executor)
        self.assertEqual(completed["state"], "completed")
        self.assertEqual([item["attempts"] for item in completed["items"]], [1, 2])

    def test_cancelled_plan_remains_resumable(self):
        source = self.root / "book.epub"
        source.write_bytes(b"book")
        plan = self.store.create_plan("import", [{"action": "move", "source": source}])
        token = CancellationToken()
        token.cancel()

        paused = self.store.apply(plan["id"], lambda *_: {}, token)

        self.assertEqual(paused["state"], "paused")
        self.assertEqual(len(self.store.list_resumable()), 1)

    def test_committed_journal_move_reconciles_crashed_running_item(self):
        source = self.root / "book.epub"
        destination = self.root / "library" / source.name
        source.write_bytes(b"book content")
        expected_hash = file_transactions.calcular_sha256_archivo(source)
        plan = self.store.create_plan("import", [{"action": "move", "source": source}])
        self.store.set_item_state(plan["id"], 0, "running")
        destination.parent.mkdir()
        source.replace(destination)

        count = self.store.reconcile_from_journal([{
            "id": "move-1",
            "state": "committed",
            "origin": str(source),
            "destination": str(destination),
            "hash": expected_hash,
        }])
        reconciled = self.store.get_plan(plan["id"])

        self.assertEqual(count, 1)
        self.assertEqual(reconciled["state"], "completed")
        self.assertEqual(reconciled["items"][0]["state"], "completed")
        self.assertEqual(reconciled["items"][0]["result"]["destination"], str(destination))

    def test_legacy_sqlite_columns_are_migrated_in_place(self):
        legacy_path = self.root / "legacy.sqlite3"
        con = sqlite3.connect(legacy_path)
        try:
            con.execute(
                "CREATE TABLE plans (id TEXT PRIMARY KEY, kind TEXT NOT NULL, state TEXT NOT NULL, created_at REAL NOT NULL)"
            )
            con.execute(
                """
                CREATE TABLE plan_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, plan_id TEXT NOT NULL,
                    ordinal INTEGER NOT NULL, action TEXT NOT NULL,
                    source TEXT NOT NULL, state TEXT NOT NULL,
                    UNIQUE(plan_id, ordinal)
                )
                """
            )
            con.execute("INSERT INTO plans VALUES ('legacy', 'import', 'preview', 1)")
            con.execute(
                "INSERT INTO plan_items(plan_id, ordinal, action, source, state) VALUES ('legacy', 0, 'move', 'missing.epub', 'pending')"
            )
            con.commit()
        finally:
            con.close()

        migrated = OperationPlanStore(legacy_path).get_plan("legacy")

        self.assertEqual(migrated["schema_version"], 1)
        self.assertEqual(migrated["items"][0]["expected_hash"], "")
        self.assertEqual(migrated["items"][0]["result"], {})


if __name__ == "__main__":
    unittest.main()

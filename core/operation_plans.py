import json
import os
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from .cancellation import CancellationToken, OperationCancelled
from .file_transactions import calcular_sha256_archivo

SCHEMA_VERSION = 2
FINAL_PLAN_STATES = {"completed", "cancelled"}
FINAL_ITEM_STATES = {"completed", "skipped"}


class PlanValidationError(RuntimeError):
    pass


class OperationPlanStore:
    """SQLite-backed preview/apply plans with row-level resumability."""

    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._initialize()

    def _connect(self):
        con = sqlite3.connect(self.path, timeout=10)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA synchronous=FULL")
        con.execute("PRAGMA busy_timeout=10000")
        return con

    @contextmanager
    def _db(self):
        con = self._connect()
        try:
            yield con
            con.commit()
        # Transaction boundary: roll back every ordinary application or SQLite
        # failure, then preserve its original type for the caller.
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    def _initialize(self):
        with self._lock:  # noqa: SIM117 - lock must outlive transaction cleanup
            with self._db() as con:
                con.execute(
                    """
                    CREATE TABLE IF NOT EXISTS plans (
                        id TEXT PRIMARY KEY,
                        kind TEXT NOT NULL,
                        state TEXT NOT NULL,
                        created_at REAL NOT NULL,
                        updated_at REAL NOT NULL,
                        metadata_json TEXT NOT NULL,
                        schema_version INTEGER NOT NULL
                    )
                    """
                )
                plan_columns = {row[1] for row in con.execute("PRAGMA table_info(plans)")}
                for name, declaration in (
                    ("updated_at", "REAL NOT NULL DEFAULT 0"),
                    ("metadata_json", "TEXT NOT NULL DEFAULT '{}'"),
                    ("schema_version", "INTEGER NOT NULL DEFAULT 1"),
                ):
                    if name not in plan_columns:
                        con.execute(f"ALTER TABLE plans ADD COLUMN {name} {declaration}")
                con.execute(
                    """
                    CREATE TABLE IF NOT EXISTS plan_items (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        plan_id TEXT NOT NULL REFERENCES plans(id) ON DELETE CASCADE,
                        ordinal INTEGER NOT NULL,
                        action TEXT NOT NULL,
                        source TEXT NOT NULL,
                        destination TEXT NOT NULL,
                        expected_size INTEGER,
                        expected_hash TEXT NOT NULL DEFAULT '',
                        reason TEXT NOT NULL DEFAULT '',
                        state TEXT NOT NULL,
                        attempts INTEGER NOT NULL DEFAULT 0,
                        error TEXT NOT NULL DEFAULT '',
                        result_json TEXT NOT NULL DEFAULT '{}',
                        updated_at REAL NOT NULL,
                        UNIQUE(plan_id, ordinal)
                    )
                    """
                )
                item_columns = {row[1] for row in con.execute("PRAGMA table_info(plan_items)")}
                for name, declaration in (
                    ("destination", "TEXT NOT NULL DEFAULT ''"),
                    ("expected_size", "INTEGER"),
                    ("expected_hash", "TEXT NOT NULL DEFAULT ''"),
                    ("reason", "TEXT NOT NULL DEFAULT ''"),
                    ("attempts", "INTEGER NOT NULL DEFAULT 0"),
                    ("error", "TEXT NOT NULL DEFAULT ''"),
                    ("result_json", "TEXT NOT NULL DEFAULT '{}'"),
                    ("updated_at", "REAL NOT NULL DEFAULT 0"),
                ):
                    if name not in item_columns:
                        con.execute(f"ALTER TABLE plan_items ADD COLUMN {name} {declaration}")
                con.execute("CREATE INDEX IF NOT EXISTS idx_plan_items_state ON plan_items(plan_id, state, ordinal)")
                # A process may have stopped after claiming an item. No file is
                # repeated automatically: it returns to pending and is
                # revalidated against its preview signature before execution.
                con.execute("UPDATE plan_items SET state='pending' WHERE state='running'")
                con.execute("UPDATE plans SET state='paused', updated_at=? WHERE state='applying'", (time.time(),))
                con.execute(f"PRAGMA user_version={SCHEMA_VERSION}")

    def create_plan(self, kind, items, metadata=None, *, capture_hashes=True):
        now = time.time()
        plan_id = uuid.uuid4().hex
        prepared = []
        for ordinal, raw in enumerate(items):
            item = dict(raw)
            source = Path(item.get("source", ""))
            expected_size = item.get("expected_size")
            expected_hash = str(item.get("expected_hash", "") or "")
            if capture_hashes and source.exists() and source.is_file():
                expected_size = source.stat().st_size
                expected_hash = calcular_sha256_archivo(source)
            prepared.append((
                plan_id, ordinal, str(item.get("action", "")), str(source),
                str(item.get("destination", "") or ""), expected_size,
                expected_hash, str(item.get("reason", "") or ""), "pending", now,
            ))
        if not prepared:
            raise PlanValidationError("Un plan necesita al menos una acción.")
        with self._lock:  # noqa: SIM117 - lock must outlive transaction cleanup
            with self._db() as con:
                con.execute(
                    "INSERT INTO plans VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (plan_id, str(kind), "preview", now, now, json.dumps(metadata or {}, ensure_ascii=False), SCHEMA_VERSION),
                )
                con.executemany(
                    """
                    INSERT INTO plan_items
                    (plan_id, ordinal, action, source, destination, expected_size,
                     expected_hash, reason, state, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    prepared,
                )
        return self.get_plan(plan_id)

    def get_plan(self, plan_id):
        with self._db() as con:
            plan = con.execute("SELECT * FROM plans WHERE id=?", (str(plan_id),)).fetchone()
            if not plan:
                return None
            items = con.execute(
                "SELECT * FROM plan_items WHERE plan_id=? ORDER BY ordinal", (str(plan_id),)
            ).fetchall()
        result = dict(plan)
        result["metadata"] = json.loads(result.pop("metadata_json") or "{}")
        result["items"] = []
        for row in items:
            item = dict(row)
            item["result"] = json.loads(item.pop("result_json") or "{}")
            result["items"].append(item)
        return result

    def list_resumable(self):
        with self._db() as con:
            rows = con.execute(
                "SELECT id FROM plans WHERE state NOT IN ('completed', 'cancelled') ORDER BY updated_at DESC"
            ).fetchall()
        return [self.get_plan(row["id"]) for row in rows]

    def reconcile_from_journal(self, records):
        """Complete stranded plan rows only when a committed move is verifiable.

        A process can stop after the durable file transaction commits but before
        the plan row is updated.  The journal is authoritative only when its
        final destination still exists and matches the immutable preview hash.
        """
        operations = {}
        for record in records or []:
            operation_id = str(record.get("id", "") or "")
            if not operation_id:
                continue
            previous = operations.get(operation_id, {})
            merged = dict(record)
            for key in ("origin", "destination", "hash"):
                if not merged.get(key) and previous.get(key):
                    merged[key] = previous[key]
            operations[operation_id] = merged

        committed_by_source = {}
        for record in operations.values():
            if record.get("state") not in {"committed", "committed_recovered"}:
                continue
            source = str(record.get("origin", "") or "")
            destination = Path(str(record.get("destination", "") or ""))
            if not source or not destination.exists() or not destination.is_file():
                continue
            key = os.path.normcase(os.path.abspath(source))
            committed_by_source.setdefault(key, []).append((record, destination))

        reconciled = 0
        with self._lock:  # noqa: SIM117 - lock must outlive transaction cleanup
            with self._db() as con:
                rows = con.execute(
                    """
                    SELECT * FROM plan_items
                    WHERE state IN ('pending','running','failed')
                    """
                ).fetchall()
                touched_plans = set()
                for row in rows:
                    item = dict(row)
                    source = Path(item["source"])
                    if source.exists():
                        continue
                    key = os.path.normcase(os.path.abspath(str(source)))
                    for record, destination in committed_by_source.get(key, []):
                        expected_hash = str(item.get("expected_hash", "") or "")
                        journal_hash = str(record.get("hash", "") or "")
                        if expected_hash and journal_hash and expected_hash != journal_hash:
                            continue
                        if expected_hash and calcular_sha256_archivo(destination) != expected_hash:
                            continue
                        con.execute(
                            """
                            UPDATE plan_items
                            SET state='completed', error='', result_json=?, updated_at=?
                            WHERE id=?
                            """,
                            (
                                json.dumps(
                                    {"reconciled_from_journal": True, "destination": str(destination)},
                                    ensure_ascii=False,
                                ),
                                time.time(), item["id"],
                            ),
                        )
                        reconciled += 1
                        touched_plans.add(item["plan_id"])
                        break
                for plan_id in touched_plans:
                    remaining = con.execute(
                        """
                        SELECT COUNT(*) FROM plan_items
                        WHERE plan_id=? AND state NOT IN ('completed','skipped')
                        """,
                        (plan_id,),
                    ).fetchone()[0]
                    if remaining == 0:
                        self._set_plan_state(con, plan_id, "completed")
        return reconciled

    def _set_plan_state(self, con, plan_id, state):
        con.execute("UPDATE plans SET state=?, updated_at=? WHERE id=?", (state, time.time(), plan_id))

    def set_plan_state(self, plan_id, state):
        if state not in {"preview", "applying", "paused", "failed", "completed", "cancelled"}:
            raise PlanValidationError(f"Estado de plan no válido: {state}")
        with self._lock, self._db() as con:
            self._set_plan_state(con, str(plan_id), state)
        return self.get_plan(plan_id)

    def set_item_state(self, plan_id, ordinal, state, *, result=None, error=""):
        if state not in {"pending", "running", "completed", "failed", "skipped"}:
            raise PlanValidationError(f"Estado de elemento no válido: {state}")
        attempts_increment = 1 if state == "running" else 0
        with self._lock:  # noqa: SIM117 - lock must outlive transaction cleanup
            with self._db() as con:
                cursor = con.execute(
                    """
                    UPDATE plan_items
                    SET state=?, attempts=attempts+?, result_json=?, error=?, updated_at=?
                    WHERE plan_id=? AND ordinal=?
                    """,
                    (
                        state, attempts_increment, json.dumps(result or {}, ensure_ascii=False),
                        str(error or ""), time.time(), str(plan_id), int(ordinal),
                    ),
                )
                if cursor.rowcount != 1:
                    raise PlanValidationError(f"No existe el elemento {ordinal} del plan {plan_id}")

    def finalize_tracked_plan(self, plan_id, *, cancelled=False):
        with self._lock:  # noqa: SIM117 - lock must outlive transaction cleanup
            with self._db() as con:
                counts = {
                    row["state"]: row["count"]
                    for row in con.execute(
                        "SELECT state, COUNT(*) AS count FROM plan_items WHERE plan_id=? GROUP BY state",
                        (str(plan_id),),
                    )
                }
                if cancelled:
                    state = "paused"
                elif counts.get("failed"):
                    state = "failed"
                elif sum(counts.get(value, 0) for value in FINAL_ITEM_STATES) == sum(counts.values()):
                    state = "completed"
                else:
                    state = "paused"
                self._set_plan_state(con, str(plan_id), state)
        return self.get_plan(plan_id)

    def _validate_item_source(self, item):
        source = Path(item["source"])
        if not source.exists() or not source.is_file():
            raise PlanValidationError(f"Ya no existe el origen del plan: {source}")
        if item["expected_size"] is not None and source.stat().st_size != item["expected_size"]:
            raise PlanValidationError(f"Cambió el tamaño desde la previsualización: {source}")
        if item["expected_hash"] and calcular_sha256_archivo(source) != item["expected_hash"]:
            raise PlanValidationError(f"Cambió el contenido desde la previsualización: {source}")

    def validate_item(self, plan_id, ordinal):
        with self._db() as con:
            row = con.execute(
                "SELECT * FROM plan_items WHERE plan_id=? AND ordinal=?",
                (str(plan_id), int(ordinal)),
            ).fetchone()
        if not row:
            raise PlanValidationError(f"No existe el elemento {ordinal} del plan {plan_id}")
        self._validate_item_source(dict(row))
        return True

    def apply(self, plan_id, executor, cancellation=None, *, retry_failed=True, stop_on_error=True):
        cancellation = cancellation or CancellationToken()
        plan_id = str(plan_id)
        with self._lock:
            with self._db() as con:
                plan = con.execute("SELECT state FROM plans WHERE id=?", (plan_id,)).fetchone()
                if not plan:
                    raise PlanValidationError(f"No existe el plan {plan_id}")
                if plan["state"] in FINAL_PLAN_STATES:
                    return self.get_plan(plan_id)
                if retry_failed:
                    con.execute(
                        "UPDATE plan_items SET state='pending', error='' WHERE plan_id=? AND state='failed'",
                        (plan_id,),
                    )
                self._set_plan_state(con, plan_id, "applying")

            while True:
                try:
                    cancellation.raise_if_cancelled()
                except OperationCancelled:
                    with self._db() as con:
                        self._set_plan_state(con, plan_id, "paused")
                    break

                with self._db() as con:
                    row = con.execute(
                        """
                        SELECT * FROM plan_items
                        WHERE plan_id=? AND state='pending' ORDER BY ordinal LIMIT 1
                        """,
                        (plan_id,),
                    ).fetchone()
                    if not row:
                        remaining = con.execute(
                            "SELECT COUNT(*) FROM plan_items WHERE plan_id=? AND state NOT IN ('completed','skipped')",
                            (plan_id,),
                        ).fetchone()[0]
                        self._set_plan_state(con, plan_id, "completed" if remaining == 0 else "failed")
                        break
                    item = dict(row)
                    con.execute(
                        "UPDATE plan_items SET state='running', attempts=attempts+1, updated_at=? WHERE id=?",
                        (time.time(), item["id"]),
                    )

                try:
                    cancellation.raise_if_cancelled()
                    self._validate_item_source(item)
                    result = executor(dict(item), cancellation) or {}
                    with self._db() as con:
                        con.execute(
                            "UPDATE plan_items SET state='completed', result_json=?, error='', updated_at=? WHERE id=?",
                            (json.dumps(result, ensure_ascii=False), time.time(), item["id"]),
                        )
                except OperationCancelled:
                    with self._db() as con:
                        con.execute(
                            "UPDATE plan_items SET state='pending', updated_at=? WHERE id=?",
                            (time.time(), item["id"]),
                        )
                        self._set_plan_state(con, plan_id, "paused")
                    break
                # Executors combine format readers and file transactions with
                # distinct typed failures. The plan boundary records all of
                # them durably and keeps the item resumable.
                except Exception as exc:  # noqa: BLE001
                    with self._db() as con:
                        con.execute(
                            "UPDATE plan_items SET state='failed', error=?, updated_at=? WHERE id=?",
                            (str(exc), time.time(), item["id"]),
                        )
                        self._set_plan_state(con, plan_id, "failed")
                    if stop_on_error:
                        break
        return self.get_plan(plan_id)

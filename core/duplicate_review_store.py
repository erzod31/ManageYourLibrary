import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path


class DuplicateReviewStore:
    """Durable, paginated duplicate review sessions."""

    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as con:
            con.execute("PRAGMA journal_mode=WAL")
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS review_sessions (
                    id TEXT PRIMARY KEY, state TEXT NOT NULL,
                    created_at REAL NOT NULL, updated_at REAL NOT NULL
                )
                """
            )
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS review_pairs (
                    session_id TEXT NOT NULL REFERENCES review_sessions(id) ON DELETE CASCADE,
                    ordinal INTEGER NOT NULL, pair_json TEXT NOT NULL,
                    state TEXT NOT NULL DEFAULT 'pending', updated_at REAL NOT NULL,
                    PRIMARY KEY(session_id, ordinal)
                )
                """
            )
            con.execute("CREATE INDEX IF NOT EXISTS idx_review_pending ON review_pairs(session_id, state, ordinal)")
            con.execute("PRAGMA user_version=1")

    @contextmanager
    def _db(self):
        con = sqlite3.connect(self.path, timeout=10)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        try:
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    def create_session(self, pairs):
        session_id = uuid.uuid4().hex
        now = time.time()
        with self._db() as con:
            con.execute("INSERT INTO review_sessions VALUES (?, 'open', ?, ?)", (session_id, now, now))
            con.executemany(
                "INSERT INTO review_pairs VALUES (?, ?, ?, 'pending', ?)",
                ((session_id, index, json.dumps(pair, ensure_ascii=False), now) for index, pair in enumerate(pairs)),
            )
        return session_id

    def page(self, session_id, *, offset=0, limit=50, state=None):
        limit = max(1, min(500, int(limit)))
        offset = max(0, int(offset))
        query = "SELECT ordinal, pair_json, state FROM review_pairs WHERE session_id=?"
        params = [str(session_id)]
        if state:
            query += " AND state=?"
            params.append(str(state))
        query += " ORDER BY ordinal LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        with self._db() as con:
            rows = con.execute(query, params).fetchall()
        return [
            {"ordinal": row["ordinal"], "state": row["state"], "pair": json.loads(row["pair_json"])}
            for row in rows
        ]

    def mark(self, session_id, ordinal, state):
        if state not in {"pending", "resolved", "skipped", "error"}:
            raise ValueError(f"Invalid review state: {state}")
        with self._db() as con:
            con.execute(
                "UPDATE review_pairs SET state=?, updated_at=? WHERE session_id=? AND ordinal=?",
                (state, time.time(), str(session_id), int(ordinal)),
            )
            pending = con.execute(
                "SELECT COUNT(*) FROM review_pairs WHERE session_id=? AND state='pending'",
                (str(session_id),),
            ).fetchone()[0]
            if pending == 0:
                con.execute(
                    "UPDATE review_sessions SET state='completed', updated_at=? WHERE id=?",
                    (time.time(), str(session_id)),
                )

    def pending_count(self, session_id=None):
        """Return unresolved review pairs, optionally limited to one session."""
        with self._db() as con:
            if session_id:
                return con.execute(
                    "SELECT COUNT(*) FROM review_pairs WHERE session_id=? AND state='pending'",
                    (str(session_id),),
                ).fetchone()[0]
            return con.execute(
                "SELECT COUNT(*) FROM review_pairs WHERE state='pending'"
            ).fetchone()[0]

    def latest_open_session(self):
        with self._db() as con:
            row = con.execute(
                "SELECT id FROM review_sessions WHERE state='open' ORDER BY updated_at DESC LIMIT 1"
            ).fetchone()
        return row["id"] if row else None

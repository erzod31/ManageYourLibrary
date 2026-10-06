"""Durable catalog model separating works, editions, and concrete files.

The JSON index remains a compatibility/export surface.  This SQLite catalog is
updated from it without deleting records, so upgrading cannot make a user's
books or confirmed metadata disappear.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import time
import unicodedata
from contextlib import contextmanager
from pathlib import Path

SCHEMA_VERSION = 1


def _fold(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", text).strip().casefold()


def _stable_id(prefix: str, *values: object) -> str:
    payload = "\x1f".join(_fold(value) for value in values)
    return f"{prefix}_{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:24]}"


def _path_key(value: object) -> str:
    return os.path.normcase(os.path.abspath(str(value or "")))


class CatalogStore:
    """SQLite catalog with non-destructive synchronization from index rows."""

    def __init__(self, path, *, initialize=True):
        self.path = Path(path)
        if initialize:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._initialize()

    @contextmanager
    def _db(self, *, read_only=False):
        if read_only:
            con = sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", uri=True, timeout=0.1)
        else:
            con = sqlite3.connect(self.path, timeout=15)
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

    def _initialize(self):
        with self._db() as con:
            con.execute("PRAGMA journal_mode=WAL")
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS works (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    sort_title TEXT NOT NULL,
                    author TEXT NOT NULL DEFAULT '',
                    sort_author TEXT NOT NULL DEFAULT '',
                    series TEXT NOT NULL DEFAULT '',
                    tags_json TEXT NOT NULL DEFAULT '[]',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS editions (
                    id TEXT PRIMARY KEY,
                    work_id TEXT NOT NULL REFERENCES works(id),
                    isbn TEXT NOT NULL DEFAULT '',
                    language TEXT NOT NULL DEFAULT '',
                    publisher TEXT NOT NULL DEFAULT '',
                    publication_year TEXT NOT NULL DEFAULT '',
                    edition_label TEXT NOT NULL DEFAULT '',
                    cover_url TEXT NOT NULL DEFAULT '',
                    provenance_json TEXT NOT NULL DEFAULT '{}',
                    confidence REAL NOT NULL DEFAULT 0,
                    manual_lock INTEGER NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS book_files (
                    id TEXT PRIMARY KEY,
                    edition_id TEXT NOT NULL REFERENCES editions(id),
                    path TEXT NOT NULL UNIQUE,
                    path_key TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    extension TEXT NOT NULL DEFAULT '',
                    size_bytes INTEGER NOT NULL DEFAULT 0,
                    mtime REAL NOT NULL DEFAULT 0,
                    sha256 TEXT NOT NULL DEFAULT '',
                    integrity_state TEXT NOT NULL DEFAULT 'unknown',
                    present INTEGER NOT NULL DEFAULT 1,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    first_seen REAL NOT NULL,
                    last_seen REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_works_sort ON works(sort_title, sort_author);
                CREATE INDEX IF NOT EXISTS idx_editions_work ON editions(work_id);
                CREATE INDEX IF NOT EXISTS idx_files_edition ON book_files(edition_id);
                CREATE INDEX IF NOT EXISTS idx_files_sha ON book_files(sha256);
                CREATE TABLE IF NOT EXISTS collections (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS collection_works (
                    collection_id TEXT NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
                    work_id TEXT NOT NULL REFERENCES works(id) ON DELETE CASCADE,
                    PRIMARY KEY(collection_id, work_id)
                );
                """
            )
            con.execute(f"PRAGMA user_version={SCHEMA_VERSION}")

    @staticmethod
    def _record_identity(record: dict) -> dict:
        name = str(record.get("nombre") or Path(str(record.get("ruta") or "")).name)
        title = str(record.get("titulo") or "").strip()
        author = str(record.get("autor") or "").strip()
        if not title:
            stem = Path(name).stem.replace("_", " ").strip()
            parts = [part.strip() for part in re.split(r"\s+-\s+", stem) if part.strip()]
            if len(parts) >= 2 and author and _fold(parts[0]) == _fold(author):
                title = " - ".join(parts[1:])
            elif len(parts) >= 2 and not author:
                author, title = parts[0], " - ".join(parts[1:])
            else:
                title = stem
        isbn = re.sub(r"[^0-9Xx]", "", str(record.get("isbn") or "")).upper()
        if len(isbn) not in {10, 13}:
            isbn = ""
        return {
            "title": title or name or "Sin título",
            "author": author,
            "isbn": isbn,
            "language": str(record.get("idioma") or record.get("language") or "").strip(),
            "publisher": str(record.get("editorial") or record.get("publisher") or "").strip(),
            "year": str(record.get("anio") or record.get("year") or "").strip(),
            "series": str(record.get("serie") or record.get("series") or "").strip(),
            "edition": str(record.get("edicion") or record.get("edition") or "").strip(),
        }

    def sync_index(self, index: dict) -> dict:
        """Upsert every live index row; never delete rows missing from a scan."""
        rows = list((index or {}).get("archivos", []) or [])
        now = time.time()
        seen_keys = set()
        with self._db() as con:
            for record in rows:
                path = str(record.get("ruta") or "").strip()
                if not path:
                    continue
                path_key = _path_key(path)
                seen_keys.add(path_key)
                identity = self._record_identity(record)
                work_id = _stable_id("work", identity["title"], identity["author"])
                edition_key = identity["isbn"] or "|".join(
                    (identity["language"], identity["publisher"], identity["year"], identity["edition"])
                ) or "unspecified"
                edition_id = _stable_id("edition", work_id, edition_key)
                file_id = _stable_id("file", path_key)
                provenance = record.get("provenance") or record.get("evidencias") or {}
                confidence = record.get("confianza_global", record.get("confianza", 0)) or 0
                try:
                    confidence = float(confidence)
                except (TypeError, ValueError):
                    confidence = 0
                con.execute(
                    """INSERT INTO works(id,title,sort_title,author,sort_author,series,tags_json,created_at,updated_at)
                       VALUES(?,?,?,?,?,?,?, ?,?)
                       ON CONFLICT(id) DO UPDATE SET
                         title=excluded.title, sort_title=excluded.sort_title,
                         author=CASE WHEN works.author='' THEN excluded.author ELSE works.author END,
                         sort_author=CASE WHEN works.sort_author='' THEN excluded.sort_author ELSE works.sort_author END,
                         series=CASE WHEN ? AND (? OR NOT EXISTS(
                           SELECT 1 FROM editions WHERE work_id=works.id AND manual_lock=1
                         )) THEN excluded.series ELSE works.series END,
                         tags_json=CASE WHEN ? THEN excluded.tags_json ELSE works.tags_json END,
                         updated_at=excluded.updated_at""",
                    (work_id, identity["title"], _fold(identity["title"]), identity["author"],
                     _fold(identity["author"]), identity["series"], json.dumps(record.get("tags") or [], ensure_ascii=False), now, now,
                     int("serie" in record or "series" in record), int(bool(record.get("manual_lock"))), int("tags" in record)),
                )
                con.execute(
                    """INSERT INTO editions(id,work_id,isbn,language,publisher,publication_year,edition_label,
                                             cover_url,provenance_json,confidence,manual_lock,created_at,updated_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                       ON CONFLICT(id) DO UPDATE SET
                         language=CASE WHEN excluded.manual_lock=1 OR (editions.manual_lock=0 AND excluded.language<>'') THEN excluded.language ELSE editions.language END,
                         publisher=CASE WHEN excluded.manual_lock=1 OR (editions.manual_lock=0 AND excluded.publisher<>'') THEN excluded.publisher ELSE editions.publisher END,
                         publication_year=CASE WHEN excluded.manual_lock=1 OR (editions.manual_lock=0 AND excluded.publication_year<>'') THEN excluded.publication_year ELSE editions.publication_year END,
                         edition_label=CASE WHEN excluded.manual_lock=1 OR (editions.manual_lock=0 AND excluded.edition_label<>'') THEN excluded.edition_label ELSE editions.edition_label END,
                         manual_lock=MAX(editions.manual_lock, excluded.manual_lock),
                         cover_url=CASE WHEN excluded.cover_url<>'' THEN excluded.cover_url ELSE editions.cover_url END,
                         provenance_json=CASE WHEN excluded.provenance_json<>'{}' THEN excluded.provenance_json ELSE editions.provenance_json END,
                         confidence=MAX(editions.confidence, excluded.confidence), updated_at=excluded.updated_at""",
                    (edition_id, work_id, identity["isbn"], identity["language"], identity["publisher"], identity["year"],
                     identity["edition"], str(record.get("cover_url") or ""), json.dumps(provenance, ensure_ascii=False),
                     confidence, int(bool(record.get("manual_lock"))), now, now),
                )
                con.execute(
                    """INSERT INTO book_files(id,edition_id,path,path_key,name,extension,size_bytes,mtime,sha256,
                                                integrity_state,present,metadata_json,first_seen,last_seen)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                       ON CONFLICT(path_key) DO UPDATE SET
                         edition_id=excluded.edition_id, path=excluded.path, name=excluded.name,
                         extension=excluded.extension, size_bytes=excluded.size_bytes, mtime=excluded.mtime,
                         sha256=CASE WHEN excluded.sha256<>'' THEN excluded.sha256 ELSE book_files.sha256 END,
                         integrity_state=excluded.integrity_state, present=1,
                         metadata_json=excluded.metadata_json, last_seen=excluded.last_seen""",
                    (file_id, edition_id, path, path_key, str(record.get("nombre") or Path(path).name),
                     str(record.get("extension") or Path(path).suffix).lower(), int(record.get("tamano_bytes") or 0),
                     float(record.get("mtime") or 0), str(record.get("sha256") or ""),
                     "valid" if record.get("integrity_valid") is True else "unknown", 1,
                     json.dumps(record, ensure_ascii=False, default=str), now, now),
                )
            # A missing file remains catalogued and recoverable; only its presence flag changes.
            if seen_keys:
                placeholders = ",".join("?" for _ in seen_keys)
                con.execute(f"UPDATE book_files SET present=0 WHERE path_key NOT IN ({placeholders})", tuple(sorted(seen_keys)))
            else:
                con.execute("UPDATE book_files SET present=0")
        return self.stats()

    def stats(self) -> dict:
        with self._db() as con:
            return {
                "works": con.execute("SELECT COUNT(*) FROM works").fetchone()[0],
                "editions": con.execute("SELECT COUNT(*) FROM editions").fetchone()[0],
                "files": con.execute("SELECT COUNT(*) FROM book_files").fetchone()[0],
                "present_files": con.execute("SELECT COUNT(*) FROM book_files WHERE present=1").fetchone()[0],
            }

    def record_for_path(self, path) -> dict | None:
        if not self.path.is_file():
            return None
        with self._db(read_only=True) as con:
            row = con.execute(
                """SELECT w.title,w.author,w.series,w.tags_json,e.isbn,e.language,e.publisher,e.publication_year,
                          e.edition_label,e.cover_url,e.provenance_json,e.confidence,e.manual_lock,
                          f.path,f.name,f.extension,f.size_bytes,f.mtime,f.sha256,f.integrity_state,f.present
                   FROM book_files f JOIN editions e ON e.id=f.edition_id JOIN works w ON w.id=e.work_id
                   WHERE f.path_key=?""",
                (_path_key(path),),
            ).fetchone()
        if not row:
            return None
        result = dict(row)
        result["tags"] = json.loads(result.pop("tags_json") or "[]")
        try:
            result["provenance"] = json.loads(result.pop("provenance_json") or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            result["provenance"] = {}
        return result

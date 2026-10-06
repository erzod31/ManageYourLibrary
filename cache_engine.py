import json
import logging
import os
import sqlite3
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path


APP_NAME = "ManageYourLibrary"


def _app_data_dir() -> Path:
    if os.name == "nt":
        return Path(os.environ.get("APPDATA", str(Path.home()))) / APP_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    return Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))) / APP_NAME


APP_DATA = _app_data_dir()
DB_PATH = APP_DATA / "analysis_cache.sqlite3"
SCHEMA_VERSION = 2
_DB_LOCK = threading.RLock()
_INITIALIZED_PATHS = set()
LOGGER = logging.getLogger(__name__)


def _connect():
    APP_DATA.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=5)
    con.execute("PRAGMA busy_timeout=5000")
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    return con


def _initialize_schema(con):
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS api_cache (
            query_hash TEXT PRIMARY KEY,
            source TEXT NOT NULL,
            query TEXT NOT NULL,
            response_json TEXT NOT NULL,
            confidence REAL DEFAULT 0,
            created_at REAL NOT NULL
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS file_analysis_cache (
            file_key TEXT PRIMARY KEY,
            path TEXT NOT NULL,
            size INTEGER NOT NULL,
            modified_time REAL NOT NULL,
            format TEXT NOT NULL,
            result_json TEXT NOT NULL,
            confidence REAL DEFAULT 0,
            created_at REAL NOT NULL
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS ocr_signal_cache (
            file_key TEXT NOT NULL,
            page_number INTEGER NOT NULL,
            dpi INTEGER NOT NULL,
            psm TEXT NOT NULL,
            preprocessing_profile TEXT NOT NULL,
            text_summary TEXT NOT NULL,
            confidence REAL DEFAULT 0,
            layout_json TEXT NOT NULL,
            created_at REAL NOT NULL,
            PRIMARY KEY (file_key, page_number, dpi, psm, preprocessing_profile)
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS candidate_cache (
            file_key TEXT NOT NULL,
            candidate_type TEXT NOT NULL,
            candidate_value TEXT NOT NULL,
            source TEXT NOT NULL,
            score REAL DEFAULT 0,
            evidence_json TEXT NOT NULL,
            created_at REAL NOT NULL
        )
        """
    )
    con.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_candidate_unique
        ON candidate_cache(file_key, candidate_type, candidate_value, source)
        """
    )
    # Older databases allowed duplicate candidate rows.  Clean those only
    # after the table exists so first-run initialization is also safe.
    con.execute(
        """
        DELETE FROM candidate_cache
        WHERE rowid NOT IN (
            SELECT MAX(rowid) FROM candidate_cache
            GROUP BY file_key, candidate_type, candidate_value, source
        )
        """
    )
    con.execute("CREATE INDEX IF NOT EXISTS idx_candidate_created ON candidate_cache(created_at)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_api_created ON api_cache(created_at)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_file_analysis_created ON file_analysis_cache(created_at)")
    con.execute(f"PRAGMA user_version={SCHEMA_VERSION}")


def prune_cache(max_age_days=90):
    cutoff = time.time() - max(1, int(max_age_days)) * 86400
    try:
        with _database() as con:
            counts = {}
            for table in ("api_cache", "file_analysis_cache", "ocr_signal_cache", "candidate_cache"):
                cursor = con.execute(f"DELETE FROM {table} WHERE created_at < ?", (cutoff,))
                counts[table] = cursor.rowcount
        return counts
    except Exception as exc:
        _report_cache_error("prune_cache", exc)
        return {}


@contextmanager
def _database():
    """Return a serialized connection and always close it after use."""
    db_key = str(Path(DB_PATH).resolve())
    with _DB_LOCK:
        con = _connect()
        try:
            if db_key not in _INITIALIZED_PATHS:
                _initialize_schema(con)
                con.commit()
                _INITIALIZED_PATHS.add(db_key)
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()


def _report_cache_error(operation, exc):
    LOGGER.warning("Cache operation %s failed: %s", operation, exc)


def _json_load(value, default=None):
    try:
        return json.loads(value)
    except Exception:
        return default


def _json_dump(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def cache_api_response(query_hash, source, query, response_json, confidence=0):
    if response_json is None:
        return
    try:
        with _database() as con:
            con.execute(
                """
                INSERT OR REPLACE INTO api_cache
                (query_hash, source, query, response_json, confidence, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (str(query_hash), str(source), str(query), _json_dump(response_json), float(confidence or 0), time.time()),
            )
    except Exception as exc:
        _report_cache_error("cache_api_response", exc)


def get_cached_api_response(query_hash, max_age_days=30):
    try:
        max_age = time.time() - (max_age_days * 86400)
        with _database() as con:
            row = con.execute(
                "SELECT response_json FROM api_cache WHERE query_hash=? AND created_at>=?",
                (str(query_hash), max_age),
            ).fetchone()
        return _json_load(row[0]) if row else None
    except Exception as exc:
        _report_cache_error("get_cached_api_response", exc)
        return None


def cache_file_analysis(file_key, path, size, modified_time, format_name, result, confidence=0):
    if not file_key or not result:
        return
    try:
        with _database() as con:
            con.execute(
                """
                INSERT OR REPLACE INTO file_analysis_cache
                (file_key, path, size, modified_time, format, result_json, confidence, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(file_key),
                    str(path),
                    int(size or 0),
                    float(modified_time or 0),
                    str(format_name or ""),
                    _json_dump(result),
                    float(confidence or 0),
                    time.time(),
                ),
            )
    except Exception as exc:
        _report_cache_error("cache_file_analysis", exc)


def get_cached_file_analysis(file_key, size=None, modified_time=None, max_age_days=30):
    try:
        max_age = time.time() - (max_age_days * 86400)
        with _database() as con:
            row = con.execute(
                """
                SELECT size, modified_time, result_json
                FROM file_analysis_cache
                WHERE file_key=? AND created_at>=?
                """,
                (str(file_key), max_age),
            ).fetchone()
        if not row:
            return None
        cached_size, cached_mtime, result_json = row
        if size is not None and int(size) != int(cached_size):
            return None
        if modified_time is not None and abs(float(modified_time) - float(cached_mtime)) > 1:
            return None
        return _json_load(result_json)
    except Exception as exc:
        _report_cache_error("get_cached_file_analysis", exc)
        return None


def cache_ocr_result(file_key, page_number, dpi, psm, preprocessing_profile, text_summary, confidence=0, layout=None):
    """Store OCR execution metadata only; OCR text is never persisted."""
    if not file_key:
        return
    summary = ""
    try:
        with _database() as con:
            con.execute(
                """
                INSERT OR REPLACE INTO ocr_signal_cache
                (file_key, page_number, dpi, psm, preprocessing_profile, text_summary, confidence, layout_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(file_key),
                    int(page_number or 0),
                    int(dpi or 0),
                    str(psm or ""),
                    str(preprocessing_profile or ""),
                    summary,
                    float(confidence or 0),
                    _json_dump(layout or {}),
                    time.time(),
                ),
            )
    except Exception as exc:
        _report_cache_error("cache_ocr_result", exc)


def get_cached_ocr_result(file_key, page_number, dpi, psm, preprocessing_profile, max_age_days=7):
    try:
        max_age = time.time() - (max_age_days * 86400)
        with _database() as con:
            row = con.execute(
                """
                SELECT text_summary, confidence, layout_json
                FROM ocr_signal_cache
                WHERE file_key=? AND page_number=? AND dpi=? AND psm=? AND preprocessing_profile=? AND created_at>=?
                """,
                (str(file_key), int(page_number or 0), int(dpi or 0), str(psm or ""), str(preprocessing_profile or ""), max_age),
            ).fetchone()
        if not row:
            return None
        return {
            "text_summary": row[0],
            "confidence": row[1],
            "layout": _json_load(row[2], {}),
        }
    except Exception as exc:
        _report_cache_error("get_cached_ocr_result", exc)
        return None


def cache_candidate(file_key, candidate_type, candidate_value, source, score=0, evidence=None):
    if not file_key or not candidate_value:
        return
    try:
        with _database() as con:
            con.execute(
                """
                INSERT INTO candidate_cache
                (file_key, candidate_type, candidate_value, source, score, evidence_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(file_key, candidate_type, candidate_value, source)
                DO UPDATE SET score=excluded.score, evidence_json=excluded.evidence_json,
                              created_at=excluded.created_at
                """,
                (
                    str(file_key),
                    str(candidate_type or ""),
                    str(candidate_value),
                    str(source or ""),
                    float(score or 0),
                    _json_dump(evidence or {}),
                    time.time(),
                ),
            )
            con.execute(
                "DELETE FROM candidate_cache WHERE created_at < ?",
                (time.time() - 90 * 86400,),
            )
    except Exception as exc:
        _report_cache_error("cache_candidate", exc)

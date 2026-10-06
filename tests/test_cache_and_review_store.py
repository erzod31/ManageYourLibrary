import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import cache_engine
from core.duplicate_review_store import DuplicateReviewStore


class CacheInitializationTests(unittest.TestCase):
    def test_fresh_database_is_initialized_before_candidate_cleanup(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with (
                patch.object(cache_engine, "APP_DATA", root),
                patch.object(cache_engine, "DB_PATH", root / "cache.sqlite3"),
                patch.object(cache_engine, "_INITIALIZED_PATHS", set()),
            ):
                cache_engine.cache_candidate(
                    "file-key", "title", "The Book", "local", 90,
                    {"page": 1},
                )
                self.assertTrue((root / "cache.sqlite3").exists())


class DuplicateReviewStoreTests(unittest.TestCase):
    def test_review_session_is_paginated_and_completed_durably(self):
        with tempfile.TemporaryDirectory() as temp:
            store = DuplicateReviewStore(Path(temp) / "reviews.sqlite3")
            session = store.create_session([
                {"left": "a", "right": "b"},
                {"left": "c", "right": "d"},
            ])

            self.assertEqual(len(store.page(session, limit=1)), 1)
            self.assertEqual(store.latest_open_session(), session)
            self.assertEqual(store.pending_count(), 2)
            store.mark(session, 0, "resolved")
            self.assertEqual(store.pending_count(session), 1)
            store.mark(session, 1, "skipped")

            rows = store.page(session, limit=10)
            self.assertEqual([row["state"] for row in rows], ["resolved", "skipped"])
            self.assertEqual(store.pending_count(), 0)
            self.assertIsNone(store.latest_open_session())


if __name__ == "__main__":
    unittest.main()

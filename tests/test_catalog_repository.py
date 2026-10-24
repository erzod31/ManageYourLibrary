import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.catalog_repository import CatalogRepository, CatalogConflictError
from core.index_store import IndexRecoveryError


class CatalogRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.legacy = self.root / 'index.json'
        self.original = {'archivos': [{'ruta': str(self.root / 'a.epub'), 'titulo': 'Original',
                                      'tags': ['personal'], 'favorite': True}]}
        self.legacy.write_text(json.dumps(self.original), encoding='utf-8')
        self.repository = CatalogRepository(self.root / 'catalog.sqlite3', self.legacy)

    def test_migration_keeps_legacy_unchanged_and_preserves_all_fields(self):
        before = self.legacy.read_bytes()
        current = self.repository.load()
        self.assertEqual(current['archivos'], self.original['archivos'])
        self.assertEqual(self.legacy.read_bytes(), before)

    def test_single_row_update_and_projection_commit_together(self):
        current = self.repository.load()
        row = current['archivos'][0]
        before = self.legacy.read_bytes()
        updated, revision = self.repository.update(row['ruta'], lambda row: {**row, 'titulo': 'Corrected'})
        self.assertEqual(updated['titulo'], 'Corrected')
        self.assertEqual(self.repository.load()['_revision'], revision)
        self.assertEqual(self.repository.store.record_for_path(row['ruta'])['title'], 'Corrected')
        self.assertEqual(self.legacy.read_bytes(), before)

    def test_stale_full_snapshot_cannot_overwrite_correction(self):
        stale = self.repository.load()
        self.repository.update(stale['archivos'][0]['ruta'], lambda row: {**row, 'favorite': False})
        with self.assertRaises(CatalogConflictError):
            self.repository.save(stale)
        self.assertFalse(self.repository.load()['archivos'][0]['favorite'])

    def test_failed_projection_rolls_back_revision_and_data(self):
        before = self.repository.load()
        with patch.object(self.repository.store, 'sync_index', side_effect=sqlite3.OperationalError('disk full')):
            with self.assertRaises(sqlite3.OperationalError):
                self.repository.update(before['archivos'][0]['ruta'], lambda row: {**row, 'favorite': False})
        self.assertEqual(self.repository.load(), before)

    def test_changed_legacy_is_not_silently_overwritten(self):
        self.repository.load()
        self.legacy.write_text('{broken', encoding='utf-8')
        with self.assertRaises(IndexRecoveryError):
            self.repository.load()

    def test_backup_is_consistent_and_never_overwrites_existing_backup(self):
        before = self.repository.load()
        backup = self.repository.backup(self.root / 'backup.sqlite3')
        restored = CatalogRepository(backup, self.legacy).load()
        self.assertEqual(restored, before)
        with self.assertRaises(FileExistsError):
            self.repository.backup(backup)

    def test_export_does_not_overwrite_legacy(self):
        with self.assertRaises(ValueError):
            self.repository.export_json(self.legacy)
        target = self.root / 'export.json'
        self.repository.export_json(target)
        self.assertEqual(json.loads(target.read_text(encoding='utf-8')), self.original)

    def test_identity_ids_survive_single_book_correction(self):
        self.repository.load()
        with self.repository.store._db() as db:
            before = tuple(db.execute('SELECT id,edition_id FROM book_files').fetchone())
        self.repository.update(self.original['archivos'][0]['ruta'], lambda row: {**row, 'titulo': 'New title'})
        with self.repository.store._db() as db:
            after = tuple(db.execute('SELECT id,edition_id FROM book_files').fetchone())
        self.assertEqual(before, after)

    def test_new_conflict_can_lower_projected_confidence(self):
        path = self.original['archivos'][0]['ruta']
        self.repository.load()
        self.repository.update(path, lambda row: {**row, 'confianza_global': 98})
        self.repository.update(path, lambda row: {**row, 'confianza_global': 60, 'review_required': True})
        self.assertEqual(self.repository.store.record_for_path(path)['confidence'], 60)

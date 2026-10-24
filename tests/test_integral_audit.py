"""Regression fixtures for the 2026-10 audit; never use a personal profile."""
import io
import itertools
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from bibliographic_validator import candidates_to_evidence
from book_identity_scorer import score_identity
from core import document_readers, index_store
from core.catalog_store import CatalogStore
from core.cover_service import CoverService
from core.operation_plans import OperationPlanStore
from metadata import external_providers as providers


class IntegralAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_catalog_sync_does_not_depend_on_sql_parameter_capacity(self):
        connect = sqlite3.connect

        def limited(*args, **kwargs):
            con = connect(*args, **kwargs)
            con.setlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER, 64)
            return con

        with patch('core.catalog_store.sqlite3.connect', side_effect=limited):
            store = CatalogStore(self.root / 'catalog.db')
            rows = [{'ruta': str(self.root / f'{i}.epub'), 'titulo': f'Book {i}'} for i in range(150)]
            self.assertEqual(store.sync_index({'archivos': rows})['present_files'], 150)
            self.assertEqual(store.sync_index({'archivos': rows[:100]})['present_files'], 100)

    def test_repeated_candidate_cannot_raise_confidence(self):
        candidate = {'source': 'Open Library', 'title': 'A Synthetic Book',
                     'author': 'Example Author', 'isbn': '9780306406157', 'year': '2000'}
        original = score_identity(candidates_to_evidence([candidate]))
        for count in (2, 3, 100):
            scored = score_identity(candidates_to_evidence([candidate] * count))
            self.assertEqual(scored['confidence'], original['confidence'])
            self.assertEqual(scored['decision'], original['decision'])

    def test_evidence_order_does_not_change_result(self):
        candidates = [{'source': source, 'title': title, 'author': 'Example Author'}
                      for source, title in [('Open Library', 'Long title of a book'),
                                            ('Wikidata', 'Long title of the book'),
                                            ('Crossref', 'Another title')]]
        results = [score_identity(candidates_to_evidence(order)) for order in itertools.permutations(candidates)]
        self.assertTrue(all(result == results[0] for result in results))

    def test_second_store_does_not_recover_a_live_plan(self):
        path = self.root / 'plans.db'
        store = OperationPlanStore(path)
        plan = store.create_plan('audit', [{'source': str(self.root / 'missing.epub')}])
        store.set_plan_state(plan['id'], 'applying')
        store.set_item_state(plan['id'], 0, 'running')
        other = OperationPlanStore(path)
        actual = other.get_plan(plan['id'])
        self.assertEqual(actual['state'], 'applying')
        self.assertEqual(actual['items'][0]['state'], 'running')

    def test_plain_text_reads_only_its_budget(self):
        stream = io.BytesIO(b'a' * 12_000_000)
        requested = []
        original_read = stream.read

        def read(size=-1):
            requested.append(size)
            return original_read(size)

        stream.read = read
        with patch.object(Path, 'open', return_value=stream):
            document_readers._plain(self.root / 'large.txt')
        self.assertTrue(requested)
        self.assertTrue(all(0 < size <= 4_000_001 for size in requested))

    def test_oversized_zip_member_is_rejected_before_expansion(self):
        path = self.root / 'large.docx'
        with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('word/document.xml', '<p>' + 'a' * 13_000_000 + '</p>')
        with zipfile.ZipFile(path) as archive, self.assertRaises(ValueError):
            document_readers._read_zip_member(archive, 'word/document.xml')

    def test_corrupt_index_is_not_an_empty_library(self):
        path = self.root / 'index.json'
        path.write_text('{"archivos": [', encoding='utf-8')
        with self.assertRaises(ValueError):
            index_store.cargar_indice(path)
        self.assertEqual(path.read_text(encoding='utf-8'), '{"archivos": [')

    def test_saving_does_not_replace_a_corrupt_index(self):
        path = self.root / 'index.json'
        path.write_text('{broken', encoding='utf-8')
        with self.assertRaises(ValueError):
            index_store.guardar_indice(path, {'archivos': []})
        self.assertEqual(path.read_text(encoding='utf-8'), '{broken')

    def test_circuit_open_queries_do_not_extend_cooldown(self):
        with patch.dict(providers.PROVIDER_HEALTH, {}, clear=True):
            with patch.object(providers.time, 'monotonic', return_value=0), patch.object(providers.time, 'time', return_value=0):
                for _ in range(3):
                    providers._record_health('audit.invalid', 'error')
            with patch.object(providers.time, 'monotonic', return_value=50), patch.object(providers.time, 'time', return_value=50):
                self.assertTrue(providers._circuit_is_open('audit.invalid'))
                providers._record_health('audit.invalid', 'circuit_open')
            with patch.object(providers.time, 'monotonic', return_value=61), patch.object(providers.time, 'time', return_value=61):
                self.assertFalse(providers._circuit_is_open('audit.invalid'))

    def test_pdf_cover_and_ocr_share_serialization(self):
        from ocr_engine import _render_pdf_page
        active = 0
        peak = 0
        lock = threading.Lock()

        class Document:
            def __init__(self, path):
                nonlocal active, peak
                with lock:
                    active += 1
                    peak = max(peak, active)
                time.sleep(.02)

            def __len__(self):
                return 0

            def close(self):
                nonlocal active
                with lock:
                    active -= 1

        with patch.dict(sys.modules, {'pypdfium2': SimpleNamespace(PdfDocument=Document)}):
            with ThreadPoolExecutor(max_workers=4) as pool:
                futures = [pool.submit(CoverService._extract_pdf, self.root / 'a.pdf'),
                           pool.submit(_render_pdf_page, self.root / 'b.pdf', 0, 72)]
                for future in futures:
                    future.result()
        self.assertEqual(peak, 1)
        self.assertEqual(active, 0)

import io
import json
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
import zipfile
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from core.cancellation import CancellationToken, OperationCancelled
from core.catalog_repository import CatalogRepository
from core.cover_service import CoverService, SafeCoverRedirect, _copy_bounded_image
from core.document_readers import _run_bounded
from core.import_preview import prepare_import, needs_review
from core.index_service import merge_persistent_metadata
from core.operation_plans import OperationPlanStore, PlanValidationError
from core.profile_backup import create_backup, restore_backup
from core.profile_guard import ProfileGuard, ProfileInUseError
from metadata import external_providers


class AuditWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.profile = self.root / 'profile'
        self.profile.mkdir()
        self.book = self.root / 'book.txt'
        self.book.write_bytes(b'Synthetic original')

    def test_preparation_is_read_only_and_strips_document_contents(self):
        store = OperationPlanStore(self.profile / 'plans.sqlite3')
        before = self.book.read_bytes()
        plan = prepare_import([self.book], store, lambda path: {'titulo': 'Proposed', 'ocr_text': 'PRIVATE CONTENT'},
                              self.root / 'library', CancellationToken())
        self.assertEqual(plan['state'], 'preview')
        self.assertEqual(plan['metadata']['prepared_metadata'][str(self.book)], {'titulo': 'Proposed'})
        self.assertEqual(self.book.read_bytes(), before)
        self.assertTrue(needs_review({'encontrado': True, 'requiere_revision_manual': True}))

    def test_preparation_detects_source_change_and_can_resume_same_plan(self):
        store = OperationPlanStore(self.profile / 'plans.sqlite3')
        plan = store.create_plan('import_books', [{'source': self.book}])
        def analyzer(path):
            path.write_bytes(b'Changed')
            return {'encontrado': True}
        with self.assertRaises(PlanValidationError):
            prepare_import([self.book], store, analyzer, self.root, CancellationToken(), previous_plan=plan)
        self.assertEqual(store.get_plan(plan['id'])['state'], 'paused')
        self.assertEqual(len(store.list_resumable()), 1)

    def test_cancelled_preview_does_not_apply_files(self):
        token = CancellationToken()
        token.cancel()
        store = OperationPlanStore(self.profile / 'plans.sqlite3')
        with self.assertRaises(OperationCancelled):
            prepare_import([self.book], store, lambda path: self.fail('Analyzer must not run'), self.root, token)
        self.assertEqual(self.book.read_bytes(), b'Synthetic original')

    def test_catalog_only_application_keeps_uncertain_original_and_completes_plan(self):
        import library_core as core
        from library_app import App
        store = OperationPlanStore(self.profile / 'plans.sqlite3')
        plan = prepare_import([self.book], store, lambda path: {'titulo': 'Proposed', 'autor': 'Example',
                              'requiere_revision_manual': True, 'motivo': 'Conflicting sources'},
                              self.root / 'library', CancellationToken())
        app = SimpleNamespace(trabajando=False, cancel_token=CancellationToken(),
            bloquear=lambda value: None, _start_worker=lambda target: target(),
            _encolar_ui=lambda callback, *args: callback(*args), actualizar_label_indice=lambda: None,
            workspace=SimpleNamespace(refresh_library=lambda: None), estado=lambda text: None)
        with patch.multiple(core, INDICE_JSON=self.profile / 'index.json',
                            CATALOG_DB=self.profile / 'catalog.sqlite3'), patch.object(core, 'operation_plan_store', return_value=store):
            App._catalogar_plan(app, plan)
            persisted = core.cargar_indice()['archivos'][0]
        self.assertEqual(self.book.read_bytes(), b'Synthetic original')
        self.assertFalse((self.root / 'library').exists())
        self.assertTrue(persisted['linked'])
        self.assertTrue(persisted['review_required'])
        self.assertEqual(persisted['review_reason'], 'Conflicting sources')
        self.assertEqual(store.get_plan(plan['id'])['state'], 'completed')

    def test_cancel_catalog_only_keeps_empty_catalog_and_resumable_plan(self):
        import library_core as core
        from library_app import App
        store = OperationPlanStore(self.profile / 'plans.sqlite3')
        plan = prepare_import([self.book], store, lambda path: {}, self.root, CancellationToken())
        token = CancellationToken()
        token.cancel()
        app = SimpleNamespace(trabajando=False, cancel_token=token, bloquear=lambda value: None,
            _start_worker=lambda target: target(), _encolar_ui=lambda callback, *args: callback(*args),
            estado=lambda text: None)
        with patch.multiple(core, INDICE_JSON=self.profile / 'index.json',
                            CATALOG_DB=self.profile / 'catalog.sqlite3'), patch.object(core, 'operation_plan_store', return_value=store):
            App._catalogar_plan(app, plan)
            self.assertEqual(core.cargar_indice()['archivos'], [])
        self.assertEqual(self.book.read_bytes(), b'Synthetic original')
        self.assertEqual(store.get_plan(plan['id'])['state'], 'paused')

    def test_plan_live_owner_excludes_other_session_and_releases(self):
        store = OperationPlanStore(self.profile / 'plans.sqlite3')
        plan = store.create_plan('audit', [{'source': self.book}])
        store.set_plan_state(plan['id'], 'applying')
        other = OperationPlanStore(store.path)
        with self.assertRaises(PlanValidationError):
            other.set_plan_state(plan['id'], 'applying')
        store.set_plan_state(plan['id'], 'paused')
        other.set_plan_state(plan['id'], 'applying')

    def test_plan_dead_owner_is_recoverable(self):
        store = OperationPlanStore(self.profile / 'plans.sqlite3')
        plan = store.create_plan('audit', [{'source': self.book}])
        store.set_plan_state(plan['id'], 'applying')
        store.set_item_state(plan['id'], 0, 'running')
        with patch('core.operation_plans.process_is_alive', return_value=False):
            recovered = OperationPlanStore(store.path).get_plan(plan['id'])
        self.assertEqual(recovered['state'], 'paused')
        self.assertEqual(recovered['items'][0]['state'], 'pending')
        self.assertEqual(self.book.read_bytes(), b'Synthetic original')

    def test_profile_guard_excludes_second_instance_and_releases(self):
        with ProfileGuard(self.profile):
            with self.assertRaises(ProfileInUseError):
                with ProfileGuard(self.profile):
                    self.fail('Second profile owner')
        with ProfileGuard(self.profile):
            pass

    def test_plan_rejects_files_changed_while_hashing(self):
        from core.file_identity import FileChangedDuringReadError
        store = OperationPlanStore(self.profile / 'plans.sqlite3')
        plan = store.create_plan('audit', [{'source': self.book}])
        with patch('core.operation_plans.validated_sha256_file', side_effect=FileChangedDuringReadError('changed')):
            with self.assertRaises(PlanValidationError):
                store.create_plan('audit', [{'source': self.book}])
            with self.assertRaises(PlanValidationError):
                store.validate_item(plan['id'], 0)
        self.assertEqual(self.book.read_bytes(), b'Synthetic original')

    def test_hash_rejects_replaced_identity_even_with_equal_size_and_times(self):
        from core import file_identity
        with patch.object(file_identity, '_live_signature', side_effect=[(18, 1, 1, 2, 3), (18, 1, 1, 2, 4)]):
            with self.assertRaises(file_identity.FileChangedDuringReadError):
                file_identity.validated_sha256_file(self.book)

    def test_final_consensus_is_independent_of_duplicate_hits_and_order(self):
        from metadata.scoring import score_campo_consenso
        evidence = [{'field': 'title', 'value': 'Synthetic Book', 'confidence': 90, 'source': source}
                    for source in ('Open Library', 'Wikidata')]
        evidence.append({'field': 'title', 'value': 'Unrelated account', 'confidence': 95, 'source': 'Local'})
        original = score_campo_consenso('Synthetic Book', evidence, 'title')
        for count in (2, 10, 100):
            self.assertEqual(score_campo_consenso('Synthetic Book', list(reversed(evidence * count)), 'title'), original)
        self.assertLess(original[0], 82)

    def test_corrupt_saved_views_cannot_be_replaced_by_saving_another_view(self):
        from core.index_store import IndexRecoveryError
        from core.saved_views import save_view
        path = self.profile / 'saved_views.json'
        path.write_text('{broken', encoding='utf-8')
        with self.assertRaises(IndexRecoveryError):
            save_view(path, 'New filter', {'read': 'reading'})
        self.assertEqual(path.read_text(encoding='utf-8'), '{broken')

    def test_language_aliases_do_not_create_false_translation_conflicts(self):
        from book_identity_evidence import normalize_for_field
        for values in (('es', 'spa', 'español'), ('en', 'eng', 'English'), ('fr', 'fra', 'fre')):
            self.assertEqual(len({normalize_for_field('language', value) for value in values}), 1)

    def test_external_reader_bounds_output_and_timeout(self):
        with patch('core.document_readers.MAX_PROCESS_BYTES', 100):
            with self.assertRaisesRegex(RuntimeError, 'límite'):
                _run_bounded([sys.executable, '-c', 'import sys;sys.stdout.write("x"*10000)'], timeout=5)
        with self.assertRaisesRegex(RuntimeError, 'superó'):
            _run_bounded([sys.executable, '-c', 'import time;time.sleep(5)'], timeout=.2)

    def test_external_reader_cancel_is_acknowledged_without_ui_wait(self):
        token = CancellationToken()
        timer = threading.Timer(.2, token.cancel)
        timer.start()
        self.addCleanup(timer.join)
        with self.assertRaises(OperationCancelled):
            _run_bounded([sys.executable, '-c', 'import time;time.sleep(5)'], timeout=6, cancellation=token)

    def test_network_request_obeys_inherited_cancellation(self):
        token = CancellationToken()
        token.cancel()
        with external_providers.request_context(token), patch.object(external_providers.urllib.request, 'urlopen') as request:
            with self.assertRaises(OperationCancelled):
                external_providers.http_get('https://openlibrary.org/search.json?q=synthetic')
            request.assert_not_called()

    def test_cover_rejects_redirect_and_pixel_bomb_before_decode(self):
        with self.assertRaises(ValueError):
            SafeCoverRedirect().redirect_request(None, None, 302, '', {}, 'https://127.0.0.1/private')
        self.assertEqual(CoverService._validated_remote_url('https://covers.openlibrary.org:999/a'), '')
        class HugeImage:
            width, height = 50_000, 50_000
            def copy(self):
                raise AssertionError('Must not decode')
        with self.assertRaises(ValueError):
            _copy_bounded_image(HugeImage())

    def test_field_lock_does_not_claim_unedited_fields_are_confirmed(self):
        previous = {'titulo': 'Human', 'autor': 'Old', 'locked_fields': ['titulo'], 'manual_lock': True,
                    'confianza_global': 62, 'provenance': {'titulo': {'source': 'usuario'}}}
        row = merge_persistent_metadata({}, previous, {'titulo': 'Wrong', 'autor': 'New',
            'provenance': {'titulo': {'source': 'web'}, 'autor': {'source': 'web'}}})
        self.assertEqual(row['titulo'], 'Human')
        self.assertEqual(row['autor'], 'New')
        self.assertEqual(row['confianza_global'], 62)
        self.assertEqual(row['provenance']['titulo']['source'], 'usuario')

    def test_prepared_sort_and_single_row_update_keep_both_orders_consistent(self):
        from core.library_view_model import LibraryViewIndex
        rows = [{'ruta': str(self.root / f'{i}.txt'), 'titulo': f'Title {i}', 'mtime': i} for i in range(100)]
        view = LibraryViewIndex(rows)
        self.assertEqual(view.filter(recent=True)[0]['mtime'], 99)
        unaffected = view._by_path[rows[50]['ruta']]
        view.update_record({**rows[0], 'mtime': 1000, 'titulo': 'AAA'})
        self.assertEqual(view.filter(recent=True)[0]['mtime'], 1000)
        self.assertEqual(view.filter()[0]['titulo'], 'AAA')
        self.assertIs(view._by_path[rows[50]['ruta']], unaffected)

    def test_synthetic_contradiction_corpus_never_auto_renames(self):
        from bibliographic_validator import candidates_to_evidence
        from book_identity_scorer import score_identity, AUTO_RENAME
        # Property corpus, NOT an estimate of accuracy on real books.
        for number in range(500):
            field = ('language', 'volume', 'edition')[number % 3]
            first = {'source': 'Open Library', 'title': f'Synthetic title {number}', 'author': 'Example Author',
                     'isbn': '9780306406157', field: 'es' if field == 'language' else '1'}
            second = {**first, 'source': 'Wikidata', field: 'en' if field == 'language' else '2'}
            score = score_identity(candidates_to_evidence([first, second]))
            with self.subTest(number=number, field=field):
                self.assertTrue(score['conflicts'])
                self.assertNotEqual(score['decision'], AUTO_RENAME)

    def test_profile_backup_restore_preserves_catalog_plans_and_quarantine(self):
        legacy = self.profile / 'index.json'
        legacy.write_text(json.dumps({'archivos': [{'ruta': str(self.book), 'favorite': True}]}), encoding='utf-8')
        repository = CatalogRepository(self.profile / 'catalog.sqlite3', legacy)
        index = repository.load()
        store = OperationPlanStore(self.profile / 'plans.sqlite3')
        plan = store.create_plan('audit', [{'source': self.book}])
        for name, data in [('config.json', '{}'), ('journal.jsonl', '{"pending":true}'), ('quarantine/item.txt', 'recoverable')]:
            path = self.profile / name
            path.parent.mkdir(exist_ok=True)
            path.write_text(data, encoding='utf-8')
        target = self.root / 'backup.zip'
        create_backup(self.profile, target)
        restored = self.root / 'restored'
        restore_backup(target, restored)
        self.assertEqual(CatalogRepository(restored / 'catalog.sqlite3', restored / 'index.json').load(), index)
        self.assertEqual(OperationPlanStore(restored / 'plans.sqlite3').get_plan(plan['id'])['items'], plan['items'])
        self.assertEqual((restored / 'quarantine/item.txt').read_text(), 'recoverable')
        self.assertEqual(self.book.read_bytes(), b'Synthetic original')
        with self.assertRaises(FileExistsError):
            restore_backup(target, restored)
        with self.assertRaises(FileExistsError):
            create_backup(self.profile, target)

    def test_restore_rejects_path_traversal_before_writing(self):
        target = self.root / 'bad.zip'
        with zipfile.ZipFile(target, 'w') as archive:
            archive.writestr('../evil.txt', b'evil')
            archive.writestr('profile-manifest.json', json.dumps({'version': 1, 'files': {'../evil.txt': {}}}))
        with self.assertRaises(ValueError):
            restore_backup(target, self.root / 'restore')
        self.assertFalse((self.root / 'evil.txt').exists())

    def test_existing_projection_is_backed_up_before_activation(self):
        from core.catalog_store import CatalogStore
        database = self.profile / 'catalog.sqlite3'
        CatalogStore(database).sync_index({'archivos': [{'ruta': str(self.book), 'titulo': 'Older projection'}]})
        legacy = self.profile / 'index.json'
        legacy.write_text(json.dumps({'archivos': [{'ruta': str(self.book), 'titulo': 'Legacy authority'}]}))
        CatalogRepository(database, legacy).load()
        backups = list((self.profile / 'backups').glob('*.sqlite3'))
        self.assertEqual(len(backups), 1)
        with closing(sqlite3.connect(backups[0])) as con:
            self.assertEqual(con.execute('SELECT title FROM works').fetchone()[0], 'Older projection')

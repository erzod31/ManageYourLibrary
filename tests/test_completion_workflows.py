"""New behavior, fault injection and real disposable reader processes."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from core.cancellation import CancellationToken, OperationCancelled
from core.file_identity import sha256_file, validated_sha256_file
from core.file_transactions import restaurar_accion_undo, leer_jsonl, recuperar_transacciones_archivo_pendientes
from core.import_copy import copy_verified, import_copies
from core.import_preview import prepare_import, field_comparison
from core.library_view_model import LibraryViewIndex
from core.operation_plans import OperationPlanStore
from core.reader_worker import run_reader, ReaderFailure


# Deliberately hostile worker fixture. Only launched by fault-injection tests;
# the application's allowlist never accepts arbitrary commands or these modes.
FAULT_WORKER = '''
import json, sys, time, os
from pathlib import Path
request_path = Path(sys.argv[1])
while not (request_path.parent / 'ready').is_file(): time.sleep(.025)
request = json.loads(request_path.read_bytes())
mode = request['payload']['mode']
if mode == 'hang': time.sleep(60)
if mode == 'crash': os._exit(71)
if mode == 'memory':
    allocations = []
    while True: allocations.append(bytearray(16 * 1024 * 1024))
if mode == 'oversize':
    Path(request['output']).write_bytes(b'x' * (17 * 1024 * 1024))
else:
    Path(request['output']).write_text(json.dumps({'ok': True, 'value': True}))
'''


class CompletionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.profile = self.root / 'profile'
        self.library = self.root / 'library'
        self.library.mkdir()
        self.source = self.root / 'original.txt'
        self.source.write_bytes(b'Original synthetic book.\n' * 100)
        self.digest = sha256_file(self.source)
        self.journal = self.profile / 'file_transactions.jsonl'

    def test_real_reader_is_a_different_process(self):
        result = run_reader('probe', {})
        self.assertTrue(result['isolated'])
        self.assertNotEqual(result['pid'], os.getpid())

    def test_reader_transport_works_without_console_stdin(self):
        from core import reader_worker
        request_path = self.root / 'request.json'
        result_path = self.root / 'result.json'
        request_path.write_text(json.dumps({'kind': 'probe', 'payload': {},
                                           'memory_mb': 1024, 'output': str(result_path)}))
        (self.root / 'ready').touch()
        # Avoid applying POSIX process limits to the test runner itself.
        with patch.object(reader_worker, '_set_posix_limits'), patch.object(sys, 'stdin', None), \
                patch.object(reader_worker, '_IN_WORKER', False):
            self.assertEqual(reader_worker.worker_main(request_path), 0)
        self.assertTrue(json.loads(result_path.read_bytes())['ok'])

    def fault(self, mode, **kwargs):
        popen = subprocess.Popen
        processes = []
        def spawn(command, **options):
            process = popen([sys.executable, '-B', '-c', FAULT_WORKER, command[-1]], **options)
            processes.append(process)
            return process
        with patch('core.reader_worker.subprocess.Popen', side_effect=spawn):
            with self.assertRaises((ReaderFailure, OperationCancelled)):
                run_reader('probe', {'mode': mode}, **kwargs)
        self.assertTrue(processes)
        self.assertIsNotNone(processes[0].poll(), 'Worker leaked after failure')

    def test_reader_hang_has_hard_timeout_and_is_reaped(self):
        self.fault('hang', timeout=.3)

    def test_reader_crash_is_contained(self):
        self.fault('crash')

    @unittest.skipUnless(os.name == 'nt', 'Fault fixture tests Windows Job memory cap; POSIX worker uses RLIMIT_AS')
    def test_reader_job_enforces_real_memory_limit(self):
        self.fault('memory', memory_mb=96, timeout=10)

    def test_reader_output_is_bounded(self):
        self.fault('oversize')

    def test_reader_can_be_cancelled_while_hung(self):
        token = CancellationToken()
        timer = threading.Timer(.3, token.cancel)
        timer.start()
        try:
            self.fault('hang', cancellation=token, timeout=10)
        finally:
            timer.cancel()

    def test_hash_cancelled_before_and_during_read(self):
        token = CancellationToken()
        token.cancel()
        with self.assertRaises(OperationCancelled):
            validated_sha256_file(self.source, cancellation=token)
        calls = 0
        class Token:
            def raise_if_cancelled(self):
                nonlocal calls
                calls += 1
                if calls == 3:
                    raise OperationCancelled('cancel')
        with self.assertRaises(OperationCancelled):
            sha256_file(self.source, block_size=10, cancellation=Token())
        self.assertEqual(calls, 3)

    def copy(self, destination=None, **kwargs):
        return copy_verified(self.source, destination or self.library / 'copy.txt', expected_hash=self.digest,
                             journal_path=self.journal, app_data=self.profile, **kwargs)

    def test_copy_and_undo_preserve_original_and_quarantine_copy(self):
        result = self.copy()
        self.assertEqual(sha256_file(self.source), self.digest)
        self.assertEqual(sha256_file(Path(result['destination'])), self.digest)
        ok, location = restaurar_accion_undo({'tipo': 'copiar', 'origen': str(self.source),
            'destino': result['destination'], 'sha256': self.digest}, journal_path=self.journal, app_data=self.profile)
        self.assertTrue(ok, location)
        self.assertEqual(sha256_file(self.source), self.digest)
        self.assertEqual(sha256_file(Path(location)), self.digest)
        self.assertIn('undone-copies', location)

    def test_copy_never_overwrites_existing_file(self):
        destination = self.library / 'copy.txt'
        destination.write_bytes(b'Existing book')
        with self.assertRaises(FileExistsError):
            self.copy(destination)
        self.assertEqual(destination.read_bytes(), b'Existing book')

    def test_copy_refuses_source_changed_after_preview(self):
        self.source.write_bytes(b'Changed')
        with self.assertRaises(RuntimeError):
            self.copy()
        self.assertEqual(list(self.library.iterdir()), [])

    def make_plan(self, review=False):
        store = OperationPlanStore(self.profile / 'plans.sqlite3')
        plan = prepare_import([self.source], store, lambda path: {
            'titulo': 'Synthetic', 'autor': 'Fixture Author', 'nombre_sugerido': 'copy.txt',
            'encontrado': True, 'requiere_revision_manual': review}, self.library, CancellationToken())
        return store, plan

    def test_copy_import_resumes_after_catalog_failure_without_second_copy(self):
        store, plan = self.make_plan()
        def fail(*args):
            raise RuntimeError('catalog unavailable')
        with self.assertRaises(RuntimeError):
            import_copies(plan, store, library=self.library, journal_path=self.journal, app_data=self.profile,
                          cancellation=CancellationToken(), catalog_copy=fail)
        self.assertEqual(len(list(self.library.glob('*.txt'))), 1)
        recorded = []
        resumed = import_copies(store.get_plan(plan['id']), store, library=self.library, journal_path=self.journal,
                                app_data=self.profile, cancellation=CancellationToken(),
                                catalog_copy=lambda *args: recorded.append(args))
        self.assertEqual(resumed['state'], 'completed')
        self.assertEqual(len(recorded), 1)
        self.assertEqual(len(list(self.library.glob('*.txt'))), 1)
        self.assertEqual(sha256_file(self.source), self.digest)

    def test_ambiguous_copy_import_stays_pending(self):
        store, plan = self.make_plan(review=True)
        result = import_copies(plan, store, library=self.library, journal_path=self.journal, app_data=self.profile,
                               cancellation=CancellationToken(), catalog_copy=lambda *args: self.fail('Ambiguous item copied'))
        self.assertEqual(result['state'], 'paused')
        self.assertEqual(list(self.library.iterdir()), [])

    def test_comparison_preserves_confirmed_fields(self):
        rows = field_comparison({'titulo': 'Confirmed', 'locked_fields': ['titulo']},
                                {'titulo': 'Proposed', 'autor': 'Writer', 'fuente': 'local', 'motivo': 'evidence'})
        self.assertEqual(rows[0]['effective'], 'Confirmed')
        self.assertEqual(rows[1]['effective'], 'Writer')
        self.assertEqual(rows[1]['reason'], 'evidence')

    def test_entity_navigation_is_exact_not_substring_matching(self):
        index = LibraryViewIndex([{'ruta': 'one.epub', 'autor': 'Ana', 'serie': 'Sea', 'tags': ['History']},
                                  {'ruta': 'two.epub', 'autor': 'Anabel', 'serie': 'Sea', 'tags': ['History', 'Blue']}])
        self.assertEqual(len(index.entities('authors')), 2)
        self.assertEqual(index.entities('series')[0]['count'], 2)
        self.assertEqual(len(index.entity_books('authors', 'ana', index.filter())), 1)
        index.update_record({'ruta': 'one.epub', 'autor': 'Anabel', 'serie': 'Moon'})
        self.assertEqual(index.entities('authors'), [{'key': 'anabel', 'name': 'Anabel', 'count': 2}])
        self.assertEqual(index.entities('tags')[0]['count'], 1)

    def test_copy_recovery_never_moves_staging_over_original(self):
        result = self.copy()
        rows = leer_jsonl(self.journal)
        from core.file_transactions import append_jsonl_durable
        append_jsonl_durable(self.journal, {**rows[-1], 'state': 'staged'})
        recuperar_transacciones_archivo_pendientes(self.journal, self.profile)
        self.assertEqual(leer_jsonl(self.journal)[-1]['state'], 'committed_recovered')
        self.assertEqual(sha256_file(self.source), self.digest)
        self.assertEqual(sha256_file(Path(result['destination'])), self.digest)

    def test_failed_reader_becomes_review_and_does_not_abort_other_previews(self):
        store = OperationPlanStore(self.profile / 'plans.sqlite3')
        def broken(path):
            raise ReaderFailure('Timed out')
        plan = prepare_import([self.source], store, broken, self.library, CancellationToken())
        self.assertEqual(plan['state'], 'preview')
        self.assertTrue(plan['metadata']['prepared_metadata'][str(self.source)]['requiere_revision_manual'])

    def test_verified_move_retains_id_and_corrections_with_location_history(self):
        from core.catalog_repository import CatalogRepository
        from core.index_service import update_paths
        # Use the transaction implementation through the repository's public
        # adapter, with an explicit temporary library/profile.
        from core.file_transactions import _mover_verificado, iniciar_transaccion_archivo, actualizar_transaccion_archivo
        repository = CatalogRepository(self.profile / 'catalog.sqlite3', self.profile / 'legacy.json')
        initial = {'archivos': [{'ruta': str(self.source), 'nombre': self.source.name, 'sha256': self.digest,
                                'titulo': 'Confirmed title', 'autor': 'Confirmed author', 'favorite': True,
                                'locked_fields': ['titulo'], 'linked': True}]}
        repository.save(initial)
        old_id = repository.store.record_for_path(self.source)['file_id']
        destination = self.library / 'moved.txt'
        op = iniciar_transaccion_archivo(self.journal, self.profile, 'move', self.source, destination)
        _mover_verificado(self.source, destination, journal_path=self.journal, app_data=self.profile,
                         op_id=op, tipo='move', hash_esperado=self.digest)
        actualizar_transaccion_archivo(self.journal, self.profile, op, 'committed', 'move',
                                      self.source, destination, hash_archivo=self.digest)
        updated = update_paths(initial, [self.source, destination], library_root=self.library,
                               build_item=lambda p, n: {'ruta': str(p), 'nombre': n, 'sha256': sha256_file(p)},
                               committed_moves=leer_jsonl(self.journal))
        repository.save(updated)
        self.assertEqual(repository.store.record_for_path(destination)['file_id'], old_id)
        self.assertEqual(repository.load()['archivos'][0]['titulo'], 'Confirmed title')
        self.assertTrue(repository.load()['archivos'][0]['favorite'])
        with repository.store._db() as con:
            self.assertEqual(con.execute('SELECT COUNT(*) FROM file_location_history').fetchone()[0], 1)
        # Reusing the vacated path must allocate a different file identity.
        self.source.write_bytes(b'Different book')
        updated['archivos'].append({'ruta': str(self.source), 'sha256': sha256_file(self.source)})
        repository.save(updated)
        self.assertNotEqual(repository.store.record_for_path(self.source)['file_id'], old_id)

    def test_versioned_evaluation_has_no_unsafe_decisions(self):
        from tools.evaluate_corpus import evaluate, CORPUS
        corpus = json.loads(CORPUS.read_text(encoding='utf-8'))
        tuning = {case['id'] for case in corpus['cases'] if case['split'] == 'tuning'}
        evaluation = {case['id'] for case in corpus['cases'] if case['split'] == 'evaluation'}
        self.assertFalse(tuning & evaluation)
        report = evaluate()
        self.assertEqual(report['unsafe_decisions'], 0)
        self.assertEqual(report['count'], 12)
        self.assertGreater(report['automatic_count'], 0)

    def test_large_catalog_gc_guard_keeps_gc_on_and_releases_ownership(self):
        import gc
        from core.catalog_gc import CatalogGcGuard
        # Do not change the test runner's global GC generations. The real
        # standalone lifecycle is exercised by benchmark_ui in a new process.
        with patch.object(gc, 'collect'), patch.object(gc, 'freeze') as freeze, patch.object(gc, 'unfreeze') as unfreeze:
            guard = CatalogGcGuard(10_000)
            self.assertTrue(gc.isenabled())
            try:
                self.assertTrue(guard.owned)
                freeze.assert_called_once()
                other = CatalogGcGuard(20_000)
                self.assertFalse(other.owned)
                other.close()
                unfreeze.assert_not_called()
            finally:
                guard.close()
            unfreeze.assert_called_once()

    def test_preview_can_resume_completed_analysis_without_repeating_reader(self):
        store = OperationPlanStore(self.profile / 'plans.sqlite3')
        second = self.root / 'second.txt'
        second.write_bytes(b'Second synthetic file')
        token = CancellationToken()
        def progress(done, total):
            if done == 1:
                token.cancel()
        with self.assertRaises(OperationCancelled):
            prepare_import([self.source, second], store, lambda path: {'titulo': path.stem},
                           self.library, token, progress)
        pending = store.list_resumable()[0]
        analyzed = []
        resumed = prepare_import([self.source, second], store, lambda path: analyzed.append(path) or {'titulo': path.stem},
                                 self.library, CancellationToken(), previous_plan=pending)
        self.assertEqual(analyzed, [second])
        self.assertEqual(len(resumed['metadata']['prepared_metadata']), 2)

    def test_preview_cannot_rename_against_human_correction(self):
        store = OperationPlanStore(self.profile / 'plans.sqlite3')
        plan = prepare_import([self.source], store, lambda path: {'titulo': 'Automatic', 'encontrado': True},
                              self.library, CancellationToken(), previous_catalog={'archivos': [
                                  {'ruta': str(self.source), 'titulo': 'Confirmed', 'locked_fields': ['titulo']}]})
        self.assertTrue(plan['metadata']['prepared_metadata'][str(self.source)]['requiere_revision_manual'])

    def test_resumed_preview_rechecks_new_human_corrections(self):
        store, plan = self.make_plan()
        resumed = prepare_import([self.source], store, lambda path: self.fail('Reader repeated'),
            self.library, CancellationToken(), previous_plan=plan,
            previous_catalog={'archivos': [{'ruta': str(self.source), 'titulo': 'Confirmed later',
                                           'locked_fields': ['titulo']}]})
        self.assertTrue(resumed['metadata']['prepared_metadata'][str(self.source)]['requiere_revision_manual'])

    def test_scan_missing_or_inaccessible_root_does_not_save_empty_catalog(self):
        import library_core as core
        with patch.object(core, 'FINAL', self.root / 'missing'), patch.object(core, 'biblioteca_configurada', return_value=True):
            with self.assertRaises(FileNotFoundError):
                core.buscar_libros_final()
        def inaccessible(*args, **kwargs):
            kwargs['onerror'](PermissionError('synthetic denied directory'))
            return []
        with patch.object(core, 'FINAL', self.library), patch.object(core, 'biblioteca_configurada', return_value=True), \
                patch.object(core.os, 'walk', side_effect=inaccessible):
            with self.assertRaises(OSError):
                core.buscar_libros_final()


if __name__ == '__main__':
    unittest.main()

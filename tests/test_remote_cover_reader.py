"""Remote cover isolation with inert transports and one real retained process."""
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

from core import cover_service as covers
from core import reader_worker
from core.cancellation import OperationCancelled

URL = 'https://covers.openlibrary.org/b/isbn/9780306406157-M.jpg'

# This transport exists only in the test child. The real worker dispatcher,
# request handshake, OS limits, cancellation and process cleanup still run.
# It cannot access the network or the original synthetic book/profile.
BLOCKED_HTTP_WORKER = r'''
import sys, time
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0, sys.argv[2])
from core import cover_service, reader_worker
request_path = Path(sys.argv[1])
class Response:
    status = 200
    headers = {'Content-Type': 'image/png'}
    def __init__(self, url): self.url = url
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def geturl(self): return self.url
    def read(self, limit):
        (request_path.parent / 'http-read-entered').write_bytes(b'entered')
        time.sleep(60)
        return b''
cover_service.urllib.request.build_opener = lambda *handlers: SimpleNamespace(
    open=lambda request, timeout: Response(request.full_url))
raise SystemExit(reader_worker.worker_main(request_path))
'''


class Response:
    def __init__(self, data, *, url=URL, status=200, headers=None):
        self.data, self.url, self.status = data, url, status
        self.headers = {'Content-Type': 'image/png'} if headers is None else headers
        self.read_limits = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def geturl(self):
        return self.url

    def read(self, limit):
        self.read_limits.append(limit)
        return self.data[:limit]


class RemoteCoverReaderTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        offline = patch.dict(os.environ, {'MANAGE_YOUR_LIBRARY_OFFLINE': '0'})
        offline.start()
        self.addCleanup(offline.stop)

    @staticmethod
    def png():
        raw = io.BytesIO()
        Image.new('RGB', (16, 24), 'teal').save(raw, 'PNG')
        return raw.getvalue()

    def test_parent_sends_only_url_and_size_and_never_opens_http(self):
        service = covers.CoverService(self.root / 'cache', size=(80, 112))
        with patch.object(covers, 'run_reader', return_value=None) as reader, \
                patch.object(covers.urllib.request, 'build_opener', side_effect=AssertionError('Parent HTTP')), \
                patch.object(service, '_wait_remote_turn') as rate:
            self.assertIsNone(service._fetch_remote(URL))
        rate.assert_called_once()
        reader.assert_called_once_with(
            'remote_cover', {'url': URL, 'size': (80, 112)},
            timeout=covers.REMOTE_WORKER_TIMEOUT_SECONDS, memory_mb=512, cancellation=service.cancellation,
        )

    def test_worker_parser_accepts_injected_transport_and_returns_bounded_rgb(self):
        response = Response(self.png())
        opener = SimpleNamespace(open=lambda *_args, **_kwargs: response)
        with patch.object(reader_worker, '_IN_WORKER', True), \
                patch.object(covers.urllib.request, 'build_opener', return_value=opener):
            result = reader_worker._dispatch('remote_cover', {'url': URL, 'size': [8, 12]})
        image = reader_worker.decode_image_result(result)
        try:
            self.assertEqual(image.size, (8, 12))
        finally:
            image.close()
        self.assertEqual(response.read_limits, [covers.MAX_REMOTE_IMAGE_BYTES + 1])

    def test_worker_rejects_extra_document_fields_hosts_and_invalid_sizes_before_http(self):
        payloads = [
            {'url': URL, 'size': [80, 112], 'path': 'a-book.epub'},
            {'url': URL, 'size': [80, 112], 'content': 'book contents'},
            {'url': 'https://example.invalid/cover.png', 'size': [80, 112]},
            {'url': 'http://covers.openlibrary.org/cover.png', 'size': [80, 112]},
            {'url': URL, 'size': [0, 112]},
            {'url': URL, 'size': [80, 2049]},
        ]
        with patch.object(reader_worker, '_IN_WORKER', True), \
                patch.object(covers.urllib.request, 'build_opener') as opener:
            for payload in payloads:
                with self.subTest(payload=payload), self.assertRaises(ValueError):
                    reader_worker._dispatch('remote_cover', payload)
            opener.assert_not_called()

    def test_worker_preserves_status_redirect_type_byte_and_pixel_limits(self):
        responses = [Response(self.png(), status=404),
                     Response(self.png(), url='https://example.invalid/cover.png'),
                     Response(self.png(), headers={'Content-Type': 'text/html'}),
                     Response(self.png(), headers={'Content-Length': str(covers.MAX_REMOTE_IMAGE_BYTES + 1)})]
        with patch.object(reader_worker, '_IN_WORKER', True):
            for response in responses:
                service = covers.CoverService(self.root / 'cache', urlopen_func=lambda *_a, _response=response, **_kw: _response)
                with self.subTest(status=response.status, url=response.url, headers=response.headers):
                    self.assertIsNone(service._fetch_remote(URL))
                    self.assertEqual(response.read_limits, [])
            oversized = Response(b'x' * 33)
            service = covers.CoverService(self.root / 'cache', urlopen_func=lambda *_a, **_kw: oversized)
            with patch.object(covers, 'MAX_REMOTE_IMAGE_BYTES', 32):
                self.assertIsNone(service._fetch_remote(URL))
            self.assertEqual(oversized.read_limits, [33])
            service = covers.CoverService(self.root / 'cache', urlopen_func=lambda *_a, **_kw: Response(self.png()))
            with patch.object(covers, 'MAX_IMAGE_PIXELS', 1):
                self.assertIsNone(service._fetch_remote(URL))

    def test_offline_covers_never_start_http_and_document_workers_always_stay_offline(self):
        service = covers.CoverService(self.root / 'cache')
        with patch.dict(os.environ, {'MANAGE_YOUR_LIBRARY_OFFLINE': '1'}), \
                patch.object(covers, 'run_reader') as reader, \
                patch.object(covers.urllib.request, 'build_opener') as opener:
            self.assertIsNone(service._fetch_remote(URL))
            with patch.object(reader_worker, '_IN_WORKER', True):
                self.assertIsNone(reader_worker._dispatch('remote_cover', {'url': URL, 'size': [80, 112]}))
            self.assertEqual(reader_worker._reader_environment('remote_cover')['MANAGE_YOUR_LIBRARY_OFFLINE'], '1')
            reader.assert_not_called()
            opener.assert_not_called()
        with patch.dict(os.environ, {'MANAGE_YOUR_LIBRARY_OFFLINE': '0'}):
            self.assertEqual(reader_worker._reader_environment('remote_cover')['MANAGE_YOUR_LIBRARY_OFFLINE'], '0')
            for kind in ('local_fast', 'local_full', 'document', 'ocr_file', 'cover', 'image_decode'):
                self.assertEqual(reader_worker._reader_environment(kind)['MANAGE_YOUR_LIBRARY_OFFLINE'], '1')

    def test_global_rate_limit_is_shared_by_parent_instances(self):
        moments = []
        with patch.object(covers.CoverService, '_last_remote_request', 0), \
                patch.object(covers.CoverService, '_remote_interval_seconds', .04), \
                patch.object(covers, 'run_reader', side_effect=lambda *_a, **_kw: moments.append(time.monotonic())):
            covers.CoverService(self.root / 'one')._fetch_remote(URL)
            covers.CoverService(self.root / 'two')._fetch_remote(URL)
        self.assertGreaterEqual(moments[1] - moments[0], .035)

    def test_cancel_while_waiting_for_parent_rate_lock_starts_no_process(self):
        service = covers.CoverService(self.root / 'cache')
        entered = threading.Event()
        wait = service._wait_remote_turn
        def wait_turn():
            entered.set()
            wait()
        with ThreadPoolExecutor(max_workers=1) as pool, patch.object(covers, 'run_reader') as reader, \
                patch.object(service, '_wait_remote_turn', side_effect=wait_turn):
            service._remote_lock.acquire()
            try:
                future = pool.submit(service._fetch_remote, URL)
                self.assertTrue(entered.wait(1))
                service.cancellation.cancel()
                with self.assertRaises(OperationCancelled):
                    future.result(timeout=1)
                reader.assert_not_called()
            finally:
                service._remote_lock.release()

    def test_cancel_reaps_real_process_blocked_in_http_and_preserves_originals(self):
        source = self.root / 'original.mobi'
        source.write_bytes(b'Synthetic original book; never sent to remote reader.')
        profile = self.root / 'profile'
        profile.mkdir()
        sentinel = profile / 'state.json'
        sentinel.write_bytes(b'{"synthetic_preserved": true}')
        original = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in (source, sentinel)}
        service = covers.CoverService(self.root / 'cache')
        real_popen, processes, requests = subprocess.Popen, [], []

        def spawn(command, **options):
            request_path = Path(command[-1])
            request = json.loads(request_path.read_bytes())
            self.assertEqual(request['kind'], 'remote_cover')
            self.assertEqual(request['payload'], {'url': URL, 'size': [120, 172]})
            requests.append(request_path)
            process = real_popen([sys.executable, '-B', '-c', BLOCKED_HTTP_WORKER,
                                  str(request_path), str(Path(__file__).resolve().parents[1])], **options)
            processes.append(process)
            return process

        with ThreadPoolExecutor(max_workers=1) as pool, \
                patch.object(reader_worker.subprocess, 'Popen', side_effect=spawn), \
                patch.object(covers.urllib.request, 'build_opener', side_effect=AssertionError('Parent HTTP')):
            future = pool.submit(service.thumbnail_path, source, URL)
            try:
                deadline = time.monotonic() + 8
                while not requests or not (requests[0].parent / 'http-read-entered').exists():
                    if future.done():
                        future.result()  # Show an actual startup/dispatch error.
                        self.fail('Reader completed before the retained HTTP transport')
                    if time.monotonic() >= deadline:
                        self.fail('Real child did not enter its retained HTTP read')
                    time.sleep(.01)
                started = time.monotonic()
                service.cancellation.cancel()
                with self.assertRaises(OperationCancelled):
                    future.result(timeout=4)
                self.assertLess(time.monotonic() - started, 4)
                self.assertTrue(processes)
                self.assertTrue(all(process.poll() is not None for process in processes), 'Remote reader leaked')
                self.assertFalse((self.root / 'cache').exists(), 'Cancelled download wrote a miss/cache entry')
            finally:
                service.cancellation.cancel()
        self.assertEqual({p: hashlib.sha256(p.read_bytes()).hexdigest() for p in original}, original)

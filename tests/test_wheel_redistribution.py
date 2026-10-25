"""Fail-closed wheel provenance checks with inert synthetic files only."""
import base64
import copy
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import call, patch
from urllib.error import HTTPError, URLError

from tools import verify_wheel_redistribution as verifier


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


class Response(io.BytesIO):
    def geturl(self):
        return 'https://example.invalid/pinned-license'


class WheelRedistributionTests(unittest.TestCase):
    def fixture(self, root):
        raw_notice = b'Unmodified synthetic license\n'
        catalog = {'schema': 1, 'profile': 'fixture-v1', 'scope': 'bounded-fixture',
                   'families': [{'name': 'example', 'version': '1.0', 'metadata': 'example.dist-info/METADATA',
                                 'wheel': {'filename': 'example.whl', 'sha256': '1' * 64},
                                 'binaries': {'example/native.pyd': digest(b'fake PE bytes')},
                                 'notices': {'example.dist-info/LICENSE': digest(b'fake upstream notice')},
                                 'inventory': {'directory': 'example', 'suffix': '.pyd'}}],
                   'supplemental_directory': 'licenses/wheels',
                   'supplemental_notices': [{'path': 'codec/LICENSE.txt', 'encoding': 'utf-8',
                                             'url': 'https://example.invalid/pinned-license', 'sha256': digest(raw_notice)}],
                   'required_acknowledgements': ['Acknowledged synthetic library.']}
        catalog_path = root / 'catalog.json'
        catalog_path.write_text(json.dumps(catalog), encoding='utf-8')
        catalog_patch = patch.object(verifier, 'CATALOG', catalog_path)
        self.addCleanup(catalog_patch.stop)
        catalog_patch.start()
        internal = root / 'payload/_internal'
        for relative, value in {'example.dist-info/METADATA': b'Name: example\nVersion: 1.0\n',
                                'example/native.pyd': b'fake PE bytes',
                                'example.dist-info/LICENSE': b'fake upstream notice',
                                'THIRD_PARTY_NOTICES.md': b'Acknowledged synthetic library.'}.items():
            path = internal / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(value)
        output = internal / 'licenses/wheels'
        with patch.object(verifier.urllib.request, 'urlopen', return_value=Response(raw_notice)):
            verifier.collect_notices(output)
        return root / 'payload', catalog, catalog_path

    def test_complete_pinned_fixture_passes_without_importing_payload_code(self):
        with tempfile.TemporaryDirectory() as directory:
            payload, _, _ = self.fixture(Path(directory))
            report = verifier.verify_windows_payload(payload)
            self.assertTrue(report['passed'])
            self.assertEqual(report['global_redistribution_review'], 'not_approved_by_this_check')
            self.assertNotIn(str(Path(directory)), json.dumps(report))

    def test_changed_binary_notice_version_and_receipt_are_rejected(self):
        for relative, replacement in (('example/native.pyd', b'tampered'),
                                       ('example.dist-info/LICENSE', b'tampered'),
                                       ('example.dist-info/METADATA', b'Name: example\nVersion: 2.0\n'),
                                       ('licenses/wheels/codec/LICENSE.txt', b'tampered'),
                                       ('licenses/wheels/receipt.json', b'{}'),
                                       ('THIRD_PARTY_NOTICES.md', b'missing acknowledgement')):
            with self.subTest(relative=relative), tempfile.TemporaryDirectory() as directory:
                payload, _, _ = self.fixture(Path(directory))
                (payload / '_internal' / relative).write_bytes(replacement)
                with self.assertRaises(ValueError):
                    verifier.verify_windows_payload(payload)

    def test_missing_and_extra_native_files_fail(self):
        for extra in (False, True):
            with tempfile.TemporaryDirectory() as directory:
                payload, _, _ = self.fixture(Path(directory))
                if extra:
                    (payload / '_internal/example/unreviewed.pyd').write_bytes(b'new native bytes')
                else:
                    (payload / '_internal/example/native.pyd').unlink()
                with self.assertRaises(ValueError):
                    verifier.verify_windows_payload(payload)

    def test_copyleft_dll_cannot_be_added_outside_the_wheel_subdirectory(self):
        with tempfile.TemporaryDirectory() as directory:
            payload, _, _ = self.fixture(Path(directory))
            (payload / '_internal/fribidi.dll').write_bytes(b'new binary')
            with self.assertRaisesRegex(ValueError, 'copyleft native'):
                verifier.verify_windows_payload(payload)

    def test_collector_refuses_overwrite_and_preserves_exact_base64_decoded_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, catalog, path = self.fixture(root)
            catalog['supplemental_notices'][0]['encoding'] = 'base64'
            path.write_text(json.dumps(catalog))
            output = root / 'fresh-notices'
            data = b'Unmodified synthetic license\n'
            with patch.object(verifier.urllib.request, 'urlopen', return_value=Response(base64.b64encode(data))):
                verifier.collect_notices(output)
            self.assertEqual((output / 'codec/LICENSE.txt').read_bytes(), data)
            with self.assertRaises(FileExistsError):
                verifier.collect_notices(output)

    def test_wrong_download_hash_has_no_success_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            output = root / 'bad-notices'
            with patch.object(verifier.urllib.request, 'urlopen', return_value=Response(b'tampered')) as request, \
                    patch.object(verifier.time, 'sleep') as sleep:
                with self.assertRaises(ValueError):
                    verifier.collect_notices(output)
                request.assert_called_once()
                sleep.assert_not_called()
            self.assertFalse((output / 'receipt.json').exists())

    def test_transient_http_failure_retries_the_same_pinned_request_then_succeeds(self):
        for code in (429, 500, 502, 503, 504):
            with self.subTest(code=code), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                _, catalog, _ = self.fixture(root)
                output = root / 'retry-notices'
                url = catalog['supplemental_notices'][0]['url']
                failure = HTTPError(url, code, 'transient', {}, None)
                with patch.object(verifier.urllib.request, 'urlopen', side_effect=[
                        failure, Response(b'Unmodified synthetic license\n')]) as request, \
                        patch.object(verifier.time, 'sleep') as sleep:
                    verifier.collect_notices(output)
                self.assertEqual(request.call_count, 2)
                self.assertEqual([c.args[0].full_url for c in request.call_args_list], [url, url])
                self.assertEqual([c.kwargs['timeout'] for c in request.call_args_list], [30, 30])
                sleep.assert_called_once_with(1)
                self.assertEqual((output / 'codec/LICENSE.txt').read_bytes(), b'Unmodified synthetic license\n')
                self.assertTrue((output / 'receipt.json').is_file())

    def test_persistent_transient_failure_is_bounded_and_has_no_success_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, catalog, _ = self.fixture(root)
            url = catalog['supplemental_notices'][0]['url']
            failures = [HTTPError(url, 503, 'unavailable', {}, None) for _ in range(3)]
            output = root / 'unavailable-notices'
            with patch.object(verifier.urllib.request, 'urlopen', side_effect=failures) as request, \
                    patch.object(verifier.time, 'sleep') as sleep:
                with self.assertRaises(HTTPError):
                    verifier.collect_notices(output)
                self.assertEqual(request.call_count, 3)
                self.assertEqual(sleep.call_args_list, [call(1), call(2)])
            self.assertFalse((output / 'receipt.json').exists())

    def test_transport_timeouts_at_open_or_read_retry_then_succeed(self):
        for phase in ('open', 'wrapped', 'read'):
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.fixture(root)
                first = TimeoutError('timed out')
                if phase == 'wrapped':
                    first = URLError(first)
                elif phase == 'read':
                    first = Response(b'')
                    first.read = lambda _limit: (_ for _ in ()).throw(TimeoutError('timed out reading'))
                output = root / 'timeout-notices'
                with patch.object(verifier.urllib.request, 'urlopen', side_effect=[
                        first, Response(b'Unmodified synthetic license\n')]) as request, \
                        patch.object(verifier.time, 'sleep') as sleep:
                    verifier.collect_notices(output)
                self.assertEqual(request.call_count, 2)
                sleep.assert_called_once_with(1)
                self.assertTrue((output / 'receipt.json').is_file())

    def test_not_found_and_non_timeout_transport_errors_are_not_retried(self):
        failures = [HTTPError('https://example.invalid/pinned-license', 404, 'not found', {}, None),
                    URLError(ConnectionRefusedError('refused'))]
        for failure in failures:
            with self.subTest(error=type(failure).__name__), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.fixture(root)
                output = root / 'permanent-failure'
                with patch.object(verifier.urllib.request, 'urlopen', side_effect=failure) as request, \
                        patch.object(verifier.time, 'sleep') as sleep:
                    with self.assertRaises(type(failure)):
                        verifier.collect_notices(output)
                    request.assert_called_once()
                    sleep.assert_not_called()
                self.assertFalse((output / 'receipt.json').exists())

    def test_oversized_notice_has_no_success_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            output = root / 'oversized-notices'
            with patch.object(verifier.urllib.request, 'urlopen', return_value=Response(b'x' * (verifier.MAX_NOTICE + 1))), self.assertRaisesRegex(ValueError, 'Oversized'):
                verifier.collect_notices(output)
            self.assertFalse((output / 'receipt.json').exists())

    def test_cross_host_redirect_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            response = Response(b'Unmodified synthetic license\n')
            response.geturl = lambda: 'https://unreviewed.invalid/license'
            with patch.object(verifier.urllib.request, 'urlopen', return_value=response), self.assertRaisesRegex(ValueError, 'redirect'):
                verifier.collect_notices(root / 'redirected')

    def test_unsafe_catalog_paths_fail_before_download(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, catalog, path = self.fixture(root)
            for value in ('../escape.txt', 'C:/escape.txt', 'codec\\escape.txt', '/escape.txt'):
                changed = copy.deepcopy(catalog)
                changed['supplemental_notices'][0]['path'] = value
                path.write_text(json.dumps(changed))
                with self.subTest(path=value), patch.object(verifier.urllib.request, 'urlopen') as request:
                    with self.assertRaises(ValueError):
                        verifier.collect_notices(root / 'unsafe')
                    request.assert_not_called()

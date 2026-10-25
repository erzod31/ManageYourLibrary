"""Fail-closed wheel provenance checks with inert synthetic files only."""
import base64
import copy
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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
            with patch.object(verifier.urllib.request, 'urlopen', return_value=Response(b'tampered')), self.assertRaises(ValueError):
                verifier.collect_notices(output)
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

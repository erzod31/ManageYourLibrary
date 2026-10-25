import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import verify_python_license_payload as verifier


class PythonLicensePayloadTests(unittest.TestCase):
    def fixture(self, root):
        payload = root / 'payload'
        base = payload / '_internal/licenses/python-runtime'
        base.mkdir(parents=True)
        raw = b'Unmodified upstream notice'
        raw_hash = hashlib.sha256(raw).hexdigest()
        catalog = {'python_version': '3.12.10', 'architecture': 'AMD64',
                   'distribution': {'sha256': 'test-source-pin'},
                   'notices': [{'file': 'NOTICE.txt', 'sha256': raw_hash}],
                   'native_files': {'python312.dll': 'python312.dll'}}
        source = root / 'sources.json'
        source.write_text(json.dumps(catalog))
        (base / 'sources.json').write_bytes(source.read_bytes())
        (base / 'README.txt').write_bytes(b'Evidence scope')
        (base / 'NOTICE.txt').write_bytes(raw)
        license_path = payload / '_internal/licenses/python/LICENSE.txt'
        license_path.parent.mkdir()
        license_path.write_bytes(b'Official Python license')
        binary = payload / '_internal/python312.dll'
        binary.write_bytes(b'Official Python native file')
        native = {'python_relative_path': 'python312.dll', 'sha256': verifier.digest(binary)}
        receipt = {'schema': 1, 'mode': 'windows_pe_verified', 'python_version': '3.12.10',
                   'architecture': 'AMD64', 'distribution': catalog['distribution'],
                   'global_release_approval': False, 'redistribution_review': 'not_complete',
                   'source_catalog_sha256': verifier.digest(source),
                   'official_python_license_sha256': verifier.digest(license_path),
                   'files': {name: verifier.digest(base / name) for name in ('NOTICE.txt', 'README.txt', 'sources.json')},
                   'notices': [{**catalog['notices'][0], 'notice_sha256': raw_hash}],
                   'native_files': {'python312.dll': native}}
        (base / 'receipt.json').write_text(json.dumps(receipt))
        (payload / '_internal/licenses/windows-dependency-provenance.json').write_text(json.dumps({
            'files': [{'path': '_internal/python312.dll', 'sha256': native['sha256'],
                       'origin': {'root': 'python', 'relative': 'python312.dll'}}]}))
        return payload, source, receipt

    def test_complete_collected_notices_and_official_selected_bytes_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            payload, source, _ = self.fixture(Path(directory))
            with patch.object(verifier, 'SOURCES', source):
                report = verifier.verify_windows_payload(payload)
            self.assertTrue(report['passed'])
            self.assertEqual(report['selected_native_files'], 1)
            self.assertNotIn('global_release_approval', report)

    def test_missing_modified_extra_or_unsafe_notice_is_rejected(self):
        for mutation in ('missing', 'modified', 'extra', 'unsafe'):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                payload, source, receipt = self.fixture(Path(directory))
                base = payload / '_internal/licenses/python-runtime'
                if mutation == 'missing':
                    (base / 'NOTICE.txt').unlink()
                elif mutation == 'modified':
                    (base / 'NOTICE.txt').write_bytes(b'Changed')
                elif mutation == 'extra':
                    (base / 'extra.txt').write_bytes(b'Unexpected')
                else:
                    receipt['files']['../outside.txt'] = 'fake'
                    (base / 'receipt.json').write_text(json.dumps(receipt))
                with patch.object(verifier, 'SOURCES', source), self.assertRaises(ValueError):
                    verifier.verify_windows_payload(payload)

    def test_stale_or_self_approving_receipt_is_rejected(self):
        for key, value in (('source_catalog_sha256', 'old'), ('mode', 'notices_only'),
                           ('global_release_approval', True), ('redistribution_review', 'passed')):
            with self.subTest(key=key), tempfile.TemporaryDirectory() as directory:
                payload, source, receipt = self.fixture(Path(directory))
                receipt[key] = value
                (payload / '_internal/licenses/python-runtime/receipt.json').write_text(json.dumps(receipt))
                with patch.object(verifier, 'SOURCES', source), self.assertRaises(ValueError):
                    verifier.verify_windows_payload(payload)

    def test_changed_python_native_file_or_license_is_rejected(self):
        for relative in ('_internal/python312.dll', '_internal/licenses/python/LICENSE.txt'):
            with self.subTest(path=relative), tempfile.TemporaryDirectory() as directory:
                payload, source, _ = self.fixture(Path(directory))
                (payload / relative).write_bytes(b'Not the reviewed bytes')
                with patch.object(verifier, 'SOURCES', source), self.assertRaises(ValueError):
                    verifier.verify_windows_payload(payload)

    def test_receipt_cannot_rename_a_python_source_to_another_relative_path(self):
        with tempfile.TemporaryDirectory() as directory:
            payload, source, receipt = self.fixture(Path(directory))
            receipt['native_files']['python312.dll']['python_relative_path'] = 'other.dll'
            (payload / '_internal/licenses/python-runtime/receipt.json').write_text(json.dumps(receipt))
            with patch.object(verifier, 'SOURCES', source), self.assertRaisesRegex(ValueError, 'mapping differs'):
                verifier.verify_windows_payload(payload)

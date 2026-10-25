"""Pinned, bounded and non-destructive Python-runtime evidence collection."""
import copy
import hashlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from tools import collect_python_license_evidence as evidence


class PythonLicenseEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.base = self.root / 'python'
        self.base.mkdir()
        (self.base / 'DLLs').mkdir()
        members = {'python312.dll': b'synthetic native Python', '_test.pyd': b'synthetic module',
                   'vcruntime140.dll': b'synthetic Windows runtime',
                   'LICENSE.txt': b'official synthetic license\r\n'}
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w') as archive:
            for name, raw in members.items():
                archive.writestr(name, raw)
        self.raw = {'https://example.test/embed.zip': stream.getvalue(),
                    'https://example.test/notice': b'/* Verbatim MIT attribution */\nint unused_source;\n',
                    'https://example.test/windows': b'Windows-only notice\r\n'}
        def source(url):
            raw = self.raw[url]
            return {'url': url, 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}
        self.catalog = {'schema': 1, 'python_version': '3.12.10', 'architecture': 'AMD64',
                        'distribution': source('https://example.test/embed.zip'),
                        'native_files': {'python312.dll': 'python312.dll', '_test.pyd': 'DLLs/_test.pyd',
                                         'VCRUNTIME140.dll': 'VCRUNTIME140.dll'},
                        'notices': [{'file': 'notice.txt', 'scope': 'common', 'extract': 'initial_c_comment',
                                     **source('https://example.test/notice')},
                                    {'file': 'windows.txt', 'scope': 'windows', **source('https://example.test/windows')}]}
        self.catalog_path = self.root / 'sources.json'
        self.write_catalog()
        (self.base / 'python312.dll').write_bytes(members['python312.dll'])
        (self.base / 'DLLs/_test.pyd').write_bytes(members['_test.pyd'])
        (self.base / 'VCRUNTIME140.dll').write_bytes(members['vcruntime140.dll'])
        (self.base / 'LICENSE.txt').write_bytes(members['LICENSE.txt'])
        self.output = self.root / 'output'
        catalog_patch = patch.object(evidence, 'SOURCES', self.catalog_path)
        catalog_patch.start()
        self.addCleanup(catalog_patch.stop)
        download_patch = patch.object(evidence, '_read_url', side_effect=lambda src: self.raw[src['url']])
        self.download = download_patch.start()
        self.addCleanup(download_patch.stop)

    def write_catalog(self):
        self.catalog_path.write_text(json.dumps(self.catalog), encoding='utf-8')

    def test_windows_receipt_verifies_pe_bytes_and_retains_exact_notices(self):
        before = (self.base / 'python312.dll').read_bytes()
        report = evidence.collect(self.output, self.base)
        self.assertEqual(report['mode'], 'windows_pe_verified')
        self.assertEqual(len(report['native_files']), 3)
        self.assertEqual(report['native_files']['VCRUNTIME140.dll']['archive_member'], 'vcruntime140.dll')
        self.assertEqual((self.output / 'notice.txt').read_bytes(), b'/* Verbatim MIT attribution */')
        self.assertEqual((self.output / 'windows.txt').read_bytes(), self.raw['https://example.test/windows'])
        self.assertFalse(any(path.suffix.lower() in {'.dll', '.exe', '.pyd', '.zip'} for path in self.output.rglob('*')))
        self.assertNotIn(str(self.base), json.dumps(report))
        self.assertFalse(report['global_release_approval'])
        self.assertEqual(report['redistribution_review'], 'not_complete')
        self.assertEqual((self.base / 'python312.dll').read_bytes(), before)
        self.assertFalse((self.output / 'LICENSE.txt').exists())
        summary = (self.output / 'README.txt').read_text()
        self.assertIn('original Python BASE installation', summary)
        self.assertIn('do not automatically grant redistribution rights', summary)
        self.assertIn('license_eligibility: not_determined', summary)

    def test_existing_evidence_is_never_overwritten(self):
        self.output.mkdir()
        marker = self.output / 'keep.txt'
        marker.write_bytes(b'original')
        with self.assertRaises(FileExistsError):
            evidence.collect(self.output, self.base)
        self.assertEqual(marker.read_bytes(), b'original')
        self.download.assert_not_called()

    def test_evidence_never_writes_into_python_installation(self):
        with self.assertRaisesRegex(ValueError, 'Python installation'):
            evidence.collect(self.base / 'evidence', self.base)
        self.download.assert_not_called()

    def test_wrong_installed_version_missing_or_changed_pe_fails_closed(self):
        target = self.base / 'python312.dll'
        target.write_bytes(b'a different Python build')
        with self.assertRaisesRegex(ValueError, 'differs.*official'):
            evidence.collect(self.output, self.base)
        self.assertFalse(self.output.exists())
        target.unlink()
        with self.assertRaisesRegex(ValueError, 'Missing.*python312.dll'):
            evidence.collect(self.output, self.base)
        self.assertFalse(self.output.exists())

    def test_archive_or_notice_tampering_does_not_create_partial_evidence(self):
        original = copy.deepcopy(self.raw)
        for url in ('https://example.test/embed.zip', 'https://example.test/notice'):
            self.raw = copy.deepcopy(original)
            self.raw[url] += b'changed'
            with self.subTest(url=url), self.assertRaisesRegex(ValueError, 'hash/size mismatch'):
                evidence.collect(self.output, self.base)
            self.assertFalse(self.output.exists())

    def test_wrong_catalog_or_unsafe_paths_are_rejected(self):
        self.catalog['python_version'] = '3.12.11'
        self.write_catalog()
        with self.assertRaisesRegex(ValueError, 'Unsupported'):
            evidence.collect(self.output, self.base)
        self.catalog['python_version'] = '3.12.10'
        self.catalog['notices'][0]['file'] = '../escape.txt'
        self.write_catalog()
        with self.assertRaisesRegex(ValueError, 'Unsafe'):
            evidence.collect(self.output, self.base)
        self.assertFalse(self.output.exists())

    def test_notices_only_never_claims_native_origin_or_downloads_windows_archive(self):
        with patch.object(evidence.sys, 'version_info', (3, 12, 10)):
            report = evidence.collect_notices(self.output)
        self.assertEqual(report['native_verification'], 'not_performed')
        self.assertEqual(report['mode'], 'notices_only')
        self.assertNotIn('native_files', report)
        self.assertFalse((self.output / 'windows.txt').exists())
        self.assertEqual(self.download.call_count, 1)
        self.assertFalse(report['global_release_approval'])

    def test_notices_only_rejects_other_interpreter_version(self):
        with patch.object(evidence.sys, 'version_info', (3, 12, 11)), self.assertRaisesRegex(ValueError, '3.12.10'):
            evidence.collect_notices(self.output)
        self.download.assert_not_called()

    def test_extraction_requires_a_real_bounded_initial_comment(self):
        for raw in (b'not a notice /* copyright */', b'/* unterminated', b'/*' + b'x' * 9000 + b'*/'):
            with self.assertRaisesRegex(ValueError, 'initial license'):
                evidence._initial_comment(raw)

    def test_pinned_download_bound_is_checked_before_network(self):
        with self.assertRaisesRegex(ValueError, 'download bound'):
            evidence._download({'bytes': evidence.MAX_DOWNLOAD + 1, 'sha256': 'a' * 64, 'url': 'https://example.test/a'})
        self.download.assert_not_called()

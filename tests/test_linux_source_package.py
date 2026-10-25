"""Exercise the real source writer with inert data; never execute a payload."""
import hashlib
import io
import json
import os
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import verify_linux_source_package as verifier


def digest(data):
    return hashlib.sha256(data).hexdigest()


def fixture(root):
    payload, evidence, output = root / 'app', root / 'evidence', root / 'review'
    (payload / '_internal').mkdir(parents=True)
    (payload / '_internal/libexample.so.1').write_bytes(b'inert copied library')
    data = {'copyright/libexample1%3Aamd64/copyright': b'copyright; /usr/share/common-licenses/LGPL-2.1\n',
            'common-licenses/LGPL-2.1': b'synthetic license',
            'authenticated-indexes/archive.ubuntu.com_ubuntu_dists_jammy_InRelease': b'synthetic signed index',
            'authenticated-indexes/archive.ubuntu.com_ubuntu_dists_jammy_main_source_Sources': b'synthetic Sources index',
            'sources/example--1.0/example_1.0.orig.tar.gz': b'inert compressed archive stand-in',
            'sources/example--1.0/example_1.0.dsc': b'inert dsc'}
    for name, content in data.items():
        path = evidence / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    package = {'binary_package': 'libexample1:amd64', 'binary_version': '1.0', 'source_package': 'example',
               'source_version': '1.0', 'architecture': 'amd64',
               'copyright_sha256': digest(data['copyright/libexample1%3Aamd64/copyright'])}
    source_files = {Path(name).name: {'sha256': digest(content), 'bytes': len(content)}
                    for name, content in data.items() if name.startswith('sources/')}
    report = {'schema': 1, 'platform': 'Ubuntu 22.04',
              'scope': 'copyright_and_exact_source_delivery_evidence_not_global_license_approval',
              'apt_authentication': {'check_valid_until': True, 'allow_insecure': False,
                                     'allow_unauthenticated': False, 'keyring_sha256': 'a' * 64},
              'binary_packages': {'libexample1:amd64': package},
              'copied_binary_origins': [{**package, 'destination': 'libexample.so.1',
                                         'original_sha256': digest(b'inert copied library')}],
              'source_archives': [{'package': 'example', 'version': '1.0', 'evidence_directory': 'sources/example--1.0',
                                   'files': source_files,
                                   'uris': {name: 'https://archive.ubuntu.com/ubuntu/pool/main/e/example/' + name for name in source_files}}],
              'evidence_files_sha256': {name: digest(content) for name, content in data.items()}}
    (evidence / verifier.REPORT).write_text(json.dumps(report), encoding='utf-8')
    return payload, evidence, output


class LinuxSourcePackageTests(unittest.TestCase):
    def guarded(self):
        for patcher in (patch.object(verifier.sys, 'platform', 'linux'),
                        patch.dict(os.environ, {'GITHUB_ACTIONS': 'true', 'MYL_ISOLATED_SOURCE_CI': '1'})):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_real_writer_and_reopened_tar_preserve_original_without_any_execution(self):
        self.guarded()
        with tempfile.TemporaryDirectory() as temporary:
            payload, evidence, output = fixture(Path(temporary))
            before = verifier.payload_inventory(payload)
            with patch('subprocess.Popen', side_effect=AssertionError('No subprocess may run')):
                result = verifier.run_and_record(payload, evidence, output, 'synthetic-source-review')
            self.assertEqual(result, 0)
            report = json.loads((output / verifier.REVIEW).read_text())
            self.assertTrue(report['passed'])
            self.assertFalse(report['publishable_release'])
            self.assertFalse(report['application_executed'])
            self.assertEqual(report['source_families'], 1)
            self.assertEqual(report['verified_tar_members'], 7)
            self.assertEqual(verifier.payload_inventory(payload), before)
            self.assertFalse((payload / '_internal/licenses').exists())
            self.assertEqual({path.name for path in output.iterdir()},
                             {verifier.REVIEW, 'synthetic-source-review-license-sources.tar'})

    def test_windows_and_missing_ci_guards_precede_all_input_reads_or_writes(self):
        for platform, env in (('win32', {'GITHUB_ACTIONS': 'true', 'MYL_ISOLATED_SOURCE_CI': '1'}),
                              ('linux', {'GITHUB_ACTIONS': 'false', 'MYL_ISOLATED_SOURCE_CI': '1'})):
            with patch.object(verifier.sys, 'platform', platform), patch.dict(os.environ, env), \
                    patch.object(verifier, '_validate') as validation, patch.object(verifier.shutil, 'copytree') as copying:
                report = verifier.run_checks(Path('absent'), Path('absent'), Path('absent'), 'test')
            self.assertEqual(report['status'], 'not_run')
            validation.assert_not_called()
            copying.assert_not_called()

    def test_output_cannot_overwrite_or_mutate_original_inputs(self):
        self.guarded()
        with tempfile.TemporaryDirectory() as temporary:
            payload, evidence, output = fixture(Path(temporary))
            for forbidden in (payload / 'new', evidence / 'new'):
                with self.assertRaises(ValueError):
                    verifier.run_checks(payload, evidence, forbidden, 'test')
                self.assertFalse(forbidden.exists())
            output.mkdir()
            with self.assertRaises(FileExistsError):
                verifier.run_checks(payload, evidence, output, 'test')

    def test_tampering_fails_with_original_hashes_preserved(self):
        self.guarded()
        with tempfile.TemporaryDirectory() as temporary:
            payload, evidence, output = fixture(Path(temporary))
            source = next((evidence / 'sources').rglob('*.gz'))
            source.write_bytes(b'changed')
            report = verifier.run_checks(payload, evidence, output, 'test')
            self.assertEqual(report['status'], 'failed')
            self.assertEqual(report['failed_stage'], 'validate_collected_evidence')
            self.assertTrue(report['checks']['original_payload_unchanged'])
            self.assertFalse(output.exists())

    def test_tar_rejects_foreign_duplicate_link_missing_or_changed_members(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            expected = root / 'expected.txt'
            expected.write_bytes(b'expected')
            for mutation in ('foreign', 'duplicate', 'link', 'missing', 'changed'):
                archive = root / (mutation + '.tar')
                with tarfile.open(archive, 'w') as tar:
                    if mutation != 'missing':
                        name = 'foreign.txt' if mutation == 'foreign' else 'expected.txt'
                        info = tarfile.TarInfo(name)
                        info.mode = 0o644
                        content = b'changed!' if mutation == 'changed' else b'expected'
                        info.size = len(content)
                        if mutation == 'link':
                            info.type, info.linkname, info.size = tarfile.SYMTYPE, 'outside', 0
                        tar.addfile(info, io.BytesIO(content))
                        if mutation == 'duplicate':
                            tar.addfile(info, io.BytesIO(content))
                with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                    verifier.validate_tar(archive, {'expected.txt': expected}, {'expected.txt': digest(b'expected')})

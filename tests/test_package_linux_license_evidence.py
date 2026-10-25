"""Small synthetic evidence tests; no APT, Linux process, or real sources."""
import hashlib
import json
import tarfile
import tempfile
import unittest
from pathlib import Path

from tools import package_linux_license_evidence as packager


def digest(data):
    return hashlib.sha256(data).hexdigest()


class PackageLinuxLicenseEvidenceTests(unittest.TestCase):
    def fixture(self, root):
        payload, evidence, release = root / 'app', root / 'evidence', root / 'release'
        (payload / '_internal').mkdir(parents=True)
        (payload / '_internal' / 'libexample.so.1').write_bytes(b'original ELF stand-in')
        copyright_data = b'Example copyright\nLicense: /usr/share/common-licenses/LGPL-2.1\n'
        data = {'copyright/libexample1%3Aamd64/copyright': copyright_data,
                'common-licenses/LGPL-2.1': b'synthetic common license\n',
                'authenticated-indexes/archive.ubuntu.com_ubuntu_dists_jammy_InRelease': b'synthetic signed index',
                'authenticated-indexes/archive.ubuntu.com_ubuntu_dists_jammy_main_source_Sources': b'synthetic source index',
                'sources/example--1.0-1ubuntu1/example_1.0.orig.tar.gz': b'synthetic upstream archive',
                'sources/example--1.0-1ubuntu1/example_1.0-1ubuntu1.dsc': b'synthetic dsc'}
        for name, value in data.items():
            path = evidence / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(value)
        package = {'binary_package': 'libexample1:amd64', 'binary_version': '1.0-1ubuntu1',
                   'source_package': 'example', 'source_version': '1.0-1ubuntu1', 'architecture': 'amd64',
                   'copyright_sha256': digest(copyright_data)}
        source_files = {Path(name).name: {'sha256': digest(value), 'bytes': len(value)}
                        for name, value in data.items() if name.startswith('sources/')}
        report = {'schema': 1, 'platform': 'Ubuntu 22.04', 'scope': packager.SCOPE,
                  'apt_authentication': {'check_valid_until': True, 'allow_insecure': False,
                                         'allow_unauthenticated': False, 'keyring_sha256': 'a' * 64},
                  'binary_packages': {'libexample1:amd64': package},
                  'copied_binary_origins': [{**package, 'destination': 'libexample.so.1',
                                             'original_sha256': digest(b'original ELF stand-in')}],
                  'source_archives': [{'package': 'example', 'version': '1.0-1ubuntu1',
                                       'evidence_directory': 'sources/example--1.0-1ubuntu1', 'files': source_files,
                                       'uris': {name: 'https://archive.ubuntu.com/ubuntu/pool/main/e/example/' + name for name in source_files}}],
                  'evidence_files_sha256': {name: digest(value) for name, value in data.items()}}
        self.write_report(evidence, report)
        return payload, evidence, release, report

    def write_report(self, evidence, report):
        (evidence / packager.REPORT).write_text(json.dumps(report), encoding='utf-8')

    def test_separate_uncompressed_tar_small_app_notices_and_final_hash_map(self):
        with tempfile.TemporaryDirectory() as directory:
            payload, evidence, release, _ = self.fixture(Path(directory))
            final = b'patchelf modified stand-in'
            (payload / '_internal/libexample.so.1').write_bytes(final)
            receipt = packager.prepare(payload, evidence, release, 'example-linux')
            archive = release / receipt['archive']
            self.assertEqual(receipt['sha256'], packager.sha256(archive))
            self.assertEqual(receipt['copied_binary_hashes']['libexample.so.1']['final_sha256'], digest(final))
            self.assertTrue(receipt['copied_binary_hashes']['libexample.so.1']['bytes_changed_after_collection'])
            target = payload / '_internal/licenses/linux-system'
            self.assertFalse((target / 'sources').exists())
            self.assertFalse((target / 'authenticated-indexes').exists())
            self.assertTrue((target / 'copyright/libexample1%3Aamd64/copyright').is_file())
            self.assertEqual(json.loads((target / 'source-asset.json').read_text())['archive'], archive.name)
            with tarfile.open(archive, mode='r:') as tar:
                self.assertEqual(set(tar.getnames()), set(packager._files(evidence)))
                self.assertTrue(all(member.uid == 0 and member.uname == '' for member in tar.getmembers()))
            self.assertNotIn('passed', receipt)

    def test_missing_or_tampered_evidence_rejected_before_outputs(self):
        for tamper in ('missing', 'tamper'):
            with self.subTest(tamper=tamper), tempfile.TemporaryDirectory() as directory:
                payload, evidence, release, _ = self.fixture(Path(directory))
                source = next((evidence / 'sources').rglob('*.gz'))
                if tamper == 'missing':
                    source.unlink()
                else:
                    source.write_bytes(b'bad')
                with self.assertRaises(ValueError):
                    packager.prepare(payload, evidence, release, 'test')
                self.assertFalse(release.exists())
                self.assertFalse((payload / '_internal/licenses/linux-system').exists())

    def test_foreign_files_rejected_even_if_added_to_hash_inventory(self):
        for declared, name in ((False, 'foreign.exe'), (True, 'foreign.exe'),
                               (True, 'authenticated-indexes/foreign.exe')):
            with self.subTest(declared=declared, name=name), tempfile.TemporaryDirectory() as directory:
                payload, evidence, release, report = self.fixture(Path(directory))
                (evidence / name).write_bytes(b'foreign')
                if declared:
                    report['evidence_files_sha256'][name] = digest(b'foreign')
                    self.write_report(evidence, report)
                with self.assertRaises(ValueError):
                    packager.prepare(payload, evidence, release, 'test')

    def test_sources_asset_must_not_be_placed_in_app_or_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            payload, evidence, _, _ = self.fixture(Path(directory))
            for release in (payload / 'release', evidence / 'release'):
                with self.subTest(release=release), self.assertRaisesRegex(ValueError, 'separate'):
                    packager.prepare(payload, evidence, release, 'test')
                self.assertFalse(release.exists())

    def test_missing_source_family_and_wrong_version_size_uri_rejected(self):
        for mutation in ('missing', 'version', 'size', 'uri'):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                payload, evidence, release, report = self.fixture(Path(directory))
                source = report['source_archives'][0]
                if mutation == 'missing':
                    report['source_archives'] = []
                elif mutation == 'version':
                    source['version'] = '2.0'
                elif mutation == 'size':
                    next(iter(source['files'].values()))['bytes'] += 1
                else:
                    source['uris'][next(iter(source['uris']))] = 'https://unofficial.invalid/source'
                self.write_report(evidence, report)
                with self.assertRaises(ValueError):
                    packager.prepare(payload, evidence, release, 'test')

    def test_origin_paths_and_unsafe_labels_rejected(self):
        for value in ('../escape', '/absolute', 'a\\b', 'x\nname'):
            with self.subTest(value=value), tempfile.TemporaryDirectory() as directory:
                payload, evidence, release, report = self.fixture(Path(directory))
                report['copied_binary_origins'][0]['destination'] = value
                self.write_report(evidence, report)
                with self.assertRaises(ValueError):
                    packager.prepare(payload, evidence, release, 'test')
        with tempfile.TemporaryDirectory() as directory:
            payload, evidence, release, _ = self.fixture(Path(directory))
            with self.assertRaises(ValueError):
                packager.prepare(payload, evidence, release, '../escape')

    def test_existing_archive_or_app_notices_never_overwritten(self):
        for existing in ('archive', 'notices'):
            with self.subTest(existing=existing), tempfile.TemporaryDirectory() as directory:
                payload, evidence, release, _ = self.fixture(Path(directory))
                if existing == 'archive':
                    release.mkdir()
                    target = release / 'test-license-sources.tar'
                    target.write_bytes(b'keep')
                else:
                    target = payload / '_internal/licenses/linux-system'
                    target.mkdir(parents=True)
                with self.assertRaises(FileExistsError):
                    packager.prepare(payload, evidence, release, 'test')
                if existing == 'archive':
                    self.assertEqual(target.read_bytes(), b'keep')

    def test_missing_payload_library_or_common_license_is_not_inferred(self):
        for missing in ('library', 'common'):
            with self.subTest(missing=missing), tempfile.TemporaryDirectory() as directory:
                payload, evidence, release, report = self.fixture(Path(directory))
                if missing == 'library':
                    (payload / '_internal/libexample.so.1').unlink()
                else:
                    name = 'common-licenses/LGPL-2.1'
                    (evidence / name).unlink()
                    del report['evidence_files_sha256'][name]
                    self.write_report(evidence, report)
                with self.assertRaises(ValueError):
                    packager.prepare(payload, evidence, release, 'test')

"""Offline parser and fail-closed policy tests; never run APT on the test host."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import collect_linux_license_evidence as collector

HASH = 'a' * 64
SOURCE = ('Package: example\nVersion: 1:2.0-0ubuntu1\nDirectory: pool/main/e/example\n'
          'Checksums-Sha256:\n ' + HASH + ' 10 example_2.0.orig.tar.gz\n '
          + HASH + ' 20 example_2.0-0ubuntu1.dsc\n')


class LinuxLicenseEvidenceTests(unittest.TestCase):
    def test_inventory_accepts_json_pairs_and_deduplicates(self):
        entries = collector.parse_toc([['libexample.so.1', '/usr/lib/libexample.so.1', 'BINARY'],
                                       {'destination': 'libexample.so.1', 'source': '/usr/lib/libexample.so.1'}])
        self.assertEqual(len(entries), 1)

    def test_inventory_rejects_conflicts_traversal_and_shell_patterns(self):
        for data in ([{'destination': '../escape', 'source': '/usr/lib/x.so'}],
                     [{'destination': 'x.so', 'source': '/usr/lib/*.so'}],
                     [{'destination': 'x.so', 'source': 'relative.so'}],
                     [['x.so', '/usr/lib/a.so', 'BINARY'], ['x.so', '/usr/lib/b.so', 'BINARY']]):
            with self.subTest(data=data), self.assertRaises(ValueError):
                collector.parse_toc(data)

    def test_source_version_must_match_exactly_including_epoch(self):
        record = collector.source_record(SOURCE, 'example', '1:2.0-0ubuntu1')
        self.assertEqual(len(record['files']), 2)
        self.assertEqual(record['files']['example_2.0.orig.tar.gz']['bytes'], 10)
        with self.assertRaisesRegex(ValueError, 'Exact source version absent'):
            collector.source_record(SOURCE, 'example', '2.0-0ubuntu1')

    def test_weak_missing_hashes_and_conflicting_index_records_fail(self):
        for text in (SOURCE.replace(HASH, 'md5'), SOURCE.replace('Checksums-Sha256', 'Files'),
                     SOURCE + '\n' + SOURCE.replace('pool/main/e/example', 'pool/other/example')):
            with self.subTest(text=text), self.assertRaises(ValueError):
                collector.source_record(text, 'example', '1:2.0-0ubuntu1')

    def test_official_https_source_uris_are_bound_to_expected_files(self):
        files = collector.source_record(SOURCE, 'example', '1:2.0-0ubuntu1')['files']
        text = "'https://archive.ubuntu.com/ubuntu/pool/main/e/example/example_2.0.orig.tar.gz' example_2.0.orig.tar.gz 10 MD5Sum:ignored\n"
        text += "'https://security.ubuntu.com/ubuntu/pool/main/e/example/example_2.0-0ubuntu1.dsc' example_2.0-0ubuntu1.dsc 20 MD5Sum:ignored\n"
        self.assertEqual(len(collector.validate_source_uris(text, files)), 2)
        for changed in (text.replace('https:', 'http:'), text.replace('archive.ubuntu.com', 'archive.ubuntu.com.attacker.invalid'),
                        text.replace(' 10 ', ' 11 '), text.splitlines()[0]):
            with self.subTest(text=changed), self.assertRaises(ValueError):
                collector.validate_source_uris(changed, files)

    def test_dpkg_source_fields_are_not_guessed_from_filename(self):
        result = collector.parse_dpkg_fields('libexample1:amd64\t1:2.0-0ubuntu1\texample\t1:2.0-0ubuntu1\tamd64\tinstalled\n')
        self.assertEqual(result['source_package'], 'example')
        with self.assertRaises(ValueError):
            collector.parse_dpkg_fields('example\t1\texample\t1\tamd64\tnot-installed\n')

    def test_isolated_apt_disables_host_config_hooks_and_weak_auth(self):
        config, sources = collector.apt_configuration(Path('/tmp/new-evidence'))
        self.assertIn('Dir::Etc::parts "-";', config)
        self.assertIn('Dir::Etc::main "-";', config)
        self.assertIn('Acquire::AllowInsecureRepositories "false";', config)
        self.assertIn('APT::Get::AllowUnauthenticated "false";', config)
        self.assertIn('Acquire::Check-Valid-Until "true";', config)
        self.assertNotIn('trusted=yes', sources)
        self.assertEqual(sources.count('signed-by='), 4)
        self.assertNotIn('http://', sources)

    def test_duplicate_debian_control_fields_fail(self):
        with self.assertRaises(ValueError):
            collector.parse_deb822('Package: example\nPackage: other\n')

    def test_windows_is_rejected_before_any_output_or_command(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'not-created'
            with patch.object(collector.sys, 'platform', 'win32'), patch.object(collector.subprocess, 'run') as command:
                with self.assertRaisesRegex(RuntimeError, 'never on Windows'):
                    collector.collect(Path(directory) / 'absent.json', output)
                command.assert_not_called()
            self.assertFalse(output.exists())

    def test_inventory_is_plain_json_not_eval(self):
        with self.assertRaises(ValueError):
            collector.parse_toc(json.dumps([['x.so', '/usr/lib/x.so', 'BINARY']]))

    def test_literal_collect_toc_selects_binaries_and_preserves_wheel_origins(self):
        text = "([('x.so', '/usr/lib/x.so', 'BINARY'), ('PIL/_imaging.so', '/venv/PIL/_imaging.so', 'EXTENSION'), ('app', '/build/app', 'EXECUTABLE'), ('data', '/etc/data', 'DATA')], True, False)"
        entries = collector.parse_pyinstaller_toc(text)
        self.assertEqual([entry['destination'] for entry in entries], ['PIL/_imaging.so', 'x.so'])
        self.assertEqual(entries[0]['source'], '/venv/PIL/_imaging.so')

    def test_literal_toc_rejects_code_relative_paths_and_excessive_depth(self):
        for text in ("__import__('os').system('echo unsafe')", "[('x', 'relative', 'BINARY')]",
                     '[' * 70 + '0' + ']' * 70):
            with self.subTest(text=text), self.assertRaises(ValueError):
                collector.parse_pyinstaller_toc(text)

    def test_literal_toc_size_is_bounded(self):
        with self.assertRaises(ValueError):
            collector.parse_pyinstaller_toc(' ' * (collector.MAX_TOC_BYTES + 1))

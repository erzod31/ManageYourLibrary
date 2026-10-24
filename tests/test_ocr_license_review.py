"""Audit completeness is distinct from permission to redistribute OCR binaries."""
import hashlib
import json
import unittest
from pathlib import Path

from tools.collect_ocr_license_evidence import package_fields, simple_variable
from tools.write_ocr_license_review import json_digest

ROOT = Path(__file__).resolve().parents[1]


class OcrLicenseReviewTests(unittest.TestCase):
    def setUp(self):
        self.catalog_path = ROOT / 'tools/ocr_license_catalog.json'
        self.catalog = json.loads(self.catalog_path.read_text(encoding='utf-8'))
        self.report = json.loads((ROOT / 'docs/validation_data_2026-10-25/windows-ocr-license-review.json').read_text(encoding='utf-8'))
        self.inventory_path = ROOT / 'docs/validation_data_2026-10-24/windows-ocr-provenance.json'
        self.inventory = json.loads(self.inventory_path.read_text(encoding='utf-8'))

    def test_each_binary_has_exactly_one_license_finding(self):
        expected = {row['file']: row['sha256'] for row in self.inventory['files']}
        actual = {row['file']: row['sha256'] for row in self.report['findings']}
        self.assertEqual(len(actual), len(self.report['findings']))
        self.assertEqual(actual, expected)
        self.assertEqual(self.report['binary_count'], len(expected))
        self.assertEqual(self.report['dll_count'], sum(name.endswith('.dll') for name in expected))

    def test_json_receipts_are_bound_to_reviewed_catalog(self):
        self.assertEqual(self.report['catalog_sha256'], json_digest(self.catalog_path))
        self.assertEqual(self.report['provenance_sha256'], json_digest(self.inventory_path))

    def test_exact_packages_are_not_inferred_from_recipe_versions(self):
        expected = {row['file']: row['sha256'] for row in self.inventory['files']}
        matched = []
        for receipt in self.report['package_receipts']:
            for row in receipt.get('matching_files', []):
                self.assertEqual(row['sha256'], expected[row['file']])
                self.assertEqual(row['expected_sha256'], expected[row['file']])
                matched.append(row['file'])
            if receipt.get('candidate_package', {}).get('retrieval') != 'downloaded':
                self.assertFalse(receipt.get('matching_files'))
        self.assertEqual(len(matched), len(set(matched)))
        self.assertEqual(self.report['exact_package_matches'], len(matched))

    def test_notices_remain_verbatim(self):
        for notice in self.report['verbatim_notice_files']:
            path = ROOT / 'tesseract/licenses/reviewed-package-notices' / notice['path']
            raw = path.read_bytes()
            self.assertEqual(len(raw), notice['bytes'], path.name)
            self.assertEqual(hashlib.sha256(raw).hexdigest(), notice['sha256'], path.name)

    def test_library_and_tool_licenses_are_not_conflated(self):
        by_id = {row['id']: row for row in self.catalog['components']}
        self.assertEqual(by_id['libiconv']['license'], 'LGPL-2.1-or-later')
        self.assertEqual(by_id['gettext']['license'], 'LGPL-2.1-or-later')
        self.assertEqual(by_id['lz4']['license'], 'BSD-2-Clause')
        self.assertEqual(by_id['xz']['license'], '0BSD')
        self.assertNotIn('MIT', by_id['graphite2']['license'])
        self.assertIn('GCC-exception-3.1', by_id['gcc']['license'])
        self.assertEqual(by_id['jbigkit']['license'], 'GPL-2.0-or-later')

    def test_open_obligations_cannot_appear_as_license_clearance(self):
        self.assertEqual(self.report['redistribution_review'], 'not_complete')
        self.assertFalse(self.report['source_obligations_fulfilled'])
        for receipt in self.report['package_receipts']:
            self.assertIs(receipt['redistribution_cleared'], False)
        self.assertTrue(all(row['redistribution_status'].startswith('blocked_') for row in self.report['findings']))

    def test_package_recipe_is_never_evaluated(self):
        self.assertEqual(simple_variable('pkgver=1.2.3\n', 'pkgver'), '1.2.3')
        for value in ('$(touch malicious)', '`code`', '${other}', '1; injected'):
            with self.assertRaises(ValueError):
                simple_variable('pkgver=' + value + '\n', 'pkgver')

    def test_package_metadata_does_not_export_builder_identities_or_paths(self):
        actual = package_fields(b'pkgver = 1\npackager = Private <private@example.invalid>\nbuilddir = /private\nlicense = MIT\n')
        self.assertEqual(actual, {'pkgver': ['1'], 'license': ['MIT']})


if __name__ == '__main__':
    unittest.main()

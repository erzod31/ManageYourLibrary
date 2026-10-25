import json
import tempfile
import unittest
from pathlib import Path

from tools.check_native_publication_licenses import EXPECTED, check


class NativePublicationLicenseTests(unittest.TestCase):
    def fixtures(self, directory):
        paths = []
        for name, architecture in sorted(EXPECTED):
            path = directory / (name + '-' + architecture + '-manifest.json')
            path.write_text(json.dumps({'platform': name, 'architecture': architecture,
                'validation': {'redistribution_review': 'passed', 'ocr_libraries_profile': 'passed'},
                'ocr_source_payload': {'resolution': 'replaced_legacy_stack_no_gpl_lgpl_ocr_libraries'}}))
            paths.append(path)
        return paths

    def test_only_complete_recorded_reviews_pass_the_publication_gate(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            self.fixtures(directory)
            self.assertEqual(check(directory), 3)

    def test_ocr_only_review_does_not_clear_the_whole_native_app(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            path = self.fixtures(directory)[0]
            value = json.loads(path.read_text())
            value['validation']['redistribution_review'] = 'not_complete'
            path.write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError, 'complete redistribution review'):
                check(directory)

    def test_missing_target_is_not_a_complete_publication(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            self.fixtures(directory)[0].unlink()
            with self.assertRaises(ValueError):
                check(directory)

    def test_legacy_ocr_cannot_be_approved_by_a_general_review_flag(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            path = self.fixtures(directory)[0]
            value = json.loads(path.read_text())
            value['ocr_source_payload']['resolution'] = 'legacy'
            path.write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError, 'controlled OCR'):
                check(directory)


if __name__ == '__main__':
    unittest.main()

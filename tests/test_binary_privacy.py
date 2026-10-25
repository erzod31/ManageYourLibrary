"""Native path guards with synthetic inputs; never print actual user paths."""
import tempfile
import unittest
from pathlib import Path

from tools.verify_binary_privacy import contains_profile_path, require_clean_tree, require_neutral_location, validate_tree


class BinaryPrivacyTests(unittest.TestCase):
    def test_windows_profile_paths_are_detected_in_native_string_encodings(self):
        for value in ('C:\\Users\\SyntheticUser\\build\\bridge.c', 'd:/USERS/SyntheticUser/build/tcl.dll'):
            for encoding in ('utf-8', 'utf-16-le', 'utf-16-be'):
                with self.subTest(value=value, encoding=encoding):
                    self.assertTrue(contains_profile_path(b'X' + value.encode(encoding) + b'\x00'))

    def test_exact_profile_prefix_is_detected_without_windows_conventions(self):
        self.assertTrue(contains_profile_path(b'/home/synthetic/build/gui', prefixes=('/home/synthetic',)))
        self.assertFalse(contains_profile_path(b'/opt/project/gui', prefixes=('/home/synthetic',)))

    def test_neutral_paths_and_public_owner_are_not_private_profile_paths(self):
        for value in (b'C:\\myl-native-build\\gui\\tcl91.dll', b'Built by erzod31',
                      b'114614289+erzod31@users.noreply.github.com'):
            self.assertFalse(contains_profile_path(value))
        require_neutral_location('C:/myl-native-build/gui')
        with self.assertRaisesRegex(ValueError, 'neutral directory'):
            require_neutral_location('C:/Users/SyntheticUser/gui')

    def test_report_identifies_only_the_file_not_the_private_string(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'example.dll'
            path.write_bytes(b'prefix C:\\Users\\SyntheticUser\\build\\gui.c suffix')
            report = validate_tree(directory)
            self.assertFalse(report['passed'])
            self.assertEqual(report['findings'], ['example.dll'])
            self.assertNotIn('SyntheticUser', str(report))
            with self.assertRaisesRegex(ValueError, 'example.dll'):
                require_clean_tree(directory)

    def test_missing_or_empty_scan_is_not_a_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                validate_tree(directory)
            with self.assertRaises(FileNotFoundError):
                validate_tree(Path(directory) / 'missing')

    def test_native_and_runtime_text_inputs_are_checked_but_models_are_not_decoded(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'example.dll').write_bytes(b'neutral native data')
            (root / 'init.tcl').write_text('neutral runtime text', encoding='utf-8')
            (root / 'model.traineddata').write_bytes(b'opaque model data')
            report = require_clean_tree(root)
        self.assertTrue(report['passed'])
        self.assertEqual(report['files_checked'], 2)

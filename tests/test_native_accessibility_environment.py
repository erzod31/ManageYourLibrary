"""Enforce the extracted API gate without changing its parent process."""
import os
import unittest
from unittest.mock import patch

from tools.package_native_release import accessibility_api_environment

class NativeAccessibilityEnvironmentTests(unittest.TestCase):
    def test_extracted_linux_gate_overrides_debug_without_mutating_parent(self):
        before = {'G_DEBUG': 'gc-friendly', 'DISPLAY': ':synthetic'}
        with patch.dict(os.environ, before, clear=True):
            result = accessibility_api_environment('linux')
            self.assertEqual(result, {**before, 'G_DEBUG': 'fatal-warnings'})
            self.assertEqual(dict(os.environ), before)

    def test_macos_inherits_environment_and_unknown_platform_is_rejected(self):
        self.assertIsNone(accessibility_api_environment('macos'))
        with self.assertRaises(ValueError):
            accessibility_api_environment('other')

if __name__ == '__main__':
    unittest.main()

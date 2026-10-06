"""Check product attribution without recording a developer's personal identity."""
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DistributionPrivacyTests(unittest.TestCase):
    def test_installer_publisher_is_the_product(self):
        installer = (ROOT / "platforms/windows/ManageYourLibrary.iss").read_text(encoding="utf-8")
        publisher = re.search(r"^AppPublisher=(.+)$", installer, re.MULTILINE)
        self.assertIsNotNone(publisher)
        self.assertEqual(publisher.group(1).strip(), "Manage Your Library")

    def test_readme_uses_first_use_instructions_not_personal_attribution(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertNotRegex(readme, r"(?m)^## Author\s*$")
        for marker in ("Choose library folder", "**Import**", "move and rename", "empty catalog"):
            self.assertIn(marker, readme)


if __name__ == "__main__":
    unittest.main()

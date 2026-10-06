"""Keep intentional public ownership separate from private user/profile data."""
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

    def test_readme_retains_first_use_instructions_and_public_owner(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertNotRegex(readme, r"(?m)^## Author\s*$")
        self.assertIn('**[erzod31](https://github.com/erzod31)**', readme)
        self.assertIn('Built and maintained by', readme)
        for marker in ("Choose library folder", "**Import**", "move and rename", "empty catalog"):
            self.assertIn(marker, readme)


if __name__ == "__main__":
    unittest.main()

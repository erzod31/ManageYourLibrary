"""Keep first-use documentation aligned with supported formats and release assets."""
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ReadmeCompletenessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.readme = (ROOT / "README.md").read_text(encoding="utf-8")
        cls.version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()

    def test_downloads_cover_all_four_assets_of_published_version(self):
        prefix = f"https://github.com/erzod31/ManageYourLibrary/releases/download/v{self.version}/"
        for name in (
            f"ManageYourLibrary-{self.version}-Setup-x64.exe",
            f"ManageYourLibrary-{self.version}-Windows-x64-portable.zip",
            f"SHA256SUMS-{self.version}.txt",
            f"build-manifest-{self.version}.json",
        ):
            self.assertIn(prefix + name, self.readme)
        self.assertIn("source-code ZIP is not", self.readme)

    def test_all_supported_library_extensions_are_documented(self):
        import library_core as core
        for suffix in core.EXTENSIONES_LIBROS:
            self.assertIn(f"`{suffix}`", self.readme)
        for marker in ("soffice", "djvutxt", "PATH", "images are not normal"):
            self.assertIn(marker, self.readme)

    def test_documentation_links_resolve_inside_repository(self):
        for target in re.findall(r"\]\(([^)]+)\)", self.readme):
            if re.match(r"https?://", target):
                continue
            path = (ROOT / target.split("#", 1)[0]).resolve()
            self.assertTrue(path.is_relative_to(ROOT), target)
            self.assertTrue(path.is_file(), target)

    def test_checksums_match_the_immutable_release_record(self):
        record = (ROOT / "docs" / f"windows_{self.version}_checksums.md").read_text(encoding="utf-8")
        hashes = re.findall(r"`([A-F0-9]{64})`", self.readme)
        self.assertEqual(len(hashes), 2)
        for digest in hashes:
            self.assertIn(digest, record)
        self.assertIn("Get-FileHash -LiteralPath", self.readme)
        self.assertIn("-Algorithm SHA256", self.readme)
        self.assertIn("**do not run the file**", self.readme)

    def test_backup_support_and_security_limits_are_explicit(self):
        for marker in (
            "## Backups, updates and restoration", "## Troubleshooting",
            "## Report a problem", "%APPDATA%\\ManageYourLibrary",
            ".trash_manageyourlibrary/", "close the application",
            "back up the **current**", "manual upgrade/uninstall approval is still pending",
            "do not disable Defender/Smart App Control", "/issues/new",
            "**Redact personal paths", "Do not upload your books",
        ):
            self.assertIn(marker, self.readme)

    def test_native_downloads_and_security_limits_are_documented(self):
        prefix = f'https://github.com/erzod31/ManageYourLibrary/releases/download/v{self.version}-native.2/'
        for target in ('macOS-arm64.zip', 'macOS-x64.zip', 'Linux-x64.tar.gz'):
            self.assertIn(prefix + f'ManageYourLibrary-{self.version}-' + target, self.readme)
        for marker in ('macOS 15', 'Ubuntu 22.04', 'no Developer ID', 'notarization', 'XDG_DATA_HOME', 'Application Support'):
            self.assertIn(marker, self.readme)


if __name__ == "__main__":
    unittest.main()

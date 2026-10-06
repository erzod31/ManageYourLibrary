import tempfile
import unittest
from pathlib import Path

from tools import write_build_manifest


class BuildManifestTests(unittest.TestCase):
    def test_source_fingerprint_is_stable_and_nonempty(self):
        first = write_build_manifest.source_tree_fingerprint()
        second = write_build_manifest.source_tree_fingerprint()

        self.assertEqual(first, second)
        self.assertGreater(first["files"], 0)
        self.assertRegex(first["sha256"], r"^[0-9A-F]{64}$")

    def test_manifest_distinguishes_automated_and_manual_validation(self):
        with tempfile.TemporaryDirectory() as temporary:
            artifact = Path(temporary) / "app.exe"
            artifact.write_bytes(b"synthetic artifact")

            write_build_manifest.main(
                [str(artifact), "--platform", "test", "--validated-release-gates"],
            )
            manifest = (artifact.parent / "build-manifest.json").read_text(encoding="utf-8")

        self.assertIn('"automated_tests": "passed"', manifest)
        self.assertIn('"frozen_smoke": "passed"', manifest)
        self.assertIn('"manual_installed_ui": "not_run"', manifest)
        self.assertIn('"code_signing": "not_performed"', manifest)


if __name__ == "__main__":
    unittest.main()

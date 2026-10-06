import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class PlatformBuildTests(unittest.TestCase):
    def test_native_scripts_share_release_gates_and_onedir_shape(self):
        scripts = {
            "linux": ROOT / "platforms" / "linux" / "build_linux.sh",
            "macos": ROOT / "platforms" / "macos" / "build_macos.sh",
        }
        for platform_name, path in scripts.items():
            with self.subTest(platform=platform_name):
                script = path.read_text(encoding="utf-8")
                self.assertIn("requirements-build.txt", script)
                self.assertIn("unittest discover", script)
                self.assertIn("main.py --smoke-test", script)
                self.assertIn("benchmark_catalog.py --check", script)
                self.assertIn("--onedir", script)
                self.assertNotIn("--onefile", script)
                self.assertIn("write_build_manifest.py", script)

    def test_cross_platform_build_versions_are_exact(self):
        requirements = (ROOT / "requirements-build.txt").read_text(encoding="utf-8")
        package_lines = [line for line in requirements.splitlines() if line and not line.startswith("#")]

        self.assertTrue(package_lines)
        self.assertTrue(all("==" in line for line in package_lines))

    def test_cross_platform_ci_does_not_claim_to_build_unbundled_releases(self):
        workflow = (ROOT / ".github" / "workflows" / "cross-platform-validation.yml").read_text(
            encoding="utf-8",
        )

        self.assertIn("source validation", workflow.lower())
        self.assertNotIn("pyinstaller", workflow.lower())


if __name__ == "__main__":
    unittest.main()

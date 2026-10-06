import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from tools.bundle_native_ocr import dependencies
from tools.lock_native_wheels import wheel_requirement
from tools.package_native_release import validate_payload, validate_report

ROOT = Path(__file__).resolve().parents[1]


class NativeReleaseTests(unittest.TestCase):
    def test_wheel_lock_records_metadata_and_bytes(self):
        with tempfile.TemporaryDirectory() as temp:
            wheel = Path(temp) / 'example.whl'
            with zipfile.ZipFile(wheel, 'w') as handle:
                handle.writestr('example-1.2.dist-info/METADATA', 'Name: example\nVersion: 1.2\n')
                handle.writestr('vendor/other-2.dist-info/METADATA', 'Name: other\nVersion: 2\n')
            self.assertRegex(wheel_requirement(wheel), r'^example==1\.2 --hash=sha256:[0-9a-f]{64}$')

    def test_payload_rejects_books_and_personal_state(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name in ('config.json', 'library_catalog.sqlite3', 'my-book.pdf'):
                path = root / name
                path.touch()
                with self.assertRaises(ValueError):
                    validate_payload(root)
                path.unlink()

    def test_payload_hashes_resources(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'resource.svg').write_text('<svg/>')
            self.assertEqual(list(validate_payload(root)), ['resource.svg'])

    def test_external_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'payload'
            root.mkdir()
            outside = Path(temp) / 'outside'
            outside.touch()
            try:
                (root / 'link').symlink_to(outside)
            except OSError:
                self.skipTest('Symlink creation unavailable on this host')
            with self.assertRaises(ValueError):
                validate_payload(root)

    def test_internal_symlink_allowed_for_native_bundles(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'binary').touch()
            try:
                (root / 'link').symlink_to(root / 'binary')
            except OSError:
                self.skipTest('Symlink creation unavailable on this host')
            self.assertEqual(set(validate_payload(root)), {'binary', 'link'})

    def test_ocr_linux_does_not_bundle_glibc_but_keeps_support_libraries(self):
        listing = 'libc.so.6 => /lib/libc.so.6 (0x1)\nlibfoo.so.1 => /lib/libfoo.so.1 (0x2)\n/lib64/ld-linux-x86-64.so.2 (0x3)'
        with patch('tools.bundle_native_ocr.output', return_value=listing):
            self.assertEqual(list(dependencies(Path('tesseract'), 'linux').values()), [Path('/lib/libfoo.so.1')])

    def test_missing_ocr_dependency_fails(self):
        with patch('tools.bundle_native_ocr.output', return_value='libfoo => not found'):
            with self.assertRaises(RuntimeError):
                dependencies(Path('tesseract'), 'linux')

    def test_source_report_cannot_authorize_frozen_package(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'report.json'
            path.write_text('{"version":"0.5.3","frozen":false,"passed":true,"checks":{"tk":"passed"}}')
            with self.assertRaises(ValueError):
                validate_report(path, {'tk'}, '0.5.3')

    def test_native_workflow_builds_each_real_target(self):
        workflow = (ROOT / '.github/workflows/native-release.yml').read_text()
        for marker in ('ubuntu-22.04', 'macos-15-intel', 'macos-15', 'lock_native_wheels.py', 'bundle_native_ocr.py', 'package_native_release.py', 'sha256sum -c', '--latest=false'):
            self.assertIn(marker, workflow)

    def test_native_scripts_include_resources_languages_and_frozen_gates(self):
        for name in ('linux', 'macos'):
            script = (ROOT / 'platforms' / name / ('build_' + name + '.sh')).read_text()
            for marker in ('--add-data "$ROOT/data:data"', 'eng spa fra nld chi_sim', '--runtime-self-test', '--first-use-self-test', '--require-hashes', '--hidden-import PIL._tkinter_finder'):
                self.assertIn(marker, script)


if __name__ == '__main__':
    unittest.main()

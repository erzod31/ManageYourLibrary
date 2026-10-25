"""Fail closed on partial, stale, cross-platform or unfrozen API evidence."""
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tools.package_native_release import validate_accessibility_api_report
from tools.verify_accessibility import BASE_CHECKS, WINDOWS_CHECKS, execution_provenance


COMMIT = 'a' * 40
TREE = {'sha256': 'b' * 64, 'files': 7}
EXECUTABLE = 'c' * 64


class NativeAccessibilityEvidenceTests(unittest.TestCase):
    def report(self, *, platform='linux', frozen=False):
        checks = WINDOWS_CHECKS if platform == 'macos' else BASE_CHECKS
        result = {'passed': True, 'backend': 'tk_native', 'platform': platform, 'version': '0.5.3',
                  'windowing_system': 'aqua' if platform == 'macos' else 'x11',
                  'frozen': frozen, 'checks': dict.fromkeys(checks, True), 'errors': []}
        if frozen:
            result['executable_sha256'] = EXECUTABLE
        else:
            result.update(git_commit=COMMIT, git_status='', source_tree=copy.deepcopy(TREE))
        return result

    def validate(self, report, *, platform='linux', frozen=False, **overrides):
        context = dict(platform=platform, frozen=frozen, version='0.5.3')
        context.update(dict(executable_sha256=EXECUTABLE) if frozen else dict(source_commit=COMMIT, source_tree=TREE))
        context.update(overrides)
        path = SimpleNamespace(read_text=lambda **_kwargs: json.dumps(report))
        return validate_accessibility_api_report(path, **context)

    def test_exact_complete_platform_checks_pass_with_bound_provenance(self):
        self.assertEqual(len(BASE_CHECKS), 21)
        self.assertEqual(len(WINDOWS_CHECKS), 22)
        for platform in ('linux', 'macos'):
            for frozen in (False, True):
                report = self.report(platform=platform, frozen=frozen)
                self.assertEqual(self.validate(report, platform=platform, frozen=frozen), report)

    def test_partial_extra_and_non_boolean_checks_are_rejected(self):
        for mutation in ('missing', 'extra', 'integer', 'string'):
            report = self.report()
            key = next(iter(report['checks']))
            if mutation == 'missing':
                del report['checks'][key]
            elif mutation == 'extra':
                report['checks']['unrelated_new_claim'] = True
            else:
                report['checks'][key] = 1 if mutation == 'integer' else 'passed'
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.validate(report)

    def test_failed_wrong_version_platform_backend_and_runtime_are_rejected(self):
        for key, value in (('passed', False), ('version', 'old'), ('platform', 'macos'),
                           ('backend', 'unsupported_runtime'), ('windowing_system', 'aqua'),
                           ('frozen', True), ('errors', ['Native provider failure'])):
            report = self.report()
            report[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.validate(report)

    def test_stale_dirty_missing_and_unknown_source_context_is_rejected(self):
        for key, value in (('git_commit', 'd' * 40), ('source_tree', {'sha256': 'd' * 64, 'files': 7}),
                           ('git_status', ' M source.py'), ('git_commit', None), ('source_tree', None)):
            report = self.report()
            report[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                self.validate(report)
        for overrides in ({'source_commit': 'unknown'}, {'source_tree': {'sha256': 'unknown', 'files': 0}},
                          {'source_tree': {'sha256': 'b' * 64, 'files': False}}):
            with self.subTest(context=overrides), self.assertRaises(ValueError):
                self.validate(self.report(), **overrides)

    def test_frozen_report_requires_actual_executable_binding(self):
        for value in ('', None, 'd' * 64, 'g' * 64):
            report = self.report(frozen=True)
            report['executable_sha256'] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.validate(report, frozen=True)
        report = self.report(frozen=True)
        report['executable_sha256'] = EXECUTABLE.upper()
        self.assertEqual(self.validate(report, frozen=True), report)
        with self.assertRaises(ValueError):
            self.validate(report, frozen=True, executable_sha256='g' * 64)

    def test_frozen_provenance_reads_the_running_binary_without_git(self):
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / 'synthetic-executable'
            data = b'Synthetic frozen executable bytes'
            executable.write_bytes(data)
            with patch('tools.verify_accessibility.sys.frozen', True, create=True), \
                    patch('tools.verify_accessibility.sys.executable', str(executable)), \
                    patch('tools.write_build_manifest.git_value') as git:
                report = execution_provenance()
            self.assertTrue(report['frozen'])
            self.assertEqual(report['executable_sha256'], hashlib.sha256(data).hexdigest())
            self.assertNotIn('git_commit', report)
            git.assert_not_called()

    def test_source_provenance_records_its_actual_tree_and_status(self):
        with patch('tools.verify_accessibility.sys.frozen', False, create=True), \
                patch('tools.write_build_manifest.git_value', side_effect=[COMMIT, ' M synthetic.py']), \
                patch('tools.write_build_manifest.source_tree_fingerprint', return_value=TREE):
            report = execution_provenance()
        self.assertFalse(report['frozen'])
        self.assertEqual(report['git_commit'], COMMIT)
        self.assertEqual(report['git_status'], ' M synthetic.py')
        self.assertEqual(report['source_tree'], TREE)
        self.assertNotIn('executable_sha256', report)

    def test_native_builds_keep_frozen_api_report_outside_signed_macos_bundle(self):
        root = Path(__file__).resolve().parents[1]
        macos = (root / 'platforms/macos/build_macos.sh').read_text(encoding='utf-8')
        linux = (root / 'platforms/linux/build_linux.sh').read_text(encoding='utf-8')
        self.assertIn('--accessibility-self-test "$ROOT/dist/macos/accessibility-self-test.json"', macos)
        self.assertNotIn('--accessibility-self-test "$ROOT/dist/macos/ManageYourLibrary.app/', macos)
        self.assertIn('--accessibility-self-test "$ROOT/dist/linux/ManageYourLibrary/accessibility-self-test.json"', linux)

    def test_native_builds_collect_and_bundle_runtime_and_wheel_notices_before_freezing(self):
        root = Path(__file__).resolve().parents[1]
        for platform in ('linux', 'macos'):
            script = (root / f'platforms/{platform}/build_{platform}.sh').read_text(encoding='utf-8')
            for command in (
                    'tools/collect_python_license_evidence.py --notices-only --output "$ROOT/dist/license-staging/python"',
                    'tools/verify_wheel_redistribution.py --collect-notices "$ROOT/dist/license-staging/wheels"'):
                self.assertIn(command, script)
                self.assertLess(script.index(command), script.index('python3 -m PyInstaller'))
            self.assertIn('--add-data "$ROOT/dist/license-staging/python:licenses/python-runtime"', script)
            self.assertIn('--add-data "$ROOT/dist/license-staging/wheels:licenses/wheels"', script)
            self.assertIn('--add-data "$GUI_LICENSES:licenses/tcltk"', script)
            self.assertIn('--exclude-module readline', script)

"""Offline fail-closed bridge recipe/evidence tests; real mainloop runs in builds."""
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import tkinter_tcl9_patch as recipe
from tools import verify_tkinter_threading as contract


class BridgeRecipeTests(unittest.TestCase):
    def source(self, directory):
        modules = Path(directory)
        raw = ('/* preserved upstream license */\n' + recipe.BEFORE
               + '\nstatic int Tkinter_busywaitinterval = 20;\n').encode()
        (modules / '_tkinter.c').write_bytes(raw)
        return modules, raw, hashlib.sha256(raw).hexdigest()

    def test_changes_only_thread_detection_and_preserves_tcl8_path(self):
        raw = 'before\n' + recipe.BEFORE + '\nafter\n'
        repaired = recipe.repair_source(raw)
        self.assertEqual(repaired.replace(recipe.AFTER, recipe.BEFORE), raw)
        self.assertIn('#if TCL_MAJOR_VERSION >= 9\n    v->threaded = 1;\n#else\n', repaired)
        self.assertIn(recipe.BEFORE + '\n#endif', repaired)

    def test_missing_or_duplicate_context_rejected(self):
        for raw in ('', recipe.BEFORE + '\n' + recipe.BEFORE):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                recipe.repair_source(raw)

    def test_unknown_download_is_untouched(self):
        with tempfile.TemporaryDirectory() as directory:
            modules, raw, _ = self.source(directory)
            with self.assertRaisesRegex(ValueError, 'Unrecognized'):
                recipe.apply_bridge_patch(modules)
            self.assertEqual((modules / '_tkinter.c').read_bytes(), raw)
            self.assertFalse((modules / recipe.OUTPUT).exists())
            self.assertFalse((modules / recipe.RECEIPT).exists())

    def test_separate_copy_receipt_and_resume_preserve_download(self):
        with tempfile.TemporaryDirectory() as directory:
            modules, raw, digest = self.source(directory)
            with patch.object(recipe, 'INPUT_SHA256', digest):
                result = recipe.apply_bridge_patch(modules)
                self.assertEqual(recipe.apply_bridge_patch(modules), result)
            self.assertEqual((modules / '_tkinter.c').read_bytes(), raw)
            self.assertEqual((modules / recipe.OUTPUT).read_text(), recipe.repair_source(raw.decode()))
            self.assertEqual(result['output_sha256'], hashlib.sha256((modules / recipe.OUTPUT).read_bytes()).hexdigest())
            self.assertEqual(result['patcher_sha256'], hashlib.sha256(Path(recipe.__file__).read_bytes()).hexdigest())
            self.assertEqual(result['source_url'], recipe.SOURCE_URL)
            self.assertIn('4a5a7b9f6d528c9be272d876ed7ca620f0e40038', result['fix_reference'])

    def test_missing_receipt_does_not_overwrite_output(self):
        with tempfile.TemporaryDirectory() as directory:
            modules, _, digest = self.source(directory)
            (modules / recipe.OUTPUT).write_text('retain')
            with patch.object(recipe, 'INPUT_SHA256', digest), self.assertRaises(FileExistsError):
                recipe.apply_bridge_patch(modules)
            self.assertEqual((modules / recipe.OUTPUT).read_text(), 'retain')

    def test_resume_rejects_changed_recipe_provenance_or_output(self):
        for changed in ('patcher_sha256', 'source_url', 'output_and_receipt', 'original'):
            with self.subTest(changed=changed), tempfile.TemporaryDirectory() as directory:
                modules, _, digest = self.source(directory)
                with patch.object(recipe, 'INPUT_SHA256', digest):
                    receipt = recipe.apply_bridge_patch(modules)
                    if changed == 'original':
                        (modules / '_tkinter.c').write_text('tampered')
                    elif changed == 'output_and_receipt':
                        (modules / recipe.OUTPUT).write_bytes(b'tampered')
                        receipt['output_sha256'] = hashlib.sha256(b'tampered').hexdigest()
                    else:
                        receipt[changed] = 'changed'
                    (modules / recipe.RECEIPT).write_text(json.dumps(receipt))
                    with self.assertRaises(ValueError):
                        recipe.apply_bridge_patch(modules)


class BridgeContractTests(unittest.TestCase):
    def report(self):
        return {'passed': True, 'checks': dict.fromkeys(contract.REQUIRED_CHECKS, True),
                'python_version': '3.12.10', 'tcl_version': '9.1.0', 'tk_version': '9.1.0',
                'platform': 'linux', 'busywait_interval_ms': 20, 'errors': [],
                'reader_started': False, 'audible_output': 'not_used',
                'bridge_sha256': 'a' * 64, 'contract_sha256': 'b' * 64}

    def test_valid_exact_contract_binds_binary_script_platform(self):
        report = self.report()
        self.assertIs(contract.validate_report(report, expected_bridge_sha256='a' * 64,
                                               expected_contract_sha256='b' * 64,
                                               expected_platform='linux'), report)

    def test_each_required_check_must_be_boolean_true(self):
        for name in contract.REQUIRED_CHECKS:
            for value in (False, 1, 'passed', None):
                report = self.report()
                report['checks'][name] = value
                with self.subTest(name=name, value=value), self.assertRaises(ValueError):
                    contract.validate_report(report)
            report = self.report()
            del report['checks'][name]
            with self.assertRaises(ValueError):
                contract.validate_report(report)

    def test_errors_versions_or_unbounded_extra_checks_fail(self):
        mutations = ({'passed': False}, {'python_version': '3.12.9'}, {'tcl_version': '8.6.12'},
                     {'tk_version': '9.0.0'}, {'platform': 'other'}, {'errors': ['RuntimeError']},
                     {'reader_started': True}, {'audible_output': 'enabled'},
                     {'busywait_interval_ms': 1}, {'bridge_sha256': 'missing'},
                     {'contract_sha256': 'missing'})
        for mutation in mutations:
            report = {**self.report(), **mutation}
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                contract.validate_report(report)
        report = self.report()
        report['checks']['extra'] = True
        with self.assertRaises(ValueError):
            contract.validate_report(report)

    def test_different_binary_script_or_platform_cannot_reuse_evidence(self):
        for options in ({'expected_bridge_sha256': 'c' * 64},
                        {'expected_contract_sha256': 'c' * 64}, {'expected_platform': 'darwin'}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                contract.validate_report(self.report(), **options)

    def test_refuses_overwrite_or_invalid_expected_binary_before_gui(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(contract, 'run_checks') as run:
            path = Path(directory) / 'contract.json'
            with self.assertRaises(ValueError):
                contract.run_and_record(path, expected_bridge_sha256='invalid')
            path.write_text('earlier evidence')
            with self.assertRaises(FileExistsError):
                contract.run_and_record(path, expected_bridge_sha256='a' * 64)
            run.assert_not_called()
            self.assertEqual(path.read_text(), 'earlier evidence')

    def test_failed_contract_recorded_with_failure_exit(self):
        report = copy.deepcopy(self.report())
        report['passed'] = False
        report['checks']['worker_completed'] = False
        with tempfile.TemporaryDirectory() as directory, patch.object(contract, 'run_checks', return_value=report):
            path = Path(directory) / 'contract.json'
            with patch('builtins.print'):
                self.assertEqual(contract.run_and_record(path, expected_bridge_sha256='a' * 64), 1)
            self.assertEqual(json.loads(path.read_text()), report)


if __name__ == '__main__':
    unittest.main()

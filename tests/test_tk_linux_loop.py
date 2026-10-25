"""Compile the actual GLib/Tcl Linux notifier contract without GUI/readers."""
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tools.test_native_a11y_linux_loop import REQUIRED_CHECKS, validate_report


class LoopEvidenceTests(unittest.TestCase):
    def report(self):
        return {'passed': True, 'checks': dict.fromkeys(REQUIRED_CHECKS, True),
                'versions': {'tcl': '8.6.12', 'glib': '2.72.4'},
                'benchmark': {'scope': 'synthetic_pipe_roundtrip_glib_tcl_not_atspi',
                              'unit': 'microseconds', 'samples_per_mode': 40, 'payload_bytes': 1,
                              'legacy_polling_10ms': {'samples': 40, 'p50': 10000.0, 'p95': 11000.0},
                              'fd_notifier': {'samples': 40, 'p50': 25000.0, 'p95': 30000.0}}}

    def test_no_performance_result_is_fabricated_as_a_contract(self):
        report = self.report()  # Slower/noisy notifier remains an honest measurement.
        self.assertIs(validate_report(report), report)

    def test_exact_true_contract_checks_required(self):
        for value in (1, False, 'true'):
            report = self.report()
            report['checks']['owner_thread_dispatch'] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_report(report)
        report = self.report()
        report['checks'].pop('queued_event_cleanup')
        with self.assertRaises(ValueError): validate_report(report)

    def test_context_lifetime_contracts_cannot_be_omitted(self):
        for field in ('pending_prepare_delete_last_context_ref', 'pending_check_delete_last_context_ref'):
            report = self.report()
            report['checks'].pop(field)
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_report(report)

    def test_benchmark_scope_samples_and_quantiles_checked(self):
        for field, value in (('samples', 39), ('p50', float('nan')), ('p95', 1), ('p50', True)):
            report = self.report()
            report['benchmark']['fd_notifier'][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                validate_report(report)


@unittest.skipUnless(sys.platform.startswith('linux'), 'Native GLib/Tcl notifier contract requires Linux')
class LinuxLoopTests(unittest.TestCase):
    def test_real_glib_tcl_notifier_contract(self):
        compiler, pkg_config = shutil.which('cc'), shutil.which('pkg-config')
        if not compiler or not pkg_config:
            if os.environ.get('GITHUB_ACTIONS') == 'true':
                self.fail('Linux CI must provide cc and pkg-config for the notifier contract')
            self.skipTest('Native notifier requires cc and pkg-config')
        flags = subprocess.run([pkg_config, '--cflags', '--libs', 'glib-2.0', 'tcl'],
                               capture_output=True, text=True, check=False)
        if flags.returncode:
            if os.environ.get('GITHUB_ACTIONS') == 'true':
                self.fail('Linux CI must provide GLib and Tcl development libraries')
            self.skipTest('Native notifier requires GLib and Tcl development libraries')
        source = Path(__file__).resolve().parents[1] / 'tools/native/test_tkUnixA11yLoop.c'
        with tempfile.TemporaryDirectory(prefix='myl_glib_tcl_loop_') as directory:
            executable = Path(directory) / 'loop-contract'
            compiled = subprocess.run([compiler, '-std=c11', '-Wall', '-Wextra', '-Werror', str(source),
                                       '-o', str(executable), *shlex.split(flags.stdout)],
                                      capture_output=True, text=True, timeout=30, check=False)
            self.assertEqual(compiled.returncode, 0, compiled.stderr[-10000:])
            result = subprocess.run([str(executable)], capture_output=True, text=True, timeout=15, check=False)
            self.assertEqual(result.returncode, 0, result.stderr[-10000:])
            self.assertIn('GLib/Tcl notifier contract: passed', result.stdout)

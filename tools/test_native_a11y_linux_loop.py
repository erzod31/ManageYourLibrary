"""Compile/run actual GLib + system Tcl contracts, without Tcl_Init or readers."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_CHECKS = {
    'owner_thread_dispatch', 'foreign_thread_rejected', 'dynamic_fd_and_same_number_reuse',
    'owned_duplicates_cloexec', 'teardown_preserves_original_fd_and_handler',
    'queued_event_cleanup', 'glib_and_tcl_timer_fairness', 'nested_loop_no_reentry',
    'delete_inside_dispatch', 'equal_ipc_samples_and_payload',
    'thread_exit_queued_event_cleanup',
    'worker_invoke_owner_thread', 'idle_wait_has_no_poll_timer',
    'idempotent_init_and_restart', 'nested_modal_glib_service', 'stale_query_fd_recovers',
    'pending_prepare_delete_last_context_ref', 'pending_check_delete_last_context_ref',
}


def validate_report(report):
    if (not isinstance(report, dict) or report.get('passed') is not True
            or set(report.get('checks', {})) != REQUIRED_CHECKS
            or any(value is not True for value in report['checks'].values())):
        raise ValueError('Incomplete native notifier contract')
    benchmark = report.get('benchmark', {})
    if (benchmark.get('scope') != 'synthetic_pipe_roundtrip_glib_tcl_not_atspi'
            or benchmark.get('unit') != 'microseconds' or benchmark.get('payload_bytes') != 1
            or type(benchmark.get('samples_per_mode')) is not int or benchmark['samples_per_mode'] < 10):
        raise ValueError('Invalid native notifier benchmark scope')
    for mode in ('legacy_polling_10ms', 'fd_notifier'):
        data = benchmark.get(mode, {})
        if data.get('samples') != benchmark['samples_per_mode']:
            raise ValueError('Unequal native notifier benchmark samples')
        for metric in ('p50', 'p95'):
            if type(data.get(metric)) not in (int, float) or not math.isfinite(data[metric]) or data[metric] < 0:
                raise ValueError('Invalid native notifier latency')
        if data['p95'] < data['p50']:
            raise ValueError('Invalid native notifier quantiles')
    versions = report.get('versions', {})
    if set(versions) != {'tcl', 'glib'} or not all(isinstance(v, str) and v for v in versions.values()):
        raise ValueError('Missing native notifier library versions')
    return report


def run(output):
    if not sys.platform.startswith('linux'):
        raise RuntimeError('Native notifier contract requires Linux')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    compiler, pkg_config = shutil.which('cc'), shutil.which('pkg-config')
    if not compiler or not pkg_config:
        raise RuntimeError('Native notifier requires cc and pkg-config')
    flags = subprocess.run([pkg_config, '--cflags', '--libs', 'glib-2.0', 'tcl'],
                           capture_output=True, text=True, timeout=10, check=True)
    native = ROOT / 'tools/native'
    source, header = native / 'test_tkUnixA11yLoop.c', native / 'tkUnixA11yLoop.h'
    executable = output / 'loop-contract'
    sanitizer_flags = ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
    probe_source, probe = output / 'sanitizer-probe.c', output / 'sanitizer-probe'
    probe_source.write_text('int main(void) { return 0; }\n', encoding='ascii')
    enabled = subprocess.run([compiler, *sanitizer_flags, str(probe_source), '-o', str(probe)],
                             capture_output=True, text=True, timeout=30, check=False).returncode == 0
    env = dict(os.environ, ASAN_OPTIONS='detect_leaks=0:halt_on_error=1',
               UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1')
    if enabled:
        enabled = subprocess.run([str(probe)], env=env, capture_output=True,
                                 text=True, timeout=10, check=False).returncode == 0
    subprocess.run([compiler, '-std=c11', '-Wall', '-Wextra', '-Werror',
                    *(sanitizer_flags if enabled else []), str(source),
                    '-o', str(executable), *shlex.split(flags.stdout)], check=True, timeout=30)
    result = subprocess.run([str(executable)], env=env, capture_output=True,
                            text=True, timeout=15, check=True)
    report = validate_report(json.loads(result.stdout))
    report['header_sha256'] = hashlib.sha256(header.read_bytes()).hexdigest()
    report['source_sha256'] = hashlib.sha256(source.read_bytes()).hexdigest()
    report['scope'] = 'native_glib_tcl_contract_and_synthetic_ipc_not_external_reader_validation'
    report['sanitizers'] = {'address_and_undefined': enabled, 'leak_detection': False,
                            'same_instrumentation_both_benchmark_modes': True,
                            'status': 'executed' if enabled else 'compiler_or_runtime_not_available'}
    (output / 'result.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    run(args.output)

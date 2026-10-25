"""Probe ONE GLib replacement in a disposable frozen Linux CI copy, silently.

An inert, non-allocated ELF section changes file bytes without changing code.
This tests loading changed bytes, not arbitrary ABI compatibility or legal
compliance. Never run on a desktop/user profile, start a reader, or modify input.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import time
from contextlib import ExitStack
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.external_accessibility_fixture import STAGES, atomic_json
from tools.package_linux_license_evidence import _validate, sha256
from tools.verify_accessibility import BASE_CHECKS
from tools.verify_orca_accessibility import (
    isolated_ci_problem,
    silent_environment,
    stop_owned,
)

LIBRARY = 'libglib-2.0.so.0'
SOURCE_FAMILY = 'glib2.0'
SECTION = '.myl_replacement_probe'
MARKER = b'MYL inert GLib replacement probe v1\n'
MAX_LOG = 4 * 1024 * 1024
MAX_JSON = 256 * 1024
TOTAL_SECONDS = 360
RUNTIME_CHECKS = {'tk_init', 'bundled_languages', 'image_ocr', 'pdfium_ocr', 'reader_isolation'}
FIRST_CHECKS = {'clean_defaults', 'empty_workspace', 'no_background_operations', 'no_automatic_network', 'fresh_state'}


def payload_inventory(root):
    """Record all original files and internal relative links without mutation."""
    root = Path(root).resolve()
    inventory = {}
    for path in sorted(root.rglob('*')):
        name = path.relative_to(root).as_posix()
        if path.is_symlink():
            target = os.readlink(path)
            if Path(target).is_absolute() or not path.resolve().is_relative_to(root):
                raise ValueError('Payload symlink cannot be safely copied')
            inventory[name] = {'link': target}
        elif path.is_file():
            inventory[name] = {'sha256': sha256(path)}
        elif not path.is_dir():
            raise ValueError('Payload has a non-regular entry')
    if not inventory:
        raise ValueError('Empty frozen payload')
    return inventory


def elf_identity(dynamic, symbols):
    sonames = re.findall(r'\(SONAME\).*?\[([^\]]+)\]', dynamic)
    entries = []
    for line in symbols.splitlines():
        fields = line.split()
        if fields and re.fullmatch(r'\d+:', fields[0]):
            if len(fields) < 7:
                raise ValueError('Malformed dynamic symbol entry')
            entries.append(' '.join(fields[1:]))
    if len(sonames) != 1 or not entries:
        raise ValueError('Missing unique SONAME or dynamic symbols')
    return {'soname': sonames[0], 'dynamic_symbols': sorted(entries)}


def verify_marker_section(path):
    """Parse ELF64 headers as data; the marker must have no ALLOC/EXEC flags."""
    path = Path(path)
    if not 64 <= path.stat().st_size <= 64 * 1024 * 1024:
        raise ValueError('Unexpected ELF file size')
    data = path.read_bytes()
    header = struct.unpack_from('<16sHHIQQQIHHHHHH', data)
    if data[:6] != b'\x7fELF\x02\x01' or header[2] != 62 or header[11] != 64:
        raise ValueError('Probe requires little-endian ELF64 x86_64')
    offset, count, strings_index = header[6], header[12], header[13]
    if not 0 < count <= 4096 or not 0 <= strings_index < count or offset + count * 64 > len(data):
        raise ValueError('Invalid ELF section table')
    sections = [struct.unpack_from('<IIQQQQIIQQ', data, offset + number * 64) for number in range(count)]
    strings = sections[strings_index]
    if strings[4] + strings[5] > len(data):
        raise ValueError('Invalid ELF string table')
    names = data[strings[4]:strings[4] + strings[5]]
    matches = []
    for section in sections:
        if section[0] >= len(names):
            raise ValueError('Invalid ELF section name')
        name = names[section[0]:].split(b'\x00', 1)[0].decode('ascii', errors='strict')
        if name == SECTION:
            matches.append(section)
    if len(matches) != 1:
        raise ValueError('Missing unique replacement marker section')
    section = matches[0]
    if (section[1] != 1 or section[2] & 6 or section[4] + section[5] > len(data)
            or data[section[4]:section[4] + section[5]] != MARKER):
        raise ValueError('Marker section is executable, allocated, or changed')
    return {'name': SECTION, 'allocated': False, 'executable': False, 'marker_sha256': hashlib.sha256(MARKER).hexdigest()}


def mapped_copy(text, target, *, inode, device):
    """Inspect only the owned PID's maps; match path AND device/inode."""
    if len(text.encode('utf-8')) > MAX_LOG:
        raise ValueError('Oversized process maps')
    target = Path(target).resolve()
    for line in text.splitlines():
        fields = line.split(None, 5)
        if len(fields) != 6 or not fields[4].isdigit() or 'x' not in fields[1]:
            continue
        path = re.sub(r'\\([0-7]{3})', lambda match: chr(int(match[1], 8)), fields[5])
        if path.endswith(' (deleted)') or Path(path).resolve() != target:
            continue
        try:
            major, minor = (int(value, 16) for value in fields[3].split(':'))
        except ValueError:
            continue
        if int(fields[4]) == inode and (major, minor) == device:
            return True
    return False


def read_json(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_JSON:
        raise ValueError('Missing or oversized owned fixture/report state')
    return json.loads(path.read_text(encoding='utf-8'))


def validate_diagnostic(report, checks, version, *, boolean_checks=False):
    return (report.get('passed') is True and report.get('frozen') is True
            and report.get('version') == version and set(report.get('checks', {})) == checks
            and (all(value is True for value in report['checks'].values()) if boolean_checks
                 else all(value == 'passed' for value in report['checks'].values()))
            and (not boolean_checks or (report.get('backend') == 'tk_native'
                                        and report.get('windowing_system') == 'x11' and report.get('errors') == [])))


def run_checks(payload: Path, evidence: Path):
    report = {'schema': 1, 'passed': False, 'status': 'not_run', 'checks': {},
              'scope': 'one_glib_inert_elf_marker_loading_not_arbitrary_abi_or_global_license_approval',
              'target_family': SOURCE_FAMILY, 'family_exercised': None, 'library': LIBRARY, 'reader_started': False,
              'audible_output': 'disabled', 'profile': 'synthetic_disposable',
              'not_established': ['other_library_families', 'arbitrary_library_modifications', 'global_license_approval']}
    problem = isolated_ci_problem()
    if problem:
        report['reason'] = problem
        return report
    tools = {name: shutil.which(name) for name in ('readelf', 'objcopy')}
    manager = Path('/usr/bin/openbox')
    if not all(tools.values()) or not manager.is_file():
        report['reason'] = 'missing_reviewed_ci_elf_tools_or_window_manager'
        return report
    payload = Path(payload)
    if payload.is_symlink() or not payload.is_dir():
        report['reason'] = 'missing_ordinary_frozen_payload'
        return report
    payload = payload.resolve()
    before = None
    processes = []
    checks = report['checks']
    deadline = time.monotonic() + TOTAL_SECONDS
    try:
        before = payload_inventory(payload)
        report['original_payload_inventory_sha256'] = hashlib.sha256(json.dumps(before, sort_keys=True).encode()).hexdigest()
        report['original_payload_entries'] = len(before)
        original = payload / '_internal' / LIBRARY
        executable = payload / 'ManageYourLibrary'
        if not original.is_file() or not executable.is_file():
            raise ValueError('Missing expected frozen launcher or reviewed GLib library')
        evidence = Path(evidence)
        if evidence.is_symlink() or not evidence.is_dir():
            raise ValueError('Evidence must be an ordinary collector output directory')
        inventory, _, _ = _validate(evidence)
        matches = [entry for entry in inventory['copied_binary_origins'] if entry['destination'] == LIBRARY]
        if len(matches) != 1 or matches[0]['source_package'] != SOURCE_FAMILY:
            raise ValueError('GLib origin is not an exact, reviewed Ubuntu source family')
        origin = matches[0]
        if sha256(original) != origin['original_sha256']:
            raise ValueError('Input GLib bytes changed from collected origin; investigate before probing')
        report['source_package'], report['source_version'] = origin['source_package'], origin['source_version']
        report['binary_package'], report['binary_version'] = origin['binary_package'], origin['binary_version']
        report['original_library_sha256'] = sha256(original)
        report['application_sha256'] = sha256(executable)
        version = (payload / '_internal' / 'VERSION').read_text(encoding='utf-8').strip()
        report['version'] = version
        checks['exact_origin_and_original_inventory'] = True
        with tempfile.TemporaryDirectory(prefix='myl_glib_replacement_ci_') as temporary, ExitStack() as stack:
            directory = Path(temporary).resolve()
            env = silent_environment(os.environ, directory)
            copy = directory / 'app'
            shutil.copytree(payload, copy, symlinks=True)
            if payload_inventory(copy) != before:
                raise ValueError('Disposable application copy differs before modification')
            checks['complete_disposable_copy'] = True
            launcher = copy / executable.relative_to(payload)
            modified = (copy / '_internal' / LIBRARY).resolve()
            if not modified.is_relative_to(copy) or modified.is_symlink():
                raise ValueError('Replacement target escapes disposable application')

            def owned(command, phase, seconds=90):
                log = directory / (phase + '.log')
                handle = stack.enter_context(log.open('w'))
                process = subprocess.Popen(command, env=env, stdin=subprocess.DEVNULL,
                                           stdout=handle, stderr=subprocess.STDOUT, start_new_session=True)
                processes.append(process)
                stack.callback(stop_owned, process)
                end = min(deadline, time.monotonic() + seconds)
                while process.poll() is None:
                    if time.monotonic() >= end or log.stat().st_size > MAX_LOG:
                        raise TimeoutError('Owned replacement probe deadline/log bound: ' + phase)
                    time.sleep(.05)
                if process.returncode:
                    raise RuntimeError('Owned replacement probe failed: ' + phase)
                if log.stat().st_size > MAX_LOG:
                    raise ValueError('Owned replacement probe log exceeded bound')
                return log.read_text(encoding='utf-8', errors='replace')

            def identity(path, phase):
                return elf_identity(owned([tools['readelf'], '--dynamic', '--wide', str(path)], phase + '-dynamic', 10),
                                    owned([tools['readelf'], '--dyn-syms', '--wide', str(path)], phase + '-symbols', 10))

            original_identity = identity(modified, 'before')
            if original_identity['soname'] != LIBRARY:
                raise ValueError('Unexpected GLib SONAME')
            marker = directory / 'marker.bin'
            marker.write_bytes(MARKER)
            output = modified.with_name(modified.name + '.probe-new')
            owned([tools['objcopy'], '--add-section', SECTION + '=' + str(marker), '--set-section-flags',
                   SECTION + '=readonly,contents', str(modified), str(output)], 'objcopy', 15)
            output.replace(modified)
            report['section'] = verify_marker_section(modified)
            report['modified_library_sha256'] = sha256(modified)
            checks['different_bytes_same_soname_and_symbols'] = (report['modified_library_sha256'] != report['original_library_sha256']
                                                                 and identity(modified, 'after') == original_identity)
            if not checks['different_bytes_same_soname_and_symbols']:
                raise ValueError('ELF replacement did not preserve inspected ABI metadata')
            for flag, required in (('runtime', RUNTIME_CHECKS), ('first-use', FIRST_CHECKS), ('accessibility', BASE_CHECKS)):
                result = directory / (flag + '.json')
                owned([str(launcher), '--' + flag + '-self-test', str(result)], flag)
                checks[flag + '_diagnostic'] = validate_diagnostic(read_json(result), required, version,
                                                                 boolean_checks=flag == 'accessibility')
                if not checks[flag + '_diagnostic']:
                    raise ValueError('Modified-copy diagnostic contract failed: ' + flag)
            wm_log = stack.enter_context((directory / 'wm.log').open('w'))
            wm = subprocess.Popen([str(manager)], env=env, stdin=subprocess.DEVNULL,
                                  stdout=wm_log, stderr=subprocess.STDOUT, start_new_session=True)
            processes.append(wm)
            stack.callback(stop_owned, wm)
            control = directory / 'fixture'
            control.mkdir()
            fixture_log = stack.enter_context((directory / 'fixture.log').open('w'))
            fixture = subprocess.Popen([str(launcher), '--external-accessibility-fixture', str(control)], env=env,
                                       stdin=subprocess.DEVNULL, stdout=fixture_log, stderr=subprocess.STDOUT,
                                       start_new_session=True)
            processes.append(fixture)
            stack.callback(stop_owned, fixture)

            def state():
                return read_json(control / 'state.json') if (control / 'state.json').exists() else None

            def wait_for(predicate, seconds):
                end = min(deadline, time.monotonic() + seconds)
                while time.monotonic() < end:
                    if fixture.poll() is not None or wm.poll() is not None:
                        raise RuntimeError('Owned GUI fixture/window manager exited early')
                    if any(p.stat().st_size > MAX_LOG for p in (directory / 'fixture.log', directory / 'wm.log')):
                        raise ValueError('Owned GUI log exceeded bound')
                    value = state()
                    if value and predicate(value):
                        return value
                    time.sleep(.05)
                raise TimeoutError('Owned replacement GUI fixture deadline')

            ready = wait_for(lambda value: value.get('action') == 'ready', 15)
            if ready.get('pid') != fixture.pid or ready.get('frozen') is not True or ready.get('version') != version:
                raise ValueError('Fixture PID/frozen identity mismatch')
            checks['owned_frozen_fixture_pid'] = True
            for sequence, action in enumerate(STAGES, 1):
                atomic_json(control / 'command.json', {'sequence': sequence, 'action': action})
                current = wait_for(lambda value, seq=sequence: value.get('sequence') == seq, 5)
                if (current.get('action') != action or current.get('focus_matches_target') is not True
                        or current.get('voice_off') is not True or current.get('no_network') is not True or current.get('errors')):
                    raise ValueError('Real GUI focus/isolation contract failed')
            checks['real_gui_focus_voice_off_no_network'] = True
            stat = modified.stat()
            maps = Path('/proc') / str(fixture.pid) / 'maps'
            if maps.stat().st_size > MAX_LOG:
                raise ValueError('Owned PID maps exceeded bound')
            with maps.open(encoding='utf-8') as stream:
                text = stream.read(MAX_LOG + 1)
            checks['modified_library_mapped_from_copy'] = mapped_copy(text, modified, inode=stat.st_ino,
                                                                      device=(os.major(stat.st_dev), os.minor(stat.st_dev)))
            if not checks['modified_library_mapped_from_copy']:
                raise ValueError('Owned frozen fixture did not map the modified GLib copy')
            report['family_exercised'] = SOURCE_FAMILY
            if sha256(modified) != report['modified_library_sha256']:
                raise ValueError('Modified copy changed unexpectedly during diagnostics')
            atomic_json(control / 'command.json', {'sequence': len(STAGES) + 1, 'action': 'shutdown'})
            fixture.wait(timeout=8)
            if fixture.returncode:
                raise RuntimeError('Owned GUI fixture failed on shutdown')
            checks['fixture_clean_shutdown'] = True
            report['status'] = 'passed'
    except (OSError, ValueError, RuntimeError, TimeoutError, TypeError, KeyError, subprocess.SubprocessError, struct.error) as exc:
        report['status'] = 'failed'
        # Exceptions use phase descriptions, not captured logs or user paths.
        report['reason'] = type(exc).__name__
        if isinstance(exc, (ValueError, RuntimeError, TimeoutError)):
            report['detail'] = re.sub(r'/(?:home|Users|tmp)/[^\s]+', '<QA_PATH>', str(exc))[:500]
    finally:
        for process in reversed(processes):
            try:
                stop_owned(process)
            except (OSError, subprocess.SubprocessError):
                report['cleanup_error'] = 'owned_process_cleanup_failed'
        checks['owned_processes_stopped'] = all(process.poll() is not None for process in processes)
        if before is not None:
            try:
                after = payload_inventory(payload)
                checks['original_payload_unchanged'] = after == before
                report['original_payload_after_sha256'] = hashlib.sha256(json.dumps(after, sort_keys=True).encode()).hexdigest()
            except (OSError, ValueError):
                checks['original_payload_unchanged'] = False
        if report['status'] == 'passed' and not all(checks.values()):
            report['status'] = 'failed'
    report['passed'] = report['status'] == 'passed' and all(checks.values()) and not report.get('cleanup_error')
    return report


def run_and_record(payload, evidence, output):
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise FileExistsError('Refusing to overwrite earlier replacement evidence')
    report = run_checks(payload, evidence)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, indent=2)
        stream.write('\n')
    print(json.dumps({'status': report['status'], 'family_exercised': report['family_exercised'], 'scope': report['scope']}))
    return 0 if report['passed'] else 2 if report['status'] == 'not_run' else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--payload', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(run_and_record(args.payload, args.evidence, args.output))

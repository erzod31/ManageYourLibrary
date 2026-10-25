"""Reject embedded Windows profile paths in native/runtime release inputs.

Read-only and intentionally reports filenames, never the private strings found.
This is a bounded path check, not a complete secret or personal-data scanner.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

WINDOWS_PROFILE = re.compile(rb'[A-Za-z]:[\\/]+Users[\\/]+[^\\/\x00\r\n\t ]+[\\/]', re.I)
CHECKED_SUFFIXES = {'.exe', '.dll', '.pyd', '.tcl', '.py', '.json', '.txt', '.cfg', '.ini', '.sh'}


def contains_profile_path(data, *, prefixes=()):
    # Removing NULs also finds UTF-16LE/BE strings, including unaligned strings.
    if WINDOWS_PROFILE.search(data.replace(b'\x00', b'')):
        return True
    folded = data.lower()
    for prefix in prefixes:
        for value in {str(prefix), str(prefix).replace('\\', '/')}:
            for encoding in ('utf-8', 'utf-16-le', 'utf-16-be'):
                if value.encode(encoding).lower() in folded:
                    return True
    return False


def require_neutral_location(path):
    if contains_profile_path(str(path).encode('utf-8'), prefixes=(Path.home(),)):
        raise ValueError('Native GUI build needs a neutral directory outside user profiles (for example C:/myl-native-build)')


def validate_tree(directory):
    directory = Path(directory).resolve()
    if not directory.is_dir():
        raise FileNotFoundError('Missing privacy-check input directory')
    findings = []
    checked = 0
    for path in sorted(directory.rglob('*')):
        if path.is_file() and path.suffix.lower() in CHECKED_SUFFIXES:
            if path.is_symlink() or not path.resolve().is_relative_to(directory):
                raise ValueError('Privacy input escapes its directory')
            checked += 1
            if contains_profile_path(path.read_bytes(), prefixes=(Path.home(),)):
                findings.append(path.relative_to(directory).as_posix())
    if not checked:
        raise ValueError('No native/runtime privacy inputs found')
    return {'passed': not findings, 'files_checked': checked, 'findings': findings,
            'scope': 'windows_profile_paths_in_native_and_runtime_inputs'}


def require_clean_tree(directory):
    report = validate_tree(directory)
    if not report['passed']:
        raise ValueError('Private profile path in build input: ' + ', '.join(report['findings'][:8]))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    report = validate_tree(args.directory)
    encoded = json.dumps(report, indent=2)
    if args.output:
        args.output.write_text(encoded + '\n', encoding='utf-8')
    print(encoded)
    raise SystemExit(0 if report['passed'] else 1)

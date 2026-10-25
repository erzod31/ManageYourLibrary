"""Keep Windows native inputs inside explicit build roots, never ambient PATH.

Windows 10+ supplies the Universal CRT and API-set forwarding contracts. Do not
redistribute copies found in unrelated applications. The provenance receipt
records source-relative names and hashes, not local profile paths or approval
of redistribution rights.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path, PurePosixPath

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

OS_COMPONENT = re.compile(r'(?i)^(?:ucrtbase|(?:api|ext)-ms-win-[^/\\]+)\.dll$')
NATIVE_SUFFIXES = {'.dll', '.pyd', '.exe'}
RECEIPT = Path('_internal/licenses/windows-dependency-provenance.json')


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def normalized_destination(value):
    name = str(value).replace('\\', '/')
    parts = PurePosixPath(name).parts
    if (not parts or name.startswith('/') or any(part in {'.', '..'} or ':' in part for part in parts)):
        raise ValueError('Unsafe native dependency destination')
    return name


def select_inputs(binaries, datas, *, roots):
    """Filter a PyInstaller TOC and return portable, hash-bound provenance.

    This is a selection step before COLLECT, not deletion from a built package.
    A new native input from outside the selected venv/Python/GUI/OCR roots is an
    error. Exact upstream/notice reviews remain separate from this origin gate.
    """
    approved = sorted(((label, Path(path).resolve()) for label, path in roots.items()),
                      key=lambda value: len(value[1].parts), reverse=True)
    included, excluded, seen = [], [], set()

    def select(entries):
        result = []
        for item in entries:
            if len(item) != 3:
                raise ValueError('Unexpected PyInstaller dependency record')
            name, source, kind = item
            name = normalized_destination(name)
            if PurePosixPath(name).suffix.lower() not in NATIVE_SUFFIXES:
                result.append(item)
                continue
            if OS_COMPONENT.fullmatch(PurePosixPath(name).name):
                excluded.append(name)
                continue
            source = Path(source)
            if source.is_symlink() or not source.is_file():
                raise ValueError('Missing or symlink native dependency: ' + name)
            resolved = source.resolve()
            origin = next(((label, resolved.relative_to(root).as_posix())
                           for label, root in approved if resolved.is_relative_to(root)), None)
            if origin is None:
                raise ValueError('Native dependency outside controlled build roots: ' + name)
            destination = '_internal/' + name
            if destination.casefold() in seen:
                raise ValueError('Repeated native dependency destination: ' + name)
            seen.add(destination.casefold())
            included.append({'path': destination, 'sha256': digest(resolved),
                             'origin': {'root': origin[0], 'relative': origin[1]}})
            result.append(item)
        return result

    selected_binaries = select(binaries)
    selected_datas = select(datas)
    if not included:
        raise ValueError('No controlled native dependencies selected')
    report = {'schema': 1, 'platform': 'windows-x64', 'os_runtime': 'Windows 10 or later system UCRT/API sets',
              'scope': 'controlled input origins and unchanged native bytes; not legal approval',
              'files': sorted(included, key=lambda row: row['path']),
              'excluded_os_components': sorted(set(excluded))}
    return selected_binaries, selected_datas, report


def verify_payload(folder):
    folder = Path(folder).resolve()
    report = json.loads((folder / RECEIPT).read_text(encoding='utf-8'))
    if report.get('schema') != 1 or report.get('platform') != 'windows-x64':
        raise ValueError('Unsupported Windows dependency provenance')
    expected = {}
    for row in report.get('files', []):
        name = normalized_destination(row['path'])
        if (not name.startswith('_internal/') or PurePosixPath(name).suffix.lower() not in NATIVE_SUFFIXES
                or OS_COMPONENT.fullmatch(PurePosixPath(name).name) or name.casefold() in expected
                or not re.fullmatch(r'[0-9a-f]{64}', row.get('sha256', ''))):
            raise ValueError('Invalid native provenance entry')
        origin = row.get('origin', {})
        if origin.get('root') not in {'python', 'python_wheels', 'gui_runtime', 'gui_bridge', 'controlled_ocr', 'microsoft_redist'}:
            raise ValueError('Unknown native provenance root')
        normalized_destination(origin['relative'])
        expected[name.casefold()] = row['sha256']
    if not expected:
        raise ValueError('Empty Windows native provenance')
    actual = {}
    for path in folder.rglob('*'):
        if path.is_file() and path.suffix.lower() in NATIVE_SUFFIXES:
            if path.is_symlink() or not path.resolve().is_relative_to(folder):
                raise ValueError('Native payload escapes its directory')
            name = path.relative_to(folder).as_posix()
            if name == 'ManageYourLibrary.exe':
                continue  # Bound separately by build-manifest.json.
            if OS_COMPONENT.fullmatch(path.name):
                raise ValueError('OS UCRT/API-set copy must not be bundled: ' + name)
            key = name.casefold()
            if key in actual:
                raise ValueError('Repeated case-insensitive native payload name')
            actual[key] = digest(path)
    if actual != expected:
        raise ValueError('Native payload bytes or inventory differ from controlled input provenance')
    from tools.windows_vc_runtime import verify_payload as verify_microsoft_runtime
    runtime = verify_microsoft_runtime(folder)
    return {'passed': True, 'native_files': len(actual), 'receipt_sha256': digest(folder / RECEIPT),
            'microsoft_runtime': runtime, 'scope': report['scope']}


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('payload', type=Path)
    args = parser.parse_args()
    print(json.dumps(verify_payload(args.payload), indent=2))

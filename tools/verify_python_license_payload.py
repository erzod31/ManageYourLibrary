"""Check collected Python notices and their selected native-file provenance.

An integrity/attribution gate, never a legal or full-release approval. The
collector first verifies upstream downloads and the official Python archive.
"""
import hashlib
import json
from pathlib import Path, PurePosixPath

from tools.collect_python_license_evidence import SOURCES


def digest(path):
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def safe_file(root, name):
    parts = PurePosixPath(name).parts
    if not parts or name.startswith('/') or '\\' in name or any(p in {'.', '..'} or ':' in p for p in parts):
        raise ValueError('Unsafe Python notice path')
    path = root.joinpath(*parts)
    if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('Missing or unsafe Python notice file')
    return path


def verify_windows_payload(folder):
    folder = Path(folder)
    base = folder / '_internal/licenses/python-runtime'
    catalog = json.loads(SOURCES.read_text(encoding='utf-8'))
    receipt = json.loads(safe_file(base, 'receipt.json').read_text(encoding='utf-8'))
    if (receipt.get('schema') != 1 or receipt.get('mode') != 'windows_pe_verified'
            or receipt.get('source_catalog_sha256') != digest(SOURCES)
            or receipt.get('python_version') != catalog['python_version']
            or receipt.get('architecture') != catalog['architecture']
            or receipt.get('distribution') != catalog['distribution']
            or receipt.get('global_release_approval') is not False
            or receipt.get('redistribution_review') != 'not_complete'):
        raise ValueError('Incomplete or unreviewed Python notice provenance')
    if safe_file(base, 'sources.json').read_bytes() != SOURCES.read_bytes():
        raise ValueError('Python notice source catalog differs from the pinned input')
    required = {item['file'] for item in catalog['notices']} | {'sources.json', 'README.txt'}
    if set(receipt.get('files', {})) != required:
        raise ValueError('Incomplete Python notice inventory')
    actual = {path.relative_to(base).as_posix() for path in base.rglob('*') if path.is_file()}
    if actual != required | {'receipt.json'}:
        raise ValueError('Unexpected Python notice inventory')
    for name, expected in receipt['files'].items():
        if digest(safe_file(base, name)) != expected:
            raise ValueError('Modified Python notice: ' + name)
    observed = receipt.get('notices', [])
    if len(observed) != len(catalog['notices']):
        raise ValueError('Incomplete Python source notice chain')
    for expected, entry in zip(catalog['notices'], observed):
        if (any(entry.get(key) != value for key, value in expected.items())
                or receipt['files'][expected['file']] != entry.get('notice_sha256')):
            raise ValueError('Python notice chain differs from the source catalog')
        if not expected.get('extract') and entry.get('notice_sha256') != expected['sha256']:
            raise ValueError('Python verbatim notice differs from upstream')
    official_license = folder / '_internal/licenses/python/LICENSE.txt'
    if digest(official_license) != receipt.get('official_python_license_sha256'):
        raise ValueError('Official Python license missing or changed')
    origins = json.loads((folder / '_internal/licenses/windows-dependency-provenance.json').read_text(encoding='utf-8'))
    native = receipt.get('native_files', {})
    if set(native) != set(catalog['native_files']):
        raise ValueError('Incomplete verified Python native family')
    if any(value.get('python_relative_path') != catalog['native_files'][name]
           for name, value in native.items()):
        raise ValueError('Python native mapping differs from the source catalog')
    by_relative = {value['python_relative_path'].casefold(): value for value in native.values()}
    if len(by_relative) != len(native):
        raise ValueError('Ambiguous case-folded Python native mapping')
    checked = 0
    for row in origins['files']:
        if row['origin']['root'] == 'python':
            expected = by_relative.get(row['origin']['relative'].casefold())
            if not expected or row['sha256'] != expected['sha256']:
                raise ValueError('Selected Python binary has no official archive provenance')
            if digest(safe_file(folder, row['path'])) != expected['sha256']:
                raise ValueError('Selected Python binary changed after provenance collection')
            checked += 1
    if not checked:
        raise ValueError('No selected Python native inputs verified')
    return {'passed': True, 'python_version': catalog['python_version'], 'selected_native_files': checked,
            'notice_files': len(required), 'receipt_sha256': digest(base / 'receipt.json'),
            'scope': 'collected notice integrity and selected Python origin; not global legal approval'}

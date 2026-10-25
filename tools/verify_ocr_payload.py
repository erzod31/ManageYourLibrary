"""Reject legacy, incomplete or modified OCR bundles before distribution."""
import argparse
import hashlib
import json
import sys
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]


def sha256(path):
    with Path(path).open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def validate_payload(directory):
    directory = Path(directory).resolve()
    lock_path = ROOT / 'tools/ocr_source_lock.json'
    lock = json.loads(lock_path.read_text(encoding='utf-8'))
    manifest = json.loads((directory / 'native-ocr-manifest.json').read_text(encoding='utf-8'))
    if (manifest.get('schema') != 1 or manifest.get('profile') != lock['profile']
            or manifest.get('platform') != sys.platform
            or manifest.get('source_lock_sha256') != sha256(lock_path)
            or manifest.get('components') != lock['components']
            or manifest.get('models_commit') != lock['models_commit']
            or manifest.get('legacy_artifacts_cleared') is not False
            or manifest.get('license_resolution') != 'replaced_legacy_stack_no_gpl_lgpl_ocr_libraries'):
        raise ValueError('OCR payload does not match the reviewed source profile')
    files = manifest.get('files', {})
    expected = set(files) | {'native-ocr-manifest.json'}
    actual = set()
    for path in directory.rglob('*'):
        if path.is_symlink():
            raise ValueError('OCR payload must not contain symlinks')
        if path.is_file():
            actual.add(path.relative_to(directory).as_posix())
    # The native destination has one tracked build-help document, not a binary.
    if actual - expected == {'README.md'}:
        actual.remove('README.md')
    if actual != expected:
        raise ValueError('OCR inventory has missing or unexpected files: ' + str(sorted(actual ^ expected)))
    for relative, expected_hash in files.items():
        parts = PurePosixPath(relative).parts
        if (not parts or relative.startswith('/') or '\\' in relative
                or any(p in {'.', '..'} or ':' in p for p in parts)):
            raise ValueError('Unsafe OCR inventory path')
        if sha256(directory / relative) != expected_hash:
            raise ValueError('Modified OCR payload file: ' + relative)
    binary = 'tesseract.exe' if manifest['platform'] == 'win32' else 'tesseract'
    if binary not in files:
        raise ValueError('OCR executable missing')
    # No dynamic OCR libraries, debug/training Java tools, or hidden second CLI.
    for relative in files:
        path = PurePosixPath(relative)
        if path.suffix.lower() in {'.dll', '.so', '.dylib', '.jar', '.exe'} and relative != binary:
            raise ValueError('Unapproved OCR binary: ' + relative)
    required = {binary, 'sources/ocr_source_lock.json', 'sources/build_permissive_ocr.py',
                'sources/build-commands.json', 'licenses/TESSDATA-APACHE-2.0.txt',
                'tessdata/configs/tsv', 'tessdata/configs/txt'}
    for component in lock['components']:
        name = component['id']
        required |= {'sources/' + name + '.tar.gz', 'licenses/' + name + '/SOURCE-NOTICES.txt'}
        required.add('sources/' + name + '-CMakeCache.txt')
        if sha256(directory / 'sources' / (name + '.tar.gz')) != component['sha256']:
            raise ValueError('Missing exact upstream source: ' + name)
        for notice, expected_hash in component['notices'].items():
            relative = 'licenses/' + name + '/' + PurePosixPath(notice).name
            required.add(relative)
            if sha256(directory / relative) != expected_hash:
                raise ValueError('License notice differs from upstream: ' + relative)
    for name, expected_hash in lock['models'].items():
        relative = 'tessdata/' + name + '.traineddata'
        required.add(relative)
        if sha256(directory / relative) != expected_hash:
            raise ValueError('Unapproved trained-data model: ' + name)
    if not required <= set(files):
        raise ValueError('OCR provenance/notice inventory is incomplete')
    if manifest['platform'] == 'win32':
        import pefile
        with pefile.PE(str(directory / binary)) as pe:
            names = {entry.dll.decode('ascii').lower() for entry in pe.DIRECTORY_ENTRY_IMPORT}
            names |= {entry.dll.decode('ascii').lower() for entry in getattr(pe, 'DIRECTORY_ENTRY_DELAY_IMPORT', [])}
        allowed = {'kernel32.dll', 'advapi32.dll', 'ws2_32.dll', 'user32.dll',
                   'shell32.dll', 'ole32.dll', 'bcrypt.dll', 'ntdll.dll'}
        if not names or any(n not in allowed and not n.startswith('api-ms-win-') for n in names):
            raise ValueError('OCR imports an unapproved DLL: ' + str(sorted(names)))
        if names != {n.lower() for n in manifest['system_dependencies']}:
            raise ValueError('OCR import receipt differs from the executable')
    return {'profile': lock['profile'], 'files': len(files), 'sha256': sha256(directory / 'native-ocr-manifest.json'),
            'resolution': manifest['license_resolution'], 'legacy_artifacts_cleared': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(validate_payload(args.directory), indent=2))
    except (OSError, ValueError, KeyError) as exc:
        sys.exit(str(exc))

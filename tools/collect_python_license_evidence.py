"""Collect pinned Python license notices, optionally verifying Windows PE origin.

No interpreter, DLL or executable is run or copied. New evidence directories
only: source/runtime installations and prior evidence are never modified.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import sys
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

SOURCES = Path(__file__).with_name('python_runtime_sources.json')
MAX_DOWNLOAD = 32 * 1024 * 1024
MAX_EXPANDED = 128 * 1024 * 1024
VERSION = (3, 12, 10)


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def _safe_relative(value):
    path = PurePosixPath(value)
    if not path.parts or path.is_absolute() or '\\' in value or any(p in {'.', '..'} or ':' in p for p in path.parts):
        raise ValueError('Unsafe relative evidence path')
    return path


def _read_url(source):
    if urlsplit(source['url']).scheme != 'https':
        raise ValueError('Evidence requires HTTPS')
    with urllib.request.urlopen(source['url'], timeout=45) as response:
        if urlsplit(response.geturl()).scheme != 'https':
            raise ValueError('Evidence redirect requires HTTPS')
        raw = response.read(min(MAX_DOWNLOAD, source['bytes']) + 1)
    return raw


def _download(source):
    if not isinstance(source.get('bytes'), int) or not 0 < source['bytes'] <= MAX_DOWNLOAD:
        raise ValueError('Invalid pinned download bound')
    if not re.fullmatch('[0-9a-f]{64}', source.get('sha256', '')):
        raise ValueError('Invalid pinned source hash')
    raw = _read_url(source)
    if len(raw) != source['bytes'] or sha256(raw) != source['sha256']:
        raise ValueError('Python evidence source hash/size mismatch')
    return raw


def _catalog():
    raw = SOURCES.read_bytes()
    data = json.loads(raw)
    if data.get('schema') != 1 or data.get('python_version') != '3.12.10' or data.get('architecture') != 'AMD64':
        raise ValueError('Unsupported Python evidence source catalog')
    names = []
    for item in data['notices']:
        _safe_relative(item['file'])
        if item['scope'] not in {'common', 'windows'}:
            raise ValueError('Unknown notice scope')
        names.append(item['file'].casefold())
    if len(names) != len(set(names)) or set(names) & {'readme.txt', 'sources.json', 'receipt.json'}:
        raise ValueError('Duplicate/reserved evidence filename')
    if not data['native_files'] or 'python312.dll' not in data['native_files']:
        raise ValueError('Missing pinned Python native family')
    for name, relative in data['native_files'].items():
        if _safe_relative(name).name != name:
            raise ValueError('Native archive member must be a basename')
        _safe_relative(relative)
    return data, raw


def _initial_comment(raw):
    start = len(raw) - len(raw.lstrip())
    end = raw.find(b'*/', start)
    if raw[start:start + 2] != b'/*' or not start <= end < 8192:
        raise ValueError('Pinned source no longer has an initial license comment')
    # Keep the exact source bytes, including its comment delimiters.
    return raw[start:end + 2]


def _notices(data, *, windows):
    files, evidence = {}, []
    for source in data['notices']:
        if not windows and source['scope'] != 'common':
            continue
        raw = _download(source)
        notice = _initial_comment(raw) if source.get('extract') == 'initial_c_comment' else raw
        if source.get('extract') not in {None, 'initial_c_comment'}:
            raise ValueError('Unknown notice extraction rule')
        files[source['file']] = notice
        evidence.append({**source, 'notice_sha256': sha256(notice), 'notice_bytes': len(notice)})
    return files, evidence


def _summary(*, windows):
    common = (
        'Python runtime attribution and provenance evidence, not a legal or security certification.\n'
        'The CPython 3.12.10 history/license document and supplemental notices remain verbatim.\n'
        'Initial license comments were copied byte-for-byte from the pinned HACL*, KaRaMeL and BLAKE2 sources.\n'
        'Their raw source hashes and extraction rule are recorded in receipt.json.\n'
        'The Unicode notice is the hash-pinned current V3 text; the UCD 15.0.0 ReadMe is separately retained.\n'
        'This collector does not modify CPython sources. The GUI build preserves the original _tkinter.c\n'
        'download and compiles a separate copy with the pinned Tcl 9 thread-detection backport.\n'
        'See licenses/tcltk/myl-tkinter-tcl9-repair for sources, license, recipe and contract.\n'
        'The separate Tk Windows/Linux accessibility repairs are project-maintained, not an upstream release.\n'
        'The original PSF, Microsoft and dependency rights are not replaced by the project MIT license.\n'
        'This evidence does not approve redistribution of the entire application or historical releases.\n'
    )
    if windows:
        return (common + 'The 25 listed PE files describe the original Python BASE installation: their bytes matched\n'
                'the official CPython Windows AMD64 embed archive. This is not a claim that the app ships\n'
                'all of those files unchanged when packaging deliberately replaces its two VC runtime DLLs.\n'
                'No PE file or archive is copied into this evidence directory. The official Python LICENSE.txt\n'
                'already retained by the Windows build must accompany these supplemental notices.\n'
                'liblzma is the public-domain library portion, not the separately licensed XZ tools/build scripts.\n'
                'SQLite is public domain; its publisher attribution reference is in sources.json.\n'
                'The Additional Conditions in official Python LICENSE.txt describe Microsoft code in that\n'
                'original Python distribution; they do not automatically grant redistribution rights for\n'
                'a newer CRT selected separately from Visual Studio REDIST. Such replacement DLLs have a\n'
                'separate MSVC receipt with their own provenance, hashes and license_eligibility: not_determined.\n'
                'Consult that receipt and the applicable Microsoft terms; no rights are relabeled as MIT.\n').encode()
    return (common + 'NOTICES-ONLY MODE: no Windows archive or installed native files were verified.\n'
            'The host may link different OS/native-library versions; their complete closure still needs review.\n'
            'Windows component versions listed in sources.json are not asserted for this host.\n').encode()


def _write(output, files, report):
    output.mkdir(parents=True, exist_ok=False)
    for relative, raw in files.items():
        target = output.joinpath(*_safe_relative(relative).parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as stream:
            stream.write(raw)
    report['files'] = {name: sha256(raw) for name, raw in sorted(files.items())}
    with (output / 'receipt.json').open('x', encoding='utf-8') as stream:
        json.dump(report, stream, indent=2)
        stream.write('\n')
    return report


def collect(output: Path, python_base: Path):
    output, python_base = Path(output).resolve(), Path(python_base).resolve()
    if output.exists():
        raise FileExistsError('Python evidence output must be new')
    if output.is_relative_to(python_base):
        raise ValueError('Evidence must not modify the Python installation')
    data, catalog_raw = _catalog()
    archive_raw = _download(data['distribution'])
    verified = {}
    with zipfile.ZipFile(io.BytesIO(archive_raw)) as archive:
        members = archive.infolist()
        if len(members) > 200 or sum(item.file_size for item in members) > MAX_EXPANDED:
            raise ValueError('Oversized official Python archive')
        member_names = {item.filename.casefold(): item.filename for item in members}
        if len(member_names) != len(members):
            raise ValueError('Ambiguous case-folded Python archive members')
        for name, relative in data['native_files'].items():
            path = python_base.joinpath(*_safe_relative(relative).parts)
            if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(python_base):
                raise ValueError('Missing or unsafe installed Python file: ' + relative)
            member = member_names.get(name.casefold())
            if member is None:
                raise ValueError('Missing pinned native archive member: ' + name)
            expected = sha256(archive.read(member))
            if path.stat().st_size > MAX_DOWNLOAD or sha256(path.read_bytes()) != expected:
                raise ValueError('Installed Python differs from pinned official archive: ' + name)
            verified[name] = {'python_relative_path': relative, 'archive_member': member, 'sha256': expected}
        # The build already copies this exact text; record equivalence without duplicating it.
        license_sha = sha256(archive.read('LICENSE.txt'))
        installed_license = python_base / 'LICENSE.txt'
        if not installed_license.is_file() or sha256(installed_license.read_bytes()) != license_sha:
            raise ValueError('Installed Python LICENSE differs from the official archive')
    files, notices = _notices(data, windows=True)
    files.update({'README.txt': _summary(windows=True), 'sources.json': catalog_raw})
    report = {'schema': 1, 'mode': 'windows_pe_verified', 'python_version': data['python_version'],
              'architecture': data['architecture'], 'distribution': data['distribution'],
              'native_files': verified, 'official_python_license_sha256': license_sha,
              'notices': notices, 'source_catalog_sha256': sha256(catalog_raw),
              'redistribution_review': 'not_complete', 'global_release_approval': False}
    return _write(output, files, report)


def collect_notices(output: Path):
    output = Path(output).resolve()
    if output.exists():
        raise FileExistsError('Python evidence output must be new')
    if tuple(sys.version_info[:3]) != VERSION:
        raise ValueError('Notices-only evidence is pinned to Python 3.12.10')
    data, catalog_raw = _catalog()
    files, notices = _notices(data, windows=False)
    files.update({'README.txt': _summary(windows=False), 'sources.json': catalog_raw})
    report = {'schema': 1, 'mode': 'notices_only', 'python_version': data['python_version'],
              'native_verification': 'not_performed', 'notices': notices,
              'source_catalog_sha256': sha256(catalog_raw),
              'redistribution_review': 'not_complete', 'global_release_approval': False}
    return _write(output, files, report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--python-base', type=Path, default=Path(sys.base_prefix))
    parser.add_argument('--notices-only', action='store_true')
    args = parser.parse_args()
    receipt = collect_notices(args.output) if args.notices_only else collect(args.output, args.python_base)
    print(json.dumps({'mode': receipt['mode'], 'files': len(receipt['files']),
                      'native_files_verified': len(receipt.get('native_files', {})),
                      'redistribution_review': receipt['redistribution_review']}))


if __name__ == '__main__':
    main()

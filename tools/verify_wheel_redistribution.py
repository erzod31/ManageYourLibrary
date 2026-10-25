"""Pin reviewed Windows wheel bytes/notices without approving a full release.

No code is imported from the payload. Feature observations in the catalog were
made separately in a trusted build venv and are bound to exact binary hashes.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import urllib.parse
import urllib.request
from email.parser import BytesParser
from pathlib import Path, PurePosixPath

CATALOG = Path(__file__).with_name('wheel_redistribution_sources.json')
MAX_NOTICE = 128 * 1024


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def _relative(value):
    path = PurePosixPath(value)
    if (not path.parts or path.is_absolute() or '\\' in value
            or any(part in {'.', '..'} or ':' in part for part in path.parts)):
        raise ValueError('Unsafe wheel notice path')
    return path


def _catalog():
    raw = CATALOG.read_bytes()
    data = json.loads(raw)
    if data.get('schema') != 1 or not data.get('families') or not data.get('supplemental_notices'):
        raise ValueError('Incomplete wheel redistribution catalog')
    for family in data['families']:
        if not family.get('binaries') or not family.get('notices'):
            raise ValueError('Incomplete wheel family pin')
        for name, value in {**family['binaries'], **family['notices']}.items():
            _relative(name)
            if not re.fullmatch('[0-9a-f]{64}', value):
                raise ValueError('Invalid wheel file hash')
    for notice in data['supplemental_notices']:
        _relative(notice['path'])
        if (not re.fullmatch('[0-9a-f]{64}', notice['sha256'])
                or urllib.parse.urlsplit(notice['url']).scheme != 'https'
                or notice['encoding'] not in {'utf-8', 'base64'}):
            raise ValueError('Invalid supplemental notice pin')
    return data, _sha256(raw)


def _checked_file(directory, relative):
    path = directory.joinpath(*_relative(relative).parts)
    if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(directory.resolve()):
        raise ValueError('Missing or unsafe wheel file: ' + relative)
    return path


def _expected_receipt(data, catalog_hash):
    return {'schema': 1, 'catalog_sha256': catalog_hash,
            'notices': {item['path']: item['sha256'] for item in data['supplemental_notices']},
            'scope': 'exact_supplemental_notices_not_global_redistribution_approval'}


def collect_notices(output: Path):
    """Fetch only fixed, hash-verified notice texts into a NEW directory.

    Partial output is preserved on failure; it has no success receipt and is
    never silently resumed or overwritten. No upstream text is normalized.
    """
    data, catalog_hash = _catalog()
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise FileExistsError('Notice output must be a new directory')
    output.mkdir(parents=True, exist_ok=False)
    for item in data['supplemental_notices']:
        request = urllib.request.Request(item['url'], headers={'User-Agent': 'ManageYourLibrary-license-evidence/1'})
        with urllib.request.urlopen(request, timeout=30) as response:
            original = urllib.parse.urlsplit(item['url'])
            final = urllib.parse.urlsplit(response.geturl())
            if final.scheme != 'https' or final.netloc != original.netloc:
                raise ValueError('Unexpected notice download redirect')
            raw = response.read(MAX_NOTICE + 1)
        if len(raw) > MAX_NOTICE:
            raise ValueError('Oversized supplemental notice')
        decoded = base64.b64decode(raw, validate=True) if item['encoding'] == 'base64' else raw
        decoded.decode('utf-8')
        if b'\x00' in decoded or _sha256(decoded) != item['sha256']:
            raise ValueError('Supplemental notice differs from pinned source: ' + item['path'])
        path = output.joinpath(*_relative(item['path']).parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as out:
            out.write(decoded)
    receipt = _expected_receipt(data, catalog_hash)
    with (output / 'receipt.json').open('x', encoding='utf-8') as out:
        json.dump(receipt, out, indent=2)
        out.write('\n')
    return receipt


def verify_windows_payload(folder: Path):
    """Reject changed/unreviewed family binaries or incomplete notices."""
    data, catalog_hash = _catalog()
    folder = Path(folder).resolve()
    internal = folder / '_internal'
    if not internal.is_dir() or internal.is_symlink():
        raise ValueError('Missing Windows wheel payload directory')
    families = []
    for family in data['families']:
        metadata = BytesParser().parsebytes(_checked_file(internal, family['metadata']).read_bytes())
        if (metadata.get('Name', '').lower().replace('_', '-') != family['name']
                or metadata.get('Version') != family['version']):
            raise ValueError('Unreviewed wheel version: ' + family['name'])
        for relative, expected in {**family['binaries'], **family['notices']}.items():
            if _sha256(_checked_file(internal, relative).read_bytes()) != expected:
                raise ValueError('Unreviewed wheel binary/notice bytes: ' + relative)
        inventory = family['inventory']
        directory = internal.joinpath(*_relative(inventory['directory']).parts)
        actual = {p.relative_to(internal).as_posix() for p in directory.rglob('*')
                  if p.is_file() and p.suffix.lower() == inventory['suffix']}
        if actual != set(family['binaries']):
            raise ValueError('Unexpected wheel native family inventory: ' + family['name'])
        families.append({'name': family['name'], 'version': family['version'],
                         'binaries': family['binaries'], 'notices_checked': len(family['notices']),
                         'wheel': family['wheel'], 'observed_evidence': family.get('observed_evidence', {})})
    for path in internal.rglob('*'):
        if (path.is_file() and path.suffix.lower() in {'.dll', '.pyd'}
                and any(term in path.name.lower() for term in ('fribidi', 'imagequant', 'jbig'))):
            raise ValueError('Unreviewed optional copyleft native file: ' + path.name)
    supplement = internal.joinpath(*_relative(data['supplemental_directory']).parts)
    for item in data['supplemental_notices']:
        if _sha256(_checked_file(supplement, item['path']).read_bytes()) != item['sha256']:
            raise ValueError('Modified supplemental notice: ' + item['path'])
    expected_receipt = _expected_receipt(data, catalog_hash)
    receipt = json.loads(_checked_file(supplement, 'receipt.json').read_text(encoding='utf-8'))
    if receipt != expected_receipt:
        raise ValueError('Supplemental notice receipt differs from the catalog')
    acknowledgements = ' '.join(_checked_file(internal, 'THIRD_PARTY_NOTICES.md').read_text(encoding='utf-8').split())
    if any(' '.join(text.split()).casefold() not in acknowledgements.casefold()
           for text in data['required_acknowledgements']):
        raise ValueError('FreeType/IJG binary-distribution acknowledgements missing')
    return {'passed': True, 'profile': data['profile'], 'catalog_sha256': catalog_hash,
            'families': families, 'supplemental_notices': expected_receipt['notices'],
            'scope': data['scope'], 'global_redistribution_review': 'not_approved_by_this_check'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_mutually_exclusive_group(required=True)
    commands.add_argument('--collect-notices', type=Path)
    commands.add_argument('--payload', type=Path)
    parser.add_argument('--output', type=Path, help='New verification report, not collection destination')
    args = parser.parse_args()
    if args.collect_notices and args.output:
        parser.error('--output is only valid with --payload')
    result = collect_notices(args.collect_notices) if args.collect_notices else verify_windows_payload(args.payload)
    if args.payload and args.output:
        with args.output.open('x', encoding='utf-8') as out:
            json.dump(result, out, indent=2)
            out.write('\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()

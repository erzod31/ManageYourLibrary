"""Collect non-executing, hash-based OCR package/license evidence.

Historical MSYS2 recipes propose package versions, never prove their identity.
Only an exact DLL SHA-256 comparison establishes a matching package receipt.
No DLL, executable, PKGBUILD or downloaded script is loaded or executed.
7-Zip is used solely as a Zstandard decompressor. No tar extraction.
The output is audit evidence, not automatic redistribution authorization.
"""
import argparse
import concurrent.futures
import hashlib
import json
import re
import shutil
import subprocess
import tarfile
import urllib.error
import urllib.request
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
MAX_DOWNLOAD = 80 * 1024 * 1024
MAX_TAR = 256 * 1024 * 1024


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def json_digest(path):
    value = json.loads(path.read_text(encoding='utf-8'))
    return digest(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('utf-8'))


def fetch(url):
    request = urllib.request.Request(url, headers={'User-Agent': 'ManageYourLibrary-license-review'})
    with urllib.request.urlopen(request, timeout=45) as response:
        raw = response.read(MAX_DOWNLOAD + 1)
    if len(raw) > MAX_DOWNLOAD:
        raise ValueError('Audit download exceeds size limit')
    return raw


def simple_variable(recipe, name):
    """Read literal assignments only; never source or eval a package recipe."""
    found = re.search(r'^' + re.escape(name) + r'=([^\n]*)', recipe, re.MULTILINE)
    if not found:
        raise ValueError('Missing recipe literal: ' + name)
    value = found[1].strip().strip('\'"')
    if not re.fullmatch(r'[A-Za-z0-9.+_-]*', value):
        raise ValueError('Not a recipe literal: ' + name)
    return value


def read_package(raw, decoder):
    # The trusted decoder is an already installed build tool, not a download.
    # TemporaryFile bounds RAM use and is deleted after parsing; the decoder
    # output is inspected for size before tarfile sees it.
    import tempfile
    with tempfile.TemporaryFile() as unpacked:
        subprocess.run([decoder, 'x', '-tzstd', '-si', '-so'], input=raw,
                       stdout=unpacked, stderr=subprocess.PIPE, timeout=60, check=True)
        if unpacked.tell() > MAX_TAR:
            raise ValueError('Audit package exceeds tar size limit')
        unpacked.seek(0)
        result = {}
        with tarfile.open(fileobj=unpacked, mode='r:') as stream:
            for member in stream:
                path = PurePosixPath(member.name)
                wanted = member.name in ('.PKGINFO', '.BUILDINFO') or (
                    '/share/licenses/' in member.name or
                    (str(path.parent) == 'mingw64/bin' and path.suffix.lower() in ('.dll', '.exe')))
                if not wanted or not member.isfile():
                    continue
                if path.is_absolute() or '..' in path.parts or member.size > 40 * 1024 * 1024:
                    raise ValueError('Unsafe audit member')
                result[member.name] = stream.extractfile(member).read()
        return result


def package_fields(raw):
    allowed = {'pkgname', 'pkgbase', 'pkgver', 'license', 'url', 'builddate',
               'pkgbuild_sha256sum', 'depend', 'makedepend'}
    result = {}
    for line in raw.decode('utf-8', errors='replace').splitlines():
        key, separator, value = line.partition(' = ')
        if separator and key in allowed:
            result.setdefault(key, []).append(value)
    return result


def collect_component(component, commit, inventory, output, decoder):
    key = component['id']
    directory = output / key
    directory.mkdir()
    recipe_url = f'https://raw.githubusercontent.com/msys2/MINGW-packages/{commit}/mingw-w64-{key}/PKGBUILD'
    recipe_raw = fetch(recipe_url)
    (directory / 'PKGBUILD').write_bytes(recipe_raw)
    recipe = recipe_raw.decode('utf-8')
    version = component.get('version') or simple_variable(recipe, 'pkgver')
    release = simple_variable(recipe, 'pkgrel')
    package = component.get('package', key)
    filename = f'mingw-w64-x86_64-{package}-{version}-{release}-any.pkg.tar.zst'
    url = 'https://repo.msys2.org/mingw/mingw64/' + filename
    result = {'component': key, 'recipe': {'url': recipe_url, 'sha256': digest(recipe_raw)},
              'candidate_package': {'url': url, 'version': version + '-' + release},
              'matching_files': [], 'nonmatching_files': [], 'notices': [],
              'source_obligations_fulfilled': False, 'redistribution_cleared': False}
    # Inspect a project's versioned license independently of package metadata.
    # Do not present a GitHub HTML wrapper as the actual permission text.
    license_url = component['upstream']
    if license_url.startswith('https://github.com/') and '/blob/' in license_url:
        license_url = license_url.replace('https://github.com/', 'https://raw.githubusercontent.com/', 1).replace('/blob/', '/', 1)
    elif '/-/blob/' in license_url:
        license_url = license_url.replace('/-/blob/', '/-/raw/', 1)
    try:
        license_raw = fetch(license_url)
        target = directory / 'upstream-license-reference'
        target.write_bytes(license_raw)
        result['upstream_reference'] = {'url': license_url, 'sha256': digest(license_raw),
                                        'bytes': len(license_raw), 'retrieval': 'downloaded',
                                        'text_is_html': b'<html' in license_raw[:2000].lower() or b'<!doctype html' in license_raw[:2000].lower()}
    except (urllib.error.URLError, TimeoutError) as exc:
        result['upstream_reference'] = {'url': license_url, 'retrieval': type(exc).__name__}
    try:
        archive = fetch(url)
    except urllib.error.HTTPError as exc:
        result['candidate_package']['retrieval'] = 'http_' + str(exc.code)
        return result
    result['candidate_package'].update({'retrieval': 'downloaded', 'sha256': digest(archive),
                                         'bytes': len(archive), 'signature_verified': False})
    (directory / filename).write_bytes(archive)
    members = read_package(archive, decoder)
    result['package_metadata'] = package_fields(members.get('.PKGINFO', b''))
    result['build_metadata'] = package_fields(members.get('.BUILDINFO', b''))
    for name in component['files']:
        raw = members.get('mingw64/bin/' + name)
        actual = digest(raw) if raw is not None else None
        row = {'file': name, 'sha256': actual, 'expected_sha256': inventory[name]['sha256']}
        result['matching_files' if actual == inventory[name]['sha256'] else 'nonmatching_files'].append(row)
    for name, raw in members.items():
        if '/share/licenses/' not in name:
            continue
        target = directory / 'notices' / PurePosixPath(name).relative_to('mingw64/share/licenses')
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        result['notices'].append({'package_path': name, 'sha256': digest(raw), 'bytes': len(raw)})
    return result


def collect(destination, decoder):
    catalog = json.loads((ROOT / 'tools/ocr_license_catalog.json').read_text(encoding='utf-8'))
    provenance = ROOT / 'docs/validation_data_2026-10-24/windows-ocr-provenance.json'
    inventory = {row['file']: row for row in json.loads(provenance.read_text())['files']}
    listed = [name for component in catalog['components'] for name in component['files']]
    if len(listed) != len(set(listed)) or set(listed) != set(inventory):
        raise ValueError('License catalog must cover each audited binary exactly once')
    destination = destination.resolve()
    destination.mkdir(parents=True, exist_ok=False)
    decoder = shutil.which(decoder)
    if not decoder:
        raise FileNotFoundError('Install/select an existing 7-Zip compatible decoder')
    def one(component):
        try:
            result = collect_component(component, catalog['msys2_recipe_commit'], inventory, destination, decoder)
        except (OSError, ValueError, tarfile.TarError, subprocess.SubprocessError) as exc:
            # Preserve successful receipts even if a historical archive vanished.
            result = {'component': component['id'], 'error': type(exc).__name__ + ': ' + str(exc),
                      'redistribution_cleared': False}
        print(result['component'], len(result.get('matching_files', [])),
              result.get('candidate_package', {}).get('retrieval', result.get('error')), flush=True)
        return result
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        components = list(pool.map(one, catalog['components']))
    report = {'review_date': catalog['review_date'], 'scope': catalog['scope'],
              'json_fingerprint_encoding': 'canonical-json-sorted-ascii-compact',
              'provenance_sha256': json_digest(provenance),
              'catalog_sha256': json_digest(ROOT / 'tools/ocr_license_catalog.json'),
              'binary_count': len(inventory), 'dll_count': sum(n.endswith('.dll') for n in inventory),
              'component_count': len(components),
              'exact_package_matches': sum(len(c.get('matching_files', [])) for c in components),
              'components': components, 'redistribution_review': 'not_complete',
              'downloaded_binaries_executed': False,
              'limitations': ['Historical recipes are candidate evidence, not exact build receipts.',
                             'TLS download and SHA-256 matching, not detached PGP signature verification.',
                             'Source archives, patches and complete redistribution obligations are not yet fulfilled.']}
    (destination / 'package-evidence.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: report[k] for k in ('binary_count', 'component_count', 'exact_package_matches', 'redistribution_review')}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--decoder', default='7z')
    args = parser.parse_args()
    collect(args.output, args.decoder)

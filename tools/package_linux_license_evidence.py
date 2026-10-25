"""Package bounded Ubuntu source evidence separately from the application.

This verifies the collector's recorded bytes and relationships. It does not
authenticate the original CI host, establish library replacement rights, or
approve LGPL/GPL or patent compliance. It never runs APT or payload code.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import tarfile
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.collect_linux_license_evidence import (
    PACKAGE,
    SHA256,
    SOURCE_PACKAGE,
    VERSION,
    relative_name,
    validate_source_uris,
)

REPORT = 'linux-license-evidence.json'
SCOPE = 'copyright_and_exact_source_delivery_evidence_not_global_license_approval'
MAX_REPORT = 16 * 1024 * 1024
MAX_FILES = 20000
INDEX_NAME = re.compile(r'(?:archive|security)\.ubuntu\.com_ubuntu_dists_jammy(?:-(?:updates|security|backports))?_'
                        r'(?:InRelease|(?:main|restricted|universe|multiverse)_source_Sources(?:\.(?:lz4|xz|gz|bz2))?)\Z')


def sha256(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def _digest(value):
    if not isinstance(value, str) or not SHA256.fullmatch(value):
        raise ValueError('Invalid evidence SHA-256')
    return value


def _files(root):
    files = {}
    for path in root.rglob('*'):
        if path.is_symlink():
            raise ValueError('Evidence must contain ordinary files, never symlinks')
        if path.is_dir():
            continue
        if not path.is_file():
            raise ValueError('Evidence contains a non-regular file')
        name = path.relative_to(root).as_posix()
        relative_name(name)
        files[name] = path
        if len(files) > MAX_FILES:
            raise ValueError('Oversized evidence inventory')
    return files


def _validate(evidence):
    files = _files(evidence)
    if REPORT not in files or files[REPORT].stat().st_size > MAX_REPORT:
        raise ValueError('Missing or oversized Linux evidence report')
    raw = files[REPORT].read_bytes()
    report = json.loads(raw)
    if report.get('schema') != 1 or report.get('platform') != 'Ubuntu 22.04' or report.get('scope') != SCOPE:
        raise ValueError('Unsupported Linux evidence scope')
    authentication = report.get('apt_authentication', {})
    if (authentication.get('check_valid_until') is not True
            or authentication.get('allow_insecure') is not False
            or authentication.get('allow_unauthenticated') is not False):
        raise ValueError('Missing strict Ubuntu repository authentication evidence')
    _digest(authentication.get('keyring_sha256'))
    inventory = report.get('evidence_files_sha256')
    if not isinstance(inventory, dict) or not inventory or set(inventory) != set(files) - {REPORT}:
        raise ValueError('Evidence inventory differs from complete directory contents')
    for name, expected in inventory.items():
        relative_name(name)
        if sha256(files[name]) != _digest(expected):
            raise ValueError('Evidence file SHA-256 mismatch: ' + name)
    packages = report.get('binary_packages')
    origins = report.get('copied_binary_origins')
    sources = report.get('source_archives')
    if not isinstance(packages, dict) or not packages or not isinstance(origins, list) or not origins or not isinstance(sources, list):
        raise ValueError('Missing package, source, or binary origin evidence')
    expected_files, expected_families = set(), set()
    for name, package in packages.items():
        if not PACKAGE.fullmatch(name) or package.get('binary_package') != name:
            raise ValueError('Invalid binary package evidence identity')
        if (not VERSION.fullmatch(package.get('binary_version', ''))
                or not SOURCE_PACKAGE.fullmatch(package.get('source_package', ''))
                or not VERSION.fullmatch(package.get('source_version', ''))):
            raise ValueError('Invalid exact source package identity')
        expected_families.add((package['source_package'], package['source_version']))
        copyright_name = 'copyright/' + urllib.parse.quote(name, safe='.+-~') + '/copyright'
        if inventory.get(copyright_name) != _digest(package.get('copyright_sha256')):
            raise ValueError('Package copyright absent or mismatched')
        expected_files.add(copyright_name)
        copyright_text = files[copyright_name].read_text(encoding='utf-8', errors='replace')
        for common in set(re.findall(r'/usr/share/common-licenses/([A-Za-z0-9.+-]+)', copyright_text)):
            common_name = 'common-licenses/' + common.rstrip('.')
            if common_name not in inventory:
                raise ValueError('Referenced common license is missing')
            expected_files.add(common_name)
    actual_families = set()
    for source in sources:
        family = (source.get('package'), source.get('version'))
        if family not in expected_families or family in actual_families:
            raise ValueError('Duplicate or foreign exact source family')
        actual_families.add(family)
        directory = 'sources/' + family[0] + '--' + urllib.parse.quote(family[1], safe='.+-~')
        if source.get('evidence_directory') != directory:
            raise ValueError('Unexpected source evidence directory')
        records = source.get('files', {})
        if (not isinstance(records, dict) or not records
                or not any(name.endswith('.dsc') for name in records)
                or not any('.tar.' in name or name.endswith('.diff.gz') for name in records)):
            raise ValueError('Incomplete corresponding source archive set')
        for filename, record in records.items():
            if relative_name(filename).name != filename:
                raise ValueError('Unsafe source archive filename')
            name = directory + '/' + filename
            if inventory.get(name) != _digest(record.get('sha256')) or name not in files:
                raise ValueError('Source archive hash missing or mismatched')
            if type(record.get('bytes')) is not int or record['bytes'] <= 0 or files[name].stat().st_size != record['bytes']:
                raise ValueError('Source archive size mismatch')
            expected_files.add(name)
        uris = source.get('uris', {})
        if set(uris) != set(records):
            raise ValueError('Incomplete source download URI provenance')
        preview = '\n'.join("'" + uris[name] + "' " + name + ' ' + str(records[name]['bytes']) for name in records)
        validate_source_uris(preview, records)
    if actual_families != expected_families:
        raise ValueError('Exact corresponding source family is missing')
    index_names = {name for name in inventory if name.startswith('authenticated-indexes/')}
    if (not any(name.endswith('InRelease') for name in index_names)
            or not any(re.search(r'_Sources(?:\.[a-z0-9]+)?$', name) for name in index_names)
            or any(len(relative_name(name).parts) != 2 or not INDEX_NAME.fullmatch(relative_name(name).name)
                   for name in index_names)):
        raise ValueError('Authenticated Ubuntu release/source indexes are incomplete')
    expected_files.update(index_names)
    if expected_files != set(inventory):
        raise ValueError('Foreign file in Linux evidence inventory')
    seen, used_packages = set(), set()
    for origin in origins:
        name = origin.get('destination')
        relative_name(name)
        if name in seen:
            raise ValueError('Duplicate copied binary destination')
        seen.add(name)
        _digest(origin.get('original_sha256'))
        package = packages.get(origin.get('binary_package'))
        if package is None or any(origin.get(key) != package.get(key) for key in
                                  ('binary_package', 'binary_version', 'source_package', 'source_version', 'architecture')):
            raise ValueError('Binary origin disagrees with exact package identity')
        used_packages.add(origin['binary_package'])
    if used_packages != set(packages):
        raise ValueError('Foreign package not linked to any copied binary')
    return report, files, {**inventory, REPORT: hashlib.sha256(raw).hexdigest()}


class _HashingReader:
    def __init__(self, stream):
        self.stream = stream
        self.hasher = hashlib.sha256()

    def read(self, size=-1):
        data = self.stream.read(size)
        self.hasher.update(data)
        return data


def prepare(payload: Path, evidence: Path, release: Path, label: str) -> dict:
    """Create a NEW source asset and small application notices, before app tar."""
    payload, evidence, release = Path(payload), Path(evidence), Path(release)
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,119}', label):
        raise ValueError('Unsafe release evidence label')
    if evidence.is_symlink() or not evidence.is_dir():
        raise ValueError('Linux evidence must be an ordinary directory')
    internal = payload / '_internal'
    if not internal.is_dir() or internal.is_symlink() or payload.is_symlink():
        raise ValueError('Missing ordinary Linux application payload')
    target = internal / 'licenses' / 'linux-system'
    archive = release / (label + '-license-sources.tar')
    if (evidence.resolve().is_relative_to(payload.resolve())
            or payload.resolve().is_relative_to(evidence.resolve())
            or archive.resolve().is_relative_to(payload.resolve())
            or archive.resolve().is_relative_to(evidence.resolve())):
        raise ValueError('Application, source evidence, and source archive must remain separate')
    if (target.exists() or target.is_symlink() or archive.exists() or archive.is_symlink()
            or release.is_symlink() or (internal / 'licenses').is_symlink()):
        raise FileExistsError('Existing source asset or application license evidence is never overwritten')
    report, files, hashes = _validate(evidence)
    binaries = {}
    for origin in report['copied_binary_origins']:
        name = origin['destination']
        path = internal.joinpath(*relative_name(name).parts)
        if not path.is_file() or not path.resolve().is_relative_to(internal.resolve()):
            raise ValueError('Copied Ubuntu binary missing or outside application: ' + name)
        final = sha256(path)
        binaries[name] = {'original_sha256': origin['original_sha256'], 'final_sha256': final,
                          'bytes_changed_after_collection': final != origin['original_sha256'],
                          'binary_package': origin['binary_package'], 'binary_version': origin['binary_version'],
                          'source_package': origin['source_package'], 'source_version': origin['source_version'],
                          'review': 'changed bytes may include patchelf; investigate modifications and library replacement rights separately'}
    release.mkdir(parents=True, exist_ok=True)
    # tarballs remain compressed individually; no redundant recompression.
    # Hash bytes WHILE archiving to reject mutations after initial validation.
    with archive.open('xb') as output, tarfile.open(fileobj=output, mode='w') as tar:
        for name, path in sorted(files.items()):
            if path.is_symlink():
                raise ValueError('Evidence changed to a symlink during packaging')
            info = tarfile.TarInfo(name)
            info.size = path.stat().st_size
            info.mode, info.mtime, info.uid, info.gid = 0o644, 0, 0, 0
            with path.open('rb') as stream:
                reader = _HashingReader(stream)
                tar.addfile(info, reader)
                if reader.hasher.hexdigest() != hashes[name] or stream.read(1):
                    raise ValueError('Evidence changed during source archive creation')
    receipt = {'schema': 1, 'archive': archive.name, 'name': archive.name, 'sha256': sha256(archive),
               'evidence_report_sha256': hashes[REPORT], 'scope': 'verified_evidence_delivery_not_global_license_approval',
               'source_asset_required_with_release': True, 'copied_binary_hashes': binaries,
               'remaining_review': ['authenticate original CI provenance; inspect any changed library bytes',
                                    'validate dynamic library replacement rights and package-specific LGPL/GPL conditions',
                                    'review wheel/manual-build libraries and patent conditions separately']}
    target.mkdir(parents=True, exist_ok=False)
    copied = {}
    for name, path in sorted(files.items()):
        if not name.startswith(('copyright/', 'common-licenses/')):
            continue
        destination = target.joinpath(*relative_name(name).parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != hashes[name]:
            raise ValueError('Application notice changed during copying')
        with destination.open('xb') as stream:
            stream.write(data)
        copied[name] = hashes[name]
    receipt['application_notices_sha256'] = copied
    with (target / 'source-asset.json').open('x', encoding='utf-8') as stream:
        json.dump(receipt, stream, indent=2)
        stream.write('\n')
    return receipt

"""Collect Ubuntu-library copyright and exact source evidence, never install.

Run on the ORIGINAL Ubuntu 22.04 build host, after PyInstaller analysis. Input
is its literal COLLECT-00.toc (preferred), Analysis-00.toc, or JSON exported
from Analysis.binaries: [{"destination": ..., "source": ...}] or its triples.
Original paths are queried with dpkg; frozen SONAMEs are not package proof.

Only apt-get update in isolated state and apt-get source --download-only are
used. No system repository is changed, no package is installed, and downloaded
source is neither extracted nor executed. This is not LGPL/GPL legal approval.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
from pathlib import Path, PurePosixPath

PACKAGE = re.compile(r'[a-z0-9][a-z0-9+.-]*(?::[a-z0-9]+)?\Z')
SOURCE_PACKAGE = re.compile(r'[a-z0-9][a-z0-9+.-]*\Z')
VERSION = re.compile(r'[0-9][A-Za-z0-9.+:~\-]*\Z')
SHA256 = re.compile(r'[0-9a-f]{64}\Z')
SUITES = ('jammy', 'jammy-updates', 'jammy-security', 'jammy-backports')
KEYRING = Path('/usr/share/keyrings/ubuntu-archive-keyring.gpg')
MAX_TOC_BYTES = 2 * 1024 * 1024
MAX_TOC_NODES = 100000
MAX_TOC_DEPTH = 64
MAX_SOURCE_SET = 1024 * 1024 * 1024


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def relative_name(value):
    path = PurePosixPath(value)
    if (not path.parts or path.is_absolute() or '\\' in value
            or any(ord(c) < 32 or ord(c) == 127 for c in value)
            or any(p in {'.', '..'} or ':' in p for p in path.parts)):
        raise ValueError('Unsafe evidence destination name')
    return path


def parse_toc(data):
    if isinstance(data, dict):
        data = data.get('binaries')
    if not isinstance(data, list) or not data or len(data) > 10000:
        raise ValueError('Missing or oversized binary-source inventory')
    entries = {}
    for item in data:
        if isinstance(item, (list, tuple)) and len(item) == 3:
            destination, source, kind = item
            if kind not in {'BINARY', 'EXTENSION'}:
                continue
        elif isinstance(item, dict):
            destination, source = item.get('destination'), item.get('source')
        else:
            raise ValueError('Expected JSON binary-source entries, not executable TOC code')
        if not isinstance(destination, str) or not isinstance(source, str):
            raise TypeError('Invalid binary-source inventory entry')
        relative_name(destination)
        if (not PurePosixPath(source).is_absolute() or any(c in source for c in '*?[]')
                or any(ord(c) < 32 or ord(c) == 127 for c in source)):
            raise ValueError('Binary origin must be a literal absolute Linux path')
        if destination in entries and entries[destination] != source:
            raise ValueError('Conflicting origins for the same payload file')
        entries[destination] = source
    if not entries:
        raise ValueError('No binary-source entries')
    return [{'destination': name, 'source': value} for name, value in sorted(entries.items())]


def parse_pyinstaller_toc(text):
    """Read PyInstaller literal TOC data without importing or executing it."""
    if len(text.encode('utf-8')) > MAX_TOC_BYTES:
        raise ValueError('Oversized PyInstaller TOC')
    try:
        tree = ast.parse(text, mode='eval')
    except (SyntaxError, ValueError, RecursionError) as error:
        raise ValueError('Invalid PyInstaller literal TOC') from error
    pending, count = [(tree, 0)], 0
    while pending:
        node, depth = pending.pop()
        count += 1
        if count > MAX_TOC_NODES or depth > MAX_TOC_DEPTH:
            raise ValueError('Oversized or deeply nested PyInstaller TOC')
        pending.extend((child, depth + 1) for child in ast.iter_child_nodes(node))
    try:
        data = ast.literal_eval(tree)
    except (ValueError, TypeError, RecursionError) as error:
        raise ValueError('Only literal PyInstaller TOC data is permitted') from error
    pending, entries = [data], []
    while pending:
        item = pending.pop()
        if not isinstance(item, (list, tuple)):
            continue
        if len(item) == 3 and isinstance(item[2], str) and item[2] in {'BINARY', 'EXTENSION'}:
            entries.append(item)
        else:
            pending.extend(item)
    return parse_toc(entries)


def parse_deb822(text):
    paragraphs, current, field = [], {}, None
    for line in text.splitlines() + ['']:
        if not line.strip():
            if current:
                paragraphs.append(current)
            current, field = {}, None
        elif line[:1].isspace():
            if field is None:
                raise ValueError('Invalid Debian control continuation')
            current[field] += '\n' + line.lstrip()
        else:
            key, separator, value = line.partition(':')
            if not separator or key in current:
                raise ValueError('Invalid or duplicate Debian control field')
            field = key
            current[key] = value.strip()
    return paragraphs


def source_record(text, package, version):
    if not SOURCE_PACKAGE.fullmatch(package) or not VERSION.fullmatch(version):
        raise ValueError('Invalid exact source-package identity')
    matches = [p for p in parse_deb822(text) if p.get('Package') == package and p.get('Version') == version]
    if not matches:
        raise ValueError('Exact source version absent from authenticated Ubuntu indexes: '
                         + package + '=' + version + '; retain a signed build-time index/snapshot, do not substitute a newer source')
    records = []
    for paragraph in matches:
        files = {}
        for line in paragraph.get('Checksums-Sha256', '').splitlines():
            if not line.strip():
                continue
            parts = line.split()
            if len(parts) != 3 or not SHA256.fullmatch(parts[0]) or not parts[1].isdigit():
                raise ValueError('Missing strong source-file hashes')
            checksum, size, filename = parts
            if PurePosixPath(filename).name != filename or filename.startswith('.') or '\\' in filename:
                raise ValueError('Unsafe source archive filename')
            relative_name(filename)
            if filename in files or int(size) <= 0:
                raise ValueError('Duplicate or empty source archive')
            files[filename] = {'sha256': checksum, 'bytes': int(size)}
        if not files or not any(name.endswith('.dsc') for name in files) or not any('.tar.' in name or name.endswith('.diff.gz') for name in files):
            raise ValueError('Incomplete source archive set')
        if sum(f['bytes'] for f in files.values()) > MAX_SOURCE_SET:
            raise ValueError('Source archive set exceeds evidence size limit')
        records.append({'package': package, 'version': version,
                        'directory': paragraph.get('Directory', ''), 'files': files})
    if any(record != records[0] for record in records[1:]):
        raise ValueError('Conflicting authenticated records for the exact source version')
    return records[0]


def validate_source_uris(text, expected):
    uris = {}
    for line in text.splitlines():
        if not line.startswith("'"):
            continue
        fields = shlex.split(line)
        if len(fields) < 3:
            raise ValueError('Invalid apt source URI record')
        url, filename, size = fields[:3]
        parsed = urllib.parse.urlsplit(url)
        host = parsed.hostname or ''
        allowed = host in {'archive.ubuntu.com', 'security.ubuntu.com', 'ports.ubuntu.com'} or host.endswith('.archive.ubuntu.com')
        if (parsed.scheme != 'https' or not allowed or parsed.username or parsed.password
                or parsed.port not in {None, 443} or parsed.fragment
                or '..' in PurePosixPath(urllib.parse.unquote(parsed.path)).parts):
            raise ValueError('Source URI is not an official HTTPS Ubuntu archive')
        if filename not in expected or not size.isdigit() or int(size) != expected[filename]['bytes']:
            raise ValueError('Source URI differs from authenticated file record')
        if filename in uris:
            raise ValueError('Duplicate source URI')
        uris[filename] = url
    if set(uris) != set(expected):
        raise ValueError('Source URI set is incomplete')
    return uris


def parse_dpkg_fields(text):
    fields = text.rstrip('\n').split('\t')
    if len(fields) != 6:
        raise ValueError('Invalid dpkg provenance response')
    binary, version, source, source_version, architecture, status = fields
    if (not PACKAGE.fullmatch(binary) or not VERSION.fullmatch(version)
            or not SOURCE_PACKAGE.fullmatch(source) or not VERSION.fullmatch(source_version)
            or not re.fullmatch('[a-z0-9]+', architecture) or status != 'installed'):
        raise ValueError('Incomplete or non-installed dpkg package identity')
    return {'binary_package': binary, 'binary_version': version, 'source_package': source,
            'source_version': source_version, 'architecture': architecture}


def apt_configuration(work):
    # APT_CONFIG is read BEFORE normal config fragments. Disable those here,
    # not with late -o flags, so host post-update hooks/auth config cannot run.
    work = Path(work)
    root = work.as_posix()
    if any(c in root for c in '"\n\r\\'):
        raise ValueError('Unsafe isolated apt directory')
    config = f'''Dir::Etc::parts "-";
Dir::Etc::main "-";
Dir::Etc::sourcelist "{root}/sources.list";
Dir::Etc::sourceparts "-";
Dir::Etc::trustedparts "-";
Dir::Etc::trusted "{KEYRING.as_posix()}";
Dir::Etc::netrc "-";
Dir::Etc::netrcparts "-";
Dir::State "{root}/state";
Dir::State::lists "{root}/state/lists";
Dir::State::status "/var/lib/dpkg/status";
Dir::Cache "{root}/cache";
Dir::Cache::archives "{root}/cache/archives";
Dir::Log "{root}/logs";
Acquire::AllowInsecureRepositories "false";
Acquire::AllowDowngradeToInsecureRepositories "false";
Acquire::AllowWeakRepositories "false";
Acquire::Check-Valid-Until "true";
APT::Get::AllowUnauthenticated "false";
APT::Get::List-Cleanup "false";
'''
    sources = ''.join('deb-src [signed-by=' + KEYRING.as_posix() + '] https://'
                      + ('security.ubuntu.com' if suite == 'jammy-security' else 'archive.ubuntu.com')
                      + '/ubuntu ' + suite + ' main restricted universe multiverse\n' for suite in SUITES)
    return config, sources


def run(command, *, env, cwd=None):
    result = subprocess.run(command, env=env, cwd=cwd, capture_output=True, text=True, timeout=900, check=False)
    if result.returncode:
        raise RuntimeError('Evidence command failed: ' + Path(command[0]).name + '; no source-version substitution is allowed')
    return result.stdout


def package_owner(path, *, env):
    owners = set()
    for candidate in dict.fromkeys((str(path), str(path.resolve()))):
        result = subprocess.run(['dpkg-query', '--admindir=/var/lib/dpkg', '-S', candidate],
                                env=env, capture_output=True, text=True, timeout=30, check=False)
        if result.returncode not in {0, 1}:
            raise RuntimeError('dpkg ownership query failed')
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                owner, separator, _ = line.partition(': ')
                if not separator or not PACKAGE.fullmatch(owner):
                    raise ValueError('Ambiguous dpkg/diversion ownership requires manual review')
                owners.add(owner)
    if len(owners) > 1:
        raise ValueError('Multiple dpkg owners require manual review')
    if not owners:
        return None
    owner = owners.pop()
    format_string = '${binary:Package}\t${Version}\t${source:Package}\t${source:Version}\t${Architecture}\t${db:Status-Status}\n'
    return parse_dpkg_fields(run(['dpkg-query', '--admindir=/var/lib/dpkg', '-W', '-f=' + format_string, owner], env=env))


def collect(toc: Path, output: Path, *, pyinstaller_toc=False):
    if sys.platform != 'linux':
        raise RuntimeError('Linux evidence collection must run on the original Ubuntu build host, never on Windows')
    host = dict(line.split('=', 1) for line in Path('/etc/os-release').read_text().splitlines()
                if '=' in line and not line.startswith('#'))
    if host.get('ID', '').strip('"') != 'ubuntu' or host.get('VERSION_ID', '').strip('"') != '22.04':
        raise RuntimeError('This evidence recipe is restricted to Ubuntu 22.04')
    for name in ('apt-get', 'apt-cache', 'dpkg-query'):
        if not shutil.which(name):
            raise RuntimeError('Required build-host evidence tool missing: ' + name)
    if not KEYRING.is_file():
        raise RuntimeError('Ubuntu archive keyring is missing')
    toc = Path(toc)
    if toc.stat().st_size > MAX_TOC_BYTES:
        raise ValueError('Oversized binary-source inventory')
    raw_toc = toc.read_text(encoding='utf-8')
    entries = parse_pyinstaller_toc(raw_toc) if pyinstaller_toc else parse_toc(json.loads(raw_toc))
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise FileExistsError('Evidence output must be NEW; previous evidence is never overwritten')
    output.mkdir(parents=True, exist_ok=False)
    env = dict(os.environ, LC_ALL='C', LANGUAGE='C')
    for name in ('DPKG_ROOT', 'DPKG_ADMINDIR', 'APT_CONFIG'):
        env.pop(name, None)
    packages, binaries, unowned = {}, [], []
    for entry in entries:
        original = Path(entry['source'])
        if not original.is_file():
            raise ValueError('Original analysis binary disappeared: ' + entry['destination'])
        checksum = sha256(original)
        owner = package_owner(original, env=env)
        if sha256(original) != checksum:
            raise ValueError('Original binary changed during provenance lookup')
        record = {'destination': entry['destination'], 'original_sha256': checksum}
        if owner is None:
            unowned.append({**record, 'status': 'not_dpkg_owned_requires_separate_wheel_or_source_build_review'})
            continue
        binaries.append({**record, **owner})
        packages[owner['binary_package']] = owner
    if not packages:
        raise ValueError('No Ubuntu-owned copied binaries; no source evidence can be claimed')
    for name, package in sorted(packages.items()):
        copyright_path = Path('/usr/share/doc') / name.split(':')[0] / 'copyright'
        if not copyright_path.is_file():
            raise ValueError('Installed package copyright is missing: ' + name)
        target = output / 'copyright' / urllib.parse.quote(name, safe='.+-~')
        target.mkdir(parents=True)
        shutil.copy2(copyright_path, target / 'copyright')
        package['copyright_sha256'] = sha256(target / 'copyright')
        text = copyright_path.read_text(encoding='utf-8', errors='replace')
        for common in set(re.findall(r'/usr/share/common-licenses/([A-Za-z0-9.+-]+)', text)):
            common = common.rstrip('.')
            path = Path('/usr/share/common-licenses') / common
            if not path.is_file():
                raise ValueError('Referenced common license is missing: ' + common)
            directory = output / 'common-licenses'
            directory.mkdir(exist_ok=True)
            destination = directory / common
            if not destination.exists():
                shutil.copy2(path, destination)
    source_families = sorted({(p['source_package'], p['source_version']) for p in packages.values()})
    sources = []
    with tempfile.TemporaryDirectory(prefix='myl_apt_source_evidence_') as directory:
        work = Path(directory)
        for relative in ('state/lists/partial', 'cache/archives/partial', 'logs'):
            (work / relative).mkdir(parents=True)
        config, source_list = apt_configuration(work)
        (work / 'apt.conf').write_text(config, encoding='utf-8')
        (work / 'sources.list').write_text(source_list, encoding='utf-8')
        env['APT_CONFIG'] = str(work / 'apt.conf')
        run(['apt-get', '--error-on=any', 'update'], env=env)
        releases = list((work / 'state/lists').glob('*InRelease'))
        if not releases:
            raise ValueError('No freshly authenticated Ubuntu release records')
        signed = output / 'authenticated-indexes'
        signed.mkdir()
        for release in releases:
            raw = release.read_text(encoding='utf-8')
            if '\nOrigin: Ubuntu\n' not in raw or '\nCodename: jammy\n' not in raw:
                raise ValueError('Unexpected repository identity')
            shutil.copy2(release, signed / release.name)
        # Retain the actual authenticated Sources indexes too. APT may store
        # them as lz4; retaining those bytes and InRelease permits independent
        # decompression and comparison with the signed uncompressed Sources
        # checksum. No package index supplied by the host is reused.
        indexes = [p for p in (work / 'state/lists').iterdir()
                   if p.is_file() and re.search(r'_Sources(?:\.[a-z0-9]+)?$', p.name)]
        if not indexes:
            raise ValueError('Authenticated source-package indexes are missing')
        for index in indexes:
            shutil.copy2(index, signed / index.name)
        for package, version in source_families:
            record = source_record(run(['apt-cache', '--only-source', 'showsrc', package], env=env), package, version)
            target = output / 'sources' / (package + '--' + urllib.parse.quote(version, safe='.+-~'))
            target.mkdir(parents=True)
            selector = package + '=' + version
            preview = run(['apt-get', '--print-uris', '--download-only', '--only-source', 'source', selector], env=env, cwd=target)
            record['uris'] = validate_source_uris(preview, record['files'])
            required_bytes = sum(v['bytes'] for v in record['files'].values())
            if shutil.disk_usage(target).free < required_bytes * 2 + 50 * 1024 * 1024:
                raise RuntimeError('Insufficient room for complete corresponding-source evidence')
            run(['apt-get', '--download-only', '--only-source', 'source', selector], env=env, cwd=target)
            actual = {p.name for p in target.iterdir() if p.is_file()}
            if actual != set(record['files']):
                raise ValueError('Incomplete or unexpected downloaded source set')
            for filename, expected in record['files'].items():
                path = target / filename
                if path.is_symlink() or path.stat().st_size != expected['bytes'] or sha256(path) != expected['sha256']:
                    raise ValueError('Downloaded source differs from authenticated SHA-256 record')
            record['evidence_directory'] = target.relative_to(output).as_posix()
            sources.append(record)
    report = {'schema': 1, 'platform': 'Ubuntu 22.04', 'copied_binary_origins': binaries,
              'binary_packages': packages, 'source_archives': sources, 'unowned_binary_origins': unowned,
              'apt_authentication': {'method': 'fresh isolated apt-get update; official Ubuntu HTTPS deb-src; signed-by Ubuntu archive keyring',
                                     'keyring_sha256': sha256(KEYRING), 'check_valid_until': True,
                                     'allow_insecure': False, 'allow_unauthenticated': False},
              'scope': 'copyright_and_exact_source_delivery_evidence_not_global_license_approval',
              'input_limits': {'toc_bytes': MAX_TOC_BYTES, 'toc_ast_nodes': MAX_TOC_NODES,
                               'toc_ast_depth': MAX_TOC_DEPTH, 'binary_entries': 10000,
                               'source_family_bytes': MAX_SOURCE_SET},
              'remaining_review': ['validate wheel/manual-build origins separately', 'verify final payload hashes and dynamic-library replacement rights',
                                   'check package-specific LGPL/GPL terms and required notices; this does not establish patent freedom or certify compliance']}
    report['evidence_files_sha256'] = {p.relative_to(output).as_posix(): sha256(p) for p in sorted(output.rglob('*')) if p.is_file()}
    with (output / 'linux-license-evidence.json').open('x', encoding='utf-8') as stream:
        json.dump(report, stream, indent=2)
        stream.write('\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument('--toc', type=Path, help='JSON Analysis.binaries with original source paths')
    inputs.add_argument('--pyinstaller-toc', type=Path, help='Literal PyInstaller COLLECT-00.toc (preferred) or Analysis-00.toc')
    parser.add_argument('--output', required=True, type=Path, help='New output directory; retained for review on any failure')
    args = parser.parse_args()
    report = collect(args.pyinstaller_toc or args.toc, args.output, pyinstaller_toc=args.pyinstaller_toc is not None)
    print(json.dumps({'source_families': len(report['source_archives']), 'unowned_origins': len(report['unowned_binary_origins']),
                      'scope': report['scope']}))


if __name__ == '__main__':
    main()

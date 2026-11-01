"""Recover runtime notices from the same SHA-pinned PBS build as native Python."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

RELEASE = '20261026'
SOURCES = {
    'arm64': ('aarch64-apple-darwin', '016758f4881e5f71d63eddfbcdd53f25c5a9152435a863e4dc0770758eae32c3'),
    'x64': ('x86_64-apple-darwin', '2839e81f9be73bf12dcbb84ad47e6e7a732700a689c3c713ac67ad4b5e9c9af5'),
}
REQUIRED = {'LICENSE.cpython.txt', 'LICENSE.tcl.txt', 'LICENSE.openssl-3.txt',
            'LICENSE.libffi.txt', 'LICENSE.expat.txt', 'LICENSE.sqlite.txt', 'LICENSE.zlib.txt'}


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def verify_notices(folder, arch):
    folder = Path(folder)
    proof = json.loads((folder / 'provenance.json').read_text(encoding='utf-8'))
    target, expected = SOURCES[arch]
    if (proof.get('release'), proof.get('pythonVersion'), proof.get('target'), proof.get('archiveSha256')) != (
            RELEASE, '3.12.16', target, expected):
        raise ValueError('Runtime notice provenance differs from the pinned native Python build')
    notices = proof.get('notices', {})
    if not REQUIRED <= notices.keys():
        raise ValueError('Required Python/Tcl/runtime notices are missing')
    for name, expected_hash in notices.items():
        if not re.fullmatch(r'LICENSE\.[A-Za-z0-9_-]+\.txt', name) or digest(folder / name) != expected_hash:
            raise ValueError('Runtime notice contents changed: ' + name)
    return proof


def prepare(archive, python_root, output, arch, *, tar='tar'):
    archive, python_root, output = Path(archive), Path(python_root), Path(output)
    target, expected = SOURCES[arch]
    if digest(archive) != expected:
        raise ValueError('Full Python archive hash does not match the pinned release')

    def read(member):
        return subprocess.check_output([tar, '-xOf', str(archive), member], timeout=120)

    metadata = json.loads(read('python/PYTHON.json'))
    if metadata.get('python_version') != '3.12.16' or metadata.get('target_triple') != target:
        raise ValueError('Full archive has the wrong Python version/architecture')
    # The install-only archive omits the toolchain notices. Prove that the full
    # archive supplying them contains exactly the executable we are bundling.
    executable_hash = hashlib.sha256(read('python/install/bin/python3.12')).hexdigest()
    if digest(python_root / 'bin/python3.12') != executable_hash:
        raise ValueError('Runtime notices do not belong to the installed Python executable')
    members = subprocess.check_output([tar, '-tf', str(archive)], text=True, timeout=120).splitlines()
    selected = [m for m in members if re.fullmatch(r'python/licenses/LICENSE\.[A-Za-z0-9_-]+\.txt', m)]
    if len(set(selected)) != len(selected) or not REQUIRED <= {Path(m).name for m in selected}:
        raise ValueError('Full Python archive is missing unique runtime notices')
    if output.exists():
        raise ValueError('Existing notice evidence must be preserved')
    output.mkdir(parents=True)
    hashes = {}
    for member in sorted(selected):
        content = read(member)
        if not 0 < len(content) <= 1024 * 1024:
            raise ValueError('Unexpected runtime notice size')
        name = Path(member).name
        (output / name).write_bytes(content)
        hashes[name] = hashlib.sha256(content).hexdigest()
    proof = {'release': RELEASE, 'pythonVersion': '3.12.16', 'target': target,
             'archiveSha256': expected, 'pythonExecutableSha256': executable_hash, 'notices': hashes,
             'scope': 'Unmodified PBS toolchain notice set, including notices for components that may not be bundled.'}
    (output / 'provenance.json').write_text(json.dumps(proof, indent=2) + '\n', encoding='utf-8')
    verify_notices(output, arch)
    return proof


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', required=True, type=Path)
    parser.add_argument('--python-root', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--arch', required=True, choices=SOURCES)
    parser.add_argument('--tar', default='tar', help='Archive reader; native CI uses preinstalled gtar/zstd')
    args = parser.parse_args()
    proof = prepare(args.archive, args.python_root, args.output, args.arch, tar=args.tar)
    print(json.dumps({k: v for k, v in proof.items() if k != 'notices'}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

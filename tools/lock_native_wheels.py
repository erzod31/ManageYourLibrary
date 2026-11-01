"""Resolve binary wheels on the target OS and install only their recorded hashes."""
from __future__ import annotations

import argparse
import email
import hashlib
import json
import platform
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def wheel_record(path):
    with zipfile.ZipFile(path) as archive:
        names = [n for n in archive.namelist() if n.endswith('.dist-info/METADATA')]
        if len(names) != 1:
            raise ValueError('Wheel must contain one distribution metadata record')
        metadata = email.message_from_bytes(archive.read(names[0]))
    name, version = metadata['Name'], metadata['Version']
    import re
    if not name or not re.fullmatch(r'[A-Za-z0-9_.-]+', name) or not version or not re.fullmatch(r'[A-Za-z0-9_.+!-]+', version):
        raise ValueError('Invalid wheel distribution identity')
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    return {'name': name, 'version': version, 'file': path.name, 'bytes': path.stat().st_size, 'sha256': digest}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if sys.version_info[:2] != (3, 12) or sys.platform not in {'darwin', 'linux'}:
        raise SystemExit('Resolve native release wheels using Python 3.12 on macOS or Linux')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    wheels = output / 'wheels'
    wheels.mkdir()
    subprocess.run([sys.executable, '-m', 'pip', 'download', '--only-binary=:all:', '--dest', str(wheels),
                    '-r', str(ROOT / 'requirements-build.txt')], check=True)
    records = [wheel_record(p) for p in sorted(wheels.glob('*.whl'))]
    names = [r['name'].lower().replace('_', '-') for r in records]
    if not records or len(names) != len(set(names)):
        raise SystemExit('Empty or ambiguous native wheel set')
    lock = output / 'requirements.lock'
    lock.write_text(''.join(f"{r['name']}=={r['version']} --hash=sha256:{r['sha256']}\n" for r in records))
    (output / 'provenance.json').write_text(json.dumps({'python': sys.version, 'platform': sys.platform,
        'machine': platform.machine(), 'wheels': records}, indent=2))
    subprocess.run([sys.executable, '-m', 'pip', 'install', '--no-index', '--find-links', str(wheels),
                    '--require-hashes', '-r', str(lock)], check=True)
    print(lock)


if __name__ == '__main__':
    main()

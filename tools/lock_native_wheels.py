"""Resolve native wheels once and install exactly their recorded SHA-256 hashes."""
import email
import hashlib
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def wheel_requirement(path):
    with zipfile.ZipFile(path) as archive:
        metadata = [name for name in archive.namelist()
                    if name.count('/') == 1 and name.endswith('.dist-info/METADATA')]
        if len(metadata) != 1:
            raise ValueError('Ambiguous wheel metadata')
        message = email.message_from_bytes(archive.read(metadata[0]))
    with path.open('rb') as handle:
        digest = hashlib.file_digest(handle, 'sha256').hexdigest()
    return f"{message['Name']}=={message['Version']} --hash=sha256:{digest}"


def main():
    destination = ROOT / 'dist' / 'native-dependencies'
    destination.mkdir(parents=True, exist_ok=False)
    subprocess.run([sys.executable, '-m', 'pip', 'download', '--only-binary=:all:',
                    '-r', str(ROOT / 'requirements-build.txt'), '-d', str(destination)], check=True)
    lock = destination / 'requirements.lock'
    lock.write_text('\n'.join(sorted(wheel_requirement(p) for p in destination.glob('*.whl'))) + '\n', encoding='utf-8')
    subprocess.run([sys.executable, '-m', 'pip', 'install', '--no-index', '--find-links', str(destination),
                    '--require-hashes', '-r', str(lock)], check=True)


if __name__ == '__main__':
    main()

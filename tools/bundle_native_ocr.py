"""Build and stage the controlled OCR payload on a disposable native host.

Do not copy distro/Homebrew OCR: their optional TIFF/JBIG and LGPL dependencies
are not part of this app's reviewed PNG-only runtime profile.
"""
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.build_permissive_ocr import build
from tools.verify_ocr_payload import validate_payload


def main():
    if sys.platform not in ('darwin', 'linux'):
        raise SystemExit('Build native OCR on its target OS.')
    name = 'macos' if sys.platform == 'darwin' else 'linux'
    destination = ROOT / 'platforms' / name / 'tesseract'
    if any(p.name != 'README.md' for p in destination.iterdir()):
        raise FileExistsError('Refusing to overwrite an existing native OCR payload')
    output = ROOT / 'dist/ocr'
    build(output)
    validate_payload(output / 'payload')
    shutil.copytree(output / 'payload', destination, dirs_exist_ok=True)
    validate_payload(destination)
    print('Staged reviewed OCR source profile: ' + name)


if __name__ == '__main__':
    main()

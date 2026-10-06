"""Set Finder-visible release metadata before sealing the macOS bundle."""
import plistlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUNDLE_ID = 'org.manageyourlibrary.desktop'


def configure_bundle(bundle, version):
    metadata_path = bundle / 'Contents/Info.plist'
    with metadata_path.open('rb') as handle:
        metadata = plistlib.load(handle)
    metadata.update({'CFBundleShortVersionString': version, 'CFBundleVersion': version,
                     'CFBundleIdentifier': BUNDLE_ID, 'CFBundleDisplayName': 'Manage Your Library'})
    with metadata_path.open('wb') as handle:
        plistlib.dump(metadata, handle)
    subprocess.run(['codesign', '--force', '--deep', '--sign', '-', str(bundle)], check=True)
    subprocess.run(['codesign', '--verify', '--deep', '--strict', str(bundle)], check=True)


if __name__ == '__main__':
    if sys.platform != 'darwin':
        raise SystemExit('Configure and seal the bundle on macOS only.')
    configure_bundle(ROOT / 'dist/macos/ManageYourLibrary.app', (ROOT / 'VERSION').read_text().strip())

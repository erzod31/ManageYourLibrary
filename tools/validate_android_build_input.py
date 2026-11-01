"""Verify a desktop build's APK with the SDK before accepting its release identity."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def validate(directory, version, signature_text, badging_text, *, allow_ci_certificate=False):
    directory = Path(directory)
    apk = directory / f'ManageYourLibrary-{version}.apk'
    descriptor = json.loads(apk.with_suffix('.update.json').read_text(encoding='utf-8-sig'))
    numbers = tuple(map(int, version.split('.')))
    expected = {'schema': 1, 'product': 'ManageYourLibrary', 'platform': 'android-universal', 'version': version,
                'packageName': 'com.erzod31.manageyourlibrary', 'versionCode': numbers[0]*1000000+numbers[1]*1000+numbers[2],
                'minSdk': 26, 'name': apk.name, 'bytes': apk.stat().st_size, 'sha256': digest(apk)}
    if any(descriptor.get(k) != v for k, v in expected.items()):
        raise ValueError('Android input product/version/hash/SDK mismatch')
    match = re.search(r'Signer #1 certificate SHA-256 digest: ([a-fA-F0-9]{64})', signature_text)
    if not match or match.group(1).lower() != descriptor.get('certificateSha256') or 'Number of signers: 1' not in signature_text:
        raise ValueError('Actual APK signing identity differs from metadata')
    package = re.search(r"package: name='([^']+)' versionCode='(\d+)' versionName='([^']+)'", badging_text)
    if (not package or package.groups() != ('com.erzod31.manageyourlibrary', str(expected['versionCode']), version)
            or "sdkVersion:'26'" not in badging_text or "targetSdkVersion:'37'" not in badging_text
            or 'application-debuggable' in badging_text or 'instrumentation:' in badging_text):
        raise ValueError('Actual APK package/version/SDK/QA flags mismatch')
    release_certificate = (ROOT/'platforms/android/release-certificate.sha256').read_text().strip()
    trusted = match.group(1).lower() == release_certificate
    if not trusted and not allow_ci_certificate:
        raise ValueError('CI/test signing key cannot replace the preserved Android release identity')
    return {'passed': True, 'version': version, 'sha256': expected['sha256'], 'bytes': expected['bytes'],
            'certificateSha256': match.group(1).lower(), 'releaseSigner': trusted, 'distributionEligible': trusted,
            'signingValidation': 'real Android SDK apksigner and aapt; read-only, no install'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, default=ROOT/'dist/android')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--allow-ci-certificate', action='store_true')
    args = parser.parse_args()
    version = (ROOT/'VERSION').read_text().strip()
    sdk = Path(os.environ['ANDROID_HOME'])/'build-tools/36.0.0'
    java = Path(os.environ['JAVA_HOME'])/'bin'/('java.exe' if os.name == 'nt' else 'java')
    apk = args.directory/f'ManageYourLibrary-{version}.apk'
    signature = subprocess.check_output([str(java), '-jar', str(sdk/'lib/apksigner.jar'), 'verify', '--verbose', '--print-certs',
                                         '--min-sdk-version', '26', str(apk)], text=True)
    badging = subprocess.check_output([str(sdk/('aapt.exe' if os.name == 'nt' else 'aapt')), 'dump', 'badging', str(apk)], text=True)
    report = validate(args.directory, version, signature, badging, allow_ci_certificate=args.allow_ci_certificate)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()

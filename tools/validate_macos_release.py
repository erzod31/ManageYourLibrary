"""Native bundle/architecture/signature gates. QA acceptance never means distribution approval."""
from __future__ import annotations

import argparse
import json
import os
import platform
import plistlib
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.app_updates import APP_ID, MAC_BUNDLE_ID, PRODUCT
from tools.prepare_macos_python_notices import verify_notices

CPUS = {0x01000007: 'x64', 0x0100000C: 'arm64'}


def macho_architectures(header):
    """Read thin/fat Mach-O headers without executing a binary or assuming a host OS."""
    if len(header) < 8:
        return set()
    magic = header[:4]
    if magic in {b'\xcf\xfa\xed\xfe', b'\xce\xfa\xed\xfe', b'\xfe\xed\xfa\xcf', b'\xfe\xed\xfa\xce'}:
        endian = '<' if magic[:1] in {b'\xcf', b'\xce'} else '>'
        cpu = struct.unpack_from(endian + 'I', header, 4)[0]
        return {CPUS.get(cpu, 'unsupported')}
    if magic not in {b'\xca\xfe\xba\xbe', b'\xca\xfe\xba\xbf', b'\xbe\xba\xfe\xca', b'\xbf\xba\xfe\xca'}:
        return set()
    endian = '>' if magic[:1] == b'\xca' else '<'
    count = struct.unpack_from(endian + 'I', header, 4)[0]
    stride = 32 if magic in {b'\xca\xfe\xba\xbf', b'\xbf\xba\xfe\xca'} else 20
    if not 1 <= count <= 16 or len(header) < 8 + count * stride:
        raise ValueError('Truncated/invalid fat Mach-O architecture table')
    return {CPUS.get(struct.unpack_from(endian + 'I', header, 8 + i * stride)[0], 'unsupported') for i in range(count)}


def inspect_bundle(bundle, version, arch):
    bundle = Path(bundle).resolve()
    if bundle.name != 'ManageYourLibrary.app' or arch not in {'arm64', 'x64'}:
        raise ValueError('Unexpected macOS bundle/architecture')
    plist = plistlib.loads((bundle / 'Contents/Info.plist').read_bytes())
    expected = {'CFBundleIdentifier': MAC_BUNDLE_ID, 'CFBundleExecutable': 'ManageYourLibrary',
                'CFBundleShortVersionString': version, 'CFBundleVersion': version}
    if any(plist.get(k) != v for k, v in expected.items()):
        raise ValueError('Published bundle identity/version was not preserved')
    if plist.get('LSMinimumSystemVersion') != '14.0':
        raise ValueError('The pinned OCR runtime requires an explicit macOS 14.0 minimum')
    marker = next((bundle / p for p in ['Contents/Resources/update-identity.json',
                  'Contents/Frameworks/update-identity.json'] if (bundle / p).is_file()), None)
    if marker is None:
        raise ValueError('No embedded updater identity')
    identity = json.loads(marker.read_text())
    if any(identity.get(k) != v for k, v in {'product': PRODUCT, 'appId': APP_ID,
        'macBundleId': MAC_BUNDLE_ID, 'version': version, 'platform': 'macos-' + arch}.items()):
        raise ValueError('Embedded updater identity does not match bundle')
    if marker.with_name('VERSION').read_text().strip() != version:
        raise ValueError('Bundled VERSION does not match')
    runtime_notices = verify_notices(marker.parent / 'third_party/python-runtime', arch)
    executable = bundle / 'Contents/MacOS/ManageYourLibrary'
    if not executable.is_file() or not executable.stat().st_mode & 0o111:
        raise ValueError('Main executable is missing or not executable')
    binaries, seen = [], set()
    for path in bundle.rglob('*'):
        if path.is_symlink() and not path.resolve().is_relative_to(bundle):
            raise ValueError('Bundle contains an external symlink')
        if not path.is_file() or path.resolve() in seen:
            continue
        seen.add(path.resolve())
        with path.open('rb') as stream:
            architectures = macho_architectures(stream.read(1024))
        if architectures:
            if arch not in architectures or 'unsupported' in architectures:
                raise ValueError('Wrong Mach-O architecture: ' + path.relative_to(bundle).as_posix())
            binaries.append(path.relative_to(bundle).as_posix())
    if executable.relative_to(bundle).as_posix() not in binaries:
        raise ValueError('Main executable is not Mach-O')
    return {'bundleId': MAC_BUNDLE_ID, 'version': version, 'arch': arch, 'minimumMacOS': '14.0',
            'runtimeNoticesChecked': len(runtime_notices['notices']), 'machOBinariesChecked': len(binaries)}


def command(arguments):
    result = subprocess.run(arguments, capture_output=True, text=True, timeout=120)
    return {'exitCode': result.returncode, 'output': (result.stdout + result.stderr).strip()[:12000]}


def native_validate(bundle, version, arch, *, require_distribution=False, expected_team=None, run=command):
    if sys.platform != 'darwin':
        raise RuntimeError('macOS native validation requires a real macOS executor')
    actual = 'arm64' if platform.machine().lower() == 'arm64' else 'x64'
    if actual != arch:
        raise ValueError('Native runner architecture differs from selected output')
    report = inspect_bundle(bundle, version, arch)
    signature = run(['/usr/bin/codesign', '--verify', '--deep', '--strict', str(bundle)])
    details = run(['/usr/bin/codesign', '-dv', '--verbose=4', str(bundle)])
    gatekeeper = run(['/usr/sbin/spctl', '--assess', '--type', 'execute', '--verbose=4', str(bundle)])
    ticket = run(['/usr/bin/xcrun', 'stapler', 'validate', str(bundle)])
    import re
    match = re.search(r'^TeamIdentifier=(.+)$', details['output'], re.M)
    team = match.group(1).strip() if match else None
    developer_id = 'Authority=Developer ID Application:' in details['output'] and team not in {None, 'not set'}
    input_report = ROOT/'dist/android/build-input-validation.json'
    trusted_android = False
    if input_report.is_file():
        from tools.validate_android_build_input import digest
        android = json.loads(input_report.read_text())
        apk = next((bundle / p for p in [f'Contents/Resources/android/ManageYourLibrary-{version}.apk',
                    f'Contents/Frameworks/android/ManageYourLibrary-{version}.apk'] if (bundle / p).is_file()), None)
        pinned = (ROOT/'platforms/android/release-certificate.sha256').read_text().strip()
        trusted_android = bool(apk and android.get('passed') is True and android.get('releaseSigner') is True and
            android.get('sha256') == digest(apk) and android.get('version') == version and android.get('certificateSha256') == pinned)
    eligible = (signature['exitCode'] == details['exitCode'] == gatekeeper['exitCode'] == ticket['exitCode'] == 0
                and developer_id and trusted_android and bool(expected_team) and team == expected_team)
    report.update(nativeExecution=True, signature=signature, identity=details, gatekeeper=gatekeeper,
                  stapledTicket=ticket, developerTeam=team, expectedTeam=expected_team,
                  androidReleaseInput=trusted_android, distributionEligible=eligible,
                  validationMode='distribution' if require_distribution else 'qa',
                  passed=signature['exitCode'] == details['exitCode'] == 0 and (eligible or not require_distribution))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundle', type=Path)
    parser.add_argument('--version', required=True)
    parser.add_argument('--arch', choices=['arm64', 'x64'], required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--require-distribution', action='store_true')
    args = parser.parse_args()
    if args.output.resolve().is_relative_to(args.bundle.resolve()):
        raise SystemExit('Validation evidence must stay outside the signed bundle')
    try:
        report = native_validate(args.bundle.resolve(), args.version, args.arch,
            require_distribution=args.require_distribution, expected_team=os.environ.get('MYL_MACOS_TEAM_ID'))
    except Exception as exc:
        report = {'passed': False, 'nativeExecution': sys.platform == 'darwin', 'distributionEligible': False,
                  'error': f'{type(exc).__name__}: {exc}'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k not in {'signature', 'identity', 'gatekeeper', 'stapledTicket'}}))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())

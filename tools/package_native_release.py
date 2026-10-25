"""Fail-closed native packaging, including a re-test of the extracted archive."""
import argparse
import hashlib
import json
import os
import platform
import plistlib
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.write_build_manifest import git_value, source_tree_fingerprint
from tools.verify_ocr_payload import validate_payload as validate_ocr_payload
from tools.verify_accessibility import BASE_CHECKS, WINDOWS_CHECKS
RUNTIME_CHECKS = {'tk_init', 'bundled_languages', 'image_ocr', 'pdfium_ocr', 'reader_isolation'}
FIRST_CHECKS = {'clean_defaults', 'empty_workspace', 'no_background_operations', 'no_automatic_network', 'fresh_state'}
PRIVATE_NAMES = {'config.json', 'library_index.json', 'historial.csv', 'library_history.csv',
                 'undo_log.jsonl', 'file_transactions.jsonl', 'trash_manifest.jsonl',
                 'saved_views.json', 'profile-manifest.json', '.profile.lock'}
PRIVATE_SUFFIXES = {'.db', '.jsonl', '.csv', '.gguf', '.part', '.log', '.pdf', '.epub', '.mobi', '.azw', '.azw3',
                    '.djvu', '.fb2', '.rtf', '.doc', '.docx', '.odt', '.cbr', '.cbz'}


def sha256(path):
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def validate_payload(payload):
    root = payload.resolve()
    files = {}
    for path in sorted(payload.rglob('*')):
        if path.is_symlink() and not path.resolve().is_relative_to(root):
            raise ValueError('Payload symlink escapes the application')
        name = path.name.lower()
        if (name in PRIVATE_NAMES or '.sqlite' in name or path.suffix.lower() in PRIVATE_SUFFIXES
                or name.startswith(('metadata_cache', 'ocr_cache', 'analysis_cache'))
                or name in {'.trash_manageyourlibrary', 'ui_thumbnails', '__pycache__', 'test_reports', 'backups'}):
            raise ValueError('Personal state or book file in payload: ' + path.name)
        if path.is_file():
            files[path.relative_to(payload).as_posix()] = sha256(path)
    return files


def validate_report(path, checks, version):
    report = json.loads(path.read_text(encoding='utf-8'))
    if report.get('version') != version or report.get('frozen') is not True or report.get('passed') is not True:
        raise ValueError('Diagnostic did not pass in the frozen application')
    if set(report.get('checks', {})) != checks or any(value != 'passed' for value in report['checks'].values()):
        raise ValueError('Incomplete diagnostic checks')
    return report


def validate_accessibility_api_report(path, *, platform, version, frozen,
                                      source_commit=None, source_tree=None, executable_sha256=None):
    report = json.loads(path.read_text(encoding='utf-8'))
    if platform not in {'linux', 'macos'}:
        raise ValueError('Unsupported native accessibility platform')
    required = WINDOWS_CHECKS if platform == 'macos' else BASE_CHECKS
    checks = report.get('checks', {})
    if (report.get('passed') is not True or report.get('backend') != 'tk_native'
            or report.get('platform') != platform or report.get('version') != version
            or report.get('windowing_system') != ('aqua' if platform == 'macos' else 'x11')
            or report.get('frozen') is not frozen or set(checks) != required
            or not all(value is True for value in checks.values())
            or report.get('errors')):
        raise ValueError('Native accessibility API report is incomplete or failed')
    if frozen:
        if (not isinstance(executable_sha256, str) or not re.fullmatch(r'[0-9a-fA-F]{64}', executable_sha256)
                or str(report.get('executable_sha256', '')).lower() != executable_sha256.lower()):
            raise ValueError('Frozen accessibility report does not match the executable')
    elif (not isinstance(source_commit, str) or not re.fullmatch(r'(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})', source_commit)
            or not isinstance(source_tree, dict)
            or not re.fullmatch(r'[0-9a-fA-F]{64}', str(source_tree.get('sha256', '')))
            or type(source_tree.get('files')) is not int or source_tree['files'] <= 0
            or report.get('git_commit') != source_commit or report.get('source_tree') != source_tree
            or report.get('git_status') != ''):
        raise ValueError('Source accessibility report does not match the clean source tree')
    return report


def validate_gui_provenance(path, lock_path, *, platform, patch_receipt=None):
    """Retain the actual GUI build record, including the Linux repair."""
    record = json.loads(path.read_text(encoding='utf-8'))
    locked = json.loads(lock_path.read_text(encoding='utf-8'))
    if not isinstance(record, dict) or any(record.get(key) != value for key, value in locked.items()):
        raise ValueError('GUI build provenance differs from the pinned upstream inputs')
    if platform == 'linux':
        if patch_receipt is None:
            raise ValueError('Linux GUI patch receipt is missing')
        patch = json.loads(patch_receipt.read_text(encoding='utf-8'))
        from tools.tk_linux_patch import PATCH_ID
        if patch.get('patch_id') != PATCH_ID or record.get('linux_accessibility_patch') != patch:
            raise ValueError('Linux GUI build record differs from the packaged patch receipt')
    elif platform != 'macos' or record != locked:
        raise ValueError('Unexpected native GUI build provenance')
    return {'sha256': sha256(path), 'upstream_version': locked['version'],
            'linux_accessibility_patch': record.get('linux_accessibility_patch', {}).get('patch_id')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--platform', choices=('linux', 'macos'), required=True)
    args = parser.parse_args()
    name = args.platform
    version = (ROOT / 'VERSION').read_text().strip()
    architecture = {'x86_64': 'x64', 'arm64': 'arm64', 'aarch64': 'arm64'}[platform.machine()]
    base = ROOT / 'dist' / name
    payload = base / ('ManageYourLibrary.app' if name == 'macos' else 'ManageYourLibrary')
    executable = payload / ('Contents/MacOS/ManageYourLibrary' if name == 'macos' else 'ManageYourLibrary')
    evidence = base if name == 'macos' else payload
    api_report = ROOT / 'dist/accessibility-self-test.json'
    source_commit = git_value('rev-parse', 'HEAD')
    source_tree = source_tree_fingerprint()
    validate_accessibility_api_report(api_report, platform=name, version=version, frozen=False,
                                      source_commit=source_commit, source_tree=source_tree)
    validate_report(evidence / 'runtime-self-test.json', RUNTIME_CHECKS, version)
    validate_report(evidence / 'first-use-self-test.json', FIRST_CHECKS, version)
    manifest = json.loads((evidence / 'build-manifest.json').read_text(encoding='utf-8'))
    if (manifest['version'] != version or manifest['git_commit'] != source_commit
            or manifest['source_tree'] != source_tree):
        raise ValueError('Manifest does not describe the current build source/version')
    if manifest['git_status'] or manifest['sha256'].lower() != sha256(executable):
        raise ValueError('Build source is dirty or executable differs from manifest')
    frozen_api_report = evidence / 'accessibility-self-test.json'
    validate_accessibility_api_report(frozen_api_report, platform=name, version=version, frozen=True,
                                      executable_sha256=manifest['sha256'])
    if (manifest['validation'].get('ocr_libraries_profile') != 'passed'
            or manifest.get('ocr_source_payload') != validate_ocr_payload(ROOT / 'platforms' / name / 'tesseract')):
        raise ValueError('Native OCR source profile was not validated')
    gui_provenance = ROOT / 'dist/native-gui/build-provenance.json'
    patch_receipt = (payload / '_internal/licenses/tcltk/myl-tk-linux-repair/patch-provenance.json'
                     if name == 'linux' else None)
    manifest['gui_build_provenance'] = validate_gui_provenance(
        gui_provenance, ROOT / 'tools/tk_sources.json', platform=name, patch_receipt=patch_receipt)
    for gate in ('automated_tests', 'source_smoke', 'catalog_performance_gate', 'frozen_smoke', 'runtime_self_test', 'first_use_self_test'):
        if manifest['validation'].get(gate) != 'passed':
            raise ValueError('Build gate was not recorded: ' + gate)
    if name == 'macos':
        with (payload / 'Contents/Info.plist').open('rb') as handle:
            metadata = plistlib.load(handle)
        if metadata.get('CFBundleShortVersionString') != version or metadata.get('CFBundleVersion') != version:
            raise ValueError('Finder-visible version does not match the release')
        subprocess.run(['codesign', '--verify', '--deep', '--strict', str(payload)], check=True)
        manifest['validation']['code_signing'] = 'ad_hoc_only; no Developer ID; not notarized'
    release = ROOT / 'dist' / 'native-release'
    release.mkdir(parents=True, exist_ok=True)
    label = f'ManageYourLibrary-{version}-' + ('macOS' if name == 'macos' else 'Linux') + '-' + architecture
    if name == 'linux':
        from tools.package_linux_license_evidence import prepare
        manifest['linux_os_library_evidence'] = prepare(payload, ROOT / 'dist/linux-license-evidence', release, label)
    files = validate_payload(payload)
    archive = release / (label + ('.zip' if name == 'macos' else '.tar.gz'))
    if archive.exists():
        raise ValueError('Refusing to overwrite an existing release archive')
    if name == 'macos':
        subprocess.run(['ditto', '-c', '-k', '--sequesterRsrc', '--keepParent', str(payload), str(archive)], check=True)
    else:
        with tarfile.open(archive, 'w:gz') as handle:
            handle.add(payload, arcname=payload.name)
    with tempfile.TemporaryDirectory(prefix='myl-extracted-') as temp:
        extracted = Path(temp)
        if name == 'macos':
            subprocess.run(['ditto', '-x', '-k', str(archive), temp], check=True)
            subprocess.run(['codesign', '--verify', '--deep', '--strict', str(extracted / payload.name)], check=True)
        else:
            with tarfile.open(archive) as handle:
                # Our archive has already passed an internal-only symlink audit.
                handle.extractall(extracted, filter='data')
        restored = extracted / payload.name
        if validate_payload(restored) != files:
            raise ValueError('Archive contents differ from the validated application')
        launcher = restored / executable.relative_to(payload)
        subprocess.run([str(launcher), '--smoke-test'], check=True, timeout=90)
        for flag, check_set in (('runtime', RUNTIME_CHECKS), ('first-use', FIRST_CHECKS)):
            report = extracted / (flag + '.json')
            result = subprocess.run([str(launcher), '--' + flag + '-self-test', str(report)], timeout=90)
            if result.returncode:
                if report.is_file():
                    diagnostic = evidence / ('extracted-' + flag + '-self-test.json')
                    shutil.copy2(report, diagnostic)
                    print(report.read_text(encoding='utf-8'), flush=True)
                raise RuntimeError('Extracted application failed ' + flag + ' diagnostics')
            validate_report(report, check_set, version)
        extracted_api_report = extracted / 'accessibility.json'
        result = subprocess.run([str(launcher), '--accessibility-self-test', str(extracted_api_report)], timeout=90)
        if result.returncode:
            if extracted_api_report.is_file():
                shutil.copy2(extracted_api_report, evidence / 'extracted-accessibility-self-test.json')
                print(extracted_api_report.read_text(encoding='utf-8'), flush=True)
            raise RuntimeError('Extracted application failed accessibility diagnostics')
        validate_accessibility_api_report(extracted_api_report, platform=name, version=version, frozen=True,
                                          executable_sha256=manifest['sha256'])
        # Diagnostic reports stay outside the extracted payload. Checks must
        # not silently modify signed resources or the original application.
        if validate_payload(restored) != files:
            raise ValueError('Extracted diagnostics modified the application payload')
    manifest.update({
        'architecture': architecture, 'build_os': platform.platform(),
        'archive': {'name': archive.name, 'sha256': sha256(archive), 'size': archive.stat().st_size},
        'extracted_archive_checks': 'frozen smoke, runtime OCR/Tk/PDFium, clean first use and native accessibility API passed',
        'github_run_id': os.environ.get('GITHUB_RUN_ID', ''),
        'minimum_tested_os': 'macOS 15' if name == 'macos' else 'Ubuntu 22.04 x64 (glibc 2.35)',
        'payload_sha256': files,
        'accessibility_scope': 'source and frozen/extracted native API properties/actions; not external client or speech certification',
    })
    (release / (label + '-manifest.json')).write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    for filename in ('runtime-self-test.json', 'first-use-self-test.json'):
        shutil.copy2(evidence / filename, release / (label + '-' + filename))
    shutil.copy2(ROOT / 'dist/native-dependencies/requirements.lock', release / (label + '-requirements.lock'))
    shutil.copy2(ROOT / 'platforms' / name / 'tesseract/native-ocr-manifest.json', release / (label + '-ocr-manifest.json'))
    shutil.copy2(ROOT / 'docs/NATIVE_FIRST_USE.md', release / (label + '-README.md'))
    shutil.copy2(api_report, release / (label + '-source-accessibility-api.json'))
    shutil.copy2(frozen_api_report, release / (label + '-frozen-accessibility-api.json'))
    shutil.copy2(gui_provenance, release / (label + '-gui-sources.json'))
    shutil.copy2(ROOT / 'dist/ocr-formats.json', release / (label + '-ocr-formats.json'))
    checksums = release / (label + '-SHA256SUMS.txt')
    checksums.write_text(''.join(f'{sha256(p)}  {p.name}\n' for p in sorted(release.glob(label + '*')) if p != checksums), encoding='utf-8')
    print(archive)


if __name__ == '__main__':
    main()

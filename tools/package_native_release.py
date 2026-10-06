"""Fail-closed native packaging, including a re-test of the extracted archive."""
import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.write_build_manifest import git_value, source_tree_fingerprint
RUNTIME_CHECKS = {'tk_init', 'bundled_languages', 'image_ocr', 'pdfium_ocr'}
FIRST_CHECKS = {'clean_defaults', 'empty_workspace', 'no_background_operations', 'no_automatic_network', 'fresh_state'}
PRIVATE_NAMES = {'config.json', 'library_index.json', 'historial.csv', 'library_history.csv',
                 'undo_log.jsonl', 'file_transactions.jsonl', 'trash_manifest.jsonl'}
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
    validate_report(evidence / 'runtime-self-test.json', RUNTIME_CHECKS, version)
    validate_report(evidence / 'first-use-self-test.json', FIRST_CHECKS, version)
    manifest = json.loads((evidence / 'build-manifest.json').read_text(encoding='utf-8'))
    if (manifest['version'] != version or manifest['git_commit'] != git_value('rev-parse', 'HEAD')
            or manifest['source_tree'] != source_tree_fingerprint()):
        raise ValueError('Manifest does not describe the current build source/version')
    if manifest['git_status'] or manifest['sha256'].lower() != sha256(executable):
        raise ValueError('Build source is dirty or executable differs from manifest')
    for gate in ('automated_tests', 'source_smoke', 'catalog_performance_gate', 'frozen_smoke', 'runtime_self_test', 'first_use_self_test'):
        if manifest['validation'].get(gate) != 'passed':
            raise ValueError('Build gate was not recorded: ' + gate)
    if name == 'macos':
        subprocess.run(['codesign', '--verify', '--deep', '--strict', str(payload)], check=True)
        manifest['validation']['code_signing'] = 'ad_hoc_only; no Developer ID; not notarized'
    files = validate_payload(payload)
    release = ROOT / 'dist' / 'native-release'
    release.mkdir(parents=True, exist_ok=True)
    label = f'ManageYourLibrary-{version}-' + ('macOS' if name == 'macos' else 'Linux') + '-' + architecture
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
            subprocess.run([str(launcher), '--' + flag + '-self-test', str(report)], check=True, timeout=90)
            validate_report(report, check_set, version)
    manifest.update({
        'architecture': architecture, 'build_os': platform.platform(),
        'archive': {'name': archive.name, 'sha256': sha256(archive), 'size': archive.stat().st_size},
        'extracted_archive_checks': 'frozen smoke, runtime OCR/Tk/PDFium and clean first use passed',
        'github_run_id': os.environ.get('GITHUB_RUN_ID', ''),
        'minimum_tested_os': 'macOS 15' if name == 'macos' else 'Ubuntu 22.04 x64 (glibc 2.35)',
        'payload_sha256': files,
    })
    (release / (label + '-manifest.json')).write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    for filename in ('runtime-self-test.json', 'first-use-self-test.json'):
        shutil.copy2(evidence / filename, release / (label + '-' + filename))
    shutil.copy2(ROOT / 'dist/native-dependencies/requirements.lock', release / (label + '-requirements.lock'))
    shutil.copy2(ROOT / 'platforms' / name / 'tesseract/native-ocr-manifest.json', release / (label + '-ocr-manifest.json'))
    shutil.copy2(ROOT / 'docs/NATIVE_FIRST_USE.md', release / (label + '-README.md'))
    checksums = release / (label + '-SHA256SUMS.txt')
    checksums.write_text(''.join(f'{sha256(p)}  {p.name}\n' for p in sorted(release.glob(label + '*')) if p != checksums), encoding='utf-8')
    print(archive)


if __name__ == '__main__':
    main()

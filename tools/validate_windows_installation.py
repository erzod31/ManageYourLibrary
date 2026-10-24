"""Install/upgrade/uninstall a unique sandbox AppId; never touch an existing install.

The installer file rules are identical; shortcuts are suppressed for this probe.
This is not interactive desktop, administrator, or security-policy certification.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(command, **options):
    result = subprocess.run([str(value) for value in command], capture_output=True, text=True,
                            errors='replace', timeout=600, creationflags=subprocess.CREATE_NO_WINDOW, **options)
    if result.returncode:
        raise RuntimeError(f'{Path(command[0]).name} failed ({result.returncode}): {result.stderr[-1000:]}')


def validate(payload, previous, compiler):
    if os.name != 'nt':
        raise RuntimeError('Native Windows check only')
    for folder in {payload, previous}:
        if not (folder / 'ManageYourLibrary.exe').is_file():
            raise FileNotFoundError(str(folder))
    with tempfile.TemporaryDirectory(prefix='myl_installer_validation_') as directory:
        base = Path(directory).resolve()
        install = base / 'installation'
        profile = base / 'profile'
        profile.mkdir()
        # Representative synthetic state; no real catalog or current installation.
        fixtures = {'config.json': '{"library":"synthetic","language":"es"}',
                    'library_index.json': '{"archivos":[]}', 'pending-plans.txt': 'pending synthetic plan',
                    'quarantine/book.txt': 'recoverable synthetic book', 'history.txt': 'human correction fixture'}
        for name, content in fixtures.items():
            path = profile / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding='utf-8')
        before = {name: digest(profile / name) for name in fixtures}
        unique_id = 'ManageYourLibrary.Validation.' + uuid.uuid4().hex
        version = (ROOT / 'VERSION').read_text(encoding='utf-8').strip()
        checks = {}

        def check_profile(stage):
            if {name: digest(profile / name) for name in fixtures} != before:
                raise RuntimeError('Sandbox profile changed during ' + stage)
            checks[stage + '_preserves_profile'] = 'passed'

        def compile_install(folder, stage):
            output = base / stage
            output.mkdir()
            run([compiler, '/Qp', '/DSourceRoot=' + str(ROOT), '/DSourcePayload=' + str(folder),
                 '/DInstallerOutput=' + str(output), '/DValidationAppId=' + unique_id,
                 '/DAppVersion=' + version, ROOT / 'platforms/windows/ManageYourLibrary.iss'])
            setup = output / f'ManageYourLibrary-{version}-Setup-x64.exe'
            run([setup, '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/CURRENTUSER', '/SP-',
                 '/DIR=' + str(install), '/LOG=' + str(base / (stage + '.log'))])
            if digest(install / 'ManageYourLibrary.exe') != digest(folder / 'ManageYourLibrary.exe'):
                raise RuntimeError('Installed executable does not match ' + stage)
            check_profile(stage)
            checks[stage + '_payload'] = 'passed'

        try:
            compile_install(previous, 'initial_install')
            compile_install(payload, 'upgrade')
            result_path = base / 'installed-runtime.json'
            run([install / 'ManageYourLibrary.exe', '--runtime-self-test', result_path],
                env={**os.environ, 'MANAGE_YOUR_LIBRARY_PROFILE': str(profile)})
            result = json.loads(result_path.read_text(encoding='utf-8'))
            expected = {'tk_init', 'bundled_languages', 'image_ocr', 'pdfium_ocr', 'reader_isolation'}
            if (result.get('passed') is not True or result.get('frozen') is not True
                    or set(result.get('checks', {})) != expected
                    or any(value != 'passed' for value in result['checks'].values())):
                raise RuntimeError('Installed runtime checks failed')
            checks['installed_runtime'] = result['checks']
        finally:
            uninstaller = install / 'unins000.exe'
            # Resolve the exact test-owned target before running a removal tool.
            if uninstaller.is_file():
                if not uninstaller.resolve().is_relative_to(base) or install.parent != base:
                    raise RuntimeError('Unsafe uninstaller target')
                run([uninstaller, '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART'])
                if (install / 'ManageYourLibrary.exe').exists():
                    raise RuntimeError('Sandbox executable survived uninstall')
                check_profile('uninstall')
                checks['uninstall_payload_removed'] = 'passed'
        return {'scope': 'Native Windows silent per-user install, upgrade and uninstall with a unique test AppId; no shortcuts',
                'previous_exe_sha256': digest(previous / 'ManageYourLibrary.exe'),
                'current_exe_sha256': digest(payload / 'ManageYourLibrary.exe'),
                'checks': checks, 'passed': True, 'manual_installed_ui': 'not_run',
                'real_user_profile': 'not_opened', 'signing': 'not_performed'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--payload', required=True, type=Path)
    parser.add_argument('--previous', required=True, type=Path)
    parser.add_argument('--compiler', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    result = validate(args.payload.resolve(), args.previous.resolve(), args.compiler.resolve())
    args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()

"""Compile and exercise the actual Windows dispatcher with AddressSanitizer."""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--baseline-source', type=Path,
                        help='Also reproduce the original memory error from the hash-locked upstream source.')
    args = parser.parse_args()
    if os.name != 'nt':
        raise RuntimeError('Native dispatcher tests require Windows/MSVC')
    from setuptools._distutils._msvccompiler import _get_vc_env
    env = {key.upper(): value for key, value in os.environ.items()}
    env.update({key.upper(): value for key, value in _get_vc_env('x86_amd64').items()})
    env['ASAN_OPTIONS'] = 'halt_on_error=1:detect_leaks=0'
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    source = ROOT / 'tools/native/test_tkWinA11yDispatch.c'
    header = source.with_name('tkWinA11yDispatch.h')
    compiler = shutil.which('cl.exe', path=env['PATH'])
    if not compiler:
        raise FileNotFoundError('MSVC compiler not found')
    executable = output / 'dispatch-tests.exe'
    command = [compiler, '/nologo', '/std:c11', '/Zi', '/Od', '/fsanitize=address',
               '/W4', str(source), '/Fe:' + str(executable),
               '/Fo:' + str(output / 'dispatch-tests.obj'), '/Fd:' + str(output / 'dispatch-tests.pdb')]
    subprocess.run(command, env=env, cwd=output, check=True)
    result = subprocess.run([str(executable)], env=env, cwd=output, check=True,
                            text=True, capture_output=True, timeout=45)
    report = json.loads(result.stdout)
    report.update(address_sanitizer=True, compiler=Path(compiler).name,
                  source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                  dispatcher_sha256=hashlib.sha256(header.read_bytes()).hexdigest())
    enum_source = source.with_name('test_tkWinA11yEnum.c')
    enum_executable = output / 'enum-tests.exe'
    enum_command = [compiler, '/nologo', '/std:c11', '/Zi', '/Od', '/fsanitize=address',
                    str(enum_source), '/Fe:' + str(enum_executable),
                    '/Fo:' + str(output / 'enum-tests.obj'), '/Fd:' + str(output / 'enum-tests.pdb'),
                    '/link', 'oleaut32.lib', 'uuid.lib']
    subprocess.run(enum_command, env=env, cwd=output, check=True)
    enum_result = subprocess.run([str(enum_executable)], env=env, cwd=output, check=True,
                                 text=True, capture_output=True, timeout=30)
    report['enumerator'] = json.loads(enum_result.stdout)
    report['enumerator']['source_sha256'] = hashlib.sha256(enum_source.read_bytes()).hexdigest()
    report['enumerator']['header_sha256'] = hashlib.sha256(enum_source.with_name('tkWinA11yEnum.h').read_bytes()).hexdigest()
    if args.baseline_source:
        from tk_windows_patch import INPUT_HASHES
        raw = args.baseline_source.read_bytes()
        if hashlib.sha256(raw).hexdigest() != INPUT_HASHES['tkWinAccessibility.c']:
            raise ValueError('Baseline is not the pinned upstream source')
        original = raw.decode('utf-8')
        start = original.index('typedef struct {\n    Tcl_Event header;\n    MainThreadFunc func;')
        end = original.index('} MainThreadSyncEvent;', start) + len('} MainThreadSyncEvent;')
        pieces = [original[start:end]]
        for name in ('ExecuteOnMainThreadSync', 'RunOnMainThreadSync'):
            match = re.search(r'^(?:int|void) ' + name + r'\([^;]*?^\{.*?^\}', original, re.M | re.S)
            if not match:
                raise ValueError('Missing baseline function: ' + name)
            pieces.append(match[0])
        (output / 'legacy-dispatch.h').write_text('\n'.join(pieces), encoding='utf-8')
        baseline = output / 'legacy-dispatch-tests.exe'
        baseline_command = [compiler, '/nologo', '/std:c11', '/Zi', '/Od', '/fsanitize=address',
                            '/DMYL_TEST_LEGACY', '/I' + str(output), str(source),
                            '/Fe:' + str(baseline), '/Fo:' + str(output / 'legacy-tests.obj'),
                            '/Fd:' + str(output / 'legacy-tests.pdb')]
        subprocess.run(baseline_command, env=env, cwd=output, check=True)
        old = subprocess.run([str(baseline)], env=env, cwd=output,
                             text=True, capture_output=True, timeout=45)
        diagnostics = old.stdout + old.stderr
        (output / 'baseline-asan.log').write_text(diagnostics, encoding='utf-8')
        reproduced = (old.returncode != 0 and 'AddressSanitizer' in diagnostics
                      and ('heap-use-after-free' in diagnostics or 'double-free' in diagnostics))
        report['baseline_memory_error_reproduced'] = reproduced
        if not reproduced:
            raise AssertionError('The negative control did not reproduce the original memory error')
    (output / 'result.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()

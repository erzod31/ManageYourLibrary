"""Build the app's PNG-only OCR CLI from pinned source; never bundle system OCR.

All image codecs needed by the app live in Pillow/PDFium, upstream of this CLI.
The four OCR libraries are static, not the host OS/C++ runtime. No JBIG/TIFF,
gettext, iconv, GLib, Pango, archive, curl, GCC DLL or training tools are copied.
"""
import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import urllib.request
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / 'tools/ocr_source_lock.json'
MAX_DOWNLOAD = 40 * 1024 * 1024
MAX_EXPANDED = 200 * 1024 * 1024


def digest(path):
    with Path(path).open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def fetch(url, path, expected):
    if not path.exists():
        with urllib.request.urlopen(url, timeout=90) as response, path.open('xb') as out:
            size = 0
            while chunk := response.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_DOWNLOAD:
                    raise ValueError('Oversized source download')
                out.write(chunk)
    if digest(path) != expected:
        raise ValueError('Source/notice hash mismatch: ' + path.name)


def extract(archive, target):
    """Extract files/directories only, rejecting links, traversal and tar bombs."""
    target.mkdir()
    with tarfile.open(archive, 'r:gz') as source:
        members = source.getmembers()
        if sum(m.size for m in members) > MAX_EXPANDED or len(members) > 20000:
            raise ValueError('Oversized source archive')
        roots = set()
        for member in members:
            parts = PurePosixPath(member.name).parts
            if (not parts or member.name.startswith('/') or '\\' in member.name
                    or any(p in {'.', '..'} or ':' in p for p in parts)
                    or not (member.isfile() or member.isdir())):
                raise ValueError('Unsafe source archive member: ' + member.name)
            roots.add(parts[0])
        if len(roots) != 1:
            raise ValueError('Expected one upstream source directory')
        source.extractall(target, members=members, filter='data')
    return target / roots.pop()


def verify_extracted_source(archive, source):
    with tarfile.open(archive, 'r:gz') as upstream:
        expected = set()
        for member in upstream.getmembers():
            relative = PurePosixPath(member.name).parts[1:]
            if member.isfile():
                path = source.joinpath(*relative)
                expected.add(path.relative_to(source).as_posix())
                if path.is_symlink() or not path.is_file() or path.read_bytes() != upstream.extractfile(member).read():
                    raise ValueError('Extracted source differs from pinned archive: ' + member.name)
        actual = {p.relative_to(source).as_posix() for p in source.rglob('*') if p.is_file()}
        if actual != expected:
            raise ValueError('Unexpected files in resumed source directory')


def build_environment():
    env = dict(os.environ)
    if os.name == 'nt':
        from setuptools._distutils._msvccompiler import _get_vc_env
        env = {k.upper(): v for k, v in env.items()}
        env.update({k.upper(): v for k, v in _get_vc_env('x86_amd64').items()})
        vs = Path(os.environ.get('ProgramFiles(x86)', 'C:/Program Files (x86)')) / 'Microsoft Visual Studio/2022/BuildTools'
        cmake = vs / 'Common7/IDE/CommonExtensions/Microsoft/CMake'
        env['PATH'] += os.pathsep + str(cmake / 'CMake/bin') + os.pathsep + str(cmake / 'Ninja')
    for key in ('CFLAGS', 'CXXFLAGS', 'LDFLAGS', 'CPATH', 'LIBRARY_PATH', 'CL', '_CL_', 'LINK', '_LINK_'):
        env.pop(key, None)
    return env


def run(command, *, env, log=None):
    command = [str(part) for part in command]
    if log:
        with log.open('a', encoding='utf-8') as out:
            result = subprocess.run(command, env=env, stdout=out, stderr=subprocess.STDOUT)
        if result.returncode:
            print('\n'.join(log.read_text(encoding='utf-8', errors='replace').splitlines()[-45:]), flush=True)
            raise RuntimeError('Build failed; diagnostics: ' + str(log))
        return ''
    return subprocess.check_output(command, env=env, text=True, stderr=subprocess.STDOUT)


def system_dependencies(executable, env):
    """Fail closed if the CLI imports anything beyond the host OS/C++ baseline."""
    if os.name == 'nt':
        dumpbin = shutil.which('dumpbin', path=env['PATH'])
        output = run([dumpbin, '/dependents', executable], env=env)
        names = sorted(set(re.findall(r'^\s+([\w.-]+\.dll)\s*$', output, re.M | re.I)))
        allowed = {'kernel32.dll', 'advapi32.dll', 'ws2_32.dll', 'user32.dll',
                   'shell32.dll', 'ole32.dll', 'bcrypt.dll', 'ntdll.dll'}
        valid = bool(names) and all(n.lower() in allowed or n.lower().startswith('api-ms-win-') for n in names)
    elif sys.platform == 'darwin':
        output = run(['otool', '-L', executable], env=env)
        names = [line.strip().split(' (')[0] for line in output.splitlines()[1:]]
        valid = bool(names) and all(n.startswith(('/usr/lib/', '/System/Library/')) for n in names)
    else:
        output = run(['ldd', executable], env=env)
        names = sorted(set(re.findall(r'^\s*(\S+)', output, re.M)))
        allowed = {'linux-vdso.so.1', 'libstdc++.so.6', 'libgcc_s.so.1',
                   'libc.so.6', 'libm.so.6', 'libpthread.so.0', 'libdl.so.2', 'librt.so.1'}
        valid = bool(names) and 'not found' not in output and all(n in allowed or n.startswith('/lib') and '/ld-linux' in n for n in names)
    if not valid:
        raise ValueError('Unexpected OCR native dependency:\n' + output)
    return names


def collect_source_notices(source, target):
    """Preserve file-level attributions too, including third-party algorithm code.

    Full unmodified archives also accompany the CLI, including upstream notices
    for unbuilt examples. No claim is made that every source file is permissive.
    """
    seen = set()
    notices = []
    for path in sorted(source.rglob('*')):
        relative = path.relative_to(source)
        if not path.is_file() or path.suffix not in {'.c', '.cpp', '.h', '.hpp'}:
            continue
        if relative.parts[0] in {'contrib', 'prog', 'test', 'tests', 'unittest'}:
            continue
        text = path.read_text(encoding='utf-8', errors='replace')
        match = re.match(r'\s*(/\*.*?\*/|(?://[^\n]*\n)+)', text, re.S)
        if match and re.search('copyright|license|permission', match[0], re.I):
            block = match[0].strip()
            if block not in seen:
                notices.append('--- ' + relative.as_posix() + ' ---\n' + block)
                seen.add(block)
    target.write_text('\n\n'.join(notices) + '\n', encoding='utf-8')


def build(output, resume=False, jobs=4):
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=resume)
    payload = output / 'payload'
    if payload.exists():
        raise FileExistsError('A completed/partial OCR payload already exists; choose a new output')
    downloads = output / 'sources'
    downloads.mkdir(exist_ok=resume)
    prefix = output / 'prefix'
    lock = json.loads(LOCK.read_text(encoding='utf-8'))
    env = build_environment()
    cmake = shutil.which('cmake', path=env.get('PATH', env.get('Path', '')))
    if not cmake:
        raise RuntimeError('CMake is required (Visual Studio Build Tools on Windows)')
    generator = 'Ninja' if shutil.which('ninja', path=env.get('PATH', env.get('Path', ''))) else 'Unix Makefiles'
    base = ['-DCMAKE_BUILD_TYPE=Release', '-DBUILD_SHARED_LIBS=OFF',
            '-DCMAKE_POLICY_DEFAULT_CMP0091=NEW', '-DCMAKE_MSVC_RUNTIME_LIBRARY=MultiThreaded',
            '-DCMAKE_INSTALL_PREFIX=' + prefix.as_posix(), '-DCMAKE_INSTALL_LIBDIR=lib',
            '-DCMAKE_PREFIX_PATH=' + prefix.as_posix(), '-DCMAKE_FIND_USE_PACKAGE_REGISTRY=OFF',
            '-DCMAKE_FIND_USE_SYSTEM_PACKAGE_REGISTRY=OFF', '-DCMAKE_DISABLE_FIND_PACKAGE_PkgConfig=TRUE']
    if os.name == 'nt':
        base.append('-DCMAKE_MAKE_PROGRAM=' + shutil.which('ninja', path=env['PATH']).replace('\\', '/'))
        flags = '/experimental:deterministic /pathmap:"' + str(output) + '=/usr/src/myl-ocr"'
    else:
        flags = '-ffile-prefix-map=' + str(output) + '=/usr/src/myl-ocr'
    base += ['-DCMAKE_C_FLAGS=' + flags, '-DCMAKE_CXX_FLAGS=' + flags]
    roots = {}
    commands = []
    for component in lock['components']:
        name = component['id']
        print('Building pinned ' + name + ' ' + component['version'], flush=True)
        archive = downloads / (name + '.tar.gz')
        fetch(component['url'], archive, component['sha256'])
        extracted = output / ('src-' + name)
        source = next(extracted.iterdir()) if resume and extracted.exists() else extract(archive, extracted)
        verify_extracted_source(archive, source)
        roots[name] = source
        build_dir = output / ('build-' + name)
        options = ['-D' + key + '=' + value for key, value in component['options'].items()]
        if name != 'zlib':
            zlib_library = prefix / 'lib' / ('zs.lib' if os.name == 'nt' else 'libz.a')
            options += ['-DZLIB_LIBRARY=' + zlib_library.as_posix(),
                        '-DZLIB_INCLUDE_DIR=' + (prefix / 'include').as_posix()]
        if name in {'leptonica', 'tesseract'}:
            png_library = prefix / 'lib' / ('libpng16_static.lib' if os.name == 'nt' else 'libpng16.a')
            options += ['-DPNG_LIBRARY=' + png_library.as_posix(),
                        '-DPNG_PNG_INCLUDE_DIR=' + (prefix / 'include').as_posix()]
        configure = [cmake, '-S', source, '-B', build_dir, '-G', generator, *base, *options]
        if name == 'tesseract':
            configure += ['-DLeptonica_DIR=' + (prefix / 'lib/cmake/leptonica').as_posix()]
        commands.append([str(arg).replace(str(output), '${BUILD_ROOT}') for arg in configure])
        log = output / (name + '-build.log')
        run(configure, env=env, log=log)
        run([cmake, '--build', build_dir, '--parallel', jobs], env=env, log=log)
        run([cmake, '--install', build_dir], env=env, log=log)
    executable = prefix / 'bin' / ('tesseract.exe' if os.name == 'nt' else 'tesseract')
    dependencies = system_dependencies(executable, env)
    raw = executable.read_bytes()
    for private_path in (str(output), output.as_posix(), str(Path.home()), Path.home().as_posix()):
        if private_path.encode() in raw or private_path.encode('utf-16-le') in raw:
            raise ValueError('Compiler leaked a local profile/build path into the OCR executable')
    if sys.platform == 'darwin':
        run(['codesign', '--force', '--sign', '-', executable], env=env)
    payload.mkdir()
    shutil.copy2(executable, payload / executable.name)
    licenses = payload / 'licenses'
    licenses.mkdir()
    for component in lock['components']:
        name = component['id']
        dest = licenses / name
        dest.mkdir()
        for relative, expected in component['notices'].items():
            notice = roots[name] / relative
            if digest(notice) != expected:
                raise ValueError('Upstream notice changed: ' + name + '/' + relative)
            shutil.copy2(notice, dest / Path(relative).name)
        collect_source_notices(roots[name], dest / 'SOURCE-NOTICES.txt')
    source_dest = payload / 'sources'
    source_dest.mkdir()
    for component in lock['components']:
        shutil.copy2(downloads / (component['id'] + '.tar.gz'), source_dest)
        cache = (output / ('build-' + component['id']) / 'CMakeCache.txt').read_text(encoding='utf-8')
        for path, label in ((output, '${BUILD_ROOT}'), (ROOT, '${PROJECT_ROOT}'), (Path.home(), '${USER_PROFILE}')):
            cache = cache.replace(str(path), label).replace(path.as_posix(), label)
        (source_dest / (component['id'] + '-CMakeCache.txt')).write_text(cache, encoding='utf-8')
    shutil.copy2(LOCK, source_dest / LOCK.name)
    shutil.copy2(Path(__file__), source_dest / Path(__file__).name)
    (source_dest / 'build-commands.json').write_text(json.dumps(commands, indent=2), encoding='utf-8')
    data = payload / 'tessdata'
    data.mkdir()
    for language, expected in lock['models'].items():
        model = ROOT / 'tesseract/tessdata' / (language + '.traineddata')
        if digest(model) != expected:
            raise ValueError('Model hash mismatch: ' + language)
        shutil.copy2(model, data)
    configs = data / 'configs'
    configs.mkdir()
    for config in ('tsv', 'txt'):
        shutil.copy2(roots['tesseract'] / 'tessdata/configs' / config, configs)
    shutil.copy2(roots['tesseract'] / 'LICENSE', licenses / 'TESSDATA-APACHE-2.0.txt')
    (licenses / 'README.txt').write_text(
        'OCR libraries: Tesseract (Apache-2.0), Leptonica (BSD-2-Clause), libpng (libpng-2.0), zlib (Zlib).\n'
        'Models: tessdata_fast (Apache-2.0), exact commit in sources/ocr_source_lock.json.\n'
        'No JBIG-KIT, TIFF, GPL/LGPL OCR library or GCC DLL is linked or copied.\n'
        'Windows is built with the Microsoft C/C++ static runtime (/MT); Microsoft toolchain terms apply.\n'
        'Linux uses the host OS glibc and GCC C++ runtime; these are not copied into this OCR payload.\n'
        'macOS uses the Apple system libraries; these are not copied.\n'
        'Unmodified source archives include separately licensed, unbuilt examples/contrib files.\n'
        'Their notices are preserved; those examples do not form part of the OCR executable.\n', encoding='utf-8')
    cli_env = dict(env, TESSDATA_PREFIX=str(data))
    version = run([executable, '--version'], env=cli_env)
    languages = run([payload / executable.name, '--list-langs'], env=cli_env)
    if not all(lang in languages.splitlines() for lang in lock['models']):
        raise ValueError('Missing OCR language')
    manifest = {'schema': 1, 'profile': lock['profile'], 'platform': sys.platform,
                'architecture': platform.machine(), 'source_lock_sha256': digest(LOCK),
                'components': lock['components'], 'models_commit': lock['models_commit'],
                'system_dependencies': dependencies, 'tesseract_version': version.strip(),
                'license_resolution': 'replaced_legacy_stack_no_gpl_lgpl_ocr_libraries',
                'legacy_artifacts_cleared': False,
                'files': {p.relative_to(payload).as_posix(): digest(p) for p in sorted(payload.rglob('*')) if p.is_file()}}
    (payload / 'native-ocr-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print('Controlled OCR payload: ' + str(payload), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--resume', action='store_true', help='Resume an interrupted build, never an existing payload')
    parser.add_argument('--jobs', type=int, default=4)
    args = parser.parse_args()
    if not 1 <= args.jobs <= 32:
        parser.error('--jobs must be between 1 and 32')
    build(args.output, args.resume, args.jobs)

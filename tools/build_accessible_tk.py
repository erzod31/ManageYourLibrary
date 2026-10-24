"""Build pinned Tcl/Tk 9.1 and CPython's unmodified bridge in an isolated venv.

Only build output and the selected virtual environment are modified. Never
replace the system Python's DLLs or its tkinter module. Native CI runs this on
each architecture; no GUI binaries are committed to Git.
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import sysconfig
import tarfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(command, *, cwd, env):
    command = list(map(str, command))
    command[0] = shutil.which(command[0], path=env.get('PATH')) or command[0]
    print('Building:', ' '.join(map(str, command)), flush=True)
    subprocess.run(command, cwd=cwd, env=env, check=True)


def build(destination, resume=False):
    if sys.prefix == sys.base_prefix:
        raise RuntimeError('Activate a disposable virtual environment first')
    lock = json.loads((ROOT / 'tools/tk_sources.json').read_text())
    if tuple(sys.version_info[:2]) != (3, 12):
        raise RuntimeError('This bridge is pinned to CPython 3.12')
    destination = destination.resolve()
    destination.mkdir(parents=True, exist_ok=resume)
    sources = destination / 'sources'
    sources.mkdir(exist_ok=resume)
    modules = sources / 'Modules'
    modules.mkdir(exist_ok=resume)
    roots = {}
    for source in lock['sources']:
        existing = sources / (source['name'] + '.tar.gz') if source['name'] in ('tcl', 'tk') else modules / source['name']
        if resume:
            raw = existing.read_bytes()
        else:
            with urllib.request.urlopen(source['url'], timeout=120) as response:
                raw = response.read(64 * 1024 * 1024 + 1)
        if len(raw) > 64 * 1024 * 1024 or hashlib.sha256(raw).hexdigest() != source['sha256']:
            raise RuntimeError('Source hash mismatch: ' + source['name'])
        name = source['name']
        if name in ('tcl', 'tk'):
            archive = sources / (name + '.tar.gz')
            archive.write_bytes(raw)
            if not resume:
                with tarfile.open(archive) as stream:
                    stream.extractall(sources, filter='data')
            roots[name] = next(sources.glob(name + '-*'))
            if not roots[name].is_dir():
                raise RuntimeError('Invalid source tree')
            # GitHub tarballs omit Fossil's generated source stamp. Supply the
            # exact upstream tag commit, never a fabricated repository HEAD.
            stamp = roots[name] / 'manifest.uuid'
            if not stamp.exists():
                stamp.write_text('git-' + source['git_commit'] + '\n')
        else:
            target = modules / name
            target.parent.mkdir(exist_ok=True, parents=True)
            if not resume:
                target.write_bytes(raw)
    prefix = destination / 'runtime'
    env = {key.upper(): value for key, value in os.environ.items()} if os.name == 'nt' else dict(os.environ)
    if os.name == 'nt':
        from setuptools._distutils._msvccompiler import _get_vc_env
        env.update({key.upper(): value for key, value in _get_vc_env('x86_amd64').items()})
        for name in ('tcl', 'tk'):
            args = ['nmake', '/nologo', '-f', 'makefile.vc', 'INSTALLDIR=' + str(prefix)]
            if name == 'tk':
                args += ['TCLDIR=' + str(roots['tcl'])]
            run([*args, 'release'], cwd=roots[name] / 'win', env=env)
            run([*args, 'install'], cwd=roots[name] / 'win', env=env)
    else:
        for name in ('tcl', 'tk'):
            work = destination / ('build-' + name)
            work.mkdir(exist_ok=resume)
            # Appended script ZIPs make Mach-O install_name_tool/codesign reject
            # the dylib. Ordinary installed scripts also simplify frozen builds.
            args = [roots[name] / 'unix/configure', '--prefix=' + str(prefix), '--enable-shared', '--disable-zipfs']
            if name == 'tcl':
                args += ['--without-system-libtommath']
            if name == 'tk':
                args += ['--with-tcl=' + str(prefix / 'lib')]
                if sys.platform == 'darwin':
                    args += ['--enable-aqua']
            run(args, cwd=work, env=env)
            run(['make', '-j', str(min(os.cpu_count() or 2, 4))], cwd=work, env=env)
            run(['make', 'install'], cwd=work, env=env)
            # Unix installs may embed the ZIP only in the shared library.
            # CPython and PyInstaller also need ordinary script directories.
            for archive in work.glob('libt*9*.zip'):
                shutil.copy2(archive, prefix / 'lib' / archive.name)
    from setuptools import Distribution, Extension
    lib = prefix / 'lib'
    # Tk 9.1 installs script archives on Unix as well as Windows. Explicit
    # directories also let PyInstaller collect the complete script library.
    for archive in lib.glob('libt*9*.zip'):
        with zipfile.ZipFile(archive) as stream:
            for name in stream.namelist():
                if not (lib / name).resolve().is_relative_to(lib.resolve()):
                    raise RuntimeError('Unsafe runtime ZIP member')
            stream.extractall(lib)
    if os.name == 'nt':
        libraries = [next(p for p in lib.glob(pattern) if 'stub' not in p.name).stem
                     for pattern in ('tcl91.lib', 'tcl9tk91.lib')]
        libraries += ['tommath']
    else:
        # Keep the version's decimal point: libtcl9.1.so -> tcl9.1.
        # libtcl9*.so ALSO matches libtcl9tk9.1.so. Never let directory order
        # choose Tk twice and omit Tcl from the ELF/Mach-O link dependencies.
        libraries = ['tcl9.1', 'tcl9tk9.1']
        suffix = '.dylib' if sys.platform == 'darwin' else '.so'
        for name in libraries:
            if not (lib / ('lib' + name + suffix)).is_file():
                raise FileNotFoundError('Missing exact GUI link library: ' + name)
    extension = Extension('_tkinter', [str(modules / n) for n in ('_tkinter.c', 'tkappinit.c')],
        include_dirs=[str(prefix / 'include'), str(Path(sysconfig.get_path('include')) / 'internal')],
        library_dirs=[str(lib)], libraries=libraries,
        define_macros=[('WITH_APPINIT', '1')] + ([('TCL_WITH_EXTERNAL_TOMMATH', '1')] if os.name == 'nt' else []),
        runtime_library_dirs=[] if os.name == 'nt' else [str(lib)])
    distribution = Distribution({'name': 'myl-accessible-tk', 'ext_modules': [extension]})
    command = distribution.get_command_obj('build_ext')
    bridge = destination / 'bridge'
    bridge.mkdir(exist_ok=resume)
    command.build_lib = str(bridge)
    command.build_temp = str(destination / 'bridge-build')
    command.force = True
    command.ensure_finalized()
    # distutils initializes its compiler from the process environment.
    if os.name == 'nt':
        os.environ.update(env)
    command.run()
    for name, tree in roots.items():
        license_path = next((tree / n for n in ('license.terms', 'license.terms.txt') if (tree / n).is_file()), None)
        if license_path is None:
            raise RuntimeError('Missing upstream license: ' + name)
        notices = prefix / 'licenses' / name
        notices.mkdir(parents=True, exist_ok=resume)
        shutil.copy2(license_path, notices / license_path.name)
    for owner, relative in (('tcl', 'libtommath'), ('tcl', 'compat/zlib'),
                            ('tcl', 'zlib'), ('tcl', 'utf8proc'), ('tk', 'unix/bidi')):
        directory = roots[owner] / relative
        if directory.is_dir():
            for notice in directory.iterdir():
                if notice.is_file() and (notice.name.lower() in {'license', 'license.terms', 'readme', 'copying', 'license.md'}
                                        or notice.name.startswith('LICENSE_')):
                    target = prefix / 'licenses' / relative.replace('/', '-')
                    target.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(notice, target / notice.name)
    # Site .pth files are intentionally confined to this disposable venv.
    bootstrap = bridge / 'myl_tk_runtime_bootstrap.py'
    bootstrap.write_text('import os, sys\n'
        f'sys.path.insert(0, {str(bridge)!r})\n'
        f'os.environ["TCL_LIBRARY"] = {str(lib / ("tcl_library" if (lib / "tcl_library").is_dir() else "tcl9.1"))!r}\n'
        f'os.environ["TK_LIBRARY"] = {str(lib / ("tk_library" if (lib / "tk_library").is_dir() else "tk9.1"))!r}\n'
        + (f'_dll = os.add_dll_directory({str(prefix / "bin")!r})\n' if os.name == 'nt' else ''), encoding='utf-8')
    site = Path(sysconfig.get_path('purelib'))
    activation = site / 'myl_accessible_tk.pth'
    if activation.exists() and (not resume or activation.read_text().splitlines()[0] != str(bridge)):
        raise FileExistsError('Virtual environment already contains a custom Tk activation')
    activation.write_text(str(bridge) + '\nimport myl_tk_runtime_bootstrap\n', encoding='utf-8')
    (destination / 'build-provenance.json').write_text(json.dumps(lock, indent=2))
    if sys.platform.startswith('linux'):
        run(['ldd', next(bridge.glob('_tkinter*.so'))], cwd=ROOT, env=env)
    run([sys.executable, '-B', '-c',
         ('import tkinter as t; r=t.Tk(); print(r.tk.call("package", "present", "Tk")); '
          'assert r.tk.call("info", "commands", "::tk::accessible::set_acc_role"); r.destroy()')], cwd=ROOT, env=env)
    print('Accessible Tk runtime installed in the selected venv.', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--resume', action='store_true', help='Re-use only hash-verified source downloads in a previous build')
    args = parser.parse_args()
    build(args.output, resume=args.resume)

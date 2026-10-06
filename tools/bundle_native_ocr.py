"""Copy native Tesseract, its non-system libraries and five local languages.

Run only on a disposable native build host with distro/Homebrew Tesseract installed.
The generated inventory records the exact bytes, including third-party licenses.
"""
import hashlib
import json
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LANGUAGES = ('eng', 'spa', 'fra', 'nld', 'chi_sim')
LINUX_SYSTEM = re.compile(r'^(?:ld-linux.*|lib(?:c|m|pthread|dl|rt|util|resolv)\.so\..*)$')


def output(*command):
    return subprocess.check_output(command, text=True).strip()


def dependencies(path, system):
    if system == 'linux':
        result = output('ldd', str(path))
        if 'not found' in result:
            raise RuntimeError(f'Missing shared library for {path.name}')
        return {match: Path(match) for match in re.findall(r'(?:=>\s*)?(/[^\s]+)\s+\(', result)
                if not LINUX_SYSTEM.fullmatch(Path(match).name)}
    lines = output('otool', '-L', str(path)).splitlines()[1:]
    paths = [line.strip().split(' (', 1)[0] for line in lines]
    if path.name.endswith('.dylib'):
        paths = paths[1:]  # First entry is the dylib's own install ID.
    rpaths = re.findall(r'cmd LC_RPATH\s+cmdsize \d+\s+path (.*?) \(offset', output('otool', '-l', str(path)))
    result = {}
    for raw in paths:
        if raw.startswith(('/usr/lib/', '/System/Library/')):
            continue
        if raw.startswith('@loader_path/'):
            resolved = path.parent / raw.removeprefix('@loader_path/')
        elif raw.startswith('@rpath/'):
            candidates = [Path(p.replace('@loader_path', str(path.parent))) / raw.removeprefix('@rpath/') for p in rpaths]
            candidates.append(path.parent / raw.removeprefix('@rpath/'))
            resolved = next((p for p in candidates if p.is_file()), None)
        else:
            resolved = Path(raw)
        if resolved is None or not resolved.is_file():
            raise RuntimeError(f'Unresolved Homebrew dependency for {path.name}: {raw}')
        result[raw] = resolved
    return result


def main():
    system = 'macos' if sys.platform == 'darwin' else 'linux'
    if sys.platform not in ('darwin', 'linux'):
        raise SystemExit('Build OCR on macOS or Linux, not via cross-compilation.')
    executable = Path(shutil.which('tesseract') or '')
    if not executable.is_file():
        raise SystemExit('Native Tesseract is required.')
    destination = ROOT / 'platforms' / system / 'tesseract'
    if any(destination.glob('tesseract')) or (destination / 'lib').exists():
        raise SystemExit('Refusing to overwrite an existing native OCR payload.')
    (destination / 'lib').mkdir()
    (destination / 'tessdata').mkdir()
    (destination / 'licenses').mkdir()
    version = output(str(executable), '--version').splitlines()[0]
    queue = [executable]
    copied = {}
    edges = {}
    while queue:
        source = queue.pop(0)
        if str(source) in copied:
            continue
        target = destination / ('tesseract' if source == executable else 'lib/' + source.name)
        if target.exists():
            if target.read_bytes() != source.read_bytes():
                raise RuntimeError('Conflicting library basenames: ' + source.name)
        else:
            shutil.copy2(source.resolve(), target)
        copied[str(source)] = target
        edges[str(source)] = dependencies(source, system)
        queue.extend(dep for dep in edges[str(source)].values() if str(dep) not in copied and dep != source)
    for source, target in copied.items():
        target.chmod(target.stat().st_mode | 0o200)
        if system == 'linux':
            rpath = '$ORIGIN/lib' if target.name == 'tesseract' else '$ORIGIN'
            subprocess.run(['patchelf', '--force-rpath', '--set-rpath', rpath, str(target)], check=True)
        else:
            subprocess.run(['codesign', '--remove-signature', str(target)], check=False, capture_output=True)
            if target.name != 'tesseract':
                subprocess.run(['install_name_tool', '-id', '@loader_path/' + target.name, str(target)], check=True)
            for raw, dep in edges[source].items():
                relative = '@loader_path/' + ('lib/' if target.name == 'tesseract' else '') + dep.name
                subprocess.run(['install_name_tool', '-change', raw, relative, str(target)], check=True)
            subprocess.run(['codesign', '--force', '--sign', '-', str(target)], check=True)
    if system == 'linux':
        tessdata = Path('/usr/share/tesseract-ocr/4.00/tessdata')
        # All dependency copyright files are small; retain distro notices together.
        for copyright_file in Path('/usr/share/doc').glob('*/copyright'):
            shutil.copy2(copyright_file, destination / 'licenses' / (copyright_file.parent.name + '.txt'))
    else:
        prefix = Path(output('brew', '--prefix'))
        tessdata = prefix / 'share' / 'tessdata'
        notices_sources = list(copied) + [str(tessdata / 'eng.traineddata'), str(tessdata / 'spa.traineddata')]
        for source in notices_sources:
            resolved = Path(source).resolve()
            parts = resolved.parts
            if 'Cellar' in parts:
                cell = Path(*parts[:parts.index('Cellar') + 3])
                for notice in cell.rglob('*'):
                    if notice.is_file() and notice.name.lower() in ('license', 'license.txt', 'copying', 'copyright'):
                        label = '-'.join(notice.relative_to(cell).parts)
                        shutil.copy2(notice, destination / 'licenses' / (cell.parent.name + '-' + label))
    for lang in LANGUAGES:
        shutil.copy2(tessdata / (lang + '.traineddata'), destination / 'tessdata')
    # Debian/Homebrew package inventories and licenses identify the upstream sources.
    packages = output('dpkg-query', '-W') if system == 'linux' else output('brew', 'list', '--versions')
    inventory = {
        'tesseract': version, 'system': system, 'architecture': platform.machine(),
        'language_data': list(LANGUAGES), 'package_inventory': packages,
        'files': {p.relative_to(destination).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in sorted(destination.rglob('*')) if p.is_file() and p.name != 'README.md'},
    }
    (destination / 'native-ocr-manifest.json').write_text(json.dumps(inventory, indent=2), encoding='utf-8')
    subprocess.run([str(destination / 'tesseract'), '--list-langs', '--tessdata-dir', str(destination / 'tessdata')], check=True)


if __name__ == '__main__':
    main()

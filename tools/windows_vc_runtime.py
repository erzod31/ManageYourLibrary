"""Select signed x64 VC runtimes from the selected MSVC installation's REDIST.

Read-only: never install a redistributable or search PATH/Windows for DLLs.
Only result['receipt'] is portable; roots/files are local integration handles.
Microsoft licensing eligibility and complete release review are not approved.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

NAMES = ('vcruntime140.dll', 'vcruntime140_1.dll')
AMD64 = 0x8664
REFERENCES = [
    'https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist',
    'https://learn.microsoft.com/en-us/cpp/windows/redistributing-visual-cpp-files',
]


def _version(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d+\.\d+\.\d+(?:\.\d+)?', value):
        raise ValueError('Missing or invalid MSVC runtime/toolset version')
    parts = tuple(map(int, value.split('.')))
    return parts + (0,) * (4 - len(parts))


def _build_environment():
    if os.name != 'nt':
        raise RuntimeError('Selecting an installed Microsoft REDIST requires Windows')
    from setuptools._distutils._msvccompiler import _get_vc_env
    return {key.upper(): value for key, value in _get_vc_env('x86_amd64').items()}


def _metadata(path):
    import pefile
    with pefile.PE(str(path)) as pe:
        version = None
        if getattr(pe, 'VS_FIXEDFILEINFO', None):
            info = pe.VS_FIXEDFILEINFO[0]
            version = '.'.join(map(str, (info.FileVersionMS >> 16, info.FileVersionMS & 65535,
                                        info.FileVersionLS >> 16, info.FileVersionLS & 65535)))
        strings = {key.decode(): value.decode(errors='replace')
                   for group in getattr(pe, 'FileInfo', []) for block in group
                   if block.Key == b'StringFileInfo' for table in block.StringTable
                   for key, value in table.entries.items()}
        return {'version': version, 'machine': pe.FILE_HEADER.Machine,
                'company': strings.get('CompanyName', ''),
                'linker_version': [pe.OPTIONAL_HEADER.MajorLinkerVersion, pe.OPTIONAL_HEADER.MinorLinkerVersion],
                'imports': sorted({item.dll.decode('ascii').lower()
                                   for item in getattr(pe, 'DIRECTORY_ENTRY_IMPORT', [])}
                                  | {item.dll.decode('ascii').lower()
                                     for item in getattr(pe, 'DIRECTORY_ENTRY_DELAY_IMPORT', [])})}


def _authenticode(path):
    # The path is passed as an environment value, never interpolated into code.
    # Use the OS PowerShell location, not a potentially contaminated PATH.
    shell = Path(os.environ.get('SystemRoot', 'C:/Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
    if not shell.is_file():
        raise RuntimeError('Windows Authenticode verifier is unavailable')
    script = ("$ErrorActionPreference='Stop'; "
              "$s=Get-AuthenticodeSignature -LiteralPath $env:MYL_VC_SIGNATURE_FILE; "
              "@{status=$s.Status.ToString();subject=$s.SignerCertificate.Subject;"
              "thumbprint=$s.SignerCertificate.Thumbprint}|ConvertTo-Json -Compress")
    result = subprocess.run([str(shell), '-NoLogo', '-NoProfile', '-NonInteractive', '-Command', script],
                            env={**os.environ, 'MYL_VC_SIGNATURE_FILE': str(path),
                                 # A PowerShell 7 parent can export modules that
                                 # cannot be loaded by Windows PowerShell 5.1.
                                 'PSModulePath': str(shell.parent / 'Modules')},
                            capture_output=True, text=True, check=True, timeout=30,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    return json.loads(result.stdout)


def _file_signature(path):
    stat = path.stat()
    return stat.st_size, stat.st_mtime_ns, stat.st_ino


def _signed_file(path, metadata):
    before = _file_signature(path)
    signature = _authenticode(path)
    if (signature.get('status') != 'Valid'
            or not re.search(r'(?:^|,\s*)O=Microsoft Corporation(?:,|$)', signature.get('subject', ''))):
        raise ValueError('REDIST DLL does not have a valid Microsoft Authenticode signature: ' + path.name)
    with path.open('rb') as handle:
        digest = hashlib.file_digest(handle, 'sha256').hexdigest()
    if _file_signature(path) != before or _metadata(path) != metadata:
        raise ValueError('REDIST DLL changed during verification: ' + path.name)
    return {'sha256': digest, 'bytes': before[0], 'version': metadata['version'],
            'machine': 'AMD64', 'authenticode': signature}


def select_redist():
    """Return local roots/files plus a portable receipt, or fail closed.

    Runtime file versions must be >= VCToolsVersion (not the misleading
    REDIST directory name). Source roots stay inside VC/Redist/MSVC, use the
    desktop x64 CRT directory, and never include debug_nonredist/onecore DLLs.
    """
    env = _build_environment()
    required = _version(env.get('VCTOOLSVERSION', '').strip())
    if required[0] != 14 or env.get('VSCMD_ARG_TGT_ARCH', 'x64').lower() not in {'x64', 'amd64'}:
        raise ValueError('This application requires the MSVC v14 x64 target')
    for key in ('VCINSTALLDIR', 'VCTOOLSINSTALLDIR', 'VCTOOLSREDISTDIR'):
        if not env.get(key):
            raise ValueError('Missing selected compiler metadata: ' + key)
    vc = Path(env['VCINSTALLDIR']).resolve()
    toolset = Path(env['VCTOOLSINSTALLDIR']).resolve()
    if not toolset.is_dir() or not toolset.is_relative_to(vc / 'Tools/MSVC') or _version(toolset.name) != required:
        raise ValueError('Selected toolset is outside its declared Microsoft VC installation')
    redist_root = vc / 'Redist/MSVC'
    declared = Path(env['VCTOOLSREDISTDIR']).resolve()
    if not redist_root.is_dir() or not declared.is_dir() or not declared.is_relative_to(redist_root):
        raise ValueError('Selected MSVC REDIST directory is absent or outside VC/Redist/MSVC')
    candidates = []
    for directory in sorted({declared, *(p.resolve() for p in redist_root.iterdir() if p.is_dir() and not p.is_symlink())}):
        if not directory.is_relative_to(redist_root):
            raise ValueError('MSVC REDIST source escapes its installation')
        for crt in directory.glob('x64/Microsoft.VC*.CRT'):
            if crt.is_symlink() or not re.fullmatch(r'Microsoft\.VC\d+\.CRT', crt.name):
                continue
            files = {name: crt / name for name in NAMES}
            if not all(path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(redist_root)
                       for path in files.values()):
                continue
            metadata = {name: _metadata(path) for name, path in files.items()}
            if any(info['machine'] != AMD64 or info['company'].strip() != 'Microsoft Corporation'
                   for info in metadata.values()):
                raise ValueError('MSVC REDIST directory contains a wrong architecture or publisher')
            versions = [_version(info['version']) for info in metadata.values()]
            if min(versions) >= required and len(set(versions)) == 1:
                candidates.append((min(versions), crt, files, metadata))
    if not candidates:
        raise ValueError('No signed-source x64 REDIST with runtime version >= selected VCToolsVersion '
                         + env['VCTOOLSVERSION'] + '; install/review the matching Build Tools component separately')
    _release, crt, files, metadata = max(candidates, key=lambda item: (item[0], str(item[1])))
    records = {}
    for name, path in files.items():
        records[name] = {**_signed_file(path, metadata[name]),
                         'source_relative_to_vc': path.relative_to(vc).as_posix()}
    receipt = {'schema': 1, 'family': 'microsoft-msvc-redist', 'architecture': 'AMD64',
               'compiler_toolset_version': env['VCTOOLSVERSION'],
               'selection_rule': 'runtime_file_version_at_least_selected_VCToolsVersion; signed desktop x64 REDIST only',
               'files': records, 'license': 'Microsoft Distributable Code; not MIT',
               'license_eligibility': 'not_determined', 'global_release_approval': False,
               'references': REFERENCES}
    return {'roots': {'vc': vc, 'toolset': toolset, 'redist': declared, 'crt': crt},
            'files': files, 'receipt': receipt}


def validate_binary_toolsets(selection, binaries):
    """Additional PE-linker/import check, not proof of every compiler switch.

    Compare native Tcl/Tk/bridge linker major/minor with the selected runtime.
    Full build version evidence comes from the toolset selection, not the PE
    linker fields, which do not encode the complete compiler build number.
    """
    runtime = min(_version(value['version']) for value in selection['receipt']['files'].values())
    result = {}
    for path in map(Path, binaries):
        info = _metadata(path)
        linker = tuple(info['linker_version'])
        if info['machine'] != AMD64 or (linker[0] == 14 and runtime[:2] < linker):
            raise ValueError('Selected REDIST is below a native binary linker/architecture requirement: ' + path.name)
        unsupported = [name for name in info['imports']
                       if re.match(r'(?:vcruntime|msvcp|msvcr)\d', name) and name not in NAMES]
        if unsupported:
            raise ValueError('Additional Microsoft runtime family needs explicit review: ' + ', '.join(unsupported))
        result[path.name] = {'linker_version': list(linker),
                             'selected_v14_runtime_not_older_than_linker': linker[0] == 14 and runtime[:2] >= linker,
                             'runtime_imports': [name for name in info['imports'] if name in NAMES]}
    return result


def verify_payload(folder):
    """Verify unchanged bytes against the build's signed REDIST selection.

    Authenticode is NOT rerun here: its build-time result is retained in the
    hash-bound receipt. This is not independent authentication of the receipt,
    signing of the application, or approval of Microsoft licensing eligibility.
    """
    folder = Path(folder).resolve()
    provenance = json.loads((folder / '_internal/licenses/windows-dependency-provenance.json').read_text(encoding='utf-8'))
    receipt = provenance.get('msvc_redist', {})
    if (receipt.get('schema') != 1 or receipt.get('family') != 'microsoft-msvc-redist'
            or receipt.get('architecture') != 'AMD64' or set(receipt.get('files', {})) != set(NAMES)
            or receipt.get('global_release_approval') is not False):
        raise ValueError('Missing or unsupported Microsoft REDIST build receipt')
    minimum = _version(receipt.get('compiler_toolset_version'))
    if minimum[0] != 14:
        raise ValueError('Unsupported Microsoft compiler toolset family')
    internal = folder / '_internal'
    candidates = {name: [p for p in internal.iterdir() if p.name.casefold() == name] for name in NAMES}
    rows = provenance.get('files', [])
    checked = {}
    for name in NAMES:
        source = receipt['files'][name]
        recorded_version = _version(source.get('version'))
        signature = source.get('authenticode', {})
        origin_pattern = r'Redist/MSVC/[^/]+/x64/Microsoft\.VC\d+\.CRT/' + re.escape(name)
        if (recorded_version < minimum or source.get('machine') != 'AMD64'
                or type(source.get('bytes')) is not int or source['bytes'] <= 0
                or not re.fullmatch('[0-9a-f]{64}', source.get('sha256', ''))
                or not re.fullmatch(origin_pattern, source.get('source_relative_to_vc', ''), re.I)
                or signature.get('status') != 'Valid'
                or not re.search(r'(?:^|,\s*)O=Microsoft Corporation(?:,|$)', signature.get('subject', ''))):
            raise ValueError('Incomplete, old, or untrusted-build Microsoft REDIST record: ' + name)
        origin_rows = [row for row in rows
                       if str(row.get('path', '')).replace('\\', '/').casefold() == '_internal/' + name]
        if (len(origin_rows) != 1 or origin_rows[0].get('sha256') != source['sha256']
                or origin_rows[0].get('origin', {}).get('root') != 'microsoft_redist'
                or str(origin_rows[0].get('origin', {}).get('relative', '')).casefold() != name):
            raise ValueError('Microsoft REDIST native origin differs from its selected source: ' + name)
        if len(candidates[name]) != 1:
            raise ValueError('Missing or repeated Microsoft REDIST payload file: ' + name)
        path = candidates[name][0]
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(folder):
            raise ValueError('Unsafe Microsoft REDIST payload file: ' + name)
        if path.stat().st_size != source['bytes']:
            raise ValueError('Microsoft REDIST payload size differs from its build receipt: ' + name)
        with path.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        info = _metadata(path)
        if (digest != source['sha256'] or info['machine'] != AMD64
                or _version(info['version']) != recorded_version
                or info['company'].strip() != 'Microsoft Corporation'):
            raise ValueError('Microsoft REDIST payload bytes/version differ from its build receipt: ' + name)
        checked[name] = {'sha256': digest, 'bytes': source['bytes'], 'version': source['version']}
    return {'passed': True, 'files': checked, 'compiler_toolset_version': receipt['compiler_toolset_version'],
            'scope': 'unchanged PE bytes/version/origin bound to build-time Microsoft Authenticode result; '
                     'signature not rerun, receipt/application not independently authenticated, no license approval'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--receipt', type=Path)
    parser.add_argument('--binary', type=Path, action='append', default=[])
    args = parser.parse_args()
    selected = select_redist()
    receipt = selected['receipt']
    if args.binary:
        receipt['native_linker_checks'] = validate_binary_toolsets(selected, args.binary)
    if args.receipt:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        with args.receipt.open('x', encoding='utf-8') as output:
            json.dump(receipt, output, indent=2)
            output.write('\n')
    print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    main()

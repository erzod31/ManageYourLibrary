from pathlib import Path
import sys
import os

from PyInstaller.utils.hooks import collect_all, copy_metadata
from PyInstaller.config import CONF


ROOT = Path.cwd()
sys.path.insert(0, str(ROOT))
from tools.verify_ocr_payload import validate_payload
from tools.windows_dependency_policy import select_inputs
from tools.windows_vc_runtime import select_redist, validate_binary_toolsets

OCR = Path(os.environ.get('MANAGE_YOUR_LIBRARY_OCR_DIR', str(ROOT / 'dist/ocr/payload'))).resolve()
validate_payload(OCR)
datas = [
    (str(ROOT / "app_icon.ico"), "."),
    (str(ROOT / "VERSION"), "."),
    (str(ROOT / "LICENSE"), "."),
    (str(ROOT / "THIRD_PARTY_NOTICES.md"), "."),
    (str(Path(sys.base_prefix) / "LICENSE.txt"), "licenses/python"),
    (str(ROOT / "data"), "data"),
    (str(OCR), "tesseract"),
]
for setting, destination in (('MANAGE_YOUR_LIBRARY_PYTHON_LICENSE_DIR', 'licenses/python-runtime'),
                             ('MANAGE_YOUR_LIBRARY_WHEEL_LICENSE_DIR', 'licenses/wheels')):
    evidence = Path(os.environ.get(setting, ''))
    if not os.environ.get(setting) or not (evidence / 'receipt.json').is_file():
        raise ValueError('Collect verified license evidence before building: ' + setting)
    datas += [(str(evidence), destination)]
binaries = []
if not os.environ.get('TK_LIBRARY') or not os.environ.get('TCL_LIBRARY'):
    raise ValueError('Use the verified isolated GUI runtime through BUILD_WINDOWS.bat')
if os.environ.get('TK_LIBRARY'):
    # Tk 9.1's Windows library is extracted from its embedded ZIP by the
    # reproducible GUI builder; collect that exact directory, not an old guess.
    datas += [(os.environ['TK_LIBRARY'], '_tk_data')]
    if os.environ.get('TCL_LIBRARY'):
        datas += [(os.environ['TCL_LIBRARY'], '_tcl_data')]
    gui_prefix = Path(os.environ['TK_LIBRARY']).parent.parent
    # CPython's custom bridge does not live alongside these DLLs. The generic
    # hook cannot infer this private runtime from the system Python directory.
    gui_bin = gui_prefix / 'bin'
    binaries += [(str(path), '.') for path in sorted(gui_bin.glob('*.dll'))]
    gui_licenses = Path(os.environ['TK_LIBRARY']).parent.parent / 'licenses'
    if gui_licenses.is_dir():
        datas += [(str(gui_licenses), 'licenses/tcltk')]
hiddenimports = ["pypdf", "pypdfium2", "PIL", "ftfy"]
for package in ("Pillow", "pypdf", "wcwidth", "pyinstaller", "pefile"):
    datas += copy_metadata(package)
for package in ("pypdfium2", "ftfy"):
    package_datas, package_binaries, package_hidden = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hidden

a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=[
        # Source-only provenance imports must not bundle setuptools/build tools
        # in the app. Frozen API checks hash sys.executable without Git.
        'tools.write_build_manifest',
        "pandas", "pyarrow", "scipy", "sklearn", "matplotlib", "torch",
        "tensorflow", "transformers", "datasets", "numpy", "Crypto",
        "psutil", "fontTools", "yaml", "charset_normalizer",
    ],
    noarchive=False,
)
import _tkinter
selected_crt = select_redist()
selected_crt['receipt']['native_linker_checks'] = validate_binary_toolsets(
    selected_crt, [*gui_bin.glob('*.dll'), Path(_tkinter.__file__).resolve()])
# The Python distribution's CRT can be older than the compiler used for Tk.
# Replace only these explicit targets with the signed toolchain REDIST files.
a.binaries = [item for item in a.binaries if Path(item[0]).name.casefold() not in selected_crt['files']]
a.datas = [item for item in a.datas if Path(item[0]).name.casefold() not in selected_crt['files']]
a.binaries += [(name, str(path), 'BINARY') for name, path in selected_crt['files'].items()]
controlled_roots = {
    'python': Path(sys.base_prefix),
    'python_wheels': Path(sys.prefix) / 'Lib/site-packages',
    'gui_runtime': gui_bin,
    'gui_bridge': Path(_tkinter.__file__).resolve().parent,
    'controlled_ocr': OCR,
    'microsoft_redist': selected_crt['roots']['crt'],
}
a.binaries, a.datas, native_inputs = select_inputs(a.binaries, a.datas, roots=controlled_roots)
native_inputs['msvc_redist'] = selected_crt['receipt']
# Keep hashes of the selected bytes, not personal absolute build paths. This
# deliberately excludes application-local UCRT/API-set copies on Windows 10+.
import json
native_receipt = Path(CONF['workpath']) / 'windows-dependency-provenance.json'
native_receipt.write_text(json.dumps(native_inputs, indent=2) + '\n', encoding='utf-8')
a.datas += [('licenses/windows-dependency-provenance.json', str(native_receipt), 'DATA')]
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ManageYourLibrary",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(ROOT / "app_icon.ico"),
    version=str(ROOT / "platforms" / "windows" / "version_info.txt"),
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="ManageYourLibrary",
)

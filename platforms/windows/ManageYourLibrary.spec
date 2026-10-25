from pathlib import Path
import sys
import os

from PyInstaller.utils.hooks import collect_all, copy_metadata


ROOT = Path.cwd()
sys.path.insert(0, str(ROOT))
from tools.verify_ocr_payload import validate_payload

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
binaries = []
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
for package in ("Pillow", "pypdf", "wcwidth", "pyinstaller"):
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
        "pandas", "pyarrow", "scipy", "sklearn", "matplotlib", "torch",
        "tensorflow", "transformers", "datasets", "numpy", "Crypto",
        "psutil", "fontTools", "yaml", "charset_normalizer",
    ],
    noarchive=False,
)
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
    upx=True,
    console=False,
    icon=str(ROOT / "app_icon.ico"),
    version=str(ROOT / "platforms" / "windows" / "version_info.txt"),
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    name="ManageYourLibrary",
)

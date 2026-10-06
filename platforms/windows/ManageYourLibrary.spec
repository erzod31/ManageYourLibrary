from pathlib import Path

from PyInstaller.utils.hooks import collect_all


ROOT = Path.cwd()
datas = [
    (str(ROOT / "app_icon.ico"), "."),
    (str(ROOT / "VERSION"), "."),
    (str(ROOT / "data"), "data"),
    (str(ROOT / "tesseract"), "tesseract"),
]
binaries = []
hiddenimports = ["pypdf", "pypdfium2", "PIL", "ftfy"]
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

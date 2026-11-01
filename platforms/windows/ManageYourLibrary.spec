from pathlib import Path
import sys

from PyInstaller.utils.hooks import collect_all, collect_data_files, copy_metadata
from tools.write_update_identity import write as write_update_identity


ROOT = Path.cwd()
update_identity = write_update_identity(ROOT / "dist/build-inputs/windows/update-identity.json", "windows-portable-x64")
datas = [
    (str(ROOT / "app_icon.ico"), "."),
    (str(ROOT / "VERSION"), "."),
    (str(ROOT / "LICENSE"), "."),
    (str(ROOT / "THIRD_PARTY_NOTICES.md"), "."),
    (str(update_identity), "."),
    (str(ROOT / "platforms/windows/APPLY_PORTABLE_UPDATE.ps1"), "platforms/windows"),
    (str(ROOT / "data"), "data"),
    (str(ROOT / "ocr_models" / "indra"), "ocr_models/indra"),
    (str(ROOT / "third_party"), "third_party"),
]
android_apk = ROOT / "dist" / "android" / f"ManageYourLibrary-{(ROOT / 'VERSION').read_text(encoding='utf-8').strip()}.apk"
if not android_apk.is_file():
    raise SystemExit("Build the matching signed companion with platforms/android/BUILD_ANDROID.ps1 first")
datas.append((str(android_apk), "android"))
android_info = android_apk.with_suffix(".update.json")
if not android_info.is_file():
    raise SystemExit("The matching Android update metadata is missing; rebuild the signed APK first")
datas.append((str(android_info), "android"))
binaries = []
hiddenimports = ["pypdf", "pypdfium2", "PIL", "ftfy", "indra_ocr", "cv2", "onnxruntime", "numpy"]
for package in ("pypdfium2", "ftfy"):
    package_datas, package_binaries, package_hidden = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hidden
for distribution in ("indra-ocr", "onnxruntime", "opencv-python-headless", "numpy", "Pillow", "pypdf", "pypdfium2", "ftfy"):
    datas += copy_metadata(distribution)
datas += collect_data_files("onnxruntime", includes=["LICENSE", "ThirdPartyNotices.txt"])
datas.append((str(Path(sys.base_prefix) / "LICENSE.txt"), "third_party/python"))
for runtime in ("tcl8.6", "tk8.6"):
    notice = Path(sys.base_prefix) / "tcl" / runtime / "license.terms"
    if notice.is_file():
        datas.append((str(notice), f"third_party/{runtime}"))

a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=[
        "pandas", "pyarrow", "scipy", "sklearn", "matplotlib", "torch",
        "tensorflow", "transformers", "datasets", "Crypto",
        "psutil", "fontTools", "yaml", "charset_normalizer",
        "huggingface_hub", "hf_xet", "onnxruntime.tools", "onnxruntime.quantization",
    ],
    noarchive=False,
)
# VideoIO's optional FFmpeg plugin is not imported by cv2.pyd or used by Indra.
# Keep the CPU image-processing module; omit the 30 MB video-only plugin.
a.binaries = [item for item in a.binaries if not Path(item[0]).name.lower().startswith("opencv_videoio_ffmpeg")]
a.datas = [item for item in a.datas if not Path(item[0]).name.lower().startswith("opencv_videoio_ffmpeg")]
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

"""Native macOS entry used by build_macos.sh; preserves the published bundle ID."""
import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_data_files, copy_metadata
from tools.write_update_identity import write as write_update_identity
from core.app_updates import MAC_BUNDLE_ID

ROOT = Path.cwd()
VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
import platform
arch = "arm64" if platform.machine().lower() in {"arm64", "aarch64"} else "x64"
identity = write_update_identity(ROOT / "dist/build-inputs/macos/update-identity.json", "macos-" + arch)
apk = ROOT / "dist/android" / f"ManageYourLibrary-{VERSION}.apk"
if not apk.is_file() or not apk.with_suffix(".update.json").is_file():
    raise SystemExit("Copy the matching signed Android APK and update metadata into dist/android first")
datas = [(str(ROOT / "VERSION"), "."), (str(ROOT / "LICENSE"), "."),
    (str(ROOT / "THIRD_PARTY_NOTICES.md"), "."), (str(identity), "."),
    (str(ROOT / "app_icon.ico"), "."), (str(ROOT / "data"), "data"),
    (str(ROOT / "ocr_models/indra"), "ocr_models/indra"), (str(ROOT / "third_party"), "third_party"),
    (str(apk), "android"), (str(apk.with_suffix(".update.json")), "android")]
binaries, hiddenimports = [], ["indra_ocr", "onnxruntime", "cv2", "numpy", "pypdf", "PIL", "PIL._tkinter_finder", "pypdfium2", "ftfy"]
for package in ("pypdfium2", "ftfy"):
    package_datas, package_binaries, package_hidden = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hidden
for distribution in ("indra-ocr", "onnxruntime", "opencv-python-headless", "numpy", "Pillow", "pypdf", "pypdfium2", "ftfy"):
    datas += copy_metadata(distribution)
datas += collect_data_files("onnxruntime", includes=["LICENSE", "ThirdPartyNotices.txt"])
signer = os.environ.get("MANAGE_YOUR_LIBRARY_CODESIGN_IDENTITY") or None
a = Analysis([str(ROOT / "main.py")], pathex=[str(ROOT)], binaries=binaries, datas=datas,
    hiddenimports=hiddenimports, excludes=["pandas", "pyarrow", "scipy", "sklearn", "matplotlib", "torch", "tensorflow",
    "transformers", "datasets", "huggingface_hub", "hf_xet", "onnxruntime.tools", "onnxruntime.quantization"], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="ManageYourLibrary", debug=False, strip=False,
    upx=False, console=False, target_arch="arm64" if arch == "arm64" else "x86_64",
    codesign_identity=signer, entitlements_file=None)
coll = COLLECT(exe, a.binaries, a.datas, name="ManageYourLibrary", strip=False, upx=False)
app = BUNDLE(coll, name="ManageYourLibrary.app", bundle_identifier=MAC_BUNDLE_ID,
    codesign_identity=signer, entitlements_file=None,
    info_plist={"CFBundleIdentifier": MAC_BUNDLE_ID, "CFBundleShortVersionString": VERSION,
                "CFBundleVersion": VERSION, "NSHighResolutionCapable": True})

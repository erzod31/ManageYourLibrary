#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

echo "=================================================="
echo "Manage Your Library - Linux build"
echo "=================================================="

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 was not found."
  exit 1
fi

python3 -c 'import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) else 1)' || {
  echo "The release build requires Python 3.12."
  exit 1
}

python3 -m pip install -r "$ROOT/requirements-build.txt"
python3 tools/prepare_indra_models.py
python3 -m unittest discover -s tests -v
python3 main.py --smoke-test
python3 tools/benchmark_catalog.py --check

WORK="$(mktemp -d "${TMPDIR:-/tmp}/ManageYourLibrary_linux_XXXXXX")"
if [ -e "$ROOT/dist/linux" ]; then
  ARCHIVE="$ROOT/dist/archive/linux-before-$(date +%Y%m%d-%H%M%S)-$$"
  mkdir -p "$ROOT/dist/archive"
  mv "$ROOT/dist/linux" "$ARCHIVE"
fi
mkdir -p "$ROOT/dist/linux"
VERSION="$(tr -d '\r\n' < VERSION)"
APK="$ROOT/dist/android/ManageYourLibrary-$VERSION.apk"
test -f "$APK" && test -f "${APK%.apk}.update.json" || { echo "Prepare the matching signed Android bundle first"; exit 1; }
python3 tools/write_update_identity.py "$WORK/update-identity.json" --platform linux

python3 -m PyInstaller \
  --clean \
  --noconfirm \
  --onedir \
  --windowed \
  --workpath "$WORK/build" \
  --specpath "$WORK" \
  --distpath "$ROOT/dist/linux" \
  --add-data "$ROOT/app_icon.ico:." \
  --add-data "$ROOT/VERSION:." \
  --add-data "$ROOT/LICENSE:." \
  --add-data "$ROOT/THIRD_PARTY_NOTICES.md:." \
  --add-data "$WORK/update-identity.json:." \
  --add-data "$APK:android" \
  --add-data "${APK%.apk}.update.json:android" \
  --add-data "$ROOT/data:data" \
  --add-data "$ROOT/ocr_models/indra:ocr_models/indra" \
  --add-data "$ROOT/third_party:third_party" \
  --hidden-import indra_ocr \
  --hidden-import onnxruntime \
  --hidden-import cv2 \
  --hidden-import numpy \
  --exclude-module huggingface_hub \
  --exclude-module hf_xet \
  --copy-metadata indra-ocr \
  --copy-metadata onnxruntime \
  --copy-metadata opencv-python-headless \
  --copy-metadata numpy \
  --copy-metadata Pillow \
  --copy-metadata pypdf \
  --copy-metadata pypdfium2 \
  --copy-metadata ftfy \
  --collect-all pypdfium2 \
  --collect-all ftfy \
  --exclude-module pandas \
  --exclude-module pyarrow \
  --exclude-module scipy \
  --exclude-module sklearn \
  --exclude-module matplotlib \
  --exclude-module torch \
  --exclude-module tensorflow \
  --exclude-module transformers \
  --exclude-module datasets \
  --hidden-import pypdf \
  --hidden-import pypdfium2 \
  --hidden-import PIL \
  --hidden-import PIL._tkinter_finder \
  --hidden-import ftfy \
  --name ManageYourLibrary \
  main.py

"$ROOT/dist/linux/ManageYourLibrary/ManageYourLibrary" --smoke-test
"$ROOT/dist/linux/ManageYourLibrary/ManageYourLibrary" --runtime-self-test "$WORK/runtime-self-test.json"
"$ROOT/dist/linux/ManageYourLibrary/ManageYourLibrary" --first-use-self-test "$WORK/first-use-self-test.json"
"$ROOT/dist/linux/ManageYourLibrary/ManageYourLibrary" --mobile-self-test "$WORK/mobile-self-test.json"
"$ROOT/dist/linux/ManageYourLibrary/ManageYourLibrary" --update-self-test "$WORK/update-self-test.json"
python3 tools/write_build_manifest.py "$ROOT/dist/linux/ManageYourLibrary/ManageYourLibrary" --platform linux --validated-release-gates --validated-runtime --validated-first-use --validated-mobile --validated-updater
python3 tools/package_native_release.py --platform linux

echo
echo "DONE"
echo "Output: $ROOT/dist/linux/ManageYourLibrary/"

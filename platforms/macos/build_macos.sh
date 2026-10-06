#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

echo "=================================================="
echo "Manage Your Library - macOS build"
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
python3 -m unittest discover -s tests -v
python3 main.py --smoke-test
python3 tools/benchmark_catalog.py --check

rm -rf "$ROOT/dist/macos" "${TMPDIR:-/tmp}/ManageYourLibrary_pyinstaller_macos"
mkdir -p "$ROOT/dist/macos"

ICON_ARGS=()
if [ -f "$ROOT/app_icon.icns" ]; then
  ICON_ARGS+=(--icon "$ROOT/app_icon.icns")
fi

TESSERACT_ARGS=()
if [ -x "$ROOT/platforms/macos/tesseract/tesseract" ]; then
  TESSERACT_ARGS+=(--add-data "$ROOT/platforms/macos/tesseract:tesseract")
  echo "Bundled macOS Tesseract found: platforms/macos/tesseract/tesseract"
elif [ -x "$ROOT/platforms/macos/tesseract/bin/tesseract" ]; then
  TESSERACT_ARGS+=(--add-data "$ROOT/platforms/macos/tesseract:tesseract")
  echo "Bundled macOS Tesseract found: platforms/macos/tesseract/bin/tesseract"
else
  if [ "${MANAGE_YOUR_LIBRARY_ALLOW_SYSTEM_TESSERACT:-}" = "1" ]; then
    echo "WARNING: No bundled macOS Tesseract runtime found."
    echo "OCR will require tesseract to be installed on PATH on the target computer."
  else
    echo "ERROR: macOS Tesseract runtime was not found."
    echo "Put a native macOS runtime in platforms/macos/tesseract/ before building a release."
    echo "For development-only builds, set MANAGE_YOUR_LIBRARY_ALLOW_SYSTEM_TESSERACT=1."
    exit 1
  fi
fi

if [ "${#TESSERACT_ARGS[@]}" -gt 0 ]; then
  for lang in eng spa fra chi_sim; do
    if [ ! -f "$ROOT/platforms/macos/tesseract/tessdata/${lang}.traineddata" ] && [ ! -f "$ROOT/platforms/macos/tesseract/share/tessdata/${lang}.traineddata" ]; then
      echo "ERROR: macOS Tesseract language data is incomplete."
      echo "Missing: ${lang}.traineddata"
      exit 1
    fi
  done
fi

python3 -m PyInstaller \
  --clean \
  --noconfirm \
  --onedir \
  --windowed \
  --workpath "${TMPDIR:-/tmp}/ManageYourLibrary_pyinstaller_macos/build" \
  --specpath "${TMPDIR:-/tmp}/ManageYourLibrary_pyinstaller_macos" \
  --distpath "$ROOT/dist/macos" \
  "${ICON_ARGS[@]}" \
  --add-data "$ROOT/app_icon.ico:." \
  --add-data "$ROOT/VERSION:." \
  "${TESSERACT_ARGS[@]}" \
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
  --hidden-import ftfy \
  --name ManageYourLibrary \
  main.py

rm -f "${TMPDIR:-/tmp}/ManageYourLibrary_pyinstaller_macos/ManageYourLibrary.spec"

"$ROOT/dist/macos/ManageYourLibrary.app/Contents/MacOS/ManageYourLibrary" --smoke-test
python3 tools/write_build_manifest.py "$ROOT/dist/macos/ManageYourLibrary.app/Contents/MacOS/ManageYourLibrary" --platform macos --validated-release-gates

echo
echo "DONE"
echo "Output: $ROOT/dist/macos/ManageYourLibrary.app"

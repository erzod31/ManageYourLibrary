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
python3 -m unittest discover -s tests -v
python3 main.py --smoke-test
python3 tools/benchmark_catalog.py --check

rm -rf "$ROOT/dist/linux" "${TMPDIR:-/tmp}/ManageYourLibrary_pyinstaller_linux"
mkdir -p "$ROOT/dist/linux"

TESSERACT_ARGS=()
if [ -x "$ROOT/platforms/linux/tesseract/tesseract" ]; then
  TESSERACT_ARGS+=(--add-data "$ROOT/platforms/linux/tesseract:tesseract")
  echo "Bundled Linux Tesseract found: platforms/linux/tesseract/tesseract"
elif [ -x "$ROOT/platforms/linux/tesseract/bin/tesseract" ]; then
  TESSERACT_ARGS+=(--add-data "$ROOT/platforms/linux/tesseract:tesseract")
  echo "Bundled Linux Tesseract found: platforms/linux/tesseract/bin/tesseract"
else
  if [ "${MANAGE_YOUR_LIBRARY_ALLOW_SYSTEM_TESSERACT:-}" = "1" ]; then
    echo "WARNING: No bundled Linux Tesseract runtime found."
    echo "OCR will require tesseract to be installed on PATH on the target computer."
  else
    echo "ERROR: Linux Tesseract runtime was not found."
    echo "Put a native Linux runtime in platforms/linux/tesseract/ before building a release."
    echo "For development-only builds, set MANAGE_YOUR_LIBRARY_ALLOW_SYSTEM_TESSERACT=1."
    exit 1
  fi
fi

if [ "${#TESSERACT_ARGS[@]}" -gt 0 ]; then
  for lang in eng spa fra chi_sim; do
    if [ ! -f "$ROOT/platforms/linux/tesseract/tessdata/${lang}.traineddata" ] && [ ! -f "$ROOT/platforms/linux/tesseract/share/tessdata/${lang}.traineddata" ]; then
      echo "ERROR: Linux Tesseract language data is incomplete."
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
  --workpath "${TMPDIR:-/tmp}/ManageYourLibrary_pyinstaller_linux/build" \
  --specpath "${TMPDIR:-/tmp}/ManageYourLibrary_pyinstaller_linux" \
  --distpath "$ROOT/dist/linux" \
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

rm -f "${TMPDIR:-/tmp}/ManageYourLibrary_pyinstaller_linux/ManageYourLibrary.spec"

"$ROOT/dist/linux/ManageYourLibrary/ManageYourLibrary" --smoke-test
python3 tools/write_build_manifest.py "$ROOT/dist/linux/ManageYourLibrary/ManageYourLibrary" --platform linux --validated-release-gates

echo
echo "DONE"
echo "Output: $ROOT/dist/linux/ManageYourLibrary/"

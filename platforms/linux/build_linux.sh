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

if [ -f "$ROOT/dist/native-dependencies/requirements.lock" ]; then
  python3 -m pip install --no-index --find-links "$ROOT/dist/native-dependencies" --require-hashes -r "$ROOT/dist/native-dependencies/requirements.lock"
else
  python3 -m pip install -r "$ROOT/requirements-build.txt"
fi
python3 -m unittest discover -s tests -v
python3 main.py --smoke-test
python3 tools/benchmark_catalog.py --check

if [ -e "$ROOT/dist/linux" ]; then
  echo "Refusing to overwrite an existing build. Use a clean checkout."
  exit 1
fi
BUILD_TEMP="$(mktemp -d "${TMPDIR:-/tmp}/myl-linux.XXXXXX")"
trap 'rm -rf -- "$BUILD_TEMP"' EXIT
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
  for lang in eng spa fra nld chi_sim; do
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
  --workpath "$BUILD_TEMP/build" \
  --specpath "$BUILD_TEMP" \
  --distpath "$ROOT/dist/linux" \
  --add-data "$ROOT/app_icon.ico:." \
  --add-data "$ROOT/VERSION:." \
  --add-data "$ROOT/data:data" \
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

"$ROOT/dist/linux/ManageYourLibrary/ManageYourLibrary" --smoke-test
"$ROOT/dist/linux/ManageYourLibrary/ManageYourLibrary" --runtime-self-test "$ROOT/dist/linux/ManageYourLibrary/runtime-self-test.json"
"$ROOT/dist/linux/ManageYourLibrary/ManageYourLibrary" --first-use-self-test "$ROOT/dist/linux/ManageYourLibrary/first-use-self-test.json"
python3 tools/write_build_manifest.py "$ROOT/dist/linux/ManageYourLibrary/ManageYourLibrary" --platform linux --validated-release-gates --validated-runtime --validated-first-use

echo
echo "DONE"
echo "Output: $ROOT/dist/linux/ManageYourLibrary/"

#!/usr/bin/env bash
set -euo pipefail
test "$(uname -s)" = Darwin && test "$(uname -m)" = x86_64
test "${MYL_EXPECTED_ARCH:-}" = x64 && test -n "${RUNNER_TEMP:-}" && test -n "${GITHUB_ENV:-}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
OWNED="$(mktemp -d "$RUNNER_TEMP/myl-ort-x64-XXXXXXXX")"
EVIDENCE="$ROOT/dist/onnx-macos-x64"
mkdir -p "$EVIDENCE"
mkdir -p "$OWNED/official-wheels"
if python3 -m pip download --only-binary=:all: --no-deps 'onnxruntime==1.31.1' --dest "$OWNED/official-wheels"; then
  printf 'MYL_NATIVE_EXTRA_WHEELS=%s\n' "$OWNED/official-wheels" >> "$GITHUB_ENV"
  echo 'Exact official x64 wheel now available; no source compilation needed.'
  exit 0
fi
# Keep the same current runtime; do not silently fall back to the older Intel wheel.
mkdir -p "$OWNED/bootstrap-wheels"
python3 -m pip download --only-binary=:all: --dest "$OWNED/bootstrap-wheels" \
  'setuptools==84.2.1' 'wheel' 'packaging==26.3' 'numpy==2.5.4'
MYL_ORT_BOOTSTRAP="$OWNED/bootstrap-wheels" MYL_ORT_EVIDENCE="$EVIDENCE" python3 - <<'PY'
import json,os
from pathlib import Path
from tools.lock_native_wheels import wheel_record
wheels=Path(os.environ['MYL_ORT_BOOTSTRAP']);out=Path(os.environ['MYL_ORT_EVIDENCE'])
records=[wheel_record(p) for p in sorted(wheels.glob('*.whl'))]
(out/'bootstrap.lock').write_text(''.join(f"{r['name']}=={r['version']} --hash=sha256:{r['sha256']}\n" for r in records))
(out/'bootstrap-provenance.json').write_text(json.dumps(records,indent=2))
PY
python3 -m pip install --no-index --find-links "$OWNED/bootstrap-wheels" --require-hashes -r "$EVIDENCE/bootstrap.lock"
SOURCE_SHA=6af1a932e2286d5c58166085d24c68783033edee
git init "$OWNED/source"
git -C "$OWNED/source" remote add origin https://github.com/microsoft/onnxruntime.git
git -C "$OWNED/source" fetch --depth 1 origin "$SOURCE_SHA"
git -C "$OWNED/source" checkout --detach FETCH_HEAD
test "$(git -C "$OWNED/source" rev-parse HEAD)" = "$SOURCE_SHA"
git -C "$OWNED/source" submodule update --init --recursive --depth 1
git -C "$OWNED/source" submodule status --recursive > "$EVIDENCE/submodule-revisions.txt"
printf 'onnxruntime=1.31.1\nsource=%s\narchitecture=x86_64\nconfiguration=Release\nparallel=3\n' "$SOURCE_SHA" > "$EVIDENCE/source-build.txt"
cd "$OWNED/source"
./build.sh --config Release --build_shared_lib --build_wheel --parallel 3 \
  --skip_tests --skip_submodule_sync --compile_no_warning_as_error \
  --build_dir "$OWNED/build" --apple_deploy_target 14.0 \
  --cmake_extra_defines CMAKE_OSX_ARCHITECTURES=x86_64
test -n "$(find "$OWNED/build/Release/dist" -name 'onnxruntime-1.31.1-*.whl' -print -quit)"
printf 'MYL_NATIVE_EXTRA_WHEELS=%s\n' "$OWNED/build/Release/dist" >> "$GITHUB_ENV"
find "$OWNED/build/Release/dist" -name '*.whl' -exec shasum -a 256 {} \; > "$EVIDENCE/wheel-sha256.txt"

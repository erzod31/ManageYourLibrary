#!/usr/bin/env bash
set -euo pipefail
test "$(uname -s)" = Darwin || { echo 'Native macOS runner required'; exit 1; }
test -n "${RUNNER_TEMP:-}" && test -n "${GITHUB_PATH:-}" || { echo 'Independent GitHub runner environment required'; exit 1; }
case "${MYL_EXPECTED_ARCH:-}" in
  arm64)
    test "$(uname -m)" = arm64
    TARGET=aarch64
    SHA=fbf4afef53c2a6b72bb741bc06d5671a9dfaf87bd84e5aa73ac9b3d0d589f14e
    ;;
  x64)
    test "$(uname -m)" = x86_64
    TARGET=x86_64
    SHA=a962e47df522889eaa7ff0d6a56203f1079f68aabb65ffdbe8455f362bc769f3
    ;;
  *) echo 'Unsupported or absent native architecture'; exit 1;;
esac
OWNED="$(mktemp -d "$RUNNER_TEMP/myl-python-XXXXXXXX")"
URL="https://github.com/astral-sh/python-build-standalone/releases/download/20261026/cpython-3.12.16%2B20261026-$TARGET-apple-darwin-install_only.tar.gz"
curl --fail --location --retry 2 --proto '=https' --tlsv1.2 "$URL" --output "$OWNED/python.tar.gz"
printf '%s  %s\n' "$SHA" "$OWNED/python.tar.gz" | shasum -a 256 --check
tar -xzf "$OWNED/python.tar.gz" -C "$OWNED"
"$OWNED/python/bin/python3" -c 'import sys,platform,tkinter; assert sys.version_info[:3]==(3,12,16); print(sys.version,platform.machine(),"Tk",tkinter.TkVersion)'
"$OWNED/python/bin/python3" -m venv "$OWNED/build-venv"
printf '%s\n' "$OWNED/build-venv/bin" >> "$GITHUB_PATH"
printf '%s\n' "MYL_NATIVE_PYTHON_ROOT=$OWNED/python" >> "$GITHUB_ENV"

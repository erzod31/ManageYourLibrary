#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
command -v python3 >/dev/null
python3 -c 'import sys,platform,os; actual="arm64" if platform.machine()=="arm64" else "x64"; assert sys.platform=="darwin", "Native macOS executor required"; assert actual==os.environ.get("MYL_EXPECTED_ARCH",actual), "Wrong native runner architecture"'
python3 -c 'import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) else 1)' || {
  echo "The release build requires Python 3.12."; exit 1;
}
WORK="$(mktemp -d "${TMPDIR:-/tmp}/ManageYourLibrary_macos_XXXXXX")"
if [ -e "$ROOT/dist/macos" ]; then
  echo "Existing macOS output is preserved. Build in an isolated fresh checkout."; exit 1
fi
mkdir -p "$ROOT/dist/macos/validation"
EVIDENCE="$ROOT/dist/macos/validation"
# Resolve requirements-build.txt on the native architecture, then install only
# the recorded binary wheel hashes. Retain the exact transitive dependency set.
python3 tools/lock_native_wheels.py --output "$WORK/dependencies"
cp "$WORK/dependencies/requirements.lock" "$EVIDENCE/requirements.lock"
cp "$WORK/dependencies/provenance.json" "$EVIDENCE/dependency-provenance.json"
python3 tools/prepare_indra_models.py
python3 -m unittest discover -s tests -v
python3 main.py --smoke-test
python3 tools/benchmark_catalog.py --check
# The spec uses COLLECT/BUNDLE (the --onedir shape), a stable published bundle
# ID and version metadata before signing. No post-signing Info.plist rewrite.
python3 -m PyInstaller --clean --noconfirm --workpath "$WORK/build" \
  --distpath "$ROOT/dist/macos" platforms/macos/ManageYourLibrary.spec
APP="$ROOT/dist/macos/ManageYourLibrary.app/Contents/MacOS/ManageYourLibrary"
"$APP" --smoke-test
"$APP" --runtime-self-test "$EVIDENCE/runtime-self-test.json"
"$APP" --first-use-self-test "$EVIDENCE/first-use-self-test.json"
"$APP" --mobile-self-test "$EVIDENCE/mobile-self-test.json"
"$APP" --update-self-test "$EVIDENCE/update-self-test.json"
ARCH="$(python3 -c 'import platform;print("arm64" if platform.machine()=="arm64" else "x64")')"
VERSION="$(tr -d '\r\n' < VERSION)"
if [ "${MYL_MACOS_REQUIRE_DISTRIBUTION:-0}" = "1" ]; then
  python3 tools/validate_macos_release.py "$ROOT/dist/macos/ManageYourLibrary.app" --version "$VERSION" --arch "$ARCH" --output "$EVIDENCE/macos-native-gates.json" --require-distribution
else
  python3 tools/validate_macos_release.py "$ROOT/dist/macos/ManageYourLibrary.app" --version "$VERSION" --arch "$ARCH" --output "$EVIDENCE/macos-native-gates.json"
fi
python3 tools/write_build_manifest.py "$APP" --output "$ROOT/dist/macos/build-manifest.json" --platform macos --validated-release-gates --validated-runtime --validated-first-use --validated-mobile --validated-updater
if [ "${MYL_MACOS_REQUIRE_DISTRIBUTION:-0}" = "1" ]; then
  python3 tools/package_native_release.py --platform macos
else
  python3 tools/package_native_release.py --platform macos --validation-only
fi
echo "Native macOS candidate tested. Read validationMode/distributionEligible before any publication."

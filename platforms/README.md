# Platform Builds

This folder separates the build instructions for each operating system without duplicating the app source code.

The Python files in the project root are the single source of truth:

- `main.py`
- `library_app.py`
- `library_core.py`
- `ocr_engine.py`
- `cache_engine.py`
- `rounded_widgets.py`

When the app source changes, the Windows, Linux, and macOS builds automatically use the updated files the next time their build script is run.

## Important

PyInstaller should build on the same operating system as the target:

- Build Windows on Windows.
- Build Linux on Linux.
- Build macOS on macOS.

Do not copy the whole source into each platform folder. That would create three different versions of the app and make updates harder.

## Folders

```text
platforms/
  windows/
    BUILD_WINDOWS.bat
  linux/
    build_linux.sh
    tesseract/README.md
  macos/
    build_macos.sh
    tesseract/README.md
```

The generated, diagnosable `onedir` apps go to:

```text
dist/windows/
dist/linux/
dist/macos/
```

All platform entry points require Python 3.12, run the complete test suite, a
source smoke test, and the catalog performance gate before packaging. They then
run the frozen smoke test and write a `build-manifest.json` beside the native
executable. Windows uses the platform-specific hash lock. Linux and macOS use
exact versions from `requirements-build.txt`; a release made on either platform
must generate and retain a native wheel hash lock in its CI provenance.

Only a build executed and tested on its target operating system is a validated
release. Passing Windows tests does not validate Linux or macOS artifacts.

The `dist/` folder is ignored by Git and should not be committed.

## Native release CI

The manually dispatched `native-release.yml` workflow builds on Ubuntu 22.04
x64, macOS 15 Apple Silicon, and macOS 15 Intel. It prepares the native OCR
payload, resolves exact Python wheel versions into a SHA-256 lock, and uses the
existing platform entry points. Both frozen diagnostics and extracted-archive
diagnostics must pass before publication. The workflow refuses to overwrite an
existing release. `publish=false` retains only Actions artifacts; `publish=true`
publishes a native supplement without changing the existing Windows release.

For a clean native checkout with the OS prerequisites installed:

```bash
python3 tools/lock_native_wheels.py
python3 tools/bundle_native_ocr.py
# Linux requires a graphical display (CI uses xvfb-run -a).
bash platforms/linux/build_linux.sh
python3 tools/package_native_release.py --platform linux
# On macOS, use build_macos.sh and --platform macos instead.
```

Each package retains manifests, wheel hash locks, OCR inventories, SHA-256 sums,
and first-use/runtime diagnostic reports as release assets. macOS ZIPs preserve
the .app symlinks and ad-hoc signature; Developer ID signing and notarization are
not performed. Linux tar archives preserve executable permissions. Read
[native first use and limitations](../docs/NATIVE_FIRST_USE.md).

## OCR Runtime

Windows already uses the bundled runtime in the project root:

```text
tesseract/tesseract.exe
tesseract/tessdata/
```

Linux and macOS need their own native Tesseract runtime for release builds, so OCR behaves like the Windows build. Put it in:

```text
platforms/linux/tesseract/
platforms/macos/tesseract/
```

Release builds stop if those folders do not contain a native Tesseract binary and the required language data.

For development-only builds that rely on a system Tesseract from `PATH`, run the script with:

```bash
MANAGE_YOUR_LIBRARY_ALLOW_SYSTEM_TESSERACT=1 ./platforms/linux/build_linux.sh
MANAGE_YOUR_LIBRARY_ALLOW_SYSTEM_TESSERACT=1 ./platforms/macos/build_macos.sh
```

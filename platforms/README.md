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

The reviewed platform builds require Python 3.12.10, run the complete test suite, a
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

For a clean native checkout with Python 3.12.10 and the OS build prerequisites
installed, use a disposable virtual environment. The GUI builder changes only
that environment, and later Python invocations load its isolated runtime:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements-build.txt
python3 tools/lock_native_wheels.py
# Linux needs a display here too (CI uses xvfb-run -a).
python3 tools/build_accessible_tk.py --output dist/native-gui
python3 tools/bundle_native_ocr.py
# Linux requires a graphical display (CI uses xvfb-run -a).
bash platforms/linux/build_linux.sh
# Collect on the original Ubuntu 22.04 build host, before packaging.
python3 tools/collect_linux_license_evidence.py --pyinstaller-toc dist/linux-binary-inputs.toc --output dist/linux-license-evidence
python3 tools/package_native_release.py --platform linux
# On macOS, use build_macos.sh and --platform macos; omit the Ubuntu collector.
```

Each package retains manifests, wheel hash locks, OCR inventories, SHA-256 sums,
and first-use/runtime diagnostic reports as release assets. macOS ZIPs preserve
the .app symlinks and ad-hoc signature; Developer ID signing and notarization are
not performed. Linux tar archives preserve executable permissions. Read
[native first use and limitations](../docs/NATIVE_FIRST_USE.md).

Linux also retains a separate `*-license-sources.tar` with exact corresponding
Ubuntu source archives and authenticated APT indexes. Keep it with the matching
application archive. A superseded installed binary version must be updated and
rebuilt, or justified by an authenticated exact-version snapshot; sources from a
different version are rejected. Collection is evidence, not global redistribution
approval. Publication remains blocked while that review is incomplete.

## OCR Runtime

All new builds use the controlled PNG-only OCR source profile. The old Windows
DLL/EXE/JAR bundle is no longer tracked or accepted by the packager. The models
and historical legal evidence remain under `tesseract/`.

Windows requires Visual Studio 2022 C++ Build Tools, CMake/Ninja and Python 3.12.10:

```text
python -B tools/build_permissive_ocr.py --output dist/ocr
python -B tools/verify_ocr_payload.py dist/ocr/payload
```

`BUILD_EXE.bat` prepares this payload if absent. An already verified external
payload can be selected with `MANAGE_YOUR_LIBRARY_OCR_DIR`. Outputs include
notices, exact source archives, build caches/commands and a hash inventory.

Linux and macOS build on their target OS using `tools/bundle_native_ocr.py`.
It builds the same pinned OCR sources and stages them in:

```text
platforms/linux/tesseract/
platforms/macos/tesseract/
```

Release builds reject an unverified runtime, missing notices/models or changed
payload files. No arbitrary system/Homebrew OCR runtime is copied into a release.
See [license resolution and scope](../docs/RESOLUCION_GPL_LGPL_OCR_2026-10-25.md).

For development-only builds that rely on a system Tesseract from `PATH`, run the script with:

```bash
MANAGE_YOUR_LIBRARY_ALLOW_SYSTEM_TESSERACT=1 ./platforms/linux/build_linux.sh
MANAGE_YOUR_LIBRARY_ALLOW_SYSTEM_TESSERACT=1 ./platforms/macos/build_macos.sh
```

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

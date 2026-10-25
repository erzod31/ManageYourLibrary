# Windows release checklist

Use this checklist before publishing a Windows build of Manage Your Library.

## 1. Start from a clean repository

- [ ] Confirm that the intended branch is checked out.
- [ ] Run `git status --short --branch`.
- [ ] Confirm that `VERSION` contains the intended release-candidate or release version.
- [ ] Confirm that the matching changelog entry and release notes exist.
- [ ] Confirm that no personal books, caches, configuration files, logs, or quarantine folders are staged.
- [ ] Confirm that `dist/`, `build/`, and `.trash_manageyourlibrary/` remain ignored by Git.

## 2. Run automated validation

The regular `python` command must resolve to the Python installation used for packaging.
Prepare and verify the controlled OCR payload in section 3 before running the
OCR corpus command. Do not use an old Windows DLL bundle as a shortcut.

```bat
python -B tools/run_tests.py
python -B tools/evaluate_corpus.py --ocr
ruff check --no-cache --select E9,F63,F7,F82 .
git diff --check
git diff --cached --check
```

Expected result:

- [ ] The isolated runner finishes without accessing a real user profile.
- [ ] The full unit-test suite succeeds.
- [ ] Both Git whitespace checks succeed.
- [ ] Disposable-reader crash, timeout, memory and cancellation checks succeed.
- [ ] No forbidden cloud OCR or Google Books references are present.
- [ ] `rapidfuzz` is not present in requirements or build scripts.

## 3. Prepare and verify the controlled OCR payload

From a clean checkout with Python 3.12 and Visual Studio 2022 C++ Build Tools
(including CMake/Ninja), build the pinned OCR sources:

```bat
python -B tools/build_permissive_ocr.py --output dist/ocr
python -B tools/verify_ocr_payload.py dist/ocr/payload
python -B tools/verify_ocr_functionality.py dist/ocr/payload --output dist/ocr-formats.json
```

An existing verified payload may be reused; do not overwrite earlier evidence.
For an external payload, set `MANAGE_YOUR_LIBRARY_OCR_DIR` to its directory
before validation/building and pass that directory to the verification tools.
The new executable is `dist\ocr\payload\tesseract.exe`, not the removed
`tesseract\tesseract.exe` from the legacy distribution.

See [OCR license resolution](RESOLUCION_GPL_LGPL_OCR_2026-10-25.md) for the
source lock, notices and the distinct scope of historical binaries.

Expected result:

- [ ] Six models are hash-verified: `eng`, `spa`, `fra`, `nld`, `chi_sim`, `osd`.
- [ ] The payload inventory, exact source archives and license notices are verified.
- [ ] Seven image formats, combined language loading and TSV checks pass.
- [ ] The old DLL/JAR bundle is not included in the new payload.
- [ ] OCR is local only.
- [ ] No document is uploaded to an OCR service.
- [ ] Record exact native DLL/model provenance, license notices, source obligations and security review.
- [ ] Preserve Python/wheel license texts in the frozen payload.
- [ ] Close the native redistribution review before approving a public package.
      `--development` only creates explicitly marked local test artifacts; it does not clear this gate.

## 4. Prepare the isolated accessible GUI runtime and build the EXE

Use a fresh neutral build directory outside Windows profiles. Tcl embeds its
build-library fallback and C source filenames; removing debug symbols alone
does not remove these paths. The builder and packager reject embedded profile
paths rather than editing linked binaries.

```bat
py -3.12 -m venv C:\myl-native-build\venv
C:\myl-native-build\venv\Scripts\python.exe -m pip install --require-hashes -r requirements.lock
C:\myl-native-build\venv\Scripts\python.exe -B tools\build_accessible_tk.py --output C:\myl-native-build\gui
set "MANAGE_YOUR_LIBRARY_PYTHON=C:\myl-native-build\venv\Scripts\python.exe"
```

This does not replace the system Python or enable a screen reader. The patched
runtime must pass its ASan regression, native COM contract and path checks.

From the repository root:

```bat
BUILD_EXE.bat
```

The shortcut delegates to:

```text
platforms\windows\BUILD_WINDOWS.bat
```

Expected artifact:

```text
dist\windows\ManageYourLibrary\ManageYourLibrary.exe
```

Verify:

- [ ] The build succeeds without a traceback.
- [ ] The EXE exists.
- [ ] The EXE icon is present.
- [ ] `dist/` is ignored and is not staged.
- [ ] Temporary PyInstaller build folders are removed.
- [ ] `pypdfium2_raw\pdfium.dll` is inside the frozen archive.
- [ ] Tesseract and the required language files are inside the frozen archive.
- [ ] Frozen `--runtime-self-test` passes with isolated application data.
- [ ] Frozen `--accessibility-self-test`, `--windows-provider-self-test` and
      `--local-voice-self-test` pass. The last writes synthetic audio to a temporary
      WAV without playing it; it is not a substitute for an authorized hearing test.
- [ ] Compile the installer with `platforms\windows\BUILD_INSTALLER.bat`.
- [ ] Run `python tools/package_windows_release.py` and verify the resulting ZIP
  extracted into a temporary directory before distributing it.
- [ ] Record runtime tests separately from visual installed-UI approval; building
  an installer alone does not complete the latter.

## 5. Smoke-test the EXE safely

Follow [manual_test_plan_windows.md](manual_test_plan_windows.md).

Minimum release smoke checks:

- [ ] Start the EXE with isolated `APPDATA` and `LOCALAPPDATA`.
- [ ] Confirm that the main window appears without a traceback or missing-runtime message.
- [ ] Confirm that the library is initially unconfigured in the isolated environment.
- [ ] Confirm that the main actions are visible: Add books, Search metadata, Open library, Undo, and Check duplicates.
- [ ] Process the synthetic scanned-PDF fixture from the frozen UI and confirm that no Tesseract or PDFium error appears.
- [ ] Confirm that frozen OCR remains local and does not upload the fixture.
- [ ] Close the application and confirm that no `ManageYourLibrary.exe` process remains.
- [ ] Verify names, roles, disabled actions and selection using an external assistive client, not only Tcl getters.
- [ ] Exercise the intended Windows screen reader and record its version and observed speech/focus behavior.
- [ ] Resolve and regression-test the Tk 9.1 Windows provider risks recorded in [native/accessibility validation](VALIDACION_NATIVA_Y_ACCESIBILIDAD_2026-10-25.md) before approving that runtime for distribution.
- [ ] Retain the patched runtime receipt, ASan dispatcher/enum report and the
      real in-process COM contract report; those are not external reader certification.
- [ ] Confirm the app voice starts off without an engine/thread, with visible
      Activate/Deactivate controls on every page. Activation must be user initiated.
- [ ] With the user's agreement to hear audio, test the local Windows voice,
      deactivation/purge, focus-loss pause and close. Never start NVDA automatically
      or alter an independently running reader to make this check pass.

## 6. Validate safe temporary workflows

Use only the temporary release-validation library described in the manual test plan.

- [ ] Add a synthetic low-confidence test file and confirm it goes to `PARA REVISAR NUEVAMENTE`.
- [ ] Add an exact duplicate synthetic file and confirm it goes to `.trash_manageyourlibrary/`.
- [ ] Confirm that `.trash_manageyourlibrary/` contains a manifest and remains recoverable.
- [ ] Use Search metadata on a temporary file and confirm that it stays in the original folder.
- [ ] Exercise Undo after a temporary rename or quarantine operation.
- [ ] Close and reopen the EXE with the same isolated `APPDATA`.

## 7. Final publication hygiene

- [ ] Run `git status --short --branch`.
- [ ] Remove temporary validation folders.
- [ ] Remove `__pycache__/`.
- [ ] Confirm that no EXE, `dist/`, `build/`, local cache, or quarantine file is staged.
- [ ] Record the tested commit hash.
- [ ] Record the EXE SHA256 and compare it with the checksum document for the intended release.
- [ ] Record EXE size and build date.
- [ ] Keep the generated EXE outside Git unless publishing it separately as a release asset.

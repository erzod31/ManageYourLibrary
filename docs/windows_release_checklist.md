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

```bat
python -m compileall .
python -m unittest discover -s tests
git diff --check
git diff --cached --check
```

Expected result:

- [ ] Compilation succeeds.
- [ ] The full unit-test suite succeeds.
- [ ] Both Git whitespace checks succeed.
- [ ] No forbidden cloud OCR or Google Books references are present.
- [ ] `rapidfuzz` is not present in requirements or build scripts.

## 3. Confirm bundled OCR files

Before building, confirm that these files exist:

```text
tesseract\tesseract.exe
tesseract\tessdata\eng.traineddata
tesseract\tessdata\spa.traineddata
tesseract\tessdata\fra.traineddata
tesseract\tessdata\nld.traineddata
tesseract\tessdata\chi_sim.traineddata
```

Optional command:

```bat
tesseract\tesseract.exe --list-langs
```

Expected result:

- [ ] `eng`, `spa`, `fra`, `nld`, and `chi_sim` are listed.
- [ ] OCR is local only.
- [ ] No document is uploaded to an OCR service.

## 4. Build the EXE

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

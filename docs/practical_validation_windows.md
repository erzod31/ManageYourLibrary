# Windows practical validation

Validated on Windows on 2026-05-30 after the Phase 3 refactors.

## Isolated product checks

- Imported `main`, `library_app`, and `library_core`.
- Constructed and closed `App(root)` with library and application-data paths redirected to a temporary directory.
- Exercised safe file operations only inside temporary directories:
  - move to library;
  - low-confidence move to `PARA REVISAR NUEVAMENTE`;
  - exact duplicate quarantine;
  - quarantine undo;
  - replacement undo restoring both files;
  - metadata rename in place, including Unicode names;
  - collision-safe rename;
  - committed and recovered journal events;
  - corrupt-index fallback;
  - quarantine ignored by the index.
- Confirmed offline-provider behavior through mocked regression tests.

## Local OCR and PDF rendering

- Confirmed the bundled `tesseract/tesseract.exe` starts correctly.
- Confirmed bundled language data: `eng`, `spa`, `fra`, `chi_sim`, and `osd`.
- Ran local Tesseract against a synthetic image.
- Rendered a synthetic scanned PDF page through `pypdfium2`.
- Confirmed that no cloud OCR provider is referenced by the application sources.

## Windows build

Build command:

```bat
BUILD_EXE.bat
```

The Windows script delegates to `platforms/windows/BUILD_WINDOWS.bat` and bundles:

- `tesseract/`, including `tessdata`;
- `pypdfium2` and `pypdfium2_raw/pdfium.dll`;
- Tkinter runtime files;
- the application icon.

Generated artifact:

```text
dist/windows/ManageYourLibrary.exe
```

Archive inspection confirmed that the EXE contains:

- `tesseract/tesseract.exe`;
- `tesseract/tessdata/eng.traineddata`;
- `tesseract/tessdata/spa.traineddata`;
- `tesseract/tessdata/fra.traineddata`;
- `tesseract/tessdata/chi_sim.traineddata`;
- `pypdfium2_raw/pdfium.dll`.

The EXE was started with isolated `APPDATA` and `LOCALAPPDATA` directories and remained running until the smoke test closed it.

Phase 4B also started the frozen EXE with a `PATH` that did not contain Python. A second smoke test:

- bound the visible Tkinter window to the frozen EXE process;
- started and closed the EXE twice with the same isolated profile;
- used a temporary configured library;
- confirmed that `library_index.json` was created only under the isolated `APPDATA`;
- confirmed that no `ManageYourLibrary.exe` process remained after cleanup.

## Known limitations

- The EXE currently has no command-line smoke mode for invoking OCR from inside the frozen application without UI interaction.
- Linux and macOS shell syntax could not be revalidated on this Windows machine because the local WSL installation is unavailable. Their only Phase 4A change removes an unused hidden import.


# Windows RC build report

## Candidate

- Version: `0.1.0-rc1`
- Built on: `2026-05-31`
- Platform: Windows 11
- Build script: `platforms/windows/BUILD_WINDOWS.bat`
- Generated artifact: `dist/windows/ManageYourLibrary.exe`
- Size: `107328510` bytes
- SHA256: `0A0334D6F07BAD4849B2708EA05A1E0FA791FE4D5DAD537B1C5C1A3C99CAD279`

The generated EXE is intentionally ignored by Git. Attach it separately to a GitHub Release after the remaining manual checks pass.

## Frozen archive verification

Archive inspection confirmed that the EXE contains:

- `pypdfium2_raw/pdfium.dll`;
- `tesseract/tesseract.exe`;
- `tesseract/tessdata/eng.traineddata`;
- `tesseract/tessdata/spa.traineddata`;
- `tesseract/tessdata/fra.traineddata`;
- `tesseract/tessdata/chi_sim.traineddata`.

The archive does not contain the removed optional `rapidfuzz` payload.

## Automated smoke verification

The frozen EXE was started twice with:

- isolated temporary `APPDATA` and `LOCALAPPDATA`;
- a disposable configured library folder;
- a reduced `PATH` containing Windows system folders only, without Python.

Both launches opened the expected Tkinter window titled `Gestiona tu biblioteca`. The isolated configuration remained readable on restart, all test processes were closed, and the temporary profile was removed afterward.

Local runtime checks also confirmed:

- bundled Tesseract languages: `chi_sim`, `eng`, `fra`, `osd`, and `spa`;
- local `pypdfium2` and `pypdfium2_raw` imports;
- frozen archive payload verification.

The artifact was rebuilt during Phase 4D before the manual-validation gate. The size and SHA256 above identify that most recent tested artifact.

## Pending before final release

Complete the interactive workflow in [manual_test_plan_windows.md](manual_test_plan_windows.md) with disposable folders only:

- select a temporary library through the UI;
- add a synthetic low-confidence file;
- confirm exact-duplicate quarantine and manifest creation;
- verify metadata search remains rename-in-place;
- exercise Undo;
- perform a frozen OCR check through the UI.


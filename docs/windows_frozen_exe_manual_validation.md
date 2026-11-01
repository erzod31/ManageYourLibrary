# Windows frozen EXE manual validation

## Gate status

- Date: `2026-05-31`
- Release: `0.1.0`
- Tested artifact: `dist/windows/ManageYourLibrary.exe`
- Size: `107326924` bytes
- SHA256: `D6808B050EEF9C8F036FE4005FF5F3387E44B5099110CC7C101BE0B6F4A2906E`
- Decision: **approved for the final Windows build**

The frozen runtime, safe automated workflows, and final human click-through inside the frozen Tkinter UI were validated with disposable fixtures only.

The official post-release checksum is the SHA256 calculated from the published GitHub Release asset downloaded to `%USERPROFILE%\Downloads\ManageYourLibrary.exe`:

```text
D6808B050EEF9C8F036FE4005FF5F3387E44B5099110CC7C101BE0B6F4A2906E
```

See [post_release_v0.1.0_verification.md](post_release_v0.1.0_verification.md) for the published-asset verification record.

## Safety boundary

No personal library or personal ebook was used. Automated checks created and removed only:

```text
temp_frozen_manual_validation/
  appdata/
  localappdata/
  input/
  library/
  review/
  ocr/
```

The frozen smoke used temporary `APPDATA`, temporary `LOCALAPPDATA`, a disposable configured library, and a reduced Windows-only `PATH` without Python.

## Completed automated checks

### Official Windows build

`platforms/windows/BUILD_WINDOWS.bat` completed successfully and generated:

```text
dist/windows/ManageYourLibrary.exe
```

Archive inspection confirmed:

- `pypdfium2_raw/pdfium.dll`;
- `tesseract/tesseract.exe`;
- `tesseract/tessdata/eng.traineddata`;
- `tesseract/tessdata/spa.traineddata`;
- `tesseract/tessdata/fra.traineddata`;
- `tesseract/tessdata/chi_sim.traineddata`;
- no `rapidfuzz` payload.

The final `0.1.0` rebuild generated a `107326924` byte EXE with SHA256:

```text
D6808B050EEF9C8F036FE4005FF5F3387E44B5099110CC7C101BE0B6F4A2906E
```

### Frozen startup and restart

The EXE opened twice with the isolated profile and a `PATH` without Python. Both visible Tkinter windows had the expected Spanish title:

```text
Gestiona tu biblioteca
```

The isolated configuration remained readable across restarts. No `ManageYourLibrary.exe` process remained afterward.

The final `0.1.0` rebuild was smoke-tested again with a fresh temporary profile under `temp\phase4e_final_smoke`. It opened twice with a reduced Windows-only `PATH` without Python, exposed the expected Tkinter window, retained the disposable configured library, created its isolated index, closed normally, left no residual process, and removed the temporary profile afterward.

### Safe workflow fixtures

The practical regression suite exercised temporary paths only:

- committed move journal entry;
- quarantine plus Undo restoration;
- replacement plus Undo restoration;
- Unicode metadata rename in place;
- missing Undo source with a clear error;
- local Tesseract processing of a synthetic image;
- PDFium rendering of a synthetic scanned PDF.

An additional temporary OCR/PDFium smoke extracted text from a generated image and rendered one scanned-PDF page. The fixture contained no personal data.

## Completed human click-through

This environment can launch and observe the frozen Tkinter window, but it does not provide a reliable desktop controller for clicking Tkinter widgets. A human completed [manual_click_validation_form_windows.md](manual_click_validation_form_windows.md) using the generated disposable fixtures. The longer [manual_test_plan_windows.md](manual_test_plan_windows.md) remains available as supporting detail.

Record these results:

| Flow | Required frozen-UI confirmation | Status |
| --- | --- | --- |
| Add books | Select the temporary library and add the low-confidence fixture. Confirm move to temporary review and understandable log output. | Passed |
| Exact duplicate | Add the controlled duplicate. Confirm visible `.trash_manageyourlibrary/`, manifest creation, and no irreversible delete. | Passed |
| Undo | Undo a quarantine or rename. Confirm restoration without overwrite or corruption. | Passed |
| Search metadata | Process the temporary rename fixture. Confirm rename-in-place and no move into the library. | Passed |
| OCR | Process the generated scanned PDF. Confirm no Tesseract-language error and no external upload. | Passed |
| PDFium | Process the generated scanned PDF. Confirm no missing-PDFium runtime error. | Passed |

## Verified release hygiene

- `dist/` remains ignored by Git.
- No generated EXE, `dist/`, or `build/` content is staged.
- Temporary validation folders remain local and ignored by Git until final release checks are complete.
- No personal library was selected.
- OCR remains local.
- The generated EXE should be attached separately to a GitHub Release and must not be committed to Git.


# Manage Your Library 0.1.0-rc1

This is the first Windows release candidate prepared after the file-safety and modularization work.

## What this candidate protects

- Discarded duplicates are moved to `.trash_manageyourlibrary/` instead of being deleted directly.
- Replacements use quarantine, transaction journaling, destination verification, index updates, and recoverable Undo records.
- Metadata search keeps its existing contract: it can rename files in place, but it does not move them into the active library.
- Uncertain additions remain conservative and go to `PARA REVISAR NUEVAMENTE`.

## Included Windows runtime

- Local Tesseract OCR runtime with `eng`, `spa`, `fra`, and `chi_sim` language data.
- `pypdfium2` and PDFium for rendering scanned PDF pages locally when OCR is needed.
- Tkinter runtime files and the application icon.

OCR remains local. The app does not upload user documents and does not use a remote OCR service.

## Metadata providers

The supported external providers remain Open Library, Wikidata, Library of Congress, Crossref, OpenAlex, Internet Archive, and Gutendex as an auxiliary fallback. The app continues conservatively with local analysis when external metadata is unavailable.

## Known limitations

- The Windows EXE has no command-line OCR smoke mode. OCR behavior inside the frozen UI still requires the isolated manual test plan before a final public release.
- Linux and macOS builds are prepared but are not release candidates in this phase.
- This candidate should be tested with disposable folders before publishing a final release.

## Before final publication

1. Follow [windows_release_checklist.md](windows_release_checklist.md).
2. Complete [manual_test_plan_windows.md](manual_test_plan_windows.md) using only a disposable library.
3. Compare the generated EXE with the SHA256 in [windows_rc_build_report.md](windows_rc_build_report.md).
4. Attach the generated EXE to a GitHub Release; do not commit it to the repository.


# Manage Your Library 0.3.0 for Windows

Version 0.3.0 focuses on file integrity, conservative duplicate handling,
interruption recovery, local OCR coverage, and reproducible packaging.

## File safety

- Exact duplicate decisions rehash the live files immediately before action.
- Critical moves require a durable journal record and verify destination size
  and SHA-256 after moving.
- Interrupted replacements restore the quarantined previous copy when the new
  source was not applied, or verify the completed destination before committing.
- Recoverable discarded files remain in `.trash_manageyourlibrary/`.
- Partial Undo progress is saved per item and failed restores remain retryable.
- Non-exact title matches are sent to review because they can be different
  editions, translations, volumes, or versions.

## Durable plans and cancellation

- Imports create an immutable SQLite preview containing source signatures.
- Plan items are persisted individually and completed items are not selected
  again when a paused plan resumes.
- Active analysis, OCR, duplicate scans, and bounded external readers support
  cooperative cancellation.
- The app offers to resume an interrupted import after restart.
- Completed journal moves are reconciled after a crash, older plan databases
  gain missing columns in place, and routine operations update only affected
  index paths.
- One immutable document context reuses the content hash across analysis cache
  lookup and persistence and rejects mid-analysis file changes.

## OCR and document readers

- Local OCR defaults to 12 pages and is configurable up to 200 pages.
- Finding an ISBN does not end OCR unless sufficient bibliographic evidence is
  also present.
- English, Spanish, French, Dutch, Simplified Chinese, and orientation data are
  bundled for Tesseract.
- `pypdfium2` renders scanned PDF pages locally before Tesseract OCR.
- DOCX, ODT, RTF, FB2, and TXT use format-aware readers. DOC and DjVu use
  bounded local LibreOffice or DjVuLibre processes when installed.

OCR remains local. The application does not upload documents, pages, or OCR
text. The metadata lookup sends only short derived queries such as title, author,
ISBN, or DOI, and can be disabled with offline mode.

## Build and validation

- Windows builds require CPython 3.12 and hash-locked wheels.
- The checked-in PyInstaller spec produces a diagnosable `onedir` application.
- The build runs all automated tests and a frozen `--smoke-test` before writing
  a provenance manifest.
- An Inno Setup recipe creates the complete installer from the validated folder.
- Generated binaries remain outside Git history.

See [windows_0.3.0_checksums.md](windows_0.3.0_checksums.md) for the artifacts
actually built and validated on Windows.

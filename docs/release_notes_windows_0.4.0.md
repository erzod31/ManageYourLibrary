# Manage Your Library 0.4.0 for Windows

Version 0.4.0 introduces a redesigned desktop workspace while preserving the conservative file-safety foundation from 0.3.0.

## Interface

- Library dashboard with cover and table views, responsive layout, live search, format filtering, collection statistics, pagination, and a details inspector.
- Guided four-stage import flow: Select, Analyze, Review, and Organize.
- Dedicated review area for exact duplicates, possible editions, and uncertain metadata.
- Activity page with visible progress, cancellation, technical history, and Undo access.
- Settings for language, theme, offline metadata lookup, OCR, provider health, and optional local AI.
- English, Spanish, French, and Chinese interface support.

## Local previews and privacy

Cover thumbnails are extracted locally from supported images, PDFs, EPUBs, and CBZ files. PDF rendering uses bundled `pypdfium2`; OCR uses bundled `Tesseract`. OCR remains local, and the application does not upload documents. Online metadata lookup can be disabled with offline mode.

## Safety

- File changes continue to use journaled operation plans with preview, cancellation, resume, and Undo.
- Exact duplicate decisions are hash-validated immediately before action.
- Removed duplicates continue to enter the recoverable `.trash_manageyourlibrary/` quarantine.
- Possible editions and translations remain manual-review cases.
- The Windows build uses hash-locked dependencies and includes provenance information.

## Windows artifact

The 64-bit installer is named `ManageYourLibrary-0.4.0-Setup-x64.exe`. See [windows_0.4.0_checksums.md](windows_0.4.0_checksums.md) for verification details.

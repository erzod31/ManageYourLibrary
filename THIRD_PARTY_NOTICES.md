# Third-Party Notices

Manage Your Library uses and/or bundles third-party components for local ebook analysis and packaging.

## Tesseract OCR

- Project: Tesseract OCR
- Homepage: https://github.com/tesseract-ocr/tesseract
- License: Apache License 2.0
- Purpose: Local OCR engine used for scanned PDFs and image files.

## Tesseract Language Data

- Project: tessdata / tessdata_fast
- Homepage: https://github.com/tesseract-ocr/tessdata_fast
- License: Apache License 2.0
- Included or expected models: `eng`, `spa`, `fra`, `nld`, `chi_sim`, and `osd`.

## Python Dependencies

- pypdf: PDF metadata and text extraction.
- pypdfium2 / PDFium: PDF page rendering for local OCR.
- Pillow: image preparation for OCR.
- Python standard-library `SequenceMatcher`: deterministic title and author comparison; RapidFuzz is not bundled.
- ftfy: Unicode/mojibake repair.
- PyInstaller and its Windows helper packages: application packaging.

## Packaging tools

- PyInstaller: GPL-2.0-or-later with the PyInstaller bootloader exception.
- Inno Setup: installer generation; it is a build-time dependency and is not bundled as a runtime component.

OCR runs locally. The app does not send documents to external OCR services.

# Third-Party Notices

Manage Your Library uses and/or bundles third-party components for local ebook analysis and packaging.

The project's own source is MIT licensed; see `LICENSE`. This does not relicense
the components below. The optional Qt experiment in `tools/benchmark_qt_prototype.py`
requires a separately installed PySide6 environment and is not bundled with the
application. Its distribution would require a separate Qt license review.

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

## Development-package audit, 2026-10-24

Frozen builds retain the installed wheel metadata and license files for Pillow,
pypdf, pypdfium2/PDFium, ftfy, wcwidth and the PyInstaller bootloader. The Windows
build also carries the Python distribution's `LICENSE.txt` under `licenses/python`.
Pillow's wheel includes its binary dependency notices and SBOM. These documents
are third-party attribution, not personal project-owner data.

The checked-in Windows OCR runtime identifies itself as Tesseract
`5.5.0.20241111`, with Leptonica 1.85.0 and additional DLLs. The preserved Apache
license texts cover the engine/model projects, **not every DLL in that legacy
bundle**. Exact native dependency provenance, redistribution notices/source
obligations and security review remain release blockers. A passing OCR test or
Python vulnerability scan does not clear those blockers. Development artifacts
are for local validation; they are not approved for a new public release.

Upstream sources: [engine license](https://github.com/tesseract-ocr/tesseract/blob/5.5.0/LICENSE),
[model license](https://github.com/tesseract-ocr/tessdata_fast/blob/4.1.0/LICENSE),
[Windows distributor](https://github.com/UB-Mannheim/tesseract/wiki).

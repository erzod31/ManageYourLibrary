# Third-Party Notices

Manage Your Library uses and/or bundles third-party components for local ebook analysis and packaging.

## Indra OCR

- Project: Indra OCR by Datalab, version 1.1.2.
- Homepage: https://github.com/datalab-to/indra-ocr
- Code: Apache-2.0, reproduced in `third_party/indra/CODE_LICENSE.txt`.
- Purpose: local OCR for scanned PDFs and images, running on the desktop.

## Indra model weights and OCR Output

- Source: https://huggingface.co/datalab-to/indra-ocr
- Model revision: `bd02167fdf2005a19962cc15188f8496a2c87d3b`.
- Datalab's modified OpenRAIL-M terms, including use/commercial restrictions
  and share-alike provisions: `third_party/indra/MODEL_LICENSE.txt` and NOTICE.
- Models are unmodified and hash-checked. No weights are bundled in Android.
- This separate license is not replaced by the project's MIT license and
  does not change ownership/licensing of the original books.
- Tesseract, tessdata and its legacy JBIG-KIT stack are not in current payloads.

## Python Dependencies

- pypdf: PDF metadata and text extraction.
- pypdfium2 / PDFium: PDF page rendering for local OCR.
- Pillow: image preparation for OCR.
- Indra OCR, ONNX Runtime, NumPy and OpenCV headless: local CPU OCR inference.
- Python standard-library `SequenceMatcher`: deterministic title and author comparison; RapidFuzz is not bundled.
- ftfy: Unicode/mojibake repair.
- PyInstaller and its Windows helper packages: application packaging.

## Packaging tools

- PyInstaller: GPL-2.0-or-later with the PyInstaller bootloader exception.
- Inno Setup: installer generation; it is a build-time dependency and is not bundled as a runtime component.
- Android SDK build tools, D8 and apksigner: build-time tools. The native Android
  client uses system Android/Java APIs and contains no third-party native DLLs
  or OCR runtime. Project/model notices are included under `assets/licenses`.

OCR runs locally. The app does not send documents to external OCR services.
The optional companion transfers explicitly selected copies to the user's PC
or phone through private Tailscale HTTPS. Tailscale is installed separately.

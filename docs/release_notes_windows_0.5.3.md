# Windows 0.5.3 — Indra OCR

Indra OCR 1.1.2 replaces Tesseract. OCR remains local and does not upload documents.
Digital PDFs still use their existing text layer first; pypdfium2 renders scans
only when needed. Existing metadata lookup behavior and conservative identity
decisions remain in place. Books and `.trash_manageyourlibrary/` stay recoverable.

The Windows installer includes the Python runtime, ONNX Runtime, OpenCV, the
language models and dependencies. No separate Python, GPU, OCR installation or
model download is needed by an installed user. Windows builds use hash-locked
dependencies and model revision bd02167fdf2005a19962cc15188f8496a2c87d3b.

Models load lazily in one reusable subprocess; text and line geometry come from
one OCR pass. Weak short lines may receive one bounded recognition-only retry
with expanded context, retaining the original detected reading order.
Requests are cancellable and time limited. Caches are bounded;
the worker exits after 60 seconds idle and when the app closes. PDF rendering
retains one page at a time. Upgrades preserve user state; old OCR-derived cache
decisions are recomputed under the updated cache version.

The Indra code is Apache-2.0. Models and OCR Output are governed by Datalab's
separate modified OpenRAIL-M license, including its commercial/use restrictions
and share-alike terms. See `third_party/indra/MODEL_LICENSE.txt` and NOTICE.txt.
The installer presents the model terms; portable users must also comply. This
does not change ownership or licensing of the original books.

Current local checks and artifact hashes are recorded in
[windows_0.5.3_checksums.md](windows_0.5.3_checksums.md).
Extraction and isolated payload diagnostics do not certify an actual Windows
install, upgrade, uninstall or manual UI session. No GitHub release is implied.

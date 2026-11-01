# Manage Your Library 0.4.2 for Windows

Version 0.4.2 makes cover loading fast and memory-efficient while preserving the warm editorial interface introduced in 0.4.1.

## Cover loading

- A local embedded cover is always preferred.
- If no local cover is available and the book has an ISBN, the app uses an Open Library cover URL without storing the original image in the library.
- Only currently visible cover thumbnails are kept in memory, with at most four downloads running at once.
- Compact WebP thumbnails are reused from a bounded 100 MB disk cache; older entries are removed automatically.
- Requests use HTTPS, a known-host allowlist, a six-second timeout, an 8 MB response limit, and a short negative cache for missing covers.
- Offline mode prevents remote cover requests.

## Existing behavior preserved

The guided import, duplicate review, operation journal, Undo, local `Tesseract` OCR, `pypdfium2` rendering, optional metadata lookup, and offline mode remain available. OCR remains local, the app does not upload documents, and duplicate quarantine remains recoverable in `.trash_manageyourlibrary/`.

The Windows build continues to use hash-locked dependencies. See [windows_0.4.2_checksums.md](windows_0.4.2_checksums.md) for the validated artifact.

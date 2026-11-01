# Manage Your Library 0.4.3 for Windows

Version 0.4.3 improves the finish and consistency of the editorial interface.

## Interface improvements

- Rounded buttons and cards use supersampled surfaces for cleaner, antialiased edges.
- Combobox fields and their opened menus use matching foreground, background, selection, arrow, and border colors in dark mode.
- The light/dark theme switch now lives in the persistent sidebar and is available from every page.
- Selected-book details show the complete absolute file path instead of only the file name.

## Existing behavior preserved

Fast URL-backed covers, the bounded WebP cache, guided import, duplicate review, operation journal, Undo, local `Tesseract` OCR, `pypdfium2` rendering, optional metadata lookup, and offline mode remain available. OCR remains local, the app does not upload documents, and duplicate quarantine remains recoverable in `.trash_manageyourlibrary/`.

The Windows build continues to use hash-locked dependencies. See [windows_0.4.3_checksums.md](windows_0.4.3_checksums.md) for the validated artifact.

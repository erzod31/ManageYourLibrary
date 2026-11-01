# Manage Your Library 0.5.1 for Windows

Version 0.5.1 consolidates the catalog workspace, improves pointer behavior,
and makes important book metadata directly actionable from the details panel.

## Interactive book details

- Author, series, tags, and favorite state appear directly beside the selected
  book with the same icon language as the rest of the application.
- Clicking an author, series, or tag opens the corresponding filtered catalog.
- Favorite status can be changed in place without renaming, moving, or modifying
  the source book file.
- Organizational changes no longer lock the bibliographic identity of a book.

## Interface responsiveness and accessibility

- Pointer feedback is stable across nested cards, tooltips, disabled controls,
  and rounded buttons.
- Rounded hover surfaces are cached to avoid redraw stalls while moving through
  the interface.
- Keyboard activation, focus indication, translated accessible names, and page
  shortcuts cover the primary workspace controls.
- Prepared catalog indexes keep search and filtering responsive on large
  libraries.

## Safety and local runtime

Recoverable quarantine in `.trash_manageyourlibrary/`, durable plans,
transaction journaling, Undo, local `Tesseract` OCR, `pypdfium2` PDF rendering,
optional metadata lookup, and offline mode remain available. OCR remains local,
the app does not upload documents, and ambiguous bibliographic matches still
require review.

The Windows build uses hash-locked dependencies. See
[windows_0.5.1_checksums.md](windows_0.5.1_checksums.md) for the artifact record.

# Manage Your Library 0.5.0 for Windows

Version 0.5.0 focuses the application on safe library intake, review, and long-term catalog quality.

## Durable catalog

- A new SQLite catalog separates the conceptual work, publication edition, and concrete local file.
- The existing JSON index remains available as a portable compatibility and recovery surface.
- Existing index rows are migrated in the background without deleting unavailable records.
- Human corrections are recorded with field provenance and protected from later automated refreshes.
- The manual metadata editor changes the catalog only; it does not rename or move the book.

## Focused workspace

- The editorial navigation now includes Library, Authors, Series, Tags, Favorites, Import, and Reviews; clicking the status strip opens Activity.
- Authors, Series, Tags, and Favorites are working catalog scopes rather than decorative links.
- A consistent 24 px rounded-line icon palette now covers navigation, search, view controls, details, file actions, metadata, appearance, and Undo in both themes.
- Primary navigation items provide short translated hover explanations; the bottom Appearance and Settings controls remain unobtrusive.
- Review counters expose unfinished work and durable duplicate-review sessions can be resumed.
- Details are grouped into Identity, Edition, File, and Provenance and include the complete path, Copy path, and Show in folder.
- The layout collapses the navigation rail and details inspector at narrower window sizes.
- The navigation rail and book inspector can be resized by dragging their dividers.
- Mouse-wheel scrolling follows the central library and long workflow pages; the left navigation and right inspector remain static.
- The library search bar is larger, full-width, accent outlined, and exposes its `Ctrl+K` shortcut.
- Its magnifier is drawn from the same icon system and follows the active theme accent.
- Panel dividers use an immediate native drag preview and apply the selected size once on release.
- Cover cards are repositioned in place after resizing, without rebuilding their widgets or reloading cover images.
- System, Light, and Dark appearance preferences apply throughout the application.

## Safety and local runtime

Recoverable quarantine in `.trash_manageyourlibrary/`, durable plans, transaction journaling, Undo, local `Tesseract` OCR, `pypdfium2` PDF rendering, optional metadata lookup, and offline mode remain available. OCR remains local, the app does not upload documents, and ambiguous bibliographic matches still require review.

The Windows build uses hash-locked dependencies. See [windows_0.5.0_checksums.md](windows_0.5.0_checksums.md) for the artifact record.

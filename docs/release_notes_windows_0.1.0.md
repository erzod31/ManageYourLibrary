# Manage Your Library 0.1.0 for Windows

This is the first stable Windows release of Manage Your Library. It was promoted after automated validation and an isolated human click-through of the frozen Tkinter executable with disposable fixtures only.

## File safety

- Discarded duplicates move to `.trash_manageyourlibrary/` instead of being deleted directly.
- Replacements quarantine the old copy first, verify the new destination, record the transaction journal, update the index, and keep a recoverable Undo record.
- Critical JSON state uses atomic writes.
- Uncertain additions remain conservative and go to `PARA REVISAR NUEVAMENTE`.
- Search metadata preserves its contract: it renames in place and never moves files into the active library.

## Included Windows runtime

- Local Tesseract OCR runtime with `eng`, `spa`, `fra`, and `chi_sim` language data.
- `pypdfium2` and bundled PDFium for rendering scanned PDF pages locally when OCR is needed.
- Tkinter runtime files and the application icon.

OCR is local only. The app does not use cloud OCR, does not upload user documents, and does not use Google Books.

## Identification and metadata

- Similarity matching is deterministic and uses the standard-library `SequenceMatcher`.
- The removed optional `rapidfuzz` package is not bundled.
- External metadata providers are Open Library, Wikidata, Library of Congress, Crossref, OpenAlex, Internet Archive, and Gutendex as an auxiliary fallback.
- When internet metadata is unavailable, the app continues conservatively with local analysis.

## Basic use

1. Start the EXE and choose a personal library folder.
2. Use **Add books** to move new books into the selected library.
3. Use **Search metadata** when files should only be renamed in their current folders.
4. Review uncertain additions in `PARA REVISAR NUEVAMENTE`.
5. Inspect `.trash_manageyourlibrary/` before manually cleaning quarantined files.

Test the application with a temporary folder before using it on an important library.

## Known limitations

- Linux and macOS build scripts are prepared but are not validated release artifacts for `0.1.0`.
- External metadata quality depends on the upstream providers and network availability.
- OCR intentionally analyzes a limited number of pages and remains conservative for weak evidence.
- Permanent quarantine cleanup remains a manual user decision.

## Windows artifact

The Windows EXE is attached separately to the GitHub Release and is not committed to this repository. Verify its SHA256 against [windows_0.1.0_checksums.md](windows_0.1.0_checksums.md):

```text
D6808B050EEF9C8F036FE4005FF5F3387E44B5099110CC7C101BE0B6F4A2906E
```

This official checksum was calculated from the asset downloaded from the published GitHub Release.

## Reporting problems

When reporting an issue, include the release version, Windows version, action performed, visible error text, and whether the file was moved to review or quarantine. Do not upload personal ebooks or OCR text.


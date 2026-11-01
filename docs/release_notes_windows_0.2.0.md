# Manage Your Library 0.2.0 for Windows

This stable Windows release improves metadata-processing speed while preserving the conservative file-safety model introduced in `0.1.0`.

## Performance and metadata quality

- Expensive OCR is deferred until fast local analysis cannot identify a book confidently.
- Metadata processing can run with controlled parallel workers.
- Tkinter updates from background work are routed through a safe main-thread queue.
- Sequential and parallel snapshots were compared with disposable fixtures and produced zero differences.
- Main versus candidate quality regression checks produced zero regressions.
- Metadata quality regression tooling protects known identification behavior.

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

## Validation scope

- Automated suite: `160` tests passed.
- Functional regression subset: `36` tests passed.
- Sequential versus parallel snapshot: `0` differences.
- Main versus candidate quality regressions: `0`.
- Frozen EXE startup, reopen, configuration persistence, normal close, and residual-process checks passed with an isolated temporary profile.
- Frozen image OCR and scanned-PDF OCR/PDFium buttons were checked manually with synthetic fixtures.
- Add books, duplicate quarantine, Undo, manifest, and journal behavior remain covered by isolated automated tests and the earlier frozen-EXE click-through.

No personal library was used during release validation.

## Residual risk

The post-merge frozen-EXE click-through repeated image OCR and scanned-PDF OCR/PDFium checks. It did not repeat manual clicks for Add books, duplicate quarantine, or Undo. Those flows were checked visually before the merge and remain covered afterward by isolated automated tests. This release does not claim post-merge manual clicks that were not performed.

## Basic use

1. Start the EXE and choose a personal library folder.
2. Use **Add books** to move new books into the selected library.
3. Use **Search metadata** when files should only be renamed in their current folders.
4. Review uncertain additions in `PARA REVISAR NUEVAMENTE`.
5. Inspect `.trash_manageyourlibrary/` before manually cleaning quarantined files.

Test the application with a temporary folder before using it on an important library.

## Known limitations

- Linux and macOS build scripts are prepared but are not validated release artifacts for `0.2.0`.
- External metadata quality depends on the upstream providers and network availability.
- OCR intentionally analyzes a limited number of pages and remains conservative for weak evidence.
- Permanent quarantine cleanup remains a manual user decision.

## Windows artifact

The Windows EXE is attached separately to the GitHub Release and is not committed to this repository. Verify its SHA256 against [windows_0.2.0_checksums.md](windows_0.2.0_checksums.md):

```text
8E5B86393ED5A16DF533E3CCD020A1734ED28E854F9FA1FA902D59D94864FC78
```

- Artifact: `ManageYourLibrary.exe`
- Size: `107380918` bytes
- Functional source commit: `e8ca259`

This official checksum was calculated from the asset downloaded from the published GitHub Release.

## Reporting problems

When reporting an issue, include the release version, Windows version, action performed, visible error text, and whether the file was moved to review or quarantine. Do not upload personal ebooks or OCR text.

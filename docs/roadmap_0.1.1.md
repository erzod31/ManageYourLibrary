# Roadmap for 0.1.1 maintenance

## Purpose

The `0.1.1` cycle is reserved for validated post-release bugs and small, reviewable improvements discovered while using Windows release `v0.1.0`.

Do not use this cycle for a large refactor, broad redesign, or speculative behavior changes. Keep each correction narrow, covered by tests, and easy to review.

## Compatibility rules

Every maintenance change must preserve:

- safe file handling without irreversible deletion as the first action;
- **Add books** moving accepted files into the configured library;
- **Search metadata** renaming files in place without moving them into the library;
- `.trash_manageyourlibrary/` quarantine for discarded files;
- recoverable Undo operations where supported;
- the persistent transaction journal;
- atomic writes for critical JSON state;
- local Tesseract OCR;
- bundled PDFium support for scanned PDFs;
- offline conservative behavior;
- the absence of Google Books;
- the absence of cloud OCR and document uploads;
- the absence of `rapidfuzz`.

## Maintenance workflow

For each reported bug:

1. Reproduce it with disposable fixtures or a temporary library.
2. Create a small branch or a narrowly scoped commit.
3. Change only the behavior required to fix the confirmed bug.
4. Add or update focused regression tests.
5. Run the full automated suite.
6. Validate file safety boundaries when the change touches moves, quarantine, Undo, journal, index, or metadata rename-in-place.
7. Keep generated EXE, `dist/`, `build/`, and temporary validation folders outside Git.

## Minimum checklist before publishing 0.1.1

- [ ] At least one real, validated maintenance correction exists.
- [ ] No large refactor was included.
- [ ] `python -m compileall .` passes.
- [ ] `python -m unittest discover -s tests` passes.
- [ ] `git diff --check` passes.
- [ ] **Add books** remains validated with disposable fixtures.
- [ ] **Search metadata** still renames in place.
- [ ] Quarantine, Undo, journal, and atomic JSON writes remain intact.
- [ ] OCR remains local and PDFium remains bundled.
- [ ] No Google Books, cloud OCR, user-document upload, or `rapidfuzz` dependency was introduced.
- [ ] Windows EXE is rebuilt only when a release candidate is intentionally prepared.
- [ ] Final EXE checksum is calculated from the published GitHub Release asset.
- [ ] No EXE, `dist/`, or `build/` content is committed.

## Version note

This document plans the next maintenance cycle. It does not change the current application version, create a tag, or publish a release.

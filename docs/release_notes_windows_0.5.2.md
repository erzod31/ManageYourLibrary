# Manage Your Library 0.5.2 for Windows

Prepared maintenance release focused on safer file operations, preservation of
confirmed metadata and smoother interaction with large libraries.

## Clean first launch

New users start without books, saved preferences, history or pending work. The
empty library screen offers a translated choose-folder action; no library path
is prefilled and nothing is indexed until the user selects a folder. The system
language and appearance are used, and optional local AI remains disabled.
Windows packages include OCR and PDF rendering without requiring Python.

Builds exercise the actual Tk workspace in an isolated fresh profile before
packaging. Release preparation rejects bundled books, personal-state files and
caches. Existing users keep their own data on upgrade; this is not a reset.

## Safety and catalog integrity

- Local-AI filename signals retain only the basename and actual file extension
  for Windows, UNC and POSIX paths, even when imported on another operating
  system; parent directories are not included in these signals.
- Destination collisions cannot silently overwrite a book, including moves
  between drives, rollback and quarantine restoration.
- Undo verifies recorded content hashes. Unverifiable or ambiguous legacy
  actions remain pending for review rather than changing files automatically.
- Reindexing preserves confirmed metadata, series, tags and favorites only when
  the live file still matches the recorded content.
- Saved titles are used for display and search; catalog synchronization retains
  corrected editions and human identity locks.

## Interface and covers

- A bounded pool of 30 reusable cover cards avoids rebuilding the grid on every
  search or page change. Large tables load in cancellable batches.
- Splitters resize live; cover relayout is throttled, and changing a view no
  longer reapplies the whole theme.
- Worker callbacks have a time budget. Obsolete cover requests are skipped;
  offline misses can retry when connectivity returns.
- Rounded surfaces use antialiased reusable corners and bounded button-image
  caches; PDF thumbnails render at an appropriate scale and close bitmaps.

## Safety and local runtime

Recoverable quarantine in `.trash_manageyourlibrary/`, transaction journaling,
durable plans and Undo remain available. Tesseract OCR and pypdfium2 PDF rendering
are bundled. OCR remains local; the application does not upload documents.
Optional metadata lookup and remote cover requests can be disabled in offline
mode. Ambiguous identities still require human review.

Builds use hash-locked Windows dependencies. The package preparation command
rejects stale source fingerprints and personal-state files, and generates a
portable ZIP, installer copy and SHA-256 checksums outside Git.

## Publication status

The artifacts are prepared locally, not automatically published to GitHub.
Automated runtime checks do not certify visual behavior or an installed upgrade.
See [windows_0.5.2_checksums.md](windows_0.5.2_checksums.md) for the exact revision,
tests, hashes and remaining manual approval before public distribution.

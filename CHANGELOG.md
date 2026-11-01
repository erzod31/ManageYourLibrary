# Changelog

## Unreleased

## 0.5.5 - 2026-10-28

- Add user-initiated binary update UIs and verified, platform-specific handoff
  on desktop and Android. Retain product, AppId, package/bundle identifiers,
  signatures and user data; no update is applied automatically at launch.
- Use the existing public GitHub release channel for desktop and the paired
  PC's signed bundle for Android. Keep native confirmations, reject altered
  packages/wrong identities/downgrades, and preserve portable rollback folders.
- Fix raw Windows ZIP separators in APK assets; verify with actual Android
  asset access and fake native installer requests. Preserve all books,
  catalog/profile state and `.trash_manageyourlibrary/`.
- Prepare native builds without overwriting earlier outputs; preserve the
  published macOS bundle ID and write version metadata before signing.

## 0.5.4 - 2026-10-28

- Add a native Android companion for the private desktop library through
  Tailscale HTTPS. Target Android 17 (API 37), request local-network permission
  when pairing, and keep credentials encrypted with Android Keystore.
- Add visible desktop activation, deactivation, expiring single-use pairing
  codes and device revocation. Access is off at launch; existing Tailscale
  endpoints are preserved.
- Browse/search books, view details and full PC paths, edit catalog metadata,
  transfer verified copies, and request local desktop analysis. Imports and
  quarantine use durable preview/confirmation plans and recoverable Undo.
- Preserve all books, catalog data, history and `.trash_manageyourlibrary/`.
  Android contains no OCR models, advertisements or analytics.

## 0.5.3 - 2026-10-28

- Replace Tesseract with local Indra OCR 1.1.2 and pinned, hash-checked models.
  Reuse one cancellable worker for text and geometry, release it after idle,
  bound session caches and avoid repeated language/segmentation passes.
- Package all OCR models and runtime dependencies for offline first use. Include
  model license, attribution and installer acceptance; retain original books,
  catalog, history, pending plans and `.trash_manageyourlibrary/`.
- Keep PDF pages streaming and close native resources promptly. A standalone
  ISBN does not stop evidence gathering. Invalidate stale analysis cache entries
  without deleting user data or human corrections.

## 0.5.2 - 2026-10-06

- Start new profiles with an empty library field and a translated choose-folder
  action. Add an isolated frozen first-launch gate checking empty/default state
  and no automatic book operations or network requests; reject books, caches,
  models and personal-state files when packaging clean releases.

- Make the equal-size mutation-during-hash regression deterministic on Windows
  by explicitly advancing the fixture timestamp; keep the safety rejection.

- Strip Windows, UNC and POSIX parent paths from local-AI filename signals on
  every host, including extension extraction. Make the Windows launcher test
  independent of native slash conventions and cover cross-platform privacy.

- Add a frozen local runtime self-test for Tk, bundled OCR languages, image OCR
  and PDFium rendering/OCR. Verify release payloads and source fingerprints
  before packaging portable archives, installers and SHA-256 records.
- Ignore catalog databases and thumbnail caches; include version and bundled
  runtime assets in build fingerprints while excluding derived checksum reports.

- Reuse a bounded 30-card Tk pool for cover search/pagination, populate large
  tables in cancellable batches, throttle grid relayout to a frame, and enable
  live splitter resizing. Avoid reapplying the whole theme on page/view changes.
- Give worker-to-UI callbacks an 8 ms time budget, skip obsolete cover jobs,
  cache bounded button photos and render rounded surfaces with antialiased
  nine-slice corners. PDF covers render at thumbnail scale and close bitmaps.
- Add isolated native Tk fluency measurements and scheduling/render regressions.

- Reject destination races without overwriting books, including cross-volume
  copies, rollback and quarantine restoration. Undo now checks recorded content
  hashes; unverifiable or ambiguous legacy actions remain pending for review.
- Preserve confirmed metadata and organizing fields on reindexing, revalidate
  annotated files and prevent a replacement from inheriting the old identity.
  Display and search now honor saved titles; SQLite synchronizes corrected
  editions, series and tags while retaining manual identity locks.
- Normalize legacy favorite flags when toggling favorites. Retry deferred
  offline covers online, shorten transient remote misses, and allow a new view
  to request covers independently of a pending previous view.
- Add audit regression tests and isolate workflow-test catalog databases.

## 0.5.1 - 2026-09-29

- Stabilizes pointer feedback by preventing tooltip interception, suppressing
  nested-card hover flicker, caching rounded hover surfaces, and showing a hand
  cursor only for controls that can currently be activated.
- Makes author, series, tags, and favorite state directly interactive in the
  book inspector, with matching icons, theme-aware states, and catalog filters.
- Formalized the analysis/UI boundary with typed result and progress contracts,
  and isolated the main-thread callback queue from the analysis pipeline.
- Added a prepared catalog view index and a reproducible 1k/10k/50k benchmark,
  so search, format filtering, and statistics are not recomputed per keystroke.
- Added keyboard activation and focus styling to rounded controls, translated
  names/tooltips for icon-only actions, page shortcuts, and an explicit
  packaged-build accessibility validation checklist.
- Unified native build gates around Python 3.12, tests, source/frozen smoke,
  catalog performance checks, onedir artifacts, and provenance manifests; added
  cross-platform source CI and a measured Tkinter/PySide6 decision gate.
- Build manifests now fingerprint tracked and untracked build inputs and keep
  automated, manual UI, and signing validation states distinct.

### Maintenance and architecture

- Extracts live file hashing and partial signatures into a focused core service, with before/after file-state validation during duplicate comparisons.
- Moves library and operation configuration validation into `core/config_store.py` while preserving unrelated settings through atomic writes.
- Extracts filename sanitization, mojibake repair, readable-title cleanup, author-alias handling, and suggested-name construction into `core/naming.py`.
- Revalidates file state before and after hashing, narrows silent exception handling in durable file operations, and rolls a move back when destination verification fails.
- Removes the unreachable legacy interface, obsolete global-scroll handlers, and the superseded embedded PNG icon payload.
- Removes only regenerated build output and caches; catalog, configuration, quarantine, journal, plans, backups, history, and confirmed corrections remain untouched.
- Documents the technology-stack decision: retain the Python core and current Tkinter UI, measure explicit migration triggers, and prefer a staged PySide6 view migration if those triggers are reached.

## 0.5.0 - 2026-09-28

### Product direction and durable catalog

- Adds a non-destructive SQLite catalog that separates works, editions, and concrete files while keeping the portable JSON index as a compatibility and recovery surface.
- Migrates the existing index in the background and marks unavailable files without deleting their catalog records.
- Persists title, author, ISBN, language, publisher, year, series, edition, cover, confidence, and field provenance.
- Preserves confirmed human corrections across rescans and prevents automated refreshes from overwriting locked identity fields.
- Adds a manual metadata editor that updates only the catalog; it never renames or moves the source file.

### Workflow and interface

- Expands the editorial sidebar to Library, Authors, Series, Tags, Favorites, Import, and Reviews; the status strip remains the entry point to Activity.
- Adds functional catalog scopes for authors, series, tags, and favorites without duplicating or changing book records.
- Introduces a complete 24 px rounded-line icon family with theme-aware terracotta active states across navigation, search, views, details, file actions, metadata, and Undo.
- Adds translated hover explanations to the primary sidebar destinations while keeping the lower appearance and settings controls quiet.
- Keeps both side columns static while the center library and long workflow pages retain contextual mouse-wheel scrolling.
- Adds pending-review counts and resumes durable review sessions instead of forcing a new scan.
- Groups the book inspector into Identity, Edition, File, and Provenance, with full-path copy and reveal-in-folder actions.
- Adds System, Light, and Dark appearance preferences while retaining the theme control on every page.
- Adapts the sidebar and details inspector to narrower windows and lowers the minimum supported window size.
- Makes the left navigation and right inspector widths directly adjustable from visible drag dividers.
- Routes mouse-wheel scrolling to the content under the pointer, including covers, tables, long pages, logs, and the book inspector.
- Gives the library search bar a full-width, taller treatment with an accent outline and visible `Ctrl+K` shortcut.
- Replaces the legacy search bitmap with a crisp vector-like magnifier that follows the current accent color.
- Uses native proxy sash dragging so panel movement stays responsive even with a full cover grid.
- Reflows existing cover cards in place instead of destroying, recreating, and reloading them after a width change.
- Defers supersampled rounded-edge rendering until resizing settles, while using lightweight native drawing during active window resizing.
- Uses consistent 8 px control corners and 12 px card corners instead of pill-shaped buttons everywhere.
- Adds keyboard access for search, refresh, metadata editing, and Undo.

### Metadata and covers

- Preserves recognition metadata during incremental index updates and renames.
- Prefers Open Library Cover IDs when available, identifies network requests with the project URL, spaces ISBN cover requests, and retains the bounded lazy WebP cache.
- Expands catalog search to series, language, publisher, ISBN, and tags.

## 0.4.3 - 2026-09-28

### Interface polish

- Replaces jagged Tkinter button outlines with supersampled, antialiased rounded surfaces.
- Applies the complete light or dark palette to combobox fields, arrows, borders, and opened dropdown lists.
- Moves the theme switch to the persistent sidebar so it remains available on every page.
- Shows the complete absolute file path in the selected-book details panel.

## 0.4.2 - 2026-09-28

### Fast web covers

- Uses each book ISBN to request its cover from Open Library only when no usable local cover exists.
- Loads cover thumbnails lazily with at most four concurrent downloads so the interface stays responsive.
- Keeps only visible Tk images in memory and releases them when leaving the library or switching to table view.
- Stores compact WebP thumbnails in a bounded 100 MB disk cache and automatically removes the least-recently-used files.
- Rejects unknown hosts and oversized responses, applies short network timeouts, remembers temporary misses, and respects offline mode.

## 0.4.1 - 2026-09-28

### Editorial visual refresh

- Adopts a warm ivory and terracotta visual system inspired by a personal reading room.
- Uses editorial serif typography for book titles and identity, with neutral sans-serif controls.
- Adds rounded search, filter pills, navigation states, action buttons, content cards, and book inspector.
- Gives covers more space, removes dashboard clutter, and keeps essential collection counts in the sidebar.
- Adds quick EPUB/PDF/other filters, recent/title ordering, responsive cover columns, and a larger selected-book preview.

## 0.4.0 - 2026-09-28

### New interface

- Replaces the single-panel screen with a modern workspace for Library, Import, Reviews, Activity, and Settings.
- Adds responsive cover and table views, live search, format filters, collection statistics, pagination, and a book inspector.
- Extracts local cover thumbnails from images, PDFs, EPUBs, and CBZ files into a bounded application cache.
- Guides imports through Select, Analyze, Review, and Organize stages while keeping the existing journaled, undoable file operations.
- Keeps task progress and cancellation visible in a persistent status strip.
- Preserves English, Spanish, French, and Chinese navigation, controls, and table headings in light and dark themes.

### Cleanup and validation

- Removes temporary build, validation, bytecode, and generated work folders while preserving final installers.
- Retains recoverable duplicate quarantine in `.trash_manageyourlibrary/` as a safety feature, not as temporary data.
- Validates the source application with the full automated suite and dedicated UI foundation tests.

## 0.3.0 - 2026-09-28

### Improved

- Revalidates live SHA-256 values before exact-duplicate actions and verifies destination bytes after every critical move.
- Makes the transaction journal mandatory and reconciles pending operations against the real filesystem during startup recovery.
- Keeps partially failed undo batches resumable at item level.
- Adds durable SQLite operation plans with immutable previews, cancellation, retries, and row-level resume state.
- Migrates older SQLite plan columns in place, reconciles committed journal moves after a crash, and updates only affected index paths after imports, renames, and Undo.
- Reuses one immutable `DocumentContext` hash across cache lookup and persistence while detecting mid-analysis file changes.
- Sends non-exact title matches to manual review instead of automatically replacing or quarantining possible editions and translations.
- Adds structured DOCX, ODT, RTF, FB2 and text readers plus bounded external reader paths for DOC and DjVu.
- Raises the default OCR budget to 12 pages, configurable up to 200, and adds local Dutch OCR data.
- Adds offline metadata mode, provider health tracking, bounded responses, retries, and circuit breaking.
- Introduces a locked, hash-verified Windows build, a checked-in PyInstaller spec, CI validation, build provenance manifest, and Inno Setup recipe.

- Improved local cover OCR for difficult books with multiple image-preparation variants, adaptive Tesseract page segmentation modes, and layout-aware title/author candidates.
- Added conservative comic-archive metadata recovery for CBZ/CBR-style files, including archives mislabeled as `.cbz` but backed by RAR when a local `tar`/libarchive-compatible reader is available.
- Added comic cover extraction and internal-path metadata hints without unpacking archives to a visible temporary folder.
- Avoided treating binary comic archives as plain text evidence; unreadable comic covers now remain conservative instead of producing noisy metadata.
- Improved difficult review-folder recovery for compact filenames, contaminated author/title fragments, multilingual titles, and non-Latin author aliases.
- Changed the folder duplicate checker to compare two selected folders against each other instead of scanning only one folder internally.
- Removed the separate "Analyze review" action because difficult-review resolution now belongs to the normal add/metadata workflow instead of a parallel manual-only path.

### Validated

- Added regression coverage for OCR layout candidates, comic archive cover extraction, RAR-backed `.cbz` handling, comic metadata hints, and stable suggested names such as `Akira Toriyama - Sand Land (2003).cbz`.

## 0.2.0 - 2026-06-01

Stable Windows performance and metadata-quality release.

### Improved

- Deferred expensive OCR until fast local analysis cannot identify a book confidently.
- Added controlled parallel metadata processing while preserving sequential-equivalent results.
- Added metadata quality regression tooling and broader regression coverage.

### Validated

- Confirmed sequential and parallel metadata snapshots produce zero differences on disposable fixtures.
- Confirmed the frozen Windows EXE opens without Python on `PATH`, reopens with an isolated profile, and closes without residual processes.
- Confirmed local Tesseract OCR and PDFium rendering from the frozen UI with synthetic image and scanned-PDF fixtures.
- Preserved recoverable quarantine, Undo, transaction journal, atomic writes, and rename-in-place Search metadata behavior.

## 0.1.0 - 2026-05-31

First stable Windows release.

### Released

- Promoted the tested Windows release candidate after the isolated frozen-EXE click-through passed.
- Confirmed recoverable duplicate quarantine, Undo, rename-in-place metadata search, local OCR, and PDFium rendering with disposable fixtures only.
- Documented the final Windows artifact checksum separately from the source repository.

## 0.1.0-rc1 - 2026-05-31

First Windows release candidate prepared after the safety and modularization phases.

### Added

- Recoverable quarantine under `.trash_manageyourlibrary/` for discarded files.
- Persistent transaction journal and broader Undo coverage for recoverable file operations.
- Atomic writes for critical JSON state.
- Dedicated modules for safe file operations, index storage, history, duplicate detection, scoring, external providers, and metadata orchestration.
- Windows release checklist, isolated manual test plan, and release-candidate build report.

### Validated

- Local Tesseract OCR runtime and required language data are bundled in the Windows EXE.
- PDFium rendering support is bundled through `pypdfium2`.
- The frozen application starts without Python on `PATH` and reopens with an isolated temporary profile.
- Generated builds remain outside Git and are intended to be attached separately to a GitHub Release.


# Manage Your Library

A Python/Tkinter desktop app for organizing a personal digital book library. Windows is the primary tested build target, with separate build scripts prepared for Linux and macOS.

The app can add books to a selected library folder, check for duplicates in the library or in any selected folder, search metadata online, rename files with a consistent format, open the library folder, undo the last action, switch languages, and toggle light/dark mode.

Prepared Windows release: [`0.5.5`](docs/release_notes_windows_0.5.5.md).
Publication and installed-UI approval are separate from building the artifacts;
see the current validation record below before distributing them.

Development continuity and the provenance-aware handoff reconstructed from the
related ChatGPT conversations are documented in
[`docs/PROJECT_CONTEXT_2026-09-28.md`](docs/PROJECT_CONTEXT_2026-09-28.md).

## Main Features

- Add one or more books to a user-selected library folder.
- Detect exact duplicates and possible duplicates before moving files.
- Check duplicate books between two selected folders using the same title/author resolution and visual comparison workflow.
- Search metadata using Open Library, Wikidata, Library of Congress, Crossref, and OpenAlex.
- Deep Identity Scan for difficult files: a local evidence/scoring layer for EPUB, MOBI/AZW/AZW3, PDF, OCR-supported images, and readable comic archives that renames only with high confidence and otherwise sends files to review.
- Optional **Reinforce with local AI** mode for uncertain metadata decisions using llama.cpp portable and Qwen3 GGUF Q4 models. It is disabled by default, uses only minimal signals and real candidates, and never sends books to remote AI services. See [local AI reinforcement](docs/local_ai_reinforcement.md).
- Local OCR for scanned PDFs, image files, and readable comic covers using Indra OCR on CPU.
- Rename books using this format:

  ```text
  Author - Title (Year) [ISBN].ext
  ```

- Search metadata for selected files or folders without moving them.
- Open the active library folder from the app.
- Undo the last move or rename action. Duplicate files that are discarded are moved to an internal quarantine folder before any permanent cleanup.
- Multilingual interface: English, Spanish, French, and Chinese.
- Modern workspace with cover/table library views, search and format filters, collection statistics, guided imports, review queues, activity history, and settings.
- Durable SQLite catalog separating a work, its publication edition, and each concrete file, while retaining the JSON index for portability and recovery.
- Human-confirmed metadata corrections with field-level provenance that survive later scans without renaming or moving the source file.
- Focused Library, Inbox, and Reviews workflow with resumable review sessions and pending counters.
- Local cover previews for supported image, PDF, EPUB, and CBZ files, with a lazy Open Library cover fallback by ISBN.
- Compact WebP cover cache capped at 100 MB; only visible covers stay in memory, and offline mode disables web downloads.
- On first launch, the app uses the system language when supported; otherwise it starts in English.
- System, light, and dark appearance modes available from every page.
- Rounded Tkinter interface.

## First Use

Windows users do not need Python: install `ManageYourLibrary-0.5.5-Setup-x64.exe`
or extract the complete portable ZIP and run `ManageYourLibrary.exe` beside its
`_internal` folder. Do not distribute only the launcher EXE.

New users start with an empty catalog, no selected library, no pending plans or
history, system language/appearance and local AI disabled. Select **Choose
library folder** on the empty library screen, then import your own books. No
folder is scanned or organized until you choose it.

The release contains the application and bundled local OCR runtime, not the
developer's books, catalog, preferences, caches or AI models. User state lives
in the operating system's application-data folder (on Windows,
`%APPDATA%\ManageYourLibrary`). Upgrading or opening the portable edition under
the same Windows account intentionally keeps existing state; it is not a
factory reset. Do not delete that folder just to prepare a release.

If you downloaded the source code from GitHub and already have Python installed, run:

```bat
python main.py
```

When the app opens for the first time:

1. Choose the folder you want to use as your library with **Choose library folder**.
2. Wait for the initial index to be created.
3. Use **Import** to add new books. Confirming an import may move and rename the
   originals; start with disposable copies of a few books.
4. Use **Search metadata** if you only want to rename existing files.

The first launch automatically follows the operating system language if it is supported. If the system language is not available, the app opens in English. After the user chooses a language inside the app, that choice is saved.

## Project Structure

The optional [Android companion](docs/ANDROID_COMPANION.md) connects privately
through Tailscale. Install the matching desktop build, open Settings → Android /
Tailscale, activate access, and pair the phone using the displayed HTTPS address
and single-use code. The PC retains the catalog and local OCR; it must stay on.
Closing the connection panel stops access. The Android interface is in Spanish.

```text
main.py              Main launcher
library_app.py       Tkinter interface and user workflows
library_core.py      Library logic, indexing, metadata, translations, and undo
ocr_engine.py        Local Indra OCR, bounded session cache, and bibliographic evidence
cache_engine.py      SQLite cache for API responses and analysis summaries
core/operation_plans.py  Durable preview, apply, cancellation, and resume plans
core/index_service.py    Incremental updates for paths changed by an operation
core/catalog_store.py    Durable work/edition/file catalog and provenance
core/document_context.py One immutable, memoized file snapshot per identification
core/document_readers.py Structured and bounded document readers
rounded_widgets.py   Rounded widgets and embedded icons
app_icon.ico         Windows executable icon
app_icon.svg         Icon preview/source
BUILD_EXE.bat        Windows build shortcut
platforms/           Platform-specific build scripts
README.md            Main documentation
```

## Run From Python

Requirements:

- Windows, Linux, or macOS for running from source.
- Python 3.10 or newer recommended

Install Python dependencies with:

```bat
python -m pip install -r requirements.txt
```

The identification/OCR stack uses:

- `pypdf` for PDF metadata and text extraction.
- `pypdfium2` for rendering scanned PDF pages to in-memory images for OCR.
- `Pillow` for lightweight image preparation.
- Deterministic standard-library similarity matching for consistent behavior in source and frozen builds.
- Local OCR uses Indra OCR 1.1.2 with ONNX Runtime on CPU; no GPU is needed.
- `ftfy` for Unicode/mojibake repair before title comparison and EXE packaging.
- Pinned OCR models and runtime dependencies are bundled with each native build. Models are prepared at build time, never downloaded while processing books.
- EPUB metadata is read from OPF files; MOBI/AZW/AZW3 metadata and cover references are read from Kindle EXTH records when available.
- CBZ/CBR-style comic archives can provide cover images and short internal-path metadata hints. If a `.cbz` file is actually RAR-backed, the app can use a local `tar`/libarchive-compatible reader when available; otherwise it stays conservative and reports that no readable comic cover was found.
- Difficult files can be cross-checked by [Deep Identity Scan](docs/deep_identity_scan.md), which combines only short local evidence and minimal external candidates. It does not store full book text, does not break DRM, and does not send full pages or OCR output to APIs.

Run:

```bat
python main.py
```

## Build the EXE

Build the matching Android companion first using a JDK 21 and Android SDK
Platform 37 / Build Tools 36.0.0:

```powershell
.\platforms\android\BUILD_ANDROID.ps1
```

Set `JAVA_HOME` and `ANDROID_HOME` to the installed tools. Preserve the private
Android signing key/password outside Git for future APK updates; see
[Android setup and build instructions](docs/ANDROID_COMPANION.md).

On Windows, run:

```bat
BUILD_EXE.bat
```

The diagnosable application folder will be created at:

```text
dist\windows\ManageYourLibrary\ManageYourLibrary.exe
```

The build runs the complete test suite, uses hash-locked dependencies, runs a
frozen smoke test, and writes `build-manifest.json`. Run
`platforms\windows\BUILD_INSTALLER.bat` afterward to create the Inno Setup
installer when Inno Setup 6 is installed.

After both builds, run `python tools/package_windows_release.py` to verify the
matching source fingerprint, frozen runtime checks and clean payload, then
generate the portable ZIP, copied installer and SHA-256 file in `dist/release/`.
The runtime check initializes Tkinter and exercises synthetic local OCR/PDF
rendering; it does not replace an installed-application visual click-through.

For GitHub, keep the source code in the repository and attach the generated `.exe` only to a GitHub **Release**. Do not commit generated EXE/build files to the main repository.

Before publishing a Windows EXE, follow:

- [`docs/release_notes_windows_0.5.5.md`](docs/release_notes_windows_0.5.5.md)
- [`docs/windows_0.5.5_checksums.md`](docs/windows_0.5.5_checksums.md)
- [`docs/windows_frozen_exe_manual_validation.md`](docs/windows_frozen_exe_manual_validation.md)
- [`docs/manual_click_validation_form_windows.md`](docs/manual_click_validation_form_windows.md)
- [`docs/windows_release_checklist.md`](docs/windows_release_checklist.md)
- [`docs/manual_test_plan_windows.md`](docs/manual_test_plan_windows.md)

Historical release notes and checksums, including `0.5.1`, remain in `docs/`.

## Platform Build Folders

Platform-specific build scripts are kept in separate folders so the app source is not duplicated:

```text
platforms/windows/BUILD_WINDOWS.bat
platforms/linux/build_linux.sh
platforms/macos/build_macos.sh
```

All three scripts build from the same source files in the project root. When the app is modified, rebuild the target platform and it will use the latest code.

PyInstaller should be run on the same operating system as the target:

- Build Windows on Windows.
- Build Linux on Linux.
- Build macOS on macOS.

Outputs are separated by platform:

```text
dist/windows/
dist/linux/
dist/macos/
```

All native builds prepare the same hash-checked Indra models; ONNX Runtime and
OpenCV provide platform wheels. Native Linux/macOS execution must be validated
on those systems; a Windows build does not certify them.

## OCR

OCR is fully local. The app does not upload documents and does not use web OCR services.

- Indra OCR replaces Tesseract. Text, confidence and line positions use one pass.
- Digital PDFs use their existing text first. Scans stream through pypdfium2 one page at a time.
- OCR analyzes up to 12 pages by default, configurable from 1 to 200. An isolated ISBN does not stop evidence gathering.
- One background worker loads models lazily, reuses them between pages, supports cancellation/time limits and exits after 60 seconds idle.
- Session caches are bounded and cleared on exit. Persistent cache summaries contain metadata, not full OCR text.
- Build-time models are pinned to an immutable revision with SHA-256 checks. There is no system OCR fallback or runtime model download.
- Source users prepare models explicitly before running OCR:

```bat
python tools/prepare_indra_models.py
```

The Indra code uses Apache-2.0. Its models and OCR Output use a **modified
OpenRAIL-M license**, with commercial/use restrictions and share-alike conditions.
Read [the full model license](third_party/indra/MODEL_LICENSE.txt) and
[attribution and use terms](third_party/indra/NOTICE.txt). These terms apply in
addition to other component licenses; they do not change the original books.
The installer presents the model license for acceptance. No model weights are
modified. Tesseract files retained in this checkout are legacy assets and are
excluded from new application/installer payloads.

## User Data

The app stores configuration, SQLite metadata/analysis cache, resumable operation plans, index, history, and undo logs in the user data folder:

```text
Windows: %APPDATA%\ManageYourLibrary
macOS: ~/Library/Application Support/ManageYourLibrary
Linux: $XDG_DATA_HOME/ManageYourLibrary or ~/.local/share/ManageYourLibrary
```

The SQLite cache keeps small metadata/API summaries and reusable analysis decisions. OCR text remains session-only in memory.

## Safety Notes

- Only byte-identical files may be handled automatically as exact duplicates, after a fresh SHA-256 comparison. Title matches that may represent another edition, translation, volume, or version go to manual review.
- Replacements are handled defensively: the operation is recorded in a local journal, the previous copy is moved to quarantine first, the preferred copy is moved into place, and the destination is verified.
- `.trash_manageyourlibrary/` is ignored by the library index and by Git. Its manifest records where quarantined files came from and why they were moved. Delete its contents manually only after confirming the library is correct.
- Undo records recoverable moves, quarantines, replacements, review moves, and metadata renames when restoration is still possible.
- If reliable metadata is not found, the app keeps the original filename and sends the file to `PARA REVISAR NUEVAMENTE` when adding books.
- When adding books, files without reliable metadata matches are moved to review and the reason is shown in the activity log.
- Metadata search only renames files in their current location; it does not move them.
- Adding books moves the original file into the selected library folder.

## Identification Algorithm

The app identifies books through a conservative hybrid evidence pipeline and a bibliographic consensus engine:

- Collect local evidence first: EPUB OPF, MOBI/AZW EXTH, PDF metadata/text, ISBN, DOI, first pages, and OCR only when needed.
- Process evidence progressively: cheap metadata, real digital text, OCR hints only when needed, selective external verification, then final confidence.
- Use a conservative fast path for clean structured EPUB/MOBI metadata, falling back to the full resolver whenever confidence is not clearly safe.
- For comic archives, use internal folder/file names and cover OCR as weak local hints, then require bibliographic confirmation before an automatic rename.
- Analyze selected files with a bounded lightweight worker pool while keeping deferred OCR in a separate conservative queue.
- Treat the current filename as weak evidence because it may already be contaminated by older bad names.
- Use ambiguous authors only as search hints, never as final authors.
- Generate a small set of focused web queries when local evidence is incomplete or ambiguous.
- If the first pass is not reliable enough, run an internal investigation pass that tests cleaned local hypotheses, compares title/author variants against already collected evidence, rejects contaminated titles, and only then runs active web recovery without repeating already-tried queries.
- Share collected evidence across the whole process so local extraction, web providers, recovery, duplicate checks, and OCR do not work from separate contradictory assumptions.
- Cache only successful web metadata responses, prune the cache, and retry later after provider/network failures instead of permanently caching failed lookups.
- Score candidates with positive and negative evidence: ISBN, title similarity, author confirmation, source, document type, bibliographic role, and contradictions.
- Treat OCR as a proposing evidence source, not as an automatic decision maker.
- Treat compacted or contaminated filenames as hypotheses to test, including multilingual and non-Latin cases, rather than as final metadata.
- Use a lightweight RDA/MARC-inspired hierarchy to distinguish title, author, publisher, translator, editor, compiler, series, edition, and file copy.
- Prefer sending uncertain cases to `PARA REVISAR NUEVAMENTE` over renaming incorrectly.
- Rename only when confidence is high and the final author is reliable.
- Skip web calls when local structured metadata is already strong enough.

## Performance Pipeline

- Clean structured metadata can finish in the fast phase without invoking OCR.
- Files that still need OCR are deferred to a separate queue; PDF and image OCR remains capped to the first useful pages.
- Lightweight file analysis uses a bounded worker pool. Deferred OCR uses only one worker by default and never more than two.
- Tkinter updates emitted by the new worker pools are queued and drained by the main UI thread.
- Low-confidence results remain conservative and continue to use `PARA REVISAR NUEVAMENTE`.

## Metadata Providers

The active metadata providers are:

- Open Library for general book metadata and ISBN confirmation.
- Wikidata as secondary verification.
- Library of Congress as bibliographic fallback.
- Crossref for DOI/academic documents.
- OpenAlex for DOI/academic documents.
- Internet Archive and Gutendex/Project Gutenberg as auxiliary recovery sources only, after the main providers fail to reach enough confidence.

APIs are called through official endpoints only; the app does not scrape HTML.
Metadata queries may send a derived title, author, ISBN, or DOI to those providers;
book files, pages, and OCR text are not uploaded. The Settings panel provides a
fully offline metadata mode.


## Update from the app

Desktop Settings → **Buscar / instalar actualización**; Android Connection → **Actualizar esta aplicación**. Downloads verify product, platform, version, size, SHA-256 and native signing identities before an explicit native installation request. See [in-app updates and initial migration](docs/IN_APP_UPDATES.md) and [DG-0020 platform validation](docs/in-app-updates-DG-0020.json). A source build or candidate is not a published release.

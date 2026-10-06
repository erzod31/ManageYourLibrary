# Manage Your Library

A Python/Tkinter desktop organizer for your own digital books. Windows x64
packages include local OCR and do not require Python.

Prepared Windows release: [`0.5.3`](docs/release_notes_windows_0.5.3.md).

[Download the latest release](https://github.com/erzod31/ManageYourLibrary/releases/latest)
and [primer uso en español](docs/FIRST_USE_ES.md).

## First use

1. Install `ManageYourLibrary-0.5.3-Setup-x64.exe`, or extract the **complete**
   portable ZIP and run `ManageYourLibrary.exe` beside `_internal`. Do not run
   inside the ZIP or distribute the launcher alone.
2. On the empty catalog, click **Choose library folder** and select a writable
   folder for your books. Wait for any existing books to be indexed.
3. Use **Import** for additional books. Confirmation can **move and rename**
   originals: back up your books and start with disposable copies of a few files.
4. Resolve uncertain matches in Reviews. **Open** uses the system's default
   reader; install or associate a PDF/EPUB reader separately.

No application account or API key is needed. Internet is used for optional web
metadata and covers; offline mode disables those requests. OCR stays local.
Local AI is disabled by default and needs an optional separate engine and model.

New profiles have no books, saved preferences, history or pending plans. Language
and appearance follow the system when supported. No folder is scanned before it
is chosen. On Windows state lives in `%APPDATA%\ManageYourLibrary`. Installer and
portable under the same account intentionally share existing state; upgrading
must not erase it.

## Features and formats

- Cover/table views, search, filters, authors, series, tags and favorites.
- Interactive details and human-confirmed metadata corrections.
- Guided imports, review queues, resumable plans, activity and recoverable Undo.
- Bundled Tesseract and PDFium for local image/scanned-PDF OCR.
- Local document evidence and optional bibliographic metadata lookup.
- Bounded cover loading, capped disk cache and offline controls.
- English, Spanish, French and Chinese; system, light and dark appearance.

DOC extraction needs LibreOffice; DjVu extraction needs DjVuLibre. Some CBR
archives need a compatible archive reader. Reading applications and optional AI
models are not bundled. The application does not remove DRM.

## Safety and privacy

OCR remains local and the app does not upload documents. Web metadata queries
may send a short title, author, ISBN or DOI. Uncertain editions, translations and
volumes require review. Discarded duplicates remain recoverable in
`.trash_manageyourlibrary/`; do not empty it casually. Preview does not change
originals. Catalog and settings are preserved on upgrade.

The public snapshot excludes personal libraries, developer profiles, local paths,
private development conversations and earlier Git history. Product attribution
uses the application name. Third-party notices are retained.

Executables are **unsigned**. Automated checks do not replace manual installed-UI,
upgrade or uninstall tests. See each release's exact validation record.

## Source and builds

Use Python 3.12 for the Windows build:

```text
python -m pip install --require-hashes -r requirements.lock
python -m unittest discover -s tests
python main.py
```

Run `BUILD_EXE.bat`, then `platforms\windows\BUILD_INSTALLER.bat` (Inno Setup 6)
and `python tools/package_windows_release.py`. Outputs are in `dist/release/`.
Linux/macOS scripts require native OCR runtimes. Source CI does not certify
native Unix release packages.

## Documentation

- [Release notes](docs/release_notes_windows_0.5.3.md)
- [Build evidence and checksums](docs/windows_0.5.3_checksums.md)
- [Frozen and manual validation](docs/windows_frozen_exe_manual_validation.md)
- [Manual form](docs/manual_click_validation_form_windows.md)
- [Release checklist](docs/windows_release_checklist.md)
- [Manual test plan](docs/manual_test_plan_windows.md)
- [Identity scan](docs/deep_identity_scan.md)
- [Optional local AI](docs/local_ai_reinforcement.md)
- [Third-party notices](THIRD_PARTY_NOTICES.md)

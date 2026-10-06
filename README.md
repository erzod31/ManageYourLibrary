# Manage Your Library

A Python/Tkinter desktop organizer for your own digital books. Windows x64
packages include local OCR and do not require Python.

Published Windows release: [`0.5.3`](docs/release_notes_windows_0.5.3.md).

[Download the latest release](https://github.com/erzod31/ManageYourLibrary/releases/latest)
and [primer uso en español](docs/FIRST_USE_ES.md).

## Downloads and requirements

Choose the **installer** for normal use, or the portable ZIP if you prefer an
application folder without installation. GitHub's source-code ZIP is not the
ready-to-run application. These links are for the same published version, 0.5.3:

| Download | Purpose |
| --- | --- |
| [Windows x64 installer](https://github.com/erzod31/ManageYourLibrary/releases/download/v0.5.3/ManageYourLibrary-0.5.3-Setup-x64.exe) | Install the application and optional desktop shortcut. |
| [Windows x64 portable ZIP](https://github.com/erzod31/ManageYourLibrary/releases/download/v0.5.3/ManageYourLibrary-0.5.3-Windows-x64-portable.zip) | Extract the complete folder before running. |
| [SHA-256 checksums](https://github.com/erzod31/ManageYourLibrary/releases/download/v0.5.3/SHA256SUMS-0.5.3.txt) | Check downloaded files against this release. |
| [Build manifest](https://github.com/erzod31/ManageYourLibrary/releases/download/v0.5.3/build-manifest-0.5.3.json) | Exact build source, dependencies and recorded automated gates. |

- The distributed packages target **Windows x64**. Local package checks ran on
  Windows 11; other Windows versions/architectures are not certified by that
  result. Linux/macOS have source/build instructions, not published native packages.
- Python, a separate Tesseract installation, an application account and API keys
  are **not required** for the Windows packages.
- Choose a writable library folder and leave space for your books, the extracted
  application and its caches. External PDF/EPUB reading applications are separate.
- Internet is optional for library management/local OCR, but required for web
  metadata and remote cover lookup. Optional AI and special-format tools are separate.
- Executables are **unsigned**. Manual installed-UI, upgrade and uninstall checks
  remain unperformed; see the [actual validation record](docs/windows_0.5.3_checksums.md).

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

### Supported library formats

The library index/import accepts the following file extensions. Acceptance does
not guarantee readable content, complete metadata or successful identification.
Corrupt, encrypted/DRM-protected or unusual files may need manual review.

| Formats | Extraction and dependencies |
| --- | --- |
| `.pdf` | Embedded text/metadata, plus bundled PDFium/Tesseract for scanned pages. |
| `.epub` | EPUB metadata and readable content; local cover extraction/OCR when needed. |
| `.mobi`, `.azw`, `.azw3` | Kindle metadata/content evidence when readable; no DRM removal. |
| `.fb2`, `.txt`, `.rtf`, `.docx`, `.odt` | Built-in structured/text readers; no LibreOffice required for these formats. |
| `.doc` | Legacy DOC extraction needs `soffice` or `libreoffice` available on PATH. |
| `.djvu` | Text extraction needs DjVuLibre's `djvutxt` available on PATH. |
| `.cbz`, `.cbr` | Readable comic cover evidence; RAR-backed archives depend on a compatible local archive reader. |

Metadata analysis can also process supported image files (`.jpg`, `.jpeg`, `.png`,
`.tif`, `.tiff`, `.bmp`, `.webp`) with local OCR. These images are not normal
book entries in the library index. A cover or confident identity is not guaranteed
for every book; unresolved or conflicting evidence stays for review.

## Verify a download

Download `SHA256SUMS-0.5.3.txt` from the same release. Open PowerShell in the folder
containing the downloaded files and run the command for the file you chose:

```powershell
Get-FileHash -LiteralPath '.\ManageYourLibrary-0.5.3-Setup-x64.exe' -Algorithm SHA256
Get-FileHash -LiteralPath '.\ManageYourLibrary-0.5.3-Windows-x64-portable.zip' -Algorithm SHA256
```

Compare the reported `Hash` with the matching filename in the checksum file:

| File | Expected SHA-256 for 0.5.3 |
| --- | --- |
| Installer | `E43DE948B8ED1DC1795D7EECE40519CB1B48BB2A514E012A41CE6EDDBBA310E6` |
| Portable ZIP | `91B316DA15F1B8D55D49DD2856CD0F7922A72DFF157F6E363EE2F1D79F43F131` |

Upper/lowercase does not matter. If the value differs, **do not run the file**;
download it again from the official release and recheck. SHA-256 verifies that
the bytes match this published package; it is not a digital signature or a safety
certification. See [Microsoft's Get-FileHash documentation](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.utility/get-filehash?view=powershell-5.1).

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

## Backups, updates and restoration

The application folder/installer is **not** a backup of your library or profile.
For a filesystem backup:

1. Finish or cancel active work and close the application before copying databases.
   Do not erase unfinished plans, journals or quarantine to make a backup look clean.
2. Copy your **whole library folder**, including hidden `.trash_manageyourlibrary/`
   folders and their manifests. Include any other source/review/quarantine folders
   referenced by pending operations.
3. On Windows, copy the **whole** `%APPDATA%\ManageYourLibrary` folder. It contains
   settings, index/catalog, confirmed metadata, review state, pending plans,
   journals and Undo/activity history. Backing up only `config.json` is insufficient.
4. Keep the library and profile snapshots together and record their folder paths.
   This is a manual backup procedure, not a claim of automatic backup scheduling.

Before updating, keep those backups. Close the app, then install the new version
or extract a portable release into a **new application folder**; do not mix old
and new `_internal` files. Both editions intentionally use the same Windows
profile. Do not delete `%APPDATA%\ManageYourLibrary` or quarantine as an update step.
Preservation is the design intent; manual upgrade/uninstall approval is still pending.

Before restoring, close the app and back up the **current** books/profile first.
Restore a matching library/profile snapshot, retaining recorded folder locations
where possible. If locations changed, select the correct library and let it
reindex, then verify the results. Do not resume old plans or use Undo until their
recorded source/destination paths match the actual files. An old profile does not
restore missing book files by itself.

## Troubleshooting

| Problem | What to check |
| --- | --- |
| Empty library on first launch | Expected: choose a library folder and wait for indexing, or use Import. |
| Missing `_internal`, Python DLL or bundled runtime error | Extract the entire portable ZIP to a new folder, or use the complete installer. Do not copy/run only the launcher. Verify the download hash. |
| Windows security warning or application blocked | Packages are unsigned. Verify the official origin and hash; do not disable Defender/Smart App Control or add broad exclusions as a workaround. A hash does not override a security policy. Report the exact warning. |
| Access denied or import cannot write | Choose a library folder writable by your account; avoid protected system/application folders. Keep originals and review the activity result before retrying. |
| Open does not launch a reader | Associate the file extension with an installed compatible reader. Open is not an embedded ebook reader. |
| Metadata/cover unavailable | Check Internet and offline settings; providers may be unavailable or have no match. Local evidence remains usable; uncertain results need review. |
| DOC/DjVu/archive reader unavailable | Check the format-specific tools above and their PATH availability. These extras are not needed for ordinary PDF/EPUB extraction. |
| OCR is slow or incomplete | Scans can be expensive. OCR defaults to 12 pages and can be adjusted from 1 to 200 in settings. Keep work cancellable and review uncertain output; do not force a confident rename. |
| File is missing after an import | Import may move/rename originals. Check the book's full path in Details, Reviews, activity and quarantine before importing again or attempting Undo. |
| Old library/settings appear in the portable edition | The same Windows account shares `%APPDATA%\ManageYourLibrary`. Portable is not a factory reset; do not delete that folder as a quick fix. |

Windows may block an unsigned app depending on its security policy. See
[Microsoft's Smart App Control explanation](https://support.microsoft.com/en-us/windows/security/threat-malware-protection/smart-app-control-frequently-asked-questions).

## Report a problem

Use [GitHub Issues](https://github.com/erzod31/ManageYourLibrary/issues/new) with
the app version, Windows version/architecture, installer or portable edition,
steps to reproduce, expected/actual result and the exact error message. Say
whether an operation moved a file and whether a review/pending plan remains.
Posting an issue requires a GitHub account; using the application does not.

**Redact personal paths, account names, book titles and other private information**
from screenshots/logs. Do not upload your books, complete OCR text, application
profile, catalog databases, configuration, Undo journals, quarantine or credentials.
Use a small synthetic example when possible. Never delete evidence of a partial
operation merely to reproduce an issue.

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

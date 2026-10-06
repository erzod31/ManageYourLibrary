# Project context

Manage Your Library is a Python/Tkinter desktop library organizer. This public
snapshot starts with fresh Git history. Private conversations, local paths,
old build reports, old release assets and personal library data are excluded.

## Safety

Preserve books, catalog, settings, quarantine, transaction journals, pending plans,
Undo history, backups and human corrections. Matching titles cannot prove that
editions, translations, volumes or versions are interchangeable. Revalidate file
identity before changes and retain recoverable records after partial or failed
operations. Preview must not modify originals. OCR and optional AI remain local.

## Implementation

- `library_app.py` and `ui/workspace.py`: workspace and guided import.
- `core/catalog_store.py`: durable catalog and confirmed metadata.
- `core/file_transactions.py`, `core/operation_plans.py`, `core/undo_history.py`:
  recoverable operations and resumable plans.
- `ocr_engine.py`, `core/document_readers.py`: local document extraction.
- `tools/runtime_self_test.py`: bundled Tk, OCR and PDF-rendering checks.
- `tools/first_use_self_test.py`: actual Tk workspace with isolated fresh state.
- `tools/package_windows_release.py`: fingerprint, validation and payload gates.

## Verification

Use the existing platform scripts and current tests. Windows includes OCR but
not books or optional AI models. New profiles start with a blank library field
and no automatic scan. Existing profiles are preserved; portable is not a reset.
Record actual source revision, fingerprint, dependencies, artifact hashes, tests
and signing status. Automated Tk initialization is not manual installed-UI,
upgrade or uninstall approval.

# Manage Your Library 0.5.3 for Windows x64

Clean public snapshot with product-only attribution, fresh Git history and
first-use instructions. Private reports, conversations, old packages and personal
application state are excluded.

New profiles have a blank library field, empty catalog, no pending work/history,
system language/appearance and local AI disabled. Choose a writable folder and
use Import. Import can move and rename originals after confirmation; start with
disposable copies. Existing users keep their own state.

The installer requires no Python. Extract the complete portable ZIP and keep
the launcher beside `_internal`. Open uses an external default reading app.

Bundled Tesseract and pypdfium2 provide local image/scanned-PDF OCR.
OCR remains local; the app does not upload documents. Optional metadata lookup
and covers use Internet and can be disabled in offline mode. Local AI needs an
optional separate runtime/model.

Ambiguous identities require review. Discarded duplicates remain recoverable in
`.trash_manageyourlibrary/`. Durable plans, journal and Undo retain partial or
failed operations. Titles alone cannot identify interchangeable editions/volumes.

Builds use hash-locked dependencies, automated smoke/catalog tests, bundled
runtime checks and an isolated first-use Tk workspace. Packaging verifies the
source fingerprint and rejects books, models, caches and personal state.

Executables are unsigned. Automated checks do not certify manual installed-UI,
upgrade or uninstall behavior. Actual current build evidence and hashes are in
[windows_0.5.3_checksums.md](windows_0.5.3_checksums.md).

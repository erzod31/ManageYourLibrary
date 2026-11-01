# Manage Your Library 0.5.5 candidate · in-app updates

Adds explicit in-app binary update controls on Windows, Android, Linux and
macOS source. See [the update guide](IN_APP_UPDATES.md) and
[DG-0020 platform evidence](in-app-updates-DG-0020.json).

The desktop queries a configurable real GitHub release channel, rejects other
products/platforms and unauthorized downgrades, verifies download size/SHA-256
and native identities/signatures, and asks before invoking the native installer
or portable update helper. User data and `.trash_manageyourlibrary/` are
preserved. Android uses the paired PC's signed APK and its normal authorization
and package installer, preserving the existing package name and signing key.

Old binaries need one manual transition. A candidate is not a published update;
availability depends on actual matching assets in the selected channel.
Native macOS/Linux build and validation status must be read from DG-0020.

Indra and pypdfium2 remain local on the PC with hash-locked Windows dependencies.
OCR remains local and does not upload documents to update servers. Optional
metadata lookup follows the existing PC configuration. No source/model OCR
behavior is replaced by the updater.

The APK packager also fixes noncanonical Windows ZIP separators in assets,
verified through actual Android asset access. First-use defaults remain empty,
with no automatic network/update/OCR work. Installer compilation, independent
extraction and frozen execution are distinct from actual installation/upgrade;
no real Windows installer/actual updater is run in the shared Windows session.

Artifact checks: [windows_0.5.5_checksums.md](windows_0.5.5_checksums.md).

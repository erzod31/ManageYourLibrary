# Manage Your Library 0.5.4 · Android companion

The desktop application now supports an optional native Android companion over
private Tailscale HTTPS. See [Android setup](ANDROID_COMPANION.md).

Access starts disabled. In Settings, open Android / Tailscale, activate access,
copy the HTTPS address, and pair the phone with the single-use 8-digit code.
Both devices must be connected to the same tailnet. The PC must remain on.
Only a dedicated HTTPS endpoint is used; existing Serve routes are preserved.

The phone can browse/search, see full PC paths and covers, edit favorites/tags/
series and catalog metadata, upload a copy, preview imports, and confirm safe
recoverable operations. Downloaded copies require a compatible Android reader.
Quarantine is recoverable through Undo and `.trash_manageyourlibrary/`;
there is no remote permanent-delete operation. Originals on the phone remain
untouched. Changed files and occupied destinations block operations for review.

Indra OCR and pypdfium2 remain bundled on the PC with hash-locked dependencies
and fixed, hash-checked models. OCR remains local. The companion does not upload documents
to external OCR services. Optional metadata lookup follows the PC's
existing provider/offline settings. Model license restrictions and attribution
remain available in the installer and through the companion's connection page.

The Android build targets API 37 (Android 17), uses platform Java APIs without
native libraries, and requires Android 8 or newer. The intended phone is an
updated Galaxy S26 Ultra. Emulator results cannot certify the physical phone,
every Samsung firmware, TalkBack behavior, or every possible book file.

APK and Windows artifacts are local release files, excluded from Git. See
[artifact verification](windows_0.5.4_checksums.md) for performed checks and
limits. No GitHub release is published by these build scripts.

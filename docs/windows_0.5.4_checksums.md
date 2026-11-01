# Windows 0.5.4 checksums

Local validation: 2026-10-28. These are built artifacts; no GitHub publication was performed.

Base Git commit: `0480074649b2a8c638ca9175dcfea9708bed0a10` with uncommitted changes.
Source fingerprint: `5125097251934F313661593DE098F20CF3D8886BE58F67A78E1A84F614ADF0B0` (257 build-relevant files).

## Android companion

- `dist/release/ManageYourLibrary-0.5.4.apk`
- Bytes: 62,109
- SHA256: `19FA6F2DFEF7C687A22A45FA57675CE2BCB3BE7B6DD4C7F10FC735F921487721`

## Windows installer

- `dist/release/ManageYourLibrary-0.5.4-Setup-x64.exe`
- Bytes: 126,156,527
- SHA256: `7B9A269C1A3415BEB15D15690D94C91FAC527643399B1EEEA7F8E361249A5292`

## Windows launcher

- `dist/windows/ManageYourLibrary/ManageYourLibrary.exe`
- Bytes: 7,082,979
- SHA256: `F0C4AD23AAD97B102EB5623D3AF96DF30D6CF0E08CA2A836635F24A31AE3B805`

## Windows portable

- `dist/release/ManageYourLibrary-0.5.4-Windows-x64-portable.zip`
- Bytes: 155,603,867
- SHA256: `573E7154AA13A120624073B35EA191DD1CC300DEA2769AA3613BE911833EDF23`

## Performed checks

- 429 automated Python tests passed in 22.126 seconds in the locked Python 3.12.10 build environment. Source/frozen smoke checks and the catalog performance gate passed.
- Frozen runtime: Tk initialization, all bundled Indra model hashes, synthetic image OCR and scanned-PDF OCR passed. First-use checks passed with empty library/configuration and no automatic network/OCR work.
- Five frozen mobile checks passed: bundled release APK and lazy imports, private HTTP pairing, catalog/confirmed metadata, verified upload + preview + apply + undo, and token revocation.
- Independently extracted the installer with innounp 2.67.11: all 1,202 files (289,643,086 bytes) matched the built application by SHA-256. The embedded model license was present; no legacy Tesseract, JBIG or FFmpeg files were found.
- Executed the extracted launcher with Windows-only PATH and an isolated temporary profile. Smoke, OCR/runtime, first-use and mobile self-tests passed. The extracted payload remained unchanged.
- Android release APK installed and cold-launched on an isolated Android 17 / API 37 x86_64 emulator with a 1080×2340 display. It opened the empty connection page. The APK contains no architecture-specific native libraries.
- Twelve native Android checks passed across four instrumentation runs using the separate QA package and a disposable TLS fixture: pairing UI, encrypted credentials/address rejection, search, favorite/metadata roundtrip, verified download/read-only provider + import/undo, recoverable quarantine/undo, selected-file upload preserving the original, light/dark pages, rotation/reconnect, 150% font layout, and granting/denying the actual Android 17 local-network permission.
- Production APK: minSdk 26, targetSdk 37; signatures v2/v3 and ZIP alignment verified. Debugging, backups and cleartext HTTP disabled; test CA, instrumentation and signing secrets absent. Project/model notices included in assets.
- Real Tailscale 1.102.3 test on the PC: temporary private HTTPS endpoint, one-use pairing and authenticated request passed. The complete pre-existing Serve configuration was unchanged afterward. The test endpoint was stopped.

Android update-certificate SHA-256: `fba973adeed2ccf19714b4edcd9be129f2435e851b6a87d89796ca8b72cc10e1`. Windows executable/installer are not Authenticode signed.

## Limits

- The physical Galaxy S26 Ultra, its exact Samsung firmware, TalkBack and a physical phone-to-PC Tailscale connection were not tested. The emulator is not a Samsung hardware certification. Android 8–16 compatibility is declared by the minimum SDK, not certified by device runs here.
- Windows installer installation, upgrade and uninstall were not executed. Extraction and isolated payload execution do not certify those workflows.
- macOS/Linux native artifacts were not built or validated in this task. No zero-defect or universal-format claim is made.
- The Android client needs a running PC and private access enabled. Opening a book requires a compatible Android reader; OCR remains on the PC.

Local evidence: `dist/android-qa/android-verification.json`, `windows-extracted-verification.json`, `tailscale-real-final.json`, build logs and screenshots. Combined export: `dist/release/verification-0.5.4.json`; hashes: `dist/release/SHA256SUMS-0.5.4.txt`.

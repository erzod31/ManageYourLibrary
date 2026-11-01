# Updating the application from its UI · DG-0020

This updates the installed binary, not the library index. The 0.5.5 candidate
adds Settings → **Buscar / instalar actualización** on desktop and Connection →
**Actualizar esta aplicación** on Android. It is a local candidate, not a newly
published release. Existing 0.5.3 public desktop packages and the locally
delivered Android/Windows 0.5.4 binaries do not gain this UI retroactively.
Install the updater-capable candidate manually once; later releases can use
the in-app flow when matching packages are actually published/provided.

## Desktop

1. Open Settings → Buscar / instalar actualización. It shows the running version
   and architecture. Press Buscar to query the configured channel.
2. The default channel is the real GitHub Releases API of
   `erzod31/ManageYourLibrary`. A different `owner/repository` can be saved only
   with an explicit trust confirmation. Configuration is in the existing config
   file's `updates.repository`; other configuration fields are preserved.
3. Stable, uploaded assets are selected by exact product/platform/version names.
   Drafts, prereleases, unsupported platforms and unauthorized downgrades are
   rejected. A newer release without a valid size/SHA-256 fails verification.
4. Download is bounded, cancellable and staged separately from the app/library.
   The HTTPS origin, size, SHA-256, version and product identity are checked.
   They are checked again before installation. No book/OCR data is sent to GitHub.
5. Confirm **Instalar y reabrir** after all book operations finish. Installed
   Windows uses the existing Inno Setup identity and native UI. Its normal
   completion offers to reopen the app; cancelling leaves the existing app
   available. Portable Windows/Linux/macOS use a helper after the current
   process exits, keep the old application directory as a rollback, and request
   reopening. A launcher/helper failure retains a durable plan and the original
   or rollback files. No updater executes at application startup.

Windows keeps AppId `{A4A5DE08-8644-4D67-B03E-271515180F7D}`. Unsigned legacy
Windows distribution is identified as **NotSigned**, with an explicit notice
in the app's confirmation; invalid/untrusted signatures are rejected. If the
installed app has a valid publisher certificate, its replacement must retain
that signer. No SmartScreen, UAC, execution-policy or signature checks are
disabled. Source-code runs may check versions but do not replace their source
tree. Windows portable helpers use system PowerShell without policy bypass.

macOS retains the published `org.manageyourlibrary.desktop` bundle identifier,
checks codesign, preserves an existing Developer ID team, and asks Gatekeeper
to assess the staged bundle. Rejected/unauthorized bundles are blocked. There
is no quarantine removal or re-signing of downloaded apps. A production Mac
release still needs a native build, valid signing/notarization as required by
Gatekeeper, and native verification. The manifest is kept outside the signed
bundle so packaging does not invalidate its resource seal.

Linux uses the existing x64 portable `.tar.gz` layout. Installation folders must
be writable by the user; a root/organization-managed location needs its own
authorized deployment process. No `sudo`, silent privileged service or custom
APT repository is added. Archive extraction rejects traversal, special files,
hard links and external symlinks. Internal macOS framework symlinks are kept.
Application/rollback directories must not overlap the configured library or
profile. Stored catalogs, quarantine, journal, pending plans and backups remain
outside the binary replacement and are preserved.

## Android

The existing private, paired PC is the channel. In Connection, search for the
signed companion bundled by the PC, download and verify it, and confirm install.
The PC must run 0.5.5 or later and remain reachable through the user's existing
Tailscale connection. No new public update server or Funnel endpoint is added.
The authenticated endpoints are `/api/v1/android-update` and
`/api/v1/android-update/file`; metadata contains no credentials or personal paths.

Android checks the APK size/hash, package name, internal version/versionCode,
minimum SDK, and equality with the currently installed signing certificates.
Changing or losing the signing key blocks updates. The release key remains
outside Git and must be preserved; QA keys/packages never replace it.

Android may ask to authorize installation from this app. Returning from that
screen does not install anything automatically: press Install again and confirm
the system's package installer. Only a read-only URI to the verified APK is
granted. User cancellation/rejection preserves the current version and data.
After completion use the system's Open action or reopen the app; Android can
terminate the old process during replacement. No silent/background install or
forced activity launch is promised.

## Packaging and verification

Use existing entry points: Android `BUILD_ANDROID.ps1`, Windows
`BUILD_WINDOWS.bat`/`BUILD_INSTALLER.bat`, and native `build_linux.sh` /
`build_macos.sh`. Matching APK/update metadata are build inputs. Native archive
names/layout and the Mac bundle identifier match the actual published 0.5.3
packages. Native builds must execute on their target OS; source tests do not
certify a compiled app. The native packager writes candidates and SHA-256 files
without publishing or overwriting earlier artifacts.

The Android builder normalizes raw ZIP entry separators before alignment and
signing. This fixes Windows-style asset names that Android otherwise cannot
open. The frozen mobile gate checks raw ZIP names, and Android instrumentation
reads actual package assets and verifies the update flow.

DG-0020 validation uses fake native install launchers, extracted payloads and
isolated profiles. No real Windows installer/updater/uninstaller is executed,
and no user's device/installation is updated. Current platform-specific results,
actual release/channel inventory, package hashes, blockers and remaining work
are recorded in [the DG-0020 report](in-app-updates-DG-0020.json).

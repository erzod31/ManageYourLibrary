# Native macOS updater validation and distribution

The native workflow uses real GitHub-hosted `macos-15` (Apple Silicon) and
`macos-15-intel` runners and CPython 3.12.16 from Python Build Standalone's
20261026 release, with an explicit per-architecture SHA-256. GitHub's standard
Python manifest does not offer macOS/Windows binaries after 3.12.10; the
Windows APK verifier uses 3.12.10 without changing the product runtime.
The Mac Python/venv is created only under the independent runner's temporary
directory, without changing host services or signing credentials. It retains the published bundle ID
`org.manageyourlibrary.desktop`, builds architecture-specific Mach-O executables,
resolves exact native binary wheels and installs their recorded hashes offline.
It runs source/frozen tests, local synthetic OCR, clean first use, the mobile
API and updater fake-launcher tests. It then checks every Mach-O architecture,
bundle/update identity, codesign, Gatekeeper and stapled-ticket status. After
ZIP packaging, it checks file bytes, executable permissions and symlinks and
reruns the frozen diagnostics from an independent extraction.

If PyPI has no macOS Intel wheel for the pinned ONNX Runtime 1.31.1, the Intel
runner attempts a CPU build of that exact version from the upstream release
commit `6af1a932e2286d5c58166085d24c68783033edee`. It records submodule revisions,
hash-locks bootstrap wheels and feeds the resulting native wheel into the normal
hash-locked dependency resolver. It does not silently downgrade the OCR runtime
or substitute an Apple Silicon/Linux binary. Failure remains a native build
failure, with diagnostics retained outside the app.

The default workflow produces **QA artifacts only**. The disposable Android
input key is isolated to the runner and never replaces the maintainer's signing
key. `distributionEligible: false` is expected for ad-hoc Mac signatures or a
CI-signed APK. Passing native compilation is not Gatekeeper approval or an
installed application update. The workflow has read permissions and no release
publishing job, device connection or Tailscale/firewall changes.

Run `.github/workflows/native-release.yml` manually, or push audited source to
`codex/dg-0035-native-*`. Optional `android_bundle_run_id` and
`android_artifact_name` inputs consume an existing Actions artifact. It must
contain the matching `ManageYourLibrary-<VERSION>.apk` and `.update.json`.
The Windows SDK verifies actual APK signature/package/version/SDK and compares
the certificate with `platforms/android/release-certificate.sha256`. An explicitly
supplied input with the wrong certificate is rejected, not downgraded to QA.
No private signing key is uploaded by this workflow.

For a distribution build on an authorized, independent Mac, supply the preserved
release-signed APK and verification record, a valid existing Developer ID
Application identity (`MANAGE_YOUR_LIBRARY_CODESIGN_IDENTITY`), its matching
`MYL_MACOS_TEAM_ID`, and a valid stapled notarization ticket. With
`MYL_MACOS_REQUIRE_DISTRIBUTION=1`, the canonical build refuses packaging unless
all distribution gates pass. Signing/notarization credentials must already be
authorized and configured; the project does not create an Apple account,
purchase a certificate, upload secrets, remove quarantine or weaken Gatekeeper.
The QA workflow intentionally cannot perform this production transition.

The native build command is `bash platforms/macos/build_macos.sh` in a fresh
checkout with the matching APK under `dist/android`. Existing output is
preserved and must not be overwritten. Validation evidence and dependency locks
stay outside the signed app in `dist/macos/validation`; archives and round-trip
evidence are in `dist/native-release`.

`python tools/prepare_update_publication.py --output <new-review-directory>`
validates the existing Windows/Android/Linux candidate hashes and immutable
runtime input baseline, checks offline channel selection and writes a publication
review. It never uploads or publishes. Existing binaries can be reused when only
native build/audit tooling changed; their original source provenance remains
unchanged. A real source/runtime change requires a reviewed rebuild.

Production publication is a separate final operational step: use a reviewed
source commit, create a new draft, upload and compare all digests, then publish
only after review. Drafts do not appear in the app's update offers. Returning a
release to draft stops new offers without silently downgrading installed apps
or rolling back books/catalogs. The Mac supplement must include matching native
approval evidence; QA bundles are never promoted merely because they compiled.

Users of older binaries without an updater need one manual transition. Actual
S26 Ultra/Tailscale, native installed upgrades and external-reader accessibility
must be distinguished from CI/mocked evidence. The LG and all physical user
devices are outside this validation workflow.

Primary platform references:
[GitHub runner labels](https://docs.github.com/en/actions/reference/runners/github-hosted-runners),
[PyInstaller native architecture/signing](https://pyinstaller.org/en/stable/feature-notes.html#macos-multi-arch-support),
[Apple notarization](https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution).

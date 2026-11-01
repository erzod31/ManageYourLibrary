# Windows 0.5.2 checksums — local artifact record

Rebuilt locally on 2026-10-06 with the clean first-use workflow and gates. Source
commits were pushed to draft [PR #3](https://github.com/erzod31/ManageYourLibrary_GitHub/pull/3).
No merge, version tag or GitHub Release was performed. This record supersedes
the earlier local 0.5.2 packages; earlier evidence remains in Git history.

## Source provenance and dependencies

- Build source commit: `9c082ae5c06147ef3b95a4737f0f21168223aae4`.
- Branch: `feature-ocr-cover-pipeline`; working tree was clean when built.
- Fingerprint of 225 source/config/runtime inputs:
  `E75253B37A34A8307BEC7B86DF93DA39E2DFEA0B9D294F0818C08723EC5C69AC`.
- Derived checksum reports are excluded from that fingerprint; this evidence
  can be completed after building without changing the packaged source inputs.
- Python 3.12.10, Windows 11 x64 build 26300.
- Hash-locked requirements were already satisfied: PyInstaller 6.21.0,
  hooks 2026.6, pypdf 6.13.2, pypdfium2 5.9.0, Pillow 12.2.0, ftfy 6.3.1.
- Installer compiler: Inno Setup 6.7.3.

## Checks actually performed

- 390 automated tests passed inside `platforms/windows/BUILD_WINDOWS.bat`
  using temporary APPDATA, LOCALAPPDATA and TEMP directories, not personal data.
- Source smoke, 1k/10k/50k catalog performance gate and frozen smoke passed.
  The 50k synthetic search p95 was 9.300 ms; preparation took 1,834.681 ms.
- GitHub CI passed for the build source commit: [Windows test/build/runtime
  validation](https://github.com/erzod31/ManageYourLibrary_GitHub/actions/runs/37419921142)
  and [Linux/macOS source validation](https://github.com/erzod31/ManageYourLibrary_GitHub/actions/runs/37419921077).
  Windows ran 390 tests successfully twice (test step and official build entry
  point). Linux and macOS each reported 390 tests, OK with one pre-existing
  Windows-only test skipped. These are source checks, not native Unix releases.
- The equal-size mutation-during-hash regression passed 100 consecutive local
  runs. Its fixture explicitly advances mtime to avoid relying on immediate
  timestamp updates after rapid writes on Windows. The production signature
  rejection and test assertion remain unchanged. This does not add locking or
  guarantee detection of content changes that preserve every sampled stat field.
- Frozen runtime self-test passed: Tk initialization, bundled OCR executable
  and `eng`, `spa`, `fra`, `nld`, `chi_sim` files, image OCR and PDFium OCR.
  OCR recognized a synthetic image and a generated scanned PDF locally.
- Source and frozen first-use tests passed using the real Tk App with a
  disposable empty state directory, before importing profile-dependent code.
  All five checks passed: clean defaults, empty workspace, empty catalog/history
  and state, no automatic book operation or pending plan, and no automatic
  network request during startup. The library field is blank and the translated
  choose-folder action is present. Existing-user state was not loaded or reset.
  This automated check is not an installed-UI visual or upgrade approval.
- Native source Tk benchmark with 4,158 synthetic records: no callback errors,
  30 cover cards, 4,158 table rows, warmed heartbeat maximum 69.90 ms,
  startup heartbeat maximum 333.48 ms. Callback timings exclude deferred paint;
  these numbers do not certify visual appearance or universal 60 fps.
- Inno Setup compiled the installer successfully. It was not installed.
- Packaging rejected stale source fingerprints, missing runtime/first-use gates,
  books, models and personal state/cache payloads without deleting those files.
  ZIP CRC verification passed for 1,235 entries.
- The ZIP was extracted into a temporary directory; the extracted EXE passed
  smoke, the four runtime checks and the five fresh-profile first-use checks
  with an isolated profile and Windows-only PATH (no Python). Its hash matched
  the original frozen EXE. Reports are saved outside Git in
  `dist/release/portable-runtime-0.5.2.json` and
  `dist/release/portable-first-use-0.5.2.json`.
- `git diff --check` and staged whitespace checks passed; basic secret-pattern
  scans of 163 tracked source/document files and private-state filename scans
  found no candidates. This is not a full
  security certification.
- Windows profile paths in current documentation use `%USERPROFILE%`; privacy
  test fixtures use a generic profile. Saved build and installer logs replace
  the local profile root with `%USERPROFILE%`. Tracked text, release metadata,
  logs and extracted executable code were scanned without finding the personal
  Windows username. Historical Git commits were not rewritten; older versions
  still contain the former paths. Author/publisher attribution was retained.
- Removed 1,253 generated compiler, extracted-portable and synthetic-profile
  files (239,543,502 bytes) from this first-use validation workspace. No
  personal library, catalog, configuration, quarantine, history or backup was
  removed. Final artifacts, build evidence and the previous 0.5.1 packages were
  retained; generated outputs remain outside Git.

## Application folder

- Path: `dist/windows/ManageYourLibrary/ManageYourLibrary.exe`
- EXE size: `4,995,705 bytes`
- Full folder: `1,235 files`, `222,369,747 bytes`
- Product/File version: `0.5.2`
- SHA256: `8A1141B3BD92BA86822AF6F948A28A1DBC9A595BBB2DEC9B4125AF929F2DD906`
- Authenticode: `NotSigned`

This is an onedir application: the EXE must stay beside `_internal` and the
other payload files. Never distribute the launcher alone.

## Portable ZIP

- Path: `dist/release/ManageYourLibrary-0.5.2-Windows-x64-portable.zip`
- Size: `98,031,159 bytes`
- Entries: `1,235`
- SHA256: `953043D806A8F47945E312EC8302357AC7D8E4F6ACAE73E78E90C2E52195FAA2`

## Installer

- Build path: `dist/installer/ManageYourLibrary-0.5.2-Setup-x64.exe`
- Publication copy: `dist/release/ManageYourLibrary-0.5.2-Setup-x64.exe`
- Size: `68,024,006 bytes`
- Product version: `0.5.2`
- SHA256: `3A2E8E10B8E8FB3641E924FCD0748834B21A024F3010C40416E6679AFBAFABA2`
- Authenticode: `NotSigned`

## Publication assets and remaining approval

Attach the installer, portable ZIP, `dist/release/SHA256SUMS-0.5.2.txt` and
`dist/release/build-manifest-0.5.2.json` as Release assets, not source commits.
The provenance JSON SHA256 is
`54B9FDA9118BEFD796AC914A94F29611C3AF32921D20E2D085B83312D1B9A3CF`.

Before public distribution:

- [ ] Visual installed-UI and upgrade/uninstall click-through with disposable
  fixtures, including preservation of catalog, settings, quarantine and history.
- [x] GitHub Windows CI and Linux/macOS source CI passed for the build revision
  linked above. Evidence-only follow-up commits must also retain green CI.
- [ ] Decide whether to distribute unsigned or sign and regenerate checksums.
- [x] Push corrected source commits and keep PR #3 in draft.
- [ ] Merge, version tag and GitHub Release require separate publication
  authorization; none was performed.

The Windows computer-use helper could not initialize because its sandbox failed
with `helper_unknown_error: apply deny-read ACLs`, even after one kernel reset.
No visual click-through or installed-upgrade validation is claimed. Automated Tk
initialization and source benchmarks are separate from that manual approval.

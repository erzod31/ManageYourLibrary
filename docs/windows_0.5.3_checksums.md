# Windows 0.5.3 checksums

Rebuilt on 2026-10-06 from the initial clean public source. Historical hashes,
test counts and manual installer approvals were not inherited.

## Source and dependencies

- Build source: `c7f09003f92090c65034cfa6a89ad46a491344b0` on `main`, clean tree.
- Fingerprint of 200 build inputs:
  `0D93A4A366495CC45CEC37CF991C21706E38DD6E7BF6E7AE572EB5036061CB48`.
- Derived checksum reports are excluded from this fingerprint. Completing this
  evidence after building does not alter the packaged inputs.
- Python 3.12.10, PyInstaller 6.21.0, pypdf 6.13.2, pypdfium2 5.9.0,
  Pillow 12.2.0, ftfy 6.3.1, Windows x64 and Inno Setup 6.
- Installed build versions satisfied the hash-locked requirements. The local
  build reused the already installed versions; it did not reinstall dependencies.

## Checks actually performed

- 392 current tests passed locally and again inside the official Windows build
  with isolated APPDATA, LOCALAPPDATA, TEMP and TMP, not personal profiles.
- Source smoke, catalog gate and frozen smoke passed. The 50k synthetic catalog
  search p95 was 7.882 ms; preparation took 1,788.880 ms on this build host.
- [Windows test/build CI](https://github.com/erzod31/ManageYourLibrary/actions/runs/37425076982)
  and [Linux/macOS source CI](https://github.com/erzod31/ManageYourLibrary/actions/runs/37425076775)
  succeeded for the exact build revision. Unix source CI is not a native release.
- Frozen runtime checks passed for Tk initialization, bundled language files,
  synthetic image OCR and scanned-PDF OCR through PDFium.
- The real Tk workspace passed all five isolated fresh-profile checks: clean
  defaults, empty workspace, empty state, no automatic book operation and no
  automatic network request during startup.
- Packaging checked the current source fingerprint, actual runtime/first-use
  reports and forbidden personal-state payloads. ZIP CRC verification passed.
- The full portable ZIP was extracted. Its launcher hash matched the original.
  Smoke, all four runtime checks and all five first-use checks passed with only
  Windows directories on PATH, without Python.
- A targeted privacy/secret-pattern audit inspected 239 tracked source/runtime
  files, 1,235 payload files, six compiled scripts and 498 compiled modules and
  their code filenames/constants. No targeted developer identity/profile path,
  old repository reference, secret candidate or personal state was found.
  This is a bounded audit, not a guarantee that every possible secret was detected.
- Commit attribution uses the product name and a non-personal placeholder email.
  Previous Git history, private conversations and development reports were not
  copied. Third-party attribution and the necessary public GitHub owner identity
  were retained. Local build logs were anonymized and are not Release assets.
- Inno Setup compiled the installer. Installation was not performed.
- Manual installed-UI, upgrade and uninstall validation: **not performed**.
- Authenticode for launcher and installer: **NotSigned**.

## Application folder

- Path: `dist/windows/ManageYourLibrary/ManageYourLibrary.exe`
- Size: `4,995,692 bytes`
- SHA256: `D1B96C77914367D42EF9774E1F5697BC1C65251661DB9D97E369AB91FDCC6674`
- The launcher requires its complete folder, including `_internal`.

## Release assets

| Asset | Bytes | SHA-256 |
| --- | ---: | --- |
| ManageYourLibrary-0.5.3-Windows-x64-portable.zip | 98,030,545 | `91B316DA15F1B8D55D49DD2856CD0F7922A72DFF157F6E363EE2F1D79F43F131` |
| ManageYourLibrary-0.5.3-Setup-x64.exe | 68,018,025 | `E43DE948B8ED1DC1795D7EECE40519CB1B48BB2A514E012A41CE6EDDBBA310E6` |
| build-manifest-0.5.3.json | 1,053 | `0886898AABA65B0941EA0B3E06DB235F5E5AD670D22C673923A6614FBE9422AA` |

Attach these three files and `SHA256SUMS-0.5.3.txt` to the Release, not source
history. User books, catalog, settings, quarantine, journals, pending plans,
history and backups are excluded and must remain intact. Existing profiles are
preserved; a clean distribution is not a reset of an existing user's account.

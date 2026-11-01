# Windows 0.5.0 checksums — local artifact record

Build performed on 2026-09-29 from the working tree identified by
`dist/windows/ManageYourLibrary/build-manifest.json`.

## Validation actually performed

- Python 3.12.10 on Windows 11 AMD64;
- 334 automated tests passed inside the build entry point;
- source smoke test passed;
- 1k/10k/50k catalog performance gate passed;
- frozen `ManageYourLibrary.exe --smoke-test` passed;
- Tesseract plus `eng`, `spa`, `fra`, `nld`, and `chi_sim` data verified in the
  frozen folder;
- PDFium DLL verified in the frozen folder;
- source-tree fingerprint (152 build inputs):
  `6090D19F6738F042E346B3316EFC5A30A56504782D5A73DAA552EAA0C4E4C92D`.

The tree contained local tracked and untracked changes; the manifest records
them. Installed-UI/manual accessibility validation was not run for this build.

## Diagnosable application

- Path: `dist/windows/ManageYourLibrary/ManageYourLibrary.exe`
- EXE size: `4,845,417 bytes`
- Complete folder: `1,233 files`, `222,221,661 bytes`
- SHA256: `1543A4C55EEFF79135516156940EB50497B9F488F883F41B0874106AFF38CB43`
- Product/File version: `0.5.0`
- Authenticode: not signed

The EXE is an `onedir` launcher and must remain beside its `_internal` folder.

## Portable archive

- Path: `dist/release/ManageYourLibrary-0.5.0-Windows-x64-portable.zip`
- Size: `100,818,532 bytes`
- Entries: `1,237`
- SHA256: `83D0090F498FED232A620119BD72B2342ED010796BE4C78B2F6D63BBBC830543`

## Installer

No new installer was produced because Inno Setup 6 is not installed on this
machine. A build is not an installed-application validation, and the older
2026-09-28 installer checksum must not be attributed to this source snapshot.

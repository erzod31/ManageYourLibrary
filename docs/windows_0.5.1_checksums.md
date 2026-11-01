# Windows 0.5.1 checksums — local artifact record

Build performed on 2026-09-29 from the working tree identified by
`dist/windows/ManageYourLibrary/build-manifest.json`.

## Validation actually performed

- Python 3.12.10 on Windows 11 AMD64;
- locked, hash-verified dependencies were already satisfied;
- 338 automated tests passed inside the Windows build entry point;
- source smoke test passed;
- 1k/10k/50k catalog performance gate passed;
- frozen `ManageYourLibrary.exe --smoke-test` passed;
- the portable ZIP was extracted into an isolated temporary folder and its
  frozen smoke test passed with version `0.5.1`;
- Tesseract plus `eng`, `spa`, `fra`, `nld`, and `chi_sim` data were bundled;
- PDFium DLL was bundled;
- source-tree fingerprint (154 build inputs):
  `E2E6B2E9EF3811C83CCD97D7F998B6E1A3B0F22A82DC8C6574607438838F85A4`.

The tree contained local tracked and untracked changes; the manifest records
them. The installer compiled successfully with Inno Setup 6.7.3, but installed-
UI validation and code signing were not performed.

## Diagnosable application

- Path: `dist/windows/ManageYourLibrary/ManageYourLibrary.exe`
- EXE size: `4,850,802 bytes`
- Complete folder: `1,233 files`, `222,227,244 bytes`
- SHA256: `B9FB0DEB117851588AA11E586006C69858FAFF8D376F1F24B75430F767E4CA15`
- Product/File version: `0.5.1`
- Authenticode: not signed

The EXE is an `onedir` launcher and must remain beside its `_internal` folder.

## Portable archive

- Path: `dist/release/ManageYourLibrary-0.5.1-Windows-x64-portable.zip`
- Size: `100,868,786 bytes`
- Entries: `1,237`
- SHA256: `AF53F3AB36ED90AE6CCC3C2C8A716EEB423ADB8548813C840245181135C2CD5A`

## Installer

- Path: `dist/installer/ManageYourLibrary-0.5.1-Setup-x64.exe`
- Size: `67,883,033 bytes`
- Product version: `0.5.1`
- SHA256: `26ECF2904F2B1C752C5417C35A5D32D1BB5377A4504FB191A98ECF6DCDDD9B2C`
- Authenticode: not signed

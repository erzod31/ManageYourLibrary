# Windows 0.3.0 checksums

Built and validated locally on Windows 11 with CPython 3.12.10,
PyInstaller 6.21.0, and Inno Setup 6.7.3.

- Artifact: `dist/windows/ManageYourLibrary/ManageYourLibrary.exe`
- Size: `4,687,328` bytes
- SHA256: `FEAABFED01C17E143B7CF76D2F54BD6C53AEC6EB8CFC03AAED5FE3E9CBD478BF`
- Authenticode: `NotSigned` (no code-signing certificate was available)
- Frozen smoke test: passed
- Packaged GUI startup/clean shutdown with isolated app data: passed
- Product/File version: `0.3.0`

- Installer: `dist/installer/ManageYourLibrary-0.3.0-Setup-x64.exe`
- Size: `67,111,718` bytes
- SHA256: `C8586181FCD25CD3F0D24CA649EE54946EB40594C1EE5F1C22332B79D66124FD`
- Authenticode: `NotSigned` (no code-signing certificate was available)
- Silent install, installed smoke test, and uninstall: passed
- Source branch: `feature-ocr-cover-pipeline`

An artifact is not considered validated solely because PyInstaller or Inno
Setup produced it. The automated tests, frozen smoke test, signature status,
and manual GUI checks must be recorded separately. The command-line and
installer validations above do not claim an Authenticode signature.

# Post-release verification for Windows v0.2.0

## Official published asset

- Verification date: `2026-06-01`
- Version: `v0.2.0`
- Published asset name: `ManageYourLibrary.exe`
- Verified downloaded asset: `%USERPROFILE%\Downloads\ManageYourLibrary.exe`
- Size: `107380918` bytes
- Official SHA256: `8E5B86393ED5A16DF533E3CCD020A1734ED28E854F9FA1FA902D59D94864FC78`

The checksum above is the official Windows `v0.2.0` checksum because it was calculated from the asset downloaded from the published GitHub Release.

An intermediate local comparison referenced SHA256 `209C06CD3927384E75BD58041B2AF899B38D2FE9FBAAF813ECFBB5254033DD5F` before the published asset was downloaded. That intermediate value is not the checksum of the currently published download and is not an official release checksum.

## Scope of this correction

- Documentation only.
- No EXE rebuild.
- No GitHub Release asset replacement.
- No version change.
- No tag movement or recreation.
- No personal library access.
- No functional code change.

## Repository hygiene

- The EXE remains outside Git.
- `dist/` and `build/` remain outside Git.
- Temporary validation files remain outside Git.

## Decision

The official Windows `v0.2.0` checksum is:

```text
8E5B86393ED5A16DF533E3CCD020A1734ED28E854F9FA1FA902D59D94864FC78
```

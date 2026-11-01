# Post-release verification for Windows v0.1.0

## Official published asset

- Verification date: `2026-05-31`
- Version: `v0.1.0`
- Published asset name: `ManageYourLibrary.exe`
- Verified downloaded asset: `%USERPROFILE%\Downloads\ManageYourLibrary.exe`
- Size: `107327057` bytes
- Official SHA256: `D6808B050EEF9C8F036FE4005FF5F3387E44B5099110CC7C101BE0B6F4A2906E`

The checksum above is the official Windows `v0.1.0` checksum because it was calculated from the asset downloaded from the published GitHub Release.

An intermediate local comparison referenced a different checksum during post-release documentation work. That intermediate value is not the checksum of the currently published download and is not an official release checksum.

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
- Temporary manual validation files remain outside Git.

## Decision

The official Windows `v0.1.0` checksum is:

```text
D6808B050EEF9C8F036FE4005FF5F3387E44B5099110CC7C101BE0B6F4A2906E
```

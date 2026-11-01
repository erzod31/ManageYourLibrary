# Windows 0.2.0 checksums

## Published GitHub Release asset

- Artifact: `ManageYourLibrary.exe`
- Verified downloaded asset: `%USERPROFILE%\Downloads\ManageYourLibrary.exe`
- Size: `107380918` bytes
- SHA256: `8E5B86393ED5A16DF533E3CCD020A1734ED28E854F9FA1FA902D59D94864FC78`
- Verified: `2026-06-01`

This is the official checksum because it was calculated from the asset downloaded from the published GitHub Release.

## Local build provenance

- Local build path: `dist/windows/ManageYourLibrary.exe`
- Built: `2026-06-01T17:34:48+02:00`
- Functional source commit: `e8ca259`
- Build command: `BUILD_EXE.bat`

The generated EXE is intentionally ignored by Git. Do not commit `dist/`, `build/`, or the EXE to the source repository. Attach the EXE separately to the GitHub Release for tag `v0.2.0`.

The application source in this artifact is the validated functional merge at `e8ca259`. The release metadata promotion changes documentation, tests, and `VERSION` only; it does not change application logic.

An intermediate local comparison referenced SHA256 `209C06CD3927384E75BD58041B2AF899B38D2FE9FBAAF813ECFBB5254033DD5F` before the GitHub Release asset was downloaded. That intermediate value is not the official published-asset checksum.

## Frozen archive verification

Archive inspection confirmed:

- `pypdfium2_raw\pdfium.dll`;
- `tesseract\tesseract.exe`;
- `tesseract\tessdata\eng.traineddata`;
- `tesseract\tessdata\spa.traineddata`;
- `tesseract\tessdata\fra.traineddata`;
- `tesseract\tessdata\chi_sim.traineddata`;
- no `rapidfuzz` payload.

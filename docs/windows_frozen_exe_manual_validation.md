# Windows 0.5.3 frozen validation status

Frozen smoke, Tk initialization, bundled-language image OCR, PDFium OCR and
fresh-profile first-use checks are automated. Results for the current build are
recorded in `windows_0.5.3_checksums.md` after building.

Manual installed-UI, upgrade and uninstall validation: **not performed**.
No checklist or approval from earlier builds is carried into this snapshot.
Use isolated APPDATA and LOCALAPPDATA with disposable fixtures.

The launcher is `dist/windows/ManageYourLibrary/ManageYourLibrary.exe`.
The manual test plan covers Tesseract, PDFium, `.trash_manageyourlibrary/`, Undo,
imports and preservation of settings/catalog. Mark the current-build checklist
only after actually exercising the GUI.

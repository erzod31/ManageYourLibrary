# Windows manual test plan

This plan validates the frozen Windows EXE without touching a personal ebook library.

## Safety boundary

Use a disposable folder inside the repository root:

```text
temp_release_validation\
  appdata\
  localappdata\
  input\
  library\
  ocr\
```

Do not select an existing personal library during this test.

Create the folders from PowerShell:

```powershell
$root = Join-Path $PWD "temp_release_validation"
New-Item -ItemType Directory -Force `
  (Join-Path $root "appdata"), `
  (Join-Path $root "localappdata"), `
  (Join-Path $root "input"), `
  (Join-Path $root "library"), `
  (Join-Path $root "ocr") | Out-Null
```

## 1. Start with isolated application data

From the same PowerShell window:

```powershell
$env:APPDATA = Join-Path $PWD "temp_release_validation\appdata"
$env:LOCALAPPDATA = Join-Path $PWD "temp_release_validation\localappdata"
Start-Process ".\dist\windows\ManageYourLibrary\ManageYourLibrary.exe"
```

Confirm:

- [ ] The main window opens.
- [ ] No Python installation prompt appears.
- [ ] No Tesseract or PDFium error appears.
- [ ] No personal library is preselected.
- [ ] Add books, Search metadata, Open library, Undo, and Check duplicates are visible.
- [ ] The initial status/log area is visible.

## 2. Select only the temporary library

In the app:

1. Choose the library folder.
2. Select `temp_release_validation\library`.
3. Confirm that the displayed active-library path is the temporary folder.

Do not continue if a personal-library path appears.

## 3. Add books conservatively

Create a tiny synthetic file:

```powershell
Set-Content -Encoding UTF8 `
  ".\temp_release_validation\input\Libro sintético ñ 三体.txt" `
  "Synthetic fixture without reliable bibliographic metadata."
```

In the app:

1. Click Add books.
2. Select the synthetic file.
3. Confirm that uncertain metadata does not cause an invented confident rename.
4. Confirm that the file is moved only inside the temporary library, normally to `PARA REVISAR NUEVAMENTE`.

## 4. Check exact-duplicate quarantine

Duplicate a temporary test file:

```powershell
Copy-Item `
  ".\temp_release_validation\library\PARA REVISAR NUEVAMENTE\Libro sintético ñ 三体.txt" `
  ".\temp_release_validation\input\Libro sintético duplicado.txt"
```

Add the copied file through the app.

Confirm:

- [ ] The app detects an exact duplicate.
- [ ] The discarded copy is moved to `.trash_manageyourlibrary/`.
- [ ] The discarded file still exists in quarantine.
- [ ] A quarantine manifest exists.
- [ ] No file is deleted directly.

## 5. Validate Search metadata separation

Place another synthetic file in `temp_release_validation\input`.

In the app:

1. Click Search metadata.
2. Select the temporary input file or temporary input folder.
3. Confirm that any rename occurs in place.
4. Confirm that Search metadata does not move the file to the selected library.
5. Confirm that a name collision receives a safe suffix instead of overwriting a file.

## 6. Validate Undo

Use Undo after a temporary rename or quarantine operation.

Confirm:

- [ ] The previous path is restored when possible.
- [ ] Existing files are not overwritten.
- [ ] A clear message appears if restoration is impossible.

## 7. Restart with the same isolated profile

Close the EXE and run it again from the same PowerShell window.

Confirm:

- [ ] No `ManageYourLibrary.exe` process remains before reopening.
- [ ] The temporary library remains configured.
- [ ] Index and status information load without an error.
- [ ] No personal application-data folder was used.

## 8. Validate frozen OCR and PDFium

Create a synthetic scanned PDF. This fixture contains no personal data:

```powershell
python -c "from pathlib import Path; from PIL import Image, ImageDraw; root=Path(r'.\temp_release_validation\ocr'); root.mkdir(parents=True, exist_ok=True); image=Image.new('RGB',(1600,420),'white'); ImageDraw.Draw(image).text((90,130),'MANAGE YOUR LIBRARY OCR TEST 2026',fill='black'); image.save(root/'scanned-fixture.pdf','PDF',resolution=150.0)"
```

If `python` is not in `PATH`, run the same command with the Python interpreter used to build the EXE.

In the frozen app:

1. Use Add books or Search metadata and select `temp_release_validation\ocr\scanned-fixture.pdf`.
2. Wait for local analysis to finish.
3. Confirm that no Tesseract-language or PDFium error appears.
4. Confirm that the activity log remains understandable if the synthetic fixture has insufficient bibliographic metadata.
5. Confirm that the fixture never leaves the temporary folders except through the selected temporary-library workflow.

Expected result:

- [ ] PDFium renders the scanned PDF without a missing-runtime error.
- [ ] Tesseract runs locally without a missing-language error.
- [ ] No document is uploaded to an OCR service.
- [ ] Low-confidence OCR does not invent reliable bibliographic metadata.

## 9. Optional: validate comic cover OCR and archive handling

This optional check uses only disposable synthetic files. It is intended for
builds that include the comic-cover OCR improvements.

Create a tiny CBZ with a synthetic cover image:

```powershell
python -c "from pathlib import Path; import zipfile; from PIL import Image, ImageDraw; root=Path(r'.\temp_release_validation\input\comic'); root.mkdir(parents=True, exist_ok=True); cover=root/'cover.jpg'; image=Image.new('RGB',(900,1300),'white'); draw=ImageDraw.Draw(image); draw.text((90,180),'SAND LAND',fill='black'); draw.text((90,260),'AKIRA TORIYAMA',fill='black'); draw.text((90,340),'2003',fill='black'); image.save(cover, quality=90); cbz=root/'Sand Land (2003) synthetic.cbz'; z=zipfile.ZipFile(cbz,'w'); z.write(cover,'Sand Land (2003) synthetic/000.jpg'); z.close(); cover.unlink()"
```

If `python` is not in `PATH`, run the same command with the Python interpreter
used to build the EXE.

In the frozen app:

1. Use Search metadata and select
   `temp_release_validation\input\comic\Sand Land (2003) synthetic.cbz`.
2. Confirm that the file stays in the same folder if it is renamed.
3. Confirm that the log does not show raw binary archive text as metadata.
4. Confirm that weak comic OCR remains conservative if external metadata does
   not confirm the identity.

Optional RAR-backed check:

- If you have a disposable `.cbz` that is actually a RAR archive, test it only
  inside `temp_release_validation\input\comic`.
- Expected behavior is either cover extraction through the local system archive
  reader or a clear conservative message that no readable comic cover was found.
- The app must not upload the file, unpack it outside the temporary validation
  tree, or invent final metadata from binary bytes.

Expected result:

- [ ] CBZ cover OCR runs without a Tesseract error.
- [ ] Search metadata keeps the comic archive in place.
- [ ] No raw binary text is used as book metadata.
- [ ] RAR-backed `.cbz` files either extract through the local reader or fail
      conservatively with an understandable log.

## 10. Cleanup

Close the application first. Then remove only the explicit temporary folder:

```powershell
$target = (Resolve-Path ".\temp_release_validation").Path
$repo = (Resolve-Path ".").Path
if ($target.StartsWith($repo, [System.StringComparison]::OrdinalIgnoreCase)) {
    Remove-Item -LiteralPath $target -Recurse -Force
} else {
    throw "Refusing to remove a folder outside the repository."
}
```

Run:

```powershell
git status --short --branch
```

Confirm that no temporary file, EXE, `dist/`, build folder, cache, or quarantine folder is staged.

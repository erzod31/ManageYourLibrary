@echo off
title Build Windows - Manage Your Library
setlocal
cd /d "%~dp0..\.."

if defined MANAGE_YOUR_LIBRARY_PYTHON (
  set "PYTHON_EXE=%MANAGE_YOUR_LIBRARY_PYTHON%"
  goto python_ready
)
set "PYTHON_EXE=%LocalAppData%\Programs\Python\Python312\python.exe"
if exist "%PYTHON_EXE%" goto python_ready
set "PYTHON_EXE=python"
where python >nul 2>nul
if errorlevel 1 (
  echo ERROR: Python 3.12 was not found.
  exit /b 1
)

:python_ready

set /p "APP_VERSION="<VERSION
if not exist "dist\android\ManageYourLibrary-%APP_VERSION%.apk" (
  echo ERROR: Build the matching Android companion first with platforms\android\BUILD_ANDROID.ps1.
  exit /b 1
)

"%PYTHON_EXE%" -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) else 1)"
if errorlevel 1 (
  echo ERROR: The locked Windows build requires Python 3.12.
  exit /b 1
)

if not defined MANAGE_YOUR_LIBRARY_SKIP_INSTALL (
  echo Installing locked, hash-verified dependencies...
  "%PYTHON_EXE%" -m pip install --require-hashes -r requirements.lock
  if errorlevel 1 exit /b 1
)

echo Preparing pinned, hash-checked local Indra OCR models...
"%PYTHON_EXE%" tools\prepare_indra_models.py
if errorlevel 1 exit /b 1

echo Running automated tests...
"%PYTHON_EXE%" -m unittest discover -s tests -v
if errorlevel 1 (
  echo ERROR: Tests failed. No artifact was built.
  exit /b 1
)

echo Running source smoke test and catalog performance gate...
"%PYTHON_EXE%" main.py --smoke-test
if errorlevel 1 exit /b 1
"%PYTHON_EXE%" tools\benchmark_catalog.py --check
if errorlevel 1 exit /b 1

echo Building the diagnosable onedir application...
"%PYTHON_EXE%" -m PyInstaller --clean --noconfirm --distpath "%CD%\dist\windows" --workpath "%TEMP%\ManageYourLibrary_build" platforms\windows\ManageYourLibrary.spec
if errorlevel 1 exit /b 1

echo Running frozen smoke test...
"dist\windows\ManageYourLibrary\ManageYourLibrary.exe" --smoke-test
if errorlevel 1 (
  echo ERROR: The frozen smoke test failed.
  exit /b 1
)

echo Checking bundled Tk, PDFium and local OCR with synthetic fixtures...
"dist\windows\ManageYourLibrary\ManageYourLibrary.exe" --runtime-self-test "dist\windows\ManageYourLibrary\runtime-self-test.json"
if errorlevel 1 exit /b 1

echo Checking a clean first launch with an isolated empty profile...
"dist\windows\ManageYourLibrary\ManageYourLibrary.exe" --first-use-self-test "dist\windows\ManageYourLibrary\first-use-self-test.json"
if errorlevel 1 exit /b 1

echo Checking private Android API and recoverable operations in an isolated profile...
"dist\windows\ManageYourLibrary\ManageYourLibrary.exe" --mobile-self-test "dist\windows\ManageYourLibrary\mobile-self-test.json"
if errorlevel 1 exit /b 1

echo Checking the binary updater with a fake native launcher...
"dist\windows\ManageYourLibrary\ManageYourLibrary.exe" --update-self-test "dist\windows\ManageYourLibrary\update-self-test.json"
if errorlevel 1 exit /b 1

"%PYTHON_EXE%" tools\write_build_manifest.py "dist\windows\ManageYourLibrary\ManageYourLibrary.exe" --platform windows-x64 --validated-release-gates --validated-runtime --validated-first-use --validated-mobile --validated-updater
if errorlevel 1 exit /b 1

echo DONE: dist\windows\ManageYourLibrary\ManageYourLibrary.exe
exit /b 0

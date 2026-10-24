@echo off
title Build Windows - Manage Your Library
setlocal
cd /d "%~dp0..\.."

set "PYTHON_EXE=%LocalAppData%\Programs\Python\Python312\python.exe"
if defined MANAGE_YOUR_LIBRARY_PYTHON set "PYTHON_EXE=%MANAGE_YOUR_LIBRARY_PYTHON%"
if exist "%PYTHON_EXE%" goto python_ready
set "PYTHON_EXE=python"
where python >nul 2>nul
if errorlevel 1 (
  echo ERROR: Python 3.12 was not found.
  exit /b 1
)

:python_ready

if not defined MANAGE_YOUR_LIBRARY_DIST_DIR set "MANAGE_YOUR_LIBRARY_DIST_DIR=%CD%\dist\windows"
if exist "%MANAGE_YOUR_LIBRARY_DIST_DIR%\ManageYourLibrary" (
  echo ERROR: Output already exists. Choose a new MANAGE_YOUR_LIBRARY_DIST_DIR to preserve existing artifacts.
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

echo Running automated tests...
"%PYTHON_EXE%" -B tools\run_tests.py
if errorlevel 1 (
  echo ERROR: Tests failed. No artifact was built.
  exit /b 1
)

echo Running source smoke test and catalog performance gate...
"%PYTHON_EXE%" main.py --smoke-test
if errorlevel 1 exit /b 1
"%PYTHON_EXE%" tools\benchmark_catalog.py --check
if errorlevel 1 exit /b 1

if not exist "tesseract\tesseract.exe" goto missing_tesseract
for %%L in (eng spa fra nld chi_sim) do if not exist "tesseract\tessdata\%%L.traineddata" goto missing_tessdata

echo Building the diagnosable onedir application...
"%PYTHON_EXE%" -m PyInstaller --clean --noconfirm --distpath "%MANAGE_YOUR_LIBRARY_DIST_DIR%" --workpath "%TEMP%\ManageYourLibrary_build" platforms\windows\ManageYourLibrary.spec
if errorlevel 1 exit /b 1

echo Running frozen smoke test...
"%MANAGE_YOUR_LIBRARY_DIST_DIR%\ManageYourLibrary\ManageYourLibrary.exe" --smoke-test
if errorlevel 1 (
  echo ERROR: The frozen smoke test failed.
  exit /b 1
)

echo Checking bundled Tk, PDFium and local OCR with synthetic fixtures...
"%MANAGE_YOUR_LIBRARY_DIST_DIR%\ManageYourLibrary\ManageYourLibrary.exe" --runtime-self-test "%MANAGE_YOUR_LIBRARY_DIST_DIR%\ManageYourLibrary\runtime-self-test.json"
if errorlevel 1 exit /b 1

echo Checking a clean first launch with an isolated empty profile...
"%MANAGE_YOUR_LIBRARY_DIST_DIR%\ManageYourLibrary\ManageYourLibrary.exe" --first-use-self-test "%MANAGE_YOUR_LIBRARY_DIST_DIR%\ManageYourLibrary\first-use-self-test.json"
if errorlevel 1 exit /b 1

"%PYTHON_EXE%" tools\write_build_manifest.py "%MANAGE_YOUR_LIBRARY_DIST_DIR%\ManageYourLibrary\ManageYourLibrary.exe" --platform windows-x64 --validated-release-gates --validated-runtime --validated-first-use
if errorlevel 1 exit /b 1

echo DONE: %MANAGE_YOUR_LIBRARY_DIST_DIR%\ManageYourLibrary\ManageYourLibrary.exe
exit /b 0

:missing_tesseract
echo ERROR: tesseract\tesseract.exe is missing.
exit /b 1

:missing_tessdata
echo ERROR: Required Tesseract language data is incomplete.
exit /b 1

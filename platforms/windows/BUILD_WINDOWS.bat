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

"%PYTHON_EXE%" -c "import sys; raise SystemExit(0 if sys.version_info[:3] == (3, 12, 10) else 1)"
if errorlevel 1 (
  echo ERROR: The locked Windows runtime and license evidence require Python 3.12.10.
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
"%PYTHON_EXE%" -B -c "import tkinter as t; r=t.Tk(); assert r.tk.call('info', 'commands', '::tk::accessible::myl_patch_version'), 'Build the isolated patched Tk runtime first'; assert r.tk.call('::tk::accessible::myl_patch_version') == 'myl-tk91-win-msaa-1'; r.destroy()"
if errorlevel 1 (
  echo ERROR: A patched isolated Tk runtime is required. See docs\VALIDACION_NATIVA_Y_ACCESIBILIDAD_2026-10-25.md.
  exit /b 1
)
"%PYTHON_EXE%" main.py --smoke-test
if errorlevel 1 exit /b 1
"%PYTHON_EXE%" tools\benchmark_catalog.py --check
if errorlevel 1 exit /b 1

if not defined MANAGE_YOUR_LIBRARY_OCR_DIR set "MANAGE_YOUR_LIBRARY_OCR_DIR=%CD%\dist\ocr\payload"
if not exist "%MANAGE_YOUR_LIBRARY_OCR_DIR%\native-ocr-manifest.json" (
  echo Building local OCR from pinned source, without JBIG-KIT or GPL/LGPL OCR libraries...
  "%PYTHON_EXE%" -B tools\build_permissive_ocr.py --output "%CD%\dist\ocr"
  if errorlevel 1 exit /b 1
)
rem Required models: eng spa fra nld chi_sim osd. The validator also verifies notices and sources.
"%PYTHON_EXE%" -B tools\verify_ocr_payload.py "%MANAGE_YOUR_LIBRARY_OCR_DIR%"
if errorlevel 1 exit /b 1

echo Collecting hash-verified Python and wheel license evidence...
set "MANAGE_YOUR_LIBRARY_PYTHON_LICENSE_DIR=%MANAGE_YOUR_LIBRARY_DIST_DIR%\license-staging\python"
set "MANAGE_YOUR_LIBRARY_WHEEL_LICENSE_DIR=%MANAGE_YOUR_LIBRARY_DIST_DIR%\license-staging\wheels"
"%PYTHON_EXE%" -B tools\collect_python_license_evidence.py --output "%MANAGE_YOUR_LIBRARY_PYTHON_LICENSE_DIR%"
if errorlevel 1 exit /b 1
"%PYTHON_EXE%" -B tools\verify_wheel_redistribution.py --collect-notices "%MANAGE_YOUR_LIBRARY_WHEEL_LICENSE_DIR%"
if errorlevel 1 exit /b 1

echo Building the diagnosable onedir application...
"%PYTHON_EXE%" -m PyInstaller --clean --noconfirm --distpath "%MANAGE_YOUR_LIBRARY_DIST_DIR%" --workpath "%TEMP%\ManageYourLibrary_build" platforms\windows\ManageYourLibrary.spec
if errorlevel 1 exit /b 1

echo Verifying controlled native origins and complete wheel notices...
"%PYTHON_EXE%" -B tools\windows_dependency_policy.py "%MANAGE_YOUR_LIBRARY_DIST_DIR%\ManageYourLibrary"
if errorlevel 1 exit /b 1
"%PYTHON_EXE%" -B tools\verify_wheel_redistribution.py --payload "%MANAGE_YOUR_LIBRARY_DIST_DIR%\ManageYourLibrary"
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

echo Checking frozen native accessibility and the real local voice to WAV only...
"%MANAGE_YOUR_LIBRARY_DIST_DIR%\ManageYourLibrary\ManageYourLibrary.exe" --accessibility-self-test "%MANAGE_YOUR_LIBRARY_DIST_DIR%\ManageYourLibrary\accessibility-self-test.json"
if errorlevel 1 exit /b 1
"%MANAGE_YOUR_LIBRARY_DIST_DIR%\ManageYourLibrary\ManageYourLibrary.exe" --windows-provider-self-test "%MANAGE_YOUR_LIBRARY_DIST_DIR%\ManageYourLibrary\windows-provider-self-test.json"
if errorlevel 1 exit /b 1
"%MANAGE_YOUR_LIBRARY_DIST_DIR%\ManageYourLibrary\ManageYourLibrary.exe" --local-voice-self-test "%MANAGE_YOUR_LIBRARY_DIST_DIR%\ManageYourLibrary\local-voice-self-test.json"
if errorlevel 1 exit /b 1

echo Checking the entire frozen payload for embedded Windows profile paths...
"%PYTHON_EXE%" -B tools\verify_binary_privacy.py "%MANAGE_YOUR_LIBRARY_DIST_DIR%\ManageYourLibrary"
if errorlevel 1 exit /b 1

"%PYTHON_EXE%" tools\write_build_manifest.py "%MANAGE_YOUR_LIBRARY_DIST_DIR%\ManageYourLibrary\ManageYourLibrary.exe" --platform windows-x64 --validated-release-gates --validated-runtime --validated-first-use --validated-windows-accessibility
if errorlevel 1 exit /b 1

echo DONE: %MANAGE_YOUR_LIBRARY_DIST_DIR%\ManageYourLibrary\ManageYourLibrary.exe
exit /b 0

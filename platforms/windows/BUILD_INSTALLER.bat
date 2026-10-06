@echo off
setlocal
cd /d "%~dp0..\.."

set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%LocalAppData%\Programs\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" (
  echo ERROR: Inno Setup 6 was not found.
  exit /b 1
)
if not exist "dist\windows\ManageYourLibrary\ManageYourLibrary.exe" (
  echo ERROR: Build the Windows application first.
  exit /b 1
)

set /p "APP_VERSION="<VERSION
if not defined APP_VERSION (
  echo ERROR: VERSION is empty.
  exit /b 1
)

"%ISCC%" /DSourceRoot="%CD%" /DAppVersion=%APP_VERSION% "platforms\windows\ManageYourLibrary.iss"
if errorlevel 1 exit /b 1
echo Installer created in dist\installer

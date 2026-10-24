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
if not defined MANAGE_YOUR_LIBRARY_DIST_DIR set "MANAGE_YOUR_LIBRARY_DIST_DIR=%CD%\dist\windows"
if not defined MANAGE_YOUR_LIBRARY_INSTALLER_DIR set "MANAGE_YOUR_LIBRARY_INSTALLER_DIR=%CD%\dist\installer"
if not exist "%MANAGE_YOUR_LIBRARY_DIST_DIR%\ManageYourLibrary\ManageYourLibrary.exe" (
  echo ERROR: Build the Windows application first.
  exit /b 1
)

set /p "APP_VERSION="<VERSION
if not defined APP_VERSION (
  echo ERROR: VERSION is empty.
  exit /b 1
)

if exist "%MANAGE_YOUR_LIBRARY_INSTALLER_DIR%\ManageYourLibrary-%APP_VERSION%-Setup-x64.exe" (
  echo ERROR: Installer already exists. Choose a new MANAGE_YOUR_LIBRARY_INSTALLER_DIR.
  exit /b 1
)
"%ISCC%" /DSourceRoot="%CD%" /DSourcePayload="%MANAGE_YOUR_LIBRARY_DIST_DIR%\ManageYourLibrary" /DInstallerOutput="%MANAGE_YOUR_LIBRARY_INSTALLER_DIR%" /DAppVersion=%APP_VERSION% "platforms\windows\ManageYourLibrary.iss"
if errorlevel 1 exit /b 1
echo Installer created in %MANAGE_YOUR_LIBRARY_INSTALLER_DIR%

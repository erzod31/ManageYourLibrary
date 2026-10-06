@echo off
title Build EXE - Manage Your Library
cd /d "%~dp0"

echo This shortcut uses the Windows platform build script.
echo.
call "%~dp0platforms\windows\BUILD_WINDOWS.bat"

@echo off
setlocal EnableExtensions
cd /d "%~dp0"

where py >nul 2>nul
if errorlevel 1 (
  echo Python 3 is required to build. Install it from https://www.python.org/downloads/windows/
  exit /b 1
)

if not exist ".build-venv\Scripts\python.exe" py -3 -m venv .build-venv
if errorlevel 1 goto :error
call ".build-venv\Scripts\activate.bat"
python -m pip install --upgrade pip
if errorlevel 1 goto :error
python -m pip install -r requirements.txt pyinstaller
if errorlevel 1 goto :error

pyinstaller --noconfirm --clean packaging\audiocapture.spec
if errorlevel 1 goto :error

set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" (
  echo.
  echo The portable application is built in dist\AudioCaptureStudio\.
  echo To also build the installer, install Inno Setup 6 and run this file again.
  exit /b 0
)
"%ISCC%" packaging\AudioCaptureStudio.iss
if errorlevel 1 goto :error
echo.
echo Installer created in dist\AudioCaptureStudio-Setup.exe
exit /b 0

:error
echo Build failed. See the error above.
exit /b 1

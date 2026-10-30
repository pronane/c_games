@echo off
cd /d "%~dp0"
if not exist "release\MarioKart64.exe" (
    call "release.bat"
    exit /b %ERRORLEVEL%
)
start "" "release\MarioKart64.exe"

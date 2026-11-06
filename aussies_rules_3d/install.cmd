@echo off
rem Aussie Rules 3D — one-click installer for Windows.
setlocal
cd /d "%~dp0"

where node >nul 2>nul
if errorlevel 1 (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
) else (
  node scripts\install.mjs %*
)
pause

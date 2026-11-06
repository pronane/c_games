@echo off
rem Aussie Rules 3D — starts the game on Windows.
rem   start.cmd            build once, serve at http://localhost:8080
rem   start.cmd --dev      development server with hot reload
setlocal
cd /d "%~dp0"

where node >nul 2>nul
if errorlevel 1 (
  if exist "%USERPROFILE%\.aussie-rules-3d\node\node.exe" (
    set "PATH=%USERPROFILE%\.aussie-rules-3d\node;%PATH%"
  ) else (
    echo.
    echo Node is not installed. Run install.cmd / install.ps1 first.
    echo.
    exit /b 1
  )
)

node scripts\start.mjs %*

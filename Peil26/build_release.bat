@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title PEIL 26 - Build Release

echo ============================================
echo   PEIL 26   3D Gaelic Football
echo   Build a Windows app and run it
echo ============================================
echo.

where node >nul 2>&1
if errorlevel 1 (
  echo Node.js was not found on PATH.
  echo Install the current LTS from https://nodejs.org/ and run this file again.
  pause
  exit /b 1
)

echo Installing Electron and the packager. The first run downloads about 100 MB.
call npm install
if errorlevel 1 goto :fail

echo.
echo Building dist\Peil26.exe ...
call npm run dist
if errorlevel 1 goto :fail

if exist "dist\Peil26.exe" (
  echo.
  echo Build succeeded: %cd%\dist\Peil26.exe
  start "" "dist\Peil26.exe"
  exit /b 0
)

echo The packager finished but Peil26.exe was not where this script expected it.
echo Look in the dist folder. You can still play without packaging:
echo    npx electron .
goto :fail

:fail
echo.
echo Build failed. If Electron itself installed, you can still play with:
echo    npx electron .
echo.
pause
exit /b 1

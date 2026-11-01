@echo off
title Guitar Lab installer
echo Installing Guitar Lab. This takes a few minutes the first time.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
echo.
pause

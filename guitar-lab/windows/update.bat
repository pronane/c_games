@echo off
title Guitar Lab update
cd /d "%~dp0.."
if exist "..\.git" (
  where git >nul 2>nul
  if not errorlevel 1 (
    echo Getting the latest Guitar Lab code...
    git pull --ff-only
    if errorlevel 1 (
      echo Could not update the code automatically. Your files were not changed.
      pause
      exit /b 1
    )
  )
) else (
  echo This copy was not downloaded with git. Download the latest ZIP and copy it over this folder,
  echo then this update will rebuild everything.
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" -Update %*
echo.
pause

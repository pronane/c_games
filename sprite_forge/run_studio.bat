@echo off
rem Opens the visual Sprite Forge Studio (Tkinter).  Run setup.bat once first.
setlocal
set "HERE=%~dp0"
if exist "%HERE%.venv\Scripts\python.exe" (
  "%HERE%.venv\Scripts\python.exe" "%HERE%sprite_forge_studio.py"
) else (
  where py >nul 2>nul
  if errorlevel 1 (python "%HERE%sprite_forge_studio.py") else (py -3 "%HERE%sprite_forge_studio.py")
)
if errorlevel 1 pause
endlocal

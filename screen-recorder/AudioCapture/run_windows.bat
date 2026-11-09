@echo off
REM ===================================================================
REM  Audio Capture Studio - Windows launcher
REM  First run installs the dependencies, later runs start immediately.
REM ===================================================================
setlocal
cd /d "%~dp0"

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (
    where python >nul 2>nul && set "PY=python"
)
if not defined PY (
    echo.
    echo   Python was not found.
    echo   Install Python 3.9 or newer from https://www.python.org/downloads/windows/
    echo   and tick "Add python.exe to PATH" during setup.
    echo.
    pause
    exit /b 1
)

if not exist ".venv\" (
    echo Creating a private virtual environment ^(one time only^)...
    %PY% -m venv .venv || goto :error
)

call ".venv\Scripts\activate.bat"

if not exist ".venv\.deps_installed" (
    echo Installing dependencies...
    python -m pip install --upgrade pip --quiet
    python -m pip install -r requirements.txt --quiet || goto :error
    if exist "requirements-windows.txt" python -m pip install -r requirements-windows.txt --quiet
    echo ok > ".venv\.deps_installed"
)

start "" pythonw audiocapture_app.py 2>nul
if errorlevel 1 python audiocapture_app.py
exit /b 0

:error
echo.
echo   Something went wrong while installing dependencies.
echo   Try running this file again, or install manually:
echo       pip install -r requirements.txt
echo.
pause
exit /b 1

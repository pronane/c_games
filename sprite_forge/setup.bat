@echo off
rem Sprite Forge Studio setup - Windows 10/11 (cmd or PowerShell).  Everything goes into .venv\ (and venv_pose\ for
rem mocap) next to this file; nothing is installed system-wide and no ffmpeg / Blender / COLMAP install is needed.
rem   setup.bat               core + extras + mocap (mocap may download Python 3.12 with uv, ~30 MB, + pose model)
rem   setup.bat --core-only   only requirements-core.txt
rem   setup.bat --no-pose     skip the mocap venv
rem   set PYTHON=C:\Python312\python.exe  first to choose the interpreter.
rem From an MSYS2 shell use ./setup.sh instead.
setlocal EnableExtensions
cd /d "%~dp0"
set "EXTRAS=1"
set "POSE=1"
:args
if "%~1"=="" goto args_done
if /i "%~1"=="--core-only" set "EXTRAS=0"
if /i "%~1"=="--core-only" set "POSE=0"
if /i "%~1"=="--no-pose" set "POSE=0"
shift
goto args
:args_done

if exist ".venv\Scripts\python.exe" goto have_venv

rem ---- 1. find a Python >= 3.9 (PYTHON variable, py launcher, python on PATH, else uv)
set "PYEXE="
set "USEPY="
if defined PYTHON set "PYEXE=%PYTHON%"
if defined PYEXE goto make_venv
where py >nul 2>nul
if errorlevel 1 goto try_python
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>nul
if errorlevel 1 goto try_python
set "USEPY=1"
goto make_venv
:try_python
where python >nul 2>nul
if errorlevel 1 goto try_uv
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>nul
if errorlevel 1 goto try_uv
for /f "delims=" %%i in ('python -c "import sys; print(sys.executable)"') do set "PYEXE=%%i"
goto make_venv
:try_uv
where uv >nul 2>nul
if errorlevel 1 goto no_python
echo == no Python 3.9+ found - fetching Python 3.12 with uv
uv python install 3.12
if errorlevel 1 goto no_python
for /f "delims=" %%i in ('uv python find 3.12') do set "PYEXE=%%i"
if not defined PYEXE goto no_python
goto make_venv
:no_python
echo Python 3.9+ was not found.
echo   Install it from https://www.python.org/downloads/windows/  (tick "Add python.exe to PATH" and "tcl/tk")
echo   or:  winget install Python.Python.3.12
echo   or install uv  (powershell -c "irm https://astral.sh/uv/install.ps1 | iex")  and re-run setup.bat
exit /b 1

:make_venv
echo == creating .venv
if defined USEPY (
  py -3 -m venv .venv
) else (
  "%PYEXE%" -m venv .venv
)
if not exist ".venv\Scripts\python.exe" (
  echo venv creation failed
  exit /b 1
)

:have_venv
set "VPY=.venv\Scripts\python.exe"
echo == Python in .venv:
"%VPY%" -c "import sys; print(sys.version)"
echo == installing core packages - requirements-core.txt
"%VPY%" -m pip install --disable-pip-version-check --upgrade pip >nul 2>nul
"%VPY%" -m pip install --disable-pip-version-check -r requirements-core.txt
if errorlevel 1 (
  echo core install failed - see the messages above
  exit /b 1
)
if not "%EXTRAS%"=="1" goto skip_extras
echo == installing extras - requirements-extras.txt - optional, failures are not fatal
"%VPY%" -m pip install --disable-pip-version-check -r requirements-extras.txt
if errorlevel 1 echo some extras failed - forge.bat doctor shows what that disables
:skip_extras
if not "%POSE%"=="1" goto skip_pose
echo == mocap: venv_pose with Python 3.12 + mediapipe + pose model - tools\setup_pose.py
"%VPY%" tools\setup_pose.py
if errorlevel 1 echo mocap setup failed - everything else works. Re-run: %VPY% tools\setup_pose.py
:skip_pose
echo == forge.py doctor
"%VPY%" forge.py doctor
echo.
echo Next steps
echo   run_studio.bat                                     visual Studio (Help tab explains every field)
echo   forge.bat build --spec examples_char.txt --preset fighter14     demo character -^> out\rua_keeper
echo   forge.bat video --clip walk:8=examples_video\walk_static.mp4 --name vid --consoles snes
echo   forge.bat scan --video examples_video\orbit_mannequin.mp4 --frames 72 --run --name orbit
echo   forge.bat help quickstart        beginner guide;    forge.bat doctor    re-check
echo   build_release.bat                build + verify every demo
endlocal
exit /b 0

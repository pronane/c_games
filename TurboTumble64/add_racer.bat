@echo off
rem ==========================================================================
rem  TURBO TUMBLE 64 - add a racer from a photo or a text description
rem
rem  EASIEST:  drag a photo (jpg/png) onto this file and type a name.
rem            drag a .txt character description onto it for a drawn racer
rem            (see tools\example\racer_spec_example.txt).
rem  OR, from a command prompt in this folder:
rem     add_racer.bat --photo me.jpg --name "Speedy Me"
rem     add_racer.bat --spec tools\example\racer_spec_example.txt
rem     add_racer.bat --help
rem  The racer is written to assets\characters\<name>\ and appears on the
rem  character select screen the next time the game starts.
rem  Needs MSYS2 (https://www.msys2.org); python + pillow + numpy + scipy are
rem  installed automatically with pacman the first time.
rem ==========================================================================
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
title Turbo Tumble 64 - add a racer

set "MSYS="
if defined MSYS2_ROOT if exist "%MSYS2_ROOT%\usr\bin\bash.exe" set "MSYS=%MSYS2_ROOT%"
for %%D in ("C:\msys64" "D:\msys64" "E:\msys64" "C:\msys2" "C:\tools\msys64" "%USERPROFILE%\msys64" "%USERPROFILE%\scoop\apps\msys2\current" "%LOCALAPPDATA%\msys64" "%ProgramFiles%\msys64" "C:\ProgramData\chocolatey\lib\msys2\tools\msys64") do (
    if not defined MSYS if exist "%%~D\usr\bin\bash.exe" set "MSYS=%%~D"
)
if not defined MSYS (
    echo [ERROR] Could not find MSYS2. Install it from https://www.msys2.org
    echo         or set MSYS2_ROOT to its folder, then run me again.
    goto :fail
)
echo [ok] MSYS2 found at %MSYS%
set "PATH=%MSYS%\ucrt64\bin;%MSYS%\usr\bin;%PATH%"
set "PY=%MSYS%\ucrt64\bin\python.exe"

set "NEED=0"
if not exist "%PY%" set "NEED=1"
if "%NEED%"=="0" (
    "%PY%" -c "import PIL, numpy, scipy" >nul 2>&1
    if errorlevel 1 set "NEED=1"
)
if "%NEED%"=="1" (
    echo [..] installing python, pillow, numpy and scipy with pacman - needs internet, a few minutes the first time
    "%MSYS%\usr\bin\bash.exe" -lc "pacman -S --needed --noconfirm mingw-w64-ucrt-x86_64-python mingw-w64-ucrt-x86_64-python-pillow mingw-w64-ucrt-x86_64-python-numpy mingw-w64-ucrt-x86_64-python-scipy"
    if errorlevel 1 echo [warn] pacman reported a problem - will still try.
)
if not exist "%PY%" (
    echo [ERROR] python was not found in %MSYS%\ucrt64\bin.
    echo         Open "MSYS2 UCRT64" and run:
    echo         pacman -S mingw-w64-ucrt-x86_64-python mingw-w64-ucrt-x86_64-python-pillow mingw-w64-ucrt-x86_64-python-numpy mingw-w64-ucrt-x86_64-python-scipy
    goto :fail
)

if "%~1"=="" (
    "%PY%" tools\add_racer.py --help
    echo.
    echo Tip: drag a photo or a character .txt onto add_racer.bat
    goto :done
)
set "FIRST=%~1"
if "!FIRST:~0,1!"=="-" goto :passthru
if /i "%~1"=="build" goto :passthru
rem dropped file: photo or text spec
set "EXT=%~x1"
if /i "%EXT%"==".txt" (
    "%PY%" tools\add_racer.py --spec "%~1"
    goto :check
)
if /i "%EXT%"==".ini" (
    set /p "RNAME=Racer name: "
    "%PY%" tools\add_racer.py --hints "%~1" --name "!RNAME!"
    goto :check
)
set /p "RNAME=Racer name (e.g. Speedy Sam): "
if "!RNAME!"=="" set "RNAME=%~n1"
set "BACK="
if not "%~2"=="" set "BACK=--back "%~2""
"%PY%" tools\add_racer.py --photo "%~1" !BACK! --name "!RNAME!" --keep-cutouts "work_cutouts\!RNAME!"
goto :check

:passthru
"%PY%" tools\add_racer.py %*

:check
if errorlevel 1 goto :fail
echo.
echo Done. Start the game - the new racer is on the character select screen.
echo If the cut-out is not clean, open preview.png in the racer's folder and see
echo HOW_TO_ADD_A_RACER.txt for the --box / --bg-box / --fg-box hints.
goto :done

:fail
echo.
echo Something went wrong - see the messages above.
:done
echo.
pause
endlocal

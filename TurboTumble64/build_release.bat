@echo off
rem ==========================================================================
rem  TURBO TUMBLE 64 - one-click release build for Windows (MSYS2 UCRT64 + gcc)
rem  Double-click me. I find MSYS2, install gcc + raylib if missing, build the
rem  game and launch it. If anything goes wrong you get a readable error and
rem  the prebuilt game is launched instead.
rem ==========================================================================
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
title Turbo Tumble 64 - release build
set "GAME=TurboTumble64"
set "LOG=build_log.txt"
set "PREBUILT=prebuilt\%GAME%.exe"
echo Turbo Tumble 64 build log > "%LOG%"

echo.
echo  ==============================================
echo      TURBO TUMBLE 64  -  release build
echo  ==============================================
echo.

rem ---------------------------------------------------------------- 1. MSYS2
set "MSYS="
if defined MSYS2_ROOT if exist "%MSYS2_ROOT%\usr\bin\bash.exe" set "MSYS=%MSYS2_ROOT%"
for %%D in ("C:\msys64" "D:\msys64" "E:\msys64" "C:\msys2" "C:\tools\msys64" "%USERPROFILE%\msys64" "%USERPROFILE%\scoop\apps\msys2\current" "%LOCALAPPDATA%\msys64" "%ProgramFiles%\msys64" "C:\ProgramData\chocolatey\lib\msys2\tools\msys64") do (
    if not defined MSYS if exist "%%~D\usr\bin\bash.exe" set "MSYS=%%~D"
)
if not defined MSYS (
    echo [ERROR] Could not find MSYS2.
    echo         Looked in C:\msys64, D:\msys64, C:\msys2, C:\tools\msys64, %%USERPROFILE%%\msys64 ...
    echo         Install it from https://www.msys2.org or set MSYS2_ROOT to its folder.
    goto :fail
)
echo [ok] MSYS2 found at %MSYS%
set "PATH=%MSYS%\ucrt64\bin;%MSYS%\usr\bin;%PATH%"

rem ---------------------------------------------------------------- 2. gcc + raylib
set "NEEDPKG=0"
if not exist "%MSYS%\ucrt64\bin\gcc.exe" set "NEEDPKG=1"
if not exist "%MSYS%\ucrt64\include\raylib.h" set "NEEDPKG=1"
if "%NEEDPKG%"=="1" (
    echo [..] gcc or raylib missing - installing them with pacman. This needs internet and can take a few minutes.
    "%MSYS%\usr\bin\bash.exe" -lc "pacman -S --needed --noconfirm mingw-w64-ucrt-x86_64-gcc mingw-w64-ucrt-x86_64-raylib"
    if errorlevel 1 echo [warn] pacman reported a problem - will still try to build.
)
if not exist "%MSYS%\ucrt64\bin\gcc.exe" (
    echo [ERROR] gcc was not found in %MSYS%\ucrt64\bin even after trying to install it.
    echo         Open "MSYS2 UCRT64" and run:  pacman -S mingw-w64-ucrt-x86_64-gcc mingw-w64-ucrt-x86_64-raylib
    goto :fail
)
for /f "delims=" %%V in ('gcc -dumpversion 2^>nul') do set "GCCVER=%%V"
echo [ok] gcc %GCCVER%

rem ---------------------------------------------------------------- 3. compile
set "SRC=src\main.c src\util.c src\characters.c src\tracks.c src\kart.c src\items.c src\render.c src\race.c src\menu.c src\audio.c src\input.c src\padraw.c"
set "CFLAGS=-std=c99 -O2 -Wall -Wno-missing-braces"
set "SYSLIBS=-lopengl32 -lgdi32 -lwinmm"
if exist "%GAME%.exe" del /q "%GAME%.exe" >nul 2>&1
if exist "%GAME%.exe" (
    echo [ERROR] %GAME%.exe is in use - close the game and run me again.
    goto :fail
)

if exist "%MSYS%\ucrt64\include\raylib.h" (
    echo [..] Building against the MSYS2 raylib package - static link ...
    echo ==== static link against MSYS2 raylib ==== >> "%LOG%"
    gcc %CFLAGS% %SRC% -o %GAME%.exe -static -lraylib -lglfw3 %SYSLIBS% -mwindows >> "%LOG%" 2>&1
    if exist "%GAME%.exe" goto :built
    echo [..] static link did not work, trying the raylib DLL ...
    echo ==== dynamic link against MSYS2 raylib ==== >> "%LOG%"
    gcc %CFLAGS% %SRC% -o %GAME%.exe -lraylib %SYSLIBS% -mwindows >> "%LOG%" 2>&1
    if exist "%GAME%.exe" (
        for %%F in (libraylib.dll glfw3.dll libgcc_s_seh-1.dll libwinpthread-1.dll) do (
            if exist "%MSYS%\ucrt64\bin\%%F" copy /y "%MSYS%\ucrt64\bin\%%F" . >nul
        )
        goto :built
    )
)

echo [..] Building the bundled raylib 5.5 from source - first time takes about a minute ...
call :bundled_raylib
if errorlevel 1 (
    echo [ERROR] Could not compile the bundled raylib. See build_log.txt
    goto :fail
)
echo ==== static link against bundled raylib 5.5 ==== >> "%LOG%"
gcc %CFLAGS% -Ideps\raylib-5.5\src %SRC% -o %GAME%.exe build\raylib\libraylib.a -static %SYSLIBS% -mwindows >> "%LOG%" 2>&1
if not exist "%GAME%.exe" (
    echo [ERROR] Compiling the game failed. Last lines of build_log.txt:
    echo ---------------------------------------------------------------
    powershell -NoProfile -Command "Get-Content -Tail 25 build_log.txt" 2>nul || type "%LOG%"
    echo ---------------------------------------------------------------
    goto :fail
)

:built
echo [ok] Build succeeded: %~dp0%GAME%.exe
echo.
echo  Launching Turbo Tumble 64 ... have fun!
start "" "%GAME%.exe"
endlocal
exit /b 0

rem ---------------------------------------------------------------- helpers
:bundled_raylib
if exist "build\raylib\libraylib.a" exit /b 0
if not exist "build\raylib" mkdir "build\raylib"
set "RLS=deps\raylib-5.5\src"
set "RLF=-std=c99 -O2 -Wno-missing-braces -D_GNU_SOURCE -DPLATFORM_DESKTOP_GLFW -DGRAPHICS_API_OPENGL_33 -I%RLS% -I%RLS%\external\glfw\include"
echo ==== bundled raylib 5.5 ==== >> "%LOG%"
for %%M in (rcore rshapes rtextures rtext utils rmodels raudio rglfw) do (
    echo       compiling %%M.c
    gcc -c "%RLS%\%%M.c" %RLF% -o "build\raylib\%%M.o" >> "%LOG%" 2>&1
    if errorlevel 1 exit /b 1
)
ar rcs build\raylib\libraylib.a build\raylib\rcore.o build\raylib\rshapes.o build\raylib\rtextures.o build\raylib\rtext.o build\raylib\utils.o build\raylib\rmodels.o build\raylib\raudio.o build\raylib\rglfw.o >> "%LOG%" 2>&1
if errorlevel 1 exit /b 1
exit /b 0

:fail
echo.
echo  Build did not complete. Details are in build_log.txt
if exist "%PREBUILT%" (
    echo  A ready-made copy of the game is included - press any key to play that instead.
    pause >nul
    copy /y "%PREBUILT%" "%GAME%.exe" >nul 2>&1
    if exist "%GAME%.exe" (start "" "%GAME%.exe") else (start "" "%PREBUILT%")
) else (
    pause
)
endlocal
exit /b 1

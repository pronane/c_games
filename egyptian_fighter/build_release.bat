@echo off
setlocal EnableDelayedExpansion
:: ==========================================================================
::  Egyptian Fighter - release build for Windows (MSYS2 UCRT64 + gcc + raylib)
::
::  One-time setup, in the "MSYS2 UCRT64" terminal:
::      pacman -S --needed mingw-w64-ucrt-x86_64-gcc mingw-w64-ucrt-x86_64-raylib
::
::  Then double-click this file, or run it from VS Code / CMD / PowerShell.
::  Output: release\egyptian_fighter.exe + release\assets\  (zip that folder to share)
::  Test mode: release\egyptian_fighter.exe --demo 5      (5 = PADEL MIKE, 4 = DEC, 6 = DARAGH)
:: ==========================================================================
cd /d "%~dp0"

if not defined MSYS2_ROOT set "MSYS2_ROOT=C:\msys64"
set "UCRT=%MSYS2_ROOT%\ucrt64"

where gcc >nul 2>&1
if errorlevel 1 (
    if exist "%UCRT%\bin\gcc.exe" (
        set "PATH=%UCRT%\bin;%PATH%"
    ) else (
        echo ERROR: gcc not found. Install MSYS2 to C:\msys64 or set MSYS2_ROOT.
        pause & exit /b 1
    )
)
if not exist "%UCRT%\include\raylib.h" (
    echo ERROR: raylib not found in %UCRT%.
    echo In the MSYS2 UCRT64 terminal run:  pacman -S mingw-w64-ucrt-x86_64-raylib
    pause & exit /b 1
)

if not exist release mkdir release
set "SRC=src\main.c src\player.c src\game.c src\demo.c src\pad.c src\gfx.c"
set "CFLAGS=-std=c99 -O2 -Wall -I"%UCRT%\include""
set "LIBS=-L"%UCRT%\lib" -lraylib -lopengl32 -lgdi32 -lwinmm"

echo Compiling (static, no console window)...
:: MSYS2's raylib uses the separate glfw package, so -lglfw3 is tried first.
:: Raw-joystick fallback for unmapped USB pads needs GLFW; the last attempt builds without it.
set "BUILT="
set "LINKMODE=-static"
set "GLFWLIB=-lglfw3"
gcc %CFLAGS% %SRC% -o release\egyptian_fighter.exe -L"%UCRT%\lib" -lraylib -lglfw3 -lopengl32 -lgdi32 -lwinmm -mwindows -static >nul 2>&1 && set "BUILT=static" && set "LINKMODE=-static"
if not defined BUILT (
    set "GLFWLIB="
    gcc %CFLAGS% %SRC% -o release\egyptian_fighter.exe %LIBS% -mwindows -static >nul 2>&1 && set "BUILT=static" && set "LINKMODE=-static"
)
if not defined BUILT (
    echo Static link failed - retrying with the raylib DLL...
    set "GLFWLIB=-lglfw3"
    gcc %CFLAGS% %SRC% -o release\egyptian_fighter.exe %LIBS% -lglfw3 -mwindows -static-libgcc >nul 2>&1 && set "BUILT=dll" && set "LINKMODE=-static-libgcc"
)
if not defined BUILT (
    set "GLFWLIB="
    gcc %CFLAGS% %SRC% -o release\egyptian_fighter.exe %LIBS% -mwindows -static-libgcc >nul 2>&1 && set "BUILT=dll" && set "LINKMODE=-static-libgcc"
)
if not defined BUILT (
    echo Retrying without the raw-joystick fallback ^(mapped / XInput pads still work^)...
    set "CFLAGS=%CFLAGS% -DEF_NO_RAW_PAD"
    gcc %CFLAGS% -DEF_NO_RAW_PAD %SRC% -o release\egyptian_fighter.exe %LIBS% -mwindows -static-libgcc
    if errorlevel 1 ( echo BUILD FAILED & pause & exit /b 1 )
    set "BUILT=dll"
    set "LINKMODE=-static-libgcc"
)
if "%BUILT%"=="dll" (
    for %%D in (libraylib.dll raylib.dll glfw3.dll libwinpthread-1.dll) do (
        if exist "%UCRT%\bin\%%D" copy /Y "%UCRT%\bin\%%D" release\ >nul
    )
)
echo Linked: %BUILT%

:: console build for debugging (shows TraceLog output: loaded sheets, missing files)
gcc %CFLAGS% %SRC% -o release\egyptian_fighter_console.exe %LIBS% %GLFWLIB% %LINKMODE% >nul 2>&1

echo Copying assets...
robocopy assets release\assets /E /NFL /NDL /NJH /NJS /NP >nul
if %errorlevel% GEQ 8 ( echo Asset copy failed & pause & exit /b 1 )

echo.
echo Build OK:  release\egyptian_fighter.exe
echo (run release\egyptian_fighter_console.exe to see asset loading messages)
echo.
if /i not "%1"=="norun" (
    pushd release
    start "" egyptian_fighter.exe
    popd
)
endlocal

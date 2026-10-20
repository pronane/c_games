@echo off
setlocal EnableDelayedExpansion

echo ======================================================
echo  Image to 3D Mesh Generator - Build Script (Windows)
echo ======================================================
echo.

:: -------------------------------------------------------
:: 1. Try to find a working compiler + raylib
:: -------------------------------------------------------

set "CC="
set "CFLAGS=-O2 -std=c99"
set "LIBS=-lraylib -lopengl32 -lgdi32 -lwinmm"

:: Prefer gcc from MinGW / MSYS2 / w64devkit if available
where gcc >nul 2>&1
if %ERRORLEVEL% equ 0 (
    set "CC=gcc"
    echo Found gcc
) else (
    where cl >nul 2>&1
    if %ERRORLEVEL% equ 0 (
        set "CC=cl"
        echo Found MSVC cl.exe
    )
)

if "%CC%"=="" (
    echo.
    echo ERROR: No C compiler found in PATH.
    echo.
    echo Please install one of the following:
    echo   - w64devkit          https://github.com/skeeto/w64devkit
    echo   - MSYS2 + mingw-w64  https://www.msys2.org
    echo   - Visual Studio with C++ workload
    echo.
    echo After installing, open a new terminal and run this bat again.
    pause
    exit /b 1
)

:: -------------------------------------------------------
:: 2. Check for raylib
:: -------------------------------------------------------
echo.
echo Checking for raylib...

:: Common locations
set "RAYLIB_FOUND=0"

:: Try pkg-config style (if available)
where pkg-config >nul 2>&1
if %ERRORLEVEL% equ 0 (
    pkg-config --exists raylib
    if !ERRORLEVEL! equ 0 (
        set "RAYLIB_FOUND=1"
        for /f "delims=" %%i in ('pkg-config --cflags raylib') do set "CFLAGS=!CFLAGS! %%i"
        for /f "delims=" %%i in ('pkg-config --libs raylib') do set "LIBS=%%i"
        echo Found raylib via pkg-config
    )
)

:: Try common install paths
if "%RAYLIB_FOUND%"=="0" (
    if exist "C:\raylib\raylib\src\raylib.h" (
        set "CFLAGS=%CFLAGS% -IC:\raylib\raylib\src"
        set "LIBS=-L C:\raylib\raylib\src %LIBS%"
        set "RAYLIB_FOUND=1"
        echo Found raylib in C:\raylib
    )
)

if "%RAYLIB_FOUND%"=="0" (
    if exist "%USERPROFILE%\raylib\src\raylib.h" (
        set "CFLAGS=%CFLAGS% -I%USERPROFILE%\raylib\src"
        set "LIBS=-L %USERPROFILE%\raylib\src %LIBS%"
        set "RAYLIB_FOUND=1"
        echo Found raylib in user profile
    )
)

if "%RAYLIB_FOUND%"=="0" (
    echo.
    echo WARNING: raylib not found automatically.
    echo.
    echo You need raylib installed to compile this program.
    echo.
    echo Easiest options:
    echo   1. Download pre-built raylib for Windows from:
    echo      https://github.com/raysan5/raylib/releases
    echo   2. Or install via vcpkg / MSYS2
    echo.
    echo If you already have raylib, edit this build.bat and add:
    echo   set CFLAGS=%%CFLAGS%% -I"path\to\raylib\src"
    echo   set LIBS=-L"path\to\raylib\src" %%LIBS%%
    echo.
    pause
    exit /b 1
)

:: -------------------------------------------------------
:: 3. Compile
:: -------------------------------------------------------
echo.
echo Compiling image_to_mesh_gui.c ...
echo.

if "%CC%"=="gcc" (
    gcc %CFLAGS% -o image_to_mesh_gui.exe image_to_mesh_gui.c %LIBS%
) else (
    :: MSVC path (basic)
    cl /O2 /Fe:image_to_mesh_gui.exe image_to_mesh_gui.c /I"%INCLUDE%" /link raylib.lib opengl32.lib gdi32.lib winmm.lib
)

if %ERRORLEVEL% neq 0 (
    echo.
    echo BUILD FAILED.
    echo Check the error messages above.
    pause
    exit /b 1
)

echo.
echo ======================================================
echo  BUILD SUCCESSFUL
echo ======================================================
echo.
echo Running the program...
echo.

image_to_mesh_gui.exe

echo.
echo Program closed.
pause

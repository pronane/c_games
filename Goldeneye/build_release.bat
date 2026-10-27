@echo off
setlocal

cd /d "%~dp0" || (
    echo ERROR: Could not open the project folder.
    exit /b 1
)

set "GCC="
if exist "C:\msys64\ucrt64\bin\gcc.exe" set "GCC=C:\msys64\ucrt64\bin\gcc.exe"
if not defined GCC if exist "C:\msys64\mingw64\bin\gcc.exe" set "GCC=C:\msys64\mingw64\bin\gcc.exe"
if not defined GCC (
    for %%G in (gcc.exe) do set "GCC=%%~$PATH:G"
)
if not defined GCC (
    echo ERROR: GCC was not found. Install raylib and GCC, or add gcc.exe to PATH.
    exit /b 1
)

set "RAYLIB_INCLUDE="
set "RAYLIB_LIB="
if exist "C:\msys64\ucrt64\include\raylib.h" set "RAYLIB_INCLUDE=-IC:\msys64\ucrt64\include"
if exist "C:\msys64\ucrt64\lib\libraylib.a" set "RAYLIB_LIB=-LC:\msys64\ucrt64\lib"
if not defined RAYLIB_INCLUDE if exist "C:\msys64\mingw64\include\raylib.h" set "RAYLIB_INCLUDE=-IC:\msys64\mingw64\include"
if not defined RAYLIB_LIB if exist "C:\msys64\mingw64\lib\libraylib.a" set "RAYLIB_LIB=-LC:\msys64\mingw64\lib"

echo Compiling Glass Harbor...
"%GCC%" main.c game.c -o MySpy.exe -O2 -std=c99 -Wall -Wextra -Werror -DPLATFORM_RAYLIB %RAYLIB_INCLUDE% %RAYLIB_LIB% -lraylib -lopengl32 -lgdi32 -lwinmm
if errorlevel 1 (
    echo ERROR: Compilation failed. Check that GCC and raylib are installed for the same toolchain.
    exit /b 1
)

echo Build succeeded. Starting Glass Harbor...
MySpy.exe
exit /b %ERRORLEVEL%

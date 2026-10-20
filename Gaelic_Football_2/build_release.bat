@echo off
setlocal

pushd "%~dp0"
if errorlevel 1 (
    echo ERROR: Could not open the project folder.
    exit /b 1
)

set "GCC="
for /f "delims=" %%G in ('where gcc 2^>nul') do if not defined GCC set "GCC=%%G"

if not defined GCC if exist "C:\msys64\ucrt64\bin\gcc.exe" set "GCC=C:\msys64\ucrt64\bin\gcc.exe"
if not defined GCC if exist "C:\msys64\mingw64\bin\gcc.exe" set "GCC=C:\msys64\mingw64\bin\gcc.exe"

if not defined GCC (
    echo ERROR: GCC was not found. Install MSYS2 with the UCRT64 GCC toolchain.
    popd
    exit /b 1
)

for %%G in ("%GCC%") do set "GCC_BIN=%%~dpG"
set "PATH=%GCC_BIN%;%PATH%"
if defined RAYLIB_DIR goto raylib_dir_set
for %%P in ("%GCC_BIN%..") do set "RAYLIB_DIR=%%~fP"

:raylib_dir_set
if not exist "%RAYLIB_DIR%\include\raylib.h" (
    echo ERROR: raylib.h was not found under "%RAYLIB_DIR%\include".
    echo Set RAYLIB_DIR to the raylib installation prefix if it is installed elsewhere.
    popd
    exit /b 1
)
if not exist "%RAYLIB_DIR%\lib\libraylib.a" (
    echo ERROR: libraylib.a was not found under "%RAYLIB_DIR%\lib".
    echo Set RAYLIB_DIR to the raylib installation prefix if it is installed elsewhere.
    popd
    exit /b 1
)

echo Building Gaelic Football...
"%GCC%" -std=c99 -O2 -DNDEBUG -Wall -Wextra -Werror -DPLATFORM_RAYLIB ^
    -I"%CD%\src" -I"%RAYLIB_DIR%\include" ^
    "%CD%\src\main.c" "%CD%\src\game.c" "%CD%\src\audio.c" "%CD%\src\player_model.c" ^
    -L"%RAYLIB_DIR%\lib" -lraylib -lopengl32 -lgdi32 -lwinmm -lm ^
    -o "%CD%\gaelic_football.exe"
if errorlevel 1 (
    echo ERROR: Build failed.
    popd
    exit /b 1
)

echo Build complete. Starting the game...
"%CD%\gaelic_football.exe"
set "GAME_EXIT_CODE=%ERRORLEVEL%"
popd
exit /b %GAME_EXIT_CODE%

@echo off
rem Builds gaelic_football.exe with MSYS2 UCRT64 gcc + raylib and runs it.
rem   Install once (in an "MSYS2 UCRT64" shell):
rem     pacman -S --needed mingw-w64-ucrt-x86_64-gcc mingw-w64-ucrt-x86_64-raylib mingw-w64-ucrt-x86_64-glfw
rem   Override locations with: set MSYS2_ROOT=D:\msys64   or   set RAYLIB_DIR=C:\raylib
setlocal
pushd "%~dp0"

if not defined MSYS2_ROOT set "MSYS2_ROOT=C:\msys64"
set "GCC="
if exist "%MSYS2_ROOT%\ucrt64\bin\gcc.exe" set "GCC=%MSYS2_ROOT%\ucrt64\bin\gcc.exe"
if not defined GCC for /f "delims=" %%G in ('where gcc 2^>nul') do if not defined GCC set "GCC=%%G"
if not defined GCC (
    echo ERROR: gcc not found. Install MSYS2 UCRT64 gcc, or set MSYS2_ROOT.
    popd & exit /b 1
)
for %%G in ("%GCC%") do set "GCC_BIN=%%~dpG"
set "PATH=%GCC_BIN%;%PATH%"
if not defined RAYLIB_DIR for %%P in ("%GCC_BIN%..") do set "RAYLIB_DIR=%%~fP"

if not exist "%RAYLIB_DIR%\include\raylib.h" (
    echo ERROR: raylib.h not found in "%RAYLIB_DIR%\include".
    echo Run: pacman -S mingw-w64-ucrt-x86_64-raylib   or set RAYLIB_DIR.
    popd & exit /b 1
)

echo Using "%GCC%"  with raylib in "%RAYLIB_DIR%"
"%GCC%" -std=c99 -O2 -DNDEBUG -Wall -Wextra ^
    -I"%RAYLIB_DIR%\include" src\main.c src\game.c ^
    -L"%RAYLIB_DIR%\lib" -lraylib -lglfw3 -lopengl32 -lgdi32 -lwinmm -lm ^
    -static-libgcc -o gaelic_football.exe
if errorlevel 1 (
    echo ERROR: Build failed. If glfw is missing run: pacman -S mingw-w64-ucrt-x86_64-glfw
    popd & exit /b 1
)
rem MSYS2's raylib uses GLFW as a DLL, so copy the runtime DLLs next to the exe.
for %%D in (glfw3.dll libwinpthread-1.dll libraylib.dll) do if exist "%RAYLIB_DIR%\bin\%%D" copy /y "%RAYLIB_DIR%\bin\%%D" . >nul
echo Build complete. Starting the game...
gaelic_football.exe
set "RC=%ERRORLEVEL%"
popd
exit /b %RC%

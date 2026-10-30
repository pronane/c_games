@echo off
setlocal
rem ---------------------------------------------------------------
rem  Facility 64 - release build (MSYS2 UCRT64 gcc + raylib)
rem  Needs:  pacman -S mingw-w64-ucrt-x86_64-gcc mingw-w64-ucrt-x86_64-raylib
rem
rem  Output:
rem    game.exe                 (runs from this folder, uses .\assets)
rem    release\                 exe + DLLs + assets\ (textures + models) + tools\ (self-contained)
rem    Facility64_release.zip   zip of the release folder
rem ---------------------------------------------------------------
set "MSYS_BIN=C:\msys64\ucrt64\bin"
set "PATH=%MSYS_BIN%;%PATH%"
cd /d "%~dp0"

where gcc >nul 2>nul
if errorlevel 1 (
    echo ERROR: gcc not found. Is MSYS2 installed at C:\msys64 with the UCRT64 toolchain?
    pause
    exit /b 1
)

echo Building game.exe ...
rem main.c #includes gfx_textures.c, gfx_models.c, gfx_enhanced.c and input_pad.c (single translation unit)
gcc src\main.c -o game.exe -std=c99 -Wall -O2 -static-libgcc -lraylib -lopengl32 -lgdi32 -lwinmm
if errorlevel 1 (
    echo.
    echo BUILD FAILED - see errors above.
    pause
    exit /b 1
)

rem Copy runtime DLLs next to the exe so it also runs when double-clicked
for %%D in (libraylib.dll glfw3.dll libwinpthread-1.dll libgcc_s_seh-1.dll) do (
    if exist "%MSYS_BIN%\%%D" copy /y "%MSYS_BIN%\%%D" . >nul
)

rem Textures: shipped in assets\textures. If the folder is missing, regenerate it
rem (the game can also generate everything in memory, so this is optional).
if not exist "assets\textures\wall_concrete.png" (
    echo Generating assets\textures ...
    game.exe --export-textures --quit-after-export
)

echo Packaging release\ ...
if exist release rmdir /s /q release
mkdir release
copy /y game.exe release\ >nul
for %%D in (libraylib.dll glfw3.dll libwinpthread-1.dll libgcc_s_seh-1.dll) do (
    if exist "%%D" copy /y "%%D" release\ >nul
)
rem assets\textures (Classic + Enhanced) and assets\models (Enhanced-mode GLB models + models.cfg)
xcopy /e /i /q /y assets release\assets >nul
if not exist "release\assets\models\models.cfg" echo WARNING: assets\models missing - Enhanced mode (F2) will fall back to Classic.
if exist tools xcopy /e /i /q /y tools release\tools >nul
copy /y README.md release\ >nul
rem optional SDL controller mappings for non-XInput pads (e.g. Easy SMX in D-input mode)
if exist gamecontrollerdb.txt copy /y gamecontrollerdb.txt release\ >nul

if exist Facility64_release.zip del /q Facility64_release.zip
powershell -NoProfile -Command "Compress-Archive -Path 'release\*' -DestinationPath 'Facility64_release.zip' -Force"
if errorlevel 1 (
    echo WARNING: could not create the zip, but release\ is ready.
) else (
    echo Created Facility64_release.zip
)

echo.
echo Build OK: game.exe   (release copy in release\)
echo Run it with:  game.exe
pause

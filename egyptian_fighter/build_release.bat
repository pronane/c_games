@echo off
setlocal EnableDelayedExpansion

echo ========================================
echo  Egyptian Fighter - Release Build
echo ========================================
echo.

:: -------------------------------------------------
:: Detect if we are inside MSYS2 / UCRT64 / MINGW64
:: -------------------------------------------------
set "IS_MSYS=0"
if defined MSYSTEM (
    echo %MSYSTEM% | findstr /i "UCRT64 MINGW64 CLANG64" >nul 2>&1
    if !ERRORLEVEL! EQU 0 set "IS_MSYS=1"
)

:: -------------------------------------------------
:: 1. Find gcc
:: -------------------------------------------------
where gcc >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: gcc not found in PATH.
    echo.
    echo Please open "MSYS2 UCRT64" terminal and run this script from there.
    echo.
    pause
    exit /b 1
)

echo Found gcc
gcc -dumpmachine
echo.

:: -------------------------------------------------
:: 2. Set Raylib paths
:: -------------------------------------------------
if not defined RAYLIB_PATH (
    if exist "C:\msys64\ucrt64\include\raylib.h" (
        set "RAYLIB_PATH=C:\msys64\ucrt64"
        set "RAYLIB_PATH_MSYS=/ucrt64"
    ) else if exist "C:\msys64\mingw64\include\raylib.h" (
        set "RAYLIB_PATH=C:\msys64\mingw64"
        set "RAYLIB_PATH_MSYS=/mingw64"
    ) else (
        echo WARNING: Could not auto-detect Raylib.
        echo Set RAYLIB_PATH=C:\msys64\ucrt64
        pause
        exit /b 1
    )
) else (
    :: User set RAYLIB_PATH, try to guess MSYS path
    set "RAYLIB_PATH_MSYS=%RAYLIB_PATH%"
    set "RAYLIB_PATH_MSYS=!RAYLIB_PATH_MSYS:C:\msys64=/!"
    set "RAYLIB_PATH_MSYS=!RAYLIB_PATH_MSYS:\=/!"
)

echo Using RAYLIB_PATH=%RAYLIB_PATH%
echo.

:: -------------------------------------------------
:: 3. Create output folder
:: -------------------------------------------------
if not exist "bin" mkdir bin

:: -------------------------------------------------
:: 4. Compile
:: -------------------------------------------------
echo Compiling...

if "%IS_MSYS%"=="1" (
    :: Running inside MSYS2 → use Unix-style paths (this is the reliable way)
    gcc -std=c99 -O2 -Wall ^
        src/main.c src/player.c src/game.c ^
        -I%RAYLIB_PATH_MSYS%/include -L%RAYLIB_PATH_MSYS%/lib ^
        -lraylib -lopengl32 -lgdi32 -lwinmm ^
        -o bin/egyptian_fighter.exe
) else (
    :: Running from normal PowerShell / CMD
    gcc -std=c99 -O2 -Wall ^
        src/main.c src/player.c src/game.c ^
        -I"%RAYLIB_PATH%\include" -L"%RAYLIB_PATH%\lib" ^
        -lraylib -lopengl32 -lgdi32 -lwinmm ^
        -o bin/egyptian_fighter.exe
)

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Compilation FAILED.
    pause
    exit /b 1
)

echo.
echo Build successful!  bin\egyptian_fighter.exe
echo.

:: -------------------------------------------------
:: 5. Copy assets
:: -------------------------------------------------
if not exist "bin\assets" mkdir bin\assets
xcopy /Y /Q /E /I "assets\*" "bin\assets\" >nul 2>&1
echo Assets copied to bin\assets\
echo.
echo NOTE: Missing PNG files show colored placeholders + console warnings.
echo.

:: -------------------------------------------------
:: 6. Run
:: -------------------------------------------------
echo Starting game...
echo.
cd bin
egyptian_fighter.exe
cd ..

endlocal

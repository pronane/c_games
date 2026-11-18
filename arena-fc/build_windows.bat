@echo off
REM ============================================================
REM  Arena FC — Windows Build Script
REM  Builds the Godot project and runs tests on Windows.
REM
REM  Prerequisites:
REM    - Godot 4.7.2 (C# / .NET version) installed
REM    - .NET 9 SDK installed
REM    - Git installed
REM
REM  Usage: build_windows.bat [godot_path]
REM    godot_path: full path to Godot exe (optional, auto-detected)
REM ============================================================

setlocal enabledelayedexpansion

echo ============================================================
echo  Arena FC — Windows Build
echo ============================================================
echo.

REM --- Find Godot ---
set GODOT=
if not "%~1"=="" (
    set GODOT=%~1
) else (
    REM Try common install locations
    for %%P in (
        "%ProgramFiles%\Godot\Godot_v4.7.2-stable_mono_win64\Godot_v4.7.2-stable_mono_win64.exe"
        "%ProgramFiles(x86)%\Godot\Godot_v4.7.2-stable_mono_win64\Godot_v4.7.2-stable_mono_win64.exe"
        "%LOCALAPPDATA%\Godot\Godot_v4.7.2-stable_mono_win64\Godot_v4.7.2-stable_mono_win64.exe"
    ) do (
        if exist %%P set GODOT=%%P
    )
    REM Check PATH
    if "%GODOT%"=="" (
        where godot >nul 2>&1 && set GODOT=godot
    )
)

if "%GODOT%"=="" (
    echo [ERROR] Godot 4.7.2 not found.
    echo         Install from: https://godotengine.org/download
    echo         Or pass the path: build_windows.bat "C:\path\to\Godot.exe"
    exit /b 1
)
echo [OK] Godot: %GODOT%

REM --- Check .NET ---
where dotnet >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERROR] .NET SDK not found.
    echo         Install from: https://dotnet.microsoft.com/download/dotnet/9.0
    exit /b 1
)
for /f "tokens=*" %%V in ('dotnet --version') do echo [OK] .NET SDK: %%V

REM --- Navigate to project ---
cd /d "%~dp0"
echo [OK] Project: %CD%
echo.

REM --- Step 1: Pull latest ---
echo [1/5] Pulling latest changes...
git pull origin main
if %ERRORLEVEL% neq 0 (
    echo [WARN] git pull failed — continuing with local changes
)
echo.

REM --- Step 2: Build .NET ---
echo [2/5] Building .NET solution...
dotnet build ArenaFC.sln -c Release --nologo -v q
if %ERRORLEVEL% neq 0 (
    echo [ERROR] .NET build failed
    exit /b 1
)
echo [OK] .NET build succeeded
echo.

REM --- Step 3: Run .NET tests ---
echo [3/5] Running .NET tests...
dotnet run --project Tests\MatchCoreTests.csproj -c Release --no-build
if %ERRORLEVEL% neq 0 (
    echo [WARN] Some tests failed — check output above
) else (
    echo [OK] All .NET tests passed
)
echo.

REM --- Step 4: Run Python tests ---
echo [4/5] Running Python tests...
where python >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [WARN] Python not found — skipping Python tests
    echo        Install from: https://python.org/downloads/
) else (
    python Tools\test_soccer_forge.py
    python Tools\test_pads.py
)
echo.

REM --- Step 5: Open Godot editor ---
echo [5/5] Opening Godot editor...
echo       Press F5 in Godot to run the game.
echo       Or run: "%GODOT%" --path "%CD%"
echo.
"%GODOT%" --path "%CD%"

endlocal

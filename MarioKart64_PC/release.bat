@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo ============================================================================
echo   MARIO KART 64 PC - N64 EDITION (EASYSMX USB CONTROLLER READY)
echo   One-Click Release Build ^& Launch System
echo ============================================================================
echo.

if not exist "release" mkdir "release"

set "CSC_EXE="
if exist "%SystemRoot%\Microsoft.NET\Framework64\v4.0.30319\csc.exe" (
    set "CSC_EXE=%SystemRoot%\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
)
if "!CSC_EXE!"=="" (
    if exist "%SystemRoot%\Microsoft.NET\Framework\v4.0.30319\csc.exe" (
        set "CSC_EXE=%SystemRoot%\Microsoft.NET\Framework\v4.0.30319\csc.exe"
    )
)
if "!CSC_EXE!"=="" (
    for /f "delims=" %%I in ('where csc.exe 2^>nul') do (
        if "!CSC_EXE!"=="" set "CSC_EXE=%%I"
    )
)

if not "!CSC_EXE!"=="" goto :build_with_csc

:: Fallback to modern .NET SDK if Framework csc.exe was not found
where dotnet >nul 2>nul
if %ERRORLEVEL% EQU 0 goto :build_with_dotnet

echo [ERROR] Could not locate Windows C# compiler (csc.exe) or .NET SDK (dotnet).
echo Please ensure .NET Framework 4.x (pre-installed on Windows 10/11) is enabled.
pause
exit /b 1

:build_with_csc
echo [1/3] Compiling all Mario Kart 64 source modules with:
echo       "!CSC_EXE!"
echo.

set "ICON_ARG="
if exist "assets\mk64.ico" set "ICON_ARG=/win32icon:assets\mk64.ico"

"!CSC_EXE!" /nologo /optimize+ /target:winexe /out:"release\MarioKart64.exe" !ICON_ARG! ^
    /r:System.dll ^
    /r:System.Core.dll ^
    /r:System.Drawing.dll ^
    /r:System.Windows.Forms.dll ^
    "src\*.cs" ^
    "src\Core\*.cs" ^
    "src\Input\*.cs" ^
    "src\Audio\*.cs" ^
    "src\Entities\*.cs" ^
    "src\Tracks\*.cs" ^
    "src\Rendering\*.cs" ^
    "src\Game\*.cs"

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Compilation failed with exit code %ERRORLEVEL%.
    pause
    exit /b %ERRORLEVEL%
)
goto :post_build

:build_with_dotnet
echo [1/3] Compiling Mario Kart 64 with .NET SDK...
dotnet build "MarioKart64.csproj" -c Release -o "release"
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] dotnet build failed with exit code %ERRORLEVEL%.
    pause
    exit /b %ERRORLEVEL%
)

:post_build
echo [2/3] Staging release assets ^& EasySMX USB controller configuration...
if exist "assets\mk64.ico" copy /y "assets\mk64.ico" "release\mk64.ico" >nul
if not exist "release\easysmx_config.ini" (
    if exist "easysmx_config.ini" copy /y "easysmx_config.ini" "release\easysmx_config.ini" >nul
)
if exist "README.md" copy /y "README.md" "release\README.md" >nul

echo [3/3] Verifying executable, 16 GP tracks, 4 Battle arenas ^& EasySMX input...
"release\MarioKart64.exe" --verify
if %ERRORLEVEL% NEQ 0 (
    echo [WARNING] Verification returned non-zero status, continuing...
)

echo.
echo ============================================================================
echo   [SUCCESS] Built standalone executable: release\MarioKart64.exe
echo ============================================================================

if /I "%~1"=="--build-only" exit /b 0
if /I "%~1"=="/norun" exit /b 0

echo Launching Mario Kart 64 PC...
start "" "release\MarioKart64.exe"
exit /b 0

@echo off
REM Arena FC - start the Play With Friends server (Windows).
REM Friends then enter ws://YOUR-IP:7777 in the game -> PLAY WITH FRIENDS.
setlocal
cd /d "%~dp0"
set PORT=%1
if "%PORT%"=="" set PORT=7777
where dotnet >nul 2>&1
if errorlevel 1 (
  echo No .NET 9 SDK found. Install from https://dotnet.microsoft.com/download
  exit /b 1
)
echo Arena FC friend server on ws://0.0.0.0:%PORT%
echo Status page: http://127.0.0.1:%PORT%/   Health: http://127.0.0.1:%PORT%/health
dotnet run --project Server\ArenaFC.Server.csproj -c Release -- --port %PORT% --bind 0.0.0.0 --team-size 5 --seed 2026 --verbose

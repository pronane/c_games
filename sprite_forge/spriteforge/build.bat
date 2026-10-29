@echo off
rem Compile the SpriteForge example with MSYS2 UCRT64 gcc + raylib.
rem   pacman -S mingw-w64-ucrt-x86_64-gcc mingw-w64-ucrt-x86_64-raylib
rem Run from cmd/PowerShell/VS Code terminal.  MSYS2 not in C:\msys64? set MSYS2=D:\msys64 first.
setlocal
cd /d "%~dp0"
if "%MSYS2%"=="" set "MSYS2=C:\msys64"
where gcc >nul 2>nul || set "PATH=%MSYS2%\ucrt64\bin;%PATH%"
where gcc >nul 2>nul || (echo gcc not found - install MSYS2 UCRT64 gcc, see README.md & exit /b 1)
if not exist bin mkdir bin
echo gcc -std=c99 -O2 -Wall example\main.c -Iinclude -o bin\example.exe -lraylib -lopengl32 -lgdi32 -lwinmm
gcc -std=c99 -O2 -Wall example\main.c -Iinclude -o bin\example.exe -lraylib -lopengl32 -lgdi32 -lwinmm
if errorlevel 1 (echo BUILD FAILED & exit /b 1)
echo Built bin\example.exe   -  run:  bin\example.exe assets\dec assets\flame

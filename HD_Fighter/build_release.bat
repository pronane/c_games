@echo off
cd /d "%~dp0"
echo ========================================
echo  HD Fighter 2 - Release Build (CLASSIC + HD via F2)
echo  Procedural V2 + AI HD assets included
echo ========================================
echo.
python --version >nul 2>&1
if %errorlevel% neq 0 ( echo ERROR: Python not on PATH. & pause & exit /b 1 )
echo [1/4] Installing dependencies...
pip install -r requirements.txt
if %errorlevel% neq 0 ( echo ERROR: pip failed. & pause & exit /b 1 )
echo [2/4] Cleaning...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist "__pycache__" rmdir /s /q "__pycache__"
echo [3/4] Building exe...
python -m PyInstaller --noconsole --onedir --name "HD_Fighter_2" --add-data="assets;assets" --add-data="assets_hd;assets_hd" --hidden-import pygame game.py
if %errorlevel% neq 0 ( echo ERROR: build failed. & pause & exit /b 1 )
echo [4/4] Copying assets...
if exist "dist\HD_Fighter_2\assets" rmdir /s /q "dist\HD_Fighter_2\assets"
if exist "dist\HD_Fighter_2\assets_hd" rmdir /s /q "dist\HD_Fighter_2\assets_hd"
xcopy /E /I /Y "assets" "dist\HD_Fighter_2\assets" >nul
xcopy /E /I /Y "assets_hd" "dist\HD_Fighter_2\assets_hd" >nul
echo.
echo ========================================
echo  BUILD COMPLETE — dist\HD_Fighter_2\HD_Fighter_2.exe
echo  Press F2 in-game to toggle CLASSIC <-> HD
echo  Zip dist\HD_Fighter_2 to share
echo ========================================
pause

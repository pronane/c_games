@echo off
echo Building HD Fighter 2 for Windows/Linux/macOS...
pip install pygame pyinstaller -q
pyinstaller --noconfirm --onedir --windowed --name "HD_Fighter_2" --add-data "assets;assets" --add-data "assets_hd;assets_hd" --hidden-import pygame game.py
echo Build complete: dist/HD_Fighter_2/HD_Fighter_2.exe (Windows) or dist/HD_Fighter_2/HD_Fighter_2 (Linux/macOS)
pause

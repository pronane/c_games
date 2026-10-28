@echo off
cd /d "%~dp0"
python Tools\build.py --check
pause

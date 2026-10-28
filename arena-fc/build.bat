@echo off
REM Arena FC - build every device package. Requires Python 3.9+ on PATH.
cd /d "%~dp0"
python Tools\build.py %*
pause

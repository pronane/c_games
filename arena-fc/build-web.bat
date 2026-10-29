@echo off
REM Arena FC - build web export only (for Option B deployment)
REM
REM Exports the Godot WASM web build to build/web/
REM Then serves it locally with python Tools/build.py --serve
REM
cd /d "%~dp0"
python Tools\build.py --platforms web %*
pause

@echo off
REM Arena FC - build and run locally
REM
REM Builds web + windows + linux + macos, then launches the Windows build.
REM
REM Examples:
REM   run.bat                    (build + run)
REM   run.bat --platforms web    (web only, then serve)
REM
cd /d "%~dp0"
python Tools\build.py --platforms web,windows,linux,macos --run %*
pause

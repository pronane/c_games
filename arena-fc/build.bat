@echo off
REM Arena FC - build device packages. Requires Python 3.9+ on PATH.
REM
REM Default platforms: web windows linux macos
REM   (Android needs --android-sdk + JAVA_HOME + .NET 9 SDK; iOS needs macOS + Xcode)
REM
REM Examples:
REM   build.bat                          (web + windows + linux + macos)
REM   build.bat --platforms web          (web only, fastest)
REM   build.bat --platforms all          (everything, incl. Android/iOS)
REM   build.bat --platforms web,windows  (web + windows only)
REM
REM Use --serve after building to play the web build locally:
REM   python Tools/build.py --serve
REM
cd /d "%~dp0"
python Tools\build.py --platforms web,windows,linux,macos %*
pause

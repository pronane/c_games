@echo off
rem kept for v4 users: the real work is done by tools\setup_pose.py (no curl, fetches Python 3.12 with uv if needed)
cd /d "%~dp0\.."
if exist .venv\Scripts\python.exe (
  .venv\Scripts\python.exe tools\setup_pose.py %*
) else (
  where py >nul 2>nul && (py -3 tools\setup_pose.py %*) || (python tools\setup_pose.py %*)
)
exit /b %errorlevel%

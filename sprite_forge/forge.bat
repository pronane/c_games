@echo off
rem Sprite Forge Studio CLI wrapper.  Uses .venv\ if setup.bat made it.  Examples:
rem   forge.bat doctor
rem   forge.bat build --spec examples_char.txt --preset fighter14
rem   forge.bat build --photo front.png --back back.png --name qanna --preset kart12
rem   forge.bat gui
setlocal
set "HERE=%~dp0"
if exist "%HERE%.venv\Scripts\python.exe" (
  "%HERE%.venv\Scripts\python.exe" "%HERE%forge.py" %*
  goto done
)
where py >nul 2>nul
if errorlevel 1 (
  python "%HERE%forge.py" %*
) else (
  py -3 "%HERE%forge.py" %*
)
:done
endlocal & exit /b %errorlevel%

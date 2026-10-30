@echo off
rem Sprite Forge Studio - build + verify every demo (Windows 10/11).  Runs setup.bat first if .venv is missing.
rem   1. setup/doctor   2. demo builds (+ FBX check, SNES, profiles, video, scan, mocap)   3. raylib C example (MSYS2)
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" call setup.bat --no-pose
if not exist ".venv\Scripts\python.exe" goto :err
set "PY=.venv\Scripts\python.exe"
echo [1/3] doctor
%PY% forge.py doctor || goto :err
echo [2/3] Demo build (SPEC example, fighter14 set) -^> out\rua_keeper  (model.fbx by the built-in writer)
%PY% forge.py build --spec examples_char.txt --preset fighter14 --out out || goto :err
%PY% tools\verify_output.py out\rua_keeper || goto :err
echo [2a/3] FBX check with independent readers (assimp / FBX2glTF / Blender when installed)
%PY% tools\verify_fbx.py out\rua_keeper\model.glb out\rua_keeper\model.fbx --json out\rua_keeper\fbx_check.json >nul || goto :err
echo FBX check PASS - out\rua_keeper\fbx_check.json
echo [2b/3] Same character for the SNES preset -^> out_snes\rua_keeper\console
%PY% forge.py build --spec examples_char.txt --preset fighter14 --console snes --no-fbx --out out_snes || goto :err
%PY% tools\verify_console.py out_snes\rua_keeper || goto :err
echo [2c/3] Output profiles: validate all, then a kart racer (TurboTumble64-style) from the text spec, 8 views
%PY% forge.py profile validate || goto :err
%PY% forge.py build --spec examples_char.txt --profile kart_racer --no-fbx --out out_profiles || goto :err
%PY% forge.py build --spec examples_char.txt --profile topdown8dir --no-fbx --out out_profiles_topdown || goto :err
echo [2d/3] VIDEO: the bundled test clips (rendered mannequin) -^> sprites + SNES  -^> out_video\vidhero
%PY% forge.py video --clip walk:8=examples_video\walk_static.mp4 --clip run:8=examples_video\run_tracking.mp4 --clip jump:12=examples_video\jump_handheld.mp4 --clip punch:10=examples_video\punch_green.mp4 --name vidhero --out out_video --consoles snes --no-fbx || goto :err
echo [2e/3] SCAN: orbit clip -^> pycolmap SfM -^> mesh -^> console LODs (project only if pycolmap is missing)
%PY% -c "import pycolmap" >nul 2>nul
if errorlevel 1 (
  %PY% forge.py scan --video examples_video\orbit_mannequin.mp4 --frames 72 --name orbit_demo --out out_scan || goto :err
) else (
  %PY% forge.py scan --video examples_video\orbit_mannequin.mp4 --frames 72 --run --height 1.75 --name orbit_demo --out out_scan || goto :err
)
echo [2f/3] MOCAP (only if tools\setup_pose.py / setup.bat made venv_pose)
if exist venv_pose\Scripts\python.exe %PY% forge.py mocap --clip walk:8=examples_video\walk_static.mp4 --clip jump:12=examples_video\jump_handheld.mp4 --name mocap_demo --out out_mocap
echo [3/3] raylib C example (needs MSYS2 UCRT64 gcc + raylib: pacman -S mingw-w64-ucrt-x86_64-raylib)
set "PATH=C:\msys64\ucrt64\bin;%PATH%"
pushd spriteforge
call build.bat
if errorlevel 1 echo C example not built - optional, needs MSYS2 UCRT64 gcc + raylib
popd
echo.
echo Done.  Try:  spriteforge\bin\example.exe out\rua_keeper
echo        or:   run_studio.bat     (Help tab / Help menu explains everything)
echo        or:   forge.bat help quickstart
exit /b 0
:err
echo Build failed - see messages above.
pause
exit /b 1

@echo off
rem ---------------------------------------------------------------
rem  Facility 64 - convert FBX models to GLB for assets\models\
rem    tools\convert_fbx_to_glb.bat model.fbx
rem    tools\convert_fbx_to_glb.bat C:\path\to\folder
rem  Uses Blender if found (keeps every animation take as a named clip),
rem  otherwise the Assimp tool (MSYS2: pacman -S mingw-w64-ucrt-x86_64-assimp).
rem ---------------------------------------------------------------
setlocal enabledelayedexpansion
if "%~1"=="" ( echo usage: %~nx0 file.fbx ^| folder & exit /b 1 )
set "BL=%BLENDER%"
if "%BL%"=="" (
  for /d %%V in ("C:\Program Files\Blender Foundation\Blender*") do if exist "%%V\blender.exe" set "BL=%%V\blender.exe"
)
if "%BL%"=="" ( where blender >nul 2>nul && set "BL=blender" )
set "PATH=C:\msys64\ucrt64\bin;%PATH%"
if exist "%~1\" (
  for %%F in ("%~1\*.fbx") do call :one "%%~fF"
) else (
  call :one "%~f1"
)
echo Copy the .glb files into assets\models\ and edit models.cfg (F3 reloads in game).
exit /b 0

:one
set "OUT=%~dpn1.glb"
if not "%BL%"=="" (
  "%BL%" -b -P "%~dp0blender_fbx_to_glb.py" -- "%~1" "%OUT%"
) else (
  where assimp >nul 2>nul || ( echo Need Blender or assimp to convert %~1 & exit /b 1 )
  assimp export "%~1" "%OUT%" -fglb2
)
exit /b 0

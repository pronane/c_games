@echo off
setlocal
set "ROOT=%~dp0"
set "APK=%ROOT%AudioCapture-Mobile-debug.apk"
if not exist "%APK%" (echo APK not found. Run build_android_apk.bat first.& exit /b 1)
if not defined ANDROID_HOME if defined LOCALAPPDATA if exist "%LOCALAPPDATA%\Android\Sdk" set "ANDROID_HOME=%LOCALAPPDATA%\Android\Sdk"
if not defined ANDROID_HOME if defined ANDROID_SDK_ROOT set "ANDROID_HOME=%ANDROID_SDK_ROOT%"
set "ADB=adb"
where adb >nul 2>nul || if defined ANDROID_HOME if exist "%ANDROID_HOME%\platform-tools\adb.exe" set "ADB=%ANDROID_HOME%\platform-tools\adb.exe"
if "%ADB%"=="adb" (where adb >nul 2>nul || goto PHONE_STEPS)
"%ADB%" get-state >nul 2>nul
if errorlevel 1 goto PHONE_STEPS
"%ADB%" install -r "%APK%"
if errorlevel 1 exit /b 1
echo Installed on the connected Android device.
exit /b 0
:PHONE_STEPS
echo No adb device found. To install manually:
echo 1. Copy this file to the Android phone.
echo 2. Open it in Files/Downloads and allow Install unknown apps if prompted.
echo 3. Tap Install. This is a debug-signed sideload APK, not a Play Store package.
exit /b 0

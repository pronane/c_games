@echo off
setlocal
set "ROOT=%~dp0"
set "APP=%ROOT%android-app"

if not defined JAVA_HOME (
  if defined ANDROID_STUDIO_JBR if exist "%ANDROID_STUDIO_JBR%\bin\java.exe" set "JAVA_HOME=%ANDROID_STUDIO_JBR%"
  if not defined JAVA_HOME if exist "%ProgramFiles%\Android\Android Studio\jbr\bin\java.exe" set "JAVA_HOME=%ProgramFiles%\Android\Android Studio\jbr"
)
if defined JAVA_HOME set "PATH=%JAVA_HOME%\bin;%PATH%"
where java >nul 2>nul || (echo ERROR: Install JDK 17 or Android Studio (JBR 17+) and set JAVA_HOME.& exit /b 1)
java -version 2>&1 | findstr /C:"17." >nul || (echo ERROR: Android build requires Java 17. Set JAVA_HOME to a JDK 17 installation.& exit /b 1)
if not defined ANDROID_HOME if defined LOCALAPPDATA if exist "%LOCALAPPDATA%\Android\Sdk" set "ANDROID_HOME=%LOCALAPPDATA%\Android\Sdk"
if not defined ANDROID_HOME if defined ANDROID_SDK_ROOT set "ANDROID_HOME=%ANDROID_SDK_ROOT%"
if not defined ANDROID_HOME if not exist "%APP%\local.properties" (echo ERROR: Install Android Studio and Android SDK Platform 35, or set ANDROID_HOME.& exit /b 1)

echo Building Audio Capture Studio APK with Java 17...
pushd "%APP%"
call gradlew.bat assembleDebug
if errorlevel 1 (popd & exit /b 1)
popd
copy /Y "%APP%\app\build\outputs\apk\debug\app-debug.apk" "%ROOT%AudioCapture-Mobile-debug.apk" >nul
if errorlevel 1 exit /b 1
echo.
echo Build complete: %ROOT%AudioCapture-Mobile-debug.apk
endlocal

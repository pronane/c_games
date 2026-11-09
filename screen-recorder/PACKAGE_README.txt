COMPLETE AUDIO CAPTURE + SCREEN RECORDER BUNDLE

Contents:
- AudioCapture/: Audio Capture Studio desktop source, tests, Windows installer build files, Android source, and the debug-signed Android APK.
- screen-recorder/: the independent reusable Python screen-recorder module and its tests.

Windows installer:
Run AudioCapture/build_windows.bat on Windows with Python 3 installed. Install Inno Setup 6 to have the script create dist/AudioCaptureStudio-Setup.exe. The installer itself is not prebuilt in this Linux-produced archive.

Android APK:
Install AudioCapture/AudioCapture-Mobile-debug.apk on Android 10 or later for testing/sideloading. Android will prompt for playback capture. Some source apps disallow capture; this app does not bypass those restrictions.

Android source is in AudioCapture/android-app/. Build with Android Studio or ./gradlew assembleDebug (Java 17 and Android SDK Platform 35 required).

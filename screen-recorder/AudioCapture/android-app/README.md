# Audio Capture Studio for Android (MVP)

This is a small native Android companion app that records **permitted playback audio from other apps** to stereo 48 kHz, 16-bit WAV files. It does not record microphone input. The Android platform requires the user to approve a MediaProjection capture prompt for each capture session. The source app must allow playback capture; protected audio and apps that opt out can be silent or unavailable. See [Android's playback-capture requirements](https://developer.android.com/guide/topics/media/playback-capture).

The app saves recordings to `Music/Audio Capture` and provides built-in playback. Minimum Android version is Android 10 (API 29). This initial mobile version does not yet include the desktop editor, playlists, or URL/browser workflow.

## Install the built APK

Use `../AudioCapture-Mobile-debug.apk` (debug-signed, for testing/sideloading). On the device, allow installation from the file manager/browser used to open the APK, then install. The package may require Android's confirmation screen. This debug APK is not a Play Store release.

## Build from source

Open this folder in Android Studio, or run the Gradle wrapper:

```sh
./gradlew assembleDebug
```

Output: `app/build/outputs/apk/debug/app-debug.apk`. The first source build needs Android SDK Platform 35, Build Tools, Java 17, and an internet connection for Gradle dependencies. The wrapper downloads Gradle once if it is not already cached.

To install to a connected, developer-enabled device with `adb`:

```sh
./gradlew installDebug
```

## Privacy and behavior

- Audio capture begins only after an in-app action and Android's system capture approval.
- The app asks Android for the `RECORD_AUDIO` permission because Android requires it for playback capture. Captured samples come from permitted app playback, not the microphone.
- Capturing other apps is best-effort and follows Android/source-app policy; this does not bypass DRM or app restrictions.
- Files are local on the device; the app does not upload them.

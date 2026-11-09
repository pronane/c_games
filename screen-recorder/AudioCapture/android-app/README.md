# Audio Capture Studio for Android (MVP)

Native Android companion app, version 1.1.0. It records **permitted playback audio from other apps** to stereo 48 kHz, 16-bit WAV files; it does not record microphone input. Android requires a MediaProjection capture approval each session. The source app must allow playback capture; protected audio and apps that opt out may be silent or unavailable. See [Android's playback-capture requirements](https://developer.android.com/guide/topics/media/playback-capture).

Recordings are saved to `Music/Audio Capture` and can be played in-app. WAV recordings now have a non-destructive editor with waveform preview, start/end selection sliders, trim-to-selection, remove-selection, repeated cuts, undo/redo, and save-as-copy. A review-only loudness-change scanner flags possible breaks; it is not ad recognition and never cuts automatically. Minimum Android version is Android 10 (API 29).

The Android companion now has a session-only multiline URL list that opens pages in the user's normal browser; it does not store URL lists, cookies, or browser sessions. Capture is a single combined WAV, not per-URL files. Optional silence monitoring has an editable grace period, quiet duration, and dBFS threshold; it reports through an Android notification that the user taps to open the next URL (Android background-launch rules prevent reliable silent browser launching). Detected quiet gaps at auto-next transitions are removed from the final combined WAV. Android does not yet support separate URL files, lossless FLAC/MP3/AAC export, exact per-process capture, or automatic ad recognition. Android's playback capture remains subject to user approval and source-app policy.

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

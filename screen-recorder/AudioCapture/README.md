

### Editing and URL privacy

The editor supports waveform drag-selection plus dedicated start/end sliders for precise range selection. Use **Trim to selection** to keep only the chosen range, or **Remove selection** to cut it out; repeat for multiple middle cuts and use Undo/Redo as needed. **Find possible breaks** scans for abrupt loudness changes and selects a short region around each candidate for review; click again to cycle candidates, then preview and choose whether to cut. This is only a loudness heuristic, not ad recognition, and quiet programme audio can be flagged. The original recording is preserved; saving exports an edited copy.

URL lists remain in memory for the current app session unless you explicitly save a named playlist. Persistent playlists now discard all URL query strings and fragments because providers can place credentials under arbitrary parameter names; this may remove page identifiers required by some URLs. URL credentials in the authority are rejected. AudioCapture does not read, copy, or store browser cookies/session databases; normal browser sign-in remains managed by the browser. The browser may persist its own sign-in according to its own settings, which is outside AudioCapture's storage. The app cannot guarantee that arbitrary tokens embedded in URL paths or page content are absent, and should not be treated as a browser privacy boundary.

Automatic ad removal is not enabled: reliable ad identification is not possible from system audio alone. Review suspected ad sections in the waveform editor before cutting to avoid removing quiet programme audio.


Android companion build (v1.1.0): supports local playback capture, in-app playback, an editable WAV range editor with undo/redo, review-only loudness-change hints, and session-only browser URL lists with user-confirmed silence-triggered next-URL notifications. Android currently records a combined WAV; separate URL files and alternate export formats remain unsupported. Android playback capture requires user approval and source-app permission.

### Android quick install and rebuild

The bundle includes a debug APK at `AudioCapture-Mobile-debug.apk` and short instructions in `ANDROID-QUICK-START.txt`. For a connected USB-debugging device, run `install_android_apk.bat` on Windows or `./install_android_apk.sh` on macOS/Linux; without adb, copy the APK to the phone and install from Files. To rebuild, run `build_android_apk.bat` or `./build_android_apk.sh`. Builds require JDK 17, Android SDK Platform 35, and Build Tools. The build script copies the output APK to the bundle root.

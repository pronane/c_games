#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
APK="$ROOT/AudioCapture-Mobile-debug.apk"
[[ -f "$APK" ]] || { echo "APK not found. Run build_android_apk.sh first." >&2; exit 1; }
ADB="$(command -v adb || true)"
if [[ -z "$ADB" && -n "${ANDROID_HOME:-}" && -x "$ANDROID_HOME/platform-tools/adb" ]]; then ADB="$ANDROID_HOME/platform-tools/adb"; fi
if [[ -n "$ADB" ]] && "$ADB" get-state >/dev/null 2>&1; then
  "$ADB" install -r "$APK"
  echo "Installed on the connected Android device."
else
  echo "No adb device found. Copy this APK to your phone, open it in Files/Downloads,"
  echo "allow installation from that source if prompted, then tap Install."
  echo "This is a debug-signed sideload build, not a Play Store release."
fi

#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
APP="$ROOT/android-app"

if [[ -z "${JAVA_HOME:-}" ]]; then
  for candidate in "${ANDROID_STUDIO_JBR:-}" "$HOME/.jdks/jbr" "$HOME/android-studio/jbr" "/opt/android-studio/jbr"; do
    [[ -n "$candidate" ]] || continue
    if [[ -x "$candidate/bin/java" ]]; then export JAVA_HOME="$candidate"; break; fi
  done
fi
if [[ -n "${JAVA_HOME:-}" ]]; then export PATH="$JAVA_HOME/bin:$PATH"; fi
if ! command -v java >/dev/null 2>&1; then echo "ERROR: Install JDK 17 or Android Studio with JBR 17+, then set JAVA_HOME." >&2; exit 1; fi
JAVA_VERSION="$(java -version 2>&1 | head -n 1)"
if [[ "$JAVA_VERSION" != *'version "17'* ]]; then echo "ERROR: Android build requires Java 17; found: $JAVA_VERSION. Set JAVA_HOME to JDK 17." >&2; exit 1; fi
if [[ -z "${ANDROID_HOME:-}" ]]; then
  if [[ -n "${ANDROID_SDK_ROOT:-}" ]]; then export ANDROID_HOME="$ANDROID_SDK_ROOT"
  elif [[ -d "$HOME/Android/Sdk" ]]; then export ANDROID_HOME="$HOME/Android/Sdk"
  elif [[ -d "$HOME/Library/Android/sdk" ]]; then export ANDROID_HOME="$HOME/Library/Android/sdk"
  elif [[ ! -f "$APP/local.properties" ]]; then echo "ERROR: Install Android Studio + Android SDK Platform 35, then set ANDROID_HOME." >&2; exit 1; fi
fi
( cd "$APP" && bash ./gradlew assembleDebug )
cp "$APP/app/build/outputs/apk/debug/app-debug.apk" "$ROOT/AudioCapture-Mobile-debug.apk"
echo "Build complete: $ROOT/AudioCapture-Mobile-debug.apk"

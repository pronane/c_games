"""Quick diagnostics: `python tests/selftest.py` (or the Tools button).

Prints the backend, every device the app can see, then does a 2 second test
capture so you can confirm audio is really coming through.
"""

import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from audiocapture.audio import AudioEngine, BackendError, describe_channels
from audiocapture.recorder import AudioFile, Recorder


def main() -> int:
    print("=" * 66)
    print(" Audio Capture Studio - self test")
    print("=" * 66)
    print(f" Python       : {sys.version.split()[0]} on {sys.platform}")
    engine = AudioEngine()
    print(f" Backend      : {engine.backend_name}")
    if not engine.available:
        try:
            engine.sc
        except BackendError as exc:
            print("\n [X] " + str(exc))
        return 2

    print("\n System audio (loopback) devices")
    try:
        loopbacks = engine.list_loopbacks()
    except BackendError as exc:
        print("  [X] " + str(exc))
        loopbacks = []
    if not loopbacks:
        print("  (none found)")
    for dev in loopbacks:
        print(f"  * {dev.name!r}  [{describe_channels(dev.channels)}]"
              f"{'  <- default' if dev.is_default else ''}"
              f"{f'  device rate {dev.sample_rate} Hz' if dev.sample_rate else ''}")

    print("\n Microphone devices")
    try:
        inputs = engine.list_inputs()
    except BackendError as exc:
        print("  [X] " + str(exc))
        inputs = []
    for dev in inputs:
        print(f"  * {dev.name!r}  [{describe_channels(dev.channels)}]"
              f"{'  <- default' if dev.is_default else ''}")

    target = engine.default_loopback(loopbacks) or (loopbacks[0] if loopbacks else None)
    if target is None:
        print("\n Nothing to record from - connect an output device first.")
        return 3

    rate = target.sample_rate or 48000
    channels = min(2, target.channels)
    print(f"\n Recording 2 s from {target.name!r} at {rate} Hz, "
          f"{describe_channels(channels)}...")
    print(" (play something on the computer now)")
    path = os.path.join(tempfile.gettempdir(), "audiocapture_selftest.wav")
    rec = Recorder(engine.capture_source(target), path, rate, channels, "WAV")
    rec.start()
    for _ in range(20):
        time.sleep(0.1)
        rms, peak = rec.level()
        bars = int(min(1.0, rms * 3) * 40)
        print("\r  level [" + "#" * bars + " " * (40 - bars) + "]", end="", flush=True)
    print()
    info = rec.stop()
    audio = AudioFile(info.path)
    print(f"\n Saved  : {info.path}")
    print(f" Length : {info.duration:.2f} s, {info.frames} frames")
    print(f" Peak   : {info.peak_db:.1f} dBFS")
    if audio.data is not None:
        silent = float(np.max(np.abs(audio.data)))
        if silent < 1e-4:
            print("\n [!] The capture is silent. If audio was playing, check the")
            print("     device selection - on Windows apps running as admin also")
            print("     bypass the loopback mix.")
        else:
            print("\n [OK] Signal detected - the app is recording correctly.")
        return 0
    print("\n [X] Could not read the file back:", audio.error)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

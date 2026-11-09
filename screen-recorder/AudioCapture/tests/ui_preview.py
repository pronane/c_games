"""UI screenshot harness with a fake audio backend (no audio hardware needed).

Run with a display, e.g.:  DISPLAY=:99 python3 tests/ui_preview.py
It starts the real App, injects a fake loopback device, records ~2.5 s,
stops, then screenshots the result.
"""
import os
import sys
import subprocess
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import audiocapture.ui as ui
from audiocapture.audio import Device


class FakeLoopback:
    def __init__(self, samplerate=48000, channels=2):
        self.samplerate, self.channels = samplerate, channels
        self.phase = 0.0

    def recorder(self, samplerate, channels=None, blocksize=None):
        return _FakeRecorder(self, samplerate, channels)


class _FakeRecorder:
    def __init__(self, dev, samplerate, channels):
        self.dev, self.sr, self.ch = dev, samplerate, channels

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def record(self, numframes, **_kw):
        time.sleep(numframes / float(self.sr))
        t = np.arange(numframes) / self.sr + self.dev.phase
        self.dev.phase += numframes / self.sr
        # music-ish signal with an envelope so the waveform looks alive
        env = 0.25 + 0.65 * np.abs(np.sin(2 * np.pi * 0.7 * t))
        sig = env * (0.6 * np.sin(2 * np.pi * 220 * t) +
                     0.3 * np.sin(2 * np.pi * 660 * t) +
                     0.1 * np.sin(2 * np.pi * 1760 * t))
        data = np.stack([sig, sig * 0.8], axis=1)
        return data.astype(np.float32)


def fake_devices():
    return [Device(id="fake-speakers", name="Speakers (Realtek(R) Audio)",
                   kind="loopback", channels=2, sample_rate=48000,
                   is_default=True, info="System output (WASAPI loopback)",
                   raw=FakeLoopback())]


def main():
    shot_dir = os.environ.get("SHOT_DIR", "/tmp/shots")
    os.makedirs(shot_dir, exist_ok=True)
    ui.App.refresh_devices = lambda self, select_saved=True: _patch_refresh(self)
    ui.App._initial_load = lambda self: _patch_initial(self)

    app = ui.App()
    app.update()
    app.refresh_library()

    def shot(name):
        app.update_idletasks()
        app.update()
        subprocess.run(["import", "-window", "root", f"{shot_dir}/{name}.png"],
                       check=False)

    def sequence():
        shot("01_idle")
        app.start_recording()
        app.after(2600, after_recording)

    def after_recording():
        shot("02_recording")
        app.stop_recording()
        app.after(1200, after_stop)

    def after_stop():
        shot("03_saved")
        if app.file_audio is not None:
            app.start_play()
        app.after(900, lambda: (shot("04_playing"), app.after(400, finish)))

    def finish():
        app.on_close()

    app.after(700, sequence)
    app.mainloop()


def _patch_refresh(self):
    self.devices = fake_devices()
    self.device_menu.configure(values=[d.label for d in self.devices])
    self.device_menu.set(self.devices[0].label)
    self._current_device = self.devices[0]
    self._describe_device(self.devices[0])
    self._update_quality_widgets()
    self._set_status("Ready", ui.MUTED)


def _patch_initial(self):
    self._apply_settings_to_widgets()
    _patch_refresh(self)
    self._update_name_preview()
    self.settings["output_dir"] = os.environ.get("OUT_DIR", "/tmp/ui_recordings")
    self.dir_label.configure(text=self.settings["output_dir"])


if __name__ == "__main__":
    main()

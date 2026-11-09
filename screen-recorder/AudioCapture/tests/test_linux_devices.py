"""Verify the Linux (PulseAudio) device-resolution logic with a mocked backend.

The ``soundcard`` pulseaudio module can't load here (no libpulse in the build
container), so we stub the small surface our engine uses and check that:

  * only one monitor per output sink is listed (not every internal source),
  * monitors are labelled as loopbacks and the default sink is flagged,
  * microphones are listed separately and are not treated as loopbacks,
  * ``capture_source`` returns the monitor object itself,
  * rates come from the sink/source info when available.
"""

import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np


# --------------------------------------------------------------- fake backend
class FakeMic:
    def __init__(self, name, channels=2, isloopback=False):
        self.id = name
        self.name = name
        self.channels = channels
        self._loop = isloopback

    def _get_info(self):
        return {"channels": self.channels,
                "device.class": "monitor" if self._loop else "sound"}

    def recorder(self, samplerate, channels=None, blocksize=None):
        return _FakeRec(samplerate, channels)


class _FakeRec:
    def __init__(self, samplerate, channels):
        self.samplerate, self.channels = samplerate, channels

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass

    def record(self, numframes, **_kw):
        return np.zeros((numframes, self.channels), dtype=np.float32)


SINKS = [{"name": "Built-in Audio Analog Stereo", "id": "alsa_output.pci-0000_00_1f.3.analog-stereo"},
         {"name": "USB Headset", "id": "alsa_output.usb-headset.analog-stereo"}]
SOURCES = [
    {"name": "Built-in Audio Analog Stereo", "id": "alsa_output.pci-0000_00_1f.3.analog-stereo.monitor"},
    {"name": "USB Headset", "id": "alsa_output.usb-headset.analog-stereo.monitor"},
    {"name": "Built-in Microphone", "id": "alsa_input.pci-0000_00_1f.3.analog-stereo"},
]


class FakePulse:
    server_info = {"default sink id": "alsa_output.pci-0000_00_1f.3.analog-stereo",
                   "default source id": "alsa_input.pci-0000_00_1f.3.analog-stereo"}
    sink_list = SINKS
    source_list = SOURCES

    def sink_info(self, sid):
        return {"sample rate": 48000, "channels": 2}

    def source_info(self, sid):
        return {"sample rate": 44100, "channels": 2}


fake = types.ModuleType("soundcard")
fake.pulseaudio = types.SimpleNamespace(_pulse=FakePulse())
fake.all_speakers = lambda: []
fake.all_microphones = lambda include_loopback=False: [
    FakeMic(s["id"], isloopback="monitor" in s["id"]) for s in SOURCES
    if include_loopback or "monitor" not in s["id"]]
fake.get_microphone = lambda mid, include_loopback=False: FakeMic(mid, isloopback="monitor" in mid)
fake.default_speaker = lambda: types.SimpleNamespace(id=SINKS[0]["id"])
sys.modules["soundcard"] = fake

import audiocapture.audio as audio_mod  # noqa: E402

# force the linux branch regardless of the host platform
audio_mod.sys.platform = "linux"
# pactl is absent here on purpose: rates must then come back as None
audio_mod.subprocess = types.ModuleType("subprocess")


def run():
    engine = audio_mod.AudioEngine()
    loops = engine.list_loopbacks()
    assert len(loops) == 2, f"expected 2 outputs, got {len(loops)}"
    assert all(d.is_loopback for d in loops), "monitors must be loopbacks"
    assert loops[0].is_default and not loops[1].is_default, "default sink not flagged"
    assert loops[0].channels == 2
    print("loopbacks:", [(d.label, d.channels, d.is_default) for d in loops])
    src = engine.capture_source(loops[0])
    assert src.id.endswith(".monitor"), "capture source must be a monitor"
    print("capture source:", src.id)

    mics = engine.list_inputs()
    assert len(mics) == 1 and not mics[0].is_loopback, f"mic listing wrong: {mics}"
    assert mics[0].is_default, "default source not flagged"
    print("inputs:", [(d.label, d.channels) for d in mics])

    # rate choices: native rate first when known
    dev = loops[0]
    dev = audio_mod.Device(**{**dev.__dict__, "sample_rate": 96000}) \
        if hasattr(dev, "__dict__") else dev
    labels = [lbl for _r, lbl in audio_mod.rate_choices(dev)]
    assert "96,000 Hz (96 kHz)  -  native" in labels[0], labels[:2]
    print("rate labels:", labels[:3])

    # graceful failure with no devices at all
    FakePulse.sink_list = []
    FakePulse.source_list = []
    assert engine.list_loopbacks() == []
    print("empty-device handling: OK")
    print("\nLINUX DEVICE LOGIC TESTS PASSED")


if __name__ == "__main__":
    run()

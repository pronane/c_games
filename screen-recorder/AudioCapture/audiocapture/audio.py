"""Audio device discovery and capture-source resolution.

The app records the *system output* (what you hear) by default.  How that is
done depends on the platform:

Windows (WASAPI)
    Every render (speaker) endpoint can be opened in *loopback* mode.  This is
    the cleanest form of system-audio capture: it is digital, bit-accurate with
    respect to the shared-mode mixer, keeps the recorded level independent of
    the speaker volume slider and needs no drivers at all.

Linux (PulseAudio / PipeWire-pulse)
    Each output has a matching ``*.monitor`` source.  Recording the monitor of
    the default sink gives exactly the same thing.

In both cases the data is already float32 and converted/resampled by the OS
mixer ("AUTOCONVERT" on Linux, WASAPI ``AUTOCONVERTPCM`` on Windows), so any
sample rate the device supports can be requested - including lossless 24-bit
quality at the device's native rate.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import Any, List, Optional

# Sample rates we offer.  The device's native rate is marked in the UI; all of
# these are resampled by the OS mixer, so they are safe for any device.
COMMON_RATES = (44100, 48000, 88200, 96000, 176400, 192000)
DEFAULT_RATE = 48000


class BackendError(RuntimeError):
    """Raised when no audio backend / device can be used."""


@dataclass(frozen=True)
class Device:
    """A capture device (either a loopback of an output, or a real input)."""

    id: Any
    name: str
    kind: str  # "loopback" | "input"
    channels: int
    sample_rate: Optional[int] = None  # native/mixer rate if the OS tells us
    is_default: bool = False
    info: str = ""
    raw: Any = field(default=None, repr=False, compare=False)

    @property
    def is_loopback(self) -> bool:
        return self.kind == "loopback"

    @property
    def label(self) -> str:
        mark = "Default - " if self.is_default else ""
        return f"{mark}{self.name}"

    @property
    def channel_text(self) -> str:
        return describe_channels(self.channels)


def describe_channels(n: int) -> str:
    return {
        1: "Mono (1.0)",
        2: "Stereo (2.0)",
        6: "5.1 surround",
        8: "7.1 surround",
    }.get(n, f"{n} channels")


def format_rate(rate: Optional[int]) -> str:
    if not rate:
        return "device rate (unknown)"
    khz = rate / 1000.0
    return f"{rate:,} Hz ({khz:g} kHz)"


def rate_choices(device: Optional[Device]) -> List[tuple[int, str]]:
    """Return [(rate, label)] with the device's native rate first."""
    native = device.sample_rate if device else None
    preferred = native or DEFAULT_RATE
    rates = list(COMMON_RATES)
    if native and native not in rates:
        rates.append(native)
    rates.sort(key=lambda r: (r != preferred, r))
    out = []
    for r in rates:
        label = format_rate(r)
        if native and r == native:
            label += "  -  native"
        out.append((r, label))
    return out


class AudioEngine:
    """Thin wrapper around the ``soundcard`` library (WASAPI / PulseAudio)."""

    backend_name = "soundcard (WASAPI / PulseAudio)"

    def __init__(self) -> None:
        self._sc = None
        self._import_error: Optional[str] = None
        self.platform = sys.platform

    # ------------------------------------------------------------------ setup
    @property
    def sc(self):
        if self._sc is None:
            if self._import_error:
                raise BackendError(self._import_error)
            try:
                # soundcard infers the program name from sys.argv at import time
                # (``_infer_program_name``) and raises IndexError when argv is
                # empty, e.g. ``python -c "import ..."`` or some host apps
                # embedding us.  Give it something safe to chew on.
                if not getattr(sys, "argv", None):
                    sys.argv = ["audiocapture"]
                elif sys.argv[0] == "-c" and len(sys.argv) < 2:
                    sys.argv = ["audiocapture"] + list(sys.argv[1:])
                import soundcard  # noqa: WPS433 (deliberate lazy import)

                self._sc = soundcard
            except Exception as exc:  # OSError on Linux without libpulse, etc.
                first_line = str(exc).splitlines()[0][:160]
                hint = ""
                if sys.platform.startswith("linux"):
                    hint = (
                        "\nOn Linux this usually means PulseAudio or PipeWire is not "
                        "running. Install/start one of:\n"
                        "  sudo apt install pulseaudio     (or pipewire-pulse)"
                    )
                elif sys.platform == "win32":
                    hint = (
                        "\nOn Windows, make sure the 'soundcard' package installed "
                        "correctly:  pip install --force-reinstall soundcard"
                    )
                self._import_error = f"Audio backend unavailable: {first_line}{hint}"
                raise BackendError(self._import_error) from exc
        return self._sc

    @property
    def available(self) -> bool:
        try:
            self.sc  # noqa: B018
            return True
        except BackendError:
            return False

    # ------------------------------------------------------- device listings
    def list_loopbacks(self) -> List[Device]:
        """Outputs, recorded via loopback/monitor (the default source)."""
        if sys.platform == "win32":
            return self._windows_loopbacks()
        return self._linux_loopbacks()

    def list_inputs(self) -> List[Device]:
        """Physical microphones / line-in devices."""
        if sys.platform == "win32":
            devices = list(self.sc.all_microphones(include_loopback=False))
            default_id = self._default_windows_mic_id()
            out = []
            for dev in devices:
                out.append(
                    Device(
                        id=dev.id,
                        name=self._safe(lambda d=dev: d.name, "Microphone"),
                        kind="input",
                        channels=self._safe(lambda d=dev: d.channels, 2) or 2,
                        sample_rate=None,
                        is_default=getattr(dev, "id", None) == default_id,
                        info="Microphone input",
                        raw=dev,
                    )
                )
            return out
        return self._linux_inputs()

    def default_loopback(self, devices: List[Device]) -> Optional[Device]:
        for dev in devices:
            if dev.is_default:
                return dev
        return devices[0] if devices else None

    # ------------------------------------------------------------ resolution
    def capture_source(self, device: Device):
        """Return an object with a ``.recorder(...)`` context manager."""
        if device.raw is None:
            raise BackendError("Device is not available any more - please refresh.")
        if device.kind == "loopback" and sys.platform == "win32":
            # soundcard exposes WASAPI loopback via a microphone wrapper around
            # a render endpoint.
            import soundcard.mediafoundation as mf

            return mf._Microphone(device.raw, isloopback=True)
        return device.raw

    # --------------------------------------------------------------- windows
    def _windows_loopbacks(self) -> List[Device]:
        speakers = list(self.sc.all_speakers())
        default_id = None
        try:
            default_id = self.sc.default_speaker().id
        except Exception:
            pass
        out = []
        for spk in speakers:
            channels, rate, bits = self._windows_format(spk)
            out.append(
                Device(
                    id=spk.id,
                    name=self._safe(lambda s=spk: s.name, "Speakers"),
                    kind="loopback",
                    channels=channels or 2,
                    sample_rate=rate,
                    is_default=getattr(spk, "id", None) == default_id,
                    info=f"System output (WASAPI loopback"
                         + (f", {bits}-bit shared mix" if bits else "") + ")",
                    raw=spk,
                )
            )
        return out

    @staticmethod
    def _windows_format(speaker):
        """Read (channels, sample_rate, bits) from the device's WAVEFORMATEX.

        Same property ``soundcard`` uses for ``.channels``; we additionally pull
        the sample rate and bit depth so the UI can default to the device's
        native format (e.g. 48 000 Hz 24-bit) instead of guessing.
        """
        try:
            import soundcard.mediafoundation as mf

            _ffi = mf._ffi
            _com = mf._com
            ppPropertyStore = _ffi.new("IPropertyStore **")
            ptr = speaker._device_ptr()
            hr = ptr[0][0].lpVtbl.OpenPropertyStore(ptr[0], 0, ppPropertyStore)
            _com.release(ptr)
            _com.check_error(hr)
            propvariant = mf._PropVariant()
            key = _ffi.new("PROPERTYKEY *",
                           [[0xf19f064d, 0x82c, 0x4e27,
                             [0xbc, 0x73, 0x68, 0x82, 0xa1, 0xbb, 0x8e, 0x4c]], 0])
            hr = ppPropertyStore[0][0].lpVtbl.GetValue(ppPropertyStore[0], key,
                                                       propvariant.ptr)
            _com.release(ppPropertyStore)
            _com.check_error(hr)
            if propvariant.ptr[0].vt != 65:
                return None, None, None
            blob = _ffi.cast("BLOB_PROPVARIANT *", propvariant.ptr)
            wave = _ffi.cast("WAVEFORMATEX *", blob[0].blob.pBlobData)
            return int(wave[0].nChannels), int(wave[0].nSamplesPerSec), int(wave[0].wBitsPerSample)
        except Exception:
            return None, None, None

    def _default_windows_mic_id(self):
        try:
            return self.sc.default_microphone().id
        except Exception:
            return None

    # ----------------------------------------------------------------- linux
    def _linux_loopbacks(self) -> List[Device]:
        sc = self.sc
        default_sink_id = None
        try:
            default_sink_id = sc.pulseaudio._pulse.server_info["default sink id"]
        except Exception:
            pass
        out = []
        # Sinks and their monitors share a name; build monitors explicitly so
        # only one monitor per output is listed (not every internal source).
        try:
            sinks = sc.pulseaudio._pulse.sink_list
        except Exception as exc:
            raise BackendError(f"Could not enumerate audio outputs: {exc}") from exc
        for sink in sinks:
            monitor_id = sink["id"] + ".monitor"
            try:
                monitor = sc.get_microphone(monitor_id, include_loopback=True)
            except Exception:
                continue  # monitor not available (rare)
            out.append(
                Device(
                    id=monitor_id,
                    name=sink["name"],
                    kind="loopback",
                    channels=self._safe(lambda m=monitor: m.channels, 2) or 2,
                    sample_rate=self._linux_rate(sink["id"], kind="sink"),
                    is_default=sink["id"] == default_sink_id,
                    info="System output (PulseAudio monitor)",
                    raw=monitor,
                )
            )
        return out

    def _linux_inputs(self) -> List[Device]:
        sc = self.sc
        default_source_id = None
        try:
            default_source_id = sc.pulseaudio._pulse.server_info["default source id"]
        except Exception:
            pass
        out = []
        try:
            mics = sc.all_microphones(include_loopback=False)
        except Exception as exc:
            raise BackendError(f"Could not enumerate microphones: {exc}") from exc
        # Prefer the human-friendly PulseAudio description over the raw id
        # (``mic.name`` on Linux is the source *name* such as
        # ``alsa_input.pci-0000_00_1f.3.analog-stereo``).
        descriptions = {}
        try:
            for entry in sc.pulseaudio._pulse.source_list:
                descriptions[entry["id"]] = entry["name"]
        except Exception:
            pass
        for mic in mics:
            out.append(
                Device(
                    id=mic.id,
                    name=descriptions.get(mic.id)
                    or self._safe(lambda m=mic: m.name, "Microphone"),
                    kind="input",
                    channels=self._safe(lambda m=mic: m.channels, 2) or 2,
                    sample_rate=self._linux_rate(mic.id, kind="source"),
                    is_default=mic.id == default_source_id,
                    info="Microphone input",
                    raw=mic,
                )
            )
        return out

    def _linux_rate(self, dev_id: str, kind: str = "sink") -> Optional[int]:
        """Native/mixer sample rate of a sink/source, via ``pactl`` (stable API).

        The sample rate shown by PulseAudio is its server-side mixer rate, which
        is the rate at which monitor sources deliver audio.
        """
        try:
            import re
            import subprocess

            cmd = "sinks" if kind == "sink" else "sources"
            res = subprocess.run(
                ["pactl", "list", "short", cmd],
                capture_output=True,
                text=True,
                timeout=2,
            )
            for line in res.stdout.splitlines():
                cols = line.split("\t")
                if len(cols) >= 5 and cols[1] == dev_id:
                    return int(cols[4])
        except Exception:
            pass
        return None

    # ---------------------------------------------------------------- helpers
    @staticmethod
    def _safe(fn, fallback):
        try:
            return fn()
        except Exception:
            return fallback


def ensure_com_initialized() -> None:
    """Initialise the COM apartment for the *calling* thread (Windows).

    WASAPI is COM based and every thread that touches an ``IAudioClient`` must
    have called ``CoInitializeEx`` first.  ``soundcard`` only does this once,
    on whichever thread imports it, so worker threads must do it themselves or
    device access fails with ``CO_E_NOTINITIALIZED`` (0x800401F0).
    Safe to call repeatedly and on other platforms (no-op).
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes

        RPC_E_CHANGED_MODE = -2147417850  # already initialised in another mode
        hr = ctypes.windll.ole32.CoInitializeEx(None, 0x0)  # COINIT_MULTITHREADED
        if hr not in (0, 1, RPC_E_CHANGED_MODE):
            raise OSError(f"CoInitializeEx failed: 0x{hr & 0xFFFFFFFF:08X}")
    except OSError:
        raise
    except Exception:
        pass


def downmix_block(block, target_channels: int):
    """Return ``block`` as float32 with exactly ``target_channels`` columns."""
    import numpy as np

    data = np.asarray(block, dtype=np.float32)
    if data.ndim == 1:
        data = data[:, None]
    src = data.shape[1]
    if src == target_channels:
        return np.ascontiguousarray(data)
    if target_channels == 1:
        if src >= 2:
            return np.ascontiguousarray(data[:, :2].mean(axis=1, keepdims=True))
        return np.ascontiguousarray(data[:, :1])
    if target_channels == 2:
        if src >= 2:  # front L/R from a surround mix, or plain stereo
            return np.ascontiguousarray(data[:, :2])
        return np.ascontiguousarray(np.repeat(data[:, :1], 2, axis=1))
    # pad with silence for exotic configurations
    out = np.zeros((data.shape[0], target_channels), dtype=np.float32)
    take = min(src, target_channels)
    out[:, :take] = data[:, :take]
    return out

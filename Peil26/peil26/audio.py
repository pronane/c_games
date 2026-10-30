"""Original stadium audio for PEIL 26. No licensed recordings."""

from __future__ import annotations

import math

import numpy as np

SR = 44100


def _env(n, attack=0.01, release=0.08):
    t = np.linspace(0, 1, n, endpoint=False)
    a = np.minimum(1.0, t / max(attack, 1e-4))
    r = np.minimum(1.0, (1 - t) / max(release, 1e-4))
    return np.minimum(a, r).astype(np.float32)


def _tone(freq, dur, vol=0.3, wave="sine", decay=3.0):
    n = int(SR * dur)
    t = np.arange(n) / SR
    if wave == "square":
        sig = np.sign(np.sin(2 * math.pi * freq * t))
    elif wave == "tri":
        sig = 2 * np.abs(2 * (freq * t % 1) - 1) - 1
    else:
        sig = np.sin(2 * math.pi * freq * t)
    sig = sig * np.exp(-decay * t) * _env(n, 0.005, min(0.2, dur * 0.4))
    return (sig * vol).astype(np.float32)


def _noise(dur, vol=0.2, color="white", decay=1.5):
    n = int(SR * dur)
    rng = np.random.default_rng(int(dur * 1000) + 7)
    sig = rng.standard_normal(n).astype(np.float32)
    if color == "brown":
        sig = np.cumsum(sig)
        sig -= sig.mean()
    sig /= np.max(np.abs(sig)) + 1e-6
    t = np.arange(n) / SR
    sig *= np.exp(-decay * t) * _env(n, 0.005, 0.1)
    return (sig * vol).astype(np.float32)


def _stereo(mono, pan=0.0, width=0.15):
    left = mono * (1 - pan) 
    right = mono * (1 + pan)
    # tiny delay for width
    shift = int(SR * width * 0.002)
    if shift:
        right = np.roll(right, shift)
    return np.column_stack([left, right]).astype(np.float32)


def _mix(*parts):
    n = max(len(p) for p in parts)
    out = np.zeros(n, dtype=np.float32)
    for p in parts:
        out[: len(p)] += p
    peak = np.max(np.abs(out)) + 1e-6
    if peak > 1:
        out *= 0.95 / peak
    return out


class Audio:
    def __init__(self):
        self.muted = False
        self.ok = False
        self.sounds = {}
        self.crowd = None
        self.music = None
        try:
            import pygame
            self.pygame = pygame
            if not pygame.mixer.get_init():
                pygame.mixer.init(SR, -16, 2, 512)
            self._build()
            self.ok = True
        except Exception:
            self.pygame = None

    def _snd(self, samples):
        pcm = np.clip(samples * 32767, -32767, 32767).astype(np.int16)
        return self.pygame.mixer.Sound(buffer=pcm.tobytes())

    def _build(self):
        rng = np.random.default_rng(26)
        # Crowd bed: murmur, low hum, a soft bodhrán pulse. Original, not a recording.
        n = SR * 6
        white = rng.standard_normal(n).astype(np.float32)
        brown = np.cumsum(white)
        brown = brown - np.convolve(brown, np.ones(800) / 800, mode="same")
        brown /= np.max(np.abs(brown)) + 1e-6
        t = np.arange(n) / SR
        hum = 0.18 * np.sin(2 * math.pi * 92 * t) + 0.1 * np.sin(2 * math.pi * 138 * t)
        pulse = (np.sin(2 * math.pi * 2.15 * t) > 0.72).astype(np.float32)
        thump = np.convolve(pulse, np.exp(-np.linspace(0, 8, 1800)), mode="same")
        thump /= np.max(thump) + 1e-6
        bed = brown * 0.22 + hum * 0.08 + thump * 0.05
        bed = _stereo(bed.astype(np.float32), 0.05, 0.4)
        self.crowd = self._snd(bed)
        self.crowd.set_volume(0.28)

        cheer = _mix(_noise(1.6, 0.55, "brown", 0.6), _tone(523, 1.2, 0.08, decay=1.2), _tone(659, 1.2, 0.06, decay=1.2))
        roar = _mix(_noise(2.4, 0.8, "brown", 0.35), _tone(196, 1.6, 0.2, decay=0.8), _tone(294, 1.4, 0.14, decay=0.9), _tone(392, 1.1, 0.1, decay=1.0))
        groan = _mix(_noise(1.1, 0.35, "brown", 1.2), _tone(220, 0.8, 0.08, decay=2))
        whistle = _mix(_tone(3250, 0.32, 0.22, decay=2), _noise(0.28, 0.08, decay=6))
        whistle_long = _mix(_tone(3100, 1.1, 0.2, decay=0.4), _noise(1.0, 0.05, decay=1))
        hooter = _mix(_tone(520, 0.7, 0.28, "square", 0.6), _tone(390, 0.9, 0.22, "square", 0.5))
        kick = _mix(_tone(78, 0.18, 0.55, decay=18), _noise(0.08, 0.25, decay=30))
        hand = _mix(_tone(180, 0.09, 0.35, decay=28), _noise(0.06, 0.18, decay=40))
        bounce = _mix(_tone(110, 0.12, 0.3, decay=16), _tone(90, 0.1, 0.15, decay=20))
        post = _mix(_tone(880, 0.22, 0.2, decay=8), _tone(1320, 0.16, 0.1, decay=10))
        goal = roar
        two = _mix(_tone(349, 0.35, 0.16, decay=3), _tone(523, 0.4, 0.14, decay=3), _noise(0.8, 0.2, "brown", 1.2))
        point = cheer * 0.8

        table = {
            "crowd": bed,
            "cheer": _stereo(cheer, 0.1),
            "groan": _stereo(groan),
            "whistle": _stereo(whistle),
            "whistle_long": _stereo(whistle_long),
            "hooter": _stereo(hooter),
            "kick": _stereo(kick, -0.05),
            "hand": _stereo(hand),
            "bounce": _stereo(bounce),
            "solo": _stereo(hand * 0.7),
            "post": _stereo(post),
            "goal": _stereo(goal, 0.05),
            "point": _stereo(point),
            "two": _stereo(two),
            "tackle": _stereo(_noise(0.12, 0.3, decay=18)),
            "shoulder": _stereo(_noise(0.14, 0.28, decay=14)),
            "block": _stereo(_mix(_noise(0.1, 0.3, decay=20), _tone(240, 0.08, 0.15, decay=20))),
            "save": _stereo(_mix(_noise(0.2, 0.3, decay=8), _tone(160, 0.15, 0.2, decay=10))),
            "switch": _stereo(_tone(740, 0.06, 0.12, decay=20)),
            "pa": _stereo(_tone(880, 0.08, 0.1, decay=12)),
        }
        for name, data in table.items():
            if data.ndim == 1:
                data = _stereo(data)
            self.sounds[name] = self._snd(data)
        self.music = self._snd(self._menu_music())
        self.music.set_volume(0.16)

    def _menu_music(self):
        # Original 8-bar line in D mixolydian. Not a traditional air.
        melody = [293.66, 349.23, 392.00, 440.00, 523.25, 440.00, 392.00, 349.23,
                  293.66, 329.63, 392.00, 466.16, 440.00, 392.00, 349.23, 293.66]
        parts = []
        for i, f in enumerate(melody):
            note = _tone(f, 0.42, 0.11, "sine", decay=2.2)
            parts.append(note)
        line = np.concatenate(parts)
        # soft fifth underneath
        drone = _tone(146.83, len(line) / SR, 0.04, decay=0.15)
        return _stereo(_mix(line, drone), 0.0, 0.2)

    def start_bed(self):
        if self.ok and self.crowd and not self.muted:
            self.crowd.play(loops=-1)

    def stop_bed(self):
        if self.ok and self.crowd:
            self.crowd.stop()

    def start_music(self):
        if self.ok and self.music and not self.muted:
            self.music.play(loops=-1)

    def stop_music(self):
        if self.ok and self.music:
            self.music.stop()

    def play(self, name):
        if not self.ok or self.muted:
            return
        snd = self.sounds.get(name)
        if snd:
            snd.play()

    def set_intensity(self, amount):
        if self.ok and self.crowd and not self.muted:
            self.crowd.set_volume(0.18 + 0.22 * max(0.0, min(1.0, amount)))

    def toggle_mute(self):
        self.muted = not self.muted
        if self.muted:
            self.stop_bed()
            self.stop_music()
        return self.muted

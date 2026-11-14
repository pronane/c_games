"""Check a transcription by playing it back against the recording it came from.

After a breakdown the app has two versions of each part: the audio it heard and the notes it
wrote down. This renders the notes with the engine's own guitar playback and compares the two
recordings pitch by pitch, ten times a second, and marks the stretches where they disagree:

- **gap**: the recording is sounding but the transcription has no note at all;
- **differs**: the pitches in the two versions match clearly worse than they do in the rest of
  this same song.

The second test is relative on purpose. The playback is a generic guitar sound, so even a
note-perfect transcription never matches the recording exactly (about 0.7 on this measure for
clean guitar), and the level varies from one recording to the next. Comparing each stretch with
the song's own typical match finds the places where the transcription went wrong, whatever the
recording sounds like. The thresholds were set on GuitarSet with planted errors
(benchmarks/transcription_check_eval.py).
"""
from __future__ import annotations

import base64

import numpy as np

SR = 22050
FPS = 10                        # analysis frames per second
HOP = SR // FPS
LOW_MIDI, BINS = 40, 49         # E2 .. E6: the guitar's range
STRETCH_S = 2.0
DIFFERS_BELOW = 0.15            # a stretch this far under the song's median match is flagged
DIFFERS_FLOOR = 0.45            # and anything under this is flagged regardless
MISSING_ABOVE = 0.20            # a stretch missing this much more of the recording's pitch than usual
MISSING_FLOOR = 0.45            # (share of the recording's strong pitch the playback lacks)
GAP_MIN_S = 1.5
NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']


def note_name(midi: int) -> str:
    return f'{NAMES[midi % 12]}{midi // 12 - 1}'


def mono22(audio, sr) -> np.ndarray:
    import librosa
    y = np.asarray(audio, dtype=np.float32)
    if y.ndim == 2:
        y = y.mean(axis=1)
    return librosa.resample(y, orig_sr=sr, target_sr=SR) if sr != SR else y


def playback(notes: list, length_s: float, tuning_cents: float = 0.0) -> np.ndarray:
    """The transcription as the engine plays it (clean steel string), mono at SR."""
    from .fx.playback import render_acoustic
    clean = [{'time': float(n['time']), 'duration': max(0.05, float(n.get('duration', 0.3))), 'midi': int(n['midi']),
              'velocity': n.get('velocity', 90)} for n in notes]
    out = render_acoustic(clean, sr=SR, length_s=length_s, tuning_cents=tuning_cents) if clean else np.zeros(int(SR * length_s))
    out = np.asarray(out, dtype=np.float32)
    return out.mean(axis=1) if out.ndim == 2 else out


def _levels(y):
    import librosa
    C = np.abs(librosa.cqt(y, sr=SR, hop_length=HOP, fmin=librosa.midi_to_hz(LOW_MIDI), n_bins=BINS))
    return librosa.amplitude_to_db(C, ref=np.max)


def _chroma(y):
    import librosa
    return librosa.feature.chroma_stft(y=y, sr=SR, n_fft=4096, hop_length=HOP)


def compare(original: np.ndarray, played: np.ndarray, notes: list) -> dict:
    """Stretch-by-stretch comparison of a recording (mono, SR) with its transcription's playback."""
    import librosa
    played = np.pad(played, (0, max(0, len(original) - len(played))))[:len(original)]
    lo, lp = _levels(original), _levels(played)
    n = min(lo.shape[1], lp.shape[1])
    lo, lp = lo[:, :n], lp[:, :n]
    fo, fp = lo - lo.max(axis=0, keepdims=True), lp - lp.max(axis=0, keepdims=True)
    strong_o, strong_p = (fo > -14) & (lo > -45), (fp > -14) & (lp > -45)
    missing = strong_o & (fp < -30)                # in the recording, absent from the playback
    extra = strong_p & (fo < -30)                  # in the playback, absent from the recording
    rms = librosa.feature.rms(y=original, frame_length=2 * HOP, hop_length=HOP)[0][:n]
    sounding = rms > 0.1 * max(float(np.percentile(rms, 90)), 1e-9)

    co, cp = _chroma(original)[:, :n], _chroma(played)[:, :n]
    step = int(STRETCH_S * FPS)
    match, lack = [], []
    for a in range(0, n, step):
        if sounding[a:a + step].mean() < 0.5:
            match.append(None)
            lack.append(None)
            continue
        x, y = co[:, a:a + step], cp[:, a:a + step]
        match.append(float((x * y).sum() / (np.linalg.norm(x) * np.linalg.norm(y) + 1e-9)))
        lack.append(float(missing[:, a:a + step].sum() / max(1, strong_o[:, a:a + step].sum())))
    scored = [m for m in match if m is not None]
    typical = float(np.median(scored)) if scored else 0.0
    cut = max(DIFFERS_FLOOR, typical - DIFFERS_BELOW) if scored else 0.0
    lacks = [m for m in lack if m is not None]
    usual_lack = float(np.median(lacks)) if lacks else 0.0
    lack_cut = max(MISSING_FLOOR, usual_lack + MISSING_ABOVE)

    covered = np.zeros(n, bool)
    for note in notes:
        a = int(float(note['time']) * FPS)
        covered[a:a + max(1, int(max(float(note.get('duration', 0.3)), 0.3) * FPS)) + 1] = True
    flags = []
    run = None
    for i in range(n + 1):
        hole = i < n and sounding[i] and not covered[i]
        if hole and run is None:
            run = i
        if not hole and run is not None:
            if i - run >= GAP_MIN_S * FPS:
                flags.append({'start': run / FPS, 'end': i / FPS, 'status': 'gap'})
            run = None
    for k, m in enumerate(match):
        if m is not None and (m < cut or lack[k] > lack_cut):
            a, b = k * STRETCH_S, min((k + 1) * STRETCH_S, n / FPS)
            if not any(f['status'] == 'gap' and f['start'] <= a and b <= f['end'] for f in flags):
                flags.append({'start': a, 'end': b, 'status': 'differs', 'match': round(m, 3)})
    flags = _merge(sorted(flags, key=lambda f: f['start']))
    for f in flags:
        a, b = int(f['start'] * FPS), int(f['end'] * FPS)
        f['missing'] = [note_name(LOW_MIDI + i) for i in np.argsort(-missing[:, a:b].sum(1))[:3] if missing[i, a:b].sum() >= 3]
        f['extra'] = [note_name(LOW_MIDI + i) for i in np.argsort(-extra[:, a:b].sum(1))[:3] if extra[i, a:b].sum() >= 3]
        f['start'], f['end'] = round(f['start'], 1), round(f['end'], 1)
    active = sounding.sum() / FPS
    flagged = sum(f['end'] - f['start'] for f in flags)

    def top(mask):
        count = mask[:, sounding].sum(axis=1)
        return [{'note': note_name(LOW_MIDI + i), 'seconds': round(float(count[i]) / FPS, 1)}
                for i in np.argsort(-count)[:5] if count[i] >= FPS]

    return {
        'summary': {'typical_match': round(typical, 3), 'flagged_seconds': round(flagged, 1),
                    'sounding_seconds': round(float(active), 1),
                    'flagged_share': round(flagged / active, 3) if active else 0.0,
                    'stretches': len(flags)},
        'stretches': flags,
        'match_per_stretch': [None if m is None else round(m, 3) for m in match],
        'missing_per_stretch': [None if m is None else round(m, 3) for m in lack],
        'stretch_s': STRETCH_S,
        'most_missing': top(missing),
        'most_extra': top(extra),
        'roll': {'fps': FPS, 'low_midi': LOW_MIDI, 'bins': BINS, 'frames': int(n),
                 'level': base64.b64encode((np.clip((lo + 60) / 60, 0, 1) * 255).astype(np.uint8).tobytes()).decode(),
                 'missing': base64.b64encode(missing.astype(np.uint8).tobytes()).decode(),
                 'extra': base64.b64encode(extra.astype(np.uint8).tobytes()).decode()},
    }


def _merge(flags):
    out = []
    for f in flags:
        last = out[-1] if out else None
        if last and f['start'] <= last['end'] + 1e-6:
            last['end'] = max(last['end'], f['end'])
            if f['status'] == 'gap':
                last['status'] = 'gap'
            if 'match' in f:
                last['match'] = min(last.get('match', 1.0), f['match'])
        else:
            out.append(dict(f))
    return out


def check(audio, sr, notes: list, tuning_cents: float = 0.0):
    """(report, playback audio at SR) for one part."""
    original = mono22(audio, sr)
    played = playback(notes, len(original) / SR, tuning_cents)
    return compare(original, played, notes), played

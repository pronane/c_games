"""Training segments for heavy-guitar fine-tuning.

GuitarSet (CC BY 4.0) pickup recordings from players 00-04 are re-amped through random crunch /
high-gain chains (player 05 is held out: the regression library uses it). Original riffs from
training/riffs.py add palm-muted chugs and double-tracked power chords at 90-220 BPM. A share
of clean GuitarSet stays in so the model does not forget clean playing.

Writes 10 s segments (16 kHz, int16) with their notes to <out>/seg_*.npz."""
from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from training import amp, riffs  # noqa: E402

SR = 16000
SEG = 10.0


def guitarset_notes(jams_path):
    from benchmarks.guitarset import truth
    return truth(jams_path)[0]


def save(out: Path, k: int, y: np.ndarray, notes: list, source: str):
    np.savez_compressed(out / f'seg_{k:05d}.npz', audio=(np.clip(y, -1, 1) * 32767).astype(np.int16),
                        notes=json.dumps([[n['time'], n['duration'], n['midi']] for n in notes]), source=source)


def segments(y, notes, rng):
    """Random-offset 10 s windows covering the clip; notes clipped to each window."""
    total = len(y) / SR
    start = rng.uniform(0, 2.0)
    while start + 4 < total:
        a, b = start, min(total, start + SEG)
        seg = y[int(a * SR):int(b * SR)]
        seg = np.pad(seg, (0, int(SEG * SR) - len(seg)))
        inside = [dict(time=max(0.0, n['time'] - a), duration=min(n['time'] + n['duration'], b) - max(n['time'], a), midi=n['midi'])
                  for n in notes if n['time'] < b and n['time'] + n['duration'] > a]
        yield seg, [n for n in inside if n['duration'] > 0.01]
        start += SEG


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--guitarset-audio', required=True)
    ap.add_argument('--guitarset-ann', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--riffs', type=int, default=500)
    ap.add_argument('--seed', type=int, default=7)
    a = ap.parse_args()
    import librosa
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(a.seed)
    k = 0
    for wav in sorted(glob.glob(f'{a.guitarset_audio}/*.wav')):
        name = Path(wav).name
        if name.startswith('05_'):
            continue                                   # held out
        jams = Path(a.guitarset_ann) / name.replace('_mix.wav', '.jams')
        notes = guitarset_notes(jams)
        y, sr = sf.read(wav, dtype='float32')
        y = librosa.resample(y if y.ndim == 1 else y.mean(1), orig_sr=sr, target_sr=SR)
        r = rng.random()
        style = 'clean' if r < 0.25 else 'crunch' if r < 0.55 else 'high_gain'
        z = y / (np.abs(y).max() + 1e-9) * 0.7 if style == 'clean' else amp.reamp(y, SR, rng, style)
        for seg, ns in segments(z, notes, rng):
            save(out, k, seg, ns, f'guitarset:{style}'); k += 1
    for i in range(a.riffs):
        bpm, notes, length = riffs.riff(rng, bars=int(rng.integers(3, 7)))
        y = riffs.render(notes, length, rng, takes=int(rng.choice([1, 2, 2, 3])))
        y = amp.reamp(y, SR, rng, 'high_gain' if rng.random() < 0.75 else 'crunch')
        ns = [{'time': t, 'duration': d, 'midi': int(round(m))} for t, d, m, _ in notes]
        for seg, sn in segments(y, ns, rng):
            save(out, k, seg, sn, 'riff'); k += 1
    print(k, 'segments')


if __name__ == '__main__':
    main()

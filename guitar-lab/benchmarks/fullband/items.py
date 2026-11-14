"""Build items for the frozen full-band test (benchmarks/fullband/gate.py).

An item is a folder with `mix.wav` (a real band mix) and `reference.json` (the guitar's notes,
known independently of the mix). Two ways to make one:

    # Play-along: your own recording of the guitar part, played on its own (clean, no backing
    # audible in the recording), mixed into the song with the song's own guitar taken out.
    python -m benchmarks.fullband.items playalong <take audio> <song audio> <name>

    # Multitrack: a song whose separate guitar track(s) you have.
    python -m benchmarks.fullband.items multitrack <mix audio> <name> <guitar track> [<guitar track> ...]

The reference is Riley's reading of the guitar on its own, where it is right about 94% of the
time on clean guitar (RESULTS.md). The test therefore measures what the band mix costs: how
much of what the engine hears in the guitar alone it still hears inside the mix. Items are
written to benchmarks/fullband/data/, which is not committed: recordings stay on this machine.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

DATA = Path(__file__).resolve().parent / 'data'
SR = 44100


def load(path):
    import librosa
    y, _ = librosa.load(str(path), sr=SR, mono=False)
    y = np.atleast_2d(y).T.astype(np.float32)
    return np.repeat(y, 2, axis=1) if y.shape[1] == 1 else y[:, :2]


def reference(guitar_mono, source):
    import librosa
    from server import riley
    notes = riley.decode(riley.posteriors(librosa.resample(guitar_mono, orig_sr=SR, target_sr=riley.SAMPLE_RATE)))[0]
    return {'source': source, 'notes': [{'time': round(n['time'], 4), 'duration': round(n['duration'], 4), 'midi': int(n['midi'])} for n in notes]}


def write(name, mix, ref, extra):
    folder = DATA / name
    folder.mkdir(parents=True, exist_ok=True)
    peak = float(np.abs(mix).max()) or 1.0
    sf.write(folder / 'mix.wav', mix / max(1.0, peak / 0.98), SR)
    (folder / 'reference.json').write_text(json.dumps({**ref, **extra}))
    (folder / 'guitar.wav').unlink(missing_ok=True)          # separation cache of an older mix
    print(json.dumps({'item': name, 'seconds': round(len(mix) / SR, 1), 'reference_notes': len(ref['notes']), **extra}))
    return folder


def take_offset(take_mono, song_guitar_mono):
    """Where the take starts in the song (seconds), from the pitch content of the take and of
    the song's own guitar. The take must be played at the song's tempo."""
    from server import tab_align as ta
    X = ta._unit(ta.audio_chroma(take_mono, SR))
    Y = ta._unit(ta.audio_chroma(song_guitar_mono, SR))
    fit = ta.linear_fit(X, Y, ratios=[1.0], max_offset_s=1e6, min_overlap=0.8)
    return fit['offset'], fit['similarity']


def playalong(take_path, song_path, name):
    from server import models
    take, song = load(take_path), load(song_path)
    stems, sr, _ = models.run_demucs(song, SR)
    assert sr == SR
    offset, similarity = take_offset(take.mean(axis=1), stems['guitar'].mean(axis=1))
    backing = sum(v for k, v in stems.items() if k != 'guitar')
    a = int(round(offset * SR))
    placed = np.zeros_like(backing)
    src = take[max(0, -a):]
    start = max(0, a)
    n = min(len(src), len(placed) - start)
    placed[start:start + n] = src[:n]
    # The take at the level the song's own guitar had where both play.
    both = slice(start, start + n)
    gain = float(np.sqrt((stems['guitar'][both] ** 2).mean() / ((placed[both] ** 2).mean() + 1e-12)))
    gain = float(np.clip(gain, 0.1, 10.0))
    ref = reference(placed.mean(axis=1), 'play-along take, transcribed on its own')
    lo, hi = start / SR, (start + n) / SR
    return write(name, backing + gain * placed, ref,
                 {'kind': 'playalong', 'take_starts_at_s': round(offset, 2), 'line_up_similarity': round(similarity, 3),
                  'take_gain': round(gain, 2), 'scored_from_s': round(lo, 2), 'scored_to_s': round(hi, 2)})


def multitrack(mix_path, name, guitar_paths):
    mix = load(mix_path)
    guitar = np.zeros(len(mix), np.float32)
    for p in guitar_paths:
        g = load(p).mean(axis=1)
        guitar[:min(len(g), len(guitar))] += g[:len(guitar)]
    ref = reference(guitar, 'the song\'s own guitar tracks, transcribed on their own')
    return write(name, mix, ref, {'kind': 'multitrack', 'scored_from_s': 0.0, 'scored_to_s': round(len(mix) / SR, 2)})


if __name__ == '__main__':
    mode, args = sys.argv[1], sys.argv[2:]
    playalong(*args) if mode == 'playalong' else multitrack(args[0], args[1], args[2:])

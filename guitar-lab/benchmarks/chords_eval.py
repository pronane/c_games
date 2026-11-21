"""How often are the app's chords right? Measured against chords read from the player's own tabs.

For each song the reference is the chord the tab implies on each beat: the pitch classes of every
pitched tab track sounding on that beat (placed on the recording by a saved line-up), matched to
the same chord templates the app uses. The app's chords come from the same function the song
breakdown uses (song_analysis.chords_per_beat) on beat-synchronous chroma from

- ``mix``: the whole recording,
- ``harmonic``: the separated guitar + other stems (what the app used: everything but drums and
  vocals; bass and piano are not saved for these songs, so this is close, not identical),
- ``model``: the trained chord model (server/chord_model.py) on the whole mix, what the app uses
  when the model is installed.

Scored the usual way for chord recognition (MIREX "majmin"): root and major/minor must match;
7ths count as their triad, power chords and sus chords as major; beats where the tab has no
chord are left out.

    python -m benchmarks.chords_eval <manifest.json>

The manifest lists songs: {"name": ..., "audio": wav, "harmonic": [wav, ...], "tab": tab.json,
"map": line-up map.json, "skip_tracks": [track numbers that are drums or vocals]}. The songs
are the player's own and stay private; only aggregate scores are reported.

Result (21 Nov 2026, 5 tabbed rock songs, 1,508 beats): majmin 0.53 / root 0.59 on the mix,
0.50 / 0.56 on guitar + other stems. Harmonic-percussive separation, mean instead of median,
bass chroma, CENS, stickier smoothing and no key prior were tried; none beat the current
settings (stickier smoothing and bass chroma were worse). The tab-derived reference is itself
noisy where a part is a riff or arpeggio rather than a strummed chord.
With the trained model (BTC): 0.60 / 0.70 on the mix.
"""
from __future__ import annotations

import json
import sys

import numpy as np

SR = 22050
HOP = 512


def majmin(label):
    """(root, 'maj'|'min') or None for no chord."""
    if label in (None, 'N'):
        return None
    names = {'C': 0, 'C#': 1, 'Db': 1, 'D': 2, 'D#': 3, 'Eb': 3, 'E': 4, 'F': 5, 'F#': 6, 'Gb': 6, 'G': 7,
             'G#': 8, 'Ab': 8, 'A': 9, 'A#': 10, 'Bb': 10, 'B': 11}
    root = label[:2] if label[:2] in names else label[:1]
    quality = label[len(root):]
    return names[root], 'min' if quality.startswith('m') and not quality.startswith('maj') else 'maj'


def tab_chords(notes, beats, end):
    """Chord label per beat from tab notes (pitch classes weighted by how long they sound)."""
    from server import song_analysis as sa
    labels, T = sa.chord_templates()
    names = sa.NAMES_SHARP
    out = []
    edges = list(beats) + [end]
    for a, b in zip(edges[:-1], edges[1:]):
        pc = np.zeros(12)
        for n in notes:
            overlap = min(b, n['time'] + n['duration']) - max(a, n['time'])
            if overlap > 0:
                pc[int(n['midi']) % 12] += overlap * (1.5 if int(n['midi']) < 52 else 1.0)   # bass notes count a bit more
        if np.count_nonzero(pc) < 2:
            out.append('N')
            continue
        v = pc / np.linalg.norm(pc)
        sim = T[1:] @ v
        for i, lab in enumerate(labels[1:]):
            if lab[1] not in ('', 'm'):
                sim[i] -= .06
        lab = labels[1 + int(np.argmax(sim))]
        out.append(names[lab[0]] + lab[1])
    return out


def app_chords(y, beats):
    import librosa
    from server import song_analysis as sa
    cents = sa.estimate_tuning_cents(y, SR)
    chroma = librosa.feature.chroma_cqt(y=y, sr=SR, hop_length=HOP, tuning=cents / 100)
    key = sa.estimate_key(chroma.sum(axis=1))
    frames = np.clip(librosa.time_to_frames(beats, sr=SR, hop_length=HOP), 0, chroma.shape[1] - 1)
    bounds = list(frames) + [chroma.shape[1]]
    synced = np.stack([np.median(chroma[:, a:max(b, a + 1)], axis=1) for a, b in zip(bounds[:-1], bounds[1:])], axis=1)
    return sa.chords_per_beat(synced, key)


def score(pred, ref):
    pairs = [(majmin(p), majmin(r)) for p, r in zip(pred, ref) if majmin(r) is not None]
    if not pairs:
        return None, 0
    root = sum(p is not None and p[0] == r[0] for p, r in pairs) / len(pairs)
    both = sum(p == r for p, r in pairs) / len(pairs)
    return {'majmin': round(both, 3), 'root': round(root, 3)}, len(pairs)


def main(manifest):
    import librosa
    from server import tab_align as ta
    songs = json.load(open(manifest))
    rows = []
    for s in songs:
        mix, _ = librosa.load(s['audio'], sr=SR, mono=True)
        harmonic = sum(librosa.load(f, sr=SR, mono=True)[0][:len(mix)] for f in s['harmonic'])
        harmonic = np.pad(harmonic, (0, max(0, len(mix) - len(harmonic))))
        tab = json.load(open(s['tab']))
        mapping = json.load(open(s['map']))
        tracks = [{'name': t['name'], 'track': t['index'], 'notes': t['notes']} for t in tab['tracks']
                  if t['index'] not in s.get('skip_tracks', [])]
        placed = [n for part in ta.place_tracks(tracks, mapping) for n in part['notes']]
        if not placed:
            continue
        _, beat_frames = librosa.beat.beat_track(y=mix, sr=SR, hop_length=HOP)
        beats = librosa.frames_to_time(beat_frames, sr=SR, hop_length=HOP)
        lo, hi = min(n['time'] for n in placed), max(n['time'] + n['duration'] for n in placed)
        keep = (beats >= lo) & (beats < hi)
        ref = tab_chords(placed, beats, len(mix) / SR)
        row = {'song': s['name']}
        from server import chord_model
        variants = [('mix', mix), ('harmonic', harmonic)]+([('model', mix)] if chord_model.status()[0] else [])
        for name, y in variants:
            pred = chord_model.chords_per_beat(y, beats, len(mix)/SR, SR) if name == 'model' else app_chords(y, beats)
            got, n = score([p for p, k in zip(pred, keep) if k], [r for r, k in zip(ref, keep) if k])
            row[name] = got
            row['beats'] = n
        rows.append(row)
        print(json.dumps(row), flush=True)
    summary = {}
    for name in ('mix', 'harmonic', 'model'):
        scored = [r for r in rows if r.get(name)]
        total = sum(r['beats'] for r in scored)
        summary[name] = {k: round(sum(r[name][k] * r['beats'] for r in scored) / total, 3) for k in ('majmin', 'root')} if total else None
    print('SUMMARY', json.dumps({'songs': len(rows), **summary}))


if __name__ == '__main__':
    main(sys.argv[1])

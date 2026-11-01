"""Accuracy on a real band recording, using the band's own multitrack stems as ground truth.

Give it a folder of stems (one file per recorded track) and a small JSON description saying
which stems are guitars, bass, drums, vocals and keys, plus the true tempo. The script sums
the stems into the mix, sends that mix through the running engine exactly as the app does
(upload -> breakdown -> score), and compares what comes back with the stems:

- instruments: detected present/absent vs which stem groups actually play
- separation: SI-SDR of each separated stem vs the sum of its true stems (higher is better;
  the "raw mix" figure is the score of doing nothing)
- tempo: estimate vs the tempo the band published
- guitar parts: how much of each true guitar track each detected part carries
- notes: the app's guitar notes vs the same transcriber run on the band's isolated guitar
  tracks. This isolates what separation costs; it is not a hand-checked transcription.

Example description (1,000,000.json):
  {"title": "1,000,000", "artist": "Nine Inch Nails", "licence": "CC BY-NC-SA 3.0 US",
   "bpm": 136, "groups": {"guitar": ["Gtr", "Gtr2"], "bass": ["Bass"], "drums": ["Drums", "Tamb"],
   "vocals": ["LV", "BV"], "other": ["Rozz", "Rozz2", "expand"]}}

Run from guitar-lab/ with the engine running on :8000:
  python -m benchmarks.multitrack "/path/to/Audio Files" song.json out_dir
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
import time

import numpy as np
import soundfile as sf

BASE = 'http://127.0.0.1:8000'
HEADERS = {'X-Fretwork-Client': 'studio'}
SR = 44100


def load(path):
    a, sr = sf.read(path, always_2d=True, dtype='float32')
    if sr != SR:
        import librosa
        a = librosa.resample(a.T, orig_sr=sr, target_sr=SR).T
    return a if a.shape[1] == 2 else np.repeat(a[:, :1], 2, axis=1)


def sisdr(est, ref):
    n = min(len(est), len(ref))
    e, r = est[:n].ravel().astype(np.float64), ref[:n].ravel().astype(np.float64)
    if not np.any(r):
        return float('nan')
    a = np.dot(e, r)/np.dot(r, r)
    return float(10*np.log10(np.sum((a*r)**2)/max(np.sum((e-a*r)**2), 1e-12)))


def share(est, ref):
    """Fraction of a true track's energy that ends up in an estimated part (projection)."""
    n = min(len(est), len(ref))
    e, r = est[:n].ravel().astype(np.float64), ref[:n].ravel().astype(np.float64)
    rr = np.dot(r, r)
    return float(max(0.0, np.dot(e, r)/rr)) if rr else 0.0


def stem_files(folder, name):
    hits = [p for p in Path(folder).iterdir() if p.suffix.lower() in ('.flac', '.wav', '.aif', '.aiff')
            and p.stem.split(' ', 1)[-1].lower() == name.lower()]
    if not hits:
        hits = [p for p in Path(folder).iterdir() if p.stem.lower().endswith(' '+name.lower())]
    if len(hits) != 1:
        raise SystemExit(f'Stem "{name}" not found exactly once in {folder}')
    return hits[0]


def run(folder, desc_path, out_dir):
    import httpx
    import mir_eval
    desc = json.loads(Path(desc_path).read_text())
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    stems = {name: load(stem_files(folder, name)) for g in desc['groups'].values() for name in g}
    n = max(len(a) for a in stems.values())
    stems = {k: np.pad(a, ((0, n-len(a)), (0, 0))) for k, a in stems.items()}
    mix = sum(stems.values())
    scale = .95/max(float(np.max(np.abs(mix))), 1e-9)
    mix *= scale
    stems = {k: a*scale for k, a in stems.items()}
    truth = {g: sum(stems[s] for s in names) for g, names in desc['groups'].items()}
    mix_path = out/'mix.flac'
    sf.write(mix_path, mix, SR, subtype='PCM_16')

    http = httpx.Client(timeout=600)
    t0 = time.time()
    r = http.post(f'{BASE}/api/songs', headers=HEADERS, data={'consent': 'true', 'instrument': 'guitar'},
                  files={'file': (mix_path.name, mix_path.open('rb'), 'audio/flac')})
    r.raise_for_status()
    key = r.json()['id']
    while (song := http.get(f'{BASE}/api/songs/{key}').json())['status'] not in ('complete', 'failed'):
        time.sleep(2)
    if song['status'] == 'failed':
        raise SystemExit(song['error'])
    seconds = time.time()-t0
    res = song['result']

    def track(name):
        p = out/f'app_{name}.flac'
        p.write_bytes(http.get(f'{BASE}/api/songs/{key}/tracks/{name}', params={'format': 'flac'}).content)
        return load(p)

    report = {'title': desc['title'], 'artist': desc.get('artist'), 'licence': desc.get('licence'),
              'seconds_to_process': round(seconds, 1), 'duration': round(n/SR, 1)}

    # Instruments
    present_truth = {g for g, a in truth.items() if np.sqrt(np.mean(a**2)) > .005}
    detected = {row['stem']: row['verdict'] for row in res['instruments']}
    report['instruments'] = {g: {'plays': g in present_truth, 'app': detected.get(g, 'n/a')}
                             for g in ('guitar', 'bass', 'drums', 'vocals', 'piano', 'other')
                             if g in truth or g in detected}

    # Separation
    report['separation_si_sdr_db'] = {}
    for g in ('guitar', 'bass', 'drums', 'vocals'):
        if g in truth:
            report['separation_si_sdr_db'][g] = {'raw_mix': round(sisdr(mix, truth[g]), 1),
                                                 'app': round(sisdr(track(g), truth[g]), 1)}

    # Tempo
    report['tempo'] = {'true_bpm': desc.get('bpm'), 'app_bpm': res['tempo']['bpm'],
                       'error_percent': round(100*abs(res['tempo']['bpm']-desc['bpm'])/desc['bpm'], 1)
                       if desc.get('bpm') else None}
    report['key'] = {'app': res['key']['key'] if res['key'] else None, 'true': desc.get('key'),
                     'confidence': res['key']['confidence'] if res['key'] else None}
    report['tuning'] = res['tuning']['suggested'] if res['tuning'] else None

    # Guitar parts: which true guitar track each detected part carries
    parts = {}
    guitars = desc['groups'].get('guitar', [])
    for p in res['parts']:
        audio = track(p['id'])
        parts[p['label']] = {'role': p['role'], 'notes': p['notes'],
                             'lead_bars': [r['bar'] for r in p['roles'] if r['role'] == 'lead'],
                             'carries': {g: round(share(audio, stems[g]), 2) for g in guitars}}
    report['guitar_parts'] = parts

    # Notes: app vs the same transcriber on the band's own guitar tracks
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from server import models
    clean = out/'true_guitar.wav'
    sf.write(clean, truth['guitar'].mean(axis=1), SR, subtype='PCM_16')
    ref_notes = models.transcribe(clean, midi_min=36, midi_max=88)
    app_notes = http.post(f'{BASE}/api/songs/{key}/score', headers=HEADERS,
                          json={'part': 'all', 'role': 'any', 'tuning': 'standard'}).json()['notes']

    def arr(notes):
        if not notes:
            return np.zeros((0, 2)), np.zeros(0)
        return (np.array([[x['time'], x['time']+max(x['duration'], .05)] for x in notes]),
                np.array([440*2**((x['midi']-69)/12) for x in notes]))
    ri, rp = arr(ref_notes)
    ei, ep = arr(app_notes)
    P, R, F, _ = mir_eval.transcription.precision_recall_f1_overlap(ri, rp, ei, ep, offset_ratio=None, onset_tolerance=.05)
    pc = mir_eval.transcription.precision_recall_f1_overlap(
        ri, 440*2**((np.round(12*np.log2(rp/440)) % 12)/12) if len(rp) else rp,
        ei, 440*2**((np.round(12*np.log2(ep/440)) % 12)/12) if len(ep) else ep,
        offset_ratio=None, onset_tolerance=.05)
    report['guitar_notes_vs_isolated_track'] = {'isolated_track_notes': len(ref_notes), 'app_notes': len(app_notes),
                                                'precision': round(P, 2), 'recall': round(R, 2), 'f1': round(F, 2),
                                                'f1_ignoring_octave': round(pc[2], 2)}
    report['chords_first_bars'] = [c['chord'] for c in res['chords'][:16]]
    http.delete(f'{BASE}/api/songs/{key}', headers=HEADERS)
    (out/'report.json').write_text(json.dumps(report, indent=1))
    return report


if __name__ == '__main__':
    if len(sys.argv) != 4:
        raise SystemExit(__doc__)
    print(json.dumps(run(*sys.argv[1:]), indent=1))

"""Shared helpers for the FX training/eval jobs (local only)."""
import sys, copy, json
from collections import Counter, defaultdict
from pathlib import Path
import numpy as np, soundfile as sf, mir_eval, pretty_midi
REPO = Path('/workspace/guitar-lab-test/guitar-lab-fullband/guitar-lab')
sys.path.insert(0, str(REPO))
from server import models
import server.song_analysis as sa
from server.fx.classify import EffectMatcher
from server.fx.undo import undo_effects
SR = 44100
TMP = Path('/workspace/guitar-lab-test/fx_train/tmp'); TMP.mkdir(exist_ok=True, parents=True)

def load(path, max_s=None, offset=0.0, mono=True):
    info = sf.info(path)
    start = int(offset * info.samplerate); stop = None if max_s is None else start + int(max_s * info.samplerate)
    y, sr = sf.read(path, start=start, stop=stop, dtype='float32', always_2d=True)
    if mono: y = y.mean(axis=1)
    if sr != SR:
        import librosa
        y = librosa.resample(y.T if not mono else y, orig_sr=sr, target_sr=SR)
        if not mono: y = y.T
    return y.astype(np.float32)

def transcribe_audio(y, name, tone):
    p = TMP / f'{name}.wav'
    sf.write(p, y, SR, subtype='PCM_16')
    th = models.thresholds_for(tone, chosen_by_user=False)
    notes = models.transcribe(str(p), midi_min=36, midi_max=88, thresholds=th)
    p.unlink(missing_ok=True)
    return notes

def post(notes, tone, dur, bpm=120.0, suppress=True):
    notes = copy.deepcopy(notes)
    if suppress:
        notes = sa.suppress_harmonic_ghosts(notes, tone=tone, window=.15)
        bars = list(np.arange(0, dur + 240 / bpm, 240 / bpm))
        roles = sa.bar_roles(notes, bars, dur)
        notes = sa.drop_overtones(notes, roles, window=.15, tone=tone)
    return notes

def tone_of(y):
    t = sa.tone_estimate(y, SR)['tone']
    return 'distorted' if t == 'uncertain' else t

def midi_notes(path, program_filter=None):
    pm = pretty_midi.PrettyMIDI(str(path))
    out = []
    for inst in pm.instruments:
        if inst.is_drum: continue
        for n in inst.notes:
            out.append({'time': n.start, 'duration': n.end - n.start, 'midi': n.pitch, 'velocity': n.velocity})
    return sorted(out, key=lambda n: n['time'])

def f1(est, ref, tol=0.05, shift=0.0, pitch=True):
    if not est or not ref: return {'p': 0.0, 'r': 0.0, 'f1': 0.0, 'n_ref': len(ref), 'n_est': len(est)}
    hz = lambda p: 440 * 2 ** ((np.asarray(p, float) - 69) / 12)
    r_on = np.array([n['time'] for n in ref]); r_iv = np.c_[r_on, r_on + np.maximum([n['duration'] for n in ref], .05)]
    e_on = np.maximum(np.array([n['time'] for n in est]) + shift, 0); e_iv = np.c_[e_on, e_on + np.maximum([n['duration'] for n in est], .05)]
    if pitch:
        P, R, F, _ = mir_eval.transcription.precision_recall_f1_overlap(r_iv, hz([n['midi'] for n in ref]), e_iv, hz([n['midi'] for n in est]), onset_tolerance=tol, offset_ratio=None)
    else:
        P, R, F = mir_eval.onset.f_measure(np.unique(np.round(r_on, 3)), np.unique(np.round(e_on, 3)), window=tol)
    return {'p': round(P, 3), 'r': round(R, 3), 'f1': round(F, 3), 'n_ref': len(ref), 'n_est': len(est)}

def best_shift(est, ref, lo=-1.0, hi=1.0, step=0.01):
    best = (0, -1)
    for s in np.arange(lo, hi + 1e-9, step):
        v = f1(est, ref, 0.05, s)['f1']
        if v > best[1]: best = (round(float(s), 3), v)
    return best[0]

def chord_stats(notes, window=.05):
    g = defaultdict(set)
    for n in notes: g[round(n['time'] / window)].add(n['midi'])
    h = Counter(len(v) for v in g.values()); n = len(g)
    return {'n_notes': len(notes), 'n_onsets': n, 'frac_chord': round(sum(c for k, c in h.items() if k >= 2) / n, 3) if n else 0.0}

_M = None
def defx(y):
    global _M
    _M = _M or EffectMatcher()
    det = _M.predict(y, SR)
    return undo_effects(y, SR, effects=det['effects']).astype(np.float32), det

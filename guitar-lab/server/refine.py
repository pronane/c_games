"""Revise a guitar transcription until playing it back matches the target audio.

The loop is: transcribe, render with the Karplus–Strong guitar voice, compare that
rendering to the target, then try a few explainable edits (add, remove, shift,
repitch, a harmonic-ghost check, or a short re-transcription at another threshold).
An edit is kept only when it raises the score on its own region and on the whole
file. The best transcription seen is returned, which is never worse than pass 1.

Off unless the caller asks. The HTTP API also requires FRETWORK_REFINE=1.
Notation is not run through this loop: those notes are already exact.

Timing, measured here on the synthetic 8-note line (4.1 s, Karplus–Strong):
pass 1 note F1 0.67, four edits, final note F1 1.00, match score 0.69 → 0.90,
about 0.4 s. A correct first pass that already scores at the target returns in
one comparison. A long real stem stops at `max_seconds` (default 20) or 5
iterations. The absolute score on a real amp take is not the synthetic ceiling:
the renderer is Karplus–Strong, so only the rise in score is meaningful.
"""
from __future__ import annotations

import os
from pathlib import Path
import tempfile
import time

import numpy as np
from scipy import signal

SR = 22050
N_FFT = 2048
HOP = 256
# One global lag, in frames. 3 frames is about 35 ms: enough to absorb the
# analysis window, not enough to hide a note that is on the wrong beat.
MAX_LAG = 3
AUDIO_WEIGHT = 0.85
NOTE_WEIGHT = 0.15
ALT_THRESHOLDS = ((0.5, 0.3), (0.45, 0.25), (0.7, 0.5), (0.35, 0.2))
_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']


def refine_enabled():
    return os.getenv('FRETWORK_REFINE', '0') == '1'


def refinement_gate(instrument, requested, notation=False):
    """Why the loop must not run, or None when it should. Shared by the job and song APIs."""
    if notation:
        return 'notation reference is exact'
    if not requested:
        return 'not requested'
    if instrument != 'guitar':
        return 'refinement is guitar-only'
    if not refine_enabled():
        return 'FRETWORK_REFINE is not set'
    return None


def skipped_refinement(reason, requested=False):
    return {
        'enabled': False, 'requested': bool(requested), 'skipped': reason,
        'original_score': None, 'final_score': None, 'best_score': None,
        'stopped': 'skipped', 'elapsed_seconds': 0.0, 'iterations': [],
    }


def combine_refinements(logs):
    """One refinement object for several guitar parts. A single log is returned as-is."""
    logs = [l for l in logs if l]
    if not logs:
        return skipped_refinement('not requested')
    if len(logs) == 1:
        return logs[0]
    enabled = [l for l in logs if l.get('enabled')]
    if not enabled:
        out = dict(logs[0])
        out['parts'] = logs
        return out

    def avg(key):
        vals = [l[key] for l in enabled if isinstance(l.get(key), (int, float))]
        return round(sum(vals) / len(vals), 4) if vals else None

    iterations = []
    for log in logs:
        for step in log.get('iterations') or []:
            iterations.append(dict(step, part=log.get('part')))
    return {
        'enabled': True, 'requested': True, 'skipped': None,
        'original_score': avg('original_score'), 'final_score': avg('final_score'),
        'best_score': avg('best_score'),
        'stopped': enabled[-1].get('stopped'),
        'elapsed_seconds': round(sum(float(l.get('elapsed_seconds') or 0) for l in logs), 3),
        'iterations': iterations, 'parts': logs,
    }


def _note_name(midi):
    midi = int(midi)
    return f'{_NAMES[midi % 12]}{midi // 12 - 1}'


def _default_transcribe(path, thresholds=None, midi_min=40, midi_max=88):
    from . import models
    return models.transcribe(path, midi_min=midi_min, midi_max=midi_max, thresholds=thresholds)


def _call_transcribe(fn, path, thresholds, midi_min, midi_max):
    try:
        return fn(path, thresholds=thresholds, midi_min=midi_min, midi_max=midi_max)
    except TypeError:
        return fn(path)


def load_mono(path, sr=SR):
    import soundfile as sf
    audio, file_sr = sf.read(path, always_2d=True, dtype='float32')
    y = np.asarray(audio, dtype=np.float64).mean(axis=1)
    if file_sr != sr and len(y):
        import librosa
        y = librosa.resample(y, orig_sr=file_sr, target_sr=sr).astype(np.float64)
    return y, sr


def render_guitar(notes, sr=SR, length_s=1.0, seed=0):
    """Place transcription notes (`time` or `start`) on the Karplus–Strong voice.

    The seed is restored afterwards. The same notes and seed render the same audio,
    so a comparison against a render of the true notes is meaningful.
    """
    from .fx.undo import acoustic_playback
    play = []
    for n in notes or []:
        midi = n.get('midi', n.get('pitch'))
        if midi is None:
            continue
        start = float(n.get('start', n.get('time', n.get('onset', 0.0))))
        if 'duration' in n:
            dur = float(n['duration'])
        elif 'end' in n:
            dur = float(n['end']) - start
        else:
            dur = 0.3
        vel = float(n.get('velocity', n.get('amplitude', 0.7)))
        play.append({
            'midi': int(round(float(midi))), 'start': max(0.0, start),
            'duration': max(0.04, dur), 'velocity': float(np.clip(vel if vel <= 1.5 else vel / 5.0, 0.05, 1.0)),
            'damping': bool(n.get('damping', n.get('palm_mute', False))),
        })
    state = np.random.get_state()
    np.random.seed(int(seed))
    try:
        return acoustic_playback(play, sr=sr, length_s=max(0.05, float(length_s)))
    finally:
        np.random.set_state(state)


def _weights(midi_min, midi_max, n_fft, sr):
    key = (midi_min, midi_max, n_fft, sr)
    cached = _weights.cache.get(key)
    if cached is not None:
        return cached
    freqs = np.fft.rfftfreq(n_fft, 1.0 / sr)
    rows = midi_max - midi_min + 1
    W = np.zeros((rows, len(freqs)), dtype=np.float64)
    for i, midi in enumerate(range(midi_min, midi_max + 1)):
        f0 = 440.0 * 2 ** ((midi - 69) / 12.0)
        lo, hi = f0 * 2 ** (-0.5 / 12.0), f0 * 2 ** (0.5 / 12.0)
        idx = np.where((freqs >= lo) & (freqs < hi))[0]
        if len(idx) == 0:
            idx = np.array([int(np.argmin(np.abs(freqs - f0)))])
        W[i, idx] = 1.0 / len(idx)
    _weights.cache[key] = W
    return W


_weights.cache = {}


def _features(y, sr, midi_min, midi_max):
    """Chroma, constant-Q (semitone) magnitude, and note-onset activation.

    Semitone bands are a constant-Q magnitude: each row is one semitone wide.
    Onset activation is the positive change in that magnitude. Both stay in
    NumPy so a revision can be scored without a second CQT filterbank.
    """
    y = np.ascontiguousarray(np.asarray(y, dtype=np.float64).reshape(-1))
    if len(y) < N_FFT:
        y = np.pad(y, (0, N_FFT - len(y)))
    _freqs, times, Z = signal.stft(
        y, fs=sr, nperseg=N_FFT, noverlap=N_FFT - HOP, window='hann', boundary=None, padded=False)
    mag = np.abs(Z)
    W = _weights(midi_min, midi_max, N_FFT, sr)
    if W.shape[1] != mag.shape[0]:
        cols = min(W.shape[1], mag.shape[0])
        S = W[:, :cols] @ mag[:cols]
    else:
        S = W @ mag
    S = np.maximum(S, 0.0)
    flux = np.maximum(0.0, np.diff(np.log1p(S), axis=1, prepend=np.log1p(S[:, :1])))
    chroma = np.zeros((12, S.shape[1]), dtype=np.float64)
    for i in range(S.shape[0]):
        chroma[(midi_min + i) % 12] += S[i]
    return {'S': S, 'flux': flux, 'chroma': chroma, 'times': np.asarray(times, dtype=np.float64)}


def _shift(a, b, lag):
    if lag < 0:
        return a[:, -lag:], b[:, :b.shape[1] + lag]
    if lag > 0:
        return a[:, :a.shape[1] - lag], b[:, lag:]
    return a, b


def _cosine(a, b):
    n = min(a.shape[1], b.shape[1])
    if n <= 0:
        return 1.0
    a, b = a[:, :n], b[:, :n]
    na = np.linalg.norm(a, axis=0)
    nb = np.linalg.norm(b, axis=0)
    mask = (na > 1e-6) | (nb > 1e-6)
    if not np.any(mask):
        return 1.0
    num = np.sum(a[:, mask] * b[:, mask], axis=0)
    den = na[mask] * nb[mask] + 1e-12
    return float(np.mean(num / den))


def audio_similarity(render_y, target_feats, sr, midi_min, midi_max, region=None):
    """Onset-aligned chroma, constant-Q magnitude, and note-activation agreement.

    `region` is (t0, t1) in seconds. The returned number is in 0..1.
    """
    if region is not None:
        t0, t1 = region
        a, b = max(0, int(t0 * sr)), max(0, int(t1 * sr))
        b = min(len(render_y), max(b, a + N_FFT))
        render_y = render_y[a:b]
        # Target features were computed on the full file; recompute the slice so
        # the two sides share a clock. Slicing frames would cross the window.
        target_y = target_feats.get('_audio')
        if target_y is None:
            return 0.0
        target_feats = _features(target_y[a:min(len(target_y), b)], sr, midi_min, midi_max)
    feats = _features(render_y, sr, midi_min, midi_max)
    best = 0.0
    for lag in range(-MAX_LAG, MAX_LAG + 1):
        chroma = _cosine(*_shift(feats['chroma'], target_feats['chroma'], lag))
        cqt = _cosine(*_shift(feats['S'], target_feats['S'], lag))
        act = _cosine(*_shift(feats['flux'], target_feats['flux'], lag))
        score = 0.40 * chroma + 0.35 * cqt + 0.25 * act
        if score > best:
            best = score
    return float(best)


def _harmonic_score(flux):
    score = np.array(flux, dtype=np.float64, copy=True)
    for shift, weight in ((12, 0.85), (19, 0.55), (24, 0.45)):
        if shift < score.shape[0]:
            score[:-shift] += weight * flux[shift:]
    return score


def target_events(feats, midi_min, strength=0.24, min_gap=0.12):
    """Note attacks heard in the target: time, midi, strength. Monophonic bias.

    A second pitch is not emitted when it is an octave, fifth, or octave-plus-fifth
    of the fundamental, so a single pluck does not become a chord of its partials.
    """
    score = _harmonic_score(feats['flux'])
    if score.size == 0 or not np.isfinite(score).any():
        return []
    peak = float(np.max(score))
    if peak <= 0:
        return []
    times = feats['times']
    env = score.max(axis=0)
    thr = strength * peak
    gap = max(1, int(round(min_gap / (HOP / SR))))
    chosen = []
    for i in range(1, len(env) - 1):
        if env[i] < thr or env[i] < env[i - 1] or env[i] < env[i + 1]:
            continue
        if chosen and i - chosen[-1] < gap:
            if env[i] > env[chosen[-1]]:
                chosen[-1] = i
            continue
        chosen.append(i)
    events = []
    for i in chosen:
        midi = midi_min + int(np.argmax(score[:, i]))
        events.append({'time': float(times[i]), 'midi': midi, 'strength': float(env[i])})
    return events


def note_agreement(reference, candidate, duration):
    """PR #47 take-vs-target comparison against a re-transcription of the target.

    The reference note list is the first-pass transcription of the target audio.
    `compare_to_target` scores pitch, timing and completeness on onset DTW.
    The returned value is that overall score scaled to 0..1. `duration` is unused;
    the comparison uses the note times themselves.
    """
    del duration
    from .compare import compare_to_target
    if not reference and not candidate:
        return 1.0
    if not reference:
        return 0.0
    report = compare_to_target(candidate, {
        'source': 'stem',
        'notes': reference,
        'label': 'Re-transcription of the target',
        'bpm': 120,
    })
    overall = report['summary']['overall']
    if overall is None:
        return 1.0 if not candidate else 0.0
    return float(overall) / 100.0


def _normalise(notes, duration, midi_min, midi_max):
    out = []
    for n in notes or []:
        midi = n.get('midi', n.get('pitch'))
        if midi is None:
            continue
        midi = int(round(float(midi)))
        if not midi_min <= midi <= midi_max:
            continue
        start = float(n.get('time', n.get('start', n.get('onset', 0.0))))
        if 'duration' in n:
            dur = float(n['duration'])
        elif 'end' in n:
            dur = float(n['end']) - start
        else:
            dur = 0.3
        if start >= duration or dur <= 0:
            continue
        start = max(0.0, start)
        dur = max(0.04, min(dur, max(0.04, duration - start)))
        amp = float(n.get('amplitude', n.get('velocity', 0.65)))
        if amp > 1.5:
            amp = amp / 5.0
        out.append({
            'time': start, 'duration': dur, 'midi': midi,
            'amplitude': float(np.clip(amp, 0.05, 1.0)),
        })
    out.sort(key=lambda n: (n['time'], n['midi']))
    for i, n in enumerate(out):
        n['id'] = i
    return out


def _public(notes):
    notes = sorted(notes, key=lambda n: (n['time'], n['midi']))
    return [{
        'id': i,
        'time': round(float(n['time']), 4),
        'duration': round(float(n['duration']), 4),
        'midi': int(n['midi']),
        'amplitude': round(float(n['amplitude']), 4),
    } for i, n in enumerate(notes)]


def _copy(notes):
    return [dict(n) for n in notes]


def _proposals(notes, events, duration):
    """Small, named edits. Each one changes a single note, or drops one ghost."""
    unused = set(range(len(events)))
    matched = {}
    for i, n in enumerate(notes):
        same = [(abs(events[j]['time'] - n['time']), j) for j in unused
                if events[j]['midi'] == n['midi'] and abs(events[j]['time'] - n['time']) <= 0.22]
        if not same:
            continue
        j = min(same)[1]
        unused.discard(j)
        matched[i] = j
    for i, n in enumerate(notes):
        if i in matched:
            continue
        other = [(abs(events[j]['time'] - n['time']), j) for j in unused
                 if abs(events[j]['time'] - n['time']) <= 0.12]
        if not other:
            continue
        j = min(other)[1]
        unused.discard(j)
        matched[i] = j

    props = []
    for i, n in enumerate(notes):
        if i not in matched:
            props.append({
                'kind': 'remove', 'index': i,
                'span': (n['time'] - 0.2, n['time'] + n['duration'] + 0.15),
                'text': f"removed {_note_name(n['midi'])} at {n['time']:.2f}s (no attack of that pitch in the original)",
            })
            continue
        event = events[matched[i]]
        if event['midi'] != n['midi']:
            props.append({
                'kind': 'repitch', 'index': i, 'midi': event['midi'],
                'span': (n['time'] - 0.2, n['time'] + n['duration'] + 0.15),
                'text': (f"changed {_note_name(n['midi'])} to {_note_name(event['midi'])} "
                         f"at {n['time']:.2f}s"),
            })
        elif abs(event['time'] - n['time']) >= 0.04:
            props.append({
                'kind': 'shift', 'index': i, 'time': event['time'],
                'span': (min(n['time'], event['time']) - 0.15, max(n['time'], event['time']) + n['duration'] + 0.1),
                'text': (f"shifted {_note_name(n['midi'])} from {n['time']:.2f}s to {event['time']:.2f}s"),
            })
    median = float(np.median([n['duration'] for n in notes])) if notes else 0.3
    for j in sorted(unused, key=lambda j: -events[j]['strength']):
        event = events[j]
        if any(abs(n['time'] - event['time']) < 0.08 and n['midi'] == event['midi'] for n in notes):
            continue
        props.append({
            'kind': 'add', 'time': event['time'], 'midi': event['midi'], 'duration': median,
            'span': (event['time'] - 0.15, event['time'] + median + 0.15),
            'text': f"added {_note_name(event['midi'])} at {event['time']:.2f}s",
        })
    # One harmonic-ghost candidate: a higher partial with no attack of its own.
    for i, n in enumerate(notes):
        if any(abs(event['time'] - n['time']) <= 0.08 and event['midi'] == n['midi'] for event in events):
            continue
        lower = [m for m in notes if abs(n['time'] - m['time']) <= 0.04 and n['midi'] - m['midi'] in (12, 19, 24)]
        if not lower:
            continue
        props.append({
            'kind': 'remove', 'index': i,
            'span': (n['time'] - 0.15, n['time'] + n['duration'] + 0.1),
            'text': f"removed harmonic ghost {_note_name(n['midi'])} at {n['time']:.2f}s",
        })
        break
    order = {'repitch': 0, 'remove': 1, 'add': 2, 'shift': 3}
    props.sort(key=lambda p: order.get(p['kind'], 9))
    # Deduplicate identical descriptions so a ghost and a plain remove are not tried twice.
    seen, unique = set(), []
    for prop in props:
        if prop['text'] in seen:
            continue
        seen.add(prop['text'])
        unique.append(prop)
    return unique[:6]


def _apply(notes, prop, duration):
    trial = _copy(notes)
    kind = prop['kind']
    if kind == 'remove':
        trial.pop(prop['index'])
    elif kind == 'repitch':
        trial[prop['index']]['midi'] = int(prop['midi'])
    elif kind == 'shift':
        note = trial[prop['index']]
        note['time'] = float(np.clip(prop['time'], 0.0, max(0.0, duration - 0.05)))
        note['duration'] = min(note['duration'], max(0.04, duration - note['time']))
    elif kind == 'add':
        start = float(np.clip(prop['time'], 0.0, max(0.0, duration - 0.05)))
        dur = min(float(prop['duration']), max(0.04, duration - start))
        trial.append({'time': start, 'duration': dur, 'midi': int(prop['midi']), 'amplitude': 0.7, 'id': -1})
    elif kind == 'replace':
        t0, t1 = prop['span']
        kept = [n for n in trial if not (t0 - 1e-4 <= n['time'] < t1)]
        trial = kept + _normalise(prop['notes'], duration, 0, 127)
    else:
        return None
    for i, n in enumerate(sorted(trial, key=lambda n: (n['time'], n['midi']))):
        n['id'] = i
    return sorted(trial, key=lambda n: (n['time'], n['midi']))


def _region_transcription(target, sr, notes, t0, t1, thresholds, transcribe, midi_min, midi_max, duration):
    if transcribe is None or t1 - t0 < 0.35:
        return None
    a, b = max(0, int(t0 * sr)), min(len(target), int(t1 * sr))
    if b - a < int(0.35 * sr):
        return None
    fd, name = tempfile.mkstemp(suffix='.wav')
    os.close(fd)
    path = Path(name)
    try:
        import soundfile as sf
        sf.write(path, np.asarray(target[a:b], dtype=np.float32), sr)
        found = _call_transcribe(transcribe, path, thresholds, midi_min, midi_max) or []
    except Exception:
        return None
    finally:
        path.unlink(missing_ok=True)
    shifted = []
    for n in found:
        item = dict(n)
        item['time'] = float(n.get('time', n.get('start', 0.0))) + t0
        shifted.append(item)
    old = {(round(n['time'], 2), n['midi']) for n in notes if t0 - 1e-4 <= n['time'] < t1}
    new = {(round(n['time'], 2), int(round(n['midi']))) for n in shifted}
    diff = old.symmetric_difference(new)
    if not diff or len(diff) > 4:
        return None
    onset, frame = thresholds if thresholds else (None, None)
    label = (f"re-transcribed {t0:.2f}–{t1:.2f}s"
             + (f" at onset {onset:.2f} / frame {frame:.2f}" if onset is not None else ""))
    return {
        'kind': 'replace', 'notes': shifted, 'span': (t0, t1),
        'text': f"{label} ({len(diff)} note edits)",
    }


def _worst_window(render_y, target_feats, sr, midi_min, midi_max, duration, width=1.2):
    feats = _features(render_y, sr, midi_min, midi_max)
    n = min(feats['chroma'].shape[1], target_feats['chroma'].shape[1])
    if n < 4:
        return 0.0, min(duration, width)
    a = feats['chroma'][:, :n]
    b = target_feats['chroma'][:, :n]
    na = np.linalg.norm(a, axis=0)
    nb = np.linalg.norm(b, axis=0)
    per = np.sum(a * b, axis=0) / (na * nb + 1e-12)
    times = target_feats['times'][:n]
    best, start = 1.0, 0.0
    t = 0.0
    while t < duration - 0.2:
        sel = (times >= t) & (times < t + width)
        if int(sel.sum()) >= 3:
            mean = float(np.mean(per[sel]))
            if mean < best:
                best, start = mean, t
        t += 0.4
    return start, min(duration, start + width)


def _score_pair(notes, render_y, scorer):
    audio = audio_similarity(render_y, scorer['target_feats'], scorer['sr'], scorer['midi_min'], scorer['midi_max'])
    notes_s = note_agreement(scorer['reference'], notes, scorer['duration'])
    return AUDIO_WEIGHT * audio + NOTE_WEIGHT * notes_s, audio, notes_s


def refine_transcription(audio_path, options=None, **kwargs):
    """Transcribe `audio_path` and revise until the rendering stops getting closer.

    `options` (or keyword arguments): `notes` (first pass; skips the opening
    transcription), `transcribe`, `midi_min`, `midi_max`, `max_iterations` (5),
    `max_seconds` (20), `target_score` (0.97), `min_improvement` (0.008),
    `tone`, `on_progress`, `seed`.

    Returns `{notes, refinement}`. `refinement` is the iteration log.
    """
    opts = dict(options or {})
    opts.update(kwargs)
    started = time.perf_counter()
    midi_min = int(opts.get('midi_min', 40))
    midi_max = int(opts.get('midi_max', 88))
    max_iterations = max(0, int(opts.get('max_iterations', 5)))
    max_seconds = float(opts.get('max_seconds', 20))
    target_score = float(opts.get('target_score', 0.97))
    min_delta = float(opts.get('min_improvement', 0.008))
    min_local = float(opts.get('min_local', 0.004))
    on_progress = opts.get('on_progress') or (lambda _msg: None)
    transcribe = opts.get('transcribe') or _default_transcribe
    seed = int(opts.get('seed', 0))
    tone = opts.get('tone') or 'clean'

    y, sr = load_mono(audio_path, SR)
    duration = len(y) / sr if sr else 0.0
    if duration <= 0:
        empty = skipped_refinement('the target audio is empty', requested=True)
        empty['enabled'] = True
        empty['stopped'] = 'empty audio'
        return {'notes': [], 'refinement': empty}

    if opts.get('notes') is None:
        first = _call_transcribe(transcribe, audio_path, None, midi_min, midi_max)
    else:
        first = opts.get('notes')
    notes = _normalise(first, duration, midi_min, midi_max)
    reference = _copy(notes)
    target_feats = _features(y, sr, midi_min, midi_max)
    target_feats['_audio'] = y
    events = target_events(target_feats, midi_min)
    scorer = {
        'target_feats': target_feats, 'reference': reference, 'sr': sr,
        'midi_min': midi_min, 'midi_max': midi_max, 'duration': duration, 'events': events,
    }

    def render(current):
        return render_guitar(current, sr=sr, length_s=duration, seed=seed)

    current_y = render(notes)
    total, audio_s, note_s = _score_pair(notes, current_y, scorer)
    best_notes, best_total, best_y = _copy(notes), total, current_y
    original = total
    iterations = [{
        'iteration': 0, 'score': round(total, 4), 'audio_score': round(audio_s, 4),
        'note_score': round(note_s, 4), 'changes': 0, 'changed': [], 'action': 'first pass',
    }]
    stopped = 'iteration cap'
    on_progress(f'Refining guitar transcription, pass 1/{max_iterations} · match {total:.0%}')

    def overtime():
        return (time.perf_counter() - started) >= max_seconds

    if overtime():
        stopped = 'time cap'
    elif total >= target_score:
        stopped = 'target score'
    else:
        for iteration in range(1, max_iterations + 1):
            if overtime():
                stopped = 'time cap'
                break
            if best_total >= target_score:
                stopped = 'target score'
                break
            on_progress(f'Refining guitar transcription, pass {iteration}/{max_iterations} · match {best_total:.0%}')
            changed = []
            action = 'revise mismatches'
            # Up to two kept edits this pass, each re-scored. A third would be a
            # new iteration, so the log stays a short list of what actually moved.
            for _round in range(2):
                if overtime():
                    stopped = 'time cap'
                    break
                props = _proposals(notes, events, duration)
                t0, t1 = _worst_window(current_y, target_feats, sr, midi_min, midi_max, duration)
                thresholds = ALT_THRESHOLDS[(iteration + _round - 1) % len(ALT_THRESHOLDS)]
                region = _region_transcription(
                    y, sr, notes, t0, t1, thresholds, transcribe, midi_min, midi_max, duration)
                if region is not None:
                    props.append(region)
                from .song_analysis import suppress_harmonic_ghosts
                cleaned = _normalise(suppress_harmonic_ghosts(notes, tone=tone), duration, midi_min, midi_max)
                if [(n['time'], n['midi']) for n in cleaned] != [(n['time'], n['midi']) for n in notes]:
                    dropped = len(notes) - len(cleaned)
                    # A harmonic pass that rewrites the line is not a small edit.
                    if 0 < dropped <= 3:
                        props.append({
                            'kind': 'replace', 'notes': cleaned,
                            'span': (min(n['time'] for n in notes), max(n['time'] for n in notes) + 0.4),
                            'text': f're-ran harmonic-ghost check ({tone}), removed {dropped}',
                        })
                best_prop, best_trial, best_seen = None, None, best_total
                local_cache = {}
                for prop in props:
                    if overtime():
                        stopped = 'time cap'
                        break
                    trial = _apply(notes, prop, duration)
                    if trial is None:
                        continue
                    trial_y = render(trial)
                    gain_total, _a, _n = _score_pair(trial, trial_y, scorer)
                    if gain_total < best_total + min_delta or gain_total <= best_seen:
                        continue
                    span = prop['span']
                    span = (max(0.0, span[0]), min(duration, max(span[0] + 0.2, span[1])))
                    key = (round(span[0], 3), round(span[1], 3))
                    if key not in local_cache:
                        local_cache[key] = audio_similarity(
                            current_y, target_feats, sr, midi_min, midi_max, region=span)
                    local_after = audio_similarity(
                        trial_y, target_feats, sr, midi_min, midi_max, region=span)
                    if local_after < local_cache[key] + min_local:
                        continue
                    best_prop = prop
                    best_trial = (trial, trial_y, gain_total)
                    best_seen = gain_total
                if best_prop is None:
                    break
                notes, current_y, total = best_trial
                if total > best_total:
                    best_total = total
                    best_notes = _copy(notes)
                    best_y = current_y
                changed.append(best_prop['text'])
                if best_prop['kind'] == 'replace' and 're-transcribed' in best_prop['text']:
                    action = 're-transcribe a mismatched region'
                elif best_prop['text'].startswith('re-ran'):
                    action = 're-ran harmonic checks'
            _total, audio_s, note_s = _score_pair(best_notes, best_y if changed else current_y, scorer)
            # Report the best score, which is the transcription we would return.
            iterations.append({
                'iteration': iteration, 'score': round(best_total, 4),
                'audio_score': round(audio_s, 4), 'note_score': round(note_s, 4),
                'changes': len(changed), 'changed': changed, 'action': action if changed else 'no improvement',
            })
            if stopped == 'time cap':
                break
            if not changed:
                stopped = 'no improvement'
                break
            if best_total >= target_score:
                stopped = 'target score'
                break
        else:
            stopped = 'iteration cap'

    # Never hand back a transcription that scores below pass 1, even if a later
    # comparison disagrees with the running best by a rounding error.
    final_y = render(best_notes)
    final_total, final_audio, final_note = _score_pair(best_notes, final_y, scorer)
    if final_total + 1e-9 < original:
        best_notes = reference
        final_total, final_audio, final_note = _score_pair(best_notes, render(best_notes), scorer)
        stopped = 'reverted to first pass'
    elapsed = time.perf_counter() - started
    log = {
        'enabled': True, 'requested': True, 'skipped': None,
        'original_score': round(float(original), 4),
        'final_score': round(float(final_total), 4),
        'best_score': round(float(max(final_total, best_total, original)), 4),
        'stopped': stopped,
        'elapsed_seconds': round(elapsed, 3),
        'iterations': iterations,
        'events_heard': len(events),
        'tone': tone,
        'note_reference': 're-transcription of the target, scored with compare_to_target',
    }
    on_progress(
        f'Guitar transcription refined · match {log["original_score"]:.0%} → {log["final_score"]:.0%} · {stopped}')
    return {'notes': _public(best_notes), 'refinement': log}

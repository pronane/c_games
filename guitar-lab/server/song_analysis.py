"""Whole-song breakdown: instrument presence, guitar parts, key, tempo, tuning, chords,
lead/rhythm roles, string/fret fingering and MusicXML. Pure functions; no model loading.

Everything here is an estimate. Callers must present results as suggestions the player can
correct, never as verified transcriptions.
"""
from __future__ import annotations

import itertools
import math
from xml.sax.saxutils import escape

import numpy as np

NAMES_SHARP = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
NAMES_FLAT = ['C', 'Db', 'D', 'Eb', 'E', 'F', 'Gb', 'G', 'Ab', 'A', 'Bb', 'B']
HARMONIC_STEMS = ('guitar', 'bass', 'piano', 'other')


# ---------------------------------------------------------------- audio helpers

def mono(audio):
    audio = np.asarray(audio, dtype=np.float32)
    return audio.mean(axis=1) if audio.ndim == 2 else audio


def frame_rms(y, sr, seconds=.5):
    hop = max(1, int(sr*seconds))
    n = max(1, len(y)//hop)
    return np.sqrt(np.array([np.mean(y[i*hop:(i+1)*hop]**2) for i in range(n)]) + 1e-20)


def presence(stems: dict, sr: int, reference_peak: float):
    """Energy share and active time of each separated stem -> present / trace / absent."""
    energies = {k: float(np.mean(np.asarray(v, dtype=np.float64)**2)) for k, v in stems.items()}
    total = sum(energies.values()) or 1.0
    rows = []
    for name, audio in stems.items():
        share = energies[name]/total
        active = float(np.mean(frame_rms(mono(audio), sr) > .02*max(reference_peak, 1e-6)))
        verdict = 'present' if share > .03 and active > .2 else ('trace' if share > .005 else 'absent')
        rows.append({'stem': name, 'energy_share': share, 'active_fraction': active, 'verdict': verdict})
    return sorted(rows, key=lambda r: -r['energy_share'])


# ---------------------------------------------------------------- multiple guitars

def pan_parts(stem, sr, min_share=.06, min_active=.1):
    """Split one stereo stem into left / centre / right parts with soft panning masks.

    Many records pan two guitars hard left and right. Parts that sit at the same position
    cannot be separated this way; that limitation is reported to the user.
    Returns [(name, audio, share)] that sum back to the stem.
    """
    import librosa
    stem = np.asarray(stem, dtype=np.float32)
    if stem.ndim != 2 or stem.shape[1] != 2 or np.allclose(stem[:, 0], stem[:, 1], atol=1e-4):
        return [('centre', stem, 1.0)]
    n_fft, hop = 4096, 1024
    L = librosa.stft(stem[:, 0], n_fft=n_fft, hop_length=hop)
    R = librosa.stft(stem[:, 1], n_fft=n_fft, hop_length=hop)
    aL, aR = np.abs(L), np.abs(R)
    pan = (aR-aL)/(aR+aL+1e-9)                     # -1 hard left .. +1 hard right
    left = np.clip((-pan-.25)/.35, 0, 1)
    right = np.clip((pan-.25)/.35, 0, 1)
    centre = 1-left-right
    parts = []
    total = float(np.sum(aL**2+aR**2)) or 1.0
    peak = float(np.max(np.abs(stem))) or 1.0
    for name, mask in (('left', left), ('centre', centre), ('right', right)):
        share = float(np.sum((aL**2+aR**2)*mask**2))/total
        y = np.stack([librosa.istft(L*mask, hop_length=hop, length=len(stem)),
                      librosa.istft(R*mask, hop_length=hop, length=len(stem))], axis=1).astype(np.float32)
        active = float(np.mean(frame_rms(mono(y), sr) > .03*peak))
        parts.append((name, y, share, active))
    kept = [p for p in parts if p[2] >= min_share and p[3] >= min_active]
    if len(kept) <= 1:
        return [('centre', stem, 1.0)]
    # Fold weak parts into the nearest kept part so the parts still sum to the stem.
    order = ['left', 'centre', 'right']
    out = {p[0]: p[1].copy() for p in kept}
    for name, y, _, _ in parts:
        if name not in out:
            nearest = min(out, key=lambda k: abs(order.index(k)-order.index(name)))
            out[nearest] += y
    shares = {p[0]: p[2] for p in parts}
    return [(k, out[k], shares[k]) for k in order if k in out]


def bar_levels(audio, sr, edges):
    """RMS of a part in each bar (edges in seconds, len = bars+1)."""
    y = mono(audio)
    out = []
    for a, b in zip(edges[:-1], edges[1:]):
        seg = y[max(0, int(a*sr)):max(0, int(b*sr))]
        out.append(float(np.sqrt(np.mean(seg.astype(np.float64)**2))) if len(seg) else 0.0)
    return out


def shared_fraction(notes, other, start, end, window=.08):
    """Share of `notes` in [start, end) echoed by `other` at the same pitch and moment."""
    mine = [n for n in notes if start <= n['time'] < end]
    if not mine:
        return 0.0
    theirs = [m for m in other if start-window <= m['time'] < end+window]
    hits = sum(any(m['midi'] == n['midi'] and abs(m['time']-n['time']) < window for m in theirs) for n in mine)
    return hits/len(mine)


def bleed_bars(levels: dict, notes: dict, edges, faint=.08, quieter=.45, shared=.4, overlap=.6):
    """Mark bars where a pan part only carries bleed from another part.

    Soft panning masks leak: a hard-right lead leaks into the centre while the left guitar
    plays too, and a centre lead leaks a quieter copy into a side. A bar is bleed when the
    part is (a) almost silent next to the loudest part, (b) much quieter than another part
    and repeating its exact pitches, or (c) the centre, quieter than both sides together
    (time-frequency overlap of left and right lands in the centre mask).
    Returns {part: [bool per bar]}.
    """
    parts = list(levels)
    nb = len(edges)-1
    out = {p: [False]*nb for p in parts}
    for i in range(nb):
        lv = {p: levels[p][i] for p in parts}
        loudest = max(lv.values()) or 1e-12
        for p in parts:
            if lv[p] < faint*loudest:
                out[p][i] = True
                continue
            if p == 'centre' and 'left' in lv and 'right' in lv and lv[p] < overlap*min(lv['left'], lv['right']):
                out[p][i] = True
                continue
            for q in parts:
                if q != p and lv[p] < quieter*lv[q] and \
                        shared_fraction(notes.get(p, []), notes.get(q, []), edges[i], edges[i+1]) >= shared:
                    out[p][i] = True
                    break
    return out


def chroma_similarity(a, b, sr):
    import librosa
    ca = librosa.feature.chroma_stft(y=mono(a), sr=sr, hop_length=2048)
    cb = librosa.feature.chroma_stft(y=mono(b), sr=sr, hop_length=2048)
    n = min(ca.shape[1], cb.shape[1])
    ca, cb = ca[:, :n].ravel(), cb[:, :n].ravel()
    return float(np.dot(ca, cb)/(np.linalg.norm(ca)*np.linalg.norm(cb)+1e-9))


# ---------------------------------------------------------------- tempo, bars, key, tuning

def beat_grid(rhythm_audio, sr, bass_audio=None, harmonic_audio=None):
    """Beat times plus a 4/4 bar grid.

    The downbeat is the beat phase where the harmony changes most (chords usually change on
    beat one), helped by bass attacks. Bass or kick alone is ambiguous when they hit every beat.
    """
    import librosa
    y = mono(rhythm_audio)
    tempo, beats = librosa.beat.beat_track(y=y, sr=sr, units='time', trim=False)
    tempo = float(np.atleast_1d(tempo)[0])
    beats = np.asarray(beats, dtype=float)
    if len(beats) < 8 or not tempo:
        period = 60/120
        beats = np.arange(0, len(y)/sr, period)
        tempo = 120.0
    else:
        # Beat trackers jitter by a few percent, which drifts bar numbers over a song. When the
        # beats fit a straight line well (steady tempo, e.g. played to a click) use the fit.
        idx = np.arange(len(beats))
        slope, intercept = np.polyfit(idx, beats, 1)
        if np.max(np.abs(beats-(slope*idx+intercept))) < .25*slope:
            beats = slope*idx+intercept
            beats = beats[beats >= -1e-3]
    phase = downbeat_phase(beats, sr, bass_audio, harmonic_audio) if len(beats) >= 8 else 0
    # Extend the grid backwards so the first bar starts at or before 0 s.
    period = float(np.median(np.diff(beats))) if len(beats) > 1 else 60/tempo
    beats = beats[phase:] if phase else beats
    # Prepend whole bars until the grid starts at or before 0 s (a pickup bar may start < 0).
    while beats[0] > .05:
        beats = np.concatenate([beats[0]-period*np.arange(4, 0, -1), beats])
    bars = beats[::4]
    return {'bpm': round(60/period, 1), 'beats': [float(b) for b in beats], 'bars': [float(b) for b in bars],
            'time_signature': '4/4', 'note': 'Beat and bar grid estimated; 4/4 assumed.'}


def downbeat_phase(beats, sr, bass_audio=None, harmonic_audio=None):
    """Which of the four beat phases is beat one: harmonic change + bass attack evidence."""
    import librosa
    score = np.zeros(4)
    if harmonic_audio is not None:
        chroma = librosa.feature.chroma_cqt(y=mono(harmonic_audio), sr=sr, hop_length=512)
        frames = np.clip(librosa.time_to_frames(beats, sr=sr, hop_length=512), 0, chroma.shape[1]-1)
        bounds = list(frames)+[chroma.shape[1]]
        synced = np.stack([chroma[:, a:max(b, a+1)].mean(axis=1) for a, b in zip(bounds[:-1], bounds[1:])], axis=1)
        unit = synced/(np.linalg.norm(synced, axis=0, keepdims=True)+1e-9)
        change = np.concatenate([[0.], 1-np.sum(unit[:, 1:]*unit[:, :-1], axis=0)])
        per = np.array([change[p::4].mean() for p in range(4)])
        if per.max() > 0:
            score += per/per.max()
    if bass_audio is not None:
        env = librosa.onset.onset_strength(y=mono(bass_audio), sr=sr, hop_length=512)
        idx = np.clip(librosa.time_to_frames(beats, sr=sr, hop_length=512), 0, len(env)-1)
        per = np.array([env[idx][p::4].mean() for p in range(4)])
        if per.max() > 0:
            score += .5*per/per.max()
    return int(np.argmax(score))


KRUMHANSL_MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
KRUMHANSL_MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
MAJOR_FIFTHS = {0: 0, 7: 1, 2: 2, 9: 3, 4: 4, 11: 5, 6: 6, 5: -1, 10: -2, 3: -3, 8: -4, 1: -5}


def key_name(tonic, mode):
    fifths = key_fifths(tonic, mode)
    names = NAMES_FLAT if fifths < 0 else NAMES_SHARP
    if mode == 'major' and tonic == 6:
        names = NAMES_SHARP
    return f"{names[tonic]} {mode}"


def key_fifths(tonic, mode):
    major = tonic if mode == 'major' else (tonic+3) % 12
    return MAJOR_FIFTHS[major]


def estimate_key(chroma_profile):
    """Krumhansl-Schmuckler key finding. Relative major/minor confusion is common."""
    c = np.asarray(chroma_profile, dtype=float)
    if c.sum() <= 0:
        return None
    scores = []
    for tonic in range(12):
        for mode, prof in (('major', KRUMHANSL_MAJOR), ('minor', KRUMHANSL_MINOR)):
            scores.append((float(np.corrcoef(c, np.roll(prof, tonic))[0, 1]), tonic, mode))
    scores.sort(reverse=True)
    best, second = scores[0], scores[1]
    margin = best[0]-second[0]
    return {'key': key_name(best[1], best[2]), 'tonic': best[1], 'mode': best[2],
            'fifths': key_fifths(best[1], best[2]), 'correlation': best[0],
            'confidence': 'high' if margin > .08 and best[0] > .7 else ('moderate' if best[0] > .55 else 'low'),
            'alternatives': [key_name(s[1], s[2]) for s in scores[1:3]]}


def estimate_tuning_cents(harmonic_audio, sr):
    """Deviation of the recording from A4 = 440 Hz, in cents (-50..+50)."""
    import librosa
    y = mono(harmonic_audio)
    if np.sqrt(np.mean(y**2)) < 1e-4:
        return 0.0
    return float(100*librosa.estimate_tuning(y=y, sr=sr, bins_per_octave=12))


def suggest_tuning(notes, cents, tunings: dict, flats=False):
    """Suggest a tuning from the lowest notes actually played and the reference offset.

    Audio alone cannot tell some tunings apart (drop D and D standard sound identical on a
    D5 power chord), so every plausible option is returned with the evidence.
    """
    pitches = sorted(n['midi'] for n in notes if n.get('amplitude', 1) >= .25)
    lowest = None
    if pitches:
        # Ignore isolated transcription glitches: need the pitch at least twice.
        counts = {}
        for p in pitches:
            counts[p] = counts.get(p, 0)+1
        repeated = [p for p in sorted(counts) if counts[p] >= 2] or pitches
        lowest = repeated[0]
    options = []
    for name, strings in tunings.items():
        low = min(strings)
        if lowest is not None and lowest < low:
            continue
        # Prefer the tuning whose lowest string equals the lowest played note, then standard.
        score = (0 if lowest is not None and lowest == low else 1, 0 if name == 'standard' else 1,
                 abs((lowest or low)-low))
        options.append((score, name))
    options.sort()
    names = [n for _, n in options]
    if not names:
        names = [min(tunings, key=lambda k: min(tunings[k]))]
    best = names[0]
    reasons = []
    if lowest is not None:
        reasons.append(f"Lowest repeated note heard: {(NAMES_FLAT if flats else NAMES_SHARP)[lowest % 12]}{lowest//12-1}.")
    if lowest is not None and lowest < min(tunings.get('standard', [lowest])):
        reasons.append('That is below standard tuning, so the guitar was tuned down.')
    ambiguous = [n for n in names[1:] if min(tunings[n]) == min(tunings[best])]
    if ambiguous:
        reasons.append('These sound the same on most chords; pick the one the original player used if you know it: '
                       + ', '.join([best]+ambiguous).replace('_', ' ')+'.')
    reference = round(440*2**(cents/1200), 1)
    if abs(cents) >= 15:
        reasons.append(f"The recording sits {cents:+.0f} cents from A440 (A4 = {reference} Hz). "
                       'Tune every string to that reference to play along in tune.')
    return {'suggested': best, 'options': names, 'lowest_midi': lowest, 'reference_cents': round(cents, 1),
            'reference_a4_hz': reference, 'reasons': reasons,
            'confidence': 'moderate' if lowest is not None else 'low'}


# ---------------------------------------------------------------- chords

QUALITIES = {'': (0, 4, 7), 'm': (0, 3, 7), '7': (0, 4, 7, 10), 'maj7': (0, 4, 7, 11), 'm7': (0, 3, 7, 10),
             'sus2': (0, 2, 7), 'sus4': (0, 5, 7), '5': (0, 7)}


def chord_templates():
    labels, rows = ['N'], [np.full(12, 1/12)]
    for root in range(12):
        for q, ints in QUALITIES.items():
            t = np.zeros(12)
            for i in ints:
                t[(root+i) % 12] = 1
            labels.append((root, q))
            rows.append(t/np.linalg.norm(t))
    return labels, np.array(rows)


def chords_per_beat(chroma_beats, key=None, self_prob=.6):
    """Template matching + Viterbi smoothing over beats. chroma_beats: (12, n_beats)."""
    import librosa
    labels, T = chord_templates()
    C = np.asarray(chroma_beats, dtype=float)
    energy = C.sum(axis=0)
    norm = C/(np.linalg.norm(C, axis=0, keepdims=True)+1e-9)
    sim = T@norm                                     # (n_labels, n_beats)
    sim[0] = .55                                     # "no chord" baseline
    sim[0, energy < .05*np.max(energy+1e-9)] = 1.5
    # Simple qualities are more common: small prior against 7ths/sus/power.
    for i, lab in enumerate(labels[1:], 1):
        if lab[1] not in ('', 'm'):
            sim[i] -= .1 if lab[1] == '5' else .06
    # Key prior: distortion and bright guitars add harmonics (the 5th harmonic of E is G#),
    # which pull minor chords toward major. Penalise chord tones outside the key's scale;
    # strong evidence (e.g. a major V in a minor key) still wins.
    if key is not None and 'tonic' in key:
        major_tonic = key['tonic'] if key.get('mode') == 'major' else (key['tonic']+3) % 12
        scale = {(major_tonic+s) % 12 for s in (0, 2, 4, 5, 7, 9, 11)}
        for i, lab in enumerate(labels[1:], 1):
            outside = sum((lab[0]+s) % 12 not in scale for s in QUALITIES[lab[1]])
            sim[i] -= .05*outside
    prob = np.exp(12*sim)
    prob /= prob.sum(axis=0, keepdims=True)
    n = len(labels)
    trans = np.full((n, n), (1-self_prob)/(n-1))
    np.fill_diagonal(trans, self_prob)
    path = librosa.sequence.viterbi(prob, trans)
    flats = key is not None and key.get('fifths', 0) < 0
    names = NAMES_FLAT if flats else NAMES_SHARP
    out = []
    for i in path:
        lab = labels[i]
        out.append('N' if lab == 'N' else names[lab[0]]+lab[1])
    return out


def resolve_mode(key, segments):
    """Relative major and minor share every note, so profiles alone often pick the wrong one.
    Use the harmony: the key is the one whose tonic chord opens the song or lasts longest."""
    if not key or not segments:
        return key
    rel_tonic = (key['tonic']+9) % 12 if key['mode'] == 'major' else (key['tonic']+3) % 12
    rel_mode = 'minor' if key['mode'] == 'major' else 'major'
    flats = key.get('fifths', 0) < 0
    names = NAMES_FLAT if flats else NAMES_SHARP
    own = names[key['tonic']]+('' if key['mode'] == 'major' else 'm')
    rel = names[rel_tonic]+('m' if rel_mode == 'minor' else '')
    def time(ch):
        return sum(s['end']-s['start'] for s in segments if s['chord'] == ch)
    first = next((s['chord'] for s in segments if s['chord'] != 'N'), None)
    if (first == rel and time(rel) >= .8*time(own)) or time(rel) > 1.25*time(own):
        alternatives = [key['key']]+[a for a in key.get('alternatives', []) if a != key_name(rel_tonic, rel_mode)]
        return dict(key, key=key_name(rel_tonic, rel_mode), tonic=rel_tonic, mode=rel_mode,
                    fifths=key_fifths(rel_tonic, rel_mode), alternatives=alternatives[:2],
                    basis='tonic chord from the harmony (relative major/minor share the same notes)')
    return key


def chord_segments(beat_labels, beats):
    segs = []
    for i, lab in enumerate(beat_labels):
        if segs and segs[-1]['chord'] == lab:
            segs[-1]['end'] = beats[i+1] if i+1 < len(beats) else segs[-1]['end']
            continue
        segs.append({'chord': lab, 'start': beats[i], 'end': beats[i+1] if i+1 < len(beats) else beats[i]+.5})
    return segs


# ---------------------------------------------------------------- lead / rhythm roles

def onset_groups(notes, window=.04):
    groups = []
    for n in sorted(notes, key=lambda n: (n['time'], n['midi'])):
        if groups and n['time']-groups[-1][0]['time'] <= window:
            groups[-1].append(n)
        else:
            groups.append([n])
    return groups


def bar_edges(bars, end_time):
    return list(bars)+[max(end_time, bars[-1]+1e-3 if bars else end_time)]


def bar_roles(notes, bars, end_time, bleed=None):
    """Label each bar lead / rhythm / mixed / rest from note texture.

    Rhythm: mostly chords or power chords (2+ notes struck together). Lead: mostly single
    notes in the upper register. Bars flagged in `bleed` are 'rest' (the part is silent and
    only carries leakage from another part there).
    """
    edges = bar_edges(bars, end_time)
    out = []
    for i in range(len(edges)-1):
        a, b = edges[i], edges[i+1]
        if bleed is not None and i < len(bleed) and bleed[i]:
            out.append({'bar': i+1, 'start': float(a), 'end': float(b), 'role': 'rest', 'notes': 0, 'bleed': True})
            continue
        inside = [n for n in notes if a <= n['time'] < b]
        groups = onset_groups(inside)
        if len(groups) < 2:
            # A lone single note is usually a tail ringing over from the previous bar.
            role = 'rhythm' if groups and len(groups[0]) >= 3 else 'rest'
        else:
            chordal = sum(len(g) >= 2 for g in groups)/len(groups)
            single = sum(len(g) == 1 for g in groups)/len(groups)
            high = np.median([n['midi'] for n in inside]) >= 59
            role = 'rhythm' if chordal >= .5 else ('lead' if single >= .7 and high else
                                                   'rhythm' if single >= .7 and not high else 'mixed')
        out.append({'bar': i+1, 'start': float(a), 'end': float(b), 'role': role, 'notes': len(inside)})
    return out


def drop_overtones(notes, roles, window=.05):
    """Remove octave / octave-and-fifth ghosts in lead bars.

    Overdriven single-note lines produce strong 2nd/3rd harmonics that the transcriber
    reports as extra notes struck together with the real one. In lead bars a note exactly
    12, 19 or 24 semitones above another note at the same moment is treated as a ghost.
    Chords in rhythm bars are left alone (octave doublings there are real).
    """
    lead = [(r['start'], r['end']) for r in roles if r['role'] == 'lead']
    def in_lead(t):
        return any(a <= t < b for a, b in lead)
    keep = []
    for n in notes:
        if in_lead(n['time']) and any(m is not n and abs(m['time']-n['time']) < window and n['midi']-m['midi'] in (12, 19, 24)
                                      for m in notes):
            continue
        keep.append(n)
    return keep


def summarise_roles(roles):
    counts = {}
    for r in roles:
        if r['role'] != 'rest':
            counts[r['role']] = counts.get(r['role'], 0)+1
    if not counts:
        return 'silent'
    top = max(counts, key=counts.get)
    total = sum(counts.values())
    return top if counts[top]/total >= .65 else 'lead and rhythm'


# ---------------------------------------------------------------- fingering

def _assignments(pitches, strings, max_fret, limit=24):
    """All ways to place a chord's pitches on distinct strings."""
    options = []
    per = []
    for p in pitches:
        cand = [(s, p-o) for s, o in enumerate(strings) if 0 <= p-o <= max_fret]
        if not cand:
            return []
        per.append(cand)
    for combo in itertools.product(*per):
        used = [s for s, _ in combo]
        if len(set(used)) != len(used):
            continue
        frets = [f for _, f in combo if f > 0]
        span = (max(frets)-min(frets)) if frets else 0
        if span > 5:
            continue
        options.append(combo)
        if len(options) >= 400:
            break
    def static(c):
        frets = [f for _, f in c if f > 0]
        return (max(frets)-min(frets) if frets else 0, sum(f for _, f in c))
    options.sort(key=static)
    return options[:limit]


# Fingering weights (per note): cost of fret height, extra cost above fret 12, cost per fret
# of hand movement between notes, and a penalty for leaps of more than four frets.
# Tuned on GuitarSet (360 real performances): exact string+fret 38.5% -> 43.8% on solos,
# 74.0% -> 79.1% on chord playing, versus the original hand-set weights (.12, .25, .8, 2).
FRET_COST, HIGH_FRET_COST, MOVE_COST, LEAP_COST = 0.0, .2, .4, 0.0


def fingering(notes, open_strings, max_fret=24):
    """Choose string/fret for every note with a Viterbi pass that minimises hand movement.

    String numbers follow tab convention: 1 = highest-pitched string.
    Notes that cannot be placed (out of range for the tuning) get string/fret None.
    """
    if not open_strings:
        return [dict(n, string=None, fret=None) for n in notes]
    groups = onset_groups(notes)
    states = []
    for g in groups:
        g = sorted(g, key=lambda n: n['midi'])[:len(open_strings)]
        opts = _assignments([n['midi'] for n in g], open_strings, max_fret) or [None]
        states.append((g, opts))

    def position(c):
        frets = [f for _, f in c if f > 0] if c else []
        return float(np.mean(frets)) if frets else None

    def local_cost(c):
        if c is None:
            return 50.0
        frets = [f for _, f in c if f > 0]
        span = (max(frets)-min(frets)) if frets else 0
        # Prefer lower positions (most tab is written there) and avoid the top of the neck.
        return .4*span+FRET_COST*sum(f for _, f in c)/len(c)+HIGH_FRET_COST*sum(max(0, f-12) for _, f in c)/len(c) \
            + (1.5*span if span > 4 else 0)

    cost = [local_cost(c) for c in states[0][1]] if states else []
    back = []
    for k in range(1, len(states)):
        prev_opts, opts = states[k-1][1], states[k][1]
        new_cost, ptr = [], []
        for c in opts:
            pc = position(c)
            best, arg = math.inf, 0
            for j, p in enumerate(prev_opts):
                pp = position(p)
                move = abs(pc-pp) if pc is not None and pp is not None else 0
                # Capped so one stray high note cannot drag a whole phrase up the neck.
                v = cost[j]+MOVE_COST*min(move, 7)+(LEAP_COST if move > 4 else 0)
                if v < best:
                    best, arg = v, j
            new_cost.append(best+local_cost(c))
            ptr.append(arg)
        cost = new_cost
        back.append(ptr)
    choice = [0]*len(states)
    if states:
        choice[-1] = int(np.argmin(cost))
        for k in range(len(states)-1, 0, -1):
            choice[k-1] = back[k-1][choice[k]]
    out = []
    for (g, opts), ci in zip(states, choice):
        c = opts[ci]
        placed = {id(n): (c[i] if c else None) for i, n in enumerate(g)}
        for n in g:
            sf = placed.get(id(n))
            out.append(dict(n, string=(sf[0]+1) if sf else None, fret=sf[1] if sf else None))
    # Notes dropped from over-full chords keep no tab position.
    seen = {(n['time'], n['midi']) for n in out}
    for n in notes:
        if (n['time'], n['midi']) not in seen:
            out.append(dict(n, string=None, fret=None))
    return sorted(out, key=lambda n: (n['time'], n['midi']))


# ---------------------------------------------------------------- notation (MusicXML)

DURATIONS = [(16, 'whole', 0), (12, 'half', 1), (8, 'half', 0), (6, 'quarter', 1), (4, 'quarter', 0),
             (3, 'eighth', 1), (2, 'eighth', 0), (1, '16th', 0)]


def split_duration(units):
    """Decompose a length in 16ths into notatable values (tied together by the caller)."""
    parts = []
    while units > 0:
        for d, name, dots in DURATIONS:
            if d <= units:
                parts.append((d, name, dots))
                units -= d
                break
    return parts


def time_to_sixteenths(t, beats):
    beats = np.asarray(beats, dtype=float)
    if len(beats) < 2:
        return int(round(t*8))
    period = beats[1]-beats[0]
    if t <= beats[0]:
        pos = (t-beats[0])/period
    elif t >= beats[-1]:
        pos = len(beats)-1+(t-beats[-1])/(beats[-1]-beats[-2])
    else:
        pos = float(np.interp(t, beats, np.arange(len(beats))))
    return int(round(pos*4))


def spell(midi, flats):
    names = NAMES_FLAT if flats else NAMES_SHARP
    name = names[midi % 12]
    return name[0], (1 if '#' in name else -1 if 'b' in name else 0), midi//12-1


def musicxml(notes, beats, key, tuning, title='Transcription', part_name='Guitar', chords=None,
             tab=True, clef='treble8vb', max_bars=400):
    """Single-staff MusicXML with optional string/fret technical marks for a TAB view.

    Notes are quantised to a 16th grid that follows the estimated beat times, merged into
    chords by onset and written in one voice. Expressive detail (bends, slides, dynamics,
    tuplets) is not transcribed.
    """
    fifths = (key or {}).get('fifths', 0)
    flats = fifths < 0
    if tab and tuning:
        # A note with no string/fret can't sit on a tab staff, and notation viewers (alphaTab)
        # fail to draw the score when given one. Callers report how many were left out.
        notes = [n for n in notes if n.get('string') and n.get('fret') is not None]
    events = {}
    for n in notes:
        s = max(0, time_to_sixteenths(n['time'], beats))
        e = max(s+1, time_to_sixteenths(n['time']+n['duration'], beats))
        events.setdefault(s, []).append((n, e))
    starts = sorted(events)
    if not starts:
        total = 16
    else:
        total = max(e for evs in events.values() for _, e in evs)
    bars = min(max_bars, max(1, math.ceil(total/16)))
    harmony = {}
    for c in chords or []:
        if c['chord'] != 'N':
            harmony.setdefault(max(0, time_to_sixteenths(c['start'], beats)), c['chord'])

    # Timeline of (start, length, [notes]) where length runs to the next onset or note end.
    timeline = []
    for i, s in enumerate(starts):
        nxt = starts[i+1] if i+1 < len(starts) else None
        end = max(e for _, e in events[s])
        if nxt is not None:
            end = min(end, nxt)
        timeline.append((s, max(1, end-s), [n for n, _ in events[s]]))

    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 4.0 Partwise//EN" '
           '"http://www.musicxml.org/dtds/partwise.dtd">',
           '<score-partwise version="4.0">',
           f'<work><work-title>{escape(title)}</work-title></work>',
           '<identification><encoding><software>Guitar Lab</software></encoding>'
           '<miscellaneous><miscellaneous-field name="note">Automatic transcription estimate; check by ear.'
           '</miscellaneous-field></miscellaneous></identification>',
           f'<part-list><score-part id="P1"><part-name>{escape(part_name)}</part-name></score-part></part-list>',
           '<part id="P1">']
    bpm = 60/float(np.median(np.diff(beats))) if len(beats) > 1 else 120
    emitted = set()
    ti = 0
    for bar in range(bars):
        bar_start, bar_end = bar*16, bar*16+16
        out.append(f'<measure number="{bar+1}">')
        if bar == 0:
            out.append('<attributes><divisions>4</divisions>'
                       f'<key><fifths>{fifths}</fifths><mode>{(key or {}).get("mode", "major")}</mode></key>'
                       '<time><beats>4</beats><beat-type>4</beat-type></time>')
            if clef == 'bass':
                out.append('<clef><sign>F</sign><line>4</line></clef>')
            elif clef == 'treble':
                out.append('<clef><sign>G</sign><line>2</line></clef>')
            else:
                out.append('<clef><sign>G</sign><line>2</line><clef-octave-change>-1</clef-octave-change></clef>')
            if tab and tuning:
                out.append(f'<staff-details><staff-lines>{len(tuning)}</staff-lines>')
                for line, midi in enumerate(reversed(tuning), 1):
                    step, alter, octave = spell(midi, flats)
                    alt = f'<tuning-alter>{alter}</tuning-alter>' if alter else ''
                    out.append(f'<staff-tuning line="{line}"><tuning-step>{step}</tuning-step>{alt}'
                               f'<tuning-octave>{octave}</tuning-octave></staff-tuning>')
                out.append('</staff-details>')
            out.append('</attributes>')
            out.append(f'<direction placement="above"><direction-type><metronome><beat-unit>quarter</beat-unit>'
                       f'<per-minute>{round(bpm)}</per-minute></metronome></direction-type>'
                       f'<sound tempo="{round(bpm)}"/></direction>')
        pos = bar_start
        while pos < bar_end:
            # Chord symbols attach to the next written note or rest; one per position.
            due = [h for h in harmony if h not in emitted and h < pos+1]
            if due:
                out.append(_harmony_xml(harmony[max(due)]))
                emitted.update(due)
            # carry-over of a note tied from the previous bar
            if ti < len(timeline) and timeline[ti][0] < pos < timeline[ti][0]+timeline[ti][1]:
                s, length, group = timeline[ti]
                seg = min(s+length, bar_end)-pos
                out += _note_group(group, seg, flats, tie_start=s+length > bar_end, tie_stop=True, tab=tab)
                pos += seg
                if s+length <= pos:
                    ti += 1
                continue
            if ti < len(timeline) and timeline[ti][0] == pos:
                s, length, group = timeline[ti]
                seg = min(length, bar_end-pos)
                out += _note_group(group, seg, flats, tie_start=s+length > bar_end, tie_stop=False, tab=tab)
                pos += seg
                if s+length <= pos:
                    ti += 1
                continue
            nxt = timeline[ti][0] if ti < len(timeline) else bar_end
            nxt_h = min([h for h in harmony if pos < h < bar_end and h not in emitted], default=bar_end)
            rest = min(nxt, bar_end, nxt_h)-pos
            for d, name, dots in split_duration(rest):
                out.append(f'<note><rest/><duration>{d}</duration><type>{name}</type>{"<dot/>"*dots}</note>')
            pos += rest
        out.append('</measure>')
    out.append('</part></score-partwise>')
    return '\n'.join(out)


def _harmony_xml(name):
    root = name[0]
    alter = 1 if name[1:2] == '#' else -1 if name[1:2] == 'b' else 0
    quality = name[1+(alter != 0):]
    kind = {'': 'major', 'm': 'minor', '7': 'dominant', 'maj7': 'major-seventh', 'm7': 'minor-seventh',
            'sus2': 'suspended-second', 'sus4': 'suspended-fourth', '5': 'power'}.get(quality, 'major')
    alt = f'<root-alter>{alter}</root-alter>' if alter else ''
    return (f'<harmony><root><root-step>{root}</root-step>{alt}</root>'
            f'<kind text="{escape(quality)}">{kind}</kind></harmony>')


def _note_group(group, length, flats, tie_start, tie_stop, tab):
    xml = []
    pieces = split_duration(length)
    for pi, (d, name, dots) in enumerate(pieces):
        start_tie = tie_start or pi < len(pieces)-1
        stop_tie = tie_stop or pi > 0
        for ni, n in enumerate(sorted(group, key=lambda n: n['midi'])):
            step, alter, octave = spell(n['midi'], flats)
            ties = (('<tie type="stop"/>' if stop_tie else '')+('<tie type="start"/>' if start_tie else ''))
            tied = (('<tied type="stop"/>' if stop_tie else '')+('<tied type="start"/>' if start_tie else ''))
            tech = ''
            if tab and n.get('string') and n.get('fret') is not None:
                tech = f'<technical><string>{n["string"]}</string><fret>{n["fret"]}</fret></technical>'
            notations = f'<notations>{tied}{tech}</notations>' if (tied or tech) else ''
            alt = f'<alter>{alter}</alter>' if alter else ''
            xml.append(f'<note>{"<chord/>" if ni else ""}<pitch><step>{step}</step>{alt}<octave>{octave}</octave></pitch>'
                       f'<duration>{d}</duration>{ties}<type>{name}</type>{"<dot/>"*dots}{notations}</note>')
    return xml


# ---------------------------------------------------------------- where is this take?

def locate(reference, take, sr, bars, hop=1024, top=3):
    """Find where a take sits inside a (much longer) reference part.

    Subsequence DTW over CENS chroma (robust to timbre, dynamics and small tempo drift),
    so the player's guitar does not need to sound like the record. Repeated sections give
    several near-equal matches; up to `top` non-overlapping candidates are returned, each
    with its start time, nearest bar and an uncalibrated similarity in 0..1.
    """
    import librosa
    ref, tk = mono(reference), mono(take)
    if len(tk) < sr*2:
        raise ValueError('The take is shorter than 2 seconds; record or upload at least a bar.')
    if len(tk) > len(ref):
        raise ValueError('The take is longer than the song.')
    X = librosa.feature.chroma_cens(y=ref, sr=sr, hop_length=hop)
    Y = librosa.feature.chroma_cens(y=tk, sr=sr, hop_length=hop)
    if not np.any(Y > 0) or not np.any(X > 0):
        raise ValueError('No pitched notes found to match.')
    # Cosine distance with silent frames (e.g. outside the chosen lead bars) costing 1.
    def unit(M):
        norms = np.linalg.norm(M, axis=0, keepdims=True)
        return np.divide(M, norms, out=np.zeros_like(M), where=norms > 1e-9)
    C_full = 1-unit(Y).T@unit(X)
    D, path = librosa.sequence.dtw(C=C_full, subseq=True)
    costs = D[-1, :]/Y.shape[1]                       # per-frame cost of a match ending here
    order = np.argsort(costs)
    length = Y.shape[1]
    picks = []
    for end in order:
        if not np.isfinite(costs[end]):
            continue
        if any(abs(end-p) < length*.75 for p in picks):
            continue
        picks.append(int(end))
        if len(picks) == top*4:
            break
    edges = np.asarray(bars, dtype=float)
    out = []
    for end in picks:
        _, wp = librosa.sequence.dtw(C=C_full[:, :end+1], subseq=True)
        start_frame = int(wp[-1, 1])                   # path is reversed: last row is the start
        start = librosa.frames_to_time(start_frame, sr=sr, hop_length=hop)
        bar = int(np.argmin(np.abs(edges-start)))+1 if len(edges) else None
        snapped = float(edges[bar-1]) if bar and abs(edges[bar-1]-start) < .35 else float(start)
        if any(o['bar'] == bar and abs(o['raw_start']-start) < 1.0 for o in out):
            continue                                   # same place reached by another path
        out.append({'start': snapped, 'raw_start': float(start), 'bar': bar,
                    'similarity': float(max(0.0, 1-costs[end]))})
        if len(out) == top:
            break
    best = out[0] if out else None
    confidence = 'low'
    if best and best['similarity'] > .8:
        confidence = 'high' if len(out) < 2 or best['similarity']-out[1]['similarity'] > .05 else 'repeated'
    elif best and best['similarity'] > .65:
        confidence = 'moderate'
    return {'candidates': out, 'confidence': confidence,
            'note': 'Matched on harmony. Repeated sections (choruses) match equally well; pick the right one.'}

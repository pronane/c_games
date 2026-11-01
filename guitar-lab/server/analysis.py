"""Musical alignment + conservative note-event observations, not technique diagnoses."""
import numpy as np

SR = 22050
HOP = 512
SAME_PITCH_WINDOW = .4    # seconds; a correct note this far off is a timing finding
OTHER_PITCH_WINDOW = .12  # seconds; a different pitch must sit close to count as a wrong note
TIMING_TOLERANCE = .1     # seconds after latency compensation


def align(reference, take, sr=SR):
    import librosa
    a = librosa.resample(np.asarray(reference), orig_sr=sr, target_sr=SR)
    b = librosa.resample(np.asarray(take), orig_sr=sr, target_sr=SR)
    if np.sqrt(np.mean(a*a)) < .0001 or np.sqrt(np.mean(b*b)) < .0001:
        raise ValueError('Reference or take is silent; alignment is not meaningful.')
    # Harmonic component limits percussive contamination, but does not isolate guitars.
    ca = librosa.feature.chroma_stft(y=librosa.effects.harmonic(a), sr=SR, hop_length=HOP)
    cb = librosa.feature.chroma_stft(y=librosa.effects.harmonic(b), sr=SR, hop_length=HOP)
    ca = ca + 1e-8
    cb = cb + 1e-8
    costs, path = librosa.sequence.dtw(X=ca, Y=cb, metric='cosine', global_constraints=True, band_rad=.25)
    path = path[::-1]
    # For each take frame, take the median corresponding reference time.
    mapping = np.array([[j*HOP/SR, np.median(path[path[:, 1] == j, 0])*HOP/SR]
                        for j in np.unique(path[:, 1])])
    cost = float(costs[-1, -1]/len(path))
    offsets = mapping[:, 1]-mapping[:, 0]
    slope = float(np.polyfit(mapping[:, 0], mapping[:, 1], 1)[0]) if len(mapping)>1 else 1.
    return {'map': mapping[::max(1, len(mapping)//300)].tolist(), 'mean_chroma_cost': cost,
            'confidence': 'low' if cost > .35 else 'moderate',
            'median_offset_seconds': float(np.median(offsets)), 'reference_seconds_per_take_second': slope,
            'warning': 'Uncalibrated similarity, not a probability. Repeated chords, silence and separation artefacts can misalign. Offsets include recording latency.'}


def observations(reference_notes, take_notes, alignment):
    mapping = np.array(alignment['map'])
    # Constant offset (mostly recording latency) estimated by alignment; used only to label
    # timing differences, never to hide them: raw_timing_seconds is still reported.
    latency = -float(alignment.get('median_offset_seconds', 0.0) or 0.0)
    used = set()
    findings = []
    # Same-pitch one-to-one matching first, in a wider window than different-pitch matching,
    # so a late/early correct note is reported as timing rather than as a wrong pitch.
    # Never grade fretting pressure from this.
    for take in sorted(take_notes, key=lambda n: n['time']):
        mapped = float(np.interp(take['time'], mapping[:, 0], mapping[:, 1]))
        nominal = take['time']-latency

        def distance(r):
            return min(abs(r['time']-mapped), abs(r['time']-nominal))
        same = [(distance(r), i, r) for i, r in enumerate(reference_notes)
                if i not in used and r['midi'] == take['midi'] and distance(r) <= SAME_PITCH_WINDOW]
        other = [(distance(r), i, r) for i, r in enumerate(reference_notes)
                 if i not in used and distance(r) <= OTHER_PITCH_WINDOW]
        match = min(same or other, key=lambda x: x[0]) if same or other else None
        if match is None:
            findings.append({'kind': 'unmatched_take', 'take_time': take['time'], 'take_midi': take['midi'],
                             'detail': 'No nearby reference event; could be an extra note or transcription/alignment error.'})
            continue
        _, i, ref = match
        used.add(i)
        compensated = take['time']-latency-ref['time']
        kind = 'pitch_difference' if ref['midi'] != take['midi'] else (
            'timing_difference' if abs(compensated) > TIMING_TOLERANCE+1e-6 else 'matched')
        findings.append({'kind': kind,
                         'take_time': take['time'], 'reference_time': ref['time'],
                         'take_midi': take['midi'], 'reference_midi': ref['midi'],
                         'raw_timing_seconds': take['time']-ref['time'],
                         'latency_compensated_seconds': compensated,
                         'aligned_residual_seconds': mapped-ref['time'],
                         'duration_difference_seconds': take['duration']-ref['duration']})
    for i, ref in enumerate(reference_notes):
        if i not in used:
            findings.append({'kind': 'unmatched_reference', 'reference_time': ref['time'], 'reference_midi': ref['midi'],
                             'detail': 'Not matched in the take; not proof of a missed note.'})
    timed = [abs(f['raw_timing_seconds']) for f in findings if f['kind'] in ('matched', 'timing_difference')]
    return {'findings': findings, 'mean_absolute_timing_seconds': float(np.mean(timed)) if timed else None,
            'pitch_difference_candidates': sum(f['kind'] == 'pitch_difference' for f in findings),
            'timing_difference_candidates': sum(f['kind'] == 'timing_difference' for f in findings),
            'estimated_latency_seconds': latency,
            'uncertainty': 'Experimental note-event comparison. Separation, transcription and alignment errors compound. No calibrated accuracy score; no finger-pressure, buzz or string-specific diagnosis.'}


# ---------------------------------------------------------------- checking a take against known notes

def score_informed(reference_notes, take_notes, post, onset_hit=.3, wrong_hit=.45, extra_amp=.5,
                   early=.12, late=.25, near=.06, rival=.6, timing_tolerance=.12, merge_neighbours=True,
                   weak_hit=.8):
    """Compare a take with notes known exactly (an uploaded tab), not with a transcription.

    For each written note, ask the transcription model's onset activations whether that pitch
    started near its written time. Far more reliable than transcribing the take blind and
    matching two uncertain note lists. `post` holds Basic Pitch's (frames, 88) 'onset' and
    'note' activations and 'hop' seconds per frame. Same output shape as observations().
    """
    onset, hop = np.asarray(post['onset']), float(post['hop'])
    frames = onset.shape[0]
    refs = sorted(reference_notes, key=lambda n: (n['time'], n['midi']))

    def span(t0, t1):
        return max(0, int(np.floor(t0/hop))), min(frames, int(np.ceil(t1/hop))+1)

    def peak(midi, t0, t1):
        i = midi-21
        a, b = span(t0, t1)
        if not 0 <= i < 88 or b <= a:
            return 0.0, None
        k = int(np.argmax(onset[a:b, i]))
        return float(onset[a+k, i]), (a+k)*hop

    # Each note's search window stops halfway to the next written note at the same pitch, so
    # repeated notes cannot claim the same attack.
    nxt = {}
    by_pitch = {}
    for idx, r in enumerate(refs):
        by_pitch.setdefault(r['midi'], []).append(idx)
    for idxs in by_pitch.values():
        for a, b in zip(idxs, idxs[1:]+[None]):
            nxt[a] = refs[b]['time'] if b is not None else None

    def window(idx, latency):
        r = refs[idx]
        hi = r['time']+latency+late
        if nxt[idx] is not None:
            hi = min(hi, (r['time']+nxt[idx])/2+latency)
        prev_same = [refs[j]['time'] for j in by_pitch[r['midi']] if j < idx]
        lo = r['time']+latency-early
        if prev_same:
            lo = max(lo, (prev_same[-1]+r['time'])/2+latency)
        return lo, hi

    # Pass 1: the player's constant offset (latency left after recording), from clear hits.
    offsets = []
    for idx, r in enumerate(refs):
        s, t = peak(r['midi'], *window(idx, 0.0))
        if s >= .5:
            offsets.append(t-r['time'])
    latency = float(np.clip(np.median(offsets), -.1, .4)) if len(offsets) >= 3 else 0.0

    def nearest(midi, t0, t1, expected):
        """The attack closest to `expected` among clear onset peaks; else the strongest."""
        i = midi-21
        a, b = span(t0, t1)
        if not 0 <= i < 88 or b <= a:
            return 0.0, None
        seg = onset[a:b, i]
        peaks = [k for k in range(len(seg)) if seg[k] >= onset_hit
                 and (k == 0 or seg[k] >= seg[k-1]) and (k == len(seg)-1 or seg[k] >= seg[k+1])]
        if not peaks:
            k = int(np.argmax(seg))
            return float(seg[k]), (a+k)*hop
        strongest = max(peaks, key=lambda k: seg[k])
        close = [k for k in peaks if abs((a+k)*hop-expected) <= near and seg[k] >= rival*seg[strongest]]
        k = min(close, key=lambda k: abs((a+k)*hop-expected)) if close else strongest
        return float(seg[k]), (a+k)*hop

    findings = []
    claimed = []
    for idx, r in enumerate(refs):
        lo, hi = window(idx, latency)
        s, t = nearest(r['midi'], lo, hi, r['time']+latency)
        if s >= onset_hit:
            d = t-latency-r['time']
            claimed.append((r['midi'], t))
            findings.append({'kind': 'timing_difference' if abs(d) > timing_tolerance else 'matched',
                             'reference_time': r['time'], 'take_time': t, 'reference_midi': r['midi'],
                             'take_midi': r['midi'], 'raw_timing_seconds': t-r['time'],
                             'latency_compensated_seconds': d, 'onset_strength': s})
            continue
        # Not there: a strong attack a semitone or two away (or an octave) is a wrong note.
        best = (0.0, None, None)
        for dm in (-2, -1, 1, 2, -12, 12):
            s2, t2 = peak(r['midi']+dm, r['time']+latency-early, r['time']+latency+late)
            if s2 > best[0]:
                best = (s2, r['midi']+dm, t2)
        if best[0] >= wrong_hit and not any(m == r['midi'] for m, _ in claimed if abs(_-r['time']-latency) < .05):
            findings.append({'kind': 'pitch_difference', 'reference_time': r['time'], 'take_time': best[2],
                             'reference_midi': r['midi'], 'take_midi': best[1],
                             'raw_timing_seconds': best[2]-r['time'], 'latency_compensated_seconds': best[2]-latency-r['time']})
            claimed.append((best[1], best[2]))
        else:
            findings.append({'kind': 'unmatched_reference', 'reference_time': r['time'], 'reference_midi': r['midi'],
                             'detail': 'No attack of this note heard near its written time.'})

    # Extra notes: confident attacks not explained by the tab (or an overtone of a written note).
    for n in take_notes:
        if n.get('amplitude', 1) < extra_amp:
            continue
        t = n['time']-latency
        if any(abs(m-n['midi']) in (0, 12, 19, 24) and abs(ct-n['time']) < .15 for m, ct in claimed):
            continue
        if any(abs(r['midi']-n['midi']) in (0, 12, 19, 24) and r['time']-.15 <= t <= r['time']+max(r['duration'], .15)
               for r in refs):
            continue
        findings.append({'kind': 'unmatched_take', 'take_time': n['time'], 'take_midi': n['midi'],
                         'detail': 'A note we did not expect from the tab.'})

    # A semitone or tone off is often heard as both: a weak "hit" on the written pitch (the
    # neighbour bleeds into it) plus a confident note next to it. Report that as a wrong note.
    if merge_neighbours:
        for f in [f for f in findings if f['kind'] == 'unmatched_take']:
            near = [g for g in findings if g['kind'] in ('matched', 'timing_difference')
                    and abs(g['take_time']-f['take_time']) < .06 and abs(g['take_midi']-f['take_midi']) in (1, 2)
                    and g.get('onset_strength', 1) < weak_hit]
            if near:
                g = min(near, key=lambda g: abs(g['take_time']-f['take_time']))
                g.update(kind='pitch_difference', take_midi=f['take_midi'])
                findings.remove(f)

    timed = [abs(f['latency_compensated_seconds']) for f in findings if f['kind'] in ('matched', 'timing_difference')]
    return {'findings': findings, 'mean_absolute_timing_seconds': float(np.mean(timed)) if timed else None,
            'pitch_difference_candidates': sum(f['kind'] == 'pitch_difference' for f in findings),
            'timing_difference_candidates': sum(f['kind'] == 'timing_difference' for f in findings),
            'estimated_latency_seconds': latency, 'method': 'score-informed (written notes checked one by one)',
            'uncertainty': 'Written notes are exact; whether each was played is judged from the transcription model\'s '
                           'note-onset evidence. Quiet, muted or heavily bent notes can be judged missed.'}

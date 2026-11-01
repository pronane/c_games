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

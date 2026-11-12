"""Take versus target: what the player actually played, against a guitar note list.

The target is pluggable. It is the same note list whether it came from

* the separated guitar stem (source ``stem``),
* the written step-4 notation (source ``notation``: fingered, then snapped to the
  same 16th grid the MusicXML uses), or
* an uploaded chart (source ``file``: MusicXML, MIDI, or text tab; Guitar Pro is
  parsed by the studio's existing reader and sent as this same note list).

The take is transcribed on the clean-guitar Basic Pitch path (learners record a
clean part even when the song is distorted). Alignment is onset DTW on pitch,
not on the clock, so a take played slower or rushed still lines up. Early/late
is the residual after a local tempo fit, in milliseconds and beats.

This does not replace the older stem-audio job (``analysis.observations`` /
``score_informed``). Both stay available.
"""
from __future__ import annotations

import io
import re
import struct
import zipfile
import xml.etree.ElementTree as ET

import numpy as np

# A note this far from the local tempo, and at least this far in beats, is early or late.
# Both gates: 80 ms is nothing at a slow tempo, and a tenth of a beat is nothing when the
# tempo is fast. 250 ms at 120 BPM (half a beat) is late; 30 ms is not.
TIMING_SECONDS = 0.08
TIMING_BEATS = 0.12
# Duration is compared after stretching by the fitted tempo. Transcription lengths wander,
# so only a clear miss (both a fraction of the note and an absolute gap) counts.
DURATION_ABS = 0.12
DURATION_RATIO = 0.45
ONSET_WINDOW = 0.04
SKIP_COST = 0.72
TAKE_HISTORY = 5

KINDS = ('correct', 'wrong_pitch', 'wrong_string', 'early', 'late', 'missing', 'extra', 'wrong_duration')
SOURCES = ('stem', 'notation', 'file')
NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
_STEP = {'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7, 'A': 9, 'B': 11}


def note_name(midi: int) -> str:
    midi = int(midi)
    return f'{NAMES[midi % 12]}{midi // 12 - 1}'


def normalize_notes(notes) -> list:
    """{time, duration, midi, string?, fret?} from the loose dicts each producer emits."""
    out = []
    if not notes:
        return out
    for n in notes:
        if not isinstance(n, dict) or 'midi' not in n:
            raise ValueError('Each note needs a midi pitch.')
        midi = int(n['midi'])
        if not 0 <= midi <= 127:
            raise ValueError('MIDI pitch out of range.')
        time = float(n.get('time', n.get('start', 0)) or 0)
        if 'duration' in n and n['duration'] is not None:
            dur = float(n['duration'])
        elif n.get('end') is not None:
            dur = float(n['end']) - time
        else:
            dur = 0.25
        item = {'time': time, 'duration': max(0.03, dur), 'midi': midi}
        if n.get('string') is not None and n.get('fret') is not None:
            item['string'] = int(n['string'])
            item['fret'] = int(n['fret'])
        out.append(item)
    out.sort(key=lambda n: (n['time'], n['midi']))
    return out


def _bars_from(bars, bpm, beats_per_bar, span):
    beats_per_bar = int(beats_per_bar or 4)
    if bars:
        out = []
        for i, b in enumerate(bars):
            if isinstance(b, dict):
                out.append({'number': int(b.get('number', i + 1)), 'time': float(b.get('time', 0))})
            else:
                out.append({'number': i + 1, 'time': float(b)})
        out.sort(key=lambda b: (b['time'], b['number']))
        return out, float(bpm or 120), beats_per_bar
    bpm = float(bpm or 120)
    bar_len = (60.0 / bpm) * beats_per_bar
    span = max(float(span or 0), bar_len)
    count = max(1, int(np.ceil(span / bar_len - 1e-9)))
    return [{'number': i + 1, 'time': i * bar_len} for i in range(count)], bpm, beats_per_bar


def place_in_take_time(notes, bars, start, end, speed, bpm, beats_per_bar=4):
    """Shift song-time notes and bar lines onto the take.

    The take was recorded while the song played at ``speed`` (1 = original). A bar that
    started before the excerpt keeps a negative time so beat numbers stay the song's.
    """
    speed = float(speed or 1)
    if speed <= 0:
        raise ValueError('Speed must be positive.')
    start, end = float(start), float(end)
    if end <= start:
        raise ValueError('The excerpt end must be after its start.')
    notes = normalize_notes(notes)
    span = max([n['time'] + n['duration'] for n in notes] + [end, start + 1])
    bar_list, bpm, beats_per_bar = _bars_from(bars, bpm, beats_per_bar, span)
    kept = []
    for n in notes:
        if n['time'] < start - 1e-4 or n['time'] >= end - 1e-4:
            continue
        kept.append(dict(n, time=(n['time'] - start) / speed, duration=n['duration'] / speed))
    bar_len = (60.0 / bpm) * beats_per_bar
    placed = []
    for i, b in enumerate(bar_list):
        nxt = bar_list[i + 1]['time'] if i + 1 < len(bar_list) else b['time'] + bar_len
        if nxt > start + 1e-6 and b['time'] < end - 1e-6:
            placed.append({'number': b['number'], 'time': (b['time'] - start) / speed})
    return kept, placed, bpm * speed, beats_per_bar


def _group_onsets(notes, window=ONSET_WINDOW):
    groups = []
    for n in notes:
        if groups and n['time'] - groups[-1]['time'] <= window:
            groups[-1]['notes'].append(n)
        else:
            groups.append({'time': n['time'], 'notes': [n]})
    return groups


def _pitch_cost(a, b):
    d = abs(int(a) - int(b))
    if d == 0:
        return 0.0
    if d % 12 == 0:
        return 0.4          # octave: wrong string, still the same alignment
    if d <= 6:
        return 0.16 * d     # a step or two is a wrong note, not a different place in the song
    return 1.0


def _onset_cost(take_notes, target_notes):
    a = [n['midi'] for n in take_notes]
    b = [n['midi'] for n in target_notes]
    if not a and not b:
        return 0.0
    if not a or not b:
        return 1.0
    used = set()
    total = 0.0
    for m in a:
        best_j, best = None, None
        for j, t in enumerate(b):
            if j in used:
                continue
            c = _pitch_cost(m, t)
            if best is None or c < best:
                best, best_j = c, j
        if best_j is None:
            break
        used.add(best_j)
        total += best
    unmatched = (len(a) - len(used)) + (len(b) - len(used))
    return (total + 0.85 * unmatched) / max(len(a), len(b))


def _align_onsets(take_groups, target_groups):
    """DTW on the onset sequence. Returns (take_index|None, target_index|None) steps.

    Cost is pitch, not time, so playing the whole phrase slower does not break the path.
    """
    n, m = len(take_groups), len(target_groups)
    if n == 0:
        return [(None, j) for j in range(m)]
    if m == 0:
        return [(i, None) for i in range(n)]
    inf = 1e9
    cost = [[inf] * (m + 1) for _ in range(n + 1)]
    back = [[0] * (m + 1) for _ in range(n + 1)]
    cost[0][0] = 0.0
    for i in range(1, n + 1):
        cost[i][0] = i * SKIP_COST
        back[i][0] = 2
    for j in range(1, m + 1):
        cost[0][j] = j * SKIP_COST
        back[0][j] = 3
    for i in range(1, n + 1):
        ti = take_groups[i - 1]['notes']
        row = cost[i]
        prev = cost[i - 1]
        for j in range(1, m + 1):
            local = _onset_cost(ti, target_groups[j - 1]['notes'])
            match = prev[j - 1] + local
            extra = prev[j] + SKIP_COST
            missing = row[j - 1] + SKIP_COST
            # Ties prefer a match, so a repeated pitch is not thrown away as a skip.
            best, kind = match, 1
            if extra < best:
                best, kind = extra, 2
            if missing < best:
                best, kind = missing, 3
            row[j] = best
            back[i][j] = kind
    i, j = n, m
    steps = []
    while i > 0 or j > 0:
        kind = back[i][j]
        if kind == 1 and i > 0 and j > 0:
            steps.append((i - 1, j - 1))
            i, j = i - 1, j - 1
        elif kind == 2 and i > 0:
            steps.append((i - 1, None))
            i -= 1
        elif j > 0:
            steps.append((None, j - 1))
            j -= 1
        else:
            break
    steps.reverse()
    return steps


def _pair_onset(take_notes, target_notes):
    """Exact pitches first, then nearest leftover pitch as a substitution."""
    used_t, used_r = set(), set()
    pairs = []
    for i, target in enumerate(target_notes):
        for j, take in enumerate(take_notes):
            if j in used_t or take['midi'] != target['midi']:
                continue
            used_t.add(j)
            used_r.add(i)
            pairs.append((take, target, 'pitch'))
            break
    left_t = [j for j in range(len(take_notes)) if j not in used_t]
    left_r = [i for i in range(len(target_notes)) if i not in used_r]
    cands = sorted(
        (abs(target_notes[i]['midi'] - take_notes[j]['midi']), i, j) for i in left_r for j in left_t)
    for _, i, j in cands:
        if i in used_r or j in used_t:
            continue
        used_r.add(i)
        used_t.add(j)
        pairs.append((take_notes[j], target_notes[i], 'wrong'))
    for i in left_r:
        if i not in used_r:
            pairs.append((None, target_notes[i], 'missing'))
    for j in left_t:
        if j not in used_t:
            pairs.append((take_notes[j], None, 'extra'))
    return pairs


def _local_offset(times, offsets, index, half=4):
    """Offset the local tempo predicts at ``index``, ignoring that note itself.

    Theil-Sen on the neighbours: a straight slow-down fits exactly, and one late note
    does not pull the line with it.
    """
    idx = [j for j in range(max(0, index - half), min(len(times), index + half + 1)) if j != index]
    if not idx:
        return float(offsets[index])
    if len(idx) == 1:
        return float(offsets[idx[0]])
    slopes = []
    for a in range(len(idx)):
        for b in range(a + 1, len(idx)):
            dt = float(times[idx[b]] - times[idx[a]])
            if abs(dt) < 1e-3:
                continue
            slopes.append(float(offsets[idx[b]] - offsets[idx[a]]) / dt)
    if not slopes:
        return float(np.median(offsets[idx]))
    slope = float(np.median(slopes))
    intercept = float(np.median(offsets[idx] - slope * times[idx]))
    return slope * float(times[index]) + intercept


def _speed_ratio(pairs):
    """How fast the take is relative to the target (1 = same tempo, 0.5 = half speed).

    Intervals across a gap (a missing bar) are left out so they don't look like a tempo change.
    """
    pairs = sorted(pairs, key=lambda p: p[1]['time'])
    ratios = []
    for a, b in zip(pairs, pairs[1:]):
        dt_t = b[1]['time'] - a[1]['time']
        dt_k = b[0]['time'] - a[0]['time']
        if dt_t < 0.05 or dt_k <= 0.02 or dt_t > 4 or dt_k > 8:
            continue
        ratios.append(dt_t / dt_k)
    if len(ratios) < 2:
        return None
    return float(np.median(ratios))


def _locate(time, bars, bpm, beats_per_bar):
    beat_len = 60.0 / bpm if bpm else 0.5
    bar_len = beat_len * beats_per_bar
    if not bars:
        time = max(0.0, time)
        bar = int(time // bar_len) + 1
        beat = int((time - (bar - 1) * bar_len + 1e-6) // beat_len) + 1
        return bar, min(beats_per_bar, max(1, beat)), beat_len
    i = 0
    for k, b in enumerate(bars):
        if b['time'] <= time + 1e-6:
            i = k
        else:
            break
    bar = bars[i]
    if time + 1e-6 < bars[0]['time']:
        bar = bars[0]
        i = 0
    nxt = bars[i + 1]['time'] if i + 1 < len(bars) else None
    local_bar = (nxt - bar['time']) if nxt and nxt > bar['time'] + 1e-6 else bar_len
    local_beat = local_bar / beats_per_bar
    # Past the last bar line: keep counting bars of the same length.
    if nxt is None and time > bar['time'] + local_bar - 1e-6:
        extra = int((time - bar['time']) // local_bar)
        origin = bar['time'] + extra * local_bar
        beat = int((time - origin + 1e-6) // local_beat) + 1
        return bar['number'] + extra, min(beats_per_bar, max(1, beat)), local_beat
    beat = int((time - bar['time'] + 1e-6) // local_beat) + 1
    return bar['number'], min(beats_per_bar, max(1, beat)), local_beat


def _duration_off(take_dur, target_dur, speed_ratio):
    expected = target_dur / speed_ratio if speed_ratio else target_dur
    expected = max(0.03, expected)
    return abs(take_dur - expected) > max(DURATION_ABS, DURATION_RATIO * expected)


def _describe(kind, bar, beat, take, target, delta_ms, delta_beats):
    where = f'bar {bar} beat {beat}'
    if kind == 'wrong_pitch':
        return f'{where}: played {note_name(take["midi"])}, expected {note_name(target["midi"])}'
    if kind == 'wrong_string':
        return (f'{where}: played string {take["string"]} fret {take["fret"]}, '
                f'expected string {target["string"]} fret {target["fret"]}')
    if kind == 'early':
        return f'{where}: {note_name(target["midi"])} was {abs(delta_ms)} ms early ({abs(delta_beats):.2f} beats)'
    if kind == 'late':
        return f'{where}: {note_name(target["midi"])} was {delta_ms} ms late ({delta_beats:.2f} beats)'
    if kind == 'missing':
        return f'{where}: missed {note_name(target["midi"])}'
    if kind == 'extra':
        return f'{where}: extra {note_name(take["midi"])}'
    if kind == 'wrong_duration':
        word = 'too long' if take['duration'] > target['duration'] else 'too short'
        return (f'{where}: {note_name(target["midi"])} held {word} '
                f'(played {round(take["duration"] * 1000)} ms, expected {round(target["duration"] * 1000)} ms)')
    return ''


def _empty_counts():
    return {k: 0 for k in KINDS}


def _summary(counts, speed_ratio):
    n_target = sum(counts[k] for k in KINDS if k != 'extra')
    right_pitch = sum(counts[k] for k in ('correct', 'early', 'late', 'wrong_duration', 'wrong_string'))
    pitch_den = right_pitch + counts['wrong_pitch']
    on_time = counts['correct'] + counts['wrong_duration'] + counts['wrong_string']
    timed = on_time + counts['early'] + counts['late']
    pitch = round(right_pitch / pitch_den, 3) if pitch_den else None
    timing = round(on_time / timed, 3) if timed else None
    completeness = round((n_target - counts['missing']) / n_target, 3) if n_target else None
    parts, weights = [], []
    for value, weight in ((pitch, 0.45), (timing, 0.25), (completeness, 0.30)):
        if value is not None:
            parts.append(weight * value)
            weights.append(weight)
    base = sum(parts) / sum(weights) if weights else 0.0
    penalty = n_target / (n_target + counts['extra']) if (n_target + counts['extra']) else 1.0
    overall = int(round(100 * base * penalty)) if (n_target or counts['extra']) else None
    return {
        'pitch_accuracy': pitch,
        'timing_accuracy': timing,
        'completeness': completeness,
        'overall': overall,
        'counts': counts,
        'speed_ratio': None if speed_ratio is None else round(float(speed_ratio), 3),
    }


def _bar_rows(notes, bars):
    by = {}
    for n in notes:
        row = by.setdefault(n['bar'], {'bar': n['bar'], 'time': n.get('bar_time'), 'counts': _empty_counts(), 'messages': []})
        row['counts'][n['kind']] += 1
        if n['message']:
            row['messages'].append(n['message'])
        if row['time'] is None:
            row['time'] = n.get('bar_time')
    rows = []
    for row in by.values():
        graded = sum(row['counts'].values())
        credit = (row['counts']['correct']
                  + 0.5 * (row['counts']['early'] + row['counts']['late']
                           + row['counts']['wrong_duration'] + row['counts']['wrong_string']))
        row['score'] = int(round(100 * credit / graded)) if graded else None
        rows.append(row)
    rows.sort(key=lambda r: (r['time'] is None, r['time'] if r['time'] is not None else 0, r['bar']))
    worst = [r for r in rows if r['messages']]
    worst.sort(key=lambda r: (r['score'] if r['score'] is not None else 101, -len(r['messages']), r['bar']))
    return rows, [{'bar': r['bar'], 'score': r['score'], 'messages': r['messages']} for r in worst[:5]]


def compare_to_target(take_notes, target, *, duration_review=False) -> dict:
    """Per-note and per-bar diff of one take against one target note list."""
    source = target.get('source') or 'file'
    if source not in SOURCES:
        raise ValueError('Target source must be stem, notation, or file.')
    take = normalize_notes(take_notes)
    ref = normalize_notes(target.get('notes') or [])
    span = 0.0
    for n in take + ref:
        span = max(span, n['time'] + n['duration'])
    bpm = float(target['bpm']) if target.get('bpm') else 120.0
    beats_per_bar = int(target.get('beats_per_bar') or 4)
    bars, bpm, beats_per_bar = _bars_from(target.get('bars'), bpm, beats_per_bar, span or 1)

    take_groups = _group_onsets(take)
    ref_groups = _group_onsets(ref)
    steps = _align_onsets(take_groups, ref_groups)

    paired = []          # (take, target, relation) with both sides, in path order
    loose = []           # missing / extra from the path
    for ti, ri in steps:
        tnotes = take_groups[ti]['notes'] if ti is not None else []
        rnotes = ref_groups[ri]['notes'] if ri is not None else []
        if ti is None:
            loose.extend((None, n, 'missing') for n in rnotes)
            continue
        if ri is None:
            loose.extend((n, None, 'extra') for n in tnotes)
            continue
        for take_n, ref_n, rel in _pair_onset(tnotes, rnotes):
            if take_n is not None and ref_n is not None:
                paired.append((take_n, ref_n, rel))
            else:
                loose.append((take_n, ref_n, rel))

    order = sorted(range(len(paired)), key=lambda i: paired[i][1]['time'])
    times = np.array([paired[i][1]['time'] for i in order], dtype=float)
    offsets = np.array([paired[i][0]['time'] - paired[i][1]['time'] for i in order], dtype=float)
    residual = {}
    predicted_offset = np.zeros(len(order))
    for pos, i in enumerate(order):
        predicted_offset[pos] = _local_offset(times, offsets, pos) if len(order) else 0.0
        residual[id(paired[i][0])] = float(offsets[pos] - predicted_offset[pos])
    ratio = _speed_ratio([(t, r) for t, r, rel in paired if rel == 'pitch'])

    # Map a take time onto the target clock so an extra note lands in the right bar.
    # The smooth map is take_time - predicted_offset, which is the target time when the
    # note is in tempo (residual ~ 0) and ignores one-off rushes.
    def warp(take_time):
        if not len(order):
            return float(take_time)
        take_ts = np.array([paired[i][0]['time'] for i in order], dtype=float)
        target_ts = take_ts - predicted_offset
        idx = np.argsort(take_ts, kind='mergesort')
        take_ts, target_ts = take_ts[idx], target_ts[idx]
        keep = np.concatenate([[True], np.diff(take_ts) > 1e-4])
        return float(np.interp(take_time, take_ts[keep], target_ts[keep]))

    findings = []

    def add(kind, take_n, target_n, when):
        bar, beat, beat_len = _locate(when, bars, bpm, beats_per_bar)
        delta = residual.get(id(take_n), 0.0) if take_n is not None and target_n is not None else 0.0
        delta_ms = int(round(delta * 1000))
        delta_beats = round(delta / beat_len, 2) if beat_len else 0.0
        if kind == 'pitch':
            if (take_n.get('string') is not None and target_n.get('string') is not None
                    and (take_n['string'] != target_n['string'] or take_n['fret'] != target_n['fret'])):
                kind = 'wrong_string'
            elif abs(delta) > TIMING_SECONDS and abs(delta_beats) >= TIMING_BEATS - 1e-9:
                kind = 'late' if delta > 0 else 'early'
            elif _duration_off(take_n['duration'], target_n['duration'], ratio):
                kind = 'wrong_duration'
            else:
                kind = 'correct'
        message = _describe(kind, bar, beat, take_n, target_n, delta_ms, delta_beats)
        if duration_review and kind == 'wrong_duration':
            message = (f'bar {bar} beat {beat}: duration estimate differs for '
                       f'{note_name(target_n["midi"])}; review by ear. '
                       'Sustain, noise or effect tails can affect this estimate; this is not a confirmed playing mistake.')
        bar_time = next((b['time'] for b in bars if b['number'] == bar), None)
        findings.append({
            'kind': kind,
            'bar': bar,
            'beat': beat,
            'bar_time': bar_time,
            'message': message,
            'target_time': None if target_n is None else round(target_n['time'], 4),
            'target_duration': None if target_n is None else round(target_n['duration'], 4),
            'target_midi': None if target_n is None else target_n['midi'],
            'target_string': None if target_n is None else target_n.get('string'),
            'target_fret': None if target_n is None else target_n.get('fret'),
            'take_time': None if take_n is None else round(take_n['time'], 4),
            'take_duration': None if take_n is None else round(take_n['duration'], 4),
            'take_midi': None if take_n is None else take_n['midi'],
            'take_string': None if take_n is None else take_n.get('string'),
            'take_fret': None if take_n is None else take_n.get('fret'),
            'delta_seconds': round(delta, 4),
            'delta_ms': delta_ms,
            'delta_beats': delta_beats,
        })

    for take_n, target_n, rel in paired:
        add('wrong_pitch' if rel == 'wrong' else 'pitch', take_n, target_n, target_n['time'])
    for take_n, target_n, rel in loose:
        when = target_n['time'] if target_n is not None else warp(take_n['time'])
        add(rel, take_n, target_n, when)

    findings.sort(key=lambda n: (n['target_time'] is None, n['target_time'] if n['target_time'] is not None else n['take_time'] or 0,
                                  n['target_midi'] or n['take_midi'] or 0))
    for i, n in enumerate(findings):
        n['id'] = i
    counts = _empty_counts()
    for n in findings:
        counts[n['kind']] += 1
    bar_rows, worst = _bar_rows(findings, bars)
    summary = _summary(counts, ratio)
    return {
        'source': source,
        'label': target.get('label') or {'stem': 'Guitar stem', 'notation': 'Written notation', 'file': 'Uploaded chart'}[source],
        'bpm': round(bpm, 3),
        'summary': summary,
        'notes': findings,
        'bars': bar_rows,
        'worst_bars': worst,
        'method': 'Onset DTW against the target note list. Tempo drift is removed before early/late is called.',
    }


def _combine(reports):
    stem = next((r for r in reports if r['source'] == 'stem'), None)
    notation = next((r for r in reports if r['source'] == 'notation'), None)
    if not stem or not notation:
        return None

    def avg(key):
        vals = [r['summary'][key] for r in (stem, notation) if r['summary'][key] is not None]
        if not vals:
            return None
        mean = sum(vals) / len(vals)
        return int(round(mean)) if key == 'overall' else round(mean, 3)

    return {
        'overall': avg('overall'),
        'pitch_accuracy': avg('pitch_accuracy'),
        'timing_accuracy': avg('timing_accuracy'),
        'completeness': avg('completeness'),
        'detail': 'Average of the guitar-stem notes and the written notation.',
    }


def compare_take(take_notes, targets, transcription='notes supplied') -> dict:
    """Score one take against each target. Stem + notation also produce a combined score."""
    if not targets:
        raise ValueError('At least one target note list is required.')
    import os
    review = (os.getenv('FRETWORK_DURATION_REVIEW', '0') == '1'
              and transcription.startswith('clean-guitar '))
    reports = [compare_to_target(take_notes, t, duration_review=review) for t in targets]
    if review:
        for report in reports:
            report['duration_policy'] = 'review_only'
            report['duration_notice'] = ('Duration differences are uncertain audio estimates. '
                                         'Counts and diagnostic bar scores are unchanged, not confirmed mistake grades.')
    return {
        'take_notes': normalize_notes(take_notes),
        'transcription': transcription,
        'reports': reports,
        'combined': _combine(reports),
    }


# ---------------------------------------------------------------- step-4 notation target

def _sixteenth_to_time(sixteenths, beats):
    beats = np.asarray(beats, dtype=float)
    if len(beats) < 2:
        return float(sixteenths) / 8.0
    pos = sixteenths / 4.0
    if pos <= 0:
        return float(beats[0] + pos * (beats[1] - beats[0]))
    if pos >= len(beats) - 1:
        period = float(beats[-1] - beats[-2])
        return float(beats[-1] + (pos - (len(beats) - 1)) * period)
    i = int(np.floor(pos))
    frac = pos - i
    return float(beats[i] + frac * (beats[i + 1] - beats[i]))


def quantize_notes(notes, beats):
    """Snap starts and lengths to the 16th grid ``song_analysis.musicxml`` writes."""
    from . import song_analysis as sa
    notes = normalize_notes(notes)
    if len(beats) < 2:
        return notes
    out = []
    for n in notes:
        start = sa.time_to_sixteenths(n['time'], beats)
        end = max(start + 1, sa.time_to_sixteenths(n['time'] + n['duration'], beats))
        item = dict(n, time=_sixteenth_to_time(start, beats),
                    duration=max(0.05, _sixteenth_to_time(end, beats) - _sixteenth_to_time(start, beats)))
        out.append(item)
    # The staff draws one note per pitch at a grid position.
    seen, unique = set(), []
    for n in out:
        key = (round(n['time'], 4), n['midi'])
        if key in seen:
            continue
        seen.add(key)
        unique.append(n)
    return unique


def notation_notes(raw_notes, beats, open_strings, max_fret=24):
    """The note list the written tab actually shows: fingered, on the grid, playable."""
    from . import song_analysis as sa
    notes = [dict(n) for n in raw_notes]
    if open_strings:
        notes = sa.fingering(notes, open_strings, max_fret)
        notes = [n for n in notes if n.get('string')]
    return quantize_notes(notes, beats)


# ---------------------------------------------------------------- clean-guitar transcription

def transcribe_take(path):
    """Transcribe a learner's take with the existing engine, on the clean-guitar thresholds.

    The song may have been transcribed as distorted. A practice take is scored as clean
    guitar: same Basic Pitch model, the GuitarSet onset/frame thresholds.
    """
    from . import models
    from .instruments import resolve_profile
    profile = resolve_profile('guitar')
    thresholds = models.thresholds_for('clean', chosen_by_user=True)
    return models.transcribe(path, midi_min=profile['midi_min'], midi_max=profile['midi_max'],
                             thresholds=thresholds)


# ---------------------------------------------------------------- uploaded charts (MusicXML, MIDI, text tab)

def _xml_root(text: str):
    text = text.lstrip('\ufeff').strip()
    if text.startswith('<?xml'):
        text = text.split('?>', 1)[1]
    text = re.sub(r'<!DOCTYPE[^>[]*(?:\[[^\]]*\])?[^>]*>', '', text, count=1)
    root = ET.fromstring(text)
    for el in root.iter():
        if isinstance(el.tag, str) and '}' in el.tag:
            el.tag = el.tag.split('}', 1)[1]
    return root


def _pitch_midi(pitch):
    step = _STEP.get((pitch.findtext('step') or 'C').strip()[:1].upper())
    if step is None:
        return None
    alter = float(pitch.findtext('alter') or 0)
    octave = int(pitch.findtext('octave') or 4)
    return int(round((octave + 1) * 12 + step + alter))


def notes_from_musicxml(text: str) -> dict:
    """Partwise MusicXML (what this app writes, and the usual export) -> note list."""
    root = _xml_root(text) if isinstance(text, str) else _xml_root(text.decode('utf-8', 'replace'))
    bpm = 120.0
    beats_per_bar = 4
    divisions = 1
    notes, bars = [], []
    open_ties = {}
    seconds = 0.0
    for measure in root.iter('measure'):
        number = int(measure.get('number') or (len(bars) + 1))
        bars.append({'number': number, 'time': seconds})
        measure_end = seconds
        last_start = seconds
        division_seconds = (60.0 / bpm) / divisions
        for child in list(measure):
            tag = child.tag
            if tag == 'attributes':
                div = child.findtext('divisions')
                if div:
                    divisions = max(1, int(float(div)))
                    division_seconds = (60.0 / bpm) / divisions
                time_el = child.find('time')
                if time_el is not None and time_el.findtext('beats'):
                    beats_per_bar = int(time_el.findtext('beats'))
            elif tag == 'direction':
                sound = child.find('sound')
                per = child.findtext('.//per-minute')
                if sound is not None and sound.get('tempo'):
                    bpm = float(sound.get('tempo')) or bpm
                elif per:
                    bpm = float(per) or bpm
                division_seconds = (60.0 / bpm) / divisions
            elif tag == 'backup':
                d = int(float(child.findtext('duration') or 0))
                seconds -= d * division_seconds
            elif tag == 'forward':
                d = int(float(child.findtext('duration') or 0))
                seconds += d * division_seconds
                measure_end = max(measure_end, seconds)
            elif tag == 'note':
                if child.find('grace') is not None:
                    continue
                dur_div = int(float(child.findtext('duration') or 0))
                dur_s = max(0.0, dur_div * division_seconds)
                if child.find('rest') is not None:
                    seconds += dur_s
                    measure_end = max(measure_end, seconds)
                    continue
                is_chord = child.find('chord') is not None
                start = last_start if is_chord else seconds
                if not is_chord:
                    last_start = start
                    seconds += dur_s
                    measure_end = max(measure_end, seconds)
                pitch = child.find('pitch')
                if pitch is None:
                    continue
                midi = _pitch_midi(pitch)
                if midi is None:
                    continue
                voice = child.findtext('voice') or '1'
                ties = {t.get('type') for t in child.findall('tie')}
                ties |= {t.get('type') for t in child.findall('.//tied')}
                key = (voice, midi)
                if 'stop' in ties and key in open_ties:
                    prev = open_ties[key]
                    prev['duration'] = max(prev['duration'], start + dur_s - prev['time'])
                    if 'start' not in ties:
                        del open_ties[key]
                    continue
                tech = child.find('.//technical')
                item = {'time': start, 'duration': max(0.03, dur_s or 0.25), 'midi': midi}
                if tech is not None and tech.findtext('string') and tech.findtext('fret'):
                    item['string'] = int(tech.findtext('string'))
                    item['fret'] = int(tech.findtext('fret'))
                notes.append(item)
                if 'start' in ties:
                    open_ties[key] = item
        seconds = max(seconds, measure_end)
    return {'notes': normalize_notes(notes), 'bars': bars, 'bpm': bpm, 'beats_per_bar': beats_per_bar}


def notes_from_mxl(data: bytes) -> dict:
    with zipfile.ZipFile(io.BytesIO(data)) as bundle:
        name = None
        if 'META-INF/container.xml' in bundle.namelist():
            root = _xml_root(bundle.read('META-INF/container.xml').decode('utf-8', 'replace'))
            rootfile = root.find('.//rootfile')
            if rootfile is not None and rootfile.get('full-path'):
                name = rootfile.get('full-path')
        if not name or name not in bundle.namelist():
            xmls = [n for n in bundle.namelist() if n.lower().endswith('.xml') and not n.startswith('META-INF')]
            if not xmls:
                raise ValueError('The compressed MusicXML file has no score in it.')
            name = xmls[0]
        return notes_from_musicxml(bundle.read(name).decode('utf-8', 'replace'))


def _vlq(n):
    out = [n & 0x7F]
    n >>= 7
    while n:
        out.append((n & 0x7F) | 0x80)
        n >>= 7
    return bytes(reversed(out))


def _read_vlq(data, i):
    n = 0
    while True:
        b = data[i]
        i += 1
        n = (n << 7) | (b & 0x7F)
        if not b & 0x80:
            return n, i


def notes_to_midi(notes, bpm=120, beats_per_bar=4) -> bytes:
    """A one-track MIDI file, so a synthetic take can go through the same parser as an upload."""
    tpq = 960
    notes = normalize_notes(notes)
    us = int(round(60_000_000 / float(bpm)))
    events = [(0, 0, bytes([0xFF, 0x51, 0x03]) + us.to_bytes(3, 'big'))]
    events.append((0, 1, bytes([0xFF, 0x58, 0x04, int(beats_per_bar) & 0xFF, 2, 24, 8])))
    for n in notes:
        on = max(0, int(round(n['time'] * bpm / 60 * tpq)))
        off = max(on + 1, int(round((n['time'] + n['duration']) * bpm / 60 * tpq)))
        events.append((on, 2, bytes([0x90, n['midi'] & 0x7F, 80])))
        events.append((off, 3, bytes([0x80, n['midi'] & 0x7F, 0])))
    end = max((e[0] for e in events), default=0) + tpq
    events.append((end, 4, bytes([0xFF, 0x2F, 0x00])))
    events.sort()
    track = b''
    last = 0
    for tick, _, payload in events:
        track += _vlq(tick - last) + payload
        last = tick
    header = b'MThd' + struct.pack('>IHHH', 6, 0, 1, tpq)
    return header + b'MTrk' + struct.pack('>I', len(track)) + track


def _tick_to_seconds(tick, changes, tpq):
    sec = 0.0
    us = 500000
    last = 0
    for t, tempo in changes:
        if t >= tick:
            break
        sec += (t - last) * us / tpq / 1e6
        last, us = t, tempo
    sec += (tick - last) * us / tpq / 1e6
    return sec


def notes_from_midi(data: bytes) -> dict:
    """Standard MIDI file -> note list. Tempo and time-signature meta events are honoured."""
    if len(data) < 14 or data[:4] != b'MThd':
        raise ValueError('That is not a MIDI file.')
    _, fmt, ntracks, division = struct.unpack('>IHHH', data[4:14])
    if division & 0x8000:
        raise ValueError('SMPTE MIDI files are not supported.')
    tpq = division or 960
    i = 14
    bpm = 120.0
    beats_per_bar = 4
    notes = []
    for _ in range(ntracks):
        if i + 8 > len(data) or data[i:i + 4] != b'MTrk':
            break
        length = struct.unpack('>I', data[i + 4:i + 8])[0]
        track, i = data[i + 8:i + 8 + length], i + 8 + length
        tick = 0
        j = 0
        status = 0
        changes = [(0, 500000)]
        onsets = []  # (tick, midi, velocity) waiting for note-off; raw, converted after the tempo map
        while j < len(track):
            delta, j = _read_vlq(track, j)
            tick += delta
            if j >= len(track):
                break
            if track[j] & 0x80:
                status = track[j]
                j += 1
            if status == 0xFF:
                if j >= len(track):
                    break
                meta = track[j]
                j += 1
                ln, j = _read_vlq(track, j)
                payload, j = track[j:j + ln], j + ln
                if meta == 0x51 and len(payload) == 3:
                    us = int.from_bytes(payload, 'big') or 500000
                    changes.append((tick, us))
                    bpm = 60_000_000 / us
                elif meta == 0x58 and payload:
                    beats_per_bar = payload[0] or 4
                elif meta == 0x2F:
                    break
                continue
            if status in (0xF0, 0xF7):
                ln, j = _read_vlq(track, j)
                j += ln
                continue
            kind, channel = status & 0xF0, status & 0x0F
            if kind in (0xC0, 0xD0):
                j += 1
                continue
            if j + 1 > len(track):
                break
            data1, data2 = track[j], track[j + 1]
            j += 2
            if channel == 9:
                continue  # drums
            if kind == 0x90 and data2 > 0:
                onsets.append([tick, data1, None])
            elif kind in (0x80, 0x90):
                for ev in reversed(onsets):
                    if ev[1] == data1 and ev[2] is None:
                        ev[2] = tick
                        break
        changes.sort()
        for start, midi, end in onsets:
            if end is None or end <= start:
                continue
            t0 = _tick_to_seconds(start, changes, tpq)
            t1 = _tick_to_seconds(end, changes, tpq)
            notes.append({'time': t0, 'duration': max(0.03, t1 - t0), 'midi': int(midi)})
    if not notes and fmt not in (0, 1):
        raise ValueError('No notes found in the MIDI file.')
    return {'notes': normalize_notes(notes), 'bars': [], 'bpm': round(bpm, 3), 'beats_per_bar': beats_per_bar}


def target_from_upload(filename: str, data: bytes, bpm: float | None = None) -> dict:
    """Parse an uploaded chart into a ``file`` target, using the parsers we already have.

    Guitar Pro is binary and is read in the studio by alphaTab (the same reader as
    "Learn from a tab"). Send those notes as a ``file`` target; this function accepts
    MusicXML, compressed MusicXML, MIDI, and plain-text tab.
    """
    name = (filename or '').lower()
    if name.endswith(('.gp', '.gp3', '.gp4', '.gp5', '.gpx')):
        raise ValueError('Guitar Pro files are read in the studio (Learn from a tab) and sent as notes. '
                         'Upload MusicXML, MIDI, or a text tab here.')
    if name.endswith(('.mid', '.midi')):
        parsed = notes_from_midi(data)
    elif name.endswith('.mxl'):
        parsed = notes_from_mxl(data)
    elif name.endswith(('.xml', '.musicxml')):
        parsed = notes_from_musicxml(data.decode('utf-8', 'replace'))
    elif name.endswith(('.txt', '.tab')):
        from .instruments import resolve_profile
        from .tabs import parse_ascii_tab
        profile = resolve_profile('guitar')
        parsed = parse_ascii_tab(data.decode('utf-8', 'replace'), profile['open_strings'], bpm or 90)
        parsed = {'notes': parsed['notes'], 'bars': [{'number': i + 1, 'time': t} for i, t in enumerate(parsed['bars'])],
                  'bpm': parsed['bpm'], 'beats_per_bar': 4}
    else:
        raise ValueError('Upload MusicXML (.musicxml, .xml, .mxl), MIDI (.mid), or a text tab (.txt).')
    if not parsed.get('notes'):
        raise ValueError('No pitched notes found in that file.')
    label = filename or 'Uploaded chart'
    return {'source': 'file', 'label': label, 'notes': parsed['notes'], 'bars': parsed.get('bars') or None,
            'bpm': bpm or parsed.get('bpm') or 120, 'beats_per_bar': parsed.get('beats_per_bar') or 4}


def remember_take(history, entry, limit=TAKE_HISTORY):
    """Keep the last ``limit`` takes. Oldest falls off the front."""
    return ([*(history or []), entry])[-limit:]

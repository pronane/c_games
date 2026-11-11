"""Two-sided behaviour lock for the user's recordings.

There is no ground-truth tab, so a higher note count or a higher agreement
is not automatically better. The lock fails when the song-path decoder moves
by more than the same slack the public clips use (0.02). Note counts use a
2% relative slack, because a five-minute take has hundreds of notes and an
absolute 0.02 would be a fraction of a note.

When the AAC files are absent the check is a skip, not a failure. A file
that is present but has a different checksum is a failure: the locked
numbers belong to these exact recordings.
"""
from __future__ import annotations

SLACK = 0.02
COUNT_REL = 0.02

# Timing and rate fields. Pitch-class bins are checked separately.
TIME_KEYS = (
    'notes_per_second', 'median_duration_s', 'p10_duration_s', 'short_fraction',
    'median_ioi_s', 'first_onset_s', 'last_onset_s', 'playback_onset_lag_s',
)
PAIR_KEYS = ('note_f1_50', 'onset_f1_50', 'pitch_class_cosine')


def _delta_problem(label, key, got, locked, slack):
    if got is None or locked is None:
        if got != locked:
            return {'id': label, 'key': key, 'problem': 'missing metric', 'got': got, 'locked': locked}
        return None
    delta = float(got) - float(locked)
    if abs(delta) > slack:
        return {
            'id': label, 'key': key, 'got': round(float(got), 4),
            'locked': round(float(locked), 4), 'delta': round(delta, 4),
        }
    return None


def lock_problems(got: dict, locked: dict, slack=SLACK, count_rel=COUNT_REL):
    """Differences larger than the slack. Empty means the behaviour held."""
    problems = []
    if locked.get('ground_truth') is not False:
        problems.append({'problem': 'lock file claims a ground truth these recordings do not have'})
    got_rows = {row['id']: row for row in got.get('rows') or []}
    for ref in locked.get('rows') or []:
        row = got_rows.get(ref['id'])
        if row is None:
            problems.append({'id': ref['id'], 'problem': 'missing'})
            continue
        if row.get('sha256') != ref.get('sha256'):
            problems.append({'id': ref['id'], 'problem': 'checksum', 'got': row.get('sha256'), 'locked': ref.get('sha256')})
            continue
        count = ref.get('n_notes')
        if count is None or row.get('n_notes') is None:
            problems.append({'id': ref['id'], 'key': 'n_notes', 'problem': 'missing metric'})
        else:
            allowed = max(count_rel * float(count), 0.0)
            # At least one note of room when the take is short, so a single
            # boundary note does not fail a deterministic re-run. A 2% move
            # on a long take still fails.
            allowed = max(allowed, 1.0)
            if abs(int(row['n_notes']) - int(count)) > allowed:
                problems.append({
                    'id': ref['id'], 'key': 'n_notes', 'got': row['n_notes'], 'locked': count,
                    'delta': int(row['n_notes']) - int(count),
                })
        for key in TIME_KEYS:
            item = _delta_problem(ref['id'], key, row.get(key), ref.get(key), slack)
            if item:
                problems.append(item)
        got_pc = row.get('pitch_class') or []
        ref_pc = ref.get('pitch_class') or []
        if len(got_pc) != 12 or len(ref_pc) != 12:
            problems.append({'id': ref['id'], 'key': 'pitch_class', 'problem': 'missing metric'})
        else:
            for index, (g, r) in enumerate(zip(got_pc, ref_pc)):
                item = _delta_problem(ref['id'], f'pitch_class_{index}', g, r, slack)
                if item:
                    problems.append(item)
    got_pairs = {(p['src'], p['dst']): p for p in got.get('pairs') or []}
    for ref in locked.get('pairs') or []:
        pair = got_pairs.get((ref['src'], ref['dst']))
        label = f"{ref['src']} -> {ref['dst']}"
        if pair is None:
            problems.append({'id': label, 'problem': 'missing pair'})
            continue
        for key in PAIR_KEYS:
            item = _delta_problem(label, key, pair.get(key), ref.get(key), slack)
            if item:
                problems.append(item)
    return problems


def recordings_gate_action(root=None) -> str:
    """``skip`` without the files, ``checksum`` when the bytes differ, ``no-transcriber``
    without Riley, else ``run``."""
    from benchmarks.recordings.score import audio_ready, present_files
    files = present_files(root)
    if any(digest is None for _name, _path, digest, _expected in files):
        return 'skip'
    if not audio_ready(root):
        return 'checksum'
    from server.transcribers import availability
    if not availability().get('riley', {}).get('installed'):
        return 'no-transcriber'
    return 'run'


def run_recordings_gate(root=None):
    """Score the private takes and compare them to the committed lock.

    Returns the list of moves. Raises FileNotFoundError if the lock is missing.
    """
    import json

    from benchmarks.recordings.score import LOCK, score_recordings

    if not LOCK.is_file():
        raise FileNotFoundError(f'locked recording behaviour missing: {LOCK.name}')
    locked = json.loads(LOCK.read_text())
    got = score_recordings(root)
    return lock_problems(got, locked)

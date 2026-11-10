"""No-drop checks for the regression library.

The public fast clips stay a two-sided match (±0.02) against
``reference/basic_pitch_fast.json``. EGSet12 and Guitar-TECHS are a one-sided
floor: a score may rise, and a drop larger than the slack fails. Both checks
live here so a transcription change that lowers a locked number fails the
same gate.

When the new datasets are not on disk the electric check is a skip, not a
failure. CI stays green without them.
"""
from __future__ import annotations

from benchmarks.regression.electric import BASELINE

# Same tolerance as the committed fast-clip match.
CLIP_SLACK = 0.02
# A broad small drop across a category still fails, even when no single clip exceeds CLIP_SLACK.
CATEGORY_SLACK = 0.01
CLIP_KEYS = ('note_f1', 'note_f1_100', 'onset_f1', 'pitch_recall_300ms')

DOWNLOAD_HINT = (
    'Download with: python -m benchmarks.regression.download '
    '(see benchmarks/regression/README.md). '
    'The sets are CC BY 4.0 evaluation material and are not in git.'
)


def _index(rows):
    return {row['id']: row for row in rows if row.get('id')}


def match_problems(got_rows, locked_rows, keys, slack=CLIP_SLACK):
    """Two-sided differences larger than ``slack``. This is the public fast clip gate."""
    locked = _index(locked_rows)
    got = _index(got_rows)
    problems = []
    for clip_id, ref in locked.items():
        row = got.get(clip_id)
        if row is None or row.get('status') not in (None, 'ok'):
            problems.append({'id': clip_id, 'problem': 'missing'})
            continue
        for key in keys:
            if ref.get(key) is None:
                continue
            if row.get(key) is None:
                problems.append({'id': clip_id, 'key': key, 'problem': 'missing metric'})
                continue
            delta = float(row[key]) - float(ref[key])
            if abs(delta) > slack:
                problems.append({
                    'id': clip_id, 'key': key, 'got': float(row[key]),
                    'locked': float(ref[key]), 'delta': delta,
                })
        if 'cross_f1' in ref and ref.get('cross_f1') is not None:
            if row.get('cross_f1') is None or abs(float(row['cross_f1']) - float(ref['cross_f1'])) > slack:
                problems.append({
                    'id': clip_id, 'key': 'cross_f1',
                    'got': row.get('cross_f1'), 'locked': ref['cross_f1'],
                })
    return problems


def drop_problems(got_rows, locked_rows, keys=CLIP_KEYS, slack=CLIP_SLACK):
    """Metrics that fell by more than ``slack``. An improvement is not a drop."""
    locked = _index(locked_rows)
    got = _index(got_rows)
    problems = []
    for clip_id, ref in locked.items():
        row = got.get(clip_id)
        if row is None or row.get('status') != 'ok':
            problems.append({'id': clip_id, 'problem': row.get('status') if row else 'missing'})
            continue
        if row.get('sha256_ok') is False:
            problems.append({'id': clip_id, 'problem': 'checksum'})
            continue
        for key in keys:
            if ref.get(key) is None:
                continue
            if row.get(key) is None:
                problems.append({'id': clip_id, 'key': key, 'problem': 'missing metric'})
                continue
            delta = float(row[key]) - float(ref[key])
            if delta < -slack:
                problems.append({
                    'id': clip_id, 'key': key, 'got': round(float(row[key]), 4),
                    'locked': round(float(ref[key]), 4), 'delta': round(delta, 4),
                })
    return problems


def category_drop_problems(got_means, locked_means, slack=CATEGORY_SLACK):
    problems = []
    for name, locked in (locked_means or {}).items():
        if locked is None:
            continue
        got = (got_means or {}).get(name)
        if got is None:
            problems.append({'category': name, 'problem': 'missing'})
            continue
        delta = float(got) - float(locked)
        if delta < -slack:
            problems.append({
                'category': name, 'got': round(float(got), 4),
                'locked': round(float(locked), 4), 'delta': round(delta, 4),
            })
    return problems


def assert_within(got_rows, locked_rows, keys, slack=CLIP_SLACK):
    problems = match_problems(got_rows, locked_rows, keys, slack=slack)
    if problems:
        raise AssertionError(f'locked baseline moved by more than {slack}: {problems}')


def assert_no_drop(got_rows, locked_rows, keys=CLIP_KEYS, slack=CLIP_SLACK,
                   got_means=None, locked_means=None, got_means_100=None, locked_means_100=None):
    problems = drop_problems(got_rows, locked_rows, keys=keys, slack=slack)
    problems += [{'kind': 'category', **item} for item in category_drop_problems(got_means, locked_means)]
    problems += [{'kind': 'category_f1_100', **item}
                 for item in category_drop_problems(got_means_100, locked_means_100)]
    if problems:
        raise AssertionError(f'scores dropped below the locked baseline: {problems}')


def _means(rows, key):
    buckets = {}
    for row in rows:
        if row.get('status') != 'ok' or row.get(key) is None:
            continue
        buckets.setdefault(row['category'], []).append(float(row[key]))
    return {name: round(sum(values) / len(values), 4) for name, values in sorted(buckets.items())}


def electric_gate_action():
    """``skip`` without the datasets, ``no-transcriber`` without a runnable model, else ``run``."""
    from benchmarks.regression import catalog
    summary = catalog.available_summary()
    if not summary['egset12'] and not summary['guitar_techs']:
        return 'skip'
    from server.models import capabilities
    from server.transcribers import availability, default_backend
    default = default_backend()
    if default == 'basic_pitch':
        if not capabilities()['transcription']['configured']:
            return 'no-transcriber'
    elif not availability().get(default, {}).get('installed'):
        return 'no-transcriber'
    return 'run'


def backends_for_gate():
    """The default transcriber, plus the other of Basic Pitch and Riley when that one is installed."""
    from server.models import capabilities
    from server.transcribers import availability, default_backend
    info = availability()
    default = default_backend()
    names = []
    if default == 'basic_pitch':
        if capabilities()['transcription']['configured']:
            names.append('basic_pitch')
        if info.get('riley', {}).get('installed'):
            names.append('riley')
    else:
        names.append(default)
        if capabilities()['transcription']['configured']:
            names.append('basic_pitch')
    return names


def run_electric_gate(backends=None):
    """Score the sets that are on disk and compare them to ``electric_baseline.json``.

    Returns the list of drops. Raises FileNotFoundError if the lock file is missing.
    """
    import json

    from benchmarks.regression import catalog
    from benchmarks.regression.score import score_egset12, score_guitar_techs

    if not BASELINE.is_file():
        raise FileNotFoundError(f'locked baseline missing: {BASELINE.name}')
    locked = json.loads(BASELINE.read_text())
    summary = catalog.available_summary()
    problems = []
    names = list(backends or backends_for_gate())
    if not names:
        return [{'problem': 'no transcriber'}]
    for backend in names:
        body = (locked.get('backends') or {}).get(backend)
        if body is None:
            problems.append({'backend': backend, 'problem': 'no locked baseline'})
            continue
        got = []
        if summary['egset12']:
            got.extend(score_egset12(backend))
        if summary['guitar_techs']:
            got.extend(score_guitar_techs(backend))
        locked_rows = [
            row for row in body.get('rows') or []
            if (row['id'].startswith('egset_') and summary['egset12'])
            or (row['id'].startswith('techs_') and summary['guitar_techs'])
        ]
        got_means = _means(got, 'note_f1')
        got_means_100 = _means(got, 'note_f1_100')
        locked_means = {key: value for key, value in (body.get('categories') or {}).items() if key in got_means}
        locked_100 = {key: value for key, value in (body.get('categories_f1_100') or {}).items() if key in got_means_100}
        found = drop_problems(got, locked_rows)
        found += [{'kind': 'category', **item} for item in category_drop_problems(got_means, locked_means)]
        found += [{'kind': 'category_f1_100', **item} for item in category_drop_problems(got_means_100, locked_100)]
        for item in found:
            item['backend'] = backend
        problems.extend(found)
    return problems

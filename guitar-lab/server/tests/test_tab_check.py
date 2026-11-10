import numpy as np

from server import tab_check as tc


def _placed():
    """Two parts on the recording's clock: 60 s of a line, and a part that only plays late."""
    line = [{'time': 0.5 + 0.25 * i, 'duration': 0.2, 'midi': 52 + (i * 5) % 12} for i in range(236)]
    late = [{'time': 40.2 + 0.5 * i, 'duration': 0.4, 'midi': 64 + i % 3} for i in range(38)]
    return [{'name': 'Line', 'notes': line}, {'name': 'Late', 'notes': late}]


def _onsets(notes, length_s=62.0, miss_every=0):
    """An onset map with a hit at each given note (optionally leaving some out)."""
    m = np.zeros((int(length_s * tc.FPS), 88), np.float32)
    for i, n in enumerate(notes):
        if miss_every and i % miss_every == 0:
            continue
        m[int(round(n['time'] * tc.FPS)), n['midi'] - tc.LOW] = 0.9
    return tc.widen(m)


def test_notes_in_the_recording_are_confirmed_and_wrong_ones_are_not():
    placed = _placed()
    played = placed[0]['notes'] + placed[1]['notes']
    res = tc.check(placed, _onsets(played, miss_every=10))
    assert [p['name'] for p in res['parts']] == ['Line', 'Late']
    assert 0.85 < res['parts'][0]['confirmed'] <= 0.92            # one note in ten was not played
    assert all(s['status'] == 'confirmed' and s['control'] < 0.1 for s in res['stretches'])
    assert placed[0]['notes'][0]['confirmed'] is False and placed[0]['notes'][1]['confirmed'] is True
    # The same tab with every pitch one fret out: nothing is confirmed.
    wrong = [{'name': t['name'], 'notes': [dict(n, midi=n['midi'] + 1) for n in t['notes']]} for t in _placed()]
    off = tc.check(wrong, _onsets(played))
    assert off['confirmed'] < 0.1 and all(s['status'] == 'not_confirmed' for s in off['stretches'])


def test_a_stretch_where_the_tab_and_the_recording_disagree_is_reported():
    placed = _placed()
    # The recording follows the tab for 30 s, then plays something else on a dense steady pulse.
    played = [n for n in placed[0]['notes'] if n['time'] < 30]
    played += [{'time': 30 + 0.05 * i, 'midi': 40 + (i * 7) % 40} for i in range(640)]
    res = tc.check(placed, _onsets(played))
    by = {(s['start'], s['end']): s['status'] for s in res['stretches']}
    assert by[(0.0, 20.0)] == 'confirmed'
    assert res['stretches'][-1]['status'] == 'not_confirmed' and res['stretches'][-1]['end'] == 60.0
    assert res['parts'][1]['confirmed'] < 0.4                     # the late part is in the stretch that differs


def test_an_empty_tab_gives_an_empty_report():
    assert tc.check([{'name': 'x', 'notes': []}], np.zeros((100, 88), np.float32)) == {
        'parts': [{'name': 'x', 'notes': 0, 'confirmed': 0.0}], 'stretches': [], 'confirmed': 0.0}

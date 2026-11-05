"""Heard-only metrics and the chroma alignment lock. No transcription model."""
import numpy as np

from benchmarks.heard_metrics import collapse_unisons, score_heard
from benchmarks.score_alignment import align_linear, place_chroma, stretch_chroma


def test_unison_collapse_counts_a_doubled_attack_once():
    # Two tab tracks, same pitch, 10 ms apart, plus one real extra note.
    ref = [
        {'time': 1.00, 'midi': 40, 'amplitude': .5},
        {'time': 1.01, 'midi': 40, 'amplitude': .9},
        {'time': 1.50, 'midi': 47, 'amplitude': .8},
    ]
    assert len(collapse_unisons(ref)) == 2
    est = [{'time': 1.02, 'midi': 40, 'amplitude': .7}]
    # Missing the fifth must cost one miss, not be hidden by the doubled root.
    s = score_heard(est, ref, tol=0.05)
    assert s['n_ref'] == 2 and s['hits'] == 1
    assert s['recall'] == 0.5


def test_timing_is_separate_from_pitch():
    ref = [{'time': i * 0.5, 'midi': 60 + (i % 3), 'duration': .2} for i in range(6)]
    # Right pitches, every onset 80 ms late: fails ±50 ms, still a pitch match at ±300 ms.
    late = [{'time': n['time'] + 0.08, 'midi': n['midi'], 'duration': .2} for n in ref]
    s = score_heard(late, ref, tol=0.05, loose=0.30)
    assert s['f1'] == 0
    assert s['pitch_recall_loose'] == 1
    assert s['timing_given_pitch'] == 0
    assert 0.07 < s['median_abs_onset_s'] < 0.09
    on_time = score_heard(ref, ref)
    assert on_time['f1'] == 1 and on_time['timing_given_pitch'] == 1


def test_chroma_alignment_recovers_a_known_stretch_without_note_f1():
    # Unique pitch-class sequence so a repeating riff cannot lock a bar late.
    frames = 80
    score = np.zeros((12, frames))
    for i in range(frames):
        score[(i * 5 + (i // 7)) % 12, i] = 1.0
        score[(i * 5 + (i // 7) + 4) % 12, i] = 0.4
    hop = 0.1
    alpha, lag_s = 1.06, 2.5
    audio = place_chroma(stretch_chroma(score, alpha), lag_s / hop)
    best, _attempts = align_linear(
        score, audio, hop, anchor_a=(4, 16), anchor_b=(48, 16),
        alphas=np.round(np.arange(0.98, 1.12, 0.01), 2))
    assert abs(best['alpha'] - alpha) <= 0.011
    assert abs(best['origin_s'] - lag_s) <= hop


def test_one_anchor_is_the_chroma_peak_not_the_f1_line():
    from benchmarks.score_alignment import ONE_FROZEN
    anchor = ONE_FROZEN['intro_anchor']
    assert abs((anchor['audio_s'] - anchor['tab_s']) - ONE_FROZEN['origin_s']) < 0.05
    assert ONE_FROZEN['historical_f1_max_map']['used'] is False
    assert ONE_FROZEN['whole_song_linear_map'] is None
    # The rejected line does not pass through the intro peak.
    rejected = ONE_FROZEN['historical_f1_max_map']
    predicted = rejected['origin_s'] + rejected['alpha'] * anchor['tab_s']
    assert abs(predicted - anchor['audio_s']) > 2.0

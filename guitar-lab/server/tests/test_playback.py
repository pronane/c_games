"""Dual playback: acoustic voice tuning/sustain/articulation and the distorted approximation."""
import numpy as np

from server.fx.playback import (ks_pluck, note_start, plan, render_acoustic, render_distorted,
                                amp, drive_curve_from_stem)
from server.fx.undo import acoustic_playback

SR = 22050


def _cents(y, f, sr=SR):
    seg = y[int(.05 * sr):int(.4 * sr)] * np.hanning(int(.4 * sr) - int(.05 * sr))
    Y = np.abs(np.fft.rfft(seg, 2**20))
    fr = np.fft.rfftfreq(2**20, 1 / sr)
    m = (fr > f * 2 ** (-1 / 12)) & (fr < f * 2 ** (1 / 12))
    return 1200 * np.log2(fr[m][np.argmax(Y[m])] / f)


def _fund_db(y, f, at, sr=SR):
    seg = y[int(at * sr):int(at * sr) + 2048]
    t = np.arange(len(seg)) / sr
    return 20 * np.log10(abs(np.sum(seg * np.exp(-2j * np.pi * f * t))) + 1e-12)


def test_tuned_voice_is_in_tune_high_and_low():
    # Old voice: C5 ~ -14 cents, C6 ~ -35 cents at 22.05 kHz-ish rates.
    for midi in (40, 64, 72, 84, 88):
        f = 440 * 2 ** ((midi - 69) / 12)
        assert abs(_cents(ks_pluck(f, SR, SR), f)) < 2.0, midi


def test_high_notes_sustain():
    f = 440 * 2 ** ((84 - 69) / 12)  # C6
    y = ks_pluck(f, 2 * SR, SR)
    # fundamental still within 25 dB of the attack half a second later (old voice: ~-70 dB)
    assert _fund_db(y, f, .5) - _fund_db(y, f, .03) > -25


def test_time_key_is_the_start():
    n = {'time': 1.0, 'duration': .4, 'midi': 64}
    assert note_start(n) == 1.0
    y = acoustic_playback([n], sr=SR, length_s=2.0)
    assert np.max(np.abs(y[:int(.95 * SR)])) < 1e-6  # silent before the note
    assert np.max(np.abs(y[int(1.0 * SR):int(1.3 * SR)])) > .1


def test_repick_stops_the_string_and_palm_mute_is_short():
    notes = [{'time': 0.0, 'duration': 2.0, 'midi': 52, 'string': 5, 'letRing': True},
             {'time': 0.5, 'duration': .3, 'midi': 50, 'string': 5}]
    p = plan(notes)
    assert p[0][3] <= 0.52  # first note's ring cut at the re-pick
    pm = plan([{'time': 0, 'duration': 1.0, 'midi': 40, 'palmMute': True}])
    assert pm[0][3] <= .25
    lr = plan([{'time': 0, 'duration': .5, 'midi': 40, 'letRing': True}])
    assert lr[0][3] > 2.0


def test_bend_raises_pitch():
    f = 440 * 2 ** ((64 - 69) / 12)
    n = {'time': 0, 'duration': 1.0, 'midi': 64, 'bend': [[0, 2], [1, 2]]}
    y = render_acoustic([n], sr=SR, length_s=1.2, body=False)
    assert abs(_cents(y, f * 2 ** (2 / 12)) - 0) < 5


def test_distorted_is_compressed_and_finite():
    notes = [{'time': .1 * i, 'duration': .1, 'midi': 40, 'palmMute': True, 'track': 0} for i in range(10)]
    notes += [{'time': 1.0, 'duration': 1.0, 'midi': m, 'track': 1} for m in (40, 47, 52)]
    rep = {}
    d = render_distorted(notes, sr=SR, length_s=2.5, report=rep)
    a = render_acoustic(notes, sr=SR, length_s=2.5, stereo=True)
    assert d.shape == a.shape and np.isfinite(d).all()
    crest = lambda x: np.max(np.abs(x)) / (np.sqrt(np.mean(x[int(1.1 * SR):int(1.9 * SR)] ** 2)) + 1e-12)
    assert crest(d) < crest(a)
    assert rep['label'] == 'distorted playback approximation'


def test_clean_gain_is_nearly_linear():
    x = 0.5 * np.sin(2 * np.pi * 220 * np.arange(SR) / SR)
    y = amp(x, SR, gain=1.0)
    Y = np.abs(np.fft.rfft(y[SR // 4:]))
    f = np.fft.rfftfreq(len(y) - SR // 4, 1 / SR)
    h3 = Y[np.argmin(abs(f - 660))] / Y[np.argmin(abs(f - 220))]
    assert h3 < .05


def test_drive_follows_stem_tone():
    sr = SR
    t = np.arange(8 * sr) / sr
    rng = np.random.default_rng(0)
    clean = np.concatenate([np.exp(-3 * (t[:sr] )) * np.sin(2 * np.pi * 196 * t[:sr])] * 4)
    dist = np.tanh(40 * (np.sin(2 * np.pi * 98 * t[:4 * sr]) + .2 * rng.standard_normal(4 * sr))) * .5
    stem = np.concatenate([clean * .5, dist])
    g, tones = drive_curve_from_stem(stem, sr, lambda x: x, 8.0, sr, win_s=2.0, hop_s=1.0)
    assert g[int(1.5 * sr)] < g[int(6.5 * sr)]

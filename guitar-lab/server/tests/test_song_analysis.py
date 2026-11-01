import xml.etree.ElementTree as ET
import numpy as np
import pytest
from server import song_analysis as sa

STANDARD = [64, 59, 55, 50, 45, 40]
HALF_DOWN = [63, 58, 54, 49, 44, 39]


def notes_from(pitches, step=.3, start=0., dur=.25):
    return [{'id': i, 'time': start+i*step, 'duration': dur, 'midi': p, 'amplitude': .8} for i, p in enumerate(pitches)]


def test_fingering_keeps_hand_in_one_position_and_matches_pitch():
    # A minor arpeggio around the open position
    notes = notes_from([45, 52, 57, 60, 64, 60, 57, 52])
    tab = sa.fingering(notes, STANDARD)
    for n in tab:
        assert STANDARD[n['string']-1]+n['fret'] == n['midi']
    assert max(n['fret'] for n in tab) <= 3


def test_fingering_chord_uses_distinct_strings():
    chord = [{'id': i, 'time': 1., 'duration': .5, 'midi': m, 'amplitude': .8} for i, m in enumerate([40, 47, 52, 56, 59, 64])]
    tab = sa.fingering(chord, STANDARD)
    assert len({n['string'] for n in tab}) == 6
    assert [n['fret'] for n in sorted(tab, key=lambda n: n['string'])] == [0, 0, 1, 2, 2, 0]   # open E major


def test_out_of_range_note_has_no_tab_position():
    tab = sa.fingering(notes_from([39]), STANDARD)
    assert tab[0]['string'] is None and tab[0]['fret'] is None
    tab = sa.fingering(notes_from([39]), HALF_DOWN)
    assert tab[0]['string'] == 6 and tab[0]['fret'] == 0


def test_key_estimation_a_minor_and_flat_spelling():
    profile = np.zeros(12)
    for pc, w in {9: 5, 0: 4, 4: 4, 2: 2, 5: 3, 7: 3, 11: 2}.items():
        profile[pc] = w
    k = sa.estimate_key(profile)
    assert k['key'] == 'A minor' and k['fifths'] == 0
    assert sa.key_name(3, 'major') == 'Eb major' and sa.key_fifths(3, 'major') == -3


def test_tuning_suggestion_detects_half_step_down():
    played = notes_from([39, 39, 46, 51, 39, 44, 51])
    tunings = {'standard': STANDARD, 'half_step_down': HALF_DOWN, 'drop_d': [64, 59, 55, 50, 45, 38]}
    s = sa.suggest_tuning(played, 3.0, tunings)
    assert s['suggested'] == 'half_step_down'
    assert 'standard' not in s['options']
    assert any('tuned down' in r for r in s['reasons'])


def test_tuning_suggestion_reports_reference_offset():
    s = sa.suggest_tuning(notes_from([40, 40, 45]), 30.0, {'standard': STANDARD})
    assert s['suggested'] == 'standard' and s['reference_a4_hz'] == pytest.approx(447.7, abs=.1)
    assert any('+30 cents' in r for r in s['reasons'])


def test_bar_roles_lead_vs_rhythm():
    bars = [0., 2., 4.]
    rhythm = [{'time': t, 'duration': .4, 'midi': m, 'amplitude': .8} for t in (0, .5, 1, 1.5) for m in (45, 52, 57, 60)]
    lead = notes_from([69, 71, 72, 74, 76, 74], step=.3, start=2.)
    roles = sa.bar_roles(rhythm+lead, bars, 6.)
    assert [r['role'] for r in roles] == ['rhythm', 'lead', 'rest']
    assert sa.summarise_roles(roles) == 'lead and rhythm'


def test_chords_per_beat_finds_progression():
    def chroma(pcs):
        c = np.full(12, .02)
        c[list(pcs)] = 1
        return c
    beats = np.stack([chroma({9, 0, 4})]*4+[chroma({5, 9, 0})]*4+[chroma({0, 4, 7})]*4+[chroma({7, 11, 2})]*4, axis=1)
    labels = sa.chords_per_beat(beats)
    segs = sa.chord_segments(labels, [i*.6 for i in range(16)])
    assert [s['chord'] for s in segs] == ['Am', 'F', 'C', 'G']


def test_musicxml_is_valid_and_every_bar_is_full():
    beats = [i*.6 for i in range(40)]
    notes = sa.fingering(notes_from([45, 52, 57, 60, 64, 60, 57, 52]*3, step=.3, start=.0, dur=.5), STANDARD)
    xml = sa.musicxml(notes, beats, {'fifths': 0, 'mode': 'minor'}, STANDARD,
                      chords=[{'chord': 'Am', 'start': 0, 'end': 4.8}, {'chord': 'F', 'start': 4.8, 'end': 9}])
    root = ET.fromstring(xml.split('\n', 2)[2])
    measures = root.findall('.//measure')
    assert len(measures) >= 3
    for m in measures:
        total = sum(int(n.find('duration').text) for n in m.findall('note') if n.find('chord') is None)
        assert total == 16, f'bar {m.get("number")} has {total} sixteenths'
    struck = [n for n in root.findall('.//note') if n.find('pitch') is not None
              and not any(t.get('type') == 'stop' for t in n.findall('tie'))]
    assert len(struck) == len(notes)
    assert all(n.find('notations/technical/fret') is not None for n in struck)
    assert [h.find('root/root-step').text for h in root.findall('.//harmony')] == ['A', 'F']
    tuning = root.findall('.//staff-tuning')
    assert len(tuning) == 6 and tuning[0].find('tuning-step').text == 'E'


def test_pan_parts_splits_hard_panned_guitars():
    sr = 22050
    t = np.arange(sr*3)/sr
    left = .3*np.sin(2*np.pi*196*t)*(np.sin(2*np.pi*2*t) > 0)
    right = .3*np.sin(2*np.pi*659*t)*(np.sin(2*np.pi*3*t) > 0)
    stem = np.stack([left, right], axis=1).astype(np.float32)
    parts = sa.pan_parts(stem, sr)
    assert [p[0] for p in parts] == ['left', 'right']
    total = sum(p[1] for p in parts)
    assert np.max(np.abs(total-stem)) < 1e-3          # parts sum back to the stem
    assert sa.pan_parts(np.stack([left, left], axis=1), sr)[0][0] == 'centre'


def test_presence_labels():
    sr = 8000
    loud = np.ones((sr*4, 2), np.float32)*.5
    quiet = np.ones((sr*4, 2), np.float32)*.001
    rows = {r['stem']: r['verdict'] for r in sa.presence({'guitar': loud, 'other': quiet}, sr, 1.)}
    assert rows == {'guitar': 'present', 'other': 'absent'}


def test_bleed_bars_flags_leakage_but_keeps_a_quiet_real_part():
    edges = [0., 2., 4., 6.]
    # bar 1: only rhythm (left). bar 2: lead on the right, its leakage in the centre.
    # bar 3: a quieter centre lead playing different notes from the left rhythm.
    levels = {'left': [.065, .06, .066], 'centre': [.003, .024, .029], 'right': [.0, .07, .01]}
    lead_a = notes_from([71, 74, 76, 74], step=.4, start=2.)
    lead_b = notes_from([79, 78, 76, 74], step=.4, start=4.)
    rhythm = [{'time': t, 'duration': .3, 'midi': m, 'amplitude': .8} for t in (0, 1, 2, 3, 4, 5) for m in (40, 47)]
    notes = {'left': rhythm, 'centre': lead_a+lead_b, 'right': lead_a+[dict(n, amplitude=.3) for n in lead_b]}
    bleed = sa.bleed_bars(levels, notes, edges)
    assert bleed['left'] == [False, False, False]
    assert bleed['centre'] == [True, True, False]      # silent, then overlap leakage, then real
    assert bleed['right'] == [True, False, True]       # silent, real lead, then copy of centre lead
    roles = sa.bar_roles(notes['right'], [0., 2., 4.], 6., bleed=bleed['right'])
    assert [r['role'] for r in roles] == ['rest', 'lead', 'rest'] and roles[2]['bleed']


def test_power_chords_count_as_rhythm():
    power = [{'time': t, 'duration': .3, 'midi': m, 'amplitude': .8} for t in (0, .5, 1, 1.5) for m in (40, 47)]
    assert sa.bar_roles(power, [0.], 2.)[0]['role'] == 'rhythm'


def test_key_prior_keeps_minor_chord_despite_major_third_harmonic():
    def chroma(pcs, extra=()):
        c = np.full(12, .02)
        c[list(pcs)] = 1
        for p in extra:
            c[p] = .9
        return c
    # E minor with a strong G# (harmonic of E) -> without the key the major chord can win.
    beats = np.stack([chroma({4, 7, 11}, extra=(8,))]*4, axis=1)
    key = {'key': 'E minor', 'tonic': 4, 'mode': 'minor', 'fifths': 1}
    assert set(sa.chords_per_beat(beats, key)) == {'Em'}


def test_resolve_mode_uses_tonic_chord():
    key = {'key': 'G major', 'tonic': 7, 'mode': 'major', 'fifths': 1, 'alternatives': ['E minor', 'C major']}
    segs = [{'chord': c, 'start': i*2., 'end': i*2.+2} for i, c in enumerate(['Em', 'C', 'G', 'D']*4)]
    resolved = sa.resolve_mode(key, segs)
    assert resolved['key'] == 'E minor' and resolved['tonic'] == 4 and resolved['fifths'] == 1
    assert 'G major' in resolved['alternatives']
    segs = [{'chord': c, 'start': i*2., 'end': i*2.+2} for i, c in enumerate(['G', 'Em', 'C', 'D']*4)]
    assert sa.resolve_mode(key, segs)['key'] == 'G major'


def test_beat_grid_fits_steady_tempo():
    sr = 22050
    period = 60/110
    y = np.zeros(int(sr*30), np.float32)
    for k in range(int(30/period)):
        i = int(k*period*sr)
        burst = np.random.default_rng(k).standard_normal(3000)*np.exp(-np.arange(3000)/400)
        y[i:i+3000] += (burst*(1 if k % 4 == 0 else .5)).astype(np.float32)[:len(y)-i]
    grid = sa.beat_grid(y, sr, y)
    assert abs(grid['bpm']-110) < 1
    assert abs(grid['bars'][4]-grid['bars'][0]-16*period) < .1


def test_overtone_ghosts_removed_only_in_lead_bars():
    lead = notes_from([74, 76, 74], step=.4, start=2.)
    ghosts = [dict(n, midi=n['midi']+12, amplitude=.5) for n in lead]
    chord = [{'time': .5, 'duration': .3, 'midi': m, 'amplitude': .8} for m in (40, 47, 52)]
    roles = [{'start': 0., 'end': 2., 'role': 'rhythm'}, {'start': 2., 'end': 4., 'role': 'lead'}]
    kept = sa.drop_overtones(lead+ghosts+chord, roles)
    assert sorted(n['midi'] for n in kept) == [40, 47, 52, 74, 74, 76]


def test_downbeat_follows_chord_changes_when_bass_hits_every_beat():
    sr = 22050
    period = .5
    beats = np.arange(0, 16)*period
    t = np.arange(int(sr*8))/sr
    # Chords change every 4 beats starting on beat index 1 (so beat one is phase 1).
    harmonic = np.zeros_like(t)
    for bar, root in enumerate([220, 174.6, 261.6, 196]):
        a, b = (1+4*bar)*period, (5+4*bar)*period
        sel = (t >= a) & (t < b)
        harmonic[sel] = np.sin(2*np.pi*root*t[sel])+np.sin(2*np.pi*root*1.26*t[sel])
    assert sa.downbeat_phase(beats, sr, None, harmonic.astype(np.float32)) == 1


def _phrase(sr, notes, step=.25):
    out = []
    for m in notes:
        t = np.arange(int(sr*step))/sr
        f = 440*2**((m-69)/12)
        out.append((np.sin(2*np.pi*f*t)+.4*np.sin(4*np.pi*f*t))*np.exp(-t*4))
    return np.concatenate(out).astype(np.float32)


def test_locate_finds_the_take_and_flags_repeats():
    sr = 22050
    verse = _phrase(sr, [64, 67, 71, 67]*4)            # bars 1-2
    chorus = _phrase(sr, [69, 72, 76, 72, 74, 77, 81, 77]*2)  # bars 3-4, and again at 7-8
    bridge = _phrase(sr, [62, 66, 69, 66]*4)           # bars 5-6
    song = np.concatenate([verse, chorus, bridge, chorus])
    bars = [i*2.0 for i in range(8)]
    # A take of the bridge played on a different-sounding instrument, a little slower.
    import librosa
    take = librosa.effects.time_stretch(_phrase(sr, [62, 66, 69, 66]*4)*.5, rate=.95)
    found = sa.locate(song, take, sr, bars)
    assert found['candidates'][0]['bar'] == 5
    chorus_take = _phrase(sr, [69, 72, 76, 72, 74, 77, 81, 77]*2)
    found = sa.locate(song, chorus_take, sr, bars)
    assert {c['bar'] for c in found['candidates'][:2]} == {3, 7}
    assert found['confidence'] in ('repeated', 'moderate', 'low')
    with pytest.raises(ValueError):
        sa.locate(song, take[:sr], sr, bars)


def test_locate_tolerates_silent_stretches_in_the_reference():
    sr = 22050
    lead = _phrase(sr, [69, 72, 76, 72, 74, 77, 81, 77]*2)
    song = np.concatenate([np.zeros(len(lead), np.float32), lead, np.zeros(len(lead), np.float32)])
    found = sa.locate(song, lead*.7, sr, [i*2.0 for i in range(6)])
    assert found['candidates'][0]['bar'] == 3


def test_webm_video_decodes_audio_only(tmp_path):
    """A downloaded .webm video: the engine reads its audio track through ffmpeg."""
    import shutil
    from pathlib import Path
    from server.songs import decode
    if not shutil.which('ffmpeg'):
        pytest.skip('ffmpeg not installed')
    src = Path(__file__).resolve().parents[2]/'tests/fixtures/tone-video.webm'
    copy = tmp_path/'source'
    shutil.copy(src, copy)
    audio, sr = decode(copy)
    assert sr == 44100 and audio.shape[1] == 2
    assert 5.5 < len(audio)/sr < 6.5
    spectrum = np.abs(np.fft.rfft(audio[:sr, 0]))
    assert abs(np.argmax(spectrum) - 220) < 3      # 1-second window: one bin per Hz

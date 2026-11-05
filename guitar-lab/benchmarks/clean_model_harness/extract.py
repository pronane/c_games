"""Candidate extraction: Basic Pitch at low thresholds + posteriors -> per-candidate features + labels."""
import sys, json, glob
sys.path.insert(0, '/workspace/guitar-lab-test/fx_train'); sys.path.insert(0, '/workspace/guitar-lab-test/guitar-lab-fullband/guitar-lab')
from common import *
import importlib, server.clean_model as cm
B = '/workspace/guitar-lab-test/bands'; G = f'{B}/guitar-techs/raw'; HG = f'{B}/hollow-ground-ill-fate'
M = EffectMatcher()
def items():
    for i in range(1, 13):
        t = f'{i:02d}'
        for src in ('micamp', 'directinput'):
            yield f'techs_p3_{t}_{src}', f'{G}/P3_music/audio/{src}/{src}_{t}.wav', ('midi', f'{G}/P3_music/midi/midi_{t}.mid'), f'techs_p3_{t}'
    for k in ('Bendings', 'Harmonics', 'PalmMute', 'PinchHarmonics', 'Vibrato'):
        for src in ('micamp', 'directinput'):
            yield f'techs_p1_{k}_{src}', f'{G}/P1_techniques/audio/{src}/{src}_{k}.wav', ('midi', f'{G}/P1_techniques/midi/midi_{k}.mid'), f'techs_p1_{k}'
    for di, amps in (('14_ElecGtr1c_DI', ['12_ElecGtr1a_Amp1', '13_ElecGtr1b_Amp2']), ('17_ElecGtr2c_DI', ['15_ElecGtr2a_Amp1', '16_ElecGtr2b_Amp2']), ('19_ElecGtr3b_DI', ['18_ElecGtr3a_Amp'])):
        for a in amps:
            yield f'hollow_{a}', f'{HG}/stems/{a}.wav', ('di', f'{HG}/stems/{di}.wav'), f'hollow_{di[:9]}'
out = {}
ref_cache = {}
for name, path, (rk, rp), group in items():
    y = load(path); dur = len(y) / SR
    if rk == 'midi': ref = midi_notes(rp)
    else:
        if rp not in ref_cache:
            yd = load(rp); ref_cache[rp] = post(transcribe_audio(yd, 'di', 'clean'), 'clean', len(yd) / SR)
        ref = ref_cache[rp]
    det = M.predict(y, SR)
    tone = tone_of(y)
    p = TMP / 'c.wav'; sf.write(p, y, SR, subtype='PCM_16')
    cand, post_ = models.transcribe(str(p), midi_min=36, midi_max=88, posteriors=True, thresholds=cm.CANDIDATE_THRESHOLDS)
    base_raw = models.transcribe(str(p), midi_min=36, midi_max=88, thresholds=models.thresholds_for(tone, False)); p.unlink()
    base = post(base_raw, tone, dur)
    X = cm.candidate_features(cand, post_, cm.clip_fx_vector(det))
    # shift to align (Guitar-TECHS has a small constant lag); computed on baseline only
    s = best_shift(base, ref, -0.2, 0.2, 0.01) if rk == 'midi' else 0.0
    lab = cm.label_candidates(cand, ref, shift=s)
    out[name] = dict(group=group, tone=tone, shift=s, X=X, y=lab, cand=cand, ref=ref, base=base, fx=det['effects'], dur=dur)
    print(name, tone, len(cand), int(lab.sum()), len(ref), f1([dict(n, time=n['time'] + s) for n in base], ref)['f1'], flush=True)
import pickle; pickle.dump(out, open('cands.pkl', 'wb'))

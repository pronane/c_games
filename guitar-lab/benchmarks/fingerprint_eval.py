import sys, json, glob, random, os, time
import numpy as np, librosa, scipy.signal as ss
sys.path.insert(0, '/workspace/guitar-lab-test/guitar-lab-fullband/guitar-lab')
from server import fingerprint as fp
random.seed(0); rng = np.random.default_rng(0)
SR = 22050
def L(p, off=0, dur=None): return librosa.load(p, sr=SR, mono=True, offset=off, duration=dur)[0]
GS = '/workspace/guitar-lab-test/guitarset/mic'; B = '/workspace/guitar-lab-test/bands'
gs = sorted(glob.glob(f'{GS}/*_comp_mic.wav'))
# same progression, different players
by = {}
for p in gs: by.setdefault(os.path.basename(p)[3:], []).append(p)
progs = [k for k, v in by.items() if len(v) >= 2]; random.shuffle(progs)
recs = {'carcassi': '/workspace/guitar-lab-test/data/carcassi_op60_1.wav',
        'hollow_amp_sum': f'{B}/hollow-ground-ill-fate/mix/guitar_AMP_sum_44k.wav',
        'hollow_mix': f'{B}/hollow-ground-ill-fate/mix/mix_44k.wav',
        'techs_amp01': f'{B}/guitar-techs/raw/P3_music/audio/micamp/micamp_01.wav',
        'techs_di02': f'{B}/guitar-techs/raw/P3_music/audio/directinput/directinput_02.wav'}
for k in progs[:6]: recs['gs_' + os.path.basename(by[k][0])[:-8]] = by[k][0]
def reverb(y):
    ir = rng.standard_normal(int(1.2 * SR)) * np.exp(-np.arange(int(1.2 * SR)) / (0.3 * SR)); ir[0] = 3
    z = ss.fftconvolve(y, ir)[:len(y)]; return z / np.abs(z).max()
degr = {
 'excerpt_8s': lambda y: y,
 'noise_10dB': lambda y: y + rng.standard_normal(len(y)) * np.sqrt(np.mean(y**2) / 10),
 'eq_tilt': lambda y: ss.lfilter(*ss.butter(2, [300 / (SR / 2), 3000 / (SR / 2)], 'band'), y) + 0.3 * y,
 'reverb_rt1s': reverb,
 'distortion': lambda y: np.tanh(20 * y / np.abs(y).max()),
 'clipping': lambda y: np.clip(y, -0.2 * np.abs(y).max(), 0.2 * np.abs(y).max()),
 'mp3ish_lp4k_8bit': lambda y: np.round(ss.lfilter(*ss.butter(6, 4000 / (SR / 2)), y) * 128) / 128,
 'excerpt_5s': lambda y: y,
}
rows = []
def run(kind, name, q, ref_idx, truth, extra=None):
    t = time.time(); r = fp.match(q, SR, ref_idx)
    rows.append(dict(kind=kind, name=name, truth=truth, pred=r['matched'], votes=r['votes'], ratio=r['peak_to_next_ratio'], offset=r['offset_s'], tempo=r['tempo_ratio'], secs=round(time.time() - t, 2), **(extra or {})))
    print(json.dumps(rows[-1]), flush=True)
idx = {}
for k, p in recs.items():
    y = L(p, 0, 120); idx[k] = (y, fp.Index(y, SR))
for k, (y, I) in idx.items():
    dur = len(y) / SR
    for d, f in degr.items():
        ln = 5 if d == 'excerpt_5s' else 8
        st = float(rng.uniform(0, max(dur - ln - 0.5, 0.1)))
        q = f(y[int(st * SR):int((st + ln) * SR)].copy()).astype(np.float32)
        run('same_recording', f'{k}|{d}', q, I, True, {'true_offset': round(st, 3)})
    # tempo-stretched excerpt (e.g. MIDI at other tempo): 1.04x
    st = float(rng.uniform(0, max(dur - 9, 0.1))); q = librosa.effects.time_stretch(y[int(st*SR):int((st+8)*SR)], rate=1.04)
    run('same_recording', f'{k}|tempo_1.04', q, I, True, {'true_offset': round(st, 3)})
# cover-type (different performance / signal chain) -> should NOT match
for k in progs[:12]:
    a, b = by[k][0], by[k][1]
    ya = L(a, 5, 10); run('cover_other_player', os.path.basename(a)[:-8] + ' vs ' + os.path.basename(b)[:2], ya, fp.Index(L(b, 0, 120), SR), False)
HG = f'{B}/hollow-ground-ill-fate/stems'
for di, amp in (('14_ElecGtr1c_DI', '12_ElecGtr1a_Amp1'), ('17_ElecGtr2c_DI', '15_ElecGtr2a_Amp1'), ('19_ElecGtr3b_DI', '18_ElecGtr3a_Amp')):
    run('same_take_DI_vs_amp', f'hollow {di} vs {amp}', L(f'{HG}/{di}.wav', 5, 8), fp.Index(L(f'{HG}/{amp}.wav', 0, 120), SR), False)
T = f'{B}/guitar-techs/raw/P3_music/audio'
for i in ('01', '03', '05', '07'):
    run('same_take_DI_vs_amp', f'techs {i} di vs micamp', L(f'{T}/directinput/directinput_{i}.wav', 5, 10), fp.Index(L(f'{T}/micamp/micamp_{i}.wav'), SR), False)
my, _ = fp.render_midi('/workspace/guitar-lab-test/data/carcassi-op60-01.mid', SR)
run('midi_rendering_vs_recording', 'carcassi midi render vs recording', L(recs['carcassi'], 10, 10), fp.Index(my, SR), False)
import glob as g
for mid in sorted(g.glob(f'{B}/guitar-techs/raw/P3_music/midi/*.mid'))[:4]:
    i = mid[-6:-4]; m, _ = fp.render_midi(mid, SR)
    run('midi_rendering_vs_recording', f'techs {i} midi vs DI', L(f'{T}/directinput/directinput_{i}.wav', 5, 10), fp.Index(m, SR), False)
# unrelated
keys = list(idx)
for _ in range(30):
    a, b = random.sample(keys, 2); ya = idx[a][0]; st = int(rng.uniform(0, max(len(ya) - 9 * SR, 1)))
    run('unrelated', f'{a} vs {b}', ya[st:st + 8 * SR], idx[b][1], False)
json.dump(rows, open('fp_rows.json', 'w'), indent=1)

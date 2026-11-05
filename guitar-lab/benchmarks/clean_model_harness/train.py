import sys, json, pickle
sys.path.insert(0, '/workspace/guitar-lab-test/fx_train'); sys.path.insert(0, '/workspace/guitar-lab-test/guitar-lab-fullband/guitar-lab')
from common import f1, post
import numpy as np, server.clean_model as cm
from sklearn.ensemble import GradientBoostingClassifier
D = pickle.load(open('cands.pkl', 'rb'))
import os
VAR = os.environ.get('VAR', 'nofx')
NF = len(cm.FEATURE_NAMES)
for v in D.values():
    if v['X'].shape[1] == NF - 3: v['X'] = cm.add_clip_normalised(v['X'])
FX = [i for i, n in enumerate(cm.FEATURE_NAMES) if n.startswith('fx_')]
KEEP = {'nofx': [i for i in range(NF) if i not in FX], 'all': list(range(NF)),
        'distfx': [i for i in range(NF) if i not in FX or cm.FEATURE_NAMES[i] in ('fx_distortion', 'fx_overdrive', 'fx_clean')]}[VAR]
MASK = np.zeros(NF, bool); MASK[KEEP] = True
for v in D.values():
    v['X'] = v['X'] * MASK  # masked columns become constant 0 -> never split on
groups = sorted({v['group'] for v in D.values()})
# 4 folds over groups, hollow guitars spread across folds
folds = {g: i % 4 for i, g in enumerate(groups)}
def score(names, keepfn, suppress):
    out = []
    for n in names:
        d = D[n]; e = keepfn(d)
        if suppress: e = post(e, 'distorted', d['dur'])
        e = [dict(x, time=x['time'] + d['shift']) for x in e]
        out.append((f1(e, d['ref'], .05)['f1'], f1(e, d['ref'], .1)['f1']))
    return np.array(out)
def fit(train):
    X = np.vstack([D[n]['X'] for n in train]); y = np.concatenate([D[n]['y'] for n in train])
    c = GradientBoostingClassifier(n_estimators=150, max_depth=3, learning_rate=0.1, subsample=0.8, random_state=0).fit(X, y)
    return c
res = {}
TH = np.arange(0.2, 0.81, 0.05)
per = {}
for k in range(4):
    test = [n for n in D if folds[D[n]['group']] == k]
    train = [n for n in D if folds[D[n]['group']] != k]
    c = fit(train)
    for n in train + test: D[n].setdefault('p', {})[k] = c.predict_proba(D[n]['X'])[:, 1] if len(D[n]['X']) else np.zeros(0)
    # choose threshold + suppression on train amp clips
    tr_amp = [n for n in train if 'directinput' not in n]
    best = max(((th, s) for th in TH for s in (0, 1)), key=lambda a: score(tr_amp, lambda d: [c_ for c_, p in zip(d['cand'], d['p'][k]) if p >= a[0]], a[1])[:, 0].mean())
    for n in test:
        d = D[n]
        b = score([n], lambda d: d['base'], False)[0]
        m = score([n], lambda d: [c_ for c_, p in zip(d['cand'], d['p'][k]) if p >= best[0]], best[1])[0]
        per[n] = dict(fold=k, th=round(float(best[0]), 2), sup=best[1], base50=b[0], base100=b[1], model50=m[0], model100=m[1], tone=d['tone'])
        print(n, per[n], flush=True)
def summ(sel):
    a = np.array([[v['base50'], v['model50'], v['base100'], v['model100']] for n, v in per.items() if sel(n)])
    return {'n': len(a), 'base_f1_50': round(a[:, 0].mean(), 3), 'model_f1_50': round(a[:, 1].mean(), 3), 'base_f1_100': round(a[:, 2].mean(), 3), 'model_f1_100': round(a[:, 3].mean(), 3)} if len(a) else None
S = {'techs_p3_amp': summ(lambda n: n.startswith('techs_p3') and 'micamp' in n), 'techs_p1_amp': summ(lambda n: n.startswith('techs_p1') and 'micamp' in n),
     'hollow_amp': summ(lambda n: n.startswith('hollow')), 'techs_p3_DI': summ(lambda n: n.startswith('techs_p3') and 'directinput' in n), 'techs_p1_DI': summ(lambda n: n.startswith('techs_p1') and 'directinput' in n)}
print(json.dumps(S, indent=1))
json.dump({'summary': S, 'per_clip': per}, open(f'cv_results_{VAR}.json', 'w'), indent=1, default=float)
# final model on everything, threshold = median of fold choices
c = fit(list(D)); th = float(np.median([v['th'] for v in per.values()])); sup = int(np.median([v['sup'] for v in per.values()]))
m = cm.export_gbdt(c, th, {'trained_on': 'Guitar-TECHS P1/P3 (DI+micamp, real MIDI, CC BY 4.0) + Hollow Ground amp (DI-derived labels)', 'post_suppression': sup, 'feature_mask': MASK.astype(int).tolist(), 'variant': VAR, 'cv': S})
json.dump(m, open(f'clean_model_{VAR}.json', 'w'))
import os; print('size', os.path.getsize(f'clean_model_{VAR}.json'), 'th', th, 'sup', sup)

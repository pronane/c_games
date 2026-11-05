#!/usr/bin/env python3
"""Build effect templates from GuitarSet mic clips + synthetic FX; evaluate matcher."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

# Allow running as script from anywhere
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fx.features import extract_features, features_vector, FEATURE_NAMES
from fx.renderers import EFFECT_NAMES, apply_effect
from fx.classify import EffectMatcher
from fx.undo import undo_effects, acoustic_playback, damping_from_decay

try:
    import soundfile as sf
except ImportError:
    import librosa
    sf = None


def load_wav(path, sr=44100, max_s=6.0):
    if sf is not None:
        x, file_sr = sf.read(path, always_2d=False)
        x = np.asarray(x, dtype=np.float64)
        if x.ndim > 1:
            x = x.mean(axis=-1)
        if file_sr != sr:
            import librosa
            x = librosa.resample(x, orig_sr=file_sr, target_sr=sr)
    else:
        import librosa
        x, _ = librosa.load(path, sr=sr, mono=True)
    if max_s and len(x) > int(max_s * sr):
        x = x[: int(max_s * sr)]
    peak = np.max(np.abs(x)) + 1e-12
    return (x / peak * 0.9).astype(np.float64)


def find_guitarset_clips(mic_dir: Path, n=8):
    files = sorted(mic_dir.glob('*_solo_mic.wav')) + sorted(mic_dir.glob('*_comp_mic.wav'))
    # Prefer diverse prefixes
    picked = []
    seen = set()
    for f in files:
        key = f.name.split('_')[0]
        if key in seen:
            continue
        seen.add(key)
        picked.append(f)
        if len(picked) >= n:
            break
    if len(picked) < n:
        picked = files[:n]
    return picked


def build_dataset(clips, sr=44100, holdout_frac=0.25, seed=0):
    rng = np.random.default_rng(seed)
    rows = []  # (vec, label, audio_for_holdout_optional)
    for clip in clips:
        clean = load_wav(clip, sr=sr, max_s=6.0)
        for name in EFFECT_NAMES:
            if name == 'clean':
                y = clean
            elif name == 'reverb':
                y = apply_effect(name, clean, sr=sr, rt60=float(rng.uniform(0.8, 1.6)))
            else:
                y = apply_effect(name, clean, sr=sr)
            feats = extract_features(y, sr)
            rows.append({
                'vec': features_vector(feats),
                'label': name,
                'audio': y,
                'clip': clip.name,
                'feats': feats,
            })
    rng.shuffle(rows)
    # Hold out by clip name so train/test don't share the same DI
    clips_u = sorted({r['clip'] for r in rows})
    rng.shuffle(clips_u)
    n_hold = max(1, int(round(len(clips_u) * holdout_frac)))
    hold_clips = set(clips_u[:n_hold])
    train = [r for r in rows if r['clip'] not in hold_clips]
    test = [r for r in rows if r['clip'] in hold_clips]
    return train, test


def fit_optional_rf(train):
    try:
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.multioutput import MultiOutputClassifier
    except ImportError:
        return None
    X = np.stack([r['vec'] for r in train])
    # multi-hot: for synthetic single-label, one-hot
    labels = list(EFFECT_NAMES)
    Y = np.zeros((len(train), len(labels)), dtype=np.int32)
    for i, r in enumerate(train):
        Y[i, labels.index(r['label'])] = 1
    clf = MultiOutputClassifier(
        RandomForestClassifier(n_estimators=80, max_depth=8, random_state=0, n_jobs=1)
    )
    clf.fit(X, Y)
    return clf


def evaluate_matcher(matcher: EffectMatcher, test_rows, use_rf=False):
    labels = list(EFFECT_NAMES)
    # Confusion for primary (argmax excluding chance)
    conf = {a: {b: 0 for b in labels} for a in labels}
    correct = 0
    # multilabel: predicted set contains true
    hit = 0
    for r in test_rows:
        feats = {FEATURE_NAMES[i]: float(r['vec'][i]) for i in range(len(FEATURE_NAMES))}
        # rebuild full feats from stored if present
        feats = r.get('feats', feats)
        scores = matcher.predict_scores(feats)
        ranked = sorted(scores.items(), key=lambda kv: -kv[1])
        pred = ranked[0][0]
        conf[r['label']][pred] += 1
        if pred == r['label']:
            correct += 1
        active = {n for n, s in ranked if s >= matcher.threshold}
        if r['label'] == 'clean':
            # clean: top is clean OR no non-clean above threshold
            if pred == 'clean' or not (active - {'clean'}):
                hit += 1
        elif r['label'] in active or pred == r['label']:
            hit += 1
    n = len(test_rows) or 1
    return {
        'n': len(test_rows),
        'top1_acc': correct / n,
        'threshold_hit_rate': hit / n,
        'confusion': conf,
    }


def per_class_acc(confusion):
    out = {}
    for lab, row in confusion.items():
        tot = sum(row.values())
        out[lab] = (row.get(lab, 0) / tot) if tot else None
    return out


def eval_undo_on_rendered(clean, sr=44100):
    """Measure simple pitch-track F1 proxy before/after undo on distorted+reverb render."""
    import librosa
    from fx.undo import dereverb_spectral

    def notes_pyin(y):
        f0, voiced_flag, _ = librosa.pyin(
            y, fmin=librosa.note_to_hz('E2'), fmax=librosa.note_to_hz('E6'),
            sr=sr, frame_length=2048
        )
        hop = 512
        notes = []
        i = 0
        while i < len(f0):
            if voiced_flag[i] and np.isfinite(f0[i]):
                j = i
                freqs = []
                while j < len(f0) and voiced_flag[j] and np.isfinite(f0[j]):
                    freqs.append(f0[j])
                    j += 1
                midi = float(np.round(librosa.hz_to_midi(np.median(freqs))))
                notes.append({
                    'midi': midi,
                    'start': i * hop / sr,
                    'end': j * hop / sr,
                    'velocity': 0.7,
                })
                i = j
            else:
                i += 1
        return notes

    def f1(ref, est, tol=0.08):
        # onset+pitch match
        matched = 0
        used = set()
        for n in ref:
            for k, m in enumerate(est):
                if k in used:
                    continue
                if abs(n['start'] - m['start']) <= tol and int(n['midi']) == int(m['midi']):
                    matched += 1
                    used.add(k)
                    break
        p = matched / (len(est) or 1)
        r = matched / (len(ref) or 1)
        return 0.0 if p + r == 0 else 2 * p * r / (p + r), matched, len(ref), len(est)

    ref = notes_pyin(clean)
    dirty = apply_effect('distortion', clean, sr=sr)
    dirty = apply_effect('reverb', dirty, sr=sr, rt60=1.1, mix=0.4)
    before = notes_pyin(dirty)
    cleaned = undo_effects(dirty, sr=sr, effects=['distortion', 'reverb'])
    after = notes_pyin(cleaned)
    # Also acoustic playback from ref notes (oracle articulation)
    for n in ref:
        n['damping'] = damping_from_decay(clean, n['start'], n['end'], sr)
    acoustic = acoustic_playback(ref, sr=sr, length_s=len(clean) / sr)

    f1_b, *_ = f1(ref, before)
    f1_a, *_ = f1(ref, after)
    return {
        'note_f1_before_undo': round(f1_b, 3),
        'note_f1_after_undo': round(f1_a, 3),
        'n_ref': len(ref),
        'n_before': len(before),
        'n_after': len(after),
        'acoustic_rms': float(np.sqrt(np.mean(acoustic ** 2))),
    }


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--mic-dir', default='/workspace/guitar-lab-test/guitarset/mic')
    ap.add_argument('--out', default=str(Path(__file__).resolve().parent / 'data' / 'templates.json'))
    ap.add_argument('--report', default='/workspace/guitar-lab-test/fx_eval_report.json')
    ap.add_argument('--n-clips', type=int, default=6)
    ap.add_argument('--head-down', default='/workspace/guitar-lab-test/bands/head-down/stems_excerpt75/Gtr_Riff.wav')
    args = ap.parse_args()

    clips = find_guitarset_clips(Path(args.mic_dir), n=args.n_clips)
    print('clips:', [c.name for c in clips])
    train, test = build_dataset(clips)
    print(f'train={len(train)} test={len(test)}')

    X = np.stack([r['vec'] for r in train])
    y = [r['label'] for r in train]
    matcher = EffectMatcher()
    matcher.labels = list(EFFECT_NAMES)
    matcher.fit_centroids(X, y)
    # Tune threshold on train via simple sweep
    best_t, best_hit = 0.55, -1
    for t in np.linspace(0.35, 0.75, 9):
        matcher.threshold = float(t)
        ev = evaluate_matcher(matcher, train)
        if ev['threshold_hit_rate'] > best_hit:
            best_hit, best_t = ev['threshold_hit_rate'], float(t)
    matcher.threshold = best_t

    rf = fit_optional_rf(train)
    matcher.rf = rf

    ev_test = evaluate_matcher(matcher, test)
    # Also RF top-1 if available
    rf_acc = None
    if rf is not None:
        labels = list(EFFECT_NAMES)
        ok = 0
        for r in test:
            proba = rf.predict_proba(r['vec'].reshape(1, -1))
            scores = []
            for i, lab in enumerate(labels):
                if isinstance(proba, list) and i < len(proba) and proba[i].shape[1] == 2:
                    scores.append((lab, float(proba[i][0, 1])))
                else:
                    scores.append((lab, 0.0))
            pred = max(scores, key=lambda kv: kv[1])[0]
            ok += int(pred == r['label'])
        rf_acc = ok / (len(test) or 1)

    matcher.save(args.out, extra={'n_train': len(train), 'n_test': len(test), 'clips': [c.name for c in clips]})

    # Undo eval on first train clean belonging to a held-in clip
    clean = load_wav(clips[0], max_s=6.0)
    undo_metrics = eval_undo_on_rendered(clean)

    # Head Down real stem classification (no FX ground truth labels — report scores only)
    hd = None
    hd_path = Path(args.head_down)
    if hd_path.is_file():
        audio = load_wav(hd_path, max_s=20.0)
        hd = matcher.predict(audio, sr=44100)
        # undo + pyin F1 vs pyin on raw (self-consistency, not true MIDI)
        from fx.undo import undo_effects as _u
        import librosa
        cleaned = _u(audio, sr=44100, effects=[e['name'] for e in hd['effects']])
        def count_voiced(y):
            f0, v, _ = librosa.pyin(y, fmin=80, fmax=1000, sr=44100, frame_length=2048)
            return int(np.sum(v & np.isfinite(f0)))
        hd['voiced_frames_before'] = count_voiced(audio)
        hd['voiced_frames_after_undo'] = count_voiced(cleaned)
        hd['note'] = 'No pitch-accurate MIDI for Head Down; voiced-frame counts only.'

    report = {
        'templates': args.out,
        'threshold': matcher.threshold,
        'test_top1_acc': ev_test['top1_acc'],
        'test_threshold_hit_rate': ev_test['threshold_hit_rate'],
        'rf_top1_acc': rf_acc,
        'per_class_top1': per_class_acc(ev_test['confusion']),
        'confusion': ev_test['confusion'],
        'undo_synth': undo_metrics,
        'head_down': hd,
        'limitations': [
            'Templates from synthetic FX on acoustic GuitarSet mic — not commercial amp sims.',
            'IDMT-SMT-Audio-Effects not downloaded (6.5GB, CC BY-NC-ND).',
            'Head Down has no pitch MIDI; cannot report true note F1.',
            'Centroid matcher confuses related FX (OD/dist/fuzz; chorus/flanger).',
        ],
    }
    Path(args.report).write_text(json.dumps(report, indent=2))
    print(json.dumps({k: report[k] for k in (
        'threshold', 'test_top1_acc', 'test_threshold_hit_rate', 'rf_top1_acc',
        'per_class_top1', 'undo_synth')}, indent=2))
    if hd:
        print('head_down effects:', hd['effects'])


if __name__ == '__main__':
    main()

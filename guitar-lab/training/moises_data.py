"""Real-recording training data from MoisesDB (CC BY-NC-SA 4.0, non-commercial research).

MoisesDB has real band recordings with every instrument on its own tracks. For each song with
electric guitar the mix is the sum of all tracks and the label is Riley's reading of the song's
own guitar tracks (where Riley is right about 90% of the time). Training on separated guitar
with those labels teaches the model to read a separated guitar the way it reads a clean one,
on real recordings rather than sampled instruments (Slakh did not carry over to real records;
benchmarks/regression/RESULTS.md).

The dataset is one 89 GB zip. Songs are read out of it with HTTP range requests
(training/runpod/moises_zip.py), so only the songs used are downloaded. The download link is
personal and expires: pass it in a file, never commit it.

    python -m training.moises_data prepare <link file> <test songs.json> <work dir> [--val 15] [--shard i/n]
    python -m training.moises_data separate <work dir>            # BS-RoFormer SW and Demucs guitar
    python -m training.moises_data segments <work dir> <out dir>  # training segments, train split only
    python -m training.moises_data items <work dir> <split> <sep> <out dir>   # frozen-test items

Splits: ``test`` are the songs of the frozen MoisesDB test (benchmarks/fullband), ``val`` a
fixed set of other songs for choosing the checkpoint and its threshold, ``train`` the rest.
"""
from __future__ import annotations

import argparse
import io
import json
import random
import shutil
import sys
import zipfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

SR = 16000
SEG_S = 10.0


def _zip(link_file):
    from training.runpod.moises_zip import HTTPFile
    return zipfile.ZipFile(io.BufferedReader(HTTPFile(Path(link_file).read_text().strip()), buffer_size=16 << 20))


def songs_with_electric_guitar(z):
    """(root, data.json) for every song whose guitar tracks include electric guitar, none with bleed."""
    names = {i.filename for i in z.infolist()}
    out = []
    for name in sorted(n for n in names if n.endswith('data.json')):
        d = json.loads(z.read(name))
        root = name.rsplit('/', 1)[0]
        guitar = [t for s in d['stems'] if s['stemName'] == 'guitar' for t in s['tracks']]
        if not any('electric' in t['trackType'] for t in guitar) or any(t['has_bleed'] for t in guitar):
            continue
        files = [f"{root}/{s['stemName']}/{t['id']}.{t['extension']}" for s in d['stems'] for t in s['tracks']]
        if all(f in names for f in files):
            out.append((root, d))
    return out


def prepare(link_file, test_file, work, n_val, shard=(0, 1)):
    import librosa
    import soundfile as sf
    from server import riley
    work = Path(work)
    (work / 'mixes').mkdir(parents=True, exist_ok=True)
    z = _zip(link_file)
    test_roots = {c['root'] for c in json.load(open(test_file))['picked']}
    songs = songs_with_electric_guitar(z)
    others = [r for r, _ in songs if r not in test_roots]
    random.Random(20261117).shuffle(others)
    split = {r: 'test' for r in test_roots}
    split.update({r: 'val' for r in others[:n_val]})
    split.update({r: 'train' for r in others[n_val:]})
    manifest_path = work / f'songs_{shard[0]}.json'
    manifest = json.loads(manifest_path.read_text()) if manifest_path.is_file() else {}
    for root, d in songs[shard[0]::shard[1]]:
        name = root.rsplit('/', 1)[1][:8]
        if name in manifest:
            continue
        mix = guitar = None
        rate = None
        for s in d['stems']:
            for t in s['tracks']:
                y, sr = sf.read(io.BytesIO(z.read(f"{root}/{s['stemName']}/{t['id']}.{t['extension']}")), dtype='float32', always_2d=True)
                y = np.repeat(y, 2, axis=1) if y.shape[1] == 1 else y[:, :2]
                rate = rate or sr

                def add(acc, y):
                    if acc is None:
                        return y.copy()
                    n = max(len(acc), len(y))
                    out = np.zeros((n, 2), np.float32)
                    out[:len(acc)] += acc
                    out[:len(y)] += y
                    return out
                mix = add(mix, y)
                if s['stemName'] == 'guitar':
                    guitar = add(guitar, y)
        scale = 1.0 / max(1.0, float(np.abs(mix).max()) / 0.98)
        sf.write(work / 'mixes' / f'{name}.wav', mix * scale, rate)
        g = librosa.resample((guitar * scale).mean(axis=1), orig_sr=rate, target_sr=SR).astype(np.float32)
        np.save(work / 'mixes' / f'{name}.guitar16.npy', g)
        notes = riley.decode(riley.posteriors(g, device=_device()))[0]
        (work / 'mixes' / f'{name}.notes.json').write_text(json.dumps(
            [{'time': round(n['time'], 4), 'duration': round(n['duration'], 4), 'midi': int(n['midi'])} for n in notes]))
        manifest[name] = {'root': root, 'split': split[root], 'genre': d['genre'], 'seconds': round(len(mix) / rate, 1),
                          'notes': len(notes), 'guitar_types': sorted({t['trackType'] for s in d['stems'] if s['stemName'] == 'guitar' for t in s['tracks']})}
        manifest_path.write_text(json.dumps(manifest, indent=1))
        print(name, manifest[name]['split'], manifest[name]['seconds'], 's', len(notes), 'notes', flush=True)


def load_manifest(work):
    """All songs prepared so far (one manifest file per prepare shard)."""
    out = {}
    for f in sorted(Path(work).glob('songs_*.json')):
        out.update(json.loads(f.read_text()))
    return out


def _device():
    import torch
    return 'cuda' if torch.cuda.is_available() else 'cpu'


def separate(work):
    """BS-RoFormer SW guitar (audio-separator) and the app's Demucs guitar, for every mix."""
    import subprocess
    import librosa
    import soundfile as sf
    from server import models
    work = Path(work)
    mixes = sorted(p for p in (work / 'mixes').glob('*.wav'))
    sw_out = work / 'sw'
    sw_out.mkdir(exist_ok=True)
    def guitar_of(p):
        found = [f for f in sw_out.glob(f'{p.stem}_(*') if f.name[len(p.stem) + 2:].lower().startswith('guitar)')]
        return found[0] if found else None
    todo = [str(p) for p in mixes if guitar_of(p) is None]
    for i in range(0, len(todo), 20):
        subprocess.run(['audio-separator', *todo[i:i + 20], '-m', 'BS-Roformer-SW.ckpt', '--model_file_dir', str(work / 'models'),
                        '--output_dir', str(sw_out), '--output_format', 'WAV', '--single_stem', 'Guitar'], check=True)
    for p in mixes:
        sw = guitar_of(p)
        target = work / 'mixes' / f'{p.stem}.sw16.npy'
        if not target.is_file():
            y, sr = sf.read(sw, dtype='float32', always_2d=True)
            np.save(target, librosa.resample(y.mean(axis=1), orig_sr=sr, target_sr=SR).astype(np.float32))
        target = work / 'mixes' / f'{p.stem}.demucs16.npy'
        if not target.is_file():
            mix, sr = sf.read(p, dtype='float32', always_2d=True)
            stems, got, _ = models.run_demucs(mix, sr)
            np.save(target, librosa.resample(stems['guitar'].mean(axis=1), orig_sr=got, target_sr=SR).astype(np.float32))
        print(p.stem, 'separated', flush=True)


def segments(work, out):
    work, out = Path(work), Path(out)
    out.mkdir(parents=True, exist_ok=True)
    manifest = load_manifest(work)
    k = 0
    for name, info in sorted(manifest.items()):
        if info['split'] != 'train':
            continue
        notes = json.loads((work / 'mixes' / f'{name}.notes.json').read_text())
        for kind in ('sw', 'demucs', 'guitar'):
            y = np.load(work / 'mixes' / f'{name}.{kind}16.npy')
            peak = float(np.abs(y).max()) or 1.0
            for a in np.arange(0, len(y) / SR - SEG_S, SEG_S):
                inside = [n for n in notes if a <= n['time'] < a + SEG_S]
                if len(inside) < 4:
                    continue
                seg = y[int(a * SR):int((a + SEG_S) * SR)] / peak * 0.9
                np.savez_compressed(out / f'seg_m_{k:06d}.npz', audio=(np.clip(seg, -1, 1) * 32767).astype(np.int16),
                                    notes=json.dumps([[n['time'] - a, n['duration'], n['midi']] for n in inside]),
                                    source=f'moises:{kind}:{name}')
                k += 1
    print('segments', k)


def items(work, split, sep, out):
    """benchmarks/fullband items (reference.json + guitar.wav) for one split, from one separator."""
    import soundfile as sf
    work, out = Path(work), Path(out)
    manifest = load_manifest(work)
    for name, info in sorted(manifest.items()):
        if info['split'] != split or info['notes'] < 50:
            continue
        folder = out / name
        folder.mkdir(parents=True, exist_ok=True)
        notes = json.loads((work / 'mixes' / f'{name}.notes.json').read_text())
        (folder / 'reference.json').write_text(json.dumps({
            'source': "the song's own guitar tracks (MoisesDB), transcribed on their own", 'kind': 'multitrack',
            'notes': notes, 'scored_from_s': 0.0, 'scored_to_s': info['seconds'], 'genre': info['genre']}))
        sf.write(folder / 'guitar.wav', np.load(work / 'mixes' / f'{name}.{sep}16.npy'), SR)
    print(split, sep, len(list(out.iterdir())), 'items')


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='mode', required=True)
    p = sub.add_parser('prepare')
    p.add_argument('link')
    p.add_argument('test')
    p.add_argument('work')
    p.add_argument('--val', type=int, default=15)
    p.add_argument('--shard', default='0/1', help='i/n: every n-th song starting at i (run n processes)')
    p = sub.add_parser('separate')
    p.add_argument('work')
    p = sub.add_parser('segments')
    p.add_argument('work')
    p.add_argument('out')
    p = sub.add_parser('items')
    p.add_argument('work')
    p.add_argument('split', choices=['train', 'val', 'test'])
    p.add_argument('sep', choices=['sw', 'demucs', 'guitar'])
    p.add_argument('out')
    a = ap.parse_args()
    if a.mode == 'prepare':
        prepare(a.link, a.test, a.work, a.val, tuple(int(x) for x in a.shard.split('/')))
    elif a.mode == 'separate':
        separate(a.work)
    elif a.mode == 'segments':
        segments(a.work, a.out)
    else:
        items(a.work, a.split, a.sep, a.out)


if __name__ == '__main__':
    main()

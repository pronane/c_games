"""Fine-tune Riley's guitar model on re-amped / heavy segments (training/build_data.py).

The convolutional front ends stay frozen (they already hear guitar well); the recurrent and
output layers of the onset, offset and frame heads and the two conditioning GRUs are trained.
Targets follow Kong et al.: a framewise roll, and onset/offset regression rolls that peak at the
exact event time and fall off linearly over 5 frames. Velocity is not trained (no labels).
Checkpoints go to <out>/step_<n>.pth in the same layout as the released file."""
from __future__ import annotations

import argparse
import glob
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from server import riley  # noqa: E402
from server.riley import config  # noqa: E402

FPS = config.frames_per_second
BEGIN = config.begin_note
K = config.classes_num
J = 5


def targets(notes, frames):
    frame = np.zeros((frames, K), np.float32)
    onset = np.zeros((frames, K), np.float32)
    offset = np.zeros((frames, K), np.float32)
    def bump(roll, t, k):
        c = t * FPS
        for f in range(max(0, int(c) - J), min(frames, int(c) + J + 1)):
            roll[f, k] = max(roll[f, k], max(0.0, 1 - abs(f - c) / J))
    for t, d, m in notes:
        k = int(m) - BEGIN
        if not 0 <= k < K:
            continue
        a, b = int(round(t * FPS)), int(round((t + d) * FPS))
        frame[max(0, a):min(frames, b + 1), k] = 1
        bump(onset, t, k)
        if t + d < frames / FPS:
            bump(offset, t + d, k)
    return frame, onset, offset


class Segments(torch.utils.data.Dataset):
    def __init__(self, files):
        self.files = files

    def __len__(self):
        return len(self.files)

    def __getitem__(self, i):
        d = np.load(self.files[i])
        audio = d['audio'].astype(np.float32) / 32767
        frames = int(len(audio) / config.sample_rate * FPS) + 1
        f, on, off = targets(json.loads(str(d['notes'])), frames)
        return torch.from_numpy(audio), torch.from_numpy(f), torch.from_numpy(on), torch.from_numpy(off)


TRAINABLE = ('frame_model.fc5', 'frame_model.bn5', 'frame_model.gru', 'frame_model.fc',
             'reg_onset_model.fc5', 'reg_onset_model.bn5', 'reg_onset_model.gru', 'reg_onset_model.fc',
             'reg_offset_model.fc5', 'reg_offset_model.bn5', 'reg_offset_model.gru', 'reg_offset_model.fc',
             'reg_onset_gru', 'reg_onset_fc', 'frame_gru', 'frame_fc')


def set_mode(model):
    model.train()
    for name, m in model.named_modules():
        if name and not any(name == t or name.startswith(t + '.') for t in TRAINABLE) and \
                not any(t.startswith(name + '.') for t in TRAINABLE):
            m.eval()          # frozen parts: no dropout, BatchNorm statistics untouched


def bce(pred, target):
    pred = pred.clamp(1e-7, 1 - 1e-7)
    return F.binary_cross_entropy(pred, target)


def song_id(source: str) -> str:
    """Song key for a segment source tag.

    ``slakh:<kind>:<track>`` and ``guitarset:<style>:<clip>`` share a song across every
    segment of that track. A tag with no song field (``riff``, ``guitarset:clean``) is one group.
    """
    parts = str(source).split(':')
    if len(parts) >= 3 and parts[-1]:
        return parts[-1]
    return str(source)


def assign_songs(groups: dict, val_target: int = 60, order=None):
    """Hold out whole songs until validation has ``val_target`` segments.

    No song is split. At least one song stays in training. Returns ``(val_files, train_files)``.
    """
    songs = list(order) if order is not None else list(groups)
    if len(songs) < 2:
        raise SystemExit('Need segments from at least two songs so validation does not share a song with training.')
    unknown = [song for song in songs if song not in groups]
    if unknown or len(songs) != len(groups):
        raise SystemExit('Song order must list each song once.')
    val_songs = []
    count = 0
    index = 0
    while index < len(songs) - 1 and count < val_target:
        song = songs[index]
        val_songs.append(song)
        count += len(groups[song])
        index += 1
    train_songs = songs[index:]
    if not val_songs or not train_songs:
        raise SystemExit('Could not hold out a whole song and still leave a training song.')
    val = [path for song in val_songs for path in groups[song]]
    train = [path for song in train_songs for path in groups[song]]
    return val, train


def split_files(files, read_source, val_target: int = 60, rng=None):
    groups = defaultdict(list)
    for path in files:
        groups[song_id(read_source(path))].append(path)
    songs = list(groups)
    if rng is not None:
        rng.shuffle(songs)
    return assign_songs(groups, val_target, songs)


def require_trainable(train, batch: int):
    if batch < 1:
        raise SystemExit('Batch size must be at least 1.')
    if len(train) < batch:
        raise SystemExit(
            f'Training set has {len(train)} segments, fewer than the batch size ({batch}). '
            'Nothing to train; the run stops instead of spinning on an empty loader.'
        )


def prepare_workers(workers: int):
    """DataLoader workers must spawn. Forking after CUDA is initialized hangs or errors."""
    if workers <= 0:
        return
    import torch.multiprocessing as mp
    current = mp.get_start_method(allow_none=True)
    if current == 'spawn':
        return
    try:
        mp.set_start_method('spawn', force=True)
    except RuntimeError as exc:
        found = mp.get_start_method(allow_none=True)
        raise SystemExit(f'workers={workers} needs the spawn start method (found {found}): {exc}') from exc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--data', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--steps', type=int, default=1200)
    ap.add_argument('--batch', type=int, default=4)
    ap.add_argument('--lr', type=float, default=1e-4)
    ap.add_argument('--every', type=int, default=200)
    ap.add_argument('--init', help='resume from a checkpoint written by this script')
    ap.add_argument('--start', type=int, default=0, help='step number the --init checkpoint ended at')
    ap.add_argument('--device', default='auto', help='auto (GPU when there is one), cuda or cpu')
    ap.add_argument('--all-layers', action='store_true',
                    help='train every layer, not only the recurrent and output layers (needs a GPU and much more data)')
    ap.add_argument('--workers', type=int, default=0)
    a = ap.parse_args()
    prepare_workers(a.workers)
    torch.manual_seed(0)
    torch.set_num_threads(max(1, torch.get_num_threads()))
    files = sorted(glob.glob(f'{a.data}/seg_*.npz'))

    def read_source(path):
        with np.load(path) as data:
            return str(data['source']) if 'source' in data.files else Path(path).name

    rng = np.random.default_rng(0)
    val, train = split_files(files, read_source, rng=rng)
    require_trainable(train, a.batch)
    device = torch.device('cuda' if (a.device == 'auto' and torch.cuda.is_available()) else 'cpu' if a.device == 'auto' else a.device)
    print('device', device, flush=True)
    model = riley.load('riley')
    if a.init:
        model.load_state_dict(torch.load(a.init, map_location='cpu', weights_only=False)['model'])
    for p_name, p in model.named_parameters():
        p.requires_grad = a.all_layers or any(p_name.startswith(t + '.') or p_name == t for t in TRAINABLE)
    model.to(device)
    mode = (lambda m: m.train()) if a.all_layers else set_mode
    params = [p for p in model.parameters() if p.requires_grad]
    print(f'training {sum(p.numel() for p in params)/1e6:.1f}M of {sum(p.numel() for p in model.parameters())/1e6:.1f}M parameters on {len(train)} segments', flush=True)
    opt = torch.optim.Adam(params, lr=a.lr)
    loader = torch.utils.data.DataLoader(Segments(train), batch_size=a.batch, shuffle=True, drop_last=True, num_workers=a.workers)
    vloader = torch.utils.data.DataLoader(Segments(val), batch_size=a.batch)
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)

    def losses(batch):
        audio, fr, on, off = (t.to(device) for t in batch)
        o = model(audio)
        n = min(o['frame_output'].shape[1], fr.shape[1])
        return (bce(o['reg_onset_output'][:, :n], on[:, :n]) + bce(o['reg_offset_output'][:, :n], off[:, :n])
                + bce(o['frame_output'][:, :n], fr[:, :n]))

    def validate():
        model.eval()
        with torch.no_grad():
            v = float(np.mean([losses(b).item() for b in vloader]))
        mode(model)
        return v

    print('validation loss before', round(validate(), 4), flush=True)
    step, t0, first = a.start, time.time(), a.start
    if len(loader) == 0:
        raise SystemExit('The training loader is empty. Refusing to wait on a loader that yields no batches.')
    while step < a.steps:
        for batch in loader:
            mode(model)
            loss = losses(batch)
            opt.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(params, 3.0)
            opt.step()
            step += 1
            if step % 20 == 0:
                print(f'step {step} loss {loss.item():.4f} ({(time.time()-t0)/max(1, step-first):.1f} s/step)', flush=True)
            if step % a.every == 0 or step == a.steps:
                v = validate()
                torch.save({'model': {k: v.cpu() for k, v in model.state_dict().items()}}, out / f'step_{step}.pth')
                print(f'step {step} validation {v:.4f} saved', flush=True)
            if step >= a.steps:
                break


if __name__ == '__main__':
    main()

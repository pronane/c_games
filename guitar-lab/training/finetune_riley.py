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
    a = ap.parse_args()
    torch.manual_seed(0)
    torch.set_num_threads(max(1, torch.get_num_threads()))
    files = sorted(glob.glob(f'{a.data}/seg_*.npz'))
    rng = np.random.default_rng(0)
    rng.shuffle(files)
    val, train = files[:60], files[60:]
    model = riley.load('riley')
    if a.init:
        model.load_state_dict(torch.load(a.init, map_location='cpu', weights_only=False)['model'])
    for p_name, p in model.named_parameters():
        p.requires_grad = any(p_name.startswith(t + '.') or p_name == t for t in TRAINABLE)
    params = [p for p in model.parameters() if p.requires_grad]
    print(f'training {sum(p.numel() for p in params)/1e6:.1f}M of {sum(p.numel() for p in model.parameters())/1e6:.1f}M parameters on {len(train)} segments', flush=True)
    opt = torch.optim.Adam(params, lr=a.lr)
    loader = torch.utils.data.DataLoader(Segments(train), batch_size=a.batch, shuffle=True, drop_last=True, num_workers=0)
    vloader = torch.utils.data.DataLoader(Segments(val), batch_size=a.batch)
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)

    def losses(batch):
        audio, fr, on, off = batch
        o = model(audio)
        n = min(o['frame_output'].shape[1], fr.shape[1])
        return (bce(o['reg_onset_output'][:, :n], on[:, :n]) + bce(o['reg_offset_output'][:, :n], off[:, :n])
                + bce(o['frame_output'][:, :n], fr[:, :n]))

    def validate():
        model.eval()
        with torch.no_grad():
            v = float(np.mean([losses(b).item() for b in vloader]))
        set_mode(model)
        return v

    print('validation loss before', round(validate(), 4), flush=True)
    step, t0, first = a.start, time.time(), a.start
    while step < a.steps:
        for batch in loader:
            set_mode(model)
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
                torch.save({'model': model.state_dict()}, out / f'step_{step}.pth')
                print(f'step {step} validation {v:.4f} saved', flush=True)
            if step >= a.steps:
                break


if __name__ == '__main__':
    main()

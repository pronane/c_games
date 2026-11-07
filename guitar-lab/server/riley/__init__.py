"""Riley et al.'s high-resolution guitar transcriber, run inside the engine.

The CRNN (Kong et al.'s onset/offset/frame/velocity regression model) and its note decoder
are adapted into this folder, so no extra package is needed beyond torchlibrosa. The
checkpoint (about 100 MB) is fetched from Hugging Face on first use and cached.
"""
from __future__ import annotations

import numpy as np

from . import config

REPO = 'xavriley/midi-transcription-models'
CHECKPOINTS = {'riley': 'guitar-fl.pth', 'gaps': 'guitar-gaps.pth'}
SAMPLE_RATE = config.sample_rate
# Published decoder thresholds.
THRESHOLDS = {'onset': 0.3, 'offset': 0.3, 'frame': 0.1}

_loaded: dict = {}


def load(which: str = 'riley', device: str = 'cpu'):
    """The model for `which` ('riley' or 'gaps'), downloading its checkpoint the first time."""
    key = (which, device)
    if key in _loaded:
        return _loaded[key]
    import torch
    from huggingface_hub import hf_hub_download
    from .models import Regress_onset_offset_frame_velocity_CRNN
    path = hf_hub_download(repo_id=REPO, filename=CHECKPOINTS[which])
    model = Regress_onset_offset_frame_velocity_CRNN(frames_per_second=config.frames_per_second,
                                                    classes_num=config.classes_num)
    # The checkpoints are plain pickles from before torch 2.6's weights-only default.
    state = torch.load(path, map_location=device, weights_only=False)
    model.load_state_dict(state['model'] if 'model' in state else state, strict=False)
    model.to(device).eval()
    _loaded[key] = model
    return model


def posteriors(audio: np.ndarray, which: str = 'riley', device: str = 'cpu', segment_s: float = 10.0):
    """Frame-wise outputs for mono 16 kHz audio: reg_onset/offset, frame, velocity (frames x 88)."""
    import torch
    model = load(which, device)
    seg = int(segment_s * SAMPLE_RATE)
    n = len(audio)
    padded = np.concatenate([audio.astype(np.float32), np.zeros(max(seg, int(np.ceil(n / seg)) * seg) - n, np.float32)])
    # Half-overlapping segments; keep the middle half of each (as the original deframe does).
    starts = list(range(0, len(padded) - seg + 1, seg // 2)) or [0]
    outs = {}
    with torch.no_grad():
        for s in starts:
            x = torch.from_numpy(padded[s:s + seg][None].astype(np.float32)).to(device)
            for k, v in model(x).items():
                outs.setdefault(k, []).append(v[0].cpu().numpy())
    return {k: _deframe(v)[: int(np.ceil(n / SAMPLE_RATE * config.frames_per_second))] for k, v in outs.items()}


def _deframe(chunks):
    if len(chunks) == 1:
        return chunks[0]
    frames = chunks[0].shape[0] - 1  # the model emits segment_frames + 1
    q = frames // 4
    parts = [chunks[0][: 3 * q]]
    for c in chunks[1:-1]:
        parts.append(c[q: 3 * q])
    parts.append(chunks[-1][q:])
    return np.concatenate(parts, axis=0)


def notes_from_posteriors(out: dict, onset=None, offset=None, frame=None):
    """Note events from the model outputs with the original regression decoder."""
    from .postprocess import RegressionPostProcessor
    pp = RegressionPostProcessor(config.frames_per_second, classes_num=config.classes_num,
                                 onset_threshold=onset or THRESHOLDS['onset'],
                                 offset_threshold=offset or THRESHOLDS['offset'],
                                 frame_threshold=frame or THRESHOLDS['frame'], pedal_offset_threshold=0.2)
    events = pp.output_dict_to_note_events(out) if hasattr(pp, 'output_dict_to_note_events') else \
        pp.output_dict_to_midi_events(out)[0]
    return [{'time': float(e['onset_time']), 'duration': float(max(e['offset_time'] - e['onset_time'], 0.03)),
             'midi': int(e['midi_note']), 'amplitude': float(e['velocity']) / 127} for e in events]


# Reverb: tails re-trigger the onset head, so at the published 0.3 onset threshold a wet take
# comes out with 2-9x too many notes (recall stays high, precision collapses). Measured on
# GuitarSet + IDMT clips through synthetic rooms (RT60 0.8 / 2.0 / 3.5 s), note F1:
#   published 0.3:   dry .897  room .851  hall .585  wash .259
#   this rule:       dry .905  room .879  hall .801  wash .587
# Dry clips barely change between 0.3 and 0.65 (note-count ratio 1.00-1.22), wet ones balloon
# (1.6-9.4), so the ratio decides the onset threshold per file.
DRY_ONSET, WET_ONSET, WET_RATIO = 0.5, 0.65, 1.5


def decode(out: dict):
    """Notes with the onset threshold chosen for how reverberant the audio is.
    Returns (notes, info) where info says what was decided and why."""
    loose = notes_from_posteriors(out)
    strict = notes_from_posteriors(out, onset=WET_ONSET)
    ratio = len(loose) / max(len(strict), 1)
    wet = ratio > WET_RATIO
    notes = strict if wet else notes_from_posteriors(out, onset=DRY_ONSET)
    return notes, {'reverb': 'heavy' if wet else 'light', 'onset_threshold': WET_ONSET if wet else DRY_ONSET,
                   'onset_ratio': round(ratio, 2)}

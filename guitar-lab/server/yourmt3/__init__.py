"""YourMT3+ (YPTF.MoE+Multi, noPS) run inside the engine.

The inference code is adapted into ``amt/`` (Apache-2.0; see LICENSE). Its training-only
dependencies (PyTorch Lightning, wandb, torchmetrics) are not needed: if they are not installed,
inert stand-ins satisfy the imports. The 560 MB checkpoint is fetched from Hugging Face on first
use and cached. It runs at fp32 on CPU, at roughly real time.
"""
from __future__ import annotations

import os
import sys
import threading
import types
from pathlib import Path

AMT = Path(__file__).resolve().parent / 'amt'
REPO = 'mimbres/YourMT3'
EXP = 'mc13_256_g4_all_v7_mt3f_sqr_rms_moe_wf4_n8k2_silu_rope_rp_b36_nops'
CHECKPOINT = f'logs/2024/{EXP}/checkpoints/last.ckpt'
ARGS = [f'{EXP}@last.ckpt', '-p', '2024', '-tk', 'mc13_full_plus_256', '-dec', 'multi-t5', '-nl', '26',
        '-enc', 'perceiver-tf', '-sqr', '1', '-ff', 'moe', '-wf', '4', '-nmoe', '8', '-kmoe', '2', '-act', 'silu',
        '-epe', 'rope', '-rp', '1', '-ac', 'spec', '-hop', '300', '-atc', '1', '-pr', '32']

_lock = threading.Lock()
_model = None


def _stand_ins():
    """Inert modules for training-only imports, used only when the real package is missing."""
    import importlib.util
    import torch.nn as nn
    if importlib.util.find_spec('pytorch_lightning') is None:
        pl = types.ModuleType('pytorch_lightning')

        class LightningModule(nn.Module):
            def __init__(self, *a, **k):
                super().__init__()

            def save_hyperparameters(self, *a, **k):
                # As Lightning does: the calling __init__'s arguments become self.hparams.
                import inspect
                frame = inspect.currentframe().f_back
                values = {k: v for k, v in frame.f_locals.items()
                          if k not in ('self', '__class__') and not k.startswith('_')}
                self.hparams = types.SimpleNamespace(**values)

            def log(self, *a, **k):
                pass

            def log_dict(self, *a, **k):
                pass

            global_rank = local_rank = 0
            trainer = None

            @property
            def device(self):
                return next(self.parameters()).device

        pl.LightningModule, pl.Trainer = LightningModule, object
        sys.modules['pytorch_lightning'] = pl
        for name, attrs in {'loggers': {'WandbLogger': object},
                            'callbacks': {'ModelCheckpoint': object, 'LearningRateMonitor': object},
                            'utilities': {'rank_zero_only': lambda f: f}}.items():
            mod = types.ModuleType(f'pytorch_lightning.{name}')
            for k, v in attrs.items():
                setattr(mod, k, v)
            sys.modules[mod.__name__] = mod
            setattr(pl, name, mod)
    if importlib.util.find_spec('wandb') is None:
        wandb = types.ModuleType('wandb')

        class Table:
            def __init__(self, *a, **k):
                pass

            def add_data(self, *a, **k):
                pass

        wandb.Table = Table
        sys.modules.setdefault('wandb', wandb)
    if importlib.util.find_spec('torchmetrics') is None:
        tm = types.ModuleType('torchmetrics')

        class _Metric(nn.Module):
            def __init__(self, *a, **k):
                super().__init__()

        tm.MeanMetric = tm.SumMetric = tm.Metric = _Metric
        sys.modules['torchmetrics'] = tm


def available() -> bool:
    import importlib.util
    return all(importlib.util.find_spec(m) for m in ('torch', 'torchaudio', 'transformers', 'einops', 'huggingface_hub'))


def load():
    """The model, built once (downloads the checkpoint the first time)."""
    global _model
    with _lock:
        if _model is not None:
            return _model
        import torch
        from huggingface_hub import hf_hub_download
        ckpt = Path(hf_hub_download(REPO, CHECKPOINT))
        _stand_ins()
        if str(AMT) not in sys.path:
            sys.path.insert(0, str(AMT))
        import model.init_train as init_train  # noqa: E402  (amt/ on the path)

        def initialize_trainer(args, stage='test'):
            # Inference only: no Trainer, logger or checkpoint callbacks; point at the cached checkpoint.
            from copy import deepcopy
            from config.config import shared_cfg as default_shared_cfg
            if '@' in args.exp_id:
                args.exp_id = args.exp_id.split('@')[0]
            return None, None, {'lightning_dir': str(ckpt.parent.parent), 'last_ckpt_path': str(ckpt)}, \
                deepcopy(default_shared_cfg)

        init_train.initialize_trainer = initialize_trainer
        import model_helper  # noqa: E402
        model_helper.initialize_trainer = initialize_trainer
        stdout, sys.stdout = sys.stdout, sys.stderr  # it prints its whole config
        try:
            _model = model_helper.load_model_checkpoint(args=list(ARGS), device='cpu')
        finally:
            sys.stdout = stdout
        torch.set_num_threads(os.cpu_count() or 1)
        return _model


def transcribe(path) -> list[dict]:
    """Every note YourMT3+ hears in the file: time, duration, midi, program, drum, amplitude."""
    import soundfile as sf
    import torch
    import torchaudio
    model = load()
    from utils.audio import slice_padded_array
    from utils.note2event import mix_notes
    from utils.event2note import merge_zipped_note_events_and_ties_to_notes
    x, sr = sf.read(str(path), dtype='float32', always_2d=True)
    audio = torchaudio.functional.resample(torch.from_numpy(x.T.copy()).mean(0, keepdim=True), sr,
                                           model.audio_cfg['sample_rate'])
    frames = model.audio_cfg['input_frames']
    segments = torch.from_numpy(slice_padded_array(audio.numpy(), frames, frames).astype('float32')).unsqueeze(1)
    with torch.no_grad():
        pred, _ = model.inference_file(bsz=8, audio_segments=segments)
    starts = [frames * i / model.audio_cfg['sample_rate'] for i in range(segments.shape[0])]
    per_channel = []
    for ch in range(model.task_manager.num_decoding_channels):
        zipped, _, _ = model.task_manager.detokenize_list_batches([b[:, ch, :] for b in pred], starts, return_events=True)
        per_channel.append(merge_zipped_note_events_and_ties_to_notes(zipped)[0])
    return [{'time': float(n.onset), 'duration': float(max(n.offset - n.onset, 0.01)), 'midi': int(n.pitch),
             'program': int(n.program), 'drum': bool(n.is_drum),
             'amplitude': float(n.velocity) / 127 if n.velocity > 1 else 0.7}
            for n in mix_notes(per_channel)]

"""Optional guitar transcription backends.

The default note list is still Basic Pitch (see ``server.models``). Other
backends are off unless ``FRETWORK_TRANSCRIBER`` names one.

* ``riley`` — Riley, Edwards, Dixon, "High Resolution Guitar Transcription via
  Domain Adaptation" (ICASSP 2024). Checkpoint ``guitar-fl.pth``. Wrapper and
  weights are MIT; inference uses the Kong high-resolution CRNN
  (upstream Apache-2.0).
* ``gaps`` — the same authors' later GAPS guitar checkpoint (``guitar-gaps.pth``,
  MIT), same wrapper.
* ``yourmt3`` — not vendored. Inference code is GPL-3.0; checkpoints on
  Hugging Face are Apache-2.0. Set ``FRETWORK_YOURMT3_ROOT`` to a separate
  checkout. This tree does not copy that code.

Install the Riley/GAPS stack from ``server/requirements-transcription-extras.txt``.
Neither backend is imported unless it is selected. Posterior maps stay on
Basic Pitch: callers that need them are the comparison and refinement paths.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

from .models import ModelUnavailable

_MODELS: dict = {}

_ALIASES = {
    'basic': 'basic_pitch',
    'default': 'basic_pitch',
    'bp': 'basic_pitch',
    'basicpitch': 'basic_pitch',
    'guitar_fl': 'riley',
    'guitar-fl': 'riley',
    'fl': 'riley',
    'guitar_gaps': 'gaps',
    'guitar-gaps': 'gaps',
    'your_mt3': 'yourmt3',
    'ymt3': 'yourmt3',
}

YOURMT3_NOTE = (
    'YourMT3+ is not bundled. Its inference code is GPL-3.0 '
    '(https://github.com/mimbres/YourMT3) and its checkpoints are Apache-2.0 '
    '(https://huggingface.co/mimbres/YourMT3, about 2.8 GB). '
    'Clone that repository separately and set FRETWORK_YOURMT3_ROOT. '
    'This project does not vendor GPL code.'
)

RILEY_NOTE = (
    'The Riley/GAPS guitar models are optional. From guitar-lab/: '
    'pip install -r server/requirements-transcription-extras.txt'
)


def normalize_backend(name=None) -> str:
    if name is None or str(name).strip() == '':
        name = os.environ.get('FRETWORK_TRANSCRIBER', 'basic_pitch')
    key = str(name).strip().lower().replace(' ', '_')
    return _ALIASES.get(key, key)


def backend_name() -> str:
    return normalize_backend(None)


def uses_basic_pitch(name=None) -> bool:
    return normalize_backend(name) == 'basic_pitch'


def transcription_label(name=None) -> str:
    """Provenance string. The Basic Pitch default matches the existing UI copy."""
    chosen = normalize_backend(name)
    if chosen == 'basic_pitch':
        return 'Basic Pitch ONNX'
    if chosen == 'riley':
        return 'Riley guitar-fl (high-resolution CRNN, MIT)'
    if chosen == 'gaps':
        return 'GAPS guitar CRNN (MIT)'
    if chosen == 'yourmt3':
        return 'YourMT3+ (external)'
    return chosen


def clean_take_label(name=None) -> str:
    if uses_basic_pitch(name):
        return 'clean-guitar Basic Pitch'
    return f'clean-guitar {transcription_label(name)}'


def _spec_available(module: str) -> bool:
    import importlib.util
    return importlib.util.find_spec(module) is not None


def availability() -> dict:
    """Which optional backends can be constructed. Does not download weights."""
    riley = (_spec_available('piano_transcription_inference') and _spec_available('torch')
             and _spec_available('huggingface_hub'))
    yourmt3_root = os.environ.get('FRETWORK_YOURMT3_ROOT', '')
    return {
        'basic_pitch': {'installed': True, 'license': 'Apache-2.0', 'default': True},
        'riley': {
            'installed': riley,
            'license': 'MIT (wrapper and guitar-fl.pth); CRNN inference Apache-2.0',
            'checkpoint': 'guitar-fl.pth',
            'paper': 'Riley, Edwards, Dixon, ICASSP 2024',
            'detail': None if riley else RILEY_NOTE,
        },
        'gaps': {
            'installed': riley,
            'license': 'MIT',
            'checkpoint': 'guitar-gaps.pth',
            'paper': 'Riley et al., GAPS, 2024',
            'detail': None if riley else RILEY_NOTE,
        },
        'yourmt3': {
            'installed': bool(yourmt3_root and Path(yourmt3_root).is_dir()),
            'license': 'code GPL-3.0 (not vendored); checkpoints Apache-2.0',
            'detail': YOURMT3_NOTE,
        },
    }


def _notes_from_midi_bytes(data: bytes, midi_min: int, midi_max: int):
    from .compare import notes_from_midi
    parsed = notes_from_midi(data)
    notes = []
    for n in parsed.get('notes') or []:
        midi = int(n['midi'])
        if midi < midi_min or midi > midi_max:
            continue
        dur = float(n['duration'])
        if dur <= 0:
            continue
        notes.append({
            'time': max(0.0, float(n['time'])),
            'duration': dur,
            'midi': midi,
            'amplitude': float(n.get('amplitude') or 0.7),
        })
    notes.sort(key=lambda n: (n['time'], n['midi']))
    for i, n in enumerate(notes):
        n['id'] = i
    return notes


# guitar-fl is the ICASSP 2024 domain-adaptation model. guitar-gaps is the later
# GAPS checkpoint. hf-midi-transcription 0.1.1's instrument list only names
# "guitar" (GAPS), so the checkpoint is loaded directly.
_CHECKPOINTS = {'riley': 'guitar-fl.pth', 'gaps': 'guitar-gaps.pth'}


def _load_riley(which: str):
    cached = _MODELS.get(which)
    if cached is not None:
        return cached
    try:
        import torch
        from huggingface_hub import hf_hub_download
        from piano_transcription_inference import PianoTranscription, sample_rate
    except ImportError as exc:
        raise ModelUnavailable(RILEY_NOTE) from exc
    filename = _CHECKPOINTS[which]
    checkpoint = hf_hub_download(repo_id='xavriley/midi-transcription-models', filename=filename)
    # Published decoder thresholds (onset 0.3 / offset 0.3 / frame 0.1). Not retuned here.
    model = PianoTranscription(
        'Regress_onset_offset_frame_velocity_CRNN',
        device=torch.device('cpu'),
        checkpoint_path=checkpoint,
        segment_samples=int(sample_rate) * 10,
        batch_size=1,
    )
    _MODELS[which] = (model, int(sample_rate))
    return _MODELS[which]


def _transcribe_riley_path(which: str, path: Path, midi_min: int, midi_max: int):
    import librosa
    model, sample_rate = _load_riley(which)
    audio, _ = librosa.load(str(path), sr=sample_rate, mono=True)
    fd, midi_name = tempfile.mkstemp(suffix='.mid')
    os.close(fd)
    midi_path = Path(midi_name)
    try:
        model.transcribe(audio, str(midi_path))
        data = midi_path.read_bytes()
    finally:
        midi_path.unlink(missing_ok=True)
    return _notes_from_midi_bytes(data, midi_min, midi_max)


def _transcribe_yourmt3_path(path: Path, midi_min: int, midi_max: int):
    root = os.environ.get('FRETWORK_YOURMT3_ROOT', '')
    if not root or not Path(root).is_dir():
        raise ModelUnavailable(YOURMT3_NOTE)
    # A checkout is present, but there is no stable one-command API that we
    # have executed. Refuse rather than guess a command line.
    raise ModelUnavailable(
        YOURMT3_NOTE + ' A checkout was found at FRETWORK_YOURMT3_ROOT, but this '
        'build does not call into it: the research entry point was not run here.'
    )


def _run_one(name: str, path: Path, midi_min: int, midi_max: int):
    if name in ('riley', 'gaps'):
        return _transcribe_riley_path(name, path, midi_min, midi_max)
    if name == 'yourmt3':
        return _transcribe_yourmt3_path(path, midi_min, midi_max)
    raise ModelUnavailable(
        f'Unknown transcription backend {name!r}. '
        'Use basic_pitch, riley, gaps, or yourmt3.'
    )


def transcribe_file(name: str, path, midi_min=40, midi_max=88):
    """Note list from one optional backend.

    Stereo files with both channels active are transcribed per channel and
    merged with the same rule as Basic Pitch (``FRETWORK_LR_TRANSCRIBE``).
    """
    import soundfile as sf
    from . import models

    chosen = normalize_backend(name)
    if chosen == 'basic_pitch':
        return models.transcribe(path, midi_min=midi_min, midi_max=midi_max, backend='basic_pitch')
    path = Path(path)
    audio, sr = sf.read(path, always_2d=True, dtype='float32')
    channels = models.stereo_tx_channels(audio) if models.lr_transcribe_enabled() else [('mono', audio.mean(axis=1))]
    if len(channels) == 1:
        return _run_one(chosen, path, midi_min, midi_max)

    lists = []
    tmp_paths = []
    try:
        for label, mono in channels:
            tmp = path.with_name(f'{path.stem}.{label}.wav')
            sf.write(tmp, mono, sr, subtype='PCM_16')
            tmp_paths.append(tmp)
            lists.append(_run_one(chosen, tmp, midi_min, midi_max))
    finally:
        for tmp in tmp_paths:
            tmp.unlink(missing_ok=True)
    return models.merge_note_lists(*lists)

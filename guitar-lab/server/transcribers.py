"""Optional guitar transcription backends.

The default note list is still Basic Pitch (see ``server.models``). Other
backends are off unless ``FRETWORK_TRANSCRIBER`` names one.

* ``riley`` — Riley, Edwards, Dixon, "High Resolution Guitar Transcription via
  Domain Adaptation" (ICASSP 2024). Checkpoint ``guitar-fl.pth``. Wrapper and
  weights are MIT; inference uses the Kong high-resolution CRNN
  (upstream Apache-2.0).
* ``gaps`` — the same authors' later GAPS guitar checkpoint (``guitar-gaps.pth``,
  MIT), same wrapper.
* ``yourmt3`` — YourMT3+ (YPTF.MoE+Multi, noPS), adapted into server/yourmt3
  from the authors' Apache-2.0 release. ``FRETWORK_YOURMT3_PROGRAMS=guitar``
  keeps only notes it labels as guitar.

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
    'YourMT3+ runs from server/yourmt3 and needs transformers 4.45.1 and einops: '
    'pip install -r server/requirements-transcription.txt. Its checkpoint (about 560 MB) '
    'downloads from huggingface.co/mimbres/YourMT3 the first time it is used.'
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


def checked_backend(name=None) -> str:
    """A transcriber chosen in the studio: known and installed, else ValueError with the fix."""
    chosen = normalize_backend(name)
    info = availability().get(chosen)
    if chosen == 'basic_pitch':
        return chosen
    if info is None:
        raise ValueError(f'Unknown transcriber {name!r}. Use basic_pitch, riley, gaps or yourmt3.')
    if not info.get('installed'):
        raise ValueError(f"{info.get('label', chosen)} is not installed here. {info.get('detail') or ''}".strip())
    return chosen


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


def _yourmt3_available() -> bool:
    from . import yourmt3
    return yourmt3.available()


def availability() -> dict:
    """Which optional backends can be constructed. Does not download weights."""
    riley = (_spec_available('torchlibrosa') and _spec_available('torch')
             and _spec_available('huggingface_hub'))
    return {
        'basic_pitch': {'installed': True, 'license': 'Apache-2.0', 'default': True, 'label': 'Basic Pitch',
                        'summary': 'Fast (1-4 s per minute). Default; best on the app\'s own guitar sound.'},
        'riley': {
            'installed': riley, 'label': 'Riley guitar model',
            'summary': 'Most accurate on real guitar (acoustic .908, electric .902); reverb-aware. 10-30 s per minute.',
            'license': 'MIT (adapted into server/riley; checkpoint fetched on first use, ~100 MB)',
            'checkpoint': 'guitar-fl.pth',
            'paper': 'Riley, Edwards, Dixon, ICASSP 2024',
            'detail': None if riley else RILEY_NOTE,
        },
        'gaps': {
            'installed': riley, 'label': 'GAPS (classical guitar)',
            'summary': 'Classical guitar model; falls apart on distorted playing.',
            'license': 'MIT',
            'checkpoint': 'guitar-gaps.pth',
            'paper': 'Riley et al., GAPS, 2024',
            'detail': None if riley else RILEY_NOTE,
        },
        'yourmt3': {
            'label': 'YourMT3+',
            'summary': 'Best on acoustic (.917) but misses low notes on synthetic guitar; about a minute per minute.',
            'installed': _yourmt3_available(),
            'license': 'Apache-2.0 (adapted into server/yourmt3; checkpoint fetched on first use, ~560 MB)',
            'detail': None if _yourmt3_available() else YOURMT3_NOTE,
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


def _transcribe_riley_path(which: str, path: Path, midi_min: int, midi_max: int):
    """Riley (guitar-fl) or GAPS, run in the engine from server/riley."""
    import librosa
    try:
        import torchlibrosa  # noqa: F401
        from . import riley
    except ImportError as exc:
        raise ModelUnavailable(RILEY_NOTE) from exc
    audio, _ = librosa.load(str(path), sr=riley.SAMPLE_RATE, mono=True)
    out = riley.posteriors(audio, which)
    # The reverb-adaptive decoder was tuned on Riley; GAPS keeps its published thresholds.
    notes = riley.decode(out)[0] if which == 'riley' else riley.notes_from_posteriors(out)
    notes = [n for n in notes if midi_min <= n['midi'] <= midi_max]
    notes.sort(key=lambda n: (n['time'], n['midi']))
    for i, n in enumerate(notes):
        n['id'] = i
    return notes


GUITAR_PROGRAMS = range(24, 32)  # General MIDI guitars, nylon to harmonics


def yourmt3_notes(raw: list, midi_min: int, midi_max: int, programs: str = 'all'):
    """YourMT3+ notes -> engine notes. Drums are dropped. ``programs='guitar'`` keeps only
    notes it labelled as a guitar (it also writes bass, piano, strings...)."""
    keep = []
    for n in raw:
        if n.get('drum'):
            continue
        if programs == 'guitar' and int(n.get('program', -1)) not in GUITAR_PROGRAMS:
            continue
        midi = int(n['midi'])
        if not midi_min <= midi <= midi_max:
            continue
        keep.append({'time': float(n['time']), 'duration': max(0.03, float(n['duration'])), 'midi': midi,
                     'amplitude': float(n.get('amplitude') or 0.7)})
    keep.sort(key=lambda n: (n['time'], n['midi']))
    # Several decoder channels can write the same note: one event per pitch within 30 ms.
    out = []
    for n in keep:
        if any(o['midi'] == n['midi'] and abs(o['time'] - n['time']) < 0.03 for o in out[-8:]):
            continue
        out.append(n)
    for i, n in enumerate(out):
        n['id'] = i
    return out


def _transcribe_yourmt3_path(path: Path, midi_min: int, midi_max: int):
    """YourMT3+ run inside the engine from server/yourmt3 (Apache-2.0, adapted)."""
    from . import yourmt3
    if not yourmt3.available():
        raise ModelUnavailable(YOURMT3_NOTE)
    return yourmt3_notes(yourmt3.transcribe(path), midi_min, midi_max,
                         os.environ.get('FRETWORK_YOURMT3_PROGRAMS', 'all'))


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

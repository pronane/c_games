"""EGSet12 and Guitar-TECHS musical excerpts.

These sets are evaluation material for the regression gate. Audio, Guitar Pro
files, and MIDI are downloaded into ``data/private/`` and are not committed.
The note reference is read after transcription. Nothing here picks a time
shift by maximising note F1.

EGSet12's reference is the official JAMS ``note_midi`` annotations (one per
string). The ``.gp`` files are Guitar Pro 6/7 packages (GPX); they are
downloaded and checksummed so the tablature source is present, and they are
not parsed.

Guitar-TECHS P3 is twelve musical excerpts. Each wav is dual-mono (the two
channels are copies). The reference is the per-string Fishman MIDI. The
authors warn that signals can be up to 100 ms apart. ``onset_lag_seconds``
estimates one constant lag per clip from the audio onset envelope and the
MIDI onset times, searched only inside ±100 ms. That lag is frozen in
``reference/electric_alignment.json`` and added to the reference. It does not
look at a transcriber's notes.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from benchmarks.regression import catalog

MANIFEST = catalog.ROOT / 'reference' / 'electric_manifest.json'
ALIGNMENT = catalog.ROOT / 'reference' / 'electric_alignment.json'
BASELINE = catalog.ROOT / 'reference' / 'electric_baseline.json'

# Authors: signals may be ≤100 ms apart. The search does not go outside that.
LAG_LIMIT_S = 0.10
LAG_HOP = 128
# Below this normalised peak the correlation is not a lag; the frozen shift is 0.
WEAK_PEAK = 0.08

TECHS_SIGNALS = ('micamp', 'directinput')


def load_manifest():
    return json.loads(MANIFEST.read_text())


def load_alignment():
    if not ALIGNMENT.is_file():
        return None
    return json.loads(ALIGNMENT.read_text())


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def md5_file(path: Path) -> str:
    digest = hashlib.md5()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def egset_wav(piece: str) -> Path:
    return catalog.egset12_dir() / f'{piece}.wav'


def egset_jams(piece: str) -> Path:
    return catalog.egset12_dir() / f'{piece}.jams'


def techs_audio(piece: str, signal: str) -> Path:
    folder = 'micamp' if signal == 'micamp' else 'directinput'
    return catalog.guitar_techs_dir() / 'P3_music' / 'audio' / folder / f'{folder}_{piece}.wav'


def techs_midi(piece: str) -> Path:
    return catalog.guitar_techs_dir() / 'P3_music' / 'midi' / f'midi_{piece}.mid'


def _parallel_events(data: dict):
    times = data.get('time') or []
    durations = data.get('duration') or []
    values = data.get('value') or []
    events = []
    for index, midi in enumerate(values):
        events.append({
            'time': float(times[index]) if index < len(times) else 0.0,
            'duration': float(durations[index]) if index < len(durations) else 0.05,
            'value': midi,
        })
    return events


def jams_note_midi(path: Path):
    """Every string's ``note_midi`` events. Pitch contours and tempo are ignored."""
    payload = json.loads(Path(path).read_text())
    notes = []
    for ann in payload.get('annotations') or []:
        if ann.get('namespace') != 'note_midi':
            continue
        data = ann.get('data')
        events = _parallel_events(data) if isinstance(data, dict) else list(data or [])
        for event in events:
            midi = int(round(float(event['value'])))
            start = float(event['time'])
            dur = float(event.get('duration') or 0.05)
            if dur <= 0:
                continue
            notes.append({'time': start, 'duration': max(0.03, dur), 'midi': midi})
    notes.sort(key=lambda n: (n['time'], n['midi']))
    return notes


def midi_notes(path: Path):
    """Non-drum notes from a per-string MIDI file, in seconds."""
    import pretty_midi

    pm = pretty_midi.PrettyMIDI(str(path))
    notes = []
    for inst in pm.instruments:
        if inst.is_drum:
            continue
        for note in inst.notes:
            dur = float(note.end - note.start)
            if dur <= 0:
                continue
            notes.append({
                'time': float(note.start),
                'duration': max(0.03, dur),
                'midi': int(note.pitch),
            })
    notes.sort(key=lambda n: (n['time'], n['midi']))
    return notes


def onset_lag_seconds(y, sr, notes, limit_s=LAG_LIMIT_S, hop=LAG_HOP):
    """Seconds to add to ``notes`` so their onsets line up with the audio envelope.

    Pitch-blind: the reference contributes onset times only, and no
    transcription is consulted. The search stays inside ±``limit_s``.
    Returns ``(shift_s, peak_correlation)``.
    """
    import librosa

    y = np.asarray(y, dtype=np.float32)
    if y.ndim == 2:
        y = y.mean(axis=1)
    if y.size < hop * 8 or not notes:
        return 0.0, 0.0
    env = np.asarray(librosa.onset.onset_strength(y=y, sr=int(sr), hop_length=hop), dtype=np.float64)
    if env.size < 4 or float(np.max(env)) <= 0:
        return 0.0, 0.0
    impulses = np.zeros(env.shape[0], dtype=np.float64)
    for note in notes:
        index = int(round(float(note['time']) * sr / hop))
        if 0 <= index < impulses.size:
            impulses[index] += 1.0
    if float(impulses.sum()) < 1:
        return 0.0, 0.0
    env = env - env.mean()
    impulses = impulses - impulses.mean()
    corr = np.correlate(env, impulses, mode='full')
    # np.correlate(env, impulses)[k] sums env[n+k] * impulses[n].
    # A positive k means the envelope is later than the impulses, so the
    # reference times need that same positive shift.
    lags = np.arange(-impulses.size + 1, env.size)
    max_lag = int(round(limit_s * sr / hop))
    mask = np.abs(lags) <= max_lag
    if not np.any(mask):
        return 0.0, 0.0
    window = corr[mask]
    best = int(np.argmax(window))
    denom = float(np.linalg.norm(env) * np.linalg.norm(impulses)) + 1e-12
    peak = float(window[best] / denom)
    shift = float(lags[mask][best] * hop / sr)
    return shift, peak


def _read_mono(path: Path):
    import soundfile as sf

    audio, sr = sf.read(path, always_2d=True, dtype='float32')
    return audio.mean(axis=1), int(sr)


def _clip_lag(audio_path: Path, notes):
    y, sr = _read_mono(audio_path)
    shift, peak = onset_lag_seconds(y, sr, notes)
    applied = 0.0 if peak < WEAK_PEAK else shift
    return {
        'shift_s': round(float(applied), 4),
        'estimated_shift_s': round(float(shift), 4),
        'peak': round(float(peak), 4),
        'weak': bool(peak < WEAK_PEAK),
    }


def _mean(values):
    return float(np.mean(values)) if values else 0.0


def choose_techs_signal(by_signal):
    """Prefer the miked amp unless DI is a clearly tighter pitch-blind alignment.

    The comparison is onset-envelope correlation, not note F1.
    ``by_signal`` maps a signal name to a list of lag records.
    """
    def stats(rows):
        return {
            'peak': _mean([row['peak'] for row in rows]),
            'abs_lag': _mean([abs(row['estimated_shift_s']) for row in rows]),
            'weak': sum(1 for row in rows if row['weak']),
        }

    mic = stats(by_signal['micamp'])
    di = stats(by_signal['directinput'])
    # DI wins only when its correlation is plainly stronger and its lag is tighter.
    if di['peak'] >= mic['peak'] + 0.05 and di['abs_lag'] + 0.005 < mic['abs_lag']:
        signal = 'directinput'
        reason = (
            f"direct input correlation {di['peak']:.3f} beats the miked amp {mic['peak']:.3f} "
            f"and its mean absolute lag is smaller ({di['abs_lag']*1000:.1f} ms vs {mic['abs_lag']*1000:.1f} ms)"
        )
    else:
        signal = 'micamp'
        reason = (
            f"miked amp kept (correlation {mic['peak']:.3f}, mean |lag| {mic['abs_lag']*1000:.1f} ms; "
            f"direct input {di['peak']:.3f}, {di['abs_lag']*1000:.1f} ms)"
        )
    def rounded(stats):
        return {key: round(value, 4) if isinstance(value, float) else value for key, value in stats.items()}

    return signal, reason, {'micamp': rounded(mic), 'directinput': rounded(di)}


def freeze_alignment(path: Path = ALIGNMENT):
    """Write the frozen lags. Requires the datasets on disk. Does not transcribe."""
    if not catalog.available_summary()['egset12'] or not catalog.available_summary()['guitar_techs']:
        raise FileNotFoundError(
            'EGSet12 and Guitar-TECHS excerpts must both be on disk before lags are frozen. '
            'Run: python -m benchmarks.regression.download'
        )
    clips = {}
    for clip in catalog.EGSET12_CLIPS:
        notes = jams_note_midi(egset_jams(clip['piece']))
        clips[clip['id']] = _clip_lag(egset_wav(clip['piece']), notes)
        clips[clip['id']]['signal'] = 'mic'
    techs = {}
    techs_notes = {}
    for clip in catalog.GUITAR_TECHS_CLIPS:
        techs_notes[clip['id']] = midi_notes(techs_midi(clip['piece']))
        techs[clip['id']] = {}
        for signal in TECHS_SIGNALS:
            techs[clip['id']][signal] = _clip_lag(techs_audio(clip['piece'], signal), techs_notes[clip['id']])
    by_signal = {
        signal: [techs[clip['id']][signal] for clip in catalog.GUITAR_TECHS_CLIPS]
        for signal in TECHS_SIGNALS
    }
    chosen, reason, stats = choose_techs_signal(by_signal)
    for clip in catalog.GUITAR_TECHS_CLIPS:
        chosen_row = dict(techs[clip['id']][chosen])
        chosen_row['signal'] = chosen
        chosen_row['alternatives'] = {
            signal: {'peak': techs[clip['id']][signal]['peak'],
                     'estimated_shift_s': techs[clip['id']][signal]['estimated_shift_s']}
            for signal in TECHS_SIGNALS
        }
        clips[clip['id']] = chosen_row
    payload = {
        'method': (
            'Pitch-blind onset-envelope cross-correlation against reference onset times. '
            f'Search limited to ±{LAG_LIMIT_S*1000:.0f} ms (hop {LAG_HOP}). '
            f'A peak below {WEAK_PEAK} stores a shift of 0. '
            'Transcription notes are not an input, and the lag is not chosen by note F1. '
            'Guitar-TECHS authors warn of up to 100 ms misalignment between signals; '
            'this one constant per excerpt is the correction. Residual error inside that '
            'bound is why note F1 at ±100 ms is locked beside F1 at ±50 ms.'
        ),
        'limit_s': LAG_LIMIT_S,
        'hop': LAG_HOP,
        'weak_peak': WEAK_PEAK,
        'guitar_techs_signal': chosen,
        'guitar_techs_signal_reason': reason,
        'guitar_techs_signal_stats': stats,
        'clips': clips,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + '\n')
    return payload


def frozen_shift(clip_id: str):
    """``(shift_s, detail)`` from the committed alignment, or ``(None, reason)``."""
    payload = load_alignment()
    if payload is None:
        return None, 'reference/electric_alignment.json is missing; run download --align'
    clip = (payload.get('clips') or {}).get(clip_id)
    if clip is None:
        return None, f'{clip_id} has no frozen lag'
    return float(clip['shift_s']), 'frozen'


def expected_sha256(dataset: str, name: str):
    manifest = load_manifest()
    if dataset == 'egset12':
        item = (manifest.get('egset12') or {}).get('files', {}).get(name) or {}
        return item.get('sha256')
    if dataset == 'guitar_techs_zip':
        return ((manifest.get('guitar_techs') or {}).get('archive') or {}).get('sha256')
    extracted = (manifest.get('guitar_techs') or {}).get('extracted') or {}
    return (extracted.get(name) or {}).get('sha256')

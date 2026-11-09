"""Score transcription backends on the regression library.

The transcriber receives audio only. Ground truth is applied after the notes
come back. Run from guitar-lab/:

    python -m benchmarks.regression --tier fast --backend basic_pitch
    python -m benchmarks.regression --tier all --backend basic_pitch --backend riley --backend gaps
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import soundfile as sf

from benchmarks.regression import catalog, material
from benchmarks.regression.metrics import (
    chroma_time_map, score_notes, src_span_for_dst_window, warp_times,
)
from benchmarks.regression.tab_notes import (INTRO_AUDIO_END_S, INTRO_ORIGIN_S, INTRO_STRETCH, INTRO_TAB_END_S,
                                             intro_reference)

REFERENCE = catalog.ROOT / 'reference'
MIDI_MIN, MIDI_MAX = 36, 88


def _round(row):
    out = {}
    for key, value in row.items():
        if isinstance(value, float):
            out[key] = round(value, 4)
        else:
            out[key] = value
    return out


def _read_any(path: Path):
    path = Path(path)
    if path.suffix.lower() in {'.aac', '.m4a', '.mp4'}:
        wav = path.with_suffix('.wav')
        if not wav.is_file():
            subprocess.check_call(
                ['ffmpeg', '-y', '-loglevel', 'error', '-i', str(path), '-acodec', 'pcm_s16le', str(wav)],
                stdout=subprocess.DEVNULL)
        path = wav
    audio, sr = sf.read(path, always_2d=True, dtype='float32')
    return audio, int(sr), path


def _write_slice(audio, sr, start, end, dest: Path):
    a = max(0, int(round(start * sr)))
    b = min(len(audio), int(round(end * sr)))
    if b <= a:
        b = min(len(audio), a + sr // 10)
    sf.write(dest, audio[a:b], sr, subtype='PCM_16')
    return (b - a) / sr


def _transcribe(backend, path, midi_min=MIDI_MIN, midi_max=MIDI_MAX):
    from server import models
    from server.transcribers import transcribe_file
    started = time.perf_counter()
    if backend == 'basic_pitch':
        notes = models.transcribe(path, midi_min=midi_min, midi_max=midi_max, backend='basic_pitch')
    else:
        notes = transcribe_file(backend, path, midi_min=midi_min, midi_max=midi_max)
    elapsed = time.perf_counter() - started
    return notes, elapsed


def _shift(notes, seconds):
    out = []
    for note in notes:
        copied = dict(note)
        copied['time'] = float(note['time']) + float(seconds)
        out.append(copied)
    return out


def _window_notes(notes, start, end):
    kept = []
    for note in notes:
        t = float(note['time'])
        if start <= t < end:
            kept.append(note)
    return kept


def _idmt_notes(xml_path: Path):
    root = ET.parse(xml_path).getroot()
    notes = []
    for event in root.iter('event'):
        pitch = event.findtext('pitch')
        onset = event.findtext('onsetSec')
        offset = event.findtext('offsetSec')
        if pitch is None or onset is None or offset is None:
            continue
        start = float(onset)
        end = float(offset)
        notes.append({'time': start, 'duration': max(0.03, end - start), 'midi': int(float(pitch))})
    notes.sort(key=lambda n: (n['time'], n['midi']))
    return notes


def _score_file(backend, audio_path, ref, window=None, score_end=None):
    audio, sr, path = _read_any(audio_path)
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / 'clip.wav'
        if window is None:
            sf.write(dest, audio, sr, subtype='PCM_16')
            duration = len(audio) / sr
            origin = 0.0
            ref_w = ref
        else:
            start, end = window
            duration = _write_slice(audio, sr, start, end, dest)
            origin = start
            ref_w = _window_notes(ref, start, end)
        notes, elapsed = _transcribe(backend, dest)
    notes = _shift(notes, origin)
    if score_end is not None:
        notes = _window_notes(notes, origin, score_end)
        ref_w = _window_notes(ref_w, origin, score_end)
    metrics = score_notes(notes, ref_w)
    metrics['audio_s'] = round(float(duration), 3)
    metrics['seconds'] = round(float(elapsed), 3)
    metrics['seconds_per_audio_minute'] = round(elapsed / max(duration / 60.0, 1e-6), 2)
    return metrics


def score_guitarset(backend, tier):
    rows = []
    for clip in catalog.GUITARSET_CLIPS:
        if tier == 'fast' and not clip['fast']:
            continue
        wav = catalog.GUITARSET / clip['wav']
        if not wav.is_file():
            rows.append({'id': clip['id'], 'category': clip['category'], 'status': 'missing'})
            continue
        digest = hashlib.sha256(wav.read_bytes()).hexdigest()
        ref = catalog.guitarset_notes(catalog.GUITARSET / clip['notes'])
        window = (0.0, clip['fast_window_s']) if tier == 'fast' and clip.get('fast_window_s') else None
        metrics = _score_file(backend, wav, ref, window=window)
        rows.append(_round({
            'id': clip['id'], 'category': clip['category'], 'style': clip['style'],
            'status': 'ok', 'sha256': digest, 'sha256_ok': digest == clip['sha256'],
            'window_s': None if window is None else list(window),
            **metrics,
        }))
    return rows


def score_rendered(backend, tier):
    rows = []
    clear_notes = None
    for clip in catalog.RENDERED:
        if tier == 'fast' and not clip['fast']:
            continue
        audio, ref, _voice = material.render_case(clip['id'])
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / f"{clip['id']}.wav"
            sf.write(dest, audio, 22050, subtype='PCM_16')
            duration = len(audio) / 22050
            notes, elapsed = _transcribe(backend, dest)
        metrics = score_notes(notes, ref)
        row = {
            'id': clip['id'], 'category': clip['category'], 'voice': clip['voice'],
            'status': 'ok', 'audio_s': round(duration, 3), 'seconds': round(elapsed, 3),
            'seconds_per_audio_minute': round(elapsed / max(duration / 60.0, 1e-6), 2),
            **metrics,
        }
        if clip['id'] == 'ks_clear':
            clear_notes = notes
        if clip['id'] == 'ks_reverb' and clear_notes is not None:
            # Same timeline. The clear transcription is the reference, not the chart.
            row['cross_f1'] = round(score_notes(notes, clear_notes)['note_f1'], 4)
        rows.append(_round(row))
    return rows


def score_idmt(backend):
    folder = catalog.idmt_dir()
    rows = []
    if not catalog.available_summary()['idmt']:
        return [{'id': 'idmt', 'category': 'clean_electric', 'status': 'missing',
                 'detail': 'IDMT-SMT-Guitar dataset3 is not in benchmarks/regression/data/private/idmt. '
                           'CC BY-NC-ND: the audio is not in git.'}]
    for name in catalog.IDMT_PIECES:
        wav = folder / 'audio' / f'{name}.wav'
        xml = folder / 'annotation' / f'{name}.xml'
        ref = _idmt_notes(xml)
        metrics = _score_file(backend, wav, ref)
        rows.append(_round({
            'id': f'idmt_{name}', 'category': 'clean_electric', 'status': 'ok',
            'instrument': 'electric guitar, direct input', **metrics,
        }))
    return rows


def score_user_pair(backend):
    takes = catalog.user_takes()
    if not catalog.available_summary()['user_reverb_pair']:
        return [{'id': 'user_reverb_pair', 'category': 'reverb_clear', 'status': 'missing',
                 'detail': 'Place take_a_4m51.aac (reverb) and take_c_synth_4m58.aac (clear) '
                           'in benchmarks/regression/data/private/user/.'}]
    clear_audio, clear_sr, _ = _read_any(takes['clear'])
    wet_audio, wet_sr, _ = _read_any(takes['reverb'])
    src_t, dst_t = chroma_time_map(wet_audio, wet_sr, clear_audio, clear_sr)
    rows = []
    for index, (t0, t1) in enumerate(catalog.USER_WINDOWS):
        wet_lo, wet_hi = src_span_for_dst_window(src_t, dst_t, t0, t1, pad=1.0)
        wet_hi = min(wet_hi, len(wet_audio) / wet_sr)
        clear_hi = min(t1, len(clear_audio) / clear_sr)
        with tempfile.TemporaryDirectory() as tmp:
            clear_path = Path(tmp) / 'clear.wav'
            wet_path = Path(tmp) / 'wet.wav'
            clear_dur = _write_slice(clear_audio, clear_sr, t0, clear_hi, clear_path)
            wet_dur = _write_slice(wet_audio, wet_sr, wet_lo, wet_hi, wet_path)
            clear_notes, clear_s = _transcribe(backend, clear_path)
            wet_notes, wet_s = _transcribe(backend, wet_path)
        clear_notes = _shift(clear_notes, t0)
        wet_abs = _shift(wet_notes, wet_lo)
        warped_times = warp_times([n['time'] for n in wet_abs], src_t, dst_t)
        warped = []
        for note, when in zip(wet_abs, warped_times):
            if t0 <= float(when) < t1:
                copied = dict(note)
                copied['time'] = float(when)
                warped.append(copied)
        # Clear notes are the reference. The reverb take is the estimate.
        # No chart is involved.
        metrics = score_notes(warped, _window_notes(clear_notes, t0, t1))
        elapsed = clear_s + wet_s
        audio_s = clear_dur + wet_dur
        rows.append(_round({
            'id': f'user_reverb_w{index}',
            'category': 'reverb_clear',
            'status': 'ok',
            'clear_window_s': [t0, t1],
            'reverb_slice_s': [round(wet_lo, 3), round(wet_hi, 3)],
            'cross_f1': metrics['note_f1'],
            'cross_onset_f1': metrics['onset_f1'],
            'cross_pitch_recall_300ms': metrics['pitch_recall_300ms'],
            'n_clear': metrics['n_ref'],
            'n_reverb': metrics['n_est'],
            'audio_s': round(audio_s, 3),
            'seconds': round(elapsed, 3),
            'seconds_per_audio_minute': round(elapsed / max(audio_s / 60.0, 1e-6), 2),
            'alignment': 'chroma DTW, note F1 was not an input',
        }))
    return rows


def score_metallica(backend):
    paths = catalog.metallica_paths()
    if not catalog.available_summary()['metallica']:
        return [{'id': 'metallica_one_intro', 'category': 'full_band_intro', 'status': 'missing',
                 'detail': 'song.mp3 and song.gp4 are not in benchmarks/regression/data/private/metallica/. '
                           'The commercial recording is not in git.'}]
    ref = intro_reference(paths['tab'])
    # 50 ms of audio past the window so an onset on the last note can still match.
    # Estimates after the window are dropped; they are not extra credit.
    end = INTRO_AUDIO_END_S
    window = (INTRO_ORIGIN_S, end + 0.05)
    metrics = _score_file(backend, paths['audio'], ref, window=window, score_end=end)
    # Estimates are shifted onto the file clock by _score_file. Drop anything
    # the slice tail picked up past the scored intro.
    return [_round({
        'id': 'metallica_one_intro',
        'category': 'full_band_intro',
        'status': 'ok',
        'origin_s': INTRO_ORIGIN_S,
        'tab_window_s': [0.0, INTRO_TAB_END_S],
        'audio_window_s': [INTRO_ORIGIN_S, round(INTRO_AUDIO_END_S, 3)],
        'tempo_stretch': round(INTRO_STRETCH, 4),
        'separation': 'not applied; the intro is the clean guitar before the band',
        'alignment': 'beat-tracked tempo (99.4 BPM) and onset-envelope origin; no transcription F1 used',
        **metrics,
    })]


def score_backend(backend, tier):
    rows = []
    rows.extend(score_guitarset(backend, 'fast' if tier == 'fast' else 'full'))
    rows.extend(score_rendered(backend, 'fast' if tier == 'fast' else 'full'))
    if tier in ('full', 'all'):
        rows.extend(score_idmt(backend))
        rows.extend(score_user_pair(backend))
        rows.extend(score_metallica(backend))
    return rows


def _category_value(row):
    if row.get('status') != 'ok':
        return None
    if row['category'] == 'reverb_clear' and 'cross_f1' in row and row['id'].startswith('user_'):
        return row['cross_f1']
    if 'note_f1' in row:
        return row['note_f1']
    return row.get('cross_f1')


def summarise(rows):
    buckets = {}
    for row in rows:
        if row.get('status') != 'ok':
            continue
        value = _category_value(row)
        if value is None:
            continue
        buckets.setdefault(row['category'], []).append(value)
    return {name: round(float(np.mean(values)), 4) for name, values in sorted(buckets.items())}


def compare_backends(results, coverage):
    """Opt in unless a backend is at least Basic Pitch on every scored category and clearly better.

    A missing category (no EGDB amp recordings, no Carcassi audio) blocks a
    default switch: we do not treat 'unmeasured' as a win.
    """
    base = results.get('basic_pitch', {}).get('categories') or {}
    report = []
    for name, payload in results.items():
        if name == 'basic_pitch' or name.startswith('_'):
            continue
        cats = payload.get('categories') or {}
        losses = []
        missing = []
        gains = []
        for category, base_value in base.items():
            if category not in cats:
                missing.append(category)
                continue
            delta = cats[category] - base_value
            if delta < -0.005:
                losses.append({'category': category, 'basic_pitch': base_value, 'backend': cats[category], 'delta': round(delta, 4)})
            else:
                gains.append({'category': category, 'delta': round(delta, 4)})
        unmeasured = []
        if not coverage.get('egdb'):
            unmeasured.append('amp-distorted electric (EGDB clean/amp pairs were not obtainable)')
        if not coverage.get('carcassi_audio'):
            unmeasured.append('Carcassi Op.60 No.1 recording (aligned MIDI only; audio not located)')
        clearly = bool(gains) and all(item['delta'] >= 0.02 for item in gains) and not losses and not missing and not unmeasured
        # "Clearly better" requires a real margin on every measured category, not a tie.
        mean_delta = None
        if base and cats:
            shared = [cats[k] - base[k] for k in base if k in cats]
            mean_delta = round(float(np.mean(shared)), 4) if shared else None
        promote = (not losses and not missing and not unmeasured and mean_delta is not None and mean_delta >= 0.02
                   and all(cats[k] + 1e-9 >= base[k] for k in base if k in cats))
        report.append({
            'backend': name,
            'default': bool(promote),
            'losses': losses,
            'missing_categories': missing,
            'unmeasured': unmeasured,
            'mean_delta': mean_delta,
            'clearly_better': clearly and promote,
        })
    return report


def run(backends, tier):
    payload = {'tier': tier, 'coverage': catalog.available_summary(), 'backends': {}}
    for backend in backends:
        try:
            rows = score_backend(backend, tier)
            error = None
        except Exception as exc:  # noqa: BLE001 — one backend must not hide the others
            rows = []
            error = f'{type(exc).__name__}: {exc}'
        payload['backends'][backend] = {
            'error': error,
            'rows': rows,
            'categories': summarise(rows),
        }
    payload['decision'] = compare_backends(payload['backends'], payload['coverage'])
    return payload


def write_report(payload, path: Path):
    lines = [
        '# Transcription regression',
        '',
        'Basic Pitch is the in-app default. Other backends are opt-in '
        '(`FRETWORK_TRANSCRIBER`) unless the decision below says otherwise.',
        'Charts are not an input to any model. The Metallica intro is timed at the recording\'s '
        f'beat-tracked tempo (tab 0 = {INTRO_ORIGIN_S} s, stretch {INTRO_STRETCH:.4f}), not a whole-song F1 search.',
        '',
        '## Coverage',
        '',
    ]
    for key, value in payload['coverage'].items():
        lines.append(f'- {key}: {"present" if value else "not available"}')
    lines += ['', '## Category means', '', '| backend | ' + ' | '.join(_all_categories(payload)) + ' |',
              '| --- | ' + ' | '.join('---' for _ in _all_categories(payload)) + ' |']
    cats = _all_categories(payload)
    for name, body in payload['backends'].items():
        cells = [name]
        for category in cats:
            value = body['categories'].get(category)
            cells.append('' if value is None else f'{value:.3f}')
        lines.append('| ' + ' | '.join(cells) + ' |')
    lines += ['', '## Decision', '']
    if not payload['decision']:
        lines.append('Only Basic Pitch was scored.')
    for item in payload['decision']:
        if item['default']:
            lines.append(f"- `{item['backend']}` is at least Basic Pitch on every measured category "
                         f"and ahead by {item['mean_delta']} on average, with nothing unmeasured. "
                         'It may be the default.')
        else:
            lines.append(f"- `{item['backend']}` stays opt-in.")
            for loss in item['losses']:
                lines.append(f"  - loses {loss['category']}: {loss['backend']:.3f} vs Basic Pitch {loss['basic_pitch']:.3f} ({loss['delta']:+.3f})")
            for missing in item['missing_categories']:
                lines.append(f'  - no score for {missing}')
            for gap in item['unmeasured']:
                lines.append(f'  - unmeasured: {gap}')
            if item['mean_delta'] is not None:
                lines.append(f"  - mean category delta vs Basic Pitch: {item['mean_delta']:+.3f}")
    lines += ['', '## CPU time', '']
    lines.append('Seconds of wall clock per minute of audio, around the transcribe call, on this CPU. '
                 'The first clip of Riley and of GAPS includes the weight load.')
    lines.append('')
    for name, body in payload['backends'].items():
        rates = [row['seconds_per_audio_minute'] for row in body.get('rows') or []
                 if row.get('status') == 'ok' and row.get('seconds_per_audio_minute') is not None]
        if not rates:
            continue
        lines.append(f'- {name}: {min(rates):.1f}–{max(rates):.1f} s per minute of audio')
    lines += ['', '## Where a backend is worse on a clip', '']
    lines.append('Category means hide this. A drop of more than 0.005 against Basic Pitch:')
    lines.append('')
    worse = _clip_losses(payload)
    if not worse:
        lines.append('No clip-level drops.')
    else:
        for item in worse:
            lines.append(
                f"- `{item['backend']}` {item['id']} ({item['category']}): "
                f"{item['value']:.3f} vs Basic Pitch {item['base']:.3f} ({item['delta']:+.3f})"
            )
    lines += ['', '## Clips', '']
    for name, body in payload['backends'].items():
        lines.append(f'### {name}')
        lines.append('')
        if body['error']:
            lines.append(f'Error: {body["error"]}')
            lines.append('')
            continue
        lines.append('| clip | category | note F1 | onset F1 | pitch recall @300ms | cross F1 | s / min audio |')
        lines.append('| --- | --- | --- | --- | --- | --- | --- |')
        for row in body['rows']:
            if row.get('status') != 'ok':
                lines.append(f"| {row.get('id')} | {row.get('category')} |  |  |  |  | missing |")
                continue
            lines.append(
                f"| {row['id']} | {row['category']} | {_fmt(row.get('note_f1'))} | {_fmt(row.get('onset_f1'))} | "
                f"{_fmt(row.get('pitch_recall_300ms'))} | {_fmt(row.get('cross_f1'))} | {_fmt(row.get('seconds_per_audio_minute'))} |"
            )
        lines.append('')
    lines += [
        '## Licenses and what was not run',
        '',
        '- Basic Pitch: Apache-2.0, ONNX, default.',
        '- Riley guitar-fl and GAPS: MIT weights and wrapper; Kong CRNN inference is Apache-2.0. '
        'Optional (`requirements-transcription-extras.txt`). Decoder thresholds are the published 0.3/0.3/0.1, not fit here.',
        '- YourMT3+: built in (server/yourmt3, Apache-2.0); run it with --backend yourmt3.',
        '- GuitarSet excerpts: CC BY 4.0, Xi et al., ISMIR 2018. Player 05.',
        '- IDMT-SMT-Guitar: CC BY-NC-ND 4.0. Audio is local only. These pieces are clean direct-input electric, not amp distortion.',
        '- EGDB / EGDB-PG: the paired clean-and-amp set was not downloaded (the public FLAC bundle is 135 GB; the original set is on request).',
        '- Carcassi: `ground_truth_aligned_to_recording.mid` is in the tree. The recording it was aligned to was not in the attachment and was not found. '
        'A different public performance was not substituted.',
        '- Metallica and the user AAC takes: local only, not committed.',
        '',
    ]
    path.write_text('\n'.join(lines))


def _metric(row):
    if row.get('id', '').startswith('user_'):
        return row.get('cross_f1')
    return row.get('note_f1', row.get('cross_f1'))


def _clip_losses(payload, slack=0.005):
    base_rows = {row['id']: row for row in payload['backends'].get('basic_pitch', {}).get('rows') or []}
    losses = []
    for name, body in payload['backends'].items():
        if name == 'basic_pitch':
            continue
        for row in body.get('rows') or []:
            if row.get('status') != 'ok' or row['id'] not in base_rows:
                continue
            value, base = _metric(row), _metric(base_rows[row['id']])
            if value is None or base is None:
                continue
            delta = value - base
            if delta < -slack:
                losses.append({
                    'backend': name, 'id': row['id'], 'category': row.get('category'),
                    'value': value, 'base': base, 'delta': delta,
                })
    return losses


def _fmt(value):
    if value is None:
        return ''
    return f'{value:.3f}'


def _all_categories(payload):
    names = []
    for body in payload['backends'].values():
        for name in body['categories']:
            if name not in names:
                names.append(name)
    return names


def main(argv=None):
    parser = argparse.ArgumentParser(description='Score guitar transcription backends')
    parser.add_argument('--tier', choices=('fast', 'full', 'all'), default='all')
    parser.add_argument('--backend', action='append', dest='backends')
    parser.add_argument('--out', type=Path, default=None)
    args = parser.parse_args(argv)
    backends = args.backends or ['basic_pitch']
    tier = 'full' if args.tier == 'all' else args.tier
    payload = run(backends, tier)
    out = args.out or (REFERENCE / f'{tier}.json')
    out.parent.mkdir(parents=True, exist_ok=True)
    serial = payload
    out.write_text(json.dumps(serial, indent=2))
    report_path = catalog.ROOT / 'RESULTS.md'
    write_report(serial, report_path)
    print(f'wrote {out}')
    print(f'wrote {report_path}')
    for name, body in serial['backends'].items():
        print(name, body['categories'] or body['error'])
    for item in serial['decision']:
        print('decision', item['backend'], 'default' if item['default'] else 'opt-in', 'mean', item['mean_delta'])


if __name__ == '__main__':
    main()

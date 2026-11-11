"""Score the user's own recordings with the song-path decoder.

There is no ground-truth tab for these files. The report locks what the
decoder currently emits (how many notes, which pitch classes, whether two
takes still agree, and whether playback still starts on those note times).
A later change that moves those numbers is a behaviour change, not a proven
improvement.

The packaged ``current_upload.aac`` is byte-identical to ``take_c_synth_4m58.aac``.
Take A, take B, and take C are three earlier files. Earlier notes describe A
and C as separate performances of one song, and B as a different section.
They are not a confirmed dry/wet pair, and this module does not treat them
as one.

Audio stays out of git. Point ``--root`` at a directory that holds the four
AAC files, or leave them in ``benchmarks/regression/data/private/user/``.
"""
from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import os
from pathlib import Path

import numpy as np

from benchmarks.regression.metrics import chroma_time_map, score_notes, warp_times

# Hashes of the files this lock was measured on. A different file must not
# silently reuse these numbers.
REQUIRED = {
    'current_upload.aac': 'cb121e0fd26f48cec619e651fb77a9587bde54b54891e959fd879b5465b14564',
    'take_a_4m51.aac': 'f0e075a1c53be2fabd5fb0e3305c34420e995e85731a7d7c798f75e7e0a97322',
    'take_b_1m44.aac': '8aa776e0739f1101466e00d939900f0e3ac66f41349be9e2f92621bd91c3267e',
    'take_c_synth_4m58.aac': 'cb121e0fd26f48cec619e651fb77a9587bde54b54891e959fd879b5465b14564',
}

# current_upload.aac and take C are the same bytes. The manifest that came
# with the earlier takes named a different hash (9c8e4494…) for a newer upload
# that was not in that package, and it was not substituted there. The zip
# delivered for this run as the latest recording hashes to take C.
SAME_BYTES = ('current_upload.aac', 'take_c_synth_4m58.aac')

# Pairs worth describing. None of them is a ground-truth alignment.
PAIRS = (
    ('take_a_4m51.aac', 'take_c_synth_4m58.aac', 'separate performances of one song, not a dry/wet pair'),
    ('take_a_4m51.aac', 'take_b_1m44.aac', 'earlier notes say B does not line up with A'),
    ('current_upload.aac', 'take_c_synth_4m58.aac', 'same bytes, so the decoder must emit the same notes'),
)

ROOT = Path(__file__).resolve().parent
LOCK = ROOT / 'reference' / 'user_recordings.json'


def recordings_dir() -> Path:
    env = os.environ.get('FRETWORK_USER_RECORDINGS')
    if env:
        return Path(env)
    from benchmarks.regression import catalog
    return catalog.PRIVATE / 'user'


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def present_files(root: Path | None = None):
    """``(name, path, sha256 or None)`` for the four required takes."""
    folder = Path(root) if root is not None else recordings_dir()
    found = []
    for name, expected in REQUIRED.items():
        path = folder / name
        digest = sha256_file(path) if path.is_file() and path.stat().st_size > 0 else None
        found.append((name, path, digest, expected))
    return found


def audio_ready(root: Path | None = None) -> bool:
    return all(digest == expected for _name, _path, digest, expected in present_files(root))


def _decoder_token() -> str:
    """Changes when the song-path decoder changes, so a cache cannot hide a regression."""
    from server import models, riley, songs
    from server import transcribers
    parts = []
    for fn in (
        riley.posteriors, riley.decode, riley.notes_from_posteriors,
        transcribers._transcribe_riley_path, transcribers.transcribe_file,
        models.merge_note_lists, models.stereo_tx_channels, songs.decode,
    ):
        parts.append(inspect.getsource(fn))
    return hashlib.sha256(''.join(parts).encode()).hexdigest()[:16]


def _cache_path(audio_sha: str) -> Path:
    folder = recordings_dir() / '.note-cache' / _decoder_token()
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f'{audio_sha}.json'


def _transcribe_song_path(path: Path):
    """Decode like a song upload, then the same Riley entry the song pipeline uses.

    Stereo files with both channels active are transcribed per channel and
    merged. That is the song path, not a mono mix-down.
    """
    import soundfile as sf

    from server import songs
    from server.transcribers import transcribe_file

    audio, sr = songs.decode(path, min_seconds=2)
    # songs.decode refuses anything over ten minutes and anything silent.
    tmp = path.with_suffix('.songpath.wav')
    try:
        sf.write(tmp, audio, sr, subtype='PCM_16')
        notes = transcribe_file('riley', tmp)
    finally:
        tmp.unlink(missing_ok=True)
    return notes, float(len(audio) / sr), int(sr), audio


def transcribe_take(path: Path, audio_sha: str):
    """Notes for one file. Identical bytes share one transcription."""
    cache = _cache_path(audio_sha)
    if cache.is_file():
        payload = json.loads(cache.read_text())
        return payload['notes'], float(payload['duration_s'])
    notes, duration, _sr, _audio = _transcribe_song_path(path)
    slim = [
        {'time': round(float(n['time']), 4), 'duration': round(float(n['duration']), 4), 'midi': int(n['midi'])}
        for n in notes
    ]
    cache.write_text(json.dumps({'duration_s': duration, 'notes': slim}))
    return slim, duration


def pitch_classes(notes) -> list[float]:
    counts = np.zeros(12, dtype=float)
    for note in notes:
        counts[int(note['midi']) % 12] += 1
    total = float(counts.sum()) or 1.0
    return [round(float(v / total), 4) for v in counts]


def timing_summary(notes, duration_s: float) -> dict:
    if not notes:
        return {
            'n_notes': 0, 'duration_s': round(float(duration_s), 3), 'notes_per_second': 0.0,
            'median_duration_s': None, 'p10_duration_s': None, 'short_fraction': None,
            'median_ioi_s': None, 'first_onset_s': None, 'last_onset_s': None,
            'pitch_class': [0.0] * 12,
        }
    times = np.sort(np.asarray([float(n['time']) for n in notes], dtype=float))
    durations = np.asarray([float(n['duration']) for n in notes], dtype=float)
    ioi = np.diff(times)
    return {
        'n_notes': len(notes),
        'duration_s': round(float(duration_s), 3),
        'notes_per_second': round(len(notes) / max(float(duration_s), 1e-6), 4),
        'median_duration_s': round(float(np.median(durations)), 4),
        'p10_duration_s': round(float(np.percentile(durations, 10)), 4),
        'short_fraction': round(float(np.mean(durations < 0.08)), 4),
        'median_ioi_s': round(float(np.median(ioi)), 4) if len(ioi) else None,
        'first_onset_s': round(float(times[0]), 4),
        'last_onset_s': round(float(times[-1]), 4),
        'pitch_class': pitch_classes(notes),
    }


def playback_onset_lag_s(notes, sr=22050, limit=12) -> float | None:
    """How late the acoustic playback attack is, relative to the note time.

    The first notes inside the opening eight seconds are rendered. A change
    that delays playback moves this number. It is not a claim about the
    recording's true note times.
    """
    from server.fx.playback import render_acoustic

    chosen = [n for n in notes if 0.2 <= float(n['time']) <= 8.0][:limit]
    if len(chosen) < 4:
        chosen = list(notes[:limit])
    if len(chosen) < 1:
        return None
    end = max(float(n['time']) + float(n['duration']) for n in chosen) + 0.3
    rendered = np.asarray(render_acoustic(chosen, sr=sr, length_s=end), dtype=float)
    if rendered.ndim == 2:
        rendered = rendered.mean(axis=1)
    lags = []
    window = int(0.04 * sr)
    for note in chosen:
        start = int(round(float(note['time']) * sr))
        chunk = rendered[start:start + window]
        if len(chunk) == 0 or float(np.max(np.abs(chunk))) < 1e-8:
            lags.append(0.04)
            continue
        threshold = 0.2 * float(np.max(np.abs(chunk)))
        hit = int(np.argmax(np.abs(chunk) >= threshold))
        lags.append(hit / sr)
    return round(float(np.median(lags)), 4)


def pitch_class_cosine(left, right) -> float:
    a = np.asarray(pitch_classes(left) if left and isinstance(left[0], dict) else left, dtype=float)
    b = np.asarray(pitch_classes(right) if right and isinstance(right[0], dict) else right, dtype=float)
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0:
        return 0.0
    return round(float(np.dot(a, b) / denom), 4)


def _load_for_dtw(path: Path):
    """Song-path decode, down to the rate the chroma map uses. Audio only."""
    from server import songs
    audio, sr = songs.decode(path, min_seconds=2)
    return np.asarray(audio, dtype=np.float32), int(sr)


def agreement(src_notes, dst_notes, src_audio, src_sr, dst_audio, dst_sr) -> dict:
    """How well src's notes land on dst's notes after an audio-only time map.

    The map is chroma DTW. Note F1 is not an input to the alignment. With no
    chart, a high number means the two transcriptions tell the same story,
    not that either story is the true tab.
    """
    if not src_notes or not dst_notes:
        return {'note_f1_50': 0.0, 'onset_f1_50': 0.0, 'pitch_class_cosine': pitch_class_cosine(src_notes, dst_notes)}
    src_t, dst_t = chroma_time_map(src_audio, src_sr, dst_audio, dst_sr)
    warped_times = warp_times([n['time'] for n in src_notes], src_t, dst_t)
    warped = []
    for note, when in zip(src_notes, warped_times):
        copied = dict(note)
        copied['time'] = float(when)
        warped.append(copied)
    metrics = score_notes(warped, dst_notes, onset_tol=0.05)
    return {
        'note_f1_50': round(float(metrics['note_f1']), 4),
        'onset_f1_50': round(float(metrics['onset_f1']), 4),
        'pitch_class_cosine': pitch_class_cosine(src_notes, dst_notes),
    }


def score_recordings(root: Path | None = None, backend_check: bool = True) -> dict:
    """Transcribe the four files and summarise them. Raises if a hash does not match."""
    if backend_check:
        from server.transcribers import availability
        if not availability().get('riley', {}).get('installed'):
            raise RuntimeError('Riley is not installed, so the song-path decoder cannot be scored.')
    folder = Path(root) if root is not None else recordings_dir()
    files = present_files(folder)
    missing = [name for name, _path, digest, _expected in files if digest is None]
    if missing:
        raise FileNotFoundError('private recordings missing: ' + ', '.join(missing))
    mismatched = [
        {'file': name, 'sha256': digest, 'expected': expected}
        for name, _path, digest, expected in files if digest != expected
    ]
    if mismatched:
        raise ValueError(f'recording checksum does not match the locked files: {mismatched}')

    by_hash: dict = {}
    rows = []
    decoded = {}
    for name, path, digest, _expected in files:
        if digest not in by_hash:
            notes, duration = transcribe_take(path, digest)
            by_hash[digest] = (notes, duration)
        notes, duration = by_hash[digest]
        if name not in decoded:
            decoded[name] = _load_for_dtw(path)
        summary = timing_summary(notes, duration)
        summary['playback_onset_lag_s'] = playback_onset_lag_s(notes)
        rows.append({'id': name, 'sha256': digest, **summary})

    pairs = []
    notes_for = {name: by_hash[digest][0] for name, _path, digest, _expected in files}
    for src, dst, why in PAIRS:
        src_audio, src_sr = decoded[src]
        dst_audio, dst_sr = decoded[dst]
        if REQUIRED[src] == REQUIRED[dst]:
            # Same bytes. Compare the note lists directly so a cache mix-up
            # cannot look like a successful alignment.
            metrics = score_notes(notes_for[src], notes_for[dst], onset_tol=0.05)
            measured = {
                'note_f1_50': round(float(metrics['note_f1']), 4),
                'onset_f1_50': round(float(metrics['onset_f1']), 4),
                'pitch_class_cosine': pitch_class_cosine(notes_for[src], notes_for[dst]),
            }
        else:
            measured = agreement(notes_for[src], notes_for[dst], src_audio, src_sr, dst_audio, dst_sr)
        pairs.append({'src': src, 'dst': dst, 'why': why, **measured})
    return {
        'ground_truth': False,
        'decoder': 'riley song path (upload decode, then per-channel transcription when both channels are active)',
        'same_bytes': list(SAME_BYTES),
        'rows': rows,
        'pairs': pairs,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description='Score private user recordings. No ground-truth tab.')
    parser.add_argument('--root', type=Path, default=None)
    parser.add_argument('--out', type=Path, default=None)
    args = parser.parse_args(argv)
    payload = score_recordings(args.root)
    text = json.dumps(payload, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + '\n')
        print(f'wrote {args.out}')
    print(text)


if __name__ == '__main__':
    main()

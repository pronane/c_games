"""Learn-a-song sessions: one upload -> all instruments separated, the chosen instrument
transcribed to tab and notation, plus key, tempo, chords and a tuning suggestion.

Same privacy model as practice jobs: explicit consent, temporary files, one-hour expiry,
immediate deletion on request. Streaming-service links are refused (their terms forbid
downloading and the audio is DRM-protected); only direct audio-file links are fetched.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import ipaddress
from pathlib import Path
import shutil
import socket
import subprocess
import time
from urllib.parse import urljoin, urlparse
from uuid import uuid4

from fastapi import APIRouter, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
import numpy as np
import soundfile as sf

from . import models
from . import song_analysis as sa
from .instruments import CATALOGUE, resolve_profile
from .runtime import EXECUTOR, LOCK, ROOT, TTL_SECONDS

router = APIRouter(prefix='/api/songs')
SONGS: dict = {}
MAX_SONG_BYTES = 120*1024*1024
MAX_SONG_SECONDS = 10*60
TARGET_SR = 44100
STREAMING_HOSTS = ('youtube.com', 'youtu.be', 'spotify.com', 'soundcloud.com', 'music.apple.com', 'tidal.com',
                   'deezer.com', 'bandcamp.com', 'music.amazon', 'pandora.com')


@dataclass
class Song:
    id: str
    folder: Path
    instrument: str
    name: str
    status: str = 'queued'
    stage: str = 'Waiting for audio worker'
    created: float = field(default_factory=time.time)
    result: dict | None = None
    error: str | None = None
    cancelled: bool = False
    active: bool = True
    notes: dict = field(default_factory=dict)     # part id -> transcribed notes (pre-fingering)


def client(x_fretwork_client):
    if x_fretwork_client != 'studio':
        raise HTTPException(403, 'Use the studio client header.')


def cleanup():
    with LOCK:
        for key, song in list(SONGS.items()):
            if time.time()-song.created > TTL_SECONDS:
                song.cancelled = True
                if not song.active:
                    shutil.rmtree(song.folder, ignore_errors=True)
                    del SONGS[key]


def get_song(key) -> Song:
    cleanup()
    with LOCK:
        song = SONGS.get(key)
        if not song or song.cancelled:
            raise HTTPException(404, 'Song session not found or expired.')
        return song


def serialize(song: Song):
    return {'id': song.id, 'name': song.name, 'instrument': song.instrument, 'status': song.status,
            'stage': song.stage, 'error': song.error, 'result': song.result,
            'expires_at': song.created+TTL_SECONDS}


# ---------------------------------------------------------------- input

def check_public_url(url: str):
    """Allow only https links to public hosts; refuse streaming services and private networks."""
    parsed = urlparse(url)
    if parsed.scheme != 'https' or not parsed.hostname:
        raise HTTPException(422, 'Use an https:// link to an audio file.')
    host = parsed.hostname.lower()
    if any(host == h or host.endswith('.'+h) for h in STREAMING_HOSTS):
        raise HTTPException(422, 'Streaming-service links (YouTube, Spotify, SoundCloud and similar) cannot be '
                                 'downloaded: their terms forbid it and the audio is protected. Upload a file you own instead.')
    try:
        infos = socket.getaddrinfo(host, parsed.port or 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise HTTPException(422, 'That web address could not be found.') from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global:
            raise HTTPException(422, 'Links to private or local network addresses are not allowed.')


async def fetch_url(url: str, dest: Path):
    import httpx
    async with httpx.AsyncClient(timeout=60, follow_redirects=False) as http:
        for _ in range(4):
            check_public_url(url)
            async with http.stream('GET', url, headers={'User-Agent': 'GuitarLab/0.3'}) as r:
                if r.status_code in (301, 302, 303, 307, 308) and 'location' in r.headers:
                    url = urljoin(url, r.headers['location'])
                    continue
                if r.status_code != 200:
                    raise HTTPException(422, f'The link returned HTTP {r.status_code}.')
                kind = r.headers.get('content-type', '').split(';')[0].strip().lower()
                if not (kind.startswith('audio/') or kind in ('application/octet-stream', 'video/mp4', 'application/ogg')):
                    raise HTTPException(422, 'That link is a web page, not an audio file. Link directly to an MP3, WAV, FLAC, M4A or OGG file.')
                total = 0
                with dest.open('wb') as out:
                    async for block in r.aiter_bytes(1024*1024):
                        total += len(block)
                        if total > MAX_SONG_BYTES:
                            raise HTTPException(413, 'Songs must be under 120 MB.')
                        out.write(block)
                return Path(urlparse(url).path).name or 'linked-song'
        raise HTTPException(422, 'Too many redirects.')


async def save_upload(upload: UploadFile, dest: Path):
    total = 0
    try:
        with dest.open('wb') as out:
            while block := await upload.read(1024*1024):
                total += len(block)
                if total > MAX_SONG_BYTES:
                    raise HTTPException(413, 'Songs must be under 120 MB.')
                out.write(block)
    finally:
        await upload.close()
    if total == 0:
        raise HTTPException(422, 'The uploaded file is empty.')


def decode(path: Path, min_seconds=5):
    """Decode with libsndfile (WAV/FLAC/OGG/MP3), falling back to ffmpeg for AAC/M4A and others."""
    try:
        audio, sr = sf.read(path, always_2d=True, dtype='float32')
    except Exception:
        if not shutil.which('ffmpeg'):
            raise ValueError('This format needs ffmpeg on the server. Upload WAV, FLAC, OGG or MP3.')
        proc = subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-i', str(path), '-t', str(MAX_SONG_SECONDS+1),
                               '-f', 'f32le', '-ac', '2', '-ar', str(TARGET_SR), '-'], capture_output=True, timeout=300)
        if proc.returncode != 0 or not proc.stdout:
            raise ValueError('The file could not be decoded as audio.')
        audio, sr = np.frombuffer(proc.stdout, dtype=np.float32).reshape(-1, 2).copy(), TARGET_SR
    if audio.shape[1] > 2:
        audio = audio[:, :2]
    if audio.shape[1] == 1:
        audio = np.repeat(audio, 2, axis=1)
    duration = len(audio)/sr
    if duration < min_seconds:
        raise ValueError(f'The recording is shorter than {min_seconds} seconds.')
    if duration > MAX_SONG_SECONDS:
        raise ValueError('Songs up to 10 minutes are supported. Trim the file and try again.')
    if not np.isfinite(audio).all() or np.sqrt(np.mean(audio**2)) < 1e-4:
        raise ValueError('The audio is silent or invalid.')
    if sr != TARGET_SR:
        import librosa
        audio = librosa.resample(audio.T, orig_sr=sr, target_sr=TARGET_SR).T.astype(np.float32)
        sr = TARGET_SR
    return audio, sr


def write_track(folder: Path, name: str, audio, sr):
    """FLAC for analysis, MP3 for fast playback on phones."""
    sf.write(folder/f'{name}.flac', audio, sr, subtype='PCM_16')
    peak = float(np.max(np.abs(audio))) if len(audio) else 0
    safe = audio/peak*.98 if peak > .98 else audio
    sf.write(folder/f'{name}.mp3', safe, sr, format='MP3')


# ---------------------------------------------------------------- pipeline

STEM_LABELS = {'guitar': 'Guitar', 'bass': 'Bass', 'drums': 'Drums', 'vocals': 'Vocals', 'piano': 'Piano / keys',
               'other': 'Other instruments'}
POSITION_LABELS = {'left': 'left', 'centre': 'centre', 'right': 'right'}


def check(song):
    if song.cancelled:
        raise RuntimeError('Session cancelled')


def run_song(song: Song):
    import librosa
    try:
        check(song)
        song.status, song.stage = 'decoding', 'Reading the song'
        audio, sr = decode(song.folder/'source')
        (song.folder/'source').unlink(missing_ok=True)       # keep only what is needed
        tracks = song.folder/'tracks'
        tracks.mkdir()
        write_track(tracks, 'mix', audio, sr)
        check(song)
        song.status, song.stage = 'separating', 'Separating every instrument (htdemucs_6s, six stems)'
        stems, sr_s, provenance = models.run_demucs(audio, sr)
        check(song)
        song.stage = 'Finding which instruments play'
        peak = float(np.max(np.abs(audio)))
        found = sa.presence(stems, sr_s, peak)
        for name, y in stems.items():
            write_track(tracks, name, y, sr_s)
        profile = resolve_profile(song.instrument)
        stem_name = profile['separation_stem']
        stem = stems[stem_name]

        song.stage = f'Looking for more than one {profile["name"].lower()} part'
        split = sa.pan_parts(stem, sr_s) if song.instrument != 'piano' else [('centre', stem, 1.0)]
        parts = []
        for pos, y, share in split:
            pid = stem_name if len(split) == 1 else f'{stem_name}_{pos}'
            if len(split) > 1:
                write_track(tracks, pid, y, sr_s)
            label = STEM_LABELS[stem_name] if len(split) == 1 else f'{STEM_LABELS[stem_name]} ({POSITION_LABELS[pos]})'
            parts.append({'id': pid, 'label': label, 'position': pos, 'share': share, 'audio': y})
        if len(parts) == 2:
            similarity = sa.chroma_similarity(parts[0]['audio'], parts[1]['audio'], sr_s)
            for p in parts:
                p['doubled'] = similarity > .9
        check(song)

        duration = len(audio)/sr
        song.stage = 'Estimating tempo, bars and key'
        def mono22(y):
            return librosa.resample(sa.mono(y), orig_sr=sr_s, target_sr=22050)
        drums_present = any(r['stem'] == 'drums' and r['verdict'] == 'present' for r in found)
        rhythm = mono22(stems['drums']+stems['bass']) if drums_present else mono22(audio)
        harmonic = mono22(sum(stems[k] for k in sa.HARMONIC_STEMS if k in stems))
        grid = sa.beat_grid(rhythm, 22050, mono22(stems['bass']), harmonic)
        cents = sa.estimate_tuning_cents(harmonic, 22050)
        chroma = librosa.feature.chroma_cqt(y=harmonic+mono22(stems['vocals'])*.5, sr=22050, hop_length=512,
                                            tuning=cents/100)
        key = sa.estimate_key(chroma.sum(axis=1))
        chord_chroma = librosa.feature.chroma_cqt(y=harmonic, sr=22050, hop_length=512, tuning=cents/100)
        # Only beats inside the audio; the grid may start with a pickup bar before 0 s.
        beat_times = [b for b in grid['beats'] if 0 <= b < duration]
        frames = librosa.time_to_frames(beat_times, sr=22050, hop_length=512)
        frames = np.clip(frames, 0, chord_chroma.shape[1]-1)
        bounds = list(frames)+[chord_chroma.shape[1]]
        synced = np.stack([np.median(chord_chroma[:, a:max(b, a+1)], axis=1) for a, b in zip(bounds[:-1], bounds[1:])], axis=1)
        labels = sa.chords_per_beat(synced, key)
        chords = sa.chord_segments(labels, beat_times)
        key = sa.resolve_mode(key, chords)
        check(song)

        song.stage = f'Transcribing the {profile["name"].lower()} notes (Basic Pitch)'
        widest = min(min(t) for t in profile['tunings'].values()) if profile['tunings'] else profile['midi_min']
        for p in parts:
            check(song)
            y = sa.mono(p['audio'])
            if abs(cents) >= 20:
                # Re-centre an off-A440 recording so notes round to the right semitone.
                y = librosa.effects.pitch_shift(y, sr=sr_s, n_steps=-cents/100)
            path = song.folder/f'transcribe-{p["id"]}.wav'
            sf.write(path, y, sr_s, subtype='PCM_16')
            song.notes[p['id']] = models.transcribe(path, midi_min=widest, midi_max=profile['midi_max'])
            path.unlink(missing_ok=True)
        # Panning masks leak; find bars where a part only carries another part's bleed and
        # drop those notes so they do not appear twice in tab or count as a second lead.
        edges = sa.bar_edges(grid['bars'], duration)
        if len(parts) > 1:
            levels = {p['position']: sa.bar_levels(p['audio'], sr_s, edges) for p in parts}
            by_pos = {p['position']: song.notes[p['id']] for p in parts}
            bleed = sa.bleed_bars(levels, by_pos, edges)
        else:
            bleed = {p['position']: None for p in parts}
        for p in parts:
            flags = bleed[p['position']]
            if flags:
                song.notes[p['id']] = [n for n in song.notes[p['id']]
                                       if not flags[min(len(flags)-1, max(0, int(np.searchsorted(edges, n['time'], 'right'))-1))]]
            p['roles'] = sa.bar_roles(song.notes[p['id']], grid['bars'], duration, bleed=flags)
            song.notes[p['id']] = sa.drop_overtones(song.notes[p['id']], p['roles'], window=.15)
            p['role'] = sa.summarise_roles(p['roles'])
            p['notes'] = len(song.notes[p['id']])
            del p['audio']
        # A part that is bleed everywhere stays in the mix (it is still part of the guitars'
        # sound) but is labelled 'silent' so the UI does not offer it as something to learn.
        all_notes = [n for v in song.notes.values() for n in v]
        tuning = sa.suggest_tuning(all_notes, cents, profile['tunings'], flats=bool(key and key['fifths'] < 0)) if profile['tunings'] else None

        song.result = {
            'duration': duration,
            'instruments': [dict(r, label=STEM_LABELS.get(r['stem'], r['stem'])) for r in found],
            'selected_stem': stem_name, 'parts': parts, 'tempo': grid, 'key': key, 'chords': chords,
            'tuning': tuning, 'reference_cents': round(cents, 1),
            'provenance': dict(provenance, transcription='Basic Pitch ONNX', onset_threshold=models.ONSET_THRESHOLD,
                               frame_threshold=models.FRAME_THRESHOLD),
            'warnings': [
                'Every result here is an automatic estimate. Check notes and chords by ear and correct them.',
                'Parts panned to the same place and playing at the same time cannot be separated.',
                'Tab positions are suggestions: the same note can be played on several strings.',
            ],
        }
        song.status, song.stage = 'complete', 'Breakdown ready'
    except Exception as exc:
        song.status, song.stage = 'failed', 'Processing stopped; no substitute was used'
        song.error = str(exc)
    finally:
        with LOCK:
            song.active = False
            if song.cancelled:
                shutil.rmtree(song.folder, ignore_errors=True)
                SONGS.pop(song.id, None)


# ---------------------------------------------------------------- routes

@router.post('', status_code=202)
async def create_song(file: UploadFile | None = File(None), url: str | None = Form(None),
                      consent: bool = Form(False), instrument: str = Form('guitar'),
                      x_fretwork_client: str | None = Header(None)):
    client(x_fretwork_client)
    if not consent:
        raise HTTPException(422, 'Explicit upload consent is required.')
    if (file is None) == (not url):
        raise HTTPException(422, 'Provide either a song file or a link, not both.')
    try:
        resolve_profile(instrument)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    caps = models.capabilities()
    if not caps['separation']['configured'] or not caps['transcription']['configured']:
        raise HTTPException(503, 'Instrument separation and transcription models must both be installed; see server/README.md.')
    if url:
        check_public_url(url.strip())
    cleanup()
    with LOCK:
        if len(SONGS) >= 4 or sum(s.active for s in SONGS.values()) >= 2:
            raise HTTPException(429, 'The song worker is busy. Delete an old song or try again shortly.')
        key = uuid4().hex
        folder = ROOT/f'song-{key}'
        folder.mkdir(mode=0o700)
        song = Song(key, folder, instrument, (file.filename if file else '') or 'Uploaded song',
                    stage='Receiving the song')
        SONGS[key] = song
    try:
        if file is not None:
            await save_upload(file, folder/'source')
        else:
            song.name = await fetch_url(url.strip(), folder/'source')
        song.name = Path(song.name).name[:120]
        EXECUTOR.submit(run_song, song)
    except BaseException:
        shutil.rmtree(folder, ignore_errors=True)
        with LOCK:
            SONGS.pop(key, None)
        raise
    return serialize(song)


@router.get('/{key}')
def song_status(key: str):
    return serialize(get_song(key))


@router.get('/{key}/tracks/{track}')
def track_audio(key: str, track: str, format: str = 'mp3'):
    song = get_song(key)
    if format not in ('mp3', 'flac') or not track.replace('_', '').isalnum():
        raise HTTPException(404, 'Unknown track.')
    path = song.folder/'tracks'/f'{track}.{format}'
    if not path.is_file():
        raise HTTPException(404, 'Track not ready.')
    return FileResponse(path, media_type='audio/mpeg' if format == 'mp3' else 'audio/flac',
                        headers={'Cache-Control': 'private, max-age=3600'})


class ScoreRequest(BaseModel):
    part: str = Field(default='all', max_length=40)       # a part id, or 'all'
    role: str = Field(default='any', pattern='^(any|lead|rhythm)$')
    tuning: str = Field(default='standard', max_length=40)
    capo: int = Field(default=0, ge=0, le=12)


@router.post('/{key}/score')
def score(key: str, body: ScoreRequest, x_fretwork_client: str | None = Header(None)):
    client(x_fretwork_client)
    song = get_song(key)
    if song.status != 'complete' or not song.result:
        raise HTTPException(409, 'Wait for the breakdown to finish.')
    try:
        profile = resolve_profile(song.instrument, body.tuning if song.instrument != 'piano' else 'none', body.capo)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    parts = {p['id']: p for p in song.result['parts']}
    chosen = list(parts) if body.part == 'all' else [body.part]
    if any(p not in parts for p in chosen):
        raise HTTPException(404, 'Unknown part.')
    notes = []
    for pid in chosen:
        roles = parts[pid]['roles']
        for n in song.notes.get(pid, []):
            if body.role != 'any':
                bar = next((r for r in roles if r['start'] <= n['time'] < r['end']), None)
                if not bar or bar['role'] != body.role:
                    continue
            notes.append(dict(n, part=pid))
    # Doubled parts play the same notes; keep one copy of near-identical events.
    notes.sort(key=lambda n: (n['time'], n['midi']))
    deduped = []
    for n in notes:
        if deduped and n['midi'] == deduped[-1]['midi'] and abs(n['time']-deduped[-1]['time']) < .05:
            continue
        deduped.append(n)
    strings = profile['open_strings']
    tabbed = sa.fingering(deduped, strings, profile['max_fret']) if strings else [dict(n, string=None, fret=None) for n in deduped]
    unplayable = sum(1 for n in tabbed if strings and n['string'] is None)
    key_info = song.result['key']
    label = 'All parts' if body.part == 'all' else parts[body.part]['label']
    if body.role != 'any':
        label += f' · {body.role} passages'
    clef = 'treble8vb' if song.instrument == 'guitar' else 'bass' if song.instrument == 'bass' else 'treble'
    xml = sa.musicxml(tabbed, song.result['tempo']['beats'], key_info, strings, title=Path(song.name).stem,
                      part_name=label, chords=song.result['chords'], tab=bool(strings), clef=clef)
    return {'part': body.part, 'role': body.role, 'label': label, 'instrument_profile': profile,
            'notes': tabbed, 'unplayable_notes': unplayable, 'musicxml': xml,
            'chords': song.result['chords'], 'key': key_info, 'tempo': {k: song.result['tempo'][k] for k in ('bpm', 'time_signature')}}


MUTED_ROLES = {'any': None, 'lead': ('lead', 'mixed'), 'rhythm': ('rhythm',)}


def target_audio(song: Song, parts: list[str], role: str, sr=22050):
    """Mono sum of the chosen parts, silent outside their lead / rhythm bars when asked."""
    import librosa
    known = {p['id']: p for p in song.result['parts']}
    total = None
    for pid in parts:
        if pid not in known:
            raise HTTPException(404, 'Unknown part.')
        y, rate = sf.read(song.folder/'tracks'/f'{pid}.flac', always_2d=True, dtype='float32')
        y = librosa.resample(y.mean(axis=1), orig_sr=rate, target_sr=sr)
        keep = MUTED_ROLES[role]
        if keep:
            gate = np.zeros_like(y)
            for bar in known[pid]['roles']:
                if bar['role'] in keep:
                    gate[int(bar['start']*sr):int(bar['end']*sr)] = 1
            y = y*gate
        total = y if total is None else total[:len(y)]+y[:len(total)]
    return total


@router.post('/{key}/locate')
async def locate_take(key: str, take: UploadFile = File(...), parts: str = Form(...),
                      role: str = Form('any'), x_fretwork_client: str | None = Header(None)):
    """Where in the song does this take belong? Matches against the part being learned."""
    client(x_fretwork_client)
    song = get_song(key)
    if song.status != 'complete' or not song.result:
        raise HTTPException(409, 'Wait for the breakdown to finish.')
    if role not in MUTED_ROLES:
        raise HTTPException(422, 'Unknown role.')
    path = song.folder/f'locate-{uuid4().hex}'
    try:
        await save_upload(take, path)
        try:
            audio, sr = decode(path, min_seconds=2)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        import librosa
        y = librosa.resample(audio.mean(axis=1), orig_sr=sr, target_sr=22050)
        ids = [p for p in parts.split(',') if p][:6]
        def work():
            reference = target_audio(song, ids, role)
            return sa.locate(reference, y, 22050, song.result['tempo']['bars'])
        try:
            found = await asyncio.to_thread(work)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return dict(found, take_seconds=len(y)/22050)
    finally:
        path.unlink(missing_ok=True)


@router.delete('/{key}', status_code=204)
def delete_song(key: str, x_fretwork_client: str | None = Header(None)):
    client(x_fretwork_client)
    song = get_song(key)
    with LOCK:
        song.cancelled = True
        if not song.active:
            shutil.rmtree(song.folder, ignore_errors=True)
            SONGS.pop(key, None)

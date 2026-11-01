"""Single-user development service. Temporary audio, explicit consent, bounded queue."""
import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
import importlib.metadata
import math
import os
from pathlib import Path
import shutil
import threading
import time
from uuid import uuid4

from fastapi import FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
import numpy as np
import soundfile as sf

from . import models
from .analysis import align, observations, score_informed
from .model_store import install_stream, InvalidCheckpoint
from .instruments import resolve_profile, CATALOGUE
from .devices import policy_for

MAX_BYTES = 40 * 1024 * 1024
from .runtime import ROOT, LOCK, EXECUTOR, TTL_SECONDS
from . import songs
from . import tabs
JOBS = {}


@dataclass
class Job:
    id: str
    folder: Path
    kind: str
    original_offset: float
    duration: float
    profile: dict = field(default_factory=resolve_profile)
    status: str = 'queued'
    stage: str = 'Waiting for audio worker'
    created: float = field(default_factory=time.time)
    device: dict = field(default_factory=dict)
    result: dict | None = None
    error: str | None = None
    cancelled: bool = False
    active: bool = True
    policy: str = 'cpu'
    # Notes from an uploaded tab/score: the exact reference, so it is not transcribed.
    reference_notes: list | None = None


def cleanup():
    with LOCK:
        for key, job in list(JOBS.items()):
            if time.time()-job.created > TTL_SECONDS:
                job.cancelled = True
                if not job.active:
                    shutil.rmtree(job.folder, ignore_errors=True)
                    del JOBS[key]


@asynccontextmanager
async def lifespan(app):
    async def sweep():
        while True:
            await asyncio.sleep(30)
            cleanup()
            songs.cleanup()
    task = asyncio.create_task(sweep())
    yield
    task.cancel()
    with LOCK:
        for job in JOBS.values():
            job.cancelled = True
        for song in songs.SONGS.values():
            song.cancelled = True
    EXECUTOR.shutdown(wait=True, cancel_futures=True)
    shutil.rmtree(ROOT, ignore_errors=True)


app = FastAPI(title='Fretwork analysis engine', lifespan=lifespan)
app.include_router(songs.router)
app.include_router(tabs.router)


def client(x_fretwork_client: str | None):
    # Custom header prevents cross-origin HTML form submissions. No permissive CORS.
    if x_fretwork_client != 'studio':
        raise HTTPException(403, 'Use the studio client header.')


def get_job(key):
    cleanup()
    with LOCK:
        job = JOBS.get(key)
        if not job or job.cancelled:
            raise HTTPException(404, 'Session not found or expired.')
        return job


def serialize(job):
    return {'id': job.id, 'status': job.status, 'stage': job.stage, 'error': job.error,
            'device': job.device, 'result': job.result, 'original_offset': job.original_offset,
            'duration': job.duration, 'instrument_profile': job.profile, 'expires_at': job.created+TTL_SECONDS,
            'guitar_url': f'/api/jobs/{job.id}/guitar' if job.status in ('review', 'analysing', 'complete') else None}


def cancelled(job):
    if job.cancelled:
        raise RuntimeError('Session cancelled')


def run_job(job, phase):
    chained = False
    try:
        cancelled(job)
        if phase == 'separate':
            audio, sr = sf.read(job.folder/'reference.wav', always_2d=True, dtype='float32')
            if job.kind == 'mix':
                job.status, job.stage = 'separating', f"Extracting {job.profile['separation_stem']} with htdemucs_6s"
                guitar, sr, provenance = models.separate_instrument(audio, sr, job.profile['separation_stem'], job.policy)
                job.device = provenance
            else:
                guitar = audio
                job.device = {'model': f"User-supplied isolated {job.profile['name']}", 'device': 'not needed',
                              'quality': 'Human review required; not independently verified.'}
            cancelled(job)
            sf.write(job.folder/'guitar.wav', guitar, sr, subtype='PCM_16')
            if job.reference_notes is not None:
                # The reference is the app's own rendering of a tab: nothing to approve.
                job.status, job.stage = 'queued', 'Comparing your take with the tab'
                chained = True
                EXECUTOR.submit(run_job, job, 'analyse')
                return
            job.status, job.stage = 'review', 'Listen to the instrument reference and approve its quality'
        else:
            job.status, job.stage = 'analysing', 'Aligning harmonic features within the selected passage'
            import librosa
            reference, sr = sf.read(job.folder/'guitar.wav', always_2d=True, dtype='float32')
            take, take_sr = sf.read(job.folder/'take.wav', always_2d=True, dtype='float32')
            take = librosa.resample(take.mean(axis=1), orig_sr=take_sr, target_sr=sr)
            alignment = align(reference.mean(axis=1), take, sr)
            cancelled(job)
            if job.reference_notes is not None:
                reference_notes = job.reference_notes
            else:
                job.stage = f"Transcribing reference {job.profile['name']} with Basic Pitch"
                reference_notes = models.transcribe_profile(job.folder/'guitar.wav', job.profile)
            cancelled(job)
            job.stage = 'Transcribing your take with Basic Pitch'
            if job.reference_notes is not None:
                take_notes, post = models.transcribe_profile(job.folder/'take.wav', job.profile, posteriors=True)
            else:
                take_notes = models.transcribe_profile(job.folder/'take.wav', job.profile)
            cancelled(job)
            versions = {}
            for name in ('librosa', 'demucs', 'basic-pitch', 'torch', 'onnxruntime'):
                try:
                    versions[name] = importlib.metadata.version(name)
                except importlib.metadata.PackageNotFoundError:
                    pass
            job.result = {'alignment': alignment, 'reference_notes': reference_notes, 'take_notes': take_notes,
                          'comparison': score_informed(reference_notes, take_notes, post) if job.reference_notes is not None
                          else observations(reference_notes, take_notes, alignment),
                          'provenance': {'separation': job.device,
                                         'transcription': 'Reference: notes from the uploaded tab/score. Take: Basic Pitch ONNX (CPU).'
                                         if job.reference_notes is not None else 'Basic Pitch ONNX (CPU provider by default)',
                                         'versions': versions, 'instrument_profile': job.profile, 'edited': False},
                          'warnings': [job.profile['status'], 'Basic Pitch estimates can miss or invent notes.']+(
                                       ['Reference notes come from the uploaded tab; only your take is estimated.']
                                       if job.reference_notes is not None else
                                       ['Reference may contain overlapping parts and separation artefacts.',
                                        'Manual song position is assumed; this is not whole-song recognition.'])}
            job.status, job.stage = 'complete', 'Comparison ready — review uncertainty and correct notes if needed'
    except Exception as exc:
        job.status, job.stage = 'failed', 'Processing stopped; no substitute algorithm was used'
        job.error = str(exc)
    finally:
        with LOCK:
            if chained:
                return
            job.active = False
            if job.cancelled:
                shutil.rmtree(job.folder, ignore_errors=True)
                JOBS.pop(job.id, None)


@app.get('/api/health')
def health():
    cleanup()
    return {'service': 'Fretwork Python engine', 'models': models.capabilities(), 'instruments': CATALOGUE,
            'retention_seconds': TTL_SECONDS, 'max_passage_seconds': 60,
            'privacy': 'Selected excerpts uploaded only after consent. Temporary files deleted on deletion, expiry or clean shutdown.'}


async def save_audio(upload, path):
    total = 0
    try:
        with path.open('wb') as out:
            while block := await upload.read(1024*1024):
                total += len(block)
                if total > MAX_BYTES:
                    raise HTTPException(413, 'Each audio excerpt must be under 40 MB.')
                out.write(block)
        try:
            info = sf.info(path)
            if not 1 <= info.duration <= 60.1 or info.channels not in (1, 2) or not 8000 <= info.samplerate <= 96000:
                raise ValueError('Use 1–60 second mono/stereo WAV excerpts at 8–96 kHz.')
            if info.format != 'WAV':
                raise ValueError('Upload PCM WAV audio; the browser converts supported input files.')
            audio, sr = sf.read(path, always_2d=True, dtype='float32')
            if not np.isfinite(audio).all() or np.max(np.abs(audio)) > 1.1:
                raise ValueError('Audio has invalid sample values.')
            if np.sqrt(np.mean(audio**2)) < .0001:
                raise ValueError('Audio is silent or too quiet.')
            return info.duration
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(422, str(exc)) from exc
    finally:
        await upload.close()


@app.post('/api/models/separation')
async def install_separation_model(checkpoint: UploadFile = File(...), x_fretwork_client: str | None = Header(None)):
    client(x_fretwork_client)
    if os.getenv('FRETWORK_ALLOW_MODEL_INSTALL') != '1':
        await checkpoint.close()
        raise HTTPException(403, 'Model installation is disabled. Use the operator CLI or explicitly enable the development installer.')
    try:
        # Accept only the exact pinned checkpoint. Never load arbitrary uploaded
        # pickles; the full size and SHA-256 are checked before publishing it.
        installed = await asyncio.to_thread(install_stream, checkpoint.file)
        return {'installed': installed, 'models': models.capabilities()}
    except InvalidCheckpoint as exc:
        raise HTTPException(422, str(exc)) from exc
    finally:
        await checkpoint.close()


@app.post('/api/jobs', status_code=202)
async def create_job(reference: UploadFile = File(...), take: UploadFile = File(...),
                     consent: bool = Form(False), kind: str = Form(...),
                     original_offset: float = Form(0), instrument: str = Form('guitar'), tuning: str = Form('standard'),
                     capo: int = Form(0), notation: str | None = Form(None), processing: str = Form('cpu'),
                     reference_notes: str | None = Form(None), x_fretwork_client: str | None = Header(None)):
    client(x_fretwork_client)
    if not consent:
        raise HTTPException(422, 'Explicit upload consent is required.')
    try:
        policy = policy_for(processing)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    tab_notes = parse_reference_notes(reference_notes) if reference_notes else None
    if tab_notes is not None and kind != 'isolated':
        raise HTTPException(422, 'Tab reference notes need the rendered tab as an isolated reference.')
    if kind not in ('mix', 'isolated') or not math.isfinite(original_offset) or original_offset < 0:
        raise HTTPException(422, 'Invalid reference type or original timestamp.')
    try:
        profile = resolve_profile(instrument, tuning, capo, notation)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    caps = models.capabilities()
    if kind == 'mix' and not caps['separation']['configured']:
        raise HTTPException(503, 'Six-source instrument separation model unavailable. Provision htdemucs_6s weights; no job audio was saved.')
    if not caps['transcription']['configured']:
        raise HTTPException(503, 'Basic Pitch transcription model unavailable. Provision nmp.onnx; no audio was saved.')
    cleanup()
    with LOCK:
        if len(JOBS) >= 8 or sum(j.active for j in JOBS.values()) >= 3:
            raise HTTPException(429, 'Worker queue is full. Delete old sessions or try later.')
        key = uuid4().hex
        folder = ROOT/key
        folder.mkdir(mode=0o700)
        # Reserve capacity before streaming uploads.
        job = Job(key, folder, kind, original_offset, 0, profile=profile, stage='Receiving consented excerpts',
                  policy=policy, reference_notes=tab_notes)
        JOBS[key] = job
    try:
        rd = await save_audio(reference, folder/'reference.wav')
        td = await save_audio(take, folder/'take.wav')
        if abs(rd-td) > .1:
            raise HTTPException(422, 'Reference and take excerpts must have the same duration.')
        job.duration = min(rd, td)
        if tab_notes is not None:
            if any(n['time'] > job.duration+.1 for n in tab_notes):
                raise HTTPException(422, 'Tab notes run past the end of the rendered reference.')
            if any(not profile['midi_min'] <= n['midi'] <= profile['midi_max'] for n in tab_notes):
                raise HTTPException(422, 'The tab has notes outside the selected instrument and tuning.')
        EXECUTOR.submit(run_job, job, 'separate')
    except BaseException:
        shutil.rmtree(folder, ignore_errors=True)
        with LOCK:
            JOBS.pop(key, None)
        raise
    return serialize(job)


@app.get('/api/jobs/{key}')
def status(key: str):
    return serialize(get_job(key))


@app.get('/api/jobs/{key}/stem')
@app.get('/api/jobs/{key}/guitar')
def guitar(key: str):
    job = get_job(key)
    if not (job.folder/'guitar.wav').is_file():
        raise HTTPException(409, 'Guitar reference is not ready.')
    return FileResponse(job.folder/'guitar.wav', media_type='audio/wav', headers={'Cache-Control': 'no-store'})


class Approval(BaseModel):
    approved: bool


@app.post('/api/jobs/{key}/approve', status_code=202)
def approve(key: str, body: Approval, x_fretwork_client: str | None = Header(None)):
    client(x_fretwork_client)
    job = get_job(key)
    with LOCK:
        if job.status != 'review' or job.active:
            raise HTTPException(409, 'Wait for guitar review stage.')
        if not body.approved:
            raise HTTPException(422, 'Approve a usable reference or delete this session and supply a cleaner stem.')
        if sum(j.active for j in JOBS.values()) >= 3:
            raise HTTPException(429, 'Worker queue is full. Try again shortly.')
        job.active = True
        job.status, job.stage = 'queued', 'Waiting for alignment and transcription worker'
        EXECUTOR.submit(run_job, job, 'analyse')
    return serialize(job)


def parse_reference_notes(raw: str):
    """JSON list of {time, duration, midi[, string, fret]} from an uploaded tab, validated."""
    import json
    try:
        data = json.loads(raw)
        if not isinstance(data, list) or len(data) > 5000:
            raise ValueError
        notes = [NoteEdit(id=i, **{k: n[k] for k in ('time', 'duration', 'midi', 'string', 'fret') if k in n}).model_dump()
                 for i, n in enumerate(data)]
    except Exception as exc:
        raise HTTPException(422, 'Reference notes must be a list of {time, duration, midi} (max 5000).') from exc
    return sorted(notes, key=lambda n: (n['time'], n['midi']))


class NoteEdit(BaseModel):
    id: int = Field(ge=0)
    time: float = Field(ge=0, le=60, allow_inf_nan=False)
    duration: float = Field(gt=0, le=60, allow_inf_nan=False)
    midi: int = Field(ge=21, le=108)
    amplitude: float = Field(default=.5, ge=0, le=1, allow_inf_nan=False)
    string: int | None = Field(default=None, ge=1, le=6)
    fret: int | None = Field(default=None, ge=0, le=24)


class Edits(BaseModel):
    notes: list[NoteEdit] = Field(max_length=1000)


@app.put('/api/jobs/{key}/notes')
def edit_notes(key: str, body: Edits, x_fretwork_client: str | None = Header(None)):
    client(x_fretwork_client)
    job = get_job(key)
    with LOCK:
        if job.status != 'complete' or job.result is None:
            raise HTTPException(409, 'Wait for completed transcription.')
        if any(n.time+n.duration > job.duration+.1 for n in body.notes) or len({n.id for n in body.notes}) != len(body.notes):
            raise HTTPException(422, 'Notes must fit within the passage and have unique IDs.')
        for n in body.notes:
            if not job.profile['midi_min'] <= n.midi <= job.profile['midi_max']:
                raise HTTPException(422, 'Note is outside the selected instrument range.')
            if (n.string is None) != (n.fret is None):
                raise HTTPException(422, 'Supply both string and fret or neither.')
            if n.string is not None:
                strings = job.profile['open_strings']
                if n.string > len(strings) or n.fret > job.profile['max_fret'] or strings[n.string-1]+n.fret != n.midi:
                    raise HTTPException(422, 'Tab must agree with this instrument, tuning and capo.')
        notes = [n.model_dump() for n in body.notes]
        job.result['take_notes'] = sorted(notes, key=lambda n: (n['time'], n['midi']))
        job.result['comparison'] = observations(job.result['reference_notes'], notes, job.result['alignment'])
        job.result['provenance']['edited'] = True
    return serialize(job)


@app.delete('/api/jobs/{key}', status_code=204)
def delete_job(key: str, x_fretwork_client: str | None = Header(None)):
    client(x_fretwork_client)
    job = get_job(key)
    with LOCK:
        job.cancelled = True
        if not job.active:
            shutil.rmtree(job.folder, ignore_errors=True)
            JOBS.pop(key, None)
    # Running inference cannot be interrupted safely in this single-worker version.
    # Session is immediately inaccessible; files removed when current stage exits.


@app.post('/api/shutdown', status_code=202)
def shutdown(request: Request, x_fretwork_client: str | None = Header(None)):
    """Let the Windows uninstaller/updater stop a running app. Only enabled by the local
    launcher (FRETWORK_LOCAL_APP=1) and only for requests from this computer."""
    client(x_fretwork_client)
    if os.getenv('FRETWORK_LOCAL_APP') != '1' or (request.client and request.client.host not in ('127.0.0.1', '::1')):
        raise HTTPException(403, 'Shutdown is only available to the local launcher.')
    import signal
    threading.Timer(.2, lambda: signal.raise_signal(signal.SIGINT)).start()
    return {'stopping': True}


# ---------------------------------------------------------------- the studio itself
# When the studio has been built (npm run build -> dist/), serve it from here too, so one
# program on one address runs everything (used by the Windows launcher). Registered last so
# every /api route above takes precedence. In development, Vite serves the studio instead.
UI_DIR = Path(os.getenv('FRETWORK_UI_DIR', Path(__file__).resolve().parents[1]/'dist'))
# Python takes file types from the Windows registry, where other software often registers .js
# as text/plain; browsers then refuse to run the studio ("Expected a JavaScript module").
# Set the web types explicitly so the studio loads on every machine.
WEB_TYPES = {'.js': 'text/javascript', '.mjs': 'text/javascript', '.css': 'text/css', '.html': 'text/html',
             '.json': 'application/json', '.svg': 'image/svg+xml', '.wasm': 'application/wasm',
             '.woff': 'font/woff', '.woff2': 'font/woff2', '.ttf': 'font/ttf', '.otf': 'font/otf',
             '.sf2': 'application/octet-stream', '.png': 'image/png', '.ico': 'image/x-icon'}


def fix_web_types():
    import mimetypes
    mimetypes.init()
    for ext, kind in WEB_TYPES.items():
        mimetypes.add_type(kind, ext)


if (UI_DIR/'index.html').is_file():
    from fastapi.staticfiles import StaticFiles
    fix_web_types()
    app.mount('/', StaticFiles(directory=UI_DIR, html=True), name='studio')

"""Single-user development service. Temporary audio, explicit consent, bounded queue."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
import importlib.metadata
import math
import os
from pathlib import Path
import shutil
import tempfile
import threading
import time
from uuid import uuid4

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
import numpy as np
import soundfile as sf

from . import models
from .analysis import align, observations
from .model_store import install_stream, InvalidCheckpoint

MAX_BYTES = 40 * 1024 * 1024
TTL_SECONDS = 3600
ROOT = Path(tempfile.mkdtemp(prefix='fretwork-'))
LOCK = threading.RLock()
EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix='audio')
JOBS = {}


@dataclass
class Job:
    id: str
    folder: Path
    kind: str
    original_offset: float
    duration: float
    status: str = 'queued'
    stage: str = 'Waiting for audio worker'
    created: float = field(default_factory=time.time)
    device: dict = field(default_factory=dict)
    result: dict | None = None
    error: str | None = None
    cancelled: bool = False
    active: bool = True


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
    task = asyncio.create_task(sweep())
    yield
    task.cancel()
    with LOCK:
        for job in JOBS.values():
            job.cancelled = True
    EXECUTOR.shutdown(wait=True, cancel_futures=True)
    shutil.rmtree(ROOT, ignore_errors=True)


app = FastAPI(title='Fretwork analysis engine', lifespan=lifespan)


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
            'duration': job.duration, 'expires_at': job.created+TTL_SECONDS,
            'guitar_url': f'/api/jobs/{job.id}/guitar' if job.status in ('review', 'analysing', 'complete') else None}


def cancelled(job):
    if job.cancelled:
        raise RuntimeError('Session cancelled')


def run_job(job, phase):
    try:
        cancelled(job)
        if phase == 'separate':
            audio, sr = sf.read(job.folder/'reference.wav', always_2d=True, dtype='float32')
            if job.kind == 'mix':
                job.status, job.stage = 'separating', 'Extracting guitar with htdemucs_6s'
                guitar, sr, provenance = models.separate_guitar(audio, sr)
                job.device = provenance
            else:
                guitar = audio
                job.device = {'model': 'User-supplied isolated guitar', 'device': 'not needed',
                              'quality': 'Human review required; not independently verified.'}
            cancelled(job)
            sf.write(job.folder/'guitar.wav', guitar, sr, subtype='PCM_16')
            job.status, job.stage = 'review', 'Listen to the guitar reference and approve its quality'
        else:
            job.status, job.stage = 'analysing', 'Aligning harmonic features within the selected passage'
            import librosa
            reference, sr = sf.read(job.folder/'guitar.wav', always_2d=True, dtype='float32')
            take, take_sr = sf.read(job.folder/'take.wav', always_2d=True, dtype='float32')
            take = librosa.resample(take.mean(axis=1), orig_sr=take_sr, target_sr=sr)
            alignment = align(reference.mean(axis=1), take, sr)
            cancelled(job)
            job.stage = 'Transcribing reference guitar with Basic Pitch'
            reference_notes = models.transcribe(job.folder/'guitar.wav')
            cancelled(job)
            job.stage = 'Transcribing your take with Basic Pitch'
            take_notes = models.transcribe(job.folder/'take.wav')
            cancelled(job)
            versions = {}
            for name in ('librosa', 'demucs', 'basic-pitch', 'torch', 'onnxruntime'):
                try:
                    versions[name] = importlib.metadata.version(name)
                except importlib.metadata.PackageNotFoundError:
                    pass
            job.result = {'alignment': alignment, 'reference_notes': reference_notes, 'take_notes': take_notes,
                          'comparison': observations(reference_notes, take_notes, alignment),
                          'provenance': {'separation': job.device, 'transcription': 'Basic Pitch ONNX (CPU provider by default)',
                                         'versions': versions, 'edited': False},
                          'warnings': ['Basic Pitch estimates can miss or invent chord notes.',
                                       'Reference may contain multiple guitars and separation artefacts.',
                                       'Manual song position is assumed; this is not whole-song recognition.']}
            job.status, job.stage = 'complete', 'Comparison ready — review uncertainty and correct notes if needed'
    except Exception as exc:
        job.status, job.stage = 'failed', 'Processing stopped; no substitute algorithm was used'
        job.error = str(exc)
    finally:
        with LOCK:
            job.active = False
            if job.cancelled:
                shutil.rmtree(job.folder, ignore_errors=True)
                JOBS.pop(job.id, None)


@app.get('/api/health')
def health():
    cleanup()
    return {'service': 'Fretwork Python engine', 'models': models.capabilities(),
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
                     original_offset: float = Form(0), x_fretwork_client: str | None = Header(None)):
    client(x_fretwork_client)
    if not consent:
        raise HTTPException(422, 'Explicit upload consent is required.')
    if kind not in ('mix', 'isolated') or not math.isfinite(original_offset) or original_offset < 0:
        raise HTTPException(422, 'Invalid reference type or original timestamp.')
    caps = models.capabilities()
    if kind == 'mix' and not caps['separation']['configured']:
        raise HTTPException(503, 'Guitar separation model unavailable. Provision htdemucs_6s weights; no audio was saved.')
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
        job = Job(key, folder, kind, original_offset, 0, stage='Receiving consented excerpts')
        JOBS[key] = job
    try:
        rd = await save_audio(reference, folder/'reference.wav')
        td = await save_audio(take, folder/'take.wav')
        if abs(rd-td) > .1:
            raise HTTPException(422, 'Reference and take excerpts must have the same duration.')
        job.duration = min(rd, td)
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


class NoteEdit(BaseModel):
    id: int = Field(ge=0)
    time: float = Field(ge=0, le=60, allow_inf_nan=False)
    duration: float = Field(gt=0, le=60, allow_inf_nan=False)
    midi: int = Field(ge=40, le=88)
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
            if (n.string is None) != (n.fret is None):
                raise HTTPException(422, 'Supply both string and fret or neither.')
            if n.string is not None and [64, 59, 55, 50, 45, 40][n.string-1]+n.fret != n.midi:
                raise HTTPException(422, 'Tab position must agree with the MIDI note in standard tuning.')
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

# Fretwork specialist engine (development milestone)

**Latest installation status:** see [INSTALLATION_STATUS.md](INSTALLATION_STATUS.md). PyTorch/torchaudio/Demucs are installed in the active sandbox, but the real checkpoint download is blocked by outbound network restrictions. The operator installer supports a checksum-verified browser upload or CLI import.


Python 3.11 recommended. UI requests `/api` on its own origin; Vite proxies them to the Python server. No browser code calls localhost. No third-party analytics or audio-training service is used.

## Install and run

From `guitar-lab/`:

```sh
python3 -m venv .venv
.venv/bin/pip install -r server/requirements-transcription.txt
.venv/bin/pip install --no-deps basic-pitch==0.4.0
.venv/bin/python -m uvicorn server.app:app --host 0.0.0.0 --port 8000
# In a second terminal:
npm ci
npm run dev -- --port 5173
```

The explicit ONNX installation avoids the TensorFlow dependency pulled by Basic Pitch 0.4.0's Linux/Python 3.11 package metadata. The bundled `basic_pitch/saved_models/icassp_2022/nmp.onnx` is used; override with `FRETWORK_BASIC_PITCH_MODEL=/absolute/path/nmp.onnx` if needed. Optional-runtime warnings from Basic Pitch about TensorFlow/CoreML/TFLite are expected: ONNX works without them. No inference-time model downloads.

With these dependencies **isolated-reference sessions work**. Full-band sessions remain blocked until the guitar-capable separation model is provisioned below. `/api/health` reports configuration, not a guarantee that a model loads on every machine.

### Enable genuine guitar separation

1. Install matching **PyTorch and torchaudio** builds for your machine from their official distribution. Choose a CPU build for CPU machines or a CUDA-compatible build for NVIDIA. Do not mix torch and torchaudio versions. On modern PyTorch, older Demucs checkpoint loading may require compatibility review; use trusted official weights only. Demucs 4.0.1 was designed for older PyTorch, so validate your exact environment.
2. Install `demucs==4.0.1` into the same environment.
3. Run `.venv/bin/python -m server.model_store` to download and verify the pinned checkpoint, or `.venv/bin/python -m server.model_store --checkpoint /path/to/5c90dfd2-34c22ccb.th` for offline installation. The default cache is `.cache/models/demucs`; `FRETWORK_DEMUCS_REPO` overrides it. To use the development browser installer instead, start the API with `FRETWORK_ALLOW_MODEL_INSTALL=1` and use the studio's one-time model setup panel. This is disabled by default; production needs operator authentication and proxy upload-size limits. Both paths accept only the pinned 54,996,327-byte SHA-256-verified checkpoint and write a fixed model definition.

Alternatively, obtain the official Demucs `htdemucs_6s` checkpoint and bag definition. This is the six-source model with a **dedicated guitar stem**, not the default four-source `htdemucs` model.
4. Place **both** files in a local model directory:
   - `htdemucs_6s.yaml` containing `models: ['5c90dfd2']`
   - `5c90dfd2-34c22ccb.th` (official six-source checkpoint)
5. If using a non-default model directory, start the server with `FRETWORK_DEMUCS_REPO=/absolute/path/to/model-directory`. Otherwise the default cache is discovered automatically.

The official Demucs package's `demucs/remote/files.txt` identifies the checkpoint location under the publisher's `hybrid_transformer` directory; `demucs/remote/htdemucs_6s.yaml` supplies the bag definition. Review publisher terms and obtain weights through an approved provisioning process. Never load arbitrary uploaded pickle/checkpoint files. The server cannot select or download models from user requests.

**Sandbox limitation:** this workspace permits only selected network hosts. Both the official checkpoint host and the GitHub release-asset redirect are outside that list. The runtime is installed, but the checkpoint has not been downloaded or inference-tested here. Git LFS pointers are explicitly rejected. The one-time browser upload or CLI import can complete installation without outbound server access. No filter, `other` stem, mock or synthetic output is substituted for guitar separation.

### GPU/CPU policy

- `FRETWORK_DEVICE=auto` (default): CUDA, supported Apple MPS, otherwise CPU for Demucs.
- `cpu`: explicitly use CPU.
- `cuda` / `mps`: require the chosen backend; no silent fallback.
- Auto retries on CPU only for known memory/unsupported-operation RuntimeErrors, with the **same model, float32, overlap and shift settings**. Other errors fail visibly. Real GPU/MPS inference remains untested in this sandbox; unit tests cover routing and fallback semantics.
- Basic Pitch currently uses its ONNX **CPU provider**, including on GPU-equipped servers. It retains full functionality, but this stage is not GPU-accelerated in v0.2. This is disclosed in provenance. Adding an ONNX GPU provider is a separate benchmarked optimization.

## Instrument profiles

See [INSTRUMENT_PROFILES.md](../INSTRUMENT_PROFILES.md). Multipart jobs now accept `instrument`, `tuning`, `capo` and `notation` (standard guitar by default). Both languages read `shared/instruments.json`; jobs snapshot and validate the resolved profile, use its dedicated stem and transcription bounds, and validate edits against its range/tuning/capo. Bass and piano are experimental; no real-world accuracy claim or piano pedal grading is made. The existing `/guitar` endpoint is retained alongside a generic `/stem` alias.

## Workflow / API

1. UI uses already-decoded audio to generate equal-length, 44.1 kHz PCM WAV excerpts. Only the selected original timestamp and 1–60 seconds of reference/take are sent, not the entire song. Beginning of the take corresponds to the manually selected reference timestamp. Permission checkbox is never preselected.
2. `POST /api/jobs` multipart: `reference`, `take`, `consent=true`, `kind=mix|isolated`, `original_offset`. Custom `X-Fretwork-Client: studio` header required for mutations. No permissive CORS.
3. Poll `GET /api/jobs/{id}` for queue/separation state.
4. `GET /api/jobs/{id}/guitar` serves the guitar excerpt for review. **No transcription/comparison starts before explicit approval.** For an isolated reference this is the provided guitar, labelled accordingly.
5. `POST /api/jobs/{id}/approve` JSON `{ "approved": true }` starts harmonic/chroma DTW and real Basic Pitch transcription of both passages.
6. Results include alignment map, estimated reference/take note events, one-to-one note-pair observations, raw onset/duration differences and model provenance. MIDI pitches are restricted to the resolved instrument profile (standard guitar E2–E6; bass E1–G4; piano A0–C8). DTW is constrained within the manually chosen passage, not a whole-song search.
7. `PUT /api/jobs/{id}/notes` accepts edited take events and recomputes observations. It does not rerun the alignment or change reference transcription. String/fret edits must agree with the pitch in standard tuning. UI labels unsaved changes. Notes/tab can be added, removed and corrected.
8. `DELETE /api/jobs/{id}` makes the session immediately inaccessible. If inference is running, physical deletion occurs when that stage exits; it cannot be force-interrupted safely in this single-process worker version.

### Honest interpretation

DTW cost confidence labels are heuristic/uncalibrated, not probabilities. Matching repeated chords and silence can fail. Raw onset differences include latency and tempo differences; warped residuals are separate fields and should not be used to erase timing mistakes. Unmatched notes are **candidates**, not confirmed mistakes. Duration differences can reflect articulation, separation artefacts or transcription errors. No claim is made about buzz, finger pressure, exact played strings or physical cause. Human review of the stem is not independent proof of its accuracy.

Tab positions are suggestions in standard tuning. Alternate tunings, capo, staff engraving, chord-arrangement segmentation, automatic song-position search, pitch-preserving playback, model calibration, multi-guitar part selection and production-scale serving remain future work. Playback in the existing local preview is not DTW time-warped.

## Limits, privacy and deployment

This is a **single-user development service**, not a production public upload service. IDs are unguessable session capabilities; do not share URLs. Add authentication/ownership checks, TLS, reverse-proxy request-size limits, rate limiting, durable isolated workers, monitoring and model licence/security review before multi-user/public deployment. There is no user account system yet.

- 40 MB per file, 1–60 seconds, mono/stereo WAV, 8–96 kHz; finite non-silent audio required.
- Bounded process-local queue: one worker, at most three active/queued jobs and eight sessions.
- Raw uploads and derived stems live in a private temporary directory outside the repository. No uploaded filenames are used as paths. No audio content is logged or sent elsewhere.
- Files and in-memory results expire one hour after session creation (cleanup checks every 30 seconds). Active work is marked cancelled and deleted after its current stage returns. Clean shutdown also removes the temp directory. Hard process/host crashes can leave temporary files; production needs external TTL cleanup/encrypted storage.
- UI requests deletion on changing input/settings or unmounting; interrupted browser connections cannot guarantee delivery. Consent explains the expiry fallback.
- Models/large artifacts, virtual environments and temporary data must remain out of Git.

## Tests

```sh
.venv/bin/pip install -r server/requirements-test.txt
.venv/bin/python -m pytest server/tests -q
npm test
npm run build
```

API orchestration tests mock separation/transcription explicitly; they do **not** validate actual model quality. Alignment tests run real librosa. Optional integration tests run the actual bundled ONNX transcription model. Full-band real-model and physical-GPU smoke tests require provisioned hardware/weights and are not claimed as passing here.

### Browser end-to-end smoke test

Start both services above, then use an installed Chromium executable:

```sh
BROWSER_EXECUTABLE_PATH=/absolute/path/to/chromium npm run test:e2e
```

This test uses the real ONNX model on the synthetic isolated-reference demo, approves the stem, edits a note, saves/recomputes, checks phone-width page overflow and deletes the session. It does not exercise microphone permission, actual mobile hardware, real-song separation or musical accuracy. `STUDIO_URL` can override the default local studio address. Browser binaries are not committed or downloaded automatically.

Validation in this sandbox: 14 Python tests, 4 TypeScript tests, a production build, a real-model HTTP/proxy smoke test, and the Chromium isolated-reference end-to-end flow passed. Real full-band separation and physical GPU/MPS inference remain unvalidated.

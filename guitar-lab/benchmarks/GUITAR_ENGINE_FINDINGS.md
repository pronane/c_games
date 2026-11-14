# Consolidated guitar-engine findings and next steps

Consolidated: 31 October 2026  
Evaluated source: `f2817d7`  
Review branch: `arena/23399fc5-c-games`

## Follow-up evidence

[Fresh rerun and opt-in experiments](evidence/README.md) now provide new versioned
results and test logs. The historical artifact limitations below still apply to
the older runs, not to the new evidence. No merge has been performed.

## Executive conclusion

Keep Riley as the primary guitar-transcription candidate. It materially outperformed Basic Pitch on the three bundled real recordings, but better note recognition does not yet make the app a trustworthy judge of arbitrary learner performances against full-band songs.

The next engineering work should address **quiet-input/reverb-policy confusion** and **uncertain duration feedback**, then validate those changes on held-out real guitar recordings before changing defaults. Do not globally lower thresholds or claim support for every effect chain.

This is a consolidation of measurements already reported in this conversation, **not a new benchmark execution**. At consolidation time the checkout had returned to the older base and the earlier uncommitted audit files/raw JSON were absent. The source was fast-forwarded to `f2817d7` on the same branch. The tables below preserve previously reported observations; missing per-clip artifacts are not recreated or represented as newly measured raw results. Re-executing the evaluations and committing their small result artifacts is a prerequisite for a release decision.

## 1. Evidence we have

### Full public regression, paired backends

Three bundled GuitarSet recordings, one player; exact MIDI pitch, ±50 ms onset tolerance, offsets ignored. Near-duplicate unisons are collapsed by the existing harness.

| Recording | Basic Pitch note F1 | Riley note F1 |
|---|---:|---:|
| Rock solo | .8731 | .9453 |
| Funk solo | .7611 | .8421 |
| Jazz comping | .8101 | .9379 |
| **Macro average** | **.8148** | **.9084** |

Riley's absolute gain was .0936 F1. This is not a percentage of correctly graded playing, and these are reused regression clips, not an independent population study.

Rendered cases: Basic Pitch .9412 on the clean scale and 1.0 on the distorted chug/clear/reverb phrases; Riley 1.0 on all four. These synthetic successes cannot substitute for real amp recordings.

Observed Riley runtime on the full real recordings was 42.65–49.69 seconds per minute of audio, versus 1.11–7.63 for Basic Pitch. Another evaluation process was running, and initialisation affects first-call timing; these are workload observations, not isolated performance benchmarks.

### Corruption comparison

Three source recordings, first eight seconds each. Seven waveform conditions, two backends: 42 inference trials, **only three independent performances**.

| Condition | Basic Pitch F1 | Riley F1 | BP reference notes labelled correct | Riley reference notes labelled correct |
|---|---:|---:|---:|---:|
| Original | .8352 | .8967 | 66.9% | 81.6% |
| −24 dB input | .8659 | .8398 | 70.2% | 62.8% |
| Noise, 20 dB SNR | .8048 | .8733 | 69.2% | 67.0% |
| Noise, 5 dB SNR | .7385 | .8749 | 57.4% | 59.8% |
| Hard clipping | .6840 | .8375 | 52.0% | 65.7% |
| Simple comb reverb | .8387 | .9030 | 61.5% | 80.3% |
| Stereo antiphase | .8352 | .8967 | 66.9% | 81.6% |

All values are per-clip macro averages. The feedback control compares the transcribed audio to its own annotations as a correct performance. It is not human-adjudicated learner feedback: annotation mismatch, window boundaries and model/comparison errors all contribute to apparent false alarms.

On original windows (98 reference notes), Riley produced 81 correct, 6 missing, 2 wrong pitch and 9 wrong duration, plus 9 extras. At 5 dB SNR it produced 34 wrong-duration findings. Strong onset/pitch F1 therefore does not validate sustain feedback.

### Exploratory Riley decoder sweep

Three eight-second excerpts × four waveform conditions × eight decoders = 96 decoded outputs from 12 neural inputs. This exploratory sweep is not held-out tuning validation. Its room response is synthetic, not a measured room or amp.

| Condition | Adaptive F1 | Fixed onset .4 | Fixed onset .5 | Fixed onset .65 | Adaptive correct-feedback fraction |
|---|---:|---:|---:|---:|---:|
| Original | .897 | .885 | .897 | .879 | 81.6% |
| −24 dB | .840 | .912 | .901 | .811 | 62.8% |
| Hard clipping | .830 | .846 | .846 | .810 | 65.1% |
| Synthetic room, RT60 2 s | .862 | .851 | .862 | .851 | 36.8% |

The quiet dry funk clip was classified as heavy reverb by the note-count heuristic (loose/strict ratio 1.58). The clipped jazz clip was also classified heavy (1.74). All three synthetic-room cases were classified light. Thus the heuristic is confounded by factors other than reverb.

Mean of the per-clip median offset errors for matched notes rose from approximately 16 ms on originals to 132 ms with the room response. This excludes unmatched notes. Changing the tested offset threshold did not resolve the room feedback failure.

Hard clipping in this sweep was applied after resampling to 16 kHz, unlike the earlier waveform audit. Those rows are not identical-input reruns.

### Alignment-only controls

1,000 seeded monophonic note-list controls: 200 each for identical, slower/offset, wrong pitch, missing note and late note. These do not test audio recognition.

All but three trials met their intended location/correctness criterion. The three failures produced missing-note findings at the wrong target time; repeated-pitch ambiguity needs explicit regression cases.

## 2. Running-app and test observations

Previously verified in this session (not rerun during this consolidation):

- Frontend build succeeded; 52 frontend tests passed.
- Fresh Chromium session selected “Riley guitar model (default)” in both controls; no page JavaScript errors.
- Actual guitar WAV posted through the running Vite proxy to `/api/compare`: HTTP 200 and Riley transcription provenance. No supplied-note substitute was used.
- No full-band separation was configured in this sandbox; no usable GPU or physical USB-device validation.
- Earlier stable-environment Python suite: 190 passed, 1 failed, 5 skipped. The playback lock failure was exact floating-point equality with tiny differences (acoustic max absolute difference 4.40e−14; distorted 4.16e−12), not demonstrated audible damage.
- Earlier numba 0.68.1/librosa test execution crashed; numba 0.61.2 allowed completion. This is a local dependency-compatibility observation, not proof of a universal upstream defect.
- Last tuning turn: four targeted Python tests passed, 17 deselected; the full suite was not rerun then.

Riley CPU evaluation used torch 2.2.2, torchlibrosa 0.1.0, NumPy 1.26.4, numba 0.61.2, librosa 0.11.0; paired Basic Pitch used 0.4.0 ONNX with ONNX Runtime 1.31.1. Treat this as historical evaluation provenance, **not a recommended patched production dependency lock**.

Uploaded model: eight renamed split 7z volumes, successfully reconstructed. Extracted original checkpoint SHA256: `50d93dba89bdd3401849bc735614478e83d9f46d21fa3f71d8aca5acc0a52028`. Restricted loading plus strict tensor-state matching succeeded. This verifies structure/integrity, not independent publisher authenticity. Model weights must remain outside Git.

## 3. What the current code actually does

- `server/transcribers.py::default_backend`: Riley when torch/torchlibrosa are installed, Basic Pitch otherwise. A remembered browser choice or explicit job selection can override it. Runtime detection is not proof that weights load.
- `server/riley/__init__.py::decode`: 20-second-window dry/wet policy; loose onset .3 versus strict .65 note-count ratio >1.5, with at least eight loose notes, selects .65; otherwise .5.
- `server/models.py`: clean/crunch/distorted onset/frame threshold presets apply to **Basic Pitch**, not Riley. Optional-backend dispatch happens before those thresholds are used.
- Stereo L/R inference and merge are available to Riley. This preserves antiphase material but does not separate overlapping centre-panned guitarists.
- `server/songs.py`: effect estimates are informational; Basic Pitch candidate promotion is not automatically mixed into Riley. Existing ghost/refinement tools should be reused and evaluated, not assumed accurate on all real effects.
- Some health/model descriptions and song threshold provenance still describe Basic Pitch as the default or show Basic Pitch settings for Riley. Correct these before presenting backend-specific tuning controls. Earlier wording fixes did not survive the checkout restoration and are not claimed as shipped here.

## 4. Prioritised engineering backlog

### P0-A: restore repeatable, durable evidence

**Implement:** restore the corruption/sweep runners as versioned tools; save small per-clip JSON artifacts, seed, exact dependencies, checkpoint hashes and source commit. Require missing-coverage reporting and fail release evaluation when mandatory datasets are absent. Keep weights/audio local and gitignored.

**Acceptance:** fresh paired baseline matches the preserved observations within declared tolerances or discrepancies are explained; backend errors cannot be mistaken for a successful run. The existing CLI catches errors and can exit zero, so inspect `backends.*.error` and require nonempty scored rows.

### P0-B: fix quiet-input/reverb-policy confounding

**Implement:** independent level, noise-floor, clipping and tail/onset diagnostics; evaluate guarded gain normalisation; decode candidate policies from a single posterior pass. Replace the count-ratio-only decision only after validation. Offer an explicit dry/wet override with truthful provenance.

**Acceptance:** preregister quiet/noisy dry, quiet wet and clipped-polyphonic holdouts; improve quiet recall without unacceptable ghost/onset precision loss on wet material. Publish per-condition precision/recall, not just average F1. Select policies from audio evidence, never truth labels at inference.

### P0-C: make duration feedback uncertainty-aware

**Implement:** separate direct-note sustain evidence from reverberant tails, carry uncertainty through comparison, and make weak duration findings advisory/abstentions instead of certain mistakes.

**Acceptance:** human-labelled correct sustains and deliberately short real notes; report false duration warnings, real short-note detection, offset errors and abstention coverage together. A proposed safety target is <5% false wrong/missing claims on adjudicated correct notes, not a result achieved today. Do not improve apparent accuracy simply by suppressing all feedback.

### P1: distortion-aware candidate validation and alignment

- Use onset, pitch/frame persistence and harmonic structure to validate candidates; do not indiscriminately union two models' notes.
- Preserve genuine repeated picking, palm mutes and chord notes while filtering unsupported harmonic ghosts.
- Add minimal repeated-pitch/missing-note location regressions and ambiguous repeated-section alignment cases.
- Keep audio-only and reference-assisted hypotheses separate. Reference conditioning must not overwrite evidence that the learner played the wrong note.
- Correct default descriptions and backend-specific settings/provenance, including the fact that optional Riley inference is currently CPU in its wrapper.

**Acceptance:** held-out real rhythm and lead, low tunings, gain levels and repeated chords; report ghost precision, repeated-onset recall and location errors. No claim that waveform pitch alone proves the played string/fret or finger pressure.

### P2: broader data and possible model fine-tuning

- Provision 360 GuitarSet performances, EGSet12 and Guitar-TECHS; split by player/song/source before creating variants.
- Evaluate real amp/cabinet and room responses, delay, modulation, compression, fuzz/wah and combinations. Hold out effect chains/IRs as well as performers.
- Use paired dry/effected data with known labels; distinguish pitch-changing effects from label-preserving effects.
- Fine-tune only after decoder/candidate-policy gains are measured. FX classification is not the same as undoing effects or producing trustworthy note labels.
- Evaluate the actual full route: mix → separated guitar → selected lead/rhythm part → notes → section alignment → learner feedback, against true stems and human-labelled takes.

**Acceptance:** held-out real amp and multitrack results, per-condition uncertainty, false feedback and isolated CPU/GPU runtime. Confidence intervals should resample independent recordings, not correlated augmented clips.

## 5. Data and scope limits

This sandbox cannot download from Zenodo or Hugging Face under its current host restrictions; an account link does not change that. Official files can be uploaded locally. Do not share account credentials or private tokens, bypass restrictions, or add large models/datasets to Git.

Official data starting points:

- GuitarSet: https://zenodo.org/records/3371780 (`annotation.zip`, `audio_mono-mic.zip`).
- EGSet12: https://zenodo.org/records/11406378.
- Guitar-TECHS: https://zenodo.org/records/14963133 (`P3_music.zip` for the existing gate).

Reuse `benchmarks/guitarset.py`, `benchmarks/regression/download.py`, catalog/checksums and current error-taxonomy tooling. 360 performances × 12 conditions is 4,320 trials but still only 360 independent performances.

There is no honest guarantee of recovery under every effect: clipping destroys information, delays resemble intentional repetitions, and overlapping instruments can be ambiguous. Guitar remains the priority; bass/piano, physical USB hardware, production concurrency and complete full-band grading need separate validation.

## 6. Reproduction starting point

From `guitar-lab/`, after provisioning dependencies and a trusted local Riley checkpoint:

```sh
export FRETWORK_RILEY_CHECKPOINT=/absolute/path/guitar-fl.pth
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2
python -m benchmarks.regression --tier full --backend basic_pitch --backend riley --no-report --out /tmp/paired-baseline.json
python -m pytest server/tests -q -ra
npm ci
npm run build
npm test
```

Inspect the JSON backend errors and missing coverage even when the CLI returns zero. Do not overwrite immutable historical references to make a regression pass. The earlier exploratory sweep runner/raw outputs are currently absent and must be restored before claiming exact sweep reproducibility.

## Branch deliverable

This branch change is intentionally **documentation only**: consolidated observations, limitations and an actionable backlog. It does not change production thresholds, silently ship an unvalidated tuning rule, or claim missing raw artifacts were recovered. The next implementation should address P0-A/B/C with baseline and held-out before/after evidence.

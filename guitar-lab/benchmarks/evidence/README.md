# Evidence branch: fresh rerun and opt-in changes

**Next-stage intake:** [holdout evidence](holdout/README.md) records the new human-review
workflow and an explicitly blocked empty holdout. It contains no new accuracy claim.

**Follow-up:** [routing verification](routing/README.md) resolves the detector routing
and tab replay check described as outstanding below. It retains the historical
failures here and records new results separately. See [complete branch status](../../BRANCH_STATUS.md).

No merge requested or performed. All work is on `arena/23399fc5-c-games`. This Arena session cannot create/switch to a second branch; this branch is the isolated evidence workspace, not a release approval.

This directory supersedes the *missing-artifacts* limitation for the **new runs below**, not for every historical observation in `../GUITAR_ENGINE_FINDINGS.md`. The new runner, raw small JSON outputs, environment and logs are versioned. No model weights, uploaded recording, decoded audio or full private note transcription is committed.

## Scope: what actually changed

1. **Repeatable baseline/evidence:** `benchmarks/evidence_run.py` performs paired baseline/experimental Riley inference, public metrics, feedback diagnostics and optional unlabelled private-audio windows. `audio.json` is the actual output, not reconstructed historical figures. The existing full regression harness was also rerun.
2. **Quiet-input candidate:** opt-in `FRETWORK_RILEY_LEVEL_GUARD=1` applies a bounded lift only to quiet, dynamic input. RMS range .0005–.012, frame dynamic ratio >=3, crest ratio >=1.5, +24 dB maximum and .95 peak headroom. Silence, steady noise and normal levels are left alone. These guards are heuristics, not a proven noise/reverb detector. Existing adaptive decoding is unchanged.
3. **Duration safety candidate:** opt-in `FRETWORK_DURATION_REVIEW=1` changes audio-derived duration findings to “review by ear; not a confirmed playing mistake”, with a UI notice. It deliberately preserves diagnostic kinds/counts and scores. This is uncertainty-aware presentation, **not a solved duration estimator, learned confidence calibration or a measured reduction in raw duration errors**. Supplied-note/MIDI controls retain their existing behaviour.
4. **Larger held-out library:** NOT completed. Official electric/other private sets are absent. The newly uploaded take is unlabelled and is not a substitute for a held-out labelled library.
5. **Distortion/full-band refinement:** NOT completed. Clipping/room stress cases were run, but there is no new distortion-trained model, amp library or real full-band separator evaluation. These remain follow-up gates before merge.

Both inference/presentation flags default to OFF. They were enabled explicitly in the evidence preview and experimental test run. No global threshold retune or default backend change was made.

## Source identity and test hygiene

- `f096a68`: opt-in policies, paired runner, policy unit tests and UI notice.
- `060dfe9`: tight DSP comparison tolerance and precise browser consent selectors.
- `822dd05`: legacy synthetic browser fixtures explicitly select Basic Pitch.
- `fcab7dc`: added a separate real-guitar default-Riley browser test. A follow-up fixes URI encoding of `#` in the fixture name; the first failed attempt is retained in logs.

`audio.json` records its observed HEAD and working-diff hash. Production policy code is the same across the above test-hygiene commits. Source commit hashes must be read alongside the branch commits, not treated as evidence that all prior runs had identical harness files.

The original exact-PCM lock failed on tiny cross-platform floating-point differences. The fix preserves the golden arrays, uses `rtol=0, atol=1e-10` for cross-platform matching and retains bitwise repeat-render determinism. No fixtures were regenerated.

Legacy browser fixtures were written for Basic Pitch synthetic tones (one literally asserts “Expected notes from real Basic Pitch”). With the current Riley default, the sample guitar/piano fixtures yielded no notes. The tests now explicitly select their intended Basic Pitch backend; this is **not evidence of Riley piano/synthetic-tone accuracy**. The separate real-guitar smoke tests actual default Riley inference. Original failures are retained.

## Fresh test results

All npm test scripts in guitar-lab were attempted, plus the newly added real-Riley script. This is not a rerun of unrelated games elsewhere in this monorepo.

| Check | Result | Evidence |
|---|---|---|
| Frontend production build | PASS | `frontend.txt` |
| Frontend unit tests | 52 PASS | `frontend.txt` |
| First full Python run, before PCM test correction | 199 pass, 1 fail, 3 skip | `python_baseline.txt` |
| Final full Python, flags OFF | **200 pass, 3 skip** | `python_baseline_final.txt` |
| Full Python, flags ON | **200 pass, 3 skip** | `python_experimental.txt` |
| Input browser simulation | PASS | `inputs.browser.txt` |
| Legacy E2E, explicit Basic Pitch | PASS | `e2e.explicit_backend.txt` |
| Profiles, explicit Basic Pitch | PASS | `profiles.explicit_backend.txt` |
| Fresh default Riley + real guitar through browser/API | PASS; HTTP 200, 102 detected notes, review_only, no JS errors | `riley.browser.rerun.txt` |
| Tab browser smoke | **FAIL**; “What the app heard” stays disabled on fake-mic fixture | `tab.explicit_backend.txt` |
| Song/full-band browser smoke with uploaded AAC | **BLOCKED / timed out at 45 s**; no configured separator | `song.browser.txt` |

Initial browser attempts also hit ambiguous consent selectors and Chromium renderer crashes under concurrent CPU/memory-heavy evaluation. An isolated E2E rerun reached a completed Riley job but found zero notes in the synthetic fixture (`e2e.isolated.txt`). These are preserved, not silently discarded. The browser loop wrapper may exit zero even when a suite fails; consult the per-suite status files, not the wrapper status.

Python skips are explicit: EGSet12/Guitar-TECHS missing; heavyweight separation integration opt-in/unprovisioned; older private user fixture takes absent. The new AAC is a distinct recording and was not relabelled as one of those older fixtures just to avoid a skip. ffmpeg and actual Riley inference were available for these fresh runs.

The tab failure still needs investigation. `/api/compare` uses the server default for audio takes, rather than the browser's detector selection; the fake microphone/Riley combination and that backend-selection discrepancy need separate tests. Do not claim it is solely a hardware or model defect, or call the full browser suite green.

## Fresh public regression

`public_regression.json`: no backend errors. Existing full tier, Basic Pitch and Riley; experimental flags enabled. Charts are not passed to the transcriber.

| Category | Basic Pitch F1 | Riley F1 |
|---|---:|---:|
| Three real GuitarSet recordings (macro) | .8148 | .9084 |
| Rendered clean/distorted (macro) | .9706 | 1.0000 |
| Rendered clear/comb-reverb (macro) | 1.0000 | 1.0000 |

IDMT, earlier private takes, Metallica, EGSet12 and Guitar-TECHS were missing, not passes. This is not full-band readiness or broad amp validation. The three real recordings are one player and reused regression material.

## Fresh paired policy experiment

`audio.json`: three source performances × four conditions × two policies = 24 public inference trials, eight-second windows. Additional private windows are separate. The room is a deterministic synthetic diffuse response decaying to -60 dB at two seconds, not a measured room. Correlated variants are not independent performances.

| Condition | Baseline Riley F1 | Guard-enabled F1 | Baseline correct-feedback fraction | Experimental correct-feedback fraction |
|---|---:|---:|---:|---:|
| Original | .8967 | .8967 | 81.6% | 81.6% |
| −24 dB | .8398 | **.8967** | 62.8% | **81.6%** |
| Hard clipping | .8375 | .8375 | 65.7% | 65.7% |
| Synthetic room | .8569 | .8569 | 51.1% | 51.1% |

Per-clip macro averages. Exact-pitch/onset note F1 ignores offsets. “Correct-feedback fraction” is a correct-performance annotation control, not human-adjudicated player accuracy. Duration wording does not change these fractions. Experimental duration review messages: original 9, quiet 9, clipped 10, room 41 (summed across clips).

The guard recovered the quiet sample's baseline loss without changing the tested other conditions. This is an exploratory candidate evaluated on reused data, **not validation of universal improvement or permission to merge**. The new room treatment runs at the source sample rate before file writing, unlike the earlier 16 kHz decoder sweep; those historical numbers are not identical-input reruns.

## Uploaded recording

The `.txt` upload was copied locally as `benchmarks/regression/data/private/user/whatsapp_take.aac`. The uploaded original was preserved. ffmpeg successfully decoded the entire file: AAC LC, 44.1 kHz stereo, approximately **305.0 seconds**. A mono 22.05 kHz WAV was generated for evaluation. Both are gitignored.

`private_manifest.json` records the source checksum/size and decode metadata. No ground-truth notes, take/reference mapping or confirmed content labels were supplied. It must not receive an accuracy score.

Fixed ten-second windows at 0, 145 and 290 seconds were transcribed with both policies: note counts 7/7, 4/4 and 3/3 respectively. These counts are not precision, recall, correctness, or evidence of a clean guitar source. The whole recording was decoded; **only these windows were transcribed**, not all five minutes. Raw private note sequences and audio are not in Git. Selected-window successful inference does not validate the full-band song route.

## Reproduction

Provision trusted Riley weights, a compatible ONNX/torch environment (see `environment.txt`) and ffmpeg. The recorded runtime is an evaluation environment, not a patched production dependency/security lock. Browser tests also need a local Chromium plus system libraries; this sandbox used an npm-distributed Chromium with its bundled shared libraries.

From guitar-lab:

```sh
export FRETWORK_RILEY_CHECKPOINT=/absolute/path/to/trusted-local-checkpoint.pth
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2
FRETWORK_RILEY_LEVEL_GUARD=0 FRETWORK_DURATION_REVIEW=0 python -m pytest server/tests -q -ra
FRETWORK_RILEY_LEVEL_GUARD=1 FRETWORK_DURATION_REVIEW=1 python -m pytest server/tests -q -ra
python -m benchmarks.evidence_run --out /tmp/audio.json --take /local/decoded-take.wav
FRETWORK_RILEY_LEVEL_GUARD=1 python -m benchmarks.regression --tier full --backend basic_pitch --backend riley --no-report --out /tmp/regression.json
npm ci && npm run build && npm test
```

For browser tests run engine and frontend separately; set `BROWSER_EXECUTABLE_PATH`, appropriate library paths and `SONG_FILE` where required. Execute `test:e2e`, `test:inputs`, `test:profiles`, `test:tab`, `test:song`, and `test:riley` individually and retain exit statuses. The song test requires real separation. Inspect JSON backend errors/coverage even if a CLI returns zero.

## Before any merge decision

1. Keep both experimental flags OFF in normal deployments until held-out evaluation.
2. Add quiet/noisy dry and quiet/wet real recordings, with independent player/song splits; measure ghost precision, note recall and abstentions.
3. Validate real sustain errors versus correct sustains with human labels; presentation-only review is not an improved offset estimator.
4. Investigate tab/default-detector routing and replace or explicitly scope beep-based inference expectations. Restore full-band separation and rerun the blocked song test.
5. Expand the licensed amp/effects library, then evaluate mix-to-feedback with true stems and section/lead/rhythm labels. Do not infer these capabilities from the small clean-guitar regression.

**No merge performed. This branch contains test evidence and opt-in experiments, not an approved release of all five roadmap items.**

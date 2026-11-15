# Evidence branch: what is complete, and what is not

Branch: `arena/23399fc5-c-games`  
Latest tested implementation: `2f084ec`  
**No merge performed. Experimental flags remain off by default.**

## New follow-up: holdout intake and human review

Implementation `5cdb730` adds a frozen collection protocol, fail-closed intake/evaluator,
and a local browser labelling tool. See [the holdout workflow](benchmarks/holdout/README.md)
and [fresh verification](benchmarks/evidence/holdout/README.md).

- **Ready:** checksum/leakage/coverage checks, paired-policy evaluator, raw sustain metrics,
  and an unlabelled listening packet from the existing upload.
- **Not completed:** independent holdout acquisition or actual human sustain review.
  The real intake contains **zero approved clips**; evaluation exits 3 without inference.
- **Fresh checks:** 37 new holdout tests, review-page browser smoke, frontend build and
  53 frontend unit tests passed. The earlier 206-test full Python runs below were not
  rerun in this infrastructure-only follow-up. Automated review fixtures are not human labels.
- No new transcription-accuracy score, production policy/default change or merge.

## Does this improve transcription into tab/standard notation?

Only a narrower improvement has been measured: the opt-in quiet-input guard improved pitch/onset note detection on deliberately attenuated versions of three reused real-guitar clips. Those detected notes feed notation generation, so better detection can help the resulting notation. We have **not demonstrated that the uploaded WhatsApp recording now has more accurate tab, rhythm spelling, sustain, string/fret choices or standard notation**. It has no verified score against which to measure that.

Successful notation rendering/export is a functional test, not proof that the notation is musically accurate. Note counts are not accuracy scores.

## Completed on this branch

| Work | Status / evidence |
|---|---|
| Consolidated findings and prioritised plan | Completed: [findings](benchmarks/GUITAR_ENGINE_FINDINGS.md). Historical observations are explicitly separated from fresh runs. |
| Durable paired evaluation | Completed for the small public set: source runner, raw JSON, dependency manifest, test logs and missing-coverage reporting in [evidence](benchmarks/evidence/README.md). |
| Quiet-input gain candidate | Implemented behind `FRETWORK_RILEY_LEVEL_GUARD=1`. Bounded, gated lift; defaults OFF. Reused quiet samples: F1 .8398 → .8967. Other tested conditions unchanged. Not held-out validation. |
| Duration-feedback safety candidate | Implemented behind `FRETWORK_DURATION_REVIEW=1`. Audio-derived duration findings say review by ear; UI explains uncertainty. Counts/scores unchanged. This does not improve the duration estimator. |
| Detector routing for direct/tab comparisons | Fixed: client sends detector, API validates it, inference and response label use the same chosen backend. Omitted detector uses engine default; invalid/unavailable choices are rejected, not silently replaced. |
| Detector routing for song takes | Fixed: explicit detector is honoured; otherwise use the song session's detector rather than the unrelated global default. |
| Job provenance label | Fixed to describe the job's chosen backend, not whichever backend is globally default. The older tab score-informed path deliberately uses Basic Pitch posterior maps and still says so. |
| Tab replay/render/export check | Passing with a real-guitar microphone fixture. Detected notes replay on the app guitar, render as tab/notation and offer a Guitar Pro download. The fixture is unrelated to the tab: its low match score is expected, not a transcription-accuracy benchmark. |
| Uploaded recording handling | Entire 5:05 AAC decoded locally; three fixed 10-second windows transcribed with both policies. No ground truth, no accuracy claim, no audio committed. Not a whole-recording transcription. |
| Git sharing | Code, evidence and documentation are pushed to this branch. No pull-request merge, main update, or release approval. |

## Latest fresh checks after routing changes

Implementation tested: `2f084ec`; see [routing evidence](benchmarks/evidence/routing/README.md).

| Check | Result |
|---|---|
| Production frontend build | PASS |
| Frontend unit tests | **53 passed** |
| Full Python, experimental flags OFF | **206 passed, 3 skipped** |
| Full Python, experimental flags ON | **206 passed, 3 skipped** |
| E2E browser (legacy Basic Pitch fixture) | PASS |
| Input simulation browser | PASS — not physical USB testing |
| Instrument-profile browser (Basic Pitch fixture) | PASS — not Riley piano/bass validation |
| Tab browser | PASS — replay, notation, export option and mobile layout |
| Real-guitar browser: default Riley and explicit Basic Pitch | PASS — actual inference and matching provenance for each |
| Full-band song/separator route | Still BLOCKED/unprovisioned; not rerun or counted as a pass in this follow-up |

The three Python skips are missing EGSet12/Guitar-TECHS, unprovisioned heavyweight separation, and the older private recording fixtures. The new uploaded AAC is not substituted for unrelated older takes.

The legacy beep-based tab fixture was changed to a bundled real-guitar microphone input because beep/silence did not provide detected guitar notes. This is a test-input correction, **not evidence that the model became more accurate**. Independent routing unit tests and a real-guitar default/override browser check accompany it.

## Not completed / not ready to merge as a quality claim

1. **Larger held-out library.** No new independent players/songs or broad real amp/effect set has been provisioned. Three source performances plus variants do not establish population accuracy.
2. **Validated sustain-error detection.** Review-only wording is safer presentation, not learned confidence or separation of direct sustain from room tails. Correct/shortened real notes need human labels.
3. **Distortion/effects refinement.** No new trained amp/room model or universal decoder policy. Real high gain, fuzz, modulation, delay and combined effects remain under-tested.
4. **Full-band end-to-end validation.** Separator runtime/weights are absent here. Mix → selected guitar → lead/rhythm → notes → aligned learner feedback remains unverified in the fresh runs.
5. **Accurate transcription of the uploaded recording.** No verified target score/annotations and no full-recording notation audit. Automatic string/fret positions remain suggestions.
6. **Physical hardware, GPU and production readiness.** Browser input simulations are not physical USB/latency tests; no GPU/concurrency release validation.

## Next work, in order

- Obtain labelled, independent quiet/dry and quiet/wet recordings; run paired policy tests without tuning against the held-out answers.
- Label genuine sustain mistakes and correct sustains; measure false warnings, missed errors and abstention coverage, not just onset F1.
- Provision licensed amp/effect and multitrack datasets plus separation weights; evaluate real lead/rhythm/section accuracy end to end.
- Decide whether either flag should become a default only after that evidence. Keep this branch isolated until review.

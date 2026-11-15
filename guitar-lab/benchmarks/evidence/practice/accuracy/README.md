# Actual model / real recorded guitar results

This follow-up is based on ef4313e plus the checksummed accuracy-suite working tree. `real-regression.json` records source-code hashes, model hash, runtime versions, Git base and dirty-tree status. No production detector threshold, model weight or feedback rule was tuned here.

## Fresh local verification

- `python-tests.txt`: **43 passed**, no skips with real inference enabled. This includes 24 existing comparison/self-check tests and 19 new accuracy/intake tests. Most validation/metric tests use synthetic unit fixtures; one new real integration test uploads **all three actual GuitarSet WAVs through the real `/api/compare` API and Basic Pitch**, without replacing inference or comparison functions. A single server lifespan is used because real shutdown intentionally deletes its temporary store.
- `api/*.json`: actual API transcription metrics and comparison counts for all three unchanged real recordings.
- `real-inference.txt` and `real-regression.json`: separate real inference plus publisher-annotation metrics and self-check diagnostics. This uses no cached posterior/prediction fixture, altered reference or synthesized input recording. The self-check intentionally synthesizes its true-note guide and compares it with real audio, as the feature normally does.
- `independent-status.json`: **blocked_missing_coverage**, zero audited sources/performers, inference_run/attempted/completed all false, quality_approved false.
- `independent-exit.txt`: exit 3, the expected fail-closed result for empty independent intake.

## Measured development results (not an independent holdout)

| Real recording | Note F1, correct pitch/onset ±50 ms | Self-check marked share with true notes |
|---|---:|---:|
| Funk lead | 0.7611 | 0.0% |
| Jazz rhythm | 0.8101 | 0.0% |
| Rock lead | 0.8731 | 14.5% |

Macro note F1 = **0.8148**. This reproduces the small development set's existing approximate baseline; it is not a new accuracy gain. Self-check marking 14.5% of the Rock recording with true notes is a limitation worth reviewing, not a successful detection claim.

All three are previously used player-05 acoustic microphone recordings. They do **not** establish independent performer accuracy, genuine learner-fault precision/recall, DI/effects/full-band performance, Riley quality, physical USB support or GPU quality. Dataset notes describe performed notes, not independently judged musical mistakes. Diagnostic warning counts are therefore annotation-consistency signals rather than authenticated false-playing-fault labels.

## Independent evaluation next

See `benchmarks/practice_feedback/README.md` and `protocol.json`: six new physical takes from three performers, real DI/microphone/effects coverage, rhythm/lead, explicit correct passages and localized genuine faults, unexposed reviewer and separate checksum-bound audit. The preparation tool extracts private source audio and writes an unapproved audit form, never human truth. No qualifying inputs have been supplied, so **no independent accuracy numbers exist yet**.

GitHub CI was configured to repeat the real CPU regression and upload artifacts on relevant PR changes. These committed files record local results; remote Actions completion must be checked separately. No frontend/browser suite was rerun in this Python-only follow-up; earlier browser results remain historical workflow evidence.

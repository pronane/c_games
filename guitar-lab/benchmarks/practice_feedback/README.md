# Real practice-accuracy tests, with evidence tiers kept separate

These tests add **actual model inference on real recorded guitar** plus a separate fail-closed path for independent human playing-fault evaluation. A green development regression is not independent holdout approval.

## 1. Real audio → real model → real comparison API

The three bundled GuitarSet v1.1.0 microphone recordings and publisher note annotations are used unchanged. No synthesized audio, planted reference errors, cached predictions or inference mocks are used by the opt-in integration test.

```sh
# From guitar-lab/, Python 3.11. CPU is sufficient.
python -m venv .venv
.venv/bin/pip install -r benchmarks/practice_feedback/requirements.txt
.venv/bin/pip install --no-deps basic-pitch==0.4.0

OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  .venv/bin/python -m benchmarks.practice_feedback regression \
  --backend basic_pitch --out /tmp/practice-regression.json

FRETWORK_RUN_REAL_PRACTICE=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  FRETWORK_REAL_PRACTICE_EVIDENCE=/tmp/practice-api-results \
  .venv/bin/python -m pytest server/tests/test_practice_feedback_accuracy.py -q
```

The integration test uploads all three real WAVs through `/api/compare` with an explicit Basic Pitch selection. It scores the returned take notes with `mir_eval` (correct pitch and onset ±50 ms, offsets ignored), checks the waveform hashes and compares F1 with the **frozen current development baseline**, allowing an absolute 0.02 regression. This is a regression tripwire, not a scientifically justified quality acceptance threshold. No app notes/model functions are replaced by mocks. The module's other tests use synthetic fixtures to test metrics and fail-closed validation; they are not human evidence.

`regression` additionally records comparison warning counts and transcription self-check flagged duration using the publisher's true note list against the **real** audio. Those are annotation-consistency diagnostics, not a new human judgement that every warning is false. A self-check flag on correct notes demonstrates potential false positives, not successful mistake detection.

Fresh measured development results are in `../evidence/practice/accuracy/`:

| Material | Note F1, ±50 ms | Self-check marked duration with true notes |
|---|---:|---:|
| Funk lead | 0.7611 | 0.0% |
| Jazz rhythm | 0.8101 | 0.0% |
| Rock lead | 0.8731 | 14.5% |
| Macro note F1 | **0.8148** | Not a note-accuracy percentage |

**Limits:** all three are previously used development clips, one performer, acoustic microphone. They do not represent independent new performers, DI, real effects, full-band separation, physical USB, Riley or GPU accuracy. Model-training overlap is unknown. The 14.5% true-note self-check flag share in the Rock clip is an important limitation, not evidence of accurate feedback. No threshold/engine tuning was performed in this PR follow-up.

The new GitHub workflow `Guitar practice real-audio regression (not independent holdout)` runs these actual CPU inference tests for relevant PR changes or manual dispatch, saves provenance/metrics as artifacts and checks that empty independent intake remains blocked. Its GitHub execution status is separate from locally recorded results; do not claim remote CI passed until its checks actually finish.

## 2. Independent human listening-fault accuracy

`protocol.json` is a frozen initial collection/measurement protocol. `intake.json` is **empty on purpose**. Evaluation exits **3**, reports `blocked_missing_coverage`, and imports/runs **no model** until every check passes. It does not inherit a green status from the development regression.

Required collection:

- Six new independent physical performances from at least three performers, not used for project tuning. Existing player-05 and WhatsApp development sources are excluded.
- At least two sources each of `dry_di`, `microphone`, `real_effects`, and both rhythm and lead across the set. Real effects means real amp/pedal/room capture, not synthetic convolution.
- At least five localized audible events of each type—pitch, timing, missing, extra, sustain—across at least two sources per type.
- At least 120 seconds explicitly labelled as correct regions. Empty labels or whole-take-listened checkboxes do not silently create correctness truth.
- One packet per physical performance. For this initial intake, the packet WAV must be the unmodified standalone source take, with the source WAV supplied and checksums matching. Do not submit crops, gain variants or different captures of the same performance as new sources. The earlier `benchmarks/holdout/` protocol handles paired quiet/wet variants separately.
- A reviewer who declares no exposure to app predictions and a full listening pass, plus a separate auditor who verifies consent/rights, real guitar/source identity, capture condition, reference and annotations, project-tuning exclusion and reviewer exposure. Declarations are checksum-bound, not authenticated proof; never label synthetic tests as genuine human reviews.

### Prepare an intake without manufacturing approvals

1. Collect/record a new take, retain its audio in the app, and use a trusted, reviewed reference.
2. Export a listening-only packet, then ask the unexposed reviewer to use the separate `?listening-review` page and export labels. Keep observations local: faults should be localized to at most a two-second interval around their occurrence. Mark correct regions explicitly and uncertainty/noise separately.
3. Prepare the private record, using aliases that the collector supplies:

```sh
.venv/bin/python -m benchmarks.practice_feedback.prepare \
  --packet /path/to/listening-only-packet.json \
  --labels /path/to/listening-review-labels.json \
  --out benchmarks/practice_feedback/private/new-intake \
  --source physical-performance-alias --performer performer-alias \
  --condition dry_di --part lead
```

This extracts/copies the exact WAV and labels, creates a manifest entry and writes a **pending** audit form with every approval false. It never invents a reviewer, verifies a physical performance automatically, overwrites existing review files or runs inference. The destination is gitignored by convention; do not commit private audio or identities.

4. Have a different human auditor complete the generated `*.audit.pending.json` only after checking the evidence. It binds the exact packet digest, raw-label-file checksum and original-waveform checksum. Editing labels afterwards invalidates the audit. Repeat the preparation command with genuinely different sources until coverage is complete.
5. Audit before inference:

```sh
.venv/bin/python -m benchmarks.practice_feedback audit \
  --manifest benchmarks/practice_feedback/private/new-intake/intake.json \
  --out /tmp/practice-intake-audit.json

.venv/bin/python -m benchmarks.practice_feedback evaluate --backend basic_pitch \
  --manifest benchmarks/practice_feedback/private/new-intake/intake.json \
  --out /tmp/independent-practice-feedback.json
```

Exit codes: **0** complete audit/measurement, **3** missing/invalid independent coverage (no inference), **2** malformed input/runtime/model error. Errors overwrite the requested report so an older successful file cannot masquerade as a new run. `quality_approved` remains false for all outputs; this tool never merges code or promotes engine defaults.

`--backend riley` / `gaps` is supported only if actually provisioned. There is no silent fallback to Basic Pitch. Basic Pitch ONNX model hash, numerical runtime versions, code/protocol checksums and relevant flags are recorded. Other backends require their own model-checkpoint provenance before external publication.

### What the human feedback metrics mean

- These are **localized issue-event** metrics, not per-note truth or exact wrong-pitch diagnosis. The listening labels do not encode expected/actual MIDI pitches.
- Map wrong pitch→pitch, early/late→timing, missed→missing, extra→extra, note-length warning→sustain. Inferred wrong string and engine uncertainty are counted separately as unsupported/abstained findings.
- Cluster same-kind note findings within 150 ms of the cluster's first note, so a chord warning is not counted once per string. Merge overlapping same-kind human intervals as one event. Match one-to-one by type within the labelled interval plus the preregistered ±150 ms tolerance.
- Use actual take times. For missed notes with no take event, interpolate the reference position through aligned target/take note pairs; if no time map exists, abstain instead of pretending a target timestamp is an observed recording event.
- Count precision only over explicit correct or fault coverage. Report unreviewed predictions and noise/uncertainty-masked events separately; do not treat unknown material as correct. Report recall over labelled fault events, and false warnings per explicitly correct minute.
- Report per-kind TP/FP/FN, precision/recall/F1, source rows and recording-condition/part breakdowns. Retain alignment warnings. Empty precision/recall denominators are null, not perfect scores. Source-macro false-warning rates prevent long/dense takes from silently dominating. No small-sample bootstrap confidence claim is made.

**Current independent result: blocked; zero approved recordings/labels supplied.** App labels retain `independent_ground_truth:false`; a separate audited intake is necessary, and the audit itself still relies on human declarations. These tests complement—not replace—the earlier note/sustain holdout protocol. No independent accuracy result has been fabricated or inferred from mocked tests.

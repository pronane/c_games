# Independent quiet/wet and human sustain evaluation

This is **intake and review infrastructure**, not a new accuracy result. It never labels machine predictions as human truth, counts transformed versions as independent performances, or promotes defaults. See [current intake result](../evidence/holdout/intake-status.json).

## Current state

- The three bundled GuitarSet performances, their performer 05 and the previously used WhatsApp take are development material, not a new holdout.
- No new independent recording or human-verified sustain label has been supplied.
- The checked-in `intake.json` is deliberately empty. `evaluate` exits **3**, reports `blocked_missing_coverage`, and does not import/run a model.
- Existing inference, notation, grading rules and experimental defaults are unchanged by this milestone.
- The review UI is available with `python -m benchmarks.holdout.serve_review --port 8765`. It serves only the page, not the dataset. Audio is selected locally in the browser and never uploaded by this tool.

## Frozen initial protocol

`protocol.json` is versioned before acquiring the new evaluation set:

- At least **six independent physical performances from three performers** not used in project tuning.
- Each performance has paired **dry, quiet dry, wet and quiet wet** cases: at least 24 waveform trials, still only six performances.
- Wet examples must come from real effect/amp/room captures, not simulated convolution. Reamping the same recorded DI through real equipment is suitable; document alignment. Digital level variants are permitted for quiet conditions but remain the same source.
- If a guitarist plays the piece again, that is a new physical performance, not a sample-aligned variant. Never reuse another take's labels without reviewing it.
- At least **20 correctly held, 20 genuinely short and 10 genuinely long** human-labelled sustain examples across at least three source performances. Counts are deduplicated across variants.
- Labels describe direct-note offsets, not reverberant tails. Expected durations must fit within the window and refer to the recording's tempo. State a trusted score/reference or musical listening rationale for each sustain judgement.
- Review targets: quiet-dry macro note-F1 gain >=.02; no other-condition macro loss >.01; any individual clip loss >.05 requires review. Raw false sustain-warning goal <5%, with unmatched/abstention coverage reported. These are targets, not measured achievements or automatic merge gates.

This set is held out from **this project's policy tuning** only. Riley's original training-data overlap cannot be independently guaranteed. Six performances are a minimum collection milestone, not proof of universal robustness. Keep an additional future test set if tuning follows these results.

## Collecting and labelling

1. Obtain rights/consent for the recordings. Prefer reviewer/performer aliases rather than personal details.
2. Save the original physical performance's checksum and a stable `source_id`. Every derived gain/effect variant retains this parent identity. Do not invent new IDs for crops or effects.
3. Prepare .4–60 second PCM WAV windows, mono or stereo. Avoid clipping note ends at window boundaries. Preserve alignment and direct-note timing when preparing paired conditions.
4. Open `review.html`, select a WAV, and listen with a trusted musical reference. Add only pitches and direct-note boundaries that can be verified. Unknown offsets are not eligible sustain labels.
5. For each sustain example, enter expected duration, human judgement and its basis. A correct sustain need not have mathematically identical length; it is a human musical judgement, not the engine's duration threshold.
6. Use consistent note IDs across paired variants; use different prefixes for non-overlapping windows. Do not count overlapping examples twice within one condition.
7. Enter a reviewer alias, personally verify the rows, then export labels. The tool computes the WAV checksum; it makes no note predictions. A second reviewer should resolve ambiguous boundaries. The checkbox records a declaration, not authenticated identity or proof of expertise.
8. Place audio and labels under a private, gitignored intake directory. Uploading exported labels/independent recordings here is sufficient; the agent can construct/check the manifest. Do not put private audio in Git.

### Prepared packet from the user's existing take

A local ZIP was prepared at `benchmarks/regression/data/private/user/sustain-review.zip`, containing three ten-second windows beginning at 0, 145 and 290 seconds, the offline review page, pending-label templates and parent timestamps/checksums. No note, sustain judgement or dry/wet category was inferred.

**This packet is development review material, not independent holdout data.** The parent take was already used in this session. Human labels for it could help establish whether the current feedback is meaningful on that recording, but cannot satisfy the independent-holdout gate. No human review has yet occurred.

The review page performs no network audio upload. Its automated browser test simulates clicks and exports a synthetic schema fixture; that output is deleted and is explicitly **not human-labelled evidence**.

## Manifest format

Create a local manifest beside the intake files. This abbreviated example is a template, not valid evidence until real checksums/review exist:

```json
{
  "protocol": "guitar-holdout-v1",
  "clips": [{
    "id": "p01-performance01-dry-window01",
    "source_id": "performance01",
    "source_sha256": "SHA256_OF_ORIGINAL_PHYSICAL_PERFORMANCE",
    "performer_id": "new-player-01",
    "condition": "dry",
    "capture": "real",
    "split": "evaluation",
    "rights_confirmed": true,
    "audio": "performance01-dry.wav",
    "sha256": "SHA256_OF_THIS_WAV",
    "labels": "performance01-dry.labels.json",
    "labels_sha256": "SHA256_OF_EXPORTED_LABELS"
  }]
}
```

- File paths must be relative and resolve inside the manifest directory; symlink/path escapes are rejected.
- Audio and labels checksums must match. Known development hashes, source IDs and performer IDs are rejected.
- One parent hash cannot become multiple independent source IDs. Identical audio cannot be renamed as another source/condition.
- Labels require a nonempty reviewer alias, `review_status: human_verified`, and a matching `source_sha256` (the selected WAV). Merely editing the status is not legitimate human review.
- Notes have unique `id`, `time`, `duration`, integer `midi`. Sustain entries have `note_id`, `expected_duration`, `judgement` (`correct`, `too_short`, `too_long`) and nonempty `basis`.
- Repeated sustain IDs across different conditions count once for independent example coverage. Conflicting judgements across variants and overlaps within one condition are rejected. If the processing changes the direct performance rather than merely its sound, it is not the same labelled example.
- `capture: synthetic` cases can be retained as exploratory records but never satisfy required real-wet/real-capture coverage.
- Human provenance is self-declared. Checksums/schema checks cannot authenticate a reviewer or discover all deliberately misrepresented source relationships.

## Commands and exit statuses

From guitar-lab:

```sh
python -m benchmarks.holdout audit --manifest /private/holdout/manifest.json --out /tmp/intake.json
FRETWORK_RILEY_CHECKPOINT=/local/trusted-model.pth python -m benchmarks.holdout evaluate --manifest /private/holdout/manifest.json --out /tmp/results.json
python -m pytest server/tests/test_holdout.py -q
# Start review server separately, then with a compatible Chromium:
BROWSER_EXECUTABLE_PATH=/local/chromium npm run test:review
```

- **0:** coverage audit ready, or evaluation completed. **Not quality/merge approval.**
- **3:** missing mandatory data/coverage; no model inference.
- **1:** invalid intake or failed evaluation. No successful quality claim.

The audit uses only Python's standard library and does not need torch/model weights. Evaluation needs the existing specialist engine stack. It freezes baseline vs guarded input and never passes condition labels or expected notes to inference. The guard environment setting is restored, including on errors.

Evaluation reports onset/pitch F1, matched-note offset error, raw sustain false flags/misses, unmatched coverage, per-condition summaries and a paired source-grouped bootstrap interval. Missing matched notes are not counted as evidence that duration is correct. Review-only wording cannot improve these raw metrics. Variants are averaged within sources before bootstrap; the small number of performers still limits inference.

The current runner is a **transcriber/raw-duration evaluation**, not the complete mix-to-notation/feedback application. It uses the current guitar transcription range, MIDI 40–88. It does not validate rhythm spelling, fingering, full-band separation, physical USB hardware or GPU processing.

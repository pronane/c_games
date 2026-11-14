# Review → Practise → Retry

## Purpose and entry points

Help a guitarist hear a problem, choose a useful exercise and improve the next attempt. This is not a promise of arbitrary full-band performance grading.

- In **Learn from a tab or score**, load/select the intended track, then choose **Review → practise → retry this chart**.
- In **Song Lab**, generate the intended part's tab, listen to the isolated part and inspect it, then choose **Review → practise → retry this part**.
- The new workspace appears below the chart lesson. Saved projects can be opened without repeating separation or importing the chart again.

## Review the reference

Projects start **unverified**, including imported charts. Check the arrangement, song passage, tuning/capo and rhythm/lead part. Grading is gated on explicit reference approval. Unreviewed projects can still be heard and recorded without a grade.

The correction editor accepts a bounded JSON list of `{time, duration, midi}` rows, in reference seconds. Simultaneous notes represent chord tones. Applying corrections creates a new reference revision and revokes approval. Historical reports remain historical; their expected-audio comparisons and focus/retry actions are disabled against a changed reference.

Named sections support verse, chorus, solo or any other label. Exclude an unreliable section to disable grading for every overlapping phrase, even if a retry is given a different name. This is a conservative interval-overlap check, not just a section-name check.

Weak Riley onset evidence is now **uncertain**, not **correct**. Uncertain notes are excluded from diagnostic summary/bar-score denominators. An entirely uncertain bar has no score. Duration and inferred fingering findings are explicitly listening-review candidates in the guided workspace. Too few aligned note pairs trigger an alignment warning and suppress automatic focus suggestions. These are heuristic warnings, not calibrated confidence probabilities.

## Practise and retry

1. Select/name a phrase (0.1–60 reference seconds) and speed (50–100%).
2. Listen to or loop the plain-guitar guide. Pitch stays unchanged as timing is slowed.
3. Wear headphones; optionally calibrate device delay with the existing latency tool.
4. Record with four-beat count-in, guide and click. Early-stop partial phrases are not graded.
5. Review a finding with expected → take or simultaneous playback around its timestamp. Confirm, dismiss or mark it unsure.
6. Pick a focus phrase. Human-confirmed issues are ranked first; at most two pitch/missing/extra or calibrated-timing candidates are suggested. Dismissed/unsure issues and uncertain duration/string findings are not automatically suggested.
7. Read the short exercise guidance, practise, then retry at the same phrase/speed. Speed increases remain a deliberate player choice.

Earlier audio can be uploaded with a reference start timestamp and declared practice speed. Trim count-in first; audio duration determines the reference end. This is the manual fallback, not automatic section recognition. Uploaded takes are marked latency-unverified. Browser audio-codec support applies; normal Song Lab import remains available for broader server decoding.

Expected audio uses a generic plucked guitar, not the original amp. Finding snippets use the aligned expected/take timestamps; they are not guaranteed sample-perfect overlays or a substitute for listening to the original.

## Saved projects, progress and privacy

- Explicit **Save project on this device** uses IndexedDB. No accounts or cloud storage.
- Save title, goal, part, tuning/capo, editable reference notes/revision, sections/exclusions, speed/active section, take comparisons, user review labels and optionally take audio.
- **Audio retention is off by default.** Enable it before capturing to enable later A/B listening. Retention controls local project audio, not temporary engine storage.
- Projects preserve reference *notes*, not the original full song/stems or complete chart file. Keep originals separately. The notes remain playable and editable after the temporary song session expires.
- Changes are not autosaved. Explicitly save after removing audio/takes to update the saved copy. Delete project removes its saved IndexedDB copy; exported downloads are not deleted.
- Portable JSON export includes retained WAV audio. Imports are size/schema bounded, never executed, and get a new ID rather than overwriting an existing project. Maximum 600-second reference, 30,000 reference notes, 100 sections, 50 takes, 50 MB retained audio, 80 MB import.
- Progress is compared only across identical phrase boundaries, practice speed and reference revision. Counts are human-confirmed issues, with review coverage shown—not a universal ability/accuracy score. With retained audio, play previous → current take directly.
- Browser storage can be evicted or fail for quota/privacy reasons. Errors are surfaced; export backups before clearing browser data.

Recordings are sent to the configured Python analysis API for comparison. Existing engine consent/temporary-storage limits still apply. CPU functionality remains; this feature does not introduce a GPU-only path or claim that heavyweight models are provisioned in every environment.

## Real-guitarist validation protocol (not yet completed)

The workspace collects finding confirmations/dismissals/uncertainty plus whether the issue was audible, the exercise useful and the retry better. **Export review labels** excludes audio and explicitly sets `independent_ground_truth: false`. A user confirming the app's suggestion is not independent annotation.

For an actual release-quality validation:

1. Obtain consent and licence/ownership declarations. Use the existing `benchmarks/holdout/` intake and independent performer/source-group requirements; do not silently reuse development recordings as a holdout.
2. Include correct performances, genuine wrong/missed/extra notes and early/late changes, rhythm chords and lead phrases, clean DI, microphone and real hardware effects. Include correct sustain and effect tails to measure false duration accusations.
3. Before showing app findings, have a guitarist/teacher annotate audible faults with timestamps and reference version. Record reviewer identity, recording source/performer, capture/effects condition and uncertainty. Preserve this independent annotation separately.
4. Run the app, match findings to annotations and report false warnings on correctly played material as well as recall. Break down by issue type, reference source and recording condition. Do not pool full-band separation results with trusted-chart results.
5. Observe whether the player understands the finding, performs the suggested exercise, and improves on a matched-speed retry. Have the reviewer compare before/after without knowing the app's score; retain inconclusive judgements.
6. Audit coverage through the existing fail-closed holdout tooling before claiming independent engine improvements. App review exports supplement that process; they do not automatically approve a holdout or generate truth labels.

**No real participants, independent labels, physical USB/GPU evidence, new model training or model-accuracy improvement is claimed by this feature PR.** Automatic section recognition, cloud project sync, full notation editing and calibrated confidence are not implemented.

## Verification

- `npm run build`
- `npm test` (including project schema, phrase timing, reference revision/speed comparability, uncertainty and exclusion-overlap tests)
- `.venv/bin/python -m pytest server/tests/test_transcription_check.py server/tests/test_compare.py -q`
- `BROWSER_EXECUTABLE_PATH=/path/to/chromium npm run test:practice` with the frontend and API running

Browser smoke uses an actual browser/fake microphone and **mocked comparison responses**. It verifies chart entry, reference/exclusion gates, capture, review playback, focus/retry, IndexedDB reload including audio, portable export, correction revision and deletion. It is not a transcription or real-guitar accuracy test.

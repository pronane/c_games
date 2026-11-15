# Review → Practise → Retry

## Purpose and entry points

Help a guitarist hear a problem, choose a useful exercise and improve the next attempt. This is not a promise of arbitrary full-band performance grading.

- In **Learn from a tab or score**, load/select the intended track, then choose **Review → practise → retry this chart**.
- In **Song Lab**, generate the intended part's tab, listen to the isolated part and inspect it, then choose **Review → practise → retry this part**.
- The new workspace appears below the chart lesson. Saved projects can be opened without repeating separation or importing the chart again.

## Review the reference

Projects start **unverified**, including imported charts. Check the arrangement, song passage, tuning/capo and rhythm/lead part. Grading is gated on explicit reference approval. Unreviewed projects can still be heard and recorded without a grade.

Open **Visual reference editor — notes and chord tones** to edit the current section in a piano roll:

- Click a note to select it; Shift-click adds to a selection. Optionally select chord tones together (attacks within 30 ms).
- Drag to change time/pitch; Alt-drag to resize duration. Keyboard arrows move notes; Alt-left/right changes length. Numeric fields offer precise timing, pitch and length edits.
- Choose beat/eighth/sixteenth snapping or no snapping. Add/delete notes, transpose a chord, or duplicate the selection one beat later. Group transforms preserve intervals/spacing and stay within MIDI/time bounds.
- Audition the draft phrase or selected notes; stop playback with **Stop phrase playback**. The audition uses the selected practice speed and generic guitar sound, not the original amp.
- Undo/redo keeps up to 40 draft edit states. **Apply visual corrections** is the only action that changes the live reference. Unapplied drafts are not saved/exported; apply before switching projects.
- Source note tails are bounded to the reference end in the visual draft. At most 2,000 overlapping notes are drawn; use shorter sections for dense material.

An advanced JSON editor remains available for `{time, duration, midi}` rows in reference seconds. Simultaneous notes represent chord tones. Either editor's Apply creates a new reference revision and revokes approval. Historical reports remain historical; their expected-audio comparisons and focus/retry actions are disabled against a changed reference. This is a pitch/timing editor, not a complete notation/fingering editor.

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
- Projects preserve reference *notes* and optionally an original chart attachment (Guitar Pro, MusicXML, MIDI or text tab, up to 8 MB). Attach under **Keep an original reference chart with this project**. The attachment is an inert byte-for-byte backup, is never executed, and can be downloaded/removed; corrections do not rewrite it. Full songs/stems are not retained; keep original audio separately. Notes remain playable/editable after the temporary song session expires.
- Changes are not autosaved. Explicitly save after removing audio/takes to update the saved copy. Delete project removes its saved IndexedDB copy; exported downloads are not deleted.
- Portable JSON export includes retained WAV audio. Imports are size/schema bounded, never executed, and get a new ID rather than overwriting an existing project. Maximum 600-second reference, 30,000 reference notes, 100 sections, 50 takes, 50 MB retained audio plus an optional 8 MB chart, 80 MB import/export. Export fails explicitly if the complete JSON exceeds 80 MB; remove older audio before retrying.
- Progress is compared only across identical phrase boundaries, practice speed, reference revision and detector label. The history table shows review coverage and confirmed/dismissed/unsure counts. Unrelated imported review keys do not count. Count-based change commentary is withheld until both reports have no unresolved findings or alignment warnings. Counts concern detected findings, not false negatives or a universal ability/accuracy score. With retained audio, play previous → current take directly.
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
- `BROWSER_EXECUTABLE_PATH=/path/to/chromium npm run test:reference-editor` (synthetic fixture; editor, portable chart and coverage-aware progress checks)
- `BROWSER_EXECUTABLE_PATH=/path/to/chromium npm run test:practice` with the frontend and API running

Browser smoke uses an actual browser/fake microphone and **mocked comparison responses**. It verifies chart entry, reference/exclusion gates, capture, review playback, focus/retry, IndexedDB reload including audio, portable export, correction revision and deletion. It is not a transcription or real-guitar accuracy test.

## Recording readiness and listening-only reviews

### Signal checks, not technique judgements

Use **Check recording input before practising → Check input for 3 seconds**. Play normally, wearing headphones. This captures a short local test, plays no guide, sends no audio to the Python engine and retains no test recording. It reports peak, average RMS level (dBFS) and fraction of samples reaching ±0.999. The microphone is released afterwards.

Every new recorded/uploaded take also stores the same signal-health summary:

- `no_signal`: peak below 0.0002 and RMS below −75 dBFS. The take is **not sent for comparison**; check input selection/cable/gain and retry. It can still be retained for inspection if audio retention was enabled.
- `low_level`: RMS below −45 dBFS (excluding no-signal). This is a caution, not a hard gate: rests, intentional quiet playing and capture distance also affect it.
- `ceiling`: at least 2% of samples at absolute amplitude ≥0.999. This is a caution, not proof of ADC clipping: intentional effects may create the same waveform.
- `usable`: no basic level problem detected. This does not prove clean capture, correct tuning, successful separation, calibrated latency or accurate transcription.

Low-level/ceiling takes may still be compared, but automatic focus suggestions and count-based progress commentary are suppressed pending listening review. Old takes without metadata are explicitly labelled “not checked”. These thresholds are transparent engineering heuristics, not independently calibrated guitar-quality metrics. No denoiser, noise-floor estimator or new detector tuning is implied.

### Prediction-free reviewer packets

1. Enable audio retention **before** recording/uploading a take. Its reference revision must still match the current project.
2. Under **Listening-only teacher/reviewer packet**, choose **Export listening-only packet**. Get permission before sharing recordings.
3. Save the project to retain its packet-ID/checksum-to-take audit mapping. At most 20 packets can be exported per take; reuse an existing packet file for multiple reviewers. The packet deliberately omits project title/goal, other takes, app predictions, scores and existing finding labels.
4. Ask a reviewer who has not seen the app findings to open **Open listening-only reviewer** (the separate `?listening-review` entry point) and load the packet. This entry point does not mount the practice app or make model/API requests.
5. The reviewer hears the retained take and a synthesized reference-note guide, declares a pseudonym and whether they have seen app predictions, then annotates time intervals as pitch/timing/missing/extra/sustain/noise/correct-region/uncertain. They can mark whether they listened through the whole take.
6. Export the labels before closing; there is no autosave. Saved labels can be restored only for the matching packet ID and checksum. Match returned labels to the saved take mapping before external evaluation.

The packet is whitelist-only and SHA-256 binds its audio, note reference and timing map. A checksum detects changes; it is **not** proof of authenticity, reviewer expertise or independence. Full original-song audio is not supplied: the reference guide may contain transcription errors and is clearly labelled as such. An unreviewed reference remains labelled unreviewed. No predictions are revealed after annotation.

Review exports always keep `independent_ground_truth: false` and include self-declared exposure, whole-take coverage, reviewer pseudonym and packet checksum. A separate audit must establish consent, performer/source independence, reference validity and annotation quality. No accuracy metric is calculated by this tool, and returned labels do not automatically alter app findings or count as holdout approval. Use the existing fail-closed holdout protocol for any engine-quality claims.

Limits: packet ≤45 MB, WAV take ≤30 MB, take ≤120 seconds, reference ≤5,000 notes, ≤1,000 annotations, comment ≤1,000 characters. Packets and labels stay local unless explicitly downloaded/shared. Neither the preflight nor the reviewer workflow was validated with physical USB hardware or independent human participants in this feature follow-up.

Verification: `npm run test:listening-review` uses synthetic silent/tone WAVs, a fake microphone and a mocked comparison response. It verifies that silent input makes zero inference requests, packet export contains no predictions, the isolated reviewer makes zero API calls, labels export/restore correctly and modified packets fail checksum checks. This is workflow verification, not transcription accuracy evidence.

## Actual accuracy evaluation

The [practice-feedback accuracy suite](benchmarks/practice_feedback/README.md) runs the real comparison API and Basic Pitch on the bundled unchanged GuitarSet recordings, with dataset-note F1 and real-audio transcription-self-check diagnostics. This is development regression evidence, not a new independent holdout. The same suite can audit/import listening-only reviewer exports and run independent issue-event metrics only after the frozen coverage and separate human-audit gates pass. Current independent intake is empty and exits 3 without importing a model. See the linked protocol and recorded results before describing any pass as independent accuracy.

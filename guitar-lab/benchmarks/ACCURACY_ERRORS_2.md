# Guitar Lab accuracy round 2 (5 Nov 2026, Europe/London)

Base: adaptive ghost gate (`accuracy-fixes.patch`) on main after PR #46. This branch also includes PR #47 (take-vs-target comparison). That comparison does not change these transcription numbers.
Harness: `acc2/` (cache.py, harness.py, promote*.py, harm*.py, subdrop.py, fing*.py, nin.py, verify.py).
Metric: mir_eval note onset F1, exact pitch, offsets ignored, ±50 ms / ±100 ms. Guitar-TECHS uses a per-clip
`best_shift` computed on the **baseline** and frozen for every variant. Carcassi ref is DTW-aligned with
`evaluate.py` (this run's baseline 0.645, vs 0.623 earlier with the old alignment path).
Split: Guitar-TECHS P3 amp odd songs = tuning, even songs = held-out. DI, GuitarSet 20 (seed 42) and Carcassi = checks.

## Patches
- `accuracy-fixes-2.patch` — full diff vs origin/main (includes the ghost gate from accuracy-fixes.patch).
- `accuracy-fixes-2-incremental.patch` — only this round, on top of accuracy-fixes.patch.
- Author's `pytest server/tests -q` on the pre-#47 tree: **111 passed, 1 skipped**. `npm test` was not run there (no TS changes in that patch). On this branch, after merging PR #47: `pytest server/tests -q` **123 passed, 2 skipped**; `npm test` **52 passed**.

## 1. Selective candidate promotion — KEPT, default on (`FRETWORK_PROMOTE=0` disables)
Second Basic Pitch pass at 0.3/0.2. A candidate is added only if: BP amplitude ≥ 0.35, pitch already used in the part,
an audio onset peak within ±50 ms, harmonic-series energy at that pitch rises ≥1.5× across the onset, not a
partial (+7/12/19/24/28/31) of a kept note, not a ±1–2 st neighbour, not a re-trigger of a sustaining same pitch; cap 30% adds.
Rule-based, no learned filter. Applied after suppress/drop_overtones in `songs.py`.

| Variant (F1@50 / F1@100) | amp tune (6) | **amp held (6)** | DI (12) | GuitarSet 20 | Carcassi |
|---|---|---|---|---|---|
| Baseline (ghost gate) | .6731/.6780 | .6771/.6800 | .6601/.6667 | .8213/.8263 | .6448/.7022 |
| **Promote (shipped)** | .6788/.6860 | **.6913/.6965** | .6664/.6748 | .8285/.8365 | .6441/.7009 |
| Promote, amp ≥0.3 (best tune) | .6790/.6878 | .6918/.6976 | .6661/.6744 | .8241/.8328 | .6398/.6962 |
| Promote, no amp gate | .668–.674 | .678–.685 | ≤.661 | .78–.81 | .58–.64 |
| Promote, no vocab gate | lower everywhere | | | | |
| Promote, distorted/crunch only | .673 | .685 | .664 | .8213 | .6448 |

0.35 chosen over 0.3 because Carcassi fell .005 at 0.3. NIN false-chord fraction (7 stems, 60 s): unchanged
within ±0.006 (Chorus_Gtr 0→.006, Echoplex_outriff 0→.006, Riff_Mutated .062→.056).
Cost: one extra Basic Pitch pass + an STFT per part (~2× transcription time) — not timed in the app.

## 2. Distorted harmonic-series pitch pick — FAILED; replaced by sub-partial drop (opt-in)
Moving a note to {+7, +12} when its fundamental is weak never helped (best = no change; looser = −0.01 to −0.015).
Diagnosis on distorted clips: of base notes that are a fifth/octave/fourth below a true note, **~95% are duplicates**
(true note already transcribed: +7_dup 67, +5_dup 42, +12_dup 37, +19_dup 21 vs +7 alone 1, +12 alone 9).
So "other_pitch" is mostly extra sub-partial ghosts, not wrong picks. Fundamental ratio e0/e(m+7): ghosts median 1.3, real notes 17.
`drop_sub_partials` (distorted only): drop a note if a note +7/+12/+5/+19 above starts within 50 ms and its own fundamental < the upper note's.

| Variant | amp tune | amp held | DI | GS20 | Carc |
|---|---|---|---|---|---|
| Baseline | .6731 | .6771 | .6601 | .8213 | .6448 |
| Pitch move ±7/12 (any ratio) | ≤.6731 | ≤.6771 | ≤.6601 | = | = |
| Sub-partial drop r=1.0 | **.6891** | .6767 | .6648 | = | = |
| Sub-partial drop on all tones | .6809 | .6751 | .6692 | **.7633** | .6316 |
| Promote + sub-partial drop | .6945/.7022 | .6918/.6971 | .6712/.6813 | .8285 | .6441 |

Tuning gain did not transfer to held-out amp (−0.0004) → shipped **off** (`FRETWORK_SUBPARTIAL_DROP=1`).
It did cut NIN Gtr_Riff false chords .134 → .093. Clean tone is never touched.

## 3. Tab (string/fret) — KEPT but opt-in (`FRETWORK_FINGERING=prior`)
New Viterbi: 4-fret hand window (move only when a note falls outside it) + per-pitch string prior counted from GuitarSet
players 00–02 only (`server/string_prior.json`, CC BY 4.0 attribution in file). Other tunings keep classic costs.

| Fingering on TRUE notes (GuitarSet 360) | players 00–02 (tune) | **players 03–05 (held)** | all |
|---|---|---|---|
| Classic (current) | .6252 | .5754 | .6003 |
| Window only, no prior | — | .6042 | — |
| **Window + prior 0.5** | .7445 | **.7136** | .7290 |
| + open-string bonus −0.5 | .7041 | .6705 | — |
| String-jump cost, move 0.8 | ≤.744 | .70–.718 | — |
| Oracle: true assignment among the candidate options | | | **.9993** |

End to end (GuitarSet 20, exact string+fret on pitch/onset-matched engine notes): classic **.556** → prior **.674**
(window-only .534). Caveat: the 20-file sample mixes tune and held players.
Why opt-in: GuitarSet players (jazz/funk/bossa) avoid open strings, so the prior moves open-position parts up the neck
(open E → B string fret 5; F on B-6 instead of E-1). The existing Carcassi and A-minor-arpeggio regression tests fail with
it, and adding an open-string bonus still fails them while losing ~4 points. Needs a style switch (classical/folk vs
plectrum/jazz) or a better tab truth set before going default. Gap to oracle: candidates are not the problem (.999
coverage); the cost model is (held .714 vs 1.0).

## Not measured / limits
- Hollow Ground, P1 techniques, EGDB-BIAS, Demucs-separated full-band songs: not re-run with promotion.
- App end-to-end (`songs.py` path) not executed on audio; the functions were verified to reproduce the harness numbers exactly, and unit tests cover the wiring indirectly only.
- Runtime cost of the extra BP pass not timed.
- Offsets/durations not scored. Held-out sets are small (6 amp clips); no significance test was run.
- Carcassi tab correctness has no ground truth (Mutopia MIDI has no strings).
- IDMT not used this round.

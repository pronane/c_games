# Guitar Lab accuracy error analysis (5 Nov 2026, Europe/London)

Focus: **guitar notes only**. Goal: get transcription (notes, timing, tab) as close to 100% as possible against real MIDI. The 7 product requirements already roughly work; accuracy is the bottleneck.

Workspace data under `/workspace/guitar-lab-test/` (`cands.pkl` from the clean-model harness, Guitar-TECHS, Hollow Ground, Carcassi, GuitarSet). The kept fix is adaptive ghost suppression in `server/song_analysis.py`. The patch was written against `origin/main` @ 48823af and applied on current main after PR #46 (advisory fingerprint and opt-in `clean_model`). Those paths are unchanged; the learned `clean_model` filter stays off.

## Baseline F1 (engine default, onset/frame via `thresholds_for`)

| Set | n | F1@50 | F1@100 | notes |
|-----|---|-------|--------|-------|
| Guitar-TECHS P3 **amp** (real MIDI) | 12 | **0.667** | 0.672 | after per-clip `best_shift` (~+13–25 ms MIDI lag) |
| Guitar-TECHS P3 **DI** | 12 | 0.660 | 0.667 | same |
| Guitar-TECHS P3 amp **held-out even songs** | 6 | 0.661 | — | used for fix decisions |
| Guitar-TECHS P1 techniques amp | 5 | 0.518 | 0.534 | bends/harmonics/palm-mute… |
| Hollow Ground amp vs DI-engine labels | 5 | 0.448–0.478 | ~0.49 | not true MIDI; DI transcription as pseudo-GT |
| Carcassi Op.60 No.1 (Mutopia MIDI, DTW-aligned) | 1 | **0.623** | 0.675 | clean nylon |
| GuitarSet mic sample (20 files this run) | 20 | **0.821** | — | full 360-file official bench was F1 **0.80** |
| GuitarSet tab exact on matched notes (20) | 20 | — | — | **0.56** (fingering-on-true-notes 0.59) |

Oracle note: filtering Basic Pitch candidates perfectly on the same pool would score ~0.85–0.92 on amp clips (prior clean-model ceiling). **Choosing which candidates are real notes remains the main gap**, not raw candidate recall. The learned `clean_model` filter was net **worse** on real MIDI and stays off.

## Error taxonomy (share of unmatched events)

Matching: mir_eval note onset ±50 ms, exact MIDI pitch, offsets ignored. Per-clip constant `best_shift` applied for Guitar-TECHS (annotation lag vs audio). Categories are counted on unmatched est/ref notes (not mutually exclusive with merge/split heuristics).

### Guitar-TECHS P3 amp (12 clips, primary)

| Category | count | share | approx. what-if micro-F1 if fixed |
|----------|------:|------:|-----------------------------------:|
| **missed_onset** | 436 | **43.3%** | 0.67 → ~0.81 |
| **other_pitch** | 275 | **27.3%** | (mixed intervals; see below) |
| **extra_ghost** | 112 | 11.1% | → ~0.69 |
| **wrong_octave** | 76 | 7.5% | → ~0.70 |
| **split_notes** | 53 | 5.3% | small |
| **semitone** | 22 | 2.2% | small |
| **merged_notes** | 19 | 1.9% | small |
| timing-only (50–100 ms) | 15 | 1.5% | small |

Chord confusion (onset groups ±50 ms): `gt_single_est_chord` **222**, `gt_chord_est_single` 83, both_single 665, both_chord 140. Engine still invents chords on mono lines more often than it collapses real chords.

**other_pitch interval histogram** (est−gt at same onset; P3 DI+amp combined, n=642): dominated by **−7** (76), **−5** (62), **−3** (60), **−9** (54), **−4** (52), **−19** (43). Many look like sub-fifth / wrong-partial picks rather than random noise. Fifths-class (±7 mod 12) ≈ 129; thirds-class ≈ 281.

### Guitar-TECHS P3 DI

Similar shape: other_pitch 36%, missed 33%, ghosts 11%, octave 7%, splits 6%. Residual timing after shift: median ≈ **−14 ms** (est still slightly early vs MIDI).

### Guitar-TECHS P1 techniques (amp)

**extra_ghost 62%** (technique artefacts: harmonics, pinch, vibrato confuse BP), missed 20%, other_pitch 7%. Large MIDI lag (~44 ms) before shift.

### Hollow Ground amp vs DI labels

**missed_onset 62%**, ghosts 16%, other_pitch 5%, octave 4%. Chord collapse: `gt_chord_est_single` 70 vs `gt_single_est_chord` 3 — amp path under-detects polyphony relative to DI labels. Treat as soft labels only.

### Timing distribution (matched notes, after best_shift)

| Set | median onset error | p95 | notes |
|-----|-------------------:|----:|-------|
| P3 amp | ≈ −6 ms | ≈ +9 ms | after ~+19 ms mean shift |
| P3 DI | ≈ −14 ms | ≈ 0 ms | after ~+13 ms mean shift |
| Hollow | ≈ +6 ms | ≈ +35 ms | no MIDI shift |
| Raw P3 amp **without** shift | ≈ **−25 ms** | — | systematic MIDI/audio lag |

`dur` refinement does not move onset F1 (offsets not scored). Bad-duration counts among matches are non-zero but secondary for current metric.

### Tab (GuitarSet)

On 20 random mic files: note F1 0.82; among pitch-matched notes, exact string+fret **0.56** (fingering alone on true MIDI notes 0.59). Large remaining tab gap even when pitch is right — separate from note F1.

## Prototypes tried (held-out / clean checks)

All scored with per-clip `best_shift` unless noted. Clean sets = Carcassi (DTW) + GuitarSet sample.

| Fix | P3 amp held F1@50 | Clean / other | Verdict |
|-----|------------------:|---------------|---------|
| **Adaptive ghost suppress** (`max_drop_frac=0.15`: if cleanup drops >15% of notes, keep raw) | **0.661 → 0.677** (+0.016); all-amp 0.667→0.675 | GuitarSet unchanged 0.819; Carcassi 0.623 unchanged; Hollow unchanged; NIN false-chord frac stayed **0.0** (vs 0.023 with suppress fully off) | **KEEP** |
| Global/audio lag calibration (onset-envelope median) | +0.008 only when **not** using best_shift; with aligned MIDI ≈ flat/down | GuitarSet slight down | **drop** |
| Oracle +25 ms constant shift | 0.658 (helps TECHS MIDI) | Hollow / GuitarSet down | **drop** (dataset-specific annotation lag) |
| Spectral octave snap (±12, ratio 2.5) | down (~0.65) | GuitarSet down | **drop** |
| Fifth-up snap (midi+7 when spectrum prefers) | down hard when it fires | — | **drop** |
| Merge split sustains | ~flat / slight DI up | GuitarSet down | **drop** |
| Snap each onset to envelope peak (±30 ms) | down | GuitarSet down | **drop** |
| Fill missed onsets (yin on empty peaks) | down (loose) / ~flat (tight, ~0 adds) | — | **drop** |
| Duration-by-energy decay | flat (onset F1) | — | not for onset metric |
| Lower BP thresholds (0.55/0.35, 0.5/0.3, …) | all down (P falls more than R rises) | GuitarSet down | **drop** |
| Disable suppress entirely | amp held 0.676 | NIN chord frac 0→0.023 | **drop** (adaptive gate captures the win without NIN regression) |
| Learned clean_model filter | prior: P3 amp 0.667→0.623 | — | already off; **do not pursue** |

## Kept change (in patch)

`server/song_analysis.suppress_harmonic_ghosts(..., max_drop_frac=0.15)`  
After classify_onset + reverb-tail cleanup, if more than 15% of notes would be removed, return the pre-cleanup list. Default on. Pass `max_drop_frac=None` to force cleanup (unit tests with synthetic 3× ghost loads do this).

**Why it helps:** on Guitar-TECHS P3_08 amp, full suppress removed ~24% of events that were mostly real notes (F1 0.57 vs 0.66 with no suppress). The gate reverts that clip only (1/24 P3 DI+amp clips). NIN mono stems still fully suppress (drop fraction stays under the cap) so false-chord rate remains 0.

## Not measured / limits

- Full GuitarSet 360 re-run after the gate (12–20 file smoke only; clean tone skips suppress so F1 identical by construction).
- EGDB-BIAS, multi-effect chains, Demucs-separated full-band with the gate.
- Real cover/live fingerprint cases (out of scope here).
- Offset/duration F1 (onset-only metric used throughout).
- Carcassi absolute F1 without DTW is meaningless (score MIDI vs performance needs warp; DTW gives 0.623).
- Hollow Ground labels are DI-engine notes, not published MIDI.
- IDMT used only previously for FX ID; not redistributed.
- Tab string/fret errors not fixed this turn.
- Parallel “take vs target” learner-compare UI is a separate cloud-agent track.

## Recommended next experiments

1. **Missed-onset recall without drowning precision** — selective candidate promotion (high onset posterior + yin agreement + not a partial of a kept note). Prior GBDT filter failed; try a 2–3 rule gate scored on P3 held-out + GuitarSet.
2. **other_pitch / −7 cluster** — joint pitch+amp decision at each onset (pick the MIDI with strongest harmonic series among {reported, ±7, ±12}), gated by tone=distorted and measured so clean nylon never moves.
3. **Tab positioner** — GuitarSet string accuracy ~0.56–0.60; improve Viterbi costs (hand stretch, repeated-string bias) independently of note F1.
4. **Retry-until-match loop** — render estimated notes (Karplus / clean guitar), compare to upload with the same F1 + chroma DTW, nudge thresholds/suppress only when the adaptive gate or candidate rules improve the score (needs the compare harness from the parallel track).
5. Do **not** spend more time on global constant time-shifts or broad spectral octave rewrites; they regress clean sets or only fit Guitar-TECHS MIDI lag.

## Patch / tests

- Category helper: `benchmarks/accuracy_errors.py` (mir_eval note matching).
- `pytest server/tests -q` on the patched tree.
- Raw analysis JSON from the local run (not committed): `accuracy_errors/summary.json`, `ab_v2.json`, `suppress_ablation.json`.

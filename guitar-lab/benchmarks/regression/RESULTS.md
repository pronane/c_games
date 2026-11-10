# Transcription regression

Basic Pitch is the in-app default. Other backends are opt-in (`FRETWORK_TRANSCRIBER`) unless the decision below says otherwise.
Charts are not an input to any model. The Metallica intro uses the frozen alignment (tab 0 = 19.3 s), not a whole-song F1 search.

## Coverage

- guitarset: present
- idmt: present
- user_reverb_pair: present
- metallica: present
- carcassi_audio: not available
- egdb: not available

## Category means

| backend | clean_electric | full_band_intro | rendered | reverb_clear | solo_acoustic |
| --- | --- | --- | --- | --- | --- |
| basic_pitch | 0.824 | 0.083 | 0.971 | 0.703 | 0.815 |
| riley | 0.902 | 0.119 | 1.000 | 0.583 | 0.888 |
| gaps | 0.899 | 0.121 | 0.572 | 0.637 | 0.870 |

## Decision

- `riley` stays opt-in.
  - loses reverb_clear: 0.583 vs Basic Pitch 0.703 (-0.120)
  - unmeasured: amp-distorted electric (EGDB clean/amp pairs were not obtainable)
  - unmeasured: Carcassi Op.60 No.1 recording (aligned MIDI only; audio not located)
  - mean category delta vs Basic Pitch: +0.019
- `gaps` stays opt-in.
  - loses rendered: 0.572 vs Basic Pitch 0.971 (-0.399)
  - loses reverb_clear: 0.637 vs Basic Pitch 0.703 (-0.066)
  - unmeasured: amp-distorted electric (EGDB clean/amp pairs were not obtainable)
  - unmeasured: Carcassi Op.60 No.1 recording (aligned MIDI only; audio not located)
  - mean category delta vs Basic Pitch: -0.059

## YourMT3+ (YPTF.MoE+Multi, noPS), added separately

Run on another machine from the table above (then as a separate program; it now runs in the engine from `server/yourmt3` and gives identical scores). The user reverb pair and the
Metallica intro were not on that machine, so those two categories are **unmeasured** for YourMT3+.
Basic Pitch was re-run on the same machine and matched the committed numbers.

| backend | clean_electric | rendered | reverb_clear (synthetic pair only) | solo_acoustic |
| --- | --- | --- | --- | --- |
| basic_pitch | 0.824 | 0.971 | 1.000 | 0.815 |
| riley (from above) | 0.902 | 1.000 | — | 0.888 |
| yourmt3, all pitched notes | 0.880 | **0.606** | 1.000 | **0.917** |
| yourmt3, guitar-labelled only | 0.863 | 0.606 | 0.955 | 0.917 |

- Best of all backends on real acoustic guitar: rock solo 0.929, funk solo 0.889 and jazz comping 0.934, against Basic Pitch's 0.873, 0.761 and 0.810.
- On IDMT clean electric it sits between Basic Pitch and Riley. The biggest gain is on quintfall: 0.853 against Basic Pitch's 0.667.
- It fails the app's own rendered voice. On the clean scale it writes nothing for the five lowest notes (E2 to B3), scoring 0.545. On the distorted palm-mute chug it adds an octave above every note, scoring 0.667.
- Keeping only guitar-labelled notes never helps here: it drops correct notes that were labelled as another instrument.
- CPU: 70–298 s per minute of audio at fp32, about 50–100× Basic Pitch. Short clips are dominated by the fixed per-segment cost.
- Decision: **opt-in only**. It loses the rendered category by 0.365 and has two unmeasured categories. It is now built into the engine and selectable from the Note detector drop-down.

## Riley inside the engine, with the reverb fix

Riley now runs from `server/riley` (adapted from the MIT code) on the engine's own PyTorch, and is
selectable per song or practice take from the studio's **Note detector** drop-down.
Reverb tails were re-triggering Riley's onset head: on wet audio it wrote 2–9× too many notes.
The decoder now picks its onset threshold per file from how much the note count swells between
0.3 and 0.65: 0.5 when it barely changes (dry), 0.65 when it balloons (heavy reverb).

Known-note clips (3 GuitarSet + 5 IDMT) through synthetic rooms, note F1:

| | dry | room (RT60 0.8 s) | hall (2.0 s) | wash (3.5 s) |
| --- | --- | --- | --- | --- |
| Basic Pitch | 0.821 | 0.736 | 0.579 | 0.422 |
| Riley, published decoder | 0.897 | 0.851 | 0.585 | 0.259 |
| **Riley, reverb-aware** | **0.905** | **0.879** | **0.801** | **0.587** |

Library categories with the new decoder: solo acoustic 0.908 (was 0.888), clean electric 0.902,
rendered 1.000. GAPS keeps its published decoder. The real reverb pair and the Metallica intro were
not on this machine, so Basic Pitch stays the default until those are re-measured.

## Metallica intro re-timed (beat-tracked tempo)

The chart is written at 108 BPM, but the recording's intro plays at **99.4 BPM**. A beat tracker
on the audio gives 99.4 BPM over 19 s and 41 s windows, starting from either a 100 or a 108 prior.
Scored at 108, the reference drifted about 0.7 s by the end of the window, so every detector got
about 0.1. Tab 0 is now placed by lining up the chart's onset times with the audio's onset envelope,
which is pitch-blind and ignores every detector's notes. It lands 0.95 s before the old chroma anchor.
An F1 search over stretch and offset picks the same map for all three detectors (stretch 1.085–1.09,
offset −0.94 to −1.02), but it was only used as a cross-check.

| backend | intro note F1 | precision | recall |
| --- | --- | --- | --- |
| Basic Pitch | 0.458 | 0.330 | 0.750 |
| **Riley** | **0.873** | 1.000 | 0.775 |
| GAPS | 0.845 | 0.968 | 0.750 |
| YourMT3+ | 0.566 | 0.455 | 0.750 |

Riley now wins every measured category. The real reverb/clear pair still can't be scored,
because only the reverb take (take A) is on this machine. On take A, Riley's reverb check reads
heavy reverb: it finds 6.7× more onsets at threshold 0.3 than at 0.65, so it decodes at 0.65.
That is the same note explosion behind the old 0.16–0.18 result.

## Whole song: tab-named parts on One (private recording + tab)

`server/tab_align.py` lines the user's tab (5 guitar tracks, repeats played out) up with the full
recording. Over the intro the map is 0.17 s out on average against the beat-tracked reference.
Riley ran on the Demucs guitar stem, and its notes were scored against all five tab guitar parts.

| stretch | Riley note F1 | precision | recall |
| --- | --- | --- | --- |
| 0:00–3:30 (clean / acoustic) | 0.654 | 0.80 | 0.55 |
| 3:30–7:30 (heavy, distorted) | 0.027 | 0.16 | 0.01 |

The heavy half fails on transcription, not alignment. A local ±2.5 s shift search per 30 s
window never lifts F1 above 0.08. Riley writes 25–35 notes per 30 s there, where the tab has
about 400. At onset threshold 0.3, which writes ~5× more notes, it still reaches only F1 0.10
there. Basic Pitch scores 0.056 there and 0.511 in the first half.

Riley's reverb check also fires on this dry studio stem. Distortion swells the onset count
just as reverb does, so 74% of 20 s stretches decode at 0.65. A fixed 0.5 would score 0.695
in the first half. The check now decides per 20 s stretch instead of per file, which leaves the
simulated-room results unchanged. Telling reverb apart from distortion is still open.

## Tempo: double/half-time check against the mix

The breakdown takes its tempo from the drum and bass stems. On busy hi-hats that can lock onto
double time: one user song read 184.6 BPM, while its published tempo is about 97. The
drum-based estimate is now checked against the full mix. The candidates are both estimates
and their halves and doubles, scored on how strongly the mix repeats at the beat and at the
bar, with a gentle preference for 70–160 BPM.

| song (user files, full breakdown path) | listed | before | now |
| --- | --- | --- | --- |
| slow grunge ballad | ~97 | 184.6 | **94.9** |
| power ballad | 140 | 136.0 | 143.6 |
| hard-rock ballad | ~91 | 90.3 | 90.3 |
| post-grunge single | 146 (one site) | 129.2 | 129.2 (not an octave error; unresolved) |

GuitarSet, 360 clips with the tempo in each file name (mix only): correct within 4% went from
62.2% to 65.0%. Double-time errors fell from 7.5% to 2.8%, and half-time errors rose from 3.1%
to 5.3%. The rest are mostly 3:4 / 4:3 confusions in funk and jazz comping.

## Reverb vs distortion: a negative result

Note tails were measured in dB/s at each note's own pitch over the 300 ms after it ends:

- Clean clips: dry −50 to −65, simulated hall −9 to −17, very wet −3 to −5.
- One's dry studio guitar stem: −13. Distortion sustains like a hall.
- The heavy half: −7.
- The user's reverb take: −9.

So tail decay cannot separate them either, and neither can the onset swell or the tone
estimate. Riley keeps the per-20 s onset-swell rule. Its known cost is the dry first half of
One: 0.654 against 0.695 with a fixed 0.5.

## Heavy sections: not a separation leak

In One's heavy half the Demucs 'other' stem is silent (RMS 0.000 against 0.191 for guitar),
so the guitar is not leaking into 'other'. Riley's note F1 against the aligned tab:

| input | onset | 0–3:30 | 3:30–7:30 |
| --- | --- | --- | --- |
| guitar stem | 0.5 | 0.695 | 0.082 |
| guitar + other | 0.5 | 0.692 | 0.083 |
| guitar + other | 0.3 | 0.660 | 0.105 |
| full mix (no separation) | 0.5 | 0.604 | 0.027 |

Separation is doing its job: it beats the raw mix in both halves. The failure is
transcription of dense, double-tracked high-gain playing (the chart's tempo jumps to 216 BPM
there). No released transcriber here was trained on that. The realistic fix is training data:
amp-rendered guitar from tabs with known notes, which the app can already render, used to
fine-tune Riley.

## Fine-tuning Riley on amp-rendered guitar: not adopted

The model was fine-tuned for 330 steps on 1,441 ten-second segments:
- GuitarSet players 00–04, re-amped through random crunch and high-gain chains.
- Original double-tracked riffs, rendered with a plucked-string model.
- The front end was frozen; 14.1M of 24.7M parameters were trained.

Held-out loss on the same kind of data fell from 0.0445 to 0.0293. On One, it got worse:

| Checkpoint | Clean half (0.5) | Heavy half (0.5) | Heavy, best threshold |
|---|---|---|---|
| Released | .695 | .082 | .104 (0.2) |
| Step 110 | .673 | .063 | |
| Step 220 | .663 | .040 | |
| Step 330 | .662 | .054 | .101 (0.1) |

The heavy half of One (aggregate, released model, threshold 0.5):
- **Note counts:** 1,273 notes heard against 4,762 in the tab.
- **Timing:** onset F1 is .45 when pitch is ignored, so the notes are found roughly in time.
- **Pitch:** pitch-class F1 is .22 and note F1 is .08. Pitch is where it fails: the heard median is MIDI 55, the tab's is 47, so the model is hearing distortion overtones and octaves.

Fine-tuning made the model more cautious (504 notes heard) without fixing pitch. The synthetic amp chains and plucked-string riffs don't transfer to a real heavy record. At every threshold, no checkpoint beats the released model on the heavy half, and every checkpoint is worse on the clean half, so the released weights stay.

The tools (`training/`) and the `FRETWORK_RILEY_CHECKPOINT` override stay for later attempts with real multitrack recordings that come with tabs.

## Tab library: the user's tabs against the user's recordings (private)

Seven tab/recording pairs, scored like One: the tab is lined up with the full mix, its guitar
tracks become the reference, and the detector runs on the Demucs guitar stem. Files stay in
`data/private/songs` (not in the repo); only aggregates are reported. The tabs are fan charts
and are not assumed exact.

| Song | Recording | Tuning shift found | Band tempo vs chart | Tab guitar notes | Riley (0.5) | Basic Pitch | Right pitch within 300 ms | Best / worst 30 s |
|---|---|---|---|---|---|---|---|---|
| Down in a Hole | 2:00 clip | 0 | 94% | 691 | .400 | .294 | .59 | .44 / .37 |
| 18 and Life | 2:31 clip | 0 | 100% | 823 | .227 | .243 | .60 | .61 / .15 |
| Every Rose Has Its Thorn | 1:53 clip | −1 | 97% | 991 | .213 | .168 | .43 | .54 / .11 |
| November Rain | 8:57 | −1 | 101% | 4,601 | .167 | .146 | .35 | .31 / .00 |
| Home Sweet Home | 4:54 | 0 | 100% | 819 | .164 | .156 | .56 | .27 / .08 |
| One (new full-band GP3) | 7:26 | 0 | 97% | 4,468 | .300 | .268 | .31 | .91 / .00 |
| One (one-guitar arrangement) | 7:26 | 0 | 94% | 2,868 | .221 | .182 | .27 | .85 / .01 |

What the new material showed:
- **Clips:** three recordings are about two minutes of a longer song. The old line fit needed
  60% of the tab inside the recording and failed on them. It now scores every offset (FFT
  cross-correlation) and needs 60% of the shorter of the two.
- **Tuning:** two charts are written a half step above the record. The line-up now tries
  ±1 and ±2 semitones and takes a shift only when it fits clearly better (0.03).
- **One, new full-band tab:** the clean half averages .76 per 30 s (the GP4 gave .695 over the
  same half), so this chart is the closer reference there. The heavy half is still .07.
- **Full-band ballads score low** (.16–.40) for every detector. These numbers mix three things
  that this test cannot separate: detector misses, strummed parts written as full six-string
  chords on every strum, and guitar that Demucs leaves in other stems (piano-led songs).
  "Right pitch within 300 ms" (.35–.60) is the looser view: about half of the tab's notes are
  heard near where the tab puts them.
- **Tab-only references:** For Whom the Bell Tolls and the Alice in Chains collection have no
  recording yet, so nothing is scored for them.

Riley stays ahead of Basic Pitch on five of the seven pairs; 18 and Life is within .02.

## Real distortion pedals: what goes wrong (EGFxSet, CC BY 4.0)

EGFxSet: every note on a Stratocaster (6 strings × 23 frets × 5 pickup settings = 690 notes,
5 s each), recorded clean and through real Pro Co RAT2, Ibanez Tube Screamer and Boss BD-2
Blues Driver pedals at full gain. Not in the repo; scripts in `.scratch/egfx_*.py`.

**Single notes** (Riley, onset 0.5):

| Sound | Real note found | Notes reported per pluck | Same note re-fired later | Octave ghosts |
|---|---|---|---|---|
| Clean | 84% | 0.84 | 0 | 0 |
| Tube Screamer | 82% | 1.9 | 0.95 per pluck | 0.01 |
| Blues Driver | 89% | 4.5 | 2.6 per pluck | 0.59 |
| RAT | 94% | 4.5 | 2.8 per pluck | 0.23 |

- Wrong pitch instead of the real one is rare (under 1%). Distortion helps on the low E string
  (found 56% clean, 90% through the RAT).
- The fault is re-triggering: a sustained distorted note is reported again and again.

**Riffs spliced from those notes** (monophonic, the next pick stops the string; 4 riffs each):

| Sound | 100 BPM eighths (0.30 s) | 140 BPM sixteenths (0.11 s) | 180 BPM sixteenths (0.08 s) |
|---|---|---|---|
| Clean | | F1 .998 | F1 .985 |
| Tube Screamer | F1 1.000 | F1 .998 | F1 .983 |
| Blues Driver | F1 .752 (precision .61) | F1 .937 | F1 .914 |
| RAT | F1 .531 (precision .36) | F1 .890 | F1 .932 |

Recall stays at .93–1.00 through every pedal and tempo. Distortion on its own does not stop
Riley finding notes, even fast ones; it adds false repeats on notes longer than about 0.1 s.
So the near-zero heavy half of One (where Riley hears too *few* notes) is not explained by
distortion. The likelier cause is the dense band mix and what separation leaves in the guitar
stem.

**Re-trigger filter: not adopted.** Requiring a pick attack (onset flux, pitch-energy rise,
frame dip) before accepting a repeat of a sounding note removes at most 72% of false repeats
while dropping 7–30% of real repeated notes on real recordings (EGSet12, Guitar-TECHS,
GuitarSet). Real repeats are too common in music for that trade.

## CPU time

Seconds of wall clock per minute of audio, around the transcribe call, on this CPU. The first clip of Riley and of GAPS includes the weight load.

- basic_pitch: 0.6–3.0 s per minute of audio
- riley: 9.0–30.0 s per minute of audio
- gaps: 9.8–33.9 s per minute of audio

## Where a backend is worse on a clip

Category means hide this. A drop of more than 0.005 against Basic Pitch:

- `riley` user_reverb_w0 (reverb_clear): 0.157 vs Basic Pitch 0.379 (-0.223)
- `riley` user_reverb_w1 (reverb_clear): 0.177 vs Basic Pitch 0.434 (-0.257)
- `gaps` ks_dist_chug (rendered): 0.143 vs Basic Pitch 1.000 (-0.857)
- `gaps` user_reverb_w0 (reverb_clear): 0.319 vs Basic Pitch 0.379 (-0.061)
- `gaps` user_reverb_w1 (reverb_clear): 0.229 vs Basic Pitch 0.434 (-0.205)

## Clips

### basic_pitch

| clip | category | note F1 | onset F1 | pitch recall @300ms | cross F1 | s / min audio |
| --- | --- | --- | --- | --- | --- | --- |
| gs_rock_solo | solo_acoustic | 0.873 | 0.883 | 0.899 |  | 2.980 |
| gs_funk_solo | solo_acoustic | 0.761 | 0.814 | 0.783 |  | 0.700 |
| gs_jazz_comp | solo_acoustic | 0.810 | 0.861 | 0.794 |  | 0.640 |
| ks_clean_scale | rendered | 0.941 | 0.941 | 1.000 |  | 0.800 |
| ks_dist_chug | rendered | 1.000 | 1.000 | 1.000 |  | 1.390 |
| ks_clear | reverb_clear | 1.000 | 1.000 | 1.000 |  | 0.980 |
| ks_reverb | reverb_clear | 1.000 | 1.000 | 1.000 | 1.000 | 0.960 |
| idmt_nocturneNr2 | clean_electric | 0.756 | 0.889 | 0.850 |  | 0.670 |
| idmt_pathetique_mono | clean_electric | 0.947 | 0.947 | 1.000 |  | 0.570 |
| idmt_pathetique_poly | clean_electric | 0.750 | 0.900 | 0.833 |  | 1.230 |
| idmt_promenade_mono | clean_electric | 1.000 | 1.000 | 1.000 |  | 0.600 |
| idmt_quintfall | clean_electric | 0.667 | 0.783 | 0.862 |  | 0.600 |
| user_reverb_w0 | reverb_clear |  |  |  | 0.379 | 1.080 |
| user_reverb_w1 | reverb_clear |  |  |  | 0.434 | 1.030 |
| metallica_one_intro | full_band_intro | 0.083 | 0.206 | 0.500 |  | 1.210 |

### riley

| clip | category | note F1 | onset F1 | pitch recall @300ms | cross F1 | s / min audio |
| --- | --- | --- | --- | --- | --- | --- |
| gs_rock_solo | solo_acoustic | 0.922 | 0.942 | 0.980 |  | 17.320 |
| gs_funk_solo | solo_acoustic | 0.817 | 0.867 | 0.867 |  | 13.100 |
| gs_jazz_comp | solo_acoustic | 0.925 | 0.928 | 0.952 |  | 12.520 |
| ks_clean_scale | rendered | 1.000 | 1.000 | 1.000 |  | 13.290 |
| ks_dist_chug | rendered | 1.000 | 1.000 | 1.000 |  | 30.020 |
| ks_clear | reverb_clear | 1.000 | 1.000 | 1.000 |  | 17.900 |
| ks_reverb | reverb_clear | 1.000 | 1.000 | 1.000 | 1.000 | 17.200 |
| idmt_nocturneNr2 | clean_electric | 0.829 | 0.927 | 0.850 |  | 9.030 |
| idmt_pathetique_mono | clean_electric | 1.000 | 1.000 | 1.000 |  | 13.360 |
| idmt_pathetique_poly | clean_electric | 0.833 | 1.000 | 0.833 |  | 28.150 |
| idmt_promenade_mono | clean_electric | 1.000 | 1.000 | 1.000 |  | 16.940 |
| idmt_quintfall | clean_electric | 0.848 | 0.949 | 0.897 |  | 11.410 |
| user_reverb_w0 | reverb_clear |  |  |  | 0.157 | 25.080 |
| user_reverb_w1 | reverb_clear |  |  |  | 0.177 | 23.030 |
| metallica_one_intro | full_band_intro | 0.119 | 0.269 | 0.425 |  | 27.840 |

### gaps

| clip | category | note F1 | onset F1 | pitch recall @300ms | cross F1 | s / min audio |
| --- | --- | --- | --- | --- | --- | --- |
| gs_rock_solo | solo_acoustic | 0.907 | 0.927 | 0.950 |  | 20.320 |
| gs_funk_solo | solo_acoustic | 0.793 | 0.845 | 0.800 |  | 15.300 |
| gs_jazz_comp | solo_acoustic | 0.908 | 0.924 | 0.905 |  | 14.820 |
| ks_clean_scale | rendered | 1.000 | 1.000 | 1.000 |  | 15.200 |
| ks_dist_chug | rendered | 0.143 | 0.286 | 0.083 |  | 33.890 |
| ks_clear | reverb_clear | 1.000 | 1.000 | 1.000 |  | 18.840 |
| ks_reverb | reverb_clear | 1.000 | 1.000 | 1.000 | 1.000 | 21.490 |
| idmt_nocturneNr2 | clean_electric | 0.850 | 0.950 | 0.850 |  | 9.810 |
| idmt_pathetique_mono | clean_electric | 1.000 | 1.000 | 1.000 |  | 13.680 |
| idmt_pathetique_poly | clean_electric | 0.833 | 1.000 | 0.833 |  | 26.070 |
| idmt_promenade_mono | clean_electric | 1.000 | 1.000 | 1.000 |  | 14.110 |
| idmt_quintfall | clean_electric | 0.814 | 0.949 | 0.828 |  | 12.010 |
| user_reverb_w0 | reverb_clear |  |  |  | 0.319 | 28.090 |
| user_reverb_w1 | reverb_clear |  |  |  | 0.229 | 26.460 |
| metallica_one_intro | full_band_intro | 0.121 | 0.273 | 0.400 |  | 25.180 |

## Licenses and what was not run

- Basic Pitch: Apache-2.0, ONNX, default.
- Riley guitar-fl and GAPS: MIT weights and wrapper; Kong CRNN inference is Apache-2.0. Optional (`requirements-transcription-extras.txt`). Decoder thresholds are the published 0.3/0.3/0.1, not fit here.
- YourMT3+: built in (server/yourmt3, Apache-2.0); see its section above.
- GuitarSet excerpts: CC BY 4.0, Xi et al., ISMIR 2018. Player 05.
- IDMT-SMT-Guitar: CC BY-NC-ND 4.0. Audio is local only. These pieces are clean direct-input electric, not amp distortion.
- EGDB / EGDB-PG: the paired clean-and-amp set was not downloaded (the public FLAC bundle is 135 GB; the original set is on request).
- Carcassi: `ground_truth_aligned_to_recording.mid` is in the tree. The recording it was aligned to was not in the attachment and was not found. A different public performance was not substituted.
- Metallica and the user AAC takes: local only, not committed.

## Real miked-amp electric (EGSet12 and Guitar-TECHS excerpts)

Added as gate material. Audio is not in the repo. The numbers below are the
locked floors in `reference/electric_baseline.json`. A later transcription may
score higher. A clip that falls by more than 0.02, or a category mean that
falls by more than 0.01, fails `test_electric_sets_do_not_drop_below_the_locked_baseline`
when the files are on disk. Without the files that test skips.

Same transcribe entry as the rest of this library: Basic Pitch at 0.6/0.4, Riley
with its reverb-aware decoder. No chart is an input. Song-level ghost suppression
and missed-note pickup are not in this score. The default transcriber is unchanged.
EGDB's high-gain pairs are still unmeasured, so this does not clear that gap.

Both sets are CC BY 4.0, for evaluation only.

- EGSet12: Pedroza, Abreu, Corey, and Roman, DAFx 2024. https://zenodo.org/records/11406378. doi:10.48550/arXiv.2405.14679. All 12 miked-amp solos, no other effects. Reference is the JAMS `note_midi` annotations (one per string).
- Guitar-TECHS excerpts: Pedroza, Abreu, Corey, and Roman, ICASSP 2025. https://zenodo.org/records/14963133 and https://guitar-techs.github.io/. doi:10.1109/ICASSP49660.2025.10887996. Only `P3_music.zip` (the 12 musical excerpts, about 8 minutes). Not the 4.1 GB of techniques, chords, and scales.

The authors warn of up to 100 ms misalignment. Each clip has one frozen lag from
a pitch-blind onset-envelope correlation inside ±100 ms (`electric_alignment.json`).
It is not chosen by note F1. EGSet12 landed at +8 to +24 ms. Guitar-TECHS miked
amp landed at −5 to −21 ms (mean absolute 10.4 ms). Direct input was 13.1 ms and
no stronger, so the gate scores the miked amp. Note F1 at ±100 ms is locked
beside ±50 ms.

| backend | amp solo F1@50 | amp solo F1@100 | amp excerpt F1@50 | amp excerpt F1@100 |
| --- | --- | --- | --- | --- |
| basic_pitch | 0.828 | 0.851 | 0.663 | 0.675 |
| riley | 0.893 | 0.914 | 0.772 | 0.780 |

Riley is ahead on both sets. That does not switch the default: it was already
Riley when the package is installed, and the unmeasured EGDB and Carcassi gaps
remain.

Per clip, note F1 at ±50 ms. The ±100 ms number is in parentheses when it differs.

### basic_pitch

| clip | F1@50 (F1@100) | onset F1 | pitch recall @300ms | notes ref/est |
| --- | --- | --- | --- | --- |
| egset_01 | 0.906 | 0.906 | 0.989 | 92/109 |
| egset_02 | 0.762 | 0.767 | 0.636 | 242/162 |
| egset_03 | 0.682 (0.832) | 0.694 | 0.949 | 78/95 |
| egset_04 | 0.771 (0.792) | 0.785 | 0.671 | 170/118 |
| egset_05 | 0.902 (0.930) | 0.902 | 0.990 | 102/113 |
| egset_06 | 0.562 (0.595) | 0.648 | 0.530 | 370/238 |
| egset_07 | 0.932 | 0.947 | 0.969 | 64/69 |
| egset_08 | 0.964 | 0.964 | 0.964 | 84/84 |
| egset_09 | 0.916 | 0.916 | 0.933 | 89/90 |
| egset_10 | 0.872 (0.899) | 0.872 | 0.972 | 71/78 |
| egset_11 | 0.738 (0.757) | 0.878 | 0.845 | 103/111 |
| egset_12 | 0.929 | 0.929 | 0.951 | 82/86 |
| techs_01 | 0.764 (0.773) | 0.778 | 0.723 | 235/192 |
| techs_02 | 0.775 | 0.808 | 0.741 | 224/199 |
| techs_03 | 0.615 (0.644) | 0.664 | 0.859 | 78/130 |
| techs_04 | 0.686 (0.702) | 0.734 | 0.789 | 175/204 |
| techs_05 | 0.700 (0.722) | 0.722 | 0.750 | 88/92 |
| techs_06 | 0.662 (0.667) | 0.685 | 0.534 | 275/160 |
| techs_07 | 0.534 (0.543) | 0.552 | 0.408 | 147/74 |
| techs_08 | 0.659 (0.674) | 0.705 | 0.627 | 142/116 |
| techs_09 | 0.674 (0.682) | 0.722 | 0.836 | 104/151 |
| techs_10 | 0.521 (0.533) | 0.599 | 0.754 | 191/323 |
| techs_11 | 0.671 (0.695) | 0.695 | 0.563 | 103/64 |
| techs_12 | 0.692 | 0.704 | 0.637 | 182/139 |

### riley

| clip | F1@50 (F1@100) | onset F1 | pitch recall @300ms | notes ref/est |
| --- | --- | --- | --- | --- |
| egset_01 | 0.994 | 0.994 | 0.989 | 92/91 |
| egset_02 | 0.869 | 0.913 | 0.806 | 242/207 |
| egset_03 | 0.776 (0.921) | 0.790 | 0.936 | 78/74 |
| egset_04 | 0.931 | 0.931 | 0.876 | 170/150 |
| egset_05 | 0.956 (0.975) | 0.956 | 0.990 | 102/101 |
| egset_06 | 0.642 (0.656) | 0.688 | 0.505 | 370/200 |
| egset_07 | 0.985 | 0.985 | 1.000 | 64/66 |
| egset_08 | 0.950 | 0.950 | 0.905 | 84/76 |
| egset_09 | 0.929 | 0.929 | 0.888 | 89/81 |
| egset_10 | 0.929 (0.957) | 0.929 | 0.972 | 71/69 |
| egset_11 | 0.794 (0.813) | 0.938 | 0.854 | 103/106 |
| egset_12 | 0.958 (0.982) | 0.958 | 0.988 | 82/83 |
| techs_01 | 0.773 (0.798) | 0.798 | 0.672 | 235/161 |
| techs_02 | 0.950 (0.959) | 0.954 | 0.938 | 224/214 |
| techs_03 | 0.918 (0.932) | 0.932 | 0.872 | 78/68 |
| techs_04 | 0.869 | 0.888 | 0.823 | 175/154 |
| techs_05 | 0.797 | 0.797 | 0.670 | 88/60 |
| techs_06 | 0.656 (0.660) | 0.675 | 0.506 | 275/143 |
| techs_07 | 0.440 (0.461) | 0.461 | 0.299 | 147/44 |
| techs_08 | 0.655 (0.664) | 0.691 | 0.528 | 142/81 |
| techs_09 | 0.895 | 0.895 | 0.817 | 104/86 |
| techs_10 | 0.806 | 0.806 | 0.686 | 191/134 |
| techs_11 | 0.767 (0.779) | 0.779 | 0.660 | 103/69 |
| techs_12 | 0.733 (0.740) | 0.747 | 0.593 | 182/110 |

Download with `python -m benchmarks.regression.download` from `guitar-lab/`.

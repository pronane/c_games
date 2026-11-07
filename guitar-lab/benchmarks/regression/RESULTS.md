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

Run on another machine from the table above, with `tools/yourmt3`. The user reverb pair and the
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
- Decision: **opt-in only**. It loses the rendered category by 0.365 and has two unmeasured categories. Its code is GPL-3.0, so it runs as a separate program and is not shipped with the app.

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
- YourMT3+: checkpoints Apache-2.0 (~2.8 GB). Inference code is GPL-3.0 and is not vendored. It was not executed in this run.
- GuitarSet excerpts: CC BY 4.0, Xi et al., ISMIR 2018. Player 05.
- IDMT-SMT-Guitar: CC BY-NC-ND 4.0. Audio is local only. These pieces are clean direct-input electric, not amp distortion.
- EGDB / EGDB-PG: the paired clean-and-amp set was not downloaded (the public FLAC bundle is 135 GB; the original set is on request).
- Carcassi: `ground_truth_aligned_to_recording.mid` is in the tree. The recording it was aligned to was not in the attachment and was not found. A different public performance was not substituted.
- Metallica and the user AAC takes: local only, not committed.

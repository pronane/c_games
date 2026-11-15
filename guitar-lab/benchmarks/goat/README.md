# GOAT evaluation

Research only. [GOAT](https://doi.org/10.5281/zenodo.15690894) is CC BY-NC 4.0
(Loth, Sarmento, Sarkar, Guo, Barthet, and Sandler, ISMIR 2025). Do not commit
the audio, the tabs, or the MIDI, and do not ship weights trained on them.

The files live outside this tree. From `guitar-lab/`:

```sh
python -m benchmarks.goat --root /path/to/GOAT-parent --split train
python -m benchmarks.goat --root /path/to/GOAT-parent --split train --frame-join
python -m benchmarks.goat --root /path/to/GOAT-parent --split train --sustain
python -m benchmarks.goat --root /path/to/GOAT-parent --split test
```

`--split train` refuses the official test items 35, 60, 103, 118, 152, 156, and
166. Item 60 stays in the test split but is left out of the primary mean: its
fine-alignment is below the authors' 0.75 cutoff, which is a label-quality
decision, not a detector score. `--split test` prints the held-out scores. It
is not a place to choose a threshold.

A cropped item is scored from `audio_and_midi_crop` and that directory's
time-adjusted fine MIDI. `original_full_references` is the uncropped chart and
is not the timing reference. The fine MIDI's 120 BPM and 220 ticks per quarter
are the file's clock, not the musical tempo.

`item_*_gp.wav` / `.flac` is the Guitar Pro synthetic render. It is not one of
the five amplifier renders. Those renders are a random NAM profile plus a
cabinet impulse, with a room-reverb send on about a quarter of them. They are
not chorus, phaser, delay, or wah.

`--frame-join` repeats a same-pitch frame-dip comparison (cut 0.85, gap 0.20 s).
It is not the app decoder. See the result below.

## What the default decoder scored

Riley was not changed. Note F1 is exact pitch with offsets ignored. `offset_f1`
also requires the offset within 20% of the reference duration. Each item's DI
and five NAM amplifier renders are averaged together. The Guitar Pro render is
not in the mean. These are the files on disk for this pass: six 30 s crops and
one full short take (item 166, 28.052 s), not the full-duration GOAT test set.
Those official items are standard tuning, player 1: six Stratocasters and one
Jazzmaster (item 35). Train item 5 is downtuned and train item 101 is player 2.
They add a little development variety. They are not held-out evidence for other
guitars, tunings, players, or pedal effects.

Official primary test (items 35, 103, 118, 152, 156, 166; 36 signals), one pass,
thresholds left as they were:

| | F1@50 | precision | recall | F1@100 | offset F1 |
| --- | --- | --- | --- | --- | --- |
| DI only (6) | 0.756 | 0.751 | 0.761 | 0.884 | 0.574 |
| amplifiers (30) | 0.563 | 0.596 | 0.561 | 0.623 | 0.295 |
| primary mean | 0.595 | 0.622 | 0.595 | 0.666 | 0.341 |

Onset F1 at 50 ms on that primary mean is 0.629, and pitch recall inside 300 ms
is 0.695. The amplifier mean is what pulls both down.

Item 60 (alignment 0.746) is reported apart from that mean: F1@50 0.487 across
its DI and five amplifiers. It was not used to choose anything.

Item 35's DI is 0.122 at 50 ms and 0.875 at 100 ms, with pitch recall 0.873
inside 300 ms. Four of its five amplifiers also lose pitch at 300 ms (0.22 to
0.37). The crop's own alignment is 0.793. The reference was not shifted.

Train items 4, 5, 46, and 101, same metric, default decoder: mean F1@50 0.577,
F1@100 0.598, offset F1 0.279 across 24 signals. That split is for development.
It is not a second test score.

## Sustain rule, measured and not adopted

A same-pitch onset inside 0.12 s is joined when the frame posterior between the
two onsets falls below 0.80. Separately, a 20 s stretch uses onset 0.65 when at
least 70% of the notes present at 0.5 and missing at 0.65 are same-pitch
neighbours, and it keeps onset 0.5 when the reverb ratio said wet but fewer
than 40% of those notes are. Both cuts were read off the train items only
(4, 5, 46, 101). Held-out items were not scored and were not used to choose
the cuts. `--sustain` repeats the comparison. The app decoder does not call it.

Note F1, exact pitch, offsets ignored:

| | F1@50 before | after | F1@100 before | after |
| --- | ---: | ---: | ---: | ---: |
| DI (4) | 0.877 | 0.877 | 0.908 | 0.908 |
| amplifiers (20) | 0.517 | 0.589 | 0.536 | 0.610 |
| all 24 | 0.577 | 0.637 | 0.598 | 0.660 |

No train file's F1@50 or F1@100 fell. The gains are item 4 amplifiers 2 and 3
(0.876 to 0.919, 0.736 to 0.955), item 46 amplifiers 3 and 4 (0.233 to 0.432,
0.448 to 0.517), and item 101 amplifiers 2 to 5 (0.296 to 0.462, 0.328 to
0.590, 0.270 to 0.673, 0.498 to 0.588). Item 5 did not move: those false
onsets keep the frame up (median floor about 0.92), and 0.65 is already the
better list there. Matched notes on item 5 DI stay about 0.63 s short. Joining
onsets does not lengthen a note that was never split.

It is not in the decoder. EGSet12 clip 04 pitch recall inside 300 ms fell from
0.8765 to 0.8471. The user-recording lock moved the other way too: the current
upload and take C went from 238 notes to 261, and take B from 565 to 536
(median duration 0.211 s to 0.259 s). Take A stayed inside the lock. With the
rule left out, those gates are unchanged.

## Frame-dip join, measured and not adopted

On train item 4 amplifier 3 the join moved F1@50 from 0.736 to 0.955 and offset
F1 from 0.286 to 0.876. The rendered 16th-note chug stayed at onset F1 1.0.
Items 5, 46, and 101 barely moved. The same post-decoder join then missed the
locked electric floor: EGSet12 clip 02 note F1 0.8686 to 0.8428, clip 04 note
F1 0.9313 to 0.8742, clip 12 F1@100 0.9818 to 0.9434, Guitar-TECHS excerpt 02
pitch recall 0.9375 to 0.9107, and the amp-solo category F1@100 0.9136 to
0.9027. With the join left out, the electric gate and the rest of
`server/tests` pass (182 passed; the heavyweight separation test stays
skipped). Playback and the locked floors are unchanged.

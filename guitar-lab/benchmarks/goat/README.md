# GOAT evaluation

Research only. [GOAT](https://doi.org/10.5281/zenodo.15690894) is CC BY-NC 4.0
(Loth, Sarmento, Sarkar, Guo, Barthet, and Sandler, ISMIR 2025). Do not commit
the audio, the tabs, or the MIDI, and do not ship weights trained on them.

The files live outside this tree. From `guitar-lab/`:

```sh
python -m benchmarks.goat --root /path/to/GOAT-parent --split train
python -m benchmarks.goat --root /path/to/GOAT-parent --split train --frame-join
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

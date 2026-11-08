# Fine-tuning Riley for distorted guitar

Riley's released guitar model was trained on clean guitar. On One's heavy half it finds about
30 notes per 30 s where the tab has about 400. This folder makes training data that sounds
like crunch and high-gain guitar, where every note is known, and fine-tunes the model on it.

- `amp.py` builds random amp chains with [pedalboard](https://github.com/spotify/pedalboard):
  low cut, drive, mid EQ, cabinet roll-off, sometimes a compressor or a small room.
- `riffs.py` writes original riffs (chugs, gallops, power chords, single-note lines at
  90–220 BPM), often double-tracked. A plucked-string model renders them.
- `build_data.py` re-amps GuitarSet pickup recordings (CC BY 4.0) from players 00–04.
  Player 05 is held out because the regression library uses it. About 25% stays clean.
  The original riffs are added, and everything is cut into 10 s segments.
- `finetune_riley.py` keeps the convolutional front ends frozen. It trains the recurrent and
  output layers of the onset, offset and frame heads, using Kong-style targets. It runs on CPU.

```sh
python training/build_data.py --guitarset-audio <audio_mono-pickup_mix> --guitarset-ann <annotation> --out data/heavy
python training/finetune_riley.py --data data/heavy --out runs/heavy --steps 440 --every 110
FRETWORK_RILEY_CHECKPOINT=runs/heavy/step_440.pth python -m benchmarks.regression --tier full --backend riley
```

No commercial recordings or tabs are used for training. The user's private recordings are
only used as held-out tests.

## Result so far

First run: 330 steps on CPU, about 1.5 hours. It was **not adopted**. Loss on held-out synthetic data improved, but One's heavy half didn't improve and its clean half got worse. See `benchmarks/regression/RESULTS.md`, "Fine-tuning Riley on amp-rendered guitar". The failure is pitch (overtones and octaves) under real high-gain tone. Synthetic amps and plucked-string riffs don't close that gap.

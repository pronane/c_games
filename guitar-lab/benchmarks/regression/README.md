# Transcription regression library

Scores what a backend returns from audio alone. The chart, when one exists, is
applied only after transcription. Nothing here writes chart notes back into
the model, and nothing picks an alignment by maximising note F1.

From `guitar-lab/`:

```sh
python -m benchmarks.regression --tier fast --backend basic_pitch
python -m benchmarks.regression --tier full --backend basic_pitch --backend riley --backend gaps
```

`server/tests/test_regression_benchmark.py` replays the public fast clips
(GuitarSet rock solo, first 8 s, plus the rendered clean, distorted, and
reverb pair) and checks them against `reference/basic_pitch_fast.json`.

## Categories

| Category | What is scored | Ground truth |
| --- | --- | --- |
| Solo acoustic | GuitarSet player 05, mono mic: rock solo, funk solo, jazz comping (CC BY 4.0) | `note_midi` annotations |
| Clean electric | IDMT-SMT-Guitar dataset 3, five short DI pieces (local only, CC BY-NC-ND) | note XML |
| Reverb vs clear | User AAC pair, two fixed windows on the clear timeline (30–60 s, 150–180 s). Warped with chroma DTW. Also a synthetic dry/wet pair with known MIDI | clear transcription (user); the rendered notes (synthetic) |
| Rendered | Karplus-Strong clean scale and distorted palm-mute chug, same voice as playback | the notes that were rendered |
| Full-band intro | Metallica "One" intro only: tab 0–16.5 s placed at audio 19.3 s (`ONE_FROZEN`) | guitar tracks of the GP4, bass and drums omitted |

Carcassi Op. 60 No. 1: the aligned MIDI is in `data/carcassi/`. The recording it
belongs to was not in the attachment and was not found, so it is not scored.
EGDB's clean/amp pairs were not downloaded (public bundle is 135 GB; the
original set is on request). IDMT here is direct-input electric, not an amp.

## Metrics

Per clip, mir_eval where it applies:

- note F1, onset ±50 ms, exact pitch, offsets ignored
- onset-only F1
- pitch recall at ±300 ms

Unisons inside 30 ms collapse, so doubled tab notes are one event. CPU time is
seconds per minute of audio, measured around the transcribe call.

## Backends

Basic Pitch ONNX at the app's current thresholds is the default and the
committed reference. `FRETWORK_TRANSCRIBER=riley` selects the Riley, Edwards,
and Dixon high-resolution guitar model (`guitar-fl.pth`, ICASSP 2024).
`FRETWORK_TRANSCRIBER=gaps` selects their later GAPS checkpoint. Both are MIT
and run on CPU; install `server/requirements-transcription-extras.txt`.
Published decoder thresholds are left alone.

`FRETWORK_TRANSCRIBER=yourmt3` runs YourMT3+ (YPTF.MoE+Multi, noPS) as a
separate program. Its inference code is GPL-3.0 and is not vendored;
`tools/yourmt3/setup.sh` installs it elsewhere. The 560 MB checkpoint is Apache-2.0.
Results are in RESULTS.md. A default switch requires a
backend to be at least Basic Pitch on every measured category, clearly better
on average, and to have no unmeasured category from the list above. Otherwise
it stays opt-in. There is no per-category router: a router fit on this library
would be tuning to the test charts.

## Private audio

`data/private/` is gitignored.

- `private/idmt/dataset3/` — IDMT dataset 3 wav + xml
- `private/user/take_a_4m51.aac` — reverb/delay take
- `private/user/take_c_synth_4m58.aac` — clear synth of the same piece
- `private/metallica/song.mp3` and `song.gp4` — local copy of the remaster and the tab

`take_b` is a different song and is not used.

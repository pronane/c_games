# Transcription regression library

Scores what a backend returns from audio alone. The chart, when one exists, is
applied only after transcription. Nothing here writes chart notes back into
the model, and nothing picks an alignment by maximising note F1.

From `guitar-lab/`:

```sh
python -m benchmarks.regression --tier fast --backend basic_pitch
python -m benchmarks.regression --tier full --backend basic_pitch --backend riley --backend gaps
python -m benchmarks.regression --tier electric --backend basic_pitch --backend riley --no-report
```

`server/tests/test_regression_benchmark.py` replays the public fast clips
(GuitarSet rock solo, first 8 s, plus the rendered clean, distorted, and
reverb pair) and checks them against `reference/basic_pitch_fast.json`.
That match is two-sided (±0.02). EGSet12 and the Guitar-TECHS excerpts are a
one-sided floor against `reference/electric_baseline.json`: a score may rise,
and a drop of more than 0.02 on a clip (or 0.01 on a category mean) fails.
The electric check skips when those files are not on disk, so CI stays green
without them. A wrong checksum does not skip.

## Real miked-amp sets

Both are CC BY 4.0 evaluation material. They are not training data, and they
are not passed into the transcriber as a chart. Audio, Guitar Pro files, and
MIDI stay in `data/private/` (gitignored). Checksums are in
`reference/electric_manifest.json`.

| Set | What is scored | Ground truth |
| --- | --- | --- |
| EGSet12 | All 12 solos, miked amp, no other effects. Pop, funk, jazz, twelve-tone. https://zenodo.org/records/11406378 | JAMS `note_midi`, one annotation per string. The `.gp` files are Guitar Pro 6/7 packages; they are downloaded and checksummed, and they are not parsed. |
| Guitar-TECHS | The 12 musical excerpts only (`P3_music.zip`, 129 MB), not the 4.1 GB of techniques, chords, and scales. https://zenodo.org/records/14963133 and https://guitar-techs.github.io/ | Per-string Fishman MIDI. Miked amp (`micamp`); direct input is downloaded so the alignment can be compared, and it is not the scored signal. |

Credit EGSet12 to Pedroza, Abreu, Corey, and Roman, DAFx 2024
(doi:10.48550/arXiv.2405.14679). Credit Guitar-TECHS to Pedroza, Abreu, Corey,
and Roman, ICASSP 2025 (doi:10.1109/ICASSP49660.2025.10887996).

The Guitar-TECHS authors warn that signals can be up to 100 ms apart. Each
excerpt gets one constant lag from a pitch-blind onset-envelope correlation,
searched only inside ±100 ms and frozen in `reference/electric_alignment.json`.
Note F1 is not an input. On this measurement the miked-amp lag was −5 to −21 ms
(mean absolute 10.4 ms) and direct input was no tighter (13.1 ms), so the gate
scores the miked amp. EGSet12's JAMS clock is already close: the same estimator
lands at +8 to +24 ms. Note F1 at ±50 ms is the library's metric. Note F1 at
±100 ms is locked beside it so a residual inside the authors' bound is visible.
Neither number picks the lag.

EGDB, GOAT, and Cambridge-MT are not downloaded. The TabCNN weights shipped
next to EGSet12 are not downloaded. The other Guitar-TECHS zips are not
downloaded.

```sh
python -m benchmarks.regression.download
python -m benchmarks.regression.download --check   # exit 3 if the files are absent
```

A single official file, if you want the bytes without the script:

```sh
curl -L -o P3_music.zip "https://zenodo.org/api/records/14963133/files/P3_music.zip/content"
# md5 071ba80aecf00f4a31fbd167b3f22198, 129505089 bytes
curl -L -o 01.wav "https://zenodo.org/api/records/11406378/files/01.wav/content"
```

The record pages are the source. `--align` rewrites the frozen lags from the
audio and the reference onsets. It does not look at a transcription. Do not
refit those lags to raise F1.

## Categories

| Category | What is scored | Ground truth |
| --- | --- | --- |
| Solo acoustic | GuitarSet player 05, mono mic: rock solo, funk solo, jazz comping (CC BY 4.0) | `note_midi` annotations |
| Amp solo | EGSet12, all 12 miked-amp solos, no other effects (local only, CC BY 4.0) | JAMS `note_midi` |
| Amp excerpt | Guitar-TECHS player 3, 12 musical excerpts, miked amp (local only, CC BY 4.0) | per-string MIDI, frozen onset lag |
| Clean electric | IDMT-SMT-Guitar dataset 3, five short DI pieces (local only, CC BY-NC-ND) | note XML |
| Reverb vs clear | User AAC pair, two fixed windows on the clear timeline (30–60 s, 150–180 s). Warped with chroma DTW. Also a synthetic dry/wet pair with known MIDI | clear transcription (user); the rendered notes (synthetic) |
| Rendered | Karplus-Strong clean scale and distorted palm-mute chug, same voice as playback | the notes that were rendered |
| Full-band intro | Metallica "One" intro only: tab 0–16.5 s placed at audio 19.3 s (`ONE_FROZEN`) | guitar tracks of the GP4, bass and drums omitted |

Carcassi Op. 60 No. 1: the aligned MIDI is in `data/carcassi/`. The recording it
belongs to was not in the attachment and was not found, so it is not scored.
EGDB's clean/amp pairs were not downloaded (public bundle is 135 GB; the
original set is on request). IDMT here is direct-input electric, not an amp.
EGSet12 is a miked amp with no other effects. It does not stand in for those
missing high-gain pairs, and scoring it does not change the default transcriber.

## Metrics

Per clip, mir_eval where it applies:

- note F1, onset ±50 ms, exact pitch, offsets ignored
- onset-only F1
- pitch recall at ±300 ms

Unisons inside 30 ms collapse, so doubled tab notes are one event. CPU time is
seconds per minute of audio, measured around the transcribe call.

## Backends

Basic Pitch ONNX at the app's current thresholds is the committed fast-clip
reference. Riley is the in-app default when it is installed, otherwise Basic
Pitch. This gate does not change that choice.
`FRETWORK_TRANSCRIBER=riley` selects the Riley, Edwards,
and Dixon high-resolution guitar model (`guitar-fl.pth`, ICASSP 2024).
`FRETWORK_TRANSCRIBER=gaps` selects their later GAPS checkpoint. Both are MIT
and run on CPU; install `server/requirements-transcription-extras.txt`.
Published decoder thresholds are left alone.

`FRETWORK_TRANSCRIBER=yourmt3` runs YourMT3+ (YPTF.MoE+Multi, noPS) as a
inside the engine from `server/yourmt3`, adapted from the authors' Apache-2.0 release.
Its 560 MB checkpoint (Apache-2.0) downloads on first use.
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
- `private/egset12/` — EGSet12 wav, JAMS, and Guitar Pro (CC BY 4.0, downloaded)
- `private/guitar_techs/` — Guitar-TECHS P3 excerpts, miked amp, DI, and MIDI (CC BY 4.0, downloaded)
- `private/cache/P3_music.zip` — that excerpt archive

`take_b` is a different song and is not used.

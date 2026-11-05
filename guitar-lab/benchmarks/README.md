# Accuracy benchmarks

Both scripts score what the app actually produces. Results from 5 Nov 2026 are in the main README.

## Error taxonomy

`accuracy_errors.py` classifies unmatched notes against MIDI (wrong octave, semitone, other pitch, extra ghost, missed onset, merges, splits, timing-only). The write-up is [ACCURACY_ERRORS.md](ACCURACY_ERRORS.md).

Ghost suppression reverts when it would drop more than 15% of the notes (`suppress_harmonic_ghosts(..., max_drop_frac=0.15)`). Held-out Guitar-TECHS P3 amp F1 at ±50 ms went from 0.661 to 0.677. Carcassi, the GuitarSet sample, the DI take, Hollow Ground and the NIN false-chord test did not move (false-chord fraction stayed 0.0). The opt-in `clean_model` filter from PR #46 is unchanged and stays off.

Round 2 is [ACCURACY_ERRORS_2.md](ACCURACY_ERRORS_2.md). Missed-note pickup is on by default (`FRETWORK_PROMOTE=0` disables it): a second Basic Pitch pass at 0.3/0.2 adds a note only with corroborating evidence, capped at 30%. Held-out Guitar-TECHS amp F1 at ±50 ms went from 0.677 to 0.691 on 6 clips. The string prior (`FRETWORK_FINGERING=prior`) and sub-partial drop (`FRETWORK_SUBPARTIAL_DROP=1`) stay off. With the prior, exact string and fret on true notes for held-out GuitarSet players 03–05 went from 0.575 to 0.714. The held-out amp set is only 6 clips, pickup is about 2× transcription time, and the full app path was not run on real audio.

## Real guitarists: GuitarSet

CC BY 4.0, Xi et al., ISMIR 2018. Download `annotation.zip` and `audio_mono-mic.zip` from
https://zenodo.org/records/3371780, unzip, then from `guitar-lab/`:

    python -m benchmarks.guitarset ann_dir mic_dir results.jsonl
    python -m benchmarks.guitarset --report results.jsonl

About 25 minutes for all 360 recordings on 2 CPU cores.

## A real band: multitrack stems

`benchmarks/songs/1000000.json` describes Nine Inch Nails, "1,000,000" (The Slip, 2008), whose
multitrack stems the band released under CC BY-NC-SA 3.0 US. Download
`1000000Multi-tracks.7z` from https://archive.org/details/NineInchNails-TheSlipMulti-trackStems,
extract it, start the engine on :8000, then:

    python -m benchmarks.multitrack "/path/to/1,000,000 Multi-Tracks/Audio Files" benchmarks/songs/1000000.json out_dir

`1000000.report.json` is the result of that run. Any song you have real stems for works the same
way: write a JSON naming which stems are guitar, bass, drums, vocals and other, plus the tempo.
The stems and the derived mix are not committed (licence: non-commercial, share-alike).

## Transcription refinement (synthetic until real takes are scored)

`benchmarks/refine_eval.py` scores note F1 (±50 ms onset, offsets ignored) for a guitar
stem against a MIDI key, first pass and after the render-and-revise loop:

    python -m benchmarks.refine_eval stem.wav notes.mid
    python -m benchmarks.refine_eval --self-check

The self-check does not use a recording. It renders eight notes with the Karplus–Strong
voice, drops two, adds one, and shifts one. Measured here: first-pass note F1
0.67, refined note F1 1.00, match score 0.69 → 0.90, about 0.4 s. Real MIDI-keyed amp takes
are not in this number. Run the same script on those files when they are available; pass
the guitar stem, not the full mix. The loop is off unless `FRETWORK_REFINE=1` and the
request asks for it. See `server/refine.py`.

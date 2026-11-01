# Accuracy benchmarks

Both scripts score what the app actually produces. Results from 1 Nov 2026 are in the main README.

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

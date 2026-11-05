# Fretwork — guitar comparison prototype v0.4

**On Windows:** double-click `windows\install.bat`, then use the **Guitar Lab** shortcut. See [windows/README.md](windows/README.md).
Everything runs on your PC: the engine also serves the studio at `http://localhost:8000`.

## File types

Songs and recordings can be MP3, WAV, FLAC, OGG, M4A/AAC, Opus, or the sound of a video file (WebM, MP4, MKV, MOV). Video and compressed formats are decoded in the browser and sent to the engine as WAV, so ffmpeg isn't required; if the browser can't decode a file, the engine tries ffmpeg. The video picture is ignored.

## Learn from a tab or score (new in v0.4)

Separation can't guarantee a clean part from every recording, so this mode doesn't depend on it.

1. Upload a Guitar Pro file (.gp, .gp3–.gp5, .gpx), MusicXML (.musicxml, .xml, .mxl) or a text tab (.txt), or paste a text tab.
2. Pick the track. The app shows notation and tab, says if the tab needs a different tuning or capo and retunes the tuner in one tap, and offers a Guitar Pro download.
3. Play the app's own rendition (a plucked-string synth at the exact written pitches), with click, loop and 50–100% speed without pitch change.
4. Record along with a count-in, with the tab quietly in your headphones or just the click. The measured device delay is removed.
5. **Check my take against the tab**: each written note is checked against your recording ("did this pitch start near its written time?"), rather than comparing two uncertain transcriptions. The result is the score per bar, the top issues and a next step.

Text tab has no rhythm: notes are placed by where they sit between bar lines and rounded to sixteenths. Guitar Pro and MusicXML repeats are played once in written order.

The song breakdown links here too: **Practise from this tab** sends its generated tab to this mode. If the generated notes are wrong, download the MusicXML, fix it in MuseScore or Guitar Pro, and load the corrected file.

### Hear what the app heard

After any comparison, **Your take, as the app heard it** plays back the notes the app picked out of your recording on its own guitar sound. Next to it you can play the tab (or original part), both together (original in the left ear, you in the right), or your actual recording. A note you played but can't hear in the app's version wasn't picked up. **Show my take as notation and tab** writes your performance out, with a Guitar Pro download.

### Practice piece

`examples/night-watch-etude.gp` is an original 22-bar study in A minor at 104 BPM, written for this app and free to use. It goes in five steps: clean arpeggios, palm-muted chugs with power-chord accents, a gallop rhythm, double stops in thirds, and an ending. Load it under **Learn from a tab or score**. Its alphaTex source is next to it; rebuild with `npx tsx examples/make-practice-piece.mts`.

### How reliable is the tab check? (GuitarSet, 60 real performances, 13,807 notes)

Each recording is checked against exactly what the player played, so anything flagged is a false alarm. Mistakes are then planted by editing the tab.

| | |
| --- | --- |
| Correct notes called correct | 89% |
| Correct notes wrongly flagged: wrong note / missed / off the beat | 2.6% / 2.1% / 6.8% |
| Extra notes flagged per minute | 3.6 |
| Wrong notes caught (1–2 semitones off) | 72% |
| Missed notes caught | 68% |
| Notes 150 ms late caught | 42% |

On an original Drop D riff played back on a different guitar sound with three planted mistakes (a wrong note, a missed note, a late note), it reported exactly those three and nothing else. Settings favour few false accusations over catching every small timing slip. Run `python -m benchmarks.feedback_check` to reproduce.

## Processing: CPU or graphics card

Separation runs on the CPU by default. **Separate instruments on → Graphics card** is enabled when the analysis server has a usable NVIDIA (CUDA) or Apple (MPS) GPU. It is much faster and falls back to CPU, with a note, if the card runs out of memory. Transcription always runs on the CPU. The server default can be changed with `FRETWORK_DEVICE` (`cpu`, `auto`, `cuda`, `mps`).

## Learn a song (new in v0.3)

Pick your instrument, then add a song (upload, or a direct https link to an audio file you have the right to use; YouTube, Spotify and other streaming links are refused because their terms forbid downloading and the audio is protected). The engine runs Demucs `htdemucs_6s` once and returns:

- **Which instruments play** (energy share and active time per stem) with solo / mute for each.
- **Guitar parts**: the guitar stem is split by stereo position (left / centre / right) and every bar is labelled lead, rhythm, mixed or rest. Bars where a part only carries leakage from another part are detected (quieter copy of the same pitches, or centre overlap of both sides) and left out of tab and roles.
- **What I'll play**: one guitar, one guitar's lead or rhythm bars, *every lead passage whichever guitar plays it*, every rhythm passage, or all guitars. This choice drives the backing track, the guide, the recording, your mix, the comparison and the tab.
- **Tuning**: a suggestion from the lowest notes played and the recording's offset from A440 (e.g. "half step down, A4 = 440"), one tap to retune the tuner. Drop D vs D standard and similar pairs are reported as ambiguous.
- **Key, tempo, bars, chords**: key from pitch profile, resolved between relative major/minor by the tonic chord; steady-tempo beat grid with the downbeat at the strongest chord change; chords per beat with a key prior.
- **Tab and notation** for the chosen part (alphaTab rendering, MusicXML download for MuseScore / Guitar Pro / Sibelius), fingered with a hand-position Viterbi pass for the selected tuning and capo.
- **Hear it back three ways**: the separated part ("what it heard"), the tab as written on the app's own guitar, or both (one per ear). Your own take plays back as heard and as written in its tab.
- **Guitar sound**: clean, crunch or high-gain amp plus chorus, delay and reverb for the app's guitar. The breakdown guesses the song's sound (or you tell it), and the transcription thresholds follow it: distortion hides note starts, so driven guitar is transcribed with lower onset thresholds (measured: high-gain note F1 0.45-0.56 -> 0.58-0.67).
- **Tab files play with their own instruments**: Guitar Pro / MusicXML files play through a General MIDI sound bank (SONiVOX EAS, Apache-2.0, shipped with alphaTab) with every track, repeats played out, palm mutes, let-ring and bends; mute your track and play along with the rest of the band.
- **Practice**: loop a bar range, slow to 50–100% without changing pitch (WSOLA in the browser), play along and record with a count-in while the chosen music is muted, optional quiet guide.
- **Your take in the song**: hear the band with your take in place of the part you replaced, download the mix, or send it to the comparison engine.
- **Feedback**: the comparison now opens with an estimated match score, a score per bar, the top issues ("2 wrong notes in bar 6", "rushed bar 4 (about 120 ms early)") and one next step.

### How accurate is it? (measured 5 Nov 2026)

**Real guitarists: [GuitarSet](https://zenodo.org/records/3371780)** (CC BY 4.0). 360 recordings by six players in five styles, every note's string and fret captured with a hexaphonic pickup. Guitar alone, no band. Run with `python -m benchmarks.guitarset`.

| What | Solos | Chord playing | All |
| --- | --- | --- | --- |
| Notes (onset ±50 ms, right pitch), F1 | 0.87 | 0.74 | 0.80 |
| Tab: right string and fret, given the right notes | 0.437 | 0.763 | 0.600 |
| Chords (major/minor, time-weighted) | — | 0.51 | — |
| Key exactly right | 0.33 | 0.56 | 0.44 |
| Tempo within 4% (allowing double/half) | 0.76 | 0.66 | 0.71 |

Note F1 is at onset/frame thresholds 0.6/0.4, up from 0.78 overall at 0.7/0.5 (chord playing 0.69 to 0.74, solos 0.88 to 0.87). Exact string and fret given the true notes is 0.600, up from 0.589, from carrying the fretting hand through open strings. A 0.05 fret-height cost regressed that score to 0.554, so the fret-height weight stays 0.0.

**A real band: Nine Inch Nails, "1,000,000"** from *The Slip* (2008), using the band's own multitrack stems, released under CC BY-NC-SA 3.0 US ([archive](https://archive.org/details/NineInchNails-TheSlipMulti-trackStems)). The stems are summed into the mix, the mix goes through the app as a user's upload would, and the output is scored against the stems. Run with `python -m benchmarks.multitrack`.

| What | Result |
| --- | --- |
| Which instruments play (guitar, bass, drums, vocals, other; no piano) | all correct |
| Tempo (band's figure 136 BPM) | 135.9 BPM |
| Bass / drums / vocals separation (SI-SDR vs doing nothing) | +11.0 / +8.5 / +7.4 dB |
| Guitar separation | failed: −2.3 dB vs −2.0 dB for the raw mix; most of the main guitar track lands outside the guitar stem |
| Guitar notes vs the same transcriber on the band's isolated guitar tracks | F1 0.22 |
| Tuning suggestion | D standard (likely wrong; low notes from the bass) |

**Could a newer separator fix that?** BS-RoFormer SW (a six-stem community model) on the same song: guitar −0.8 dB vs Demucs −2.4 dB. It keeps 86% of the second guitar in its guitar stem (Demucs 54%). Neither model finds the band's main, very low guitar track: Demucs puts most of it under "other", RoFormer under "bass". RoFormer also needed 48 minutes for this 4-minute song on a 2-core CPU (Demucs a few minutes), and its licence is unknown, so it is not used. On our synthetic songs it won on the acoustic one (13.3 vs 2.0 dB) and lost on the distorted one (1.6 vs 17.5 dB). A licensed RoFormer-class guitar model on a GPU is the most promising upgrade.

**What that means.** On a clean guitar recording the notes are mostly right and good enough to learn from, with a note editor for the rest. Chords, key and tab positions are a starting point to check, not an answer. On a full commercial mix everything depends on getting a clean guitar out first. The open six-stem model does that well for clearly recorded guitars (17.5 dB on our distorted three-guitar test song) and badly for heavily processed ones like this NIN track. When it fails, every guitar-specific result after it fails too. It will not always be right, and the app says so on every result.

**Harmonic ghosts on distorted guitar.** On overdriven guitar, Basic Pitch often writes octave and fifth partials as extra notes, so a single-note line is counted as chords. Ghost suppression runs before bar-role labelling and is a no-op on clean tone. If cleanup would remove more than 15% of the notes, the raw list is kept (`max_drop_frac=0.15`). On held-out Guitar-TECHS P3 amp (real MIDI) that raised note F1 at ±50 ms from 0.661 to 0.677; Carcassi (0.623), a GuitarSet sample, the DI take, Hollow Ground and the NIN false-chord test did not move (false-chord fraction stayed 0.0, versus 0.023 with suppression fully off). See [benchmarks/ACCURACY_ERRORS.md](benchmarks/ACCURACY_ERRORS.md). On the Nine Inch Nails "Head Down" excerpt at the distorted thresholds (onset 0.5 / frame 0.3), the chord fraction fell from 0.139 to 0.071 and note F1 rose from 0.355 to 0.374. Clean-tone guitar and GuitarSet are unchanged. On full-band songs the main bottleneck is guitar separation, not transcription: note F1 is 0.40 on the separated guitar versus 0.75 on the true guitar stem for Head Down.

**Missed-note pickup (on by default).** After ghost cleanup, a second Basic Pitch pass at onset/frame 0.3/0.2 may add a note only when its pitch is already in the part, its amplitude is at least 0.35, an onset peak is within 50 ms, the harmonic series at that pitch rises at least 1.5×, and it is not a partial, a semitone neighbour, or a re-trigger of a note already kept. Adds are capped at 30% of the notes. `FRETWORK_PROMOTE=0` turns this off. Held-out Guitar-TECHS P3 amp F1 at ±50 ms went from 0.677 to 0.691 (6 clips only). DI 0.660 to 0.666, a 20-file GuitarSet sample 0.821 to 0.829, Carcassi 0.645 to 0.644. The extra pass is about 2× transcription time, and the full app path was not run on real audio. See [benchmarks/ACCURACY_ERRORS_2.md](benchmarks/ACCURACY_ERRORS_2.md).

**Dense repeated notes (on by default).** Basic Pitch's decoder holds a note open until the frame activation drops for about 130 ms, so palm-muted 16ths faster than that come back as every other pick. The onset posterior still peaks on each pick. When one pitch has a regular run of those peaks (45–160 ms apart) and the decoder already kept that pitch, the missing picks are filled in. A peak an octave or a fifth above a note at the same instant is left out, and a slow line is not a run, so it is not split. `FRETWORK_RESEGMENT=0` turns this off. On rendered guitar with known MIDI (the chart is not fed back in), heard-only F1 at ±50 ms went from 0.667 to 0.980 for distorted 16ths at 160 BPM and from 0.545 to 0.935 at 216 BPM. A scale and a changing-pitch 16th line stayed at 1.000; power chords were unchanged. See `python -m benchmarks.repeated_onset_eval --self-check`.

**String prior and sub-partial drop (both off).** `FRETWORK_FINGERING=prior` uses a four-fret hand window plus a string prior counted from GuitarSet players 00–02. Exact string and fret on the true notes, held-out players 03–05, went from 0.575 to 0.714. It moves open-position classical parts up the neck, so the default stays the classic costs and the Carcassi and A-minor arpeggio checks still pass. `FRETWORK_SUBPARTIAL_DROP=1` drops a distorted note a fifth, fourth, octave or twelfth below a simultaneous upper note when its own fundamental is weaker. The tuning-set gain did not hold on the held-out amp half, so it stays off.

**Effects detection (prototype, trained on real pedals).** The effect classifier in `server/fx/` is a 60-tree random forest over 67 audio features, trained on [IDMT-SMT-Audio-Effects](https://www.idmt.fraunhofer.de/en/publications/datasets/audio_effects.html) guitar clips (26,892 clips, 12 classes; CC BY-NC-ND, so only derived numbers ship in `fx/data/templates.json`, 0.9 MB). Tested on a guitar it never saw (train on one guitar, test on the other, both ways): right effect 93.1% of the time (single notes 92.1%, chords 96.2%), up from 37.5% for the earlier synthetic templates. Distortion, delay, reverb, tremolo and vibrato are 98-100%; phaser is the weakest at 65% (confused with chorus and flanger), then no-effect 87% and chorus 87%. Retrain with `python -m server.fx.train_idmt --features <cached.npz>`. **Real songs are still weak:** on clean DI and amp recordings (Guitar-TECHS, Hollow Ground) it mostly answers "feedback delay" at low confidence, so the result is shown as a hint, not a fact.

**Removing effects before transcribing does not help yet.** On real amp recordings, transcribing the de-effected audio scored the same or slightly worse than the amp audio itself (Hollow Ground 5 amp tracks: note F1 0.450 de-effected vs 0.448 as recorded, against the engine on the same take's DI; Guitar-TECHS techniques: unchanged once low-confidence delay guesses no longer trigger de-reverb). De-FX is therefore used only for the "clean version" playback, not for the tab. On Guitar-TECHS (real MIDI), note F1 on the amp take vs the direct take: palm mute 0.61 vs 0.67, bends 0.45 vs 0.47, vibrato 0.71 vs 0.74, harmonics 0.45 vs 0.35, 12 songs 0.67 vs 0.65-0.66. Palm-muted notes stay short through the pipeline (median length 0.26 s vs 1.95 s for open notes on the amp take; true MIDI 0.19 s vs 3.64 s), but the acoustic re-synthesis shortens open notes to about 0.7 s, so long sustains are not yet reproduced.

**Reference check (Shazam-style fingerprint, advisory only).** `server/fingerprint.py` hashes spectrogram peak pairs (f1, f2, dt) and votes on time offset (Wang 2003). If a song is given a `reference` (a recording or a MIDI file), the result gets a `reference_check` with match / offset / tempo ratio. It is computed after every output is final and only adds that key: with the check off, a matching reference or a non-matching one, the transcription, notation and tab were byte-identical (SHA-256 of result + score, Carcassi and Hollow Ground). A non-match says "no match - not an error". Measured (`benchmarks/fingerprint_eval.py`, 8-second excerpts unless stated): the same recording matched 86/99 times (noise 10 dB, EQ, MP3-style low-pass, 5 s excerpts and a 4% tempo change 11/11 each; clipping 10/11; distortion 7/11; heavy 1 s reverb 3/11), offsets within 63 ms. Different players on the same GuitarSet progression (cover-type): 0/12 matched. Unrelated pairs: 0/30. The same take's DI vs its amp track matched 7/7 (same performance, so this is expected). A MIDI rendering matched its recording 1/5 (the fingerprint is recording-specific, so MIDI references are mostly "no match").

**Learned note filter for processed guitar (opt-in, off by default).** `server/clean_model.py` re-scores Basic Pitch candidates (thresholds 0.3/0.2) with a 150-tree gradient-boosted model (`fx/data/clean_model.json`, 70 KB). It was trained on Guitar-TECHS (real MIDI) and Hollow Ground (labels from the DI) with performance-held-out 4-fold CV. Only crunch/distorted audio and only `FRETWORK_CLEAN_MODEL=1`. Held-out note F1 at ±50 ms, baseline then model: Hollow Ground amp 0.448 to 0.482 (±100 ms 0.494 to 0.560); Guitar-TECHS 12 songs amp take 0.667 to 0.623 (distorted-gated subset 0.692 to 0.623); techniques amp 0.518 to 0.509. NIN false-chord fraction got worse, 0.028 to 0.081 (0.042 with suppression). Real-MIDI results regress, so it stays off. GuitarSet (40 random files) and Carcassi are estimated clean or uncertain and never reach it.

**Refine until it matches (opt-in, off by default).** For a guitar stem or a clean guitar take, the engine can transcribe, play the notes back with the Karplus–Strong voice, and revise the transcription while that rendering gets closer to the target audio. An edit is kept only when the local region and the whole file both score higher, and the result is never worse than the first pass. Written notation (MusicXML, MIDI, Guitar Pro, tab) is already exact, so that path is not revised. Switch it on with `FRETWORK_REFINE=1` on the server and the "Refine until it matches" control. The result JSON gains a `refinement` object (original score, final score, and the per-pass log) and leaves every existing key as it was. Synthetic timing (`python -m benchmarks.refine_eval --self-check`, 8 notes, 4.1 s): note F1 0.67 → 1.00, match score 0.69 → 0.90, about 0.4 s. Real MIDI-keyed recordings are not part of that number. The loop stops after 5 passes or 20 seconds. On a real amp take the absolute match score stays lower than this, because the playback voice is not the amp.

Earlier synthetic checks (FluidSynth instruments): three guitars split into the right parts and lead bars; centre lead 32/32 notes; E minor, 110 BPM and Em–C–G–D found; an E♭-tuned song correctly suggests half step down.

## Instrument profiles and tuning

Choose guitar, four-string bass or piano before playing. Shared instrument profiles drive pitch limits, stem/method selection, tuning/capo-aware tab, notation and feedback policy. An optional live single-note tuner works through the selected audio input. See [instrument profiles and limitations](INSTRUMENT_PROFILES.md). Bass/piano routing is experimental, not validated instrument-specific coaching.

## USB audio / MIDI input

The studio supports OS/browser-exposed USB audio interfaces with device selection, mono/stereo input routing, PCM recording, a level meter and clipping warnings. USB MIDI keyboards/adapters have a separate local note-capture and `.mid` export path. See [USB input setup, compatibility and limitations](USB_INPUTS.md). Comparison routing now follows the selected profile; real-world bass/piano accuracy is not yet validated.

## Specialist engine milestone

The studio now includes a **separate Python engine workflow** with explicit excerpt-upload consent, guitar-stem listening approval, librosa chroma/DTW passage alignment, actual Basic Pitch ONNX transcription, editable notes/standard-tuning tab, and uncertainty-labelled timing/pitch/duration observations. See [server setup and limitations](server/README.md).

The browser-only preview below it remains available as a clearly labelled lightweight experiment. It is **not** the specialist model pipeline. Audio stays local unless the user explicitly consents in the specialist engine panel.

**Current sandbox:** real ONNX transcription and alignment work with isolated guitar references. Full-band source separation is wired to Demucs htdemucs_6s but blocked until official weights and its runtime are provisioned. No end-to-end full-band inference or GPU hardware validation is claimed. The interface makes this limitation visible.

## Original browser-only prototype

A responsive, local-first TypeScript/React application for desktop, tablet and phone browsers. This is an experimental signal-analysis prototype, not an AI guitar teacher.

## Browser-only setup (for the specialist service, use server/README.md)

```sh
cd guitar-lab
npm ci
npm run dev
```

Open the provided HTTPS preview (microphone capture requires HTTPS or localhost). Vite binds to all interfaces. `npm run build` creates a static deployment; `npm test` runs signal-processing smoke tests. In the browser-only preview, no audio is uploaded or persisted. The specialist engine uses explicit consent and temporary server storage. Refreshing clears the session. Supported codecs depend on the browser.

## Working flow

1. Load an original song or isolated guitar reference.
2. Record a guitar passage (automatic length limit) or upload your take. Wear headphones to avoid backing-track leakage.
3. Supply the original timestamp corresponding to the **beginning of the uploaded take**, including any silence. Select 10/20/60 seconds (12 seconds is also available for the demo).
4. Compare the overlapping duration. Audio is downmixed/resampled to 16 kHz and processed in a Web Worker.
5. Listen to reference/take/together at adjustable speed, review candidate notes, suggested standard-tuning tablature and two-second chord estimates.

The sample creates two synthetic, plucked-envelope monophonic exercises with known differences. It uses the actual analysis pipeline, not prerecorded scores. It is not evidence of accuracy on real polyphonic guitar.

## What the measurements mean

- **Full mix:** bass, drums, voice and other instruments are present. Guitar pitch grading is intentionally withheld. Onset distance refers to mixed-track attacks, not identified guitar attacks.
- **Isolated guitar:** pitch-class overlap measures shared normalised spectral energy. It is NOT a percent-correct score. A missing note cannot be reliably inferred from it.
- **Onset distance:** average absolute distance from each detected take attack to the nearest reference attack. No one-to-one sequence alignment or latency compensation. Extra/missing attacks, rubato and repeated rhythms can mislead it.
- **Notes:** dominant narrow-band energy candidates (Goertzel bins, E2–E6). Harmonics, chords, bends, detuning and noise can mislead this method.
- **Tab:** a low-fret playable position in standard tuning, not detected string/finger placement. Alternative positions may be correct.
- **Chords:** maximum-energy major/minor triad guess in two-second windows; not a verified arrangement, key or beat-synchronised transcription.
- **Playback:** browser playback-rate control changes pitch along with speed. Pitch-preserving stretch is not implemented.

## Architecture decision and next milestones

TypeScript provides one portable UI and capture/playback implementation across modern browsers. Mobile microphone and codec support need real-device testing, particularly Safari. Native wrappers (e.g. Capacitor) and PWA offline installation are future options, not included capabilities.

Use a separate Python service for the next generation of audio analysis; do not attempt to infer clean guitar errors directly from a mastered mix:

1. Introduce explicit-consent uploads, job lifecycle, deletion/retention rules and separation-model licensing review.
2. Separate guitar from the full mix using a guitar-capable model. A generic four-stem model's `other` output is not a guitar stem. Store model/version, confidence and source provenance. Separation cannot necessarily distinguish doubled guitars or lead from rhythm.
3. Verify separated-stem quality and abstain where uncertain. Accept user/teacher-supplied clean references as the high-confidence alternative.
4. Use chroma subsequence matching plus dynamic time warping to propose the passage and timing map; ask the player to confirm ambiguous repeated sections.
5. Polyphonic transcription, tuning/capo input, explicit rhythm/lead selection, beat-aware chord segmentation and editable notation; validate on real guitar recordings.
6. Calibrate hardware latency; implement pitch-preserving time stretch and repeatable passage loops.
7. Evaluate buzz, sustain and missing-chord-tone classifiers with labelled examples. Report observations and uncertainty, not unproven finger-pressure causes. Ask the player to pick strings individually for diagnosis.

The preceding limitations describe the v0.1 browser preview. For v0.2 specialist-engine capabilities, model provisioning and outstanding limitations, see server/README.md.

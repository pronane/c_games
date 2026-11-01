# Fretwork — guitar comparison prototype v0.4

**On Windows:** double-click `windows\install.bat`, then use the **Guitar Lab** shortcut. See [windows/README.md](windows/README.md).
Everything runs on your PC: the engine also serves the studio at `http://localhost:8000`.

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
- **Practice**: loop a bar range, slow to 50–100% without changing pitch (WSOLA in the browser), play along and record with a count-in while the chosen music is muted, optional quiet guide.
- **Your take in the song**: hear the band with your take in place of the part you replaced, download the mix, or send it to the comparison engine.
- **Feedback**: the comparison now opens with an estimated match score, a score per bar, the top issues ("2 wrong notes in bar 6", "rushed bar 4 (about 120 ms early)") and one next step.

### How accurate is it? (measured 1 Nov 2026)

**Real guitarists: [GuitarSet](https://zenodo.org/records/3371780)** (CC BY 4.0). 360 recordings by six players in five styles, every note's string and fret captured with a hexaphonic pickup. Guitar alone, no band. Run with `python -m benchmarks.guitarset`.

| What | Solos | Chord playing | All |
| --- | --- | --- | --- |
| Notes (onset ±50 ms, right pitch), F1 | 0.88 | 0.69 | 0.78 |
| Tab: right string and fret, given the right notes | 0.44 | 0.79 | — |
| Chords (major/minor, time-weighted) | — | 0.51 | — |
| Key exactly right | 0.33 | 0.56 | 0.44 |
| Tempo within 4% (allowing double/half) | 0.76 | 0.66 | 0.71 |

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

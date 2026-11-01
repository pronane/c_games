# Fretwork — guitar comparison prototype v0.3

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

### What it gets right and wrong

Measured on original, synthetic test songs (FluidSynth General MIDI instruments), not commercial recordings:

| Check | Result |
| --- | --- |
| Instruments present (5-instrument song) | all correct |
| Three guitars (rhythm left, lead right bars 5–8, lead centre bars 11–14) | all three parts and their lead bars found exactly |
| Lead transcription, centre lead | 32/32 notes |
| Lead transcription, right lead | F1 0.74 (a few octave ghosts and misses) |
| Strummed 6-string rhythm chords | ~25% of chord tones; chord symbols carry this part |
| Key / tempo / chords (E minor, 110 BPM, Em–C–G–D) | correct |
| E♭-tuned song | suggests half step down |

It will not always be right. Expect errors with dense distorted mixes, doubled guitars panned together, two guitars at the same stereo position playing at once (cannot be separated by panning), bends, slides, harmonics, and tempo changes. Tab positions are suggestions. Check by ear and against a trusted source; use the note editor to correct.

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

# Instrument profiles and optional pre-recording tuner

## Choose before playing

The **Before you play → Choose your instrument** panel controls the session. Guitar, four-string bass, and piano/keyboard profiles share one catalogue: `shared/instruments.json`, consumed by both TypeScript and Python. It defines pitch limits, separation stem, transcription method, tuning presets/capo support, preferred/allowed notation and available feedback categories.

| Profile | Range | Presets | Stem | Display |
|---|---|---|---|---|
| Guitar | E2–E6 standard; D2 low with drop-D/DADGAD | Standard, drop D, DADGAD; capo 0–12 | `guitar` | Tab or note events |
| Bass, four strings | E1–G4 standard; D1 low with drop D | Standard, drop D; no capo | `bass` | Four-string tab or note events |
| Piano / keyboard | A0–C8 | No string tuning/capo | `piano` | Note events (no staff engraving yet) |

String arrays are high-to-low. Capo changes open-string sounding pitches and relative tab fret positions. Maximum physical fret is 24, so available relative fret range is `0..24-capo`; the playable top pitch does not grow when fitting a capo. DADGAD's top range reflects its lowered highest string. Recorded audio/reference playback is **not** automatically transposed by changing a profile or capo.

Changing instrument, tuning, capo or preferred notation clears the current take/comparison, disconnects the old recording input and deletes the specialist session. The original track remains available. This conservative reset prevents a take made under one setup being silently graded as another setup.

## Actual engine routing, not just labels

- Audio uploads include `instrument`, `tuning`, `capo`, and `notation`; omission defaults to standard guitar for backwards compatibility.
- The API independently validates these values against the same catalogue, snapshots the resolved settings into the job and records them in result provenance. Unknown instruments/tunings, inappropriate capo or piano tab are rejected.
- Full mixes select the dedicated `guitar`, `bass` or `piano` output of the pinned **six-source** `htdemucs_6s` model. The actual source list is checked; an `other` stem is never substituted. **The real checkpoint still needs provisioning in this sandbox.** A bass/piano profile does not remove that requirement or prove model quality.
- All three initial profiles explicitly select **Basic Pitch ONNX**. The dispatcher uses that method with profile-specific frequency bounds and filters output note events to the same pitch range. An unimplemented method fails rather than silently selecting another algorithm.
- Editable note choices, server note validation, suggested tab strings/frets and capo checks use the resolved profile. Piano has no string/fret editor or tab view. Preferred note-event notation also hides tab for stringed instruments.
- Chord guesses in the lightweight browser preview are enabled only for the guitar profile. Timing/pitch/sustain comparisons remain **uncalibrated candidates**, not accuracy percentages or physical-technique diagnoses.
- The server's legacy `/api/jobs/{id}/guitar` route remains for compatibility and serves the selected instrument reference. `/api/jobs/{id}/stem` is the generic alias. The `guitar_url` response key is also retained for existing clients.

## Optional tune/check before recording

1. Choose the instrument/tuning/capo above.
2. Connect your microphone or USB audio interface under **Your take**.
3. Enable **Optional: tune / check pitch before recording**.
4. Play a single sustained note. Stringed profiles offer automatic nearest-open-string targets or a manual string selector. Targets include the selected capo.
5. Read detected frequency and cents relative to the target (A4 = 440 Hz). Within ±5 cents is labelled “In tune”. Tuning is optional and does not block recording; detection pauses during recording.

The tuner uses a YIN-style normalised difference detector on the selected input, never uploads tuning readings and never outputs a monitoring tone. It is an experimental single-note helper, not a calibrated hardware tuner. Noise, harmonics, chords, low signal and interface processing can mislead it. Detection is approximately 25–1,500 Hz (subject to selected profile); it does not cover the highest piano keys. Acoustic piano adjustments belong with a qualified piano technician; this is only a pitch/reference check for single keys/digital keyboards.

## Scope and validation

Bass and piano are now selectable and routed end to end with the correct bounds/stem/notation. Their real-world transcription accuracy, low bass intonation, dense piano chords and separation quality **have not been established**. Staff engraving, pedal/expression grading, calibrated scores, five/six-string bass profiles, arbitrary custom tuning, automatic instrument recognition and MIDI-to-reference comparison remain future work. MIDI capture/export is still a separate local path, not instrument scoring.

Tests cover catalogue consistency, guitar drop-D/capo positions, bass E1, piano A0–C8/no-tab, invalid combinations, instrument-aware upload/edit validation, bass routing through the job pipeline, and tuner tones/silence/noise/cents. Browser tests use a synthetic USB source to exercise live tuning and a synthetic isolated exercise through the real ONNX piano-profile workflow; neither constitutes physical guitar/bass/piano or real full-band validation.

```sh
npm test
npm run build
.venv/bin/python -m pytest server/tests -q
BROWSER_EXECUTABLE_PATH=/path/to/chromium npm run test:inputs
BROWSER_EXECUTABLE_PATH=/path/to/chromium npm run test:profiles
```

# Effects library — design note (integration)

## Layout
- `server/fx/renderers.py` — synthetic FX for template building
- `server/fx/features.py` — fixed feature vector
- `server/fx/classify.py` — centroid (+ optional RF) multi-label matcher
- `server/fx/undo.py` — de-reverb + mild OD inverse + acoustic playback
- `server/fx/data/templates.json` — shipped centroids (built from GuitarSet mic + synth FX)
- `server/fx/build_library.py` — rebuild templates / run eval

## Integration into `songs.run_song` / API / UI
1. After guitar stem is chosen, call `fx.match_effects(guitar_audio, sr)`.
2. Attach result to analysis payload as `effects_detected: [{name, confidence}, ...]`.
3. If any of `distortion|overdrive|fuzz|reverb|delay` with conf ≥ threshold:
   - `clean_audio = undo.undo_effects(...)` (optional preprocess before Basic Pitch)
   - Always keep original stem for “amped” playback.
4. After notes exist, enrich each note with `damping=damping_from_decay(...)`.
5. API: `GET/POST .../effects` returns matcher output; `play_clean=true` returns
   `acoustic_playback(notes)` WAV.
6. UI: **Effects detected** panel (chips with confidence) + **Play clean version** toggle
   that swaps the audio element to the acoustic render while leaving notation/tab unchanged.

## Non-goals (v1)
- Plugin-accurate amp/cab IR identification
- Perfect inverse of hard clipping
- Shipping IDMT audio (CC BY-NC-ND)

## CPU
Template build uses ≤8 short (6 s) GuitarSet clips × 12 effects. Matcher is O(F·labels).

# Gaelic motion matching: first slice and remaining work

This implementation is independent of `arena-fc`. It borrows the idea of exact,
normalized pose matching, not its code, data or assets. `src/motion_match.c` is
pure C99. The renderer samples the loaded raylib animations at startup (every
third 60 Hz frame) and normalizes the left/right foot XZ positions and velocities.
It searches only the already-selected destination clip, and only when moving
between the idle, jog, run, sidestep or carry clips. Existing cross-fades, planting,
stride speed and procedural carry remain in use. A failed bake or search falls back
to the original selector. `--model` gets a fresh database from that model, and
`--no-motion-match` disables it. No persistent feature file is used.

The current implementation is **not** a full port of Arena FC's 24-dimensional
motion engine. It does not choose between clips, predict trajectories, perform
periodic rematching, match action entry frames, or use an offline feature bake.
The source GLB's horizontal root motion is stripped, so its poses alone do not
provide real root trajectory data. The existing selector supplies the gait choice.
Action clips and their contact times remain exactly on the existing path; matching
is skipped during actions and jumps. This is particularly important because
`detectContacts()` sets the rules engine's timing and `on_release` positions the
ball. A visually selected clip must not change when a rule or ball release occurs.

## Validation and next stages

- Run `make test`. On a machine with raylib and a display, run `--shots-motion`
  both with and without `--no-motion-match`, inspect the output/screenshots, and
  compare repeated `--bench 600` runs with the same quality setting. Check gait
  transitions, planted foot sliding, carrying, and 30-player frame time. These
  visual and performance checks require a functioning graphics environment.
- Create a versioned offline bake and metadata from licensed Gaelic clips, with
  explicit skeleton/coordinate conventions, contact limb, plant side, action and
  ball-state tags. Validate the baked data against the GLB and fail safely on a
  mismatch. The existing runtime sample avoids mismatched files in the meantime.
- Add real or deliberately authored root/trajectory data, extend the query to
  position and facing predictions, then test hard ball-state filtering and
  deterministic clip/phase selection. Profile exact search before indexing it.
- Add action-specific solo and handpass candidates first, followed by kick, pickup,
  bounce, catch and keeper actions. Align each animation to the authoritative
  action deadline without moving the rules event, and test one release per action,
  contact limb/ball position and interrupted actions. Avoid cross-action matches.
- The shipped GLB has no moving bounce clip. Obtain appropriately licensed Gaelic
  motion before claiming realistic bounce or aerial contests; the Mixamo metadata
  in the source bounce FBX is not evidence of a licence. More varied captures and
  paired-player actions are needed for a complete HyperMotion-like result.

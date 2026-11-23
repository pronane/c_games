# Gaelic motion matching

This implementation is independent of `arena-fc`. The reusable C99 matcher is in
`../shared/arena_motion/`; `src/motion_match.c` adapts it to Gaelic's existing gait
path. Matching searches the already-selected idle, jog, run, sidestep or carry
clip for a suitable entry frame using left/right foot XZ positions and velocities.
Existing cross-fades, foot planting and stride logic remain in control. The shared
core's trajectory queries, action filters and contact-deadline helper are tested
but are **not yet used by Gaelic gameplay**.

## Offline gait bake

With a built game, raylib and a working graphics environment, run from the game
folder (the game changes its working directory to the executable's directory):

```sh
./gaelic_football --bake-motion assets/models/gaelic_player.gfmotion
./gaelic_football --motion-cache assets/models/gaelic_player.gfmotion
```

On Windows use `gaelic_football.exe`. The first command samples the loaded GLB
using the same raylib animation poses and the same bake code as runtime, writes
the cache and exits. It is an offline precomputation, but **currently opens a
window and is not a headless baker**. Use `--model PATH` with both commands to
bake/use a different model. The cache is optional: with no `--motion-cache`, the
game samples at startup; if a cache is missing, malformed or incompatible, it
logs a warning and samples instead. `--no-motion-match` disables matching entirely.

The v1 little-endian binary cache contains the five gait clip IDs and sample times
and eight model-space foot features every third frame. It stores a schema version,
raylib version, a full-model FNV-1a fingerprint, dimension and row count, and a
payload checksum. Loading verifies those, finite values, bounded sizes, and the
expected clip/time layout against the loaded animations before rebuilding the
normalization. FNV is for accidental mismatch/corruption detection, not security.
Bump the cache version if the clip IDs, feature semantics or extraction algorithm
change. Generated caches are local build artifacts, not new motion assets.

This first bake does **not** include action contact/plant annotations or trajectory
features. The current GLB's horizontal root motion was stripped; an honest
trajectory database needs authored or captured data rather than guessed motion.
It is not a full Arena FC motion database, and it does not select a different clip
or perform periodic rematching. No new or unlicensed motion clips were added.

## Release safety

`game.c` retains authority over possession, contact timing and ball flight.
The release notification now takes a `const GameState *`, and the raylib callback
only triggers presentation effects. Previously it overwrote the simulated ball's
position from the last rendered bone, which might be stale, off screen or blended.
The flight now starts at the rules engine's existing position instead. This is an
intentional change from the old rendered-bone origin: a visible gap may occur at
release until a presentation-only contact alignment is built and validated. The
existing `detectContacts()` still sets action timing from the loaded clips at
startup; action matching must not modify that authoritative deadline at runtime.

## Validation and next stages

- `make test` covers rules including single-release and interrupted actions,
  cache round trips/mismatches/corruption, the gait adapter and portable core.
- On a machine with raylib and a display, compare `--shots-motion` and repeated
  `--bench 600` runs with matching on and off. Bake and load a cache using the
  same GLB and compare transitions and performance. Check release contact in
  particular; these graphical checks have not been run in the current sandbox.
- Add versioned action-specific contact-limb, ball-state and plant metadata,
  followed by solo and handpass matching against the authoritative deadline.
  Test the visible ball/limb alignment, interruptions and one release per action
  without letting rendering move the simulation ball.
- Add real or deliberately authored root/trajectory data, then connect the
  portable query and hard ball/action filters. Profile before adding an index.
- The shipped GLB has no moving bounce clip. Obtain appropriately licensed Gaelic
  motion before claiming realistic bounce or aerial contests; Mixamo metadata in
  the source bounce FBX is not evidence of a licence.

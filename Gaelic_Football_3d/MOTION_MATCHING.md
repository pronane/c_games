# Gaelic motion matching

`../shared/arena_motion/` is the reusable C99 matching core. Gaelic's adapters
use it without changing `arena-fc`. The live gait path picks an entry frame of
the already-selected idle, jog, run, sidestep or carry clip. The action path
also matches entries for **handpass and solo**, using the existing dedicated
clips only. It does not select between alternative actions or create new motion.

For each action, startup detects the contact time and limb as before, and bakes
pre-contact entry frames with foot positions and velocities, action, carried-ball
and detected limb tags, and remaining clip time to contact. A search runs when
an action is first observed while in possession. It hard-filters action, clip,
ball state and limb, and accepts only entries whose wind-up can reach the same
authoritative deadline at 0.5–1.8 times the authored speed. If fewer than 0.13 s
remain, metadata is missing, or no compatible row exists, the original action
animation is used. Playback aligns the selected contact frame to the existing
rules-engine clock; interruption or a new action clears the plan. Solo's rules
counter is reset immediately when the action starts; its detected contact time
is used for visual toe contact, **not** as a new gameplay event.

The source GLB's horizontal root motion is stripped. The library's trajectory
query is therefore not enabled in Gaelic, and no trajectories are fabricated.
Only the current two action clips are supported; bounce, pickup, kicks, catches,
keeper actions and paired interactions still use the original selector.

## Offline bake

With a built game, raylib and a graphics environment, run from the game folder:

```sh
./gaelic_football --bake-motion assets/models/gaelic_player.gfmotion
./gaelic_football --motion-cache assets/models/gaelic_player.gfmotion
```

On Windows use `gaelic_football.exe`. Baking loads and samples the GLB through
raylib, writes the cache and exits. It is an offline precomputation but currently
**opens a window and is not headless**. Use `--model PATH` with both commands for
another model. Without a cache, or if it is invalid, the game samples at startup.
`--no-motion-match` disables gait and action matching. A failed action bake or
search falls back to the original clip/time selection.

The v2 little-endian binary cache stores the five gait clips and pre-contact
handpass/solo entries, including action/ball/limb tags and time to contact. The
model fingerprint, raylib version, schema, payload checksum, row counts and
finite values are checked. The game also validates the expected clip, sample
and action/contact layout against its loaded clips and detected metadata before
using the cache. Old v1 caches are rejected and rebuilt at startup; rebake them
with `--bake-motion`. The fingerprints detect accidental mismatches, not hostile
files. Bump the cache version whenever the IDs or extraction semantics change.
Caches are local build artifacts; no new animation assets are added.

## Release safety and visual alignment

`game.c` remains authoritative for action timing, possession and ball flight.
Its release notification is read-only. For a handpass, when a recent rendered
hand pose exists near the launch, the renderer applies a short bounded visual
correction from the hand toward the simulated flight position. This correction
never writes back to the ball state and clears on a new release or possession.
A missing/stale pose or an excessive offset skips the correction. Solo's visible
ball is at the detected toe at its visual contact time. Cross-fades, foot IK and
frame timing can still cause visible discrepancies: these need graphics testing.

## Validation and remaining work

- `make test` covers the rules, release interruptions, cache round trips and
  corruption, action tags, feasible entry selection, deadline alignment,
  presentation-only correction, gait adapter and portable core.
- On a machine with raylib and a display, bake and reload the actual model;
  compare `--shots-motion` and `--bench 600` with matching on and with
  `--no-motion-match`. Inspect hand/ball and toe/ball contact, skipped frames,
  off-screen releases, clipping and 30-player performance. The existing
  `--shots-motion` scrub marks actions as already released, so also exercise
  real handpasses and solos in training; the scrub alone does not validate a
  normal handpass match. These graphical checks have not been run here.
- Add authored/captured trajectory data and more licensed Gaelic actions before
  extending the matcher beyond these clips. The shipped GLB has no moving bounce
  clip; Mixamo metadata in the source bounce FBX is not evidence of a licence.

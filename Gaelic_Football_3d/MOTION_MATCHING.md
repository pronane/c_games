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
animation is used. The matcher also rejects entries whose unblended XZ foot
position error is worse than the original selector at that instant. This is a
conservative proxy, not a guarantee of visual quality or low foot sliding.
Playback aligns the selected contact frame to the existing rules-engine clock; interruption or a new action clears the plan. Solo's rules
counter is reset immediately when the action starts; its detected contact time
is used for visual toe contact, **not** as a new gameplay event.

The source GLB's horizontal root motion is stripped. The library's trajectory
query is therefore not enabled in Gaelic, and no trajectories are fabricated.
Only the current two action clips are supported; bounce, pickup, kicks, catches,
keeper actions and paired interactions still use the original selector.

## Offline bake

The headless raylib 5.5 baker/checker can run on Linux with GCC, GNU ld and
Python 3, without an installed raylib or a display:

```sh
make -C Gaelic_Football_3d test-motion-model
# Or persist a cache from the game folder:
cd Gaelic_Football_3d
make motion_headless
./motion_headless assets/models/gaelic_player.glb assets/models/gaelic_player.gfmotion
```

It compiles only the vendored raylib 5.5 animation loader and uses the same
sampling, metadata detection, cache writer and model validation as the game.
It currently supports self-contained `.glb` models and raylib 5.5 cache files;
a raylib 6 game will reject the cache and use runtime sampling. The checker also
runs rules-input and search probes before returning success. The temporary
cache used by `test-motion-model` is automatically removed.

Alternatively, with the built game, raylib and a graphics environment:

```sh
./gaelic_football --bake-motion assets/models/gaelic_player.gfmotion
./gaelic_football --motion-cache assets/models/gaelic_player.gfmotion
```

On Windows use `gaelic_football.exe`. The game's baking option opens a window,
samples the GLB through raylib, writes the cache and exits. Use `--model PATH` with both commands for
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
- `make test-motion-model` bakes and reloads the shipped GLB headlessly, checks
  old-cache fallback, drives real handpass and solo rules inputs at 30 and
  60 Hz, checks one release / interruption and exercises a simulated culled
  handpass and first observation after release (without rendering). It also
  compares ball physics, possession, carry steps and events with and without
  the presentation matcher. It measures unblended XZ foot position across 16 carry phases. Before the new guard, the
  solo mean error was 0.4012 m for the original entry versus 0.4558 m matched;
  after the guard it was 0.3937 m, with no worse sample by this proxy. The
  synthetic 30-gait-plus-30-action search probe measures search only, not full
  game FPS. CI runs both test commands.
- On a machine with raylib and a display, compare `--shots-motion` and
  `--bench 600` with matching on and with `--no-motion-match`. Inspect hand/ball and toe/ball contact, skipped frames,
  off-screen releases, clipping and 30-player performance. The existing
  `--shots-motion` scrub marks actions as already released, so also exercise
  real handpasses and solos in training; the scrub alone does not validate a
  normal handpass match. These graphical checks have not been run here. The
  manually dispatched **Gaelic motion visual comparison** GitHub workflow builds
  with Xvfb and uploads A/B motion recordings and benchmark logs for inspection;
  it has not yet been run in this session.
- Add authored/captured trajectory data and more licensed Gaelic actions before
  extending the matcher beyond these clips. The shipped GLB has no moving bounce
  clip; Mixamo metadata in the source bounce FBX is not evidence of a licence.

### Player presentation follow-up

A supplied 37-second matching-on motion recording showed ball/hand overlap,
forward-leaning poses and close-ups that can crop the character. The recording
is a scripted scrub, not a normal match. The sampled source jog, run and carry
clips had forward-bending knees, while the stride and foot-plant IK could bend
some knees backwards. Leg IK now retains the authored pole where possible and
uses a model-forward fallback when a new target would reverse it; the two-bone
solver also clamps both too-near and too-far targets. A small, bounded upper
body correction reduces excessive forward lean in locomotion without changing
rules positions. The carried ball now uses the same centre as the full-weight
procedural grip, and the wrist targets are outside the ball.

`test-motion-model` exercises the shipped locomotion clips through the leg IK,
checking finite positions, knee direction and segment lengths, and checks torso
and grip bone-position proxies. These are numerical checks only: they do not
prove that the skinned hand mesh clears the ball or that motion looks natural.
The corrected rendering, foot-plant smoothness and real gameplay actions still
need visual A/B review. Trajectory matching, expanded actions, full 30-player
hardware profiling and the broader graphics work remain outstanding.

A follow-up visual review found the leg still looked too straight. A model-space
probe showed the old stride/plant adjustments brought the hip-to-foot reach
above 94% of the two-bone length in 28 of 41 run samples for each leg (versus
7 of 41 in the source run clip). The procedural stride and maximum reach are
now capped more conservatively; the model test checks the cap for both legs.
This may trade some foot locking for sliding and needs rendered evaluation,
especially at sprint speed. The motion matcher selects clip entries; these leg
IK adjustments are separate from the shared matching library.

A later recording showed a stiff jog, finger/ball intersection and apparent
shorts deformation. The jog now limits procedural stride expansion at lower
speeds, and fades a planted-foot constraint in and out using the shared
`am_smooth` helper. Finger bone *segments*, not just endpoints, are kept outside
an expanded ball in a full-weight procedural grip. The tests cover the fade at
30/60 Hz and segment distances for the shipped model. Neither bone clearance nor
these numerical tests establish skin/ball clearance or natural movement; this
needs fresh rendered A/B review. The shorts are separate skinned meshes. An extra pelvis-only offset has been
removed because it distorted the hip-to-leg hierarchy, but the mesh still
needs deformation/weight inspection; no cloth or mesh fix is claimed here.
Research sources and their code/data licence boundaries are in
`../shared/arena_motion/RESEARCH.md`; no third-party footage or motion data is
shipped or used to train a model.

The visual workflow also has a CMU experiment: it downloads a pinned BVH take,
checks its hash, imports and retargets it with Sprite Forge, and compares the
shipped jog against a temporary in-place candidate under identical quick motion
scripts. This tests real captured locomotion rather than only adjusting a
procedural clip. No candidate is installed or added to the repository; it must
be visually reviewed and is not proof of Gaelic skill or hand-contact quality.
See `../shared/arena_motion/RESEARCH.md` for source terms and limitations.

### Forward-jog direction

The shared gait helper compares low-foot movement over a cycle. For the
forward-jog slot only, clearly forward-moving low feet trigger reverse clip
playback; ambiguous and already-correct cycles retain their authored direction.
This is a heuristic, not a replacement for validated motion capture. Playback,
matching features and their velocities use the same mapping; cache version 3
invalidates older extracted features. The shipped model triggers reversal.
Headless checks establish pose/feature alignment, not visual realism or shorts
mesh deformation. In particular, the shorts' skinned geometry and weights still
need rendered investigation; bone-length checks cannot validate their hem.

Locomotion cross-fades advance the outgoing cycle instead of holding the last
pose, using the same speed-dependent cadence as clip selection. This applies
only between locomotion clips; action and bounce timing remain unchanged. The
headless report includes low-foot velocity and pelvis-relative hand ranges for
candidate comparisons. These are raw clip-pose measurements, not a measurement
of final skinned vertices, ball carrying, ground slip or rendered appearance.

At lower forward-jog speeds (up to 2.2 m/s) the stride adjustment preserves the
captured leg pose; its additional reach ramps in through 3.2 m/s using the
shared cubic easing function. Foot planting remains enabled. This is a
presentation-only heuristic and does not change the player's world motion.
The headless model check also reports low-foot horizontal world-ankle motion
before stride adjustment, after stride adjustment, and after planting, at 30
and 60 Hz. It uses a constant straight-line speed, samples an ankle rather than
a sole vertex, and classifies low feet using the unadjusted clip; it does not
measure rendered slipping, skinned shorts, or general gameplay.

### Jog visual and shorts diagnostics

The manual visual workflow records both the shipped and local experimental CMU
model with their normal tracking camera and, separately, a world-fixed side
camera during frames 120–209 of the same scripted jog. The fixed view makes
field travel easier to judge; it does not automatically quantify foot slip.
The workflow saves the camera logs alongside the videos.

`python3 tools/inspect_shorts_skin.py assets/models/gaelic_player.glb` reports
bind-space low-hem vertices and their mean skin weights by side, for each
shorts mesh. In the current shipped model the two low hems have essentially
matching bind heights and approximately 97% corresponding-thigh / 3% pelvis
weights. This is an approximate bind-space band, not an animated hem or visual
proof; it does not identify the cause of the observed changing shorts length.

`python3 tools/inspect_shorts_motion.py assets/models/gaelic_player.glb`
evaluates the actual GLB jog transforms and linear-blend skinning on the
bind-selected hem vertices. It reports mean and maximum individual-vertex
thigh-local vertical offset ranges, not screen-space or cloth length. For the
first shipped shorts mesh sampled at 60 phases, the mean hem offset ranges are
about 1.4 mm and 0.8 mm; individual vertices reach 7.3 mm and 4.8 mm. The
experimental CMU candidate measured about 2.3 mm mean and 9.9 mm maximum
individual range on each side. These measurements exclude procedural IK,
renderer behavior, camera perspective and occlusion. They do not rule out the
reported visual issue or validate a fix.

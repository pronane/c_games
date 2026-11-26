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

`python3 tools/inspect_shorts_runtime.py MODEL.glb --tool ./motion_headless
--speed 3.5 --fps 60` extends this comparison: raylib 5.5 samples paired
poses before and after the same `lengthenStride` and `plantFeet` routines used
by the game, then the inspector skins the selected hem vertices. It checks
that GLB inverse binds agree with raylib's node-based bind convention. It
compares each vertex's thigh-local Y at the *same time* before and after IK;
this is not a measurement of the hem in world space or on screen. It warms up
for one second and samples three seconds at constant speed on a straight path.
The script excludes full rendering, turns, culling, transitions, other actions,
and any differences in raylib 6. The no-IK control and 30/60 Hz sampling are
tested. In the local experimental CMU jog at 60 Hz, across all nine shorts
meshes, the maximum paired IK change was 1.2 mm at 2 m/s and 2.4 mm at
3.5 m/s for a sampled vertex; mean-hem changes peaked at 0.34 mm and 0.69 mm
respectively. This is limited evidence for those scenarios, not a fix or proof
that the visually reported shorts issue is absent.

The runtime shorts inspector also supports `--scenario turn-transition`.
It synthesizes a straight jog followed by a turn, sprint, jog and stop; it
uses the same gait matcher, raylib 5.5 cross-fade sampling and leg IK as the
frontend. The position, speed and facing inputs are scripted rather than a
rules-engine match. Its report counts each chosen clip, actual cross-fade and
turn frames, and thigh-local per-vertex frame-to-frame movement. Turn frames
are categorized before cross-fade frames when both occur. These steps are not
on-screen hem movement or evidence of a visible pop. At 60 Hz, the local CMU
candidate sampled sidestep, jog, run and idle, with 60 turning frames and 79
cross-fade frames. Across nine shorts meshes the largest single-vertex
thigh-local step was 1.4 mm during turns, 3.7 mm during non-turn cross-fades,
and 6.4 mm during non-turn, non-cross-fade frames; the largest paired leg-IK
change was 4.1 mm. This does not cover actual gameplay, camera perspective,
raylib 6 or occlusion and does not establish the cause of the reported issue.

### Experimental jog arm assist

`--jog-arm-assist` is an **opt-in experiment**, not the default. A shared
helper profiles each hand's forward movement relative to its shoulder and the
opposite knee's forward movement relative to its hip. It enables a bounded
additional shoulder swing only where the source arm motion is small but
already correlates with the opposite leg. Strong, ambiguous and uncorrelated
source motion is left unchanged. The adjustment is phased by the current
opposite leg, fades through locomotion cross-fades, and rigidly rotates each arm
subtree so bone lengths are preserved. It is excluded during ball possession,
jumps and actions, and does not affect simulation or gait selection.

With the local experimental CMU clip, unblended wrist forward ranges relative
to the shoulder change from roughly 0.137/0.110 m to 0.191/0.160 m in the
headless bone proxy; the shipped jog's stronger arm motion is unchanged. This
is not a visual quality, hand-mesh, transition or performance guarantee. The
manual visual workflow records a separate `cmu-jog-arm-assist.mp4` beside the
unmodified CMU version for review. Do not make it the default based on these
numbers alone.

### Experimental relaxed jog fingers

The CMU BVH does not capture fingers. In the locally retargeted candidate,
its hand and finger joint rotations remain almost static and near the target
bind pose; this is not captured hand motion. The candidate's unblended wrist
centres average approximately 0.108/0.113 m forward of their corresponding
shoulders (bone proxy, not a rendered posture measurement). Increasing swing
alone does not change that mean arm posture reliably.

`--jog-hand-relax` is a separate **opt-in** experiment. For nearly static
finger joints only, it blends their local rotations toward the game's existing
idle pose, with a maximum correction of 0.25 radians per joint. It rebuilds
finger descendants parent-first so segments remain connected. Strongly moving
source joints retain their local animation, and both experiments are excluded
from carrying, jumps and actions. The target is a heuristic reference, not
captured CMU finger data or a claim of anatomically correct hands. Headless
checks cover local-angle bounds, bone lengths, unrelated bones, transitions,
and disabled/carry/action/jump guards; they do not check rendered hand mesh,
self-intersection, perspective or visual quality. The visual workflow records
`cmu-hands-before.mp4` and `cmu-hands-relaxed.mp4` with a closer tracking view
from frames 120–209, with arm assist enabled in both. Keep both experiments
off by default until reviewed.

### API-accessible review stills

The manual visual workflow also publishes two machine-readable GitHub check
runs with six downscaled stills per hand comparison video. They are bounded to
60,000 characters per check output and are not committed to the repository.
To retrieve them where the GitHub API is reachable but the artifact CDN is
not, run `python3 tools/download_review_frames.py RUN_ID --out build/review`
from the game directory (with authenticated `gh`). Full videos remain workflow
artifacts; still frames cannot establish fluid motion, timing, or foot slide.
This check publishing requires `checks: write` in the manual `jog-ab` job.

### API-accessible motion previews

The same workflow publishes bounded, three-second, 12 fps compressed MP4
previews for the two hand close-ups and two fixed-camera jog recordings. Run
`python3 tools/download_review_videos.py RUN_ID --out build/review` from the
game directory with authenticated `gh`. Each preview fits within one check
output, has a SHA-256 integrity check, and may be downscaled further to fit.
The hand view is cropped around the upper body; the fixed view is uncropped.
These are useful for inspecting timing, but their reduced resolution and frame
rate cannot replace the original 30 fps artifact or prove foot contact, mesh
intersection, or gameplay quality.

### Fixed-world detail and shared drift diagnostic

The visual workflow also records `original-feet.mp4` and `cmu-jog-feet.mp4`
with the same scripted motion and a closer stationary world-space camera during
frames 120–209. A shorter 15 fps preview is published through GitHub checks;
the player may leave this narrow view, and a compressed preview cannot resolve
all sole or fabric details. The original 30 fps recordings remain artifacts.

The shared `am_contact_drift_sample` utility accumulates horizontal world-space
path distance only across consecutive contact-proxy samples. The headless gait
report now uses it on each adjusted ankle with the existing low raw-ankle height
proxy; it reports a 2D mean speed in addition to the historical 1D forward
metric. It does not establish actual sole contact, rendered mesh clearance, or
correctness in a turning gameplay scenario. No simulation state depends on it.

### Sole detail and hand reference investigation

The visual workflow records matched `original-soles.mp4` and
`cmu-jog-soles.mp4` with a tighter **stationary** world-space view. The API
preview covers only 0.8 seconds at 20 fps and may be further downscaled; it is
not a substitute for the full 30 fps video. The scripted sole view hides selection markers to avoid covering the ground;
camera perspective and compression can still obscure true sole contact.

`tools/inspect_hand_references.py MODEL.glb` compares index-through-pinky bone
geometry across selected non-possession clips. Its spread and middle-joint bend
are direction proxies, not anatomical measures; it excludes the thumb, the end
of each finger and the skinned mesh. The workflow saves reports for both models
and publishes headless candidate before/after and idle-reference measurements
through a check. The headless report calls the reusable `am_direction_angle`
primitive from `shared/arena_motion`. None of these metrics select a reference or
change poses. No alternative is enabled without rendered review and joint/mesh
validation; the previous idle-reference experiment remains opt-in.

The shipped-model scan found that idle at 0.2 s has different left/right
middle-joint bend proxies (about 22 vs 5 degrees), while run and sidestep tend
to be substantially more curled. Keeper poses are purpose-specific; none is
established as a better relaxed running reference. The CMU candidate's
headless test reported index-to-pinky direction spread of 28.9 degrees on both
sides before the existing experimental correction and 13.1/21.5 afterward,
but captured images still look splayed. These are joint proxies, not fingertip
mesh spread or evidence of an anatomically correct pose. The asymmetry and
rendered uncertainty argue against automatically promoting another clip.

### Experimental fingertip mesh probes

`tools/inspect_hand_mesh.py MODEL --tool ./motion_headless --mode N` compares
paired raylib 5.5 jog poses using CPU linear skinning of the model's `v0_body`.
It selects the distal 20% of vertices strongly weighted to each index, middle,
ring and pinky tip bone, and reports adjacent fingertip-cap centroid gaps,
minimum *sampled vertex* distances and maximum paired displacement. It excludes
the thumb, most finger surfaces, triangles and self-occlusion. The result is
not collision detection, anatomical validation or a substitute for a render.
The basic point and skinning operations live in `shared/arena_motion` for reuse.

Mode 0 is an unmodified control; 1 is the existing opt-in 0.25-radian idle
reference; 2 is an additional opt-in **experiment**, `--jog-hand-relax-strong`,
which permits at most 0.5 radians per eligible joint using the same shared
bounded rotation helper. Neither is enabled by default. Both retain the
possession/action/jump and transition guards. The stronger correction is not a
new reference or a validated natural pose, and should not be promoted based on
point gaps alone. The workflow produces three matched hand videos, sampled
stills and mesh proxy reports for comparison.

In workflow run 45854098631, the CMU candidate's mean adjacent fingertip-cap
centroid gaps (left/right) were 43.1/43.1 mm unmodified, 36.2/41.8 mm with
mode 1, and 33.5/45.4 mm with mode 2. The stronger setting moved some sampled
tip vertices by up to 44.5 mm and increased the right-hand gap. The six
close-up stills still showed splayed fingers, with no persuasive overall visual
improvement. These are sampled cap metrics, not triangle collisions, and the
three captures are not proof of frame-perfect comparison. Do not promote the
stronger setting on this evidence; a more suitable, validated hand reference
and mesh-level intersection checks remain open.

### Mirrored-reference experiment

`--jog-hand-relax-mirrored` is a separate opt-in experiment, capped at 0.25
radians per joint. It uses the existing idle left-hand local finger reference
on the left and an X-reflected copy on the right, using the shared quaternion
reflection helper. The adapter checks matching bone and parent names, very low
jog finger motion and approximate mirrored source local rotations; if a right
joint fails these checks it receives no local correction. These heuristics do
not prove mirrored rig bases, anatomy, triangle clearance or visual quality.
Mode 3 in the fingertip mesh tool evaluates this experiment. Carry, jump,
action and locomotion transition guards are the same as the other prototypes.
All remain off by default; no motion capture finger data is being claimed.

Run 45855729295 found all 15 candidate right-hand joints eligible for this
mirrored experiment. Mean adjacent fingertip-cap gaps were 43.1/43.1 mm before,
36.2/41.8 mm with the original idle reference and 36.2/36.2 mm with the
mirrored reference (left/right). This shows improved *proxy symmetry*, not proof
of natural hand shape or a reduction in intersections; the sampled close-ups
still show open, splayed fingers. Maximum sampled tip displacement in the
mirrored case was 18.3 mm. Keep it experimental pending better reference and
surface/visual evaluation.

### Authored curl and sampled finger-surface check

`--jog-hand-relax-curled` is an opt-in, authored procedural reference (mode 4),
not external motion capture or a claim of a natural pose. Starting from the
mirrored idle reference, it composes local-X offsets on the four named finger
chains (not the thumb), for joints with the existing stillness and mirrored
source guards. Per-joint deviation from the jog is capped at 0.35 radians. The
local-X axis and offset choices are rig-specific, not general anatomy; moving
source joints are preserved, and possession/action/jump/transition guards are
unchanged. Shared `am_rotation_compose_local` supplies only the generic math.

`inspect_hand_mesh.py --surface` also skins selected proximal/distal finger
triangles from `v0_body` and tests pairwise overlap across five fingers at 12
sampled clip phases, using the shared floating-point triangle-overlap helper.
It intentionally excludes weakly finger-weighted and palm triangles, so it can
miss intersections, containment, self-overlap within a finger or collisions
between phases. Contact/touch within numerical tolerance counts as overlap.
This is a screen for selected surfaces, not proof that the mesh is collision
free or that a pose is anatomically correct. Neither correction is default.

In run 45857933327, the candidate's mean fingertip-cap centroid gaps were
43.1/43.1 mm before, 36.2/36.2 mm with the mirrored idle reference and
30.9/30.9 mm with the authored curl (left/right). Max sampled tip displacement
was 33.4 mm. The selected-triangle screen found zero pair overlaps in 12
sampled phases for both the raw CMU pose and the curled pose; this does not
cover the excluded surfaces, between-frame motion or containment. Retrieved
close-up stills show noticeably more curled, less open fingers than before,
but this is not an anatomical or motion-quality verdict. Keep the experiment
off by default until it is reviewed in full-resolution motion and broader
scenarios.

### Curled-hand transition and guard investigation

`tests/hand_transition_tests.py` drives the raylib 5.5 presentation blend and
hand correction through scripted idle, jog, run, carry, jump, handpass and solo
states at 30/60 Hz. Guarded states must be exact no-ops. It reports the largest
per-frame change in the *local correction quaternion*, including state
boundaries; this isolates the added hand correction, not the rendered pose or
actual gameplay. At 30 Hz on the shipped model the hard guard switch removed up
to about 20 degrees of correction in one frame when carrying, jumping or
starting an action; an unguarded jog previously also resumed without a fade.
Guard onset stays immediate because delaying it could interfere with ball or
action posing. The subsequent re-entry ramp is documented below. The curled
experiment is not ready to default on.

With `--surface`, the script also checks selected skinned finger triangles at
one mid-state sample for each scripted state; guarded samples must match the
uncorrected geometry. This is not complete mesh, live gameplay, continuous
collision or visual validation. The workflow publishes 1.2-second 24 fps
closer hand crops through the API; original 30 fps videos remain artifacts.

In candidate run 45860524131, the synthetic guard switches produced an
approximately 20.08 degree one-frame local-correction removal at both 30 and
60 Hz, despite exact no-op behavior during carry, jump, handpass and solo.
The selected-triangle mid-state scan also reported overlapping triangle pairs
in the unmodified run, carry and solo clip poses; adjusted and raw counts were
identical at those samples. These are partial headless clip/blend poses without
ball IK or a live match, so they are a warning to investigate, not a diagnosis
of the complete rendered hand. The detail previews were retrieved at 480 pixels
wide and 24 fps; sampled images show a less-open curled pose, but neither the
full-resolution video nor transition motion was visually verified here.

### Guarded re-entry ramp

The opt-in curled mode uses the shared `am_guarded_fade` helper to reintroduce
its correction over 0.20 seconds after an exclusion ends. Guard activation
still resets the envelope immediately to zero, so possession, action and jump
poses remain exact no-ops. The envelope also resets on match/training start and
when a player is hidden or culled, preventing stale re-entry after missed
frames. The ramp multiplies the existing locomotion blend; modes 1–3 and
simulation state are unchanged. A 30/60 Hz scripted regression checks the
previously abrupt jump-to-jog correction re-entry. Abrupt **guard onset** still
exists by design and needs an action-aware solution and rendered validation.

Candidate run 45862807573 reduced the scripted jump-to-jog first-frame
correction change from 20.08 degrees to 1.49 degrees at 30 Hz and 0.40 degrees
at 60 Hz. Carry, jump, handpass and solo still remained exact no-ops, while
entry into those guards continued to remove up to 20.08 degrees in one frame.
These are local-quaternion correction deltas in a synthetic presentation
scenario, not proof of visually smooth real gameplay or full mesh clearance.

### Scripted cradled-hand surface screen

`tools/inspect_hand_grip.py MODEL --tool ./motion_headless` generates and
verifies actual bind rotations from the GLB, runs 12 hand-picked standing,
carrying, solo, handpass, catch and pickup clip states through the frontend's
`balanceTorso` and `cradleBall` functions, and skins selected finger surfaces.
Its paired curled/disabled outputs must be exactly equal while possession or
action guards apply. The workflow also checks the generated bind rotations
against raylib 5.5's actual renderer-loaded bind pose.

The surface report covers selected triangles only. Where normal non-action
carrying gives a valid cradle centre, it also screens the selected triangles
against a radius-0.11 m sphere using a shared point-to-triangle distance helper.
It deliberately omits the sphere for action states: `carriedBall` uses a
different, time-dependent ball position there. This is a small synthetic set,
not real input, complete mesh intersection, live ball physics, animated
transitions or rendered validation; partial cradle blends can also obscure
whether an overlap comes from the clip or procedural adjustment.

# Arena Motion: portable C core (early stage)

A presentation-only C99 library, independent of raylib, Godot and sport rules.
It follows Arena FC's pose/trajectory matching approach; it is not EA HyperMotion
and does not link to or modify `arena-fc`. Compile `arena_motion.c` and include
`arena_motion.h`; link the platform math library where needed. The Gaelic game is
its first client, through a small adapter that preserves its existing gait matcher.

## Contract

- Rows contain an application-defined non-negative clip, category, ball state and
  action ID, clip time in seconds, and 24 raw-unit float features. The caller is
  responsible for using a consistent facing-root XZ coordinate system and for
  providing correct animation sample data. Row IDs are not portable between games.
- Features follow the layout used by Arena FC: left/right foot positions and
  velocities, root XZ velocity and yaw rate, predicted positions and facings at
  0.2, 0.4 and 0.6 seconds, and seconds until contact (1.5 means no contact).
  `am_build_features` implements its damped-pursuit query; it does not extract
  trajectories or poses from animation assets.
- Initialize, add validated rows, optionally change non-negative weights, and
  finalize to compute standard deviations. Queries use exact normalized weighted
  squared distance; specified IDs are hard filters, `AM_ANY` is a wildcard, and
  ties resolve in insertion order. Adding a row invalidates normalization.
- `am_action_time` maps an authoritative action clock to clip time while keeping
  the requested contact deadline. It has no gameplay side effects; a game must
  still own release, interruption, limb/ball alignment and timing policy.

`AMDatabase` owns a bounded array and is relatively large; allocate it statically
or on the heap. The caller owns all state; concurrent reads of a finalized,
unchanged database are safe. An application must validate its own asset skeleton,
feature meaning, ID mapping, contact metadata and provenance. The API does not
load or serialize data, choose animations, blend poses or provide IK.

Run the portable and Gaelic adapter tests with `make -C Gaelic_Football_3d test`.

## Current integration limits

The Gaelic adapter uses foot features to hard-filter the selected gait. For
handpass and solo it also uses the contact-time feature and action/ball/limb
filters, with a predicate to reject entries that cannot reach the deadline. Its
in-place GLB does not contain real root trajectories; no fabricated trajectory
is passed off as captured motion. The 24-dimensional trajectory query has unit
tests but is **not live in Gaelic**. The optional v2 cache includes handpass
and solo entry metadata. More action and trajectory metadata, additional licensed
clips, and visual/performance validation remain future work. See
`Gaelic_Football_3d/MOTION_MATCHING.md`.

`am_smooth` is a frame-rate-independent exponential scalar approach suitable
for presentation weights, such as fading an IK foot lock in and out; it is not
motion prediction or a learned model. See `RESEARCH.md` for external references
and the difference between their code and data licences.

`am_contact_drift_sample` is an optional renderer-independent diagnostic for
horizontal world-space contact-proxy drift. Call it once per sample and per
foot with positions, elapsed time and a caller-provided contact flag; divide
accumulated path distance by accumulated seconds to obtain mean speed. It
excludes intervals across contact gaps or invalid samples. It does not detect
contact, drive the simulation or correct animation, and results are only as
meaningful as the caller's positions and contact proxy.

`am_direction_angle` safely measures the angle between caller-supplied 3D
directions. It is usable for diagnostics such as comparing hand-joint segment
bends; it does not classify anatomical plausibility or inspect a skinned mesh.

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

The Gaelic adapter uses only the first eight foot features and hard-filters the
existing selected gait. Its in-place GLB does not contain real root trajectories;
no fabricated trajectory is passed off as captured motion. The 24-dimensional query,
category/action filters and contact-deadline helper have unit tests but are **not
live Gaelic trajectory or action matching yet**. A versioned offline bake and
asset validation, Gaelic contact metadata, safe integration with the existing
release callback, additional licensed clips, and visual/performance validation
remain future work. See `Gaelic_Football_3d/MOTION_MATCHING.md`.

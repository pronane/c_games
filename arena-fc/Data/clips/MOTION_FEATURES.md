# Motion feature bake (schema v2) — pose-level motion matching

`motion_features.json` is an offline, presentation-only feature table derived from the
shipped `soccer_rig.json` poses and `clip_manifest.json` metadata. Rebuild it with:

```sh
python3 Tools/build_motion_features.py
```

**Schema v2 covers every clip**, not just locomotion:

- looping clips (gaits, keeper stances, idles) contribute every frame;
- one-shot clips contribute their *entry frames* — up to the ball contact, or the first
  35% when the clip has no contact.

The 24 dimensions are:

- facing-root XZ foot positions and velocities;
- root velocity and yaw rate;
- three future root positions and three future facings (0.2, 0.4 and 0.6 s ahead);
- **`time_to_contact`**: the seconds of wind-up left before that frame's ball contact.
  It is 1.5 when no contact lies ahead.

Rows carry the payload `(clipId, frameIndex, phase, category, ballState, styleTag)`.
`styleTag = "dedicated"` marks clips authored for one engine action (skills, chip,
trivela, bicycle, punch ...). A category search never returns these clips; only a
query that names the clip does.

The table drives live selection. `MotionEngine.Database` is set by the Godot
`MotionDriver`. The engine searches the table in two cases:

- **On every clip switch.** The search finds the best frame to enter, given the pose
  the body is in, the path it is about to take and, for ball actions, the time the
  simulation has left before it strikes the ball.
- **About ten times a second for running cycles.** The search finds the best gait and
  phase.

The old rule selector started every action at frame 0 and fast-forwarded the wind-up.
It still runs when no table is loaded.

Measured over 2 minutes of an 11-a-side AI match (`MatchEngine`, seed 7):

| | Rule selector | Motion matching |
|---|---|---|
| Ball-action playback speed | 2.07x average, >2x on 70% of frames | 0.87x average, >2x on 1% |
| Clip switches per player per second | 5.2 | 3.8 |

The simulation is untouched. Selection is presentation-only, and the search is
exact, deterministic brute force over about 1.3k rows.

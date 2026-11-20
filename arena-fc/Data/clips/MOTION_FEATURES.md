# Motion feature bake (schema v1)

`motion_features.json` is an offline, presentation-only feature table derived from the
shipped `soccer_rig.json` poses and `clip_manifest.json` metadata. It contains only
looping locomotion clips; kick, pass, tackle, dive, and other event-driven actions are
not searchable candidates. No pose assets are modified or added.

Rebuild it from the current rig data with:

```sh
python3 Tools/build_motion_features.py
```

The tool is deterministic and uses only the Python standard library. Its rows are
sorted by clip ID and source frame. `featureSchemaVersion` and the ordered `layout`
are validated by the pure-C# `MotionDatabase` loader; change the schema version when
the dimension order or interpretation changes.

The 23 dimensions are facing-root XZ foot positions and velocities, root velocity,
yaw rate, three future root-position samples, and three future facing samples. The
future horizon is 0.2, 0.4, and 0.6 seconds. Because the shipped pose clips are
mostly in-place, the bake uses each clip's authored preferred speed (and turn rate
when available) as a deterministic root-motion proxy when animated root translation
is negligible. Per-dimension z-score statistics are
baked once, then group weights are applied by exact search. Rows retain `(clipId,
frameIndex, phase, category, ballState, styleTag)` payloads for stable tie-breaking
and hard context filtering.

`MotionQuery` and `MotionDatabase` are Core-only infrastructure in this phase. They
are covered by tests but are intentionally not wired into live selection yet; the
existing rule/phase selector, simulation outcomes, and contact-timed one-shots remain
unchanged. VQ/PQ/RVQ are deferred until profiling shows a feature-table cost.

# Gameplay recovery: first implementation and verification contract

Cosmetic/post-processing work is paused. This batch addresses the three priorities in `reviews/aussies-gameplay/GAP_ANALYSIS.md`. It is an implementation candidate, **not visual acceptance**.

## 1. Ball readability and camera

- Ball presentation is separate from the simulation radius: yellow leather where the material is named `leather`, visual enlargement bounded to 2.5×, and a high-contrast screen-sized locator. The locator is intentionally visible through occluders; it identifies the ball, not a physically visible ball surface. Its transparent canvas is 14 CSS px across, with the actual outlined ring about 9.6 px. Camera distance cannot make this locator arbitrarily small.
- Other players' team rings are subdued to stop them dominating ball location.
- Camera fitting is planned before easing, with a conservative inner region. Distance has a hold period and slow push-in. Live ball has priority; only nearby selected players enter the planned fit. A distant selection uses the existing offscreen arrow instead of forcing an enormous view.
- Emergency recovery is ball-only and counted. It can still snap on teleport/extreme situations; counts and per-frame camera positions are recorded for diagnosis. Celebrations remain exempt and are labelled separately in capture data.
- This replaces the previous requirement that both ball and selected player must always be in-frame. The workflow explicitly opts into that policy, still requires player observations, and reports player visibility rather than silently treating missing data as success.

## 2. Facing and controller

- Player creation and update now share one model-yaw conversion. Tests prove that the declared model -Z forward axis maps to sim heading in all four quadrants. Actual asset appearance still needs capture review.
- Velocity changes are bounded in m/s²; turning is bounded in rad/s and slows at running speed. Heading disagreement reduces target speed so a large reversal brakes before accelerating in the opposite direction.
- This is a kinematic sports controller, **not** a new rigid-body character solver. Body overlap separation still exists. It does not author missing pivot, backpedal, contact or stop-start animation clips. Shared AME, playback caps and optional planting remain presentation tools; planting is still off by default.

## 3. Team shape and stoppages

- Contest/receiving/marking jobs persist for 0.8 s, with immediate replanning on holder changes. Two contest slots per team, distinct short/outlet destinations and unique defensive marking assignments replace per-frame ranking in the normal sim path. Role homes have distinct offsets.
- Protected restarts now exclude human as well as CPU tackles. The CPU commit timer belongs to a specific tackler/carrier pair; switching candidates cannot inherit a nearly completed attempt. Stale pre-disposal carriers cannot be tackled after possession changes.
- CPU wrap range is 1.95 m (human range retained at 2.15 m), above body separation but below the previous 2.3 m reach.
- Normal tackles are explicitly standing wraps. They no longer randomly invent high contact, a push in the back, or an incorrect disposal. The rules engine and its illegal-contact decisions are unchanged. This is **not** a complete geometry-based illegal-tackle system: high/push/incorrect-disposal actions need explicit action/contact modelling before this controller should generate those flags.
- No free-kick laws were disabled; prior-opportunity logic is unchanged and remains a separate fidelity limitation. No arbitrary whistle mute was added. Live time, free events by reason, restart events, attempts/misses, recent tackle outcomes and actual audio whistle triggers are separately counted.

## Repeatable workflow output, without repeated user uploads

The Motion A/B workflow keeps its experimental SwiftShader status. The match leg:

1. Waits for an explicit first-render readiness flag, rather than assuming HTML load plus 15 seconds means game readiness. Readiness/load/capture failures exit with an error.
2. Drives a shared fixed input trace (straight run, cut, reversal, stop/kick, handball, selection/tackle inputs) through the normal match code. Each screenshot advances exactly 30 fixed simulation ticks. 36 frames at 2 fps represent 18 simulation seconds, independent of rendering speed.
3. Saves per-frame JSON: seed/tick, ball projection/pixel size, camera position/mode/emergency count, selected-player heading/model yaw/velocity, crowd count and tackle/stoppage/audio diagnostics.
4. Publishes aggregate measurements and **six bounded JPEG previews as check annotations**. These are game-only low-resolution frames, not desktop recordings. This provides an API-accessible visual fallback if the artifact-download host is blocked. Full PNGs, states and MP4 remain in the artifact.
5. Fails missing/short capture data, incorrect tick increments or normal-play ball-centre framing failures. Readability/animation/team quality are not certified by this geometric gate.

Agent-side retrieval:

```sh
cd aussies_rules_3d
bash tools/review_workflow.sh RUN_ID
```

This retrieves job results and annotations with `gh`, reconstructs annotated previews as local JPEGs, then attempts full video download. If download fails, the output says explicitly that video was not reviewed. No credentials are requested/stored by the script. Low-resolution previews allow frame-based diagnosis, not proof of smooth continuous motion or audio quality.

The seeded simulation audit is also published as API-readable annotations in `ab-metrics`. It reports three 60-second seeds, event reasons, local density and backwards-facing samples. It does not invent realism thresholds or call marks/boundary awards tackle fouls. Browser-only whistle counts are not inferred from simulation events.

### Actual diagnosis retrieved from the previous workflow

Run `45417811569` (post-PR #268) passed build/metrics but failed visual-ab. All three captures and MP4 assembly completed. Its API annotations specifically reported **missing/insufficient visibility samples** for the LOD and match logs. That is a data-coverage failure, not reported evidence of out-of-frame ball values. Video download was retried and blocked by the artifact host. Startup readiness is now checked, but this is not a confirmed diagnosis/fix until a fresh run succeeds.

## Local verification and comparison

`node scripts/check.mjs`: TypeScript, **178 tests**, production build and both asset-contract checks pass. Shell syntax, JS syntax, workflow YAML parse and `git diff --check` were also checked.

A local numerical comparison used source from branch HEAD `440626d` and this working tree, identical input trace/seeds, 60 simulated seconds per seed. No branch switch or baseline source modification was involved. This is a simulation comparison, not before/after video or human acceptance:

| Seed | Live seconds before → after | Restart events before → after | Free events before → after |
|---|---:|---:|---:|
| 11 | 41.55 → 46.88 | 5 → 3 | 4 → 0 |
| 42 | 44.23 → 52.37 | 5 → 2 | 2 → 1 |
| 123 | 38.95 → 51.78 | 3 → 4 | 0 → 1 |

Free events include marks and boundary awards; lower is not inherently better. One seed has more restarts. Three scripted seeds cannot establish natural football, appropriate pressure, tactical intelligence or a correct foul distribution. The initial intermediate implementation also had mixed live-time results; the table is the final local iteration with persistent defensive assignments.

## Still owed before calling the reported problems fixed

- Push only with user permission, run the updated workflow, retrieve annotations/previews and inspect actual output; no remote success is claimed now.
- Inspect camera continuity, visibility/locator intrusiveness, actual mesh facing and turns in the captured sequence. Tune failures rather than merely raising thresholds.
- Continuous video and real GPU play remain necessary for motion feel, occlusion/readability and frame pacing. Record wall-clock frame timings separately from scripted simulation time (already kept separate).
- Broader scenarios, authentic turn/contact assets, movement/contact physics, prior-opportunity fidelity and calibration against real Australian-rules footage remain open. This batch does not claim parity with commercial sports games.

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

- Contest/receiving/marking jobs persist for 0.8 s, with immediate replanning on holder, phase and active-roster changes. Two contest slots per team, distinct short/outlet destinations and unique defensive marking assignments replace per-frame ranking in the normal sim path. Role homes have distinct offsets.
- Protected restarts now exclude human as well as CPU tackles. The CPU commit timer belongs to a specific tackler/carrier pair; switching candidates cannot inherit a nearly completed attempt. Stale pre-disposal carriers cannot be tackled after possession changes.
- CPU wrap range is 1.95 m (human range retained at 2.15 m), above body separation but below the previous 2.3 m reach.
- Normal tackles are explicitly standing wraps. They no longer randomly invent high contact, a push in the back, or an incorrect disposal. The rules engine and its illegal-contact decisions are unchanged. This is **not** a complete geometry-based illegal-tackle system: high/push/incorrect-disposal actions need explicit action/contact modelling before this controller should generate those flags.
- No free-kick laws were disabled; prior-opportunity logic is unchanged and remains a separate fidelity limitation. No arbitrary whistle mute was added. Live time, free events by reason, restart events, attempts/misses, recent tackle outcomes and actual audio whistle triggers are separately counted.

## Repeatable workflow output, without repeated user uploads

The Motion A/B workflow keeps its experimental SwiftShader status. The match leg (now restored to the shipped asset, independent of LOD-capture success):

1. Serves the production bundle over local HTTP to Electron on the runner, then waits for an explicit first-render readiness flag, rather than assuming HTML load plus 15 seconds means game readiness. Readiness/load/capture failures exit with an error.
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

`node scripts/check.mjs`: TypeScript, **190 tests**, production build and both asset-contract checks pass. Shell syntax, JS syntax, workflow YAML parse and `git diff --check` were also checked.

A local numerical comparison used source from branch HEAD `440626d` and the first candidate `18efb2b`, identical input trace/seeds, 60 simulated seconds per seed. No branch switch or baseline source modification was involved. This is a simulation comparison, not before/after video or human acceptance:

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


## Follow-up batch after PR #272 opened

- Contest jobs now invalidate on phase and roster changes; protected phases assign shape jobs rather than retaining pressure/receiving roles. CPU tackle timers are cleared through loose-ball gaps as well as restart guards.
- The match capture records actual selected-player rendered-root direction and contact-conditioned world-foot displacement. It reports maximum continuous backwards travel above 3 m/s, AME availability, selected clip, contact-foot speed and team replans. A 0.5-second sustained-backwards limit is an engineering regression guard, not a researched biomechanics threshold. Missing motion observations or AME fallback fail the scripted acceptance check. Contact flags come from clip metadata; foot-speed measurements are not proof of genuine planted-foot contact.
- Run `45720126542` passed `ab-metrics`; original attract capture completed, LOD capture failed, and the dependent match leg was skipped. No match preview was available, so priorities 1–3 remain visually unaccepted. The follow-up makes capture legs independent after the initial build, restores the shipped model before match capture, and publishes startup/error excerpts even when no state is captured.
- The capture harness uses an HTTP origin matching the browser build rather than relying on file-protocol fetch behaviour. This is tested with real HTTP requests for HTML, GLB and JSON, but is not claimed as the confirmed cause of the LOD failure.
- Retrieval was tested against the real run. The installed older `gh` lacks `--slurp`; annotations now use paginated JSON-lines compatible with that client.
- New seeded audits after phase-aware role handling include seeds with no tackles. Less congestion/fewer foul calls alone is not sufficient acceptance; pressure, tackle frequency and disposal opportunities still require capture review and broader calibration.


## Capture evidence and preview transport follow-up

Run `45721534269` at `b8d40e6` passed **all jobs**, including visual-ab. All three capture legs completed. The scripted shipped-asset match reported 36 states (ticks 30–1080), zero tick errors, zero ball-centre framing failures, zero emergency corrections, no AME fallback and zero sustained backwards time for the observed selected player. It recorded two whistle triggers, zero free events and zero tackle attempts in this short scenario. These are observed values, not evidence of realistic pressure/tackle frequency.

The run also recorded **zero contact-foot samples**. Inspection confirmed the shipped motion manifest's plant-frame arrays are empty. This is a real metadata/validation gap: foot sliding remains unverified, and no fake contacts were inserted simply to produce a passing number.

The first API preview attempt was truncated: each annotation message was limited to 4096 characters, producing 3072-byte JPEG fragments with grey incomplete image areas. Those fragments are **not rendering evidence**. Preview publication now uses messages below 3 KB, at most five parts per image, one image per workflow step, SHA-256 integrity validation and JPEG start/end validation. Missing/truncated/duplicate/altered parts are rejected rather than displayed. Round-trip tests simulate the observed 4096-character limit. Startup excerpts exclude capture-state records so actual startup failures stay readable.

An optional `workflow_dispatch` input `review_run` downloads an already completed run's artifact **on the GitHub runner**, repacks its original frames and republishes integrity-checked preview annotations. It does not advance or re-verify gameplay. This allows recovering source evidence without repeated full captures or asking users to upload files. The retrieval script rejects the old unverified format.

Priorities 1–3 have implementation and automated regression coverage; visual acceptance remains open until intact previews/video support it. Foot-contact metadata and convincing movement/contact animation remain explicit outstanding gaps, not completed checkboxes.


## Findings recovered without a user upload

Evidence-only run `45723581795` successfully republished the original frames from gameplay run `45721534269`. All six previews were reconstructed locally with matching SHA-256 hashes and inspected. This repairs the evidence transport; it is **not a fresh gameplay run**.

The intact previews show a remaining composition problem around source frames 018/024: substantial empty pitch/stands despite successful ball-centre framing. Inspection found the camera could pitch toward an elevated ball without retaining ground context. The AI also waited for a moving loose ball to come within 9 m instead of committing authorised aerial contest players to the drop point.

Follow-up implementation:
- Ball and its ground projection are planned/protected together; desired camera height stays above the live ball, rather than tilting toward stands to centre it. This is covered across all five views and set shots in the projection integration test. Emergency correction counts remain visible; no continuity claim is made from these tests.
- Contest assignments rank players against the predicted/clamped drop point for high loose balls. Assigned contest players can begin running there before the current ball is nearby. Receiving lanes use the same anchor. A regression fixture places the current ball 75 m behind the suitable receiver and verifies movement toward the future landing point instead.
- New capture states record ground projection and world ball coordinates. Normal fresh captures now check ground context too. Evidence-only republication explicitly labels legacy source data rather than retroactively demanding a field that old captures did not record.

This change still needs a fresh workflow capture. Ball readability/continuity, natural movement and team/contact behaviour are not all visually signed off. Empty plant metadata, full pivot/contact animation coverage and pressure/tackle-frequency calibration remain outstanding. Nothing in a green numeric gate overrides these limitations.


## Boundary-camera root cause from per-frame evidence

Fresh run `45724096115` passed all jobs, with 36 states, zero ball/ground framing failures and zero emergency corrections. Its intact previews still showed poor boundary composition. This means the ball+ground numeric guard was insufficient; it is not treated as visual acceptance.

Compact state annotations were added and evidence-only run `45725287383` republished the exact source states. At source frame 018 the phase was `throwIn`, ball Z was 50.44 m and camera Z was 47.27 m; at frame 024 the ball was on the ground, Z 50.36 m, while camera Z was 41.31 m. Thus the camera was **inside** the near wing, looking outward toward the ball/stands. This was not simply an elevated-flight problem.

The next correction keeps the broadcast camera outside the touchline (at least boundary half-width +12 m), with a damped lens to maintain action scale rather than moving the camera through the near wing. Other intentional chase views retain their own policies. A boundary fixture asserts the outside-side invariant. Captures now record/guard that invariant explicitly.

Around-ground ball-ups/throw-ins also reserve four distinct inward staging positions (two per team), without granting tackle permissions. Previously the blanket non-live shape policy could send everyone home during a boundary restart. Centre restarts still retain their home/6-6-6 policy. This is regression-tested; full team-flow calibration is not claimed.

These final boundary/staging changes need a new capture before visual acceptance. Priorities 1–3 are **not all signed off**: the foot-contact metadata gap and natural transition/contact animation remain open, and a green geometric check alone has repeatedly proved insufficient.

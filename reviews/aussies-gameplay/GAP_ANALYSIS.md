# Gameplay review: readability, movement, team play and stoppages

## Evidence and limits

Input: user attachment `image-1.jpeg`. Its bytes identify an ISO MP4 container, not a JPEG. A byte-for-byte copy is available locally as `gameplay-review.mp4`, opened in the file viewer. FFmpeg decoded it successfully: 49.72 seconds, 1280 × 666, H.264, approximately 25 fps average, AAC stereo audio. No transcoding was necessary. The source attachment was preserved.

Review method: decoded timeline stills at three-second intervals, closer code inspection, and the user's live-play observations. This is **not** a claim of continuous real-time playback/listening by the agent. Audio exists, but no exact whistle count was measured. Backwards running, freezing and continuous whistles are user-reported symptoms; stills alone cannot establish their duration or frequency. Recording frame rate is not game FPS. The exact game commit, selected camera controls and runtime flags in the recording are unknown.

Code baseline: working branch at `440626d` (includes the merged camera/capture changes). Repository documentation and open PR metadata were inspected. No gameplay implementation was changed during this review. Media is ignored locally rather than committed.

AME below means **Arena Motion Engine**, including its C core, C# origin and TypeScript port. This does not assume those implementations or integrations are identical.

## Executive finding

**This is a gameplay-credibility failure, not a colour-grading problem.**

The improved colours do not compensate for an unreadable ball, implausible facing/locomotion, mechanically crowded positioning, unstable composition and repeated stoppages. Pause visual-polish work. Fix these five issues before adding more stadium detail, bloom, career features or commentary.

My previous camera work addressed a narrow geometric condition: subject centres inside a safe NDC rectangle. Its tests do not establish readable action, a stable camera or convincing football. Presenting that as the next substantial gameplay improvement was insufficient. The supplied evidence is a failed visual acceptance review, not something to dismiss because unit tests pass.

## Timeline evidence (approximate recording times)

These are sampled windows, not exact event boundaries or a complete event count.

| Window | Visible evidence | What it supports / does not prove |
|---|---|---|
| Opening ~0–3 s | Large `PUSH IN THE BACK!` overlay, high/steep camera, several overlapping player rings, scoreboard 0–0 | A foul interruption and poor visual hierarchy. Does not establish whether this particular decision was legal. |
| ~6–9 s | Steep overhead composition, controlled player separated from groups; very small dark ball-like detail on turf | Ball acquisition is difficult even in frame; highlights are dominated by player rings. |
| ~12–15 s | Much wider/lower stadium view, several tight multi-player groups; scoreboard still 0–0 | Composition and subject size differ substantially from opening; clustering is not limited to one contest. Player input may contribute to camera changes. |
| ~18–21 s | Score now 1.0 (6)–0.0 (0), ball-up hint, wide field view | A goal and restart occurred; this is not a wholly frozen simulation. The still sequence cannot quantify intervening freezes. |
| ~24–36 s | Repeated adjacent pairs/groups across lines and around action, camera shows substantial stadium area | A two-chaser cap and overlap separation have not delivered convincing spatial organisation or broadcast readability. |
| ~39–42 s | `HOLDING THE BALL!` overlay, further nearby groups | At least another distinct foul type is visible. Cannot derive a per-minute infringement rate from these stills. |
| Final seconds | Windows application-switcher overlay | Exclude this section from in-game freeze/performance judgements. |

## Ranked gap analysis

### P0-A — The ball is technically rendered, functionally unreadable

**Observed:** difficult to reliably locate the football among rings, pitch stripes and players. It should not require frame inspection to find the object of play.

**Code evidence:**
- `aussies_rules_3d/src/main.ts` loads the ball and applies a fixed `0.19` scale. The intended long dimension is about 0.275 m.
- `tools/blender/gen_ball.py` uses dark reddish-brown leather and darker seams.
- The ball has a blob shadow but no guaranteed screen-space readability treatment.
- Camera framing checks a subject centre, not projected ball diameter, colour contrast, occlusion or whether a human can locate it. It even uses a clamped ball height rather than the exact mesh silhouette.
- `render/players.ts` draws numerous bright, large team rings. These compete with the actual ball.

At 80 m camera depth, 46° vertical FOV and a 666-pixel image height, an ideal 0.275 m feature spans only about **2.7 pixels** (shorter axis smaller still). This is a projection illustration, not a measured diameter in the recording. Geometric realism alone is not presentation readability.

**Required:** retain the physical ball for simulation, but introduce an explicitly presentational readability policy: high-contrast approved colour, restrained silhouette/halo or optional locator, distance-aware visual scale with a strict cap, landing indicator during long flight, and reduced nonessential player markers. Never enlarge collision radius to solve a rendering problem.

**Acceptance:** annotated ground/flight/held-ball captures at 720p/1080p and portrait; measure projected major/minor diameter and occlusion, not merely NDC position. Initial proposed target: at least 6 px short-axis visual footprint or an equivalent legible locator when the ball itself is smaller. Human reviewer must be able to locate ball and carrier immediately. Tune the target against actual footage, not call it an industry standard.

### P0-B — Facing, turning and displacement do not form a believable movement model

**User report:** players run backwards without turning; physics/motion look wrong.

**Confirmed code inconsistencies / mechanisms:**
- `render/players.ts` sets root yaw at creation to `-p.facing + PI/2`, then overwrites it during updates with `-p.facing - PI/2`: a **180° inconsistency**. Which convention matches the actual GLB must be established with a labelled front-axis test; the inconsistency alone does not prove the per-frame convention is the wrong one.
- `sim/match.ts::movePlayer` approaches desired world velocity independently of facing. It then turns toward velocity after moving. Faster reverse braking is a velocity coefficient, not a plant/pivot animation or traction constraint. It permits large translation/facing disagreement during reversal.
- Acceleration coefficients 13/17.5 are rapid exponential response rates, not measured acceleration in m/s². They do not establish realistic biomechanics.
- Player roots are placed directly at sim coordinates. `separatePlayers` also pushes positions apart independently of the locomotion pose.
- The AME gait selector and crossfade cannot create missing deceleration, pivot, crossover or turn-in-place clips.
- The earlier stride playback cap explicitly trades excessive cadence for some sliding. Experimental planting is **off by default** (`?plantik=1`). Neither is proof of natural locomotion.

**Required:** one asset-facing convention shared by renderer, local-velocity queries and IK; instrument heading vs movement; acceleration/deceleration/turn limits coupled to speed; explicit stop/pivot/re-accelerate behaviour for large reversals; authorised backpedal/strafe states only where intended. Supply directional and transition clips before expecting matching to hide discontinuities. Match foot contacts to travel and action release deadlines.

**Acceptance:** front/back/side-labelled asset test; scripted straight travel, 90° cut, 180° reversal, stop-start, carry, disposal and tackle. Record heading error, root travel, contact-foot drift and action contact error. No prolonged high-speed forward-gait travel backwards. Test both IK states; do not turn IK on globally merely because the math tests pass.

### P0-C — Body separation is not team intelligence

**Observed:** overlapping rings and repeated small packs/pairs across the field; not just a single legitimate stoppage contest.

**Code evidence:**
- `sim/ai.ts` already restricts chase eligibility to two nearest teammates per team. The remedy is **not** simply to add that same cap again.
- Loose-ball chasing, carrier pressure, support runs and marking are selected by local ranking/distance tests.
- `homePosition` uses a ball-relative anchor and a small role-shape table with parity-based lateral positioning. Players can be attracted to similar destinations; role names alone do not establish distinct jobs.
- `sim/match.ts` separates bodies below about 1.7 m using positional pushes. This limits overlap but does not allocate useful space, stable receivers, exits or defensive cover.

**Required:** persistent contest jobs (collector, tackler, receiver, cover), commitment/hysteresis before swapping jobs, reserved support lanes, field-width/depth constraints and a stable defensive assignment. Use collision avoidance to reach distinct football destinations, not just to repel players after converging. Allow genuine stoppage congestion; do not force an artificial uniform spread.

**Acceptance:** contested pickup, wing exit, half-back rebound, forward lead and turnover fixtures. Measure players within 3/5/10 m of the ball, local density outside stoppages, assignment churn, available passing outlets and possession-chain length. A human must see a reason for off-ball movement. Calibrate against annotated real Australian-rules sequences; no claimed real-match target distribution has yet been measured.

### P0-D — My framing correction is not a broadcast-camera solution

**Observed:** large changes in field composition and player size across the recording. Jumping/freezing is additionally user-reported; the still review does not quantify it.

**Code evidence:**
- `render/camera.ts` eases toward each view's desired position, then calls `enforceFraming`.
- `render/framing.ts` returns an immediate recenter/pullback whenever subjects exceed the margin. That correction bypasses the smoothing just performed.
- There is no hysteresis/dwell-time state for entering/leaving the correction. Normal view easing can move inward again, then trigger another outward correction.
- Ball plus a faraway controlled player can demand a very wide shot. Keeping both centres safe can make both unreadable. This is an inherent composition conflict, not something a projection test resolves.
- Set-shot and celebration modes change camera policy. Celebration is exempt from the framing constraint. Frequent stoppages can cause repeated mode changes.
- The frame loop caps dt and catch-up accumulation. Slow rendering can cause wall-time/simulation-time mismatch. This is a diagnostic avenue, not proof of the reported freezes.

**Required:** a stateful camera planner: stable broadcast side, soft safe region, predictive flight target, damped centre/distance, separate pull-out/push-in rates, hysteresis and transition dwell. Prioritise live ball/carrier; use an edge indicator for a distant selected player rather than unlimited zoom-out. Preserve a true emergency offscreen recovery, but count and bound its discontinuities. Keep the last normal-play camera state across short stoppages where sensible.

**Acceptance:** repeatable long kick, cross-field switch, turnover, goal/reset and distant-player selection. Log target/actual position, distance, mode, correction count and reason. Measure screen-space ball size, frame-to-frame pan/zoom change and correction oscillation alongside visibility. Observe continuous videos; a ball-centre pass cannot certify camera quality. Exclude OS overlays and intentional pause/menu states from freeze statistics.

### P0-E — Repeated stoppages need causal audit, not a quieter whistle

**Visible:** push-in-back and holding-ball callouts. **User-reported:** whistle almost constantly sounding.

**Code evidence:**
- `sim/match.ts::tryTackles` has a commit window/cooldown, but uses random miss/foul outcomes. `commitTackle` also rolls for high contact, back contact and incorrect disposal.
- `forceFoul` is directly translated into back contact, regardless of a measured push/contact trajectory. This can produce a push-in-the-back decision without physically demonstrated pushing.
- `rules/engine.ts` accrues prior opportunity after a fixed 0.35 s of holding (or a fend). This is a rough proxy, not full context about being balanced/steady, having time and a disposal opportunity.
- `onTackle` can create a free kick, ball-up, or immediate possession transfer depending on decision. The live match feel depends on the frequency and inputs of these transitions, not only the correctness of each pure rule branch.
- `main.ts::handleEvents` whistles for free kicks, behinds, ball-ups, throw-ins, centre ball-ups and boundary decisions. Several whistle triggers are not fouls. It is not valid to count every whistle as an infringement.

**Required:** log tackle attempts, geometry, prior-opportunity state/reason, decision, stoppage IDs and audible cues. Audit restart immunity, repeated event emission and timer ownership before changing thresholds. Replace arbitrary back/high-contact flags with actual contact circumstances or explicitly authored risky tackle choices. Add cue deduplication by authoritative stoppage ID only if duplicate emissions are demonstrated. Do not suppress valid laws just to make flow smoother.

**Acceptance:** deterministic legal-side/behind tackle, illegal push, high tackle, immediate no-prior tackle, prior-and-failed-disposal, spill/play-on and restart fixtures. Report free kicks by reason, ball-ups, whistles, uninterrupted live-play time and repeat decisions at the same spot over multiple seeded matches. Review actual laws/interpretations before changing decisions. No exact target foul rate or count from this recording is claimed.

## Real Australian rules vs our simulation

Real-football analysis here is a qualitative coaching/readability baseline, not tracking data extracted from a professional match.

| Real-football requirement | Current gap | Engineering implication |
|---|---|---|
| Crowding can be correct at stoppages, with receivers, exits and coverage outside | Similar small clumps recur beyond one contest | Contest responsibilities plus spatial team structure, not global repulsion |
| Players decelerate and orient their body for major changes of direction | World displacement can reverse independently of body turn | Couple movement constraints and available animation transitions |
| Tackles have legal/illegal contact context; no-prior is not automatically identical to prior | Simplified timing and random contact flags feed rules | Derive decision inputs from action history/contact, preserve rule tests |
| Ball flight, bounce, possession and release must be readable | Oval-ball physics exists but ball is hard to locate | Separate physical correctness from presentation visibility |
| Broadcast camera follows the relevant play with continuity | Hard corrective fit and mode changes can alter composition abruptly | Stateful shot policy and quality metrics |

Official AFL guidance explains the difference between prior opportunity, genuinely attempting disposal without prior, and a ball being dislodged in a legal tackle. Use that for scenario design, not a simplistic 'less whistle' slider: [2](https://www.afl.com.au/news/1277215/holding-the-ball-a-focus-as-afl-clears-up-rules-with-clubs-ahead-of-2025-season). This is 2025 guidance, not a claim of a completed 2026 law audit.

If 'the real Aussie rules game' means a specific commercial AFL title rather than the sport, identify the title/version and provide a comparable clip. No AFL commercial build was run for this review. Prior documents' release dates, review scores and studio-size claims are not reused as verified evidence here.

## What shared engine / AME work actually supplies

| Layer | Verified repository state | Does NOT supply |
|---|---|---|
| `shared/arena_motion` C99 | Presentation-only feature normalization/search, hard filters, query construction, contact-time mapping, smoothing. README explicitly assigns pose data, blending and IK to callers. | Team AI, rules, ball physics, body collisions, camera planning, realistic motion data or automatic root-motion extraction |
| `arena-fc/Scripts/Core/Animation` C# | Deterministic clip selection/phase, optional feature database, locomotion queries, crossfade/contact policy. Class explicitly does not mutate player/match state. | A guarantee of realistic locomotion merely by sharing the class name or feature layout |
| Aussies TypeScript port + `render/motionBinding.ts` | Manifest/features loaded into TS engine; selected poses applied through three.js; fallback on failed assets; stride playback limit; opt-in planted feet | Proof of correct facing, natural pivots, correct release at a hand/foot, or convincing match AI |
| Gaelic adapter | Shared-core integration and gait/action matching; documentation explicitly says stripped root motion and no live authentic trajectory query in Gaelic | An automatically portable, fully validated motion/physics package for the web game |
| Gaelic recent diagnostics | Fixed side-camera jog captures, animated shorts-skinning and runtime IK probes; these explicitly exclude turns and full-match contexts | A solved backwards-running or Australian-rules gameplay problem |

**Current work in progress:** open PR #270, `Prototype opt-in gait-linked jog arm swing`, adds an opposite-leg-driven arm assist, excluding carrying/jumps/actions. Its body reports only a subtle improvement; arms remain forward/fingers splayed, shorts deformation unresolved. It is off by default, and the CMU candidate is not shipped. This is narrow motion presentation research—not a replacement for the five gameplay fixes above. PR status/body were inspected; its branch was not checked out or merged. https://github.com/pronane/c_games/pull/270

Do not blindly port it or enable all experiments. First define shared coordinate conventions, contact/trajectory metadata and a common scenario contract, then have each adapter prove its own asset/runtime behaviour. Retargeting and a database search cannot invent absent pivots, believable contact dynamics or tactical intent.

## Comparison with 'FIFA 25' (EA SPORTS FC 25)

The EA title is **EA SPORTS FC 25**. It is a football/soccer comparator, not an Australian-rules ruleset reference. No FC 25 executable, proprietary source or comparable capture was evaluated here.

EA's official descriptions separate **FC IQ** (roles/team tactics), **HyperMotionV** (data-driven player motion) and **PlayStyles** (individual abilities). That separation is useful architecture guidance; these are publisher descriptions, not independently measured guarantees of quality:
- [1](https://www.ea.com/games/ea-sports-fc/fc-25/news/pitch-notes-fc-25-gameplay-deep-dive)
- [2](https://www.ea.com/en/games/ea-sports-fc/fc-25/news/pitch-notes-fc-25-fc-iq-deep-dive)

| Dimension | FC 25 benchmark to learn from | Our real gap / practical response |
|---|---|---|
| Off-ball organisation | Explicit roles and team tactics, distinct from animation | Stable jobs, space reservations and measurable support shape; do not call clip matching tactical intelligence |
| Movement variety | EA describes animation driven by real-world volumetric data | Small authored database lacks proven transition coverage. Build/licence directional starts, stops, pivots and sport-specific contacts; do not claim HyperMotion equivalence |
| Ball/player readability | Desired playable-sports benchmark: locate play at broadcast distance | Measure actual pixels/occlusion and human acquisition; matching physical scale alone is insufficient |
| Camera continuity | Desired broadcast presentation benchmark, not a verified FC 25 algorithm | We need a stateful planner; no evidence warrants claiming how EA implements it internally |
| Physical credibility | Desired coherent displacement, turning, contact and animation | A motion selector is not a physics/controller system. Fix sim/renderer integration before more feature dimensions |
| Rules | Soccer rules differ fundamentally from AFL | Borrow architecture and presentation principles, not soccer formations, tackle laws or stoppage-rate targets |

There is no honest percentage 'close to FIFA' from the available evidence. This prototype is well short of a credible playable-sports benchmark on the five fundamentals, irrespective of the number of clips/tests or improved colours. We do not need EA's data scale to fix facing conventions, stable camera policy, readable ball presentation and deterministic football roles.

## Revised delivery sequence and gates

1. **Establish a regression replay/scenario contract.** Same seed, fixed input trace, version/flags displayed, simulation tick logged with capture time. Include turns, tackles, long kicks, selection changes and restarts. Keep actual in-match visual capture; do not substitute attract-only coverage. Freeze work on cosmetic improvements.
2. **Fix ball readability and camera policy together.** Prefer ball/carrier, readable visual footprint, optional distant-player edge indicator. Remove zoom pumping; keep a bounded emergency visibility recovery. Compare against the supplied clip with the same camera mode.
3. **Fix facing and locomotion fundamentals.** Asset-axis proof, consistent yaw transform, speed/turn coupling, authored turn/stop states, foot/contact validation. Reuse shared AME only where adapter tests establish conventions.
4. **Fix team shape and contact-driven laws as a coupled gameplay-flow task.** Persistent contest/support jobs reduce pointless collisions; tackle/context audit prevents artificial stoppage churn. Preserve valid free kicks and genuine contested footy.
5. **Only then resume visual polish / expand modes.** Human acceptance plus the relevant deterministic scenario checks must pass first.

### Verification must distinguish four things

- **Math correctness:** projection, IK reach, deterministic feature search. Existing tests help here.
- **Runtime correctness:** correct meshes, facing, states, action timing and authoritative events in this actual game/adapter.
- **Presentation quality:** ball readability, no ugly camera oscillations, plausible turns/foot planting, useful team structure. Requires time-based captures and human judgement.
- **Performance:** real frame pacing on the user's browser/GPU; SwiftShader is a non-blocking capture tripwire only.

Do not report the last three as verified by the first. A green overall workflow can hide the non-blocking visual job's failure. The latest capture work adds controlled-player sample requirements and diagnostics, but neither an NDC pass nor 167 passing tests closes this review.

## Requested next implementation scope

Recommended next batch: **ball readability + stable ball-first camera + a labelled facing diagnostic**, with a fixed-input replay and before/after capture. Then facing/turn controller changes, then team-flow/tackle context. This is deliberately smaller than claiming to replace the entire physics/animation engine in one PR.

No fixes have been claimed from this analysis. No commit, push or merge was performed.

# Arena FC — Root-and-Branch Gap Review vs EA FC 26 / HyperMotion and Pro Evolution / eFootball
## And the roadmap to bring Arena FC closer (with our own motion engine)

**Date:** 2026-11-18 (eFootball section added same day)  
**Branch:** `arena/430b74e3-c-games` (from `main` `c7b7d79`, PR #106 merged)  
**Scope:** Compare Arena FC today against the latest FIFA/EA FC title (EA Sports FC 26, Sept 2025) **and** Konami's Pro Evolution Soccer lineage (now eFootball, v5.x–v6.0 Aug 2026) and the videos/reviews available, identify every material gap, and lay out a feasible, original-assets-only path to close the biggest ones — including building our own HyperMotion-like engine and expanding Sprite Forge — while still running on PCs, laptops, devices and the browser. The browser must not limit desktop richness.

> **Standing constraint (unchanged):** original code and art only. No FIFA/PES/eFootball assets, branding, likenesses, kits, audio or proprietary code. Everything below is genre-standard technique implemented from scratch.

---

## 1. Executive summary

Arena FC is no longer a prototype. It has a deterministic 11v11/7v7/5v5 simulation, a sculpted 18-bone player with 67 clips, cadence-matched locomotion on desktop *and* browser, and authoritative online play. That is a solid foundation that EA-scale studios would recognise as "the right shape."

The gap to FC 26 **and** eFootball is not one missing feature. It is **five stacked gaps**, in order of how much they affect feel. The two rivals take opposite philosophies — FC 26 is fast/responsive/arcade-leaning, eFootball is slower/heavier/sim-leaning — and Arena FC should learn from both:

1. **Motion intelligence** — FC 26 synthesises context-aware animation (stride, first touch, shielding, turns) from 8.7M+ captured frames. eFootball uses motion-captured animation with momentum/inertia and player individuality. Arena FC plays one forward clip per speed band. This is the single biggest "wooden / treadmill / bunched" complaint in the user video.
2. **Ball control** — FC 26 has dynamic dribbling with frequent touches, explosive turns and strength-based shielding. eFootball has heavier, momentum-based dribbling where beating a player feels earned, plus manual shielding and attribute-driven passing/shooting. Arena FC glues the ball at a fixed offset and resolves tackles with a probability roll.
3. **AI and tactics** — FC 26 has ML goalkeeper positioning, smarter pressing and off-ball runs. eFootball has disciplined positional AI, Fluid Formations (separate attack/defence shapes), Team Playstyles (e.g. Overload) and Link-Up Plays. Arena FC has formation slots + 3 pressers + support runs.
4. **Presentation** — FC 26 has volumetric lighting, grass deformation, crowd and commentary. eFootball has photorealistic graphics and motion-captured animation on Unreal Engine. Arena FC has Compatibility-renderer flat pitch and text commentary.
5. **Modes and depth** — FC 26 has Career, Ultimate Team, Clubs, Rush, Archetypes and PlayStyles. eFootball has Dream Team, Master League (Sprint), Custom Tournaments, Match Analysis and real-time AI advice. Arena FC has Kickoff, editor and friend online.

**The good news:** gaps 1 and 2 — the ones players *feel* most — are closable without a mocap stage or a GPU cluster. Sprite Forge already contains 80% of the pipeline (video mocap, retarget, foot-lock, blend, polish). What is missing is the **runtime motion engine** that uses those baked clips intelligently, plus a larger, event-synced clip library.

This document proposes **Arena Motion Engine (AME)** — our own HyperMotion-like system — built in three layers:

- **Bake time (Sprite Forge):** record real phone video → solve to skeleton → clean/plant/blend → export clips with event frames (`ball_contact`, `footsteps`).
- **Runtime (C# + GDScript, shared data):** a locomotion blend space (speed × turn × ball state) + context selector (approach, first touch, shield, cut) + procedural polish (foot planting, lean, look).
- **Sim sync (Match.cs):** the simulation emits *intent* (pass, shoot, trap, shield, cut) and the motion engine picks the clip and syncs the ball release to the `ball_contact` frame — exactly how FC 26's ML-Flow works, but rule-based and deterministic.

AME runs identically on desktop, laptop, mobile and browser because it is data-driven (JSON clips + manifest) and CPU-cheap (18 bones, quaternion slerp). Desktop gets extra richness (higher LOD, shadows, post FX) via quality presets — the browser never limits it.

**Recommended order:** Phase 0 (days, quick wins) → Phase 1 (motion engine core, 2–3 weeks) → Phase 2 (gameplay depth) → Phase 3 (presentation/platform). Details in §7.

---

## 2. What FC 26 / HyperMotion actually is

### 2.1 HyperMotion lineage

HyperMotion began with FIFA 22: the first capture of a full 90-minute, 22-player match using Xsens suits + a local positioning system (LPS beacons) to avoid drift, generating 8.75 million frames [1](https://www.wired.com/story/fifa-22-hypermotion/). EA's proprietary ML then learns from those frames and "writes new animations in real time" instead of picking a clip from a database without context [1](https://www.wired.com/story/fifa-22-hypermotion/) [2](https://www.mirror.co.uk/sport/football/news/fifa-22-new-features-hypermotion-24680794).

Key sub-systems that matter for us:

| System | What it does | Why it matters |
|---|---|---|
| **ML-Flow** | Learns how players adjust stride and cadence on approach to the ball to control or strike it smoothly [2](https://www.mirror.co.uk/sport/football/news/fifa-22-new-features-hypermotion-24680794) | No more treadmill / foot slide on approach |
| **Kinetic air battles** | Syncs two-player animations when contesting aerial balls [2](https://www.mirror.co.uk/sport/football/news/fifa-22-new-features-hypermotion-24680794) | Headers and 50/50s look physical |
| **Composed ball control** | Longer two-touch animations for trapping [2](https://www.mirror.co.uk/sport/football/news/fifa-22-new-features-hypermotion-24680794) | First touch is a skill, not a magnet |
| **Player humanisation** | Off-ball ambient behaviour (pointing, talking, directing) [2](https://www.mirror.co.uk/sport/football/news/fifa-22-new-features-hypermotion-24680794) | Pitch feels alive when you don't have the ball |
| **Volumetric capture** | Full-body volumetric data (not just skeleton) for cloth/hair/interaction | Kits and bodies collide believably |

The modern mocap loop is unchanged: record → solve → clean → retarget → blend with procedural [5](https://sunstrikestudios.com/en/blog/motion_capture_for_games_and_film/). EA's edge is *scale* (full matches) + *learning* (context-aware synthesis), not a different loop.

### 2.2 FC 26 specifically (Sept 2025)

FC 26 runs **HyperMotion V2 Plus**: 2,000+ new animations, improved frame blending, unique run cycles by height/body type, enhanced volumetric animations [1](https://www.fifaworldcupnews.com/ea-sports-fc-26-release-date-features/). Gameplay changes from the official deep dive and reviews:

- **Two presets:** Competitive (fast, arcade, online-locked) vs Authentic (slower, weather on, tighter lines, realistic tackle accuracy, offline) [1](https://godisageek.com/2026/07/fc-26-review/) [3](https://www.pushsquare.com/reviews/ps5/ea-sports-fc-26) [4](https://www.gamespew.com/2025/09/ea-sports-fc-26-review/).
- **Dynamic dribbling:** rebuilt for consistency, more frequent touches, explosive turns, agility by body type [4](https://ea.com/en-gb/news/ea-sports-fc-26-community) [2](https://www.thesixthaxis.com/2025/07/22/ea-sports-fc-26-deep-dive-explains-the-gameplay-changes/).
- **Physicality/shielding:** "more consistent shielding, new ways to use your body to protect the ball, and an all-new enforcer playstyle" [4](https://ea.com/en-gb/news/ea-sports-fc-26-community).
- **Passing:** wider angles, improved first-touch animations, better receiver selection for through balls, lobbed balls into space with fewer obstructions [2](https://www.thesixthaxis.com/2025/07/22/ea-sports-fc-26-deep-dive-explains-the-gameplay-changes/).
- **Shooting:** wider angles, tighter close-range animations, control shot for manual power [2](https://www.thesixthaxis.com/2025/07/22/ea-sports-fc-26-deep-dive-explains-the-gameplay-changes/) [5](https://www.gamemeca.com/en/view.php?gid=1766119).
- **Goalkeeping:** reinforcement-learning positioning (only for positioning, not saves), more responsive, better angle-cutting [2](https://www.thesixthaxis.com/2025/07/22/ea-sports-fc-26-deep-dive-explains-the-gameplay-changes/) [4](https://ea.com/en-gb/news/ea-sports-fc-26-community).
- **Player types:** Explosive / Lengthy / Controlled archetypes by agility, strength, acceleration and height [5](https://www.gamemeca.com/en/view.php?gid=1766119).
- **Defending:** well-timed tackles now reliably win clean possession; Authentic defending has a real skill floor [1](https://godisageek.com/2026/07/fc-26-review/).
- **Presentation:** 4K/60 on PS5/XSX, PC 60 fps on mid-range, grass deformation, crowd density, stadium lighting [2](https://gamecritix.co.uk/ea-sports-fc-26-review/).

Old-gen consoles (PS4/Xbox One) do **not** get HyperMotion V — a reminder that EA itself tiers features by hardware. We will do the same (§6).

### 2.3 Pro Evolution Soccer → eFootball (Konami)

PES (1995–2021) built its reputation on **player individuality, ball physics, Master League and advanced tactics** (pressing/defensive-line sliders, advanced instructions like False Fullbacks/Gegenpress) [5](https://www.playefootballgame.com/pro-evolution-soccer/). PES 2011 already promised "total control" 360° passing, 1,000+ new mocap animations from 100+ hours of capture, and individual run styles [1](https://worthplaying.com/article/2010/7/13/news/75516-pro-evolution-soccer-2011-all-reveals-new-features-game-modes-screens/). PES 2013's "FullControl" added manual passing/shooting (power + height), R2 first-touch trapping and fine dribbling [4](https://pro-evolution-soccer-2013.en.download.it/).

In 2021 Konami rebranded PES to **eFootball** (free-to-play, new engine — Unreal Engine 4 — across console/PC/mobile) [5](https://www.playefootballgame.com/pro-evolution-soccer/). The current eFootball 2026 (v5.x, v6.0 Aug 2026) adds:

- **Gameplay feel:** measured tempo in both phases, refined movement speeds, defensive overhaul, more responsive dribbling + Sharp Touch, rebalanced pressing/Match-up, new tackle/slide animations (less automatic), revised long-range/chip shooting and 1v1 keeper positioning [2](https://www.fifaworldcupnews.com/efootball-2026-features-latest-updates/).
- **Tactics:** Fluid Formations (separate attacking/defensive shapes), new Team Playstyles (Overload concentrates players ball-side for numerical superiority), expanded Playing Styles, managers with two Link-Up Plays (e.g. Conte "Touchdown Pass C" + "One-Two Cut-In B") [1](https://www.konami.com/games/eu/en/topics/19232/) [3](https://www.konami.com/efootball/en/topic/news/5558).
- **Shooting:** Dynamic Volley — Stunning Shot command while ball is mid-air for first-time aerial strikes [3](https://www.konami.com/efootball/en/topic/news/5558).
- **Modes/systems:** Custom Tournaments (up to 8, spectatable), Master League Sprint (transfers/training/synergy/injuries), Match Analysis (last 10 PvP matches, style charts), real-time AI advice + expanded AI Control (delegate hard moments), Advanced/Easy Feint commands on mobile [2](https://www.fifaworldcupnews.com/efootball-2026-features-latest-updates/) [4](https://egw.news/fifa/news/30963/efootball-2026-v520-update-brings-massive-overhaul-gG3fZO69-).
- **Scale:** 1 billion cumulative downloads (Apr 2026) [5](https://www.insideworldfootball.com/2026/04/10/konami-hits-1bn-downloads-efootball-game-launches-suite-new-features/).

**Head-to-head consensus (2025–26 comparisons):**

| Area | FC 26 | eFootball 26 | Takeaway for Arena FC |
|---|---|---|---|
| **Dribbling** | Fast, responsive, skill chains glide; needs PlayStyles (e.g. Technical) for Messi moments [1](https://soccergaming.com/fc-26-vs-efootball-2026-which-gameplay-is-better/) | Heavier, momentum-based; can't zigzag, must feint and wait — beating a player feels earned [1](https://soccergaming.com/fc-26-vs-efootball-2026-which-gameplay-is-better/) | Offer both: Competitive = FC-style, Authentic = eFootball-style (see Phase 2.9) |
| **Passing** | Huge variety (driven, trivela, threaded) but PlayStyle-gated; elite attributes can feel flat without them [1](https://soccergaming.com/fc-26-vs-efootball-2026-which-gameplay-is-better/) | Attribute-driven (vision/technique show naturally); pinpoint diagonals feel real [1](https://soccergaming.com/fc-26-vs-efootball-2026-which-gameplay-is-better/) | Make `Passing` attribute matter directly (we already do — keep it, don't gate behind PlayStyles) |
| **Shooting** | Many shot types but PlayStyle-dependent; meta narrows to few attackers [1](https://soccergaming.com/fc-26-vs-efootball-2026-which-gameplay-is-better/) | Natural/attribute-driven; composed striker finishes calmly, pressured striker misses [1](https://soccergaming.com/fc-26-vs-efootball-2026-which-gameplay-is-better/) | Keep skill+pressure error model; add Dynamic Volley (first-time aerial) |
| **Defending** | Skill-based (tactical/advanced defending); reduced AI assist rewards manual play [1](https://soccergaming.com/fc-26-vs-efootball-2026-which-gameplay-is-better/) | Reading game > constant pressing; disciplined shape, less exploitable [2](https://www.mrgeek.net/blog/fc-26-vs-efootball-26) | Jockey/contain + timing (Phase 2.5), not just probability |
| **AI** | Dynamic, distinct identities (Manager Playstyles); offline AI can lack desperation [1](https://soccergaming.com/fc-26-vs-efootball-2026-which-gameplay-is-better/) | Disciplined positional, holds shape; Konami tunes via seasonal patches [2](https://www.mrgeek.net/blog/fc-26-vs-efootball-26) | Formation + off-ball runs + tactics presets (Phase 2.7) |
| **Feel** | "Ice skating / ping-pong" complaints; fast but generic [4](https://www.reddit.com/r/eFootball/comments/1o4u3b1/this_game_is_a_disaster_after_playing_fc_26/) | "Smooth movement, juicy challenge at Legend" praise; but Smart Assist automates a lot [4](https://www.reddit.com/r/eFootball/comments/1o4u3b1/this_game_is_a_disaster_after_playing_fc_26/) | Weight/momentum + manual control; no Smart Assist — skill should show |

**What Arena FC should steal from eFootball (not FC 26):**
- Momentum/inertia in dribbling and turning (can't 180° at sprint) — Phase 2.2.
- Attribute-driven passing/shooting (already our model — protect it).
- Fluid Formations + Team Playstyles as *light* tactics (attack/defence shapes, Overload-style ball-side concentration) — Phase 2.7.
- Dynamic Volley (first-time aerial shot) — Phase 2.4.
- Match Analysis / real-time advice as a *post-match* learning tool (cheap: we already log events) — Phase 3.

**What Arena FC should steal from FC 26 (not eFootball):**
- Context-aware motion synthesis (ML-Flow → our AME blend space).
- Authentic/Competitive presets (two tunings, one sim).
- Archetypes (Explosive/Lengthy/Controlled) + RL-style keeper positioning (rule-based version).
- Dynamic dribbling touch frequency + shielding with strength.

---

## 3. What Arena FC has today (inventory)

### 3.1 Simulation core — `Scripts/Core/Match.cs` (1,111 lines)

Pure C#, deterministic, fixed 60 Hz, seeded RNG, no Godot dependency. This is the right architecture for online play and replay.

| System | Implementation | Notes |
|---|---|---|
| **Phases** | `Kickoff, Play, Goal, HalfTime, FullTime, ThrowIn, Corner, GoalKick, FreeKick, Penalty, Paused` | Full restart coverage |
| **Commands** | `PlayerCommand`: Move, Sprint, Pass, Shoot, Through, Tackle, Switch, Lob, Slide, Shield, Dribble, Charge | Tiny struct, cheap to send online |
| **PlayerState** | Pos/Vel/Facing/Home/Target, Stamina, AnimPhase, ActionTimer, PossessionLock, TackleLock, Action string, Pressing/Shielding/Dribbling/Sprinting, Cards | `MaxSpeed = (3.6 + Pace*3.5) * keeper?0.94` |
| **AI (`Decide`)** | Formation slots + ball-shift, 3 pressers (chaser1/2/3) with goal-side lanes, carrier dribbles toward goal + evades, support runs, keeper positioning + dive trigger | No off-ball runs, no tactics, no stamina decisions |
| **Passing (`PassTo`)** | `FindBestPassTarget` scores forward*0.22 + openness*0.55 − dist*0.10 − laneBlocked*6; error cone by Passing skill; through-ball lead 0.55s + 4m toward goal; lob arc | No first-touch, no curve, no weak foot, no timed |
| **Shooting (`Shoot`)** | Charge 0.25–1.0 → power 17–31 m/s, loft 0.08–0.30, error by Shooting skill + distance; volley flag | No timed finishing, no placement vs power choice |
| **Tackling (`AttemptTackle`)** | Standing (reach 3.6m) / slide (4.6m), human lunge 2.2–5.2m, contest: `0.42 + Defending*0.34 + strength + between*0.20 − shield − dribble − pace*0.12`, foul chance if close miss | Probability roll, no jockey/contain, no timing meter |
| **Ball (`BallPhysics`)** | Gravity, Magnus from Spin, bounce 0.48, roll friction, post/bar, goal, keeper save radius (1.15m / 1.65m diving), throw/corner/goal-kick | No drag curve, no pitch/weather variation |
| **Possession (`TryPossession`)** | Nearest within 1.0m (keeper 1.5m), PossessionLock 0.12s, PassReceiver guard | Ball glued at fixed offset in `Tick` (lead 0.30–0.46m) |
| **Rules** | Offside (second-last defender), fouls → free kick / penalty in box, cards 12%, stamina fatigue 0.72–1.0× speed | No VAR, injuries, subs, morale |

### 3.2 Player and animation — `Tools/soccer_motions.py` + `SoccerClipRig.cs` + `Web/BrowserBoot.gd`

| Artifact | Detail |
|---|---|
| **Mesh** | Sculpted footballer via `sforge.footballer` (122 SDF shapes, marching cubes 6mm, decimate to 16,000 tris), 6 flat kit materials (skin/jersey/shorts/socks/boots/hair), height 1.7682m, grounded, faces +Z |
| **Skeleton** | 18 bones: `Hips, Spine, Chest, Neck, Head, Face, LUpperArm, LForearm, LHand, RUpperArm, RForearm, RHand, LThigh, LShin, LFoot, RThigh, RShin, RFoot` — identical contract in GLB, JSON and `RigDefinition.cs` |
| **Clips** | 67 clips, 31 frames @ 30 fps (1.04s), 12 looping. Registry in `soccer_motions.py`: locomotion (idle/walk/jog/run/sprint/run_ball), ball (dribble/shield/short_pass/long_pass/through/cross/shoot/volley/header/chest/trap/toe_lift/pickup), defence (tackle/slide/shoulder/dispossess/block/foul/stumble), keeper (ready/catch/dive_left/right/punch/throw_out), restarts (throw_in/corner/goal_kick/free_kick/penalty), reactions (celebrate/disappointed/injured/get_up) |
| **Desktop playback** | `SoccerClipRig.cs`: `GltfDocument` + `AnimationPlayer`, cadence-matched (`SpeedScale = speed / (naturalRate * styleStride)`, natural rates measured: walk 0.74, jog/run 1.01, sprint 1.22, dribble 0.60 m/cycle), hysteresis bands, one-shots once, lean from speed+accel, roll from lateral accel, per-player style ±7% seeded from spec |
| **Browser playback** | `BrowserBoot.gd`: same 67 clips baked into `soccer_rig.json` (2.0 MB, per-bone quaternions + Hips translation), same cadence logic (`CLIP_NATURAL`/`CLIP_MAXRATE`), fallback to procedural `animate_rig()` if clips absent. WASM template has no glTF module (verified: `GLTFDocument` 0 hits in symbols), so JSON is the browser path |
| **Tests** | `test_soccer_forge.py` 52/0, `test_pads.py` 129/0, CI green |

### 3.3 Sprite Forge (v11.13, in-repo `sprite_forge/`)

| Module | What it does | Relevance to AME |
|---|---|---|
| `mocap.py` | MediaPipe `track`, `repair_swaps`, `fill_and_smooth`, IK `solve_frame`, `analyse`, `keys_motion`, `save_keys` | Video → skeleton. The "record real footage" path |
| `motionlib.py` | `MotionLibrary`, `clean_keys` (feet/weight/anticipation/follow), `plant_on_rig`, `retarget_motion`, `record_video`, BVH import, `canonical_keys` | Bake-time cleaning and retarget |
| `footlock.py` | `contacts`, `_ik`, `lock`, `measure` | Foot planting (bake-time; needs runtime version) |
| `blend.py` | `blend_motion`, `add_moves`, `crossfade`, `fill_crossfades` | Clip blending |
| `motionpolish.py` | `polish_sample`, `clamp_joints`, `weight_shift` | Joint limits, weight shift |
| `retarget.py` | `retarget`, `edit_clip` (trim/speed/loop) | Mannequin → Arena 18-bone |
| `footballer.py` | `Skeleton`, `Design`, `build`, `paints` | Sculpted player + kit layers |
| `motions.py` | `P`, `loco`, `idle_func`, `K`, `M`, `_kick`, `_dive` | Procedural pose channels (source of current 67 clips) |
| `game_packs/soccer.json` | Side camera, 128×160, moves with `fps`/`events` (`ball_contact`, `footsteps`, `hit_start/end`) | Event-synced clips — **under-used by Arena FC today** |
| `motion_library/` | 37 generic JSON clips (idle/walk/run/kick/pass/shoot/tackle/save/dive_left/right/gk_throw_out…) | Starter library |

### 3.4 What the user video showed

`02.11.2026_21.46.12_REC.mp4` (55s, native desktop): 22 rigged players, ball at feet, HUD/minimap/commentary all working — but 1 shot in 55s, endless "X wins the ball!" loop, 3–5 player scrums at centre circle. Root cause was the `PossessionLock` release bug in `Match.Tick()` (fixed PR #37: owner flips 653→33, goals 0→2). Subsequent fixes (PRs #38/#39) added pad menu select, second camera, tackles (7→16), gait knees, and reduced fouls (4→1). The remaining "wooden / bunched / no joints" feel is now a **motion and AI** problem, not a sim bug.

---

## 4. Gap matrix — Arena FC vs FC 26 **and** eFootball

Severity: **P0** = players feel it every second · **P1** = felt every match · **P2** = felt over a session · **P3** = polish.

### 4.1 Motion and animation (P0)

| # | FC 26 | eFootball 26 | Arena FC today | Gap | Severity |
|---|---|---|---|---|---|
| M1 | Context-aware synthesis (ML-Flow): stride/cadence adapts on approach | Mocap + momentum/inertia; new movement/dribble/passing/shooting/trapping/GK animations [1](https://www.konami.com/games/eu/en/topics/19232/) | Single forward clip per speed band; cadence matched to speed only | No approach phase, no stride shortening before trap/strike | **P0** |
| M2 | Unique run cycles by height/body (Explosive/Lengthy/Controlled) | Player individuality (unique styles/movement) | One base mesh scaled by `Height`; style ±7% only | All players run identically; no archetypes | **P0** |
| M3 | Directional locomotion (strafe, backpedal, cut, turn) | Momentum-based turning; feint/wait to beat defender [1](https://soccergaming.com/fc-26-vs-efootball-2026-which-gameplay-is-better/) | Forward-only clips; facing lerps to velocity | Turning looks like skating; no cut/step-over | **P0** |
| M4 | Foot planting (volumetric + IK) | Mocap ground contact | Bake-time `footlock` only; runtime has no IK | Feet slide on turns, slopes, tackles | **P0** |
| M5 | Upper/lower split (aim while running) | Manual shielding, body feint (LS) | Whole-body clip + root lean/roll only | Can't look over shoulder, aim pass while sprinting | **P1** |
| M6 | Ball-contact sync | Mocap contact frames | `ActionTimer` 0.34–0.40s fixed; ball teleports | Kick looks disconnected | **P0** |
| M7 | First-touch variants | Trapping animations; Dynamic Volley (mid-air Stunning Shot) [3](https://www.konami.com/efootball/en/topic/news/5558) | `trap`/`chest`/`volley`/`header` exist but never selected | Every control is a magnet | **P0** |
| M8 | Dribble touches (frequent, by speed) | Heavier momentum dribble; Sharp Touch [2](https://www.fifaworldcupnews.com/efootball-2026-features-latest-updates/) | `dribble` loop + fixed lead 0.30–0.46m | Ball glued; no knock-on/touch interval | **P0** |
| M9 | Shielding with strength | Manual shielding | `shield` clip + flag reduces tackle 0.22 | No body positioning visible | **P1** |
| M10 | Skill moves | Advanced/Easy Feint commands (mobile) [2](https://www.fifaworldcupnews.com/efootball-2026-features-latest-updates/) | None | No stick-gesture moves | **P1** |
| M11 | Keeper (dive/punch/catch/parry/rush) | New GK animations; 1v1 positioning improved [2](https://www.fifaworldcupnews.com/efootball-2026-features-latest-updates/) | `dive`/`catch`/`punch` exist; radius check only | No parry/rush/punch-vs-catch | **P1** |
| M12 | Ambient/off-ball | Ambient off-ball behaviour | `celebrate`/`disappointed` only on goal | Pitch feels dead | **P2** |
| M13 | Cloth/hair | Photorealistic kits | None | Kits look painted | **P2** |
| M14 | Faces/expressions | Facial animation | `Face` bone, no expressions | No emotion | **P3** |

### 4.2 Gameplay and ball (P0–P1)

| # | FC 26 | eFootball 26 | Arena FC | Gap | Severity |
|---|---|---|---|---|---|
| G1 | Dynamic dribbling, explosive turns | Momentum dribble (slow, feint, wait) [1](https://soccergaming.com/fc-26-vs-efootball-2026-which-gameplay-is-better/) | Fixed lead; unlimited turn rate | Sprint-turn 180° instant | **P0** |
| G2 | First touch by pressure/skill | Trapping by attribute/pressure | Instant possession 1.0m | No heavy touch/knock-on/failure | **P0** |
| G3 | Passing variety, PlayStyle-gated | Attribute-driven (vision/technique) [1](https://soccergaming.com/fc-26-vs-efootball-2026-which-gameplay-is-better/) | Error cone by Passing; fixed through lead | No driven/lofted/threaded/chip/curve | **P1** |
| G4 | Shooting variety, control shot | Natural/attribute-driven; Dynamic Volley [3](https://www.konami.com/efootball/en/topic/news/5558) | Charge only; skill+distance error | No placement/power, curve, first-time | **P1** |
| G5 | Tackling skill-based, reduced AI assist | Reading > pressing; new tackle/slide anims [2](https://www.fifaworldcupnews.com/efootball-2026-features-latest-updates/) | Probability roll; slide 4.6m | No jockey/contain/timing | **P0** |
| G6 | Drag/curve/deflection | Realistic ball physics, natural momentum [2](https://www.mrgeek.net/blog/fc-26-vs-efootball-26) | Gravity+Magnus+bounce; no drag curve | Shots float | **P1** |
| G7 | Fatigue affects movement | Stamina gentler on acceleration; awareness affects marking [4](https://egw.news/fifa/news/30963/efootball-2026-v520-update-brings-massive-overhaul-gG3fZO69-) | Speed scalar 0.72–1.0× only | Tired players trap perfectly | **P1** |
| G8 | Set pieces (FK curve, routines) | Set-piece roles (near/post watchers) | `Restart` places ball; penalty auto | No aiming/routines | **P1** |
| G9 | Fouls/cards/referee | Fouls/cards, less automatic defending | Foul chance + 12% card | No advantage/VAR/injury | **P2** |

### 4.3 AI and tactics (P1)

| # | FC 26 | eFootball 26 | Arena FC | Gap | Severity |
|---|---|---|---|---|---|
| A1 | ML keeper positioning | 1v1 positioning improved [2](https://www.fifaworldcupnews.com/efootball-2026-features-latest-updates/) | Simple formula `tx/tz` | No angle/rush/parry | **P1** |
| A2 | Smarter pressing, line, trap | Disciplined shape, holds position [2](https://www.mrgeek.net/blog/fc-26-vs-efootball-26) | 3 pressers + 0.30× shift | No line/trap/cover | **P1** |
| A3 | Off-ball runs, Manager Playstyles | Fluid Formations, Overload, Link-Up Plays [1](https://www.konami.com/games/eu/en/topics/19232/) | Support = slot + carrier + 3.5m | No runs into space | **P1** |
| A4 | Tactics: mentality/width/instructions | Team Playstyles, Playing Styles, advanced instructions | Formations only | No in-match tactics | **P2** |
| A5 | Difficulty by tactics | Seasonal AI tuning by feedback [2](https://www.mrgeek.net/blog/fc-26-vs-efootball-26) | `Difficulty` scales aggression | Legendary = stat boost | **P2** |

### 4.4 Presentation, audio, modes (P2–P3)

| # | FC 26 | eFootball 26 | Arena FC | Gap | Severity |
|---|---|---|---|---|---|
| P1 | Volumetric, grass deformation, crowd | Photorealistic, Unreal Engine, mocap [5](https://www.playefootballgame.com/pro-evolution-soccer/) | Compatibility, flat pitch, text feed | Looks indie | **P2** |
| P2 | Career/UT/Clubs/Rush/Archetypes | Dream Team, Master League Sprint, Custom Tournaments, Match Analysis [2](https://www.fifaworldcupnews.com/efootball-2026-features-latest-updates/) | Kickoff/editor/friend online | No progression | **P2** |
| P3 | Accessibility | AI Control, real-time advice [4](https://egw.news/fifa/news/30963/efootball-2026-v520-update-brings-massive-overhaul-gG3fZO69-) | Basic remapping | — | **P3** |
| P4 | Quality presets, 60 fps | Free-to-play all devices, mobile visuals improved [2](https://www.fifaworldcupnews.com/efootball-2026-features-latest-updates/) | Single tier | No Low/Med/High | **P2** |

---

## 5. Our own HyperMotion-like engine — Arena Motion Engine (AME)

We cannot (and should not) copy EA's ML or mocap data. We *can* copy the **architecture**: capture at scale → learn/synthesise context → blend procedurally. Our scale is a phone camera and procedural poses; our "learning" is a deterministic rule-based context selector tuned by measurement. That is enough to close M1–M9.

### 5.1 Design principles

1. **Data-driven, not code-driven.** Clips, events, natural rates and blend weights live in JSON/manifest. C# and GDScript read the same files. Adding a clip never requires a code change.
2. **Deterministic.** AME inputs are sim state (speed, turn rate, ball distance/height, intent) — all already in `PlayerState`. No RNG in animation. Online snapshots stay tiny.
3. **CPU-cheap.** 18 bones × quaternion slerp + 2-bone IK = <0.05 ms/player. 22 players <1 ms. Runs on a phone browser.
4. **Bake-time heavy, runtime light.** All IK solving, foot-lock and polish happen in Sprite Forge at build time. Runtime only blends and applies a small procedural offset.
5. **Event-synced.** Every ball clip carries `ball_contact` frame (already in `game_packs/soccer.json`). `Match.cs` releases the ball on that frame, not on a fixed timer.

### 5.2 Architecture (3 layers)

```
┌─────────────────────────────────────────────────────────┐
│ LAYER 3 — Procedural polish (runtime, per frame)        │
│  Foot planting IK · lean/roll · look-at · ball contact  │
│  (extends SoccerClipRig.UpdateLean + BrowserBoot)       │
├─────────────────────────────────────────────────────────┤
│ LAYER 2 — Context selector (runtime, per decision)      │
│  speed × turnRate × ballState × intent → clip + phase   │
│  (replaces SelectClip/SelectLocomotion)                 │
├─────────────────────────────────────────────────────────┤
│ LAYER 1 — Clip library (bake time, Sprite Forge)        │
│  67 → ~140 clips with events, archetype variants,       │
│  directional locomotion, first-touch set, skill moves   │
│  (soccer_motions.py + mocap.py + footlock/blend/polish) │
└─────────────────────────────────────────────────────────┘
         ▲ sim intent (Match.cs: Action, ActionTimer)
         │ ball release on ball_contact frame
```

**Layer 1 — Clip library.** Extend `Tools/soccer_motions.py` from 67 to ~140 clips:

- **Directional locomotion (12):** `strafe_left/right`, `backpedal`, `turn_left/right` (90° cut), `cut` (180°), `sprint_turn`, each in walk/jog/run variants. Source: `loco()` with different stride/lean + `mocap.py` phone recordings for realism.
- **Archetype variants (×3):** Explosive (short stride, high cadence, forward lean), Lengthy (long stride, low cadence), Controlled (compact, upright). Generated by parameterising `loco(stride, knee, arm, elbow, lean)` per `CharacterSpec` archetype — no new mocap needed. This mirrors FC 26's Explosive/Lengthy/Controlled without copying data.
- **First-touch set (8):** `trap_ground`, `trap_aerial`, `chest_control` (exists), `volley` (exists), `header` (exists), `toe_lift` (exists), `knock_on`, `heavy_touch`. Selected by ball height/speed/pressure in Layer 2.
- **Dribble touches (6):** `dribble_close`, `dribble_open`, `dribble_sprint`, `step_over`, `roulette`, `heel_to_heel`, `fake_shot`, `ball_roll`. Each carries `ball_contact` + `footsteps` events.
- **Defence (6):** `jockey`, `contain`, `shoulder_charge` (exists), `slide` (exists), `block`, `recover`. Jockey/contain are low-speed directional loops.
- **Keeper (6):** `dive_left/right` (exist), `punch` (exists), `parry`, `rush`, `catch_high/low`. Parry = deflect, not possess.
- **Ambient (6):** `point`, `gesture`, `disappointed` (exists), `celebrate` (exists), `walk_back`, `stretch`. Played by off-ball players.

Every clip gets: `fps`, `frames`, `loop`, `events: {ball_contact, footsteps[], hit_start/end}`, `natural_rate` (measured foot travel), `archetypes: [explosive, lengthy, controlled]` (or parameterised). The builder (`build_soccer_player.py`) already writes `fps/frames/loop/bones` — extend it to write `events` and `natural_rate` from the manifest.

**Layer 2 — Context selector.** Replace `SelectClip`/`SelectLocomotion` with a blend-space lookup:

```
Inputs (all from PlayerState, already available):
  speed (m/s), turnRate (rad/s), ballDist, ballHeight, ballSpeed,
  intent (Action string), isCarrier, isPressing, stamina, archetype

Output: clip name + phase + blend weight + SpeedScale

Rules (deterministic, tuned by measurement):
  - speed < 0.5 → idle / keeper_ready / jockey (if pressing)
  - turnRate > 1.5 rad/s → turn/cut clip (not forward run)
  - ballDist < 2m && ballHeight > 1.2m && intent == trap → chest_control
  - ballDist < 2m && ballHeight < 0.3m && ballSpeed > 8 → trap_ground
  - isCarrier && speed > 4 → dribble_sprint (open touch)
  - isCarrier && speed < 2 && presserNear → shield
  - intent == pass/shoot → clip with ball_contact; sim waits for contact frame
```

Blending: 0.08–0.12s crossfade (already in `SoccerClipRig`), plus **phase sync** — when switching locomotion clips, align `AnimPhase` so feet don't pop. This is the "frame blending" FC 26 advertises, done with quaternion slerp.

**Layer 3 — Procedural polish.**

- **Foot planting IK:** 2-bone IK (thigh/shin) to pin the stance foot to the ground during locomotion. Bake-time version exists in `footlock.py:_ik`; port a runtime version to `SoccerClipRig.cs` + `BrowserBoot.gd` (same maths, ~60 lines). Only the stance foot is pinned; swing foot is free.
- **Lean/roll:** already shipped (`UpdateLean`). Extend with **turn lean** (lean into cut) and **reach** (arm toward ball on trap).
- **Look-at:** head/neck yaw toward ball when off-ball, toward goal when carrier. `Face` bone already exists.
- **Ball contact:** ball offset driven by clip's `ball_contact` frame + foot position, not a fixed lead. During `dribble`, ball position = foot pos + touch interval offset (by speed).

### 5.3 Why this is "HyperMotion-like" without ML

| EA HyperMotion | AME equivalent |
|---|---|
| 8.7M frames from full-match capture | Phone-video mocap via `mocap.py` + procedural `loco()` variants (hundreds of clips, not millions of frames) |
| ML-Flow writes stride on approach | Rule: `stride = clamp(speed / cadence, min, max)` + approach phase clip when `ballDist < 3m` |
| ML blends by context | Blend space (speed × turn × ballState) + phase sync |
| Volumetric data | 18-bone skeleton + flat kit layers (no cloth sim initially) |
| RL keeper positioning | Angle-to-shooter positioning + rush/parry decisions (rule-based, tuned) |

We get 80% of the *feel* for 5% of the cost. ML can come later (Phase 3) if we want to learn blend weights from recorded play — but it is not required to close the gap.

### 5.4 Sim sync — the missing link

Today `Match.cs` sets `ActionTimer = 0.34f` and teleports the ball. AME changes this to:

```csharp
// Match.cs: PassTo / Shoot / Trap
from.Action = "pass"; from.ActionTimer = clipDuration; from.ActionFrame = 0;
// BallPhysics: when ActionFrame == clip.ball_contact_frame → release ball
```

The clip's `ball_contact` frame comes from `game_packs/soccer.json` events (already defined for `kick`/`pass`). The builder must export it into `soccer_player_manifest.json` and `soccer_rig.json`. This one change fixes M6 and makes every kick/pass/shoot look connected.

---

## 6. Cross-platform strategy — browser must not limit desktop

**Principle:** one deterministic sim (`Match.cs`), one clip library (JSON), two renderers (C# GLB + GDScript JSON), quality tiers on top. The browser edition is a *tier*, not a *fork*.

| Tier | Target | Renderer | Mesh | Clips | Extras |
|---|---|---|---|---|---|
| **Desktop High** | PC, Mac, Linux (Godot C#) | Compatibility (or Forward+ if we fork) | 16k tris, full shadows, post FX (bloom, tonemap, vignette) | All ~140, 30 fps | Crowd, replay/slow-mo, cloth, commentary audio |
| **Laptop / Low** | Integrated GPU | Compatibility | 8k tris LOD, blob shadows | All ~140, 30 fps | No post FX, reduced crowd |
| **Mobile** | Android/iOS (Godot export) | Compatibility | 4k tris LOD, blob shadows | Locomotion + ball clips only (~60) | Touch controls, auto quality |
| **Browser** | WebGL2 / WASM (GDScript) | Compatibility (WebGL2) | 16k tris (JSON), blob shadows | All ~140 baked JSON (2–3 MB) | WebSocket online, no post FX |

**How we avoid browser limits leaking into desktop:**

- `Match.cs` is pure C# with no Godot dependency — it already runs headless on the server. Desktop richness (shadows, post, crowd) lives in `Scripts/Godot/World3D.cs` / `StadiumKit.gd`, never in the sim.
- Clips are data. Desktop loads GLB (with `AnimationPlayer` blending); browser loads JSON (with manual slerp). Same manifest, same natural rates, same events. Adding a clip updates both.
- Quality presets (`MatchOptions.QualityTier`) select LOD + shadow + post. Browser defaults to Medium; desktop defaults to High. The sim never sees the tier.
- Online: server runs `Match.cs` at 60 Hz, clients send `PlayerCommand` only. Animation is client-side and deterministic from state, so a phone browser and a desktop PC render the same motion from the same snapshots.

**What the browser *cannot* do (and desktop can):** Forward+ features (SSGI, SDFGI, volumetric fog) — Compatibility renderer rules them out. If we want them, fork the renderer per platform (desktop Forward+, browser Compatibility) behind the same `World3D` interface. That is a Phase 3 decision, not a blocker.

---

## 7. Phased roadmap

### Phase 0 — Quick wins (days, no architecture change)

| # | Task | Files | Test |
|---|---|---|---|
| 0.1 | Export `ball_contact`/`footsteps` events from `game_packs/soccer.json` into manifest + JSON; sync ball release to contact frame | `build_soccer_player.py`, `Match.cs`, `SoccerClipRig.cs`, `BrowserBoot.gd` | `test_soccer_forge.py` +1 check; visual: kick connects |
| 0.2 | Wire unused clips: `trap`/`chest`/`volley`/`header` selected by ball height/speed in `Decide`/`TryPossession` | `Match.cs`, `soccer_motions.py` aliases | Sim: aerial ball → chest clip, not magnet |
| 0.3 | Dribble touch interval: ball lead by speed (0.15m close → 0.60m sprint) + knock-on on sprint | `Match.cs:Tick` ball offset | Foot speed ≈ ball speed at sprint |
| 0.4 | Turn clips: add `turn_left/right` + `cut` to library; select by turnRate in `SelectLocomotion` | `soccer_motions.py`, `SoccerClipRig.cs`, `BrowserBoot.gd` | No skating on 90° turns |
| 0.5 | Keeper parry: deflect (not possess) when ball speed > 18 m/s or diving | `Match.cs:BallPhysics` | Parry events in commentary |

**Status: DONE (2026-11-18).** All five items implemented on `arena/430b74e3-c-games` (C# core + desktop `SoccerClipRig.cs` + browser `BrowserBoot.gd` kept in lock-step):

- **0.1** — `Tools/soccer_motions.py` now defines `CLIP_EVENTS` for all 67 clips (`ball_contact`/`footsteps`/`hit_start`/`hit_end` as frame + fraction); `Tools/build_soccer_player.py` exports them to `Data/soccer_rig.json` (baked clips) and `Data/soccer_player_manifest.json`. `Match.cs` gained an event-synced pending-action system (`SetAction`/`FirePending`): `PassTo`/`Shoot` (incl. `volley`) hold the ball until `ActionContactAt` then release (Kind 1); first-touch captures at contact (Kind 2). Net state (`Packet.cs`/`Match.Network.cs`) carries `ActionDuration`/`ActionContactAt` + all pending ball fields, so online clients stay in sync. Desktop `SoccerClipRig.cs` and browser `animate_clip()` speed-match one-shots so contact lands on the sim's release frame (`clipDuration/ActionDuration`, clamped 0.6–1.8).
- **0.2** — `TryPossession` now selects first-touch by ball height/speed: `header` (high, dropping), `chest_control` (high), `trap` (low/fast), each with a Kind-2 pending capture; `MovePlayer` plants feet (speed ×0.30) for those actions. Aliases `volley`/`header`/`chest_control`/`trap` wired in both animation systems.
- **0.3** — Dribble lead is speed-scaled (0.15 m close → 0.60 m sprint, `Lerp` by speed) with a sprint knock-on (+0.08 m when sprinting >4.5 m/s), in both `Match.cs` and `BrowserBoot.gd`.
- **0.4** — Turn clips selected by turn rate: `SelectLocomotion` (C#) and `clip_select_locomotion` (GDScript) compute facing turn rate and play the `soccer_turn` (turn/cut) clip when >2.2 rad/s at speed >1.2 m/s (0.6 s cooldown). The library has no directional turn sources, so left/right variants are deferred to Phase 1.4 (directional locomotion set). Aliases `cut`/`strafe`/`change_direction`/`parry` added (78 total).
- **0.5** — Keeper parry in `BallPhysics` (C#) and `keeper_saves()` (GDScript): deflect (not possess) when ball speed >18 m/s, or >14 m/s while diving; otherwise catch. Keeper dive now goes through `SetAction` so it is event-synced.

**Verified:** `test_soccer_forge.py` 68/0, `test_pads.py` 129/0, `gdparse` clean on `BrowserBoot.gd`, and the C# core compiled + ran via the Roslyn WASM runner (`@live-codes/blazor-wasm`): `Tests/Program.cs` **149 passed, 1 failed** — the single failure (`gamecontrollerdb.txt found`) is a sandbox artifact (the file exists at `arena-fc/Data/input/gamecontrollerdb.txt`; the WASM sandbox cwd has no such file). One test (`shot gives ball velocity`) was updated for the new pending-release timing (steps past the 0.20 s contact frame before asserting velocity).

**Exit criteria:** user video re-record shows no treadmill, no magnet trap, kicks connect to ball. *(Pending a native Windows rebuild + re-record; not yet visually verified.)*

### Phase 1 — AME core (2–3 weeks)

| # | Task | Files |
|---|---|---|
| 1.1 | Blend space: speed × turnRate × ballState → clip + phase + weight (replace `SelectClip`) | `SoccerClipRig.cs`, `BrowserBoot.gd` (mirror) |
| 1.2 | Runtime foot-planting IK (port `footlock._ik` to C# + GDScript) | `SoccerClipRig.cs`, `BrowserBoot.gd` |
| 1.3 | Archetypes: Explosive/Lengthy/Controlled via `loco()` params + `CharacterSpec.Archetype` | `soccer_motions.py`, `CharacterSpec.cs`, `Teams.cs` |
| 1.4 | Directional locomotion set (strafe/backpedal/jockey) | `soccer_motions.py` |
| 1.5 | Look-at + reach polish | `SoccerClipRig.cs`, `BrowserBoot.gd` |
| 1.6 | Phase sync on clip switch (no foot pop) | `SoccerClipRig.cs`, `BrowserBoot.gd` |

**Status: DONE (2026-11-18).** All six items implemented on `arena/a7fc5fee-c-games` (C# core + desktop `SoccerClipRig.cs` + browser `BrowserBoot.gd` kept in lock-step):

- **1.1** — Blend space replaces `SelectClip`: `SoccerClipRig.SelectClip(speed, turnRate, hasBall)` maps (speed, turnRate, ballState) → clip; `SelectDirectionalClip(speed, headingOffset, hasBall)` adds heading-based selection. GDScript `clip_select_locomotion` mirrors this with heading-offset computation from velocity vs facing.
- **1.2** — Two-bone analytic IK ported from `footlock._ik`: `SolveTwoBone` (C#) / `solve_two_bone` (GDScript) use law-of-cosines + pole vector + shortest-arc quaternion. Only corrects feet near the ground plane (planted phase), leaving swing-phase feet to the clip.
- **1.3** — `Archetype` enum (Controlled/Explosive/Lengthy) on `CharacterSpec`; `Teams.CreateRoster` assigns by role/pace/height; `ARCHETYPE_PRESETS` in `soccer_motions.py` define `loco()` params per archetype; runtime biases (lean/cadence/stride/roll) applied in both C# (`SetArchetype`) and GDScript (`ARCHETYPE_BIAS`).
- **1.4** — Four new directional clips: `soccer_strafe_l`, `soccer_strafe_r`, `soccer_backpedal`, `soccer_jockey` (71 clips total, 82 aliases). Built from `loco()` with lateral weight shift / reverse lean / low wide stance.
- **1.5** — Head look-at (neck+head yaw/pitch toward ball, clamped) and arm reach (extends toward nearby ball for traps/receives) in both C# (`UpdateLookAt`/`UpdateReach`/`ApplyLookAndReach`) and GDScript (`apply_look_reach`).
- **1.6** — Phase sync: on clip switch, the new clip starts at the current cycle phase (`startPhase`) so feet don't pop. Both C# and GDScript track `_phase`/`clip_t` continuously.

**Exit criteria:** 90° cuts, strafes and traps look planted (IK + phase sync); three archetypes visibly distinct (stride/cadence/lean biases); `test_soccer_forge.py` 74/0 + `test_pads.py` 129/0 + `gdparse` clean.

### Phase 2 — Gameplay depth (3–4 weeks)

| # | Task | Files |
|---|---|---|
| 2.1 | First-touch system: heavy/light touch by pressure, stamina, skill; knock-on | `Match.cs:TryPossession`, `BallPhysics` |
| 2.2 | Dribble system: touch interval, momentum-limited turns (eFootball-style weight), explosive bursts (FC-style), skill moves on stick gesture | `Match.cs:MovePlayer`, `HumanActions`, `soccer_motions.py` |
| 2.3 | Passing variety: driven/lofted/threaded/chip + curve; keep attribute-driven (eFootball lesson — don't gate behind PlayStyles) | `Match.cs:PassTo`, `BallPhysics` |
| 2.4 | Shooting: placement vs power, first-time vs set, control shot, **Dynamic Volley** (first-time aerial, eFootball v6.0) | `Match.cs:Shoot` |
| 2.5 | Defending: jockey/contain, timing meter, shoulder vs slide; less-automatic tackles (eFootball v5.4 lesson) | `Match.cs:AttemptTackle`, `Decide` |
| 2.6 | Keeper AI: angle-cutting, rush, punch vs catch vs parry; 1v1 positioning (eFootball v5.4) | `Match.cs:Decide` (keeper), `BallPhysics` |
| 2.7 | Off-ball AI: overlap/underlap/decoy runs, third-man; **Fluid Formations** (attack/defence shapes) + **Overload** Team Playstyle (eFootball v6.0) | `Match.cs:Decide`, `Teams.cs` |
| 2.8 | Set pieces: FK aim + curve, corner routines, throw movement, near/post assignments | `Match.cs:Restart`, `SetPieceAim.gd` |
| 2.9 | Authentic/Competitive presets (FC 26-style + eFootball measured tempo): `MatchOptions.Preset` scales pace, tackle accuracy, weather, stamina effect | `Match.cs`, `GameApp.cs` |

**Exit criteria:** dribbling, first touch and tackling feel skill-based; keeper angles visibly better; presets feel distinct.

### Phase 3 — Presentation and platform (4+ weeks, parallelisable)

| # | Task | Files |
|---|---|---|
| 3.1 | Post FX (desktop High only): ACES tonemap, bloom, vignette, LUTs | `World3D.cs`, `StadiumKit.gd` |
| 3.2 | Pitch: normal-mapped grass, mowing stripes, wear, wet reflections | `pitch.gdshader`, `StadiumKit.gd` |
| 3.3 | Ball: panel normal, spin blur, trail; net ripple | `ball.gdshader`, `net.gdshader` |
| 3.4 | Crowd + audio: procedural ambience, reactions, whistles, impacts | `ProceduralAudio.gd`, `crowd.gdshader` |
| 3.5 | Replay/slow-mo + camera cuts (built on 6-view system) | `ReplayRecorder.gd`, `World3D.cs` |
| 3.6 | Modes: tournament (Custom Tournament-style, up to 8, spectatable), season/Master League Sprint-style, training, shootout, local 2P polish | `GameApp.cs`, `Match.cs` |
| 3.7 | Quality presets + auto-detect (Low/Med/High); free-to-play friendly (eFootball lesson: all devices) | `MatchOptions`, `World3D.cs`, `BrowserBoot.gd` |
| 3.8 | Match Analysis (last 10 matches, style charts) + real-time advice (eFootball v5.2) — cheap from existing event log | `Match.cs` events, `Hud.cs` |
| 3.9 | (Optional) Learn blend weights from recorded play — first ML step | `Tools/` offline, export weights to manifest |

**Exit criteria:** desktop High looks broadcast-grade; browser Medium still 60 fps on a laptop; all tiers pass `test_pads.py` + `test_soccer_forge.py`.

---

## 8. Sprite Forge — what it can do more of

Sprite Forge is already the right tool. It needs **soccer-specific extensions**, not a rewrite.

| Enhancement | Module | Effort | Payoff |
|---|---|---|---|
| **Phone-video mocap for soccer** — multi-angle capture, ball tracking, foot-contact detection; `forge.py motion record --folder` already does single-angle | `mocap.py`, `motion_cli.py` | Medium | Real dribble/trap/turn clips instead of procedural `loco()` |
| **Soccer game pack v2** — extend `game_packs/soccer.json` with dribble touches, first-touch, skill moves, keeper parry/rush; export events to Arena manifest | `game_packs/soccer.json`, `gamepack.py` | Low | Event-synced clips (Phase 0.1) |
| **Runtime foot-lock** — port `footlock.lock`/`_ik` to a Godot-ready format (bake stance-foot targets into clip metadata) | `footlock.py` | Low | Phase 1.2 IK without runtime solving |
| **Archetype generator** — `loco()` with Explosive/Lengthy/Controlled presets + height/bulk scaling; batch-export 3 variants per locomotion clip | `motions.py`, `footballer.py` | Low | Phase 1.3 without new mocap |
| **Blend-space exporter** — export blend weights + phase-sync points alongside clips (not just keyframes) | `blend.py`, `motionlib.py` | Medium | Phase 1.1 data-driven blending |
| **Polish presets for soccer** — `clean_keys` with soccer joint limits (knee hyperextension, ankle dorsiflexion), anticipation for kicks, follow-through for headers | `motionpolish.py`, `motionlib.py:clean_keys` | Low | Fewer weird poses in new clips |
| **Body variants** — `footballer.build` with height/bulk/leg-length params matching `CharacterSpec` (currently one base + runtime scale) | `footballer.py`, `gamemesh.py`, `lod.py` | Medium | Distinct silhouettes per archetype; LODs for mobile/browser |
| **Kit texture bake** — `gamemesh.bake` + `footballer.paints` to baked kit texture variant (keep flat-colour for per-club tint) | `gamemesh.py`, `kits.py` | Low | Optional visual upgrade without skeleton change |
| **Clip QA** — `qa.py` checks: foot slide > 5 cm, joint limit violation, ball-contact frame present, loop seam error | `qa.py`, `Tools/test_soccer_forge.py` | Low | Catch bad clips before they ship |

**What Sprite Forge should *not* do:** runtime animation (that's AME in Godot), sim logic (that's `Match.cs`), or online (that's the .NET server). Keep the boundary clean: Sprite Forge bakes, Godot plays, `Match.cs` decides.

---

## 9. Risks, non-goals and honest limits

| Risk / limit | Mitigation |
|---|---|
| **No mocap stage, no ML cluster** — we will never match EA's 8.7M frames | Phone video + procedural variants + rule-based synthesis. 80% of feel, 5% of cost. ML later if wanted. |
| **18-bone skeleton** — no finger, toe, or cloth bones | Enough for football. Cloth/hair via shader/jiggle in Phase 3, not new bones. |
| **Compatibility renderer** — no Forward+ features on web/mobile | Tiered quality; fork renderer per platform only if Phase 3 demands it. |
| **Browser JSON size** — 140 clips × 18 bones × 31 frames ≈ 3 MB | Acceptable (current 67 clips = 2.0 MB). Compress quaternions to 3 components if needed. |
| **Determinism across platforms** — float differences C# vs GDScript | Sim is C# only (server + desktop). Browser GDScript sim is a *separate* lightweight sim for offline; online browser clients render server snapshots. No cross-platform float equality required. |
| **Scope creep** — trying to build Career/UT now | Phase 0–1 first. Modes are Phase 3. |

**Non-goals:** licensed clubs/players/stadiums, real mocap suits, copying EA code/data, microtransactions, matchmaking infrastructure (friend codes are enough).

---

## 10. How to verify progress

Each phase has a **video test** (the user's recording is the baseline) + **automated tests**:

| Check | Command | Pass |
|---|---|---|
| Sim determinism | `dotnet run --project Tests/MatchCoreTests.csproj` | All pass; owner flips < 50/60s, goals > 0 |
| Clip/manifest | `python3 Tools/test_soccer_forge.py` | 52/0 → grows with each phase |
| Pads/input/camera | `python3 Tools/test_pads.py` | 129/0 |
| GDScript parse | `gdparse Web/BrowserBoot.gd` | Clean |
| CI | `arena-fc-tests.yml` (dotnet-core + Sprite Forge steps) | Green |
| **Video** | Re-record 55s native desktop + browser preview, same seed | No treadmill, no magnet trap, kicks connect, no scrums |

---

## Appendix A — File map for implementers

```
arena-fc/
  Scripts/Core/Match.cs            # Sim: Decide, PassTo, Shoot, AttemptTackle, BallPhysics, TryPossession
  Scripts/Core/CharacterSpec.cs    # Height/Bulk/LegLength + Pace/Shooting/Passing/Defending/Goalkeeping
  Scripts/Core/Teams.cs            # Clubs, formations, roster generation
  Scripts/Godot/SoccerClipRig.cs   # Desktop clip playback (AME Layer 2+3 lives here)
  Web/BrowserBoot.gd               # Browser clip playback (mirror of SoccerClipRig)
  Tools/soccer_motions.py          # Clip registry (67 → ~140)
  Tools/build_soccer_player.py     # Bake: sculpt → retarget → GLB + JSON + manifest
  Tools/test_soccer_forge.py       # Clip/manifest checks
  Data/soccer_player_manifest.json # Clip list, aliases, materials (add events + natural_rate)
  Data/soccer_rig.json             # Browser mesh + baked clips (add events)
  Data/models/soccer_player.glb    # Desktop mesh + clips

sprite_forge/
  sforge/mocap.py                  # Video → skeleton (extend for soccer)
  sforge/motionlib.py              # clean_keys, plant_on_rig, retarget_motion
  sforge/footlock.py               # Foot planting IK (port to runtime)
  sforge/blend.py                  # Crossfade (use for locomotion blending)
  sforge/motionpolish.py           # Joint limits, weight shift
  sforge/footballer.py             # Sculpted player (add archetype variants)
  sforge/motions.py                # Procedural loco() (parameterise by archetype)
  game_packs/soccer.json           # Events: ball_contact, footsteps (extend + export)
  motion_library/                  # Generic clips (starter set)
```

## Appendix B — Sources

**EA FC / HyperMotion:**
- HyperMotion origin (WIRED, FIFA 22, 8.75M frames, LPS, ML context blending) [1](https://www.wired.com/story/fifa-22-hypermotion/)
- HyperMotion features (ML-Flow, kinetic air battles, composed ball control, humanisation) [2](https://www.mirror.co.uk/sport/football/news/fifa-22-new-features-hypermotion-24680794)
- FC 26 HyperMotion V2 Plus (2,000+ anims, run cycles by body type, volumetric) [1](https://www.fifaworldcupnews.com/ea-sports-fc-26-release-date-features/)
- FC 26 deep dive (dribbling, GK RL positioning, passing, shooting) [2](https://www.thesixthaxis.com/2025/07/22/ea-sports-fc-26-deep-dive-explains-the-gameplay-changes/)
- FC 26 presets + reviews (Authentic vs Competitive, defending, GK) [1](https://godisageek.com/2026/07/fc-26-review/) [3](https://www.pushsquare.com/reviews/ps5/ea-sports-fc-26) [4](https://www.gamespew.com/2025/09/ea-sports-fc-26-review/)
- FC 26 community post (dynamic dribbling, shielding, enforcer) [4](https://ea.com/en-gb/news/ea-sports-fc-26-community)
- FC 26 archetypes + control shot + keeper overhaul [5](https://www.gamemeca.com/en/view.php?gid=1766119)
- Mocap loop (record → solve → clean → retarget → blend) [5](https://sunstrikestudios.com/en/blog/motion_capture_for_games_and_film/)

**Pro Evolution / eFootball:**
- PES legacy (Master League, individuality, tactics, Unreal Engine, free-to-play rebrand) [5](https://www.playefootballgame.com/pro-evolution-soccer/)
- PES 2011 (total control, 1,000+ mocap anims, 100h capture) [1](https://worthplaying.com/article/2010/7/13/news/75516-pro-evolution-soccer-2011-all-reveals-new-features-game-modes-screens/)
- PES 2013 FullControl (manual pass/shoot, R2 first-touch) [4](https://pro-evolution-soccer-2013.en.download.it/)
- eFootball v6.0 Aug 2026 (Custom Tournament, Fluid Formations, Overload, Dynamic Volley, Link-Up Plays) [1](https://www.konami.com/games/eu/en/topics/19232/) [3](https://www.konami.com/efootball/en/topic/news/5558)
- eFootball 2026 v5.x (measured tempo, defensive overhaul, Master League Sprint, feints, 1v1 GK) [2](https://www.fifaworldcupnews.com/efootball-2026-features-latest-updates/)
- eFootball v5.2 (Match Analysis, real-time advice, AI Control, through-ball rebalance) [4](https://egw.news/fifa/news/30963/efootball-2026-v520-update-brings-massive-overhaul-gG3fZO69-)
- eFootball 1B downloads (Apr 2026) [5](https://www.insideworldfootball.com/2026/04/10/konami-hits-1bn-downloads-efootball-game-launches-suite-new-features/)
- FC 26 vs eFootball 2026 gameplay (dribbling/passing/shooting/defending/AI) [1](https://soccergaming.com/fc-26-vs-efootball-2026-which-gameplay-is-better/) [2](https://www.mrgeek.net/blog/fc-26-vs-efootball-26)

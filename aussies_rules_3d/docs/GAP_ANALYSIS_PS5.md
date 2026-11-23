# Gap analysis — Aussies Rules 3D vs the PS5-generation AFL / GAA standard

**Date:** 2026-11-06 · **Base:** `main` @ `b279879` (post-#256…#260) · **Author:** session engineering notes
**Scope:** what stands between this game and the latest PS5-era Australian rules / Gaelic football titles, what can close it, and what cannot.

Reference titles (verified 2026-11-06):

| Title | Studio / publisher | Platform & date | Notable
|---|---|---|
| **AFL 26** | Big Ant Studios / Nacon | PS5 (+PS4/Xbox/Switch 2/PC), 8 May 2025 | PS5 Metacritic ~75; official AFL license; photogrammetry/scans + mocap; 50+ recreated stadiums (series coverage); career paths (player + management); AFLW; $59.99 on PS Store [1][2][3][4] |
| **Gaelic Football Laochra** | Buck Eejit Games (≈7-person Belfast team) / Tru Blu | PS5 (+Xbox Series X\|S/Steam), 28 May 2026 | First GAA game in ~20 years; Aidan Forker cover; Michael D McAndrew commentary; 34 county teams + London/New York creation suite; career mode, tournaments, local 2P at launch, online later; latest ruleset [5][6][7][8][9] |

Laochra matters here: it proves a **small team on a small budget** can ship a credible modern football game. AFL 26 shows what a licensed, 100+-person studio looks like. Aussies Rules 3D sits far below both today — but the gap decomposes cleanly into (a) things we can build, (b) things we cannot afford/licence, and (c) things we must not claim.

---

## 1. Current state of Aussies Rules 3D (verified, this repo)

| Area | State (evidence) |
|---|---|
| Rules sim | 18-a-side, AFL 2026 laws (per in-game footer), difficulty tiers (Rookie/Club/AFL), quarter lengths (3/5/20 min), interchange = 5/team (`rules/types.ts`), fatigue + metres-since-break, pass-assist handball targeting, ball aero w/ drag + spin Magnus (`sim/ball.ts`) |
| Render | three.js/WebGL, antialias, PCF shadow map, IBL (RoomEnvironment), procedural AFL guernseys (12 clubs, patterns/collar/number via `render/guernsey.ts`), LED perimeter ribbon, 3D scoreboards + LED bug, broadcast cam w/ dynamic framing (`render/camera.ts`), blob contact shadows |
| Players | 52-joint squad GLB, 32 authored (not mocap) clips, nine looks, contract-gated in CI (`scripts/check.mjs`) |
| Motion | **Shared Arena Motion Engine in use** — TS port (`src/motion/*`, 1,063 lines, port of arena-fc MotionEngine minus 18-bone gate) live via `MotionBinding` → `players.ts`; baked assets `afl_motion.json` (32-clip manifest) + `afl_motion_features.json` (1,273 × 24-dim feature table, z-scored, 0.2/0.4/0.6 s horizons, `time_to_contact` weight 12); LOCOMOTION_QUERY_INTERVAL 0.1 s; exact deterministic O(N) search (no IVF) responsible-behaviour crossfade (0.12 s) + contact-aligned playback scale; one-shot routing (kick→drop_kick set / kick_run on run); 20 motion-related tests green; gait search consumes the 24-dim trajectory prediction dims |
| AME core (C99) | `shared/arena_motion/` — framework contract finalized; v2 trajectory query **not live** in games; Gaelic adapter live for idle/jog/run/sidestep/carry + handpass/solo action matching; our web port does the gait+action queries live (TS) |
| Audio | WebAudio fully synthesized — crowd bed w/ excitement, kick thud, bounce, whistle, roar, siren. **No commentary, no voice, no chants** |
| Online | `shared/netplay/` exists (C + WS server) but is **not wired into this game**. No online mode |
| Modes | Single match only (+attract demo). **No career/season/ladder/tournament/club mgmt/creation suite** |
| Perf | **Never measured on a GPU anywhere.** LOD runtime landed (#254) but shipped GLB carries no `_lod` nodes (no-op); LOD candidate contract-verified in CI (`aussies-rules-motion-ab.yml`, #259/#257), **swap rejected**, browser unverified. SwiftShader CI captures run (experimental, unverified pixels) |
| Licensing | **Zero rights.** No AFL, AFLPA, club, or stadium licenses. Kits are "AFL-inspired". Fictional LED sponsors. Siren/scoreboard generic |

**Reference-point measurements on this machine:** squad GLB 18.8 MB (249k tris reported in review; 318,539 base tris measured by the A/B tool — definition differs: "base-look tris" vs "mesh tris", both reported honestly); `stadium.glb` 2.6 MB; `ball.glb` 0.1 MB; `afl_motion_features.json` 330 KB.

## 2. Head-to-head: what PS5-class football games ship

**AFL 26** [1][4]: engine (Big Ant "Sports Engine"), official AFL license since the series' revival, photogrammetry/real-player scans + motion capture, 50+ stadiums recreated, career modes (player + management), AFLW, loyalty rewards, $59.99; Metacritic 75 (PS5) — praised for improved gameplay vs AFL 23, criticized for AI decision-making and a rough launch; reviews note it is "still patching away".

**Gaelic Football Laochra** [5][6][7][8][9]: ~20 years since the last GAA game (Transmission, 2007 PS2). Small Belfast team; Tru Blu publishing (the same publisher Codemasters/Big Ant uses for AFL). Content scope achieved: 34 counties via a **creation suite** rather than licensed names, career + tournaments, local 2P day one, online deliberately deferred, commentary by a real broadcaster, latest ruleset changes, cover athlete Aidan Forker.

**Takeaway for us:** nobody is "close" on an indie budget to AFL 26. Laochra is the honest ceiling for a team of our size — and even it ships no online and uses creation-suite branding to dodge licensing.

## 3. Dimension-by-dimension gaps

Severity: 🔴 blocking commercial release · 🟠 major credibility gap · 🟡 polish/quality · 🟢 strengths we should lean on.

### 3.1 Licensing & content rights 🔴
AFL 26 is inseparable from its license (AFL marks, 1,200+ scanned players in AFL 23 terms, club identities, broadcast look). We have **none of it**: club names/logos/likenesses/music/commentary/broadcast overlays are all unlicensed. Laochra solved this with creation-suite branding + one cover athlete deal.
→ **Cannot be closed with engineering.** Requires rights holders (AFL, AFLPA, clubs) or deliberate unlicensed fiction (fictional leagues, invented clubs/players — the LED board already uses fictional sponsors; extend that pattern). Any commercial release on "AFL"/club marks without a license is not viable.

### 3.2 Player models & likeness 🔴🔶
AFL 26: photogrammetry + scans, distinct faces, licensed names. Ours: one shared squad rig (52 joints, nine looks) retargeted from a generic athletic base (MakeHuman-lineage), 18.8 MB, nine bodies × 12 clubs, **no faces, no likenesses, no player identities**.
→ Gap closeable only via (a) licensed scans (cost, not skill) or (b) a fictional-league direction (invented names/faces — cheap, legal). Body diversity beyond 9 looks = more work on the atlas/rig, doable.

### 3.3 Animation & motion — the shared AME work 🟠 (currently our strongest asset, still far off)
What we have (verified in-tree): a real, deterministic, tested motion-matching path (see §1). What PS5 titles additionally ship:
- **Actual motion capture.** Every claim of "life-like" movement in AFL 26 ultimately rests on mocap + tuning, not on matching alone. Our clips are authored/retargeted — crossing from "reads as animation" to "reads as *that athlete*" needs capture (budget) or at minimum a larger, better-authored clip set (free-ish, slow).
- **Foot-plant + contact IK.** We track clip foot-plant phases for FX only; there is **no planted-foot constraint IK** and stride scaling is unconstrained (the Gaelic branch shipped a `strideLimit()` + planted-foot fade — **not yet ported**). Expect foot sliding at some speeds; unverified on GPU.
- **Ragdoll / physics reactions.** None — `knocked_down`/`stumble`/`hit_react` are authored one-shots. PS5 games blend physics reactions for unpredicted contact.
- **Entire action coverage:** AFL-specific actions — mark contest, spoil, fend-off, ruck contest, snap kick, throw-in, siren/set-shot celebrations — were authored in the (never-shipped) 11-clip AFL library (see `MOTION_GRAPHICS_REVIEW.md` §3/Phase 2, 43-clip candidate, NOT in shipped GLB). Shipped manifest has 32 clips; the AFL-specific layer needs re-review, relicensing or honestly re-authoring.
- **Contact-time alignment unwired:** the sim has `kickCharge`/wind-up only for the human; AI disposals are effectively instant. AME's `secondsUntilContact` path is therefore unobservable for AI players — aligning kick contact to the rules clock needs sim-side disposal wind-up for AI first.
- **No trajectory-matched selection in web port** (the 0.2/0.4/0.6 s horizons are features, and the gait/action search uses them, but the C core's separate v2 trajectory-match path remains off, as designed/documented in `shared/arena_motion/README.md`).
- **No facial animation, no micro-expression, no crowd-player interaction.**

→ Ordered, mostly-legal actions: (1) port Gaelic's stride-limit + planted-foot fade (math-only, testable headlessly), (2) AFL-clip coverage pass authored on our rig (mark/spoil/ruck/throw-in/celebrations; license-clean, provenance-checked), (3) sim-side AI disposal wind-up so contact alignment works for AI, (4) UDP/IK foot planting if GPU budget allows (Three.js IK via bone constraints or simple 2-bone IK), (5) only then consider mocap acquisition.

### 3.4 Rendering & graphics 🟠
AFL 26: PS5-targeted PBR, 4K/60, weather, recreated stadiums at correct times of day. Laochra: indie, but licensed cover athlete, real stadiums, modewest lighting.
Ours: three.js antialias + PCF shadows + RoomEnvironment IBL; PCF shadow (not soft/VSM/CSM); **no post-processing at all** (no bloom, AO, TAA/FXAA beyond MSAA, no color grading); single sun directional + ambient/hemi; crowd is a **texture** (fixed dots on stand geometry) — no crowd agents, no stands detail pass; pitch is flat painted lines; stadium is one 2.6 MB mesh; ball 0.1 MB (good); **zero GPU measurements anywhere** (fps, frame-time, draw-call budget); LOD system exists but inert (no `_lod` nodes in shipped asset; candidate in CI, never rendered); textures mostly canvas-generated (deliberately light, phone-friendly).
→ Highest-value, no-license actions: (i) **measure** (rAF frame-time HUD or `renderer.info` in a debug flag; add perf capture to `visual-ab` leg), (ii) port stride-limit/foot fade (see 3.3), (iii) post stack: cheap bloom + vignette + tonemap (UnrealBloom or a half-res threshold pass) — biggest "life-like" perception gain per hour, (iv) stadium/crowd pass: time-of-day variants + simple crowd instancing shimmer (two atlas frames swapped rarely) for atmosphere, (v) ship the LOD candidate **only after** browser/GPU verification — do this in the same PR as the perf harness so the decision is data-driven.

### 3.5 Presentation & broadcast 🟠
Strengths: five camera views with dynamic openness model, behind-goals & wing knowledge built into the camera (`DESIGN_REVIEW.md` cites the ABC analysis), LED ribbon + 3D scoreboards + LED bug, celebration camera, siren/roar.
Missing vs PS5: **replay system** (immediate + slow-mo), full-time ceremony/walk-off, umpire feedback (merge: none), lower-thirds with player names/stats (our "markers" are abstract chevrons), team sheet/ladder screens, pause/menu art, half-time analysis, set-piece presentation ("goal review"), in-moment camera cuts (we do none of the behind-goals → close-up cut rhythm that defines AFL TV).
→ Action: a **TV-direction layer** (cut logic on score/mark/kick-in events, replay ring buffer of the last ~8 s of sim state → render from replay camera) is buildable today, no licensing, sequencing skill-bound, and moves perceived authenticity more than any single shader.

### 3.6 Audio & crowd 🟠
Ours: fully synthesized WebAudio (crowd bed w/ excitement band, kick, bounce, whistle, roar, siren) — impressive constraint compliance (offline, tiny) but "game without commentary".
AFL 26: licensed broadcast sound; Laochra: named commentator (Michael D McAndrew) + stadium atmosphere.
→ Action: crowd chants (crowd-sourced or synth-phrased sing lines), player effort grunts, umpire whistle/calls ("mark!", "hold the ball!") — text-to-speech or recorded one-off VO (licensing: union-negotiated one take), plus commentary hooks (commentary exists as data-driven line engine w/ dry lines; avoid real broadcasters until licensed).

### 3.7 Rules & simulation depth 🟡
18-a-side, quarters, interchange=5, fatigue, metres-since-break, pass assist, spin/Magnus — solid spine. **Unknown/needs audit:** advantage rule, 50 m penalties, holding-the-ball/tackle-from-behind free assignment edge cases, mark contests (holding/spoil), bounce rule (10 m overstep), scoring set shots within 25/35/50 boundaries, behind/goal integrity under pressure, free-kick advantage flow, siren-time goals, umpire decision model. AFL 26's AI (even licensed) is panned for poor decisions [1] — simulation fidelity ≠ AI quality.
→ Action: **laws-of-the-game audit** (`docs/fwd-laws-audit.md`) — test-per-rule from the official 2026 AFL laws; each rule: sim behavior + test. Cheap, boring, huge for credibility; catches exploits.

### 3.8 AI 🟠
Rookie/Club/AFL tiers exist; difficulty feeds selection. No published behavior model; support running, defensive pressing, forward-line patterns, set-play calls — unverified. AFL 26 review consensus: AI poor decisions is the genre's hardest problem, not a "solved" one.
→ Action: blueprint perception→intent layers with explicit utility scores (kick to space vs carry, marking contest read, defensive pressure curve); instrument existing sim with per-decision telemetry before changing anything; evaluate vs recorded pro-game priors. Multi-week, no licenses, high risk of rabbit-holing — timebox it.

### 3.9 Modes & content depth 🔴
Laochra (indie, 7 people): career, tournaments, 34-county creation suite, 2P local. AFL 26: career paths + management, AFLW, online PRO Team, ladder/season.
Ours: one match. No season structure, ladder, trophies, draft, injuries, morale, training, or career. **Creation suite = biggest ROI**: invent all teams/players procedurally → fictional "APL" (Australian Premier League) — solves 3.1/3.2 wholesale and instantly looks like "an AFL game" without trademarks.
→ Action: season/tournament framework on top of the single-match sim (fixtures, ladder, premiership points, premiership ladder math already trivial), fictional league content pack (clubs + names + guernsey patterns generator — we already have the guernsey painter), local 2P already effectively present (input profiles separate).

### 3.10 Online 🔴
`shared/netplay/` (C + WS server) is in-repo but **not integrated** here; AFL 26 has PRO Team ecosystem; Laochra defers online.
→ Action: wire netplay for 1v1 quick match (or defer honestly). Do NOT attempt ranked ecosystem. Local 2P is the honest "multiplayer" today — verify it works on gamepad/keyboard, then document it.

### 3.11 Platform & delivery 🟡
Web/PWA + Electron desktop; phones via browser; no App Store presence; no console anything. PS5 port implies native engine or middleware + Sony cert + devkits — **not happening this project**; the honest comparison target is "best-in-class browser/PWA football game".
→ Action: performance budget in CI (frame-time capture in visual-ab leg), mobile Safari verification, service-worker installability pass, size budget (<30 MB playable).

## 4. Roadmap — "as life-like as possible" within reach

| Tier | Item | Effort | Deps | Verify |
|---|---|---|---|---|
| **P0 (days)** | Port Gaelic stride-limit + planted-foot fade into three.js motion binding (+ tests) | 1–2 d | none | unit tests green; visual A/B in visual-ab |
| P0 | Laws-of-the-game audit w/ per-rule tests (`docs/fwd-laws-audit.md`) | 2–3 d | none | `check.mjs` stays 5/5 |
| P0 | Perf harness: rAF frame-time + renderer.info capture in Electron CI (`visual-ab` prints percentile table) | 1 d | #259 | CI job |
| P0 | Fix verify gap: GPU/browser manual check (guernseys, LOD, motion) — **required before any perf claim** | 1 d | human | screenshot/video |
| **P1 (weeks)** | TV-direction layer: replay ring buffer + event cuts (score/mark/kick-in) + instant replay UI | 1–2 w | P0 | gameplay video |
| P1 | AFL-coverage clips re-authored on shipped rig (mark/spoil/ruck/throw-in/celebration), relicensed or re-created; keep 32-clip contract gate green | 2–4 w | none | contract + tests |
| P1 | Post stack: bloom + vignette + tonemap; pitch normal/detail pass; crowd shimmer atlases | 1–2 w | P0 | visual A/B |
| P1 | AI intent layer telemetry + tuned weights (timeboxed 3 w max) | 3 w | P0 | telemetry deltas |
| P1 | Commentary hooks + synthesized crowd calls/chants | 1–2 w | none | audio review |
| P1 | Fictional league content pack + season/ladder framework + creation-suite seed | 2–4 w | none | playthrough |
| **P2 (months/biz)** | Browser GPU verification of everything (tester) | ongoing | human GPU | sign-off doc |
| P2 | Licensing strategy — AFL/AFLPA outreach OR full fictional-league pivot | weeks | business | term sheet/decision |
| P2 | Wire shared/netplay 1v1, honest "quick match online" | 2–3 w | infra | playtest |
| P2 | Mocap acquisition (licensed or in-house) — the only true "life-like" unlock | months | money/people | motion A/B |
| P2 | App-store/native packaging (Capacitor or Electron wrappers) | 1–2 w | none | store build |
| **Not now** | PS5 port; licensed commentators; AFLPA likenesses; ranked online; anything requiring console SDKs | — | — | — |

**Explicitly rejected:** shipping the LOD candidate without GPU verification; claiming "PS5 parity" anywhere in docs/PR/store copy; meshopt-quantized squad GLB (readback fails — see `MOTION_GRAPHICS_REVIEW.md` §3); any store claim of official AFL/club affiliation.

## 5. What "done" looks like — broadcast-authentic checklist
Score each 0–2 (not present / partial / convincing), goal ≥ 26/32 before any external release claim:

1. Motion: stride matches speed (no slide) **0** · contact aligned to action **0** · celebration/mark reactions **0–1** · crowd reactions **1–2**
2. Camera: cuts on events (not fixed shot) **0** · behind-goals angle used **1** (wing/behind exists, unused as cut) · replay on score **0**
3. Sound: crowd rises on contests **2** · commentary line coverage **0** · siren/roar **2**
4. Simulation: rules audit pass **?** (not done) · advantage flow sane **?** · 50 m / holding-the-ball correct **?**
5. Graphics: GPU-verified ≥ 60 fps mid-tier phone **?** · grass/stands hold up in motion **0–1** · bloom/vignette **0**
6. Content: 100% licensed-or-fictional — everything ships either rights-cleared or invented **1** (LED fictional; clubs still unlicensed)

**Honest headline:** with P0+P1 done this game could plausibly be the best free browser AFL game and a legitimately compelling original title — closer to Laochra's scope discipline than to AFL 26. It cannot be "AFL 26 quality" without the license, the mocap, and the team.

## 6. Sources
[1] AFL 26 — Wikipedia (platforms, date, Metacritic ~75 PS5, development) — https://en.wikipedia.org/wiki/AFL_26
[2] AFL (video game series) — Grokipedia (series history, AFL 23's 1,200 licensed players, Big Ant "Sports Engine", AFL 26 upgrades) — https://grokipedia.com/page/AFL_(video_game_series)
[3] AFL 26 PS4 & PS5 price/release — GG.deals ($59.99 PS Store) — https://gg.deals/game/afl-26-ps4-ps5/
[4] AFL 26 Release Date Set — Operation Sports (May 8, 2025 window; loyalty rewards) — https://www.operationsports.com/afl-26-trailer-and-loyalty-rewards-revealed/
[5] Gaelic football game by Belfast developers set to be released on PlayStation 5 and Xbox — Irish News — https://www.irishnews.com/news/northern-ireland/belfast-developers-putting-finishing-touches-to-irelands-first-homegrown-gaa-video-game-VGBSZLB4JJDIFFHJZK2FTILRNA/
[6] Gaelic Football Laochra: First GAA game in 20 years, 28 May — Hot 97 / Hotminute — https://hotminute.co.uk/2026/05/09/first-gaelic-football-game-in-20-years-launches-28-may/
[7] First new Gaelic football game in nearly 20 years is released — Roscommon Herald — https://www.roscommonherald.ie/first-gaelic-football-game-in-nearly-20-years-is-released_arid-99693.html
[8] New Gaelic football game launches this month — Irish Post — https://www.irishpost.com/news/belfast-studio-launches-new-gaelic-football-video-game-308244
[9] Gaelic Football Laochra is the first new GAA video game in nearly 20 years — Goosed (7-person team; online post-launch) — https://goosed.ie/news/gaelic-football-laochra-is-the-first-new-gaa-video-game-in-nearly-20-years/

**In-repo references:** `docs/MOTION_GRAPHICS_REVIEW.md` (AME review, feature table, rejected approaches), `docs/DESIGN_REVIEW.md` (camera research), `docs/AFL_PLAYER.md` (squad bake limits), `docs/LOD_CANDIDATE.md` (LOD status), `Gaelic_Football_3d/MOTION_MATCHING.md` (C99 AME + Gaelic adapter), `shared/arena_motion/README.md` (AME contract & limits), `scripts/check.mjs` (gates), `.github/workflows/aussies-rules-motion-ab.yml` (A/B CI).

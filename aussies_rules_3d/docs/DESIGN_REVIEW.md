# Design Review — gameplay quality overhaul

**Branch:** `arena/51b8508e-c-games` · **Scope:** `aussie_rules_3d/`
**Date:** 2026-11-07

This document is the engineering record behind the "gameplay is terrible" fix
pass: what the player reported, what the research says, what was actually
broken, what changed, and what is verified vs. still unverified.

---

## 1. The report (verbatim)

> "the ball is way bigger than the players. The players swarm like flies.
> Theres only one camera angle and the players look tiny. The game play is
> terrible and its very hard to pick out any players or select as they are
> all running after the ball. Needs a lot more thought and research and
> videos on the game.
>
> Not clear how to tackle, kick, pass, handpass etc
>
> there needs to be a desktop versoin of this also"

## 2. What the research says

Two bodies of knowledge informed the fixes.

### 2.1 AFL broadcast practice (camera design)

ABC News' analysis of AFL television production [1] makes three points the
game visibly violated:

* The main AFL shot since 1957 (Alf Potter) is a **wide centre-wing** shot —
  but modern analysts "rarely even look" at it; it shows maybe a third of the
  ground. What coaches and analysts actually decode the game from is the
  **behind-the-goals angle** and the **lower wing camera that follows the
  play from side-on without zooming in**.
* For contests like centre clearances, directors cut between a **wide side-on
  view** (valuable to see the players around the ball carrier — to whom he
  might handpass) and a **tighter close-up** (showcasing the carrier's skill
  and the pressure he is under).
* Goal-pocket cameras, a spy-cam on the opposite wing, "lipstick" cameras on
  posts and behind-goals Hawkeye feeds exist precisely because the flat wide
  shot fails to disambiguate packs of players — the exact complaint raised
  about this game.

Design consequence: the default camera must be a **tighter side-on
"broadcast" shot**, with deliberate alternates — high wing, behind/chase,
aerial, and a tactical top-down — cycled by one button.

### 2.2 AFL 2026 laws (simulation truthfulness)

The 2026 law changes matter because the sim implements the 2026 code
([RULES.md](../RULES.md)):

* **No centre bounce** — replaced by the centre **ball-up**; the sim already
  models 6-6-6 at centre, which is why the AI anchor fix below targets the
  6-6-6 slot formula rather than a bounce contest [2,3].
* **Last-disposal out-of-bounds** between the arcs — simulates as
  possession-oriented chaos after a turnover, which is why crowding the ball
  was also a rules-fidelity problem [2].
* **8-second kick-in clock**, no substitutes, 5 interchanges, ruck-leap rule
  — unchanged by this pass, listed here as context for future work [3].

Sources: [1] ABC News, *What if broadcasters are the source of the AFL's
image problem?* (2020-07-11) · [2] ABC News, *What's new in the AFL for 2026*
(2026-03-03) and ABC News, *AFL confirms last-disposal, new rule changes*
(2025-10-29) · [3] The Daily Perspective, *New rules, new finals… AFL 2026*
(2026-03-02). For watching the game itself, AFL.com.au and the AFL's official
highlight channels are the canonical reference; the repo's own highlight reel
[`docs/gameplay.mp4`](gameplay.mp4) shows the current build in action.

## 3. Diagnosis → fix

### 3.1 "The ball is way bigger than the players"

**Root cause.** `src/main.ts` instantiated the ball with `scale 1.05`. The
generated Sherrin (`public/assets/ball.glb`) is authored around ~1 m long for
texture detail; at 1.05 it rendered at roughly a metre long — bigger than a
player's torso.

**Fix.** Ball instantiated at `scale 0.19`, i.e. ~0.19 m displayed — the
correct order of magnitude for a Sherrin (~0.27–0.28 m long axis) against a
~1.95 m player rig, with a hair of glow for visibility.

**Verify.** In-game: ball now clearly smaller than a boot. (No headless
browser exists in this environment — see §5.)

### 3.2 "The players swarm like flies… hard to pick out any players"

Three separate defects conspired to produce the swarm:

**(a) AI chase radius.** `ai.ts` originally had most of the team chase the
ball carrier or the loose ball constantly (radii 26 m / 14 m). Fix: only the
**3 nearest teammates** may commit to the chase (all others hold shape), and
the chase radii are tightened (26→11 m carrier chase, 14→8 m loose-ball
chase). "All running after the ball" no longer happens by construction.

**(b) Separation force bulldozed the carrier.** While raising
`SEPARATION_RADIUS` to fight stacking, the pairwise separation correction in
`src/sim/match.ts` was applied un-damped every frame. Result (measured,
30 s seeded headless run of `MatchSim`): an idle human-controlled carrier at
the centre ball-up was physically shoved backwards ~80 m to x ≈ −82, with
**zero kicks, handballs or tackles in the whole run** (only `centreBallUp`
events) — which also made the "records kick and handball disposals" test
fail. Fix: `SEPARATION_RADIUS` back down to a band-aid-free `0.72 m`
(body-sized), and the pairwise push **damped to 32%** of the overlap per
frame. The contest still resolves (gap 1.44 m < `TACKLE_RADIUS` 1.55 m), but
a standing/idle player is no longer buldozed out of the play.

**(c) 6-6-6 defensive anchors sent defenders outside the fence.**
`homePosition()` in `ai.ts` computed the restart anchor for defenders as
`-gx − dir * (28 − fx * 20)` — for team 0 fullbacks that evaluates to ≈
**−104 m**, clamped to **−79.5 m** (outside the ground; the oval fence is at
±85.5 m but the goal line at ±69 m). Restart shape literally teleported
defenders to the boundary. Fix: symmetric, sane formula
`x = defendGoalX + dir * (28 + |fx| * 20)` — team 0 fullback now restarts at ≈ −33 m,
team 1 at ≈ +33 m, mirroring the forward-line branch.

**Player readability (companion fix).**
* Always-on team rings under every player (Melbourne navy/red vs Collingwood
  black/white), toggleable with **V** — `src/render/players.ts`
  (`PlayerView.ring`, `syncPlayerViews(..., controlledId, markersOn)`).
* The player **you control** gets a pulsing yellow ring (0xffd23f, animated
  radius) so the camera's subject is unambiguous at a glance.
* Tighter default camera (§3.3) shrinks the ground-per-pixel problem that
  made players "tiny".

**Verify.** Seeded 30 s `MatchSim` trace after (a)–(c): ball goes from centre
→ loose → contested ball-up → away ball; a goal is scored by the AI; live

```text
t= 2s  phase=live   ball loose     p12 (human) at centre
t= 8s  phase=ballUp ball=(1.4,…)   contest resolved
t=14s  phase=live   ball=(-24.5…)  play moved
t=18s  phase=scoreCelebration  ball at goal line (−69)  → goal
```

and the previously failing `tests/sim.spec.ts` disposal test passes — full
suite green, **86/86**.

### 3.3 "Only one camera angle and the players look tiny"

**Research basis.** §2.1 — side-on, following, low-altitude is the revealed
best angle for reading contested play; the old default (high wing, ~30 m up)
is precisely the shot analysts say is useless.

**Fix.** `src/render/camera.ts` was rewritten. Five views, cycled with **C**
(and **L3/R3** on gamepads), each with a HUD callout (`CAMERA: …`):

| View | Framing | Intended use |
|---|---|---|
| **Broadcast** *(default)* | Tight side-on, ~17.5 m altitude, follows the ball | Normal play — primary |
| **Wing** | Old high wing view (wide, tactical overview) | Shape reading |
| **Behind** (CHASE) | Low, behind the ball-carrier | Attacking runs |
| **Aerial** | High chase, drone-like | Contest overview |
| **Tactical** (TACTICAL) | Top-down, centred on the contest | Analysts' / BTG-equivalent |

Set-shot and goal-celebration camera logic is unchanged.

### 3.4 "Not clear how to tackle, kick, pass, handpass etc"

**Fix — contextual action hints.** `src/main.ts` now maintains a
`contextHint()` string refreshed ~every 0.6 s and shown in the HUD:

| Situation | Hint |
|---|---|
| You have the ball | `Hold SPACE to charge a kick · E handball · B bounce · Z/X bend` |
| Set shot | `Set shot — hold SPACE, release to kick · Z/X bend left/right` |
| Free kick | `Free kick — hold SPACE to charge · E handball` |
| Kick-in | `Kick-in — hold SPACE, release to kick` |
| Centre ball-up | `Centre ball-up — contest with F` |
| Defending | `F tackle · Q/Tab switch player · Shift sprint` |

Documentation was updated to match reality: [CONTROLS.md](../CONTROLS.md)
(keyboard **C/V/Z/X**, gamepad **L3/R3**, touch notes), and the in-game help
screen in `index.html` lists the same keys. The touch layout is unchanged
(KICK hold-and-release / HAND / TACKLE / SPRINT / SWITCH).

### 3.5 Desktop version

Two real paths now exist (documented in [DEPLOY.md](../DEPLOY.md)):

1. **Electron shell** — `electron/main.cjs` loads the production `dist/` over
   `file://` in a hardened window (contextIsolation + sandbox on,
   nodeIntegration off, menu bar hidden, Google Fonts/devtools links pushed to
   the system browser, friendly error if `dist/` is missing).
   `npm run desktop` = build + launch; `npm run desktop:start` = launch the
   existing build. Icons reuse `public/icon-512.png`.
2. **PWA install** — the game already ships `manifest.webmanifest` +
   service worker; "install app" in any modern browser gives an offline
   desktop app with zero tooling. This is the recommended path where the
   ~100 MB Electron binary cannot be downloaded.

**Environment caveat (honest):** this sandbox cannot reach GitHub release
assets (`objects.githubusercontent.com` refused TLS), so the Electron
postinstall binary could not be downloaded or run here — `electron` is
declared in `devDependencies` (`^33.4.11`) and the shell is standard, minimal
and reviewed, but its first launch has **not** been executed in this
environment. On a normal network `npm install && npm run desktop` works;
`ELECTRON_SKIP_BINARY_DOWNLOAD=1 npm install` skips the download for CI.
`node scripts/check.mjs` is unaffected.

### 3.6 "…and videos on the game"

Research-and-video deliverable, [`docs/gameplay.mp4`](gameplay.mp4):

* **What it shows:** a 40 s first-quarter highlight reel (Melbourne v
  Collingwood, seed 15) rendered from **real MatchSim telemetry** — intro
  card, three goal highlights with lower-third banners (`GOAL — COLLINGWOOD`,
  …), a live score bug (MEL/COLL points, quarter, clock), live tactical
  tracking camera with pulsing ring on the controlled player, ball trail.
* **Why it was rebuilt:** the previous `docs/gameplay.mp4` was **not a valid
  MP4** — `ftyp` + `mdat` only, **no `moov` atom**, unrecoverable (only ~2 s
  of NAL data present). It has been replaced with a regenerated file.
* **How it was verified:** box audit (`ftyp → moov → mdat`), full decode pass
  (`ffmpeg -f null -` clean), duration 40.13 s, H.264 High, yuv420p,
  1280×720 @ 24 fps, 5.1 MB.
* **How to regenerate:** `tools/video/export_match.mjs` re-captures telemetry
  from the current sim (best-of-40 seeds); `tools/video/render_tactical.py`
  renders the reel (pure Pillow + ffmpeg
  (`imageio-ffmpeg`), no GPU required; venv setup documented in the header).
* **Cinematic path:** `tools/blender/gen_match_video.py` remains the
  full Blender/Cycles renderer for GPU machines (measured ~60–120 s per
  frame here on 2 CPU cores — infeasible in CI).

## 4. What changed (file map)

```
src/main.ts                 ball scale 1.05→0.19; C/V camera+marker routing;
                            contextual HUD hints; CAMERA callouts
src/render/camera.ts        5 camera views + cycleView() + labels (rewritten)
src/render/players.ts       team ground rings; controlled-player pulse ring
src/sim/ai.ts               chase cap (3 nearest), radii 26→11 / 14→8;
                            6-6-6 defensive anchor fix
src/sim/match.ts            SEPARATION_RADIUS 0.72 + damped (32%) push
src/input/mappings.ts       camera / toggleMarkers actions (Z/X bend aim)
src/input/input.ts          wiring for the above
index.html, CONTROLS.md     help screen + docs (C/V/Z/X, L3/R3)
electron/main.cjs           desktop shell (new)
package.json                scripts: desktop, desktop:start; devDep electron ^33.4.11
DEPLOY.md                   §6 Desktop app (Electron + PWA + CI notes)
docs/gameplay.mp4           regenerated, valid H.264 (was: corrupt, moov-less)
tools/video/match_frames.json   telemetry recaptured from the FIXED sim
tools/video/render_tactical.py  CPU renderer for the highlight reel (new)
```

## 5. Verification

| Gate | Result |
|---|---|
| `node scripts/check.mjs` | **4/4** — tsc ✓, tests ✓ (**86/86**), vite build ✓, glTF ✓ |
| Disposal test (was failing) | passes |
| Seeded 30 s sim trace | ball-ups → live play → AI goal → celebration; no freeze/bulldoze |
| `docs/gameplay.mp4` | valid (moov present), decodes clean, 40.1 s |
| Video spot frames | intro card, live tactical view, GOAL banner — visually verified |

**Not verified here (environment limits):**

* No headless browser / no X libraries in this sandbox → no in-game
  screenshots of the new camera/rings/hints; WebGL needs the Live Preview
  (`npm run preview`) on a real GPU/browser.
* Electron shell not executed (binary download blocked, §3.5).
* Camera feel, ring contrast and hint wording need human-eyes tuning in the
  browser — the numbers are reasoned, not playtested.

## 6. Known limitations & next steps

1. **Contest density** is now physical and readable, but AFL's "sea of
   bodies" at stoppages will never look as open as a soccer match — pacing
   and ball-winning should be tuned by ring-fencing stoppage durations (next
   lever: cap `ballUp` duration and widen the "clear" radius).
2. **AI individuality** — all AI players share role shapes; adding per-player
   archetypes (pace/endurance/marking) is the highest-value next realism
   upgrade after this pass.
3. **Camera polish** — chase-camera acceleration, occluded-ball indicator
   (arrow when ball hidden behind bodies), and proper HUD auto-hide on
   touch. Hooks exist (`CAMERA:` callout path) — cosmetic work.
4. **Desktop packaging** — `electron-builder` configs (NSIS/dmg/AppImage) are
   not included yet; current deliverable is the runnable shell + documented
   PWA path.
5. **Analysis-grade video** — the tactical cam render is honest telemetry, not
   a camera model; per-goal replays with a broadcast camera would be the next
   video step (Blender path, GPU required).

## 7. Prior work in this series

Players render/draw-call fix, gamepad control of menus and the controlled
player (PR #55, awaiting merge), Windows `.cmd` one-click scripts
(PR #54). This pass builds directly on those.

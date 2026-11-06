# Arena FC — 06.11.2026 gameplay / camera / EasySMX fix report

## Recordings analysed

| Clip | What it shows |
| --- | --- |
| `screenshots/06.11.2026_19.36.34_REC (1).mp4` (1280×742, 51.9 s, 25 fps) | Current desktop build. The camera swings from centre-circle to goal-line, corner/stand and midfield viewpoints within seconds; the controlled-player ring is thin; ball owner and ball are hard to follow; players move stiffly; no convincing short/long pass, dribble, sprint, kick or tackle response from the pad. |
| `screenshots/06.11.2026_19.40.33_REC.mp4` (804×464, 64.5 s, 25 fps) | Target: elevated, stable ball-following broadcast camera, clear player indicator, readable possession, close-control dribbling / shielding, short and long passing, and fluid human animation. |

Frame sheets used for the diagnosis were generated into the gitignored
`arena-fc/build/video_analysis/` directory. The target is a commercial football
title; this report does not claim parity with its art or animation system — it uses
the clip to define **camera stability, possession readability and reachable actions**.

## Why the controls appeared dead

1. **One-shot button presses were discarded.** `MatchEngine.Tick()` only called
   `Decide()` every 0.08–0.18 s, and pass / shoot / tackle / slide handling lived
   inside `Decide()`. A normal pad tap lasts one 1/60 s frame, so it was usually
   gone before the next AI decision tick. Human actions are now evaluated on
   **every fixed tick** in `HumanActions()`, and `MatchView` buffers one-shot edges
   across physics frames where the fixed-tick accumulator produces no tick.
2. **Two different `InputHub` instances.** `Hud` created its own hub, while
   `MatchView.Read()` polled another; HUD/touch state never reached the match.
   Both now share one instance.
3. **Menu START/accept was unreliable.** Button 8 was simultaneously `accept`
   and `back`; a first press on an unfocused overlay only seeded focus and did
   not activate. Fix: distinct accept/back buttons, first-press activation, a
   focus list containing only actionable widgets, and a fallback to the first
   focusable `Button`.
4. **Camera cycling could be triggered by a stick click.** The camera button now
   has a 0.12 s hold debounce, and mode changes are smoothed instead of snapped.

## Camera and possession readability

* New Godot-free `Scripts/Core/CameraPlan.cs` keeps the broadcast / ball-follow /
  sideline modes at a **fixed world orientation** and frames a weighted midpoint
  of the ball and controlled player. The shoulder mode uses a heading damped over
  ~0.7 s rather than instantaneous facing. Tactical keeps a stable `-Z` up vector.
  All targets are clamped to the stadium bowl.
* Five modes: **Broadcast**, **Ball follow**, **Shoulder**, **Sideline**,
  **Tactical**. `C` / pad R3 cycles; keyboard `1`–`5` still select directly in the
  browser edition.
* Distinct 3D markers: yellow ball ring, amber ball-owner ring + floating arrow,
  enlarged green controlled-player ring + floating arrow. The HUD shows
  `BALL · YOU/AWAY · NAME` (or `BALL · LOOSE`) and the minimap draws a line from
  the controlled player to the ball plus an owner outline.

## Reachable gameplay actions

| Action | Keyboard | Pad (mapped / XInput) | Raw EasySMX D-input |
| --- | --- | --- | --- |
| Move | WASD / arrows | Left stick / D-pad | Left stick / D-pad |
| Short pass | `E` | A (b0) | A (b2) |
| Through ball | `Q` | Y (b3) | Y (b0) |
| Long ball / cross | `R` | Back / Select (b4) | Back (b8) |
| Shoot (hold to charge) | `SPACE` | X (b2) | X (b3) |
| Standing tackle / press | `F` | B (b1) | B (b1) |
| Slide tackle | `SHIFT+F` | RB + B | RB + B (b5+b1) |
| Sprint | `SHIFT` | RB / RT (b10 / axis 5) | RB / RT (b5 / b7) |
| Close-control dribble + shield | `X` (hold) | LT / L3 (axis 4 / b7) | LT / L3 (b6 / b10) |
| Switch player | `TAB` / middle mouse | LB (b9) | LB (b4) |
| Camera | `C` | R3 (b8) | R3 (b11) |
| Pause | `ESC` | Start (b6) | Start (b9) |
| Menu select / back | Enter / Esc | any face button or Start / Back | any face button or Start / Back |

Additional simulation changes:

* **Sprint** is 1.42× (was 1.24×) with 25% stronger acceleration and a faster gait.
* **Close-control dribble** keeps the ball at ~0.30–0.36 m with alternating
  inside/outside touches, adds quick-foot animation, costs a little top speed but
  gives 35% more acceleration and makes the carrier harder to tackle.
* **Short pass** prefers nearby open teammates; **long ball** requires a distant
  target, adds power and loft, and is reachable from the pad.
* **Dispossession** has longer reach (2.9 m standing / 3.8 m slide), a higher base
  success chance, a dribble-evade penalty, and an automatic shoulder-charge
  strength contest when sprinting into a carrier without pressing tackle.
* Releasing the stick no longer auto-runs the human toward goal or formation.
* `PlayerCommand.Dribble` uses the existing protocol-v2 `sd` field, so the .NET
  server, desktop client and browser client keep one wire format.

## Animation

`Scripts/Core/Gait.cs` now includes hip yaw/roll, foot roll, shoulder
counter-rotation, sprint/dribble lean and stride blending. `RigAnimator.Pose`
eases between gait poses with `Gait.Lerp()` and blends kick / tackle / slide /
foul / dive clips in and out rather than snapping to a constant pose.

## Files changed

Core: `Scripts/Core/Match.cs`, `Match.Network.cs`, `CameraPlan.cs`, `Gait.cs`,
`Input/PadLayout.cs`, `Net/Packet.cs`. Desktop: `Scripts/Godot/Controls.cs`,
`PadMenuNavigator.cs`, `Ui.cs`, `GameApp.cs`, `MatchView.cs`, `Hud.cs`,
`World3D.cs`, `RigFactory.cs`. Web: `Web/Controllers.gd`, `Web/BrowserBoot.gd`.
Tests: `Tests/Program.cs`, `Tests/MatchCoreTests.cs`, `Tools/test_pads.py`,
`Tests/gd/test_pads.gd`, `Tests/gd/test_input_camera.gd`. Docs: this report,
`CONTROLS_AND_DEPLOY.md`, `FOLLOWUP_FIXES_REPORT.md`, `README.md`.

## Verification

Final head: `5b71c4e`. PR #53 is **MERGEABLE / CLEAN**, with every check green.
The .NET job now uploads its test logs as a CI artifact and surfaces any failing
test case as a GitHub annotation, which made the two remaining regressions
readable from the checks API.

| Check | Result |
| --- | --- |
| `python3 Tools/test_pads.py` | **120 passed, 0 failed**; **122 passed, 0 failed** with optional `gdtoolkit` + `tree-sitter-c-sharp` parsers |
| `dotnet build ArenaFC.sln -c Release` | **pass** (CI run `42291984663`, `dotnet-core`) |
| `dotnet build Server/ArenaFC.Server.csproj -c Release` | **pass** |
| `dotnet run --project Tests/CoreTests.csproj -c Release` | **pass** |
| `dotnet run --project Tests/MatchCoreTests.csproj -c Release` | **pass** |
| `Tools/run-gd-tests.sh` (headless Godot 4.7.2) | **pass** (`godot-gdscript`) |
| Node hub + `net_smoketest.py` / `net_v2_smoketest.py` | **pass** (`node-hub`) |
| Determinism / sim Linux + Windows + compare + netplay | **pass** (CI run `42291984682`) |
| GitGuardian security check | **pass** |
| Physical EasySMX / Windows rebuild / new gameplay recording | **user-side** |

### CI regressions found and fixed during this round

* `CS0117 MathF.Clamp` in the eased action envelope → `Math.Clamp`.
* Stale core-suite assertions that still expected LT to sprint → updated to
  LT=dribble / RT=sprint and added long-ball / R3 checks.
* `CS0136` duplicate `oppOwns` local in `Decide()` → renamed the human flag.
* `MatchCoreTests` gait assertion used phase 0, where hip yaw is legitimately 0 →
  split hip-yaw and foot-roll probes across two phases.
* Removing all human auto-movement cut opposition tackles from 30 to 7 → the
  selected player now auto-presses **only while the opposition has the ball**;
  AI closing was nudged up and foul odds slightly down. The 60 s / 11v11
  regression thresholds pass again.

Native `dotnet`/`godot` binaries, a physical EasySMX pad, a Windows rebuild and a
new gameplay recording remain **not available in this sandbox**; those are the
remaining user-side checks.

## Second pass — remaining 06.11.2026 issues

The first-pass fixes were CI-green, but the follow-up reported that the camera still "keeps moving
all the time", the ball carrier / controlled player / opposition were hard to track, EasySMX
select/start and gameplay buttons still looked dead, and there was no convincing short pass, long
pass, dribble or dispossession.  The two recordings were decoded again frame-by-frame (16-frame
contact sheets plus full-resolution crops of the HUD and controller overlay).  The target clip is a
commercial-football tutorial: the useful targets are its **stable elevated camera, immediate player
identification, safe close control, short/long passing and shielding**, not its art assets.

### Additional root causes

1. **Polling alone can miss a short press.** `Input.IsJoyButtonPressed()` only reports the state at
   the instant of the poll.  `PadMenuNavigator._Input()` and `MatchView._Input()` now latch every
   joypad button event in `InputHub`; `ReadButtons()` ORs the polled state, the held event state and
   one pending-press edge.  This is the missing link between "navigation works" and "select/start/
   kick/tackle does nothing".
2. **Select/Back had no action on the main menu.** It was mapped only to `back`, and the main menu
   has no Back/Resume button.  `TryGoBack()` now returns false on screens with no back target, and
   the same press falls through to activation.  Overlays still go back.
3. **The fixed-orientation camera still panned continuously.** `BroadcastPlan` recomputed its focus
   from the ball and player every frame, and camera height breathed with their separation.  The new
   `Focus()` / `AdvanceFocus()` helpers hold a dead-zone focus and ease only on a real breakaway.
4. **Possession cues were too small / hidden.** The old labels sat under the webcam overlay and a
   thin ring did not distinguish ball, owner, controlled player and nearest opponent.  The second
   pass adds always-on billboarded nameplates, larger rings/arrows, a pressure ring, a larger
   minimap with the same pressure outline, and a contextual top-centre action bar.
5. **Actions existed but had weak feedback / awkward reachability.** Gentle stick movement now
   enters close control, short pass prefers a near safe man, long ball stays distant and lofted,
   and a human tackle/slide lunges into range.  AI pressers do **not** lunge, preserving spacing.
6. **The squad still marched in lockstep.** `MatchEngine` seeds `AnimPhase` with
   `Gait.InitialPhase(index)`; `Gait.LookYaw()` turns heads/chests toward the ball; shield gets its
   own upper-body pose; `HeadYaw` is part of the eased `GaitPose`.

### Files changed in the second pass

Core: `Scripts/Core/CameraPlan.cs`, `Gait.cs`, `Match.cs`. Desktop: `Scripts/Godot/Controls.cs`,
`PadMenuNavigator.cs`, `MatchView.cs`, `Hud.cs`, `World3D.cs`, `GameApp.cs`. Tests:
`Tests/MatchCoreTests.cs`, `Tools/test_pads.py`. Docs: this report,
`FOLLOWUP_FIXES_REPORT.md`, `CONTROLS_AND_DEPLOY.md`. The web pad constants are unchanged, so the
browser edition stays wire-compatible; its gait already has per-player phase and ball-aware head yaw.

### Local verification

| Check | Result |
| --- | --- |
| `python3 Tools/test_pads.py` with `gdtoolkit` + `tree-sitter-c-sharp` | **130 passed, 0 failed** |
| `Tests/MatchCoreTests.cs` compiled and executed with Roslyn/WASM (`@live-codes/blazor-wasm`) | **42 passed, 0 failed** |
| 60 s / 11v11 / seed 2026 regression | possession, tackles, fouls and spacing thresholds all pass |
| New pure-C# assertions | short-vs-long pass distance, auto close control, camera dead zone / breakaway / fixed modes, held-focus override, distinct gait phases, ball-aware head yaw and eased head yaw |

GitHub Actions results for the pushed head are recorded in the PR checks; the sandbox still has no
native `dotnet`, `godot`, Windows build, physical EasySMX pad or new gameplay recording.

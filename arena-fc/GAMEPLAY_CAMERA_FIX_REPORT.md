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

_Update after CI_: see the final table below. Local portable checks currently pass
(`python3 Tools/test_pads.py`). Native `dotnet`/`godot`, a physical EasySMX pad,
a Windows rebuild and a new gameplay recording are **not** available in this
sandbox; those remain user-side validation.

| Check | Result |
| --- | --- |
| `python3 Tools/test_pads.py` | 120 passed, 0 failed |
| `dotnet build ArenaFC.sln -c Release` | pending CI |
| `dotnet run --project Tests/CoreTests.csproj -c Release` | pending CI |
| `dotnet run --project Tests/MatchCoreTests.csproj -c Release` | pending CI |
| `Tools/run-gd-tests.sh` (Godot headless) | pending CI |
| Node hub + Python netplay smoke tests | pending CI |
| Determinism / sim Linux + Windows | pending CI |
| Physical EasySMX / Windows build / new recording | user-side |

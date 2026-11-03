# Follow-up fixes: menu select, actions, fouls, spacing, cameras, knees

Date: 2026-11-03. Branch: `arena/66c1b3bb-c-games`. Follows PR #38.
The online architecture answer lives in `ONLINE_AND_ROADMAP.md`.

## 1. "Up/down works with the controller but I can't select it"

Two independent causes, both fixed:

* `PadMenuNavigator.Activate()` relied on `btn.EmitSignal(BaseButton.SignalName.Pressed)` from
  another node to invoke a C# `Pressed +=` subscription. `Ui.Btn()` now registers every click
  callback in `Ui.ButtonClicked` (and `Ui.CheckChanged` for checkboxes); the navigator calls that
  `Action` directly, with `EmitSignal` only as a fallback.
* `ReadMenuPad()` derived "select" from `PadLayout.Held()["pass"]`. A pad that Godot reports as
  *known* but which actually sends raw D-input button indices never produced `pass`, so A did
  nothing — while up/down (stick/d-pad, layout-independent) worked. Menus now accept **any face
  button (A/B/X/Y), Start or Back**; back/cancel is R3/L3.

## 2. "No button seems to tackle or pass / selecting a player isn't right"

* **Auto-select.** `Match.Tick()` now puts the controlled-player ring on the home ball carrier when
  attacking, and otherwise moves it to the nearest outfielder if that player is ≥1.6 m closer to the
  ball (hysteresis so it doesn't flicker). TAB switching gets a 1.2 s `ControlLock` so auto-select
  does not fight the user. Previously the ring stayed on a distant player and pass/tackle looked dead.
* **First-touch actions.** Pass / through / shoot now also work within 1.6 m of a *loose* ball, not
  only when `Ball.Owner == controlled`.
* **Documented button map** (CONTROLS screen, HUD hint, `CONTROLS_AND_DEPLOY.md`):

  | Action | Keyboard | Mapped pad | Raw EasySMX |
  | --- | --- | --- | --- |
  | Move | WASD / arrows | left stick / d-pad | left stick / d-pad |
  | Pass | `E` | A | b2 |
  | Shoot (hold) | `SPACE` | X | b3 |
  | Through ball | `Q` | Y | b0 |
  | Chip | `R` | — | — |
  | Standing tackle | `F` | B | b1 |
  | **Slide tackle** | `SHIFT+F` | sprint + B | RB + B |
  | **Shield / strength** | `X` (hold) | LB (hold) | Back b8 (hold) |
  | Switch | `TAB` | Start | LB b4 |
  | Camera | `C` | R3/L3 | L3 b10 |

* **New mechanics.** `PlayerCommand.Slide` and `.Shield`, `PlayerState.Shielding`,
  `AttemptSlide()` (3.2 m reach, 1.35 s cooldown, `slide` pose, higher foul chance) and a strength
  contest in `AttemptTackle()`: bulk + defending + being goal-side/in front of the carrier increase
  the chance, a shielding carrier reduces it. This is the "get between the player and the ball"
  mechanic. Shield costs stamina; standing tackle reach went 2.0 → 2.4 m.

## 3. "Opposition keeps giving away frees that don't look like fouls"

* Failed tackles only become fouls within 1.7 m (2.6 m for a slide) at **12% / 30%**, instead of
  every miss within 2 m at ~18%. Deterministic 60 s sim: **4 invisible free kicks → 1**.
* The fouled player now visibly stumbles (`foul` pose with chest/hip/leg/arm fall over 1.1 s), the
  slider has a low `slide` pose, and the HUD shows `FOUL · FREE KICK` / `FOUL · PENALTY!` toasts.

## 4. "Players still seem a bit bunched"

* Personal space 0.62 m → **1.05 m** with a stronger push; non-carriers are nudged out of the
  carrier's immediate space. Critically that nudge is **only while the ball is owned** — applying it
  to a loose ball stopped anybody reaching pickup range (found and fixed by the sim probe: the ball
  stayed loose for the whole 60 s).
* The two supporting pressers take opposite ±2.4 m wings instead of the same point.
* Average players within 4 m of the ball: **2.62 → 2.24** (−14%).

## 5. One more camera

`BroadcastCamera` now has **5** modes, cycling close-to-far after Player cam:
Broadcast (28 m) → Player cam (3.1 m) → **Shoulder** (new, 8.5 m high / 13 m behind, slightly
off-axis, fov 62) → Sideline (14 m / 24 m) → Tactical (62 m top-down, stable `-Z` up).
WASD remains camera-relative in all five.

## 6. "Knees don't bend, legs come out behind"

The sign convention was backwards. A leg bone points **down** `(0,-1,0)`; a positive X rotation sends
it to `-Z` (behind the player, whose forward is `+Z`). The old positive thigh angles kicked the legs
out backwards, and the knee curves were too small at walking speed to read as a bend.

`Scripts/Core/Gait.cs` is now a Godot-free gait curve shared by `RigAnimator.Pose` (and mirrored in
`BrowserBoot.animate_rig`): **negative thigh angles swing forward**, **positive knee angles fold the
shin back**, knees stay bent even when walking (`flex = .35 + .65·amp`), ankles counter-rotate, and
the stride keeps harmonic hip swing, torso twist/lean, head stabilisation and a two-bounce weight
shift. `Tests/MatchCoreTests.cs` asserts the sign convention numerically.

Sample values at sprint, left leg leading: `hipL = -0.660`, `hipR = +0.660`, `kneeL = 0.908`,
`kneeR = 0.172`, `footL = -0.357`; idle `kneeL = 0.359`.

## Verification

| Check | Result |
| --- | --- |
| `Tools/test_pads.py` (plain / with parsers) | 101 / **103 passed, 0 failed** |
| `gdparse` on all changed GDScript | OK |
| tree-sitter C# parse of `Scripts/**/*.cs` + `Tests/*.cs` | clean |
| `Tests/MatchCoreTests.cs` compiled with Roslyn (real engine) | **15 passed, 0 failed** |
| Deterministic 60 s / 11v11 / seed 2026 | tackles **30**, fouls **1**, near-2 m ticks **1527**, avg within 4 m **2.24**, goals **1** |
| CI `dotnet-core` (.NET 9 build + core tests + static checks) | see PR |
| CI `godot-gdscript`, `node-hub`, determinism / sim | see PR |

## Limits

* No native rebuild or new recording here; the animation and menu feel were validated by maths,
  static wiring, Roslyn-compiled core tests and CI compilation — not by watching the game move.
  Please `git pull` and record another clip.
* Pad menu select is now layout-independent but still not tested with a physical EasySMX pad.
* Slide/shield/auto-select are in the **desktop C#** match engine. The browser edition already has
  its own auto-switch; its action set and mesh remain separate (`Web/Controllers.gd`,
  `Tools/gen_rig.py`). Porting these is the natural next step if both editions should match.
* The `foul` / `slide` poses are in `RigAnimator` (C#); the browser edition has its own action poses.

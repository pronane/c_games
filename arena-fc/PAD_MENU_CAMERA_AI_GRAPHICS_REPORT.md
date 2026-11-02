# Pad menus, mid camera, pressing AI and the rig graphics

Date: 2026-11-02. Branch: `arena/48f3dee7-c-games`. Follows PR #37 (the possession fix).
All four points below come from the user's follow-up after watching a new recording.

## 1. Menus needed a mouse

**Root cause:** `Ui.Style()` ended with

```csharp
b.FocusMode = Control.FocusModeEnum.None;
```

Every Button in the desktop build was explicitly non-focusable. `ShowMenu()`'s `GrabFocus()` had
nothing to grab, and Godot sends `ui_up` / `ui_down` / `ui_accept` to the *focused* Control — so
arrow keys, Enter and a gamepad did nothing on the main menu, pause menu, settings, controls,
controller setup and character editor.

**Fix:**
* `Ui.Style()` → `FocusMode.All`, plus a visible accent `focus` stylebox. `Combo` / `Check` also
  focusable; `Ui.FocusFirst()` seeds focus on the first focusable control of each menu.
* New `Scripts/Godot/PadMenuNavigator.cs`, attached to the `Window` (survives `GameApp.Clear()`).
  It polls every connected pad with `InputHub.ReadMenuPad()` — which uses the same `PadLayout`
  tables as gameplay, so **unmapped EasySMX D-input pads work** — and:
  - d-pad / left stick up-down (and left-right) walks focus through all focusable Controls,
  - A / Start activates (`EmitSignal(Pressed)` on Button, toggles CheckBox, cycles OptionButton,
    nudges Slider),
  - B / R3 / L3 goes back to the `Back` / `Resume` button.
* `InputHub.EnsureMenuPadActions()` removes only the *joypad* events from Godot's default
  `ui_accept` / `ui_*` actions so a pad A press cannot activate a button twice; keyboard Enter /
  arrows / Space are untouched.
* `GameApp` toggles `PadMenuNavigator.Active` on every menu/match swap; `Hud.SetPaused()` enables it
  and focuses "Resume"; `CharacterEditor` seeds focus. `CONTROLS` screen documents the pad menu keys.

## 2. A camera between the near and high views

`BroadcastCamera` had 3 modes (Broadcast 28 m/46 m, Player cam 3 m/7 m, Tactical 62 m top-down).
Added a fourth, **Sideline** (14 m high, 24 m behind, fov 58) — a low, wide tracking shot that sits
between the on-pitch player cam and the high views. `Cycle()` now uses `ModeCount = 4`; `ModeName`
reports `Broadcast / Player cam / Sideline / Tactical`. Tactical stays mode 3 (stable `-Z` up vector
so it cannot spin). WASD remains camera-relative via `MatchView`.

## 3. Opposition did not try to win the ball back

In `Match.Decide()`, only two players per team chased, they aimed at the ball's *projected* position,
they had no pace advantage, and tackle attempts were rare (`aggression ≈ .17`, range 1.8 m, cooldown
1.1 s). A carrier could stroll away while nine opponents stood in formation.

**Fix:** three pressers when the opposition owns the ball; the nearest leads the carrier, the other two
cut the lane to goal; new `PlayerState.Pressing` gives +12% speed / +33% acceleration; aggression
`.30 + Difficulty*.08`, tackle range 2.0 m, cooldown 0.8 s.

Measured on the **real C# engine** (Roslyn compiled, deterministic 60 s / 11v11, seed 2026):

| Metric | Before | After |
| --- | --- | --- |
| Successful tackles | 7 | **16** |
| Ticks with a defender within 2 m of the carrier | 579 | **740** |
| Ticks with a defender within 3 m | 1448 | 1364 |
| Fouls | 4 | 7 |

`Tests/MatchCoreTests.cs` now asserts `nearTicks > 400` and `tackles >= 10` in addition to the
possession regression checks. Result: **6 passed / 0 failed**.

## 4. Wooden legs / invisible joints and toes

**Animation.** `RigAnimator.Pose` used `Max(0, -sin)` for the knees — a half-wave-rectified sine that
snaps the leg between two straight angles. Rewritten (and mirrored in `BrowserBoot.animate_rig`) with:
* harmonic hip swing (`sin + 0.10·sin2`),
* a continuously flexing knee (`0.10 + (0.5−0.5·cos(phase+0.55))·0.95`),
* ankle toe-off / dorsiflexion, `LFoot` / `RFoot` posed in both editions,
* counter-swinging arms with elbow flex that varies through the stride,
* hips/spine/chest/neck/head lean, counter-twist, roll and idle breathing,
* two-bounce-per-stride vertical bob plus lateral sway (weight transfer instead of gliding).

**Mesh.** Still 18 bones and 9 material slots, so the editor, JSON round-trip and exports are
unchanged, but `RigDefinition.Build()` now adds:
* rounded hip, **knee cap**, ankle, shoulder, elbow and wrist joint spheres,
* shorts hem and sock top kit bands (visible thigh / knee / shin segmentation),
* a **raised toe box**, dark sole and coloured boot stripe, plus a rounded pelvis and two kit stripes,
* 12-segment / 4-ring limbs instead of 10 / 3.

`RigFactory.MakeMaterial()` adds specular + rim (`MetallicSpecular`, `RimEnabled/Rim/RimTint`) so the
rounded joints catch light rather than merging into one flat tube.

Rig probe on the real generator: **18 bones, 4191 vertices, 5752 triangles, 8 surfaces, weight sums
1.0000..1.0000, all bone indices valid, all vertices finite, bounds −0.015..1.848 m** — every
assertion in `Tests/Program.cs`'s rig section still holds.

## Verification

| Check | Result |
| --- | --- |
| `Tools/test_pads.py` (with gdtoolkit + tree-sitter) | **98 passed, 0 failed** |
| `gdparse` on `BrowserBoot.gd`, `NetClient.gd`, `ProceduralRig3D.gd`, `test_input_camera.gd` | OK |
| tree-sitter C# parse of all `Scripts/**/*.cs` + `Tests/*.cs` | clean |
| `Tests/MatchCoreTests.cs` on the real engine (Roslyn, Node) | **6/6 PASS** |
| CI `dotnet-core` (build `ArenaFC.sln` on .NET 9 + core tests + static checks) | see PR |
| CI `godot-gdscript`, `node-hub`, determinism / sim workflows | see PR |

## Limits

* No .NET 9 SDK / Godot editor in this sandbox: the native game was not rebuilt and no new recording
  was produced. The animation was validated by reading the pose maths and by the rig generator probe,
  not by watching it move. A new clip after `git pull` is the real test of the feel.
* The **browser** edition's mesh still comes from `Tools/gen_rig.py` → `Data/rig_default.json` (a
  separate Python model). This round mirrors the *animation* improvements there; the new joint/foot
  geometry is in the C# desktop rig. If you want both meshes identical, the next step is to port the
  joint primitives into `gen_rig.py` and regenerate the JSON.
* Pad menu navigation was verified statically (focus modes, navigator wiring, `PadLayout` reuse) and
  by CI compilation, not with a physical EasySMX pad. Please confirm on hardware.

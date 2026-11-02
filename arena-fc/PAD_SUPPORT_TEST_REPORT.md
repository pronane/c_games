# USB / EasySMX pad support — implementation & test report

Branch: `arena/39ababe0-c-games` (PR #33, base `main`).

## What changed

| Area | Before | Now |
|---|---|---|
| SDL database | `Data/input/gamecontrollerdb.txt` shipped but **never loaded** | Loaded at boot via `Input.AddJoyMapping` / `add_joy_mapping`, filtered to the current OS; 6 EasySMX / generic-USB lines are also compiled in as a fallback. All export presets include `Data/input/*.txt`. |
| Device selection | Hard-coded device `0` | `Input.GetConnectedJoypads()` / `get_connected_joypads()` every frame; all pads drive P1 in 1P, pad 1/2 split in the browser's 2P mode. |
| Unmapped pads | Standard A/B/X/Y order (wrong for EasySMX D-input) | EasySMX D-input order `b0=Y b1=B b2=A b3=X b4=LB b5=RB b6=LT b7=RT b8=Back b9=Start b10=L3 b11=R3`; d-pad as hat buttons (one table chosen to avoid the 11-14 / 12-15 overlap), hat axes 6/7, triggers as buttons or axes. |
| Remapping | Browser only | **CONTROLLER SETUP** on desktop (C#) and browser; per-pad-name bindings in `user://pads.json`. |
| Browser netplay input | Hard-coded pad 0 + standard buttons | Goes through `Controllers.gd`'s pad rules like local play. |

New/changed code: `Scripts/Core/Input/PadLayout.cs` (pure C#, shared by CoreTests),
`Web/Controllers.gd` (pure + Godot-backed GDScript, including the keyboard schemes),
`Scripts/Godot/Controls.cs`, `Scripts/Godot/GameApp.cs`, `Web/BrowserBoot.gd`,
export presets, `CONTROLS_AND_DEPLOY.md`, `README.md`.

## Tests run in this sandbox (2026-11-02)

The sandbox has no Godot editor and no .NET 9 SDK (GitHub release asset hosts are
blocked here), so the full `Tools/build.py --check` could not be executed. Instead:

| Suite | Command | Result |
|---|---|---|
| Portable pad harness — executes the **shipped** `Web/Controllers.gd` pure block (translated to Python), cross-checks C#/GDScript constants, validates the real SDL DB, static-checks wiring, parses all changed GDScript (gdtoolkit) and C# (tree-sitter) | `python3 Tools/test_pads.py` | **78 passed, 0 failed** |
| `Scripts/Core/Input/PadLayout.cs` compiled with Roslyn on .NET Core 3.1 and the **shipped PadLayout test section** from `Tests/Program.cs` executed | local csc + `dotnet exec` | **40 passed, 0 failed** |
| `Scripts/Godot/Controls.cs` and the new `GameApp.cs` controller-setup methods type-checked against Godot API stubs | local csc | **compiled, no errors** |
| GDScript syntax | `gdparse Web/Controllers.gd Tests/gd/test_pads.gd Web/BrowserBoot.gd` | **OK** |
| `git diff --check` | — | **OK** |

No physical EasySMX pad is available in the sandbox; the raw-layout behaviour was
verified with simulated button/axis states.

## Continuous integration (GitHub Actions, PR #33)

`arena-fc-tests.yml` runs on every push / PR touching `arena-fc/**`:

| Job | Result |
|---|---|
| `godot-gdscript` — real Godot 4.7.2 (mono editor used as a GDScript runner) executing `Tools/run-gd-tests.sh`: `test_modules.gd`, `test_game.gd`, `test_rules.gd` and the new `test_pads.gd` | **pass (23 s)** |
| `node-hub` — `npm ci && npm test` plus the Arena FC WebSocket hub against the protocol suites | **pass (53 s)** |
| `Determinism + netplay tests` (`netplay`, `sim-linux`, `sim-windows`, `sim-compare`) | **pass** |
| GitGuardian security checks | **pass** |

CI exposed two Godot-4.7-only compile issues that the local gdtoolkit parser could
not see, both fixed on this branch:

* `extends "res://Web/PadSupport.gd"` failed to resolve ("Could not resolve class"),
  which made `BrowserBoot.gd` fail to compile. The pure + engine-backed pad logic is
  now in the single `Web/Controllers.gd` script (the repo's existing convention);
  `Web/PadSupport.gd` was removed.
* `var x := min(...)` cannot be inferred because `min()` returns a Variant. Locals
  in the pad code are now untyped, which is equivalent here.

`Tools/run-gd-tests.sh` now wraps each SceneTree test in a `timeout` (180 s, override
with `ARENA_FC_TEST_TIMEOUT`) and emits check-run annotations from the failing test's
output, so a script error before `quit()` fails the job quickly instead of hanging it.
`Tests/gd/test_pads.gd` also has a 90 s watchdog.  Two earlier CI runs hung for ~30 min
before this was added; they are unrelated to the final state.

## Run the engine suites on your machine

```bash
cd arena-fc
python3 Tools/test_pads.py                 # no Godot/.NET needed
GODOT=/path/to/godot Tools/run-gd-tests.sh # includes Tests/gd/test_pads.gd
python3 Tools/build.py --check             # .NET 9 core tests + GDScript + in-engine self test + network
```

## Manual check with the real controller

1. Plug in the EasySMX pad (USB / 2.4G dongle) and press a button once.
2. Start Arena FC → **CONTROLLER SETUP**. It should list the pad, its detected
   kind (`EasySMX (XInput)` or `EasySMX (USB / D-input)`) and the SDL mapping count.
3. Move the left stick / d-pad; try pass, shoot, tackle, switch, sprint and Start.
4. If any button is in the wrong place, use **REMAP PAD 1** and press each button
   when asked. Bindings are restored on the next launch.
5. Switch the pad between XInput and D-input/PC mode and repeat — both layouts
   should work without reconfiguring.

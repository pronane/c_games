# USB / EasySMX pad support — implementation & test report

Branch: `arena/39ababe0-c-games` (commit `78c8dd1`).

## What changed

| Area | Before | Now |
|---|---|---|
| SDL database | `Data/input/gamecontrollerdb.txt` shipped but **never loaded** | Loaded at boot via `Input.AddJoyMapping` / `add_joy_mapping`, filtered to the current OS; 6 EasySMX / generic-USB lines are also compiled in as a fallback. All export presets include `Data/input/*.txt`. |
| Device selection | Hard-coded device `0` | `Input.GetConnectedJoypads()` / `get_connected_joypads()` every frame; all pads drive P1 in 1P, pad 1/2 split in the browser's 2P mode. |
| Unmapped pads | Standard A/B/X/Y order (wrong for EasySMX D-input) | EasySMX D-input order `b0=Y b1=B b2=A b3=X b4=LB b5=RB b6=LT b7=RT b8=Back b9=Start b10=L3 b11=R3`; d-pad as hat buttons (one table chosen to avoid the 11-14 / 12-15 overlap), hat axes 6/7, triggers as buttons or axes. |
| Remapping | Browser only | **CONTROLLER SETUP** on desktop (C#) and browser; per-pad-name bindings in `user://pads.json`. |
| Browser netplay input | Hard-coded pad 0 + standard buttons | Goes through `PadSupport` like local play. |

New/changed code: `Scripts/Core/Input/PadLayout.cs` (pure C#, shared by CoreTests),
`Web/PadSupport.gd` (pure + Godot-backed GDScript), `Web/Controllers.gd` (thin wrapper),
`Scripts/Godot/Controls.cs`, `Scripts/Godot/GameApp.cs`, `Web/BrowserBoot.gd`,
export presets, `CONTROLS_AND_DEPLOY.md`, `README.md`.

## Tests run in this sandbox (2026-11-02)

The sandbox has no Godot editor and no .NET 9 SDK (GitHub release asset hosts are
blocked here), so the full `Tools/build.py --check` could not be executed. Instead:

| Suite | Command | Result |
|---|---|---|
| Portable pad harness — executes the **shipped** `Web/PadSupport.gd` pure block (translated to Python), cross-checks C#/GDScript constants, validates the real SDL DB, static-checks wiring, parses all changed GDScript (gdtoolkit) and C# (tree-sitter) | `python3 Tools/test_pads.py` | **78 passed, 0 failed** |
| `Scripts/Core/Input/PadLayout.cs` compiled with Roslyn on .NET Core 3.1 and the **shipped PadLayout test section** from `Tests/Program.cs` executed | local csc + `dotnet exec` | **40 passed, 0 failed** |
| `Scripts/Godot/Controls.cs` and the new `GameApp.cs` controller-setup methods type-checked against Godot API stubs | local csc | **compiled, no errors** |
| GDScript syntax | `gdparse Web/PadSupport.gd Web/Controllers.gd Tests/gd/test_pads.gd Web/BrowserBoot.gd` | **OK** |
| `git diff --check` | — | **OK** |

No physical EasySMX pad is available in the sandbox; the raw-layout behaviour was
verified with simulated button/axis states.

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

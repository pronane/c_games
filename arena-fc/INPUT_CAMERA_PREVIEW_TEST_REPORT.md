# Preview input, camera and gameplay — diagnosis and test rerun

Date: 2026-11-02. Branch: `arena/6aad79d7-c-games`. Landed on `main` via PR **#36**
(merge `54f43a7`). Live preview: `python3 Tools/serve_wasm_preview.py --port 8080`.

## Why the main screen could not be controlled

1. **Keyboard focus.** Godot's Web build registers `keydown`/`keyup` on the `<canvas>` element, not on
   `window` (verified in the 4.7.2 Web glue). The old preview page rendered a canvas with no `tabindex`
   and never focused it, so every WASD / `C` / `1`-`4` / `+` / `-` key was discarded by the browser.
   It looked exactly like "controls and camera angles don't work". The generated page now uses
   `<canvas tabindex="0">`, `focusCanvas: true`, and refocuses on pointer-down / stray keydown.
2. **Pad menu.** `Web/BrowserBoot.gd` had no gamepad menu navigation: a pad could only leave the menu.
   The first menu Button now takes GUI focus on boot (arrow keys + Enter/Space), while a pad's d-pad or
   left stick moves the highlight and A / Start selects.
3. **Pad camera.** `Web/Controllers.gd` has always reported a `camera` system button (R3 on mapped pads,
   L3 on raw EasySMX pads), but `BrowserBoot.gd` ignored it. It now cycles broadcast / telephoto /
   player / tactical views, alongside `C` and `1`-`4`. The HUD `CAM` button, wheel and `+`/`-` zoom are
   unchanged.
4. **Rigs were missing in the preview — the real gameplay problem.** The Godot 4.7.2 Web template from
   npm is built without the WebSocket and glTF modules. Compile-time `WebSocketPeer` and
   `GLTFDocument`/`GLTFState` references made `Web/NetClient.gd`, `Scripts/Godot/ProceduralRig3D.gd` and
   therefore everything that preloads them fail to parse. `RigBuilder.load_rig_data()` returned null, so
   the match spawned 10 "players" with no skeleton or mesh. Both scripts now resolve those optional
   classes through `ClassDB` (`class_exists` / `instantiate` / `class_get_integer_constant`) and use
   untyped locals for dynamic calls. Rigs load from `Data/rig_default.json` again; only online play and
   GLB import degrade to a warning.

## What changed

| File | Change |
| --- | --- |
| `Web/BrowserBoot.gd` | Menu focus/pad navigation, pad `camera` action, HUD hint, `build_touch(force := false)` |
| `Web/NetClient.gd` | `ClassDB` lookup for `WebSocketPeer`; optional-module guard in `_open()` |
| `Scripts/Godot/ProceduralRig3D.gd` | `ClassDB` lookup for `GLTFDocument`/`GLTFState` in `load_glb()` |
| `Tools/serve_wasm_preview.py` | New reproducible preview generator (focusable canvas, COOP/COEP, npm WASM runtime) |
| `Tests/gd/test_input_camera.gd` | New 19-check headless input/camera suite |
| `Tools/run-gd-tests.sh`, `Tools/test_pads.py` | Wire the new suite; +6 static checks |
| `CONTROLS_AND_DEPLOY.md` | Controls, focus requirement, WASM module limits |

## Test rerun (all green)

| Suite | Result |
| --- | --- |
| `python3 Tools/test_pads.py` | **85 passed, 0 failed** |
| Godot 4.7.2 WASM engine, headless — `test_input_camera.gd` | **19 PASS / 0 FAIL** |
| … `test_pads.gd` | **41 / 0** |
| … `test_rules.gd` | **33 / 0** |
| … `test_modules.gd` | **32 / 0** (was 31 PASS / 1 FAIL) |
| … `test_game.gd` | **23 / 0** (was 21 PASS / 2 FAIL) |
| Game boot, 120 simulated frames | `ARENA_FC_WEB_READY`, no script errors |
| Generated preview boot simulated end-to-end | 33 files staged, starts, READY, no script errors |
| `gdparse`, `py_compile`, `node --check`, `git diff --check` | OK (`gdlint` reports the same 36 pre-existing style warnings in `NetClient.gd` as on `main`) |
| Preview HTTP sanity (index, boot.mjs, godot.wasm, manifest, staged scripts) | 200 |
| PR #36 CI (Arena FC tests, determinism/netplay, deploy) | all passed |
| Post-merge CI on `main` at `54f43a7` (3 workflows) | all passed |

Reproduce locally:

```sh
cd arena-fc
python3 Tools/test_pads.py
bash Tools/run-gd-tests.sh            # needs the Godot 4.7.2 editor binary
python3 Tools/serve_wasm_preview.py --port 8080
```

## Limits / not verified here

* No Chromium/Playwright in the sandbox: the preview was verified by HTTP, a DOM/fetch boot simulation
  and the real Godot WASM engine headlessly — **not** by visual browser automation. General gameplay
  "feel" still needs a human look at the live preview; click the canvas once if another iframe took focus.
* Online play and GLB import/export need the native/editor build; Godot cannot export the C# desktop
  game to Web, so this preview is the GDScript browser edition only.
* Windows `D:\c_games` still needs `git pull` to `54f43a7`, a native .NET 9 rebuild,
  `Tools/build.py --check` / `--run`, and a physical EasySMX pad test. Those were not run here.

# Turbo Tumble 64 — progress

## v3 polish pass + final zip (Oct 17, ~00:40)

Final zip: `/workspace/kartgame/TurboTumble64.zip`

### Handling / game feel (GP + Time Trial)
- Snappier steering (faster stick response, more turn rate, more grip outside drifts).
- Drift reworked: steering against the drift widens it and steering into it tightens it; charge builds faster, and wiggling adds a bonus.
- Sparks behind the rear wheels: white, then **blue**, then **orange**. They're additive glowing streaks with a core glow.
- Mini-turbo: blue = TURBO!, orange = SUPER TURBO! (longer and stronger, with exhaust flames, an FOV punch and camera shake). The HUD has a charge bar.
- CPU racers drift and fire mini-turbos too: about 15-85 blue per race, plus a few orange.
- Item roulette: a slot-machine reel in the HUD item box that eases out, with a rainbow frame, a landing pop and a flash.
- Time Trial ghost: the best lap is recorded at 20 Hz and saved to `ghost_trackN.dat`. It replays as a translucent glowing blue kart, and the HUD shows the GHOST time.
- GP: standings after every race show the points gained (+N) and each racer's last-race place.
- After race 6: final standings, then the **trophy ceremony** (podium, top-3 karts, rotating gold/silver/bronze cup, confetti).

### Visuals
- All karts and characters were rebuilt from rounded primitives: bevelled round-box tubs, side pods, spoked wheels with rounded tyres, capsule arms, gloves, rounded heads with eyes (whites, pupils, glints), blinking, smiles and cheeks.
- Models are baked into cached meshes per mode, so each kart is about 8 draw calls.
- ORIGINAL: still about 320x240 with a point upscale, but the characters are rounder.
- ENHANCED: native res, 4x MSAA, about 2-3x the mesh density, high-detail trees (clumped spheres, 12-sided pines), a smoother and brighter sky dome with horizon haze, a sun glow and a bloom-ish top gradient, half the fog density, soft elliptical blob shadows, and 15% bigger particles.
- Ghoulwood Manor is brightened: a lighter purple sky, a lighter road and walls, and less fog.
- Fixed: translucent objects in ORIGINAL no longer punch dark alpha holes when the low-res view is upscaled.

### Test results (all full runs: 6 GP races, cup ceremony, TT ghost, 6 checkpoint tests, VS)
| Run | Result | Avg fps (software GL, 4x sim speed) |
|---|---|---|
| Linux ORIGINAL (`v3_`) | PASS, 0 failures | 64 |
| Linux ENHANCED (`v3e_`) | PASS, 0 failures | 48 |
| Wine, shipped `prebuilt/TurboTumble64.exe` (`wine3_`) | PASS, 0 failures | 59 |

Logs: `screenshots/v3_autotest_log.txt`, `v3e_autotest_log.txt`, `wine3_autotest_log.txt`.

Caveats:
- Not run on real Windows or MSYS2: the bat was only checked for logic and CRLF.
- No physical gamepad was tested.
- fps numbers come from a CPU software renderer with three runs in parallel. A real GPU will be far faster, but the new models are heavier than v2.

### Screenshots (screenshots/)
- v3e_race2_drift_orange.png: SUPER TURBO! flames and sparks.
- v3e_race1_2_racing.png: ENHANCED racing.
- v3e_cup_trophy_ceremony.png: the trophy ceremony.
- v3e_tt_ghost.png: the Time Trial ghost.
- v3_race1_item_roulette.png: item roulette (ORIGINAL).
- v3_race5_2_racing.png: Ghoulwood, brightened.
- v3_race6_5_final_standings.png: final cup standings.
- *_drift_blue.png: blue sparks.
- *_bumps_airborne.png, *_shortcut.png.

---

## Interim build delivered (Oct 16, 23:40)
- **Zip:** `/workspace/kartgame/interim.zip` (also `TurboTumble64.zip`, identical for now, 3.9 MB)
- Unzip, then double-click `TurboTumble64\build_release.bat`. It finds MSYS2, installs gcc/raylib if missing, builds and launches. If the build fails, it falls back to `prebuilt\TurboTumble64.exe`.

## What's in it
- 6 tracks: Sunny Meadow, Coconut Cove (beach), Dusty Dunes (bumpy desert), Frosty Peak (bumpy snow), Ghoulwood Manor (spooky, bumpy), Starlight Spire (long rainbow night course). Each has a secret shortcut (hint shown on track select).
- 9 racers: 8 built in, plus **Mango Mo**, made from a photo with `tools/make_character.py` (data-driven from `assets/characters/`).
- Controls (N64 style): A = accelerate, B = brake/reverse, R = hop/drift, Z/LT/LB = item, Start = pause. Keyboard still works. Options shows the pad name, and there is a remap screen. gamecontrollerdb with EasySMX entries; raw-joystick fallback.
- Visual modes: ORIGINAL (320x240 point-upscaled, default) and ENHANCED (native res, 4x MSAA, aniso, longer draw distance). Toggle in Options or with F2.
- GP (6 races), Time Trial, VS split-screen (unchanged).

## Test results
- Linux xvfb full autotest (ORIGINAL): **PASS**, 0 failures, 99 fps avg. All 6 races, shortcuts taken, bump lift-offs and checkpoint tests (reverse / shortcut / backwards) pass.
- Linux xvfb full autotest (ENHANCED): **PASS**, 0 failures, 72 fps avg (xvfb software GL, 4x sim steps).
- Wine full autotest of the Windows exe: **PASS**, 0 failures, 95 fps avg.
- Wine race 2 with Mango Mo (sprite character) on the final exe: **PASS**.
- Zip extract check: all 12 sources listed in the bat are present and compile.
- NOT verified: a real Windows 10 machine, the real MSYS2 bat run, a physical EasySMX pad.

## Screenshots
`/workspace/kartgame/screenshots/` — `v2_*` (Linux), `wine_*` (Wine), `*_shortcut.png`, `*_bumps_airborne.png`, `v2e_*` (ENHANCED).

## Next
Single-player GP/TT feel polish, control polish, brighten Ghoulwood a little.

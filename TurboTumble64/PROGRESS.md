# Turbo Tumble 64 — progress

## v8: HD photo sprites for Éabha + Qanna, add_racer tool (Oct 25)

### Éabha and Qanna as HD photo sprites
- Built only from their own photo/video pixels: cut-outs, mirroring, darkening, warps and drawn
  marks. No generative model was used on the real people.
- Each is an 8-angle sheet (2 rows of 4 cells, 512x640) in the 3D kart. The kart, decals, fruit,
  rattle, duck, bib and towel are unchanged.
  - Qanna: real front, 3/4 and back frames from her video. The side views are warped from the
    nearest real frames.
  - Éabha: front from her photo. The 3/4 and side views are warped from it. The back is
    invented: a mirrored silhouette, hair colour sampled from her head, jumper colour from her top
    and a bib collar band.
- The game cross-fades between neighbouring angles. Éabha's win mood bounces, and Qanna sways
  and leans as if dozing.
- Win sprites are simple edits of the front photo:
  - Éabha: tilt, smile line, blush and sparkles, with "Car!".
  - Qanna: tilt, heavy lids, frown and anger vein, with "I didn't sleep last night".
- The 3D towel knot is hidden for photo sprites because the photo already shows the towel.

### Generic tool: `tools/add_racer.py` + `add_racer.bat`
- Photo mode: an automatic face finder and a GrabCut-style colour-model cut-out (numpy/scipy,
  offline). Optional hints: `--box`, `--fg-box`, `--bg-box` (repeatable), `--face`, `--mask` or a
  hints .ini.
- It builds 8 angles plus a portrait, win sprite, decal (`--kart-text`) and `character.ini`.
  Extra real views can be added with `--side`, `--back` and `--view`.
- Spec mode (`--spec file.txt`): a procedural cartoon racer from a text description (ethnicity,
  complexion, hair, eyes, nose, ears, mouth, size, weight, hands, feet, clothes...). Example:
  Ruby Rocket.
- Output uses the Sprite Forge sheet layout (`frame_w`, `frame_h`, `ground_y`). The game finds
  new racers at startup.
- `add_racer.bat` (CRLF) supports drag-and-drop and installs Python, Pillow, numpy and scipy via
  MSYS2 pacman. See `HOW_TO_ADD_A_RACER.txt`.
- I tested it on a public-domain NASA astronaut portrait (Michael A. Baker). It needed a few
  `--bg-box` hints because the background is close to the suit colour. This test racer is NOT
  shipped; it is kept in `work/v8/`.

### Other
- The character-select grid adapts its columns (4 to 6) and the preview panel no longer overlaps
  the grid.
- `--gallery` now also shoots photo racers (8 views each).

### Tests (all on the final build)
| Run | Result | Loop fps |
|---|---|---|
| Linux `--autotest --enhanced` (`v8e_`, final assets) | PASS, 0 failures | 38 |
| Linux `--autotest --enhanced` with the extra test racer (13 racers) | PASS, 0 failures | 39 |
| Wine, `prebuilt/TurboTumble64.exe` (`wine8_`) | PASS, 0 failures | 45 |

Forced-win quips ("Car!" and "I didn't sleep last night") PASS on both platforms. Screenshots and
logs are in `screenshots/v8/` (that folder is not in the zip).

### Release
`/workspace/kartgame/TurboTumble64_v8.zip` (13.1 MB, 262 files). It has no raw photos or video, no test
racer and no cut-out sources. The .bat and .txt files are CRLF. A fresh unzip compiles on Linux
and MinGW, and `add_racer.py --spec` runs from it.

### Honest limits
- Side and 3/4 views are warped front photos, so the face stays frontal.
- Mirrored views mirror text: "Mumma's" on Éabha's top, and generated decals viewed from the front.
- Éabha's invented back is plain.
- The top of Qanna's towel in her side frames is washed out (video exposure).
- The rear wing hides most of the driver's back in the chase camera.

## v7: Mudslide Megadome, 3D Éabha + Qanna, EasySMX pads (Oct 22)

### New track 7: Mudslide Megadome
A night indoor dirt supercross stadium. The layout and all names, faces and logos are original.
- Very wide course sunk in a trench with sloped dirt banks. The dirt is ribbed with dark lines,
  and the moguls bounce karts into the air.
- Light-blue retaining walls painted with our dark-blue mascot face.
- Red/white striped barriers on the raised deck and ramps.
- Pitch-black sky with light towers; stands with a crowd and camera flashes.
- A neon "BIG AIR" sign with a yellow arrow before the jump.
- A blue jumbotron with a live chase cam of the leader (a render texture), switching to a
  trackside TV angle every 7 s.
- A start truss with a black **TURBO TUMBLE 64** banner and chequered flags.
- Rows of item boxes, and its own music.
- Secret shortcut: a dark gap in the dirt bank at the top of the big U-turn.
- Overpass: the course climbs onto a raised deck and jumps north over the lower east straight.
  The deck has its own height samples, and the checkpoints follow the deck, so the crossing
  can't be used to skip a lap. CPUs drive it, take the shortcut and finish laps.
- Routing is my own consistent layout, not a copy: the hairpin turns right, and the jump goes
  north over the lower east straight.
- It is in the Grand Prix (now 7 races, and it is the last one) and in Time Trial.
- `--stadium` runs an 8-shot camera tour.

### Éabha and Qanna are now 3D low-poly models built in code
- Both are real meshes (no billboards), baked like the built-in racers, so they look right from
  every angle.
- Win-pose variants are baked too:
  - Éabha throws her arms up, with happy-arc eyes and an open mouth;
  - Qanna folds her arms, with a frown, half-lidded eyes and a sleepy head-nod.
- Win cards and select-screen portraits are rendered from these models.
- **Éabha:** pink top, a cream bib with sprinkles, chubby cheeks and a hair curl. Her kart has a
  rattle and toy fruit, and the back wing reads **"Milkies"** in rounded Fredoka letters
  (`tools/make_decal.py "Milkies" --style bubbly`). Win line: **"Car!"**.
- **Qanna:**
  - teal turban #1A5E63 with the knot at the top centre of the forehead;
  - a 4-panel cape to mid-back with a straight hem. It wraps the shoulders, sways and lifts with
    speed and steering;
  - a little dark-brown hair;
  - oval face #DDBDA5, thick dark brows, a deadpan downward gaze;
  - oversized oatmeal ribbed jumper #BCAE9F with drop shoulders and sleeves bunched at the
    wrists;
  - a silver necklace with a pendant;
  - black leggings #151515 and slouched white socks.
  "I'M ANNOYING" blinks in bold comic letters on the kart. Win line: **"I didn't sleep last
  night"** (sleepy/angry, with Zzz).
- **Privacy:** only processed assets go in the game, never the raw photos. The v5/v6 photo-derived
  sprite/portrait/preview/win PNGs were removed from `assets/characters/` (moved outside the
  package to `/workspace/kartgame/removed_v6_photo_assets/`). Their `character.ini` now uses
  `model3d = eabha|qanna`. The only image files left are the generated text decals; Mango Mo is
  an illustration.

### Controllers
- New `assets/gamecontrollerdb_easysmx.txt` (from `tools/make_padmaps.py`) is loaded after the
  main SDL DB. It has 39 entries for EasySMX ESM-9101 / ESM-9013 / ESM-9110:
  - X-input receivers `2f24:0091/00b7/0048`;
  - D-input `20bc:9100`, `11c1:9101`, `20bc:9013/9110`;
  - Android mode `0079:181c`, `2563:0526/0527`;
  - Linux version variants, and Windows entries.
  Entries already in the community DB are kept as they are, not overridden.
- Unknown pads use the raw-joystick fallback (winmm / js*) with the generic DInput layout. Remap
  works for both standard and raw layouts.
- `--padcheck` self-test: both DB files accepted, the remap rules, the config round trip, and the
  raw fallback binds.

### v7 finishing log (Oct 22, evening)
- [x] Clover Creek Farm CPU drift fix compiled (kart.c: wider-bend drift threshold on terrain-following tracks).
  Race 11 rerun: PASS (CPUs fired 15 blue mini-turbos). Race 8 rerun: PASS.
- [x] Real faces: `tools/make_face.py` cuts an elliptical HD crop (colour pop + unsharp, soft edge) from the
  photo into `face.png` + `face_win.png` (Éabha: warmer/rosier; Qanna: heavy lids, scowl brows, tired
  bags, grumpy flush). Shown on the 3D head as a curved patch that hugs the head ellipsoids; drawn
  eyes/nose/mouth are skipped and the head skin is matched to the photo. Towel, cape, hair, bib,
  toy fruit and kart lettering unchanged. Raw photos are not in the game folder.
- [x] Shortcut counting fix (kart.c): a shortcut now counts once the kart is past the middle of the corridor
  (was: past 2/3). Shellby Shores' wide-shoulder exit rejoins the road at index 58/87, exactly on the old
  threshold, so race 10 and the Shellby checkpoint test failed intermittently ("player autopilot did not
  complete the shortcut", "shortcut registered=no"). Race 10 rerun x2 after fix: PASS (normal + ENHANCED).
- [x] `prebuilt\TurboTumble64.exe` run in place now finds `..\assets` automatically (main.c).
- [x] Screenshots collected in `screenshots/v7/` (real-face gallery rendered 22:49 from the final face code;
  tours of tracks 8-11 + stadium; forced-win result/podium cards).
- [x] Windows exe rebuilt (23:17) with all of the above and copied to `prebuilt/`.
- [x] Real-face gallery re-shot at ~23:42 with the final build (`screenshots/v7/char_*`, `wincard_*`).
- [x] Full Linux ENHANCED autotest + Wine autotest: both PASS 28/28 (table below).
- [x] Packaged `TurboTumble64_v7.zip` (5.3 MB, 241 files). No screenshots, raw photos, binaries or cfg.
  Fresh unzip compiles on Linux and with MinGW. bat lists all 15 .c files. prebuilt exe matches.

### Tests (Xvfb + llvmpipe software GL; Wine for the Windows exe)
v7 final runs (Oct 22, ~23:20-23:40), both on the final code (shortcut fix included), `--speed 6`:

| Track | Linux ENHANCED (`v7e_`) | loop fps | Wine, shipped exe (`wine7_`) | loop fps |
|---|---|---|---|---|
| 1 Sunny Meadow Circuit | PASS | 28 | PASS | 40 |
| 2 Coconut Cove | PASS | 32 | PASS | 44 |
| 3 Dusty Dunes Rally | PASS | 32 | PASS | 45 |
| 4 Frosty Peak Pass | PASS | 30 | PASS | 40 |
| 5 Ghoulwood Manor | PASS | 11* | PASS | 43 |
| 6 Starlight Spire | PASS | 39 | PASS | 57 |
| 7 Mudslide Megadome | PASS | 28 | PASS | 32 |
| 8 Grand Tumble Raceway (v7) | PASS | 28 | PASS | 37 |
| 9 Canopy River Parkway (v7) | PASS | 25 | PASS | 31 |
| 10 Shellby Shores (v7) | PASS | 33 | PASS | 40 |
| 11 Clover Creek Farm (v7) | PASS | 33 | PASS | 35 |
| Cup ceremony, time-trial ghost, 11 lap checkpoints, VS split-screen, 4 forced-win quips | all PASS | | all PASS | |
| **Summary** | **PASS, 28/28 checks, 0 failures** | avg 29 | **PASS, 28/28, 0 failures** | avg 40 |

\* Race 5 ran while the Wine run was using the same CPU; it ran at 38 fps in the earlier full run. fps is the
render-loop rate with 6 sim steps per frame on software GL (llvmpipe) under Xvfb. A real GPU will be much faster.
Uncapped single-step PERF on the new tracks: 25-34 fps (Linux), 34-38 fps (Wine).
Earlier run (before the shortcut fix): Linux full 27/28 (Shellby checkpoint FAIL), Wine 27/28 (race 10 FAIL), which led to the fix.
Logs: `screenshots/v7/v7e_autotest_log.txt`, `screenshots/v7/wine7_autotest_log.txt`.
Not tested: a real Windows 10 PC, the real MSYS2 `build_release.bat` run, a physical EasySMX pad
(only the `--padcheck` self-test and the Wine run).

## v5: family photo racers (Oct 17)
- **Baby Éabha** (light: speed 2.5, accel 5, handling 4.5, mass 1.0, voice pitch 1.75) and
  **Towelhead Qanna** (medium: 3.5 / 3.0 / 4.0, mass 3.0, voice pitch 1.15).
- Pipeline (`tools/make_character.py`):
  - neural cut-out (rembg isnet), a head + upper-body crop, and largest-blob cleanup;
  - a 512 px HD sprite with a dark outline;
  - a procedural back view (hair or towel texture with the photo's shading);
  - a 16-angle sheet in 2 rows, plus a portrait.
- Game:
  - multi-row sprite sheets; driver bob, lean, slide, air stretch and landing squash;
  - themed karts: rattle + toy fruit, spa towels + cucumbers + rubber duck, and a flapping
    towel tail;
  - portraits for every racer in the select grid, and names shrink to fit;
  - UTF-8-safe name padding in the standings.
- Autotest:
  - player = Éabha in race 2, Qanna in race 4, Mango Mo in race 6;
  - photo racers fill the CPU grid first in the other races;
  - new `raceN_closeup.png` front-camera shot, and `02b_character_select.png`.
- Privacy: only processed sprites are in `assets/characters/`; the photos are not in the game
  folder or the zip.

## v4 visual-richness overhaul (Oct 17)
Gameplay and handling are unchanged. Visual changes only:
- New `src/textures.c`: all textures are generated in code (asphalt, curbs, barriers, wood,
  stone, rock, bark, leaves, roofs, crowd, signs, water, rainbow tiles, item box, clouds, per-track
  ground) plus a per-track 2048x256 painted panorama.
- New `src/scenery.c`: about 40 prop types per theme, baked into culled spatial chunks.
- Terrain: a 112x112 smooth-normal height grid with hills away from the track, lakes, and a sea.
  Rounded barrier tops and raised curbs.
- Shader: scrolling water UVs, rainbow hue cycling, a saturation lift, and much lighter fog.
  Palettes are bluer and more saturated.
- Racers: ORIGINAL draws pre-rendered sprite racers (24 angles x 3 poses, outlined) made from the
  HD models at startup. ENHANCED draws full 3D models with stronger rim light.
- ORIGINAL renders at 640x480 with a bilinear upscale. The new ORIGINAL RETRO option (Options)
  restores 320x240 point filtering.
- Item boxes: translucent rainbow cubes with a "?" panel on every face.
- ENHANCED is now the default on first launch. The choice is saved in turbotumble64.cfg next to
  the exe, and the title hint reads "F2: ENHANCED / ORIGINAL N64 look".
- Tests: full autotests PASS with 0 failures in Linux ORIGINAL (v4_), Linux ENHANCED (v4e_), and
  Wine on the Windows exe (wine4_).

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

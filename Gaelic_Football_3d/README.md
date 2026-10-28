# Sunday League: Gaelic Football (C + raylib), v3.2

3D Gaelic football on a full-size pitch (140 x 85 m) with two 15-a-side teams, a referee
and four umpires. The game runs on **your original rules engine** (`src/game.c` / `src/game.h`,
brought over from `legacy/` and extended), with a raylib 3D frontend in `src/main.c`.

## Build & run on Windows (MSYS2 UCRT64)
1. In an **MSYS2 UCRT64** shell, once:
   `pacman -S --needed mingw-w64-ucrt-x86_64-gcc mingw-w64-ucrt-x86_64-raylib mingw-w64-ucrt-x86_64-glfw`
2. Double-click `build_release.bat`. It builds `gaelic_football.exe` from `src\main.c src\game.c`,
   linking `-lraylib -lglfw3 -lopengl32 -lgdi32 -lwinmm -static-libgcc`. It then copies `glfw3.dll`,
   `libwinpthread-1.dll` and `libraylib.dll` from `%RAYLIB_DIR%\bin` and starts the game.
   Set `MSYS2_ROOT` or `RAYLIB_DIR` if MSYS2 is installed somewhere else.
   You can also build in the UCRT64 shell with `make && ./gaelic_football.exe`.
3. `make test` builds and runs the rules-engine unit tests (`tests/core_tests.c`).

Works with raylib 5.5 and 6.x. Run the game from this folder, because `assets/` is loaded
relative to the exe.

## Start-up
The game opens with a **20-second AI-vs-AI attract demo**. It uses broadcast cameras (aerial
bowl sweep, main camera, Hill 16 end, tracking, crane), a title overlay and crowd sound.
Press **Enter**, or **Start / A** on the pad, to skip it. The title menu offers **Play match**,
**Training**, **Controller test**, **Graphics: Low/Medium/High** and **Quit**. Esc in a match
goes back to the menu.

Launch options:
- `--no-intro`
- `--demo` (the CPU plays your team)
- `--training` (start straight in training)
- `--quality 0|1|2`
- `--cpu-skin`
- `--bench [frames]` (AI v AI, uncapped; prints average fps and a ms breakdown)
- `--screenshots` / `--shots31` / `--shots32` (scripted test scenes that write `v3_*.png` / `v31_*.png` / `v32_*.png`; the shots31/32 scripts drive a simulated pad)
- `--record-intro FILE` (raw 30 fps RGBA frames plus `FILE.wav`, for ffmpeg)

## Who am I?
- The player you control stands in a **yellow ring** with a facing tick, and a yellow arrow
  bobs above his head.
- His number, name and position are at the top of the HUD.
- In possession, a **cyan ring** marks the team-mate a hand pass (A / E) will go to, and the
  HUD names him. While you charge a kick (X), an **orange ring** marks the kick-pass target.
- When your player is off screen, an arrow with his number points to him from the screen edge.

## v3.2 gameplay changes
- **Auto-switching (FIFA-style):**
  - You take over your carrier instantly.
  - When the opposition has the ball, you get the best *goal-side* defender.
  - On a loose or high ball, you get the player who will reach it first.
  - After your pass, you get the receiver.
  - On restarts, you get the taker.
  - A shrinking ring flashes on each new player.
- **L1 / Tab / Q** switches to the player nearest the play. Tap again within 1.2 s to walk
  through the next-nearest players. A manual pick is kept for 2 s.
- **Pass assist:**
  - The left stick chooses the receiver (the cyan ring for a hand pass, the orange ring for a kick pass).
  - Passes are led into his run.
  - The kick power is fitted to the distance automatically, with your charge adding 15%.
  - Shots at the posts are not affected. When the posts are closer and better lined up, the kick goes to them.
- **Magnetism:**
  - With your stick idle, or pointed roughly at it, your player bends toward a loose ball within 7 m and picks it up.
  - With the stick idle while the ball is in the air, he runs to the drop and jumps to catch it.
- **Movement:** acceleration, turning that is slower at full speed, a plant-and-turn on
  reversals, and a sprint that builds up. It is smoother than the old instant movement.
- **Dynamic camera:**
  - All views frame the ball, the carrier and nearby players, with smoothing.
  - The view widens for long kicks, kick-outs and spread play, and tightens for close contests.
  - Any right-stick zoom or orbit recentres after 3 s.
  - A trigger axis that rests off-centre (some EasySMX modes) no longer locks the zoom.
- **Team AI:** two team-mates make support runs (a short option and a deep option) when you carry the ball. Backs mark
  the nearest attacker goal-side.
- The design notes and future roadmap are in `GAMEPLAY_REVIEW.md`.

## Training (menu -> Training)
- Free play in the attacking half with you, two team-mates to pass to, and the opposition
  goalkeeper. No clock, no 3v3 rule.
- After a score, a wide, a save or a lost ball, it comes back to you after about 1.5 s.
- On-screen prompts show the pad buttons, or the keys when no pad is connected, for what you
  can do right now (with or without the ball).
- The tally counts points, goals, shots and wides/saves.
- Use it to practise solo, bounce, hand pass, kick, shot and power kick, and to check the
  controller.

## Graphics quality and performance (F2 / F3 / F4)
- **F2**, or the menu, cycles the graphics quality. The setting is saved in `settings.txt`.
  - **Low** (default): blob shadows, no shadow-map sampling, no MSAA.
  - **Medium**: projected player shadows plus 1-tap stadium shadows.
  - **High**: soft 3x3 PCF shadows plus 4x MSAA (MSAA takes effect at the next start).
- **F3** shows FPS and a per-frame ms breakdown: game update, pose/skinning, 3D submit, HUD,
  GPU+swap.
- **F4** switches character skinning between the GPU (default: vertex-shader skinning, only
  52 bone matrices sent per draw) and the CPU (v3 behaviour, about 0.5 M vertices skinned and
  re-uploaded every frame). Keep whichever F3 shows is faster on your PC; it is saved too.
- VSync is on, with a 60 fps cap. Characters outside the camera view are not posed or drawn.

## Controller test and troubleshooting
To open the test screen, use the menu (**Controller test**), **F1**, or **Back** on the pad.
- It shows a live pad diagram: stick dots inside their circles (the deadzone is the inner
  ring), d-pad arrows, and A/B/X/Y/L1/L2/R1/R2/Start/Back lighting up while held, with
  trigger travel bars.
- It also shows the raw axis values, the raw button and hat numbers, the pad name and GUID,
  and whether a mapping was found.
- In a match the game pauses while the screen is open.

If the pad is not working:
- The game loads `assets/input/gamecontrollerdb.txt` (the SDL community database) at
  start-up. With it, most DirectInput pads, including EasySMX in D-mode, get the standard
  layout. XInput pads (EasySMX X-mode) always work.
- If the screen says **[no mapping - generic layout]**, the generic DirectInput layout is
  used: b0 Y, b1 B, b2 A, b3 X, b4 L1, b5 R1, b6 L2, b7 R2, b8 Back, b9 Start, hat = d-pad.
- If the buttons are wrong, either switch the pad to X-mode (hold the mode/home button about
  5 s; see the pad's manual), or add a line for your GUID to `gamecontrollerdb.txt`. The
  test screen shows the GUID and the raw button numbers you need.
- "No controller detected": try another USB port, or re-plug the pad while the game is
  running. Slots 0-3 are scanned every frame.

## Controls: gamepad (EasySMX / any XInput pad)
The game uses the first connected pad (slots 0-3) and checks again every frame, so you can
plug the pad in at any time. On an EasySMX pad, X-input mode is the most reliable; D-input works through
the bundled gamecontrollerdb (see *Controller test and troubleshooting*). Sticks have a 0.22 radial deadzone with rescaling. The keyboard keeps working
alongside the pad.

| Pad | With the ball | Without the ball |
|---|---|---|
| Left stick | move (camera-relative) | move |
| Right stick | orbit / zoom the camera (R3 resets) | same |
| A | hand pass | toe-lift pick-up |
| B | solo or bounce (picks the legal one) | - |
| X | kick: hold for power, release to kick | jump / high catch |
| Y | shoot: faces the posts; a low drive when close and central | - |
| R1 | sprint (about 9 m/s) | sprint |
| R2 | power kick: full-power long kick, aimed at the posts within 52 m (a two-point attempt from outside the arc) | - |
| L1 | - | switch to the player nearest the ball |
| L2 | - | tackle / shoulder charge |
| L2 + Y | - | **hook / head-hit special move: always a RED card** |
| Start | pause; skip the intro; menu select | |
| Back | controller test screen (F1 on the keyboard) | |
| D-pad | menu up/down; next/previous camera in a match | |

## Controls: keyboard
| Key | Action |
|---|---|
| WASD / arrows | move (relative to the camera) |
| Left Shift | sprint |
| SPACE hold + release | drop-punt pass/shot, with power set by hold time; without the ball: tackle |
| F | low driven / ground shot |
| G | shoot at goal (auto-aim) |
| L | power kick / two-point attempt |
| E | hand pass; pick up a ground ball |
| R | solo (toe-tap), or *Solo & Go* / play on from a mark |
| B | bounce (only once in a row) |
| J | jump / high-field |
| K | tackle |
| H | hook / head hit (red card!) |
| Q / TAB | switch player |
| 1-6 / C | cameras: Broadcast, TV close, Chase, Behind goal, Tactical, Player close-up |
| Z / X, V | orbit the camera, reset |
| T | auto-solo assist on/off |
| P | pause. F1: controller test / controls. F2 graphics quality. F3 FPS / profiler. F4 GPU/CPU skinning. Enter: new match after full time |

## Cards and discipline (shown by the referee)
* **Yellow**: a caution. A **second yellow = red**, and the player is sent off.
* **Black**: a **10-minute sin bin** (about 86 real seconds at the default match length). The
  HUD shows a countdown in match minutes for each binned player, and the team plays a man down.
  A black-card foul that denies a goal-scoring chance also gives a **penalty**.
* **Red**: sent off for the rest of the match. The player walks to the tunnel.
* The referee jogs to the offender and holds the card up. A large card graphic and the
  offender's name appear on screen, and the score bar shows each team's cards and man-down count.
* Also enforced: the advanced mark (a clean catch inside the 20 m line from a kick of 20 m or
  more), dissent (the free moves 50 m forward) and the back-pass to the keeper.

## Stadium, lighting and audio
* The stadium is modelled on Croke Park. It has a three-tier bowl of blue seats under a
  cantilever roof, the **Hill 16** terrace with a big screen, and a county-ground covered
  stand on the near side with yellow and blue seats and open terraces. The crowd moves more
  when play gets exciting. There is a sky dome and a distant city and hill backdrop.
* The grass is mown in stripes and the full GAA markings are painted on it: the 13, 20, 45
  and 65 m lines (the 65 m line is a hurling line, drawn as at Croke Park), the dashed halfway
  line, the 40 m scoring arc, the 20 m D, the small and large rectangles, and the penalty mark.
  The H-posts have nets.
* Lighting: a sun with a 2048 PCF shadow map for the stadium, hemispheric ambient, rim light
  and haze. Players and the ball cast sun-projected shadows (stencilled, so overlaps do not
  darken twice).
* Audio is generated in code, with no sound files. It includes a crowd bed and chants,
  whistles (single, long and double), a roar for goals, cheers, groans on wides, an "ooh"
  on cards, and kick and hand-pass thuds.
* **Commentary**: a text ticker at the bottom left. Each line also goes to
  `gf_commentary_hook(const char *line, int event, void *user)` in `src/sfx.c`. Set that
  pointer to connect a TTS voice later; no voice is included. Set the `GF_COMMENTARY=1`
  environment variable to print the lines to stdout.

## Rules implemented (2025/26 FRC rules, GAA Official Guide 2026)
* **Throw-in** by the referee at halfway to start each half: one midfielder per side contests
  it, and everyone else is behind the 45s.
* **Scoring**: goal = 3, point = 1, **two-pointer = 2** for a clean kick or free from on or
  outside the **40 m arc** (a 45 scores only 1). Umpires wave flags: green for a goal, white
  for a point, orange for a two-pointer.
* **Carrying**: at most 4 steps, then a solo (toe-tap) or bounce. You can't bounce twice in a
  row. **Overcarry** or a **double bounce** gives a free to the opposition.
* **Hand pass** has to be struck (fist action); the ball is released from the hand on the
  contact frame.
* **Ball on the ground** is lifted with the foot (pick-up action); a hand scoop off the ground is never used.
* **Kick-out** from the 20 m line by the keeper (distinct kit). The ball must travel beyond
  the 40 m arc, otherwise it's a free to the opposition. The opposition must be 13 m away and
  may contest it beyond the arc. Highlighted in yellow while pending.
* **Wide** gives a kick-out. Defender plays it over his own endline: **45**. Over the sideline:
  **sideline kick** for the other team.
* **Frees** for fouled tackles, with a deliberate run-up kick. *Solo & Go* (tap and play on) is
  allowed except inside the opposition 20 m line.
* **Penalty** for a foul in the large rectangle: off the ground from 11 m, only the keeper on
  the line, everyone else outside the 20 m / arc. The keeper may save.
* **3v3**: each team keeps at least 3 outfield players in each half. A breach gives a free.
* Referee runs with play and signals frees and scores. Restarts and fouls show event text.

**Not implemented:** advanced mark, the back-pass-to-keeper restriction, 50 m advance for
dissent/tactical fouls, cards/sin-bin, early-movement offences at the throw-in, the
"kick-out must be kicked forward" detail, and extra time.

## Animation
`assets/models/gaelic_player.glb` holds the skinned player (52 bones) plus 32 clips. The ball
(size 5, 22 cm) is attached to the hand bones while carrying. In a solo it drops to the foot
and comes back; in a bounce it goes to the ground ahead. Kicks release it from the kicking foot
bone on the contact frame, and hand passes from the striking hand. Clips cross-fade over 0.15 s.

| Source file | Clip | Used for |
|---|---|---|
| anim_idle | idle | standing |
| anim_run | run | running without the ball |
| anim_run_ball | run_ball | carrying the ball (one-arm carry); also the bounce |
| anim_keeper_ready | keeper_ready | keeper stance; ball cradled in both hands when standing |
| anim_kick_run | kick_run | running drop punt, ground kick |
| anim_drop_kick | drop_kick | frees / sideline / 45 (run-up) |
| anim_kick_out | kick_out | keeper kick-out |
| anim_solo | solo | toe-tap solo |
| anim_hand_pass | hand_pass | hand pass, tackle (arm action), referee arm-out signal |
| anim_catch | catch | high fielding, referee arms-up signal |
| anim_pickup | pickup | ground pick-up |
| anim_dive_save / dive_high / dive_roll / get_up | dive_* | keeper saves (penalties) |

| anim_kick_place | kick_place | frees, penalties and kick-outs off the ground (placed ball) |
| anim_toe_lift | toe_lift | outfield toe-lift pick-up |
| anim_tackle_reach | tackle_reach | tackle (two-hand reach segment 0.45-1.15 s) |
| anim_hook / anim_head_hit | hook, head_hit | special move (straight red card) |
| anim_trip / anim_knocked_down | trip, knocked_down | the fouled player falls |
| anim_jog / anim_sidestep | jog, sidestep | slower movement, officials |
| anim_celebrate_jump | celebrate_jump | scorer celebration |
| anim_keeper_idle / keeper_high_catch / keeper_scoop | keeper_* | keeper stance and handling |
| anim_hit_react, stumble, pushed, solo_left | (in the GLB, spare) | for later |

The FBX files that are not in the GLB (run_stumble, toe_lift_left, idle_shuffle and the other
keeper dives) are kept in `assets/source/` for later use. Contact frames (foot for kicks, hand
for passes and hooks, head for head hits) are detected automatically from the bone motion,
so kicks release on the true contact frame.

## Assets
* `assets/source/` holds the original FBX files (renamed `anim_<skill>.fbx`), the skin
  texture `young_lightskinned_male_diffuse.png` and the eye texture `brown_eye.png`.
* `tools/convert_assets.sh` regenerates the GLB and kit textures (needs FBX2glTF, python3,
  numpy and pillow).
* `assets/textures/` holds the kits: home, away, two keeper kits, referee, and umpire (long
  white coat).

`legacy/` keeps the original prototype sources for reference. The rules engine now lives in
`src/game.c`.
`./gaelic_football --screenshots` runs scripted scenes and writes `v3_*.png`.
`--demo` lets the computer play your team.

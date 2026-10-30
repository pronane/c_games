# Facility 64 — a GoldenEye 007 (N64)-inspired FPS prototype

Small first-person shooter in C99 + raylib, with a late-90s console look:
textured rooms, baked vertex lighting, fog, animated 3D guards and first-person
weapons with hands. All art is original and generated procedurally by the code.
There are no ripped or copied assets.

## v3: Enhanced graphics mode (press F2)
F2 switches between the **Classic** procedural look and **Enhanced** while you play, in a mission or in
deathmatch. A toast shows `Graphics: Enhanced (F2)` or `Graphics: Classic (F2)`. Your choice is saved to
`settings.cfg` next to the exe. Enhanced is the default the first time you run the game.

The Enhanced look adds:
- **Skeletal-mesh models.** Guards, deathmatch players, first-person arms and weapons, and props
  (crates, barrels, desks, server racks) are 3D models loaded from `assets/models/`.
  - Characters are skinned on the GPU in the lighting shader.
  - Clips are blended by name: idle/walk/run, an upper-body layer for aim/shoot/reload
    over the legs, a death clip, and 0.18 s crossfades between them.
  - The held weapon is attached to the hand bone, and muzzle flashes come from the weapon's muzzle.
  - Blob shadows sit under the hips and feet.
- **Level shading.** Textures are upscaled to 512 px with fine detail. If
  `assets/textures_hd/<name>.png` exists, it replaces the texture with that name.
  Surfaces get bump and specular from the texture detail, the 6 nearest lights are per-pixel, and the fog is
  tinted with a little extra height fog near the floor.
- **Bloom** around lights and muzzle flashes (needs raylib 6.x). 4x MSAA is used where the driver supports it.

Each model falls back on its own: if a model file is missing or fails to load, that one thing is drawn
the Classic way. The console log lists every `ENHANCED: [role] ...` line.

### Using your own models (GLB / glTF / IQM / OBJ / FBX)
1. Put the file in `assets/models/`.
2. Edit `assets/models/models.cfg`. Every key is documented at the top of that file:
   ```ini
   [guard_soldier]          ; role: guard_soldier guard_cap commando player1 player2
   file  = my_soldier.glb   ; weapon_pp7 weapon_pp7_silenced weapon_kf7 weapon_golden
   height = 1.8             ; view_pp7 view_pp7_silenced view_kf7 view_golden
   rot   = 0 90 0           ; prop_crate prop_barrel prop_desk prop_rack
   clip_walk = Walking      ; clip names in your file (exact, then "contains")
   clip_death = Death_A
   attach = hand.R          ; bone the weapon is attached to
   upper_body = spine       ; first bone of the aim/shoot/reload layer
   ```
3. Press **F3** in game to reload the manifest and all models. You don't need to recompile.

The game expects:
- Characters face +Z in the file (the glTF default), are Y-up, stand on y = 0 and are about 1.8 units tall.
- The weapon socket bone (`attach`) is at the grip, with the barrel along +Z.
- Viewmodels are authored in camera space looking down +Z.
- Clips idle, walk, run, aim, shoot, reload and death are mapped by name.
  Missing clips fall back: run→walk→idle, shoot/reload→aim→idle.

**FBX** isn't loaded directly (raylib has no FBX loader). Convert it first:
- Windows: `tools\convert_fbx_to_glb.bat model.fbx`, or pass a folder.
- Linux/macOS: `tools/convert_fbx_to_glb.sh model.fbx`

The script uses **Blender** if it can find it (recommended). It runs headless through
`tools/blender_fbx_to_glb.py` and keeps every animation take as a named clip. If Blender isn't
available it uses the **Assimp** CLI (`assimp export in.fbx out.glb -fglb2`). Assimp keeps the
skeleton and clips, but it often loses embedded textures and leaves the model in centimetres,
so add `height = 1.8` for it.
Both routes were tested with a round-trip FBX of one of the bundled characters.

**Placeholder art.** All bundled models are original placeholder designs. `tools/make_models.py` built them
in headless Blender, and `tools/make_textures.py` made their textures.
Run `blender -b -P tools/make_models.py -- <texture_dir> assets/models` to rebuild them.
None of the models or textures are ripped or copied from any commercial game, and none use the likeness of a real
person or character.

## What's in v2 (graphics overhaul)
- **Textures.** 46 procedural, tileable textures (concrete, brick, wood panelling, lab
  tiles, steel plate, checker and wood floors, ceiling tiles, hazard stripes, crates,
  doors, character atlases, weapons, sky and snow). They're shipped as PNGs in `assets/textures/`.
  If that folder is missing, the game regenerates them in memory.
  Run `game.exe --export-textures` to rewrite the PNGs, then edit them in any paint program
  and the game will load your versions.
- **Lighting.** A GLSL 330 shader. Per-vertex baked light comes from 17 ceiling fixtures plus
  daylight through the outside windows, with distance falloff, light occlusion by walls and doors, and ambient occlusion
  in corners and around props. Up to 4 dynamic lights (muzzle flashes, the extraction beacon)
  and exponential fog are added at run time. If the shader fails to compile, the game falls back to raylib's default shader.
- **Guards.** Jointed 3D humanoids (hips, torso, head, arms and legs) with walk-cycle, aiming and death
  animations. There are 5 original outfits: soldier with helmet, facility guard with cap,
  commando with beanie and balaclava, and two suited agents used for the deathmatch players. Blob shadows sit under each one.
- **Weapons.** 3D PP7-style pistol and KF7-style rifle viewmodels with hands, sleeves
  and cuffs. They have walk bob, recoil kick, a slide that locks back, a reload dip, a screw-on silencer model,
  a rotating muzzle flash and ejected shell casings.
- **Effects.** Bullet-hole decals, sparks, dust and chips, gun smoke, a muzzle light, a red damage
  vignette, a crosshair that grows with movement and firing, and glowing light fixtures. There is no blood.
- **Props.** Crates and crate stacks, barrels, desks with CRT terminals and keyboards,
  server racks with blinking LEDs, pillars, and a red armoury door with gold padlocks. Pickups are
  3D models (ammo box, body armour, data disk, the Golden Gun, a dropped KF7).
- **Outside.** Exterior windows show a snowy mountain skybox and snowfield.
  4x MSAA is used where the driver supports it.

## Build (Windows 10, MSYS2 UCRT64)
1. In an **MSYS2 UCRT64** terminal, install the toolchain and raylib once:
   `pacman -S --needed mingw-w64-ucrt-x86_64-gcc mingw-w64-ucrt-x86_64-raylib`
2. Double-click `build_release.bat`, or run it from a VS Code terminal.
   It adds `C:\msys64\ucrt64\bin` to PATH, builds `game.exe`, and copies the
   raylib/glfw DLLs next to it.
3. Run `game.exe`. The batch file also creates a self-contained `release\` folder
   (exe, DLLs, `assets\`, README) and zips it into `Facility64_release.zip`.
   You can share that zip.

Manual command: `gcc src/main.c -o game.exe -O2 -lraylib -lopengl32 -lgdi32 -lwinmm`
(compile only `main.c`, because it `#include`s `gfx_textures.c`, `gfx_models.c`, `gfx_enhanced.c` and `input_pad.c`).
Keep `assets\models\` next to the exe for Enhanced mode. `build_release.bat` copies it into `release\`.
Tested against raylib 5.5 and 6.2.

## Modes
- **[1] Mission: Facility.** A bunker with 12 small rooms, several routes, sliding doors,
  and bulletproof windows. You can see through the windows, but guards can't.
  - A. Shoot the gold lock off the red armoury door (in the server room).
  - B. Pick up the data disk in the armoury.
  - C. Reach the green extraction pad in the top-right room.
- **[2] Deathmatch, 2-4 players.** Pressing 2 opens a join-in lobby (see *Controllers* below).
  2 players use a top/bottom split and 3-4 players use a 4-way split. With 3 players the spare quadrant shows the scores.
  First to 5 kills wins.
  The **Golden Gun** in the main hall kills in one hit. It goes back to the hall when its holder dies.

## Controls — Mission
| Action | Keys |
|---|---|
| Move / strafe | W A S D |
| Look | Mouse, or arrow keys (Page Up/Down also look up/down) |
| Fire | Left mouse, Space, or Left Ctrl |
| Aim (slower look + zoom) | Z |
| Reload | R |
| Weapons | 1 = PP7, 2 = KF7 Soviet (guards drop it), mouse wheel / F = next |
| Silencer on/off (PP7) | T |
| Open door | E or right mouse (walking into a door also opens it) |
| Watch menu (pause, objectives) | TAB, ESC or P |
| In the watch menu | Up/Down + ENTER: Resume / Restart / Options / Quit to title. Q quits to title, TAB/P/ESC resumes |
| Controller options (title screen) | O (or 0) |
| Graphics: Classic / Enhanced | F2 (any time, also in deathmatch and on the title screen) |
| Reload models.cfg + models | F3 |

## Controls — Deathmatch
- **P1:** WASD, mouse look, Q/E to turn, Left mouse or Space to fire, R to reload, 1/2/3 or the wheel to switch weapons
- **Keyboard P2** (press K in the lobby, or press ENTER in the lobby when you are alone): arrow keys to move and turn,
  `,` `.` to strafe, Right Ctrl, Enter or Numpad 0 to fire, Right Shift to switch weapons, `/` to reload.
- **Controllers:** up to 4, one per player. See below.

## Controllers (gamepads)
Up to 4 controllers (raylib gamepad ids 0-3) work in the title menu, the options, the mission and deathmatch,
in both Classic and Enhanced graphics. Keyboard + mouse always stays available for P1.

**Joining and hot-plug**
- Title and menus: D-pad or left stick to move, **A** to select, **B** to go back. Holding a direction repeats.
  The controller you use on the title screen becomes P1's.
- Deathmatch lobby: a free controller presses **A** or **START** to join as the next player, and **B** leaves.
  **START** on a joined controller (or ENTER) starts the match, and **BACK** lets P1 use the keyboard and a controller together.
  The *Deathmatch pad assignment* option switches between "press A / START to join" and "automatic, in connection order".
- Mission: P1 gets the first connected controller automatically.
- Plugging in or unplugging shows a message. If a deathmatch player's controller disconnects, or P1's controller
  disconnects while it was the active device in the mission, the game pauses. Reconnect it, or press **A** on another
  controller to take over that player.
- Prompts show controller button names while a controller is the active device, and keys after you touch the keyboard or mouse.

**Control styles** (generic Xbox-style names: A B X Y, LB RB, LT RT, BACK START)

| Action | Modern dual-stick | Classic 1.2-style |
|---|---|---|
| Move / strafe | left stick | right stick (digital) or D-pad |
| Turn / look | right stick | left stick (turn + look up/down, like the old single stick) |
| Fire | RT | RT |
| Aim (slower look + zoom) | LT | RB |
| Reload | X | A (shared with Use) |
| Next weapon | Y | B |
| Use / open door | A | A |
| Silencer (mission) | B | Y |
| Pause / watch menu | START (BACK also works) | START (BACK also works) |

"Classic 1.2-style" is only an approximation of the old one-stick-look, C-buttons-to-walk idea, mapped to a modern pad.
It is not a copy of any original layout.

**Options** (title: OPTIONS / CONTROLLER, or watch menu: OPTIONS / CONTROLLER)
- Control style, look sensitivity (0.2-3.0), **radial** stick deadzone (0.05-0.45, rescaled so movement starts smoothly
  at the edge of the deadzone), invert look Y, aim acceleration (full stick deflection for longer than 0.2 s ramps turning
  up to 2x), trigger threshold (10-90 %), vibration on/off, and deathmatch pad assignment.
- The options screen shows live stick previews: the raw input and the input after the deadzone.
- **Remap buttons...:** pick an action, then press the new button. Waits for you to let go first, times out after 6 s,
  and ESC cancels. LEFT/RIGHT switches between the two styles. Buttons used by two actions are marked "(shared)".
  Menus always use A/B, so a bad remap can't lock you out.
- **Controller debug...:** live axes, stick previews and the button grid for all 4 slots, with the name from `GetGamepadName`.
  Hold LB+RB to test rumble. Hold B for 1 s (or ESC) to leave.
- Settings are saved to **`controls.cfg` next to the exe** when you leave the options. It's plain text, so you can edit it by hand.
  Delete it to get the defaults back.

**Rumble**
- Rumble is requested when you fire (strength depends on the weapon) and when you take damage (longer when you die).
- **Windows:** raylib's desktop (GLFW) `SetGamepadVibration` is only a stub, so the game loads XInput itself
  (`xinput1_4.dll`, falling back to `xinput1_3` / `xinput9_1_0`) and calls `XInputSetState`.
  GLFW doesn't expose the XInput slot, so the game maps the k-th XInput-style raylib pad to the k-th connected
  XInput slot. That is correct for the usual setups, but it is a guess.
- **Linux / macOS:** no rumble. The options and debug screens say "unsupported".

**Windows / XInput / Easy SMX**
- Easy SMX pads in their default **XInput** mode show up as an Xbox controller (e.g. "Xbox Controller"),
  and everything above works, including rumble.
- In **D-input / Android** mode the pad shows up under its own name, and GLFW needs an SDL mapping for it.
  Put a `gamecontrollerdb.txt` (the community SDL_GameControllerDB file) next to the exe and the game loads it at start-up
  with `SetGamepadMappings`. Or switch the pad back to XInput mode (the pad's manual explains its mode button combo).
- The debug screen shows the name and the raw buttons, so you can check what Windows reports.

**Testing without hardware:** `game --pad-script FILE` replaces the real pads with simulated ones driven by a script.
Each line is `TIME PAD COMMAND ARGS`, with these commands:
`connect NAME`, `disconnect`, `down BTN`, `up BTN`, `tap BTN`, `axis LX|LY|RX|RY|LT|RT VALUE`, `shot FILE.png`, `quit`.
Times are in seconds, and the trigger values go from 0 to 1. `PAD` is `-` for shot/quit.

## How the guards behave
- Guards patrol back and forth. They spot you with a vision cone plus a line-of-sight check.
  Walls, closed doors and windows block their sight.
- Each gunshot alerts every guard within a noise radius, and they come to investigate where you fired from.
  The silenced PP7 has a radius of 3 m, the loud PP7 12 m and the KF7 18 m.
  Each extra shot within 2.5 s raises the radius by 50%, up to 3.5x.
  If you stay quiet for 2.5 s, it resets. The HUD shows the current radius.
- A guard who sees you shouts, which alerts guards nearby. Guards open doors and path-find through the level.
- A headshot does 3x damage, so one PP7 headshot kills a guard.

## Code layout
- `src/main.c`: game logic, AI, level, lighting bake, shader, rendering, HUD and menus.
  The level is the ASCII map near the top. The legend is in the comment above it.
  `O` marks an outside window. Props are placed in `SetupProps()`.
- `src/gfx_textures.c`: procedural texture generators, including the character atlases.
- `src/gfx_models.c`: mesh builders for the characters, weapons, doors and pickups.
- `src/input_pad.c`: controllers. It has the pad polling, radial deadzone and aim curve, control styles and remapping,
  `controls.cfg`, XInput rumble, the deathmatch lobby, hot-plug, the options/remap/debug screens and `--pad-script`.
- `src/gfx_enhanced.c`: Enhanced mode. It has the models.cfg parser, the model loading and fallback, the pose
  evaluator (clip layers, crossfade, upper-body mask), the GPU-skinning lighting shaders, the HD textures, bloom,
  and the F2/F3 handling and settings.
- `assets/textures/`: exported PNGs, loaded at start-up if present.
- `assets/models/`: the Enhanced-mode GLB models and `models.cfg`.
- `tools/`: `make_textures.py` and `make_models.py` (Blender) rebuild the placeholder art.
  `convert_fbx_to_glb.*` and `blender_fbx_to_glb.py` convert FBX files.

## Known limits
- Enhanced mode:
  - The bundled models are simple placeholders.
  - Characters hold pistols in the same two-hand pose as rifles.
  - The death clip doesn't use the hit direction.
  - Bloom is only available with raylib 6.x. On raylib 5.5 everything else works.
  - The split-screen halves have no MSAA.
  - FBX has to be converted first (see above).
- The look is late-90s style: low-poly box-built models, 128-256 px textures and
  per-vertex lighting. There are no real-time shadows, apart from blob shadows under characters.
- Split screen renders into textures without MSAA. Sprites such as particles and glass aren't fogged.
- Controllers:
  - Testing was done with simulated pads (`--pad-script` and a code-level test harness), not with real hardware.
  - Rumble only works on Windows, and its XInput slot mapping is a guess (see above).
  - Settings are shared by all players, not stored per player.
  - Only one keyboard player can be added in the lobby (P2).
  - Pads that aren't XInput need a `gamecontrollerdb.txt` mapping.

# Egyptian Fighter – Character Select + Versus (Raylib + C)

A complete Street Fighter-style prototype with:

- Character select screen
- Two different characters (just called Character 1 & Character 2)
- Human vs CPU **or** Human vs Human
- Full moveset for each character
- **Works even if many (or all) PNG files are missing** – missing assets become colored placeholders + console warnings

## Controls

### Character Select (update 4: one cursor, 2D grid)
| Key / button | Action |
|-----|--------|
| Arrows or WASD, D-pad or stick | Move the cursor over the grid (up/down **and** left/right) |
| Enter / J / Z / Space, pad **A** or **Start** | Lock the highlighted fighter. The first lock is the LEFT slot; the cursor then jumps to the RIGHT slot (CPU or P2) |
| Backspace / X, pad **B** | Un-ready the last pick |
| Tab / E, pad **RB** | Next mode: 1P vs CPU → CPU vs 1P → 1P vs 2P |
| Q, pad **LB** | Previous mode |
| F1, pad Back/Select | Controller test / pad controls screen |

When both slots say **READY**, the game goes straight to the PADEL WARS face-off and then the fight.
With **two controllers in 1P vs 2P**, each pad gets its own cursor (P1 = blue, P2 = pink) and each
player locks with their own A/Start and un-readies with their own B. On the keyboard in that mode:
P1 = WASD + J (Backspace back), P2 = arrows + Z (X back).

(Gamepad controls: see **USB controllers / gamepads** below.)

### During Fight
**Player 1**
| Key | Action |
|-----|--------|
| WASD / Arrows | Move / Crouch / Jump |
| J | Punch |
| K | Kick |
| U | Special 1 – Pyramid Blast |
| I | Special 2 – Bum Fireball |
| L | Block (hold) |
| O | Throw |
| P | Taunt |

**Player 2** (Human vs Human)
| Key | Action |
|-----|--------|
| Arrow keys | Move / Crouch / Jump |
| Z | Punch |
| X | Kick |
| C | Special 1 |
| V | Special 2 |
| B | Block |
| N | Throw |
| M | Taunt |

| Key | Global |
|-----|--------|
| ESC | Pause / Unpause |
| R / Enter | Return to Character Select (after match) |

### USB controllers / gamepads (2 players) – incl. EasySMX

Plug in one or two USB (or wireless-dongle) pads. The keyboard keeps working at the same time,
so you can mix pad and keyboard. Controllers can be plugged in or pulled out at any time.

* **1P vs 2P:** the first pad (pad 0) is **Player 1**, the second (pad 1) is **Player 2**.
  A pad plugged in later takes the free player slot. If a player's pad is unplugged during a fight,
  the game pauses and tells you which pad was lost.
* **1P vs CPU / CPU vs 1P:** the human can use **any** connected pad.
* The select screen shows what each side is using, e.g. `P1: Keyboard + Xbox 360 Controller (pad 0)`.

**Fight**

| Pad (Xbox name / PlayStation name) | Action | Keyboard P1 / P2 |
|---|---|---|
| D-pad **or** left stick | Walk left / right | A D / ← → |
| D-pad up / stick up, **or A / Cross** | Jump | W / ↑ |
| D-pad down / stick down | Crouch | S / ↓ |
| **X / Square** | Punch | J / Z |
| **Y / Triangle** | Kick | K / X |
| **B / Circle** or **LT / L2** | Special 1 – Pyramid Blast | U / C |
| **RT / R2** | Special 2 – Bum Fireball | I / V |
| **RB / R1** (hold) | Block | L / B |
| **LB / L1** | Throw | O / N |
| **Back / Select** | Taunt | P / M |
| X or Y while in the air | Jump attack | J,K / Z,X in the air |
| **Start** | Pause / resume | ESC |

Stick dead-zone: 0.35 for left/right, 0.5 for up/down (so walking never makes you jump by accident).

**Menus (character select)**

| Pad | Action |
|---|---|
| Left / Right (D-pad or stick) | Change your fighter (each player uses their own pad in 1P vs 2P) |
| Up / Down | Change mode (1P vs CPU → CPU vs 1P → 1P vs 2P) |
| A / Cross or Start | Ready (against the CPU, the fight starts straight away) |
| B / Circle | Cancel ready |
| LB / RB | Change the **CPU's** fighter (CPU modes) |
| Back / Select (or **F1** on the keyboard) | **Controller test** screen |
| A / Start on the result screen | Back to character select |

**Controller test screen** (Back/Select or F1 on the select screen): shows every connected pad,
its name and GUID, whether it is *MAPPED* (green) or using the *RAW FALLBACK* (orange), the
buttons and sticks you are pressing, and the raw button/axis/hat numbers. It also lists the pad
controls. Leave with F1 / Esc, or hold Start for 1 second.

#### EasySMX and other "PC / USB" pads

EasySMX pads (and many other cheap pads) can run in two modes:

* **XInput mode** – Windows sees an "Xbox 360 Controller". Works out of the box with the standard
  Xbox layout. **This is the most reliable mode.** How you switch depends on the model: many EasySMX
  pads switch mode by holding the Home/mode button for a few seconds, others have a mode switch.
  Check your pad's manual, because the steps vary by model.
* **DirectInput / "PC" mode** – Windows sees a generic HID joystick. Its buttons have no standard
  layout, so the game needs a *mapping*:
  1. `assets/gamecontrollerdb.txt` (the Windows + Linux part of the community
     [SDL_GameControllerDB](https://github.com/mdqinc/SDL_GameControllerDB), zlib licence) is loaded at
     start-up. It includes several EasySMX entries.
  2. EasySMX and a few generic USB pad mappings are also built into the game, so they work even
     without that file.
  3. If your pad still isn't recognised, it shows as **RAW FALLBACK** on the controller test screen and
     the game uses the most common generic layout: buttons 0=Y/Triangle, 1=B/Circle,
     2=A/Cross, 3=X/Square, 4=LB, 5=RB, 6=LT, 7=RT, 8=Back, 9=Start, hat = D-pad, axes 0/1 = left stick.
  4. If buttons are still in the wrong place, make a mapping line for your pad (for example with
     the free *SDL2 Gamepad Tool*). Put it in a new file, `assets/gamecontrollerdb_user.txt`. That file
     is loaded last, so it overrides everything else.

The game uses raylib's gamepad API (GLFW). Up to 4 pads are detected and 2 players are supported.
Vibration isn't used.

---

## Online versus

Press **Tab** (or **RB**) on the select screen until the mode says **ONLINE**. Then choose:

* **Quick match**: you're paired with the next player who does the same.
* **Create private room**: you get a 5-character code to send to a friend.
* **Join room with code**: type the code and press Enter.

In the room, pick your fighter and lock it in (Enter / A). Backspace / B un-readies, and Esc leaves the room. When both players are ready, the face-off plays and the fight starts on both screens at the same time. You always use the P1 keys (WASD + J K U I L O P) or any controller, whichever side you're on. There's no pause online. If someone's connection drops, the fight waits up to 30 s for them to come back.

Both players need the same server. Run the shared server (`shared/netplay/server`, `npm start`) or deploy it to Render, then either copy `netplay.cfg.example` to `netplay.cfg` and set `server = wss://<your-app>.onrender.com/egyptian`, or start the game with `--server ws://host:3000/egyptian` (or set `EF_SERVER`). The default is `ws://localhost:3000/egyptian`.

How it works (lockstep, the same protocol as HD Fighter) and its limits are in [`shared/netplay/README.md`](../shared/netplay/README.md). Both players should run the same build.

## Asset Folders

```
assets/
├── char1/
│   ├── idle.png
│   ├── walk.png
│   ├── crouch.png
│   ├── jump.png
│   ├── punch.png
│   ├── kick.png
│   ├── pyramid_blast.png
│   ├── bum_fireball.png
│   ├── block.png
│   ├── hit.png
│   ├── throw.png
│   ├── jump_attack.png
│   ├── taunt.png
│   └── victory.png
└── char2/
    └── (same 14 files)
```

You can put any of the generated male/female sheets into `char1` or `char2`.  
They are treated simply as two different characters.

Each animation PNG should be a single horizontal strip. The game uses these
frame counts: 6 for idle, crouch, punch, kick, both specials, block, hit, throw,
jump attack, taunt, and victory; 8 for walk and jump. Keep transparent padding
around the figures: the game uses it to align their feet and normalize their
on-screen height.

### Missing assets behaviour
- The game **compiles and runs** even if zero PNG files exist.
- Every missing file prints a clear `WARNING: MISSING ASSET: ...` in the console.
- A colored placeholder rectangle is shown instead (different colour per animation state).
- You can add the real PNGs later at any time and they will be used automatically.

---

## How to Build & Run (Windows + VS Code)

1. Install MSYS2 + MinGW + Raylib (easiest):
   ```bash
   pacman -S mingw-w64-x86_64-gcc mingw-w64-x86_64-raylib
   ```
   Add `C:\msys64\mingw64\bin` to your PATH.

2. Open this folder in VS Code.

3. Double-click **`build_release.bat`** (or run it from a terminal).

The script detects the compiler, builds an optimized executable, copies assets, and launches the game.

Controller support: `build_release.bat` also links `-lglfw3`. MSYS2's raylib package uses the
separate `glfw` package, which pacman installs with it. The raw-joystick fallback for unmapped
DirectInput pads calls GLFW directly. If GLFW can't be linked, the script builds without that
fallback (`-DEF_NO_RAW_PAD`). XInput and mapped pads still work. When it falls back to the DLL
build, `glfw3.dll` is copied next to the exe.

Developer test hooks: set `EF_FAKEPAD_DIR=<folder>` to feed fake pads from text files
`pad0`…`pad3` (see `src/pad.c`). Set `EF_LOGSTATE=1` to print every fighter state change.
Set `EF_TEST_HP2=10` to start player 2 with 10 health (quick KO / victory-pose tests).

If Raylib is not auto-detected:
```bat
set RAYLIB_PATH=C:\msys64\mingw64
build_release.bat
```

---

## Project Structure

```
egyptian_fighter/
├── src/
│   ├── main.c
│   ├── common.h
│   ├── player.h / player.c
│   ├── pad.h / pad.c      ← USB / XInput / EasySMX gamepad support
│   ├── gfx.h / gfx.c      ← fullscreen, TV scaling, fonts, texture filtering
│   └── game.h / game.c    ← screens (select, PADEL WARS face-off, fight, result)
├── assets/
│   ├── gamecontrollerdb.txt   ← controller mappings (SDL_GameControllerDB)
│   ├── captions.cfg    ← PADEL WARS title + face-off captions (edit me)
│   ├── fonts/          ← Barlow Semi Condensed + Bangers (SIL Open Font License)
│   ├── char_mike/ char_daragh/ char_dec/  ← sheets + sprites.cfg + portrait.png
│   ├── char1/          ← drop Character 1 sprites here
│   └── char2/          ← drop Character 2 sprites here
├── build_release.bat
└── README.md
```

Enjoy!

---

## Rebuilt sheets for PADEL MIKE, DANGEROUS DEC and DARAGH (grid format)

The first versions of these characters showed several copies of the fighter at once
(e.g. 6 Mikes while walking, 2 while blocking) and walked by gliding. There were two causes:

1. **Code:** the loader cut every sheet into equal slices (`width / 6` or `width / 8`).
   The source strips for these characters are 7,000–16,000 px wide, have uneven spacing
   and contain the same pose tiled several times, so one "frame" held several figures.
2. **Art:** the walk strips repeat one stride pose (the legs never alternate), each sheet
   uses a different scale, the suit/LONDON sheets had the white shirt keyed out to
   transparent, and one sheet still had its background.

### What changed
* `tools/build_sprites.py` rebuilds each sheet from `sprite_sources/`: background removal
  by flood fill from the edges (white shirts are kept), one figure per frame by connected
  components, duplicates and slivers dropped, everything scaled to the same standing height
  and placed in a uniform grid with the feet on one baseline. It also writes `sprites.cfg`.
  The walk cycles are rebuilt by cutting the legs apart at the hip and swinging them
  alternately, so one foot passes the other.
* `src/player.c`: if `assets/<char>/sprites.cfg` exists, the character is loaded in
  **grid mode** (exact cell width, exact frame count, feet anchored at the baseline, frame
  time per animation). Missing animations fall back to a similar one (e.g. kick -> punch ->
  idle) rather than a placeholder. Characters without `sprites.cfg` (RA, PAUL, DRAGON, FLAME)
  use the old loader as before.
* Fixed a drawing bug: a character facing left drew the *next* cell of the strip, and on the
  last frame it read past the end of the strip.
* `--demo <index> [outDir]` test mode plays idle/walk/block/punch/kick/jump/crouch/throw/hit
  for one character (facing both ways) and can save PNG frames.

### Rebuilding the sheets yourself
```
pacman -S mingw-w64-ucrt-x86_64-python-pillow mingw-w64-ucrt-x86_64-python-numpy mingw-w64-ucrt-x86_64-python-scipy
python tools/build_sprites.py                   # all three characters
python tools/build_sprites.py --only char_mike --preview preview
```
Edit the `SPEC` table at the top of the script to change source files, frames (`pick`),
scale (`stand_h` = upright height of the figure in the source, in pixels) or frame time.

### sprites.cfg
```
cell 456 600          # every frame is exactly 456 x 600 px
baseline 591          # y of the feet inside a cell
stand_height 420      # upright figure height -> drawn 300 px tall on screen
anim walk walk.png 8 0.085   # name, file, frame count, seconds per frame
projectile ball       # specials fire a projectile drawn by the game: ball | book | card
```

> **Folder mapping:** `char_dec` = the man in the navy suit, `char_daragh` = the man in the white
> "LONDON" T-shirt with a padel racket, `char_mike` = the "I ♥ HYROX" vest. If Dec and Daragh are
> the wrong way round, swap the two folder names.


## Full move set for Mike, Daragh and Dec (update 2)

**Why "nothing happened" on punch / kick / jump / throw:** the game logic was running (the
moves started, dealt damage and the jump left the ground), but Mike only had idle / walk /
block sheets and Daragh only idle / walk, so every other move fell back to the idle picture
and looked like nothing happened. On top of that the CPU walked *away* when close (which
turned it round), so its attacks went the wrong way, and there were no projectiles at all.

What is in this version:

* Every state Flame/Dragon have now has its own sheet for all three characters:
  idle, walk, crouch, jump, punch, kick, pyramid_blast (special 1), bum_fireball (special 2),
  block, hit, throw, jump_attack, taunt, victory.
* **Dec** uses his real frames (idle, crouch, jump, punch, kick, throw, hit) and the extra moves
  are re-timed / transformed copies of them with a purple "magic" glow (special 1 = throw
  frames, special 2 = punch frames, jump attack = high-kick frames, victory = arms-up jump
  frames, taunt = guard frames, hit = real hit frames with a red flash).
* **Mike and Daragh** have no source art for these moves, so `tools/poses.py` builds them from
  their own photo (no new pictures are generated): the figure is cut into far leg, near leg,
  body, free arm and racket arm, and the parts are rotated / shifted / squashed (punch = arm
  extends, kick = leg swings up, jump = squash then tuck, crouch = low wide stance, hit = lean
  back + red flash, block = racket up, throw = lunge + two-hand shove, specials = racket
  smash / low drive with a yellow glow, victory / taunt = racket raised). Mike keeps his real
  ready-stance block. Part maps are in `RIGS` in `tools/build_sprites.py`.
* **Projectiles** (`game.c`): characters whose `sprites.cfg` has a `projectile` line fire one on
  the middle frame of their specials: Mike a spinning padel ball, Daragh a speech bubble (update 3), Dec a purple book
  (special 1, high – duck under it) or purple card (special 2, low – jump over it). 10 damage,
  1 chip damage through a block, two projectiles cancel. Flame/Dragon are unchanged.
* **Facing:** on the ground fighters always face the opponent (walking away is a slower back
  step), so attacks never go the wrong way.
* **CPU:** walks in, punches / kicks / throws / uses specials and jump attacks, fires
  projectiles from range, blocks some of your attacks. In CPU vs 1P the CPU really controls
  the left fighter (before, the keyboard drove the "CPU" and the AI drove you).
* Sheets are composed and saved at full resolution (fighters 560 px tall, `OUT_SCALE = 1.0` in `tools/build_sprites.py`) for a sharp picture on big TVs. Set `OUT_SCALE = 0.75` to make the download smaller.

---

## Update 3: PADEL WARS face-off, Mike's flex, Daragh's speech bubble, big-TV mode

### Mike's victory: double-bicep flex
Mike's `victory` sheet is now a 6-frame double-bicep pose. It was built from his own photo
frames: the arms were cut at the elbow, then the upper arms raised and the forearms bent up
with the fists clenched beside his head. Frames 2–5 loop as a flex "pulse" (`loop victory 2`
in `sprites.cfg`), so he keeps flexing on the win screen.

### Daragh's special: the speech bubble
Both of Daragh's specials (U / I, pad B/LT / RT) now play an 8-frame move. He turns around,
bends at the hips (about 80°) so his backside points at the opponent, then straightens and turns
back. On the fire frame a cartoon speech bubble (white with a black outline, tail pointing at
his backside) comes out. It says **PARP!** for special 1 and **PADEL!** for special 2.
The bubble is his projectile: it flies like the ball did and does the same damage and hit
detection. `projectile bubble` is set in `assets/char_daragh/sprites.cfg`.
Mike still throws the padel ball. Specials are now always cast standing still: before, firing
one mid-walk slid the fighter along the floor.

### PADEL WARS face-off screen
After both players are ready, a 3.6 s face-off screen plays. It shows a **PADEL WARS** title,
both faces sliding in (P2 mirrored to face P1), a slammed-in **VS** and a caption under each face.
It also plays in the CPU modes. Skip it with **Enter / Space / pad A / Start**.

Captions live in **`assets/captions.cfg`**. Edit it with Notepad and restart the game:
```
title = PADEL WARS
char_mike = Mike "The Padeller"
char_daragh = Flynn 'The Padel' Fidder
```
Each key can be the folder (`char_mike`) or the display name (`PADEL MIKE`). Fighters that
aren't listed show their name. The faces are, in order of preference:
1. `assets/<folder>/portrait.png` (a head-and-shoulders crop of the photo, written by `tools/build_sprites.py`);
2. the character's select-screen portrait (`assets/portraits/...`);
3. an automatic head-and-shoulders crop of the first idle frame (Flame, Dragon, Ra and Paul use this
   unless you add a portrait).

### Playing on a big TV (56" over HDMI)
- **Fullscreen:** press **F11** or **Alt+Enter** (also Alt+keypad Enter). You can also start the game
  with `egyptian_fighter.exe --fullscreen` (or `--windowed`). The choice is saved in `settings.cfg`
  next to where you run the game, so it is remembered next time.
- Fullscreen is a borderless window at the **TV's native resolution** (1080p or 4K). The game keeps its
  1280×720 layout but draws everything at the real screen resolution. It is not stretched from a small
  picture, so sprites, text and lines stay sharp. A different aspect ratio gets black bars.
- Sprites are now kept at full resolution (fighters about 560 px tall) and drawn with trilinear
  filtering, mipmaps and premultiplied alpha, so edges have no dark fringes or shimmer. The game also
  uses 4× MSAA and VSync (no tearing).
- Text uses real fonts (Barlow Semi Condensed and Bangers, SIL Open Font License, in `assets/fonts/`)
  rendered at 96/192 px, so it stays crisp on a TV. If the fonts are missing, the old built-in font is used.
- **Stage backgrounds:** use at least **1920×1080** PNGs (3840×2160 for 4K TVs). Smaller stages
  log a `STAGE ... is only WxH` warning and will look soft.
- The console prints `DISPLAY: drawing at WxH (game scale S)` so you can check the real resolution.

**TV / Windows settings for the sharpest picture:**
1. Windows *Settings → System → Display*: set the TV as the display at its **recommended (native)
   resolution** (3840×2160 for a 4K TV, 1920×1080 for a 1080p TV). Scaling 100–150% is fine, because
   the game draws at native pixels either way.
2. On the TV, turn on **Game mode** for that HDMI input. This gives lower input lag and less over-processing.
3. Turn off overscan: picture size / aspect = **"Just Scan"**, **"Screen Fit"**, **"PC"** or **"1:1"**
   (the name depends on the brand). Otherwise the edges, including the health bars, are cut off and
   the picture is rescaled and soft. Some TVs only offer this when the input is labelled **PC**.
4. Use a High Speed / Premium HDMI cable for 4K at 60 Hz.

## Update 4: consistent fighters, one-cursor select screen, Mike's front + back flex

### Every fighter now plays by the same rules (Flame and Dragon are the reference)
Timing and damage no longer depend on how many frames a sheet has. A move lasts a fixed time and the
sheet's frames are spread over it (`MOVE_TIME_*` in `src/common.h`):

| Move | Duration (all fighters) | Hits during |
|------|------------------|-------------|
| Punch, kick, throw | 0.42 s | 33 %–83 % of the move (0.14 s → 0.35 s) |
| Specials | 0.48 s | 33 %–83 %; the projectile leaves at 50 % (0.24 s) |
| Jump attack | 0.36 s | 33 %–83 % |
| Getting hit (hit-stun) | 0.60 s | – |

* Melee damage 8, projectile damage 10, chip damage through block 1, all the same for everyone.
* Projectiles: the same speeds for everyone (9 px/frame low special, 10.5 high special) and the same 36×36 hit box.
  Daragh's speech bubble is no longer slower or bigger than the others.
* Flame and Dragon's specials now throw a **fireball** (Flame: orange; Dragon: orange for the pyramid
  blast and blue for the bum fireball). Before, they were short-range melee hits.
* Walk speed, jump arc, hurt box, reach and invincibility time were already shared; they are unchanged.
* Idle, walk, jump and victory animations keep their own frame speeds. They look different but don't change the fight.

### Optional: rebuilt Flame / Dragon sheets (download parts 3 and 4)
The original Flame/Dragon sheets have figures of different sizes, and some figures touch each other,
so the old loader cut some frames through a neighbour ("double" figures and slivers). Flame's
punch and kick were also drawn much bigger than his idle pose.
`tools/legacy_fighters.py` cuts every figure out of **your own original sheets** (no new artwork), scales each
sheet so the fighter is the same height as Mike/Daragh/Dec, and puts the feet on one ground line.
It writes `g_*.png`, `portrait.png` and a `sprites.cfg` into `assets/char_flame` and `assets/char_dragon`.

* To use them, copy the `assets/char_flame` and `assets/char_dragon` folders from parts 3 (Flame) and 4 (Dragon) over yours.
  Your original `idle.png`, `walk.png` and other sheets are **not** overwritten.
* To go back, delete `sprites.cfg` from those folders. The game then uses the original sheets, with the new timings and fireballs.
* Flame's block, victory and bum-fireball sheets are upper-body only. For those, the rebuilt version puts the upper body
  on his own guard-stance legs. Dragon's block and victory are built the same way. Check these frames
  before you rely on them.
* Flame's idle is now his standing frames (from `taunt.png`), so he stands like Dragon. He has no
  separate taunt, so the game uses his victory animation instead.
* To rebuild: `python3 tools/legacy_fighters.py --out assets --preview prev` (needs Python 3, numpy, scipy and Pillow,
  plus the original sheets in `sprite_sources/flame` and `sprite_sources/dragon`).

### Mike's victory: front flex, turn around, back flex
Mike's victory animation has 17 frames. He raises both arms into a front double-bicep, turns round, does a back double-bicep, then
turns to face the camera again and repeats (`loop victory 1`).
* The front pose uses his real front photo. His arms are re-posed cut-outs of his own arms, with the racket removed.
* **There is no photo of Mike's back.** The back view is reconstructed: his own front image is mirrored, the shirt print and face are
  painted out and replaced with his own hair, and the image is slightly darkened. The turn is a flat "card flip" squeeze, not a real 3D turn.
* Fixed: the black patch on his shorts where the racket used to be.

# SpriteForge: character sprites for raylib/C games

SpriteForge takes the art you already have and turns it into game-ready sprite sheets. The input can be per-move sprite strips, single frames, or one photo. Every character it builds has:

* a clean cut-out: background removed, no halos or fringes
* one common character height across all moves
* feet on a single ground line, inside a fixed canvas cell
* 14 standard moves, with missing ones filled from what exists
* a `sprites.cfg` that the header-only C loader `include/spriteforge.h` reads

> **SpriteForge never creates new images of real people.** It only cuts out, scales, shifts, and
> procedurally transforms the images you give it: bob, lean, squash, leg swing, tint, glow.
> `generate_character.py` only *prints* prompts. It does not call any image generator.

Moves (fixed order, also the `SF_IDLE..SF_VICTORY` enum):
`idle walk crouch jump punch kick special1 special2 block hit throw jumpattack taunt victory`

---

**Release zips.** Unzip all of them into the same folder; each one contains a `spriteforge/` directory.
* `spriteforge_release.zip`: the tools, the loader, the example, the build scripts, a prebuilt `example_prebuilt.exe`, and the dec and photo samples, including `assets/dec`.
* `part2_flame_src`: source art for the flame sample.
* `part3_assets`: prebuilt `assets/flame` and `assets/daragh`.
* `part4_preview`: screenshots.

Only the first zip is needed to build and run the demo.

## 1. Windows setup (Windows 10, VS Code, MSYS2 UCRT64)

1. Install MSYS2 from https://www.msys2.org, then open **MSYS2 UCRT64** and run:
   ```
   pacman -S --needed mingw-w64-ucrt-x86_64-gcc mingw-w64-ucrt-x86_64-raylib make
   pacman -S --needed mingw-w64-ucrt-x86_64-python mingw-w64-ucrt-x86_64-python-pillow ^
                      mingw-w64-ucrt-x86_64-python-numpy mingw-w64-ucrt-x86_64-python-scipy
   ```
   You can use a normal Windows Python instead: `pip install pillow numpy scipy`.
   Optionally run `pip install rembg` for photos with busy backgrounds.
2. Add `C:\msys64\ucrt64\bin` to PATH, or let the `.bat` files do it. If MSYS2 is installed
   somewhere else, `set MSYS2=D:\msys64` first.
3. Unzip this folder and open it in VS Code. In the terminal (cmd or PowerShell), run:
   ```
   build_release.bat                         :: builds assets\dec from samples_src\dec, then compiles and runs
   build_release.bat flame samples_src\flame
   build_release.bat me C:\photos\me.jpg     :: one photo becomes a full (procedural) move set
   ```
   `build_release.bat` runs four steps:
   1. Builds the sprites with `tools\spriteforge.py`.
   2. Checks the result with `tools\verify_cfg.py`.
   3. Compiles with `build.bat`.
   4. Starts `bin\example.exe`.

   If gcc or raylib is missing, it falls back to `bin\example_prebuilt.exe`, a statically
   linked build that needs no DLLs.

Manual compile (this is exactly what `build.bat` runs):
```
gcc -std=c99 -O2 -Wall example\main.c -Iinclude -o bin\example.exe -lraylib -lopengl32 -lgdi32 -lwinmm
```
In an MSYS2 shell you can also use `make`, `make run CHAR=flame`, `make sprites CHAR=dec`, and `make verify`.
The Makefile has a Linux branch as well. If raylib isn't installed, point it at a raylib source tree with `RAYLIB=path/to/raylib/src`.

**Linux (v5):** with no raylib package, run `make raylib`. It downloads the raylib 5.5 source with Python
(`tools/fetch_raylib.py`, into `third_party/raylib`) and builds `libraylib.a`, and then `make` uses it automatically.
It needs gcc, make and the X11/GL headers, e.g. on Debian/Ubuntu
`sudo apt install build-essential libx11-dev libxrandr-dev libxinerama-dev libxcursor-dev libxi-dev libgl1-mesa-dev`.
Tested: `make raylib && make` -> `bin/example`.

### Example controls
| Key | Action |
|---|---|
| ← → | walk |
| ↓ | crouch |
| ↑ | jump |
| 1 2 3 4 5 6 7 8 9 0 Q W E R | play move 1-14 |
| SPACE | next move |
| F | flip |
| + / - | size |
| TAB | strip view of the current move, with ground line and anchor |
| ESC | quit |

To view two characters, run `bin\example.exe assets\dec assets\flame`.
`bin\example.exe assets\dec --shots outdir` writes preview PNGs and exits.

---

## 2. Building sprites: `tools/spriteforge.py`

```
python tools/spriteforge.py --name NAME --src DIR_OR_PHOTO --out assets/NAME
        [--height 480] [--layout per-move|combined|both] [--glow 255,120,40]
        [--choke 1] [--fill-shirt] [--no-preview]
```

**What goes in `--src`** (file names are the move names; aliases such as `ready_stance`, `fireball`, and `jump_attack` also work):

* `punch.png`: a horizontal strip with any number of poses, on a transparent background or a
  plain/flat one (grey, white, green and so on, gradients included). Poses can sit on several rows.
* `punch/` folder or `punch_01.png, punch_02.png …`: one image per frame.
* a single photo, or a folder with one image: this becomes `idle`, and all other moves are procedural.

**Output written to `--out`:**

| File | What it is |
|---|---|
| `<move>.png` | One strip per move, `frames × frame_w` wide. With `--layout combined` you get one `combined.png` with one row per move instead. |
| `frames/<move>_NN.png` | Every frame as its own image. |
| `sprites.cfg` | The config the loader reads (format below). |
| `contact.png` | Every move with its ground line, anchor and origin, for a quick visual check. |

**Pipeline overview:**

1. **Cut-out.** The background colour is modelled from the image borders (a quadratic fit, so gradients work too). It is flood-filled from the edges, and enclosed background pockets are removed as well. The edge is soft only inside the cut, and colour is decontaminated so the old background doesn't bleed into the edge pixels. Fully transparent pixels are cleaned too. This step is what removes halos.
2. **Pose splitting.** Poses are split by connected components. Effects, hands and other small detached parts are merged back into their pose. Poses are ordered row by row, and touching poses are split. Duplicates, slivers and stray pieces of neighbouring poses are dropped.
3. **One height.** Each source sheet gets one scale. That scale is set by a body-area metric (√solid area) calibrated on the reference move (idle, else walk …). Crouch, jump and kick poses therefore keep their true size and are not stretched to full height.
4. **One ground line.** Every frame is placed so its lowest solid row sits on `ground` and its body centre sits on `anchor_x`. All moves share one cell size.

**Fallback table.** When a move has no source, it is built from the first available source in its row, in order:

| Missing move | Built from (source : operation) |
|---|---|
| idle | walk / block / hit / any : bob (breathing) |
| walk | idle : legswing (procedural leg rig) |
| crouch | idle : squash |
| jump | idle : stretch (crouch, rise, land) |
| punch | throw : same, kick : same, idle : lunge |
| kick | idle : legkick (rigged leg raise), punch : same |
| special1 | throw : glow, punch : glow |
| special2 | kick : glow, punch : glow, special1 : same |
| block | punch : first2 (wind-up frames), idle : leanback |
| hit | idle : hitflash (recoil + red flash) |
| throw | punch : same, special1 : same |
| jumpattack | kick : same, punch : same, jump : same |
| taunt | idle : taunt (sway) / victory : same |
| victory | taunt : same, jump : same, idle : cheer |

A single still image of idle, taunt or victory is animated with a bob, and a single walk still
gets a procedural leg swing. The comment after each `move` line in `sprites.cfg` records
where that move came from (`real`, `idle:legswing` …) and its scale.

### Per-character overrides: `<src>/spriteforge.json`

```json
{
  "height": 480,
  "glow": [255, 140, 40],
  "fill_shirt": false,
  "fill_light_holes": true,
  "choke": 0,
  "moves": {
    "idle":    {"src": "taunt.png"},
    "crouch":  {"pick": [0, 2, 4, 5]},
    "throw":   {"frames": 6},
    "kick":    {"stand_h": 900, "fps": 16, "loop": 0},
    "block":   {"skip": true},
    "special1":{"fill_shirt": false, "drop_stray": false}
  }
}
```

| Key | What it does |
|---|---|
| `src` | Use a different file for this move. |
| `pick` | Keep only these frame indices, after splitting. |
| `frames` | Cut the strip into N equal columns. Use this when poses overlap. |
| `stand_h` | Standing height in source pixels for this sheet. Overrides the automatic scale. |
| `fps` / `loop` | Playback speed, and whether the move loops. |
| `skip` | Ignore the source, for example a bust-only or broken sheet. The move then comes from the fallback table. |
| `fill_shirt` | Paint over see-through holes in the torso, which happen when a white shirt was keyed out with the background. |
| `drop_stray` | Set to false to keep detached bits such as projectiles. |

Default playback (fps / loop): idle 8 / loop, walk 12 / loop, crouch 16, jump 10, punch 15, kick 14,
special1 / special2 12, block 12, hit 10, throw 12, jumpattack 14, taunt 8 / loop, victory 7 / loop.

---

## 3. `sprites.cfg` format

The file is plain text. `#` starts a comment.
```
version 1
name dec
frame 400 536          # cell width, height (all moves share it)
height 480             # standing character height in px
ground 524             # y of the feet inside a cell
anchor_x 200           # x of the body centre inside a cell
move <name> <file> <frames> <frame_w> <frame_h> <fps> <loop 0|1> <row>
move idle idle.png 5 400 536 8 1 0
move punch punch.png 6 400 536 15 0 0
```
`row` is the row of the image that holds the strip. It is 0 for per-move files and the move index for
`combined.png`. Frame `i` of a move is the rectangle `(i*frame_w, row*frame_h, frame_w, frame_h)`.
A `loop 0` move plays once and holds its last frame.

To check a character folder, run `python tools/verify_cfg.py assets/dec`. The check covers:
* the cfg parses
* every sheet exists and is large enough
* every frame has its feet on `ground`

---

## 4. Using it in C: `include/spriteforge.h` (header-only, raylib)

```c
#define SPRITEFORGE_IMPLEMENTATION      /* in exactly one .c file */
#include "spriteforge.h"

SF_Character dec = SF_LoadCharacter("assets/dec");   /* after InitWindow */
float scale = SF_ScaleForHeight(&dec, 300);          /* draw 300 px tall */
SF_Anim anim = {0};
SF_Play(&anim, SF_IDLE);                             /* or SF_FindMove(&dec, "punch") */

/* per frame */
if (SF_Update(&anim, &dec, GetFrameTime()))          /* true when a one-shot move ends */
    SF_Play(&anim, SF_IDLE);
SF_DrawAnim(&dec, &anim, x, groundY, facingLeft, scale);
/* or without SF_Anim: SF_Draw(&dec, SF_PUNCH, t, x, groundY, flip, scale); */

SF_Unload(&dec);
```
`x, groundY` is where the character's feet and body centre land on screen. `flip` mirrors around
that point, so a character never jumps sideways when it turns. `SF_DrawEx` adds a tint, for
example a hit flash. Other calls are `SF_FrameAt` and `SF_MoveDuration`. `SF_ParseConfig` parses a cfg
without loading textures. `SF_STD_MOVE_NAMES` lists the 14 move names.

---

## 5. Adding a new character

1. Create `samples_src/<name>/` and put in it whatever art you have, named by move:
   `idle.png walk.png punch.png …`, folders of frames, or one photo of the person.
   Use art you own or have permission to use. It works best with a transparent or plain background
   that contrasts with the clothes.
2. Need a list of what to make? Run
   `python generate_character.py --name "Dec" --desc "navy suit, white shirt, patterned tie" --photo me.jpg`.
   It creates `sources/dec/` and prints 14 prompts, one per move and file name. You can use them with your own reference
   photo in an image tool of your choice. Any moves you skip are filled in by the fallback table.
3. Run `build_release.bat <name> samples_src\<name>`, or call `python tools/spriteforge.py …` directly.
4. Open `assets/<name>/contact.png`. If something is off, add a `spriteforge.json` with `pick`,
   `frames`, `skip` or `stand_h` and rebuild.
5. In your game, call `SF_LoadCharacter("assets/<name>")`.

## 6. What's in the box

| Path | What it is |
|---|---|
| `tools/spriteforge.py` | Sprite builder (Pillow, numpy, scipy; rembg optional). |
| `tools/verify_cfg.py` | Python version of the C loader's parsing, used to check output. |
| `generate_character.py` | Prints the 14 per-move prompts. |
| `include/spriteforge.h` | The raylib loader. |
| `example/main.c` | Viewer and demo. |
| `Makefile`, `build.bat`, `build_release.bat` | Build scripts. |
| `samples_src/dec`, `samples_src/flame`, `samples_src/photo` | Sample sources from the Padel Wars art. |
| `assets/*` | Prebuilt sample characters. |
| `preview/` | Screenshots captured from the example. |

## 7. Known limits

* Photos need a plain background that contrasts with the subject, a pre-cut transparent PNG, or `pip install rembg`.
  A white shirt on a white wall gets keyed out.
* `fill_shirt` is a heuristic. It can also paint real gaps between the arm and body in the upper torso.
* Sheets that show only a bust (no legs) are not composited onto legs. Skip them, and the fallback table fills those moves.
* The procedural fallbacks are simple 2D transforms: a walk built from one still looks puppet-like.
  Real frames always win.
* Source art should face right (the engine flips at draw time). Left-facing sheets are not auto-detected; the flame sample's special1 faces left.

"""Beginner help: shared by the UI Help tab, `forge.py help <topic>` and HELP.md (tools/make_help_md.py)."""
from __future__ import annotations

TOPICS = {}   # key -> (title, text)


def T(key, title, text):
    TOPICS[key] = (title, text.strip("\n"))


T("quickstart", "Quick start (5 minutes)", r"""
Sprite Forge Studio turns a character into game-ready sprite frames (and, for made-up characters, a 3D model).

0. Once: setup.bat (Windows) or ./setup.sh (Linux) - installs everything into this folder (Help > Install).
1. Open the Studio:  double-click run_studio.bat, or ./run_studio.sh on Linux  (or: python sprite_forge_studio.py)
   v8/v9: the START tab walks you through 6 steps in plain language, including STYLE (faces, colours,
   variants - Help > New in v9). The rest of this
   page describes the Build (advanced) tab, which has every setting.
2. Pick an INPUT MODE at the top-left (Photo, Frames folder, Per-move sheets, Sprite sheet, Text spec,
   Mannequin). Only the fields that mode needs are shown. Hover or click a (?) for an explanation.
3. In the middle, pick a MOVE PRESET (Fighter 14, Kart 12, Gaelic 36, Platformer 10) and tick the moves you
   want. You can change frames / fps / loop per move.
4. Optional: pick a CONSOLE TARGET (NES, SNES, GBA, PS1, N64 ... PS5, PC HD). The normal output is always
   made; the console version is added in out/<name>/console/.
5. Press BUILD. The log shows what happened. When it finishes, the preview plays each move and the contact
   sheet appears. Your files are in  out/<name>/.

Not sure where to start? Press  Help > Example walkthrough  (or the button on the Help tab). It builds the
sample character from examples_char.txt and opens its preview, so you can see every output file.

Command line (same engine):
    forge.bat build --spec examples_char.txt --preset fighter14
    forge.bat build --photo me_front.png --name hero --preset kart12 --console snes
    forge.bat help sprite-sheet          (this help, any topic)
""")

T("install", "Install / setup (Windows & Linux) and forge.py doctor", r"""
You do NOT need to install ffmpeg, Blender or COLMAP by hand. Everything comes from pip into a private .venv:

  Windows 10/11:  double-click setup.bat        (needs Python 3.9+ from python.org, or uv - it tells you)
  Linux / macOS:  ./setup.sh                    (MSYS2 shell on Windows: ./setup.sh too)
Then:  run_studio.bat / ./run_studio.sh   (visual Studio)    forge.bat ... / ./forge.sh ...   (command line)
Options: --core-only (just the core), --no-pose (skip mocap).  Re-check any time:  forge.py doctor

What replaces the old external programs:
  ffmpeg    -> imageio-ffmpeg wheel (contains an ffmpeg binary); OpenCV / PyAV decode as fallbacks
  Blender   -> built-in pure-Python FBX 7.4 writer (sforge/fbx.py): rig, skin weights, one take per move.
               Blender is now optional (--fbx-writer blender, or the Blender exe field).
  COLMAP    -> pycolmap wheel (same COLMAP library, CPU) for scan --run; colmap.exe still used if pycolmap is missing
  MediaPipe -> needs Python 3.9-3.12. tools/setup_pose.py (run by setup) makes venv_pose with Python 3.12 -
               if you have no 3.12 it installs `uv` with pip and uv downloads one (~30 MB) - and fetches the
               pose model with Python (no curl).
Still from the system, only if you want them:
  tkinter   the GUI toolkit. Windows/macOS python.org installers include it. Linux: sudo apt install python3-tk
            (Fedora: sudo dnf install python3-tkinter, Arch: sudo pacman -S tk). doctor prints the command.
  gcc/make + raylib   only for the C example in spriteforge/ (MSYS2: pacman -S mingw-w64-ucrt-x86_64-raylib;
            Linux: your package manager, or  make -C spriteforge raylib  downloads and builds it).

forge.py doctor lists every piece as OK / MISSING / -- (optional) with where it came from and, for anything
missing, exactly which feature that disables. --json gives the same for scripts.
""")

T("modes", "Input modes - which one do I need?", r"""
PHOTO (own pixels)
  You have a photo of your character (front, optional back). The tool cuts the background out, scales the
  figure and stands it on the ground line. Idle uses your real pixels. Every other move is a simple TRANSFORM
  of that one pose (bob, lean, squash, flash) - clearly marked "placeholder" - because ONE PHOTO CANNOT BE
  ANIMATED INTO REAL NEW POSES. Add real frames per move with "Video / frames per move" (walk=walk.mp4 or a
  folder of PNGs).
  Needs: Front photo.        CLI: --photo front.png [--back back.png] [--video walk=walk.mp4]

FRAMES FOLDER
  You already drew/rendered frames elsewhere. Put them in one folder as  walk/01.png walk/02.png ...  or
  walk_01.png walk_02.png ... (folder or file name = move name). They are cut out, scaled to a common
  height and put on one ground line.
  Needs: Frames folder.      CLI: --frames my_frames/

PER-MOVE SHEETS
  One image per move, each a horizontal STRIP of that move's frames (e.g. walk.png = 8 walking poses side
  by side). Frames are found automatically by the transparent gaps between them, or set "Frames across".
  Needs: at least one  move = strip.png.   CLI: --move-sheet walk=walk.png --move-sheet punch=punch.png

SPRITE SHEET (one big sheet)
  A single image with ALL moves: one ROW per move (layout "rows") or one cell per move ("cells").
  Grid "4x8" = 4 rows, 8 columns; blank = auto-detect by transparent gaps. Row 1 = first ticked move, etc.
  Needs: Sprite sheet file.  CLI: --sheet sheet.png --sheet-layout rows --grid 4x8

TEXT SPEC (fictional character)
  Describe a MADE-UP character in a text file (height, build, skin tone, hair, clothes, colours). The tool
  builds a procedural low-poly 3D mannequin (no real person's likeness), animates every move and renders
  the frames, plus model.glb / model.fbx.  Start from examples_char.txt or "New spec from template"; "Edit spec..." opens it in the built-in editor.
  Needs: Spec file.          CLI: --spec char.txt

GAELIC / 3D MANNEQUIN
  No input at all: the default no-likeness mannequin in a team kit (home, away, blue, red, black, gk),
  e.g. the 36 Gaelic football moves with 3D models per kit.
  CLI: --mannequin --preset gaelic36 --kits all

Rule built into the tool: it never generates images of real people with AI. Photos are only transformed
procedurally; for real poses, import frames made elsewhere.

VIDEO -> SPRITES / VIDEO -> MOCAP (3D) / ORBIT VIDEO -> 3D MESH
  Your own video clips become sprite moves (cut out of the footage), or drive the 3D mannequin (motion
  capture), or an orbit video becomes a mesh with console LODs. See the help topics "Video to sprites",
  "Video to motion capture" and "Video to a 3D model".
  CLI: forge.bat video ... / forge.bat mocap ... / forge.bat scan ...
""")

T("outputs", "What each output file is", r"""
Everything goes to  out/<name>/  (the layout never changes; console exports add out/<name>/console/).

atlas.png         The SPRITE SHEET: every frame of every move in one transparent PNG. One ROW per move,
                  frames left to right. All cells are the same size (frame_w x frame_h). If it would be
                  bigger than "max atlas", it continues in atlas_1.png, atlas_2.png ...
atlas.json        A map of atlas.png for engines (Phaser, Pixi, Godot/Unity importers, your own code):
                  for each frame its rectangle {x,y,w,h}, its page, its duration, plus per move:
                  frame list, fps, loop, row. meta.pivot = the feet point. TexturePacker-style "hash" format.
sprites.cfg       The same information as plain text, one line per move (SpriteForge v1 format), read by
                  the C header spriteforge/include/spriteforge.h:
                     move walk atlas.png 8 256 256 10 1 1   = name file frames w h fps loop row
character.ini     Name, frame size, ground_y, pivot_x, scale, standing height, facing=right, and the
                  move list with frames/fps/loop/source. Easy to read from any language.
moves/<move>_<NN>.png   Every frame as its own PNG (walk_00.png, walk_01.png ...). Use these if your engine
                  prefers single images or you want to touch frames up in a paint program.
preview.png       A labelled contact sheet of all moves - just for looking.
build_report.txt  What was rendered, imported or FILLED (placeholder) for each move, plus warnings.
model.glb         (Spec / mannequin modes) Rigged, skinned 3D model with one animation clip per move.
                  glTF binary: opens in Blender, Godot, Unity (with glTFast), Three.js, Unreal (glTF plugin).
model.fbx         Same model as binary FBX 7.4 (built-in writer, no Blender) - Unity / Unreal / Maya / Blender.
model_<kit>.glb   Extra team-kit variants (--kits).
console/          Only when a console target is chosen - see "Console targets".
""")

T("sprite-sheet", "How to use a sprite sheet (plain language)", r"""
A sprite sheet is just ONE picture that contains many small pictures (frames) on an invisible grid.
Your game shows one cell at a time, very fast, and that is the animation - like a flip book.

THE GRID
  Every cell is the same size: frame_w x frame_h (e.g. 256 x 256). Cell (column c, row r) starts at
      x = c * frame_w        y = r * frame_h
  In atlas.png each ROW is one move: row 0 = idle, row 1 = walk ... (the order is in sprites.cfg /
  atlas.json / character.ini). A move with 8 frames uses columns 0..7 of its row.

PLAYING A MOVE (fps and loop)
  fps = frames per second. walk at 10 fps -> show the next column every 1/10 s.
      frame = floor(time_since_move_started * fps)
  loop = 1 (idle, walk, run): wrap around   frame = frame % frames
  loop = 0 (punch, jump, hit): stop on the last frame   frame = min(frame, frames - 1)
  then go back to idle (or whatever your game logic wants).

PIVOT AND GROUND LINE (why the character doesn't "jump around")
  Every frame has the character's feet on the same line y = ground_y, centred at x = pivot_x
  (e.g. 128, 240 in a 256 x 256 cell). This point is the character's POSITION in your game:
      draw_x = player_x - pivot_x          draw_y = player_y - ground_y
  so the feet always land exactly on player_x, player_y, no matter which frame is shown.
  Jump frames are drawn higher inside the cell (feet above the line) - never below it.

FACING LEFT (flipping)
  All sprites face RIGHT. To face left, draw the same cell mirrored horizontally (negative width in raylib,
  flipX in Unity/Godot, scale.x = -1). Because the pivot is centred, mirroring keeps the feet in place:
  if pivot_x is not exactly the centre, use  draw_x = player_x - (frame_w - pivot_x)  when mirrored.

SCALE
  Draw the cell at any scale; multiply pivot_x / ground_y by the same scale. For pixel art use
  nearest-neighbour filtering (no blur).

Copy-paste code for raylib, Unity, Godot, Unreal and SNES/GBA-style tile banks: topic "engines".
""")

T("engines", "Engine examples (copy-paste)", r"""
--- raylib C with spriteforge.h (bundled: spriteforge/include/spriteforge.h) -----------------------------
    #include "raylib.h"
    #define SPRITEFORGE_IMPLEMENTATION
    #include "spriteforge.h"
    int main(void) {
        InitWindow(800, 450, "hero");                                  /* window first (textures need GPU) */
        SF_Character hero = SF_LoadCharacter("out/nova_vance");       /* reads sprites.cfg + atlas pages */
        SF_Anim anim = { 0 };
        SF_Play(&anim, SF_FindMove(&hero, "walk"));
        bool left = false;
        while (!WindowShouldClose()) {
            if (IsKeyPressed(KEY_SPACE)) SF_Restart(&anim, SF_FindMove(&hero, "punch"));
            if (SF_Update(&anim, &hero, GetFrameTime()))              /* true when a one-shot move ended */
                SF_Play(&anim, SF_FindMove(&hero, "idle"));
            left = IsKeyDown(KEY_LEFT);
            BeginDrawing(); ClearBackground(DARKGRAY);
            SF_DrawAnim(&hero, &anim, 400, 380, left, 1.0f);           /* x, feet y, flip, scale */
            EndDrawing();
        }
        SF_Unload(&hero); CloseWindow();
    }
  (Full demo: spriteforge/example/main.c.  Build on Windows: spriteforge\\build.bat)
  Without the header - plain raylib:
    Rectangle src = { col * fw, row * fh, facingLeft ? -fw : fw, fh };
    DrawTexturePro(atlas, src, (Rectangle){ x - pivot_x, y - ground_y, fw, fh }, (Vector2){0,0}, 0, WHITE);

--- Unity / Godot PLUGINS (v9, in plugins/) -------------------------------------------------------------
  Unity: copy plugins/unity/com.spriteforge.importer into Packages/ (or Package Manager > Add from disk),
         copy the build folder under Assets/, then Tools > Sprite Forge > Import Build Folder...  -> sliced
         sprites (feet pivot), <name>_data.asset, .anim clips + .controller, <name>.prefab with hurt / hit
         BoxCollider2D children driven by framedata.json; maps/atlas_normal.png -> _NormalMap for 2D lights.
  Godot 4: copy plugins/godot/addons/sprite_forge into your project's addons/, enable it (Project Settings >
         Plugins), then Project > Tools > Sprite Forge: Import Build Folder... -> <name>_frames.tres
         (SpriteFrames) + <name>.tscn (SpriteForgeCharacter: AnimatedSprite2D with Hurtbox / Hitbox Area2D,
         hit_active signal, normal maps as CanvasTexture). Reads atlas.json or a multi-character pack.json.
  Help > Plugins has the details and the honest limits.

--- Unity (C#) by hand -----------------------------------------------------------------------------------
  Import atlas.png: Texture Type = Sprite (2D and UI), Sprite Mode = Multiple, Filter = Point (pixel art),
  Sprite Editor > Slice > Grid By Cell Size = frame_w x frame_h, Pivot = Custom (pivot_x/frame_w,
  1 - ground_y/frame_h). Then drag a row's sprites into the scene to make an Animation clip (set its fps).
  Or in code (frames sliced in order, frames per row known from atlas.json):
    public Sprite[] walk; public float fps = 10; SpriteRenderer sr; float t;
    void Update() { t += Time.deltaTime; sr.sprite = walk[(int)(t * fps) % walk.Length];
                    sr.flipX = facingLeft; }
  3D: drop model.fbx (or model.glb with glTFast) into Assets; each move is an AnimationClip.

--- Godot 4 (GDScript) -----------------------------------------------------------------------------------
  AnimatedSprite2D > SpriteFrames > "Add frames from sprite sheet" > atlas.png, H = frames in the row,
  V = number of rows, pick that row's cells, set the fps and loop. Set offset so the feet are the origin:
      offset = Vector2(frame_w/2 - pivot_x, frame_h/2 - ground_y)  (centered = true)
  Code:
    $Hero.play("walk"); $Hero.flip_h = facing_left
  3D: import model.glb directly; AnimationPlayer contains one animation per move.

--- Unreal / generic engines -----------------------------------------------------------------------------
  Unreal Paper2D: import atlas.png, right-click > Sprite Actions > Extract Sprites (Grid, cell = frame size),
  then Create Flipbook per row; set the sprite pivot to Custom (pivot_x, ground_y). 3D: import model.fbx
  (skeletal mesh + animations).
  Generic: parse atlas.json - frames[name].frame = {x,y,w,h}, animations[move] = {frames, fps, loop}.

--- Pure C for SNES / GBA-style tile banks (console/<name>_<console>.h) ----------------------------------
  The console export splits each frame into 8x8 tiles, de-duplicates them (also mirrored copies) and gives
  you: a palette, tile banks (raw tile data in the console's native format) and a tile map per frame.
    #include "nova_vance_snes.h"      /* palette, banks, maps, frames, anims */
    /* once per bank change: copy tiles to sprite VRAM, palette to sprite CGRAM/PAL RAM */
    upload_tiles(nova_vance_snes_banks[f->bank].tiles, nova_vance_snes_banks[f->bank].count * 32);
    upload_palette(nova_vance_snes_palette, 16);
    /* each frame: one 8x8 hardware sprite per non-empty cell */
    const SFTAnim  *a = &nova_vance_snes_anims[move];
    const SFTFrame *f = &nova_vance_snes_frames[a->first + (tick * a->fps / 60) % a->count];
    int n = 0;
    for (int ty = 0; ty < f->th; ty++)
      for (int tx = 0; tx < f->tw; tx++) {
        uint16_t e = nova_vance_snes_maps[f->map + ty * f->tw + tx];
        if (e == SFT_EMPTY) continue;
        int cx = left ? (f->tw - 1 - tx) : tx;                  /* mirror the grid to face left */
        int hf = ((e & SFT_HFLIP) != 0) ^ left;                  /* and flip each tile */
        set_oam(n++, x - f->pivot_x + cx * 8, y - f->ground_y - f->rise + ty * 8, SFT_TILE(e), hf);
      }
  set_oam() / upload_*() are your platform's (PVSnesLib, libtonc, devkitPro, gbdk, cc65 ...). NES: tiles are
  CHR (2bpp, 16 bytes each); GB: 2bpp; SMS: 4bpp planar; SNES: 4bpp SNES-planar; Genesis/GBA/DS: 4bpp packed.
""")

T("views", "Multi-view: front / side / back / 3/4 and 8 directions", r"""
Many games need the character from more than one side: kart racers turn the camera around the driver,
top-down RPGs walk in 8 directions, beat-'em-ups show a back view. Sprite Forge calls each side a VIEW.

View names say which way the character FACES ON SCREEN (angle = camera yaw around the character):
    front 0     front_right 45 (3/4)   right 90 (side, facing image-right)   back_right 135
    back 180    back_left 225          left 270 (side, facing image-left)     front_left 315
(aliases: side = right, side_left = left, 3/4 = front_right, rear = back, or just the angle: 45=...)

PHOTO mode - give the photos you have:
    Studio: Front photo + Side photo (+ 'Side faces left' if needed) + 3/4 photo + Back photo
    CLI:    forge.bat build --photo front.jpg --side side.jpg --back back.jpg --name zed
            forge.bat build --photo front.jpg --view back=back.jpg --view 45=threeq.jpg --view left=walk_left.mp4
  A view's source can also be a folder of frames or a video (its frames become that view's idle).
  Every view is cut out separately and scaled so the figure has the SAME height, the same top line and
  the same ground line in every view (and the widest view still fits the frame).

Views you did not photograph:  Output views = front,right,back,left  or  billboard8
  * mirrored:  left from right, front_left from front_right, back_left from back_right (exact mirror -
    logos/text come out back-to-front)
  * filled:interpolated  - the nearest real view squeezed horizontally (a quick stand-in, NOT a real
    new angle). Real photos of more sides always look better.
  Every filled view is flagged in atlas.json ("filled": true), sprites.cfg ('view ... mirrored:right'),
  character.ini [views] and build_report.txt. Nothing is invented by AI.
TEXT SPEC / MANNEQUIN: every view is rendered for real by the 3D renderer (camera yaw = view angle).

Moves per view: each views/atlas_<view>.png has exactly the same rows/columns as atlas.png. For
photo views only idle is real (still or video); the other moves are placeholders from that view's
still. 'view_moves' in a profile (or --view-moves idle,walk) chooses which moves animate per view;
the rest are still copies.

Outputs (in out/<name>/):
    views/<view>/<move>_NN.png    every frame per view
    views/atlas_<view>.png        sheet per view (same layout as atlas.png)
    turnaround.png                grid: one row per view, one column per move (middle frame)
    turnaround_preview.png        the same with labels, green = real, yellow = mirrored, red = filled
    billboard8.png                8 directions in one row, angle order (billboard8 / 8 views)
    sprites.cfg                   view <name> <angle> <file> <source>
    atlas.json                    "views": {name: {angle, source, filled, images, moves, rows}}
    character.ini                 views = front,right,...   and a [views] section
Bust cut for seated drivers: View cut = 0.55 keeps head-to-lap, like TurboTumble64's racers.
  All views share ONE scale. If one view is wider than the frame (e.g. the side view of a driver holding
  a steering wheel), every view is drawn smaller so it fits - build_report.txt says by how much.
""")

T("profiles", "Output profiles - make the output fit ANY game", r"""
A profile is a small JSON file in profiles/ that says what a TYPE of game needs: moves, views, frame
size, which images to make and which description files (manifests) to write. The tool has no
game-specific code - change the profile and the output changes.

Shipped profiles (forge.bat profile list):
    generic_2d    atlas + Godot SpriteFrames (.tres) + Tiled tileset (.tsx) + Unity-style JSON, front/back
    fighter14     2D fighter: the 14 fighter moves, side-on (Egyptian Fighter style)
    kart_racer    kart racer that draws its own kart (TurboTumble64 style): 8 angles of the seated driver,
                  sprite.png (4x2 grid of 512x640, angles 0,45..315), win.png, portrait.png, character.ini
    gaelic36      sports game: 36 Gaelic football moves + Tiled tileset
    platformer    side-scroller: 10 basic moves + Godot / Unity / Tiled files
    topdown8dir   top-down RPG: idle/walk/run in 8 directions (views/atlas_<view>.png, billboard8.png)
    retro_nes / retro_snes / retro_gba   small frames + that console's export (palette, tiles, C header)

Use one:  Studio: '2. Output' > Profile (fills the fields; you can still change any of them)
          CLI:    forge.bat build --photo f.jpg --side s.jpg --back b.jpg --profile kart_racer --name zed
                  --set "tagline=Fast and furious" --set speed=4      (template variables)
Make one: Studio: 'Create profile...'  (name, start-from profile, frame, views, extra files)
          CLI:    forge.bat profile new my_game --from platformer --frame 96x96 --manifest godot_spriteframes
          Check:  forge.bat profile validate my_game        Show: forge.bat profile show kart_racer

What a profile can contain (all optional):
    "moves": "kart12" or ["idle", "walk", "dash=sprint:8:14:loop"]
    "frame": [512, 640], "figure_h": 0.97, "ground_y": 636      (numbers <= 1 = fraction of frame height)
    "views": "billboard8" or ["front", "right", "back"], "view_cut": 0.55, "view_moves": ["idle"]
    "prop": "none", "console": "snes", "yaw": 90, "gifs": false, "vars": {"speed": "3.0"}
    "images": grid (views side by side, e.g. sprite.png 4x2), frame (one cell, e.g. win.png),
              portrait (square head crop), frames (copy frames into your own folder/file names)
    "manifests": ini (any key = value file), template (free text with per-move / per-view lines),
              json (any JSON with {placeholders}), godot_spriteframes, tiled_tsx, unity_json
Placeholders: {name} {display_name} {frame_w} {frame_h} {ground_y} {pivot_x} {scale} {atlas} {columns}
{moves_csv} {views_csv} {face_x} {face_y} {date} {version} + your vars; per move: {move} {frames} {fps}
{loop_word} {row} {image} {duration_ms} {first_tile}; per view: {view} {angle} {image} {source} {filled}.
sprites.cfg / atlas.json / character.ini are always written; a profile file with the same name replaces it.
""")

T("videos", "Tutorial videos", r"""
Short screen recordings of the real Studio (in the videos/ folder next to this help; play them with any
video player):
    01_photo_to_game.mp4        photo (+ side/back) -> sprite sheet -> installed in a kart game
    02_text_to_character.mp4    text description -> character -> sprite sheet + 3D model (GLB/FBX)
    03_using_the_sprite_sheet.mp4  what the files are, loading atlas.png in an engine, console export
    04_video_to_game.mp4        your own clips -> sprites, mocap (GLB/FBX) and orbit scan -> LODs
    05_setup_windows_linux.mp4  v5 setup.bat / setup.sh, what replaced ffmpeg/COLMAP/Blender, Check setup (doctor)
If the folder is missing, the videos come as a separate download (sprite_forge_videos_v3.zip).

What they show (all real screen capture, sped up only while a build runs - marked '>> 6x'):
    01  Photo mode, Teal Racer: front photo + side + back (the side/back in the video are SYNTHETIC
        mannequin renders, labelled, standing in for real photos), profile kart_racer, billboard8 views,
        BUILD, then the folder copied into TurboTumble64 and raced - select screen + chase camera.
    02  Text spec mode: the built-in spec editor (Edit spec...), profile platformer, GLB + FBX, BUILD,
        play moves, then model.fbx re-imported in Blender to show the rig and takes.
    03  Help > sprite sheet + profiles, fighter14 profile + SNES console target, BUILD, the console
        files + verify_console.py result, then the sheet in Egyptian Fighter via tools/export_ef.py.
    05  Help > Install / setup, the Check setup (doctor) table, then a GLB + FBX build on a machine
        without Blender (the FBX comes from the built-in writer).

Make your own (Linux, needs Xvfb; ffmpeg comes from the imageio-ffmpeg pip package):
    python3 tools/record_tutorial.py tools/tutorials/01_photo_to_game.json
  A plan is a list of segments (title cards, stills, the studio driven step by step, a game driver).
""")

T("consoles", "Console targets (what each preset does)", "@CONSOLES@")

T("fields", "Every field explained", "@FIELDS@")

T("troubleshooting", "Troubleshooting", r"""
"Nothing happens / Python not found"   Install Python 3.9+ from python.org (tick "Add to PATH"), then run
                                       setup.bat (Linux: ./setup.sh). Then  forge.bat doctor  shows what is ready.
"No module named tkinter" (Linux)      sudo apt install python3-tk  (dnf: python3-tkinter, pacman: tk). The CLI works without it.
"no video decoder"                     Run setup again (installs imageio-ffmpeg), or pip install imageio-ffmpeg.
FBX looks wrong in an engine           FBX is written by the built-in writer. Compare with model.glb; or try
                                       --fbx-writer blender if Blender is installed, and tell us.
Background not removed well            Use a photo on a plain background, or a PNG that already has
                                       transparency (Cutout = alpha). Cutout = rembg uses an optional AI
                                       background remover (segmentation only).
Character looks cut off                Raise frame W/H or lower "Figure px".
Moves say "FILLED / placeholder"       There were no source frames for that move. Add frames for it
                                       (video, frames folder, per-move sheet) for real poses.
Console export looks mushy             Old consoles have tiny sprites and few colours: try dithering off,
                                       fewer moves, or a larger target (SNES/GBA instead of NES).
"N tiles do not fit one bank"          Normal for big move sets: games swap tile banks per move
                                       (CHR bank switching / DMA). Each frame says which bank it uses.
""")
T("video", "Video to sprites (Video -> sprites mode)", r"""
Turn YOUR OWN video clips (one per move) into sprite frames. Only use footage you shot yourself or have the
right to use, of people who agreed to it.

What it does, step by step (all automatic, each step can be overridden):
  1. decode      ffmpeg reads the clip (optionally only  @start-end  seconds)
  2. camera      works out whether the camera is static, handheld (small shake) or TRACKING a runner
                 ("running in frame": the person stays in the middle, the background slides past)
  3. background  builds a clean background: median of all frames (static), an empty "plate" (the first
                 frames before the person walks in), a chroma screen (green/blue), or rembg if installed.
                 Tracking shots: the background is stitched into a moving panorama per depth layer
                 (far / middle / ground move at different speeds).
  4. cut out     difference against that background + shadow removal + clean-up -> transparent frames
  5. timing      LOOPS (walk, run): finds one exact cycle by frame similarity, so the loop has no jump.
                 ONE-SHOTS (jump, punch): finds where the action starts and ends.
  6. slow motion if the clip has fewer frames than you asked for, in-between frames are made by optical flow
                 (Slow motion x 2 = twice as many in-betweens). Shoot at 60 fps or more for fast moves.
  7. normalise   every frame scaled to the same standing height and put on one ground line, then the
                 normal build: moves/<move>_NN.png, atlas, profiles, console exports (HD + SNES/GBA ...).

Clip format:   move:frames=path.mp4      e.g.  walk:8=C:/clips/walk.mp4
               add  @2.0-3.5  to use only that part,  #bg=chroma,camera=static  to override per clip.
CLI:  forge.bat video --clip walk:8=walk.mp4 --clip jump:12=jump.mp4@1-2.5 --name hero --consoles snes,gba

Filming tips: side-on, whole body in frame, camera at hip height, plain background if you can, 2-3 full
cycles for loops, bright light (less motion blur), 60/120 fps for runs and kicks.
Limits (honest): loose hair/clothes and shadows on busy floors give ragged edges; a moving camera with a
crowd or trees behind is the hardest case (check out/<name>_video/_debug/*.png); the person must not leave
the frame; overlapping limbs stay overlapped - this is a cut-out of the real footage, not a redraw.
""")

T("mocap", "Video to motion capture (Video -> mocap mode)", r"""
Use YOUR OWN clip to drive the 3D mannequin: the body pose is tracked in every frame, fitted onto the
mannequin skeleton and baked as an animation. Result: model.glb / model.fbx with the move as a clip, plus
sprites rendered from the mannequin (any angle, any kit, any console). No real person's looks are copied -
only the motion.

Pipeline: MediaPipe Pose (33 body points per frame, runs on CPU) -> gap fill + smoothing -> depth from bone
lengths -> joint-angle fit (inverse kinematics) onto the mannequin's 19 bones -> loop / action detection ->
keyframes -> forge.py build --mocap.

Needs MediaPipe, which supports Python 3.9-3.12 only (not 3.13). setup.bat / ./setup.sh does it for you; or
run  python tools/setup_pose.py  : it makes venv_pose\ with Python 3.12 (downloaded with uv if you have none),
pip-installs mediapipe and downloads models/pose_landmarker_full.task (add --heavy for the heavy model).
The Studio finds venv_pose automatically (or set SFS_POSE_PYTHON).
CLI:  forge.bat mocap --clip walk:8=walk.mp4 --clip punch:10=punch.mp4 --name hero --consoles snes

Accuracy we measured on test clips with known answers: walk hip/knee angles within ~6-13 degrees, runs
13-26 degrees (fast limbs blur, knees come out less bent). Check out/<name>_mocap/<move>_check.png: top row =
tracked points, bottom = fitted mannequin. Side-on clips work best; arms behind the body and spins are weak.
Finger, face and foot roll are NOT captured. Clean up in Blender if you need game-quality animation.
""")

T("scan", "Video to a 3D model (Orbit video -> 3D mesh)", r"""
Photogrammetry: walk slowly AROUND a still object (or a person who stays completely still) while filming.
This is NOT one-click and the quality depends almost entirely on the capture.

What the Studio does:
  1. picks the sharpest frame in each time slot -> out/<name>_scan/images/  (+ run_colmap.bat and notes for
     Meshroom / RealityScan, which give better, textured results)
  2. "Run COLMAP + mesh" (pycolmap pip wheel, or colmap on PATH): camera positions (structure from motion, CPU), then our own
     CPU depth-map step (OpenCV stereo, checked between neighbouring views) fused into a surface, floor cut off
  3. makes console LODs: one GLB + OBJ per console triangle budget (PS1 600, N64 900, PS2 5000, PS4 40000 ...)
     with vertex colours, and scan_preview.png.
  "...or finished mesh": skip 1-2 and just make LODs from a mesh you made elsewhere.

Capture guide: 60-120 frames over 1-2 full circles at two heights; steady pace, no fast turns; matte,
textured surfaces (shiny, glass, black or plain white things fail); even light, no moving shadows; fill the
frame with the object; keep the background still (no people walking).
On our synthetic test (textured mannequin, 72 views, CPU only) the mesh was within ~1.3 cm on average of the
true 1.75 m figure and took ~40 s. Real footage of a person is much harder: any movement smears the result.
The CPU mesh has vertex colours only (no high-res texture) - for a hero-quality textured model use Meshroom
(free, NVIDIA GPU) or a phone app on the images/ folder, then bring the mesh back here for LODs.
CLI:  forge.bat scan --video orbit.mp4 --run --height 1.75 --name statue
      forge.bat scan --mesh texturedMesh.obj --name statue --budgets ps1=600,ps2gc=5000
""")

T("library", "Library: your FBX / GLB rigs and animations as templates", r"""
The Library tab keeps rigs (mesh + skeleton), animations (skeleton + clips) and kits (colour sets) that you can
use as templates instead of the built-in mannequin. It lives in  library/  next to forge.py (or $SFS_LIBRARY).

ADD
  Library tab > Add FBX / GLB...   (or drop files in library/inbox/ and press Rescan)
  forge.py library add my_hero.fbx --name my_hero --spdx CC0-1.0 --author "Me" --redistribution yes
  Reads FBX 7.x binary and ASCII and glTF/GLB with our own pure-Python readers (no Blender, no assimp needed;
  assimp / trimesh are only used as a fallback if they are installed). Mesh, skin weights, bind pose,
  materials + embedded textures and every animation take are imported, converted to metres, Y up, facing +Z.

BONE MAP
  Each asset gets bonemap.json: canonical names (hips, spine, chest, neck, head, upperarm_L, forearm_L, hand_L,
  thigh_L, shin_L, foot_L ...) -> the rig's bone names. Mixamo (mixamorig:*), Rigify / Blender (DEF-*, *.L),
  Unity Humanoid / generic (LeftUpperArm, Hips ...) are recognised automatically; anything else is matched by
  name patterns and by the shape of the skeleton. "Bone map..." shows it on the skeleton; unmapped bones
  (fingers, twist, end bones) simply follow their parent.  CLI: forge.py library bonemap NAME --set head=MyHead

USE AS TEMPLATE
  Select a rig > "Use as template" -> Build tab in mode "Library rig". Pick moves, profile, console, views and
  kit as usual and press BUILD. The 3D output (model.glb / model.fbx, one take per move) is the library rig.
  CLI: forge.py build --rig sample_lanky --profile fighter14 --kit sample_gold_black --consoles gba
       forge.py build --rig C:/models/hero.fbx --moves idle,walk,run   (a file: imported on the fly)

WHICH CLIP PLAYS A MOVE  (column "library clip" in 3. Moves, or --clip / "clip_map" in a profile)
  1. what you chose: --clip kick=sample_moves:hop@speed=1.2,trim=0.1-0.8,once  (trim in seconds)
  2. a mocap capture for that move (forge.py mocap ... --rig NAME)
  3. a clip with the move's name in the rig itself
  4. a clip with that name in another library asset - retargeted
  5. the built-in procedural motion - retargeted from the mannequin
  6. rest pose (reported as filled:rest-pose)
  The build log lists the source of every move.

RETARGETING
  Clips move between rigs of different proportions through the canonical bone map: bone directions are copied
  with rest-pose compensation (A-pose / T-pose differences), hip height and travel are scaled by leg length,
  feet are put back on the ground. Root motion: keep / inplace / root.
  forge.py retarget sample_moves:wave,bow my_hero --save --out my_hero_moves.glb
  Limits: no IK / foot-locking (feet can slide a little on very different legs), only the first animation
  layer of an FBX, blend shapes and constraints are ignored, fingers follow the hand.

PACKS  (.sfpack = zip with pack.json, rigs/, animations/, kits/, thumbnails/, LICENSES.txt)
  Export pack... / forge.py library pack my.sfpack NAME ...    Install pack... / forge.py library install X.sfpack
  forge.py library verify X.sfpack  checks the manifest, every file's SHA-256 and every licence record.
  Install always shows the licences and needs your acknowledgement. See Help > Licensing.

The bundled starter pack (packs/sfs_starter_cc0.sfpack, already installed in library/) is our own synthetic
content - CC0 1.0, no likeness of anyone: sforge_mannequin, sample_chibi, sample_lanky, sample_stocky,
sample_moves and three kits.
""")

T("licensing", "Licensing: what you may put in a pack", r"""
Every library asset has a licence record (licence.json): SPDX id (e.g. CC0-1.0, CC-BY-4.0) or a custom licence
text, author, source URL, redistribution yes / no / unknown, and the attribution text to show.

  Using an asset yourself is always allowed by the Studio (your own files, or files whose terms allow your use).
  PUTTING an asset in a pack (sharing it) is only allowed if its record says redistribution = yes.
  Assets marked no or unknown are refused - unless you confirm "I own the rights" and give your name.
  That confirmation, your name and the date are written into the pack and shown to everyone who installs it,
  so only use it for things you made yourself.
  Installing shows every asset's licence and installs nothing until you acknowledge them.

THIRD-PARTY CHARACTERS AND ANIMATIONS
  Terms differ per store and change over time - read the terms of the place you got a file from.
  Mixamo, for example, lets you use its characters and animations in your own projects and games, but its terms
  do not allow redistributing the raw files as an asset library - so keep downloaded Mixamo FBX files local
  (redistribution = no) and share only your finished game / renders. A clip retargeted from a Mixamo
  animation onto your own rig is still Mixamo animation data - mark it no as well, and do not use the
  "I own the rights" confirmation for it. (Adobe's Mixamo FAQ: helpx.adobe.com/creative-cloud/faq/mixamo-faq.html) Store assets (Unity Asset Store, Sketchfab,
  CGTrader ...) each have their own licence; CC-BY needs the attribution text; "editorial" or "personal use"
  licences usually forbid games or sharing. When in doubt: redistribution = unknown, and it stays local.

WHAT WE SHIP
  Sprite Forge Studio bundles no third-party characters or animations. The starter pack is our own synthetic
  content released as CC0 1.0. Files you import stay yours; the Studio never uploads anything.
  This is practical guidance, not legal advice.
""")

T("v7", "New in v7: material slots, animation files, equip, MakeHuman, your own mesh", r"""
MATERIAL SLOTS - every 3D output (model.glb / model.fbx, library exports, anim files) names its materials
  Skin_Mat, Jersey_Mat, Shorts_Mat, Socks_Mat (+ Trim_Mat, Hair_Mat, Shoes_Mat when present). A mesh with one
  unnamed material is split by bone region automatically (--material-split auto). --material-slots core4 gives
  exactly the 4 core slots; keep = materials as imported. Empty slots are still written so engine code can rely on them.
SEPARATE ANIMATION FILES - forge.py anim-export --rig NAME --out DIR (or build --anim-export, GUI "Separate anim
  files"): character_base.glb (+ .fbx) with the mesh, one anim_<move>.glb per move (armature + 1 take) and
  manifest.json. Bones are ordered parents-first and names are cut to 31 bytes for raylib (LoadModelAnimations);
  --verify reloads every file and compares the motion. examples_raylib3d/anim_viewer.c is a raylib 5.5/6.0 viewer.
CLEAN IMPORTS - library add stands Z-up / lying / centimetre files upright (+Y up, metres, grounded), fixes takes
  keyed on a Z-up armature and drops duplicate meshes (Body.001, *_LOD1 copies). Everything is listed in the report.
  --orient off / --dedupe off turn it off; --blender-cleanup runs Blender first if you have it.
MESHY / UE5 / UNITY - a Meshy download (.zip with FBX/GLB + textures) imports as is; Mixamo (Meshy uses it),
  Unity humanoid, Unreal UE4/UE5 (pelvis, spine_01, calf_l ...), Rigify and MakeHuman bone names are detected.
  --preset meshy-free (CC BY 4.0 + credit line) or --preset meshy-paid (private: redistribution no). Meshy
  animation-library clips are kept out of packs by default (--meshy-anims-redistributable yes to confirm).
EQUIP - library outfits (skinned to a skeleton, re-fitted to any rig, hide the body under them) and props (rigid,
  on a socket: hand_r hand_l head back hip foot_r foot_l). Build: --outfit sample_vest --attach sample_sword@hand_r
  --slot-color Jersey=#c8102e, or the GUI "Equip..." button. Add your own: library add FILE --kind outfit|prop.
  Each item's licence is written to build_report.txt.
MAKEHUMAN MODE - one-time: forge.py human --setup (downloads the CC0 MakeHuman assets, ~28 MB, no MakeHuman code).
  Then forge.py human --gender female --age 30 --muscle 0.7 --skeleton game_engine --name hero (library rig), or
  build --human "gender=1,age=25,skeleton=game_engine", or the GUI "MakeHuman body" field (Gaelic / 3D mannequin
  mode). Skeletons: default 163, default_no_toes 135, game_engine 65 (fingers), body 26. Without the assets the
  parametric mannequin is used and the report says so.
YOUR OWN MESH (experimental) - there is no text-to-3D in the Studio (it would need a paid or web service). Make or
  buy a mesh anywhere, then: forge.py autoskin mesh.obj --skeleton sample_lanky --name mine --spdx ... (weights by
  distance to the bones). It is a quick start, not a replacement for Blender weight painting or Mixamo auto-rig.
""")


T("v8", "New in v8: Start wizard, three goal tabs, side-on turn, faster builds", r"""
START TAB (new front page). Five steps, Back / Next at the bottom:
  1 Start from      photo, video clips, frames / sheets, make a character, library rig, text description
  2 Your source     pick the file(s). Photo: 'Cut out person' makes the transparent cut-out + pose points.
  3 Look & view     which way the character faces (0 front, 90 side-on, 180 back, 270 other side, or any
                    angle) with 'Preview this view'. Photo only - 3D characters use Camera yaw instead.
  4 What to make    three tabs - they add up, one build makes all of them:
                      HD sprite sheet         game / move set + the MOVE PICKER (tick moves, frames, fps,
                                              'Add a move' from other presets; warns if a game needs a move)
                      Retro console sprites   none, or one of 18 consoles (Atari 2600 ... PS5) + dither
                      3D files                GLB / FBX / per-move animation files (3D characters only)
  5 Build           Quick preview (seconds) or Final. 'Same as typing' shows the exact forge.py command.
                    'Export to a game folder...' writes an Egyptian Fighter char_<name>/ folder.
The Build (advanced) tab still has every setting; the Start tab only fills it in.

SIDE-ON FROM A PHOTO (turn). From ONE front photo Sprite Forge estimates the body's depth (MakeHuman CC0
body template, a simple relief, or your own side photo / video frame), projects your photo onto the front
and turns it. The front is your real pixels; the side, back and face profile are ESTIMATED. A real side
photo (Side reference) makes the side view much closer to the person.
    forge.bat cutout photo.jpg --person right --out cut
    forge.bat turn cut --yaw 90 --out turn                       (compare_90.png: front vs turned)
    forge.bat build --photo cut\cutout.png --landmarks cut\landmarks.json --turn 90 --preset fighter14

SPEED. Unchanged moves are re-used from a cache (out/<name> + a per-user cache), frames render on all CPU
cores, PNGs are saved in the background. Quick preview = half size, 4 frames a move, no 3D / console files.
    --quality draft     quick preview from the command line
    --no-cache          force a full rebuild
    forge.bat cache stats | clear | prune
""")


T("v9", "New in v9: faces, colours, variants (+ extras)", r"""
The Start tab has a new step 4 STYLE with three tabs - the same settings as the forge.py flags shown below.

FACES - expressions and mouth shapes
  neutral, happy, angry, hurt, shout, taunt and blink, chosen PER MOVE: Automatic picks punch/kick = angry,
  specials = shout, hit / ko = hurt, taunt = taunt, victory = happy; change any move in the list
  (--expr-map punch=shout,victory=happy) or use one face everywhere (--expressions happy). Looping
  neutral moves blink once per loop (--no-blink to stop). faces.png + faces/ = a HUD portrait of every
  expression and mouth shape. Talking: --talk "Ready to fight" -> talk/talk_strip.png + talk.json (frame
  timing). Mouth shapes (rest, M/B/P, A/I, E, O, U, F/V, L) come from the LETTERS, not speech recognition.
  3D characters: a morphed face mesh (also morph targets in model.glb).  PHOTO characters: procedural warps
  and small overlays of YOUR photo's own face - ESTIMATED, subtle on small faces, very subtle on side-on
  (turned) views, none on back views.

COLOURS - palette swaps, region masks, texture overlays, one-click sets
  One click: team_red / team_blue / ... / kerry / dublin / mayo / cork / galway / egypt_gold / ninja /
  villain / ghost / fire / ice / p2_alt (hue shift)   (forge.py sets lists them; save your own).
  Per region: skin hair top trim bottom socks shoes accessory  (--recolor "team_blue;hair=black").
  Overlay on the top: hoops stripes sash chest_band halves check dots camo, or your own tiled texture
  (--overlay top:hoops:#ffffff, --overlay top:texture:cloth.png).
  3D characters: the colours go into the 3D spec (exact).  PHOTO: regions are ESTIMATED (pose points + skin
  model + colour clusters) and your photo's own pixels are re-tinted with their shading kept; every build writes
  regions.png - paint over it and pass it back with --regions to fix a mask.
  Already built?  forge.py recolor out/hero --set team_red   (palette swap of every PNG into out/hero_team_red;
  photo / game folders: add --from top=#2a5bd7,bottom=#202020 to say which colours to replace).

VARIANTS - a crowd from one character
  --variants 8 writes variants/ (variants_sheet.png + variant_<seed>.txt specs); --variant SEED builds that
  one as the character. Vary: body, outfit, colours, skin, accessories, face (--vary all). Same seed = same
  variant, every time.  PHOTO: a variant only re-tints the clothes and scales the body (face, skin and hair
  are kept) - never a new image of the person.  forge.py variants --npc goblin -n 12  (no build needed).

ENEMY / NPC PRESET PACK
  forge.py npc lists 17 fictional characters (villager, guard, knight, goblin, orc_brute, wizard, skeleton,
  zombie, ghost, robot, boss_king ...) and 7 move presets (npc_civilian, npc_guard, enemy_grunt, enemy_caster,
  enemy_creature, boss, zombie) with new motions (wave, talk, patrol, cower, cast, roar, lunge, die, sit ...).
  forge.py build --npc goblin --variants 6

EXTRAS (Start > What to make > Extras, or the flags)
  --framedata     hit / hurt boxes + startup / active / recovery -> framedata.json, framedata.cfg, preview
  --footlock      2-bone IK pins planted feet (no sliding) in 3D-character sprite moves
  --fx            outline=2, cel=3, pixel=4, colors=32, light=-1:-1:1, rim=0.4 look passes on every frame
  --maps          normal,emissive -> maps/ (normal maps light 2D sprites in Unity URP 2D / Godot)
  --blend         idle>walk:3 -> blend_idle_walk transition move
  --lods 2        model_baked.glb (one texture, one material) + model_lod1/2.glb + lods.json
  QA check        on by default: qa_report.txt (clipping, empty frames, feet drift, pops, loop seams,
                  specks, halos); --no-qa to skip; forge.py qa <folder> on any build or game folder
  Physics         hair / cape / scarf swing on 3D characters (--no-physics to stop)

TOOLS menu / commands
  forge.py atlas out/a out/b out/c --out out/pack     several characters on shared pages + pack.json
  forge.py batch queue.txt --workers 3                one forge.py command per line (or a .json queue);
                                                      writes queue_report.txt + per-job logs
  forge.py framedata <folder>    forge.py qa <folder>    forge.py recolor <folder> --set NAME

Honest limits: frame data and normal maps are ESTIMATED from the 2D silhouettes (tune them); foot locking
is for sprites (the GLB clips are not re-solved); LODs are rebuilt at fewer segments (not decimation) and the
baked model uses a flat palette texture (no baked lighting); the Unity package was compiled against stub APIs,
not run in Unity; the Godot plugin was tested on Godot 4.3.
""")

T("plugins", "Game engine plugins: Unity and Godot", r"""
Both read a Sprite Forge build folder (atlas.json + atlas pages, + framedata.json and maps/ if you made them)
or a multi-character pack.json from forge.py atlas.

GODOT 4 (plugins/godot/addons/sprite_forge) - tested on Godot 4.3 (headless + rendered)
  1. Copy addons/sprite_forge into your project; Project Settings > Plugins > enable "Sprite Forge".
  2. Copy the build folder into the project (e.g. res://chars/hero).
  3. Project > Tools > Sprite Forge: Import Build Folder...  (or in code:
        SpriteForgeImport.import_folder("res://chars/hero")   )
  -> hero_frames.tres (SpriteFrames: every move with its fps / loop, feet pivot) and hero.tscn
     (SpriteForgeCharacter = AnimatedSprite2D + Hurtbox / Hitbox Area2D children that follow framedata.json,
     mirrored with flip_h; signal hit_active(move, frame, rect); show_boxes draws them).
  Normal maps: frames become CanvasTexture(diffuse + normal) so PointLight2D lights the sprite.

UNITY 2021.3+ (plugins/unity/com.spriteforge.importer)
  1. Package Manager > + > Add package from disk > com.spriteforge.importer/package.json
  2. Copy the build folder under Assets/.  3. Tools > Sprite Forge > Import Build Folder...
  Batch: Unity -batchmode -quit -projectPath P -executeMethod SpriteForge.Editor.SpriteForgeImporter.ImportFromCommandLine -sfFolder Assets/chars/hero
  -> sprites sliced with the feet pivot, <name>_data.asset (moves + boxes in units), Anim/*.anim + .controller,
     <name>.prefab (SpriteRenderer + SpriteForgeCharacter driving BoxCollider2D hurt / hit boxes, HitActive event).
     maps/atlas_normal.png is attached as the _NormalMap secondary texture (URP 2D lights).
  HONEST: compiled against stub Unity APIs only (tools/unity_stub_check) - not yet run inside Unity.
""")

T("python", "Is Python fast enough? (how the engine is built)", r"""
Python is the glue; the heavy lifting runs in native code:
  ffmpeg (C)            decoding / encoding video          ~500 frames/s at 640x360 on an 8-core CPU (imageio-ffmpeg)
  NumPy / OpenCV (C++)  background, cut-out, optical flow  ~150 frames/s static camera, ~17 frames/s for a
                                                           tracking camera with 3 parallax layers
  MediaPipe (C++/TFLite) pose tracking                     ~70 frames/s (full model), 24 (heavy)
  SciPy                 skeleton fitting                   ~15-20 frames/s
  COLMAP (C++)          camera solve for 3D scans          ~25 s for 72 frames (pycolmap wheel or colmap CLI)
  our FBX writer (Py)   rigged model + 14 takes -> FBX     ~0.3 s (NumPy; Blender used to take ~5-8 s)
A whole 4-move clip set becomes HD + SNES + GBA sprites in ~25 s. Rewriting it in C++ would mostly speed up
the glue, which is a small part of the time. Where it would matter: real-time preview of 4K footage or
GPU dense reconstruction - those are done by dedicated tools (ffmpeg, COLMAP/Meshroom) the Studio calls.
Python also means one code base for Windows and Linux, installed with pip only (see: forge.py help install).
""")


FIELDS = [
    ("Name", "Character name; becomes the folder out/<name>/ and the symbol prefix in console headers."),
    ("Front photo", "PHOTO mode: picture of your character facing the camera or to the right. A plain background or a transparent PNG works best."),
    ("Back photo", "PHOTO mode (optional): back view. With no other views: the idle_back frame. With a side / 3/4 photo or 'Output views': the 'back' view (views/atlas_back.png)."),
    ("Side photo", "PHOTO mode (optional): side profile of the SAME person/character (facing image-right unless 'Side faces left' is ticked) -> the 'right' view; the 'left' view is its mirror."),
    ("Side faces left", "Tick if the side photo faces image-LEFT (it becomes the 'left' view and 'right' is mirrored from it)."),
    ("3/4 photo", "PHOTO mode (optional): three-quarter front view turned towards image-right -> the 'front_right' (45) view."),
    ("Output views", "Which views to output: e.g. front,right,back  or  billboard8 (all 8 directions). Views with no photo are MIRRORED or INTERPOLATED (squashed) from the nearest real one and flagged as filled. Spec/mannequin renders every view for real. Blank = only the views you gave photos for."),
    ("View cut", "Keep only the top part of each view: 0.55 = head to lap (seated kart drivers), blank/0 = whole figure. Every view is aligned to the same top and cut line."),
    ("Profile", "Output profile = what kind of game you build for (kart_racer, fighter14, platformer, topdown8dir, retro_snes, ...). It fills frame size, moves, views and writes the extra files that game type needs (e.g. sprite.png + character.ini for a kart racer). '(none)' = standard outputs only."),
    ("Profile vars", "Values for the profile's templates, e.g.  tagline=Fast!; speed=4; kart=255,80,40  (the kart_racer profile lists its own)."),
    ("Video / frames per move", "PHOTO mode (optional): real frames for some moves, e.g. walk=walk.mp4; kick=C:/frames/kick  (videos are decoded by the bundled imageio-ffmpeg)."),
    ("Frames folder", "FRAMES mode: folder with walk/01.png ... or walk_01.png ... (folder/file name = move name)."),
    ("Per-move sheets", "PER-MOVE SHEETS mode: one strip image per move: walk=walk.png; punch=punch.png. Use 'Add strip...' to pick files."),
    ("Frames across", "PER-MOVE SHEETS / SPRITE SHEET: frames per strip / grid columns. Blank = auto-detect by transparent gaps."),
    ("Sprite sheet", "SPRITE SHEET mode: one image with all moves (one row per move, or one cell per move)."),
    ("Sheet layout", "rows = each row is one move's frames; cells = each cell is a separate 1-frame move."),
    ("Grid", "ROWSxCOLS of the sheet, e.g. 4x8. Blank = auto-detect by transparent gaps."),
    ("Spec file", "TEXT SPEC mode: key=value description of a FICTIONAL character (see examples_char.txt)."),
    ("Kit", "Mannequin/spec colours: home, away, blue, red, black, gk (goalkeeper). LIBRARY RIG: '(own colours)' keeps the rig's textures/colours, or pick a library kit (recolours by material name)."),
    ("Extra kits", "Mannequin / library rig: also export model_<kit>.glb/.fbx for these kits (comma list or 'all')."),
    ("Library rig", "LIBRARY RIG mode: a rig or animation asset from the Library tab (e.g. sample_lanky), or browse to any .fbx / .glb file (imported on the fly). Its mesh and bones are the template; every move is rendered through the same pipeline as the mannequin."),
    ("MakeHuman body", "v7 MANNEQUIN mode: build a realistic human body from the CC0 MakeHuman assets instead of the mannequin - gender 0 (female)..1 (male), age 0..1 or years, muscle / weight / height / proportions 0..1 (0.5 = average), skeleton default (163 bones) | default_no_toes | game_engine (65, fingers) | body (26). One-time setup: forge.py human --setup. Without the assets the mannequin is used and the report says so."),
    ("Material split", "v7, 3D: auto = a single-material / unnamed mesh is split into engine slots Skin_Mat / Jersey_Mat / Shorts_Mat / Socks_Mat (+ Shoes_Mat) by bone regions and heights; off = only rename recognisable material names."),
    ("Material slots", "v7, 3D: full = Skin/Jersey/Shorts/Socks + optional Trim/Hair/Shoes slots; core4 = exactly the 4 core slots; keep = materials exactly as imported (pre-v7 behaviour)."),
    ("Separate anim files", "v7, 3D: also write anim/character_base.glb + one anim_<move>.glb (+ .fbx) per move + anim/manifest.json - load the base once and the moves separately (raylib / Godot / Unity / Unreal)."),
    ("Outfits", "v7 EQUIP: library outfits (skinned clothing / armour on the same skeleton), separated by ';'. NAME, or NAME:hide=torso+arms to change which body regions are hidden underneath, NAME:slot=Jersey to follow a kit slot. Use the Equip... button to pick."),
    ("Props", "v7 EQUIP: library props (rigid items) separated by ';': NAME@socket with socket hand_r, hand_l, head, back, hip or foot; optional :ox,oy,oz (m) :rx,ry,rz (deg) :scale. Use the Equip... button to pick."),
    ("Slot colours", "v7: recolour material slots, e.g. Jersey=#c8102e,Armour=#777777. Untextured slots are tinted; a slot with an image texture keeps its texture."),
    ("Root motion", "LIBRARY RIG, 3D takes: keep = the hips travel as in the clip, inplace = hips stay over the origin (engine moves the character), root = the travel is moved onto the root bone. Sprites are always centred."),
    ("Library clip", "LIBRARY RIG: which clip plays this move: asset:clip, e.g. sample_moves:wave, with options @speed=1.2,trim=0.2-0.9,loop|once (trim in seconds). Blank = automatic: mocap > same-named clip in the rig > same-named clip elsewhere in the library (retargeted) > the built-in motion retargeted > rest pose."),
    ("Camera yaw", "3D camera angle for rendering: 65 = three-quarter facing right (default), 90 = pure side view, 0 = front."),
    ("Kart prop", "Kart moves: auto = draw a kart under the driver, none = driver only (for games that draw their own kart)."),
    ("Frame W", "Width of every frame cell in pixels."),
    ("Frame H", "Height of every frame cell in pixels."),
    ("Figure px", "How tall (px) a 180 cm standing figure is in the frame. Blank = 62% of frame height."),
    ("Ground line y", "The y pixel where the feet stand in every frame. Blank = 94% of frame height."),
    ("Cutout", "Background removal: auto, alpha (image already transparent), rembg (optional AI segmentation), threshold (plain backdrop), none."),
    ("Flip", "Mirror imported images so the character faces right (all outputs face right)."),
    ("Height cm", "PHOTO/FRAMES: real height of the character, to scale it against the 180 cm reference."),
    ("Missing moves", "What to do with ticked moves that have no source frames: placeholder (transform of idle), static (copy of idle), mannequin, skip, puppet (v8: your photo cut into body parts and posed per move - needs pose landmarks from 'forge.py cutout')."),
    ("Pose landmarks", "landmarks.json written by 'forge.py cutout' (33 body points). Empty = landmarks.json next to the photo. Needed for 'puppet' moves and any Turn other than 0."),
    ("Turn", "v8: which way the character faces in the game. 0 = as photographed (face-on). 90 = side-on facing right (fighting-game view). 180 = back. 270 = the other side, mirrored so it still faces right. Built from your ONE front photo plus a depth guess (see Turn depth) - the side view is an estimate, not a real side photo."),
    ("Turn angle", "Optional fine angle in degrees (e.g. 60 for a three-quarter view). Overrides the Turn dropdown when filled in."),
    ("Turn depth", "How thick each part of the body is front-to-back, used to work out the side view. auto = side reference if given, else the bundled MakeHuman CC0 body template. template = MakeHuman body. relief = simple ellipses (no template). side = fit to your own side photo / video frame (Turn side reference)."),
    ("Turn side reference", "Optional: a side-on photo, cut-out PNG or a frame of a video of the SAME person (use forge.py build --side-frame for a video time). Gives the real outline thickness for the turned view. Colours still come from the front photo."),
    ("Quality", "final = full size, every frame, all exports. draft = Quick preview: half-size frames, up to 4 frames a move, no 3D/console files - a few seconds instead of minutes."),
    ("Cache", "Remember moves already built with the same settings and re-use them, so changing one move only rebuilds that move. Untick to force a full rebuild."),
    ("Outline", "Draw a dark outline around rendered mannequin frames."),
    ("GLB model", "Spec/mannequin: write the rigged 3D model model.glb."),
    ("Move picker", "v8 Start tab: tick the moves to make and set frames / fps per move. 'Add a move' brings in any move from the other presets (e.g. a platformer 'climb' for a fighter). Same list as '3. Moves' on the Build tab."),
    ("GLB", "Also write model.glb (glTF binary: rigged mesh + one animation per move). Opens in Godot, Blender, three.js, raylib."),
    ("Animation export", "Also write one animation file per move next to the model (raylib 5.5 / 6 friendly), see Help > 3D models."),
    ("FBX", "Also write model.fbx (built-in FBX 7.4 writer - Blender not needed)."),
    ("Strips", "Also write strips/<move>.png (one image per move)."),
    ("GIF previews", "Also write previews/<move>.gif to look at quickly."),
    ("Console target", "Extra export for a console (frame size, colours, tiles, texture pages, low-poly model) into out/<name>/console/. 'None' = only the normal output."),
    ("Dither", "Console export: mix palette colours in a pattern when reducing colours (smoother gradients, noisier pixels)."),
    ("Output folder", "Where out/<name>/ is created."),
    ("Blender exe", "Optional. Only used for Blender-based LOD decimation, or if you choose --fbx-writer blender. Blank = not used / auto-detect."),
    ("Clips", "VIDEO / MOCAP: one clip per move: walk:8=C:/clips/walk.mp4 (8 sprite frames). Optional @start-end seconds, #bg=chroma to override. Separate clips with ';' or use 'Add clip...'."),
    ("Video camera", "VIDEO: auto works it out. static = tripod, handheld = small shake, tracking = camera follows the person (running in frame)."),
    ("Video background", "VIDEO: auto, median (background seen behind the moving person), plate (clip starts with the empty scene), chroma (green/blue screen), rembg (optional AI cut-out)."),
    ("Slow motion", "VIDEO: 1 = use real frames only; 2 = make twice as many in-between frames by optical flow when the clip is short."),
    ("Pose model", "MOCAP: MediaPipe model size: lite (fastest), full (default), heavy (most accurate, ~3x slower)."),
    ("Orbit video", "SCAN: a video walking slowly around a STILL object. See Help > Video to a 3D model for the capture guide."),
    ("Scan frames", "SCAN: how many sharp frames to extract (60-120)."),
    ("Run COLMAP", "SCAN: also reconstruct here (pycolmap from setup, or COLMAP installed). Off = only prepare the images/ folder for Meshroom/COLMAP."),
    ("Scan mesh", "SCAN: skip reconstruction and make console LODs from a finished mesh (obj/ply/glb from Meshroom, RealityScan, Polycam...)."),
    ("Scan height", "SCAN: real height in metres (photogrammetry has no scale of its own)."),
    ("Scan budgets", "SCAN: triangle budgets, e.g. ps1=600,ps2gc=5000,pc_hd=100000. Blank = one LOD per console preset."),
    ("Expressions", "v9 FACES: auto = a face per move (punch angry, hit hurt, taunt taunt, victory happy ...); off = neutral; or one face for all. Photo: ESTIMATED warps of your own photo."),
    ("Talk", "v9: a line of dialogue -> talk/ strip with mouth shapes + talk.json. Shapes come from the letters (not speech recognition). 'sheet' = every mouth shape."),
    ("Regions", "v9 PHOTO: a painted region map (start from the regions.png a build writes) to fix the ESTIMATED skin / hair / clothes masks."),
    ("Variant", "v9: build procedural variant SEED as the character (same seed = same result). Empty = the character itself."),
    ("Frame data", "v9: hit / hurt boxes + startup / active / recovery measured from the sprites (ESTIMATED) -> framedata.json + framedata.cfg."),
    ("Foot lock", "v9: 2-bone IK keeps planted feet still (no sliding) in 3D-character sprite moves."),
    ("QA", "v9: sprite QA check after the build -> qa_report.txt (clipping, empty frames, feet drift, pops, loop seams, specks, halos)."),
    ("Physics", "v9: ponytail / long hair / cape / scarf swing as simple verlet chains (3D characters)."),
    ("FX", "v9 look passes: outline=2, cel=3 (bands), pixel=4 (pixel-art block size), colors=32, light=x:y:z, rim=0.4, outline_colour=#101018."),
    ("Maps", "v9: normal and/or emissive maps -> maps/ (estimated from the 2D sprite; for 2D lights in Unity / Godot)."),
    ("Blend", "v9: transition moves a>b:frames, e.g. idle>walk:3 -> blend_idle_walk (3D: pose blend; photo: crossfade)."),
    ("LODs", "v9 3D: model_baked.glb (1 palette texture, 1 material) + N lower-detail model_lodN.glb + lods.json."),
    ("Moves", "Tick the moves to build. frames = number of frames, fps = playback speed, loop = repeats (idle/walk) or plays once (punch)."),
]
FIELD_HELP = dict(FIELDS)


def _consoles_text():
    from . import consoles
    L = ["Pick a console and the build ALSO writes out/<name>/console/ shaped for that machine.",
         "Numbers are typical practical values for ONE character; items listed under 'approx' are rules of thumb",
         "(budgets depend on your engine, scene and video mode). Check your platform's docs for hard limits.", "",
         "What gets made:",
         "  Retro tile consoles (2600, NES, SMS, GB, SNES, Genesis, GBA, DS): frames cropped and scaled to the",
         "    sprite size, one shared palette (snapped to the console's real colour space), indexed PNGs, unique 8x8",
         "    tiles (mirrored duplicates removed) in banks that fit sprite VRAM, raw tile data in the native format,",
         "    palette.pal/.bin, and <name>_<console>.h with C arrays (palette, banks, per-frame tile maps, anims).",
         "  Texture consoles (PS1 .. PS5, PC): frames packed on texture pages within the max texture size (power of",
         "    two where the hardware needs it), CLUT-indexed where the console used palettes, a frame-rect table in",
         "    the .h, and for spec/mannequin builds a re-generated low-poly model_<console>.glb/.fbx within the",
         "    polygon budget (fewer or more segments on the same shapes; it cannot add real detail).",
         "  Jumps: airborne frames are put on the ground line in console/ and their height is stored as 'rise'.", ""]
    for k in consoles.ORDER:
        p = consoles.PRESETS[k]
        L.append("%s (%s)" % (p["label"], k))
        L.append("    " + consoles.describe(k))
        L.append("    " + p["notes"])
    return "\n".join(L)


def _fields_text():
    return "\n".join("%-24s %s" % (k, v) for k, v in FIELDS)


def get(key):
    title, text = TOPICS[key]
    if text == "@CONSOLES@":
        text = _consoles_text()
    elif text == "@FIELDS@":
        text = _fields_text()
    return title, text


ALIASES = {"sheet": "sprite-sheet", "spritesheet": "sprite-sheet", "sprite_sheet": "sprite-sheet", "start": "quickstart",
           "files": "outputs", "doctor": "install", "setup": "install", "linux": "install", "fbx": "install", "output": "outputs", "mode": "modes", "console": "consoles", "engine": "engines",
           "unity": "plugins", "godot": "plugins", "plugin": "plugins", "style": "v9", "faces": "v9", "expressions": "v9",
           "colours": "v9", "colors": "v9", "recolor": "v9", "variants": "v9", "npc": "v9", "batch": "v9", "atlas": "v9", "qa": "v9", "framedata": "v9", "raylib": "engines", "unreal": "engines", "snes": "engines", "gba": "engines"}


def render(topic=""):
    t = (topic or "").lower().strip()
    t = ALIASES.get(t, t)
    if t in ("all", "*"):
        return "\n\n".join("== %s ==\n%s" % get(k) for k in TOPICS)
    if t in TOPICS:
        return "== %s ==\n%s" % get(t)
    return "Sprite Forge Studio help.  forge.py help <topic>   (or 'all')\n\n" + "\n".join(
        "  %-16s %s" % (k, v[0]) for k, v in TOPICS.items())


def markdown():
    out = ["# Sprite Forge Studio - Help", "", "The same text is in the app (Help tab / Help menu) and `forge.py help <topic>`.", ""]
    out += ["- [%s](#%s)" % (TOPICS[k][0], k) for k in TOPICS]
    for k in TOPICS:
        title, text = get(k)
        out += ["", '<a id="%s"></a>' % k, "## " + title, "", "```", text, "```"]
    return "\n".join(out) + "\n"

# Sprite Forge Studio v9.0

A character sprite + 3D pipeline with a visual UI. The 2D core and C/raylib loader are the
**SpriteForge** base pipeline (`spriteforge/`, vendored, same `sprites.cfg` v1 format). The Studio adds the
Tkinter UI, SPEC mode, the procedural rigged mannequin, GLB/FBX export, `character.ini`, `atlas.json` and
game exporters.

## New in v11.5: film a move set, pick a game type, drop the character in

v11.4 stored one clip for every game. v11.5 is the rest of that idea: your own movement as the
default, a data file per genre, and one manifest a loader can read. `forge.py help game` has the
same commands and the same limits.

* **Recording session** (`forge.py motion record --folder CLIPS --set owner`):
  * One clip per move, named after the move (`punch.mp4`, `walk.mp4`). Side-on, full body, about
    1 second of T-pose, then the move about 3 times. Optional `idle_front.mp4` / `walk_front.mp4` /
    `run_front.mp4`.
  * The folder is imported in one go through the existing mocap tracker. A pose-track JSON (what
    that tracker writes) is the same path, which is how the tests run with no person and no MediaPipe.
  * Each clip is checked first. The report says what is wrong: feet out of frame, body cut off,
    too dark, no T-pose, too short, tracking lost — and which files to reshoot.
  * A repeated move keeps the best repeat, or a clean average of two close ones, and is trimmed to
    a loop or a single action.
  * Stored as skeleton keys only. The video, the frames, the face and the body shape are not kept.
    Temporary tracker files are deleted (`--keep-temp` leaves a pose trace you should not pack).
  * `forge.py motion use-set owner` makes that set the first place a build looks. Missing moves
    come from the shipped starter, then the procedural motion. The build report names the source
    of each move (`punch=set:owner`, `kick=starter`, `special1=procedural`).
  * `forge.py motion shotlist --game soccer` is the printable checklist for that pack.
* **Game-type packs** (`game_packs/*.json`, `forge.py game list`, `forge.py build --game soccer`):
  * A pack is data: moves mapped to generic library names, frames / fps / loop, camera
    (`side`, `three_quarter`, `topdown8`), props the game draws, and events (hit frames, ball
    contact, footsteps, throw release, shoot, reload).
  * Shipped: fighting, gaelic, platformer, topdown_rpg, kart, soccer, basketball, boxing,
    wrestling, tennis, beat_em_up, shooter. Drop another JSON file in `game_packs/` to add one.
  * Character types from v11.4 apply on every pack. The old profiles still build unchanged.
  * A move uses a clip of its own name when the set or the starter has one, otherwise its own
    procedural animation. A generic clip (jab and cross sharing punch, a header sharing jump)
    is only the fallback when that move has no animation of its own. The build report lists
    any clips that are still shared. See `forge.py game show boxing`.
* **One game file** (`out/<name>/game_character.json`, written by every build):
  * Character, type, pack, camera, animations (strip and sheet, frames, fps, loop, pivot and
    ground line), events, and hit / hurt boxes when the framedata pass can measure them.
  * Loaders copied next to it: `loaders/raylib/` (header + example, same style as `spriteforge.h`),
    `loaders/godot/game_character.gd`, `loaders/unity/GameCharacter.cs`.
  * Egyptian Fighter and HD Fighter adapters still read a normal build. If `atlas.json` or
    `sprites.cfg` is missing they rebuild that index from the manifest. Arena FC still needs a
    cut-out photo. `tools/gaelic_forge.py` is still the 3D mesh, not this file.
* **Studio**: Library → Recording session. Build and Start → What to make have the game-type
  dropdown and the motion-set dropdown. The Build step names the manifest.

Limits: the starter is procedural keys, not motion capture. A video import needs MediaPipe
(`python tools/setup_pose.py`); without it the checker says so and does not keep the video.
Hitboxes are a silhouette estimate. Quick preview scales event frames down because it builds
fewer frames. No Mixamo or Meshy clips. Do not commit a recording of a real person.

## New in v11.30: tailored kits and boots, and a kit atlas (fed back from Arena FC)

Arena FC's squad wore its kit as body paint. The MakeHuman clothes hugged every muscle (pecs and abs through the
shirt), every hem was a staircase of whole triangles, and the "boots" were the bare feet, toes and all.
**`sforge/tailor.py`** rebuilds each garment from its skin-tight source:

- every opening (shirt hem, sleeves, collar, shorts legs, sock tops, boot collars) is snapped onto one plane, pushed
  out to the furthest point of the old edge so nothing shortens over a body that has no skin underneath;
- the muscles are smoothed away (Taubin, no shrinkage) and the cloth is lifted back onto the body's high points, so it
  drapes over the chest and shoulder blades and spans the hollows; it then stands off the skin by an `ease` that
  grows towards the hem (`flare`);
- a lip is turned in at each opening, so a sleeve or a shirt tail has thickness;
- the shirt tail tucked inside the shorts is cut away (it poked through the shorts in motion);
- boots lose their toes (400 smoothing passes on the foot) and get a flat sole on the ground;
- all four garments are laid out on one **kit atlas** (`tailor.LAYOUT`: torso front / back, sleeves, shorts, socks,
  boots), with print areas for the name, numbers and crest (`tailor.PRINT`); the front reads the right way round from
  the front and the back from behind;
- `replace_parts(glb_in, glb_out, {"v0_": parts, ...})` swaps the garments into a skinned GLB and keeps every node,
  the skin and every animation; `skeleton_from_glb()` maps a MakeHuman game skeleton to the garment rules.

Rules are data (`Garment`: source, ease, flare, smoothing, lip, extend, tuck), so long sleeves, a guernsey or rugby
shorts are a new list, not new code.

**`sforge/kitdesign.py`** ships the kit as masks a game tints at run time (any club, the character editor): a
pattern mask per style (`plain stripes hoops sash halves pinstripes chevron fade quarters band`), a detail map (trim:
collar V, cuffs, shorts stripe and hem, sock bands; boot sole plate, flash and heel; a knitted weave and side seams), a
lettering atlas (Big Shoulders Bold, SIL OFL 1.1, in `sforge/data/fonts`) with fill and outline, and
`kit_layout.json`, the contract the game's shader reads. `paint()` renders the same maths to a picture for previews.
Designs are original: no real club's crest, sponsor or template.

Arena FC runs both from `arena-fc/Tools/tailor_soccer_player.py` (and on every `build_soccer_player.py` build), and
its `Shaders/kit.gdshader` prints each player's name and number on the shirt, his number on the front and the shorts,
and an original crest.

Test: `python tools/test_tailor.py` (on the Gaelic squad GLB: straight hems, stand-off, no toes, the tuck, UV panels,
the back print on the back, the GLB round trip, every kit style).

## New in v11.29: labelled match events to moves - SoccerTrack v2 (fed back from Arena FC)

`sforge.matchcapture.process_events(video, events, models)` handles footage that already says *who*
did *what* and *when*. Each event carries a label, a contact frame, and that player's box in every frame.

**What it does:**
1. Makes one pass over the video. Frames outside the events' windows are skipped without decoding.
2. Poses only the labelled player.
3. Refines the labelled contact frame to the kicking ankle's speed peak.
4. Lifts the pose to 3D and fits it to the shared skeleton, as v11.26 does.

There is no detector, no tracker and no guessing which motion was a kick.

**Labels it uses:**

| Label | Becomes |
|---|---|
| pass, lofted pass, cross, shot, free kick | a kick, with its sub-kind kept |
| header | a header |
| tackle, block | a tackle or block |
| throw-in | a throw-in |
| drive | a dribble loop |

**SoccerTrack v2 adapter:** `tools/soccertrack_capture.py ROOT OUT` reads
[SoccerTrack v2](https://huggingface.co/datasets/atomscott/soccertrack-v2). The dataset is
CC BY 4.0: 10 university matches as 4K panoramas at 25 fps, with ball-action labels and per-frame player boxes.

- It streams the 2.7 GB-per-half box files with `ijson`.
- It handles the files' known quirks:
  - events are listed under `actions`;
  - labels may be upper case;
  - half-2 times are counted from the start of the match;
  - frame numbers carry an offset.
- `tools/runpod_soccertrack.sh` runs the whole job on a GPU pod: download (token needed), capture, merge, and stage.
- `write_takes` is now shared by both capture paths.

Test: `python tools/test_matchcapture.py`. The tests cover label parsing, half-2 timing, player ids, streamed boxes and contact refinement.

## New in v11.28: textured multi-part GLBs - realistic players on a game skeleton (fed back from Arena FC)

`rigrec.write_glb_parts(rig, path, parts, materials, images, clips)` writes one skinned GLB with
several textured mesh parts on one skeleton, each part its own node.

- **Use:** a game can ship several player identities in one file, show one per player and hide the rest.
- **Kept per part:** smooth per-vertex normals and UVs.
- **Materials:** hair, lashes and beard shells can be alpha-masked and double-sided.
- **Textures:** mip-mapped with linear filtering. Images may be JPEG, which keeps opaque skin atlases small.

Arena FC uses it to put the realistic MakeHuman squad (real skin, eye, hair and beard atlases) onto its
18-bone animation skeleton. The steps are the same as for the sculpt:
1. Collapse the weights from 52 bones to 18.
2. Conform the mesh to the bind pose with `sforge.bindconform`.

Every retargeted clip then plays on the realistic body.

Test: `python tools/test_glb_parts.py`.

## New in v11.27: hurling, Aussie rules and rugby; the hurley and helmet; rugby and guernsey kits

### Three new game packs

`forge.py build --game hurling | aussie_rules | rugby`, `forge.py roster --game ...` and the Games tab all take them,
with the same QA, cell fit, HD frames, rosters, portraits and engine projects (Godot, Unity, Unreal, raylib, web,
pygame) as the other packs. Every move has its own motion; none borrows another move's clip.

| Pack | Moves |
|------|-------|
| `hurling` (21) | idle, walk, run, sprint, **solo** (sliotar on the bas), **strike**, **ground_strike**, **puckout**, **free**, **lift**, **catch** (hurley up to guard the hand), hand_pass, **hook**, **block**, shoulder, sidestep, fall, get_up, hit, celebrate_point, celebrate_goal |
| `aussie_rules` (21) | idle, walk, run, sprint, bounce, drop_punt, set_shot, snap, handball, **mark** (chest), **speccy**, **ruck_tap**, tackle, **shepherd**, smother, pick_up, sidestep, fall, get_up, hit, celebrate |
| `rugby` (23) | idle, walk, run, sprint, carry, **pass** (spin pass), offload, kick, drop_goal, place_kick, catch, **lineout**, tackle, **hand_off**, **scrum**, **ruck**, **try**, pick_up, sidestep, fall, get_up, hit, celebrate |

The bold moves are new procedural motions (`hurl_*`, `aussie_*`, `rugby_*`, `lineout_lift` in `sforge/motions.py`).
The events (`ball_contact` when the bas meets the sliotar, `throw_release`, `hit_start` / `hit_end`) are in
`game_character.json` like every pack's.

### The hurley and helmet (`"equip"` in a game pack)

A pack can now list props the player always carries: the hurling pack has
`"equip": ["sport_hurley@hand_r", "sport_hurl_helmet@head"]`, so every hurler holds a hurley and wears a helmet in
every move, in the sprites and in `model.glb` / `model.fbx`. `--attach` replaces them and `--no-equip` leaves them
off. Both props are CC0, made from boxes and a dome by `tools/make_sport_props.py` (no third-party content).
A mannequin build with props draws the mannequin as a library rig, which the props need.

### Kit cuts on the look builder

`--kit sf_<kit>[#number][@cut]`:

* `@rugby`: a deep collar and placket in the trim colour, hooped socks.
* `@guernsey`: Aussie rules, sleeveless (the arms are bare skin), with a yoke across the shoulders.
* no cut: the football shirt (soccer, Gaelic, hurling).

The number on the back works with every cut. Rosters pick the game's cut by themselves (`roster.KIT_STYLE`), and a
player in a roster file can set its own `"kit_style"`.

### Rosters

The new games are team games with real positions: hurling (goalkeeper in the keeper's kit, full back, midfield,
forwards), Aussie rules (ruckman, key defender, midfielder, small and key forwards) and rugby (prop, lock, flanker,
fly-half, winger, hooker, scrum-half), each with a body type to suit. The Games tab offers forward and back types
(heavy, big, quick, small) for these sports.

### Fix: the Games tab and `check_motion --pack` show the clip the build really plays

They used to guess a move's clip from its `prefer` list and generic `library` name, and missed a pack's `"own"`
motion: a move like rugby's `try` showed as missing, and a strike as the generic shot. They now ask the build's own
resolver (`sforge.motionset`).

Test: `python tools/test_new_sports.py` (all 15 packs validated; new motions, equip, props, kit cuts, rosters; the
three packs built on the mannequin with no QA FAIL and nothing clipped; the helmet on the head).

## New in v11.26: match capture - real match video to library moves (fed back from Arena FC)

`python -m sforge.matchcapture VIDEO OUT_DIR --models MODELS_DIR` turns a wide-angle match
recording (e.g. a Veo camera, players 60-150 px tall) into anonymous library moves:

1. **people**: YOLOX-m (Human-Art) person boxes on the whole frame plus two half tiles, NMS
2. **tracks**: a small SORT-style tracker joins boxes across frames
3. **2D pose**: RTMPose Halpe-26 top-down on each box (`--pose rtmpose_l_halpe26` on GPU, `_m_` on CPU)
4. **3D**: Sprite Forge's own 2D->3D lifter (`sforge/models/lifter_v1.onnx`, 9-frame window, 19 joints,
   trained by `tools/train_lifter.py` on SkillCorner's MIT pose data, 10.6 cm validation error)
5. **moves**: kicks found from 2D foot speed + knee straightening, run loops from the cleanest stride,
   then fitted with `jointtrack.fit_landmarks` (the same IK as v11.22) into `.json` moves + `_import.json`

MediaPipe is not used here: its person finder sees nothing at Veo player sizes.

* `tools/fetch_models.py MODELS_DIR` downloads the detector / pose ONNX files listed in
  `sforge/models/registry.json` (each with its licence - check it before shipping moves made with it)
* `tools/matchcapture_batch.py FOOTAGE OUT --workers N` runs every clip (zips are unpacked), merges the
  per-clip folders with renumbered names and packs `moves.tgz`; `--purge` deletes each video once done
* `tools/runpod_matchcapture.sh` does the same on a GPU pod (footage on a network volume)
* **privacy**: only joint angles leave the pipeline - no video, faces, names, numbers or per-player
  tracks are written; `--footage-licence` records who owns the footage in each move
* test: `python tools/test_matchcapture.py` (tracker, kick detector, lifter round trip, merge, registry)
## New in v11.25: sprites that are not blocky or blotchy, HD players, a sports idle

### Drawing (`sforge/render_rich.py`)

A character with several textures (skin, hair, kit, eyes) used to be drawn **one flat colour per triangle**, sampled
at the triangle's centre and lit per triangle. That was the blotchy patches, the blocky body and the missing shirt
number. Every textured rig is now drawn per pixel:

* each material's own texture, sampled smoothly from a shrunk copy, so a large texture doesn't shimmer;
* smooth light that blends across the body, while hard creases stay sharp;
* hair, brow and lash cards drawn as cut-outs, so their see-through parts show what's behind;
* supersampled to about 640 px tall (4x for a 160 px cell, 2x for an HD cell).

The kit recolours materials as before, and the framing is unchanged. `SF_FLAT_SPRITES=1` brings back the old drawing.

### Kits on the look characters

* **Hems:** the hems of the shirt, sleeves, shorts and socks zig-zagged one triangle up, one down. They are now
  smoothed straight, without shrinking, and no vertex moves more than 1.5 cm.
* **Plain kits:** the game kits (`sf_<kit>`) are plain. The sock hoops and shorts piping that broke up along the hems
  are gone.

### HD players

* **Command line:** `forge.py build --frame 256x320`, or `forge.py roster --hd`, draws sprites at twice the game's
  frame size.
* **Games tab:** the same switch is the **HD sprites (2x)** tick-box.
* **Proportions:** a pack's figure share (Gaelic 0.58) is kept at any frame size (`BuildConfig.figure_share`).
* **QA:** the ground tolerance grows with the cell, so HD isn't flagged for the same half-pixel.

### A sports idle

The plain idle stands to attention. The new `idle_athletic` stance has soft knees, a slight lean, loose arms and
weight rocking from foot to foot. It is a CC0 starter clip, and soccer, Gaelic, basketball and tennis prefer it.

A pack's named motion now wins over a rig's own clip that only shares the move's name, such as a template's stiff
"idle". A `lib:` name that is not a library clip finds the procedural motion of that name.

### Feet on the ground

The feet reference is now where idle, walk and run plant (the median of each move's most-planted frame), not idle
frame 0 alone. The cell fit places it on the ground line before fitting. A crouched idle no longer lifts every other
move off the ground, and the ground lock no longer pushes a fitted leap out of the top of the cell.

### Tests

`tools/test_render_quality.py` has 11 checks and runs in CI:

* per-pixel textures, smooth light, see-through cards, kit recolouring and seam normals;
* the supersampling rule;
* straight hems that keep their size;
* the sports idle;
* the grounding rule and the QA tolerance;
* every game pack at HD on the mannequin: twice the size and no clipped move;
* the sports idle builds and passes the QA.

## New in v11.24: players who look different, every move inside its cell, hit boxes in the preview

### Teams and casts that look like real rosters

Every player in a default roster (`forge.py roster`, or **Build the team** / **Build the fighter cast** in the Games
tab) gets a look of their own, made from MakeHuman appearance keys (`forge.py look --keys`):

* hair style and colour, facial hair, skin tone, eye colour and eyebrows;
* the face shape: nose, lips, jaw, chin, cheekbones, eyes, ears;
* muscles to suit their type, so a heavy brawler is more muscular than a small agile fighter.

Each player is built as a realistic MakeHuman character in the roster's kit, with their **squad number on the back**
of the shirt. The looks are repeatable, so a roster rebuilds the same. A roster file can give any player a `"look"`
of their own. Without the MakeHuman library (`forge.py human --setup --full`), players fall back to the mannequin
with different bodies, and `roster.json` records which way each was built.

Two bugs fixed on the way:

* The look builder's GLB had grey hair in Unity, Unreal, raylib and Sprite Forge's own sprites. The colour was only a
  vertex colour; it is now baked into the hair, brow and lash textures.
* The look builder ignored `--kit`, so every look came out in the home kit. It now uses the kit you give.

Sprites and portraits no longer draw the see-through parts of hair cards as solid, which hid faces behind long hair.

### No move cut off at the edge of its cell

Moves are drawn on a padded canvas, then fitted into the cell:

1. **One shared shift.** The pivot and ground line move as little as possible so every move fits, and they stay the
   same for every move, so every engine format stays right.
2. **Its own pivot.** A move that can't fit alongside the others gets its own pivot and ground line, written per move
   in `game_character.json` and `atlas.json`.
3. **One smaller scale.** A rig too big for the cell (a tall rig's leap) is drawn smaller, once, for every move.

A ball flying off on its own may still leave the cell: the fit and the QA look at the character, not the prop. The
Gaelic pack draws its players at 58% of the frame height (new pack key `"figure"`, default 0.62) so the leap catch
fits.

Result: the sprite QA's **clipped** FAILs are gone from all 12 packs on the mannequin, and from the tall library rig
on the packs with leaps and dives. Before, there were 9 clipped moves on the mannequin, plus the boxing KO, block and
jumps on library rigs.

### Hit boxes in the Games tab

With **Show: built character**, the preview draws over the sprite:

* the **hurt boxes** (head, body, legs) in blue;
* the **hit box** on the frames where a strike can land, in red, marked "HIT";
* the **pivot**, at the feet.

These are the same boxes the engines get. Untick **hit boxes** to hide them.

### Tests

`tools/test_roster_look.py` has 9 checks and runs in CI:

* every game's default roster gives every player a valid, distinct, repeatable look;
* the look and build command lines are right;
* hair colour is baked into its texture;
* the squad number is readable on the back and not on the front;
* see-through card faces are skipped;
* cell fit works on synthetic frames;
* all 12 packs on the mannequin and 4 on the tall rig have no clipped moves, and their pivots agree between
  `game_character.json` and `atlas.json`;
* a real roster is built from looks (when the MakeHuman library is installed).

`test_game_tabs` adds check 14: hit boxes on the hit frame.

## New in v11.23: teams and casts, portraits, and ready-to-open engine projects (Godot, Unity, Unreal, raylib, web, pygame)

### Teams and fighter casts in one go

```
forge.py roster --game soccer --out rosters/
forge.py roster --game fighting --size 6 --out rosters/
forge.py roster --file my_roster.json --out rosters/
```

* **`--game soccer`** builds two sides, Home and Away, with 5 players each by default. The keeper wears the keeper's
  kit and the others are playmakers, strikers and all-rounders with different builds.
* **`--game fighting --size 6`** builds a cast of six fighters: every fighter type, each with its own body.
* **`--file`** takes your own list, mixing mannequins, library rigs and your captures. The format is in
  `sforge/roster.py`.

Every player is an ordinary build, with sprites, an atlas, `game_character.json` and the 3D model, plus a
**portrait**. The portrait is a head-and-shoulders render from the player's own model; a build without a model gets a
crop of its idle sprite instead. `forge.py portrait BUILD_DIR` makes one for any build.

The roster itself gets:

* `roster.json`: the sides, and for each player the name, kit, type, body, files and QA;
* `select_screen.png`: the portraits in a select-screen grid;
* `team_sheet.png`: each side's line-up.

### One-click engine projects

```
forge.py engine ENGINE BUILD_OR_ROSTER --out DIR
```

`ENGINE` is godot, unity, unreal, raylib, web, pygame, or all. It turns one character or a whole roster into a
project that engine opens directly. Each project holds the characters (sprites, move events, hit and hurt boxes,
portraits, and the 3D model with every move as an animation) and a demo that plays them side by side. LEFT / RIGHT
change the move.

| Engine | Open it | What you get |
|---|---|---|
| Godot 4 | `project.godot`, then Play | `main.tscn` plays the sprites with the move events. `demo3d.tscn` loads each model at run time and plays its animations. The Sprite Forge addon is enabled. |
| Unity 2021.3+ | Add the folder in Unity Hub | On first open, every character is imported: sliced sprites, clips, prefab, hit and hurt boxes, `model.fbx` with an Animator. `Assets/Scenes/SpriteForgeDemo.unity` is saved. |
| Unreal Engine 5 | `SpriteForgeDemo.uproject` | On first open, every character is imported: a Paper2D sprite per frame, a flipbook per move at its fps, the skeletal mesh with every move as an animation, the move events as sync markers. The level `/Game/SpriteForge/Demo` is saved. |
| raylib 5.5+ | `make`, then `./demo` and `./demo3d` | Sprites with the hit window, and the models with their animations. Joints are rewritten as 8-bit indices for raylib. |
| Web | `python serve.py` | `index.html` plays the sprites in a canvas; `viewer3d.html` shows the models in three.js. |
| pygame | `python play.py` | A small player; its `Character` class is a loader you can copy. |

### In the Studio's Games tab

* **Build the team** or **Build the fighter cast**, with a size. The select screen shows when it's done.
* **Export project** for any engine, or all of them, from the last build or roster. **Open folder** opens it.
* **Show: built character** plays the last build's own sprites in the preview instead of the figure. That build can
  be the mannequin, a library rig or your capture.

### Tests

`tools/test_engines.py` (11 checks, in CI):

* every game's default roster validates, and bad rosters are refused;
* a real two-fighter roster builds, with portraits from the models;
* all six projects are made from a roster and from a single build;
* raylib's 8-bit-joint models read back identical;
* the Godot project runs headless (`--godot BIN`) and loads every character and animation in 2D and 3D;
* the Unity project agrees with the bundled importer;
* the Unreal import script runs against a recording stand-in of UE5's Python API (`tools/unreal_stub.py`), with
  every flipbook, frame rect, fps, animation and event marker checked;
* the raylib demos compile and run (`--raylib PATH`);
* the web page loads in a browser;
* the pygame player runs.

`test_game_tabs` gains the preview, roster and export checks from the tab.

**Not run inside Unity or Unreal.** Neither engine runs on this machine. Godot 4.3, raylib 5.5, Chromium and pygame
were run.

## New in v11.22: 3D joint tracks onto the shared skeleton (fed back from Arena FC)

Body-pose datasets give named 3D joints per frame, not a rig. **`sforge/jointtrack.py`** fits them onto the shared
skeleton with the same per-frame IK as `forge.py mocap`. It reads SkillCorner open body pose and OpenPose BODY_25
names, with a Z-up or Y-up source. It returns motion-library keys and a fit report (bone error per segment), and
`keys_record()` saves them as a library move with a licence record.

- **Gaps:** missing joints borrow the nearest joint the source has, and short gaps in the track are interpolated.
- **Facing:** the take is turned to face forward at a chosen frame, such as the contact frame of a kick.
- **Root motion:** the root stays in place; the game supplies root motion.

Arena FC uses it to import 56 real in-match moves from two A-League matches: shots, passes, lofted passes,
clearances, first touches, ball wins and dribble loops (`arena-fc/Tools/import_skillcorner_pose.py`, MIT data).
The fits have a mean bone error of 1.4–2.6°. `tools/test_jointtrack.py` checks the fitter end to end: a known clip
is turned into joint tracks and fitted back.

Limits: single-person tracks only. There are no finger, twist or face channels. The ankle comes from the
heel-to-toe line. Precision is the source's: broadcast pose is accurate to 7–15 cm per joint.

## New in v11.21: field-sport moves and bind-pose conform (fed back from Arena FC)

Arena FC (the soccer game in `arena-fc/`) asked Sprite Forge for actions it had no clip for, and played
stand-ins: every skill move came out as a sharp cut, thigh control as a toe flick, a punch as a fist *shot* and a
headbutt as a jumping header. **`sforge/fieldsport_motions.py`** adds 15 clips for ball games on a pitch, authored for
the action they name, with the ball keyed through each touch:

- skill moves: `fs_stepover`, `fs_roulette`, `fs_drag_back`, `fs_elastico`, `fs_ball_roll`, `fs_rainbow_flick`,
  `fs_fake_shot`, `fs_heel_to_heel`
- aerial control and strikes: `fs_thigh_control`, `fs_chip_shot`, `fs_trivela` (outside of the boot),
  `fs_bicycle_kick`, `fs_keeper_penalty_set`
- violent conduct: `fs_punch`, `fs_headbutt`

They register in the motion library automatically, carry event frames as fractions (`fieldsport_motions.EVENTS`:
ball_contact, footsteps, hit window), and the **soccer** game pack offers ten of them as moves.

**`fieldsport_motions.qa(name)`** checks a clip for the two bugs that hurt Arena most: an arm raised over the shoulder
in a clip with no reason for it (players stood with their hands up at every free kick), and a ball clip with no ball
at its contact frame.

**`sforge/bindconform.py`** is the fix for Arena's worst animation bug. A mesh sculpted in one rest pose (MakeHuman's
A-pose arms) but skinned to a skeleton bound in another (arms hanging) carries the difference into every frame of
every clip: all 71 of Arena's clips had the arms 45-60 deg too far out and up. `conform_to_bind(V, N, J, W, src_heads,
tgt_heads, parents)` re-poses the mesh into the target bind pose before skinning - rotation only, about the source's
own joints, nothing stretched, aligned bones untouched. Any game that skins a sculpt to its own skeleton should call it.

Test: `python tools/test_fieldsport.py` (clips, QA, game pack, conform).

## New in v11.19: a Games tab with a page per kind of game

The Studio's **Games** tab (`sforge/gui_games.py`) lists every kind of game Sprite Forge builds characters for:
basketball, beat 'em up, boxing, fighting, Gaelic football, kart racer, platformer, shooter, soccer, tennis / padel,
top-down RPG and wrestling. Any pack JSON you add to `game_packs/` gets a page too.

Each game's page shows:

* **What the game needs:** its description, camera (side-on, three-quarter or top-down 8-way), frame size, the props
  the game draws (ball, racket, gun...) and its notes.
* **Its moves:** one row per move with the clip it plays, and whether that is its own clip, one **borrowed** from
  another move (header plays jump) or **procedural**. Also the frames and fps, whether it loops, its game events
  (ball contact, hit window, release, footsteps) and, after a build, its sprite QA.
  - Pick a move and it plays on the mannequin, side-on or front-on. Its events are marked on the timeline and named
    as the figure passes them.
  - Below the table: where the clip came from, its licence, and what the last build actually drew it from.
* **The character:** the mannequin (female-male, muscle and weight sliders), a library rig, or your own captured
  GLB / FBX. Only the settings that fit the game are offered:
  - fighter types (quick striker, heavy brawler, small agile, big boss) for boxing, fighting, wrestling and
    beat 'em up;
  - player types (playmaker, keeper) and a **team kit** for soccer, Gaelic and basketball.
* **Build this game's character:** runs `forge.py build --game PACK ...` in the background with the log streamed.
  Then it shows the sheet preview, and colours each move by its QA (clipping, feet drift, pops, loop seams).
* **Shot list:** what to film to replace the borrowed and procedural moves with your own.

A **Motions** folder (your own library, e.g. CMU or recorded moves) can be set, and every game's moves are then
resolved against it.

Tests: `xvfb-run -a python tools/test_game_tabs.py [--motion-library DIR]` (11 checks, in CI). It covers every pack in
`game_packs/`, not only the shipped twelve:

* every move of every game has a clip that plays;
* its events fall on its timeline;
* each game offers the right settings;
* the build line really builds a mannequin soccer player in a kit and a library-rig boxer;
* the page reads back the QA and sources;
* every page fills and every move draws in the window, and Build and Shot list run from the tab.

Known: two shipped moves fail their sprite QA today. The soccer tackle touches the cell edge, and the procedural
boxing KO fails. The tab shows both in red.

## New in v11.18: Capture and Motion tabs in the Studio

`python forge.py gui` (or `run_studio`) now has two more tabs, so the video-to-character pipeline and the motion
library no longer need the command line.

* **Capture tab** (`sforge/gui_capture.py`): a turnaround video, or one photo, of a person becomes a rigged,
  textured 3D character.
  - Pick the video, give a name and the person's height, and press **Capture**. It runs `forge.py capture`.
  - Options: body (auto / male / female), a face close-up photo, the **neutral garment** picker (`--neutral`),
    separate clothes and hair meshes, face fit, taking out the room's light, camera alignment, texture size and
    frames per second.
  - The log streams as it runs. Five steps light up as they go: Track, Fit, Texture, Export, Check.
  - Every finished capture in the output folder is listed. Pick one to see its turntable, its fit and held-out
    scores in plain words, and its files (GLB, FBX, OBJ, MakeHuman, MPFB).
  - **Rebuild texture** reruns `--rebuild` on a capture without refitting. **Download models** fetches the pose
    models once.
  - The inputs are checked first: a missing video, a name with spaces, a height that isn't in centimetres.
* **Motion tab** (`sforge/gui_motion.py`): the shared-skeleton motion library (`forge.py motion`).
  - Every move (the shipped starter set, recorded clips, Mixamo, CMU and Quaternius imports) is listed with its
    category, length, whether it loops, where it came from and its licence. Search and filter by category.
  - Pick a move and it plays on the mannequin, front-on and side-on, with play / pause, a scrubber and speed.
  - The motion checks (`tools/check_motion.py`: length, size, floor, pops, facing, feet) show beside it as pass /
    fail lines.
  - **Import file** (BVH / FBX / GLB / JSON, with its licence), **Record from video**, **Clean move** (foot plant,
    weight shift, anticipation, follow-through) and **Retarget onto** (a GLB / FBX rig) run the matching
    `forge.py motion` commands. The result appears in the list.
* **`tools/test_studio_tabs.py`**: 12 checks.
  - Without a window: the form's options become the right capture flags; the progress steps follow the real log
    lines; bad inputs are refused; captures are found and read; every starter move is listed and can be drawn;
    the views are the right way round; the checks run.
  - With a window (`xvfb-run` on a server): the Studio opens with both tabs; picking a move draws it; Import
    turns a BVH into a playable move; a failed capture says so plainly.
  - Work started from either tab runs in a background thread that only queues its output. The tab reads the
    queue on Tk's own thread, because Tk isn't thread-safe.

## New in v11.17: white balance from a neutral garment; the face's colour matched to the skin

* **The problem.** A video's colour is the room's light as much as the clothes'. Tmon's video has lamps and a
  window, and the phone's white balance swings between them: his hoodie is blue-grey by the window and
  orange-brown under the lamps. Most frames are lamp-lit, so the model came out brown.
  - Taking out the frames' bias doesn't help. The blend already gives every frame about the same say (it leant by
    1-3%). The colour is what the video shows.
  - Automatic white balance can't tell a warm room from a warm jumper. On these videos, grey-world and grey-edge
    disagree, so the person has to say.
* **`forge.py capture VIDEO --neutral upper|lower|shoes`.** Name a garment that is white, grey or black. The
  exported texture is white-balanced so that garment comes out neutral, with its lightness kept and everything
  else corrected the same way.
  - `capture_texture.neutral_gain` / `white_balance`.
  - Blown-out and black texels (a print, a shadow) don't steer it.
  - Under 200 texels of the garment seen: nothing is changed.
  - The held-out check and the lighting file still use the texture as filmed.
* **The face's colour matched to the person's other skin (`capture_texture.face_to_skin`).**
  - The face is painted from the frames that saw it front-on, often under a different light from the ones that
    saw the neck and hands.
  - Its colour (a, b, not its lightness) moves 80% of the way to the median of the person's other skin, weighted
    by how much each texel is face, at most 15.
  - A step under 3 is left. `SF_FACE_SKIN=0` switches it off.
  - On the sample captures the step is small (3-4).
* **`tools/test_white_balance.py`**: 8 checks, no assets:
  - the named garment comes out grey with its lightness kept, and the other parts are corrected the same way;
  - lower and shoes work, and an unknown part is refused;
  - too little seen: nothing changes;
  - a white print doesn't steer it;
  - a cool face moves to the skin's colour with its lightness kept; the move follows the face weight; a matching
    face is left alone; a huge step is capped.
* **Tmon.** His face's frames and his neck and hands' frames both come out grey-pale, because his video is dim
  and mixed. White-balancing to any of his garments makes him cooler, not warmer. The footage limits him; a
  close-up face photo in even daylight (`--face-photo`) or a re-film in even light would do more.

## New in v11.16: no white band under the chin; the collar stays below the jaw

* **The white band under the jaw (Mike).** The video sees his white shirt collar past the chin. Each frame's
  exposure gain pushed those colours above pure white. The chin rule only dropped texels near a garment's
  average colour, so these over-bright ones were kept.
  - Body texels under the chin and on the neck that the video labels clothes are now dropped whatever their
    colour, and refilled from the skin round them.
  - Colours are clipped to 0-255 before the cleanup.
* **The scalp step leaves the underside of the jaw alone.** v11.13's scalp check had counted the underside of
  the jaw as scalp. That part is now left to the chin rule. A refilled scalp patch also keeps the lightness range
  of its own kind, so a collar-lit neighbour can't make it white.
* **The collar stays below the jaw (`capture_layers.under_jaw`).** The collar's height is measured from the
  bottom of the neck, which at the front is close under the chin. Each worn neck vertex now stays `JAW_GAP`
  (1.5 cm) below the head's surface above it. At the back, the collar still goes up as far as the neck allows.
* **Tests:**
  - New `tools/test_collar.py` (MakeHuman assets, no videos): 18 checks on a man, a woman and a smaller body,
    with clothes voted up the whole neck and only at its base. Nothing is worn under the jaw; the collar still
    goes up the back; a low collar stays low; the head, hands and feet are never worn.
  - `tools/test_head_look.py` check 22: a refilled scalp patch next to bright texels keeps the skin's lightness.

## New in v11.15: the face joins the head - no "transplanted" face from the side

The face is painted almost from one frame, so its eyes don't double. The sides of the head are blended from many
frames. Switched at a hard line, the face kept its frame's own light and white balance, and from the side it
looked set into the head: a seam ran from the temple to the jaw (Mike, Tmon).

* **Gradual blend (`capture_texture.face_weight`).** How much a texel is "face" now rises gradually: 0..1 as the
  head turns forward, and fading out towards the crown. The face's single-frame weighting, its colour gain and the
  rule that keeps guessed head turns off the face all follow that gradual weight. `SF_FACE_FEATHER=0` gives the
  old hard line.
* **Colours meet halfway (`capture_texture.face_join`).** Along the face's edge, the colour difference between
  face and head is measured and smoothed over 2 cm. The face and the sides each take half of it at the edge,
  fading to nothing 3.5 cm away. The middle of the face, the back of the head and fine detail (eyes, stubble)
  don't change. `SF_FACE_JOIN=0` switches it off.
* **The head's length from the side (`capture_face.fit_head_depth`).**
  - The face fit sees the head mostly from the front, so it left the head's length at MakeHuman's average. For
    most people that is too long: the cheek between the ear and the nose looked stretched.
  - In the side-on frames (70-110 degrees round), the width of the person's silhouette along the row through the
    nose is compared with the fitted body drawn through the same camera. `head_depth` is then set to match.
  - It only ever shortens, by up to 15% (the slider itself gives about 7%), because the video's silhouette
    includes the hair.
  - It changes nothing if there are fewer than 4 side-on frames or they disagree.
  - Sample captures:
    - Mike: x1.12 too long; changed head_depth 0 -> -1 (nose to back 22.8 -> 21.2 cm).
    - PR: x1.14 too long; changed head_depth 0 -> -1.
    - Declan: x1.05 too long; changed head_depth 0.05 -> -0.59.
    - Tmon: frames disagree; left alone.
  - `SF_HEAD_DEPTH=0` switches it off.
* **Tests: `tools/test_head_look.py` checks 12-21.**
  - No step anywhere in the face weight.
  - A pale face set into a warm head: the edge step more than halves.
  - The face middle and back unchanged.
  - Detail kept.
  - A matching face is left alone.
  - The head length: the silhouette row through the nose is measured; a long head is shortened; one shorter than
    the video's is left alone; disagreeing or too few frames are left alone.
* **Still left on the heads:** a shirt collar reaching up under the jaw (white under Mike's chin when his layers
  are rebuilt), the hairline's hard steps, and Tmon's face colour from his mixed lamp and window light.

## New in v11.14: no more tiled heads - the hair shell's texture map

* **The cause.** The hair shell's texture map was a straight top-down view of the head.
  - Below the widest part of the head, the back and sides fold under the top in that view.
  - So 6,000-14,000 texels of each sample head's map belonged to two places at once, and each place was painted
    with the other's colour. That made the angular, tiled patches on the back and sides of every head.
  - The texture was being blended correctly; it was being stored in a map that overlapped itself.
* **The fix: `capture_layers.shell_uv` flattens the shell like a peeled cap.**
  - It starts from the head's own angles: the angle down from the crown is the distance from the centre of the
    map, and the direction round the head is the angle round the map, with the front at the top.
  - Where that folds (over the ears, below the back of the skull), the area round the fold is laid out again with
    mean-value weights until nothing folds. A cap that still folds is laid with its rim on a circle, which is
    always one-to-one.
  - A shell in two pieces (a parting) gets a band of the map for each piece. Single-vertex gaps in the hair votes
    are closed first.
  - **`capture_layers.uv_overlap(F, fuv)`** counts texels claimed by two triangles in any atlas.
  - All four sample heads go from 6,069-14,042 shared texels to 0. Mike's back of head is smooth now.
* **`tools/test_hair_uv.py`** (needs the MakeHuman assets, no videos) runs 6 checks on 3 head shapes × 6
  hairstyles (cap, short, down to the nape, split by a parting, patchy votes, shaved):
  - no texel claimed twice;
  - no triangle folded;
  - the map stays in its quarter;
  - front at the top;
  - no part of the shell starved of texels;
  - and that the old top-down map fails the first check.
* **Not fixed by this:**
  - Tmon's head is still patchy in colour. That is light: his video mixes lamp and window light. It is not tiling.
  - The front edge of the hairline still has a few hard steps where the hair shell meets the skin.
  - Existing captures pick up the new map when their layers are rebuilt (`forge.py capture` again).

## New in v11.13: heads - no ghost face in profile, no window-blue scalp

* **The head follows the camera.** In a turnaround people turn their head towards the phone. The face tracker
  only gives the head's own pose up to about 60 degrees; past that the bake used the body's camera, so a face
  turned to the camera was painted on the side or back of the head (a second face in profile on Declan, PR and
  Tmon).
  - `capture_texture.head_turn_model` fits how far the person turns their head against the body's angle in the
    frames the tracker covers.
  - `turned_head_poses` carries that turn into the other frames, rotating the head about the neck.
  - It holds the end of the tracked range to 90 degrees and fades to no turn by 150 degrees (from behind, the head
    cannot face the camera). `SF_HEAD_TURN=0` switches it off.
  - A frame given a turned head (a guess) paints only the sides and back of the head, never the face itself; when
    it painted the cheeks too, Declan's face came out grey.
* **Hair and scalp are checked for patches of the wrong colour.** The back of a head is often seen only in frames
  lit by a window, so Tmon's crown came out brown with blue patches. In `capture_clean`:
  - A hair texel far in colour (a, b) from the hair's median is dropped, unless it is close to the skin's colour
    (the hairline, sideburns and ears show skin through the shell). Dropped texels are filled from the hair round
    them.
  - The hair's colour is pulled most of the way to its median. The light and dark of the strands are kept.
  - Scalp and the sides of the head (not the face) are dropped only when far from both the head's skin and its
    hair. They are refilled from scalp of their own kind: lightness from round them, colour from that kind's
    median.
  - Dyed, red and blonde hair keep their own colour. `SF_HAIR_EVEN=0` switches it off.
* **`tools/test_head_look.py`** runs 11 checks with no assets: the turn model inside and past the tracked range,
  the fade with no jump, the pivot at the neck, an off-colour patch filled, each hair colour kept, strands kept,
  and a fringe beside skin kept.
* **On the five sample captures:**
  - Declan's profile ghost face is gone, and his face keeps its colour.
  - Tmon's blue crown is mostly gone. A small purple patch behind one ear is left.
  - Mike and PR are unchanged apart from more even hair.
  - The blotchy, tiled look of a head painted from many frames is not fixed yet; that is next.

## New in v11.12: Mixamo moves, and Gaelic football moves from key poses

* **`tools/import_mixamo.py FOLDER_OR_ZIP --library DIR`** imports Mixamo FBX downloads.
  - Download them from mixamo.com as FBX Binary, Without Skin, 30 fps, with no keyframe reduction and In Place
    unticked.
  - Known Mixamo names get the names the packs look for, e.g. `Receive Punch To The Face` becomes `hit_face`.
  - Goalkeeper dives are sorted into left and right by measuring which way the hips travel.
  - Every clip goes through `check_motion`. Mixamo files may be used in games but not redistributed, so they go
    only to your own library.
* **First batch (57 files, 56 kept):**
  - punches, blocks, hit reactions, a knockdown and a fighting idle;
  - headers, slide tackles and a trip;
  - goalkeeper dives (both ways) and a goalkeeper catch;
  - taunts and victories.

  `Standing Up` came in upside down, with the old importer too. The new get-up rule caught it and it is left out.
* **`tools/pose_from_image.py`** gives a key pose from a still picture. It uses the same MediaPipe model and solver
  as `motion record`, and `--sheet` draws each picture beside the solved pose.
* **`tools/build_gaelic_moves.py`** builds six Gaelic moves from key poses: `gaa_hand_pass`, `gaa_kick`,
  `gaa_solo`, `gaa_high_catch`, `gaa_toe_lift` and `gaa_carry`. They keep only joint angles, are turned to face
  forward, and are written to your own library.
* **Packs:**
  - Gaelic: hand and fist pass, kick passes and points, solo, high and leap catches, toe-lift pick-up, carry,
    keeper catch and dives, a trip for the fall, spin, keeper throw-out, and an arms-up victory.
  - Boxing: idle, jab, cross, hook, block, hit and knockdown.
  - Fighting: idle, combo special, block, hit, taunt and victory.
  - Soccer: header, keeper save, slide tackle and celebration.
  - Hit reactions in the other packs.
* **`check_motion`:**
  - a get-up must end standing the right way up;
  - a catch may be overhead;
  - seated kart clips are sized as seated.

  All 109 library clips pass except 3: a lying idle and two small flinches.
* **Sprite QA across the 12 packs:**
  - 3 fails, down from 6. Gaelic now has none, with its score up from 33 to 67.
  - Tried and dropped: Mixamo's idle. It stands 4 px lower than the other clips, so every other move then looked
    like it floated.
* **Tests:** `test_motion_gaps` is now 22 checks. It adds the get-up rule, the Mixamo name mapping, key-pose moves
  facing forward with the high catch leaving the ground, and a move with missing poses being skipped.

## New in v11.11: the moves the game packs were missing, and a check for any clip

* **12 more CMU moves** (`tools/import_cmu.py`, into your own library - CMU clips are never shipped):
  `block_left`, `dodge_duck`, `stumble` (hit reaction), `ko_fall_back`, `stop_sudden`, `sidestep_shuffle`,
  `juke_feint`, `swing_forehand`, `celebrate_jump`, `limp_walk`, `catch_chest`, `catch_low`.
* **11 CC0 moves from Quaternius' Universal Animation Library 1 and 2** (`tools/import_quaternius.py`). These are
  public domain, so unlike the CMU clips they may be shipped:
  - `death_fall`, `roll`, `sprint`;
  - `drive_seated` for kart;
  - `pistol_shoot` and `pistol_reload` for the shooter;
  - `cast_spell`, `dance`;
  - `slide_tackle` for soccer;
  - `throw_overhand_q`, `idle_arms_folded` (a taunt).

  Each clip was looked at and passes `check_motion`. Left out: UAL2's knockback (ends upside down), its lay-to-idle
  (runs backwards) and its hook (breaks mid-swing), plus UAL1's head and chest hits, which are too small to read
  as hits.

  Importing it needed two fixes. Rigify rigs that name their bones `DEF-hips`, `DEF-neck` and `DEF-head` now map,
  and clip names are matched ignoring case.
* **Keeper dives in the CC0 starter** (`dive_left`, `dive_right`): they were procedural only, so the Gaelic
  pack's dives fell back to the standing save.
* **Packs use them.** Soccer gets a slide tackle, shooter pistol shots and reloads, kart a seated driving loop, the
  top-down RPG a spell cast, fighting and wrestling a folded-arms taunt, and Gaelic a sprint.
  Boxing gets a real block, slip, stagger and knockout. Fighting gets block, stagger and a
  victory jump. Gaelic gets the sudden stop, juke, sidestep shuffle, pick-up, celebrations, fall and both keeper
  dives. Platformer and shooter get a fall, tennis a forehand swing, and soccer a celebration. Without a CMU
  library, KO / fall / die now use their own procedural motions (a real fall) instead of the starter's hit.
* **Import fixes found by the new check:**
  - `soccer_kick` and `soccer_shoot` came in facing backwards. The strike was aimed by its furthest reach, which
    can be the backswing; now the body must face within 90 degrees of the opponent unless it spins.
  - `walk_casual` walked sideways: its loop was cut where the walker had turned. Clips now face forward over
    what is kept, and the walk is a straight take (07_01).
  - `get_up`'s standing part floated 13 cm: one floor for a take that lies and then stands. The floor now
    follows the feet while standing and the body while lying.
* **Sprites are drawn in place.** A move that travels more than 35 cm (a walk cycle, a stumble, a shuffle) has
  its travel taken out of the sprite cell. The game moves the character, and 3D takes keep their root motion.
  Sprite QA over all 12 packs, before and after: 41 fails become 6 (the 6 left are kicks and throws whose foot
  or hand reaches the cell edge).
* **`tools/check_motion.py`** is the gate for any clip:
  - `check_motion.py LIBRARY_DIR` checks clips; `--pack NAME --library DIR` checks what a pack will use,
    procedural fallbacks included.
  - It checks size, the floor, glitches between frames, length, loops (end where they start, and go straight),
    and facing.
  - It also checks that the move does what its name says: a block raises the hands in front, a KO ends on the
    ground, a dodge ducks, a celebration lifts a hand over the head, a stop slows down, a sidestep moves
    sideways, a catch takes the hands up and forward, a dive gets low and travels, and a swing whips a hand
    round.
  - All 46 clips in the library pass (35 CMU, 11 Quaternius), and so do the 18 starter clips. Every pack passes with a CMU library. Without one,
    a few Gaelic and tennis moves are flagged as stand-ins (stop, sidestep, forehand).
* **Tests:** `tools/test_motion_gaps.py` (18 checks, synthetic, including the Rigify and Mixamo bone names). It covers a walk that turns a corner, a kick
  peaking on its backswing, a spin kick, and a take lying lower than it stands; each fails on the old importer.
  It also feeds the checker a broken clip of each kind and makes sure it is caught for its own reason.
  `test_mocap_import`, `test_motion_v114` and `test_v115` still pass.
* **Not yet:** a tackle, a header, wrestling grapples and a backhand. CMU has no takes for these; the Gaelic
  poses you film, or `motion record`, can fill them.

## New in v11.10: every frame's camera registered to its own picture, and checks for any new video

* **Registration** (`capture_register.py`, on by default, `--no-register` to skip): the landmark cameras leave
  each frame 5-10 px off what its picture shows. A first plain texture is drawn from each frame's camera, DIS
  optical flow (forward / backward checked, away from the outline, only where there is texture) says where each
  visible vertex really is, and the camera is re-solved to those points - position first, the angles held close.
  Three rounds. A move is **kept only if** the misfit left falls by at least 10%, the outline does not get worse
  (IoU drop under 0.005), it is a correction and not a jump (under 8 degrees and 12% of the distance per round)
  and it rests on at least 150 trusted points over a quarter of the person's height. Otherwise the frame keeps
  its camera and the report says why.
* **Measured on the five:** median misfit Tmon 13.6 -> 4.4 px, Mike 6.3 -> 3.5, Declan 7.2 -> 5.3, PR 8.4 -> 7.3,
  Anna 8.5 -> 7.6; no frame that moved got worse; silhouette IoU unchanged; held-out SSIM within +-0.006. Real people
  also move a little between frames (arms, sway), which no camera can absorb: the texture's own flow alignment
  (v11.9) takes care of what is left. The gain is real but modest.
* **Hands and feet keep the landmark camera.** The registered camera lines up the bulk of the body; hands and feet
  move on their own, and through it PR's navy socks and Mike's white ones were partly painted from the floor and the
  skin. They are drawn through the landmark fit's camera, which was placed by the ankle, toe and wrist keypoints.
* **Shoes and socks keep their own colour** (found while checking v11.10): feet the video calls worn are a
  material of their own in the clean - they were pulled to the colour of whatever cluster they fell in (PR's navy
  socks shared one with shaded skin), and the rings may no longer paint them with a skin-coloured band (Declan's
  black socks). Anna's patterned socks now read as socks rather than bare feet. Still wrong: Tmon's white trainers
  come out tan (a wooden floor round them in every frame); v11.9 had them black.
* **`tools/check_capture.py CAPTURE_DIR`** (or `--all captures/`): the gate for any new video's capture - files
  and a valid skinned GLB, held-out IoU >= 0.70, texture coverage, registration (misfit did not grow, no frame
  worse, no move beyond a correction; a warning when most frames are still far off), face landmark error.
* **Tests that do not depend on the five samples:**
  - `tools/test_register.py` (14 checks): knocked-off cameras come back (3.6 -> 0.2 px) and no frame gets
    worse; a right camera stays put; a frame that is not the person, a camera 15 degrees off (a tracking
    failure) and a tiny person are all left alone; half the person hidden never ends up worse; and seven kinds of
    video the samples do not have - full body, a close-up with the legs cut off, a dim noisy room, motion blur,
    heavy JPEG, a ragged segmentation mask, plain one-colour clothes - never worse, and better wherever there is
    detail to align to.
  - `tools/test_feet.py` (7 checks): adds dark socks in the skin's colour cluster keeping their colour, white
    trainers under black trousers staying white, bare feet still cleaned as skin.
  - `tools/test_capture.py` (10 checks): the whole synthetic capture, now with its cameras knocked off by what a
    real video leaves: misfit in the pictures halved, cameras a third of the way back, texture closer to the
    truth, and every moved frame keeping its landmark camera for the hands and feet.
  - `tools/test_check_capture.py` (12 checks): the gate passes a good capture and catches each kind of broken
    one for its own reason; a one-photo capture is judged on its photo fit.

## New in v11.9: a sharper texture - prints, lettering and stripes survive

The cameras and the fitted body put each point of the texture within a centimetre or two of where a frame shows
it: enough for the silhouette, not for a 1 cm stripe or a logo's lettering. Averaged over frames that each miss by
a different centimetre, thin detail went grey - and the clean then treated the grey as a blotch.

* **Frames aligned by optical flow** (`capture_texture.align_flows`): a first texture is drawn into every frame
  from its camera, and the frame is matched to the drawing (DIS optical flow on locally normalised grey, so
  exposure does not matter). The flow is smoothed, capped at 3% of the frame and fades out over the person's outer
  15 px; hands and feet keep the camera's projection (on the outline the flow matches the floor). The texture is
  then baked again from the corrected positions. Typical shift: 7-10 px per frame.
* **Detail put back after the clean**: the clean still decides each garment's colours and edges. On the clothes,
  where at least two views agree (spread under 25), the clean texture's own blur plus the aligned bake's fine
  detail replaces it - a print's lettering, a stripe, a shirt's folds - but not where the clean moved a garment
  edge (a hem snapped to its ring).
* `SF_ALIGN=0` turns it off. It costs one extra bake per capture.
* **Measured** (all five rebuilt): silhouette IoU unchanged. With the registration taken out of the comparison
  (each held-out frame warped onto the render by optical flow), the rendered detail rises towards the footage's
  (Mike 0.73 -> 0.83 of the frames' detail, PR 0.93 -> 0.97). Declan's frames are softer than his texture already
  and gain noise rather than detail (aligned SSIM 0.754 -> 0.735). The plain held-out SSIM drops 0.01-0.03: a
  sharper texture seen through a camera that is a centimetre off scores lower than a blurred one.
* A synthetic capture with perfect cameras gets a 0.5 px median shift - the flow does not invent motion.

## New in v11.8: hands, feet in socks and shoes, no trousers on the feet

* **Hands** read as skin: at game size a hand is a few pixels, and the bake gave it fingers stained with the
  trousers it hung against and red / dark streaks. Unless the video says they are not skin (gloves), hand texels
  are pulled to the body's skin colour (colour nearly all the way, lightness half-way so knuckles keep some shape).
* **Feet in socks or shoes have no toes** (`capture_layers.shod_feet`): MakeHuman's foot is bare, with five
  modelled toes, so a sock showed five white toes. When the video calls the feet something worn, the front of each
  foot becomes one rounded toe box of the same length, width and height, sole on the floor. Bare feet are untouched.
* **No trouser colour on the feet**: below a trouser leg's hem its colour was only forbidden for the band's
  choice, so feet seen through the hem in most frames stayed jeans-blue. Now those texels are refilled too, and
  dark shoes and socks show.
* `tools/test_feet.py` (needs the MakeHuman assets, 4 checks).
* **Tried and dropped:** keeping vertical stripes (a material that holds one angle round the limb). The bake blurs
  thin stripes into a grey that also covers the rest of the trousers, so keeping it made PR's black track pants grey.
  Thin stripes need a sharper bake first. Clothes folds as a normal map are for 3D engines, not the sprites, and
  are left for later.
* **Rebuilt all five:** silhouette IoU unchanged; held-out colour error up a little more (Mike 10.9 -> 11.3, Tmon
  12.9 -> 13.9, PR 8.3 -> 9.1, Anna and Declan within 0.1) - the hands are now even skin, not what each frame saw.
* **Known:** PR's black socks come out brown (under black trousers their colour is the trousers' colour, which the
  rule above refuses on the feet); Anna's patterned light socks read as bare feet.

## New in v11.7: clothes that read as clothes - clean hems, socks and collars, shirts that stay on the body

Seen in a game, a captured character was judged by its edges: a ragged shorts hem, one white sock and one brown,
a white blob at the collar, dark shorts colour on the knees, and the shirt's tails painted onto the thighs, so they
swung with the leg in a kick. v11.7 treats a garment edge as what it is - a ring round the limb.

* **Rings** (`capture_rings.py`): every point on an arm or leg gets its distance along the limb (shoulder / hip ->
  elbow / knee -> wrist / ankle -> toes). Along it, in 1 cm bands with left and right pooled, a 1D labelling with a
  cost per change (Viterbi) decides each band's material. Sleeves, shorts and socks end in one straight edge at the
  same place on both sides.
* **Geometry:** the clothes layer's sleeves and trouser legs are tubes down to that hem; the hem row is slid onto
  the ring, so the edge is straight, not the saw-tooth of whole triangles. A collar is a ring up the neck (at most
  6 cm, as high as the views agree).
* **Texture:** limb texels take their band's material; a torso garment (a shirt) is never painted onto the legs, and
  the trousers' colour never below their hem. Dropped texels are flattened with the material they were filled
  from, so no blotch survives the fill.
* **Socks and shoes:** MediaPipe's "other" class inside the person's own mask is now a "worn" label. Before, it was
  thrown away with the TV and the chair, so white socks were never sampled and the feet came out skin or floor.
* **Faces:** squarer views for the head, the side of the head that joins the face badly is mirrored from the good
  side, and the face's left / right light is evened out.
* `tools/test_rings.py` (synthetic, 6 checks).
* **Trade-off, measured:** held-out silhouette IoU is unchanged for all five (0.785-0.880). Colour error against
  the real held-out frames rises (Mike dE 8.0 -> 10.9, Tmon 10.1 -> 12.9, the others +0.2-0.6): the texture is now
  flatter than the footage, on purpose - the frames' own shading and colour casts were the blotches.
* **Not solved:** thin vertical stripes (PR's track-pant stripes are lost), a two-shade band on Declan's jeans at
  the knee, hand texture, Anna's TV-purple hair.

## New in v11.6: real motion capture, for any game pack

* **Mocap import that works on real takes** (`motion import`): any unit, the leading T-pose skipped, turned to
  face forward, on the floor, 30 fps, arms re-solved to the take (joints within ~2 mm). `--start/--end` and
  `--peak hand_R` cut one move out of a long take; loops are narrowed to their best cycle.
* **Free real motion** (`tools/import_cmu.py --library ~/my_motions`): 23 moves from the CMU Graphics Lab
  database into your own folder. CMU allows them in products, not redistribution of the clips, so they stay out
  of the repo. Build with `--motion-library`.
* **Packs prefer specific clips** (`"prefer": ["jab"]` before `"library": "punch"`): boxing's jab, cross and
  hook, fighting's roundhouse and side kick, soccer's kick and shot, gaelic's fist pass and leap catch, basketball's
  dribble, shot and layup use that clip when you have imported it. Without it, a move that has its own
  animation (a special, a throw, a jump attack) plays that animation. A move that does not (jab, header)
  still uses the generic clip, and the build report says so.
* **Recording real footage** (`motion record --folder`): no T-pose is a note, not a reshoot (`--strict` for the
  old rule); a take where tracking drops out keeps its longest well-tracked stretch; sets go to `--library`.
* `tools/to_egyptian_fighter.py` is gone: `tools/export_ef.py` does the same job.

## New in v11.4: a motion library, and character types that change how a move is performed

Sprite Forge could already retarget a clip and track a video. The moves themselves were still mostly
hand-written poses, one pack per game. v11.4 stores a move once on the shared skeleton and lets any
profile play it.

* **Motion library** (`forge.py motion`, `motion_library/`, your clips in `library/motions/`):
  * `motion record --clip punch=punch.mp4` runs the existing mocap tracker and stores the keys.
  * `motion import clip.bvh` (also FBX / GLB) retargets onto the mannequin and stores the same kind of keys.
  * `motion retarget punch --to sample_lanky` plays that clip on any mapped rig.
  * `motion clean walk` writes foot planting, a weight shift, anticipation and follow-through back into the clip.
  * Names are generic (`punch`, `kick`, `walk`, `tackle`, `shoot`, ...). `fighter14` and `gaelic36` map onto
    them with `--motions punch,kick` or `"motion": "lib:punch"` in a profile. `profiles/motion_demo.json` is a
    small example that is not a fighting-game list.
  * The shipped starter is CC0, generated from the procedural motions. No Mixamo or Meshy clips are included.
* **Character types** (`character_types/*.json`, `--character-type`):
  * `timing`, `stance`, `reach` and `weight` are numbers in the file. A new type is a new file.
  * `heavy_brawler` against `quick_striker`, or `keeper` against `playmaker`, on the same clip: the timing,
    stance width, reach and weight change by a measured amount.
  * Works on library clips and on the existing procedural presets, for a fighter profile or a sports profile.
* **Studio**: Build tab and Start → What to make have the type dropdown and "Use motion library".
  Library tab → Motions... lists the clips. `forge.py help motion` has the commands and the limits.

Limits: the starter is procedural keys, not motion-capture quality. Import drops fingers, twist bones and
facial tracks. A GLB round trip of our own mannequin keeps bone directions and lands the joints within
about 6 cm, because the stored clip is the simpler shared skeleton. Foot planting aims the canonical
thigh, shin and foot on that skeleton and again after retarget; the rest of a GLB is not re-solved.
Character types change shared-skeleton builds. Photo-puppet 2D poses are not redrawn (playback fps still
follows `timing`).

## New in v11.3: captured characters in a game - texture-mapped sprites, cleaner textures
Tried in Egyptian Fighter, where a fighter is about 300 px tall, a captured character showed different faults
from the close-up turntables.

* **Sprites are texture-mapped.** Library rigs with one texture (every `forge.py capture` character) were drawn
  with one flat colour per triangle, which threw the face and all clothing detail away. They are now z-buffered with
  the texture sampled at every pixel (`render.render_textured`), and lit gently so a white shirt doesn't blow out.
  Rigs with several materials or a kit recolour still use the flat path.
* **Texture clean-up** (`sforge/capture_clean.py`, on by default in the bake):
  * Skin far from the person's skin colour is dropped, and hands are always treated as skin.
  * Each surface's colours are clustered (shirt / shorts / skin / socks) and the clusters smoothed over the body in
    3D, left / right symmetric. Speckles go and garment edges come out clean.
  * Unseen and dropped texels are filled on the body in 3D: from their mirror image first, then from the nearest
    kept texels of the same cluster, bone or layer. Before, they were inpainted in 2D across UV islands.
  * Light / dark bands inside one material are pulled part-way to its colour.
* **Into the game** (`tools/export_ef.py`): converts a fighter build to Egyptian Fighter's sheet format.
  The whole route from a captured GLB is in that file's header.

On the synthetic test the clean-up costs a little texture accuracy (4.3 → 5.9 / 255) for the cleaner look; the
body fit is unchanged.

## New in v11.2: the face's own shape, faces painted where they are, the room's light taken out
**Face** (`sforge/capture_face.py`):

* **Detect.** MediaPipe's Face Landmarker (478 points) runs on every frame that sees the face.
* **One head pose per frame.** The body's cameras put the face 25 to 40% of its width off, because the head is a
  small part of a whole-body fit and moves a little during the turnaround. So each frame gets the head's own pose
  from its landmarks.
* **Fit the face shape.** MakeHuman's own face modifiers (nose, mouth, eyes, brows, chin, cheeks, forehead and head
  size) are fitted to all those frames at once. The landmarks are matched to MakeHuman's face by running the same
  detector on a render of it.
* **Paint.** The texture bake projects the face, scalp and hair through each frame's head pose, so the face is
  painted where it really is on the head. In v11.1 a front view could show a split, doubled face.
* **MakeHuman.** The fitted face is made of ordinary MakeHuman modifiers, so `NAME.mhm` carries it into
  MakeHuman / MPFB.
* **`--face-photo PHOTO`.** Optional: a close-up, front-on photo of the face is posed the same way, colour-matched
  to the video and feathered onto the face. `--no-face` keeps MakeHuman's average face.

**Light** (`sforge/capture_light.py`). The person stands still while the camera walks round, so the room's light
on each bit of the body depends only on which way it faces.
* **Fit.** A smooth coloured light (spherical harmonics, order 2) is fitted together with one colour per material:
  hair / skin / clothes, split by colour so a white shirt and black shorts are separate. It is then divided out of
  the texture.
* **Outputs.** The exported texture holds the true colours, for engines and Blender to light. `NAME_lighting.json`
  holds the light, and `NAME_texture_as_filmed.png` the texture as filmed. `--keep-light` leaves the light in.
* **Synthetic check** (`tools/test_light.py`). A known one-sided warm light on a body with known colours is
  removed: colour error 17.8 → 0.3, and the left / right difference halves, down to the test's own texture noise.

Results on the five real captures, v11.1 → v11.2:

| | Mike | Anna | Declan | PR | Tmon | mean |
|---|---|---|---|---|---|---|
| face identity (SFace) on held-out renders | 0.53 → 0.54 | 0.36 → **0.50** | 0.32 → **0.38** | 0.44 → **0.53** | 0.36 → **0.47** | 0.40 → **0.48** |
| face landmarks on held-out frames (error, % of face width) | 2.8 → 1.6 | 2.7 → 2.0 | 2.1 → 1.7 | 2.0 → 1.6 | 2.2 → 1.9 | 2.4 → 1.8 |
| left / right colour difference, clothes (dE, as filmed → light removed) | 14.5 → 11.9 | 10.2 → 8.0 | 2.9 → 3.0 | 8.2 → kept | 15.9 → 13.6 | |

Notes on the table:
* **Face identity.** It is OpenCV's face recogniser (0.363 = same person) comparing held-out real frames with the
  character rendered from the same camera. Every person is now above the threshold; in v11.1 Declan was below it
  and Anna and Tmon were borderline.
* **Unchanged.** Silhouette, LPIPS, DISTS and DINOv2 on the held-out frames don't move: those frames are compared
  with the texture as filmed.
* **Light removal** helps most where the room light is lopsided (Mike, Anna, Tmon).
  * **PR.** His black, striped clothes were partly read as light, and the light-free texture came out less
    symmetric. A safeguard notices that and keeps the texture as filmed.
* **Close-up photo.** The `--face-photo` path was run with the closest frame of Mike's video standing in for a
  photo: it placed it with 1.5% landmark error and painted it in. No real close-ups have been tried yet.

**Still opens everywhere** (`tools/capture_compat.py`, all five):
* Khronos glTF-Validator: 0 errors and 0 warnings.
* Godot, Blender and Assimp load the GLB, FBX and OBJ.
* MakeHuman (MPFB2) loads each `.mhm` with the face modifiers (64 to 72 shape keys). The human it builds is within
  2.8 to 4.0 mm mean of Sprite Forge's body. On the head alone it matches the *fitted* face (Mike 1.2 mm, Anna
  0.9 mm) better than MakeHuman's average face (1.9 / 1.4 mm), so MakeHuman reads the face modifiers the same way.

v11.2 limits:
* Light from a **nearby** source (Anna's TV: purple on the side of her hair) is local, not room-wide, and stays.
* The face is only as sharp as the best video frame (a 60 to 230 px face) unless a close-up photo is given.
* Hair is still painted on a shell; long hair hanging free is not modelled.

## New in v11.1: clothes, skirts and hair as their own meshes; MakeHuman / Blender round trip; external judges
`forge.py capture` now builds the person in layers on one 26-bone skeleton:

* **Body** - fitted *under* the clothes. A missed clothes pixel costs a third of a missed skin pixel, so a long
  jumper no longer makes the body fat.
* **Clothes** - the body faces the video labels as clothes, pushed out by a per-limb offset (torso low / high,
  upper arm, forearm, thigh, shin) fitted to the silhouettes.
* **Skirt** - for a dress, a long jumper or a coat (not shorts or trousers; see the limits below): a tube from
  the hips to the hem height measured in the front and back views. Its section is the convex hull of the legs as
  the person stands, so no leg pokes through.
* **Hair** - a shell over the scalp the video labels as hair; long hair also gets a curtain down the back, kept
  only when the silhouettes want it.

In the GLB / FBX each layer is its own named mesh (Body / Clothes / Skirt / Hair), sharing one 2048² texture atlas
and skinned to the same bones. Hide the clothes in Blender and the fitted body is underneath; in the OBJ each
layer is an `o` / `g` group. `--no-layers` gives v11's single body.

Also new:
* **T-pose frames** are used in the fit (arm length and shoulders), when the clip has them.
* **Limb pose fix.** The arm and leg directions measured joint to joint are now applied joint to joint. Before,
  they were applied to each bone's own tail, which sits part-way down the limb in the 26-bone rig, so legs came out
  spread and twisted. Synthetic body error dropped from 0.65 cm to 0.33 cm (texture error 6.6 → 4.3 / 255).
* **Texture.**
  * Every layer takes only its own kind of pixel: clothes from clothes, hair from hair. A skirt also takes only its
    own colour, so leggings don't paint the hem.
  * Hands take skin wherever the video shows them as skin, so they don't take the trousers' colour.
  * Legs under a dress don't take the dress colour.
  * Unseen texels are filled from seen ones only. Before, black atlas gutters could bleed in.
  * The blend runs in chunks, so the 2048² atlas bakes in about 3.5 GB. Before, it needed over 6 GB and was killed
    on an 8 GB machine.
* **Held-out pairs.** `out/heldout/` holds each held-out real frame next to the render from its camera.

**Opens in other tools** (`tools/capture_compat.py OUT NAME`, writes COMPAT.md):

| tool | what is checked |
|---|---|
| Khronos glTF-Validator | the reference glTF 2.0 validator |
| Assimp (WASM) | GLB, FBX, OBJ: meshes, UVs, skinned bones, animations, texture |
| Godot 4.3 | headless import of the GLB and the FBX (ufbx) |
| Blender 4.5 | glTF, FBX and OBJ importers; saves NAME.blend |
| MakeHuman (MPFB2) | loads NAME.mhm and builds the human vertex by vertex |

Each capture also writes:
* `NAME.mhm` - opens in MakeHuman 1.x, or in Blender through MPFB2: macros + every fitted modifier, at the captured
  stature.
* `NAME.mpfb.json` - an MPFB2 human preset.
* `NAME_skin.png` - the body quarter of the atlas, in MakeHuman's UV layout, usable as a MakeHuman skin.

Sprite Forge's own body build now mixes MakeHuman's macros exactly as MPFB2 does, so the body you get in MakeHuman
is the one Sprite Forge fitted.

Results on the five real captures (every check passed for every person):

| check | result |
|---|---|
| Khronos glTF-Validator | 0 errors, 0 warnings, all five |
| Assimp | GLB, FBX and OBJ load: 3 or 4 meshes, 26 skinned bones in the GLB, 7 animations, texture found |
| Godot 4.3 | GLB and FBX: 26 bones, 3 or 4 meshes, 7 animations, textured |
| Blender 4.5 | GLB, FBX and OBJ import at the right height; vertex groups match the bones; `.blend` saved |
| MakeHuman (MPFB2) | loads every `.mhm` with MakeHuman's 163-bone rig: the human it builds is within 1.8 to 3.1 mm mean (max 8.7 mm) of Sprite Forge's body, at the same stature to the millimetre |

Assimp's FBX reader counts 25 bones for the bodies without a skirt: the root bone drives no vertex there.

Held-out frames per person (every 4th frame, never used for the texture), v11 → v11.1:

| | Mike | Anna | Declan | PR | Tmon |
|---|---|---|---|---|---|
| silhouette IoU | 0.85 → 0.85 | 0.86 → **0.88** | 0.81 → **0.83** | 0.78 → **0.79** | 0.87 → **0.88** |
| colour dE (lower is better) | 8.9 → **7.9** | 7.5 → **7.3** | 7.0 → 7.3 | 8.4 → **7.6** | 10.7 → **10.0** |
| SSIM | 0.64 → 0.65 | 0.73 → 0.74 | 0.65 → 0.67 | 0.63 → 0.63 | 0.73 → 0.73 |

**How real is it? Judged by models Sprite Forge does not use** (`tools/capture_quality_external.py`, EXTERNAL.md).
Held-out frames are compared with the renders from the same camera, both cut to the person on grey, by four
published models:
* LPIPS (Zhang 2018) and DISTS (Ding 2020) - perceptual distance
* DINOv2 (Oquab 2023) - feature similarity
* SFace (OpenCV zoo) - face identity

A reference row compares each real frame with a nearby real frame of the same video. That frame is half a second
further round, so it is not pixel-aligned (IoU 0.63). It is a fair yardstick for the content judges (DINOv2, face
identity), not for the pixel ones (LPIPS, DISTS).

Means over the five people (held-out frames):

| | LPIPS ↓ | DISTS ↓ | DINOv2 ↑ | face identity (SFace) ↑ | silhouette IoU ↑ |
|---|---|---|---|---|---|
| v11.1 (layers) | 0.148 | 0.204 | **0.752** | 0.398 | **0.839** |
| v11.1 without layers (`--no-layers`) | 0.150 | 0.204 | 0.746 | 0.410 | 0.820 |
| real frame vs a nearby real frame | (0.219, not aligned) | (0.156, not aligned) | 0.892 | 0.678 | (0.633) |

* **Face identity.** The face recogniser calls the render the same person as the real frame on average (0.398,
  above OpenCV's 0.363 threshold). By person it is clear for Mike (0.53) and PR (0.44), borderline for Tmon (0.36)
  and Anna (0.36), and below the threshold for Declan (0.32). Two real frames of the same person score 0.68, so the
  faces, which come from a 768 px phone video, are recognisable but soft.
* **DINOv2.** Renders score 0.75 against 0.89 for two real frames: clearly the same subject, but not yet mistakable
  for a photo.
* **Layers.** The clothes / skirt / hair layers raise the silhouette match (+0.019 IoU, and +0.02 for Anna, Declan
  and Tmon) and slightly raise DINOv2. The other judges are unchanged within noise: the layers improve the shape,
  and the texture was already good.

**One photo vs PIFuHD** (`tools/capture_vs_pifuhd.py`). PIFuHD is Facebook Research's published single-image
clothed-human reconstruction (CVPR 2020). It got the same frontal photo, and both were judged on every other frame
of the turnaround video. PIFuHD was helped: its mesh was scaled to the person and aligned to the video-fitted body.

Mean silhouette IoU over every other frame of each person's video:

| | Mike | Anna | Declan | PR | Tmon | mean |
|---|---|---|---|---|---|---|
| **Sprite Forge, 1 photo** | **0.854** | **0.867** | **0.807** | **0.790** | 0.864 | **0.837** |
| PIFuHD, 1 photo | 0.811 | 0.807 | 0.662 | 0.783 | **0.869** | 0.787 |
| Sprite Forge, video (reference) | 0.863 | 0.882 | 0.831 | 0.796 | 0.869 | 0.848 |

Sprite Forge's one-photo body wins on four of the five people, most clearly on the back views (Anna 0.849 vs
0.761). PIFuHD wins on Tmon by 0.005 and is close on PR. Declan's photo has a broken person mask: MediaPipe lost
his dark jeans and kept a toy he was holding. PIFuHD rebuilds what the mask shows, while Sprite Forge's template body
does not depend on it. Leaving Declan out, the means are 0.844 vs 0.818. PIFuHD gives a clothed surface with folds and
hair (its back is inferred too); as released it outputs an untextured mesh with no rig. Sprite Forge's is a rigged,
textured, animated character.

v11.1 limits:
* **Skirt.** A skirt tube is made only for a garment that runs from the torso past the hips and then ends: a dress,
  a long jumper or a coat. That is checked by colour in the front and back views.
  * A separate skirt in a different colour from the top is treated as shorts (clothes on the thighs, no tube).
  * A black dress over black tights reads as trousers.
* **Long hair** mostly stays painted on the back. The hair curtain is kept only when the silhouettes improve with
  it, and on these five videos they never did.
* **Skin-tight clothes.** Clothes are allowed to stand off the body, so the body under skin-tight clothes can come
  out about 1 cm small (synthetic test with everything labelled clothes).
* **Room light** (a purple TV glow on Anna's hair) is still baked into the texture.
* **Memory.** The 2048² atlas needs about 3.5 GB of RAM. `--texture 512` makes a 1024² atlas, which needs far less.

## New in v11: people to rigged 3D characters (`forge.py capture`)
A **turnaround video** (the person stands still while you walk once round them) or **one photo** becomes a rigged,
textured 3D character: **GLB, FBX and OBJ** with a 26-bone game skeleton (pelvis, spine_01.., thigh_l, calf_l,
upperarm_l ...), MakeHuman's own skin weights and Sprite Forge's clips (idle, walk, run, jump, kick, punch,
celebrate). It is the same skeleton as `forge.py look`, so every sprite, console and game exporter works with it.
All of it runs inside Sprite Forge on the CPU. Blender and MakeHuman are used only to check the result.

```
forge.py human --setup --from-git          # once: the CC0 MakeHuman body (no pip needed)
forge.py capture --setup                   # once: the MediaPipe pose + segmentation models (Apache-2.0)
forge.py capture turnaround.mp4 --name mike --height-cm 180      # -> captures/mike/out/mike.glb .fbx .obj
forge.py capture photo.jpg --name mike --height-cm 180           # one photo works too (depth + back estimated)
forge.py capture --rebuild --name mike     # redo texture + exports from the saved fit
```

How it works (`sforge/capture*.py`):
1. **Track.** For each sampled frame, MediaPipe gives the 33 pose landmarks (2D and 3D), a person mask, and
   hair / skin / clothes labels. It also gives the body's yaw, which is unwrapped round the orbit.
2. **Fit.** The CC0 MakeHuman body is fitted to the person's silhouette in about 24 frames round the orbit. The fit
   covers gender, muscle, weight and proportions, plus 22 shape sliders (torso / hip depth and width, belly,
   buttocks, bust, waist, hips, thighs, calves, arms, shoulders, neck, head, limb and torso lengths). Arms and legs
   are posed to the measured stance. Each frame has its own perspective camera: PnP from the joints, with the yaw
   held near the orbit and left / right swapped when MediaPipe reads a back view mirrored, then refined on the
   silhouette.
3. **Texture.** Every texel of MakeHuman's UV layout is projected into the frames. It keeps the views where it is
   the visible surface, inside the person (by mask and labels), and facing the camera. Closer and sharper views
   weigh more. The views are blended with a robust (weighted-median) mix, with a per-frame exposure gain. The face
   comes from the single best frontal frame (no double eyes).
4. **Export.** GLB (skin, texture, clips), FBX written by Sprite Forge's own writer (texture embedded), OBJ + MTL,
   a turntable picture, a fit overlay and report.json.
5. **Check.** Every 4th frame is left out of the texture. The model is re-rendered from those frames' cameras and
   compared with the real frames (silhouette IoU, colour dE, SSIM).

**One photo.** The silhouette gives widths and lengths. The depth a photo cannot see comes from **priors learned
from the turnaround videos** (`sforge/data/capture_priors.json`, numbers only). The back is painted from the
front: per row band, the median colour of each label, so a logo on the front does not reappear on the back. Hidden
hands become skin, and the back of the head is hair when the photo shows hair.

**Checked against the real tools:**
* *MakeHuman.* `tools/capture_vs_makehuman_blender.py` builds the same fitted body with MPFB2 (MakeHuman's own
  code in Blender). It matches Sprite Forge's standalone build to 0.3 mm mean and under 1 mm max.
* *Blender's importers.* `tools/capture_check_blender.py` loads the GLB, FBX and OBJ in Blender: 26 bones, 7
  actions, texture present, correct height. It also renders the clips (`blender_check.png`).

Tests and benchmarks:
* `tools/test_capture.py` (synthetic, needs no people) films a known body with a virtual orbit, fits it back,
  bakes the texture and checks the exports.
* `tools/capture_bench.py` is the turnaround benchmark and writes the priors.

Measured on 5 real turnaround videos (2 to 3 people per worker, CPU only, about 8 to 14 minutes each):

| | Mike | Anna | Declan | PR | Tmon |
|---|---|---|---|---|---|
| fit silhouette IoU (video) | 0.869 | 0.873 | 0.817 | 0.784 | 0.868 |
| held-out frames: IoU / colour dE / SSIM | 0.85 / 8.9 / 0.64 | 0.86 / 7.5 / 0.73 | 0.81 / 7.0 / 0.65 | 0.78 / 8.4 / 0.63 | 0.87 / 10.7 / 0.73 |

What one photo predicts about the views it never saw (`tools/capture_bench.py`, leave-one-out priors, mean
silhouette IoU over every other frame of the person's video):

| body | Mike | Anna | Declan | PR | Tmon | mean |
|---|---|---|---|---|---|---|
| average MakeHuman body | 0.807 | 0.816 | 0.779 | 0.757 | 0.844 | 0.801 |
| photo fit, no priors | 0.847 | 0.855 | 0.779 | 0.761 | 0.860 | 0.820 |
| **photo fit + video priors** | **0.849** | **0.859** | **0.789** | **0.763** | **0.865** | **0.825** |
| video fit (upper bound) | 0.858 | 0.861 | 0.808 | 0.787 | 0.871 | 0.837 |

One photo with the learned priors closes two thirds of the gap between the average body and a full turnaround, and
the priors help all five people. The photo's painted back is judged against the real back views: colour dE 14 to
35, mean 21. The 35 is Tmon, whose back was filmed in a warmer-lit room, which no photo of the front can predict.

Synthetic check (`tools/test_capture.py --quick`): silhouette IoU 0.955, body vertex error 0.65 cm (the starting
body was 1.72 cm off), texture error 6 / 255, and GLB / FBX / OBJ all pass.

Known limits:
* The body is MakeHuman's undressed body, so loose clothes (a long jumper, a hoodie) are fitted as body volume.
  Hair is not modelled as geometry; it is painted on the head.
* Coloured light in the room (a TV) is baked into the texture.
* Clothed silhouettes cannot tell a man's body from a woman's: use `--body male|female`.
* The face comes from the best single frame of a phone video (768 px), so it is soft.
* Motion: `forge.py mocap --rig captures/NAME/out/NAME.glb` puts video motion on the captured character. A
  toddler's walk clip worked (9 deg mean bone error). A dark, crowded pub dance worked for most frames (12 deg) but
  falls over in its last frames.
* `forge.py mocap` no longer crashes on clips over 600 frames.

## New in v10.3: self-contained looks, better beards and long hair
* **No other game or program needed.** `forge.py look` and the Appearance tab now use a built-in template: the CC0
  MakeHuman body with a 26-bone skeleton and Sprite Forge's own clips (idle, walk, run, jump, kick, punch,
  celebrate).  It is made once from the MakeHuman library (`sforge/mhtemplate.py`).  Your own rigged MakeHuman
  model still works (`--template`, `$SFS_MH_TEMPLATE` or `assets/makehuman/template.glb`).
* **Beards:** a soft base layer of fine strands follows the face (thinning out at the edges, with sideburns up to
  the hair), and shorter strand clumps on top.  No more clumpy, scraggly edge.
* **Ponytails and long hair:** an inner layer fills the gaps between hair cards, the skin under the hair is
  hair-coloured wherever hair lies close, and the hair is lit as one smooth volume (no flat, faceted planes or dark
  patches).  The preview and sprites use soft (dithered) hair edges.
* **Blender check, now one command (optional):** `forge.py look --look my_look.txt --verify-blender OUT` rebuilds the
  look with MakeHuman's own code in Blender (MPFB2) and compares it with Sprite Forge's build (verify.json + Cycles
  portraits).  It needs Blender as a Python module with MPFB2; nothing else in Sprite Forge does.

## New in v10.2: change a character's features (Appearance tab, `forge.py look`)
Realistic characters are built from the CC0 MakeHuman library: its base mesh, its own morph targets, and its fitted
hair, eyebrows, eyelashes and eyes.  Every feature is one key, so the same look drives the Studio sliders, a text
file, the 3D model and the sprites.
* **Body:** arm, shoulder, chest, back, thigh and calf muscle; shoulder width.
* **Face:** nose size and width, lips (thin to full), mouth width, cheekbones, cheek fullness, jaw, chin, eye size,
  ears, eyebrow height.
* **Hair:** 12 styles (bald, buzz, 4 short, long, ponytail, 2 bobs, braid, afro), any colour, a balding hairline
  (0 full to 1 balding; strands fade out, no hard edge), stubble, moustache, goatee or beard (strand cards, not
  paint), 12 eyebrow shapes, thin to bushy, dark or light.
* **Skin and eyes:** 11 MakeHuman skins, 9 eye colours, optional skin tint.

Use it three ways:
* **Studio, Appearance tab:** sliders with a live preview (face + body, front, side, back, or run / kick sprites;
  about 3-5 s per change). Load / save a look, randomise, export a GLB or sprites.
* **Command line:** `forge.py look --set "hair_style=long01,facial_hair=beard,muscle_arms=0.8" --preview me.png
  --glb me.glb --sprites out/ --clips run,kick_run` (`forge.py look --keys` lists every key).
* **Squads:** a file with one `[variant]` block per look. `tools/gaelic_squad.py` builds all of them into one GLB
  for Gaelic Football 3D (each player gets a look; skeleton and 32 clips unchanged).
* **An external mesh on that skeleton:** `forge.py gaelic-fit MESH.glb --out /tmp/gf_fit` (also the Gaelic
  tab in the Studio) stands a T-pose or A-pose GLB/OBJ up and skins it to the 52-joint template, keeping
  all 32 clips. Kit shells use the squad atlas so `kit_*.png` still swaps teams. The scratch files are not
  written into `assets/models`. Prompts for Meshy or Rodin are in `tools/GAELIC_FIT.md`. This command does
  not generate a person.

Sprites come from the same character: the 3D model is posed with the template's clips and drawn by a software
renderer (`sforge/mhrender.py`: textured, lit, alpha-tested strands), 192x256 cells facing right with the feet on
y = 248, plus `meta.json`.

**Checked against MakeHuman itself.** `tools/mh_verify_blender.py` builds every squad look a second time with
MPFB2 (MakeHuman for Blender, MakeHuman's own code) and compares: body vertices 0.000 mm apart over 9 looks, fitted
hair / brows / lashes / eyes 0.0 mm apart, plus a Cycles portrait of each.  `tools/test_look.py` runs in CI.

Setup: `forge.py human --setup --full` (CC0 MakeHuman library, about 280 MB; one download).  The rigged template
is built in (v10.3).
Limits: one body type per template (the template's skeleton is kept, so very large height or proportion changes
are not offered); hair is MakeHuman's card hair, which reads well at game distance and in sprites but is not
strand-level; the preview renderer has no shadows.

## New in v9.5: a better three-quarter view (photo3d)

The 3D engine's turned views were the weakest output: an outline puffed up like a balloon, a flat face, and grain
where points fought for the same pixel. Three changes fix that, and none of them needs more than the one photo:

* **Real body shape**: torso and legs take their depth from the free CC0 **MakeHuman** body. Each photo row is
  matched to the same body height on the template, and the template's real cross-section is scaled to the row's
  width, giving a flatter back, a rounded chest and round thighs. The shoulders stay round, and every row is centred
  on the bones so that limbs stay attached when they swing. Set it up once with
  `forge.py human --setup --from-git`, which sparse-clones the assets from GitHub, needs no pip and makes about
  30 MB. Without the assets, photo3d falls back to the inflated outline. `--body3d template|inflate|auto`.
* **Real face depth**: MediaPipe's 468-point canonical face (Apache-2.0, vendored in `sforge/data/mediapipe_face/`)
  is posed onto the photo's face from the eyes, nose and mouth corners with solvePnP (a slightly turned head is
  followed). Its depth is blended into the head, giving the nose, eye sockets, lips, chin and the cheeks turning
  away, in place of three guessed bumps.
* **Surface drawing**: each pixel averages the points of the front surface within 1.2 cm of the nearest one, in
  place of a single point winning, which removes grain and checkerboard. Side walls take a colour blurred down the
  body rather than streaks, and the silhouette is closed front to back, so the white seam down a side-on figure is
  gone. Knees and elbows now bend half-way on both sides of the cut, so a bent joint stays closed.
  `--surface3d crisp|smooth|points` (default crisp: it measured best).

Measured on the Mike test photo (`tools/quality_report.py`, against the proportion-corrected photo at the same
size; fighter14, 96 frames):

| build | identity (aligned SSIM) | face sharpness | BRISQUE idle (photo) | colour dE top / legs |
|---|---|---|---|---|
| 2D skin 35 deg | 0.48 | 56% | 14.3 (18.1) | 4.7 / 6.4 |
| photo3d 35 deg v9.4 | 0.42 | 71% | 18.0 (12.9) | 2.4 / 9.0 |
| **photo3d 35 deg v9.5** | **0.44** | 67% | **11.8** (12.9) | 4.7 / **7.8** |
| photo3d 90 deg v9.4 | 0.31 | 81% | 23.1 (13.6) | 17.3 / 8.5 |
| **photo3d 90 deg v9.5** | **0.40** | 42% | 22.5 (13.6) | 19.4 / **8.2** |

The 35-degree view now looks more natural than the photo scaled to the same size (BRISQUE 11.8 against 12.9),
and identity is up at both angles. Face sharpness at 90 degrees is lower: v9.4's figure was raised by aliased point
grain, which the surface drawing removes. In tests, sharpening brought the number back but lowered identity and
naturalness, so it is off.

Limb test (`tools/test_limbs.py --engine photo3d`) at 35 and 90 degrees: 11 PASS, 3 WARN and 0 FAIL. The warnings
are the same speed warnings as in v9.4 (kick, throw and jumpattack keys), and no limb comes off.

Still limited: the sides and back are estimated, and the template is one average adult body (fine for most adults,
not for a child or a very heavy build yet). More photos or a turn-around video of the same person are the next step
up; they will be optional, never required.

## New in v9.4: measured realism, dress-as, pose-it-yourself, squads, references

Measured with independent tools (`tools/quality_report.py`: YuNet + Haar face detection, aligned-face SSIM identity,
BRISQUE naturalness, CIELAB colour, head ratio vs Drillis & Contini adult norms; models via `tools/setup_quality_models.sh`).
On a real phone photo: head 0.185 -> 0.152 of height (norm 0.130), front view BRISQUE 11.6 -> 9.0 at full sharpness,
side view sharpness 20% -> 81% and BRISQUE 32.9 -> 23.1 (photo3d instead of the 2D turn).

* `--proportions auto|on|off` (+ `--proportion-strength`): phone-camera perspective (big head, short legs) corrected
  once, up front; the head is scaled uniformly so the face keeps its shape. auto = only when clearly distorted.
* photo3d: fighter motion pack (`sforge/fightpack.py`, `--motion-pack`): side-on staging, torso opened to the camera,
  strikes in profile, uppercut / sweep / low block / knockdown / get-up / roundhouse extras, smear frames on fast moves;
  back surfaces continue the front's colour at the edge (no seam), sleeves and trouser legs keep their real fabric all
  round, wider halo clean-up, `--normal-maps` for 2D dynamic lighting. Limb test at 35 deg: 0 fails, 3 warnings (the
  fastest strikes at 6-8 frames).
* `--dress-as police|postman|astronaut|firefighter|builder|chef|doctor|ninja|file.json` (`sforge/outfits.py`):
  garments recoloured on the photo's own pixels with shading kept, plus props from the pose (caps, helmets, badges,
  satchels, belts, hi-vis, gloves, chest units). Generic - no real insignia or lettering.
* Pose-it-yourself: `tools/pose_editor.html` (drag a skeleton, keyframes) -> JSON -> `--custom-move file.json`
  (`sforge/posekit.py`), rendered by any engine at any angle. Example: `library/moves_custom/spinning_backfist.json`.
* Video-to-move: `forge.py mocap` clips -> `--mocap clip.json --moves idle,kick2=mocap_kick2:8:14` on photo3d.
  `tools/test_video_move.py` proves the chain without a camera (recovered motion within 1.5 deg per bone).
* Style lock / match: `tools/style_match.py GAME_SPRITES SRC DST` learns pixel size, palette, outline and colour from
  the game's own sprites and restyles a build to fit.
* Engines / editors: `tools/export_engines.py --all` -> Aseprite (JSON + Lua import), Phaser 3 atlas + anims, Godot 4
  SpriteFrames, GIF / WebP previews (Unity: plugins/unity).
* Squad mode: `tools/squad.py PEOPLE OUT --roster roster.csv [--game arena-fc|ef|hdf|tt64]` - one scale for everybody
  (heights from the roster), outfits per member, line-up sheet, game files.
* Learned body: `tools/learned_body.py import MESH` binds any reconstructed / generated mesh (LHM-class models, Meshy,
  Tripo, a scan) to the skeleton as a library rig; `run PHOTO --cmd ...` drives a GPU reconstruction model first.
* Reference library: `tools/refs.py add|list|cut|bench|motions|dataset` - photos and videos with consent and licence
  records (store git-ignored); `bench` scores every engine on every consented person, `motions` turns videos into
  library moves, `dataset` writes a consented-only manifest for future training.

## New in v9.3 (experimental): photo -> 3D body, any camera angle, GPU when available

* `--puppet-engine photo3d` inflates the cut-out into a 3D body (front = the photo's own pixels; depth, sides and back
  estimated from the silhouette and edge colours; a nose / brow / chin profile from the face landmarks), skins it to
  the standard rig and drives it with the skeletal motion library - the same clips as spec / GLB builds. The torso
  twists, shoulders roll, a kick is a real hip-knee-ankle chain, and `--turn-yaw` is just a camera angle on the same
  body (front, 35 deg fighter, 90 deg side, 8-way). The head keeps facing the opponent within a natural neck range.
* Motions are sampled by pose change, not clock time, so a fast strike gets in-betweens instead of one big jump.
* `--device auto|cpu|cuda|mps` (env `SFS_DEVICE`): skinning and the z-buffer run through `sforge/accel.py` - PyTorch on
  CUDA / Apple MPS when installed (`requirements-gpu.txt`), NumPy otherwise. ~0.5 s per 512 px frame on 2 CPU cores.
* `tools/test_limbs.py --engine photo3d` checks it with 3D-aware motion tests (bone speed and swing measured on the 3D
  bones, knees against the body's own hinge). Status on a real photo at 35 deg: idle, walk, crouch, block, victory pass;
  the football-derived kick / jump / special clips still move too far per frame at the fighter preset's frame counts
  and the hidden-hand arm can lose coverage - a fighter motion set for the 3D rig is the next step. Opt-in; defaults
  are unchanged.

## New in v9.2: photo puppets that hold together (limb test, 3/4 view, game adapters)

* **`tools/test_limbs.py`**: renders every frame of every move straight from the rig (effects stripped) and fails
  on a detached limb (bone coverage + floating pieces), a missing foot, flapping arms, a snap (>75 deg/frame arm,
  >60 leg) or a knee / elbow bending the wrong way. `--selftest OUT` renders a front mannequin with exact landmarks,
  so it runs anywhere (CI: `.github/workflows/sprite-forge-tests.yml`).
* **3/4 fighter view** `--turn-yaw 35`: keeps the face and clothing print readable with the body side-on enough for
  attacks. Recommended for 2D fighters; 90 deg needs a `--side-photo` for a real profile.
* Fixes found by the test: joint discs at elbows, knees and hips (no seams on sharp bends or leans); hands that hang
  against the thigh now move with the forearm (they used to stay on the leg); cut-out slivers are removed before
  effects; the side of a turned head uses the cheek colour (no stretched-ear smear).
* `--billboard8` / `--views` on a photo puppet fill missing views by **turning** the photo (was a squashed copy).
* Game adapters: `tools/export_hdf.py` (HD Fighter), `tools/export_arenafc.py` (Arena FC CharacterSpec from the
  photo's colours and build), next to `export_ef.py` and `export_tt64.py`.

## New in v9.1: bendier photo puppets (opt-in)

Two `forge.py build` options for the front-photo puppet (`--fill puppet`). The defaults are unchanged.

| Option | What it does |
|---|---|
| `--puppet-engine skin` | Elbows and knees bend smoothly (linear blend skinning, `sforge/skinwarp.py`) instead of rigid pieces with cap discs. On the mannequin test the detached forearm/shin islands in kick, punch and jump frames went away (about 3 islands per frame down to 2). If a hidden hand had to be copied from the visible one, the classic renderer is used for that build and the report says so. |
| `--motion-style polish` | Smooth in-betweens (monotone cubic instead of straight lines), a slight lag on forearms and shins, small sway on idle/taunt/victory and a landing squash on jumps (`sforge/motionpolish.py`). Only moves with more frames than key poses change (kick, throw, hit, taunt and both specials in fighter14). The trade-off is that peak joint speed rises (kick about 105 to 152 deg/frame), so judge fast moves by eye. |

```
python tools/setup_pose.py                                   # once: the pose model forge.py cutout needs
python forge.py cutout photo.jpg --person largest --out cut
python forge.py build --photo cut/cutout.png --landmarks cut/landmarks.json --fill puppet \
    --preset fighter14 --puppet-engine skin --motion-style polish --name me --out out
```

Tested on the project's own mannequin render with hand-placed landmarks: `tools/test_v9.py` 44/44 and
`tools/test_v8.py` 6/6 still pass with the patch. **Not yet tested on a real photo or on cartoon art**,
because the pose model wasn't available where this was made. Compare `--puppet-engine skin` with the
classic build on your own photos before making it the default.
A front photo has no depth, so punches and kicks still extend sideways. For a side-on fighter, try
`--turn 90` (an estimate from a front photo plus a body template).

## New in v9: faces, colours, variants (+ extras, NPC pack, Unity / Godot plugins)
`python forge.py help v9` or the Help tab topic "New in v9" has the short version. Screenshots: `previews_v9/`
(mannequin / fictional NPCs only). Tests: `previews_v9/tests/RESULTS_v9_tests.md`. Results: `RESULTS_v9.md`.
Timings: `TIMINGS_v9.md`. Video: `videos/06_v9_faces_colours_variants.mp4`.

The Start wizard has a new **step 4 STYLE** with three tabs. Each tab has a **Preview** button that runs a one-move
draft build (about 1.5 s) so you see the real result. Every setting is also a `forge.py` flag.

* **Faces: expressions and mouth shapes per move.**
  * Seven faces: neutral, happy, angry, hurt, shout, taunt and blink. **Automatic** picks one per move
    (punch / kick = angry, specials = shout, hit = hurt, taunt = taunt, victory = happy). You can change any move
    (`--expr-map punch=shout,victory=happy`) or use one face for every move (`--expressions happy`). Looping
    neutral moves blink once per loop (`--no-blink` to stop it).
  * `faces.png` + `faces/` hold a HUD portrait of every expression and mouth shape.
  * Talking: `--talk "Ready to fight"` writes `talk/talk_strip.png` + `talk.json`. The 8 mouth shapes (rest, M/B/P, A/I,
    E, O, U, F/V, L) are picked from the **letters**. There is no speech recognition.
  * 3D characters get a morphed face mesh. `model.glb` also gets morph targets and weight tracks.
  * **Photo characters** get procedural warps and small overlays of **your own photo's face**. No new face is drawn.
    The result is ESTIMATED and labelled that way.
* **Colours: palette swaps, region masks, texture overlays, one-click sets.**
  * There are 20 one-click sets (`forge.py sets`): team colours, county colours (kerry, dublin, mayo, cork, galway),
    egypt_gold, ninja, villain, ghost, fire, ice and p2_alt. You can also save your own.
  * Per region: skin, hair, top, trim, bottom, socks, shoes, accessory (`--recolor "team_blue;hair=black"`).
  * Overlays on the top: hoops, stripes, sash, chest_band, halves, check, dots, camo, or your own tiled texture
    (`--overlay top:hoops:#ffffff`, `--overlay top:texture:cloth.png`).
  * 3D characters: the colours go into the 3D spec, so they are exact.
  * Photos: the regions are ESTIMATED (pose points + skin model + colour clusters). The photo's own pixels are
    re-tinted with their shading kept. Each build writes `regions.png`; paint over it and pass it back with
    `--regions` to fix a mask.
  * To recolour something already built: `forge.py recolor out/hero --set team_red` (palette swap of every PNG).
* **Variants: procedural, seeded.**
  * `--variants 8` writes `variants/` (`variants_sheet.png` + one spec per seed). `--variant SEED` builds that one
    as the character. The same seed always gives the same variant.
  * `--vary` limits what changes: body, outfit, colours, skin, accessories, face, or all.
  * For a **photo**, a variant only re-tints the clothes and scales the body. The face, skin and hair are kept,
    and no new image of the person is ever made.
* **Extras** (step 5 > Extras, or the flags):
  * `--framedata`: hit / hurt boxes plus startup / active / recovery, written to `framedata.json` / `.cfg` with a
    preview.
  * `--footlock`: 2-bone IK pins planted feet, so there is no sliding. Walk slide drops from 14.0 cm to 0.0 cm on
    the mannequin.
  * `--fx`: outline, cel, pixel-art, palette and lighting / rim passes.
  * `--maps normal,emissive`: normal maps and emissive maps.
  * `--blend idle>walk:3`: transition moves.
  * `--lods 2`: `model_baked.glb` + `model_lodN.glb`.
  * Hair, cape and scarf physics chains in the sprites and the GLB (`--no-physics` to turn them off).
  * The **QA check** runs on every build and writes `qa_report.txt`. It looks for clipping, empty frames, feet drift,
    pops, loop seams, specks and halos. `forge.py qa <folder>` checks any build or game folder.
* **Tools menu / commands:**
  * `forge.py atlas a b c --out pack` packs several characters on shared MaxRects pages (about 83% fill).
  * `forge.py batch queue.txt --workers 3` runs a queue of forge.py jobs.
  * `forge.py framedata` and `forge.py qa` run on an existing build.
* **NPC / enemy preset pack.** `forge.py npc` lists 17 fictional characters (villager, guard, knight, goblin, orc_brute,
  wizard, skeleton, zombie, ghost, robot, boss_king ...). There are 7 move presets, with new motions such as wave,
  talk, patrol, cower, cast, roar, lunge, die and sit. Example: `forge.py build --npc goblin --variants 6`.
* **Engine plugins.**
  * `plugins/godot/addons/sprite_forge`: SpriteFrames + a character scene with hit / hurt Area2D boxes and
    normal-mapped frames. It was tested headless on Godot 4.3.
  * `plugins/unity/com.spriteforge.importer`: a UPM package that makes sliced sprites, the `_NormalMap` secondary
    texture, clips + controller, and a prefab with frame-data colliders.
* **Tests.** `tools/test_v9.py OUT` passes 46/46. It includes the Godot import and a Unity compile against stub APIs,
  and its photo-path regressions use a drawn doll, not a real person. `tools/test_v8.py` passes 20/20 and
  `tools/test_v7.py` passes 50/50. `build_release.bat` / `.sh` run all three (step 2h / 6c).
* **Speed** (8 cores, 14 moves, 384x512 cells): base 2.3 s. Faces, colours, variants, foot lock, blend, frame data
  and QA each add 0 to 0.5 s. FX adds about 1 s and normal + emissive maps add about 5 s. Everything together takes
  11.6 s (`TIMINGS_v9.md`).
* Evidence for older versions (`previews_v2` - `previews_v4`) is in the v8 release zip. It is left out here to
  keep the zip under 25 MB.

### v9 limits (honest)
* **Photo expressions are estimated** procedural warps of the photo's own face. They are subtle on small in-game faces,
  very subtle on side-on (turned) views, and absent on back views.
* **Photo colour regions are estimated.** Small patches such as a bag strap can be missed. Fix them with
  `regions.png` + `--regions`.
* **Photo variants** change only the clothes colours and the body scale. The face, skin and hair are kept.
* Frame data and normal maps are **estimated** from the 2D silhouettes, so tune them. Emissive maps only pick up
  the glow colours set in the spec.
* Foot locking fixes the sprites. The GLB clips are not re-solved. On photo builds, blending is a crossfade.
* Mouth shapes come from letters, not from audio.
* LODs are rebuilt with fewer segments, not decimated. The baked model uses a flat palette texture with no baked
  lighting.
* The Unity package has only been compiled against stub APIs. It has not been run in the Unity editor. The Godot
  plugin was tested on 4.3 only.
* The NPC `sit` motion sits on an invisible stool, so add your own chair.
* QA flags real problems. The sample `rua_keeper` build has a FAIL for special1 (frame 4 touches the top edge of the cell), and that is
  correct.

## New in v8: Start wizard, three goal tabs, side-on turn, faster builds
`python forge.py help v8` or the Help tab topic "New in v8" has the short version. Screenshots: `previews_v8/`.

* **Start tab (wizard).** The Studio opens on a five-step page with Back / Next at the bottom:
  1 Start from (photo, video, frames / sheets, make a character, library rig, text description),
  2 Your source (with **Cut out person** for photos), 3 Look & view (facing, with **Preview this view**),
  4 What to make, 5 Build. Every step and button has an icon (drawn by `sforge/icons.py`; no image files).
  The old screen is still there as the **Build (advanced)** tab. The wizard fills the same settings, so you can switch at any time.
* **Three goal tabs in step 4.** They add up, so one build can make all of them:
  * **HD sprite sheet**: game / move set plus a **move picker**. Tick moves, set frames and fps per move, and use
    "Add a move" to take moves from other presets. It warns if the Egyptian Fighter needs a move you unticked.
  * **Retro console sprites**: none, or one of 18 consoles (Atari 2600 to PS1), plus dither.
  * **3D files**: GLB, FBX and per-move animation files. These are only for sources that are 3D (make a character,
    library rig, description). For a photo, video or frames source the tab is greyed out and says why.
  * A "Will make: ..." line sums up what the build will write.
* **Side-on / turned view from one photo (`--turn`).** You can use 0 front, 90 side-on facing right, 180 back,
  270 left side mirrored to face right, or any angle.
  * `forge.py cutout photo.jpg --out cut` writes the transparent cut-out and 33 pose points.
  * `forge.py turn cut --yaw 90 --out turn` writes `compare_90.png` (front vs turned).
  * `forge.py build --photo cut/cutout.png --landmarks cut/landmarks.json --turn 90 --preset fighter14` builds the moves.
  * Optional `--side-photo side.jpg` (a real side photo or video; `--side-frame SEC` picks the frame) makes the side view closer to the person.
  * The front is the photo's own pixels. The side, back, depth and face profile are **estimated** (MakeHuman CC0
    body template), and that is labelled on every preview.
* **Egyptian Fighter export.** `forge.py export-ef OUT/name GAME/char_name` writes all 14 strips and `sprites.cfg`.
  If a move is missing, it now says MISSING and exits 1 (it used to skip it without a word).
  `pyramid_blast` / `bum_fireball` now map to `special_1` / `special_2` for mannequin, spec and library sources.
* **Faster builds.**
  * Unchanged moves are re-used from a cache (`--no-cache` to force a full rebuild; `forge.py cache stats|clear|prune`).
  * Frames render on all CPU cores, and PNGs are written in the background.
  * Quick preview is half size, 4 frames a move and no 3D / console files (`--quality draft`).
  * Times on 8 cores (`previews_v8/TIMINGS_v8.md`):

  | scenario | v7 | v8 first build | v8 rebuild |
  |---|---|---|---|
  | spec fighter14 + SNES | 4.0 s | 1.5 s | 0.2 s |
  | photo fighter14 | 3.0 s | 2.0 s | - |
  | library rig | 4.4 s | 1.4 s | - |
  | mannequin gaelic36 + GLB + FBX | 11.7 s | 3.5 s | 0.3 s (one move changed: 2.5 s) |
  | video, 2 clips | 5.7 s | 4.6 s | - |
  | UI quick preview | 3.7 s | 0.3 s | - |

* **Tests.** `tools/test_v8.py OUT` covers the cache, turn, draft, icons, the wizard command flags, cut-out and
  export-ef, and passes 20/20 (`previews_v8/tests/RESULTS_v8.md`). `tools/test_v7.py` still passes 50/50.
  `build_release.bat` / `.sh` run both.
* **Sample.** `samples/mannequin_photo.jpg` is a rendered mannequin, not a real person. Use it to try Cut out → Turn → Build.

### v8 limits (honest)
* A turned view from one front photo is an estimate. The hidden side and the face profile are guesses. A real side
  reference photo helps a lot.
* The Retro tab makes one console per build, because `build` takes one `--console`. The `video` command can still do several.
* The 3D tab only works for 3D sources. Photo, video and frames sources make 2D sprites only.
* The cut-out quality check is strict about edge halos. It can flag a clean cut-out of a hard-edged CG render. The
  Studio still uses it and tells you to look at `verify.png`.
* The GUI was tested on Linux (Xvfb). The new `build_release.bat` step was not run on a real Windows 10 machine for v8.

## New in v7: engine-ready 3D (material slots, animation files, equip, MakeHuman)
Still pip-only, Windows 10 and Linux. `python forge.py help v7` or the Help tab has the short version.

* **Material slots.** Every 3D output names its materials `Skin_Mat`, `Jersey_Mat`, `Shorts_Mat`, `Socks_Mat`
  (+ `Trim_Mat`, `Hair_Mat`, `Shoes_Mat`). Single-material meshes are split by bone region. `--material-slots core4`
  gives exactly the four core slots; empty slots are still written. Checked with our reader and with Blender.
* **Separate animation files.** `forge.py anim-export --rig NAME --out DIR [--fbx] [--verify]` or `build --anim-export`
  writes `character_base.glb` + `anim_<move>.glb` (+ `.fbx`) + `manifest.json`. Bones are re-ordered parents-first
  and names cut to 31 bytes for raylib. `examples_raylib3d/anim_viewer.c` (raylib 5.5 and 6.0) loads them
  (`previews_v7/raylib*.png`). A raylib 6.0 crash on the first anim file (NULL root parent) was found and fixed.
* **Clean imports.** Z-up, lying-down and centimetre files are stood up (+Y, metres, grounded), takes keyed on a
  Z-up armature are fixed, and duplicate meshes (`Body.001`, `*_LOD1`) are dropped and listed in the report.
* **Meshy / UE5 / Unity.** Meshy zips import directly. Mixamo (also used by Meshy), Unity humanoid, Unreal UE4/UE5,
  Rigify and MakeHuman bone names are detected. Licence presets: `--preset meshy-free` (CC BY 4.0, credit line
  "Model created with Meshy - CC BY 4.0 License"), `--preset meshy-paid` (private, redistribution no),
  `--preset makehuman` (CC0). Meshy animation-library clips stay out of packs unless you confirm with
  `--meshy-anims-redistributable yes`. Meshy changes its terms; read https://www.meshy.ai/terms-of-use.
* **Equip: outfits and props.** Outfits are skinned meshes re-fitted to any library rig; they hide the body regions
  under them. Props are rigid and sit on sockets (hand_r, hand_l, head, back, hip, foot_r, foot_l).
  `build --outfit sample_vest --outfit sample_boots --attach sample_sword@hand_r --slot-color Jersey=#c8102e`, or use
  the GUI **Equip...** button. Add your own with `library add FILE --kind outfit|prop [--socket] [--hide]`.
  `build_report.txt` lists every item's licence. The sample vest, boots, sword, shield, cap and backpack are CC0.
* **MakeHuman mode.** Run `forge.py human --setup` once. It downloads the CC0 MakeHuman assets (base mesh, default
  skeleton + weights from GitHub, and the macro targets from the `makehuman` pip wheel), about 28 MB, into
  `assets/makehuman/`. No MakeHuman code (AGPL) is installed or used; the reader and morphing are our own numpy code.
  Use `--from DIR` for an offline copy.
  * `forge.py human --gender female --age 30 --muscle 0.7 --weight 0.4 --height 0.5 --proportions 0.5
    --skeleton game_engine --name hero` creates a library rig with clips. You can also use
    `build --human "gender=1,age=25,skeleton=game_engine"`, the profile key `human`, or the GUI **MakeHuman body** field.
  * Skeletons: `default` has 163 bones (MakeHuman's own). `default_no_toes` (135), `game_engine` (65, with fingers)
    and `body` (26) are our reductions, because MakeHuman's own game_engine/no-toes files are not in its public repo.
  * Without the assets, `build --human` uses the parametric mannequin (height/build) and says so. `forge.py human`
    exits with code 3 and the setup command.
* **Your own mesh (experimental), not text-to-3D.** The Studio has no text-to-3D: that needs a paid or web
  service. Model or buy a mesh elsewhere (Blender, Meshy, a store). If it is already rigged, use `library add`.
  If it is a static OBJ/GLB/FBX, use `forge.py autoskin mesh.obj --skeleton sample_lanky --name mine --spdx ...
  --author ... --redistribution yes|no`. It stands the mesh up, scales it to the skeleton and weights it by distance
  to the bones. For hero characters use Blender weight painting or Mixamo's auto-rigger.

### How v7 was tested (`python tools/test_v7.py OUT`, results in `previews_v7/RESULTS_v7.md`)
* `tools/test_v7.py` runs 50 checks: slots, anim files, clean-up, templates, equip, MakeHuman (with and without
  assets), autoskin, CLI and profiles. `tools/test_library_v6.py` still passes 38/38.
* raylib 5.5 and 6.0 report `IsModelAnimationValid` = 1 for every anim file, including a 65-bone MakeHuman rig.
  Blender 4.x imports the FBX and GLB files with the slot names and actions.
* A copy of Egyptian Fighter was tested with a MakeHuman fighter14 build wearing the vest and holding the sword
  (`previews_v7/egyptian_fighter_copy_makehuman_vest_sword.png`).
* Autoskin was tested by stripping the weights of rigs whose correct weights are known, re-skinning them, and
  comparing the walk pose:

  | rig | mean error | p95 | max | worst area |
  |---|---|---|---|---|
  | lanky | 3 mm | 11 mm | 27 mm | |
  | chibi | 5 mm | 16 mm | 60 mm | |
  | stocky | 6 mm | 17 mm | 127 mm | |
  | MakeHuman, 65 bones | 3 mm | 14 mm | 80 mm | |
  | mannequin | 18 mm | 89 mm | 304 mm | visible tear at the shin/foot |

## New in v6: your own FBX / GLB rigs and animations as templates (the Library)
Everything is still pip-only (no Blender, no Autodesk FBX SDK, no assimp) and runs on Windows 10 and Linux.

* **Library folder:** `library/` sits next to forge.py. Set `$SFS_LIBRARY` or `--library` to use another one.
  * It holds `rigs/`, `animations/` and `kits/`, plus an `inbox/` where you can drop files and then press Rescan.
  * Each asset stores `rig.json` + `rig.npz` (the normalised skeleton, mesh, skin and clips), an editable
    `bonemap.json`, `licence.json` and `thumb.png`.
* **Import:** our own pure-Python readers, `sforge/fbxread.py` and `sforge/gltfread.py`.
  * FBX 7.x, binary and ASCII. Units, axes, pre/post rotations, clusters, multiple takes and embedded textures.
  * glTF 2.0 / GLB. Skins, every animation, embedded textures.
  * Static meshes in other formats only load through optional trimesh/pyassimp.
* **Bone maps:** the bone-name convention is detected automatically: Mixamo (`mixamorig:`), Rigify (`DEF-`/`ORG-`),
  Unity/Humanoid, Sprite Forge, or generic (pattern matching).
  * The result is mapped to 22 canonical bones and saved as editable JSON.
  * You can edit it with `forge.py library bonemap NAME --set canon=Bone`, or in the Library tab's bone-map editor.
* **Rigs as templates:**
  * GUI: Build mode "library", or the Library tab's "Use as template" button.
  * CLI: `forge.py build --rig NAME|file.fbx ...`
  * Kits recolour the rig's own materials (`--kit NAME`, extra variants with `--kits a,b`).
  * Console builds decimate the rig to the console's triangle budget (skin-aware clustering, or
    fast-simplification if installed).
* **Retargeting:** `forge.py retarget SRC[:clip] TGT [--save]`
  * Rest-pose compensation (per-bone direction transfer).
  * Root motion: keep, in-place or root.
  * The stride and hip height are scaled to the target's leg length, and feet and toes are kept on the ground.
  * Export with `forge.py library export NAME out.fbx|out.glb`: every clip becomes a take.
* **Mocap onto any rig:** `forge.py mocap clip.mp4 --rig NAME`.
* **Per-move clip mapping:**
  * Use `--clip move=asset:clip@speed=1.2,trim=0.2-1.0,loop` (trim is in seconds; `once` = no loop), a profile `clip_map`, or
    the Build tab's library-clip column.
  * Fallback order: clip map, then mocap, then the rig's own clip of the same name, then a same-named clip from
    another library asset (retargeted), then the procedural mannequin motion (retargeted), then the rest pose.
* **Library tab (GUI):**
  * Thumbnails and asset info.
  * Clip play and scrub.
  * Add FBX/GLB and Remove.
  * The bone-map viewer and editor.
  * The licence editor.
  * Use as template / Use clip for a move.
  * Export pack / Install pack.
* **Redistributable packs (`.sfpack`):** a zip holding `pack.json` plus the rigs, animations, kits and thumbnails.
  * Commands: `forge.py library pack OUT.sfpack NAMES|--all`, `library install FILE --accept-licences` and
    `library verify FILE`.
  * Checks: sha256 for every file, safe paths only, and a complete licence record for every asset.
* **Licences (mandatory):** each asset has an SPDX id or custom text, author, source URL, redistribution
  (yes/no/unknown) and attribution.
  * Packing refuses assets marked no or unknown, unless you give `--i-own-the-rights NAME --by "Your Name"`.
    That confirmation is recorded in the pack.
  * Clips retargeted from a non-redistributable source are tracked (`includes`). They block packing until you
    remove them with `library clips-drop`.
  * Installing shows every licence and needs your acknowledgement.
  * See `LIBRARY_LICENSING.md` or Help > Licensing.
* **Starter pack:** `packs/sfs_starter_cc0.sfpack`, installed in `library/`. It is our own synthetic content, released as CC0 1.0:
  * the mannequin;
  * chibi (Unity names), lanky (Mixamo names) and stocky (Rigify names);
  * an animation-only `sample_moves` asset (wave, squat, hop, bow, spin);
  * 3 kits.
  
  No third-party assets are bundled.
* **Example profile:** `profiles/library_fighter.json` (rig, kit and clip_map in a profile).

### How v6 was tested (evidence in `previews_v6/`, see `previews_v6/RESULTS.md`)
* `python tools/test_library_v6.py`. It writes `previews_v6/RESULTS_tests.md` and covers:
  * the pack round trip, tampering, path traversal, licence refusal and override, and includes;
  * our GLB/FBX round trip for every sample;
  * the Blender 4 oracle (Mixamo, Rigify and Unity names, leaf bones, embedded textures);
  * retargeting between proportions;
  * fighter14 + platformer profiles and GBA + PS1 consoles built from library rigs.
* The `doctor` library check. A clean restricted-PATH Linux run. A library-rig fighter installed into a COPY of
  Egyptian Fighter and played under Xvfb. Headless screenshots of the GUI Library tab.

## New in v5: no hand-installed programs, Windows 10 and Linux
ffmpeg, COLMAP, Blender and the manual MediaPipe setup have been replaced by **pip packages** or **our own
code**. One setup script fetches everything into the project folder (only pip/uv download caches go to your user cache folder), and
there is no admin step.

```
Windows 10:  setup.bat     then  run_studio.bat   /  forge.bat doctor   /  build_release.bat
Linux:       ./setup.sh    then  ./run_studio.sh  /  ./forge.sh doctor  /  ./build_release.sh
```
`setup` makes `.venv/`, pip-installs the core and the extras, and makes `venv_pose/` for mocap. MediaPipe
needs Python 3.9-3.12, so setup gets a private CPython 3.12 into `python312/` via `uv` (itself pip-installed)
and downloads the pose model into `models/`. Re-running it is safe. `forge.py doctor` (or the **Check setup**
button on the Help tab) lists every piece, where it came from, and what a missing one disables.
There is a walkthrough in the Help topic `forge.bat help install` and in the video `videos/05_setup_windows_linux.mp4` (70 s).

| Was (v4) | Now (v5) | Source |
|---|---|---|
| ffmpeg on PATH (video decode/encode, slow-mo) | `imageio-ffmpeg` (a static ffmpeg inside the pip wheel); fallbacks: system ffmpeg, PyAV, OpenCV | pip |
| COLMAP on PATH (scan `--run`) | `pycolmap` (COLMAP's own library: SIFT, matching, incremental mapper, CPU) | pip |
| Blender for model.fbx | **built-in FBX 7.4 binary writer** (`sforge/fbx.py`): skinned mesh, 19 bones, one AnimStack per move, ~0.3 s | our code |
| Blender/open3d for LOD decimation | `fast-simplification` (quadric edge collapse); then open3d, Blender or vertex clustering | pip |
| manual Python 3.12 + MediaPipe install | `setup` → `uv` → private `python312/` → `venv_pose/` + model download | pip + download |
| raylib by hand (C example) | `make -C spriteforge raylib` downloads raylib 5.5 source and builds it | our Makefile |

**What still comes from the system** (none of it is needed for sprites, consoles, GLB/FBX, video, mocap or scan):
* **A Python ≥ 3.9** to start with: python.org or MSYS2 on Windows, the distro's `python3` on Linux.
* **Tk for the visual Studio on Linux:** `sudo apt install python3-tk` (Debian/Ubuntu), `dnf install python3-tkinter`
  (Fedora), or `pacman -S tk` (Arch). The python.org Windows installer and MSYS2 `mingw-w64-ucrt-x86_64-python-tkinter`
  include it. The CLI (`forge`) works without Tk.
* **The optional C/raylib example:** gcc + make (MSYS2 UCRT64: `pacman -S mingw-w64-ucrt-x86_64-gcc
  mingw-w64-ucrt-x86_64-raylib`). On Linux, `build-essential` plus the X11/GL headers (`libx11-dev libxrandr-dev
  libxinerama-dev libxcursor-dev libxi-dev libgl1-mesa-dev`), then `make -C spriteforge raylib && make -C spriteforge`.
* **Blender (optional):** only for `--fbx-writer blender`, if you prefer Blender's exporter.

### How v5 was tested (evidence in `previews_v5/`)
* **Linux, clean extraction, with ffmpeg, COLMAP, Blender, gcc, make, curl, git and uv hidden from PATH and an empty HOME:**
  * `setup.sh`: exit 0 in 27 s on a fast connection, with an empty HOME so nothing was cached (`linux_setup_sh.log`). `forge.sh doctor`: READY (`linux_doctor.txt`, `ui_doctor.png`).
  * `build_release.sh`: exit 0 in 122 s (`linux_build_release_sh.log`). Covered: spec build + FBX, SNES verify,
    profiles, 4 video clips (decode 690-1100 frames/s), scan via pycolmap (72/72 cameras, 0.45 px reprojection,
    24 s total), and mocap (walk 108/110 frames tracked).
  * Consoles nes, gb, genesis, snes, gba, ps1, n64, saturn and ps2gc: `verify_console` PASS (`console_builds_verify.txt`).
  * Photo mode + `--video walk=walk_static.mp4` + GBA: PASS (`photo_build_with_video_walk.png`).
* **Scan accuracy, pycolmap against v4 COLMAP CLI** (`scan_eval_pycolmap.json`): mean surface error 1.31 cm (v4: 1.33);
  ps1 LOD 1.30 cm (v4: 1.40); camera error 5.5 mm mean (v4: 4.5).
* **Built-in FBX, checked by 3 independent readers** (`fbx_check_*.json`, `fbx_builtin_*_in_blender.png`):
  * Blender 4.2: 19 bones, 14 actions, skin weights; joints match the GLB to 0.1 mm at keys and ≤ 3 mm between keys.
  * FBX2glTF: worst joint error 2.7 mm. Assimp: 14 animations, 1790 faces.
  * Mocap FBX: 0.01 mm.
  * Unity and Unreal were **not** tested; they use the same Autodesk FBX SDK reader family as FBX2glTF.
* **Windows:** **not tested on real Windows.** The .bat files were run under **wine 10** (Windows 10 emulation)
  with the official Windows Python 3.12 (`wine_*.log`, `wine_doctor.txt`):
  * `setup.bat` installed everything, including the pycolmap Windows wheel, and `doctor` reported READY.
  * `build_release.bat` exit 0 in 166 s: doctor, the demo build + FBX check, SNES, profiles, video and **scan**
    (pycolmap, 72/72 cameras, 0.45 px, 11 LODs) all passed. The C step was skipped because there is no gcc.
  * Wine itself cannot run numpy 2.x or MediaPipe (a ucrtbase function is missing), so the wine test pinned
    numpy 1.26 and mocap could not run there. These are wine limits, not app limits.
  * Wine found one real bug, an echo with parentheses inside an `if (...)` block in setup.bat, which is now fixed.
    All .bat files are CRLF.

## New in v4: video in, game assets out
Three new input modes (Studio + command line). Use **your own** footage, or the rendered test clips in
`examples_video/`. Nothing is downloaded, and no image of a real person is AI-generated.

| Mode | Command | What you get |
|---|---|---|
| **Video -> sprites** | `forge.bat video --clip walk:8=walk.mp4 --clip jump:12=jump.mp4 --consoles snes,gba` | Sprite frames cut out of the footage. Loops (walk, run) are reduced to one exact cycle; one-shots (jump, punch) are trimmed. Then the normal outputs: moves/, atlas, profiles, HD and console exports. |
| **Video -> mocap (3D)** | `forge.bat mocap --clip walk:8=walk.mp4 --clip punch:10=punch.mp4` | Body motion is tracked with MediaPipe Pose and fitted to the mannequin skeleton. Output: model.glb / model.fbx with one clip per move, plus mannequin sprites (any angle, kit or console). |
| **Orbit video -> 3D mesh** | `forge.bat scan --video orbit.mp4 --run --height 1.75` or `forge.bat scan --mesh texturedMesh.obj` | Sharp frames are picked and a COLMAP/Meshroom project is written. With `--run`, COLMAP solves the cameras (CPU), our CPU depth maps are fused into a mesh, and you get console LODs (GLB/OBJ per triangle budget). This mode is **guided, not one-click.** |

How the video modes work:
* **Camera:** auto-detected as static, handheld or **tracking**. Tracking covers "running in frame", where
  the camera follows the runner. In that case the background is rebuilt as a moving panorama per parallax layer.
* **Background:** median, empty plate, green/blue screen, or rembg.
* **Slow motion:** optical-flow in-between frames (`--slowmo 2`).

Help topics: `forge.bat help video | mocap | scan | python`. There is also a tutorial video:
`videos/04_video_to_game.mp4`.

**Mocap and scan setup (v5):** `setup.bat` / `./setup.sh` does both (venv_pose + model; pycolmap). No COLMAP or
ffmpeg install is needed. (v4 used the COLMAP and ffmpeg programs; the timings below are the v4 measurements.)

### Measured on this build box (8-core CPU, no GPU), 640x360 test clips
| Step | Speed | Native code doing the work |
|---|---|---|
| decode | ~500 frames/s | ffmpeg |
| cut-out, static camera | ~150 frames/s | NumPy / OpenCV |
| cut-out, tracking camera + 3 parallax layers | ~17 frames/s (4 frames/s without OpenCV) | OpenCV |
| 4 clips -> HD + SNES + GBA sprites | 23.7 s total | |
| pose tracking | ~70 frames/s full model, 24 frames/s heavy | MediaPipe (TFLite) |
| skeleton fit | 15–20 frames/s | SciPy |
| 72-frame orbit -> mesh -> 11 LODs | 42 s (COLMAP 25 s, dense 11 s) | COLMAP, OpenCV, Blender |

**Is Python the right language?** Yes, as the glue. Every heavy step above runs in C/C++ libraries. A
rewrite in C++ would mostly speed up the orchestration, which is a small share of the time. The one place
that would really benefit from native/GPU code is a dense high-res reconstruction, and that is exactly what
COLMAP-CUDA, OpenMVS or Meshroom do. The Studio exports a project for those tools and imports their mesh.

### Accuracy on clips with known ground truth (previews_v4/)
**Video -> sprites:**
* Walk loop period 33.0 frames (truth 33).
* Run on a tracking camera: 19.9 (truth 19.8).
* Jump action frames 27–60 (truth 27–61).
* Punch (green screen) frames 8–20.

**Mocap:**
* Tracked frames: walk 108/110, run 89/90, jump 58/73, punch 28/28.
* Walk: thigh angles within 6–8°, knees 8–14°.
* Run: thighs 13–16°, knees 20–26°. Motion blur makes the tracked knees less bent than the true ones.
* model.fbx re-imported in Blender: 19 bones and 4 actions.

**Scan (synthetic textured mannequin, 72 views):**
* 72/72 cameras solved, 0.48 px reprojection error, camera positions within 4.5 mm.
* Mesh within 1.3 cm on average of the true 1.75 m figure (p90 3.1 cm).
* The PS1 600-triangle LOD stays within 1.4 cm.

## New in v3
* **Multi-view input (front / side / back / 3/4, or a video per view).**
  * Studio: Front photo, Side photo (+ "Side faces left"), 3/4 photo and Back photo.
  * CLI: `--side`, `--back`, `--view NAME=SRC` (repeatable; an image, a frame folder or a video).
  * Each view gets its own cutout and is scaled to the same height, top line and ground line.
  * Outputs: `views/<view>/`, `views/atlas_<view>.png`, `turnaround.png`, `turnaround_preview.png` and
    `billboard8.png`. Every view is listed in atlas.json, sprites.cfg and character.ini.
  * `--views front,right,back,left` or `--billboard8`: views you did not supply are **mirrored** or **interpolated**
    (a squash of the nearest real view). They are always flagged as filled, never invented by AI.
  * Text spec and mannequin modes render every view for real with the 3D renderer.
* **Generic output profiles: `profiles/*.json`.** The studio does not need to know anything about the game. A profile
  declares:
  * moves, frame size, ground line, views
  * extra images (an angle grid, a single frame, a portrait)
  * manifests:
    * `ini`: character.ini-style keys
    * `template`: any text file
    * `json`: any JSON shape, e.g. Phaser animations
    * `godot_spriteframes`: a Godot 4 `.tres`
    * `tiled_tsx`
    * `unity_json`
  * Shipped profiles: generic_2d, fighter14, kart_racer (TurboTumble64-style), gaelic36, platformer, topdown8dir,
    retro_nes, retro_snes and retro_gba.
  * Studio: the Profile dropdown, plus "Create profile..." (it saves `profiles/<name>.json`) and Profile vars
    (`key=value; ...` for the game's own ini keys).
  * CLI:
    * `forge.py profile list|show|validate|new NAME --from platformer --moves ... --views ... --manifest godot_spriteframes`
    * `forge.py build ... --profile kart_racer --set tagline="Hi"`
* **Built-in spec editor** ("Edit spec..."), so you can write a fictional character in the studio.
* **Tutorial videos** in `videos/` (screen recordings of the real program, with captions):
  * 01: photo to game
  * 02: text to character, plus FBX
  * 03: using the sheet and console export

  You can re-record them with `python3 tools/record_tutorial.py tools/tutorials/<plan>.json`
  (this needs Linux with Xvfb; ffmpeg comes from imageio-ffmpeg).
* Test evidence is in `previews_v3/`:
  * TurboTumble64 in-game shots (select screen and race) using the side and back views
  * the Egyptian Fighter re-run (all 14 moves)
  * GUI screenshots and turnaround contact sheets

## New in v2  (start here: **HELP.md**, the Help tab, or `forge.py help`)
* **Help for beginners** - Help tab + Help menu in the studio, `python forge.py help [topic]`, and HELP.md
  (topics: quickstart, modes, outputs, sprite-sheet, engines, consoles, fields, troubleshooting).
  Every field has a **(?)** tooltip. **Example walkthrough** builds the sample character and opens a preview that
  explains each output file.
* **Adaptive UI** - pick an input mode (Photo / Frames folder / Per-move sheets / Sprite sheet / Text spec /
  Gaelic-3D mannequin) and only the fields that mode needs are shown; missing/invalid fields get a plain-English message.
* **New input mode: per-move sheets** - one strip image per move (`--move-sheet walk=walk.png`, repeat; `--frames-across N`
  if frames touch, otherwise gaps are detected automatically).
* **Console targets** - `--console KEY` (or the "Console target" dropdown). 18 presets from Atari 2600 to PS5 / PC HD:
  `python forge.py consoles`. Each one adds `out/<name>/console/` (the normal output is unchanged):
  * retro (2600, NES, SMS, GB, SNES, Genesis, GBA, DS): frame size limit, palette quantised to the console's
    colour space (+ optional Floyd-Steinberg dither), index 0 = transparent, deduplicated 8x8 tiles (h-flip aware) in
    VRAM-sized banks -> indexed `tiles_bankN.png` + raw `.chr/.2bpp/.4bpp`, `palette.pal/.bin/.png`,
    `<name>_<key>.h` with C arrays (palette, tiles, per-frame tile maps, anims) and `console.json`.
  * texture era (PS1, N64, Saturn, Dreamcast, PS2/GC/Xbox, PSP, Wii/360/PS3, Switch/PS4/One, PS5/Series, PC HD):
    frames packed on pow2 pages within the max texture size (CLUT-indexed where the console uses palettes, ARGB4444
    on Dreamcast), rect table in the `.h`, plus a low-poly `model_<key>.glb/.fbx` within the polygon budget.
  * the numbers are typical practical values, not hardware maxima; everything marked "approx" is listed in HELP.md.
* `tools/verify_console.py out/<name>` checks a console export against its preset (sizes, colours, banks, pages, tris).

## Hard rules (built in)
* The tool **never** generates images of real people with AI.
* PHOTO mode only transforms **your own photo pixels** procedurally. It cuts out, scales, grounds, and applies
  simple bob/lean/squash/flash transforms. **One photo cannot be auto-animated into 36 real poses.** Moves
  with no source frames are filled with labelled placeholder transforms and listed in `build_report.txt`.
  For real poses, import frames made elsewhere (`--video MOVE=clip.mp4|folder`, `--frames DIR`, or `--sheet`).
* SPEC mode builds a **fictional** character from key=value text. It is a procedural low-poly mannequin with no
  likeness. The `ethnicity` key is metadata only.
* The optional `rembg` package is used only for background *segmentation* (cut-out), never for generation.

## Install (Windows 10 or Linux)
```
setup.bat / ./setup.sh                 once: .venv + pip packages + venv_pose (mocap) + pose model
python tools/setup_pose.py             just the pose model (needed by forge.py cutout / photo builds)
forge.bat doctor / ./forge.sh doctor   what is installed and what a missing piece disables
run_studio.bat / ./run_studio.sh       the visual UI
forge.bat build ... / ./forge.sh build ...   the CLI; same core as the UI
build_release.bat / ./build_release.sh       demo builds + all verifiers (+ the C example if gcc is there)
```
* The scripts use `.venv` when it exists, otherwise `python` / `python3`. In VS Code, open the folder and use
  the terminal: cmd/PowerShell for .bat, MSYS2 UCRT64 or Git Bash for the .sh scripts.
* The core (2D, consoles, GLB and FBX) needs Python ≥ 3.9 with Pillow, numpy and scipy (`requirements.txt`).
  `requirements-extras.txt` adds OpenCV, scikit-image, imageio-ffmpeg, pycolmap, fast-simplification and trimesh.
* FBX is written by the built-in writer. Blender is optional (`--fbx-writer blender`, Blender field in the UI).
* The C example: MSYS2 `pacman -S mingw-w64-ucrt-x86_64-gcc mingw-w64-ucrt-x86_64-raylib` on Windows.
  On Linux, `make -C spriteforge raylib && make -C spriteforge` (needs gcc, make and the X11/GL headers listed above).

## Modes
| mode | command | what you get |
|---|---|---|
| SPEC | `forge.bat build --spec char.txt --preset fighter14` | fictional rigged mannequin rendered for every move, plus model.glb/.fbx |
| PHOTO | `forge.bat build --photo front.png --back back.png --name qanna --preset kart12` | your pixels; idle (+ idle_back); other moves = placeholder transforms (reported) |
| PHOTO + video | `... --video walk=walk.mp4 --video kick=frames\kick\` | real frames for those moves (video files are decoded by imageio-ffmpeg) |
| FRAMES / SHEET | `--frames DIR` / `--sheet sheet.png --sheet-layout rows` | normalises art made elsewhere |
| mannequin | `forge.bat build --preset gaelic36 --kits all` | default no-likeness figure in kits home/away/blue/red/black/gk |

* `forge.bat example-spec` prints a spec template (see also `examples_char.txt`).
* `forge.bat list` lists presets and motions.
* Presets:
  * `gaelic36` (36 Gaelic football moves)
  * `fighter14` (SpriteForge/EF fighter names)
  * `platformer10`
  * `kart12` (TurboTumble64)
* Custom moves: `--moves "idle,walk,dash=sprint:8:14:loop"`.
* `--prop none` renders the kart set as the driver only, for games that draw their own kart.
* `--yaw` sets the camera angle: 65 = 3/4 right-facing (default), 90 = profile.

UI: tick moves by category or preset, then set frames/fps/loop per move, the source (spec/photo/frames/mannequin),
the frame size, figure height and ground line. Press **Build** and watch the log and the live preview. Projects
save to .json, which the CLI can load with `--config`.

## Output (final format)
```
out/<name>/character.ini     [character] name, frame_w, frame_h, ground_y, pivot_x, scale, height_px, facing=right, mode, moves
                             [moves] move=frames,fps,loop,source ; [spec]/[source] metadata
out/<name>/sprites.cfg       SpriteForge v1 (below) - read by spriteforge/include/spriteforge.h
out/<name>/atlas.png         one ROW per move (atlas_1.png, atlas_2.png... only if --max-atlas is exceeded)
out/<name>/atlas.json        TexturePacker-style "frames" hash + "animations" (fps, loop, row, page) + meta.pivot
out/<name>/moves/<move>_<NN>.png   individual RGBA frames
out/<name>/preview.png       labelled contact sheet
out/<name>/model.glb / model.fbx   SPEC / mannequin only (rigged, skinned, with animation clips)
out/<name>/build_report.txt  what was rendered / imported / FILLED
```
* Every frame is RGBA, faces **right**, and is the same size.
* The feet of every grounded frame sit on `ground_y`, with the pivot at bottom-centre (`pivot_x`, `ground_y`).
* Airborne frames (jumps) sit above the line, never below it.
* Flip horizontally to face left.

sprites.cfg (SpriteForge v1):
```
version 1
name nova_vance
frame 512 512
height 303            # standing height in px
ground 481            # ground line y in every frame
anchor_x 256
move idle atlas.png 6 512 512 8 1 0     # name file frames w h fps loop row ; frame i = (i*w, row*h)
```
Engine use:
* **C/raylib:** `#define SPRITEFORGE_IMPLEMENTATION` + `#include "spriteforge.h"`, then `SF_LoadCharacter("out/nova_vance")`.
  See `spriteforge/example/main.c`; run `bin/example DIR [DIR2] [--shots outdir]`.
* **Godot / Unity / Phaser / Defold:** read `atlas.json` (frame rects, fps, loop and the pivot are all there),
  or use the `moves/*.png` frames directly.
* **3D engines:** model.glb (Y up, faces +Z, one clip per move); model.fbx for Unity/Unreal.

## Verification tools
```
python tools/verify_output.py out/<name>                        # sprites.cfg rects == atlas.json rects, frame counts
python spriteforge/tools/verify_cfg.py --airborne-ok out/<name>   # ground line, anchor, image bounds
python tools/verify_console.py out/<name>                       # console limits: size, colours, tiles, banks, tris
python tools/verify_fbx.py model.glb model.fbx [--json r.json]  # FBX vs GLB with every reader found (Blender, FBX2glTF, assimp)
python tools/scan_eval.py --work out_scan/<name> meshes...      # scan vs ground truth (the demo orbit clip)
python tools/make_release_zip.py OUT.zip [--max-mb 25]          # release zip: CRLF .bat, LF+exec .sh, split if too big
```

## Game adapters (used for the in-game tests)
* `tools/export_ef.py SRC DST --projectile ball` converts to the Egyptian Fighter per-anim strip format
  (special1→pyramid_blast, special2→bum_fireball, jumpattack→jump_attack).
  The game only needs a character table entry; see `ef_game_changes.diff` in the test pack.
* `tools/export_tt64.py SRC DST --display "Nova Vance" ...` makes a TurboTumble64 racer folder:
  sprite.png, portrait.png, and a `[turbotumble64]` block in character.ini.
  * Stock TT64 shows it as a static sprite.
  * Per-move animation needs the small driver patch (`tt64_game_changes.diff`: `sfAnim` field, `spriteforge.h`
    loader, and a move picker from kart state).

## Limits (honest)
* **v7 limits:**
  * Autoskin is distance-based. Loose clothing, long hair, capes and touching limbs (hands on hips) get wrong
    weights. It was tested only on synthetic meshes with known answers, not on a real scanned or AI-generated mesh.
  * Outfit fitting moves the outfit with the bone segments of the new rig. Very different body shapes can still
    poke through, and `--slot-color` does not recolour textured slots.
  * The MakeHuman extremes are extreme: height=1 gives about 2.4 m, which is what MakeHuman's own target does.
    Weight changes the shape only a little. There are no clothes, hair, eyes or textures; MakeHuman's clothes
    and proxies are not used. Skin is one colour (Skin_Mat), and the kit slots come from the material split.
  * Material slots on a library rig are guessed from bone regions when the file has one material. Check the
    preview and use `--material-split off` if the guess is wrong.
* **v6 library limits:**
  * Retargeting copies bone directions with rest-pose compensation and leg-length scaling. There is no IK, foot
    locking or hand contact, so feet can slide a little on rigs with very different proportions, and hands
    don't meet props.
  * The test's "direction error 0" is true by construction. The independent checks are hip height per leg
    length (within 2.5% in the tests) and ground contact (kept by the ground fix).
  * Only the first animation layer of each FBX take is read. Blendshapes, constraints, IK targets and
    non-skin deformers are ignored.
  * Textures that are not embedded must sit next to the FBX/GLB, or be in the paths the file points to.
  * Imports are grounded (lowest point at y=0), so a skeleton-only asset moves up or down by a few cm.
  * Clip speed changes only the 3D take timing; the sprite frame counts come from the move preset.
  * Console decimation uses skin-aware vertex clustering. At very low budgets (around 300 triangles) thin parts
    can get holes. Install fast-simplification for quadric decimation, which is used only if every body part
    survives.
  * Licence records are what the user says they are. The Studio enforces them but cannot check them.
  * The Egyptian Fighter test replaced an existing roster slot (char_daragh) in a copy of the game. The game
    has a hard-coded roster, so the slot keeps that character's display name.
* **v4 video modes:**
  * Video -> sprites cuts out the real footage; it does not redraw it. Loose hair and clothing, shadows on
    busy floors, and crowds or trees behind a moving camera give rough edges (check `_debug/*.png`).
  * Overlapping limbs stay overlapped, and the person must stay in frame.
* **Mocap:**
  * Body only: no fingers, face or foot roll.
  * Side-on clips work best. Arms behind the body, spins and fast blurred limbs are weak, and runs come out
    less bent.
  * It is good blocking or reference animation, not polished game animation.
  * One photo can still NOT be turned into new poses. Mocap needs real video of the motion.
* **Scan:**
  * Tested only on a synthetic, perfectly still, richly textured render. Real people move during an orbit,
    and shiny, plain or dark surfaces fail.
  * The CPU mesh has vertex colours only, so it is not a high-res textured scan. COLMAP's own dense step
    needs CUDA, and OpenMVS/Meshroom were not available on the CPU build box.
  * For hero-quality models use Meshroom or RealityScan on `images/`, then `forge.py scan --mesh` for LODs.
  * LODs use fast-simplification (quadric). Without it, open3d or Blender is tried, then crude vertex clustering.
* PHOTO mode with one photo gives one real pose. Every other move is a transform of that pose (bob,
  lean, squash, flash...), marked as `placeholder` in character.ini and build_report.txt.
* Views:
  * Each photo view is real only for its idle (or its video). The other moves per view are placeholders.
  * Filled views (45, 135...) are horizontal squashes of a real view, not new angles. Mirrored views flip text
    and logos.
  * Views are aligned by height and ground line only. If the side and back photos have different proportions,
    the views will not match.
* The v3 kart test used SYNTHETIC mannequin renders as side and back inputs, labelled as such, because only a
  front image of that test character exists.
* Profiles describe files, not game logic. The Unity JSON and Tiled .tsx outputs were checked by parsing;
  Godot .tres files were loaded in Godot 4.3 (headless).
* The mannequin is deliberately generic low-poly with no faces or likeness. Motions are procedural keyframes,
  game-ready but not mocap quality.
* FBX is written by our own code (binary FBX 7.4). It was validated with Blender 4.2, FBX2glTF and assimp, not in
  Unity or Unreal. If an engine rejects it, export with `--fbx-writer blender` (needs Blender) or use model.glb.
* **v5 platforms:** Linux was tested from a clean extraction. Windows was tested only under wine 10, not on a
  real Windows 10 PC. macOS should work with `setup.sh`, but it was not tested.
* MediaPipe exists only for Python 3.9-3.12. Setup fetches a private CPython 3.12 for it (about 110 MB unpacked, in `python312/`).

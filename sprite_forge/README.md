# Sprite Forge Studio v8.0

A character sprite + 3D pipeline with a visual UI. The 2D core and C/raylib loader are the
**SpriteForge** base pipeline (`spriteforge/`, vendored, same `sprites.cfg` v1 format). The Studio adds the
Tkinter UI, SPEC mode, the procedural rigged mannequin, GLB/FBX export, `character.ini`, `atlas.json` and
game exporters.

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

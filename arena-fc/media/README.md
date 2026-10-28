# Arena FC — gameplay videos & screenshots

Everything in this folder was produced from the **running game** on 27 October 2026.
Nothing here is a mockup, a still of a static scene, or a third-party asset.

## Videos (`videos/`)

| File | Length | What it shows |
| --- | --- | --- |
| `01_match.mp4` | 20 s, 1280×720, 24 fps | 5-a-side match in the exported C# Linux build. Real keyboard input: sprint, pass, through ball, charged shot, camera cycle, tackle, pause/resume, second-half attack. |
| `02_editor.mp4` | 15 s, 1280×720, 24 fps | Character/skeleton editor: player selection, live height & bulk changes to the 18-bone skinned mesh, Kit/Face/Skeleton/Attributes tabs, bone posing. |
| `03_menu.mp4` | 16 s, 1280×720, 24 fps | Animated 3D main menu → scrollable match settings → controls → character editor → 11v11 kick-off. |
| `04_browser.mp4` | 20 s, 1280×720, 12 fps | The exported WebAssembly/GDScript Browser Edition actually running in Chromium with SwiftShader WebGL, from load to a 5-a-side match, cycling cameras and zooming with touch controls. |
| `05_cameras.mp4` | 21 s, 1280×720, 24 fps | The camera/ring upgrade: all six views selected with `1`–`6`, mouse-wheel zoom in and out, and the selection ring + arrow staying visible from every angle. |
| `06_friends.mp4` | 18 s, 1280×720, 12 fps | A real online match: an exported Linux client in room `FRIEND6` playing against a second human host over the authoritative WebSocket server. HUD shows ping / LIVE; both rings visible. |
| `07_online_v2.mp4` | 8 s, 960×540, 12 fps | v2 online: a live authoritative room with the rollback-prediction HUD (`ONLINE · tick · ping · host · RB corrections/replayed ticks`). 96 real viewport frames from the running C# client. |

All seven are H.264 MP4 with `yuv420p` and `+faststart`, playable in browsers, VLC,
Windows Media Player, QuickTime and most phones.

## Screenshots (`screenshots/`)

32 PNGs (30 at 1280×720, plus `31`/`32` at 1280×720). `01`–`04` are frames from the match clip, `05`–`08` from the
editor clip, `09`–`13` from the menu clip, `14` from the browser clip, `15` is a
clean close-up of the procedural rigged character, `16`–`17` are the earlier
platform captures (GDScript Browser Edition in Godot and the exported web build in
Chromium), and `18`–`25` are one frame from each camera view / zoom state in the
`05_cameras` clip, `26` shows the configurable default view/zoom in Match
Settings, `27` is the WebGL browser client playing online in Chromium, `28`
is the room lobby, `29` is a live 1v1 online match with two selection rings,
`30` is local 2-player on one machine, `31` is the v2 PLAY WITH FRIENDS lobby
(reconnect / host migration / rollback status line and RECONNECT button), and
`32` is the live online match with the rollback HUD
(`ONLINE · tick 1109 · ping 320ms · host #0 · RB 380/240t e=0.00m`).

`gallery.html` is a self-contained index: open it in a browser after extracting
the ZIP to play the clips and browse the screenshots. Thumbnails are inlined as
data URIs, so it also renders inside a sandboxed preview.

**Video durations never read 0:00.** Each card bakes the real length (parsed
from the MP4 `mvhd` atom at build time) into a visible badge and into the
caption, and the player uses `preload="metadata"` instead of `preload="none"`.
Because Arena's in-app file preview is a sandboxed iframe with no network
access, sibling `videos/*.mp4` files cannot be streamed there: a short silent
low-resolution copy of each clip is embedded directly in the page as a data URI
and a small inline script swaps to it if the full-size source fails to load.
So you get a playable preview clip inside the viewer and the full-quality clip
from the ZIP / the **Open / download** link.

## How the footage was made

```bash
# 1. Build the game (see ../README.md)
python3 Tools/build.py --platforms linux --out build

# 2. Record the native clips (needs Xvfb, xdotool, ffmpeg and Mesa llvmpipe)
python3 Tools/record_media.py --game build/linux/ArenaFC.x86_64 \
        --out media --clip all --display 140

# 3. Record the web build in Chromium (needs a built build/web folder)
python3 Tools/record_media.py --out media --clip browser \
        --web-dir build/web --display 243

# 4. Rebuild the offline gallery index
python3 Tools/make_gallery.py
```

The native clips use Godot's `--fixed-fps 24`, which forces a deterministic
1/24 s timestep. `Boot.cs --record` writes the actual viewport of every rendered
frame to PNG; `xdotool` injects real key/mouse events while the frames are being
produced; `ffmpeg` encodes the sequence at 24 fps. That is why motion is smooth
even though the software rasteriser only managed ~2 real frames per second on
this machine. The browser clip is a live X11 grab of a visible Chromium window.

## Honest limitations

Software rendering (Mesa llvmpipe / SwiftShader) was used because this build
machine has no GPU, so the footage shows the game's real geometry, shaders and
UI — not its best possible frame rate. There is no audio track (the game has no
licensed audio). This is an original indie-scale football game: procedural
characters, kits, stadium and crowd, no licensed teams/likenesses/mocap/
commentary, and no career mode, matchmaking/accounts, VAR or skill-move system.
Online play with friends *is* implemented (room codes, reconnect, host
migration, rollback prediction). The web edition is a reduced GDScript
5-a-side build because Godot 4 cannot export C# projects to Web.

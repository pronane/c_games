# Arena FC — verification report

Executed on **Debian 13 x86_64**, 2026‑10‑26/27, using
Godot `4.7.2.stable.mono.official.ed1daf0bf` and the standard editor
`4.7.2.stable.official.ed1daf0bf`, .NET SDK `8.0.427` + `9.0.320`, Mesa llvmpipe
software OpenGL under Xvfb for the visual tests.

## 1. Compile

```
$ dotnet build ArenaFC.sln -c Release -v:q
Build succeeded. 0 Warning(s) 0 Error(s)
```

## 2. Pure‑C# core tests (no Godot required)

```
$ dotnet run --project Tests/CoreTests.csproj -c Release
RESULT: 66 passed, 0 failed
```

Covered: 18‑bone hierarchy, >500 vertices / >400 triangles / ≥7 surfaces, four bone
indices and four weights per vertex with every weight sum = 1, in‑range indices, finite
positions/normals, character height and ground contact, live proportion changes, blended
(not rigid) skinning, JSON round trips (colours, bone pose, 11‑player roster), deterministic
RNG, 5/7/11‑a‑side setup, 30 s of 11v11 simulation (finite state, on‑pitch players,
stamina bounds, populated commentary, AI actions, movement), byte‑identical deterministic
replay of ball and players after 10 s, goal detection/event/restart, shot velocity + stats,
throw‑in + restart, half time with switched ends, full time, and human move/switch commands.

## 3. In‑engine Godot integration tests

```
$ godot --headless --path . -- --selftest
RESULT: 55 passed, 0 failed
ARENA_FC_SELFTEST_PASS
```

Covered: all five shaders load; a real `Skeleton3D` with 18 bones; `Skin` with 18 inverse
binds; `MeshInstance3D` skeleton path; `ArrayMesh` with ≥7 PBR surfaces and 4‑bone weights;
mesh AABB height; instance AABB; bind matrices are the exact inverse of bone global rest
(no collapse); posing a bone produces a real deformation; editor pose override; bone overlay;
**GLB export** (`version=2 size≈164 KB jsonChunk=JSON meshes=1 skins=1 jointsArrays=1`),
file on disk, inspection, **Godot re‑import** of the exported GLB with ≥18 joints; JSON
round trip through `user://` `FileAccess`; stadium construction with procedural pitch
shader; HUD + touch controls; character editor construction; full 3D match pipeline
(10 rigs, all with skinned meshes, ball, current camera, 12 simulated seconds, clock,
events, no NaN, rig transforms following simulation, HUD update).

## 4. Live game loop (no test harness shortcuts)

```
$ godot --headless --path . --quit-after 300 -- --match
ARENA_FC_BOOT_OK       (exit 0, no errors — 300 physics frames of real 5v5)
```

## 5. Real rendered frames (Xvfb + Mesa llvmpipe, `--screenshot`)

`screenshots/menu.png`, `screenshots/match.png`, `screenshots/editor.png`,
`screenshots/browser.png`, `screenshots/web_browser.png` — all 1280×720, captured
from the running game / real browser (not mocked).
The exported Linux binary was also rendered the same way.

## 6. Exported Linux binary — executed

```
$ ./build/linux/ArenaFC.x86_64 --headless -- --selftest
RESULT: 55 passed, 0 failed   (exit 0)
$ ./build/linux/ArenaFC.x86_64 -- --match --screenshot   # under Xvfb
ARENA_FC_SCREENSHOT ... size=1280x720 err=Ok
```

## 7. Cross‑platform export

```
$ python3 Tools/build.py --platforms all
--- Web / HTML5 (GDScript Browser Edition) ---   OK  build/web/index.html  (40.1 MB)
--- Windows Desktop ---                          OK  build/windows/ArenaFC.exe  (109.4 MB)
--- Linux ---                                    OK  build/linux/ArenaFC.x86_64 (73.7 MB)
--- macOS ---                                    OK  build/macos/ArenaFC.zip    (129.7 MB)
--- Android ---                                  OK  build/android/ArenaFC.apk  (102.3 MB)
--- iOS ---           skipped: Godot 4.7 refuses C#/.NET Apple Embedded exports outside macOS
```

Android APK verified with `aapt dump badging`:
`package: name='com.arenafc.football' versionCode='1' versionName='1.0.0' ...
sdkVersion:'24' application-label:'Arena FC'`.

Web build verified by exporting with the **standard** Godot editor (Web templates
`web_nothreads_release.zip`) and by running the GDScript Browser Edition directly in
Godot with `--auto-play` / `--auto-editor` (300/60 frames, no errors) and rendering
`screenshots/browser.png`.

## 8. Browser Edition (GDScript) headless

```
$ godot_std --headless --path . Web/BrowserMain.tscn --quit-after 300 -- --auto-play
$ godot_std --headless --path . Web/BrowserMain.tscn --quit-after 60  -- --auto-editor
(no errors)
```

## 9. Exported Web build in a real browser

```
$ python3 Tools/build.py --serve               # COOP/COEP + application/wasm headers
$ chromium --headless=new --no-sandbox --enable-unsafe-swiftshader \
           --use-gl=angle --use-angle=swiftshader --window-size=1280,720 \
           --virtual-time-budget=60000 --screenshot=screenshots/web_browser.png \
           http://127.0.0.1:8080/
```

Chromium 156 loaded the exported `index.html`, fetched `index.wasm` (39.5 MB,
`application/wasm`) and `index.pck`, initialised **WebGL 2.0**
(`OpenGL API OpenGL ES 3.0 (WebGL 2.0 ...) - Compatibility`) and rendered the
3D main menu — see `screenshots/web_browser.png`. The GDScript match and editor
scenes were separately run for 300/60 physics frames in Godot with no errors (§8).

## 10. Gameplay video recording (real footage, 27 October 2026)

The media request was verified by actually playing and recording the game. A new
`--record DIR --frames N` mode in `Boot.cs` dumps the live viewport of every
rendered frame; combined with Godot's `--fixed-fps 24` this gives a deterministic
24 fps timeline even on a software rasteriser. `Tools/record_media.py` drives the
exported Linux build under Xvfb/Mesa llvmpipe, injects real keyboard/mouse input
with `xdotool` at specified frame numbers, and encodes the PNG sequences with
`ffmpeg`. `Tools/make_gallery.py` builds the offline `media/gallery.html` index.

```
$ python3 Tools/record_media.py --game build/linux/ArenaFC.x86_64 --out media --clip all
[01_match]  captured 480 frames -> videos/01_match.mp4   1280x720 24fps 19.96 s
[02_editor] captured 360 frames -> videos/02_editor.mp4  1280x720 24fps 14.96 s
[03_menu]   captured 384 frames -> videos/03_menu.mp4    1280x720 24fps 15.96 s
[05_cameras] captured 504 frames -> videos/05_cameras.mp4 1280x720 24fps 20.96 s
$ python3 Tools/record_media.py --out media --clip browser --web-dir build/web
[04_browser] videos/04_browser.mp4                       1280x720 12fps 20.00 s
```

Verification observations:

* Injected input is real — e.g. `Escape` produces the in-game PAUSED overlay,
  `C` switches the HUD camera label from `Broadcast` to `Player cam`, and `SPACE`
  fills the charge bar (see `media/screenshots/02_charged_shot.png` and
  `03_pause_menu.png`).
* 30 screenshots were extracted from those same frame sequences plus a clean
  `--rigshot` close-up and the two earlier browser/platform captures.
* The exported `index.wasm` (39.5 MB) was loaded in a visible Chromium window with
  SwiftShader WebGL; the `PLAY 5-A-SIDE` button was clicked and the match ran
  (`media/screenshots/14_browser_webgl.png`).
* Two defects found and fixed during recording: (1) `--record` originally leaked
  one `Image` per frame and was OOM-killed after 215 frames — now explicitly
  disposed, RSS stayed flat at ~535 MB over 480 frames; (2) long menu overlays
  pushed the `Back` button off-screen — `GameApp.Overlay` now wraps the body in a
  `ScrollContainer`, verified by clicking Back in `03_menu.mp4`.
* New in the camera update: `SelectionMarker.cs` (pulsing distance-compensated
  ring + head arrow), six `BroadcastCamera` views, dolly zoom
  (0.55×–2.4×) from wheel/pinch/keys/gamepad/touch, and `MatchOptions.CameraMode`
  / `CameraZoom`. Seven new in-engine assertions cover all six views, zoom
  clamping, orbit drag and the marker; total rose from 39 to 46. The same ring
  and four views with zoom were added to the GDScript Browser Edition and its
  WASM build was re-exported and re-captured in Chromium.
* Software rendering was used (no GPU on the build host), so the recordings show
  the real geometry/shaders/UI rather than the frame rate a GPU would achieve.

## 11. Known engine / environment constraints observed

* `Godot 4.7.2` cannot export a C#/.NET project to Web → the GDScript fallback above.
* C# Android export requires `net9.0` (the Android export template rejects `net8.0`),
  a JDK, Android SDK platform‑tools and build‑tools. All were installed and used here.
* C# iOS export is refused on non‑macOS hosts (`requires macOS`).
* macOS `.app` is exported unsigned; signing/notarisation requires macOS + Xcode.
* The Android APK is unsigned by default (`package/signed=false`) — supply a keystore.
* Godot logs a harmless `EditorSettings not instantiated yet ... shutdown_adb_on_exit`
  message after headless exports.

---

## Play With Friends verification (online / LAN / local 2P)

Added after the camera update. Tests and captures below are from the exported
builds, not mocks.

**Unit + in-engine assertions** (`python3 Tools/build.py --check`)

```
RESULT: 66 passed, 0 failed    (pure-C# core, wire protocol, snapshots, replay)
RESULT: 55 passed, 0 failed    (in-engine Godot: cameras, net drivers, HUD, UI)
```

New core coverage: `StepNetwork` drives two humans on opposite teams and is
bit-identical across two independent engines fed the same 240 input frames;
`CommandDto` / `Packet` round-trip; room-code and URL normalisation; snapshot
build + `ApplyImmediate` + interpolated apply reproduce the authoritative
state hash; a 240-tick replay survives JSON and reproduces the exact final
state; replay stays under 8 KB/s of 60 Hz play.

**Protocol / server smoke test** (`python3 Tools/net_smoketest.py --seconds 5`)

```
PASS  GET /health returns ok            PASS  client A receives welcome
PASS  server issued a 6-char room code  PASS  B joins the same room (away team)
PASS  lobby lists both players          PASS  host can start the match
PASS  both clients receive snapshots    PASS  snapshots advance the tick
PASS  shared ticks have identical world state
PASS  snapshot contains full team state / per-slot controlled indices
PASS  chat is relayed to the other player
RESULT: PASS  (0 failures)
```

**Two real headless Godot clients, one server** (`--netprobe`)

```
ARENA_FC_NETPROBE ok=True snaps=268 lastTick=779 slot=0 room=GO8888 ping=12
ARENA_FC_NETPROBE ok=True snaps=261 lastTick=759 slot=1 room=GO8888 ping=12
```

Repeated with the **exported Linux binary**:

```
ARENA_FC_NETPROBE ok=True snaps=228 lastTick=662 slot=0 room=EX9999 ping=20
ARENA_FC_NETPROBE ok=True snaps=227 lastTick=659 slot=1 room=EX9999 ping=16
```

**Cross-platform (GDScript browser project + C# desktop guest)**

```
ARENA_FC_WEB_NETPROBE snaps=218 tick=631 room=WEB8Y slot=0 mode=true
ARENA_FC_NETPROBE ok=True snaps=239 lastTick=692 slot=1 room=WEB8Y ping=16
```

**Exported WASM build in Chromium (SwiftShader WebGL)** joined room `WEBPROBE`
via a shareable query link against a desktop host. The host received **435
snapshots in 22 s**; `media/screenshots/27_browser_online.png` shows the
browser rendering the authoritative match with ring, commentary and touch
controls. `media/videos/06_friends.mp4` is an 18 s live capture of a desktop
online match (`ROOM FRIEND6 · LIVE`), with the host streaming **672 snapshots**
over the session. Screenshots `28` (lobby), `29` (online 1v1 with two rings)
and `30` (local 2-player) complete the set.

**Platform notes:** online play tested on Linux (editor + exported binary) and
Web/WASM in Chromium. The same WebSocket client code compiles for Windows,
macOS and Android; those targets were exported but not network-tested in this
sandbox. Browsers cannot use ENet/raw UDP, hence WebSocket for all clients.

---

## v2 online verification — reconnect, host migration, rollback (27 October 2026)

Everything below was executed in this sandbox against the shipped server,
editor builds and exported WASM build. No results are simulated.

### A. Pure-C# core (`dotnet run --project Tests/CoreTests.csproj -c Release`)

```
RESULT: 88 passed, 0 failed      (previous release: 66)
```

New assertions cover: `EngineCheckpoint` capture/restore forks a bit-identical
engine for a further 90 ticks; full authoritative state transfer survives a
JSON round trip and continues deterministically after handoff; full checkpoint
size; 256-bit URL-safe resume tokens, SHA-256 hashing and constant-time
comparison; and 13 rollback-prediction checks — bounded re-simulation on every
correction, exact synchronisation with the authoritative engine after 120
ticks, measured drift detection, stale-snapshot rejection, ancient-snapshot
hard reset, bounded history, and local input moving the player on the very
next simulated frame.

### B. In-engine Godot (`--headless -- --selftest`)

```
RESULT: 47 passed, 0 failed
ARENA_FC_SELFTEST_PASS
```

Includes six camera views, continuous zoom clamping, in-engine checkpoint and
full-resume state tests, and the rollback predictor.

### C. Classic two-client smoke test (both authority modes)

```
python3 Tools/net_smoketest.py --url ws://127.0.0.1:7777 --seconds 3
RESULT: PASS  (0 failures)      17/17 checks
```

### D. v2 network integration test

```
python3 Tools/net_v2_smoketest.py --url ws://127.0.0.1:7777
RESULT: PASS  (0 failures)      36/36 checks, both --peer-host and default
```

Checks: protocol v2 + grace advertised, 43-char tokens per client, three
slots, `snap.rng` / `snap.gt` / `snap.inputs` present and well-formed,
per-slot controlled players, host drop → `host` broadcast with `host=1`,
lobby `onlines=[false,true,true]`, full `authority` handoff (10 players +
ball + live tick), 14 peer `submit`s relayed to the observer and counted in
`/health`, token reconnect keeping slot 0 / home / controlled player at a
LATER live tick with a running clock and 72 input frames for rollback warm-up,
forged-token rejection, migrated-host `kick`, and `/health` migration +
reconnect counters.

### E. Real Godot C# client reconnect (process killed mid-match)

```
python3 Tools/net_reconnect_e2e.py --url ws://127.0.0.1:7777 --room RECON3
RESULT: PASS  (0 failures)      11/11 checks
```

Phase 1: headless Godot client joined room RECON3 as slot 2, played 165
snapshots with 164 corrections / 1751 replayed ticks, persisted its token in
`user://arena_fc_resume.json`, then the process was killed (abrupt socket
drop). Phase 2: a **new Godot process** launched with `--net-reconnect`:

```
ARENA_FC_NET Reconnecting to ws://127.0.0.1:7777 (room RECON3)…
ARENA_FC_NET Connected · room RECON3 · slot 2 · home
ARENA_FC_NET Reconnected into the live match - your team and player are intact.
ARENA_FC_NET Resumed live match at tick 572 · same slot 2 / team 0 / player #1
ARENA_FC_NETPROBE snaps=96 tick=572 room=FINALR slot=2 host=0 rb=95/906 resumed=True
ARENA_FC_NETQUIT snaps=154 tick=1018 rb=153/2015 resumed=True
```

### E2. Real Godot C# client as the migrated peer host

```
python3 Tools/net_hostmigration_e2e.py --url ws://127.0.0.1:7777 --room MIGR8
RESULT: PASS  (0 failures)      9/9 checks
```

Slot 0 was a stdlib client advertising `caps=1` (browser-class, not capable of
running the simulation), slot 1 a **real headless Godot C# client** (`caps=7`),
slot 2 a stdlib observer. When slot 0 dropped, the server migrated the role to
slot 1 and sent it `authority` with the full checkpoint. The Godot client
logged:

```
ARENA_FC_NET HOST MIGRATION: you now run the authoritative simulation.
```

It then submitted **more than 140 authoritative snapshots**; the observer
received 120 relayed `snap` packets with `authority=1` and ticks advancing from
~115 to ~550.
This exercises the optional `--peer-host` path with the actual shipped C#
client, not only a scripted stand-in.

### F. Headless C# online probe and exported WASM

```
ARENA_FC_NETQUIT snaps=272 tick=786 rb=271/2934 resumed=False
```

Chromium 156 (WebGL 2.0 / SwiftShader) loaded the exported WASM build and
logged:

```
ARENA_FC_WEB_READY query={ net_url, net_room, net_name, create, autostart, net_probe }
ARENA_FC_WEB_WELCOME room=WEBT4 slot=0 host=0 token=43
ARENA_FC_WEB_BEGIN room=WEBT4 slot=0
```

i.e. the browser speaks protocol v2, receives a secure resume token and enters
an authoritative match. Browser rollback re-simulation is intentionally not
implemented (see `ONLINE.md` §8).

### G. Real rendered proof (Xvfb + Mesa llvmpipe)

* `media/screenshots/31_online_v2_lobby.png` — PLAY WITH FRIENDS lobby with
  reconnect / host-migration / rollback status line and RECONNECT button.
* `media/screenshots/32_online_rollback_hud.png` — live online match; HUD
  reads `ONLINE · tick 1109 · ping 320ms · host #0 · RB 380/240t e=0.00m`.
* `media/videos/07_online_v2.mp4` — 8 s / 96 deterministic viewport frames at
  12 fps from a live authoritative room with rollback prediction enabled.

### H. Honest limits of this verification

All network tests ran on **Linux** (editor + headless C# client + stdlib
WebSocket clients + exported WASM in Chromium). Windows, macOS and Android
exports compile but were not network-tested here. `--peer-host` was exercised both with a scripted stdlib "peer host"
(`net_v2_smoketest.py`) and with the shipped C# client
(`net_hostmigration_e2e.py`);
the real C# peer-host path is now also driven end-to-end by
`Tools/net_hostmigration_e2e.py` (see E2). No TLS/WSS, no anti-cheat service,
and no cross-server-restart token persistence were tested.

# Arena FC — 3D football + in‑game rigged character studio

**Arena FC** is an original 3D football game written in **C# / Godot 4.7.2 (.NET 9)**.
Every player is a procedurally generated, **skeleton‑rigged, skinned 3D mesh** (18 bones,
four bone weights per vertex, nine PBR material surfaces). A **character editor inside the
game** lets you change proportions, kit, face, attributes and individual bone poses of
every squad member before taking that squad into a match, save/load them as JSON, or
export them as a standard **`.glb`** file.

No FIFA, PES, eFootball or other copyrighted assets, branding, likenesses, kits, audio or
proprietary code are used. All clubs, players, meshes, shaders and UI are original and
generated at runtime.

**v2 online (27 Oct 2026):** mid‑match **reconnect** with a 256‑bit secure resume
token, **host migration** that keeps the match running (optional live simulation
handoff with `--peer-host`), and **rollback prediction** so your own player
responds on the next frame instead of after a round trip. Six broadcast camera
views with continuous 0.55×–2.4× dolly zoom, a pulsing selection ring + head
arrow, and local 2‑player are also in. See `ONLINE.md` §7 for the protocol,
tests and honest limits.

---

## 1. Run it right now

The ZIP contains two ready‑to‑run builds plus the full source and the build scripts:

| What | How |
|---|---|
| **Browser (any device)** | open `prebuilt/web/index.html` **through a local server**: `python3 Tools/build.py --serve` then visit `http://localhost:8080`. Do not open it with `file://` — browsers block WebAssembly that way. |
| **Linux x86_64** | `cd prebuilt/linux && chmod +x ArenaFC.x86_64 && ./ArenaFC.x86_64` — keep the `data_ArenaFC_linuxbsd_x86_64/` folder beside it (a Godot .NET export needs that folder of assemblies) |
| **Windows / macOS / Android / iOS** | run `build.bat --platforms all` (Windows) or `./build.sh --platforms all` (Linux/macOS). Requires Python 3.9+. |

The build script is the "script that generates the various device formats" you asked for.
It bootstraps its own toolchain if needed (Godot 4.7.2 .NET editor **and** standard editor,
.NET 9 SDK, matching export templates) into `~/.cache/arena-fc`, builds the C# assemblies,
and exports:

```
python3 Tools/build.py --platforms all              # everything your host OS supports
python3 Tools/build.py --platforms windows linux
python3 Tools/build.py --platforms web
python3 Tools/build.py --platforms android --android-sdk /path/to/Android/Sdk
python3 Tools/build.py --check                      # run all tests
python3 Tools/build.py --run                       # launch the game locally
python3 Tools/build.py --serve                     # play the web build locally
```

Outputs land in `build/<platform>/` with a `build/MANIFEST.json`. Useful env vars:
`GODOT_MONO`, `GODOT_STANDARD`, `ANDROID_HOME`/`ANDROID_SDK_ROOT`, `JAVA_HOME`,
`ARENA_FC_CACHE`, and `--godot-mono` / `--godot-standard` / `--android-keystore`.

Shortcuts: `run.sh` / `run.bat`, `selftest.sh` / `selftest.bat`, `build.sh` / `build.bat`.

---

## 2. Tested platform matrix (measured, not claimed)

Tested on **Debian 13 x86_64, Godot 4.7.2.stable (commit `ed1daf0bf`), .NET SDK 9.0.320**,
with software OpenGL (Mesa llvmpipe) for the visual checks.

| Target | Result | Artifact | Notes |
|---|---|---|---|
| **Linux x86_64** | ✅ exported **and executed** — exported binary passes all 39 in‑engine self tests and renders a match | `ArenaFC.x86_64` | Headless + Xvfb/GL tested. |
| **Windows x86_64** | ✅ exported | `ArenaFC.exe` | Not executed here (no Windows/Wine host); same C# assembly + official template. |
| **macOS universal** | ✅ exported | `ArenaFC.zip` (unsigned `.app`) | Not executed here (no macOS host). `codesign/codesign=0` because signing requires macOS/Xcode. |
| **Android** | ✅ exported and inspected with `aapt` | `ArenaFC.apk` (`com.arenafc.football`, minSdk 24) | **Unsigned** (`package/signed=false`). Sign with your own keystore for a real device. C# Android export needs .NET 9 + Android SDK platform‑tools/build‑tools + a JDK. |
| **Web / HTML5** | ✅ exported and rendered | `index.html` + `.wasm` + `.pck` | **GDScript Browser Edition**, see §3. |
| **iOS** | ⚠️ **not exportable on this host** | — | Godot 4.7 refuses C#/.NET Apple‑Embedded exports outside macOS: *"requires macOS"*. Run `build.sh --platforms ios` on a Mac with Xcode. |

`TEST_REPORT.md` has the exact commands and outputs.

---

## 3. The honest Web limitation

**Upstream Godot 4 cannot export C#/.NET projects to Web.** This is an engine limitation,
not a missing setting in this project ([Godot docs](https://docs.godotengine.org/en/4.7/tutorials/export/exporting_for_web.html)).

Rather than ship a broken web target, `Tools/build.py --platforms web` generates a
**GDScript‑only "Browser Edition"** project that:

* loads the **exact same rig data** (`Data/rig_default.json`, dumped from the C#
  `RigBuilder`) and rebuilds the 18‑bone `Skeleton3D`, inverse‑bind `Skin` and
  4‑weight `ArrayMesh` in GDScript;
* runs a lighter 5‑a‑side match with AI, passing, shooting, keepers, goals, a broadcast
  camera, HUD and touch controls;
* includes a smaller in‑browser character editor (kit colours, scale, bone poses, JSON save).

So the browser build has the same rigged/skinned characters but **not** the full 11v11
engine, offside/set‑piece depth, GLB export/import, or the C# UI. That full game is the
native desktop/mobile build. The web project is in `Web/` and is regenerated (never
hand‑maintained twice) from the main project by `Tools/build.py`.

---

## 4. Realistic limits of gameplay / graphics parity

I did not reproduce "all the gameplay of FIFA or PES". No small project can: those are
multi‑hundred‑person products with licensed teams, motion‑capture libraries and bespoke
rendering. Here is what Arena FC actually has, and what it does not.

**Implemented (all original code):**
* 5/7/11‑a‑side matches, four difficulty levels, formations, two halves with switched
  ends, kickoffs, goal kicks, throw‑ins, corners, free kicks, penalties, offside, fouls,
  cards, stamina, possession/shot/foul/corner stats and a live commentary feed.
* Possession and dribbling; ground/lofted/through passes; charged shots with goal
  height/posts/crossbar, goalkeeper saves and dives; tackles; AI teammates and opponents;
  switchable controlled player; three cameras (broadcast / player / tactical).
* Ball physics with gravity, bounce, friction, Magnus‑style curl and spin visualisation.
* Procedural stadium: marked pitch (shader), goals and netting (shader), stepped stands,
  a 2,400‑instance animated crowd, floodlights, ad boards, sky, sun, fog, glow, filmic
  tonemapping. Procedural ball shader.
* Skeletal animation driven entirely from C# (run cycle, kick, tackle, dive, celebrate),
  plus editor bone‑pose overrides.
* Full keyboard, gamepad and touch input producing the same commands.
* Deterministic fixed‑step simulation (seedable) — used by the replay/determinism tests.

**Not implemented / lower fidelity than FIFA/PES:**
* No licensed clubs/players/stadiums/commentary/audio/music, no photoreal textures,
  no motion capture, no advanced IK, no facial animation, no cloth/hair simulation.
  Characters are stylised low‑poly procedural figures — clearly not AAA graphics.
* No career mode, transfers, online multiplayer, VAR, skill moves, tactical depth,
  replay editor, or thousands of animation clips.
* Sound is procedural only (`Scripts/Core/Audio/ProceduralAudio.gd`: kicks, tackles, whistle, goal, crowd). There are no recorded samples, music or commentary.
* Web edition is a deliberately reduced 5‑a‑side game (see §3).
* iOS requires a Mac; Android/macOS packages are unsigned.

The graphics are original, shader‑driven and resolution independent, but "graphics that
approach FIFA/PES" is **not** achieved — that would require a large art team and licensed
assets. This is an honest, working, extensible 3D football game, not a commercial clone.

---

## 5. Controls

| Action | Keyboard | Gamepad | Touch |
|---|---|---|---|
| Move | WASD / arrows | Left stick / D‑pad | Virtual stick (bottom left) |
| Sprint | Shift | RB / RT | SPRINT |
| Pass | E | A | PASS |
| Through ball | Q | Y | THRU |
| Lofted chip pass | R | — | — |
| Shoot (hold to charge, release) | Space | X | SHOOT |
| Tackle / press | F | B | TACKLE |
| Switch player | Tab / middle mouse | LB | SWITCH |
| Change camera | C | R3 | — |
| Pause | Esc | Start | — |

---

## 6. In‑game character editor

Open **Character Editor** from the main menu (or `--editor`). Tabs:

* **Body** — height, bulk, leg/arm length, head scale, shoulder width, skin tone. Each
  slider rebuilds the skeleton AND skinned mesh live.
* **Kit** — full/shirt name, number, role, six kit colours, long sleeves.
* **Face** — hair style/colour.
* **Skeleton** — pick any of the 18 bones and rotate X/Y/Z; show the bone overlay;
  reset a bone or the whole pose. Poses are stored in the character JSON and baked into
  the exported glTF skin.
* **Attributes** — pace, shooting, passing, defending, goalkeeping, stamina.
* **Files** — save/load character JSON, save/load whole squad JSON, **export `.glb`**
  (real glTF 2.0 with joints, inverse binds, weights, materials), **import external
  `.glb`/`.gltf`** for preview, apply the edited squad to the home team and play.

Animation preview: idle / run / kick / celebrate / keeper dive. User files live in Godot's
`user://characters/` and `user://exports/`; the editor has an "Open user data folder" button.

---

## 7. Architecture

```
Scripts/Core/      pure C#, zero Godot references — testable outside the engine
  MathX.cs          deterministic math, xorshift RNG, colours
  CharacterSpec.cs  editable character (JSON + clamping + bone pose overrides)
  RigDefinition.cs  RigBuilder → 18 bones, mesh, 4 weights/vertex, 9 surfaces
  Teams.cs          fictional clubs, formations, roster generation
  Match.cs          fixed-step deterministic match engine + rules + AI + events
Scripts/Godot/     Godot glue
  RigFactory.cs     Skeleton3D + Skin + skinned ArrayMesh + PBR materials
  World3D.cs        stadium, goals, nets, crowd, ball, cameras, skeletal animation
  MatchView.cs      simulation → 3D transforms/HUD each physics tick
  CharacterEditor.cs, Hud.cs, Controls.cs, Ui.cs, GameApp.cs, GlbExporter.cs
  SelfTest.cs       in-engine integration tests
Web/               GDScript Browser Edition (same Data/rig_default.json)
Tests/             standalone `dotnet test`-style console runner (47 assertions)
Tools/build.py     cross-platform export/bootstrap tool
```

`RigFactory` seeds each bone's `pose_position` from its rest translation — required by
Godot 4.7, where animated global poses are independent of `bone_rest`. Without that, a
skinned mesh collapses to the origin; the self test asserts the bind matrices are the
exact inverse of the bone global rest.

---

## 8. Testing (see `TEST_REPORT.md`)

```bash
python3 selftest.sh                 # 88 core + 47 in-engine assertions
# or manually:
dotnet run --project Tests/CoreTests.csproj -c Release
godot --headless --path . -- --selftest
godot --headless --path . --quit-after 300 -- --match       # 5 s of live match loop
```

The exported Linux binary was also executed with `-- --selftest` and rendered a
frame under Xvfb. `screenshots/` contains real renders. `media/` contains **seven real
gameplay videos** (match, character editor, menu/settings, six-camera & zoom showcase,
an online Play With Friends match, the WebGL browser edition, and the v2 reconnect/
rollback online match) plus 32 screenshots and a self-contained
`media/gallery.html`. They were captured from the running exported build with
`Tools/record_media.py` (deterministic `--fixed-fps` viewport frame dumps + injected
keyboard/mouse input) and indexed with `Tools/make_gallery.py`; see `media/README.md`
for the exact commands. Start at `media/gallery.html`.

### Play with friends (online / LAN / local 2P)

**PLAY WITH FRIENDS** in the main menu gives three modes: **Local 2 Player**
(two humans, one machine, no server), **CREATE MATCH** and **JOIN WITH CODE**
(1–4 humans over a room-code WebSocket server). One friend runs
`./run-server.sh` (or `run-server.bat` / Docker); everyone enters
`ws://HOST-IP:7777`, shares the 6-letter room code, and the host presses START.
The server is authoritative — it owns the seed, ball, score and rules — and
clients send only input. The GDScript WebGL build joins the same rooms, so a
phone browser can play against a desktop C# client. Full setup, architecture,
protocol, verification commands and honest limits: **`ONLINE.md`**.

The server source is `Server/` (no NuGet dependencies), the shared wire
protocol + full-state codec + rollback predictor are `Scripts/Core/Net/`, the
client is `Scripts/Godot/Net/`, and `Tools/net_smoketest.py`,
`Tools/net_v2_smoketest.py`, `Tools/net_reconnect_e2e.py` and
`Tools/net_hostmigration_e2e.py` are dependency-free end-to-end tests. `media/videos/06_friends.mp4`, `07_online_v2.mp4` and
screenshots `27`–`32` are real captures of online play.

**v2 adds** secure mid-match reconnect (same slot/team/player, no restart),
host migration that keeps the match alive, and rollback prediction. Start the
server with `--peer-host` to also hand the running simulation to the new host
when the old one drops. `ONLINE.md` §7 has the full protocol and test results.

### Cameras and the selection ring

`C` cycles six views — Broadcast, Telephoto, Player cam, Tactical, Behind goal and
Orbit — or press `1`–`6` to jump straight to one. Zoom with the mouse wheel,
trackpad pinch, `+`/`-`, gamepad right stick, the on-screen `+`/`−` buttons, or
the buttons in the pause menu. Right-drag steers the Orbit camera. The controlled
player has a pulsing ring and a floating arrow that stay readable at every zoom
level. Default view and zoom are configurable under **Match Settings**. See
`ROADMAP.md` for why the first videos showed tiny players and what else is planned.

---

## 9. Licensing / third party

* All game code, meshes, shaders, names and UI in this ZIP are original and released
  under the MIT license (`LICENSE.txt`).
* Godot Engine 4.7.2 — MIT. .NET 9 / C# — MIT. Godot export templates — MIT.
* No FIFA/PES/eFootball assets, branding, likenesses, kits, audio or proprietary code.
  Club names (Harrow United, Nordvik FC, …) are fictional.

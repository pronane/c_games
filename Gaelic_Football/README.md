# Sunday League: Gaelic Football

A C99 Gaelic football prototype with a shared, renderer-independent game core
and two rendering frontends. Gameplay simulation lives in `src/game.c` and
`src/game.h`.

## Presentation and play

- Two full 15-player teams with interim procedural 3D player models, team kits,
  multi-phase running and ball-carrying poses, raised-arm jumps to contest
  high balls, and distinct kick and hand-pass poses. The supplied Gaelic
  football photos inform original silhouettes and actions; player models do
  not reproduce real players, club marks, or sponsor designs. Models include
  individually modeled eyes, irises, pupils, brows, noses, ears, mouths and
  fingers. These procedural models are still placeholders rather than
  realistic rigged footballers.
- A fictional team and player selection screen, plus player switching.
- A stadium bowl with crowd, stands, floodlights, goals, advertising boards,
  textured pitch stripes and a following broadcast camera.
- A high tactical view, adjustable camera angle, match scoreboard, player name
  panels and a pitch minimap.
- Generated crowd ambience, an original chiptune match loop, kick and hand-pass
  effects, whistle and scoring cheers. No external soundtrack or game art is
  required.
- Touch actions for mobile builds; keyboard actions for desktop.

The game uses original generated graphics and audio. The supplied ISS
screenshots inform the 4:3 camera and match-HUD composition, but their artwork,
logos, team identities and music are not reproduced. Team AI, animations,
tackles and match rules remain simplified.

## Rendering modes

- **Enhanced desktop mode (default):** raylib renders a 1920x1080 widescreen
  scene with stadium geometry and a detailed, procedurally generated pitch
  texture, then scales it to the resizable window.
- **Authentic-style desktop mode:** the game renders directly at
  320x240 in a 4:3 broadcast layout, with an adaptive broadcast camera that
  pulls back to track long balls in flight and a closer follow view for local
  play, pitch-side advertising, colored player rings, player-name panels, a
  scoreboard and a centered minimap. The image is point-upscaled to fit the
  window. Press **F2** to switch back to enhanced desktop mode. This mode
  imitates the low-resolution presentation; it is not an emulator.
- **Nintendo 64 ROM:** `src/main_n64.c` is a separate Libdragon frontend. It
  targets the RDP at 320x240, draws flat-shaded projected 3D pitch/player
  geometry, and reads an N64 controller. The common simulation in `src/game.c`
  is used by both frontends; the desktop-only renderer and audio are not linked
  into the ROM.

## Windows build and run

With MSYS2 UCRT64 GCC and raylib installed, run `build_release.bat` from any
terminal directory or double-click it. It builds `gaelic_football.exe` in this
folder and launches the game. Set `RAYLIB_DIR` to raylib's installation prefix
if it is not installed alongside the compiler.

With GNU Make and `pkg-config` available, `make pc` builds the same desktop
frontend without launching it.

## Controls

**Before kickoff**

- Left/right arrows: select the home team.
- A/D: select the away team.
- Up/down or Tab: select your starting player.
- Enter: start the match. On touchscreens, tap a team panel, a position, then
  the bottom strip to start.

**During play**

- W/S: run along the pitch; A/D or left/right: move across it.
- Tab: switch to the home player nearest the ball; Shift+Tab: cycle backwards.
- J: jump to high-field a catch; CPU players will also attempt high fields.
- P: perform a foot pickup on a grounded ball (touchscreen: LIFT). Get close,
  plant the foot against the ball, then scoop it up into your hands.
- Space: standard kick; G: high lob; C: low drive; X: long clearance.
- Hold [ or ] while kicking to curl the ball left or right.
- E: hand pass; Q: solo; R: bounce; F: attempt a tackle when
  within 2.5 m of the opposing ball carrier. CPU defenders also close down
  and can win possession with a committed tackle.
- H or O: open the match rules and options screen.
- V: tactical camera; comma/period: rotate the camera.
- F2: toggle enhanced widescreen and authentic-style 4:3 preview.

The CPU now runs toward the predicted landing point of loose kicks, contests
high balls, closes down and tackles the home carrier, and looks for forward
passes or goal/point shots while in possession. The selected home player can
still be moved manually; press Tab to select the teammate nearest the ball.
AI players perform their own grounded foot pickups; the controlled player must
use P/LIFT, and possession is awarded after the lift animation completes.

The rules screen explains tackles, hand passes, and all four kick types. For a
kick-out, the goalkeeper restarts from the 20-yard line at the middle of the
pitch. The kick must pass the 20-yard arc, and other players are kept outside
the arc until the ball clears it.

When the ball crosses a sideline, the team that did not touch it last gets the
kick-out. When it crosses an endline without scoring, the defending team gets
the restart. The CPU takes its kick-out automatically; for a home-team restart,
move/facing-aim the selected goalkeeper and use one of the kick keys above.

## Nintendo 64 ROM build

Install Libdragon and GNU Make, then build from an MSYS2/Unix-style shell with
`N64_INST` pointing to the SDK installation:

```sh
make N64_INST=/path/to/libdragon
```

This creates `gaelic_football.z64`. The Libdragon SDK is not bundled with the
project. The N64 frontend uses Libdragon's RDP/RDPQ rendering API; it does not
depend on an OpenGL compatibility layer.

On the N64 controller, use the analog stick to move and lean it across the
pitch while kicking to curl the ball. Use A to kick, B to hand pass, Z to
tackle, C-up to solo, C-down to bounce, C-left to jump for a high field,
C-right to foot-pickup a grounded ball, and L/R to change players.

## Portable game core tests

When CMake is installed, configure and test the platform-independent rules
without requiring raylib:

```sh
cmake -S . -B build
cmake --build build --target core_tests
ctest --test-dir build --output-on-failure
```

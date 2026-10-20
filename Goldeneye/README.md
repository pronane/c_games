# Glass Harbor

A first-person spy-action prototype in C99. The game keeps
player coordinates, collision geometry, guard state, health, and mission
objectives in plain C structures in [game.h](./game.h) and [game.c](./game.c).
The frontends are implemented in [main.c](./main.c).

The mission is to recover the data core from a harbor compound and reach the
extraction pad. The PC build uses a first-person 3D view, articulated original
3D guard models, a snowbound industrial compound with a distant mountain
skyline, original weapon sprites and procedural sound effects, aimed fire,
reloads, weapon switching, and an F2 toggle between enhanced widescreen and a
point-filtered 320 x 240 4:3 view. The N64 target runs at 320 x 240 with
controller input and a native low-poly scene.

## Windows PC build

Double-click [build_release.bat](./build_release.bat), or compile from an MSYS2
UCRT64 shell:

```sh
gcc main.c game.c -o MySpy.exe -O2 -std=c99 -Wall -Wextra -DPLATFORM_RAYLIB \
  -IC:/msys64/ucrt64/include -LC:/msys64/ucrt64/lib \
  -lraylib -lopengl32 -lgdi32 -lwinmm
```

Run `MySpy.exe` from the project folder so the files in `assets/` can be found.

## Controls

- `WASD`: move
- Mouse: look; hold the right mouse button to aim
- Left mouse button or `Space`: fire
- `R`: reload
- `Q`: switch between owned weapons
- `E`: pick up the carbine / recover the data core / extract
- `Shift`: sprint
- `F2`: switch between enhanced and 320 x 240 display modes
- `Esc`: quit

N64 controls: analog stick to move, C buttons to look, **A** to fire, **B** to
interact, **L** to aim/reload, **R** to switch weapons, and **Z** to sprint.

Run `python assets/generate_sprites.py` to regenerate the original sprite art
and `python assets/generate_audio.py` to regenerate the original WAV effects.
The game logic tests can be built from an MSYS2 UCRT64 shell with
`gcc game.c tests/game_tests.c -o game_tests.exe -std=c99 -Wall -Wextra -Werror -lm`
and run with `./game_tests.exe`.

## Nintendo 64 ROM

Set `N64_INST` to a Libdragon preview SDK installation with the OpenGL port
enabled, then run:

```sh
make n64
```

The ROM output is `glass_harbor.z64`. A standard Libdragon stable toolchain
without OpenGL support cannot build this 3D frontend.

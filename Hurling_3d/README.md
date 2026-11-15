# Hurling 3D

A playable 3D hurling prototype built with C and raylib. The game uses a 15-player side, a regulation-sized pitch, the supplied rigged hurler/helmet/hurley models, a 7.3 cm sliotar, and hurling-specific striking and scoring.

## Build and run

- Windows/MSYS2 UCRT64: install `mingw-w64-ucrt-x86_64-gcc`, `mingw-w64-ucrt-x86_64-raylib`, and `mingw-w64-ucrt-x86_64-glfw`, then run `build_release.bat`.
- Other platforms: `make`, or `make test` for the rules-engine tests. Set `RAYLIB_DIR` if raylib is not in the compiler's default paths.

## Hurling rules represented

- A goal is 3 points and a point over the crossbar is 1 point. There is no two-point arc.
- A player may carry the sliotar in the hand for at most four steps, then must play it or balance it on the hurley.
- Players can strike the sliotar with the hurley, hand-pass it with a striking action (not throw it), catch it in flight, or lift it from the ground with the hurley.
- A hand-pass can score a point over the bar but cannot score a goal.
- Restarts include puck-outs, frees, sideline cuts, 65-metre frees, and penalties. A puck-out must reach 20 metres before a teammate can play it.
- The team taking a long puck-out may claim a mark on an eligible clean catch.
- Legal defensive actions include a shoulder challenge and hooking/blocking with the hurley; fouls, cards, and penalties are handled by the match engine.
- Every player model includes a helmet with faceguard and a hurley. The sliotar model has a raised seam.

This is a playable simulation, not a certified rules implementation. Competition-specific playing time, substitution, disciplinary, and local-rule variations may differ; the official rule book takes precedence.

## Controls

Move with WASD or the left stick. Sprint with Shift/right trigger. Aim and strike with the strike button; use the pass button for a hand-pass, the lift button to pick the sliotar, and the tackle button to challenge. Press `H` to show the in-game controls.

## Assets and sources

The generated hurler models and animation clips are in `assets/`; regenerate them with `python tools/gen_hurling_assets.py assets --sheet` (requires NumPy and Pillow).

Rules reference: [GAA Official Guide Part 2 — Playing Rules](https://www.gaa.ie/the-gaa/rules-regulations) and the [GAA Coaching & Games Development rules resources](https://learning.gaa.ie/CoachingResources).

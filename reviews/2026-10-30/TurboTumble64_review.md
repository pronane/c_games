# TurboTumble64 — code review

**Scope:** C99 + raylib 5.5 kart racer, 12 source files (~7.5k lines in `src/`), bundled raylib, prebuilt Windows exe, Python photo-to-racer tool.
**Method:** static read of `kart.c`, `race.c`, `characters.c`, `items.c`, `main.c`, `common.h`; compile check of every `.c` file with `gcc -std=c99 -Wall -Wextra -Wshadow` against the bundled raylib 5.5 headers.
**Not done:** I could not build or run the game (raylib's X11/GL development headers are missing in my sandbox). I did not play it, test a gamepad, or run `--autotest`. The only runtime evidence is the author's own `screenshots/autotest_log.txt` (race 1 only: PASS, 8/8 racers finished).

## Summary
Well organised, readable code with a good feature set (drifting and mini-turbos, items, ghost, 6 tracks, data-driven characters). It compiles with only 11 minor warnings. The weak points are robustness of saved files, a variable timestep, and almost no automated testing outside the in-game autotest.

## Findings

| # | Severity | Area | Finding | Suggestion |
|---|---|---|---|---|
| 1 | Medium | Ghost file (`race.c`) | Ghost is a raw `struct` dump (`SaveFileData(..., sizeof(G.ghost))`). Loading checks only file size and a track index read through an `int*` cast. Struct padding, compiler, or any change to `Ghost`/track data silently produces a wrong or misaligned ghost. | Add magic + version + track-geometry hash header; write fields explicitly. |
| 2 | Medium | Save location | Ghosts, settings (`turbotumble64.cfg`) and logs are written next to the exe (`GetApplicationDirectory`). Fails if installed under Program Files. | Use a per-user data directory. |
| 3 | Medium | Timestep (`main.c`) | Game steps use `dt/steps` where `steps = ceil(dt/SIM_DT)`, so each step is up to 1/60 s but varies with refresh rate. Physics uses `Approach`/`LerpAngle` with `dt`, so handling differs slightly between 60 Hz and 144 Hz and replays are not deterministic. Autotest uses a fixed step, so tests do not cover this path. | Fixed-step accumulator (60 Hz) with render interpolation. |
| 4 | Low | Characters (`characters.c`) | `Dup()` strings from `character.ini` are never freed; a repeated key leaks the earlier string. `atof`/`atoi` accept garbage silently. `MAX_CHARACTERS` (32) overflow is skipped without a warning to the user. | Free on replace; validate numbers; log skipped folders. |
| 5 | Low | Compiler warnings | 8x missing initializer for `spriteAngles`/`spriteSize` (`characters.c` 18–25); 3x shadowing of the global `R` and a local `m` (`tracks.c` 728, 913, 920). | Initialise the fields; rename locals. |
| 6 | Low | Dead code | `if (k->human >= 0) yawRate *= 1.0f;`, `(void)oldPos`, redundant `T.loaded = true` inside `if (T.loaded)` (F2 handler). | Remove. |
| 7 | Low | Items (`items.c`) | `rand()` is shared by items, AI and effects, so item rolls are not isolated or reproducible. Projectile pool (64) evicts the oldest; particles beyond 4096 are dropped silently (acceptable, but undocumented). | Use a dedicated seeded RNG per race. |
| 8 | Low | Statistics | `Boost()` increments `statBoosts` on every refresh of an active boost, so boost counts in logs are inflated. | Count only new boosts. |
| 9 | Info | AI | Rubber-banding scales CPU speed by up to about +13% (factor 1 − 0.085·clamp(diff/0.14) plus 0.05 when far behind, times skill 0.955–1.0). In the author's log the autopilot "player" finished 8th, so the autotest checks that races complete, not that AI is competitive. | Add AI-quality assertions if balance matters. |
| 10 | Info | Testing/CI | No unit tests and no CI. `--autotest` needs a GL window. No Makefile/CMake for Linux/macOS; build docs target MSYS2. | Add CMake + a headless logic test target. |
| 11 | Info | Repo hygiene | A prebuilt exe and a full raylib copy are committed; `.gitignore` does not exclude them. | Release binaries separately. |

## Positives
- Clear module split; physics, AI, items and rendering are separate files.
- Autotest harness with screenshots and a pass/fail log is unusually thorough for a hobby game.
- Data-driven characters (`character.ini` + sprite) and a photo pipeline.
- Ghost capped and validated at load (count, character id range).

## Suggested priorities
1. Versioned ghost/settings files in a user data folder (#1, #2).
2. Fixed timestep (#3).
3. Fix warnings and leaks (#4–#6), add CMake build.

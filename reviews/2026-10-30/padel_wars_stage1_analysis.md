# Padel Wars Stage 1 (deterministic sim) — independent check

Checked: `padel_wars_stage1.zip` + the report text, against the original `egyptian_fighter/` from `c_games-main.zip`.

## Verified by me
- **Patch applies cleanly** to the original `egyptian_fighter/` (`git apply --check` and apply both succeed; only a harmless executable-bit warning on `build.sh`).
- **Shipped files match the patch**: every changed/new file in the zip is identical to the patched tree (I compared `src/*.c|h`, `build.sh`, `build_release.bat`, `README.md`, `ONLINE_PLAN.md`, `.gitignore`). The five files not in the zip (`demo.c`, `gfx.c/h`, `pad.c/h`) are unchanged by the patch.
- **Compiles**: all `.c` files pass `gcc -std=c99 -fsyntax-only -Wall -Wextra` with raylib 5.5 headers; the only warning is the pre-existing unused `dt` in `UpdatePhysics` (`player.c`), as the report says.
- **Sim path is free of obvious nondeterminism**: `Game_SimTick` takes inputs only from the 16-bit mask; remaining `GetFrameTime`, `IsKey*` and `GetTime()` calls are in the menu/frame code. The clock-based seed (`game.c:222`) is only used when `EF_SEED` is not set. The RNG (`rng.h`, xorshift32 + splitmix seeding) uses unsigned integer math only, so it is portable.

## NOT verified by me
- I could **not link or run** anything (no raylib headless backend and no X11/GL dev headers here). So I did not reproduce `--sim-test`, the hashes (`952e5c07…`, `5c9a84ca…`, `c5342812…`, `0ce736c9…`), the frame-by-frame comparisons, or the replay results. Those are the other run's measurements; treat them as reported, not independently confirmed.
- Windows build, MSVC, clang and wasm are untested (the report says so too).

## Egyptian Fighter bugs from my earlier review: still present (by design)
Stage 1 keeps behaviour identical, so these carried over unchanged:
1. **Block exploit** — melee is cancelled by the held block flag alone (`game.c` ~499/503: `!p2->inputBlock`), not by being in the block state, grounded and facing.
2. **Arrow keys drive both fighters** in 1P vs 2P (`input.c` lines ~8–9 for P1 and ~25–26 for P2).
3. **Double KO** gives P2 the win (P1 is checked first, `game.c` ~509/515). A timeout draw works.
4. The frame-rate dependence from my review **is fixed** by the 1/60 s tick and accumulator.

## Recommendations before Stage 2 (netcode)
1. **Fix 1–3 now, before online play.** Any gameplay change alters the hashes and invalidates recorded `.efrec` files, so do it once, deliberately, and re-baseline the four hashes. Add a **sim version number** to the replay header and config hash so old recordings are rejected cleanly.
2. **Run `--sim-test` on Windows** (and in CI on Linux and Windows) and compare the four final hashes. This is the single most important unproven step for cross-play.
3. **Floats remain.** `-ffp-contract=off` and the same compiler give matching results on x86-64 gcc, but MSVC/clang/wasm may differ. Convert position, velocity and timers to integers or fixed-point before relying on peer-to-peer lockstep, as the report's README section lists.
4. **Config hash includes loaded sprite sizes**, so a GPU with a smaller max texture size will refuse to match. That is safe, but make the error message clear to players.
5. **Seeding for online:** the host must choose the seed and send it; never use the clock seed in a networked match.
6. Add a tiny CI script: build, `--sim-test`, `--replay` a committed short recording.

## Ready-to-paste prompt for your running session
> Read `padel_wars_stage1_analysis.md`. Before starting Stage 2: (a) fix the three carried-over bugs — blocking must require being grounded in the block state facing the attacker (throws bypass block), the arrow keys must not drive P1 when P2 is human, and a double KO must be a draw; (b) add a sim version number to the replay header and config hash; (c) re-run `--sim-test`, update the expected hashes, and note in the commit message that recordings from before this change are invalid; (d) add a CI job that runs `--sim-test` on Linux and Windows.

# Padel Wars - Stage 1 (deterministic sim) - report (as supplied, summarised)

Finished Fri 30 Oct 2026 ~20:15 London. Built in a local scratch clone (branch `padel-wars-deterministic`), never pushed.
Base: `egyptian_fighter/` at 38c4712 (identical at main HEAD ce1f135).

## Local commits (each compiles with gcc -Wall -Wextra)
| Commit | Milestone |
|---|---|
| ec0b16f | M1: 16-bit input mask + sampling layer (`input.c`) |
| 6283b6b | M2: fixed 1/60 s tick (`Game_SimTick`) + accumulator; pause/F11 never step the sim |
| 9d4354e | M3: seeded xorshift32 PRNG (`rng.h`) replaces `GetRandomValue` in the CPU AI |
| e324da4 | M4+M5: `Sim_Hash`, `--sim-test`, `--record`/`--replay`, `Sim_ConfigHash` |
| 2645d08 | M6: floats kept, `-ffp-contract=off`; README determinism notes; `ONLINE_PLAN.md` |

## Tests
1. `--sim-test` (headless): PASS.
   - 4 scripted fights, each with: run1 == run2; 1 tick per frame == 3 ticks per frame; random 0-4 ticks per frame with pauses gives the same result.
   - Sensitivity checks catch a flipped input and a changed seed. Record/replay round trip passes. Accumulator checks pass.
   - Hashes are identical at -O0/-O2/-O3 -march=native:
     - MIKE/DARAGH `952e5c07fabfc1b7`
     - DEC/DRAGON `5c9a84cad2dd45d3`
     - RA/FLAME `c5342812f2a56f7c`
     - time-out `0ce736c967cd17ac`
2. Behaviour and visuals unchanged versus the original under Xvfb.
   - 4 scenarios, per-frame state traces identical, screenshots pixel-identical (10/10, 10/10, 14/14, 27/27).
   - `--demo 2/5/6` identical.
3. Fights recorded in the GUI replay headless: PASS (91/67/62/207 checks).
4. `build.sh` on Linux with raylib 5.5: PASS.

## Not run / limits
- No Windows build: `build_release.bat` was edited but not run. Run it, then `--sim-test`; the hashes should match the ones above.
- Tested only with gcc on x86-64 Linux (not MSVC, clang or wasm).
- Timers are still floats (1/60 per tick). README lists the fields to make fixed-point before Windows-vs-browser cross-play.
- Different max texture sizes give a different config hash, by design, so a mismatch is detected rather than causing a desync.
- Cross-machine agreement needs Stage 2+ (netcode) plus the Windows `--sim-test`.

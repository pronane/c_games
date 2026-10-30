# Padel Wars - Stage 1 (deterministic sim) - changed files

Base: `pronane/c_games` main, `egyptian_fighter/` as of commit 38c4712 (PR #4, Padel Wars v4).
main HEAD ce1f135 only changed deploy.yml, so the folder is the same. Nothing was pushed to GitHub.

## How to drop it in

Option A - copy files: unzip, then copy the contents of this zip's `egyptian_fighter/` folder over
your `c_games/egyptian_fighter/` folder (overwrite when asked). No files are deleted, only added or changed.

Option B - patch: from the root of the `c_games` repo run
`git apply padel_wars_stage1.patch` (check it first with `git apply --check padel_wars_stage1.patch`).

Then build as usual: `./build.sh` (MSYS2 UCRT64 or Linux) or `build_release.bat` (Windows).
Both already list the two new files `src/input.c` and `src/sim.c`; if you use another build
(IDE project, CI), add those two files and the flag `-ffp-contract=off`.

## Files

New:
- `src/input.h`, `src/input.c` - 16-bit per-player input mask; the only place keyboard/pads are read for the fight
- `src/rng.h` - seeded xorshift32 PRNG (replaces GetRandomValue in the CPU AI)
- `src/sim.h`, `src/sim.c` - sim hash, config hash, tick accumulator, `--sim-test`, `--record`/`--replay`
- `ONLINE_PLAN.md` - the online plan with Stage 1 status

Changed:
- `src/game.c`, `src/game.h` - fight logic moved into `Game_SimTick` (one fixed 1/60 s tick, reads only input bits); seeded RNG in the Game state
- `src/player.c`, `src/player.h` - timers use the fixed tick; headless (no-GPU) sprite loading for tests
- `src/main.c` - fixed-step accumulator loop; new command-line options
- `src/common.h` - tick constants
- `build.sh`, `build_release.bat` - add input.c, sim.c and `-ffp-contract=off`
- `README.md` - new "Determinism" section (incl. where fixed-point will be needed)
- `.gitignore` - ignore `*.efrec` recordings

## New command-line options (run from the egyptian_fighter folder)

    bin/egyptian_fighter --sim-test            # headless; prints PASS/FAIL (exit code 0 = pass)
    bin/egyptian_fighter --record fight.efrec  # play normally, every fight is recorded
    bin/egyptian_fighter --replay fight.efrec  # headless re-simulation, checks every hash
    EF_SEED=1234 bin/egyptian_fighter          # fixed CPU random seed

Gameplay, controls and visuals are unchanged (verified frame by frame, see the report).

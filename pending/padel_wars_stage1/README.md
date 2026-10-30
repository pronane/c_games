# Parked: Padel Wars Stage 1 (deterministic sim) for egyptian_fighter

**Applied** (31 Oct 2026) to `egyptian_fighter/` on branch `claude/sprite-forge-recommendations-pt2ip4`, as the base for the online mode.
The earlier online changes were removed first, Stage 1 was applied to main's files, and online.c was rebuilt on `Game_SimTick` / `Sim_Hash`.
`--sim-test` passes with the same four final hashes as the report. This folder is kept as the record of the original upload.

- `padel_wars_stage1.zip`: the original upload (changed and new files plus the patch)
- `padel_wars_stage1.patch`: `git diff` against `main`, 16 files, +1089 / -179
- `README_STAGE1_CHANGES.md`: file list and drop-in steps
- `REPORT.md`: the Stage 1 test report

## Status, checked 30 Oct 2026
- `git apply --check` **passes on `origin/main`** (ce1f135).
- It does **not** apply on branch `claude/sprite-forge-recommendations-pt2ip4`. That branch's commit
  93382ea added an ONLINE mode to egyptian_fighter (`online.c`, `Game_FightStep`, `Game_Hash`) and touched
  the same files: game.c/h, main.c, player.c, build.sh, build_release.bat. Stage 1 overlaps that work
  (fixed tick, input bits, seeded RNG, sim hash). When it's applied, either apply it to main and rebuild
  the online layer on its `Game_SimTick` / `Sim_Hash`, or drop the branch's egyptian_fighter changes first.
- Still to do, from the report: run `build_release.bat` and `--sim-test` once on Windows and compare
  the hashes.

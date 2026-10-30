# Review status: what has been done (branch `claude/sprite-forge-recommendations-pt2ip4`, 31 Oct 2026)

These are the reviews in this folder (from the review conversation's handover), each finding checked against the branch.
**Done** = changed and tested here (Linux x86-64, gcc, raylib 5.5 under Xvfb). **Partly** / **Not done** say why.

## Egyptian Fighter (`EgyptianFighter_review.md`, `padel_wars_stage1_analysis.md`)

| # | Finding | Status |
|---|---|---|
| 1 | Block exploit (held button cancels melee; throws blockable) | **Done.** A block needs `STATE_BLOCK`, on the ground, facing the attack (`Blocks()` in game.c), for melee and projectiles. Throws can't be blocked. `--sim-test` "combat rules" checks it. |
| 2 | Frame-rate dependence | **Done** by Stage 1 (fixed 1/60 s `Game_SimTick` + accumulator). |
| 3 | Arrow keys drive both fighters in 1P vs 2P | **Done.** P1 uses `Input_KeysP1Only()` (WASD) when P2 is human; the README table is corrected. |
| 4 | Double KO gives P2 the win | **Done.** It's a draw. Melee hits are now decided for both fighters before either is applied, so a simultaneous exchange trades instead of P1 always winning it. Tested. |
| 5 | Same move data for every fighter, no combos | Not done. This is a design change (per-character data table), so it needs your choices. |
| 6 | CPU reads attacks perfectly, no difficulty | Not done. Design. |
| 7 | README out of date | **Partly.** Keyboard table fixed; the `char1`/`char2` description isn't rewritten yet. |
| 8 | Real names / in-jokes before public release | Your call. Not changed. |
| 9 | No automated tests / CI | **Done.** Stage 1's `--sim-test` + `.github/workflows/sim-test.yml` (see below). |
| S1 (a) | Fix the 3 carried-over bugs before Stage 2 | **Done** (rows 1, 3, 4). |
| S1 (b) | Sim version in the replay header + config hash | **Done.** `SIM_VERSION 2` (common.h) is in `RulesHash` and the `EFREC 2 sim 2` header. Old `EFREC 1` files are rejected with a clear message. |
| S1 (c) | Re-run `--sim-test`, update the expected hashes, note that recordings are invalid | **Done.** Expected hashes are now compiled into `--sim-test` and checked: `b5ff8d84…`, `eb5ca790…` (changed: the CPU blocks under the new rule), `c5342812…`, `0ce736c9…` (unchanged). The README and the commit message say old recordings are invalid. Passes at -O0 and -O2. |
| S1 (d) | CI on Linux and Windows | **Written, not yet run.** `sim-test.yml` builds and runs `--sim-test` on ubuntu-latest and windows-latest (MSYS2 UCRT64), then diffs the two platforms' hashes. It runs on the next push to GitHub; check the Actions tab. |
| S1 rec 3 | Floats remain; convert to fixed-point before cross-platform play | Not done. A big change, and only needed for Windows-vs-browser. The CI diff will show whether Windows and Linux already agree. |
| S1 rec 4 | Clear message when the config hash differs | **Partly.** Online, a config mismatch shows up as "Desync at frame 30" (the config hash is folded into every checkpoint). There's no dedicated "your game data differs" message yet. |
| S1 rec 5 | Seed comes from the host online | **Done.** The server sends the seed (`countdown`/`go`); online never uses the clock seed. |

## TurboTumble64 (`TurboTumble64_review.md`)

| # | Finding | Status |
|---|---|---|
| 1 | Ghost file is a raw struct dump | **Done.** v2 format: "TTGH" magic, version, track, track-layout hash, then fields written one by one (race.c). v1 files still load. Round trip, wrong-layout rejection and legacy load were tested with a throwaway harness. |
| 2 | Files saved next to the exe | Not done. Moving save files would orphan existing settings and ghosts; it needs a migration step. Documented in the README for now. |
| 3 | Variable timestep | **Partly.** Online races run at a fixed `SIM_DT`. Offline play still uses the old sub-stepping, because a fixed step without render interpolation would judder on 144 Hz screens. |
| 4 | `Dup()` leaks, silent skips | **Done** for the leak and the 32-racer limit warning. `atof` validation isn't done (values are already clamped). |
| 5 | Compiler warnings | **Done.** 0 warnings with `-Wall -Wextra -Wshadow`. |
| 6 | Dead code | **Done** (`yawRate *= 1.0f`, redundant `T.loaded = true`). `(void)oldPos` was left alone: it only silences an unused variable. |
| 7 | Shared `rand()` | **Done** in the first commit: a seeded `SimRand` for the race, `VisRandF` for visuals only. |
| 8 | `statBoosts` inflated | **Done.** It counts only new boosts. |
| 9–11 | AI assertions, CMake/CI, committed binaries | Not done. The CI workflow compile-checks TurboTumble64 on Windows; there's no CMake yet. |

## Sprite Forge (`SpriteForge_review.md`)

| Item | Status |
|---|---|
| v9.1 patch (`--puppet-engine skin`, `--motion-style polish`) | **Applied** (`sforge/skinwarp.py`, `sforge/motionpolish.py`, forge.py, build.py), byte-identical to the patch. Defaults unchanged. No new dependencies (scipy was already required). |
| Regression | `tools/test_v9.py` 44/44 and `tools/test_v8.py` 6/6 pass here with the patch. `test_v7` not run. |
| Next step 1: try skin on real photos / cartoon art | **Blocked** here too: needs the pose model (`tools/setup_pose.py`, network) and a real photo. Commands are in the README "New in v9.1" section. |
| Next step 5: skin engine in `test_v9.py` | Not done. |
| Next step 6: document `tools/setup_pose.py` in the quick start | **Done** (README Install + v9.1 section). |
| Next steps 2–4 (2x upscale, foot-lock for photo builds, judge polish by eye) | Not done. They need visual judgement on real input. |

## Arena FC (`ArenaFC_review.md`)

No code changed yet. I installed .NET 9 SDK 9.0.320 (Microsoft's `dotnet-install.sh`) and Godot 4.7.2 .NET (the official release
zip) in the session container and actually built and ran the project, in a scratch copy:

| What | Result |
|---|---|
| Godot game project (`ArenaFC.csproj`), `dotnet build` | **Builds**, 0 warnings |
| In-engine self-test (`godot --headless --rendering-driver dummy -- --selftest`) | **39 passed, 0 failed**. Godot prints RID leak messages at exit with the dummy renderer; they aren't test failures. |
| Server (`Server/ArenaFC.Server.csproj`) | **Does not compile.** (1) `Program.cs:507` uses `$$"..."` (raw-string syntax) on a normal string: error CS9004. A one-character fix. (2) The `ArenaFC.Core.Net` namespace (`NetProtocol`, referenced 147 times) **isn't in the repo**: `Scripts/Core/Net/` holds only two `.gd` files. The C# networking sources were never committed. |
| Core tests (`Tests/CoreTests.csproj`) | **Do not compile** for the same missing `ArenaFC.Core.Net` reason, so the 66 core tests can't run from the repo. |

So review findings #1–#5 (the WebSocket server) can't be fixed or tested until the missing `Scripts/Core/Net/*.cs` files are added.
`Tests/obj` is committed and gets rewritten by every build (review #11).

## Online play (from the first request)

HD Fighter's relay is now `shared/netplay/server` (HD tests pass unchanged on it). There's a C client in
`shared/netplay/c`, an online mode in Egyptian Fighter (on Stage 1, sim version 2) and ONLINE VS in
TurboTumble64. Re-tested after the changes above with two game windows each: TurboTumble64 agreed at
tick 1800, and Egyptian Fighter at tick 1500. One Egyptian Fighter window exited early once, while four
game windows were sharing one software-rendered display; it passed when re-run on its own, and the cause
wasn't captured.

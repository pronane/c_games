# Master Hypermotion/AME + Football Intelligence Validation Status

Branch: `arena/8459237b-c-games`  
PR: https://github.com/pronane/c_games/pull/271 (do-not-merge)  
Status date: 2026-11-25 (sandbox evidence; visual/runtime Godot checks are limited)

## CI / automated evidence

- `9649645`: all green (dotnet-core, godot-gdscript, godot-selftest, node-hub, sim-compare/linux/windows, netplay, GitGuardian).
- `ee65ca6`: all observed checks green; netplay was pending in one snapshot but had passed on adjacent heads.
- `8e01729`: all green (dotnet-core, godot-gdscript, godot-selftest, node-hub, sim-compare/linux/windows, netplay, GitGuardian).
- `1132e04`: dotnet-core failed on M6 manifest test (`soccer_sidestep` locomotion clip has zero root velocity; 94/95). Fixed in follow-up by relaxing test tolerance.
- `73e641b`: doc-only head; inherited `1132e04` dotnet-core failure (other checks green).
- `76825fc`: M6 test tolerance fix; CI green (Arena FC tests pass, netplay/determinism pass).
- `c83e932`: M3 close-presser invariant; CI green (Arena FC tests pass, netplay/determinism pass).
- `4827746`: BallFocus parity fallback + M3/M6 schema tests; CI green (Arena FC tests pass, netplay/determinism pass).
- `b327a06`: intercept contracts, M3 per-player flap test, sandbox validation procedure; CI green (Arena FC tests pass, netplay/determinism pass).

Automated checks in CI include: manifest version sanity, `bake_clip_manifest_v2.py --check`, Godot C# build, server build, full `Tests/CoreTests.csproj` suite, netplay/determinism, sim compare, Godot selftest/GDScript tests.

## Milestone status

| Milestone | Status | Evidence | Remaining gaps / sandbox limits |
|---|---|---|---|
| M1 Shared authoritative ball physics + prediction parity | Partial | `BallTrajectory.Step` used by `Match.BallPhysics`; parity test in `MatchCoreTests`; `Match.BallPred(horizonSeconds)` per-tick cache; `MatchAerial.BallFocus` uses `BallPred` (including non-skill high-ball fallback end sample); direct `BallTrajectory.Predict` in `Match.cs` limited to tactical 0.8s build and `BallPred`. | Full audit of all prediction/physics consumers for parity; explicit sim-vs-prediction scenario coverage; evaluate `LandingPoint` analytical fallback (skill mode/fallback) against parity goals; collision/claim/intercept parity evidence. |
| M2 PlayerPerception with real capabilities, no duplicate evals | Partial | `PlayerPerception` pure C#; `LaneSafety` has per-opponent speed/accel overload; pass/loose-ball intercept use real capabilities; `ClosestToBall` intercept scoring uses `p.MaxSpeed` and accel from Pace/Defending. | Audit remaining decision paths for hardcoded capability/duplicate ball-eval logic; add perception scenario tests; document capability-plumbed callers. |
| M3 TacticalCoordinator sole authority | Partial | `TacticalCoordinator` uses predicted ball, real capabilities, hysteresis, role targets, `ClearState`; Decide consumes coordinator press/cover/support/recover with limited shape-preserving blends; `PrimaryChaser` routes chaser ranks through coordinator roles; tackle aggression fallback uses `PrimaryChaser`; M3 tests cover unique assignments, <=1 press/cover per OOP team, no conflicting hard pressers, bounded role changes, no conflicting close AI pressers, sane coordinator movement targets, and bounded per-player role flap. | `ClosestToBall` remains fallback when coordinator role absent; stronger no-conflicting-chaser proof across all engagement/chase paths; support-destination quality/stability scenario evidence; calibration-safe removal of remaining independent chase decisions. |
| M4 PlayerActionContract authoritative end-to-end | Partial | `PopulateBaselineContracts()` emits carry/receive baselines; `RecordActionContract` enriched; `SetAction` supports intent override and emits pass/shoot/clear intents; MatchView/MotionDriver consume contracts; M4 tests validate keys/finite fields, baseline carrier/receive, action intents, pass/shoot and tackle observation. | Full major action-state coverage (dribble/intercept/claim transitions as applicable); MotionEngine/SoccerClipRig deeper contract consumption; action-trace validation across broader action set; runtime visual evidence (Godot sandbox-blocked). |
| M5 Inertialization/grounding/pelvis/plant curves | Partial | Velocity-aware inertialization in SoccerClipRig; continuous plant weights drive pelvis stabilization and IK lock weighting with residual-motion damping. | Broader inertialization chain coverage; ground-normal validation; pelvis residual correction validation; continuous plant-curve end-to-end/contact timing/transition validation. Requires Godot runtime/visual evidence outside sandbox. |
| M6 Root velocity/provenance/validation, AME preserved | Partial | Manifest bake `--check` passes; clips include `source`/`provenance`; in-place GLB locomotion/dribble/carry/GK clips get metadata-speed facing-local root-velocity fallback when sampled hips velocity is zero; M6 C# test validates provenance/source and locomotion nonzero root velocity. | Confirm metadata fallback is accepted provenance contract for in-place GLB clips; deterministic bake evidence across environments; stronger schema/provenance validation; AME motion-matching functional validation. Runtime/visual evidence sandbox-blocked. |
| M7 Full validation/evidence/docs | Not done | CI green on recent heads; netplay passing; determinism/sim compare jobs present. | Full scenario coverage, full-match tactical/ball-physics/animation regression evidence, performance measurement, before/after visual evidence, PR/docs completion. |

## Sandbox-blocked evidence / manual validation procedure

The sandbox has no `dotnet`/Godot runtime for local execution; visual animation validation, performance profiling, and before/after capture cannot be completed here. CI provides build/test/netplay/sim-compare evidence.

### Commands (Godot-capable environment)

```bash
# From arena-fc/
python3 Tools/bake_clip_manifest_v2.py --check Data/clips/clip_manifest.json Data/models/soccer_player.glb
dotnet build ArenaFC.sln -c Release
dotnet run --project Tests/CoreTests.csproj -c Release
# Run determinism/netplay suite as in CI (arena-fc-tests.yml).
```

### Visual / runtime checklist (capture before/after artifacts for PR)

- **M4 contracts:** enable debug overlay; verify carry/receive/pass/shoot/clear/tackle/intercept states select contract-driven animations; confirm MatchView/MotionDriver/MotionEngine consume contract intent/target/facing/timing without sim desync.
- **M5 grounding/inertialization:** verify foot plant/IK lock on continuous plant curves, no slide-back on jog/run/stop/turn, facing alignment, pelvis stabilization/residual correction, inertialized transitions on stop/turn/kick/receive/tackle.
- **M6 AME/provenance:** verify motion-matching selects expected locomotion clips with meaningful root velocity; confirm bake provenance (`source`/`provenance`) is acceptable for in-place GLB clips; capture motion-matching debug overlay.
- **Performance:** record frame time / sim tick budget in representative 11v11 match; compare before/after if baseline available.
- **Artifacts:** attach screenshots/video clips, debug-overlay captures, and perf numbers to PR description or `arena-fc/Docs/` evidence folder.

## Known risks / non-complete items

- `ClosestToBall` remains as fallback; coordinator is not yet proven sole authority over every chase/engagement path.
- `LandingPoint` analytical fallback remains for skill mode/fallback; parity with `BallTrajectory` should be explicitly evaluated.
- M4 contract consumption is present in MatchView/MotionDriver, but MotionEngine/SoccerClipRig deeper end-to-end contract-driven behavior needs validation.
- M6 locomotion root velocity uses metadata-speed fallback for in-place GLB clips; this is practical for motion-matching features but should be reviewed as provenance contract.
- No merge to main; PR remains do-not-merge until DoD evidence is complete.

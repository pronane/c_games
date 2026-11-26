# Milestone 4 - Validation & Tuning (Arena FC)

## Environment limitation
This sandbox does not have Godot/.NET runtime installed, so before/after gameplay
capture and real-clip metric measurement must be run in a Godot-enabled environment.
The instrumentation/hooks are in place; this document gives the commands to run.

## Seeded telemetry comparison (headless, deterministic)
Run CoreTests/MatchCoreTests:

```bash
cd arena-fc
dotnet test Tests/MatchCoreTests.csproj -c Release
dotnet run --project Tests/CoreTests.csproj -c Release
```

The MatchCoreTests include seeded regression checks for:
- ball trajectory determinism/intercepts
- coordinator role stability (bounded flips over N ticks)
- tactical telemetry counters (`TacticalRoleChanges`, press/cover assignments)
- action contract contact timing
- predicted intercept decision behavior
- blocked-lane avoidance

## Godot runtime capture (before/after)
Run in a machine with Godot 4.7+ and the project imported:

```bash
cd arena-fc
# Enable debug overlay for animation/contact signals
ARENA_FC_DEBUG_OVERLAY=1 godot --path . --scene res://Scenes/Match.tscn
```

Capture before/after by recording the same seed/scenario:
- Use the same `MatchOptions.Seed`, team, formation, and camera.
- Record video and the debug overlay (approach weight, TTC, contact window).
- Save screenshots/video to `arena-fc/Docs/captures/<date>/`.

## Real-clip metric measurement
AnimationMetrics hooks are wired in `MotionEngine` and `SoccerClipRig`:
- foot sliding: `AnimationMetrics.AvgFootSlide` (m/s while planted foot moves)
- contact-frame error: `AnimationMetrics.AvgContactFrameError` (normalized phase error at contact-timed transitions)
- transition discontinuity: `AnimationMetrics.AvgTransitionDiscontinuity` (hook; extend with pose delta in Godot)

To capture in Godot, add a temporary debug print in MatchView/World3D:

```csharp
GD.Print($"AnimMetrics samples={_motion.Metrics.Samples} slide={_motion.Metrics.AvgFootSlide:F3} contactErr={_motion.Metrics.AvgContactFrameError:F3} trans={_motion.Metrics.AvgTransitionDiscontinuity:F3}");
```

## Tuning targets
- Reduce foot sliding during planted phases and sharp direction changes.
- Keep contact-frame error small for pass/shoot/tackle/receive contracts.
- Avoid transition discontinuities on clip switches; prefer foot-event-aligned transitions.
- Preserve sim/online determinism: no visual fix may alter authoritative state.

## Contract field consumption audit (2026-11-26)

| Field | Populated by sim | Consumed by MotionDriver | Consumed by SoccerClipRig | Notes |
|---|---:|---:|---:|---|
| Intent | Yes | Yes | No (via motion state) | Core action selection driver. |
| HasTarget / TargetPosition | Yes | Yes | No | `HasTarget` replaces zero-vector sentinel. |
| FacingDirection | Yes | Yes | No | Overrides yaw when valid. |
| BallContactTime | Yes (remaining s, -1 N/A) | Yes (untilContact) | No | Aligned to MotionDriver remaining-time semantics. |
| DesiredSpeed / SpeedLimit | Yes | Yes | No | Speed hint clamped by SpeedLimit. |
| DesiredTurnRate | Yes (heuristic) | Yes (turn clamp) | No | Heuristic; presentation-only clamp. |
| ShouldSprint | Yes | Yes (Move->Sprint hint) | No | Presentation-only. |
| Pressing | Yes | No | No | Populated; presentation/diagnostic currently. |
| Role | Yes | No | No | Populated; presentation/diagnostic currently. |
| RequiresFootPlant | Yes | No | No | Populated; rig/plant-window integration pending. |
| RequiresBallContact | Yes | No | No | Populated; test/audit invariant. |
| BallContactPosition | Yes | No | No | Populated; presentation/diagnostic. |

SoccerClipRig currently receives motion state, not raw action contracts. Any new contract-field consumption must remain presentation-only and must not alter authoritative match state.

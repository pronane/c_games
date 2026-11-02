# Screen recording analysis — "the gameplay doesn't work"

Recording: `02.11.2026_21.46.12_REC.mp4` (from `main/arena-fc`), 55.60 s, 1280×740,
25 fps, H.264 + AAC. Branch: `arena/abfd2149-c-games`.

## 1. What is actually on screen

This is **the native C# desktop build**, not the Web/WASM preview I fixed in PR #36.
Evidence in the frames: a native window titled "Arena FC"; the HUD hint
`WASD move · SHIFT sprint · E pass · Q through · SPACE shoot (hold) · F tackle · TAB switch · C camera · ESC pause`
is verbatim `Scripts/Godot/Hud.cs`; the green camera label cycles `Player cam` / `Broadcast`,
which are the three `BroadcastCamera.ModeName` strings in `Scripts/Godot/World3D.cs`.
So the browser-edition fixes (canvas focus, `Web/BrowserBoot.gd` pad menu/camera) do
**not** touch the build in this recording.

The game is running and rendering correctly: 22 rigged players with kits, ball, stadium,
floodlights, minimap, commentary feed, power/stamina bars, and the teal controlled-player
ring. The long black shapes near players are their (harsh) directional shadows, not missing
meshes. The ball is visible at players' feet. Rigs are **not** the problem here.

## 2. What is broken (frame-by-frame evidence)

| Time | Observation |
| --- | --- |
| 0 s | "Player cam" label. Four players bunched in the centre circle around the ball; commentary `FLETCHER wins the ball! / DUARTE wins the ball! / COSTA → MENDES`. Stats: `Poss 50%-50%, Shots 1-0, Fouls 0-0, Corners 0-0`. |
| 2–16 s | Same scrum reforms repeatedly. Players never break away with the ball. `MARINHO wins the ball!`, `MENDES → FLETCHER` repeat. |
| 19–20 s | Camera cycles to a near-vertical "tactical" view: the whole pitch plus a large grey stadium stand wedge at the bottom. |
| 20 s | Feed: `MARINO wins the ball! / MENDES → FLETCHER / MENDES → FLETCHER`. Stats still `Shots 1-0`. |
| 25–39 s | Repeated `Red free kick / MENDES → FLETCHER` cycles; single player standing over a stationary ball, then another scrum. |
| 43–47 s | Orange shot-power bar fills (SPACE held) but no shot is ever registered. |
| 48 s | Tactical camera again, with the same stand wedge. |
| 55 s | Final stats `Poss 49%-51%, Shots 1-0, Fouls 2-2, Corners 0-0`. |

**One shot in 55 seconds, zero corners, and an endless "X wins the ball!" loop.** The
controlled player spends most of the clip stuck in a 3–5 player scrum near the centre
circle. That is the "gameplay doesn't work" — not a rendering or input-focus issue.

## 3. Root cause — `Scripts/Core/Match.cs`

`PossessionLock` has one meaning everywhere else in the engine: *"this player may not pick
the ball up again for a short time"*. `TryPossession()` and `AttemptTackle()` both set it
to `.12f` when a player **gains** possession; `PassTo()` / `Shoot()` set it on the kicker.

But `Tick()` used it on the **owner** as a release condition:

```csharp
if (owner.PossessionLock > 0 || Mx.FlatDist(owner.Pos, S.Ball.Pos) > 2.2f)
    S.Ball.Owner = -1;
```

So every pickup or tackle lost the ball on the very next 1/60 s tick. `BallPhysics()`
then made it loose, `TryPossession()` gave it to someone else (another "wins the ball!"
line), and the cycle repeated roughly 11× per second. Nobody could dribble, nobody
reached the penalty area, and the AI almost never got into its shot range. Pressing
SPACE normally does nothing anyway unless your exact controlled player owns the ball —
hence the power bar filling with no shot.

## 4. Fixes in this branch

| File | Change |
| --- | --- |
| `Scripts/Core/Match.cs` | Owner release condition now only uses the distance guard; `PossessionLock` is left to mean "cannot pick up again". Added explanatory comment. |
| `Scripts/Godot/MatchView.cs` | WASD is rotated into camera space (`Cam.GlobalTransform.Basis`), so W is always "up the screen" in broadcast / player / tactical views instead of a fixed world -Z. |
| `Scripts/Godot/World3D.cs` | Player cam: fallback facing when a stationary player has zero facing (prevents a degenerate overhead `LookAt`). Tactical: straight-down at 62 m with `-Z` as the up vector so the pitch fills the frame, the stands don't intrude, and the view cannot spin; faster camera lerp. |
| `Scripts/Godot/GameApp.cs` | First menu Button calls `GrabFocus()`, so arrow keys / Enter and a mapped gamepad d-pad can actually drive the desktop main menu. |
| `Scripts/Godot/Hud.cs` | Hint now mentions `C / pad R3 camera`. |
| `Tests/MatchCoreTests.cs` + `.csproj` | New self-contained .NET 9 regression suite for the pure match core (does not need the missing `Scripts/Core/Net/*.cs`). |
| `Tests/Program.cs` | Same possession checks added to the main suite for when the net sources are restored. |
| `Tools/test_pads.py` | +6 static guards (91 checks total). |
| `.github/workflows/arena-fc-tests.yml` | New `dotnet-core` job: builds `ArenaFC.sln` with .NET 9, runs `MatchCoreTests.csproj` and `Tools/test_pads.py`. Previously **no CI job compiled any C#**, which is why this bug shipped. |

## 5. Verification — real C# engine, A/B

I compiled the actual `Match.cs` (plus `MathX.cs`, `Teams.cs`, `CharacterSpec.cs`) with
Roslyn and ran a deterministic 60 s / 11v11 simulation (seed 2026, `TimeSpeed=15`,
3600 ticks), once with the buggy line and once with the fix:

| Metric (60 s real = 15 game minutes) | Before | After |
| --- | --- | --- |
| Ball ownership changes | **653** | **33** |
| Longest continuous possession | 376 ticks | **602 ticks** |
| `wins the ball!` events | 5 | 7 |
| Passes | 10 | 8 |
| Goals | **0** | **2** |
| Loose ball collected then held for 30 ticks | **4/30** | **30/30** |

`Tests/MatchCoreTests.cs` on the same engine: **5 passed / 0 failed** with the fix,
**2 passed / 3 failed** with the buggy line restored (the three failing checks are
the owner-flip storm, no goals, and the 4/30 possession drop).

Other checks run here:
* `python3 Tools/test_pads.py` → **91 passed, 0 failed** (with gdtoolkit + tree-sitter parsers).
* tree-sitter C# parse: all changed C# files clean; `gdparse` clean on the GDScript files.
* `Tests/MatchCoreTests.csproj` and workflow YAML parse cleanly.

## 6. Limits / what I could not check

* I watched the video as extracted still frames (1 fps and 2 fps grids plus full-resolution
  crops of the HUD, commentary feed and players). I cannot play it in real time, and the
  AAC track contains no intelligible speech — an offline speech recogniser returned only
  noise/silence. If you narrated the problem, please type the key points.
* I did **not** rebuild the native Windows game here (no .NET 9 SDK / Godot editor in this
  sandbox). CI now compiles the C# assemblies; your `D:\c_games` still needs `git pull`,
  a native rebuild and a new recording to confirm the feel.
* The exact camera *aesthetics* (shadow harshness, player-cam distance, name-label
  overlap) are visible in the recording but I only fixed the degenerate tactical view,
  zero-facing spin and camera-relative movement. Tell me if you want the camera tuned
  further.

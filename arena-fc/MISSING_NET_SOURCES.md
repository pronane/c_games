# Networking sources — rebuilt (option 2)

> **Status: resolved.** The first-party C# net layer that was never committed has
> been rewritten from the wire format that *is* checked in. `local_changes`, all
> 36 remote branches, GitHub code search, commit-path history and the compiled
> `CoreTests.dll` were searched previously: none of them contained these files,
> so there was nothing to restore. This document now records what was rebuilt,
> which checked-in definition each part came from, and what was verified.

## Why the build was broken

`Server/ArenaFC.Server.csproj` and `Tests/CoreTests.csproj` both compile
`../Scripts/Core/**/*.cs`. `Scripts/Core/Net/` only held `ReplayPlayer.gd` and
`ReplayRecorder.gd` (GDScript, ignored by the C# compiler), so neither project
could type-check. Online play was therefore impossible on the desktop C# build
regardless of hosting choice.

## The format definitions used (all checked in)

| Definition | What it fixed |
| --- | --- |
| `Web/NetClient.gd` | message names (`hello`, `welcome`, `lobby`, `begin`, `resume`, `snap`, `host`, `ping`/`pong`, `chat`, `end`, `error`, `input`, `start`, `ready`, `kick`), `ver`/`caps`/`create`/`token`, URL normalisation, slot/team/host/grace/size fields |
| `Web/BrowserBoot.gd` (`net_apply_snapshots`) | snapshot player keys `x,z,vx,vz,fx,fz,a`, ball `x,y,z,vx,vy,vz,owner`, `score`, `clock`, `phase`, `half`, `ctrls`, `ev`, `com` |
| `ONLINE.md` §4/§7 | input-only authority, 60 Hz sim / 20 Hz snapshots, 100–120 ms interpolation, message DTOs live in `Scripts/Core/Net/`, replay + state hashing |
| `Tools/net_smoketest.py` | `hello`/`welcome`/`lobby`/`start`/`input`/`snap`/`chat`, `/health`, identical shared-tick world state, `size`, `ctrls`, `tick` |
| `Tools/net_v2_smoketest.py` | `rng`, `gt`, `inputs[{t,c}]`, `full{tick,rng,players,ball,clock}`, `submit`, `authority`, `host`, `kickSlot`, 43-char bearer token, reconnect into the same slot/team/player |
| `Tools/net_reconnect_e2e.py`, `net_hostmigration_e2e.py` | token handling and host-migration expectations |
| `shared/netplay/server/arena/*.js` | independent Node reference server: deterministic tick, snapshot cadence, room codes, kick/migration semantics |
| `Server/*.cs` and `Tests/Program.cs` | the exact member surface the missing types had to expose |

## What was written

| File | Purpose |
| --- | --- |
| `Scripts/Core/Net/NetProtocol.cs` | v2 constants, message names, capability/authority bits, `Encode`/`Decode` (explicit JSON names, null fields omitted), room/name/URL/token helpers, FNV-1a state hash |
| `Scripts/Core/Net/Packet.cs` | `CommandDto` (1/256-quantised `mx,my,sp,pa,sh,ch,th,ta,sw,lo,sl,sd`), `PlayerDto`, `BallDto`, `InputFrameDto`, `FullPlayerDto`, `FullBallDto`, `FullStateDto`, `Packet` |
| `Scripts/Core/Net/Snapshot.cs` | 20 Hz `snap` build + `ApplyImmediate` / `ApplyInterpolated` (100 ms behind) |
| `Scripts/Core/Net/StateCodec.cs` | full-fidelity `resume` / peer-host checkpoint, wire hash helpers |
| `Scripts/Core/Net/Replay.cs` | compact 60 Hz input log, `ToJson`/`FromJson`/`CreateEngine`/`Play` |
| `Scripts/Core/Net/RollbackPredictor.cs` | zero-RTT local prediction, bounded re-simulation, stale/ancient snapshot handling |
| `Scripts/Core/Net/OnlineClient.cs` | Godot-free C# WebSocket client (`INetTransport`, `WebSocketTransport`, `LoopbackTransport`), handshake/state machine, ping-pong, `Poll()` |
| `Scripts/Core/Net/OnlineMatch.cs` | desktop match driver: sends only input, predicts, mirrors snapshots, reconciles |
| `Scripts/Core/Match.Network.cs` | `MatchEngine` partial: `StepNetwork`, `StepOneTick`, `CurrentTick`, `FindNearestForTeam`, `Capture`/`Restore`, `ApplyFull`, `EngineCheckpoint` |
| `Scripts/Core/Match.cs` | `MatchEngine` is `partial`; `Tick` accepts per-player network commands; `ControlledAway` |
| `Scripts/Core/MathX.cs` | `Rng.State` get/set so the deterministic stream is one checkpoint word |
| `Scripts/Godot/GameApp.cs` | **PLAY WITH FRIENDS** lobby: server URL / room / name, CREATE / JOIN / READY / START, live status, resume token |
| `Scripts/Godot/MatchView.cs` | optional `OnlineMatch` driver; renders the predicted engine, sends local input each physics tick |
| `Tests/Program.cs` | +23 checks for the desktop online client and the rollback loopback driver |
| `Tests/MatchCoreTests.csproj` | now compiles `Match.Network.cs` alongside `Match.cs` |

Two latent compile errors in the checked-in sources were fixed along the way:
`Tests/Program.cs` declared `int o` inside a loop and `var o` at top level
(CS0136), and `Server/Program.cs` had a malformed raw-string literal `$$"…"`
(CS9004) in the `/` status page.

## Verification (local, .NET 9 language level via Roslyn WASM)

* `Tests/Program.cs` — **148 passed, 0 failed** (rig, rosters, RNG, match,
  possession, replay, protocol, snapshots, interpolation, checkpoints,
  full-state handoff, secure tokens, rollback, **online client + online match**,
  pad support). The shipped `gamecontrollerdb.txt` was staged into the WASM VFS
  for the sandbox run only.
* `Tests/MatchCoreTests.cs` — **15 passed, 0 failed**.
* `Server/*.cs` + all `Scripts/Core/**/*.cs` — compiles clean; `SERVER_COMPILE_OK`.
  (The server binary itself cannot bind sockets inside a WASM sandbox, so the
  executable was replaced with a compile-only harness for that check.)
* `ArenaFC.sln` / `Server/ArenaFC.Server.csproj` / `Tests/CoreTests.csproj` are
  exercised by the `dotnet-core` CI job on .NET 9.

Still environment-dependent: a real `net_smoketest.py` /
`net_v2_smoketest.py` run needs a native `dotnet` host, which this sandbox does
not have. The Node reference server (`shared/netplay/server/arena/standalone.js`)
speaks the same format and remains the CI-tested end-to-end check.

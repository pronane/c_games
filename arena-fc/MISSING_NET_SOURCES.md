# Missing networking sources

`Server/ArenaFC.Server.csproj` compiles `../Scripts/Core/**/*.cs`, but `Scripts/Core/Net/` contains only
the two GDScript replay files. The C# the server and `Tests/Program.cs` depend on is not in the
repository, and git history shows it was never committed. `RENDER_REUSE_ANALYSIS.md` already lists
"missing `Scripts/Core/Net/`, `Scripts/Godot/Net/`, `build/web/`" as the first thing to restore.

Until those files are back, `dotnet build Server/ArenaFC.Server.csproj` cannot succeed, so online play
cannot run regardless of the hosting choice.

## What the committed code expects (found by searching the C# that is here)

| Type | Members used by `Server/*.cs` and `Tests/Program.cs` |
| --- | --- |
| `NetProtocol` | `Version`, `DefaultPort`, `SnapshotHz`, `MaxPlayersPerRoom`, `MaxRollbackTicks`, `ReconnectGraceSeconds`; message names `Hello Welcome Lobby Ready Start Begin Input PeerInput Snap Resume Host Authority End Error Chat Ping Pong Leave Kick Hash Submit`; capability/authority values `CapFullDesktop CapPeerHost Authority AuthorityPeer AuthorityServer`; helpers `Encode Decode NewRoomCode NewResumeToken HashToken TokenHashEquals NormalizeName NormalizeRoom NormalizeUrl` |
| `Packet` | fields `Authority Ball Clock Com Ctrls Full Half Host Inputs Name Names Phase Pings Players Room Score Slot Team` |
| `Snapshot` | `Build`, `ApplyImmediate`, `ApplyInterpolated` |
| `StateCodec` | `BuildFull`, `ApplyFull` |
| `PlayerDto`, `BallDto` | `From(...)` |
| `Scripts/Godot/Net/` | the desktop client side (lobby UI, connection) |

The wire format the browser client speaks is defined by `Web/NetClient.gd` and `ONLINE.md`, and the
snapshot fields the browser reads are in `BrowserBoot.net_apply_snapshots` (`players[{x,z,vx,vz,fx,fz,a}]`,
`ball`, `score`, `clock`, `ctrls`, `ev`). Those can guide a rewrite, but the original files are the right
thing to restore if you still have them (an older checkout or the "stale ZIPs" mentioned in the analysis).

# Online play: how coordinates are shared, and what to add next

Date: 2026-11-03. Written after the "how will online play work?" follow-up.
Companion to `ONLINE.md` (protocol details) and `MISSING_NET_SOURCES.md` (what is absent).

## Short answer

**Clients never send each other positions.** Every client sends only its *intent* (stick direction
and button edges) to one authoritative server. The server runs the deterministic match simulation at
60 Hz, then broadcasts a **snapshot** of the whole pitch (player coordinates, ball, score, clock,
phase, events) 20 times a second. Everyone renders the same snapshot, so everyone sees the same
coordinates by construction.

```
  You (pad/keyboard)                     Server                         Other player(s)
  ── input 30 Hz ────────────────────▶  ┌──────────────────┐  ── snap 20 Hz ──▶ renders
   {mx,my,sp,pa,sh,th,ta,sw,lo,ch}      │ match engine 60Hz │  ◀── input 30 Hz ──
  ◀── snapshot 20 Hz ─────────────────  │ seed + RNG + log  │
      renders 100 ms behind, lerps       └──────────────────┘
```

Transport is **WebSocket + UTF-8 JSON** (`ws://`, `wss://` behind a proxy) because browsers cannot
open raw UDP sockets. There is no ENet/NuGet dependency.

## The coordinate system on the pitch

| Axis | Meaning | Range |
| --- | --- | --- |
| `X` | pitch length, home attacks `+X` in the first half | −52.5 … +52.5 m |
| `Y` | height above the turf | 0 … ~25 m (ball) |
| `Z` | pitch width | −34 … +34 m |

The origin is the centre spot. Goals sit at `X = ±52.5`, `|Z| < 3.66 m`, height 2.44 m.
`SideSign(team)` flips the attacking direction at half time, so a snapshot is always in the same
world frame — clients do not need to mirror anything themselves.

## Exactly what goes over the wire

**Client → server (30 Hz, `input`):**

```json
{"t":"input","seq":42,"room":"ABC123","cmd":{
  "mx":0.375,"my":-0.625,"sp":true,"pa":false,"sh":true,
  "th":false,"ta":false,"sw":false,"lo":false,"ch":0.8125}}
```

Stick values are quantised (`CommandDto.From/To`, 1/256 steps) so the same input produces the same
floating-point result on every machine. No `x`/`z` is ever sent by a client.

**Server → clients (20 Hz, `snap`):**

```json
{"t":"snap","tick":240,"clock":12.4,"score":[0,0],"phase":1,"half":1,
 "ball":{"x":1.34,"y":0.11,"z":-9.26,"vx":2.1,"vy":0,"vz":-0.4,"owner":7},
 "players":[{"x":-14.7,"z":-19.0,"vx":1.2,"vz":0.3,"fx":0.9,"fz":0.2,"a":"run"}, …],
 "ctrls":[7,18,-1,-1],"ev":["MENDES → FLETCHER"],"rng":"…","gt":4.0,
 "pings":[12,30,-1,-1]}
```

`players[]` is in a **fixed index order** (team 0 slots 0..N-1, then team 1), so player 7 means the
same person in every client. `x/z` are positions, `vx/vz` velocity (for interpolation/extrapolation),
`fx/fz` facing, `a` animation action. The ball carries `x/y/z` plus velocity and `owner` (the index of
the player whose foot it is glued to, or −1 when loose). Discrete state — score, clock, phase,
commentary, events, controlled-player indices — comes from the newest frame, not from interpolation.

**Rendering:** each client keeps a mirror `MatchEngine` and draws 100–120 ms behind the newest
snapshot, linearly interpolating between the two nearest frames. That hides the 20 Hz tick rate and
network jitter. Your own input is predicted locally (C# desktop/mobile rollback) so it feels
immediate; the server later confirms or corrects it. The HUD shows the correction distance `e=…m`.

**Why this is cheat-resistant:** a modified client can lie about its stick but cannot move the ball,
teleport a player or change the score — the server owns the seed, the RNG, the rules and the ball.
`NetProtocol.Hash(state)` (FNV-style mix of all player `x/z`, ball `xyz`, score) lets the server and
clients detect divergence; `Replay.Play()` reproduces the exact final state from `seed + inputs`.

**Rooms & resilience:** room code → lobby → begin → input/snap → end. v2 adds secure resume tokens,
mid-match reconnect (180 s reservation), host migration (`--peer-host`) and rollback prediction.

## What actually works today (honest status)

| Path | Status |
| --- | --- |
| Node hub `shared/netplay/server/arena/{sim,server,standalone}.js` | **Complete and CI-tested** (`npm test`, `net_smoketest.py`, `net_v2_smoketest.py`, two-client e2e). Owns a deterministic 60 Hz sim and emits the snapshot above. |
| GDScript Browser Edition (`Web/NetClient.gd` → `BrowserBoot.net_apply_snapshots`) | **Works** against the Node hub: reconnect, host-migration notices, snapshot interpolation. No rollback. |
| C# desktop/mobile client + .NET server | **Restored (option-2 rewrite).** `Scripts/Core/Net/*.cs` (protocol, DTOs, snapshots, state codec, replay, rollback, `OnlineClient` / `OnlineMatch`) and the desktop **PLAY WITH FRIENDS** lobby in `Scripts/Godot/GameApp.cs` were rebuilt from the checked-in wire format — see `MISSING_NET_SOURCES.md`. `Tests/Program.cs` is 148/0, `Tests/MatchCoreTests.cs` 15/0, and the server sources compile. A native `.NET 9` host is still needed to run the server binary and the Python WebSocket smoke tests. |

So to play online right now: run the Node server and open the browser edition; the
desktop C# client is now built against the same protocol and joins those rooms.

```sh
cd shared/netplay/server
node arena/standalone.js --port 7777
# in the browser build: Play With Friends → ws://<host>:7777 → create/join a room code
```

Desktop online play was restored by rewriting those sources from the wire format above;
`Tools/build.py --check` and the `dotnet-core` CI job now build/run them.

## What else can be added (prioritised)

1. **Native .NET 9 end-to-end run** — start `Server/ArenaFC.Server.csproj` on a machine with the
   SDK and run `Tools/net_smoketest.py`, `net_v2_smoketest.py` and the reconnect / host-migration
   e2e suites against it. The sandbox has no native `dotnet`, so those remain unverified here.
2. **Matchmaking / room browser / accounts** — currently room codes only; add a lobby list, skill
   rating, persistent resume tokens and a friends list.
3. **NAT traversal / WebRTC data channels** — remove the need to port-forward; keep the server as
   arbiter but relay less. Browser clients already speak WebRTC-friendly transports.
4. **Spectator mode & replay sharing** — the server already writes replay JSON at full time; add a
   spectator slot, a timeline scrubber and shareable match links.
5. **Set-piece / referee polish** — visible referee, cards shown on screen, advantage rule, VAR-style
   replays; the foul/stumble poses added this round are the groundwork.
6. **Better AI personalities** — per-club tactics (pressing intensity, defensive line, tempo), so
   "World class" differs by more than a tackle probability.
7. **Graphics** — port the new joint/toe geometry into `Tools/gen_rig.py` so the browser mesh matches
   the desktop rig, add kit patterns/numbers, crowd animation and ball trails.
8. **Accessibility & UX** — remappable keyboard, colour-blind kits, larger HUD, controller glyphs
   that match the detected pad layout (standard vs raw), and an on-screen pad test in CONTROLLER SETUP.
9. **Anti-cheat / input validation** — rate-limit and sanity-check input magnitudes on the server.

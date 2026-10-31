# Arena FC online on Node (no .NET)

The C# server cannot be built from this repository (`Scripts/Core/Net/*.cs` are missing, see
`MISSING_NET_SOURCES.md`), so online play now has a second, self-contained server written in Node. It lives in
the shared hub (`shared/netplay/server/arena/`) and is switched on with **`ARENA_NATIVE=1`**.

```
browser --https--> shared Node hub --(in process)--> arena/server.js  (rooms, lobby, authoritative match)
                     /arena/        static web build
                     /arena/ws      WebSocket (protocol v2, the same one NetClient.gd speaks)
                     /arena/api/health
```

| File | What it is |
| --- | --- |
| `arena/rules.js` | Pure rules: keeper reading, save odds, shot error, lane-aware passing, posts and bar, restarts, fouls. A port of `Web/MatchRules.gd`. |
| `arena/sim.js` | The 5-a-side match at 60 Hz, a port of the browser edition's offline sim (AI, keeper saves, throw-ins/corners/goal kicks, fouls, halves). Deterministic for a given seed and inputs. |
| `arena/server.js` | Rooms, lobby, ready/start, resume tokens (SHA-256 stored, constant-time compare), 180 s reconnect grace, host migration, kick, chat, ping, per-IP and flood limits, Origin allow-list, `/health`. |
| `arena/standalone.js` | Runs the server alone (`node arena/standalone.js --port 7777`), same `/health` as the .NET server. |

## Run it

```
cd shared/netplay/server && npm install
ARENA_NATIVE=1 ARENA_WEB_DIR=../../../arena-fc/build/web node hub.js     # http://localhost:3000/arena/
# or only the game server, for any client:
node arena/standalone.js --port 7777
```

Deploy with `arena-fc/option-a/Dockerfile` (or `render.yaml`): one Node service, no .NET. Set
`TRUST_PROXY=1` behind a proxy and `ARENA_ALLOWED_ORIGINS` to your site's origin. In the game, **PLAY WITH
FRIENDS** with the default address `./ws` and everything works from the page URL.

Options (`standalone.js`, and `createArenaServer({...})`): `--half-minutes` (45), `--time-speed` (15 game
seconds per second, so a match is about 6 minutes), `--grace-seconds` (180), `--seed`.

## How it was checked

* `node test_arena.js`: 50 checks on the rules, determinism (same seed and inputs give the same state),
  keeper stops some shots but not all, restarts, full time, and the wire protocol (lobby, start, snapshots,
  chat, token resume, host migration, kick, forged token, flood and per-IP limits, health).
* `node test_hub_arena_native.js`: the hub routes `/arena/ws` and `/arena/api/health` and the fighters still work.
* The existing protocol suites written for the .NET server pass unchanged against this one:
  `Tools/net_smoketest.py` (17/17) and `Tools/net_v2_smoketest.py` (all checks), run with
  `node arena/standalone.js --port 7791` and `--url ws://127.0.0.1:7791`.
* A real headless Godot browser client (`BrowserMain.tscn --net-url ...`) connected, started a match and
  received about 120 snapshots in 9 seconds.

## What it is not

* **Not the C# match.** `Scripts/Core/Match.cs` (11-a-side engine, the desktop game) is not ported. Online
  matches are the browser edition's 5-a-side game, so desktop C# clients cannot join this server and
  browser players cannot join a C# server's rooms.
* **No peer-host handoff and no client rollback.** The server is always the authority. Snapshots carry
  `rng`, `gt` and the trailing input log so the fields exist, but the browser client does not predict: it
  interpolates 20 Hz snapshots, so you will feel your own latency.
* **Up to 4 humans** (2 per side); AI fills the rest. Browsers only, 5-a-side only.
* Not load-tested beyond the unit and protocol checks: a few hundred concurrent rooms is untested.

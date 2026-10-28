# Arena FC — Play With Friends

**This is working online multiplayer, not a design sketch.** A friend hosts a
room, everyone else joins with a 6-letter code, and an authoritative server
runs the deterministic match. Desktop (C#), the Web/WebGL build and any
WebSocket client can be in the same room.

> **v2 (27 October 2026)** adds the three features most requested after the
> first release: **mid-match reconnect**, **host migration** and **rollback
> prediction**. See [§7](#7-v2--reconnect--host-migration--rollback). Protocol
> version is now **2**; v1 clients still work (they simply do not use the new
> features).

Three ways to play, all in the game's **PLAY WITH FRIENDS** screen:

| Mode | Server needed | Players | Best for |
| --- | --- | --- | --- |
| **Local 2 Player** | No | 2, one machine | Couch play / same keyboard + gamepad |
| **LAN / direct join** | Yes (one friend runs `run-server.sh`) | 1–4 | House, office, same Wi-Fi |
| **Internet** | Yes (VPS / port forward / Docker) | 1–4 | Friends in different places |

---

## 1. Quick start (LAN, ~60 seconds)

1. **One friend** runs the server on their machine:

   ```bash
   ./run-server.sh                 # Linux/macOS  (needs .NET 9 SDK or runtime)
   run-server.bat                  # Windows
   # or:  python3 Tools/build.py --check   bootstraps a local SDK if needed
   ```

   It prints `ws://0.0.0.0:7777`. Open `http://127.0.0.1:7777/` to see the
   status page and `http://127.0.0.1:7777/health` for JSON.

2. **Everyone** finds that machine's LAN IP (`192.168.x.x`, `10.x.x.x`) and in
   the game goes **PLAY WITH FRIENDS → server address** =
   `ws://192.168.1.20:7777`, enters a name.

3. **Host** clicks **CREATE MATCH** (optionally types a custom 3–12 character
   room code first) and shares the displayed **ROOM CODE** (there is a COPY
   button). Everyone else types that code and clicks **JOIN WITH CODE**.

4. **Host** clicks **START MATCH**. Play. Up to 4 humans (2v2 co-op), AI fills
   the rest of each 5-a-side team. The HUD shows
   `ONLINE · tick N · ping Nms · host #N · RB corrections/replayedTicks`.
   If you lose your connection the game reconnects automatically with your
   team and controlled player intact — or press **RECONNECT** / **RECONNECT
   TO LAST MATCH** (browser) from the lobby.

---

## 2. Playing over the internet

The server is a single small .NET 9 console app with **no external packages,
no database and no third-party service**. Put it anywhere your friends can
reach:

**Option A — home port forward.** Run `run-server.sh` and forward TCP 7777 on
your router to that machine. Friends use `ws://YOUR-PUBLIC-IP:7777`. (UPnP is
not automated yet.)

**Option B — cheap VPS / Raspberry Pi / free tier.**

```bash
git clone <your repo> && cd arena-fc
docker build -f Dockerfile -t arenafc-server .
docker run -d --name arenafc -p 7777:7777 --restart unless-stopped arenafc-server
# or without Docker:
dotnet run --project Server/ArenaFC.Server.csproj -c Release -- --port 7777 --bind 0.0.0.0
```

**Option C — HTTPS/WSS via reverse proxy.** The server speaks plain `ws://`
(and plain HTTP for `/health`). Browsers on an `https://` page cannot open an
insecure `ws://` socket, so if you host the web build over HTTPS, terminate TLS
with nginx/Caddy and proxy WebSocket upgrades to port 7777. Example Caddyfile:

```
arena.example.com {
    reverse_proxy 127.0.0.1:8080          # static web build (Tools/serve_web.py)
}
ws.arena.example.com {
    reverse_proxy 127.0.0.1:7777          # Upgrade header forwarded automatically
}
```

Then friends use `wss://ws.arena.example.com`.

**Shareable join links (browser build).** Append a query string to the web
build URL and the game connects and opens the lobby automatically:

```
https://arena.example.com/?net_url=wss%3A%2F%2Fws.arena.example.com&net_room=ABC123&net_name=Sam&create=0
```

`create=1` makes that link create the room (host), `autostart=1` starts the
match 3 seconds after connecting (useful for kiosk/demo setups).

> **Security:** there is no authentication, rate limiting or TLS in the server
> itself. It is intended for private rooms among friends. Do not expose it to
> the open internet without a reverse proxy, a firewall allowlist and WSS.

---

## 3. Controls

**Player 1 (home):** WASD / arrows, Shift sprint, E pass, Q through ball,
R chip, Space hold-then-release shoot, F tackle, Tab switch, C / 1–6 cameras,
mouse wheel or `+`/`-` zoom, Esc pause. Gamepad 0 works too.

**Player 2 (away, local 2-player only):** IJKL move, T sprint, U pass,
O through, H tackle, N shoot (hold), Y switch, M chip. Gamepad 1 works too.
Each player has a ring (green = P1, amber = P2) and their own shot-power bar.

**Online:** each client uses the Player 1 controls; the server assigns your
team and controlled player. Your ring is green, the visible opponent's ring is
amber. Touch controls and the browser build use the on-screen buttons.

---

## 4. How it works

```
  ┌────────────┐   input 30 Hz    ┌───────────────────────────┐
  │ C# desktop │ ───────────────▶ │  ArenaFC.Server (.NET 9)  │
  │ C# mobile  │ ◀─────────────── │  · room codes / lobby     │
  │ GDScript   │  snapshots 20 Hz │  · authoritative Match    │
  │ WebGL/WASM │                  │    Engine at 60 Hz        │
  └────────────┘      WebSocket   │  · chat / ping / replays  │
                                  └───────────────────────────┘
```

* **Transport:** RFC 6455 WebSocket, UTF-8 JSON messages (`ws://` or `wss://`
  behind a proxy). No ENet — browsers cannot open raw UDP sockets. The server
  implements the handshake and framing itself in `Server/WebSocketServer.cs`,
  so there are no NuGet dependencies.
* **Authority:** clients send **only input** (`mx,my,sp,pa,sh,th,ta,sw,lo,ch`).
  The server owns the seed, rules, score, ball and RNG, calls
  `MatchEngine.StepNetwork()` at 60 Hz and broadcasts state. A modified client
  cannot move the ball or change the score.
* **Rendering:** clients keep a mirror `MatchEngine` and render 100–120 ms
  behind the newest snapshot with linear interpolation between frames
  (`OnlineDriver.cs`). Discrete state (score, clock, phase, commentary, events,
  controlled-player indices) comes from the newest frame.
* **Determinism:** `Scripts/Core/Match.cs` is pure C# with a seeded RNG. The
  server records `seed + team size + input log` to
  `Server/bin/Release/net9.0/replays/ROOM-timestamp.json` at full time;
  `Replay.Play()` reproduces the exact final state (covered by unit tests).
* **Rooms:** `hello` (optionally `create=true` with a custom code) → `welcome`
  → `lobby` → `begin` → `input`/`snap` → `end` → back to `lobby` for a rematch.
  `ping`/`pong` measures RTT; `chat` relays lobby messages. Protocol version
  is checked on connect; mismatches get a clear error.

Message DTOs, quantization, snapshot build/apply, state hashing and replay
live in `Scripts/Core/Net/NetProtocol.cs` — Godot-free, so they are unit
tested by `Tests/CoreTests.csproj` and shared by the server and both clients.

---

## 5. Server options

```
dotnet run --project Server/ArenaFC.Server.csproj -c Release -- [options]

  --port N           WebSocket + HTTP port          (default 7777)
  --bind ADDR        0.0.0.0 default; 127.0.0.1 for local-only
  --team-size N      5, 7 or 11 per side           (default 5)
  --seed N           deterministic match seed      (default 2026)
  --half-minutes N   game minutes per half         (default 45)
  --time-speed N     game seconds / real second    (default 15)
  --difficulty N     0 easy .. 3 legendary         (default 1)
  --snap-hz N        snapshots / second            (default 20)
  --tick-hz N        simulation ticks / second     (default 60)
  --max-rooms N      room cap                      (default 200)
  --grace-seconds N  reconnect slot reservation    (default 180, 5..3600)
  --peer-host        on host loss, HAND the live simulation to the new host
                     client (server relays). Default: server stays authority.
  --verbose          log joins and match events
```

`/health` returns JSON: `ok`, `protocol`, `rooms`, `players`, `peerHost`,
`reconnectGraceSeconds`, `migrations`, `reconnects`, `submits` and
`matches[]` with room code, online players, reservations, host, authority,
started flag, tick and score. `/` is a live HTML status page (auto-refresh 5 s).

---

## 6. Verification (what was actually run)

```bash
python3 Tools/build.py --check
#   RESULT: 66 passed, 0 failed         (pure-C# core + protocol + replay)
#   RESULT: 55 passed, 0 failed         (in-engine Godot, incl. net drivers)

./run-server.sh 7777                    # in another terminal
python3 Tools/net_smoketest.py --url ws://127.0.0.1:7777 --seconds 5
#   17 checks: room code, join, lobby, start, identical snapshots, chat, /health

# Two real headless Godot clients against the same server:
godot --headless --path . -- --netprobe --url ws://127.0.0.1:7777 \
      --room TEST77 --name A --host --seconds 14
godot --headless --path . -- --netprobe --url ws://127.0.0.1:7777 \
      --room TEST77 --name B --seconds 13
#   ARENA_FC_NETPROBE ok=True snaps=268 lastTick=779 slot=0 room=TEST77 ping=12
#   ARENA_FC_NETPROBE ok=True snaps=261 lastTick=759 slot=1 room=TEST77 ping=12

# The GDScript browser project against a C# desktop guest:
godot_std --headless --path build/web_src -- --net-url ws://127.0.0.1:7777 \
      --net-room WEB8Y --net-host --net-autostart --net-probe-seconds 14
#   ARENA_FC_WEB_NETPROBE snaps=218 tick=631 room=WEB8Y slot=0 mode=true
```

Also verified with the **exported Linux binary** (two instances, 228/227
snapshots), and with the **exported WebAssembly build in Chromium** playing a
real match against a desktop host (browser received 218 snapshots; host
received 435 in 22 s). See `media/videos/06_friends.mp4` and
`media/screenshots/27–30`.

---

## 7. v2 — reconnect / host migration / rollback

### 7.1 Mid-match reconnect (secure resume token)

* On `welcome` the server issues a **256-bit cryptographically random,
  URL-safe bearer token**. It stores only the **SHA-256 hash**; the token is
  never written to server logs. The client persists it in
  `user://arena_fc_resume.json` (desktop/mobile) or browser `user://`
  storage (Web/IndexedDB).
* A dropped client's **slot, team, controlled-player index, name and ready
  flag are reserved for 180 s** (`--grace-seconds 5..3600`). The lobby shows
  that slot as `(reconnecting…)`.
* Reconnect sends `hello` with `token` + `room`. The server looks the hash up,
  fixes the slot and replies with `welcome` (same slot/team, **no new token**),
  then a `resume` packet containing a **complete engine checkpoint**: every
  player field, ball spin/pass targets, score, clock, phase, commentary,
  event feed, xorshift RNG word and the current simulation tick. The client
  rebuilds its engine and continues from that exact tick — **the match is not
  restarted**.
* If the old socket is still open it is closed and **its late `OnClose` is
  ignored**, so reconnect cannot accidentally re-mark the player offline.
* A forged/random token cannot steal a slot: `Tools/net_v2_smoketest.py`
  asserts this explicitly. Tokens are compared in constant time.
* The C# client retries automatically (1 s → 8 s exponential backoff) while
  inside the grace window. The browser client does the same.

### 7.2 Host migration

* The host is an **explicit stored slot**, not "the lowest connected slot",
  so a reconnecting former host does not steal the role back and cause
  flapping.
* When the host disconnects, the lowest still-connected slot becomes host.
  A `host` packet (`host`, previous `slot`, `reason`, `authority`, `tick`,
  `started`) is broadcast, then a fresh `lobby`. The **match keeps running** —
  `Room.Started`/`Engine` are untouched and ticks continue uninterrupted.
* The migrated host immediately gets **start / ready / chat / kick** control
  (`kick` with `kickSlot` is new in v2).
* **`--peer-host` (opt-in):** the *actual simulation* is transferred too.
  The server sends `authority` with the full checkpoint to a client that
  advertised `caps & 4` (`CapPeerHost`), switches to relay mode and forwards
  `peerinput` batches (three 60 Hz ticks per 20 Hz message). The new host
  steps its own `MatchEngine` at 60 Hz and sends `submit` (snapshot +
  `full` + trailing input log) at 20 Hz; the server relays `snap` to the
  others and keeps a cached engine so it can hand off **again** if that host
  also drops.
* **Browser clients advertise `caps=1`** (reconnect only) because GDScript
  cannot run the shared C# simulation. If no capable client is online the
  server logs that and **stays authoritative** — so a WebGL-only room never
  loses its match.
* Without `--peer-host` (the default) migration is a **role change**; the
  server remains the single authority. This is the recommended LAN/VPS setup.

### 7.3 Rollback prediction

* The pure-C# `RollbackPredictor` (`Scripts/Core/Net/RollbackPredictor.cs`)
  keeps a bounded history (180 ticks / 24-tick re-simulation cap) of complete
  `EngineCheckpoint`s and the inputs used for each tick.
* Every 60 Hz tick the client predicts **before** any snapshot arrives, so the
  controlled player responds on the next rendered frame regardless of RTT.
* Every `snap` now carries the authoritative **RNG word** (`rng`), global time
  (`gt`) and a **trailing input log** (`inputs: [{t, c}]`). On receipt the
  client rewinds to that tick, overwrites the networked fields with the
  authoritative state, restores the authoritative RNG word and re-simulates
  the unconfirmed tail. Re-simulation is bounded and degrades to a hard reset
  for very old snapshots.
* Remote players and the loose ball still use 100 ms snapshot interpolation;
  the local player and a dribbled ball come from the predicted engine. That
  hybrid keeps remote motion smooth while eliminating local input lag.
* `EngineCheckpoint` capture/restore is also what makes resume and peer-host
  handoff bit-exact. `Tests/Program.cs` verifies that a restored engine
  continues deterministically for another 90 ticks.

### 7.4 New protocol messages (v2)

| `t` | Direction | Purpose |
| --- | --- | --- |
| `resume` | server → client | full live-match checkpoint after reconnect |
| `host` | server → all | host slot changed (migration) |
| `authority` | server → new host | you now own the simulation + full checkpoint |
| `submit` | peer host → server | authoritative snapshot + `full` + input log |
| `peerinput` | server → peer host | batched commands from other peers |
| `kick` | host → server | remove `kickSlot` |
| `hello.token` | client → server | secure resume token |
| `hello.caps` | client → server | `1` reconnect, `2` rollback, `4` peer-host |
| `snap.rng`, `snap.gt`, `snap.inputs` | server/host → clients | rollback data |

### 7.5 Verification performed (27 October 2026, Linux)

| Test | Result |
| --- | --- |
| `dotnet run --project Tests/CoreTests.csproj -c Release` | **88 / 88** (was 66) |
| In-engine `--selftest` (Godot 4.7.2 Mono, headless) | **47 / 47** (was 39) |
| `Tools/net_smoketest.py` (classic 2-client) | **17 / 17**, both authority modes |
| `Tools/net_v2_smoketest.py` (`--peer-host`) | **36 / 36** — tokens, migration, handoff, resume, rollback fields, kick, forged token |
| `Tools/net_v2_smoketest.py` (default host-role mode) | **36 / 36** |
| `Tools/net_reconnect_e2e.py` (real Godot C# client) | **11 / 11** — process killed mid-match, second process resumed at a live tick (~570) with `resumed=True`, 154 further snapshots, 153 corrections / 2031 replayed ticks |
| `Tools/net_hostmigration_e2e.py` (real Godot C# peer host) | **9 / 9** — host role + live simulation handed to a headless C# client; >140 submissions, 120 relayed snapshots, tick ~115 → ~550 |
| Headless Godot C# online probe | 272 snapshots, 271 corrections, 2934 replayed ticks |
| Exported WASM build in Chromium 156 (WebGL 2.0) | connected with v2 `hello`, received a 43-char token, started a match (`ARENA_FC_WEB_WELCOME`, `ARENA_FC_WEB_BEGIN`) |
| Real rendered frames | `media/screenshots/31_online_v2_lobby.png`, `32_online_rollback_hud.png`, `media/videos/07_online_v2.mp4` |

Reproduce the v2 checks:

```bash
./run-server.sh --peer-host --grace-seconds 180 &
python3 Tools/net_v2_smoketest.py --url ws://127.0.0.1:7777
python3 Tools/net_reconnect_e2e.py --url ws://127.0.0.1:7777 --room MYROOM
python3 Tools/net_hostmigration_e2e.py --url ws://127.0.0.1:7777 --room MYROOM2
python3 Tools/net_smoketest.py --url ws://127.0.0.1:7777 --seconds 4
```

---

## 8. Honest current limits

* No matchmaking, friends list, accounts or skill rating — room codes only.
* No NAT hole punching / STUN-TURN. Internet play needs a reachable server
  (port forward, VPS or reverse proxy). WebRTC P2P is a possible later step.
* Reconnect works **while the room's slot reservation is alive** (default
  180 s). After that, or if the server process restarts, you must rejoin the
  lobby for the next match. Tokens are in-memory only — there is no persistent
  account database to survive a server restart.
* Host migration keeps the **room** alive; it cannot survive the **server
  process** stopping. `--peer-host` moves the simulation to a desktop client
  but the server is still the hub/relay, so a server outage still ends the
  match. A fully peer-to-peer (WebRTC) fallback is future work.
* No TLS/auth inside the server; use a reverse proxy + WSS for public use.
  Resume tokens are bearer credentials — protect the connection.
* Rollback prediction is implemented in the **C# desktop/mobile core and
  client**. The GDScript Browser Edition uses snapshot interpolation plus
  token reconnect and host-migration notices, but no rollback re-simulation
  (it has a reduced, separate 5-a-side sim). On a high-latency link the
  browser player will still feel their own input delay.
* Prediction is not input-delay compensation for *remote* players and does not
  prevent all visual corrections on jittery links; the HUD shows the measured
  error `e=…m` so you can see exactly how much was corrected.
* The GDScript Browser Edition is the reduced 5-a-side game. It joins the same
  rooms and renders the same authoritative state, but the desktop C# build is
  the full game (11v11, editor, GLB import/export).
* 1–4 humans per room, 5/7/11-a-side AI-filled teams. Co-op 2v2 is supported
  by the protocol and server but has had less play-testing than 1v1.
* No licensed assets, audio, commentary voices or anti-cheat service.

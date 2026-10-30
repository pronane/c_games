# netplay — shared online play for c_games

One server and one protocol for every online game in this repo:

| Game | Client | Server path | Picks |
|------|--------|-------------|-------|
| HD Fighter 2 | browser (`HD_Fighter/multiplayer/public/game.js`) | `/` | fighter name (`kairo`, `lyra`, …) |
| Egyptian Fighter | C, `egyptian_fighter/src/online.c` + `c/netplay.c` | `/egyptian` | fighter index `"0"`–`"6"` |
| TurboTumble64 | C, `TurboTumble64/src/online.c` + `c/netplay.c` | `/turbo` | `"<racer>:<track>:<cc>"` |

```
shared/netplay/
  server/            Node package "c-games-netplay-server"
    relay.js         rooms + lockstep relay (game-agnostic; moved out of HD Fighter's server.js)
    index.js         createServer(game) for one game, createHub(games) for several on one port
    games.js         per-game settings (allowed picks, input names, history length)
    hub.js           one process for all three games (npm start)
    test_hub.js      routing test (npm test)
    Dockerfile, render.yaml
  c/                 C client for raylib games (no dependencies)
    netplay.h/.c     rooms, clock, input delay, NACKs, hashes, rejoin
    netplay_ws.h/.c  WebSocket: WinHTTP on Windows, the browser on Emscripten, sockets on Linux/macOS
    test_netplay.c   two C clients against the real server, with a drop + rejoin (test_netplay.sh)
```

## How HD Fighter's online play works

The model is **deterministic lockstep with input delay**. The server never runs the game.

1. **Room.** A player sends `create` (gets a 5-character code such as `K7Q2M`), `join` with a code, or `quick` (paired with whoever is waiting). Each player has a `userId` kept for the tab/window, so reconnecting reclaims the same slot (0 = left, 1 = right).
2. **Pick + ready.** `pick` then `ready`. Ready is a set value, not a toggle. When both slots are picked and ready the server sends `countdown` with **one seed** and a start time.
3. **Load.** Each client loads its assets and replies `loaded` with its ping statistics (`rtt`, `jitter`, `samples`).
4. **Go.** When both have loaded, the server chooses **one input delay** for both (`chooseDelay`: each side's one-way time + jitter + 34 ms, in 1/60 s frames, 2–36) and sends `go`.
5. **Lockstep.** Both clients step the sim at a fixed 1/60 s of wall time (never faster: a stall restarts the clock instead of fast-forwarding). The local input for frame *f* is scheduled for frame *f + delay* and sent as a packed bit mask (`{"t":"input","base":B,"bits":[…],"ack":A}`), repeating the unacknowledged tail. Frame *f* runs only when both players' inputs for it are known, so both machines run the same frames with the same inputs. A gap triggers a `nack` and an immediate resend.
6. **Desync check.** Every 30 frames each client sends a hash of its state; a mismatch ends the round ("no contest").
7. **Drops.** If a socket drops mid-match the server holds the slot for 30 s (`peer_hold`). It keeps a copy of every input, so when the player rejoins it sends `resume` with both players' input history; the client replays from frame 0 to the current frame and carries on. If they don't return, the other player wins by forfeit.

Because only inputs cross the network, the bandwidth is tiny (about 60 small packets a second each way) and the server is cheap: one free Render instance is enough. The trade-off is feel: on a slow link the input delay grows (about 20 frames at 120 ms each way). Rollback would hide that, but it is not implemented here.

## Does it work for the other games?

**Egyptian Fighter: yes, and it now has an online mode.** It's built on the Padel Wars Stage 1 deterministic sim (`input.c`, `sim.c`, `rng.h`):
- each lockstep tick is one `Game_SimTick` with both players' 16-bit `InputBits`; the "pressed" bits travel explicitly;
- the face-off, the fight and the KO/time-out are all in the sim, so both machines reach the result on the same tick;
- checkpoint hashes are `Sim_Hash` folded to 32 bits, XOR `Sim_ConfigHash`, so mismatched sprite data is caught at the first checkpoint;
- `--sim-test` still passes with the online layer in, and its final hashes are unchanged from the Stage 1 report.

**TurboTumble64 — yes for two humans plus the CPU karts.** It already had a fixed `SIM_DT`, a 2-human VS mode and per-player `KartInput`. The changes were:
- a seeded race-sim RNG (`SimRand` / `RandF`) instead of `rand()`, so CPU driving, item rolls and the grid are identical on both machines. Visual-only randomness (ENHANCED extra particles) uses `VisRandF` so different graphics settings can't change the race;
- inputs are 9 bits: steer quantised to −15…15 plus accelerate, brake, hop and item. The hop and item presses are derived in the sim;
- both machines simulate both humans and all six CPU karts. Each window draws only its own kart, full screen;
- the race ends on a fixed sim frame (`RACE_DONE` + 4.5 s) so both machines stop together. Slot 0's track and engine class are used.

Limits that apply to both C games:
- **Two players per room.** The relay is built around two slots (as HD Fighter is). Four-player karting would need N slots in `relay.js` and the C client.
- **Same build on both sides.** Float results must match bit-for-bit. Two copies of the same exe (or the same web build) are fine. A Windows build against a Linux build may differ in `sinf`/`powf`. The hash check catches it and ends the round instead of letting the games drift apart.
- **Input delay.** Same as HD Fighter. It's fine on a home connection, but sluggish on a bad one.

## Running it

```bash
cd shared/netplay/server
npm install
npm start                 # hub on :3000 → /  (HD Fighter web client), /egyptian, /turbo
npm test                  # hub routing
../c/test_netplay.sh      # builds the C client test, plays 600 frames with a drop + rejoin
```

HD Fighter can still run alone (`cd HD_Fighter/multiplayer && npm install && npm start`). Its `server.js` is now a thin wrapper that requires this package (`"c-games-netplay-server": "file:../../shared/netplay/server"`; `postinstall` installs the package's own dependencies). Its tests run unchanged against the shared relay.

Point the C games at a server with `--server ws://host:3000/egyptian`, the `EF_SERVER` / `TT_SERVER` environment variable, or a `netplay.cfg` file (`server = wss://your-app.onrender.com/turbo`; see each game's `netplay.cfg.example`).

### Deploy

- **Render, one service for everything:** use `shared/netplay/server/render.yaml` (root directory `shared/netplay/server`, start `node hub.js`, health check `/api/health`). HD Fighter's page is then at `/`, and the C games use `wss://<app>.onrender.com/egyptian` and `/turbo`.
- **Render, HD Fighter only:** unchanged (`HD_Fighter/render.yaml`, root directory `HD_Fighter/multiplayer`).
- **Docker:** build from the repo root, `docker build -f shared/netplay/server/Dockerfile .` (or `HD_Fighter/multiplayer/Dockerfile`).

The free Render tier sleeps. Clients show "Waking the server..." and keep retrying for 90 s.

### TLS from the C games

`wss://` (needed for Render) works on Windows through WinHTTP, which is part of Windows (link `-lwinhttp`; the build scripts do). On Linux/macOS the plain-socket backend does `ws://`; build with `-DNETPLAY_OPENSSL -lssl -lcrypto` for `wss://`. An Emscripten/web build uses the browser's WebSocket (link `-lwebsocket.js`).

## Adding a game

1. Add an entry to `server/games.js` (name, allowed picks) and a path in `hubGames`.
2. In the game: make the sim step deterministic (fixed dt, randomness only from the match seed, no `GetFrameTime()`/`rand()`/input reads inside it) and write a state hash.
3. Use the C client as in `netplay.h`:

```c
Netplay *np = Np_New(url, userId);
Np_Create(np);  /* or Np_Join(np, code) / Np_Quick(np) */
Np_Pick(np, "3"); Np_Ready(np, true);
/* each frame */
Np_Poll(np);
while (Np_NextEvent(np, &ev)) { /* COUNTDOWN -> load, Np_Loaded; START -> reset sim with ev.seed */ }
for (int i = 0, n = Np_StepsDue(np); i < n; i++) {
    uint16_t in[2];
    Np_SetLocalInput(np, myBits);
    if (!Np_FrameInputs(np, in)) break;
    Sim_Step(in[0], in[1]);
    Np_FrameDone(np, Sim_Hash());
}
```

`NETPLAY_DEBUG=1` prints the lobby traffic (`=2` adds inputs and hashes).

## Message reference

Client → server: `create`, `join {room}`, `quick`, `pick {char}`, `ready {ready, readySeq}`, `loaded {startId, rtt, jitter, samples}`, `input {base, bits[], ack}`, `nack {fromFrame, toFrame}`, `hash {frame, hash}`, `hb`, `hold_frame {frame, hash, base, bits}`, `give_up`, `ping {ts}`, `leave`. All carry `userId` where they identify the player.

Server → client: `created` / `joined` / `matched` (room, slot, picks, ready), `queued`, `room_state`, `peer`, `peer_pick`, `ready_ack`, `countdown {seed, startAt, startId}`, `countdown_cancel`, `go {seed, delay, startAt, now}`, `input`, `nack`, `hash`, `hb`, `peer_hold {timeoutMs}`, `need_frame`, `resume {frame, end, have, hash, p0, p1}`, `peer_back`, `forfeit {winner}`, `match_end`, `peer_left`, `pong`, `error {msg}`.

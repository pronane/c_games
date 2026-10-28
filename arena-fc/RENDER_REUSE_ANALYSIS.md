# HD Fighter 2 → Arena FC: source-verified reuse analysis (v2)

**Date:** 28 October 2026
**Source of truth:** `https://github.com/pronane/c_games` — **public** repo, branch
`main`, HEAD `157ee3645102441a1426602d944071b8f63738ed`, 1,195 files, ~363 MB.
No PAT was needed or used: the repo is public, so everything below came from
unauthenticated GitHub API + `raw.githubusercontent.com`.

Files examined:

| File | Size | Role |
| --- | --- | --- |
| `multiplayer/server.js` | 9,333 B / 198 lines | **the real server** |
| `multiplayer/public/game.js` | 19,838 B | client logic |
| `multiplayer/public/index.html` | 8,201 B | client shell |
| `multiplayer/package.json`, `package-lock.json` | — | `ws`, `express`, `cors` |
| `multiplayer/render.yaml` | 175 B | nested Blueprint |
| `render.yaml` (root) | 249 B | root Blueprint |
| `multiplayer/Dockerfile` | 127 B | `node:20-slim` |
| `.github/workflows/deploy.yml` | 332 B | CI |
| `DEPLOY.md`, `README_ONLINE.md`, `README.md` | — | deploy docs |
| `assets_hd/`, `multiplayer/public/assets_hd/` | 119 files each | **duplicated** assets |

**Verification performed:** `git ls-remote` and the GitHub tree API; byte-diffed
the repo's `game.js` and `index.html` against the live deployment — **both are
identical**, so the deployed build is this source. I also ran the real
`server.js` locally on port 3100 and drove
`create → join → pick → pick → ready → ready → input`, capturing the exact
messages. So the protocol below is observed, not inferred.

---

## 1. Corrections to my earlier analysis

I need to be explicit about what I got wrong when I only had the live client.

| # | My earlier claim | Reality in the source |
| --- | --- | --- |
| 1 | "A GitHub Actions deploy hook gates deploys." | **There is no deploy hook.** `.github/workflows/deploy.yml` is named *Deploy Online Multiplayer* but only runs `npm install --prefix multiplayer` and `timeout 3 npm start --prefix multiplayer \|\| true`. It is a 3-second smoke test. The hook existed only in **my reconstruction**, not in the real repo. Deploys happen via the **Deploy-to-Render button** in `DEPLOY.md` (`https://render.com/deploy?repo=…`) or a manual Web Service with auto-deploy on push. |
| 2 | Health check `/health`. | Real endpoints are **`/api/health`**, `/api/rooms`, `/api/debug`. Root `render.yaml` correctly uses `healthCheckPath: /api/health`. My reconstruction used `/health`. |
| 3 | "Server needs `$PORT` support for Render." | The real server already does `const PORT = process.env.PORT \|\| 3000` and `server.listen(PORT,'0.0.0.0')`. **It is Render-ready.** The `$PORT` note applies only to **Arena FC's .NET server**, which reads only `--port`. |
| 4 | One Blueprint. | **Two conflicting `render.yaml` files.** Root: `env: node`, `rootDir: multiplayer`, `PORT=10000`, `plan: free`, `healthCheckPath: /api/health`. Nested `multiplayer/render.yaml`: `PORT=3000`, no plan, no health check, no `rootDir`. If Render's Root Directory is `multiplayer`, it may read the nested one and get a different config. Also `env: node` is the legacy key — current Blueprint spec uses `runtime: node`. |
| 5 | ~12-message protocol. | Real protocol is larger: `ping/pong`, `quick→queued/matched`, `create→created`, `join→joined/peer/peer_rejoin/room_state/error`, `pick→pick_ack/peer_pick/both_picked`, `ready→ready_ack/peer_ready/peer_waiting/room_state/start/error`, `input/state/hit/chat` relay, `leave→peer_left`. `matched` carries `peer`/`userId`; `created`/`joined` carry `picks`/`ready`/`rejoin`; relayed frames gain `from` (slot) and `ts`. |
| 6 | COOP/COEP headers are part of the pattern. | The real server sets **no** COOP/COEP. It sets `Cache-Control: no-store`, `etag:false`, `maxAge:0`. COOP/COEP were my addition and are **still required for Godot WASM** — so that's an Arena FC addition, not something to copy. |
| 7 | Rooms expire after 30 min (my reconstruction). | Real: empty rooms are deleted after **120 s**; `nextRoom` restarts at 1 on every process start, so `R0001` is reused after a restart (stale invite links can land in a *new* room with the same code). |
| 8 | "Rooms are cached." | `saveRoomState(room){ /* placeholder for Redis */ }` is an **empty function**. Every "cached" comment in the source is misleading — nothing persists. `userRoom` (userId → room) is never pruned, so it grows unbounded. |
| 9 | Static assets served from `public`. | Client loads `./assets_hd/…` from `public/assets_hd/`. The server *also* mounts `/assets` → `../assets_hd`, but that route is **unused**; the repo simply contains two copies of the 119 asset files. `cors` is in `package.json` but never `require`d. |

### What I got right (confirmed)

* **Client-authoritative input relay.** The server never simulates combat, never
  computes HP, has **no fixed tick loop**. The comment `// INPUT: relay to
  peer(s) with server tick` is aspirational — the code only adds
  `m.ts = Date.now()`. The client runs `requestAnimationFrame(loop)` with
  variable `dt`. **This is the confirmed root cause of the HP desync** I measured.
* `state`, `hit` and `chat` are accepted and relayed verbatim by the server, but
  **the current client never sends them** (it only sends `create/join/quick/pick/
  ready/input/leave`). So the server has **unused generic passthrough hooks**.
* Single-origin static + `wss://` derived from `location.protocol`, `$PORT`,
  `0.0.0.0`, hash invite `#R0001`, touch joystick + gamepad — the multi-device
  / browser story is exactly as described and works (I tested it live, 14/14).
* No rate limiting, no origin check, no input validation. `/api/debug` publicly
  lists every room code (minor information leak).

### Real bugs found in `multiplayer/server.js`

1. **Line 99** `!room.userIds[0]===uid` is always false (`!x === uid` → boolean
   vs string). The "room full for this user" branch is dead code; lines 100–103
   are contradictory and also dead.
2. **Line 180** `r.players = r.players.filter(Boolean)` on disconnect compacts
   the array, but `picks`, `ready` and `userIds` stay keyed by **slot**. After a
   disconnect/rejoin, slot indices and `players[]` indices diverge — rejoins and
   broadcasts can target the wrong peer. This is a genuine reconnect bug.
3. Lines 105–108 assign slots via sparse-array juggling that can push duplicate
   `ws` references (`if(!room.players[0]) room.players[0]=room.players[slot]`).
4. `both_picked` is emitted twice to one client (observed in the protocol trace).
5. `cors` dependency and `/assets` static route are dead code; assets are
   duplicated (~12 MB) between `assets_hd/` and `multiplayer/public/assets_hd/`.
6. `saveRoomState` is a no-op; `userRoom` never cleaned; `nextRoom` resets.

---

## 2. Observed protocol trace (real server, local run)

```
A<- {"t":"created","room":"R0001","slot":0,"picks":{}}
B<- {"t":"joined","room":"R0001","slot":1,"picks":{},"ready":{}}
A<- {"t":"peer","id":"dbegd","slot":1,"picks":{}}
A<- {"t":"pick_ack","char":"kairo","slot":0}
B<- {"t":"peer_pick","slot":0,"char":"kairo","picks":{"0":"kairo"}}
... both_picked (x2 to B) ...
A<- {"t":"peer_ready","slot":1,...,"ready":{"0":true,"1":true}}
A<- {"t":"start","picks":{"0":"kairo","1":"lyra"},"seed":8195}
B<- {"t":"input","inp":{"right":true},"userId":"ua","from":0,"ts":1793201068496}
```

---

## 3. Revised verdict: can the same server be reused for Arena FC?

**More reusable than I first said — but still not drop-in.**

Two facts change the picture:

1. The real server is a **generic 2-player room relay**, not a fighter-specific
   one. It already has room codes, quick match, userId rejoin, slot assignment,
   broadcast-with-exclusion, static hosting on `$PORT`, and **unused** `state` /
   `hit` / `chat` passthrough.
2. **Arena FC v2 already has a peer-host relay mode**: `authority`
   (server → host, carrying a full `EngineCheckpoint`), `submit` (host → server:
   snapshot + `full` + input log), `peerinput` (server → host). In that mode the
   server is *literally* a relay that caches the last checkpoint and
   re-broadcasts `snap`. That maps almost 1:1 onto what `multiplayer/server.js`
   already does.

So a **fork** of the real `server.js` could host Arena FC rooms with roughly
**150–250 additional lines**: `hello → welcome` (token, slot, team, caps, grace),
`lobby` broadcasts, `start → begin` (match options), `submit` → cache `full` +
broadcast `snap`, host disconnect → elect new `caps&4` host and send
`authority` with the cached `full`, token reconnect → `resume` with the cached
`full` + trailing inputs, plus `kick`/`host`/`end`.

**But there are two hard constraints:**

* A **peer host must be a desktop C# client** (`caps & CapPeerHost`). Arena FC's
  GDScript browser client advertises `caps=1` and **cannot run the deterministic
  C# engine**. So a **browser-only room would have no authority**. Either require
  one desktop/mobile C# player, or keep the .NET authoritative server in the
  loop.
* Forking means **porting Arena FC's v2 semantics into Node** — you'd lose the
  server-authoritative 60 Hz sim, replay verification and the tested
  reconnect/host-migration logic unless you port it carefully. It is a **fork
  with ~60% reuse**, not "reuse the server unchanged".

### Three deployment topologies (revised)

**Option A — Fork the relay into a Node v2 server (a genuinely separate deployment).**
Single Node service, single origin, no .NET. Reuses the real room/relay code.
* **Pros:** one runtime, exactly the HD Fighter pattern, multi-device/browser
  through a peer host, smallest image, easiest to understand.
* **Cons:** browser-only rooms need a desktop host; you must port v2 protocol;
  no authoritative server sim → weaker determinism/anti-cheat; you inherit the
  relay bugs above and should fix them first.
* **Use when:** you want one codebase and are happy that a desktop/mobile C#
  client hosts each room.

**Option B — Real Node server as static edge + .NET authoritative server behind a `/ws` proxy (RECOMMENDED).**
One Docker image with Node 20 + .NET 9 (or a self-contained published .NET
binary) and a supervisor. Express keeps serving static with `no-store` **plus
COOP/COEP**; `http-proxy-middleware` (`ws:true`) pipes `wss://<host>/ws` to
`ws://127.0.0.1:7777`. Arena FC's handshake ignores the request path for WS
upgrades, so `/ws` needs **no .NET change**.
* **Pros:** all v2 netcode preserved (60 Hz authoritative sim, rollback,
  reconnect, host migration, replay); **browser-only rooms work**; one origin,
  one shareable `https://host/#ROOM`, one health check, one Blueprint.
* **Cons:** heavier image, two runtimes, needs a supervisor.

**Option C — Two separate Render services.**
Static Node site (the real `server.js` trimmed to static-only) + .NET Docker
service. Browser connects cross-origin to `wss://arena-fc-server.onrender.com`.
* **Pros:** simplest change, no proxy, independent scaling.
* **Cons:** two cold-starting free-tier services, two URLs, users must paste a
  long `wss://` address, and the `ws://` defaults still need fixing.

**Option D — Pattern transfer only (cheapest).**
Change no server. Copy the multi-device *patterns* into Arena FC's existing
.NET deployment: hash invites, `https→wss` auto-upgrade, same-origin default,
`no-store` headers, `$PORT`, `/api/health`, touch/gamepad parity, and a real CI
smoke test. Lowest risk, least new infrastructure.

---

## 4. Concrete changes Arena FC needs (verified against real source)

1. **`Server/Program.cs`** — `int port = int.TryParse(Environment.GetEnvironmentVariable("PORT"), out var ep) ? ep : NetProtocol.DefaultPort;` (the real Node server already does this; Arena FC does not).
2. **`Web/NetClient.gd`** — currently forces `ws://` when no scheme. On an HTTPS page that is **mixed content and will be blocked**. Auto-upgrade to `wss://` when `location.protocol==='https:'`; accept blank/relative `net_url` meaning same-origin `/ws`.
3. **`Web/BrowserBoot.gd`** — default `net_url` to same-origin WS; change shareable link from `/?net_url=ws://host:7777&net_room=CODE` to a hash invite `https://host/#CODE` (as HD Fighter does).
4. **`Scripts/Godot/Net/NetClient.cs` + `NetProtocol.NormalizeUrl`** — same `https→wss` upgrade for desktop/mobile.
5. **Static edge headers** — add `Cross-Origin-Opener-Policy: same-origin` and `Cross-Origin-Embedder-Policy: require-corp` (Godot WASM needs them; **the real HD Fighter server does not set them**), keep `Cache-Control: no-store`.
6. **`render.yaml`** — one authoritative Blueprint. If using the `rootDir` pattern, mirror the root file but use `runtime: node`, don't hardcode `PORT`, and point `healthCheckPath` at the endpoint you actually implement (`/health` or `/api/health`).
7. **CI** — replace the no-op `deploy.yml` with a real job: `npm ci` → start server → run `Tools/net_v2_smoketest.py` / a two-tab Puppeteer test against `wss://` → upload artifacts. Add a Render Deploy Hook only if you want deploys gated on that test.
8. **If forking the relay (Option A)** — fix first: slot mapping on `leave`, the `!a===b` condition, `userRoom` cleanup, `nextRoom` persistence, `/api/debug` exposure, rate limiting + origin checks, and implement `saveRoomState` with Redis or remove the misleading comments.

---

## 5. Platform caveats (unchanged, now measured)

* Render free tier sleeps; I measured **10–32 s cold starts** on the live HD
  Fighter service. WebSockets drop and **all rooms are lost** (both servers keep
  rooms in memory; `saveRoomState` is a no-op). Real cross-device play needs a
  paid plan or a keep-alive plus Redis.
* Rooms are per-process; >1 instance needs Redis pub/sub.
* Arena FC's browser build is a reduced GDScript 5-a-side client with reconnect
  + host-migration notices but **no rollback prediction**. Fine for cross-device
  play; not identical feel to the C# desktop build.
* `caps` already prevents browsers becoming peer host — that design carries
  over cleanly and is exactly why Option B is safer than Option A for
  browser-only rooms.
* Godot 4 **cannot export C# to Web** — hence the separate GDScript client and
  the need for a static edge at all.

---

## 6. Bottom line

The real HD Fighter deployment is a **clean, generic, single-origin Node relay**
with a **no-op CI "deploy" workflow** and **two conflicting Blueprints**. Its
deployment layer (static + `ws` on `$PORT`, hash invites, `wss` auto, `no-store`,
health endpoint, touch/gamepad) is directly reusable for Arena FC. Its **game
server logic is not** — but because Arena FC v2 already has a peer-host relay
mode, a **fork with ~60% reuse** is genuinely feasible if you accept a desktop
client as host. For full browser-only rooms with no compromises, use **Option B**:
keep the .NET authoritative server and put the Node server in front as a static
edge + `/ws` proxy.

**Step 0 before implementation:** restore the regressed Arena FC snapshot
(missing `Scripts/Core/Net/`, `Scripts/Godot/Net/`, `build/web/`, stale ZIPs)
and rebuild the web export.

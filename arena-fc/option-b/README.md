# Arena FC online: .NET server + the shared Node hub

Arena FC's match runs on an authoritative .NET server (`Server/`). Browsers can't talk to it directly
(an HTTPS page can only open `wss://` on its own host), so the **same Node hub that already serves HD
Fighter, Egyptian Fighter and TurboTumble64** (`shared/netplay/server`) now also:

- serves the Godot Web build at `/arena/`
- proxies `wss://<host>/arena/ws` to the .NET server on `127.0.0.1:7777`
- reports `/arena/api/health` (200 only while the .NET server accepts connections)

The hub's lockstep relay is **not** used for Arena FC. That relay is for two-player, bit-exact lockstep
games; Arena FC is server-authoritative with up to 4 humans and rollback, so the hub only forwards its
frames (`proxy.js`). Everything else in the hub is reused: Express, static hosting, health checks,
the Docker/Render deploy, and one public port and certificate for all four games.

```
browser ── https://host/arena/  ───────────────►  Node hub (shared/netplay/server)  serves build/web
browser ── wss://host/arena/ws  ───────────────►  Node hub ──► ws://127.0.0.1:7777  .NET Arena FC server
```

## Status: read this first

| Piece | Verified how |
| --- | --- |
| `proxy.js`, hub routing, `/arena/api/health` | `test_proxy.js` (15 checks) and `test_hub_arena.js` run against a fake game server. The hub test ran on a stand-in for Express, because the sandbox could not install the real package. Run `npm test` in `shared/netplay/server` to confirm with real Express. |
| Godot web client (`Web/*.gd`, audio, replay, aim, rig) | Run headless in Godot 4.7.2: `Tools/run-gd-tests.sh` |
| **The .NET server and the Docker image** | **Not built or run.** No .NET SDK was available. |
| **`Scripts/Core/Net/*.cs`** | **Missing from the repository** (see `MISSING_NET_SOURCES.md`). The server cannot compile until they are restored. |

## 1. Export the web build (once per change to the game)

In Godot 4.7.2 with the Web export templates installed, from `arena-fc/`:

```
godot --headless --export-release "Web" build/web/index.html
```

(`Web/export_presets_web.cfg` is the preset. Threads are off, so no COOP/COEP headers are needed.)

## 2. Try it on your LAN before deploying

From the repository root:

```
docker build -f arena-fc/option-b/Dockerfile -t c-games .
docker run --rm -p 10000:10000 c-games
```

Open `http://<your-LAN-IP>:10000/arena/` on two devices, choose **PLAY WITH FRIENDS**, leave the address
as `./ws`, create a room on one and join it on the other. Plain `http://` pages use `ws://`, which works
on a LAN; the internet needs HTTPS (below).

No Docker? Run the two processes yourself:

```
dotnet run --project arena-fc/Server -- --port 7777 --bind 127.0.0.1
ARENA_BACKEND=ws://127.0.0.1:7777 node shared/netplay/server/hub.js     # needs: cd shared/netplay/server && npm install
```

## 3. Deploy

`render.yaml` is a Render blueprint for one Docker web service (Docker needs a paid plan). Fly.io or any
VPS that runs Docker works the same: expose `$PORT`, terminate TLS in front, health check `/arena/api/health`.

| Variable | Meaning |
| --- | --- |
| `PORT` | public port (Render sets it; the image defaults to 10000) |
| `ARENA_BACKEND` | enables the `/arena` path; set by `start.sh` to the internal .NET server |
| `ARENA_WEB_DIR` | web build folder (default `arena-fc/build/web`) |
| `ARENA_ALLOWED_ORIGINS` | comma-separated Origins allowed to open the socket; empty allows any |
| `TRUST_PROXY=1` | take the client IP from `X-Forwarded-For` (needed behind Render/Fly for per-IP limits) |
| `ARENA_FC_PEER_HOST=1` | let a desktop player host the simulation (host migration); default is server-authoritative |

Limits in `proxy.js`: 16 sockets per IP, 1 MB per frame, a 30 s keep-alive ping (hosts drop idle sockets
after about a minute).

## What this does not fix

The .NET server's own findings (hand-written WebSocket framing, no per-IP limits of its own, etc. in
`ArenaFC_review.md`) still apply: the hub adds a cap and an Origin check in front, but it forwards frames
without parsing them. Replacing the hand-written server with ASP.NET's WebSocket support remains the
better long-term fix.

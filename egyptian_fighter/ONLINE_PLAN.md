# Padel Wars (Egyptian Fighter) online: plan

Plan written 29 Oct 2026 (Europe/London). Stage 1 implemented 30 Oct 2026 on the local branch
`padel-wars-deterministic` (not pushed). Model: HD_Fighter's lockstep relay (`HD_Fighter/multiplayer/`).
Line numbers in section 3 refer to the v4 source *before* Stage 1.

## 0. Stage 1 status (deterministic sim, no networking) - DONE

| Plan item | What was done | Differs from the plan? |
|---|---|---|
| #5 input | `src/input.c/.h`: `InputBits` (uint16) per player; held bits 0-4, "pressed this tick" bits 5-12. Keyboard + pads are sampled outside the sim (`Input_SampleFight`); `Game_SimTick(g, in[2])` only sees the bits. | Pressed edges are sent as event bits computed by the sampler (raylib `IsKeyPressed` / `Pad_Pressed`), not re-derived in the sim from the previous bits. That keeps local play bit-for-bit identical (e.g. holding J on the keyboard while tapping X on a pad still punches). It is just as deterministic: the bits *are* the input stream. |
| #1-#3 time | `Game_SimTick` always steps `SIM_DT = 1/60 s`; `main.c` runs it from an accumulator (`Sim_StepsForFrame`, 60 Hz +-1.5 ms snaps to one tick per frame, max 4 catch-up ticks). No `GetFrameTime`/`GetTime` in the sim (`invincibleTimer` uses the step). | Timers stay `float` seconds advanced by a constant `SIM_DT` instead of integer frame counters: same values on every run, and identical to the old game at 60 fps. Integer counters can come with fixed-point (1b). |
| #6 pause / fullscreen | Pause, controller-lost pause and the fullscreen toggle simply don't step the sim (no time is banked, no tap carries over). | Online mode must still not pause locally (stage 4). |
| #4 RNG | `src/rng.h` xorshift32 (splitmix-seeded) in `Game.rng`; seed per fight (`EF_SEED` env, or the server's `go.seed` later). | - |
| hash | `Sim_Hash` (FNV-1a 64, field by field, render data excluded) every 30 ticks. | - |
| #7 config hash | `Sim_ConfigHash`: rule constants + per fighter the loaded frame counts / frame times / loop points / projectile kind (from `sprites.cfg` and the sheet image widths). Logged at every fight start; written into replays. | - |
| textures | Not split into a `PlayerGfx` yet. Instead `Player.noGpu` makes the same loader read only image sizes, so `--sim-test` / `--replay` run without a window. Copying `Game` is a valid snapshot (used by the test). | Split later for rollback (stage 6). |
| test | `--sim-test` (headless): 4 scripted fights x {run twice, 1 vs 3 ticks per frame, random 0-4 ticks + pause frames}, input-change sensitivity, CPU seed sensitivity, record -> replay round trip, accumulator checks. `--record <file>` / `--replay <file>`. | - |
| #10 floats | Kept. See "Determinism" in README.md. | Fixed-point is stage 1b, needed for Windows<->browser cross-play. |

## 1. Recommendation (short version)

**Yes, lockstep + a thin relay is the right approach for this game.**
- It is a 2-player fighter with about 12 buttons per player. A whole frame of input fits in one 16-bit number, so the relay only ever carries tiny messages.
- Delay-based lockstep (adaptive delay of 2-6 frames) is what HD_Fighter already does, and it plays fine on normal home or 4G links.
- Rollback would feel better on bad links, but it needs save/restore of the whole sim and re-simulating several frames per tick. Do that later, after the sim is clean (stage 6).
- Arena FC already ships rollback, so it can serve as a reference.

**Platforms:**
- **Web first (Emscripten), native Windows second.** The web build is what makes "multiple devices" easy: phones, Macs and other PCs just open a link, with nothing to install and no SmartScreen warnings.
- The native Windows build connects to the same relay and can play against web players, with the float caveat in section 3.
- I would **not** build a web-only JavaScript rewrite. The C game is the game: compile it to wasm and keep one codebase.

**Server: one shared module of code, independent deployments.** See section 4.
- The relay code lives once in the repo as `multiplayer-core/`.
- Each game runs its own instance with its own config, port/URL and hosting: HD_Fighter, Padel Wars, TurboTumble64 and optionally Arena FC.

**Effort:** about 8-12 working days to get to a playable, tested web build, plus 2-4 days for native Windows. Details in section 5.

## 2. How the C game talks to the relay

| Build | Transport | Notes |
|---|---|---|
| Web (Emscripten) | `<emscripten/websocket.h>`: `emscripten_websocket_new`, `..._set_onmessage_callback`, `emscripten_websocket_send_utf8_text` | Built in, no extra library; link with `-lwebsocket.js`. Callbacks run on the main thread between frames, so no locking is needed. TLS (`wss://`) comes free from the browser. |
| Native Windows / Linux | **libcurl WebSocket API** (`curl_ws_send` / `curl_ws_recv`, with `CURLOPT_CONNECT_ONLY=2L`), polled once per frame | Recommended. MSYS2 already has the package (`pacman -S mingw-w64-ucrt-x86_64-curl`), it supports `wss://` with TLS built in (OpenSSL or Windows Schannel), and the license is permissive. Downside: the build ships extra DLLs, or needs a bigger static link. |
| Native (alternative) | Hand-written WS client over a raw TCP socket (~400 lines: HTTP upgrade + framing) | Only works with `ws://` (LAN or self-hosted). Hosted platforms (Render/Fly/Railway) force `wss://`, which means adding TLS (mbedTLS), and then curl is simpler. |
| Raw UDP | Not recommended | Browsers cannot do UDP, so web and native couldn't share a relay, and lockstep doesn't need UDP at these input sizes. |

Message format:
- Keep HD_Fighter's JSON on the wire. A tiny JSON helper in C (a vendored copy of `cJSON`, MIT, 1 file) handles control messages.
- Input messages are short and fixed-shape (`{"t":"input","base":N,"bits":[..],"ack":N,"epoch":E}`), so C can write them with `snprintf`.
- A binary encoding is optional later. It isn't needed for 2 players × 60 Hz.

The C client library (`mp_client.h/.c`, see section 4) hides the difference behind one API:
`mp_connect(url)`, `mp_poll()`, `mp_send_input(frame, bits)`, `mp_get_input(slot, frame, &bits)`, `mp_send_hash(frame, h)`, plus event callbacks.
It has two backends: `mp_ws_emscripten.c` and `mp_ws_curl.c`.

## 3. Determinism audit (v4 source)

Lockstep only works if both machines, given the same inputs, produce exactly the same fight on every frame. Today they would not. This table lists what has to change.

| # | Where | Problem | Change |
|---|---|---|---|
| 1 | `game.c:621` `float dt = GetFrameTime();` used at `game.c:707` (prefight), `749-750` `Player_Update(dt)`, `755` `UpdateProjectiles(g, dt)` (projectile age at `game.c:387`, 4 s life), `758` `roundTimer -= dt`, `796` (result screen) | Real wall-clock frame time: a 59.8 fps machine and a 60.1 fps machine drift apart within seconds | The fight sim runs on a fixed step: `#define SIM_DT (1.0f/60.0f)`. Better still, use integer frame counters (`roundFrames`, `prefightFrames`, `age` in frames). |
| 2 | `player.c` `Player_Update`: `stateTimer += dt`, animation `frameTimer += dt` (~`player.c:388`) drives `currentFrame`, state changes, hit windows (`Player_Progress`) and projectile launch | Same as #1, and this is where hits are decided | Count frames instead. Convert the `sprites.cfg` frame times to whole 60 Hz ticks at load time (`ticks = round(ft*60)`). |
| 3 | `player.c:465` `p->invincibleTimer -= GetFrameTime();` | Reads raylib's clock inside the sim | Use an integer `invincibleFrames--`. |
| 4 | `game.c:295, 309, 310, 315, 319, 322, 331, 334, 336`: `GetRandomValue` in `SimpleCPU` | Unseeded global RNG | Only matters for vs-CPU, but replace it anyway with a seeded PRNG (xorshift32/PCG) stored in `Game`, seeded from the server's `go.seed`. That also allows online vs-CPU and replays. |
| 5 | `game.c:216-233` `ReadInputP1`, `236-256` `ReadInputP2` (`IsKeyDown`/`IsKeyPressed`), `263-278` `ApplyPad`, combined at `718-745` | The sim reads the keyboard and pad directly, and "pressed" edges depend on the local frame | Split it: `SampleLocalInput() -> uint16 bits` (outside the sim), then `Sim_Step(&g, bits1, bits2)`. Compute edges *inside* the sim from the previous frame's bits stored in the state. |
| 6 | `main.c:47-52` controller-disconnect pause, `main.c:54` ESC/Start pause, `main.c:64` fullscreen toggle skips `Game_Update` | Any local pause or skipped frame desyncs the match | Online: these must not stop the sim. Show the overlay, but keep stepping or stall through the lockstep pacer. Separate "sim step" from "render frame" in `main.c`. |
| 7 | Sim timing comes from asset files: `sprites.cfg` frame counts/times (`player.c:232, 239`), `loopFrom` (`player.c:213`), `projectileKind` (`player.c:203-208`, folder-name fallback `player.c:309-310`), `FRAME_COUNTS` defaults when a PNG/cfg is missing (`player.c:144, 151`) | Two players with different asset versions get different hit timing, which is a silent desync | Compute a **config hash** (FNV-1a over roster + each character's frame counts/ticks/loopFrom/projectileKind + `SIM_VERSION`) and send it in `create`/`join`. The relay refuses mismatches with a readable "update your game" message. |
| 8 | `game.c:173-204` sprites load inside `StartFight` | Loading takes a different time on each device | Use HD_Fighter's `loaded` handshake: the server sends `go` (start frame, seed) only after both clients report loaded. |
| 9 | `game.c:196` `getenv("EF_TEST_HP2")` | Test hook changes HP | Ignore it in online mode. |
| 10 | Floats in the sim (positions, velocities: `MOVE_SPEED 4.5`, `GRAVITY 0.55`, `pos.x += vx`, `fabsf`/`fminf`) | Only `+ - * /` and fabs/fmin are used. These are exactly reproducible on x86-64 SSE2 and wasm **if** the compiler doesn't fuse or reorder them | Build with `-ffp-contract=off`, never `-ffast-math`; 64-bit Windows only (or `-msse2 -mfpmath=sse`). For guaranteed native↔web cross-play, move positions to fixed-point ints (e.g. 1/256 px). It's about half a day and removes the risk completely. Recommended. |
| 11 | Update order: p1 then p2, hits resolved in a fixed order | OK as long as slot 0 is always player 1 on both machines | The relay's slot number decides P1/P2, not "who is local". |
| OK | `player.c:604` `GetTime()` (invincibility flash), `sinf/cosf/powf` in draw code (`game.c:418-506, 826-959`), `pad.c:221/307` `GetFrameTime` (menu key repeat), `static logStates` (`player.c:326`) | Render or menu only | No change. Keep them out of the sim's state hash. |
| Note | `Player` contains `SpriteSheet sheets[STATE_COUNT]` (GPU textures) next to the gameplay fields | Can't hash or snapshot the struct as raw memory | Move textures to a separate `PlayerGfx`. The sim state then becomes plain data, which also makes rollback possible later. |

Desync detection: as in HD_Fighter, each client hashes the sim state every 30 frames and sends `hash`, and the relay compares them.
- Hash the fields, not the raw struct, because of padding.
- Log the first mismatch frame together with both states.

## 4. Shared relay: one module in the repo, one deployment per game

### 4.1 What is generic and what is HD_Fighter-specific today

In `HD_Fighter/multiplayer/server.js` (982 lines):
- **Generic:** rooms and codes, `quick`, `create`/`join`, slots, `ready` / `countdown` / `loaded` / `go` with seed and start frame, `input` relay with `base/bits/ack/epoch`, the history buffer (`blankHist`, `noteHist`, `packHist`, `histEnd`), `nack`, `hb`/`ping`/`pong`, `chooseDelay(rtt, jitter)`, hold/resume (`beginHold`, `sendResume`, `peer_hold`, `need_frame`, `peer_back`), forfeit, `match_end`, `give_up`, room expiry, `/health`, and static file serving.
- **Game-specific:**
  - `FIGHTERS` set (line 17) plus `pick`, `rememberPick` / `restorePick`;
  - `INPUT_KEYS` plus `packLoose` (lines 21, 132) for old loose-input clients;
  - the `state`/`hit`/`chat` passthrough (line 891);
  - fixed 2 slots;
  - hist size 6400 frames;
  - the countdown length.

In `public/`, `wire.mjs`, `pace.mjs` and `stall.mjs` are generic. `sim.mjs` and most of `game.js` (lobby UI, drawing) are HD_Fighter's own.

### 4.2 Proposed layout

```
multiplayer-core/                 # shared CODE (one copy in the repo)
  PROTOCOL.md                     # every message, field and state machine; protocol version
  server/
    relay.js                      # createRelay(gameConfig) -> { listen, close, httpHandler }
    rooms.js  hist.js  delay.js  hold.js
    bin/run.js                    # node bin/run.js --config ../../padel_wars/online/game.config.json
  client-js/                      # for JS games (HD_Fighter)
    wire.mjs  pace.mjs  stall.mjs  lockstep.mjs (input queue, delay, hashes, resume)
  client-c/                       # for C/raylib games (Padel Wars, TurboTumble64)
    mp_client.h  mp_client.c      # API from section 2
    mp_ws_emscripten.c  mp_ws_curl.c
    vendor/cJSON.c cJSON.h
  test/
    bots.mjs                      # headless node bot clients (fake 60 Hz players)
    netem-proxy.js                # delay/jitter/drop/blackhole proxy (from hdperf stuckproxy)
    relay.test.mjs

HD_Fighter/multiplayer/           # this game's DEPLOYMENT: thin
  game.config.json                # {gameId:"hd_fighter", slots:2, picks:[...], inputBits:12, protocol:2}
  server.js                       # 10 lines: createRelay(require('./game.config.json'))
  public/...                      # game client, imports ../../multiplayer-core/client-js
  Dockerfile / render.yaml        # its own service, own URL

egyptian_fighter/online/          # Padel Wars' DEPLOYMENT
  game.config.json                # {gameId:"padel_wars", slots:2, picks:["char_egypt",...], inputBits:12,
                                  #  configHashRequired:true, countdownMs:3000, histFrames:6400}
  server.js  Dockerfile  render.yaml
  web/shell.html                  # Emscripten page; the relay also serves the built .wasm/.data
```

`gameConfig` decides:
- `gameId`: the relay rejects a client whose `hello.gameId` differs. That stops a Padel Wars build from joining an HD_Fighter instance by mistake.
- slot count: 2 for the fighters, up to 4 for TurboTumble64.
- the list of valid picks.
- input width: 16 or 32 bits.
- hash interval, history length, delay bounds and hold/forfeit times.
- an optional `onPick`/`validate` hook.

The core never knows what a "fighter" is.

**Deployments are independent:**
- Each game has its own process, URL, config, logs and free-tier sleep behaviour.
- Updating or restarting one game's server does not touch the others.
- Each game pins the core by protocol version, so a core change can't silently break a game that hasn't been redeployed.
- Simplest way to do that: the game's Dockerfile copies `multiplayer-core/` from the same commit.

**Fixes the core must include** (found while re-verifying HD_Fighter v5):
- **Resume pacer bug (critical):**
  - `resumeMatch` uses `createPacer(performance.now())`, which starts the pacer's clock at frame 0. The resumed client then freezes for `sim.frame/60` seconds.
  - In v5, any drop more than ~9 s into a round ends in "Connection lost".
  - Fix: `createPacer(performance.now() - sim.frame*FRAME_MS)`.
  - Write-up: `/workspace/preview/hdfighter_pr1_v5/BUG_resume_pacer_freeze.md`.
  - The C client's pacer must start from the resume frame in the same way.
- Keep v5's connect timeout (4 s), backoff with jitter, "heartbeats don't count as liveness", the "Poor connection" banner and the 30 s reconnect hold. Those all re-tested well.

### 4.3 The other games

- **TurboTumble64** (C/raylib kart racer) can use the same core and `client-c`. 2-4 slots is a config change. It would need its own determinism audit: physics and items RNG.
- **Arena FC** already has its own authoritative C# server with rollback, host migration and reconnect (`arena-fc/ONLINE.md`, `Server/Room.cs`).
  - That is a different model: the server runs the sim.
  - Don't force it onto the relay. At most, reuse `PROTOCOL.md` naming and the test bots.
  - Being skeptical: making one core serve both an authoritative C# server and a JS relay would cost more than it saves.

## 5. Staged plan

| Stage | What | Effort | Done when |
|---|---|---|---|
| 0 | Land the v4 source in the repo (see `padelwars_repo_compare.md`) | 0.5 d | Repo builds v4 as-is |
| 1 | **Sim refactor:** fixed step, frame counters, seeded PRNG, input bitmask with in-sim edges, textures split from state, `Sim_Step()`, `Sim_Hash()`. No networking yet. | 2-3 d | Offline game plays the same. A headless test that runs 10,000 frames of random inputs twice gives identical hashes. |
| 1b | Fixed-point positions (optional but recommended for cross-play) | 0.5-1 d | Same tests, plus native and wasm hashes match |
| 2 | Extract `multiplayer-core` from HD_Fighter (server + client-js), switch HD_Fighter to it, fix the resume-pacer bug | 2 d | HD_Fighter's existing browser tests pass on the core |
| 3 | **Web build** of Padel Wars: emsdk, raylib built for `PLATFORM_WEB`, `--preload-file assets`, main loop via `emscripten_set_main_loop`, audio unlocked on first click/tap | 1.5-2 d | Runs in Chromium/Firefox/Safari, local 2P works |
| 4 | `client-c` + online menu (Create / Join code / Quick match), lobby, ready/loaded/go, lockstep pacer with adaptive delay, hold/resume/forfeit overlays | 2-3 d | Two browsers play a full match through the relay. Drop, reconnect and forfeit all work. |
| 5 | Native Windows client via curl WebSocket, cross-play with web | 2-4 d | Windows exe vs browser plays a full match with no hash mismatch |
| 6 | Later: rollback (save/restore state, re-sim up to 7 frames), spectators, rematch | 3-5 d | Optional |

**Main risks**
1. **Web texture limits and download size:**
   - `assets/char_mike/victory.png` is **10608×800**, which is over the 8192 px texture limit on many phones and older GPUs. 7 more sheets are wider than 4096.
   - Sprites total about 52 MB of PNG, which is a heavy first load on mobile.
   - Fix: re-pack into 2D atlases (rows of frames) at most 4096 px, use a half-size set on the web (Sprite Forge already exports 320×400 cells), and load characters on demand, or at least only the two picked ones.
2. **Audio:** browsers block sound until a click or tap. Start `InitAudioDevice` (or resume the context) on the first input. Raylib's web audio otherwise works.
3. **Gamepad on web:**
   - `pad.c` uses GLFW raw-joystick code. Compile it with the existing `-DEF_NO_RAW_PAD` path, and rely on raylib's Gamepad-API mapping in the browser (works in Chromium/Firefox; Safari is patchier).
   - `gamecontrollerdb.txt` (435 KB) isn't needed on web.
   - Add touch buttons for phones later.
4. **Native↔web float differences:** solved by 1b, or else limit cross-play to "same platform".
5. **Hosting:** free tiers (e.g. Render) sleep after inactivity, so the first connect can take 30-60 s. HD_Fighter's "Waking the server..." screen covers this.
6. **Settings file:** `gfx.c:133` writes `settings.cfg`. On web that needs IDBFS, or skip saving.
7. **Native networking build:** curl adds DLLs and size to `build_release.bat`'s static-link attempts. Expect some MSYS2 fiddling.

## 6. What can be tested here on the box (headless)

The box has gcc, Node and Playwright, plus Chromium/Firefox/WebKit under Xvfb. It does not have emsdk (easy to install) or a Windows machine.

- **Sim determinism:**
  - Build the refactored sim *without raylib* as a native test binary.
  - Run random and recorded input streams and compare hashes across runs and `-O0/-O2`.
  - Compile the same files with emcc and run them in Node, so native vs wasm hashes can be compared. This is the key cross-play test.
- **Relay:** node bot clients (`test/bots.mjs`) play thousands of frames against a local relay through the netem proxy: delay, jitter, burst loss, blackhole, stuck CONNECTING, 15 s outage, forfeit. These are the same scenarios that found the v5 pacer bug.
- **Web build:**
  - Playwright drives two browser contexts (Chromium×Firefox×WebKit) under Xvfb. WebGL runs on software rendering, slowly but correctly.
  - Read the game's status via a small `Module.mp_status()` export, and record side-by-side videos as for HD_Fighter.
- **Native Linux client:** raylib 5.5 source is already in `TurboTumble64/deps/`, so a Linux build of the native client (with curl) can run under Xvfb against a browser. That covers the curl backend.
- **Not testable here:**
  - real Windows .exe behaviour (MSYS2 static link, Schannel TLS, Windows Defender);
  - real phones (texture limits, touch, Safari gamepad);
  - real long-distance latency.

These need a short manual test with the user.

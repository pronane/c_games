# Arena FC: controls, local multiplayer and where to deploy

## Controls

| | Player 1 | Player 2 (local versus) | Gamepad |
| --- | --- | --- | --- |
| Move | WASD | Arrow keys | Left stick or D-pad |
| Sprint | Shift | `/` | RB / R1 or either trigger |
| Pass | E | `,` | A / Cross |
| Through ball | Q | `L` | Y / Triangle |
| Shoot (hold, release) | Space | `.` | X / Square |
| Tackle (slide when sprinting) | F | `;` | B / Circle |
| Switch player | Tab | `'` | LB / L1 |

Players also switch automatically to whoever is closest to the ball. Menu: Esc or the pad's Start button.
Camera `C` / `1-4`, zoom wheel or `+/-`, replay `V`, mute `M`.

**2 PLAYERS - LOCAL VERSUS** (main menu): P1 plays the red team and P2 the blue team on one machine.
With two pads, pad 1 drives P1 and pad 2 drives P2; with one player, every pad drives P1.

## USB pads and EasySMX controllers

Both builds now share the same pad logic: `Scripts/Core/Input/PadLayout.cs` (desktop, C#) and
`Web/Controllers.gd` (browser, GDScript, pure rules + Godot-backed polling). `Scripts/Godot/Controls.cs`
is the desktop adapter; `Tests/gd/test_pads.gd`, `Tools/test_pads.py` and the PadLayout section of
`Tests/Program.cs` test both.

* **The bundled SDL database is loaded at boot.** `Data/input/gamecontrollerdb.txt` is fed to
  `Input.add_joy_mapping()` / `Input.AddJoyMapping()` before the first poll, filtered to the current OS
  (Windows / Linux / macOS / Android / iOS). It already contains the Windows `EasySMX Controller`, the
  Linux `EasySMX` and `EasySMX ESM-9101`, and several generic `USB Controller` GUIDs. Those six lines are
  also compiled into both code paths as a fallback, so an export missing the `.txt` still recognises them.
  Browser Gamepad API IDs carry no OS tag, so the Web build registers all six built-ins regardless of
  their `platform:` tag. All export presets now include `Data/input/*.txt` in the PCK.
* **Every connected pad is discovered.** The old code hard-coded device 0, so a pad enumerated at 2 or 5
  (common after a reconnect or with a wireless dongle) was ignored. In one-player mode all pads drive P1;
  in the browser's 2-player mode pad 1 drives P1 and pad 2 drives P2.
* **Unmapped pads use the real EasySMX D-input order.** An EasySMX pad in "PC"/D-input mode (and most
  cheap USB boxes) arrives as an unmapped joystick with `b0=Y, b1=B, b2=A, b3=X, b4=LB, b5=RB, b6=LT,
  b7=RT, b8=Back, b9=Start, b10=L3, b11=R3`. The previous raw table wrongly assumed the standard
  A/B/X/Y order. The D-pad is read as Godot's d-pad buttons 11-14, as browser raw buttons 12-15 when
  those are the ones being pressed, or as hat axes 6/7 (only one button table is used at a time, since
  the two index ranges overlap). Triggers work as buttons or analogue axes.
* **XInput mode** (hold the mode button / use the 2.4G dongle) presents the pad as an Xbox controller and
  gets the standard layout automatically.
* **The main menu is controllable without a mouse.** The first menu button takes GUI focus on boot, so
  arrow keys + Enter/Space work immediately; a pad's d-pad or left stick moves the highlight and A or
  Start selects. `BrowserBoot.menu_focus_step()` is a pure helper covered by
  `Tests/gd/test_input_camera.gd`.
* **Camera angles work from a pad.** `Controllers.held()` has always reported the `camera` system button
  (R3 on a mapped pad, L3 on a raw EasySMX pad) but the browser edition ignored it. It now cycles the
  broadcast / telephoto / player / tactical views just like `C` or `1`-`4`; the HUD `CAM` button and
  wheel / `+` / `-` zoom are unchanged.
* **Every desktop menu is playable without a mouse.** `Ui.Style()` used to force `FocusMode.None` on
  every Button, so the main menu, pause menu, settings, controls, controller setup and character editor
  ignored arrow keys, Enter and the pad. Buttons are now focusable, each menu seeds focus on its first
  item, and `PadMenuNavigator` (on the Window, outside the menu/match swaps) walks focus with the d-pad /
  left stick, activates with A / Start and goes back with B. It uses the same `PadLayout` tables as
  gameplay, so unmapped EasySMX D-input pads work too. A / left-right also cycle combos and sliders.
* **Five camera angles.** `C` (or pad R3/L3) cycles Broadcast → Player cam → **Shoulder** (8.5 m high,
  13 m behind the controlled player, slightly off-axis) → **Sideline** (14 m / 24 m wide tracking) →
  Tactical (62 m top-down). Shoulder is the missing step between "right on top of the players" and the
  next view out; WASD is camera-relative in all five.
* **Pad menus select on the FIRST press.** A pad reported as "known" but actually sending raw
  D-input indices used to leave `A` unmapped; later, button 8 was both ACCEPT and BACK, so START
  appeared to do nothing. Menus now accept **any A/B/X/Y or START**, activate even when focus has
  just been seeded, focus only actionable widgets, and use the direct click callback. Back/Select
  alone goes back; R3 is gameplay camera only.
* **Button presses are no longer dropped.** Human one-shot actions used to be read only on the
  0.08–0.18 s AI decision clock, so a normal tap was usually discarded. They are now consumed on
  every fixed tick and buffered across physics frames that produce no tick. The human also no longer
  auto-runs toward goal when the stick is released.
* **Full action set (desktop):** `E`/A **short pass**, `R`/pad Back **long ball / cross**,
  `SPACE`/pad X **shoot (hold to charge)**, `Q`/pad Y **through ball**, `F`/pad B **standing
  tackle**, `SHIFT+F` / pad RB+B **slide tackle**, `X` / pad LT or L3 **close-control dribble +
  shield**, `TAB` / pad LB **switch**, `C` / pad R3 **camera**, `ESC` / Start **pause**.
  `SHIFT` / RB / RT **sprint** is now 1.42× with stronger acceleration; sprinting into a carrier
  also triggers a **shoulder-charge strength contest**. First-touch pass / shoot / long ball work
  within 1.6 m of a loose ball. LT and RT are now separate actions instead of both meaning sprint.
* **Remap** from **CONTROLLER SETUP** in the main menu (desktop and browser): *Remap pad 1/2*, then press
  the button asked for each action. Bindings are saved per pad name in `user://pads.json` (IndexedDB in
  the browser) and restored next time. The screen also lists each pad's name, detected kind and current
  button numbers.
* Plug the pad in and press any button once — Windows and browsers hide a gamepad until it is used.

Tests: `python3 Tools/test_pads.py` (runs without Godot/.NET, see below), `Tools/run-gd-tests.sh` and
`python3 Tools/build.py --check`. These cover mapping parsing/platform filtering, the raw EasySMX
layout, dead zones, d-pad/hat/trigger handling, remapping and device discovery. Physical hardware still
needs a manual check; the remap screen covers adapters whose button order differs.

## Online play and where the C# server goes

Online play uses the **same Node hub** as the other games, but the hub cannot run Arena FC's simulation:
the hub's relay is a two-player bit-exact lockstep relay, while Arena FC is server-authoritative with up to
four humans, rollback and a full C# match simulation. So the hub is the *front door* and the C# server
stays a separate process:

```
browser --https--> Node hub (shared/netplay/server)  --ws://127.0.0.1:7777--> .NET Arena FC server
```

One container runs both (`arena-fc/option-b/Dockerfile`, `start.sh`), so you deploy **one service**:

| Host | Notes |
| --- | --- |
| **Fly.io** (good fit) | `fly launch` with the Dockerfile, one shared-cpu VM, `internal_port = 10000`, TLS handled for you, WebSockets work without extra config. |
| **Render** | `option-b/render.yaml` blueprint; needs a paid Docker web service (free tier sleeps and drops sockets). |
| **Railway / any VPS (Hetzner, DigitalOcean)** | `docker run -p 10000:10000`, put Caddy or nginx in front for HTTPS (`wss://` is required from an https page). |

Set `TRUST_PROXY=1` behind any of these, and `ARENA_ALLOWED_ORIGINS` to your site's origin.

**No .NET needed any more:** `arena-fc/ARENA_NODE.md` describes a Node port of the match that runs inside the same hub
(`ARENA_NATIVE=1`, `arena-fc/option-a/Dockerfile`). It speaks the same protocol, passes the existing protocol
tests and serves the browser build, so you can deploy the whole thing on your existing Node service. The C#
`.NET` server is now restored too: `Scripts/Core/Net/*.cs` was rebuilt from the checked-in wire format
(see `MISSING_NET_SOURCES.md`); it builds on .NET 9 and is used by the desktop C# clients.

## Browser preview without a Godot editor

`python3 Tools/serve_wasm_preview.py --port 8080` builds the GDScript-only browser edition into
`build/wasm_preview/` and serves it on `0.0.0.0:8080` using the Godot 4.7.2 WebAssembly runtime from
npm (`@ringozz/godot-web-wasm32`). The first run needs `npm` on PATH to fetch the engine; later runs use
the cache in `~/.cache/arena-fc/wasm`.

**The canvas must have focus.** Godot's Web build attaches `keydown`/`keyup` to the canvas element, not to
`window`, so the generated page uses `<canvas tabindex="0">` and focuses it on load and on pointer-down.
An unfocused canvas silently swallows every WASD / `C` / `1`-`4` key, which looks like broken controls
and broken camera angles. Click the game once if focus was lost (e.g. after using another iframe).

This WASM runtime is a Web *template* build with no `WebSocketPeer` or glTF module. Online play and GLB
import are therefore unavailable in the preview; use the native/editor builds for those. `Web/NetClient.gd`
and `Scripts/Godot/ProceduralRig3D.gd` resolve those optional classes through `ClassDB` at runtime, so the
scripts still parse there — player rigs load from `Data/rig_default.json` and all five GDScript suites pass
in the WASM engine. The desktop C# game also cannot run in this runtime (Godot cannot export C# to Web).

## Match feel (desktop C#)

* **Opposition presses and tackles.** When the other team has the ball, three players (not two) close
  down the carrier: the nearest leads him, the other two cut the lane to goal. Pressing defenders get a
  12% pace / acceleration boost, tackle attempts are more frequent, and the tackle cooldown is shorter.
  In a deterministic 60 s 11v11 sim (seed 2026) successful tackles went from 7 to 16 and the number of
  ticks with a defender within 2 m of the carrier from 579 to 740.
* **Rounded joints and shaped boots.** The procedural 18-bone rig now has hip, knee, ankle, shoulder,
  elbow and wrist spheres, shorts/sock kit bands, a boot toe box, a dark sole and a coloured stripe, plus
  rim/specular materials so the joints read as separate volumes instead of one straight cylinder.
* **Smoother gait, correct direction.** `Scripts/Core/Gait.cs` is now the single, pure-C# gait curve
  used by `RigAnimator.Pose` (and mirrored in `BrowserBoot.animate_rig`). A leg bone points down, so a
  **negative** X rotation swings it forward and a **positive** knee angle folds the shin back — the old
  positive thigh angles kicked the legs out behind the player and made knees look locked. Knees now bend
  even while walking, ankles counter-rotate, and the stride has harmonic hip swing, torso twist, lean,
  head stabilisation and a two-bounce weight shift. `Tests/MatchCoreTests.cs` asserts the sign convention.
* **Fewer phantom free kicks.** Failed tackles only become fouls within 1.7 m (2.6 m for a slide) and at
  12% / 30% instead of every miss at 2 m at ~18%. The fouled player now visibly stumbles (`foul` pose),
  the slider has its own low `slide` pose, and the HUD shows `FOUL · FREE KICK` / `FOUL · PENALTY!`.
  In the deterministic 60 s sim, free kicks dropped from 4 invisible ones to 1.
* **Less bunching.** Personal space went from 0.62 m to 1.05 m with a stronger push, non-carriers are
  nudged out of the carrier's immediate space (but **never** away from a loose ball — otherwise nobody
  can pick it up), and the two supporting pressers now take opposite wings instead of the same point.
  Average players within 4 m of the ball: 2.62 → 2.24.
* **Auto-selected controlled player.** When the home side has the ball the ring goes to the carrier;
  otherwise it moves to the nearest outfielder if that player is ≥1.6 m closer. TAB switching gets a
  1.2 s lock so auto-select does not fight you. This is why pass/tackle previously felt dead.

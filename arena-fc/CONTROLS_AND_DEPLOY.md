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
server stays blocked on the missing `Scripts/Core/Net/*.cs` and is only needed for the desktop 11-a-side game.

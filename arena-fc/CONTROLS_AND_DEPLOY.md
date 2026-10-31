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

## USB pads and generic adapters (SMX-style)

* Desktop builds read pads through Godot/SDL. The web build uses the browser Gamepad API: plug the pad in,
  then press any button once (browsers hide a pad until it is used).
* Pads Godot recognises use the standard layout. **Unknown adapters** (the cheap USB boxes that report as
  a generic joystick) use the raw layout: buttons 0-3 face buttons, 4/5 shoulders, axes 0/1 stick, axes
  6/7 D-pad.
* If a button is in the wrong place: **CONTROLLER SETUP** in the main menu -> *Remap pad 1/2*, then press
  the button asked for each action. Bindings are saved per pad name (`user://pads.json`; in the browser
  that is IndexedDB) and restored next time.
* `Web/Controllers.gd` holds all of this and is covered by `Tests/gd/test_rules.gd` (dead zone, binding tables).
  I could not test with a physical SMX adapter here: the generic/raw path follows the common layout, and
  the remap screen exists for any adapter that differs.

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

**Blocker:** `Scripts/Core/Net/*.cs` (the server's protocol and snapshot types) are missing from the
repository (see `MISSING_NET_SOURCES.md`), so the .NET server cannot be built until they are restored. If
they cannot be found, the alternative is a Node-side authoritative server, i.e. port the match simulation
(`Match.cs`, or the simpler browser sim in `Web/BrowserBoot.gd` + `Web/MatchRules.gd`) to JavaScript and run
it inside the hub. That is a real piece of work but it would let everything run on the existing Node
deployment with no .NET at all.

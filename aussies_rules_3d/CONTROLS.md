# Controls — every device, one game

Aussie Rules 3D uses a single device-agnostic action layer
(`src/input/mappings.ts`): keyboard, mouse, gamepads and touch all resolve to
the same game actions, so the game plays identically everywhere. Two players
can play on the same device (keyboard + gamepad, or two gamepads).

## Keyboard

| Key | Action |
|---|---|
| **W A S D** / Arrow keys | Move |
| **Space** (hold & release) | Kick — hold to charge power; in a set shot, hold and aim |
| **E** | Handball |
| **F** | Tackle / contest / smother attempt |
| **Shift** | Sprint |
| **Q** or **Tab** | Switch player (defence) |
| **B** | Bounce the ball |
| **Z / X** | Bend a set shot (left / right) |
| **C** | Cycle camera (broadcast → wing → chase → aerial → tactical) |
| **V** | Toggle player rings / markers |
| **Esc** | Pause / back |

## Gamepad (standard mapping — Xbox / PlayStation / Switch Pro / Stadia)

| Button | Action |
|---|---|
| **Left stick** / **D-pad** | Move |
| **Right stick (X)** | Set-shot aim (bends the shot) |
| **A / Cross** | Kick (hold to charge) |
| **B / Circle** | Handball |
| **X / Square** | Tackle / contest |
| **Y / Triangle** | Switch player |
| **LB / L1** | Bounce |
| **RB / R1** or **RT / R2** | Sprint |
| **Start / Options** | Pause |
| **L3 / R3** | Cycle camera |
| **Back / Select** | Menu navigation: back (in a menu, quits to menu from pause) |
| **Left stick (Y)** / **D-pad** (in menus) | Move focus between buttons |
| **A / Cross** (in menus) | Select the focused menu button |
| **B / Circle** (in menus) | Back to the previous screen |

Rumble is supported on controllers that expose the standard vibration actuator
(tackles, goals). Any browser-standard gamepad works — no setup needed.

## Touch (phone, tablet, touchscreen laptops)

| Control | Action |
|---|---|
| **Left half of the screen** — virtual stick | Move |
| **KICK** (hold & release) | Kick / set shot |
| **HAND** | Handball |
| **TACKLE** | Tackle / contest |
| **SPRINT** | Sprint |
| **SWITCH** | Switch player |

The touch UI appears automatically on touch devices; buttons are large,
thumb-friendly and safe-area aware. The device vibrates on big hits.

## Local multiplayer

Player 1 uses keyboard (or gamepad 0) / touch. Player 2 joins on **gamepad 1**
and plays on the same team with their own controlled player.

## Test & input parity

The input layer is covered by the same test matrix as the
`gaelic_football_3d` project: unit tests for every keyboard mapping, the
standard gamepad layout (face buttons, triggers, bumpers, d-pad, menu
buttons), stick dead zones and radial scaling, edge detection, the touch
button layout and virtual-stick geometry (`tests/input.spec.ts`), plus
controller support (Gamepad API with rumble) and the shared action enum.
The rules/engine/sim test suites extend that parity with 86 tests total
(`npm test`).

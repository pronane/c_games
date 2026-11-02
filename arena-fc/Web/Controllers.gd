# Controllers.gd - browser-edition wrapper around Web/PadSupport.gd.
#
# PadSupport.gd owns all USB / EasySMX / generic joystick handling (SDL mappings,
# raw EasySMX D-input layout, remapping and device discovery).  This script keeps
# the keyboard schemes and the small compatibility surface used by BrowserBoot.gd
# and by the headless tests (C.stick, C.RAW, C.ACTIONS, ...).
extends "res://Web/PadSupport.gd"

# ---- keyboard schemes (physical keycodes) ---------------------------------------------------------
## P1 shares the classic layout; in two-player mode P1 keeps WASD and P2 gets the arrow cluster.
const KB_P1 := {"left": KEY_A, "right": KEY_D, "up": KEY_W, "down": KEY_S, "sprint": KEY_SHIFT, "pass": KEY_E,
	"through": KEY_Q, "shoot": KEY_SPACE, "tackle": KEY_F, "switch": KEY_TAB}
const KB_P2 := {"left": KEY_LEFT, "right": KEY_RIGHT, "up": KEY_UP, "down": KEY_DOWN, "sprint": KEY_SLASH,
	"pass": KEY_COMMA, "through": KEY_L, "shoot": KEY_PERIOD, "tackle": KEY_SEMICOLON, "switch": KEY_APOSTROPHE}

## Dead-zone helper kept for Tests/gd/test_rules.gd and any older callers.
static func stick(x: float, y: float) -> Vector2:
	var s := stick_xy(x, y, DEADZONE)
	return Vector2(float(s[0]), float(s[1]))

static func kb_move(scheme: Dictionary, include_arrows: bool) -> Vector2:
	var m := Vector2.ZERO
	if Input.is_key_pressed(scheme["left"]) or (include_arrows and Input.is_key_pressed(KEY_LEFT)): m.x -= 1
	if Input.is_key_pressed(scheme["right"]) or (include_arrows and Input.is_key_pressed(KEY_RIGHT)): m.x += 1
	if Input.is_key_pressed(scheme["up"]) or (include_arrows and Input.is_key_pressed(KEY_UP)): m.y -= 1
	if Input.is_key_pressed(scheme["down"]) or (include_arrows and Input.is_key_pressed(KEY_DOWN)): m.y += 1
	return m

static func kb_held(scheme: Dictionary) -> Dictionary:
	var out := {}
	for a in ACTIONS:
		out[a] = Input.is_key_pressed(scheme[a])
	return out

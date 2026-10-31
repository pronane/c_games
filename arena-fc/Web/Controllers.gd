# Controllers.gd — USB / Bluetooth gamepads and keyboard schemes for local play.
#
# * Works with anything the OS (desktop) or the browser Gamepad API (web) exposes: Xbox/PlayStation pads,
#   generic USB pads and cheap adapter boxes (the "SMX"-style ones that show up as an unmapped joystick).
# * Known pads use Godot's standard layout. Unknown pads fall back to the raw layout most adapters share
#   (buttons 0-3 face, 4/5 shoulders, axes 0/1 stick, hat or axes 6/7 as d-pad) and can be remapped in
#   the CONTROLLER SETUP screen. Bindings are remembered per pad name in user://pads.json.
# * Nothing here touches the scene tree, so it is unit-tested headless.
extends RefCounted

const ACTIONS := ["pass", "through", "shoot", "tackle", "switch", "sprint"]
const SAVE_PATH := "user://pads.json"
const DEADZONE := 0.25

# standard layout (Godot JoyButton indices): A, Y, X, B, LB, RB
const STANDARD := {"pass": 0, "through": 3, "shoot": 2, "tackle": 1, "switch": 9, "sprint": 10}
# raw layout used by generic adapters (no SDL mapping): 0..3 face, 4/5 shoulders
const RAW := {"pass": 0, "through": 3, "shoot": 2, "tackle": 1, "switch": 4, "sprint": 5}

var binds_by_name: Dictionary = {}          # pad name -> {action: button index}

func load_saved() -> void:
	if not FileAccess.file_exists(SAVE_PATH):
		return
	var f := FileAccess.open(SAVE_PATH, FileAccess.READ)
	if f == null:
		return
	var parsed = JSON.parse_string(f.get_as_text())
	if parsed is Dictionary:
		for k in parsed:
			if parsed[k] is Dictionary:
				var b := {}
				for a in ACTIONS:
					if parsed[k].has(a):
						b[a] = int(parsed[k][a])
				if b.size() == ACTIONS.size():
					binds_by_name[str(k)] = b

func save() -> void:
	var f := FileAccess.open(SAVE_PATH, FileAccess.WRITE)
	if f != null:
		f.store_string(JSON.stringify(binds_by_name))

func pad_name(dev: int) -> String:
	return Input.get_joy_name(dev)

func is_known(dev: int) -> bool:
	return Input.is_joy_known(dev)

## Bindings in force for `dev`: the user's remap, else standard (known pads) or raw (unknown adapters).
func binds_for(dev: int) -> Dictionary:
	var n := pad_name(dev)
	if binds_by_name.has(n):
		return binds_by_name[n]
	return (STANDARD if is_known(dev) else RAW).duplicate()

func set_bind(dev: int, action: String, button: int) -> void:
	var n := pad_name(dev)
	var b: Dictionary = binds_for(dev).duplicate()
	b[action] = button
	binds_by_name[n] = b

func reset_binds(dev: int) -> void:
	binds_by_name.erase(pad_name(dev))

## Pads that are plugged in, in device order.
func pads() -> Array:
	return Input.get_connected_joypads()

## Apply a dead zone and rescale so small drift never moves the player.
static func stick(x: float, y: float) -> Vector2:
	var v := Vector2(x, y)
	var l := v.length()
	if l < DEADZONE:
		return Vector2.ZERO
	return v.normalized() * minf(1.0, (l - DEADZONE) / (1.0 - DEADZONE))

## Left stick + d-pad of pad `dev` as a movement vector (x right, y down).
func move_of(dev: int) -> Vector2:
	var m := stick(Input.get_joy_axis(dev, JOY_AXIS_LEFT_X), Input.get_joy_axis(dev, JOY_AXIS_LEFT_Y))
	var d := Vector2.ZERO
	if Input.is_joy_button_pressed(dev, JOY_BUTTON_DPAD_LEFT): d.x -= 1
	if Input.is_joy_button_pressed(dev, JOY_BUTTON_DPAD_RIGHT): d.x += 1
	if Input.is_joy_button_pressed(dev, JOY_BUTTON_DPAD_UP): d.y -= 1
	if Input.is_joy_button_pressed(dev, JOY_BUTTON_DPAD_DOWN): d.y += 1
	if not is_known(dev):
		# many adapters report the d-pad as axes 6/7 (or the hat on 9) instead of buttons
		var hx := Input.get_joy_axis(dev, 6)
		var hy := Input.get_joy_axis(dev, 7)
		if absf(hx) > 0.5: d.x += signf(hx)
		if absf(hy) > 0.5: d.y += signf(hy)
	var out := m + d
	return out.normalized() if out.length() > 1.0 else out

## Held state of every action on pad `dev`.
func held(dev: int) -> Dictionary:
	var b := binds_for(dev)
	var out := {}
	for a in ACTIONS:
		out[a] = Input.is_joy_button_pressed(dev, int(b[a]))
	# analogue triggers also sprint
	if Input.get_joy_axis(dev, JOY_AXIS_TRIGGER_RIGHT) > 0.5 or Input.get_joy_axis(dev, JOY_AXIS_TRIGGER_LEFT) > 0.5:
		out["sprint"] = true
	return out

# ---- keyboard schemes (physical keycodes) ---------------------------------------------------------
## P1 shares the classic layout; in two-player mode P1 keeps WASD and P2 gets the arrow cluster.
const KB_P1 := {"left": KEY_A, "right": KEY_D, "up": KEY_W, "down": KEY_S, "sprint": KEY_SHIFT, "pass": KEY_E,
	"through": KEY_Q, "shoot": KEY_SPACE, "tackle": KEY_F, "switch": KEY_TAB}
const KB_P2 := {"left": KEY_LEFT, "right": KEY_RIGHT, "up": KEY_UP, "down": KEY_DOWN, "sprint": KEY_SLASH,
	"pass": KEY_COMMA, "through": KEY_L, "shoot": KEY_PERIOD, "tackle": KEY_SEMICOLON, "switch": KEY_APOSTROPHE}

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

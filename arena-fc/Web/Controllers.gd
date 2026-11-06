# Controllers.gd - gamepad + keyboard input for the Arena FC browser edition.
#
# USB / EasySMX support lives here (pure rules + Godot-backed polling); the desktop
# C# twin is Scripts/Core/Input/PadLayout.cs.  Everything between PURE START / PURE
# END is deliberately written in a small side-effect-free subset of GDScript so
# Tools/test_pads.py can execute it without Godot (it translates that block to
# Python).  Keep that block free of Input/FileAccess/SceneTree calls.
#
# The bundled SDL database is loaded at boot, every connected pad is discovered,
# and pads Godot cannot map are read with the EasySMX D-input button order.
extends RefCounted

# ---- PURE START ----
const DEADZONE := 0.25
const DB_PATH := "res://Data/input/gamecontrollerdb.txt"
const SAVE_PATH := "user://pads.json"
const ACTIONS := ["pass", "through", "shoot", "tackle", "switch", "sprint"]

# Godot JoyButton order for a pad with an SDL mapping (Xbox / XInput).
const STANDARD := {"pass": 0, "through": 3, "shoot": 2, "tackle": 1, "switch": 9, "sprint": 10}
# EasySMX D-input / PC mode and most cheap USB pads (b0=Y b1=B b2=A b3=X ...).
const RAW := {"pass": 2, "through": 0, "shoot": 3, "tackle": 1, "switch": 4, "sprint": 5}
const SYSTEM_STANDARD := {"pause": 6, "camera": 8}
const SYSTEM_RAW := {"pause": 9, "camera": 11}
const DPAD_STANDARD := {"up": 11, "down": 12, "left": 13, "right": 14}
const DPAD_RAW := {"up": 12, "down": 13, "left": 14, "right": 15}
const HAT_AXES := [6, 7]
const TRIGGER_AXES := [4, 5]
const TRIGGER_BUTTONS := [6, 7]
const STICK_AXES := [0, 1]
const EASYSMX_TOKENS := ["easysmx", "easy smx", "esm-", "esm_"]
const GENERIC_TOKENS := ["usb", "generic", "gamepad", "controller", "joystick", "adapter", "shanwan", "szmy", "esm"]

# Always available, even when the .txt database is missing from an export.
# Copied verbatim from Data/input/gamecontrollerdb.txt (SDL 2.0.16 format).
const BUILTIN := [
"03000000bc2000000091000000000000,EasySMX Controller,a:b2,b:b1,back:b8,dpdown:h0.4,dpleft:h0.8,dpright:h0.2,dpup:h0.1,leftshoulder:b4,leftstick:b10,lefttrigger:b6,leftx:a0,lefty:a1,rightshoulder:b5,rightstick:b11,righttrigger:b7,rightx:a2,righty:a3,start:b9,x:b3,y:b0,platform:Windows,",
"03000000c11100000191000011010000,EasySMX,a:b2,b:b1,back:b8,dpdown:h0.4,dpleft:h0.8,dpright:h0.2,dpup:h0.1,leftshoulder:b4,leftstick:b10,lefttrigger:b6,leftx:a0,lefty:a1,rightshoulder:b5,rightstick:b11,righttrigger:b7,rightx:a2,righty:a3,start:b9,x:b3,y:b0,platform:Linux,",
"03000000242f00009100000000010000,EasySMX ESM-9101,a:b0,b:b1,back:b6,dpdown:h0.4,dpleft:h0.8,dpright:h0.2,dpup:h0.1,guide:b8,leftshoulder:b4,leftstick:b9,lefttrigger:a2,leftx:a0,lefty:a1,rightshoulder:b5,rightstick:b10,righttrigger:a5,rightx:a3,righty:a4,start:b7,x:b2,y:b3,platform:Linux,",
"030000000b0400003065000000000000,USB Controller,a:b2,b:b1,back:b8,dpdown:h0.4,dpleft:h0.8,dpright:h0.2,dpup:h0.1,leftshoulder:b4,leftstick:b10,lefttrigger:b6,leftx:a0,lefty:a1,rightshoulder:b5,rightstick:b11,righttrigger:b7,rightx:a2,righty:a5,start:b9,x:b3,y:b0,platform:Windows,",
"03000000300f00000701000000000000,USB Controller,a:b2,b:b1,back:b8,dpdown:h0.4,dpleft:h0.8,dpright:h0.2,dpup:h0.1,leftshoulder:b4,leftstick:b10,lefttrigger:b6,leftx:a0,lefty:a1,rightshoulder:b5,rightstick:b11,righttrigger:b7,rightx:a3,righty:a2,start:b9,x:b3,y:b0,platform:Windows,",
"030000006b1400000203000000000000,USB Controller,a:b0,b:b1,back:b8,dpdown:h0.4,dpleft:h0.8,dpright:h0.2,dpup:h0.1,guide:b12,leftshoulder:b4,leftstick:b10,lefttrigger:b6,leftx:a0,lefty:a1,rightshoulder:b5,rightstick:b11,righttrigger:b7,rightx:a2,righty:a3,start:b9,x:b2,y:b3,platform:Windows,"
]

# ---- keyboard schemes (physical keycodes) ---------------------------------------------------------
## P1 shares the classic layout; in two-player mode P1 keeps WASD and P2 gets the arrow cluster.
const KB_P1 := {"left": KEY_A, "right": KEY_D, "up": KEY_W, "down": KEY_S, "sprint": KEY_SHIFT, "pass": KEY_E,
	"through": KEY_Q, "shoot": KEY_SPACE, "tackle": KEY_F, "switch": KEY_TAB}
const KB_P2 := {"left": KEY_LEFT, "right": KEY_RIGHT, "up": KEY_UP, "down": KEY_DOWN, "sprint": KEY_SLASH,
	"pass": KEY_COMMA, "through": KEY_L, "shoot": KEY_PERIOD, "tackle": KEY_SEMICOLON, "switch": KEY_APOSTROPHE}

# Instance state (after all constants, before any method - gdlint definition order).
var binds_by_name: Dictionary = {}
var mappings_loaded: int = -1

static func normalize_platform(p: String) -> String:
	var q = p.to_lower().strip_edges()
	if q == "mac os x" or q == "macos" or q == "osx" or q == "darwin" or q == "mac":
		return "macos"
	if q == "windows" or q == "win32" or q == "win64" or q == "win":
		return "windows"
	if q == "linux" or q == "linuxbsd" or q == "x11" or q == "xorg":
		return "linux"
	if q == "web" or q == "html5":
		return "web"
	return q

static func mapping_platform(line: String) -> String:
	var tag = ""
	for part in line.split(",", false):
		var s = str(part).strip_edges()
		if s.begins_with("platform:"):
			tag = s.replace("platform:", "")
	return normalize_platform(tag)

static func platform_matches(line: String, platform: String) -> bool:
	var tag = mapping_platform(line)
	if tag == "":
		return true
	return tag == normalize_platform(platform)

static func valid_mapping(line: String) -> bool:
	var parts = line.split(",", false)
	if parts.size() < 4:
		return false
	var guid = str(parts[0]).strip_edges()
	return guid.length() == 32

static func parse_db(text: String, platform: String) -> Array:
	var out = []
	for raw in text.split("\n"):
		var line = str(raw).strip_edges()
		if line == "" or line.begins_with("#"):
			continue
		if not valid_mapping(line):
			continue
		if not platform_matches(line, platform):
			continue
		out.append(line)
	return out

static func builtin_mappings(platform: String) -> Array:
	var out = []
	# Browser Gamepad API IDs do not carry an OS tag: keep every built-in line
	# on Web so EasySMX / USB fallbacks are always registered there.
	var web = normalize_platform(platform) == "web"
	for line in BUILTIN:
		if web or platform_matches(str(line), platform):
			out.append(str(line))
	return out

static func has_token(name: String, tokens: Array) -> bool:
	var low = name.to_lower()
	for t in tokens:
		if low.find(str(t)) >= 0:
			return true
	return false

static func is_easysmx(name: String) -> bool:
	return has_token(name, EASYSMX_TOKENS)

static func is_generic_usb(name: String) -> bool:
	return has_token(name, GENERIC_TOKENS)

static func pad_kind(name: String, known: bool) -> String:
	if is_easysmx(name):
		return "EasySMX (XInput)" if known else "EasySMX (USB / D-input)"
	if is_generic_usb(name):
		return "USB gamepad" if known else "USB controller (raw)"
	return "Standard gamepad" if known else "Unknown joystick (raw)"

static func binds_for_name(name: String, known: bool, saved: Dictionary) -> Dictionary:
	if name in saved:
		var b: Dictionary = saved[name]
		var complete = true
		for a in ACTIONS:
			if not (a in b):
				complete = false
		if complete:
			return b.duplicate()
	if known:
		return STANDARD.duplicate()
	return RAW.duplicate()

static func axis_of(axes: Array, i: int) -> float:
	if i < 0 or i >= axes.size():
		return 0.0
	return float(axes[i])

static func button_of(buttons: Array, i: int) -> bool:
	if i < 0 or i >= buttons.size():
		return false
	return bool(buttons[i])

static func vec_len(x: float, y: float) -> float:
	return sqrt(x * x + y * y)

static func stick_xy(x: float, y: float, dz: float) -> Array:
	var l = vec_len(x, y)
	if l < dz:
		return [0.0, 0.0]
	var scale = min(1.0, (l - dz) / (1.0 - dz)) / l
	return [x * scale, y * scale]

static func gd_sign(v: float) -> float:
	if v > 0.0:
		return 1.0
	if v < 0.0:
		return -1.0
	return 0.0

static func move_xy(buttons: Array, axes: Array, known: bool, dz: float) -> Array:
	var s = stick_xy(axis_of(axes, STICK_AXES[0]), axis_of(axes, STICK_AXES[1]), dz)
	# Godot desktop drivers expose a hat as DPAD_* (11-14); the browser Gamepad
	# API exposes it as raw buttons 12-15.  Those ranges overlap, so pick ONE
	# table - OR-ing both would make button 12 mean up AND down.
	var dpad = DPAD_STANDARD
	if not known:
		var raw_hat = false
		for k in DPAD_RAW:
			if button_of(buttons, int(DPAD_RAW[k])):
				raw_hat = true
		if raw_hat:
			dpad = DPAD_RAW
	var dx = 0.0
	var dy = 0.0
	if button_of(buttons, dpad["left"]): dx -= 1.0
	if button_of(buttons, dpad["right"]): dx += 1.0
	if button_of(buttons, dpad["up"]): dy -= 1.0
	if button_of(buttons, dpad["down"]): dy += 1.0
	if not known:
		var hx = axis_of(axes, HAT_AXES[0])
		var hy = axis_of(axes, HAT_AXES[1])
		if abs(hx) > 0.5: dx += gd_sign(hx)
		if abs(hy) > 0.5: dy += gd_sign(hy)
	var ox = float(s[0]) + dx
	var oy = float(s[1]) + dy
	var l = vec_len(ox, oy)
	if l > 1.0:
		return [ox / l, oy / l]
	return [ox, oy]

static func held_from(buttons: Array, axes: Array, binds: Dictionary, known: bool) -> Dictionary:
	var out = {}
	for a in ACTIONS:
		out[a] = button_of(buttons, int(binds.get(a, -1)))
	var sys = SYSTEM_STANDARD if known else SYSTEM_RAW
	out["pause"] = button_of(buttons, int(sys["pause"]))
	out["camera"] = button_of(buttons, int(sys["camera"]))
	# Back/Select = long ball; LT/L3 = close control; RT/RB = sprint.
	out["lob"] = button_of(buttons, 4 if known else 8)
	out["dribble"] = axis_of(axes, TRIGGER_AXES[0]) > 0.5 or button_of(buttons, 7 if known else 10)
	var sprint = bool(out["sprint"])
	if axis_of(axes, TRIGGER_AXES[1]) > 0.5:
		sprint = true
	if not known:
		if button_of(buttons, int(TRIGGER_BUTTONS[0])):
			out["dribble"] = true
		if button_of(buttons, int(TRIGGER_BUTTONS[1])):
			sprint = true
	out["sprint"] = sprint
	return out

static func devices_for(connected: Array, two_player: bool, player: int) -> Array:
	if connected.size() == 0:
		return []
	if not two_player:
		return connected.duplicate()
	if player < connected.size():
		return [int(connected[player])]
	return []
# ---- PURE END ----

## Dead-zone helper kept for Tests/gd/test_rules.gd and any older callers.
static func stick(x: float, y: float) -> Vector2:
	var s = stick_xy(x, y, DEADZONE)
	return Vector2(float(s[0]), float(s[1]))

static func kb_move(scheme: Dictionary, include_arrows: bool) -> Vector2:
	var m = Vector2.ZERO
	if Input.is_key_pressed(scheme["left"]) or (include_arrows and Input.is_key_pressed(KEY_LEFT)): m.x -= 1
	if Input.is_key_pressed(scheme["right"]) or (include_arrows and Input.is_key_pressed(KEY_RIGHT)): m.x += 1
	if Input.is_key_pressed(scheme["up"]) or (include_arrows and Input.is_key_pressed(KEY_UP)): m.y -= 1
	if Input.is_key_pressed(scheme["down"]) or (include_arrows and Input.is_key_pressed(KEY_DOWN)): m.y += 1
	return m

static func kb_held(scheme: Dictionary) -> Dictionary:
	var out = {}
	for a in ACTIONS:
		out[a] = Input.is_key_pressed(scheme[a])
	return out

# ---- Engine-backed half (Godot Input / FileAccess) -------------------------------------------
func load_saved() -> void:
	if not FileAccess.file_exists(SAVE_PATH):
		return
	var f = FileAccess.open(SAVE_PATH, FileAccess.READ)
	if f == null:
		return
	var parsed = JSON.parse_string(f.get_as_text())
	if parsed is Dictionary:
		for k in parsed:
			if parsed[k] is Dictionary:
				var b = {}
				for a in ACTIONS:
					if parsed[k].has(a):
						b[a] = int(parsed[k][a])
				if b.size() == ACTIONS.size():
					binds_by_name[str(k)] = b

func save() -> void:
	var f = FileAccess.open(SAVE_PATH, FileAccess.WRITE)
	if f != null:
		f.store_string(JSON.stringify(binds_by_name))

## Feed the SDL database (plus the built-in EasySMX/USB fallbacks) to Godot.
## Call once at boot, BEFORE the first pad is polled.  Returns the number added.
func load_mappings(platform: String) -> int:
	var count = 0
	for line in builtin_mappings(platform):
		Input.add_joy_mapping(str(line), true)
		count += 1
	if FileAccess.file_exists(DB_PATH):
		var f = FileAccess.open(DB_PATH, FileAccess.READ)
		if f != null:
			for line in parse_db(f.get_as_text(), platform):
				Input.add_joy_mapping(str(line), true)
				count += 1
	mappings_loaded = count
	return count

func pads() -> Array:
	return Input.get_connected_joypads()

func pad_name(dev: int) -> String:
	return Input.get_joy_name(dev)

func is_known(dev: int) -> bool:
	return Input.is_joy_known(dev)

func binds_for(dev: int) -> Dictionary:
	return binds_for_name(pad_name(dev), is_known(dev), binds_by_name)

func set_bind(dev: int, action: String, button: int) -> void:
	var n = pad_name(dev)
	var b = binds_for(dev).duplicate()
	b[action] = button
	binds_by_name[n] = b

func reset_binds(dev: int) -> void:
	binds_by_name.erase(pad_name(dev))

## Raw snapshot of one pad; the pure functions above turn it into commands.
func snapshot(dev: int) -> Dictionary:
	var buttons = []
	for i in range(21):
		buttons.append(Input.is_joy_button_pressed(dev, i))
	var axes = []
	for i in range(10):
		axes.append(Input.get_joy_axis(dev, i))
	return {"buttons": buttons, "axes": axes}

func move_of(dev: int) -> Vector2:
	var s = snapshot(dev)
	var m = move_xy(s["buttons"], s["axes"], is_known(dev), DEADZONE)
	return Vector2(float(m[0]), float(m[1]))

func held(dev: int) -> Dictionary:
	var s = snapshot(dev)
	return held_from(s["buttons"], s["axes"], binds_for(dev), is_known(dev))

func start_pressed(dev: int) -> bool:
	return bool(held(dev)["pause"])

func pad_info(dev: int) -> String:
	var b = binds_for(dev)
	var head = "Pad %d: %s  [%s]" % [dev + 1, pad_name(dev), pad_kind(pad_name(dev), is_known(dev))]
	var binds = "   pass=%d  through=%d  shoot=%d  tackle=%d  switch=%d  sprint=%d" % [b["pass"], b["through"], b["shoot"], b["tackle"], b["switch"], b["sprint"]]
	return head + "\n" + binds

func describe() -> String:
	var lines = []
	lines.append("SDL mappings loaded: %d  |  pads connected: %d" % [mappings_loaded, pads().size()])
	if pads().is_empty():
		lines.append("No gamepad detected. Plug in a USB pad and press any button on it (browsers hide a pad until it is used).")
	for dev in pads():
		lines.append(pad_info(int(dev)))
	return "\n".join(PackedStringArray(lines))

# Headless test: main-menu control and camera angles for keyboard + USB/EasySMX pads.
# Run by Tools/run-gd-tests.sh (and Tools/build.py --check).
extends SceneTree

const B = preload("res://Web/BrowserBoot.gd")

var fails = 0

func ok(cond: bool, name: String) -> void:
	if cond:
		print("PASS ", name)
	else:
		fails += 1
		print("FAIL ", name)

## Stands in for Web/Controllers.gd so a pad can be simulated without hardware.
class FakePads extends RefCounted:
	var dir = Vector2.ZERO
	var buttons = {}
	func pads() -> Array:
		return [0]
	func move_of(_dev: int) -> Vector2:
		return dir
	func held(_dev: int) -> Dictionary:
		return {
			"pass": bool(buttons.get("pass", false)),
			"through": false, "shoot": false, "tackle": false,
			"switch": false, "sprint": false,
			"pause": bool(buttons.get("pause", false)),
			"camera": bool(buttons.get("camera", false)),
			"lob": false, "dribble": false,
		}
	func start_pressed(_dev: int) -> bool:
		return bool(buttons.get("pause", false))

func key(code: Key, down: bool) -> void:
	var ev = InputEventKey.new()
	ev.keycode = code
	ev.physical_keycode = code
	ev.pressed = down
	Input.parse_input_event(ev)
	# Events are buffered; let the main loop flush them before is_key_pressed().
	await process_frame

func _init() -> void:
	_run.call_deferred()
	_watchdog.call_deferred()

func _watchdog() -> void:
	await create_timer(90.0).timeout
	print("FAIL watchdog: test_input_camera.gd did not finish in 90s")
	quit(1)

func _run() -> void:
	print("== main menu / camera input ==")

	# Pure focus stepping: wrap-around, no movement on neutral or conflicting input.
	ok(B.menu_focus_step(0, 5, false, false) == 0, "neutral d-pad keeps menu focus")
	ok(B.menu_focus_step(0, 5, false, true) == 1, "d-pad down advances one menu item")
	ok(B.menu_focus_step(0, 5, true, false) == 4, "d-pad up wraps to the last item")
	ok(B.menu_focus_step(4, 5, false, true) == 0, "d-pad down wraps to the first item")
	ok(B.menu_focus_step(2, 5, true, true) == 2, "conflicting directions do not move focus")
	ok(B.menu_focus_step(7, 0, false, true) == 0, "empty menu is safe")

	var b = load("res://Web/BrowserMain.tscn").instantiate()
	root.add_child(b)
	await process_frame
	ok(b.menu_buttons.size() >= 5, "menu buttons are collected for pad/keyboard focus")
	ok(b.menu_focus == 0, "first menu button owns focus on boot")
	var focused: Control = root.get_viewport().gui_get_focus_owner()
	ok(focused is Button, "a Button really has GUI focus (arrow keys / Enter work)")

	var fake = FakePads.new()
	b.pad_ctl = fake

	# Pad d-pad / stick drives the menu; edge() gives one step per press.
	b.read_pad_menu()                       # clear edges
	fake.dir = Vector2(0, 1)
	b.read_pad_menu()
	ok(b.menu_focus == 1, "pad down moves the menu highlight")
	fake.dir = Vector2.ZERO
	b.read_pad_menu()                       # release
	fake.dir = Vector2(0, -1)
	b.read_pad_menu()
	ok(b.menu_focus == 0, "pad up moves the highlight back")

	# A / Start activates the highlighted menu button.
	var hits = []
	var first: Button = b.menu_buttons[0]
	first.pressed.connect(func(): hits.append(1))
	fake.dir = Vector2.ZERO
	b.read_pad_menu()                       # clear the accept edge
	fake.buttons["pass"] = true
	b.read_pad_menu()
	ok(hits.size() == 1, "pad A / Start presses the highlighted menu button")
	fake.buttons["pass"] = false
	b.read_pad_menu()

	# Camera angles: keyboard C / 1-4, the HUD CAM button, and the pad camera button.
	b.cam_mode = 0
	b.read_global_keys()                    # clear the 'cam' edge
	fake.buttons["camera"] = true
	b.read_global_keys()
	ok(b.cam_mode == 1, "pad camera button cycles the camera angle")
	fake.buttons["camera"] = false
	b.read_global_keys()
	fake.buttons["camera"] = true
	b.read_global_keys()
	ok(b.cam_mode == 2, "camera cycles again on the next press")
	fake.buttons["camera"] = false
	b.read_global_keys()

	b.cam_mode = 0
	b.read_global_keys()
	await key(KEY_C, true)
	b.read_global_keys()
	ok(b.cam_mode == 1, "C key cycles the camera angle")
	await key(KEY_C, false)
	b.read_global_keys()
	await key(KEY_3, true)
	b.read_global_keys()
	ok(b.cam_mode == 2, "number keys pick a camera angle directly")
	await key(KEY_3, false)
	b.read_global_keys()

	var zoom_before: float = b.cam_zoom
	await key(KEY_MINUS, true)
	b.read_global_keys()
	ok(b.cam_zoom > zoom_before, "minus key zooms out")
	await key(KEY_MINUS, false)
	b.read_global_keys()

	var cam_btn: Button = null
	for node in b.hud.find_children("*", "Button", true, false):
		if node is Button and node.text == "CAM":
			cam_btn = node
			break
	if cam_btn == null:
		# The headless desktop runner does not build the touch/web overlay on boot.
		# Construct it explicitly so the CAM wiring is still exercised there.
		b.build_touch(true)
		for node in b.hud.find_children("*", "Button", true, false):
			if node is Button and node.text == "CAM":
				cam_btn = node
				break
	var hud_kids = b.hud.get_child_count() if b.hud != null else -1
	ok(cam_btn != null, "HUD exposes an on-screen CAM button [hud=%s kids=%d web=%s touch=%s]" % [
		str(b.hud), hud_kids, str(OS.has_feature("web")),
		str(DisplayServer.is_touchscreen_available())])
	if cam_btn != null:
		var before: int = b.cam_mode
		cam_btn.emit_signal("pressed")
		ok(b.cam_mode == (before + 1) % b.cam_names.size(), "on-screen CAM button changes angle")

	print("RESULT fails=", fails)
	quit(1 if fails > 0 else 0)

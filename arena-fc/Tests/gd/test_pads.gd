extends SceneTree
# Headless tests for USB / EasySMX gamepad support (Web/PadSupport.gd + Web/Controllers.gd).
# Run with: GODOT=/path/to/godot Tools/run-gd-tests.sh
const P = preload("res://Web/PadSupport.gd")
const C = preload("res://Web/Controllers.gd")
var fails := 0

func ok(c: bool, msg: String) -> void:
	print(("PASS " if c else "FAIL ") + msg)
	if not c: fails += 1

func _init() -> void:
	_run.call_deferred()

func btns(pressed := []) -> Array:
	var b := []
	for i in range(21):
		b.append(false)
	for i in pressed:
		b[int(i)] = true
	return b

func axs(changes := {}) -> Array:
	var a := []
	for i in range(10):
		a.append(0.0)
	for k in changes:
		a[int(k)] = float(changes[k])
	return a

func _run() -> void:
	# ---- SDL mapping database ----
	var sample := "\n".join(PackedStringArray([
		"# Game Controller DB", "", P.BUILTIN[0], P.BUILTIN[3], P.BUILTIN[1],
		"not a mapping", "badguid,a:b0,platform:Windows,"]))
	var win := P.parse_db(sample, "Windows")
	var lin := P.parse_db(sample, "Linux")
	ok(win.size() == 2, "comments, blanks and invalid GUIDs are skipped (%d kept)" % win.size())
	var only_win := true
	for l in win:
		if not P.platform_matches(str(l), "Windows"): only_win = false
	ok(only_win, "Windows DB keeps only Windows / platform-agnostic lines")
	ok(lin.size() == 1, "Linux DB keeps only Linux lines")
	ok(P.normalize_platform("Mac OS X") == "macos" and P.normalize_platform("Windows") == "windows",
		"platform names normalise")
	ok(P.builtin_mappings("Windows").size() == 4 and P.builtin_mappings("Linux").size() == 2,
		"built-in fallback lines are platform-filtered")
	ok(P.builtin_mappings("Web").size() == P.BUILTIN.size(),
		"Web keeps every built-in fallback (browser IDs have no OS tag)")
	var win_easy := false
	for l in P.builtin_mappings("Windows"):
		if str(l).contains("EasySMX"): win_easy = true
	ok(win_easy, "built-in Windows fallback includes EasySMX")
	var lin_esm := false
	for l in P.builtin_mappings("Linux"):
		if str(l).contains("ESM-9101"): lin_esm = true
	ok(lin_esm, "built-in Linux fallback includes ESM-9101")
	if FileAccess.file_exists(P.DB_PATH):
		var f := FileAccess.open(P.DB_PATH, FileAccess.READ)
		var text := f.get_as_text()
		var pw := P.parse_db(text, "Windows")
		var pl := P.parse_db(text, "Linux")
		ok(pw.size() > 800 and pl.size() > 700, "shipped SDL DB parses (%d Windows / %d Linux)" % [pw.size(), pl.size()])
		var has_win_easy := false
		var has_usb := false
		for l in pw:
			if str(l).contains("EasySMX Controller"): has_win_easy = true
			if str(l).contains("USB Controller"): has_usb = true
		var has_lin_easy := false
		for l in pl:
			if str(l).contains("EasySMX"): has_lin_easy = true
		ok(has_win_easy and has_lin_easy and has_usb, "EasySMX and generic USB mappings are present")
		var all_builtin := true
		for l in P.BUILTIN:
			if not text.contains(str(l)): all_builtin = false
		ok(all_builtin, "every built-in fallback line comes from the shipped DB")
	else:
		ok(false, "shipped gamecontrollerdb.txt found")

	# ---- layouts and detection ----
	ok(C.ACTIONS.size() == 6 and C.RAW.size() == 6 and C.STANDARD.size() == 6,
		"binding tables cover every action")
	ok(C.RAW["pass"] == 2 and C.RAW["through"] == 0 and C.RAW["shoot"] == 3
		and C.RAW["tackle"] == 1 and C.RAW["switch"] == 4 and C.RAW["sprint"] == 5,
		"EasySMX D-input raw order is Y B A X / LB / RB")
	ok(C.STANDARD["pass"] == 0 and C.STANDARD["sprint"] == 10,
		"mapped pads use Godot's standard JoyButton order")
	ok(P.is_easysmx("EasySMX ESM-9101") and P.is_generic_usb("USB Controller")
		and not P.is_easysmx("Xbox One S Controller"), "EasySMX / USB names detected")
	ok(P.pad_kind("EasySMX", false).contains("D-input") and P.pad_kind("EasySMX", true).contains("XInput"),
		"pad kind reports the active mode")
	var saved := {"My USB pad": {"pass": 7, "through": 8, "shoot": 9, "tackle": 10, "switch": 11, "sprint": 12}}
	ok(P.binds_for_name("My USB pad", false, saved)["pass"] == 7, "saved per-pad remap wins")
	ok(P.binds_for_name("Other", false, {"Other": {"pass": 7}})["through"] == 0,
		"incomplete remap falls back to the default")

	# ---- pure input processing ----
	ok(C.stick(0.1, 0.1) == Vector2.ZERO, "stick drift inside dead zone is ignored")
	ok(C.stick(1.0, 0.0).x > 0.99, "full stick deflection reaches 1.0")
	var raw := P.binds_for_name("EasySMX (D-mode)", false, {})
	var std := P.binds_for_name("Xbox Wireless Controller", true, {})
	var empty := axs()
	var h := P.held_from(btns([2]), empty, raw, false)
	ok(h["pass"] and not h["shoot"] and not h["through"], "raw EasySMX b2 is PASS")
	ok(P.held_from(btns([3]), empty, raw, false)["shoot"], "raw EasySMX b3 is SHOOT")
	ok(P.held_from(btns([0]), empty, raw, false)["through"], "raw EasySMX b0 is THROUGH")
	ok(P.held_from(btns([1]), empty, raw, false)["tackle"], "raw EasySMX b1 is TACKLE")
	ok(P.held_from(btns([4]), empty, raw, false)["switch"], "raw EasySMX b4 switches player")
	ok(P.held_from(btns([6]), empty, raw, false)["sprint"], "raw LT button also sprints")
	ok(P.held_from(btns([9]), empty, raw, false)["pause"], "raw Start (b9) pauses")
	ok(P.held_from(btns([0]), empty, std, true)["pass"], "standard A is PASS")
	ok(P.held_from(btns([6]), empty, std, true)["pause"], "standard Start (b6) pauses")
	ok(P.held_from(btns(), axs({4: 1.0}), std, true)["sprint"], "analogue trigger sprints")
	ok(P.move_xy(btns([12]), empty, false, C.DEADZONE)[1] < -0.9, "raw hat button 12 moves up (no 11-14 conflict)")
	ok(P.move_xy(btns([11]), empty, false, C.DEADZONE)[1] < -0.9, "Godot hat button 11 works on an unmapped pad")
	ok(P.move_xy(btns(), axs({6: -1.0}), false, C.DEADZONE)[0] < -0.9, "hat-as-axis 6 moves left")
	ok(P.move_xy(btns([15]), empty, true, C.DEADZONE)[0] == 0.0,
		"mapped pads use d-pad 11-14, not raw 12-15")
	ok(P.move_xy(btns([11]), empty, true, C.DEADZONE)[1] < -0.9, "mapped pad d-pad up works")

	# ---- device discovery ----
	ok(P.devices_for([0, 3, 7], false, 0).size() == 3, "1P: every connected pad drives P1")
	ok(P.devices_for([0, 3, 7], true, 1) == [3], "2P: player 2 gets the second pad")
	ok(P.devices_for([], false, 0).is_empty(), "no pads -> no devices")

	# ---- instance API with no hardware attached (must not crash) ----
	var ctl = C.new()
	ctl.load_saved()
	ok(ctl.binds_for(0).size() == C.ACTIONS.size(), "binds_for works with no pad attached")
	ok(ctl.describe().contains("mappings loaded"), "CONTROLLER SETUP text is available")
	# Web registers all six built-ins and no OS-tagged DB lines: exercises the
	# FileAccess / Input.add_joy_mapping path without replaying 1600 SDL lines
	# into Godot (platform filtering itself is covered by the pure tests above).
	ok(ctl.load_mappings("Web") >= 6, "SDL mappings load on Web (all built-in fallbacks)")
	print("RESULT fails=", fails)
	quit(1 if fails > 0 else 0)

extends Node3D
## Arena FC - BROWSER EDITION (GDScript).
## Upstream Godot 4 cannot export C#/.NET projects to Web, so this GDScript-only
## runtime ships the same procedural skinned rig (Data/rig_default.json, generated
## by the C# RigBuilder) and a lighter 5-a-side match. Runs in any browser/WebGL2.

const HALF_L := 52.5
const HALF_W := 34.0
const GOAL_W := 3.66
const GOAL_H := 2.44
const BALL_R := 0.11
const TEAM := 5

var rig_data: Dictionary = {}
var bone_index: Dictionary = {}
var players: Array = []
var rigs: Array = []
var ball: Dictionary = {}
var ball_mesh: MeshInstance3D
var cam: Camera3D
var ring_mesh: MeshInstance3D
var arrow_mesh: MeshInstance3D
var cam_lbl: Label
var cam_mode := 0
var cam_zoom := 0.9
var cam_names := ["Broadcast", "Telephoto", "Player cam", "Tactical"]
var world: Node3D
var switch_cd := 0.0
var cam_look := Vector3.ZERO
var humans: Array = []
var two_player_mode := false
var pad_ctl
var hud_over: Control
var pad_ui: Control
var pad_info: Label
var pad_learn_idx := -1
var pad_learn_dev := 0
var stadium: Node3D
var menu: Control
var editor: Control
var hud: Control
var score_lbl: Label
var clock_lbl: Label
var feed_lbl: Label
var preview: Node3D
var edit_bone: int = 11
var edit_rx: HSlider
var edit_ry: HSlider
var edit_rz: HSlider
var auto_shot := false
var shot_done := false

var phase := "menu"          # menu / play / goal / kickoff / editor

# --- Play With Friends (WebSocket client) ---
var net: Node                       # Web/NetClient.gd
var net_mode := false
var net_ui: Control
var net_url_edit: LineEdit
var net_name_edit: LineEdit
var net_room_edit: LineEdit
var net_status: Label
var net_room_label: Label
var net_players_label: Label
var net_start_btn: Button
var net_prev_snap: Dictionary = {}
var net_latest_snap: Dictionary = {}
var net_tick := 0
var net_seq_acc := 0.0
var net_auto_start := false
var net_probe := 0.0
var net_snap_count := 0
var net_reconnecting := false
var net_host_notice := ""
var ui_layer: CanvasLayer
const NetClientScript = preload("res://Web/NetClient.gd")
const RigBuilder = preload("res://Scripts/Godot/ProceduralRig3D.gd")
const AudioScript = preload("res://Scripts/Core/Audio/ProceduralAudio.gd")
const RecorderScript = preload("res://Scripts/Core/Net/ReplayRecorder.gd")
const ReplayerScript = preload("res://Scripts/Core/Net/ReplayPlayer.gd")
const AimScript = preload("res://Scripts/Godot/SetPieceAim.gd")
const StadiumScript = preload("res://Scripts/Godot/StadiumKit.gd")
const MatchRules = preload("res://Web/MatchRules.gd")
const Controllers = preload("res://Web/Controllers.gd")
const HudScript = preload("res://Web/HudOverlay.gd")
var audio: Node                      # ProceduralAudio (the "Audio" autoload if present)
var recorder: Node                   # ReplayRecorder: rolling highlight buffer + optional file
var replayer: Node                   # ReplayPlayer
var aim: Node3D                      # SetPieceAim
var practice := false                # free-kick practice mode
var practice_timer := 0.0
var replay_label: Label
var feed_prev: Array = []
var feed_primed := false
var phase_timer := 0.0
var t := 0.0
var clock := 0.0
var score := [0, 0]
var feed: Array = []
var controlled := 4
var charge := 0.0
var prev: Dictionary = {}
var touch_move := Vector2.ZERO
var touch_down: Dictionary = {}
var rng := RandomNumberGenerator.new()
var home_cols := [Color("#d7263d"), Color("#f8fafc"), Color("#14213d")]
var away_cols := [Color("#1d4ed8"), Color("#f8fafc"), Color("#1e3a8a")]

# ---------------------------------------------------------------- lifecycle
func _ready() -> void:
	rng.seed = 2026
	# user://rig_override.json (e.g. exported from Sprite Forge) wins if it validates, else the shipped rig.
	rig_data = RigBuilder.load_rig_data()
	setup_modules()
	var bones: Array = rig_data["bones"]
	for i in range(bones.size()):
		bone_index[bones[i]["n"]] = i
	build_static()
	build_ui()
	setup_net()
	show_menu()
	var args := OS.get_cmdline_user_args()
	# Shareable join links: /?net_url=ws://host:7777&net_room=CODE&net_name=Sam
	var q := web_query()
	print("ARENA_FC_WEB_READY query=", q)
	if q.has("net_url"):
		net_url_edit.text = str(q.get("net_url", "ws://127.0.0.1:7777"))
		net_name_edit.text = str(q.get("net_name", "Web Player"))
		net_room_edit.text = str(q.get("net_room", ""))
		show_net_ui()
		net.connect_to(net_url_edit.text, net_name_edit.text, net_room_edit.text, bool(q.get("create", "0") == "1"))
		net_auto_start = bool(q.get("autostart", "0") == "1")
		if q.has("net_probe"):
			net_probe = float(q.get("net_probe", "12"))
		if q.has("reconnect"):
			net.reconnect_saved()
	if args.has("--net-url"):
		var u := arg_value(args, "--net-url", "ws://127.0.0.1:7777")
		var n := arg_value(args, "--net-name", "Web Player")
		var r := arg_value(args, "--net-room", "")
		show_net_ui()
		net.connect_to(u, n, r, args.has("--net-host"))
		net_auto_start = args.has("--net-autostart")
		if args.has("--net-probe-seconds"):
			net_probe = float(arg_value(args, "--net-probe-seconds", "12"))
	if args.has("--auto-play"):
		start_match()
	elif args.has("--auto-editor"):
		show_editor()
	auto_shot = args.has("--auto-shot")
	if auto_shot and phase == "menu":
		start_match()

func _physics_process(delta: float) -> void:
	t += delta
	if net != null:
		net.poll(delta)
		if net_auto_start and net.is_host() and not net.in_match and t > 3.0:
			net_auto_start = false
			net.send_start()
		if net_probe > 0.0 and t > net_probe:
			print("ARENA_FC_WEB_NETPROBE snaps=%d tick=%d room=%s slot=%d host=%d mode=%s resumed=%s" % [net_snap_count, net_tick, net.room, net.slot, net.host_slot, str(net_mode), str(net.resumed)])
			get_tree().quit(0)
	if auto_shot and not shot_done and t > 1.2:
		shot_done = true
		var img := get_viewport().get_texture().get_image()
		img.save_png("user://browser_shot.png")
		print("ARENA_FC_BROWSER_SHOT ", ProjectSettings.globalize_path("user://browser_shot.png"))
		get_tree().quit()
	if phase == "editor":
		if preview:
			preview.rotation.y = sin(t * 0.4) * 0.3
			animate_rig(preview, 2.0, t, "idle")
		return
	if phase == "menu":
		cam.position = Vector3(sin(t * 0.12) * 2.0, 2.6, 8.0)
		cam.look_at_from_position(cam.position, Vector3(0, 1.0, 0), Vector3.UP)
		return
	if phase == "replay":
		update_visuals(delta)
		if net_mode:
			net_send_input(delta)          # you keep playing while you watch
		if Input.is_key_pressed(KEY_ENTER) or Input.is_key_pressed(KEY_X):
			replayer.stop()
			_on_replay_finished()
		return
	if phase == "aim":
		update_visuals(delta)
		aim.nudge(-touch_move.x * aim.turn_speed_deg * delta)
		aim.set_external_hold(bool(touch_down.get("shoot", false)))
		return
	if phase != "play":
		if not net_mode:
			update_visuals(delta)
		phase_timer -= delta
		if phase_timer <= 0.0:
			if phase == "goal":
				if practice:
					setup_practice()
				elif not start_instant_replay():
					end_goal_break()
			elif phase == "kickoff" or phase == "restart":
				phase = "play"
				say("Back under way!")
				audio.play_whistle()
		return
	clock += delta * 15.0
	step_match(delta)
	recorder.capture(delta, players, ball, score, clock)
	if practice:
		practice_timer -= delta
		if practice_timer <= 0.0:
			setup_practice()

func _input(event: InputEvent) -> void:
	if pad_learn_idx >= 0 and event is InputEventJoypadButton and event.pressed:
		pad_learn_button(event.device, event.button_index)
		get_viewport().set_input_as_handled()
		return
	if event is InputEventKey and event.pressed and not event.echo and phase in ["play", "aim", "replay", "goal", "kickoff"] \
			and (net_ui == null or not net_ui.visible):
		if event.keycode == KEY_M:
			say("Sound on" if audio.toggle() else "Sound off")
		elif event.keycode == KEY_V and phase == "play":
			start_instant_replay()
	if event is InputEventMouseButton:
		if event.button_index == MOUSE_BUTTON_WHEEL_UP and event.pressed:
			add_zoom(-0.09)
		elif event.button_index == MOUSE_BUTTON_WHEEL_DOWN and event.pressed:
			add_zoom(0.09)
	if event is InputEventMagnifyGesture:
		add_zoom(-(event.factor - 1.0) * 1.4)
	if event is InputEventScreenTouch or event is InputEventScreenDrag:
		var p: Vector2 = event.position
		var screen: Vector2 = get_viewport().get_visible_rect().size
		if p.x < screen.x * 0.45 and p.y > screen.y * 0.5:
			var centre := Vector2(130, screen.y - 130)
			var d: Vector2 = (p - centre) / 90.0
			touch_move = d.limit_length(1.0)
			if event is InputEventScreenTouch and not event.pressed:
				touch_move = Vector2.ZERO

# ---------------------------------------------------------------- static world
func build_static() -> void:
	stadium = StadiumScript.new()
	stadium.half_l = HALF_L
	stadium.half_w = HALF_W
	stadium.goal_w = GOAL_W
	stadium.goal_h = GOAL_H
	add_child(stadium)
	stadium.build()

	var pitch := MeshInstance3D.new()
	var pm := PlaneMesh.new()
	pm.size = Vector2(HALF_L * 2.0, HALF_W * 2.0)
	pitch.mesh = pm
	pitch.material_override = ShaderMaterial.new()
	(pitch.material_override as ShaderMaterial).shader = load("res://Shaders/pitch.gdshader")
	pitch.position.y = 0.012
	add_child(pitch)

	world = Node3D.new()
	world.name = "World"
	add_child(world)
	cam = Camera3D.new()
	cam.fov = 52
	cam.far = 600
	cam.position = Vector3(0, 2.6, 8.0)
	add_child(cam)
	cam.make_current()

# ---------------------------------------------------------------- rig from JSON
func v3(a: Array) -> Vector3:
	return Vector3(float(a[0]), float(a[1]), float(a[2]))

func packed_v3(flat: Array) -> PackedVector3Array:
	var out := PackedVector3Array()
	for i in range(0, flat.size(), 3):
		out.append(Vector3(float(flat[i]), float(flat[i + 1]), float(flat[i + 2])))
	return out

func packed_v2(flat: Array) -> PackedVector2Array:
	var out := PackedVector2Array()
	for i in range(0, flat.size(), 2):
		out.append(Vector2(float(flat[i]), float(flat[i + 1])))
	return out

func mat_for(idx: int, cols: Array) -> StandardMaterial3D:
	return RigBuilder.material_for(idx, cols)

func make_rig(cols: Array) -> Node3D:
	return RigBuilder.build(rig_data, cols)

func recolor(r: Node3D, cols: Array) -> void:
	var am := (r.get_meta("mi") as MeshInstance3D).mesh as ArrayMesh
	var mats: Array = rig_data["mats"]
	for s in range(am.get_surface_count()):
		am.surface_set_material(s, mat_for(int(mats[s]), cols))
	r.set_meta("cols", cols)

# ---------------------------------------------------------------- match
var formation := [Vector2(-0.86, 0), Vector2(-0.52, 0), Vector2(-0.12, -0.48), Vector2(-0.12, 0.48), Vector2(0.10, 0)]

func reset_positions() -> void:
	score = [0, 0]
	# queue_free() only takes effect at the end of the frame, so keep the ball out of the purge and
	# reuse it unless it is itself already doomed (show_menu() frees every child of `world`).
	if ball_mesh != null and is_instance_valid(ball_mesh) and ball_mesh.get_parent() == world:
		world.remove_child(ball_mesh)
	for c in world.get_children():
		c.queue_free()
	players.clear()
	rigs.clear()
	for side in range(2):
		var sign := 1.0 if side == 0 else -1.0
		var cols := home_cols if side == 0 else away_cols
		for i in range(TEAM):
			var p := {
				"team": side, "slot": i,
				"pos": Vector3(sign * formation[i].x * HALF_L * 0.94, 0, formation[i].y * HALF_W * 0.88),
				"home": Vector3(sign * formation[i].x * HALF_L * 0.94, 0, formation[i].y * HALF_W * 0.88),
				"vel": Vector3.ZERO, "facing": Vector3(sign, 0, 0), "phase": rng.randf() * 6.28,
				"keeper": i == 0, "action": "idle", "lock": 0.0,
			}
			players.append(p)
			var r := make_rig(cols)
			r.position = p["pos"]
			world.add_child(r)
			rigs.append(r)
	if ball_mesh == null or not is_instance_valid(ball_mesh) or ball_mesh.is_queued_for_deletion():
		ball_mesh = MeshInstance3D.new()
		var sm := SphereMesh.new()
		sm.radius = BALL_R
		sm.height = BALL_R * 2.0
		ball_mesh.mesh = sm
		ball_mesh.material_override = ShaderMaterial.new()
		(ball_mesh.material_override as ShaderMaterial).shader = load("res://Shaders/ball.gdshader")
	world.add_child(ball_mesh)
	ball = {"pos": Vector3(0, BALL_R, 0), "vel": Vector3.ZERO, "owner": TEAM - 1, "free": 0.0, "last": 0}
	set_humans(two_player_mode)
	build_selection_marker()


func build_selection_marker() -> void:
	var mat := StandardMaterial3D.new()
	mat.albedo_color = Color("#35ffa0")
	mat.emission_enabled = true
	mat.emission = Color("#35ffa0")
	mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	var torus := TorusMesh.new()
	torus.inner_radius = 0.60
	torus.outer_radius = 0.78
	torus.ring_segments = 32
	torus.rings = 8
	ring_mesh = MeshInstance3D.new()
	ring_mesh.mesh = torus
	ring_mesh.material_override = mat
	world.add_child(ring_mesh)
	var amat := StandardMaterial3D.new()
	amat.albedo_color = Color("#35ffa0")
	amat.emission_enabled = true
	amat.emission = Color("#35ffa0")
	amat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	amat.no_depth_test = true
	var cone := CylinderMesh.new()
	cone.top_radius = 0.0
	cone.bottom_radius = 0.14
	cone.height = 0.28
	cone.radial_segments = 4
	arrow_mesh = MeshInstance3D.new()
	arrow_mesh.mesh = cone
	arrow_mesh.material_override = amat
	arrow_mesh.rotation_degrees = Vector3(180, 45, 0)
	world.add_child(arrow_mesh)

func add_zoom(d: float) -> void:
	cam_zoom = clampf(cam_zoom + d, 0.55, 2.4)

func start_match(two_player := false) -> void:
	two_player_mode = two_player
	if not net_mode:
		if net != null:
			net.close()
	menu.visible = false
	editor.visible = false
	hud.visible = true
	clock = 0.0
	feed.clear()
	practice = false
	reset_positions()
	say("Kick off! Arena FC browser edition.")
	audio.play_whistle()
	phase = "kickoff"
	phase_timer = 1.0
	start_recording()

func say(text: String) -> void:
	feed.append(text)
	if feed.size() > 3:
		feed.pop_front()
	feed_lbl.text = "\n".join(PackedStringArray(feed))
	if hud_over != null:
		hud_over.show_banner(text)

func goal(side: int) -> void:
	score[side] += 1
	say("GOAL!  %d - %d" % [score[0], score[1]])
	if stadium != null:
		stadium.celebrate(0)
	audio.play_goal()
	for q in players:
		if q["team"] == side and not q["keeper"]:
			q["action"] = "celebrate"
			q["atime"] = 4.0
	phase = "goal"
	phase_timer = 1.5 if not practice else 2.5

func step_match(delta: float) -> void:
	if net_mode:
		net_send_input(delta)
		net_apply_snapshots(delta)
	else:
		step_offline(delta)

	update_visuals(delta)

# ---------------------------------------------------------------- offline simulation
func team_of_ball_owner() -> int:
	return -1 if ball["owner"] < 0 else int(players[ball["owner"]]["team"])

func opp_positions(team: int) -> Array:
	var out: Array = []
	for q in players:
		if q["team"] != team:
			out.append(q["pos"])
	return out

## Rank (0 = closest) of player i among his team's outfield players by distance to the ball.
func chase_rank(i: int) -> int:
	var mine: float = players[i]["pos"].distance_to(ball["pos"])
	var rank := 0
	for j in range(players.size()):
		if j != i and players[j]["team"] == players[i]["team"] and not players[j]["keeper"]:
			if players[j]["pos"].distance_to(ball["pos"]) < mine - 0.001:
				rank += 1
	return rank

func set_action(p: Dictionary, a: String, dur: float) -> void:
	p["action"] = a
	p["atime"] = dur

func step_offline(delta: float) -> void:
	var cmds := read_inputs(delta)
	# --- ball ---
	if ball["owner"] >= 0:
		var o: Dictionary = players[ball["owner"]]
		var f: Vector3 = Vector3(o["facing"].x, 0, o["facing"].z).normalized()
		if f.length() < 0.1:
			f = Vector3(1, 0, 0)
		var run: float = clampf(o["vel"].length() / 5.0, 0.0, 1.0)
		var touch: float = 0.5 + 0.18 * sin(float(o["phase"]) * 3.0) * run     # ball runs ahead, then is re-taken
		ball["pos"] = o["pos"] + f * touch + Vector3(0, BALL_R, 0)
		ball["vel"] = o["vel"]
		ball["last"] = ball["owner"]
	else:
		var bv: Vector3 = ball["vel"]
		bv.y -= 9.81 * delta
		bv *= max(0.0, 1.0 - 0.06 * delta)
		ball["pos"] += bv * delta
		if ball["pos"].y < BALL_R:
			ball["pos"].y = BALL_R
			if bv.y < 0:
				bv.y = -bv.y * 0.48
				if bv.y > 1.5:
					audio.play_ball_bounce()
			if abs(bv.y) < 0.45:
				bv.y = 0
			bv.x *= max(0, 1 - 1.5 * delta)
			bv.z *= max(0, 1 - 1.5 * delta)
		ball["vel"] = bv
		ball["free"] += delta
		for side in [-1.0, 1.0]:
			var w: Dictionary = MatchRules.woodwork(ball["pos"], ball["vel"], side, HALF_L, GOAL_W, GOAL_H, BALL_R)
			if w["hit"]:
				ball["pos"] = w["pos"]
				ball["vel"] = w["vel"]
				audio.play_post()
				say("Off the woodwork!" if w["kind"] == "post" else "Off the bar!")
				break

	# --- players ---
	var ball_team := team_of_ball_owner()
	for i in range(players.size()):
		var p: Dictionary = players[i]
		p["lock"] = max(0, float(p["lock"]) - delta)
		p["atime"] = float(p.get("atime", 0.0)) - delta
		if p["atime"] <= 0.0 and p["action"] != "celebrate":
			p["action"] = "idle"
		var sign := 1.0 if p["team"] == 0 else -1.0
		var goal_pos := Vector3(sign * HALF_L, 0, 0)
		var own_goal := Vector3(-sign * HALF_L, 0, 0)
		var wish := Vector3.ZERO
		var speed := 5.4
		if p["keeper"]:
			var kt: Vector3 = MatchRules.keeper_target(own_goal.x, sign, ball["pos"], ball["vel"], GOAL_W)
			var to: Vector3 = kt - p["pos"]
			var heading: bool = ball["owner"] < 0 and -sign * ball["vel"].x > 8.0
			if heading:
				if not p.get("reading", false):
					p["reading"] = true                       # misjudges each shot a little; faster shots fool him more
					p["kerr"] = rng.randfn(0.0, 0.9 + ball["vel"].length() * 0.05)
				kt.z = clampf(kt.z + float(p["kerr"]), -GOAL_W - 0.6, GOAL_W + 0.6)
				to = kt - p["pos"]
			else:
				p["reading"] = false
			if to.length() > 0.2:
				wish = to.normalized()
			speed = 8.0 if heading else 6.0
			if heading and to.length() > 0.6:
				p["action"] = "dive"
				p["atime"] = 0.3
			if ball["owner"] == i:
				p["hold"] = float(p.get("hold", 0.0)) + delta
				wish = Vector3.ZERO
				if p["hold"] > 1.1:
					p["hold"] = 0.0
					pass_ball(i, false)
			else:
				p["hold"] = 0.0
		elif human_of(i) >= 0:
			var cmd: Dictionary = cmds[human_of(i)]
			wish = Vector3(cmd["move"].x, 0, cmd["move"].y)
			speed *= 1.0 + 0.3 * float(cmd["move"].length() > 0.1 and cmd["sprint"])
		elif ball["owner"] == i:
			wish = ai_carrier(i, p, goal_pos, delta)
			speed = 5.6
		else:
			wish = ai_off_ball(i, p, sign, ball_team, delta)
			if ball_team != p["team"] and chase_rank(i) < 2:
				speed = 5.9
		p["vel"] = p["vel"].lerp(wish * speed, min(1, delta * 8))
		p["pos"] += p["vel"] * delta
		p["pos"].y = 0
		p["pos"].x = clamp(p["pos"].x, -HALF_L - 2, HALF_L + 2)
		p["pos"].z = clamp(p["pos"].z, -HALF_W - 2, HALF_W + 2)
		if p["vel"].length() > 0.2:
			p["facing"] = p["facing"].slerp(Vector3(p["vel"].x, 0, p["vel"].z).normalized(), min(1.0, delta * 12.0))
		p["phase"] += delta * (2.0 + p["vel"].length())

	keeper_saves()

	# --- free ball pickup ---
	if ball["owner"] < 0 and ball["free"] > 0.1 and ball["pos"].y < 1.4:
		for i in range(players.size()):
			if players[i]["lock"] > 0:
				continue
			if players[i]["pos"].distance_to(ball["pos"]) < 1.05:
				ball["owner"] = i
				ball["vel"] = Vector3.ZERO
				ball["free"] = 0
				ball["last"] = i
				if not players[i]["keeper"]:
					assign_ctrl(int(players[i]["team"]), i)
				break
	auto_switch(delta)

	# --- rules ---
	var bp: Vector3 = ball["pos"]
	if abs(bp.x) > HALF_L and abs(bp.z) < GOAL_W and bp.y < GOAL_H:
		goal(0 if bp.x > 0 else 1)
		return
	if abs(bp.x) > HALF_L + 0.6 or abs(bp.z) > HALF_W + 0.6:
		ball_out()

func ai_carrier(i: int, p: Dictionary, goal_pos: Vector3, delta: float) -> Vector3:
	var to_goal: Vector3 = (goal_pos - p["pos"])
	to_goal.y = 0
	var dir := to_goal.normalized()
	var avoid := Vector3.ZERO
	for q in players:
		if q["team"] != p["team"]:
			var d: Vector3 = q["pos"] - p["pos"]
			var l := d.length()
			if l < 4.5 and l > 0.01 and d.normalized().dot(dir) > 0.2:
				var side := Vector3(-d.z, 0, d.x).normalized()
				if side.dot(dir) < 0:
					side = -side
				avoid += side * (4.5 - l) / 4.5
	var pr: float = MatchRules.pressure(p["pos"], opp_positions(p["team"]))
	var dg: float = to_goal.length()
	if dg < 24.0 and rng.randf() < delta * (1.5 if dg < 16.0 else 0.8):
		shoot(i, rng.randf_range(0.55, 0.95))
	elif rng.randf() < delta * (0.3 + pr * 3.0):
		pass_ball(i, false)
	return (dir + avoid * 1.6).normalized()

func ai_off_ball(i: int, p: Dictionary, sign: float, ball_team: int, delta: float) -> Vector3:
	var home: Vector3 = p["home"]
	home.x += clamp(ball["pos"].x * 0.18, -6, 6)
	home.z += clamp(ball["pos"].z * 0.15, -5, 5)
	var rank := chase_rank(i)
	if ball_team == p["team"]:
		home.x += sign * 9.0                              # support the attack, spread wide
		home.z += (-6.0 if p["slot"] % 2 == 0 else 6.0)
		return (home - p["pos"]).normalized() if p["pos"].distance_to(home) > 1.0 else Vector3.ZERO
	if ball_team < 0:
		if rank == 0:
			return (ball["pos"] - p["pos"]).normalized()
		return (home - p["pos"]).normalized() if p["pos"].distance_to(home) > 1.0 else Vector3.ZERO
	# opponents have it: two press, the rest hold shape between ball and goal
	var holder: Dictionary = players[ball["owner"]]
	if rank == 0:
		var to: Vector3 = holder["pos"] - p["pos"]
		if to.length() < 1.6 and p["lock"] <= 0 and rng.randf() < delta * 3.0:
			try_tackle(i, ball["owner"])
		return to.normalized()
	if rank == 1:
		var cut: Vector3 = holder["pos"] + Vector3(-sign * 3.0, 0, 0)
		return (cut - p["pos"]).normalized()
	return (home - p["pos"]).normalized() if p["pos"].distance_to(home) > 1.0 else Vector3.ZERO

func try_tackle(tackler: int, victim: int, sliding := false) -> void:
	var t: Dictionary = players[tackler]
	var v: Dictionary = players[victim]
	t["lock"] = 0.5
	set_action(t, "slide" if sliding else "tackle", 0.45)
	if rng.randf() < MatchRules.foul_chance(t["vel"], v["facing"], sliding):
		foul(tackler, victim)
		return
	ball["owner"] = tackler
	say("Tackle!")
	audio.play_tackle()

func foul(tackler: int, victim: int) -> void:
	var v: Dictionary = players[victim]
	say("Foul!  Free kick.")
	audio.play_whistle()
	var spot: Vector3 = v["pos"]
	spot.y = BALL_R
	free_kick(int(v["team"]), spot)

## Free kick to `team` at `spot`. A human team in shooting range gets the aim mode; otherwise the nearest
## player takes it quickly.
func free_kick(team: int, spot: Vector3) -> void:
	spot.x = clamp(spot.x, -HALF_L + 1.0, HALF_L - 1.0)
	spot.z = clamp(spot.z, -HALF_W + 1.0, HALF_W - 1.0)
	var sign := 1.0 if team == 0 else -1.0
	if team == 0 and not practice and spot.distance_to(Vector3(HALF_L, 0, 0)) < 34.0:
		var taker := nearest_outfield(0, spot)
		var wall_c := spot + (Vector3(HALF_L, 0, 0) - spot).normalized() * 9.15
		var k := 0
		for j in range(TEAM, players.size()):
			if players[j]["keeper"]:
				continue
			players[j]["pos"] = wall_c + Vector3(0, 0, (k - 1.5) * 0.9)
			players[j]["vel"] = Vector3.ZERO
			k += 1
			if k >= 3:
				break
		players[taker]["pos"] = spot - Vector3(0.9, 0, 0)
		players[taker]["facing"] = Vector3(1, 0, 0)
		ball["pos"] = spot
		ball["vel"] = Vector3.ZERO
		ball["owner"] = -1
		ball["free"] = 0.0
		controlled = taker
		phase = "aim"
		aim.start_aim(spot, Vector3(1, 0, 0))
		return
	restart_with(team, spot, "Free kick")

func nearest_outfield(team: int, pos: Vector3) -> int:
	var best := -1
	var bd := 1e9
	for j in range(players.size()):
		if players[j]["team"] == team and not players[j]["keeper"]:
			var d: float = players[j]["pos"].distance_to(pos)
			if d < bd:
				bd = d
				best = j
	return best

func restart_with(team: int, spot: Vector3, label: String) -> void:
	var taker := nearest_outfield(team, spot)
	if label == "Goal kick":
		taker = team * TEAM                             # the keeper
	for p in players:
		p["vel"] = Vector3.ZERO
	players[taker]["pos"] = Vector3(spot.x, 0, spot.z) - Vector3(clampf(spot.x, -1, 1) * 0.0, 0, 0)
	players[taker]["lock"] = 0.0
	ball["pos"] = Vector3(spot.x, BALL_R, spot.z)
	ball["vel"] = Vector3.ZERO
	ball["owner"] = taker
	ball["free"] = 0.0
	ball["last"] = taker
	if not players[taker]["keeper"]:
		assign_ctrl(team, taker)
	say(label + ".")
	audio.play_whistle()
	phase = "restart"
	phase_timer = 0.9

func ball_out() -> void:
	if practice:
		setup_practice()
		return
	var last_team := 0
	if ball["last"] >= 0 and ball["last"] < players.size():
		last_team = int(players[ball["last"]]["team"])
	var r: Dictionary = MatchRules.restart_for(ball["pos"], last_team, HALF_L, HALF_W)
	var label: String = {"throw": "Throw-in", "corner": "Corner", "goal_kick": "Goal kick"}[r["kind"]]
	restart_with(int(r["team"]), r["spot"], label)

func keeper_saves() -> void:
	if ball["owner"] >= 0:
		return
	for i in range(players.size()):
		var k: Dictionary = players[i]
		if not k["keeper"] or k["lock"] > 0:
			continue
		var sign := 1.0 if k["team"] == 0 else -1.0
		if -sign * ball["vel"].x <= 0.0:
			continue
		var reach_pt: Vector3 = k["pos"] + Vector3(0, 1.0, 0)
		var miss: float = ball["pos"].distance_to(reach_pt)
		if miss > 1.9 or ball["pos"].y > 2.7 or ball["free"] < 0.1:
			continue
		var spd: float = ball["vel"].length()
		if spd < 10.0:
			ball["owner"] = i
			ball["vel"] = Vector3.ZERO
			say("Keeper claims it.")
			return
		k["lock"] = 0.6
		if rng.randf() < MatchRules.save_chance(miss, spd, 1.9):
			ball["vel"] = Vector3(sign * spd * 0.35, 3.0, (ball["pos"].z - k["pos"].z) * 4.0 + rng.randf_range(-3.0, 3.0))
			set_action(k, "dive", 0.6)
			say("Great save!")
			audio.play_tackle()
		return

func auto_switch(delta: float) -> void:
	switch_cd = max(0.0, switch_cd - delta)
	if switch_cd > 0.0:
		return
	for h in humans:
		if ball["owner"] == h["ctrl"]:
			continue
		var best := nearest_outfield(int(h["team"]), ball["pos"])
		if best >= 0 and best != h["ctrl"]:
			var dc: float = players[h["ctrl"]]["pos"].distance_to(ball["pos"])
			var db: float = players[best]["pos"].distance_to(ball["pos"])
			if db < dc - 2.5:
				h["ctrl"] = best
				switch_cd = 0.6
	controlled = humans[0]["ctrl"]

func update_visuals(delta: float) -> void:
	for i in range(rigs.size()):
		var r: Node3D = rigs[i]
		r.position = players[i]["pos"]
		r.rotation.y = atan2(players[i]["facing"].x, players[i]["facing"].z)
		var pi_: Dictionary = players[i]
		var tb: Vector3 = ball["pos"] - pi_["pos"]
		var yaw_rel: float = clampf(wrapf(atan2(tb.x, tb.z) - atan2(pi_["facing"].x, pi_["facing"].z), -PI, PI), -0.9, 0.9)
		animate_rig(r, pi_["vel"].length(), pi_["phase"], pi_["action"], yaw_rel)
		var hop := 0.0
		if pi_["action"] == "celebrate":
			hop = absf(sin(t * 7.0 + float(i))) * 0.3
		elif pi_["action"] == "slide":
			hop = -0.12
		r.position.y = hop
	ball_mesh.position = ball["pos"]
	ball_mesh.rotation_degrees += Vector3(ball["vel"].z, 0, -ball["vel"].x) * delta * 150.0
	update_browser_camera(delta)
	score_lbl.text = "HAR  %d  -  %d  NOR" % [score[0], score[1]]
	if net_mode:
		clock_lbl.text = "%02d:%02d   ·   ONLINE ROOM %s" % [int(clock / 60.0), int(clock) % 60, net.room if net != null else "?"]
	else:
		clock_lbl.text = "%02d:%02d   ·   BROWSER EDITION 5v5" % [int(clock / 60.0), int(clock) % 60]



# ---------------------------------------------------------------- ONLINE PLAY
func web_query() -> Dictionary:
	if not OS.has_feature("web"):
		return {}
	var q := str(JavaScriptBridge.eval("window.location.search"))
	if q.begins_with("?"):
		q = q.substr(1)
	var out := {}
	for pair in q.split("&"):
		var kv := pair.split("=", true, 1)
		if kv.size() == 2:
			out[str(kv[0])] = str(kv[1]).uri_decode()
	return out

func arg_value(args: PackedStringArray, key: String, fallback: String) -> String:
	var i := args.find(key)
	if i >= 0 and i + 1 < args.size():
		return str(args[i + 1])
	return fallback

func setup_net() -> void:
	net = NetClientScript.new()
	net.name = "NetClient"
	add_child(net)
	net.connected.connect(_on_net_connected)
	net.lobby_changed.connect(_on_net_lobby)
	net.match_begin.connect(_on_net_begin)
	net.snapshot_received.connect(_on_net_snapshot)
	net.match_ended.connect(_on_net_end)
	net.error_raised.connect(_on_net_error)
	net.disconnected_msg.connect(_on_net_disconnect)
	net.match_resumed.connect(_on_net_resume)
	net.host_changed.connect(_on_net_host)
	net.reconnect_pending.connect(_on_net_reconnect)

func _on_net_connected(_info: Dictionary) -> void:
	_set_net_status("Connected as %s (slot %d)." % [net.player_name, net.slot])

func _on_net_lobby(_info: Dictionary) -> void:
	refresh_net_lobby()

func _on_net_begin(_info: Dictionary) -> void:
	# net_mode MUST be set first: start_match() closes the socket in single-player mode.
	print("ARENA_FC_WEB_BEGIN room=", net.room, " slot=", net.slot)
	net_mode = true
	start_match()                 # builds rigs / ball / ring / hud
	net_prev_snap = {}
	net_latest_snap = {}
	feed_prev = []
	feed_primed = false
	if net_ui != null:
		net_ui.visible = false
	say("Online match started! Room " + net.room)

func _on_net_snapshot(pkt: Dictionary) -> void:
	net_snap_count += 1
	net_prev_snap = net_latest_snap.duplicate(true)
	net_latest_snap = pkt
	net_tick = int(pkt.get("tick", 0))

func _on_net_end(info: Dictionary) -> void:
	say(str(info.get("com", "Full time")))
	_set_net_status(str(info.get("com", "Full time")) + " — back in the lobby.")
	if net_ui != null:
		net_ui.visible = true
	net_mode = false
	recorder.stop_recording()
	refresh_net_lobby()

func _on_net_error(msg: String) -> void:
	print("ARENA_FC_WEB_ERROR ", msg)
	_set_net_status(msg)
	if net_ui != null:
		net_ui.visible = true

func _on_net_host(new_slot: int, reason: String) -> void:
	net_host_notice = reason
	_set_net_status(reason)
	refresh_net_lobby()

func _on_net_reconnect(attempt: int) -> void:
	net_reconnecting = true
	_set_net_status("Connection lost — reconnecting with your saved token (attempt %d)…" % attempt)

func _on_net_resume(info: Dictionary) -> void:
	# net_mode MUST be set first: start_match() closes the socket offline.
	net_mode = true
	net_reconnecting = false
	net_prev_snap = {}
	net_latest_snap = info.duplicate(true)
	net_tick = int(info.get("tick", 0))
	start_match()
	var arr: Array = info.get("players", [])
	for i in range(min(arr.size(), players.size())):
		var q: Dictionary = arr[i]
		players[i]["pos"] = Vector3(float(q.get("x", 0)), 0, float(q.get("z", 0)))
		players[i]["vel"] = Vector3(float(q.get("vx", 0)), 0, float(q.get("vz", 0)))
		var f := Vector3(float(q.get("fx", 1)), 0, float(q.get("fz", 0)))
		players[i]["facing"] = f.normalized() if f.length_squared() > 0.001 else Vector3(1, 0, 0)
		players[i]["action"] = str(q.get("a", "idle"))
	var bb: Dictionary = info.get("ball", {})
	if not bb.is_empty():
		ball["pos"] = Vector3(float(bb.get("x", 0)), float(bb.get("y", BALL_R)), float(bb.get("z", 0)))
		ball["vel"] = Vector3(float(bb.get("vx", 0)), float(bb.get("vy", 0)), float(bb.get("vz", 0)))
		ball["owner"] = int(bb.get("owner", -1))
	var sc: Array = info.get("score", [0, 0])
	if sc.size() >= 2:
		score = [int(sc[0]), int(sc[1])]
	clock = float(info.get("clock", clock))
	var ctrls: Array = info.get("ctrls", [])
	if net.slot >= 0 and net.slot < ctrls.size() and int(ctrls[net.slot]) >= 0:
		controlled = int(ctrls[net.slot])
	if net_ui != null:
		net_ui.visible = false
	print("ARENA_FC_WEB_RESUME tick=", net_tick, " slot=", net.slot, " token_ok=", net.resumed)
	_set_net_status("Reconnected into the live match — same team, same player, tick %d." % net_tick)

func _on_net_disconnect(msg: String) -> void:
	# Keep the frozen match on screen while the token-based reconnect runs.
	var can_retry: bool = net != null and bool(net.token.length() >= 32) and not bool(net._explicit)
	if not can_retry:
		net_mode = false
		net_reconnecting = false
	_set_net_status(msg)
	if net_ui != null:
		net_ui.visible = true
		refresh_net_lobby()

func net_send_input(delta: float) -> void:
	if net == null or not net.in_match:
		return
	var move := Vector2.ZERO
	if Input.is_key_pressed(KEY_A) or Input.is_key_pressed(KEY_LEFT): move.x -= 1
	if Input.is_key_pressed(KEY_D) or Input.is_key_pressed(KEY_RIGHT): move.x += 1
	if Input.is_key_pressed(KEY_W) or Input.is_key_pressed(KEY_UP): move.y -= 1
	if Input.is_key_pressed(KEY_S) or Input.is_key_pressed(KEY_DOWN): move.y += 1
	var jx := Input.get_joy_axis(0, JOY_AXIS_LEFT_X)
	var jy := Input.get_joy_axis(0, JOY_AXIS_LEFT_Y)
	if abs(jx) > 0.2 or abs(jy) > 0.2:
		move += Vector2(jx, jy)
	move += touch_move
	if move.length() > 1:
		move = move.normalized()
	var shoot_now: bool = Input.is_key_pressed(KEY_SPACE) or Input.is_joy_button_pressed(0, JOY_BUTTON_X) or touch_down.get("shoot", false)
	var cmd := {}
	if abs(move.x) > 0.01: cmd["mx"] = snappedf(move.x, 0.001)
	if abs(move.y) > 0.01: cmd["my"] = snappedf(move.y, 0.001)
	if Input.is_key_pressed(KEY_SHIFT) or Input.is_joy_button_pressed(0, JOY_BUTTON_RIGHT_SHOULDER) or touch_down.get("sprint", false):
		cmd["sp"] = true
	if edge("npass", Input.is_key_pressed(KEY_E) or Input.is_joy_button_pressed(0, JOY_BUTTON_A) or touch_down.get("pass", false)):
		cmd["pa"] = true
	if edge("nthrough", Input.is_key_pressed(KEY_Q) or Input.is_joy_button_pressed(0, JOY_BUTTON_Y) or touch_down.get("through", false)):
		cmd["th"] = true
	if edge("ntackle", Input.is_key_pressed(KEY_F) or Input.is_joy_button_pressed(0, JOY_BUTTON_B) or touch_down.get("tackle", false)):
		cmd["ta"] = true
	if edge("nswitch", Input.is_key_pressed(KEY_TAB) or Input.is_joy_button_pressed(0, JOY_BUTTON_LEFT_SHOULDER) or touch_down.get("switch", false)):
		cmd["sw"] = true
	if edge("nlob", Input.is_key_pressed(KEY_R)):
		cmd["lo"] = true
	if shoot_now:
		charge = min(1.0, charge + delta / 0.9)
	elif charge > 0:
		cmd["sh"] = true
		cmd["ch"] = max(0.25, charge)
		charge = 0
	# Camera controls stay entirely client-side.
	if edge("cam", Input.is_key_pressed(KEY_C)):
		cam_mode = (cam_mode + 1) % cam_names.size()
	for m in range(cam_names.size()):
		if edge("mode%d" % m, Input.is_key_pressed(KEY_1 + m)):
			cam_mode = m
	if edge("zin", Input.is_key_pressed(KEY_EQUAL) or Input.is_key_pressed(KEY_KP_ADD)):
		add_zoom(-0.14)
	if edge("zout", Input.is_key_pressed(KEY_MINUS) or Input.is_key_pressed(KEY_KP_SUBTRACT)):
		add_zoom(0.14)
	if Input.is_key_pressed(KEY_ESCAPE):
		leave_net()
		return
	net_seq_acc += delta
	var one_shot: bool = cmd.has("pa") or cmd.has("sh") or cmd.has("th") or cmd.has("ta") or cmd.has("sw") or cmd.has("lo")
	if one_shot or net_seq_acc >= 1.0 / 30.0:
		net_seq_acc = 0.0
		net.send_input(cmd)

func net_apply_snapshots(delta: float) -> void:
	var b: Dictionary = net_latest_snap
	if b.is_empty():
		return
	var arr: Array = b.get("players", [])
	for i in range(min(arr.size(), players.size())):
		var q: Dictionary = arr[i]
		var p: Dictionary = players[i]
		var target := Vector3(float(q.get("x", 0)), 0, float(q.get("z", 0)))
		p["pos"] = Vector3(p["pos"]).lerp(target, minf(1.0, delta * 20.0))
		p["vel"] = Vector3(float(q.get("vx", 0)), 0, float(q.get("vz", 0)))
		var f := Vector3(float(q.get("fx", 1)), 0, float(q.get("fz", 0)))
		p["facing"] = f.normalized() if f.length_squared() > 0.001 else Vector3(1, 0, 0)
		p["action"] = str(q.get("a", "idle"))
	var bb: Dictionary = b.get("ball", {})
	if not bb.is_empty():
		ball["pos"] = Vector3(float(bb.get("x", 0)), float(bb.get("y", BALL_R)), float(bb.get("z", 0)))
		ball["vel"] = Vector3(float(bb.get("vx", 0)), float(bb.get("vy", 0)), float(bb.get("vz", 0)))
		ball["owner"] = int(bb.get("owner", -1))
	var sc: Array = b.get("score", [0, 0])
	if sc.size() >= 2:
		if feed_primed and int(sc[0]) + int(sc[1]) > score[0] + score[1]:
			audio.play_goal()
		score = [int(sc[0]), int(sc[1])]
	clock = float(b.get("clock", clock))
	var ctrls: Array = b.get("ctrls", [])
	if net.slot >= 0 and net.slot < ctrls.size() and int(ctrls[net.slot]) >= 0 and int(ctrls[net.slot]) < players.size():
		controlled = int(ctrls[net.slot])
	var evs: Array = b.get("ev", [])
	var fresh: Array = AudioScript.new_lines(feed_prev, evs, feed_primed)
	for line in fresh:
		audio.play_for_event(AudioScript.event_for_text(str(line)))
	feed_prev = evs.duplicate()
	feed_primed = true
	if evs.size() > 0:
		feed.clear()
		for e in evs:
			feed.append(str(e))
		feed_lbl.text = "\n".join(PackedStringArray(feed))

func mk_edit(placeholder: String, text: String) -> LineEdit:
	var e := LineEdit.new()
	e.placeholder_text = placeholder
	e.text = text
	e.custom_minimum_size = Vector2(0, 36)
	return e

func build_net_ui(layer: CanvasLayer) -> void:
	net_ui = Control.new()
	net_ui.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	net_ui.visible = false
	layer.add_child(net_ui)
	var bg := ColorRect.new()
	bg.color = Color(0, 0, 0, 0.55)
	bg.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	net_ui.add_child(bg)
	var panel := PanelContainer.new()
	panel.offset_left = 350
	panel.offset_top = 70
	panel.offset_right = 930
	panel.offset_bottom = 660
	net_ui.add_child(panel)
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", 7)
	panel.add_child(v)
	var title := Label.new()
	title.text = "PLAY WITH FRIENDS"
	title.add_theme_font_size_override("font_size", 28)
	title.add_theme_color_override("font_color", Color("#2bdb85"))
	v.add_child(title)
	mk_label("Same authoritative server as the desktop game · room codes · up to 4 players", 13, Vector2.ZERO, Vector2(560, 24), v)
	mk_label("SERVER ADDRESS", 13, Vector2.ZERO, Vector2(560, 20), v)
	net_url_edit = mk_edit("wss://YOUR-PUBLIC-HOST/arena/ws", "./ws")   # "./ws" = next to this page
	v.add_child(net_url_edit)
	mk_label("YOUR NAME", 13, Vector2.ZERO, Vector2(560, 20), v)
	net_name_edit = mk_edit("Your name", "Web Player")
	v.add_child(net_name_edit)
	mk_label("ROOM CODE  (optional for CREATE — leave blank for a random code)", 13, Vector2.ZERO, Vector2(560, 20), v)
	net_room_edit = mk_edit("e.g. 7JRV6T", "")
	v.add_child(net_room_edit)
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 8)
	var create_btn := mk_button("CREATE MATCH", func(): net_connect(true))
	create_btn.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	var join_btn := mk_button("JOIN WITH CODE", func(): net_connect(false))
	join_btn.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(create_btn)
	row.add_child(join_btn)
	v.add_child(row)
	net_room_label = mk_label("ROOM  —", 30, Vector2.ZERO, Vector2(560, 46), v)
	net_room_label.add_theme_color_override("font_color", Color("#2bdb85"))
	net_players_label = mk_label("Not connected.", 14, Vector2.ZERO, Vector2(560, 110), v)
	net_start_btn = mk_button("START MATCH  (host only)", func(): net.send_start())
	net_start_btn.visible = false
	v.add_child(net_start_btn)
	v.add_child(mk_button("RECONNECT TO LAST MATCH", func():
		if not net.reconnect_saved():
			_set_net_status("No saved session to reconnect to.")))
	net_status = mk_label("Online: leave the address as ./ws when you opened this page from the game server; it finds the right wss:// address itself.", 12, Vector2.ZERO, Vector2(560, 40), v)
	v.add_child(mk_button("LEAVE / BACK TO MENU", leave_net))

func net_connect(create: bool) -> void:
	net_prev_snap = {}
	net_latest_snap = {}
	net.connect_to(net_url_edit.text, net_name_edit.text, net_room_edit.text, create)
	_set_net_status("Connecting to " + net.url + " …")

func _set_net_status(msg: String) -> void:
	if net_status != null:
		net_status.text = msg

func refresh_net_lobby() -> void:
	if net_room_label == null or net == null:
		return
	net_room_label.text = "ROOM  " + (net.room if not net.room.is_empty() else "—")
	var lines: Array = []
	for i in range(net.names.size()):
		if str(net.names[i]).is_empty():
			continue
		var sl := i if i >= net.slots.size() else int(net.slots[i])
		var pg := -1 if i >= net.pings.size() else int(net.pings[i])
		var online := true if i >= net.onlines.size() else bool(net.onlines[i])
		lines.append("  #%d  %s   %s   %s%s%s" % [sl, str(net.names[i]), "HOME" if sl % 2 == 0 else "AWAY", ("%d ms" % pg) if pg >= 0 else "—", "  HOST" if sl == net.host_slot else "", "" if online else "  (reconnecting…)"])
	net_players_label.text = "\n".join(PackedStringArray(lines)) if lines.size() > 0 else "Waiting for players…"
	net_start_btn.visible = net.is_host() and not net.in_match

func show_net_ui() -> void:
	if net_ui != null:
		net_ui.visible = true
	menu.visible = false
	editor.visible = false
	hud.visible = false
	refresh_net_lobby()

func leave_net() -> void:
	if net != null:
		net.close()
	net_mode = false
	if net_ui != null:
		net_ui.visible = false
	show_menu()

func update_browser_camera(delta: float) -> void:
	var bpos: Vector3 = ball["pos"]
	var ppos: Vector3 = players[controlled]["pos"]
	var facing: Vector3 = players[controlled]["facing"]
	# broadcast framing: look slightly ahead of where the ball is going, never past the stands
	var bv: Vector3 = ball["vel"]
	if ball["owner"] >= 0 and ball["owner"] < players.size():
		bv = players[ball["owner"]]["vel"] * 1.6
	var lead := Vector3(bv.x, 0, bv.z).limit_length(16.0) * 0.6
	var look := Vector3(clampf(bpos.x + lead.x, -HALF_L + 8.0, HALF_L - 8.0), 1.0, bpos.z * 0.9 + lead.z * 0.3)
	var target := Vector3(look.x - 3.0, 15.0, look.z + 30.0)
	var fov := 46.0 + clampf(bv.length() * 0.35, 0.0, 6.0)
	match cam_mode:
		1:
			target = Vector3(bpos.x - 2, 12, bpos.z + 30)
			fov = 39.0
		2:
			var fwd := Vector3(facing.x, 0, facing.z)
			if fwd.length_squared() < 0.001:
				fwd = Vector3(1, 0, 0)
			fwd = fwd.normalized()
			look = ppos + fwd * 7 + Vector3(0, 1.35, 0)
			target = ppos - fwd * 8 + Vector3(0, 3.2, 0)
			fov = 66.0
		3:
			look = Vector3(bpos.x * 0.5, 0, bpos.z * 0.4)
			target = look + Vector3(0, 78, 0.01)
			fov = 58.0
	target = look + (target - look) * cam_zoom
	target.y = maxf(target.y, 2.2)
	if phase == "aim":
		look = Vector3(bpos.x + 18.0, 1.4, bpos.z)
		target = Vector3(bpos.x - 12.0, 4.2, bpos.z)
		fov = 52.0
	if phase == "goal" and cam_mode != 3:                 # cinematic: swing round the scorer
		var ang := t * 0.7
		look = Vector3(bpos.x, 1.4, bpos.z)
		target = look + Vector3(cos(ang) * 11.0, 3.6, sin(ang) * 11.0)
		fov = 40.0
	var w := 1.0 - exp(-delta * (2.4 if phase == "goal" else 3.2))      # frame-rate independent spring
	cam.position = cam.position.lerp(target, w)
	cam_look = cam_look.lerp(look, 1.0 - exp(-delta * 5.0))
	cam.look_at_from_position(cam.position, cam_look, Vector3.UP)
	cam.fov = lerpf(cam.fov, fov, w)
	if cam_lbl:
		var extra := ""
		if net_mode and net != null:
			var pt := ("%d ms" % net.ping_ms) if net.ping_ms >= 0 else "-- ms"
			extra = "  ·  ROOM %s · %s · ONLINE" % [net.room, pt]
		cam_lbl.text = "%s  ·  zoom %d%%%s" % [cam_names[cam_mode], int(roundf(100.0 / cam_zoom)), extra]
	if is_instance_valid(ring_mesh) and is_instance_valid(arrow_mesh):
		var d := cam.position.distance_to(ppos)
		var s := clampf(d / 34.0, 0.75, 3.6)
		ring_mesh.position = Vector3(ppos.x, 0.055, ppos.z)
		ring_mesh.scale = Vector3(s, 1, s)
		ring_mesh.rotation.y = t * 0.6
		var a := clampf(d / 18.0, 0.5, 3.8)
		arrow_mesh.position = Vector3(ppos.x, 2.15 + a * 0.18 + sin(t * 3.2) * 0.1, ppos.z)
		arrow_mesh.scale = Vector3(a, a, a)

func animate_rig(r: Node3D, speed: float, time: float, action: String, look_yaw := 0.0) -> void:
	var sk := r.get_meta("sk") as Skeleton3D
	if sk == null:
		return
	var amp: float = clamp(speed / 6.0, 0.0, 1.0)
	var ph: float = time * 1.05                                    # `time` is the player's accumulated stride phase
	var s: float = sin(ph) * amp * 0.9
	var lk: float = max(0.0, sin(ph + 1.3)) * amp * 1.25        # knee flexes as the leg swings through
	var rk: float = max(0.0, sin(ph + 1.3 + PI)) * amp * 1.25
	var breathe: float = sin(time * 1.9) * 0.025
	# defaults: running / idle
	var hips := Vector3(0, 0, 0)
	var chest := Vector3(amp * 0.16 + breathe, s * 0.22, 0)
	var spine := Vector3(amp * 0.08, -s * 0.12, 0)
	var lth := Vector3(s, 0, 0.03)
	var rth := Vector3(-s, 0, -0.03)
	var lsh := Vector3(lk, 0, 0)
	var rsh := Vector3(rk, 0, 0)
	var lua := Vector3(-s * 0.9, 0, -0.14 - amp * 0.1)
	var rua := Vector3(s * 0.9, 0, 0.14 + amp * 0.1)
	var lfa := Vector3(-0.35 - amp * 0.9, 0, 0)
	var rfa := Vector3(-0.35 - amp * 0.9, 0, 0)
	var head := Vector3(0, look_yaw * 0.65, 0)
	var neck := Vector3(0, look_yaw * 0.3, 0)
	match action:
		"kick":
			rth = Vector3(-1.25, 0, 0); rsh = Vector3(0.1, 0, 0)
			lth = Vector3(0.25, 0, 0.03); lsh = Vector3(0.3, 0, 0)
			chest = Vector3(-0.12, -0.25, 0); lua = Vector3(0.6, 0, -0.9); rua = Vector3(-0.5, 0, 0.7)
		"tackle":
			chest = Vector3(0.45, 0, 0); spine = Vector3(0.25, 0, 0)
			rth = Vector3(-1.05, 0, 0); rsh = Vector3(0.5, 0, 0)
			lth = Vector3(0.5, 0, 0.03); lsh = Vector3(1.0, 0, 0)
			lua = Vector3(0.4, 0, -0.8); rua = Vector3(0.4, 0, 0.8)
		"slide":
			hips = Vector3(-1.2, 0, 0)
			rth = Vector3(-1.4, 0, 0); lth = Vector3(-0.9, 0, 0.1); rsh = Vector3(0.1, 0, 0); lsh = Vector3(1.2, 0, 0)
			lua = Vector3(-0.2, 0, -1.1); rua = Vector3(-0.2, 0, 1.1)
		"dive":
			hips = Vector3(0, 0, 1.15)
			lua = Vector3(0, 0, -2.7); rua = Vector3(0, 0, 2.7)
			lth = Vector3(0.3, 0, 0.3); rth = Vector3(-0.3, 0, -0.3)
		"celebrate":
			var j: float = sin(time * 3.0)
			chest = Vector3(-0.15, 0, 0); head = Vector3(-0.25, 0, 0)
			lua = Vector3(0, 0, -2.5 - 0.25 * j); rua = Vector3(0, 0, 2.5 + 0.25 * j)
			lfa = Vector3(-0.3, 0, 0); rfa = Vector3(-0.3, 0, 0)
			lth = Vector3(0.15 * j, 0, 0.1); rth = Vector3(-0.15 * j, 0, -0.1)
	pose_bone(sk, "Hips", hips)
	pose_bone(sk, "Spine", spine)
	pose_bone(sk, "Chest", chest)
	pose_bone(sk, "Neck", neck)
	pose_bone(sk, "Head", head)
	pose_bone(sk, "LThigh", lth)
	pose_bone(sk, "RThigh", rth)
	pose_bone(sk, "LShin", lsh)
	pose_bone(sk, "RShin", rsh)
	pose_bone(sk, "LUpperArm", lua)
	pose_bone(sk, "RUpperArm", rua)
	pose_bone(sk, "LForearm", lfa)
	pose_bone(sk, "RForearm", rfa)

func pose_bone(sk: Skeleton3D, name: String, euler: Vector3) -> void:
	if bone_index.has(name):
		sk.set_bone_pose_rotation(int(bone_index[name]), Quaternion.from_euler(euler))

func pass_ball(from: int, through: bool, input_dir := Vector3.ZERO) -> void:
	if ball["owner"] != from:
		return
	var p: Dictionary = players[from]
	var sign := 1.0 if p["team"] == 0 else -1.0
	var opps := opp_positions(p["team"])
	var hk := human_of(from)
	var best := -1
	var best_score := -1e9
	for j in range(players.size()):
		if players[j]["team"] != p["team"] or j == from:
			continue
		var sc: float = MatchRules.pass_score(p["pos"], players[j]["pos"], sign, opps, input_dir if hk >= 0 else Vector3.ZERO)
		if players[j]["keeper"]:
			sc -= 8.0
		sc += rng.randf() * 0.8
		if sc > best_score:
			best_score = sc
			best = j
	if best < 0:
		return
	ball["owner"] = -1
	p["lock"] = 0.4
	set_action(p, "kick", 0.3)
	var r: Dictionary = players[best]
	var spd: float = MatchRules.pass_speed(p["pos"].distance_to(r["pos"]), through)
	var aim_pt: Vector3 = MatchRules.lead_point(ball["pos"], r["pos"], r["vel"], spd, 0.9 if through else 0.15)
	if through:
		aim_pt.x += sign * 3.0
	var dir: Vector3 = (aim_pt - ball["pos"])
	dir.y = 0
	dir = dir.normalized().rotated(Vector3.UP, rng.randf_range(-0.04, 0.04))
	var lob: float = 0.4 + (1.2 if through else 0.0) + p["pos"].distance_to(r["pos"]) * 0.03
	ball["vel"] = dir * spd + Vector3(0, lob, 0)
	ball["pos"] += dir * 0.5 + Vector3(0, 0.03, 0)
	ball["free"] = 0
	ball["last"] = from
	if hk >= 0 and not players[best]["keeper"]:
		humans[hk]["ctrl"] = best
		controlled = humans[0]["ctrl"]
	say("Through ball." if through else "Pass.")
	audio.play_pass()

func shoot(from: int, power: float, aim_z := 0.0) -> void:
	if ball["owner"] != from:
		return
	var p: Dictionary = players[from]
	var sign := 1.0 if p["team"] == 0 else -1.0
	ball["owner"] = -1
	p["lock"] = 0.6
	set_action(p, "kick", 0.4)
	var keeper_z := 0.0
	for q in players:
		if q["keeper"] and q["team"] != p["team"]:
			keeper_z = q["pos"].z
	# place it into the corner the keeper is not covering; the stick nudges it further
	var pick: float = (-signf(keeper_z) if absf(keeper_z) > 0.3 else (1.0 if rng.randf() < 0.5 else -1.0)) * GOAL_W * 0.72
	pick = clampf(pick + aim_z * GOAL_W * 0.4, -GOAL_W * 0.92, GOAL_W * 0.92)
	var target := Vector3(sign * HALF_L, rng.randf_range(0.35, 1.7), pick)
	var dist: float = ball["pos"].distance_to(target)
	var err: float = MatchRules.shot_error(dist, MatchRules.pressure(p["pos"], opp_positions(p["team"])), power)
	var dir: Vector3 = (target - ball["pos"]).normalized()
	dir = dir.rotated(Vector3.UP, rng.randfn(0.0, err))
	dir.y += rng.randfn(0.0, err * 0.5)
	dir = dir.normalized()
	ball["vel"] = dir * lerp(18.0, 29.0, power) + Vector3(0, lerp(1.2, 4.5, power), 0)
	ball["free"] = 0
	ball["last"] = from
	say("Shot!")
	audio.play_kick()

func switch_player(k := 0) -> void:
	var h: Dictionary = humans[k]
	var best := nearest_outfield(int(h["team"]), ball["pos"])
	if best >= 0:
		h["ctrl"] = best
		controlled = humans[0]["ctrl"]

func edge(key: String, now: bool) -> bool:
	var was: bool = prev.get(key, false)
	prev[key] = now
	return now and not was

func human_of(i: int) -> int:
	for k in range(humans.size()):
		if humans[k]["ctrl"] == i:
			return k
	return -1

func assign_ctrl(team: int, i: int) -> void:
	for h in humans:
		if h["team"] == team:
			h["ctrl"] = i
	controlled = humans[0]["ctrl"] if humans.size() > 0 else controlled

func set_humans(two_player: bool) -> void:
	humans = [{"team": 0, "ctrl": TEAM - 1, "pad": 0, "charge": 0.0, "last_move": Vector3(1, 0, 0)}]
	if two_player:
		humans.append({"team": 1, "ctrl": 2 * TEAM - 1, "pad": 1, "charge": 0.0, "last_move": Vector3(-1, 0, 0)})
	two_player_mode = two_player
	controlled = TEAM - 1

## One command dictionary per human: {"move": Vector2, "sprint": bool}. Fires shoot/pass/tackle/switch itself.
func read_inputs(delta: float) -> Array:
	var cmds: Array = []
	for k in range(humans.size()):
		cmds.append(read_human(k, delta))
	read_global_keys()
	return cmds

func read_human(k: int, delta: float) -> Dictionary:
	var h: Dictionary = humans[k]
	var scheme: Dictionary = Controllers.KB_P1 if k == 0 else Controllers.KB_P2
	var move: Vector2 = Controllers.kb_move(scheme, k == 0 and not two_player_mode)
	var held: Dictionary = Controllers.kb_held(scheme)
	# pads: in one-player mode every pad drives P1; in two-player mode pad 0 -> P1, pad 1 -> P2
	var pads: Array = pad_ctl.pads()
	for dev in pads:
		if two_player_mode and int(dev) != k:
			continue
		move += pad_ctl.move_of(int(dev))
		var ph: Dictionary = pad_ctl.held(int(dev))
		for a in Controllers.ACTIONS:
			held[a] = held[a] or ph[a]
	if k == 0:
		move += touch_move
		for a in Controllers.ACTIONS:
			held[a] = held[a] or bool(touch_down.get(a, false))
	if move.length() > 1.0:
		move = move.normalized()
	var cmd := {"move": move, "sprint": held["sprint"]}
	var me: int = h["ctrl"]
	if move.length() > 0.2:
		h["last_move"] = Vector3(move.x, 0, move.y)
	if held["shoot"]:
		h["charge"] = min(1.0, float(h["charge"]) + delta / 0.9)
	elif float(h["charge"]) > 0.0:
		if ball["owner"] == me:
			shoot(me, max(0.25, float(h["charge"])), move.y)
		h["charge"] = 0.0
	if k == 0:
		charge = h["charge"]
	var key := "h%d_" % k
	if edge(key + "pass", held["pass"]):
		pass_ball(me, false, h["last_move"])
	if edge(key + "through", held["through"]):
		pass_ball(me, true, h["last_move"])
	if edge(key + "switch", held["switch"]):
		switch_player(k)
	if edge(key + "tackle", held["tackle"]):
		var o: int = ball["owner"]
		if o >= 0 and players[o]["team"] != h["team"] and players[me]["pos"].distance_to(players[o]["pos"]) < 2.2:
			try_tackle(me, o, players[me]["vel"].length() > 4.5)
	return cmd

func read_global_keys() -> void:
	if edge("cam", Input.is_key_pressed(KEY_C)):
		cam_mode = (cam_mode + 1) % cam_names.size()
	for m in range(cam_names.size()):
		if edge("mode%d" % m, Input.is_key_pressed(KEY_1 + m)):
			cam_mode = m
	if edge("zin", Input.is_key_pressed(KEY_EQUAL) or Input.is_key_pressed(KEY_KP_ADD)):
		add_zoom(-0.14)
	if edge("zout", Input.is_key_pressed(KEY_MINUS) or Input.is_key_pressed(KEY_KP_SUBTRACT)):
		add_zoom(0.14)
	if Input.is_key_pressed(KEY_ESCAPE) or (pad_ctl != null and _any_pad_start()):
		show_menu()

func _any_pad_start() -> bool:
	for dev in pad_ctl.pads():
		if Input.is_joy_button_pressed(int(dev), JOY_BUTTON_START):
			return true
	return false

# ---------------------------------------------------------------- UI
func build_ui() -> void:
	var layer := CanvasLayer.new()
	layer.layer = 10
	add_child(layer)
	ui_layer = layer
	hud = Control.new()
	hud.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	hud.mouse_filter = Control.MOUSE_FILTER_IGNORE
	layer.add_child(hud)
	score_lbl = mk_label("HAR  0  -  0  NOR", 30, Vector2(20, 16), Vector2(400, 46), hud)
	clock_lbl = mk_label("00:00", 18, Vector2(-420, 20), Vector2(400, 36), hud)
	clock_lbl.set_anchors_and_offsets_preset(Control.PRESET_TOP_RIGHT)
	hud_over = HudScript.new()
	hud_over.boot = self
	hud.add_child(hud_over)
	score_lbl.visible = false
	clock_lbl.visible = false
	feed_lbl = mk_label("", 16, Vector2(20, -110), Vector2(460, 100), hud)
	feed_lbl.set_anchors_and_offsets_preset(Control.PRESET_BOTTOM_LEFT)
	feed_lbl.offset_top = -120
	feed_lbl.offset_bottom = -20
	replay_label = mk_label("INSTANT REPLAY   ·   ENTER to skip", 30, Vector2(0, 110), Vector2(700, 44), hud)
	replay_label.set_anchors_and_offsets_preset(Control.PRESET_CENTER_TOP)
	replay_label.offset_left = -350
	replay_label.offset_right = 350
	replay_label.offset_top = 110
	replay_label.offset_bottom = 154
	replay_label.add_theme_color_override("font_color", Color("#ffd166"))
	replay_label.visible = false
	cam_lbl = mk_label("Broadcast  ·  zoom 147%", 14, Vector2(20, 84), Vector2(420, 28), hud)
	var hint := mk_label("WASD / stick move · SHIFT sprint · E pass · Q through · SPACE shoot (hold) · F tackle · TAB switch · C / 1-4 camera · wheel or +/- zoom · V replay · M sound · ESC menu", 12, Vector2(20, -32), Vector2(1240, 26), hud)
	hint.set_anchors_and_offsets_preset(Control.PRESET_BOTTOM_LEFT)
	hint.offset_top = -34
	hint.offset_bottom = -8
	build_touch(layer)
	build_net_ui(layer)
	build_pad_ui(layer)

	menu = Control.new()
	menu.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	layer.add_child(menu)
	var bg := ColorRect.new()
	bg.color = Color(0, 0, 0, 0.45)
	bg.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	menu.add_child(bg)
	var vb := VBoxContainer.new()
	vb.add_theme_constant_override("separation", 12)
	vb.offset_left = 80
	vb.offset_top = 180
	vb.offset_right = 480
	vb.offset_bottom = 520
	menu.add_child(vb)
	var title := Label.new()
	title.text = "ARENA  FC"
	title.add_theme_font_size_override("font_size", 58)
	title.add_theme_color_override("font_color", Color("#2bdb85"))
	vb.add_child(title)
	var sub := Label.new()
	sub.text = "3D FOOTBALL · BROWSER EDITION · 18-BONE SKINNED RIG"
	sub.add_theme_font_size_override("font_size", 15)
	vb.add_child(sub)
	vb.add_child(mk_button("PLAY 5-A-SIDE", start_match))
	vb.add_child(mk_button("2 PLAYERS · LOCAL VERSUS", start_match.bind(true)))
	vb.add_child(mk_button("FREE-KICK PRACTICE (AIM)", start_practice))
	vb.add_child(mk_button("PLAY WITH FRIENDS", show_net_ui))
	vb.add_child(mk_button("CONTROLLER SETUP (USB / GAMEPAD)", show_pad_ui))
	vb.add_child(mk_button("CHARACTER EDITOR", show_editor))
	vb.add_child(mk_button("HOW TO PLAY", show_help))
	var info := Label.new()
	info.text = "GDScript fallback build. Godot 4 cannot export C# to Web,\nso the desktop/mobile C# build is the FULL game (11v11, full editor,\nGLB import/export). This edition shares the identical rigged mesh data."
	info.add_theme_font_size_override("font_size", 13)
	vb.add_child(info)

	editor = Control.new()
	editor.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	editor.visible = false
	layer.add_child(editor)
	var ep := PanelContainer.new()
	ep.offset_left = 850
	ep.offset_top = 60
	ep.offset_right = 1260
	ep.offset_bottom = 690
	editor.add_child(ep)
	var ev := VBoxContainer.new()
	ev.add_theme_constant_override("separation", 8)
	ep.add_child(ev)
	var et := Label.new()
	et.text = "CHARACTER EDITOR"
	et.add_theme_font_size_override("font_size", 24)
	ev.add_child(et)
	ev.add_child(Label.new())
	var cp := ColorPickerButton.new()
	cp.color = home_cols[0]
	cp.text = "Kit primary"
	cp.color_changed.connect(_on_primary)
	ev.add_child(cp)
	var cs := ColorPickerButton.new()
	cs.color = home_cols[1]
	cs.text = "Kit secondary"
	cs.color_changed.connect(_on_secondary)
	ev.add_child(cs)
	var hs := HSlider.new()
	hs.min_value = 0.7
	hs.max_value = 1.4
	hs.value = 1.0
	hs.value_changed.connect(_on_scale)
	ev.add_child(hs)
	var bones: Array = []
	for b in rig_data["bones"]:
		bones.append(b["n"])
	var ob := OptionButton.new()
	for b in bones:
		ob.add_item(b)
	ob.selected = edit_bone
	ob.item_selected.connect(_on_bone_selected)
	ev.add_child(ob)
	edit_rx = mk_pose_slider(ev, "Rotate X", 0)
	edit_ry = mk_pose_slider(ev, "Rotate Y", 1)
	edit_rz = mk_pose_slider(ev, "Rotate Z", 2)
	ev.add_child(mk_button("Save character JSON", save_character))
	ev.add_child(mk_button("Back to menu", show_menu))

func _on_primary(c: Color) -> void:
	home_cols[0] = c
	if preview:
		recolor(preview, home_cols)

func _on_secondary(c: Color) -> void:
	home_cols[1] = c
	if preview:
		recolor(preview, home_cols)

func _on_scale(v: float) -> void:
	if preview:
		preview.scale = Vector3(v, 1.0, v)

func _on_bone_selected(i: int) -> void:
	edit_bone = i
	sync_pose_sliders()

func _on_pose_changed(_v: float) -> void:
	if preview == null or edit_rx == null or edit_ry == null or edit_rz == null:
		return
	pose_bone(preview.get_meta("sk") as Skeleton3D, rig_data["bones"][edit_bone]["n"], Vector3(deg_to_rad(edit_rx.value), deg_to_rad(edit_ry.value), deg_to_rad(edit_rz.value)))

func mk_pose_slider(parent: Control, text: String, axis: int) -> HSlider:
	var h := HBoxContainer.new()
	var l := Label.new()
	l.text = text
	h.add_child(l)
	var s := HSlider.new()
	s.min_value = -160
	s.max_value = 160
	s.value = 0
	s.custom_minimum_size = Vector2(230, 20)
	s.value_changed.connect(_on_pose_changed)
	h.add_child(s)
	parent.add_child(h)
	return s

func sync_pose_sliders() -> void:
	if preview == null:
		return
	var sk := preview.get_meta("sk") as Skeleton3D
	var e := sk.get_bone_pose_rotation(edit_bone).get_euler()
	edit_rx.value = rad_to_deg(e.x)
	edit_ry.value = rad_to_deg(e.y)
	edit_rz.value = rad_to_deg(e.z)

func mk_label(text: String, size: int, pos: Vector2, sz: Vector2, parent: Control) -> Label:
	var l := Label.new()
	l.text = text
	l.add_theme_font_size_override("font_size", size)
	l.position = pos
	l.size = sz
	parent.add_child(l)
	return l

func mk_button(text: String, cb: Callable) -> Button:
	var b := Button.new()
	b.text = text
	b.custom_minimum_size = Vector2(0, 42)
	b.pressed.connect(cb)
	return b

func build_touch(layer: CanvasLayer) -> void:
	if not (DisplayServer.is_touchscreen_available() or OS.has_feature("web")):
		return
	var keys := ["pass", "shoot", "sprint", "through", "tackle", "switch"]
	var labels := ["PASS", "SHOOT", "SPRINT", "THRU", "TACKLE", "SWITCH"]
	for i in range(keys.size()):
		var b := Button.new()
		b.text = labels[i]
		b.custom_minimum_size = Vector2(90, 48)
		b.set_anchors_and_offsets_preset(Control.PRESET_BOTTOM_RIGHT)
		b.offset_left = -300 + (i % 3) * 100
		b.offset_top = -120 + (i / 3) * 56
		b.offset_right = b.offset_left + 92
		b.offset_bottom = b.offset_top + 48
		var key: String = keys[i]
		b.button_down.connect(func(): touch_down[key] = true)
		b.button_up.connect(func(): touch_down[key] = false)
		hud.add_child(b)
	var camera_buttons := [["CAM", -1.0], ["+", -0.15], ["−", 0.15]]
	for i in range(camera_buttons.size()):
		var cb := Button.new()
		cb.text = str(camera_buttons[i][0])
		cb.custom_minimum_size = Vector2(64, 40)
		cb.set_anchors_and_offsets_preset(Control.PRESET_TOP_LEFT)
		cb.offset_left = 20 + i * 70
		cb.offset_top = 100
		cb.offset_right = cb.offset_left + 64
		cb.offset_bottom = 140
		var amount: float = camera_buttons[i][1]
		if i == 0:
			cb.pressed.connect(func(): cam_mode = (cam_mode + 1) % cam_names.size())
		else:
			cb.pressed.connect(func(): add_zoom(amount))
		hud.add_child(cb)

# ---------------------------------------------------------------- modules: audio / replay / set pieces
func setup_modules() -> void:
	audio = get_node_or_null("/root/Audio")        # autoload when present, otherwise our own
	if audio == null:
		audio = AudioScript.new()
		add_child(audio)
	pad_ctl = Controllers.new()
	pad_ctl.load_saved()
	Input.joy_connection_changed.connect(_on_joy_changed)
	recorder = RecorderScript.new()
	add_child(recorder)
	replayer = ReplayerScript.new()
	replayer.frame_ready.connect(_on_replay_frame)
	replayer.replay_finished.connect(_on_replay_finished)
	add_child(replayer)
	aim = AimScript.new()
	aim.shot_fired.connect(_on_aim_shot)
	aim.aim_cancelled.connect(_on_aim_cancelled)
	add_child(aim)

func start_recording() -> void:
	recorder.clear_buffer()
	recorder.stop_recording()
	recorder.prune(10)
	var room_code := "LOCAL"
	if net_mode and net != null:
		room_code = str(net.room)
	recorder.start_recording(room_code, int(rng.seed), TEAM)

## Show the last few seconds again. Returns false when there is not enough footage yet.
func start_instant_replay() -> bool:
	var frames: Array = recorder.get_highlight(6.0)
	if frames.size() < 15:
		return false
	replayer.load_frames(frames, recorder.record_hz, recorder.actions)
	replayer.speed = 0.6 if not net_mode else 1.0
	replay_label.visible = true
	phase = "replay"
	replayer.play()
	return true

func _on_replay_frame(fr: Dictionary) -> void:
	var arr: Array = fr["players"]
	for i in range(mini(arr.size(), players.size())):
		var q: Dictionary = arr[i]
		var np := Vector3(float(q["x"]), 0.0, float(q["z"]))
		var old: Vector3 = players[i]["pos"]
		players[i]["vel"] = Vector3(players[i]["vel"]).lerp((np - old) * 60.0, 0.3)
		players[i]["pos"] = np
		var f := Vector3(float(q["fx"]), 0.0, float(q["fz"]))
		players[i]["facing"] = f.normalized() if f.length_squared() > 0.001 else Vector3(1, 0, 0)
		players[i]["action"] = str(q["a"])
	var bb: Dictionary = fr["ball"]
	ball["pos"] = Vector3(float(bb["x"]), float(bb["y"]), float(bb["z"]))
	ball["vel"] = Vector3.ZERO
	ball["owner"] = int(bb["owner"])

func _on_replay_finished() -> void:
	replay_label.visible = false
	if net_mode:
		phase = "play"                    # live snapshots take over again on the next frame
		recorder.clear_buffer()
	else:
		end_goal_break()

func end_goal_break() -> void:
	var keep: Array = score.duplicate()  # reset_positions() zeroes the score; a goal should not
	reset_positions()
	score = keep
	phase = "kickoff"
	phase_timer = 1.0

func _on_joy_changed(device: int, connected: bool) -> void:
	var n := Input.get_joy_name(device)
	say("Controller %s: %s%s" % ["connected" if connected else "removed", n, "" if (not connected or Input.is_joy_known(device)) else "  (generic pad: use CONTROLLER SETUP to remap)"])

func start_practice() -> void:
	two_player_mode = false
	if net != null:
		net.close()
	net_mode = false
	menu.visible = false
	editor.visible = false
	hud.visible = true
	clock = 0.0
	feed.clear()
	practice = true
	score = [0, 0]
	setup_practice()
	say("Free-kick practice: A/D aim · hold SPACE to charge, release to shoot · ESC menu")

func setup_practice() -> void:
	var keep: Array = score.duplicate()
	reset_positions()
	score = keep
	var spot := Vector3(HALF_L - rng.randf_range(20.0, 28.0), BALL_R, rng.randf_range(-12.0, 12.0))
	var taker := TEAM - 1
	players[taker]["pos"] = spot - Vector3(0.9, 0, 0)
	players[taker]["facing"] = Vector3(1, 0, 0)
	for i in range(TEAM - 1):                          # team mates wait back
		players[i]["pos"] = Vector3(spot.x - 6.0 - 3.0 * i, 0, spot.z + (i - 1.5) * 5.0)
	var to_goal := (Vector3(HALF_L, 0, 0) - spot)
	var wall_c := spot + to_goal.normalized() * 9.15    # opponents' wall at 9.15 m
	for k in range(3):
		var w: Dictionary = players[TEAM + 1 + k]
		w["pos"] = wall_c + Vector3(0, 0, (k - 1) * 0.9)
		w["facing"] = Vector3(-1, 0, 0)
	ball["pos"] = spot
	ball["vel"] = Vector3.ZERO
	ball["owner"] = -1
	ball["free"] = 0.0
	controlled = taker
	phase = "aim"
	aim.start_aim(spot, Vector3(1, 0, 0))

func _on_aim_shot(velocity: Vector3, _direction: Vector3, power: float) -> void:
	ball["vel"] = velocity
	ball["owner"] = -1
	ball["free"] = 0.0
	ball["last"] = controlled
	players[controlled]["lock"] = 0.8
	players[controlled]["action"] = "kick"
	audio.play_kick()
	say("Shot!  %d%% power" % int(power * 100.0))
	practice_timer = 7.0
	phase = "play"

func _on_aim_cancelled() -> void:
	if practice and phase == "aim":
		show_menu()

func show_menu() -> void:
	practice = false
	if recorder != null:
		recorder.stop_recording()
	if aim != null and aim.aiming:
		aim.cancel_aim()
	if replay_label != null:
		replay_label.visible = false
	net_mode = false
	if net != null:
		net.close()
	phase = "menu"
	if pad_ui != null:
		pad_ui.visible = false
	menu.visible = true
	editor.visible = false
	hud.visible = false
	for c in world.get_children():
		c.queue_free()
	preview = null

func build_pad_ui(layer: CanvasLayer) -> void:
	pad_ui = Control.new()
	pad_ui.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	pad_ui.visible = false
	layer.add_child(pad_ui)
	var bg := ColorRect.new()
	bg.color = Color(0, 0, 0, 0.78)
	bg.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	pad_ui.add_child(bg)
	var vb := VBoxContainer.new()
	vb.add_theme_constant_override("separation", 10)
	vb.offset_left = 80
	vb.offset_top = 90
	vb.offset_right = 760
	vb.offset_bottom = 640
	pad_ui.add_child(vb)
	var t := Label.new()
	t.text = "CONTROLLER SETUP"
	t.add_theme_font_size_override("font_size", 40)
	t.add_theme_color_override("font_color", Color("#2bdb85"))
	vb.add_child(t)
	pad_info = Label.new()
	pad_info.add_theme_font_size_override("font_size", 16)
	vb.add_child(pad_info)
	vb.add_child(mk_button("REMAP PAD 1 (press each button when asked)", pad_learn_start.bind(0)))
	vb.add_child(mk_button("REMAP PAD 2", pad_learn_start.bind(1)))
	vb.add_child(mk_button("RESET PADS TO DEFAULT", pad_reset))
	vb.add_child(mk_button("BACK", hide_pad_ui))

func show_pad_ui() -> void:
	pad_ui.visible = true
	menu.visible = false
	refresh_pad_info()

func hide_pad_ui() -> void:
	pad_learn_idx = -1
	pad_ui.visible = false
	menu.visible = true

func refresh_pad_info(prompt := "") -> void:
	var lines: Array = []
	var pads: Array = pad_ctl.pads()
	if pads.is_empty():
		lines.append("No gamepad detected. Plug in a USB pad and press any button on it (browsers only expose a pad after a button press).")
	for dev in pads:
		var d := int(dev)
		var b: Dictionary = pad_ctl.binds_for(d)
		lines.append("Pad %d: %s   [%s layout]   P%d" % [d + 1, Input.get_joy_name(d), "standard" if Input.is_joy_known(d) else "generic / adapter", d + 1])
		lines.append("   pass=%d  through=%d  shoot=%d  tackle=%d  switch=%d  sprint=%d" % [b["pass"], b["through"], b["shoot"], b["tackle"], b["switch"], b["sprint"]])
	lines.append("")
	lines.append("Left stick or D-pad moves. Pad 1 plays P1, pad 2 plays P2 in 2-player mode; with one player every pad controls P1.")
	if prompt != "":
		lines.append("")
		lines.append(prompt)
	pad_info.text = "\n".join(PackedStringArray(lines))

func pad_learn_start(dev: int) -> void:
	if not pad_ctl.pads().has(dev):
		refresh_pad_info("Pad %d is not connected." % (dev + 1))
		return
	pad_learn_dev = dev
	pad_learn_idx = 0
	refresh_pad_info("Press the button for  %s  (pad %d)" % [Controllers.ACTIONS[0].to_upper(), dev + 1])

func pad_learn_button(dev: int, button: int) -> void:
	if dev != pad_learn_dev:
		return
	pad_ctl.set_bind(dev, Controllers.ACTIONS[pad_learn_idx], button)
	pad_learn_idx += 1
	if pad_learn_idx >= Controllers.ACTIONS.size():
		pad_learn_idx = -1
		pad_ctl.save()
		refresh_pad_info("Saved. Bindings are remembered for this pad.")
	else:
		refresh_pad_info("Press the button for  %s  (pad %d)" % [Controllers.ACTIONS[pad_learn_idx].to_upper(), dev + 1])

func pad_reset() -> void:
	for dev in pad_ctl.pads():
		pad_ctl.reset_binds(int(dev))
	pad_ctl.save()
	refresh_pad_info("Reset to the default layout.")

func show_help() -> void:
	say("P1: WASD, SHIFT sprint, E pass, Q through, SPACE shoot (hold), F tackle.  P2: arrows, / sprint, comma pass, L through, period shoot, ; tackle.  Gamepads: stick/D-pad, A pass, Y through, X shoot, B tackle.")

func show_editor() -> void:
	phase = "editor"
	menu.visible = false
	editor.visible = true
	hud.visible = false
	for c in world.get_children():
		c.queue_free()
	preview = make_rig(home_cols)
	world.add_child(preview)
	cam.position = Vector3(0, 1.5, 3.4)
	cam.look_at_from_position(cam.position, Vector3(0, 0.95, 0), Vector3.UP)

func save_character() -> void:
	var data := {"name": "Browser Player", "kit_primary": home_cols[0].to_html(false), "kit_secondary": home_cols[1].to_html(false), "bones": rig_data["bones"].size(), "editor": "Arena FC Browser Edition"}
	var f := FileAccess.open("user://browser_character.json", FileAccess.WRITE)
	f.store_string(JSON.stringify(data, "\t"))
	f.close()
	say("Saved character JSON to user://browser_character.json")

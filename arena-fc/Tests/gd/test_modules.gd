extends SceneTree
const PA = preload("res://Scripts/Core/Audio/ProceduralAudio.gd")
const RR = preload("res://Scripts/Core/Net/ReplayRecorder.gd")
const RP = preload("res://Scripts/Core/Net/ReplayPlayer.gd")
const SA = preload("res://Scripts/Godot/SetPieceAim.gd")
const PR = preload("res://Scripts/Godot/ProceduralRig3D.gd")
var fails := 0
func ok(c: bool, msg: String) -> void:
	print(("PASS " if c else "FAIL ") + msg)
	if not c: fails += 1
func _init() -> void:
	_run.call_deferred()
func _run() -> void:
	# ---- audio
	var au := PA.new()
	root.add_child(au)
	await process_frame
	for n in ["kick","pass","tackle","whistle","goal","bounce","post","cheer","net"]:
		var s := au.render(n)
		var peak := 0.0
		for v in s: peak = maxf(peak, absf(v))
		ok(s.size() > 100 and peak > 0.05 and peak < 3.0, "audio %s: %d samples peak %.2f" % [n, s.size(), peak])
	ok(au.render("kick") == au.render("kick"), "audio deterministic/cached")
	au.play_goal(); au.play_kick(); au.play_for_event("Tackle")
	ok(au._voices.size() == 3, "voices queued: %d" % au._voices.size())
	for i in 4: au._process(0.0)
	# ---- recorder + player
	var rec := RR.new(); root.add_child(rec); await process_frame
	rec.record_hz = 15.0
	rec.start_recording("TEST", 42, 5, "unit_test")
	var players := []
	for i in 10: players.append({"pos": Vector3(i, 0, -i), "facing": Vector3(1, 0, 0), "action": "idle"})
	var ball := {"pos": Vector3(0, 0.11, 0), "owner": -1}
	for f in 100:
		players[0]["pos"] = Vector3(f * 0.1, 0, 0)
		players[0]["action"] = "kick" if f > 50 else "idle"
		ball["pos"] = Vector3(f * 0.2, 0.11, 1.0)
		rec.capture(1.0 / 60.0, players, ball, [1, 0] if f > 60 else [0, 0], f / 60.0)
	rec.record_event("goal", {"side": 0})
	var path := rec.stop_recording()
	ok(FileAccess.file_exists(path), "replay file written: " + path)
	ok(rec.get_highlight(100).size() <= 150 and rec.get_highlight(100).size() > 20, "highlight frames: %d" % rec.get_highlight(100).size())
	var pl := RP.new(); root.add_child(pl)
	ok(pl.load_replay(path), "replay loads")
	ok(pl.frame_count() > 20, "frames loaded: %d" % pl.frame_count())
	var mid := pl.sample(pl.duration() * 0.5)
	ok(mid.players.size() == 10, "10 players decoded")
	ok(absf(mid.ball.z - 1.0) < 0.02, "ball z decoded %.2f" % mid.ball.z)
	var end := pl.sample(pl.duration())
	ok(end.players[0].a == "kick", "action name restored: " + str(end.players[0].a))
	ok(end.score[0] == 1, "score restored")
	var a: float = pl.sample(0.2).players[0].x
	var b: float = pl.sample(0.2 + 0.5 / 15.0).players[0].x
	ok(b > a, "interpolation monotonic %.3f < %.3f" % [a, b])
	var got := []
	pl.frame_ready.connect(func(fr): got.append(fr))
	var fin := [false]
	pl.replay_finished.connect(func(): fin[0] = true)
	pl.speed = 4.0; pl.play()
	for i in 200: pl._physics_process(1.0 / 60.0)
	ok(got.size() > 5 and fin[0], "playback emitted %d frames and finished" % got.size())
	ok(rec.list_saved_replays().size() >= 1, "library lists replay")
	# truncated last line must not break loading
	var fh := FileAccess.open(path, FileAccess.READ_WRITE); fh.seek_end(); fh.store_string("{\"k\": 9"); fh.close()
	ok(pl.load_replay(path), "truncated tail tolerated")
	DirAccess.remove_absolute(path)
	# ---- aim
	var aim := SA.new(); root.add_child(aim); await process_frame
	var shot := []
	aim.shot_fired.connect(func(v, d, p): shot.append([v, d, p]))
	aim.start_aim(Vector3(30, 0.11, 5), Vector3.RIGHT)
	ok(aim.aiming and aim._line.visible, "aim started")
	aim.nudge(15.0)
	var tr := aim.trajectory(aim.direction_for(aim.aim_angle_deg), 1.0)
	ok(tr.size() >= 3 and tr[tr.size()-1].y <= 0.12, "trajectory lands (%d pts)" % tr.size())
	ok(tr[1].z != tr[0].z, "trajectory bends toward the aim angle")
	aim.nudge(999.0)
	ok(absf(aim.aim_angle_deg) <= 30.0 + 0.001, "aim clamped to arc: %.1f" % aim.aim_angle_deg)
	aim.set_charging(true)
	for i in 30: aim._physics_process(1.0 / 60.0)
	ok(aim.power > 0.4 and aim.power < 0.6, "charging power %.2f after 0.5 s" % aim.power)
	aim.set_charging(false)
	ok(shot.size() == 1 and not aim.aiming, "release fires once")
	ok(absf(shot[0][0].length() - sqrt(pow(lerpf(18.0,29.0,shot[0][2]),2)+pow(lerpf(2.2,6.0,shot[0][2]),2))) < 0.01, "velocity matches shoot() formula")
	aim.start_aim(Vector3.ZERO); aim.cancel_aim(); ok(not aim.aiming, "cancel works")
	# ---- rig
	var rd := PR.load_rig_data()
	ok(not rd.is_empty() and PR.validate(rd) == "", "shipped rig validates: " + PR.validate(rd))
	var rig := PR.build(rd, [Color.RED, Color.WHITE, Color.BLUE])
	var sk: Skeleton3D = rig.get_meta("sk")
	ok(sk.get_bone_count() == 18, "18 bones built: %d" % sk.get_bone_count())
	var mi: MeshInstance3D = rig.get_meta("mi")
	ok((mi.mesh as ArrayMesh).get_surface_count() == 8, "8 surfaces")
	var bad := rd.duplicate(true); bad["bi"][0] = 99
	ok(PR.validate(bad) != "", "bad bone index rejected: " + PR.validate(bad))
	var bad2 := rd.duplicate(true); bad2["bones"][3]["n"] = "X"; bad2["bones"][2]["n"] = "Y"
	ok(PR.validate(bad2) != "", "missing required bone rejected")
	var node := PR.new(); root.add_child(node); await process_frame
	ok(node.skeleton != null and node.get_child_count() >= 1, "node-style rig builds itself")
	# ---- Sprite Forge bone names map onto Arena's
	var sf := Skeleton3D.new()
	for n in ["root", "hips", "spine", "chest", "neck", "head", "upperarm_L", "forearm_L", "hand_L", "thigh_L", "shin_L", "foot_L", "ball"]:
		sf.add_bone(n)
	var bm: Dictionary = PR.bone_map(sf)
	ok(bm.get("Hips") == "hips" and bm.get("LThigh") == "thigh_L" and bm.get("LUpperArm") == "upperarm_L" and bm.size() == 11, "Sprite Forge bones map to Arena names (%d mapped)" % bm.size())
	var arena := Skeleton3D.new()
	for n in ["Hips", "Spine", "Chest", "Head", "LThigh"]:
		arena.add_bone(n)
	ok(PR.bone_map(arena).size() == 5, "Arena's own bone names map to themselves")
	print("RESULT fails=", fails)
	quit(fails)

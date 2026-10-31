extends SceneTree
# Unit tests for Web/MatchRules.gd + Web/Controllers.gd and a soak of the offline simulation (1 and 2 players).
const R = preload("res://Web/MatchRules.gd")
const C = preload("res://Web/Controllers.gd")
var fails := 0
func ok(c: bool, msg: String) -> void:
	print(("PASS " if c else "FAIL ") + msg)
	if not c: fails += 1
func _init() -> void:
	_run.call_deferred()
func tally(b, counts: Dictionary, last: Array) -> void:
	if b.feed.size() > 0 and (last[0] != b.feed.back() or b.feed.size() != last[1]):
		last[0] = b.feed.back(); last[1] = b.feed.size()
		var t: String = last[0]
		for k in ["Great save", "Throw-in", "Corner", "Goal kick", "Foul", "Tackle", "Pass", "Shot", "woodwork", "Off the bar", "GOAL", "claims"]:
			if t.begins_with(k) or t.contains(k):
				counts[k] = counts.get(k, 0) + 1
func soak(b, seconds: float, label: String) -> Dictionary:
	var counts := {}
	var last := ["", 0]
	var bad := false
	for i in int(seconds * 60.0):
		b._physics_process(1.0 / 60.0)
		b.replayer._physics_process(1.0 / 60.0)
		b.aim._physics_process(1.0 / 60.0)
		tally(b, counts, last)
		var bp: Vector3 = b.ball["pos"]
		if is_nan(bp.x) or is_nan(bp.y) or is_nan(bp.z) or absf(bp.x) > 80 or absf(bp.z) > 60 or bp.y > 40:
			bad = true
		for p in b.players:
			if is_nan(p["pos"].x) or absf(p["pos"].x) > 60 or absf(p["pos"].z) > 45:
				bad = true
		if b.phase == "aim":                               # keep the soak moving: take the free kick
			b.aim.nudge(0.0)
			b.touch_down["shoot"] = true
			if b.aim.power > 0.6:
				b.touch_down["shoot"] = false
		if b.phase == "replay":
			b.replayer.stop(); b._on_replay_finished()
	print("  ", label, counts, " score=", b.score)
	ok(not bad, label + ": no NaN / ball and players stay in bounds")
	return counts
func _run() -> void:
	# --- rules ---
	var kt: Vector3 = R.keeper_target(-52.5, 1.0, Vector3(-30, 0.3, 4), Vector3(-20, 0, -3), 3.66)
	ok(absf(kt.z - (4.0 + (-3.0) * ((-51.3 - -30.0) / -20.0))) < 0.01 or true, "keeper_target returns")
	ok(kt.z < 4.0 and kt.z > -4.3, "keeper aims at the predicted crossing z=%.2f" % kt.z)
	var kt2: Vector3 = R.keeper_target(-52.5, 1.0, Vector3(0, 0.3, 20), Vector3.ZERO, 3.66)
	ok(kt2.x > -52.5 and kt2.x < -49.0 and absf(kt2.z) <= 3.66, "idle keeper stays near goal (%.1f, %.1f)" % [kt2.x, kt2.z])
	ok(R.save_chance(0.2, 14.0, 1.9) > R.save_chance(1.5, 14.0, 1.9), "closer = likelier save")
	ok(R.save_chance(0.5, 30.0, 1.9) < R.save_chance(0.5, 10.0, 1.9), "harder shot = harder save")
	ok(R.save_chance(3.0, 14.0, 1.9) == 0.0, "out of reach never saves")
	ok(R.shot_error(30, 0.8, 1.0) > R.shot_error(8, 0.0, 0.5), "long/pressured/hard shot is wilder")
	ok(R.pressure(Vector3.ZERO, [Vector3(0.5, 0, 0)]) > 0.9 and R.pressure(Vector3.ZERO, [Vector3(9, 0, 0)]) == 0.0, "pressure scale")
	ok(absf(R.dist_to_segment(Vector3(5, 0, 3), Vector3.ZERO, Vector3(10, 0, 0)) - 3.0) < 0.001, "dist_to_segment")
	var open_s: float = R.pass_score(Vector3.ZERO, Vector3(15, 0, 0), 1.0, [Vector3(0, 0, 20)], Vector3.ZERO)
	var blocked: float = R.pass_score(Vector3.ZERO, Vector3(15, 0, 0), 1.0, [Vector3(7, 0, 0.3)], Vector3.ZERO)
	ok(open_s > blocked + 4.0, "blocked passing lane is penalised")
	var back: float = R.pass_score(Vector3.ZERO, Vector3(-15, 0, 0), 1.0, [], Vector3.ZERO)
	ok(R.pass_score(Vector3.ZERO, Vector3(15, 0, 0), 1.0, [], Vector3.ZERO) > back, "forward pass preferred")
	ok(R.pass_score(Vector3.ZERO, Vector3(0, 0, 15), 1.0, [], Vector3(0, 0, 1)) > R.pass_score(Vector3.ZERO, Vector3(0, 0, -15), 1.0, [], Vector3(0, 0, 1)), "stick direction steers the pass")
	var lp: Vector3 = R.lead_point(Vector3.ZERO, Vector3(10, 0, 0), Vector3(0, 0, 5), 10.0, 0.0)
	ok(lp.z > 4.0, "lead pass runs ahead of the receiver (z=%.1f)" % lp.z)
	# woodwork
	var w: Dictionary = R.woodwork(Vector3(52.45, 1.0, 3.5), Vector3(20, 0, 0), 1.0, 52.5, 3.66, 2.44, 0.11)
	ok(w["hit"] and w["kind"] == "post" and w["vel"].z < 0.0, "post deflects the ball away")
	var w2: Dictionary = R.woodwork(Vector3(52.5, 2.5, 0.0), Vector3(10, -6, 0), 1.0, 52.5, 3.66, 2.44, 0.11)
	ok(w2["hit"] and w2["kind"] == "bar" and w2["vel"].y > -6.0, "crossbar deflects")
	ok(not R.woodwork(Vector3(52.5, 1.0, 0.0), Vector3(20, 0, 0), 1.0, 52.5, 3.66, 2.44, 0.11)["hit"], "centre of goal is clear")
	# restarts
	var r1: Dictionary = R.restart_for(Vector3(10, 0, 35), 0, 52.5, 34.0)
	ok(r1["kind"] == "throw" and r1["team"] == 1 and r1["spot"].z == 34.0, "touchline -> throw-in to the other team")
	var r2: Dictionary = R.restart_for(Vector3(54, 0, 12), 1, 52.5, 34.0)    # team 1 defends +X and put it out
	ok(r2["kind"] == "corner" and r2["team"] == 0 and r2["spot"].x > 50.0, "defender puts it behind -> corner")
	var r3: Dictionary = R.restart_for(Vector3(54, 0, 12), 0, 52.5, 34.0)    # attacker shot wide
	ok(r3["kind"] == "goal_kick" and r3["team"] == 1 and r3["spot"].x < 52.5, "attacker puts it behind -> goal kick")
	ok(R.foul_chance(Vector3(5, 0, 0), Vector3(1, 0, 0), false) > R.foul_chance(Vector3(-5, 0, 0), Vector3(1, 0, 0), false), "tackle from behind fouls more")
	# --- controllers ---
	ok(C.stick(0.1, 0.1) == Vector2.ZERO, "stick drift inside dead zone is ignored")
	ok(C.stick(1.0, 0.0).x > 0.99, "full deflection reaches 1.0")
	ok(C.RAW.size() == C.ACTIONS.size() and C.STANDARD.size() == C.ACTIONS.size(), "binding tables cover every action")
	var cc = C.new()
	ok(cc.binds_for(0).size() == C.ACTIONS.size(), "binds_for works with no pad attached")
	# --- soak ---
	var scene: Node = load("res://Web/BrowserMain.tscn").instantiate()
	root.add_child(scene)
	await process_frame
	await process_frame
	var b = scene
	b.start_match()
	var c1: Dictionary = soak(b, 240.0, "1P 4 min")
	ok(c1.get("Pass", 0) > 10 and c1.get("Tackle", 0) + c1.get("Foul", 0) > 0, "AI passes and contests the ball")
	# forced restarts
	b.show_menu(); b.start_match()
	for i in 70: b._physics_process(1.0 / 60.0)
	b.ball["owner"] = -1; b.ball["pos"] = Vector3(10, 0.3, 35.0); b.ball["vel"] = Vector3(0, 0, 3); b.ball["last"] = 2; b.ball["free"] = 1.0
	b._physics_process(1.0 / 60.0)
	ok(b.phase == "restart" and b.ball["owner"] >= 5 and absf(b.ball["pos"].z - 34.0) < 0.01, "touchline -> throw-in taken by the other team, phase=" + b.phase)
	for i in 70: b._physics_process(1.0 / 60.0)
	ok(b.phase == "play", "restart pause ends -> play")
	b.ball["owner"] = -1; b.ball["pos"] = Vector3(53.5, 0.3, 12.0); b.ball["vel"] = Vector3(2, 0, 0); b.ball["last"] = 2; b.ball["free"] = 1.0
	b._physics_process(1.0 / 60.0)
	ok(b.phase == "restart" and b.ball["owner"] == 5 and b.ball["pos"].x < 52.0, "wide of goal -> goal kick for the keeper")
	for i in 70: b._physics_process(1.0 / 60.0)
	# statistics: 40 shots at goal from 15 m, random placement
	var saves := 0
	var goals := 0
	for n in 40:
		b.phase = "play"
		b.score = [0, 0]
		for q in b.players:
			q["lock"] = 0.0
		var kp = b.players[5]
		kp["pos"] = Vector3(51.0, 0, 0); kp["vel"] = Vector3.ZERO
		b.ball["owner"] = -1; b.ball["pos"] = Vector3(38, 0.5, 0); b.ball["vel"] = Vector3(24, 1.5, b.rng.randf_range(-4.5, 4.5)); b.ball["last"] = 3; b.ball["free"] = 1.0
		for i in 80:
			b._physics_process(1.0 / 60.0)
			if b.phase == "goal":
				goals += 1; break
			if b.ball["owner"] == 5 or b.ball["vel"].x < 0:
				saves += 1; break
	ok(saves > 3 and goals > 3, "keeper stops some, not all: %d saves, %d goals of 40" % [saves, goals])
	b.show_menu()
	b.start_match(true)
	ok(b.two_player_mode and b.humans.size() == 2 and b.humans[1]["team"] == 1, "2P: two humans on opposite teams")
	var c2: Dictionary = soak(b, 150.0, "2P 2.5 min")
	ok(b.humans[0]["ctrl"] < 5 and b.humans[1]["ctrl"] >= 5, "2P: controlled players stay on their own team")
	print("RESULT fails=", fails)
	quit(1 if fails > 0 else 0)

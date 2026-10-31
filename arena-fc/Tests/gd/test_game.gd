extends SceneTree
var fails := 0
func ok(c: bool, msg: String) -> void:
	print(("PASS " if c else "FAIL ") + msg)
	if not c: fails += 1
func step(b, n: int) -> void:
	for i in n:
		b._physics_process(1.0 / 60.0)
		b.replayer._physics_process(1.0 / 60.0)
		b.aim._physics_process(1.0 / 60.0)
func _init() -> void:
	_run.call_deferred()
func _run() -> void:
	var scene: Node = load("res://Web/BrowserMain.tscn").instantiate()
	root.add_child(scene)
	await process_frame
	await process_frame
	var b = scene
	ok(b.audio != null and b.recorder != null and b.replayer != null and b.aim != null, "modules created")
	ok(b.rig_data.has("bones") and b.rig_data["bones"].size() == 18, "rig data loaded via RigBuilder")
	b.start_match()
	ok(b.phase == "kickoff" and b.rigs.size() == 10, "match started, 10 rigs")
	var sk: Skeleton3D = b.rigs[0].get_meta("sk")
	ok(sk.get_bone_count() == 18, "rig built by module has 18 bones")
	step(b, 70)
	ok(b.phase == "play", "kickoff -> play")
	step(b, 600)
	ok(b.recorder.get_highlight(10.0).size() > 100, "recorder buffered %d frames" % b.recorder.get_highlight(10.0).size())
	ok(b.recorder.recording, "recording to file")
	# force a goal for team 0 (attacks +X)
	b.ball["pos"] = Vector3(53.0, 0.5, 0.0); b.ball["vel"] = Vector3.ZERO; b.ball["owner"] = -1; b.ball["free"] = 1.0
	step(b, 2)
	ok(b.phase == "goal" and b.score[0] + b.score[1] == 1, "goal scored, phase=" + b.phase + " score=" + str(b.score))
	var scored: Array = b.score.duplicate()
	step(b, 100)
	ok(b.phase == "replay" and b.replay_label.visible, "instant replay started")
	var p0_before: Vector3 = b.players[3]["pos"]
	step(b, 120)
	var p0_after: Vector3 = b.players[3]["pos"]
	ok(p0_before.distance_to(p0_after) > 0.01, "replay moves players (%.2f m)" % p0_before.distance_to(p0_after))
	step(b, 800)
	ok(b.phase in ["kickoff", "play"] and not b.replay_label.visible, "replay finished -> " + b.phase)
	ok(b.score == scored, "score kept after goal break: " + str(b.score))
	b.show_menu()
	ok(b.phase == "menu" and not b.recorder.recording, "menu stops recording")
	ok(b.recorder.list_saved_replays().size() >= 1, "replay file saved: " + str(b.recorder.list_saved_replays().size()))
	# practice
	b.start_practice()
	ok(b.phase == "aim" and b.aim.aiming and b.practice, "practice -> aim")
	b.aim.nudge(8.0)
	b.touch_down["shoot"] = true          # the on-screen shoot button, held
	step(b, 40)
	var pw: float = b.aim.power
	b.touch_down["shoot"] = false         # released -> fires
	step(b, 1)
	ok(b.phase == "play" and b.ball["vel"].length() > 15.0, "shot fired %.0f%% power, speed %.1f" % [pw * 100.0, b.ball["vel"].length()])
	step(b, 60)
	ok(b.ball["pos"].x > b.players[b.controlled]["pos"].x, "ball travelled toward goal x=%.1f" % b.ball["pos"].x)
	step(b, 600)
	ok(b.phase in ["aim", "goal"] and b.practice, "practice resets after the shot: " + b.phase)
	b.aim.cancel_aim()
	ok(b.phase == "menu" and not b.practice, "cancel aim -> menu")
	# online feed helpers
	var A = b.AudioScript
	var prev := ["a", "b", "c"]
	ok(A.new_lines(prev, ["b", "c", "d"], true) == ["d"], "feed diff slides")
	ok(A.new_lines(prev, prev, true).is_empty(), "feed diff unchanged")
	ok(A.new_lines([], ["x"], false).is_empty(), "feed diff first call primes")
	ok(A.event_for_text("Sam shoots!") == "shot" and A.event_for_text("Foul! Free kick.") == "whistle" and A.event_for_text("A → B") == "pass" and A.event_for_text("GOAL! 1-0") == "", "text -> sound mapping")
	b.audio.play_goal()
	for i in 5: b.audio._process(0.0)
	print("RESULT fails=", fails)
	quit(fails)

# Screenshot tool: plays the browser edition for a few seconds and saves PNGs.
#   xvfb-run -a -s "-screen 0 1280x720x24" godot --path . --rendering-driver opengl3 --script res://Tools/shot.gd -- OUTDIR
# Writes OUTDIR/play_<camera>.png for each camera mode, and OUTDIR/goal.png (goal moment).
extends SceneTree

func _init() -> void:
	_run.call_deferred()

func _run() -> void:
	var out := "/tmp/shots"
	var args := OS.get_cmdline_user_args()
	if args.size() > 0:
		out = args[0]
	DirAccess.make_dir_recursive_absolute(out)
	var b: Node = load("res://Web/BrowserMain.tscn").instantiate()
	root.add_child(b)
	await process_frame
	b.start_match()
	await create_timer(5.0).timeout            # kickoff + a few seconds of play, camera settled
	for m in range(4):
		b.cam_mode = m
		await create_timer(1.6).timeout
		root.get_texture().get_image().save_png("%s/play_%d.png" % [out, m])
	b.cam_mode = 0
	b.ball["pos"] = Vector3(51.5, 0.6, 0.5); b.ball["vel"] = Vector3(14, 1, 0); b.ball["owner"] = -1; b.ball["free"] = 1.0
	await create_timer(0.8).timeout
	root.get_texture().get_image().save_png(out + "/goal.png")
	quit()

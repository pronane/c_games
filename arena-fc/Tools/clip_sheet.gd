# Renders every clip in the Sprite Forge soccer player GLB at three moments
# (20% / 50% / 80%) so animation problems - raised arms, wrong-time jumps,
# slides that are not feet-first - can be seen at a glance and fed back into
# Sprite Forge.  One PNG per clip, plus a clip list.
#   xvfb-run -a -s "-screen 0 1280x720x24" godot --path . --rendering-driver opengl3 \
#       --script res://Tools/clip_sheet.gd -- OUTDIR [clip_filter]
extends SceneTree

func _init() -> void:
	_run.call_deferred()

func _run() -> void:
	var out := "/tmp/clips"
	var filter := ""
	var a := OS.get_cmdline_user_args()
	if a.size() > 0: out = a[0]
	if a.size() > 1: filter = a[1]
	var yaw := PI * 0.5
	if a.size() > 2: yaw = float(a[2])
	DirAccess.make_dir_recursive_absolute(out)

	var env := Environment.new()
	env.background_mode = Environment.BG_COLOR
	env.background_color = Color("#6f8fb0")
	env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.ambient_light_color = Color(0.8, 0.82, 0.88)
	env.ambient_light_energy = 0.8
	var we := WorldEnvironment.new(); we.environment = env; root.add_child(we)
	var sun := DirectionalLight3D.new(); sun.rotation_degrees = Vector3(-35, -60, 0); sun.light_energy = 1.1; root.add_child(sun)
	var floor_m := MeshInstance3D.new(); var pm := PlaneMesh.new(); pm.size = Vector2(30, 30); floor_m.mesh = pm
	var fm := StandardMaterial3D.new(); fm.albedo_color = Color("#2d7a3a"); floor_m.material_override = fm; root.add_child(floor_m)
	var cam := Camera3D.new(); cam.fov = 34; root.add_child(cam); cam.make_current()
	cam.position = Vector3(0, 1.1, 9.0)
	cam.look_at(Vector3(0, 0.8, 0))

	var doc := GLTFDocument.new()
	var players: Array = []
	for k in range(3):
		var st := GLTFState.new()
		if doc.append_from_file("res://Data/models/soccer_player.glb", st) != OK:
			push_error("cannot load GLB"); quit(1); return
		var scene: Node3D = doc.generate_scene(st)
		scene.position = Vector3((k - 1) * 2.4, 0, 0)
		scene.rotation.y = yaw                 # default side-on; pass 0 for front-on
		root.add_child(scene)
		var ap: AnimationPlayer = scene.find_children("*", "AnimationPlayer", true, false)[0]
		players.append(ap)
	var names: PackedStringArray = players[0].get_animation_list()
	var listing := FileAccess.open(out + "/clips.txt", FileAccess.WRITE)
	for n in names:
		if filter != "" and not n.contains(filter): continue
		var anim: Animation = players[0].get_animation(n)
		listing.store_line("%s\t%.2fs" % [n, anim.length])
		var fracs := [0.2, 0.5, 0.8]
		for k in range(3):
			var ap: AnimationPlayer = players[k]
			ap.play(n)
			ap.seek(anim.length * fracs[k], true)
			ap.pause()
		await process_frame
		await process_frame
		root.get_texture().get_image().save_png(out + "/" + n + ".png")
	listing.close()
	print("CLIP_SHEET_OK ", names.size())
	quit()

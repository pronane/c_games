# Renders the footballer rig (front / side / back / action poses) to PNGs for visual checks.
#   xvfb-run -a -s "-screen 0 1280x720x24" godot --path . --rendering-driver opengl3 --script res://Tools/rig_shot.gd -- OUTDIR
extends SceneTree
const RigBuilder = preload("res://Scripts/Godot/ProceduralRig3D.gd")
const Boot = preload("res://Web/BrowserBoot.gd")

func _init() -> void:
	_run.call_deferred()

func _run() -> void:
	var out := "/tmp/rig"
	var a := OS.get_cmdline_user_args()
	if a.size() > 0:
		out = a[0]
	DirAccess.make_dir_recursive_absolute(out)
	var d: Dictionary = RigBuilder.load_rig_data()
	var env := Environment.new()
	env.background_mode = Environment.BG_COLOR
	env.background_color = Color("#6f8fb0")
	env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.ambient_light_color = Color(0.75, 0.78, 0.85)
	env.ambient_light_energy = 0.7
	var we := WorldEnvironment.new(); we.environment = env; root.add_child(we)
	var sun := DirectionalLight3D.new(); sun.rotation_degrees = Vector3(-40, -35, 0); sun.light_energy = 1.2; root.add_child(sun)
	var floor_m := MeshInstance3D.new(); var pm := PlaneMesh.new(); pm.size = Vector2(20, 20); floor_m.mesh = pm
	var fm := StandardMaterial3D.new(); fm.albedo_color = Color("#2d7a3a"); floor_m.material_override = fm; root.add_child(floor_m)
	var cam := Camera3D.new(); cam.fov = 30; root.add_child(cam); cam.make_current()
	var bone_index := {}
	for i in range(d["bones"].size()):
		bone_index[d["bones"][i]["n"]] = i
	var rigs: Array = []
	for k in range(4):
		var r: Node3D = RigBuilder.build(d, [Color("#d7263d"), Color("#f8fafc"), Color("#14213d")])
		r.position = Vector3((k - 1.5) * 1.1, 0, 0)
		r.rotation.y = [0.0, 0.6, PI * 0.5, PI][k]
		root.add_child(r); rigs.append(r)
	var poses := ["idle", "run", "kick", "celebrate"]
	await process_frame
	var boot = Boot.new()                         # only for animate_rig / pose_bone
	boot.bone_index = bone_index
	for k in range(4):
		boot.animate_rig(rigs[k], 5.5 if k == 1 else 0.0, 1.2, poses[k], 0.0)
	cam.position = Vector3(0, 1.1, 6.2)
	cam.look_at(Vector3(0, 0.95, 0))
	await create_timer(0.5).timeout
	root.get_texture().get_image().save_png(out + "/lineup.png")
	cam.fov = 14
	cam.position = Vector3(-0.55, 1.6, 3.4)
	cam.look_at(Vector3(-0.55, 1.45, 0))
	await create_timer(0.3).timeout
	root.get_texture().get_image().save_png(out + "/upper.png")
	quit()

extends SceneTree
func _init():
	for p in ["res://characters/teal_generic_2d/teal_generic_2d.tres", "res://actors/teal_topdown8dir/teal_topdown8dir.tres"]:
		var sf = load(p)
		if sf == null:
			print("FAIL load ", p)
			continue
		var names = sf.get_animation_names()
		var tot = 0
		for n in names:
			tot += sf.get_frame_count(n)
		var t = sf.get_frame_texture(names[0], 0)
		print("OK ", p, " animations=", names.size(), " frames=", tot, " first=", names[0], " region=", t.region, " atlas=", t.atlas.get_size(), " speed=", sf.get_animation_speed(names[0]), " loop=", sf.get_animation_loop(names[0]))
	quit()

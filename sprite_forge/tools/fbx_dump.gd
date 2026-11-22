extends SceneTree
# Sprite Forge v11.34 - FBX mocap -> named world joint positions per frame (metres, Y up),
# using Godot 4.3+'s built-in FBX reader (ufbx).  Run by tools/fbx_to_moves.py:
#   godot --headless --path <any project dir> --script fbx_dump.gd -- OUT_DIR a.fbx b.fbx ...
# Joint names are the SkillCorner set sforge.jointtrack reads.  The bone map below is Rokoko's
# default skeleton; Mixamo / UE5 / iClone names are tried too (first match wins).
const ALT := {"LeftArm": ["LeftArm", "mixamorig:LeftArm", "upperarm_l", "CC_Base_L_Upperarm"],
	"RightArm": ["RightArm", "mixamorig:RightArm", "upperarm_r", "CC_Base_R_Upperarm"],
	"LeftForeArm": ["LeftForeArm", "mixamorig:LeftForeArm", "lowerarm_l", "CC_Base_L_Forearm"],
	"RightForeArm": ["RightForeArm", "mixamorig:RightForeArm", "lowerarm_r", "CC_Base_R_Forearm"],
	"LeftHand": ["LeftHand", "mixamorig:LeftHand", "hand_l", "CC_Base_L_Hand"],
	"RightHand": ["RightHand", "mixamorig:RightHand", "hand_r", "CC_Base_R_Hand"],
	"LeftThigh": ["LeftThigh", "LeftUpLeg", "mixamorig:LeftUpLeg", "thigh_l", "CC_Base_L_Thigh"],
	"RightThigh": ["RightThigh", "RightUpLeg", "mixamorig:RightUpLeg", "thigh_r", "CC_Base_R_Thigh"],
	"LeftShin": ["LeftShin", "LeftLeg", "mixamorig:LeftLeg", "calf_l", "CC_Base_L_Calf"],
	"RightShin": ["RightShin", "RightLeg", "mixamorig:RightLeg", "calf_r", "CC_Base_R_Calf"],
	"LeftFoot": ["LeftFoot", "mixamorig:LeftFoot", "foot_l", "CC_Base_L_Foot"],
	"RightFoot": ["RightFoot", "mixamorig:RightFoot", "foot_r", "CC_Base_R_Foot"],
	"LeftToeTip": ["LeftToeTip", "LeftToe_End", "mixamorig:LeftToe_End", "ball_l", "CC_Base_L_ToeBase"],
	"RightToeTip": ["RightToeTip", "RightToe_End", "mixamorig:RightToe_End", "ball_r", "CC_Base_R_ToeBase"],
	"Head": ["Head", "mixamorig:Head", "head", "CC_Base_Head"], "Hips": ["Hips", "mixamorig:Hips", "pelvis", "CC_Base_Hip"],
	"HeadTip": ["HeadTip", "HeadTop_End", "mixamorig:HeadTop_End"]}
const MAP := {"nose": "Head", "lShoulder": "LeftArm", "rShoulder": "RightArm", "lElbow": "LeftForeArm", "rElbow": "RightForeArm",
	"lWrist": "LeftHand", "rWrist": "RightHand", "lHip": "LeftThigh", "rHip": "RightThigh", "lKnee": "LeftShin", "rKnee": "RightShin",
	"lAnkle": "LeftFoot", "rAnkle": "RightFoot", "lBigToe": "LeftToeTip", "rBigToe": "RightToeTip", 	"hips": "Hips", "headtip": "HeadTip"}
func _init():
	run.call_deferred()

func run():
	var args := OS.get_cmdline_user_args()
	var out_dir: String = args[0]
	for path in args.slice(1):
		var doc := FBXDocument.new(); var st := FBXState.new()
		if doc.append_from_file(path, st) != OK: print("FAIL ", path); continue
		var sc: Node3D = doc.generate_scene(st)
		root.add_child(sc)
		await process_frame
		var sk: Skeleton3D = sc.find_children("*", "Skeleton3D", true, false)[0]
		var ap: AnimationPlayer = sc.find_children("*", "AnimationPlayer", true, false)[0]
		var an: String = ap.get_animation_list()[0]
		var length: float = ap.get_animation(an).length
		ap.play(an)
		var fps := 30.0
		var frames := []
		var n := int(floor(length * fps)) + 1
		for f in n:
			ap.seek(min(f / fps, length), true)
			ap.advance(0)
			sk.force_update_all_bone_transforms()
			var fr := {}
			for k in MAP:
				var bi := -1
				for cand in ALT.get(MAP[k], [MAP[k]]):
					bi = sk.find_bone(cand)
					if bi >= 0: break
				if bi < 0: continue
				var p: Vector3 = (sk.global_transform * sk.get_bone_global_pose(bi)).origin
				fr[k] = [p.x, p.y, p.z]
			frames.append(fr)
		var f2 := FileAccess.open(out_dir + "/" + path.get_file().get_basename() + ".json", FileAccess.WRITE)
		f2.store_string(JSON.stringify({"fps": fps, "length": length, "frames": frames}))
		f2.close()
		print("OK ", path.get_file(), " ", n)
		sc.queue_free()
	quit()

# ProceduralRig3D.gd
# Builds the skinned 18-bone player from rig data (Data/rig_default.json) at runtime, with no
# FBX/OBJ import step. BrowserBoot.gd uses this for every player, and it is also the entry point
# for putting Sprite Forge output on the pitch:
#
#   * rig JSON: drop a file in the same schema at user://rig_override.json (or pass a path)
#     and load_rig_data() uses it instead of the shipped one. The schema is checked first, so a
#     bad file falls back to the default instead of producing a broken mesh.
#   * GLB: Sprite Forge's exporter writes a skinned GLB (model.glb) with baked clips. Its bones are named
#     differently (hips / thigh_L / upperarm_L ...); load_glb() imports it at runtime and report_glb()
#     maps those names onto Arena's and lists any required bone that is missing.
#
# Rig data schema: bones[{n,p,h}] (name, parent index, head position), pos/nrm/uv flat float lists,
# bi/w four bone indices / weights per vertex, mats (material ids), idx {material id -> triangle indices}.
class_name ProceduralRig3D
extends Node3D

const DEFAULT_RIG := "res://Data/rig_default.json"
const OVERRIDE_RIG := "user://rig_override.json"

## Bone names Arena FC's animation code poses by name (BrowserBoot.animate_rig and the C# rig).
const REQUIRED_BONES := ["Hips", "Spine", "Chest", "Head"]

@export var kit_primary: Color = Color("#d7263d")
@export var kit_secondary: Color = Color("#f8fafc")
@export var kit_tertiary: Color = Color("#14213d")
@export var rig_path: String = ""

var rig_data: Dictionary = {}
var skeleton: Skeleton3D
var mesh_instance: MeshInstance3D

func _ready() -> void:
	if get_child_count() == 0:
		build_rig()

## Node-style use: instance the scene node, set the exports, and it builds itself.
func build_rig() -> void:
	for c in get_children():
		c.queue_free()
	rig_data = load_rig_data(rig_path)
	var root := build(rig_data, [kit_primary, kit_secondary, kit_tertiary])
	skeleton = root.get_meta("sk")
	mesh_instance = root.get_meta("mi")
	for c in root.get_children():
		root.remove_child(c)
		add_child(c)
	root.free()

# ---------------------------------------------------------------- data
## Rig data from `path`, else user://rig_override.json, else the shipped default.
static func load_rig_data(path: String = "") -> Dictionary:
	var candidates: Array = []
	if not path.is_empty():
		candidates.append(path)
	candidates.append(OVERRIDE_RIG)
	candidates.append(DEFAULT_RIG)
	for p in candidates:
		if not FileAccess.file_exists(p):
			continue
		var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(p))
		if typeof(parsed) != TYPE_DICTIONARY:
			push_warning("ProceduralRig3D: %s is not a JSON object, skipping" % p)
			continue
		var problem := validate(parsed)
		if problem.is_empty():
			return parsed
		push_warning("ProceduralRig3D: %s rejected: %s" % [p, problem])
	return {}

## "" when the rig data is usable, otherwise the first problem found.
static func validate(d: Dictionary) -> String:
	for k in ["bones", "pos", "nrm", "uv", "bi", "w", "mats", "idx"]:
		if not d.has(k):
			return "missing '%s'" % k
	var bones: Array = d["bones"]
	if bones.is_empty():
		return "no bones"
	var names := {}
	for i in range(bones.size()):
		var b: Variant = bones[i]
		if typeof(b) != TYPE_DICTIONARY or not (b.has("n") and b.has("p") and b.has("h")):
			return "bone %d needs n, p and h" % i
		if int(b["p"]) >= i:
			return "bone %d has parent %d (parents must come first)" % [i, int(b["p"])]
		if (b["h"] as Array).size() != 3:
			return "bone %d head must be [x,y,z]" % i
		names[str(b["n"])] = true
	for r in REQUIRED_BONES:
		if not names.has(r):
			return "missing required bone '%s'" % r
	var verts: int = (d["pos"] as Array).size() / 3
	if verts == 0 or (d["pos"] as Array).size() % 3 != 0:
		return "pos must be a flat list of x,y,z"
	if (d["nrm"] as Array).size() != verts * 3 or (d["uv"] as Array).size() != verts * 2:
		return "nrm/uv length does not match pos"
	if (d["bi"] as Array).size() != verts * 4 or (d["w"] as Array).size() != verts * 4:
		return "bi/w must have 4 entries per vertex"
	for v in d["bi"]:
		if int(v) < 0 or int(v) >= bones.size():
			return "bone index %d out of range" % int(v)
	for m in d["mats"]:
		var tri: Variant = d["idx"][str(int(m))] if typeof(d["idx"]) == TYPE_DICTIONARY else d["idx"][int(m)]
		if (tri as Array).size() % 3 != 0:
			return "material %d index list is not a multiple of 3" % int(m)
		for t in tri:
			if int(t) < 0 or int(t) >= verts:
				return "triangle index %d out of range" % int(t)
	return ""

# ---------------------------------------------------------------- building
static func material_for(idx: int, cols: Array) -> StandardMaterial3D:
	var m := StandardMaterial3D.new()
	match idx:
		0: m.albedo_color = Color("#d69a72")        # skin
		1: m.albedo_color = cols[0]                 # shirt
		2: m.albedo_color = cols[1]                 # shorts
		3: m.albedo_color = cols[2]                 # socks
		4: m.albedo_color = cols[1]
		5: m.albedo_color = Color("#ffd166")
		6: m.albedo_color = Color("#241811")        # hair
		7: m.albedo_color = Color("#2b2d42")
		_: m.albedo_color = Color("#14151a")        # boots
	m.roughness = 0.72
	return m

static func _v3(a: Array) -> Vector3:
	return Vector3(float(a[0]), float(a[1]), float(a[2]))

static func _packed_v3(flat: Array) -> PackedVector3Array:
	var out := PackedVector3Array()
	out.resize(flat.size() / 3)
	for i in range(out.size()):
		out[i] = Vector3(float(flat[i * 3]), float(flat[i * 3 + 1]), float(flat[i * 3 + 2]))
	return out

## Root Node3D > Skeleton3D > MeshInstance3D, with meta sk / mi / cols (what BrowserBoot expects).
static func build(d: Dictionary, cols: Array) -> Node3D:
	var root := Node3D.new()
	var sk := Skeleton3D.new()
	root.add_child(sk)
	var bones: Array = d["bones"]
	for i in range(bones.size()):
		var b: Dictionary = bones[i]
		var idx := sk.add_bone(str(b["n"]))
		var par := int(b["p"])
		if par >= 0:
			sk.set_bone_parent(idx, par)
		var local := _v3(b["h"]) - (_v3(bones[par]["h"]) if par >= 0 else Vector3.ZERO)
		sk.set_bone_rest(idx, Transform3D(Basis.IDENTITY, local))
		sk.set_bone_pose_position(idx, local)      # Godot 4.7: poses are independent of rest
	var skin := Skin.new()
	for i in range(bones.size()):
		skin.add_bind(i, Transform3D(Basis.IDENTITY, _v3(bones[i]["h"])).inverse())

	var uv := PackedVector2Array()
	var uv_flat: Array = d["uv"]
	uv.resize(uv_flat.size() / 2)
	for i in range(uv.size()):
		uv[i] = Vector2(float(uv_flat[i * 2]), float(uv_flat[i * 2 + 1]))
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = _packed_v3(d["pos"])
	arrays[Mesh.ARRAY_NORMAL] = _packed_v3(d["nrm"])
	arrays[Mesh.ARRAY_TEX_UV] = uv
	arrays[Mesh.ARRAY_BONES] = PackedInt32Array(d["bi"])
	arrays[Mesh.ARRAY_WEIGHTS] = PackedFloat32Array(d["w"])
	var am := ArrayMesh.new()
	for mi in d["mats"]:
		var tri: Array = d["idx"][str(int(mi))] if typeof(d["idx"]) == TYPE_DICTIONARY else d["idx"][int(mi)]
		if tri.is_empty():
			continue
		arrays[Mesh.ARRAY_INDEX] = PackedInt32Array(tri)
		am.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
		am.surface_set_material(am.get_surface_count() - 1, material_for(int(mi), cols))
	var mesh_inst := MeshInstance3D.new()
	mesh_inst.mesh = am
	mesh_inst.skin = skin
	sk.add_child(mesh_inst)
	mesh_inst.skeleton = NodePath("..")
	root.set_meta("sk", sk)
	root.set_meta("mi", mesh_inst)
	root.set_meta("cols", cols)
	return root

# ---------------------------------------------------------------- Sprite Forge GLB
## Import a Sprite Forge (or any skinned) GLB at runtime. Returns null and warns on failure.
static func load_glb(path: String) -> Node3D:
	var doc := GLTFDocument.new()
	var state := GLTFState.new()
	var err := doc.append_from_file(path, state)
	if err != OK:
		push_warning("ProceduralRig3D: cannot read GLB %s (error %d)" % [path, err])
		return null
	var scene := doc.generate_scene(state)
	return scene as Node3D

## Sprite Forge's skeleton uses different bone names from Arena's. Both name sets map onto the same
## body, so a Sprite Forge GLB can be matched to Arena bones through this table.
const SPRITE_FORGE_BONES := {
	"hips": "Hips", "spine": "Spine", "chest": "Chest", "neck": "Neck", "head": "Head",
	"upperarm_l": "LUpperArm", "forearm_l": "LForearm", "hand_l": "LHand",
	"upperarm_r": "RUpperArm", "forearm_r": "RForearm", "hand_r": "RHand",
	"thigh_l": "LThigh", "shin_l": "LShin", "foot_l": "LFoot",
	"thigh_r": "RThigh", "shin_r": "RShin", "foot_r": "RFoot",
}

## {arena bone name -> bone name in `sk`}. Exact Arena names win, then the Sprite Forge names above.
static func bone_map(sk: Skeleton3D) -> Dictionary:
	var out := {}
	for i in range(sk.get_bone_count()):
		var n := sk.get_bone_name(i)
		if n in SPRITE_FORGE_BONES.values():
			out[n] = n
	for i in range(sk.get_bone_count()):
		var n := sk.get_bone_name(i)
		var alias: String = SPRITE_FORGE_BONES.get(n.to_lower(), "")
		if not alias.is_empty() and not out.has(alias):
			out[alias] = n
	return out

## How well a loaded GLB matches the bones Arena FC animates.
## {skeletons, bones, map: {arena -> glb}, missing: [required arena bones not found], animations, ok}
static func report_glb(scene: Node) -> Dictionary:
	var sks := scene.find_children("*", "Skeleton3D", true, false)
	var out := {"skeletons": sks.size(), "bones": [], "map": {}, "missing": [], "animations": [], "ok": false}
	if sks.is_empty():
		return out
	var sk: Skeleton3D = sks[0]
	for i in range(sk.get_bone_count()):
		out["bones"].append(sk.get_bone_name(i))
	out["map"] = bone_map(sk)
	for r in REQUIRED_BONES:
		if not out["map"].has(r):
			out["missing"].append(r)
	for ap in scene.find_children("*", "AnimationPlayer", true, false):
		out["animations"].append_array((ap as AnimationPlayer).get_animation_list())
	out["ok"] = out["missing"].is_empty()
	return out

# ---------------------------------------------------------------- misc
static func make_ball(radius: float = 0.11) -> MeshInstance3D:
	var sphere := SphereMesh.new()
	sphere.radius = radius
	sphere.height = radius * 2.0
	var inst := MeshInstance3D.new()
	inst.mesh = sphere
	var mat := StandardMaterial3D.new()
	mat.albedo_color = Color("#ffffff")
	inst.material_override = mat
	return inst

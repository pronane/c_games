# ProceduralRig3D.gd
# Generates a skinned football player rig procedurally in Godot — no FBX/Obj needed.
# Drop this into arena-fc/Scripts/Godot/ and instance ProceduralRig3D in your scene.
# Exports: player mesh with 18-bone skeleton, kit colors, height scale.

class_name ProceduralRig3D
extends Node3D

@export var kit_primary: Color = Color("#d7263d")
@export var kit_secondary: Color = Color("#f8fafc")
@export var height: float = 1.8
@export var build_save_to_tres: bool = false

# 18-bone skeleton definition (matches Arena FC rig_data.json convention)
const BONE_NAMES := [
	"Hips", "Spine", "Chest", "Neck", "Head",
	"LThigh", "LShin", "LFoot",
	"RThigh", "RShin", "RFoot",
	"LUpperArm", "LLowerArm", "LHand",
	"RUpperArm", "RLowerArm", "RHand",
	"Root"
]

var skeleton: Skeleton3D
var mesh_instance: MeshInstance3D
var skin: Skin

func _ready() -> void:
	build_rig()

func build_rig() -> void:
	# Clean previous
	for child in get_children():
		if child is MeshInstance3D or child is Skeleton3D:
			child.queue_free()

	skeleton = Skeleton3D.new()
	add_child(skeleton)

	# Bone rest poses (local positions relative to parent)
	var bone_positions := {
		"Root": Vector3(0, 0, 0),
		"Hips": Vector3(0, 0.9 * height / 1.8, 0),
		"Spine": Vector3(0, 1.25 * height / 1.8, 0),
		"Chest": Vector3(0, 1.55 * height / 1.8, 0),
		"Neck": Vector3(0, 1.75 * height / 1.8, 0),
		"Head": Vector3(0, 1.95 * height / 1.8, 0),
		"LThigh": Vector3(-0.18, 0.9 * height / 1.8, 0),
		"LShin": Vector3(-0.18, 0.45 * height / 1.8, 0),
		"LFoot": Vector3(-0.18, 0.05 * height / 1.8, 0),
		"RThigh": Vector3(0.18, 0.9 * height / 1.8, 0),
		"RShin": Vector3(0.18, 0.45 * height / 1.8, 0),
		"RFoot": Vector3(0.18, 0.05 * height / 1.8, 0),
		"LUpperArm": Vector3(-0.22, 1.5 * height / 1.8, 0),
		"LLowerArm": Vector3(-0.35, 1.25 * height / 1.8, 0),
		"LHand": Vector3(-0.42, 1.05 * height / 1.8, 0),
		"RUpperArm": Vector3(0.22, 1.5 * height / 1.8, 0),
		"RLowerArm": Vector3(0.35, 1.25 * height / 1.8, 0),
		"RHand": Vector3(0.42, 1.05 * height / 1.8, 0),
	}

	var bone_parents := {
		"Root": -1,
		"Hips": "Root",
		"Spine": "Hips",
		"Chest": "Spine",
		"Neck": "Chest",
		"Head": "Neck",
		"LThigh": "Hips",
		"LShin": "LThigh",
		"LFoot": "LShin",
		"RThigh": "Hips",
		"RShin": "RThigh",
		"RFoot": "RShin",
		"LUpperArm": "Chest",
		"LLowerArm": "LUpperArm",
		"LHand": "LLowerArm",
		"RUpperArm": "Chest",
		"RLowerArm": "RUpperArm",
		"RHand": "RLowerArm",
	}

	# Add bones
	for i in range(BONE_NAMES.size()):
		var name := BONE_NAMES[i]
		var idx := skeleton.add_bone(name)
		var parent_name := bone_parents[name]
		var parent_idx := -1
		if parent_name >= 0:
			parent_idx = parent_name
		elif parent_name != "":
			parent_idx := skeleton.find_bone(parent_name)
		if parent_idx >= 0:
			skeleton.set_bone_parent(idx, parent_idx)

		var local_pos := bone_positions[name]
		if parent_idx >= 0:
			var parent_pos := bone_positions[BONE_NAMES[parent_idx]] if parent_name >= 0 else bone_positions[parent_name]
			local_pos = local_pos - parent_pos
		skeleton.set_bone_rest(idx, Transform3D(Basis.IDENTITY, local_pos))

	# Build skinned mesh (capsule-based body segments)
	var surface_tool := SurfaceTool.new()
	surface_tool.begin(Mesh.PRIMITIVE_TRIANGLES)

	var mat_skin := StandardMaterial3D.new()
	mat_skin.albedo_color = kit_secondary
	var mat_kit := StandardMaterial3D.new()
	mat_kit.albedo_color = kit_primary

	func add_segment(bone_a: String, bone_b: String, radius: float, material: Material):
		var pos_a := bone_positions[bone_a]
		var pos_b := bone_positions[bone_b]
		var dir := (pos_b - pos_a).normalized()
		var len := pos_a.distance_to(pos_b)
		if len < 0.01:
			return
		var up := Vector3.UP
		if abs(dir.dot(up)) > 0.9:
			up = Vector3.FORWARD
		var side := dir.cross(up).normalized()
		up = side.cross(dir).normalized()

		var rings := 8
		var ring_step := TAU / rings
		var verts := []
		var normals := []
		var bones_arr := []
		var weights := []
		var uvs := []

		for r in range(rings + 1):
			var angle := r * ring_step
			var circ := Vector3(cos(angle), 0, sin(angle))
			var offset := (side * circ.x + up * circ.y) * radius
			var p1 := pos_a + offset
			var p2 := pos_b + offset
			verts.append(p1)
			verts.append(p2)
			normals.append(circ)
			normals.append(circ)
			var ba := skeleton.find_bone(bone_a)
			var bb := skeleton.find_bone(bone_b)
			bones_arr.append([ba, bb])
			bones_arr.append([ba, bb])
			weights.append([0.5, 0.5])
			weights.append([0.5, 0.5])
			uvs.append([float(r) / rings, 0.0])
			uvs.append([float(r) / rings, 1.0])

		for r in range(rings):
			var i0 := r * 2
			var i1 := i0 + 1
			var i2 := (r + 1) * 2
			var i3 := i2 + 1
			surface_tool.add_normal(normals[i0])
			surface_tool.add_vertex(verts[i0])
			surface_tool.add_bones(bones_arr[i0])
			surface_tool.add_weights(weights[i0])
			surface_tool.add_uv(uvs[i0])
			surface_tool.add_normal(normals[i2])
			surface_tool.add_vertex(verts[i2])
			surface_tool.add_bones(bones_arr[i2])
			surface_tool.add_weights(weights[i2])
			surface_tool.add_uv(uvs[i2])
			surface_tool.add_normal(normals[i3])
			surface_tool.add_vertex(verts[i3])
			surface_tool.add_bones(bones_arr[i3])
			surface_tool.add_weights(weights[i3])
			surface_tool.add_uv(uvs[i3])
			surface_tool.add_normal(normals[i0])
			surface_tool.add_vertex(verts[i0])
			surface_tool.add_bones(bones_arr[i0])
			surface_tool.add_weights(weights[i0])
			surface_tool.add_uv(uvs[i0])
			surface_tool.add_normal(normals[i3])
			surface_tool.add_vertex(verts[i3])
			surface_tool.add_bones(bones_arr[i3])
			surface_tool.add_weights(weights[i3])
			surface_tool.add_uv(uvs[i3])
			surface_tool.add_normal(normals[i1])
			surface_tool.add_vertex(verts[i1])
			surface_tool.add_bones(bones_arr[i1])
			surface_tool.add_weights(weights[i1])
			surface_tool.add_uv(uvs[i1])

	# Torso
	add_segment("Hips", "Chest", 0.22, mat_kit)
	# Neck + Head
	add_segment("Chest", "Head", 0.10, mat_skin)
	# Arms
	add_segment("Chest", "LHand", 0.07, mat_kit)
	add_segment("Chest", "RHand", 0.07, mat_kit)
	# Legs
	add_segment("Hips", "LFoot", 0.12, mat_kit)
	add_segment("Hips", "RFoot", 0.12, mat_kit)

	surface_tool.add_material(mat_kit)
	var array_mesh := surface_tool.commit()
	var mesh_inst := MeshInstance3D.new()
	mesh_inst.mesh = array_mesh
	mesh_inst.skeleton = NodePath("Skeleton3D")
	add_child(mesh_inst)

	# Skin bind poses
	skin = Skin.new()
	for i in range(skeleton.get_bone_count()):
		skin.add_bind(i, skeleton.get_bone_rest(i).inverse())
	mesh_inst.skin = skin

	mesh_instance = mesh_inst

	if build_save_to_tres:
		ResourceSaver.save(array_mesh, "res://Data/procedural_player_mesh.tres")
		print("[ProceduralRig3D] Saved procedural mesh to res://Data/procedural_player_mesh.tres")

# Create a football
func make_ball(radius: float = 0.11) -> MeshInstance3D:
	var sphere := SphereMesh.new()
	sphere.radius = radius
	var inst := MeshInstance3D.new()
	inst.mesh = sphere
	var mat := StandardMaterial3D.new()
	mat.albedo_color = Color("#ffffff")
	inst.material_override = mat
	return inst

# Create pitch markings (lines)
func make_pitch_line(start: Vector3, end: Vector3, width: float = 0.02) -> MeshInstance3D:
	var cyl := CylinderMesh.new()
	cyl.radius = width
	cyl.height = start.distance_to(end)
	var inst := MeshInstance3D.new()
	inst.mesh = cyl
	inst.position = (start + end) / 2
	inst.look_at_from_position(inst.position, end, Vector3.UP)
	var mat := StandardMaterial3D.new()
	mat.albedo_color = Color("#ffffff")
	inst.material_override = mat
	return inst

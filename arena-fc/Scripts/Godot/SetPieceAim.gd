# SetPieceAim.gd
# Tier 3 — Aimed set pieces
# Provides aiming logic for free kicks, penalties, and corner placement.
# Shows a trajectory line + power meter, then fires the ball along the aimed vector.
# Attach to the match/ball node or an autoload "SetPieceAim".

class_name SetPieceAim
extends Node3D

@export var aim_line_length: float = 30.0
@export var max_power: float = 30.0
@export var power_charge_rate: float = 12.0  # power per second
@export var aim_arc_degrees: float = 45.0    # total horizontal aim arc
@export var line_segment_count: int = 20

signal aim_started()
signal aim_updated(angle_deg: float, power: float)
signal aim_cancelled()
signal shot_fired(direction: Vector3, power: float)

var aiming := false
var aim_angle_deg := 0.0   # -aim_arc_degrees/2 .. +aim_arc_degrees/2 relative to goal
var power := 0.0
var aim_start_pos := Vector3.ZERO
var target_node: Node3D = null  # the ball or a placement marker
var line_mesh: ImmediateMesh = null
var power_meter: Control = null

func _ready() -> void:
	if target_node == null:
		# Try to find a ball node named "ball_mesh" or similar
		var ball := get_node_or_null("../ball_mesh")
		if ball:
			target_node = ball

func _input(event: InputEvent) -> void:
	if not aiming:
		return
	if event.is_action_pressed("ui_cancel") or event.is_action_pressed("ui_accept") and not event.is_pressed():
		# Release to shoot on accept-up, or cancel
		if event.is_action_pressed("ui_cancel"):
			cancel_aim()
		elif event.is_action_pressed("ui_accept"):
			fire_shot()
	elif event.is_action_pressed("aim_left"):
		aim_angle_deg = clamp(aim_angle_deg + 2.0, -aim_arc_degrees / 2.0, aim_arc_degrees / 2.0)
		_update_aim()
	elif event.is_action_pressed("aim_right"):
		aim_angle_deg = clamp(aim_angle_deg - 2.0, -aim_arc_degrees / 2.0, aim_arc_degrees / 2.0)
		_update_aim()
	elif event.is_action_pressed("charge_power"):
		# Held to increase power
		pass

func _physics_process(delta: float) -> void:
	if not aiming:
		return
	if Input.is_action_pressed("charge_power"):
		power = clamp(power + power_charge_rate * delta, 0.0, max_power)
		_update_aim()

func start_aim(start_pos: Vector3) -> void:
	aiming = true
	aim_start_pos = start_pos
	aim_angle_deg = 0.0
	power = 0.0
	if target_node:
		target_node.global_position = start_pos
	_create_aim_line()
	aim_started.emit()

func cancel_aim() -> void:
	if not aiming:
		return
	aiming = false
	_destroy_aim_line()
	aim_cancelled.emit()

func fire_shot() -> void:
	if not aiming:
		return
	aiming = false
	var direction := _direction_from_angle(aim_angle_deg)
	_destroy_aim_line()
	shot_fired.emit(direction, power)

func get_aim_data() -> Dictionary:
	return {
		"aiming": aiming,
		"angle_deg": aim_angle_deg,
		"power": power,
		"max_power": max_power,
		"start_pos": aim_start_pos,
	}

# ---------------------------------------------------------------- internal
func _update_aim() -> void:
	if not aiming:
		return
	_destroy_aim_line()
	_create_aim_line()
	aim_updated.emit(aim_angle_deg, power)

func _create_aim_line() -> void:
	if line_mesh:
		line_mesh.queue_free()
	line_mesh = ImmediateMesh.new()
	var line_inst := MeshInstance3D.new()
	line_inst.mesh = line_mesh
	line_inst.name = "AimLine"
	add_child(line_inst)

	var start := aim_start_pos
	var dir := _direction_from_angle(aim_angle_deg)
	var surface := ArrayMesh.new()
	# We'll draw with ImmediateMesh for simplicity
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	var vertices := PackedVector3Array()
	var colors := PackedColorArray()

	# Draw trajectory segments
	var steps := line_segment_count
	var gravity := 9.81
	var vel := dir * power
	var pos := start
	var dt := 0.05
	var y_vel := dir.y * power * 0.5  # slight lift component

	for i in range(steps + 1):
		vertices.append(pos)
		# Color: green at start, red at end
		var t := float(i) / float(steps)
		colors.append(Color.lerp(Color("#00ff00"), Color("#ff0000"), t))
		# Simple physics step
		pos += dir * power * dt
		pos.y += y_vel * dt - 0.5 * gravity * dt * dt
		y_vel -= gravity * dt

	arrays[Mesh.ARRAY_VERTEX] = vertices
	arrays[Mesh.ARRAY_COLOR] = colors
	surface.add_surface_from_arrays(Mesh.PRIMITIVE_LINE_STRIP, arrays)
	line_mesh.add_surface_from_arrays(Mesh.PRIMITIVE_LINE_STRIP, arrays)

func _destroy_aim_line() -> void:
	if line_mesh:
		line_mesh.queue_free()
		line_mesh = null

func _direction_from_angle(angle_deg: float) -> Vector3:
	# angle is relative to facing goal (Z axis). Convert to 2D direction on XZ plane.
	var rad := deg_to_rad(angle_deg)
	var x := sin(rad)
	var z := -cos(rad)  # negative Z is "forward" toward goal
	return Vector3(x, 0.0, z).normalized()

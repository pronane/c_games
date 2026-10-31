# SetPieceAim.gd
# Aimed set pieces: free-kick / penalty / corner aiming with a trajectory preview and a power meter.
#
#   var aim := SetPieceAim.new(); add_child(aim)
#   aim.shot_fired.connect(func(velocity, direction, power): ...)
#   aim.start_aim(spot, Vector3.RIGHT)        # attack_dir = the way the taker is attacking
#
# Controls (polled directly, so no InputMap entries are needed):
#   A / Left , D / Right  turn the aim        hold Space (or call set_charging(true)) to charge
#   release Space         fire                 Escape cancels
# Touch/gamepad front ends can call nudge(), set_charging() and fire_shot() themselves.
#
# The velocity formula is the same one BrowserBoot.shoot() uses, so what the preview shows is
# what a normal shot would do at that power.
class_name SetPieceAim
extends Node3D

signal aim_started()
signal aim_updated(angle_deg: float, power: float)
signal aim_cancelled()
signal shot_fired(velocity: Vector3, direction: Vector3, power: float)

@export var aim_arc_degrees: float = 60.0          # total sweep, centred on attack_dir
@export var turn_speed_deg: float = 40.0           # degrees per second while a key is held
@export var charge_seconds: float = 0.9            # empty to full
@export var min_speed: float = 18.0
@export var max_speed: float = 29.0
@export var min_lift: float = 2.2
@export var max_lift: float = 6.0
@export var gravity: float = 9.81
@export var ball_radius: float = 0.11
@export var preview_steps: int = 40

var aiming := false
var aim_angle_deg := 0.0            # 0 = straight at the goal; + turns anticlockwise seen from above
var power := 0.0                    # 0..1
var charging := false
var aim_start_pos := Vector3.ZERO
var attack_dir := Vector3.RIGHT

var _mesh := ImmediateMesh.new()
var _line: MeshInstance3D
var _min_power := 0.25

func _ready() -> void:
	_line = MeshInstance3D.new()
	_line.name = "AimLine"
	_line.mesh = _mesh
	var mat := StandardMaterial3D.new()
	mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	mat.vertex_color_use_as_albedo = true
	mat.no_depth_test = true
	_line.material_override = mat
	_line.visible = false
	add_child(_line)

# ---------------------------------------------------------------- API
func start_aim(start_pos: Vector3, p_attack_dir: Vector3 = Vector3.RIGHT) -> void:
	aiming = true
	aim_start_pos = start_pos
	attack_dir = Vector3(p_attack_dir.x, 0.0, p_attack_dir.z).normalized()
	if attack_dir.length_squared() < 0.5:
		attack_dir = Vector3.RIGHT
	aim_angle_deg = 0.0
	power = 0.0
	charging = false
	_line.visible = true
	_redraw()
	aim_started.emit()

func cancel_aim() -> void:
	if not aiming:
		return
	_end()
	aim_cancelled.emit()

func nudge(delta_deg: float) -> void:
	if not aiming:
		return
	var half := aim_arc_degrees / 2.0
	aim_angle_deg = clampf(aim_angle_deg + delta_deg, -half, half)
	_redraw()
	aim_updated.emit(aim_angle_deg, power)

## Alias of set_external_hold(): true starts charging, false fires.
func set_charging(on: bool) -> void:
	set_external_hold(on)

func fire_shot() -> void:
	if not aiming:
		return
	var p := maxf(_min_power, power)
	var dir := direction_for(aim_angle_deg)
	var vel := shot_velocity(dir, p)
	_end()
	shot_fired.emit(vel, dir, p)

func get_aim_data() -> Dictionary:
	return {"aiming": aiming, "angle_deg": aim_angle_deg, "power": power, "start_pos": aim_start_pos}

## Unit direction on the pitch for an aim angle.
func direction_for(angle_deg: float) -> Vector3:
	return attack_dir.rotated(Vector3.UP, deg_to_rad(angle_deg)).normalized()

## Initial ball velocity. Same shape as BrowserBoot.shoot(): dir * lerp(18, 29, p) + up * lerp(2.2, 6, p).
func shot_velocity(dir: Vector3, p: float) -> Vector3:
	return dir * lerpf(min_speed, max_speed, p) + Vector3(0.0, lerpf(min_lift, max_lift, p), 0.0)

# ---------------------------------------------------------------- input
func _physics_process(delta: float) -> void:
	if not aiming:
		return
	var turn := 0.0
	if Input.is_key_pressed(KEY_A) or Input.is_key_pressed(KEY_LEFT):
		turn += 1.0
	if Input.is_key_pressed(KEY_D) or Input.is_key_pressed(KEY_RIGHT):
		turn -= 1.0
	if turn != 0.0:
		nudge(turn * turn_speed_deg * delta)
	var space := Input.is_key_pressed(KEY_SPACE)
	if space:
		charging = true
	if charging:
		power = minf(1.0, power + delta / charge_seconds)
		_redraw()
		aim_updated.emit(aim_angle_deg, power)
		if not space and not _external_hold:
			fire_shot()
	if Input.is_key_pressed(KEY_ESCAPE):
		cancel_aim()

var _external_hold := false
## For touch buttons: hold true while the button is down, false on release (that fires).
func set_external_hold(on: bool) -> void:
	if on:
		_external_hold = true
		charging = aiming
	elif _external_hold:
		_external_hold = false
		if aiming:
			fire_shot()

# ---------------------------------------------------------------- drawing
func _end() -> void:
	aiming = false
	charging = false
	_external_hold = false
	_mesh.clear_surfaces()
	if _line != null:
		_line.visible = false

func trajectory(dir: Vector3, p: float) -> PackedVector3Array:
	var pts := PackedVector3Array()
	var pos := aim_start_pos
	pos.y = maxf(pos.y, ball_radius)
	var vel := shot_velocity(dir, maxf(p, _min_power))
	var dt := 1.0 / 30.0
	for i in range(preview_steps):
		pts.append(pos)
		vel.y -= gravity * dt
		pos += vel * dt
		if pos.y <= ball_radius:       # first bounce ends the preview
			pos.y = ball_radius
			pts.append(pos)
			break
	return pts

func _redraw() -> void:
	_mesh.clear_surfaces()
	var pts := trajectory(direction_for(aim_angle_deg), power)
	if pts.size() < 2:
		return
	_mesh.surface_begin(Mesh.PRIMITIVE_LINE_STRIP)
	var c0 := Color(0.2, 1.0, 0.2)
	var c1 := Color(1.0, 0.2, 0.2)
	for i in range(pts.size()):
		_mesh.surface_set_color(c0.lerp(c1, float(i) / float(pts.size() - 1)))
		_mesh.surface_add_vertex(pts[i])
	_mesh.surface_end()

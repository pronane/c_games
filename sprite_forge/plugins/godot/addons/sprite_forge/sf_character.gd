@tool
class_name SpriteForgeCharacter
extends AnimatedSprite2D
## Sprite Forge character: plays the moves and keeps two Area2D children ("Hurtbox", "Hitbox") in step with
## framedata.json (hurt boxes every frame, hit boxes only on active frames). Origin = the feet.
## Signals: hit_active(move, frame, rect) when an active frame starts.  flip_h mirrors the boxes too.

signal hit_active(move: String, frame: int, rect: Rect2)

@export_file("*.json") var framedata_path: String = "":
	set(v):
		framedata_path = v
		_fd = {}
@export var cell_size: Vector2 = Vector2(256, 256)
@export var pivot_px: Vector2 = Vector2(128, 240)
@export var show_boxes: bool = false:
	set(v):
		show_boxes = v
		queue_redraw()
@export_flags_2d_physics var hurt_layer: int = 1
@export_flags_2d_physics var hit_mask: int = 1

var _fd: Dictionary = {}
var hurtbox: Area2D
var hitbox: Area2D

func _ready() -> void:
	hurtbox = _area("Hurtbox", hurt_layer, 0)
	hitbox = _area("Hitbox", 0, hit_mask)
	frame_changed.connect(_update_boxes)
	animation_changed.connect(_update_boxes)
	_update_boxes()

func _area(n: String, layer: int, mask: int) -> Area2D:
	var a := get_node_or_null(n) as Area2D
	if a == null:
		a = Area2D.new()
		a.name = n
		a.collision_layer = layer
		a.collision_mask = mask
		add_child(a)
	return a

func framedata() -> Dictionary:
	if _fd.is_empty() and framedata_path != "":
		var f := FileAccess.open(framedata_path, FileAccess.READ)
		if f:
			_fd = JSON.parse_string(f.get_as_text())
	return _fd

func move_data(move: String = "") -> Dictionary:
	var fd := framedata()
	if fd.is_empty():
		return {}
	return fd.get("moves", {}).get(move if move != "" else String(animation), {})

func boxes(kind: String, move: String = "", f: int = -1) -> Array[Rect2]:
	## kind = "hurt" | "hit"; rects in this node's local space (origin = feet), mirrored when flip_h
	var out: Array[Rect2] = []
	var md := move_data(move)
	if md.is_empty():
		return out
	var i := frame if f < 0 else f
	var frs: Array = md.get("frames", [])
	if i >= frs.size():
		return out
	for b in frs[i].get(kind, []):
		var bx: Array = b["box"]
		var r := Rect2(bx[0] - pivot_px.x, bx[1] - pivot_px.y, bx[2], bx[3])
		if flip_h:
			r.position.x = -r.position.x - r.size.x
		out.append(r)
	return out

func _update_boxes() -> void:
	if hurtbox == null:
		return
	for a in [hurtbox, hitbox]:
		for c in a.get_children():
			c.free()
	for r in boxes("hurt"):
		hurtbox.add_child(_shape(r))
	var hits := boxes("hit")
	for r in hits:
		hitbox.add_child(_shape(r))
	if hits.size() > 0:
		hit_active.emit(String(animation), frame, hits[0])
	queue_redraw()

func _shape(r: Rect2) -> CollisionShape2D:
	var cs := CollisionShape2D.new()
	var rs := RectangleShape2D.new()
	rs.size = r.size
	cs.shape = rs
	cs.position = r.get_center()
	return cs

func _draw() -> void:
	if not show_boxes:
		return
	for r in boxes("hurt"):
		draw_rect(r, Color(0.2, 0.6, 1.0, 0.8), false, 2.0)
	for r in boxes("hit"):
		draw_rect(r, Color(1.0, 0.2, 0.2, 0.9), false, 2.0)

extends Node2D
## Godot 4 loader for Sprite Forge game_character.json (v11.5).
##
## Drop this script on a Node2D. Set `character_dir` to the build folder
## (the one that contains game_character.json and strips/). Call `play("idle")`.
## Feet sit on this node's origin. The game draws props (ball, gun, kart); the
## manifest only says which frame to use.
##
## Hitboxes are an estimate from the sprite silhouette. Events use -1 for "none".
## A custom event key in the JSON is left on the Dictionary; this script reads the
## known ones (hit_start, hit_end, ball_contact, throw_release, shoot, reload, footsteps).

@export var character_dir: String = ""
@export var scale_to: float = 128.0

var data: Dictionary = {}
var anims: Dictionary = {}
var order: PackedStringArray = []
var current: String = ""
var time: float = 0.0
var frame_i: int = 0
var done: bool = false
var sprite: Sprite2D

func _ready() -> void:
	sprite = Sprite2D.new()
	sprite.centered = false
	add_child(sprite)
	if character_dir != "":
		load_dir(character_dir)

func load_dir(path: String) -> bool:
	character_dir = path
	var file := path.path_join("game_character.json")
	if not FileAccess.file_exists(file):
		push_error("game_character.json not found in " + path)
		return false
	var parsed = JSON.parse_string(FileAccess.get_file_as_string(file))
	if typeof(parsed) != TYPE_DICTIONARY:
		push_error("game_character.json is not an object")
		return false
	data = parsed
	anims.clear()
	order = PackedStringArray()
	for a in data.get("animations", []):
		var tex := _load_strip(path.path_join(str(a.get("strip", ""))))
		if tex == null:
			push_warning("no strip for " + str(a.get("name", "?")))
			continue
		anims[str(a["name"])] = {"def": a, "tex": tex}
		order.append(str(a["name"]))
	if order.size() > 0:
		play("idle" if anims.has("idle") else order[0])
	return anims.size() > 0

func _load_strip(p: String) -> Texture2D:
	if not FileAccess.file_exists(p):
		return null
	var img := Image.new()
	if img.load(p) != OK:
		return null
	return ImageTexture.create_from_image(img)

func play(move: String) -> void:
	if not anims.has(move):
		return
	current = move
	time = 0.0
	frame_i = 0
	done = false
	_show()

func _process(delta: float) -> void:
	if current == "" or not anims.has(current):
		return
	var a: Dictionary = anims[current]["def"]
	var n := int(a.get("frames", 1))
	var fps := float(a.get("fps", 12))
	if fps <= 0.0:
		fps = 12.0
	time += delta
	var f := int(time * fps)
	var loop := bool(a.get("loop", false))
	if loop:
		f = posmod(f, n)
	elif f >= n:
		f = n - 1
		done = true
	if f != frame_i:
		frame_i = f
		_show()
		_emit_events(a)

func _show() -> void:
	var a: Dictionary = anims[current]["def"]
	var tex: Texture2D = anims[current]["tex"]
	var w := int(a.get("w", 1))
	var h := int(a.get("h", 1))
	sprite.texture = tex
	sprite.region_enabled = true
	sprite.region_rect = Rect2(frame_i * w, 0, w, h)
	var pivot: Dictionary = a.get("pivot", {})
	var px := float(pivot.get("x", w / 2))
	var py := float(pivot.get("y", a.get("ground_y", h)))
	var sc := scale_to / float(h) if h > 0 else 1.0
	sprite.scale = Vector2(sc, sc)
	sprite.position = Vector2(-px * sc, -py * sc)

func _emit_events(a: Dictionary) -> void:
	var ev: Dictionary = a.get("events", {})
	if int(ev.get("hit_start", -1)) >= 0:
		var end := int(ev.get("hit_end", ev.get("hit_start", -1)))
		if frame_i >= int(ev["hit_start"]) and frame_i <= end:
			# the game decides damage; this only says the frame is live
			pass
	for key in ["ball_contact", "throw_release", "shoot", "reload"]:
		if int(ev.get(key, -1)) == frame_i:
			pass

func event_now(key: String) -> bool:
	## True when the playing frame is the event (or inside hit_start..hit_end for "hit").
	if current == "" or not anims.has(current):
		return false
	var ev: Dictionary = anims[current]["def"].get("events", {})
	if key == "hit":
		var a := int(ev.get("hit_start", -1))
		var b := int(ev.get("hit_end", a))
		return a >= 0 and frame_i >= a and frame_i <= b
	if key == "footstep":
		return frame_i in ev.get("footsteps", [])
	return int(ev.get(key, -1)) == frame_i

func moves() -> PackedStringArray:
	return order

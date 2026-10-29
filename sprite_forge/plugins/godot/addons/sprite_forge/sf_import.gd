@tool
class_name SpriteForgeImport
extends RefCounted
## Sprite Forge Studio v9 importer (works in the editor AND at runtime / headless:
##   godot --headless --script res://addons/sprite_forge/sf_cli.gd -- res://chars/hero)
## atlas.json (one character, any number of pages)  -> <name>_frames.tres + <name>.tscn
## pack.json  (several characters, trimmed frames)  -> one _frames.tres + .tscn per character
## framedata.json -> the scene's SpriteForgeCharacter shows hit / hurt boxes per frame
## maps/atlas_normal.png -> CanvasTexture (normal-mapped 2D lighting with Light2D)

static func _read_json(path: String) -> Variant:
	var f := FileAccess.open(path, FileAccess.READ)
	if f == null:
		return null
	return JSON.parse_string(f.get_as_text())

static func _texture(path: String) -> Texture2D:
	# imported resource in the editor; plain PNG load otherwise (headless / runtime folders)
	if ResourceLoader.exists(path):
		var t = load(path)
		if t is Texture2D:
			return t
	var img := Image.load_from_file(ProjectSettings.globalize_path(path))
	if img == null:
		return null
	return ImageTexture.create_from_image(img)

static func _frame_texture(page: Texture2D, normal: Texture2D, region: Rect2, margin: Rect2) -> Texture2D:
	# AtlasTexture regions are ignored when the atlas is a CanvasTexture (Godot 4.3), so a normal-mapped frame is
	# a CanvasTexture made of two AtlasTextures (colour + normal) cut from the same rectangle.
	var at := AtlasTexture.new()
	at.atlas = page
	at.region = region
	at.margin = margin
	if normal == null:
		return at
	var an := AtlasTexture.new()
	an.atlas = normal
	an.region = region
	an.margin = margin
	var ct := CanvasTexture.new()
	ct.diffuse_texture = at
	ct.normal_texture = an
	return ct

static func import_folder(dir: String, write_scene: bool = true) -> Array:
	var made: Array = []
	if FileAccess.file_exists(dir.path_join("atlas.json")):
		made.append_array(_import_atlas(dir, write_scene))
	elif FileAccess.file_exists(dir.path_join("pack.json")):
		made.append_array(_import_pack(dir, write_scene))
	else:
		push_error("Sprite Forge: no atlas.json or pack.json in " + dir)
	return made

static func _import_atlas(dir: String, write_scene: bool) -> Array:
	var js: Dictionary = _read_json(dir.path_join("atlas.json"))
	var meta: Dictionary = js["meta"]
	var name: String = meta.get("name", dir.get_file())
	var images: Array = meta.get("images", [meta.get("image", "atlas.png")])
	var normals: Array = []
	var mj = _read_json(dir.path_join("maps/maps.json"))
	if mj != null and mj.get("files", {}).has("normal"):
		for n in mj["files"]["normal"]:
			normals.append("maps/" + str(n))
	var pages: Array = []
	var npages: Array = []
	for i in images.size():
		pages.append(_texture(dir.path_join(images[i])))
		var np := dir.path_join(normals[i]) if i < normals.size() else ""
		npages.append(_texture(np) if np != "" and FileAccess.file_exists(np) else null)
	var sf := SpriteFrames.new()
	if sf.has_animation("default"):
		sf.remove_animation("default")
	var frames: Dictionary = js["frames"]
	for mv in js["animations"]:
		var a: Dictionary = js["animations"][mv]
		sf.add_animation(mv)
		sf.set_animation_speed(mv, float(a.get("fps", 12)))
		sf.set_animation_loop(mv, bool(a.get("loop", false)))
		for fname in a["frames"]:
			var fr: Dictionary = frames[fname]
			var r: Dictionary = fr["frame"]
			var ss: Dictionary = fr.get("spriteSourceSize", {"x": 0, "y": 0})
			var src: Dictionary = fr.get("sourceSize", {"w": r["w"], "h": r["h"]})
			var margin := Rect2()
			if fr.get("trimmed", false):
				margin = Rect2(ss["x"], ss["y"], src["w"] - r["w"], src["h"] - r["h"])
			var pg := int(fr.get("page", 0))
			sf.add_frame(mv, _frame_texture(pages[pg], npages[pg], Rect2(r["x"], r["y"], r["w"], r["h"]), margin))
	var piv: Dictionary = meta.get("pivot", {"x": meta["frame_w"] / 2, "y": meta["ground_y"]})
	return _save(dir, name, sf, Vector2(meta["frame_w"], meta["frame_h"]), Vector2(piv["x"], piv["y"]),
		dir.path_join("framedata.json"), write_scene)

static func _import_pack(dir: String, write_scene: bool) -> Array:
	var js: Dictionary = _read_json(dir.path_join("pack.json"))
	var meta: Dictionary = js["meta"]
	var pages: Array = []
	for img in meta["images"]:
		pages.append(_texture(dir.path_join(img)))
	var per: Dictionary = {}
	for key in js["animations"]:
		var a: Dictionary = js["animations"][key]
		var ch: String = a["character"]
		if not per.has(ch):
			var s := SpriteFrames.new()
			if s.has_animation("default"):
				s.remove_animation("default")
			per[ch] = s
		var sf: SpriteFrames = per[ch]
		var mv: String = a["move"]
		sf.add_animation(mv)
		sf.set_animation_speed(mv, float(a["fps"]))
		sf.set_animation_loop(mv, bool(a["loop"]))
		for fk in a["frames"]:
			var fr: Dictionary = js["frames"][fk]
			var r: Dictionary = fr["frame"]
			var ss: Dictionary = fr["spriteSourceSize"]
			var src: Dictionary = fr["sourceSize"]
			sf.add_frame(mv, _frame_texture(pages[int(fr["page"])], null, Rect2(r["x"], r["y"], r["w"], r["h"]),
				Rect2(ss["x"], ss["y"], src["w"] - r["w"], src["h"] - r["h"])))
	var made: Array = []
	for ch in per:
		var cm: Dictionary = meta["characters"][ch]
		made.append_array(_save(dir, ch, per[ch], Vector2(cm["frame_w"], cm["frame_h"]),
			Vector2(cm["pivot"]["x"], cm["pivot"]["y"]), "", write_scene))
	return made

static func _save(dir: String, name: String, sf: SpriteFrames, cell: Vector2, pivot: Vector2, fd_path: String, write_scene: bool) -> Array:
	var made: Array = []
	var tres := dir.path_join(name + "_frames.tres")
	if ResourceSaver.save(sf, tres) == OK:
		made.append(tres)
	if not write_scene:
		return made
	var node := SpriteForgeCharacter.new()
	node.name = name.to_pascal_case()
	node.sprite_frames = sf
	node.centered = false
	node.offset = -pivot                 # node origin = the character's feet (ground pivot)
	node.cell_size = cell
	node.pivot_px = pivot
	if fd_path != "" and FileAccess.file_exists(fd_path):
		node.framedata_path = fd_path
	if sf.has_animation("idle"):
		node.animation = "idle"
		node.autoplay = "idle"
	var ps := PackedScene.new()
	if ps.pack(node) == OK:
		var scn := dir.path_join(name + ".tscn")
		if ResourceSaver.save(ps, scn) == OK:
			made.append(scn)
	node.free()
	return made

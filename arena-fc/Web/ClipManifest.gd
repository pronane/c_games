# Shared Arena Motion Engine metadata reader for the browser/GDScript build.
# Pose frames remain in soccer_rig.json; this manifest supplies category,
# timing and phase metadata consumed by C# and GDScript presentation code.
extends RefCounted

const DEFAULT_PATH := "res://Data/clips/clip_manifest.json"
const SUPPORTED_VERSIONS := [1, 2]

static func load_manifest(path: String = DEFAULT_PATH) -> Dictionary:
	if not FileAccess.file_exists(path):
		push_warning("AME clip manifest not found: %s" % path)
		return {}
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	if typeof(parsed) != TYPE_DICTIONARY:
		push_error("Unsupported or malformed AME clip manifest: %s" % path)
		return {}
	var version := int(parsed.get("version", -1))
	if not version in SUPPORTED_VERSIONS:
		push_error("Unsupported or malformed AME clip manifest: %s" % path)
		return {}
	var source: Variant = parsed.get("clips", null)
	if typeof(source) != TYPE_ARRAY:
		push_error("AME clip manifest has no clips array")
		return {}
	var by_id := {}
	for raw in source:
		if typeof(raw) != TYPE_DICTIONARY:
			push_error("AME clip entry is not an object")
			return {}
		var id := str(raw.get("id", ""))
		if id.is_empty() or by_id.has(id):
			push_error("AME clip id is empty or duplicated: %s" % id)
			return {}
		if float(raw.get("duration", 0.0)) <= 0.0 or int(raw.get("boneCount", 0)) != 18:
			push_error("AME clip has invalid duration or skeleton size: %s" % id)
			return {}
		var plants: Variant = raw.get("footPlantFrames", [])
		var sides: Variant = raw.get("footPlantSides", [])
		if typeof(plants) != TYPE_ARRAY or typeof(sides) != TYPE_ARRAY:
			push_error("AME clip foot plants/sides must be arrays: %s" % id)
			return {}
		if raw.has("footPlantSides") and sides.size() != plants.size():
			push_error("AME clip footPlantSides count differs from footPlantFrames: %s" % id)
			return {}
		for side in sides:
			if str(side) not in ["Left", "Right"]:
				push_error("AME clip has invalid foot plant side: %s" % id)
				return {}
		by_id[id] = raw
	return {"version": version, "skeleton": str(parsed.get("skeleton", "")), "by_id": by_id}

static func phase_from_seconds(clip_id: String, seconds: float, manifest: Dictionary) -> float:
	var meta: Dictionary = manifest.get("by_id", {}).get(clip_id, {})
	var duration := maxf(float(meta.get("duration", 0.0)), 0.000001)
	return wrapf(seconds / duration, 0.0, 1.0) if bool(meta.get("loop", false)) else clampf(seconds / duration, 0.0, 1.0)

static func align_phase(old_id: String, new_id: String, phase: float, manifest: Dictionary) -> float:
	var by_id: Dictionary = manifest.get("by_id", {})
	var from: Dictionary = by_id.get(old_id, {})
	var to: Dictionary = by_id.get(new_id, {})
	var a: Array = from.get("footPlantFrames", [])
	var b: Array = to.get("footPlantFrames", [])
	if a.is_empty() or b.is_empty():
		return wrapf(phase, 0.0, 1.0)
	var source_index := 0
	var best := INF
	for i in range(a.size()):
		var d := absf(wrapf(phase - float(a[i]) + 0.5, 0.0, 1.0) - 0.5)
		if d < best:
			best = d
			source_index = i
	var source_plant := float(a[source_index])
	var source_side := _plant_side(from, source_index)
	var target_index := -1
	best = INF
	for i in range(b.size()):
		if _plant_side(to, i) != source_side:
			continue
		var d := absf(wrapf(source_plant - float(b[i]) + 0.5, 0.0, 1.0) - 0.5)
		if d < best:
			best = d
			target_index = i
	if target_index < 0:
		return wrapf(phase, 0.0, 1.0)
	var target_plant := float(b[target_index])
	var offset := _circular_diff(phase, source_plant)
	return wrapf(target_plant + offset, 0.0, 1.0)

static func _circular_diff(a: float, b: float) -> float:
	var d := fmod(a - b, 1.0)
	if d > 0.5:
		d -= 1.0
	if d < -0.5:
		d += 1.0
	return d

static func _plant_side(meta: Dictionary, index: int) -> String:
	var sides: Array = meta.get("footPlantSides", [])
	if index < sides.size():
		return str(sides[index])
	return "Left" if index % 2 == 0 else "Right"

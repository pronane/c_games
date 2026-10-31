# ReplayPlayer.gd
# Plays back frames made by ReplayRecorder: either a rolling highlight (load_frames) or a
# saved match (load_replay). It interpolates between the recorded snapshots and emits
# `frame_ready` with decoded values; the game applies them to its rigs and ball exactly
# as it would apply a live network snapshot.
#
#   frame_ready(frame): {players: [{x, z, fx, fz, a}], ball: {x, y, z, owner}, score: [h, a], clock: float}
class_name ReplayPlayer
extends Node

signal replay_loaded(path: String, match_id: String)
signal frame_ready(frame: Dictionary)
signal replay_finished()
signal replay_error(msg: String)

var playing := false
var speed := 1.0                      # 0.25 slow-mo ... 4.0 fast
var time := 0.0                       # seconds into the replay
var hz := 15.0
var match_id := ""
var actions: Array = ["idle"]

var _frames: Array = []               # raw frames (see ReplayRecorder)

func duration() -> float:
	return maxf(0.0, float(_frames.size() - 1) / hz)

func frame_count() -> int:
	return _frames.size()

## Use frames straight from ReplayRecorder.get_highlight().
func load_frames(frames: Array, p_hz: float = 15.0, p_actions: Array = []) -> void:
	_frames = frames.duplicate(true)
	hz = p_hz
	actions = p_actions if not p_actions.is_empty() else ["idle"]
	time = 0.0
	playing = false

func load_replay(path: String) -> bool:
	var f := FileAccess.open(path, FileAccess.READ)
	if f == null:
		replay_error.emit("Cannot open: " + path)
		return false
	var frames: Array = []
	var acts: Array = ["idle"]
	var rate := 15.0
	var mid := path.get_file().get_basename()
	while not f.eof_reached():
		var line := f.get_line().strip_edges()
		if line.is_empty():
			continue
		var parser := JSON.new()
		if parser.parse(line) != OK or typeof(parser.data) != TYPE_DICTIONARY:
			continue                  # a half-written last line after a crash is skipped, not fatal
		var obj: Dictionary = parser.data
		if obj.has("hdr"):
			rate = float(obj["hdr"].get("hz", 15.0))
			mid = str(obj["hdr"].get("match_id", mid))
		elif obj.has("end"):
			acts = obj["end"].get("actions", acts)
		elif obj.has("k") and obj.has("p"):
			frames.append(obj)
	f.close()
	if frames.is_empty():
		replay_error.emit("Replay has no frames: " + path)
		return false
	load_frames(frames, rate, acts)
	match_id = mid
	replay_loaded.emit(path, match_id)
	return true

func play() -> void:
	if _frames.is_empty():
		return
	if time >= duration():
		time = 0.0
	playing = true

func pause() -> void:
	playing = false

func stop() -> void:
	playing = false
	time = 0.0

func seek(seconds: float) -> void:
	time = clampf(seconds, 0.0, duration())
	_emit_current()

func current_frame() -> Dictionary:
	return sample(time)

## Decoded, interpolated frame at `seconds`.
func sample(seconds: float) -> Dictionary:
	if _frames.is_empty():
		return {}
	var f := clampf(seconds * hz, 0.0, float(_frames.size() - 1))
	var i := int(floor(f))
	var j := mini(i + 1, _frames.size() - 1)
	return _blend(_frames[i], _frames[j], f - float(i))

func _blend(a: Dictionary, b: Dictionary, t: float) -> Dictionary:
	var pa: Array = a["p"]
	var pb: Array = b["p"]
	var players: Array = []
	for n in range(pa.size()):
		var qa: Array = pa[n]
		var qb: Array = pb[n] if n < pb.size() else qa
		var fx := lerpf(float(qa[2]), float(qb[2]), t) / 100.0
		var fz := lerpf(float(qa[3]), float(qb[3]), t) / 100.0
		var act_id := int(qa[4]) if t < 0.5 else int(qb[4])
		players.append({"x": lerpf(float(qa[0]), float(qb[0]), t) / 100.0, "z": lerpf(float(qa[1]), float(qb[1]), t) / 100.0,
			"fx": fx, "fz": fz, "a": str(actions[act_id]) if act_id < actions.size() else "idle"})
	var ba: Array = a["b"]
	var bb: Array = b["b"]
	return {"players": players,
		"ball": {"x": lerpf(float(ba[0]), float(bb[0]), t) / 100.0, "y": lerpf(float(ba[1]), float(bb[1]), t) / 100.0,
			"z": lerpf(float(ba[2]), float(bb[2]), t) / 100.0, "owner": int(ba[3]) if t < 0.5 else int(bb[3])},
		"score": (a["s"] as Array).duplicate(), "clock": float(a["c"])}

func _emit_current() -> void:
	var fr := sample(time)
	if not fr.is_empty():
		frame_ready.emit(fr)

func _physics_process(delta: float) -> void:
	if not playing or _frames.is_empty():
		return
	time += delta * speed
	if time >= duration():
		time = duration()
		_emit_current()
		playing = false
		replay_finished.emit()
		return
	_emit_current()

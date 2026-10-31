# ReplayRecorder.gd
# Match recording + instant-replay buffer.
#
# The simulation lives in the C# server (or, offline, in BrowserBoot.gd), so the browser
# edition cannot re-simulate a match from inputs. Instead this records what the screen
# shows: compact position snapshots (default 15 per second). ReplayPlayer feeds them back
# through the same rendering path the live game uses.
#
# Two things happen at once:
#   1. a rolling buffer of the last `highlight_seconds` is always kept in memory, so a goal
#      can be shown again instantly (get_highlight());
#   2. when recording is on, every frame is appended to user://replays/<match_id>.jsonl
#      (one JSON object per line: header, frames, events). Appending keeps the cost of a
#      flush constant instead of rewriting a growing file.
#
# Frame (in memory and on disk):
#   {"k": tick, "p": [[x_cm, z_cm, fx_100, fz_100, action_id], ...], "b": [x_cm, y_cm, z_cm, owner],
#    "s": [home, away], "c": clock_seconds}
class_name ReplayRecorder
extends Node

signal replay_saved(path: String, match_id: String)
signal replay_error(msg: String)

const REPLAY_DIR := "user://replays/"
const FORMAT_VERSION := 2
const FLUSH_EVERY_FRAMES := 45        # ~3 s at 15 Hz

@export var record_hz: float = 15.0
@export var highlight_seconds: float = 10.0

var recording := false
var match_id := ""
var room_code := ""
var seed_value := 0
var team_size := 5
var actions: Array = ["idle"]          # action name -> id (index); grows as new names appear
var frames_written := 0

var _acc := 0.0
var _tick := 0
var _pending: Array = []               # lines waiting to be appended
var _path := ""
var _highlight: Array = []             # rolling in-memory frames
var _last_score: Array = [0, 0]

func _ready() -> void:
	DirAccess.make_dir_recursive_absolute(REPLAY_DIR)

# ---------------------------------------------------------------- recording
func start_recording(p_room_code: String, p_seed: int, p_team_size: int, p_match_id: String = "") -> void:
	if recording:
		return
	recording = true
	room_code = p_room_code
	seed_value = p_seed
	team_size = p_team_size
	match_id = p_match_id if not p_match_id.is_empty() else str(Time.get_unix_time_from_system()).replace(".", "_")
	actions = ["idle"]
	frames_written = 0
	_pending.clear()
	_path = REPLAY_DIR + match_id + ".jsonl"
	var f := FileAccess.open(_path, FileAccess.WRITE)
	if f == null:
		recording = false
		replay_error.emit("Cannot write replay to " + _path)
		return
	f.store_line(JSON.stringify({"hdr": {"v": FORMAT_VERSION, "match_id": match_id, "room": room_code,
		"seed": seed_value, "team_size": team_size, "hz": record_hz,
		"started_at": Time.get_unix_time_from_system()}}))
	f.close()

func stop_recording() -> String:
	if not recording:
		return ""
	_flush(true)
	recording = false
	replay_saved.emit(_path, match_id)
	return _path

## Call every physics frame with the game's current state. It samples at `record_hz`.
## players: Array of Dictionary {pos: Vector3, facing: Vector3, action: String}
## ball: Dictionary {pos: Vector3, owner: int}
func capture(delta: float, players: Array, ball: Dictionary, score: Array, clock: float) -> void:
	_acc += delta
	var step := 1.0 / record_hz
	if _acc < step:
		return
	_acc = fmod(_acc, step)
	_tick += 1
	var frame := encode_frame(_tick, players, ball, score, clock)
	_last_score = score.duplicate()
	_highlight.append(frame)
	var max_frames := int(highlight_seconds * record_hz)
	while _highlight.size() > max_frames:
		_highlight.pop_front()
	if recording:
		_pending.append(JSON.stringify(frame))
		if _pending.size() >= FLUSH_EVERY_FRAMES:
			_flush(false)

func record_event(event_type: String, data: Dictionary = {}) -> void:
	if not recording:
		return
	_pending.append(JSON.stringify({"ev": {"k": _tick, "type": event_type, "data": data}}))

## The last `seconds` of play as frames (for an instant replay). Copies, so callers can keep them.
func get_highlight(seconds: float = 8.0) -> Array:
	var n := mini(_highlight.size(), int(seconds * record_hz))
	return _highlight.slice(_highlight.size() - n).duplicate(true)

func clear_buffer() -> void:
	_highlight.clear()
	_acc = 0.0

func encode_frame(tick: int, players: Array, ball: Dictionary, score: Array, clock: float) -> Dictionary:
	var p := []
	for q in players:
		var pos: Vector3 = q["pos"]
		var fc: Vector3 = q["facing"]
		p.append([roundi(pos.x * 100.0), roundi(pos.z * 100.0), roundi(fc.x * 100.0), roundi(fc.z * 100.0),
			_action_id(str(q.get("action", "idle")))])
	var bp: Vector3 = ball["pos"]
	return {"k": tick, "p": p, "b": [roundi(bp.x * 100.0), roundi(bp.y * 100.0), roundi(bp.z * 100.0), int(ball.get("owner", -1))],
		"s": [int(score[0]), int(score[1])], "c": snappedf(clock, 0.01)}

func _action_id(name: String) -> int:
	var i := actions.find(name)
	if i < 0:
		actions.append(name)
		i = actions.size() - 1
	return i

func _flush(final: bool) -> void:
	if _path.is_empty() or (_pending.is_empty() and not final):
		return
	var f := FileAccess.open(_path, FileAccess.READ_WRITE)
	if f == null:
		replay_error.emit("Cannot append replay to " + _path)
		return
	f.seek_end()
	for line in _pending:
		f.store_line(line)
		if not line.begins_with("{\"ev\""):
			frames_written += 1
	if final:
		f.store_line(JSON.stringify({"end": {"frames": frames_written, "score": _last_score, "actions": actions}}))
	f.close()
	_pending.clear()

# ---------------------------------------------------------------- library
func list_saved_replays() -> Array:
	var out: Array = []
	var da := DirAccess.open(REPLAY_DIR)
	if da == null:
		return out
	for fn in da.get_files():
		if fn.ends_with(".jsonl"):
			out.append(REPLAY_DIR + fn)
	out.sort_custom(func(a, b): return FileAccess.get_modified_time(a) > FileAccess.get_modified_time(b))
	return out

## Delete the oldest saved replays so at most `keep` remain (browser storage is limited).
func prune(keep: int = 10) -> int:
	var all := list_saved_replays()
	var removed := 0
	for i in range(keep, all.size()):
		if DirAccess.remove_absolute(all[i]) == OK:
			removed += 1
	return removed

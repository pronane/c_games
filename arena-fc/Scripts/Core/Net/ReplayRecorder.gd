# ReplayRecorder.gd
# Tier 1 — Replay viewer / highlights
# Records deterministic inputs during an online match so they can be replayed later.
# Attach to a persistent node (e.g. an Autoload) before match start.

class_name ReplayRecorder
extends Node

signal replay_saved(path: String, match_id: String)
signal replay_error(msg: String)

const REPLAY_DIR := "user://replays/"
const SAVE_INTERVAL_TICKS := 60  # flush to disk every 60 ticks (~1 second at 60Hz)

var recording := false
var replay_data := {}
var current_inputs := Array()
var current_events := Array()
var tick := 0
var match_id := ""
var room_code := ""
var seed := 0
var team_size := 5
var start_time := 0
var score := [0, 0]
var flush_counter := 0

func _ready() -> void:
	if not DirAccess.dir_exists_absolute(REPLAY_DIR):
		DirAccess.make_dir_absolute(REPLAY_DIR)

func start_recording(p_room_code: String, p_seed: int, p_team_size: int, p_match_id: String = "") -> void:
	if recording:
		return
	recording = true
	room_code = p_room_code
	seed = p_seed
	team_size = p_team_size
	match_id = p_match_id if not p_match_id.is_empty() else str(Time.get_unix_time_from_system())
	tick = 0
	score = [0, 0]
	current_inputs.clear()
	current_events.clear()
	start_time = Time.get_unix_time_from_system()
	replay_data = {
		"match_id": match_id,
		"room_code": room_code,
		"seed": seed,
		"team_size": team_size,
		"started_at": start_time,
		"version": 1,
		"inputs": [],
		"snapshots": [],
		"events": [],
		"score": score,
	}
	print("[ReplayRecorder] Recording started: match_id=", match_id, " room=", room_code)

func stop_recording() -> void:
	if not recording:
		return
	recording = false
	_flush_to_disk()
	print("[ReplayRecorder] Recording stopped: match_id=", match_id)

func record_input(slot: int, cmd: Dictionary) -> void:
	if not recording:
		return
	current_inputs.append({
		"tick": tick,
		"slot": slot,
		"cmd": cmd,
	})
	tick += 1
	flush_counter += 1
	if flush_counter >= SAVE_INTERVAL_TICKS:
		_flush_to_disk()
		flush_counter = 0

func record_event(event_type: String, data: Dictionary = {}) -> void:
	if not recording:
		return
	current_events.append({
		"tick": tick,
		"type": event_type,
		"data": data,
	})

func record_snapshot(tick: int, players: Array, ball: Dictionary, p_score: Array) -> void:
	if not recording:
		return
	replay_data["snapshots"].append({
		"tick": tick,
		"players": players,
		"ball": ball,
		"score": p_score,
	})
	score = p_score

func _flush_to_disk() -> void:
	if not recording:
		return
	var path := REPLAY_DIR + match_id + ".json"
	var file := FileAccess.open(path, FileAccess.WRITE)
	if file == null:
		replay_error.emit("Cannot write replay to " + path)
		return
	replay_data["inputs"] = current_inputs.duplicate()
	replay_data["events"] = current_events.duplicate()
	replay_data["score"] = score
	file.store_string(JSON.stringify(replay_data, "\t"))
	file.close()
	print("[ReplayRecorder] Flushed replay to ", path, " (ticks=", tick, " inputs=", current_inputs.size(), ")")

func save_replay() -> String:
	if not recording:
		return ""
	var path := REPLAY_DIR + match_id + ".json"
	_flush_to_disk()
	replay_saved.emit(path, match_id)
	return path

func list_saved_replays() -> Array:
	var out := Array()
	if not DirAccess.dir_exists_absolute(REPLAY_DIR):
		return out
	var da := DirAccess.open(REPLAY_DIR)
	if da == null:
		return out
	da.list_dir_begin()
	var file_name := da.get_next()
	while not file_name.is_empty():
		if file_name.ends_with(".json"):
			out.append(REPLAY_DIR + file_name)
		file_name = da.get_next()
	da.list_dir_end()
	out.sort_custom(func(a, b):
		var fa := FileAccess.open(a, FileAccess.READ)
		var fb := FileAccess.open(b, FileAccess.READ)
		if fa == null or fb == null:
			return false
		var ta := fa.get_modified_time()
		var tb := fb.get_modified_time()
		fa.close()
		fb.close()
		return ta > tb
	)
	return out

func load_replay(path: String) -> Dictionary:
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		replay_error.emit("Cannot read replay: " + path)
		return {}
	var text := file.get_as_text()
	file.close()
	var parsed := JSON.parse_string(text)
	return parsed if typeof(parsed) == TYPE_DICTIONARY else {}

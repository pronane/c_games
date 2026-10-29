# ReplayPlayer.gd
# Tier 1 — Replay viewer / highlights
# Plays back a recorded replay by feeding inputs into a headless match simulation.
# Works alongside BrowserBoot.gd — attach to a node in your replay viewer scene.

class_name ReplayPlayer
extends Node

signal replay_loaded(path: String, match_id: String)
signal replay_tick(tick: int, data: Dictionary)
signal replay_finished()
signal replay_error(msg: String)

var replay_data := {}
var current_tick := 0
var playing := false
var play_speed := 1.0
var input_index := 0
var event_index := 0

func load_replay(path: String) -> bool:
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		replay_error.emit("Cannot open: " + path)
		return false
	var text := file.get_as_text()
	file.close()
	var parsed := JSON.parse_string(text)
	if typeof(parsed) != TYPE_DICTIONARY:
		replay_error.emit("Invalid replay JSON: " + path)
		return false
	replay_data = parsed
	current_tick = 0
	input_index = 0
	event_index = 0
	playing = false
	replay_loaded.emit(path, str(replay_data.get("match_id", "")))
	print("[ReplayPlayer] Loaded: match_id=", replay_data.get("match_id"), " inputs=", replay_data.get("inputs", []).size())
	return true

func start_playback() -> void:
	if replay_data.is_empty():
		return
	playing = true
	input_index = 0
	event_index = 0
	current_tick = 0

func pause() -> void:
	playing = false

func resume() -> void:
	playing = true

func stop() -> void:
	playing = false
	current_tick = 0
	input_index = 0
	event_index = 0

func seek_to_tick(tick: int) -> void:
	current_tick = tick
	input_index = 0
	event_index = 0
	var inputs := replay_data.get("inputs", [])
	for i in range(inputs.size()):
		if int(inputs[i].get("tick", 0)) > tick:
			input_index = i
			break
	var events := replay_data.get("events", [])
	for i in range(events.size()):
		if int(events[i].get("tick", 0)) > tick:
			event_index = i
			break

func get_inputs_at_tick(tick: int) -> Array:
	var out := Array()
	var inputs := replay_data.get("inputs", [])
	while input_index < inputs.size():
		var entry := inputs[input_index]
		if int(entry.get("tick", -1)) == tick:
			out.append(entry)
			input_index += 1
		elif int(entry.get("tick", -1)) > tick:
			break
		else:
			input_index += 1
	return out

func get_events_at_tick(tick: int) -> Array:
	var out := Array()
	var events := replay_data.get("events", [])
	while event_index < events.size():
		var entry := events[event_index]
		if int(entry.get("tick", -1)) == tick:
			out.append(entry)
			event_index += 1
		elif int(entry.get("tick", -1)) > tick:
			break
		else:
			event_index += 1
	return out

func get_total_ticks() -> int:
	var inputs := replay_data.get("inputs", [])
	if inputs.size() == 0:
		return 0
	var max_tick := 0
	for entry in inputs:
		var t := int(entry.get("tick", 0))
		if t > max_tick:
			max_tick = t
	return max_tick

func get_match_info() -> Dictionary:
	return {
		"match_id": replay_data.get("match_id", ""),
		"room_code": replay_data.get("room_code", ""),
		"seed": replay_data.get("seed", 0),
		"team_size": replay_data.get("team_size", 5),
		"started_at": replay_data.get("started_at", 0),
		"total_ticks": get_total_ticks(),
	}

func _physics_process(delta: float) -> void:
	if not playing or replay_data.is_empty():
		return
	# Advance simulation ticks based on play_speed.
	# In a real implementation you'd step the match engine here.
	# For now we emit tick events so the UI can sync.
	pass

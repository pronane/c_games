class_name ArenaFCNetClient
extends Node
## Arena FC Browser Edition - WebSocket client for the Play With Friends server.
## Browsers cannot open raw UDP sockets (no ENet), so the browser build joins the
## same authoritative server over WebSocket and renders the same snapshots.
##
## v2: secure resume tokens (persisted in user://), automatic reconnect, host
## migration notices and full mid-match resume. Browsers cannot host the C#
## simulation, so they advertise caps=1 and are never chosen as a peer host.

signal connected(info: Dictionary)
signal lobby_changed(info: Dictionary)
signal match_begin(info: Dictionary)
signal match_resumed(info: Dictionary)
signal snapshot_received(pkt: Dictionary)
signal match_ended(info: Dictionary)
signal error_raised(msg: String)
signal disconnected_msg(msg: String)
signal host_changed(slot: int, reason: String)
signal reconnect_pending(attempt: int)

const VERSION := 2
const CAP_RECONNECT := 1       # browser capabilities bitmask
const BOOKMARK := "user://arena_fc_resume.json"

var ws: WebSocketPeer
var url := ""
var player_name := "Web Player"
var room := ""
var create_room := false
var slot := -1
var team := 0
var host_slot := -1
var team_size := 5
var ping_ms := -1
var names: Array = []
var slots: Array = []
var teams: Array = []
var pings: Array = []
var readys: Array = []
var onlines: Array = []
var in_match := false
var last_error := ""
var chat_line := ""
var seq := 0
var token := ""
var grace := 180
var resumed := false
var reconnect_attempts := 0
var authority := 0
var _connected := false
var _explicit := false
var _retry_at := -1.0
var _delay := 1.0
var _clock := 0.0
var _saved_at := 0


func connect_to(p_url: String, p_name: String, p_room: String, p_create: bool, p_token: String = "") -> void:
	close()
	_explicit = false
	url = p_url.strip_edges()
	# Same-origin relative path (e.g. "/ws"): upgrade to wss:// or ws:// based on page protocol.
	# This lets the browser build connect to the Node edge proxy on the public host instead of
	# a raw ws:// address that browsers block on HTTPS pages.
	if url.begins_with("/"):
		if OS.has_feature("web"):
			var proto := str(JavaScriptBridge.eval("window.location.protocol"))
			var host := str(JavaScriptBridge.eval("window.location.host"))
			var secure := proto.begins_with("https")
			url = ("wss://" if secure else "ws://") + host + url
		else:
			url = "ws://127.0.0.1:7777" + url
	# Page-relative ("./ws"): resolves against the page URL, so the same build works at the site root and
	# under a sub-path such as /arena/ on the shared Node hub.
	if url == "ws" or url.begins_with("./") or url.begins_with("../"):
		if OS.has_feature("web"):
			url = str(JavaScriptBridge.eval("new URL(%s, window.location.href).href.replace(/^http/, 'ws')" % JSON.stringify(url)))
		else:
			url = "ws://127.0.0.1:7777"
	if not url.contains("://"):
		url = "ws://" + url
	if url.ends_with("/"):
		url = url.substr(0, url.length() - 1)
	player_name = p_name.strip_edges()
	if player_name.is_empty():
		player_name = "Web Player"
	player_name = player_name.substr(0, 16)
	room = p_room.strip_edges().to_upper().replace(" ", "").replace("-", "")
	create_room = p_create
	token = p_token
	slot = -1
	in_match = false
	resumed = false
	reconnect_attempts = 0
	last_error = ""
	_delay = 1.0
	_open()


func reconnect_saved() -> bool:
	var b := load_bookmark()
	if b.is_empty():
		return false
	if Time.get_unix_time_from_system() - int(b.get("saved", 0)) > int(b.get("grace", 180)) - 5:
		return false
	connect_to(str(b.get("url", "")), str(b.get("name", player_name)),
			str(b.get("room", "")), false, str(b.get("token", "")))
	return true


func load_bookmark() -> Dictionary:
	if not FileAccess.file_exists(BOOKMARK):
		return {}
	var f := FileAccess.open(BOOKMARK, FileAccess.READ)
	if f == null:
		return {}
	var parsed: Variant = JSON.parse_string(f.get_as_text())
	f.close()
	return parsed if typeof(parsed) == TYPE_DICTIONARY else {}


func save_bookmark() -> void:
	if token.length() < 32 or room.length() < 3:
		return
	var f := FileAccess.open(BOOKMARK, FileAccess.WRITE)
	if f == null:
		return
	f.store_string(JSON.stringify({
		"url": url, "room": room, "name": player_name, "token": token,
		"slot": slot, "team": team, "grace": grace,
		"saved": Time.get_unix_time_from_system(),
	}))
	f.close()


func clear_bookmark() -> void:
	token = ""
	if FileAccess.file_exists(BOOKMARK):
		DirAccess.remove_absolute(ProjectSettings.globalize_path(BOOKMARK))


func _open() -> void:
	ws = WebSocketPeer.new()
	ws.inbound_buffer_size = 1 << 20
	ws.max_queued_packets = 2048
	_connected = false
	_retry_at = -1.0
	var err := ws.connect_to_url(url)
	if err != OK:
		last_error = "Cannot open %s (error %d)" % [url, err]
		error_raised.emit(last_error)
		ws = null
		_schedule_retry()


func _send(pkt: Dictionary) -> void:
	if ws == null or ws.get_ready_state() != WebSocketPeer.STATE_OPEN:
		return
	ws.send_text(JSON.stringify(pkt))


func send_input(cmd: Dictionary) -> void:
	seq += 1
	_send({"t": "input", "seq": seq, "cmd": cmd})


func send_start() -> void:
	_send({"t": "start"})


func send_ready(on: bool) -> void:
	_send({"t": "ready", "ready": on})


func send_chat(text: String) -> void:
	_send({"t": "chat", "m": text})


func is_host() -> bool:
	return slot >= 0 and slot == host_slot


func poll(delta: float) -> void:
	_clock += delta
	if ws == null:
		if not _explicit and _retry_at > 0.0 and _clock >= _retry_at:
			_open()
		return
	ws.poll()
	var state := ws.get_ready_state()
	if state == WebSocketPeer.STATE_CLOSED:
		var unexpected := _connected and not _explicit
		ws = null
		_connected = false
		disconnected_msg.emit(last_error if not last_error.is_empty() else "Disconnected from server.")
		if unexpected:
			_schedule_retry()
		return
	if not _connected:
		if state != WebSocketPeer.STATE_OPEN:
			return
		_connected = true
		_delay = 1.0
		var hello := {
			"t": "hello", "ver": VERSION, "name": player_name,
			"room": room, "create": create_room, "caps": CAP_RECONNECT,
		}
		if token.length() >= 32:
			hello["token"] = token
		_send(hello)
	var guard := 0
	while ws != null and ws.get_available_packet_count() > 0 and guard < 128:
		guard += 1
		var raw := ws.get_packet()
		if raw.is_empty():
			continue
		var parsed: Variant = JSON.parse_string(raw.get_string_from_utf8())
		if typeof(parsed) != TYPE_DICTIONARY:
			continue
		_handle(parsed)


func _schedule_retry() -> void:
	var b := load_bookmark()
	if b.is_empty() or Time.get_unix_time_from_system() - int(b.get("saved", 0)) > int(b.get("grace", 180)) - 5:
		disconnected_msg.emit("Disconnected - reconnect window expired.")
		return
	token = str(b.get("token", ""))
	url = str(b.get("url", url))
	room = str(b.get("room", room))
	player_name = str(b.get("name", player_name))
	create_room = false
	reconnect_attempts += 1
	_retry_at = _clock + _delay
	reconnect_pending.emit(reconnect_attempts)
	_delay = minf(8.0, _delay * 1.6)


func _handle(p: Dictionary) -> void:
	var t: String = str(p.get("t", ""))
	match t:
		"welcome":
			slot = int(p.get("slot", -1))
			team = int(p.get("team", 0))
			room = str(p.get("room", room))
			host_slot = int(p.get("host", 0))
			team_size = int(p.get("size", 5))
			grace = int(p.get("grace", 180))
			authority = int(p.get("authority", 0))
			in_match = bool(p.get("started", false))
			var issued: String = str(p.get("token", ""))
			if issued.length() >= 32:
				token = issued
				save_bookmark()
			print("ARENA_FC_WEB_WELCOME room=", room, " slot=", slot, " host=", host_slot, " token=", token.length())
			connected.emit(p)
		"lobby":
			room = str(p.get("room", room))
			host_slot = int(p.get("host", host_slot))
			team_size = int(p.get("size", team_size))
			authority = int(p.get("authority", authority))
			names = p.get("names", [])
			slots = p.get("slots", [])
			teams = p.get("teams", [])
			pings = p.get("pings", [])
			readys = p.get("readys", [])
			onlines = p.get("onlines", [])
			in_match = bool(p.get("started", false))
			lobby_changed.emit(p)
		"begin":
			in_match = true
			match_begin.emit(p)
		"resume":
			in_match = true
			resumed = true
			reconnect_attempts = 0
			match_resumed.emit(p)
		"snap":
			var arr: Array = p.get("pings", [])
			if slot >= 0 and slot < arr.size():
				ping_ms = int(arr[slot])
			snapshot_received.emit(p)
		"host":
			host_slot = int(p.get("host", host_slot))
			host_changed.emit(host_slot, str(p.get("reason", "Host changed.")))
		"ping":
			_send({"t": "pong", "ms": p.get("ms", 0)})
		"chat":
			chat_line = "%s: %s" % [p.get("name", "?"), p.get("m", "")]
		"end":
			in_match = false
			match_ended.emit(p)
		"error":
			last_error = str(p.get("reason", "Server error"))
			error_raised.emit(last_error)


func close() -> void:
	_explicit = true
	if ws != null:
		ws.close()
		ws = null
	_connected = false
	_retry_at = -1.0

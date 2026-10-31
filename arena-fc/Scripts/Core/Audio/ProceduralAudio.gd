# ProceduralAudio.gd
# Procedural sound effects: every sound is synthesised in code, no .wav/.ogg files.
#
# Registered as the autoload "Audio" (see project.godot), so both the Godot desktop client
# (C#) and the browser edition (GDScript) can call it:
#     Audio.play_kick()                         # GDScript
#     GetNode("/root/Audio").Call("play_kick")  # C#
#
# How it works: each effect is rendered once into a PackedFloat32Array (cached), then
# "voices" are mixed together in _process() into one AudioStreamGenerator. Rendering is
# seeded, so a sound is identical on every device.
class_name ProceduralAudio
extends Node

@export var master_volume: float = 0.7
@export var enabled: bool = true
const MIX_RATE := 22050          # low rate keeps the web build cheap; these are short, dull sounds
const MAX_VOICES := 12

var _gen: AudioStreamGenerator
var _playback: AudioStreamGeneratorPlayback
var _player: AudioStreamPlayer
var _cache: Dictionary = {}       # name -> PackedFloat32Array
var _voices: Array = []           # [{s: PackedFloat32Array, i: int, g: float}]
var _last_played: Dictionary = {} # name -> msec, to stop machine-gunning the same sound

func _ready() -> void:
	_gen = AudioStreamGenerator.new()
	_gen.mix_rate = MIX_RATE
	_gen.buffer_length = 0.25
	_player = AudioStreamPlayer.new()
	_player.stream = _gen
	_player.bus = &"Master"
	add_child(_player)
	_player.play()
	_playback = _player.get_stream_playback() as AudioStreamGeneratorPlayback

# ---------------------------------------------------------------- mixer
func _process(_delta: float) -> void:
	if _playback == null:
		return
	var frames := _playback.get_frames_available()
	if frames <= 0:
		return
	var buf := PackedVector2Array()
	buf.resize(frames)
	if _voices.is_empty():
		_playback.push_buffer(buf)       # silence keeps the generator fed
		return
	for v in _voices:
		var s: PackedFloat32Array = v["s"]
		var i: int = v["i"]
		var g: float = v["g"] * master_volume
		var n := mini(frames, s.size() - i)
		for k in range(n):
			var x := s[i + k] * g
			buf[k] = Vector2(buf[k].x + x, buf[k].y + x)
		v["i"] = i + n
	for k in range(frames):             # soft clip so stacked voices never wrap around
		var l := buf[k].x
		buf[k] = Vector2(l / (1.0 + absf(l)), l / (1.0 + absf(l)))
	_playback.push_buffer(buf)
	_voices = _voices.filter(func(v): return v["i"] < (v["s"] as PackedFloat32Array).size())

func _play(sfx: String, gain: float = 1.0, min_gap_ms: int = 40) -> void:
	if not enabled or _playback == null:
		return
	var now := Time.get_ticks_msec()
	if now - int(_last_played.get(sfx, -100000)) < min_gap_ms:
		return
	_last_played[sfx] = now
	if _voices.size() >= MAX_VOICES:
		_voices.pop_front()
	_voices.append({"s": render(sfx), "i": 0, "g": gain})

# ---------------------------------------------------------------- synthesis
## Render (or fetch from cache) the samples for an effect. Public so tests can inspect it.
func render(sfx: String) -> PackedFloat32Array:
	if _cache.has(sfx):
		return _cache[sfx]
	var out := PackedFloat32Array()
	match sfx:
		"kick":
			out = _mix([_tone(130.0, 0.14, 0.7, 40.0), _noise(0.03, 0.3, 4000.0, 1)])
		"pass":
			out = _mix([_tone(170.0, 0.09, 0.45, 30.0), _noise(0.02, 0.2, 3000.0, 2)])
		"tackle":
			out = _mix([_noise(0.2, 0.55, 700.0, 3), _tone(62.0, 0.2, 0.5, 20.0)])
		"whistle":
			out = _concat([_whistle(1250.0, 0.16), _silence(0.04), _whistle(1500.0, 0.3)])
		"goal":
			out = _mix([
				_concat([_tone(523.0, 0.15, 0.5, 0.0), _tone(659.0, 0.15, 0.5, 0.0), _tone(784.0, 0.4, 0.6, 0.0)]),
				_noise(1.4, 0.4, 1800.0, 4, true)])
		"bounce":
			out = _mix([_tone(85.0, 0.09, 0.5, 30.0), _tone(420.0, 0.04, 0.2, 100.0)])
		"post":
			out = _mix([_tone(520.0, 0.35, 0.45, 5.0), _tone(1040.0, 0.2, 0.2, 5.0)])
		"cheer":
			out = _noise(1.2, 0.35, 2000.0, 5, true)
		"net":
			out = _mix([_noise(0.25, 0.3, 1500.0, 6), _tone(95.0, 0.2, 0.3, 10.0)])
		_:
			out = _silence(0.01)
	_cache[sfx] = out
	return out

func _silence(sec: float) -> PackedFloat32Array:
	var a := PackedFloat32Array()
	a.resize(int(sec * MIX_RATE))
	return a

# Sine with an exponential decay. `decay_rate` is in 1/s; 0 means a flat tone with a short fade.
func _tone(freq: float, sec: float, vol: float, decay_rate: float) -> PackedFloat32Array:
	var n := int(sec * MIX_RATE)
	var a := PackedFloat32Array()
	a.resize(n)
	var ph := 0.0
	var step := TAU * freq / MIX_RATE
	var fade := maxi(1, int(0.01 * MIX_RATE))
	for i in range(n):
		var env := exp(-decay_rate * float(i) / MIX_RATE)
		env *= minf(1.0, float(i) / fade) * minf(1.0, float(n - i) / fade)
		a[i] = sin(ph) * env * vol
		ph += step
	return a

# Referee whistle: a tone with fast vibrato (the "pea") and a slight rise.
func _whistle(freq: float, sec: float) -> PackedFloat32Array:
	var n := int(sec * MIX_RATE)
	var a := PackedFloat32Array()
	a.resize(n)
	var ph := 0.0
	var fade := maxi(1, int(0.015 * MIX_RATE))
	for i in range(n):
		var t := float(i) / MIX_RATE
		var f := freq * (1.0 + 0.02 * t) + 55.0 * sin(TAU * 38.0 * t)
		ph += TAU * f / MIX_RATE
		a[i] = sin(ph) * 0.55 * minf(1.0, float(i) / fade) * minf(1.0, float(n - i) / fade)
	return a

# Low-passed noise (one-pole). `swell` fades in and out like a crowd instead of decaying.
func _noise(sec: float, vol: float, cutoff: float, seed_: int, swell: bool = false) -> PackedFloat32Array:
	var rng := RandomNumberGenerator.new()
	rng.seed = 7919 * (seed_ + 1)
	var n := int(sec * MIX_RATE)
	var a := PackedFloat32Array()
	a.resize(n)
	var k := clampf(TAU * cutoff / (TAU * cutoff + MIX_RATE), 0.01, 1.0)
	var y := 0.0
	for i in range(n):
		y += (rng.randf() * 2.0 - 1.0 - y) * k
		var x := float(i) / maxf(1.0, float(n))
		var env := (sin(PI * x) if swell else (1.0 - x))
		a[i] = y * env * vol * 2.2
	return a

func _mix(parts: Array) -> PackedFloat32Array:
	var n := 0
	for p in parts:
		n = maxi(n, (p as PackedFloat32Array).size())
	var a := PackedFloat32Array()
	a.resize(n)
	for p in parts:
		var s: PackedFloat32Array = p
		for i in range(s.size()):
			a[i] += s[i]
	return a

func _concat(parts: Array) -> PackedFloat32Array:
	var a := PackedFloat32Array()
	for p in parts:
		a.append_array(p)
	return a

# ---------------------------------------------------------------- public effects
func play_kick() -> void: _play("kick", 1.0, 60)
func play_pass() -> void: _play("pass", 0.9, 60)
func play_tackle() -> void: _play("tackle", 1.0, 120)
func play_whistle() -> void: _play("whistle", 0.8, 300)
func play_whistle_start() -> void: play_whistle()
func play_goal() -> void: _play("goal", 1.0, 800)
func play_ball_bounce() -> void: _play("bounce", 0.6, 90)
func play_post() -> void: _play("post", 0.9, 200)
func play_net() -> void: _play("net", 0.8, 300)
func play_crowd_cheer(_duration_sec: float = 1.2) -> void: _play("cheer", 0.7, 500)

## Map a match event name (the C# EventKind names, or the browser edition's own) to a sound.
func play_for_event(kind: String) -> void:
	match kind.to_lower():
		"goal": play_goal()
		"shot": play_kick()
		"pass": play_pass()
		"post": play_post()
		"tackle", "save": play_tackle()
		"foul", "whistle", "offside", "card": play_whistle()
		"out": play_ball_bounce()
		_: pass

## Which sound a commentary line should make ("" = none). Goals are handled from the score change,
## so "GOAL" lines map to "" to avoid playing the jingle twice.
static func event_for_text(text: String) -> String:
	var t := text.to_lower()
	if t.contains("goal kick"):
		return "out"
	if t.contains("goal"):
		return ""
	if t.contains("post") or t.contains("crossbar"):
		return "post"
	if t.contains("shoots") or t.contains("shot"):
		return "shot"
	if t.contains("wins the ball") or t.contains("tackle"):
		return "tackle"
	if t.contains("foul") or t.contains("offside") or t.contains("half time") or t.contains("full time") \
			or t.contains("penalty") or t.contains("free kick") or t.contains("yellow") or t.contains("red card"):
		return "whistle"
	if t.contains("\u2192") or t.contains("pass"):
		return "pass"
	return ""

## Lines in `cur` that were not in `prev`, where both are sliding windows of the same feed
## (oldest first). Returns [] for the first call, which only primes the window.
static func new_lines(prev: Array, cur: Array, primed: bool) -> Array:
	if not primed:
		return []
	for shift in range(prev.size() + 1):
		var overlap := prev.size() - shift
		if overlap > cur.size():
			continue
		var same := true
		for i in range(overlap):
			if prev[shift + i] != cur[i]:
				same = false
				break
		if same:
			return cur.slice(overlap)
	return cur.duplicate()

func set_enabled(on: bool) -> void:
	enabled = on
	if not on:
		_voices.clear()

func toggle() -> bool:
	set_enabled(not enabled)
	return enabled

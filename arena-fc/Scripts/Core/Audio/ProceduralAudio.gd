# ProceduralAudio.gd
# Tier 2 — Procedural audio
# Generates sound effects programmatically instead of relying on static .wav/.ogg samples.
# Uses AudioStreamGenerator to synthesize sine waves, noise bursts, and envelopes at runtime.
# Attach to an Autoload (e.g. "Audio") and call play_kick(), play_tackle(), etc.

class_name ProceduralAudio
extends Node

@export var master_volume: float = 0.7
@export var sample_rate: int = 44100

var generator: AudioStreamGenerator
var playback: AudioStreamGeneratorPlayback

# ---------------------------------------------------------------- init
func _ready() -> void:
	generator = AudioStreamGenerator.new()
	generator.mix_rate = sample_rate
	generator.buffer_seconds = 1.0
	var stream_player := AudioStreamPlayer.new()
	stream_player.stream = generator
	add_child(stream_player)
	playback = generator.stream_playback()
	playback.start()

# ---------------------------------------------------------------- low-level synth
# Write a mono signal into the generator buffer as a burst of samples.
func _play_buffer(samples: Float32Array, volume: float = 1.0) -> void:
	if playback == null:
		return
	var frames := samples.size()
	# Push chunks of 1024 frames to avoid overflow
	var chunk := 1024
	var offset := 0
	while offset < frames:
		var end := min(offset + chunk, frames)
		var slice := samples.slice(offset, end - offset)
		# Apply volume
		for i in range(slice.size()):
			slice[i] = slice[i] * volume * master_volume
		playback.push_buffer(slice)
		offset = end

# Generate a sine wave burst with ADSR-ish envelope.
func _tone(freq: float, duration_sec: float, volume: float = 0.5, attack: float = 0.01, decay: float = 0.1, sustain: float = 0.3, release: float = 0.1) -> void:
	var total_frames := int(duration_sec * sample_rate)
	var samples := Float32Array(total_frames)
	var phase := 0.0
	var phase_step := (TAU * freq) / sample_rate
	var attack_frames := int(attack * sample_rate)
	var release_frames := int(release * sample_rate)
	for i in range(total_frames):
		var env := 1.0
		if i < attack_frames:
			env = i / attack_frames
		elif i > total_frames - release_frames:
			env = (total_frames - i) / release_frames
		env = clamp(env * sustain, 0.0, 1.0) if i >= attack_frames else env
		samples[i] = sin(phase) * env
		phase += phase_step
	_play_buffer(samples, volume)

# Generate a noise burst (white noise filtered by envelope).
func _noise(duration_sec: float, volume: float = 0.4, decay: float = 0.05, lowpass_freq: float = 1000.0) -> void:
	var total_frames := int(duration_sec * sample_rate)
	var samples := Float32Array(total_frames)
	var decay_frames := int(decay * sample_rate)
	var prev := 0.0
	var lp_coeff := lowpass_freq / (lowpass_freq + sample_rate)  # simple one-pole LP
	for i in range(total_frames):
		var raw := randf() * 2.0 - 1.0
		prev = prev + (raw - prev) * lp_coeff
		var env := 1.0
		if i > total_frames - decay_frames:
			env = (total_frames - i) / decay_frames
		samples[i] = prev * env
	_play_buffer(samples, volume)

# ---------------------------------------------------------------- public SFX
func play_kick() -> void:
	# Football strike: low thud + high tick
	_tone(120.0, 0.15, 0.6, 0.005, 0.05, 0.4, 0.05)
	_tone(900.0, 0.08, 0.3, 0.001, 0.02, 0.5, 0.02)

func play_tackle() -> void:
	# Body impact: noise burst + low thud
	_noise(0.2, 0.5, 0.08, 800.0)
	_tone(60.0, 0.2, 0.4, 0.01, 0.1, 0.3, 0.1)

func play_whistle() -> void:
	# Referee whistle: two short tones
	_tone(1200.0, 0.12, 0.7, 0.005, 0.02, 0.8, 0.05)
	_tone(1500.0, 0.12, 0.7, 0.005, 0.02, 0.8, 0.05)

func play_goal() -> void:
	# Goal: rising arpeggio + crowd cheer noise
	_tone(523.0, 0.15, 0.6, 0.01, 0.05, 0.7, 0.1)  # C5
	_tone(659.0, 0.15, 0.6, 0.01, 0.05, 0.7, 0.1)  # E5
	_tone(784.0, 0.3, 0.8, 0.01, 0.1, 0.8, 0.2)    # G5
	_noise(0.8, 0.4, 0.3, 1500.0)                  # crowd

func play_ball_bounce() -> void:
	# Ball bounce: soft thud + rubber tick
	_tone(80.0, 0.1, 0.4, 0.005, 0.03, 0.4, 0.02)
	_tone(400.0, 0.05, 0.2, 0.001, 0.01, 0.5, 0.01)

func play_whistle_start() -> void:
	play_whistle()

func play_crowd_cheer(duration_sec: float = 1.0) -> void:
	_noise(duration_sec, 0.35, duration_sec * 0.4, 2000.0)

# Adapted from piano_transcription_inference 0.0.6 (Qiuqiang Kong, MIT licence; see LICENSE in this
# folder). The guitar weights are Riley, Edwards & Dixon (ICASSP 2024). Changes for Guitar Lab are noted.
sample_rate = 16000
classes_num = 88    # Number of notes of piano
begin_note = 21     # MIDI note of A0, the lowest note of a piano.
segment_seconds = 10.	# Training segment duration
hop_seconds = 1.
frames_per_second = 100
velocity_scale = 128
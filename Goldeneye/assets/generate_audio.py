import math
import os
import random
import struct
import wave


SAMPLE_RATE = 22050


def write_wave(path, samples):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    pcm = [max(-32768, min(32767, round(sample * 32767))) for sample in samples]
    with wave.open(path, "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(SAMPLE_RATE)
        output.writeframes(struct.pack("<" + "h" * len(pcm), *pcm))


def make_shot(path, seed, low_frequency, noise_level):
    random_source = random.Random(seed)
    count = int(SAMPLE_RATE * 0.18)
    samples = []
    for index in range(count):
        time = index / SAMPLE_RATE
        envelope = math.exp(-time * 25.0)
        pitch = low_frequency + 90.0 * math.exp(-time * 38.0)
        thump = math.sin(2.0 * math.pi * pitch * time) * 0.48
        crack = random_source.uniform(-1.0, 1.0) * noise_level
        samples.append(envelope * (thump + crack))
    write_wave(path, samples)


def make_pickup(path):
    count = int(SAMPLE_RATE * 0.32)
    notes = (660.0, 880.0, 1100.0)
    samples = []
    for index in range(count):
        time = index / SAMPLE_RATE
        sample = 0.0
        for note_index, frequency in enumerate(notes):
            start = note_index * 0.075
            elapsed = time - start
            if elapsed >= 0.0:
                envelope = math.exp(-elapsed * 18.0)
                sample += math.sin(2.0 * math.pi * frequency * elapsed) * envelope * 0.2
        samples.append(sample)
    write_wave(path, samples)


def make_reload(path, seed):
    random_source = random.Random(seed)
    count = int(SAMPLE_RATE * 0.38)
    samples = []
    for index in range(count):
        time = index / SAMPLE_RATE
        sample = 0.0
        for start, strength in ((0.045, 0.7), (0.245, 0.5)):
            elapsed = time - start
            if 0.0 <= elapsed < 0.04:
                envelope = math.exp(-elapsed * 95.0)
                noise = random_source.uniform(-1.0, 1.0) * 0.32
                ring = math.sin(2.0 * math.pi * 1350.0 * elapsed) * 0.48
                sample += strength * envelope * (noise + ring)
        samples.append(sample)
    write_wave(path, samples)


def main():
    audio = os.path.join(os.path.dirname(os.path.abspath(__file__)), "audio")
    make_shot(os.path.join(audio, "sidearm.wav"), 1729, 92.0, 0.45)
    make_shot(os.path.join(audio, "carbine.wav"), 2718, 135.0, 0.38)
    make_pickup(os.path.join(audio, "pickup.wav"))
    make_reload(os.path.join(audio, "reload.wav"), 3141)


if __name__ == "__main__":
    main()

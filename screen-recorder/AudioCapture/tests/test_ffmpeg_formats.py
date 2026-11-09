import os
import subprocess
import tempfile
import unittest

import numpy as np
import soundfile as sf

from audiocapture.editing import AudioEditSession
from audiocapture.ffmpeg_support import ffmpeg_executable
from audiocapture.recorder import AudioFile


class CompressedFormatTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.rate = 48000
        t = np.arange(self.rate, dtype=np.float32) / self.rate
        self.samples = (0.25 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
        self.wav = os.path.join(self.tmp.name, "tone.wav")
        sf.write(self.wav, self.samples, self.rate, subtype="FLOAT")
        self.session = AudioEditSession(AudioFile(self.wav))
        self.ffmpeg = ffmpeg_executable()

    def tearDown(self):
        self.tmp.cleanup()

    def test_export_m4a_aac_and_mp3_high_bitrate(self):
        for ext, enc, bitrate in (("m4a", "aac", 320), ("mp3", "mp3", 320), ("mp3", "mp3", 256)):
            path = os.path.join(self.tmp.name, f"tone-{bitrate}.{ext}")
            self.session.export(path, bitrate_kbps=bitrate)
            self.assertGreater(os.path.getsize(path), 1000)
            decoded = AudioFile(path)
            self.assertIsNone(decoded.error, decoded.error)
            self.assertAlmostEqual(decoded.duration, 1.0, delta=0.08)
            decoded.close()

    def test_mp4_import_extracts_audio_only(self):
        video = os.path.join(self.tmp.name, "with-audio.mp4")
        cmd = [self.ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
               "-f", "lavfi", "-i", "color=c=black:s=64x64:d=1:r=2",
               "-i", self.wav, "-shortest", "-c:v", "mpeg4", "-c:a", "aac", video]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        audio = AudioFile(video)
        self.assertIsNone(audio.error, audio.error)
        self.assertAlmostEqual(audio.duration, 1.0, delta=0.08)
        self.assertEqual(audio.channels, 1)
        self.assertTrue(audio._temporary_decode_path)
        self.assertTrue(os.path.exists(audio._temporary_decode_path))
        decoded_path = audio._temporary_decode_path
        audio.close()
        self.assertFalse(os.path.exists(decoded_path))


if __name__ == "__main__":
    unittest.main()

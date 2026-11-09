import os
import tempfile
import threading
import unittest

import numpy as np

from audiocapture.recorder import AudioFile, Recorder


class CompressedRecordingWriterTests(unittest.TestCase):
    def test_live_writer_encodes_high_bitrate_m4a_and_mp3(self):
        with tempfile.TemporaryDirectory() as directory:
            rate, channels = 48000, 2
            t = np.arange(rate, dtype=np.float32) / rate
            mono = 0.2 * np.sin(2 * np.pi * 440 * t)
            data = np.column_stack((mono, mono * 0.7)).astype(np.float32)
            for label, ext in (("M4A AAC 320", ".m4a"), ("MP3 320", ".mp3")):
                path = os.path.join(directory, "tone" + ext)
                writer = Recorder(None, path, rate, channels, label)
                writer._q.put(data)
                writer._q.put(None)
                thread = threading.Thread(target=writer._writer_loop)
                thread.start(); thread.join(30)
                self.assertFalse(thread.is_alive(), f"encoder hung for {label}")
                self.assertIsNone(writer._writer_error, writer._writer_error)
                self.assertTrue(os.path.exists(path))
                audio = AudioFile(path)
                self.assertIsNone(audio.error, audio.error)
                self.assertAlmostEqual(audio.duration, 1.0, delta=0.1)
                self.assertEqual(audio.channels, channels)
                audio.close()


if __name__ == "__main__":
    unittest.main()

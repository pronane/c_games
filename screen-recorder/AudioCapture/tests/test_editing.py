import os
import tempfile
import unittest

import numpy as np
import soundfile as sf

from audiocapture.editing import AudioEditSession
from audiocapture.recorder import AudioFile


class AudioEditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.source = os.path.join(self.tmp.name, 'source.wav')
        self.rate = 1000
        self.samples = np.arange(10000, dtype=np.float32).reshape(-1, 1) / 10000
        sf.write(self.source, self.samples, self.rate, subtype='FLOAT')
        self.session = AudioEditSession(AudioFile(self.source))
        self.source_size = os.path.getsize(self.source)

    def tearDown(self):
        self.tmp.cleanup()

    def test_trim_remove_middle_undo_redo_and_export(self):
        self.session.remove(2, 4)
        self.assertEqual(self.session.duration_frames, 8000)
        self.assertTrue(self.session.undo())
        self.assertEqual(self.session.duration_frames, 10000)
        self.assertTrue(self.session.redo())
        output = os.path.join(self.tmp.name, 'cut.wav')
        self.session.export(output)
        out, rate = sf.read(output, dtype='float32', always_2d=True)
        self.assertEqual(rate, self.rate)
        self.assertEqual(len(out), 8000)
        np.testing.assert_array_equal(out[:, 0], np.concatenate([self.samples[:2000, 0], self.samples[4000:, 0]]))

    def test_trim_and_preview_do_not_mutate_source(self):
        self.session.trim(1, 3)
        preview = os.path.join(self.tmp.name, 'selection.wav')
        self.session.export_selection(preview, .5, 1.5)
        audio, rate = sf.read(preview, dtype='float32', always_2d=True)
        self.assertEqual(len(audio), 1000)
        self.assertEqual(rate, self.rate)
        self.assertEqual(self.session.duration_frames, 2000)
        self.assertEqual(os.path.getsize(self.source), self.source_size)

    def test_full_remove_rejected(self):
        with self.assertRaises(ValueError):
            self.session.remove(0, 10)


if __name__ == '__main__':
    unittest.main()

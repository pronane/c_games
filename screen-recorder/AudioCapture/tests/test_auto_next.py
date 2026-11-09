import unittest

from audiocapture.auto_next import SilenceAutoAdvance


class SilenceAutoAdvanceTests(unittest.TestCase):
    def test_grace_period_then_continuous_silence(self):
        watch = SilenceAutoAdvance(delay_seconds=150, silence_seconds=5)
        watch.reset(0)
        self.assertFalse(watch.update(149.9, 0.0))
        self.assertFalse(watch.update(150, 0.0))
        self.assertFalse(watch.update(154.9, 0.0))
        self.assertTrue(watch.update(155, 0.0))
        self.assertFalse(watch.update(200, 0.0))  # only one trigger per URL

    def test_sound_resets_silence_timer(self):
        watch = SilenceAutoAdvance(delay_seconds=0, silence_seconds=5)
        watch.reset(10)
        self.assertFalse(watch.update(10, .01))  # establishes audio start
        self.assertFalse(watch.update(10, 0.0))
        self.assertFalse(watch.update(14.9, 0.0))
        self.assertFalse(watch.update(15, .01))  # sound returned, timer resets
        self.assertFalse(watch.update(19.9, 0.0))
        self.assertTrue(watch.update(24.9, 0.0))

    def test_pause_does_not_accumulate_silence(self):
        watch = SilenceAutoAdvance(delay_seconds=0, silence_seconds=5)
        watch.reset(0)
        watch.update(0, .02)
        watch.update(1, 0.0)
        watch.update(4, 0.0, paused=True)
        self.assertFalse(watch.update(100, 0.0, paused=True))
        self.assertFalse(watch.update(100, 0.0))
        self.assertFalse(watch.update(104.9, 0.0))
        self.assertTrue(watch.update(105, 0.0))

    def test_pause_freezes_grace_period_as_well_as_silence(self):
        watch = SilenceAutoAdvance(delay_seconds=10, silence_seconds=5)
        watch.reset(0)
        watch.update(0, .01)
        watch.update(4, .0)
        watch.update(4, .0, paused=True)
        self.assertFalse(watch.update(104, .0, paused=True))
        self.assertFalse(watch.update(104, .0))  # only 4 s of playback elapsed
        self.assertFalse(watch.update(109.9, .0))
        self.assertFalse(watch.update(110, .0))  # silence timer starts here
        self.assertTrue(watch.update(115, .0))

    def test_never_played_url_skips_after_delay_and_silence(self):
        watch = SilenceAutoAdvance(delay_seconds=120, silence_seconds=5)
        watch.reset(50)
        self.assertFalse(watch.update(169.9, 0.0))
        self.assertFalse(watch.update(170, 0.0))
        self.assertTrue(watch.update(175, 0.0))


if __name__ == "__main__":
    unittest.main()

"""Notation playback stays the same as main.

The golden arrays were rendered from the note list below with the playback
voices on main (dual acoustic / distorted approximation). A change to those
voices fails this test. Uploaded charts become this same note list before
they are played; the voices do not read the chart a second time.
"""
import json
from pathlib import Path

import numpy as np

from server.fx.playback import render_acoustic, render_distorted

FIX = Path(__file__).parent / 'fixtures'
NOTES = json.loads((FIX / 'playback_notes.json').read_text())


def test_acoustic_and_distorted_playback_match_locked_pcm():
    acoustic = render_acoustic(NOTES, sr=22050, length_s=2.0)
    distorted = render_distorted(NOTES, sr=22050, length_s=2.0, stereo=True)
    assert np.array_equal(acoustic, np.load(FIX / 'playback_acoustic.npy'))
    assert np.array_equal(distorted, np.load(FIX / 'playback_distorted.npy'))


def test_playback_is_deterministic():
    first = render_acoustic(NOTES, sr=22050, length_s=2.0)
    second = render_acoustic(NOTES, sr=22050, length_s=2.0)
    assert np.array_equal(first, second)

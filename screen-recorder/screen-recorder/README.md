# screen-recorder

A small, reusable desktop/game-screen recorder for the `c_games` collection. It captures a monitor (or a rectangular region) to MP4 using FFmpeg and supports **pause/resume** without adding paused time or blank frames. It does not capture audio in this first version.

## Requirements

- Python 3.10+
- FFmpeg on `PATH`, built with `libx264`
- Python packages in `requirements.txt` (`mss`, `numpy`)

## CLI

```bash
python -m pip install -r requirements.txt
python -m screen_recorder --output recordings/gameplay.mp4 --fps 30 --monitor 1
```

Press **Ctrl+C** to finish and finalize the MP4. The default monitor is monitor 1 (the primary display). On multi-monitor systems, monitor numbers are 1-based; monitor 0 is the combined virtual desktop and can include gaps between displays.

For region capture, supply the desktop-coordinate rectangle:

```bash
python -m screen_recorder --output clip.mp4 --region 100 100 1280 720
```

## Python API

```python
from screen_recorder import ScreenRecorder

recorder = ScreenRecorder("clip.mp4", fps=30, monitor=1)
recorder.start()
# ... user/game interaction ...
recorder.pause()    # stops accepting frames; paused time is excluded
recorder.resume()   # continue in the same MP4
recorder.stop()     # closes FFmpeg and finalizes the file
```

Call `stop()` in a `finally` block in long-running integrations. A recording is not finalized until `stop()` completes.

## Notes

- The MP4 video uses H.264 CRF 18 by default, a high-quality lossy video setting. `--crf 0` requests x264's lossless coding mode, but the BGR-to-YUV420 color conversion is still not pixel-bit-exact; screen content is not promised to be mathematically identical.
- This module records screen video only. It does not capture system audio, input devices, protected content, or bypass OS restrictions.
- Tests use fake frame and encoder backends, so they run without a display, FFmpeg, or recording permissions.

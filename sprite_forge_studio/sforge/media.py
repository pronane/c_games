"""Video I/O without a hand-installed ffmpeg.

Order of preference for the ffmpeg executable:
  1. $SFS_FFMPEG                      (explicit path)
  2. imageio-ffmpeg (pip)             ships a static ffmpeg binary inside the wheel - no system install
  3. ffmpeg on PATH                   (apt / MSYS2 pacman / winget / brew ...)
If no ffmpeg exists at all, decoding falls back to OpenCV's VideoCapture (opencv-python-headless wheels
carry their own FFmpeg build) and then to PyAV ("av" wheel).  Encoding (tutorial / orbit mp4s) needs an
ffmpeg executable or OpenCV's VideoWriter (mp4v).  ffprobe is never required: stream info is parsed from
`ffmpeg -i` or read via OpenCV.
"""
from __future__ import annotations
import os
import re
import shutil
import subprocess
import time
import numpy as np

_FF = None


def ffmpeg_exe():
    """-> (path or None, source label)."""
    global _FF
    if _FF is not None:
        return _FF
    p = os.environ.get("SFS_FFMPEG", "")
    if p and os.path.isfile(p):
        _FF = (p, "SFS_FFMPEG")
        return _FF
    try:
        import imageio_ffmpeg
        p = imageio_ffmpeg.get_ffmpeg_exe()
        if p and os.path.isfile(p):
            _FF = (p, "imageio-ffmpeg (pip)")
            return _FF
    except Exception:
        pass
    p = shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")
    _FF = (p, "system PATH") if p else (None, "none")
    return _FF


def _cv2():
    try:
        import cv2
        return cv2
    except Exception:
        return None


def _av():
    try:
        import av
        return av
    except Exception:
        return None


def backend():
    ff, src = ffmpeg_exe()
    if ff:
        return "ffmpeg [%s]" % src
    if _cv2() is not None:
        return "opencv VideoCapture"
    if _av() is not None:
        return "PyAV"
    return None


def probe(path):
    """-> dict(w, h, fps, n, duration).  No ffprobe needed."""
    if not os.path.isfile(path):
        raise ValueError("video not found: %s" % path)
    ff, _ = ffmpeg_exe()
    if ff:
        r = subprocess.run([ff, "-hide_banner", "-i", path], capture_output=True, text=True, errors="replace")
        txt = r.stderr
        m = re.search(r"Stream #\S+.*?Video:.*?[ ,](\d{2,5})x(\d{2,5})[ ,\[\n]", txt)
        if m:
            w, h = int(m.group(1)), int(m.group(2))
            fm = re.search(r"Video:.*?([\d.]+) fps", txt) or re.search(r"Video:.*?([\d.]+) tbr", txt)
            fps = float(fm.group(1)) if fm else 30.0
            dm = re.search(r"Duration: (\d+):(\d+):([\d.]+)", txt)
            dur = (int(dm.group(1)) * 3600 + int(dm.group(2)) * 60 + float(dm.group(3))) if dm else 0.0
            rot = re.search(r"rotate\s*:\s*(-?\d+)", txt) or re.search(r"rotation of (-?[\d.]+)", txt)
            if rot and abs(round(float(rot.group(1)))) % 180 == 90:
                w, h = h, w            # ffmpeg auto-rotates phone clips on decode
            return dict(w=w, h=h, fps=fps, n=int(round(dur * fps)), duration=dur)
        raise ValueError("cannot read video %s: %s" % (path, txt.strip().splitlines()[-1][:200] if txt.strip() else "?"))
    cv2 = _cv2()
    if cv2 is not None:
        cap = cv2.VideoCapture(path)
        if cap.isOpened():
            w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = cap.get(cv2.CAP_PROP_FPS) or 30.0; n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            cap.release()
            return dict(w=w, h=h, fps=fps, n=n, duration=n / fps if fps else 0)
    av = _av()
    if av is not None:
        with av.open(path) as c:
            s = c.streams.video[0]
            fps = float(s.average_rate or 30)
            return dict(w=s.width, h=s.height, fps=fps, n=int(s.frames or 0), duration=float(s.duration * s.time_base) if s.duration else 0)
    raise ValueError("no video decoder: pip install imageio-ffmpeg (or opencv-python-headless)")


def read_frames(path, w, h, start=None, end=None, vf_extra=None):
    """-> uint8 array (N,h,w,3) RGB, resized to w x h.  vf_extra = extra ffmpeg filters (ignored by fallbacks)."""
    ff, _ = ffmpeg_exe()
    if ff:
        cmd = [ff, "-v", "error"]
        if start:
            cmd += ["-ss", "%.3f" % float(start)]
        cmd += ["-i", path]
        if end:
            cmd += ["-t", "%.3f" % (float(end) - float(start or 0))]
        vf = ["scale=%d:%d" % (w, h)] + list(vf_extra or [])
        cmd += ["-vf", ",".join(vf), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
        raw = subprocess.run(cmd, capture_output=True)
        if raw.returncode != 0:
            raise ValueError("ffmpeg failed on %s: %s" % (path, raw.stderr.decode(errors="replace")[:300]))
        n = len(raw.stdout) // (w * h * 3)
        return np.frombuffer(raw.stdout, np.uint8)[: n * w * h * 3].reshape(n, h, w, 3)
    out = []
    cv2 = _cv2()
    if cv2 is not None:
        cap = cv2.VideoCapture(path)
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        i = 0
        while True:
            ok, f = cap.read()
            if not ok:
                break
            t = i / fps; i += 1
            if start and t < float(start) - 1e-6:
                continue
            if end and t >= float(end):
                break
            out.append(cv2.resize(cv2.cvtColor(f, cv2.COLOR_BGR2RGB), (w, h), interpolation=cv2.INTER_AREA))
        cap.release()
    elif _av() is not None:
        av = _av()
        from PIL import Image
        with av.open(path) as c:
            for fr in c.decode(video=0):
                t = float(fr.time or 0)
                if start and t < float(start) - 1e-6:
                    continue
                if end and t >= float(end):
                    break
                out.append(np.asarray(fr.to_image().convert("RGB").resize((w, h), Image.BILINEAR)))
    else:
        raise ValueError("no video decoder: pip install imageio-ffmpeg (or opencv-python-headless)")
    return np.stack(out) if out else np.zeros((0, h, w, 3), np.uint8)


def can_interpolate():
    return ffmpeg_exe()[0] is not None


def encode(frames_or_pattern, out_path, fps=30, crf=23):
    """Write an mp4 from a list of RGB uint8 arrays / PIL images, or from an image pattern like dir/f_%04d.png."""
    ff, _ = ffmpeg_exe()
    if isinstance(frames_or_pattern, str):
        if ff:
            r = subprocess.run([ff, "-y", "-v", "error", "-framerate", str(fps), "-i", frames_or_pattern, "-c:v", "libx264",
                                "-pix_fmt", "yuv420p", "-crf", str(crf), "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2", out_path],
                               capture_output=True, text=True)
            if r.returncode == 0:
                return out_path
        import glob
        pat = re.sub(r"%0?\d*d", "*", frames_or_pattern)
        from PIL import Image
        frames = [np.asarray(Image.open(p).convert("RGB")) for p in sorted(glob.glob(pat))]
    else:
        frames = [np.asarray(f.convert("RGB")) if hasattr(f, "convert") else np.asarray(f) for f in frames_or_pattern]
    if not frames:
        raise ValueError("encode: no frames")
    h, w = frames[0].shape[:2]
    if ff:
        p = subprocess.Popen([ff, "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "%dx%d" % (w, h), "-r", str(fps),
                              "-i", "-", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", str(crf),
                              "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2", out_path], stdin=subprocess.PIPE)
        for f in frames:
            p.stdin.write(np.ascontiguousarray(f[:, :, :3]).tobytes())
        p.stdin.close(); p.wait()
        if p.returncode == 0:
            return out_path
    cv2 = _cv2()
    if cv2 is not None:
        vw = cv2.VideoWriter(out_path, cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
        for f in frames:
            vw.write(cv2.cvtColor(np.ascontiguousarray(f[:, :, :3]), cv2.COLOR_RGB2BGR))
        vw.release()
        return out_path
    raise RuntimeError("encode: needs imageio-ffmpeg / ffmpeg or opencv")


def bench_decode(path):
    t0 = time.time(); info = probe(path)
    fr = read_frames(path, info["w"] - info["w"] % 2, info["h"] - info["h"] % 2)
    return len(fr), time.time() - t0

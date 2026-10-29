"""Procedural TEST CLIPS for the video pipeline (no real people, nothing downloaded).

Renders the Sprite Forge mannequin (a generic no-likeness figure) performing
walk / run / jump / punch and composites it onto procedurally drawn scenes the
way a real phone clip would look: sensor noise, h264 compression, a soft cast
shadow, a hand-held camera shake, a camera that PANS to follow a runner
('in frame' running with parallax background) and a green-screen take.

    python tools/make_test_clips.py OUT_DIR [--quick]

Writes walk_static.mp4, run_tracking.mp4, jump_handheld.mp4, punch_green.mp4,
orbit_turntable.mp4 (for the photogrammetry test) and clips.json (ground truth)."""
from __future__ import annotations
import os as _os, sys as _sys, shutil as _sh
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
try:
    from sforge.media import ffmpeg_exe as _ffx
    FFMPEG = _ffx()[0] or "ffmpeg"
except Exception:
    FFMPEG = "ffmpeg"
FFPROBE = _sh.which("ffprobe") or "ffprobe"

import json, math, os, subprocess, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from sforge import mesh, render, anim          # noqa: E402
from sforge.motions import find_motion          # noqa: E402
from sforge.rig import evaluate                 # noqa: E402
from sforge.spec import CharacterSpec           # noqa: E402

W, H = 640, 360
RNG = np.random.default_rng(7)


def _ffmpeg_writer(path, fps, crf=23):
    return subprocess.Popen([FFMPEG, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                             "-s", "%dx%d" % (W, H), "-r", str(fps), "-i", "-", "-c:v", "libx264", "-preset", "medium",
                             "-crf", str(crf), "-pix_fmt", "yuv420p", path], stdin=subprocess.PIPE)


class Figure:
    def __init__(self, yaw=90.0, fig_h=230, kit="home"):
        sp = CharacterSpec()
        try:
            sp.kit = kit
        except Exception:
            pass
        self.T, self.B, self.M = mesh.build_mannequin(sp, include_ball=False)
        self.cols = sp.colours()
        self.rs = render.RenderSettings(360, 360, fig_h, 340, 180, yaw=yaw, outline=False, ss=2)

    def at(self, motion, t, lift_px=0):
        pose, mix = find_motion(motion).sample(t)
        st = evaluate(pose, mix)
        return render.render_state(self.T, self.B, self.M, self.cols, st, self.rs)


# ------------------------------------------------------------ scenery
def _noise(h, w, scale, seed):
    r = np.random.default_rng(seed)
    small = r.random((max(2, h // scale), max(2, w // scale))).astype(np.float32)
    return np.asarray(Image.fromarray((small * 255).astype(np.uint8)).resize((w, h), Image.BICUBIC)).astype(np.float32) / 255


def scene_static(seed=1):
    img = np.zeros((H, W, 3), np.float32)
    y = np.linspace(0, 1, H)[:, None]
    img[:] = (np.array([0.55, 0.72, 0.92]) * (1 - y[..., None] * 0.4)).reshape(H, 1, 3)
    im = Image.fromarray((img * 255).astype(np.uint8))
    d = ImageDraw.Draw(im)
    r = np.random.default_rng(seed)
    for i in range(9):                                   # houses / blocks
        x0 = int(r.integers(-40, W)); w = int(r.integers(50, 120)); h = int(r.integers(60, 150))
        c = tuple(int(v) for v in r.integers(90, 200, 3))
        d.rectangle([x0, 250 - h, x0 + w, 250], fill=c)
        for wx in range(x0 + 8, x0 + w - 12, 22):
            for wy in range(250 - h + 10, 240, 26):
                d.rectangle([wx, wy, wx + 10, wy + 12], fill=(60, 70, 90))
    for i in range(6):                                   # trees
        x = int(r.integers(0, W)); d.rectangle([x - 4, 200, x + 4, 252], fill=(90, 60, 40))
        d.ellipse([x - 26, 150, x + 26, 214], fill=(40 + int(r.integers(0, 40)), 120, 50))
    d.rectangle([0, 250, W, H], fill=(120, 118, 110))   # pavement
    a = np.asarray(im).astype(np.float32) / 255
    a[250:] *= (0.85 + 0.3 * _noise(H - 250, W, 6, seed + 3))[..., None]
    for x in range(0, W, 48):                            # paving joints
        a[250:, x:x + 2] *= 0.8
    return np.clip(a, 0, 1)


def layer_strip(kind, width, seed):
    """Wide panorama layers for the tracking shot (far / mid / ground)."""
    r = np.random.default_rng(seed)
    im = Image.new("RGBA", (width, H), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    if kind == "far":
        arr = np.zeros((H, width, 4), np.uint8)
        y = np.linspace(0, 1, H)[:, None]
        arr[..., 0] = (140 * (1 - y * 0.3)); arr[..., 1] = (185 * (1 - y * 0.3)); arr[..., 2] = 235; arr[..., 3] = 255
        im = Image.fromarray(arr, "RGBA"); d = ImageDraw.Draw(im)
        xs = np.arange(width)
        hills = 175 + 25 * np.sin(xs / 90.0 + seed) + 12 * np.sin(xs / 37.0)
        for x in range(width):
            d.line([x, int(hills[x]), x, 260], fill=(110, 150, 120, 255))
    elif kind == "mid":
        x = 0
        while x < width:
            w = int(r.integers(40, 110)); h = int(r.integers(50, 140))
            if r.random() < 0.35:
                d.rectangle([x + w // 2 - 4, 196, x + w // 2 + 4, 256], fill=(90, 60, 40, 255))
                d.ellipse([x + w // 2 - 28, 140, x + w // 2 + 28, 206], fill=(50, int(r.integers(110, 150)), 55, 255))
            else:
                c = tuple(int(v) for v in r.integers(100, 210, 3)) + (255,)
                d.rectangle([x, 256 - h, x + w, 256], fill=c)
                for wx in range(x + 8, x + w - 12, 22):
                    for wy in range(256 - h + 10, 246, 26):
                        d.rectangle([wx, wy, wx + 10, wy + 12], fill=(60, 70, 90, 255))
            x += w + int(r.integers(10, 60))
    else:  # ground
        arr = np.zeros((H, width, 4), np.float32)
        tex = 0.8 + 0.35 * _noise(H, width, 5, seed)
        arr[256:, :, :3] = (np.array([0.5, 0.47, 0.42]) * tex[256:, :, None])
        for x in range(0, width, 40):
            arr[256:, x:x + 3, :3] *= 0.7
        arr[256:, :, 3] = 1
        im = Image.fromarray((np.clip(arr, 0, 1) * 255).astype(np.uint8), "RGBA")
    return im


def shadow_under(frame, x, y, w, strength=0.45):
    m = Image.new("L", (W, H), 0)
    ImageDraw.Draw(m).ellipse([x - w, y - 7, x + w, y + 7], fill=255)
    m = np.asarray(m.filter(ImageFilter.GaussianBlur(5))).astype(np.float32) / 255
    frame *= (1 - strength * m)[..., None]


def comp(bg, fig_rgba, x, y):
    """paste a 360x360 figure cell so its anchor (180, 340) lands at (x, y)."""
    out = Image.fromarray((np.clip(bg, 0, 1) * 255).astype(np.uint8)).convert("RGBA")
    out.alpha_composite(fig_rgba, (int(round(x - 180)), int(round(y - 340)))) if 0 else out.paste(fig_rgba, (int(round(x - 180)), int(round(y - 340))), fig_rgba)
    return np.asarray(out.convert("RGB")).astype(np.float32) / 255


def finish(frame, gain=1.0):
    f = frame * gain + RNG.normal(0, 0.012, frame.shape).astype(np.float32)
    return (np.clip(f, 0, 1) * 255).astype(np.uint8)


# ------------------------------------------------------------ clips
def clip_walk(path, quick=False):
    fps, period, n = 30, 1.1, (75 if quick else 110)
    fig = Figure(); bg = scene_static(1); wr = _ffmpeg_writer(path, fps)
    for i in range(n):
        t = i / fps
        x = 60 + t * 140                                 # walks left -> right
        cell = fig.at("walk", (t / period) % 1.0)
        f = bg.copy(); shadow_under(f, x + 6, 338, 40)
        wr.stdin.write(finish(comp(f, cell, x, 338)).tobytes())
    wr.stdin.close(); wr.wait()
    return dict(file=os.path.basename(path), move="walk", fps=fps, period_frames=period * fps, camera="static", note="walks across, cast shadow")


def clip_run_tracking(path, quick=False):
    fps, period, n = 30, 0.66, (60 if quick else 90)
    fig = Figure(fig_h=220)
    speeds = dict(far=1.0, mid=4.5, ground=11.0)           # px/frame: parallax
    layers = {k: layer_strip(k, W + int(v * n) + 40, s) for (k, v), s in zip(speeds.items(), (2, 3, 4))}
    wr = _ffmpeg_writer(path, fps)
    for i in range(n):
        t = i / fps
        canvas = Image.new("RGBA", (W, H))
        for k in ("far", "mid", "ground"):
            ox = int(round(speeds[k] * i))
            canvas.alpha_composite(layers[k].crop((ox, 0, ox + W, H)))
        f = np.asarray(canvas.convert("RGB")).astype(np.float32) / 255
        x = W / 2 + 18 * math.sin(t * 1.3) + 6 * math.sin(t * 4.1)  # operator does not track perfectly
        shadow_under(f, x, 336, 36, 0.35)
        # motion blur: 3 sub-frames
        acc = np.zeros_like(f)
        for s in range(3):
            acc += comp(f, fig.at("run", ((t + s / (3 * fps)) / period) % 1.0), x, 336)
        wr.stdin.write(finish(acc / 3, 1.0 + 0.03 * math.sin(i * 0.7)).tobytes())
    wr.stdin.close(); wr.wait()
    return dict(file=os.path.basename(path), move="run", fps=fps, period_frames=period * fps, camera="pan-tracking",
                note="camera follows the runner; 3 parallax layers scroll at 1 / 4.5 / 11 px per frame; motion blur")


def clip_jump(path, quick=False):
    fps = 30
    fig = Figure(yaw=75); bg = scene_static(5); wr = _ffmpeg_writer(path, fps)
    empty, hold, dur = 15, 12, 34          # 0.5 s of empty scene first (clean plate), then the jump
    n = empty + hold + dur + hold
    shake = np.cumsum(RNG.normal(0, 0.8, (n, 2)), axis=0); shake -= shake.mean(axis=0)
    for i in range(n):
        f = bg.copy()
        if i < empty:
            fr = f
        else:
            k = i - empty
            tt = min(1.0, max(0.0, (k - hold) / (dur - 1)))
            cell = fig.at("jump", tt) if hold <= k < hold + dur else fig.at("idle" if k < hold else "jump", 0.0 if k < hold else 1.0)
            shadow_under(f, 320, 338, 38)
            fr = comp(f, cell, 320, 338)
        sx, sy = shake[i]
        fr = np.asarray(Image.fromarray((fr * 255).astype(np.uint8)).transform((W, H), Image.AFFINE, (1, 0, sx, 0, 1, sy), Image.BILINEAR)).astype(np.float32) / 255
        wr.stdin.write(finish(fr).tobytes())
    wr.stdin.close(); wr.wait()
    return dict(file=os.path.basename(path), move="jump", fps=fps, camera="hand-held shake (+-3 px)", plate_frames=empty, action_frames=[empty + hold, empty + hold + dur])


def clip_punch_green(path, quick=False):
    fps = 24
    fig = Figure(yaw=80, kit="red"); wr = _ffmpeg_writer(path, fps)
    g = np.zeros((H, W, 3), np.float32); g[:] = (0.05, 0.69, 0.27)
    yy, xx = np.mgrid[0:H, 0:W]
    g *= (1 - 0.25 * (((xx - W / 2) / W) ** 2 + ((yy - H / 2) / H) ** 2))[..., None]   # uneven lighting
    hold, dur = 8, 12
    n = hold + dur + hold
    for i in range(n):
        tt = min(1.0, max(0.0, (i - hold) / (dur - 1)))
        cell = fig.at("punch", tt) if hold <= i < hold + dur else fig.at("punch", 0.0 if i < hold else 1.0)
        fr = comp(g, cell, 300, 338)
        wr.stdin.write(finish(fr).tobytes())
    wr.stdin.close(); wr.wait()
    return dict(file=os.path.basename(path), move="punch", fps=fps, camera="static, green screen", action_frames=[hold, hold + dur],
                note="only 12 action frames at 24 fps -> needs slow-motion interpolation for 16+ sprite frames")


def clip_orbit(path, quick=False):
    """turntable orbit of the mannequin in T-pose-ish idle for the photogrammetry test."""
    fps, n = 12, (36 if quick else 72)
    wr = _ffmpeg_writer(path, fps)
    sp = CharacterSpec(); T, B, M = mesh.build_mannequin(sp, include_ball=False); cols = sp.colours()
    st = evaluate(find_motion("idle").sample(0.0)[0])
    floor = np.zeros((H, W, 3), np.float32); floor[:] = (0.78, 0.76, 0.72)
    tex = 0.75 + 0.5 * _noise(H, W, 3, 11)
    floor *= tex[..., None]
    for i in range(n):
        rs = render.RenderSettings(360, 360, 300, 345, 180, yaw=i * 360.0 / n, pitch=12, outline=False, ss=2)
        cell = render.render_state(T, B, M, cols, st, rs)
        wr.stdin.write(finish(comp(floor, cell, 320, 350)).tobytes())
    wr.stdin.close(); wr.wait()
    return dict(file=os.path.basename(path), move="orbit", fps=fps, camera="turntable 360 deg, %d views" % n)


def main(argv=None):
    a = sys.argv[1:] if argv is None else argv
    out = a[0] if a else "test_clips"; quick = "--quick" in a
    os.makedirs(out, exist_ok=True)
    meta = []
    for fn, name in ((clip_walk, "walk_static.mp4"), (clip_run_tracking, "run_tracking.mp4"), (clip_jump, "jump_handheld.mp4"),
                     (clip_punch_green, "punch_green.mp4"), (clip_orbit, "orbit_turntable.mp4")):
        meta.append(fn(os.path.join(out, name), quick)); print("wrote", name, flush=True)
    json.dump(meta, open(os.path.join(out, "clips.json"), "w"), indent=1)


if __name__ == "__main__":
    main()

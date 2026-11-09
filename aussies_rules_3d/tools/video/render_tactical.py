#!/usr/bin/env python3
"""
render_tactical.py — render docs/gameplay.mp4 from sim telemetry.

A "coach's tactical cam" highlight reel of Aussie Rules 3D:
Melbourne (navy/red, you) vs Collingwood (black/white), first quarter.

Every frame is the real MatchSim (tools/video/match_frames.json, produced by
tools/video/export_match.mjs from the current simulation), drawn top-down
with a smoothed ball-tracking camera so the contest stays readable.

The Blender/Cycles path (tools/blender/gen_match_video.py) is the "cinematic"
option but needs a GPU box (~2 min/frame on 2 CPU cores). This renderer is the
CPU-friendly counterpart and can be regenerated anywhere:

    python3 -m venv tools/video/venv
    tools/video/venv/bin/pip install pillow numpy imageio-ffmpeg
    tools/video/venv/bin/python tools/video/render_tactical.py
"""
import json
import math
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
TELEMETRY = os.path.join(ROOT, "tools", "video", "match_frames.json")
OUT_MP4 = os.path.join(ROOT, "docs", "gameplay.mp4")

W, H = 1280, 720
FPS = 24

# Field geometry mirrors src/rules/types.ts FIELD
FIELD_A, FIELD_B, FIELD_N = 85.5, 73.0, 2.4
GOAL_LINE_X = 69.0
GOAL_POST_HALF = 3.2
BEHIND_POST_HALF = 9.6
GOAL_SQ_DEPTH = 9.0
CENTRE_SQ_HALF = 25.0
ARC_RADIUS = 50.0

# World sprite: high-res pre-render of the ground, cropped per frame.
S = 14.0            # px per metre on the sprite
MARGIN = 90         # px of margin around the oval (dark surroundings)
SPR_W = int(2 * FIELD_A * S) + 2 * MARGIN
SPR_H = int(2 * FIELD_B * S) + 2 * MARGIN

# Camera: 16:9 window onto the world, smoothed toward the ball
VIEW_W_M, VIEW_H_M = 88.0, 49.5
VIEW_W, VIEW_H = int(VIEW_W_M * S), int(VIEW_H_M * S)  # 1232 x 693
CAM_LERP = 2.6      # exponential smoothing, higher = snappier

MEL = {"fill": (37, 82, 158), "ring": (240, 60, 74), "glow": (240, 60, 74), "label": "MEL"}
COL = {"fill": (16, 16, 16), "ring": (245, 245, 245), "glow": (245, 245, 245), "label": "COLL"}
BG = (10, 18, 32)
PITCH_DARK = (34, 66, 36)

FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_REG = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def font(size, bold=True):
    return ImageFont.truetype(FONT_BOLD if bold else FONT_REG, size)


F_TITLE = font(64)
F_SUB = font(22, bold=False)
F_BUG = font(30)
F_BUG_SM = font(15, bold=False)
F_BANNER = font(58)
F_BANNER_SM = font(20, bold=False)
F_NUM = font(16)
F_TAG = font(13, bold=False)
F_CARD_BODY = font(17, bold=False)


def to_px(x, z):
    """World (metres) → sprite pixels."""
    return (MARGIN + (x + FIELD_A) * S, MARGIN + (z + FIELD_B) * S)


def super_point(theta, a=FIELD_A, b=FIELD_B, n=FIELD_N):
    c, s_ = math.cos(theta), math.sin(theta)
    return (math.copysign(abs(c) ** (2.0 / n), c) * a,
            math.copysign(abs(s_) ** (2.0 / n), s_) * b)


# --------------------------------------------------------------------------- #
#  Static layers
# --------------------------------------------------------------------------- #

def build_vignette():
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    cx, cy = W / 2, H / 2
    d = np.sqrt(((xx - cx) / (W * 0.72)) ** 2 + ((yy - cy) / (H * 0.72)) ** 2)
    alpha = np.clip((d - 0.55) / 0.75, 0, 1) ** 1.6 * 200
    layer = np.zeros((H, W, 4), dtype=np.uint8)
    layer[..., 3] = alpha.astype(np.uint8)
    return Image.fromarray(layer, "RGBA")


def build_pitch():
    """The painted ground + dark margins, pre-rendered once (sprite size)."""
    tex = Image.new("RGBA", (SPR_W, SPR_H), PITCH_DARK + (255,))
    d = ImageDraw.Draw(tex)

    poly = [to_px(*super_point(t / 540 * 2 * math.pi)) for t in range(540)]

    # mow stripes, clipped to the oval
    mask = Image.new("L", (SPR_W, SPR_H), 0)
    ImageDraw.Draw(mask).polygon(poly, fill=255)
    stripes = Image.new("RGBA", (SPR_W, SPR_H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(stripes)
    stripe_w = int(FIELD_A * 2 * S / 22)
    x0 = to_px(-FIELD_A, 0)[0]
    for i in range(23):
        shade = (68, 133, 66, 255) if i % 2 else (58, 121, 58, 255)
        sd.rectangle([x0 + i * stripe_w, 0, x0 + (i + 1) * stripe_w, SPR_H], fill=shade)
    tex.paste(stripes, (0, 0), mask)

    white = (248, 248, 248, 255)
    lw = 5

    # boundary
    d.line(poly + [poly[0]], fill=white, width=lw, joint="curve")

    # goal lines at x=±69 (straight across the oval)
    gz = FIELD_B * (1 - (GOAL_LINE_X / FIELD_A) ** FIELD_N) ** (1 / FIELD_N)
    for sx in (-1, 1):
        d.line([to_px(sx * GOAL_LINE_X, -gz), to_px(sx * GOAL_LINE_X, gz)], fill=white, width=lw)

    # goal squares
    for sx in (-1, 1):
        xa, xb = sx * GOAL_LINE_X - (GOAL_SQ_DEPTH if sx > 0 else -GOAL_SQ_DEPTH), sx * GOAL_LINE_X
        lo, hi = min(xa, xb), max(xa, xb)
        p0 = to_px(lo, -GOAL_POST_HALF)
        p1 = to_px(hi, GOAL_POST_HALF)
        d.rectangle([p0[0], p0[1], p1[0], p1[1]], outline=white, width=lw)

    # 50 m arcs — only the half bulging toward centre (AFL arc, not a circle)
    for sx in (-1, 1):
        cxp, cyp = to_px(sx * GOAL_LINE_X, 0)
        r = ARC_RADIUS * S
        bbox = [cxp - r, cyp - r, cxp + r, cyp + r]
        # PIL arc angles: 0° = 3 o'clock, increasing clockwise
        if sx > 0:
            d.arc(bbox, start=90, end=270, fill=white, width=lw)   # left half
        else:
            d.arc(bbox, start=270, end=90, fill=white, width=lw)   # right half

    # centre square (50 m) + centre circle (5 m)
    p0 = to_px(-CENTRE_SQ_HALF, -CENTRE_SQ_HALF)
    p1 = to_px(CENTRE_SQ_HALF, CENTRE_SQ_HALF)
    d.rectangle([p0[0], p0[1], p1[0], p1[1]], outline=white, width=lw)
    cxp, cyp = to_px(0, 0)
    r = 5.0 * S
    d.ellipse([cxp - r, cyp - r, cxp + r, cyp + r], outline=white, width=lw)

    # goal posts (goal + behind), white ticks
    for sx in (-1, 1):
        for half, is_goal in ((GOAL_POST_HALF, True), (BEHIND_POST_HALF, False)):
            for sgn in (-1, 1):
                px, py = to_px(sx * GOAL_LINE_X, sgn * half)
                tick = 9 if is_goal else 5
                d.ellipse([px - tick, py - tick, px + tick, py + tick],
                          fill=white if is_goal else (210, 210, 210, 255))

    return tex


# --------------------------------------------------------------------------- #
#  Camera
# --------------------------------------------------------------------------- #

class Camera:
    def __init__(self):
        self.x = 0.0
        self.z = 0.0
        self.ready = False

    def update(self, tx, tz, dt):
        if not self.ready:
            self.x, self.z = tx, tz
            self.ready = True
            return
        k = 1.0 - math.exp(-CAM_LERP * dt)
        self.x += (tx - self.x) * k
        self.z += (tz - self.z) * k

    def crop_box(self):
        px, py = to_px(self.x, self.z)
        x0 = int(px - VIEW_W / 2)
        y0 = int(py - VIEW_H / 2)
        x0 = max(0, min(SPR_W - VIEW_W, x0))
        y0 = max(0, min(SPR_H - VIEW_H, y0))
        return x0, y0


# --------------------------------------------------------------------------- #
#  HUD (screen space)
# --------------------------------------------------------------------------- #

def draw_bug(d, frame):
    d.rectangle([0, 0, W, 54], fill=(8, 13, 24))
    d.rectangle([0, 54, W, 56], fill=(210, 30, 46))

    mel_pts, col_pts = frame["scores"]
    q = frame["quarter"]
    clock = max(0, frame["clock"])
    mm, ss = divmod(int(clock), 60)

    # left block — Melbourne
    d.rectangle([0, 0, 300, 54], fill=MEL["fill"])
    d.text((26, 10), "MELBOURNE", font=F_BUG_SM, fill=(235, 240, 250))
    d.text((26, 26), str(mel_pts), font=F_BUG, fill=(255, 255, 255))
    d.text((110, 26), "PTS", font=F_BUG_SM, fill=(180, 195, 220))

    # right block — Collingwood
    d.rectangle([W - 300, 0, W, 54], fill=COL["fill"])
    tw = d.textlength("COLLINGWOOD", font=F_BUG_SM)
    d.text((W - 26 - tw, 10), "COLLINGWOOD", font=F_BUG_SM, fill=(245, 245, 245))
    tw = d.textlength(str(col_pts), font=F_BUG)
    d.text((W - 26 - tw, 26), str(col_pts), font=F_BUG, fill=(255, 255, 255))
    tw = d.textlength("PTS", font=F_BUG_SM)
    d.text((W - 26 - tw - 46, 26), "PTS", font=F_BUG_SM, fill=(170, 170, 170))

    # centre — quarter + clock
    mid = f"QUARTER {q}   ·   {mm}:{ss:02d}"
    tw = d.textlength(mid, font=F_BUG)
    d.text(((W - tw) / 2, 8), mid, font=F_BUG, fill=(240, 244, 252))
    tag = "AUSSIE RULES 3D  ·  LIVE TACTICAL CAM"
    tw = d.textlength(tag, font=F_BUG_SM)
    d.text(((W - tw) / 2, 36), tag, font=F_BUG_SM, fill=(150, 162, 185))


def draw_tags(d):
    d.text((18, H - 26), "MELBOURNE v COLLINGWOOD  ·  SEED 15  ·  QUARTER 1", font=F_TAG, fill=(128, 142, 166))
    tw = d.textlength("GITHUB.COM/PRONANE/C_GAMES", font=F_TAG)
    d.text((W - 18 - tw, H - 26), "GITHUB.COM/PRONANE/C_GAMES", font=F_TAG, fill=(128, 142, 166))


def draw_banner(img, text, sub, colour, t_frac):
    W_LOCAL, bar_h = W, 96
    a = min(1.0, min(t_frac / 0.12, (1 - t_frac) / 0.15))
    if a <= 0:
        return
    y = int(H - 205 + (1 - min(1.0, t_frac / 0.12)) * 26)
    overlay = Image.new("RGBA", (W_LOCAL, bar_h), (8, 13, 24, int(228 * a)))
    img.paste(overlay, (0, y), overlay)
    d = ImageDraw.Draw(img, "RGBA")
    d.rectangle([0, y, 9, y + bar_h], fill=colour + (int(255 * a),))
    d.text((40, y + 6), text, font=F_BANNER, fill=(255, 255, 255, int(255 * a)))
    d.text((40, y + 66), sub, font=F_BANNER_SM, fill=(190, 200, 218, int(255 * a)))


# --------------------------------------------------------------------------- #
#  Per-frame world drawing (sprite space)
# --------------------------------------------------------------------------- #

def draw_world(world, frames, idx, trail, cam_box):
    d = ImageDraw.Draw(world, "RGBA")
    f = frames[idx]
    ox, oy = cam_box

    # ball trail
    if len(trail) > 1:
        for i in range(1, len(trail)):
            a = int(150 * (i / len(trail)))
            d.line([trail[i - 1], trail[i]], fill=(255, 224, 130, a), width=5)

    squad = [p for p in f["players"] if not (p[1] == 0 and p[2] == 0)]
    carrier_id = next((p[0] for p in squad if p[6] == 4), None)

    ctrl = f["controlledId"]
    pulse = 1.0 + 0.22 * math.sin(2 * math.pi * 2.2 * f["t"])

    for p in squad:
        pid, x, z, y, facing, speed, anim = p
        team = MEL if pid < 100 else COL
        px, py = to_px(x, z)
        r = 16
        # team glow under the dot
        d.ellipse([px - r - 6, py - r - 6, px + r + 6, py + r + 6],
                  fill=team["glow"] + (70,))
        # shadow then body
        d.ellipse([px - r, py - r + 4, px + r, py + r + 4], fill=(0, 0, 0, 90))
        d.ellipse([px - r, py - r, px + r, py + r], fill=team["fill"] + (255,),
                  outline=team["ring"] + (255,), width=4)
        num = str(pid % 100 + 1)
        tw = d.textlength(num, font=F_NUM)
        d.text((px - tw / 2, py - 10), num, font=F_NUM, fill=(255, 255, 255, 255))

    # controlled player: pulsing yellow ring (in-game marker language)
    if ctrl >= 0:
        for p in squad:
            if p[0] == ctrl:
                px, py = to_px(p[1], p[2])
                r = int(24 * pulse)
                d.ellipse([px - r, py - r, px + r, py + r],
                          outline=(255, 210, 63, 255), width=5)

    # carrier: white rim
    if carrier_id is not None:
        for p in squad:
            if p[0] == carrier_id:
                px, py = to_px(p[1], p[2])
                d.ellipse([px - 22, py - 22, px + 22, py + 22],
                          outline=(255, 255, 255, 235), width=4)

    # ball: shadow + lifted dot (lift reads as "in the air")
    b = f["ball"]
    bx, by = to_px(b[0], b[2])
    height = b[1]
    shadow_r = max(4, 11 - height * 1.1)
    d.ellipse([bx - shadow_r, by + 8 - shadow_r / 2, bx + shadow_r, by + 8 + shadow_r / 2],
              fill=(0, 0, 0, 120))
    lift = min(44, height * 3.2)
    br = 8
    d.ellipse([bx - br, by - lift - br, bx + br, by - lift + br],
              fill=(122, 74, 33), outline=(255, 255, 255), width=3)


def event_banners(frames):
    GREEN = (46, 204, 113)
    RED = (231, 76, 60)
    BLUE = (91, 155, 213)
    AMBER = (241, 196, 15)
    banners = []
    for i, f in enumerate(frames):
        for e in f["events"]:
            t = e["type"]
            if t == "goal":
                team = "MELBOURNE" if (e.get("team") == 0) else "COLLINGWOOD"
                banners.append((i, f"GOAL — {team}", "Six points on the board", GREEN, int(FPS * 2.6)))
            elif t == "behind":
                banners.append((i, "BEHIND", "One point", AMBER, int(FPS * 2.0)))
            elif t == "mark":
                banners.append((i, "MARK", "Clean grab", BLUE, int(FPS * 1.5)))
            elif t == "freeKick":
                banners.append((i, "FREE KICK", "Umpire's call", RED, int(FPS * 1.3)))
    return banners


def intro_card(d):
    d.rectangle([0, 0, W, H], fill=(10, 18, 32))
    d.rectangle([0, H // 2 - 130, W, H // 2 - 128], fill=(210, 30, 46))
    title = "AUSSIE RULES 3D"
    tw = d.textlength(title, font=F_TITLE)
    d.text(((W - tw) / 2, H // 2 - 96), title, font=F_TITLE, fill=(245, 248, 252))
    sub = "FIRST-QUARTER HIGHLIGHTS  ·  MELBOURNE v COLLINGWOOD"
    tw = d.textlength(sub, font=F_SUB)
    d.text(((W - tw) / 2, H // 2 - 14), sub, font=F_SUB, fill=(170, 182, 205))
    for i, line in enumerate([
        "Every frame is the live MatchSim — 22 players, AFL 2026 laws,",
        "captured headlessly and replayed from telemetry.",
        "",
        "MELBOURNE (you)  —  navy with the red trim",
        "COLLINGWOOD (CPU)  —  black with white trim",
    ]):
        tw = d.textlength(line, font=F_CARD_BODY)
        d.text(((W - tw) / 2, H // 2 + 26 + i * 26), line, font=F_CARD_BODY, fill=(140, 155, 180))
    tag = "GITHUB.COM/PRONANE/C_GAMES"
    tw = d.textlength(tag, font=F_TAG)
    d.text(((W - tw) / 2, H - 48), tag, font=F_TAG, fill=(110, 124, 148))


def outro_card(d):
    d.rectangle([0, 0, W, H], fill=(10, 18, 32))
    d.rectangle([0, H // 2 - 110, W, H // 2 - 108], fill=(210, 30, 46))
    title = "THAT'S THE FIRST QUARTER"
    tw = d.textlength(title, font=F_SUB)
    d.text(((W - tw) / 2, H // 2 - 84), title, font=F_SUB, fill=(170, 182, 205))
    title2 = "PLAY THE WHOLE GAME"
    tw = d.textlength(title2, font=F_TITLE)
    d.text(((W - tw) / 2, H // 2 - 36), title2, font=F_TITLE, fill=(245, 248, 252))
    for i, line in enumerate([
        "npm install && npm run dev",
        "npm run desktop   (Electron shell)   ·   installable as a PWA",
        "",
        "Camera: C cycles broadcast / wing / chase / aerial / tactical",
        "Markers: V toggles rings   ·   Kick: hold SPACE, release to kick",
    ]):
        tw = d.textlength(line, font=F_CARD_BODY)
        d.text(((W - tw) / 2, H // 2 + 46 + i * 26), line, font=F_CARD_BODY, fill=(140, 155, 180))
    tag = "MIT  ·  GITHUB.COM/PRONANE/C_GAMES"
    tw = d.textlength(tag, font=F_TAG)
    d.text(((W - tw) / 2, H - 48), tag, font=F_TAG, fill=(110, 124, 148))


# --------------------------------------------------------------------------- #
#  Main render
# --------------------------------------------------------------------------- #

def main():
    with open(TELEMETRY) as fh:
        cap = json.load(fh)
    frames = cap["frames"]
    goal_frames = cap.get("goalFrames", [])
    print(f"[tactical] {len(frames)} telemetry frames, goals at {goal_frames}")

    windows = []
    for gf in goal_frames:
        a = max(0, gf - 8 * FPS)
        b = min(len(frames), gf + 4 * FPS + 1)
        windows.append((a, b))

    banners = event_banners(frames)

    intro_frames, outro_frames = 48, 48
    live_indices = []
    for w in windows:
        live_indices.extend(range(w[0], w[1]))
    total = intro_frames + len(live_indices) + outro_frames
    print(f"[tactical] timeline: {total} frames ({total / FPS:.1f}s)")

    # banner lookup by source frame index
    banner_map = {}
    for (fi, text, sub, colour, length) in banners:
        for k in range(length):
            banner_map.setdefault(fi + k, (k / length, text, sub, colour))

    pitch = build_pitch()
    vignette = build_vignette()
    camera = Camera()
    img = Image.new("RGB", (W, H), BG)

    import imageio_ffmpeg
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    import subprocess
    cmd = [ffmpeg, "-y",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
           "-i", "-",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
           "-pix_fmt", "yuv420p", "-movflags", "+faststart",
           OUT_MP4]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

    trail = []
    prev_idx = None
    frame_dt = 1.0 / FPS

    def emit():
        proc.stdin.write(img.tobytes())

    live_ptr = 0
    for i in range(total):
        if i < intro_frames:
            ImageDraw.Draw(img).rectangle([0, 0, W, H], fill=BG)
            intro_card(ImageDraw.Draw(img))
            emit()
            continue
        if i >= intro_frames + len(live_indices):
            ImageDraw.Draw(img).rectangle([0, 0, W, H], fill=BG)
            outro_card(ImageDraw.Draw(img))
            emit()
            continue

        idx = live_indices[live_ptr]
        live_ptr += 1
        f = frames[idx]
        if prev_idx != idx - 1:
            trail = []
            camera = Camera()  # re-aim instantly on scene cuts
        camera.update(f["ball"][0], f["ball"][2], frame_dt)
        box = camera.crop_box()
        px, py = to_px(f["ball"][0], f["ball"][2])
        trail.append((px, py))
        if len(trail) > 18:
            trail.pop(0)
        prev_idx = idx

        world = pitch.copy()
        draw_world(world, frames, idx, trail, box)
        crop = world.crop((box[0], box[1], box[0] + VIEW_W, box[1] + VIEW_H))
        crop = crop.resize((W, H), Image.LANCZOS)
        img.paste(crop.convert("RGB"), (0, 0))

        img.paste(vignette, (0, 0), vignette)
        d = ImageDraw.Draw(img, "RGBA")
        draw_bug(d, f)
        draw_tags(d)
        if idx in banner_map:
            t_frac, text, sub, colour = banner_map[idx]
            draw_banner(img, text, sub, colour, t_frac)
        emit()

    proc.stdin.close()
    err = proc.stderr.read().decode()
    rc = proc.wait()
    if rc != 0:
        print(err)
        sys.exit(f"ffmpeg exited {rc}")
    size = os.path.getsize(OUT_MP4)
    print(f"[tactical] wrote {OUT_MP4} ({size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()

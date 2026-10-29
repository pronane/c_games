"""Sprite Forge Studio v9 - animation blending (transition moves between two moves).

BuildConfig.blend / --blend "idle>walk:3,walk>idle:3,punch>fight_idle:4"  adds moves blend_<a>_<b> with N frames.
Mannequin / spec builds: a real pose blend (every joint angle eased from the last pose of A into the first pose
of B, so the transition is a proper in-between pose).  Photo / library / frame builds: an alpha cross-fade of
A's last frame into B's first frame (flagged 'crossfade' in the report - it is not a new pose)."""
from __future__ import annotations
import re

from PIL import Image

from .mathutil import smooth


def parse(spec):
    out = []
    for part in re.split(r"[,;]", spec or ""):
        part = part.strip()
        if not part:
            continue
        m = re.fullmatch(r"([\w\-]+)\s*>\s*([\w\-]+)(?::(\d+))?", part)
        if not m:
            raise ValueError("bad blend '%s' (use from>to:frames, e.g. idle>walk:3)" % part)
        out.append((m.group(1), m.group(2), max(1, int(m.group(3) or 3))))
    return out


def blend_motion(motion_str):
    """'blend:a>b' -> Motion easing from a's last pose to b's first pose"""
    from .motions import Motion, find_motion, _lerp_pose
    a, b = motion_str[6:].split(">")
    ma, mb = find_motion(a), find_motion(b)
    if ma is None or mb is None:
        return None
    pa = ma.sample(0.0 if ma.loop else 1.0)[0]
    pb = mb.sample(0.0)[0]
    return Motion("blend_%s_%s" % (a, b), func=lambda t: _lerp_pose(pa, pb, smooth(0.12 + 0.76 * min(1.0, max(0.0, t)))), loop=False,
                  desc="transition %s -> %s" % (a, b), category="Blend")


def add_moves(cfg, report=None):
    """append MoveSpecs for the blends (mannequin: posed motion; other modes: filled later by crossfade)"""
    from .moves import MoveSpec
    have = {m.name: m for m in cfg.moves}
    added = []
    for a, b, n in parse(cfg.blend):
        if a not in have or b not in have:
            if report:
                report.warning("blend %s>%s: both moves must be in the build" % (a, b))
            continue
        name = "blend_%s_%s" % (a, b)
        if name in have:
            continue
        # n in-between frames + the two end poses are A / B themselves -> sample n+2 and drop the ends later? keep simple:
        ma, mb = have[a], have[b]
        motion = "blend:%s>%s" % (ma.motion or a, mb.motion or b)
        ms = MoveSpec(name=name, label="%s > %s" % (ma.label or a, mb.label or b), category="Blend", frames=n,
                      fps=max(ma.fps, mb.fps), loop=False, motion=motion, desc="transition")
        cfg.moves.append(ms); have[name] = ms; added.append(name)
    return added


def crossfade(fa, fb, n):
    """n in-between frames from frame fa to frame fb (alpha cross-fade)"""
    out = []
    for i in range(n):
        t = (i + 1) / (n + 1.0)
        out.append(Image.blend(fa.convert("RGBA"), fb.convert("RGBA"), smooth(t)))
    return out


def fill_crossfades(cfg, frames, report):
    """photo / library / frame builds: blend moves the renderer could not pose -> cross-fades"""
    for a, b, n in parse(cfg.blend):
        name = "blend_%s_%s" % (a, b)
        if a not in frames or b not in frames:
            continue
        if cfg.mode in ("spec", "mannequin"):
            continue                      # posed by the 3D renderer
        fa, fb = frames[a][0][-1], frames[b][0][0]
        frames[name] = (crossfade(fa, fb, n), "crossfade", "alpha cross-fade %s -> %s (not a new pose)" % (a, b))

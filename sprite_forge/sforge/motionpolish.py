"""v9.1 MOTION POLISH (opt-in: --motion-style polish): smoother in-betweens for the photo puppet.

The classic sampler (puppet._sample) interpolates linearly between key poses, so joints change speed abruptly at
every key.  This keeps the SAME key poses and only changes the frames between them:

  1. monotone cubic (PCHIP) interpolation instead of straight lines: C1 continuous, never overshoots a key, a
     repeated key (a hold) stays still.
  2. distal lag: forearms and shins (fn, ff, sn, sf) trail their upper segment by a fraction of a key interval,
     converging on the last key so the move still ends exactly on its final pose.
  3. weight shift: small sway on idle / taunt / victory and a landing squash on jumps.

It applies to moves whose frame count differs from their number of key poses (in the stock fighter14 build that is
kick, throw, hit, taunt, special1 and special2; the others have one key pose per frame and are left exactly as they
are).  Key poses are still reproduced, except that forearms / shins trail slightly (see lag).

Measured on the mannequin test at 16 frames (velocity change at the key poses, deg/frame, lower = smoother):
kick 15.4 -> 6.2, throw 8.7 -> 4.2, punch 1.4 -> 0.6.  Cost: peak joint speed rises (kick ~105 -> ~152 deg/frame)
because the same keys are reached with an eased curve; check fast moves by eye before making it the default.
"""
from __future__ import annotations
import math
import numpy as np
from scipy.interpolate import PchipInterpolator

NEUTRAL = {"lean": 0.0, "lift": 0.0, "dx": 0.0, "sx": 1.0, "sy": 1.0}
DISTAL = ("fn", "ff", "sn", "sf")
SEGS = ("un", "fn", "uf", "ff", "tn", "sn", "tf", "sf")
LAG = {"punch": 0.30, "kick": 0.32, "pyramid_blast": 0.22, "special1": 0.22, "special_1": 0.22,
       "bum_fireball": 0.30, "special2": 0.30, "special_2": 0.30, "throw": 0.25, "jump_attack": 0.25,
       "jumpattack": 0.25, "walk": 0.18, "taunt": 0.22, "victory": 0.15, "jump": 0.15, "hit": 0.0,
       "block": 0.0, "idle": 0.10, "crouch": 0.0}


def _numeric_channels(keys):
    return sorted({n for k in keys for n, v in k.items() if isinstance(v, (int, float)) and not isinstance(v, bool)})


def polish_sample(keys, n, rest, name="", cyclic=False, lag=None):
    K = len(keys)
    if K == 1:
        return [dict(keys[0]) for _ in range(n)]
    lag = LAG.get(name, 0.15) if lag is None else lag
    chans = _numeric_channels(keys)
    xs = np.arange(K, dtype=float)
    fs = np.linspace(0, K - 1, n) if n > 1 else np.array([0.0])
    curves = {}
    for c in chans:
        base = rest.get(c, NEUTRAL.get(c, 0.0))
        ys = np.array([float(k.get(c, base)) for k in keys])
        curves[c] = (lambda f, v=ys[0]: np.full_like(np.asarray(f, float), v)) if np.ptp(ys) < 1e-9 \
            else PchipInterpolator(xs, ys, extrapolate=False)
    out = []
    for f in fs:
        i0 = min(int(math.floor(f)), K - 2)
        t = f - i0
        pose = {}
        for kname in set(keys[i0]) | set(keys[i0 + 1]):          # glow colours, orb, tint, arm_order ...
            va, vb = keys[i0].get(kname), keys[i0 + 1].get(kname)
            if isinstance(va, (int, float)) or isinstance(vb, (int, float)):
                continue
            pose[kname] = vb if (t >= 0.5 and vb is not None) or va is None else va
        for c in chans:
            ff = f
            if c in DISTAL and lag > 0:
                fade = 1.0 if cyclic else min(1.0, max(0.0, K - 1 - f))
                ff = f - lag * fade
                if cyclic and K > 2:
                    ff = ff % (K - 1)
                ff = min(max(ff, 0.0), K - 1.0)
            v = float(curves[c](ff))
            pose[c] = v if np.isfinite(v) else float(curves[c](min(max(ff, 0.0), K - 1.0)))
        out.append(pose)
    return out


def weight_shift(poses, name, amount=0.006):
    n = len(poses)
    if name in ("idle", "taunt", "victory") and n > 2:
        for i, p in enumerate(poses):
            p["dx"] = p.get("dx", 0.0) + amount * math.sin(2 * math.pi * i / n)
    if name in ("jump", "jump_attack", "jumpattack") and n > 3:
        for j in range(n - 2, n):
            sq = j == n - 2
            poses[j]["sy"] = poses[j].get("sy", 1.0) * (0.96 if sq else 0.98)
            poses[j]["sx"] = poses[j].get("sx", 1.0) * (1.03 if sq else 1.015)
    return poses


def polished(keys, n, rest, name, cyclic=False):
    return weight_shift(polish_sample(keys, n, rest, name, cyclic), name)

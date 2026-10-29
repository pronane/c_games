"""Sprite Forge Studio v9 - foot locking with two-bone leg IK (mannequin / spec builds).

For every move: find the frames where each foot is planted (ankle near the move's lowest ankle height), then
replace the planted ankle path - in the sprite's own root-relative space - by its best straight line at floor
height (a stationary foot is pinned exactly; a walk-cycle foot slides back at one steady treadmill speed),
and bend thigh + shin with analytic two-bone IK so the leg reaches it.  Removes skating, jitter and floor
sinking / floating.  measure() gives the before / after slide in cm for the build report and the tests."""
from __future__ import annotations
import copy

import numpy as np

from .physics import _shortest_arc

LEGS = (("thigh_L", "shin_L", "foot_L"), ("thigh_R", "shin_R", "foot_R"))


def _p(st, j):
    return st.world[j][:3, 3].copy()


def _rel(st, p):
    r = np.asarray(st.root_t, float)
    return p - np.array([r[0], 0.0, r[2]])


def contacts(states, foot, loop, h_tol=0.025, v_tol=0.06):
    """list of contact segments (frame index lists) for one foot"""
    n = len(states)
    if n < 2:
        return []
    P = np.array([_rel(s, _p(s, foot)) for s in states])
    y0 = P[:, 1].min()
    low = P[:, 1] < y0 + h_tol
    sp = np.zeros(n)
    for i in range(n):
        j = (i + 1) % n if loop else min(n - 1, i + 1)
        k = (i - 1) % n if loop else max(0, i - 1)
        sp[i] = np.linalg.norm((P[j] - P[k])[[0, 2]]) / max(1, (j - k) % n if loop else max(1, j - k))
    med = np.median(sp[low]) if low.any() else 0
    on = low & (sp < max(v_tol, 2.5 * med))
    segs, cur = [], []
    order = list(range(n))
    if loop and on.all():
        return [order]
    if loop and on.any():
        s = int(np.argmin(on))           # start the scan at a non-contact frame so wrapped segments stay whole
        order = list(range(s, n)) + list(range(0, s))
    for i in order:
        if on[i]:
            cur.append(i)
        elif cur:
            segs.append(cur); cur = []
    if cur:
        segs.append(cur)
    return [s for s in segs if len(s) >= 2]


def _ik(st, thigh, shin, foot, target):
    """bend thigh + shin (world matrices) so the ankle reaches target; foot keeps its world orientation"""
    W = st.world
    hip, knee, ank = _p(st, thigh), _p(st, shin), _p(st, foot)
    l1, l2 = np.linalg.norm(knee - hip), np.linalg.norm(ank - knee)
    d_vec = target - hip
    d = float(np.linalg.norm(d_vec))
    d = min(max(d, abs(l1 - l2) + 1e-4), l1 + l2 - 1e-4)
    dirn = d_vec / (np.linalg.norm(d_vec) + 1e-9)
    target = hip + dirn * d
    pole = (knee - hip) - np.dot(knee - hip, dirn) * dirn
    if np.linalg.norm(pole) < 1e-5:
        pole = W[thigh][:3, :3] @ np.array([0, 0, 1.0])
        pole = pole - np.dot(pole, dirn) * dirn
    pole /= np.linalg.norm(pole) + 1e-9
    a = (l1 * l1 - l2 * l2 + d * d) / (2 * d)
    h = np.sqrt(max(0.0, l1 * l1 - a * a))
    knee2 = hip + dirn * a + pole * h
    Q1 = _shortest_arc(knee - hip, knee2 - hip)
    Rf = W[foot][:3, :3].copy()
    W[thigh] = W[thigh].copy(); W[thigh][:3, :3] = Q1 @ W[thigh][:3, :3]
    W[shin] = W[shin].copy(); W[shin][:3, :3] = Q1 @ W[shin][:3, :3]; W[shin][:3, 3] = knee2
    Q2 = _shortest_arc(Q1 @ (ank - knee), target - knee2)
    W[shin][:3, :3] = Q2 @ W[shin][:3, :3]
    W[foot] = W[foot].copy(); W[foot][:3, :3] = Rf; W[foot][:3, 3] = target
    return float(np.linalg.norm(target - (knee2 + (Q2 @ Q1 @ (ank - knee)))))


def _fit_line(ts, P):
    A = np.stack([ts, np.ones_like(ts)], 1)
    coef, *_ = np.linalg.lstsq(A, P, rcond=None)
    return coef            # slope (3,), intercept (3,)


def lock(states, loop, fps=12):
    """-> (new states, info).  states are not modified in place."""
    out = [copy.copy(s) for s in states]
    for s in out:
        s.world = dict(s.world)
    info = {"segments": 0, "frames": 0, "before_cm": 0.0, "after_cm": 0.0}
    n = len(states)
    errs_b, errs_a = [], []
    for thigh, shin, foot in LEGS:
        for seg in contacts(states, foot, loop):
            P = np.array([_rel(states[i], _p(states[i], foot)) for i in seg])
            ts = np.arange(len(seg), dtype=float)
            slope, icpt = _fit_line(ts, P[:, [0, 2]])
            if np.linalg.norm(slope) * len(seg) < 0.02:    # stationary foot: pin it
                slope = np.zeros(2); icpt = P[:, [0, 2]].mean(0)
            yfloor = float(P[:, 1].min())
            fit = np.stack([icpt[0] + slope[0] * ts, np.full(len(seg), yfloor), icpt[1] + slope[1] * ts], 1)
            errs_b += list(np.linalg.norm(P - fit, axis=1))
            for k, i in enumerate(seg):
                r = np.asarray(states[i].root_t, float)
                tgt = fit[k] + np.array([r[0], 0.0, r[2]])
                _ik(out[i], thigh, shin, foot, tgt)
                errs_a.append(float(np.linalg.norm(_rel(out[i], _p(out[i], foot)) - fit[k])))
            info["segments"] += 1; info["frames"] += len(seg)
    if errs_b:
        info["before_cm"] = round(100 * float(np.mean(errs_b)), 2)
        info["after_cm"] = round(100 * float(np.mean(errs_a)), 2)
    return out, info


def measure(states, loop):
    """mean deviation (cm) of planted ankles from a steady straight path - the 'foot slide' number"""
    e = []
    for _, _, foot in LEGS:
        for seg in contacts(states, foot, loop):
            P = np.array([_rel(states[i], _p(states[i], foot)) for i in seg])
            ts = np.arange(len(seg), dtype=float)
            slope, icpt = _fit_line(ts, P[:, [0, 2]])
            if np.linalg.norm(slope) * len(seg) < 0.02:
                slope = np.zeros(2); icpt = P[:, [0, 2]].mean(0)
            fit = np.stack([icpt[0] + slope[0] * ts, np.full(len(seg), P[:, 1].min()), icpt[1] + slope[1] * ts], 1)
            e += list(np.linalg.norm(P - fit, axis=1))
    return round(100 * float(np.mean(e)), 2) if e else 0.0

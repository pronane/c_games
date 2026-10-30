"""Sampling motions into frame states (shared by sprite renderer and glTF)."""
from __future__ import annotations
from .rig import evaluate


def sample_times(n, loop):
    if n <= 1:
        return [0.0]
    return [i / n for i in range(n)] if loop else [i / (n - 1) for i in range(n)]


def states_for(motion, n, loop=None):
    loop = motion.loop if loop is None else loop
    out = []
    for t in sample_times(n, loop):
        pose, mix = motion.sample(t)
        out.append(evaluate(pose, mix))
    return out

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


# v11.11: real takes travel (a CMU walk 1.5 m a cycle, a stumble 2.4 m, a shuffle 3 m sideways). A sprite cell is
# drawn in place - the game moves the character - so a move that travels further than this has its travel taken out
# (the hips stay over the cell's anchor); shorter shifts (a lunge, a sway) are kept as they are
SPRITE_TRAVEL_M = 0.35


def sprite_states(motion, n, loop=None):
    """states_for, drawn in place for a sprite sheet when the move travels"""
    return in_place(states_for(motion, n, loop))


def in_place(states):
    import numpy as np
    if not states:
        return states
    xz = np.array([[float(s.root_t[0]), float(s.root_t[2])] for s in states])
    if float(np.max(np.linalg.norm(xz - xz[0], axis=1))) <= SPRITE_TRAVEL_M:
        return states
    from .rig import FrameState
    out = []
    for s, (x, z) in zip(states, xz):
        T = np.eye(4); T[0, 3], T[2, 3] = -x, -z
        W = {k: T @ v for k, v in s.world.items()}
        rt = np.array(s.root_t, dtype=float).copy(); rt[0] -= x; rt[2] -= z
        bp = None if s.ball_pos is None else np.asarray(s.ball_pos, dtype=float) - np.array([x, 0.0, z])
        out.append(FrameState(W, s.local_R, rt, bp))
    return out


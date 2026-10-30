"""Animation retargeting between library rigs through the canonical bone map (v6).

For every canonical bone c mapped on both rigs:
    Wt(t) = Ws(t) . Ws0^-1 . A_c . Wt0          (world rotations)
  Ws(t) / Ws0 source bone world rotation now / at rest, Wt0 the target rest rotation and A_c the rest-pose
  compensation: the minimal rotation taking the target's rest bone direction (bone -> canonical child) onto the
  source's (so an A-pose rig can take a T-pose or arms-down clip and vice versa).  Bones without a canonical
  child (hands, head, toes) inherit their parent's compensation.  Unmapped target bones (twist / helper /
  finger bones) keep their rest rotation relative to their parent.
Hips translation is scaled by the leg-length ratio (target hip height / source hip height) and, by default,
corrected so the lowest ankle follows the source's (less floating / sinking when proportions differ).
Root motion: keep (travel on the hips), inplace (horizontal travel removed), root (travel moved onto the
target's root bone when it has one).
Quality metric: per frame angle between source and target bone directions for every mapped chain segment.
"""
from __future__ import annotations
import math
import numpy as np

from . import bonemap as BM
from .rigrec import rot_between, m4, Clip, FPS, mats_from_quat, quat_from_mats, nlerp


def retarget(src, src_rec, clip, tgt, tgt_rec, root_motion="keep", name=None, ground_fix=True):
    c = src.clips[clip] if isinstance(clip, str) else clip
    ims = BM.index_map(src, src_rec); imt = BM.index_map(tgt, tgt_rec)
    common = [k for k in BM.CANON if k in ims and k in imt]
    cset = set(common)
    Bs, Bt = src.bind, tgt.bind
    A = {}
    for k in common:
        ch = next((x for x in BM.child_candidates(k) if x in cset), None)
        if ch:
            ds = Bs[ims[ch], :3, 3] - Bs[ims[k], :3, 3]
            dt = Bt[imt[ch], :3, 3] - Bt[imt[k], :3, 3]
            A[k] = rot_between(dt, ds)
        else:
            p = BM.canon_parent(k, A)
            A[k] = A[p] if p else np.eye(3)
    inv_t = {i: k for k, i in imt.items() if k in cset}
    L0 = tgt.rest_local()
    Ws = src.clip_worlds(c)
    legs, legt = BM.leg_length(src, src_rec), BM.leg_length(tgt, tgt_rec)
    kscale = legt / max(1e-6, legs)
    hs, ht = ims.get("hips"), imt.get("hips")
    root_t = imt.get("root")
    feet_s = [ims[k] for k in ("foot_L", "foot_R", "toe_L", "toe_R") if k in ims and k in imt]
    feet_t = [imt[k] for k in ("foot_L", "foot_R", "toe_L", "toe_R") if k in ims and k in imt]
    order = tgt.order()
    Fn = c.frames
    Wf = np.zeros((Fn, tgt.nb, 4, 4))
    for f in range(Fn):
        hip_pos = None
        if hs is not None and ht is not None:
            d = (Ws[f, hs, :3, 3] - Bs[hs, :3, 3]) * kscale
            if root_motion == "inplace":
                d0 = (Ws[0, hs, :3, 3] - Bs[hs, :3, 3]) * kscale
                d[0] = d0[0]; d[2] = d0[2]
            hip_pos = Bt[ht, :3, 3] + d
        W = _pose(tgt, order, L0, inv_t, A, Ws[f], Bs, Bt, ims, hip_pos, root_t, root_motion, f, Ws, kscale)
        if ground_fix and feet_s and feet_t and ht is not None:
            ys = min(Ws[f, i, 1, 3] for i in feet_s); ys0 = min(Bs[i, 1, 3] for i in feet_s)
            yt0 = min(Bt[i, 1, 3] for i in feet_t)
            want = yt0 + (ys - ys0) * kscale
            got = min(W[i, 1, 3] for i in feet_t)
            if abs(want - got) > 1e-5:
                hip_pos = hip_pos + np.array([0, want - got, 0])
                W = _pose(tgt, order, L0, inv_t, A, Ws[f], Bs, Bt, ims, hip_pos, root_t, root_motion, f, Ws, kscale)
        Wf[f] = W
    nm = name or (c.name if isinstance(clip, Clip) else clip)
    out = tgt.clip_from_worlds(nm, Wf, c.fps, c.loop, "retargeted from %s:%s" % (src.name, c.name))
    # metric
    errs = []
    for f in range(Fn):
        for k in common:
            ch = next((x for x in BM.child_candidates(k) if x in cset), None)
            if not ch:
                continue
            a = Ws[f, ims[ch], :3, 3] - Ws[f, ims[k], :3, 3]
            b = Wf[f, imt[ch], :3, 3] - Wf[f, imt[k], :3, 3]
            na, nb = np.linalg.norm(a), np.linalg.norm(b)
            if na > 1e-6 and nb > 1e-6:
                errs.append(math.degrees(math.acos(max(-1.0, min(1.0, float(np.dot(a, b) / (na * nb)))))))
    rep = dict(clip=nm, frames=Fn, common_bones=len(common), leg_ratio=round(kscale, 4),
               mean_dir_err_deg=round(float(np.mean(errs)), 4) if errs else None,
               max_dir_err_deg=round(float(np.max(errs)), 4) if errs else None,
               target_unmapped=[tgt.bones[i] for i in range(tgt.nb) if i not in inv_t],
               source_unused=[k for k in ims if k not in cset])
    return out, rep


def _pose(tgt, order, L0, inv_t, A, Wsf, Bs, Bt, ims, hip_pos, root_t, root_motion, f, Ws, kscale):
    W = np.zeros((tgt.nb, 4, 4))
    for i in order:
        p = tgt.parent[i]
        k = inv_t.get(i)
        if k is not None:
            s = ims[k]
            R = Wsf[s, :3, :3] @ Bs[s, :3, :3].T @ A[k] @ Bt[i, :3, :3]
        else:
            R = (W[p, :3, :3] @ L0[i, :3, :3]) if p >= 0 else L0[i, :3, :3]
        pos = (W[p] @ np.r_[L0[i, :3, 3], 1.0])[:3] if p >= 0 else L0[i, :3, 3].copy()
        if k == "hips" and hip_pos is not None:
            pos = hip_pos
        if root_motion == "root" and root_t is not None and i == root_t and "hips" in ims:
            hs = ims["hips"]
            d = (Wsf[hs, :3, 3] - Ws[0, hs, :3, 3]) * kscale
            pos = Bt[i, :3, 3] + np.array([d[0], 0, d[2]])
        W[i] = m4(R, pos)
    return W


def edit_clip(clip, trim=None, speed=1.0, loop=None, name=None):
    """trimmed (seconds a-b) / speed-scaled copy, resampled at 30 fps."""
    a, b = (trim or (0.0, clip.duration))
    a = max(0.0, float(a)); b = min(clip.duration, float(b)) if b is not None else clip.duration
    if b <= a:
        b = clip.duration
    speed = float(speed or 1.0)
    dur = (b - a) / speed
    n = max(2, int(round(dur * FPS)) + 1) if dur > 0 else 1
    R = np.zeros((n,) + clip.R.shape[1:]); T = np.zeros((n,) + clip.T.shape[1:])
    for k in range(n):
        t = a + (k / FPS) * speed if n > 1 else a
        f = min(max(t * clip.fps, 0), clip.frames - 1)
        i0 = int(math.floor(f)); i1 = min(clip.frames - 1, i0 + 1); al = f - i0
        R[k] = nlerp(clip.R[i0], clip.R[i1], al); T[k] = clip.T[i0] * (1 - al) + clip.T[i1] * al
    return Clip(name or clip.name, R, T, FPS, clip.loop if loop is None else loop, clip.source + (" trim %.2f-%.2f" % (a, b) if trim else "") + (" x%.2f" % speed if speed != 1 else ""))

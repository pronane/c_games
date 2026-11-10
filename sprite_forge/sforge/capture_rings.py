"""forge.py capture - garment edges as rings round the limbs (v11.7).

A sleeve ends in a cuff, shorts in a hem, a sock in a band: round the limb, at one distance along it, the same on
the left and the right. The video's labels and colours do not know that. One frame calls the shin above a sock
"clothes", another sees the floor through a gap by the thigh, so the edges come out ragged, and one sock comes out
white and the other brown. Here every point on an arm or a leg gets a coordinate s, the distance (m) along the limb
from the shoulder / hip, through the elbow / knee, to the wrist / ankle and on to the toes. Along s, in 1 cm bins,
both sides pooled, a 1D labelling with a cost per change (Potts, solved exactly by Viterbi) says which material
each bin is: so the edge is one clean ring, at the same s on both sides, wherever most of the evidence puts it.

    limb_coords(head, X, bone, bi) -> (limb id per point: 0 arm L, 1 arm R, 2 leg L, 3 leg R, -1 none; s in metres)
    segment(limb, s, mat, n_mat, ...) -> material per point decided by its ring, and how ring-like each bin is

Used for the clothes' geometry (capture_layers.clothes_faces: which faces are a sleeve or a trouser leg) and for
the texture (capture_clean: which colour cluster a texel on a limb belongs to; a torso garment - a shirt's tails -
is not painted onto the thighs, where it would swing with the leg in a kick)."""
from __future__ import annotations
import numpy as np

CHAINS = {
    0: ("upperarm01.L", "lowerarm01.L", "wrist.L"),
    1: ("upperarm01.R", "lowerarm01.R", "wrist.R"),
    2: ("upperleg01.L", "lowerleg01.L", "foot.L", "toe1-1.L"),
    3: ("upperleg01.R", "lowerleg01.R", "foot.R", "toe1-1.R"),
}
# the points that belong to a limb: their dominant bone is one of these (hands are skin, not ringed)
MEMBERS = {
    0: ("upperarm01.L", "lowerarm01.L"),
    1: ("upperarm01.R", "lowerarm01.R"),
    2: ("upperleg01.L", "lowerleg01.L", "foot.L", "toe1-1.L"),
    3: ("upperleg01.R", "lowerleg01.R", "foot.R", "toe1-1.R"),
}
LEGS = (2, 3)
ARMS = (0, 1)
HIPS = (4,)
# the hips (below the waist) as a ring too: where a shirt or jumper ends over shorts / trousers, s = metres down
# from the navel
HIP_BONES = ("root", "spine05", "pelvis.L", "pelvis.R")


def _polyline(head, bi, chain, toe_len=0.07):
    pts = [np.asarray(head[bi[b]], float) for b in chain if b in bi]
    if chain[-1].startswith("toe"):
        # the toe joint is the ball of the foot: carry on to the tip of the toes
        d = pts[-1] - pts[-2]; d[1] = 0.0
        pts.append(pts[-1] + d / (np.linalg.norm(d) + 1e-9) * toe_len)
    return np.array(pts)


def _project(P, Q):
    """arc-length coordinate of each point of P on the polyline Q (nearest segment)"""
    best_d = np.full(len(P), np.inf); best_s = np.zeros(len(P))
    acc = 0.0
    for a, b in zip(Q[:-1], Q[1:]):
        ab = b - a; L = float(np.linalg.norm(ab)) + 1e-9
        t = np.clip(((P - a) @ ab) / (L * L), 0.0, 1.0)
        d = np.linalg.norm(P - (a + t[:, None] * ab), axis=1)
        up = d < best_d
        best_d[up] = d[up]; best_s[up] = acc + t[up] * L
        acc += L
    return best_s


def limb_coords(head, X, bone, bi):
    """head: rest joint heads (bones x 3); X: rest points; bone: dominant bone index per point; bi: name -> index"""
    limb = np.full(len(X), -1)
    s = np.zeros(len(X))
    for k, chain in CHAINS.items():
        mem = [bi[b] for b in MEMBERS[k] if b in bi]
        sel = np.isin(bone, mem)
        if not sel.any() or any(b not in bi for b in chain[:2]):
            continue
        limb[sel] = k
        s[sel] = _project(X[sel], _polyline(head, bi, chain))
    hb = [bi[b] for b in HIP_BONES if b in bi]
    if "spine04" in bi and "upperleg01.L" in bi:
        top = float(head[bi["spine04"]][1])
        # the hips are one band by height, whichever bone a point follows: the crotch down is the legs
        crotch = 0.5 * (head[bi["upperleg01.L"]][1] + head[bi["upperleg01.R"]][1]) - 0.07
        sel = (np.isin(bone, hb) & (limb < 0)) | (np.isin(limb, LEGS) & (X[:, 1] > crotch) & (X[:, 1] < top))
        limb[sel] = 4
        s[sel] = np.clip(top - X[sel, 1], 0, None)
    return limb, s


def viterbi(cost, change):
    """cost (bins, n_mat): cost of each material in each bin; change: cost of a change between bins -> labels"""
    nb, nm = cost.shape
    acc = cost[0].copy(); back = np.zeros((nb, nm), int)
    for i in range(1, nb):
        stay = acc
        best = int(np.argmin(acc))
        sw = acc[best] + change
        back[i] = np.where(stay <= sw, np.arange(nm), best)
        acc = np.minimum(stay, sw) + cost[i]
    lab = np.zeros(nb, int); lab[-1] = int(np.argmin(acc))
    for i in range(nb - 1, 0, -1):
        lab[i - 1] = back[i, lab[i]]
    return lab


def segment(limb, s, mat, n_mat, weight=None, which=(0, 1, 2, 3, 4), bin_m=0.01, change=None, forbid=None,
            forbid_beyond=None, bare=None):
    """per limb pair (arms pooled, legs pooled - mirror images share their edges): the material of each 1 cm bin
    along s. mat: material id per point (-1 = no evidence); forbid: {pair: [material ids not allowed there]}.
    -> (ring material per point (-1 off the limbs), bin share of the ring material per point, edge distance (m) to
    the nearest change of ring material per point)"""
    ring = np.full(len(s), -1); share = np.zeros(len(s)); edge = np.full(len(s), np.inf)
    w = np.ones(len(s)) if weight is None else weight
    for pair in (ARMS, LEGS, HIPS):
        on = np.isin(limb, [p for p in pair if p in which])
        if not on.any():
            continue
        nb = int(np.ceil(s[on].max() / bin_m)) + 1
        bi_ = np.clip((s / bin_m).astype(int), 0, nb - 1)
        ev = on & (mat >= 0)
        H = np.zeros((nb, n_mat))
        np.add.at(H, (bi_[ev], mat[ev]), w[ev])
        tot = H.sum(1, keepdims=True)
        # the share of the bin that is not that material - a foot seen by few frames weighs as much as a thigh
        # seen by all, as long as it has some evidence (bins with under 5% of the usual count weigh less)
        med_t = float(np.median(tot[tot > 0])) if (tot > 0).any() else 1.0
        conf = np.clip(tot / (0.05 * med_t), 0, 1)
        cost = (tot - H) / np.maximum(tot, 1e-9) * conf
        fb = (forbid or {}).get(pair, ())
        for m in fb:
            if 0 <= m < n_mat:
                cost[:, m] += 1e9
        # forbid_beyond {pair: (s0, [materials])}: not allowed past s0 (the trouser colour below the trousers' hem)
        if forbid_beyond and pair in forbid_beyond:
            s0, ms = forbid_beyond[pair]
            b0 = int(np.ceil(s0 / bin_m))
            for m in ms:
                if 0 <= m < n_mat and b0 < nb:
                    cost[b0:, m] += 1e9
        # empty bins (gaps between the evidence) cost nothing either way
        ch = 1.5 if change is None else change               # a change costs one and a half bins of disagreement
        lab = viterbi(cost, ch)
        if bare is not None and pair == LEGS:
            # a foot is not bare below a sock: bare skin at the far end after a garment (white socks on a wooden
            # floor read as skin at their edges) takes the garment, unless the end is clearly bare
            runs = np.r_[0, np.nonzero(lab[1:] != lab[:-1])[0] + 1, nb]
            if len(runs) >= 3 and lab[runs[-2]] == bare and lab[runs[-3]] != bare:
                a_, b_ = runs[-2], runs[-1]
                hb = H[a_:b_].sum(0); ht = hb.sum()
                if ht == 0 or hb[bare] / ht < 0.75:
                    lab[a_:b_] = lab[runs[-3]]
        sh_ = np.where(tot[:, 0] > 0, H[np.arange(nb), lab] / np.maximum(tot[:, 0], 1e-9), 0.0)
        # distance of each bin to the nearest change of label
        chg = np.nonzero(lab[1:] != lab[:-1])[0]
        if len(chg):
            centres = (np.arange(nb) + 0.5) * bin_m
            cuts = (chg + 1) * bin_m
            ed = np.abs(centres[:, None] - cuts[None, :]).min(1)
        else:
            ed = np.full(nb, np.inf)
        ring[on] = lab[bi_[on]]; share[on] = sh_[bi_[on]]; edge[on] = ed[bi_[on]]
    return ring, share, edge


"""forge.py capture - clean the baked texture (v11.3): the faults that show at game size.

Seen in a game (a fighter ~300 px tall) a captured character's texture is judged by its blotches, not its detail:
black blobs on a white shirt along the shorts, a ragged garment edge, dark hands, white patches on the legs, one
sock white and the other brown, a dark gap under the collar. They come from views that disagree (loose cloth moves
against the body from view to view) and from parts no frame saw, which were filled by 2D inpainting across UV
islands. Here, on the texels of the atlas (their colours, where they sit on the rest-pose body, layer, label, bone):

  1 skin      skin texels (not the head) far from the person's skin colour - a hand painted with the shorts behind
              it, a floor-coloured shin - are dropped
  2 garments  each garment layer's colours are clustered (shirt / shorts / trim); the cluster labels are smoothed
              over the surface in 3D (3 cm), so speckles vanish and the edge between two garments is clean; texels
              whose cluster changed are dropped
  3 fill      every dropped or never-seen texel is filled in 3D on the body, in this order: its mirror image
              (x -> -x; the other sock, the other hand), the nearest kept texels of its own cluster, of its own
              bone, of its own layer; hands / neck / head with nothing near get the person's skin colour (so the
              gap under a collar is skin, not shadow)
  4 flatten   large light / dark bands inside one material (wrinkle highlights blended from different frames) are
              pulled part-way to the material's colour; fine detail stays

    clean(mix, seen, X, layer, label, bone, protect, skin_bones, log) -> (colours, filled mask, info)
"""
from __future__ import annotations
import numpy as np

W_LAB = np.array([0.6, 1.0, 1.0])


def _lab(rgb):
    import cv2
    return cv2.cvtColor(np.clip(rgb, 0, 255).astype(np.uint8)[None], cv2.COLOR_RGB2LAB)[0].astype(np.float32)


def _rgb(lab):
    import cv2
    return cv2.cvtColor(np.clip(lab, 0, 255).astype(np.uint8)[None], cv2.COLOR_LAB2RGB)[0].astype(np.float32)


def _kmeans(Z, k, seed=0):
    from scipy.cluster.vq import kmeans2
    rng = np.random.default_rng(seed)
    sub = Z[rng.choice(len(Z), min(len(Z), 30000), replace=False)].astype(float)
    cent, _ = kmeans2(sub, k, minit="++", seed=seed)
    lab = np.empty(len(Z), int)
    for i in range(0, len(Z), 200000):
        lab[i:i + 200000] = np.argmin(((Z[i:i + 200000, None, :] - cent[None]) ** 2).sum(2), 1)
    return lab, cent


def _smooth_labels(X, lab, k, voxel=0.006, size=7):
    """majority label in a (size * voxel)^3 neighbourhood on the body; the mirror image (x -> -x) votes too, so
    garment edges and socks come out the same left and right"""
    from scipy.ndimage import uniform_filter
    lo = np.minimum(X.min(0), (X * [-1, 1, 1]).min(0)) - voxel * size
    ijk = np.floor((X - lo) / voxel).astype(int)
    ijm = np.floor((X * [-1, 1, 1] - lo) / voxel).astype(int)
    shape = np.maximum(ijk.max(0), ijm.max(0)) + size + 1
    best = None; arg = np.zeros(len(X), int)
    for c in range(k):
        g = np.zeros(shape, np.float32)
        np.add.at(g, tuple(ijk[lab == c].T), 1.0)
        np.add.at(g, tuple(ijm[lab == c].T), 0.6)
        g = uniform_filter(g, size=size, mode="constant")
        v = g[tuple(ijk.T)]
        if best is None:
            best = v
        else:
            up = v > best
            arg[up] = c; best = np.where(up, v, best)
    return arg


def _knn_fill(tree_pts, tree_col, q, k=4, max_d=None):
    """colour at q from its k nearest tree points (inverse-distance); -> (colours, ok mask)"""
    from scipy.spatial import cKDTree
    if len(tree_pts) == 0 or len(q) == 0:
        return np.zeros((len(q), 3), np.float32), np.zeros(len(q), bool)
    k = min(k, len(tree_pts))
    d, j = cKDTree(tree_pts).query(q, k=k)
    if k == 1:
        d = d[:, None]; j = j[:, None]
    w = 1.0 / (d + 1e-3)
    col = (tree_col[j] * w[..., None]).sum(1) / w.sum(1)[:, None]
    ok = d[:, 0] < max_d if max_d is not None else np.ones(len(q), bool)
    return col.astype(np.float32), ok


def clean(mix, seen, X, layer, label, bone, protect, skin_bones, hand_bones=(), log=print, flatten=0.35):
    """mix (N,3) blended texel colours; seen (N,) bool; X (N,3) texel positions on the rest-pose body (x = left /
    right); layer (N,) 0 body, 1 clothes, 2 skirt, 3 hair; label (N,) majority video label 0 none, 1 hair, 2 skin,
    3 clothes; bone (N,) dominant bone id; protect (N,) texels never dropped or flattened (the face);
    skin_bones: bone ids that are bare skin when unseen (hands, neck, head).
    -> (colours with every texel filled, kept mask = texels whose own samples survived, info)"""
    N = len(mix)
    lab = _lab(mix)
    keep = seen.copy()
    info = {}
    # ---- 1 skin outliers
    skin = seen & (layer == 0) & (label == 2)
    body_skin = skin & ~protect
    skin_med = None
    if skin.sum() > 500:
        skin_med = np.median(lab[skin], 0)
        d = np.linalg.norm((lab - skin_med) * W_LAB, axis=1)
        lim = max(28.0, 3.5 * float(np.median(d[skin])))
        bad = body_skin & (d > lim)
        # hands are skin whatever the video labelled them (a hand by the thigh is often labelled as the shorts)
        bad |= seen & (layer == 0) & np.isin(bone, list(hand_bones)) & (d > lim)
        keep &= ~bad
        info["skin_dropped"] = int(bad.sum())
    # ---- 2 garments: cluster, smooth the clusters on the surface
    cluster = np.full(N, -1)                      # global cluster id of kept garment texels
    want = np.full(N, -1)                         # cluster a dropped texel should be filled from
    nc = 0; flipped = 0
    # (the body below the head is one surface: skin, shorts and socks are its clusters)
    for g_sel in (layer == 1, layer == 2, layer == 0):
        sel = np.nonzero(g_sel & keep & ~protect)[0]
        if len(sel) < 3000:
            continue
        k = int(min(4, max(1, len(sel) // 6000)))
        if k == 1:
            cluster[sel] = nc; nc += 1
            continue
        cl, _ = _kmeans(lab[sel] * W_LAB, k)
        sm = _smooth_labels(X[sel], cl, k)
        ch = sm != cl
        cluster[sel[~ch]] = nc + cl[~ch]
        want[sel[ch]] = nc + sm[ch]
        keep[sel[ch]] = False
        flipped += int(ch.sum()); nc += k
    info["garment_relabelled"] = flipped
    # ---- 3 fill
    out = mix.astype(np.float32).copy()
    todo = ~keep
    done = keep.copy()
    Xm = X * [-1, 1, 1]
    for L in np.unique(layer):
        src = np.nonzero(keep & (layer == L))[0]
        if len(src) == 0:
            continue
        # a) the mirror image (not for texels that must take a given cluster)
        q = np.nonzero(todo & ~done & (layer == L) & (want < 0))[0]
        if len(q):
            col, ok = _knn_fill(X[src], out[src], Xm[q], k=3, max_d=0.012)
            out[q[ok]] = col[ok]; done[q[ok]] = True
    info["mirror_filled"] = int((done & todo).sum())
    # b) relabelled garment texels: nearest kept texels of the cluster they belong to
    for c in np.unique(want[want >= 0]):
        q = np.nonzero(~done & (want == c))[0]
        src = np.nonzero(keep & (cluster == c))[0]
        col, ok = _knn_fill(X[src], out[src], X[q], k=4, max_d=0.08)
        out[q[ok]] = col[ok]; done[q[ok]] = True
    # c) bare-skin parts: nearest kept skin on the same bone, else the person's skin colour
    skin_keep = keep & (layer == 0) & (label == 2)
    is_skin_bone = np.isin(bone, list(skin_bones))
    for b_ in np.unique(bone[~done & (layer == 0) & is_skin_bone]):
        q = np.nonzero(~done & (layer == 0) & (bone == b_))[0]
        src = np.nonzero(skin_keep & (bone == b_))[0]
        col, ok = _knn_fill(X[src], out[src], X[q], k=6, max_d=0.03)
        out[q[ok]] = col[ok]; done[q[ok]] = True
        rest = q[~ok]
        if len(rest) and skin_med is not None:
            src2 = np.nonzero(skin_keep & ~protect)[0]
            base = np.median(out[src2], 0) if len(src2) > 200 else _rgb(skin_med[None])[0]
            out[rest] = base; done[rest] = True
    # d) everything else: nearest kept texels of the same bone and layer, then of the same layer
    for same_bone in (True, False):
        for L in np.unique(layer[~done]):
            q_all = np.nonzero(~done & (layer == L))[0]
            if not len(q_all):
                continue
            if same_bone:
                for b_ in np.unique(bone[q_all]):
                    q = q_all[bone[q_all] == b_]
                    src = np.nonzero(keep & (layer == L) & (bone == b_))[0]
                    col, ok = _knn_fill(X[src], out[src], X[q], k=4, max_d=0.06)
                    out[q[ok]] = col[ok]; done[q[ok]] = True
            else:
                src = np.nonzero(keep & (layer == L))[0]
                col, ok = _knn_fill(X[src], out[src], X[q_all], k=4)
                out[q_all[ok]] = col[ok]; done[q_all[ok]] = True
    info["filled"] = int(todo.sum()); info["unfilled"] = int((~done).sum())
    # ---- 4 flatten bands inside each material (garment clusters; body skin as one material)
    if flatten > 0:
        lab2 = _lab(out)
        mats = [np.nonzero(cluster == c)[0] for c in range(nc)]
        for idx in mats:
            if len(idx) < 500:
                continue
            med = np.median(lab2[idx], 0)
            dev = lab2[idx] - med
            # deviations beyond one robust sigma are compressed, small ones (weave, print edges) kept
            s = 1.4826 * np.median(np.abs(dev), 0) + 1.0
            lab2[idx] = med + np.sign(dev) * (np.minimum(np.abs(dev), s) + float(np.clip(1 - flatten * 1.6, 0.2, 1)) * np.maximum(np.abs(dev) - s, 0))
        chg = np.concatenate([i for i in mats if len(i) >= 500]) if any(len(i) >= 500 for i in mats) else np.zeros(0, int)
        out[chg] = _rgb(lab2[chg])
    log("texture clean: %d skin texels off-colour and %d garment texels relabelled, dropped; %d texels filled on the "
        "body in 3D (%d from their mirror image)" % (info.get("skin_dropped", 0), flipped, info["filled"], info["mirror_filled"]))
    return np.clip(out, 0, 255), keep, info

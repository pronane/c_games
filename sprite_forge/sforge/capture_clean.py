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


def _ring_pass(lab, keep, cluster, want, layer, bone, limb, s, protect, torso_bones, log, label=None):
    """v11.7: on the arms and legs a garment edge is a ring (capture_rings): per layer, the cluster each 1 cm band
    along the limb belongs to (both sides pooled); texels of another cluster near an edge or in a clear band, and
    every unseen limb texel, take the band's cluster. A torso garment (a shirt) is not allowed on the legs."""
    from . import capture_rings as CR
    changed = 0
    tube = {}                                       # clothes layer: where its legs / sleeves end, and their colours
    for L in (1, 0):
        on = (layer == L) & (limb >= 0) & ~protect
        ids = np.unique(cluster[(layer == L) & (cluster >= 0)])
        if not on.any() or len(ids) < 2:
            continue
        # clusters of nearly one colour are one material (two shades of the same skin are not two garments)
        cen = np.array([np.median(lab[cluster == c], 0) for c in ids])
        grp = np.arange(len(ids))
        for i in range(len(ids)):
            for j in range(i):
                if np.linalg.norm((cen[i] - cen[j]) * W_LAB) < 14.0:
                    grp[grp == grp[i]] = grp[j]
        uniq, grp = np.unique(grp, return_inverse=True)
        size = np.array([(cluster == c).sum() for c in ids])
        rep = np.array([ids[np.argmax(np.where(grp == g, size, -1))] for g in range(len(uniq))])  # a group's id
        loc = {int(c): int(g) for c, g in zip(ids, grp)}
        mat = np.full(len(lab), -1)
        k_on = on & keep & (cluster >= 0)
        mat[k_on] = [loc.get(int(c), -1) for c in cluster[k_on]]
        # torso garments: most of their texels on the torso, few on the legs
        forbid = []
        lay_c = (layer == L) & (cluster >= 0)
        for g in range(len(uniq)):
            sel = lay_c & np.isin(cluster, ids[grp == g])
            n = max(1, int(sel.sum()))
            tor = float(np.isin(bone[sel], torso_bones).sum()) / n
            leg = float(np.isin(limb[sel], (2, 3)).sum()) / n
            if L == 1 and tor > 0.45 and leg < 0.3:            # clothes layer only: the body under a shirt is hidden
                forbid.append(g)
        fb2 = {}
        if L == 0 and tube:
            # bare skin below a trouser leg / sleeve is not the trousers' colour (a knee shaded dark from views where
            # the shorts hung over it)
            for pair, (s0, cols) in tube.items():
                bad = [g for g in range(len(uniq)) if min(np.linalg.norm((cen[np.argmax(grp == g)] - c) * W_LAB)
                                                         for c in cols) < 20.0]
                fb2[pair] = (s0 + 0.015, bad)
        bare = None
        if L == 0:
            nsk = [int(((label == 2) & (mat == g)).sum()) for g in range(len(uniq))]
            bare = int(np.argmax(nsk)) if max(nsk) > 0 else None
        ring, share, edge = CR.segment(limb, s, mat, len(uniq), forbid={(2, 3): forbid}, forbid_beyond=fb2, bare=bare)
        own = mat
        wrong = on & (ring >= 0) & (own != ring) & ((share >= 0.3) | (edge <= 0.025) | np.isin(own, forbid) | (own < 0))
        # v11.8: the trousers' colour below the trousers' hem (feet seen through the jeans' hem in most frames) is
        # wrong however much of the band it fills
        for pair, (s0, bad) in fb2.items():
            wrong |= on & np.isin(limb, pair) & (s > s0) & np.isin(own, bad) & (ring >= 0) & (own != ring)
        if L == 1:
            for pair in (CR.ARMS, CR.LEGS):
                t = (layer == 1) & np.isin(limb, pair)
                if t.sum() > 100:
                    rr = ring[t]
                    cols = [cen[np.argmax(grp == g)] for g in np.unique(rr[rr >= 0])]
                    tube[pair] = (float(np.percentile(s[t], 99)), cols)
        ch = wrong & keep
        changed += int(ch.sum())
        keep[wrong] = False
        want[wrong] = rep[ring[wrong]]
    log("texture clean: garment edges on the limbs snapped to rings (%d texels moved to their band's colour)" % changed)
    return changed


def clean(mix, seen, X, layer, label, bone, protect, skin_bones, hand_bones=(), log=print, flatten=0.5,
          limb=None, s=None, torso_bones=(), drop=None, chroma=0.75, skin_flatten=0.8, foot_bones=()):
    """mix (N,3) blended texel colours; seen (N,) bool; X (N,3) texel positions on the rest-pose body (x = left /
    right); layer (N,) 0 body, 1 clothes, 2 skirt, 3 hair; label (N,) majority video label 0 none, 1 hair, 2 skin,
    3 clothes; bone (N,) dominant bone id; protect (N,) texels never dropped or flattened (the face);
    skin_bones: bone ids that are bare skin when unseen (hands, neck, head).
    -> (colours with every texel filled, kept mask = texels whose own samples survived, info)"""
    N = len(mix)
    # v11.10: feet in shoes or socks - the video calls them worn or clothes more than skin, the rule that gives them a
    # toe box (capture_layers.shod_feet) - are footwear, a material of their own: they are not pulled to the colour
    # of whatever cluster they fell in (PR's navy socks shared a cluster with shaded skin and came out skin-pale).
    # They stay in the ring pass, which keeps the trousers' colour off them (Declan's jeans)
    shod = np.zeros(N, bool)
    if len(foot_bones):
        fo = (layer == 0) & np.isin(bone, list(foot_bones)) & ~protect
        fs = fo & seen
        if fs.sum() > 200 and ((label[fs] == 3) | (label[fs] == 4)).sum() > (label[fs] == 2).sum():
            shod = fo
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
    # ---- 1b texels the caller knows are wrong (v11.7: garment colour under the chin / on the neck)
    if drop is not None and drop.any():
        info["dropped_given"] = int((keep & drop).sum())
        keep &= ~drop
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
    if limb is not None and s is not None:
        keep0 = keep.copy()
        info["ring_moved"] = _ring_pass(lab, keep, cluster, want, layer, bone, limb, s, protect, list(torso_bones), log,
                                       label=label)
        if shod.any():
            # footwear is not skin: a band the ring pass would paint a shod foot with that is mostly skin-labelled
            # (Declan's black socks came out skin) is not used there - the foot keeps its own colour
            cl_ = np.unique(cluster[cluster >= 0])
            skin_cl = [c for c in cl_ if (label[cluster == c] == 2).mean() > 0.5]
            back = shod & keep0 & ~keep & np.isin(want, skin_cl)
            keep[back] = True; want[back] = -1
            info["feet_not_skin"] = int(back.sum())
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
        q2 = q[~ok]
        if len(q2) and len(src):                  # a band far from any of its own texels: the cluster's colour
            out[q2] = np.median(out[src], 0); done[q2] = True
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
        # v11.7: every texel of a garment / the skin is flattened, not only the ones whose own samples survived -
        # a dropped or never-seen texel was filled from its neighbours and kept their blotch. Each texel joins the
        # cluster of its layer nearest in colour (a filled texel takes the cluster it was filled from: `want`)
        memb = cluster.copy()
        # a dropped texel belongs to the cluster it was filled from, not the one its own (rejected) colour fell in
        memb[(~keep | (memb < 0)) & (want >= 0)] = want[(~keep | (memb < 0)) & (want >= 0)]
        for L in np.unique(layer):
            ids_L = np.unique(cluster[(layer == L) & (cluster >= 0)])
            q = np.nonzero((memb < 0) & (layer == L) & ~protect)[0]
            if len(ids_L) == 0 or len(q) == 0:
                continue
            cen_L = np.array([np.median(lab2[cluster == c], 0) for c in ids_L])
            dd = np.linalg.norm((lab2[q, None, :] - cen_L[None]) * W_LAB, axis=2)
            memb[q] = ids_L[np.argmin(dd, 1)]
        mats = [np.nonzero(memb == c)[0] for c in range(nc)]
        # clusters of nearly one colour in the same layer are one material (a white shirt split into a warm and a
        # cool white): flattened together
        cen = [np.median(lab2[m_], 0) if len(m_) else None for m_ in mats]
        lay_of = [int(np.bincount(layer[m_]).argmax()) if len(m_) else -1 for m_ in mats]
        # complete linkage: a cluster joins a group only when it is near every member (a chain skin -> pale skin
        # -> grey sock must not make the socks skin)
        groups = []
        for i in range(nc):
            if cen[i] is None:
                continue
            lim = 16.0 if lay_of[i] >= 1 else 10.0
            for g in groups:
                if all(lay_of[j] == lay_of[i] and np.linalg.norm((cen[i] - cen[j]) * W_LAB) < lim for j in g):
                    g.append(i)
                    break
            else:
                groups.append([i])
        mats = [np.concatenate([mats[c] for c in g]) for g in groups]
        # the bare skin (the material most texels labelled skin belong to, on the body layer): flattened harder - at
        # game size blotches on a shin read as dirt, and the renderer puts its own light on the figure
        skin_m = -1
        best_n = 0
        for i_, idx in enumerate(mats):
            n_ = int(((label[idx] == 2) & (layer[idx] == 0)).sum())
            if n_ > best_n and n_ > 0.3 * len(idx):
                best_n, skin_m = n_, i_
        if shod.any():
            info["feet_shod"] = int(shod.sum())
            mats = [m_[~shod[m_]] for m_ in mats] + [np.nonzero(shod)[0]]
        for i_, idx in enumerate(mats):
            if len(idx) < 500:
                continue
            fl = flatten
            if i_ == skin_m:
                # only what the video called skin: a white sock or a watch in the same colour cluster stays itself.
                # On the limbs the rings have already decided the material, so every limb texel of it is skin
                idx = idx[(label[idx] == 2) | ((limb[idx] >= 0) if limb is not None else False)]
                fl = skin_flatten
                if len(idx) < 500:
                    continue
            med = np.median(lab2[idx], 0)
            dev = lab2[idx] - med
            # deviations beyond one robust sigma are compressed, small ones (weave, print edges) kept
            sig = 1.4826 * np.median(np.abs(dev), 0) + 1.0
            lab2[idx] = med + np.sign(dev) * (np.minimum(np.abs(dev), sig) + float(np.clip(1 - fl * 1.6, 0.1, 1)) * np.maximum(np.abs(dev) - sig, 0))
            # v11.7: colour (a, b) blotches inside one material are views that disagree (a white shirt warm in one
            # frame, cool in the next, skin showing through): pulled most of the way to the material's colour.
            # Lightness - the folds - is left as above
            lab2[idx, 1:] = med[1:] + (1.0 - chroma) * (lab2[idx, 1:] - med[1:])
        # v11.8: hands. At game size a hand is a few pixels of skin; what the bake gives it is fingers stained with
        # the trousers they hung against and red / dark streaks from views that disagree. Unless the video says
        # they are not skin (gloves), hand texels are pulled to the body's skin colour: lightness half-way (the
        # knuckles keep some shape), colour nearly all the way
        hb = (layer == 0) & np.isin(bone, list(hand_bones)) & ~protect
        if hb.sum() > 200 and skin_m >= 0:
            seen_h = hb & seen
            skin_share = float((label[seen_h] == 2).mean()) if seen_h.any() else 1.0
            if skin_share >= 0.3:
                ref = mats[skin_m]
                ref = ref[(label[ref] == 2) & ~np.isin(bone[ref], list(hand_bones))]
                if len(ref) > 500:
                    med = np.median(lab2[ref], 0)
                    hi_ = np.nonzero(hb)[0]
                    dL = np.clip(lab2[hi_, 0] - med[0], -30, 30)
                    lab2[hi_, 0] = med[0] + 0.5 * dL
                    lab2[hi_, 1:] = med[1:] + 0.15 * (lab2[hi_, 1:] - med[1:])
                    info["hands_evened"] = int(len(hi_))
        out = np.where(np.any(np.abs(lab2 - _lab(out)) > 0.5, 1)[:, None], _rgb(lab2), out)
    log("texture clean: %d skin texels off-colour and %d garment texels relabelled, dropped; %d texels filled on the "
        "body in 3D (%d from their mirror image)" % (info.get("skin_dropped", 0), flipped, info["filled"], info["mirror_filled"]))
    return np.clip(out, 0, 255), keep, info

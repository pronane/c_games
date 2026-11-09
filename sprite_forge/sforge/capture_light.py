"""forge.py capture - take the room's light out of the texture (v11.2).

The person stands still and the camera walks round, so the room's light on any bit of the body is the same in
every frame: it depends on which way that bit faces. Baked as it is, the texture carries that light - a darker back,
a warm side from a lamp, purple on the hair from a TV - and a game engine or Blender then lights it a second time.

Model, per colour channel, in log space:   log(observed) = log(albedo of the material) + L(normal)
  L       smooth coloured light from all round: real spherical harmonics up to order 2 (8 terms - the constant one
          belongs to the albedo), robust least squares (IRLS, Huber), lightly regularised
  albedo  one per material: the texels of each layer and label (hair / skin / clothes) clustered by colour with
          the light taken out, refitted 3 times - so a white shirt and black shorts are two materials, and the
          shaded back of the white shirt stays the white shirt
The texture is divided by exp(L), limited to x0.5..x2. The light found is written to NAME_lighting.json (the 9
coefficients per channel), so the original look can be re-lit, and the held-out check re-applies it.

    fit_light(mix, normals, groups, log)   -> (albedo mix, info)
    relight(albedo, normals, info)         -> lit colours
"""
from __future__ import annotations
import numpy as np


def sh_basis(n):
    """real spherical harmonics up to order 2 (9 columns) of unit normals n (N,3) - x = person's left, y up, z front"""
    x, y, z = n[:, 0], n[:, 1], n[:, 2]
    return np.stack([np.full_like(x, 0.282095), 0.488603 * y, 0.488603 * z, 0.488603 * x,
                     1.092548 * x * y, 1.092548 * y * z, 0.315392 * (3 * z * z - 1), 1.092548 * x * z,
                     0.546274 * (x * x - y * y)], 1)


def _kmeans(Z, k, seed=0):
    from scipy.cluster.vq import kmeans2
    if len(Z) <= k:
        return np.arange(len(Z)) % max(1, k)
    rng = np.random.default_rng(seed)
    sub = Z[rng.choice(len(Z), min(len(Z), 20000), replace=False)]
    cent, _ = kmeans2(sub, k, minit="++", seed=seed)
    d = ((Z[:, None, :] - cent[None]) ** 2).sum(2)
    return np.argmin(d, 1)


def _lab(rgb):
    import cv2
    return cv2.cvtColor(np.clip(rgb, 0, 255).astype(np.uint8)[None], cv2.COLOR_RGB2LAB)[0].astype(float)


def fit_light(mix, normals, groups, weights=None, log=print, k=4, reg=0.05, max_gain=2.0, n_fit=150000):
    """mix (N,3) observed texel colours 0..255, normals (N,3) unit (the room's frame), groups (N,) int material
    group (layer x label). -> (albedo colours (N,3), info dict with 'sh' (3,9))"""
    N = len(mix)
    rng = np.random.default_rng(0)
    good = (mix.max(1) > 8) & (mix.min(1) < 250) & np.isfinite(normals).all(1)
    if weights is not None:
        good &= weights > 0
    idx = np.nonzero(good)[0]
    if len(idx) < 2000:
        return mix, dict(sh=np.zeros((3, 9)).tolist(), applied=False)
    fit_i = idx[rng.choice(len(idx), min(n_fit, len(idx)), replace=False)]
    Y = sh_basis(normals[fit_i])[:, 1:]                                     # 8 directional terms
    logc = np.log(mix[fit_i] + 4.0)
    L = np.zeros((3, 8))
    for it in range(3):
        # materials: within each group, cluster the colours with the current light divided out
        shade = Y @ L.T                                                     # (n,3)
        alb = np.exp(logc - shade) - 4.0
        lab = _lab(alb)
        mat = np.zeros(len(fit_i), int); nm = 0
        for g in np.unique(groups[fit_i]):
            sel = groups[fit_i] == g
            kk = min(k, max(1, sel.sum() // 3000))
            lab_s = lab[sel] * [1.0, 1.5, 1.5]
            mat[sel] = nm + _kmeans(lab_s, kk, seed=it)
            nm += kk
        M = np.zeros((len(fit_i), nm)); M[np.arange(len(fit_i)), mat] = 1.0
        A = np.hstack([M, Y])
        for c in range(3):
            w = np.ones(len(fit_i))
            for _ in range(4):                                              # IRLS, Huber
                Aw = A * w[:, None]; bw = logc[:, c] * w
                R = np.zeros((A.shape[1], A.shape[1])); R[nm:, nm:] = reg * len(fit_i) * 0.01 * np.eye(8)
                x = np.linalg.solve(Aw.T @ Aw + R, Aw.T @ bw)
                r = logc[:, c] - A @ x
                s = 1.4826 * np.median(np.abs(r)) + 1e-6
                w = np.sqrt(np.minimum(1.0, 1.345 * s / (np.abs(r) + 1e-9)))
            L[c] = x[nm:]
    # apply to every texel
    shade = sh_basis(normals)[:, 1:] @ L.T
    shade = np.clip(shade, -np.log(max_gain), np.log(max_gain))
    out = mix.copy()
    out[good] = np.clip((mix[good] + 4.0) * np.exp(-shade[good]) - 4.0, 0, 255)
    sh = np.c_[np.zeros(3), L]                                              # (3, 9); constant term 0 (in the albedo)
    # how strong is the light: the spread of the shading factor over the body, and its colour
    f = np.exp(shade[good])
    spread = float(np.percentile(f.mean(1), 95) / np.percentile(f.mean(1), 5))
    tint = (np.percentile(f, 95, axis=0) / np.percentile(f, 5, axis=0)).round(2).tolist()
    log("light: room light from %d texels, %d materials; brightest / darkest side x%.2f (R/G/B x%s) - divided out" % (
        len(fit_i), nm, spread, "/".join("%.2f" % t for t in tint)))
    return out, dict(sh=sh.tolist(), applied=True, materials=int(nm), spread=spread, tint=tint)


def relight(albedo, normals, info, max_gain=2.0):
    sh = np.asarray(info["sh"], float)
    shade = np.clip(sh_basis(normals) @ sh.T, -np.log(max_gain), np.log(max_gain))
    return np.clip((albedo + 4.0) * np.exp(shade) - 4.0, 0, 255)


def symmetry_de(V, F, fuv, tex, layer_mask=None):
    """mean colour difference (CIE76 dE) between each vertex and its mirror image (x -> -x) on the same mesh, colours
    sampled from the texture at the vertices' UVs. Bodies and most clothes are left / right symmetric, light from
    one side is not - a lower value after delighting means less side light left in the texture (independent of the
    light fit, which never sees left vs right)"""
    from scipy.spatial import cKDTree
    import cv2
    H, W = tex.shape[:2]
    uv = np.full((len(V), 2), np.nan)
    uv[F.ravel()] = fuv.reshape(-1, 2)
    ok = np.isfinite(uv[:, 0])
    if layer_mask is not None:
        ok &= layer_mask
    ids = np.nonzero(ok)[0]
    tree = cKDTree(V[ids])
    d, j = tree.query(V[ids] * [-1, 1, 1])
    pair = d < 0.004
    a, b = ids[pair], ids[j[pair]]
    keep = np.abs(V[a, 0]) > 0.02                                           # not the midline itself
    a, b = a[keep], b[keep]
    px = lambda i: tex[np.clip(((1 - uv[i, 1]) * H).astype(int), 0, H - 1), np.clip((uv[i, 0] * W).astype(int), 0, W - 1)]
    la = cv2.cvtColor(px(a)[None].astype(np.uint8), cv2.COLOR_RGB2LAB)[0].astype(float) * [100 / 255, 1, 1]
    lb = cv2.cvtColor(px(b)[None].astype(np.uint8), cv2.COLOR_RGB2LAB)[0].astype(float) * [100 / 255, 1, 1]
    return float(np.linalg.norm(la - lb, axis=1).mean()), int(len(a))

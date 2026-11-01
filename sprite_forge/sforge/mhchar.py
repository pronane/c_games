"""Realistic characters from the MakeHuman template library (v10.2), shaped by sforge.appearance.

A TEMPLATE is a rigged MakeHuman body already in a game's space (e.g. Gaelic Football's player: MakeHuman topology,
52-bone skeleton, 32 clips).  Every template vertex is matched to a MakeHuman base vertex through the shared UV
layout, so any MakeHuman modifier target and any fitted CC0 asset (.mhclo) can be applied to it:

    tm = mhchar.Template.load("gaelic_template.glb")
    ch = mhchar.build(tm, appearance, lib)        # -> Character: body / garments / hair / brows / lashes / eyes
    ch.meshes, ch.skin_png

Morph deltas and asset offsets are authored in MakeHuman's rest space; they are carried into the template's pose with
a per-vertex similarity transform (rotation + scale) fitted to each vertex's mesh neighbourhood, so a nose or a hair
cap follows the head however the template is posed and scaled."""
from __future__ import annotations
import io
from dataclasses import dataclass, field
import numpy as np
from PIL import Image
from . import glbpack
from .mhlib import Library


# ------------------------------------------------------------------ template
def _acc(j, b, i):
    a = j["accessors"][i]; bv = j["bufferViews"][a["bufferView"]]
    dt = glbpack.COMP[a["componentType"]]; n = glbpack.NCOMP[a["type"]]
    o = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
    return np.frombuffer(b[o:o + a["count"] * n * np.dtype(dt).itemsize], dt).reshape(a["count"], n).copy()


@dataclass
class Template:
    path: str
    P: np.ndarray            # (n,3) body vertices in template space (bind pose)
    UV: np.ndarray           # (n,2)
    F: np.ndarray            # (m,3)
    J: np.ndarray            # (n,4)
    W: np.ndarray            # (n,4)
    joints: list
    base_of: np.ndarray = None      # (n,) template vertex -> base vertex
    rep: np.ndarray = None          # (19158,) base vertex -> one template vertex (body only, -1 helpers)
    R: np.ndarray = None            # (19158,3,3) base -> template rotation*scale per base vertex
    G0: np.ndarray = None           # (19158,3) every base vertex in template space (helpers by their nearest body vertex)
    Wd: np.ndarray = None           # (19158,nj) dense skin weights per base vertex
    Vb: np.ndarray = None           # MakeHuman base rest positions (dm)

    @classmethod
    def load(cls, path, lib: Library):
        j, b = glbpack.read_glb(path)
        pr = j["meshes"][0]["primitives"][0]; a = pr["attributes"]
        P = _acc(j, b, a["POSITION"]).astype(float); UV = _acc(j, b, a["TEXCOORD_0"]).astype(float)
        F = _acc(j, b, pr["indices"]).reshape(-1, 3).astype(np.int64)
        J = _acc(j, b, a["JOINTS_0"]).astype(np.int64); W = _acc(j, b, a["WEIGHTS_0"]).astype(float)
        names = [j["nodes"][i]["name"] for i in j["skins"][0]["joints"]]
        t = cls(path, P, UV, F, J, W, names)
        t._match(lib)
        return t

    def _match(self, lib):
        from scipy.spatial import cKDTree
        Vb, Fb, uvb = lib.base()
        nb = len(Vb)
        cu = uvb.reshape(-1, 2); cv = Fb.reshape(-1)
        q = self.UV.copy(); q[:, 1] = 1.0 - q[:, 1]
        d, i = cKDTree(cu).query(q)
        if np.percentile(d, 99) > 1e-4:
            raise ValueError("template is not MakeHuman topology (UV match %.2e)" % np.percentile(d, 99))
        self.base_of = cv[i]
        rep = np.full(nb, -1, np.int64); rep[self.base_of] = np.arange(len(self.P))
        self.rep = rep
        body = np.nonzero(rep >= 0)[0]
        # neighbourhoods on the base body mesh (2 rings, padded to K)
        adj = [set() for _ in range(nb)]
        for f in Fb:
            for a_, b_ in ((0, 1), (1, 2), (2, 0)):
                adj[f[a_]].add(f[b_]); adj[f[b_]].add(f[a_])
        K = 16
        nbr = np.zeros((nb, K), np.int64)
        for v in body:
            s = set(adj[v])
            for u in list(s):
                s |= adj[u]
            s.discard(v)
            L = [u for u in s if rep[u] >= 0][:K] or [v]
            nbr[v] = (L * (K // len(L) + 1))[:K]
        X = Vb[nbr[body]] - Vb[body][:, None]                       # base
        Y = self.P[rep[nbr[body]]] - self.P[rep[body]][:, None]     # template
        H = np.einsum("nki,nkj->nij", X, Y)
        U, S, Vt = np.linalg.svd(H)
        D = np.ones((len(body), 3)); D[:, 2] = np.sign(np.linalg.det(np.einsum("nij,njk->nik", U, Vt)).T)
        Rr = np.einsum("nji,nj,nkj->nik", Vt, D, U)                  # V diag U^T
        sc = (S * D).sum(1) / np.maximum((X ** 2).sum((1, 2)), 1e-12)
        R = np.zeros((nb, 3, 3)); R[body] = Rr * sc[:, None, None]
        G0 = np.zeros((nb, 3)); G0[body] = self.P[rep[body]]
        helpers = np.nonzero(rep < 0)[0]
        _, near = cKDTree(Vb[body]).query(Vb[helpers])
        nbody = body[near]
        R[helpers] = R[nbody]
        G0[helpers] = G0[nbody] + np.einsum("nij,nj->ni", R[nbody], Vb[helpers] - Vb[nbody])
        self.R, self.G0 = R, G0
        self.Vb = Vb
        nj = len(self.joints)
        Wd = np.zeros((nb, nj))
        Wd_body = np.zeros((len(self.P), nj)); np.add.at(Wd_body, (np.arange(len(self.P))[:, None].repeat(4, 1), self.J), self.W)
        Wd[body] = Wd_body[rep[body]]; Wd[helpers] = Wd[nbody]
        self.Wd = Wd

    def to_template(self, Vb_new, idx=None):
        """morphed base positions -> template space (per-vertex transform of the displacement)"""
        Vb = self.Vb
        idx = np.arange(len(Vb)) if idx is None else idx
        return self.G0[idx] + np.einsum("nij,nj->ni", self.R[idx], Vb_new[idx] - Vb[idx])


_LIB_BASE = [None]


# ------------------------------------------------------------------ character
@dataclass
class Part:
    name: str
    role: str                 # body | kit | hair | brows | lashes | eyes
    V: np.ndarray
    F: np.ndarray
    UV: np.ndarray
    J: np.ndarray
    W: np.ndarray
    N: np.ndarray = None
    C: np.ndarray = None      # vertex colours (n,4) or None
    image: str = ""           # key into Character.images


@dataclass
class Character:
    parts: list = field(default_factory=list)
    images: dict = field(default_factory=dict)      # key -> PNG bytes


def normals(V, F):
    fn = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
    N = np.zeros_like(V)
    for k in range(3):
        np.add.at(N, F[:, k], fn)
    ln = np.linalg.norm(N, axis=1, keepdims=True)
    return np.where(ln > 1e-12, N / np.maximum(ln, 1e-12), np.array([0, 1.0, 0]))


def hair_normals(X, F, radius=0.025, k=32):
    """smooth normals for card hair: each card's own normal is flat (faceted lighting, visible planes), so average the
    normals of all cards within `radius` (metres, template space) and point them away from the local hair mass -
    the hair is lit like one soft volume, as real hair reads"""
    from scipy.spatial import cKDTree
    N0 = normals(X, F)
    tree = cKDTree(X)
    d, idx = tree.query(X, k=min(k, len(X)))
    w = np.clip(1 - d / radius, 0, 1)[..., None]
    # big-scale outward direction: from the hair's own axis (vertical spread damped, so a hanging tail points out
    # sideways, not down); every card normal is turned to agree with it before averaging - no flipped patches
    big = X - X.mean(0); big[:, 1] *= 0.35
    big /= np.linalg.norm(big, axis=1, keepdims=True) + 1e-12
    N0 = np.where((N0 * big).sum(1, keepdims=True) < 0, -N0, N0)
    N = (N0[idx] * w).sum(1)
    N = N / (np.linalg.norm(N, axis=1, keepdims=True) + 1e-12) + 0.8 * big
    return N / (np.linalg.norm(N, axis=1, keepdims=True) + 1e-12)


def top4(Wd):
    idx = np.argsort(-Wd, axis=1)[:, :4]
    w = np.take_along_axis(Wd, idx, 1)
    w[w < 0.01] = 0
    w = w / np.maximum(w.sum(1, keepdims=True), 1e-9)
    idx = np.where(w > 0, idx, 0)
    return idx.astype(np.uint16), w.astype(np.float32)


def _png(im):
    bio = io.BytesIO(); im.save(bio, "PNG", optimize=True); return bio.getvalue()


def _neutral_alpha_texture(path, size=512):
    """hair / brow / lash texture -> light grey detail + hard alpha (tinted per character by vertex colour;
    soft alpha edge band; hard_alpha() makes the copy the game gets, which draws card hair alpha-tested)"""
    im = Image.open(path).convert("RGBA").resize((size, size), Image.LANCZOS)
    a = np.asarray(im).astype(np.float32) / 255
    rgb, al = a[..., :3], a[..., 3]
    lum = rgb.mean(-1)
    m = al > 0.3
    ref = np.median(lum[m]) if m.any() else 0.5
    g = np.clip(0.82 * lum / max(ref, 1e-3), 0, 1.25)
    from scipy.ndimage import distance_transform_edt
    _, (iy, ix) = distance_transform_edt(~m, return_indices=True)
    g = g[iy, ix]                                                      # bleed colour under transparent texels
    out = np.dstack([g, g, g, _ss(0.12, 0.62, al)])                    # soft edge band (engines blend / dither it)
    return Image.fromarray((np.clip(out, 0, 1) * 255).astype(np.uint8), "RGBA")


def hard_alpha(png, cut=0.4):
    """alpha-tested copy of a hair texture (for engines that draw card hair without sorting)"""
    im = Image.open(io.BytesIO(png)).convert("RGBA")
    a = np.asarray(im).copy()
    a[..., 3] = np.where(a[..., 3] > cut * 255, 255, 0)
    return _png(Image.fromarray(a, "RGBA"))


def engine_images(images):
    """images for a GLB: card hair textures alpha-tested, everything else as is"""
    return {k: (hard_alpha(v) if k.startswith("hair_") else v) for k, v in images.items()}


def build(tm: Template, ap, lib: Library, name="player", kit_regions=None, skin_res=1024):
    """-> Character with body, kit garments, hair, brows, lashes, eyes (all on the template's skeleton)"""
    _LIB_BASE[0] = lib.base()
    Vb, Fb, uvb = lib.base()
    # ---- body morph
    Vm = Vb.copy()
    for t, w in ap.target_weights(lib).items():
        i, d = lib.target(t)
        Vm[i] += d * w
    G = tm.to_template(Vm)
    ch = Character()
    Pb = G[tm.base_of]
    Jb, Wb = tm.J.astype(np.uint16), tm.W.astype(np.float32)
    covered = np.zeros(len(tm.F), bool)
    for gname, faces, thick in garment_faces(tm, Pb, kit_regions):
        sub = tm.F[faces]
        wid = weld_ids(Pb)
        rim = np.unique(wid[boundary_edges_welded(Pb, sub)])
        inner = ~np.isin(wid[sub], rim).any(1)
        covered[faces[inner]] = True
    ch.parts.append(Part(name + "_body", "body", Pb, tm.F[~covered], tm.UV, Jb, Wb, normals(Pb, tm.F), image="skin"))
    # ---- skin texture (MakeHuman skin + facial hair / stubble / scalp paint)
    ch.images["skin"] = _png(paint_skin(tm, ap, lib, Vm, skin_res))
    # ---- kit garments from the body surface
    for gname, faces, thick in garment_faces(tm, Pb, kit_regions):
        V, F, UV, J, W = _solidify(Pb, tm.F[faces], tm.UV, Jb, Wb, thick)
        ch.parts.append(Part("%s_%s" % (name, gname), "kit", V, F, kit_uv(gname, UV), J, W, normals(V, F), image="kit"))
    # ---- fitted assets
    def fitted(kind, aname, role, tint=None, image_key=None, keep=None, scale_about=None, hairline_scale=True, fade=None,
               inner=False):
        p = lib.proxy(kind, aname)
        Xb = p.fit(Vm)                                                  # base space (dm)
        r0 = p.ref[:, 0]
        X = G[r0] + np.einsum("nij,nj->ni", tm.R[r0], Xb - Vm[r0])
        if scale_about is not None:
            X = scale_about(X)
        Wd = (tm.Wd[p.ref] * p.w[..., None]).sum(1)
        J, W = top4(Wd)
        F = p.F
        if keep is not None:
            F = F[keep(Xb, p)]
            if hairline_scale:
                mk = hair_mask(Xb, ap.hairline, Vb)
                f = np.clip(0.35 + 0.65 * mk, 0.35, 1.0)[:, None]          # thinning strands lie flatter / shorter
                X = G[r0] + (X - G[r0]) * f
        C = None
        if tint is not None:
            C = np.tile(np.array(list(tint) + [1.0], np.float32), (len(X), 1))
        if fade is not None:                                            # thinning hairline: strands fade out
            mk = hair_mask(Xb, fade, Vb)
            al = _ss(0.12, 0.75, mk)
            F = F[al[F].max(1) > 0.04]
            if C is None:
                C = np.ones((len(X), 4), np.float32)
            C[:, 3] = al
        key = image_key or ("%s_%s" % (kind, aname))
        if key not in ch.images and p.tex:
            ch.images[key] = _png(_neutral_alpha_texture(p.tex) if role in ("hair", "brows", "lashes")
                                  else Image.open(p.tex).convert("RGB"))
        if inner and role == "hair":                                     # inner layer: fills the gaps between cards
            cb, _r = _head_frame(Vm)
            Xi_b = cb + (Xb - cb) * 0.965
            Xi = G[r0] + np.einsum("nij,nj->ni", tm.R[r0], Xi_b - Vm[r0])
            Ci = C.copy() if C is not None else np.ones((len(Xi), 4), np.float32)
            Ci[:, :3] *= 0.93
            ch.parts.append(Part("%s_hairinner" % name, role, Xi, F, p.UV, J, W, hair_normals(Xi, F), Ci, key))
        ch.parts.append(Part("%s_%s" % (name, role), role, X, F, p.UV, J, W,
                             hair_normals(X, F) if role == "hair" else normals(X, F), C, key))
    eye_key = "eyes_" + ap.eye_colour
    if eye_key not in ch.images:
        ch.images[eye_key] = _png(Image.open(lib.eye_texture(ap.eye_colour)).convert("RGB").resize((512, 512)))
    fitted("eyes", "high-poly", "eyes", image_key=eye_key,
           keep=lambda Xb, p: ~(p.UV[p.F].min(1) > 0.85).all(1), hairline_scale=False)   # drop the cornea domes
    fitted("eyelashes", "eyelashes02", "lashes", tint=np.array([0.08, 0.06, 0.05]))
    bt = float(ap.brow_thickness)
    fitted("eyebrows", ap.brow_style, "brows", tint=ap.rgb("brow_colour"),
           scale_about=(lambda X: _bushy(X, bt)) if abs(bt) > 1e-3 else None)
    # ---- facial hair: strand cards on the face (moustache / goatee / beard), lit with the skin's normal
    for k, (Xb, Fs, UVs, vb, al, Ns) in enumerate(facial_hair_shell(ap, lib, Vm)):
        X = G[vb] + np.einsum("nij,nj->ni", tm.R[vb], Xb - Vm[vb])
        Nx = np.einsum("nij,nj->ni", tm.R[vb], Ns); Nx /= np.linalg.norm(Nx, axis=1, keepdims=True) + 1e-12
        J, W = top4(tm.Wd[vb])
        C = np.tile(np.array(list(np.array(ap.rgb("facial_hair_colour")) * (0.85 if k == 0 else 1.0)) + [1.0], np.float32), (len(X), 1))
        C[:, 3] = al
        Fk = Fs[al[Fs].max(1) > 0.02]
        if "beard_shell" not in ch.images:
            ch.images["beard_shell"] = _png(shell_texture())
        ch.parts.append(Part("%s_beardshell%d" % (name, k), "hair", X, Fk, UVs, J, W, Nx, C, "beard_shell"))
    fc = facial_hair_cards(ap, lib, Vm)
    if fc is not None:
        Xb, Fc, UVc, tri, bcc, Ns = fc
        r0 = tri[:, 0]
        X = G[r0] + np.einsum("nij,nj->ni", tm.R[r0], Xb - Vm[r0])
        Nx = np.einsum("nij,nj->ni", tm.R[r0], Ns); Nx /= np.linalg.norm(Nx, axis=1, keepdims=True) + 1e-12
        J, W = top4((tm.Wd[tri] * bcc[..., None]).sum(1))
        C = np.tile(np.array(list(ap.rgb("facial_hair_colour")) + [1.0], np.float32), (len(X), 1))
        if "facial_hair" not in ch.images:
            ch.images["facial_hair"] = _png(strand_texture())
        ch.parts.append(Part("%s_facialhair" % name, "hair", X, Fc, UVc, J, W, Nx, C, "facial_hair"))
    hs = ap.hair_style
    if hs not in ("bald", "buzz"):
        hl = float(ap.hairline)
        fitted("hair", hs, "hair", tint=ap.rgb("hair_colour"), fade=hl if hl > 0.05 else None, inner=True)
    return ch


def _bushy(X, t):
    """thicker / thinner brows: scale each brow card about its own centre (taller and fuller when t > 0)"""
    out = X.copy()
    for s in (X[:, 0] > 0, X[:, 0] <= 0):
        if not s.any():
            continue
        c = X[s].mean(0)
        f = 1.0 + 0.45 * t
        out[s] = c + (X[s] - c) * np.array([1.0 + 0.1 * t, f, 1.0 + 0.3 * max(t, 0)])
    return out


_HF = {}


def _head_frame(Vb):
    """head centre / radius in MakeHuman base space (decimetres), from the body's head vertices"""
    k = id(Vb)
    if k not in _HF:
        body = Vb[:13380]
        H = body[body[:, 1] > 6.9]
        H = H[np.abs(H[:, 0]) < 1.0]
        top, back, front = H[:, 1].max(), H[:, 2].min(), H[:, 2].max()
        c = np.array([0.0, top - 0.8, (front + back) / 2])
        _HF[k] = (c, 0.95)
    return _HF[k]


def _sig(x):
    return 1.0 / (1.0 + np.exp(-np.clip(x, -40, 40)))


def hair_mask(Pb, hairline, Vb):
    """0..1 how much hair a base-space point keeps.  hairline 0 = full head; the temples go first, then the front
    hairline moves back, then (past 0.5) the crown thins - the sides and back always stay (horseshoe)"""
    c, r = _head_frame(Vb)
    d = Pb - c
    u = d / np.maximum(np.linalg.norm(d, axis=1, keepdims=True), 1e-9)
    temple = np.exp(-((np.abs(u[:, 0]) - 0.45) / 0.18) ** 2) * np.clip(u[:, 2] * 2, 0, 1)
    fs = u[:, 2] + 0.45 * u[:, 1]
    thr = 1.25 - 1.0 * hairline - 0.35 * hairline * temple
    front = _sig((fs - thr) / 0.04)
    crown = _sig((u[:, 1] - (1.3 - 0.6 * hairline)) / 0.03) * (hairline > 0.5)
    return np.clip(1 - np.maximum(front, crown), 0, 1)


def _hair_keep(Xb, p, hairline, Vb, seed=11):
    """receding hair thins out instead of stopping at a line: each strand card survives with a probability that
    follows the hair mask (full hair 1 -> bald 0), so the hairline is sparse and uneven like a real one"""
    m = hair_mask(Xb, hairline, Vb)[p.F].mean(1)
    u = np.random.default_rng(seed).random(len(p.F))
    return m > 0.08 + 0.84 * u


# ------------------------------------------------------------------ garments
KIT = {   # name: thickness (m)
    "jersey": 0.009, "shorts": 0.011, "socks": 0.003, "boots": 0.007,
}


def garment_faces(tm: Template, P, regions=None):
    """faces of the body that each garment covers (by dominant bone and position along the bone)"""
    jn = {n: i for i, n in enumerate(tm.joints)}
    Fc = P[tm.F].mean(1)
    W = np.zeros((len(P), len(tm.joints))); np.add.at(W, (np.arange(len(P))[:, None].repeat(4, 1), tm.J.astype(np.int64)), tm.W)
    Wf = W[tm.F].mean(1)
    dom = np.argmax(Wf, 1)
    nm = np.array(tm.joints)[dom]
    y = Fc[:, 1]
    jpos = _joint_positions(tm)

    def along(a, b):
        A, B = jpos[a], jpos[b]
        ab = B - A
        return ((Fc - A) @ ab) / (ab @ ab)
    out = []
    nms = nm.astype(str)
    torso = np.char.startswith(nms, "spine_") | np.isin(nm, ["clavicle_l", "clavicle_r"]) | ((nm == "pelvis") & (y > 0.86))
    neck = (nm == "neck_01") & (y < 1.47)
    arm = np.zeros(len(Fc), bool)
    for s in "lr":
        arm |= (nm == "upperarm_" + s) & (along("upperarm_" + s, "lowerarm_" + s) < 0.52)
    out.append(("jersey", np.nonzero(torso | neck | arm)[0], KIT["jersey"]))
    leg = np.zeros(len(Fc), bool)
    for s in "lr":
        leg |= (nm == "thigh_" + s) & (along("thigh_" + s, "calf_" + s) < 0.36)
    shorts = ((nm == "pelvis") | np.char.startswith(nms, "hip_") | leg | ((nm == "spine_01") & (y < 0.99))) & (y < 0.99)
    out.append(("shorts", np.nonzero(shorts)[0], KIT["shorts"]))
    sock = np.zeros(len(Fc), bool)
    for s in "lr":
        sock |= (nm == "calf_" + s) & (along("calf_" + s, "foot_" + s) > 0.22)
    out.append(("socks", np.nonzero(sock)[0], KIT["socks"]))
    boot = np.isin(nm, ["foot_l", "foot_r", "ball_l", "ball_r"]) | ((np.char.startswith(nm.astype(str), "calf_")) & (y < 0.115))
    out.append(("boots", np.nonzero(boot)[0], KIT["boots"]))
    return out


def _joint_positions(tm):
    j, _ = glbpack.read_glb(tm.path)
    from .footballer import Skeleton
    sk = Skeleton.from_glb(tm.path)
    return {n: sk.p(n) for n in sk.names}


def boundary_edges(F):
    E = np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]])
    key = np.sort(E, 1)
    _, inv, cnt = np.unique(key, axis=0, return_inverse=True, return_counts=True)
    return E[cnt[inv.ravel()] == 1]


def _smooth_hem(V, bd, iters=6, lam=0.5):
    """relax the hem (boundary loop) so it runs straight instead of stepping along the triangles"""
    V = V.copy()
    nb = {}
    for a, b in bd:
        nb.setdefault(a, []).append(b); nb.setdefault(b, []).append(a)
    keys = np.array(list(nb.keys()))
    if not len(keys):
        return V
    pairs = np.array([nb[k][:2] if len(nb[k]) >= 2 else [nb[k][0], nb[k][0]] for k in keys])
    for _ in range(iters):
        V[keys] = V[keys] * (1 - lam) + lam * 0.5 * (V[pairs[:, 0]] + V[pairs[:, 1]])
    return V


def weld_ids(P, tol=1e-5):
    """vertex -> id shared by vertices at the same position (UV seams split the template's vertices)"""
    _, inv = np.unique(np.round(P / tol).astype(np.int64), axis=0, return_inverse=True)
    return inv.ravel()


def boundary_edges_welded(P, F):
    """real open edges of a face set (UV seams are not edges): (k,2) vertex indices of F"""
    w = weld_ids(P)
    E = np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]])
    key = np.sort(w[E], 1)
    _, inv, cnt = np.unique(key, axis=0, return_inverse=True, return_counts=True)
    return E[cnt[inv.ravel()] == 1]


def _solidify(P, F, UV, J, W, t):
    """offset a face set along the vertex normals, straighten the hems and close them with a rim strip"""
    used = np.unique(F)
    remap = -np.ones(len(P), np.int64); remap[used] = np.arange(len(used))
    Fl = remap[F]
    Pu = P[used]
    w = weld_ids(Pu)
    # normals and hems on the welded surface (seam vertices move together: no cracks, no false hems)
    nw = w.max() + 1
    Pw = np.zeros((nw, 3)); Pw[w] = Pu
    Nw = normals(Pw, w[Fl])
    Pn = Nw[w]
    bdw = boundary_edges(w[Fl])
    base = _smooth_hem(Pw, bdw)[w]
    V = base + Pn * t
    # boundary edges -> rim quads from the outer surface down to the body (hides the gap)
    bd = boundary_edges_welded(Pu, Fl)
    n0 = len(V)
    Vin = base - Pn * 0.002
    V = np.concatenate([V, Vin])
    rim = []
    for a, b in bd:
        rim += [[a, b, n0 + b], [a, n0 + b, n0 + a]]
    Fo = np.concatenate([Fl, np.array(rim, np.int64).reshape(-1, 3)]) if rim else Fl
    UVo = np.concatenate([UV[used], UV[used]])
    Jo = np.concatenate([J[used], J[used]]); Wo = np.concatenate([W[used], W[used]])
    return V, Fo, UVo, Jo, Wo


# ------------------------------------------------------------------ skin painting
def raster_base_uv(tm: Template, res):
    """texel -> template face id + barycentrics (template UVs)"""
    from .render_sculpt import rasterise
    sx = tm.UV[:, 0] * res; sy = tm.UV[:, 1] * res
    tid, bc, _ = rasterise(sx, sy, np.zeros(len(sx)), tm.F, res, res, K=8)
    return tid, bc


def _landmarks(lib, Vb):
    def c(t):
        i, _ = lib.target(t); return Vb[i].mean(0)
    def box(t):
        i, _ = lib.target(t); return Vb[i]
    return {"mouth": c("mouth/mouth-scale-horiz-incr"), "mouth_pts": box("mouth/mouth-scale-horiz-incr"),
            "nose": c("nose/nose-scale-vert-incr"), "nose_pts": box("nose/nose-scale-vert-incr"),
            "chin": c("chin/chin-prominent-incr"), "cheek_l": c("cheek/l-cheek-bones-incr"),
            "cheek_r": c("cheek/r-cheek-bones-incr"), "ear_l": c("ears/l-ear-scale-incr"), "ear_r": c("ears/r-ear-scale-incr"),
            "eye_l": c("eyes/l-eye-scale-incr"), "eye_r": c("eyes/r-eye-scale-incr")}


def _noise(P, f):
    return (np.sin(P[:, 0] * f * 1.7 + P[:, 1] * f * 0.3) * np.sin(P[:, 1] * f * 1.3 - P[:, 2] * f * 0.9) +
            0.5 * np.sin(P[:, 2] * f * 2.3 + P[:, 0] * f * 1.1)) / 1.5


def _ss(e0, e1, v):
    t = np.clip((v - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


MOUTH_Y, LIP_TOP, NOSE_BASE, CHIN_Y = 6.63, 6.715, 6.83, 6.40   # MakeHuman base face midline profile (dm)


def facial_zones(P, L):
    """0..1 masks at base rest positions P (dm): beard face area, lips, moustache, chin (goatee)"""
    x, y, z = P[:, 0], P[:, 1], P[:, 2]
    ax = np.abs(x)
    ear_z = (L["ear_l"][2] + L["ear_r"][2]) / 2
    ch_ = L["chin"]
    upper = 7.02 - 0.22 * np.clip((0.75 - ax) / 0.45, 0, 1)
    face = _ss(ear_z - 0.05, ear_z + 0.15, z) * (1 - _ss(upper - 0.08, upper + 0.06, y)) * _ss(ch_[1] - 0.75, ch_[1] - 0.55, y) * \
        _ss(ch_[2] - 1.0, ch_[2] - 0.7, z)
    lips = 1 - _ss(0.85, 1.15, np.sqrt((x / 0.26) ** 2 + ((y - MOUTH_Y) / 0.085) ** 2))
    mous_lo = LIP_TOP - 0.11 * _ss(0.14, 0.30, ax)
    mous = (1 - _ss(0.27, 0.33, ax)) * _ss(mous_lo - 0.012, mous_lo + 0.012, y) * (1 - _ss(NOSE_BASE - 0.04, NOSE_BASE, y)) * \
        _ss(1.25, 1.38, z) * (1 - lips * 0.85)
    chin = (1 - _ss(0.17, 0.25, ax)) * (1 - _ss(MOUTH_Y - 0.11, MOUTH_Y - 0.06, y)) * _ss(CHIN_Y - 0.25, CHIN_Y - 0.12, y) * \
        _ss(1.0, 1.15, z)
    # sideburns: a strip in front of the ear from the beard up to the hairline, so beard and hair join
    side = _ss(ear_z - 0.02, ear_z + 0.08, z) * (1 - _ss(ear_z + 0.30, ear_z + 0.42, z)) * _ss(0.55, 0.65, ax) * \
        (1 - _ss(7.52, 7.66, y)) * _ss(upper - 0.2, upper, y)
    # neckline: the beard stops under the jaw instead of running down the neck
    neck = _ss(ch_[1] - 0.62, ch_[1] - 0.40, y) + (1 - _ss(ch_[1] - 0.62, ch_[1] - 0.40, y)) * _ss(ch_[2] - 0.55, ch_[2] - 0.25, z)
    face = np.maximum(face, side) * np.clip(neck, 0, 1)
    return {"face": face, "lips": lips, "mous": mous, "chin": chin, "side": side}


def strand_texture(size=256, strands=26, seed=3):
    """RGBA strand clump for facial hair cards: light grey (tinted by vertex colour), darker at the root (bottom),
    tapering tips at the top, hard alpha for alpha-tested drawing"""
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:size, 0:size] / float(size)
    a = np.zeros((size, size)); g = np.zeros((size, size))
    for _ in range(strands):
        xc = rng.uniform(0.05, 0.95); w = rng.uniform(0.012, 0.022); top = rng.uniform(0.0, 0.3)
        bend = rng.uniform(-0.08, 0.08)
        xs = xc + bend * (1 - yy) ** 2
        prof = np.clip(1 - ((xx - xs) / (w * (0.35 + 0.65 * _ss(top, 1.0, yy)))) ** 2, 0, 1) * (yy > top)
        a = np.maximum(a, prof); g = np.maximum(g, prof * rng.uniform(0.75, 1.0))
    al = (a > 0.3).astype(float)
    shade = 0.62 + 0.38 * g * (1 - 0.35 * yy)
    out = np.dstack([shade, shade, shade, al])
    return Image.fromarray((np.clip(out, 0, 1) * 255).astype(np.uint8), "RGBA")


def facial_hair_cards(ap, lib, Vm, seed=5):
    """strand cards for moustache / goatee / beard in base space (dm) -> (X (n,3), F, UV, base triangle verts (n,3),
    barycentrics (n,3)) - mapped onto the template like any fitted asset"""
    kind = ap.facial_hair
    if kind not in ("moustache", "goatee", "beard"):
        return None
    Vb, Fb, _ = lib.base()
    rng = np.random.default_rng(seed)
    L = _landmarks(lib, Vb)
    head = (Vb[Fb].mean(1)[:, 1] > 6.1) & (np.abs(Vb[Fb].mean(1)[:, 0]) < 1.0) & (Vb[Fb].mean(1)[:, 2] > 0.4)
    T = Fb[head]
    A = 0.5 * np.linalg.norm(np.cross(Vm[T[:, 1]] - Vm[T[:, 0]], Vm[T[:, 2]] - Vm[T[:, 0]]), axis=1)
    n_cand = 60000
    ti = rng.choice(len(T), n_cand, p=A / A.sum())
    r1, r2 = rng.random(n_cand), rng.random(n_cand)
    sq = np.sqrt(r1)
    bc = np.stack([1 - sq, sq * (1 - r2), sq * r2], 1)
    tri = T[ti]
    Pr = (Vb[tri] * bc[..., None]).sum(1); Pm = (Vm[tri] * bc[..., None]).sum(1)
    z = facial_zones(Pr, L)
    if kind == "moustache":
        dens = z["mous"]; per = 0.020
    elif kind == "goatee":
        dens = np.maximum(z["mous"], z["chin"] * (1 - z["lips"])); per = 0.028
    else:
        dens = np.maximum(z["face"] * (1 - z["lips"]), z["mous"]); per = 0.095
    dens = np.where(dens > 0.35, dens, 0.0)                     # strays outside the zone: the shell softens the edge
    keep = rng.random(n_cand) < dens * per / max(dens.mean() + 1e-6, 0.02) * 0.30
    Pm, tri, bc, Pr, dens = Pm[keep], tri[keep], bc[keep], Pr[keep], dens[keep]
    fn = np.cross(Vm[tri[:, 1]] - Vm[tri[:, 0]], Vm[tri[:, 2]] - Vm[tri[:, 0]])
    n = fn / (np.linalg.norm(fn, axis=1, keepdims=True) + 1e-12)
    outward = np.sign(((Pm - np.array([0, 6.9, 0.2])) * n).sum(1))[:, None]
    n = n * np.where(outward == 0, 1, outward)
    on_lip = z["mous"][keep] > 0.3 if kind != "beard" else (z["mous"][keep] > 0.3)
    f0 = np.tile(np.array([0.0, -1.0, 0.18]), (len(Pm), 1))
    f0[on_lip] = np.stack([np.sign(Pr[on_lip, 0]) * 0.55, -np.ones(on_lip.sum()), 0.25 * np.ones(on_lip.sum())], 1)
    f = f0 - n * (f0 * n).sum(1, keepdims=True); f /= np.linalg.norm(f, axis=1, keepdims=True) + 1e-12
    b = np.cross(n, f)
    edge = _ss(0.35, 0.8, dens)                                  # shorter towards the edge of the beard
    Ln = np.where(on_lip, rng.uniform(0.07, 0.10, len(Pm)), rng.uniform(0.08, 0.13, len(Pm)) * (1.05 if kind == "beard" else 1.0))
    Ln = Ln * (0.45 + 0.55 * edge)
    Wd = (0.07 if kind == "beard" else 0.05) * (0.8 + 0.4 * rng.random(len(Pm)))
    root = Pm + n * 0.004
    tip = root + f * Ln[:, None] + n * (Ln * 0.12)[:, None]
    Nsurf = np.tile(n, (4, 1))
    X = np.concatenate([root - b * (Wd / 2)[:, None], root + b * (Wd / 2)[:, None],
                        tip + b * (Wd * 0.3)[:, None], tip - b * (Wd * 0.3)[:, None]])
    k = len(Pm); i = np.arange(k)
    # wound so the face normal points out of the skin (engines cull back faces)
    F = np.concatenate([np.stack([i, i + 2 * k, i + k], 1), np.stack([i, i + 3 * k, i + 2 * k], 1)])
    UV = np.concatenate([np.stack([np.zeros(k), np.ones(k)], 1), np.stack([np.ones(k), np.ones(k)], 1),
                         np.stack([np.ones(k), np.zeros(k)], 1), np.stack([np.zeros(k), np.zeros(k)], 1)])
    return X, F, UV, np.tile(tri, (4, 1)), np.tile(bc, (4, 1)), Nsurf


def shell_texture(size=256, strands=420, seed=11):
    """tileable fine-strand texture for the beard shell: alpha = strand strength (0.5..1), so lowering the vertex
    alpha thins the beard strand by strand instead of cutting it off"""
    rng = np.random.default_rng(seed)
    a = np.zeros((size, size)); g = np.zeros((size, size))
    yy, xx = np.mgrid[0:size, 0:size]
    for _ in range(strands):
        x0, y0 = rng.uniform(0, size, 2); ln = rng.uniform(0.18, 0.45) * size; w = rng.uniform(1.1, 2.2)
        bend = rng.uniform(-0.12, 0.12); st = rng.uniform(0.5, 1.0)
        t = np.mod(yy - y0, size) / ln                                    # 0 at the root, 1 at the tip (wraps)
        xs = x0 + bend * ln * t ** 2
        dx = np.mod(xx - xs + size / 2, size) - size / 2
        prof = np.clip(1 - (dx / (w * (1 - 0.6 * t))) ** 2, 0, 1) * (t <= 1)
        a = np.maximum(a, prof * st); g = np.maximum(g, prof * rng.uniform(0.7, 1.0))
    al = np.where(a > 0.25, 0.15 + 0.85 * a, 0)
    shade = 0.58 + 0.42 * g
    out = np.dstack([shade, shade, shade, al])
    return Image.fromarray((np.clip(out, 0, 1) * 255).astype(np.uint8), "RGBA")


def facial_hair_shell(ap, lib, Vm, offsets=(0.018, 0.04)):
    """beard / moustache / goatee base: copies of the face surface lifted off the skin, textured with fine strands,
    alpha = growth density (soft edge).  -> list of (X (n,3) dm, F, UV, base vertex (n,), alpha (n,), N)"""
    kind = ap.facial_hair
    if kind not in ("moustache", "goatee", "beard"):
        return []
    Vb, Fb, _ = lib.base()
    L = _landmarks(lib, Vb)
    z = facial_zones(Vb, L)
    if kind == "moustache":
        dens = z["mous"]
    elif kind == "goatee":
        dens = np.maximum(z["mous"], z["chin"] * (1 - z["lips"]))
    else:
        dens = np.maximum(z["face"] * (1 - z["lips"]), z["mous"])
    sel = (dens[Fb] > 0.02).any(1) & (Vb[Fb][:, :, 1].min(1) > 5.8)
    F0 = Fb[sel]
    used = np.unique(F0)
    remap = -np.ones(len(Vb), np.int64); remap[used] = np.arange(len(used))
    F = remap[F0]
    N = normals(Vm, Fb)[used]
    c = np.array([0.0, 6.9, 0.3])
    flip = ((Vm[used] - c) * N).sum(1) < 0
    N[flip] *= -1
    P0 = Vb[used]
    u = np.arctan2(P0[:, 0], P0[:, 2] - 0.3) * 0.9 * 4.0                # ~4 tiles per dm around the face
    v = -P0[:, 1] * 4.0
    UV = np.stack([u, v], 1)
    out = []
    for k, off in enumerate(offsets):
        jit = np.random.default_rng(3 + k).uniform(0.8, 1.0, len(used))
        a = np.clip(_ss(0.0, 0.9, dens[used]) ** 0.8 * jit, 0, 1) * (1.0 if k == 0 else 0.85)
        X = Vm[used] + N * off * (0.55 + 0.45 * _ss(0.2, 0.9, dens[used]))[:, None]   # thinner at the edge
        out.append((X, F, UV + k * 0.37, used, a, N))
    return out


def paint_skin(tm, ap, lib, Vm, res=1024):
    """MakeHuman skin texture + facial hair, stubble, buzz cut / receding scalp, optional tint"""
    im = Image.open(lib.skin(ap.skin)).convert("RGB").resize((res, res), Image.LANCZOS)
    img = np.asarray(im).astype(np.float32) / 255
    tint = ap.rgb("skin_tint")
    if tint is not None:
        img = img * (np.array(tint) / max(np.mean(tint), 1e-3) * 0.25 + 0.75)
    Vb = lib.base()[0]
    fh, hs, hl = ap.facial_hair, ap.hair_style, float(ap.hairline)
    if fh == "none" and hs == "bald" and hl < 0.05:
        return Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8), "RGB")
    tid, bc = raster_base_uv(tm, res)
    idx = np.nonzero(tid >= 0)
    bv = tm.base_of[tm.F[tid[idx]]]
    P = (Vb[bv] * bc[idx][..., None]).sum(1)                # base rest positions of the texels (dm)
    L = _landmarks(lib, Vb)
    hair_rgb = np.array(ap.rgb("hair_colour")); fh_rgb = np.array(ap.rgb("facial_hair_colour"))
    col = img[idx]
    x, y, z = P[:, 0], P[:, 1], P[:, 2]
    ax = np.abs(x)
    ss = _ss
    ch_ = L["chin"]
    # strand noise in texture space (fine, random, slightly streaked) - no visible pattern
    rng = np.random.default_rng(7)
    from scipy.ndimage import gaussian_filter
    nz = gaussian_filter(rng.random((res, res)).astype(np.float32), (1.1, 0.5))
    nz = (nz - nz.mean()) / (nz.std() + 1e-6)
    n = nz[idx]
    dots = gaussian_filter((rng.random((res, res)) > 0.5).astype(np.float32), 0.6)[idx]
    z_ = facial_zones(P, L)
    face, lips, mous, chin = z_["face"], z_["lips"], z_["mous"], z_["chin"]
    fh = ap.facial_hair
    dens = np.zeros(len(P))
    if fh == "stubble":                                  # short growth: a soft, even shadow with fine grain
        dens = (face * (1 - lips) * 0.42 + mous * 0.38) * (0.65 + 0.35 * dots)
    elif fh == "moustache":                              # strand cards carry the moustache; skin gets its shadow
        dens = np.maximum(mous * 0.55, face * (1 - lips) * 0.16 * (0.6 + 0.4 * dots))
    elif fh == "goatee":
        dens = np.maximum(np.maximum(mous, chin * (1 - lips)) * 0.55, face * (1 - lips) * 0.16 * (0.6 + 0.4 * dots))
    elif fh == "beard":
        dens = np.maximum(face * (1 - lips) * 0.85, mous * 0.7) * (0.85 + 0.15 * n)
    a = np.clip(dens, 0, 1)[:, None]
    shade = (0.75 + 0.25 * np.clip(n, -2, 2)[:, None] * 0.5)
    col = col * (1 - a) + fh_rgb * shade * a
    # ---- scalp: buzz cut over the whole scalp, or a faint shaved shadow where a receding hairline left skin
    c_, r_ = _head_frame(Vb)
    d = P - c_; u = d / np.maximum(np.linalg.norm(d, axis=1, keepdims=True), 1e-9)
    scalp = ss(0.70 * r_, 0.80 * r_, np.linalg.norm(d, axis=1)) * ss(-0.35, -0.15, u[:, 1] + 0.25 * np.clip(-u[:, 2], 0, 1)) * \
        (1 - ss(0.25, 0.45, u[:, 2]) * (1 - ss(0.25, 0.45, u[:, 1])))
    ear_zone = 1 - ss(0.12, 0.2, np.sqrt((ax - 0.75) ** 2 + ((y - 7.12) / 1.5) ** 2))
    scalp = scalp * (1 - ear_zone)
    keep = hair_mask(P, float(ap.hairline), Vb)
    hs = ap.hair_style
    if hs == "buzz":
        sd = scalp * keep * (0.62 + 0.25 * dots + 0.08 * n)
        col = col * (1 - sd[:, None]) + hair_rgb * 0.9 * sd[:, None]
    elif hs != "bald":
        # hair colour under the hair: no skin-coloured gaps.  Scalp plus wherever the fitted hair lies close to the
        # skin (long hair over the neck, a fringe over the forehead), thinned with the hairline like the hair itself
        from scipy.spatial import cKDTree
        Xh = lib.proxy("hair", hs).fit(Vb)
        dist, _ = cKDTree(Xh).query(P, distance_upper_bound=0.4)
        near = 1 - ss(0.07, 0.2, np.minimum(dist, 0.4))
        under = np.clip(np.maximum(scalp, near * 0.85) * keep * 1.15, 0, 1)
        col = col * (1 - under[:, None]) + hair_rgb * 0.85 * under[:, None]
        shadow = scalp * (1 - keep) * 0.18 * dots                   # receding: faint shaved shadow
        col = col * (1 - shadow[:, None]) + hair_rgb * shadow[:, None]
    out = img.copy(); out[idx] = np.clip(col, 0, 1)
    return Image.fromarray((np.clip(out, 0, 1) * 255).astype(np.uint8), "RGB")


# ------------------------------------------------------------------ kit textures (atlas: left = jersey/socks/boots, right = shorts)
def kit_uv(gname, UV):
    UV = UV.copy()
    UV[:, 0] = UV[:, 0] * 0.5 + (0.5 if gname == "shorts" else 0.0)
    return UV


def kit_textures(tm: Template, kits, paints_for, res=1024):
    """kits: names; paints_for(kit) -> {"jersey","shorts","socks","boots"} paint functions in template space.
    -> {kit: PIL image (2*res x res)}"""
    tid, bc = raster_base_uv(tm, res)
    idx = np.nonzero(tid >= 0)
    P = (tm.P[tm.F[tid[idx]]] * bc[idx][..., None]).sum(1)
    member = {}
    for gname, faces, _ in garment_faces(tm, tm.P):
        m = np.zeros(len(tm.F), bool); m[faces] = True; member[gname] = m[tid[idx]]
    out = {}
    from .gamemesh import dilate
    for kit in kits:
        pf = paints_for(kit)
        halves = []
        for side in ("left", "right"):
            img = np.zeros((res, res, 3)); valid = np.zeros((res, res), bool)
            order = ("boots", "socks", "jersey") if side == "left" else ("shorts",)
            col = np.zeros((len(P), 3)); have = np.zeros(len(P), bool)
            for g in order:
                sel = member[g] & ~have if side == "left" else member[g]
                if sel.any():
                    c, _ = pf[g].fn(P[sel], np.zeros((sel.sum(), 3)))
                    col[sel] = c; have |= sel
            img[idx[0][have], idx[1][have]] = np.clip(col[have], 0, 1); valid[idx[0][have], idx[1][have]] = True
            # gentle cloth shading baked in: darker toward garment folds is left to the engine; add weave noise
            if valid.any():
                img = dilate(img, valid)
            halves.append(img)
        both = np.concatenate(halves, 1)
        out[kit] = Image.fromarray((both * 255 + 0.5).astype(np.uint8), "RGB")
    return out

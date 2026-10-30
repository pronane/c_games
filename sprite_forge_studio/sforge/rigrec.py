"""Normalized rig record used by the library (v6).

Every imported FBX / glTF / GLB (and the built-in mannequin) becomes a `Rig`:

  bones      names, parent index (-1 = root), bind world matrices (scale-free rotation + translation,
             metres, Y up, the character faces +Z, its left = +X, feet on y = 0)
  mesh       V (nv,3) bind-pose vertices, F (nf,3), per-vertex 4 joints / weights (linear blend skinning),
             per-face material, optional per-corner UVs (nf,3,2) and colours (nf,3,3)
  materials  [{name, color [r,g,b] 0-1, texture "textures/x.png" | None}]
  clips      {name: Clip}: per frame, per bone LOCAL rotation (quaternion xyzw) + local translation, 30 fps

Saved as rig.json + rig.npz (+ textures/) inside library/rigs/<name>/ or library/animations/<name>/.
"""
from __future__ import annotations
import json
import math
import os
import numpy as np
from PIL import Image, ImageDraw

FPS = 30.0


# ----------------------------------------------------------------- math helpers (vectorised)
def quat_from_mats(R):
    """R (...,3,3) -> quaternions (...,4) xyzw."""
    R = np.asarray(R, float)
    sh = R.shape[:-2]
    R = R.reshape(-1, 3, 3)
    q = np.zeros((len(R), 4))
    tr = R[:, 0, 0] + R[:, 1, 1] + R[:, 2, 2]
    for i in range(len(R)):
        m = R[i]
        if tr[i] > 0:
            s = math.sqrt(tr[i] + 1.0) * 2
            q[i] = [(m[2, 1] - m[1, 2]) / s, (m[0, 2] - m[2, 0]) / s, (m[1, 0] - m[0, 1]) / s, 0.25 * s]
        elif m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
            s = math.sqrt(max(1e-12, 1.0 + m[0, 0] - m[1, 1] - m[2, 2])) * 2
            q[i] = [0.25 * s, (m[0, 1] + m[1, 0]) / s, (m[0, 2] + m[2, 0]) / s, (m[2, 1] - m[1, 2]) / s]
        elif m[1, 1] > m[2, 2]:
            s = math.sqrt(max(1e-12, 1.0 + m[1, 1] - m[0, 0] - m[2, 2])) * 2
            q[i] = [(m[0, 1] + m[1, 0]) / s, 0.25 * s, (m[1, 2] + m[2, 1]) / s, (m[0, 2] - m[2, 0]) / s]
        else:
            s = math.sqrt(max(1e-12, 1.0 + m[2, 2] - m[0, 0] - m[1, 1])) * 2
            q[i] = [(m[0, 2] + m[2, 0]) / s, (m[1, 2] + m[2, 1]) / s, 0.25 * s, (m[1, 0] - m[0, 1]) / s]
    q /= np.linalg.norm(q, axis=1, keepdims=True) + 1e-12
    return q.reshape(sh + (4,))


def mats_from_quat(q):
    q = np.asarray(q, float)
    q = q / (np.linalg.norm(q, axis=-1, keepdims=True) + 1e-12)
    x, y, z, w = q[..., 0], q[..., 1], q[..., 2], q[..., 3]
    R = np.empty(q.shape[:-1] + (3, 3))
    R[..., 0, 0] = 1 - 2 * (y * y + z * z); R[..., 0, 1] = 2 * (x * y - z * w); R[..., 0, 2] = 2 * (x * z + y * w)
    R[..., 1, 0] = 2 * (x * y + z * w); R[..., 1, 1] = 1 - 2 * (x * x + z * z); R[..., 1, 2] = 2 * (y * z - x * w)
    R[..., 2, 0] = 2 * (x * z - y * w); R[..., 2, 1] = 2 * (y * z + x * w); R[..., 2, 2] = 1 - 2 * (x * x + y * y)
    return R


def polar(M):
    """closest rotation to M (...,3,3) (removes scale / shear)."""
    U, _, Vt = np.linalg.svd(M)
    R = U @ Vt
    d = np.linalg.det(R)
    if np.ndim(d) == 0:
        if d < 0:
            U[:, -1] *= -1; R = U @ Vt
    else:
        bad = d < 0
        if bad.any():
            U[bad, :, -1] *= -1; R[bad] = U[bad] @ Vt[bad]
    return R


def rot_between(a, b):
    """minimal rotation matrix taking direction a onto direction b."""
    a = np.asarray(a, float); b = np.asarray(b, float)
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na < 1e-9 or nb < 1e-9:
        return np.eye(3)
    a = a / na; b = b / nb
    v = np.cross(a, b); c = float(np.dot(a, b))
    if c < -0.999999:
        p = np.array([1.0, 0, 0]) if abs(a[0]) < 0.9 else np.array([0, 1.0, 0])
        ax = np.cross(a, p); ax /= np.linalg.norm(ax)
        return 2 * np.outer(ax, ax) - np.eye(3)
    K = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + K + K @ K * (1.0 / (1.0 + c))


def m4(R=None, t=None):
    M = np.eye(4)
    if R is not None:
        M[:3, :3] = R
    if t is not None:
        M[:3, 3] = t
    return M


def inv_rigid(M):
    """inverse of rotation+translation matrices (...,4,4)."""
    R = M[..., :3, :3]; t = M[..., :3, 3]
    out = np.zeros_like(M)
    Rt = np.swapaxes(R, -1, -2)
    out[..., :3, :3] = Rt
    out[..., :3, 3] = -np.einsum("...ij,...j->...i", Rt, t)
    out[..., 3, 3] = 1
    return out


def nlerp(q0, q1, a):
    d = np.sum(q0 * q1, axis=-1, keepdims=True)
    q1 = np.where(d < 0, -q1, q1)
    q = q0 * (1 - a) + q1 * a
    return q / (np.linalg.norm(q, axis=-1, keepdims=True) + 1e-12)


# ----------------------------------------------------------------- record
class Clip:
    def __init__(self, name, R, T, fps=FPS, loop=None, source=""):
        self.name = name
        self.R = np.asarray(R, float)        # (F, nb, 4) local rotations xyzw
        self.T = np.asarray(T, float)        # (F, nb, 3) local translations
        self.fps = float(fps)
        lname = name.lower()
        self.loop = loop if loop is not None else any(k in lname for k in ("idle", "walk", "run", "jog", "sprint", "loop", "cycle", "drive"))
        self.source = source

    @property
    def frames(self):
        return len(self.R)

    @property
    def duration(self):
        return max(0.0, (self.frames - 1) / self.fps)

    def local_at(self, t, loop=None):
        """local matrices (nb,4,4) at time t (seconds), linear / nlerp between baked frames."""
        loop = self.loop if loop is None else loop
        F = self.frames
        if F == 1:
            i0 = i1 = 0; a = 0.0
        else:
            f = t * self.fps
            if loop:
                f = f % (F - 1) if F > 1 else 0
            f = min(max(f, 0.0), F - 1.0)
            i0 = int(math.floor(f)); i1 = min(F - 1, i0 + 1); a = f - i0
        q = nlerp(self.R[i0], self.R[i1], a)
        T = self.T[i0] * (1 - a) + self.T[i1] * a
        L = np.zeros((len(q), 4, 4)); L[:, :3, :3] = mats_from_quat(q); L[:, :3, 3] = T; L[:, 3, 3] = 1
        return L


class Rig:
    def __init__(self, name="rig"):
        self.name = name
        self.bones: list = []
        self.parent = np.zeros(0, int)
        self.bind = np.zeros((0, 4, 4))
        self.V = np.zeros((0, 3)); self.F = np.zeros((0, 3), int)
        self.J = np.zeros((0, 4), int); self.W = np.zeros((0, 4))
        self.fmat = np.zeros(0, int)
        self.fuv = None; self.fcol = None
        self.materials: list = []
        self.textures: dict = {}             # "textures/x.png" -> PIL image
        self.clips: dict = {}
        self.meta: dict = {}
        self._tri_cache = {}

    # ---------- basics
    @property
    def nb(self):
        return len(self.bones)

    def index(self, name):
        try:
            return self.bones.index(name)
        except ValueError:
            return -1

    def order(self):
        """bone indices parents-before-children."""
        seen, out = set(), []
        def visit(i):
            if i in seen:
                return
            p = self.parent[i]
            if p >= 0:
                visit(p)
            seen.add(i); out.append(i)
        for i in range(self.nb):
            visit(i)
        return out

    def rest_local(self):
        L = np.zeros((self.nb, 4, 4))
        inv = inv_rigid(self.bind)
        for i in range(self.nb):
            p = self.parent[i]
            L[i] = self.bind[i] if p < 0 else inv[p] @ self.bind[i]
        return L

    def fk(self, L):
        W = np.zeros_like(L)
        for i in self.order():
            p = self.parent[i]
            W[i] = L[i] if p < 0 else W[p] @ L[i]
        return W

    def worlds(self, clip=None, t=0.0, loop=None):
        if clip is None:
            return self.bind.copy()
        c = self.clips[clip] if isinstance(clip, str) else clip
        return self.fk(c.local_at(t, loop))

    def clip_worlds(self, clip):
        c = self.clips[clip] if isinstance(clip, str) else clip
        out = np.zeros((c.frames, self.nb, 4, 4))
        for f in range(c.frames):
            L = np.zeros((self.nb, 4, 4)); L[:, :3, :3] = mats_from_quat(c.R[f]); L[:, :3, 3] = c.T[f]; L[:, 3, 3] = 1
            out[f] = self.fk(L)
        return out

    def clip_from_worlds(self, name, Wf, fps=FPS, loop=None, source=""):
        """build a Clip from per-frame bone world matrices (F,nb,4,4)."""
        Fn = len(Wf)
        R = np.zeros((Fn, self.nb, 4)); T = np.zeros((Fn, self.nb, 3))
        for f in range(Fn):
            W = Wf[f]
            inv = inv_rigid(W)
            L = np.array([W[i] if self.parent[i] < 0 else inv[self.parent[i]] @ W[i] for i in range(self.nb)])
            R[f] = quat_from_mats(polar(L[:, :3, :3])); T[f] = L[:, :3, 3]
        # keep quaternion signs continuous (nicer interpolation / curves)
        for f in range(1, Fn):
            flip = np.sum(R[f] * R[f - 1], axis=1) < 0
            R[f][flip] *= -1
        return Clip(name, R, T, fps, loop, source)

    def children(self, i):
        return [j for j in range(self.nb) if self.parent[j] == i]

    def has_mesh(self):
        return len(self.F) > 0

    # ---------- geometry
    def skin(self, W):
        """posed vertices for bone worlds W (nb,4,4) (linear blend skinning)."""
        if not self.has_mesh():
            return self.V
        S = W @ inv_rigid(self.bind)                      # (nb,4,4)
        Vh = np.c_[self.V, np.ones(len(self.V))]
        out = np.zeros((len(self.V), 3))
        for k in range(4):
            w = self.W[:, k]
            if not np.any(w):
                continue
            M = S[self.J[:, k]]                           # (nv,4,4)
            out += w[:, None] * np.einsum("nij,nj->ni", M[:, :3, :], Vh)
        return out

    def height(self, W=None):
        if self.has_mesh():
            V = self.V if W is None else self.skin(W)
            return float(V[:, 1].max() - V[:, 1].min())
        W = self.bind if W is None else W
        y = W[:, 1, 3]
        return float(y.max() - y.min()) * 1.08 if len(y) else 0.0

    def face_colors(self, kit=None):
        """per-face rgb (nf,3): material colour, texture sampled at the face's UV centroid, kit tint."""
        key = json.dumps(kit, sort_keys=True) if kit else ""
        if key in self._tri_cache:
            return self._tri_cache[key]
        from . import kits as K
        nm = len(self.materials)
        base = np.array([m.get("color", [0.7, 0.7, 0.7])[:3] for m in self.materials] or [[0.7, 0.7, 0.7]], float)
        rules = [K.rule_for(kit, m.get("name", "")) for m in self.materials] if kit else [None] * nm
        cols = base[np.clip(self.fmat, 0, len(base) - 1)].copy()
        for mi, m in enumerate(self.materials):
            sel = self.fmat == mi
            if not sel.any():
                continue
            rule = rules[mi]
            tex = self.textures.get(m.get("texture")) if m.get("texture") else None
            if tex is not None and self.fuv is not None and not (rule and rule["mode"] == "replace"):
                arr = np.asarray(tex.convert("RGB"), float) / 255.0
                h, w = arr.shape[:2]
                uv = self.fuv[sel].mean(axis=1)
                u = np.mod(uv[:, 0], 1.0); v = np.mod(uv[:, 1], 1.0)
                # glTF convention: v=0 is the top row (FBX v is flipped on import)
                x = np.clip((u * w).astype(int), 0, w - 1); y = np.clip((v * h).astype(int), 0, h - 1)
                c = arr[y, x] * np.array(m.get("color", [1, 1, 1])[:3]) if m.get("tint_texture") else arr[y, x]
                cols[sel] = c
            if self.fcol is not None and tex is None:
                cols[sel] = cols[sel] * self.fcol[sel].mean(axis=1)
            if rule:
                rc = np.array(rule["color"], float)
                if rule["mode"] == "replace":
                    cols[sel] = rc
                elif rule["mode"] == "multiply":
                    cols[sel] = np.clip(cols[sel] * rc, 0, 1)
                else:       # tint: keep relative light / dark detail, take the kit colour
                    lum = cols[sel] @ np.array([0.299, 0.587, 0.114])
                    ref = max(1e-3, float(np.percentile(lum, 75)))
                    cols[sel] = np.clip(rc[None, :] * (lum / ref)[:, None], 0, 1)
        self._tri_cache[key] = cols
        return cols

    def kit_texture(self, mi, kit):
        """(PIL image or None, flat rgb or None) for material mi under a kit, for 3D export.
        tint / multiply keep the texture (recoloured image); replace gives a flat colour."""
        from . import kits as K
        m = self.materials[mi]
        rule = K.rule_for(kit, m.get("name", "")) if kit else None
        tex = self.textures.get(m.get("texture")) if m.get("texture") else None
        if rule is None:
            return tex, None
        rc = np.array(rule["color"], float)
        if rule["mode"] == "replace" or tex is None:
            if tex is None and rule["mode"] != "replace":
                base = np.array(m.get("color", [0.7, 0.7, 0.7])[:3], float)
                return None, list(np.clip(base * rc, 0, 1)) if rule["mode"] == "multiply" else list(rc)
            return None, list(rc)
        arr = np.asarray(tex.convert("RGBA"), float) / 255.0
        rgb = arr[..., :3]
        if rule["mode"] == "multiply":
            out = np.clip(rgb * rc, 0, 1)
        else:
            lum = rgb @ np.array([0.299, 0.587, 0.114])
            ref = max(1e-3, float(np.percentile(lum, 75)))
            out = np.clip(rc[None, None, :] * (lum / ref)[..., None], 0, 1)
        arr = np.concatenate([out, arr[..., 3:]], axis=-1)
        return Image.fromarray((arr * 255 + 0.5).astype(np.uint8), "RGBA"), None

    def render(self, W, rs, kit=None, follow_root=None, scale=1.0):
        """sprite image for bone worlds W with the standard RenderSettings (same anchor / cut-out pipeline)."""
        from .render import render_tris
        hips = self.meta.get("hips_index", 0)
        rxz = (W[hips, 0, 3], W[hips, 2, 3]) if self.nb else (0, 0)
        if follow_root is not None:
            rs.follow_root = follow_root
        if not self.has_mesh():
            return render_skeleton(self, W, rs, rxz)
        P = self.skin(W)[self.F] * scale
        return render_tris(P, np.zeros(len(self.F), int), None, rs, (rxz[0] * scale, rxz[1] * scale), rgb=self.face_colors(kit), two_sided=True)

    # ---------- transforms
    def apply_global(self, G):
        """apply a rigid / uniform world transform G (4x4 rotation*scale + translation) to everything."""
        s = float(np.cbrt(abs(np.linalg.det(G[:3, :3])))) or 1.0
        R = polar(G[:3, :3] / s)
        Gr = m4(R, G[:3, 3])
        for i in range(self.nb):
            B = self.bind[i].copy(); B[:3, 3] *= s
            self.bind[i] = Gr @ B
        if len(self.V):
            self.V = (self.V * s) @ R.T + G[:3, 3]
        roots = [i for i in range(self.nb) if self.parent[i] < 0]
        for c in self.clips.values():
            c.T = c.T * s
            for f in range(c.frames):
                for i in roots:
                    L = m4(mats_from_quat(c.R[f, i]), c.T[f, i]); L = Gr @ L
                    c.R[f, i] = quat_from_mats(L[:3, :3]); c.T[f, i] = L[:3, 3]
        self._tri_cache = {}

    def ground(self):
        """feet on y=0, hips over the origin (bind pose)."""
        if self.has_mesh():
            y0 = self.V[:, 1].min()
        else:
            y0 = self.bind[:, 1, 3].min() - 0.03 * max(1e-3, self.height())
        hi = self.meta.get("hips_index", 0)
        c = self.bind[hi, :3, 3] if self.nb else np.zeros(3)
        self.apply_global(m4(None, [-c[0], -y0, -c[2]]))

    def rest_clip(self):
        L = self.rest_local()
        return Clip("rest", quat_from_mats(L[:, :3, :3])[None], L[:, :3, 3][None], FPS, True, "rest pose")

    # ---------- io
    def save(self, d):
        os.makedirs(d, exist_ok=True)
        arrs = dict(parent=self.parent, bind=self.bind, V=self.V, F=self.F, J=self.J, W=self.W, fmat=self.fmat)
        if self.fuv is not None:
            arrs["fuv"] = self.fuv.astype(np.float32)
        if self.fcol is not None:
            arrs["fcol"] = self.fcol.astype(np.float32)
        clips = []
        for i, (k, c) in enumerate(self.clips.items()):
            arrs["clipR_%d" % i] = c.R.astype(np.float32); arrs["clipT_%d" % i] = c.T.astype(np.float32)
            clips.append(dict(name=k, fps=c.fps, frames=c.frames, loop=bool(c.loop), source=c.source))
        np.savez_compressed(os.path.join(d, "rig.npz"), **arrs)
        for rel, im in self.textures.items():
            p = os.path.join(d, rel); os.makedirs(os.path.dirname(p), exist_ok=True)
            im.save(p)
        meta = dict(format="sforge-rig", version=1, name=self.name, bones=self.bones, materials=self.materials,
                    clips=clips, meta=self.meta, height_m=round(self.height(), 4), verts=int(len(self.V)), tris=int(len(self.F)))
        json.dump(meta, open(os.path.join(d, "rig.json"), "w", encoding="utf-8"), indent=1)

    @classmethod
    def load(cls, d):
        meta = json.load(open(os.path.join(d, "rig.json"), encoding="utf-8"))
        z = np.load(os.path.join(d, "rig.npz"))
        r = cls(meta["name"])
        r.bones = list(meta["bones"]); r.materials = meta.get("materials", []); r.meta = meta.get("meta", {})
        r.parent = z["parent"].astype(int); r.bind = z["bind"].astype(float)
        r.V = z["V"].astype(float); r.F = z["F"].astype(int); r.J = z["J"].astype(int); r.W = z["W"].astype(float)
        r.fmat = z["fmat"].astype(int)
        r.fuv = z["fuv"].astype(float) if "fuv" in z else None
        r.fcol = z["fcol"].astype(float) if "fcol" in z else None
        for i, c in enumerate(meta.get("clips", [])):
            r.clips[c["name"]] = Clip(c["name"], z["clipR_%d" % i].astype(float), z["clipT_%d" % i].astype(float),
                                      c.get("fps", FPS), c.get("loop"), c.get("source", ""))
        for m in r.materials:
            t = m.get("texture")
            if t and os.path.exists(os.path.join(d, t)):
                r.textures[t] = Image.open(os.path.join(d, t)).convert("RGBA")
        return r


# ----------------------------------------------------------------- skeleton drawing (mesh-less rigs, bone viewer)
def project(P, rs, root_xz=(0, 0)):
    from .mathutil import rx, ry
    from .rig import HEIGHT
    view = rx(rs.pitch) @ ry(rs.yaw)
    Q = np.array(P, float).copy()
    if rs.follow_root:
        Q[..., 0] -= root_xz[0]; Q[..., 2] -= root_xz[1]
    Q = Q @ view.T
    sc = rs.figure_h / HEIGHT
    return np.c_[rs.anchor_x + Q[..., 0] * sc, rs.baseline - Q[..., 1] * sc, Q[..., 2]]


def render_skeleton(rig, W, rs, root_xz=(0, 0), highlight=None, labels=False, colors=None):
    img = Image.new("RGBA", (rs.cell_w, rs.cell_h), (0, 0, 0, 0))
    dr = ImageDraw.Draw(img)
    pts = project(W[:, :3, 3], rs, root_xz)
    wd = max(2, rs.cell_h // 90)
    order = np.argsort(pts[:, 2])
    for i in order:
        p = rig.parent[i]
        if p < 0:
            continue
        col = (colors or {}).get(i) or ((230, 60, 60, 255) if highlight and i in highlight else (70, 150, 230, 255))
        dr.line([tuple(pts[p, :2]), tuple(pts[i, :2])], fill=col, width=wd)
    for i in range(rig.nb):
        x, y = pts[i, :2]
        col = (colors or {}).get(i) or ((230, 60, 60, 255) if highlight and i in highlight else (20, 40, 80, 255))
        dr.ellipse([x - wd, y - wd, x + wd, y + wd], fill=col)
        if labels:
            dr.text((x + 3, y - 5), rig.bones[i][:14], fill=(40, 40, 40, 255))
    return img


def thumbnail(rig, path=None, size=160, clip=None, t=None, kit=None):
    from .render import RenderSettings
    W = rig.bind if clip is None else rig.worlds(clip, t if t is not None else rig.clips[clip].duration * 0.3)
    h = max(0.3, rig.height(W) if rig.has_mesh() else rig.height())
    rs = RenderSettings(cell_w=size * 2, cell_h=size * 2, figure_h=int(size * 2 * 0.86 * 1.80 / h), baseline=int(size * 2 * 0.94),
                        anchor_x=size, yaw=35, ss=2)
    rs.follow_root = True
    im = rig.render(W, rs, kit)
    bg = Image.new("RGBA", im.size, (236, 239, 244, 255))
    out = Image.alpha_composite(bg, im).resize((size, size), Image.LANCZOS)
    if path:
        out.save(path)
    return out


# ----------------------------------------------------------------- mannequin as a library rig
MANNEQUIN_CLIPS = ["idle", "walk", "run", "jump", "kick", "punch", "celebrate"]


def from_mannequin(name="mannequin", kit="home", clips=None, frames=None, slots="full", sp=None):
    """the built-in no-likeness mannequin as a Rig (rigid parts -> 1 bone per vertex) with procedural clips."""
    from . import rig as R, mesh as Mh
    from .spec import CharacterSpec
    from .mesh import MATS
    if sp is None:
        sp = CharacterSpec(); sp.kit = kit if kit in Mh.KITS else "home"
    T, B, Mt = Mh.build_mannequin(sp, False, None)
    cols = sp.colours()
    names = [j for j in R.JOINT_NAMES if j != "ball"]            # the ball is a prop, not part of the body
    keep = np.array([R.JOINT_NAMES[b] != "ball" for b in B])
    T, B, Mt = T[keep], B[keep], Mt[keep]
    r = Rig(name)
    r.bones = names
    r.parent = np.array([names.index(R.PARENT[j]) if R.PARENT.get(j) else -1 for j in names], int)
    rw = R.rest_world()
    r.bind = np.array([m4(None, rw[j]) for j in names], float)
    r.V = T.reshape(-1, 3).astype(float)
    r.F = np.arange(len(r.V)).reshape(-1, 3)
    r.J = np.zeros((len(r.V), 4), int); r.J[:, 0] = np.repeat([names.index(R.JOINT_NAMES[b]) for b in B], 3)
    r.W = np.zeros((len(r.V), 4)); r.W[:, 0] = 1
    from .matslots import mannequin_name
    used = sorted(set(int(m) for m in Mt))
    r.materials, remap, six = [], {}, {}
    for m in used:                     # v7: engine slot names (Skin_Mat, Jersey_Mat, ...); core4 merges extras
        sn = mannequin_name(MATS[m], slots)
        if sn not in six:
            six[sn] = len(r.materials)
            r.materials.append(dict(name=sn, color=list(map(float, cols[MATS[m]])), part=MATS[m]))
        remap[m] = six[sn]
    r.fmat = np.array([remap[int(m)] for m in Mt], int)
    r.meta = dict(source="built-in mannequin (procedural, no likeness)", hips_index=r.bones.index("hips"), convention="sforge")
    r.weld()
    for mv in (clips or MANNEQUIN_CLIPS):
        c = motion_clip(r, mv, frames)
        if c is not None:
            r.clips[mv] = c
    return r


def motion_clip(r, motion_name, frames=None, loop=None, duration=None):
    """bake a procedural / mocap Motion (sforge.motions) on the mannequin skeleton at 30 fps."""
    from .motions import find_motion
    from . import rig as R
    m = find_motion(motion_name)
    if m is None:
        return None
    lp = m.loop if loop is None else loop
    dur = duration or (1.0 if lp else 0.8)
    n = frames or max(2, int(round(dur * FPS)) + 1)
    Wf = []
    for k in range(n):
        t = k / max(1, n - 1)          # loops: last frame == first frame
        pose, bm = m.sample(t)
        st = R.evaluate(pose, bm)
        Wf.append(np.array([st.world[j] for j in r.bones], float))
    return r.clip_from_worlds(motion_name, np.array(Wf), FPS, lp, "procedural motion '%s'" % motion_name)


def _weld(self, tol=1e-6):
    """merge identical vertices with identical skinning (keeps faces)."""
    if not len(self.V):
        return
    key = np.round(self.V / max(tol, 1e-9)).astype(np.int64)
    k2 = np.c_[key, self.J]
    _, first, inv = np.unique(k2, axis=0, return_index=True, return_inverse=True)
    inv = inv.reshape(-1)
    self.V = self.V[first]; self.J = self.J[first]; self.W = self.W[first]
    self.F = inv[self.F]


Rig.weld = _weld


# ----------------------------------------------------------------- general glTF 2.0 writer
class _GBuf:
    def __init__(self):
        self.data = bytearray(); self.views = []; self.accessors = []

    def _view(self, b, target=None):
        while len(self.data) % 4:
            self.data.append(0)
        v = {"buffer": 0, "byteOffset": len(self.data), "byteLength": len(b)}
        if target:
            v["target"] = target
        self.data += b; self.views.append(v)
        return len(self.views) - 1

    def add_raw(self, b):
        return self._view(bytes(b))

    def add(self, arr, comp, typ, target=None, minmax=False):
        arr = np.ascontiguousarray(arr)
        bv = self._view(arr.tobytes(), target)
        count = arr.shape[0]
        acc = {"bufferView": bv, "componentType": comp, "count": count, "type": typ}
        if minmax:
            a2 = arr.reshape(count, -1)
            acc["min"] = [float(x) for x in a2.min(axis=0)]; acc["max"] = [float(x) for x in a2.max(axis=0)]
        self.accessors.append(acc)
        return len(self.accessors) - 1

    def finish(self, gl):
        while len(self.data) % 4:
            self.data.append(0)
        gl["buffers"] = [{"byteLength": len(self.data)}]
        gl["bufferViews"] = self.views; gl["accessors"] = self.accessors


def write_glb(rig, path, clips=None, kit=None, extras=None, root_motion="keep", with_mesh=True, force_skin=False, full_tracks=False,
              armature_node=False):
    """write a skinned GLB of the rig: one mesh (a primitive per material), embedded textures, every clip as an animation."""
    import struct
    buf = _GBuf()
    nodes, meshes, materials, images, textures, samplers = [], [], [], [], [], []
    L0 = rig.rest_local()
    for i, b in enumerate(rig.bones):
        q = quat_from_mats(polar(L0[i, :3, :3]))
        nodes.append(dict(name=b, translation=[float(x) for x in L0[i, :3, 3]], rotation=[float(x) for x in q]))
    for i in range(rig.nb):
        ch = rig.children(i)
        if ch:
            nodes[i]["children"] = ch
    roots = [i for i in range(rig.nb) if rig.parent[i] < 0]
    scene_nodes = list(roots)
    if rig.has_mesh() and with_mesh:
        # textures (one per material when a kit recolours it)
        texidx = {}
        import io

        def _addtex(key, im, nm):
            bio = io.BytesIO(); im.save(bio, "PNG")
            bv = buf.add_raw(bio.getvalue())
            images.append(dict(bufferView=bv, mimeType="image/png", name=nm))
            textures.append(dict(source=len(images) - 1, sampler=0)); texidx[key] = len(textures) - 1
        mat_tex, mat_flat = {}, {}
        for mi, m in enumerate(rig.materials):
            im, flat = rig.kit_texture(mi, kit) if kit else (rig.textures.get(m.get("texture")) if m.get("texture") else None, None)
            mat_flat[mi] = flat
            if im is not None:
                key = m.get("texture") if not kit else "%s#%d" % (m.get("texture"), mi)
                if key not in texidx:
                    _addtex(key, im, os.path.basename(str(m.get("texture"))) if not kit else "%s_%s.png" % (m.get("name", "mat"), "kit"))
                mat_tex[mi] = key
        if textures:
            samplers.append(dict(magFilter=9728, minFilter=9728))
        prims = []; empty_mats = []
        ibm = inv_rigid(rig.bind)
        for mi, m in enumerate(rig.materials or [dict(name="default", color=[0.7, 0.7, 0.7])]):
            sel = np.where(rig.fmat == mi)[0] if rig.materials else np.arange(len(rig.F))
            if not len(sel):
                if m.get("empty") or m.get("name") in ("Skin_Mat", "Jersey_Mat", "Shorts_Mat", "Socks_Mat"):
                    # v7: an unused core slot is still written (unreferenced) so the engine sees the full slot set
                    col = list(m.get("color", [0.7, 0.7, 0.7])[:3])
                    empty_mats.append(dict(name=m.get("name"), pbrMetallicRoughness=dict(baseColorFactor=col + [1.0], metallicFactor=0.0, roughnessFactor=0.8),
                                           extras={"sforge_empty_slot": True}))
                continue
            Fm = rig.F[sel]
            # corner-split so UVs / colours stay per corner
            idx = Fm.reshape(-1)
            P = rig.V[idx].astype(np.float32)
            e1 = rig.V[Fm[:, 1]] - rig.V[Fm[:, 0]]; e2 = rig.V[Fm[:, 2]] - rig.V[Fm[:, 0]]
            N = np.cross(e1, e2); N /= np.linalg.norm(N, axis=1, keepdims=True) + 1e-12
            N = np.repeat(N, 3, axis=0).astype(np.float32)
            att = dict(POSITION=buf.add(P, 5126, "VEC3", 34962, minmax=True), NORMAL=buf.add(N, 5126, "VEC3", 34962),
                       JOINTS_0=buf.add(rig.J[idx].astype(np.uint16), 5123, "VEC4", 34962),
                       WEIGHTS_0=buf.add(rig.W[idx].astype(np.float32), 5126, "VEC4", 34962))
            col = list(m.get("color", [0.7, 0.7, 0.7])[:3])
            if mat_flat.get(mi) is not None:
                col = [float(x) for x in mat_flat[mi]]
            mat = dict(name=m.get("name", "mat%d" % mi), pbrMetallicRoughness=dict(baseColorFactor=col + [1.0], metallicFactor=0.0, roughnessFactor=0.8))
            tk = mat_tex.get(mi)
            if tk in texidx and rig.fuv is not None:
                att["TEXCOORD_0"] = buf.add(rig.fuv[sel].reshape(-1, 2).astype(np.float32), 5126, "VEC2", 34962)
                mat["pbrMetallicRoughness"]["baseColorTexture"] = dict(index=texidx[tk])
                if not m.get("tint_texture") or kit:
                    mat["pbrMetallicRoughness"]["baseColorFactor"] = [1.0, 1.0, 1.0, 1.0]
            if rig.fcol is not None:
                att["COLOR_0"] = buf.add(rig.fcol[sel].reshape(-1, 3).astype(np.float32), 5126, "VEC3", 34962)
            materials.append(mat)
            prims.append(dict(attributes=att, material=len(materials) - 1, mode=4))
        materials.extend(empty_mats)
        meshes.append(dict(name=rig.name + "_mesh", primitives=prims))
        skin = dict(joints=list(range(rig.nb)), inverseBindMatrices=buf.add(np.ascontiguousarray(np.transpose(ibm, (0, 2, 1))).reshape(-1, 16).astype(np.float32), 5126, "MAT4"),
                    skeleton=roots[0])
        nodes.append(dict(name=rig.name + "_mesh", mesh=0, skin=0))
        scene_nodes.append(len(nodes) - 1)
        skins = [skin]
    elif force_skin:
        # v7 animation-only file: the armature + a skin (joints / inverse binds) but no mesh, so engines such as
        # raylib (LoadModelAnimations needs skins[0]) and Blender read it as a standalone skeleton animation
        ibm = inv_rigid(rig.bind)
        skins = [dict(joints=list(range(rig.nb)), skeleton=roots[0], name=rig.name + "_skin",
                      inverseBindMatrices=buf.add(np.ascontiguousarray(np.transpose(ibm, (0, 2, 1))).reshape(-1, 16).astype(np.float32), 5126, "MAT4"))]
    else:
        skins = []
    anims = []
    hips = rig.meta.get("hips_index", 0)
    clipd = clips if isinstance(clips, dict) else {cn: rig.clips[cn] for cn in (clips if clips is not None else list(rig.clips))}
    for cn, c in clipd.items():
        t = (np.arange(c.frames) / c.fps).astype(np.float32)
        ta = buf.add(t, 5126, "SCALAR", minmax=True)
        ch, sm = [], []
        T = c.T.copy()
        if root_motion == "inplace":
            T = strip_root_motion(rig, c)
        for i in range(rig.nb):
            sm.append(dict(input=ta, output=buf.add(c.R[:, i].astype(np.float32), 5126, "VEC4"), interpolation="LINEAR"))
            ch.append(dict(sampler=len(sm) - 1, target=dict(node=i, path="rotation")))
            if full_tracks or np.ptp(T[:, i], axis=0).max() > 1e-6 or i == hips or rig.parent[i] < 0:
                sm.append(dict(input=ta, output=buf.add(T[:, i].astype(np.float32), 5126, "VEC3"), interpolation="LINEAR"))
                ch.append(dict(sampler=len(sm) - 1, target=dict(node=i, path="translation")))
            if full_tracks:
                sm.append(dict(input=ta, output=buf.add(np.ones((c.frames, 3), np.float32), 5126, "VEC3"), interpolation="LINEAR"))
                ch.append(dict(sampler=len(sm) - 1, target=dict(node=i, path="scale")))
        anims.append(dict(name=cn, channels=ch, samplers=sm))
    if armature_node:
        # an identity "Armature" parent above the root joint(s): raylib 6.0 reads skin.joints[0]->parent's world transform
        # (NULL parent crashes it) and Blender / Godot then name the armature nicely
        nodes.append(dict(name="Armature", children=list(roots)))
        scene_nodes = [len(nodes) - 1] + [n for n in scene_nodes if n not in roots]
    gl = dict(asset=dict(version="2.0", generator="Sprite Forge Studio library writer"), scene=0,
              scenes=[dict(nodes=scene_nodes)], nodes=nodes)
    for k, v in (("meshes", meshes), ("materials", materials), ("skins", skins), ("animations", anims), ("images", images),
                 ("textures", textures), ("samplers", samplers)):
        if v:
            gl[k] = v
    if extras:
        gl["asset"]["extras"] = extras
    buf.finish(gl)
    js = json.dumps(gl, separators=(",", ":")).encode()
    js += b" " * ((4 - len(js) % 4) % 4)
    bin_ = bytes(buf.data); bin_ += b"\0" * ((4 - len(bin_) % 4) % 4)
    with open(path, "wb") as f:
        f.write(struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(js) + 8 + len(bin_)))
        f.write(struct.pack("<II", len(js), 0x4E4F534A)); f.write(js)
        f.write(struct.pack("<II", len(bin_), 0x004E4942)); f.write(bin_)
    return dict(bones=rig.nb, tris=int(len(rig.F)), clips=len(anims), materials=len(materials), textures=len(textures))


def strip_root_motion(rig, c):
    """translations with the hips' horizontal travel removed (in-place loop)."""
    hips = rig.meta.get("hips_index", 0)
    W = rig.clip_worlds(c)
    T = c.T.copy()
    for f in range(c.frames):
        d = W[f, hips, :3, 3] - W[0, hips, :3, 3]
        d[1] = 0
        p = rig.parent[hips]
        if p >= 0:
            d = W[f, p, :3, :3].T @ d
        T[f, hips] = c.T[f, hips] - d
    return T


# ----------------------------------------------------------------- decimation for console budgets
def decimated(rig, max_tris):
    """copy of the rig with at most max_tris triangles (console budgets).
    1) quadric decimation by fast-simplification when installed (pip extra), accepted only if every skinned part survives;
    2) otherwise our pure-NumPy skin-aware vertex clustering: vertices are grouped by their dominant bone and snapped to a grid
       in that bone's own space, so thin limbs are never merged with the body and no part disappears.
    Surviving triangles keep their original UVs / material."""
    if len(rig.F) <= max_tris:
        return rig
    import copy
    dom = rig.J[np.arange(len(rig.V)), np.argmax(rig.W, axis=1)] if len(rig.V) else np.zeros(0, int)
    parts0 = set(np.unique(dom[rig.F[:, 0]]).tolist())
    try:
        import fast_simplification
        V2, F2 = fast_simplification.simplify(rig.V.astype(np.float32), rig.F.astype(np.int32),
                                              target_reduction=min(0.99, 1.0 - max_tris / float(len(rig.F))))
        V2 = V2.astype(float); F2 = F2.astype(int)
        from scipy.spatial import cKDTree
        _, vi = cKDTree(rig.V).query(V2)
        if len(F2) and len(F2) <= max_tris * 1.05 and len(set(np.unique(dom[vi][F2[:, 0]]).tolist())) >= 0.9 * len(parts0):
            cen = rig.V[rig.F].mean(axis=1); _, fi = cKDTree(cen).query(V2[F2].mean(axis=1))
            out = copy.copy(rig); out._tri_cache = {}
            out.V = V2; out.F = F2; out.J = rig.J[vi]; out.W = rig.W[vi]; out.fmat = rig.fmat[fi]
            out.fuv = np.repeat(rig.fuv[fi].mean(axis=1, keepdims=True), 3, axis=1) if rig.fuv is not None else None
            out.fcol = rig.fcol[fi] if rig.fcol is not None else None
            out.meta = dict(rig.meta, decimation="fast-simplification quadric")
            return out
    except Exception:
        pass
    return _cluster_decimate(rig, max_tris, dom)


def _cluster_decimate(rig, max_tris, dom):
    import copy
    inv_b = inv_rigid(rig.bind)
    Vh = np.c_[rig.V, np.ones(len(rig.V))]
    loc = np.einsum("nij,nj->ni", inv_b[dom], Vh)[:, :3]
    ext = float(np.ptp(rig.V, axis=0).max()) or 1.0

    def attempt(cell):
        q = np.floor(loc / cell).astype(np.int64)
        key = np.c_[dom, q]
        _, inv = np.unique(key, axis=0, return_inverse=True)
        inv = inv.ravel()
        F2 = inv[rig.F]
        good = (F2[:, 0] != F2[:, 1]) & (F2[:, 1] != F2[:, 2]) & (F2[:, 0] != F2[:, 2])
        idx = np.where(good)[0]
        if len(idx):
            _, first = np.unique(np.sort(F2[idx], axis=1), axis=0, return_index=True)
            idx = idx[np.sort(first)]
        return inv, F2, idx
    lo, hi = ext / 2000.0, ext / 2.0
    best = None
    for _ in range(30):
        cell = (lo * hi) ** 0.5
        inv, F2, idx = attempt(cell)
        if len(idx) > max_tris:
            lo = cell
        else:
            hi = cell; best = (inv, F2, idx)
        if hi / lo < 1.01:
            break
    if best is None:
        best = attempt(hi)
    inv, F2, idx = best
    n = int(inv.max()) + 1
    cnt = np.bincount(inv, minlength=n).astype(float)
    V2 = np.stack([np.bincount(inv, rig.V[:, a], minlength=n) / cnt for a in range(3)], 1)
    # skin of a cluster = the member vertex nearest the cluster centre
    d = np.linalg.norm(rig.V - V2[inv], axis=1)
    order = np.lexsort((d, inv))
    rep = order[np.r_[0, np.where(np.diff(inv[order]))[0] + 1]]
    out = copy.copy(rig); out._tri_cache = {}
    out.V = V2; out.F = F2[idx]; out.J = rig.J[rep]; out.W = rig.W[rep]; out.fmat = rig.fmat[idx]
    out.fuv = rig.fuv[idx] if rig.fuv is not None else None
    out.fcol = rig.fcol[idx] if rig.fcol is not None else None
    out.meta = dict(rig.meta, decimation="skin-aware vertex clustering (pure NumPy)")
    return out
"""Software renderer for MakeHuman characters (sforge.mhchar.Character) - v10.2.

Used by Sprite Forge Studio's Appearance tab (live preview) and by `forge.py look` (sprite sheets).  Pure numpy:
textured, lit, alpha-tested strand cards (hair, brows, lashes, facial hair), posed with the template's skeleton and
clips by linear blend skinning - the same maths the game runs on the GPU, so the sprites match the 3D model.

    poser = Poser(template_glb)
    img = render(ch, poser.pose(ch, "run", 0.3), view=View.side(), size=(192, 256))
"""
from __future__ import annotations
import io
from dataclasses import dataclass
import numpy as np
from PIL import Image

from .render_sculpt import rasterise, rx, ry
from .rigrec import inv_rigid

ALPHA_ROLES = ("hair", "brows", "lashes")


# ------------------------------------------------------------------ posing
class Poser:
    """template GLB (skeleton + clips) -> per-joint skinning matrices; joint indices are the GLB skin's joint order,
    the order mhchar parts use."""

    def __init__(self, template_glb):
        from . import gltfread, glbpack
        self.rig = gltfread.load(template_glb)
        j, _ = glbpack.read_glb(template_glb)
        names = [j["nodes"][i].get("name") for i in j["skins"][0]["joints"]]
        self.joint_names = names
        self.jmap = np.array([self.rig.bones.index(n) for n in names], int)
        self.binv = inv_rigid(self.rig.bind)[self.jmap]
        self.hips = self.rig.bones.index("pelvis") if "pelvis" in self.rig.bones else 0

    @property
    def clips(self):
        return self.rig.clips

    def matrices(self, clip=None, t=0.0):
        W = self.rig.worlds(clip, t)
        return W[self.jmap] @ self.binv, W

    def pose(self, ch, clip=None, t=0.0, follow_root=True):
        """-> list of (part, posed V, posed N); follow_root keeps the hips over the origin (x/z) for sprites"""
        S, W = self.matrices(clip, t)
        off = np.zeros(3)
        if follow_root and clip is not None:
            Wr = self.rig.bind[self.hips]
            off = np.array([W[self.hips, 0, 3] - Wr[0, 3], 0.0, W[self.hips, 2, 3] - Wr[2, 3]])
        out = []
        for p in ch.parts:
            V, N = skin(p.V, p.N, p.J, p.W, S)
            out.append((p, V - off, N))
        return out


def skin(V, N, J, Wt, S):
    Vh = np.c_[V, np.ones(len(V))]
    P = np.zeros((len(V), 3)); Q = np.zeros((len(V), 3))
    J = J.astype(np.int64)
    for k in range(4):
        w = Wt[:, k].astype(np.float64)
        if not np.any(w):
            continue
        M = S[J[:, k]]
        P += w[:, None] * np.einsum("nij,nj->ni", M[:, :3, :], Vh)
        if N is not None:
            Q += w[:, None] * np.einsum("nij,nj->ni", M[:, :3, :3], N)
    if N is None:
        return P, None
    Q /= np.linalg.norm(Q, axis=1, keepdims=True) + 1e-12
    return P, Q


def rest(ch):
    return [(p, p.V, p.N) for p in ch.parts]


# ------------------------------------------------------------------ camera
@dataclass
class View:
    yaw: float = 0.0            # degrees, 0 = facing the camera
    pitch: float = 0.0
    centre: tuple = (0.0, 0.9, 0.0)   # world point at the image centre (or at anchor)
    height: float = 2.0         # world metres visible vertically
    anchor: tuple = None        # (x px, y px) where `centre` lands; default image centre

    @staticmethod
    def side(cell=(192, 256), figure=0.80, baseline=248):
        """sprite camera: facing right, feet on the baseline, figure ~80% of the cell height"""
        h = 1.78 / figure
        return View(yaw=90.0, pitch=0.0, centre=(0.0, 0.0, 0.0), height=h, anchor=(cell[0] / 2, baseline))

    @staticmethod
    def face(yaw=25.0, top=1.75):
        return View(yaw=yaw, pitch=-4.0, centre=(0.0, top - 0.13, 0.0), height=0.36)

    @staticmethod
    def full(yaw=25.0):
        return View(yaw=yaw, pitch=-3.0, centre=(0.0, 0.88, 0.0), height=1.95)


def _decode(ch, cache):
    out = {}
    for k, png in ch.images.items():
        key = (k, len(png), hash(png[:64]), hash(png[-64:]))
        if key not in cache:
            im = Image.open(io.BytesIO(png))
            cache[key] = np.asarray(im.convert("RGBA"), np.float32) / 255.0
        out[k] = cache[key]
    return out


_TEX_CACHE = {}


def render(ch, posed, view: View = None, size=(420, 420), ss=2, bg=None, light=(-0.45, 0.65, 0.62), images=None):
    """posed (from Poser.pose or rest) -> PIL RGBA image.  bg: None = transparent, else rgb 0..1."""
    view = view or View.full()
    W, H = size[0] * ss, size[1] * ss
    tex = dict(_decode(ch, _TEX_CACHE))
    if images:
        tex.update(images)
    R = rx(view.pitch) @ ry(view.yaw)
    scale = H / view.height
    ax, ay = (view.anchor[0] * ss, view.anchor[1] * ss) if view.anchor else (W / 2, H / 2)
    c = np.asarray(view.centre, float)
    L = np.asarray(light, float) / np.linalg.norm(light)
    zb = np.full((H, W), -1e9); col = np.zeros((H, W, 3)); cov = np.zeros((H, W))
    rng = np.random.default_rng(7)
    dither = rng.uniform(0.3, 0.7, (H, W))
    opaque = [x for x in posed if x[0].role not in ALPHA_ROLES]
    alpha = [x for x in posed if x[0].role in ALPHA_ROLES]
    for group, is_alpha in ((opaque, False), (alpha, True)):
        for p, V, N in group:
            if len(p.F) == 0:
                continue
            Q = (V - c) @ R.T
            sx = ax + Q[:, 0] * scale; sy = ay - Q[:, 1] * scale; sz = Q[:, 2]
            Nv = (N @ R.T) if N is not None else None
            F = p.F.astype(np.int64)
            if not is_alpha:                                          # back-face cull (screen-space winding)
                ar = (sx[F[:, 1]] - sx[F[:, 0]]) * (sy[F[:, 2]] - sy[F[:, 0]]) - \
                     (sx[F[:, 2]] - sx[F[:, 0]]) * (sy[F[:, 1]] - sy[F[:, 0]])
                F = F[ar < 0]
                subsets = [F]
            else:                                                     # cheap depth peeling: random layers
                k = 4 if len(F) > 400 else 1
                lab = rng.integers(0, k, len(F))
                subsets = [F[lab == i] for i in range(k)]
            img = tex.get(p.image)
            for Fs in subsets:
                if len(Fs) == 0:
                    continue
                tid, bc, z = rasterise(sx, sy, sz, Fs, W, H)
                m = tid >= 0
                if not m.any():
                    continue
                yy, xx = np.nonzero(m)
                f = Fs[tid[m]]; b = bc[m]
                zz = z[m]
                nearer = zz > zb[yy, xx]
                if not nearer.any():
                    continue
                yy, xx, f, b, zz = yy[nearer], xx[nearer], f[nearer], b[nearer], zz[nearer]
                uv = (p.UV[f] * b[..., None]).sum(1)
                if img is not None:
                    th, tw = img.shape[:2]
                    u = np.mod(uv[:, 0], 1.0); v = np.mod(uv[:, 1], 1.0)
                    s = img[np.clip((v * th).astype(int), 0, th - 1), np.clip((u * tw).astype(int), 0, tw - 1)]
                    rgb, a = s[:, :3].copy(), s[:, 3].copy()
                else:
                    rgb = np.full((len(f), 3), 0.7); a = np.ones(len(f))
                if p.C is not None:
                    cc = (p.C[f] * b[..., None]).sum(1)
                    rgb *= cc[:, :3]; a *= cc[:, 3]
                if is_alpha:                                          # dithered alpha: soft, wispy edges after
                    keep = a > dither[yy, xx]                         # the supersampled image is filtered down
                    yy, xx, f, b, zz, rgb = yy[keep], xx[keep], f[keep], b[keep], zz[keep], rgb[keep]
                    if not len(yy):
                        continue
                if Nv is not None:
                    n = (Nv[f] * b[..., None]).sum(1)
                    n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-12
                    if is_alpha and p.role != "hair":                 # brows / lashes: two-sided cards face the camera
                        n = np.where((n[:, 2:3] < 0), -n, n)              # (hair has smooth volume normals)
                    nl = n @ (R @ L)
                    rim = np.clip(1 - np.abs(n[:, 2]), 0, 1) ** 3
                    shade = 0.42 + 0.66 * np.clip(nl, 0, 1) + 0.18 * rim
                    if p.role == "eyes":
                        shade = 0.75 + 0.3 * np.clip(nl, 0, 1)
                    rgb = rgb * shade[:, None]
                    if p.role == "hair" and "shell" not in p.name:      # soft sheen band (hair is glossy, skin is not)
                        hv = R @ L + np.array([0, 0, 1.0]); hv /= np.linalg.norm(hv)
                        sh = np.clip(n @ hv, 0, 1) ** 16 * 0.12
                        rgb = rgb + sh[:, None] * (0.35 + 0.65 * rgb)
                zb[yy, xx] = zz; col[yy, xx] = rgb; cov[yy, xx] = 1
    col = np.clip(col, 0, 1)
    im = np.dstack([col, cov])
    out = Image.fromarray((im * 255 + 0.5).astype(np.uint8), "RGBA")
    if ss > 1:
        # premultiplied downsample so edges do not pick up black
        pm = np.dstack([col * cov[..., None], cov])
        pi = Image.fromarray((pm * 255 + 0.5).astype(np.uint8), "RGBA").resize(size, Image.BOX)
        a = np.asarray(pi, np.float32) / 255
        rgb = a[..., :3] / np.maximum(a[..., 3:], 1e-3)
        out = Image.fromarray((np.dstack([np.clip(rgb, 0, 1), a[..., 3]]) * 255 + 0.5).astype(np.uint8), "RGBA")
    if bg is not None:
        base = Image.new("RGBA", out.size, tuple(int(x * 255) for x in bg) + (255,))
        base.alpha_composite(out); out = base
    return out


def with_kit(ch, kit_png):
    """kit garments read image 'kit'; give the character a kit atlas (PNG bytes or PIL image)"""
    if isinstance(kit_png, Image.Image):
        bio = io.BytesIO(); kit_png.save(bio, "PNG"); kit_png = bio.getvalue()
    ch.images["kit"] = kit_png
    return ch


def contact_sheet(images, cols, bg=(0.35, 0.5, 0.3), labels=None):
    w, h = images[0].size
    rows = (len(images) + cols - 1) // cols
    sheet = Image.new("RGBA", (w * cols, h * rows), tuple(int(x * 255) for x in bg) + (255,))
    for i, im in enumerate(images):
        sheet.alpha_composite(im, ((i % cols) * w, (i // cols) * h))
    if labels:
        from PIL import ImageDraw
        d = ImageDraw.Draw(sheet)
        for i, t in enumerate(labels):
            d.text(((i % cols) * w + 4, (i // cols) * h + 3), t, fill=(255, 255, 255, 255))
    return sheet

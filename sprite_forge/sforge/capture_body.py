"""forge.py capture, step 2 - a fast, posable MakeHuman body for fitting (v11).

The CC0 MakeHuman base mesh + macro targets (gender, age, muscle, weight, height, proportions) + a set of modifier
targets used as shape sliders (torso / hip depth and width, bust, waist, hips, thighs, calves, upper arms, shoulders,
neck, head, leg lengths). Everything is linear in the target weights once the macro mix is known, so a shape costs a
few milliseconds. The 'body' skeleton (25 bones, human.build's reduction of MakeHuman's default skeleton) is rebuilt
for every shape from MakeHuman's joint vertex groups; skin weights are MakeHuman's own (default_weights.mhw).

Posing: the turnaround subjects stand with their arms by their sides (or in a T-pose); the base mesh is in MakeHuman's
A-pose. `pose()` turns the upper arms, forearms, thighs and shins to the measured directions (linear blend skinning).

Units: metres, Y up, the body faces +Z, its left is +X, feet on y = 0 (the Sprite Forge rig convention)."""
from __future__ import annotations
import os
import numpy as np

from . import human as HU

# shape sliders: name -> (decr target, incr target); slider s in [-1, 1]
SLIDERS = {
    "torso_depth": ("torso/torso-scale-depth-decr", "torso/torso-scale-depth-incr"),
    "torso_width": ("torso/torso-scale-horiz-decr", "torso/torso-scale-horiz-incr"),
    "hip_depth": ("hip/hip-scale-depth-decr", "hip/hip-scale-depth-incr"),
    "hip_width": ("hip/hip-scale-horiz-decr", "hip/hip-scale-horiz-incr"),
    "bust": ("measure/measure-bust-circ-decr", "measure/measure-bust-circ-incr"),
    "waist": ("measure/measure-waist-circ-decr", "measure/measure-waist-circ-incr"),
    "hips": ("measure/measure-hips-circ-decr", "measure/measure-hips-circ-incr"),
    "belly": ("stomach/stomach-pregnant-decr", "stomach/stomach-pregnant-incr"),
    "buttocks": ("buttocks/buttocks-volume-decr", "buttocks/buttocks-volume-incr"),
    "shoulders": ("measure/measure-shoulder-dist-decr", "measure/measure-shoulder-dist-incr"),
    "upperarm": ("measure/measure-upperarm-circ-decr", "measure/measure-upperarm-circ-incr"),
    "thigh": ("measure/measure-thigh-circ-decr", "measure/measure-thigh-circ-incr"),
    "calf": ("measure/measure-calf-circ-decr", "measure/measure-calf-circ-incr"),
    "neck": ("measure/measure-neck-circ-decr", "measure/measure-neck-circ-incr"),
    "upperleg_len": ("measure/measure-upperleg-height-decr", "measure/measure-upperleg-height-incr"),
    "lowerleg_len": ("measure/measure-lowerleg-height-decr", "measure/measure-lowerleg-height-incr"),
    "torso_len": ("measure/measure-napetowaist-dist-decr", "measure/measure-napetowaist-dist-incr"),
    "head_width": ("head/head-scale-horiz-decr", "head/head-scale-horiz-incr"),
    "head_height": ("head/head-scale-vert-decr", "head/head-scale-vert-incr"),
    "head_depth": ("head/head-scale-depth-decr", "head/head-scale-depth-incr"),
}
MACROS = ("gender", "age", "muscle", "weight", "proportions")
# bones posed from the video (upper arm, forearm, thigh, shin)
CHAINS = {"L": [("upperarm01.L", "lowerarm01.L"), ("lowerarm01.L", "wrist.L"), ("upperleg01.L", "lowerleg01.L"),
                ("lowerleg01.L", "foot.L")],
          "R": [("upperarm01.R", "lowerarm01.R"), ("lowerarm01.R", "wrist.R"), ("upperleg01.R", "lowerleg01.R"),
                ("lowerleg01.R", "foot.R")]}


class BodyModel:
    def __init__(self, assets=None, skeleton="body"):
        d = HU.assets_dir(assets)
        if not HU.have_assets(d):
            raise FileNotFoundError("MakeHuman assets missing - run  forge.py human --setup --from-git")
        self.d = d
        self.Vall, F, self.fuv = HU.read_obj(os.path.join(d, "base.obj"))
        self.T = dict(np.load(os.path.join(d, "macro_targets.npz"), allow_pickle=False))
        mp = os.path.join(d, "modifier_targets.npz")
        self.M = np.load(mp, allow_pickle=False) if os.path.isfile(mp) else None
        self.sk = HU.read_skel(os.path.join(d, "default.mhskel"))
        bones_all = list(self.sk["bones"])
        self.parent_of = {b: self.sk["bones"][b].get("parent") for b in bones_all}
        self.order, self.to = HU.reduce_skeleton(bones_all, self.parent_of, skeleton)
        self.bi = {b: i for i, b in enumerate(self.order)}
        used_v = np.unique(F)
        self.used_v = used_v
        remap = -np.ones(len(self.Vall), int); remap[used_v] = np.arange(len(used_v))
        self.F = remap[F]
        acc = np.zeros((len(used_v), len(self.order)), np.float32)
        for b, lst in HU.read_weights(os.path.join(d, "default_weights.mhw")).items():
            if b not in self.to:
                continue
            a = np.array(lst, float)
            vi = remap[a[:, 0].astype(int)]; ok = vi >= 0
            np.add.at(acc[:, self.bi[self.to[b]]], vi[ok], a[ok, 1])
        J = np.argsort(-acc, axis=1)[:, :4]
        W = np.take_along_axis(acc, J, axis=1).astype(float)
        s = W.sum(1); J[s <= 0] = 0; W[s <= 0] = [1, 0, 0, 0]
        self.J, self.W = J, W / W.sum(1, keepdims=True)
        self.parent = np.array([self.bi[self._kept_parent(b)] if self._kept_parent(b) else -1 for b in self.order])
        self._macro_cache = {}
        # dense deltas for the sliders (decimetres, all vertices)
        self.slider_d = {}
        for k, (dn, up) in SLIDERS.items():
            pair = []
            for t in (dn, up):
                pair.append(self._dense(t))
            self.slider_d[k] = pair
        # the face (capture_face.FACE_SLIDERS): each slider moves one or more MakeHuman modifiers together
        from .capture_face import FACE_SLIDERS
        for k, mods in FACE_SLIDERS.items():
            pair = [None, None]
            for base, neg, pos in mods:
                for side, suf in ((0, neg), (1, pos)):
                    D = self._dense("%s-%s" % (base, suf))
                    if D is not None:
                        pair[side] = D if pair[side] is None else pair[side] + D
            self.slider_d[k] = pair

    def _kept_parent(self, b):
        p = self.parent_of.get(b)
        while p is not None and p not in self.bi:
            p = self.parent_of.get(p)
        return p

    def _dense(self, name):
        D = np.zeros_like(self.Vall)
        if self.M is None or (name + ".i") not in self.M.files:
            return None
        idx = self.M[name + ".i"].astype(np.int64); vec = self.M[name + ".v"].astype(float)
        np.add.at(D, idx, vec)
        return D

    def _macro(self, mac):
        key = tuple(round(float(mac.get(k, 0.5)), 3) for k in MACROS)
        if key not in self._macro_cache:
            p = dict(HU.DEFAULTS); p.update(dict(zip(MACROS, key))); p["height"] = 0.5
            # MakeHuman's own macro mixing as MPFB2 does it (capture_mh.mpfb_macro_weights): the body built here is
            # then exactly the body MakeHuman / MPFB build from the exported .mhm
            from .capture_mh import mpfb_macro_weights
            V, _ = HU.morph(self.Vall, self.T, mpfb_macro_weights(p))
            if len(self._macro_cache) > 64:
                self._macro_cache.clear()
            self._macro_cache[key] = V
        return self._macro_cache[key]

    def shape(self, mac=None, sliders=None, height=None):
        """-> Shape: rest vertices (metres, grounded, centred), joints, bind matrices"""
        V = self._macro(mac or {}).copy()
        for k, s in (sliders or {}).items():
            if k not in self.slider_d or not s:
                continue
            dn, up = self.slider_d[k]
            D = up if s > 0 else dn
            if D is not None:
                V += abs(float(s)) * D
        joints = self.sk["joints"]
        jp = lambda key: V[np.array(joints[key], int)].mean(0)
        head = {b: jp(self.sk["bones"][b]["head"]) for b in self.order}
        tail = {b: jp(self.sk["bones"][b]["tail"]) for b in self.order}
        Vb = V[self.used_v] * 0.1                                   # dm -> m
        H = np.array([head[b] for b in self.order]) * 0.1
        Tl = np.array([tail[b] for b in self.order]) * 0.1
        y0 = Vb[:, 1].min(); c = np.array([0.5 * (Vb[:, 0].min() + Vb[:, 0].max()), y0, 0.0])
        Vb = Vb - c; H = H - c; Tl = Tl - c
        if height:
            k = float(height) / (Vb[:, 1].max() - Vb[:, 1].min())
            Vb, H, Tl = Vb * k, H * k, Tl * k
        return Shape(self, Vb, H, Tl)


class Shape:
    def __init__(self, model, V, head, tail):
        self.m, self.V, self.head, self.tail = model, V, head, tail

    def joint(self, name):
        return self.head[self.m.bi[name]]

    def height(self):
        return float(self.V[:, 1].max() - self.V[:, 1].min())

    def pose(self, dirs=None):
        """dirs: {bone: unit direction (model space) its head->tail should point}. Unlisted bones keep the rest
        direction relative to their parent. -> posed vertices, posed joint heads (bones x 3)"""
        m = self.m
        nb = len(m.order)
        Rg = [np.eye(3)] * nb
        Pg = self.head.copy()
        for i, b in enumerate(m.order):
            p = m.parent[i]
            Rp = Rg[p] if p >= 0 else np.eye(3)
            if p >= 0:
                Pg[i] = Pg[p] + Rp @ (self.head[i] - self.head[p])
            R = Rp
            if dirs and b in dirs:
                # a limb direction is measured joint to joint (hip -> knee, shoulder -> elbow): aim the bone's next
                # kept joint, not its own tail - the 26-bone rig drops MakeHuman's upperleg02 / upperarm02 /
                # lowerarm02.., so a tail lies part-way down the limb and off its line
                end = LIMB_END.get(b)
                tip = self.head[m.bi[end]] if end in m.bi else self.tail[i]
                cur = Rp @ (tip - self.head[i])
                R = _rot_between(cur, np.asarray(dirs[b], float)) @ Rp
            Rg[i] = R
        S = np.zeros((nb, 3, 4))
        for i in range(nb):
            S[i, :, :3] = Rg[i]; S[i, :, 3] = Pg[i] - Rg[i] @ self.head[i]
        Vh = np.c_[self.V, np.ones(len(self.V))]
        P = np.zeros_like(self.V)
        for k in range(4):
            w = m.W[:, k]
            P += w[:, None] * np.einsum("nij,nj->ni", S[m.J[:, k]], Vh)
        return P, Pg, S


LIMB_END = {"upperleg01.L": "lowerleg01.L", "lowerleg01.L": "foot.L", "upperleg01.R": "lowerleg01.R",
            "lowerleg01.R": "foot.R", "upperarm01.L": "lowerarm01.L", "lowerarm01.L": "wrist.L",
            "upperarm01.R": "lowerarm01.R", "lowerarm01.R": "wrist.R"}


def _rot_between(a, b):
    a = a / (np.linalg.norm(a) + 1e-12); b = b / (np.linalg.norm(b) + 1e-12)
    v = np.cross(a, b); c = float(np.dot(a, b))
    if c < -0.9999:
        ax = np.cross(a, [1, 0, 0]) if abs(a[0]) < 0.9 else np.cross(a, [0, 1, 0])
        ax /= np.linalg.norm(ax)
        return 2 * np.outer(ax, ax) - np.eye(3)
    vx = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + vx + vx @ vx / (1 + c)


def target_weights(sliders):
    """slider values -> MakeHuman modifier target weights (the names MakeHuman / MPFB use)"""
    out = {}
    for k, s in (sliders or {}).items():
        if k in SLIDERS and abs(float(s)) > 1e-6:
            out[SLIDERS[k][1 if s > 0 else 0]] = abs(float(s))
    return out

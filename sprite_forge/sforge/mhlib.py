"""MakeHuman template library for Sprite Forge (v10.2): CC0 base body, modifier morph targets and fitted assets
(hair, eyebrows, eyelashes, eyes, skins) - the realistic starting point behind sforge.appearance.

    python3 forge.py human --setup --full        # base files + every modifier target + the CC0 system assets
    from sforge import mhlib
    lib = mhlib.Library()                        # assets/makehuman (or $SFS_MAKEHUMAN)
    d = lib.target("nose/nose-scale-vert-incr")  # (index (k,), delta (k,3) decimetres)
    p = lib.proxy("hair", "short02")             # fitted asset: obj + mhclo binding + material textures
    lib.list("hair")                             # -> ['afro01', 'bob01', ...]

v11 additions (Blender verification + rigs):
    mhlib.setup_mpfb()                           # MPFB2's CC0 data (rigs: game_engine, mixamo, default ...) -> mpfb/
    rig, weights = mhlib.load_rig("mixamo")      # bone head/tail from the helper joint cubes, official weights
    info = mhlib.human_info(appearance_targets, ...)   # the JSON MPFB2 (MakeHuman for Blender) builds a human from

Everything here is CC0 1.0 (MakeHuman assets "explicitly released as CC0 in September 2020"); no MakeHuman or MPFB
program code (AGPL / GPL) is used - the .mhclo / .mhmat / target / rig formats are read by our own code."""
from __future__ import annotations
import json
import os
import re
import shutil
import numpy as np
from . import human as HU

KINDS = ("hair", "eyebrows", "eyelashes", "eyes", "skins", "teeth")
SYSTEM_ZIP = "https://files.makehumancommunity.org/asset_packs/makehuman_system_assets/makehuman_system_assets_cc0.zip"
SYSTEM_ZIP2 = "https://files2.makehumancommunity.org/asset_packs/makehuman_system_assets/makehuman_system_assets_cc0.zip"
MPFB_URL = ("https://extensions.blender.org/download/sha256:c075b3e9b94b8e5556a5f03f4653602d02ea306de08126e8f55ed6dee28a2dad/"
            "add-on-mpfb-v2.0.18.zip")
MPFB_SHA = "c075b3e9b94b8e5556a5f03f4653602d02ea306de08126e8f55ed6dee28a2dad"


# ------------------------------------------------------------------ setup
def _modifier_subset(npz_path, out_path):
    """every non-macro target of MakeHuman's pip wheel as '<group>/<name>.i' (uint16) / '.v' (float32 dm)"""
    z = np.load(npz_path, allow_pickle=False)
    keep = {}
    for k in z.files:
        if not k.startswith("targets/") or k.startswith("targets/macrodetails/") or k.startswith("targets/expression/"):
            continue
        if k.endswith(".index"):
            name = k[len("targets/"):-len(".index")]
            keep[name + ".i"] = z[k].astype(np.uint16)
            keep[name + ".v"] = z[k[:-len(".index")] + ".vector"].astype(np.float32) / 1000.0 \
                if z[k[:-len(".index")] + ".vector"].dtype.kind == "i" else z[k[:-len(".index")] + ".vector"].astype(np.float32)
    np.savez_compressed(out_path, **keep)
    return len(keep) // 2


def setup_full(dest=None, log=print, system_zip=None, targets_npz=None):
    """base files (human.setup) + modifier_targets.npz + system/<kind>/... from the CC0 system asset pack"""
    import urllib.request, subprocess, sys, tempfile, zipfile
    dest = HU.assets_dir(dest)
    if not HU.have_assets(dest):
        HU.setup(dest, log=log)
    tmp = tempfile.mkdtemp(prefix="sfs_mhfull_")
    try:
        if not os.path.isfile(os.path.join(dest, "modifier_targets.npz")):
            if not targets_npz:
                subprocess.check_call([sys.executable, "-m", "pip", "download", "--no-deps", "-d", tmp, "-q", HU.WHEEL])
                whl = [f for f in os.listdir(tmp) if f.endswith(".whl")][0]
                with zipfile.ZipFile(os.path.join(tmp, whl)) as z, z.open("makehuman/data/targets.npz") as s, \
                        open(os.path.join(tmp, "t.npz"), "wb") as d:
                    shutil.copyfileobj(s, d)
                targets_npz = os.path.join(tmp, "t.npz")
            log("modifier targets: %d" % _modifier_subset(targets_npz, os.path.join(dest, "modifier_targets.npz")))
        if not os.path.isdir(os.path.join(dest, "system", "hair")):
            if not system_zip:
                system_zip = os.path.join(tmp, "system.zip")
                for url in (SYSTEM_ZIP, SYSTEM_ZIP2):
                    try:
                        log("download %s" % url)
                        with urllib.request.urlopen(url, timeout=600) as r, open(system_zip, "wb") as f:
                            shutil.copyfileobj(r, f)
                        break
                    except Exception as e:                        # noqa: BLE001
                        log("  failed: %s" % e)
            with zipfile.ZipFile(system_zip) as z:
                for n in z.namelist():
                    if n.endswith("/") or n.split("/")[0] not in KINDS or n.endswith(".thumb"):
                        continue
                    out = os.path.join(dest, "system", n)
                    os.makedirs(os.path.dirname(out), exist_ok=True)
                    with z.open(n) as s, open(out, "wb") as d:
                        shutil.copyfileobj(s, d)
            log("system assets -> %s" % os.path.join(dest, "system"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return dest


def setup_mpfb(dest=None, mpfb_zip=None, log=print):
    """v11: MPFB2's CC0 data folder (rigs + weights for game_engine / mixamo / default / cmu_mb ..., mesh metadata)
    into assets/makehuman/mpfb/ - for rigs other than the game template's and for Blender verification"""
    import hashlib, tempfile, urllib.request, zipfile
    dest = os.path.join(HU.assets_dir(dest), "mpfb")
    if not mpfb_zip:
        mpfb_zip = os.path.join(tempfile.mkdtemp(prefix="sfs_mpfb_"), "mpfb.zip")
        log("download %s" % MPFB_URL)
        urllib.request.urlretrieve(MPFB_URL, mpfb_zip)
    h = hashlib.sha256(open(mpfb_zip, "rb").read()).hexdigest()
    if h != MPFB_SHA:
        log("note: MPFB zip sha256 %s (expected %s for v2.0.18)" % (h[:12], MPFB_SHA[:12]))
    with zipfile.ZipFile(mpfb_zip) as z:
        for n in z.namelist():
            if n.endswith("/") or not n.startswith(("data/rigs/standard/", "data/mesh_metadata/", "data/targets/")):
                continue
            out = os.path.join(dest, n[len("data/"):])
            os.makedirs(os.path.dirname(out), exist_ok=True)
            with z.open(n) as s, open(out, "wb") as d:
                shutil.copyfileobj(s, d)
    log("MPFB rigs -> %s" % dest)
    log("targets from MPFB data: %d updated, %d added" % refresh_targets_from_mpfb(os.path.dirname(dest)))
    return dest


def refresh_targets_from_mpfb(root=None):
    """make modifier_targets.npz match MakeHuman's current data as shipped with MPFB2: targets MPFB revised replace
    the pip wheel's copies (same names), targets only MPFB has are added under MPFB's group folders.  After this a
    Forge character and the same character built by MPFB in Blender agree vertex for vertex."""
    import gzip
    root = HU.assets_dir(root)
    tdir = os.path.join(root, "mpfb", "targets")
    if not os.path.isdir(tdir):
        return (0, 0)
    out = os.path.join(root, "modifier_targets.npz")
    cur = dict(np.load(out)) if os.path.isfile(out) else {}
    by_bare = {k[:-2].split("/")[-1]: k[:-2] for k in cur if k.endswith(".i")}
    upd = add = 0
    for dp, _, files in os.walk(tdir):
        grp = os.path.relpath(dp, tdir).replace(os.sep, "/")
        if grp.split("/")[0] in ("macrodetails", "expression"):
            continue
        for f in files:
            if not f.endswith(".target.gz"):
                continue
            bare = f[:-len(".target.gz")]
            rows = [l.split() for l in gzip.open(os.path.join(dp, f), "rt") if l.strip() and not l.startswith("#")]
            i = np.array([int(r[0]) for r in rows], np.uint16)
            v = np.array([[float(x) for x in r[1:4]] for r in rows], np.float32).reshape(-1, 3)
            name = by_bare.get(bare)
            if name is None:
                name = grp + "/" + bare; add += 1
            elif cur[name + ".i"].shape != i.shape or not np.allclose(cur[name + ".v"], v, atol=1e-5) or (cur[name + ".i"] != i).any():
                upd += 1
            else:
                continue
            cur[name + ".i"] = i; cur[name + ".v"] = v
    if upd or add:
        np.savez_compressed(out, **cur)
    return (upd, add)


# ------------------------------------------------------------------ file formats (our own readers)
def _mhmat(path):
    m = {}
    if not os.path.isfile(path):
        return m
    for ln in open(path, encoding="utf-8", errors="replace"):
        t = ln.strip().split(None, 1)
        if len(t) == 2 and not t[0].startswith("#"):
            m[t[0]] = t[1].strip()
    return m


def _read_mhclo(path):
    """-> dict: header keys (obj_file, material, ...), ref (n,3) int, w (n,3), off (n,3), scales [x,y,z] (v1,v2,d) or None"""
    meta = {"scales": [None, None, None]}
    rows = []
    verts = False
    for ln in open(path, encoding="utf-8", errors="replace"):
        s = ln.strip()
        if not s or s.startswith("#"):
            continue
        t = s.split()
        if t[0] in ("x_scale", "y_scale", "z_scale"):
            meta["scales"]["xyz".index(t[0][0])] = (int(t[1]), int(t[2]), float(t[3])); continue
        if t[0] == "verts":
            verts = True; continue
        if verts and len(t) == 9 and re.match(r"^-?\d", t[0]):
            rows.append([float(x) for x in t]); continue
        if verts and len(t) == 1 and re.match(r"^\d+$", t[0]):
            i = int(t[0]); rows.append([i, i, i, 1, 0, 0, 0, 0, 0]); continue
        if t[0] in ("delete_verts", "weights", "faces"):          # a new section ends the binding rows
            verts = False; continue
        if verts and re.match(r"^-?\d", t[0]):                   # some other numeric row inside verts: skip
            continue
        meta.setdefault(t[0], " ".join(t[1:]) if len(t) > 1 else "")   # header keys may sit inside the verts block
    R = np.array(rows, float).reshape(-1, 9)
    meta["ref"] = R[:, 0:3].astype(np.int64); meta["w"] = R[:, 3:6]; meta["off"] = R[:, 6:9]
    return meta


def _read_proxy_obj(path):
    """-> (src (k,) original vertex per output vertex, triangles (m,3), uv (k,2) glTF v-down): vertices are split where
    one position has several UVs, so every output vertex has exactly one UV"""
    V, VT, faces = [], [], []
    for ln in open(path, encoding="utf-8", errors="replace"):
        if ln.startswith("v "):
            V.append(1)
        elif ln.startswith("vt "):
            VT.append([float(x) for x in ln.split()[1:3]])
        elif ln.startswith("f "):
            c = [p.split("/") for p in ln.split()[1:]]
            faces.append([(int(p[0]) - 1, int(p[1]) - 1 if len(p) > 1 and p[1] else -1) for p in c])
    key = {}; src = []; uvi = []; F = []
    for f in faces:
        ids = []
        for v, t in f:
            k = (v, t)
            if k not in key:
                key[k] = len(src); src.append(v); uvi.append(t)
            ids.append(key[k])
        for j in range(1, len(ids) - 1):
            F.append([ids[0], ids[j], ids[j + 1]])
    VT = np.array(VT, float) if VT else np.zeros((1, 2))
    UV = VT[np.maximum(np.array(uvi), 0)].copy(); UV[:, 1] = 1.0 - UV[:, 1]
    return np.array(src, np.int64), np.array(F, np.int64), UV, len(V)


class Proxy:
    def __init__(self, kind, name, src, F, UV, ref, w, off, scales, tex, alpha):
        self.kind, self.name, self.src, self.F, self.UV = kind, name, src, F, UV
        self.ref, self.w, self.off, self.scales, self.tex, self.alpha = ref, w, off, scales, tex, alpha

    def fit(self, Vb):
        """proxy vertex positions on a (morphed) base body Vb (dm, base space)"""
        sc = np.ones(3)
        for i, s in enumerate(self.scales):
            if s:
                a, b, d = s
                sc[i] = abs(Vb[a, i] - Vb[b, i]) / d if d else 1.0
        return (Vb[self.ref] * self.w[..., None]).sum(1) + self.off * sc


class Library:
    def __init__(self, root=None):
        self.root = HU.assets_dir(root)
        self._base = None
        self._mods = None

    def available(self):
        return HU.have_assets(self.root) and os.path.isfile(os.path.join(self.root, "modifier_targets.npz")) \
            and os.path.isdir(os.path.join(self.root, "system", "hair"))

    def base(self):
        """-> (all base vertices (n,3) dm, body triangles (m,3), uv per triangle corner (m,3,2) v-up)"""
        if self._base is None:
            self._base = HU.read_obj(os.path.join(self.root, "base.obj"))
        return self._base

    def mods(self):
        if self._mods is None:
            self._mods = np.load(os.path.join(self.root, "modifier_targets.npz"))
        return self._mods

    def has_target(self, name):
        return name + ".i" in self.mods().files

    def target(self, name):
        m = self.mods()
        return m[name + ".i"].astype(np.int64), m[name + ".v"].astype(np.float64)

    def targets(self, group):
        return sorted(k[:-2] for k in self.mods().files if k.startswith(group + "/") and k.endswith(".i"))

    def list(self, kind):
        p = os.path.join(self.root, "system", kind)
        if not os.path.isdir(p):
            return []
        return sorted(n for n in os.listdir(p) if os.path.isdir(os.path.join(p, n)) and n != "materials")

    def materials(self, kind):
        p = os.path.join(self.root, "system", kind, "materials")
        return sorted(f[:-6] for f in os.listdir(p) if f.endswith(".mhmat")) if os.path.isdir(p) else []

    def skin(self, name):
        d = os.path.join(self.root, "system", "skins", name)
        m = _mhmat(os.path.join(d, name + ".mhmat"))
        return os.path.join(d, os.path.basename(m.get("diffuseTexture", name + "_diffuse.png")))

    def eye_texture(self, colour):
        d = os.path.join(self.root, "system", "eyes", "materials")
        m = _mhmat(os.path.join(d, colour + ".mhmat"))
        return os.path.join(d, os.path.basename(m.get("diffuseTexture", colour + "_eye.png")))

    def proxy(self, kind, name):
        d = os.path.join(self.root, "system", kind, name)
        meta = _read_mhclo(os.path.join(d, name + ".mhclo"))
        src, F, UV, nv = _read_proxy_obj(os.path.join(d, meta.get("obj_file", name + ".obj")))
        if len(meta["ref"]) != nv:
            raise ValueError("%s: %d mhclo rows for %d vertices" % (name, len(meta["ref"]), nv))
        mat = _mhmat(os.path.join(d, meta.get("material", name + ".mhmat")))
        tex = mat.get("diffuseTexture")
        tex = os.path.join(d, os.path.basename(tex)) if tex else None
        alpha = mat.get("transparent", "false").lower() == "true"
        return Proxy(kind, name, src, F, UV, meta["ref"][src], meta["w"][src], meta["off"][src], meta["scales"], tex, alpha)


# ------------------------------------------------------------------ v11: rigs and MPFB human_info
def load_rig(name="game_engine", root=None):
    """MPFB2 CC0 rig + weights: (rig dict: bone -> head/tail cube names, parent, roll; weights: bone -> [[v, w], ...])"""
    d = os.path.join(HU.assets_dir(root), "mpfb", "rigs", "standard")
    rig = json.load(open(os.path.join(d, "rig.%s.json" % name)))
    return rig, json.load(open(os.path.join(d, "weights.%s.json" % name)))["weights"]


def vertex_groups(root=None):
    meta = json.load(open(os.path.join(HU.assets_dir(root), "mpfb", "mesh_metadata", "basemesh_vertex_groups.json")))
    return {k: (np.concatenate([np.arange(a, b + 1) for a, b in r]) if r else np.zeros(0, int)) for k, r in meta.items()}


def rig_joints(rig, Vb, groups):
    """bone -> (head, tail) on a (morphed) base body Vb (dm), from MakeHuman's helper joint cubes"""
    def pos(s):
        if s["strategy"] == "CUBE":
            return Vb[groups[s["cube_name"]]].mean(0)
        return Vb[np.asarray(s["vertex_indices"])].mean(0)
    return {b: (pos(v["head"]), pos(v["tail"])) for b, v in rig.items()}


def human_info(targets, phenotype=None, hair="", eyebrows="", eyelashes="eyelashes01", eye_colour="brown",
               skin="young_caucasian_male", rig="game_engine"):
    """the human description MPFB2 builds in Blender (HumanService.deserialize_from_dict).  targets: {name: weight}
    with Sprite Forge names ('nose/nose-scale-vert-incr'); MPFB uses the bare target name."""
    ph = {"gender": 1.0, "age": 0.5, "muscle": 0.5, "weight": 0.5, "height": 0.5, "proportions": 0.5,
          "cupsize": 0.5, "firmness": 0.5, "race": {"african": 0.0, "asian": 0.0, "caucasian": 1.0}}
    for k, v in (phenotype or {}).items():
        if k in ("african", "asian", "caucasian"):
            ph["race"][k] = v
        else:
            ph[k] = v
    return {"phenotype": ph, "rig": rig,
            "eyes": "high-poly/high-poly.mhclo", "eyes_material_type": "MAKESKIN",
            "eyes_material_settings": {}, "eye_colour": eye_colour,
            "eyebrows": ("%s/%s.mhclo" % (eyebrows, eyebrows)) if eyebrows else "",
            "eyelashes": ("%s/%s.mhclo" % (eyelashes, eyelashes)) if eyelashes else "",
            "hair": ("%s/%s.mhclo" % (hair, hair)) if hair and hair not in ("bald", "buzz") else "",
            "proxy": "", "tongue": "", "teeth": "", "clothes": [], "expressions": [],
            "skin_mhmat": "%s/%s.mhmat" % (skin, skin), "skin_material_type": "ENHANCED", "skin_material_settings": {},
            "targets": [{"target": k.split("/")[-1], "value": float(v)} for k, v in targets.items() if abs(v) > 1e-6]}

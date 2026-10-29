"""v7 MakeHuman mode - parametric HUMAN rigs (gender / age / muscle / weight / height / proportions) built from the
CC0 MakeHuman ASSETS by our own pure-numpy code.

What is used (all CC0 1.0, "explicitly released as CC0 in September 2020" by the MakeHuman team):
  base.obj              the MakeHuman base mesh (decimetres, Y up)            makehuman/data/3dobjs/base.obj
  default.mhskel        the default skeleton (163 bones, joints = vertex groups) makehuman/data/rigs/default.mhskel
  default_weights.mhw   its skin weights                                         makehuman/data/rigs/default_weights.mhw
  macro targets         macrodetails / height / proportions morph targets         makehuman/data/targets.npz (pip wheel)
What is NOT used: any MakeHuman program code (AGPL-3.0) - the macro-weight formulas below are re-implemented from the
documented behaviour; MakeHuman itself (Qt/OpenGL app) is not needed or installed.

The assets are NOT inside the studio zip (size: targets alone are 31 MB).  `forge.py human --setup` downloads them
(GitHub raw files + `pip download makehuman --no-deps` for targets.npz, only the macro targets are kept) into
<studio>/assets/makehuman (or $SFS_MAKEHUMAN), or `forge.py human --setup --from DIR` copies them from a folder.
Without the assets the human mode FALLS BACK to the parametric sforge mannequin with the same parameters
(height / build) and says so - or import any MakeHuman export (FBX/GLB) with `forge.py library add FILE --preset makehuman`.

Skeleton variants (derived from default.mhskel; MakeHuman's own game_engine / default_no_toes .mhskel files are not
in the public repository, so these are reductions of the default skeleton with weights merged into the kept parent):
  default          163 bones (face, fingers, toes)
  default_no_toes  135 bones (toes merged into the foot)
  game_engine       65 bones (spine, neck, jaw, twist bones, 15 finger bones per hand, 1 toe per foot)
  body              25 bones (no fingers / face; like a basic Mixamo rig)
"""
from __future__ import annotations
import json
import os
import shutil
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILES = ("base.obj", "default.mhskel", "default_weights.mhw", "macro_targets.npz")
RAW = "https://raw.githubusercontent.com/makehumancommunity/makehuman/master/makehuman/"
RAW_FILES = {"base.obj": "data/3dobjs/base.obj", "default.mhskel": "data/rigs/default.mhskel",
             "default_weights.mhw": "data/rigs/default_weights.mhw", "LICENSE.ASSETS.md": "../LICENSE.ASSETS.md"}
WHEEL = "makehuman==1.3.2"
RACES = ("african", "asian", "caucasian")
SKELETONS = ("default", "default_no_toes", "game_engine", "body")
PARAMS = ("gender", "age", "muscle", "weight", "height", "proportions")
DEFAULTS = dict(gender=0.5, age=0.5, muscle=0.5, weight=0.5, height=0.5, proportions=0.5)

_SIDE = lambda names: [n + s for n in names for s in (".L", ".R")]
KEEP = {
    "body": ["root", "spine05", "spine04", "spine03", "spine02", "spine01", "neck01", "head"] +
            _SIDE(["clavicle", "upperarm01", "lowerarm01", "wrist", "upperleg01", "lowerleg01", "foot", "toe1-1"]) + ["pelvis.L", "pelvis.R"],
    "game_engine": ["root", "spine05", "spine04", "spine03", "spine02", "spine01", "neck01", "neck02", "neck03", "head", "jaw"] +
                   _SIDE(["clavicle", "shoulder01", "upperarm01", "upperarm02", "lowerarm01", "lowerarm02", "wrist"] +
                         ["finger%d-%d" % (f, j) for f in range(1, 6) for j in range(1, 4)] +
                         ["pelvis", "upperleg01", "lowerleg01", "foot", "toe1-1"]),
}


# ------------------------------------------------------------------ assets
def assets_dir(d=None):
    return d or os.environ.get("SFS_MAKEHUMAN") or os.path.join(ROOT, "assets", "makehuman")


def have_assets(d=None):
    d = assets_dir(d)
    return all(os.path.isfile(os.path.join(d, f)) for f in FILES)


def _macro_subset(npz_path, out_path):
    z = np.load(npz_path, allow_pickle=False)        # plain arrays only - no pickled objects are ever loaded
    keep = {k: z[k] for k in z.files if k.startswith("targets/macrodetails/")}
    if not keep:
        raise ValueError("%s has no targets/macrodetails/* arrays" % npz_path)
    np.savez_compressed(out_path, **keep)
    return len(keep) // 2


def setup(dest=None, src=None, log=print):
    """get the CC0 assets into dest.  src: a folder holding base.obj, default.mhskel, default_weights.mhw and
    targets.npz (or macro_targets.npz) - e.g. a MakeHuman data folder; otherwise download (GitHub raw + pip)."""
    dest = assets_dir(dest)
    os.makedirs(dest, exist_ok=True)
    if src:
        def find(name):
            for root, _, files in os.walk(src):
                if name in files:
                    return os.path.join(root, name)
        for f in ("base.obj", "default.mhskel", "default_weights.mhw", "LICENSE.ASSETS.md"):
            p = find(f)
            if p:
                shutil.copyfile(p, os.path.join(dest, f))
            elif f != "LICENSE.ASSETS.md":
                raise FileNotFoundError("%s not found under %s" % (f, src))
        p = find("macro_targets.npz") or find("targets.npz")
        if not p:
            raise FileNotFoundError("targets.npz not found under %s" % src)
        n = _macro_subset(p, os.path.join(dest, "macro_targets.npz"))
        log("MakeHuman assets copied from %s -> %s (%d macro targets)" % (src, dest, n))
    else:
        import urllib.request, subprocess, sys, tempfile, zipfile
        for f, rel in RAW_FILES.items():
            url = RAW + rel if not rel.startswith("../") else RAW.rsplit("makehuman/", 1)[0] + rel[3:]
            log("download %s" % url)
            with urllib.request.urlopen(url, timeout=120) as r, open(os.path.join(dest, f), "wb") as o:
                o.write(r.read())
        tmp = tempfile.mkdtemp(prefix="sfs_mh_")
        try:
            log("pip download %s --no-deps (only data/targets.npz is used; MakeHuman's code is not installed)" % WHEEL)
            subprocess.check_call([sys.executable, "-m", "pip", "download", WHEEL, "--no-deps", "-d", tmp, "-q"])
            whl = [os.path.join(tmp, f) for f in os.listdir(tmp) if f.endswith(".whl")][0]
            with zipfile.ZipFile(whl) as z:
                with z.open("makehuman/data/targets.npz") as s, open(os.path.join(tmp, "targets.npz"), "wb") as o:
                    shutil.copyfileobj(s, o)
            n = _macro_subset(os.path.join(tmp, "targets.npz"), os.path.join(dest, "macro_targets.npz"))
            log("macro targets: %d" % n)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    with open(os.path.join(dest, "README.txt"), "w", encoding="utf-8") as f:
        f.write("MakeHuman base assets (CC0 1.0 - see LICENSE.ASSETS.md): base.obj, default.mhskel, default_weights.mhw,\n"
                "macro_targets.npz (the macrodetails/* arrays of MakeHuman's targets.npz).  Used by Sprite Forge Studio's\n"
                "own code (sforge/human.py); no MakeHuman (AGPL-3.0) program code is used.\n")
    return dest


# ------------------------------------------------------------------ readers
def read_obj(path, group="body"):
    """-> (all vertices (n,3) dm, triangles of `group` (m,3), uv per tri corner (m,3,2) or None)"""
    V, VT, F, FT = [], [], [], []
    cur = None
    with open(path, encoding="utf-8", errors="replace") as f:
        for ln in f:
            if ln.startswith("v "):
                V.append([float(x) for x in ln.split()[1:4]])
            elif ln.startswith("vt "):
                VT.append([float(x) for x in ln.split()[1:3]])
            elif ln.startswith("g "):
                cur = ln.split(None, 1)[1].strip()
            elif ln.startswith("f ") and cur == group:
                c = [p.split("/") for p in ln.split()[1:]]
                vi = [int(p[0]) - 1 for p in c]
                ti = [int(p[1]) - 1 if len(p) > 1 and p[1] else -1 for p in c]
                for k in range(1, len(vi) - 1):
                    F.append([vi[0], vi[k], vi[k + 1]]); FT.append([ti[0], ti[k], ti[k + 1]])
    V = np.array(V, float); F = np.array(F, int); FT = np.array(FT, int)
    uv = np.array(VT, float)[FT] if VT and (FT >= 0).all() else None
    return V, F, uv


def read_skel(path):
    d = json.load(open(path, encoding="utf-8"))
    return d


def read_weights(path):
    return json.load(open(path, encoding="utf-8"))["weights"]


# ------------------------------------------------------------------ macro modifiers (re-implemented)
def _clamp01(x):
    return float(min(1.0, max(0.0, x)))


def age_value(a):
    """age as 0..1 slider value, or years (>1): 1 y = 0, 11 y = 0.1875, 25 y = 0.5, 90 y = 1"""
    a = float(a)
    if a <= 1.0:
        return _clamp01(a)
    if a < 11:
        return _clamp01((a - 1) / 10 * 0.1875)
    if a < 25:
        return 0.1875 + (a - 11) / 14 * 0.3125
    return _clamp01(0.5 + (a - 25) / 65 * 0.5)


def macro_weights(p):
    g = _clamp01(p["gender"]); a = age_value(p["age"]); m = _clamp01(p["muscle"]); w = _clamp01(p["weight"])
    h = _clamp01(p["height"]); pr = _clamp01(p["proportions"])
    gen = {"female": 1 - g, "male": g}
    if a < 0.5:
        young = max(0.0, (a - 0.1875) * 3.2)
        age = {"baby": max(0.0, 1 - a * 5.333), "child": max(0.0, min(1.0, 5.333 * a) - young), "young": young, "old": 0.0}
    else:
        old = max(0.0, a * 2 - 1)
        age = {"baby": 0.0, "child": 0.0, "young": 1 - old, "old": old}

    def tri(x, lo, avg, hi):
        if x < 0.5:
            mn = max(0.0, 1 - x * 2); return {lo: mn, avg: 1 - mn, hi: 0.0}
        mx = max(0.0, x * 2 - 1); return {lo: 0.0, avg: 1 - mx, hi: mx}
    mus = tri(m, "minmuscle", "averagemuscle", "maxmuscle")
    wei = tri(w, "minweight", "averageweight", "maxweight")
    hei = {"minheight": max(0.0, 1 - h * 2), "maxheight": max(0.0, h * 2 - 1)}
    pro = {"uncommonproportions": max(0.0, 1 - pr * 2), "idealproportions": max(0.0, pr * 2 - 1)}
    races = p.get("races") or {r: 1.0 / 3 for r in RACES}
    out = {}
    for gk, gv in gen.items():
        for ak, av in age.items():
            if gv * av <= 0:
                continue
            for r, rv in races.items():
                out["targets/macrodetails/%s-%s-%s" % (r, gk, ak)] = rv * gv * av
            for mk, mv in mus.items():
                for wk, wv in wei.items():
                    base = gv * av * mv * wv
                    if base <= 0:
                        continue
                    out["targets/macrodetails/universal-%s-%s-%s-%s" % (gk, ak, mk, wk)] = base
                    for hk, hv in hei.items():
                        if hv > 0:
                            out["targets/macrodetails/height/%s-%s-%s-%s-%s" % (gk, ak, mk, wk, hk)] = base * hv
                    for pk, pv in pro.items():
                        if pv > 0 and ak != "baby":
                            out["targets/macrodetails/proportions/%s-%s-%s-%s-%s" % (gk, ak, mk, wk, pk)] = base * pv
    return out


def morph(V, targets, weights):
    """V (dm) + sum w * target.  targets: npz-like {name.index, name.vector}; vectors int16 in 1e-3 dm."""
    out = V.copy(); used = 0
    for k, w in weights.items():
        if w <= 1e-6 or (k + ".index") not in targets:
            continue
        idx = targets[k + ".index"].astype(np.int64); vec = targets[k + ".vector"].astype(float) * 1e-3
        np.add.at(out, idx, w * vec); used += 1
    return out, used


# ------------------------------------------------------------------ skeleton
def _orient(head, tail):
    y = tail - head; n = np.linalg.norm(y)
    if n < 1e-9:
        return np.eye(3)
    y = y / n
    ref = np.array([0, 0, 1.0]) if abs(y[2]) < 0.9 else np.array([0, 1.0, 0])
    x = np.cross(y, ref); x /= np.linalg.norm(x); z = np.cross(x, y)
    return np.column_stack([x, y, z])


def reduce_skeleton(bones, parent_of, variant):
    """-> (kept bone names in parents-first order, map removed bone -> kept ancestor)"""
    if variant == "default":
        keep = set(bones)
    elif variant == "default_no_toes":
        keep = {b for b in bones if not b.startswith("toe")}
    elif variant in KEEP:
        keep = set(KEEP[variant])
    else:
        raise ValueError("skeleton must be one of %s" % ", ".join(SKELETONS))
    missing = keep - set(bones)
    if missing:
        raise ValueError("skeleton %s: bones %s not in default.mhskel" % (variant, ", ".join(sorted(missing))))
    to = {}
    for b in bones:
        a = b
        while a is not None and a not in keep:
            a = parent_of.get(a)
        to[b] = a or "root"
    order, seen = [], set()

    def visit(b):
        if b in seen:
            return
        p = parent_of.get(b)
        while p is not None and p not in keep:
            p = parent_of.get(p)
        if p is not None:
            visit(p)
        seen.add(b); order.append(b)
    for b in bones:
        if b in keep:
            visit(b)
    return order, to


def build(params=None, skeleton="game_engine", assets=None, name="human", log=print):
    """-> Rig (metres, Y up, faces +Z, grounded) with MakeHuman mesh + weights for the parameters."""
    from .rigrec import Rig, m4
    d = assets_dir(assets)
    if not have_assets(d):
        raise FileNotFoundError("MakeHuman assets not found in %s (run: forge.py human --setup)" % d)
    p = dict(DEFAULTS); p.update({k: v for k, v in (params or {}).items() if v is not None})
    Vall, F, uv = read_obj(os.path.join(d, "base.obj"))
    T = np.load(os.path.join(d, "macro_targets.npz"), allow_pickle=False)
    Vm, used = morph(Vall, T, macro_weights(p))
    sk = read_skel(os.path.join(d, "default.mhskel"))
    joints = sk["joints"]

    def jpos(key):
        return Vm[np.array(joints[key], int)].mean(0)
    bones_all = list(sk["bones"])
    parent_of = {b: sk["bones"][b].get("parent") for b in bones_all}
    order, to = reduce_skeleton(bones_all, parent_of, skeleton)
    head = {b: jpos(sk["bones"][b]["head"]) for b in bones_all}
    tail = {b: jpos(sk["bones"][b]["tail"]) for b in bones_all}
    # mesh: body faces only, unused vertices dropped
    used_v = np.unique(F)
    remap = -np.ones(len(Vm), int); remap[used_v] = np.arange(len(used_v))
    V = Vm[used_v]; Fb = remap[F]
    # weights: merge removed bones into their kept ancestor, keep the 4 largest
    bi = {b: i for i, b in enumerate(order)}
    acc = np.zeros((len(V), len(order)), np.float32)
    for b, lst in read_weights(os.path.join(d, "default_weights.mhw")).items():
        if b not in to:
            continue
        a = np.array(lst, float)
        vi = remap[a[:, 0].astype(int)]; ok = vi >= 0
        np.add.at(acc[:, bi[to[b]]], vi[ok], a[ok, 1])
    J = np.argsort(-acc, axis=1)[:, :4]
    W = np.take_along_axis(acc, J, axis=1).astype(float)
    s = W.sum(1)
    J[s <= 0] = 0; W[s <= 0] = [1, 0, 0, 0]; W = W / W.sum(1, keepdims=True)
    r = Rig(name)
    r.bones = list(order)
    r.parent = np.array([bi[parent_of[b]] if parent_of.get(b) in bi else
                         (bi[to[parent_of[b]]] if parent_of.get(b) else -1) for b in order], int)
    r.bind = np.array([m4(_orient(head[b], tail[b]), head[b]) for b in order], float)
    r.V = V; r.F = Fb; r.J = J; r.W = W
    r.fmat = np.zeros(len(Fb), int)
    r.materials = [dict(name="Skin_Mat", color=[0.86, 0.66, 0.52])]
    r.fuv = uv
    r.meta = dict(source="MakeHuman CC0 base assets + parameters (sforge.human)", hips_index=bi["root"],
                  human=dict(params={k: p[k] for k in PARAMS}, skeleton=skeleton, targets_used=used), convention="makehuman")
    r.apply_global(m4(None, [0, 0, 0]) * np.diag([0.1, 0.1, 0.1, 1.0]))      # decimetres -> metres
    r.ground()
    r._tri_cache = {}
    log("MakeHuman: %d bones (%s), %d verts, %d tris, %.2f m, %d macro targets blended" % (
        len(order), skeleton, len(V), len(Fb), r.height(), used))
    return r


def parse_params(s):
    """"gender=1,age=25,muscle=0.7,weight=0.5,height=0.6,proportions=0.5[,skeleton=game_engine]" -> (params, skeleton)"""
    p, sk = {}, None
    for kv in (s or "").replace(";", ",").split(","):
        if not kv.strip():
            continue
        k, _, v = kv.partition("="); k = k.strip().lower(); v = v.strip()
        if k == "skeleton":
            if v not in SKELETONS:
                raise ValueError("skeleton must be one of %s" % ", ".join(SKELETONS))
            sk = v
        elif k in PARAMS:
            if k == "gender" and v.lower() in ("male", "m", "female", "f"):
                p[k] = 1.0 if v.lower() in ("male", "m") else 0.0
            else:
                p[k] = float(v)
        else:
            raise ValueError("unknown human parameter '%s' (%s, skeleton)" % (k, ", ".join(PARAMS)))
    return p, sk


def fallback_spec(params, name="human"):
    """parametric sforge mannequin with the same intent (used when the MakeHuman assets are missing)."""
    from .spec import CharacterSpec
    p = dict(DEFAULTS); p.update(params or {})
    sp = CharacterSpec(name=name)
    a = age_value(p["age"])
    base_h = 175 if p["gender"] >= 0.5 else 163
    age_k = 0.55 + 0.45 * min(1.0, a / 0.5) if a < 0.5 else 1.0 - 0.04 * (a - 0.5) * 2
    sp.height_cm = float(round(base_h * age_k * (0.88 + 0.24 * p["height"])))
    sp.weight_kg = float(round(sp.height_cm - 105 + 40 * (p["weight"] - 0.5)))
    m, w = p["muscle"], p["weight"]
    sp.build = ("heavy" if w > 0.75 else "muscular" if m > 0.7 else "stocky" if w > 0.6 else "slim" if w < 0.3 else
                "lean" if m < 0.35 else "athletic" if m > 0.55 else "average")
    return sp


def make_library_rig(params=None, skeleton="game_engine", name="mh_human", lib=None, clips=True, log=print, assets=None):
    """build the human, retarget the starter clips onto it, save as library rig `name` (CC0 makehuman preset)."""
    from . import library as L, bonemap as BM, samplerigs as SR
    lib = lib or L.Library(None)
    lib.ensure()
    r = build(params, skeleton, assets, name, log)
    rec = BM.detect(r)
    if clips:
        SR.add_clips(r, rec)
    lic = dict(L.LICENCE_PRESETS["makehuman"])
    r.meta["source_preset"] = "makehuman"
    d = lib.path("rigs", name)
    if os.path.exists(d):
        shutil.rmtree(d)
    lib.save_rig(r, rec, "rigs", lic)
    lib.scan(import_inbox=False, log=log)
    log("library rig '%s' saved (%s convention, %d mapped, missing: %s)" % (name, rec["convention"], len(rec["map"]),
                                                                           ", ".join(rec.get("missing") or []) or "none"))
    return name, r, rec


def main(argv):
    import argparse
    ap = argparse.ArgumentParser(prog="forge.py human", description="v7 MakeHuman mode: a parametric human rig from the CC0 MakeHuman assets -> library rig (use it with build --rig NAME)")
    ap.add_argument("--setup", action="store_true", help="get the CC0 assets (download, or --from DIR)")
    ap.add_argument("--from", dest="src", help="--setup: copy the assets from this folder instead of downloading")
    ap.add_argument("--assets", help="assets folder (default <studio>/assets/makehuman or $SFS_MAKEHUMAN)")
    ap.add_argument("--status", action="store_true", help="say whether the assets are present")
    for k in PARAMS:
        ap.add_argument("--" + k, type=str if k in ("gender", "age") else float,
                        help={"gender": "0 = female .. 1 = male (or male/female)", "age": "0..1 (0.5 = 25 y) or years, e.g. 30",
                              "height": "0..1 (0.5 = average)", "proportions": "0 uncommon .. 0.5 regular .. 1 ideal"}.get(k, "0..1 (0.5 = average)"))
    ap.add_argument("--skeleton", choices=SKELETONS, default="game_engine")
    ap.add_argument("--name", default="mh_human", help="library rig name")
    ap.add_argument("--library", help="library folder")
    ap.add_argument("--no-clips", action="store_true", help="do not retarget the starter clips onto it")
    ap.add_argument("--glb", help="also write this GLB")
    a = ap.parse_args(argv)
    if a.setup:
        setup(a.assets, a.src); return 0
    if a.status:
        d = assets_dir(a.assets)
        print("MakeHuman assets: %s in %s" % ("present" if have_assets(d) else "MISSING (forge.py human --setup)", d)); return 0
    params = {}
    for k in PARAMS:
        v = getattr(a, k)
        if v is not None:
            params[k] = (1.0 if str(v).lower() in ("male", "m") else 0.0 if str(v).lower() in ("female", "f") else float(v))
    from . import library as L
    lib = L.Library(a.library or None)
    if not have_assets(a.assets):
        print("MakeHuman assets missing (%s) - FALLBACK: the parametric sforge mannequin is used instead.\n"
              "  get them: forge.py human --setup   (CC0, ~3 MB + 30 MB pip download, kept: ~28 MB)\n"
              "  or import a MakeHuman export: forge.py library add my_human.fbx --preset makehuman" % assets_dir(a.assets))
        sp = fallback_spec(params, a.name)
        print("  fallback mannequin spec: height_cm=%s weight_kg=%s build=%s  (forge.py build --mannequin uses a spec like this)"
              % (sp.height_cm, sp.weight_kg, sp.build))
        return 3
    name, r, rec = make_library_rig(params, a.skeleton, a.name, lib, not a.no_clips)
    if a.glb:
        from . import rigrec as RR
        RR.write_glb(r, a.glb, list(r.clips) or None)
        print("GLB -> %s" % a.glb)
    print("use it: forge.py build --rig %s ..." % name)
    return 0

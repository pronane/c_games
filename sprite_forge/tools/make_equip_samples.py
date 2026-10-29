"""Generate the CC0 Equip samples (outfits + props) into a library.   python tools/make_equip_samples.py [LIBRARY_DIR]

outfits/sample_vest    armour vest   - from sample_stocky's torso (Rigify names), inflated; slot Armour, hides torso
outfits/sample_boots   boots         - from sample_lanky's feet + lower shins (Mixamo names), slot Shoes, hides feet
props/sample_sword     sword         - hand_r, blade points forward from the hand
props/sample_shield    round shield  - hand_l
props/sample_cap       cap           - head (fit to the head width)
props/sample_backpack  backpack      - back (scales with height)
Everything is built from boxes / prisms by this script: no third-party content (CC0-1.0).
"""
import os
import sys
import tempfile
import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from sforge import rigrec as RR, library as L, bonemap as BM, equip as EQ   # noqa: E402

CC0 = dict(spdx="CC0-1.0", custom_text="", author="Sprite Forge Studio (procedurally generated)", source_url="",
           redistribution="yes", attribution="", notes="Synthetic Equip sample made by tools/make_equip_samples.py; no third-party content.")


def box(lo, hi):
    x0, y0, z0 = lo; x1, y1, z1 = hi
    V = np.array([[x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0], [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1]], float)
    F = np.array([[0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7], [0, 1, 5], [0, 5, 4], [3, 7, 6], [3, 6, 2], [0, 4, 7], [0, 7, 3], [1, 2, 6], [1, 6, 5]])
    return V, F


def prism(n, r, y0, y1, axis="y", taper=1.0):
    a = np.linspace(0, 2 * np.pi, n, endpoint=False)
    ring0 = np.c_[r * np.cos(a), np.zeros(n), r * np.sin(a)]
    ring1 = np.c_[r * taper * np.cos(a), np.zeros(n), r * taper * np.sin(a)]
    ring0[:, 1] = y0; ring1[:, 1] = y1
    V = np.r_[ring0, ring1, [[0, y0, 0], [0, y1, 0]]]
    F = []
    for i in range(n):
        j = (i + 1) % n
        F += [[i, j, n + j], [i, n + j, n + i], [2 * n, j, i], [2 * n + 1, n + i, n + j]]
    V = np.array(V, float); F = np.array(F)
    if axis == "z":
        V = V[:, [0, 2, 1]]; F = F[:, ::-1]
    return V, F


def static_rig(name, pieces):
    """pieces: [(V, F, material name, colour)] -> 1-bone rig"""
    r = RR.Rig(name)
    r.bones = ["root"]; r.parent = np.array([-1]); r.bind = np.eye(4)[None]
    Vs, Fs, fm, mats = [], [], [], []
    n = 0
    for V, F, mn, col in pieces:
        if mn not in [m["name"] for m in mats]:
            mats.append(dict(name=mn, color=list(col)))
        mi = [m["name"] for m in mats].index(mn)
        Vs.append(V); Fs.append(F + n); fm += [mi] * len(F); n += len(V)
    r.V = np.concatenate(Vs); r.F = np.concatenate(Fs); r.fmat = np.array(fm)
    r.J = np.zeros((len(r.V), 4), int); r.W = np.zeros((len(r.V), 4)); r.W[:, 0] = 1
    r.materials = mats
    r.meta = dict(source="tools/make_equip_samples.py")
    return r


def vnormals(r):
    """smooth normals shared by every vertex at the same position (split / faceted meshes stay closed when inflated)"""
    key = np.round(r.V / 1e-5).astype(np.int64)
    _, gid = np.unique(key, axis=0, return_inverse=True)
    gid = gid.reshape(-1)
    P = r.V[r.F]
    fn = np.cross(P[:, 1] - P[:, 0], P[:, 2] - P[:, 0])
    N = np.zeros((gid.max() + 1, 3))
    for k in range(3):
        np.add.at(N, gid[r.F[:, k]], fn)
    N = N / np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-12)
    return N[gid]


def shell(rig, rec, regions, thick, name, colour, ymax=None):
    """faces of the base mesh in the given canonical regions, pushed out along the normals (a skinned outfit)."""
    import copy
    from sforge.cleanup import keep_faces
    r = copy.deepcopy(rig)
    can = EQ._canon_of(r, rec)
    want = set()
    for g in regions:
        want.update(EQ.REGIONS.get(g, [g]))
    dom = r.J[np.arange(len(r.V)), np.argmax(r.W, axis=1)]
    vin = np.array([can[int(b)] in want for b in dom])
    if ymax is not None:
        vin &= r.V[:, 1] <= ymax
    keep = vin[r.F].sum(1) >= 2
    N = vnormals(r)
    # winding may be inside-out: push AWAY from the centroid of each vertex's bone region
    cen = np.zeros_like(r.V)
    for b in np.unique(dom):
        sel = dom == b; cen[sel] = r.V[sel].mean(0)
    if np.mean(np.sum(N * (r.V - cen), axis=1)) < 0:
        N = -N
    r.V = r.V + thick * N
    keep_faces(r, keep)
    r.fmat = np.zeros(len(r.F), int); r.materials = [dict(name=name, color=list(colour))]
    r.fuv = None; r.fcol = None; r.textures = {}
    r.clips = {}; r.meta = dict(r.meta); r.meta.pop("mesh_parts", None)
    r.name = name
    return r


def main(libdir=None):
    lib = L.Library(libdir or os.path.join(HERE, "library"))
    tmp = tempfile.mkdtemp(prefix="sfs_equip_")
    made = []
    # ---- outfits (skinned, from our own CC0 sample rigs)
    for nm, base, regions, thick, col, hide, slot, ymax in (
            ("sample_vest", "sample_stocky", ["torso", "shoulders"], 0.03, (0.45, 0.47, 0.52), ["torso"], "Armour", None),
            ("sample_boots", "sample_lanky", ["feet", "shins"], 0.02, (0.30, 0.18, 0.10), ["feet"], "Shoes", 0.30)):
        br = lib.load_rig("rigs/" + base); brec = lib.bonemap("rigs/" + base, br)
        if ymax is not None:
            ymax = ymax * br.height() / 1.8
        o = shell(br, brec, regions, thick * br.height() / 1.8, nm, col, ymax)
        p = os.path.join(tmp, nm + ".glb")
        RR.write_glb(o, p, {})
        lib.add_file(p, nm, "outfit", dict(CC0), log=lambda *a: None, hide=hide, slot=slot, orient="off")
        made.append("outfits/" + nm)
    # ---- props (rigid; upright +Y, front +Z, grip = bottom centre)
    steel, wood, leather, red = (0.78, 0.80, 0.84), (0.42, 0.26, 0.12), (0.30, 0.20, 0.12), (0.70, 0.10, 0.12)
    gV, gF = box((-0.015, 0, -0.015), (0.015, 0.13, 0.015))
    uV, uF = box((-0.09, 0.13, -0.02), (0.09, 0.16, 0.02))
    bV, bF = box((-0.025, 0.16, -0.006), (0.025, 0.86, 0.006))
    tV, tF = prism(4, 0.025, 0.86, 0.93, taper=0.05)
    sword = static_rig("sample_sword", [(gV, gF, "Grip", leather), (uV, uF, "Guard", steel), (bV, bF, "Blade", steel), (tV, tF, "Blade", steel)])
    dV, dF = prism(12, 0.26, 0, 0.03, axis="z")
    dV[:, 1] += 0.26
    kV, kF = prism(8, 0.06, 0.03, 0.06, axis="z", taper=0.6); kV[:, 1] += 0.26
    shield = static_rig("sample_shield", [(dV, dF, "Face", red), (kV, kF, "Boss", steel)])
    cV, cF = prism(12, 0.10, 0.0, 0.08, taper=0.75)
    rV, rF = box((-0.10, 0.0, 0.0), (0.10, 0.012, 0.16))
    cap = static_rig("sample_cap", [(cV, cF, "Crown", (0.12, 0.20, 0.55)), (rV, rF, "Brim", (0.12, 0.20, 0.55))])
    pV, pF = box((-0.15, 0.0, -0.16), (0.15, 0.42, 0.0))
    fV, fF = box((-0.11, 0.05, -0.20), (0.11, 0.22, -0.16))
    pack = static_rig("sample_backpack", [(pV, pF, "Bag", (0.20, 0.35, 0.22)), (fV, fF, "Pocket", (0.16, 0.28, 0.18))])
    for r, sock, meta in ((sword, "hand_r", {}), (shield, "hand_l", dict(rotation=[-90, 0, 0])),
                          (cap, "head", dict(fit="head")), (pack, "back", dict(fit="height"))):
        p = os.path.join(tmp, r.name + ".glb")
        RR.write_glb(r, p, {})
        lib.add_file(p, r.name, "prop", dict(CC0), log=lambda *a: None, socket=sock)
        d = lib.path("props", r.name)
        pr = RR.Rig.load(d); pr.meta["prop"].update(meta); pr.save(d)
        made.append("props/" + r.name)
    for m in made:                          # temp-file provenance is meaningless for generated samples
        sj = os.path.join(lib.path(*m.split("/")), "source.json")
        if os.path.exists(sj):
            os.remove(sj)
    lib.scan(import_inbox=False)
    print("Equip samples (CC0) written to %s: %s" % (lib.dir, ", ".join(made)))
    return made


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)

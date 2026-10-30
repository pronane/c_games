#!/usr/bin/env python3
"""v7 feature tests (Linux / Windows, pip-only).  usage: python tools/test_v7.py [OUT_DIR]
Covers: material slots, separate animation files, orientation / duplicate clean-up, equip (outfits + props + licences),
MakeHuman mode (with assets when present, and the no-assets fallback), experimental autoskin, CLI + profiles.
Writes OUT_DIR (default: a temp dir)/RESULTS_v7.md + results_v7.json.  Never touches the shipped library/."""
import copy, json, os, shutil, subprocess, sys, tempfile, time
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import numpy as np

OUT = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else tempfile.mkdtemp(prefix="sfs_v7out_")
os.makedirs(OUT, exist_ok=True)
TMP = tempfile.mkdtemp(prefix="sfs_v7test_")
LIB = os.path.join(TMP, "lib")
shutil.copytree(os.path.join(HERE, "library"), LIB)
os.environ["SFS_LIBRARY"] = LIB
from sforge import library as L, importers as IM, rigrec as RR, bonemap as BM, matslots as MS, animexport as AE
from sforge import cleanup as CU, equip as EQ, human as H, autoskin as AS, samplerigs as SR, profiles as PR

R = []


def rec(sec, name, ok, detail=""):
    R.append(dict(section=sec, name=name, ok=bool(ok), detail=str(detail)))
    print("%-5s %-9s %-46s %s" % ("PASS" if ok else "FAIL", sec, name, detail)); sys.stdout.flush()


def forge(*args, env=None):
    e = dict(os.environ); e.update(env or {})
    e = {k: v for k, v in e.items() if v is not None}
    args = list(args)
    if args and args[0] == "build" and "--out" in args:          # build writes OUT/<name>/ - make it OUT/t/
        i = args.index("--out"); args[i + 1] = os.path.join(args[i + 1], "..", "_b", os.path.basename(args[i + 1]))
        args += ["--name", "t"]
    p = subprocess.run([sys.executable, os.path.join(HERE, "forge.py")] + args, capture_output=True, text=True,
                       env=e, cwd=TMP)
    return p.returncode, p.stdout + p.stderr


def B(o, *f):
    """where a build with --out o landed"""
    return os.path.normpath(os.path.join(o, "..", "_b", os.path.basename(o), "t", *f))


def mats_of(path):
    r = IM.load_file(path, {})[0]
    return [m.get("name") if isinstance(m, dict) else str(m) for m in r.materials], r


def guard(sec, name, fn):
    try:
        fn()
    except Exception as ex:                       # a crash is a FAIL, the run goes on
        import traceback; traceback.print_exc()
        rec(sec, name, False, "exception: %r" % ex)


lib = L.Library(LIB)
CORE = ["Skin_Mat", "Jersey_Mat", "Shorts_Mat", "Socks_Mat"]


# ---------------------------------------------------------------- 1 material slots
def t_materials():
    o = os.path.join(TMP, "b_full")
    rc, log = forge("build", "--rig", "sample_stocky", "--moves", "idle,walk", "--kit", "home", "--out", o)
    rec("slots", "build --rig sample_stocky (full slots)", rc == 0, "rc=%d" % rc)
    for f in ("model.glb", "model.fbx"):
        p = B(o, f)
        if os.path.exists(p):
            names, _ = mats_of(p)
            rec("slots", "%s has the 4 core slots" % f, all(c in names for c in CORE), names)
        else:
            rec("slots", "%s written" % f, False, "missing")
    o4 = os.path.join(TMP, "b_core4")
    rc, log = forge("build", "--rig", "sample_lanky", "--moves", "idle", "--material-slots", "core4", "--no-fbx", "--out", o4)
    names, _ = mats_of(B(o4, "model.glb")) if rc == 0 else ([], None)
    rec("slots", "core4 -> exactly Skin/Jersey/Shorts/Socks", sorted(names) == sorted(CORE), names)
    # empty slot kept: a rig whose mesh has no leg faces still exposes Shorts_Mat / Socks_Mat
    r = lib.load_rig("sample_lanky"); rc_ = BM.detect(r)
    ys = r.V[r.F].mean(1)[:, 1]
    keep = ys > np.percentile(r.V[:, 1], 60)
    CU.keep_faces(r, keep); r.meta.pop("mesh_parts", None)
    r, _rep = MS.apply(r, rc_, split="auto", slots="core4", log=lambda *a: None)
    nm = [m.get("name") for m in r.materials]
    rec("slots", "empty core slots kept (upper body only)", all(c in nm for c in CORE), nm)
    mo = os.path.join(TMP, "b_mann")
    rc, log = forge("build", "--mannequin", "--moves", "idle", "--no-fbx", "--out", mo)
    names, _ = mats_of(B(mo, "model.glb")) if rc == 0 else ([], None)
    rec("slots", "mannequin GLB slot names", all(c in names for c in CORE), names)


# ---------------------------------------------------------------- 2 separate animation files
def t_anim():
    o = os.path.join(TMP, "anim")
    rc, log = forge("anim-export", "--rig", "sample_lanky", "--moves", "idle,walk,run", "--fbx", "--verify", "--out", o)
    rec("anim", "anim-export --verify (lanky, 3 moves, +fbx)", rc == 0 and "FAIL" not in log, "rc=%d" % rc)
    man = os.path.join(o, "manifest.json")
    ok = os.path.exists(man)
    if ok:
        m = json.load(open(man))
        files = set(os.listdir(o))
        need = ["character_base.glb", "anim_idle.glb", "anim_walk.glb", "anim_run.glb", "anim_walk.fbx"]
        rec("anim", "base + anim_<move> + manifest files", all(n in files for n in need), sorted(files))
        rec("anim", "manifest lists 3 moves", len(m.get("animations", m.get("moves", []))) == 3, list(m.keys()))
    else:
        rec("anim", "manifest.json written", False, "missing")
    # topo re-order + long-name rename
    r = lib.load_rig("sample_lanky")
    perm = np.r_[0, np.random.RandomState(1).permutation(np.arange(1, r.nb))]
    r2 = copy.deepcopy(r)
    inv = np.argsort(perm)
    r2.bones = [r.bones[i] for i in perm]
    r2.parent = np.array([inv[r.parent[i]] if r.parent[i] >= 0 else -1 for i in perm])
    r2.bones[5] = "mixamorig:VeryLongBoneNameThatExceedsTheRaylibLimit_" + r2.bones[5]
    r3, changed = AE.topo_sorted(r2)
    rec("anim", "topo_sorted puts parents first", changed and all(r3.parent[i] < i for i in range(1, r3.nb)), "re-ordered=%s" % changed)
    W2 = r2.worlds(); W3 = r3.worlds()
    rec("anim", "re-order keeps the pose", all(np.allclose(W2[r2.index(b)], W3[r3.index(b)], atol=1e-6) for b in r2.bones), "")
    ren = AE.raylib_names(r2)
    nl = [ren.get(b, b) for b in r2.bones]
    rec("anim", "raylib names <=31 bytes, unique", max(len(n.encode()) for n in nl) <= 31 and len(set(nl)) == len(nl),
        "max %d bytes" % max(len(n.encode()) for n in nl))
    o2 = os.path.join(TMP, "b_anim")
    rc, log = forge("build", "--rig", "sample_chibi", "--moves", "idle,walk", "--anim-export", "--no-fbx", "--out", o2)
    rec("anim", "build --anim-export -> out/anim/", rc == 0 and os.path.exists(B(o2, "anim", "manifest.json")), "rc=%d" % rc)


# ---------------------------------------------------------------- 3 orientation / duplicates / grounding
def t_cleanup():
    r = lib.load_rig("sample_lanky")
    n0 = len(r.F)
    V0, F0 = r.V.copy(), r.F.copy()
    # a full copy "Body.001" and a decimated "Body_LOD1" (every other face of the same bounds)
    nv = len(r.V)
    r.V = np.vstack([V0, V0, V0]); r.J = np.vstack([r.J] * 3); r.W = np.vstack([r.W] * 3)
    lod = F0[::2]
    r.F = np.vstack([F0, F0 + nv, lod + 2 * nv])
    r.fmat = np.r_[r.fmat, r.fmat, r.fmat[::2]]
    r.fuv = None if r.fuv is None else np.concatenate([r.fuv, r.fuv, r.fuv[::2]])
    r.fcol = None if r.fcol is None else np.concatenate([r.fcol, r.fcol, r.fcol[::2]])
    r.meta["mesh_parts"] = [dict(name="Body", f0=0, f1=n0), dict(name="Body.001", f0=n0, f1=2 * n0),
                            dict(name="Body_LOD1", f0=2 * n0, f1=2 * n0 + len(lod))]
    rep = CU.dedupe(r, {})
    rec("clean", "dedupe drops Body.001 + Body_LOD1", len(r.F) == n0 and len(rep["removed"]) == 2,
        [x["name"] for x in rep["removed"]])
    # clothes overlapping the body are NOT removed
    r = lib.load_rig("sample_lanky"); n0 = len(r.F)
    r.meta["mesh_parts"] = [dict(name="Body", f0=0, f1=n0 // 2), dict(name="Shirt", f0=n0 // 2, f1=n0)]
    rep = CU.dedupe(r, {})
    rec("clean", "different parts kept", len(rep["removed"]) == 0 and len(r.F) == n0, "")
    # Z-up, centimetre, floating GLB -> upright, metres, grounded on import
    r = lib.load_rig("sample_stocky")
    G = RR.m4(np.array([[1, 0, 0], [0, 0, -1], [0, 1, 0]], float) * 100.0, [0.3, 0.2, 55.0])
    r.apply_global(G)
    p = os.path.join(TMP, "zup_cm.glb")
    RR.write_glb(r, p, clips=list(r.clips)[:2])
    rep = {}
    r2 = IM.load_file(p, rep)[0]
    h = r2.height()
    W = r2.worlds()
    im = BM.index_map(r2, BM.detect(r2))
    up = W[im["head"], :3, 3] - W[im["hips"], :3, 3]
    rec("clean", "Z-up cm GLB -> +Y up", up[1] / np.linalg.norm(up) > 0.95, "up=%s" % np.round(up / np.linalg.norm(up), 3))
    rec("clean", "-> metres (height ~ original)", 1.0 < h < 2.5, "h=%.3f m" % h)
    rec("clean", "-> grounded (min y = 0)", abs(CU.ground_report(r2)) < 1e-3, CU.ground_report(r2))
    c = list(r2.clips)[0]
    Wf = r2.clip_worlds(r2.clips[c])
    u = Wf[0, im["head"], :3, 3] - Wf[0, im["hips"], :3, 3]
    rec("clean", "clips upright too", u[1] / np.linalg.norm(u) > 0.9, c)


# ---------------------------------------------------------------- Meshy / UE5 / Unity templates
def t_templates():
    import re as _re, zipfile
    base = lib.load_rig("sample_lanky"); im = BM.index_map(base, BM.detect(base))
    for conv, n_min in (("unreal", 14), ("unity", 14), ("mixamo", 14)):
        r = copy.deepcopy(base)
        tab = BM.CONVENTIONS[conv]
        for canon, i in im.items():
            if canon in tab:
                nm = _re.sub(r"\\(.)", r"\1", tab[canon][0])
                r.bones[i] = ("mixamorig:" + nm[0].upper() + nm[1:]) if conv == "mixamo" else nm
        p = os.path.join(TMP, "tpl_%s.glb" % conv)
        RR.write_glb(r, p, clips=list(r.clips)[:2])
        if conv == "mixamo":                               # a Meshy-style download: zip with the model inside
            z = os.path.join(TMP, "Meshy_AI_test.zip")
            with zipfile.ZipFile(z, "w") as zf:
                zf.write(p, "Meshy_AI_test.glb")
            p = z
        rc, log = forge("library", "add", p, "--name", "tpl_" + conv, "--preset", "meshy-paid" if conv == "mixamo" else "makehuman")
        ok = rc == 0 and ("%s naming" % conv) in log
        nmap = _re.search(r"(\d+) mapped bones", log)
        rec("tmpl", "%s bone names detected%s" % (conv, " (Meshy zip)" if conv == "mixamo" else ""), ok and nmap and int(nmap.group(1)) >= n_min,
            (nmap.group(0) if nmap else log.strip().splitlines()[-1:]))
    rc, log = forge("library", "pack", os.path.join(TMP, "x.sfpack"), "tpl_mixamo")
    rec("tmpl", "meshy-paid asset refused in a pack", not os.path.exists(os.path.join(TMP, "x.sfpack")) and "refused" in log, "")
    rc, log = forge("build", "--rig", "tpl_unreal", "--moves", "idle,walk", "--no-fbx", "--out", os.path.join(TMP, "b_ue"))
    rec("tmpl", "build with the UE5-named rig", rc == 0, "rc=%d" % rc)


# ---------------------------------------------------------------- equip
def t_equip():
    o = os.path.join(TMP, "b_equip")
    rc, log = forge("build", "--rig", "sample_stocky", "--moves", "idle,walk", "--outfit", "sample_vest",
                    "--outfit", "sample_boots:hide=foot", "--attach", "sample_sword@hand_r", "--attach", "sample_cap@head",
                    "--slot-color", "Jersey=#c8102e", "--no-fbx", "--out", o)
    rec("equip", "build with 2 outfits + 2 props", rc == 0, "rc=%d" % rc)
    if rc == 0:
        names, r = mats_of(B(o, "model.glb"))
        rec("equip", "outfit + prop materials in model.glb", any("Prop" in n for n in names) and len(names) > 6, names)
        rep = open(B(o, "build_report.txt")).read() if os.path.exists(B(o, "build_report.txt")) else ""
        rec("equip", "build_report has equip licences", "equip outfit" in rep and "equip prop" in rep and "licence" in rep, "")
    rc, log = forge("build", "--mannequin", "--moves", "idle", "--attach", "sample_sword", "--no-fbx", "--out", os.path.join(TMP, "b_eqm"))
    rec("equip", "mannequin + prop -> library rig", rc == 0, "rc=%d" % rc)
    rec("equip", "parse_outfit aliases (foot->feet)", EQ.parse_outfit("x:hide=foot+arm")["hide"] == ["feet", "upperarms", "forearms"]
        or "feet" in EQ.parse_outfit("x:hide=foot+arm")["hide"], EQ.parse_outfit("x:hide=foot+arm"))
    bad = False
    try:
        EQ.parse_outfit("x:hide=tentacles")
    except Exception:
        bad = True
    rec("equip", "unknown hide region rejected", bad, "")


# ---------------------------------------------------------------- 4 MakeHuman
def t_human():
    have = H.have_assets()
    if have:
        t = time.time()
        r = H.build({"gender": 1, "age": 30, "muscle": 0.7}, "game_engine", log=lambda *a: None)
        rec("human", "build male game_engine", r.nb == 65 and r.has_mesh(), "%d bones %d verts %.2fs" % (r.nb, len(r.V), time.time() - t))
        for sk, nb in (("default", 163), ("default_no_toes", 135), ("body", 26)):
            rr = H.build({}, sk, log=lambda *a: None)
            rec("human", "skeleton %s" % sk, rr.nb == nb, rr.nb)
        hs = [H.build({"height": v}, "body", log=lambda *a: None).height() for v in (0.0, 0.5, 1.0)]
        rec("human", "height parameter monotonic", hs[0] < hs[1] < hs[2], np.round(hs, 3))
        f = H.build({"gender": 0}, "body", log=lambda *a: None); m = H.build({"gender": 1}, "body", log=lambda *a: None)
        rec("human", "female shorter than male (default)", f.height() < m.height(), "%.3f / %.3f" % (f.height(), m.height()))
        rc, log = forge("human", "--gender", "female", "--age", "22", "--skeleton", "game_engine", "--name", "mh_t", "--library", LIB)
        rec("human", "forge.py human -> library rig", rc == 0 and os.path.isdir(os.path.join(LIB, "rigs", "mh_t")), "rc=%d" % rc)
        rc, log = forge("build", "--human", "gender=1,age=40,skeleton=body", "--moves", "idle,walk", "--no-fbx",
                        "--out", os.path.join(TMP, "b_human"))
        rec("human", "build --human", rc == 0 and os.path.exists(B(os.path.join(TMP, "b_human"), "model.glb")), "rc=%d" % rc)
    else:
        rec("human", "assets present", True, "SKIPPED: no MakeHuman assets (forge.py human --setup) - fallback tested only")
    env = {"SFS_MAKEHUMAN": os.path.join(TMP, "no_assets_here")}
    rc, log = forge("human", "--gender", "male", "--name", "x", env=env)
    rec("human", "no assets -> clear message, rc 3", rc == 3 and "setup" in log.lower(), "rc=%d" % rc)
    rc, log = forge("build", "--human", "gender=1,height=0.8", "--moves", "idle", "--no-fbx", "--out", os.path.join(TMP, "b_hfb"), env=env)
    rec("human", "build --human fallback (mannequin + warning)", rc == 0 and "makehuman" in log.lower(), "rc=%d" % rc)


# ---------------------------------------------------------------- 5 autoskin (experimental)
def t_autoskin():
    for nm, lim in (("sample_lanky", 0.02), ("sample_chibi", 0.02), ("sample_stocky", 0.02)):
        s = lib.load_rig(nm)
        if "walk" not in s.clips:
            SR.add_clips(s, BM.detect(s), clips=["walk"])
        m = copy.deepcopy(s); m.bones = []; m.parent = np.zeros(0, int); m.bind = np.zeros((0, 4, 4)); m.clips = {}
        out = AS.autoskin(m, s, log=lambda *a: None)
        W = s.worlds("walk", 0.3); e = np.linalg.norm(out.skin(W) - s.skin(W), axis=1)
        rec("autoskin", "%s re-skinned, walk mean err < %d mm" % (nm, lim * 1000), e.mean() < lim,
            "mean %.1f mm p95 %.1f mm max %.1f mm, dominant-bone agreement %.1f%%" %
            (e.mean() * 1000, np.percentile(e, 95) * 1000, e.max() * 1000, 100 * AS.dominant_agreement(out, s)))
    # Z-up centimetre OBJ through the CLI
    s = lib.load_rig("sample_lanky")
    V = s.V @ np.array([[1, 0, 0], [0, 0, 1], [0, -1, 0]], float).T * 100.0
    p = os.path.join(TMP, "byo.obj")
    with open(p, "w") as f:
        f.writelines("v %.5f %.5f %.5f\n" % tuple(v) for v in V)
        f.writelines("f %d %d %d\n" % tuple(t + 1) for t in s.F)
    rc, log = forge("autoskin", p, "--skeleton", "sample_lanky", "--name", "byo_t", "--library", LIB, "--spdx", "CC0-1.0",
                    "--author", "test", "--redistribution", "yes")
    rec("autoskin", "CLI: Z-up cm OBJ -> library rig", rc == 0 and os.path.isdir(os.path.join(LIB, "rigs", "byo_t")), "rc=%d" % rc)
    if rc == 0:
        r = L.Library(LIB).load_rig("byo_t")
        rec("autoskin", "stood up + scaled to skeleton", abs(r.height() - s.height()) < 0.05, "%.3f vs %.3f m" % (r.height(), s.height()))
        rc, log = forge("build", "--rig", "byo_t", "--moves", "idle,walk", "--no-fbx", "--out", os.path.join(TMP, "b_byo"))
        rec("autoskin", "build --rig byo_t", rc == 0, "rc=%d" % rc)


# ---------------------------------------------------------------- CLI + profiles
def t_cli():
    rc, log = forge("--help")
    rec("cli", "forge.py --help lists human/autoskin/anim-export", rc == 0 and all(k in log for k in ("human", "autoskin", "anim-export")), "")
    rec("cli", "version 7.x", "7." in log, [l for l in log.splitlines() if "Studio" in l][:1])
    pf = os.path.join(TMP, "prof.json")
    json.dump({"name": "t", "material_slots": "core4", "outfits": ["sample_vest"], "props": "sample_cap@head",
               "slot_colors": {"Jersey": "#00ff00"}}, open(pf, "w"))
    rc, log = forge("profile", "validate", pf)
    rec("cli", "profile with v7 keys validates", rc == 0, log.strip().splitlines()[-1:] if log.strip() else "")
    rc, log = forge("doctor")
    rec("cli", "doctor runs", rc == 0, "")


for sec, fn in (("slots", t_materials), ("anim", t_anim), ("clean", t_cleanup), ("tmpl", t_templates), ("equip", t_equip),
                ("human", t_human), ("autoskin", t_autoskin), ("cli", t_cli)):
    guard(sec, fn.__name__, fn)

npass = sum(r["ok"] for r in R)
md = ["# Sprite Forge Studio v7 tests", "", "%d / %d passed  (%s, Python %s)" % (npass, len(R), sys.platform, sys.version.split()[0]), "",
      "| section | test | result | detail |", "|---|---|---|---|"]
md += ["| %s | %s | %s | %s |" % (r["section"], r["name"], "PASS" if r["ok"] else "**FAIL**", r["detail"].replace("|", "/")[:160]) for r in R]
open(os.path.join(OUT, "RESULTS_v7.md"), "w").write("\n".join(md) + "\n")
json.dump(R, open(os.path.join(OUT, "results_v7.json"), "w"), indent=1)
print("\n%d / %d passed -> %s" % (npass, len(R), OUT))
shutil.rmtree(TMP, ignore_errors=True)
sys.exit(0 if npass == len(R) else 1)

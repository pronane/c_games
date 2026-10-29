#!/usr/bin/env python3
"""v6 library tests (Linux / Windows, pip-only).  usage: python tools/test_library_v6.py [OUT_DIR]
Writes OUT_DIR (default previews_v6/)/RESULTS.md + results.json + contact images.
Optional oracle: SFS_BPY_PYTHON=<python with the pip 'bpy' module> (Blender 4.x) re-exports our sample GLBs as FBX
with Blender's exporter (Mixamo / Rigify / Unity bone names, leaf bones, embedded textures) and reads them back."""
import json, os, shutil, subprocess, sys, tempfile, time, zipfile
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import numpy as np
from PIL import Image, ImageDraw

OUT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "previews_v6"))
os.makedirs(OUT, exist_ok=True)
TMP = tempfile.mkdtemp(prefix="sfs_v6test_")
os.environ["SFS_LIBRARY"] = os.path.join(TMP, "lib")         # never touch the shipped library/
from sforge import library as L, importers as IM, rigrec as RR, retarget as RT, bonemap as BM, fbx as FBX

R = []           # (section, name, ok, detail)


def rec(sec, name, ok, detail=""):
    R.append(dict(section=sec, name=name, ok=bool(ok), detail=detail))
    print("%-5s %-10s %-44s %s" % ("PASS" if ok else "FAIL", sec, name, detail)); sys.stdout.flush()


def forge(*args):
    p = subprocess.run([sys.executable, os.path.join(HERE, "forge.py")] + list(args), capture_output=True, text=True,
                       env=dict(os.environ), cwd=TMP)
    return p.returncode, p.stdout + p.stderr


def compare(src, r):
    common = [b for b in src.bones if b in r.bones]
    si = [src.index(b) for b in common]; ri = [r.index(b) for b in common]
    if not common:
        return 0, 1e9, 1e9, False, 0.0
    # the importer grounds every model (lowest point -> y=0); remove that constant shift, report it separately
    sh = np.median(r.bind[ri, :3, 3] - src.bind[si, :3, 3], axis=0)
    sh = np.where(np.abs(sh) > 1e-4, sh, 0.0)
    bind = float(np.abs(src.bind[si, :3, 3] + sh - r.bind[ri, :3, 3]).max()) * 1000
    clip_err, frames_ok = 0.0, True
    for c in src.clips:
        if c not in r.clips:
            frames_ok = False; continue
        Ws = src.clip_worlds(src.clips[c]); Wr = r.clip_worlds(r.clips[c])
        frames_ok &= (len(Ws) == len(Wr))
        F = min(len(Ws), len(Wr))
        clip_err = max(clip_err, float(np.linalg.norm(Ws[:F][:, si, :3, 3] + sh - Wr[:F][:, ri, :3, 3], axis=-1).max()) * 1000)
    return len(common), bind, clip_err, frames_ok, float(np.linalg.norm(sh)) * 1000


t0 = time.time()
STARTER = os.path.join(HERE, "packs", "sfs_starter_cc0.sfpack")
lib = L.Library()
# ---------------------------------------------------------------- A. packs + licences
rep = L.verify(STARTER)
rec("pack", "starter pack verifies", rep["ok"], "%d assets" % len(rep["manifest"]["assets"]) if rep["ok"] else "; ".join(rep["problems"]))
rc, out = forge("library", "install", STARTER)
rec("pack", "install refused without acknowledgement", rc != 0 and "acknowledged" in out, out.strip().splitlines()[-1][:90])
rc, out = forge("library", "install", STARTER, "--accept-licences")
lib = L.Library()
rec("pack", "install with --accept-licences", rc == 0 and len(lib.all_assets()) == len(rep["manifest"]["assets"]), "%d assets" % len(lib.all_assets()))
inst = lib.licence("sample_lanky").get("installed_from", {})
rec("pack", "install records provenance + acknowledgement", inst.get("licences_acknowledged") and inst.get("pack_sha256"), inst.get("pack_name", ""))
rc, out = forge("library", "install", STARTER, "--accept-licences")
rec("pack", "re-install identical content is skipped", rc == 0 and "identical" in out and len(L.Library().all_assets()) == len(lib.all_assets()))
# tamper: change one byte of a rig file
tam = os.path.join(TMP, "tampered.sfpack")
with zipfile.ZipFile(STARTER) as zi, zipfile.ZipFile(tam, "w") as zo:
    for it in zi.infolist():
        data = zi.read(it.filename)
        if it.filename.endswith("sample_lanky/rig.json"):
            data = data.replace(b'"name"', b'"nAme"', 1)
        zo.writestr(it, data)
rv = L.verify(tam)
rec("pack", "tampered file is detected (sha256)", not rv["ok"] and any("sha256" in p or "checksum" in p for p in rv["problems"]), (rv["problems"] or ["-"])[0][:80])
evil = os.path.join(TMP, "evil.sfpack")
with zipfile.ZipFile(STARTER) as zi, zipfile.ZipFile(evil, "w") as zo:
    man = json.loads(zi.read("pack.json"))
    for it in zi.infolist():
        if it.filename != "pack.json":
            zo.writestr(it, zi.read(it.filename))
    man["assets"][0]["files"]["../../evil.txt"] = "0" * 64
    zo.writestr("../../evil.txt", "x"); zo.writestr("pack.json", json.dumps(man))
rv = L.verify(evil)
rec("pack", "path traversal entry is refused", not rv["ok"], (rv["problems"] or ["-"])[0][:80])
nolic = os.path.join(TMP, "nolic.sfpack")
with zipfile.ZipFile(STARTER) as zi, zipfile.ZipFile(nolic, "w") as zo:
    man = json.loads(zi.read("pack.json"))
    for it in zi.infolist():
        if it.filename != "pack.json":
            zo.writestr(it, zi.read(it.filename))
    man["assets"][0]["licence"]["redistribution"] = "unknown"
    zo.writestr("pack.json", json.dumps(man))
rv = L.verify(nolic)
rec("pack", "pack with a non-redistributable asset is refused", not rv["ok"], (rv["problems"] or ["-"])[0][:80])

# own-file import with unknown licence -> pack refused; override needs a name; then OK + recorded
g = os.path.join(TMP, "mine.glb"); RR.write_glb(lib.load_rig("sample_stocky"), g, ["idle", "walk"])
rc, out = forge("library", "add", g, "--name", "my_rig")
rec("licence", "add without licence warns", rc == 0 and "cannot be exported in a pack" in out)
rc, out = forge("library", "pack", os.path.join(TMP, "p1.sfpack"), "my_rig")
rec("licence", "pack refuses licence=unknown", rc != 0 and "refused" in out)
rc, out = forge("library", "pack", os.path.join(TMP, "p1.sfpack"), "my_rig", "--i-own-the-rights", "my_rig")
rec("licence", "'I own the rights' needs --by", rc != 0 and "--by" in out)
rc, out = forge("library", "pack", os.path.join(TMP, "p1.sfpack"), "my_rig", "--i-own-the-rights", "my_rig", "--by", "Test User")
rv = L.verify(os.path.join(TMP, "p1.sfpack")) if rc == 0 else {"ok": False, "manifest": None}
ov = rv["manifest"]["assets"][0]["licence"].get("rights_override", {}) if rv.get("manifest") else {}
rec("licence", "override recorded in the pack", rc == 0 and rv["ok"] and ov.get("by") == "Test User", ov.get("statement", "")[:60])
# derived clips from a non-redistributable source block the target
forge("library", "licence", "sample_moves", "--redistribution", "no")
forge("retarget", "sample_moves:wave", "sample_chibi", "--save", "--prefix", "mv_")
rc, out = forge("library", "pack", os.path.join(TMP, "p2.sfpack"), "sample_chibi")
rec("licence", "clips retargeted from a 'no' source block packing", rc != 0 and "contains clips" in out)
rc, out = forge("library", "clips-drop", "sample_chibi", "from:sample_moves")
rc2, out2 = forge("library", "pack", os.path.join(TMP, "p2.sfpack"), "sample_chibi")
rec("licence", "clips-drop clears the block", rc == 0 and rc2 == 0)
forge("library", "licence", "sample_moves", "--redistribution", "yes")
# full round trip: pack everything -> install into a second library -> identical
full = os.path.join(TMP, "full.sfpack")
rc, out = forge("library", "pack", full, "--all", "--pack-name", "roundtrip")
lib2 = L.Library(os.path.join(TMP, "lib2"))
lib2.install(full, accept=True, log=lambda s: None)
same = all(open(os.path.join(lib.path(k, n), "rig.json"), "rb").read() == open(os.path.join(lib2.path(k, n), "rig.json"), "rb").read()
           for k, n in lib.all_assets() if k != "kits")
rec("pack", "pack --all -> install elsewhere: identical rigs", rc == 0 and same and len(lib2.all_assets()) == len(lib.all_assets()),
    "%d assets" % len(lib2.all_assets()))

# ---------------------------------------------------------------- B. our own GLB / FBX round trip
RIGS = ["sforge_mannequin", "sample_chibi", "sample_lanky", "sample_stocky", "sample_moves"]
for n in RIGS:
    src = lib.load_rig(n)
    g = os.path.join(TMP, n + ".glb"); f = os.path.join(TMP, n + ".fbx")
    RR.write_glb(src, g, list(src.clips)); FBX.write_fbx_from_glb(g, f)
    for p in (g, f):
        r, rc_, rp = IM.load_file(p)
        nc, be, ce, fo, shm = compare(src, r)
        rec("import", "%s %s" % (n, os.path.splitext(p)[1]), be < 0.5 and ce < 1.0 and fo and nc == len(src.bones) and rc_["convention"] == lib.bonemap(n)["convention"],
            "%d/%d bones, %d takes, bind err %.3f mm, clip err %.2f mm, %s names%s" % (
                nc, len(src.bones), len(r.clips), be, ce, rc_["convention"], (", grounding shift %.1f mm" % shm) if shm else ""))

# ---------------------------------------------------------------- C. Blender oracle (optional)
bpy_py = os.environ.get("SFS_BPY_PYTHON")
if bpy_py and os.path.exists(bpy_py):
    for n in ("sample_chibi", "sample_lanky", "sample_stocky"):
        src = lib.load_rig(n); g = os.path.join(TMP, n + ".glb"); f = os.path.join(TMP, n + "_blender.fbx")
        subprocess.run([bpy_py, os.path.join(HERE, "tools", "blender_glb_to_fbx.py"), g, f, "--leaf", "--embed"], capture_output=True, text=True)
        if not os.path.exists(f):
            rec("blender", n, False, "Blender export failed"); continue
        r, rc_, rp = IM.load_file(f)
        nc, be, ce, fo, shm = compare(src, r)
        tex = sum(1 for m in r.materials if m.get("texture") is not None)
        rec("blender", "%s (Blender 4 FBX, leaf bones)" % n, be < 1.0 and ce < 1.0 and fo and rc_["convention"] == lib.bonemap(n)["convention"],
            "%s names, %d/%d bones common, bind %.3f mm, clips %.2f mm, %d textured mats" % (rc_["convention"], nc, len(src.bones), be, ce, tex))
else:
    rec("blender", "oracle skipped (set SFS_BPY_PYTHON)", True, "not run")

# ---------------------------------------------------------------- D. retarget between proportions
pairs = [("sample_moves", "sample_chibi"), ("sample_moves", "sample_stocky"), ("sample_lanky", "sample_chibi"),
         ("sample_chibi", "sample_lanky"), ("sforge_mannequin", "sample_stocky"), ("sample_stocky", "sforge_mannequin")]
for s, t in pairs:
    S = lib.load_rig(s); T = lib.load_rig(t); sr = lib.bonemap(s, S); tr = lib.bonemap(t, T)
    worst = {"dir": 0, "foot": 0, "hip": 0}
    for c in S.clips:
        cl, rp = RT.retarget(S, sr, c, T, tr)
        it = BM.index_map(T, tr)
        W = T.clip_worlds(cl)
        ft = [it[k] for k in ("foot_L", "foot_R", "toe_L", "toe_R") if k in it]
        low = float(np.min(W[:, ft, 1, 3])) - float(np.min(T.bind[ft, 1, 3]))   # lowest foot joint vs. its rest height
        # hip height relative to leg length should match the source's
        isrc = BM.index_map(S, sr); Ws = S.clip_worlds(S.clips[c])
        hs = Ws[:, isrc["hips"], 1, 3] / (S.bind[isrc["hips"], 1, 3] or 1); ht = W[:, it["hips"], 1, 3] / (T.bind[it["hips"], 1, 3] or 1)
        fs = [isrc[k] for k in ("foot_L", "foot_R", "toe_L", "toe_R") if k in isrc]
        lows = float(np.min(Ws[:, fs, 1, 3])) - float(np.min(S.bind[fs, 1, 3]))
        low = low - lows * rp["leg_ratio"]          # what the source does, scaled to the target's legs, is expected
        if os.environ.get("SFS_TEST_VERBOSE"):
            print("   ", c, round(low * 1000, 1), round(lows * 1000, 1))
        worst["dir"] = max(worst["dir"], rp["max_dir_err_deg"]); worst["foot"] = max(worst["foot"], abs(low) * 1000)
        worst["hip"] = max(worst["hip"], float(np.abs(hs - ht).max()))
    rec("retarget", "%s -> %s" % (s, t), worst["dir"] < 1.0 and worst["foot"] < 15 and worst["hip"] < 0.08,
        "leg ratio %.2f, dir err %.2f deg, ground contact %.1f mm off the scaled source, hip-height/leg diff %.3f" % (
            rp["leg_ratio"], worst["dir"], worst["foot"], worst["hip"]))

# ---------------------------------------------------------------- E. builds: 2 profiles + 2 consoles from library rigs
B = os.path.join(TMP, "out")
jobs = [("fighter14", None, "sample_lanky", "sample_gold_black", "victory=sample_moves:spin@speed=1.2"),
        ("platformer", None, "sample_chibi", "", "crouch=sample_moves:squat@trim=0.2-1.0"),
        (None, "gba", "sample_stocky", "sample_red_white", "victory=sample_moves:spin@speed=1.2"),
        (None, "ps1", "sample_lanky", "", "victory=sample_moves:hop@loop=1")]
sheets = []
for prof, con, rig, kit, cm in jobs:
    name = "%s_%s" % (rig, prof or con)
    a = ["build", "--rig", rig, "--out", B, "--name", name, "--clip", cm]
    a += (["--profile", prof] if prof else ["--moves", "idle,walk,run,jump,kick,punch,victory", "--console", con])
    if kit:
        a += ["--kit", kit]
    rc, out = forge(*a)
    d = os.path.join(B, name)
    ok = rc == 0 and os.path.exists(os.path.join(d, "atlas.png")) and os.path.exists(os.path.join(d, "model.fbx"))
    det = "rc %d" % rc
    if ok:
        aj = json.load(open(os.path.join(d, "atlas.json")))
        r, _, _ = IM.load_file(os.path.join(d, "model.fbx"))
        det = "%d sprite frames, model.fbx %d takes" % (len(aj.get("frames", aj)), len(r.clips))
        if con:
            cj = json.load(open(os.path.join(d, "console", "console.json")))
            det += ", console %s" % con
            mg = [f for f in os.listdir(os.path.join(d, "console")) if f.endswith(".glb")]
            if mg:
                cr, _, _ = IM.load_file(os.path.join(d, "console", mg[0]))
                bud = int(cj.get("model", {}).get("max_tris", 0) or cj.get("max_tris", 0) or len(cr.F))
                det += ", console model %d tris" % len(cr.F)
                ok &= len(cr.F) <= max(bud, 1) * 1.01
        ok &= ("lib:" + cm.split("=", 1)[1].split("@")[0]) in out
        sheets.append((name, os.path.join(d, "preview.png")))
    rec("build", name, ok, det)
if os.path.exists(os.path.join(HERE, "previews_v5")) or True:
    ims = [(n, Image.open(p).convert("RGB")) for n, p in sheets if os.path.exists(p)]
    if ims:
        w = max(i.width for _, i in ims); h = sum(i.height for _, i in ims)
        sheet = Image.new("RGB", (w, h), (24, 28, 34)); y = 0
        for _, i in ims:
            sheet.paste(i, (0, y)); y += i.height
        sheet.save(os.path.join(OUT, "library_builds.png"))
# thumbnails of every asset + decimated console models
th = Image.new("RGB", (160 * 6, 190), (236, 239, 244)); dr = ImageDraw.Draw(th)
for i, n in enumerate(RIGS + ["sample_stocky@ps1"]):
    if "@" in n:
        r = RR.decimated(lib.load_rig("sample_stocky"), 600); n2 = "stocky ps1 %d tris" % len(r.F)
    else:
        r = lib.load_rig(n); n2 = n
    im = RR.thumbnail(r, size=160, clip=(list(r.clips) or [None])[min(4, len(r.clips) - 1)] if r.clips else None)
    if not r.has_mesh():
        im = Image.open(os.path.join(lib.path(*lib.find(n)), "thumb.png")).convert("RGB").resize((160, 160))
    th.paste(im.convert("RGB"), (i * 160, 0)); dr.text((i * 160 + 4, 166), n2, fill=(20, 20, 20))
th.save(os.path.join(OUT, "library_assets.png"))

# ---------------------------------------------------------------- summary
ok = sum(1 for r in R if r["ok"]); bad = [r for r in R if not r["ok"]]
json.dump(R, open(os.path.join(OUT, "results.json"), "w"), indent=1)
md = ["# Sprite Forge Studio v6 - library tests", "", "`python tools/test_library_v6.py` on %s, Python %s, %.0f s." % (sys.platform, sys.version.split()[0], time.time() - t0),
      "", "**%d / %d passed**" % (ok, len(R)), "", "| | section | test | detail |", "|---|---|---|---|"]
md += ["| %s | %s | %s | %s |" % ("PASS" if r["ok"] else "**FAIL**", r["section"], r["name"], r["detail"].replace("|", "/")) for r in R]
open(os.path.join(OUT, "RESULTS_tests.md"), "w", encoding="utf-8").write("\n".join(md) + "\n")
shutil.rmtree(TMP, ignore_errors=True)
print("\n%d / %d passed -> %s" % (ok, len(R), OUT))
sys.exit(1 if bad else 0)

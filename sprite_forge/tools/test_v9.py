#!/usr/bin/env python3
"""v9 tests.  usage: python tools/test_v9.py [OUT_DIR]
Unit + regression tests for every v9 feature: expressions / mouth shapes (incl. facial hair), recolour sets / regions /
overlays / folder palette swap, procedural variants (seeded), foot locking IK, frame data, fx passes, normal + emissive
maps, animation blending, multi-character atlas, batch queue, QA checker, LODs + baked model, physics chains, NPC pack,
the forge.py v9 commands, the Studio argv mapping (tkinter) and the Godot / Unity plugins (when the engines / dotnet
are found: SFS_GODOT, SFS_DOTNET).  Mannequins and drawn test faces only - no photo of a real person.
Writes OUT_DIR/RESULTS_v9_tests.md + results_v9.json."""
import json, os, shutil, subprocess, sys, tempfile, time
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import numpy as np
from PIL import Image, ImageDraw

OUT = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else tempfile.mkdtemp(prefix="sfs_v9out_")
os.makedirs(OUT, exist_ok=True)
W = tempfile.mkdtemp(prefix="sfs_v9test_")
R = []
SMALL = ["--frame", "160x200", "--figure-h", "150", "--ground-y", "188"]


def rec(name, ok, detail="", secs=None):
    R.append({"test": name, "ok": bool(ok), "detail": str(detail)[:160], "secs": None if secs is None else round(secs, 2)})
    print("%-4s %-62s %s%s" % ("PASS" if ok else "FAIL", name, str(detail)[:120], "" if secs is None else "  (%.1f s)" % secs), flush=True)


def check(name, fn):
    t = time.time()
    try:
        r = fn()
        ok, det = (r if isinstance(r, tuple) else (r, ""))
    except Exception as e:  # noqa
        import traceback; traceback.print_exc()
        ok, det = False, "%s: %s" % (type(e).__name__, e)
    rec(name, ok, det, time.time() - t)


def forge(args, env=None):
    e = dict(os.environ, SFS_CACHE=os.path.join(W, "cache")); e.update(env or {})
    t = time.time()
    p = subprocess.run([sys.executable, os.path.join(HERE, "forge.py")] + args, capture_output=True, text=True, env=e)
    return p.returncode, p.stdout + p.stderr, time.time() - t


def rd(*p):
    f = os.path.join(*p)
    return open(f, encoding="utf-8").read() if os.path.isfile(f) else ""


# ---------------------------------------------------------------- 1. expressions (unit)
from sforge import expressions as X
def t_expr_map():
    ok = set(X.EXPRESSIONS) == {"neutral", "happy", "angry", "hurt", "shout", "taunt", "blink"}
    got = {m: X.expression_for(m) for m in ("idle", "punch", "hit", "taunt", "victory", "special1")}
    ok &= got["punch"] == "angry" and got["hit"] == "hurt" and got["taunt"] == "taunt" and got["victory"] == "happy" and got["idle"] == "neutral"
    ok &= X.expression_for("punch", X.parse_map("punch=shout")) == "shout"
    sch = X.schedule("idle", 8, True)
    ok &= "blink" in sch and X.schedule("idle", 8, True, blink=False).count("blink") == 0
    return ok, str(got)
check("expressions: 7 faces, auto per-move map, user map, blink", t_expr_map)

def t_visemes():
    v = X.text_to_visemes("Map of you", fps=12)
    names = [x if isinstance(x, str) else x[0] if isinstance(x, (list, tuple)) else x.get("shape", "") for x in (v if isinstance(v, list) else v.get("frames", []))]
    flat = json.dumps(v)
    return all(s in flat for s in ('"mbp"', '"ai"', '"o"', '"fv"')) and set(X.VISEMES) >= {"rest", "mbp", "ai", "e", "o", "u", "fv", "l"}, flat[:100]
check("talk: letters -> mouth shapes (M=mbp, A=ai, O=o, F=fv)", t_visemes)

def t_photo_warp():
    # a DRAWN cartoon face (not a person): every expression must change the face pixels, only inside the face
    im = Image.new("RGBA", (200, 240), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    d.ellipse((50, 40, 150, 160), fill=(225, 180, 150, 255)); d.ellipse((75, 80, 90, 92), fill=(40, 30, 30, 255))
    d.ellipse((110, 80, 125, 92), fill=(40, 30, 30, 255)); d.line((85, 130, 115, 130), fill=(150, 60, 60, 255), width=3)
    d.rectangle((40, 160, 160, 240), fill=(30, 60, 160, 255))
    L = {i: (0, 0) for i in range(33)}
    L[0] = (100, 108); L[2] = (82, 86); L[5] = (118, 86); L[9] = (88, 130); L[10] = (112, 130)
    face = X.face_from_landmarks(L)
    a0 = np.asarray(im).astype(int); diffs = {}
    for e in ("happy", "angry", "hurt", "shout", "taunt", "blink"):
        a = np.asarray(X.warp_face(im, face, X.params_for(e))).astype(int)
        diffs[e] = int((np.abs(a - a0).sum(2) > 30).sum())
        if np.abs(a[175:] - a0[175:]).max() > 0:            # the shirt must not move
            return False, "%s touched pixels below the face" % e
    return all(v > 20 for v in diffs.values()), str(diffs)
check("photo expressions: procedural warp of the drawn face only (estimated)", t_photo_warp)

# ---------------------------------------------------------------- 2. recolour (unit)
from sforge import recolor as RC
def t_rc_parse():
    r = RC.parse("team_red;hair=black")
    ok = tuple(r["top"]) == RC.to_rgb("#c4161c") and "hair" in r
    ov = RC.parse_overlay("top:hoops:#ffffff")
    ok &= ov["kind"] == "hoops"
    ok &= len(RC.all_sets()) >= 20 and all(k in RC.all_sets() for k in ("team_red", "team_blue", "kerry", "egypt_gold", "villain"))
    return ok, "%d sets" % len(RC.all_sets())
check("recolour: sets, region + overlay parsing", t_rc_parse)

def t_rc_spec():
    from sforge.spec import CharacterSpec
    sp = CharacterSpec(name="t"); RC.apply_to_spec(sp, "team_blue;hair=black", "top:stripes:#ffffff")
    return RC.to_rgb(sp.top_colour) == RC.to_rgb("#1c3fb0"), "top_colour=%s" % sp.top_colour
check("recolour: applied to the 3D spec (exact slot colours)", t_rc_spec)

def t_swap():
    im = Image.new("RGBA", (40, 20), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    for x in range(20):
        k = 0.7 + 0.025 * x                                                                  # shaded blue (lightness only)
        d.line((x, 0, x, 19), fill=(int(42 * k), int(91 * k), min(255, int(215 * k)), 255))
    d.rectangle((20, 0, 39, 19), fill=(30, 30, 30, 255))
    out = np.asarray(RC.swap_image(im, [((42, 91, 215), (200, 16, 46))])).astype(int)
    left, right = out[:, :20, :3], out[:, 20:, :3]
    return (left[..., 0] > left[..., 2]).mean() > 0.9 and np.abs(right - 30).max() < 3 and out[5, 2, 0] < out[5, 18, 0] + 40, "red share %.2f" % (left[..., 0] > left[..., 2]).mean()
check("recolour: palette swap keeps shading, leaves other colours", t_swap)

# ---------------------------------------------------------------- 3. variants (unit)
from sforge import variants as VA
from sforge.spec import CharacterSpec
def t_var():
    b = CharacterSpec(name="base")
    a1, _ = VA.vary_spec(b, 5); a2, _ = VA.vary_spec(b, 5); a3, _ = VA.vary_spec(b, 6)
    c, _ = VA.vary_spec(b, 9, "colours")
    same = a1.to_dict() == a2.to_dict(); diff = a1.to_dict() != a3.to_dict()
    only_col = all(c.to_dict()[k] == b.to_dict()[k] for k in ("build", "height_cm", "top", "hair_style"))
    p1, p2 = VA.photo_variant(3), VA.photo_variant(3)
    return same and diff and only_col and p1 == p2, "seeded + vary=colours keeps body/outfit"
check("variants: same seed = same variant, vary limits what changes", t_var)

# ---------------------------------------------------------------- 4. foot locking (unit)
def t_foot():
    from sforge import footlock as FL, anim as AN
    from sforge.build import motion_for
    from sforge.moves import MoveSpec
    m = MoveSpec("walk", "Walk", "F", 10, 10, True, "", "")
    st = AN.states_for(motion_for(m), 10, True)
    b = FL.measure(st, True); new, info = FL.lock(st, True, 10); a = FL.measure(new, True)
    return info["segments"] > 0 and a < b * 0.2, "walk slide %.2f -> %.2f cm" % (b, a)
check("foot lock: 2-bone IK removes planted-foot slide", t_foot)

# ---------------------------------------------------------------- 5. fx / maps / blend (unit)
from sforge import fx as FX, maps as MP, blend as BL
def blob():
    im = Image.new("RGBA", (80, 120), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    d.ellipse((20, 10, 60, 110), fill=(180, 120, 90, 255)); d.ellipse((35, 30, 45, 40), fill=(255, 40, 30, 255))
    return im
def t_fx():
    im = blob(); a0 = np.asarray(im)
    o = np.asarray(FX.apply(im, FX.parse("outline=2")))
    ok = (o[..., 3] > 0).sum() > (a0[..., 3] > 0).sum()
    c = FX.apply(im, FX.parse("cel=3")); nc = len(set(map(tuple, np.asarray(c)[np.asarray(c)[..., 3] > 0][:, :3].tolist())))
    p = np.asarray(FX.apply(im, FX.parse("pixel=4,colors=8")))
    blk = (p[0:4, :, :] == p[0:1, :, :]).all() if p.shape[0] >= 4 else True
    l = np.asarray(FX.apply(im, FX.parse("light=-1:-1:1,rim=0.4")))
    ok &= nc <= 12 and blk and np.abs(l.astype(int) - a0.astype(int)).max() > 10
    return ok, "outline grows, cel %d colours, pixel blocks, light changes" % nc
check("fx: outline / cel / pixel-art / lighting passes", t_fx)
def t_maps():
    n = np.asarray(FX.normal_map(blob()).convert("RGB")).astype(int)
    centre = n[60, 40]; left = n[60, 22]; right = n[60, 58]
    em, n_em = MP.emissive_map(blob(), [(255, 40, 30)])
    ea = np.asarray(em.convert("RGB")).astype(int)
    return centre[2] > 200 and left[0] < 128 < right[0] and ea[35, 40].sum() > 100 and ea[80, 40].sum() < 30, "n centre %s left %s right %s" % (centre, left, right)
check("maps: normal map faces out of the silhouette, emissive picks glow colours", t_maps)
def t_blend():
    p = BL.parse("idle>walk:3,punch>idle")
    f = BL.crossfade(blob(), blob().transpose(Image.FLIP_LEFT_RIGHT), 3)
    return p == [("idle", "walk", 3), ("punch", "idle", 3)] and len(f) == 3, str(p)
check("blend: parse + crossfade", t_blend)

# ---------------------------------------------------------------- 6. physics + npc (unit)
def t_phys():
    from sforge import physics as PH, anim as AN
    from sforge.build import motion_for
    from sforge.moves import MoveSpec
    sp = CharacterSpec(name="p", hair_style="ponytail", accessories="cape,scarf")
    ch = PH.chains_for(sp)
    m = MoveSpec("walk", "Walk", "F", 8, 10, True, "", "")
    st = AN.states_for(motion_for(m), 8, True)
    sim = PH.simulate(ch, st, 0.1, True)
    tip = [np.asarray(sim[i][0])[-1] for i in range(len(st))]
    mv = max(float(np.linalg.norm(tip[i] - tip[0])) for i in range(len(tip)))
    return len(ch) >= 3 and mv > 0.01, "%d chains (%s), tip moves %.3f" % (len(ch), ",".join(c.name for c in ch), mv)
check("physics: ponytail / cape / scarf chains swing", t_phys)
def t_npc():
    from sforge import npcpack as NP
    names = NP.NPCS if hasattr(NP, "NPCS") else NP.CHARACTERS
    return len(names) >= 17 and "goblin" in names, "%d characters" % len(names)
check("npc pack: 17 fictional characters", t_npc)

# ---------------------------------------------------------------- 7. full builds (integration)
B = os.path.join(W, "b")
rc, log, dt = forge(["build", "--mannequin", "--name", "hero", "--moves", "idle:6:8:loop,walk:8:10:loop,punch:6:14:once,hit:4:12:once,taunt:6:8:once,victory:6:8:once"] + SMALL +
                    ["--no-fbx", "--recolor", "team_blue;hair=black", "--overlay", "top:stripes:#ffffff", "--talk", "Ready to fight",
                     "--expr-map", "victory=shout", "--blend", "idle>walk:3", "--footlock", "--framedata", "--maps", "normal,emissive",
                     "--fx", "outline=2,cel=3", "--lods", "2", "--variants", "4", "--out", B])
H = os.path.join(B, "hero")
rep = rd(H, "build_report.txt")
rec("build: mannequin with every v9 option", rc == 0, log.strip().splitlines()[-1] if log.strip() else "", dt)
check("build: faces.png + per-move expressions noted", lambda: (os.path.isfile(os.path.join(H, "faces.png")) and "per-move expressions" in rep, ""))
check("build: talk strip + 8 mouth shapes + timing", lambda: (os.path.isfile(os.path.join(H, "talk", "talk_strip.png")) and len([f for f in os.listdir(os.path.join(H, "talk")) if f.startswith("mouth_")]) == 8
                                                         and json.load(open(os.path.join(H, "talk", "talk.json"))) is not None, ""))
check("build: colours noted as exact for 3D", lambda: ("colours:" in rep and "exact" in rep, ""))
check("build: variants sheet + 4 variant specs", lambda: (os.path.isfile(os.path.join(H, "variants", "variants_sheet.png")) and
                                                        len([f for f in os.listdir(os.path.join(H, "variants")) if f.endswith(".txt")]) == 4, ""))
check("build: blend_idle_walk move made", lambda: (any(f.startswith("blend_idle_walk") for f in os.listdir(os.path.join(H, "moves"))), ""))
check("build: footlock slide numbers reported", lambda: ("footlock: planted-foot slide" in rep, [l for l in rep.splitlines() if "footlock" in l][:1]))
def t_fd():
    d = json.load(open(os.path.join(H, "framedata.json")))
    p = d["moves"]["punch"]; cfg = rd(H, "framedata.cfg")
    act = [i for i, f in enumerate(p["frames"]) if f["hit"]]
    return (p["startup"] and p["active"] and act and all(f["hurt"] for f in p["frames"]) and "punch" in cfg
            and not d["moves"]["blend_idle_walk"].get("active")), "punch startup %s active %s recovery %s" % (p["startup"], p["active"], p["recovery"])
check("frame data: punch has hit boxes in its active frames, blend is not an attack", t_fd)
check("maps: maps/atlas_normal.png + atlas_emissive.png", lambda: (all(os.path.isfile(os.path.join(H, "maps", f)) for f in ("atlas_normal.png", "atlas_emissive.png")), ""))
def t_lod():
    j = json.load(open(os.path.join(H, "lods.json")))
    t = [j["lod0"]["tris"], j["lod1"]["tris"], j["lod2"]["tris"]]
    return t[0] > t[1] > t[2] and j["baked"]["materials"] == 1 and all(os.path.isfile(os.path.join(H, j[k]["file"])) for k in ("baked", "lod1", "lod2")), str(t)
check("LODs: fewer triangles per level, baked model has 1 material", t_lod)
check("QA: report written for the build", lambda: (os.path.isfile(os.path.join(H, "qa_report.txt")) and "QA" in rep, ""))

def t_beard():
    b2 = os.path.join(W, "beard")
    spec = os.path.join(W, "beard.txt")
    open(spec, "w").write("name = beardy\nfacial_hair = beard\nhair_style = ponytail\n")
    rc, log, dt = forge(["build", "--spec", spec, "--moves", "idle:2:8:loop,punch:2:12:once,hit:2:12:once"] + SMALL + ["--no-glb", "--no-fbx", "--out", b2])
    spec2 = os.path.join(W, "moustache.txt"); open(spec2, "w").write("name = tash\nfacial_hair = moustache\n")
    rc2, log2, _ = forge(["build", "--spec", spec2, "--moves", "idle:2:8:loop,taunt:2:8:once", "--expressions", "shout"] + SMALL + ["--no-glb", "--no-fbx", "--out", b2])
    return rc == 0 and rc2 == 0 and os.path.isfile(os.path.join(b2, "beardy", "faces.png")) and os.path.isfile(os.path.join(b2, "tash", "faces.png")), (log + log2)[-150:]
check("expressions with a beard and a moustache (facial hair follows the face)", t_beard)

def t_cache_footlock():
    c = os.path.join(W, "fl")
    forge(["build", "--npc", "goblin", "--moves", "walk:6:10:loop"] + SMALL + ["--no-glb", "--no-fbx", "--out", c, "--name", "g"])
    a = np.asarray(Image.open(os.path.join(c, "g", "atlas.png")))
    forge(["build", "--npc", "goblin", "--moves", "walk:6:10:loop"] + SMALL + ["--no-glb", "--no-fbx", "--out", c, "--name", "g", "--footlock"])
    b = np.asarray(Image.open(os.path.join(c, "g", "atlas.png")))
    return a.shape != b.shape or np.abs(a.astype(int) - b.astype(int)).max() > 0, "footlock changes the cached render"
check("regression: --footlock is part of the render cache key", t_cache_footlock)

# ---------------------------------------------------------------- 8. forge.py v9 commands
N = os.path.join(W, "n")
rc, log, dt = forge(["build", "--npc", "wizard", "--moves", "idle:4:8:loop,cast:6:10:once,hit:3:12:once"] + SMALL + ["--no-glb", "--no-fbx", "--out", N])
rec("build --npc wizard", rc == 0 and os.path.isfile(os.path.join(N, "wizard", "atlas.png")), "", dt)
rc, log, dt = forge(["recolor", H, "--set", "team_red", "--out", os.path.join(W, "hero_red")])
rec("forge.py recolor <folder> --set team_red", rc == 0 and os.path.isfile(os.path.join(W, "hero_red", "atlas.png")), log.strip().splitlines()[-1] if log.strip() else "", dt)
rc, log, dt = forge(["variants", "--npc", "goblin", "-n", "6", "--seed", "3", "--out", os.path.join(W, "vars")])
rec("forge.py variants --npc goblin -n 6", rc == 0 and os.path.isfile(os.path.join(W, "vars", "variants_sheet.png")), "", dt)
PK = os.path.join(W, "pack")
rc, log, dt = forge(["atlas", H, os.path.join(N, "wizard"), "--out", PK, "--max", "1024"])
def t_pack():
    j = json.load(open(os.path.join(PK, "pack.json")))
    rects = {}
    for k, f in j["frames"].items():
        r = f["frame"]; rects[(f["page"], r["x"], r["y"], r["w"], r["h"])] = 1
        sz = j["meta"]["size"][f["page"]]
        if r["x"] + r["w"] > sz["w"] or r["y"] + r["h"] > sz["h"]:
            return False, "rect outside page"
    rs = list(rects)
    for i in range(len(rs)):
        for k in range(i + 1, len(rs)):
            a, b = rs[i], rs[k]
            if a[0] == b[0] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3] and a[2] < b[2] + b[4] and b[2] < a[2] + a[4]:
                return False, "overlap"
    anims = j["animations"]
    return "hero/punch" in anims and "wizard/cast" in anims and j["meta"]["fill"] > 0.6, "fill %.2f, %d pages" % (j["meta"]["fill"], len(j["meta"]["images"]))
rec("forge.py atlas: 2 characters, one pack", rc == 0, log.strip().splitlines()[-1] if log.strip() else "", dt)
check("atlas: rects inside pages, no overlaps, fill > 60%", t_pack)
rc, log, dt = forge(["qa", H]); rec("forge.py qa <build folder> runs", rc in (0, 1) and "QA" in log, log.strip().splitlines()[-1] if log.strip() else "", dt)
def t_qa_bad():
    bad = os.path.join(W, "bad"); shutil.copytree(os.path.join(N, "wizard"), bad)
    f = sorted(x for x in os.listdir(os.path.join(bad, "moves")) if x.startswith("cast_"))[2]
    Image.new("RGBA", Image.open(os.path.join(bad, "moves", f)).size).save(os.path.join(bad, "moves", f))
    rc, log, _ = forge(["qa", bad])
    return rc == 1 and "empty" in log.lower(), log.strip().splitlines()[-1] if log.strip() else ""
check("QA: an emptied frame is flagged FAIL (exit 1)", t_qa_bad)
rc, log, dt = forge(["framedata", os.path.join(N, "wizard")])
rec("forge.py framedata <folder> (cast counts as an attack)", rc == 0 and '"cast"' in rd(N, "wizard", "framedata.json") and
    (json.load(open(os.path.join(N, "wizard", "framedata.json")))["moves"]["cast"].get("active") or 0) > 0, "", dt)
for cmd in (["npc"], ["sets"], ["expressions"]):
    rc, log, dt = forge(cmd); rec("forge.py %s lists" % cmd[0], rc == 0 and len(log.splitlines()) > 5, "", dt)

def t_batch():
    q = os.path.join(W, "queue.txt")
    open(q, "w").write("# test\nbuild --npc kid --moves idle:2:8:loop %s --no-glb --no-fbx --out %s\n"
                       "build --npc robot --moves idle:2:8:loop %s --no-glb --no-fbx --out %s\nqa %s\n"
                       % (" ".join(SMALL), os.path.join(W, "q"), " ".join(SMALL), os.path.join(W, "q"), os.path.join(W, "q", "kid")))
    rc, log, dt = forge(["batch", q, "--workers", "2"])
    r = rd(W, "queue_report.txt")
    return rc == 0 and "3 ok" in r and os.path.isfile(os.path.join(W, "q", "robot", "atlas.png")), r.splitlines()[0] if r else log[-120:]
check("forge.py batch: 3-job queue, 2 workers, dependent qa job", t_batch)


# ---------------------------------------------------------------- 8b. photo-path regressions (Mike in-game test fixes)
# a DRAWN paper doll stands in for a photo cut-out (no real person)
def make_doll():
    """a DRAWN paper doll (not a person): shaded green top, fading jeans, skin hands, white shoes + 33 landmarks"""
    im = Image.new("RGBA", (300, 620), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    P = {0: (150, 70), 2: (141, 62), 5: (159, 62), 9: (143, 86), 10: (157, 86), 11: (190, 125), 12: (110, 125),
         13: (204, 195), 14: (96, 195), 15: (208, 262), 16: (92, 262), 17: (212, 280), 18: (88, 280), 19: (206, 284),
         20: (94, 284), 21: (202, 276), 22: (98, 276), 23: (172, 300), 24: (128, 300), 25: (170, 420), 26: (130, 420),
         27: (168, 540), 28: (132, 540), 29: (164, 556), 30: (136, 556), 31: (180, 566), 32: (120, 566)}
    for i in range(33):
        P.setdefault(i, P[0])
    skin, top, top_dk, jean, jean_lt = (226, 178, 150, 255), (30, 110, 80, 255), (18, 70, 52, 255), (50, 80, 150, 255), (110, 140, 195, 255)
    def cap(a, b, r, c):
        d.line([P[a], P[b]], fill=c, width=2 * r)
        for p in (P[a], P[b]):
            d.ellipse((p[0] - r, p[1] - r, p[0] + r, p[1] + r), fill=c)
    cap(25, 27, 17, jean_lt); cap(26, 28, 17, jean_lt); cap(23, 25, 20, jean); cap(24, 26, 20, jean)
    d.polygon([P[12], P[11], (P[23][0] + 6, 310), (P[24][0] - 6, 310)], fill=top)
    d.polygon([P[12], (150, 125), (150, 310), (P[24][0] - 6, 310)], fill=top_dk)      # shaded half of the SAME top
    cap(11, 13, 14, top); cap(13, 15, 12, top); cap(12, 14, 14, top_dk); cap(14, 16, 12, top_dk)
    for w in (17,):
        d.ellipse((P[w][0] - 12, P[w][1] - 16, P[w][0] + 12, P[w][1] + 12), fill=skin)
    d.rectangle((140, 92, 160, 128), fill=skin)
    d.ellipse((122, 36, 178, 104), fill=skin)
    d.ellipse((140, 58, 145, 64), fill=(40, 30, 30, 255)); d.ellipse((156, 58, 161, 64), fill=(40, 30, 30, 255))
    d.line((144, 86, 156, 86), fill=(150, 60, 60, 255), width=2)
    for a in (31, 32):
        d.ellipse((P[a][0] - 22, 548, P[a][0] + 22, 572), fill=(240, 240, 240, 255))
    return im, [[float(P[i][0]), float(P[i][1]), 1.0] for i in range(33)]

def t_seg_shading():
    from sforge import recolor as RC
    im, L = make_doll(); lab = RC.segment(im, L); R = RC.REGIONS.index; a = np.asarray(im)
    dk = (a[..., 1] == 70) & (a[..., 3] > 0); lt = (a[..., 2] == 195) & (a[..., 3] > 0)
    f_top, f_trim = (lab[dk] == R("top")).mean(), (lab[dk] == R("trim")).mean()
    f_bot, f_sock = (lab[lt] == R("bottom")).mean(), (lab[lt] == R("socks")).mean()
    return f_top > 0.9 and f_trim < 0.02 and f_bot > 0.75 and f_sock < 0.02, \
        "shaded top: top %.2f trim %.2f; faded jeans: bottom %.2f socks %.2f" % (f_top, f_trim, f_bot, f_sock)
check("photo regions: shading / faded denim keep their region (not trim / socks)", t_seg_shading)

def t_rig_colour_ref():
    from sforge import recolor as RC, puppet as PP
    im, L = make_doll()
    blue, _ = RC.recolor_cutout(im, L, "top=#6cace4", log=None)
    r0, r1, r2 = PP.Rig(im, L), PP.Rig(blue, L, colour_ref=im), PP.Rig(blue, L)
    k = r0.hand_hidden
    n0, n1, n2 = (int(r.pieces["f" + k].sum()) for r in (r0, r1, r2))
    return n0 > 500 and n1 == n0, "hidden forearm px: original %d, light-blue top with colour_ref %d (without: %d)" % (n0, n1, n2)
check("recoloured photo: rig pieces come from the pre-recolour colours (forearm kept)", t_rig_colour_ref)

def t_var_cli_cutout():
    from sforge import variants as VA
    im, L = make_doll(); d = os.path.join(W, "doll"); os.makedirs(d, exist_ok=True)
    im.save(os.path.join(d, "cutout.png"))
    json.dump({"photo": "drawn", "landmarks": L, "landmark_format": "mediapipe33"}, open(os.path.join(d, "landmarks.json"), "w"))
    rc, log, dt = forge(["variants", "--cutout", os.path.join(d, "cutout.png"), "-n", "4", "--out", os.path.join(d, "var")])
    nohair = all("hair=" not in VA.photo_variant(s)[0] for s in range(1, 40))
    return rc == 0 and os.path.isfile(os.path.join(d, "var", "variants_sheet.png")) and nohair, \
        "rc %d, photo variants never recolour hair: %s" % (rc, nohair)
check("forge.py variants --cutout (landmarks.json dict) + photo variants keep the hair", t_var_cli_cutout)

# ---------------------------------------------------------------- 9. Studio argv mapping (no window)
try:
    import tkinter  # noqa
    HAVE_TK = True
except ImportError:
    HAVE_TK = False
if HAVE_TK:
    from sforge import gui_style as GS
    class _V:
        def __init__(self, x): self.x = x
        def get(self): return self.x
    class _App:
        def __init__(self, vv, bb):
            self.v = {k: _V(x) for k, x in {**GS.V9_VARS, **vv}.items()}
            self.b = {k: _V(x) for k, x in {**GS.V9_BOOLS, **bb}.items()}
    def t_argv():
        a = GS.style_argv(_App(dict(expressions="map", expr_map="punch=shout", recolor_set="kerry", rc_hair="#111111", overlay_kind="hoops",
                                    variants="6", variant_seed="3", fx="outline=2", maps="normal", lods="2", talk="Hi"), dict(framedata=True, blink=False)))
        s = " ".join(a)
        need = ["--expr-map punch=shout", "--no-blink", "--talk Hi", "--recolor kerry;hair=#111111", "--overlay top:hoops:#ffffff",
                "--variants 6", "--variant-seed 3", "--fx outline=2", "--maps normal", "--lods 2", "--framedata"]
        miss = [n for n in need if n not in s]
        return not miss, "missing %s" % miss if miss else s[:120]
    check("Studio: Style + Extras settings -> forge.py flags", t_argv)
    def t_defaults():
        return GS.style_argv(_App({}, {})) == [], "defaults add no flags"
    check("Studio: defaults add no v9 flags (v8 commands unchanged)", t_defaults)
    def t_cfg():
        from sforge.build import BuildConfig
        c = BuildConfig(name="x")
        GS.apply_to_config(_App(dict(recolor_set="team_red", variant="7", npc="goblin"), dict(footlock=True)), c)
        return c.recolor == "team_red" and c.variant == 7 and c.footlock and c.mode == "mannequin", "recolor/variant/footlock/npc"
    check("Studio: settings -> BuildConfig (in-process build)", t_cfg)
else:
    rec("Studio argv mapping (skipped: no tkinter)", True, "skipped")

# ---------------------------------------------------------------- 10. engine plugins
GODOT = os.environ.get("SFS_GODOT") or shutil.which("godot") or ("/tmp/godot/godot" if os.path.isfile("/tmp/godot/godot") else "")
if GODOT:
    def t_godot():
        proj = os.path.join(W, "gproj"); os.makedirs(proj)
        shutil.copytree(os.path.join(HERE, "plugins", "godot", "addons"), os.path.join(proj, "addons"))
        shutil.copytree(H, os.path.join(proj, "hero"))
        open(os.path.join(proj, "project.godot"), "w").write('config_version=5\n[application]\nconfig/name="t"\n')
        open(os.path.join(proj, "t.gd"), "w").write('extends SceneTree\nfunc _init():\n\tvar r = SpriteForgeImport.import_folder("res://hero")\n'
                                                     '\tprint("SFRESULT ", r)\n\tvar f = load("res://hero/hero_frames.tres")\n'
                                                     '\tprint("SFANIMS ", f.get_animation_names().size())\n\tquit()\n')
        subprocess.run([GODOT, "--headless", "--path", proj, "--import"], capture_output=True, timeout=180)
        p = subprocess.run([GODOT, "--headless", "--path", proj, "-s", "t.gd"], capture_output=True, text=True, timeout=180)
        n = [l for l in p.stdout.splitlines() if l.startswith("SFANIMS")]
        return bool(n) and int(n[0].split()[1]) >= 7 and os.path.isfile(os.path.join(proj, "hero", "hero.tscn")), (n[0] if n else p.stdout[-150:] + p.stderr[-150:])
    check("Godot plugin: import build -> SpriteFrames (all moves) + scene", t_godot)
else:
    rec("Godot plugin (skipped: set SFS_GODOT to a Godot 4 binary)", True, "skipped")
DOTNET = os.environ.get("SFS_DOTNET") or shutil.which("dotnet") or ("/tmp/dotnet/dotnet" if os.path.isfile("/tmp/dotnet/dotnet") else "")
if DOTNET:
    def t_unity():
        d = os.path.join(W, "ustub"); shutil.copytree(os.path.join(HERE, "tools", "unity_stub_check"), d)
        proj = open(os.path.join(d, "stub.csproj")).read().replace("../../plugins", os.path.join(HERE, "plugins").replace("\\", "/"))
        open(os.path.join(d, "stub.csproj"), "w").write(proj)
        p = subprocess.run([DOTNET, "build", d, "-nologo", "-v", "q"], capture_output=True, text=True, timeout=600)
        return p.returncode == 0 and " 0 Error" in p.stdout, [l for l in p.stdout.splitlines() if "Error" in l or "Warn" in l][:2]
    check("Unity package: compiles against stub UnityEngine/UnityEditor APIs", t_unity)
else:
    rec("Unity stub compile (skipped: no dotnet)", True, "skipped")

json.dump(R, open(os.path.join(OUT, "results_v9.json"), "w"), indent=1)
with open(os.path.join(OUT, "RESULTS_v9_tests.md"), "w") as f:
    f.write("# Sprite Forge Studio v9 tests\n\n| result | test | detail | s |\n|---|---|---|---|\n")
    for r in R:
        f.write("| %s | %s | %s | %s |\n" % ("PASS" if r["ok"] else "**FAIL**", r["test"], r["detail"].replace("|", "/"), "" if r["secs"] is None else r["secs"]))
for f in ("faces.png", "variants/variants_sheet.png", "framedata_preview.png"):
    if os.path.isfile(os.path.join(H, f)):
        shutil.copy(os.path.join(H, f), os.path.join(OUT, "test_" + os.path.basename(f)))
n_fail = sum(not r["ok"] for r in R)
print("\n%d tests, %d failed -> %s" % (len(R), n_fail, os.path.join(OUT, "RESULTS_v9_tests.md")))
shutil.rmtree(W, ignore_errors=True)
sys.exit(1 if n_fail else 0)

#!/usr/bin/env python3
"""v11.26: hurling, Aussie rules and rugby game packs; the hurley and helmet; sport kit cuts on the look builder.

    python tools/test_new_sports.py [--quick]

Without builds:
  1 every game pack loads and validates, and every move with an "own" motion finds it (all packs, not just the new)
  2 the new sports' motions exist, sample to finite poses at every frame and actually move (no frozen clip)
  3 each new pack plays its own motion for its signature moves (strike, speccy, scrum, ...) and no two of its
    moves share one clip by accident; events are inside the move's frames
  4 pack "equip": the hurling pack fills cfg.props with the hurley and helmet; --attach replaces it; a pack
    without equip leaves cfg.props alone
  5 the sport props are in the library: CC0, redistributable, on their sockets, the helmet fitted to the head
  6 kit cuts: sf_<kit>#<n>@<style> parses (rugby / guernsey / football), a bad style is refused, and roster look
    commands carry the game's cut (rugby collar, Aussie rules guernsey)
  7 rosters: hurling / Aussie rules / rugby are team games with real positions (keeper in gk, a ruckman, props
    and locks), and the Games tab offers the contact-sport player types
  8 (MakeHuman assets only) the guernsey is sleeveless: no arm faces in the jersey
  8b every clip the new packs play passes check_motion (floor, size, glitches, loops, does what its name says) -
    the scrum and ruck stay on the floor in 3D, the sidestep really cuts sideways
With builds:
  9 each new pack builds on the mannequin: no QA FAIL, no clipped move, every move drawn, the events in
    game_character.json inside each move's frames
 10 hurling: the hurley and helmet are attached in the build (report + model.glb), the helmet on the head (its
    pixels at the top of the figure, not floating above it); --no-equip builds without them
"""
from __future__ import annotations
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
R = []
NEW = ("hurling", "aussie_rules", "rugby")
SIGNATURE = {
    "hurling": {"solo": "hurl_solo", "strike": "hurl_strike", "ground_strike": "hurl_ground", "puckout": "hurl_puckout",
                "free": "hurl_free", "lift": "hurl_lift", "catch": "hurl_catch", "hook": "hurl_hook", "block": "hurl_block"},
    "aussie_rules": {"mark": "aussie_mark", "speccy": "aussie_speccy", "ruck_tap": "aussie_ruck_tap",
                     "shepherd": "aussie_shepherd", "handball": "fist_pass", "bounce": "bounce_solo"},
    "rugby": {"pass": "rugby_pass", "scrum": "rugby_scrum", "ruck": "rugby_ruck", "try": "rugby_try",
              "hand_off": "rugby_hand_off", "lineout": "lineout_lift"},
}


def rec(name, ok, detail=""):
    R.append((name, bool(ok), detail))
    print("%-4s %s%s" % ("ok" if ok else "FAIL", name, ("  - " + str(detail)[:400]) if detail and not ok else ""))


def forge(*a):
    return subprocess.run([sys.executable, os.path.join(HERE, "forge.py")] + list(a), cwd=HERE, capture_output=True,
                          text=True, timeout=1800)


def packs_check():
    from sforge import gamepack as GP
    from sforge.motions import find_motion
    bad = []
    names = GP.list_packs()
    for g in names:
        errs, _ = GP.validate(g)
        if errs:
            bad.append("%s: %s" % (g, errs))
            continue
        for m in GP.load(g)["moves"]:
            for o in m["own"]:
                if find_motion(o) is None:
                    bad.append("%s/%s: own motion %s missing" % (g, m["name"], o))
    missing = [g for g in NEW if g not in names]
    rec("1 every pack (%d) validates; every 'own' motion exists" % len(names), not bad and not missing, bad or missing)


def _numeric(v):
    try:
        np.asarray(v, float); return True
    except (TypeError, ValueError):
        return False


def motions_check():
    from sforge.motions import find_motion
    bad = []
    names = sorted({v for d in SIGNATURE.values() for v in d.values()})
    for n in names:
        m = find_motion(n)
        if m is None:
            bad.append(n + " missing"); continue
        poses = []
        for i in range(9):
            pose, _ = m.sample(i / 8.0)
            pose = {k: v for k, v in pose.items() if k != "ball" and _numeric(v)}   # 'ball' is the prop, None off-hand
            vals = []
            for v in pose.values():
                vals.extend(np.ravel(np.asarray(v, float)).tolist())
            if not np.all(np.isfinite(vals)):
                bad.append(n + " not finite"); break
            poses.append(pose)
        else:
            keys = set().union(*[set(p) for p in poses])
            span = 0.0
            for k in keys:
                arr = [np.ravel(np.asarray(p.get(k, 0.0), float)) for p in poses]
                if len({a.size for a in arr}) == 1:
                    span = max(span, float(np.ptp(np.array(arr), axis=0).max()))
            if span < 5.0:                   # degrees: a clip that barely moves is a frozen pose
                bad.append("%s moves only %.1f deg" % (n, span))
    rec("2 the %d new sport motions sample finite and move" % len(names), not bad, bad)


def resolve_check():
    from sforge import gamepack as GP, motionset as MS
    from sforge.build import BuildConfig
    bad = []
    for g in NEW:
        cfg = BuildConfig()
        GP.apply(cfg, g)
        MS.apply_cfg(cfg)
        by = {m.name: MS.clip_id(m) for m in cfg.moves}
        for mv, mo in SIGNATURE[g].items():
            # v11.41: a Meshy clip the pack prefers (motion_library_owned/mz_*) is the move's own clip too
            got = by.get(mv) or ""
            if got != "motion:" + mo and not got.startswith("lib:mz_"):
                bad.append("%s/%s plays %s, want motion:%s or its Meshy clip" % (g, mv, got, mo))
        seen = {}
        for mv, cid in by.items():
            seen.setdefault(cid, []).append(mv)
        shared = [v for v in seen.values() if len(v) > 1]
        if shared:
            bad.append("%s shares clips: %s" % (g, shared))
        for m in GP.load(g)["moves"]:
            for k, v in m["events"].items():
                for x in (v if isinstance(v, list) else [v]):
                    if isinstance(x, int) and x >= m["frames"]:
                        bad.append("%s/%s %s=%d past %d frames" % (g, m["name"], k, x, m["frames"]))
    rec("3 signature moves play their own motion, no accidental shared clips, events in range", not bad, bad)


def equip_check():
    from sforge import gamepack as GP
    from sforge.build import BuildConfig
    cfg = BuildConfig(); GP.apply(cfg, "hurling")
    ok1 = cfg.props == ["sport_hurley@hand_r", "sport_hurl_helmet@head"]
    cfg2 = BuildConfig(); cfg2.props = ["sample_sword@hand_r"]; GP.apply(cfg2, "hurling")
    ok2 = cfg2.props == ["sample_sword@hand_r"]
    cfg3 = BuildConfig(); GP.apply(cfg3, "rugby")
    ok3 = not cfg3.props
    rec("4 pack equip fills props (hurling), keeps explicit props, other packs untouched", ok1 and ok2 and ok3,
        (cfg.props, cfg2.props, cfg3.props))


def props_check():
    from sforge import rigrec as RR
    bad = []
    for name, sock, fit in (("sport_hurley", "hand_r", "none"), ("sport_hurl_helmet", "head", "head")):
        d = os.path.join(HERE, "library", "props", name)
        if not os.path.isdir(d):
            bad.append(name + " missing"); continue
        r = RR.Rig.load(d)
        pm = r.meta.get("prop", {})
        if pm.get("socket") != sock or pm.get("fit", "none") != fit:
            bad.append("%s meta %s" % (name, pm))
        lic = json.load(open(os.path.join(d, "licence.json")))
        if lic.get("spdx") != "CC0-1.0" or lic.get("redistribution") != "yes":
            bad.append("%s licence %s" % (name, lic.get("spdx")))
        if not len(r.V) or not len(r.F):
            bad.append(name + " empty")
    h = RR.Rig.load(os.path.join(HERE, "library", "props", "sport_hurley"))
    L = float(np.ptp(h.V, axis=0).max())
    if not 0.75 <= L <= 0.95:
        bad.append("hurley length %.2f m" % L)
    rec("5 hurley (%.2f m) and helmet in the library: CC0, sockets, head fit" % L, not bad, bad)


def kit_check():
    from sforge import footballer as FB, roster as RO
    bad = []
    if FB.kit_style("sf_red#4@rugby") != "rugby" or FB.kit_style("sf_blue#12@guernsey") != "guernsey":
        bad.append("styles not parsed")
    if FB.kit_style("sf_home#7") != "football" or FB.kit_style("home") != "football":
        bad.append("default style")
    cols, num = FB.sf_kit("sf_red#4@rugby")
    if num != 4:
        bad.append("number with a style: %r" % num)
    try:
        FB.kit_style("sf_red@tutu"); bad.append("bad style accepted")
    except KeyError:
        pass
    for g, want in (("rugby", "@rugby"), ("aussie_rules", "@guernsey"), ("hurling", None), ("soccer", None)):
        p = RO.default_roster(g, 2)["players"][1]
        kit = RO.look_argv(p, "/o/x.glb", g)[RO.look_argv(p, "/o/x.glb", g).index("--kit") + 1]
        if (want and not kit.endswith(want)) or (not want and "@" in kit):
            bad.append("%s look kit %s" % (g, kit))
    p = dict(RO.default_roster("soccer", 2)["players"][1]); p["kit_style"] = "rugby"
    if not RO.look_argv(p, "/o/x.glb", "soccer")[RO.look_argv(p, "/o/x.glb", "soccer").index("--kit") + 1].endswith("@rugby"):
        bad.append("a player's own kit_style ignored")
    # paint: rugby socks hooped (two colours down the sock), plain football socks one colour
    P = np.c_[np.zeros(40), np.linspace(0.17, 0.44, 40), np.full(40, 0.05)]
    base = np.zeros((40, 3))

    def sock_colours(kit):
        c, _ = FB.paints(kit)["socks"].fn(P, base)
        return len({tuple(np.round(x, 3)) for x in c})
    if sock_colours("sf_red#4@rugby") < 2 or sock_colours("sf_red#4") != 1:
        bad.append("sock hoops: rugby %d colours, football %d" % (sock_colours("sf_red#4@rugby"), sock_colours("sf_red#4")))
    rec("6 kit cuts parse, refuse bad styles, rugby socks hooped, roster looks carry the game's cut", not bad, bad)


def roster_check():
    from sforge import roster as RO, gui_games as GG
    bad = []
    for g in NEW:
        if g not in RO.TEAM_GAMES:
            bad.append(g + " not a team game"); continue
        r = RO.default_roster(g)
        if RO.validate(r):
            bad.append("%s: %s" % (g, RO.validate(r)))
        roles = [p["role"] for p in r["players"]]
        sides = {p["side"] for p in r["players"]}
        if sides != {"Home", "Away"} or len(r["players"]) != 2 * RO.TEAM_GAMES[g]:
            bad.append("%s sides %s" % (g, sides))
        for p in r["players"]:
            if (p["type"] == "keeper") != (p["kit"] == "gk"):
                bad.append("%s %s kit %s" % (g, p["name"], p["kit"]))
        want = {"hurling": "Goalkeeper", "aussie_rules": "Ruckman", "rugby": "Prop"}[g]
        if want not in roles:
            bad.append("%s roles %s" % (g, roles))
        if not GG.has_kits(g) or "heavy_brawler" not in GG.types_for(g) or "keeper" not in GG.types_for(g):
            bad.append("%s Games tab types %s" % (g, GG.types_for(g)))
    if "heavy_brawler" in GG.types_for("soccer"):
        bad.append("soccer offered contact types")
    rec("7 the new games are team games with positions; Games tab player types", not bad, bad)


def garment_check():
    from sforge import human as HU
    if not HU.have_assets():
        rec("8 guernsey sleeveless (MakeHuman assets missing - skipped)", True); return
    from sforge import mhchar, mhlib, look as LK
    lib = mhlib.Library()
    tm = mhchar.Template.load(LK.default_template(None), lib)
    J = {n: i for i, n in enumerate(tm.joints)}
    W = np.zeros((len(tm.P), len(tm.joints)))
    np.add.at(W, (np.arange(len(tm.P))[:, None].repeat(4, 1), tm.J.astype(np.int64)), tm.W)
    dom = np.array(tm.joints)[np.argmax(W[tm.F].mean(1), 1)]
    arm = np.isin(dom, ["upperarm_l", "upperarm_r"])
    g0 = dict((g, f) for g, f, _ in mhchar.garment_faces(tm, tm.P))
    g1 = dict((g, f) for g, f, _ in mhchar.garment_faces(tm, tm.P, None, "guernsey"))
    a0, a1 = arm[g0["jersey"]].sum(), arm[g1["jersey"]].sum()
    torso_kept = len(g1["jersey"]) > 0.6 * (len(g0["jersey"]) - a0)
    rec("8 guernsey: sleeves gone (%d -> %d arm faces), torso kept" % (a0, a1), a0 > 0 and a1 == 0 and torso_kept,
        (a0, a1, len(g0["jersey"]), len(g1["jersey"])))


def clip_check():
    sys.path.insert(0, os.path.join(HERE, "tools"))
    import check_motion as CM
    bad = []
    for g in NEW:
        for mv, path, r in CM.pack_clips(g, None):
            fails = [(k, d) for k, ok, d in CM.check_clip(r, mv) if ok is False]
            if fails:
                bad.append("%s/%s: %s" % (g, mv, fails))
    rec("8b every clip the new packs play passes check_motion", not bad, bad)


def build_checks(tmp, quick):
    from sforge import gamepack as GP
    bad = []
    games = NEW if not quick else ("hurling",)
    procs = {}
    for g in games:
        out = os.path.join(tmp, g)
        procs[g] = (subprocess.Popen([sys.executable, os.path.join(HERE, "forge.py"), "build", "--game", g, "--out", out],
                                     cwd=HERE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True), out)
    logs = {}
    for g, (p, out) in procs.items():
        logs[g] = p.communicate(timeout=1800)[0]
        ch = os.path.join(out, "character")
        if p.returncode != 0 or not os.path.isfile(os.path.join(ch, "qa.json")):
            bad.append("%s build failed: %s" % (g, logs[g][-300:])); continue
        rep = open(os.path.join(ch, "qa_report.txt")).read()
        head = rep.splitlines()[0]
        if " 0 FAIL" not in head or "clipped at cell edge" in rep:
            bad.append("%s QA: %s" % (g, head))
        gc = json.load(open(os.path.join(ch, "game_character.json")))
        pack = GP.load(g)
        files = os.listdir(os.path.join(ch, "moves"))
        for m in pack["moves"]:
            n = len([f for f in files if f.startswith(m["name"] + "_") and f[len(m["name"]) + 1:-4].isdigit()])
            if n == 0:
                bad.append("%s/%s not drawn" % (g, m["name"]))
        anims = gc.get("animations") or gc.get("moves") or {}
        items = anims.items() if isinstance(anims, dict) else [(a.get("name"), a) for a in anims]
        for name, a in items:
            nfr = a.get("frames") if isinstance(a.get("frames"), int) else len(a.get("frames") or [])
            for k, v in (a.get("events") or {}).items():
                for x in (v if isinstance(v, list) else [v]):
                    if isinstance(x, int) and nfr and x >= nfr:
                        bad.append("%s/%s event %s=%d past %d" % (g, name, k, x, nfr))
    rec("9 %s build on the mannequin: no QA FAIL, nothing clipped, every move drawn, events in range" % "/".join(games),
        not bad, bad)
    # 10 hurling equipment
    bad = []
    ch = os.path.join(tmp, "hurling", "character")
    rep = open(os.path.join(ch, "build_report.txt")).read() if os.path.isfile(os.path.join(ch, "build_report.txt")) else ""
    for n in ("sport_hurley", "sport_hurl_helmet"):
        if "equip prop: %s" % n not in rep:
            bad.append(n + " not in the build report")
    glb = os.path.join(ch, "model.glb")
    if os.path.isfile(glb):
        from sforge import glbpack
        j, _ = glbpack.read_glb(glb)
        names = " ".join(str(m.get("name", "")) for m in j.get("meshes", []) + j.get("materials", []))
        if "hurl" not in names.lower() and "sport" not in names.lower():
            bad.append("props not in model.glb (%s)" % names[:200])
    else:
        bad.append("no model.glb")
    # the helmet sits on the head: the top of the figure in idle is helmet black, and not far above the face
    from PIL import Image
    im = np.asarray(Image.open(os.path.join(ch, "moves", "idle_00.png")).convert("RGBA")).astype(int)
    a = im[..., 3] > 128
    rows = np.nonzero(a.any(1))[0]
    top, bottom = rows.min(), rows.max()
    band = im[top:top + 4][a[top:top + 4]]
    dark = (band[:, :3].mean(1) < 70).mean() if len(band) else 0
    skin = (im[..., 0] > 150) & (im[..., 0] > im[..., 2] + 30) & a
    sk_rows = np.nonzero(skin[: top + (bottom - top) // 4].any(1))[0]
    gap = (sk_rows.min() - top) if len(sk_rows) else 999
    hfig = bottom - top
    if dark < 0.5 or gap > 0.10 * hfig:
        bad.append("helmet: top band %.0f%% dark, face starts %d px under the top (figure %d px)" % (100 * dark, gap, hfig))
    out2 = os.path.join(tmp, "hurling_bare")
    r = forge("build", "--game", "hurling", "--no-equip", "--no-glb", "--out", out2)
    rep2 = open(os.path.join(out2, "character", "build_report.txt")).read() if r.returncode == 0 else r.stdout[-300:]
    if "equip prop" in rep2:
        bad.append("--no-equip still attached the props")
    rec("10 hurling: hurley + helmet attached (report, model.glb), helmet on the head; --no-equip leaves them off",
        not bad, bad)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="build only the hurling pack")
    ap.add_argument("--keep", help="keep the builds in this folder")
    a = ap.parse_args()
    packs_check()
    motions_check()
    resolve_check()
    equip_check()
    props_check()
    kit_check()
    roster_check()
    garment_check()
    clip_check()
    tmp = a.keep or tempfile.mkdtemp(prefix="sfs_newsports_")
    try:
        build_checks(tmp, a.quick)
    finally:
        if not a.keep:
            shutil.rmtree(tmp, ignore_errors=True)
    bad = [n for n, ok, _ in R if not ok]
    print("\n%d / %d passed" % (len(R) - len(bad), len(R)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

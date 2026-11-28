"""forge.py meshy - Meshy AI from Sprite Forge (v11.41).

    forge.py meshy balance                              free: credits left
    forge.py meshy library [--search kick]              free: Meshy's preset animation library
    forge.py meshy motion --pack gaelic --dry-run       what it would generate, and the credits
    forge.py meshy motion --pack gaelic [--moves hand_pass,tackle] [--mode swift|prime] [--max-credits 100]
    forge.py meshy import --pack gaelic                 free: re-import the saved BVH / FBX (after an importer change)
    forge.py meshy pack --pack soccer_full              write the full pack from its catalogue (base pack + catalogue)
    forge.py meshy catalogue --pack soccer_full         what the catalogue covers, by category

A catalogue (game_packs/meshy/<sport>_full.json) is a prompt file with "base" (the core pack it extends),
"also_packs" (core packs that should prefer the same clips) and per-move "category", "library" (fallback) and timing.

A move in the prompt file may say {"reuse": "mz_gaelic_get_up"} instead of a prompt: another pack's clip that already
passes, wired into this pack the same way (nothing is generated).

`motion` reads game_packs/meshy/<pack>.json (one Text to Motion prompt per move), generates each clip, keeps the
source file in motion_library_owned/src/meshy/<pack>/, imports it onto the shared skeleton as <clip_prefix><move> in
motion_library_owned/, runs check_motion on it and adds it to that move's "prefer" list in the pack, after any clips
already named there (your own human-derived clips still win where you have them). A clip that fails the check is kept out of the pack (the report says why).

Licence: the account holder owns paid-plan Meshy output, so these clips are stored as LicenseRef-Owned-Meshy, may be
redistributed with this project and are shipped in git. They are not CC0: motion_library/ (the starter) stays CC0.
Key: MESHY_API_KEY or ~/.config/meshy/key (sforge/meshy.py).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

from . import meshy as MZ

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OWNED = os.path.join(HERE, "motion_library_owned")
PROMPTS = os.path.join(HERE, "game_packs", "meshy")
LICENCE = dict(spdx="LicenseRef-Owned-Meshy", author="Sprite Forge project owner (generated with Meshy AI, paid plan)",
               source_url="https://www.meshy.ai (Text to Motion)", redistribution="yes", ml_training="unknown",
               notes="Generated with Meshy Text to Motion on the owner's paid plan; the owner holds the rights and "
                     "allows it in this project's repo and builds.")


def load_prompts(pack, folder=PROMPTS):
    p = os.path.join(folder, pack + ".json")
    if not os.path.isfile(p):
        raise SystemExit("no prompt file %s (have: %s)" % (p, ", ".join(sorted(f[:-5] for f in os.listdir(folder) if f.endswith(".json")))))
    d = json.load(open(p, encoding="utf-8"))
    for nm, m in d["moves"].items():
        if m.get("reuse"):                    # {"reuse": "mz_gaelic_get_up"}: another pack's clip, nothing generated
            continue
        if len(m["prompt"]) > 400:
            raise SystemExit("%s: prompt is %d characters (Meshy allows 400)" % (nm, len(m["prompt"])))
    return d


MAX_TRAVEL_MS = 8.0       # a footballer's sprint is ~9-10 m/s; Meshy prime takes run off at up to 30 m/s


def cap_travel(rec, peak=MAX_TRAVEL_MS):
    """Meshy's prime model sometimes sends the body across the ground far too fast (a slide tackle 30 m in 2.5 s)
    while the pose itself is right. Scale the root's ground travel so its peak speed is `peak` m/s; the original
    peak is kept in rec["meshy"]["travel"]. Games play these moves in place, so only the pose is visible there."""
    import numpy as np
    keys = rec.get("keys") or []
    if len(keys) < 2:
        return 1.0
    dur = float(rec.get("duration") or keys[-1][0] or 1.0)
    t = np.array([float(k[0]) for k in keys]) * dur / max(1e-6, float(keys[-1][0]) or 1.0)
    P = np.array([(list(k[1].get("pos", (0, 0))) + [0, 0])[:2] for k in keys], float)
    v = np.linalg.norm(np.diff(P, axis=0), axis=1) / np.maximum(1e-6, np.diff(t))
    top = float(v.max()) if len(v) else 0.0
    if top <= peak:
        return 1.0
    f = peak / top
    for k, p in zip(keys, P):
        if "pos" in k[1]:
            k[1]["pos"] = [float((p[0] - P[0, 0]) * f + P[0, 0]), float((p[1] - P[0, 1]) * f + P[0, 1])]
    rec.setdefault("meshy", {})["travel"] = {"peak_ms": round(top, 2), "scaled_to_ms": peak, "factor": round(f, 3)}
    return f


def plan(spec, moves=None, mode=None):
    mode = mode or spec.get("mode", "swift")
    names = [m for m in (moves or list(spec["moves"]))]
    bad = [m for m in names if m not in spec["moves"]]
    if bad:
        raise SystemExit("not in the prompt file: %s" % ", ".join(bad))
    names = [m for m in names if not spec["moves"][m].get("reuse")]
    return names, mode, len(names) * MZ.COST["motion_" + mode]


def import_clip(src, clip, loop, out_dir=OWNED, pack=None, move=None, prompt=""):
    """Import one Meshy file onto the shared skeleton; returns (record path, problems)."""
    cmd = [sys.executable, os.path.join(HERE, "forge.py"), "motion", "import", "--library", out_dir, src, "--name", clip,
           "--loop" if loop else "--once", "--spdx", LICENCE["spdx"], "--author", LICENCE["author"],
           "--source-url", LICENCE["source_url"], "--redistribution", LICENCE["redistribution"],
           "--ml-training", LICENCE["ml_training"], "--notes", LICENCE["notes"]]
    r = subprocess.run(cmd, capture_output=True, text=True)
    rec_p = os.path.join(out_dir, clip + ".json")
    if r.returncode or not os.path.isfile(rec_p):
        return None, ["import failed: %s" % ((r.stderr or r.stdout).strip().splitlines() or ["?"])[-1]]
    rec = json.load(open(rec_p, encoding="utf-8"))
    cap_travel(rec)
    rec["desc"] = "Meshy Text to Motion%s: %s" % (" (%s %s)" % (pack, move) if pack else "", prompt[:160])
    rec.setdefault("meshy", {}).update(pack=pack, move=move, prompt=prompt, source=os.path.relpath(src, out_dir))
    with open(rec_p, "w", encoding="utf-8") as f:
        json.dump(rec, f)
    sys.path.insert(0, os.path.join(HERE, "tools"))
    import check_motion as CM
    bad = [x for x in CM.check_clip(rec, move or clip) if x[1] is False]
    if bad:                                   # never ship a clip that fails its check; the source file stays for a re-import
        os.remove(rec_p)
    return rec_p, ["%s: %s" % (x[0], x[2]) for x in bad]


def import_prime_safely(src, clip, m, out, pack, move):
    """Import a prime take under a temporary name; it replaces the move's clip only when it passes its checks,
    so a weaker prime take never removes a swift clip that works."""
    tmp = clip + "_primetake"
    rec_p, bad = import_clip(src, tmp, m.get("loop", False), out, pack, move, m.get("prompt", ""))
    if not rec_p or bad:
        return None, bad or ["import failed"]
    rec = json.load(open(rec_p, encoding="utf-8"))
    rec["name"] = clip
    rec.setdefault("meshy", {})["mode"] = "prime"
    final = os.path.join(out, clip + ".json")
    with open(final, "w", encoding="utf-8") as f:
        json.dump(rec, f)
    os.remove(rec_p)
    return final, []


def set_mode(pack, move, mode, folder=PROMPTS):
    p = os.path.join(folder, pack + ".json")
    d = json.load(open(p, encoding="utf-8"))
    d["moves"][move]["mode"] = mode
    d["moves"][move].pop("no_clip", None)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=1)


def wire_targets(spec, pack, packs_dir=None):
    """The pack itself, plus "also_packs" (a full catalogue also feeds its core pack), that exist."""
    d = packs_dir or os.path.join(HERE, "game_packs")
    return [pk for pk in [pack] + list(spec.get("also_packs") or []) if os.path.isfile(os.path.join(d, pk + ".json"))]


CONTACT = {"Control", "Passing", "Shooting", "Skill", "Ball", "Set piece", "Goalkeeper", "Aerial"}
CAT_ORDER = ["Locomotion", "Control", "Ball", "Passing", "Shooting", "Skill", "Defending", "Defence", "Aerial", "Contact",
             "Goalkeeper", "Set piece", "Reaction", "Celebration", "Extra", "Game"]


def build_full_pack(spec, packs_dir=None, log=print):
    """game_packs/<pack>.json from a catalogue: the base pack's moves as they are, then every catalogue move it lacks,
    grouped by category. Clips are wired afterwards (prefer), so a move with no clip yet plays its library fallback."""
    d = packs_dir or os.path.join(HERE, "game_packs")
    base = json.load(open(os.path.join(d, spec["base"] + ".json"), encoding="utf-8"))
    pack = {k: v for k, v in base.items() if k not in ("moves", "v2_moves")}
    pack.update(name=spec["pack"], label=spec.get("label") or spec["pack"].replace("_", " ").title(),
                description=spec.get("description") or base.get("description", ""),
                notes="Built by forge.py meshy pack from game_packs/meshy/%s.json (the move catalogue). Every "
                      "move of the %s pack, then the catalogue's." % (spec["pack"], spec["base"]))
    moves = [dict(m) for m in base["moves"]]
    have = {m["name"] for m in moves}
    pre = spec.get("clip_prefix", "")
    old = {}
    p_out = os.path.join(d, spec["pack"] + ".json")
    if os.path.isfile(p_out):                       # keep the prefer lists already wired
        old = {m["name"]: m.get("prefer") for m in json.load(open(p_out, encoding="utf-8"))["moves"]}
    extra = []
    for n, m in spec["moves"].items():
        if n in have:
            continue
        cat = m.get("category", "Game")
        fr = 8 if m.get("loop") else max(8, min(14, int(round(m.get("duration", 2.0) * 4))))
        ev = {"hit_start": -1, "hit_end": -1, "ball_contact": fr // 2 if cat in CONTACT else -1, "throw_release": -1,
              "shoot": -1, "reload": -1, "footsteps": []}
        mv = {"name": n, "library": m.get("library") or "idle", "frames": m.get("frames", fr), "fps": m.get("fps", 12),
              "loop": bool(m.get("loop")), "category": cat, "events": ev,
              "desc": (m.get("desc") or m.get("prompt", "")).split(":")[-1].strip()[:120]}
        if old.get(n):
            mv["prefer"] = old[n]
        elif m.get("reuse"):
            mv["prefer"] = [m["reuse"]]
        elif os.path.isfile(os.path.join(OWNED, pre + n + ".json")):
            mv["prefer"] = [pre + n]
        extra.append(mv)
    extra.sort(key=lambda mv: CAT_ORDER.index(mv["category"]) if mv["category"] in CAT_ORDER else 99)
    pack["moves"] = moves + extra
    with open(p_out, "w", encoding="utf-8") as f:
        json.dump(pack, f, indent=1)
        f.write("\n")
    log("game_packs/%s.json: %d moves (%d from %s, %d from the catalogue)" % (spec["pack"], len(pack["moves"]),
                                                                          len(moves), spec["base"], len(extra)))
    return p_out


def coverage(spec, packs_dir=None, out=OWNED):
    """Per category: catalogue moves, how many have a shipped Meshy clip (or a reuse), and which do not."""
    d = packs_dir or os.path.join(HERE, "game_packs")
    pk = json.load(open(os.path.join(d, spec["pack"] + ".json"), encoding="utf-8"))
    pre = spec.get("clip_prefix", "")
    rows = {}
    for m in pk["moves"]:
        pref = [c for c in (m.get("prefer") or []) if c.startswith("mz_") and os.path.isfile(os.path.join(out, c + ".json"))]
        cat = m.get("category", "Game")
        r = rows.setdefault(cat, [0, 0, []])
        r[0] += 1
        if pref:
            r[1] += 1
        else:
            r[2].append(m["name"])
    return rows


def wire_pack(pack, move_to_clip, packs_dir=None):
    """Add each clip to its move's "prefer" list, after the clips already named there: a human-derived clip in
    your own library (CMU, Mixamo, the Gaelic key poses) still wins where you have it, and the Meshy clip fills the
    gap everywhere else. Returns the moves changed."""
    p = os.path.join(packs_dir or os.path.join(HERE, "game_packs"), pack + ".json")
    d = json.load(open(p, encoding="utf-8"))
    changed = []
    for m in d["moves"]:
        clip = move_to_clip.get(m["name"])
        if not clip:
            continue
        pref = list(m.get("prefer") or [])
        if clip not in pref:
            changed.append(m["name"])
            pref.append(clip)
        m["prefer"] = pref
    with open(p, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=1)
        f.write("\n")
    return changed


def unwire_pack(pack, clips, packs_dir=None):
    p = os.path.join(packs_dir or os.path.join(HERE, "game_packs"), pack + ".json")
    d = json.load(open(p, encoding="utf-8"))
    for m in d["moves"]:
        if m.get("prefer"):
            m["prefer"] = [c for c in m["prefer"] if c not in clips]
            if not m["prefer"]:
                del m["prefer"]
    with open(p, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=1)
        f.write("\n")


def run_motion(a, client=None, log=print):
    spec = load_prompts(a.pack, a.prompts or PROMPTS)
    names, mode, credits = plan(spec, a.moves.split(",") if a.moves else None, a.mode)
    out = os.path.abspath(a.out or OWNED)
    src_dir = os.path.join(out, "src", "meshy", a.pack)
    pre = spec.get("clip_prefix", "mz_%s_" % a.pack)
    if not a.force:
        names = [n for n in names if not os.path.isfile(os.path.join(out, pre + n + ".json"))]
        credits = len(names) * MZ.COST["motion_" + mode]
    log("%s: %d moves to generate in %s mode, %d credits%s" % (a.pack, len(names), mode, credits,
                                                               " (others already made; --force redoes them)" if not a.force else ""))
    for n in names:
        log("  %-18s %4.1fs  %s" % (n, spec["moves"][n]["duration"], spec["moves"][n]["prompt"][:90]))
    if a.dry_run:
        return 0
    if not names:
        made = reused(spec, out)
        if made and not a.no_wire:
            for pk in wire_targets(spec, a.pack, a.packs_dir):
                wire_pack(pk, made, a.packs_dir)
        return 0
    if a.max_credits is not None and credits > a.max_credits:
        raise SystemExit("would use %d credits, over --max-credits %d" % (credits, a.max_credits))
    client = client or MZ.Client()
    bal = client.balance().get("balance")
    if bal is not None and bal < credits:
        raise SystemExit("needs %d credits, the account has %d" % (credits, bal))
    made, rows = {}, []
    for n in names:
        m = spec["moves"][n]
        clip = pre + n
        try:
            t = client.text_to_motion(m["prompt"], m["duration"], mode)
            ext = t["result"].get("motion_format") or ("bvh" if mode == "swift" else "fbx")
            src = client.download(t["result"]["motion_url"], os.path.join(src_dir, "%s.%s" % (n, ext)))
            with open(os.path.join(src_dir, n + ".task.json"), "w", encoding="utf-8") as f:
                json.dump({k: t.get(k) for k in ("id", "status", "consumed_credits", "created_at", "finished_at")}
                          | {"prompt": m["prompt"], "duration": m["duration"], "mode": mode}, f, indent=1)
        except MZ.MeshyError as e:
            rows.append((n, "-", "meshy: %s" % e)); continue
        rec_p, bad = import_prime_safely(src, clip, m, out, a.pack, n) if mode == "prime" else \
            import_clip(src, clip, m.get("loop", False), out, a.pack, n, m["prompt"])
        rows.append((n, clip if rec_p else "-", "ok" if not bad else "; ".join(bad)))
        if rec_p and not bad:
            made[n] = clip
            if mode == "prime" and not a.no_wire:      # parallel --no-wire runs record it afterwards
                set_mode(a.pack, n, "prime", a.prompts or PROMPTS)
    _report(rows, log)
    made.update(reused(spec, out))
    if made and not a.no_wire:
        for pk in wire_targets(spec, a.pack, a.packs_dir):
            ch = wire_pack(pk, made, a.packs_dir)
            log("game_packs/%s.json: %d more moves prefer their Meshy clip" % (pk, len(ch)))
    return 0


def run_import(a, log=print):
    spec = load_prompts(a.pack, a.prompts or PROMPTS)
    out = os.path.abspath(a.out or OWNED)
    src_dir = os.path.join(out, "src", "meshy", a.pack)
    pre = spec.get("clip_prefix", "mz_%s_" % a.pack)
    made, rows = {}, []
    for n, m in spec["moves"].items():
        if m.get("reuse"):
            continue
        order = (".fbx", ".bvh") if m.get("mode") == "prime" else (".bvh", ".fbx")
        src = next((os.path.join(src_dir, n + e) for e in order if os.path.isfile(os.path.join(src_dir, n + e))), None)
        if not src:
            continue
        rec_p, bad = import_clip(src, pre + n, m.get("loop", False), out, a.pack, n, m["prompt"])
        rows.append((n, pre + n if rec_p else "-", "ok" if not bad else "; ".join(bad)))
        if rec_p and not bad:
            made[n] = pre + n
    _report(rows, log)
    if not a.no_wire:
        failed = [pre + n for n, c, s in rows if s != "ok"]
        made.update(reused(spec, out))
        for pk in wire_targets(spec, a.pack, a.packs_dir):
            if failed:
                unwire_pack(pk, failed, a.packs_dir)
            if made:
                wire_pack(pk, made, a.packs_dir)
    return 0


def reused(spec, out):
    """move -> clip for {"reuse": CLIP} entries whose clip is in the library (a missing one is reported, not wired)."""
    got = {}
    for n, m in spec["moves"].items():
        c = m.get("reuse")
        if c and os.path.isfile(os.path.join(out, c + ".json")):
            got[n] = c
        elif c:
            print("%-18s reuse %s: not in %s, left out" % (n, c, out))
    return got


def _report(rows, log):
    for n, c, s in rows:
        log("%-18s -> %-28s %s" % (n, c, s))
    log("%d clips, %d with a problem" % (len(rows), sum(s != "ok" for _, _, s in rows)))


def main(argv=None, client=None):
    ap = argparse.ArgumentParser(prog="forge.py meshy", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("balance", help="credits left (free)")
    lb = sub.add_parser("library", help="Meshy's preset animations (free)")
    lb.add_argument("--search")
    for nm in ("pack", "catalogue"):
        s = sub.add_parser(nm, help="write game_packs/<pack>.json from its catalogue" if nm == "pack"
                           else "what the catalogue covers, by category")
        s.add_argument("--pack", required=True)
        s.add_argument("--prompts")
        s.add_argument("--packs-dir", help=argparse.SUPPRESS)
    for nm in ("motion", "import"):
        s = sub.add_parser(nm, help="generate Text to Motion clips for a pack" if nm == "motion" else "re-import the saved Meshy files (free)")
        s.add_argument("--pack", required=True)
        s.add_argument("--out", help="library folder (default motion_library_owned/)")
        s.add_argument("--prompts", help="prompt folder (default game_packs/meshy/)")
        s.add_argument("--packs-dir", help=argparse.SUPPRESS)
        s.add_argument("--no-wire", action="store_true", help="do not change the pack's prefer lists")
        if nm == "motion":
            s.add_argument("--moves", help="comma list (default: every move in the prompt file)")
            s.add_argument("--mode", choices=["swift", "prime"], help="swift: 3 credits, BVH; prime: 10 credits, FBX")
            s.add_argument("--max-credits", type=int)
            s.add_argument("--dry-run", action="store_true")
            s.add_argument("--force", action="store_true", help="regenerate moves that already have a clip")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "balance":
            b = (client or MZ.Client()).balance()
            print("%s credits (monthly %s, permanent %s)" % (b.get("balance"), b.get("monthly_credits"), b.get("permanent_credits")))
            return 0
        if a.cmd == "library":
            items = [i for i in (client or MZ.Client()).animation_library(a.search) if i.get("rig_type") == "biped"]
            for i in items:
                print("%5d  %-36s %s / %s" % (i["action_id"], i["name"], i["category"], i["sub_category"]))
            print("%d biped animations" % len(items))
            return 0
        if a.cmd == "pack":
            build_full_pack(load_prompts(a.pack, a.prompts or PROMPTS), a.packs_dir)
            return 0
        if a.cmd == "catalogue":
            rows = coverage(load_prompts(a.pack, a.prompts or PROMPTS), a.packs_dir)
            tot = [0, 0]
            for cat in sorted(rows, key=lambda c: CAT_ORDER.index(c) if c in CAT_ORDER else 99):
                n, got, miss = rows[cat]
                tot[0] += n; tot[1] += got
                print("%-12s %3d moves  %3d Meshy  %s" % (cat, n, got, ("other source: " + ", ".join(miss)) if miss else ""))
            print("%d moves, %d with a Meshy clip" % tuple(tot))
            return 0
        if a.cmd == "motion":
            return run_motion(a, client)
        return run_import(a)
    except MZ.MeshyError as e:
        print("error: %s" % e, file=sys.stderr)
        return 1


def clip_events(rec, category, move):
    """Event fractions (0..1, -1 = none) for a game: ball_contact at the fastest foot (kicks, passes, skills), the
    fastest hand (throws, keeper saves) or the head's highest point (headers); a tackle's hit window around its foot
    peak. Same keys as Arena FC's CLIP_EVENTS. Worked out from the clip, so it follows what Meshy actually made."""
    import numpy as np
    from . import rig
    keys = rec.get("keys") or []
    ev = {"ball_contact": -1.0, "footsteps": [], "hit_start": -1.0, "hit_end": -1.0}
    if len(keys) < 3:
        return ev
    t = np.array([float(k[0]) for k in keys])
    t = (t - t[0]) / max(1e-6, t[-1] - t[0])
    W = [rig.evaluate(k[1]).world for k in keys]
    pos = lambda j: np.array([w[j][:3, 3] for w in W])
    speed = lambda j: np.r_[0.0, np.linalg.norm(np.diff(pos(j), axis=0), axis=1) / np.maximum(1e-6, np.diff(t))]
    mv = move.lower()
    if category == "Locomotion" or rec.get("loop"):
        if category == "Locomotion":
            ev["footsteps"] = [0.25, 0.75]
        return ev
    if re.search(r"head", mv) and category in ("Shooting", "Passing", "Aerial", "Defending"):
        ev["ball_contact"] = float(t[int(np.argmax(pos("head")[:, 1]))])
    elif re.search(r"throw|roll_out|catch|parry|punch|tip|collect|smother|spread|save|dive", mv):
        sp = np.maximum(speed("hand_L"), speed("hand_R"))
        if re.search(r"throw", mv) and not re.search(r"roll", mv):       # release: hands driving forward
            hz = pos("hips")[:, 2]                                       # relative to the body (a run-up)
            fwd = lambda j: np.r_[0.0, np.diff(pos(j)[:, 2] - hz) / np.maximum(1e-6, np.diff(t))]
            sp = np.maximum(fwd("hand_L"), fwd("hand_R"))
            over = np.maximum(pos("hand_L")[:, 1], pos("hand_R")[:, 1]) > pos("head")[:, 1]
            if re.search(r"throw_in|long_throw|overarm", mv) and (over & (sp > 0)).any():
                sp = np.where(over, sp, 0.0)                             # overhead throws release above the head
        ev["ball_contact"] = float(t[int(np.argmax(sp))])
    elif category in ("Passing", "Shooting", "Set piece", "Control", "Skill", "Ball", "Defending", "Goalkeeper", "Kicking"):
        fl, fr = speed("foot_L"), speed("foot_R")
        hl, hr = pos("foot_L")[:, 1], pos("foot_R")[:, 1]
        floor = min(hl.min(), hr.min())
        reach = 0.35 if not re.search(r"volley|bicycle|scorpion|thigh|chest", mv) else 1.2
        sp = np.maximum(np.where(hl - floor < reach, fl, 0.0), np.where(hr - floor < reach, fr, 0.0))
        if not sp[1:-1].any():
            sp = np.maximum(fl, fr)
        i = int(np.argmax(sp[1:-1])) + 1 if len(sp) > 2 else 0
        ev["ball_contact"] = float(t[i])
        if category == "Defending" and re.search(r"tackle|challenge|lunge|poke|block|intercept", mv):
            ev["hit_start"] = max(0.0, float(t[i]) - 0.12)
            ev["hit_end"] = min(1.0, float(t[i]) + 0.12)
    ev["ball_contact"] = round(ev["ball_contact"], 3)
    ev["hit_start"] = round(ev["hit_start"], 3)
    ev["hit_end"] = round(ev["hit_end"], 3)
    return ev

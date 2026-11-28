"""forge.py meshy - Meshy AI from Sprite Forge (v11.41).

    forge.py meshy balance                              free: credits left
    forge.py meshy library [--search kick]              free: Meshy's preset animation library
    forge.py meshy motion --pack gaelic --dry-run       what it would generate, and the credits
    forge.py meshy motion --pack gaelic [--moves hand_pass,tackle] [--mode swift|prime] [--max-credits 100]
    forge.py meshy import --pack gaelic                 free: re-import the saved BVH / FBX (after an importer change)

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
        if len(m["prompt"]) > 400:
            raise SystemExit("%s: prompt is %d characters (Meshy allows 400)" % (nm, len(m["prompt"])))
    return d


def plan(spec, moves=None, mode=None):
    mode = mode or spec.get("mode", "swift")
    names = [m for m in (moves or list(spec["moves"]))]
    bad = [m for m in names if m not in spec["moves"]]
    if bad:
        raise SystemExit("not in the prompt file: %s" % ", ".join(bad))
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
    if a.dry_run or not names:
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
        rec_p, bad = import_clip(src, clip, m.get("loop", False), out, a.pack, n, m["prompt"])
        rows.append((n, clip if rec_p else "-", "ok" if not bad else "; ".join(bad)))
        if rec_p and not bad:
            made[n] = clip
    _report(rows, log)
    if made and not a.no_wire:
        ch = wire_pack(a.pack, made, a.packs_dir)
        log("game_packs/%s.json: %d moves now prefer their Meshy clip" % (a.pack, len(ch)))
    return 0


def run_import(a, log=print):
    spec = load_prompts(a.pack, a.prompts or PROMPTS)
    out = os.path.abspath(a.out or OWNED)
    src_dir = os.path.join(out, "src", "meshy", a.pack)
    pre = spec.get("clip_prefix", "mz_%s_" % a.pack)
    made, rows = {}, []
    for n, m in spec["moves"].items():
        src = next((os.path.join(src_dir, n + e) for e in (".bvh", ".fbx") if os.path.isfile(os.path.join(src_dir, n + e))), None)
        if not src:
            continue
        rec_p, bad = import_clip(src, pre + n, m.get("loop", False), out, a.pack, n, m["prompt"])
        rows.append((n, pre + n if rec_p else "-", "ok" if not bad else "; ".join(bad)))
        if rec_p and not bad:
            made[n] = pre + n
    _report(rows, log)
    if not a.no_wire:
        failed = [pre + n for n, c, s in rows if s != "ok"]
        if failed:
            unwire_pack(a.pack, failed, a.packs_dir)
        if made:
            wire_pack(a.pack, made, a.packs_dir)
    return 0


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
        if a.cmd == "motion":
            return run_motion(a, client)
        return run_import(a)
    except MZ.MeshyError as e:
        print("error: %s" % e, file=sys.stderr)
        return 1

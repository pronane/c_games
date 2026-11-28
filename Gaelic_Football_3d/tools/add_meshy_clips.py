#!/usr/bin/env python3
"""Add Sprite Forge's Meshy Gaelic football clips (v11.42) to assets/models/gaelic_player.glb.

  * every Meshy Text to Motion Gaelic clip in sprite_forge/motion_library_owned (catalogue:
    sprite_forge/game_packs/meshy/gaelic_full.json), retargeted from the Sprite Forge mannequin onto
    assets/source/makehuman_template.glb (the player's 52-joint skeleton), in place, and merged into the
    player as mz_<move>. Meshes, parts, grips and every clip already in the player are kept;
  * each clip is checked with sforge.gaelic_clip.inspect_animation (unit quaternions, metre pelvis,
    forward time) before it goes in;
  * assets/models/meshy_clips.json: provenance (owner-held Meshy output, LicenseRef-Owned-Meshy, the prompt,
    the source record's sha256) and, per clip, its length and the measured contact (foot / hand / head)
    that src/meshy_clips.h uses to trim and time each action.

Idempotent: running it again replaces the Meshy clips (their old buffer data stays in the file, so to keep the GLB
small run it on a fresh player: git checkout the GLB first).

    python3 tools/add_meshy_clips.py [--check]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.path.dirname(HERE)
SF = os.path.abspath(os.path.join(GAME, "..", "sprite_forge"))
sys.path.insert(0, SF)

from sforge import bonemap as BM  # noqa: E402
from sforge import gaelic_clip as GC  # noqa: E402
from sforge import importers  # noqa: E402
from sforge import meshy_cli as MC  # noqa: E402
from sforge import motionlib  # noqa: E402
from sforge import retarget as RT  # noqa: E402
from sforge import rigrec as RR  # noqa: E402
from sforge.motions import LIB, M  # noqa: E402

PLAYER = os.path.join(GAME, "assets", "models", "gaelic_player.glb")
TEMPLATE = os.path.join(GAME, "assets", "source", "makehuman_template.glb")
PROV = os.path.join(GAME, "assets", "models", "meshy_clips.json")
HEADER = os.path.join(GAME, "src", "meshy_clips.h")

# game action -> (Meshy move, contactBy (0 none, 1 foot, 2 hand ...), old played seconds to match).
# Hand pass and solo stay on their clips: the motion-matching path is built around them (MOTION_MATCHING.md).
# Kickout, ground kick (penalty), pickup and tackle lost the review in swift (no visible strike / bend) and were
# redone in prime (v11.43); the prime takes were reviewed over these windows and kept.
ACTIONS = {
    "GAME_ACT_KICK": ("high_kick_pass", 1, (1.15 - 0.10) / 1.12),
    "GAME_ACT_FREE_KICK": ("free_from_hand", 1, (1.55 - 0.05) / 1.12),
    "GAME_ACT_KICKOUT": ("kickout_long", 1, (7.20 - 5.00) / 1.15),          # v11.43: prime takes
    "GAME_ACT_GROUND_KICK": ("penalty_kick", 1, (1.55 - 0.05) / 1.15),
    "GAME_ACT_PICKUP": ("pick_up_ground", 0, 0.62 / 1.08),
    "GAME_ACT_TACKLE": ("tackle", 0, (1.15 - 0.45) / 1.20),
    "GAME_ACT_BOUNCE": ("bounce", 0, 0.79 / 1.25),
    "GAME_ACT_CATCH": ("catch_aerial", 0, (1.70 - 0.82) / 1.08),
    "GAME_ACT_FALL": ("fall", 0, 1.50 / 1.15),
}


def window(rec, loop, want_s, contact):
    """Clip seconds [start, end] of the move itself (Meshy takes stand still before and after), and the rate
    that plays it in about the time the old segment took (clamped so it never looks slowed or sped up a lot)."""
    import numpy as np
    from sforge import rig
    keys = rec["keys"]
    dur = float(rec.get("duration") or keys[-1][0])
    t = np.array([float(k[0]) for k in keys]); t = (t - t[0]) / max(1e-6, t[-1] - t[0]) * dur
    P = np.array([[rig.evaluate(k[1]).world[j][:3, 3] for j in ("hips", "hand_L", "hand_R", "foot_L", "foot_R", "head")]
                  for k in keys])
    hz = P[:, :1, :]
    sp = np.r_[0.0, (np.linalg.norm(np.diff(P - hz * [1, 0, 1], axis=0), axis=2).max(1) / np.maximum(1e-6, np.diff(t)))]
    if loop:                                   # one cycle around the lowest hand (the bounce)
        c = float(t[int(np.argmin(np.minimum(P[:, 1, 1], P[:, 2, 1])))])
        s0, s1 = max(0.0, c - want_s / 2), min(dur, c + want_s / 2)
        return round(s0, 3), round(s1, 3), 1.0
    rate = 1.1                                 # brisk, and the same for every action
    L = want_s * rate                          # clip seconds that play in the old segment's time
    if contact >= 0:                           # the strike / release sits just past the middle, as before
        anchor, before = contact * dur, 0.55
    else:                                      # the move's busiest moment
        anchor, before = float(t[int(np.argmax(sp))]), 0.5
    s0 = anchor - before * L
    s0 = min(max(0.0, s0), max(0.0, dur - L))
    s1 = min(dur, s0 + L)
    return round(s0, 3), round(s1, 3), round(rate, 3)
CATALOGUES = [os.path.join(SF, "game_packs", "meshy", f) for f in ("gaelic.json", "gaelic_full.json")]


def takes():
    out, seen = [], set()
    for path in CATALOGUES:
        cat = json.load(open(path))
        pre = cat.get("clip_prefix", "mz_gaelic_")
        for move, m in cat["moves"].items():
            if move in seen:
                continue
            seen.add(move)
            out += _take(pre, move, m)
    return out


def _take(pre, move, m):
    out = []
    if True:
        clip = m.get("reuse") or pre + move
        p = os.path.join(motionlib.OWNED, clip + ".json")
        if os.path.isfile(p):
            out.append(dict(move=move, clip=clip, path=p, loop=bool(m.get("loop")), category=m.get("category") or
                            json.load(open(p)).get("category") or "Ball",
                            prompt=m.get("prompt") or json.load(open(p)).get("meshy", {}).get("prompt", "")))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="only check the player has every Meshy clip")
    a = ap.parse_args(argv)
    T_ = takes()
    doc, buf = GC.read_glb(PLAYER)
    have = {an.get("name") for an in doc.get("animations", [])}
    if a.check:
        miss = [t["move"] for t in T_ if "mz_" + t["move"] not in have]
        print("%d Meshy clips, %d missing from the player" % (len(T_), len(miss)))
        return 1 if miss else 0
    for t in T_:                                     # library record -> motion the mannequin can play
        nm = "mzsrc_" + t["move"]
        mv = motionlib.as_motion(t["clip"], path=motionlib.OWNED)
        if nm not in LIB:
            M(nm, t["category"], "Meshy " + t["move"], keys=mv.keys, loop=t["loop"])
        LIB[nm].duration_s = getattr(mv, "duration_s", None)
    names = ["mzsrc_" + t["move"] for t in T_]
    S = RR.from_mannequin(name="meshy_src", clips=names)
    srec = BM.detect(S)
    Tg, trec, _ = importers.load_file(TEMPLATE)
    out_names, worst = [], []
    for t, n in zip(T_, names):
        cl, rep = RT.retarget(S, srec, n, Tg, trec, root_motion="inplace", name="mz_" + t["move"])
        Tg.clips["mz_" + t["move"]] = cl
        out_names.append("mz_" + t["move"])
        if (rep["mean_dir_err_deg"] or 0) > 8:
            worst.append("%s %.1f" % (t["move"], rep["mean_dir_err_deg"]))
    tmp = os.path.join(tempfile.mkdtemp(prefix="gf_meshy_"), "clips.glb")
    RR.write_glb(Tg, tmp, out_names, root_motion="inplace")
    cdoc, cbuf = GC.read_glb(tmp)
    prov = {"generator": "Gaelic_Football_3d/tools/add_meshy_clips.py", "licence": "LicenseRef-Owned-Meshy",
            "owner": "project owner (Meshy paid plan); allowed in this repo and its builds",
            "catalogues": ["sprite_forge/game_packs/meshy/gaelic.json", "sprite_forge/game_packs/meshy/gaelic_full.json"], "clips": {}}
    bad = []
    for t, n in zip(T_, out_names):
        doc, buf, rep = GC.merge_clip(doc, buf, cdoc, cbuf, n, n)
        anim = next(an for an in doc["animations"] if an.get("name") == n)
        errs, _ = GC.inspect_animation(doc, buf, anim)
        if errs:
            bad.append((n, errs[:2]))
        rec = json.load(open(t["path"]))
        ev = MC.clip_events(rec, t["category"], t["move"])
        prov["clips"][n] = {"move": t["move"], "source": os.path.relpath(t["path"], os.path.join(GAME, "..")),
                            "sha256": hashlib.sha256(open(t["path"], "rb").read()).hexdigest(),
                            "seconds": round(float(rec.get("duration") or 0.0), 3), "loop": t["loop"],
                            "category": t["category"], "contact_frac": ev["ball_contact"], "prompt": t["prompt"]}
    if bad:
        print("rejected (not written):", bad)
        return 1
    GC.write_glb(PLAYER, doc, buf)
    lines = ["/* Generated by tools/add_meshy_clips.py - do not edit. Meshy clips (owner-held, see",
             " * assets/models/meshy_clips.json) and the game actions that play them. A clip the player GLB",
             " * lacks is skipped at load and its action keeps the original clip. */",
             "#ifndef MESHY_CLIPS_H", "#define MESHY_CLIPS_H",
             "typedef struct { int action; const char *clip; float start, end, rate; int contactBy; } MeshyAction;",
             "static const MeshyAction MESHY_ACTIONS[] = {"]
    for act, (move, by, want) in ACTIONS.items():
        n = "mz_" + move
        if n not in prov["clips"]:
            continue
        t = next(x for x in T_ if x["move"] == move)
        rec = json.load(open(t["path"]))
        s0, s1, rate = window(rec, t["loop"], want, prov["clips"][n]["contact_frac"])
        prov["clips"][n].setdefault("actions", []).append(act)
        lines.append('    { %s, "%s", %.3ff, %.3ff, %.3ff, %d },' % (act, n, s0, s1, rate, by))
    lines += ["};", "#define MESHY_ACTION_COUNT ((int)(sizeof MESHY_ACTIONS / sizeof MESHY_ACTIONS[0]))", "#endif", ""]
    with open(HEADER, "w") as f:
        f.write("\n".join(lines))
    with open(PROV, "w") as f:
        json.dump(prov, f, indent=1)
    print("merged %d Meshy clips into %s (%.1f MB); bone-direction errors over 8 deg: %s"
          % (len(out_names), PLAYER, os.path.getsize(PLAYER) / 1e6, ", ".join(worst) or "none"))
    return 0


if __name__ == "__main__":
    sys.exit(main())

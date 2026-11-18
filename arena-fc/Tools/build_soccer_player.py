#!/usr/bin/env python3
"""Build the Sprite Forge soccer player for Arena FC (mesh + skeleton + animations).

Pipeline (Sprite Forge v11.13, latest on main):
  1. Sculpt a footballer with sforge.footballer on the MakeHuman game skeleton
     (the same design tools/gaelic_forge.py uses), mesh it with
     sforge.gamemesh (marching cubes -> decimate -> skin weights).
  2. Collapse the 52 MakeHuman joint weights onto Arena FC's 18-bone skeleton
     (Data/rig_default.json bones) by nearest bind position.
  3. Bake every soccer clip from Tools/soccer_motions.py (67 clips) on the
     mannequin, then retarget mannequin -> Arena skeleton with
     sforge.retarget (in-place root motion).
  4. Write:
       Data/models/soccer_player.glb      desktop C# (GltfDocument + AnimationPlayer)
       Data/soccer_rig.json               browser GDScript (rig_default.json schema)
       Data/soccer_player_manifest.json   clip list, action aliases, material order

Materials are flat colours per body layer (skin / jersey / shorts / socks /
boots / hair) so the game can tint kits per club at runtime, exactly like the
procedural rig.  No baked kit texture is embedded.

  python3 Tools/build_soccer_player.py [--tris 16000] [--h 0.006] [--out-dir DIR]

Needs the Sprite Forge core deps (see sprite_forge/requirements-core.txt):
  pip install -r sprite_forge/requirements-core.txt
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ARENA = os.path.dirname(HERE)
SF = os.path.abspath(os.path.join(ARENA, "..", "sprite_forge"))
sys.path.insert(0, SF)
sys.path.insert(0, HERE)

import soccer_motions as SM  # noqa: E402
from sforge import bonemap as BM  # noqa: E402
from sforge import footballer as FB  # noqa: E402
from sforge import gamemesh as GM  # noqa: E402
from sforge import retarget as RT  # noqa: E402
from sforge import rigrec as RR  # noqa: E402

TEMPLATE = os.path.abspath(os.path.join(ARENA, "..", "Gaelic_Football_3d", "assets", "source", "makehuman_template.glb"))
RIG_JSON = os.path.join(ARENA, "Data", "rig_default.json")

# Sprite Forge body layers -> Arena material slots (see Tools/gen_rig.py header
# and Scripts/Godot/ProceduralRig3D.gd material_for).
LAYER_SLOT = {"skin": 0, "jersey": 1, "shorts": 2, "socks": 3, "boots": 8, "hair": 6}
LAYER_ORDER = ["skin", "jersey", "shorts", "socks", "boots", "hair"]
LAYER_COLOR = {
    "skin": [0.89, 0.70, 0.56],
    "jersey": [0.84, 0.15, 0.24],
    "shorts": [0.08, 0.13, 0.24],
    "socks": [0.97, 0.97, 0.95],
    "boots": [0.10, 0.10, 0.10],
    "hair": [0.23, 0.15, 0.08],
}


def arena_rig(rig_json: dict) -> RR.Rig:
    """Arena's 18-bone skeleton as a Sprite Forge Rig (bind = bone heads)."""
    bones = rig_json["bones"]
    r = RR.Rig("arena_soccer")
    r.bones = [b["n"] for b in bones]
    r.parent = np.array([b["p"] for b in bones], int)
    r.bind = np.array([RR.m4(None, np.array(b["h"], float)) for b in bones], float)
    r.meta = {"convention": "arena", "hips_index": r.bones.index("Hips")}
    return r


def arena_bonemap(tgt: RR.Rig) -> dict:
    """Canonical -> Arena bone.  BM.detect maps by name patterns but misses the
    Arena forearm names and mirrors L/R (Arena L is -X, mannequin L is +X);
    detect already handles the mirroring, so only patch the forearms."""
    rec = BM.detect(tgt)
    rec["map"]["forearm_L"] = "RForearm"
    rec["map"]["forearm_R"] = "LForearm"
    rec["missing"] = [k for k in BM.REQUIRED if k not in rec["map"]]
    rec["unmapped"] = [b for b in tgt.bones if b not in set(rec["map"].values())]
    return rec


def collapse_weights(J52, W52, sk, arena_heads: np.ndarray):
    """52 MakeHuman joints -> 18 Arena bones (nearest bind position), top-4."""
    mh_heads = np.array([sk.p(n) for n in sk.names], float)
    joint_map = [int(np.argmin(np.linalg.norm(arena_heads - mh_heads[i], axis=1)))
                 for i in range(len(sk.names))]
    n = len(J52)
    Wfull = np.zeros((n, len(arena_heads)), np.float32)
    rows = np.arange(n)
    for k in range(J52.shape[1]):
        mapped = np.array([joint_map[j] for j in J52[:, k]], int)
        np.add.at(Wfull, (rows, mapped), W52[:, k])
    top = np.argsort(-Wfull, axis=1)[:, :4]
    tw = np.take_along_axis(Wfull, top, 1)
    tw[tw < 0.01] = 0
    tw = tw / np.maximum(tw.sum(1, keepdims=True), 1e-9)
    top = np.where(tw > 0, top, 0)
    return top.astype(np.uint16), tw.astype(np.float32), joint_map


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tris", type=int, default=16000)
    ap.add_argument("--h", type=float, default=0.006, help="sculpt grid step (m)")
    ap.add_argument("--out-dir", default=os.path.join(ARENA, "Data"))
    ap.add_argument("--skip-glb", action="store_true")
    ap.add_argument("--skip-json", action="store_true")
    a = ap.parse_args()

    t0 = time.time()
    SM.register()
    errs = SM.validate()
    if errs:
        print("soccer motions invalid:", errs)
        return 1

    rig_json = json.load(open(RIG_JSON))
    arena_heads = np.array([b["h"] for b in rig_json["bones"]], float)
    tgt = arena_rig(rig_json)
    tgt_rec = arena_bonemap(tgt)
    if tgt_rec["missing"]:
        print("arena bonemap missing:", tgt_rec["missing"])
        return 1

    # ---- 1. sculpt + mesh on the MakeHuman game skeleton -------------------
    sk = FB.Skeleton.from_glb(TEMPLATE)
    prims, _paints = FB.design(sk, "home")
    print("design: %d shapes on %d joints" % (len(prims), len(sk.names)))
    hi, _field = GM.surface(prims, h=a.h, log=lambda *x: None)
    lo = GM.decimate(hi, a.tris)
    print("  mesh: %d -> %d tris" % (len(hi.F), len(lo.F)))
    J52, W52, own = GM.weights(lo, prims, sk)
    layer_of_vert = np.array([prims[o].layer for o in own])
    unknown = sorted(set(layer_of_vert) - set(LAYER_ORDER))
    if unknown:
        print("unknown body layers:", unknown)
        return 1

    # Face +Z (Arena forward).  The MakeHuman ball joint sits in front of the
    # foot when the rig faces +Z; flip Z if the template faces the other way.
    flip_z = float(sk.p("ball_l")[2] - sk.p("foot_l")[2]) < 0
    V = lo.V.copy()
    N = lo.N.copy()
    if flip_z:
        V[:, 2] *= -1
        N[:, 2] *= -1
        lo.F = lo.F[:, ::-1].copy()
        print("  template faces -Z: mesh mirrored to +Z")
    lo.V, lo.N = V, N
    # Boots on the ground line (the sculpted soles sit a centimetre under y=0).
    lo.V[:, 1] -= float(lo.V[:, 1].min())

    J18, W18, joint_map = collapse_weights(J52, W52, sk, arena_heads)
    print("  weights collapsed 52 -> 18 bones")

    # ---- 2. retarget every soccer clip mannequin -> Arena skeleton ---------
    src = RR.from_mannequin(name="soccer_src", clips=SM.ALL_CLIPS)
    src_rec = BM.detect(src)
    if src_rec["missing"]:
        print("mannequin bonemap missing:", src_rec["missing"])
        return 1
    reps = {}
    for name in SM.ALL_CLIPS:
        cl, rep = RT.retarget(src, src_rec, name, tgt, tgt_rec, root_motion="inplace", name=name)
        tgt.clips[name] = cl
        reps[name] = rep
    mean_err = float(np.mean([r["mean_dir_err_deg"] for r in reps.values() if r["mean_dir_err_deg"] is not None]))
    print("  retargeted %d clips (mean bone-direction error %.2f deg)" % (len(tgt.clips), mean_err))

    # ---- 3. GLB (desktop) ---------------------------------------------------
    os.makedirs(os.path.join(a.out_dir, "models"), exist_ok=True)
    glb_path = os.path.join(a.out_dir, "models", "soccer_player.glb")
    if not a.skip_glb:
        tgt.V = lo.V
        tgt.F = lo.F
        tgt.J = J18
        tgt.W = W18
        # Per-FACE material: write_glb indexes fmat by face, but layer_of_vert
        # is per-vertex.  Take the majority layer of each face's 3 corners
        # (same vote the rig-JSON path uses for slots).  Feeding the
        # per-vertex array straight in truncated the GLB to the first len(V)
        # faces -- a half-body mesh with scrambled kit materials.
        layer_idx = np.array([LAYER_ORDER.index(l) for l in layer_of_vert], int)
        face_votes = np.eye(len(LAYER_ORDER))[layer_idx][lo.F].sum(axis=1)
        tgt.fmat = face_votes.argmax(axis=1).astype(int)
        tgt.materials = [{"name": l, "color": LAYER_COLOR[l]} for l in LAYER_ORDER]
        tgt.fuv = None
        tgt.fcol = None
        tgt.textures = {}
        RR.write_glb(tgt, glb_path, clips=list(tgt.clips), root_motion="inplace")
        print("  wrote %s (%.1f MB)" % (glb_path, os.path.getsize(glb_path) / 1e6))

    # ---- 4. rig JSON (browser) ----------------------------------------------
    json_path = os.path.join(a.out_dir, "soccer_rig.json")
    if not a.skip_json:
        m, vmap = GM.unwrap(lo, 512)
        Ju, Wu = J18[vmap], W18[vmap]
        layer_u = layer_of_vert[vmap]
        slot_of_vert = np.array([LAYER_SLOT[l] for l in layer_u], int)
        idx = [[] for _ in range(9)]
        for f in m.F:
            slots = slot_of_vert[f]
            slot = int(np.bincount(slots, minlength=9).argmax())
            idx[slot].extend(int(x) for x in f)
        mats = sorted(s for s in range(9) if idx[s])
        r4 = lambda arr: [round(float(x), 4) for x in np.asarray(arr).ravel()]
        data = {
            "generator": "ArenaFC soccer rig (Tools/build_soccer_player.py, Sprite Forge v11.13)",
            "bones": rig_json["bones"],
            "pos": r4(m.V), "nrm": r4(m.N), "uv": r4(m.UV),
            "bi": [int(x) for x in Ju.ravel()], "w": r4(Wu),
            "idx": idx, "mats": mats,
            "height": round(float(m.V[:, 1].max()), 4),
        }
        # Baked animation clips: the same keyframes the GLB carries, as plain
        # JSON.  The Web template has no glTF module, so the browser cannot
        # read the GLB at runtime -- BrowserBoot plays these instead, with
        # the same cadence matching as the desktop SoccerClipRig.
        def _events_for(cname, frames):
            ev = SM.CLIP_EVENTS.get(cname, {"ball_contact": -1.0, "footsteps": [],
                                            "hit_start": -1.0, "hit_end": -1.0})
            def _fr(frac):
                return int(round(frac * (frames - 1))) if frac >= 0 else -1
            return {
                "ball_contact": _fr(ev["ball_contact"]),
                "ball_contact_frac": float(ev["ball_contact"]),
                "footsteps": [_fr(f) for f in ev.get("footsteps", [])],
                "hit_start": _fr(ev.get("hit_start", -1.0)),
                "hit_end": _fr(ev.get("hit_end", -1.0)),
            }

        clips_out = {}
        for cname, cl in tgt.clips.items():
            t_stripped = RR.strip_root_motion(tgt, cl)
            bones_out = {}
            for bi, bname in enumerate(tgt.bones):
                entry = {"r": r4(cl.R[:, bi])}
                if bname == "Hips":
                    entry["t"] = r4(t_stripped[:, bi])
                bones_out[bname] = entry
            clips_out[cname] = {
                "fps": float(cl.fps), "frames": int(cl.frames),
                "loop": bool(cname in SM.LOOP_CLIPS), "bones": bones_out,
                "events": _events_for(cname, int(cl.frames)),
            }
        data["clips"] = clips_out
        with open(json_path, "w") as f:
            json.dump(data, f, separators=(",", ":"))
        print("  wrote %s (%.1f MB, %d verts, %d tris)" % (json_path, os.path.getsize(json_path) / 1e6, len(m.V), len(m.F)))

    # ---- 5. manifest ----------------------------------------------------------
    def _manifest_events(n):
        ev = SM.CLIP_EVENTS.get(n, {"ball_contact": -1.0, "footsteps": [],
                                    "hit_start": -1.0, "hit_end": -1.0})
        frames = int(tgt.clips[n].frames)
        def _fr(frac):
            return int(round(frac * (frames - 1))) if frac >= 0 else -1
        return {
            "ball_contact": _fr(ev["ball_contact"]),
            "ball_contact_frac": float(ev["ball_contact"]),
            "footsteps": [_fr(f) for f in ev.get("footsteps", [])],
            "hit_start": _fr(ev.get("hit_start", -1.0)),
            "hit_end": _fr(ev.get("hit_end", -1.0)),
        }

    manifest = {
        "generator": "ArenaFC soccer rig (Tools/build_soccer_player.py)",
        "sprite_forge": "v11.13 (main 891facd)",
        "skeleton": "arena-18",
        "bones": tgt.bones,
        "materials": LAYER_ORDER,
        "layer_slots": LAYER_SLOT,
        "clips": [
            {"name": n, "loop": bool(SM.LOOP_CLIPS.__contains__(n)), "category": SM.CLIP_CATEGORIES[n],
             "source": SM.CLIP_SOURCES[n], "frames": int(tgt.clips[n].frames), "fps": float(tgt.clips[n].fps),
             "events": _manifest_events(n)}
            for n in SM.ALL_CLIPS
        ],
        "action_aliases": SM.ACTION_ALIASES,
        "stats": {
            "tris": int(len(lo.F)), "verts": int(len(lo.V)),
            "height_m": round(float(lo.V[:, 1].max()), 4),
            "bounds_min": [round(float(x), 4) for x in lo.V.min(0)],
            "bounds_max": [round(float(x), 4) for x in lo.V.max(0)],
            "mean_dir_err_deg": round(mean_err, 3),
            "seconds": round(time.time() - t0, 1),
        },
    }
    with open(os.path.join(a.out_dir, "soccer_player_manifest.json"), "w") as f:
        json.dump(manifest, f, indent=1)
    print("  wrote manifest (%d clips, %d action aliases)" % (len(manifest["clips"]), len(manifest["action_aliases"])))
    print(json.dumps(manifest["stats"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())

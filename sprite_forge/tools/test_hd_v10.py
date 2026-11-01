"""v10 HD Fighter checks (CI): hand-posed frames + sculpt renderer through forge.py build.

1. every attack's strongest pose (furthest hand / foot reach) sits on frame 1 or 2 - the only frames on which the
   shared online sim registers hits (HD_Fighter/multiplayer/public/sim.mjs hitbox())
2. frame counts match HD_Fighter/assets_hd/meta.json
3. a full `forge.py build` of one sculpted fighter writes 16 strips that pass tools/hd_install.py's checks
   (192x256 cells, transparent, nothing clipped, feet on the 244 baseline)"""
from __future__ import annotations
import json, os, subprocess, sys, tempfile
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
from sforge import hdfighter as H          # noqa: E402
import hd_install                          # noqa: E402

META = os.path.join(ROOT, "..", "HD_Fighter", "assets_hd", "meta.json")


# striking limb(s) and direction per attack: 2 = forward (+z, the character faces +z), 1 = up
STRIKE = {"lp": (("hand_L",), 2), "hp": (("hand_R",), 2), "lk": (("foot_L",), 2), "hk": (("foot_R",), 2),
          "throw": (("hand_L", "hand_R"), 2), "special1": (("hand_L", "hand_R"), 2), "special2": (("hand_R",), 1),
          "super": (("foot_L", "foot_R"), 2)}


def reach(st, s):
    W = st.world; hips = W["hips"][:3, 3]
    joints, ax = STRIKE[s]
    tip = {"hand_L": (0, -0.1, 0), "hand_R": (0, -0.1, 0), "foot_L": (0, -0.05, 0.17), "foot_R": (0, -0.05, 0.17)}
    return max((W[j][:3, :3] @ np.array(tip[j]) + W[j][:3, 3] - hips)[ax] for j in joints)


def main():
    fails = []
    meta = json.load(open(META))["characters"]
    for c in meta:
        for s, (_, n, _) in meta[c].items():
            if H.STATES[s][0] != n:
                fails.append("%s/%s: %d frames, meta.json says %d" % (c, s, H.STATES[s][0], n))
        for s in H.ATTACKS:
            r = [reach(st, s) for st in H.states(s, char=c)]
            pk = int(np.argmax(r))
            if pk not in (1, 2):
                fails.append("%s/%s: strongest pose on frame %d (reach %s)" % (c, s, pk, np.round(r, 2).tolist()))
    print("poses: %s" % ("OK" if not fails else "%d problem(s)" % len(fails)))
    char = sys.argv[1] if len(sys.argv) > 1 else "kairo"
    out = tempfile.mkdtemp(prefix="hd_v10_")
    cmd = [sys.executable, "forge.py", "build", "--spec", os.path.join(ROOT, "..", "HD_Fighter", "sprite_specs", char + ".txt"),
           "--moves", H.moves_for(char), "--yaw", "90", "--frame", "192x256", "--figure-h", "158", "--ground-y", "244",
           "--pivot-x", "92", "--quality", "final", "--expressions", "off", "--strips", "--no-glb", "--no-fbx", "--no-cache",
           "--out", out]
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    print(r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr[-2000:])
    if r.returncode:
        fails.append("forge.py build failed (%d): %s" % (r.returncode, r.stderr[-1500:]))
    else:
        for s, (_, n, _) in meta[char].items():
            p = os.path.join(out, char, "strips", s + ".png")
            if not os.path.exists(p):
                fails.append("missing strip " + p); continue
            for e in hd_install.check(p, n, s):
                fails.append("%s/%s: %s" % (char, s, e))
    for f in fails:
        print("FAIL", f)
    print("%d problem(s)" % len(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())

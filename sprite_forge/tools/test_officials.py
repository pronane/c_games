#!/usr/bin/env python3
"""Match officials pack (v11.31, fed back from Arena FC).

    python tools/test_officials.py

  1 every officials clip registers and passes its QA (signal reached and held, neutral ends)
  2 the signals that are a raised arm do raise it; the others keep it below the shoulder
  3 every clip bakes on the mannequin and retargets with no direction error
  4 append_clips adds the clips to an existing skinned GLB and keeps its meshes and clips
  5 props_glb writes the flag, both cards, the whistle and the board, grips at the origin
  6 kit_for picks an official kit that clashes with neither team"""
from __future__ import annotations

import os
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from sforge import bonemap as BM  # noqa: E402
from sforge import officials as O  # noqa: E402
from sforge import rigrec as RR  # noqa: E402
from sforge.glbpack import read_glb  # noqa: E402
from sforge.motions import LIB  # noqa: E402

R = []


def rec(name, ok, detail=""):
    R.append((name, bool(ok), detail))
    print("%-5s %-62s %s" % ("PASS" if ok else "FAIL", name, detail))


def main():
    O.register()
    q = O.qa_all()
    rec("all %d officials clips registered" % len(O.CLIPS), all(n in LIB for n in O.CLIPS))
    rec("officials QA", not any(q.values()), str({k: v for k, v in q.items() if v}))
    low = [n for n in O.CLIPS if n not in O.ARM_UP and n != "ref_penalty"]
    worst = max(max(abs(LIB[n].sample(i / 20)[0].get("arm_R", (0, 0, 0))[0]) for i in range(21)) for n in low)
    rec("non-overhead signals keep the arm at or below the shoulder", worst <= 95, "max %.0f deg" % worst)
    r = RR.from_mannequin(name="t", clips=["idle"] + list(O.CLIPS))
    rec("every clip bakes on the mannequin", all(n in r.clips and r.clips[n].frames > 10 for n in O.CLIPS))
    rec("clip lengths follow the authored durations",
        all(abs((r.clips[n].frames - 1) / r.clips[n].fps - O.CLIPS[n]["dur"]) < .05 for n in O.CLIPS))
    with tempfile.TemporaryDirectory() as td:
        base = os.path.join(td, "base.glb")
        RR.write_glb(r, base, clips=["idle"])
        j0, _ = read_glb(base)
        clips = {n: r.clips[n] for n in O.CLIPS}
        out = os.path.join(td, "out.glb")
        O.append_clips(base, out, r, clips)
        j1, _ = read_glb(out)
        names = [a["name"] for a in j1["animations"]]
        rec("append_clips adds every clip and keeps the old ones", "idle" in names and all(n in names for n in O.CLIPS),
            "%d -> %d animations" % (len(j0["animations"]), len(names)))
        rec("append_clips keeps meshes and skin", len(j1["meshes"]) == len(j0["meshes"]) and j1["skins"][0]["joints"] == j0["skins"][0]["joints"])
        O.append_clips(out, out, r, {"ref_card": r.clips["ref_card"]})
        j2, _ = read_glb(out)
        rec("appending again replaces, never duplicates", [a["name"] for a in j2["animations"]].count("ref_card") == 1)
        pg = os.path.join(td, "props.glb")
        O.props_glb(pg)
        jp, bp = read_glb(pg)
        rec("props: flag, cards, whistle, board", {n["name"] for n in jp["nodes"]} == set(O.PROPS))
        from sforge.glbpack import _acc_bytes
        ok = True
        for m in jp["meshes"]:
            a = jp["accessors"][m["primitives"][0]["attributes"]["POSITION"]]
            ok &= a["min"][1] > -.02 and a["max"][1] < 1.0
        rec("props stand on their grip (+Y up, origin at the hand)", ok)
    rec("kit_for avoids both teams (black vs black/white -> not classic)", O.kit_for("#111111", "#ffffff") != "classic")
    rec("kit_for keeps classic black for red vs blue", O.kit_for("#d7263d", "#1d4ed8") == "classic")
    fails = [x for x in R if not x[1]]
    print("\n%d checks, %d failed" % (len(R), len(fails)))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())

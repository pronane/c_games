#!/usr/bin/env python3
"""Limb-integrity + motion test for photo-puppet characters (v9.2).

    python tools/test_limbs.py --cutout cut/cutout.png --landmarks cut/landmarks.json [--engine skin|classic]
                               [--motion polish|classic] [--turn 90] [--preset fighter14] [--out DIR]
    python tools/test_limbs.py --selftest OUT        # on a mannequin rendered on the fly (no photo / pose model needed)

Every frame of every move is rendered straight from the rig (effects such as glows, orbs and hit tints are
stripped so they can't hide or fake a limb), then checked:

  attach    pixel coverage along every bone: neck->shoulder, shoulder->elbow->wrist, pelvis->hip->knee->ankle.
            A gap means a limb came off (an arm detached at the shoulder, a shin detached when kicking).
  feet      both ankles have body pixels around them (no missing / invisible legs).
  pieces    connected parts of the figure; more than one big part = something is floating.
  motion    per segment: peak angular speed (deg/frame) and swing reversals.  Two or more large reversals
            of an upper arm in one non-looping move = FLAPPING.  Speeds above the snap limit = a pop.
  joints    side-on views only: knees that bend forwards / elbows that bend backwards (anatomically wrong).

Writes DIR/limbs_report.json, DIR/LIMBS.md (one row per move) and DIR/limbs_fail_<move>.png (failing frames
with the skeleton drawn: green = covered bone, red = gap).  Exit code 1 if any move FAILs.
"""
from __future__ import annotations
import argparse, json, math, os, sys

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

FX_KEYS = ("glow_hands", "glow", "orb", "orb_hand", "orb_r", "orb_ahead", "tint")
BONES = [("neck", "nS"), ("neck", "fS"), ("nS", "nE"), ("nE", "nW"), ("fS", "fE"), ("fE", "fW"),
         ("pelvis", "nP"), ("pelvis", "fP"), ("nP", "nK"), ("nK", "nA"), ("fP", "fK"), ("fK", "fA")]
SEGMENTS = {"upper arm n": ("nS", "nE"), "forearm n": ("nE", "nT"), "upper arm f": ("fS", "fE"), "forearm f": ("fE", "fT"),
            "thigh n": ("nP", "nK"), "shin n": ("nK", "nA"), "thigh f": ("fP", "fK"), "shin f": ("fK", "fA")}
# rhythmic moves where repeated reversals are the point (a wave, a fist pump, a walk cycle, a breathing idle)
RHYTHMIC = {"walk": "all", "idle": "all", "fight_idle": "all", "victory": "all", "taunt": ("forearm n", "forearm f")}
LIMITS = dict(cover=0.90, foot=0.25, piece_frac=0.004, flap_amp=30.0, flap_reversals=2, snap_arm=75.0, snap_leg=60.0,
              hyper=12.0, tol_frac=0.005)


def make_sample(out):
    """render the built-in mannequin from the front (rest pose, arms down) and write cutout.png + landmarks.json
    (MediaPipe Pose 33 order, person's left = image right) projected straight from the rig joints"""
    from sforge import mesh, render, rig
    from sforge.mathutil import rx, ry
    os.makedirs(out, exist_ok=True)
    T, B, M = mesh.build_mannequin(None, include_ball=False)
    st = rig.evaluate({})
    cw, ch, fh, base = 520, 820, 720, 790
    rs = render.RenderSettings(cell_w=cw, cell_h=ch, figure_h=fh, baseline=base, yaw=0.0, pitch=0.0, ss=2, outline=False)
    render.render_state(T, B, M, mesh.palette(), st, rs).save(os.path.join(out, "cutout.png"))
    view = rx(0.0) @ ry(0.0); sc = fh / rig.HEIGHT
    def P(j, off=(0.0, 0.0, 0.0)):
        q = view @ (st.world[j][:3, 3] + np.array(off))
        return [round(cw / 2 + q[0] * sc, 1), round(base - q[1] * sc, 1), 0.99]
    h = "head"
    L = [P(h, (0, .10, .1)),                                                    # 0 nose
         P(h, (.02, .13, .1)), P(h, (.035, .13, .1)), P(h, (.05, .13, .1)),     # 1-3 left eye
         P(h, (-.02, .13, .1)), P(h, (-.035, .13, .1)), P(h, (-.05, .13, .1)),  # 4-6 right eye
         P(h, (.08, .11, 0)), P(h, (-.08, .11, 0)),                             # 7-8 ears
         P(h, (.025, .06, .1)), P(h, (-.025, .06, .1)),                         # 9-10 mouth
         P("upperarm_L"), P("upperarm_R"), P("forearm_L"), P("forearm_R"), P("hand_L"), P("hand_R"),
         P("hand_L", (.02, -.08, 0)), P("hand_R", (-.02, -.08, 0)),             # 17-18 pinky
         P("hand_L", (0, -.09, 0)), P("hand_R", (0, -.09, 0)),                  # 19-20 index
         P("hand_L", (-.02, -.05, 0)), P("hand_R", (.02, -.05, 0)),             # 21-22 thumb
         P("thigh_L"), P("thigh_R"), P("shin_L"), P("shin_R"), P("foot_L"), P("foot_R"),
         P("foot_L", (0, -.06, -.05)), P("foot_R", (0, -.06, -.05)),            # 29-30 heels
         P("foot_L", (0, -.07, .12)), P("foot_R", (0, -.07, .12))]              # 31-32 toes
    lp = os.path.join(out, "landmarks.json")
    json.dump({"note": "built-in mannequin, front view, landmarks projected from the rig", "landmarks": L}, open(lp, "w"), indent=1)
    return os.path.join(out, "cutout.png"), lp


def strip_fx(p):
    return {k: v for k, v in p.items() if k not in FX_KEYS}


def coverage(A, p, q, n=40):
    """fraction of points on segment p-q (ends trimmed 6%) that land on the figure"""
    H, W = A.shape
    ok = 0
    for t in np.linspace(0.06, 0.94, n):
        x, y = p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t
        xi, yi = int(round(x)), int(round(y))
        ok += 0 <= xi < W and 0 <= yi < H and bool(A[yi, xi])
    return ok / n


def seg_angle(J, a, b):
    return math.degrees(math.atan2(J[b][0] - J[a][0], J[b][1] - J[a][1]))


def wrap(d):
    return (d + 180.0) % 360.0 - 180.0


def reversals(series, cyclic, min_amp):
    """number of direction changes whose swing (turning point to turning point) is at least min_amp degrees"""
    if len(series) < 3:
        return 0, 0.0
    s = list(series) + ([series[0]] if cyclic else [])
    v = [wrap(b - a) for a, b in zip(s, s[1:])]
    turns, amp, cur, sign, n = [], 0.0, 0.0, 0, 0
    for d in v:
        sg = 0 if abs(d) < 3 else (1 if d > 0 else -1)
        if sg == 0:
            continue
        if sign and sg != sign:
            turns.append(abs(cur)); cur = 0.0
        sign = sg; cur += d
    turns.append(abs(cur))
    big = [t for t in turns if t >= min_amp]
    n = max(0, len(big) - 1)
    return n, max(turns) if turns else 0.0


class Photo3DRig:
    """test adapter for --engine photo3d: 'poses' are indices into the skeletal motion states of each move"""
    def __init__(self, cut, lms, yaw, pack="fighter3d"):
        from sforge import photo3d as P3, rig as RG
        self.P3, self.RG = P3, RG
        self.body = P3.PhotoBody(cut, lms, log=lambda *a: None)
        self.pack = pack
        self.yaw, self.open = P3.fighter_camera(float(yaw or 0), pack)
        self.side = abs(math.sin(math.radians(self.yaw))) > 0.5
        self.cell, self.base, self.ppm = (640, 640), 600, 360 / RG.HEIGHT
        self.stand_h = 360
        self.last_offset = (0.0, 0.0)
        self.rest = {}
        self.states = []

    def poses(self, move):
        from sforge.moves import motion_for
        from sforge import anim
        from sforge.motions import find_motion
        mo, _ = self.P3.resolve_motion(move, self.pack, self.open)
        if mo.category == "Fighter3D":
            self.body.look = 0.0
        sts = self.P3.sample_states(mo, move.frames, move.loop)      # exactly what the build renders
        i0 = len(self.states); self.states += sts
        return [{"_s": i0 + i} for i in range(len(sts))], bool(move.loop)

    def render(self, pose):
        st = self.states[pose["_s"]] if "_s" in pose else self.RG.evaluate({})
        return self.body.render(st, yaw=self.yaw, cell=self.cell, baseline=self.base, fig_px_per_m=self.ppm)

    def pose3d(self, pose):
        """posed 3D joints (world metres) + the hips' rotation (body forward = its z column)"""
        st = self.states[pose["_s"]] if "_s" in pose else self.RG.evaluate({})
        self.body.pose_matrices(st)
        pp = self.body._pp
        out = {}
        for k, s_ in (("n", "L"), ("f", "R")):
            out.update({k + "S": pp["upperarm_" + s_], k + "E": pp["forearm_" + s_], k + "T": pp["tip_" + s_],
                        k + "P": pp["thigh_" + s_], k + "K": pp["shin_" + s_], k + "A": pp["foot_" + s_]})
        return out, np.asarray(st.world["hips"])[:3, :3]

    def pose_joints(self, pose):
        self.render(pose)
        j = self.body.last_joints
        out = {"neck": j["neck"], "pelvis": j["hips"]}
        for k, s_ in (("n", "L"), ("f", "R")):
            out.update({k + "S": j["upperarm_" + s_], k + "E": j["forearm_" + s_], k + "W": j["hand_" + s_],
                        k + "T": j["tip_" + s_], k + "P": j["thigh_" + s_], k + "K": j["shin_" + s_], k + "A": j["foot_" + s_]})
        return out


def make_rig(cut, lms, engine, turn):
    from sforge import puppet as PP
    if engine == "photo3d":
        rig = Photo3DRig(cut, lms, turn)
        return rig, None
    if turn:
        from sforge import turn as TN
        res = TN.build_turned(cut, lms, yaw=float(turn), depth="auto", log=lambda *a: None)
        if TN.is_side(float(turn)) and math.sin(math.radians(float(turn))) < 0:
            TN.mirror_turned(res)
        rig = TN.make_rig(res, lms)
        keyfn = lambda name, n: TN.rig_move_keys(rig, name, n)
        return rig, keyfn
    if engine == "skin":
        from sforge import skinwarp as SKW
        rig = SKW.SkinRig(cut, lms)
    else:
        rig = PP.Rig(cut, lms)
    return rig, (lambda name, n: PP.move_keys(name, rig.rest, n))


def poses_for(keyfn, rig, move, motion):
    from sforge import puppet as PP
    if hasattr(rig, "poses"):
        return rig.poses(move)
    keys, cyc = keyfn(move.name, move.frames)
    keys = PP.normalize_keys(keys, rig.rest)      # exactly what build.py does
    if len(keys) == move.frames:
        return keys, cyc
    if motion == "polish":
        from sforge import motionpolish as MPL
        return MPL.polished(keys, move.frames, rig.rest, move.name, cyc), cyc
    return PP._sample(keys, move.frames), cyc


def check(cut_path, lm_path, engine="skin", motion="polish", turn=None, preset="fighter14", out="limbs_out", log=print):
    from sforge import moves as MV
    os.makedirs(out, exist_ok=True)
    cut = Image.open(cut_path).convert("RGBA")
    d = json.load(open(lm_path))
    lms = d["landmarks"] if isinstance(d, dict) else d
    rig, keyfn = make_rig(cut, lms, engine, turn)
    side = bool(getattr(rig, "side", False))
    report = {"engine": engine if engine == "photo3d" else ("side-rig" if side else engine), "motion": motion, "turn": turn, "preset": preset,
              "limits": LIMITS, "moves": {}}
    # reference: bone coverage in the rest pose.  A landmark can sit on the silhouette edge (a sloping shoulder), so
    # a bone is judged against itself standing still: "came off" = coverage fell well below its rest value.
    im0 = rig.render({})
    a0 = ndi.binary_dilation(np.asarray(im0)[..., 3] > 128, iterations=max(2, int(round(LIMITS["tol_frac"] * rig.stand_h))))
    o0 = getattr(rig, "last_offset", (0.0, 0.0))
    J0 = {k: (v[0] + o0[0], v[1] + o0[1]) for k, v in rig.pose_joints({}).items()}
    rest_cov = {"%s-%s" % b: coverage(a0, J0[b[0]], J0[b[1]]) for b in BONES}
    need = {b: min(LIMITS["cover"], c - 0.08) for b, c in rest_cov.items()}
    report["rest_coverage"] = {b: round(c, 3) for b, c in rest_cov.items()}
    worst = 0
    for mv in MV.preset(preset):
        poses, cyc = poses_for(keyfn, rig, mv, motion)
        frames, angles, fails = [], {k: [] for k in SEGMENTS}, []
        dirs3 = {k: [] for k in SEGMENTS}
        for i, p in enumerate(poses):
            p = strip_fx(p)
            im = rig.render(p)
            a = np.asarray(im)[..., 3] > 128
            # tolerance: a projected joint can sit a few px off the sleeve centre in 3/4 views; a real detachment
            # is also caught by the 'pieces' check (a limb that came off is a separate part)
            A = ndi.binary_dilation(a, iterations=max(2, int(round(LIMITS["tol_frac"] * rig.stand_h))))
            ox, oy = getattr(rig, "last_offset", (0.0, 0.0))
            J = {k: (v[0] + ox, v[1] + oy) for k, v in rig.pose_joints(p).items()}
            cov = {"%s-%s" % b: round(coverage(A, J[b[0]], J[b[1]]), 3) for b in BONES}
            r = 0.035 * rig.stand_h
            feet = {}
            for k in ("n", "f"):
                x, y = J[k + "A"]
                yy, xx = np.ogrid[0:a.shape[0], 0:a.shape[1]]
                disc = (xx - x) ** 2 + (yy - y) ** 2 <= r * r
                feet[k] = round(float(a[disc].mean()) if disc.any() else 0.0, 3)
            lab, n = ndi.label(a)
            sizes = ndi.sum(np.ones_like(lab), lab, range(1, n + 1)) if n else np.array([0])
            total = float(sizes.sum()) or 1.0
            big = int((sizes > LIMITS["piece_frac"] * total).sum())
            if hasattr(rig, "pose3d"):          # 3D body: motion measured on the real 3D bones, not their projection
                J3, Rh = rig.pose3d(p)
                fwd = Rh[:, 2]
                for sname, (s0, s1) in SEGMENTS.items():
                    d = np.asarray(J3[s1]) - np.asarray(J3[s0]); d = d / max(1e-9, np.linalg.norm(d))
                    dirs3[sname].append(d)
                    angles[sname].append(math.degrees(math.atan2(float(d @ fwd), float(-d[1]))))   # sagittal swing
            else:
                for sname, (s0, s1) in SEGMENTS.items():
                    angles[sname].append(seg_angle(J, s0, s1))
            bad = [b for b, c in cov.items() if c < need[b]] + \
                  ["foot " + k for k, c in feet.items() if c < LIMITS["foot"]] + \
                  (["%d floating parts" % (big - 1)] if big > 1 else [])
            hyper = []
            if hasattr(rig, "pose3d"):           # knees must not bend forwards (3D, in the body's own sagittal plane)
                for k in ("n", "f"):
                    knee = wrap(angles["shin " + k][-1] - angles["thigh " + k][-1])
                    if knee > LIMITS["hyper"] + 8:
                        hyper.append("knee %s bends forward %.0f deg" % (k, knee))
            elif side:     # knee must not bend forwards, elbow must not bend backwards (angles from 'down', +=forward)
                for k in ("n", "f"):
                    knee = wrap(seg_angle(J, k + "K", k + "A") - seg_angle(J, k + "P", k + "K"))
                    elbow = wrap(seg_angle(J, k + "E", k + "T") - seg_angle(J, k + "S", k + "E"))   # forearm = elbow -> hand tip, as the rig defines it
                    if knee > LIMITS["hyper"]:
                        hyper.append("knee %s bends forward %.0f deg" % (k, knee))
                    if elbow < -LIMITS["hyper"]:
                        hyper.append("elbow %s bends backward %.0f deg" % (k, -elbow))
            bad += hyper
            frames.append(dict(frame=i, coverage=cov, feet=feet, pieces=big, issues=bad))
            if bad:
                fails.append((i, im, J, cov, bad))
        motion_issues, mstats = [], {}
        rhythm = RHYTHMIC.get(mv.name, ())
        for sname, ser in angles.items():
            if dirs3[sname]:                     # 3D: true angle between successive bone directions
                dv = dirs3[sname]
                sp = [math.degrees(math.acos(float(np.clip(a_ @ b, -1, 1)))) for a_, b in zip(dv, dv[1:] + ([dv[0]] if cyc else []))] or [0.0]
            else:
                sp = [abs(wrap(b - a_)) for a_, b in zip(ser, ser[1:] + ([ser[0]] if cyc else []))] or [0.0]
            nrev, amp = reversals(ser, cyc, LIMITS["flap_amp"])
            mstats[sname] = dict(peak_speed=round(max(sp), 1), reversals=nrev, max_swing=round(amp, 1))
            exempt = rhythm == "all" or sname in rhythm
            if sname.startswith("upper arm") and nrev >= LIMITS["flap_reversals"] and not exempt:
                motion_issues.append("FLAP %s: %d reversals of >%d deg" % (sname, nrev, LIMITS["flap_amp"]))
            lim = LIMITS["snap_arm"] if "arm" in sname else LIMITS["snap_leg"]
            if max(sp) > lim:
                motion_issues.append("SNAP %s: %.0f deg in one frame (limit %d)" % (sname, max(sp), lim))
        status = "FAIL" if fails or any(m.startswith("FLAP") for m in motion_issues) else ("WARN" if motion_issues else "PASS")
        worst = max(worst, {"PASS": 0, "WARN": 1, "FAIL": 2}[status])
        report["moves"][mv.name] = dict(status=status, frames=len(poses), frame_issues=[f for f in frames if f["issues"]],
                                        motion=mstats, motion_issues=motion_issues,
                                        min_coverage=min(min(f["coverage"].values()) for f in frames))
        if fails:
            _fail_sheet(fails, os.path.join(out, "limbs_fail_%s.png" % mv.name))
        log("  %-12s %-4s  min cover %.2f  %s%s" % (mv.name, status, report["moves"][mv.name]["min_coverage"],
                                                  "; ".join(sorted({x for f in fails for x in f[4]}))[:110],
                                                  ("  | " + "; ".join(motion_issues)) if motion_issues else ""))
    json.dump(report, open(os.path.join(out, "limbs_report.json"), "w"), indent=1)
    _markdown(report, os.path.join(out, "LIMBS.md"))
    report["worst"] = ["PASS", "WARN", "FAIL"][worst]
    return report


def _fail_sheet(fails, path, cell=360, need=None):
    tiles = []
    for i, im, J, cov, bad in fails[:6]:
        im = im.copy(); d = ImageDraw.Draw(im)
        for b in BONES:
            c = cov["%s-%s" % b]
            d.line([J[b[0]], J[b[1]]], fill=(0, 220, 0, 255) if c >= LIMITS["cover"] else (255, 0, 0, 255), width=6)
        bb = im.getbbox() or (0, 0, im.width, im.height)
        t = im.crop(bb); s = cell / max(t.size); t = t.resize((max(1, int(t.width * s)), max(1, int(t.height * s))))
        tile = Image.new("RGB", (cell, cell + 30), (40, 40, 48)); tile.paste(t, ((cell - t.width) // 2, 0), t)
        ImageDraw.Draw(tile).text((4, cell + 4), ("frame %d: " % i) + ", ".join(bad)[:60], fill=(255, 200, 200))
        tiles.append(tile)
    sheet = Image.new("RGB", (cell * len(tiles), cell + 30), (40, 40, 48))
    for j, t in enumerate(tiles):
        sheet.paste(t, (j * cell, 0))
    sheet.save(path)


def _markdown(rep, path):
    L = ["# Limb + motion test", "", "engine `%s`, motion `%s`, turn `%s`, preset `%s`" % (rep["engine"], rep["motion"], rep["turn"], rep["preset"]),
         "", "| move | result | frames | min bone cover | worst arm speed (deg/frame) | arm reversals | issues |", "|---|---|---|---|---|---|---|"]
    for m, r in rep["moves"].items():
        arm = [v for k, v in r["motion"].items() if "arm" in k]
        iss = sorted({x for f in r["frame_issues"] for x in f["issues"]}) + r["motion_issues"]
        L.append("| %s | %s | %d | %.2f | %.0f | %d | %s |" % (m, r["status"], r["frames"], r["min_coverage"],
                 max(a["peak_speed"] for a in arm), max(a["reversals"] for a in arm if True), "; ".join(iss) or "-"))
    open(path, "w").write("\n".join(L) + "\n")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cutout"); ap.add_argument("--landmarks")
    ap.add_argument("--engine", default="skin", choices=["skin", "classic", "photo3d"])
    ap.add_argument("--motion", default="polish", choices=["polish", "classic"])
    ap.add_argument("--turn", default=None)
    ap.add_argument("--preset", default="fighter14")
    ap.add_argument("--out", default="limbs_out")
    ap.add_argument("--selftest", metavar="OUT", help="render a front mannequin with exact landmarks and test front / 35 / 90")
    a = ap.parse_args(argv)
    if a.selftest:
        # a front-facing mannequin is rendered on the fly with EXACT landmarks (projected rig joints), so the
        # test needs no photo of a real person and no pose model
        sdir = os.path.join(a.selftest, "sample")
        cut, lm = make_sample(sdir)
        worst = "PASS"
        for turn in (None, "35", "90"):              # the skin engine is the gate; classic is the old default
            print("== mannequin  engine=skin turn=%s" % turn)
            r = check(cut, lm, "skin", a.motion, turn, a.preset, os.path.join(a.selftest, "skin_%s" % (turn or 0)))
            worst = max(worst, r["worst"], key=["PASS", "WARN", "FAIL"].index)
        print("selftest:", worst)
        return 1 if worst == "FAIL" else 0
    if not (a.cutout and a.landmarks):
        ap.error("--cutout and --landmarks are required (or --selftest OUT)")
    r = check(a.cutout, a.landmarks, a.engine, a.motion, a.turn, a.preset, a.out)
    print("result:", r["worst"], "->", a.out)
    return 1 if r["worst"] == "FAIL" else 0


if __name__ == "__main__":
    sys.exit(main())

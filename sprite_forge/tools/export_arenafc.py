#!/usr/bin/env python3
"""Game adapter: Sprite Forge cut-out + pose landmarks -> Arena FC CharacterSpec JSON (3D procedural rig).

  python tools/export_arenafc.py cut/cutout.png cut/landmarks.json OUT.json --name "Mike Timon" [--number 7]
         [--height 1.80] [--role Midfielder] [--bald] [--hair "#b06b2c"]

Arena FC builds every player as a skinned 3D mesh from a CharacterSpec (Scripts/Core/CharacterSpec.cs), so a photo
character goes in as measured proportions + the photo's own colours, not as sprites:
  skin      median of the cheeks          -> nearest SkinPalette index
  kit       torso (sweater) / sleeves     -> KitPrimary; brightest large cluster on the torso (print) -> KitSecondary
  shorts    thighs (trousers)             -> ShortsColor;   socks/boots: ankles / feet
  shape     shoulder width / height and leg / arm length vs the editor's defaults (clamped to its Sanitize ranges)
Copy OUT.json into the game's user://characters folder and use "Load selected character JSON" in the editor.
Pure numpy + Pillow; landmarks are MediaPipe-33 order as written by `forge.py cutout`."""
import argparse, json, math
import numpy as np
from PIL import Image

PALETTE = ["#f6d5bd", "#eab998", "#d69a72", "#b8754d", "#8c5433", "#5e3520", "#3b2116"]


def hx(c):
    return "#%02x%02x%02x" % tuple(int(max(0, min(255, v))) for v in c)


def rgb(h):
    return np.array([int(h[i:i + 2], 16) for i in (1, 3, 5)], float)


def sample(img, a, pts, r):
    """median colour of opaque pixels in discs around pts"""
    H, W = a.shape
    yy, xx = np.mgrid[0:H, 0:W]
    m = np.zeros((H, W), bool)
    for x, y in pts:
        m |= (xx - x) ** 2 + (yy - y) ** 2 <= r * r
    m &= a > 200
    return np.median(img[m], 0) if m.sum() > 20 else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cutout"); ap.add_argument("landmarks"); ap.add_argument("out")
    ap.add_argument("--name", default="Photo Player"); ap.add_argument("--number", type=int, default=7)
    ap.add_argument("--height", type=float, default=1.80); ap.add_argument("--role", default="Midfielder")
    ap.add_argument("--bald", action="store_true"); ap.add_argument("--hair", default=None)
    a = ap.parse_args()
    im = np.asarray(Image.open(a.cutout).convert("RGBA")).astype(float)
    rgbim, al = im[..., :3], im[..., 3]
    d = json.load(open(a.landmarks)); L = [(p[0], p[1]) for p in (d["landmarks"] if isinstance(d, dict) else d)]
    P = lambda i: np.array(L[i], float)
    sh_w = np.linalg.norm(P(11) - P(12)); hip_mid = (P(23) + P(24)) / 2; sh_mid = (P(11) + P(12)) / 2
    rows = np.nonzero((al > 128).any(1))[0]; H = rows[-1] - rows[0]
    r = 0.025 * H
    eyes = (P(2) + P(5)) / 2
    forehead = [tuple(eyes + (eyes - P(0)) * 1.3)]        # no beard / stubble / nostril shadow up there
    skin = sample(rgbim, al, forehead, r * 0.7)
    torso = sample(rgbim, al, [tuple(sh_mid + (hip_mid - sh_mid) * t) for t in (0.25, 0.55, 0.8)], r * 1.2)
    sleeves = sample(rgbim, al, [tuple((P(11) + P(13)) / 2), tuple((P(12) + P(14)) / 2)], r * 0.6)
    thighs = sample(rgbim, al, [tuple((P(23) + P(25)) / 2), tuple((P(24) + P(26)) / 2)], r)
    ankles = sample(rgbim, al, [tuple(P(27)), tuple(P(28))], r * 0.5)
    feet = sample(rgbim, al, [tuple(P(31)), tuple(P(32))], r * 0.6)
    # print / trim colour: brightest 8% of the torso pixels
    yy, xx = np.mgrid[0:al.shape[0], 0:al.shape[1]]
    tm = (al > 200) & (yy > sh_mid[1]) & (yy < hip_mid[1]) & (np.abs(xx - sh_mid[0]) < sh_w * 0.4)
    tp = rgbim[tm]; lum = tp.mean(1); trim = np.median(tp[lum >= np.percentile(lum, 92)], 0) if len(tp) else None
    skin_i = int(np.argmin([np.linalg.norm(rgb(c) - skin) for c in PALETTE])) if skin is not None else 2
    torso_len = np.linalg.norm(hip_mid - sh_mid)
    leg = (np.linalg.norm(P(23) - P(27)) + np.linalg.norm(P(24) - P(28))) / 2
    arm = (np.linalg.norm(P(11) - P(13)) + np.linalg.norm(P(13) - P(15)) + np.linalg.norm(P(12) - P(14)) + np.linalg.norm(P(14) - P(16))) / 2
    # typical adult ratios (Drillis & Contini): shoulder width ~0.259 H, leg (hip-ankle) ~0.49 H, arm ~0.44 H
    clamp = lambda v, lo, hi: float(max(lo, min(hi, v)))
    notes = []
    def ratio(v, norm, what):
        """a phone photo taken close from chest height shortens the legs and lengthens the torso (perspective);
        a ratio more than 15% off the adult norm is treated as camera distortion, not anatomy"""
        k = (v / H) / norm
        if abs(k - 1) > 0.15:
            notes.append("%s %.2f x norm looks like perspective (camera close / high) - using 1.0" % (what, k))
            return 1.0
        return k
    spec = {
        "Name": a.name, "DisplayName": a.name.upper(), "Number": a.number, "Role": a.role,
        "Height": clamp(a.height, 1.5, 2.1),
        "Bulk": clamp((sh_w / H) / 0.259 * 0.95 + 0.05, 0.75, 1.35),
        "LegLength": clamp(ratio(leg, 0.40, "leg"), 0.85, 1.18),     # MediaPipe hip points sit high: hip-ankle ~0.40 H
        "ArmLength": clamp(ratio(arm, 0.36, "arm"), 0.85, 1.18),    # shoulder-elbow-wrist ~0.36 H
        "HeadScale": 1.0, "ShoulderWidth": clamp((sh_w / H) / 0.259, 0.8, 1.25),
        "SkinTone": skin_i, "HairStyle": 3 if a.bald else 1,
        "HairColor": a.hair or (hx(skin * 0.8) if a.bald else "#4a2f1b"),
        "KitPrimary": hx(torso if torso is not None else sleeves),
        "KitSecondary": hx(trim) if trim is not None else "#f7f7f2",
        "ShortsColor": hx(thighs) if thighs is not None else "#14213d",
        "SocksColor": hx(ankles) if ankles is not None else "#f7f7f2",
        "BootsColor": hx(feet) if feet is not None else "#ffd166",
        "GlovesColor": "#2b2d42", "LongSleeves": bool(sleeves is not None and torso is not None and np.linalg.norm(sleeves - torso) < 40),
        "Pace": 0.72, "Shooting": 0.66, "Passing": 0.74, "Defending": 0.58, "Goalkeeping": 0.10, "StaminaMax": 0.85,
        "BoneRotations": {},
    }
    json.dump(spec, open(a.out, "w"), indent=2)
    for n in notes:
        print("note:", n)
    print(json.dumps({k: spec[k] for k in ("SkinTone", "KitPrimary", "KitSecondary", "ShortsColor", "BootsColor", "Bulk", "LegLength", "ArmLength", "LongSleeves")}))


if __name__ == "__main__":
    main()

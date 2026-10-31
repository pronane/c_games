#!/usr/bin/env python3
"""Objective quality report for photo-built characters (v9.4) - how good or bad are the sprites, measured.

    python tools/quality_report.py --photo cut/cutout.png --landmarks cut/landmarks.json \
        --build "2D front=out/a/name" --build "photo3d 35=out/b/name" [--out quality] [--models DIR]
        (--build "LABEL=DIR@ref.png" judges that build against another reference, e.g. the proportion-corrected cut-out)

Every number compares the sprites with the person's own photo, using independent, published tools:

  face found     % of ALL frames in which YuNet (OpenCV's CNN face detector, Wu et al. / libfacedetection) or a Haar
                 frontal / profile cascade (Viola-Jones, OpenCV) finds a face.  A sprite whose face can't be found
                 by a face detector won't read as a person either.
  (reference = the photo scaled to the same figure height, through the same steps: 100% / 1.0 = as good as the
   photo itself can be at that sprite size)
  identity       aligned-face SSIM: each detected face is warped onto the standard 112x112 ArcFace template with its
                 5 YuNet landmarks, exactly like the photo's face, and compared (structural similarity, Wang et al.
                 2004; 1.0 = identical).  Measures whether it is still recognisably the same face.
  sharpness      Laplacian variance of the aligned face / the photo's aligned face (100% = as crisp as the photo
                 at that size; > 100% = over-sharpened / aliased).
  naturalness    BRISQUE (Mittal et al. 2012, OpenCV quality module, LIVE model; 0 best .. 100 worst) of the idle
                 figure on mid-grey, next to the photo scaled to the same height.
  head           crown (silhouette top) to chin (bottom of the YuNet face box) / standing height of the idle frame
  colour         median CIELAB dE of the torso and leg bands vs the photo (< 5 hard to see, > 10 obvious)
  proportions    head height / stature and hip height / stature against Drillis & Contini (1966) adult constants
                 (head 0.130 H, hip 0.530 H, knee 0.285 H) - from the landmarks (photo) and from the face box (sprites).

Models: YuNet ONNX + Haar XMLs + BRISQUE yml are looked up in --models (default tools/models/; fetched by
tools/setup_quality_models.sh from github.com/ShiqiYu/libfacedetection.train, opencv/opencv 4.x and opencv_contrib).
Writes OUT/QUALITY.md, OUT/quality.json and OUT/faces.png (aligned faces, photo first)."""
from __future__ import annotations
import argparse, glob, json, os, re, sys
import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE = np.array([[38.2946, 51.6963], [73.5318, 51.5014], [56.0252, 71.7366], [41.5493, 92.3655], [70.7299, 92.2041]],
                    np.float32)
DC = {"head": 0.130, "hip": 0.530, "knee": 0.285}          # Drillis & Contini 1966, fraction of stature


def _find(models, *names):
    for n in names:
        for p in glob.glob(os.path.join(models, "**", n), recursive=True):
            return p
    return None


class Judge:
    def __init__(self, models):
        import cv2
        try:
            cv2.setLogLevel(2)              # errors only
        except Exception:
            pass
        self.cv2 = cv2
        self.yunet_path = _find(models, "yunet_s_640_640.onnx", "yunet_n_640_640.onnx", "face_detection_yunet*.onnx")
        self.haar_f = _find(models, "haarcascade_frontalface_alt2.xml", "haarcascade_frontalface_default.xml")
        self.haar_p = _find(models, "haarcascade_profileface.xml")
        self.bq_model = _find(models, "brisque_model_live.yml"); self.bq_range = _find(models, "brisque_range_live.yml")
        self.cf = cv2.CascadeClassifier(self.haar_f) if self.haar_f else None
        self.cp = cv2.CascadeClassifier(self.haar_p) if self.haar_p else None

    def faces(self, rgb):
        """[(score, box, 5 landmarks)] from YuNet on an RGB uint8 image"""
        if not self.yunet_path:
            return []
        cv2 = self.cv2
        bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        h, w = bgr.shape[:2]
        det = cv2.FaceDetectorYN.create(self.yunet_path, "", (w, h), 0.5, 0.3, 50)
        _, f = det.detect(bgr)
        out = []
        if f is not None:
            for r in f:
                out.append((float(r[-1]), r[:4].copy(), r[4:14].reshape(5, 2).copy()))
        return sorted(out, key=lambda t: -t[0])

    def haar(self, rgb):
        cv2 = self.cv2
        g = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        hits = []
        for c, flip in ((self.cf, False), (self.cp, False), (self.cp, True)):
            if c is None:
                continue
            gi = g[:, ::-1].copy() if flip else g
            r = c.detectMultiScale(gi, 1.08, 3, minSize=(16, 16))
            hits += list(r)
        return len(hits) > 0

    def align(self, rgb, lm5):
        cv2 = self.cv2
        M, _ = cv2.estimateAffinePartial2D(lm5.astype(np.float32), TEMPLATE, method=cv2.LMEDS)
        if M is None:
            return None
        return cv2.warpAffine(rgb, M, (112, 112), flags=cv2.INTER_LINEAR, borderValue=(128, 128, 128))

    def brisque(self, rgb):
        if not (self.bq_model and self.bq_range):
            return None
        cv2 = self.cv2
        try:
            return float(cv2.quality.QualityBRISQUE_compute(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), self.bq_model, self.bq_range)[0])
        except Exception:
            return None


# ---- silhouette head height and garment colour (from the first quality tool)
from scipy import ndimage as ndi
def figure_box(im):
    a = np.asarray(im)[..., 3] > 100
    ys, xs = np.nonzero(a)
    return (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1) if len(xs) else None


def neck_row(im):
    """row of the narrowest silhouette between the head and the shoulders"""
    a = np.asarray(im)[..., 3] > 100
    bb = figure_box(im)
    if bb is None:
        return None
    t, b = bb[1], bb[3]; H = b - t
    w = a[t:t + int(0.32 * H)].sum(1).astype(float)
    if len(w) < 10:
        return None
    w = ndi.uniform_filter1d(w, 3)
    hmax = int(np.argmax(w[: int(0.16 * H) + 1]))            # widest row of the head
    seg = w[hmax:]
    return t + hmax + int(np.argmin(seg[: max(2, int(0.14 * H))]))


def head_box(im):
    bb = figure_box(im)
    n = neck_row(im)
    if bb is None or n is None:
        return None
    t = bb[1]; hh = max(4, n - t)
    a = np.asarray(im)[t:n, :, 3] > 100
    xs = np.nonzero(a.any(0))[0]
    cx = int(xs.mean()) if len(xs) else (bb[0] + bb[2]) // 2
    return (cx - hh // 2 - 2, t, cx + hh // 2 + 2, n)


def lab_median(im, y0f, y1f):
    from skimage.color import rgb2lab
    bb = figure_box(im)
    t, b = bb[1], bb[3]; H = b - t
    A = np.asarray(im.convert("RGBA"))
    band = A[t + int(y0f * H): t + int(y1f * H)]
    m = band[..., 3] > 200
    if m.sum() < 10:
        return None
    return np.median(rgb2lab(band[m][:, :3][None].astype(np.float32) / 255.0)[0], 0)


def dE(a, b):
    return float(np.linalg.norm(a - b)) if a is not None and b is not None else float("nan")




def on_grey(im, up=1):
    im = im.convert("RGBA")
    bb = im.getchannel("A").getbbox() or (0, 0, im.width, im.height)
    pad = 12
    im = im.crop((max(0, bb[0] - pad), max(0, bb[1] - pad), min(im.width, bb[2] + pad), min(im.height, bb[3] + pad)))
    g = Image.new("RGBA", im.size, (128, 128, 128, 255)); g.alpha_composite(im)
    g = g.convert("RGB")
    if up != 1:
        g = g.resize((g.width * up, g.height * up), Image.LANCZOS)
    return np.asarray(g), bb


def head_ratio(judge, im, up=3):
    """crown (silhouette top) to chin (YuNet face box bottom) / standing height - detector based, not silhouette"""
    rgb, bb = on_grey(im, up)
    f = judge.faces(rgb)
    if not f:
        return None
    x, y, w, h = f[0][1]
    pad = 12
    top_in_crop = (bb[1] - max(0, bb[1] - pad))          # where the figure starts inside the padded crop
    chin = (y + h) / up - top_in_crop
    return float(chin / max(1, bb[3] - bb[1]))


def lapvar(g):
    from scipy import ndimage as ndi
    return float(ndi.laplace(g.astype(np.float32)).var())


def ssim(a, b):
    from skimage.metrics import structural_similarity
    return float(structural_similarity(a, b, data_range=255))


def photo_props(cut, lms):
    sys.path.insert(0, HERE)
    from sforge.proportions import measure
    rows, frac, H = measure(cut, lms)
    return {"head": 1 - frac["chin"], "hip": frac["hip"], "knee": frac["knee"]}


def evaluate(judge, photo, lms, builds, up=3):
    cv2 = judge.cv2
    # reference face from the photo
    prgb = np.asarray(Image.new("RGBA", photo.size, (128, 128, 128, 255)).copy())
    pg = Image.new("RGBA", photo.size, (128, 128, 128, 255)); pg.alpha_composite(photo.convert("RGBA"))
    prgb = np.asarray(pg.convert("RGB"))
    pf = judge.faces(prgb)
    if not pf:
        raise SystemExit("no face found in the photo - can't score identity")
    pa = judge.align(prgb, pf[0][2])
    pgray = cv2.cvtColor(pa, cv2.COLOR_RGB2GRAY)
    p_sharp = lapvar(pgray)
    pfig = photo.getchannel("A").getbbox(); p_h = pfig[3] - pfig[1]
    res = {"photo": {"proportions": photo_props(photo, lms), "face_box_frac": float(pf[0][1][3]) / p_h,
                     "head_yunet": head_ratio(judge, photo)}}
    faces_strip = [pa]
    base_photo = photo
    for label, d in builds:
        photo = base_photo
        if "@" in d:                     # LABEL=DIR@REF.png: judge against another reference (e.g. the proportion-corrected cut-out)
            d, rp = d.split("@", 1); photo = Image.open(rp).convert("RGBA")
            pfig = photo.getchannel("A").getbbox(); p_h = pfig[3] - pfig[1]
        else:
            pfig = base_photo.getchannel("A").getbbox(); p_h = pfig[3] - pfig[1]
        files = sorted(glob.glob(os.path.join(d, "moves", "*.png")))
        # the fair reference: the photo scaled to THIS build's figure height, through the same detect + align steps
        idle = Image.open(os.path.join(d, "moves", "idle_00.png"))
        _, ibb = on_grey(idle, 1)
        fig_h = ibb[3] - ibb[1]
        ref = photo.resize((max(1, int(photo.width * fig_h / p_h)), max(1, int(photo.height * fig_h / p_h))), Image.LANCZOS)
        rup, _ = on_grey(ref, up)
        rf = judge.faces(rup)
        if rf:
            pa_ = judge.align(rup, rf[0][2]); pgray = cv2.cvtColor(pa_, cv2.COLOR_RGB2GRAY); p_sharp = lapvar(pgray)
        n = found = 0; sims, sharps = [], []
        best = None
        for f in files:
            im = Image.open(f)
            rgb, bb = on_grey(im, up)
            n += 1
            fs = judge.faces(rgb)
            hit = bool(fs) or judge.haar(rgb)
            found += hit
            if fs:
                al = judge.align(rgb, fs[0][2])
                if al is not None:
                    g = cv2.cvtColor(al, cv2.COLOR_RGB2GRAY)
                    sims.append(ssim(g, pgray)); sharps.append(lapvar(g) / max(1e-6, p_sharp))
                    if best is None and "idle_00" in f:
                        best = al
        irgb, ibb = on_grey(idle, 1)
        rrgb, _ = on_grey(ref, 1)
        ifs = judge.faces(np.asarray(Image.fromarray(irgb).resize((irgb.shape[1] * up, irgb.shape[0] * up), Image.LANCZOS)))
        idle_rgba = idle.convert("RGBA")
        head_sil = head_ratio(judge, idle_rgba)
        de_top = dE(lab_median(idle_rgba, 0.25, 0.45), lab_median(ref, 0.25, 0.45))
        de_leg = dE(lab_median(idle_rgba, 0.62, 0.85), lab_median(ref, 0.62, 0.85))
        res[label] = dict(head_silhouette=head_sil, dE_top=de_top, dE_legs=de_leg,
                          frames=n, face_found=found / max(1, n), identity_ssim=float(np.mean(sims)) if sims else None,
                          sharpness=float(np.median(sharps)) if sharps else None,
                          brisque=judge.brisque(irgb), brisque_photo_same_size=judge.brisque(rrgb),
                          face_box_frac=(float(ifs[0][1][3]) / up / fig_h) if ifs else None)
        faces_strip.append(best if best is not None else np.full((112, 112, 3), 60, np.uint8))
    return res, faces_strip


def write(res, faces, labels, out):
    os.makedirs(out, exist_ok=True)
    json.dump(res, open(os.path.join(out, "quality.json"), "w"), indent=1)
    p = res["photo"]["proportions"]; pfb = res["photo"]["face_box_frac"]
    L = ["# Quality report", "",
         "Photo proportions vs Drillis & Contini adult constants: head %.3f (norm %.3f), hip height %.3f (norm %.3f), knee %.3f (norm %.3f)" % (
             p["head"], DC["head"], p["hip"], DC["hip"], p["knee"], DC["knee"]), "",
         "| build | frames | face found | identity (aligned SSIM) | face sharpness vs photo | BRISQUE idle (photo same size) | head / height (YuNet chin) | colour dE top / legs |",
         "|---|---|---|---|---|---|---|---|"]
    for lab in labels:
        r = res[lab]
        f = lambda v, fmt: (fmt % v) if v is not None else "-"
        L.append("| %s | %d | %.0f%% | %s | %s | %s (%s) | %s | %s / %s |" % (
            lab, r["frames"], 100 * r["face_found"], f(r["identity_ssim"], "%.2f"), f(r["sharpness"] and 100 * r["sharpness"], "%.0f%%"),
            f(r["brisque"], "%.1f"), f(r["brisque_photo_same_size"], "%.1f"), f(r["head_silhouette"], "%.3f"),
            f(r["dE_top"], "%.1f"), f(r["dE_legs"], "%.1f")))
    open(os.path.join(out, "QUALITY.md"), "w").write("\n".join(L) + "\n")
    W = Image.new("RGB", (120 * len(faces), 140), (30, 32, 40)); d = ImageDraw.Draw(W)
    for i, (fc, lab) in enumerate(zip(faces, ["photo"] + labels)):
        W.paste(Image.fromarray(fc), (120 * i + 4, 4)); d.text((120 * i + 4, 120), lab[:18], fill=(230, 230, 230))
    W.save(os.path.join(out, "faces.png"))
    print("\n".join(L))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--photo", required=True); ap.add_argument("--landmarks", required=True)
    ap.add_argument("--build", action="append", default=[], help="LABEL=DIR (a build output folder with moves/)")
    ap.add_argument("--models", default=os.path.join(HERE, "tools", "models")); ap.add_argument("--out", default="quality")
    a = ap.parse_args(argv)
    d = json.load(open(a.landmarks)); lms = d["landmarks"] if isinstance(d, dict) else d
    builds = [tuple(b.split("=", 1)) for b in a.build]
    judge = Judge(a.models)
    res, faces = evaluate(judge, Image.open(a.photo).convert("RGBA"), lms, builds)
    write(res, faces, [b[0] for b in builds], a.out)


if __name__ == "__main__":
    main()

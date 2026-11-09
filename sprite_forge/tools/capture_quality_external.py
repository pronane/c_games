#!/usr/bin/env python3
"""How real is a `forge.py capture` character? Judged by independent, published image models (v11.1, optional).

    python tools/capture_quality_external.py CAPTURES_DIR [--people a,b] [--variants out,out_nolayers] [--out DIR]

For every held-out frame (frames the texture never used; capture writes OUT/heldout/NNNN_real.jpg + _render.jpg)
the real frame and the character rendered from the same camera are cut to the person (each by its own mask, on
one neutral grey) and compared with:
  LPIPS     (Zhang et al. 2018, AlexNet)        perceptual distance, 0 = identical, lower is better
  DISTS     (Ding et al. 2020)                  structure + texture distance, lower is better
  DINOv2    (Oquab et al. 2023, ViT-S/14)        cosine similarity of self-supervised image features, higher better
  SFace     (Zhong et al. 2021, OpenCV zoo)      face identity cosine (faces found by YuNet in both); OpenCV's
                                                 "same person" threshold is 0.363
  IoU / dE                                      silhouette overlap and CIE colour difference (Sprite Forge's own)
Reference row "neighbour real frame": the held-out frame against the nearest OTHER real frame of the same video
(a few degrees round the orbit) - what a near-perfect render could hope to score on these metrics.

Needs torch + lpips + DISTS_pytorch (pip) and, in --models (default tools_ext/models), dinov2_vits14_pretrain.pth,
face_detection_yunet_2023mar.onnx, face_recognition_sface_2021dec.onnx. Writes OUT/EXTERNAL.md + external.json."""
from __future__ import annotations
import argparse
import glob
import json
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GREY = np.array([128, 128, 128], np.uint8)


def crop_pair(real, rmask, ren, mmask, size=256):
    """both on grey, cut to the union box, padded square, resized"""
    a = np.where(rmask[..., None], real, GREY); b = np.where(mmask[..., None], ren, GREY)
    u = rmask | mmask
    ys, xs = np.nonzero(u)
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    h, w = y1 - y0, x1 - x0
    s = max(h, w) + 8
    cy, cx = (y0 + y1) // 2, (x0 + x1) // 2
    def cut(img):
        out = np.full((s, s, 3), 128, np.uint8)
        ya, xa = cy - s // 2, cx - s // 2
        sy0, sx0 = max(0, ya), max(0, xa); sy1, sx1 = min(img.shape[0], ya + s), min(img.shape[1], xa + s)
        out[sy0 - ya:sy1 - ya, sx0 - xa:sx1 - xa] = img[sy0:sy1, sx0:sx1]
        return np.asarray(Image.fromarray(out).resize((size, size), Image.LANCZOS))
    return cut(a), cut(b)


class Judges:
    def __init__(self, models):
        import torch
        import lpips
        from DISTS_pytorch import DISTS
        import cv2
        torch.set_num_threads(2)
        self.t = torch
        self.lp = lpips.LPIPS(net="alex", verbose=False).eval()
        self.dists = DISTS().eval()
        repo = os.path.join(models, "..", "dinov2_repo")                   # git clone facebookresearch/dinov2
        self.dino = (torch.hub.load(repo, "dinov2_vits14", source="local", pretrained=False) if os.path.isdir(repo)
                     else torch.hub.load("facebookresearch/dinov2", "dinov2_vits14", pretrained=False))
        self.dino.load_state_dict(torch.load(os.path.join(models, "dinov2_vits14_pretrain.pth"), map_location="cpu"))
        self.dino.eval()
        self.yunet = cv2.FaceDetectorYN.create(os.path.join(models, "face_detection_yunet_2023mar.onnx"), "", (320, 320), 0.6)
        self.sface = cv2.FaceRecognizerSF.create(os.path.join(models, "face_recognition_sface_2021dec.onnx"), "")
        self.cv2 = cv2

    def _t(self, a, norm="lpips"):
        x = self.t.from_numpy(a.astype(np.float32) / 255.0).permute(2, 0, 1)[None]
        if norm == "lpips":
            return x * 2 - 1
        if norm == "imagenet":
            m = self.t.tensor([0.485, 0.456, 0.406])[:, None, None]; s = self.t.tensor([0.229, 0.224, 0.225])[:, None, None]
            return (x - m) / s
        return x

    def image(self, a, b):
        with self.t.no_grad():
            lp = float(self.lp(self._t(a), self._t(b)))
            di = float(self.dists(self._t(a, "01"), self._t(b, "01"), batch_average=True))
            fa = self.dino(self.t.nn.functional.interpolate(self._t(a, "imagenet"), size=224, mode="bilinear"))
            fb = self.dino(self.t.nn.functional.interpolate(self._t(b, "imagenet"), size=224, mode="bilinear"))
            dn = float(self.t.nn.functional.cosine_similarity(fa, fb))
        return dict(lpips=lp, dists=di, dino=dn)

    def face(self, img_a, img_b):
        """SFace cosine between the largest faces in two full frames (None when either has no face)"""
        feats = []
        for img in (img_a, img_b):
            bgr = self.cv2.cvtColor(img, self.cv2.COLOR_RGB2BGR)
            self.yunet.setInputSize((bgr.shape[1], bgr.shape[0]))
            _, faces = self.yunet.detect(bgr)
            if faces is None or len(faces) == 0:
                return None
            f = faces[np.argmax(faces[:, 2] * faces[:, 3])]
            al = self.sface.alignCrop(bgr, f)
            feats.append(self.sface.feature(al))
        return float(self.sface.match(feats[0], feats[1], self.cv2.FaceRecognizerSF_FR_COSINE))


def load_pairs(d):
    out = []
    for p in sorted(glob.glob(os.path.join(d, "*_real.jpg"))):
        k = os.path.basename(p)[:4]
        real = np.asarray(Image.open(p).convert("RGB")); ren = np.asarray(Image.open(os.path.join(d, k + "_render.jpg")).convert("RGB"))
        rm = np.asarray(Image.open(os.path.join(d, k + "_mask.png"))) > 127
        mm = np.asarray(Image.open(os.path.join(d, k + "_rmask.png"))) > 127
        out.append((int(k), real, rm, ren, mm))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("captures"); ap.add_argument("--people"); ap.add_argument("--variants", default="out")
    ap.add_argument("--models", default=os.path.join(os.path.dirname(HERE), "..", "tools_ext", "models"))
    ap.add_argument("--out", default="capture_external")
    a = ap.parse_args(argv)
    J = Judges(a.models)
    people = a.people.split(",") if a.people else sorted(os.listdir(a.captures))
    res = {}
    for n in people:
        for v in a.variants.split(","):
            hd = os.path.join(a.captures, n, v, "heldout")
            if not os.path.isdir(hd):
                continue
            pairs = load_pairs(hd)
            rows = []
            for k, real, rm, ren, mm in pairs:
                A, B = crop_pair(real, rm, ren, mm)
                m = J.image(A, B)
                m["face"] = J.face(np.where(rm[..., None], real, GREY), np.where(mm[..., None], ren, GREY))
                m["iou"] = float((rm & mm).sum() / max(1, (rm | mm).sum()))
                rows.append(m)
            res.setdefault(n, {})[v] = rows
            # reference: each held-out real frame vs the nearest other real frame of the video
            if v == a.variants.split(",")[0]:
                frames = sorted(glob.glob(os.path.join(a.captures, n, "frames", "*.jpg")))
                ref = []
                for k, real, rm, ren, mm in pairs:
                    cand = [f for f in frames if abs(int(os.path.basename(f)[:4]) - k) in (1, 2)]
                    if not cand:
                        continue
                    f2 = cand[0]; k2 = os.path.basename(f2)[:4]
                    real2 = np.asarray(Image.open(f2).convert("RGB"))
                    m2 = np.asarray(Image.open(os.path.join(a.captures, n, "masks", k2 + ".png"))) > 127
                    A, B = crop_pair(real, rm, real2, m2)
                    m = J.image(A, B)
                    m["face"] = J.face(np.where(rm[..., None], real, GREY), np.where(m2[..., None], real2, GREY))
                    m["iou"] = float((rm & m2).sum() / max(1, (rm | m2).sum()))
                    ref.append(m)
                res[n]["neighbour real frame"] = ref
            print(n, v, "done", len(rows))
    def agg(rows, k):
        v = [r[k] for r in rows if r.get(k) is not None]
        return (float(np.mean(v)), len(v)) if v else (None, 0)
    os.makedirs(a.out, exist_ok=True)
    json.dump(res, open(os.path.join(a.out, "external.json"), "w"), indent=1)
    L = ["# Capture quality judged by external models", "",
         "Held-out frames (never used for the texture): real frame vs the character rendered from the same camera.", "",
         "| person | version | LPIPS (lower) | DISTS (lower) | DINOv2 sim (higher) | face identity (SFace, >0.363 = same person) | silhouette IoU |",
         "|---|---|---|---|---|---|---|"]
    for n, vs in res.items():
        for v, rows in vs.items():
            f = lambda k, fmt="%.3f": (fmt % agg(rows, k)[0]) if agg(rows, k)[0] is not None else "-"
            fc = agg(rows, "face")
            L.append("| %s | %s | %s | %s | %s | %s | %s |" % (n, v, f("lpips"), f("dists"), f("dino"),
                                                               ("%.3f (%d faces)" % fc) if fc[0] is not None else "-", f("iou")))
    L += ["", "Means over people:", ""]
    vnames = sorted({v for vs in res.values() for v in vs})
    for v in vnames:
        rows = [r for vs in res.values() for r in vs.get(v, [])]
        L.append("- %s: LPIPS %.3f, DISTS %.3f, DINOv2 %.3f, face %s, IoU %.3f" % (
            v, agg(rows, "lpips")[0], agg(rows, "dists")[0], agg(rows, "dino")[0],
            ("%.3f" % agg(rows, "face")[0]) if agg(rows, "face")[0] is not None else "-", agg(rows, "iou")[0]))
    open(os.path.join(a.out, "EXTERNAL.md"), "w").write("\n".join(L) + "\n")
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    sys.exit(main())

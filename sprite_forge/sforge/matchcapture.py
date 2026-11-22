"""v11.23 match capture: football (or any field-sport) video -> motion-library moves.

    python -m sforge.matchcapture CLIP.mp4 [CLIP2.mp4 ...] --out DIR [--models DIR]
           [--detector yolox|rtmdet] [--fps 15] [--min-height 90] [--purge]

`forge.py mocap` captures one person filling the frame.  Match footage (a Veo or
other wide camera) has twenty-odd small players, so this:

  1  detects people in every frame - the whole frame plus two overlapping halves, so
     60-120 px players are found - with an ONNX person detector (onnxruntime; GPU if
     onnxruntime-gpu is installed);
  2  links detections into tracks (IoU + motion);
  3  runs MediaPipe Pose (3D world landmarks) on each track's crop, frame by frame;
  4  finds the moments worth keeping: strikes (shots, passes, clearances - the swing
     foot's speed peak relative to the hips) and steady running (two-stride loops);
  5  fits each moment onto the shared skeleton with sforge.jointtrack (the mocap IK)
     and writes library moves with their licence record.

Privacy: frames and crops are only held in memory; nothing visual is written.  Output
is joint angles only, under anonymous ids (no names, numbers or faces).  --purge
deletes the input videos and the per-track landmark cache when the run ends.

Models and their licences are listed in sforge/models/registry.json and recorded in
every move's import block.  This is the batch job tools/runpod_matchcapture.sh runs on
a GPU pod.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
import zlib

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REGISTRY = os.path.join(HERE, "models", "registry.json")

DETECTORS = {
    # name: (registry id, input size, mean, std)
    "yolox": ("yolox_m_humanart", 640, (0.0, 0.0, 0.0), (1.0, 1.0, 1.0)),
    "rtmdet": ("rtmdet_nano_person", 320, (103.53, 116.28, 123.675), (57.375, 57.12, 58.395)),
}


def registry():
    with open(REGISTRY) as f:
        return json.load(f)


def model_path(models_dir, rid):
    entry = registry()["models"][rid]
    return os.path.join(models_dir, entry["file"]), entry


# ------------------------------------------------------------------ detection

def _ort():
    """onnxruntime, with the pip CUDA / cuDNN libraries (from torch or nvidia-* wheels) loaded first,
    so the GPU build finds them without LD_LIBRARY_PATH."""
    import onnxruntime as ort
    if hasattr(ort, "preload_dlls") and "CUDAExecutionProvider" in ort.get_available_providers():
        try: ort.preload_dlls()
        except Exception: pass
    return ort

class Detector:
    def __init__(self, models_dir, kind="yolox", conf=.35):
        ort = _ort()
        rid, self.size, mean, std = DETECTORS[kind]
        path, self.entry = model_path(models_dir, rid)
        prov = [p for p in ("CUDAExecutionProvider", "CPUExecutionProvider") if p in ort.get_available_providers()]
        self.sess = ort.InferenceSession(path, providers=prov)
        self.inp = self.sess.get_inputs()[0].name
        self.mean = np.array(mean, np.float32).reshape(3, 1, 1)
        self.std = np.array(std, np.float32).reshape(3, 1, 1)
        self.conf = conf
        self.kind = kind

    def _run(self, img):
        import cv2
        h, w = img.shape[:2]
        r = min(self.size / h, self.size / w)
        nh, nw = int(round(h * r)), int(round(w * r))
        canvas = np.full((self.size, self.size, 3), 114, np.uint8)
        canvas[:nh, :nw] = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_LINEAR)
        x = (canvas.transpose(2, 0, 1).astype(np.float32) - self.mean) / self.std
        dets, labels = self.sess.run(None, {self.inp: x[None]})
        out = []
        for d, lab in zip(dets[0], labels[0]):
            if d[4] < self.conf or int(lab) != 0:
                continue
            out.append((d[0] / r, d[1] / r, d[2] / r, d[3] / r, float(d[4])))
        return out

    def detect(self, frame):
        """whole frame + left/right overlapping squares (small players)."""
        h, w = frame.shape[:2]
        boxes = self._run(frame)
        if w > h * 1.2:
            side = min(h, int(w * .55))
            for x0 in (0, w - side):
                for b in self._run(frame[:, x0:x0 + side]):
                    boxes.append((b[0] + x0, b[1], b[2] + x0, b[3], b[4]))
        return nms(boxes, .5)


def iou(a, b):
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0])); iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    u = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / u if u > 0 else 0.0


def nms(boxes, thr):
    boxes = sorted(boxes, key=lambda b: -b[4])
    keep = []
    for b in boxes:
        if all(iou(b, k) < thr for k in keep):
            keep.append(b)
    return keep


# ------------------------------------------------------------------ tracking
class Tracker:
    """SORT-lite: greedy IoU matching on constant-velocity predictions."""

    def __init__(self, max_miss=8, min_iou=.25):
        self.tracks, self.done, self.next_id = [], [], 0
        self.max_miss, self.min_iou = max_miss, min_iou

    def update(self, fi, boxes):
        preds = []
        for t in self.tracks:
            b = t["box"]; v = t["vel"]
            preds.append((b[0] + v[0], b[1] + v[1], b[2] + v[0], b[3] + v[1]))
        pairs = sorted(((iou(p, d), ti, di) for ti, p in enumerate(preds) for di, d in enumerate(boxes)), reverse=True)
        used_t, used_d = set(), set()
        for s, ti, di in pairs:
            if s < self.min_iou or ti in used_t or di in used_d:
                continue
            used_t.add(ti); used_d.add(di)
            t = self.tracks[ti]; d = boxes[di]
            cx0, cy0 = (t["box"][0] + t["box"][2]) / 2, (t["box"][1] + t["box"][3]) / 2
            cx1, cy1 = (d[0] + d[2]) / 2, (d[1] + d[3]) / 2
            t["vel"] = (.6 * t["vel"][0] + .4 * (cx1 - cx0), .6 * t["vel"][1] + .4 * (cy1 - cy0))
            t["box"] = d[:4]; t["miss"] = 0
            t["frames"][fi] = d[:4]
        for ti, t in enumerate(self.tracks):
            if ti not in used_t:
                t["miss"] += 1
        for di, d in enumerate(boxes):
            if di not in used_d:
                self.tracks.append(dict(id=self.next_id, box=d[:4], vel=(0.0, 0.0), miss=0, frames={fi: d[:4]}))
                self.next_id += 1
        alive = []
        for t in self.tracks:
            (self.done if t["miss"] > self.max_miss else alive).append(t)
        self.tracks = alive

    def finish(self):
        self.done.extend(self.tracks); self.tracks = []
        return self.done


# ------------------------------------------------------------------ pose (2D, then lifted to 3D)
HALPE_N = 26


class Pose2D:
    """RTMPose (Halpe-26 body + feet) on given boxes: top-down, so small players work
    (MediaPipe's own person finder sees nothing on 60-120 px Veo players)."""

    def __init__(self, models_dir, rid="rtmpose_l_halpe26"):
        ort = _ort()
        path, self.entry = model_path(models_dir, rid)
        prov = [p for p in ("CUDAExecutionProvider", "CPUExecutionProvider") if p in ort.get_available_providers()]
        self.sess = ort.InferenceSession(path, providers=prov)
        shp = self.sess.get_inputs()[0].shape            # [1, 3, H, W]
        self.H, self.W = int(shp[2]), int(shp[3])
        self.inp = self.sess.get_inputs()[0].name
        self.mean = np.array([123.675, 116.28, 103.53], np.float32)
        self.std = np.array([58.395, 57.12, 57.375], np.float32)

    def __call__(self, frame, box):
        """(26, 3): x, y in frame pixels and a 0-1 score."""
        import cv2
        W, H = self.W, self.H
        cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
        w, h = (box[2] - box[0]) * 1.25, (box[3] - box[1]) * 1.25
        if w / h > W / H: h = w * H / W
        else: w = h * W / H
        src = np.float32([[cx - w / 2, cy - h / 2], [cx + w / 2, cy - h / 2], [cx - w / 2, cy + h / 2]])
        dst = np.float32([[0, 0], [W, 0], [0, H]])
        A = cv2.getAffineTransform(src, dst)
        crop = cv2.warpAffine(frame, A, (W, H), flags=cv2.INTER_LINEAR)
        x = (cv2.cvtColor(crop, cv2.COLOR_BGR2RGB).astype(np.float32) - self.mean) / self.std
        sx, sy = self.sess.run(None, {self.inp: x.transpose(2, 0, 1)[None].astype(np.float32)})
        kx = sx[0].argmax(1) / 2.0; ky = sy[0].argmax(1) / 2.0
        sc = np.minimum(sx[0].max(1), sy[0].max(1))
        # back to frame pixels
        out = np.zeros((HALPE_N, 3))
        out[:, 0] = cx - w / 2 + kx * w / W
        out[:, 1] = cy - h / 2 + ky * h / H
        out[:, 2] = np.clip(sc, 0, 1)
        return out


class Lifter:
    """Sprite Forge's own 2D -> 3D lifter (tools/train_lifter.py; trained on real match
    3D pose from SkillCorner open data, MIT)."""

    def __init__(self, models_dir, rid="lifter_v1"):
        ort = _ort()
        path, self.entry = model_path(models_dir, rid)
        meta = json.load(open(os.path.splitext(path)[0] + ".json"))
        self.idx = meta["halpe_index"]; self.win = meta["window"]; self.J = len(self.idx)
        self.sess = ort.InferenceSession(path, providers=["CPUExecutionProvider"])

    def __call__(self, K, min_score=.3):
        """K (T, 26, 3) image keypoints -> (T, 19, 3) hips-centred 3D, camera axes (Y up)."""
        T = len(K); c = self.win // 2
        X = K[:, self.idx, :2].copy(); X[..., 1] *= -1.0      # image y down -> up
        S = K[:, self.idx, 2]
        pad = lambda a: np.concatenate([a[:1].repeat(c, 0), a, a[-1:].repeat(c, 0)], 0)
        Xp, Sp = pad(X), pad(S)
        batch = np.zeros((T, self.win * self.J * 3), np.float32)
        for t in range(T):
            w = Xp[t:t + self.win].copy(); m = (Sp[t:t + self.win] > min_score).astype(np.float32)
            hip = .5 * (w[c, 9] + w[c, 10]); sh = .5 * (w[c, 3] + w[c, 4])
            s = max(float(np.linalg.norm(sh - hip)), 1e-3)
            w = (w - hip) / s * m[..., None]
            w[..., 1] *= -1.0                                  # training used image y (down)
            batch[t] = np.concatenate([w, m[..., None]], -1).reshape(-1)
        Y = self.sess.run(None, {"x": batch})[0].reshape(T, self.J, 3)
        return Y


# lifter joint -> MediaPipe landmark slot (what sforge.jointtrack reads)
LIFT_SLOTS = [0, 7, 8, 11, 12, 13, 14, 15, 16, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32]


# ------------------------------------------------------------------ moments
# Halpe-26 indices used below
H_LHIP, H_RHIP, H_LSH, H_RSH, H_LKNEE, H_RKNEE, H_LANK, H_RANK = 11, 12, 5, 6, 13, 14, 15, 16
LEG_H = (11, 12, 13, 14, 15, 16)


def _smooth(a, k=3):
    if len(a) < k: return a
    ker = np.ones(k) / k
    return np.stack([np.convolve(a[:, d], ker, mode="same") for d in range(a.shape[1])], 1)


def strikes_2d(K, fps, min_speed=7.0, min_score=.45):
    """Kicks from the 2D skeleton: the swing ankle's speed relative to the hips, in torso
    lengths per second, peaking while the knee straightens (a run's ankle swing is
    slower and keeps the knee bent).  -> [(frame, foot, speed)]"""
    hip = .5 * (K[:, H_LHIP, :2] + K[:, H_RHIP, :2]); sh = .5 * (K[:, H_LSH, :2] + K[:, H_RSH, :2])
    torso = np.median(np.linalg.norm(sh - hip, axis=1))
    if torso < 8: return []
    out = []
    for side, (kn, an, hp) in (("L", (H_LKNEE, H_LANK, H_LHIP)), ("R", (H_RKNEE, H_RANK, H_RHIP))):
        rel = _smooth(K[:, an, :2] - hip) / torso
        sp = np.r_[0.0, np.linalg.norm(np.diff(rel, axis=0), axis=1) * fps]
        # knee angle (deg) in 2D
        a = K[:, hp, :2] - K[:, kn, :2]; b = K[:, an, :2] - K[:, kn, :2]
        cos = (a * b).sum(1) / np.maximum(np.linalg.norm(a, axis=1) * np.linalg.norm(b, axis=1), 1e-6)
        knee = np.degrees(np.arccos(np.clip(cos, -1, 1)))
        sc = K[:, list(LEG_H), 2].mean(1)
        r = max(1, int(.25 * fps))
        for i in range(r, len(sp) - r):
            if sp[i] < min_speed or sc[i] < min_score: continue
            if sp[i] < sp[i - r:i + r + 1].max(): continue
            # the knee opens through contact: bent before, near-straight at the peak
            if knee[max(0, i - r):i].min() > 130 or knee[i:i + 2].max() < 145: continue
            out.append((i, side, float(sp[i])))
    out.sort()
    keep = []
    for m in out:
        if not keep or m[0] - keep[-1][0] > .6 * fps: keep.append(m)
        elif m[2] > keep[-1][2]: keep[-1] = m
    return keep


# ------------------------------------------------------------------ main
def process(video, out_dir, models_dir, detector="yolox", fps=15.0, min_height=80, log=print, max_frames=None,
            pose_model="rtmpose_l_halpe26", start_s=0.0):
    import cv2
    from . import jointtrack as JT
    t0 = time.time()
    det = Detector(models_dir, detector)
    pose = Pose2D(models_dir, pose_model)
    lifter = Lifter(models_dir)
    cap = cv2.VideoCapture(video)
    src_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    if start_s > 0: cap.set(cv2.CAP_PROP_POS_MSEC, start_s * 1000.0)
    step = max(1, int(round(src_fps / fps)))
    fps_eff = src_fps / step
    frames, tracker, fi, raw = [], Tracker(), 0, 0
    while True:
        ok, fr = cap.read()
        if not ok: break
        if raw % step == 0:
            frames.append(fr)
            tracker.update(fi, det.detect(fr))
            fi += 1
            if max_frames and fi >= max_frames: break
        raw += 1
    cap.release()
    tracks = [t for t in tracker.finish()
              if len(t["frames"]) >= 1.5 * fps_eff
              and np.median([b[3] - b[1] for b in t["frames"].values()]) >= min_height]
    t_det = time.time() - t0
    clip_id = "%08x" % (zlib.crc32(os.path.basename(video).encode()) & 0xffffffff)   # stable across runs
    takes, stats = [], dict(tracks=len(tracks), strikes=0, runs=0, rejected=0)
    for t in tracks:
        idx = sorted(t["frames"])
        # contiguous frames only (gaps filled with the last box)
        K = np.zeros((idx[-1] - idx[0] + 1, HALPE_N, 3)); last = None
        for f in range(idx[0], idx[-1] + 1):
            box = t["frames"].get(f, last); last = box
            K[f - idx[0]] = pose(frames[f], box)
        Y = lifter(K)                                    # (T, 19, 3)
        P = np.full((len(Y), 33, 3), np.nan)
        P[:, LIFT_SLOTS] = Y
        legs = K[:, list(LEG_H), 2].mean(1)
        for fr_i, foot, speed in strikes_2d(K, fps_eff):
            lo, hi = fr_i - int(.8 * fps_eff), fr_i + int(.5 * fps_eff)
            if lo < 0 or hi >= len(P) or legs[lo:hi + 1].mean() < .5:
                stats["rejected"] += 1; continue
            try:
                keys, rep = JT.fit_landmarks(P[lo:hi + 1], fps=fps_eff, face_frame=fr_i - lo)
            except ValueError:
                stats["rejected"] += 1; continue
            if rep["mean_bone_err_deg"] > 6.0:
                stats["rejected"] += 1; continue
            stats["strikes"] += 1
            takes.append(dict(kind="strike", keys=keys, rep=rep, contact=round((fr_i - lo) / max(1, hi - lo), 4),
                              foot=foot, peak_speed=round(speed, 2), vis=round(float(legs[lo:hi + 1].mean()), 3)))
        # steady running: a two-stride loop where the player is clearly running
        hts = np.array([t["frames"].get(f, t["frames"][idx[0]])[3] - t["frames"].get(f, t["frames"][idx[0]])[1]
                        for f in range(idx[0], idx[-1] + 1)], float)
        cx = K[:, [H_LHIP, H_RHIP], 0].mean(1)
        spd = np.abs(np.diff(cx)) * fps_eff / np.maximum(hts[1:], 1)
        if len(P) >= 2 * fps_eff and legs.mean() > .55 and np.median(spd) > 1.2:
            try:
                keys, rep = JT.fit_landmarks(P, fps=fps_eff)
                lk = best_loop_keys(keys, int(.5 * fps_eff), int(1.2 * fps_eff))
                if lk is not None and rep["mean_bone_err_deg"] < 6.0:
                    k2, L = lk
                    stats["runs"] += 1
                    takes.append(dict(kind="run", keys=k2, rep=dict(rep, duration=round(L / fps_eff, 4)), loop=True,
                                      vis=round(float(legs.mean()), 3)))
            except ValueError:
                pass
    frames.clear()
    log("  %s: %d frames @ %.1f fps, %d tracks, %d strikes, %d run loops, %d rejected (%.0fs detect, %.0fs total)" % (
        os.path.basename(video), fi, fps_eff, stats["tracks"], stats["strikes"], stats["runs"], stats["rejected"],
        t_det, time.time() - t0))
    return clip_id, takes


def best_loop_keys(keys, lo, hi, max_seam=7.0):
    from . import mocap as MC
    X = np.array([[np.ravel(p.get(k, 0.0)).tolist()[c] if isinstance(p.get(k, 0.0), (list, tuple)) else float(p.get(k, 0.0))
                   for k, c in MC.PARAMS] for _, p in keys])
    best = (1e9, 0, 0)
    for L in range(lo, min(hi, len(X) - 2) + 1):
        for s in range(0, len(X) - L - 1):
            e = float(np.abs(X[s] - X[s + L]).mean() + .5 * np.abs((X[s + 1] - X[s]) - (X[s + L + 1] - X[s + L])).mean())
            if e < best[0]:
                best = (e, s, L)
    e, s, L = best
    if e > max_seam or L == 0:
        return None
    return [((i - s) / L, keys[i][1]) for i in range(s, s + L + 1)], L


def licence_record(models_used, footage_licence):
    reg = registry()["models"]
    return dict(
        spdx=footage_licence.get("spdx", "LicenseRef-owner-footage"),
        custom_text=footage_licence.get("text", ""),
        author=footage_licence.get("author", ""),
        source_url=footage_licence.get("url", ""),
        redistribution=footage_licence.get("redistribution", "yes"),
        attribution=footage_licence.get("attribution", ""),
        notes="Anonymous joint motion from match video (no images kept). Models: " +
              "; ".join("%s (%s)" % (reg[m]["name"], reg[m]["licence"]) for m in models_used),
    )


def merge(clip_dirs, out, prefix="mc"):
    """Merge per-clip library folders (parallel runs) into one, numbering moves by kind."""
    os.makedirs(out, exist_ok=True)
    index, n_by = dict(source="sforge.matchcapture", takes=[]), {}
    for d in sorted(clip_dirs):
        ip = os.path.join(d, "_import.json")
        if not os.path.isfile(ip): continue
        for t in json.load(open(ip))["takes"]:
            n_by[t["kind"]] = n_by.get(t["kind"], 0) + 1
            name = "%s_%s_%03d" % (prefix, t["kind"], n_by[t["kind"]])
            rec = json.load(open(os.path.join(d, t["name"] + ".json")))
            rec["name"] = name
            with open(os.path.join(out, name + ".json"), "w") as f:
                json.dump(rec, f, indent=0)
            index["takes"].append(dict(t, name=name))
    with open(os.path.join(out, "_import.json"), "w") as f:
        json.dump(index, f, indent=1)
    return index


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == "--merge":
        ap = argparse.ArgumentParser(); ap.add_argument("--merge", required=True); ap.add_argument("--out", required=True)
        a = ap.parse_args(argv)
        idx = merge([os.path.join(a.merge, d) for d in os.listdir(a.merge)], a.out)
        print("merged %d moves into %s" % (len(idx["takes"]), a.out)); return 0
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("videos", nargs="+")
    ap.add_argument("--out", required=True, help="library folder for the moves")
    ap.add_argument("--models", default=os.path.join(HERE, "models"))
    ap.add_argument("--detector", default="yolox", choices=sorted(DETECTORS))
    ap.add_argument("--fps", type=float, default=15.0)
    ap.add_argument("--min-height", type=int, default=80)
    ap.add_argument("--pose", default="rtmpose_l_halpe26", choices=["rtmpose_l_halpe26", "rtmpose_m_halpe26"])
    ap.add_argument("--prefix", default="mc")
    ap.add_argument("--footage-licence", default="", help="JSON file: spdx/author/url/attribution/text of the footage")
    ap.add_argument("--max-frames", type=int, default=0)
    ap.add_argument("--start", type=float, default=0.0, help="seconds into each video to start")
    ap.add_argument("--purge", action="store_true", help="delete the input videos afterwards")
    args = ap.parse_args(argv)
    from . import jointtrack as JT
    os.makedirs(args.out, exist_ok=True)
    foot = json.load(open(args.footage_licence)) if args.footage_licence else {}
    lic = licence_record([DETECTORS[args.detector][0], args.pose, "lifter_v1"], foot)
    index_path = os.path.join(args.out, "_import.json")
    index = json.load(open(index_path)) if os.path.isfile(index_path) else dict(source="sforge.matchcapture", takes=[])
    n_by = {}
    for t in index["takes"]:
        n_by[t["kind"]] = max(n_by.get(t["kind"], 0), int(t["name"].rsplit("_", 1)[-1]))
    for v in args.videos:
        clip_id, takes = process(v, args.out, args.models, args.detector, args.fps, args.min_height,
                                 max_frames=args.max_frames or None, pose_model=args.pose, start_s=args.start)
        for tk in takes:
            n_by[tk["kind"]] = n_by.get(tk["kind"], 0) + 1
            name = "%s_%s_%03d" % (args.prefix, tk["kind"], n_by[tk["kind"]])
            rec = JT.keys_record(name, tk["keys"], tk["rep"], lic, category="Kick" if tk["kind"] == "strike" else "Locomotion",
                                 loop=tk.get("loop", False), source="matchcapture:%s" % clip_id,
                                 desc="%s from match video (anonymous)" % tk["kind"])
            rec["import"].update(reader="matchcapture", contact=tk.get("contact", -1.0), foot=tk.get("foot", ""),
                                 leg_visibility=tk["vis"], peak_speed=tk.get("peak_speed"))
            with open(os.path.join(args.out, name + ".json"), "w") as f:
                json.dump(rec, f, indent=0)
            index["takes"].append(dict(name=name, kind=tk["kind"], clip=clip_id, loop=tk.get("loop", False),
                                       duration=tk["rep"]["duration"], contact=tk.get("contact", -1.0), foot=tk.get("foot", ""),
                                       fit_err_deg=tk["rep"]["mean_bone_err_deg"], leg_visibility=tk["vis"]))
        with open(index_path, "w") as f:
            json.dump(index, f, indent=1)
        if args.purge:
            os.remove(v)
    print("matchcapture: %d moves in %s" % (len(index["takes"]), args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())

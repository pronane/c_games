"""forge.py capture, step 1 - track a turnaround video (v11).

A turnaround clip: the person stands still (arms by the sides, then optionally a T-pose at the end) while the camera
walks round them once. For every sampled frame this writes
  frames/NNNN.jpg        the frame
  masks/NNNN.png         person mask (MediaPipe pose segmentation, 0-255)
  parts/NNNN.png         MediaPipe multiclass labels: 0 background, 1 hair, 2 body skin, 3 face skin, 4 clothes, 5 other
  track.json             per frame: 33 image landmarks (px, visibility), 33 world landmarks (m, hips at 0),
                         body yaw (deg, 0 = facing the camera, + = the person's left turned towards the camera), and
                         whether the frame is a T-pose / arms-out frame
The yaw comes from the world landmarks (shoulder + hip line) and is then made continuous over the orbit: MediaPipe
sometimes swaps front and back, an orbit does not jump 180 degrees between neighbouring frames.

Models (Apache-2.0, Google MediaPipe; downloaded once into models/ by `forge.py capture --setup`):
  pose_landmarker_heavy.task, selfie_multiclass_256x256.tflite, face_landmarker.task (v11.2: the face shape)
"""
from __future__ import annotations
import json
import math
import os

import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS = os.path.join(ROOT, "models")
GCS = "https://storage.googleapis.com/mediapipe-models/"
MODEL_URLS = {
    "pose_landmarker_heavy.task": GCS + "pose_landmarker/pose_landmarker_heavy/float16/latest/pose_landmarker_heavy.task",
    "selfie_multiclass_256x256.tflite": GCS + "image_segmenter/selfie_multiclass_256x256/float32/latest/selfie_multiclass_256x256.tflite",
    "face_landmarker.task": GCS + "face_landmarker/face_landmarker/float16/latest/face_landmarker.task",
}
# BlazePose indices
NOSE, L_SH, R_SH, L_EL, R_EL, L_WR, R_WR, L_HIP, R_HIP, L_KN, R_KN, L_AN, R_AN = 0, 11, 12, 13, 14, 15, 16, 23, 24, 25, 26, 27, 28
L_EAR, R_EAR = 7, 8


def setup(log=print):
    import urllib.request
    os.makedirs(MODELS, exist_ok=True)
    for n, u in MODEL_URLS.items():
        p = os.path.join(MODELS, n)
        if not os.path.isfile(p):
            log("download %s" % u)
            urllib.request.urlretrieve(u, p + ".part"); os.replace(p + ".part", p)
    return MODELS


def model(name):
    p = os.path.join(os.environ.get("SFS_MODELS", MODELS), name)
    if not os.path.isfile(p):
        raise FileNotFoundError("%s missing - run  forge.py capture --setup  (downloads the MediaPipe models)" % p)
    return p


def decode(video, fps=4.0, max_side=1024):
    """-> list of (time s, RGB uint8) at about `fps`, rotated as the player shows it (ffmpeg autorotate)"""
    import cv2
    cap = cv2.VideoCapture(video)
    vfps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    step = max(1, int(round(vfps / fps)))
    out, i = [], 0
    while True:
        ok, fr = cap.read()
        if not ok:
            break
        if i % step == 0:
            rgb = cv2.cvtColor(fr, cv2.COLOR_BGR2RGB)
            h, w = rgb.shape[:2]
            k = max_side / max(h, w)
            k = min(k, 1.0)
            nw, nh = int(w * k) // 4 * 4, int(h * k) // 4 * 4     # MediaPipe's masks need a 4-aligned row stride
            if (nw, nh) != (w, h):
                rgb = cv2.resize(rgb, (nw, nh), interpolation=cv2.INTER_AREA)
            out.append((i / vfps, rgb))
        i += 1
    return out


def body_yaw(world):
    """yaw of the body from world landmarks (x right, y down, z away from camera; hips at 0): 0 = facing the camera"""
    W = np.asarray(world)
    sh = W[L_SH, [0, 2]] - W[R_SH, [0, 2]]
    hp = W[L_HIP, [0, 2]] - W[R_HIP, [0, 2]]
    v = sh / (np.linalg.norm(sh) + 1e-9) + hp / (np.linalg.norm(hp) + 1e-9)
    # facing the camera: the person's left (L) is on the image right (+x), the left-right line has no depth
    return math.degrees(math.atan2(-v[1], v[0]))


def unwrap_orbit(yaws, conf):
    """make a yaw track continuous: each step may be read as itself or flipped by 180 (front / back confusion);
    dynamic programming picks the reading with the smallest total turning, weighting jumps by confidence"""
    n = len(yaws)
    if n == 0:
        return []
    cand = np.array([[y, y + 180.0] for y in yaws])
    cost = np.zeros((n, 2)); back = np.zeros((n, 2), int)
    cost[0] = [0.0, 30.0 * conf[0]]                       # prefer MediaPipe's own reading at the start
    for i in range(1, n):
        for b in range(2):
            d = [abs(((cand[i, b] - cand[i - 1, a]) + 180) % 360 - 180) for a in range(2)]
            tot = [cost[i - 1, a] + d[a] for a in range(2)]
            a = int(np.argmin(tot)); back[i, b] = a
            cost[i, b] = tot[a] + (25.0 * conf[i] if b == 1 else 0.0)
    b = int(np.argmin(cost[-1])); path = [b]
    for i in range(n - 1, 0, -1):
        b = back[i, b]; path.append(b)
    path = path[::-1]
    y = np.array([cand[i, path[i]] for i in range(n)])
    out = [y[0]]
    for i in range(1, n):
        d = ((y[i] - out[-1]) + 180) % 360 - 180
        out.append(out[-1] + d)
    return out


def face_front(lm):
    """+1 when the face is clearly towards the camera (nose between visible ears / eyes), -1 when it is clearly away
    (both ears visible but nose not), 0 unsure. Used to settle the front / back ambiguity."""
    v = lambda i: lm[i][2]
    if v(NOSE) > 0.8 and (v(2) > 0.7 or v(5) > 0.7):
        return 1
    if v(NOSE) < 0.3 and v(L_EAR) > 0.5 and v(R_EAR) > 0.5:
        return -1
    return 0


def is_tpose(lm):
    """arms out sideways: wrists at about shoulder height and far from the body"""
    sh = (np.array(lm[L_SH][:2]) + np.array(lm[R_SH][:2])) / 2
    span = abs(lm[L_SH][0] - lm[R_SH][0]) + 1e-6
    torso = abs((lm[L_HIP][1] + lm[R_HIP][1]) / 2 - sh[1]) + 1e-6
    out = 0
    for w, s in ((L_WR, L_SH), (R_WR, R_SH)):
        if abs(lm[w][1] - lm[s][1]) < 0.35 * torso and abs(lm[w][0] - lm[s][0]) > 0.9 * torso:
            out += 1
    return out == 2 and span > 0


def track(video, out_dir, fps=4.0, log=print):
    import mediapipe as mp
    from mediapipe.tasks import python as mpt
    from mediapipe.tasks.python import vision
    os.makedirs(out_dir, exist_ok=True)
    for d in ("frames", "masks", "parts"):
        os.makedirs(os.path.join(out_dir, d), exist_ok=True)
    if os.path.splitext(video)[1].lower() in (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"):
        from PIL import ImageOps                                  # one photo: a one-frame "video"
        im = ImageOps.exif_transpose(Image.open(video)).convert("RGB")
        k = min(1.0, 1600.0 / max(im.size))
        w4, h4 = int(im.width * k) // 4 * 4, int(im.height * k) // 4 * 4
        frames = [(0.0, np.asarray(im.resize((w4, h4), Image.LANCZOS)))]
    else:
        frames = decode(video, fps)
    log("capture: %d frames at %.1f fps from %s" % (len(frames), fps, os.path.basename(video)))
    po = vision.PoseLandmarkerOptions(base_options=mpt.BaseOptions(model_asset_path=model("pose_landmarker_heavy.task")),
                                      running_mode=vision.RunningMode.VIDEO, output_segmentation_masks=True,
                                      min_pose_detection_confidence=0.4, min_tracking_confidence=0.4)
    so = vision.ImageSegmenterOptions(base_options=mpt.BaseOptions(model_asset_path=model("selfie_multiclass_256x256.tflite")),
                                      output_category_mask=True)
    rec = []
    with vision.PoseLandmarker.create_from_options(po) as pose, vision.ImageSegmenter.create_from_options(so) as seg:
        for k, (t, rgb) in enumerate(frames):
            h, w = rgb.shape[:2]
            img = mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb))
            r = pose.detect_for_video(img, int(t * 1000))
            name = "%04d" % k
            Image.fromarray(rgb).save(os.path.join(out_dir, "frames", name + ".jpg"), quality=93)
            if not r.pose_landmarks:
                rec.append(dict(i=k, t=t, ok=False)); continue
            lm = [[p.x * w, p.y * h, float(p.visibility)] for p in r.pose_landmarks[0]]
            wl = [[p.x, p.y, p.z] for p in r.pose_world_landmarks[0]]
            m = r.segmentation_masks[0].numpy_view()
            m = (np.clip(np.squeeze(m), 0, 1) * 255).astype(np.uint8)
            Image.fromarray(m).save(os.path.join(out_dir, "masks", name + ".png"))
            s = seg.segment(img).category_mask.numpy_view()
            Image.fromarray(np.squeeze(s).astype(np.uint8)).save(os.path.join(out_dir, "parts", name + ".png"))
            vis = float(np.mean([lm[i][2] for i in (L_SH, R_SH, L_HIP, R_HIP)]))
            rec.append(dict(i=k, t=t, ok=True, lm=lm, world=wl, yaw_raw=body_yaw(wl), vis=vis, face=face_front(lm),
                            tpose=bool(is_tpose(lm)), size=[w, h]))
    ok = [r for r in rec if r["ok"]]
    # front / back: the face test is reliable when it fires, so it fixes the orbit's offset
    yaws = unwrap_orbit([r["yaw_raw"] for r in ok], [r["vis"] for r in ok])
    votes = [(((y + 180) % 360 - 180), r["face"]) for y, r in zip(yaws, ok) if r["face"] != 0]
    agree = sum(1 for y, f in votes if (abs(y) < 90) == (f > 0))
    if votes and agree < len(votes) / 2:                  # the whole orbit was read back-to-front
        yaws = [y + 180 for y in yaws]
    y0 = yaws[0]
    for r, y in zip(ok, yaws):
        r["yaw"] = float(((y + 180) % 360) - 180)
        r["orbit"] = float(y - y0)
    span = (max(yaws) - min(yaws)) if yaws else 0
    info = dict(video=os.path.basename(video), fps=fps, frames=rec, orbit_span_deg=float(span),
                tpose_frames=[r["i"] for r in ok if r["tpose"]], face_votes=len(votes), face_agree=agree)
    json.dump(info, open(os.path.join(out_dir, "track.json"), "w"))
    log("capture: %d/%d frames tracked, orbit %.0f deg, %d T-pose frames" % (len(ok), len(rec), span, len(info["tpose_frames"])))
    return info

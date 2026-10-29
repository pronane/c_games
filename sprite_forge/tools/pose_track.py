#!/usr/bin/env python3
"""Pose tracking helper for `forge.py mocap` (runs in a Python that has mediapipe, e.g. 3.9-3.12).

  python tools/pose_track.py VIDEO OUT.json [--model pose_landmarker_full.task] [--max-h 720] [--start S --end E]

Writes per-frame 33 MediaPipe landmarks: image (x,y in px, visibility) and world (metres, hip-centred).
The studio itself never imports mediapipe; this script is called as a subprocess so the main app keeps
working on any Python version.
"""
import argparse, json, os, subprocess, sys, time
import numpy as np


sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def decode(path, max_h, start, end):
    from sforge import media          # imageio-ffmpeg / system ffmpeg / OpenCV - no ffprobe needed
    st = media.probe(path)
    W, H, fps = st["w"], st["h"], st["fps"]
    if H > max_h:
        W = int(round(W * max_h / H / 2)) * 2; H = max_h
    W -= W % 2; H -= H % 2
    return media.read_frames(path, W, H, start, end), fps


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video"); ap.add_argument("out")
    ap.add_argument("--model", default=os.environ.get("SFS_POSE_MODEL", ""))
    ap.add_argument("--max-h", type=int, default=720)
    ap.add_argument("--start", type=float); ap.add_argument("--end", type=float)
    a = ap.parse_args()
    import mediapipe as mp
    from mediapipe.tasks import python as mpt
    from mediapipe.tasks.python import vision
    model = a.model
    if not model or not os.path.isfile(model):
        here = os.path.dirname(os.path.abspath(__file__))
        for c in [os.path.join(here, "..", "models", "pose_landmarker_full.task")]:
            if os.path.isfile(c):
                model = c; break
    if not model or not os.path.isfile(model):
        print("pose model not found: download pose_landmarker_full.task from "
              "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/latest/pose_landmarker_full.task "
              "into models/"); return 3
    frames, fps = decode(a.video, a.max_h, a.start, a.end)
    N, H, W = frames.shape[:3]
    opts = vision.PoseLandmarkerOptions(base_options=mpt.BaseOptions(model_asset_path=model),
                                        running_mode=vision.RunningMode.VIDEO, num_poses=1,
                                        min_pose_detection_confidence=0.3, min_tracking_confidence=0.3)
    t0 = time.time(); out = []
    with vision.PoseLandmarker.create_from_options(opts) as det:
        for i in range(N):
            img = mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(frames[i]))
            r = det.detect_for_video(img, int(round(i * 1000.0 / fps)))
            if not r.pose_landmarks:
                out.append(None); continue
            lm = r.pose_landmarks[0]; wl = r.pose_world_landmarks[0]
            out.append({"img": [[p.x * W, p.y * H, p.visibility] for p in lm],
                        "world": [[p.x, p.y, p.z] for p in wl]})
    dt = time.time() - t0
    hit = sum(1 for o in out if o)
    json.dump({"video": a.video, "fps": fps, "size": [W, H], "frames": out, "model": os.path.basename(model),
               "detected": hit, "seconds": dt}, open(a.out, "w"))
    print("pose: %d/%d frames detected in %.1fs (%.1f frames/s, %s)" % (hit, N, dt, N / max(dt, 1e-6), os.path.basename(model)))
    return 0


if __name__ == "__main__":
    sys.exit(main())

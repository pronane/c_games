#!/usr/bin/env python3
"""Per-person masks + 33 pose landmarks for ONE photo (helper for `forge.py cutout --person ...`).
Runs in a Python that has mediapipe (3.9-3.12), like tools/pose_track.py; the studio calls it as a
subprocess.  Segmentation only - no pixels are generated.

  python tools/person_mask.py PHOTO OUT_DIR --model pose_landmarker_heavy.task [--max-people 6]
writes OUT_DIR/person_<i>.png (0-255 soft mask, full photo size) and OUT_DIR/people.json
"""
import argparse, json, os, sys
import numpy as np
from PIL import Image, ImageOps


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("photo"); ap.add_argument("out")
    ap.add_argument("--model", required=True)
    ap.add_argument("--max-people", type=int, default=6)
    a = ap.parse_args()
    import mediapipe as mp
    from mediapipe.tasks import python as mpt
    from mediapipe.tasks.python import vision
    im = ImageOps.exif_transpose(Image.open(a.photo)).convert("RGB")
    W, H = im.size
    opt = vision.PoseLandmarkerOptions(base_options=mpt.BaseOptions(model_asset_path=a.model),
                                       running_mode=vision.RunningMode.IMAGE, num_poses=a.max_people,
                                       output_segmentation_masks=True, min_pose_detection_confidence=0.3)
    det = vision.PoseLandmarker.create_from_options(opt)
    r = det.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=np.asarray(im)))
    os.makedirs(a.out, exist_ok=True)
    people = []
    for i, (lm, m) in enumerate(zip(r.pose_landmarks, r.segmentation_masks or [])):
        mk = np.squeeze(m.numpy_view())
        Image.fromarray((mk * 255).clip(0, 255).astype(np.uint8)).save(os.path.join(a.out, "person_%d.png" % i))
        pts = [[p.x * W, p.y * H, float(getattr(p, "visibility", 1.0) or 0.0)] for p in lm]
        ys, xs = np.nonzero(mk > 0.5)
        box = [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1] if len(xs) else [0, 0, 0, 0]
        people.append({"index": i, "mask": "person_%d.png" % i, "landmarks": pts, "box": box,
                       "area": int((mk > 0.5).sum()), "cx": float(xs.mean()) if len(xs) else 0.0})
    json.dump({"photo": os.path.abspath(a.photo), "w": W, "h": H, "people": people},
              open(os.path.join(a.out, "people.json"), "w"), indent=1)
    print("people: %d found" % len(people))
    sys.stdout.flush()
    os._exit(0)    # mediapipe's destructor can raise on interpreter exit


if __name__ == "__main__":
    main()

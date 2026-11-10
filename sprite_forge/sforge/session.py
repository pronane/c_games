"""v11.5 recording session — a folder of clips becomes one named skeleton motion set.

The owner films one clip per move (punch.mp4, walk.mp4): side-on, full body, about
one second of T-pose, then the move about three times. An optional front clip is
idle_front.mp4 / walk_front.mp4 / run_front.mp4.

This does not track poses itself. A video goes through sforge/mocap.py (the existing
MediaPipe tracker). A `.json` file in the pose-track format (what that tracker writes:
fps, size, frames of 33 landmarks) is the same pipeline after the tracker — that is
how a test can run without a person and without MediaPipe.

What is stored: pose-channel keys on the shared skeleton, same as motion_library/.
What is not stored: the video, the image frames, the face, or the body shape.
Temporary tracker files are deleted unless you pass keep_temp (and even then, do not
pack that folder — it is a pose trace of a person).

Checks, in plain language, before a clip is kept:
  too short          under about 1.6 s, or fewer than 8 frames with a person
  too dark           average brightness under 40 / 255
  tracking lost      the tracker missed the person on more than about a third of the clip,
                     or for longer than 0.4 s at a stretch
  body cut off       the head or a shoulder sits on the edge of the frame
  feet out of frame  ankles / toes sit on the bottom edge
  no T-pose          the first second does not hold the arms out at shoulder height

Where the clip repeats the move, the best repeat is kept (or a clean average of two
close ones) and the T-pose is trimmed off. Locomotion names become a loop; a strike
becomes one action.
"""
from __future__ import annotations
import json
import os
import shutil
import tempfile

from .mocap import (AN_L, AN_R, HIP_L, HIP_R, NOSE, SH_L, SH_R, TOE_L, TOE_R, WR_L, WR_R)
from .moves import slug
from .video import LOCO

VIDEO_EXT = {".mp4", ".mov", ".webm", ".mkv", ".avi", ".m4v"}
LOOP_NAMES = set(LOCO) | {"idle", "drive", "dribble", "aim", "hold", "carry"}
# brightness under this (0..255) is "too dark"
DARK_LUMA = 40.0
MIN_SECONDS = 1.6


def _loop_for(name):
    stem = slug(name).replace("_front", "").replace("_side", "")
    return stem in LOOP_NAMES or stem.endswith("_loop")


def _luma_of_video(path):
    """Mean brightness 0..255 of a few decoded frames, or None if the file cannot be read."""
    from . import media
    info = media.probe(path)
    w, h = int(info["w"]), int(info["h"])
    w -= w % 2
    h -= h % 2
    if w < 2 or h < 2:
        return None, info
    # a short sample is enough to see a black frame; don't decode a long take twice
    dur = float(info.get("duration") or 0)
    end = min(dur, 2.0) if dur else None
    fr = media.read_frames(path, max(2, w // 4 * 2 or 2), max(2, h // 4 * 2 or 2), end=end)
    if fr is None or len(fr) == 0:
        return None, info
    return float(fr.mean()), info


def _gap_frames(frames):
    best = run = 0
    for f in frames:
        if f:
            run = 0
        else:
            run += 1
            best = max(best, run)
    return best


def _detected(frames):
    return [f for f in frames if f]


def _body_cut(frames, W, H):
    det = bad = 0
    for f in frames:
        if not f:
            continue
        det += 1
        nose, shL, shR = f["img"][NOSE], f["img"][SH_L], f["img"][SH_R]
        head_out = nose[1] < 0.025 * H or nose[2] < 0.05
        side_out = min(shL[0], shR[0]) < 0.02 * W or max(shL[0], shR[0]) > 0.98 * W
        if head_out or side_out:
            bad += 1
    return bool(det) and bad > 0.25 * det


def _feet_out(frames, H):
    det = bad = 0
    for f in frames:
        if not f:
            continue
        det += 1
        ys = [f["img"][i][1] for i in (AN_L, AN_R, TOE_L, TOE_R)]
        if max(ys) > 0.97 * H:
            bad += 1
    return bool(det) and bad > 0.30 * det


def _tpose_ok(frames, fps, H):
    n = min(len(frames), max(1, int(round(float(fps) * 1.0))))
    window = frames[:n]
    det = ok = 0
    for f in window:
        if not f:
            continue
        det += 1
        good = True
        for wr, sh in ((WR_L, SH_L), (WR_R, SH_R)):
            if abs(f["img"][wr][1] - f["img"][sh][1]) > 0.10 * H:
                good = False
                break
        # arms should not be hanging at the hips either
        if good:
            for wr, hip in ((WR_L, HIP_L), (WR_R, HIP_R)):
                if f["img"][wr][1] > f["img"][hip][1] - 0.02 * H:
                    good = False
                    break
        if good:
            ok += 1
    if det < max(3, int(0.4 * n)):
        return False
    return ok >= 0.5 * det


def check_track(track, move=""):
    """-> list of plain-language reasons. Empty means the clip may be used."""
    reasons = []
    frames = list(track.get("frames") or [])
    fps = float(track.get("fps") or 30.0) or 30.0
    size = track.get("size") or [0, 0]
    W = float(size[0] or 1)
    H = float(size[1] or 1)
    n = len(frames)
    dur = n / fps
    det = _detected(frames)
    # a long clip with nobody in it is "tracking lost", not "too short"
    if dur < MIN_SECONDS or (len(det) < 8 and not (n >= 8 and len(det) == 0)):
        reasons.append("too short (%.2fs, %d frames with a person — need about 1 s of T-pose plus the move)" % (dur, len(det)))
    luma = track.get("mean_luma", None)
    if luma is not None and float(luma) < DARK_LUMA:
        reasons.append("too dark (brightness %.0f / 255 — light the room, or the figure is lost in the background)" % float(luma))
    if n and (len(det) < 0.65 * n or _gap_frames(frames) > 0.40 * fps):
        reasons.append("tracking lost (%d of %d frames, longest gap %.2fs)" % (len(det), n, _gap_frames(frames) / fps))
    if det and _body_cut(frames, W, H):
        reasons.append("body cut off (head or shoulders leave the frame — step back so the whole body stays inside)")
    if det and not _tpose_ok(frames, fps, H):
        reasons.append("no T-pose (hold the arms out at shoulder height for about 1 second before the move)")
    return reasons


def _score_span(frames, a, b, H):
    sl = frames[a:b]
    if len(sl) < 4:
        return -1.0
    det = [f for f in sl if f]
    if len(det) < 0.85 * len(sl):
        return -1.0
    if _feet_out(sl, H):
        return -1.0
    prev = None
    motion = 0.0
    for f in det:
        wx = 0.5 * (float(f["img"][WR_L][0]) + float(f["img"][WR_R][0]))
        if prev is not None:
            motion += abs(wx - prev)
        prev = wx
    return motion / max(1, len(det))


def _average(frames, spans):
    n = min(b - a for a, b in spans)
    out = []
    for i in range(n):
        samples = []
        for a, b in spans:
            f = frames[a + i] if a + i < b else None
            if f:
                samples.append(f)
        if not samples:
            out.append(None)
            continue
        img, world = [], []
        for k in range(len(samples[0]["img"])):
            cols = len(samples[0]["img"][k])
            img.append([sum(s["img"][k][c] for s in samples) / len(samples) for c in range(cols)])
            world.append([sum(s["world"][k][c] for s in samples) / len(samples) for c in range(3)])
        out.append({"img": img, "world": world})
    return out


def pick_repeat(track, loop):
    """Trim the T-pose and keep the best repeat, or the average of two close ones.

    -> (track_slice, info). info["mode"] is best | average | once.
    """
    frames = list(track.get("frames") or [])
    fps = float(track.get("fps") or 30.0) or 30.0
    H = float((track.get("size") or [1, 1])[1] or 1)
    tpose_n = min(len(frames), max(1, int(round(fps * 1.0))))
    # only skip the opening second when it actually is a T-pose
    start = tpose_n if _tpose_ok(frames, fps, H) else 0
    rest = frames[start:]
    if len(rest) < 6:
        return dict(track, frames=frames), {"mode": "whole", "repeats": 1, "picked": 0,
                                            "note": "nothing usable after the T-pose"}
    sig = []
    for f in rest:
        if not f:
            sig.append(float("nan"))
        else:
            sig.append(0.5 * (float(f["img"][WR_L][0]) + float(f["img"][WR_R][0])))
    import math
    import numpy as np
    arr = np.array(sig, float)
    if np.isnan(arr).all():
        return dict(track, frames=rest), {"mode": "once", "repeats": 1, "picked": 0, "trimmed_tpose_frames": start}
    # fill gaps so a correlation can see the repeats
    idx = np.arange(len(arr))
    good = ~np.isnan(arr)
    if good.sum() >= 2:
        arr = np.interp(idx, idx[good], arr[good])
    arr = arr - float(arr.mean())
    lo = max(4, int(0.25 * fps))
    hi = int(min(1.8 * fps, len(arr) / 2))
    best_lag, best_c = None, 0.45
    for lag in range(lo, max(lo, hi) + 1):
        a, b = arr[:-lag], arr[lag:]
        if float(np.std(a)) < 1e-3 or float(np.std(b)) < 1e-3:
            continue
        c = float(np.corrcoef(a, b)[0, 1])
        if not math.isnan(c) and c > best_c:
            best_c, best_lag = c, lag
    if not best_lag or len(arr) < best_lag * 2:
        return dict(track, frames=rest), {"mode": "once" if not loop else "whole", "repeats": 1,
                                          "picked": 0, "trimmed_tpose_frames": start,
                                          "note": "no clear repeat — using the clip after the T-pose"}
    nrep = int(len(rest) // best_lag)
    spans = [(start + i * best_lag, start + (i + 1) * best_lag) for i in range(nrep)]
    scores = [_score_span(frames, a, b, H) for a, b in spans]
    order = sorted(range(len(spans)), key=lambda i: scores[i], reverse=True)
    if scores[order[0]] < 0:
        return None, {"mode": "reject", "repeats": nrep, "scores": [round(s, 3) for s in scores],
                      "reasons": _why_spans_failed(frames, spans, H)}
    best = order[0]
    use_avg = (len(order) > 1 and scores[order[1]] > 0 and scores[best] > 0
               and scores[order[1]] >= 0.85 * scores[best]
               and (spans[order[1]][1] - spans[order[1]][0]) == (spans[best][1] - spans[best][0]))
    if use_avg:
        picked = [best, order[1]]
        avg = _average(frames, [spans[i] for i in picked])
        info = {"mode": "average", "repeats": nrep, "picked": picked, "lag_frames": best_lag,
                "scores": [round(s, 3) for s in scores], "trimmed_tpose_frames": start,
                "note": "averaged %d close repeats into one %s" % (len(picked), "loop" if loop else "move")}
        return dict(track, frames=avg), info
    a, b = spans[best]
    info = {"mode": "best", "repeats": nrep, "picked": best, "lag_frames": best_lag,
            "scores": [round(s, 3) for s in scores], "trimmed_tpose_frames": start,
            "note": "best repeat %d of %d" % (best + 1, nrep)}
    return dict(track, frames=frames[a:b]), info


def _why_spans_failed(frames, spans, H):
    feet = gap = 0
    for a, b in spans:
        sl = frames[a:b]
        if _feet_out(sl, H):
            feet += 1
        if len(_detected(sl)) < 0.85 * max(1, len(sl)):
            gap += 1
    reasons = []
    if feet:
        reasons.append("feet out of frame")
    if gap and not reasons:
        reasons.append("tracking lost")
    if not reasons:
        reasons.append("tracking lost")
    return reasons


def _fit(track, move, loop):
    """Existing mocap fitter. Returns keys, report. Raises if the fit cannot run."""
    from . import mocap
    keys, rep, _dbg = mocap.analyse(track, move, loop, n_frames=8, facing="side", log=lambda *a, **k: None)
    return keys, rep


def _load_json_track(path):
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    if not isinstance(d, dict) or "frames" not in d:
        raise ValueError("not a pose track (expected the JSON forge.py mocap writes)")
    d.pop("video", None)   # never keep a path to the person's video
    return d


def _track_from_video(path, keep_temp_dir):
    """Brightness + length first, then the existing tracker. Temp JSON is removed."""
    from . import media
    from . import mocap
    try:
        luma, info = _luma_of_video(path)
    except Exception as e:
        return None, ["could not read the video (%s)" % e]
    dur = float(info.get("duration") or 0)
    if dur and dur < MIN_SECONDS:
        reasons = ["too short (%.2fs — need about 1 s of T-pose plus the move, repeated about 3 times)" % dur]
        if luma is not None and luma < DARK_LUMA:
            reasons.append("too dark (brightness %.0f / 255)" % luma)
        return None, reasons
    if luma is not None and luma < DARK_LUMA:
        return None, ["too dark (brightness %.0f / 255 — light the room)" % luma]
    fd, tmp = tempfile.mkstemp(prefix="sfs_session_", suffix=".json")
    os.close(fd)
    try:
        d = mocap.track(path, tmp, log=lambda *a, **k: None)
    except RuntimeError as e:
        msg = str(e).strip().splitlines()[0] if str(e).strip() else "pose tracking failed"
        if "mediapipe" in msg.lower() or "pose model" in msg.lower() or "setup_pose" in msg:
            msg = "tracking needs MediaPipe (python tools/setup_pose.py) — the video was not stored"
        return None, [msg]
    finally:
        if not keep_temp_dir:
            try:
                os.remove(tmp)
            except OSError:
                pass
        elif keep_temp_dir:
            try:
                os.makedirs(keep_temp_dir, exist_ok=True)
                shutil.move(tmp, os.path.join(keep_temp_dir, slug(os.path.splitext(os.path.basename(path))[0]) + ".track.json"))
            except OSError:
                try:
                    os.remove(tmp)
                except OSError:
                    pass
    if isinstance(d, dict):
        d.pop("video", None)
        if luma is not None:
            d["mean_luma"] = luma
    return d, []


def _clip_files(folder):
    out = []
    for f in sorted(os.listdir(folder)):
        if f.startswith(".") or f.startswith("_"):
            continue
        ext = os.path.splitext(f)[1].lower()
        path = os.path.join(folder, f)
        if not os.path.isfile(path):
            continue
        if ext in VIDEO_EXT or ext == ".json":
            out.append(path)
    return out


def _pose_only(rec):
    """True when a saved move has no image, video or landmark arrays."""
    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k in ("img", "world", "video", "frames"):
                    return False
                if not walk(v):
                    return False
            return True
        if isinstance(o, (list, tuple)):
            return all(walk(x) for x in o)
        return True
    return walk(rec)


def import_folder(folder, set_name, library=None, keep_temp=False, licence=None):
    """Import every clip in `folder` into motion set `set_name`.

    -> report dict with text, kept, rejected. The set lives at
    library/motion_sets/<name>/ and holds skeleton JSON only.
    """
    from . import motionlib as ML
    from . import motionset as MS
    from .library import blank_licence, validate_licence
    if not folder or not os.path.isdir(folder):
        raise FileNotFoundError("clip folder not found: %s" % folder)
    name = slug(set_name or "") or "session"
    dest = MS.set_dir(name, library)
    os.makedirs(dest, exist_ok=True)
    keep_dir = os.path.join(dest, "_temp") if keep_temp else None
    if keep_dir and os.path.isdir(keep_dir):
        shutil.rmtree(keep_dir)
    files = _clip_files(folder)
    # one file per move: a video wins over a json of the same stem
    by_stem = {}
    for path in files:
        stem = slug(os.path.splitext(os.path.basename(path))[0].replace(".track", ""))
        ext = os.path.splitext(path)[1].lower()
        prev = by_stem.get(stem)
        if prev is None or ext in VIDEO_EXT:
            by_stem[stem] = path
    lic = dict(licence or blank_licence())
    if not lic.get("author"):
        lic["author"] = "recorded session"
    if not lic.get("redistribution"):
        lic["redistribution"] = "no"
    if not lic.get("notes"):
        lic["notes"] = ("Skeleton motion from a private recording. The video, frames, face and body "
                        "shape were not kept. Set a real SPDX id before you pack this.")
    kept, rejected = [], []
    lines = ["Recording session '%s' — skeleton motion only" % name,
             "The video, the image frames, the face and the body shape are not stored.",
             "Temporary tracker files are %s." % ("kept in _temp/ (do not pack that folder)" if keep_temp else "deleted"),
             ""]
    for stem, path in by_stem.items():
        base = os.path.basename(path)
        ext = os.path.splitext(path)[1].lower()
        try:
            if ext in VIDEO_EXT:
                track, pre = _track_from_video(path, keep_dir)
            else:
                track, pre = _load_json_track(path), []
        except Exception as e:
            rejected.append({"file": base, "move": stem, "reasons": [str(e)]})
            lines.append("%-18s RESHOOT   %s" % (base, str(e)))
            continue
        if pre:
            rejected.append({"file": base, "move": stem, "reasons": pre})
            lines.append("%-18s RESHOOT   %s" % (base, "; ".join(pre)))
            continue
        reasons = check_track(track, stem)
        if reasons:
            rejected.append({"file": base, "move": stem, "reasons": reasons})
            lines.append("%-18s RESHOOT   %s" % (base, "; ".join(reasons)))
            continue
        loop = _loop_for(stem)
        trimmed, info = pick_repeat(track, loop)
        if trimmed is None:
            why = info.get("reasons") or ["tracking lost"]
            rejected.append({"file": base, "move": stem, "reasons": why})
            lines.append("%-18s RESHOOT   %s" % (base, "; ".join(why)))
            continue
        # a trimmed repeat can still have its feet out
        if _feet_out(trimmed.get("frames") or [], float((trimmed.get("size") or [1, 1])[1] or 1)):
            rejected.append({"file": base, "move": stem, "reasons": ["feet out of frame"]})
            lines.append("%-18s RESHOOT   feet out of frame" % base)
            continue
        try:
            keys, rep = _fit(trimmed, stem, loop)
        except Exception as e:
            rejected.append({"file": base, "move": stem, "reasons": ["tracking lost (%s)" % e]})
            lines.append("%-18s RESHOOT   tracking lost (%s)" % (base, e))
            continue
        if not keys or len(keys) < 2:
            rejected.append({"file": base, "move": stem, "reasons": ["tracking lost (no skeleton keys)"]})
            lines.append("%-18s RESHOOT   tracking lost (no skeleton keys)" % base)
            continue
        rec = {
            "name": stem,
            "category": "Recorded",
            "desc": "recorded session '%s' — skeleton only" % name,
            "loop": bool(loop),
            "source": "session:%s" % name,
            "origin": "record",
            "licence": lic,
            "duration": round(len(trimmed.get("frames") or []) / float(trimmed.get("fps") or 30.0), 3),
            "keys": keys,
            "session": {
                "set": name,
                "clip": base,
                "trim": {k: info.get(k) for k in ("mode", "repeats", "picked", "note")},
                "checks": "ok",
                "stored": "skeleton",
            },
        }
        if not _pose_only(rec):
            rejected.append({"file": base, "move": stem, "reasons": ["refusing to store a clip that still contains landmarks or video"]})
            lines.append("%-18s RESHOOT   internal check refused to store landmarks" % base)
            continue
        ML.open_library(dest).save(rec)
        kept.append(stem)
        lines.append("%-18s OK        %s. %d keys. stored as skeleton only." % (base, info.get("note") or info.get("mode"), len(keys)))
    # drop any media that might have been copied by mistake
    for f in os.listdir(dest):
        ext = os.path.splitext(f)[1].lower()
        if ext in VIDEO_EXT or ext in {".png", ".jpg", ".jpeg", ".webp", ".bmp"}:
            os.remove(os.path.join(dest, f))
    meta = {
        "name": name,
        "kind": "skeleton",
        "video_kept": False,
        "frames_kept": False,
        "note": "Skeleton motion only. The source video, image frames, face and body shape are not stored.",
        "moves": kept,
        "rejected": [{"file": r["file"], "reasons": r["reasons"]} for r in rejected],
    }
    with open(os.path.join(dest, "_set.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=1)
    lines += ["", "Stored: %s" % (", ".join(kept) or "(none)"),
              "Reshoot: %s" % (", ".join(r["file"] for r in rejected) or "(none)"),
              "Set folder: %s" % dest]
    if validate_licence(lic):
        lines.append("Licence: incomplete (" + "; ".join(validate_licence(lic)) + ") — fine locally, not for a pack.")
    text = "\n".join(lines) + "\n"
    with open(os.path.join(dest, "_session.txt"), "w", encoding="utf-8") as f:
        f.write(text)
    return {"name": name, "dir": dest, "kept": kept, "rejected": rejected, "text": text, "ok": not rejected}

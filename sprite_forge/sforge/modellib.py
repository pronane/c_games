"""The "models" library kind: machine-learning models as versioned, licensed assets (v11.41).

Detectors, pose estimators, the 2D->3D lifter and, next, the Learned Motion Matching networks used to be
loose entries in sforge/models/registry.json.  Each is now a library asset:

    library/models/<name>/model.json     what it is (below)
    library/models/<name>/licence.json   the usual licence record (spdx, author, redistribution, ml_training)
    library/models/<name>/<file>         the weights, when they are stored (else `url` / `zip` to fetch)

model.json:
    name, title, task (TASKS), version (int), format (onnx / tflite / task / ...), file, sha256, bytes,
    url / zip, role, inputs / outputs, metrics {}, used_by [], check (a licence caveat to confirm),
    trained_here (bool), trained_by (script), trained_on [{dataset, spdx, ml_training, note}]

A model trained here may only be trained on data whose `ml_training` is "yes"; `validate_model` reports any
dataset that is not, and `library pack` refuses such a model.  Names carry the version ("lifter_v1",
"lifter_v2"); `latest(lib, task)` picks the highest version of a task.

    from sforge import library as L, modellib as ML
    lib = L.Library()
    ML.import_registry(lib)                    # the registry's models -> library/models/*
    ML.latest(lib, "lifter")                   # -> ("lifter_v1", model.json dict)
"""
from __future__ import annotations

import json
import os
import re
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
REGISTRY = os.path.join(HERE, "models", "registry.json")
TASKS = ("detector", "pose2d", "pose3d", "lifter", "motion_matching", "motion_generator", "classifier", "other")
META = "model.json"


def blank_model(name, task="other", version=1):
    return dict(name=name, title=name, task=task, version=int(version), format="", file="", sha256="", bytes=0,
                url="", role="", inputs=[], outputs=[], metrics={}, used_by=[], check="", trained_here=False,
                trained_by="", trained_on=[])


def version_of(name, meta=None):
    if meta and meta.get("version") not in (None, ""):
        return int(meta["version"])
    m = re.search(r"_v(\d+)$", name)
    return int(m.group(1)) if m else 1


def validate_model(meta, folder=None):
    """-> list of problems (empty = complete)."""
    p = []
    if meta.get("task") not in TASKS:
        p.append("task must be one of %s" % ", ".join(TASKS))
    try:
        int(meta.get("version"))
    except (TypeError, ValueError):
        p.append("version must be a whole number")
    f = meta.get("file")
    if not f and not (meta.get("url") or meta.get("zip")):
        p.append("needs a stored file or a url / zip to fetch it from")
    if f and folder and meta.get("stored") and not os.path.isfile(os.path.join(folder, f)):
        p.append("stored file %s is missing" % f)
    if meta.get("trained_here"):
        if not meta.get("trained_on"):
            p.append("trained here but trained_on is empty (list the datasets)")
        for d in meta.get("trained_on") or []:
            if d.get("ml_training") != "yes":
                p.append("trained on %s whose ml_training is %s - only 'yes' data may train a model"
                         % (d.get("dataset", "?"), d.get("ml_training", "unknown")))
    return p


def _licence_for(entry):
    """registry entry -> library licence record"""
    from .library import blank_licence
    txt = str(entry.get("licence", ""))
    m = re.match(r"\s*([A-Za-z0-9.\-+]+)", txt)
    spdx = m.group(1) if m else ""
    lic = blank_licence(redistribution="yes" if spdx in ("Apache-2.0", "MIT", "CC0-1.0", "BSD-3-Clause") else "unknown")
    lic.update(spdx=spdx, author=entry.get("author") or ("Sprite Forge (trained here)" if entry.get("trained_by") else
               "OpenMMLab" if "OpenMMLab" in entry.get("name", "") else "Google (MediaPipe)" if "MediaPipe" in entry.get("name", "")
               else entry.get("name", "")),
               source_url=entry.get("url") or entry.get("zip") or "", attribution="", notes=txt + (
                   ("; " + entry["check"]) if entry.get("check") else ""))
    # a model's own licence says whether its weights may be fine-tuned / distilled; Apache / MIT allow it
    # (unknown while the registry flags a training-data caveat to confirm, e.g. Human-Art / Body7 for OpenMMLab)
    lic["ml_training"] = "yes" if spdx in ("Apache-2.0", "MIT", "CC0-1.0") and not entry.get("check") else "unknown"
    return lic


TASK_GUESS = [("lifter", r"lifter|2d->3d"), ("detector", r"detector|person boxes"), ("pose3d", r"3d world|landmark"),
              ("pose2d", r"keypoints|rtmpose"), ("motion_matching", r"motion match"), ("motion_generator", r"generat")]


def _task(entry):
    hay = (entry.get("name", "") + " " + entry.get("role", "")).lower()
    for t, pat in TASK_GUESS:
        if re.search(pat, hay):
            return t
    return "other"


# the lifter's own training data (SkillCorner Open Data body pose, MIT)
LIFTER_DATA = [dict(dataset="SkillCorner opendata-bodypose", spdx="MIT", ml_training="yes",
                    note="matches 1925299 (train) and 1996435 (validation)")]


def from_registry(path=REGISTRY):
    """-> [(name, model.json dict, licence dict, stored file path or None)]"""
    reg = json.load(open(path, encoding="utf-8"))
    out = []
    for key, e in reg.get("models", {}).items():
        meta = blank_model(key, _task(e), version_of(key))
        meta.update(title=e.get("name", key), file=os.path.basename(e.get("file", "")), source_file=e.get("file", ""),
                    url=e.get("url", ""), zip=e.get("zip", ""), role=e.get("role", ""), used_by=list(e.get("used_by", [])),
                    check=e.get("check", ""), format=os.path.splitext(e.get("file", ""))[1].lstrip("."))
        if e.get("val_mpjpe_cm") is not None:
            meta["metrics"] = {"val_mpjpe_cm": e["val_mpjpe_cm"]}
        stored = None
        if e.get("trained_by"):
            meta.update(trained_here=True, trained_by=e["trained_by"], trained_on=list(LIFTER_DATA),
                        training_data=e.get("training_data", ""))
        if e.get("committed"):
            p = os.path.join(os.path.dirname(path), e.get("file", ""))
            if os.path.isfile(p):
                stored = p
        out.append((key, meta, _licence_for(e), stored))
    return out


def add_model(lib, name, meta, licence, files=()):
    """write library/models/<name>: model.json, licence.json and copies of `files` (weights, configs)."""
    from .library import sha256_file, now, slug
    lib.ensure()
    name = slug(name)
    d = lib.path("models", name)
    os.makedirs(d, exist_ok=True)
    meta = dict(meta, name=name, added=meta.get("added") or now())
    stored = []
    for i, f in enumerate(files):
        dst = os.path.join(d, os.path.basename(f))
        if os.path.abspath(f) != os.path.abspath(dst):
            shutil.copy2(f, dst)
        stored.append(os.path.basename(f))
        if i == 0:
            meta.update(file=os.path.basename(f), sha256=sha256_file(dst), bytes=os.path.getsize(dst), stored=True)
    if stored[1:]:
        meta["extra_files"] = stored[1:]
    meta.setdefault("stored", False)
    json.dump(meta, open(os.path.join(d, META), "w", encoding="utf-8"), indent=1)
    json.dump(licence, open(os.path.join(d, "licence.json"), "w", encoding="utf-8"), indent=1)
    return d, validate_model(meta, d)


def import_registry(lib, path=REGISTRY, overwrite=False, copy_weights=True):
    """registry.json -> library models.  Committed weights (the lifter) are copied (copy_weights=False keeps
    them in sforge/models; weights_path finds them there); others keep their url.  -> [(name, problems)]"""
    done = []
    for name, meta, lic, stored in from_registry(path):
        if name in lib.names("models") and not overwrite:
            done.append((name, ["already in the library (skipped)"]))
            continue
        files = []
        if stored and copy_weights:
            files.append(stored)
            side = os.path.splitext(stored)[0] + ".json"   # the lifter's joint list / normalisation
            if os.path.isfile(side):
                files.append(side)
        d, probs = add_model(lib, name, meta, lic, files)
        done.append((name, probs))
    return done


def load(lib, name):
    return json.load(open(os.path.join(lib.path("models", name), META), encoding="utf-8"))


def latest(lib, task):
    """-> (name, meta) of the highest version of `task`, or (None, None)."""
    best = (None, None, -1)
    for n in lib.names("models"):
        m = load(lib, n)
        if m.get("task") == task and version_of(n, m) > best[2]:
            best = (n, m, version_of(n, m))
    return best[0], best[1]


def weights_path(lib, name):
    """the stored weights file, or None (fetch it from meta['url'] / ['zip'] with tools/fetch_models.py)."""
    m = load(lib, name)
    p = os.path.join(lib.path("models", name), m.get("file") or "")
    if m.get("stored") and os.path.isfile(p):
        return p
    # not stored in the library: the place tools/fetch_models.py downloads it to
    q = os.path.join(HERE, "models", m.get("source_file") or m.get("file") or "")
    return q if (m.get("source_file") or m.get("file")) and os.path.isfile(q) else None

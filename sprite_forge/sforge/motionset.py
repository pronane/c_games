"""v11.5 named motion sets — one recorded skeleton library, used as the default source.

A set is a folder of the same JSON clips as the motion library (pose channels only).
Video, frames, face and body shape are not part of a set. See sforge/session.py.

Search when a set is the default source for a build:
  1. the named set
  2. your library/motions folder (a clip you imported on its own)
  3. the shipped starter (motion_library/, baked from the procedural motions)
  4. the live procedural motion, if none of those have a clip

The build report names the source of every move when a set or a game pack is in use.
With no set selected, builds behave as they did in v11.4.
"""
from __future__ import annotations
import json
import os

from .moves import slug


def library_root(library=None):
    from .library import libdir
    return libdir(library)


def sets_root(library=None):
    return os.path.join(library_root(library), "motion_sets")


def settings_path(library=None):
    return os.path.join(library_root(library), "motion_settings.json")


def set_dir(name, library=None):
    return os.path.join(sets_root(library), slug(name) or "set")


def _label(folder):
    meta = os.path.join(folder, "_set.json")
    if os.path.isfile(meta):
        try:
            with open(meta, encoding="utf-8") as f:
                n = json.load(f).get("name")
            if n:
                return str(n)
        except (OSError, json.JSONDecodeError, AttributeError):
            pass
    return os.path.basename(folder.rstrip(os.sep))


def list_sets(library=None):
    root = sets_root(library)
    if not os.path.isdir(root):
        return []
    out = []
    for name in sorted(os.listdir(root)):
        d = os.path.join(root, name)
        if os.path.isdir(d) and (os.path.isfile(os.path.join(d, "_set.json")) or any(
                f.endswith(".json") and not f.startswith("_") for f in os.listdir(d))):
            out.append(_label(d))
    return out


def saved_default(library=None):
    p = settings_path(library)
    if not os.path.isfile(p):
        return ""
    try:
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, json.JSONDecodeError):
        return ""
    return str(d.get("default_set") or "")


def set_default(name, library=None):
    """Remember the set every build should read first. `off` / empty clears it."""
    os.makedirs(library_root(library), exist_ok=True)
    p = settings_path(library)
    name = (name or "").strip()
    if not name or name.lower() in ("off", "none", "(none)"):
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"default_set": ""}, f, indent=1)
        return ""
    folder = name if os.path.isdir(name) else set_dir(name, library)
    if not os.path.isdir(folder):
        raise FileNotFoundError("motion set '%s' not found (forge.py motion sets)" % name)
    label = _label(folder)
    with open(p, "w", encoding="utf-8") as f:
        json.dump({"default_set": label,
                   "note": "Builds read this set first, then the starter fills gaps. Skeleton clips only."}, f, indent=1)
    return label


def _has_file(folder, name):
    return os.path.isfile(os.path.join(folder, slug(name) + ".json"))


def _candidates(m):
    from .motionlib import _slug
    mot = (getattr(m, "motion", "") or "").strip()
    raw = []
    if mot.lower().startswith("lib:"):
        raw.append(mot.split(":", 1)[1])
    raw.append(getattr(m, "name", "") or "")
    if mot and not mot.lower().startswith("lib:"):
        raw.append(mot)
    out = []
    for r in raw:
        s = _slug(r) if r else ""
        if s and s not in out:
            out.append(s)
    return out


def resolve_folder(choice, library=None):
    """-> (folder or None, label).

    choice "" uses the saved default (or nothing). "off" forces no set.
    A missing explicit name raises. A missing saved default is ignored.
    """
    choice = (choice or "").strip()
    if choice.lower() in ("off", "none", "(none)"):
        return None, ""
    if choice and os.path.isdir(choice) and os.path.isfile(os.path.join(choice, "_set.json")):
        return os.path.abspath(choice), _label(choice)
    if choice:
        folder = set_dir(choice, library)
        if not os.path.isdir(folder):
            raise FileNotFoundError("motion set '%s' not found under %s" % (choice, sets_root(library)))
        return folder, _label(folder)
    name = saved_default(library)
    if not name:
        return None, ""
    folder = set_dir(name, library)
    if not os.path.isdir(folder):
        return None, ""
    return folder, _label(folder)


def apply_cfg(cfg):
    """Point library moves at the set, then the starter. Sets `motion_source` on each move.

    Safe to call twice. Does nothing visible when no set is selected and no move asks
    for a library clip: procedural presets stay procedural.
    """
    from . import motionlib as ML
    library = getattr(cfg, "library_dir", "") or None
    try:
        folder, label = resolve_folder(getattr(cfg, "motion_set", "") or "", library)
    except FileNotFoundError:
        raise
    if folder:
        os.environ["SFS_MOTION_SET"] = folder
        cfg.motion_set_resolved = label
    else:
        os.environ.pop("SFS_MOTION_SET", None)
        cfg.motion_set_resolved = ""
    for m in cfg.moves or []:
        cands = _candidates(m)
        chosen = None
        if folder:
            for c in cands:
                if _has_file(folder, c):
                    chosen = c
                    break
        if chosen:
            m.motion = "lib:" + chosen
            m.motion_source = ML.origin_of(chosen, getattr(cfg, "motion_library", "") or None)
            continue
        wants = (m.motion or "").lower().startswith("lib:") or getattr(m, "want_library", False)
        if wants:
            key = cands[0] if cands else m.name
            if ML.has_move(key, getattr(cfg, "motion_library", "") or None):
                m.motion = "lib:" + ML._slug(key)
                m.motion_source = ML.origin_of(key, getattr(cfg, "motion_library", "") or None)
            else:
                if (m.motion or "").lower().startswith("lib:"):
                    m.motion = ""
                m.motion_source = "procedural"
        else:
            m.motion_source = "procedural"
    return cfg.motion_set_resolved

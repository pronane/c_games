"""v11.5 named motion sets — one recorded skeleton library, used as the default source.

A set is a folder of the same JSON clips as the motion library (pose channels only).
Video, frames, face and body shape are not part of a set. See sforge/session.py.

Search when a move asks for a library clip (a game pack, or motion "lib:name"):
  1. a specific clip the pack lists first ("prefer", then "own")
  2. a recording of this exact move (the set, then your library/motions folder)
  3. a shipped starter clip of this move (not another move's clip)
  4. the move's own procedural animation (the pre-library pose)
  5. the pack's generic library name — only when this move has no animation of
     its own, or the pack sets "alias": true

A recorded punch does not play for special1 or throw. The build report names
every move's source and lists any clips that are still shared.
With no set selected and no game pack, builds behave as they did in v11.4.
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


def _slugs(items):
    from .motionlib import _slug
    out = []
    for r in items or []:
        s = _slug(r) if r else ""
        if s and s not in out:
            out.append(s)
    return out


def _library_name(m):
    """The pack's generic clip, or the clip an explicit lib: motion names."""
    named = getattr(m, "library_name", "") or ""
    if named:
        return _slugs([named])[0]
    mot = (getattr(m, "motion", "") or "").strip()
    if mot.lower().startswith("lib:"):
        return _slugs([mot.split(":", 1)[1]])[0]
    return ""


def _dedicated(m):
    """This move's own procedural motion, or ''.

    `own` is how a pack points a colliding name at the right motion (kart "idle"
    is kart_idle, not the standing idle). Otherwise find_motion(name): special1
    is special_1, throw is throw. A miss means the move has no animation of its own.
    """
    from .motions import find_motion
    for label in list(getattr(m, "own_clips", None) or []):
        mo = find_motion(label)
        if mo is not None:
            return mo.name
    mo = find_motion(getattr(m, "name", "") or "")
    return mo.name if mo is not None else ""


def _own_spellings(m, dedicated):
    """Names that mean this move, including the old alias spellings (special1 / special_1)."""
    from .motions import ALIASES
    from .moves import slug
    name = slug(getattr(m, "name", "") or "")
    raw = [name, dedicated]
    raw.extend(getattr(m, "own_clips", None) or [])
    for k, v in ALIASES.items():
        if k == name or v == name or (dedicated and v == dedicated):
            raw.extend((k, v))
    return _slugs(raw)


def _where(name, mlib):
    from . import motionlib as ML
    if not name or not ML.has_move(name, mlib):
        return ""
    return ML.origin_of(name, mlib)


def _recorded(src):
    """A set (`set:<name>`) or the user's own library folder, not the shipped starter."""
    return src == "library" or src.startswith("set:")


def _from_motion(name, mlib):
    from . import motionlib as ML
    import json
    try:
        path = ML.open_library(mlib).path_of(name)
    except KeyError:
        return ""
    try:
        with open(path, encoding="utf-8") as f:
            return str(json.load(f).get("from_motion") or "")
    except (OSError, json.JSONDecodeError, AttributeError):
        return ""


def _starter_ok(name, m, dedicated, mlib):
    """A shipped file is this move's clip, not a different move that happens to share a word."""
    if _where(name, mlib) != "starter":
        return False
    from .moves import slug
    lib = _library_name(m)
    move = slug(getattr(m, "name", "") or "")
    baked = _from_motion(name, mlib)
    if dedicated and name == move and dedicated not in (name, baked):
        return False
    if lib and lib == move and name == move:
        return True
    if dedicated and (name == dedicated or baked == dedicated):
        return True
    if name == move and baked in ("", name) and not (lib and lib != move and not dedicated):
        return True
    return False


def _alias_allowed(m, dedicated, force):
    """The generic library name is a shared clip only when this move has nothing of its own."""
    if force:
        return True
    lib = _library_name(m)
    from .moves import slug
    move = slug(getattr(m, "name", "") or "")
    if not lib or lib == move or (dedicated and lib == dedicated):
        return False
    if dedicated and not getattr(m, "force_alias", False):
        return False
    return bool(lib)


def _bind(m, name, source, alias):
    m.motion = "lib:" + name
    m.motion_source = source
    m.motion_alias = bool(alias)
    m.resolved_clip = "lib:" + name


def _use_procedural(m, dedicated):
    from .moves import slug
    move = slug(getattr(m, "name", "") or "")
    if dedicated and dedicated != move:
        m.motion = dedicated
    elif (getattr(m, "motion", "") or "").lower().startswith("lib:"):
        m.motion = ""
    m.motion_source = "procedural"
    m.motion_alias = False
    m.resolved_clip = "motion:" + (dedicated or move or m.name)


def _is_shared_alias(m, chosen, dedicated, mlib):
    lib = _library_name(m)
    if not lib or chosen != lib:
        return False
    from .moves import slug
    move = slug(getattr(m, "name", "") or "")
    if chosen in (move, dedicated) or chosen in _slugs(getattr(m, "own_clips", None)):
        return False
    if dedicated and _from_motion(chosen, mlib) == dedicated:
        return False
    return True


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


def _pick(m, mlib, force):
    """-> (clip name or '', source or 'procedural', alias flag)."""
    dedicated = _dedicated(m)
    spellings = _own_spellings(m, dedicated)
    # prefer is a specific clip for this move. own (kart_idle, item_throw) is a spelling,
    # so a recording named idle still beats the starter, and the starter beats another move's punch.
    first = _slugs(getattr(m, "library_prefer", None))
    lib = _library_name(m)

    def take(name, source):
        return name, source, _is_shared_alias(m, name, dedicated, mlib)

    for name in first:
        src = _where(name, mlib)
        if src:
            return take(name, src)
    for name in spellings:
        src = _where(name, mlib)
        if _recorded(src):
            return take(name, src)
    if not force:
        for name in spellings:
            if _starter_ok(name, m, dedicated, mlib):
                return take(name, "starter")
        if dedicated:
            from .motionlib import STARTER
            for generic, src_name in STARTER:
                if src_name == dedicated or generic == dedicated:
                    if _starter_ok(generic, m, dedicated, mlib):
                        return take(generic, "starter")
        if dedicated and not _alias_allowed(m, dedicated, False):
            return "", "procedural", False
    if _alias_allowed(m, dedicated, force) and lib:
        src = _where(lib, mlib)
        if src:
            return take(lib, src)
    return "", "procedural", False


def apply_cfg(cfg):
    """Point each move at its own clip, then its own procedural motion.

    A generic library name is used only when the move has no animation of its own,
    or the pack sets alias, or a profile/CLI motion is an explicit lib: clip.
    Safe to call twice. With no set and no library move, procedural presets stay procedural.
    """
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
    mlib = getattr(cfg, "motion_library", "") or None
    for m in cfg.moves or []:
        mot0 = (getattr(m, "motion", "") or "").strip()
        wants = mot0.lower().startswith("lib:") or getattr(m, "want_library", False)
        explicit = mot0.lower().startswith("lib:") and not getattr(m, "want_library", False)
        force = bool(getattr(m, "force_alias", False) or explicit)
        if not wants:
            # A profile stays on its procedural motion unless the selected set has this move.
            dedicated = _dedicated(m)
            picked = ""
            if folder:
                for name in _own_spellings(m, dedicated):
                    if _has_file(folder, name):
                        picked = name
                        break
            if picked:
                _bind(m, picked, _where(picked, mlib) or ("set:" + label), False)
            else:
                m.motion_source = "procedural"
                m.motion_alias = False
                m.resolved_clip = "motion:" + ((getattr(m, "motion", "") or dedicated or getattr(m, "name", "") or ""))
            continue
        name, source, alias = _pick(m, mlib, force)
        if name:
            _bind(m, name, source, alias)
        else:
            _use_procedural(m, _dedicated(m))
    return cfg.motion_set_resolved


def clip_id(m):
    """The clip this move will play: lib:<file> or motion:<procedural name>."""
    rid = getattr(m, "resolved_clip", "") or ""
    if rid:
        return rid
    mot = (getattr(m, "motion", "") or "").strip()
    if mot.lower().startswith("lib:"):
        return "lib:" + mot.split(":", 1)[1]
    return "motion:" + (mot or getattr(m, "name", "") or "")


def shared_note(moves):
    """One line naming moves that still play the same clip. Empty when every move is its own."""
    groups = {}
    for m in moves or []:
        groups.setdefault(clip_id(m), []).append(m)
    parts = []
    for ident, ms in groups.items():
        if len(ms) < 2:
            continue
        names = "+".join(m.name for m in ms)
        clip = ident.split(":", 1)[-1]
        owners = [m for m in ms if m.name == clip or (m.motion or "") == clip]
        borrowers = [m for m in ms if m not in owners]
        if borrowers and all(getattr(m, "motion_alias", False) for m in borrowers):
            kind = "explicit alias"
        elif all(getattr(m, "motion_alias", False) for m in ms):
            kind = "explicit alias"
        else:
            kind = "shared"
        parts.append("%s=%s (%s)" % (names, ident, kind))
    return "; ".join(parts)

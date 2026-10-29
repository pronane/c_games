"""Team kits / colour variants for library rigs (v6).

A kit is library/kits/<name>.json:
  {"name": "red_team", "description": "...",
   "materials": {"*shirt*|*jersey*|*top*": {"color": "#c01010", "mode": "tint"},
                 "*shorts*|*pants*":       {"color": [0.95, 0.95, 0.95], "mode": "replace"}},
   "licence": {...}}
Material names are matched case-insensitively with shell wildcards; '|' separates alternatives; the first
matching rule wins.  Modes:
  replace   flat colour (texture ignored)
  multiply  material / texture colour x kit colour
  tint      keeps the texture's light/dark detail but takes the kit colour (good for striped / printed shirts)
The six built-in mannequin kits (home away blue red black gk) also work on library rigs: they recolour
materials whose names contain shirt/top/jersey, shorts/pants, socks and trim.
"""
from __future__ import annotations
import fnmatch
import json
import os

ROLE_PATTERNS = {"shirt": "*shirt*|*jersey*|*top*|*torso_cloth*|*kit*", "shorts": "*short*|*pant*|*trouser*",
                 "socks": "*sock*", "trim": "*trim*|*accent*|*stripe*"}


def parse_color(c):
    if isinstance(c, str):
        c = c.strip().lstrip("#")
        if len(c) == 3:
            c = "".join(ch * 2 for ch in c)
        return [int(c[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
    return [float(x) for x in list(c)[:3]]


def builtin(name):
    from .mesh import KITS
    k = KITS.get(name)
    if not k:
        return None
    return {"name": name, "description": "built-in kit: " + k["label"], "builtin": True,
            "materials": {ROLE_PATTERNS[r]: {"color": list(k[r]), "mode": "tint"} for r in ("shirt", "shorts", "socks", "trim")}}


def load(name_or_path, libdir=None):
    """kit dict from a .json path, library/kits/<name>.json or a built-in name; None for '' / unknown."""
    if not name_or_path:
        return None
    if isinstance(name_or_path, dict):
        return name_or_path
    if os.path.isfile(name_or_path):
        return json.load(open(name_or_path, encoding="utf-8"))
    if libdir:
        p = os.path.join(libdir, "kits", name_or_path + ".json")
        if os.path.isfile(p):
            return json.load(open(p, encoding="utf-8"))
    return builtin(name_or_path)


def rule_for(kit, matname):
    if not kit:
        return None
    n = (matname or "").lower()
    for pat, r in kit.get("materials", {}).items():
        if any(fnmatch.fnmatchcase(n, p.strip().lower()) for p in pat.split("|") if p.strip()):
            return {"color": parse_color(r.get("color", [1, 1, 1])), "mode": r.get("mode", "tint")}
    return None

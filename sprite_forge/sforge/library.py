"""User library of rigs, animations and kits + shareable .sfpack packs with mandatory licence records (v6).

Layout (default <studio>/library, or $SFS_LIBRARY, or --library DIR):
  library/library.json                 manifest (rebuilt by `forge.py library scan`)
  library/rigs/<name>/                 rig.json rig.npz bonemap.json licence.json thumb.png textures/ source.json
  library/animations/<name>/           same, skeleton + clips only (no mesh)
  library/kits/<name>.json             colour / material kit (licence inside)
  library/inbox/                       drop FBX / GLB files here; `library scan` imports them (licence: unknown)

Source files are never copied into the library or a pack: source.json keeps the original path + sha256.

Licence record (licence.json, mandatory for every asset):
  {"spdx": "CC0-1.0" | "" , "custom_text": "", "author": "", "source_url": "",
   "redistribution": "yes" | "no" | "unknown", "attribution": "", "notes": "",
   "rights_override": {"by": "...", "date": "...", "statement": "..."}   (only when the user confirmed)}
Pack export refuses assets whose redistribution is "no" or "unknown" unless the user explicitly confirms
"I own the rights" for that asset (recorded in the asset's licence and in the pack).  Installing a pack shows
every licence and requires acknowledgement.
"""
from __future__ import annotations
import datetime
import fnmatch
import hashlib
import io
import json
import os
import re
import shutil
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KINDS = ("rigs", "animations", "kits", "outfits", "props")
KIND_ALIASES = {"rig": "rigs", "animation": "animations", "anim": "animations", "kit": "kits", "outfit": "outfits",
                "prop": "props", "armour": "outfits", "armor": "outfits", "clothing": "outfits"}
SOCKETS = ("hand_r", "hand_l", "head", "back", "hip", "foot_r", "foot_l")
# v7 licence presets (library add --preset ...): pre-filled records the user can still edit
MESHY_ANIM_WHY = ("Meshy animation-library clips are Meshy 'Service Assets', licensed only as incorporated into your "
                  "Meshy output (Meshy Terms of Use 3.1); standalone redistribution is not clearly allowed - default NO")
LICENCE_PRESETS = {
    "meshy-free": dict(spdx="CC-BY-4.0", custom_text="", author="Meshy (free plan output, licensed CC BY 4.0)",
                       source_url="https://www.meshy.ai", redistribution="yes",
                       attribution="Model created with Meshy \u2013 CC BY 4.0 License",
                       notes="Meshy free plan: Meshy owns the output and licenses it under CC BY 4.0 (commercial use OK with "
                             "credit). Terms: https://www.meshy.ai/terms-of-use 3.2; help.meshy.ai ownership article."),
    "meshy-paid": dict(spdx="LicenseRef-Proprietary", custom_text="Meshy paid-plan output: privately owned by the user who generated it "
                       "(Meshy Terms of Use 3.2), provided the inputs did not infringe anyone's copyright.", author="",
                       source_url="https://www.meshy.ai", redistribution="no", attribution="",
                       notes="Default redistribution NO: it is your private asset - flip to yes if you want to share it "
                             "(library licence NAME --redistribution yes). Meshy asks paid users who want to keep ownership not to "
                             "publish the model to the Meshy Community."),
    "makehuman": dict(spdx="CC0-1.0", custom_text="", author="MakeHuman base assets (CC0) + your parameters",
                      source_url="http://www.makehumancommunity.org", redistribution="yes", attribution="",
                      notes="MakeHuman assets (base mesh, targets, default skeleton + weights) are CC0 1.0; exports are the "
                            "user's own data. MakeHuman program code is AGPL-3.0 and is NOT included or used here."),
}
REDIST = ("yes", "no", "unknown")
SPDX_COMMON = ["CC0-1.0", "CC-BY-4.0", "CC-BY-SA-4.0", "CC-BY-NC-4.0", "MIT", "Apache-2.0", "LicenseRef-Proprietary",
               "LicenseRef-Mixamo-Terms", "LicenseRef-Store-EULA", "custom"]
OVERRIDE_STATEMENT = "I own the rights to this asset (or have permission) and may redistribute it in a pack."
PACK_FORMAT = "sfpack"
PACK_VERSION = 1


def libdir(d=None):
    return os.path.abspath(d or os.environ.get("SFS_LIBRARY") or os.path.join(ROOT, "library"))


def now():
    return datetime.datetime.now().replace(microsecond=0).isoformat()


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def slug(s):
    return re.sub(r"[^A-Za-z0-9_\-]+", "_", s).strip("_").lower() or "asset"


# ----------------------------------------------------------------- licences
def blank_licence(redistribution="unknown"):
    return dict(spdx="", custom_text="", author="", source_url="", redistribution=redistribution, attribution="", notes="")


def validate_licence(lic):
    """-> list of problems (empty = complete record)."""
    p = []
    if not isinstance(lic, dict):
        return ["no licence record"]
    for k in ("spdx", "custom_text", "author", "source_url", "redistribution", "attribution"):
        if k not in lic:
            p.append("missing field '%s'" % k)
    if not (lic.get("spdx") or lic.get("custom_text")):
        p.append("needs an SPDX id or custom licence text")
    if lic.get("spdx") == "custom" and not lic.get("custom_text"):
        p.append("spdx 'custom' needs custom_text")
    if lic.get("redistribution") not in REDIST:
        p.append("redistribution must be yes / no / unknown")
    if not lic.get("author"):
        p.append("author is empty")
    return p


def redistributable(lic):
    """(ok, reason).  Clips saved into an asset from a non-redistributable source ("includes") block it, override or not."""
    bad = [i for i in lic.get("includes", []) if not i.get("redistributable")]
    if bad:
        return False, "contains clips retargeted from %s (%s)" % (", ".join(i.get("from", "?") for i in bad),
                                                                    "; ".join(i.get("why", "") for i in bad))
    if lic.get("redistribution") == "yes":
        return True, "licence allows redistribution"
    ov = lic.get("rights_override") or {}
    if ov.get("by") and ov.get("statement"):
        return True, "rights confirmed by %s on %s" % (ov["by"], ov.get("date", "?"))
    return False, "redistribution = %s" % lic.get("redistribution", "unknown")


def licence_text(lic, name=""):
    out = ["%s" % name] if name else []
    out.append("  licence      : %s" % (lic.get("spdx") or ("custom" if lic.get("custom_text") else "NONE (not filled in)")))
    if lic.get("custom_text"):
        out.append("  terms        : %s" % lic["custom_text"].replace("\n", " ")[:400])
    out.append("  author       : %s" % (lic.get("author") or "?"))
    if lic.get("source_url"):
        out.append("  source       : %s" % lic["source_url"])
    out.append("  redistribute : %s" % lic.get("redistribution", "unknown"))
    if lic.get("attribution"):
        out.append("  attribution  : %s" % lic["attribution"])
    ov = lic.get("rights_override")
    if ov:
        out.append("  OVERRIDE     : %s (%s, %s)" % (ov.get("statement"), ov.get("by"), ov.get("date")))
    for i in lic.get("includes", []):
        out.append("  includes     : clips %s from %s (%s%s)" % (",".join(i.get("clips", [])), i.get("from"), i.get("spdx") or "custom",
                                                                ", attribution: " + i["attribution"] if i.get("attribution") else ""))
    if lic.get("notes"):
        out.append("  notes        : %s" % lic["notes"])
    return "\n".join(out)


def record_include(target_lic, source_name, source_lic, clips):
    """licence bookkeeping when clips from source_name are saved into another asset."""
    ok, why = redistributable(source_lic or blank_licence())
    inc = [i for i in target_lic.get("includes", []) if i.get("from") != source_name]
    prev = next((i for i in target_lic.get("includes", []) if i.get("from") == source_name), {})
    sl = source_lic or {}
    inc.append({"from": source_name, "clips": sorted(set(prev.get("clips", [])) | set(clips)), "spdx": sl.get("spdx", ""),
                "author": sl.get("author", ""), "attribution": sl.get("attribution", ""), "redistributable": bool(ok),
                "why": why, "date": now()})
    out = dict(target_lic); out["includes"] = inc
    return out


def make_prop(rig, socket):
    """rigid prop: every vertex on one bone 'prop' at the model origin (the grip point); socket recorded in meta."""
    import numpy as np
    from .rigrec import Rig
    if socket == "foot":
        socket = "foot_r"
    if socket not in SOCKETS:
        raise ValueError("socket must be one of " + ", ".join(SOCKETS))
    r = Rig(rig.name)
    r.bones = ["prop"]; r.parent = np.array([-1]); r.bind = np.eye(4)[None]
    if rig.has_mesh():
        # rest-pose (bind space) positions of the original, then all on the one bone
        r.V = rig.V.copy(); r.F = rig.F.copy()
        lo, hi = r.V.min(0), r.V.max(0)
        r.V -= np.array([(lo[0] + hi[0]) / 2, lo[1], (lo[2] + hi[2]) / 2])   # grip = bottom centre
        r.fmat = rig.fmat.copy(); r.fuv = rig.fuv; r.fcol = rig.fcol
        r.materials = rig.materials; r.textures = rig.textures
        r.J = np.zeros((len(r.V), 4), int); r.W = np.zeros((len(r.V), 4)); r.W[:, 0] = 1
    r.meta = dict(rig.meta); r.meta["prop"] = dict(socket=socket, offset=[0, 0, 0], rotation=[0, 0, 0], scale=1.0)
    return r


# ----------------------------------------------------------------- assets
class Library:
    def __init__(self, d=None):
        self.dir = libdir(d)

    def path(self, kind, name):
        return os.path.join(self.dir, kind, name + (".json" if kind == "kits" else ""))

    def ensure(self):
        for k in KINDS + ("inbox",):
            os.makedirs(os.path.join(self.dir, k), exist_ok=True)

    # ---- listing
    def names(self, kind):
        d = os.path.join(self.dir, kind)
        if not os.path.isdir(d):
            return []
        if kind == "kits":
            return sorted(os.path.splitext(f)[0] for f in os.listdir(d) if f.endswith(".json"))
        return sorted(f for f in os.listdir(d) if os.path.isfile(os.path.join(d, f, "rig.json")))

    def find(self, name):
        """-> (kind, name) for 'name' or 'rigs/name' / 'animations/name' / 'kits/name'."""
        if "/" in name:
            k, n = name.split("/", 1)
            k = KIND_ALIASES.get(k, k)
            if n in self.names(k):
                return k, n
            raise KeyError("no %s '%s' in %s" % (k, n, self.dir))
        for k in KINDS:
            if name in self.names(k):
                return k, name
        raise KeyError("no library asset '%s' in %s (forge.py library list)" % (name, self.dir))

    def all_assets(self):
        return [(k, n) for k in KINDS for n in self.names(k)]

    def load_rig(self, name):
        from .rigrec import Rig
        k, n = self.find(name)
        if k == "kits":
            raise KeyError("'%s' is a kit, not a rig" % name)
        return Rig.load(self.path(k, n))

    def bonemap(self, name, rig=None):
        from . import bonemap as BM
        k, n = self.find(name)
        p = os.path.join(self.path(k, n), "bonemap.json")
        if os.path.exists(p):
            return BM.load(p, rig)
        rig = rig or self.load_rig(name)
        return BM.detect(rig)

    def licence(self, name):
        k, n = self.find(name)
        if k == "kits":
            return json.load(open(self.path(k, n), encoding="utf-8")).get("licence", blank_licence())
        p = os.path.join(self.path(k, n), "licence.json")
        return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else blank_licence()

    def set_licence(self, name, lic):
        k, n = self.find(name)
        if k == "kits":
            p = self.path(k, n); d = json.load(open(p, encoding="utf-8")); d["licence"] = lic
            json.dump(d, open(p, "w", encoding="utf-8"), indent=1)
        else:
            json.dump(lic, open(os.path.join(self.path(k, n), "licence.json"), "w", encoding="utf-8"), indent=1)

    # ---- add / remove
    def add_file(self, src, name=None, kind=None, licence=None, log=print, orient="auto", dedupe="auto", blender=False,
                 preset=None, socket=None, hide=None, slot=None, anims_redistributable=None):
        from . import importers, bonemap as BM, rigrec as RR
        self.ensure()
        if KIND_ALIASES.get(kind, kind) == "props" and orient == "auto":
            orient = "off"            # items keep their authored axes (upright +Y, front +Z); only grounded + centred
        rig, rec, rep = importers.load_file(src, orient=orient, dedupe=dedupe, blender=blender)
        name = slug(name or os.path.splitext(os.path.basename(src))[0])
        kind = kind or ("rigs" if rig.has_mesh() else "animations")
        kind = KIND_ALIASES.get(kind, kind)
        if kind not in KINDS or kind == "kits":
            raise ValueError("kind must be rig / animation / outfit / prop")
        rig.name = name
        if preset:
            if preset not in LICENCE_PRESETS:
                raise ValueError("unknown preset '%s' (%s)" % (preset, ", ".join(LICENCE_PRESETS)))
            base = dict(LICENCE_PRESETS[preset])
            for k_, v_ in (licence or {}).items():          # anything typed explicitly wins over the preset
                if v_ not in (None, "") and not (k_ == "redistribution" and v_ == "unknown"):
                    base[k_] = v_
            licence = base
            rig.meta["source_preset"] = preset
            if preset.startswith("meshy") and rig.clips:
                ok = anims_redistributable == "yes"
                licence = dict(licence); licence["includes"] = [dict(**{"from": "meshy-animation-library"}, clips=sorted(rig.clips),
                    spdx="", author="Meshy", attribution="", redistributable=ok,
                    why=("user confirmed the Meshy animation clips may be redistributed" if ok else MESHY_ANIM_WHY), date=now())]
                rep.setdefault("warnings", []).append("Meshy animation clips (%s): redistribution %s - %s" % (
                    ", ".join(rig.clips), "YES (you confirmed)" if ok else "NO by default", "" if ok else
                    "packs refuse this asset until you drop them (library clips-drop %s from:meshy-animation-library) "
                    "or confirm with --meshy-anims-redistributable yes" % name))
        if kind == "props":
            rig = make_prop(rig, socket or "hand_r")
            rec = BM.detect(rig)
        elif kind == "outfits":
            rig.meta["outfit"] = dict(hide=list(hide or []), slot=slot or "")
            rig.clips = {}            # an outfit follows the base rig's animation; its own takes are not kept
        elif socket or hide:
            raise ValueError("--socket is for --kind prop, --hide for --kind outfit")
        rep["clips"] = list(rig.clips)
        d = self.path(kind, name)
        if os.path.exists(d):
            shutil.rmtree(d)
        self.save_rig(rig, rec, kind, licence or blank_licence(), dict(path=os.path.abspath(src), sha256=sha256_file(src),
                                                                         imported=now(), report=_jsonable(rep)))
        lic = licence or blank_licence()
        if lic.get("redistribution") != "yes":
            log("note: licence for '%s' is %s - it stays usable locally but cannot be exported in a pack until its licence "
                "is set (forge.py library licence %s --spdx ... --author ... --redistribution yes|no)" % (name, lic.get("redistribution"), name))
        return kind, name, rec, rep

    def save_rig(self, rig, rec, kind, licence, source=None):
        from . import bonemap as BM, rigrec as RR
        d = self.path(kind, rig.name)
        rig.save(d)
        BM.save(rec, os.path.join(d, "bonemap.json"))
        json.dump(licence, open(os.path.join(d, "licence.json"), "w", encoding="utf-8"), indent=1)
        if source is not None:
            json.dump(source, open(os.path.join(d, "source.json"), "w", encoding="utf-8"), indent=1)
        clip = None
        if not rig.has_mesh() and rig.clips:
            clip = list(rig.clips)[0]
        RR.thumbnail(rig, os.path.join(d, "thumb.png"), clip=clip)
        return d

    def add_kit(self, name, kit, licence=None):
        self.ensure()
        kit = dict(kit); kit["name"] = name; kit["licence"] = licence or kit.get("licence") or blank_licence()
        json.dump(kit, open(self.path("kits", name), "w", encoding="utf-8"), indent=1)

    def remove(self, name):
        k, n = self.find(name)
        p = self.path(k, n)
        if k == "kits":
            os.remove(p)
        else:
            shutil.rmtree(p)
        self.scan(import_inbox=False)
        return k, n

    # ---- manifest
    def scan(self, import_inbox=True, log=print):
        self.ensure()
        imported = []
        if import_inbox:
            ib = os.path.join(self.dir, "inbox")
            for f in sorted(os.listdir(ib)):
                if os.path.splitext(f)[1].lower() in (".fbx", ".glb", ".gltf"):
                    p = os.path.join(ib, f)
                    done = os.path.join(ib, "imported")
                    try:
                        k, n, rec, rep = self.add_file(p, log=log)
                        imported.append((k, n))
                        os.makedirs(done, exist_ok=True); shutil.move(p, os.path.join(done, f))
                    except Exception as e:
                        log("inbox: %s failed: %s" % (f, e))
        entries = []
        for k in KINDS:
            for n in self.names(k):
                entries.append(self.entry(k, n))
        man = dict(format="sforge-library", version=1, updated=now(), dir=self.dir, assets=entries)
        json.dump(man, open(os.path.join(self.dir, "library.json"), "w", encoding="utf-8"), indent=1)
        return man, imported

    def entry(self, k, n):
        if k == "kits":
            kit = json.load(open(self.path(k, n), encoding="utf-8"))
            lic = kit.get("licence", blank_licence())
            return dict(kind=k, name=n, path="kits/%s.json" % n, description=kit.get("description", ""),
                        materials=list(kit.get("materials", {})), licence=dict(spdx=lic.get("spdx"), redistribution=lic.get("redistribution")),
                        licence_ok=not validate_licence(lic))
        d = self.path(k, n)
        meta = json.load(open(os.path.join(d, "rig.json"), encoding="utf-8"))
        lic = self.licence("%s/%s" % (k, n))
        bm = {}
        if os.path.exists(os.path.join(d, "bonemap.json")):
            bm = json.load(open(os.path.join(d, "bonemap.json"), encoding="utf-8"))
        return dict(kind=k, name=n, path="%s/%s" % (k, n), bones=len(meta["bones"]), tris=meta.get("tris", 0),
                    height_m=meta.get("height_m"), clips=[c["name"] for c in meta.get("clips", [])],
                    convention=bm.get("convention"), unmapped=len(bm.get("unmapped", [])), missing=bm.get("missing", []),
                    licence=dict(spdx=lic.get("spdx") or ("custom" if lic.get("custom_text") else ""), redistribution=lic.get("redistribution"),
                                 owner_confirmed=bool(lic.get("rights_override")), redistributable=redistributable(lic)[0]),
                    licence_ok=not validate_licence(lic), description=meta.get("meta", {}).get("description", ""),
                    thumb="%s/%s/thumb.png" % (k, n))

    def manifest(self):
        p = os.path.join(self.dir, "library.json")
        if not os.path.exists(p):
            return self.scan(import_inbox=False)[0]
        return json.load(open(p, encoding="utf-8"))

    # ---- all clips from every rig / animation file: {"lib:clip": (asset, clip)}
    def clip_index(self):
        out = {}
        for k in ("rigs", "animations"):
            for n in self.names(k):
                meta = json.load(open(os.path.join(self.path(k, n), "rig.json"), encoding="utf-8"))
                for c in meta.get("clips", []):
                    out["%s:%s" % (n, c["name"])] = (n, c["name"])
        return out

    # ---- packs
    def asset_files(self, k, n):
        """-> {arcname: abspath} for one asset."""
        if k == "kits":
            return {"kits/%s.json" % n: self.path(k, n)}
        d = self.path(k, n); out = {}
        for root, _, files in os.walk(d):
            for f in files:
                if f == "source.json":
                    continue            # local paths stay local
                p = os.path.join(root, f)
                out["%s/%s/%s" % (k, n, os.path.relpath(p, d).replace(os.sep, "/"))] = p
        return out

    def pack(self, out, names=None, pack_name=None, description="", override=(), by="", log=print):
        """write a .sfpack.  Refuses assets that are not redistributable unless listed in `override` with `by`."""
        assets = self.all_assets() if not names else [self.find(n) for n in names]
        refused, rows = [], []
        for k, n in assets:
            lic = dict(self.licence("%s/%s" % (k, n)))
            probs = validate_licence(lic)
            ok, why = redistributable(lic)
            if lic.get("redistribution") != "yes" and (n in override or "%s/%s" % (k, n) in override or "*" in override):
                if not by:
                    refused.append((k, n, "the 'I own the rights' override needs your name (--by NAME)")); continue
                lic["rights_override"] = dict(by=by, date=now(), statement=OVERRIDE_STATEMENT)
                for k2 in ("spdx", "custom_text", "source_url", "attribution"):
                    lic.setdefault(k2, "")
                if not lic.get("author"):
                    lic["author"] = by
                if not (lic.get("spdx") or lic.get("custom_text")):
                    lic["spdx"] = "LicenseRef-Owner-Confirmed"
                    lic["custom_text"] = ("%s confirmed owning the rights to this asset; no other licence was given, so ask "
                                          "the owner before reusing it outside Sprite Forge Studio." % by)
                self.set_licence("%s/%s" % (k, n), lic)
                ok, why = True, "rights confirmed by %s" % by
                probs = validate_licence(lic)
                log("recorded override for %s/%s: %s (%s)" % (k, n, OVERRIDE_STATEMENT, by))
            if probs and ok:
                refused.append((k, n, "incomplete licence record: " + "; ".join(probs))); continue
            if not ok:
                hint = (" (remove those clips: forge.py library clips-drop, or fix the source's licence)" if why.startswith("contains clips")
                        else " (set the licence, or confirm you own the rights)")
                refused.append((k, n, why + hint)); continue
            rows.append((k, n, lic))
        if refused:
            msg = "\n".join("  %s/%s: %s" % r for r in refused)
            raise PermissionError("pack refused - these assets may not be redistributed:\n" + msg)
        if not rows:
            raise ValueError("nothing to pack")
        man = dict(format=PACK_FORMAT, version=PACK_VERSION, name=pack_name or os.path.splitext(os.path.basename(out))[0],
                   description=description, created=now(), tool="Sprite Forge Studio", assets=[])
        lic_txt = ["Licences of the assets in this pack (Sprite Forge Studio .sfpack)", "=" * 64, ""]
        os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
        with zipfile.ZipFile(out + ".tmp", "w", zipfile.ZIP_DEFLATED) as z:
            for k, n, lic in rows:
                files = {}
                for arc, p in sorted(self.asset_files(k, n).items()):
                    if arc.endswith("/licence.json"):
                        data = json.dumps(lic, indent=1).encode("utf-8")
                    elif k == "kits":
                        kd = json.load(open(p, encoding="utf-8")); kd["licence"] = lic
                        data = json.dumps(kd, indent=1).encode("utf-8")
                    else:
                        data = open(p, "rb").read()
                    z.writestr(arc, data); files[arc] = hashlib.sha256(data).hexdigest()
                if k != "kits":
                    th = os.path.join(self.path(k, n), "thumb.png")
                    if os.path.exists(th):
                        arc = "thumbnails/%s_%s.png" % (k, n); data = open(th, "rb").read()
                        z.writestr(arc, data); files[arc] = hashlib.sha256(data).hexdigest()
                e = self.entry(k, n)
                man["assets"].append(dict(kind=k, name=n, files=files, licence=lic,
                                          info={x: e.get(x) for x in ("bones", "tris", "height_m", "clips", "convention", "description") if x in e}))
                lic_txt += [licence_text(lic, "%s/%s" % (k, n)), ""]
            z.writestr("LICENSES.txt", "\n".join(lic_txt))
            z.writestr("pack.json", json.dumps(man, indent=1))
        os.replace(out + ".tmp", out)
        return man

    def install(self, pack, accept=False, overwrite=False, log=print, ask=None):
        rep = verify(pack)
        if not rep["ok"]:
            raise ValueError("pack failed verification:\n  " + "\n  ".join(rep["problems"]))
        man = rep["manifest"]
        log("Pack '%s' (%d assets). Licences:" % (man.get("name"), len(man["assets"])))
        for a in man["assets"]:
            log(licence_text(a["licence"], "%s/%s" % (a["kind"], a["name"])))
        if not accept:
            if ask is not None:
                accept = bool(ask(man))
            elif sys.stdin is not None and sys.stdin.isatty():
                ans = input("Type 'yes' to acknowledge these licences and install: ").strip().lower()
                accept = ans in ("yes", "y")
        if not accept:
            raise PermissionError("not installed: the licences were not acknowledged (use --accept-licences after reading them)")
        self.ensure()
        installed = []
        psha = sha256_file(pack)
        with zipfile.ZipFile(pack) as z:
            for a in man["assets"]:
                k, n = a["kind"], a["name"]
                target = n
                exists = n in self.names(k)
                if exists and not overwrite:
                    same = self._same(k, n, z, a)
                    if same:
                        log("  %s/%s already installed (identical) - skipped" % (k, n)); installed.append((k, n, "skipped")); continue
                    i = 2
                    while "%s_%d" % (n, i) in self.names(k):
                        i += 1
                    target = "%s_%d" % (n, i)
                    log("  %s/%s exists with different content -> installed as %s" % (k, n, target))
                if exists and overwrite and target == n:
                    p = self.path(k, n)
                    shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)
                for arc in a["files"]:
                    if arc.startswith("thumbnails/"):
                        continue
                    rel = arc.split("/", 2)
                    if k == "kits":
                        dst = self.path("kits", target)
                    else:
                        dst = os.path.join(self.path(k, target), rel[2])
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    with open(dst, "wb") as f:
                        f.write(z.read(arc))
                lic = dict(a["licence"])
                lic["installed_from"] = dict(pack=os.path.basename(pack), pack_sha256=psha, pack_name=man.get("name"),
                                             date=now(), licences_acknowledged=True, original_name=n)
                if k == "kits":
                    kd = json.load(open(self.path("kits", target), encoding="utf-8")); kd["licence"] = lic; kd["name"] = target
                    json.dump(kd, open(self.path("kits", target), "w", encoding="utf-8"), indent=1)
                else:
                    json.dump(lic, open(os.path.join(self.path(k, target), "licence.json"), "w", encoding="utf-8"), indent=1)
                    if target != n:
                        rj = os.path.join(self.path(k, target), "rig.json")
                        meta = json.load(open(rj, encoding="utf-8")); meta["name"] = target
                        json.dump(meta, open(rj, "w", encoding="utf-8"), indent=1)
                installed.append((k, target, "installed"))
                log("  installed %s/%s" % (k, target))
        self.scan(import_inbox=False)
        return installed

    def _same(self, k, n, z, a):
        mine = self.asset_files(k, n)
        for arc, h in a["files"].items():
            if arc.startswith("thumbnails/") or arc.endswith("licence.json") or k == "kits":
                continue
            p = mine.get(arc)
            if p is None or sha256_file(p) != h:
                return False
        return True


def verify(pack):
    """check a .sfpack: manifest, safe paths, sha256 of every file, complete licence records, redistribution."""
    probs, warn = [], []
    man = None
    try:
        z = zipfile.ZipFile(pack)
    except Exception as e:
        return dict(ok=False, problems=["not a zip: %s" % e], warnings=[], manifest=None)
    with z:
        names = set(z.namelist())
        if "pack.json" not in names:
            return dict(ok=False, problems=["pack.json missing"], warnings=[], manifest=None)
        try:
            man = json.loads(z.read("pack.json").decode("utf-8"))
        except Exception as e:
            return dict(ok=False, problems=["pack.json unreadable: %s" % e], warnings=[], manifest=None)
        if man.get("format") != PACK_FORMAT:
            probs.append("format is not 'sfpack'")
        if int(man.get("version", 0)) > PACK_VERSION:
            probs.append("pack version %s is newer than this program understands (%d)" % (man.get("version"), PACK_VERSION))
        listed = {"pack.json", "LICENSES.txt"}
        for a in man.get("assets", []):
            k, n = a.get("kind"), a.get("name", "")
            tag = "%s/%s" % (k, n)
            if k not in KINDS:
                probs.append("%s: unknown kind" % tag); continue
            if not re.match(r"^[A-Za-z0-9_\-]+$", n or ""):
                probs.append("%s: bad asset name" % tag)
            lp = validate_licence(a.get("licence"))
            if lp:
                probs.append("%s: licence record incomplete (%s)" % (tag, "; ".join(lp)))
            ok, why = redistributable(a.get("licence") or {})
            if not ok:
                probs.append("%s: not redistributable (%s)" % (tag, why))
            if not a.get("files"):
                probs.append("%s: no files" % tag)
            for arc, h in (a.get("files") or {}).items():
                listed.add(arc)
                if arc.startswith("/") or ".." in arc.split("/") or "\\" in arc or ":" in arc:
                    probs.append("%s: unsafe path %s" % (tag, arc)); continue
                if not (arc.startswith("%s/%s" % (k, n)) or arc.startswith("thumbnails/")):
                    probs.append("%s: file outside its folder: %s" % (tag, arc)); continue
                if arc not in names:
                    probs.append("%s: missing file %s" % (tag, arc)); continue
                if hashlib.sha256(z.read(arc)).hexdigest() != h:
                    probs.append("%s: checksum mismatch %s" % (tag, arc))
            if k != "kits" and not any(x.endswith("/rig.json") for x in a.get("files", {})):
                probs.append("%s: rig.json missing" % tag)
        extra = sorted(n for n in names if n not in listed and not n.endswith("/"))
        if extra:
            warn.append("unlisted files ignored: %s" % ", ".join(extra[:10]))
    return dict(ok=not probs, problems=probs, warnings=warn, manifest=man)


def _jsonable(o):
    if isinstance(o, dict):
        return {str(k): _jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_jsonable(v) for v in o]
    if hasattr(o, "item"):
        return o.item()
    return o

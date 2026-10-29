"""forge.py library ... / forge.py retarget ...   (v6 user library of FBX / GLB rigs and animations)"""
from __future__ import annotations
import argparse
import json
import os
import sys

from . import library as L


def _lic_args(p):
    g = p.add_argument_group("licence record (mandatory for packs)")
    g.add_argument("--spdx", help="SPDX id, e.g. CC0-1.0, CC-BY-4.0, MIT, LicenseRef-Proprietary (or 'custom' + --custom-text)")
    g.add_argument("--custom-text", dest="custom_text", help="licence terms in your words (when there is no SPDX id)")
    g.add_argument("--author"); g.add_argument("--source-url", dest="source_url")
    g.add_argument("--redistribution", choices=list(L.REDIST), help="may this asset be shared in a pack? yes / no / unknown")
    g.add_argument("--attribution", help="credit line required by the licence")
    g.add_argument("--notes")


def _lic_from(a, base=None):
    lic = dict(base or L.blank_licence())
    for k in ("spdx", "custom_text", "author", "source_url", "redistribution", "attribution", "notes"):
        v = getattr(a, k, None)
        if v is not None:
            lic[k] = v
    return lic


def _print_entry(e):
    if e["kind"] == "kits":
        print("  %-22s kit  %s  [%s, redistribute=%s]" % (e["name"], ", ".join(e["materials"])[:40], e["licence"]["spdx"] or "?", e["licence"]["redistribution"]))
        return
    print("  %-22s %-9s %3d bones %6d tris %4.2f m  %-7s clips: %s  [%s, redistribute=%s]%s" % (
        e["name"], e["kind"][:-1], e["bones"], e["tris"], e["height_m"] or 0, e["convention"] or "?", ", ".join(e["clips"]) or "-",
        e["licence"]["spdx"] or "?", e["licence"]["redistribution"], "" if e["licence_ok"] else "  (licence incomplete)"))


def main(argv):
    p = argparse.ArgumentParser(prog="forge.py library", description="user library of rigs, animations and kits (FBX / GLB) + .sfpack packs")
    p.add_argument("--library", help="library folder (default <studio>/library or $SFS_LIBRARY)")
    sub = p.add_subparsers(dest="act")
    ls = sub.add_parser("list", help="list assets"); ls.add_argument("--json", action="store_true")
    sh = sub.add_parser("show", help="details: bones + canonical map, clips, licence"); sh.add_argument("name")
    ad = sub.add_parser("add", help="import an FBX / GLB / glTF into the library (the source file is not copied or changed)")
    ad.add_argument("file", help=".fbx / .glb / .gltf / .obj, or a .zip holding one (Meshy / Sketchfab downloads: FBX + textures)")
    ad.add_argument("--name"); ad.add_argument("--kind", choices=["rig", "animation", "outfit", "prop"],
                                               help="rig / animation, or v7: outfit (skinned clothing / armour on the same skeleton) / prop (rigid, attached to a socket)")
    _lic_args(ad)
    g7 = ad.add_argument_group("v7 import options")
    g7.add_argument("--preset", choices=sorted(L.LICENCE_PRESETS), help="pre-fill the licence: meshy-free (CC BY 4.0 + attribution), meshy-paid (private, redistribution no), makehuman (CC0)")
    g7.add_argument("--meshy-anims-redistributable", dest="anims_redist", choices=["yes", "no"], default="no",
                    help="Meshy animation-library clips inside the file: may they be shared in a pack? (default no - unclear terms)")
    g7.add_argument("--orient", choices=["auto", "off"], default="auto", help="auto (default): stand the rig and its clips upright (+Y), face +Z, metres, grounded")
    g7.add_argument("--dedupe", choices=["auto", "off"], default="auto", help="auto (default): remove duplicate / .001 / lower-LOD copies of a mesh (listed in the report)")
    g7.add_argument("--blender-cleanup", dest="blender_cleanup", action="store_true", help="optional: run Blender first (apply transforms, drop duplicates); needs Blender or pip bpy")
    g7.add_argument("--socket", choices=list(L.SOCKETS), help="prop: where it attaches (default hand_r)")
    g7.add_argument("--hide", help="outfit: body regions hidden under it, comma list of: torso,hips,neck,head,shoulders,upperarms,forearms,hands,thighs,shins,feet (or arms,legs,body)")
    g7.add_argument("--slot", help="outfit: material slot its colour follows (e.g. Jersey_Mat); default = its own materials")
    sub.add_parser("scan", help="rebuild library.json; imports files dropped in library/inbox/")
    rm = sub.add_parser("remove", help="remove an asset from the library"); rm.add_argument("name")
    li = sub.add_parser("licence", aliases=["license"], help="show or edit an asset's licence record"); li.add_argument("name"); _lic_args(li)
    bm = sub.add_parser("bonemap", help="show / edit the canonical bone map (bonemap.json)")
    bm.add_argument("name"); bm.add_argument("--set", action="append", metavar="CANON=BONE", help="e.g. --set hand_L=mixamorig:LeftHand")
    bm.add_argument("--unset", action="append", metavar="CANON"); bm.add_argument("--auto", action="store_true", help="re-detect from scratch")
    ex = sub.add_parser("export", help="write an asset as GLB or FBX (our writer), every clip a take")
    ex.add_argument("name"); ex.add_argument("out"); ex.add_argument("--clips", help="comma list (default all)")
    ex.add_argument("--kit"); ex.add_argument("--root-motion", dest="root_motion", choices=["keep", "inplace", "root"], default="keep")
    ex.add_argument("--material-split", dest="material_split", choices=["auto", "off"], default="auto")
    ex.add_argument("--material-slots", dest="material_slots", choices=["full", "core4", "keep"], default="full")
    pk = sub.add_parser("pack", help="export assets as a shareable .sfpack (refuses non-redistributable assets)")
    pk.add_argument("out"); pk.add_argument("names", nargs="*"); pk.add_argument("--all", action="store_true")
    pk.add_argument("--pack-name", dest="pack_name"); pk.add_argument("--description", default="")
    pk.add_argument("--i-own-the-rights", dest="own", metavar="NAMES", help="comma list of assets you confirm you own the rights to (recorded in their licence)")
    pk.add_argument("--by", default="", help="your name, recorded with the 'I own the rights' confirmation")
    ins = sub.add_parser("install", help="install a .sfpack (shows every licence; needs acknowledgement)")
    ins.add_argument("pack"); ins.add_argument("--accept-licences", "--accept-licenses", dest="accept", action="store_true",
                                               help="I have read the licences printed above and accept them")
    ins.add_argument("--overwrite", action="store_true", help="replace assets with the same name (default: keep both, rename)")
    ve = sub.add_parser("verify", help="check a .sfpack: checksums, safe paths, licence records"); ve.add_argument("pack")
    cd = sub.add_parser("clips-drop", help="delete clips from an asset (also clears their licence 'includes' entries)")
    cd.add_argument("name"); cd.add_argument("clips", help="comma list, or 'from:SOURCE' = every clip saved from SOURCE")
    th = sub.add_parser("thumb", help="re-render an asset's thumbnail"); th.add_argument("name"); th.add_argument("--clip"); th.add_argument("--kit")
    a = p.parse_args(argv)
    lib = L.Library(a.library)
    try:
        return _run(a, lib, p)
    except (KeyError, ValueError, PermissionError, FileNotFoundError) as e:
        print("error:", e.args[0] if e.args else e)
        return 2


def _run(a, lib, p):
    if a.act in (None, "list"):
        man = lib.manifest()
        if getattr(a, "json", False):
            print(json.dumps(man, indent=1)); return 0
        print("library: %s  (%d assets)" % (lib.dir, len(man["assets"])))
        for e in man["assets"]:
            _print_entry(e)
        if not man["assets"]:
            print("  (empty) - forge.py library add FILE.fbx | install packs/sfs_starter_cc0.sfpack")
        return 0
    if a.act == "scan":
        man, imp = lib.scan()
        print("library.json: %d assets%s" % (len(man["assets"]), (" (imported from inbox: %s)" % ", ".join(n for _, n in imp)) if imp else ""))
        return 0
    if a.act == "add":
        lic = _lic_from(a)
        k, n, rec, rep = lib.add_file(a.file, a.name, a.kind, lic, orient=a.orient, dedupe=a.dedupe, blender=a.blender_cleanup,
                                      preset=a.preset, socket=a.socket, hide=[x.strip() for x in a.hide.split(",")] if a.hide else None,
                                      slot=a.slot, anims_redistributable=a.anims_redist)
        lib.scan(import_inbox=False)
        cu = rep.get("cleanup", {})
        for d in cu.get("blender", {}).get("removed", []):
            print("  Blender clean-up removed duplicate mesh '%s' (copy of '%s')" % (d["name"], d["duplicate_of"]))
        for d in cu.get("blender", {}).get("applied", []):
            print("  Blender clean-up applied rotation/scale on '%s'" % d)
        for d in cu.get("dedupe", {}).get("removed", []):
            print("  removed duplicate mesh '%s' (%d faces): %s" % (d["name"], d["faces"], d["reason"]))
        for f in rep.get("fixes", []):
            print("  orientation:", f)
        for c in cu.get("orientation", {}).get("clips_fixed", []):
            print("  orientation: clip '%s' was lying flat (up %s) - rotated upright" % (c["clip"], c["up_was"]))
        if rep.get("zip"):
            print("  zip: read %s" % rep["zip"]["model"])
        print("added %s/%s: %s naming, %d mapped bones, unmapped: %s, missing: %s, %.2f m, clips: %s" % (
            k, n, rec["convention"], len(rec["map"]), ", ".join(rec["unmapped"][:8]) or "none", ", ".join(rec["missing"]) or "none",
            rep.get("height_m", 0), ", ".join(rep.get("clips", [])) or "-"))
        for w in rep.get("warnings", []):
            print("  warning:", w)
        return 0
    if a.act == "remove":
        k, n = lib.remove(a.name); print("removed %s/%s (your original source file is untouched)" % (k, n)); return 0
    if a.act in ("licence", "license"):
        lic = lib.licence(a.name)
        if any(getattr(a, k) is not None for k in ("spdx", "custom_text", "author", "source_url", "redistribution", "attribution", "notes")):
            lic = _lic_from(a, lic); lib.set_licence(a.name, lic); lib.scan(import_inbox=False)
        print(L.licence_text(lic, a.name))
        probs = L.validate_licence(lic)
        print("  record: %s" % ("complete" if not probs else "INCOMPLETE - " + "; ".join(probs)))
        return 0
    if a.act == "show":
        k, n = lib.find(a.name)
        if k == "kits":
            print(json.dumps(json.load(open(lib.path(k, n), encoding="utf-8")), indent=1)); return 0
        r = lib.load_rig(a.name); rec = lib.bonemap(a.name, r)
        inv = {v: c for c, v in rec["map"].items()}
        print("%s/%s  %d bones, %d verts, %d tris, %.3f m tall, naming: %s" % (k, n, r.nb, len(r.V), len(r.F), r.height(), rec["convention"]))
        def dfs(i, d, acc):
            acc.append((i, d))
            for c in r.children(i):
                dfs(c, d + 1, acc)
            return acc
        rows = []
        for i in range(r.nb):
            if r.parent[i] < 0:
                dfs(i, 0, rows)
        for i, d in rows:
            print("  %s%-30s %s" % ("  " * min(d, 12), r.bones[i], ("-> " + inv[r.bones[i]]) if r.bones[i] in inv else "(unmapped)"))
        print("missing canonical bones:", ", ".join(rec["missing"]) or "none")
        print("materials:", ", ".join("%s%s" % (m["name"], " (texture)" if m.get("texture") else "") for m in r.materials) or "-")
        for c in r.clips.values():
            print("  clip %-14s %3d frames  %.2fs  %s  %s" % (c.name, c.frames, c.duration, "loop" if c.loop else "once", c.source))
        print(L.licence_text(lib.licence(a.name), "licence"))
        return 0
    if a.act == "bonemap":
        from . import bonemap as BM
        k, n = lib.find(a.name)
        r = lib.load_rig(a.name)
        rec = BM.detect(r) if a.auto else lib.bonemap(a.name, r)
        changed = a.auto
        for kv in a.set or []:
            c, _, b = kv.partition("=")
            if c not in BM.CANON:
                print("unknown canonical name %s (choose: %s)" % (c, ", ".join(BM.CANON))); return 2
            if b not in r.bones:
                print("rig has no bone %r" % b); return 2
            rec["map"][c] = b; changed = True
        for c in a.unset or []:
            rec["map"].pop(c, None); changed = True
        if changed:
            rec = BM.make_record(r, rec["convention"], rec["map"], edited=not a.auto)
            BM.save(rec, os.path.join(lib.path(k, n), "bonemap.json")); lib.scan(import_inbox=False)
        for c in BM.CANON:
            print("  %-13s %s" % (c, rec["map"].get(c, "-")))
        print("unmapped bones:", ", ".join(rec["unmapped"]) or "none")
        print("missing (required):", ", ".join(rec["missing"]) or "none", "  edited by hand" if rec.get("edited") else "")
        return 0
    if a.act == "export":
        from . import rigrec as RR, kits as K
        r = lib.load_rig(a.name)
        clips = [c.strip() for c in a.clips.split(",")] if a.clips else list(r.clips)
        kit = K.load(a.kit, lib.dir) if a.kit else None
        if a.material_slots != "keep" and r.has_mesh():
            from . import matslots
            r, srep = matslots.apply(r, lib.bonemap(a.name, r), a.material_split, a.material_slots)
            print("material slots:", ", ".join(srep["materials"]))
        glb = a.out if a.out.lower().endswith(".glb") else os.path.splitext(a.out)[0] + ".tmp.glb"
        RR.write_glb(r, glb, clips, kit, root_motion=a.root_motion)
        if a.out.lower().endswith(".fbx"):
            from . import fbx as F
            st = F.write_fbx_from_glb(glb, a.out); os.remove(glb)
            print("wrote %s (%d bones, %d takes, built-in FBX writer)" % (a.out, st["bones"], len(st["takes"])))
        else:
            print("wrote %s (%d takes)" % (a.out, len(clips)))
        return 0
    if a.act == "pack":
        names = None if (a.all or not a.names) else a.names
        own = [x.strip() for x in (a.own or "").split(",") if x.strip()]
        man = lib.pack(a.out, names, a.pack_name, a.description, override=own, by=a.by)
        print("wrote %s: %d assets, %d KB" % (a.out, len(man["assets"]), os.path.getsize(a.out) // 1024))
        for x in man["assets"]:
            print("  %s/%s  [%s]" % (x["kind"], x["name"], x["licence"].get("spdx") or "custom"))
        return 0
    if a.act == "verify":
        rep = L.verify(a.pack)
        man = rep["manifest"] or {}
        print("%s: %s  (%d assets)" % (a.pack, "OK" if rep["ok"] else "FAILED", len(man.get("assets", []))))
        for x in man.get("assets", []):
            print(L.licence_text(x["licence"], "%s/%s" % (x["kind"], x["name"])))
        for pr in rep["problems"]:
            print("  problem:", pr)
        for w in rep["warnings"]:
            print("  warning:", w)
        return 0 if rep["ok"] else 1
    if a.act == "install":
        done = lib.install(a.pack, accept=a.accept, overwrite=a.overwrite)
        print("installed %d / %d assets into %s" % (sum(1 for d in done if d[2] == "installed"), len(done), lib.dir))
        return 0
    if a.act == "clips-drop":
        k, n = lib.find(a.name); r = lib.load_rig(a.name); lic = lib.licence(a.name)
        if a.clips.startswith("from:"):
            src = a.clips[5:]
            drop = [c for i in lic.get("includes", []) if i.get("from") == src for c in i.get("clips", [])]
        else:
            drop = [c.strip() for c in a.clips.split(",") if c.strip()]
        gone = [c for c in drop if r.clips.pop(c, None) is not None]
        inc = []
        for i in lic.get("includes", []):
            i = dict(i); i["clips"] = [c for c in i.get("clips", []) if c not in drop]
            if i["clips"]:
                inc.append(i)
        lic = dict(lic); lic["includes"] = inc
        r.save(lib.path(k, n)); lib.set_licence(a.name, lic); lib.scan(import_inbox=False)
        print("removed %d clip(s) from %s/%s: %s" % (len(gone), k, n, ", ".join(gone) or "-"))
        print(L.licence_text(lic, "%s/%s" % (k, n)))
        return 0
    if a.act == "thumb":
        from . import rigrec as RR, kits as K
        k, n = lib.find(a.name); r = lib.load_rig(a.name)
        RR.thumbnail(r, os.path.join(lib.path(k, n), "thumb.png"), clip=a.clip, kit=K.load(a.kit, lib.dir) if a.kit else None)
        print("thumbnail updated"); return 0
    p.print_help(); return 2


def retarget_main(argv):
    p = argparse.ArgumentParser(prog="forge.py retarget", description="apply clips from one library asset (or FBX / GLB file) to another rig")
    p.add_argument("source", help="SOURCE[:clip1,clip2]  library name or .fbx/.glb path (default: all clips)")
    p.add_argument("target", help="target rig: library name or .fbx/.glb path")
    p.add_argument("--out", help="write the target with the retargeted clips as .glb or .fbx")
    p.add_argument("--root-motion", dest="root_motion", choices=["keep", "inplace", "root"], default="keep",
                   help="keep = hips travel (scaled by leg length); inplace = remove horizontal travel; root = travel moved to the root bone")
    p.add_argument("--save", action="store_true", help="add the clips to the target rig in the library")
    p.add_argument("--prefix", default="", help="name prefix for the new clips (e.g. 'mx_')")
    p.add_argument("--library")
    a = p.parse_args(argv)
    from . import importers, retarget as RT, rigrec as RR
    lib = L.Library(a.library)

    def get(n):
        if os.path.isfile(n):
            r, rec, _ = importers.load_file(n); return r, rec, None
        return lib.load_rig(n), lib.bonemap(n), n
    src_name, _, clips = a.source.partition(":") if not os.path.isfile(a.source) else (a.source, "", "")
    if os.path.isfile(a.source.rsplit(":", 1)[0]) and ":" in a.source:
        src_name, clips = a.source.rsplit(":", 1)
    try:
        S, srec, _ = get(src_name); T, trec, tname = get(a.target)
    except (KeyError, ValueError) as e:
        print("error:", e); return 2
    names = [c.strip() for c in clips.split(",") if c.strip()] or list(S.clips)
    if not names:
        print("source has no animation clips"); return 2
    for c in names:
        if c not in S.clips:
            print("source has no clip %r (has: %s)" % (c, ", ".join(S.clips))); return 2
        cl, rep = RT.retarget(S, srec, c, T, trec, root_motion=a.root_motion, name=a.prefix + c)
        T.clips[a.prefix + c] = cl
        print("  %-16s -> %-16s %3d frames  leg ratio %.3f  bone-direction error mean %.2f / max %.2f deg  (%d common bones)" % (
            c, a.prefix + c, cl.frames, rep["leg_ratio"], rep["mean_dir_err_deg"], rep["max_dir_err_deg"], rep["common_bones"]))
        if rep.get("target_unmapped"):
            pass
    if a.out:
        glb = a.out if a.out.lower().endswith(".glb") else os.path.splitext(a.out)[0] + ".tmp.glb"
        RR.write_glb(T, glb, [a.prefix + c for c in names], root_motion=a.root_motion)
        if a.out.lower().endswith(".fbx"):
            from . import fbx as F
            F.write_fbx_from_glb(glb, a.out); os.remove(glb)
        print("wrote", a.out)
    if a.save:
        if not tname:
            print("--save needs a library target (add the file first: forge.py library add)"); return 2
        k, n = lib.find(tname)
        T.save(lib.path(k, n))
        src_lic = lib.licence(src_name) if not os.path.isfile(src_name) else None     # a raw file: licence unknown
        if src_name != tname:
            new = L.record_include(lib.licence(tname), src_name if not os.path.isfile(src_name) else os.path.basename(src_name),
                                   src_lic, [a.prefix + c for c in names])
            lib.set_licence(tname, new)
            ok, why = L.redistributable(new)
            if not ok:
                print("note: %s/%s now contains clips from a source that may not be redistributed -> it stays local (%s)" % (k, n, why))
        lib.scan(import_inbox=False)
        print("saved %d clips into %s/%s" % (len(names), k, n))
    return 0

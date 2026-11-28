#!/usr/bin/env python3
"""Arena FC graphics benchmark: how close the look is to an FC 25-class game, and whether a change
made it worse.

    python3 Tools/graphics_benchmark.py measure --shots DIR --glb Data/models/soccer_player.glb --out graphics.json
    python3 Tools/graphics_benchmark.py compare --head head.json [--base base.json] \
        [--targets Tools/graphics_targets.json] [--summary FILE] [--out result.json]

measure
  * the player model (straight from the GLB): triangles per player, skeleton joints, facial
    blend shapes, how many materials have normal / roughness maps, texture sizes, textured kits,
    number of distinct faces;
  * each shot from Tools/graphics_shots.sh (PNG + --graphics-report JSON): renderer, anti-aliasing,
    shadows, lighting features, draw calls, players' height on screen, and image measures:
    edge anti-aliasing, fine detail, dynamic range, clipping, colourfulness, grass colour.

compare
  Each metric with an 'fc' target shows the gap to an FC 25-class game.  Those targets are
  estimates of what current console football games ship (EA does not publish exact numbers), so
  they say "how far off", not "exactly where FIFA is".  A change fails if any metric gets worse
  than the base by more than its tolerance.  Exits 1 on a regression.
Needs numpy and Pillow.
"""
import argparse
import glob
import json
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


# --------------------------------------------------------------------------- the model (GLB)
def read_glb(path):
    b = open(path, "rb").read()
    n = struct.unpack("<I", b[12:16])[0]
    j = json.loads(b[20:20 + n])
    off = 20 + n
    binlen = struct.unpack("<I", b[off:off + 4])[0]
    return j, b[off + 8:off + 8 + binlen]


def image_size(data):
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return struct.unpack(">II", data[16:24])
    if data[:2] == b"\xff\xd8":
        i = 2
        while i < len(data) - 9:
            if data[i] != 0xFF:
                i += 1
                continue
            m = data[i + 1]
            if m in (0xC0, 0xC1, 0xC2):
                h, w = struct.unpack(">HH", data[i + 5:i + 9])
                return w, h
            seg = struct.unpack(">H", data[i + 2:i + 4])[0]
            i += 2 + seg
    return 0, 0


def audit_model(glb):
    j, binary = read_glb(glb)
    acc, bv = j["accessors"], j.get("bufferViews", [])
    ident_tris = {}
    morph = 0
    for m in j.get("meshes", []):
        name = m.get("name", "")
        mm = re.match(r"v(\d+)_", name)
        if not mm or re.search(r"lod[1-9]", name, re.I):
            continue
        tris = sum(acc[p["indices"]]["count"] // 3 for p in m["primitives"] if "indices" in p)
        ident_tris[mm.group(1)] = ident_tris.get(mm.group(1), 0) + tris
        for p in m["primitives"]:
            morph = max(morph, len(p.get("targets", [])))
    joints = max((len(s["joints"]) for s in j.get("skins", [])), default=0)
    mats = j.get("materials", [])
    player_mats = [x for x in mats if not re.search(r"lashes|brows|eye", x.get("name", ""), re.I)]
    normal = sum(1 for x in player_mats if "normalTexture" in x)
    rough = sum(1 for x in player_mats if "metallicRoughnessTexture" in x.get("pbrMetallicRoughness", {}))
    kit = [x for x in mats if re.match(r"(jersey|shorts|socks|boots|sleeves|gloves)", x.get("name", ""))]
    kit_tex = sum(1 for x in kit if "baseColorTexture" in x.get("pbrMetallicRoughness", {}))
    skin_px = []
    for im in j.get("images", []):
        if "bufferView" not in im:
            continue
        v = bv[im["bufferView"]]
        data = binary[v.get("byteOffset", 0):v.get("byteOffset", 0) + v["byteLength"]]
        w, h = image_size(data)
        if re.match(r"skin", im.get("name", ""), re.I):
            skin_px.append(max(w, h))
    tris = sorted(ident_tris.values())
    return {
        "player_tris_lod0_median": tris[len(tris) // 2] if tris else 0,
        "skeleton_joints": joints,
        "facial_blend_shapes": morph,
        "normal_mapped_materials_pct": round(100.0 * normal / max(1, len(player_mats)), 1),
        "roughness_mapped_materials_pct": round(100.0 * rough / max(1, len(player_mats)), 1),
        "kit_textured_materials_pct": round(100.0 * kit_tex / max(1, len(kit)), 1),
        "skin_texture_px_median": sorted(skin_px)[len(skin_px) // 2] if skin_px else 0,
        "distinct_faces": len(ident_tris),
    }


# --------------------------------------------------------------------------- the pictures
def image_metrics(png):
    import numpy as np
    from PIL import Image
    a = np.asarray(Image.open(png).convert("RGB")).astype(np.float32)
    H, W, _ = a.shape
    a = a[int(H * .06):int(H * .94), int(W * .03):int(W * .97)]   # leave out the HUD bars
    R, G, B = a[..., 0], a[..., 1], a[..., 2]
    lum = .299 * R + .587 * G + .114 * B
    # fine detail: variance of the Laplacian
    lap = (-4 * lum[1:-1, 1:-1] + lum[:-2, 1:-1] + lum[2:, 1:-1] + lum[1:-1, :-2] + lum[1:-1, 2:])
    detail = float(lap.var())
    # anti-aliasing: on strong edges, how often the edge pixel sits between its neighbours'
    # extremes (smoothed) rather than at one of them (a hard staircase)
    gx = np.abs(lum[1:-1, 2:] - lum[1:-1, :-2]); gy = np.abs(lum[2:, 1:-1] - lum[:-2, 1:-1])
    edge = np.maximum(gx, gy) > 60
    nb = np.stack([lum[:-2, 1:-1], lum[2:, 1:-1], lum[1:-1, :-2], lum[1:-1, 2:]])
    lo, hi = nb.min(0), nb.max(0)
    c = lum[1:-1, 1:-1]
    span = np.maximum(hi - lo, 1)
    mid = ((c - lo) / span > .15) & ((hi - c) / span > .15)
    aa = float(mid[edge].mean()) if edge.any() else 0.0
    p1, p99 = np.percentile(lum, [1, 99])
    clipped = float(((lum > 250) | (lum < 4)).mean())
    rg, yb = R - G, .5 * (R + G) - B
    colourful = float(np.sqrt(rg.std() ** 2 + yb.std() ** 2) + .3 * np.sqrt(rg.mean() ** 2 + yb.mean() ** 2))
    grass = (G > R + 12) & (G > B + 12)
    out = dict(detail=round(detail, 2), aa_edge_smoothness=round(aa, 4), dynamic_range=round(float(p99 - p1), 1),
               clipped_pct=round(clipped * 100, 3), colourfulness=round(colourful, 2), grass_pct=round(float(grass.mean()) * 100, 1))
    if grass.sum() > 1000:
        mx, mn = a.max(-1), a.min(-1)
        sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1), 0)
        out["grass_saturation"] = round(float(sat[grass].mean()), 3)
        out["grass_brightness"] = round(float(lum[grass].mean()), 1)
    return out


def measure(a):
    res = {"model": audit_model(a.glb), "shots": {}}
    for png in sorted(glob.glob(os.path.join(a.shots, "*.png"))):
        name = os.path.splitext(os.path.basename(png))[0]
        rep = os.path.join(a.shots, name + ".json")
        shot = {"image": image_metrics(png)}
        if os.path.exists(rep):
            shot["render"] = json.load(open(rep))
        res["shots"][name] = shot
    json.dump(res, open(a.out, "w"), indent=1)
    print(json.dumps(res, indent=1))
    return 0


# --------------------------------------------------------------------------- compare
def lookup(d, dotted):
    for k in dotted.split("."):
        if not isinstance(d, dict) or k not in d:
            return None
        d = d[k]
    if isinstance(d, bool):
        return 1.0 if d else 0.0
    return d


def compare(a):
    T = json.load(open(a.targets))
    head = json.load(open(a.head))
    base = json.load(open(a.base)) if a.base and os.path.exists(a.base) else None
    fails, rows = [], []
    renderer = lookup(head, "shots.broadcast.render.renderer") or "?"
    lines = ["## Graphics benchmark: %s", "",
             "Shots rendered with **%s** on the CI runner (no GPU: this is the web/mobile renderer; the desktop "
             "Forward+ look needs a GPU run). FC targets are estimates of an FC 25-class game." % renderer, ""]
    for section, metrics in T["metrics"].items():
        lines += ["### " + section, "", "| | measure | FC-class target | base | this change | gap |", "|---|---|---|---|---|---|"]
        for key, rule in metrics.items():
            h = lookup(head, key)
            if h is None:
                continue
            b = lookup(base, key) if base else None
            higher = rule.get("higher_is_better", True)
            tol = rule.get("tolerance", 0)
            tolr = rule.get("tolerance_pct", 0) / 100.0
            worse = False
            if b is not None:
                allow = max(tol, abs(b) * tolr)
                worse = (h < b - allow) if higher else (h > b + allow)
            if worse:
                fails.append(rule.get("label", key))
            fc = rule.get("fc")
            if fc is None:
                gap, status = "", ("❌" if worse else "✅")
            else:
                met = h >= fc if higher else h <= fc
                gap = "meets" if met else ("%.0f%% of target" % (100.0 * h / fc) if higher and fc else "above target")
                status = "❌" if worse else ("✅" if met else "🟡")
            fmt = lambda v: "n/a" if v is None else ("%g" % round(v, 3))
            lines.append("| %s | %s | %s | %s | %s | %s |" % (status, rule.get("label", key),
                                                              "" if fc is None else ("%s%g" % ("≥ " if higher else "≤ ", fc)),
                                                              fmt(b), fmt(h), gap))
            rows.append(dict(key=key, base=b, head=h, fc=fc, worse=worse))
        lines.append("")
    lines[0] = lines[0] % ("no regressions" if not fails else "%d regression(s): %s" % (len(fails), ", ".join(fails)))
    lines += ["🟡 = short of an FC 25-class game but no worse than the base. ❌ = worse than the base."]
    text = "\n".join(lines) + "\n"
    print(text)
    if a.summary:
        open(a.summary, "a").write(text)
    if a.out:
        json.dump(dict(passed=not fails, fails=fails, rows=rows), open(a.out, "w"), indent=1)
    return 1 if fails else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("measure")
    m.add_argument("--shots", required=True)
    m.add_argument("--glb", required=True)
    m.add_argument("--out", required=True)
    c = sub.add_parser("compare")
    c.add_argument("--head", required=True)
    c.add_argument("--base")
    c.add_argument("--targets", default=os.path.join(HERE, "graphics_targets.json"))
    c.add_argument("--summary")
    c.add_argument("--out")
    a = ap.parse_args(argv)
    return measure(a) if a.cmd == "measure" else compare(a)


if __name__ == "__main__":
    sys.exit(main())

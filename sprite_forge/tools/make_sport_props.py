"""v11.26: generate the CC0 sport props into a library.   python tools/make_sport_props.py [LIBRARY_DIR]

props/sport_hurley        hurley (camán)   - hand_r: ash handle with a grip, the bas (blade) widening to the toe and a
                                             metal band on it; held by the handle end, the bas reaching forward / down
props/sport_hurl_helmet   hurling helmet   - head (fit to the head width): shell and a face guard of bars
Built from boxes and prisms by this script: no third-party content (CC0-1.0). The hurling game pack equips both
(game_packs/hurling.json "equip"), so a rig, a capture or a roster look holds a hurley and wears a helmet in every
move, in the sprites and in model.glb / model.fbx.
"""
import os
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "tools"))
from sforge import rigrec as RR, library as L   # noqa: E402
from make_equip_samples import box, prism, static_rig   # noqa: E402

CC0 = dict(spdx="CC0-1.0", custom_text="", author="Sprite Forge Studio (procedurally generated)", source_url="",
           redistribution="yes", attribution="", notes="Sport prop made by tools/make_sport_props.py; no third-party content.")
ASH, GRIP, BAND, SHELL, BARS = (0.80, 0.66, 0.44), (0.12, 0.12, 0.13), (0.62, 0.64, 0.68), (0.10, 0.10, 0.12), (0.78, 0.80, 0.84)


def hurley_parts(length=0.86):
    """upright (+Y) from the grip at the origin; the bas bends forward (+Z) at the toe"""
    hV, hF = box((-0.016, 0.0, -0.011), (0.016, length * 0.62, 0.011))                 # handle
    gV, gF = box((-0.019, 0.0, -0.014), (0.019, 0.20, 0.014))                         # grip tape
    # the bas: a flat blade widening and curving forward over the last 38 %
    n = 6
    y0 = length * 0.60
    V, F = [], []
    for i in range(n + 1):
        t = i / float(n)
        y = y0 + t * (length - y0)
        w = 0.022 + 0.045 * t ** 0.8                                                      # half-width in z (the face)
        z0 = 0.06 * t ** 2                                                                  # the toe curls forward
        V += [[-0.011, y, z0 - w * 0.6], [0.011, y, z0 - w * 0.6], [0.011, y, z0 + w], [-0.011, y, z0 + w]]
    for i in range(n):
        a = 4 * i; b = a + 4
        for k in range(4):
            k1 = (k + 1) % 4
            F += [[a + k, b + k, b + k1], [a + k, b + k1, a + k1]]
    F += [[0, 1, 2], [0, 2, 3], [4 * n, 4 * n + 2, 4 * n + 1], [4 * n, 4 * n + 3, 4 * n + 2]]
    bV, bF = np.array(V, float), np.array(F)
    yb = y0 + 0.55 * (length - y0)
    zc = 0.06 * 0.55 ** 2
    kV, kF = box((-0.013, yb - 0.008, zc - 0.04), (0.013, yb + 0.008, zc + 0.06))     # the metal band on the bas
    return [(hV, hF, "Handle", ASH), (gV, gF, "Grip", GRIP), (bV, bF, "Bas", ASH), (kV, kF, "Band", BAND)]


def dome(n, rings, rx, rz, y0, h):
    """an elliptical dome (open at the bottom): rx across, rz front-back, from y0 up by h"""
    V, F = [], []
    for k in range(rings + 1):
        ph = 0.5 * np.pi * k / rings
        for i in range(n):
            a = 2 * np.pi * i / n
            V.append([rx * np.cos(ph) * np.cos(a), y0 + h * np.sin(ph), rz * np.cos(ph) * np.sin(a)])
    for k in range(rings):
        for i in range(n):
            j = (i + 1) % n
            a, b, c, d = k * n + i, k * n + j, (k + 1) * n + j, (k + 1) * n + i
            F += [[a, c, b], [a, d, c]]
    return np.array(V, float), np.array(F)


def helmet_parts():
    """crown at the origin (the head socket is near the top of the head); front +Z"""
    sV, sF = dome(18, 6, 0.100, 0.118, -0.10, 0.075)                                       # shell: a rounded dome
    rV, rF = prism(18, 0.106, -0.112, -0.098)                                             # rim
    rV[:, 2] *= 0.118 / 0.100
    bars = []
    for x in (-0.055, -0.018, 0.018, 0.055):                                              # vertical bars of the guard
        bars.append(box((x - 0.004, -0.205, 0.105), (x + 0.004, -0.08, 0.113)))
    for y in (-0.185, -0.15, -0.115):                                                     # cross bars
        bars.append(box((-0.07, y - 0.004, 0.103), (0.07, y + 0.004, 0.115)))
    for sx in (-1, 1):                                                                    # side struts to the shell
        bars.append(box((sx * 0.075 - 0.004, -0.19, 0.06), (sx * 0.075 + 0.004, -0.09, 0.11)))
    parts = [(sV, sF, "Shell", SHELL), (rV, rF, "Shell", SHELL)]
    parts += [(v, f, "Guard", BARS) for v, f in bars]
    return parts


def main(libdir=None):
    lib = L.Library(libdir or os.path.join(HERE, "library"))
    tmp = tempfile.mkdtemp(prefix="sfs_sport_")
    made = []
    for name, parts, sock, meta in (("sport_hurley", hurley_parts(), "hand_r", dict(rotation=[60, 0, 0])),
                                    ("sport_hurl_helmet", helmet_parts(), "head", dict(fit="head", offset=[0, -0.13, 0.01]))):
        r = static_rig(name, parts)
        p = os.path.join(tmp, name + ".glb")
        RR.write_glb(r, p, {})
        lib.add_file(p, name, "prop", dict(CC0), log=lambda *a: None, socket=sock)
        d = lib.path("props", name)
        pr = RR.Rig.load(d); pr.meta["prop"].update(meta); pr.save(d)
        sj = os.path.join(d, "source.json")             # temp-file provenance is meaningless for generated props
        if os.path.exists(sj):
            os.remove(sj)
        made.append("props/" + name)
        # the library stands an imported prop on y = 0 (its lowest point, here the bottom of the face guard), so the
        # helmet's offset brings the rim down to the brow: the head socket is just below the top of the head
    lib.scan(import_inbox=False)
    print("Sport props (CC0) written to %s: %s" % (lib.dir, ", ".join(made)))
    return made


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)

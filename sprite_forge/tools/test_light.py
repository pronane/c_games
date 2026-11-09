#!/usr/bin/env python3
"""Does capture_light take a known room light out of a texture? (v11.2, synthetic, needs the MakeHuman assets)

    python tools/test_light.py

A MakeHuman body gets a known albedo: three materials (a shirt, trousers, skin) with some texture noise. It is lit
by a known coloured light from one side and above (spherical harmonics, ~x1.3 brighter on the lit side, warmer
there). capture_light.fit_light then sees only the lit colours, the normals and the material groups (layer x label,
as in a capture: here shirt + trousers share the "clothes" group, so it must separate them itself).
Checks: the albedo error to the truth at least halves, and so does the left / right difference (what is left of
that is the 6% texture noise, different on each side)."""
from __future__ import annotations
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)


def main():
    from sforge import capture_body as CB, capture_light as CLI, capture_texture as CT
    try:
        bm = CB.BodyModel()
    except Exception as e:                                                    # noqa: BLE001
        print("skipped (no MakeHuman assets): %s" % e)
        return 0
    sh = bm.shape(dict(gender=1.0), {}, 1.8)
    V = sh.V
    N = CT.vertex_normals(V, bm.F)
    rng = np.random.default_rng(1)
    y = V[:, 1]
    shirt = (y > 0.95) & (y < 1.55); trousers = y <= 0.95; skin = ~(shirt | trousers)
    alb = np.zeros((len(V), 3))
    alb[shirt] = [200, 60, 50]; alb[trousers] = [40, 60, 110]; alb[skin] = [210, 160, 130]
    alb = np.clip(alb * (1 + 0.06 * rng.standard_normal((len(V), 1))), 0, 255)
    sh_true = np.zeros((3, 9))
    sh_true[:, 3] = [0.30, 0.22, 0.12]                                       # from the person's left (+x), warm
    sh_true[:, 1] = [0.15, 0.15, 0.15]                                       # and from above
    sh_true[:, 2] = [0.05, 0.05, 0.10]
    lit = CLI.relight(alb, N, dict(sh=sh_true.tolist()))
    groups = np.where(skin, 2, 3)                                            # labels: skin / clothes
    est, info = CLI.fit_light(lit, N, groups, log=print, n_fit=len(V))
    dE = lambda a, b: float(np.linalg.norm(a - b, axis=1).mean())
    # the constant term (overall brightness / colour) cannot be told from the albedo: compare after matching it
    g = np.median(alb / np.maximum(est, 1), 0)
    before, after = dE(lit, alb), dE(est * g, alb)
    # left / right: vertex vs its mirror
    from scipy.spatial import cKDTree
    d, j = cKDTree(V).query(V * [-1, 1, 1]); pr = (d < 0.003) & (np.abs(V[:, 0]) > 0.02)
    sym_lit, sym_est = dE(lit[pr], lit[j[pr]]), dE(est[pr], est[j[pr]])
    print("albedo error (RGB): lit %.1f -> light removed %.1f" % (before, after))
    print("left / right difference (RGB): lit %.1f -> light removed %.1f" % (sym_lit, sym_est))
    checks = [("albedo error halved", after < 0.5 * before), ("left / right difference halved", sym_est < 0.5 * sym_lit)]
    for k, v in checks:
        print("%-36s %s" % (k, "PASS" if v else "FAIL"))
    return 0 if all(v for _, v in checks) else 1


if __name__ == "__main__":
    sys.exit(main())

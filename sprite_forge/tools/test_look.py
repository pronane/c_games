"""v10.2 appearance / MakeHuman character checks (CI).

Always (no downloads): appearance keys round-trip through look files, sliders map to the right MakeHuman targets
(signed -> -incr/-decr, left/right pairs), the template skeleton re-skins its own mesh exactly at rest, the software
renderer draws textured + alpha-tested parts, and the installed Gaelic squad GLB has a role for every mesh.
With the MakeHuman library (forge.py human --setup --full; optional): builds a full look and checks every feature
part, the morph moved what it should, balding fades hair, and the sprites sit on the baseline facing right."""
from __future__ import annotations
import json, os, sys, tempfile
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
from sforge.appearance import Appearance, SLIDERS, KEYS  # noqa: E402
from sforge import look as LK, mhrender as MR, glbpack  # noqa: E402

GAME = os.path.join(ROOT, "..", "Gaelic_Football_3d")
TEMPLATE = os.path.join(GAME, "assets", "source", "makehuman_template.glb")


class FakeLib:
    def has_target(self, n):
        return True


def main():
    fails = []
    # ---- appearance keys
    ap = Appearance()
    ap.set("muscle_arms", 0.8).set("lips", "thin").set("hair_style", "long").set("facial_hair", "beard")
    ap.set("brow_height", -0.5).set("hair_colour", "#9a4a1c").set("hairline", 2)
    tw = ap.target_weights(FakeLib())
    want = {"armslegs/l-upperarm-muscle-incr", "armslegs/r-upperarm-muscle-incr", "armslegs/l-lowerarm-muscle-incr",
            "mouth/mouth-upperlip-volume-decr", "mouth/mouth-lowerlip-volume-decr", "eyebrows/eyebrows-trans-down"}
    if not want <= set(tw):
        fails.append("target mapping: missing %s" % sorted(want - set(tw)))
    if abs(tw["armslegs/l-upperarm-muscle-incr"] - 0.8) > 1e-9 or ap.hairline != 1.0 or ap.hair_style != "long01":
        fails.append("slider clamp / alias / weight wrong")
    text = LK.look_text(ap, "test")
    back = LK.read_looks(text)
    if len(back) != 1 or back[0][1].values != ap.values:
        fails.append("look file round trip changed values")
    if set(KEYS) != {s[0] for s in SLIDERS} or len(KEYS) < 25:
        fails.append("appearance key table incomplete")
    try:
        Appearance().set("hair_style", "mohawk-xl"); fails.append("bad choice accepted")
    except ValueError:
        pass
    # ---- template skeleton: rest pose re-skins exactly, clips present
    po = MR.Poser(TEMPLATE)
    j, b = glbpack.read_glb(TEMPLATE)
    from sforge.mhchar import _acc
    pr = j["meshes"][0]["primitives"][0]["attributes"]
    V = _acc(j, b, pr["POSITION"]); J = _acc(j, b, pr["JOINTS_0"]); W = _acc(j, b, pr["WEIGHTS_0"])
    S, _ = po.matrices(None)
    P, _ = MR.skin(V, None, J, W, S)
    if np.abs(P - V).max() > 1e-4:
        fails.append("rest skinning moves the mesh by %.4f m" % np.abs(P - V).max())
    if len(po.clips) < 30 or "run" not in po.clips:
        fails.append("template clips missing (%d)" % len(po.clips))
    S2, _ = po.matrices("run", 0.2)
    P2, _ = MR.skin(V, None, J, W, S2)
    if np.abs(P2 - V).max() < 0.05:
        fails.append("run pose does not move the mesh")
    # ---- renderer on a synthetic character (opaque quad + alpha card)
    from PIL import Image
    import io
    from sforge.mhchar import Character, Part
    def png(a):
        bio = io.BytesIO(); Image.fromarray(a, "RGBA").save(bio, "PNG"); return bio.getvalue()
    red = np.zeros((8, 8, 4), np.uint8); red[..., 0] = 230; red[..., 3] = 255
    card = np.zeros((8, 8, 4), np.uint8); card[..., 1] = 230; card[:, :4, 3] = 255     # left half opaque
    quad = np.array([[-0.5, 0, 0], [0.5, 0, 0], [0.5, 1, 0], [-0.5, 1, 0]], float)
    F = np.array([[0, 1, 2], [0, 2, 3]]); UV = np.array([[0, 1], [1, 1], [1, 0], [0, 0]], float)
    Jz = np.zeros((4, 4), np.uint16); Wz = np.zeros((4, 4), np.float32); Wz[:, 0] = 1
    N = np.tile([0, 0, 1.0], (4, 1))
    ch = Character([Part("q", "body", quad, F, UV, Jz, Wz, N, None, "red"),
                    Part("c", "hair", quad * 0.6 + [0, 0.2, 0.1], F, UV, Jz, Wz, N, None, "card")], {"red": png(red), "card": png(card)})
    im = np.asarray(MR.render(ch, MR.rest(ch), MR.View(centre=(0, 0.5, 0), height=1.2), (60, 60), ss=1))
    left, right = im[30, 22], im[30, 38]
    if not (left[1] > left[0] and right[0] > right[1] and im[2, 2, 3] == 0):
        fails.append("renderer: alpha test / texture / background wrong (%s %s)" % (left, right))
    # ---- installed squad: every mesh has a look + role
    parts = os.path.join(GAME, "assets", "models", "gaelic_player.parts")
    if os.path.isfile(parts):
        jg, _ = glbpack.read_glb(os.path.join(GAME, "assets", "models", "gaelic_player.glb"))
        rows = [l.split() for l in open(parts) if l.strip() and not l.startswith("#")]
        if len(rows) != len(jg["meshes"]) or {r[2] for r in rows} - {"body", "kit", "hair", "brows", "lashes", "eyes"}:
            fails.append("gaelic_player.parts does not match the GLB meshes")
        if len({r[1] for r in rows}) < 5:
            fails.append("squad has fewer than 5 looks")
    stats = {"targets": len(tw), "clips": len(po.clips)}
    # ---- full build (only with the MakeHuman library)
    from sforge import mhlib
    lib = mhlib.Library()
    if lib.available():
        b = LK.Builder(TEMPLATE, lib)
        plain = b.character(Appearance(), skin_res=256)
        ap2 = Appearance()
        for k, v in dict(hair_style="short02", hairline=0.8, facial_hair="beard", muscle_arms=1, nose_size=1, lips=1).items():
            ap2.set(k, v)
        ch2 = b.character(ap2, skin_res=256)
        roles = sorted(p.role for p in ch2.parts)
        for r in ("body", "eyes", "lashes", "brows", "hair", "kit"):
            if r not in roles:
                fails.append("look build: no %s part" % r)
        if not any(p.name.endswith("_facialhair") and len(p.F) > 500 for p in ch2.parts):
            fails.append("beard has too few strand cards")
        hair = [p for p in ch2.parts if p.name.endswith("_hair")][0]
        if hair.C is None or hair.C[:, 3].min() > 0.2:
            fails.append("balding hairline does not fade the hair")
        d = np.linalg.norm(ch2.parts[0].V - plain.parts[0].V, axis=1)
        if d.max() < 0.005:
            fails.append("sliders did not change the body")
        cells = b.sprites(ch2, ["run"], 4, None)["run"]
        lows = []
        for c in cells:
            a = np.asarray(c)[..., 3]
            ys = np.nonzero(a.max(1) > 0)[0]
            lows.append(int(ys.max()) if len(ys) else -1)
        if min(abs(y - 248) for y in lows) > 4 or max(abs(y - 248) for y in lows) > 20:      # running has a flight phase
            fails.append("run frames: feet not on the baseline %s" % lows)
        out = os.path.join(tempfile.mkdtemp(), "look.glb")
        n = b.glb(ch2, out)
        jl, _ = glbpack.read_glb(out)
        if len(jl["meshes"]) != len(ch2.parts) or len(jl["animations"]) != len(po.clips):
            fails.append("look GLB lost meshes or clips")
        # built-in CC0 template (no game files): MakeHuman CC0 body + Sprite Forge's own clips
        from sforge import mhtemplate
        b0 = LK.Builder(None, lib)
        if os.path.abspath(b0.template_path) != os.path.abspath(mhtemplate.path()):
            fails.append("default template is not the built-in CC0 one: %s" % b0.template_path)
        ch0 = b0.character(ap2, skin_res=256)
        clips0 = LK.pick_clips(b0.poser.clips)
        if not {"idle", "run", "kick"} <= set(clips0):
            fails.append("built-in template clips missing: %s" % clips0)
        c0 = np.asarray(b0.sprites(ch0, ["idle"], 1, None)["idle"][0])[..., 3]
        ys = np.nonzero(c0.max(1) > 0)[0]
        if not len(ys) or abs(ys.max() - 248) > 4 or ys.min() < 20:
            fails.append("built-in template idle sprite not standing on the baseline")
        stats.update(parts=len(ch2.parts), max_morph_mm=round(float(d.max() * 1000), 1), glb_mb=round(n / 1e6, 1))
    else:
        print("SKIP full build: MakeHuman library not installed (forge.py human --setup --full)")
    print(json.dumps(stats))
    for f in fails:
        print("FAIL", f)
    print("%d problem(s)" % len(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())

"""forge.py look - realistic MakeHuman characters from appearance keys (v10.2): preview, GLB and sprite sheets.

    forge.py look --set "hair_style=long01,facial_hair=beard,muscle_arms=0.8" --preview me.png
    forge.py look --look squad.txt --variant 2 --glb player.glb --sprites out/ --clips run,kick_run,catch

A look is the Appearance keys (sforge/appearance.py: sliders -1..1, choices, colours) as `key = value` lines, a
squad file with [variant] blocks, or --set k=v,...  The character is the CC0 MakeHuman base mesh morphed by
MakeHuman's own targets with fitted MakeHuman hair / brows / lashes / eyes, strand-card facial hair and a painted
skin, carried onto a rigged template (skeleton + clips).  The same character is rendered to sprites by
sforge.mhrender (linear blend skinning, alpha-tested strands), so 3D model and sprites match.
Needs: forge.py human --setup --full (the MakeHuman library) and a template GLB (default: Gaelic Football 3D's
MakeHuman player, or assets/makehuman/template.glb, or --template)."""
from __future__ import annotations
import argparse, io, json, os, re, sys, time
import numpy as np
from PIL import Image

from .appearance import Appearance, KEYS

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES = [os.path.join(ROOT, "assets", "makehuman", "template.glb"),
             os.path.join(ROOT, "..", "Gaelic_Football_3d", "assets", "source", "makehuman_template.glb")]
CELL = (192, 256)
BG = (0.36, 0.52, 0.30)


def default_template(path=None):
    for p in ([path] if path else []) + ([os.environ["SFS_MH_TEMPLATE"]] if os.environ.get("SFS_MH_TEMPLATE") else []) + TEMPLATES:
        if p and os.path.isfile(p):
            return os.path.abspath(p)
    return None


def read_looks(text):
    """`key = value` lines (one look) or [name] blocks (several) -> [(name, Appearance)]"""
    looks, cur = [], None
    for ln in text.splitlines():
        s = re.split(r"\s#\s", ln, maxsplit=1)[0].strip()
        if not s or s.startswith("#"):
            continue
        m = re.match(r"^\[(.+?)\]", s)
        if m:
            cur = (m.group(1).strip(), Appearance()); looks.append(cur); continue
        if "=" in s:
            k, v = [x.strip() for x in s.split("=", 1)]
            if k not in KEYS:
                continue
            if cur is None:
                cur = ("look", Appearance()); looks.append(cur)
            cur[1].set(k, v)
    return looks


def parse_set(s, ap=None):
    ap = ap or Appearance()
    for kv in (s or "").replace(";", ",").split(","):
        if kv.strip():
            k, _, v = kv.partition("=")
            ap.set(k.strip(), v.strip())
    return ap


def look_text(ap, name=None):
    return ("[%s]\n" % name if name else "") + "\n".join(ap.spec_lines()) + "\n"


class Builder:
    """caches the MakeHuman library, template, poser and kit atlases between builds (Studio live preview)"""

    def __init__(self, template=None, lib=None):
        from . import mhlib, mhchar, mhrender
        self.lib = lib or mhlib.Library()
        if not self.lib.available():
            raise FileNotFoundError("MakeHuman library missing: python3 forge.py human --setup --full")
        self.template_path = default_template(template)
        if not self.template_path:
            raise FileNotFoundError("no MakeHuman template GLB (pass --template, or copy one to %s)" % TEMPLATES[0])
        self.tm = mhchar.Template.load(self.template_path, self.lib)
        self.poser = mhrender.Poser(self.template_path)
        self._kits = {}

    def kit(self, name="home"):
        from . import mhchar, footballer as FB
        if name not in self._kits:
            if name not in FB.KITS:
                name = "home"
            self._kits[name] = mhchar.kit_textures(self.tm, [name], lambda k: FB.paints(k), res=1024)[name]
        return self._kits[name]

    def character(self, ap, kit="home", skin_res=1024, name="player"):
        from . import mhchar, mhrender
        ch = mhchar.build(self.tm, ap, self.lib, name=name, skin_res=skin_res)
        return mhrender.with_kit(ch, self.kit(kit))

    def preview(self, ch, size=420, yaw=25.0):
        """face close-up + full figure side by side"""
        from . import mhrender as MR
        top = max(float(p.V[:, 1].max()) for p in ch.parts if p.role == "body")
        face = MR.render(ch, MR.rest(ch), MR.View.face(yaw, top), (size, size), bg=BG)
        full = MR.render(ch, MR.rest(ch), MR.View.full(yaw), (int(size * 0.62), size), bg=BG)
        out = Image.new("RGBA", (face.width + full.width, size))
        out.paste(face, (0, 0)); out.paste(full, (face.width, 0))
        return out

    def sprites(self, ch, clips, frames=8, out_dir=None, cell=CELL, log=print):
        """-> {clip: [RGBA cells]}; writes <clip>.png strips + frames/<clip>_NN.png + meta.json when out_dir"""
        from . import mhrender as MR
        res = {}
        for c in clips:
            if c not in self.poser.clips:
                raise KeyError("clip '%s' not in the template (%s)" % (c, ", ".join(self.poser.clips)))
            cl = self.poser.clips[c]
            n = max(1, int(frames))
            res[c] = [MR.render(ch, self.poser.pose(ch, c, cl.duration * i / n), MR.View.side(cell), cell) for i in range(n)]
        if out_dir:
            os.makedirs(os.path.join(out_dir, "frames"), exist_ok=True)
            meta = {"cell": list(cell), "facing": "right", "baseline": 248, "clips": {}}
            for c, cells in res.items():
                strip = Image.new("RGBA", (cell[0] * len(cells), cell[1]))
                for i, im in enumerate(cells):
                    strip.alpha_composite(im, (i * cell[0], 0))
                    im.save(os.path.join(out_dir, "frames", "%s_%02d.png" % (c, i)))
                strip.save(os.path.join(out_dir, "%s.png" % c))
                meta["clips"][c] = {"frames": len(cells), "fps": round(len(cells) / max(self.poser.clips[c].duration, 1e-3), 2)}
            json.dump(meta, open(os.path.join(out_dir, "meta.json"), "w"), indent=1)
            log("sprites: %d clips x %d frames -> %s" % (len(res), frames, out_dir))
        return res

    def glb(self, ch, path):
        from . import glbpack
        bio = io.BytesIO(); self.kit("home").save(bio, "PNG")
        images = dict(ch.images); images["kit"] = bio.getvalue()
        return glbpack.pack_parts(self.template_path, path, ch.parts, images,
                                  alpha_keys=("hair_", "eyebrows_", "eyelashes_", "facial_hair"),
                                  extras={"generator": "sprite_forge forge.py look"})


def main(argv):
    ap_ = argparse.ArgumentParser(prog="forge.py look", description=__doc__.split("\n\n")[0])
    ap_.add_argument("--look", help="look file: key = value lines, or a squad file with [variant] blocks")
    ap_.add_argument("--variant", default="0", help="which [variant] of a squad file (index or name; default 0)")
    ap_.add_argument("--set", default="", help="appearance keys k=v,k=v (applied on top of --look)")
    ap_.add_argument("--template", help="rigged MakeHuman template GLB (skeleton + clips)")
    ap_.add_argument("--kit", default="home")
    ap_.add_argument("--preview", help="write a face + full-figure preview PNG")
    ap_.add_argument("--glb", help="write the character GLB (meshes per part on the template's skeleton + clips)")
    ap_.add_argument("--sprites", help="write sprite strips + frames + meta.json to this folder")
    ap_.add_argument("--clips", default="idle,run,kick_run,catch,hand_pass", help="clips for --sprites")
    ap_.add_argument("--frames", type=int, default=8)
    ap_.add_argument("--save-look", help="write the final look (key = value lines) here")
    ap_.add_argument("--keys", action="store_true", help="list the appearance keys and exit")
    a = ap_.parse_args(argv)
    if a.keys:
        from .appearance import SLIDERS
        for key, kind, d, rng, label, group, _ in SLIDERS:
            r = ("%g..%g" % rng) if kind == "slider" else ("|".join(rng) if kind == "choice" else "#rrggbb or name")
            print("%-18s %-11s %-7s %-40s %s" % (key, group, kind, label, r))
        return 0
    ap = Appearance()
    if a.look:
        looks = read_looks(open(a.look, encoding="utf-8").read())
        if not looks:
            print("no appearance keys in %s" % a.look); return 2
        pick = next((l for l in looks if l[0] == a.variant), None)
        if pick is None:
            pick = looks[int(a.variant)] if a.variant.isdigit() and int(a.variant) < len(looks) else looks[0]
        ap = pick[1]
    parse_set(a.set, ap)
    if a.save_look:
        open(a.save_look, "w").write(look_text(ap))
    if not (a.preview or a.glb or a.sprites):
        print("\n".join(ap.spec_lines()) or "(template look)"); print("nothing to write: --preview / --glb / --sprites"); return 0
    t0 = time.time()
    try:
        b = Builder(a.template)
    except FileNotFoundError as e:
        print(e); return 2
    ch = b.character(ap, a.kit)
    if a.preview:
        b.preview(ch).save(a.preview); print("preview ->", a.preview)
    if a.glb:
        n = b.glb(ch, a.glb); print("GLB -> %s (%.1f MB, %d meshes)" % (a.glb, n / 1e6, len(ch.parts)))
    if a.sprites:
        b.sprites(ch, [c.strip() for c in a.clips.split(",") if c.strip()], a.frames, a.sprites)
    print("done in %.1fs" % (time.time() - t0))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

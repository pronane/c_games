#!/usr/bin/env python3
"""Game adapter: Sprite Forge output folder -> HD Fighter character (pygame, assets/ + assets_hd/meta.json).

  python tools/export_hdf.py out/<name> <HD_Fighter> <tag> [--figure 172] [--feet 236]

HD Fighter frames are 96x128 at SCALE 2 = 192x256, one horizontal strip per state, drawn with the frame's
mid-bottom on the ground.  This crops every Sprite Forge cell around its pivot so the feet sit on row --feet and
the upright idle figure is --figure px tall (the built-in fighters are ~170), writes sprites/<tag>_<state>.png,
select/portrait_<tag>.png and adds the character to BOTH meta.json files (F2 toggles between them).
State map: lp/hp = punch, lk/hk = kick, super = special1, win = victory, lose = hit (held).
Pure Pillow; pixels are scaled, never redrawn."""
import argparse, json, os
from PIL import Image

STATES = {"idle": "idle", "walk": "walk", "crouch": "crouch", "jump": "jump", "lp": "punch", "hp": "punch",
          "lk": "kick", "hk": "kick", "block": "block", "throw": "throw", "special1": "special1",
          "special2": "special2", "super": "special1", "hit": "hit", "win": "victory", "lose": "hit"}
FW, FH = 192, 256


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src"); ap.add_argument("game"); ap.add_argument("tag")
    ap.add_argument("--figure", type=int, default=182); ap.add_argument("--feet", type=int, default=226)
    a = ap.parse_args()
    js = json.load(open(os.path.join(a.src, "atlas.json")))
    meta, an = js["meta"], js["animations"]
    gy, px = meta["ground_y"], meta.get("pivot", {}).get("x", meta["frame_w"] // 2)
    idle0 = Image.open(os.path.join(a.src, "moves", "idle_00.png"))
    bb = idle0.getchannel("A").getbbox()
    s = a.figure / float(gy - bb[1])
    sw, sh = FW / s, FH / s                        # source window (cell px) for one game frame
    x0, y0 = px - sw / 2, gy - a.feet / s
    def frame(path):
        im = Image.open(path).convert("RGBA")
        c = Image.new("RGBA", (int(round(sw)), int(round(sh))), (0, 0, 0, 0))
        c.paste(im, (int(round(-x0)), int(round(-y0))), im)
        return c.resize((FW, FH), Image.LANCZOS)
    out = {}
    for folder in ("assets", "assets_hd"):
        os.makedirs(os.path.join(a.game, folder, "sprites"), exist_ok=True)
    for st, mv in STATES.items():
        if mv not in an:
            mv = "idle"
        n, fps = an[mv].get("count", len(an[mv]["frames"])), an[mv].get("fps", 10)
        fr = [frame(os.path.join(a.src, "moves", "%s_%02d.png" % (mv, i))) for i in range(n)]
        if st == "lose":
            fr = fr[-2:]
        if st == "hp" and len(fr) > 4:               # heavy = the same punch, held longer on contact
            fr = fr[:len(fr) // 2 + 1] + fr[len(fr) // 2:]
        strip = Image.new("RGBA", (FW * len(fr), FH))
        for i, f in enumerate(fr):
            strip.paste(f, (i * FW, 0))
        rel = "sprites/%s_%s.png" % (a.tag, st)
        for folder in ("assets", "assets_hd"):
            strip.save(os.path.join(a.game, folder, rel))
        out[st] = [rel, len(fr), max(2, round(60.0 / fps) // (2 if st in ("lp", "lk") else 1))]
    # portrait: head and shoulders from idle frame 0
    head = idle0.crop((px - (gy - bb[1]) * 0.22, bb[1] - 8, px + (gy - bb[1]) * 0.22, bb[1] + (gy - bb[1]) * 0.42))
    por = Image.new("RGBA", (128, 128), (24, 28, 40, 255)); hh = head.resize((128, 128), Image.LANCZOS)
    por.alpha_composite(hh)
    for folder in ("assets", "assets_hd"):
        os.makedirs(os.path.join(a.game, folder, "select"), exist_ok=True)
        por.save(os.path.join(a.game, folder, "select", "portrait_%s.png" % a.tag))
        mp = os.path.join(a.game, folder, "meta.json")
        m = json.load(open(mp))
        m["characters"][a.tag] = out
        m["select"][a.tag] = "select/portrait_%s.png" % a.tag
        json.dump(m, open(mp, "w"), indent=2)
    print("HD Fighter export -> %s: %d states, scale %.3f" % (a.tag, len(out), s))


if __name__ == "__main__":
    main()

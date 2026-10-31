#!/usr/bin/env python3
"""Engine / editor exporters (v9.4): one Sprite Forge output folder -> files each tool opens directly.

    python tools/export_engines.py out/<name> DEST [--aseprite] [--phaser] [--godot] [--gif] [--all] [--scale 1.0]

  --aseprite  <name>_sheet.png + <name>_aseprite.json in Aseprite's own sprite-sheet JSON (array) format, one frameTag per
              move (File > Import Sprite Sheet > JSON data), + import_<name>.lua that builds a tagged .aseprite file
  --phaser    <name>.png + <name>.json (Phaser 3 texture atlas, JSON-hash) + <name>_anims.json (this.anims.fromJSON)
              + example_scene.js
  --godot     <name>_frames.tres: a Godot 4 SpriteFrames resource (AtlasTexture regions, per-move fps/loop) - no
              plugin needed; drop it on an AnimatedSprite2D (the Godot addon in plugins/ imports whole folders too)
  --gif       previews/<move>.gif and .webp, animated at the move's fps, on transparent / checker-free background
Unity: use plugins/unity (com.spriteforge.importer), which reads the same folder.
The atlas is repacked tightly (frames trimmed to the union box of the whole character, so every frame keeps the
same pivot) unless --no-trim."""
from __future__ import annotations
import argparse, json, os, sys
from PIL import Image


def load(src):
    js = json.load(open(os.path.join(src, "atlas.json")))
    meta, an = js["meta"], js["animations"]
    frames = {}
    for mv, a in an.items():
        frames[mv] = [Image.open(os.path.join(src, "moves", f + ".png")).convert("RGBA") for f in a["frames"]]
    return meta, an, frames


def union_box(frames, pad=4):
    box = None
    for fr in frames.values():
        for im in fr:
            b = im.getchannel("A").getbbox()
            if b:
                box = b if box is None else (min(box[0], b[0]), min(box[1], b[1]), max(box[2], b[2]), max(box[3], b[3]))
    W, H = next(iter(frames.values()))[0].size
    if box is None:
        return (0, 0, W, H)
    return (max(0, box[0] - pad), max(0, box[1] - pad), min(W, box[2] + pad), min(H, box[3] + pad))


def pack(frames, an, box, scale=1.0, cols=None):
    fw, fh = int(round((box[2] - box[0]) * scale)), int(round((box[3] - box[1]) * scale))
    order = [(mv, i) for mv in an for i in range(len(frames[mv]))]
    n = len(order)
    cols = cols or max(1, int((n * fh / max(1, fw)) ** 0.5 + 0.999))
    rows = (n + cols - 1) // cols
    sheet = Image.new("RGBA", (cols * fw, rows * fh), (0, 0, 0, 0))
    rects = {}
    for k, (mv, i) in enumerate(order):
        im = frames[mv][i].crop(box)
        if scale != 1.0:
            im = im.resize((fw, fh), Image.LANCZOS)
        x, y = (k % cols) * fw, (k // cols) * fh
        sheet.paste(im, (x, y))
        rects[(mv, i)] = (x, y, fw, fh)
    return sheet, rects, fw, fh, order


def aseprite(dst, name, an, frames, sheet, rects, order, fw, fh):
    sheet.save(os.path.join(dst, name + "_sheet.png"))
    fl, tags, k = [], [], 0
    for mv in an:
        n = len(frames[mv]); dur = int(round(1000.0 / max(1, an[mv].get("fps", 12))))
        for i in range(n):
            x, y, w, h = rects[(mv, i)]
            fl.append({"filename": "%s %d" % (mv, i), "frame": {"x": x, "y": y, "w": w, "h": h}, "rotated": False, "trimmed": False,
                       "spriteSourceSize": {"x": 0, "y": 0, "w": w, "h": h}, "sourceSize": {"w": w, "h": h}, "duration": dur})
        tags.append({"name": mv, "from": k, "to": k + n - 1, "direction": "forward" if an[mv].get("loop") else "forward",
                     "repeat": "0" if an[mv].get("loop") else "1"})
        k += n
    json.dump({"frames": fl, "meta": {"app": "Sprite Forge Studio", "version": "9.4", "image": name + "_sheet.png", "format": "RGBA8888",
                                      "size": {"w": sheet.width, "h": sheet.height}, "scale": "1", "frameTags": tags}},
              open(os.path.join(dst, name + "_aseprite.json"), "w"), indent=1)
    lua = '''-- Sprite Forge -> Aseprite: run with File > Scripts (or: aseprite -b --script import_%(n)s.lua)
local dir = app.fs.filePath(debug.getinfo(1, "S").source:sub(2))
local sheet = Image{ fromFile = app.fs.joinPath(dir, "%(n)s_sheet.png") }
local W, H = %(w)d, %(h)d
local spr = Sprite(W, H, ColorMode.RGB)
local frames = %(frames)s
for i, f in ipairs(frames) do
  if i > 1 then spr:newEmptyFrame() end
  local img = Image(W, H, ColorMode.RGB)
  img:drawImage(sheet, Point(-f[1], -f[2]))
  spr:newCel(spr.layers[1], i, img, Point(0, 0))
  spr.frames[i].duration = f[3] / 1000
end
for _, t in ipairs(%(tags)s) do
  local tag = spr:newTag(t[2], t[3]); tag.name = t[1]
end
spr:saveAs(app.fs.joinPath(dir, "%(n)s.aseprite"))
''' % {"n": name, "w": fw, "h": fh,
       "frames": "{" + ", ".join("{%d, %d, %d}" % (f["frame"]["x"], f["frame"]["y"], f["duration"]) for f in fl) + "}",
       "tags": "{" + ", ".join('{"%s", %d, %d}' % (t["name"], t["from"] + 1, t["to"] + 1) for t in tags) + "}"}
    open(os.path.join(dst, "import_%s.lua" % name), "w").write(lua)


def phaser(dst, name, an, frames, sheet, rects, fw, fh):
    sheet.save(os.path.join(dst, name + ".png"))
    fr = {}
    for (mv, i), (x, y, w, h) in rects.items():
        fr["%s_%02d" % (mv, i)] = {"frame": {"x": x, "y": y, "w": w, "h": h}, "rotated": False, "trimmed": False,
                                   "spriteSourceSize": {"x": 0, "y": 0, "w": w, "h": h}, "sourceSize": {"w": w, "h": h},
                                   "pivot": {"x": 0.5, "y": 1.0}}
    json.dump({"frames": fr, "meta": {"app": "Sprite Forge Studio", "image": name + ".png", "format": "RGBA8888",
                                      "size": {"w": sheet.width, "h": sheet.height}, "scale": "1"}},
              open(os.path.join(dst, name + ".json"), "w"), indent=1)
    anims = {"anims": [{"key": "%s_%s" % (name, mv), "frameRate": an[mv].get("fps", 12), "repeat": -1 if an[mv].get("loop") else 0,
                        "frames": [{"key": name, "frame": "%s_%02d" % (mv, i)} for i in range(len(frames[mv]))]} for mv in an]}
    json.dump(anims, open(os.path.join(dst, name + "_anims.json"), "w"), indent=1)
    open(os.path.join(dst, "example_scene.js"), "w").write('''// Phaser 3: load the Sprite Forge character and play a move
class Fight extends Phaser.Scene {
  preload() {
    this.load.atlas("%(n)s", "%(n)s.png", "%(n)s.json");
    this.load.json("%(n)s_anims", "%(n)s_anims.json");
  }
  create() {
    this.anims.fromJSON(this.cache.json.get("%(n)s_anims"));
    const p = this.add.sprite(400, 500, "%(n)s").setOrigin(0.5, 1);   // feet on the ground line
    p.play("%(n)s_idle");
    this.input.keyboard.on("keydown-J", () => p.play("%(n)s_punch").once("animationcomplete", () => p.play("%(n)s_idle")));
    this.input.keyboard.on("keydown-K", () => p.play("%(n)s_kick").once("animationcomplete", () => p.play("%(n)s_idle")));
  }
}
new Phaser.Game({ type: Phaser.AUTO, width: 800, height: 600, backgroundColor: "#202830", scene: Fight });
''' % {"n": name})


def godot(dst, name, an, frames, sheet, rects):
    sheet.save(os.path.join(dst, name + ".png"))
    subs, anims, sid = [], [], 1
    for mv in an:
        refs = []
        for i in range(len(frames[mv])):
            x, y, w, h = rects[(mv, i)]
            subs.append('[sub_resource type="AtlasTexture" id="AtlasTexture_%d"]\natlas = ExtResource("1_tex")\nregion = Rect2(%d, %d, %d, %d)\n' % (sid, x, y, w, h))
            refs.append('{\n"duration": 1.0,\n"texture": SubResource("AtlasTexture_%d")\n}' % sid)
            sid += 1
        anims.append('{\n"frames": [%s],\n"loop": %s,\n"name": &"%s",\n"speed": %.1f\n}' % (
            ", ".join(refs), "true" if an[mv].get("loop") else "false", mv, float(an[mv].get("fps", 12))))
    tres = '[gd_resource type="SpriteFrames" load_steps=%d format=3]\n\n[ext_resource type="Texture2D" path="res://%s.png" id="1_tex"]\n\n%s\n[resource]\nanimations = [%s]\n' % (
        sid + 1, name, "\n".join(subs), ", ".join(anims))
    open(os.path.join(dst, name + "_frames.tres"), "w").write(tres)


def previews(dst, an, frames, box, scale=0.5):
    os.makedirs(os.path.join(dst, "previews"), exist_ok=True)
    for mv in an:
        dur = int(round(1000.0 / max(1, an[mv].get("fps", 12))))
        ims = []
        for im in frames[mv]:
            c = im.crop(box)
            c = c.resize((max(1, int(c.width * scale)), max(1, int(c.height * scale))), Image.LANCZOS)
            ims.append(c)
        ims[0].save(os.path.join(dst, "previews", mv + ".webp"), save_all=True, append_images=ims[1:], duration=dur, loop=0, lossless=True)
        pal = [im.convert("RGBA") for im in ims]
        gif = [Image.alpha_composite(Image.new("RGBA", p.size, (0, 0, 0, 0)), p) for p in pal]
        gif[0].save(os.path.join(dst, "previews", mv + ".gif"), save_all=True, append_images=gif[1:], duration=dur, loop=0,
                    disposal=2, transparency=0, optimize=False)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("src"); ap.add_argument("dst")
    for k in ("aseprite", "phaser", "godot", "gif", "all"):
        ap.add_argument("--" + k, action="store_true")
    ap.add_argument("--scale", type=float, default=1.0); ap.add_argument("--no-trim", action="store_true")
    a = ap.parse_args(argv)
    meta, an, frames = load(a.src)
    name = meta.get("name", "character")
    os.makedirs(a.dst, exist_ok=True)
    W, H = next(iter(frames.values()))[0].size
    box = (0, 0, W, H) if a.no_trim else union_box(frames)
    sheet, rects, fw, fh, order = pack(frames, an, box, a.scale)
    done = []
    if a.aseprite or a.all:
        aseprite(a.dst, name, an, frames, sheet, rects, order, fw, fh); done.append("aseprite")
    if a.phaser or a.all:
        phaser(a.dst, name, an, frames, sheet, rects, fw, fh); done.append("phaser")
    if a.godot or a.all:
        godot(a.dst, name, an, frames, sheet, rects); done.append("godot")
    if a.gif or a.all:
        previews(a.dst, an, frames, box); done.append("gif/webp previews")
    print("exported %s: %d frames %dx%d (trimmed from %dx%d) -> %s" % (", ".join(done), len(order), fw, fh, W, H, a.dst))


if __name__ == "__main__":
    sys.exit(main())

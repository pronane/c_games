"""Side-by-side comparison of one frame across console exports (nearest-neighbour upscaled, true pixels).
usage: python tools/console_compare.py OUT.png FRAME_NAME build_dir [build_dir ...]"""
import json, os, sys
from PIL import Image, ImageDraw


def main(out, frame, dirs, cell=220):
    tiles = []
    for d in dirs:
        cd = os.path.join(d, "console"); st = json.load(open(os.path.join(cd, "console.json")))
        im = Image.open(os.path.join(cd, "frames", frame + ".png")).convert("RGBA")
        k = cell / max(st["frame_w"], st["frame_h"])          # every frame cell shown at the same size
        im = im.resize((max(1, int(im.width * k)), max(1, int(im.height * k))), Image.NEAREST if k >= 1 else Image.LANCZOS)
        cols = len(st.get("palette_native", [])) or st.get("colours_used", 0)
        tiles.append((im, "%s  %dx%d" % (st["label"], st["frame_w"], st["frame_h"]), ("%d colours" % cols) if cols else "true colour"))
    W = len(tiles) * (cell + 16) + 16; H = cell + 70
    m = Image.new("RGB", (W, H), (58, 62, 70)); dr = ImageDraw.Draw(m)
    for i, (im, a, b) in enumerate(tiles):
        x = 16 + i * (cell + 16); bg = Image.new("RGBA", (cell, cell), (90, 96, 108, 255))
        for yy in range(0, cell, 16):
            for xx in range(0, cell, 16):
                if (xx + yy) // 16 % 2: bg.paste((100, 106, 118, 255), (xx, yy, xx + 16, yy + 16))
        bg.alpha_composite(im, ((cell - im.width) // 2, cell - im.height)); m.paste(bg.convert("RGB"), (x, 12))
        dr.text((x, cell + 20), a, fill="white"); dr.text((x, cell + 38), b, fill=(200, 210, 220))
    m.save(out); print("wrote", out)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3:])

#!/usr/bin/env python3
"""Make one picture of a console export: sheet, palette, tiles + the verify_console.py result.
usage: console_board.py out/<name> board.png"""
import os, subprocess, sys
from PIL import Image, ImageDraw, ImageFont
HERE = os.path.dirname(os.path.abspath(__file__))
out, png = sys.argv[1], sys.argv[2]
c = os.path.join(out, "console")
r = subprocess.run([sys.executable, os.path.join(HERE, "..", "verify_console.py"), out], capture_output=True, text=True).stdout
F = lambda s: ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", s)
im = Image.new("RGB", (1500, 960), (22, 26, 38)); d = ImageDraw.Draw(im)
d.text((16, 10), "out/%s/console/  (files: %s)" % (os.path.basename(out.rstrip("/")), ", ".join(sorted(os.listdir(c)))[:150]), fill=(255, 255, 255), font=F(17))
def put(name, box, scale_to, label):
    p = os.path.join(c, name)
    if not os.path.exists(p):
        return
    s = Image.open(p).convert("RGBA"); s.thumbnail(scale_to, Image.NEAREST) if max(s.size) > max(scale_to) else None
    k = max(1, min(scale_to[0] // s.width, scale_to[1] // s.height)); s = s.resize((s.width * k, s.height * k), Image.NEAREST)
    bg = Image.new("RGBA", s.size, (60, 64, 80, 255)); bg.alpha_composite(s); im.paste(bg.convert("RGB"), box)
    d.text((box[0], box[1] - 22), label, fill=(255, 220, 120), font=F(16))
put("sheet.png", (16, 70), (900, 560), "sheet.png (indexed, console palette)")
put("palette.png", (940, 70), (520, 60), "palette.png")
put("tiles_bank0.png", (940, 190), (520, 440), "tiles_bank0.png (8x8 tiles)")
lines = [l for l in r.splitlines() if l.strip()]
y = 660
for l in lines[-12:]:
    d.text((16, y), l[:150], fill=(120, 230, 160) if "PASS" in l else (255, 120, 120) if "FAIL" in l else (220, 220, 220), font=F(17)); y += 23
im.save(png); print(png)

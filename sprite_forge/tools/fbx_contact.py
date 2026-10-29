"""Run render_fbx_preview.py with Blender/bpy and lay the renders out as one labelled PNG.
  python3 tools/fbx_contact.py out/<name>/model.fbx out.png"""
import os, subprocess, sys
from PIL import Image, ImageDraw, ImageFont
HERE = os.path.dirname(os.path.abspath(__file__))
fbx, out = sys.argv[1], sys.argv[2]
py = os.environ.get("SFS_BPY_PYTHON")
cmd = [py, os.path.join(HERE, "render_fbx_preview.py"), fbx, out] if py else ["blender", "-b", "-P", os.path.join(HERE, "render_fbx_preview.py"), "--", fbx, out]
subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL)
tmp = os.path.splitext(out)[0] + "_tmp"
items = [l.split("\t") for l in open(os.path.join(tmp, "list.txt")).read().splitlines()]
ver = open(os.path.splitext(out)[0] + "_verify.txt").read()
F = lambda s: ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", s)
cols = 4; W = cols * 330 + 10; H = 90 + ((len(items) + cols - 1) // cols) * 440 + 70
im = Image.new("RGB", (W, H), (22, 26, 38)); d = ImageDraw.Draw(im)
d.text((12, 12), "model.fbx re-imported in Blender (headless) and rendered", fill=(255, 255, 255), font=F(28))
d.text((12, 52), ver.splitlines()[0], fill=(120, 230, 160), font=F(20))
for i, (p, n) in enumerate(items):
    x = 10 + (i % cols) * 330; y = 90 + (i // cols) * 440
    im.paste(Image.open(p).convert("RGB"), (x, y)); d.text((x + 4, y + 404), n, fill=(230, 230, 230), font=F(20))
acts = ver.splitlines()[1][:150]
d.text((12, H - 50), acts, fill=(180, 190, 210), font=F(16))
im.save(out); print(out)

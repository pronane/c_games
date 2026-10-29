"""v7.1  forge.py package / forge.py summary - drop-in zip and a pipeline summary image.

  forge.py package --char <game>/assets/char_x --out pack.zip [--root char_x]
                   [--doc README.md ...] [--add SRC=DEST ...] [--exclude export_report.txt ...]
                   [--patch-orig DIR --patch-new DIR --patch-files a,b,c] [--verify] [--max-mb 25]

    The zip has ONE folder at its root (--root, default the char folder's name) holding the game files
    (g_*.png, sprites.cfg, portrait.png, contact_sheet.png ...), the --doc files, anything --add'ed
    (SRC file or folder -> DEST path inside the root folder) and, with --patch-*, --patch-dest
    (default roster_patch/roster.patch):
    a unified diff (difflib, paths a/<file> b/<file>) of each --patch-files path between the two trees.
    --verify runs tools/verify_cfg.py on the char folder first and refuses to pack on an error.
    Fails if the zip is over --max-mb.

  forge.py summary --out summary.png IMG[=Label] IMG[=Label] ... [--height 520] [--title T]
    Side-by-side strip of the given images (each fitted to --height, alpha shown on a checkerboard),
    separated by arrows and captioned - e.g. photo -> cutout -> sprite -> HD sprite -> contact sheet.
"""
from __future__ import annotations
import argparse, difflib, os, subprocess, sys, zipfile
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _font(sz):
    for f in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(f, sz)
        except OSError:
            pass
    return ImageFont.load_default()


def make_patch(orig, new, files):
    out = []
    for f in files:
        a = os.path.join(orig, f); b = os.path.join(new, f)
        al = open(a, encoding="utf-8", errors="replace").read().splitlines(True) if os.path.exists(a) else []
        bl = open(b, encoding="utf-8", errors="replace").read().splitlines(True) if os.path.exists(b) else []
        d = list(difflib.unified_diff(al, bl, "a/" + f if al else "/dev/null", "b/" + f))
        for line in d:
            out.append(line if line.endswith("\n") else line + "\n\\ No newline at end of file\n")
    return "".join(out)


def package(a):
    char = os.path.abspath(a.char)
    root = a.root or os.path.basename(char.rstrip("/"))
    if a.verify:
        r = subprocess.run([sys.executable, os.path.join(HERE, "spriteforge", "tools", "verify_cfg.py"), char],
                           capture_output=True, text=True)
        print(r.stdout.rstrip())
        if r.returncode:
            print("package: verify_cfg failed - not packing"); return 1
    items = []                                   # (src file, arcname)
    for dp, _, fs in os.walk(char):
        for f in sorted(fs):
            if f in a.exclude:
                continue
            src = os.path.join(dp, f)
            items.append((src, os.path.join(root, os.path.relpath(src, char))))
    for d in a.doc:
        items.append((d, os.path.join(root, os.path.basename(d))))
    for spec in a.add:
        src, dest = spec.split("=", 1)
        if os.path.isdir(src):
            for dp, _, fs in os.walk(src):
                for f in sorted(fs):
                    s = os.path.join(dp, f)
                    items.append((s, os.path.join(root, dest, os.path.relpath(s, src))))
        else:
            items.append((src, os.path.join(root, dest)))
    patch = None
    if a.patch_orig and a.patch_new:
        patch = make_patch(a.patch_orig, a.patch_new, [f for f in a.patch_files.split(",") if f])
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with zipfile.ZipFile(a.out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for src, arc in items:
            z.write(src, arc)
        if patch is not None:
            z.writestr(os.path.join(root, a.patch_dest), patch)
    mb = os.path.getsize(a.out) / 1e6
    print(f"package: {a.out}  {len(items) + (patch is not None)} files, {mb:.2f} MB, root folder '{root}/'")
    if patch is not None:
        print(f"package: {a.patch_dest} {patch.count(chr(10))} lines over {a.patch_files}")
    if mb > a.max_mb:
        print(f"package: ERROR zip is {mb:.2f} MB > {a.max_mb} MB"); return 1
    return 0


def summary(a):
    tiles = []
    for spec in a.images:
        path, _, label = spec.partition("=")
        im = Image.open(path).convert("RGBA")
        s = a.height / im.height
        if im.width * s > a.max_w:
            s = a.max_w / im.width
        im = im.resize((max(1, round(im.width * s)), max(1, round(im.height * s))), Image.LANCZOS)
        bg = Image.new("RGBA", im.size, (235, 235, 235, 255)); d = ImageDraw.Draw(bg)
        for y in range(0, im.height, 16):
            for x in range(0, im.width, 16):
                if (x // 16 + y // 16) % 2:
                    d.rectangle([x, y, x + 15, y + 15], fill=(205, 205, 205, 255))
        bg.alpha_composite(im)
        tiles.append((bg.convert("RGB"), label or os.path.basename(path)))
    gap, pad, cap, top = 70, 24, 44, (60 if a.title else 0)
    W = pad * 2 + sum(t.width for t, _ in tiles) + gap * (len(tiles) - 1)
    H = top + pad * 2 + a.height + cap
    out = Image.new("RGB", (W, H), (28, 30, 38)); d = ImageDraw.Draw(out)
    f, ft = _font(20), _font(30)
    if a.title:
        d.text((pad, 16), a.title, font=ft, fill=(255, 205, 60))
    x = pad
    for i, (t, label) in enumerate(tiles):
        y = top + pad + (a.height - t.height) // 2
        out.paste(t, (x, y))
        tw = d.textlength(label, font=f)
        d.text((x + (t.width - tw) / 2, top + pad + a.height + 10), label, font=f, fill=(240, 240, 240))
        if i < len(tiles) - 1:
            cy = top + pad + a.height // 2; x0, x1 = x + t.width + 14, x + t.width + gap - 14
            d.line([x0, cy, x1, cy], fill=(255, 205, 60), width=5)
            d.polygon([(x1 + 4, cy), (x1 - 12, cy - 10), (x1 - 12, cy + 10)], fill=(255, 205, 60))
        x += t.width + gap
    out.save(a.out)
    print(f"summary: {a.out} {W}x{H}, {len(tiles)} panels")
    return 0


def main(argv):
    cmd, argv = argv[0], argv[1:]
    p = argparse.ArgumentParser(prog="forge.py " + cmd)
    if cmd == "package":
        p.add_argument("--char", required=True); p.add_argument("--out", required=True)
        p.add_argument("--root"); p.add_argument("--doc", action="append", default=[])
        p.add_argument("--add", action="append", default=[]); p.add_argument("--exclude", action="append", default=[])
        p.add_argument("--patch-orig"); p.add_argument("--patch-new"); p.add_argument("--patch-files", default="")
        p.add_argument("--patch-dest", default="roster_patch/roster.patch")
        p.add_argument("--verify", action="store_true"); p.add_argument("--max-mb", type=float, default=25.0)
        return package(p.parse_args(argv))
    p.add_argument("images", nargs="+"); p.add_argument("--out", required=True)
    p.add_argument("--height", type=int, default=520); p.add_argument("--max-w", type=int, default=900)
    p.add_argument("--title")
    return summary(p.parse_args(argv))

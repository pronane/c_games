"""forge.py cutout PHOTO [--person right|left|largest|tallest|N] --out DIR
                 [--sprite CELLWxCELLH:BASELINE:STAND] [--hd CELLWxCELLH:BASELINE:STAND] [--matte-model M]

Writes DIR/cutout.png (full-resolution transparent cut-out), landmarks.json, sprite.png (normal),
sprite_hd.png (HD), verify.png (checkerboard / magenta / green / alpha) and cutout_report.txt (PASS/FAIL).
Segmentation + scaling only (the person's own pixels)."""
import argparse, json, os, sys
from PIL import Image


def _spec(s):
    wh, b, st = s.split(":")
    w, h = wh.lower().split("x")
    return int(w), int(h), int(b), int(st)


def main(argv):
    ap = argparse.ArgumentParser(prog="forge.py cutout", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("photo")
    ap.add_argument("--person", default="largest", help="right | left | largest | tallest | center | index (0..)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--erase", action="append", default=[], metavar="X,Y[,TOL]",
                    help="remove an object the matte kept (bag, bin, post): region grown from this photo pixel; repeatable")
    ap.add_argument("--loose-px", type=int, default=10, help="keep matte pixels at most this far outside the person mask (drops touching objects)")
    ap.add_argument("--matte-model", default="", help="rembg model (default birefnet-portrait); 'grabcut' = offline pose-seeded matte")
    ap.add_argument("--landmarks-in", default="", metavar="JSON",
                    help="33 MediaPipe-format points [x,y,vis] in photo pixels (hand-placed or from another tool): "
                         "skips the pose detector; without rembg the matte is the offline pose-seeded GrabCut")
    ap.add_argument("--exclude", action="append", default=[], metavar="X,Y,R",
                    help="force a disc of the photo to background (another person, a bag); repeatable")
    ap.add_argument("--sprite", default="240x400:394:280", help="normal sprite cell WxH:baseline:stand_height")
    ap.add_argument("--hd", default="480x800:788:560", help="HD sprite cell WxH:baseline:stand_height")
    a = ap.parse_args(argv)
    from sforge import person as P
    print("Sprite Forge cutout: %s  (person = %s)" % (a.photo, a.person))
    cut, info = P.person_cutout(a.photo, a.person, a.out, a.matte_model, loose_px=a.loose_px,
                                erase=[tuple(float(v) for v in e.split(',')) for e in a.erase],
                                landmarks_in=a.landmarks_in or None,
                                exclude=[tuple(float(v) for v in e.split(',')) for e in a.exclude])
    res = P.verify(cut, a.out, info)
    for tag, spec, fn in (("sprite", a.sprite, "sprite.png"), ("HD sprite", a.hd, "sprite_hd.png")):
        w, h, b, st = _spec(spec)
        im, s = P.stand_sprite(cut, w, h, b, st, info)
        im.save(os.path.join(a.out, fn))
        print("  %-10s %s  cell %dx%d  baseline %d  stand_height %d  (scale %.3f)" % (tag, fn, w, h, b, st, s))
    print("cutout %s -> %s" % ("PASS" if res["PASS"] else "FAIL", a.out))
    return 0 if res["PASS"] else 1

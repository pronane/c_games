"""Check an out/<name>/console/ export against its preset's limits.
usage: python tools/verify_console.py out/<name> [more dirs...]     exit 1 on any FAIL"""
import json, os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from PIL import Image
from sforge import consoles


def glb_tris(path):
    with open(path, "rb") as f:
        f.read(12); n, _ = struct.unpack("<II", f.read(8)); js = json.loads(f.read(n))
    t = 0
    for m in js["meshes"]:
        for p in m["primitives"]:
            t += (js["accessors"][p["indices"]]["count"] if "indices" in p else js["accessors"][p["attributes"]["POSITION"]]["count"]) // 3
    return t


def pow2(n):
    return n > 0 and (n & (n - 1)) == 0


def check(out):
    cd = os.path.join(out, "console"); st = json.load(open(os.path.join(cd, "console.json")))
    p = consoles.PRESETS[st["console"]]; res = []
    def R(ok, msg):
        res.append(("PASS" if ok else "FAIL", msg))
    FW, FH = st["frame_w"], st["frame_h"]; mw, mh = p["frame_max"]
    R(FW <= mw and FH <= mh, "frame %dx%d <= max %dx%d" % (FW, FH, mw, mh))
    if p["tiles"]:
        tw, th = p["tile"]; R(FW % tw == 0 and FH % th == 0, "frame is a multiple of the %dx%d tile" % (tw, th))
    if p["pow2"]:
        R(pow2(FW) and pow2(FH), "frame is power of two")
    if p["key"] != "atari2600" and p.get("align", 1) > 1:
        R(FW % p["align"] == 0, "frame width multiple of %d" % p["align"])
    frames = sorted(os.listdir(os.path.join(cd, "frames")))
    n_anim = sum(a["count"] for a in st["anims"])
    R(len(frames) == n_anim, "%d frame files == %d frames in anims" % (len(frames), n_anim))
    if p["colours"] and p["key"] != "atari2600":
        pal = st["palette_native"]; disp = st["palette_display"]
        R(len(pal) <= p["colours"], "palette %d colours <= %d (+ transparent)" % (len(pal), p["colours"]))
        ok = all(consoles.snap_colour(c, p["space"])[1] == v for c, v in zip(disp, pal))
        R(ok, "every palette colour is representable in the %s colour space" % p["space"])
        worst = 0; mode_ok = True
        files = [os.path.join(cd, "frames", f) for f in frames] + [os.path.join(cd, f) for f in os.listdir(cd) if f.endswith(".png") and f != "palette.png"]
        for f in files:
            im = Image.open(f); mode_ok &= im.mode == "P"
            worst = max(worst, int(np.asarray(im).max()))
        R(mode_ok, "all frames / sheets / tiles / pages are indexed (P) PNGs (%d files)" % len(files))
        R(worst <= p["colours"], "highest palette index used %d <= %d" % (worst, p["colours"]))
    elif p["key"] == "atari2600":
        R(FW == 8, "2600 sprite is 8 px wide")
        R(st.get("colours_used", 0) <= 128, "row colours from the 128-colour NTSC palette")
    if p["tiles"] and p["key"] != "atari2600":
        R(all(b <= p["bank_tiles"] for b in st["banks"]), "tiles per bank %s <= %d" % (st["banks"], p["bank_tiles"]))
        per = {"nes2": 16, "gb2": 16}.get(p["fmt"], 32)
        for i, b in enumerate(st["banks"]):
            fn = [f for f in os.listdir(cd) if f.startswith("tiles_bank%d." % i) and not f.endswith(".png")][0]
            R(os.path.getsize(os.path.join(cd, fn)) == b * per, "%s = %d tiles x %d bytes (%s)" % (fn, b, per, p["fmt"]))
    if p["tex"]:
        for f in st["page_files"]:
            w, h = Image.open(os.path.join(cd, f)).size
            okp = w <= p["max_tex"] and h <= p["max_tex"] and (not p["pow2"] or (pow2(w) and pow2(h)))
            R(okp, "%s %dx%d <= %d%s" % (f, w, h, p["max_tex"], " pow2" if p["pow2"] else ""))
    if p["space"] == "rgba4444":
        a = np.asarray(Image.open(os.path.join(cd, st["page_files"][0])))
        R(bool(np.all(a % 17 == 0)), "page pixels are 4-bit per channel (ARGB4444)")
    if st.get("model"):
        for f in st["model"]["files"]:
            if f.endswith(".glb"):
                t = glb_tris(os.path.join(cd, f))
                R(p["tris"] is None or t <= p["tris"], "%s: %d tris <= budget %s" % (f, t, p["tris"]))
    return st, res


def main(args):
    bad = 0
    for d in args:
        st, res = check(d)
        print("%s  [%s]  %dx%d  warnings: %d" % (d, st["console"], st["frame_w"], st["frame_h"], len(st.get("warnings", []))))
        for k, m in res:
            print("   %s  %s" % (k, m)); bad += k == "FAIL"
        for w in st.get("warnings", []):
            print("   NOTE  " + w)
    print("RESULT: %s (%d checks failed)" % ("PASS" if not bad else "FAIL", bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

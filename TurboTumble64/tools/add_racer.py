#!/usr/bin/env python3
"""Turbo Tumble 64 - add a new racer to the game (no recompile needed).

PHOTO MODE - the racer is cut out of your own photo(s), nothing is redrawn:
    python tools/add_racer.py --photo front.jpg --name "Auntie Bea"
    python tools/add_racer.py --photo front.jpg --back back.jpg --side side.jpg --name "Auntie Bea" \\
        --kart 230,60,90 --kart-text "Bea's Bolt" --quip "Out of my way!" --quipstyle happy

SPEC MODE - a new cartoon racer drawn from a text description (see tools/example/racer_spec_example.txt):
    python tools/add_racer.py --spec my_racer.txt

The racer is written to assets/characters/<id>/ and shows up on the character select
screen the next time the game starts.  Run with -h for every option, and see
HOW_TO_ADD_A_RACER.txt for tips (hint boxes, extra angles, video frames).

(Sprite Forge style "build" is accepted too:  add_racer.py build --photo f.png --name qanna)
"""
import argparse
import configparser
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.path.dirname(HERE)
sys.path.insert(0, HERE)

try:
    import numpy  # noqa: F401
    import scipy  # noqa: F401
    from PIL import Image
except ImportError as e:     # pragma: no cover
    sys.exit("add_racer needs python with pillow, numpy and scipy (%s).\n"
             "On Windows just double-click tools\\add_racer.bat - it installs them for you." % e)

from racerkit import cutout as ck, views as vw          # noqa: E402

REUSE = None
WEIGHT_STATS = {"light": (3.0, 4.5, 4.0, 1.5), "medium": (3.5, 3.5, 3.5, 3.0), "heavy": (4.5, 2.5, 3.0, 4.5)}


def slug(name):
    s = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return s or "racer"


def parse_pts(v):
    if not v:
        return []
    out = []
    for part in re.split(r"[;\s]+", v.strip()):
        if part:
            x, y = part.split(",")[:2]
            out.append((float(x), float(y)))
    return out


def parse_boxes(v):
    if not v:
        return []
    out = []
    for part in re.split(r"[;\s]+", v.strip()):
        if part:
            n = [float(t) for t in part.split(",")]
            if len(n) != 4:
                raise SystemExit("a box is x0,y0,x1,y1 (got %r)" % part)
            out.append(tuple(n))
    return out


def parse_rgb(v, default):
    if not v:
        return default
    n = re.findall(r"\d+", v)
    if len(n) >= 3:
        return tuple(max(0, min(255, int(t))) for t in n[:3])
    from racerkit.spec import parse_color
    return parse_color(v, default=default)


def grab_video_frame(video, t, tmpdir):
    ff = shutil.which("ffmpeg")
    if not ff:
        raise SystemExit("reading a frame from a video needs ffmpeg on the PATH (or export the frame as a picture)")
    out = os.path.join(tmpdir, "frame_%s.png" % str(t).replace(".", "_"))
    subprocess.run([ff, "-loglevel", "error", "-y", "-ss", str(t), "-i", video, "-frames:v", "1", out], check=True)
    return out


# ------------------------------------------------------------------ photo mode ----
def view_jobs(a, tmpdir):
    """collect {angle: dict(photo, box, fg, bg, bgbox, fgbox, mask, cut, mirror)} from args + hints file"""
    jobs = {}

    def add(angle, **kw):
        j = jobs.setdefault(int(angle) % 360, {})
        j.update({k: v for k, v in kw.items() if v not in (None, "", [])})

    if a.photo:
        J = lambda v: ";".join(v) if v else None      # options may be given several times
        add(0, photo=a.photo, box=a.box, face=a.face, fg=parse_pts(J(a.fg)), bg=parse_pts(J(a.bg)), bgbox=parse_boxes(J(a.bg_box)),
            fgbox=parse_boxes(J(a.fg_box)), mask=a.mask, cut=a.cut)
    if a.back:
        add(180, photo=a.back, cut=a.back_cut or a.cut)
    if a.side:
        add(90 if not a.side_faces_left else 270, photo=a.side, cut=a.cut)
    for v in a.view or []:
        if "=" not in v:
            raise SystemExit("--view wants ANGLE=FILE, e.g. --view 45=three_quarter.jpg")
        ang, f = v.split("=", 1)
        add(int(ang), photo=f, cut=a.cut)
    if a.hints:
        cp = configparser.ConfigParser(inline_comment_prefixes=(";", "#"))
        cp.read(a.hints, encoding="utf-8-sig")
        base = os.path.dirname(os.path.abspath(a.hints))
        for sec in cp.sections():
            m = re.match(r"view\s+(-?\d+)", sec.strip(), re.I)
            if not m:
                continue
            s = cp[sec]
            photo = s.get("photo")
            if s.get("video"):
                photo = grab_video_frame(os.path.join(base, s.get("video")), float(s.get("time", "0")), tmpdir)
            elif photo:
                photo = os.path.join(base, photo)
            add(int(m.group(1)), photo=photo,
                box=s.get("box"), fg=parse_pts(s.get("fg")), bg=parse_pts(s.get("bg")),
                bgbox=parse_boxes(s.get("bgbox")), fgbox=parse_boxes(s.get("fgbox")),
                mask=os.path.join(base, s["mask"]) if s.get("mask") else None,
                cut=float(s["cut"]) if s.get("cut") else None, face=s.get("face"),
                mirror=s.get("mirror", "no").lower() in ("yes", "1", "true"))
    return jobs


def run_cutouts(jobs, workdir, log):
    cuts, fracs, faces = {}, {}, {}
    for ang in sorted(jobs):
        j = jobs[ang]
        if "photo" not in j:
            raise SystemExit("view %d has no photo" % ang)
        t0 = time.time()
        if REUSE and os.path.exists(os.path.join(REUSE, "cutout_%03d.png" % ang)):
            cuts[ang] = Image.open(os.path.join(REUSE, "cutout_%03d.png" % ang)).convert("RGBA")
            fracs[ang] = j.get("cut") or 0.6
            meta = json.load(open(os.path.join(REUSE, "cutout_%03d.json" % ang)))
            if j.get("face"):
                fx0, fy0, fx1, fy1 = [float(t) for t in j["face"].split(",")]
                faces[ang] = (fx0 - meta["offset"][0], fy0 - meta["offset"][1], fx1 - meta["offset"][0], fy1 - meta["offset"][1])
            log("  view %3d: re-used %s" % (ang, os.path.join(REUSE, "cutout_%03d.png" % ang)))
            continue
        img = ck.load_photo(j["photo"])
        box = tuple(float(t) for t in j["box"].split(",")) if isinstance(j.get("box"), str) else j.get("box")
        mask = Image.open(j["mask"]) if j.get("mask") else None
        if mask is not None and mask.size != img.size:
            mask = mask.resize(img.size, Image.NEAREST)
        rgba, off = ck.cutout(img, box, j.get("fg", []), j.get("bg", []), mask, log=log,
                              fg_boxes=j.get("fgbox", []), bg_boxes=j.get("bgbox", []))
        if j.get("mirror"):
            rgba = vw.mirror(rgba)
        cuts[ang] = rgba
        if j.get("face"):
            fx0, fy0, fx1, fy1 = [float(t) for t in j["face"].split(",")]
            faces[ang] = (fx0 - float(off[0]), fy0 - float(off[1]), fx1 - float(off[0]), fy1 - float(off[1]))
        fracs[ang] = j.get("cut") if j.get("cut") else auto_cut(rgba, off, img.size)
        if workdir:
            rgba.save(os.path.join(workdir, "cutout_%03d.png" % ang))
            with open(os.path.join(workdir, "cutout_%03d.json" % ang), "w") as f:
                json.dump({"photo": j["photo"], "offset": list(map(int, off)), "size": list(img.size), "face": faces.get(ang)}, f)
        log("  view %3d: cut out %s in %.1fs (keep top %.0f%%)" % (ang, os.path.basename(j["photo"]), time.time() - t0, 100 * fracs[ang]))
    return cuts, fracs, faces


def auto_cut(rgba, off, size):
    """head-to-lap for a full-body photo, everything for a head-and-shoulders one"""
    bottom = off[1] + rgba.height
    return 1.0 if bottom >= size[1] * 0.97 else 0.6


def photo_mode(a, out, log):
    tmp = tempfile.mkdtemp(prefix="racer_")
    jobs = view_jobs(a, tmp)
    if 0 not in jobs:
        raise SystemExit("photo mode needs a front photo: --photo FILE")
    work = a.keep_cutouts
    if work:
        os.makedirs(work, exist_ok=True)
    cuts, fracs, faces = run_cutouts(jobs, work, log)
    hair = parse_rgb(a.hair_color, None) if a.hair_color else None
    collar = parse_rgb(a.collar_color, None) if a.collar_color else None
    cells, notes, src, face0 = vw.build_views(cuts, fracs, hair_rgb=hair, collar_rgb=collar, log=log, faces=faces)
    sheet, rows = vw.sheet(cells)
    sheet.save(os.path.join(out, "sprite.png"), optimize=True)
    front = src[0]
    vw.portrait(front, face=face0).save(os.path.join(out, "portrait.png"), optimize=True)
    win, face = vw.win_sprite(front, a.quipstyle or "happy", face=face0)
    vw.bleed(win).save(os.path.join(out, "win.png"), optimize=True)
    vw.preview(cells).save(os.path.join(out, "preview.png"), optimize=True)
    shutil.rmtree(tmp, ignore_errors=True)
    return rows, face, notes


# ------------------------------------------------------------------- spec mode ----
def spec_mode(a, out, log, sp):
    from racerkit import spec, spec_draw
    P = spec.resolve(sp)
    log("  drawing %s: %s %s, %s hair (%s), %s eyes, %.0f cm, build %s" % (
        P["name"], P["age"], sp.get("ethnicity", "-"), sp.get("hair_color", "default"), P["hair_style"],
        sp.get("eye_color", "default"), P["height_cm"], P["build"]))
    cells = spec_draw.draw_sheet_cells(P, vw.FW, vw.FH)
    cells = {k: vw.fade_bottom(c, 0.04) for k, c in cells.items()}
    sheet, rows = vw.sheet(cells)
    sheet.save(os.path.join(out, "sprite.png"), optimize=True)
    spec_draw.draw_portrait(P).save(os.path.join(out, "portrait.png"), optimize=True)
    style = a.quipstyle or sp.get("quipstyle") or "happy"
    win, face = spec_draw.draw_win(P, style)
    vw.bleed(win).save(os.path.join(out, "win.png"), optimize=True)
    stand = spec_draw.draw_standing(P, 420, 640)
    pv = Image.new("RGBA", (420 + 3 * 256, 640), (70, 78, 96, 255))
    pv.alpha_composite(stand, (0, 0))
    for i, ang in enumerate((45, 90, 180)):
        pv.alpha_composite(cells[ang].resize((256, 320), Image.LANCZOS), (420 + i * 256, 160))
    pv.convert("RGB").save(os.path.join(out, "preview.png"), optimize=True)
    notes = {k: "drawn from spec" for k in cells}
    return rows, face, notes, spec_draw.size_for(P)


# ------------------------------------------------------------------------ main ----
def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "build":
        argv = argv[1:]
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_argument_group("source (pick photo mode or spec mode)")
    g.add_argument("--photo", help="front photo of the person (required for photo mode)")
    g.add_argument("--back", help="optional photo from behind (otherwise the back is invented from the front's own colours)")
    g.add_argument("--side", help="optional side photo, person facing image-RIGHT (add --side-faces-left if not)")
    g.add_argument("--side-faces-left", action="store_true")
    g.add_argument("--view", action="append", metavar="ANGLE=FILE",
                   help="any extra angle: 0 front, 45 front-3/4 (person facing image-right), 90 side, 135 back-3/4, 180 back...")
    g.add_argument("--hints", help="advanced: ini file with one [view ANGLE] section per photo/video frame (see HOW_TO_ADD_A_RACER.txt)")
    g.add_argument("--spec", help="spec mode: key=value text description of a new (fictional) racer")
    h = ap.add_argument_group("cut-out hints (front photo; pixel coordinates in the original photo)")
    h.add_argument("--box", help="x0,y0,x1,y1 rectangle around the person (strongly recommended for busy rooms)")
    h.add_argument("--fg", action="append", help="points that ARE the person: x,y;x,y")
    h.add_argument("--bg", action="append", help="points that are NOT the person (sofa, bag...): x,y;x,y")
    h.add_argument("--bg-box", action="append", help="rectangles that are NOT the person: x0,y0,x1,y1;...")
    h.add_argument("--fg-box", action="append", help="rectangles that ARE the person")
    h.add_argument("--mask", help="manual mask image (white = person, black = background, grey = let the tool decide)")
    h.add_argument("--face", help="x0,y0,x1,y1 box around the face (forehead to chin) if the automatic skin finder gets it wrong")
    h.add_argument("--cut", type=float, help="fraction of the person's height to keep, top down (default: auto, ~0.6 = head to lap)")
    h.add_argument("--back-cut", type=float)
    h.add_argument("--hair-color", help="hair colour for an invented back view, e.g. 230,200,150")
    h.add_argument("--collar-color", help="colour of a collar / bib tie drawn at the neck of an invented back view")
    h.add_argument("--keep-cutouts", metavar="DIR", help="also save the raw cut-outs here for checking (keep them out of assets!)")
    c = ap.add_argument_group("racer settings")
    c.add_argument("--name")
    c.add_argument("--id", help="folder name (default: from the name)")
    c.add_argument("--out", help="output folder (default: assets/characters/<id>)")
    c.add_argument("--tagline")
    c.add_argument("--weight", choices=list(WEIGHT_STATS), help="weight class (default medium; spec key weight_class)")
    c.add_argument("--speed", type=float); c.add_argument("--accel", type=float)
    c.add_argument("--handling", type=float); c.add_argument("--mass", type=float)
    c.add_argument("--kart", help="kart colour R,G,B"); c.add_argument("--trim", help="trim colour R,G,B")
    c.add_argument("--kart-text", help="words painted on the kart")
    c.add_argument("--kart-text-style", choices=["bubbly", "comic"], default=None)
    c.add_argument("--decal", help="use this ready-made decal.png instead of --kart-text")
    c.add_argument("--decal-frames", type=int)
    c.add_argument("--kartstyle", choices=["none", "spa", "rattle"])
    c.add_argument("--quip", help="victory line"); c.add_argument("--quipstyle", choices=["happy", "sleepy"])
    c.add_argument("--voice", type=float, help="voice pitch 0.5..2")
    c.add_argument("--size", type=float, help="driver height in the kart (world units, default 1.4; Mango Mo is 1.35)")
    c.add_argument("--seat", type=float, default=0.0, help="raise/lower the driver in the seat")
    c.add_argument("--extra-ini", action="append", default=[], help="extra key=value lines for character.ini")
    h.add_argument("--reuse-cutouts", metavar="DIR", help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    global REUSE
    REUSE = a.reuse_cutouts
    log = print
    sp = None
    if a.spec:
        from racerkit import spec as spm
        sp = spm.read_spec(a.spec)
    elif not a.photo and not a.hints:
        ap.print_help()
        return 2
    name = a.name or (sp or {}).get("name") or os.path.splitext(os.path.basename(a.photo or "racer"))[0].replace("_", " ").title()
    rid = a.id or (sp or {}).get("id") or slug(name)
    out = a.out or os.path.join(GAME, "assets", "characters", rid)
    os.makedirs(out, exist_ok=True)
    log("Making racer '%s' in %s" % (name, out))
    t0 = time.time()
    get = lambda key, dflt=None: getattr(a, key, None) if getattr(a, key, None) is not None else (sp or {}).get(key, dflt)
    if sp is not None:
        rows, face, notes, size = spec_mode(a, out, log, sp)
    else:
        rows, face, notes = photo_mode(a, out, log)
        size = 1.4
    if a.size:
        size = a.size
    # decal
    decal, frames = None, 1
    kt = a.kart_text or (sp or {}).get("kart_text")
    if a.decal:
        shutil.copy(a.decal, os.path.join(out, "decal.png")) if os.path.abspath(a.decal) != os.path.abspath(os.path.join(out, "decal.png")) else None
        decal, frames = "decal.png", a.decal_frames or 1
    elif kt:
        import make_decal as md
        style = a.kart_text_style or (sp or {}).get("kart_text_style", "bubbly")
        fr = [md.bubbly(kt)] if style == "bubbly" else [md.comic(kt, False), md.comic(kt, True)]
        sheet = Image.new("RGBA", (md.W, md.H * len(fr)), (0, 0, 0, 0))
        for i, f in enumerate(fr):
            sheet.paste(f, (0, i * md.H))
        sheet.save(os.path.join(out, "decal.png"), optimize=True)
        decal, frames = "decal.png", len(fr)
    # stats
    wc = (a.weight or (sp or {}).get("weight_class") or "medium").lower()
    wc = wc if wc in WEIGHT_STATS else "medium"
    s0 = WEIGHT_STATS[wc]
    num = lambda key, d: float(get(key)) if get(key) not in (None, "") else d
    kart = parse_rgb(a.kart or (sp or {}).get("kart"), (230, 60, 60))
    trim = parse_rgb(a.trim or (sp or {}).get("trim"), (245, 245, 245))
    quip = get("quip")
    qs = get("quipstyle") or ("happy" if quip else None)
    lines = ["; Turbo Tumble 64 character - made by tools/add_racer.py (%s mode) %s" % ("spec" if sp else "photo", time.strftime("%Y-%m-%d")),
             "name = %s" % name]
    if get("tagline"):
        lines.append("tagline = %s" % get("tagline"))
    lines += ["weight = %s" % wc, "speed = %.1f" % num("speed", s0[0]), "accel = %.1f" % num("accel", s0[1]),
              "handling = %.1f" % num("handling", s0[2]), "mass = %.1f" % num("mass", s0[3]),
              "kart = %d,%d,%d" % kart, "trim = %d,%d,%d" % trim, "voice = %.2f" % num("voice", 1.0),
              "sprite = sprite.png", "angles = 8", "rows = %d" % rows, "size = %.2f" % size, "seat = %.2f" % a.seat,
              "portrait = portrait.png", "winsprite = win.png", "face = %.3f,%.3f" % face]
    if a.kartstyle and a.kartstyle != "none":
        lines.append("kartstyle = %s" % a.kartstyle)
    if quip:
        lines.append("quip = %s" % quip)
    if qs:
        lines.append("quipstyle = %s" % qs)
    if decal:
        lines.append("decal = %s" % decal)
        if frames > 1:
            lines.append("decalframes = %d" % frames)
    lines += ["; Sprite Forge compatible info (ignored by the game)",
              "frame_w = %d" % vw.FW, "frame_h = %d" % vw.FH, "ground_y = %d" % vw.FH, "scale = %.2f" % size]
    lines += a.extra_ini
    with open(os.path.join(out, "character.ini"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    atlas = {"image": "sprite.png", "frame_w": vw.FW, "frame_h": vw.FH, "pivot": "bottom-centre",
             "frames": [{"angle": ang, "x": (i % 4) * vw.FW, "y": (i // 4) * vw.FH, "source": notes.get(ang, "")}
                        for i, ang in enumerate(vw.ANGLES)]}
    with open(os.path.join(out, "atlas.json"), "w") as f:
        json.dump(atlas, f, indent=1)
    log("  angles: " + ", ".join("%d=%s" % (k, notes[k]) for k in sorted(notes)))
    log("Done in %.0fs.  Files: %s" % (time.time() - t0, ", ".join(sorted(os.listdir(out)))))
    log("Start the game - '%s' is on the character select screen." % name)
    return 0


if __name__ == "__main__":
    sys.exit(main())

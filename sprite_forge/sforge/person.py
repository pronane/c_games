"""v7.1 PERSON cut-out: one chosen person out of a photo with several people in it.

    forge.py cutout PHOTO --person right --out DIR      (also: build --cutout person --person right)

1. matte   : rembg segmentation (default model birefnet-portrait; env SFS_REMBG_MODEL / --matte-model),
             fallback isnet-general-use -> u2net -> the built-in border-colour cut-out
2. people  : MediaPipe PoseLandmarker per-person masks + 33 landmarks (tools/person_mask.py, run in the
             mediapipe Python like `forge.py mocap`) - picks right / left / largest / center / index N
3. assign  : every foreground pixel goes to the person whose mask is strongest there (nearest person
             where no mask covers it); only the chosen person is kept, largest connected piece only
4. clean   : alpha < 12 -> 0, > 243 -> 255; edge colours de-fringed from the nearest solid pixel
             (no background halo); trimmed with a small margin
Segmentation only: every kept pixel is the photo's own pixel.  Nothing is generated or redrawn.
Writes DIR/cutout.png + DIR/landmarks.json (pose landmarks in cutout pixel coords) + DIR/people/*.
"""
from __future__ import annotations
import json, os, subprocess, sys, time
import numpy as np
from PIL import Image, ImageOps
from scipy import ndimage as ndi

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MATTE_MODELS = ["birefnet-portrait", "isnet-general-use", "u2net_human_seg", "u2net"]


def matte(im_rgb, model="", log=print):
    try:
        from rembg import remove, new_session
    except Exception:
        log("  ! rembg not installed (pip install rembg[cpu]) - built-in border-colour cut-out")
        from .imaging import threshold_cutout
        return np.asarray(threshold_cutout(im_rgb.convert("RGBA")).getchannel("A")).astype(np.float32) / 255, "threshold"
    chain = [m for m in [model, os.environ.get("SFS_REMBG_MODEL", "")] if m] + MATTE_MODELS
    for m in chain:
        try:
            t = time.time()
            out = remove(im_rgb, session=new_session(m))
            log("  matte: rembg %s (%.1fs)" % (m, time.time() - t))
            return np.asarray(out.getchannel("A")).astype(np.float32) / 255, m
        except Exception as e:
            log("  matte model %s failed: %s" % (m, str(e)[:120]))
    raise RuntimeError("no rembg model could run")


def detect_people(photo, out_dir, log=print):
    from . import mocap
    py = mocap.find_pose_python()
    model = mocap.find_model("heavy") or mocap.find_model("full") or mocap.find_model("lite")
    if py is None or model is None:
        raise RuntimeError("person selection needs mediapipe + a pose model (python tools/setup_pose.py), "
                           "or set SFS_POSE_PYTHON / SFS_POSE_MODEL")
    r = subprocess.run([py, os.path.join(HERE, "tools", "person_mask.py"), photo, out_dir, "--model", model],
                       capture_output=True, text=True)
    pj = os.path.join(out_dir, "people.json")
    if not os.path.isfile(pj):
        raise RuntimeError("person detection failed:\n" + (r.stderr[-1500:] or r.stdout[-1500:]))
    d = json.load(open(pj))
    log("  people: %d detected (MediaPipe %s)" % (len(d["people"]), os.path.basename(model)))
    return d


def choose(people, which):
    if not people:
        raise RuntimeError("no person detected in the photo")
    w = str(which).lower()
    if w.isdigit():
        return people[int(w)]
    if w == "right":
        return max(people, key=lambda p: p["cx"])
    if w == "left":
        return min(people, key=lambda p: p["cx"])
    if w == "tallest":
        return max(people, key=lambda p: p["box"][3] - p["box"][1])
    return max(people, key=lambda p: p["area"])          # largest / adult / auto


def _capsule(shape, p0, p1, r):
    h, w = shape
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    (x0, y0), (x1, y1) = p0, p1
    vx, vy = x1 - x0, y1 - y0
    L2 = max(1e-6, vx * vx + vy * vy)
    t = np.clip(((xx - x0) * vx + (yy - y0) * vy) / L2, 0, 1)
    return (xx - x0 - t * vx) ** 2 + (yy - y0 - t * vy) ** 2 <= r * r


def repair_hands(keep, fg, rgb, L):
    """Where two people touch (holding hands) the per-person masks are coarse and punch holes in
    the chosen person's hand.  Inside a capsule over each of the chosen person's hands (wrist ->
    knuckles, from the pose landmarks), skin-coloured foreground pixels are given back to them;
    clothing of the other person (non-skin colours) stays removed."""
    added = 0
    r_, g_, b_ = [rgb[..., i].astype(np.int32) for i in range(3)]
    skin = (r_ > 70) & (r_ > g_ + 10) & (r_ > b_ + 8)       # warm (skin) - not green / white / black clothing
    sh = np.hypot(L[11][0] - L[12][0], L[11][1] - L[12][1])
    for wr, tips in ((15, (17, 19, 21)), (16, (18, 20, 22))):
        wx, wy = L[wr][0], L[wr][1]
        tx = sum(L[i][0] for i in tips) / 3.0; ty = sum(L[i][1] for i in tips) / 3.0
        ex, ey = wx + (tx - wx) * 1.9, wy + (ty - wy) * 1.9          # fingertips are beyond the knuckles
        cap = _capsule(keep.shape, (wx, wy), (ex, ey), 0.13 * sh)
        add = cap & fg & skin & ~keep
        added += int(add.sum())
        keep = keep | add
    return keep, added


def defringe(rgb, a, solid=0.96):
    """edge pixels take the colour of the nearest solid pixel of the figure (kills background halo)"""
    inner = a >= solid
    if not inner.any():
        return rgb
    _, (iy, ix) = ndi.distance_transform_edt(~inner, return_indices=True)
    edge = (a > 0) & ~inner
    out = rgb.copy()
    near = rgb[iy, ix]
    k = (1.0 - a[..., None]) ** 0.5           # the more transparent, the more of the solid colour
    out[edge] = (rgb[edge] * (1 - k[edge]) + near[edge] * k[edge]).astype(np.uint8)
    return out


def erase_region(keep, rgb, seed):
    """seed = (x, y[, tol]) in photo pixels. Grows a connected region of similar colour (RGB distance to the
    seed's 7x7 mean < tol) inside `keep`, then dilates it 2 px to take its anti-aliased edge too."""
    x, y = int(seed[0]), int(seed[1])
    tol = float(seed[2]) if len(seed) > 2 else 30.0
    f = rgb.astype(np.float32)
    ref = f[max(0, y - 3):y + 4, max(0, x - 3):x + 4].reshape(-1, 3).mean(0)
    sim = (np.sqrt(((f - ref) ** 2).sum(-1)) < tol) & keep
    lab, _ = ndi.label(sim)
    if lab[y, x] == 0:
        return keep, 0
    reg = ndi.binary_dilation(lab == lab[y, x], iterations=2) & keep
    reg = ndi.binary_fill_holes(reg) & keep
    k2 = keep & ~reg
    # tidy the cut: thin dark spurs left along the erased object's border are opened away (only near it)
    band = ndi.binary_dilation(reg, iterations=14)
    opened = ndi.binary_opening(k2, structure=np.ones((3, 3)), iterations=4)
    spur = band & k2 & ~opened
    k2 &= ~spur
    return k2, int(reg.sum() + spur.sum())


def _load_landmarks_in(path):
    """33 x [x, y, vis] in photo pixels: {"landmarks": [...]} or a bare list."""
    d = json.load(open(path))
    L = d["landmarks"] if isinstance(d, dict) else d
    if len(L) != 33:
        raise RuntimeError("%s: need 33 MediaPipe-format landmarks, got %d" % (path, len(L)))
    return [[float(v) for v in l[:3]] + ([] if len(l) >= 3 else [1.0]) for l in L]


def _have_rembg():
    try:
        import rembg  # noqa: F401
        return True
    except Exception:
        return False


def person_cutout(photo, which="largest", out_dir="", model="", margin=12, loose_px=10, erase=(), log=print,
                  landmarks_in=None, exclude=()):
    im = ImageOps.exif_transpose(Image.open(photo)).convert("RGB")
    W, H = im.size
    out_dir = out_dir or os.path.splitext(photo)[0] + "_cutout"
    os.makedirs(out_dir, exist_ok=True)
    if landmarks_in:
        # landmarks from outside (hand-placed, another detector): no pose network needed.  The matte is rembg
        # when installed (limited to the region around this skeleton), else the offline pose-seeded GrabCut.
        from . import posematte
        lms_in = _load_landmarks_in(landmarks_in)
        log("  landmarks: %s (33 points supplied, detector skipped)" % landmarks_in)
        gc = posematte.pose_grabcut(im, lms_in, exclude, log=log)
        if _have_rembg() and model != "grabcut":
            A, mname = matte(im, model, log)
            A = np.where(ndi.binary_dilation(gc > 0.1, iterations=12), A, 0.0)
        else:
            A, mname = gc, "pose-grabcut"
        people = [{"index": 0, "landmarks": lms_in, "mask": None, "cx": 0, "area": 1}]
        sel = people[0]
        masks = posematte.person_mask_from_alpha(A)[None]
    else:
        A, mname = matte(im, model, log)
        pdir = os.path.join(out_dir, "people")
        d = detect_people(photo, pdir, log)
        people = d["people"]
        sel = choose(people, which)
        masks = np.stack([np.asarray(Image.open(os.path.join(pdir, p["mask"]))).astype(np.float32) / 255 for p in people])
        if mname == "threshold":     # no rembg: the border-colour cut-out fails on real backgrounds - use the pose
            from . import posematte  # the detector just gave us to seed GrabCut instead
            A, mname = posematte.pose_grabcut(im, sel["landmarks"], exclude, log=log), "pose-grabcut"
    owner = masks.argmax(0)
    weak = masks.max(0) < 0.15
    if weak.any() and len(people) > 1:      # nobody's mask covers it: nearest person
        dists = np.stack([ndi.distance_transform_edt(m < 0.5) for m in masks])
        owner = np.where(weak, dists.argmin(0), owner)
    mine = (owner == sel["index"])
    # matte pixels nobody's person mask covers (bags, bins, posts touching the body): keep only a thin
    # band (loose_px) around the chosen person's mask, so hair / finger edges survive but objects do not
    own_d = ndi.distance_transform_edt(masks[sel["index"]] < 0.5)
    dropped = weak & mine & (own_d > loose_px) & (A > 0.05)
    mine &= ~(weak & (own_d > loose_px))
    if dropped.any():
        log("  removed %d matte px outside every person mask (background objects touching the body)" % int(dropped.sum()))
    fg = A > 0.05
    keep = fg & mine
    rep = np.zeros_like(keep)
    if len(people) > 1:
        k0 = keep.copy()
        keep, nrep = repair_hands(keep, fg, np.asarray(im), sel["landmarks"])
        rep = keep & ~k0
        if nrep:
            log("  hand contact repair: %d skin px given back to the chosen person's hands (people holding hands)" % nrep)
    for seed in erase or ():             # "click to erase": remove a colour region grown from a seed point
        keep, ne = erase_region(keep, np.asarray(im), seed)
        log("  erase seed %s: removed %d px (object kept by the matte, not the person)" % (seed, ne))
    lab, n = ndi.label(keep & (A > 0.5))
    if n == 0:
        raise RuntimeError("the chosen person has no foreground pixels")
    sizes = ndi.sum(np.ones_like(lab), lab, range(1, n + 1))
    body = lab == (1 + int(np.argmax(sizes)))
    body = ndi.binary_fill_holes(body) & keep | body
    region = ndi.binary_dilation(body, iterations=2) & keep
    a = np.where(region, A, 0.0)
    a[a < 12 / 255] = 0
    a[a > 243 / 255] = 1.0
    rgb = defringe(np.asarray(im).copy(), a)
    rgba = np.dstack([rgb, (a * 255).round().astype(np.uint8)])
    ys, xs = np.nonzero(rgba[..., 3] > 0)
    x0, y0 = max(0, xs.min() - margin), max(0, ys.min() - margin)
    x1, y1 = min(W, xs.max() + 1 + margin), min(H, ys.max() + 1 + margin)
    cut = Image.fromarray(rgba[y0:y1, x0:x1], "RGBA")
    cut.save(os.path.join(out_dir, "cutout.png"))
    lms = [[x - x0, y - y0, v] for x, y, v in sel["landmarks"]]
    others = [i for i in range(len(people)) if i != sel["index"]]
    info = {"photo": os.path.abspath(photo), "person": which, "person_index": sel["index"], "people": len(people),
            "crop": [int(x0), int(y0), int(x1), int(y1)], "matte_model": mname, "landmarks": lms,
            "landmark_format": "mediapipe pose 33: [x, y, visibility] in cutout.png pixels"}
    json.dump(info, open(os.path.join(out_dir, "landmarks.json"), "w"), indent=1)
    # other people's masks in cutout coords (used by verify to prove none of their pixels survived)
    if others:
        om = (masks[others].max(0) > 0.5) & (masks[sel["index"]] < 0.5)
        Image.fromarray((om[y0:y1, x0:x1] * 255).astype(np.uint8)).save(os.path.join(out_dir, "others_mask.png"))
        Image.fromarray((rep[y0:y1, x0:x1] * 255).astype(np.uint8)).save(os.path.join(out_dir, "hand_repair_mask.png"))
    log("  person '%s' = #%d of %d  -> cutout %dx%d" % (which, sel["index"], len(people), cut.width, cut.height))
    return cut, info


# ---------------------------------------------------------------------------------------------- verify
def checker(size, sq=16):
    w, h = size
    yy, xx = np.mgrid[0:h, 0:w]
    c = (((yy // sq) + (xx // sq)) % 2).astype(np.uint8)
    a = np.where(c[..., None] == 1, np.array([205, 205, 205], np.uint8), np.array([250, 250, 250], np.uint8))
    return Image.fromarray(a.astype(np.uint8), "RGB")


def verify(cut, out_dir, info=None, log=print):
    """Programmatic cut-out checks + verify.png (checkerboard / magenta / green / alpha)."""
    a = np.asarray(cut.getchannel("A")).astype(np.float32) / 255
    rgb = np.asarray(cut.convert("RGB")).astype(np.float32)
    h, w = a.shape
    res = {}
    border = np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]])
    res["border_fully_transparent"] = bool((border == 0).all())
    vis = a > 0
    res["transparent_fraction"] = round(float((a == 0).mean()), 3)
    semi = (a > 0) & (a < 1)
    res["semi_transparent_px"] = int(semi.sum())
    lab, n = ndi.label(a > 0.05, structure=np.ones((3, 3)))
    sizes = sorted(ndi.sum(np.ones_like(lab), lab, range(1, n + 1)), reverse=True) if n else []
    res["pieces"] = int(n)
    res["stray_px_outside_main_piece"] = int(sum(sizes[1:])) if n > 1 else 0
    # halo: semi-transparent edge pixels vs nearest solid figure colour (background would differ strongly)
    inner = a >= 0.96
    if inner.any() and semi.any():
        _, (iy, ix) = ndi.distance_transform_edt(~inner, return_indices=True)
        diff = np.abs(rgb - rgb[iy, ix]).sum(-1)
        res["edge_colour_diff_mean"] = round(float(diff[semi].mean()), 1)
        res["edge_halo_px(diff>120)"] = int(((diff > 120) & semi & (a > 0.25)).sum())
    om_p = os.path.join(out_dir, "others_mask.png")
    if os.path.isfile(om_p):
        om = np.asarray(Image.open(om_p)) > 127
        rp_p = os.path.join(out_dir, "hand_repair_mask.png")
        rp = (np.asarray(Image.open(rp_p)) > 127) if os.path.isfile(rp_p) else np.zeros_like(om)
        res["other_person_px_kept"] = int((om & (a > 0.05) & ~rp).sum())
        res["clasped_hand_px_in_other_mask"] = int((om & (a > 0.05) & rp).sum())
    if info and info.get("landmarks"):
        L = info["landmarks"]
        feet_y = max(L[i][1] for i in (29, 30, 31, 32))
        rows = np.nonzero(vis.any(1))[0]
        res["lowest_figure_row"] = int(rows.max())
        res["lowest_foot_landmark_row"] = int(round(feet_y))
        res["feet_included"] = bool(rows.max() >= feet_y - 4)
        res["head_top_row"] = int(rows.min())
    ok = (res["border_fully_transparent"] and res.get("other_person_px_kept", 0) == 0 and res.get("feet_included", True)
          and res["stray_px_outside_main_piece"] < 50 and res.get("edge_halo_px(diff>120)", 0) < 0.002 * vis.sum())
    res["PASS"] = bool(ok)
    # verify.png
    tiles = []
    for bg in ("checker", (255, 0, 255), (0, 200, 0), "alpha"):
        if bg == "alpha":
            t = Image.fromarray((a * 255).astype(np.uint8)).convert("RGB")
        else:
            t = checker(cut.size) if bg == "checker" else Image.new("RGB", cut.size, bg)
            t.paste(cut, (0, 0), cut)
        tiles.append(t)
    pad = 10
    sheet = Image.new("RGB", (4 * w + 5 * pad, h + 2 * pad), (40, 40, 40))
    for i, t in enumerate(tiles):
        sheet.paste(t, (pad + i * (w + pad), pad))
    sheet.save(os.path.join(out_dir, "verify.png"))
    with open(os.path.join(out_dir, "cutout_report.txt"), "w") as f:
        f.write("Sprite Forge cut-out verification\n")
        for k, v in res.items():
            f.write("  %-34s %s\n" % (k, v))
    for k, v in res.items():
        log("  %-34s %s" % (k, v))
    return res


def stand_sprite(cut, cell_w, cell_h, baseline, stand_h, info=None):
    """the cut-out scaled to stand_h (head top -> feet) with its feet on the baseline, centred on the body"""
    a = np.asarray(cut.getchannel("A"))
    rows = np.nonzero((a > 40).any(1))[0]
    top, bot = rows.min(), rows.max() + 1
    s = stand_h / float(bot - top)
    im = cut.resize((max(1, round(cut.width * s)), max(1, round(cut.height * s))), Image.LANCZOS)
    if info and info.get("landmarks"):
        L = info["landmarks"]
        cx = (L[23][0] + L[24][0] + L[11][0] + L[12][0]) / 4 * s    # body centre between hips / shoulders
    else:
        from .imaging import alpha_centroid_x
        cx = alpha_centroid_x(im)
    cell = Image.new("RGBA", (cell_w, cell_h), (0, 0, 0, 0))
    composite(cell, im, int(round(cell_w / 2 - cx)), int(round(baseline - bot * s)))
    return cell, s


def composite(dst, im, x, y):
    """alpha-composite im onto dst at (x, y) - any offset, clipped (keeps soft edges exact, unlike paste-with-mask)"""
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(dst.width, x + im.width), min(dst.height, y + im.height)
    if x1 <= x0 or y1 <= y0:
        return dst
    dst.alpha_composite(im.crop((x0 - x, y0 - y, x1 - x, y1 - y)), (x0, y0))
    return dst


"""Style lock / match (v9.4): learn a game's sprite style from its own art and restyle a character to fit.

    python tools/style_match.py REF  SRC_OUT  DST_OUT        REF = a folder of the game's sprites (or one sheet)
    style = analyse(ref_images)  ->  {palette, pixel, outline, outline_px, sat, val, contrast}
    restyle(image, style)        ->  image in that style

What is measured from the reference (nothing hand-tuned per game):
  pixel      the art's pixel size: the most common run length of identical colours (1 = smooth / painted art)
  palette    up to 32 colours by k-means over the opaque pixels (fewer when the art itself uses fewer)
  outline    the colour and thickness of the ring just inside each silhouette, if it is clearly darker than the
             interior (most pixel / cartoon art); 0 = no outline
  sat / val  median saturation and brightness, so a washed-out photo is pushed towards the game's look
Applied in that order: saturation / brightness gain -> pixelate to the reference pixel size -> palette (no dither,
pixel art style) -> outline.  Proportions are reported (head : height) but not changed - that is --proportions."""
from __future__ import annotations
import glob, json, os
import numpy as np
from PIL import Image
from scipy import ndimage as ndi


def _images(ref):
    if os.path.isdir(ref):
        ps = sorted(glob.glob(os.path.join(ref, "**", "*.png"), recursive=True))
    else:
        ps = [ref]
    return [Image.open(p).convert("RGBA") for p in ps[:60]]


def _runs(a):
    """pixel-art block size: the largest k for which (almost) every opaque pixel equals the top-left pixel of its
    k x k block, for some block offset (1 = smooth / painted art)"""
    al = a[..., 3] > 128
    if al.sum() < 50:
        return 1
    rgb = a[..., :3].astype(np.int32)
    H, W = al.shape
    for k in (8, 6, 5, 4, 3, 2):
        best = 0.0
        for oy in range(k):
            for ox in range(k):
                ys = np.arange(H); xs = np.arange(W)
                by = np.clip(ys - (ys - oy) % k, 0, H - 1); bx = np.clip(xs - (xs - ox) % k, 0, W - 1)
                src = rgb[by][:, bx]
                m = al & al[by][:, bx]
                if m.sum() < 50:
                    continue
                best = max(best, float(np.all(src[m] == rgb[m], -1).mean()))
                if best > 0.97:
                    return k
    return 1


def _hsv_stats(px):
    import colorsys
    s = px[:, :3].astype(np.float32) / 255.0
    mx, mn = s.max(1), s.min(1)
    sat = np.where(mx > 1e-6, (mx - mn) / np.maximum(mx, 1e-6), 0)
    return float(np.median(sat)), float(np.median(mx))


def analyse(ref, max_colours=32):
    ims = _images(ref)
    if not ims:
        raise ValueError("no reference images in %s" % ref)
    px, pix, outl, thick, inner, figh = [], [], [], [], [], []
    for im in ims:
        a = np.asarray(im)
        al = a[..., 3] > 128
        if al.sum() < 50:
            continue
        rows = np.nonzero(al.any(1))[0]
        figh.append(int(rows.max() - rows.min() + 1))
        pix.append(_runs(a))
        px.append(a[al][:, :3][:: max(1, int(al.sum() // 4000))])
        ring = al & ~ndi.binary_erosion(al)
        core = ndi.binary_erosion(al, iterations=3)
        if ring.sum() > 20 and core.sum() > 20:
            Lr = a[ring][:, :3].mean(1); Lc = a[core][:, :3].mean(1)
            outl.append(np.median(a[ring][:, :3], 0)); inner.append(float(np.median(Lc) - np.median(Lr)))
            t = 1
            for k in range(1, 5):          # thickness: rings stay dark this many pixels in
                rk = ndi.binary_erosion(al, iterations=k) & ~ndi.binary_erosion(al, iterations=k + 1)
                if rk.sum() and np.median(a[rk][:, :3].mean(1)) < np.median(Lr) + 18:
                    t = k + 1
                else:
                    break
            thick.append(t)
    P = np.concatenate(px).astype(np.float32)
    uniq = len(np.unique((P // 4).astype(np.int32) @ np.array([1, 64, 4096]), axis=0))
    n = int(min(max_colours, max(4, uniq)))
    from sklearn.cluster import MiniBatchKMeans
    km = MiniBatchKMeans(n_clusters=n, n_init=3, random_state=0, batch_size=2048).fit(P)
    pal = [tuple(int(v) for v in c) for c in km.cluster_centers_]
    pixel = int(np.median(pix)) if pix else 1
    has_out = bool(inner) and float(np.median(inner)) > 35
    sat, val = _hsv_stats(P)
    style = {"pixel": pixel, "palette": pal, "n_colours": int(min(max_colours, max(6, uniq))), "outline": [int(v) for v in np.median(outl, 0)] if has_out else None,
             "outline_px": int(np.median(thick)) if has_out else 0, "sat": round(sat, 3), "val": round(val, 3),
             "colours_in_ref": uniq, "n_ref": len(ims), "fig_h": int(np.median(figh)) if figh else 0,
             "pixel_art": uniq <= 64}
    return style


def restyle(im, style, src_stats=None, strength=1.0, src_fig_h=None):
    im = im.convert("RGBA")
    a = np.asarray(im).astype(np.float32)
    al = a[..., 3] > 100
    if not al.any():
        return im
    # 1) saturation / brightness towards the reference
    if src_stats is None:
        src_stats = _hsv_stats(a[al].astype(np.uint8))
    s0, v0 = src_stats
    rgb = a[..., :3] / 255.0
    mean = rgb.mean(-1, keepdims=True)
    ks = np.clip((style["sat"] / max(1e-3, s0)) ** strength, 1.0, 1.8)    # only ever more vivid
    kv = np.clip((style["val"] / max(1e-3, v0)) ** strength, 0.8, 1.25)
    rgb = np.clip((mean + (rgb - mean) * ks) * kv, 0, 1)
    a[..., :3] = rgb * 255
    out = Image.fromarray(a.clip(0, 255).astype(np.uint8), "RGBA")
    W, H = out.size
    # 2) pixel size
    p = max(1, int(style.get("pixel", 1)))
    if style.get("pixel_art") and style.get("fig_h") and src_fig_h:      # same art resolution as the game's sprites
        p = max(1, int(round(p * src_fig_h / float(style["fig_h"]))))   # block size x figure-size ratio
    if p > 1:
        small = out.resize((max(1, W // p), max(1, H // p)), Image.BOX)
        sa = small.getchannel("A").point(lambda v: 255 if v > 110 else 0)
        small.putalpha(sa)
        out = small.resize((small.width * p, small.height * p), Image.NEAREST)
        out = out.crop((0, 0, W, H)) if out.size != (W, H) else out
        if out.size != (W, H):
            c = Image.new("RGBA", (W, H), (0, 0, 0, 0)); c.paste(out, (0, 0)); out = c
    # 3) palette: as many colours as the reference uses, from the CHARACTER's own colours (a game's palette belongs
    #    to its own characters - forcing Kairo's reds onto a green jumper is wrong); colours within dE~14 of a
    #    reference colour (skin, black, white) snap to the game's exact value
    pal = style.get("palette") or []
    n = int(style.get("n_colours") or len(pal) or 0)
    if n:
        o = np.asarray(out); m = o[..., 3] > 110
        px = o[m][:, :3].astype(np.float32)
        if len(px) > n:
            from sklearn.cluster import MiniBatchKMeans
            sub = px[:: max(1, len(px) // 20000)]
            own = MiniBatchKMeans(n_clusters=n, n_init=2, random_state=0, batch_size=2048).fit(sub).cluster_centers_
            if pal:
                ref = np.array(pal, np.float32)
                d = np.linalg.norm(own[:, None] - ref[None], axis=-1)
                j = d.argmin(1)
                own = np.where((d.min(1) < 26)[:, None], ref[j], own)
            pim = Image.new("P", (1, 1))
            flat = [int(v) for c in own for v in c][:768]
            pim.putpalette(flat + [0] * (768 - len(flat)))
            q = out.convert("RGB").quantize(palette=pim, dither=Image.Dither.NONE).convert("RGB")
            q.putalpha(out.getchannel("A").point(lambda v: 255 if v > 110 else 0))
            out = q
    # 4) outline
    if style.get("outline") and style.get("outline_px", 0) > 0:
        A = np.asarray(out)[..., 3] > 0
        t = int(style["outline_px"]) * max(1, p)
        grow = ndi.binary_dilation(A, iterations=max(1, t // 2 + (t % 2)))
        ring = grow & ~A
        o = np.asarray(out).copy()
        o[ring, :3] = style["outline"]; o[ring, 3] = 255
        # and darken the inner edge so the line reads at the reference thickness
        inner = A & ~ndi.binary_erosion(A, iterations=max(1, t // 2))
        o[inner, :3] = (np.asarray(o[inner, :3], np.float32) * 0.35 + np.array(style["outline"]) * 0.65).astype(np.uint8)
        out = Image.fromarray(o, "RGBA")
    return out


def restyle_build(src, dst, style, log=print):
    """copy a Sprite Forge output folder and restyle every frame + rebuild atlas.png from the frames"""
    import shutil
    if os.path.abspath(src) != os.path.abspath(dst):
        if os.path.isdir(dst):
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
    js = json.load(open(os.path.join(dst, "atlas.json")))
    meta, an = js["meta"], js["animations"]
    fw, fh = meta["frame_w"], meta["frame_h"]
    first = Image.open(os.path.join(dst, "moves", an[next(iter(an))]["frames"][0] + ".png")).convert("RGBA")
    a0 = np.asarray(first); stats = _hsv_stats(a0[a0[..., 3] > 100])
    r0 = np.nonzero((a0[..., 3] > 100).any(1))[0]; fig_h = int(r0.max() - r0.min() + 1) if len(r0) else None
    pages = {}
    for mv, a in an.items():
        for i, f in enumerate(a["frames"]):
            p = os.path.join(dst, "moves", f + ".png")
            im = restyle(Image.open(p), style, stats, src_fig_h=fig_h)
            im.save(p)
            img = a.get("image", "atlas.png")
            if img not in pages:
                pages[img] = Image.open(os.path.join(dst, img)).convert("RGBA")
                pages[img] = Image.new("RGBA", pages[img].size, (0, 0, 0, 0))
            pages[img].paste(im, (i * fw, a["row"] * fh))
    for img, page in pages.items():
        page.save(os.path.join(dst, img))
    json.dump(style, open(os.path.join(dst, "style_match.json"), "w"), indent=1)
    log("style match (%s): pixel %d (x%s for this figure), %d colours, outline %s x%d, saturation %.2f -> %s" % (
        "pixel art" if style.get("pixel_art") else "painted", style["pixel"],
        round(style["pixel"] * fig_h / float(style["fig_h"]), 1) if style.get("pixel_art") and style.get("fig_h") and fig_h else 1,
        len(style["palette"]), style["outline"], style["outline_px"], style["sat"], dst))

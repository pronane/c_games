#!/usr/bin/env python3
"""
make_face.py - cut a crisp HD face sprite out of a photo for a 3D racer's head (v7).

    python tools/make_face.py photo.jpg --center 855,1032 --radii 116,138 --out assets/characters/baby_eabha \
           --eyes 815,1000,920,995 --win happy
    python tools/make_face.py photo.jpg --center 655,832 --radii 104,128 --out assets/characters/towelhead_qanna \
           --eyes 610,788,708,782 --win sleepy

Writes face.png (normal) and face_win.png (victory mood) - 256x320 RGBA ovals:
  * an elliptical crop of the face (brows to chin) with a short soft edge so it blends into the
    3D head's skin, a light colour pop (saturation/contrast), an unsharp-mask for crisp detail and
    a very light shade at the rim so it sits on the round head instead of looking flat;
  * --win happy  : warmer, brighter, rosier cheeks (Baby Eabha's "Car!")
  * --win sleepy : cooler/desaturated, heavy half-closed lids, dark under-eye bags and brows
                   slanted down into a scowl (Towelhead Qanna's "I didn't sleep last night")
  * prints the average skin colour so the 3D head can be matched to it.
Only the processed crops are written; the original photo is never copied into the game folder.
"""
import argparse, os, math
from PIL import Image, ImageFilter, ImageEnhance, ImageDraw, ImageChops
import numpy as np

W, H = 256, 320

def pair(s): return tuple(float(v) for v in s.split(","))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("photo"); ap.add_argument("--center", required=True); ap.add_argument("--radii", required=True)
    ap.add_argument("--eyes", required=True, help="lx,ly,rx,ry in photo pixels")
    ap.add_argument("--out", required=True); ap.add_argument("--win", choices=["happy", "sleepy"], required=True)
    ap.add_argument("--feather", type=float, default=0.12)
    a = ap.parse_args()
    cx, cy = pair(a.center); rx, ry = pair(a.radii); ex = pair(a.eyes)
    src = Image.open(a.photo).convert("RGB")
    box = (cx - rx, cy - ry, cx + rx, cy + ry)
    face = src.crop(tuple(int(round(v)) for v in box)).resize((W, H), Image.LANCZOS)
    sx, sy = W/(2*rx), H/(2*ry)
    eyes = [((ex[0] - box[0])*sx, (ex[1] - box[1])*sy), ((ex[2] - box[0])*sx, (ex[3] - box[1])*sy)]
    # colour pop + crisp detail
    face = ImageEnhance.Color(face).enhance(1.16)
    face = ImageEnhance.Contrast(face).enhance(1.07)
    face = face.filter(ImageFilter.UnsharpMask(radius=1.6, percent=85, threshold=2))
    # elliptical alpha with a short feather, and a spherical shade toward the rim
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    d = np.sqrt(((xx + 0.5 - W/2)/(W/2))**2 + ((yy + 0.5 - H/2)/(H/2))**2)
    f = a.feather
    alpha = np.clip((1.0 - d)/f, 0, 1)
    shade = 1.0 - 0.04*np.clip((d - 0.7)/0.3, 0, 1)
    arr = np.asarray(face).astype(np.float32)
    inner = d < 0.6
    skin = arr[inner].reshape(-1, 3)
    lum = skin.mean(axis=1)
    skin = skin[(lum > np.percentile(lum, 35)) & (lum < np.percentile(lum, 90))]
    print("average skin: %d,%d,%d" % tuple(int(v) for v in skin.mean(axis=0)))

    def finish(rgb, name):
        rgb = np.clip(rgb*shade[..., None], 0, 255)
        out = np.dstack([rgb, alpha*255]).astype(np.uint8)
        Image.fromarray(out, "RGBA").save(os.path.join(a.out, name))
        print("wrote", os.path.join(a.out, name))

    finish(arr.copy(), "face.png")
    eyeD = math.dist(*eyes)
    if a.win == "happy":
        w = arr.copy()
        w = w*np.array([1.06, 1.02, 0.97]) + 6
        blush = np.zeros((H, W), np.float32)
        for (x, y) in eyes:
            bx = x + (x - W/2)*0.35; by = y + eyeD*0.62
            blush += np.exp(-(((xx - bx)/(eyeD*0.42))**2 + ((yy - by)/(eyeD*0.26))**2))
        w = w*(1 - 0.35*blush[..., None]) + np.array([255, 120, 140])*0.35*blush[..., None]
        finish(w, "face_win.png")
    else:
        w = arr.copy()
        l = w.mean(axis=2, keepdims=True)
        w = l + (w - l)*0.8
        w = w*np.array([0.97, 0.93, 1.02])
        img = Image.fromarray(np.clip(w, 0, 255).astype(np.uint8), "RGB")
        base = np.asarray(img).astype(np.float32)
        out = base.copy()
        r = eyeD*0.24                          # ~ eye half-width in crop pixels
        for i, (x, y) in enumerate(eyes):
            s = -1 if i == 0 else 1            # -1 = left eye in the picture
            # heavy lid: the skin just above the eye slides down over the top ~60% of the eye,
            # drooping toward the outer corner (keeps her real skin texture and freckles)
            shift = int(round(r*0.62))
            edge_y = lambda px: y + r*0.05 + r*0.22*np.clip(((px - x)*s)/r, -1, 1)
            m = ((np.abs(xx - x) < r*1.25) & (yy > y - r*1.1) & (yy < edge_y(xx))).astype(np.float32)
            m = np.asarray(Image.fromarray((m*255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.6))).astype(np.float32)/255
            src_shift = np.roll(base, shift, axis=0)
            lidcol = np.roll(base, shift*2, axis=0)
            out = out*(1 - m[..., None]) + (0.5*src_shift + 0.5*lidcol)*0.97*m[..., None]
            # lash line along the lid edge
            lash = np.exp(-((yy - edge_y(xx))/(r*0.07))**2)*(np.abs(xx - x) < r*1.05)
            out = out*(1 - 0.75*lash[..., None]) + np.array([55, 35, 32])*0.75*lash[..., None]
            # tired dark bags
            bag = np.exp(-(((xx - x)/(r*1.1))**2 + ((yy - (y + r*0.75))/(r*0.33))**2))
            out = out*(1 - 0.28*bag[..., None]) + np.array([90, 55, 80])*0.28*bag[..., None]
        img = Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGB")
        ov = Image.new("RGBA", (W, H), (0, 0, 0, 0)); dr = ImageDraw.Draw(ov)
        for i, (x, y) in enumerate(eyes):
            s = -1 if i == 0 else 1
            inner_x = x - s*r*1.15; outer_x = x + s*r*1.3
            # scowl: brows pulled down hard toward the nose
            dr.line([(outer_x, y - r*1.3), (inner_x, y - r*0.62)], fill=(48, 30, 26, 215), width=max(3, int(r*0.3)))
        ov = ov.filter(ImageFilter.GaussianBlur(1.2))
        img = Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")
        # a grumpy flush at the cheeks
        w = np.asarray(img).astype(np.float32)
        fl = np.zeros((H, W), np.float32)
        for (x, y) in eyes:
            fl += np.exp(-(((xx - x)/(eyeD*0.4))**2 + ((yy - (y + eyeD*0.6))/(eyeD*0.25))**2))
        w = w*(1 - 0.22*fl[..., None]) + np.array([220, 90, 90])*0.22*fl[..., None]
        finish(w, "face_win.png")

if __name__ == "__main__":
    main()

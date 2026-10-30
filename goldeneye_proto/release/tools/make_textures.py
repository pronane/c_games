#!/usr/bin/env python3
"""Facility 64 - procedural texture generator for the Enhanced-mode models.
All textures are original procedural designs (noise, stripes, hand-placed
shapes); nothing is copied from any existing game.
Usage: python3 make_textures.py <outdir>      (needs numpy + Pillow)"""
import os, sys, math
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

OUT = sys.argv[1] if len(sys.argv) > 1 else "build_tex"
os.makedirs(OUT, exist_ok=True)
FONT_DIRS = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
             "C:/Windows/Fonts/arialbd.ttf", "/Library/Fonts/Arial Bold.ttf"]

def font(sz):
    for f in FONT_DIRS:
        if os.path.exists(f):
            return ImageFont.truetype(f, sz)
    return ImageFont.load_default()

# ---------------------------------------------------------------- noise
def vnoise(w, h, cells, seed):
    """tileable value noise, cells = grid resolution"""
    rng = np.random.default_rng(seed)
    g = rng.random((cells, cells))
    ys = np.linspace(0, cells, h, endpoint=False); xs = np.linspace(0, cells, w, endpoint=False)
    y0 = np.floor(ys).astype(int); x0 = np.floor(xs).astype(int)
    fy = ys - y0; fx = xs - x0
    fy = fy*fy*(3 - 2*fy); fx = fx*fx*(3 - 2*fx)
    y1 = (y0 + 1) % cells; x1 = (x0 + 1) % cells
    a = g[np.ix_(y0, x0)]; b = g[np.ix_(y0, x1)]; c = g[np.ix_(y1, x0)]; d = g[np.ix_(y1, x1)]
    fx = fx[None, :]; fy = fy[:, None]
    return (a*(1-fx) + b*fx)*(1-fy) + (c*(1-fx) + d*fx)*fy

def fbm(w, h, base, octaves, seed, gain=0.5):
    s = np.zeros((h, w)); amp = 1.0; tot = 0
    for o in range(octaves):
        s += amp*vnoise(w, h, base*(2**o), seed + o*101); tot += amp; amp *= gain
    return s/tot

def col(c): return np.array(c, dtype=np.float64)/255.0

def save(name, arr):
    arr = np.clip(arr, 0, 1)
    if arr.shape[2] == 3:
        Image.fromarray((arr*255 + 0.5).astype(np.uint8), "RGB").save(os.path.join(OUT, name + ".png"), optimize=True)
    else:
        Image.fromarray((arr*255 + 0.5).astype(np.uint8), "RGBA").save(os.path.join(OUT, name + ".png"), optimize=True)

def tint(gray, c):
    return gray[:, :, None]*col(c)[None, None, :]

# ---------------------------------------------------------------- fabrics
def fabric(name, c, seed, size=256, weave=0.05, wrinkle=0.10, grain=0.06):
    w = h = size
    yy, xx = np.mgrid[0:h, 0:w]
    wv = 1.0 + weave*(np.sin(xx*math.pi*0.5)*np.sin(yy*math.pi*0.5))           # twill weave
    wv += weave*0.6*np.sin((xx + yy)*math.pi/3.0)
    n = fbm(w, h, 4, 4, seed)
    wr = fbm(w, h, 3, 3, seed + 7)
    streak = vnoise(w, h, 16, seed + 3)
    v = wv*(1.0 - wrinkle + 2*wrinkle*n)*(1 - grain + 2*grain*streak)
    v *= 0.92 + 0.16*wr
    save(name, tint(v, c))

def camo(name, seed, size=256):
    w = h = size
    base = col((96, 102, 66))
    cols = [col((70, 82, 50)), col((118, 104, 72)), col((42, 44, 34))]
    img = np.ones((h, w, 3))*base
    for i, cc in enumerate(cols):
        n = fbm(w, h, 3, 4, seed + i*31)
        m = np.clip((n - (0.56 + 0.02*i))*14, 0, 1)
        img = img*(1 - m[:, :, None]) + cc*m[:, :, None]
    yy, xx = np.mgrid[0:h, 0:w]
    wv = 1.0 + 0.04*np.sin(xx*math.pi*0.5)*np.sin(yy*math.pi*0.5)
    img *= (wv*(0.9 + 0.2*fbm(w, h, 8, 2, seed + 99)))[:, :, None]
    save(name, img)

def leather(name, c, seed, size=256, shine=0.18):
    n = fbm(size, size, 6, 4, seed)
    cr = vnoise(size, size, 48, seed + 5)
    v = 0.85 + 0.25*n - 0.12*(cr > 0.8)
    v += shine*np.clip(fbm(size, size, 2, 2, seed + 9) - 0.5, 0, 1)
    save(name, tint(v, c))

def knit(name, c, seed, size=256):
    yy, xx = np.mgrid[0:size, 0:size]
    rib = 0.85 + 0.15*np.abs(np.sin(xx*math.pi/4.0))
    loops = 0.9 + 0.1*np.sin(yy*math.pi/3.0 + (xx // 4 % 2)*math.pi)
    v = rib*loops*(0.9 + 0.2*fbm(size, size, 8, 3, seed))
    save(name, tint(v, c))

def painted(name, c, seed, size=256, chips=0.0):
    n = fbm(size, size, 5, 5, seed)
    v = 0.86 + 0.22*n
    img = tint(v, c)
    if chips > 0:
        m = (fbm(size, size, 12, 3, seed + 3) > 1.0 - chips)[:, :, None]
        img = np.where(m, col((60, 58, 54))*(0.8 + 0.3*n[:, :, None]), img)
    save(name, img)

def skin(name, c, seed, size=128):
    n = fbm(size, size, 6, 4, seed)
    r = fbm(size, size, 3, 2, seed + 4)
    img = tint(0.94 + 0.10*n, c)
    img[:, :, 0] *= 1.0 + 0.05*(r - 0.5)
    save(name, img)

# ---------------------------------------------------------------- faces
# Spherical head UV: u = 0.5 + atan2(x, -y)/2pi (front = 0.5), v = 0.5 + asin(z)/pi
def face(name, skin_c, hair_c, eye_c, seed, style):
    S = 512
    V, U = np.mgrid[0:S, 0:S].astype(np.float64)
    U = (U + 0.5)/S; V = 1.0 - (V + 0.5)/S
    A = (U - 0.5)*2*math.pi           # 0 = front, +- pi = back, + = character's left
    L = (V - 0.5)*math.pi             # latitude
    sk = col(skin_c)
    n = fbm(S, S, 8, 4, seed)
    img = np.ones((S, S, 3))*sk*(0.95 + 0.08*n)[:, :, None]

    def ell(a0, l0, ra, rl):
        return ((A - a0)/ra)**2 + ((L - l0)/rl)**2

    def blend(mask, c):
        nonlocal img
        m = np.clip(mask, 0, 1)[:, :, None]
        img = img*(1 - m) + np.asarray(c)*m

    # soft shading: cheeks warmer, eye sockets darker, under jaw darker
    cheek = np.exp(-(ell(0.42, -0.18, 0.22, 0.14)))*0.5 + np.exp(-(ell(-0.42, -0.18, 0.22, 0.14)))*0.5
    img[:, :, 0] += 0.035*cheek; img[:, :, 2] -= 0.02*cheek
    for s in (-1, 1):
        sock = np.exp(-ell(s*0.38, 0.12, 0.19, 0.11))
        img *= (1 - 0.16*sock)[:, :, None]
    img *= (1 - 0.18*np.clip((-L - 0.55)*3, 0, 1))[:, :, None]
    # nose shading (geometry nose sits on top) + nostrils
    img *= (1 - 0.10*np.exp(-ell(0.0, -0.10, 0.09, 0.16)))[:, :, None]
    for s in (-1, 1):
        blend(0.75*(ell(s*0.05, -0.245, 0.022, 0.014) < 1), sk*0.45)
    # stubble / beard shadow
    if style.get("stubble"):
        jaw = np.clip(1 - ell(0.0, -0.42, 0.55, 0.22), 0, 1)
        jaw *= (fbm(S, S, 64, 2, seed + 50) > 0.45)
        blend(0.28*jaw, col(hair_c)*0.8)
    # mouth
    lips = ell(0.0, -0.40, 0.17, 0.035) < 1
    blend(0.55*lips, sk*np.array([0.78, 0.52, 0.50]))
    blend(0.85*(ell(0.0, -0.40, 0.16, 0.007) < 1), sk*0.38)
    if style.get("moustache"):
        mo = (ell(0.0, -0.335, 0.20, 0.035) < 1) & (np.abs(A) > 0.012)
        blend(0.95*mo, col(hair_c)*(0.8 + 0.3*n[:, :, None]))
    # eyes
    for s in (-1, 1):
        a0 = s*0.38
        white = ell(a0, 0.10, 0.125, 0.048) < 1
        blend(white*1.0, col((232, 228, 220)))
        iris = ell(a0, 0.10, 0.050, 0.046) < 1
        blend(iris*1.0, col(eye_c))
        blend((ell(a0, 0.10, 0.02, 0.019) < 1)*1.0, col((12, 10, 10)))
        blend((ell(a0 + 0.012, 0.115, 0.010, 0.009) < 1)*0.9, col((255, 255, 255)))
        lid = (np.abs(L - (0.10 + 0.048*np.sqrt(np.clip(1 - ((A - a0)/0.12)**2, 0, 1)))) < 0.009) & (np.abs(A - a0) < 0.125)
        blend(lid*0.9, sk*0.30)
        crease = (np.abs(L - (0.165 + 0.02*np.sqrt(np.clip(1 - ((A - a0)/0.12)**2, 0, 1)))) < 0.006) & (np.abs(A - a0) < 0.11)
        blend(crease*0.35, sk*0.6)
        # brows
        bl = 0.235 + 0.03*np.cos((A - a0)*4.5) - 0.015*s*(A - a0)
        brow = (np.abs(L - bl) < 0.025) & (np.abs(A - a0) < 0.15)
        blend(brow*(0.7 + 0.3*(fbm(S, S, 96, 1, seed + 8) > 0.4)), col(hair_c)*0.9)
    # ears area slightly darker (ears are geometry)
    for s in (-1, 1):
        img *= (1 - 0.10*np.exp(-ell(s*math.pi*0.5, 0.0, 0.25, 0.22)))[:, :, None]
    # hair
    if style.get("hair", True):
        absA = np.abs(A)
        front = 0.62 + 0.05*np.cos(A*7.0)*(absA < 0.8)
        side = 0.30
        back = -0.55
        line = np.where(absA < 0.85, front, np.where(absA < 1.9, front + (side - front)*np.clip((absA - 0.85)/0.6, 0, 1), side + (back - side)*np.clip((absA - 1.9)/0.7, 0, 1)))
        # sideburns
        sb = (np.abs(absA - 1.38) < 0.05) & (L > 0.05) & (L < 0.30)
        hairmask = np.clip((L - line)*25, 0, 1)
        hairmask = np.maximum(hairmask, sb*1.0)
        strands = vnoise(S, S, 128, seed + 21)
        strands = 0.75 + 0.35*vnoise(S, S, 160, seed + 22)*np.clip(1 - np.abs(np.sin(A*90 + L*8))*0.5, 0, 1)
        hc = col(hair_c)[None, None, :]*(strands*(0.85 + 0.3*fbm(S, S, 6, 3, seed + 23)))[:, :, None]
        m = hairmask[:, :, None]
        img = img*(1 - m) + hc*m
    if style.get("balaclava"):
        k = col((26, 26, 28))
        rib = 0.8 + 0.2*np.abs(np.sin(A*120))
        bal = k*(rib*(0.85 + 0.3*fbm(S, S, 12, 3, seed + 31)))[:, :, None]
        hole = (np.abs(L - 0.105) < 0.075) & (np.abs(A) < 0.55)
        holeedge = (np.abs(L - 0.105) < 0.09) & (np.abs(A) < 0.6) & ~hole
        m = (~hole)[:, :, None]*1.0
        img = img*(1 - m) + bal*m
        img[holeedge] *= 0.6
    save(name, img)

# ---------------------------------------------------------------- guns
def gunmetal(name, c, seed, size=512, brushed=0.10, wear=0.06):
    n = fbm(size, size, 6, 5, seed)
    br = vnoise(size, size, 256, seed + 2)
    br = np.repeat(br[:, :1], size, axis=1)*0.5 + vnoise(size, size, 96, seed + 3)*0.5
    v = 0.88 + 0.16*n + brushed*(br - 0.5)
    img = tint(v, c)
    if wear > 0:
        m = np.clip((fbm(size, size, 16, 3, seed + 5) - (1 - wear))*12, 0, 1)[:, :, None]
        img = img*(1 - m) + col((150, 150, 156))*m
    save(name, img)

def wood(name, c, seed, size=512):
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float64)
    warp = fbm(size, size, 4, 4, seed)*18
    g = np.sin((xx/size*40 + warp*0.9)*math.pi*0.5)
    g = 0.5 + 0.5*np.sign(g)*np.abs(g)**0.4
    pores = vnoise(size, size, 200, seed + 4)
    v = 0.78 + 0.18*g + 0.08*(pores - 0.5) + 0.1*fbm(size, size, 3, 2, seed + 6)
    img = tint(v, c)
    save(name, img)

def polymer(name, c, seed, size=256, stipple=True):
    n = fbm(size, size, 8, 3, seed)
    st = vnoise(size, size, 128, seed + 1)
    v = 0.9 + 0.12*n + (0.18*(st - 0.5) if stipple else 0)
    save(name, tint(v, c))

def checkered_grip(name, c, seed, size=256):
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float64)
    d = np.abs(np.sin((xx + yy)*math.pi/8))*np.abs(np.sin((xx - yy)*math.pi/8))
    v = 0.7 + 0.45*d + 0.08*fbm(size, size, 8, 2, seed)
    img = tint(v, c)
    # smooth border
    b = 14
    img[:b, :] = img[-b:, :] = col(c)*0.95
    img[:, :b] = img[:, -b:] = col(c)*0.95
    save(name, img)

def gold(name, seed, size=512):
    n = fbm(size, size, 6, 4, seed)
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float64)
    # engraved scroll pattern (original: overlapping sine rosettes)
    eng = np.abs(np.sin(xx*0.11 + np.sin(yy*0.07)*3.0)*np.sin(yy*0.11 + np.cos(xx*0.05)*3.0))
    eng = (eng < 0.08)*1.0
    v = 0.92 + 0.15*n - 0.28*eng
    img = tint(v, (226, 178, 62))
    img[:, :, 2] *= 0.9
    save(name, img)

# ---------------------------------------------------------------- props
def crate(name, seed, size=512):
    img = np.zeros((size, size, 3))
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float64)
    plank_h = size/5
    pid = (yy // plank_h).astype(int)
    rng = np.random.default_rng(seed)
    shades = rng.uniform(0.85, 1.1, 8)
    warp = fbm(size, size, 4, 4, seed)*30
    grain = 0.5 + 0.5*np.sin((yy*0.25 + warp + pid*13)*0.9)
    base = col((150, 112, 66))
    v = (0.8 + 0.2*grain + 0.1*fbm(size, size, 16, 3, seed + 1))*shades[pid % 8]
    img = tint(v, (150, 112, 66))
    gap = (yy % plank_h) < 4
    img[gap] = base*0.25
    # frame boards (border + diagonal brace)
    bw = 48
    frame = (xx < bw) | (xx > size - bw) | (yy < bw) | (yy > size - bw)
    diag = np.abs((xx - yy)) < bw*0.7
    fm = frame | diag
    fv = 0.75 + 0.2*(0.5 + 0.5*np.sin((xx + yy)*0.35 + warp)) + 0.1*fbm(size, size, 12, 3, seed + 2)
    img[fm] = (tint(fv, (128, 92, 52)))[fm]
    edge = (np.abs(xx - bw) < 2) | (np.abs(xx - (size - bw)) < 2) | (np.abs(yy - bw) < 2) | (np.abs(yy - (size - bw)) < 2)
    img[edge & ~diag] *= 0.45
    # nail heads
    for (cx, cy) in [(24, 24), (size - 24, 24), (24, size - 24), (size - 24, size - 24), (size//2, 24), (size//2, size - 24), (24, size//2), (size - 24, size//2)]:
        m = (xx - cx)**2 + (yy - cy)**2 < 25
        img[m] = col((70, 70, 72))
    pil = Image.fromarray((np.clip(img, 0, 1)*255).astype(np.uint8))
    d = ImageDraw.Draw(pil)
    f = font(40)
    d.text((size*0.5, size*0.38), "F-64 STORES", fill=(40, 30, 20), font=f, anchor="mm")
    d.text((size*0.5, size*0.62), "LOT 0417", fill=(40, 30, 20), font=font(34), anchor="mm")
    pil = pil.filter(ImageFilter.GaussianBlur(0.6))
    arr = np.asarray(pil).astype(np.float64)/255
    save(name, arr)

def barrel(name, c, seed, size=512):
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float64)
    n = fbm(size, size, 6, 5, seed)
    v = 0.85 + 0.2*n
    img = tint(v, c)
    # hazard band
    band = (yy > size*0.40) & (yy < size*0.60)
    stripes = ((xx + yy) // 32 % 2 == 0)
    img[band & stripes] = col((220, 180, 40))*(0.9 + 0.1*n[band & stripes][:, None])
    img[band & ~stripes] = col((30, 30, 30))
    # rust streaks
    rs = np.clip((fbm(size, size, 10, 3, seed + 3) - 0.62)*6, 0, 1)*np.clip(vnoise(size, size, 32, seed + 4)*1.5 - 0.3, 0, 1)
    img = img*(1 - rs[:, :, None]) + col((110, 60, 30))*rs[:, :, None]
    pil = Image.fromarray((np.clip(img, 0, 1)*255).astype(np.uint8))
    d = ImageDraw.Draw(pil)
    for k in range(2):
        d.text((size*(0.25 + 0.5*k), size*0.26), "COOLANT  C-9", fill=(235, 235, 225), font=font(30), anchor="mm")
    save(name, np.asarray(pil).astype(np.float64)/255)

def barrel_top(name, c, seed, size=256):
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float64)
    r = np.hypot(xx - size/2, yy - size/2)/(size/2)
    n = fbm(size, size, 6, 4, seed)
    v = 0.85 + 0.2*n - 0.15*(np.abs(r - 0.8) < 0.03) - 0.1*(np.abs(r - 0.55) < 0.02)
    img = tint(v, c)
    m = ((xx - size*0.7)**2 + (yy - size*0.5)**2) < (size*0.06)**2
    img[m] = col((90, 92, 96))
    save(name, img)

def desk_top(name, seed, size=512):
    n = fbm(size, size, 3, 4, seed)
    sp = vnoise(size, size, 256, seed + 1)
    v = 0.9 + 0.1*n + 0.05*(sp - 0.5)
    save(name, tint(v, (150, 148, 138)))

def screen(name, seed, size=256):
    rng = np.random.default_rng(seed)
    img = np.zeros((size, size, 3)) + col((6, 22, 10))
    pil = Image.fromarray((img*255).astype(np.uint8))
    d = ImageDraw.Draw(pil)
    f = font(13)
    lines = ["F64 SECURE TERMINAL", "LINK ....... OK", "SECTOR 3  STATUS", "> grid 07  NOMINAL", "> grid 08  NOMINAL", "> door A17 LOCKED",
             "> cam  B04 ONLINE", "", "AUTH: ********", "> _"]
    for i, t in enumerate(lines):
        d.text((14, 14 + i*21), t, fill=(90, 255, 140), font=f)
    pil = pil.filter(ImageFilter.GaussianBlur(0.7))
    arr = np.asarray(pil).astype(np.float64)/255
    yy = np.arange(size)[:, None]
    arr *= (0.8 + 0.2*(yy % 3 != 0))[:, :, None]
    yy2, xx2 = np.mgrid[0:size, 0:size]
    vig = 1 - 0.5*(((xx2 - size/2)/(size/2))**2 + ((yy2 - size/2)/(size/2))**2)**2
    arr *= np.clip(vig, 0, 1)[:, :, None]
    save(name, arr)

def rack_front(name, seed, size=512):
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float64)
    n = fbm(size, size, 6, 4, seed)
    img = tint(0.8 + 0.2*n, (64, 68, 74))
    rng = np.random.default_rng(seed)
    unit_h = size/8
    for u in range(8):
        y0 = int(u*unit_h) + 6; y1 = int((u + 1)*unit_h) - 6
        img[y0:y1, 20:size - 20] = col((42, 44, 50))*(0.9 + 0.1*n[y0:y1, 20:size - 20, None])
        # vents
        for vx in range(60, size - 140, 14):
            img[y0 + 10:y1 - 10, vx:vx + 6] = col((18, 18, 20))
        # LEDs
        for k in range(4):
            cx = size - 110 + k*22; cy = (y0 + y1)//2
            c = [(80, 255, 90), (255, 190, 40), (80, 255, 90), (255, 60, 50)][(u + k + rng.integers(0, 3)) % 4]
            m = (xx - cx)**2 + (yy - cy)**2 < 36
            img[m] = col(c)
        img[y0:y0 + 2, 20:size - 20] = col((110, 114, 120))
    save(name, img)

def keyboard(name, seed, size=256):
    img = np.zeros((size, size, 3)) + col((180, 172, 150))
    for r in range(5):
        for k in range(14):
            x0 = 8 + k*17; y0 = 30 + r*40
            img[y0:y0 + 30, x0:x0 + 14] = col((206, 200, 180))
            img[y0 + 26:y0 + 30, x0:x0 + 14] = col((140, 134, 118))
    save(name, img)

def soft_noise(name, c, seed, size=256, amt=0.12):
    n = fbm(size, size, 6, 4, seed)
    save(name, tint(1 - amt + 2*amt*n, c))

if __name__ == "__main__":
    # characters
    camo("ch_camo", 11)
    fabric("ch_olive", (84, 92, 60), 12)
    fabric("ch_vest_olive", (70, 76, 52), 13, weave=0.08)
    fabric("ch_vest_black", (40, 42, 44), 14, weave=0.08)
    fabric("ch_bluegrey", (92, 108, 132), 15)
    fabric("ch_navy", (46, 52, 70), 16)
    fabric("ch_black", (44, 46, 50), 17)
    fabric("ch_charcoal", (50, 52, 60), 18, weave=0.03, wrinkle=0.06)
    fabric("ch_tan", (150, 124, 90), 19, weave=0.03, wrinkle=0.06)
    fabric("ch_white", (226, 228, 230), 20, weave=0.02, wrinkle=0.06)
    fabric("ch_tie_dark", (40, 34, 52), 21, weave=0.06)
    fabric("ch_tie_red", (120, 30, 36), 22, weave=0.06)
    leather("ch_leather", (36, 32, 30), 23)
    leather("ch_leather_brown", (80, 56, 36), 24)
    painted("ch_helmet", (80, 88, 58), 25, chips=0.05)
    knit("ch_knit", (34, 34, 36), 26)
    fabric("ch_cap", (44, 50, 68), 27)
    skin("ch_skin_a", (222, 182, 150), 28)
    skin("ch_skin_b", (200, 150, 118), 29)
    skin("ch_skin_c", (214, 170, 140), 30)
    hair = lambda nm, c, sd: fabric(nm, c, sd, weave=0.0, wrinkle=0.25, grain=0.35)
    hair("ch_hair_dark", (52, 36, 24), 61)
    hair("ch_hair_fair", (176, 146, 84), 62)
    face("face_soldier", (222, 182, 150), (70, 50, 30), (70, 90, 60), 31, {"stubble": True})
    face("face_guard", (200, 150, 118), (40, 30, 25), (60, 40, 25), 32, {"moustache": True})
    face("face_commando", (225, 185, 160), (30, 30, 30), (60, 80, 110), 33, {"balaclava": True, "hair": False})
    face("face_agent1", (225, 185, 155), (55, 38, 24), (70, 90, 110), 34, {})
    face("face_agent2", (214, 170, 140), (190, 160, 92), (60, 100, 80), 35, {"stubble": False})
    # guns
    gunmetal("gun_blued", (52, 56, 66), 41)
    gunmetal("gun_park", (70, 72, 70), 42, brushed=0.04, wear=0.04)
    gunmetal("gun_steel", (150, 154, 160), 43, brushed=0.2, wear=0.0)
    wood("gun_wood", (126, 70, 38), 44)
    polymer("gun_polymer", (40, 40, 42), 45)
    checkered_grip("gun_grip", (54, 40, 30), 46)
    gold("gun_gold", 47)
    # props
    crate("pr_crate", 51)
    barrel("pr_barrel", (52, 74, 110), 52)
    barrel_top("pr_barrel_top", (52, 74, 110), 53)
    desk_top("pr_desk_top", 54)
    soft_noise("pr_metal", (120, 124, 128), 55)
    soft_noise("pr_beige", (190, 182, 160), 56, amt=0.05)
    screen("pr_screen", 57)
    rack_front("pr_rack", 58)
    keyboard("pr_keyboard", 59)
    soft_noise("pr_darkmetal", (60, 64, 70), 60)
    print("textures written to", OUT)

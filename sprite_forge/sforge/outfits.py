"""Dress-as outfit templates for photo characters (v9.4): "--outfit police" / postman / astronaut / ...

An outfit = a recolour of the photo's own garment regions (sforge.recolor: shading and folds kept) + optionally a plain
top (printed logos / text flattened away, folds kept) + PROPS drawn from the pose landmarks: hats and helmets,
badges, belts, satchels, hi-vis bands, gloves, chest units, a stethoscope ...  It edits the cut-out BEFORE any rig is
built, so every engine, view, move and console export wears it (turned / 3D views get the backs from the new
colours).  Everything drawn is generic: no real force, service or brand insignia, no lettering.

Templates: built in (OUTFITS below) or JSON files in library/outfits_photo/<name>.json with the same keys:
    {"label": "...", "colours": {"top": "#..", "bottom": "#..", ...}, "plain": true,
     "props": [{"kind": "peaked_cap", "colour": "#..", ...}, ...]}
Prop kinds: peaked_cap, hard_hat, fire_helmet, helmet_bubble, chef_hat, headband, badge, belt, satchel, vest,
reflective_bands, chest_unit, patch, stethoscope, buttons, gloves, epaulettes, radio, tie, cape_edges."""
from __future__ import annotations
import glob, json, math, os
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from scipy import ndimage as ndi

OUTFITS = {
    "police": {"label": "Police officer", "plain": True,
               "colours": {"top": "#1d2742", "trim": "#1d2742", "bottom": "#151b2f", "shoes": "#0d0d0f", "socks": "#151b2f"},
               "props": [{"kind": "peaked_cap", "colour": "#151b30", "band": "chequer", "band_colour": "#f2f2f2", "badge": "#cfd3d8"},
                         {"kind": "epaulettes", "colour": "#10162a"},
                         {"kind": "badge", "pos": "chest_l", "colour": "#d0d4da", "shape": "star"},
                         {"kind": "radio", "colour": "#1a1a1c"},
                         {"kind": "belt", "colour": "#121214", "buckle": "#c8ccd2"}]},
    "postman": {"label": "Postman", "plain": True,
                "colours": {"top": "#8eb4dc", "trim": "#8eb4dc", "bottom": "#1e2c4c", "shoes": "#151515", "socks": "#1e2c4c"},
                "props": [{"kind": "peaked_cap", "colour": "#1e2c4c", "band": "plain", "band_colour": "#b8202a", "badge": "#e8c64a"},
                          {"kind": "satchel", "colour": "#7a2a1f", "strap": "#5a1f17"},
                          {"kind": "badge", "pos": "chest_l", "colour": "#e8c64a", "shape": "shield"}]},
    "astronaut": {"label": "Astronaut", "plain": True,
                  "colours": {"top": "#eceff3", "trim": "#eceff3", "bottom": "#e4e8ee", "shoes": "#dfe3e9", "socks": "#e4e8ee"},
                  "props": [{"kind": "helmet_bubble", "rim": "#d9dde3", "glass": "#bfe3ff"},
                            {"kind": "chest_unit", "colour": "#cfd5dd", "buttons": ["#e03a3a", "#3a7be0", "#f2c230"]},
                            {"kind": "patch", "pos": "arm_l", "colour": "#2d5bd1", "ring": "#f2f2f2"},
                            {"kind": "gloves", "colour": "#f4f5f7"},
                            {"kind": "reflective_bands", "colour": "#2d5bd1", "where": ["knees"], "silver": False}]},
    "firefighter": {"label": "Firefighter", "plain": True,
                    "colours": {"top": "#2a2925", "trim": "#2a2925", "bottom": "#2a2925", "shoes": "#111111", "socks": "#2a2925"},
                    "props": [{"kind": "fire_helmet", "colour": "#c7241d"},
                              {"kind": "reflective_bands", "colour": "#f2e21a", "where": ["chest", "waist", "forearms", "shins"], "silver": True},
                              {"kind": "gloves", "colour": "#2b2b2b"}]},
    "builder": {"label": "Builder", "plain": False,
                "colours": {},
                "props": [{"kind": "hard_hat", "colour": "#f2c818"},
                          {"kind": "vest", "colour": "#d9f21a", "bands": "#d6d9de"},
                          {"kind": "gloves", "colour": "#c9a24a"}]},
    "chef": {"label": "Chef", "plain": True,
             "colours": {"top": "#f6f6f4", "trim": "#f6f6f4", "bottom": "#2a2a2a", "shoes": "#151515", "socks": "#2a2a2a"},
             "props": [{"kind": "chef_hat", "colour": "#fbfbfa"}, {"kind": "buttons", "colour": "#2a2a2a", "rows": 4},
                       {"kind": "tie", "colour": "#c8202a", "style": "neckerchief"}]},
    "doctor": {"label": "Doctor (scrubs)", "plain": True,
               "colours": {"top": "#2f8f88", "trim": "#2f8f88", "bottom": "#2f8f88", "shoes": "#f0f0f0", "socks": "#2f8f88"},
               "props": [{"kind": "stethoscope", "colour": "#1c1c1c", "metal": "#c9ced6"},
                         {"kind": "badge", "pos": "chest_l", "colour": "#f4f4f4", "shape": "card"}]},
    "ninja": {"label": "Ninja", "plain": True,
              "colours": {"top": "#141418", "trim": "#141418", "bottom": "#141418", "shoes": "#141418", "socks": "#141418"},
              "props": [{"kind": "headband", "colour": "#a01818"}, {"kind": "belt", "colour": "#a01818", "buckle": None},
                        {"kind": "gloves", "colour": "#141418"}]},
}


def _here():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def all_outfits():
    out = dict(OUTFITS)
    for p in sorted(glob.glob(os.path.join(_here(), "library", "outfits_photo", "*.json"))):
        try:
            out[os.path.splitext(os.path.basename(p))[0]] = json.load(open(p))
        except Exception:
            pass
    return out


def rgb(c, a=255):
    c = c.lstrip("#")
    return (int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16), a)


def shade(c, k):
    r, g, b = c[:3]
    return (int(max(0, min(255, r * k))), int(max(0, min(255, g * k))), int(max(0, min(255, b * k))), c[3] if len(c) > 3 else 255)


# ---------------------------------------------------------------- geometry from the landmarks + silhouette
class Geo:
    def __init__(self, cut, lms):
        a = np.asarray(cut)[..., 3] > 100
        self.alpha = a
        P = lambda i: np.array(lms[i][:2], float)
        self.P = P
        self.eyes = (P(2) + P(5)) / 2; self.mouth = (P(9) + P(10)) / 2; self.nose = P(0)
        self.chin = self.mouth + 0.85 * (self.mouth - self.eyes)
        self.shL, self.shR = P(11), P(12)                  # MediaPipe 11 = person's left (image right)
        self.hipL, self.hipR = P(23), P(24)
        self.sw = float(np.linalg.norm(self.shL - self.shR))
        cols = np.nonzero(a[int(self.eyes[1])])[0]
        self.head_w = float(cols.max() - cols.min()) if len(cols) else 0.4 * self.sw
        self.head_cx = float((cols.max() + cols.min()) / 2) if len(cols) else float(self.nose[0])
        hc = a[:, int(self.head_cx)]
        rows = np.nonzero(hc[: int(self.eyes[1])])[0]
        self.head_top = float(rows.min()) if len(rows) else float(self.eyes[1] - 0.6 * self.head_w)
        self.mid_sh = (self.shL + self.shR) / 2; self.mid_hip = (self.hipL + self.hipR) / 2

    def row_span(self, y, x0=None, x1=None):
        r = np.nonzero(self.alpha[int(np.clip(y, 0, self.alpha.shape[0] - 1))])[0]
        if x0 is not None:
            r = r[(r >= x0) & (r <= x1)]
        return (float(r.min()), float(r.max())) if len(r) else None

    def torso_span(self, y):
        lo = min(self.shL[0], self.shR[0]) - 0.15 * self.sw; hi = max(self.shL[0], self.shR[0]) + 0.15 * self.sw
        return self.row_span(y, lo, hi)


class Canvas:
    """props drawn at 4x on a transparent layer, then composited (anti-aliased) onto the cut-out"""
    K = 4

    def __init__(self, size):
        self.W, self.H = size
        self.im = Image.new("RGBA", (self.W * self.K, self.H * self.K), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.im)

    def s(self, pts):
        return [(x * self.K, y * self.K) for x, y in pts]

    def poly(self, pts, fill, outline=None, width=1):
        self.d.polygon(self.s(pts), fill=fill, outline=outline, width=width * self.K if outline else 0)

    def ellipse(self, box, fill, outline=None, width=1):
        x0, y0, x1, y1 = box
        self.d.ellipse((x0 * self.K, y0 * self.K, x1 * self.K, y1 * self.K), fill=fill, outline=outline,
                       width=width * self.K if outline else 0)

    def rect(self, box, fill, outline=None, width=1, r=0):
        x0, y0, x1, y1 = box
        self.d.rounded_rectangle((x0 * self.K, y0 * self.K, x1 * self.K, y1 * self.K), radius=r * self.K, fill=fill,
                                 outline=outline, width=width * self.K if outline else 0)

    def line(self, pts, fill, width):
        self.d.line(self.s(pts), fill=fill, width=int(width * self.K), joint="curve")

    def result(self):
        return self.im.resize((self.W, self.H), Image.LANCZOS)


def _star(cx, cy, r, n=5):
    pts = []
    for i in range(2 * n):
        rr = r if i % 2 == 0 else r * 0.45
        a = -math.pi / 2 + i * math.pi / n
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    return pts


# ---------------------------------------------------------------- props
def draw_props(cut, lms, props, labels=None, log=print):
    from . import recolor as RC
    g = Geo(cut, lms)
    W, H = cut.size
    under = Canvas((W, H))      # behind the person (satchel bag behind the hip, helmet back)
    over = Canvas((W, H))       # in front
    hw, sw = g.head_w, g.sw
    eyes_y, top = g.eyes[1], g.head_top
    cx = g.head_cx
    base = cut.copy()
    a_np = np.asarray(cut).copy()
    for pr in props:
        k = pr["kind"]
        col = rgb(pr.get("colour", "#888888"))
        if k == "peaked_cap":
            band_bot = eyes_y - 0.30 * (eyes_y - top)
            band_h = 0.15 * hw
            crown_top = top - 0.18 * hw
            w0 = 1.12 * hw
            crown = [(cx - 0.50 * w0, band_bot - band_h), (cx - 0.62 * w0, crown_top + 0.12 * hw), (cx - 0.35 * w0, crown_top),
                     (cx + 0.35 * w0, crown_top), (cx + 0.62 * w0, crown_top + 0.12 * hw), (cx + 0.50 * w0, band_bot - band_h)]
            over.poly(crown, shade(col, 1.0))
            over.poly([(cx - 0.45 * w0, crown_top + 0.04 * hw), (cx + 0.1 * w0, crown_top + 0.02 * hw),
                       (cx - 0.1 * w0, crown_top + 0.14 * hw)], shade(col, 1.25))          # top highlight
            bc = rgb(pr.get("band_colour", "#ffffff"))
            x0b, x1b = cx - 0.5 * w0, cx + 0.5 * w0
            if pr.get("band") == "chequer":
                n = 8; cw = (x1b - x0b) / n
                for i in range(n):
                    for j in range(2):
                        c_ = bc if (i + j) % 2 == 0 else shade(col, 0.8)
                        over.rect((x0b + i * cw, band_bot - band_h + j * band_h / 2, x0b + (i + 1) * cw, band_bot - band_h + (j + 1) * band_h / 2), c_)
            else:
                over.rect((x0b, band_bot - band_h, x1b, band_bot), bc)
            # peak (visor): dark curved shape just under the band
            over.d.chord((over.K * (cx - 0.48 * w0), over.K * (band_bot - 0.10 * hw), over.K * (cx + 0.48 * w0),
                          over.K * (band_bot + 0.16 * hw)), 0, 180, fill=(18, 18, 20, 255))
            if pr.get("badge"):
                over.ellipse((cx - 0.07 * hw, band_bot - band_h - 0.17 * hw, cx + 0.07 * hw, band_bot - band_h - 0.03 * hw), rgb(pr["badge"]))
        elif k in ("hard_hat", "fire_helmet"):
            brim_y = eyes_y - 0.38 * (eyes_y - top)
            dome_top = top - 0.12 * hw
            w0 = (1.12 if k == "hard_hat" else 1.18) * hw
            over.d.pieslice((over.K * (cx - 0.5 * w0), over.K * dome_top, over.K * (cx + 0.5 * w0),
                             over.K * (2 * brim_y - dome_top)), 180, 360, fill=col)
            over.d.pieslice((over.K * (cx - 0.38 * w0), over.K * (dome_top + 0.05 * hw), over.K * (cx - 0.05 * w0),
                             over.K * (brim_y)), 200, 260, fill=shade(col, 1.3))
            over.rect((cx - 0.06 * hw, dome_top - 0.01 * hw, cx + 0.06 * hw, brim_y), shade(col, 0.85))   # ridge
            bw = (0.66 if k == "hard_hat" else 0.78) * hw
            over.ellipse((cx - bw, brim_y - 0.07 * hw, cx + bw, brim_y + (0.08 if k == "hard_hat" else 0.13) * hw), shade(col, 0.9))
            if k == "fire_helmet":
                over.d.polygon(over.s(_star(cx, (dome_top + brim_y) / 2 + 0.04 * hw, 0.13 * hw, 6)), fill=(230, 200, 60, 255))
        elif k == "chef_hat":
            band_bot = eyes_y - 0.35 * (eyes_y - top)
            w0 = 1.0 * hw
            over.rect((cx - 0.48 * w0, band_bot - 0.25 * hw, cx + 0.48 * w0, band_bot), col)
            for dx, dy, r in ((-0.32, -0.55, 0.32), (0.0, -0.75, 0.38), (0.32, -0.55, 0.32), (-0.15, -0.38, 0.3), (0.17, -0.38, 0.3)):
                over.ellipse((cx + (dx - r) * w0, band_bot + (dy - r) * hw, cx + (dx + r) * w0, band_bot + (dy + r) * hw), col)
            over.line([(cx - 0.42 * w0, band_bot - 0.26 * hw), (cx + 0.42 * w0, band_bot - 0.26 * hw)], shade(col, 0.88), 0.02 * hw)
        elif k == "headband":
            y = eyes_y - 0.42 * (eyes_y - top)
            sp = g.row_span(y) or (cx - 0.5 * hw, cx + 0.5 * hw)
            over.rect((sp[0] - 1, y - 0.07 * hw, sp[1] + 1, y + 0.07 * hw), col)
            over.poly([(sp[1], y), (sp[1] + 0.35 * hw, y + 0.25 * hw), (sp[1] + 0.25 * hw, y + 0.32 * hw)], shade(col, 0.9))
            over.poly([(sp[1], y + 0.02 * hw), (sp[1] + 0.42 * hw, y + 0.05 * hw), (sp[1] + 0.38 * hw, y + 0.14 * hw)], shade(col, 0.8))
        elif k == "helmet_bubble":
            hc = np.array([cx, (top + g.chin[1]) / 2 - 0.02 * hw])
            r = 0.5 * max(g.chin[1] - top, hw) * 1.32
            glass = rgb(pr.get("glass", "#bfe3ff"))
            # glass outside the head: translucent, so it joins the silhouette
            under.ellipse((hc[0] - r, hc[1] - r, hc[0] + r, hc[1] + r), (glass[0], glass[1], glass[2], 110))
            over.ellipse((hc[0] - r, hc[1] - r, hc[0] + r, hc[1] + r), (glass[0], glass[1], glass[2], 38))
            over.d.arc((over.K * (hc[0] - r * 0.78), over.K * (hc[1] - r * 0.85), over.K * (hc[0] + r * 0.5), over.K * (hc[1] + r * 0.4)),
                       200, 255, fill=(255, 255, 255, 200), width=int(0.06 * r * over.K))
            over.ellipse((hc[0] - r, hc[1] - r, hc[0] + r, hc[1] + r), None, outline=rgb(pr.get("rim", "#d9dde3")), width=max(2, int(0.07 * r)))
            ny = g.chin[1] + 0.05 * hw
            over.rect((cx - 0.72 * hw, ny - 0.02 * hw, cx + 0.72 * hw, ny + 0.2 * hw), rgb(pr.get("rim", "#d9dde3")), r=0.08 * hw)
            over.rect((cx - 0.72 * hw, ny + 0.09 * hw, cx + 0.72 * hw, ny + 0.13 * hw), shade(rgb(pr.get("rim", "#d9dde3")), 0.75))
        elif k == "badge":
            bx = g.mid_sh[0] + 0.25 * (g.shL[0] - g.shR[0]) * (1 if pr.get("pos", "chest_l") == "chest_l" else -1)
            by = g.mid_sh[1] + 0.22 * (g.mid_hip[1] - g.mid_sh[1])
            r = 0.07 * sw
            sh_ = pr.get("shape", "star")
            if sh_ == "star":
                over.d.polygon(over.s(_star(bx, by, r, 6)), fill=col, outline=shade(col, 0.6))
            elif sh_ == "shield":
                over.poly([(bx - r, by - r), (bx + r, by - r), (bx + r, by + 0.2 * r), (bx, by + 1.2 * r), (bx - r, by + 0.2 * r)], col, shade(col, 0.6))
            else:
                over.rect((bx - 1.1 * r, by - 0.7 * r, bx + 1.1 * r, by + 0.7 * r), col, shade(col, 0.5), r=0.15 * r)
                over.rect((bx - 0.8 * r, by - 0.45 * r, bx - 0.15 * r, by + 0.35 * r), (150, 170, 190, 255))
        elif k == "radio":
            bx = g.mid_sh[0] - 0.24 * (g.shL[0] - g.shR[0]); by = g.mid_sh[1] + 0.18 * (g.mid_hip[1] - g.mid_sh[1])
            over.rect((bx - 0.05 * sw, by - 0.08 * sw, bx + 0.05 * sw, by + 0.08 * sw), col, r=0.015 * sw)
            over.line([(bx + 0.03 * sw, by - 0.08 * sw), (bx + 0.03 * sw, by - 0.15 * sw)], col, 0.015 * sw)
        elif k == "epaulettes":
            for s_ in (g.shL, g.shR):
                x = s_[0] + 0.45 * (g.mid_sh[0] - s_[0])
                col_ = np.nonzero(g.alpha[:, int(x)])[0]
                ytop = float(col_[col_ > g.chin[1]].min()) if len(col_[col_ > g.chin[1]]) else s_[1]
                over.rect((x - 0.09 * sw, ytop + 0.01 * sw, x + 0.09 * sw, ytop + 0.05 * sw), col, r=0.01 * sw)
        elif k == "belt":
            y = g.mid_hip[1] - 0.05 * sw
            sp = g.torso_span(y)
            if sp:
                over.rect((sp[0], y - 0.045 * sw, sp[1], y + 0.045 * sw), col)
                if pr.get("buckle"):
                    over.rect((g.mid_hip[0] - 0.06 * sw, y - 0.055 * sw, g.mid_hip[0] + 0.06 * sw, y + 0.055 * sw), None,
                              outline=rgb(pr["buckle"]), width=max(1, int(0.015 * sw)))
        elif k == "satchel":
            strap = rgb(pr.get("strap", "#5a1f17"))
            p0 = g.shR + 0.12 * (g.mid_sh - g.shR); p1 = g.hipL + np.array([0.0, -0.1 * sw])
            over.line([tuple(p0), tuple(p1)], strap, 0.07 * sw)
            # the bag sits ON the hip, inside the silhouette (so the rig keeps it with the body, not the hand)
            bx = g.hipL[0] - 0.2 * sw + 0.5 * (g.mid_hip[0] - g.hipL[0]) * 0
            by = g.hipL[1] - 0.12 * sw
            x0_, x1_ = g.hipL[0] - 0.30 * sw, g.hipL[0] + 0.04 * sw
            if g.hipL[0] < g.mid_hip[0]:
                x0_, x1_ = g.hipL[0] - 0.04 * sw, g.hipL[0] + 0.30 * sw
            over.rect((x0_, by, x1_, by + 0.3 * sw), col, r=0.04 * sw)
            over.rect((x0_, by, x1_, by + 0.12 * sw), shade(col, 0.82), r=0.04 * sw)
            mx = (x0_ + x1_) / 2
            over.rect((mx - 0.03 * sw, by + 0.08 * sw, mx + 0.03 * sw, by + 0.15 * sw), (200, 180, 90, 255))
        elif k == "chest_unit":
            bx, by = g.mid_sh[0], g.mid_sh[1] + 0.3 * (g.mid_hip[1] - g.mid_sh[1])
            over.rect((bx - 0.2 * sw, by - 0.12 * sw, bx + 0.2 * sw, by + 0.12 * sw), col, shade(col, 0.6), r=0.03 * sw)
            for i, bc in enumerate(pr.get("buttons", [])):
                x = bx - 0.12 * sw + i * 0.12 * sw
                over.ellipse((x - 0.035 * sw, by - 0.035 * sw, x + 0.035 * sw, by + 0.035 * sw), rgb(bc))
        elif k == "patch":
            s_ = g.shL if pr.get("pos", "arm_l") == "arm_l" else g.shR
            e_ = g.P(13) if s_ is g.shL else g.P(14)
            c_ = s_ + 0.35 * (e_ - s_)
            r = 0.08 * sw
            over.ellipse((c_[0] - r, c_[1] - r, c_[0] + r, c_[1] + r), col, rgb(pr.get("ring", "#ffffff")), max(1, int(0.18 * r)))
            over.d.polygon(over.s(_star(c_[0], c_[1], 0.5 * r, 5)), fill=(240, 240, 240, 255))
        elif k == "stethoscope":
            n0 = g.chin + np.array([0, 0.25 * hw])
            pts = [(n0[0] - 0.35 * hw, n0[1] - 0.05 * hw), (n0[0] - 0.42 * hw, n0[1] + 0.35 * hw), (n0[0] - 0.25 * hw, n0[1] + 0.95 * hw)]
            pts2 = [(n0[0] + 0.35 * hw, n0[1] - 0.05 * hw), (n0[0] + 0.40 * hw, n0[1] + 0.5 * hw), (n0[0] + 0.30 * hw, n0[1] + 1.05 * hw)]
            over.line(pts, col, 0.05 * hw); over.line(pts2, col, 0.05 * hw)
            e = pts2[-1]
            over.ellipse((e[0] - 0.1 * hw, e[1] - 0.1 * hw, e[0] + 0.1 * hw, e[1] + 0.1 * hw), rgb(pr.get("metal", "#c9ced6")))
        elif k == "buttons":
            for i in range(int(pr.get("rows", 4))):
                y = g.mid_sh[1] + (0.15 + 0.17 * i) * (g.mid_hip[1] - g.mid_sh[1])
                for dx in (-0.11, 0.11):
                    x = g.mid_sh[0] + dx * sw
                    over.ellipse((x - 0.025 * sw, y - 0.025 * sw, x + 0.025 * sw, y + 0.025 * sw), col)
        elif k == "tie":
            n0 = g.chin + np.array([0, 0.15 * hw])
            over.poly([(n0[0] - 0.32 * hw, n0[1]), (n0[0] + 0.32 * hw, n0[1]), (n0[0], n0[1] + 0.45 * hw)], col)
        elif k == "vest":
            pass                                        # painted below (it is a garment, not a drawn prop)
        elif k == "reflective_bands":
            pass
        elif k == "gloves":
            pass
    # ---- garment-like props: painted into the photo's pixels (shading kept)
    from . import recolor as RC
    lab = RC._lab(a_np[..., :3])
    H_, W_ = a_np.shape[:2]
    yy, xx = np.mgrid[0:H_, 0:W_]
    A = a_np[..., 3] > 40
    def capsule(p, q, r):
        p = np.asarray(p, float); q = np.asarray(q, float); d = q - p; L2 = max(1e-6, d @ d)
        t = np.clip(((xx - p[0]) * d[0] + (yy - p[1]) * d[1]) / L2, 0, 1)
        return (xx - p[0] - t * d[0]) ** 2 + (yy - p[1] - t * d[1]) ** 2 <= r * r
    arms = capsule(g.shL, g.P(13), 0.17 * sw) | capsule(g.P(13), g.P(15), 0.15 * sw) | \
        capsule(g.shR, g.P(14), 0.17 * sw) | capsule(g.P(14), g.P(16), 0.15 * sw)
    torso_rows = (yy > g.mid_sh[1] - 0.05 * sw) & (yy < g.mid_hip[1])
    torso = A & torso_rows & ~arms
    for pr in props:
        k = pr["kind"]
        if k == "gloves":
            hand = A & np.zeros_like(A)
            for w_, t_ in ((15, 19), (16, 20)):
                hand |= capsule(g.P(w_), g.P(t_), 0.11 * sw) | ((xx - g.P(t_)[0]) ** 2 + (yy - g.P(t_)[1]) ** 2 <= (0.13 * sw) ** 2)
            sk = A & hand
            if labels is not None:
                sk &= (labels == RC.REGIONS.index("skin"))
            if sk.any():
                w = ndi.gaussian_filter(sk.astype(np.float32), 0.8)
                lab = RC.recolour_pixels(lab, w, rgb(pr["colour"])[:3])
        elif k == "vest":
            w = ndi.gaussian_filter(torso.astype(np.float32), 1.0) * A
            lab = RC.recolour_pixels(lab, w, rgb(pr["colour"])[:3])
            band = rgb(pr.get("bands", "#d6d9de"))[:3]
            for f in (0.45, 0.72):
                y = g.mid_sh[1] + f * (g.mid_hip[1] - g.mid_sh[1])
                m = torso & (np.abs(yy - y) < 0.035 * sw)
                lab = RC.recolour_pixels(lab, m.astype(np.float32), band)
        elif k == "reflective_bands":
            yel = rgb(pr["colour"])[:3]; sil = (214, 217, 222)
            wh = pr.get("where", [])
            def strip(c, u, half, rad):
                """pixels within `half` of the line through c across direction u, and within rad of c"""
                u = np.asarray(u, float); u = u / max(1e-6, np.linalg.norm(u))
                along = (xx - c[0]) * u[0] + (yy - c[1]) * u[1]
                return A & (np.abs(along) < half) & ((xx - c[0]) ** 2 + (yy - c[1]) ** 2 < rad * rad)
            bands = []                      # (centre, axis direction, radius)
            for f, on in ((0.4, "chest"), (0.92, "waist")):
                if on in wh:
                    c_ = g.mid_sh + f * (g.mid_hip - g.mid_sh)
                    bands.append((c_, g.mid_hip - g.mid_sh, 0.75 * sw))
            for key_, f, pairs in (("forearms", 0.5, ((13, 15), (14, 16))), ("wrists", 0.8, ((13, 15), (14, 16))),
                                   ("shins", 0.45, ((25, 27), (26, 28))), ("knees", 0.0, ((25, 27), (26, 28)))):
                if key_ in wh:
                    for a_, b_ in pairs:
                        c_ = g.P(a_) + f * (g.P(b_) - g.P(a_))
                        bands.append((c_, g.P(b_) - g.P(a_), 0.16 * sw))
            for c_, u_, rad in bands:
                m = strip(c_, u_, 0.04 * sw, rad)
                if "torso" not in pr.get("over", "") and rad < 0.5 * sw:
                    m &= ~torso                     # limb bands stay on the limb
                lab = RC.recolour_pixels(lab, ndi.gaussian_filter(m.astype(np.float32), 0.6), yel)
                if pr.get("silver"):
                    ms = strip(c_, u_, 0.013 * sw, rad) & m
                    lab = RC.recolour_pixels(lab, ms.astype(np.float32), sil)
    a_np[..., :3] = np.where(A[..., None], RC._rgb(lab), a_np[..., :3])
    painted = Image.fromarray(a_np, "RGBA")
    out = under.result()
    out.alpha_composite(painted)
    out.alpha_composite(over.result())
    return out


def plain_garments(cut, labels, regions=("top", "trim", "accessory"), sigma_frac=0.02, keep=0.25, lms=None):
    """remove printed logos / text from garments: lightness replaced by a smooth version (folds and shading stay,
    letters and graphics go), colour unified; the region's own median sets the base"""
    from . import recolor as RC
    a = np.asarray(cut.convert("RGBA")).copy()
    lab = RC._lab(a[..., :3])
    m = np.zeros(labels.shape, bool)
    for r in regions:
        m |= labels == RC.REGIONS.index(r)
    if lms is not None:          # logos / graphics inside the torso are garment, whatever colour cluster they fell in
        g = Geo(cut, lms)
        yy, xx = np.mgrid[0:m.shape[0], 0:m.shape[1]]
        box = (yy > g.mid_sh[1]) & (yy < g.mid_hip[1] - 0.05 * g.sw) & \
              (np.abs(xx - g.mid_sh[0]) < 0.42 * g.sw) & (a[..., 3] > 100)
        near_hand = np.zeros_like(box)
        for w_, t_ in ((15, 19), (16, 20)):
            c_ = (g.P(w_) + g.P(t_)) / 2
            near_hand |= (xx - c_[0]) ** 2 + (yy - c_[1]) ** 2 < (0.2 * g.sw) ** 2
        m |= box & (labels != RC.REGIONS.index("bottom")) & ((labels != RC.REGIONS.index("skin")) | ~near_hand)
    if m.sum() < 50:
        return cut
    H = a.shape[0]
    sig = max(2.0, sigma_frac * H)
    L = np.where(m, lab[..., 0], 0.0)
    num = ndi.gaussian_filter(L, sig); den = ndi.gaussian_filter(m.astype(np.float32), sig)
    smooth = np.where(den > 1e-3, num / np.maximum(den, 1e-3), lab[..., 0])
    # keep a little of the original fine shading, but clamp it so bright letters vanish
    med = float(np.median(lab[m][:, 0]))
    fine = np.clip(lab[..., 0] - smooth, -10, 1.5) * keep            # dark folds stay, bright print goes
    lab[..., 0] = np.where(m, smooth + fine, lab[..., 0])
    for c in (1, 2):
        cm = float(np.median(lab[m][:, c]))
        lab[..., c] = np.where(m, cm, lab[..., c])
    a[..., :3] = np.where(m[..., None] & (a[..., 3:4] > 0), RC._rgb(lab), a[..., :3])
    return Image.fromarray(a, "RGBA")


def dress(cut, lms, name, log=print):
    """-> (dressed cut-out, summary).  name: a template name or a JSON path"""
    from . import recolor as RC
    if os.path.isfile(name):
        spec = json.load(open(name)); label = spec.get("label", os.path.basename(name))
    else:
        outs = all_outfits()
        if name not in outs:
            raise ValueError("unknown outfit '%s' - choose from: %s" % (name, ", ".join(sorted(outs))))
        spec = outs[name]; label = spec.get("label", name)
    cut = cut.convert("RGBA")
    labels = RC.segment(cut, lms)
    if spec.get("plain"):
        cut = plain_garments(cut, labels, lms=lms)
    cols = spec.get("colours", {})
    if cols:
        rec = ",".join("%s=%s" % (k, v) for k, v in cols.items())
        cut, _ = RC.recolor_cutout(cut, lms, rec, log=None)
    cut = draw_props(cut, lms, spec.get("props", []), labels=labels, log=log)
    summary = "%s: %s%s" % (label, ", ".join(p["kind"] for p in spec.get("props", [])), "; garments plain" if spec.get("plain") else "")
    log("outfit: " + summary)
    return cut, summary

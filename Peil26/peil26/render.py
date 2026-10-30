"""Broadcast 3D view of Peil Park. Software perspective, no GPU required."""

from __future__ import annotations

import math

import numpy as np
import pygame

from peil26.settings import (
    CENTER_Z,
    CROSSBAR,
    GOAL_HALF_W,
    HALF,
    PITCH_L,
    PITCH_W,
    POST_H,
    SPONSORS,
)

SKY_TOP = np.array([10, 18, 40], dtype=np.float32)
SKY_MID = np.array([36, 54, 92], dtype=np.float32)
SKY_HOR = np.array([214, 132, 72], dtype=np.float32)
X0, Z0, X1, Z1 = -36.0, -30.0, 181.0, 120.0
SKIN = [(232, 196, 162), (204, 158, 118), (168, 116, 84), (124, 82, 56), (90, 60, 42)]
HAIR = [(36, 26, 18), (70, 46, 28), (150, 86, 40), (28, 28, 30), (186, 156, 72)]


class Camera:
    def __init__(self):
        self.eye = np.array([70.0, 18.0, -16.0], dtype=float)
        self.target = np.array([84.0, 1.0, 42.0], dtype=float)
        self.fov = 50.0
        self.mode = "broadcast"
        self.shake = 0.0
        self.fwd = np.array([0.0, 0.0, 1.0])
        self.right = np.array([1.0, 0.0, 0.0])
        self.up = np.array([0.0, 1.0, 0.0])

    def update_basis(self):
        fwd = self.target - self.eye
        n = np.linalg.norm(fwd) or 1.0
        self.fwd = fwd / n
        right = np.cross(self.fwd, np.array([0.0, 1.0, 0.0]))
        rn = np.linalg.norm(right) or 1.0
        self.right = right / rn
        self.up = np.cross(self.right, self.fwd)

    def follow(self, match, dt):
        b = match.ball
        poss = match.possession_team if match.possession_team in (0, 1) else 0
        sign = match.attack_sign(poss)
        modes = {
            "broadcast": (np.array([b.x - sign * 8.0, 9.4, -4.6]), np.array([b.x + sign * 16.0, 1.1, b.z * 0.35 + CENTER_Z * 0.65])),
            "follow": (np.array([b.x - sign * 12.0, 5.6, b.z - 6.0]), np.array([b.x + sign * 8.0, 1.1, b.z])),
            "goal": (np.array([match.attack_goal_x(poss) - sign * 12.0, 4.2, CENTER_Z + 14]), np.array([match.attack_goal_x(poss), 1.4, CENTER_Z])),
            "tactical": (np.array([b.x, 62.0, b.z + 0.4]), np.array([b.x + sign * 6, 0.0, b.z])),
            "low": (np.array([b.x - sign * 7.0, 2.6, b.z - 7]), np.array([b.x + sign * 10, 1.0, b.z])),
        }
        eye, tgt = modes.get(self.mode, modes["broadcast"])
        if self.mode == "broadcast":
            if b.x < 28:
                eye = np.array([max(-6, b.x - 14), 7.2, -2.4])
                tgt = np.array([4.0, 1.5, CENTER_Z])
            elif b.x > PITCH_L - 28:
                eye = np.array([min(PITCH_L + 6, b.x + 14), 7.2, -2.4])
                tgt = np.array([PITCH_L - 4, 1.5, CENTER_Z])
        k = 1.0 - math.exp(-2.6 * max(dt, 0.001))
        self.eye = self.eye + (eye - self.eye) * k
        self.target = self.target + (tgt - self.target) * k
        if self.shake > 0:
            self.eye[1] += math.sin(match.real_time * 46) * self.shake
            self.shake = max(0.0, self.shake - dt * 1.4)
        self.update_basis()

    def project(self, x, y, z, w, h):
        px = x - self.eye[0]
        py = y - self.eye[1]
        pz = z - self.eye[2]
        cx = px * self.right[0] + py * self.right[1] + pz * self.right[2]
        cy = px * self.up[0] + py * self.up[1] + pz * self.up[2]
        cz = px * self.fwd[0] + py * self.fwd[1] + pz * self.fwd[2]
        if cz < 0.4:
            return None
        th = math.tan(math.radians(self.fov) * 0.5)
        aspect = w / float(h)
        sx = (cx / (cz * th * aspect) * 0.5 + 0.5) * w
        sy = (1.0 - (cy / (cz * th) * 0.5 + 0.5)) * h
        return sx, sy, cz

    def ground_at(self, mx, my, w, h):
        th = math.tan(math.radians(self.fov) * 0.5)
        aspect = w / float(h)
        ndc_x = (mx / w) * 2 - 1
        ndc_y = 1 - (my / h) * 2
        direction = self.fwd + self.right * ndc_x * th * aspect + self.up * ndc_y * th
        if direction[1] >= -1e-4:
            return None
        t = -self.eye[1] / direction[1]
        if t < 0:
            return None
        return float(self.eye[0] + t * direction[0]), float(self.eye[2] + t * direction[2])


def _lerp(a, b, t):
    return a + (b - a) * t


class Renderer:
    def __init__(self):
        self.cam = Camera()
        self.tex = None
        self.crowd = None
        self.built = False
        self._ground_size = (0, 0)
        self._ground = None

    def build(self, font):
        scale = 5
        span_x = X1 - X0
        span_z = Z1 - Z0
        w, h = int(span_x * scale), int(span_z * scale)
        surf = pygame.Surface((w, h))
        surf.fill((16, 78, 40))
        # Mowing stripes across the pitch, plus a darker apron.
        pitch = pygame.Rect(int((0 - X0) * scale), int((0 - Z0) * scale), int(PITCH_L * scale), int(PITCH_W * scale))
        for i in range(0, int(PITCH_L), 6):
            col = (34, 128, 58) if (i // 6) % 2 == 0 else (26, 108, 48)
            pygame.draw.rect(surf, col, (pitch.x + int(i * scale), pitch.y, int(6 * scale) + 1, pitch.h))
        # Worn mouths and a centre stripe.
        for gx in (0.0, PITCH_L):
            cx = int((gx - X0) * scale)
            cy = int((CENTER_Z - Z0) * scale)
            pygame.draw.ellipse(surf, (22, 96, 44), (cx - 70, cy - 46, 140, 92))
        arr = np.transpose(pygame.surfarray.array3d(surf), (1, 0, 2)).astype(np.uint8)
        rng = np.random.default_rng(26)
        noise = rng.integers(-8, 9, size=arr.shape[:2], dtype=np.int16)
        arr = np.clip(arr.astype(np.int16) + noise[..., None], 0, 255).astype(np.uint8)
        self.tex = arr
        self.crowd = self._make_crowd()
        self.font = font
        self.sponsors = []
        self.built = True

    def _make_crowd(self):
        rng = np.random.default_rng(8)
        cols = rng.integers(20, 230, size=(14, 48, 3), dtype=np.uint8)
        # Bias toward jackets, county colours, and the odd flag.
        cols[:, :, 1] = (cols[:, :, 1] * 0.65).astype(np.uint8)
        return cols

    def draw(self, screen, match, fonts, replay=None, hud=True):
        w, h = screen.get_size()
        iw, ih = self._internal(w, h)
        scene = self._scene(match, iw, ih, replay)
        if (iw, ih) != (w, h):
            scene = pygame.transform.smoothscale(scene, (w, h))
        screen.blit(scene, (0, 0))
        if hud:
            self._hud(screen, match, fonts)
        if replay is not None:
            self._replay_bug(screen, fonts)

    def _internal(self, w, h):
        ih = min(560, h)
        iw = max(320, int(ih * (w / float(h))))
        return iw, ih

    def _scene(self, match, w, h, replay):
        self.cam.update_basis()
        img = self._background(w, h)
        surf = pygame.surfarray.make_surface(np.transpose(img, (1, 0, 2)))
        self._stadium(surf, w, h, match)
        self._markings(surf, w, h)
        self._goals(surf, w, h)
        self._actors(surf, w, h, match, replay)
        self._hoardings(surf, w, h)
        return surf

    def _background(self, w, h):
        ys = np.linspace(0, 1, h, dtype=np.float32)[:, None]
        t = np.clip(ys / 0.62, 0, 1)
        sky = SKY_TOP * (1 - t) + SKY_HOR * t
        sky = sky + (SKY_MID - sky) * np.clip(1 - np.abs(t - 0.45) * 2.2, 0, 1) * 0.35
        img = np.broadcast_to(sky[:, None, :].astype(np.uint8), (h, w, 3)).copy()
        eye = self.cam.eye
        fwd, right, up = self.cam.fwd, self.cam.right, self.cam.up
        th = math.tan(math.radians(self.cam.fov) * 0.5)
        aspect = w / float(h)
        xs = (np.arange(w) + 0.5) / w * 2 - 1
        yss = 1 - (np.arange(h) + 0.5) / h * 2
        ndc_x = xs[None, :] * aspect * th
        ndc_y = yss[:, None] * th
        dx = fwd[0] + right[0] * ndc_x + up[0] * ndc_y
        dy = fwd[1] + right[1] * ndc_x + up[1] * ndc_y
        dz = fwd[2] + right[2] * ndc_x + up[2] * ndc_y
        hit = dy < -1e-4
        t = np.divide(-eye[1], dy, out=np.full_like(dy, 1e6), where=hit)
        wx = eye[0] + t * dx
        wz = eye[2] + t * dz
        tex = self.tex
        u = np.clip(((wx - X0) / (X1 - X0) * (tex.shape[1] - 1)).astype(np.int32), 0, tex.shape[1] - 1)
        v = np.clip(((wz - Z0) / (Z1 - Z0) * (tex.shape[0] - 1)).astype(np.int32), 0, tex.shape[0] - 1)
        sampled = tex[v, u]
        # Only paint the ground where the ray actually lands in the venue bowl.
        venue = hit & (wx > X0) & (wx < X1) & (wz > Z0) & (wz < Z1) & (t < 220)
        img[venue] = sampled[venue]
        return img

    def _poly(self, surf, pts, color, limit=2400):
        if len(pts) < 3:
            return
        if any(abs(p[0]) > limit or abs(p[1]) > limit for p in pts):
            return
        pygame.draw.polygon(surf, color, pts)

    def _quad(self, surf, w, h, corners, color):
        pts = []
        depth = 0.0
        for x, y, z in corners:
            p = self.cam.project(x, y, z, w, h)
            if p is None or p[2] < 1.2:
                return None
            pts.append((p[0], p[1]))
            depth += p[2]
        self._poly(surf, pts, color)
        return depth / 4, pts

    def _stadium(self, surf, w, h, match):
        # Far stand, then the ends. Near stand is behind the gantry camera.
        self._stand(surf, w, h, z0=96, z1=118, x0=-8, x1=PITCH_L + 8, rows=9, cols=42, wave=True)
        self._roof(surf, w, h)
        self._stand(surf, w, h, z0=2, z1=PITCH_W - 2, x0=-22, x1=-6, rows=6, cols=14, along="z")
        self._stand(surf, w, h, z0=2, z1=PITCH_W - 2, x0=PITCH_L + 6, x1=PITCH_L + 22, rows=6, cols=14, along="z")
        self._lights(surf, w, h)

    def _stand(self, surf, w, h, z0, z1, x0, x1, rows, cols, wave=False, along="x"):
        crowd = self.crowd
        for r in range(rows):
            y0 = 1.4 + r * 1.15
            y1 = y0 + 1.05
            inset = r * 0.7
            for c in range(cols):
                col = crowd[r % crowd.shape[0], c % crowd.shape[1]]
                if wave and c == int((pygame.time.get_ticks() / 260 + c) % cols):
                    col = np.clip(col.astype(int) + 60, 0, 255)
                colour = tuple(int(v) for v in col)
                if along == "x":
                    xa = x0 + (x1 - x0) * c / cols
                    xb = x0 + (x1 - x0) * (c + 1) / cols
                    z = z0 + inset
                    self._quad(surf, w, h, [(xa, y0, z), (xb, y0, z), (xb, y1, z), (xa, y1, z)], colour)
                else:
                    # Keep the near corner out of the camera, or the quad explodes.
                    za = max(z0, 18) + (min(z1, PITCH_W - 4) - max(z0, 18)) * c / cols
                    zb = max(z0, 18) + (min(z1, PITCH_W - 4) - max(z0, 18)) * (c + 1) / cols
                    face = (x1 - inset) if x0 < 0 else (x0 + inset)
                    self._quad(surf, w, h, [(face, y0, za), (face, y0, zb), (face, y1, zb), (face, y1, za)], colour)

    def _roof(self, surf, w, h):
        quad = [(-10, 14.2, 93), (PITCH_L + 10, 14.2, 93), (PITCH_L + 14, 16.4, 122), (-14, 16.4, 122)]
        pts = []
        for x, y, z in quad:
            p = self.cam.project(x, y, z, w, h)
            if not p:
                return
            pts.append((p[0], p[1]))
        self._poly(surf, pts, (28, 32, 38))
        edge = [(-10, 14.2, 93), (PITCH_L + 10, 14.2, 93)]
        a = self.cam.project(*edge[0], w, h)
        b = self.cam.project(*edge[1], w, h)
        if a and b:
            pygame.draw.line(surf, (232, 188, 78), (a[0], a[1]), (b[0], b[1]), 2)

    def _lights(self, surf, w, h):
        for x, z in ((-8, -4), (PITCH_L + 8, -4), (-8, PITCH_W + 4), (PITCH_L + 8, PITCH_W + 4)):
            base = self.cam.project(x, 0, z, w, h)
            top = self.cam.project(x, 28, z, w, h)
            if base and top:
                pygame.draw.line(surf, (186, 190, 196), (base[0], base[1]), (top[0], top[1]), 3)
                glow = pygame.Surface((18, 18), pygame.SRCALPHA)
                pygame.draw.circle(glow, (255, 236, 190, 90), (9, 9), 8)
                surf.blit(glow, (top[0] - 9, top[1] - 9), special_flags=pygame.BLEND_ADD)

    def _markings(self, surf, w, h):
        white = (236, 240, 232)
        def line(x1, z1, x2, z2, color=white, width=2):
            a = self.cam.project(x1, 0.06, z1, w, h)
            b = self.cam.project(x2, 0.06, z2, w, h)
            if a and b:
                pygame.draw.line(surf, color, (a[0], a[1]), (b[0], b[1]), width)

        line(0, 0, PITCH_L, 0)
        line(0, PITCH_W, PITCH_L, PITCH_W)
        line(0, 0, 0, PITCH_W)
        line(PITCH_L, 0, PITCH_L, PITCH_W)
        line(HALF, 0, HALF, PITCH_W)
        for dist in (13, 20, 45):
            line(dist, 0, dist, PITCH_W)
            line(PITCH_L - dist, 0, PITCH_L - dist, PITCH_W)
        for gx, sign in ((0.0, 1), (PITCH_L, -1)):
            # rectangles
            line(gx, CENTER_Z - 7, gx + sign * 4.5, CENTER_Z - 7)
            line(gx, CENTER_Z + 7, gx + sign * 4.5, CENTER_Z + 7)
            line(gx + sign * 4.5, CENTER_Z - 7, gx + sign * 4.5, CENTER_Z + 7)
            line(gx, CENTER_Z - 9.5, gx + sign * 13, CENTER_Z - 9.5)
            line(gx, CENTER_Z + 9.5, gx + sign * 13, CENTER_Z + 9.5)
            line(gx + sign * 13, CENTER_Z - 9.5, gx + sign * 13, CENTER_Z + 9.5)
            self._arc(surf, w, h, gx)
        # halfway ticks
        for z in range(5, int(PITCH_W), 10):
            line(HALF - 0.8, z, HALF + 0.8, z, white, 1)

    def _arc(self, surf, w, h, gx):
        pts = []
        for i in range(37):
            th = math.pi * i / 36
            if gx < 1:
                x = 40 * math.sin(th)
                z = CENTER_Z - 40 * math.cos(th)
            else:
                x = PITCH_L - 40 * math.sin(th)
                z = CENTER_Z - 40 * math.cos(th)
            p = self.cam.project(x, 0.08, z, w, h)
            if p:
                pts.append((p[0], p[1]))
        if len(pts) > 2:
            pygame.draw.lines(surf, (255, 196, 64), False, pts, 3)

    def _goals(self, surf, w, h):
        for gx in (0.0, PITCH_L):
            back = -1.4 if gx < 1 else 1.4
            posts = []
            for z in (CENTER_Z - GOAL_HALF_W, CENTER_Z + GOAL_HALF_W):
                a = self.cam.project(gx, 0, z, w, h)
                b = self.cam.project(gx, POST_H, z, w, h)
                if a and b:
                    pygame.draw.line(surf, (236, 236, 236), (a[0], a[1]), (b[0], b[1]), 3)
                    posts.append((z, a, b))
            c1 = self.cam.project(gx, CROSSBAR, CENTER_Z - GOAL_HALF_W, w, h)
            c2 = self.cam.project(gx, CROSSBAR, CENTER_Z + GOAL_HALF_W, w, h)
            if c1 and c2:
                pygame.draw.line(surf, (236, 236, 236), (c1[0], c1[1]), (c2[0], c2[1]), 3)
            # Net
            for i in range(5):
                z = CENTER_Z - GOAL_HALF_W + i * (GOAL_HALF_W * 2 / 4)
                a = self.cam.project(gx, CROSSBAR, z, w, h)
                b = self.cam.project(gx + back, 0.15, z, w, h)
                if a and b:
                    pygame.draw.line(surf, (210, 214, 216), (a[0], a[1]), (b[0], b[1]), 1)
            for y in (0.6, 1.3, 2.0):
                a = self.cam.project(gx, y, CENTER_Z - GOAL_HALF_W, w, h)
                b = self.cam.project(gx, y, CENTER_Z + GOAL_HALF_W, w, h)
                if a and b:
                    pygame.draw.line(surf, (210, 214, 216), (a[0], a[1]), (b[0], b[1]), 1)

    def _actors(self, surf, w, h, match, replay):
        items = []
        if replay:
            bx, by, bz = replay["ball"][:3]
            items.append((self._depth(bx, by, bz), "ball", (bx, by, bz, replay["ball"][3] if len(replay["ball"]) > 3 else 0)))
            for rec in replay["players"]:
                team, num, x, y, z, facing, role, has, kick, dive = rec
                items.append((self._depth(x, y, z), "p", (team, num, x, y, z, facing, role, has, kick, dive, False)))
        else:
            b = match.ball
            items.append((self._depth(b.x, b.y, b.z), "ball", (b.x, b.y, b.z, b.spin)))
            for p in match.players:
                if not p.on_pitch or p.sent_off or p.in_bin:
                    continue
                items.append((self._depth(p.x, p.y, p.z), "live", p))
            items.append((self._depth(match.ref_x, 0, match.ref_z), "ref", None))
        items.sort(key=lambda it: -it[0])
        for depth, kind, obj in items:
            if kind == "ball":
                self._ball(surf, w, h, *obj)
            elif kind == "ref":
                self._figure(surf, w, h, match.ref_x, 0, match.ref_z, match.ref_facing, (20, 20, 22), (20, 20, 22), (230, 230, 230), 0, 0, False, "REF")
            elif kind == "live":
                side = match.teams[obj.team]
                controlled = obj.pid == match.controlled
                self._figure(
                    surf, w, h, obj.x, obj.y, obj.z, obj.facing,
                    side.jersey, side.shorts, side.socks, obj.kick_t, obj.solo_t,
                    controlled or obj.has_ball, f"{obj.number}",
                    skin=SKIN[obj.skin % 5], hair=HAIR[obj.hair % 5],
                    ring=side.trim if controlled else None,
                    dive=obj.dive,
                )
            else:
                team, num, x, y, z, facing, role, has, kick, dive, _ = obj
                side = match.teams[team]
                self._figure(surf, w, h, x, y, z, facing, side.jersey, side.shorts, side.socks, kick, 0, bool(has), str(num), dive=dive)

    def _depth(self, x, y, z):
        return (
            (x - self.cam.eye[0]) * self.cam.fwd[0]
            + (y - self.cam.eye[1]) * self.cam.fwd[1]
            + (z - self.cam.eye[2]) * self.cam.fwd[2]
        )

    def _figure(self, surf, w, h, x, y, z, facing, jersey, shorts, socks, kick_t, solo_t, label_on, number, skin=SKIN[1], hair=HAIR[0], ring=None, dive=0.0):
        ground = self.cam.project(x, 0.02, z, w, h)
        crown = self.cam.project(x + math.sin(facing) * dive * 0.3, 1.82 + y, z, w, h)
        if ground is None or crown is None:
            return
        height = ground[1] - crown[1]
        if height < 7 or height > 220:
            return
        cx = (ground[0] + crown[0]) * 0.5
        # A small lean so a kick or a solo reads at broadcast size.
        lean = 0.0
        if kick_t > 0.05:
            lean = height * 0.18
        elif solo_t > 0.05:
            lean = -height * 0.08
        cx += lean
        bw = max(4.0, height * 0.34)
        shadow = pygame.Rect(0, 0, int(bw * 1.7), int(max(3, height * 0.16)))
        shadow.center = (int(ground[0]), int(ground[1]))
        pygame.draw.ellipse(surf, (10, 36, 20), shadow)
        # Legs
        phase = math.sin(pygame.time.get_ticks() / 140.0 + x * 0.7)
        stride = height * (0.16 if kick_t < 0.05 else 0.28) * (phase if kick_t < 0.05 else 1)
        leg = max(2, int(height * 0.09))
        hip_y = ground[1] - height * 0.46
        pygame.draw.line(surf, socks, (cx - bw * 0.22, hip_y), (cx - bw * 0.28 - stride, ground[1]), leg)
        pygame.draw.line(surf, socks, (cx + bw * 0.22, hip_y), (cx + bw * 0.28 + stride * 0.6, ground[1]), leg)
        pygame.draw.circle(surf, (28, 28, 30), (int(cx - bw * 0.28 - stride), int(ground[1])), max(2, leg // 2))
        pygame.draw.circle(surf, (28, 28, 30), (int(cx + bw * 0.28 + stride * 0.6), int(ground[1])), max(2, leg // 2))
        # Shorts and jersey as filled kits, not sticks.
        shorts_rect = pygame.Rect(0, 0, int(bw * 1.05), int(height * 0.18))
        shorts_rect.midbottom = (int(cx), int(hip_y + height * 0.08))
        pygame.draw.rect(surf, shorts, shorts_rect, border_radius=2)
        torso = [
            (cx - bw * 0.42, ground[1] - height * 0.78),
            (cx + bw * 0.42, ground[1] - height * 0.78),
            (cx + bw * 0.52, ground[1] - height * 0.48),
            (cx - bw * 0.52, ground[1] - height * 0.48),
        ]
        pygame.draw.polygon(surf, jersey, torso)
        pygame.draw.line(surf, (255, 255, 255), torso[0], torso[1], 1)
        # Arms
        arm = max(2, int(height * 0.07))
        shoulder = ground[1] - height * 0.72
        pygame.draw.line(surf, jersey, (cx - bw * 0.42, shoulder), (cx - bw * 0.78, shoulder + height * 0.18), arm)
        pygame.draw.line(surf, skin, (cx - bw * 0.78, shoulder + height * 0.18), (cx - bw * 0.7, shoulder + height * 0.30), arm)
        pygame.draw.line(surf, jersey, (cx + bw * 0.42, shoulder), (cx + bw * 0.78, shoulder + height * 0.16 + lean * 0.2), arm)
        # Head
        rad = max(3, int(height * 0.13))
        head = (int(cx), int(ground[1] - height * 0.90))
        pygame.draw.circle(surf, skin, head, rad)
        pygame.draw.circle(surf, hair, (head[0], head[1] - rad // 3), rad, max(2, rad // 2))
        if ring:
            pygame.draw.circle(surf, ring, (int(ground[0]), int(ground[1] - 2)), int(bw * 1.15), 2)
        if label_on and self.font and height > 16:
            tag = self.font.render(str(number), True, (250, 248, 240))
            surf.blit(tag, (head[0] - tag.get_width() / 2, head[1] - rad - tag.get_height() - 1))

    def _ball(self, surf, w, h, x, y, z, spin):
        p = self.cam.project(x, y, z, w, h)
        sh = self.cam.project(x, 0.03, z, w, h)
        if sh:
            pygame.draw.ellipse(surf, (16, 48, 24), (sh[0] - 6, sh[1] - 2, 12, 5))
        if not p:
            return
        rad = max(3, int(240 / max(6, p[2])))
        pygame.draw.circle(surf, (244, 244, 242), (int(p[0]), int(p[1])), rad)
        pygame.draw.circle(surf, (186, 48, 42), (int(p[0]), int(p[1])), rad, 1)
        seam = (int(p[0] + math.cos(spin) * rad * 0.4), int(p[1] + math.sin(spin) * rad * 0.3))
        pygame.draw.line(surf, (40, 40, 42), (p[0] - rad * 0.5, p[1]), seam, 1)

    def _hoardings(self, surf, w, h):
        colors = [(18, 64, 48), (140, 32, 36), (24, 48, 96), (170, 120, 28), (32, 32, 36)]
        panels = 18
        for i in range(panels):
            x0 = i / panels * PITCH_L
            x1 = (i + 1) / panels * PITCH_L
            col = colors[i % len(colors)]
            quad = [(x0, 0.05, PITCH_W + 1.3), (x1, 0.05, PITCH_W + 1.3), (x1, 1.15, PITCH_W + 1.3), (x0, 1.15, PITCH_W + 1.3)]
            pts = []
            ok = True
            for x, y, z in quad:
                p = self.cam.project(x, y, z, w, h)
                if not p:
                    ok = False
                    break
                pts.append((p[0], p[1]))
            if ok:
                self._poly(surf, pts, col)
                span = max(p[0] for p in pts) - min(p[0] for p in pts)
                tall = max(p[1] for p in pts) - min(p[1] for p in pts)
                if self.font and span > 36 and tall > 10:
                    label = self.font.render(SPONSORS[i % len(SPONSORS)], True, (240, 236, 220))
                    if label.get_width() < span - 4:
                        cx = sum(p[0] for p in pts) / 4
                        cy = sum(p[1] for p in pts) / 4
                        surf.blit(label, (cx - label.get_width() / 2, cy - label.get_height() / 2))

    def _hud(self, screen, match, fonts):
        w, h = screen.get_size()
        self._scorebug(screen, match, fonts, w)
        self._radar(screen, match, w, h)
        self._lower_third(screen, match, fonts, w, h)
        if match.banner_t > 0:
            self._banner(screen, match, fonts, w, h)

    def _scorebug(self, screen, match, fonts, w):
        bug = pygame.Surface((640, 78), pygame.SRCALPHA)
        bug.fill((8, 14, 24, 210))
        pygame.draw.rect(bug, (232, 188, 78), (0, 0, 640, 3))
        a, b = match.teams
        self._crest(bug, 18, 14, a)
        self._crest(bug, 560, 14, b)
        score_a = fonts["score"].render(f"{a.scoreline()}  ({a.total})", True, (248, 246, 240))
        score_b = fonts["score"].render(f"{b.scoreline()}  ({b.total})", True, (248, 246, 240))
        bug.blit(score_a, (78, 16))
        bug.blit(score_b, (430 - score_b.get_width() + 80, 16))
        clock = fonts["md"].render(match.clock_str(), True, (255, 208, 90))
        bug.blit(clock, (320 - clock.get_width() / 2, 8))
        sub = fonts["xs"].render(match.period_name() + "   ·   PEIL PARK", True, (186, 196, 206))
        bug.blit(sub, (320 - sub.get_width() / 2, 40))
        # sin bins
        x = 78
        for p in a.players:
            if p.in_bin:
                bug.blit(fonts["xs"].render(f"BIN {p.number} {int(p.sin_bin // 60)}:{int(p.sin_bin % 60):02d}", True, (20, 20, 20)), (x, 58))
                pygame.draw.rect(bug, (16, 16, 16), (x - 2, 56, 92, 16))
                bug.blit(fonts["xs"].render(f"{p.number} {int(p.sin_bin // 60)}:{int(p.sin_bin % 60):02d}", True, (240, 240, 240)), (x, 56))
                x += 96
        screen.blit(bug, ((w - 640) / 2, 16))

    def _crest(self, surf, x, y, side):
        pygame.draw.circle(surf, side.jersey, (x + 22, y + 22), 20)
        pygame.draw.circle(surf, side.trim, (x + 22, y + 22), 20, 2)
        # short name drawn by caller via font stored? use a tiny fallback
        if self.font:
            t = self.font.render(side.short, True, (250, 250, 250) if sum(side.jersey) < 420 else (16, 16, 18))
            surf.blit(t, (x + 22 - t.get_width() / 2, y + 14))

    def _radar(self, screen, match, w, h):
        rw, rh = 168, 104
        rad = pygame.Surface((rw, rh), pygame.SRCALPHA)
        rad.fill((8, 16, 24, 170))
        def px(x, z):
            return 6 + x / PITCH_L * (rw - 12), 6 + z / PITCH_W * (rh - 12)
        pygame.draw.rect(rad, (40, 110, 58), (6, 6, rw - 12, rh - 12))
        pygame.draw.rect(rad, (230, 230, 220), (6, 6, rw - 12, rh - 12), 1)
        # arcs
        for gx, sign in ((0, 1), (PITCH_L, -1)):
            pts = []
            for i in range(19):
                th = math.pi * i / 18
                x = (40 * math.sin(th)) if gx < 1 else PITCH_L - 40 * math.sin(th)
                z = CENTER_Z - 40 * math.cos(th)
                pts.append(px(x, z))
            if len(pts) > 1:
                pygame.draw.lines(rad, (230, 180, 60), False, pts, 1)
        for p in match.players:
            if not p.active:
                continue
            sx, sy = px(p.x, p.z)
            col = match.teams[p.team].jersey
            pygame.draw.circle(rad, col, (int(sx), int(sy)), 3)
            if p.pid == match.controlled:
                pygame.draw.circle(rad, (255, 210, 80), (int(sx), int(sy)), 5, 1)
        bx, by = px(match.ball.x, match.ball.z)
        pygame.draw.circle(rad, (255, 255, 255), (int(bx), int(by)), 3)
        screen.blit(rad, (18, h - rh - 18))

    def _lower_third(self, screen, match, fonts, w, h):
        p = match.controlled_player()
        panel = pygame.Surface((460, 64), pygame.SRCALPHA)
        panel.fill((8, 14, 24, 185))
        if p:
            name = fonts["md"].render(f"{p.number}  {p.first} {p.surname}", True, (248, 246, 240))
            panel.blit(name, (12, 6))
            # stamina
            pygame.draw.rect(panel, (30, 40, 48), (12, 36, 160, 8), border_radius=3)
            pygame.draw.rect(panel, (92, 196, 120), (12, 36, int(160 * p.stamina), 8), border_radius=3)
            if p.has_ball:
                for i in range(4):
                    filled = p.steps >= i + 0.15
                    col = (255, 196, 64) if filled else (50, 60, 70)
                    pygame.draw.circle(panel, col, (190 + i * 16, 40), 5)
                panel.blit(fonts["xs"].render("STEPS", True, (180, 186, 194)), (250, 32))
        screen.blit(panel, (200, h - 82))
        hint = fonts["xs"].render(match.hint, True, (232, 210, 150))
        screen.blit(hint, (212, h - 22))
        if match.charge > 0.02:
            bar = pygame.Surface((220, 14), pygame.SRCALPHA)
            pygame.draw.rect(bar, (20, 24, 30), (0, 0, 220, 14), border_radius=4)
            pygame.draw.rect(bar, (255, 196, 64), (0, 0, int(220 * match.charge), 14), border_radius=4)
            screen.blit(bar, ((w - 220) / 2, h - 108))
        # shape warning
        if match.human_team in (0, 1):
            own, opp = match.shape[match.human_team]
            bad = own < 4 or opp < 3
            label = fonts["xs"].render(f"SHAPE  {own}/4   {opp}/3", True, (255, 120, 90) if bad else (170, 190, 170))
            screen.blit(label, (w - label.get_width() - 24, h - 36))
        if match.ticker:
            y = h - 150
            for i, line in enumerate(list(match.ticker)[:3]):
                t = fonts["xs"].render(line, True, (220, 224, 228))
                screen.blit(t, (24, y + i * 16))

    def _banner(self, screen, match, fonts, w, h):
        kind = match.banner_kind
        big = kind in ("goal", "point", "two", "penalty", "black", "red", "hooter")
        if big:
            word = {"goal": "GOAL", "point": "POINT", "two": "2 POINTS", "penalty": "PENALTY", "black": "BLACK CARD", "red": "RED CARD", "hooter": "HOOTER"}.get(kind, match.banner)
            col = {"goal": (255, 208, 64), "two": (255, 176, 48), "point": (236, 236, 236), "black": (230, 230, 230), "red": (220, 64, 58), "penalty": (255, 208, 64)}.get(kind, (248, 246, 240))
            text = fonts["xl"].render(word, True, col)
            shadow = fonts["xl"].render(word, True, (8, 10, 16))
            screen.blit(shadow, ((w - text.get_width()) / 2 + 3, h * 0.30 + 3))
            screen.blit(text, ((w - text.get_width()) / 2, h * 0.30))
            sub = fonts["md"].render(match.banner, True, (244, 240, 230))
            screen.blit(sub, ((w - sub.get_width()) / 2, h * 0.30 + text.get_height() + 4))
            if match.banner_sub and kind in ("goal", "point", "two"):
                line = fonts["sm"].render(match.banner_sub, True, (220, 210, 180))
                screen.blit(line, ((w - line.get_width()) / 2, h * 0.30 + text.get_height() + 36))
        else:
            box = fonts["md"].render(match.banner, True, (248, 246, 240))
            bg = pygame.Surface((box.get_width() + 28, box.get_height() + 12), pygame.SRCALPHA)
            bg.fill((8, 14, 24, 200))
            screen.blit(bg, ((w - bg.get_width()) / 2, 108))
            screen.blit(box, ((w - box.get_width()) / 2, 114))

    def _replay_bug(self, screen, fonts):
        t = fonts["sm"].render("REPLAY", True, (16, 16, 16))
        bg = pygame.Surface((t.get_width() + 16, t.get_height() + 8))
        bg.fill((255, 208, 64))
        bg.blit(t, (8, 4))
        screen.blit(bg, (24, 110))


def draw_menu_panel(screen, fonts, title, lines, index, footer):
    w, h = screen.get_size()
    shade = pygame.Surface((w, h), pygame.SRCALPHA)
    shade.fill((4, 8, 16, 90))
    screen.blit(shade, (0, 0))
    panel = pygame.Surface((520, h), pygame.SRCALPHA)
    panel.fill((8, 14, 24, 215))
    screen.blit(panel, (0, 0))
    screen.blit(fonts["lg"].render("PEIL 26", True, (255, 204, 78)), (36, 36))
    screen.blit(fonts["sm"].render(title, True, (210, 216, 222)), (40, 100))
    y = 160
    for i, line in enumerate(lines):
        col = (255, 208, 90) if i == index else (232, 234, 236)
        prefix = ">  " if i == index else "    "
        screen.blit(fonts["md"].render(prefix + line, True, col), (48, y))
        y += 42
    screen.blit(fonts["xs"].render(footer, True, (160, 168, 176)), (40, h - 36))

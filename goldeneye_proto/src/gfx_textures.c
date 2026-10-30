/*
 * gfx_textures.c - procedural, tileable texture generation (no external art needed).
 * Every texture can also be exported to / loaded from assets/textures/<name>.png
 * so artists can replace them (run: game.exe --export-textures).
 */

typedef struct { int w, h; Color *p; } Cv;

static unsigned int HashU(int x, int y, int s)
{
    unsigned int h = (unsigned int)x*374761393u + (unsigned int)y*668265263u + (unsigned int)s*2246822519u;
    h = (h ^ (h >> 13)) * 1274126177u;
    return h ^ (h >> 16);
}
static float H01(int x, int y, int s) { return (float)(HashU(x, y, s) & 0xffffff) / 16777215.0f; }
static float Lat(int x, int y, int px, int py, int s) { x = ((x % px) + px) % px; y = ((y % py) + py) % py; return H01(x, y, s); }
static float VNoise(float x, float y, int px, int py, int s)
{
    int x0 = (int)floorf(x), y0 = (int)floorf(y);
    float fx = x - x0, fy = y - y0;
    fx = fx*fx*(3 - 2*fx); fy = fy*fy*(3 - 2*fy);
    float a = Lat(x0, y0, px, py, s), b = Lat(x0 + 1, y0, px, py, s);
    float c = Lat(x0, y0 + 1, px, py, s), d = Lat(x0 + 1, y0 + 1, px, py, s);
    return (a + (b - a)*fx) + ((c + (d - c)*fx) - (a + (b - a)*fx))*fy;
}
/* tileable fBm, u,v in [0,1) */
static float Fbm(float u, float v, int cx, int cy, int oct, int s)
{
    float sum = 0, amp = 0.5f, norm = 0;
    for (int i = 0; i < oct; i++) {
        sum += amp * VNoise(u*cx, v*cy, cx, cy, s + i*17);
        norm += amp; amp *= 0.5f; cx *= 2; cy *= 2;
    }
    return sum / norm;
}

static unsigned char ClampB(float v) { return (unsigned char)(v < 0 ? 0 : v > 255 ? 255 : v); }
static Cv CvNew(int w, int h, Color c)
{
    Cv cv = { w, h, (Color *)MemAlloc(w*h*sizeof(Color)) };
    for (int i = 0; i < w*h; i++) cv.p[i] = c;
    return cv;
}
static Color *CvAt(Cv *c, int x, int y) { x %= c->w; if (x < 0) x += c->w; y %= c->h; if (y < 0) y += c->h; return &c->p[y*c->w + x]; }
static void CvBlend(Cv *c, int x, int y, Color col, float a)
{
    Color *p = CvAt(c, x, y);
    p->r = ClampB(p->r + (col.r - p->r)*a); p->g = ClampB(p->g + (col.g - p->g)*a);
    p->b = ClampB(p->b + (col.b - p->b)*a); p->a = ClampB(p->a + (col.a - p->a)*a);
}
static void CvMulPx(Cv *c, int x, int y, float f) { Color *p = CvAt(c, x, y); p->r = ClampB(p->r*f); p->g = ClampB(p->g*f); p->b = ClampB(p->b*f); }
static void CvAddPx(Cv *c, int x, int y, float v) { Color *p = CvAt(c, x, y); p->r = ClampB(p->r + v); p->g = ClampB(p->g + v); p->b = ClampB(p->b + v); }
static void CvRect(Cv *c, int x, int y, int w, int h, Color col, float a) { for (int j = y; j < y + h; j++) for (int i = x; i < x + w; i++) CvBlend(c, i, j, col, a); }
static void CvRectMul(Cv *c, int x, int y, int w, int h, float f) { for (int j = y; j < y + h; j++) for (int i = x; i < x + w; i++) CvMulPx(c, i, j, f); }
static void CvBevel(Cv *c, int x, int y, int w, int h, int t, float hi, float lo)
{
    for (int k = 0; k < t; k++) {
        for (int i = x + k; i < x + w - k; i++) { CvMulPx(c, i, y + k, hi); CvMulPx(c, i, y + h - 1 - k, lo); }
        for (int j = y + k + 1; j < y + h - k - 1; j++) { CvMulPx(c, x + k, j, hi); CvMulPx(c, x + w - 1 - k, j, lo); }
    }
}
static void CvNoise(Cv *c, int cells, int oct, float amt, int seed)
{
    int cy = cells * c->h / c->w; if (cy < 1) cy = 1;
    for (int y = 0; y < c->h; y++) for (int x = 0; x < c->w; x++) {
        float n = Fbm((float)x / c->w, (float)y / c->h, cells, cy, oct, seed) - 0.5f;
        CvAddPx(c, x, y, n*amt);
    }
}
/* stretched noise for brushed metal / wood grain */
static void CvNoiseAniso(Cv *c, int cx, int cy, int oct, float amt, int seed)
{
    for (int y = 0; y < c->h; y++) for (int x = 0; x < c->w; x++) {
        float n = Fbm((float)x / c->w, (float)y / c->h, cx, cy, oct, seed) - 0.5f;
        CvAddPx(c, x, y, n*amt);
    }
}
static void CvSpeckle(Cv *c, float density, float amt, int seed)
{
    for (int y = 0; y < c->h; y++) for (int x = 0; x < c->w; x++)
        if (H01(x, y, seed) < density) CvAddPx(c, x, y, (H01(x, y, seed + 1) - 0.5f)*2*amt);
}
static void CvCircle(Cv *c, float cx, float cy, float r, Color col, float a, bool soft)
{
    for (int y = (int)(cy - r - 1); y <= (int)(cy + r + 1); y++)
        for (int x = (int)(cx - r - 1); x <= (int)(cx + r + 1); x++) {
            float d = sqrtf((x + 0.5f - cx)*(x + 0.5f - cx) + (y + 0.5f - cy)*(y + 0.5f - cy));
            float k = soft ? 1.0f - d / r : Clamp(r - d + 0.5f, 0.0f, 1.0f);
            if (k > 0) CvBlend(c, x, y, col, a*Clamp(k, 0, 1));
        }
}
static void CvRivet(Cv *c, float x, float y, float r)
{
    CvCircle(c, x + 1, y + 1, r, (Color){ 0, 0, 0, 255 }, 0.5f, false);
    CvCircle(c, x, y, r, (Color){ 170, 175, 180, 255 }, 0.9f, false);
    CvCircle(c, x - r*0.3f, y - r*0.3f, r*0.45f, (Color){ 235, 235, 240, 255 }, 0.8f, true);
}
static void CvText(Cv *c, const char *t, int x, int y, int size, Color col)
{
    Image im = { c->p, c->w, c->h, 1, PIXELFORMAT_UNCOMPRESSED_R8G8B8A8 };
    ImageDrawText(&im, t, x, y, size, col);
}
static void CvStripes(Cv *c, int x, int y, int w, int h, int period, Color a, Color b)
{
    for (int j = y; j < y + h; j++) for (int i = x; i < x + w; i++) {
        int k = ((i + j) % period + period) % period;
        Color col = k < period/2 ? a : b;
        CvBlend(c, i, j, col, 1.0f);
    }
}
static void CvSeg(Cv *c, float x0, float y0, float x1, float y1, float wdt, Color col, float a)
{
    int minx = (int)fminf(x0, x1) - (int)wdt - 1, maxx = (int)fmaxf(x0, x1) + (int)wdt + 1;
    int miny = (int)fminf(y0, y1) - (int)wdt - 1, maxy = (int)fmaxf(y0, y1) + (int)wdt + 1;
    float dx = x1 - x0, dy = y1 - y0, L2 = dx*dx + dy*dy + 1e-6f;
    for (int y = miny; y <= maxy; y++) for (int x = minx; x <= maxx; x++) {
        float t = Clamp(((x - x0)*dx + (y - y0)*dy) / L2, 0, 1);
        float px = x0 + dx*t - x, py = y0 + dy*t - y;
        float d = sqrtf(px*px + py*py);
        if (d < wdt) CvBlend(c, x, y, col, a*Clamp(wdt - d, 0, 1));
    }
}
static void CvWoodGrain(Cv *c, int x, int y, int w, int h, Color base, int seed, bool vertical)
{
    for (int j = y; j < y + h; j++) for (int i = x; i < x + w; i++) {
        float u = vertical ? (float)(i - x) / w : (float)(j - y) / h;
        float v = vertical ? (float)(j - y) / h : (float)(i - x) / w;
        float n = Fbm(u*0.5f + seed*0.13f, v*0.5f, 4, 1, 3, seed);
        float ring = 0.5f + 0.5f*sinf((u*7.0f + n*6.0f)*6.2831f);
        float f = 0.78f + 0.22f*ring + (H01(i, j, seed) - 0.5f)*0.06f;
        CvBlend(c, i, j, (Color){ ClampB(base.r*f), ClampB(base.g*f), ClampB(base.b*f), 255 }, 1.0f);
    }
}

/* ---------------- individual textures ---------------- */
static Cv TexWallConcrete(void)
{
    Cv c = CvNew(256, 384, (Color){ 150, 147, 138, 255 });
    CvNoise(&c, 4, 5, 55, 11); CvNoise(&c, 32, 3, 16, 12); CvSpeckle(&c, 0.08f, 14, 13);
    for (int y = 0; y < 384; y += 96) for (int x = 0; x < 256; x++) { CvMulPx(&c, x, y, 0.8f); CvMulPx(&c, x, y + 1, 1.07f); }
    for (int gx = 32; gx < 256; gx += 128) for (int gy = 48; gy < 330; gy += 96) {
        CvCircle(&c, gx, gy, 4.5f, (Color){ 60, 58, 54, 255 }, 0.8f, false);
        CvCircle(&c, gx - 1, gy - 1, 2.5f, (Color){ 30, 30, 30, 255 }, 0.8f, false);
    }
    for (int k = 0; k < 7; k++) {
        int sx = (int)(H01(k, 0, 5)*256), len = 60 + (int)(H01(k, 1, 5)*220), wd = 4 + (int)(H01(k, 2, 5)*10);
        for (int y = 0; y < len; y++) for (int x = sx; x < sx + wd; x++) CvMulPx(&c, x, y, 1.0f - 0.18f*(1.0f - (float)y/len));
    }
    CvRect(&c, 0, 350, 256, 34, (Color){ 58, 64, 56, 255 }, 1.0f);
    CvNoise(&c, 16, 2, 8, 14);
    CvBevel(&c, 0, 350, 256, 34, 2, 1.35f, 0.65f);
    for (int x = 0; x < 256; x++) CvMulPx(&c, x, 349, 0.5f);
    return c;
}
static Cv TexWallMetal(void)
{
    Cv c = CvNew(256, 384, (Color){ 98, 108, 116, 255 });
    CvNoiseAniso(&c, 2, 96, 3, 22, 21);
    for (int py = 0; py < 3; py++) for (int px = 0; px < 2; px++) {
        int x = px*128, y = py*112, h = 112;
        float tint = 0.93f + 0.12f*H01(px, py, 22);
        CvRectMul(&c, x + 3, y + 3, 122, h - 6, tint);
        CvBevel(&c, x, y, 128, h, 3, 1.35f, 0.55f);
        CvBevel(&c, x + 6, y + 6, 116, h - 12, 1, 0.7f, 1.25f);
        CvRivet(&c, x + 12, y + 12, 3); CvRivet(&c, x + 116, y + 12, 3);
        CvRivet(&c, x + 12, y + h - 12, 3); CvRivet(&c, x + 116, y + h - 12, 3);
    }
    CvStripes(&c, 0, 336, 256, 20, 32, (Color){ 220, 175, 30, 255 }, (Color){ 25, 25, 25, 255 });
    CvNoise(&c, 32, 2, 20, 23);
    CvBevel(&c, 0, 336, 256, 20, 1, 1.3f, 0.6f);
    CvRect(&c, 0, 356, 256, 28, (Color){ 45, 48, 52, 255 }, 1.0f);
    CvBevel(&c, 0, 356, 256, 28, 2, 1.4f, 0.6f);
    return c;
}
static Cv TexWallBrick(void)
{
    Cv c = CvNew(256, 384, (Color){ 165, 160, 150, 255 });
    CvNoise(&c, 16, 3, 20, 31);
    int bh = 28, bw = 64;
    for (int row = 0; row * bh < 352; row++) {
        int off = (row & 1) ? bw/2 : 0;
        for (int b = -1; b < 256/bw + 1; b++) {
            int x = b*bw + off, y = row*bh;
            float v = H01(b + 10, row, 32);
            Color bc = { ClampB(138 + 40*v), ClampB(62 + 20*v), ClampB(44 + 10*v), 255 };
            CvRect(&c, x + 2, y + 2, bw - 3, bh - 3, bc, 1.0f);
            CvBevel(&c, x + 2, y + 2, bw - 3, bh - 3, 2, 1.18f, 0.72f);
        }
    }
    CvNoise(&c, 32, 3, 26, 33); CvSpeckle(&c, 0.12f, 18, 34);
    CvRect(&c, 0, 352, 256, 32, (Color){ 110, 108, 100, 255 }, 1.0f);
    CvNoise(&c, 16, 2, 12, 35);
    CvBevel(&c, 0, 352, 256, 32, 2, 1.3f, 0.6f);
    return c;
}
static Cv TexWallLab(void)
{
    Cv c = CvNew(256, 384, (Color){ 170, 192, 176, 255 });
    CvNoise(&c, 8, 3, 14, 41);
    for (int y = 160; y < 384; y += 32) for (int x = 0; x < 256; x += 32) {
        float v = H01(x, y, 42);
        CvRect(&c, x, y, 32, 32, (Color){ 120, 125, 120, 255 }, 1.0f);
        CvRect(&c, x + 2, y + 2, 29, 29, (Color){ ClampB(222 + 14*v), ClampB(226 + 12*v), ClampB(220 + 10*v), 255 }, 1.0f);
        CvBevel(&c, x + 2, y + 2, 29, 29, 2, 1.04f, 0.86f);
        CvCircle(&c, x + 9, y + 8, 5, WHITE, 0.25f, true);
    }
    CvRect(&c, 0, 150, 256, 10, (Color){ 40, 95, 70, 255 }, 1.0f);
    CvBevel(&c, 0, 150, 256, 10, 2, 1.3f, 0.6f);
    CvRect(&c, 0, 360, 256, 24, (Color){ 40, 95, 70, 255 }, 1.0f);
    CvBevel(&c, 0, 360, 256, 24, 2, 1.3f, 0.6f);
    CvSpeckle(&c, 0.05f, 10, 43);
    return c;
}
static Cv TexWallWood(void)
{
    Cv c = CvNew(256, 384, (Color){ 120, 80, 48, 255 });
    for (int p = 0; p < 8; p++) {
        CvWoodGrain(&c, p*32, 0, 32, 384, (Color){ ClampB(118 + 18*H01(p, 0, 51)), ClampB(76 + 10*H01(p, 1, 51)), 44, 255 }, 50 + p, true);
        for (int y = 0; y < 384; y++) { CvMulPx(&c, p*32, y, 0.45f); CvMulPx(&c, p*32 + 1, y, 1.15f); }
    }
    CvRect(&c, 0, 196, 256, 14, (Color){ 90, 56, 30, 255 }, 1.0f);
    CvBevel(&c, 0, 196, 256, 14, 3, 1.4f, 0.55f);
    for (int k = 0; k < 2; k++) CvBevel(&c, k*128 + 14, 226, 100, 110, 4, 1.25f, 0.65f);
    CvRect(&c, 0, 352, 256, 32, (Color){ 60, 36, 20, 255 }, 1.0f);
    CvBevel(&c, 0, 352, 256, 32, 3, 1.4f, 0.6f);
    CvRect(&c, 0, 0, 256, 10, (Color){ 80, 50, 28, 255 }, 1.0f);
    CvBevel(&c, 0, 0, 256, 10, 2, 1.3f, 0.6f);
    return c;
}
static Cv TexFloorConcrete(void)
{
    Cv c = CvNew(256, 256, (Color){ 118, 116, 110, 255 });
    CvNoise(&c, 4, 5, 46, 61); CvNoise(&c, 64, 2, 14, 62); CvSpeckle(&c, 0.1f, 16, 63);
    for (int i = 0; i < 256; i++) { CvMulPx(&c, i, 0, 0.55f); CvMulPx(&c, 0, i, 0.55f); CvMulPx(&c, i, 1, 1.1f); CvMulPx(&c, 1, i, 1.1f); }
    for (int k = 0; k < 3; k++) {
        float x = H01(k, 0, 64)*256, y = H01(k, 1, 64)*256, a = H01(k, 2, 64)*6.28f;
        for (int s = 0; s < 40; s++) {
            float nx = x + cosf(a)*4, ny = y + sinf(a)*4;
            CvSeg(&c, x, y, nx, ny, 1.0f, (Color){ 50, 48, 45, 255 }, 0.6f);
            x = nx; y = ny; a += (H01(k, s, 65) - 0.5f)*1.2f;
        }
    }
    for (int k = 0; k < 4; k++) CvCircle(&c, H01(k, 5, 66)*256, H01(k, 6, 66)*256, 14 + 20*H01(k, 7, 66), (Color){ 70, 68, 62, 255 }, 0.25f, true);
    return c;
}
static Cv TexFloorTile(void)
{
    Cv c = CvNew(256, 256, (Color){ 50, 50, 50, 255 });
    for (int ty = 0; ty < 4; ty++) for (int tx = 0; tx < 4; tx++) {
        bool dark = (tx + ty) & 1;
        float v = H01(tx, ty, 71);
        Color col = dark ? (Color){ ClampB(62 + 10*v), ClampB(70 + 10*v), ClampB(78 + 8*v), 255 } : (Color){ ClampB(196 + 14*v), ClampB(186 + 12*v), ClampB(160 + 10*v), 255 };
        CvRect(&c, tx*64 + 2, ty*64 + 2, 61, 61, col, 1.0f);
        CvBevel(&c, tx*64 + 2, ty*64 + 2, 61, 61, 2, 1.08f, 0.85f);
    }
    CvNoise(&c, 8, 4, 22, 72); CvSpeckle(&c, 0.06f, 12, 73);
    return c;
}
static Cv TexFloorMetal(void)
{
    Cv c = CvNew(256, 256, (Color){ 108, 112, 116, 255 });
    CvNoise(&c, 8, 4, 28, 81);
    for (int cy = 0; cy < 256; cy += 32) for (int cx = 0; cx < 256; cx += 32) {
        CvSeg(&c, cx + 3 + 1, cy + 13 + 1, cx + 13 + 1, cy + 3 + 1, 2.2f, (Color){ 40, 42, 44, 255 }, 0.6f);
        CvSeg(&c, cx + 3, cy + 13, cx + 13, cy + 3, 2.0f, (Color){ 165, 170, 175, 255 }, 0.9f);
        CvSeg(&c, cx + 19 + 1, cy + 19 + 1, cx + 29 + 1, cy + 29 + 1, 2.2f, (Color){ 40, 42, 44, 255 }, 0.6f);
        CvSeg(&c, cx + 19, cy + 19, cx + 29, cy + 29, 2.0f, (Color){ 165, 170, 175, 255 }, 0.9f);
    }
    for (int i = 0; i < 256; i++) { CvMulPx(&c, i, 0, 0.5f); CvMulPx(&c, 0, i, 0.5f); CvMulPx(&c, i, 128, 0.6f); CvMulPx(&c, 128, i, 0.6f); }
    CvNoise(&c, 4, 3, 30, 82);
    return c;
}
static Cv TexFloorWood(void)
{
    Cv c = CvNew(256, 256, (Color){ 130, 86, 50, 255 });
    for (int r = 0; r < 8; r++) {
        int off = (int)(H01(r, 0, 91)*256);
        for (int seg = 0; seg < 2; seg++) {
            int x0 = off + seg*128;
            Color base = { ClampB(128 + 30*H01(r, seg, 92)), ClampB(84 + 16*H01(r, seg, 93)), ClampB(46 + 10*H01(r, seg, 94)), 255 };
            CvWoodGrain(&c, x0, r*32, 128, 32, base, 90 + r*3 + seg, false);
            for (int j = 0; j < 32; j++) CvMulPx(&c, x0, r*32 + j, 0.45f);
        }
        for (int i = 0; i < 256; i++) { CvMulPx(&c, i, r*32, 0.45f); CvMulPx(&c, i, r*32 + 1, 1.15f); }
    }
    return c;
}
static Cv TexFloorLab(void)
{
    Cv c = CvNew(256, 256, (Color){ 140, 140, 135, 255 });
    for (int y = 0; y < 256; y += 16) for (int x = 0; x < 256; x += 16) {
        float v = H01(x, y, 101);
        CvRect(&c, x + 1, y + 1, 15, 15, (Color){ ClampB(210 + 20*v), ClampB(214 + 18*v), ClampB(206 + 14*v), 255 }, 1.0f);
    }
    CvNoise(&c, 8, 3, 20, 102);
    return c;
}
static Cv TexCeilTile(void)
{
    Cv c = CvNew(256, 256, (Color){ 205, 202, 192, 255 });
    CvNoise(&c, 8, 3, 18, 111);
    for (int y = 0; y < 256; y++) for (int x = 0; x < 256; x++) if (H01(x, y, 112) < 0.07f) CvMulPx(&c, x, y, 0.75f);
    for (int k = 0; k < 2; k++) for (int i = 0; i < 256; i++)
        for (int t = 0; t < 4; t++) { CvBlend(&c, i, k*128 + t, (Color){ 165, 168, 170, 255 }, 1.0f); CvBlend(&c, k*128 + t, i, (Color){ 165, 168, 170, 255 }, 1.0f); }
    for (int k = 0; k < 2; k++) for (int i = 0; i < 256; i++) { CvMulPx(&c, i, k*128 + 4, 0.7f); CvMulPx(&c, k*128 + 4, i, 0.7f); }
    CvCircle(&c, 190, 60, 30, (Color){ 150, 130, 90, 255 }, 0.25f, true);
    return c;
}
static Cv TexCeilConcrete(void)
{
    Cv c = CvNew(256, 256, (Color){ 110, 110, 108, 255 });
    CvNoise(&c, 4, 5, 40, 121); CvNoiseAniso(&c, 1, 32, 2, 14, 122);
    for (int k = 0; k < 256; k += 64) for (int i = 0; i < 256; i++) { CvMulPx(&c, i, k, 0.7f); CvMulPx(&c, i, k + 1, 1.1f); }
    return c;
}
static Cv TexDoor(void)
{
    Cv c = CvNew(256, 384, (Color){ 92, 108, 120, 255 });
    CvNoiseAniso(&c, 2, 64, 3, 18, 131);
    CvBevel(&c, 0, 0, 256, 384, 8, 1.3f, 0.55f);
    CvBevel(&c, 24, 170, 208, 120, 4, 0.7f, 1.25f);
    CvRect(&c, 78, 40, 100, 100, (Color){ 30, 35, 40, 255 }, 1.0f);
    CvRect(&c, 84, 46, 88, 88, (Color){ 40, 70, 90, 255 }, 1.0f);
    for (int k = 0; k < 40; k++) CvSeg(&c, 90 + k, 130, 120 + k, 50, 1.0f, (Color){ 140, 180, 200, 255 }, k < 12 ? 0.25f : 0.0f);
    CvBevel(&c, 78, 40, 100, 100, 4, 0.6f, 1.4f);
    CvRect(&c, 206, 200, 16, 40, (Color){ 170, 172, 175, 255 }, 1.0f);
    CvBevel(&c, 206, 200, 16, 40, 2, 1.3f, 0.6f);
    CvStripes(&c, 8, 322, 240, 54, 40, (Color){ 225, 180, 30, 255 }, (Color){ 25, 25, 25, 255 });
    CvNoise(&c, 32, 2, 24, 132);
    CvBevel(&c, 8, 322, 240, 54, 2, 1.3f, 0.6f);
    CvText(&c, "B-12", 30, 180, 30, (Color){ 230, 230, 230, 200 });
    for (int k = 0; k < 5; k++) { CvRivet(&c, 20 + k*54, 20, 3); CvRivet(&c, 20 + k*54, 306, 3); }
    return c;
}
static Cv TexDoorArmory(void)
{
    Cv c = CvNew(256, 384, (Color){ 128, 38, 32, 255 });
    CvNoiseAniso(&c, 2, 64, 3, 20, 141); CvNoise(&c, 8, 3, 20, 142);
    CvStripes(&c, 0, 0, 256, 18, 36, (Color){ 230, 185, 30, 255 }, (Color){ 20, 20, 20, 255 });
    CvStripes(&c, 0, 366, 256, 18, 36, (Color){ 230, 185, 30, 255 }, (Color){ 20, 20, 20, 255 });
    CvStripes(&c, 0, 18, 18, 348, 36, (Color){ 230, 185, 30, 255 }, (Color){ 20, 20, 20, 255 });
    CvStripes(&c, 238, 18, 18, 348, 36, (Color){ 230, 185, 30, 255 }, (Color){ 20, 20, 20, 255 });
    CvBevel(&c, 18, 18, 220, 348, 4, 1.3f, 0.55f);
    for (int k = 0; k < 4; k++) { CvRect(&c, 30, 60 + k*80, 196, 10, (Color){ 90, 26, 22, 255 }, 1.0f); CvBevel(&c, 30, 60 + k*80, 196, 10, 2, 1.4f, 0.6f); }
    for (int k = 0; k < 6; k++) for (int j = 0; j < 4; j++) CvRivet(&c, 36 + k*37, 65 + j*80, 2.5f);
    CvText(&c, "ARMOURY", 46, 120, 30, (Color){ 240, 230, 210, 230 });
    CvText(&c, "RESTRICTED", 64, 270, 20, (Color){ 240, 220, 120, 210 });
    CvNoise(&c, 64, 2, 16, 143);
    return c;
}
static Cv TexHazard(void)
{
    Cv c = CvNew(128, 128, BLACK);
    CvStripes(&c, 0, 0, 128, 128, 32, (Color){ 228, 182, 28, 255 }, (Color){ 22, 22, 22, 255 });
    CvNoise(&c, 8, 4, 40, 151); CvSpeckle(&c, 0.08f, 30, 152);
    return c;
}
static Cv TexGlass(void)
{
    Cv c = CvNew(128, 128, (Color){ 150, 195, 225, 60 });
    for (int y = 0; y < 128; y++) for (int x = 0; x < 128; x++) {
        float d = (float)((x + y) % 128);
        float s = (d > 20 && d < 34) ? 1.0f : (d > 44 && d < 50) ? 0.6f : 0.0f;
        Color *p = CvAt(&c, x, y);
        p->a = ClampB(60 + s*90 + (Fbm(x/128.0f, y/128.0f, 4, 4, 2, 153) - 0.5f)*30);
        p->r = ClampB(p->r + s*80); p->g = ClampB(p->g + s*50); p->b = ClampB(p->b + s*25);
    }
    return c;
}
static Cv TexCrate(void)
{
    Cv c = CvNew(128, 128, (Color){ 150, 112, 64, 255 });
    for (int p = 0; p < 4; p++) CvWoodGrain(&c, 0, p*32, 128, 32, (Color){ ClampB(150 + 20*H01(p, 0, 161)), ClampB(112 + 12*H01(p, 1, 161)), 64, 255 }, 160 + p, false);
    for (int p = 1; p < 4; p++) for (int i = 0; i < 128; i++) CvMulPx(&c, i, p*32, 0.5f);
    CvSeg(&c, 14, 114, 114, 14, 7, (Color){ 120, 86, 46, 255 }, 1.0f);
    CvSeg(&c, 14, 114, 114, 14, 1, (Color){ 70, 50, 26, 255 }, 0.5f);
    CvRect(&c, 0, 0, 128, 14, (Color){ 112, 80, 44, 255 }, 1.0f); CvRect(&c, 0, 114, 128, 14, (Color){ 112, 80, 44, 255 }, 1.0f);
    CvRect(&c, 0, 0, 14, 128, (Color){ 112, 80, 44, 255 }, 1.0f); CvRect(&c, 114, 0, 14, 128, (Color){ 112, 80, 44, 255 }, 1.0f);
    CvNoiseAniso(&c, 1, 16, 3, 20, 162);
    CvBevel(&c, 0, 0, 128, 128, 3, 1.25f, 0.55f); CvBevel(&c, 14, 14, 100, 100, 2, 0.6f, 1.25f);
    int nails[8][2] = { { 7, 7 }, { 120, 7 }, { 7, 120 }, { 120, 120 }, { 64, 7 }, { 64, 120 }, { 7, 64 }, { 120, 64 } };
    for (int k = 0; k < 8; k++) CvCircle(&c, nails[k][0], nails[k][1], 1.6f, (Color){ 50, 50, 50, 255 }, 1.0f, false);
    CvText(&c, "07", 40, 52, 20, (Color){ 40, 30, 20, 150 });
    return c;
}
static Cv TexBarrel(void)
{
    Cv c = CvNew(128, 128, (Color){ 40, 80, 130, 255 });
    CvNoise(&c, 8, 4, 30, 171); CvNoiseAniso(&c, 16, 1, 2, 16, 172);
    int ribs[3] = { 10, 64, 118 };
    for (int k = 0; k < 3; k++) for (int x = 0; x < 128; x++) { for (int t = -3; t <= 3; t++) CvMulPx(&c, x, ribs[k] + t, t < 0 ? 1.25f : 0.7f); }
    CvStripes(&c, 0, 26, 128, 12, 16, (Color){ 225, 180, 30, 255 }, (Color){ 25, 25, 25, 255 });
    CvRect(&c, 40, 76, 48, 30, (Color){ 220, 220, 210, 255 }, 1.0f);
    CvText(&c, "FUEL", 46, 84, 12, (Color){ 30, 30, 30, 255 });
    for (int k = 0; k < 6; k++) CvCircle(&c, H01(k, 0, 173)*128, H01(k, 1, 173)*128, 6 + 8*H01(k, 2, 173), (Color){ 110, 60, 30, 255 }, 0.35f, true);
    return c;
}
static Cv TexScreen(void)
{
    Cv c = CvNew(128, 128, (Color){ 6, 26, 14, 255 });
    for (int row = 0; row < 12; row++) {
        int len = 20 + (int)(H01(row, 0, 181)*90);
        for (int x = 8; x < 8 + len; x += 6) if (H01(x, row, 182) > 0.25f) CvRect(&c, x, 10 + row*9, 4, 5, (Color){ 80, 255, 140, 255 }, 0.9f);
    }
    for (int y = 0; y < 128; y += 2) for (int x = 0; x < 128; x++) CvMulPx(&c, x, y, 0.8f);
    CvCircle(&c, 64, 64, 80, (Color){ 40, 120, 70, 255 }, 0.25f, true);
    return c;
}
static Cv TexRack(void)
{
    Cv c = CvNew(128, 256, (Color){ 30, 32, 36, 255 });
    CvNoise(&c, 8, 2, 10, 191);
    for (int u = 0; u < 16; u++) {
        CvBevel(&c, 4, u*16, 120, 16, 1, 1.6f, 0.5f);
        for (int k = 0; k < 6; k++) {
            float r = H01(u, k, 192);
            Color led = r < 0.5f ? (Color){ 60, 255, 90, 255 } : r < 0.8f ? (Color){ 255, 170, 40, 255 } : (Color){ 255, 60, 40, 255 };
            if (H01(u, k, 193) < 0.7f) CvCircle(&c, 12 + k*7, u*16 + 8, 1.8f, led, 1.0f, false);
        }
        for (int v = 60; v < 118; v += 4) CvRect(&c, v, u*16 + 4, 2, 8, (Color){ 15, 15, 18, 255 }, 1.0f);
    }
    return c;
}
static Cv TexDesk(void)
{
    Cv c = CvNew(128, 128, (Color){ 150, 142, 124, 255 });
    CvNoise(&c, 8, 4, 18, 201); CvSpeckle(&c, 0.2f, 8, 202);
    CvBevel(&c, 0, 0, 128, 128, 3, 0.8f, 0.7f);
    return c;
}
static Cv TexSolid(Color base, int seed, float noiseAmt, int anisoX, int anisoY)
{
    Cv c = CvNew(128, 128, base);
    CvNoise(&c, 8, 4, noiseAmt, seed);
    if (anisoX > 0) CvNoiseAniso(&c, anisoX, anisoY, 3, noiseAmt*0.8f, seed + 1);
    return c;
}
static Cv TexPolymer(void)
{
    Cv c = CvNew(64, 64, (Color){ 32, 32, 34, 255 });
    for (int y = 0; y < 64; y++) for (int x = 0; x < 64; x++) if (((x/2) + (y/2)) % 2 == 0) CvMulPx(&c, x, y, 1.5f);
    CvNoise(&c, 4, 2, 10, 211);
    return c;
}
static Cv TexGunWood(void)
{
    Cv c = CvNew(128, 128, (Color){ 120, 58, 28, 255 });
    CvWoodGrain(&c, 0, 0, 128, 128, (Color){ 125, 60, 30, 255 }, 221, false);
    return c;
}
static Cv TexLightPanel(void)
{
    Cv c = CvNew(64, 64, (Color){ 255, 252, 240, 255 });
    for (int i = 0; i < 64; i += 8) for (int j = 0; j < 64; j++) { CvMulPx(&c, i, j, 0.93f); CvMulPx(&c, j, i, 0.93f); }
    CvBevel(&c, 0, 0, 64, 64, 4, 0.75f, 0.6f);
    return c;
}
static Cv TexSky(void)
{
    Cv c = CvNew(512, 256, BLACK);
    for (int y = 0; y < 256; y++) for (int x = 0; x < 512; x++) {
        float t = y / 170.0f; if (t > 1) t = 1;
        Color top = { 58, 92, 150, 255 }, hor = { 196, 206, 218, 255 };
        Color col = { ClampB(top.r + (hor.r - top.r)*t), ClampB(top.g + (hor.g - top.g)*t), ClampB(top.b + (hor.b - top.b)*t), 255 };
        float cl = Fbm(x/512.0f, y/256.0f, 6, 3, 5, 231);
        cl = Clamp((cl - 0.5f)*3.0f, 0, 1) * (1.0f - t*0.6f);
        col.r = ClampB(col.r + (240 - col.r)*cl); col.g = ClampB(col.g + (242 - col.g)*cl); col.b = ClampB(col.b + (246 - col.b)*cl);
        *CvAt(&c, x, y) = col;
    }
    for (int x = 0; x < 512; x++) {
        float u = x / 512.0f * 6.2831f;
        float m = 150 + 18*sinf(u*3 + 1) + 11*sinf(u*7 + 2) + 6*sinf(u*17) + 3*sinf(u*41);
        float m2 = 168 + 8*sinf(u*5 + 4) + 5*sinf(u*13 + 1);
        for (int y = (int)m; y < 256; y++) {
            float snow = Clamp(1.0f - (y - m)/14.0f, 0, 1);
            Color mc = { ClampB(92 + 130*snow), ClampB(102 + 125*snow), ClampB(122 + 118*snow), 255 };
            CvBlend(&c, x, y, mc, 1.0f);
        }
        for (int y = (int)m2; y < 256; y++) CvBlend(&c, x, y, (Color){ 150, 160, 175, 255 }, 0.9f);
        for (int y = 186; y < 256; y++) CvBlend(&c, x, y, (Color){ 220, 226, 234, 255 }, 1.0f);
    }
    CvNoise(&c, 32, 3, 10, 232);
    return c;
}
static Cv TexSnow(void)
{
    Cv c = CvNew(256, 256, (Color){ 222, 228, 238, 255 });
    CvNoise(&c, 4, 5, 26, 241); CvSpeckle(&c, 0.05f, 20, 242);
    return c;
}
static Cv TexRadial(int size, float power, Color col)
{
    Cv c = CvNew(size, size, (Color){ col.r, col.g, col.b, 0 });
    for (int y = 0; y < size; y++) for (int x = 0; x < size; x++) {
        float dx = (x + 0.5f)/size*2 - 1, dy = (y + 0.5f)/size*2 - 1;
        float r = sqrtf(dx*dx + dy*dy);
        float a = powf(Clamp(1 - r, 0, 1), power);
        CvAt(&c, x, y)->a = ClampB(a*255);
    }
    return c;
}
static Cv TexFlash(void)
{
    Cv c = CvNew(128, 128, (Color){ 255, 200, 90, 0 });
    for (int y = 0; y < 128; y++) for (int x = 0; x < 128; x++) {
        float dx = (x + 0.5f)/64 - 1, dy = (y + 0.5f)/64 - 1;
        float r = sqrtf(dx*dx + dy*dy), th = atan2f(dy, dx);
        float star = powf(fabsf(cosf(th*3.0f)), 10.0f)*0.9f + 0.25f;
        float a = Clamp(1 - r/star, 0, 1);
        a = a*a;
        float core = Clamp(1 - r*3, 0, 1);
        Color *p = CvAt(&c, x, y);
        p->r = 255; p->g = ClampB(170 + 85*core); p->b = ClampB(60 + 180*core);
        p->a = ClampB(a*255);
    }
    return c;
}
static Cv TexHole(void)
{
    Cv c = CvNew(32, 32, (Color){ 20, 18, 16, 0 });
    for (int y = 0; y < 32; y++) for (int x = 0; x < 32; x++) {
        float dx = x + 0.5f - 16, dy = y + 0.5f - 16, r = sqrtf(dx*dx + dy*dy);
        float ang = atan2f(dy, dx);
        float ring = 7 + 3*sinf(ang*5 + 1);
        Color *p = CvAt(&c, x, y);
        if (r < 3.5f) { p->r = 5; p->g = 5; p->b = 5; p->a = 255; }
        else if (r < ring) { p->r = 60; p->g = 56; p->b = 50; p->a = ClampB(200*(1 - (r - 3.5f)/(ring - 3.5f)) + 40); }
    }
    return c;
}
static Cv TexVignette(void)
{
    Cv c = CvNew(256, 256, (Color){ 255, 255, 255, 0 });
    for (int y = 0; y < 256; y++) for (int x = 0; x < 256; x++) {
        float dx = (x + 0.5f)/128 - 1, dy = (y + 0.5f)/128 - 1, r = sqrtf(dx*dx + dy*dy)/1.414f;
        float a = Clamp((r - 0.35f)/0.6f, 0, 1);
        CvAt(&c, x, y)->a = ClampB(a*a*255);
    }
    return c;
}
static Cv TexAmmoBox(void)
{
    Cv c = CvNew(128, 128, (Color){ 84, 94, 52, 255 });
    CvNoise(&c, 8, 4, 22, 251);
    CvBevel(&c, 0, 0, 128, 128, 6, 1.3f, 0.55f);
    CvText(&c, "7.65", 26, 40, 30, (Color){ 230, 200, 60, 255 });
    CvText(&c, "AMMO", 30, 76, 20, (Color){ 230, 200, 60, 255 });
    return c;
}
static Cv TexDisk(void)
{
    Cv c = CvNew(64, 64, (Color){ 30, 60, 150, 255 });
    CvNoise(&c, 4, 2, 14, 261);
    CvRect(&c, 16, 0, 32, 22, (Color){ 180, 185, 190, 255 }, 1.0f);
    CvRect(&c, 34, 4, 8, 14, (Color){ 40, 40, 45, 255 }, 1.0f);
    CvRect(&c, 8, 30, 48, 30, (Color){ 235, 235, 225, 255 }, 1.0f);
    CvText(&c, "GE-01", 12, 36, 10, (Color){ 180, 20, 20, 255 });
    for (int k = 0; k < 2; k++) CvRect(&c, 12, 50 + k*4, 40, 1, (Color){ 60, 60, 60, 255 }, 1.0f);
    return c;
}
static Cv TexVest(void)
{
    Cv c = CvNew(128, 128, (Color){ 70, 82, 52, 255 });
    CvNoise(&c, 16, 3, 22, 271);
    for (int k = 0; k < 3; k++) { CvRect(&c, 10 + k*38, 70, 32, 40, (Color){ 60, 70, 44, 255 }, 1.0f); CvBevel(&c, 10 + k*38, 70, 32, 40, 2, 1.3f, 0.6f); }
    CvRect(&c, 0, 20, 128, 10, (Color){ 30, 30, 30, 255 }, 1.0f);
    return c;
}

/* ---------------- character atlases (64px cells, 4x4) ---------------- */
typedef struct {
    Color uniform, pants, vest, hat, skin, hair, boots;
    int hatType;      /* 0 none, 1 helmet, 2 peaked cap, 3 beanie */
    bool hasVest, balaclava, moustache, gloves, suit;
} CharStyle;

enum { AT_FACE, AT_HEADSIDE, AT_HEADBACK, AT_HEADTOP, AT_TORSOF, AT_TORSOB, AT_TORSOS, AT_BELT,
       AT_SLEEVE, AT_PANTS, AT_BOOT, AT_HAND, AT_HATSIDE, AT_HATTOP, AT_GUN, AT_WOOD };

static void CellRect(int cell, int *x, int *y) { *x = (cell % 4)*64; *y = (cell / 4)*64; }

static void FabricCell(Cv *c, int cell, Color col, int seed)
{
    int x, y; CellRect(cell, &x, &y);
    CvRect(c, x, y, 64, 64, col, 1.0f);
    for (int j = 0; j < 64; j++) for (int i = 0; i < 64; i++) {
        float n = Fbm(i/64.0f, j/64.0f, 4, 4, 3, seed) - 0.5f;
        float weave = ((i + j) % 3 == 0) ? 4.0f : 0.0f;
        CvAddPx(c, x + i, y + j, n*26 + weave);
    }
}

static Cv TexCharacter(const CharStyle *s, int seed)
{
    Cv c = CvNew(256, 256, s->uniform);
    int x, y;
    Color skin = s->skin, hair = s->hair;
    Color mask = { 22, 22, 24, 255 };
    /* face */
    CellRect(AT_FACE, &x, &y);
    CvRect(&c, x, y, 64, 64, s->balaclava ? mask : skin, 1.0f);
    if (s->balaclava) {
        CvRect(&c, x + 8, y + 22, 48, 14, skin, 1.0f);
    } else {
        CvRect(&c, x, y, 64, 12, hair, 1.0f);
        for (int i = 0; i < 64; i++) for (int j = 12; j < 16; j++) if (H01(i, j, seed) < 0.5f) CvBlend(&c, x + i, y + j, hair, 0.8f);
        for (int j = 0; j < 64; j++) { for (int i = 0; i < 6; i++) { CvMulPx(&c, x + i, y + j, 0.82f + i*0.03f); CvMulPx(&c, x + 63 - i, y + j, 0.82f + i*0.03f); } }
    }
    CvRect(&c, x + 14, y + 22, 14, 3, s->balaclava ? skin : (Color){ hair.r/2, hair.g/2, hair.b/2, 255 }, s->balaclava ? 0.0f : 1.0f);
    CvRect(&c, x + 36, y + 22, 14, 3, (Color){ hair.r/2, hair.g/2, hair.b/2, 255 }, s->balaclava ? 0.0f : 1.0f);
    CvRect(&c, x + 15, y + 27, 12, 5, (Color){ 240, 240, 235, 255 }, 1.0f);
    CvRect(&c, x + 37, y + 27, 12, 5, (Color){ 240, 240, 235, 255 }, 1.0f);
    CvRect(&c, x + 19, y + 27, 5, 5, (Color){ 50, 60, 70, 255 }, 1.0f);
    CvRect(&c, x + 41, y + 27, 5, 5, (Color){ 50, 60, 70, 255 }, 1.0f);
    CvRect(&c, x + 15, y + 32, 12, 2, (Color){ 0, 0, 0, 255 }, 0.15f);
    CvRect(&c, x + 37, y + 32, 12, 2, (Color){ 0, 0, 0, 255 }, 0.15f);
    if (!s->balaclava) {
        CvRect(&c, x + 29, y + 30, 6, 14, (Color){ 0, 0, 0, 255 }, 0.08f);
        CvRect(&c, x + 27, y + 42, 10, 3, (Color){ 0, 0, 0, 255 }, 0.2f);
        CvRect(&c, x + 31, y + 30, 2, 11, (Color){ 255, 255, 255, 255 }, 0.12f);
        if (s->moustache) CvRect(&c, x + 22, y + 45, 20, 4, hair, 1.0f);
        CvRect(&c, x + 24, y + 50, 16, 3, (Color){ 140, 70, 60, 255 }, 1.0f);
        CvRect(&c, x + 20, y + 58, 24, 6, (Color){ 0, 0, 0, 255 }, 0.12f);
    }
    CvNoise(&c, 8, 2, 8, seed + 1);
    /* head side, back, top */
    CellRect(AT_HEADSIDE, &x, &y);
    CvRect(&c, x, y, 64, 64, s->balaclava ? mask : skin, 1.0f);
    if (!s->balaclava) {
        CvRect(&c, x, y, 64, 16, hair, 1.0f); CvRect(&c, x + 40, y, 24, 40, hair, 1.0f);
        CvCircle(&c, x + 30, y + 34, 7, (Color){ skin.r*3/4, skin.g*3/4, skin.b*3/4, 255 }, 0.9f, false);
        CvCircle(&c, x + 30, y + 34, 3, (Color){ skin.r/2, skin.g/2, skin.b/2, 255 }, 0.7f, false);
    }
    CellRect(AT_HEADBACK, &x, &y);
    CvRect(&c, x, y, 64, 64, s->balaclava ? mask : hair, 1.0f);
    if (!s->balaclava) CvRect(&c, x, y + 50, 64, 14, skin, 1.0f);
    CellRect(AT_HEADTOP, &x, &y);
    CvRect(&c, x, y, 64, 64, s->balaclava ? mask : hair, 1.0f);
    for (int cell = AT_HEADSIDE; cell <= AT_HEADTOP; cell++) {
        CellRect(cell, &x, &y);
        for (int j = 0; j < 64; j++) for (int i = 0; i < 64; i++) CvAddPx(&c, x + i, y + j, (Fbm(i/64.0f, j/64.0f, 8, 8, 2, seed + cell) - 0.5f)*20);
    }
    /* torso */
    FabricCell(&c, AT_TORSOF, s->uniform, seed + 10);
    FabricCell(&c, AT_TORSOB, s->uniform, seed + 11);
    FabricCell(&c, AT_TORSOS, s->uniform, seed + 12);
    CellRect(AT_TORSOF, &x, &y);
    if (s->suit) {
        for (int j = 0; j < 64; j++) {
            int half = 4 + j/3; if (half > 16) half = 16;
            if (j < 44) CvRect(&c, x + 32 - half, y + j, half*2, 1, (Color){ 235, 235, 230, 255 }, 1.0f);
        }
        CvRect(&c, x + 29, y + 4, 6, 40, (Color){ 120, 20, 30, 255 }, 1.0f);
        CvRect(&c, x + 27, y + 2, 10, 5, (Color){ 100, 15, 25, 255 }, 1.0f);
        CvSeg(&c, x + 16, y, x + 28, y + 44, 2, (Color){ 0, 0, 0, 255 }, 0.4f);
        CvSeg(&c, x + 48, y, x + 36, y + 44, 2, (Color){ 0, 0, 0, 255 }, 0.4f);
        CvCircle(&c, x + 32, y + 50, 1.6f, (Color){ 10, 10, 10, 255 }, 1.0f, false);
    } else {
        CvRect(&c, x + 20, y, 24, 6, (Color){ s->uniform.r*3/4, s->uniform.g*3/4, s->uniform.b*3/4, 255 }, 1.0f);
        if (s->hasVest) {
            CvRect(&c, x + 4, y + 8, 56, 50, s->vest, 1.0f);
            CvBevel(&c, x + 4, y + 8, 56, 50, 2, 1.2f, 0.6f);
            for (int k = 0; k < 3; k++) { CvRect(&c, x + 7 + k*17, y + 34, 15, 20, (Color){ s->vest.r*4/5, s->vest.g*4/5, s->vest.b*4/5, 255 }, 1.0f); CvBevel(&c, x + 7 + k*17, y + 34, 15, 20, 2, 1.25f, 0.55f); }
            CvRect(&c, x + 30, y + 8, 4, 26, (Color){ 0, 0, 0, 255 }, 0.3f);
        } else {
            CvRect(&c, x + 31, y + 6, 2, 58, (Color){ 0, 0, 0, 255 }, 0.35f);
            for (int k = 0; k < 5; k++) CvCircle(&c, x + 35, y + 12 + k*11, 1.5f, (Color){ 200, 190, 120, 255 }, 1.0f, false);
            CvRect(&c, x + 8, y + 14, 14, 10, (Color){ 0, 0, 0, 255 }, 0.2f); CvRect(&c, x + 42, y + 14, 14, 10, (Color){ 0, 0, 0, 255 }, 0.2f);
            CvRect(&c, x + 44, y + 16, 10, 4, (Color){ 220, 190, 80, 255 }, 0.9f);
        }
        CellRect(AT_TORSOB, &x, &y);
        if (s->hasVest) { CvRect(&c, x + 4, y + 8, 56, 50, s->vest, 1.0f); CvBevel(&c, x + 4, y + 8, 56, 50, 2, 1.2f, 0.6f); }
    }
    for (int cell = AT_TORSOF; cell <= AT_TORSOS; cell++) { CellRect(cell, &x, &y); for (int j = 0; j < 64; j++) for (int i = 0; i < 64; i++) CvMulPx(&c, x + i, y + j, 1.08f - j*0.003f); }
    /* belt */
    FabricCell(&c, AT_BELT, s->pants, seed + 13);
    CellRect(AT_BELT, &x, &y);
    CvRect(&c, x, y, 64, 18, (Color){ 28, 24, 20, 255 }, 1.0f);
    CvRect(&c, x + 26, y + 3, 12, 12, (Color){ 180, 170, 120, 255 }, 1.0f);
    CvRect(&c, x + 29, y + 6, 6, 6, (Color){ 28, 24, 20, 255 }, 1.0f);
    /* limbs */
    FabricCell(&c, AT_SLEEVE, s->uniform, seed + 14);
    CellRect(AT_SLEEVE, &x, &y);
    if (s->suit) CvRect(&c, x, y + 56, 64, 8, (Color){ 235, 235, 230, 255 }, 1.0f);
    else { CvRect(&c, x, y + 54, 64, 10, (Color){ s->uniform.r*3/4, s->uniform.g*3/4, s->uniform.b*3/4, 255 }, 1.0f); CvRect(&c, x + 10, y + 14, 18, 14, (Color){ 0, 0, 0, 255 }, 0.15f); }
    FabricCell(&c, AT_PANTS, s->pants, seed + 15);
    CellRect(AT_PANTS, &x, &y);
    if (s->hasVest) { CvRect(&c, x + 14, y + 38, 36, 20, (Color){ 30, 30, 30, 255 }, 1.0f); CvBevel(&c, x + 14, y + 38, 36, 20, 2, 1.4f, 0.6f); }
    CvRect(&c, x, y, 64, 64, (Color){ 0, 0, 0, 255 }, 0.0f);
    CellRect(AT_BOOT, &x, &y);
    CvRect(&c, x, y, 64, 64, s->boots, 1.0f);
    CvNoise(&c, 8, 2, 0, 0);
    for (int j = 0; j < 64; j++) for (int i = 0; i < 64; i++) CvAddPx(&c, x + i, y + j, (H01(i, j, seed + 16) - 0.5f)*10 + (j < 20 ? 18 - j : 0));
    CvRect(&c, x, y + 52, 64, 12, (Color){ 15, 15, 15, 255 }, 1.0f);
    for (int k = 0; k < 4; k++) CvRect(&c, x + 22, y + 8 + k*10, 20, 2, (Color){ 90, 90, 90, 255 }, 0.8f);
    CellRect(AT_HAND, &x, &y);
    CvRect(&c, x, y, 64, 64, s->gloves ? (Color){ 25, 25, 25, 255 } : skin, 1.0f);
    for (int k = 1; k < 4; k++) CvRect(&c, x + k*16, y + 30, 1, 34, (Color){ 0, 0, 0, 255 }, 0.25f);
    /* hat */
    CellRect(AT_HATSIDE, &x, &y);
    CvRect(&c, x, y, 64, 64, s->hat, 1.0f);
    if (s->hatType == 2) { CvRect(&c, x, y + 44, 64, 10, (Color){ 20, 20, 20, 255 }, 1.0f); CvRect(&c, x + 26, y + 20, 12, 12, (Color){ 220, 190, 80, 255 }, 1.0f); }
    if (s->hatType == 1) { for (int k = 0; k < 10; k++) CvCircle(&c, x + H01(k, 0, seed + 17)*64, y + H01(k, 1, seed + 17)*64, 6, (Color){ s->hat.r*3/4, s->hat.g*3/4, s->hat.b*3/4, 255 }, 0.5f, true); CvRect(&c, x, y + 56, 64, 8, (Color){ 0, 0, 0, 255 }, 0.3f); }
    CellRect(AT_HATTOP, &x, &y);
    CvRect(&c, x, y, 64, 64, s->hat, 1.0f);
    CvCircle(&c, x + 32, y + 32, 30, WHITE, 0.15f, true);
    for (int cell = AT_HATSIDE; cell <= AT_HATTOP; cell++) { CellRect(cell, &x, &y); for (int j = 0; j < 64; j++) for (int i = 0; i < 64; i++) CvAddPx(&c, x + i, y + j, (Fbm(i/64.0f, j/64.0f, 4, 4, 3, seed + 18 + cell) - 0.5f)*24); }
    /* gun metal + wood */
    CellRect(AT_GUN, &x, &y);
    CvRect(&c, x, y, 64, 64, (Color){ 40, 42, 46, 255 }, 1.0f);
    for (int j = 0; j < 64; j++) for (int i = 0; i < 64; i++) CvAddPx(&c, x + i, y + j, (Fbm(i/64.0f, j/64.0f, 1, 16, 2, seed + 30) - 0.5f)*20);
    CellRect(AT_WOOD, &x, &y);
    CvWoodGrain(&c, x, y, 64, 64, (Color){ 120, 62, 30, 255 }, seed + 31, false);
    return c;
}

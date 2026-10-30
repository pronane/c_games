/* textures.c : every texture in the game is painted here, in code, at start-up
 * (original art - no external image files). Tileable noise, asphalt, curbs,
 * barriers with painted logos, wood / stone / bark / leaves / roof tiles, a crowd,
 * billboard signs, water, rainbow tiles, item boxes, clouds, per-track ground
 * textures and per-track painted panoramas (mountains, sea, castles, stars). */
#include "common.h"
#include "rlgl.h"

/* ---------------------------------------------------------------- */
/* noise                                                              */
/* ---------------------------------------------------------------- */
static unsigned int Hash(int x, int y, unsigned int seed)
{
    unsigned int h = (unsigned int)x*374761393u + (unsigned int)y*668265263u + seed*2246822519u;
    h = (h ^ (h >> 13))*1274126177u;
    return h ^ (h >> 16);
}
static float HashF(int x, int y, unsigned int seed) { return (Hash(x, y, seed) & 0xFFFFFF)/16777216.0f; }

/* value noise, periodic with period p (in lattice cells) so textures tile */
static float PNoise(float x, float y, int p, unsigned int seed)
{
    int xi = (int)floorf(x), yi = (int)floorf(y);
    float fx = x - xi, fy = y - yi;
    fx = fx*fx*(3 - 2*fx); fy = fy*fy*(3 - 2*fy);
    int x0 = ((xi % p) + p) % p, y0 = ((yi % p) + p) % p, x1 = (x0 + 1) % p, y1 = (y0 + 1) % p;
    float a = HashF(x0, y0, seed), b = HashF(x1, y0, seed), c = HashF(x0, y1, seed), d = HashF(x1, y1, seed);
    return (a*(1 - fx) + b*fx)*(1 - fy) + (c*(1 - fx) + d*fx)*fy;
}
/* fractal noise over a w-pixel tile: u,v in [0,1) */
static float TFbm(float u, float v, int base, int oct, unsigned int seed)
{
    float s = 0, a = 0.5f, n = 0;
    int p = base;
    for (int o = 0; o < oct; o++) {
        s += a*PNoise(u*p, v*p, p, seed + o*101u);
        n += a; a *= 0.5f; p *= 2;
    }
    return s/n;
}
/* non-periodic world noise for terrain */
float WorldNoise(float x, float z, unsigned int seed)
{
    float s = 0, a = 0.5f, n = 0, f = 1;
    for (int o = 0; o < 4; o++) {
        s += a*PNoise(x*f, z*f, 1 << 20, seed + o*77u);
        n += a; a *= 0.5f; f *= 2.03f;
    }
    return s/n;
}

static unsigned int trs = 1;
static float TRand(void) { trs = trs*1664525u + 1013904223u; return (trs >> 8)/16777216.0f; }
static int TRandI(int n) { return (int)(TRand()*n) % (n > 0 ? n : 1); }

static inline unsigned char C8(float v) { return (unsigned char)(v < 0 ? 0 : v > 255 ? 255 : v); }
static inline Color Shade(Color c, float s) { return (Color){ C8(c.r*s), C8(c.g*s), C8(c.b*s), c.a }; }
static inline Color Mix(Color a, Color b, float t) { return (Color){ C8(a.r + (b.r - a.r)*t), C8(a.g + (b.g - a.g)*t), C8(a.b + (b.b - a.b)*t), C8(a.a + (b.a - a.a)*t) }; }

static void PutW(Image *im, int x, int y, Color c)
{
    x = ((x % im->width) + im->width) % im->width;
    y = ((y % im->height) + im->height) % im->height;
    ((Color *)im->data)[y*im->width + x] = c;
}
static Color GetW(Image *im, int x, int y)
{
    x = ((x % im->width) + im->width) % im->width;
    y = ((y % im->height) + im->height) % im->height;
    return ((Color *)im->data)[y*im->width + x];
}
static void BlendW(Image *im, int x, int y, Color c, float a)
{
    PutW(im, x, y, Mix(GetW(im, x, y), c, a));
}
/* soft disc, wrapping */
static void Blob(Image *im, float cx, float cy, float r, Color c, float hard)
{
    for (int y = (int)(cy - r - 1); y <= (int)(cy + r + 1); y++)
        for (int x = (int)(cx - r - 1); x <= (int)(cx + r + 1); x++) {
            float d = sqrtf((x - cx)*(x - cx) + (y - cy)*(y - cy))/r;
            if (d >= 1) continue;
            float a = Clamp((1 - d)*hard, 0, 1);
            BlendW(im, x, y, c, a*(c.a/255.0f));
        }
}

static Texture2D Upload(Image img, bool mip, bool repeat)
{
    Texture2D t = LoadTextureFromImage(img);
    if (mip) { GenTextureMipmaps(&t); SetTextureFilter(t, TEXTURE_FILTER_TRILINEAR); }
    else SetTextureFilter(t, TEXTURE_FILTER_BILINEAR);
    SetTextureWrap(t, repeat ? TEXTURE_WRAP_REPEAT : TEXTURE_WRAP_CLAMP);
    UnloadImage(img);
    return t;
}

/* text with a dark outline, centred in a rectangle */
static void SignText(Image *im, const char *txt, int x, int y, int w, int h, int size, Color fg, Color outline)
{
    Font f = GetFontDefault();
    float sp = size/10.0f;
    Vector2 m = MeasureTextEx(f, txt, (float)size, sp);
    while (m.x > w - 8 && size > 10) { size -= 2; sp = size/10.0f; m = MeasureTextEx(f, txt, (float)size, sp); }
    int tx = x + (int)((w - m.x)/2), ty = y + (int)((h - m.y)/2);
    int o = size >= 24 ? 3 : 2;
    for (int dy = -o; dy <= o; dy++) for (int dx = -o; dx <= o; dx++)
        if (dx*dx + dy*dy <= o*o + 1) ImageDrawTextEx(im, f, txt, (Vector2){ (float)(tx + dx), (float)(ty + dy) }, (float)size, sp, outline);
    ImageDrawTextEx(im, f, txt, (Vector2){ (float)tx, (float)ty }, (float)size, sp, fg);
}

/* ---------------------------------------------------------------- */
/* materials                                                          */
/* ---------------------------------------------------------------- */
static Image GenGrain(void)
{
    int W = 128;
    Image im = GenImageColor(W, W, WHITE);
    for (int y = 0; y < W; y++) for (int x = 0; x < W; x++) {
        float n = TFbm((float)x/W, (float)y/W, 4, 4, 11);
        float v = 226 + 34*n + (HashF(x, y, 5) - 0.5f)*10;
        PutW(&im, x, y, (Color){ C8(v), C8(v), C8(v), 255 });
    }
    return im;
}

static Image GenRoad(void)
{
    int W = 256;
    Image im = GenImageColor(W, W, WHITE);
    for (int y = 0; y < W; y++) for (int x = 0; x < W; x++) {
        float u = (float)x/W, v = (float)y/W;
        float n = TFbm(u, v, 8, 4, 21);
        float val = 196 + 40*(n - 0.5f) + (HashF(x, y, 9) - 0.5f)*26;
        float sp = HashF(x, y, 77);
        if (sp > 0.985f) val += 38; else if (sp < 0.012f) val -= 46;      /* aggregate */
        /* worn racing lines (slightly darker, smoother) */
        float tl = expf(-powf((u - 0.32f)/0.05f, 2)) + expf(-powf((u - 0.68f)/0.05f, 2));
        val -= 14*tl;
        /* solid edge lines + dashed centre line */
        bool line = (u > 0.03f && u < 0.05f) || (u > 0.95f && u < 0.97f) || (u > 0.492f && u < 0.508f && v < 0.5f);
        if (line) val = 248 + (HashF(x, y, 3) - 0.5f)*10;
        PutW(&im, x, y, (Color){ C8(val), C8(val), C8(val*1.01f), 255 });
    }
    return im;
}

static Image GenCurb(void)
{
    int W = 64;
    Image im = GenImageColor(W, W, WHITE);
    for (int y = 0; y < W; y++) for (int x = 0; x < W; x++) {
        float u = (float)x/W;
        float prof = 0.78f + 0.25f*sinf(u*PI);            /* rounded, bright crown */
        if (u < 0.06f || u > 0.94f) prof *= 0.62f;           /* dark seams */
        float v = 255*prof + (HashF(x, y, 31) - 0.5f)*14 + (TFbm(u, (float)y/W, 4, 3, 7) - 0.5f)*16;
        PutW(&im, x, y, (Color){ C8(v), C8(v), C8(v), 255 });
    }
    return im;
}

/* 512x128: two rows of 4 panels (row 0 arrows point +u, row 1 arrows point -u) */
static Image GenBarrier(void)
{
    int W = 512, H = 128;
    Image im = GenImageColor(W, H, WHITE);
    for (int row = 0; row < 2; row++) {
        int y0 = row*64;
        for (int p = 0; p < 4; p++) {
            int x0 = p*128;
            for (int y = 0; y < 64; y++) for (int x = 0; x < 128; x++) {
                float v = 236 + (TFbm((float)x/128, (float)y/64, 4, 3, 41 + p) - 0.5f)*22;
                /* top & bottom trims, panel seams */
                if (y < 5 || y > 58) v *= 0.72f;
                if (x < 2 || x > 125) v *= 0.55f;
                PutW(&im, x0 + x, y0 + y, (Color){ C8(v), C8(v), C8(v), 255 });
            }
            Color dark = { 40, 40, 52, 255 }, mid = { 120, 120, 135, 255 };
            if (p == 0) {         /* bolts + ribbed stripes */
                for (int y = 18; y < 48; y += 10) for (int x = 6; x < 122; x++) BlendW(&im, x0 + x, y0 + y, mid, 0.55f);
                for (int k = 0; k < 2; k++) { Blob(&im, x0 + 10.0f + k*108, y0 + 12.0f, 2.6f, dark, 3); Blob(&im, x0 + 10.0f + k*108, y0 + 52.0f, 2.6f, dark, 3); }
            } else if (p == 1) {  /* logo plate */
                ImageDrawRectangle(&im, x0 + 10, y0 + 12, 108, 40, dark);
                ImageDrawRectangleLines(&im, (Rectangle){ (float)x0 + 10, (float)y0 + 12, 108, 40 }, 2, WHITE);
                SignText(&im, "TT64", x0 + 10, y0 + 12, 108, 40, 30, WHITE, dark);
            } else if (p == 2) {  /* chevron arrows */
                for (int k = 0; k < 3; k++) {
                    int cx = x0 + 30 + k*34;
                    for (int y = 12; y < 52; y++) {
                        int dy = abs(y - 32);
                        int off = row == 0 ? -dy*6/10 : dy*6/10;
                        for (int t = 0; t < 10; t++) PutW(&im, cx + off + (row == 0 ? t : -t), y0 + y, dark);
                    }
                }
            } else {              /* diagonal hazard stripes */
                for (int y = 8; y < 56; y++) for (int x = 4; x < 124; x++)
                    if ((((x + y) / 12) & 1) == 0) BlendW(&im, x0 + x, y0 + y, dark, 0.85f);
            }
        }
    }
    return im;
}

static Image GenWood(void)
{
    int W = 128;
    Image im = GenImageColor(W, W, WHITE);
    Color base = { 196, 142, 92, 255 };
    for (int y = 0; y < W; y++) {
        int plank = y/32;
        float tone = 0.86f + 0.22f*HashF(plank, 0, 61);
        for (int x = 0; x < W; x++) {
            float u = (float)x/W, v = (float)y/W;
            float g = sinf((v*W*0.9f + TFbm(u, v, 4, 3, 63 + plank)*14.0f)*1.3f);
            float s = tone*(0.92f + 0.08f*g + (TFbm(u, v, 16, 2, 65) - 0.5f)*0.12f);
            Color c = Shade(base, s);
            if (y % 32 < 2) c = Shade(base, 0.45f);
            PutW(&im, x, y, c);
        }
        /* nails */
        if (y % 32 == 16) for (int k = 0; k < 2; k++) Blob(&im, 8.0f + k*112 + plank*7 % 20, (float)y, 1.6f, (Color){ 70, 60, 55, 255 }, 3);
    }
    return im;
}

static Image GenStone(void)
{
    int W = 128;
    Image im = GenImageColor(W, W, WHITE);
    for (int y = 0; y < W; y++) for (int x = 0; x < W; x++) {
        int row = y/32;
        int xo = (x + (row & 1)*32) % W;
        int bx = xo/64;
        float tone = 0.84f + 0.24f*HashF(bx, row, 71);
        float u = (float)x/W, v = (float)y/W;
        float n = TFbm(u, v, 8, 3, 73);
        float val = 220*tone*(0.9f + 0.2f*n);
        int lx = xo % 64, ly = y % 32;
        if (lx < 3 || ly < 3) val = 120 + 20*n;                          /* mortar */
        else if (lx < 6 || ly < 6) val *= 1.08f;                          /* bevel highlight */
        else if (lx > 60 || ly > 28) val *= 0.82f;
        PutW(&im, x, y, (Color){ C8(val), C8(val), C8(val*1.02f), 255 });
    }
    return im;
}

static Image GenRock(void)
{
    int W = 128;
    Image im = GenImageColor(W, W, WHITE);
    for (int y = 0; y < W; y++) for (int x = 0; x < W; x++) {
        float u = (float)x/W, v = (float)y/W;
        float n = TFbm(u, v, 4, 5, 81);
        float c = fabsf(TFbm(u, v, 8, 3, 83) - 0.5f);
        float val = 150 + 110*n - (c < 0.03f ? 50 : 0);
        PutW(&im, x, y, (Color){ C8(val), C8(val*0.98f), C8(val*0.95f), 255 });
    }
    return im;
}

static Image GenBark(void)
{
    int W = 64, H = 128;
    Image im = GenImageColor(W, H, WHITE);
    Color base = { 130, 92, 60, 255 };
    for (int y = 0; y < H; y++) for (int x = 0; x < W; x++) {
        float u = (float)x/W, v = (float)y/H;
        float n = TFbm(u*1.0f, v*0.25f, 8, 3, 91);
        float ridge = fabsf(sinf((u*8 + n*1.5f)*PI));
        float s = 0.62f + 0.5f*ridge + (HashF(x, y, 93) - 0.5f)*0.1f;
        PutW(&im, x, y, Shade(base, s));
    }
    return im;
}

static Image GenLeaves(void)
{
    int W = 128;
    Image im = GenImageColor(W, W, (Color){ 120, 120, 120, 255 });
    trs = 101;
    for (int y = 0; y < W; y++) for (int x = 0; x < W; x++) {
        float n = TFbm((float)x/W, (float)y/W, 4, 3, 103);
        float v = 105 + 50*n;
        PutW(&im, x, y, (Color){ C8(v), C8(v), C8(v), 255 });
    }
    for (int i = 0; i < 520; i++) {
        float cx = TRand()*W, cy = TRand()*W, r = 2.5f + TRand()*4.5f;
        float l = 0.55f + TRand()*0.55f;
        Blob(&im, cx, cy, r, (Color){ C8(255*l*0.8f), C8(255*l*0.8f), C8(255*l*0.8f), 255 }, 2.5f);
        Blob(&im, cx - r*0.3f, cy - r*0.3f, r*0.45f, (Color){ C8(255*l), C8(255*l), C8(255*l), 255 }, 2.0f);   /* highlight */
    }
    return im;
}

static Image GenRoof(void)
{
    int W = 128;
    Image im = GenImageColor(W, W, WHITE);
    for (int y = 0; y < W; y++) for (int x = 0; x < W; x++) {
        int row = y/16;
        float xo = fmodf(x + (row & 1)*16.0f, 32.0f);
        float ly = (y % 16)/16.0f;
        float dx = (xo - 16)/16.0f;
        float scallop = ly + 0.35f*dx*dx;                   /* rounded tile ends */
        float v = 255*(0.62f + 0.38f*Clamp(1.0f - scallop, 0, 1));
        if (scallop > 1.0f) v = 105;
        v *= 0.92f + 0.12f*HashF((x + (row & 1)*16)/32, row, 111);
        PutW(&im, x, y, (Color){ C8(v), C8(v), C8(v), 255 });
    }
    return im;
}

static Image GenCrowd(void)
{
    int W = 256, H = 128;
    Image im = GenImageColor(W, H, (Color){ 46, 42, 60, 255 });
    trs = 121;
    Color skins[4] = { { 255, 214, 170, 255 }, { 225, 170, 120, 255 }, { 160, 105, 70, 255 }, { 250, 200, 150, 255 } };
    for (int row = 0; row < 6; row++) {
        float y = 14 + row*21.0f;
        for (int k = 0; k < 26; k++) {
            float x = k*(W/26.0f) + (row & 1)*5 + TRand()*3;
            Color shirt = HueColor(TRand()*360, 0.75f, 1.0f);
            Blob(&im, x, y + 9, 6.5f, Shade(shirt, 0.85f), 3);
            Blob(&im, x, y, 4.2f, skins[TRandI(4)], 3);
            if (TRand() < 0.3f) Blob(&im, x, y - 3, 4.0f, HueColor(TRand()*360, 0.8f, 0.9f), 3);   /* caps */
            if (TRand() < 0.15f) for (int a = 0; a < 8; a++) PutW(&im, (int)x + 5, (int)y - a, WHITE);  /* waving flag */
        }
    }
    return im;
}

/* 512x512: 2 columns x 8 rows of 256x64 boards */
static void DrawMascot(Image *im, float cx, float cy, float r, Color c, Color bg);
static void DrawTurtle(Image *im, float cx, float cy, float r)
{
    Blob(im, cx - r*1.05f, cy - r*0.15f, r*0.42f, (Color){ 120, 200, 90, 255 }, 3);                 /* head */
    Blob(im, cx - r*1.15f, cy - r*0.25f, r*0.09f, (Color){ 20, 20, 20, 255 }, 4);                  /* eye */
    for (int k = -1; k <= 1; k += 2) Blob(im, cx + k*r*0.55f, cy + r*0.55f, r*0.24f, (Color){ 120, 200, 90, 255 }, 3);
    Blob(im, cx, cy, r*0.78f, (Color){ 40, 140, 60, 255 }, 3);                                     /* shell */
    Blob(im, cx, cy - r*0.05f, r*0.58f, (Color){ 250, 210, 60, 255 }, 3);
    Blob(im, cx, cy - r*0.05f, r*0.30f, (Color){ 40, 140, 60, 255 }, 3);
}
static Image GenSigns(void)
{
    int W = 512, H = 1024;
    Image im = GenImageColor(W, H, WHITE);
    struct { const char *t; Color bg, fg, ol; int style; } s[32] = {
        { "TURBO TUMBLE 64", { 220, 30, 40, 255 }, { 255, 230, 40, 255 }, { 60, 0, 0, 255 }, 1 },
        { "MANGO COLA",     { 255, 140, 20, 255 }, { 255, 255, 255, 255 }, { 120, 40, 0, 255 }, 2 },
        { "ZOOM OIL",       { 30, 80, 200, 255 },  { 255, 220, 40, 255 }, { 0, 0, 60, 255 }, 1 },
        { "PIZZA PRONTO",   { 40, 160, 60, 255 },  { 255, 255, 255, 255 }, { 120, 0, 0, 255 }, 2 },
        { "BISCUIT BURGERS",{ 250, 210, 60, 255 }, { 200, 30, 30, 255 }, { 255, 255, 255, 255 }, 1 },
        { ">>>",            { 255, 210, 30, 255 }, { 20, 20, 20, 255 }, { 255, 210, 30, 255 }, 3 },
        { "<<<",            { 255, 210, 30, 255 }, { 20, 20, 20, 255 }, { 255, 210, 30, 255 }, 4 },
        { "",               { 255, 255, 255, 255 },{ 20, 20, 20, 255 }, { 0, 0, 0, 255 }, 5 },
        { "GO! GO! GO!",    { 120, 40, 200, 255 }, { 255, 255, 255, 255 }, { 40, 0, 80, 255 }, 6 },
        { "BOO!",           { 70, 30, 100, 255 },  { 180, 255, 120, 255 }, { 20, 0, 30, 255 }, 2 },
        { "SURF'S UP",      { 30, 190, 210, 255 }, { 255, 255, 255, 255 }, { 0, 70, 110, 255 }, 2 },
        { "HOT HOT HOT",    { 240, 90, 30, 255 },  { 255, 240, 120, 255 }, { 100, 20, 0, 255 }, 1 },
        { "SKI SCHOOL",     { 230, 240, 255, 255 },{ 30, 80, 200, 255 }, { 255, 255, 255, 255 }, 2 },
        { "STAR CUP",       { 20, 20, 60, 255 },   { 255, 230, 90, 255 }, { 120, 60, 0, 255 }, 6 },
        { "64",             { 230, 40, 60, 255 },  { 255, 255, 255, 255 }, { 0, 40, 160, 255 }, 1 },
        { "FUN FAIR",       { 255, 90, 170, 255 }, { 255, 255, 255, 255 }, { 120, 0, 60, 255 }, 2 },
        /* v7 */
        { "TUMBLE AIR",     { 245, 248, 255, 255 },{ 30, 70, 190, 255 }, { 30, 70, 190, 255 }, 1 },     /* 16 */
        { "SKYHOP AIRWAYS", { 30, 90, 200, 255 },  { 255, 255, 255, 255 }, { 250, 200, 40, 255 }, 1 },  /* 17 */
        { ">>>",            { 250, 250, 250, 255 },{ 220, 30, 30, 255 }, { 220, 30, 30, 255 }, 3 },     /* 18 */
        { "<<<",            { 250, 250, 250, 255 },{ 220, 30, 30, 255 }, { 220, 30, 30, 255 }, 4 },     /* 19 */
        { "SHELLBY",        { 40, 190, 220, 255 }, { 255, 255, 255, 255 }, { 0, 80, 120, 255 }, 7 },    /* 20 */
        { "MOO MILK",       { 255, 255, 255, 255 },{ 40, 110, 220, 255 }, { 20, 20, 20, 255 }, 9 },     /* 21 */
        { "CRAB SHACK",     { 230, 70, 50, 255 },  { 255, 240, 200, 255 }, { 100, 20, 10, 255 }, 2 },   /* 22 */
        { "MOLE CROSSING",  { 255, 210, 30, 255 }, { 20, 20, 20, 255 }, { 20, 20, 20, 255 }, 1 },       /* 23 */
        { "CLOVER CREEK",   { 60, 150, 60, 255 },  { 255, 250, 220, 255 }, { 30, 70, 30, 255 }, 2 },    /* 24 */
        { "TUMBLE TYRES",   { 30, 30, 36, 255 },   { 255, 210, 30, 255 }, { 220, 30, 30, 255 }, 1 },    /* 25 */
        { "RIVER TOURS",    { 30, 120, 90, 255 },  { 255, 230, 140, 255 }, { 10, 50, 30, 255 }, 2 },    /* 26 */
        { "TURBO TUMBLE 64",{ 30, 60, 170, 255 },  { 255, 255, 255, 255 }, { 250, 200, 40, 255 }, 8 },  /* 27 */
        { "FRESH EGGS",     { 250, 240, 220, 255 },{ 160, 70, 30, 255 }, { 120, 60, 20, 255 }, 2 },     /* 28 */
        { "COCONUT CO.",    { 120, 80, 40, 255 },  { 255, 250, 230, 255 }, { 40, 20, 0, 255 }, 2 },     /* 29 */
        { "PIT STOP",       { 220, 30, 40, 255 },  { 255, 255, 255, 255 }, { 40, 0, 0, 255 }, 1 },      /* 30 */
        { "FINISH",         { 252, 252, 252, 255 },{ 20, 20, 20, 255 }, { 200, 30, 30, 255 }, 1 },      /* 31 */
    };
    for (int i = 0; i < 32; i++) {
        int x0 = (i & 1)*256, y0 = (i >> 1)*64;
        for (int y = 0; y < 64; y++) for (int x = 0; x < 256; x++) {
            float g = 1.06f - 0.14f*y/64.0f + (HashF(x, y, 131 + i) - 0.5f)*0.05f;
            Color c = Shade(s[i].bg, g);
            if (s[i].style == 6) c = Shade(HueColor(x*1.4f + i*40, 0.55f, 1.0f), g*(s[i].bg.r < 50 ? 0.4f : 0.9f));
            if (s[i].style == 5) c = (((x/16) + (y/16)) & 1) ? (Color){ 20, 20, 20, 255 } : (Color){ 250, 250, 250, 255 };
            if (y < 4 || y > 59 || x < 4 || x > 251) c = s[i].style == 5 ? c : Shade(s[i].ol, 1.0f);
            PutW(&im, x0 + x, y0 + y, c);
        }
        if (s[i].style == 3 || s[i].style == 4) {
            for (int k = 0; k < 4; k++) {
                int cx = x0 + 44 + k*56;
                for (int y = 10; y < 54; y++) {
                    int dy = abs(y - 32);
                    int off = s[i].style == 3 ? -dy*8/10 : dy*8/10;
                    for (int t = 0; t < 14; t++) PutW(&im, cx + off + (s[i].style == 3 ? t : -t), y0 + y, s[i].fg);
                }
            }
        } else if (s[i].style == 7) {          /* our turtle mascot "Shellby" */
            DrawTurtle(&im, x0 + 46.0f, y0 + 32.0f, 22.0f);
            SignText(&im, s[i].t, x0 + 84, y0 + 6, 166, 54, 30, s[i].fg, s[i].ol);
        } else if (s[i].style == 8) {          /* the Tumble mascot + logo */
            DrawMascot(&im, x0 + 34.0f, y0 + 32.0f, 24.0f, (Color){ 255, 255, 255, 255 }, s[i].bg);
            SignText(&im, s[i].t, x0 + 64, y0 + 6, 186, 54, 24, s[i].fg, s[i].ol);
        } else if (s[i].style == 9) {          /* cow-spot milk board */
            for (int k = 0; k < 9; k++) Blob(&im, x0 + 14.0f + HashF(k, 1, 7)*228, y0 + 8.0f + HashF(k, 2, 7)*48, 5.0f + HashF(k, 3, 7)*6, (Color){ 25, 25, 25, 255 }, 2);
            SignText(&im, s[i].t, x0 + 6, y0 + 6, 244, 54, 34, s[i].fg, (Color){ 255, 255, 255, 255 });
        } else if (s[i].style != 5) {
            if (s[i].style == 2) for (int k = 0; k < 12; k++) Blob(&im, x0 + 12.0f + k*21, y0 + 9.0f, 3, Shade(s[i].fg, 1.0f), 3);
            SignText(&im, s[i].t, x0 + 6, y0 + 6, 244, 54, 34, s[i].fg, s[i].ol);
        }
    }
    return im;
}

static Image GenWater(void)
{
    int W = 256;
    Image im = GenImageColor(W, W, WHITE);
    for (int y = 0; y < W; y++) for (int x = 0; x < W; x++) {
        float u = (float)x/W, v = (float)y/W;
        float n1 = TFbm(u, v, 4, 3, 141), n2 = TFbm(u + 0.37f, v + 0.11f, 8, 2, 143);
        float w = sinf((v*6 + n1*2.2f)*2*PI)*0.5f + 0.5f;
        float caus = powf(1.0f - fabsf(n2 - 0.5f)*2.0f, 8.0f);
        Color deep = { 20, 120, 200, 255 }, shallow = { 60, 200, 230, 255 };
        Color c = Mix(deep, shallow, 0.35f + 0.4f*w*n1);
        c = Mix(c, WHITE, Clamp(caus*0.75f + (w > 0.96f ? 0.35f : 0), 0, 0.85f));
        c.a = 205;
        PutW(&im, x, y, c);
    }
    return im;
}

static Image GenRainbowTile(void)
{
    int W = 128;
    Image im = GenImageColor(W, W, WHITE);
    for (int y = 0; y < W; y++) for (int x = 0; x < W; x++) {
        int lx = x % 64, ly = y % 64;
        float v = 225 + 25*TFbm((float)x/W, (float)y/W, 4, 2, 151);
        if (lx < 4 || ly < 4) v = 255;
        else if (lx > 59 || ly > 59) v = 150;
        else { float dx = (lx - 32)/32.0f, dy = (ly - 32)/32.0f; v *= 0.92f + 0.1f*(1 - (dx*dx + dy*dy)); }
        PutW(&im, x, y, (Color){ C8(v), C8(v), C8(v), 255 });
    }
    /* little star sparkles */
    for (int k = 0; k < 4; k++) {
        int cx = 16 + (k & 1)*64 + (k*13) % 20, cy = 18 + (k >> 1)*64 + (k*7) % 20;
        for (int t = -4; t <= 4; t++) { PutW(&im, cx + t, cy, WHITE); PutW(&im, cx, cy + t, WHITE); }
    }
    return im;
}

static Image GenItemBox(void)
{
    int W = 64;
    Image im = GenImageColor(W, W, (Color){ 255, 255, 255, 70 });
    for (int y = 0; y < W; y++) for (int x = 0; x < W; x++) {
        int e = x < y ? x : y; int e2 = (W - 1 - x) < (W - 1 - y) ? (W - 1 - x) : (W - 1 - y); if (e2 < e) e = e2;
        float a = e < 3 ? 255 : e < 7 ? 200 - (e - 3)*25 : 70 + 40*(1.0f - y/(float)W);
        PutW(&im, x, y, (Color){ 255, 255, 255, C8(a) });
    }
    Font f = GetFontDefault();
    for (int dy = -3; dy <= 3; dy++) for (int dx = -3; dx <= 3; dx++)
        ImageDrawTextEx(&im, f, "?", (Vector2){ 21.0f + dx, 10.0f + dy }, 44, 4, (Color){ 30, 30, 90, 255 });
    ImageDrawTextEx(&im, f, "?", (Vector2){ 21, 10 }, 44, 4, WHITE);
    return im;
}

static Image GenCloud(void)
{
    int W = 256, H = 128;
    Image im = GenImageColor(W, H, (Color){ 255, 255, 255, 0 });
    float *a = (float *)calloc(W*H, sizeof(float));
    trs = 161;
    for (int i = 0; i < 26; i++) {
        float cx = 40 + TRand()*176, cy = 60 + TRand()*30 - (fabsf(cx - 128)/128.0f)*-10, r = 16 + TRand()*26*(1.0f - fabsf(cx - 128)/170.0f);
        for (int y = 0; y < H; y++) for (int x = 0; x < W; x++) {
            float d = sqrtf((x - cx)*(x - cx) + (y - cy)*(y - cy))/r;
            if (d < 1) a[y*W + x] = fmaxf(a[y*W + x], Clamp((1 - d)*3.0f, 0, 1));
        }
    }
    for (int y = 0; y < H; y++) for (int x = 0; x < W; x++) {
        float al = a[y*W + x];
        float sh = 1.0f - 0.25f*Clamp((y - 50)/60.0f, 0, 1);
        PutW(&im, x, y, (Color){ C8(255*sh), C8(255*sh), C8(255*(sh*0.97f + 0.03f)), C8(al*255) });
    }
    free(a);
    return im;
}

/* ---------------------------------------------------------------- */
/* ground textures (256, coloured per track)                          */
/* ---------------------------------------------------------------- */
static Image GenGround(const TrackDef *d, int idx)
{
    int W = 256;
    Image im = GenImageColor(W, W, d->ground);
    unsigned int sd = 200u + idx*17u;
    trs = sd;
    for (int y = 0; y < W; y++) for (int x = 0; x < W; x++) {
        float u = (float)x/W, v = (float)y/W;
        float n = TFbm(u, v, 4, 4, sd), n2 = TFbm(u, v, 16, 2, sd + 5);
        Color c = d->ground;
        switch (d->scenery) {
        case SCENERY_MEADOW: case SCENERY_SPOOKY: case SCENERY_RACEWAY: case SCENERY_JUNGLE: case SCENERY_FARM: {
            float s = 0.82f + 0.36f*n + (n2 - 0.5f)*0.14f;
            c = Shade(c, s);
            if (d->scenery == SCENERY_MEADOW) c = Mix(c, (Color){ 150, 200, 60, 255 }, Clamp((n - 0.62f)*2.0f, 0, 0.35f));
        } break;
        case SCENERY_DESERT: case SCENERY_BEACH: case SCENERY_ISLAND: {
            float rip = sinf((v*18 + n*3.0f + u*2)*2*PI);
            float s = 0.9f + 0.14f*n + rip*(d->scenery == SCENERY_DESERT ? 0.05f : 0.025f) + (HashF(x, y, sd) - 0.5f)*0.08f;
            c = Shade(c, s);
        } break;
        case SCENERY_SNOW: {
            float s = 0.92f + 0.1f*n;
            c = Mix(Shade(c, s), (Color){ 190, 210, 240, 255 }, Clamp((0.45f - n)*1.2f, 0, 0.4f));
            if (HashF(x, y, sd + 9) > 0.992f) c = WHITE;                               /* sparkle */
            else if (HashF(x, y, sd + 11) > 0.994f) c = (Color){ 200, 235, 255, 255 };
        } break;
        case SCENERY_STADIUM: {
            float ph = fmodf(v*6.0f + (n - 0.5f)*0.4f + 6.0f, 1.0f);
            float groove = expf(-powf((ph - 0.5f)/0.05f, 2));
            c = Shade(c, 0.86f + 0.24f*n + (n2 - 0.5f)*0.1f - 0.18f*groove);
            if (HashF(x, y, sd + 3) > 0.99f) c = Shade(c, 0.6f);
        } break;
        default: {
            c = Shade(c, 0.8f + 0.4f*n);
            if (HashF(x, y, sd + 3) > 0.993f) c = (Color){ 255, 220, 255, 255 };
        } break;
        }
        PutW(&im, x, y, c);
    }
    bool grassy = d->scenery == SCENERY_MEADOW || d->scenery == SCENERY_SPOOKY || d->scenery == SCENERY_RACEWAY || d->scenery == SCENERY_JUNGLE || d->scenery == SCENERY_FARM;
    if (grassy) {
        /* grass blades */
        for (int i = 0; i < 2600; i++) {
            int x = TRandI(W), y = TRandI(W), len = 3 + TRandI(5);
            float l = 0.7f + TRand()*0.6f;
            Color bc = Shade(d->ground, l);
            if (d->scenery != SCENERY_SPOOKY) bc = Mix(bc, (Color){ 170, 230, 90, 255 }, TRand()*0.3f);
            for (int k = 0; k < len; k++) BlendW(&im, x + (k > len/2 ? 1 : 0), y - k, bc, 0.75f);
        }
        if (d->scenery != SCENERY_SPOOKY) {
            for (int i = 0; i < (d->scenery == SCENERY_RACEWAY ? 20 : 70); i++) {   /* clover + tiny flowers */
                int x = TRandI(W), y = TRandI(W);
                Color fc = TRand() < 0.5f ? (Color){ 255, 255, 255, 255 } : TRand() < 0.5f ? (Color){ 255, 230, 60, 255 } : (Color){ 255, 120, 180, 255 };
                PutW(&im, x, y, fc); PutW(&im, x + 1, y, fc); PutW(&im, x, y + 1, fc); PutW(&im, x + 1, y + 1, Shade(fc, 0.8f));
            }
        } else {
            for (int i = 0; i < 120; i++) {  /* fallen leaves */
                Color lc = TRand() < 0.5f ? (Color){ 200, 110, 40, 255 } : (Color){ 140, 80, 110, 255 };
                Blob(&im, TRand()*W, TRand()*W, 1.8f, lc, 2);
            }
        }
    } else if (d->scenery == SCENERY_DESERT || d->scenery == SCENERY_BEACH || d->scenery == SCENERY_ISLAND) {
        for (int i = 0; i < 160; i++) {
            Color pc = d->scenery != SCENERY_DESERT ? (TRand() < 0.4f ? (Color){ 255, 250, 240, 255 } : (Color){ 220, 190, 140, 255 }) : (Color){ 175, 120, 70, 255 };
            Blob(&im, TRand()*W, TRand()*W, 1.2f + TRand()*1.3f, pc, 2);
        }
    }
    return im;
}

/* ---------------------------------------------------------------- */
/* panoramas (2048 x 256, tile horizontally, alpha = sky)             */
/* ---------------------------------------------------------------- */
#define PW 2048
#define PH 256
static float Profile(float x, int seed, int k0, int k1, float amp)
{
    /* periodic over PW: sum of sines with integer frequencies */
    float s = 0;
    unsigned int h = (unsigned int)seed*2654435761u;
    for (int k = k0; k <= k1; k++) {
        h = h*1664525u + 1013904223u;
        float ph = (h >> 8)/16777216.0f*2*PI;
        s += sinf(2*PI*k*x/PW + ph)/(float)k;
    }
    return s*amp;
}

static void PanoLayer(Image *im, int seed, int k0, int k1, float amp, float baseH, Color col, Color haze, float hazeAmt, bool snowCaps, float capLine, bool jag)
{
    for (int x = 0; x < PW; x++) {
        float h = baseH + Profile((float)x, seed, k0, k1, amp);
        if (jag) h += fabsf(Profile((float)x, seed + 7, k1*3, k1*6, amp*0.35f));
        int top = (int)h;
        for (int yy = 0; yy < top && yy < PH; yy++) {
            int y = PH - 1 - yy;
            float rel = (float)yy/fmaxf(h, 1);
            float n = TFbm((float)x/PW, (float)yy/PH, 32, 3, (unsigned)seed);
            /* lit slopes: lighter on one side of each peak */
            float slope = Profile((float)x + 3, seed, k0, k1, amp) - Profile((float)x - 3, seed, k0, k1, amp);
            float sh = 0.82f + 0.25f*rel + Clamp(slope*0.08f, -0.18f, 0.18f) + (n - 0.5f)*0.18f;
            Color c = Shade(col, sh);
            if (snowCaps && yy > capLine + (n - 0.5f)*24 && yy > h - (h - capLine)*1.0f) c = Shade((Color){ 245, 248, 255, 255 }, 0.9f + 0.15f*rel + Clamp(slope*0.05f, -0.12f, 0.12f));
            c = Mix(c, haze, hazeAmt*(1.0f - 0.25f*rel));
            c.a = 255;
            if (yy == top - 1) c.a = (unsigned char)(255*(h - top + 0.5f > 1 ? 1 : h - top + 0.5f) + 0.5f);
            PutW(im, x, y, c.a == 255 ? c : Mix(GetW(im, x, y), (Color){ c.r, c.g, c.b, 255 }, c.a/255.0f));
        }
    }
}

static void PanoTreeLine(Image *im, int seed, float baseH, float amp, Color col, int count, bool pine)
{
    trs = (unsigned)seed;
    for (int i = 0; i < count; i++) {
        float x = TRand()*PW;
        float h = baseH + Profile(x, seed, 2, 9, amp) - 2;
        float s = 5 + TRand()*7;
        Color c = Shade(col, 0.85f + TRand()*0.3f);
        if (pine) {
            for (int yy = 0; yy < (int)(s*2.6f); yy++) {
                float w = s*(1.0f - yy/(s*2.6f));
                for (int dx = (int)-w; dx <= (int)w; dx++) PutW(im, (int)x + dx, PH - 1 - (int)(h + yy), Shade(c, dx < 0 ? 0.85f : 1.05f));
            }
        } else {
            for (int yy = -2; yy < (int)s; yy++) PutW(im, (int)x, PH - 1 - (int)(h + yy), (Color){ 90, 60, 40, 255 });
            Blob(im, x, PH - 1 - (h + s*1.3f), s, c, 3);
            Blob(im, x - s*0.3f, PH - 1 - (h + s*1.6f), s*0.5f, Shade(c, 1.2f), 3);
        }
    }
}

static void PanoCastle(Image *im, float cx, float baseH, float sc, Color col, Color win)
{
    int towers[5][3] = { { -40, 60, 9 }, { -18, 82, 11 }, { 0, 100, 13 }, { 20, 76, 10 }, { 42, 58, 9 } };
    ImageDrawRectangle(im, (int)(cx - 44*sc), PH - (int)(baseH + 50*sc), (int)(88*sc), (int)(50*sc), col);
    for (int t = 0; t < 5; t++) {
        float x = cx + towers[t][0]*sc, h = towers[t][1]*sc, w = towers[t][2]*sc;
        ImageDrawRectangle(im, (int)(x - w/2), PH - (int)(baseH + h), (int)w, (int)h, col);
        for (int yy = 0; yy < (int)(w*1.6f); yy++) {     /* pointy roof */
            float hw = w*0.65f*(1.0f - yy/(w*1.6f));
            for (int dx = (int)-hw; dx <= (int)hw; dx++) PutW(im, (int)x + dx, PH - 1 - (int)(baseH + h + yy), Shade(col, 0.8f));
        }
        for (int k = 1; k < 4; k++) ImageDrawRectangle(im, (int)(x - 1), PH - (int)(baseH + h - k*h*0.22f), 2, 3, win);
    }
}

static Image GenPanorama(const TrackDef *d, int idx)
{
    Image im = GenImageColor(PW, PH, (Color){ 0, 0, 0, 0 });
    Color hz = d->skyBottom;
    int s = 300 + idx*31;
    if (d->scenery == SCENERY_STADIUM) return im;     /* indoors: nothing beyond the stands */
    switch (d->scenery) {
    case SCENERY_MEADOW:
        PanoLayer(&im, s, 2, 7, 70, 120, (Color){ 105, 130, 185, 255 }, hz, 0.45f, true, 140, true);
        PanoLayer(&im, s + 1, 3, 10, 26, 62, (Color){ 80, 165, 75, 255 }, hz, 0.28f, false, 0, false);
        PanoTreeLine(&im, s + 1, 62, 26, (Color){ 50, 120, 50, 255 }, 160, false);
        PanoLayer(&im, s + 2, 4, 12, 14, 38, (Color){ 70, 175, 60, 255 }, hz, 0.12f, false, 0, false);
        break;
    case SCENERY_BEACH:
        PanoLayer(&im, s, 3, 9, 50, 40, (Color){ 70, 140, 110, 255 }, hz, 0.5f, false, 0, true);
        PanoTreeLine(&im, s, 40, 50, (Color){ 50, 120, 70, 255 }, 50, false);
        for (int x = 0; x < PW; x++) for (int yy = 0; yy < 34; yy++) {   /* open sea to the horizon */
            Color c = Mix((Color){ 30, 130, 210, 255 }, (Color){ 120, 210, 240, 255 }, yy/34.0f);
            if (HashF(x/6, yy, 7) > 0.93f) c = Mix(c, WHITE, 0.6f);
            PutW(&im, x, PH - 1 - yy, c);
        }
        break;
    case SCENERY_DESERT:
        for (int x = 0; x < PW; x++) {     /* flat-topped mesas */
            float h = 40 + Profile((float)x, s, 2, 8, 120);
            float plateau = 95 + Profile((float)x, s + 3, 1, 3, 20);
            if (h > plateau) h = plateau + (h - plateau)*0.04f;
            if (h < 30) h = 30;
            for (int yy = 0; yy < (int)h; yy++) {
                float band = sinf(yy*0.32f + HashF(x/40, 0, 3))*0.06f;
                Color c = Shade((Color){ 205, 110, 70, 255 }, 0.8f + 0.25f*yy/h + band + (TFbm((float)x/PW, (float)yy/PH, 32, 2, 9) - 0.5f)*0.2f);
                c = Mix(c, hz, 0.42f); c.a = 255;
                PutW(&im, x, PH - 1 - yy, c);
            }
        }
        for (int p = 0; p < 3; p++) {      /* pyramids */
            float cx = 300 + p*680.0f, h = 70 + p*12.0f;
            for (int yy = 0; yy < (int)h; yy++) {
                float hw = h*1.1f*(1.0f - yy/h);
                for (int dx = (int)-hw; dx <= (int)hw; dx++)
                    PutW(&im, (int)cx + dx, PH - 1 - yy, Mix(Shade((Color){ 235, 195, 120, 255 }, dx < 0 ? 1.0f : 0.78f), hz, 0.35f));
            }
        }
        PanoLayer(&im, s + 2, 3, 10, 12, 30, (Color){ 240, 190, 105, 255 }, hz, 0.15f, false, 0, false);
        break;
    case SCENERY_SNOW:
        PanoLayer(&im, s, 2, 6, 110, 150, (Color){ 120, 135, 175, 255 }, hz, 0.35f, true, 120, true);
        PanoLayer(&im, s + 1, 3, 9, 40, 80, (Color){ 140, 155, 190, 255 }, hz, 0.22f, true, 70, true);
        PanoTreeLine(&im, s + 2, 40, 14, (Color){ 40, 90, 70, 255 }, 260, true);
        PanoLayer(&im, s + 2, 4, 12, 14, 40, (Color){ 235, 242, 255, 255 }, hz, 0.05f, false, 0, false);
        break;
    case SCENERY_SPOOKY:
        PanoLayer(&im, s, 2, 7, 40, 70, (Color){ 80, 60, 110, 255 }, hz, 0.35f, false, 0, false);
        PanoCastle(&im, 600, 60, 1.0f, (Color){ 55, 40, 75, 255 }, (Color){ 255, 220, 110, 255 });
        PanoCastle(&im, 1550, 50, 0.7f, (Color){ 60, 45, 82, 255 }, (Color){ 255, 220, 110, 255 });
        PanoTreeLine(&im, s + 1, 36, 10, (Color){ 45, 40, 55, 255 }, 120, true);
        PanoLayer(&im, s + 1, 3, 10, 12, 36, (Color){ 60, 70, 55, 255 }, hz, 0.2f, false, 0, false);
        break;
    case SCENERY_RACEWAY:
        PanoLayer(&im, s, 2, 6, 80, 120, (Color){ 120, 140, 190, 255 }, hz, 0.5f, true, 150, true);
        PanoLayer(&im, s + 1, 3, 9, 30, 64, (Color){ 96, 170, 80, 255 }, hz, 0.3f, false, 0, false);
        PanoTreeLine(&im, s + 1, 64, 30, (Color){ 40, 110, 50, 255 }, 140, true);
        PanoLayer(&im, s + 2, 4, 12, 12, 36, (Color){ 104, 184, 70, 255 }, hz, 0.12f, false, 0, false);
        break;
    case SCENERY_JUNGLE:
        PanoLayer(&im, s, 2, 7, 100, 150, (Color){ 170, 110, 120, 255 }, hz, 0.5f, false, 0, true);
        PanoLayer(&im, s + 1, 3, 9, 50, 90, (Color){ 90, 120, 70, 255 }, hz, 0.35f, false, 0, true);
        PanoTreeLine(&im, s + 2, 70, 40, (Color){ 30, 80, 40, 255 }, 220, false);
        PanoLayer(&im, s + 2, 5, 14, 18, 52, (Color){ 40, 100, 45, 255 }, hz, 0.15f, false, 0, false);
        break;
    case SCENERY_ISLAND:
        for (int k = 0; k < 4; k++) {      /* little islands on the horizon */
            float cx = 220 + k*520.0f + HashF(k, 0, 3)*120, w = 60 + HashF(k, 1, 3)*90, h = 18 + HashF(k, 2, 3)*26;
            for (int dx = (int)-w; dx <= (int)w; dx++) {
                float t = dx/w, hh = h*sqrtf(fmaxf(0, 1 - t*t))*(0.8f + 0.2f*sinf(dx*0.15f));
                for (int yy = 0; yy < (int)(30 + hh); yy++) PutW(&im, (int)cx + dx, PH - 1 - yy, Mix((Color){ 70, 130, 90, 255 }, hz, 0.45f));
            }
        }
        for (int x = 0; x < PW; x++) for (int yy = 0; yy < 32; yy++) {
            Color c = Mix((Color){ 20, 120, 210, 255 }, (Color){ 120, 210, 245, 255 }, yy/32.0f);
            if (HashF(x/6, yy, 9) > 0.93f) c = Mix(c, WHITE, 0.6f);
            PutW(&im, x, PH - 1 - yy, c);
        }
        break;
    case SCENERY_FARM:
        PanoLayer(&im, s, 2, 6, 70, 110, (Color){ 130, 140, 190, 255 }, hz, 0.5f, true, 160, true);
        PanoLayer(&im, s + 1, 3, 8, 22, 56, (Color){ 140, 180, 80, 255 }, hz, 0.3f, false, 0, false);
        for (int x = 0; x < PW; x++) for (int yy = 0; yy < 50; yy++) {   /* patchwork fields */
            int f = (x/90 + yy/12) % 4;
            Color fc = f == 0 ? (Color){ 120, 180, 70, 255 } : f == 1 ? (Color){ 220, 200, 100, 255 } : f == 2 ? (Color){ 90, 150, 60, 255 } : (Color){ 170, 140, 90, 255 };
            if (yy < 50 - (int)(8 + Profile((float)x, s + 4, 3, 9, 10))) PutW(&im, x, PH - 1 - yy, Mix(fc, hz, 0.25f));
        }
        PanoTreeLine(&im, s + 3, 50, 12, (Color){ 50, 110, 50, 255 }, 80, false);
        break;
    default: {
        /* starlight: soft nebula + bright stars + a ringed planet */
        for (int y = 0; y < PH; y++) for (int x = 0; x < PW; x++) {
            float n = TFbm((float)x/PW, (float)y/PH, 8, 4, (unsigned)s);
            float band = expf(-powf((y - 150.0f)/55.0f, 2));
            float a = Clamp((n - 0.42f)*2.2f, 0, 1)*band;
            Color c = Mix((Color){ 120, 60, 200, 255 }, (Color){ 255, 90, 170, 255 }, TFbm((float)x/PW, (float)y/PH, 4, 2, (unsigned)s + 3));
            c.a = C8(a*150);
            if (HashF(x, y, (unsigned)s) > 0.9985f) c = (Color){ 255, 255, 255, 255 };
            PutW(&im, x, y, c);
        }
        float pcx = 1300, pcy = 80, pr = 34;
        for (int y = (int)(pcy - pr); y <= (int)(pcy + pr); y++) for (int x = (int)(pcx - pr); x <= (int)(pcx + pr); x++) {
            float dx = (x - pcx)/pr, dy = (y - pcy)/pr;
            if (dx*dx + dy*dy > 1) continue;
            float l = 0.55f + 0.45f*(-dx*0.6f - dy*0.5f + sqrtf(fmaxf(0, 1 - dx*dx - dy*dy))*0.6f);
            PutW(&im, x, y, Shade(Mix((Color){ 255, 160, 90, 255 }, (Color){ 230, 90, 140, 255 }, (sinf(dy*9) + 1)*0.5f), l));
        }
        for (float a = 0; a < 2*PI; a += 0.004f) {
            float rx = cosf(a)*62, ry = sinf(a)*12;
            if (ry < 0 && rx*rx/(pr*pr) + ry*ry/(pr*pr) < 1) continue;
            PutW(&im, (int)(pcx + rx), (int)(pcy + ry), (Color){ 255, 230, 180, 255 });
            PutW(&im, (int)(pcx + rx*0.92f), (int)(pcy + ry*0.92f), (Color){ 220, 180, 150, 255 });
        }
    } break;
    }
    return im;
}

/* ---------------------------------------------------------------- */
/* Mudslide Megadome: ribbed supercross dirt + the arena atlas        */
/* ---------------------------------------------------------------- */
/* 256x256, tiles 6 units along the track: four raked ribs per tile with a dark groove in each */
static Image GenDirt(void)
{
    int W = 256;
    Image im = GenImageColor(W, W, WHITE);
    for (int y = 0; y < W; y++) for (int x = 0; x < W; x++) {
        float u = (float)x/W, v = (float)y/W;
        float n = TFbm(u, v, 8, 4, 501), n2 = TFbm(u, v, 32, 2, 517);
        float wob = (TFbm(u, v*0.25f, 4, 2, 533) - 0.5f)*0.05f;
        float ph = fmodf((v + wob)*4.0f + 4.0f, 1.0f);
        float rib = 0.5f + 0.5f*cosf(ph*2*PI);                       /* rounded ridge */
        float groove = expf(-powf((ph - 0.5f)/0.045f, 2));           /* dark line in the trough */
        float val = 0.86f + 0.12f*rib - 0.34f*groove + (n - 0.5f)*0.3f + (n2 - 0.5f)*0.12f;
        float sp = HashF(x, y, 541);
        if (sp > 0.988f) val += 0.18f; else if (sp < 0.01f) val -= 0.25f;   /* clods + pebbles */
        Color c = { C8(255*val), C8(244*val), C8(232*val), 255 };
        PutW(&im, x, y, c);
    }
    return im;
}

/* Our mascot "Tumble": a round, grinning crash-helmet face with goggles and a 64 badge, drawn as
   a single-colour motif (used darker-blue on the light-blue walls, white on posters). */
static void DrawMascot(Image *im, float cx, float cy, float r, Color c, Color bg)
{
    for (int y = (int)(cy - r*1.2f); y <= (int)(cy + r*1.2f); y++) for (int x = (int)(cx - r*1.2f); x <= (int)(cx + r*1.2f); x++) {
        float dx = (x - cx)/r, dy = (y - cy)/r, d = sqrtf(dx*dx + dy*dy);
        float a = 0;
        if (d < 1.0f && d > 0.86f) a = 1;                                        /* head outline */
        if (dy < -0.25f && d < 0.86f && fabsf(dy + 0.62f) < 0.07f) a = 1;      /* helmet stripe */
        if (dy < -0.62f && d < 1.0f && fabsf(dx) < 0.13f) a = 1;               /* centre crest */
        for (int e = -1; e <= 1; e += 2) {                                      /* goggles */
            float gx = (dx - e*0.36f)/0.27f, gy = (dy + 0.1f)/0.22f, gd = gx*gx + gy*gy;
            if (gd < 1.0f && gd > 0.45f) a = 1;
            float px = (dx - e*0.33f)/0.09f, py = (dy + 0.06f)/0.1f;           /* pupils glance sideways */
            if (px*px + py*py < 1) a = 1;
        }
        if (fabsf(dx) < 0.1f && fabsf(dy + 0.1f) < 0.04f) a = 1;               /* goggle bridge */
        float my = dy - 0.32f, ar = sqrtf(dx*dx*0.9f + (my + 0.18f)*(my + 0.18f));
        if (my > -0.02f && fabsf(ar - 0.45f) < 0.065f && fabsf(dx) < 0.48f) a = 1;   /* big grin */
        if (my > 0.1f && my < 0.24f && fabsf(dx) < 0.3f && ar < 0.45f) a = ((int)((dx + 1)*14) & 1) ? 1 : a; /* teeth */
        if (a > 0) PutW(im, x, y, c);
        else if (d < 0.86f && bg.a) PutW(im, x, y, bg);
    }
}

static Rectangle ArenaPx(int region)
{
    static const short R[ARENA_COUNT][4] = {
        { 0, 0, 256, 256 }, { 256, 0, 256, 128 }, { 256, 128, 256, 128 }, { 512, 0, 512, 128 },
        { 512, 128, 512, 128 }, { 0, 256, 512, 128 }, { 512, 256, 256, 128 }, { 768, 256, 256, 128 },
        { 0, 384, 256, 128 }, { 256, 384, 256, 128 }, { 512, 384, 512, 128 } };
    return (Rectangle){ R[region][0], R[region][1], R[region][2], R[region][3] };
}

Rectangle ArenaUV(int region)
{
    Rectangle r = ArenaPx(region);
    const float in = 1.5f;     /* keep bilinear / mip taps inside the region */
    return (Rectangle){ (r.x + in)/1024.0f, (r.y + in)/512.0f, (r.width - 2*in)/1024.0f, (r.height - 2*in)/512.0f };
}

static void ChequerFlag(Image *im, int x0, int y0, int w, int h, int cell)
{
    for (int y = 0; y < h; y++) for (int x = 0; x < w; x++) {
        float wave = sinf(x*0.09f)*3.0f;
        int yy = (int)(y + wave);
        Color c = ((((x/cell) + ((yy < 0 ? yy - cell : yy)/cell)) & 1) ? (Color){ 245, 245, 245, 255 } : (Color){ 18, 18, 18, 255 });
        PutW(im, x0 + x, y0 + y, c);
    }
}

static Image GenArena(void)
{
    Image im = GenImageColor(1024, 512, (Color){ 20, 20, 24, 255 });
    Rectangle r;
    /* light-blue retaining wall panel with the mascot in darker blue */
    r = ArenaPx(ARENA_WALL);
    for (int y = 0; y < 256; y++) for (int x = 0; x < 256; x++) {
        float n = TFbm(x/256.0f, y/256.0f, 8, 3, 601);
        Color c = Shade((Color){ 132, 200, 236, 255 }, 0.92f + 0.12f*n);
        if (x < 3 || x > 252) c = Shade(c, 0.7f);                 /* panel seam */
        if (y < 12) c = Shade((Color){ 70, 120, 190, 255 }, 0.9f + 0.1f*n);   /* cap */
        if (y > 236) c = Shade(c, 0.78f);                          /* kick plate */
        PutW(&im, x, y, c);
    }
    DrawMascot(&im, 128, 118, 82, (Color){ 46, 98, 176, 255 }, (Color){ 0, 0, 0, 0 });
    for (int k = 0; k < 2; k++) { Blob(&im, 14.0f + k*228, 24, 3, (Color){ 60, 90, 130, 255 }, 3); Blob(&im, 14.0f + k*228, 226, 3, (Color){ 60, 90, 130, 255 }, 3); }
    /* red/white diagonal stripes: period 64 px so each 128-px half tiles too */
    r = ArenaPx(ARENA_STRIPES);
    for (int y = 0; y < 128; y++) for (int x = 0; x < 256; x++) {
        float n = TFbm(x/256.0f, y/128.0f, 8, 3, 611);
        bool red = (((x + y) & 63) < 32);
        Color c = red ? (Color){ 222, 36, 40, 255 } : (Color){ 246, 244, 238, 255 };
        c = Shade(c, 0.88f + 0.16f*n);
        if (y < 6 || y > 121) c = Shade((Color){ 170, 170, 165, 255 }, 0.9f + 0.1f*n);
        PutW(&im, (int)r.x + x, (int)r.y + y, c);
    }
    r = ArenaPx(ARENA_CONCRETE);
    for (int y = 0; y < 128; y++) for (int x = 0; x < 256; x++) {
        float n = TFbm(x/256.0f, y/128.0f, 8, 4, 621);
        float v = 175 + 50*(n - 0.5f) + (HashF(x, y, 623) - 0.5f)*18;
        PutW(&im, (int)r.x + x, (int)r.y + y, (Color){ C8(v), C8(v), C8(v*0.97f), 255 });
    }
    /* start banner: black with chequered flags at both ends */
    r = ArenaPx(ARENA_BANNER);
    ImageDrawRectangle(&im, (int)r.x, (int)r.y, 512, 128, (Color){ 12, 12, 14, 255 });
    ImageDrawRectangleLines(&im, (Rectangle){ r.x + 4, r.y + 4, 504, 120 }, 3, (Color){ 230, 230, 230, 255 });
    ChequerFlag(&im, (int)r.x + 14, (int)r.y + 22, 70, 84, 14);
    ChequerFlag(&im, (int)r.x + 428, (int)r.y + 22, 70, 84, 14);
    SignText(&im, "TURBO TUMBLE 64", (int)r.x + 90, (int)r.y + 10, 332, 108, 50, (Color){ 255, 255, 255, 255 }, (Color){ 200, 20, 30, 255 });
    /* neon sign: yellow arrow + BIG AIR */
    r = ArenaPx(ARENA_NEON);
    ImageDrawRectangle(&im, (int)r.x, (int)r.y, 512, 128, (Color){ 16, 8, 30, 255 });
    for (int k = 0; k < 3; k++) ImageDrawRectangleLines(&im, (Rectangle){ r.x + 5 + k, r.y + 5 + k, 502 - 2*k, 118 - 2*k }, 1, (Color){ 255, 70, 200, 255 });
    {
        int ax = (int)r.x + 380, ay = (int)r.y + 64;
        for (int y = -44; y <= 44; y++) for (int x = -110; x <= 110; x++) {
            bool head = x > 30 && abs(y) < (110 - x)*0.55f;
            bool shaft = x <= 30 && x > -100 && abs(y) < 16;
            if (head || shaft) PutW(&im, ax + x, ay + y, (Color){ 255, 225, 30, 255 });
        }
    }
    SignText(&im, "BIG AIR", (int)r.x + 18, (int)r.y + 14, 240, 100, 48, (Color){ 120, 240, 255, 255 }, (Color){ 20, 60, 140, 255 });
    /* title board / jumbotron bezel */
    r = ArenaPx(ARENA_TITLE);
    for (int y = 0; y < 128; y++) for (int x = 0; x < 512; x++)
        PutW(&im, (int)r.x + x, (int)r.y + y, Mix((Color){ 30, 70, 170, 255 }, (Color){ 12, 30, 90, 255 }, y/128.0f));
    ImageDrawRectangleLines(&im, (Rectangle){ r.x + 3, r.y + 3, 506, 122 }, 4, (Color){ 255, 210, 40, 255 });
    DrawMascot(&im, r.x + 64, r.y + 64, 46, WHITE, (Color){ 46, 98, 176, 255 });
    SignText(&im, "MUDSLIDE MEGADOME", (int)r.x + 118, (int)r.y + 12, 386, 104, 40, (Color){ 255, 255, 255, 255 }, (Color){ 10, 20, 70, 255 });
    r = ArenaPx(ARENA_CHEQUER);
    for (int y = 0; y < 128; y++) for (int x = 0; x < 256; x++)
        PutW(&im, (int)r.x + x, (int)r.y + y, (((x/32) + (y/32)) & 1) ? (Color){ 245, 245, 245, 255 } : (Color){ 18, 18, 18, 255 });
    r = ArenaPx(ARENA_WHITE);
    for (int y = 0; y < 128; y++) for (int x = 0; x < 256; x++) {
        float v = 236 + (HashF(x, y, 631) - 0.5f)*14;
        PutW(&im, (int)r.x + x, (int)r.y + y, (Color){ C8(v), C8(v), C8(v), 255 });
    }
    /* flood-light panel: 4x2 lamps */
    r = ArenaPx(ARENA_LAMPS);
    ImageDrawRectangle(&im, (int)r.x, (int)r.y, 256, 128, (Color){ 50, 52, 58, 255 });
    for (int j = 0; j < 2; j++) for (int i = 0; i < 4; i++) {
        float cx = r.x + 32 + i*64, cy = r.y + 32 + j*64;
        Blob(&im, cx, cy, 28, (Color){ 120, 120, 110, 255 }, 6);
        Blob(&im, cx, cy, 24, (Color){ 255, 250, 225, 255 }, 2.5f);
        Blob(&im, cx, cy, 12, WHITE, 3);
    }
    /* steel truss: lattice of X braces */
    r = ArenaPx(ARENA_TRUSS);
    ImageDrawRectangle(&im, (int)r.x, (int)r.y, 256, 128, (Color){ 40, 42, 48, 255 });
    for (int y = 0; y < 128; y++) for (int x = 0; x < 256; x++) {
        int xm = x % 64;
        bool chord = y < 10 || y > 117 || xm < 5;
        bool brace = abs(xm - y/2) < 4 || abs(xm - (64 - y/2)) < 4;
        if (chord || brace) PutW(&im, (int)r.x + x, (int)r.y + y, Shade((Color){ 200, 205, 215, 255 }, 0.8f + 0.3f*HashF(x/4, y/4, 641)));
    }
    /* advert board */
    r = ArenaPx(ARENA_AD);
    for (int y = 0; y < 128; y++) for (int x = 0; x < 512; x++)
        PutW(&im, (int)r.x + x, (int)r.y + y, Mix((Color){ 255, 200, 30, 255 }, (Color){ 250, 130, 20, 255 }, y/128.0f));
    DrawMascot(&im, r.x + 448, r.y + 64, 48, (Color){ 40, 20, 10, 255 }, WHITE);
    SignText(&im, "TT64 SUPERCROSS", (int)r.x + 12, (int)r.y + 14, 380, 100, 44, WHITE, (Color){ 160, 30, 20, 255 });
    return im;
}

/* ---------------------------------------------------------------- */
/* v7: dusty trail with tyre ruts (tinted by the course road colour) */
static Image GenTrail(void)
{
    int W = 256;
    Image im = GenImageColor(W, W, WHITE);
    for (int y = 0; y < W; y++) for (int x = 0; x < W; x++) {
        float u = (float)x/W, v = (float)y/W;
        float n = TFbm(u, v, 6, 4, 611), n2 = TFbm(u, v, 24, 2, 613);
        float wob = (TFbm(u*0.5f, v, 3, 2, 617) - 0.5f)*0.04f;
        float rut = 0;
        for (int k = 0; k < 4; k++) { float c = 0.18f + k*0.215f; rut += expf(-powf((u + wob - c)/0.035f, 2)); }
        float val = 0.95f + (n - 0.5f)*0.32f + (n2 - 0.5f)*0.14f - 0.13f*rut;
        float sp = HashF(x, y, 619);
        if (sp > 0.985f) val += 0.16f; else if (sp < 0.012f) val -= 0.22f;
        PutW(&im, x, y, (Color){ C8(255*val), C8(246*val), C8(236*val), 255 });
    }
    return im;
}

/* v7: yellow boost floor with big red forward chevrons (forward = +v) */
static Image GenChevron(void)
{
    int W = 128;
    Image im = GenImageColor(W, W, WHITE);
    for (int y = 0; y < W; y++) for (int x = 0; x < W; x++) {
        float yc = 0.18f*W + (W*0.5f - fabsf(x - W*0.5f))*0.62f;
        float dy = y - yc;
        Color c = (Color){ 255, 214, 40, 255 };
        if (dy >= 0 && dy < 0.24f*W) c = (Color){ 228, 34, 30, 255 };
        if (x < 6 || x >= W - 6) c = (Color){ 60, 60, 66, 255 };
        float n = TFbm((float)x/W, (float)y/W, 8, 2, 621);
        PutW(&im, x, y, Shade(c, 0.92f + 0.12f*n));
    }
    return im;
}

/* v7: weathered bridge planks running across the deck, dark gaps between */
static Image GenPlank(void)
{
    int W = 128;
    Image im = GenImageColor(W, W, WHITE);
    Color base = { 206, 160, 110, 255 };
    for (int y = 0; y < W; y++) {
        int plank = y/32;
        float tone = 0.8f + 0.3f*HashF(plank, 3, 631);
        for (int x = 0; x < W; x++) {
            float u = (float)x/W, v = (float)y/W;
            float g = sinf((u*W*0.25f + TFbm(u, v, 4, 3, 633 + plank)*10.0f)*1.1f);
            Color c = Shade(base, tone*(0.9f + 0.08f*g + (TFbm(u, v, 16, 2, 637) - 0.5f)*0.16f));
            if (y % 32 < 4) c = (Color){ 50, 36, 26, 255 };
            PutW(&im, x, y, c);
        }
    }
    return im;
}

void TexturesInit(void)
{
    G.tx[TX_GRAIN] = Upload(GenGrain(), true, true);
    G.tx[TX_ROAD] = Upload(GenRoad(), true, true);
    G.tx[TX_CURB] = Upload(GenCurb(), true, true);
    G.tx[TX_BARRIER] = Upload(GenBarrier(), true, true);
    G.tx[TX_WOOD] = Upload(GenWood(), true, true);
    G.tx[TX_STONE] = Upload(GenStone(), true, true);
    G.tx[TX_ROCK] = Upload(GenRock(), true, true);
    G.tx[TX_BARK] = Upload(GenBark(), true, true);
    G.tx[TX_LEAVES] = Upload(GenLeaves(), true, true);
    G.tx[TX_ROOF] = Upload(GenRoof(), true, true);
    G.tx[TX_CROWD] = Upload(GenCrowd(), true, true);
    G.tx[TX_SIGNS] = Upload(GenSigns(), true, false);
    G.tx[TX_WATER] = Upload(GenWater(), true, true);
    G.tx[TX_RAINBOW] = Upload(GenRainbowTile(), true, true);
    G.tx[TX_ITEMBOX] = Upload(GenItemBox(), true, false);
    G.tx[TX_CLOUD] = Upload(GenCloud(), true, false);
    G.tx[TX_DIRT] = Upload(GenDirt(), true, true);
    G.tx[TX_ARENA] = Upload(GenArena(), true, false);
    G.tx[TX_TRAIL] = Upload(GenTrail(), true, true);
    G.tx[TX_CHEVRON] = Upload(GenChevron(), true, true);
    G.tx[TX_PLANK] = Upload(GenPlank(), true, true);
    for (int i = 0; i < NUM_TRACKS; i++) G.texGround[i] = Upload(GenGround(&TRACK_DEFS[i], i), true, true);
    G.texRoad = G.tx[TX_ROAD];
}

Texture2D TexturePanorama(int track)
{
    if (!G.texPano[track].id) {
        G.texPano[track] = Upload(GenPanorama(&TRACK_DEFS[track], track), true, true);
        rlTextureParameters(G.texPano[track].id, RL_TEXTURE_WRAP_T, RL_TEXTURE_WRAP_CLAMP);   /* no top/bottom bleed */
    }
    return G.texPano[track];
}

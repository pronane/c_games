/* scenery.c : dense, textured trackside scenery.
 *
 * Every prop is baked once into static meshes, grouped by texture and by a
 * spatial grid of chunks. At draw time each chunk is frustum / distance culled,
 * so a track with thousands of props still costs only a few dozen draw calls.
 * Shapes use smooth (Gouraud) normals with baked sunlight. */
#include "common.h"

/* ---------------------------------------------------------------- */
/* chunk builders                                                    */
/* ---------------------------------------------------------------- */
static const int MATS[SCENE_MATS] = { TX_GRAIN, TX_WOOD, TX_STONE, TX_ROCK, TX_BARK, TX_LEAVES, TX_ROOF, TX_CROWD, TX_SIGNS, TX_RAINBOW, TX_CURB, TX_BARRIER, TX_DIRT, TX_ARENA };
static MeshBuilder SB[MAX_SCENE_CHUNKS][SCENE_MATS];
static bool SBused[MAX_SCENE_CHUNKS][SCENE_MATS];
static int gcx, gcz, curChunk, FARC;
static float gx0, gz0, gcell;
static Track *ST;
static float gDet = 1.0f;     /* tessellation factor: ENHANCED 1, ORIGINAL ~0.65 */

static int MatIndex(int tex) { for (int i = 0; i < SCENE_MATS; i++) if (MATS[i] == tex) return i; return 0; }
static MeshBuilder *M(int tex)
{
    int mi = MatIndex(tex);
    if (!SBused[curChunk][mi]) { MB_Init(&SB[curChunk][mi]); SBused[curChunk][mi] = true; }
    return &SB[curChunk][mi];
}
static void At(Vector3 p)
{
    int cx = (int)((p.x - gx0)/gcell), cz = (int)((p.z - gz0)/gcell);
    if (cx < 0 || cz < 0 || cx >= gcx || cz >= gcz) { curChunk = FARC; return; }
    curChunk = cz*gcx + cx;
}
static void Far(void) { curChunk = FARC; }
static int Seg(int n) { int s = (int)(n*gDet + 0.5f); return s < 4 ? 4 : s; }

static unsigned int srng = 1;
static float RR(float lo, float hi) { srng = srng*1664525u + 1013904223u; return lo + (hi - lo)*((srng >> 8)/16777216.0f); }

/* ---------------------------------------------------------------- */
/* primitives with UVs + smooth normals                               */
/* ---------------------------------------------------------------- */
#define VL MB_VertexLit
static Vector3 Ortho(Vector3 a)
{
    Vector3 t = fabsf(a.y) < 0.9f ? (Vector3){ 0, 1, 0 } : (Vector3){ 1, 0, 0 };
    return Vector3Normalize(Vector3CrossProduct(a, t));
}

/* tube from a to b with radii r0 -> r1; uv u around (uRep), v along (vRep) */
static void Tube(MeshBuilder *mb, Vector3 a, Vector3 b, float r0, float r1, int sides, Color c, float uRep, float vRep, bool capA, bool capB)
{
    Vector3 ax = Vector3Subtract(b, a);
    float len = Vector3Length(ax);
    if (len < 1e-4f) return;
    Vector3 w = Vector3Scale(ax, 1.0f/len);
    Vector3 u = Ortho(w), v = Vector3CrossProduct(w, u);
    float slope = (r0 - r1)/len;
    for (int i = 0; i < sides; i++) {
        float t0 = 2*PI*i/sides, t1 = 2*PI*(i + 1)/sides;
        Vector3 d0 = Vector3Add(Vector3Scale(u, cosf(t0)), Vector3Scale(v, sinf(t0)));
        Vector3 d1 = Vector3Add(Vector3Scale(u, cosf(t1)), Vector3Scale(v, sinf(t1)));
        Vector3 n0 = Vector3Normalize(Vector3Add(d0, Vector3Scale(w, slope)));
        Vector3 n1 = Vector3Normalize(Vector3Add(d1, Vector3Scale(w, slope)));
        Vector3 p00 = Vector3Add(a, Vector3Scale(d0, r0)), p01 = Vector3Add(a, Vector3Scale(d1, r0));
        Vector3 p10 = Vector3Add(b, Vector3Scale(d0, r1)), p11 = Vector3Add(b, Vector3Scale(d1, r1));
        float ua = uRep*i/sides, ub = uRep*(i + 1)/sides;
        VL(mb, p00, (Vector2){ ua, vRep }, n0, c); VL(mb, p01, (Vector2){ ub, vRep }, n1, c); VL(mb, p11, (Vector2){ ub, 0 }, n1, c);
        if (r1 > 1e-4f) { VL(mb, p00, (Vector2){ ua, vRep }, n0, c); VL(mb, p11, (Vector2){ ub, 0 }, n1, c); VL(mb, p10, (Vector2){ ua, 0 }, n0, c); }
        else { /* cone tip: already covered by the first triangle */ }
        if (capA && r0 > 1e-4f) { Vector3 nn = Vector3Negate(w); VL(mb, a, (Vector2){ 0.5f, 0.5f }, nn, c); VL(mb, p01, (Vector2){ 0.5f + 0.5f*cosf(t1), 0.5f + 0.5f*sinf(t1) }, nn, c); VL(mb, p00, (Vector2){ 0.5f + 0.5f*cosf(t0), 0.5f + 0.5f*sinf(t0) }, nn, c); }
        if (capB && r1 > 1e-4f) { VL(mb, b, (Vector2){ 0.5f, 0.5f }, w, c); VL(mb, p10, (Vector2){ 0.5f + 0.5f*cosf(t0), 0.5f + 0.5f*sinf(t0) }, w, c); VL(mb, p11, (Vector2){ 0.5f + 0.5f*cosf(t1), 0.5f + 0.5f*sinf(t1) }, w, c); }
    }
}
static void Cyl(MeshBuilder *mb, Vector3 base, float r0, float r1, float h, int sides, Color c, float uRep, float vRep)
{
    Tube(mb, base, (Vector3){ base.x, base.y + h, base.z }, r0, r1, sides, c, uRep, vRep, false, true);
}

/* ellipsoid with a bottom->top colour gradient, optional surface wobble (rocks / foliage) */
static void Ellipsoid(MeshBuilder *mb, Vector3 c, Vector3 r, int rings, int slices, Color bot, Color top, float uRep, float vRep, float wobble, unsigned int seed)
{
    static Vector3 P[24][40], N[24][40];
    if (rings > 23) rings = 23;
    if (slices > 39) slices = 39;
    for (int i = 0; i <= rings; i++) {
        float la = -PI*0.5f + PI*i/rings;
        for (int j = 0; j <= slices; j++) {
            float lo = 2*PI*(j % slices)/slices;
            Vector3 n = { cosf(la)*cosf(lo), sinf(la), cosf(la)*sinf(lo) };
            float k = 1.0f;
            if (wobble > 0 && i > 0 && i < rings) k += wobble*(WorldNoise(n.x*2.1f + 5, n.z*2.1f + n.y*1.7f + 3, seed) - 0.5f)*2.0f;
            P[i][j] = (Vector3){ c.x + r.x*n.x*k, c.y + r.y*n.y*k, c.z + r.z*n.z*k };
            N[i][j] = Vector3Normalize((Vector3){ n.x/r.x, n.y/r.y, n.z/r.z });
        }
    }
    for (int i = 0; i < rings; i++) {
        Color c0 = ColorMix(bot, top, (float)i/rings), c1 = ColorMix(bot, top, (float)(i + 1)/rings);
        float v0 = vRep*(1.0f - (float)i/rings), v1 = vRep*(1.0f - (float)(i + 1)/rings);
        for (int j = 0; j < slices; j++) {
            float u0 = uRep*j/slices, u1 = uRep*(j + 1)/slices;
            if (i > 0) { VL(mb, P[i][j], (Vector2){ u0, v0 }, N[i][j], c0); VL(mb, P[i + 1][j + 1], (Vector2){ u1, v1 }, N[i + 1][j + 1], c1); VL(mb, P[i][j + 1], (Vector2){ u1, v0 }, N[i][j + 1], c0); }
            if (i < rings - 1) { VL(mb, P[i][j], (Vector2){ u0, v0 }, N[i][j], c0); VL(mb, P[i + 1][j], (Vector2){ u0, v1 }, N[i + 1][j], c1); VL(mb, P[i + 1][j + 1], (Vector2){ u1, v1 }, N[i + 1][j + 1], c1); }
        }
    }
}
static void Ball(MeshBuilder *mb, Vector3 c, Vector3 r, int rings, int slices, Color col, float rep)
{
    Ellipsoid(mb, c, r, rings, slices, ColorScale(col, 0.92f), col, rep, rep*0.5f, 0, 0);
}

/* box: flat faces, uv in world units / uvs */
static void Box(MeshBuilder *mb, Vector3 ctr, Vector3 size, float yaw, Color c, float uvs)
{
    Vector3 h = Vector3Scale(size, 0.5f);
    float cs = cosf(yaw), sn = sinf(yaw);
    Vector3 p[8];
    for (int i = 0; i < 8; i++) {
        float x = (i & 1) ? h.x : -h.x, y = (i & 2) ? h.y : -h.y, z = (i & 4) ? h.z : -h.z;
        p[i] = (Vector3){ ctr.x + x*cs + z*sn, ctr.y + y, ctr.z - x*sn + z*cs };
    }
    float X = size.x/uvs, Y = size.y/uvs, Z = size.z/uvs;
    MB_QuadUV(mb, p[0], p[1], p[3], p[2], (Vector2){ 0, Y }, (Vector2){ X, Y }, (Vector2){ X, 0 }, (Vector2){ 0, 0 }, c, ctr, true);
    MB_QuadUV(mb, p[4], p[5], p[7], p[6], (Vector2){ 0, Y }, (Vector2){ X, Y }, (Vector2){ X, 0 }, (Vector2){ 0, 0 }, c, ctr, true);
    MB_QuadUV(mb, p[0], p[4], p[6], p[2], (Vector2){ 0, Y }, (Vector2){ Z, Y }, (Vector2){ Z, 0 }, (Vector2){ 0, 0 }, c, ctr, true);
    MB_QuadUV(mb, p[1], p[5], p[7], p[3], (Vector2){ 0, Y }, (Vector2){ Z, Y }, (Vector2){ Z, 0 }, (Vector2){ 0, 0 }, c, ctr, true);
    MB_QuadUV(mb, p[2], p[3], p[7], p[6], (Vector2){ 0, 0 }, (Vector2){ X, 0 }, (Vector2){ X, Z }, (Vector2){ 0, Z }, c, ctr, true);
    MB_QuadUV(mb, p[0], p[1], p[5], p[4], (Vector2){ 0, 0 }, (Vector2){ X, 0 }, (Vector2){ X, Z }, (Vector2){ 0, Z }, c, ctr, true);
}
static Vector3 Rot(Vector3 o, float yaw, float x, float y, float z) { float c = cosf(yaw), s = sinf(yaw); return (Vector3){ o.x + x*c + z*s, o.y + y, o.z - x*s + z*c }; }

/* a sign board region from the sign atlas (2 cols x 16 rows) */
static void SignUV(int idx, float *u0, float *v0, float *u1, float *v1)
{
    *u0 = (idx & 1)*0.5f + 0.004f; *u1 = *u0 + 0.492f;
    *v0 = (idx >> 1)/16.0f + 0.002f; *v1 = *v0 + 0.0585f;
}
/* textured board: centre c, text runs along dir, facing 'face' (unit) */
static void Board(Vector3 c, Vector3 dir, Vector3 face, float w, float h, int sign)
{
    float u0, v0, u1, v1; SignUV(sign, &u0, &v0, &u1, &v1);
    Vector3 hw = Vector3Scale(dir, w*0.5f), up = { 0, h*0.5f, 0 };
    Vector3 f = Vector3Add(c, Vector3Scale(face, 0.06f));
    Vector3 bl = Vector3Subtract(Vector3Subtract(f, hw), up), br = Vector3Subtract(Vector3Add(f, hw), up);
    Vector3 tr = Vector3Add(Vector3Add(f, hw), up), tl = Vector3Add(Vector3Subtract(f, hw), up);
    MB_QuadUV(M(TX_SIGNS), bl, br, tr, tl, (Vector2){ u0, v1 }, (Vector2){ u1, v1 }, (Vector2){ u1, v0 }, (Vector2){ u0, v0 }, WHITE, Vector3Subtract(c, face), true);
    /* frame / back */
    Box(M(TX_GRAIN), c, (Vector3){ w + 0.25f, h + 0.25f, 0.1f }, atan2f(face.x, face.z), (Color){ 235, 235, 240, 255 }, 2.0f);
}

/* ---------------------------------------------------------------- */
/* placement helpers                                                  */
/* ---------------------------------------------------------------- */
static bool ClearOfTrack(float x, float z, float radius)
{
    const Track *tr = ST;
    for (int i = 0; i < tr->n; i += 2) {
        float lim = tr->s[i].width*0.5f + 1.0f + tr->shoulder + 2.5f + radius;
        float dx = x - tr->s[i].pos.x, dz = z - tr->s[i].pos.z;
        if (dx*dx + dz*dz < lim*lim) return false;
    }
    for (int i = 0; i < tr->scN; i++) {
        float lim = tr->scHalf + 3.0f + radius;
        float dx = x - tr->sc[i].pos.x, dz = z - tr->sc[i].pos.z;
        if (dx*dx + dz*dz < lim*lim) return false;
    }
    return true;
}
static float GY(float x, float z) { return ST->def->noGround ? 0 : TerrainY(ST, x, z) - 0.15f; }
static bool Spot(float minOff, float maxOff, float radius, Vector3 *out)
{
    const Track *tr = ST;
    for (int tries = 0; tries < 24; tries++) {
        int i = (int)RR(0, (float)tr->n - 1);
        const TrackSample *s = &tr->s[i];
        float side = RR(0, 1) < 0.5f ? -1.0f : 1.0f;
        float off = s->width*0.5f + 1.0f + tr->shoulder + RR(minOff, maxOff);
        Vector3 p = Vector3Add(s->pos, Vector3Scale(s->right, side*off));
        if (ClearOfTrack(p.x, p.z, radius)) {
            p.y = tr->def->noGround ? s->pos.y : GY(p.x, p.z);
            *out = p;
            return true;
        }
    }
    return false;
}
static bool Dry(Vector3 p) { return !ST->hasWater || p.y > ST->waterY + 0.25f; }
/* yaw that makes local +z face the nearest track point */
static float FaceTrack(Vector3 p)
{
    float best = 1e18f; int bi = 0;
    for (int i = 0; i < ST->n; i += 2) { float dx = p.x - ST->s[i].pos.x, dz = p.z - ST->s[i].pos.z, d = dx*dx + dz*dz; if (d < best) { best = d; bi = i; } }
    return atan2f(ST->s[bi].pos.x - p.x, ST->s[bi].pos.z - p.z);
}

/* ---------------------------------------------------------------- */
/* props                                                             */
/* ---------------------------------------------------------------- */
static Color Leaf(float h, float s, float v) { return ColorFromHSV(h, s, v); }

static void Oak(Vector3 p, float s)
{
    At(p);
    Color trunk = { 235, 220, 210, 255 };
    Tube(M(TX_BARK), p, (Vector3){ p.x, p.y + 3.4f*s, p.z }, 0.55f*s, 0.36f*s, Seg(8), trunk, 2, 2, false, false);
    float hue = RR(88, 128);
    Color top = Leaf(hue, 0.62f, RR(0.95f, 1.0f)), bot = Leaf(hue + 8, 0.75f, 0.55f);
    Ellipsoid(M(TX_LEAVES), (Vector3){ p.x, p.y + 4.3f*s, p.z }, (Vector3){ 2.7f*s, 2.3f*s, 2.7f*s }, Seg(7), Seg(11), bot, top, 3, 2, 0.12f, srng);
    int k = 2 + (int)RR(0, 3);
    for (int q = 0; q < k; q++) {
        float a = RR(0, 2*PI), rr = RR(1.2f, 1.9f)*s;
        Ellipsoid(M(TX_LEAVES), (Vector3){ p.x + cosf(a)*rr, p.y + RR(4.6f, 6.2f)*s, p.z + sinf(a)*rr }, (Vector3){ 1.55f*s, 1.35f*s, 1.55f*s }, Seg(5), Seg(8), bot, top, 2, 1, 0.1f, srng + q);
    }
}
static void Poplar(Vector3 p, float s)
{
    At(p);
    Tube(M(TX_BARK), p, (Vector3){ p.x, p.y + 2.2f*s, p.z }, 0.4f*s, 0.3f*s, Seg(6), WHITE, 1, 1, false, false);
    float hue = RR(95, 135);
    Ellipsoid(M(TX_LEAVES), (Vector3){ p.x, p.y + 6.2f*s, p.z }, (Vector3){ 1.6f*s, 4.8f*s, 1.6f*s }, Seg(9), Seg(9), Leaf(hue, 0.75f, 0.5f), Leaf(hue - 6, 0.6f, 0.95f), 2, 3, 0.1f, srng);
}
static void Pine(Vector3 p, float s, bool snow)
{
    At(p);
    Tube(M(TX_BARK), p, (Vector3){ p.x, p.y + 2.0f*s, p.z }, 0.45f*s, 0.38f*s, Seg(6), WHITE, 1, 1, false, false);
    float hue = RR(130, 155);
    for (int i = 0; i < 4; i++) {
        float r = (3.1f - i*0.65f)*s, y = p.y + (1.6f + i*1.5f)*s;
        Color c = Leaf(hue, 0.68f, 0.5f + i*0.1f);
        Tube(M(TX_LEAVES), (Vector3){ p.x, y, p.z }, (Vector3){ p.x, y + 2.9f*s, p.z }, r, 0, Seg(10), c, 3, 1, true, false);
        if (snow) Tube(M(TX_GRAIN), (Vector3){ p.x, y + 1.45f*s, p.z }, (Vector3){ p.x, y + 2.95f*s, p.z }, r*0.52f, 0, Seg(10), (Color){ 250, 252, 255, 255 }, 1, 1, true, false);
    }
}
static void Bush(Vector3 p, float s)
{
    At(p);
    float hue = RR(85, 130);
    for (int q = 0; q < 3; q++) {
        float a = RR(0, 2*PI);
        Ellipsoid(M(TX_LEAVES), (Vector3){ p.x + cosf(a)*0.8f*s, p.y + 0.7f*s, p.z + sinf(a)*0.8f*s }, (Vector3){ 1.2f*s, 0.95f*s, 1.2f*s }, Seg(5), Seg(8),
                  Leaf(hue, 0.75f, 0.5f), Leaf(hue - 5, 0.6f, 0.95f), 1, 1, 0.12f, srng + q);
    }
    if (RR(0, 1) < 0.5f) for (int f = 0; f < 5; f++) {   /* berries / blossoms */
        float a = RR(0, 2*PI);
        Ball(M(TX_GRAIN), (Vector3){ p.x + cosf(a)*1.3f*s, p.y + RR(0.8f, 1.5f)*s, p.z + sinf(a)*1.3f*s }, (Vector3){ 0.16f, 0.16f, 0.16f }, 3, 5, HueColor(RR(-20, 50), 0.7f, 1.0f), 1);
    }
}
static void FlowerPatch(Vector3 p)
{
    At(p);
    Color fc = HueColor(RR(0, 1) < 0.5f ? RR(-30, 20) : RR(40, 60) + (RR(0, 1) < 0.3f ? 220 : 0), RR(0.5f, 0.8f), 1.0f);
    if (RR(0, 1) < 0.25f) fc = WHITE;
    int n = 6 + (int)RR(0, 8);
    for (int i = 0; i < n; i++) {
        float a = RR(0, 2*PI), r = RR(0, 2.2f);
        Vector3 c = { p.x + cosf(a)*r, 0, p.z + sinf(a)*r };
        c.y = GY(c.x, c.z) + 0.15f + RR(0.25f, 0.55f);
        Tube(M(TX_GRAIN), (Vector3){ c.x, c.y - 0.6f, c.z }, c, 0.04f, 0.04f, 3, (Color){ 60, 160, 50, 255 }, 1, 1, false, false);
        float s = RR(0.18f, 0.28f), r0 = RR(0, PI);
        for (int k = 0; k < 2; k++) {
            float t = r0 + k*PI*0.5f;
            Vector3 d = { cosf(t)*s, 0, sinf(t)*s };
            MB_QuadUV(M(TX_GRAIN), Vector3Subtract(c, d), (Vector3){ c.x - d.z, c.y + 0.02f, c.z + d.x }, Vector3Add(c, d), (Vector3){ c.x + d.z, c.y + 0.02f, c.z - d.x },
                      (Vector2){ 0, 0 }, (Vector2){ 1, 0 }, (Vector2){ 1, 1 }, (Vector2){ 0, 1 }, fc, (Vector3){ c.x, c.y - 5, c.z }, true);
        }
        Ball(M(TX_GRAIN), (Vector3){ c.x, c.y + 0.05f, c.z }, (Vector3){ 0.08f, 0.06f, 0.08f }, 3, 4, (Color){ 255, 220, 40, 255 }, 1);
    }
}
static void Rock(Vector3 p, float s, Color c, bool snowCap)
{
    At(p);
    Ellipsoid(M(TX_ROCK), (Vector3){ p.x, p.y + s*0.35f, p.z }, (Vector3){ s*1.3f, s*0.85f, s*1.1f }, Seg(6), Seg(9), ColorScale(c, 0.8f), c, 2, 1, 0.22f, srng);
    if (snowCap) Ellipsoid(M(TX_GRAIN), (Vector3){ p.x, p.y + s*0.85f, p.z }, (Vector3){ s*1.0f, s*0.35f, s*0.85f }, Seg(4), Seg(9), (Color){ 235, 240, 250, 255 }, WHITE, 1, 1, 0.15f, srng + 1);
}
static void Fence(Vector3 a, Vector3 b, Color c)
{
    At(a);
    float len = Vector3Distance(a, b);
    int posts = (int)(len/3.0f) + 1;
    float yaw = atan2f(b.x - a.x, b.z - a.z);
    for (int i = 0; i <= posts; i++) {
        Vector3 q = Vector3Lerp(a, b, (float)i/posts);
        q.y = GY(q.x, q.z);
        Box(M(TX_WOOD), (Vector3){ q.x, q.y + 0.75f, q.z }, (Vector3){ 0.22f, 1.5f, 0.22f }, yaw, c, 1.0f);
        if (i < posts) {
            Vector3 q2 = Vector3Lerp(a, b, (float)(i + 1)/posts); q2.y = GY(q2.x, q2.z);
            for (int r = 0; r < 2; r++) {
                float hy = 0.55f + r*0.55f;
                Vector3 m = Vector3Lerp(q, q2, 0.5f);
                float seg = Vector3Distance(q, q2);
                Box(M(TX_WOOD), (Vector3){ m.x, m.y + hy, m.z }, (Vector3){ 0.1f, 0.16f, seg }, yaw, c, 1.5f);
            }
        }
    }
}
static void House(Vector3 p, float yaw, Color wall, Color roof, float sc)
{
    At(p);
    float W = 8*sc, D = 6.5f*sc, H = 5.2f*sc;
    Box(M(TX_GRAIN), (Vector3){ p.x, p.y + H*0.5f, p.z }, (Vector3){ W, H, D }, yaw, wall, 3.0f);
    Box(M(TX_STONE), (Vector3){ p.x, p.y + 0.4f, p.z }, (Vector3){ W + 0.2f, 0.8f, D + 0.2f }, yaw, (Color){ 200, 195, 190, 255 }, 1.6f);
    /* roof: two sloped quads with overhang + gables */
    float ox = W*0.5f + 0.6f, oz = D*0.5f + 0.7f, rh = 3.4f*sc;
    Vector3 a = Rot(p, yaw, -ox, H, -oz), b = Rot(p, yaw, ox, H, -oz), c = Rot(p, yaw, ox, H, oz), d = Rot(p, yaw, -ox, H, oz);
    Vector3 r1 = Rot(p, yaw, -ox, H + rh, 0), r2 = Rot(p, yaw, ox, H + rh, 0);
    Vector3 ctr = { p.x, p.y + H, p.z };
    float ru = W/2.0f, rv = (oz*1.3f)/2.0f;
    MB_QuadUV(M(TX_ROOF), a, b, r2, r1, (Vector2){ 0, rv }, (Vector2){ ru, rv }, (Vector2){ ru, 0 }, (Vector2){ 0, 0 }, roof, ctr, true);
    MB_QuadUV(M(TX_ROOF), d, c, r2, r1, (Vector2){ 0, rv }, (Vector2){ ru, rv }, (Vector2){ ru, 0 }, (Vector2){ 0, 0 }, roof, ctr, true);
    Vector3 ga = Rot(p, yaw, -W*0.5f, H, -D*0.5f), gb = Rot(p, yaw, -W*0.5f, H, D*0.5f), gt = Rot(p, yaw, -W*0.5f, H + rh*0.85f, 0);
    MB_TriUV(M(TX_GRAIN), ga, gb, gt, (Vector2){ 0, 1 }, (Vector2){ 1, 1 }, (Vector2){ 0.5f, 0 }, wall, wall, wall, ctr, true);
    ga = Rot(p, yaw, W*0.5f, H, -D*0.5f); gb = Rot(p, yaw, W*0.5f, H, D*0.5f); gt = Rot(p, yaw, W*0.5f, H + rh*0.85f, 0);
    MB_TriUV(M(TX_GRAIN), ga, gb, gt, (Vector2){ 0, 1 }, (Vector2){ 1, 1 }, (Vector2){ 0.5f, 0 }, wall, wall, wall, ctr, true);
    /* chimney, door, windows with frames */
    Box(M(TX_STONE), Rot(p, yaw, W*0.28f, H + rh*0.7f, -oz*0.35f), (Vector3){ 0.9f, 2.4f, 0.9f }, yaw, (Color){ 210, 120, 100, 255 }, 1.0f);
    Box(M(TX_WOOD), Rot(p, yaw, 0, 1.25f*sc, D*0.5f + 0.06f), (Vector3){ 1.4f*sc, 2.5f*sc, 0.12f }, yaw, (Color){ 230, 170, 130, 255 }, 1.2f);
    for (int sd = -1; sd <= 1; sd += 2) for (int f = 0; f < 2; f++) {
        float z = f ? D*0.5f + 0.05f : -D*0.5f - 0.05f;
        Vector3 wc = Rot(p, yaw, sd*W*0.28f, H*0.58f, z);
        Box(M(TX_GRAIN), wc, (Vector3){ 1.5f*sc, 1.4f*sc, 0.14f }, yaw, WHITE, 2.0f);
        Box(M(TX_GRAIN), Rot(p, yaw, sd*W*0.28f, H*0.58f, z + (f ? 0.05f : -0.05f)), (Vector3){ 1.15f*sc, 1.05f*sc, 0.14f }, yaw, (Color){ 120, 190, 255, 255 }, 2.0f);
        Box(M(TX_WOOD), Rot(p, yaw, sd*W*0.28f, H*0.58f - 0.85f*sc, z + (f ? 0.2f : -0.2f)), (Vector3){ 1.6f*sc, 0.35f*sc, 0.4f }, yaw, (Color){ 200, 120, 80, 255 }, 1.0f);
    }
}
static void Windmill(Vector3 p, float yaw)
{
    At(p);
    Cyl(M(TX_STONE), p, 3.6f, 2.4f, 14, Seg(12), (Color){ 250, 245, 235, 255 }, 4, 5);
    Tube(M(TX_ROOF), (Vector3){ p.x, p.y + 14, p.z }, (Vector3){ p.x, p.y + 18.5f, p.z }, 3.0f, 0, Seg(12), (Color){ 230, 80, 60, 255 }, 4, 2, true, false);
    Box(M(TX_WOOD), Rot(p, yaw, 0, 1.4f, 3.4f), (Vector3){ 1.6f, 2.8f, 0.3f }, yaw, WHITE, 1.2f);
    Vector3 hub = Rot(p, yaw, 0, 13, 3.0f);
    Ball(M(TX_GRAIN), hub, (Vector3){ 0.6f, 0.6f, 0.6f }, 4, 6, (Color){ 90, 60, 40, 255 }, 1);
    float spin = RR(0, 1);
    for (int i = 0; i < 4; i++) {
        float a = i*PI*0.5f + spin;
        Vector3 dir = { cosf(a)*cosf(yaw), sinf(a), -cosf(a)*sinf(yaw) };
        Vector3 side = { sinf(yaw)*0.01f, 0, cosf(yaw)*0.01f };
        Vector3 w = Vector3Scale(Vector3Normalize(Vector3CrossProduct(dir, (Vector3){ sinf(yaw), 0, cosf(yaw) })), 1.5f);
        Vector3 e = Vector3Add(hub, Vector3Scale(dir, 9.5f));
        Tube(M(TX_WOOD), hub, e, 0.18f, 0.12f, 4, WHITE, 1, 3, false, false);
        Vector3 s0 = Vector3Add(Vector3Add(hub, Vector3Scale(dir, 1.6f)), side), s1 = Vector3Add(e, side);
        MB_QuadUV(M(TX_WOOD), s0, s1, Vector3Add(s1, w), Vector3Add(s0, w), (Vector2){ 0, 0 }, (Vector2){ 4, 0 }, (Vector2){ 4, 1 }, (Vector2){ 0, 1 },
                  (Color){ 255, 250, 240, 255 }, Vector3Subtract(hub, (Vector3){ sinf(yaw)*5, 0, cosf(yaw)*5 }), true);
    }
}
static void Cow(Vector3 p, float yaw)
{
    At(p);
    Color w = { 252, 252, 250, 255 }, k = { 40, 35, 40, 255 };
    Ellipsoid(M(TX_GRAIN), Rot(p, yaw, 0, 1.45f, 0), (Vector3){ 0.85f, 0.75f, 1.45f }, Seg(6), Seg(10), ColorScale(w, 0.9f), w, 1, 1, 0, 0);
    for (int i = 0; i < 4; i++) {
        float sx = (i & 1) ? 1 : -1;
        Ellipsoid(M(TX_GRAIN), Rot(p, yaw, sx*0.55f, 1.55f + RR(-0.2f, 0.2f), RR(-0.9f, 0.8f)), (Vector3){ 0.42f, 0.36f, 0.5f }, 4, 6, k, k, 1, 1, 0, 0);
        Tube(M(TX_GRAIN), Rot(p, yaw, sx*0.45f, 0.9f, (i & 2) ? 0.9f : -0.9f), Rot(p, yaw, sx*0.45f, 0, (i & 2) ? 0.9f : -0.9f), 0.17f, 0.15f, 5, w, 1, 1, false, true);
    }
    Vector3 hd = Rot(p, yaw, 0, 1.85f, 1.65f);
    Ellipsoid(M(TX_GRAIN), hd, (Vector3){ 0.48f, 0.5f, 0.6f }, Seg(5), Seg(8), w, w, 1, 1, 0, 0);
    Ellipsoid(M(TX_GRAIN), Rot(p, yaw, 0, 1.7f, 2.15f), (Vector3){ 0.42f, 0.3f, 0.25f }, 4, 7, (Color){ 255, 170, 180, 255 }, (Color){ 255, 190, 200, 255 }, 1, 1, 0, 0);
    for (int s = -1; s <= 1; s += 2) {
        Ball(M(TX_GRAIN), Rot(p, yaw, s*0.22f, 2.0f, 2.1f), (Vector3){ 0.09f, 0.09f, 0.09f }, 3, 5, k, 1);
        Tube(M(TX_GRAIN), Rot(p, yaw, s*0.3f, 2.25f, 1.55f), Rot(p, yaw, s*0.55f, 2.6f, 1.5f), 0.07f, 0.03f, 4, (Color){ 250, 240, 200, 255 }, 1, 1, false, false);
    }
}
static void HayBale(Vector3 p, float yaw)
{
    At(p);
    Vector3 a = Rot(p, yaw, -0.9f, 0.85f, 0), b = Rot(p, yaw, 0.9f, 0.85f, 0);
    Tube(M(TX_GRAIN), a, b, 0.85f, 0.85f, Seg(10), (Color){ 240, 205, 90, 255 }, 3, 1, true, true);
}
static void Balloon(Vector3 p)
{
    Far();
    Color c1 = HueColor(RR(0, 360), 0.75f, 1.0f), c2 = RR(0, 1) < 0.5f ? WHITE : HueColor(RR(0, 360), 0.7f, 1.0f);
    int sl = Seg(16), rg = Seg(10);
    MeshBuilder *mb = M(TX_GRAIN);
    float R = 5.5f;
    for (int i = 0; i < rg; i++) {
        float la0 = -PI*0.5f + PI*i/rg, la1 = -PI*0.5f + PI*(i + 1)/rg;
        float k0 = i == 0 ? 0.25f : 1.0f - 0.45f*fmaxf(0, -sinf(la0)), k1 = 1.0f - 0.45f*fmaxf(0, -sinf(la1));
        for (int j = 0; j < sl; j++) {
            float lo0 = 2*PI*j/sl, lo1 = 2*PI*(j + 1)/sl;
            Color c = (j & 1) ? c1 : c2;
            Vector3 n00 = { cosf(la0)*cosf(lo0), sinf(la0), cosf(la0)*sinf(lo0) }, n01 = { cosf(la0)*cosf(lo1), sinf(la0), cosf(la0)*sinf(lo1) };
            Vector3 n10 = { cosf(la1)*cosf(lo0), sinf(la1), cosf(la1)*sinf(lo0) }, n11 = { cosf(la1)*cosf(lo1), sinf(la1), cosf(la1)*sinf(lo1) };
            Vector3 p00 = { p.x + n00.x*R*k0, p.y + n00.y*R*1.2f, p.z + n00.z*R*k0 }, p01 = { p.x + n01.x*R*k0, p.y + n01.y*R*1.2f, p.z + n01.z*R*k0 };
            Vector3 p10 = { p.x + n10.x*R*k1, p.y + n10.y*R*1.2f, p.z + n10.z*R*k1 }, p11 = { p.x + n11.x*R*k1, p.y + n11.y*R*1.2f, p.z + n11.z*R*k1 };
            Vector2 z = { 0.5f, 0.5f };
            VL(mb, p00, z, n00, c); VL(mb, p11, z, n11, c); VL(mb, p01, z, n01, c);
            VL(mb, p00, z, n00, c); VL(mb, p10, z, n10, c); VL(mb, p11, z, n11, c);
        }
    }
    Vector3 bk = { p.x, p.y - R*1.2f - 2.6f, p.z };
    Box(M(TX_WOOD), bk, (Vector3){ 1.6f, 1.2f, 1.6f }, 0, (Color){ 230, 180, 120, 255 }, 1.0f);
    for (int k = 0; k < 4; k++) {
        float a = k*PI*0.5f + PI*0.25f;
        Tube(M(TX_GRAIN), (Vector3){ bk.x + cosf(a)*0.75f, bk.y + 0.6f, bk.z + sinf(a)*0.75f }, (Vector3){ p.x + cosf(a)*1.4f, p.y - R*1.08f, p.z + sinf(a)*1.4f }, 0.05f, 0.05f, 3, (Color){ 90, 70, 50, 255 }, 1, 1, false, false);
    }
}
static void Billboard(int i, int side, int sign, float extra)
{
    const TrackSample *s = &ST->s[i];
    float off = s->edge[side > 0 ? 1 : 0] + 3.5f + extra;
    Vector3 c = Vector3Add(s->pos, Vector3Scale(s->right, side*off));
    if (!ClearOfTrack(c.x, c.z, 3.0f)) return;
    c.y = ST->def->noGround ? s->pos.y : GY(c.x, c.z);
    At(c);
    Vector3 dir = side > 0 ? Vector3Negate(s->fwd) : s->fwd;
    Vector3 face = Vector3Scale(s->right, (float)-side);
    float w = 9.0f, h = 2.6f, y = 3.6f;
    for (int k = -1; k <= 1; k += 2) {
        Vector3 pp = Vector3Add(c, Vector3Scale(dir, k*w*0.38f));
        Box(M(TX_GRAIN), (Vector3){ pp.x, c.y + y*0.5f, pp.z }, (Vector3){ 0.3f, y, 0.3f }, 0, (Color){ 150, 150, 160, 255 }, 1.0f);
    }
    Board((Vector3){ c.x, c.y + y + h*0.5f, c.z }, dir, face, w, h, sign);
}
static void Chevron(int i)
{
    const TrackSample *s = &ST->s[i];
    int side = s->curv > 0 ? 1 : -1;                 /* outside of the bend */
    float off = s->edge[side > 0 ? 1 : 0] + 1.2f;
    Vector3 c = Vector3Add(s->pos, Vector3Scale(s->right, side*off));
    if (ST->def->noGround) c.y = s->pos.y; else c.y = fmaxf(GY(c.x, c.z), s->pos.y - 0.2f);
    At(c);
    Vector3 dir = side > 0 ? Vector3Negate(s->fwd) : s->fwd;
    Vector3 face = Vector3Scale(s->right, (float)-side);
    Box(M(TX_GRAIN), (Vector3){ c.x, c.y + 1.2f, c.z }, (Vector3){ 0.22f, 2.4f, 0.22f }, 0, (Color){ 120, 120, 130, 255 }, 1.0f);
    Board((Vector3){ c.x, c.y + 3.0f, c.z }, dir, face, 4.4f, 1.2f, side > 0 ? 6 : 5);
}
static void Grandstand(int i0, int side, float len)
{
    const TrackSample *s = &ST->s[i0];
    float depth = 9.0f, H = 6.5f;
    float off = s->edge[side > 0 ? 1 : 0] + 2.2f + depth*0.5f;
    Vector3 c = Vector3Add(s->pos, Vector3Scale(s->right, side*off));
    c.y = ST->def->noGround ? s->pos.y - 0.4f : fminf(GY(c.x, c.z), s->pos.y);
    float yaw = atan2f(s->right.x*-side, s->right.z*-side);        /* local +z faces the track */
    At(c);
    Vector3 a = Rot(c, yaw, -len*0.5f, 0.6f, depth*0.5f), b = Rot(c, yaw, len*0.5f, 0.6f, depth*0.5f);
    Vector3 bt = Rot(c, yaw, len*0.5f, H, -depth*0.5f), at = Rot(c, yaw, -len*0.5f, H, -depth*0.5f);
    float ur = len/7.0f;
    Vector3 out = Rot(c, yaw, 0, -10, -30);
    MB_QuadUV(M(TX_CROWD), a, b, bt, at, (Vector2){ 0, 1 }, (Vector2){ ur, 1 }, (Vector2){ ur, 0 }, (Vector2){ 0, 0 }, WHITE, out, true);
    /* body, side walls, back */
    Box(M(TX_GRAIN), Rot(c, yaw, 0, 0.3f, depth*0.5f + 0.2f), (Vector3){ len + 0.6f, 1.2f, 0.6f }, yaw, (Color){ 230, 60, 60, 255 }, 2.0f);
    Box(M(TX_GRAIN), Rot(c, yaw, 0, H*0.5f, -depth*0.5f - 0.3f), (Vector3){ len + 0.6f, H, 0.6f }, yaw, (Color){ 200, 200, 210, 255 }, 3.0f);
    for (int sd = -1; sd <= 1; sd += 2) {
        Vector3 p0 = Rot(c, yaw, sd*len*0.5f, 0, depth*0.5f), p1 = Rot(c, yaw, sd*len*0.5f, 0, -depth*0.5f), p2 = Rot(c, yaw, sd*len*0.5f, H, -depth*0.5f), p3 = Rot(c, yaw, sd*len*0.5f, 1.2f, depth*0.5f);
        MB_QuadUV(M(TX_GRAIN), p0, p1, p2, p3, (Vector2){ 0, 0 }, (Vector2){ 3, 0 }, (Vector2){ 3, 2 }, (Vector2){ 0, 1 }, (Color){ 210, 210, 220, 255 }, c, true);
    }
    /* striped roof on posts */
    int stripes = (int)(len/3.0f);
    for (int k = 0; k < stripes; k++) {
        float x0 = -len*0.5f + len*k/stripes, x1 = -len*0.5f + len*(k + 1)/stripes;
        Vector3 r0 = Rot(c, yaw, x0, H + 3.4f, -depth*0.5f), r1 = Rot(c, yaw, x1, H + 3.4f, -depth*0.5f);
        Vector3 r2 = Rot(c, yaw, x1, H + 2.4f, depth*0.5f + 1.0f), r3 = Rot(c, yaw, x0, H + 2.4f, depth*0.5f + 1.0f);
        MB_QuadUV(M(TX_GRAIN), r0, r1, r2, r3, (Vector2){ 0, 0 }, (Vector2){ 1, 0 }, (Vector2){ 1, 1 }, (Vector2){ 0, 1 }, (k & 1) ? WHITE : (Color){ 40, 110, 230, 255 }, Rot(c, yaw, 0, 0, 0), true);
    }
    for (int k = 0; k <= 3; k++) {
        float x = -len*0.5f + len*k/3.0f;
        Tube(M(TX_GRAIN), Rot(c, yaw, x, 0, depth*0.5f + 0.8f), Rot(c, yaw, x, H + 2.5f, depth*0.5f + 0.8f), 0.18f, 0.18f, 6, (Color){ 220, 220, 230, 255 }, 1, 1, false, false);
    }
    /* banner along the roof edge */
    Vector3 bc = Rot(c, yaw, 0, H + 1.6f, depth*0.5f + 1.05f);
    Vector3 dir = Vector3Normalize(Vector3Subtract(Rot(c, yaw, 1, 0, 0), Rot(c, yaw, 0, 0, 0)));
    Board(bc, dir, (Vector3){ sinf(yaw), 0, cosf(yaw) }, fminf(len*0.7f, 14.0f), 1.6f, 0);
}
static void Pennants(int i0, int count, int side)
{
    for (int k = 0; k < count; k++) {
        int i = (i0 + k*4) % ST->n;
        const TrackSample *s = &ST->s[i];
        Vector3 c = Vector3Add(s->pos, Vector3Scale(s->right, side*(s->edge[side > 0 ? 1 : 0] + 1.2f)));
        if (!ST->def->noGround) c.y = fmaxf(GY(c.x, c.z), s->pos.y - 0.3f);
        At(c);
        Tube(M(TX_GRAIN), c, (Vector3){ c.x, c.y + 5.5f, c.z }, 0.09f, 0.07f, 5, (Color){ 230, 230, 235, 255 }, 1, 1, false, true);
        Color fc = HueColor(k*47.0f, 0.75f, 1.0f);
        Vector3 t = { c.x, c.y + 5.4f, c.z }, m = { c.x, c.y + 4.4f, c.z };
        Vector3 tip = Vector3Add(Vector3Lerp(t, m, 0.5f), Vector3Scale(s->fwd, -1.8f));
        MB_TriUV(M(TX_GRAIN), t, m, tip, (Vector2){ 0, 0 }, (Vector2){ 0, 1 }, (Vector2){ 1, 0.5f }, fc, fc, ColorScale(fc, 0.85f), Vector3Add(c, s->right), true);
    }
}
static void Palm(Vector3 p, float s)
{
    At(p);
    float lean = RR(0, 2*PI), la = RR(0.12f, 0.3f);
    Vector3 b = p;
    for (int k = 0; k < 5; k++) {
        Vector3 t = { b.x + cosf(lean)*la*1.9f*s*(1 + k*0.2f), b.y + 1.9f*s, b.z + sinf(lean)*la*1.9f*s*(1 + k*0.2f) };
        Tube(M(TX_BARK), b, t, (0.5f - k*0.05f)*s, (0.44f - k*0.05f)*s, Seg(7), (Color){ 255, 235, 200, 255 }, 1, 1, false, false);
        Tube(M(TX_BARK), Vector3Lerp(b, t, 0.85f), t, (0.5f - k*0.05f)*s*1.08f, (0.44f - k*0.05f)*s, Seg(7), (Color){ 200, 170, 130, 255 }, 1, 0.2f, false, false);
        b = t;
    }
    int fr = 8;
    for (int k = 0; k < fr; k++) {
        float a = k*2*PI/fr + RR(-0.2f, 0.2f), droop = RR(0.8f, 1.4f);
        Color lc = Leaf(RR(95, 120), 0.7f, RR(0.75f, 1.0f));
        Vector3 prev = b; float wPrev = 0.2f*s;
        for (int sgi = 1; sgi <= 4; sgi++) {
            float t = sgi/4.0f;
            Vector3 q = { b.x + cosf(a)*5.2f*s*t, b.y + (1.2f*t - droop*2.6f*t*t)*s, b.z + sinf(a)*5.2f*s*t };
            float w = (sgi == 4 ? 0.1f : 1.0f - t*0.5f)*1.1f*s;
            Vector3 sd0 = { -sinf(a)*wPrev, 0, cosf(a)*wPrev }, sd1 = { -sinf(a)*w, 0, cosf(a)*w };
            Vector3 mid0 = prev, mid1 = q;
            MB_QuadUV(M(TX_LEAVES), Vector3Subtract(mid0, sd0), Vector3Subtract(mid1, sd1), Vector3Add(mid1, sd1), Vector3Add(mid0, sd0),
                      (Vector2){ 0, t - 0.25f }, (Vector2){ 0, t }, (Vector2){ 1, t }, (Vector2){ 1, t - 0.25f }, lc, (Vector3){ q.x, q.y - 10, q.z }, true);
            prev = q; wPrev = w;
        }
    }
    for (int k = 0; k < 3; k++) Ball(M(TX_GRAIN), (Vector3){ b.x + cosf(k*2.1f)*0.45f*s, b.y - 0.45f*s, b.z + sinf(k*2.1f)*0.45f*s }, (Vector3){ 0.35f*s, 0.35f*s, 0.35f*s }, 4, 6, (Color){ 130, 90, 50, 255 }, 1);
}
static void Umbrella(Vector3 p)
{
    At(p);
    Tube(M(TX_GRAIN), p, (Vector3){ p.x, p.y + 3.3f, p.z }, 0.1f, 0.1f, 5, WHITE, 1, 1, false, false);
    Color c1 = HueColor(RR(0, 360), 0.75f, 1.0f);
    int seg = Seg(12);
    for (int k = 0; k < seg; k++) {
        float a0 = k*2*PI/seg, a1 = (k + 1)*2*PI/seg;
        Vector3 top = { p.x, p.y + 3.9f, p.z };
        Vector3 e0 = { p.x + cosf(a0)*2.7f, p.y + 2.9f, p.z + sinf(a0)*2.7f }, e1 = { p.x + cosf(a1)*2.7f, p.y + 2.9f, p.z + sinf(a1)*2.7f };
        Color c = ((k*2/ (seg/4 > 0 ? seg/4 : 1)) & 1) ? c1 : WHITE;
        MB_TriUV(M(TX_GRAIN), top, e0, e1, (Vector2){ 0.5f, 0 }, (Vector2){ 0, 1 }, (Vector2){ 1, 1 }, c, c, c, (Vector3){ p.x, p.y, p.z }, true);
    }
    float ty = RR(0, 6.28f);
    Box(M(TX_GRAIN), Rot(p, ty, 1.7f, 0.08f, 0), (Vector3){ 1.3f, 0.06f, 2.7f }, ty, HueColor(RR(0, 360), 0.6f, 1.0f), 1.0f);
}
static void Hut(Vector3 p, float yaw)
{
    At(p);
    Box(M(TX_WOOD), (Vector3){ p.x, p.y + 1.9f, p.z }, (Vector3){ 5.5f, 3.8f, 4.5f }, yaw, (Color){ 255, 235, 210, 255 }, 2.0f);
    Tube(M(TX_ROOF), (Vector3){ p.x, p.y + 3.8f, p.z }, (Vector3){ p.x, p.y + 6.8f, p.z }, 4.6f, 0, Seg(10), (Color){ 240, 200, 110, 255 }, 5, 2, true, false);
    Box(M(TX_GRAIN), Rot(p, yaw, 0, 1.3f, 2.3f), (Vector3){ 1.3f, 2.4f, 0.1f }, yaw, HueColor(RR(0, 360), 0.6f, 0.9f), 1.0f);
}
static void Boat(Vector3 p)
{
    At(p);
    float yaw = RR(0, 6.28f);
    Color hull = HueColor(RR(0, 360), 0.55f, 0.95f);
    for (int k = 0; k < 2; k++) {
        float sd = k ? 1.0f : -1.0f;
        Vector3 a = Rot(p, yaw, sd*1.3f, 0.9f, -2.8f), b = Rot(p, yaw, sd*1.3f, 0.9f, 2.0f), c = Rot(p, yaw, 0, 0.9f, 3.6f);
        Vector3 a2 = Rot(p, yaw, sd*0.7f, -0.3f, -2.6f), b2 = Rot(p, yaw, sd*0.7f, -0.3f, 2.0f), c2 = Rot(p, yaw, 0, -0.3f, 3.2f);
        MB_QuadUV(M(TX_WOOD), a, b, b2, a2, (Vector2){ 0, 0 }, (Vector2){ 3, 0 }, (Vector2){ 3, 1 }, (Vector2){ 0, 1 }, hull, p, true);
        MB_QuadUV(M(TX_WOOD), b, c, c2, b2, (Vector2){ 0, 0 }, (Vector2){ 1, 0 }, (Vector2){ 1, 1 }, (Vector2){ 0, 1 }, hull, p, true);
    }
    Box(M(TX_WOOD), Rot(p, yaw, 0, 0.85f, -0.4f), (Vector3){ 2.4f, 0.1f, 4.6f }, yaw, (Color){ 230, 190, 140, 255 }, 1.5f);
    Vector3 mb = Rot(p, yaw, 0, 0.9f, 0.3f), mt = Rot(p, yaw, 0, 7.5f, 0.3f);
    Tube(M(TX_WOOD), mb, mt, 0.12f, 0.09f, 5, WHITE, 1, 2, false, false);
    Vector3 sb = Rot(p, yaw, 0, 1.6f, -2.4f);
    Color sc = RR(0, 1) < 0.5f ? WHITE : (Color){ 255, 90, 80, 255 };
    MB_TriUV(M(TX_GRAIN), Rot(p, yaw, 0, 7.2f, 0.25f), Rot(p, yaw, 0, 1.6f, 0.25f), sb, (Vector2){ 0, 0 }, (Vector2){ 0, 1 }, (Vector2){ 1, 1 }, sc, sc, sc, Rot(p, yaw, 3, 3, 0), true);
}
static void Lighthouse(Vector3 p)
{
    Far();
    for (int k = 0; k < 6; k++)
        Cyl(M(TX_STONE), (Vector3){ p.x, p.y + k*4.0f, p.z }, 4.0f - k*0.35f, 3.65f - k*0.35f, 4.0f, Seg(14), (k & 1) ? (Color){ 255, 255, 255, 255 } : (Color){ 235, 60, 55, 255 }, 5, 1);
    Cyl(M(TX_GRAIN), (Vector3){ p.x, p.y + 24, p.z }, 2.6f, 2.6f, 0.5f, Seg(12), (Color){ 60, 60, 70, 255 }, 1, 1);
    Cyl(M(TX_GRAIN), (Vector3){ p.x, p.y + 24.5f, p.z }, 2.0f, 2.0f, 2.2f, Seg(12), (Color){ 255, 245, 160, 255 }, 1, 1);
    Tube(M(TX_ROOF), (Vector3){ p.x, p.y + 26.7f, p.z }, (Vector3){ p.x, p.y + 29.5f, p.z }, 2.5f, 0, Seg(12), (Color){ 220, 40, 40, 255 }, 3, 1, true, false);
    Box(M(TX_WOOD), (Vector3){ p.x + 3.2f, p.y + 1.4f, p.z }, (Vector3){ 0.2f, 2.8f, 1.4f }, 0, WHITE, 1.2f);
}
static void Cactus(Vector3 p, float s)
{
    At(p);
    Color g = Leaf(RR(105, 130), 0.62f, RR(0.6f, 0.75f)), gt = ColorScale(g, 1.25f);
    Ellipsoid(M(TX_BARK), (Vector3){ p.x, p.y + 3.2f*s, p.z }, (Vector3){ 0.75f*s, 3.4f*s, 0.75f*s }, Seg(9), Seg(10), ColorMix(g, (Color){ 120, 255, 120, 255 }, 0.3f), gt, 6, 2, 0, 0);
    float a = RR(0, 2*PI);
    for (int i = 0; i < 2; i++) {
        float side = i ? 1.0f : -1.0f, h = (i ? 2.6f : 3.6f)*s;
        Vector3 e = { p.x + cosf(a)*side*1.55f*s, p.y + h, p.z + sinf(a)*side*1.55f*s };
        Tube(M(TX_BARK), (Vector3){ p.x, p.y + h, p.z }, e, 0.42f*s, 0.42f*s, Seg(7), ColorMix(g, (Color){ 120, 255, 120, 255 }, 0.3f), 2, 1, false, false);
        Ellipsoid(M(TX_BARK), (Vector3){ e.x, e.y + 1.0f*s, e.z }, (Vector3){ 0.44f*s, 1.3f*s, 0.44f*s }, Seg(6), Seg(8), ColorMix(g, (Color){ 120, 255, 120, 255 }, 0.3f), gt, 4, 1, 0, 0);
    }
    if (RR(0, 1) < 0.4f) Ball(M(TX_GRAIN), (Vector3){ p.x, p.y + 6.6f*s, p.z }, (Vector3){ 0.3f*s, 0.25f*s, 0.3f*s }, 3, 6, (Color){ 255, 90, 160, 255 }, 1);
}
static void Pyramid(Vector3 p, float s)
{
    Far();
    Tube(M(TX_STONE), (Vector3){ p.x, p.y - 0.5f, p.z }, (Vector3){ p.x, p.y + s*0.95f, p.z }, s, 0, 4, (Color){ 255, 220, 150, 255 }, s/3.0f, s/4.0f, false, false);
}
static void Tent(Vector3 p)
{
    At(p);
    Color c = HueColor(RR(0, 360), 0.65f, 1.0f);
    int seg = Seg(10);
    for (int k = 0; k < seg; k++) {
        float a0 = 2*PI*k/seg, a1 = 2*PI*(k + 1)/seg;
        Vector3 top = { p.x, p.y + 5, p.z }, e0 = { p.x + cosf(a0)*3.5f, p.y, p.z + sinf(a0)*3.5f }, e1 = { p.x + cosf(a1)*3.5f, p.y, p.z + sinf(a1)*3.5f };
        Color cc = (k & 1) ? c : WHITE;
        MB_TriUV(M(TX_GRAIN), top, e0, e1, (Vector2){ 0.5f, 0 }, (Vector2){ 0, 1 }, (Vector2){ 1, 1 }, cc, cc, cc, (Vector3){ p.x, p.y + 1, p.z }, true);
    }
    Tube(M(TX_GRAIN), (Vector3){ p.x, p.y + 5, p.z }, (Vector3){ p.x, p.y + 6.5f, p.z }, 0.06f, 0.06f, 3, (Color){ 90, 60, 40, 255 }, 1, 1, false, false);
    MB_TriUV(M(TX_GRAIN), (Vector3){ p.x, p.y + 6.5f, p.z }, (Vector3){ p.x, p.y + 5.9f, p.z }, (Vector3){ p.x + 1.1f, p.y + 6.2f, p.z }, (Vector2){ 0, 0 }, (Vector2){ 0, 1 }, (Vector2){ 1, 0.5f }, (Color){ 255, 60, 60, 255 }, (Color){ 255, 60, 60, 255 }, (Color){ 255, 60, 60, 255 }, (Vector3){ p.x, p.y + 6, p.z + 1 }, true);
}
static void Snowman(Vector3 p, float yaw)
{
    At(p);
    Color w = { 250, 252, 255, 255 }, b = { 225, 235, 250, 255 };
    Ellipsoid(M(TX_GRAIN), (Vector3){ p.x, p.y + 1.6f, p.z }, (Vector3){ 1.8f, 1.6f, 1.8f }, Seg(7), Seg(10), b, w, 1, 1, 0, 0);
    Ellipsoid(M(TX_GRAIN), (Vector3){ p.x, p.y + 4.0f, p.z }, (Vector3){ 1.3f, 1.2f, 1.3f }, Seg(7), Seg(10), b, w, 1, 1, 0, 0);
    Ellipsoid(M(TX_GRAIN), (Vector3){ p.x, p.y + 5.8f, p.z }, (Vector3){ 0.9f, 0.9f, 0.9f }, Seg(6), Seg(10), b, w, 1, 1, 0, 0);
    Tube(M(TX_GRAIN), Rot(p, yaw, 0, 5.8f, 0.8f), Rot(p, yaw, 0, 5.75f, 1.9f), 0.17f, 0, 6, (Color){ 255, 140, 30, 255 }, 1, 1, true, false);
    for (int s = -1; s <= 1; s += 2) Ball(M(TX_GRAIN), Rot(p, yaw, s*0.3f, 6.1f, 0.78f), (Vector3){ 0.1f, 0.1f, 0.1f }, 3, 5, (Color){ 30, 30, 40, 255 }, 1);
    for (int k = 0; k < 3; k++) Ball(M(TX_GRAIN), Rot(p, yaw, 0, 3.6f + k*0.5f, 1.22f - abs(k - 1)*0.08f), (Vector3){ 0.11f, 0.11f, 0.11f }, 3, 5, (Color){ 30, 30, 40, 255 }, 1);
    Cyl(M(TX_GRAIN), (Vector3){ p.x, p.y + 6.5f, p.z }, 0.65f, 0.65f, 1.0f, Seg(9), (Color){ 40, 40, 55, 255 }, 1, 1);
    Cyl(M(TX_GRAIN), (Vector3){ p.x, p.y + 6.5f, p.z }, 1.05f, 1.05f, 0.12f, Seg(9), (Color){ 40, 40, 55, 255 }, 1, 1);
    Tube(M(TX_GRAIN), (Vector3){ p.x, p.y + 4.95f, p.z }, (Vector3){ p.x, p.y + 5.3f, p.z }, 1.0f, 0.95f, Seg(10), (Color){ 230, 50, 50, 255 }, 2, 1, false, false);
    for (int s = -1; s <= 1; s += 2) Tube(M(TX_BARK), Rot(p, yaw, s*1.1f, 4.2f, 0), Rot(p, yaw, s*2.6f, 5.0f, 0), 0.09f, 0.05f, 4, WHITE, 1, 1, false, false);
}
static void Igloo(Vector3 p)
{
    At(p);
    Ellipsoid(M(TX_STONE), p, (Vector3){ 4.2f, 3.4f, 4.2f }, Seg(10), Seg(14), (Color){ 220, 235, 255, 255 }, WHITE, 6, 3, 0, 0);
    float yaw = FaceTrack(p);
    Tube(M(TX_STONE), Rot(p, yaw, 0, 1.0f, 3.2f), Rot(p, yaw, 0, 1.0f, 5.2f), 1.4f, 1.4f, Seg(10), (Color){ 235, 245, 255, 255 }, 2, 1, false, false);
    Box(M(TX_GRAIN), Rot(p, yaw, 0, 0.8f, 5.25f), (Vector3){ 1.6f, 1.6f, 0.05f }, yaw, (Color){ 40, 50, 80, 255 }, 1);
}
static void Cabin(Vector3 p, float yaw)
{
    At(p);
    Box(M(TX_WOOD), (Vector3){ p.x, p.y + 2.2f, p.z }, (Vector3){ 7, 4.4f, 5.5f }, yaw, (Color){ 220, 160, 110, 255 }, 1.6f);
    float ox = 4.1f, oz = 3.5f, H = 4.4f, rh = 3.0f;
    Vector3 a = Rot(p, yaw, -ox, H, -oz), b = Rot(p, yaw, ox, H, -oz), c = Rot(p, yaw, ox, H, oz), d = Rot(p, yaw, -ox, H, oz);
    Vector3 r1 = Rot(p, yaw, -ox, H + rh, 0), r2 = Rot(p, yaw, ox, H + rh, 0), ctr = { p.x, p.y + H, p.z };
    MB_QuadUV(M(TX_GRAIN), a, b, r2, r1, (Vector2){ 0, 1 }, (Vector2){ 3, 1 }, (Vector2){ 3, 0 }, (Vector2){ 0, 0 }, WHITE, ctr, true);
    MB_QuadUV(M(TX_GRAIN), d, c, r2, r1, (Vector2){ 0, 1 }, (Vector2){ 3, 1 }, (Vector2){ 3, 0 }, (Vector2){ 0, 0 }, WHITE, ctr, true);
    for (int s = -1; s <= 1; s += 2) {
        Vector3 ga = Rot(p, yaw, s*3.5f, H, -2.75f), gb = Rot(p, yaw, s*3.5f, H, 2.75f), gt = Rot(p, yaw, s*3.5f, H + rh*0.9f, 0);
        MB_TriUV(M(TX_WOOD), ga, gb, gt, (Vector2){ 0, 1 }, (Vector2){ 2, 1 }, (Vector2){ 1, 0 }, (Color){ 220, 160, 110, 255 }, (Color){ 220, 160, 110, 255 }, (Color){ 220, 160, 110, 255 }, ctr, true);
    }
    Box(M(TX_GRAIN), Rot(p, yaw, 0, 2.2f, 2.8f), (Vector3){ 1.4f, 1.3f, 0.1f }, yaw, (Color){ 255, 220, 120, 255 }, 1);
    Box(M(TX_STONE), Rot(p, yaw, 2.2f, H + 2.0f, -1.2f), (Vector3){ 0.9f, 2.6f, 0.9f }, yaw, (Color){ 190, 180, 180, 255 }, 1);
}
static void IceCrystal(Vector3 p, float s)
{
    At(p);
    Tube(M(TX_GRAIN), p, (Vector3){ p.x + RR(-0.5f, 0.5f), p.y + 6*s, p.z + RR(-0.5f, 0.5f) }, 1.0f*s, 0, 5, (Color){ 160, 225, 255, 255 }, 1, 1, false, false);
    Tube(M(TX_GRAIN), p, (Vector3){ p.x + 1.8f*s, p.y + 3.5f*s, p.z + 0.6f*s }, 0.6f*s, 0, 5, (Color){ 190, 240, 255, 255 }, 1, 1, false, false);
}
static void DeadTree(Vector3 p, float s)
{
    At(p);
    Color bark = { 150, 130, 150, 255 };
    Tube(M(TX_BARK), p, (Vector3){ p.x + RR(-0.4f, 0.4f), p.y + 7.2f*s, p.z + RR(-0.4f, 0.4f) }, 0.6f*s, 0.2f*s, Seg(7), bark, 2, 3, false, false);
    for (int k = 0; k < 5; k++) {
        float a = RR(0, 2*PI), h = RR(3.0f, 6.5f)*s, l = RR(1.8f, 3.4f)*s;
        Vector3 b = { p.x, p.y + h, p.z }, e = { p.x + cosf(a)*l, p.y + h + l*0.6f, p.z + sinf(a)*l };
        Tube(M(TX_BARK), b, e, 0.2f*s, 0.05f*s, 4, bark, 1, 1, false, false);
        Vector3 e2 = { e.x + cosf(a + 0.8f)*l*0.4f, e.y + l*0.35f, e.z + sinf(a + 0.8f)*l*0.4f };
        Tube(M(TX_BARK), e, e2, 0.07f*s, 0.02f*s, 3, bark, 1, 1, false, false);
    }
}
static void Grave(Vector3 p, float yaw)
{
    At(p);
    Color st = ColorFromHSV(RR(240, 280), 0.08f, RR(0.8f, 0.95f));
    if (RR(0, 1) < 0.6f) {
        Box(M(TX_STONE), (Vector3){ p.x, p.y + 1.0f, p.z }, (Vector3){ 1.4f, 2.0f, 0.4f }, yaw, st, 1.2f);
        Tube(M(TX_STONE), Rot(p, yaw, 0, 2.0f, -0.2f), Rot(p, yaw, 0, 2.0f, 0.2f), 0.7f, 0.7f, Seg(8), st, 1, 0.3f, true, true);
    } else {
        Box(M(TX_STONE), (Vector3){ p.x, p.y + 1.3f, p.z }, (Vector3){ 0.35f, 2.6f, 0.35f }, yaw, st, 1.0f);
        Box(M(TX_STONE), (Vector3){ p.x, p.y + 1.9f, p.z }, (Vector3){ 1.5f, 0.35f, 0.35f }, yaw, st, 1.0f);
    }
    Ellipsoid(M(TX_GRAIN), (Vector3){ p.x, p.y, p.z }, (Vector3){ 1.0f, 0.25f, 1.4f }, 4, 8, (Color){ 90, 110, 70, 255 }, (Color){ 110, 130, 80, 255 }, 1, 1, 0, 0);
}
static void Pumpkin(Vector3 p, float s)
{
    At(p);
    Color o = { 255, 135, 25, 255 }, od = { 220, 90, 10, 255 };
    for (int k = 0; k < 6; k++) {
        float a = k*PI/3;
        Ellipsoid(M(TX_GRAIN), (Vector3){ p.x + cosf(a)*0.42f*s, p.y + 0.8f*s, p.z + sinf(a)*0.42f*s }, (Vector3){ 0.7f*s, 0.8f*s, 0.7f*s }, Seg(6), Seg(8), od, o, 1, 1, 0, 0);
    }
    Tube(M(TX_GRAIN), (Vector3){ p.x, p.y + 1.5f*s, p.z }, (Vector3){ p.x + 0.15f*s, p.y + 2.0f*s, p.z }, 0.14f*s, 0.1f*s, 5, (Color){ 80, 130, 50, 255 }, 1, 1, false, true);
    float yaw = FaceTrack(p);
    Color glow = { 255, 240, 130, 255 };
    for (int e = -1; e <= 1; e += 2)
        MB_TriUV(M(TX_GRAIN), Rot(p, yaw, e*0.35f*s - 0.15f*s, 1.0f*s, 1.06f*s), Rot(p, yaw, e*0.35f*s + 0.15f*s, 1.0f*s, 1.06f*s), Rot(p, yaw, e*0.35f*s, 1.3f*s, 1.0f*s), (Vector2){ 0, 0 }, (Vector2){ 1, 0 }, (Vector2){ 0.5f, 1 }, glow, glow, glow, Rot(p, yaw, 0, 1, 0), false);
    MB_QuadUV(M(TX_GRAIN), Rot(p, yaw, -0.45f*s, 0.6f*s, 1.03f*s), Rot(p, yaw, 0.45f*s, 0.6f*s, 1.03f*s), Rot(p, yaw, 0.3f*s, 0.8f*s, 1.08f*s), Rot(p, yaw, -0.3f*s, 0.8f*s, 1.08f*s),
              (Vector2){ 0, 0 }, (Vector2){ 1, 0 }, (Vector2){ 1, 1 }, (Vector2){ 0, 1 }, glow, Rot(p, yaw, 0, 0.7f, 0), false);
}
static void Ghost(Vector3 p)
{
    At(p);
    Color w = { 235, 240, 255, 255 };
    float yaw = FaceTrack(p);
    Ellipsoid(M(TX_GRAIN), (Vector3){ p.x, p.y + 0.6f, p.z }, (Vector3){ 1.1f, 1.3f, 1.1f }, Seg(7), Seg(10), (Color){ 200, 210, 240, 255 }, w, 1, 1, 0, 0);
    Tube(M(TX_GRAIN), (Vector3){ p.x, p.y + 0.3f, p.z }, (Vector3){ p.x + 0.4f, p.y - 1.6f, p.z }, 1.05f, 0.05f, Seg(10), (Color){ 210, 220, 245, 255 }, 1, 1, false, false);
    for (int e = -1; e <= 1; e += 2) Ellipsoid(M(TX_GRAIN), Rot(p, yaw, e*0.35f, 0.9f, 0.95f), (Vector3){ 0.17f, 0.27f, 0.1f }, 4, 6, (Color){ 20, 20, 40, 255 }, (Color){ 20, 20, 40, 255 }, 1, 1, 0, 0);
    Ellipsoid(M(TX_GRAIN), Rot(p, yaw, 0, 0.35f, 1.0f), (Vector3){ 0.2f, 0.25f, 0.1f }, 4, 6, (Color){ 30, 20, 50, 255 }, (Color){ 30, 20, 50, 255 }, 1, 1, 0, 0);
    for (int a = -1; a <= 1; a += 2) Ellipsoid(M(TX_GRAIN), Rot(p, yaw, a*1.1f, 0.4f, 0.2f), (Vector3){ 0.45f, 0.25f, 0.25f }, 4, 6, w, w, 1, 1, 0, 0);
}
static void Lantern(Vector3 p)
{
    At(p);
    Tube(M(TX_GRAIN), p, (Vector3){ p.x, p.y + 4.2f, p.z }, 0.14f, 0.11f, 6, (Color){ 50, 45, 60, 255 }, 1, 1, false, false);
    Box(M(TX_GRAIN), (Vector3){ p.x, p.y + 4.55f, p.z }, (Vector3){ 0.75f, 0.85f, 0.75f }, 0.4f, (Color){ 255, 225, 120, 255 }, 1);
    Tube(M(TX_GRAIN), (Vector3){ p.x, p.y + 4.95f, p.z }, (Vector3){ p.x, p.y + 5.5f, p.z }, 0.6f, 0, 4, (Color){ 50, 45, 60, 255 }, 1, 1, true, false);
}
static void Tower(Vector3 base, float h, float r, Color stone, Color roof, bool windows)
{
    Cyl(M(TX_STONE), base, r, r*0.92f, h, Seg(12), stone, r*1.2f, h/3.0f);
    Cyl(M(TX_STONE), (Vector3){ base.x, base.y + h, base.z }, r*1.25f, r*1.25f, 1.2f, Seg(12), ColorScale(stone, 0.92f), r*1.5f, 0.5f);
    for (int k = 0; k < 8; k++) {   /* battlements */
        float a = k*PI/4;
        Box(M(TX_STONE), (Vector3){ base.x + cosf(a)*r*1.18f, base.y + h + 1.6f, base.z + sinf(a)*r*1.18f }, (Vector3){ 0.8f, 0.9f, 0.8f }, -a, stone, 1);
    }
    Tube(M(TX_ROOF), (Vector3){ base.x, base.y + h + 1.2f, base.z }, (Vector3){ base.x, base.y + h + 1.2f + r*2.6f, base.z }, r*1.05f, 0, Seg(12), roof, r*1.6f, r*0.8f, true, false);
    if (windows) {
        for (int i = 0; i < 4; i++) {
            float a = i*PI*0.5f + 0.3f;
            for (int j = 1; j < 4; j++) {
                float y = base.y + h - j*h*0.2f;
                if (y < base.y + 2) continue;
                Box(M(TX_GRAIN), (Vector3){ base.x + cosf(a)*(r*0.95f), y, base.z + sinf(a)*(r*0.95f) }, (Vector3){ 0.55f, 1.3f, 0.95f }, -a + PI*0.5f, (Color){ 255, 225, 110, 255 }, 1);
            }
        }
    }
}
static void Castle(Vector3 p, Color st, Color rf, float sc)
{
    Far();
    Box(M(TX_STONE), (Vector3){ p.x, p.y + 12*sc, p.z }, (Vector3){ 36*sc, 24*sc, 26*sc }, 0, st, 3.0f);
    for (int k = 0; k < 12; k++) {
        float x = -17*sc + k*3.1f*sc;
        Box(M(TX_STONE), (Vector3){ p.x + x, p.y + 24.6f*sc, p.z + 13*sc }, (Vector3){ 1.6f, 1.4f, 0.8f }, 0, st, 1);
        Box(M(TX_STONE), (Vector3){ p.x + x, p.y + 24.6f*sc, p.z - 13*sc }, (Vector3){ 1.6f, 1.4f, 0.8f }, 0, st, 1);
    }
    Tower((Vector3){ p.x - 18*sc, p.y, p.z - 13*sc }, 40*sc, 5*sc, st, rf, true);
    Tower((Vector3){ p.x + 18*sc, p.y, p.z - 13*sc }, 44*sc, 5*sc, st, rf, true);
    Tower((Vector3){ p.x - 18*sc, p.y, p.z + 13*sc }, 36*sc, 5*sc, st, rf, true);
    Tower((Vector3){ p.x + 18*sc, p.y, p.z + 13*sc }, 38*sc, 5*sc, st, rf, true);
    Tower((Vector3){ p.x, p.y + 10*sc, p.z }, 48*sc, 7*sc, st, ColorMix(rf, (Color){ 255, 200, 60, 255 }, 0.3f), true);
    for (int k = 0; k < 6; k++)   /* glowing windows on the keep */
        Box(M(TX_GRAIN), (Vector3){ p.x - 12*sc + k*4.8f*sc, p.y + 14*sc, p.z + 13.1f*sc }, (Vector3){ 1.2f, 2.6f, 0.2f }, 0, (Color){ 255, 220, 110, 255 }, 1);
    Box(M(TX_WOOD), (Vector3){ p.x, p.y + 4*sc, p.z + 13.15f*sc }, (Vector3){ 6*sc, 8*sc, 0.3f }, 0, (Color){ 160, 110, 80, 255 }, 2);
}
static void IronFence(Vector3 a, Vector3 b)
{
    At(a);
    float len = Vector3Distance(a, b);
    int n = (int)(len/1.2f);
    for (int i = 0; i <= n; i++) {
        Vector3 q = Vector3Lerp(a, b, (float)i/n); q.y = GY(q.x, q.z);
        Tube(M(TX_GRAIN), q, (Vector3){ q.x, q.y + 2.0f, q.z }, 0.06f, 0.06f, 4, (Color){ 50, 45, 60, 255 }, 1, 1, false, false);
        Tube(M(TX_GRAIN), (Vector3){ q.x, q.y + 2.0f, q.z }, (Vector3){ q.x, q.y + 2.35f, q.z }, 0.12f, 0, 4, (Color){ 60, 55, 70, 255 }, 1, 1, false, false);
    }
    Vector3 a2 = a, b2 = b; a2.y = GY(a.x, a.z); b2.y = GY(b.x, b.z);
    for (int r = 0; r < 2; r++) Tube(M(TX_GRAIN), (Vector3){ a2.x, a2.y + 0.5f + r*1.2f, a2.z }, (Vector3){ b2.x, b2.y + 0.5f + r*1.2f, b2.z }, 0.05f, 0.05f, 4, (Color){ 50, 45, 60, 255 }, 1, 1, false, false);
}
static void Star(Vector3 c, float s, Color col)
{
    At(c);
    float yaw = RR(0, 6.28f);
    Vector3 f = { sinf(yaw)*0.35f*s, 0, cosf(yaw)*0.35f*s };
    for (int k = 0; k < 10; k++) {
        float a0 = k*2*PI/10, a1 = (k + 1)*2*PI/10;
        float r0 = (k & 1) ? 0.45f*s : s, r1 = (k & 1) ? s : 0.45f*s;
        Vector3 rt = { cosf(yaw), 0, -sinf(yaw) };
        Vector3 p0 = { c.x + rt.x*sinf(a0)*r0, c.y + cosf(a0)*r0, c.z + rt.z*sinf(a0)*r0 };
        Vector3 p1 = { c.x + rt.x*sinf(a1)*r1, c.y + cosf(a1)*r1, c.z + rt.z*sinf(a1)*r1 };
        MB_TriUV(M(TX_GRAIN), Vector3Add(c, f), p0, p1, (Vector2){ 0.5f, 0.5f }, (Vector2){ 0, 0 }, (Vector2){ 1, 0 }, col, col, col, c, true);
        MB_TriUV(M(TX_GRAIN), Vector3Subtract(c, f), p0, p1, (Vector2){ 0.5f, 0.5f }, (Vector2){ 0, 0 }, (Vector2){ 1, 0 }, col, col, col, c, true);
    }
}
static void Planet(Vector3 c, float r, Color col)
{
    Far();
    Ellipsoid(M(TX_ROCK), c, (Vector3){ r, r, r }, Seg(12), Seg(18), ColorScale(col, 0.6f), col, 3, 2, 0.04f, srng);
    int seg = Seg(32);
    for (int k = 0; k < seg; k++) {
        float a0 = 2*PI*k/seg, a1 = 2*PI*(k + 1)/seg;
        Vector3 i0 = { c.x + cosf(a0)*r*1.4f, c.y + sinf(a0)*r*0.25f, c.z + sinf(a0)*r*1.4f }, i1 = { c.x + cosf(a1)*r*1.4f, c.y + sinf(a1)*r*0.25f, c.z + sinf(a1)*r*1.4f };
        Vector3 o0 = { c.x + cosf(a0)*r*2.0f, c.y + sinf(a0)*r*0.36f, c.z + sinf(a0)*r*2.0f }, o1 = { c.x + cosf(a1)*r*2.0f, c.y + sinf(a1)*r*0.36f, c.z + sinf(a1)*r*2.0f };
        Color rc = (k & 1) ? (Color){ 255, 220, 170, 255 } : (Color){ 230, 180, 220, 255 };
        MB_QuadUV(M(TX_GRAIN), i0, o0, o1, i1, (Vector2){ 0, 0 }, (Vector2){ 1, 0 }, (Vector2){ 1, 1 }, (Vector2){ 0, 1 }, rc, (Vector3){ c.x, c.y - 100, c.z }, false);
    }
}

/* ---------------------------------------------------------------- */
/* start gate: posts, checker band and a big banner                   */
/* ---------------------------------------------------------------- */
static void StartGate(void)
{
    const TrackSample *s = &ST->s[0];
    float hw = s->width*0.5f + 1.6f;
    Vector3 l = Vector3Add(s->pos, Vector3Scale(s->right, -hw)), r = Vector3Add(s->pos, Vector3Scale(s->right, hw));
    At(s->pos);
    Color pole = ST->def->night ? (Color){ 210, 210, 255, 255 } : (Color){ 245, 245, 250, 255 };
    for (int k = 0; k < 2; k++) {
        Vector3 b = k ? r : l;
        Tube(M(TX_GRAIN), b, (Vector3){ b.x, b.y + 9.2f, b.z }, 0.55f, 0.45f, Seg(10), pole, 2, 3, false, true);
        for (int q = 0; q < 4; q++) Tube(M(TX_GRAIN), (Vector3){ b.x, b.y + 1.5f + q*2.0f, b.z }, (Vector3){ b.x, b.y + 2.2f + q*2.0f, b.z }, 0.58f, 0.58f, Seg(10), (Color){ 230, 40, 40, 255 }, 1, 1, false, false);
    }
    Vector3 m = Vector3Lerp(l, r, 0.5f);
    float W = hw*2;
    /* banner seen by approaching karts (text runs along +right), and the back side */
    Board((Vector3){ m.x, m.y + 8.3f, m.z }, s->right, Vector3Negate(s->fwd), W*0.92f, 2.2f, ST->def->scenery == SCENERY_JUNGLE ? 31 : ST->def->followTerrain ? 27 : 0);
    Board((Vector3){ m.x + s->fwd.x*0.3f, m.y + 8.3f, m.z + s->fwd.z*0.3f }, Vector3Negate(s->right), s->fwd, W*0.92f, 2.2f, 8);
    Board((Vector3){ m.x, m.y + 6.6f, m.z }, s->right, Vector3Negate(s->fwd), W*0.92f, 1.0f, 7);
    /* light gantry */
    for (int k = 0; k < 5; k++) {
        Vector3 lp = Vector3Lerp(l, r, 0.3f + k*0.1f);
        Ball(M(TX_GRAIN), (Vector3){ lp.x - s->fwd.x*0.5f, lp.y + 9.75f, lp.z - s->fwd.z*0.5f }, (Vector3){ 0.32f, 0.32f, 0.32f }, 4, 6, k < 2 ? (Color){ 255, 60, 60, 255 } : k < 4 ? (Color){ 255, 220, 60, 255 } : (Color){ 80, 255, 90, 255 }, 1);
    }
    Box(M(TX_GRAIN), (Vector3){ m.x, m.y + 9.75f, m.z }, (Vector3){ W*0.5f, 0.5f, 0.5f }, atan2f(s->right.x, s->right.z) + PI*0.5f, (Color){ 60, 60, 70, 255 }, 1);
}

/* ---------------------------------------------------------------- */
/* per-track dressing                                                 */
/* ---------------------------------------------------------------- */
/* ---------------------------------------------------------------- */
/* Mudslide Megadome: indoor arena                                    */
/* ---------------------------------------------------------------- */
static void AQuad(Vector3 bl, Vector3 br, Vector3 tr, Vector3 tl, int region, Color c, Vector3 behind)
{
    Rectangle r = ArenaUV(region);
    MB_QuadUV(M(TX_ARENA), bl, br, tr, tl, (Vector2){ r.x, r.y + r.height }, (Vector2){ r.x + r.width, r.y + r.height },
              (Vector2){ r.x + r.width, r.y }, (Vector2){ r.x, r.y }, c, behind, true);
}
/* axis-aligned-in-yaw box with every face mapped to one atlas region */
static void ABox(Vector3 ctr, Vector3 size, float yaw, int region, Color c)
{
    Vector3 h = Vector3Scale(size, 0.5f), p[8];
    for (int i = 0; i < 8; i++) p[i] = Rot(ctr, yaw, (i & 1) ? h.x : -h.x, (i & 2) ? h.y : -h.y, (i & 4) ? h.z : -h.z);
    AQuad(p[0], p[1], p[3], p[2], region, c, ctr);
    AQuad(p[5], p[4], p[6], p[7], region, c, ctr);
    AQuad(p[4], p[0], p[2], p[6], region, c, ctr);
    AQuad(p[1], p[5], p[7], p[3], region, c, ctr);
    AQuad(p[2], p[3], p[7], p[6], region, ColorScale(c, 0.8f), ctr);
    AQuad(p[1], p[0], p[4], p[5], region, ColorScale(c, 0.6f), ctr);
}
/* a beam between two points with a square section, sides mapped to an atlas region */
static void ABeam(Vector3 a, Vector3 b, float w, int region, Color c)
{
    Vector3 ax = Vector3Subtract(b, a);
    float len = Vector3Length(ax);
    if (len < 1e-3f) return;
    Vector3 f = Vector3Scale(ax, 1.0f/len), u = Ortho(f), v = Vector3CrossProduct(f, u);
    Vector3 ctr = Vector3Lerp(a, b, 0.5f);
    for (int k = 0; k < 4; k++) {
        float t0 = PI*0.5f*k + PI*0.25f, t1 = t0 + PI*0.5f;
        Vector3 d0 = Vector3Scale(Vector3Add(Vector3Scale(u, cosf(t0)), Vector3Scale(v, sinf(t0))), w*0.7071f);
        Vector3 d1 = Vector3Scale(Vector3Add(Vector3Scale(u, cosf(t1)), Vector3Scale(v, sinf(t1))), w*0.7071f);
        int segs = (int)fmaxf(1, len/(w*2.0f));
        for (int sgi = 0; sgi < segs; sgi++) {
            Vector3 pa = Vector3Lerp(a, b, (float)sgi/segs), pb = Vector3Lerp(a, b, (float)(sgi + 1)/segs);
            AQuad(Vector3Add(pa, d0), Vector3Add(pb, d0), Vector3Add(pb, d1), Vector3Add(pa, d1), region, c, ctr);
        }
    }
}
static void LampBank(Vector3 c, Vector3 target, float w, float h)
{
    Track *tr = ST;
    Vector3 f = Vector3Normalize(Vector3Subtract(target, c));
    Vector3 r = Vector3Normalize(Vector3CrossProduct(f, (Vector3){ 0, 1, 0 }));
    Vector3 u = Vector3CrossProduct(r, f);
    Vector3 hr = Vector3Scale(r, w*0.5f), hu = Vector3Scale(u, h*0.5f);
    Vector3 behind = Vector3Subtract(c, f);
    AQuad(Vector3Subtract(Vector3Subtract(c, hr), hu), Vector3Subtract(Vector3Add(c, hr), hu), Vector3Add(Vector3Add(c, hr), hu), Vector3Add(Vector3Subtract(c, hr), hu), ARENA_LAMPS, WHITE, behind);
    ABox(Vector3Subtract(c, Vector3Scale(f, 0.5f)), (Vector3){ w + 0.4f, h + 0.4f, 0.8f }, atan2f(f.x, f.z), ARENA_TRUSS, (Color){ 120, 120, 130, 255 });
    if (tr->numLights < 48) tr->lights[tr->numLights++] = Vector3Add(c, Vector3Scale(f, 0.6f));
}

static void DressStadium(void)
{
    Track *tr = ST;
    int n = tr->n;
    const float M_ = STADIUM_MARGIN, plateau = STADIUM_RISE - 0.3f;
    float X0 = tr->mapMin.x - M_, X1 = tr->mapMax.x + M_, Z0 = tr->mapMin.y - M_, Z1 = tr->mapMax.y + M_;
    float wy0 = plateau - 0.8f, wy1 = plateau + 5.0f;          /* blue retaining wall */
    float sd = 30.0f, sh = 26.0f;                               /* stands: depth + rise */
    Vector3 ctr = { (X0 + X1)*0.5f, 0, (Z0 + Z1)*0.5f };
    Vector3 ic[4] = { { X0, 0, Z0 }, { X1, 0, Z0 }, { X1, 0, Z1 }, { X0, 0, Z1 } };      /* inner corners, clockwise from NW */
    Vector3 oc[4] = { { X0 - sd, 0, Z0 - sd }, { X1 + sd, 0, Z0 - sd }, { X1 + sd, 0, Z1 + sd }, { X0 - sd, 0, Z1 + sd } };
    tr->numLights = 0; tr->numFlashSpots = 0; tr->numJumbo = 0; tr->hasNeon = false;
    Color crowdC = { 205, 200, 220, 255 };
    for (int sdI = 0; sdI < 4; sdI++) {
        Vector3 a = ic[sdI], b = ic[(sdI + 1) % 4], oa = oc[sdI], ob = oc[(sdI + 1) % 4];
        float len = Vector3Distance(a, b);
        /* wall panels with the mascot */
        int panels = (int)(len/6.5f + 0.5f);
        for (int k = 0; k < panels; k++) {
            Vector3 p0 = Vector3Lerp(a, b, (float)k/panels), p1 = Vector3Lerp(a, b, (float)(k + 1)/panels);
            Vector3 mid = Vector3Lerp(p0, p1, 0.5f);
            At(mid);
            Vector3 out = Vector3Add(mid, Vector3Scale(Vector3Normalize(Vector3Subtract(mid, ctr)), 5.0f));
            out.y = (wy0 + wy1)*0.5f;
            AQuad((Vector3){ p0.x, wy0, p0.z }, (Vector3){ p1.x, wy0, p1.z }, (Vector3){ p1.x, wy1, p1.z }, (Vector3){ p0.x, wy1, p0.z }, ARENA_WALL, WHITE, out);
        }
        /* steep stands, mitred into the corners, in chunks */
        int segs = (int)(len/24.0f) + 1;
        for (int k = 0; k < segs; k++) {
            float t0 = (float)k/segs, t1 = (float)(k + 1)/segs;
            Vector3 i0 = Vector3Lerp(a, b, t0), i1 = Vector3Lerp(a, b, t1), o0 = Vector3Lerp(oa, ob, t0), o1 = Vector3Lerp(oa, ob, t1);
            i0.y = i1.y = wy1; o0.y = o1.y = wy1 + sh;
            At(Vector3Lerp(i0, o1, 0.5f));
            float ur = Vector3Distance(i0, i1)/26.0f;   /* ~1 unit per spectator, readable from the track */
            Vector3 below = Vector3Lerp(i0, o1, 0.5f); below.y -= 40;
            Vector3 bm = Vector3Lerp(i0, i1, 0.5f); bm = Vector3Add(bm, Vector3Scale(Vector3Normalize(Vector3Subtract(bm, ctr)), 30)); bm.y = wy1 - 10;
            MB_QuadUV(M(TX_CROWD), i0, i1, o1, o0, (Vector2){ 0, 6 }, (Vector2){ ur, 6 }, (Vector2){ ur, 0 }, (Vector2){ 0, 0 }, crowdC, bm, false);
            /* back wall above the top row */
            Vector3 o0t = { o0.x, o0.y + 7, o0.z }, o1t = { o1.x, o1.y + 7, o1.z };
            MB_QuadUV(M(TX_GRAIN), o0, o1, o1t, o0t, (Vector2){ 0, 1 }, (Vector2){ 4, 1 }, (Vector2){ 4, 0 }, (Vector2){ 0, 0 }, (Color){ 40, 44, 70, 255 }, Vector3Add(o0, Vector3Scale(Vector3Normalize(Vector3Subtract(o0, ctr)), 20)), true);
            /* wall cap */
            Vector3 c0 = Vector3Lerp(i0, o0, 0.03f), c1 = Vector3Lerp(i1, o1, 0.03f);
            c0.y = c1.y = wy1 + 0.02f;
            AQuad((Vector3){ i0.x, wy1 + 0.02f, i0.z }, (Vector3){ i1.x, wy1 + 0.02f, i1.z }, c1, c0, ARENA_CONCRETE, (Color){ 90, 140, 200, 255 }, (Vector3){ i0.x, wy1 - 20, i0.z });
        }
        /* camera-flash zones: two halves of each stand */
        for (int h2 = 0; h2 < 2 && tr->numFlashSpots < 8; h2++) {
            int q = tr->numFlashSpots++;
            Vector3 A = Vector3Lerp(a, b, h2*0.5f), B = Vector3Lerp(a, b, h2*0.5f + 0.5f), C = Vector3Lerp(oa, ob, h2*0.5f);
            A.y = B.y = wy1 + 0.6f; C.y = wy1 + sh + 0.6f;
            /* pull the far edge in so flashes stay on the slope */
            tr->flashA[q] = A; tr->flashB[q] = B; tr->flashC[q] = Vector3Lerp(A, C, 0.92f);
        }
        /* flood-light banks along the top of each stand */
        int banks = (int)(len/70.0f) + 1;
        for (int k = 0; k < banks; k++) {
            Vector3 p = Vector3Lerp(oa, ob, (k + 0.5f)/banks);
            p = Vector3Lerp(p, Vector3Lerp(a, b, (k + 0.5f)/banks), 0.08f);
            p.y = wy1 + sh + 12;
            Far();
            ABeam((Vector3){ p.x, wy1 + sh, p.z }, (Vector3){ p.x, p.y - 2, p.z }, 0.9f, ARENA_TRUSS, (Color){ 150, 150, 160, 255 });
            Vector3 tgt = { ctr.x + (p.x - ctr.x)*0.25f, 0, ctr.z + (p.z - ctr.z)*0.25f };
            LampBank(p, tgt, 9.0f, 4.5f);
        }
    }
    /* roof trusses with hanging lamp clusters */
    Far();
    for (int k = 0; k < 3; k++) {
        float x = X0 + (X1 - X0)*(k + 1)/4.0f, y = wy1 + sh + 24;
        ABeam((Vector3){ x, y, Z0 - sd }, (Vector3){ x, y, Z1 + sd }, 2.4f, ARENA_TRUSS, (Color){ 90, 92, 104, 255 });
        for (int j = 0; j < 2; j++) {
            float z = Z0 + (Z1 - Z0)*(j + 1)/3.0f;
            ABeam((Vector3){ x, y, z }, (Vector3){ x, y - 8, z }, 0.5f, ARENA_TRUSS, (Color){ 120, 120, 130, 255 });
            for (int q = 0; q < 4; q++) {
                float an = q*PI*0.5f + 0.4f;
                Vector3 lp = { x + cosf(an)*3.0f, y - 9.5f, z + sinf(an)*3.0f };
                LampBank(lp, (Vector3){ lp.x + cosf(an)*40, 0, lp.z + sinf(an)*40 }, 4.0f, 2.2f);
            }
        }
    }
    ABeam((Vector3){ X0 - sd, wy1 + sh + 24, ctr.z }, (Vector3){ X1 + sd, wy1 + sh + 24, ctr.z }, 2.4f, ARENA_TRUSS, (Color){ 90, 92, 104, 255 });
    /* two jumbotrons over the north and south stands */
    for (int j = 0; j < 2; j++) {
        float zf = j == 0 ? Z0 - sd*0.55f : Z1 + sd*0.55f;
        float face = j == 0 ? 1.0f : -1.0f;                     /* +z for the north screen */
        Vector3 c = { ctr.x, wy1 + sh*0.55f + 14, zf };
        float W = 36, H = 20;
        Far();
        ABox((Vector3){ c.x, c.y, c.z - face*1.0f }, (Vector3){ W + 3, H + 3, 1.6f }, 0, ARENA_WHITE, (Color){ 40, 90, 200, 255 });
        AQuad((Vector3){ c.x - face*14, c.y - H*0.5f - 6.5f, c.z + face*0.2f }, (Vector3){ c.x + face*14, c.y - H*0.5f - 6.5f, c.z + face*0.2f },
              (Vector3){ c.x + face*14, c.y - H*0.5f - 1.5f, c.z + face*0.2f }, (Vector3){ c.x - face*14, c.y - H*0.5f - 1.5f, c.z + face*0.2f }, ARENA_TITLE, WHITE, (Vector3){ c.x, c.y, c.z - face*5 });
        ABox((Vector3){ c.x, c.y - H*0.5f - 4.0f, c.z - face*0.6f }, (Vector3){ 29, 5.6f, 1.0f }, 0, ARENA_WHITE, (Color){ 30, 60, 150, 255 });
        for (int s2 = -1; s2 <= 1; s2 += 2)
            ABeam((Vector3){ c.x + s2*12, wy1 + sh*0.55f - 2, c.z - face*1.5f }, (Vector3){ c.x + s2*12, c.y - H*0.5f, c.z - face*1.5f }, 1.2f, ARENA_TRUSS, (Color){ 140, 140, 150, 255 });
        int q = tr->numJumbo++;
        tr->jumboC[q] = (Vector3){ c.x, c.y, c.z + face*0.25f };
        tr->jumboRight[q] = (Vector3){ face*W*0.5f, 0, 0 };
        tr->jumboUp[q] = (Vector3){ 0, H*0.5f, 0 };
    }
    /* start / finish truss: black TURBO TUMBLE 64 banner, chequered flags */
    {
        const TrackSample *s0 = &tr->s[0];
        float yaw = atan2f(s0->fwd.x, s0->fwd.z);
        float L = s0->edge[0] + 1.2f, R = s0->edge[1] + 1.2f, top = s0->pos.y + 8.0f;
        Vector3 pl = Vector3Add(s0->pos, Vector3Scale(s0->right, -L)), pr = Vector3Add(s0->pos, Vector3Scale(s0->right, R));
        At(s0->pos);
        for (int k = 0; k < 2; k++) {
            Vector3 b = k ? pr : pl;
            float g = fminf(GY(b.x, b.z), s0->pos.y) - 0.5f;
            ABox((Vector3){ b.x, (g + top + 1.0f)*0.5f, b.z }, (Vector3){ 1.6f, top + 1.0f - g, 1.6f }, yaw, ARENA_TRUSS, (Color){ 200, 200, 210, 255 });
            /* chequered flag hanging off each pillar, facing the grid */
            Vector3 fc = Vector3Add(b, Vector3Scale(s0->right, k ? -1.8f : 1.8f)); fc.y = top - 4.2f;
            for (int sdd = -1; sdd <= 1; sdd += 2) {
                Vector3 off = Vector3Scale(s0->fwd, sdd*0.03f);
                Vector3 hr = Vector3Scale(s0->right, 1.3f);
                Vector3 q0 = Vector3Add(Vector3Subtract(fc, hr), off), q1 = Vector3Add(Vector3Add(fc, hr), off);
                AQuad((Vector3){ q0.x, fc.y - 1.6f, q0.z }, (Vector3){ q1.x, fc.y - 1.6f, q1.z }, (Vector3){ q1.x, fc.y + 1.6f, q1.z }, (Vector3){ q0.x, fc.y + 1.6f, q0.z },
                      ARENA_CHEQUER, WHITE, Vector3Subtract(fc, Vector3Scale(s0->fwd, sdd*3.0f)));
            }
        }
        Vector3 bl = { pl.x, top, pl.z }, br = { pr.x, top, pr.z };
        ABeam(bl, br, 1.4f, ARENA_TRUSS, (Color){ 200, 200, 210, 255 });
        /* banner: black full width, with the text panel in the middle */
        float bw = L + R, mid = 0.5f*(R - L);
        float tw = fminf(16.0f, bw - 2), th = 4.0f;
        for (int sdd = -1; sdd <= 1; sdd += 2) {
            Vector3 off = Vector3Scale(s0->fwd, sdd*0.45f);
            Vector3 cc = Vector3Add(Vector3Add(s0->pos, Vector3Scale(s0->right, mid)), off); cc.y = top - 0.7f - th*0.5f;
            Vector3 hr = Vector3Scale(s0->right, tw*0.5f);
            Vector3 behind = Vector3Subtract(cc, Vector3Scale(s0->fwd, sdd*3.0f));
            /* text faces the approaching karts on the -fwd side; the back reads correctly too */
            Vector3 a0 = Vector3Subtract(cc, hr), a1 = Vector3Add(cc, hr);
            if (sdd < 0) AQuad((Vector3){ a0.x, cc.y - th*0.5f, a0.z }, (Vector3){ a1.x, cc.y - th*0.5f, a1.z }, (Vector3){ a1.x, cc.y + th*0.5f, a1.z }, (Vector3){ a0.x, cc.y + th*0.5f, a0.z }, ARENA_BANNER, WHITE, behind);
            else AQuad((Vector3){ a1.x, cc.y - th*0.5f, a1.z }, (Vector3){ a0.x, cc.y - th*0.5f, a0.z }, (Vector3){ a0.x, cc.y + th*0.5f, a0.z }, (Vector3){ a1.x, cc.y + th*0.5f, a1.z }, ARENA_BANNER, WHITE, behind);
            /* black wings out to the pillars */
            Vector3 w0 = Vector3Add(pl, off), w1 = Vector3Add(pr, off);
            for (int k = 0; k < 2; k++) {
                Vector3 e0 = k ? a1 : w0, e1 = k ? w1 : a0;
                AQuad((Vector3){ e0.x, cc.y - th*0.5f, e0.z }, (Vector3){ e1.x, cc.y - th*0.5f, e1.z }, (Vector3){ e1.x, cc.y + th*0.5f, e1.z }, (Vector3){ e0.x, cc.y + th*0.5f, e0.z }, ARENA_WHITE, (Color){ 14, 14, 16, 255 }, behind);
            }
        }
    }
    /* neon "BIG AIR" gantry with a yellow arrow before the big jump */
    {
        int kick = -1;
        for (int i = 0; i < n; i++) if (tr->s[i].ramp && tr->s[i].pos.y > 3) { kick = i; break; }
        if (kick >= 0) {
            int gi = (kick - 18 + n) % n;
            const TrackSample *g = &tr->s[gi];
            float yaw = atan2f(g->fwd.x, g->fwd.z);
            float L = g->edge[0] + 1.0f, R = g->edge[1] + 1.0f, top = g->pos.y + 9.0f;
            At(g->pos);
            for (int k = 0; k < 2; k++) {
                Vector3 b = Vector3Add(g->pos, Vector3Scale(g->right, k ? R : -L));
                float gy = fminf(GY(b.x, b.z), g->pos.y) - 0.5f;
                ABox((Vector3){ b.x, (gy + top)*0.5f, b.z }, (Vector3){ 1.2f, top - gy, 1.2f }, yaw, ARENA_STRIPES, WHITE);
            }
            Vector3 cc = Vector3Add(g->pos, Vector3Scale(g->right, 0.5f*(R - L)));
            cc.y = top - 2.6f;
            float sw = 18.0f, shh = 4.5f;
            ABox(cc, (Vector3){ L + R + 1.2f, shh + 0.8f, 0.8f }, yaw, ARENA_WHITE, (Color){ 30, 26, 40, 255 });
            Vector3 face = Vector3Scale(g->fwd, -0.45f);
            Vector3 sc = Vector3Add(cc, face);
            Vector3 hr = Vector3Scale(g->right, -sw*0.5f);         /* reads left-to-right for oncoming karts */
            Vector3 p0 = Vector3Add(sc, hr), p1 = Vector3Subtract(sc, hr);
            AQuad((Vector3){ p0.x, sc.y - shh*0.5f, p0.z }, (Vector3){ p1.x, sc.y - shh*0.5f, p1.z }, (Vector3){ p1.x, sc.y + shh*0.5f, p1.z }, (Vector3){ p0.x, sc.y + shh*0.5f, p0.z },
                  ARENA_NEON, WHITE, cc);
            tr->hasNeon = true;
            tr->neonC = Vector3Add(sc, Vector3Scale(g->fwd, -0.05f));
            tr->neonRight = Vector3Scale(g->right, sw*0.5f);
            tr->neonUp = (Vector3){ 0, shh*0.5f, 0 };
            (void)p0;
        }
    }
    /* advertising boards on the infield, facing the course */
    Vector3 p;
    for (int i = 0; i < 10; i++) if (Spot(STADIUM_BANK_W + 1, STADIUM_BANK_W + 9, 5, &p)) {
        if (p.y < plateau - 0.5f) continue;
        float yaw = FaceTrack(p);
        At(p);
        Vector3 c = { p.x, p.y + 2.2f, p.z };
        Vector3 dir = { cosf(yaw), 0, -sinf(yaw) }, fc = { sinf(yaw), 0, cosf(yaw) };
        Vector3 hr = Vector3Scale(dir, 6.0f), f = Vector3Add(c, Vector3Scale(fc, 0.3f));
        AQuad(Vector3Add(Vector3Subtract(f, hr), (Vector3){ 0, -1.5f, 0 }), Vector3Add(Vector3Add(f, hr), (Vector3){ 0, -1.5f, 0 }),
              Vector3Add(Vector3Add(f, hr), (Vector3){ 0, 1.5f, 0 }), Vector3Add(Vector3Subtract(f, hr), (Vector3){ 0, 1.5f, 0 }), (i % 3) ? ARENA_AD : ARENA_TITLE, WHITE, Vector3Subtract(c, fc));
        ABox(c, (Vector3){ 12.4f, 3.4f, 0.5f }, yaw, ARENA_WHITE, (Color){ 60, 60, 70, 255 });
        ABox((Vector3){ p.x, p.y + 0.3f, p.z }, (Vector3){ 0.4f, 0.9f, 0.4f }, yaw, ARENA_WHITE, (Color){ 60, 60, 70, 255 });
    }
    TraceLog(LOG_INFO, "STADIUM: %d lamps, %d jumbotrons, neon %d, arena %.0fx%.0f", tr->numLights, tr->numJumbo, tr->hasNeon, X1 - X0, Z1 - Z0);
}

/* ---------------------------------------------------------------- */
/* v7 courses: Grand Tumble Raceway, Canopy River Parkway,           */
/* Shellby Shores, Clover Creek Farm                                 */
/* ---------------------------------------------------------------- */
static Vector3 Beside(int i, int side, float off)
{
    const TrackSample *s = &ST->s[((i % ST->n) + ST->n) % ST->n];
    Vector3 p = Vector3Add(s->pos, Vector3Scale(s->right, side*(s->edge[side > 0 ? 1 : 0] + off)));
    p.y = GY(p.x, p.z);
    return p;
}
static bool InZone(int i, int flags) { return (ST->s[((i % ST->n) + ST->n) % ST->n].zone & flags) != 0; }

/* the Tumble mascot's crash helmet as a building roof, with a shop below */
static void HelmetHouse(Vector3 p, float yaw)
{
    At(p);
    Cyl(M(TX_GRAIN), p, 7.0f, 7.0f, 6.0f, Seg(16), (Color){ 250, 246, 236, 255 }, 6, 2);
    for (int k = 0; k < 6; k++) {   /* windows */
        float a = yaw + k*PI/3 + 0.5f;
        Box(M(TX_GRAIN), (Vector3){ p.x + sinf(a)*7.02f, p.y + 3.4f, p.z + cosf(a)*7.02f }, (Vector3){ 2.0f, 1.8f, 0.15f }, a, (Color){ 120, 190, 255, 255 }, 1);
    }
    Box(M(TX_WOOD), Rot(p, yaw, 0, 1.3f, 7.0f), (Vector3){ 2.2f, 2.6f, 0.3f }, yaw, (Color){ 220, 60, 50, 255 }, 1);
    Vector3 c = { p.x, p.y + 6.0f, p.z };
    Ellipsoid(M(TX_GRAIN), c, (Vector3){ 8.2f, 7.0f, 8.2f }, Seg(8), Seg(16), (Color){ 200, 30, 36, 255 }, (Color){ 240, 50, 50, 255 }, 1, 1, 0, 0);
    Cyl(M(TX_GRAIN), (Vector3){ p.x, p.y + 5.6f, p.z }, 8.8f, 8.8f, 0.8f, Seg(16), (Color){ 250, 250, 250, 255 }, 1, 1);   /* white brim stripe */
    /* goggles on the front */
    for (int sd = -1; sd <= 1; sd += 2) {
        Vector3 g = Rot(p, yaw, sd*2.6f, 10.2f, 6.2f);
        Ball(M(TX_GRAIN), g, (Vector3){ 1.8f, 1.5f, 0.9f }, 5, 8, (Color){ 40, 40, 48, 255 }, 1);
        Ball(M(TX_GRAIN), Rot(p, yaw, sd*2.6f, 10.2f, 6.9f), (Vector3){ 1.3f, 1.05f, 0.5f }, 5, 8, (Color){ 140, 220, 255, 255 }, 1);
    }
    Box(M(TX_GRAIN), Rot(p, yaw, 0, 12.6f, 5.4f), (Vector3){ 2.6f, 1.4f, 0.3f }, yaw, (Color){ 255, 210, 40, 255 }, 1);   /* 64 badge */
    /* rooftop billboard on a mast */
    Vector3 m = Rot(p, yaw, 0, 13.0f, 0);
    Tube(M(TX_GRAIN), m, (Vector3){ m.x, m.y + 3.0f, m.z }, 0.2f, 0.2f, 6, (Color){ 160, 160, 170, 255 }, 1, 1, false, false);
    Vector3 face = { sinf(yaw), 0, cosf(yaw) }, dir = { cosf(yaw), 0, -sinf(yaw) };
    Board((Vector3){ m.x, m.y + 4.6f, m.z }, Vector3Negate(dir), face, 10.0f, 2.8f, 27);
}

/* a hot-air balloon shaped like the Tumble mascot's head */
static void MascotBalloon(Vector3 p)
{
    Far();
    Ellipsoid(M(TX_GRAIN), (Vector3){ p.x, p.y + 2.0f, p.z }, (Vector3){ 8.0f, 6.5f, 8.0f }, Seg(8), Seg(16), (Color){ 200, 30, 36, 255 }, (Color){ 240, 52, 52, 255 }, 1, 1, 0, 0);
    Ellipsoid(M(TX_GRAIN), (Vector3){ p.x, p.y - 2.2f, p.z }, (Vector3){ 7.4f, 5.6f, 7.4f }, Seg(8), Seg(16), (Color){ 250, 210, 170, 255 }, (Color){ 255, 226, 190, 255 }, 1, 1, 0, 0);
    for (int sd = -1; sd <= 1; sd += 2) {
        Ball(M(TX_GRAIN), (Vector3){ p.x + sd*2.8f, p.y + 1.0f, p.z + 6.6f }, (Vector3){ 2.0f, 1.6f, 1.0f }, 5, 8, (Color){ 40, 40, 48, 255 }, 1);
        Ball(M(TX_GRAIN), (Vector3){ p.x + sd*2.8f, p.y + 1.0f, p.z + 7.3f }, (Vector3){ 1.4f, 1.1f, 0.5f }, 5, 8, (Color){ 140, 220, 255, 255 }, 1);
    }
    Box(M(TX_GRAIN), (Vector3){ p.x, p.y - 3.4f, p.z + 6.9f }, (Vector3){ 5.0f, 0.7f, 0.4f }, 0, (Color){ 255, 255, 255, 255 }, 1);   /* grin */
    Box(M(TX_GRAIN), (Vector3){ p.x, p.y + 5.6f, p.z + 5.0f }, (Vector3){ 2.6f, 1.3f, 0.4f }, 0, (Color){ 255, 210, 40, 255 }, 1);  /* 64 badge */
    Vector3 bk = { p.x, p.y - 12.0f, p.z };
    Box(M(TX_WOOD), bk, (Vector3){ 2.4f, 1.6f, 2.4f }, 0, (Color){ 190, 140, 90, 255 }, 1);
    for (int k = 0; k < 4; k++) {
        float a = k*PI*0.5f + PI*0.25f;
        Tube(M(TX_GRAIN), (Vector3){ bk.x + cosf(a)*1.1f, bk.y + 0.8f, bk.z + sinf(a)*1.1f }, (Vector3){ p.x + cosf(a)*4.0f, p.y - 6.5f, p.z + sinf(a)*4.0f }, 0.06f, 0.06f, 3, (Color){ 90, 70, 50, 255 }, 1, 1, false, false);
    }
}

static void JungleTree(Vector3 p, float s)
{
    At(p);
    float h = RR(9, 14)*s;
    Tube(M(TX_BARK), p, (Vector3){ p.x + RR(-0.8f, 0.8f), p.y + h, p.z + RR(-0.8f, 0.8f) }, 0.75f*s, 0.45f*s, Seg(7), (Color){ 200, 180, 160, 255 }, 1, 3, false, false);
    float hue = RR(95, 125);
    for (int q = 0; q < 4; q++) {
        float a = RR(0, 2*PI), rr = q ? RR(1.5f, 3.0f)*s : 0;
        Ellipsoid(M(TX_LEAVES), (Vector3){ p.x + cosf(a)*rr, p.y + h + RR(-1.0f, 1.2f)*s, p.z + sinf(a)*rr }, (Vector3){ 3.6f*s, 1.7f*s, 3.6f*s }, Seg(5), Seg(9),
                  Leaf(hue, 0.8f, 0.32f), Leaf(hue - 8, 0.7f, 0.72f), 3, 1, 0.15f, srng + q);
    }
}
static void Fern(Vector3 p, float s)
{
    At(p);
    float hue = RR(90, 120);
    for (int k = 0; k < 7; k++) {
        float a = k*2*PI/7 + RR(-0.3f, 0.3f);
        Vector3 t = { p.x + cosf(a)*2.4f*s, p.y + 1.6f*s, p.z + sinf(a)*2.4f*s };
        Vector3 w = { -sinf(a)*0.45f*s, 0, cosf(a)*0.45f*s };
        MB_QuadUV(M(TX_LEAVES), Vector3Subtract(p, w), Vector3Add(p, w), Vector3Add(t, w), Vector3Subtract(t, w), (Vector2){ 0, 0 }, (Vector2){ 1, 0 }, (Vector2){ 1, 1 }, (Vector2){ 0, 1 },
                  Leaf(hue, 0.75f, RR(0.5f, 0.8f)), (Vector3){ p.x, p.y - 5, p.z }, true);
    }
}
/* deep grass clump (the monkeys hide in these) */
static void GrassClump(Vector3 p, float s)
{
    At(p);
    for (int k = 0; k < 9; k++) {
        float a = RR(0, 2*PI), r = RR(0, 1.4f)*s;
        Vector3 b = { p.x + cosf(a)*r, p.y, p.z + sinf(a)*r };
        Vector3 t = { b.x + RR(-0.5f, 0.5f), b.y + RR(1.4f, 2.4f)*s, b.z + RR(-0.5f, 0.5f) };
        Vector3 w = { RR(-0.3f, 0.3f), 0, RR(-0.3f, 0.3f) };
        MB_TriUV(M(TX_LEAVES), Vector3Subtract(b, w), Vector3Add(b, w), t, (Vector2){ 0, 1 }, (Vector2){ 1, 1 }, (Vector2){ 0.5f, 0 },
                 Leaf(100, 0.7f, 0.35f), Leaf(100, 0.7f, 0.35f), Leaf(85, 0.6f, 0.85f), (Vector3){ b.x, b.y - 5, b.z }, false);
    }
}
static void Barn(Vector3 p, float yaw)
{
    At(p);
    float W = 14, D = 20, H = 7;
    Color red = { 196, 40, 34, 255 }, trim = { 250, 248, 240, 255 };
    Box(M(TX_WOOD), (Vector3){ p.x, p.y + H*0.5f, p.z }, (Vector3){ W, H, D }, yaw, red, 4.0f);
    /* gambrel roof */
    float xs[5] = { -W*0.5f - 0.6f, -W*0.36f, 0, W*0.36f, W*0.5f + 0.6f }, ys[5] = { H, H + 3.4f, H + 5.6f, H + 3.4f, H };
    for (int k = 0; k < 4; k++) {
        Vector3 a = Rot(p, yaw, xs[k], ys[k], -D*0.5f - 0.6f), b = Rot(p, yaw, xs[k + 1], ys[k + 1], -D*0.5f - 0.6f);
        Vector3 c = Rot(p, yaw, xs[k + 1], ys[k + 1], D*0.5f + 0.6f), d = Rot(p, yaw, xs[k], ys[k], D*0.5f + 0.6f);
        MB_QuadUV(M(TX_ROOF), a, b, c, d, (Vector2){ 0, 0 }, (Vector2){ 1, 0 }, (Vector2){ 1, 4 }, (Vector2){ 0, 4 }, (Color){ 120, 110, 110, 255 }, Rot(p, yaw, 0, H, 0), true);
    }
    for (int f = -1; f <= 1; f += 2) {
        float z = f*D*0.5f;
        Vector3 ctr = Rot(p, yaw, 0, H + 1, 0);
        for (int k = 0; k < 4; k++)
            MB_TriUV(M(TX_WOOD), Rot(p, yaw, xs[k]*0.92f, ys[k] > H ? ys[k] : H, z), Rot(p, yaw, xs[k + 1]*0.92f, ys[k + 1] > H ? ys[k + 1] : H, z), Rot(p, yaw, 0, H, z),
                     (Vector2){ 0, 0 }, (Vector2){ 1, 0 }, (Vector2){ 0.5f, 1 }, red, red, red, ctr, true);
        Box(M(TX_WOOD), Rot(p, yaw, 0, 2.6f, z + f*0.1f), (Vector3){ 5.0f, 5.2f, 0.2f }, yaw, ColorScale(red, 0.85f), 1);
        for (int dg = -1; dg <= 1; dg += 2) {   /* white X on the doors */
            Vector3 a = Rot(p, yaw, -2.4f, 0.2f + (dg > 0 ? 0 : 5.0f), z + f*0.25f), b = Rot(p, yaw, 2.4f, 0.2f + (dg > 0 ? 5.0f : 0), z + f*0.25f);
            Tube(M(TX_GRAIN), a, b, 0.14f, 0.14f, 4, trim, 1, 1, false, false);
        }
        Box(M(TX_GRAIN), Rot(p, yaw, 0, H + 2.0f, z + f*0.12f), (Vector3){ 2.0f, 1.8f, 0.2f }, yaw, trim, 1);
    }
}
static void Silo(Vector3 p)
{
    At(p);
    Cyl(M(TX_STONE), p, 3.2f, 3.2f, 17, Seg(14), (Color){ 220, 220, 228, 255 }, 4, 5);
    Ellipsoid(M(TX_GRAIN), (Vector3){ p.x, p.y + 17, p.z }, (Vector3){ 3.3f, 2.6f, 3.3f }, Seg(5), Seg(12), (Color){ 170, 175, 185, 255 }, (Color){ 210, 215, 225, 255 }, 1, 1, 0, 0);
    for (int k = 0; k < 4; k++) Cyl(M(TX_GRAIN), (Vector3){ p.x, p.y + 3 + k*4.0f, p.z }, 3.32f, 3.32f, 0.3f, Seg(14), (Color){ 120, 120, 130, 255 }, 1, 1);
}

static void DressV7(void)
{
    const TrackDef *d = ST->def;
    int n = ST->n;
    Vector3 p;
    ST->hasLandmark = false;
    switch (d->scenery) {
    default: break;
    case SCENERY_RACEWAY: {
        for (int i = 0; i < 200; i++) if (Spot(4, 70, 3, &p) && Dry(p)) { float r = RR(0, 1); if (r < 0.6f) Pine(p, RR(0.9f, 1.5f), false); else Oak(p, RR(0.8f, 1.3f)); }
        for (int i = 0; i < 50; i++) if (Spot(1, 25, 2, &p) && Dry(p)) Bush(p, RR(0.6f, 1.0f));
        /* grandstands down the right of the final straight, lake on the left */
        for (int k = 0; k < 4; k++) Grandstand((int)((0.79f + k*0.05f)*n), 1, 30.0f);
        for (int k = 0; k < 5; k++) Billboard((int)((0.80f + k*0.04f)*n), -1, (k & 1) ? 17 : 16, 1.0f);
        /* airline / sponsor boards round the sweepers */
        for (int k = 0; k < 6; k++) Billboard((int)((0.07f + k*0.028f)*n), 1, (k & 1) ? 16 : 25, 2.0f);
        for (int k = 0; k < 4; k++) Billboard((int)((0.50f + k*0.05f)*n), 1, (k & 1) ? 17 : 27, 2.0f);
        /* the helmet-roof building with its billboard, inside the first sweeper */
        { int i = (int)(0.15f*n); p = Beside(i, -1, 24.0f); if (ClearOfTrack(p.x, p.z, 9)) HelmetHouse(p, FaceTrack(p)); }
        /* the red-roofed castle on a hill after the tunnel */
        { int i = (int)(0.42f*n); p = Beside(i, 1, 85.0f); Castle(p, (Color){ 236, 228, 214, 255 }, (Color){ 214, 40, 36, 255 }, 0.55f); ST->hasLandmark = true; ST->landmark = p; ST->landmarkH = 14; }
        MascotBalloon((Vector3){ (ST->mapMin.x + ST->mapMax.x)*0.5f + 30, 48, (ST->mapMin.y + ST->mapMax.y)*0.5f - 20 });
        for (int i = 0; i < 3; i++) Balloon((Vector3){ RR(ST->mapMin.x - 60, ST->mapMax.x + 60), RR(45, 80), RR(ST->mapMin.y - 60, ST->mapMax.y + 60) });
    } break;
    case SCENERY_JUNGLE: {
        for (int i = 0; i < 320; i++) if (Spot(3, 60, 3, &p) && Dry(p)) { float r = RR(0, 1); if (r < 0.55f) JungleTree(p, RR(0.8f, 1.3f)); else Palm(p, RR(0.9f, 1.4f)); }
        for (int i = 0; i < 120; i++) if (Spot(0.5f, 30, 2, &p) && Dry(p)) Fern(p, RR(0.7f, 1.3f));
        /* the jungle wall + red arrow signs on the right bank of the river straight */
        for (int i = (int)(0.44f*n); i < (int)(0.79f*n); i += 3) {
            p = Beside(i, 1, RR(2.5f, 6.0f)); if (ClearOfTrack(p.x, p.z, 1.5f) || RR(0, 1) < 0.6f) JungleTree(p, RR(0.9f, 1.3f));
            if ((i % 15) == 0) { p = Beside(i, 1, RR(8, 16)); if (ClearOfTrack(p.x, p.z, 2)) Palm(p, RR(1.0f, 1.4f)); }
        }
        for (int i = (int)(0.45f*n); i < (int)(0.78f*n); i += 16) {
            const TrackSample *s = &ST->s[i];
            Vector3 c = Vector3Add(s->pos, Vector3Scale(s->right, s->edge[1] + 1.0f)); c.y = fmaxf(GY(c.x, c.z), s->pos.y - 0.2f);
            At(c);
            Box(M(TX_WOOD), (Vector3){ c.x, c.y + 1.2f, c.z }, (Vector3){ 0.22f, 2.4f, 0.22f }, 0, (Color){ 120, 90, 60, 255 }, 1.0f);
            Board((Vector3){ c.x, c.y + 3.0f, c.z }, Vector3Negate(s->fwd), Vector3Scale(s->right, -1), 4.4f, 1.2f, 19);
        }
        /* deep grass where the monkeys hide */
        for (int i = 0; i < n; i += 2) {
            if (!InZone(i, ZN_HAZARD)) continue;
            for (int sd = -1; sd <= 1; sd += 2) {
                if (sd < 0 && InZone(i, ZN_OPEN_L)) continue;
                if (RR(0, 1) < 0.5f) { p = Beside(i, sd, RR(-2.5f, 3.0f)); if (Dry(p)) GrassClump(p, RR(0.8f, 1.2f)); }
            }
        }
        for (int k = 0; k < 4; k++) Billboard((int)((0.05f + k*0.04f)*n), k & 1 ? 1 : -1, (k & 1) ? 26 : 29, 3.0f);
    } break;
    case SCENERY_ISLAND: {
        for (int i = 0; i < 170; i++) if (Spot(1, 40, 3, &p) && Dry(p)) Palm(p, RR(0.8f, 1.3f));
        for (int i = 0; i < 30; i++) if (Spot(2, 18, 3, &p) && Dry(p)) Umbrella(p);
        for (int i = 0; i < 6; i++) if (Spot(8, 26, 7, &p) && Dry(p)) Hut(p, FaceTrack(p));
        for (int i = 0; i < 50; i++) if (Spot(1, 30, 2, &p) && Dry(p)) Bush(p, RR(0.6f, 1.0f));
        for (int i = 0; i < 60; i++) if (Spot(2, 60, 4, &p)) Rock(p, RR(1.5f, 4.5f), ColorFromHSV(RR(22, 36), 0.3f, RR(0.65f, 0.85f)), false);
        for (int i = 0; i < 12; i++) if (Spot(50, 160, 8, &p) && !Dry(p)) { p.y = ST->waterY; Boat(p); }
        /* the big cliff: a rock mass around the arch turn */
        for (int i = (int)(0.48f*n); i < (int)(0.60f*n); i += 4) {
            p = Beside(i, 1, RR(4, 16)); if (ClearOfTrack(p.x, p.z, 3)) Rock(p, RR(4, 8), ColorFromHSV(RR(22, 32), 0.3f, RR(0.7f, 0.85f)), false);
        }
        if (Spot(40, 80, 8, &p)) { Lighthouse(p); ST->hasLandmark = true; ST->landmark = p; ST->landmarkH = 10; }
        for (int k = 0; k < 8; k++) Billboard((int)((0.04f + k*0.12f)*n), 1, (k % 3) == 0 ? 20 : (k % 3) == 1 ? 22 : 27, 3.0f);
    } break;
    case SCENERY_FARM: {
        for (int i = 0; i < 120; i++) if (Spot(10, 80, 3, &p) && Dry(p)) { float r = RR(0, 1); if (r < 0.6f) Oak(p, RR(0.9f, 1.4f)); else Poplar(p, RR(0.9f, 1.3f)); }
        for (int i = 0; i < 30; i++) if (Spot(3, 40, 2.5f, &p) && Dry(p)) HayBale(p, RR(0, 6.28f));
        ST->numCows = 0;
        for (int i = 0; i < 40 && ST->numCows < 16; i++) if (Spot(5, 30, 3, &p) && Dry(p)) { Cow(p, RR(0, 6.28f)); ST->cows[ST->numCows++] = p; }
        for (int i = 0; i < 14; i++) {   /* paddock fences */
            int a = (int)RR(0, (float)n);
            const TrackSample *s = &ST->s[a];
            int side = RR(0, 1) < 0.5f ? -1 : 1;
            float off = s->edge[side > 0 ? 1 : 0] + RR(9, 16);
            Vector3 f0 = Vector3Add(s->pos, Vector3Scale(s->right, side*off));
            const TrackSample *s2 = &ST->s[(a + 12) % n];
            Vector3 f1 = Vector3Add(s2->pos, Vector3Scale(s2->right, side*off));
            if (ClearOfTrack(f0.x, f0.z, 1) && ClearOfTrack(f1.x, f1.z, 1)) Fence(f0, f1, (Color){ 250, 246, 236, 255 });
        }
        { p = Beside((int)(0.20f*n), 1, 30.0f); if (ClearOfTrack(p.x, p.z, 14)) { Barn(p, FaceTrack(p)); ST->hasLandmark = true; ST->landmark = p; ST->landmarkH = 6; } }
        { p = Beside((int)(0.24f*n), 1, 26.0f); if (ClearOfTrack(p.x, p.z, 4)) Silo(p); }
        { p = Beside((int)(0.70f*n), 1, 34.0f); if (ClearOfTrack(p.x, p.z, 12)) Windmill(p, FaceTrack(p)); }
        { p = Beside((int)(0.45f*n), -1, 30.0f); if (ClearOfTrack(p.x, p.z, 12)) House(p, FaceTrack(p), (Color){ 250, 240, 220, 255 }, (Color){ 190, 60, 50, 255 }, 1.1f); }
        { p = Beside((int)(0.88f*n), 1, 34.0f); if (ClearOfTrack(p.x, p.z, 14)) Barn(p, FaceTrack(p)); }
        for (int k = 0; k < 7; k++) Billboard((int)((0.06f + k*0.13f)*n), (k & 1) ? 1 : -1, k == 2 || k == 5 ? 23 : (k % 3) == 0 ? 21 : (k % 3) == 1 ? 28 : 24, 3.0f);
    } break;
    }
}

static void Dress(void)
{
    const TrackDef *d = ST->def;
    Vector3 p;
    int n = ST->n;
    if (d->scenery == SCENERY_STADIUM) { DressStadium(); return; }
    StartGate();
    for (int i = 0; i < n; i += 7) if (fabsf(ST->s[i].curv) > 1.0f/42.0f && !(ST->s[i].zone & (ZN_TUNNEL | ZN_CAVE | ZN_GAP | ZN_PLANKS | ZN_BOOSTFLOOR))) Chevron(i);
    /* grandstand + pennants at the start straight, sponsor boards around the lap */
    if (!d->noGround) Grandstand((n - 14) % n, d->scSide > 0 && ST->scA < 30 ? -1 : 1, 34.0f);
    else Grandstand((n - 14) % n, 1, 26.0f);
    Pennants((n - 30) % n, 14, -1);
    int themed = d->scenery == SCENERY_SPOOKY ? 9 : d->scenery == SCENERY_BEACH ? 10 : d->scenery == SCENERY_DESERT ? 11 : d->scenery == SCENERY_SNOW ? 12 : d->scenery == SCENERY_STARLIGHT ? 13 : 15;
    int signs[8] = { 0, 1, 2, themed, 3, 4, 14, themed };
    if (d->followTerrain) { DressV7(); return; }
    for (int k = 0; k < 9; k++) {
        int i = (int)((k + 0.5f)*n/9.0f);
        if (fabsf(ST->s[i].curv) > 1.0f/42.0f) i = (i + 8) % n;
        Billboard(i, (k & 1) ? 1 : -1, signs[k % 8], RR(0, 4));
    }
    float bigR = 1.0f;
    switch (d->scenery) {
    default: break;
    case SCENERY_MEADOW:
        for (int i = 0; i < 230; i++) if (Spot(2, 55, 3, &p) && Dry(p)) { float r = RR(0, 1); if (r < 0.62f) Oak(p, RR(0.8f, 1.4f)); else if (r < 0.82f) Poplar(p, RR(0.8f, 1.2f)); else Pine(p, RR(0.8f, 1.3f), false); }
        for (int i = 0; i < 90; i++) if (Spot(0.5f, 30, 2, &p) && Dry(p)) Bush(p, RR(0.7f, 1.2f));
        for (int i = 0; i < 150; i++) if (Spot(0.3f, 22, 2.5f, &p) && Dry(p)) FlowerPatch(p);
        for (int i = 0; i < 6; i++) if (Spot(12, 45, 12, &p) && Dry(p)) House(p, FaceTrack(p), HueColor(RR(20, 60), 0.15f, 1.0f), HueColor(RR(-10, 25), 0.7f, 0.95f), RR(0.9f, 1.15f));
        for (int i = 0; i < 3; i++) if (Spot(18, 55, 12, &p) && Dry(p)) Windmill(p, FaceTrack(p));
        for (int i = 0; i < 16; i++) if (Spot(6, 35, 3, &p) && Dry(p)) Cow(p, RR(0, 6.28f));
        for (int i = 0; i < 14; i++) if (Spot(5, 35, 2, &p) && Dry(p)) HayBale(p, RR(0, 6.28f));
        for (int i = 0; i < 10; i++) {   /* wooden paddock fences */
            int a = (int)RR(0, (float)n);
            const TrackSample *s = &ST->s[a];
            int side = RR(0, 1) < 0.5f ? -1 : 1;
            float off = s->edge[side > 0 ? 1 : 0] + RR(8, 14);
            Vector3 f0 = Vector3Add(s->pos, Vector3Scale(s->right, side*off));
            const TrackSample *s2 = &ST->s[(a + 10) % n];
            Vector3 f1 = Vector3Add(s2->pos, Vector3Scale(s2->right, side*off));
            if (ClearOfTrack(f0.x, f0.z, 1) && ClearOfTrack(f1.x, f1.z, 1)) Fence(f0, f1, (Color){ 255, 245, 235, 255 });
        }
        for (int i = 0; i < 7; i++) Balloon((Vector3){ RR(ST->mapMin.x - 60, ST->mapMax.x + 60), ST->groundY + RR(45, 85), RR(ST->mapMin.y - 60, ST->mapMax.y + 60) });
        break;
    case SCENERY_DESERT:
        for (int i = 0; i < 120; i++) if (Spot(1, 55, 2, &p)) Cactus(p, RR(0.7f, 1.3f));
        for (int i = 0; i < 80; i++) if (Spot(0.5f, 45, 2, &p)) Rock(p, RR(0.8f, 3.2f), ColorFromHSV(RR(12, 30), 0.45f, RR(0.75f, 0.95f)), false);
        for (int i = 0; i < 6; i++) if (Spot(60, 200, 45, &p)) Pyramid(p, RR(25, 45));
        for (int i = 0; i < 6; i++) if (Spot(6, 30, 5, &p)) Tent(p);
        for (int i = 0; i < 14; i++) if (Spot(4, 30, 4, &p) && Dry(p)) Palm(p, RR(0.9f, 1.2f));
        for (int i = 0; i < 3; i++) Balloon((Vector3){ RR(ST->mapMin.x - 40, ST->mapMax.x + 40), ST->groundY + RR(45, 80), RR(ST->mapMin.y - 40, ST->mapMax.y + 40) });
        break;
    case SCENERY_SNOW:
        for (int i = 0; i < 240; i++) if (Spot(2, 60, 3, &p)) Pine(p, RR(0.8f, 1.6f), true);
        for (int i = 0; i < 16; i++) if (Spot(2, 22, 3, &p)) Snowman(p, FaceTrack(p));
        for (int i = 0; i < 30; i++) if (Spot(1, 35, 2, &p)) IceCrystal(p, RR(0.6f, 1.4f));
        for (int i = 0; i < 5; i++) if (Spot(8, 30, 6, &p)) Igloo(p);
        for (int i = 0; i < 5; i++) if (Spot(10, 40, 8, &p)) Cabin(p, FaceTrack(p));
        for (int i = 0; i < 40; i++) if (Spot(1, 45, 3, &p)) Rock(p, RR(1, 3), (Color){ 170, 175, 195, 255 }, true);
        break;
    case SCENERY_BEACH:
        for (int i = 0; i < 110; i++) if (Spot(1, 28, 3, &p) && Dry(p)) Palm(p, RR(0.8f, 1.25f));
        for (int i = 0; i < 30; i++) if (Spot(1, 18, 3, &p) && Dry(p)) Umbrella(p);
        for (int i = 0; i < 8; i++) if (Spot(6, 22, 7, &p) && Dry(p)) Hut(p, FaceTrack(p));
        for (int i = 0; i < 40; i++) if (Spot(1, 25, 2, &p) && Dry(p)) Bush(p, RR(0.6f, 1.0f));
        for (int i = 0; i < 30; i++) if (Spot(25, 220, 4, &p)) Rock(p, RR(1.5f, 5), ColorFromHSV(RR(20, 40), 0.25f, RR(0.6f, 0.8f)), false);
        for (int i = 0; i < 14; i++) if (Spot(50, 160, 8, &p) && !Dry(p)) { p.y = ST->waterY; Boat(p); }
        if (Spot(40, 70, 8, &p)) Lighthouse(p);
        for (int i = 0; i < 8; i++) if (Spot(140, 320, 40, &p)) {
            float r = RR(15, 35);
            Far();
            Ellipsoid(M(TX_GRAIN), (Vector3){ p.x, ST->waterY - r*0.55f, p.z }, (Vector3){ r, r*0.75f, r }, Seg(8), Seg(14), (Color){ 240, 220, 160, 255 }, (Color){ 90, 190, 80, 255 }, 1, 1, 0.1f, srng);
            Palm((Vector3){ p.x, ST->waterY + r*0.18f, p.z }, 1.6f);
            Far();
        }
        for (int i = 0; i < 3; i++) Balloon((Vector3){ RR(ST->mapMin.x - 40, ST->mapMax.x + 40), ST->groundY + RR(45, 80), RR(ST->mapMin.y - 40, ST->mapMax.y + 40) });
        break;
    case SCENERY_SPOOKY:
        for (int i = 0; i < 110; i++) if (Spot(1, 50, 3, &p)) DeadTree(p, RR(0.8f, 1.4f));
        for (int i = 0; i < 80; i++) if (Spot(0.5f, 18, 1.5f, &p)) Grave(p, FaceTrack(p));
        for (int i = 0; i < 40; i++) if (Spot(0.5f, 12, 1.5f, &p)) Pumpkin(p, RR(0.7f, 1.4f));
        for (int i = 0; i < 26; i++) if (Spot(0.3f, 2, 1, &p)) Lantern(p);
        for (int i = 0; i < 14; i++) if (Spot(3, 30, 2, &p)) { p.y += RR(2.5f, 5.0f); Ghost(p); }
        for (int i = 0; i < 6; i++) {
            int a = (int)RR(0, (float)n);
            const TrackSample *s = &ST->s[a];
            int side = RR(0, 1) < 0.5f ? -1 : 1;
            float off = s->edge[side > 0 ? 1 : 0] + RR(4, 9);
            Vector3 f0 = Vector3Add(s->pos, Vector3Scale(s->right, side*off));
            const TrackSample *s2 = &ST->s[(a + 9) % n];
            Vector3 f1 = Vector3Add(s2->pos, Vector3Scale(s2->right, side*off));
            if (ClearOfTrack(f0.x, f0.z, 0.5f) && ClearOfTrack(f1.x, f1.z, 0.5f)) IronFence(f0, f1);
        }
        for (int i = 0; i < 4; i++) if (Spot(12, 40, 8, &p)) House(p, FaceTrack(p) + RR(-0.3f, 0.3f), (Color){ 150, 130, 160, 255 }, (Color){ 110, 70, 140, 255 }, 0.9f);
        if (Spot(50, 90, 35, &p)) Castle(p, (Color){ 150, 140, 175, 255 }, (Color){ 120, 60, 160, 255 }, bigR);
        break;
    case SCENERY_STARLIGHT:
        for (int i = 0; i < 22; i++) if (Spot(6, 60, 6, &p)) {
            float h = RR(30, 70);
            Far();
            Tower((Vector3){ p.x, p.y - h*0.6f, p.z }, h, RR(3, 6), (Color){ 190, 180, 230, 255 }, ColorFromHSV(RR(260, 340), 0.6f, 1.0f), true);
        }
        for (int i = 0; i < 70; i++) if (Spot(2, 60, 2, &p)) Star((Vector3){ p.x, p.y + RR(-12, 22), p.z }, RR(1.2f, 3.0f), HueColor(RR(0, 360), 0.45f, 1.0f));
        for (int i = 0; i < 4; i++) if (Spot(120, 260, 40, &p)) Planet((Vector3){ p.x, p.y + RR(20, 80), p.z }, RR(10, 22), HueColor(RR(0, 360), 0.5f, 1.0f));
        if (Spot(70, 120, 40, &p)) {
            Castle((Vector3){ p.x, p.y - 30, p.z }, (Color){ 210, 205, 240, 255 }, (Color){ 240, 80, 150, 255 }, 1.4f);
        }
        break;
    }
}

/* ---------------------------------------------------------------- */
void BuildSceneryChunks(Track *tr)
{
    ST = tr;
    gDet = G.settings.visualMode == 1 ? 1.0f : 0.68f;
    srng = 1234u + (unsigned)tr->index*7919u;
    float x0 = tr->mapMin.x - 70, x1 = tr->mapMax.x + 70, z0 = tr->mapMin.y - 70, z1 = tr->mapMax.y + 70;
    tr->numLights = tr->numFlashSpots = tr->numJumbo = 0; tr->hasNeon = false;
    gcell = fmaxf((x1 - x0), (z1 - z0))/8.0f;
    if (gcell < 40) gcell = 40;
    gcx = (int)ceilf((x1 - x0)/gcell); gcz = (int)ceilf((z1 - z0)/gcell);
    if (gcx > 9) gcx = 9;
    if (gcz > 9) gcz = 9;
    gx0 = x0; gz0 = z0;
    FARC = gcx*gcz;
    memset(SBused, 0, sizeof SBused);
    Dress();
    tr->numChunks = 0;
    tr->sceneVerts = 0;
    for (int c = 0; c <= FARC; c++) {
        SceneChunk *ch = &tr->chunks[tr->numChunks];
        ch->nm = 0; ch->far = (c == FARC);
        Vector3 mn = { 1e9f, 1e9f, 1e9f }, mx = { -1e9f, -1e9f, -1e9f };
        for (int m = 0; m < SCENE_MATS; m++) {
            if (!SBused[c][m]) continue;
            MeshBuilder *mb = &SB[c][m];
            if (mb->count < 3) { MB_Free(mb); continue; }
            for (int v = 0; v < mb->count; v++) {
                Vector3 q = { mb->v[v*3], mb->v[v*3 + 1], mb->v[v*3 + 2] };
                mn = Vector3Min(mn, q); mx = Vector3Max(mx, q);
            }
            tr->sceneVerts += mb->count;
            ch->m[ch->nm++] = MB_BuildModel(mb, G.tx[MATS[m]], true);
            MB_Free(mb);
        }
        if (ch->nm == 0) continue;
        ch->center = Vector3Scale(Vector3Add(mn, mx), 0.5f);
        ch->radius = Vector3Distance(mn, mx)*0.5f;
        tr->numChunks++;
    }
    TraceLog(LOG_INFO, "SCENERY: %d chunks, %d vertices", tr->numChunks, tr->sceneVerts);
}

/* frustum + distance culling, then one DrawModel per material per visible chunk */
static int gDrawnChunks;
void DrawSceneryChunks(Camera3D cam, float aspect)
{
    const Track *tr = &T;
    Vector3 f = Vector3Normalize(Vector3Subtract(cam.target, cam.position));
    Vector3 r = Vector3Normalize(Vector3CrossProduct(f, (Vector3){ 0, 1, 0 }));
    Vector3 u = Vector3CrossProduct(r, f);
    float th = tanf(cam.fovy*0.5f*DEG2RAD), tw = th*aspect;
    /* side plane normals (pointing inwards) */
    Vector3 nl = Vector3Normalize(Vector3Add(Vector3Scale(r, 1.0f), Vector3Scale(f, tw)));
    Vector3 nr = Vector3Normalize(Vector3Add(Vector3Scale(r, -1.0f), Vector3Scale(f, tw)));
    Vector3 nt = Vector3Normalize(Vector3Add(Vector3Scale(u, -1.0f), Vector3Scale(f, th)));
    Vector3 nb = Vector3Normalize(Vector3Add(Vector3Scale(u, 1.0f), Vector3Scale(f, th)));
    float drawDist = G.settings.visualMode == 1 ? 900.0f : 520.0f;
    gDrawnChunks = 0;
    for (int c = 0; c < tr->numChunks; c++) {
        const SceneChunk *ch = &tr->chunks[c];
        Vector3 d = Vector3Subtract(ch->center, cam.position);
        float rad = ch->radius;
        if (!ch->far && Vector3Length(d) - rad > drawDist) continue;
        if (Vector3DotProduct(d, f) < -rad) continue;
        if (Vector3DotProduct(d, nl) < -rad || Vector3DotProduct(d, nr) < -rad || Vector3DotProduct(d, nt) < -rad || Vector3DotProduct(d, nb) < -rad) continue;
        for (int m = 0; m < ch->nm; m++) DrawModel(ch->m[m], (Vector3){ 0, 0, 0 }, 1.0f, WHITE);
        gDrawnChunks++;
    }
}
int SceneryDrawnChunks(void) { return gDrawnChunks; }

void SceneryUnload(Track *tr)
{
    for (int c = 0; c < tr->numChunks; c++)
        for (int m = 0; m < tr->chunks[c].nm; m++) {
            /* textures are shared: detach before unloading so they are not freed */
            tr->chunks[c].m[m].materials[0].maps[MATERIAL_MAP_DIFFUSE].texture = (Texture2D){ 0 };
            UnloadModel(tr->chunks[c].m[m]);
        }
    tr->numChunks = 0;
}

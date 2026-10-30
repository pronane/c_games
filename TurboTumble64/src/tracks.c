/* tracks.c : track definitions (spline control points) + procedural mesh building
 *
 * Each track is a closed Catmull-Rom spline through control points
 * {x, z, height, road width}. The game resamples it every ~2 units and builds
 * a handful of static meshes (road, ground, walls, scenery, sky) once at load,
 * so a whole track costs only ~5 draw calls per frame.
 */
#include "common.h"

const TrackDef TRACK_DEFS[NUM_TRACKS] = {
    {
        .name = "Sunny Meadow Circuit", .subtitle = "Rolling hills, windmills and a sneaky jump",
        .numPts = 21,
        .pts = { {0,-40,0,22}, {0,60,0,22}, {10,135,0,22}, {55,182,1,22}, {125,190,2,22}, {178,155,2,22}, {175,98,1,22}, {125,72,0,22}, {100,30,0,22}, {118,-14,0,22}, {175,-24,0,22}, {225,10,0,22}, {255,70,0,22}, {300,98,0,22}, {348,60,0,22}, {348,-25,0,22}, {300,-88,0,22}, {220,-118,0,22}, {130,-127,0,22}, {60,-117,0,22}, {15,-97,0,22} },
        .scenery = SCENERY_MEADOW,
        .skyTop = {70,130,235,255}, .skyBottom = {175,215,250,255}, .fog = {185,215,240,255},
        .ground = {80,170,60,255}, .road = {150,150,160,255}, .rumbleA = {230,40,40,255}, .rumbleB = {250,250,250,255},
        .wallA = {250,250,250,255}, .wallB = {40,120,230,255},
        .fogDensity = 0.0035f, .grip = 1.0f, .night = false, .rainbowRoad = false, .noGround = false, .wallHeight = 1.3f,
        .numRamps = 1, .ramps = { {0.74f, 14.0f} },
        .numBoxRows = 3, .boxRows = { 0.08f, 0.45f, 0.84f },
        .scFrom = 0.383f, .scTo = 0.52f, .scSide = 1, .scIsRoad = false, .scHint = "Shortcut: a gap in the fence cuts across the meadow - pepper through the grass!",
        .numBumps = 0, .bumpAmp = 0, .bumpPeriod = 12,
        .groundFar = {60,140,50,255}, .farStart = 25, .farEnd = 120,
        .musicSeed = 11, .bpm = 150, .musicKey = 60, .musicScale = 0,
    },
    {
        .name = "Coconut Cove", .subtitle = "Palm trees, beach huts and a turquoise sea",
        .numPts = 23,
        .pts = { {0,0,0,22},{0,90,0,22},{15,160,1,22},{60,205,2,22},{130,215,3,22},{190,190,3,22},{215,135,2,22},{200,80,1,22},{160,50,0,22},{150,0,0,22},{175,-50,0,22},{230,-75,1,22},{280,-60,2,22},{310,-10,3,22},{345,25,3,22},{390,15,2,22},{405,-45,1,22},{385,-115,0,22},{320,-155,0,22},{240,-170,0,22},{150,-165,0,22},{70,-145,0,22},{20,-95,0,22} },
        .scenery = SCENERY_BEACH,
        .skyTop = {40,150,240,255}, .skyBottom = {190,235,255,255}, .fog = {200,235,250,255},
        .ground = {240,220,160,255}, .road = {170,160,150,255}, .rumbleA = {250,120,40,255}, .rumbleB = {250,250,250,255},
        .wallA = {250,250,250,255}, .wallB = {40,180,200,255},
        .fogDensity = 0.0030f, .grip = 0.97f, .night = false, .rainbowRoad = false, .noGround = false, .wallHeight = 1.2f,
        .numRamps = 1, .ramps = { {0.62f, 14.0f} },
        .numBoxRows = 3, .boxRows = { 0.08f, 0.30f, 0.72f },
        .scFrom = 0.363f, .scTo = 0.504f, .scSide = 1, .scIsRoad = false, .scHint = "Shortcut: a sandy track behind the beach huts - boost through the soft sand!",
        .numBumps = 0, .bumpAmp = 0, .bumpPeriod = 12,
        .groundFar = {40,150,205,255}, .farStart = 30, .farEnd = 75,
        .musicSeed = 71, .bpm = 144, .musicKey = 65, .musicScale = 2,
    },
    {
        .name = "Dusty Dunes Rally", .subtitle = "Cacti, pyramids and a blazing sun",
        .numPts = 17,
        .pts = { {0,0,0,24}, {0,120,2,24}, {-20,205,4,24}, {-85,245,3,24}, {-160,235,1,24}, {-195,180,0,24}, {-175,128,2,24}, {-118,104,4,24}, {-95,60,2,24}, {-125,10,0,24}, {-195,-5,1,24}, {-255,-35,3,24}, {-275,-105,1,24}, {-235,-165,0,24}, {-150,-175,2,24}, {-80,-145,3,24}, {-30,-90,1,24} },
        .scenery = SCENERY_DESERT,
        .skyTop = {60,140,230,255}, .skyBottom = {250,215,160,255}, .fog = {245,205,150,255},
        .ground = {225,180,100,255}, .road = {185,140,95,255}, .rumbleA = {200,60,30,255}, .rumbleB = {250,220,120,255},
        .wallA = {170,90,50,255}, .wallB = {230,200,140,255},
        .fogDensity = 0.0042f, .grip = 0.95f, .night = false, .rainbowRoad = false, .noGround = false, .wallHeight = 1.2f,
        .numRamps = 2, .ramps = { {0.22f, 14.0f}, {0.56f, 12.0f} },
        .numBoxRows = 3, .boxRows = { 0.10f, 0.40f, 0.82f },
        .scFrom = 0.266f, .scTo = 0.436f, .scSide = 1, .scIsRoad = false, .scHint = "Bumpy moguls! Shortcut: a gap after the first jump leads across the sand.",
        .numBumps = 2, .bumps = { {0.615f, 0.70f}, {0.86f, 0.95f} }, .bumpAmp = 0.75f, .bumpPeriod = 13,
        .groundFar = {240,200,130,255}, .farStart = 25, .farEnd = 140,
        .musicSeed = 23, .bpm = 138, .musicKey = 57, .musicScale = 2,
    },
    {
        .name = "Frosty Peak Pass", .subtitle = "Slippery ice and a climb through the pines",
        .numPts = 18,
        .pts = { {0,0,0,20}, {0,80,3,20}, {20,145,7,20}, {75,178,10,20}, {140,168,12,20}, {172,125,12,20}, {162,72,10,20}, {120,42,8,20}, {105,0,7,20}, {135,-42,6,20}, {195,-55,6,20}, {238,-95,5,20}, {228,-168,4,20}, {165,-208,2,20}, {82,-196,1,20}, {40,-152,0,20}, {30,-100,0,20}, {10,-60,0,20} },
        .scenery = SCENERY_SNOW,
        .skyTop = {120,150,200,255}, .skyBottom = {220,230,245,255}, .fog = {225,232,245,255},
        .ground = {235,240,250,255}, .road = {175,185,205,255}, .rumbleA = {40,90,200,255}, .rumbleB = {250,250,255,255},
        .wallA = {200,40,50,255}, .wallB = {250,250,255,255},
        .fogDensity = 0.0055f, .grip = 0.72f, .night = false, .rainbowRoad = false, .noGround = false, .wallHeight = 1.4f,
        .numRamps = 1, .ramps = { {0.72f, 12.0f} },
        .numBoxRows = 3, .boxRows = { 0.08f, 0.45f, 0.88f },
        .scFrom = 0.198f, .scTo = 0.371f, .scSide = -1, .scIsRoad = false, .scHint = "Moguls on the descent. Shortcut: snowy trail through the pines on the left.",
        .numBumps = 1, .bumps = { {0.58f, 0.66f} }, .bumpAmp = 0.55f, .bumpPeriod = 12,
        .groundFar = {215,225,245,255}, .farStart = 25, .farEnd = 140,
        .musicSeed = 37, .bpm = 132, .musicKey = 62, .musicScale = 3,
    },
    {
        .name = "Ghoulwood Manor", .subtitle = "Creaky boardwalks past a haunted castle",
        .numPts = 17,
        .pts = { {0,0,0,20},{0,100,1,20},{-15,170,3,20},{-70,205,5,20},{-135,190,7,20},{-158,135,8,20},{-125,92,8,20},{-72,72,7,20},{-58,22,6,20},{-95,-22,5,20},{-160,-28,6,20},{-215,-62,8,20},{-222,-135,9,20},{-172,-185,7,20},{-100,-195,4,20},{-40,-162,2,20},{-10,-100,1,20} },
        .scenery = SCENERY_SPOOKY,
        .skyTop = {42,30,92,255}, .skyBottom = {150,105,175,255}, .fog = {112,88,140,255},
        .ground = {100,118,82,255}, .road = {182,142,108,255}, .rumbleA = {170,80,220,255}, .rumbleB = {255,165,50,255},
        .wallA = {150,135,185,255}, .wallB = {100,90,125,255},
        .fogDensity = 0.0046f, .grip = 0.98f, .night = true, .rainbowRoad = false, .noGround = false, .wallHeight = 1.3f,
        .numRamps = 1, .ramps = { {0.62f, 12.0f} },
        .numBoxRows = 3, .boxRows = { 0.06f, 0.45f, 0.80f },
        .scFrom = 0.218f, .scTo = 0.351f, .scSide = 1, .scIsRoad = false, .scHint = "Rickety boardwalk bumps. Shortcut: cut through the graveyard on the right... if you dare.",
        .numBumps = 1, .bumps = { {0.70f, 0.78f} }, .bumpAmp = 0.45f, .bumpPeriod = 10,
        .groundFar = {88,76,112,255}, .farStart = 25, .farEnd = 120,
        .musicSeed = 83, .bpm = 128, .musicKey = 58, .musicScale = 1,
    },
    {
        .name = "Starlight Spire", .subtitle = "A rainbow ribbon above the night sky",
        .numPts = 17,
        .pts = { {0,0,0,18}, {0,140,6,18}, {-30,220,14,18}, {-110,250,20,18}, {-190,220,22,18}, {-210,150,18,18}, {-170,100,12,18}, {-100,90,10,18}, {-60,40,10,18}, {-80,-20,12,18}, {-150,-40,14,18}, {-220,-80,18,18}, {-230,-160,16,18}, {-170,-220,12,18}, {-80,-230,8,18}, {0,-190,4,18}, {30,-110,1,18} },
        .scenery = SCENERY_STARLIGHT,
        .skyTop = {5,5,25,255}, .skyBottom = {40,20,80,255}, .fog = {30,15,60,255},
        .ground = {40,20,70,255}, .road = {255,255,255,255}, .rumbleA = {255,255,255,255}, .rumbleB = {255,120,220,255},
        .wallA = {120,255,255,255}, .wallB = {255,120,255,255},
        .fogDensity = 0.0028f, .grip = 1.0f, .night = true, .rainbowRoad = true, .noGround = true, .wallHeight = 0.9f,
        .numRamps = 2, .ramps = { {0.20f, 14.0f}, {0.76f, 14.0f} },
        .numBoxRows = 3, .boxRows = { 0.10f, 0.58f, 0.88f },
        .scFrom = 0.392f, .scTo = 0.579f, .scSide = 1, .scIsRoad = true, .scHint = "Shortcut: a narrow star bridge on the right - nail the line!",
        .numBumps = 0, .bumpAmp = 0, .bumpPeriod = 12,
        .musicSeed = 59, .bpm = 156, .musicKey = 64, .musicScale = 1,
    },
};

/* deterministic RNG for scenery */
static unsigned int trng = 1;
static float TR(float lo, float hi) { trng = trng*1664525u + 1013904223u; return lo + (hi - lo)*((trng >> 8)/16777216.0f); }

static void CatmullRom(const float *p0, const float *p1, const float *p2, const float *p3, float t, float *out)
{
    float t2 = t*t, t3 = t2*t;
    for (int i = 0; i < 4; i++) {
        out[i] = 0.5f*((2*p1[i]) + (-p0[i] + p2[i])*t + (2*p0[i] - 5*p1[i] + 4*p2[i] - p3[i])*t2 +
                       (-p0[i] + 3*p1[i] - 3*p2[i] + p3[i])*t3);
    }
}

/* dense spline evaluation -> arrays of (x,z,h,w) */
static int SplineDense(const TrackDef *d, float (*out)[4], int perSeg)
{
    int c = 0;
    for (int i = 0; i < d->numPts; i++) {
        const float *p0 = d->pts[(i - 1 + d->numPts) % d->numPts];
        const float *p1 = d->pts[i];
        const float *p2 = d->pts[(i + 1) % d->numPts];
        const float *p3 = d->pts[(i + 2) % d->numPts];
        for (int j = 0; j < perSeg; j++) CatmullRom(p0, p1, p2, p3, (float)j/perSeg, out[c++]);
    }
    return c;
}

void TrackOutline(int index, Vector2 *out, int maxPts, int *count)
{
    static float dense[MAX_CTRL_PTS*16][4];
    const TrackDef *d = &TRACK_DEFS[index];
    int n = SplineDense(d, dense, 16);
    int step = (n + maxPts - 1)/maxPts; if (step < 1) step = 1;
    int c = 0;
    for (int i = 0; i < n && c < maxPts; i += step) out[c++] = (Vector2){ dense[i][0], dense[i][1] };
    *count = c;
}

int TrackWrap(const Track *tr, int i) { i %= tr->n; if (i < 0) i += tr->n; return i; }

float TrackHalfWidth(const Track *tr, int seg) { return tr->s[TrackWrap(tr, seg)].width*0.5f; }

float TrackWallLimit(const Track *tr, int seg, float lat) { return tr->s[TrackWrap(tr, seg)].edge[lat > 0 ? 1 : 0] - 0.9f; }

Vector3 TrackPoint(const Track *tr, int seg, float lat)
{
    const TrackSample *s = &tr->s[TrackWrap(tr, seg)];
    return Vector3Add(s->pos, Vector3Scale(s->right, lat));
}

void TrackLocate(const Track *tr, Vector3 p, int hint, int *seg, float *lat, float *along, float *groundY)
{
    int best = 0; float bd = 1e30f;
    int from = 0, to = tr->n - 1;
    if (hint >= 0) { from = hint - 14; to = hint + 14; }
    for (int i = from; i <= to; i++) {
        int k = TrackWrap(tr, i);
        float dx = p.x - tr->s[k].pos.x, dz = p.z - tr->s[k].pos.z;
        float dy = p.y - tr->s[k].pos.y;
        float d = dx*dx + dz*dz + dy*dy*0.25f;
        if (d < bd) { bd = d; best = k; }
    }
    const TrackSample *s = &tr->s[best];
    float t = ((p.x - s->pos.x)*s->fwd.x + (p.z - s->pos.z)*s->fwd.z)/tr->spacing;
    if (t < 0) { best = TrackWrap(tr, best - 1); s = &tr->s[best]; t = ((p.x - s->pos.x)*s->fwd.x + (p.z - s->pos.z)*s->fwd.z)/tr->spacing; }
    t = Clamp(t, 0.0f, 1.0f);
    const TrackSample *s2 = &tr->s[TrackWrap(tr, best + 1)];
    Vector3 r = Vector3Normalize(Vector3Lerp(s->right, s2->right, t));
    Vector3 c = Vector3Lerp(s->pos, s2->pos, t);
    *seg = best;
    *along = t;
    *lat = (p.x - c.x)*r.x + (p.z - c.z)*r.z;
    *groundY = c.y;
}

/* ------------------------------------------------------------------ */
/* Shortcut corridor                                                    */
/* ------------------------------------------------------------------ */
bool TrackShortcutLocate(const Track *tr, Vector3 p, int *idx, float *lat, float *along, float *groundY)
{
    *idx = 0; *lat = 1e6f; *along = 0; *groundY = p.y;
    if (tr->scN < 2) return false;
    int best = 0; float bd = 1e30f;
    for (int i = 0; i < tr->scN; i++) {
        float dx = p.x - tr->sc[i].pos.x, dz = p.z - tr->sc[i].pos.z;
        float d = dx*dx + dz*dz;
        if (d < bd) { bd = d; best = i; }
    }
    if (best > tr->scN - 2) best = tr->scN - 2;
    float sp = tr->sc[1].dist - tr->sc[0].dist;
    const TrackSample *s = &tr->sc[best];
    float t = ((p.x - s->pos.x)*s->fwd.x + (p.z - s->pos.z)*s->fwd.z)/sp;
    if (t < 0 && best > 0) { best--; s = &tr->sc[best]; t = ((p.x - s->pos.x)*s->fwd.x + (p.z - s->pos.z)*s->fwd.z)/sp; }
    bool inside = true;
    if (best == 0 && t < 0) inside = false;
    if (best == tr->scN - 2 && t > 1) inside = false;
    float tc = Clamp(t, 0.0f, 1.0f);
    const TrackSample *s2 = &tr->sc[best + 1];
    Vector3 c = Vector3Lerp(s->pos, s2->pos, tc);
    *idx = best; *along = tc;
    *lat = (p.x - c.x)*s->right.x + (p.z - c.z)*s->right.z;
    *groundY = c.y;
    if (fabsf(*lat) > tr->scHalf) inside = false;
    if (fabsf(p.y - c.y) > 6.0f) inside = false;
    return inside;
}

/* progress-equivalent main-track sample for a position on the shortcut */
int TrackShortcutMainSeg(const Track *tr, int idx, float along)
{
    int span = TrackWrap(tr, tr->scB - tr->scA);
    float f = (idx + along)/(float)(tr->scN - 1);
    return TrackWrap(tr, tr->scA + (int)(span*Clamp(f, 0, 1) + 0.5f));
}

static bool InMainCorridor(const Track *tr, Vector3 p, float margin)
{
    int seg; float lat, al, gy;
    TrackLocate(tr, p, -1, &seg, &lat, &al, &gy);
    return fabsf(lat) <= tr->s[seg].edge[lat > 0 ? 1 : 0] + margin && fabsf(p.y - gy) < 6.0f;
}

static bool InShortcut(const Track *tr, Vector3 p, float margin)
{
    if (tr->scN < 2) return false;
    int i; float lat, al, gy;
    Track *mt = (Track *)tr;
    float h = mt->scHalf; mt->scHalf = h + margin;
    bool r = TrackShortcutLocate(tr, p, &i, &lat, &al, &gy);
    mt->scHalf = h;
    return r;
}

static void BuildShortcut(Track *tr)
{
    const TrackDef *d = tr->def;
    tr->scN = 0;
    if (d->scTo <= d->scFrom) return;
    int n = tr->n;
    tr->scA = (int)(d->scFrom*n) % n;
    tr->scB = (int)(d->scTo*n) % n;
    tr->scHalf = d->scIsRoad ? 4.0f : 5.0f;
    const TrackSample *a = &tr->s[tr->scA], *b = &tr->s[tr->scB];
    float side = (float)d->scSide;
    Vector3 A = Vector3Add(a->pos, Vector3Scale(a->right, side*a->width*0.5f*0.45f));
    Vector3 B = Vector3Add(b->pos, Vector3Scale(b->right, side*b->width*0.5f*0.45f));
    float len = Vector3Distance((Vector3){ A.x, 0, A.z }, (Vector3){ B.x, 0, B.z });
    int cnt = (int)(len/2.0f) + 1;
    if (cnt > 256) cnt = 256;
    if (cnt < 4) return;
    /* cubic Bezier leaving tangent to the road and rejoining tangent to it */
    float L = len*0.33f;
    Vector3 P1 = Vector3Add(A, Vector3Scale(a->fwd, L)), P2 = Vector3Subtract(B, Vector3Scale(b->fwd, L));
    static Vector3 tmp[2048];
    int m = 2000;
    float arc = 0;
    for (int i = 0; i <= m; i++) {
        float u = (float)i/m, iu = 1 - u;
        Vector3 q = Vector3Add(Vector3Add(Vector3Scale(A, iu*iu*iu), Vector3Scale(P1, 3*iu*iu*u)), Vector3Add(Vector3Scale(P2, 3*iu*u*u), Vector3Scale(B, u*u*u)));
        tmp[i] = q;
        if (i) arc += Vector3Distance((Vector3){ q.x, 0, q.z }, (Vector3){ tmp[i - 1].x, 0, tmp[i - 1].z });
    }
    cnt = (int)(arc/2.0f) + 1;
    if (cnt > 256) cnt = 256;
    float acc = 0; int j = 0;
    for (int i = 0; i < cnt; i++) {
        float target = arc*i/(cnt - 1);
        while (j < m && acc + Vector3Distance((Vector3){ tmp[j].x, 0, tmp[j].z }, (Vector3){ tmp[j + 1].x, 0, tmp[j + 1].z }) < target) {
            acc += Vector3Distance((Vector3){ tmp[j].x, 0, tmp[j].z }, (Vector3){ tmp[j + 1].x, 0, tmp[j + 1].z }); j++;
        }
        TrackSample *s = &tr->sc[i];
        s->pos = tmp[j];
        s->pos.y = Lerp(A.y, B.y, (float)i/(cnt - 1)) + sinf((float)i/(cnt - 1)*PI)*0.35f;
        s->dist = target;
        s->curv = 0; s->ramp = false; s->bump = false;
        s->width = tr->scHalf*2;
        s->edge[0] = s->edge[1] = tr->scHalf;
    }
    for (int i = 0; i < cnt; i++) {
        Vector3 p0 = tr->sc[i > 0 ? i - 1 : 0].pos, p1 = tr->sc[i < cnt - 1 ? i + 1 : cnt - 1].pos;
        Vector3 f = Vector3Normalize((Vector3){ p1.x - p0.x, 0, p1.z - p0.z });
        tr->sc[i].fwd = f;
        tr->sc[i].right = (Vector3){ -f.z, 0, f.x };
    }
    /* sanity: the trail must stay clear of the rest of the course */
    float worst = 1e9f;
    for (int i = cnt/6; i < cnt - cnt/6; i++) for (int k = 0; k < n; k += 2) {
        int dA = TrackWrap(tr, k - tr->scA), dB = TrackWrap(tr, tr->scB - k);
        if (dA < TrackWrap(tr, tr->scB - tr->scA) + 10 && dB < TrackWrap(tr, tr->scB - tr->scA) + 10) continue; /* the skipped arc */
        float dx = tr->sc[i].pos.x - tr->s[k].pos.x, dz = tr->sc[i].pos.z - tr->s[k].pos.z;
        float cl = sqrtf(dx*dx + dz*dz) - fmaxf(tr->s[k].edge[0], tr->s[k].edge[1]) - tr->scHalf;
        if (cl < worst) worst = cl;
    }
    TraceLog(worst < 1.0f ? LOG_WARNING : LOG_INFO, "TRACK: shortcut %d samples, %.0f long (skips %.0f), clearance %.1f", cnt, arc,
             TrackWrap(tr, tr->scB - tr->scA)*tr->spacing, worst);
    tr->scN = cnt;
}

/* ------------------------------------------------------------------ */
/* Scenery helpers                                                     */
/* ------------------------------------------------------------------ */
static bool ClearOfTrack(const Track *tr, float x, float z, float radius)
{
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

/* pick a random spot beside the track */
static bool ScenerySpot(const Track *tr, float minOff, float maxOff, float radius, Vector3 *out)
{
    for (int tries = 0; tries < 20; tries++) {
        int i = (int)TR(0, (float)tr->n - 1);
        const TrackSample *s = &tr->s[i];
        float side = TR(0, 1) < 0.5f ? -1.0f : 1.0f;
        float off = s->width*0.5f + 1.0f + tr->shoulder + TR(minOff, maxOff);
        Vector3 p = Vector3Add(s->pos, Vector3Scale(s->right, side*off));
        if (ClearOfTrack(tr, p.x, p.z, radius)) {
            p.y = tr->def->noGround ? s->pos.y : tr->groundY;
            *out = p;
            return true;
        }
    }
    return false;
}

static void AddTree(MeshBuilder *mb, Vector3 p, float s, int kind)
{
    Color trunk = { 120, 80, 45, 255 };
    if (G.settings.visualMode == 1) {
        /* ENHANCED: smooth-shaded, more segments, extra foliage clumps */
        MB_Cylinder(mb, p, 0.55f*s, 0.38f*s, 3.2f*s, 9, trunk);
        if (kind == 0) {
            Color leaf = ColorFromHSV(TR(95, 130), 0.65f, TR(0.5f, 0.75f));
            Color dk = ColorScale(leaf, 0.7f), lt = ColorScale(leaf, 1.25f);
            MB_SmoothSphere(mb, (Vector3){ p.x, p.y + 4.0f*s, p.z }, (Vector3){ 2.6f*s, 2.2f*s, 2.6f*s }, 6, 11, dk, lt, -PI*0.5f);
            for (int q = 0; q < 3; q++) {
                float a = TR(0, 2*PI);
                MB_SmoothSphere(mb, (Vector3){ p.x + cosf(a)*1.4f*s, p.y + TR(4.6f, 5.8f)*s, p.z + sinf(a)*1.4f*s }, (Vector3){ 1.5f*s, 1.3f*s, 1.5f*s }, 5, 9, ColorScale(leaf, 0.85f), lt, -PI*0.5f);
            }
        } else {
            Color leaf = ColorFromHSV(TR(120, 150), 0.6f, TR(0.35f, 0.55f));
            for (int i = 0; i < 4; i++)
                MB_Cylinder(mb, (Vector3){ p.x, p.y + (1.8f + i*1.5f)*s, p.z }, (3.1f - i*0.65f)*s, 0, 2.9f*s, 12, ColorScale(leaf, 0.95f + i*0.08f));
            if (kind == 2) {
                for (int i = 0; i < 4; i++)
                    MB_Cylinder(mb, (Vector3){ p.x, p.y + (3.2f + i*1.5f)*s, p.z }, (1.5f - i*0.3f)*s, 0, 1.5f*s, 12, (Color){ 245, 248, 255, 255 });
            }
        }
        return;
    }
    MB_Cylinder(mb, p, 0.5f*s, 0.4f*s, 3.0f*s, 5, trunk);
    if (kind == 0) {
        Color leaf = ColorFromHSV(TR(95, 130), 0.65f, TR(0.5f, 0.75f));
        MB_Sphere(mb, (Vector3){ p.x, p.y + 4.0f*s, p.z }, (Vector3){ 2.6f*s, 2.3f*s, 2.6f*s }, 4, 6, leaf);
        MB_Sphere(mb, (Vector3){ p.x + 0.8f*s, p.y + 5.6f*s, p.z - 0.4f*s }, (Vector3){ 1.6f*s, 1.4f*s, 1.6f*s }, 3, 5, ColorScale(leaf, 1.12f));
    } else {
        Color leaf = ColorFromHSV(TR(120, 150), 0.6f, TR(0.35f, 0.55f));
        for (int i = 0; i < 3; i++)
            MB_Cylinder(mb, (Vector3){ p.x, p.y + (2.0f + i*1.9f)*s, p.z }, (3.0f - i*0.8f)*s, 0, 3.2f*s, 6, ColorScale(leaf, 1.0f + i*0.08f));
        if (kind == 2) { /* snowy tips */
            for (int i = 0; i < 3; i++)
                MB_Cylinder(mb, (Vector3){ p.x, p.y + (3.6f + i*1.9f)*s, p.z }, (1.5f - i*0.4f)*s, 0, 1.6f*s, 6, (Color){ 245, 248, 255, 255 });
        }
    }
}

static void AddHouse(MeshBuilder *mb, Vector3 p, float yaw, Color wall, Color roof)
{
    MB_Box(mb, (Vector3){ p.x, p.y + 3, p.z }, (Vector3){ 9, 6, 7 }, yaw, wall);
    float c = cosf(yaw), s = sinf(yaw);
    Vector3 a = { p.x + (-5)*c + (-4)*s, p.y + 6, p.z - (-5)*s + (-4)*c };
    Vector3 b = { p.x + (5)*c + (-4)*s, p.y + 6, p.z - (5)*s + (-4)*c };
    Vector3 cc = { p.x + (5)*c + (4)*s, p.y + 6, p.z - (5)*s + (4)*c };
    Vector3 d = { p.x + (-5)*c + (4)*s, p.y + 6, p.z - (-5)*s + (4)*c };
    Vector3 r1 = { p.x + (-5)*c, p.y + 10, p.z - (-5)*s };
    Vector3 r2 = { p.x + (5)*c, p.y + 10, p.z - (5)*s };
    Vector3 ctr = { p.x, p.y + 7, p.z };
    MB_Quad(mb, a, b, r2, r1, roof, ctr);
    MB_Quad(mb, d, cc, r2, r1, roof, ctr);
    MB_Tri(mb, a, d, r1, wall, ctr);
    MB_Tri(mb, b, cc, r2, wall, ctr);
    MB_Box(mb, (Vector3){ p.x + 4.55f*s, p.y + 1.6f, p.z + 4.55f*c*0.78f }, (Vector3){ 1.6f, 3.2f, 0.2f }, yaw, (Color){ 110, 70, 40, 255 });
}

static void AddWindmill(MeshBuilder *mb, Vector3 p, float yaw)
{
    MB_Cylinder(mb, p, 3.5f, 2.2f, 14, 8, (Color){ 240, 235, 220, 255 });
    MB_Cylinder(mb, (Vector3){ p.x, p.y + 14, p.z }, 2.8f, 0, 4, 8, (Color){ 200, 60, 50, 255 });
    float c = cosf(yaw), s = sinf(yaw);
    Vector3 hub = { p.x + s*2.8f, p.y + 13, p.z + c*2.8f };
    for (int i = 0; i < 4; i++) {
        float a = i*PI*0.5f + 0.4f;
        Vector3 dir = { cosf(a)*c, sinf(a), -cosf(a)*s };
        Vector3 e = Vector3Add(hub, Vector3Scale(dir, 9));
        Vector3 side = { s*0.3f, 0, c*0.3f };
        Vector3 w = Vector3Scale(Vector3CrossProduct(dir, (Vector3){ s, 0, c }), 1.2f);
        MB_Quad(mb, Vector3Add(hub, side), Vector3Add(e, side), Vector3Add(Vector3Add(e, w), side), Vector3Add(Vector3Add(hub, w), side),
                (Color){ 250, 250, 245, 255 }, Vector3Subtract(hub, (Vector3){ s*5, 0, c*5 }));
    }
}

static void AddCactus(MeshBuilder *mb, Vector3 p, float s)
{
    Color g = ColorFromHSV(TR(100, 130), 0.6f, TR(0.45f, 0.6f));
    MB_Cylinder(mb, p, 0.7f*s, 0.6f*s, 6.0f*s, 6, g);
    MB_Sphere(mb, (Vector3){ p.x, p.y + 6.0f*s, p.z }, (Vector3){ 0.6f*s, 0.5f*s, 0.6f*s }, 3, 6, g);
    float a = TR(0, 2*PI);
    for (int i = 0; i < 2; i++) {
        float side = i ? 1.0f : -1.0f;
        float h = (i ? 2.5f : 3.4f)*s;
        Vector3 b = { p.x + cosf(a)*side*1.4f*s, p.y + h, p.z + sinf(a)*side*1.4f*s };
        MB_Box(mb, (Vector3){ p.x + cosf(a)*side*0.8f*s, p.y + h, p.z + sinf(a)*side*0.8f*s }, (Vector3){ 1.4f*s, 0.8f*s, 0.8f*s }, -a, g);
        MB_Cylinder(mb, b, 0.42f*s, 0.38f*s, 2.2f*s, 5, g);
    }
}

static void AddSnowman(MeshBuilder *mb, Vector3 p, float yaw)
{
    Color w = { 250, 252, 255, 255 };
    MB_Sphere(mb, (Vector3){ p.x, p.y + 1.6f, p.z }, (Vector3){ 1.8f, 1.6f, 1.8f }, 4, 7, w);
    MB_Sphere(mb, (Vector3){ p.x, p.y + 4.0f, p.z }, (Vector3){ 1.3f, 1.2f, 1.3f }, 4, 7, w);
    MB_Sphere(mb, (Vector3){ p.x, p.y + 5.8f, p.z }, (Vector3){ 0.9f, 0.9f, 0.9f }, 4, 7, w);
    MB_Box(mb, (Vector3){ p.x + sinf(yaw)*1.0f, p.y + 5.8f, p.z + cosf(yaw)*1.0f }, (Vector3){ 0.25f, 0.25f, 0.9f }, yaw, ORANGE);
    MB_Cylinder(mb, (Vector3){ p.x, p.y + 6.5f, p.z }, 0.7f, 0.7f, 1.0f, 7, (Color){ 30, 30, 40, 255 });
    MB_Cylinder(mb, (Vector3){ p.x, p.y + 6.5f, p.z }, 1.1f, 1.1f, 0.12f, 7, (Color){ 30, 30, 40, 255 });
    MB_Box(mb, (Vector3){ p.x, p.y + 5.1f, p.z }, (Vector3){ 2.0f, 0.4f, 2.0f }, yaw, (Color){ 220, 40, 40, 255 });
}

static void AddTower(MeshBuilder *mb, Vector3 base, float h, float r, Color stone, Color roof, bool windows)
{
    MB_Cylinder(mb, base, r, r*0.92f, h, 8, stone);
    MB_Cylinder(mb, (Vector3){ base.x, base.y + h, base.z }, r*1.25f, r*1.25f, 1.2f, 8, ColorScale(stone, 0.9f));
    MB_Cylinder(mb, (Vector3){ base.x, base.y + h + 1.2f, base.z }, r*1.3f, 0, r*2.2f, 8, roof);
    if (windows) {
        for (int i = 0; i < 4; i++) {
            float a = i*PI*0.5f + 0.3f;
            for (int j = 1; j < 4; j++) {
                float y = base.y + h - j*h*0.18f;
                if (y < base.y + 2) continue;
                MB_Box(mb, (Vector3){ base.x + cosf(a)*(r*0.96f), y, base.z + sinf(a)*(r*0.96f) }, (Vector3){ 0.5f, 1.2f, 0.9f }, -a + PI*0.5f, (Color){ 255, 230, 120, 255 });
            }
        }
    }
}

static void AddChevronSign(MeshBuilder *mb, const Track *tr, int i)
{
    const TrackSample *s = &tr->s[i];
    float side = s->curv > 0 ? 1.0f : -1.0f;  /* outside of a left turn is the right side */
    float off = s->width*0.5f + 1.0f + tr->shoulder + 1.4f;
    Vector3 p = Vector3Add(s->pos, Vector3Scale(s->right, side*off));
    float yaw = atan2f(s->fwd.x, s->fwd.z);
    Color post = { 90, 90, 90, 255 };
    MB_Box(mb, (Vector3){ p.x, p.y + 1.2f, p.z }, (Vector3){ 0.25f, 2.4f, 0.25f }, yaw, post);
    MB_Box(mb, (Vector3){ p.x, p.y + 3.0f, p.z }, (Vector3){ 0.2f, 1.6f, 3.2f }, yaw, (Color){ 255, 210, 30, 255 });
    /* black chevron arrows on the face looking at the road, pointing along travel */
    Vector3 face = Vector3Scale(s->right, -side*0.13f);
    Vector3 c = Vector3Add(p, face);
    Vector3 f = s->fwd;
    Vector3 ref = Vector3Add(p, Vector3Scale(s->right, side*2.0f));
    for (int k = -1; k <= 1; k += 2) {
        for (int a2 = 0; a2 < 2; a2++) {
            float o = a2*1.1f - 0.55f;
            Vector3 tip = { c.x + f.x*(o + 0.5f), c.y + 3.0f, c.z + f.z*(o + 0.5f) };
            Vector3 tip2 = { c.x + f.x*(o + 0.1f), c.y + 3.0f, c.z + f.z*(o + 0.1f) };
            Vector3 ta = { c.x + f.x*(o - 0.1f), c.y + 3.0f + k*0.6f, c.z + f.z*(o - 0.1f) };
            Vector3 tb = { c.x + f.x*(o - 0.5f), c.y + 3.0f + k*0.6f, c.z + f.z*(o - 0.5f) };
            MB_Quad(mb, tip, ta, tb, tip2, (Color){ 20, 20, 20, 255 }, ref);
        }
    }
}

static void AddPalm(MeshBuilder *mb, Vector3 p, float s)
{
    /* curved trunk out of a few leaning segments */
    float lean = TR(0, 2*PI), la = TR(0.15f, 0.35f);
    Vector3 b = p;
    for (int k = 0; k < 4; k++) {
        Vector3 t = { b.x + cosf(lean)*la*2.2f*s, b.y + 2.2f*s, b.z + sinf(lean)*la*2.2f*s };
        MB_Cylinder(mb, (Vector3){ b.x, b.y, b.z }, (0.55f - k*0.06f)*s, (0.5f - k*0.06f)*s, 2.3f*s, 6, ColorScale((Color){ 150, 110, 70, 255 }, 1.0f - (k & 1)*0.12f));
        b = t;
    }
    for (int k = 0; k < 7; k++) {
        float a = k*2*PI/7 + TR(-0.2f, 0.2f);
        Vector3 tip = { b.x + cosf(a)*5.0f*s, b.y - 1.6f*s, b.z + sinf(a)*5.0f*s };
        Vector3 mid = { b.x + cosf(a)*2.6f*s, b.y + 0.6f*s, b.z + sinf(a)*2.6f*s };
        Vector3 sd = { -sinf(a)*1.0f*s, 0, cosf(a)*1.0f*s };
        Color lc = ColorFromHSV(TR(100, 125), 0.7f, TR(0.5f, 0.7f));
        MB_Tri(mb, b, Vector3Add(mid, sd), Vector3Subtract(mid, sd), lc, (Vector3){ b.x, b.y - 5, b.z });
        MB_Tri(mb, Vector3Add(mid, sd), tip, Vector3Subtract(mid, sd), ColorScale(lc, 0.9f), (Vector3){ b.x, b.y - 5, b.z });
    }
    MB_Sphere(mb, (Vector3){ b.x, b.y - 0.4f*s, b.z }, (Vector3){ 0.5f*s, 0.5f*s, 0.5f*s }, 3, 5, (Color){ 110, 75, 40, 255 });
}

static void AddUmbrella(MeshBuilder *mb, Vector3 p)
{
    MB_Cylinder(mb, p, 0.12f, 0.12f, 3.2f, 4, (Color){ 240, 240, 240, 255 });
    Color c1 = HueColor(TR(0, 360), 0.7f, 1.0f);
    for (int k = 0; k < 8; k++) {
        float a0 = k*2*PI/8, a1 = (k + 1)*2*PI/8;
        Vector3 top = { p.x, p.y + 3.8f, p.z };
        Vector3 e0 = { p.x + cosf(a0)*2.6f, p.y + 2.8f, p.z + sinf(a0)*2.6f }, e1 = { p.x + cosf(a1)*2.6f, p.y + 2.8f, p.z + sinf(a1)*2.6f };
        MB_Tri(mb, top, e0, e1, (k & 1) ? c1 : (Color){ 250, 250, 250, 255 }, (Vector3){ p.x, p.y, p.z });
    }
    MB_Box(mb, (Vector3){ p.x + 1.6f, p.y + 0.25f, p.z }, (Vector3){ 1.2f, 0.1f, 2.6f }, TR(0, 3), HueColor(TR(0, 360), 0.5f, 1.0f));
}

static void AddDeadTree(MeshBuilder *mb, Vector3 p, float s)
{
    Color bark = { 60, 50, 55, 255 };
    MB_Cylinder(mb, p, 0.6f*s, 0.25f*s, 7.0f*s, 5, bark);
    for (int k = 0; k < 4; k++) {
        float a = TR(0, 2*PI), h = TR(3.5f, 6.5f)*s, l = TR(1.8f, 3.2f)*s;
        Vector3 b = { p.x, p.y + h, p.z };
        Vector3 e = { p.x + cosf(a)*l, p.y + h + l*0.7f, p.z + sinf(a)*l };
        Vector3 sd = { -sinf(a)*0.18f*s, 0, cosf(a)*0.18f*s };
        MB_Quad(mb, Vector3Add(b, sd), Vector3Subtract(b, sd), Vector3Subtract(e, Vector3Scale(sd, 0.3f)), Vector3Add(e, Vector3Scale(sd, 0.3f)), bark, (Vector3){ p.x, p.y + 50, p.z });
    }
}

static void AddGrave(MeshBuilder *mb, Vector3 p, float yaw)
{
    Color st = ColorFromHSV(TR(240, 280), 0.1f, TR(0.5f, 0.65f));
    if (TR(0, 1) < 0.6f) {
        MB_Box(mb, (Vector3){ p.x, p.y + 1.0f, p.z }, (Vector3){ 1.4f, 2.0f, 0.4f }, yaw, st);
        MB_Cylinder(mb, (Vector3){ p.x, p.y + 2.0f, p.z }, 0.7f, 0.7f, 0.3f, 6, st);
    } else {
        MB_Box(mb, (Vector3){ p.x, p.y + 1.3f, p.z }, (Vector3){ 0.35f, 2.6f, 0.35f }, yaw, st);
        MB_Box(mb, (Vector3){ p.x, p.y + 1.9f, p.z }, (Vector3){ 1.5f, 0.35f, 0.35f }, yaw, st);
    }
}

static void AddPumpkin(MeshBuilder *mb, Vector3 p, float s)
{
    MB_Sphere(mb, (Vector3){ p.x, p.y + 0.8f*s, p.z }, (Vector3){ 1.1f*s, 0.85f*s, 1.1f*s }, 4, 8, (Color){ 240, 120, 20, 255 });
    MB_Box(mb, (Vector3){ p.x, p.y + 1.75f*s, p.z }, (Vector3){ 0.2f*s, 0.4f*s, 0.2f*s }, 0, (Color){ 70, 110, 40, 255 });
    /* glowing face */
    MB_Box(mb, (Vector3){ p.x, p.y + 0.95f*s, p.z + 1.02f*s }, (Vector3){ 0.9f*s, 0.25f*s, 0.1f*s }, 0, (Color){ 255, 240, 120, 255 });
}

static void BuildScenery(Track *tr, MeshBuilder *mb)
{
    const TrackDef *d = tr->def;
    trng = 1234u + (unsigned)tr->index*7919u;
    Vector3 p;

    /* start gate */
    {
        const TrackSample *s = &tr->s[0];
        float hw = s->width*0.5f + 1.6f;
        Vector3 l = Vector3Add(s->pos, Vector3Scale(s->right, -hw));
        Vector3 r = Vector3Add(s->pos, Vector3Scale(s->right, hw));
        float yaw = atan2f(s->fwd.x, s->fwd.z);
        Color pole = d->night ? (Color){ 200, 200, 255, 255 } : (Color){ 230, 230, 230, 255 };
        MB_Box(mb, (Vector3){ l.x, l.y + 4, l.z }, (Vector3){ 0.8f, 8, 0.8f }, yaw, pole);
        MB_Box(mb, (Vector3){ r.x, r.y + 4, r.z }, (Vector3){ 0.8f, 8, 0.8f }, yaw, pole);
        int cells = 12;
        for (int i = 0; i < cells; i++) {
            for (int j = 0; j < 2; j++) {
                float t0 = (float)i/cells, t1 = (float)(i + 1)/cells;
                Vector3 a = Vector3Lerp(l, r, t0), b = Vector3Lerp(l, r, t1);
                float y0 = 7.0f + j*0.9f, y1 = y0 + 0.9f;
                Color c = ((i + j) & 1) ? (Color){ 20, 20, 20, 255 } : WHITE;
                Vector3 fo = Vector3Scale(s->fwd, -0.3f), ba = Vector3Scale(s->fwd, 0.3f);
                Vector3 q0 = Vector3Add(a, fo), q1 = Vector3Add(b, fo);
                MB_Quad(mb, (Vector3){ q0.x, a.y + y0, q0.z }, (Vector3){ q1.x, b.y + y0, q1.z },
                        (Vector3){ q1.x, b.y + y1, q1.z }, (Vector3){ q0.x, a.y + y1, q0.z }, c, Vector3Add(s->pos, (Vector3){ 0, 7, 0 }));
                Vector3 w0 = Vector3Add(a, ba), w1 = Vector3Add(b, ba);
                MB_Quad(mb, (Vector3){ w0.x, a.y + y0, w0.z }, (Vector3){ w1.x, b.y + y0, w1.z },
                        (Vector3){ w1.x, b.y + y1, w1.z }, (Vector3){ w0.x, a.y + y1, w0.z }, c, Vector3Add(s->pos, (Vector3){ 0, 7, 0 }));
            }
        }
        Vector3 m = Vector3Lerp(l, r, 0.5f);
        MB_Box(mb, (Vector3){ m.x, m.y + 6.85f, m.z }, (Vector3){ hw*2, 0.3f, 0.6f }, yaw - PI*0.5f + PI*0.5f, (Color){ 220, 40, 40, 255 });
    }

    /* chevron signs on sharp bends */
    for (int i = 0; i < tr->n; i += 10) {
        if (fabsf(tr->s[i].curv) > 1.0f/45.0f) AddChevronSign(mb, tr, i);
    }

    switch (d->scenery) {
    case SCENERY_MEADOW:
        for (int i = 0; i < 150; i++) if (ScenerySpot(tr, 2, 45, 3, &p)) AddTree(mb, p, TR(0.8f, 1.4f), TR(0, 1) < 0.7f ? 0 : 1);
        for (int i = 0; i < 160; i++) if (ScenerySpot(tr, 0.5f, 12, 0.5f, &p)) {
            Color fc = HueColor(TR(0, 1) < 0.5f ? TR(330, 380) : TR(40, 60), 0.7f, 1.0f);
            MB_Box(mb, (Vector3){ p.x, p.y + 0.5f, p.z }, (Vector3){ 0.6f, 0.6f, 0.6f }, TR(0, 3), fc);
            MB_Box(mb, (Vector3){ p.x, p.y + 0.2f, p.z }, (Vector3){ 0.15f, 0.5f, 0.15f }, 0, (Color){ 40, 140, 40, 255 });
        }
        for (int i = 0; i < 4; i++) if (ScenerySpot(tr, 10, 40, 12, &p)) AddHouse(mb, p, TR(0, 6.28f), (Color){ 240, 230, 200, 255 }, (Color){ 190, 50, 40, 255 });
        for (int i = 0; i < 3; i++) if (ScenerySpot(tr, 15, 50, 12, &p)) AddWindmill(mb, p, TR(0, 6.28f));
        for (int i = 0; i < 18; i++) if (ScenerySpot(tr, 70, 260, 50, &p)) {
            float r = TR(30, 70);
            MB_Cylinder(mb, (Vector3){ p.x, p.y - 1, p.z }, r, r*0.15f, TR(12, 30), 9, ColorFromHSV(TR(95, 125), 0.55f, TR(0.45f, 0.6f)));
        }
        break;
    case SCENERY_DESERT:
        for (int i = 0; i < 110; i++) if (ScenerySpot(tr, 1, 50, 2, &p)) AddCactus(mb, p, TR(0.7f, 1.3f));
        for (int i = 0; i < 70; i++) if (ScenerySpot(tr, 0.5f, 40, 2, &p)) {
            float s = TR(0.8f, 3.0f);
            MB_Box(mb, (Vector3){ p.x, p.y + s*0.4f, p.z }, (Vector3){ s*1.6f, s, s*1.3f }, TR(0, 6), ColorFromHSV(TR(15, 30), 0.55f, TR(0.5f, 0.7f)));
        }
        for (int i = 0; i < 5; i++) if (ScenerySpot(tr, 60, 200, 45, &p)) {
            float s = TR(25, 45);
            MB_Cylinder(mb, (Vector3){ p.x, p.y - 0.5f, p.z }, s, 0, s*0.95f, 4, (Color){ 235, 200, 120, 255 });
        }
        for (int i = 0; i < 12; i++) if (ScenerySpot(tr, 80, 280, 40, &p)) {
            float r = TR(18, 40);
            MB_Cylinder(mb, (Vector3){ p.x, p.y - 1, p.z }, r, r*0.8f, TR(20, 45), 7, ColorFromHSV(TR(8, 22), 0.6f, TR(0.6f, 0.75f)));
        }
        for (int i = 0; i < 8; i++) if (ScenerySpot(tr, 4, 30, 4, &p)) { /* palm trees */
            MB_Cylinder(mb, p, 0.5f, 0.35f, 8, 5, (Color){ 140, 100, 60, 255 });
            for (int k = 0; k < 5; k++) {
                float a = k*2*PI/5;
                Vector3 top = { p.x, p.y + 8, p.z };
                Vector3 tip = { p.x + cosf(a)*4.5f, p.y + 6.5f, p.z + sinf(a)*4.5f };
                Vector3 sd = { -sinf(a)*0.9f, 0, cosf(a)*0.9f };
                MB_Tri(mb, top, Vector3Add(tip, sd), Vector3Subtract(tip, sd), (Color){ 60, 160, 60, 255 }, (Vector3){ p.x, p.y, p.z });
            }
        }
        break;
    case SCENERY_SNOW:
        for (int i = 0; i < 170; i++) if (ScenerySpot(tr, 2, 50, 3, &p)) AddTree(mb, p, TR(0.8f, 1.5f), 2);
        for (int i = 0; i < 12; i++) if (ScenerySpot(tr, 2, 20, 3, &p)) AddSnowman(mb, p, TR(0, 6.28f));
        for (int i = 0; i < 25; i++) if (ScenerySpot(tr, 1, 30, 2, &p)) {
            MB_Cylinder(mb, p, TR(0.8f, 1.6f), 0, TR(4, 9), 4, (Color){ 150, 220, 255, 255 });
        }
        for (int i = 0; i < 3; i++) if (ScenerySpot(tr, 8, 30, 6, &p)) {
            MB_Sphere(mb, p, (Vector3){ 5, 4, 5 }, 4, 8, (Color){ 240, 248, 255, 255 });
            MB_Box(mb, (Vector3){ p.x + 4.5f, p.y + 1.2f, p.z }, (Vector3){ 2.5f, 2.4f, 2.4f }, 0, (Color){ 230, 240, 255, 255 });
        }
        for (int i = 0; i < 16; i++) if (ScenerySpot(tr, 80, 280, 50, &p)) {
            float r = TR(35, 70);
            float h = TR(40, 90);
            MB_Cylinder(mb, (Vector3){ p.x, p.y - 1, p.z }, r, 0, h, 7, (Color){ 140, 150, 175, 255 });
            MB_Cylinder(mb, (Vector3){ p.x, p.y - 1 + h*0.62f, p.z }, r*0.385f, 0, h*0.38f + 0.3f, 7, (Color){ 250, 252, 255, 255 });
        }
        break;
    case SCENERY_BEACH:
        for (int i = 0; i < 70; i++) if (ScenerySpot(tr, 1, 26, 3, &p)) AddPalm(mb, p, TR(0.8f, 1.25f));
        for (int i = 0; i < 26; i++) if (ScenerySpot(tr, 1, 18, 3, &p)) AddUmbrella(mb, p);
        for (int i = 0; i < 6; i++) if (ScenerySpot(tr, 6, 22, 7, &p)) AddHouse(mb, p, TR(0, 6.28f), HueColor(TR(0, 360), 0.35f, 1.0f), (Color){ 200, 160, 90, 255 });
        for (int i = 0; i < 40; i++) if (ScenerySpot(tr, 45, 260, 4, &p)) {   /* rocks out in the sea */
            float s = TR(1.5f, 6);
            MB_Sphere(mb, (Vector3){ p.x, p.y - s*0.3f, p.z }, (Vector3){ s*1.3f, s, s }, 3, 6, ColorFromHSV(TR(20, 40), 0.25f, TR(0.45f, 0.6f)));
        }
        /* lighthouse */
        if (ScenerySpot(tr, 40, 70, 8, &p)) {
            for (int k = 0; k < 6; k++)
                MB_Cylinder(mb, (Vector3){ p.x, p.y + k*4.0f, p.z }, 4.0f - k*0.35f, 3.65f - k*0.35f, 4.0f, 10, (k & 1) ? (Color){ 250, 250, 250, 255 } : (Color){ 220, 40, 40, 255 });
            MB_Cylinder(mb, (Vector3){ p.x, p.y + 24, p.z }, 2.2f, 2.2f, 2.5f, 8, (Color){ 255, 240, 140, 255 });
            MB_Cylinder(mb, (Vector3){ p.x, p.y + 26.5f, p.z }, 2.6f, 0, 2.5f, 8, (Color){ 200, 30, 30, 255 });
        }
        /* little islands on the horizon */
        for (int i = 0; i < 8; i++) if (ScenerySpot(tr, 140, 320, 40, &p)) {
            float r = TR(15, 35);
            MB_Sphere(mb, (Vector3){ p.x, p.y - r*0.6f, p.z }, (Vector3){ r, r*0.8f, r }, 4, 8, ColorFromHSV(TR(90, 120), 0.5f, 0.55f));
            AddPalm(mb, (Vector3){ p.x, p.y + r*0.15f, p.z }, 1.6f);
        }
        break;
    case SCENERY_SPOOKY:
        for (int i = 0; i < 90; i++) if (ScenerySpot(tr, 1, 45, 3, &p)) AddDeadTree(mb, p, TR(0.8f, 1.4f));
        for (int i = 0; i < 70; i++) if (ScenerySpot(tr, 0.5f, 16, 1.5f, &p)) AddGrave(mb, p, TR(0, 6.28f));
        for (int i = 0; i < 30; i++) if (ScenerySpot(tr, 0.5f, 10, 1.5f, &p)) AddPumpkin(mb, p, TR(0.7f, 1.3f));
        for (int i = 0; i < 24; i++) if (ScenerySpot(tr, 0.3f, 2, 1, &p)) {         /* lantern posts */
            MB_Cylinder(mb, p, 0.15f, 0.15f, 4.0f, 4, (Color){ 40, 35, 45, 255 });
            MB_Box(mb, (Vector3){ p.x, p.y + 4.3f, p.z }, (Vector3){ 0.7f, 0.8f, 0.7f }, 0, (Color){ 255, 220, 110, 255 });
        }
        /* the haunted castle */
        if (ScenerySpot(tr, 50, 90, 35, &p)) {
            Color st = { 85, 80, 105, 255 }, rf = { 60, 30, 80, 255 };
            MB_Box(mb, (Vector3){ p.x, p.y + 12, p.z }, (Vector3){ 36, 24, 26 }, 0, st);
            AddTower(mb, (Vector3){ p.x - 18, p.y, p.z - 13 }, 40, 5, st, rf, true);
            AddTower(mb, (Vector3){ p.x + 18, p.y, p.z - 13 }, 44, 5, st, rf, true);
            AddTower(mb, (Vector3){ p.x - 18, p.y, p.z + 13 }, 36, 5, st, rf, true);
            AddTower(mb, (Vector3){ p.x + 18, p.y, p.z + 13 }, 38, 5, st, rf, true);
            AddTower(mb, (Vector3){ p.x, p.y + 10, p.z }, 48, 7, st, (Color){ 120, 40, 140, 255 }, true);
        }
        for (int i = 0; i < 14; i++) if (ScenerySpot(tr, 90, 280, 40, &p)) {
            float r = TR(30, 60);
            MB_Cylinder(mb, (Vector3){ p.x, p.y - 1, p.z }, r, r*0.25f, TR(20, 45), 7, ColorFromHSV(TR(250, 280), 0.3f, TR(0.25f, 0.35f)));
        }
        break;
    case SCENERY_STARLIGHT:
        for (int i = 0; i < 22; i++) if (ScenerySpot(tr, 6, 60, 6, &p)) {
            float h = TR(30, 70);
            AddTower(mb, (Vector3){ p.x, p.y - h*0.6f, p.z }, h, TR(3, 6), (Color){ 120, 115, 150, 255 }, ColorFromHSV(TR(260, 330), 0.6f, 0.8f), true);
        }
        for (int i = 0; i < 90; i++) if (ScenerySpot(tr, 2, 70, 2, &p)) {
            Vector3 c = { p.x, p.y + TR(-15, 25), p.z };
            float s = TR(1, 3);
            MB_Sphere(mb, c, (Vector3){ s, s*1.8f, s }, 2, 4, ColorFromHSV(TR(0, 360), 0.6f, 1.0f));
        }
        /* the grand castle */
        if (ScenerySpot(tr, 70, 120, 40, &p)) {
            Color st = { 150, 145, 180, 255 };
            MB_Box(mb, (Vector3){ p.x, p.y - 10, p.z }, (Vector3){ 40, 50, 30 }, 0, st);
            AddTower(mb, (Vector3){ p.x - 20, p.y - 35, p.z - 15 }, 75, 6, st, (Color){ 220, 60, 120, 255 }, true);
            AddTower(mb, (Vector3){ p.x + 20, p.y - 35, p.z - 15 }, 75, 6, st, (Color){ 220, 60, 120, 255 }, true);
            AddTower(mb, (Vector3){ p.x - 20, p.y - 35, p.z + 15 }, 70, 6, st, (Color){ 220, 60, 120, 255 }, true);
            AddTower(mb, (Vector3){ p.x + 20, p.y - 35, p.z + 15 }, 70, 6, st, (Color){ 220, 60, 120, 255 }, true);
            AddTower(mb, (Vector3){ p.x, p.y - 35, p.z }, 95, 9, st, (Color){ 255, 200, 60, 255 }, true);
        }
        break;
    }
}

static void BuildSky(Track *tr, MeshBuilder *mb)
{
    const TrackDef *d = tr->def;
    trng = 777u + (unsigned)tr->index*31u;
    float skyR = 600.0f;
    bool enh = G.settings.visualMode == 1;
    int slices = enh ? 48 : 24, rings = enh ? 20 : 8;
    Vector3 far = { 0, -5000, 0 };
    Vector2 uv = { 0.5f, 0.5f };
    for (int i = 0; i < rings; i++) {
        float a0 = (PI*0.5f)*i/rings, a1 = (PI*0.5f)*(i + 1)/rings;
        Color c0 = ColorMix(d->skyBottom, d->skyTop, powf((float)i/rings, 0.7f));
        Color c1 = ColorMix(d->skyBottom, d->skyTop, powf((float)(i + 1)/rings, 0.7f));
        if (enh) {
            /* ENHANCED: brighter sky with a luminous haze band at the horizon */
            float h0 = 1.0f - (float)i/rings, h1 = 1.0f - (float)(i + 1)/rings;
            Color haze = d->night ? ColorScale(d->skyBottom, 1.25f) : ColorMix(d->skyBottom, WHITE, 0.45f);
            c0 = ColorMix(ColorScale(c0, d->night ? 1.08f : 1.1f), haze, powf(h0, 5.0f)*0.8f);
            c1 = ColorMix(ColorScale(c1, d->night ? 1.08f : 1.1f), haze, powf(h1, 5.0f)*0.8f);
        }
        for (int j = 0; j < slices; j++) {
            float b0 = 2*PI*j/slices, b1 = 2*PI*(j + 1)/slices;
            Vector3 p00 = { skyR*cosf(a0)*cosf(b0), skyR*sinf(a0), skyR*cosf(a0)*sinf(b0) };
            Vector3 p01 = { skyR*cosf(a0)*cosf(b1), skyR*sinf(a0), skyR*cosf(a0)*sinf(b1) };
            Vector3 p10 = { skyR*cosf(a1)*cosf(b0), skyR*sinf(a1), skyR*cosf(a1)*sinf(b0) };
            Vector3 p11 = { skyR*cosf(a1)*cosf(b1), skyR*sinf(a1), skyR*cosf(a1)*sinf(b1) };
            MB_TriUV(mb, p00, p01, p11, uv, uv, uv, c0, c0, c1, far, false);
            MB_TriUV(mb, p00, p11, p10, uv, uv, uv, c0, c1, c1, far, false);
        }
    }
    /* below-horizon band in fog colour so the horizon is seamless */
    for (int j = 0; j < slices; j++) {
        float b0 = 2*PI*j/slices, b1 = 2*PI*(j + 1)/slices;
        Vector3 a = { skyR*cosf(b0), 0, skyR*sinf(b0) }, b = { skyR*cosf(b1), 0, skyR*sinf(b1) };
        Vector3 a2 = { a.x, -skyR*0.5f, a.z }, b2 = { b.x, -skyR*0.5f, b.z };
        Color bc = d->noGround ? ColorScale(d->fog, 0.5f) : d->fog;
        MB_TriUV(mb, a, b, b2, uv, uv, uv, d->fog, d->fog, bc, far, false);
        MB_TriUV(mb, a, b2, a2, uv, uv, uv, d->fog, bc, bc, far, false);
    }
    if (d->night) {
        for (int i = 0; i < 400; i++) {
            float th = TR(0, 2*PI), ph = TR(0.08f, 1.5f);
            Vector3 c = { skyR*0.95f*cosf(ph)*cosf(th), skyR*0.95f*sinf(ph), skyR*0.95f*cosf(ph)*sinf(th) };
            float s = TR(0.8f, 2.4f);
            Color sc = ColorFromHSV(TR(180, 300), TR(0, 0.4f), 1.0f);
            Vector3 up = { 0, s, 0 }, rt = { -sinf(th)*s, 0, cosf(th)*s };
            MB_TriUV(mb, Vector3Add(c, up), Vector3Add(c, rt), Vector3Subtract(c, up), uv, uv, uv, sc, sc, sc, Vector3Scale(c, 2), false);
            MB_TriUV(mb, Vector3Add(c, up), Vector3Subtract(c, rt), Vector3Subtract(c, up), uv, uv, uv, sc, sc, sc, Vector3Scale(c, 2), false);
        }
        /* moon */
        Vector3 mc = { -300, 330, -330 };
        for (int j = 0; j < 16; j++) {
            float a0 = 2*PI*j/16, a1 = 2*PI*(j + 1)/16;
            Vector3 r1 = Vector3Normalize(Vector3CrossProduct(mc, (Vector3){ 0, 1, 0 }));
            Vector3 u1 = Vector3Normalize(Vector3CrossProduct(r1, mc));
            Vector3 p0 = Vector3Add(mc, Vector3Add(Vector3Scale(r1, cosf(a0)*28), Vector3Scale(u1, sinf(a0)*28)));
            Vector3 p1 = Vector3Add(mc, Vector3Add(Vector3Scale(r1, cosf(a1)*28), Vector3Scale(u1, sinf(a1)*28)));
            Color mcol = { 255, 250, 220, 255 };
            MB_TriUV(mb, mc, p0, p1, uv, uv, uv, mcol, mcol, mcol, Vector3Scale(mc, 2), false);
        }
    } else {
        /* distant mountain ring */
        Color mcol = ColorMix(d->fog, d->scenery == SCENERY_DESERT ? (Color){ 200, 120, 80, 255 } :
                              d->scenery == SCENERY_SNOW ? (Color){ 150, 160, 190, 255 } : (Color){ 90, 140, 110, 255 }, 0.45f);
        int peaks = 40;
        for (int j = 0; j < peaks; j++) {
            float b0 = 2*PI*j/peaks, b1 = 2*PI*(j + 1)/peaks, bm = (b0 + b1)*0.5f;
            float h = TR(25, 75);
            Vector3 a = { skyR*0.9f*cosf(b0), -2, skyR*0.9f*sinf(b0) }, b = { skyR*0.9f*cosf(b1), -2, skyR*0.9f*sinf(b1) };
            Vector3 top = { skyR*0.9f*cosf(bm), h, skyR*0.9f*sinf(bm) };
            Color tc = d->scenery == SCENERY_SNOW ? ColorMix(mcol, WHITE, 0.6f) : ColorScale(mcol, 1.05f);
            MB_TriUV(mb, a, b, top, uv, uv, uv, mcol, mcol, tc, (Vector3){ 0, 0, 0 }, false);
        }
        /* chunky clouds */
        for (int i = 0; i < 14; i++) {
            float th = TR(0, 2*PI), h = TR(110, 200), r = TR(380, 480);
            Vector3 c = { r*cosf(th), h, r*sinf(th) };
            Color cc = { 255, 255, 255, 255 };
            for (int k = 0; k < 3; k++) {
                Vector3 cp = Vector3Add(c, (Vector3){ -sinf(th)*(k - 1)*28.0f, (k == 1) ? 8.0f : 0.0f, cosf(th)*(k - 1)*28.0f });
                int seg = enh ? 18 : 8;
                for (int q = 0; q < seg; q++) {
                    float a0 = 2*PI*q/seg, a1 = 2*PI*(q + 1)/seg;
                    float rx = 26, ry = 14;
                    Vector3 rt = { -sinf(th), 0, cosf(th) };
                    Vector3 p0 = { cp.x + rt.x*cosf(a0)*rx, cp.y + sinf(a0)*ry, cp.z + rt.z*cosf(a0)*rx };
                    Vector3 p1 = { cp.x + rt.x*cosf(a1)*rx, cp.y + sinf(a1)*ry, cp.z + rt.z*cosf(a1)*rx };
                    Color bot = ColorMix(cc, d->skyBottom, 0.35f);
                    MB_TriUV(mb, cp, p0, p1, uv, uv, uv, cc, sinf(a0) < 0 ? bot : cc, sinf(a1) < 0 ? bot : cc, Vector3Scale(cp, 2), false);
                }
            }
        }
    }
}

void TrackBuild(Track *tr, int index)
{
    if (tr->loaded && tr->index == index && tr->builtVisual == G.settings.visualMode) return;
    if (tr->loaded) TrackUnload(tr);
    const TrackDef *d = &TRACK_DEFS[index];
    tr->def = d;
    tr->index = index;
    tr->builtVisual = G.settings.visualMode;

    /* --- dense spline + arc length --- */
    static float dense[MAX_CTRL_PTS*100][4];
    static float cum[MAX_CTRL_PTS*100 + 1];
    int m = SplineDense(d, dense, 100);
    cum[0] = 0;
    for (int i = 1; i <= m; i++) {
        const float *a = dense[i - 1], *b = dense[i % m];
        float dx = b[0] - a[0], dz = b[1] - a[1], dh = b[2] - a[2];
        cum[i] = cum[i - 1] + sqrtf(dx*dx + dz*dz + dh*dh);
    }
    tr->length = cum[m];
    int n = (int)(tr->length/2.0f);
    if (n > MAX_TRACK_SAMPLES) n = MAX_TRACK_SAMPLES;
    tr->n = n;
    tr->spacing = tr->length/n;
    int j = 0;
    for (int i = 0; i < n; i++) {
        float target = i*tr->spacing;
        while (j < m - 1 && cum[j + 1] < target) j++;
        float seg = cum[j + 1] - cum[j];
        float t = seg > 0 ? (target - cum[j])/seg : 0;
        const float *a = dense[j], *b = dense[(j + 1) % m];
        tr->s[i].pos = (Vector3){ a[0] + (b[0] - a[0])*t, a[2] + (b[2] - a[2])*t, a[1] + (b[1] - a[1])*t };
        tr->s[i].width = a[3] + (b[3] - a[3])*t;
        tr->s[i].dist = target;
        tr->s[i].ramp = false;
        tr->s[i].bump = false;
    }
    for (int i = 0; i < n; i++) {
        Vector3 pa = tr->s[(i - 1 + n) % n].pos, pb = tr->s[(i + 1) % n].pos;
        Vector3 f = { pb.x - pa.x, 0, pb.z - pa.z };
        f = Vector3Normalize(f);
        tr->s[i].fwd = f;
        tr->s[i].right = (Vector3){ -f.z, 0, f.x };
    }
    for (int i = 0; i < n; i++) {
        Vector3 f0 = tr->s[(i - 2 + n) % n].fwd, f1 = tr->s[(i + 2) % n].fwd;
        float da = WrapAngle(atan2f(f1.x, f1.z) - atan2f(f0.x, f0.z));
        tr->s[i].curv = da/(4.0f*tr->spacing);
    }
    /* ramps: raise the road into a kicker, then a sudden drop */
    for (int r = 0; r < d->numRamps; r++) {
        int i0 = (int)(d->ramps[r][0]*n);
        int cnt = (int)(d->ramps[r][1]/tr->spacing);
        for (int k = 0; k < cnt; k++) {
            int idx = (i0 + k) % n;
            float f = (float)(k + 1)/cnt;
            tr->s[idx].pos.y += 2.4f*f*f*(3.0f - 2.0f*f)*0.6f + 2.4f*f*0.4f;
            tr->s[idx].ramp = true;
        }
    }
    /* moguls: rolling bumps that throw karts into the air at speed */
    for (int bi = 0; bi < d->numBumps; bi++) {
        int i0 = (int)(d->bumps[bi][0]*n), i1 = (int)(d->bumps[bi][1]*n);
        float total = (i1 - i0)*tr->spacing;
        for (int k = 0; k <= i1 - i0; k++) {
            int idx = (i0 + k) % n;
            float x = k*tr->spacing;
            float env = Clamp(fminf(x, total - x)/8.0f, 0, 1);
            float ph = x/d->bumpPeriod;
            float h = 0.5f - 0.5f*cosf(2*PI*ph);
            tr->s[idx].pos.y += d->bumpAmp*h*env;
            tr->s[idx].bump = true;
        }
    }
    float minY = 1e9f;
    tr->mapMin = (Vector2){ 1e9f, 1e9f }; tr->mapMax = (Vector2){ -1e9f, -1e9f };
    for (int i = 0; i < n; i++) {
        Vector3 p = tr->s[i].pos;
        if (p.y < minY) minY = p.y;
        if (p.x < tr->mapMin.x) tr->mapMin.x = p.x;
        if (p.z < tr->mapMin.y) tr->mapMin.y = p.z;
        if (p.x > tr->mapMax.x) tr->mapMax.x = p.x;
        if (p.z > tr->mapMax.y) tr->mapMax.y = p.z;
    }
    tr->groundY = minY - 0.45f;
    tr->shoulder = d->rainbowRoad ? 1.6f : 6.0f;
    /* wall lines: pull the inside of tight bends in so the off-road strip never folds over itself */
    {
        static float raw[MAX_TRACK_SAMPLES][2];
        for (int i = 0; i < n; i++) {
            float def = tr->s[i].width*0.5f + 1.0f + tr->shoulder;
            raw[i][0] = raw[i][1] = def;
            float c = tr->s[i].curv;
            if (fabsf(c) > 1e-4f) {
                float radius = 1.0f/fabsf(c);
                float lim = fmaxf(radius*0.8f - 0.5f, tr->s[i].width*0.5f + 2.0f);
                int inner = c > 0 ? 0 : 1;      /* left turn -> inside is the left */
                if (lim < raw[i][inner]) raw[i][inner] = lim;
            }
        }
        for (int i = 0; i < n; i++) for (int sd = 0; sd < 2; sd++) {
            float edge = raw[i][sd];
            for (int k = -5; k <= 5; k++) edge = fminf(edge, raw[(i + k + n) % n][sd] + fabsf((float)k)*0.6f);
            tr->s[i].edge[sd] = edge;
        }
    }
    BuildShortcut(tr);

    /* --- road mesh (asphalt + rumble strips + start line) --- */
    MeshBuilder mb; MB_Init(&mb);
    for (int i = 0; i < n; i++) {
        int i1 = (i + 1) % n;
        const TrackSample *a = &tr->s[i], *b = &tr->s[i1];
        float va = a->dist/10.0f, vb = (i1 == 0 ? tr->length : b->dist)/10.0f;
        float ha = a->width*0.5f, hb = b->width*0.5f;
        Vector3 below = Vector3Add(a->pos, (Vector3){ 0, -50, 0 });
        Color rc = d->road;
        if (d->rainbowRoad) rc = HueColor(a->dist/tr->length*360.0f*5.0f, 0.55f, 1.0f);
        if (d->scenery == SCENERY_SPOOKY) rc = ColorScale(rc, (i & 1) ? 0.92f : 1.04f);   /* boardwalk planks */
        if (a->bump) rc = ColorScale(rc, 0.94f + 0.12f*Clamp((a->pos.y - Lerp(tr->s[(i + n - 6) % n].pos.y, tr->s[(i + 6) % n].pos.y, 0.5f))/fmaxf(d->bumpAmp, 0.1f), 0, 1));
        if (a->ramp) rc = ((i/2) & 1) ? (Color){ 250, 200, 30, 255 } : (Color){ 60, 60, 60, 255 };
        if (i == 0 || i == 1) {
            int cells = 10;
            for (int c = 0; c < cells; c++) {
                float t0 = -1.0f + 2.0f*c/cells, t1 = -1.0f + 2.0f*(c + 1)/cells;
                Vector3 p0 = Vector3Add(a->pos, Vector3Scale(a->right, ha*t0));
                Vector3 p1 = Vector3Add(a->pos, Vector3Scale(a->right, ha*t1));
                Vector3 p2 = Vector3Add(b->pos, Vector3Scale(b->right, hb*t1));
                Vector3 p3 = Vector3Add(b->pos, Vector3Scale(b->right, hb*t0));
                Color cc = ((c + i) & 1) ? (Color){ 25, 25, 25, 255 } : (Color){ 250, 250, 250, 255 };
                MB_Quad(&mb, p0, p1, p2, p3, cc, below);
            }
        } else {
            Vector3 l0 = Vector3Add(a->pos, Vector3Scale(a->right, -ha)), r0 = Vector3Add(a->pos, Vector3Scale(a->right, ha));
            Vector3 l1 = Vector3Add(b->pos, Vector3Scale(b->right, -hb)), r1 = Vector3Add(b->pos, Vector3Scale(b->right, hb));
            MB_QuadUV(&mb, l0, r0, r1, l1, (Vector2){ 0, va }, (Vector2){ 1, va }, (Vector2){ 1, vb }, (Vector2){ 0, vb }, rc, below, true);
        }
        /* rumble strips */
        Color rum = ((i/2) & 1) ? d->rumbleA : d->rumbleB;
        if (d->rainbowRoad) rum = ((i/2) & 1) ? WHITE : HueColor(a->dist*2.0f, 0.4f, 1.0f);
        for (int sd = -1; sd <= 1; sd += 2) {
            Vector3 i0 = Vector3Add(a->pos, Vector3Scale(a->right, sd*ha)), o0 = Vector3Add(a->pos, Vector3Scale(a->right, sd*(ha + 1.0f)));
            Vector3 i1v = Vector3Add(b->pos, Vector3Scale(b->right, sd*hb)), o1 = Vector3Add(b->pos, Vector3Scale(b->right, sd*(hb + 1.0f)));
            MB_QuadUV(&mb, i0, o0, o1, i1v, (Vector2){ 0.02f, va }, (Vector2){ 0.08f, va }, (Vector2){ 0.08f, vb }, (Vector2){ 0.02f, vb }, rum, below, true);
        }
        /* ramp side walls so the kicker looks solid */
        if (a->ramp || b->ramp) {
            for (int sd = -1; sd <= 1; sd += 2) {
                Vector3 e0 = Vector3Add(a->pos, Vector3Scale(a->right, sd*(ha + 1.0f)));
                Vector3 e1 = Vector3Add(b->pos, Vector3Scale(b->right, sd*(hb + 1.0f)));
                Vector3 g0 = e0, g1 = e1; g0.y -= 3.0f; g1.y -= 3.0f;
                MB_QuadUV(&mb, e0, e1, g1, g0, (Vector2){ 0.5f, 0.5f }, (Vector2){ 0.5f, 0.5f }, (Vector2){ 0.5f, 0.5f }, (Vector2){ 0.5f, 0.5f },
                          (Color){ 90, 90, 90, 255 }, a->pos, true);
            }
        }
    }
    if (d->scIsRoad) {
        for (int i = 0; i + 1 < tr->scN; i++) {
            const TrackSample *a = &tr->sc[i], *b = &tr->sc[i + 1];
            if (InMainCorridor(tr, a->pos, -1.5f) && InMainCorridor(tr, b->pos, -1.5f)) continue;
            float hh = tr->scHalf;
            Vector3 l0 = Vector3Add(a->pos, Vector3Scale(a->right, -hh)), r0 = Vector3Add(a->pos, Vector3Scale(a->right, hh));
            Vector3 l1 = Vector3Add(b->pos, Vector3Scale(b->right, -hh)), r1 = Vector3Add(b->pos, Vector3Scale(b->right, hh));
            l0.y += 0.05f; r0.y += 0.05f; l1.y += 0.05f; r1.y += 0.05f;
            Color rc = HueColor(i*9.0f, 0.35f, 1.0f);
            MB_QuadUV(&mb, l0, r0, r1, l1, (Vector2){ 0, a->dist/10 }, (Vector2){ 1, a->dist/10 }, (Vector2){ 1, b->dist/10 }, (Vector2){ 0, b->dist/10 },
                      rc, Vector3Add(a->pos, (Vector3){ 0, -50, 0 }), true);
        }
    }
    tr->mRoad = MB_BuildModel(&mb, G.texRoad, true);
    MB_Free(&mb);

    /* --- shoulder (off-road) + ground plane --- */
    MB_Init(&mb);
    Color gc = WHITE;
    for (int i = 0; i < n; i++) {
        int i1 = (i + 1) % n;
        const TrackSample *a = &tr->s[i], *b = &tr->s[i1];
        Vector3 below = Vector3Add(a->pos, (Vector3){ 0, -50, 0 });
        for (int sd = -1; sd <= 1; sd += 2) {
            float ia = a->width*0.5f + 1.0f, ib = b->width*0.5f + 1.0f;
            Vector3 p0 = Vector3Add(a->pos, Vector3Scale(a->right, sd*ia));
            int si = sd > 0 ? 1 : 0;
            Vector3 p1 = Vector3Add(a->pos, Vector3Scale(a->right, sd*a->edge[si]));
            Vector3 p2 = Vector3Add(b->pos, Vector3Scale(b->right, sd*b->edge[si]));
            Vector3 p3 = Vector3Add(b->pos, Vector3Scale(b->right, sd*ib));
            Vector2 u0 = { p0.x/8.0f, p0.z/8.0f }, u1 = { p1.x/8.0f, p1.z/8.0f }, u2 = { p2.x/8.0f, p2.z/8.0f }, u3 = { p3.x/8.0f, p3.z/8.0f };
            Color sc = d->rainbowRoad ? (Color){ 70, 60, 110, 255 } : gc;
            MB_QuadUV(&mb, p0, p1, p2, p3, u0, u1, u2, u3, sc, below, true);
        }
    }
    if (!d->scIsRoad) {
        Color tc = d->scenery == SCENERY_SNOW ? (Color){ 200, 215, 240, 255 } : d->scenery == SCENERY_DESERT ? (Color){ 190, 140, 90, 255 } :
                   d->scenery == SCENERY_BEACH ? (Color){ 255, 240, 200, 255 } : d->scenery == SCENERY_SPOOKY ? (Color){ 150, 130, 120, 255 } : (Color){ 165, 125, 80, 255 };
        for (int i = 0; i + 1 < tr->scN; i++) {
            const TrackSample *a = &tr->sc[i], *b = &tr->sc[i + 1];
            if (InMainCorridor(tr, a->pos, -1.5f) && InMainCorridor(tr, b->pos, -1.5f)) continue;
            float hh = tr->scHalf;
            Vector3 l0 = Vector3Add(a->pos, Vector3Scale(a->right, -hh)), r0 = Vector3Add(a->pos, Vector3Scale(a->right, hh));
            Vector3 l1 = Vector3Add(b->pos, Vector3Scale(b->right, -hh)), r1 = Vector3Add(b->pos, Vector3Scale(b->right, hh));
            l0.y += 0.05f; r0.y += 0.05f; l1.y += 0.05f; r1.y += 0.05f;
            MB_QuadUV(&mb, l0, r0, r1, l1, (Vector2){ l0.x/8, l0.z/8 }, (Vector2){ r0.x/8, r0.z/8 }, (Vector2){ r1.x/8, r1.z/8 }, (Vector2){ l1.x/8, l1.z/8 },
                      tc, Vector3Add(a->pos, (Vector3){ 0, -50, 0 }), true);
        }
    }
    if (!d->noGround) {
        /* ground plane with a gentle colour gradient away from the road (sand -> sea on the beach) */
        float x0 = tr->mapMin.x - 420, x1 = tr->mapMax.x + 420, z0 = tr->mapMin.y - 420, z1 = tr->mapMax.y + 420;
        int gs = 64;
        static float gd[65][65];
        for (int gx = 0; gx <= gs; gx++) for (int gz = 0; gz <= gs; gz++) {
            float x = x0 + (x1 - x0)*gx/gs, z = z0 + (z1 - z0)*gz/gs;
            float best = 1e9f;
            for (int i = 0; i < n; i += 3) {
                float dx = x - tr->s[i].pos.x, dz = z - tr->s[i].pos.z;
                float dd = dx*dx + dz*dz;
                if (dd < best) best = dd;
            }
            gd[gx][gz] = sqrtf(best);
        }
        Color nearC = ColorScale(gc, 0.92f);
        Color farC = d->groundFar.a ? d->groundFar : nearC;
        /* ground texture is tinted by d->ground already; express the far colour relative to it */
        if (d->groundFar.a) {
            farC = (Color){ (unsigned char)Clamp(255.0f*d->groundFar.r/fmaxf(d->ground.r, 1), 0, 255),
                            (unsigned char)Clamp(255.0f*d->groundFar.g/fmaxf(d->ground.g, 1), 0, 255),
                            (unsigned char)Clamp(255.0f*d->groundFar.b/fmaxf(d->ground.b, 1), 0, 255), 255 };
            farC = ColorScale(farC, 0.92f);
        }
        Vector3 up = { 0, 1, 0 };
        for (int gx = 0; gx < gs; gx++) for (int gz = 0; gz < gs; gz++) {
            Vector3 p[4]; Color c[4]; Vector2 uv[4];
            int ix[4] = { gx, gx + 1, gx + 1, gx }, iz[4] = { gz, gz, gz + 1, gz + 1 };
            for (int k = 0; k < 4; k++) {
                float x = x0 + (x1 - x0)*ix[k]/gs, z = z0 + (z1 - z0)*iz[k]/gs;
                float f = Clamp((gd[ix[k]][iz[k]] - d->farStart)/fmaxf(d->farEnd - d->farStart, 1), 0, 1);
                f = f*f*(3 - 2*f);
                p[k] = (Vector3){ x, tr->groundY, z };
                c[k] = ColorMix(nearC, farC, f);
                uv[k] = (Vector2){ x/8, z/8 };
            }
            MB_VertexLit(&mb, p[0], uv[0], up, c[0]); MB_VertexLit(&mb, p[2], uv[2], up, c[2]); MB_VertexLit(&mb, p[1], uv[1], up, c[1]);
            MB_VertexLit(&mb, p[0], uv[0], up, c[0]); MB_VertexLit(&mb, p[3], uv[3], up, c[3]); MB_VertexLit(&mb, p[2], uv[2], up, c[2]);
        }
    }
    tr->mGround = MB_BuildModel(&mb, G.texGround[index], true);
    MB_Free(&mb);

    /* --- walls / barriers with embankment skirts --- */
    MB_Init(&mb);
    float wh = d->wallHeight;
    for (int i = 0; i < n; i++) {
        int i1 = (i + 1) % n;
        const TrackSample *a = &tr->s[i], *b = &tr->s[i1];
        Color wc = ((i/3) & 1) ? d->wallA : d->wallB;
        if (d->rainbowRoad) wc = HueColor(a->dist*1.5f + 180.0f, 0.5f, 1.0f);
        for (int sd = -1; sd <= 1; sd += 2) {
            float oa = a->edge[sd > 0 ? 1 : 0], ob = b->edge[sd > 0 ? 1 : 0];
            Vector3 in0 = Vector3Add(a->pos, Vector3Scale(a->right, sd*oa));
            Vector3 in1 = Vector3Add(b->pos, Vector3Scale(b->right, sd*ob));
            if (InShortcut(tr, in0, 0.6f) || InShortcut(tr, in1, 0.6f) || InShortcut(tr, Vector3Lerp(in0, in1, 0.5f), 0.6f)) continue; /* the secret gap */
            Vector3 out0 = Vector3Add(a->pos, Vector3Scale(a->right, sd*(oa + 0.8f)));
            Vector3 out1 = Vector3Add(b->pos, Vector3Scale(b->right, sd*(ob + 0.8f)));
            Vector3 ti0 = { in0.x, in0.y + wh, in0.z }, ti1 = { in1.x, in1.y + wh, in1.z };
            Vector3 to0 = { out0.x, out0.y + wh, out0.z }, to1 = { out1.x, out1.y + wh, out1.z };
            Vector3 farOut = Vector3Add(a->pos, Vector3Scale(a->right, sd*(oa + 30)));
            MB_Quad(&mb, in0, in1, ti1, ti0, wc, farOut);                       /* inner face */
            MB_Quad(&mb, ti0, ti1, to1, to0, ColorScale(wc, 1.05f), Vector3Add(a->pos, (Vector3){ 0, -50, 0 })); /* top */
            /* outer embankment down to the ground (or into the void) */
            float dropA = d->noGround ? 2.5f : (a->pos.y - tr->groundY);
            float dropB = d->noGround ? 2.5f : (b->pos.y - tr->groundY);
            Vector3 g0 = Vector3Add(out0, Vector3Scale(a->right, sd*(d->noGround ? 0.0f : dropA*1.3f)));
            Vector3 g1 = Vector3Add(out1, Vector3Scale(b->right, sd*(d->noGround ? 0.0f : dropB*1.3f)));
            g0.y = out0.y - dropA - 0.05f; g1.y = out1.y - dropB - 0.05f;
            Color sk = d->noGround ? ColorScale(wc, 0.5f) : ColorScale(gc.r ? d->ground : d->ground, 0.85f);
            if (d->scenery == SCENERY_MEADOW) sk = (Color){ 70, 150, 55, 255 };
            if (d->scenery == SCENERY_DESERT) sk = (Color){ 210, 165, 95, 255 };
            if (d->scenery == SCENERY_SNOW) sk = (Color){ 225, 232, 245, 255 };
            if (d->scenery == SCENERY_BEACH) sk = (Color){ 235, 215, 160, 255 };
            if (d->scenery == SCENERY_SPOOKY) sk = (Color){ 65, 72, 55, 255 };
            MB_Quad(&mb, to0, to1, g1, g0, sk, Vector3Add(a->pos, Vector3Scale(a->right, -sd*20.0f)));
        }
        if (d->noGround) {
            /* underside of the ribbon */
            Vector3 l0 = Vector3Add(a->pos, Vector3Scale(a->right, -(a->edge[0] + 0.8f))), r0 = Vector3Add(a->pos, Vector3Scale(a->right, a->edge[1] + 0.8f));
            Vector3 l1 = Vector3Add(b->pos, Vector3Scale(b->right, -(b->edge[0] + 0.8f))), r1 = Vector3Add(b->pos, Vector3Scale(b->right, b->edge[1] + 0.8f));
            l0.y -= 2.55f; r0.y -= 2.55f; l1.y -= 2.55f; r1.y -= 2.55f;
            MB_Quad(&mb, l0, r0, r1, l1, (Color){ 60, 40, 110, 255 }, Vector3Add(a->pos, (Vector3){ 0, 50, 0 }));
        }
    }
    /* shortcut fences + causeway sides */
    for (int i = 0; i + 1 < tr->scN; i++) {
        const TrackSample *a = &tr->sc[i], *b = &tr->sc[i + 1];
        for (int sd = -1; sd <= 1; sd += 2) {
            Vector3 in0 = Vector3Add(a->pos, Vector3Scale(a->right, sd*tr->scHalf));
            Vector3 in1 = Vector3Add(b->pos, Vector3Scale(b->right, sd*tr->scHalf));
            if (InMainCorridor(tr, in0, 0.5f) || InMainCorridor(tr, in1, 0.5f)) continue;
            float fh = 0.7f;
            Color fc = d->scIsRoad ? HueColor(i*12.0f, 0.4f, 1.0f) : ((i & 1) ? (Color){ 150, 100, 60, 255 } : (Color){ 120, 80, 45, 255 });
            Vector3 t0 = { in0.x, in0.y + fh, in0.z }, t1 = { in1.x, in1.y + fh, in1.z };
            Vector3 out0 = Vector3Add(in0, Vector3Scale(a->right, sd*0.5f)), out1 = Vector3Add(in1, Vector3Scale(b->right, sd*0.5f));
            Vector3 to0 = { out0.x, out0.y + fh, out0.z }, to1 = { out1.x, out1.y + fh, out1.z };
            MB_Quad(&mb, in0, in1, t1, t0, fc, Vector3Add(a->pos, Vector3Scale(a->right, sd*30)));
            MB_Quad(&mb, t0, t1, to1, to0, ColorScale(fc, 1.1f), Vector3Add(a->pos, (Vector3){ 0, -50, 0 }));
            float drop = d->noGround ? 2.5f : (a->pos.y - tr->groundY);
            Vector3 g0 = Vector3Add(out0, Vector3Scale(a->right, sd*(d->noGround ? 0 : drop*1.3f)));
            Vector3 g1 = Vector3Add(out1, Vector3Scale(b->right, sd*(d->noGround ? 0 : drop*1.3f)));
            g0.y = out0.y - drop - 0.05f; g1.y = out1.y - drop - 0.05f;
            Color sk = d->noGround ? (Color){ 60, 40, 110, 255 } : d->scenery == SCENERY_SNOW ? (Color){ 225, 232, 245, 255 } :
                       d->scenery == SCENERY_BEACH ? (Color){ 235, 215, 160, 255 } : d->scenery == SCENERY_SPOOKY ? (Color){ 65, 72, 55, 255 } :
                       d->scenery == SCENERY_DESERT ? (Color){ 210, 165, 95, 255 } : (Color){ 70, 150, 55, 255 };
            MB_Quad(&mb, out0, out1, g1, g0, sk, Vector3Add(a->pos, Vector3Scale(a->right, -sd*20.0f)));
        }
        if (d->noGround) {
            Vector3 l0 = Vector3Add(a->pos, Vector3Scale(a->right, -(tr->scHalf + 0.5f))), r0 = Vector3Add(a->pos, Vector3Scale(a->right, tr->scHalf + 0.5f));
            Vector3 l1 = Vector3Add(b->pos, Vector3Scale(b->right, -(tr->scHalf + 0.5f))), r1 = Vector3Add(b->pos, Vector3Scale(b->right, tr->scHalf + 0.5f));
            l0.y -= 2.55f; r0.y -= 2.55f; l1.y -= 2.55f; r1.y -= 2.55f;
            MB_Quad(&mb, l0, r0, r1, l1, (Color){ 60, 40, 110, 255 }, Vector3Add(a->pos, (Vector3){ 0, 50, 0 }));
        }
    }
    tr->mWalls = MB_BuildModel(&mb, G.texWhite, true);
    MB_Free(&mb);

    MB_Init(&mb);
    BuildScenery(tr, &mb);
    tr->mScenery = MB_BuildModel(&mb, G.texWhite, true);
    MB_Free(&mb);

    MB_Init(&mb);
    BuildSky(tr, &mb);
    tr->mSky = MB_BuildModel(&mb, G.texWhite, false);
    MB_Free(&mb);

    tr->loaded = true;
    TraceLog(LOG_INFO, "TRACK: built '%s' (%d samples, length %.0f)", d->name, n, tr->length);
}

void TrackUnload(Track *tr)
{
    if (!tr->loaded) return;
    UnloadModel(tr->mRoad); UnloadModel(tr->mGround); UnloadModel(tr->mWalls);
    UnloadModel(tr->mScenery); UnloadModel(tr->mSky);
    tr->loaded = false;
}

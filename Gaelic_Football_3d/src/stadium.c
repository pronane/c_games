/*  stadium.c - lighting, static shadow map, procedural stadium, pitch and sky.
 *  #included from main.c (unity build: the build scripts still compile just
 *  main.c + game.c).
 *
 *  Look references: Croke Park (tiered blue seats under a cantilever roof,
 *  Hill 16 terrace at one end), a county ground covered stand with yellow and
 *  blue seats and open terraces, and striped mowed grass.
 *
 *  World space: pitch centre at the origin, x along the pitch (-70..70),
 *  z across it (-42.5..42.5), y up. The broadcast camera sits on +z looking
 *  toward the main (far) stand on -z.
 */
#include "rlgl.h"

/* ---- shaders --------------------------------------------------------------- */
static const char *LIT_VS =
"#version 330\n"
"in vec3 vertexPosition; in vec2 vertexTexCoord; in vec3 vertexNormal; in vec4 vertexColor;\n"
"uniform mat4 mvp; uniform mat4 matModel; uniform mat4 matNormal;\n"
"uniform float uTime; uniform float uExcite;\n"
"out vec3 fragPosition; out vec2 fragTexCoord; out vec4 fragColor; out vec3 fragNormal;\n"
"void main(){\n"
"  vec3 p = vertexPosition; vec4 c = vertexColor;\n"
"  if (abs(c.a - 254.0/255.0) < 0.002) {            /* crowd figure: bob / jump with excitement */\n"
"    float ph = p.x*1.37 + p.z*0.91 + p.y*0.5;\n"
"    float b = max(0.0, sin(uTime*(2.0 + uExcite*7.0) + ph*3.0));\n"
"    p.y += b*(0.015 + 0.30*uExcite); c.a = 1.0;\n"
"  }\n"
"  fragPosition = vec3(matModel*vec4(p,1.0));\n"
"  fragTexCoord = vertexTexCoord; fragColor = c;\n"
"  fragNormal = normalize(vec3(matNormal*vec4(vertexNormal,0.0)));\n"
"  gl_Position = mvp*vec4(p,1.0);\n"
"}\n";

static const char *LIT_FS =
"#version 330\n"
"in vec3 fragPosition; in vec2 fragTexCoord; in vec4 fragColor; in vec3 fragNormal;\n"
"uniform sampler2D texture0; uniform vec4 colDiffuse;\n"
"uniform vec3 lightDir; uniform vec3 sunColor; uniform vec3 skyColor; uniform vec3 groundColor; uniform vec3 hazeColor;\n"
"uniform vec3 viewPos; uniform mat4 lightVP; uniform sampler2D shadowMap; uniform int useShadow; uniform float shadowTexel;\n"
"out vec4 finalColor;\n"
"void main(){\n"
"  vec4 tex = texture(texture0, fragTexCoord)*colDiffuse*fragColor;\n"
"  if (tex.a < 0.02) discard;\n"
"  vec3 n = normalize(fragNormal);\n"
"  if (!gl_FrontFacing) n = -n;\n"
"  vec3 l = -lightDir;\n"
"  float ndl = max(dot(n,l), 0.0);\n"
"  float sh = 1.0;\n"
"  if (useShadow >= 1) {\n"
"    vec4 lp = lightVP*vec4(fragPosition,1.0); vec3 sc = lp.xyz/lp.w*0.5 + 0.5;\n"
"    if (sc.x > 0.0 && sc.x < 1.0 && sc.y > 0.0 && sc.y < 1.0 && sc.z < 1.0) {\n"
"      float bias = 0.0006 + 0.0012*(1.0 - ndl); float s = 0.0;\n"
"      if (useShadow == 2) {\n"
"        for (int x = -1; x <= 1; x++) for (int y = -1; y <= 1; y++)\n"
"          s += (sc.z - bias > texture(shadowMap, sc.xy + vec2(x,y)*shadowTexel).r) ? 1.0 : 0.0;\n"
"        sh = 1.0 - s/9.0;\n"
"      } else sh = (sc.z - bias > texture(shadowMap, sc.xy).r) ? 0.0 : 1.0;\n"
"    }\n"
"  }\n"
"  vec3 amb = mix(groundColor, skyColor, n.y*0.5 + 0.5);\n"
"  vec3 v = normalize(viewPos - fragPosition);\n"
"  float rim = pow(1.0 - max(dot(n, v), 0.0), 3.0)*0.12;\n"
"  vec3 col = tex.rgb*(amb + sunColor*ndl*sh) + rim*skyColor*tex.rgb;\n"
"  float d = length(viewPos - fragPosition);\n"
"  col = mix(col, hazeColor, clamp((d - 220.0)/1400.0, 0.0, 0.65));\n"
"  finalColor = vec4(col, tex.a);\n"
"}\n";

static const char *FLAT_VS =
"#version 330\n"
"in vec3 vertexPosition; uniform mat4 mvp;\n"
"void main(){ gl_Position = mvp*vec4(vertexPosition,1.0); }\n";
static const char *FLAT_FS =
"#version 330\n"
"uniform vec4 colDiffuse; out vec4 finalColor;\n"
"void main(){ finalColor = colDiffuse; }\n";

/* GPU-skinned characters (raylib 5.x: UpdateModelAnimationBones + bone matrices uniform) */
#define SKIN_COMMON \
"#version 330\n" \
"in vec3 vertexPosition; in vec2 vertexTexCoord; in vec3 vertexNormal; in vec4 vertexColor;\n" \
"in vec4 vertexBoneIds; in vec4 vertexBoneWeights;\n" \
"#define MAX_BONE_NUM 64\n" \
"uniform mat4 boneMatrices[MAX_BONE_NUM];\n" \
"uniform mat4 mvp; uniform mat4 matModel; uniform mat4 matNormal;\n" \
"mat4 skinMat(){\n" \
"  return vertexBoneWeights.x*boneMatrices[int(vertexBoneIds.x)] + vertexBoneWeights.y*boneMatrices[int(vertexBoneIds.y)]\n" \
"       + vertexBoneWeights.z*boneMatrices[int(vertexBoneIds.z)] + vertexBoneWeights.w*boneMatrices[int(vertexBoneIds.w)];\n" \
"}\n"
static const char *SKIN_VS = SKIN_COMMON
"out vec3 fragPosition; out vec2 fragTexCoord; out vec4 fragColor; out vec3 fragNormal;\n"
"void main(){\n"
"  mat4 sk = skinMat();\n"
"  vec4 p = sk*vec4(vertexPosition,1.0);\n"
"  vec3 n = mat3(sk)*vertexNormal;\n"
"  fragPosition = vec3(matModel*p); fragTexCoord = vertexTexCoord; fragColor = vertexColor;\n"
"  fragNormal = normalize(vec3(matNormal*vec4(n,0.0)));\n"
"  gl_Position = mvp*p;\n"
"}\n";
static const char *FLAT_SKIN_VS = SKIN_COMMON
"void main(){ gl_Position = mvp*(skinMat()*vec4(vertexPosition,1.0)); }\n";

static Shader litShader, flatShader, skinShader, flatSkinShader;
static int gpuSkin;                 /* 1 = characters skinned in the vertex shader */
static int gpuSkinAvailable;
static int gfxQuality = 0;          /* 0 Low, 1 Medium, 2 High */
static const char *QUALITY_NAMES[3] = { "Low", "Medium", "High" };
typedef struct { int view, lightVP, shadowMap, useShadow, time, excite; } LitLocs;
static LitLocs litLocs[2];
static int haveLit;
static Vector3 sunDir;                       /* direction the light travels */
static RenderTexture2D shadowRT;
static Matrix lightVP;
#define SHADOW_RES 2048
#define SHADOW_SLOT 12

/* ---- mesh builder -------------------------------------------------------- */
typedef struct { float *v, *n, *t; unsigned char *c; int count, cap; } MB;

static void mbVert(MB *m, Vector3 p, Vector3 n, float u, float w, Color c)
{
    if (m->count == m->cap) {
        m->cap = m->cap ? m->cap * 2 : 4096;
        m->v = RL_REALLOC(m->v, m->cap * 3 * sizeof(float));
        m->n = RL_REALLOC(m->n, m->cap * 3 * sizeof(float));
        m->t = RL_REALLOC(m->t, m->cap * 2 * sizeof(float));
        m->c = RL_REALLOC(m->c, m->cap * 4);
    }
    int i = m->count++;
    m->v[i * 3] = p.x; m->v[i * 3 + 1] = p.y; m->v[i * 3 + 2] = p.z;
    m->n[i * 3] = n.x; m->n[i * 3 + 1] = n.y; m->n[i * 3 + 2] = n.z;
    m->t[i * 2] = u; m->t[i * 2 + 1] = w;
    m->c[i * 4] = c.r; m->c[i * 4 + 1] = c.g; m->c[i * 4 + 2] = c.b; m->c[i * 4 + 3] = c.a;
}

/* quad a-b-c-d (any winding); 'face' is the direction it should face */
static void mbQuad(MB *m, Vector3 a, Vector3 b, Vector3 c, Vector3 d, Vector3 face, Color col)
{
    Vector3 n = Vector3CrossProduct(Vector3Subtract(b, a), Vector3Subtract(c, a));
    if (Vector3DotProduct(n, face) < 0) { Vector3 t = b; b = d; d = t; n = Vector3Negate(n); }
    n = Vector3Normalize(n);
    mbVert(m, a, n, 0, 0, col); mbVert(m, b, n, 1, 0, col); mbVert(m, c, n, 1, 1, col);
    mbVert(m, a, n, 0, 0, col); mbVert(m, c, n, 1, 1, col); mbVert(m, d, n, 0, 1, col);
}

static Color shade(Color c, float k)
{
    return (Color){ (unsigned char)Clamp(c.r * k, 0, 255), (unsigned char)Clamp(c.g * k, 0, 255), (unsigned char)Clamp(c.b * k, 0, 255), c.a };
}

/* axis-aligned box (min corner lo, max corner hi) */
static void mbBox(MB *m, Vector3 lo, Vector3 hi, Color c)
{
    Vector3 p[8];
    for (int i = 0; i < 8; i++) p[i] = (Vector3){ i & 1 ? hi.x : lo.x, i & 2 ? hi.y : lo.y, i & 4 ? hi.z : lo.z };
    mbQuad(m, p[2], p[3], p[7], p[6], (Vector3){ 0, 1, 0 }, c);
    mbQuad(m, p[0], p[1], p[3], p[2], (Vector3){ 0, 0, -1 }, shade(c, 0.95f));
    mbQuad(m, p[4], p[5], p[7], p[6], (Vector3){ 0, 0, 1 }, shade(c, 0.95f));
    mbQuad(m, p[0], p[4], p[6], p[2], (Vector3){ -1, 0, 0 }, shade(c, 0.9f));
    mbQuad(m, p[1], p[5], p[7], p[3], (Vector3){ 1, 0, 0 }, shade(c, 0.9f));
}

static Model mbModel(MB *m)
{
    Mesh mesh = { 0 };
    mesh.vertexCount = m->count; mesh.triangleCount = m->count / 3;
    mesh.vertices = m->v; mesh.normals = m->n; mesh.texcoords = m->t; mesh.colors = m->c;
    UploadMesh(&mesh, false);
    Model mo = LoadModelFromMesh(mesh);
    if (haveLit) mo.materials[0].shader = litShader;
    memset(m, 0, sizeof *m);
    return mo;
}

/* ---- deterministic hash noise ---------------------------------------------- */
static unsigned int hsh(unsigned int x) { x ^= x >> 16; x *= 0x7feb352dU; x ^= x >> 15; x *= 0x846ca68bU; x ^= x >> 16; return x; }
static float rnd01(unsigned int a, unsigned int b) { return (float)(hsh(a * 73856093U ^ hsh(b + 0x9e3779b9U)) & 0xFFFFFF) / 16777215.0f; }

/* ---- stands ------------------------------------------------------------------ */
typedef struct { int rows; float depth, rise, start, y0; } Tier;
typedef struct { Vector3 p, out; } PathPt;

/* seat colour schemes */
enum { SEATS_CROKE, SEATS_COUNTY, SEATS_TERRACE, SEATS_HILL };

static Color crowdColor(unsigned int a, unsigned int b, int scheme)
{
    static const Color pal[] = {
        { 40, 70, 200, 255 }, { 250, 215, 30, 255 }, { 200, 20, 40, 255 }, { 20, 150, 40, 255 },
        { 235, 235, 235, 255 }, { 35, 35, 45, 255 }, { 110, 170, 230, 255 }, { 70, 70, 80, 255 },
        { 160, 120, 90, 255 }, { 25, 45, 110, 255 } };
    float r = rnd01(a, b * 7 + 3);
    if (scheme == SEATS_HILL) return r < 0.55f ? pal[6] : r < 0.8f ? pal[9] : pal[(int)(r * 97) % 10];
    return pal[(int)(r * 1000) % 10];
}

static Color seatColor(int scheme, int row, int seg, int tier)
{
    switch (scheme) {
    case SEATS_CROKE: return tier == 1 ? (Color){ 24, 52, 128, 255 } : (Color){ 30, 66, 150, 255 };
    case SEATS_COUNTY: return ((seg / 6) + (row / 7)) % 2 ? (Color){ 232, 196, 30, 255 } : (Color){ 28, 70, 165, 255 };
    default: return (Color){ 150, 148, 140, 255 };
    }
}

/* Build tiers of rows along a sampled path (front edge, outward normals).
 * Every row is a tread + riser per path segment; spectators are small
 * two-tone figures. 'aisleEvery' segments a grey stair aisle is left. */
static void buildStand(MB *m, const PathPt *path, int np, const Tier *tiers, int nt, int scheme,
                       float fill, int standing, int aisleEvery, unsigned int seed)
{
    Color concrete = { 150, 148, 140, 255 };
    for (int ti = 0; ti < nt; ti++) {
        const Tier *T = &tiers[ti];
        /* tier front wall */
        for (int i = 0; i + 1 < np; i++) {
            Vector3 a = Vector3Add(path[i].p, Vector3Scale(path[i].out, T->start));
            Vector3 b = Vector3Add(path[i + 1].p, Vector3Scale(path[i + 1].out, T->start));
            float yb = ti == 0 ? 0.0f : T->y0 - 2.6f;
            Vector3 face = Vector3Negate(path[i].out);
            mbQuad(m, (Vector3){ a.x, yb, a.z }, (Vector3){ b.x, yb, b.z }, (Vector3){ b.x, T->y0, b.z }, (Vector3){ a.x, T->y0, a.z }, face,
                   ti == 0 ? (Color){ 40, 90, 60, 255 } : (Color){ 210, 210, 205, 255 });
            if (ti > 0) {   /* soffit under the tier front */
                Vector3 a2 = Vector3Add(a, Vector3Scale(path[i].out, 6.0f)), b2 = Vector3Add(b, Vector3Scale(path[i + 1].out, 6.0f));
                mbQuad(m, (Vector3){ a.x, yb, a.z }, (Vector3){ b.x, yb, b.z }, (Vector3){ b2.x, yb, b2.z }, (Vector3){ a2.x, yb, a2.z }, (Vector3){ 0, -1, 0 }, (Color){ 120, 120, 125, 255 });
            }
        }
        for (int r = 0; r < T->rows; r++) {
            float d0 = T->start + r * T->depth, d1 = d0 + T->depth;
            float y = T->y0 + (r + 1) * T->rise, yPrev = T->y0 + r * T->rise;
            for (int i = 0; i + 1 < np; i++) {
                Vector3 o0 = path[i].out, o1 = path[i + 1].out;
                Vector3 a0 = Vector3Add(path[i].p, Vector3Scale(o0, d0)), b0 = Vector3Add(path[i + 1].p, Vector3Scale(o1, d0));
                Vector3 a1 = Vector3Add(path[i].p, Vector3Scale(o0, d1)), b1 = Vector3Add(path[i + 1].p, Vector3Scale(o1, d1));
                int aisle = aisleEvery > 0 && (i % aisleEvery) == 0;
                Color sc = aisle ? concrete : seatColor(scheme, r, i, ti);
                if (standing && !aisle) sc = (r % 2) ? (Color){ 140, 138, 132, 255 } : (Color){ 156, 154, 148, 255 };
                a0.y = b0.y = a1.y = b1.y = y;
                mbQuad(m, a0, b0, b1, a1, (Vector3){ 0, 1, 0 }, sc);
                Vector3 ra = { a0.x, yPrev, a0.z }, rb = { b0.x, yPrev, b0.z };
                mbQuad(m, ra, rb, b0, a0, Vector3Negate(o0), shade(sc, 0.7f));
                /* crush barriers on terraces */
                if (standing && r % 6 == 5 && !aisle) {
                    Vector3 c0 = Vector3Add(a0, Vector3Scale(o0, T->depth * 0.3f)), c1 = Vector3Add(b0, Vector3Scale(o1, T->depth * 0.3f));
                    mbQuad(m, (Vector3){ c0.x, y + 0.95f, c0.z }, (Vector3){ c1.x, y + 0.95f, c1.z }, (Vector3){ c1.x, y + 1.05f, c1.z }, (Vector3){ c0.x, y + 1.05f, c0.z },
                           Vector3Negate(o0), (Color){ 60, 80, 110, 255 });
                }
                if (aisle) continue;
                /* spectators */
                float segLen = Vector3Distance(a0, b0);
                float spacing = standing ? 0.52f : 0.55f;
                int nper = (int)(segLen / spacing);
                for (int k = 0; k < nper; k++) {
                    unsigned int id = seed * 100003U + (unsigned)(ti * 1000 + r) * 4099U + (unsigned)i * 31U + (unsigned)k;
                    if (rnd01(id, 11) > fill) continue;
                    float u = (k + 0.5f + (rnd01(id, 5) - 0.5f) * 0.25f) / nper;
                    Vector3 base = Vector3Lerp(Vector3Add(a0, Vector3Scale(o0, T->depth * 0.45f)), Vector3Add(b0, Vector3Scale(o1, T->depth * 0.45f)), u);
                    Vector3 out = Vector3Normalize(Vector3Lerp(o0, o1, u));
                    Vector3 side = { -out.z, 0, out.x };
                    float h0 = standing ? 0.55f : 0.08f, h1 = (standing ? 1.38f : 0.68f) + (rnd01(id, 9) - 0.5f) * 0.12f;
                    float hw = 0.19f;
                    Color shirt = crowdColor(id, seed, scheme == SEATS_HILL ? SEATS_HILL : scheme), skin = (Color){ 214, 170, 140, 254 };
                    shirt.a = 254;
                    Vector3 fwd = Vector3Negate(out);
                    Vector3 l = Vector3Add(base, Vector3Scale(side, -hw)), rr = Vector3Add(base, Vector3Scale(side, hw));
                    mbQuad(m, (Vector3){ l.x, base.y + h0, l.z }, (Vector3){ rr.x, base.y + h0, rr.z }, (Vector3){ rr.x, base.y + h1, rr.z }, (Vector3){ l.x, base.y + h1, l.z }, fwd, shirt);
                    Vector3 lb = Vector3Add(l, Vector3Scale(out, 0.22f)), rbk = Vector3Add(rr, Vector3Scale(out, 0.22f));
                    mbQuad(m, (Vector3){ l.x, base.y + h1, l.z }, (Vector3){ rr.x, base.y + h1, rr.z }, (Vector3){ rbk.x, base.y + h1, rbk.z }, (Vector3){ lb.x, base.y + h1, lb.z }, (Vector3){ 0, 1, 0 }, shade(shirt, 1.0f));
                    Vector3 hl = Vector3Add(base, Vector3Scale(side, -0.1f)), hr = Vector3Add(base, Vector3Scale(side, 0.1f));
                    hl = Vector3Add(hl, Vector3Scale(out, 0.05f)); hr = Vector3Add(hr, Vector3Scale(out, 0.05f));
                    mbQuad(m, (Vector3){ hl.x, base.y + h1 + 0.02f, hl.z }, (Vector3){ hr.x, base.y + h1 + 0.02f, hr.z }, (Vector3){ hr.x, base.y + h1 + 0.24f, hr.z }, (Vector3){ hl.x, base.y + h1 + 0.24f, hl.z }, fwd, skin);
                }
            }
        }
        /* end walls of the tier (profile closed off) */
        for (int e = 0; e < 2; e++) {
            const PathPt *pp = &path[e ? np - 1 : 0];
            Vector3 along = e ? Vector3Subtract(path[np - 1].p, path[np - 2].p) : Vector3Subtract(path[0].p, path[1].p);
            along = Vector3Normalize(along);
            for (int r = 0; r < T->rows; r++) {
                float d0 = T->start + r * T->depth, d1 = d0 + T->depth, y = T->y0 + (r + 1) * T->rise;
                Vector3 a = Vector3Add(pp->p, Vector3Scale(pp->out, d0)), b = Vector3Add(pp->p, Vector3Scale(pp->out, d1));
                float yb = ti == 0 ? 0.0f : T->y0 - 2.6f;
                mbQuad(m, (Vector3){ a.x, yb, a.z }, (Vector3){ b.x, yb, b.z }, (Vector3){ b.x, y, b.z }, (Vector3){ a.x, y, a.z }, along, (Color){ 175, 172, 165, 255 });
            }
        }
    }
}

/* glazed corporate-box band between tiers + back facade + cantilever roof */
static void buildBand(MB *m, const PathPt *path, int np, float d, float y0, float y1, Color c)
{
    for (int i = 0; i + 1 < np; i++) {
        Vector3 a = Vector3Add(path[i].p, Vector3Scale(path[i].out, d)), b = Vector3Add(path[i + 1].p, Vector3Scale(path[i + 1].out, d));
        Color cc = (i % 3 == 0) ? shade(c, 0.75f) : c;
        mbQuad(m, (Vector3){ a.x, y0, a.z }, (Vector3){ b.x, y0, b.z }, (Vector3){ b.x, y1, b.z }, (Vector3){ a.x, y1, a.z }, Vector3Negate(path[i].out), cc);
    }
}

static void buildRoof(MB *m, const PathPt *path, int np, float dFront, float dBack, float yFront, float yBack,
                      int columns, float colD, int translucentEdge)
{
    Color top = { 175, 178, 182, 255 }, under = { 92, 96, 104, 255 }, fascia = { 225, 228, 230, 255 };
    for (int i = 0; i + 1 < np; i++) {
        Vector3 o0 = path[i].out, o1 = path[i + 1].out;
        Vector3 f0 = Vector3Add(path[i].p, Vector3Scale(o0, dFront)), f1 = Vector3Add(path[i + 1].p, Vector3Scale(o1, dFront));
        Vector3 k0 = Vector3Add(path[i].p, Vector3Scale(o0, dBack)), k1 = Vector3Add(path[i + 1].p, Vector3Scale(o1, dBack));
        f0.y = f1.y = yFront; k0.y = k1.y = yBack;
        mbQuad(m, f0, f1, k1, k0, (Vector3){ 0, 1, 0 }, top);
        Vector3 f0u = { f0.x, yFront - 1.2f, f0.z }, f1u = { f1.x, yFront - 1.2f, f1.z };
        Vector3 k0u = { k0.x, yBack - 1.2f, k0.z }, k1u = { k1.x, yBack - 1.2f, k1.z };
        mbQuad(m, f0u, f1u, k1u, k0u, (Vector3){ 0, -1, 0 }, under);
        mbQuad(m, f0u, f1u, f1, f0, Vector3Negate(o0), fascia);
        /* back facade down to the ground */
        mbQuad(m, (Vector3){ k0.x, 0, k0.z }, (Vector3){ k1.x, 0, k1.z }, k1, k0, o0, (i % 2) ? (Color){ 160, 162, 168, 255 } : (Color){ 150, 152, 158, 255 });
        if (translucentEdge) {
            Vector3 e0 = Vector3Add(f0, Vector3Scale(o0, -5.0f)), e1 = Vector3Add(f1, Vector3Scale(o1, -5.0f));
            e0.y = e1.y = yFront - 0.4f;
            mbQuad(m, e0, e1, f1, f0, (Vector3){ 0, 1, 0 }, (Color){ 205, 215, 225, 150 });
            mbQuad(m, e0, e1, f1, f0, (Vector3){ 0, -1, 0 }, (Color){ 170, 180, 190, 150 });
        }
        if (columns && i % columns == 0) {
            Vector3 c = Vector3Add(path[i].p, Vector3Scale(o0, colD));
            mbBox(m, (Vector3){ c.x - 0.15f, 0, c.z - 0.15f }, (Vector3){ c.x + 0.15f, yFront + (yBack - yFront) * ((colD - dFront) / (dBack - dFront)) - 1.0f, c.z + 0.15f }, (Color){ 40, 70, 55, 255 });
        }
    }
}

/* straight path from a to b, outward normal 'out', segment length 'step' */
static int pathLine(PathPt *pp, int max, Vector3 a, Vector3 b, Vector3 out, float step)
{
    int n = (int)ceilf(Vector3Distance(a, b) / step);
    if (n + 1 > max) n = max - 1;
    for (int i = 0; i <= n; i++) { pp[i].p = Vector3Lerp(a, b, (float)i / n); pp[i].out = out; }
    return n + 1;
}

/* arc around centre c, radius r, angles in radians (angle 0 = +x, pi/2 = +z) */
static int pathArc(PathPt *pp, int max, Vector3 c, float r, float a0, float a1, float stepDeg)
{
    int n = (int)ceilf(fabsf(a1 - a0) * RAD2DEG / stepDeg);
    if (n + 1 > max) n = max - 1;
    for (int i = 0; i <= n; i++) {
        float a = a0 + (a1 - a0) * i / n;
        pp[i].out = (Vector3){ cosf(a), 0, sinf(a) };
        pp[i].p = Vector3Add(c, Vector3Scale(pp[i].out, r));
    }
    return n + 1;
}

/* ---- stadium state ------------------------------------------------------- */
#define MAX_STATIC 24
static Model staticModels[MAX_STATIC];
static int staticCount;
static Model pitchModel, apronModel, groundModel, skyModel, ballModel;
static Texture2D pitchTex, apronTex, skyTex;
static int haveStadium;
static __attribute__((unused)) Model postModel;
static float crowdExcite = 0.15f;

static long staticVerts;
static void addStatic(MB *m) { if (m->count && staticCount < MAX_STATIC) { staticVerts += m->count; staticModels[staticCount++] = mbModel(m); } }

#define PITCH_TEX_W 3072
#define PITCH_TEX_H 1946
#define PITCH_TEX_MARGIN 5.0f
#define PITCH_PX ((float)PITCH_TEX_W / (GAME_PITCH_LENGTH + 2 * PITCH_TEX_MARGIN))

/* anti-aliased line painter in game coordinates (x 0..140, z 0..85) */
static void paintSeg(Color *px, float x0, float z0, float x1, float z1, float width)
{
    float s = PITCH_PX;
    float ax = (x0 + PITCH_TEX_MARGIN) * s, ay = (z0 + PITCH_TEX_MARGIN) * s;
    float bx = (x1 + PITCH_TEX_MARGIN) * s, by = (z1 + PITCH_TEX_MARGIN) * s;
    float hw = width * 0.5f * s;
    int minx = (int)fmaxf(0, fminf(ax, bx) - hw - 2), maxx = (int)fminf(PITCH_TEX_W - 1, fmaxf(ax, bx) + hw + 2);
    int miny = (int)fmaxf(0, fminf(ay, by) - hw - 2), maxy = (int)fminf(PITCH_TEX_H - 1, fmaxf(ay, by) + hw + 2);
    float dx = bx - ax, dy = by - ay, L2 = dx * dx + dy * dy;
    for (int y = miny; y <= maxy; y++)
        for (int x = minx; x <= maxx; x++) {
            float t = L2 > 0 ? Clamp(((x + 0.5f - ax) * dx + (y + 0.5f - ay) * dy) / L2, 0, 1) : 0;
            float ex = ax + t * dx - (x + 0.5f), ey = ay + t * dy - (y + 0.5f);
            float cov = Clamp(hw + 0.5f - sqrtf(ex * ex + ey * ey), 0, 1);
            if (cov <= 0) continue;
            Color *p = &px[y * PITCH_TEX_W + x];
            p->r = (unsigned char)Lerp(p->r, 236, cov); p->g = (unsigned char)Lerp(p->g, 238, cov); p->b = (unsigned char)Lerp(p->b, 230, cov);
        }
}

static void paintArc(Color *px, float cx, float cz, float r, float a0, float a1, float width)
{
    int n = (int)(fabsf(a1 - a0) * r / 0.4f) + 2;
    for (int i = 0; i < n; i++) {
        float t0 = a0 + (a1 - a0) * i / n, t1 = a0 + (a1 - a0) * (i + 1) / n;
        paintSeg(px, cx + r * cosf(t0), cz + r * sinf(t0), cx + r * cosf(t1), cz + r * sinf(t1), width);
    }
}

/* Striped grass with every GAA marking baked in (Rule Book 2026, football;
 * the 65 m lines are hurling lines, shown as on shared county pitches). */
static Texture2D makePitchTexture(void)
{
    Color *px = RL_MALLOC(sizeof(Color) * PITCH_TEX_W * PITCH_TEX_H);
    float s = PITCH_PX;
    for (int y = 0; y < PITCH_TEX_H; y++)
        for (int x = 0; x < PITCH_TEX_W; x++) {
            float gx = x / s - PITCH_TEX_MARGIN, gz = y / s - PITCH_TEX_MARGIN;
            int band = (int)floorf((gx + 70.0f) / 7.0f);           /* mown bands across the pitch */
            int cross = (int)floorf((gz + 85.0f) / 10.625f);
            float k = (band % 2 ? 1.0f : 0.86f) * (cross % 2 ? 1.0f : 0.965f);
            float n = 0.92f + 0.16f * rnd01((unsigned)x, (unsigned)y) * 0.6f + 0.05f * rnd01((unsigned)(x / 7), (unsigned)(y / 7));
            float wear = 1.0f;
            {   /* goalmouth wear */
                float ex = fminf(gx, 140 - gx), ez = gz - 42.5f;
                float d2 = ex * ex * 0.5f + ez * ez * 0.15f;
                if (ex > -1 && d2 < 30.0f) wear = 0.86f + 0.14f * d2 / 30.0f;
            }
            float r = 58 * k * n, g = 128 * k * n * wear, b = 46 * k * n;
            if (wear < 1.0f) { r += (1 - wear) * 120; b += (1 - wear) * 60; }
            px[y * PITCH_TEX_W + x] = (Color){ (unsigned char)Clamp(r, 0, 255), (unsigned char)Clamp(g, 0, 255), (unsigned char)Clamp(b, 0, 255), 255 };
        }
    const float LW = 0.10f, L = GAME_PITCH_LENGTH, Wd = GAME_PITCH_WIDTH, cz = Wd * 0.5f;
    /* boundary */
    paintSeg(px, 0, 0, L, 0, LW); paintSeg(px, 0, Wd, L, Wd, LW);
    paintSeg(px, 0, 0, 0, Wd, LW); paintSeg(px, L, 0, L, Wd, LW);
    /* 13, 20, 45 (football) and 65 (hurling) lines from each end */
    float lines[] = { 13, 20, 45, 65 };
    for (int e = 0; e < 2; e++)
        for (int i = 0; i < 4; i++) { float x = e ? L - lines[i] : lines[i]; paintSeg(px, x, 0, x, Wd, LW); }
    /* halfway: 10 m centre line plus 5 m dashes at 5 m intervals */
    paintSeg(px, L * 0.5f, cz - 5, L * 0.5f, cz + 5, LW);
    for (float z = 0; z < cz - 5; z += 10) { paintSeg(px, L * 0.5f, z, L * 0.5f, z + 5, LW); paintSeg(px, L * 0.5f, Wd - z - 5, L * 0.5f, Wd - z, LW); }
    for (int e = 0; e < 2; e++) {
        float gx = e ? L : 0, sg = e ? -1.0f : 1.0f;
        /* small rectangle 14 m x 4.5 m, large rectangle 19 m x 13 m */
        paintSeg(px, gx, cz - 7, gx + sg * 4.5f, cz - 7, LW); paintSeg(px, gx, cz + 7, gx + sg * 4.5f, cz + 7, LW);
        paintSeg(px, gx + sg * 4.5f, cz - 7, gx + sg * 4.5f, cz + 7, LW);
        paintSeg(px, gx, cz - GAME_LARGE_RECT_HALF, gx + sg * 13, cz - GAME_LARGE_RECT_HALF, LW);
        paintSeg(px, gx, cz + GAME_LARGE_RECT_HALF, gx + sg * 13, cz + GAME_LARGE_RECT_HALF, LW);
        /* penalty mark at 11 m */
        paintSeg(px, gx + sg * GAME_PENALTY_SPOT - 0.15f, cz, gx + sg * GAME_PENALTY_SPOT + 0.15f, cz, 0.3f);
        /* 20 m D: 13 m semicircle off the 20 m line */
        if (e == 0) paintArc(px, 20, cz, 13, -PI / 2, PI / 2, LW);
        else paintArc(px, L - 20, cz, 13, PI / 2, 3 * PI / 2, LW);
        /* 40 m two-point arc from the centre of the goal to the end line */
        if (e == 0) paintArc(px, 0, cz, GAME_SCORING_ARC, -PI / 2, PI / 2, LW);
        else paintArc(px, L, cz, GAME_SCORING_ARC, PI / 2, 3 * PI / 2, LW);
    }
    Image img = { px, PITCH_TEX_W, PITCH_TEX_H, 1, PIXELFORMAT_UNCOMPRESSED_R8G8B8A8 };
    Texture2D t = LoadTextureFromImage(img);
    GenTextureMipmaps(&t);
    SetTextureFilter(t, TEXTURE_FILTER_ANISOTROPIC_8X);
    SetTextureWrap(t, TEXTURE_WRAP_CLAMP);
    UnloadImage(img);
    return t;
}

static Texture2D makeNoiseGrass(int w, int h, Color base, float stripe)
{
    Color *px = RL_MALLOC(sizeof(Color) * w * h);
    for (int y = 0; y < h; y++) for (int x = 0; x < w; x++) {
        float n = 0.9f + 0.2f * rnd01((unsigned)x + 7, (unsigned)y + 3);
        float k = ((x / (w / 4)) % 2) ? 1.0f : stripe;
        px[y * w + x] = (Color){ (unsigned char)Clamp(base.r * n * k, 0, 255), (unsigned char)Clamp(base.g * n * k, 0, 255), (unsigned char)Clamp(base.b * n * k, 0, 255), 255 };
    }
    Image img = { px, w, h, 1, PIXELFORMAT_UNCOMPRESSED_R8G8B8A8 };
    Texture2D t = LoadTextureFromImage(img);
    GenTextureMipmaps(&t); SetTextureFilter(t, TEXTURE_FILTER_TRILINEAR); SetTextureWrap(t, TEXTURE_WRAP_REPEAT);
    UnloadImage(img);
    return t;
}

/* sky dome texture: blue gradient with soft fair-weather cumulus */
static Texture2D makeSkyTexture(void)
{
    int w = 1024, h = 512;
    Image noise = GenImagePerlinNoise(w, h, 0, 0, 6.0f);
    Color *np = LoadImageColors(noise);
    Color *px = RL_MALLOC(sizeof(Color) * w * h);
    for (int y = 0; y < h; y++) for (int x = 0; x < w; x++) {
        float v = (float)y / (h - 1);                  /* 0 = top pole, 0.5 = horizon */
        float up = Clamp(1.0f - v * 2.0f, 0.0f, 1.0f); /* 1 at zenith, 0 at horizon */
        Vector3 zen = { 58, 112, 196 }, hor = { 186, 210, 232 };
        float t = powf(up, 0.55f);
        Vector3 c = Vector3Lerp(hor, zen, t);
        float cl = Clamp((np[y * w + x].r / 255.0f - 0.52f) * 3.2f, 0, 1) * Clamp(up * 4.0f, 0, 1) * Clamp((1 - up) * 3.0f, 0, 1);
        c = Vector3Lerp(c, (Vector3){ 246, 246, 248 }, cl * 0.85f);
        if (v > 0.5f) c = (Vector3){ 150, 160, 150 };
        px[y * w + x] = (Color){ (unsigned char)c.x, (unsigned char)c.y, (unsigned char)c.z, 255 };
    }
    UnloadImageColors(np); UnloadImage(noise);
    Image img = { px, w, h, 1, PIXELFORMAT_UNCOMPRESSED_R8G8B8A8 };
    Texture2D t = LoadTextureFromImage(img);
    SetTextureFilter(t, TEXTURE_FILTER_BILINEAR);
    UnloadImage(img);
    return t;
}

static Model planeModel(float w, float d, float y, float uvRepeat, Texture2D tex)
{
    Mesh m = GenMeshPlane(w, d, 1, 1);
    for (int i = 0; i < m.vertexCount; i++) { m.vertices[i * 3 + 1] = y; m.texcoords[i * 2] *= uvRepeat; m.texcoords[i * 2 + 1] *= uvRepeat; }
    UpdateMeshBuffer(m, 0, m.vertices, m.vertexCount * 3 * sizeof(float), 0);
    UpdateMeshBuffer(m, 1, m.texcoords, m.vertexCount * 2 * sizeof(float), 0);
    Model mo = LoadModelFromMesh(m);
    mo.materials[0].maps[MATERIAL_MAP_DIFFUSE].texture = tex;
    if (haveLit) mo.materials[0].shader = litShader;
    return mo;
}

static void buildPosts(MB *m)
{
    for (int e = 0; e < 2; e++) {
        float x = e ? HL : -HL, hw = GAME_GOAL_WIDTH * 0.5f;
        Color white = { 245, 245, 245, 255 };
        for (int k = -1; k <= 1; k += 2) {
            mbBox(m, (Vector3){ x - 0.06f, 0, k * hw - 0.06f }, (Vector3){ x + 0.06f, 7.5f, k * hw + 0.06f }, white);
            mbBox(m, (Vector3){ x - 0.2f, 0, k * hw - 0.2f }, (Vector3){ x + 0.2f, 1.6f, k * hw + 0.2f }, e ? (Color){ 200, 20, 40, 255 } : (Color){ 40, 70, 200, 255 });   /* base padding */
        }
        mbBox(m, (Vector3){ x - 0.06f, GAME_CROSSBAR_HEIGHT - 0.06f, -hw }, (Vector3){ x + 0.06f, GAME_CROSSBAR_HEIGHT + 0.06f, hw }, white);
        /* net support stanchions behind the goal */
        float s = e ? 1.0f : -1.0f;
        for (int k = -1; k <= 1; k += 2)
            mbBox(m, (Vector3){ x + s * 2.0f - 0.03f, 0, k * hw - 0.03f }, (Vector3){ x + s * 2.0f + 0.03f, 1.0f, k * hw + 0.03f }, (Color){ 180, 180, 180, 255 });
    }
    /* sideline flags at 13, 20, 45, 65 and halfway, and the corners */
    float fx[] = { 0, 13, 20, 45, 65, 70, 75, 95, 120, 127, 140 };
    for (int i = 0; i < 11; i++)
        for (int k = 0; k < 2; k++) {
            float x = fx[i] - HL, z = k ? HW + 1.2f : -HW - 1.2f;
            Color fc = (i == 0 || i == 10) ? (Color){ 250, 140, 20, 255 } : (i == 5) ? (Color){ 250, 250, 250, 255 } : (Color){ 240, 220, 40, 255 };
            mbBox(m, (Vector3){ x - 0.02f, 0, z - 0.02f }, (Vector3){ x + 0.02f, 1.5f, z + 0.02f }, (Color){ 230, 230, 230, 255 });
            mbBox(m, (Vector3){ x, 1.15f, z - 0.01f }, (Vector3){ x + 0.4f, 1.48f, z + 0.01f }, fc);
        }
}

static void buildPerimeter(MB *m)
{
    /* advertising boards around the pitch (far side behind the dugouts) */
    static const Color ads[] = { { 20, 60, 150, 255 }, { 220, 30, 40, 255 }, { 245, 245, 245, 255 }, { 20, 140, 70, 255 }, { 240, 190, 20, 255 }, { 30, 30, 40, 255 } };
    float bx = HL + 6.5f, bzN = HW + 6.0f, bzF = -HW - 8.0f;
    for (float x = -bx; x < bx; x += 6.0f) {
        Color c = ads[(int)((x + bx) / 6.0f) % 6];
        mbBox(m, (Vector3){ x + 0.05f, 0, bzN }, (Vector3){ x + 5.95f, 0.9f, bzN + 0.15f }, c);
        mbBox(m, (Vector3){ x + 0.05f, 0, bzF - 0.15f }, (Vector3){ x + 5.95f, 0.9f, bzF }, ads[(int)((x + bx) / 6.0f + 3) % 6]);
    }
    for (float z = -HW - 6.0f; z < HW + 5.0f; z += 6.0f)
        for (int e = 0; e < 2; e++) {
            float x = e ? bx : -bx;
            mbBox(m, (Vector3){ x - 0.08f, 0, z + 0.05f }, (Vector3){ x + 0.08f, 0.9f, z + 5.95f }, ads[(int)(z + 60) / 6 % 6]);
        }
    /* dugouts on the far side, either side of halfway */
    for (int s = -1; s <= 1; s += 2) {
        float x0 = s * 6.0f, x1 = s * 21.0f;
        Vector3 lo = { fminf(x0, x1), 0, -HW - 7.6f }, hi = { fmaxf(x0, x1), 2.2f, -HW - 5.2f };
        mbBox(m, lo, (Vector3){ hi.x, 0.5f, hi.z }, (Color){ 90, 90, 95, 255 });
        mbBox(m, (Vector3){ lo.x, 2.1f, lo.z }, hi, (Color){ 30, 70, 50, 255 });
        mbBox(m, lo, (Vector3){ hi.x, 2.2f, lo.z + 0.15f }, (Color){ 30, 70, 50, 255 });
    }
}

/* distant city roofs and hills, with haze from the shader */
static void buildBackdrop(MB *m)
{
    for (int i = 0; i < 260; i++) {
        float a = rnd01(i, 1) * 2 * PI, r = 175 + rnd01(i, 2) * 420;
        float w = 8 + rnd01(i, 3) * 22, d = 8 + rnd01(i, 4) * 18, h = 5 + rnd01(i, 5) * (r > 350 ? 30 : 14);
        if (rnd01(i, 8) < 0.04f) h = 40 + rnd01(i, 9) * 40;      /* a few taller blocks / church spires */
        float x = cosf(a) * r * 1.2f, z = sinf(a) * r;
        static const Color cols[] = { { 150, 90, 75, 255 }, { 170, 165, 155, 255 }, { 120, 115, 110, 255 }, { 190, 180, 160, 255 }, { 95, 100, 110, 255 } };
        mbBox(m, (Vector3){ x - w / 2, 0, z - d / 2 }, (Vector3){ x + w / 2, h, z + d / 2 }, cols[i % 5]);
        mbBox(m, (Vector3){ x - w / 2 - 0.3f, h, z - d / 2 - 0.3f }, (Vector3){ x + w / 2 + 0.3f, h + 1.2f, z + d / 2 + 0.3f }, (Color){ 80, 70, 70, 255 });
    }
    /* trees */
    for (int i = 0; i < 160; i++) {
        float a = rnd01(i, 21) * 2 * PI, r = 160 + rnd01(i, 22) * 300;
        float x = cosf(a) * r * 1.2f, z = sinf(a) * r, s = 3 + rnd01(i, 23) * 4;
        mbBox(m, (Vector3){ x - s, 2, z - s }, (Vector3){ x + s, 2 + s * 2.2f, z + s }, (Color){ 52, 92, 48, 255 });
    }
    /* hills ring */
    int N = 96;
    for (int i = 0; i < N; i++) {
        float a0 = 2 * PI * i / N, a1 = 2 * PI * (i + 1) / N, R = 1500;
        float h0 = 30 + 90 * (0.5f + 0.5f * sinf(a0 * 3 + 1)) * rnd01(i, 31) + 40 * rnd01(i / 4, 33);
        float h1 = 30 + 90 * (0.5f + 0.5f * sinf(a1 * 3 + 1)) * rnd01((i + 1) % N, 31) + 40 * rnd01(((i + 1) % N) / 4, 33);
        Vector3 p0 = { cosf(a0) * R, 0, sinf(a0) * R }, p1 = { cosf(a1) * R, 0, sinf(a1) * R };
        mbQuad(m, p0, p1, (Vector3){ p1.x, h1, p1.z }, (Vector3){ p0.x, h0, p0.z }, (Vector3){ -p0.x, 0, -p0.z }, (Color){ 96, 128, 104, 255 });
    }
}

static void buildStadium(void)
{
    PathPt *pp = RL_MALLOC(sizeof(PathPt) * 4096);
    MB m = { 0 };
    int np;
    const float fz = -HW - 9.5f;            /* far stand front edge */
    const float ex = HL + 10.0f;            /* end stands front edge */
    const float rc = 16.0f;                 /* bowl corner radius */
    /* Croke Park bowl: lower tier, boxes, middle tier, boxes, upper tier, roof */
    Tier bowl[3] = {
        { 24, 0.82f, 0.36f, 0.0f, 1.3f },
        { 10, 0.85f, 0.52f, 17.5f, 15.5f },
        { 26, 0.90f, 0.58f, 24.5f, 25.0f } };
    /* far side straight */
    np = pathLine(pp, 4096, (Vector3){ -ex + rc, 0, fz }, (Vector3){ ex - rc, 0, fz }, (Vector3){ 0, 0, -1 }, 1.2f);
    buildStand(&m, pp, np, bowl, 3, SEATS_CROKE, 0.78f, 0, 12, 1);
    buildBand(&m, pp, np, 19.9f, 9.9f, 15.5f, (Color){ 60, 78, 100, 255 });
    buildBand(&m, pp, np, 26.9f, 20.7f, 25.0f, (Color){ 60, 78, 100, 255 });
    buildRoof(&m, pp, np, 30.0f, 52.0f, 46.0f, 48.5f, 0, 0, 1);
    addStatic(&m);
    /* corners */
    for (int c = 0; c < 2; c++) {
        Vector3 cc = { c ? ex - rc : -ex + rc, 0, fz + rc };
        np = c ? pathArc(pp, 4096, cc, rc, -PI / 2, 0, 3.0f) : pathArc(pp, 4096, cc, rc, -PI, -PI / 2, 3.0f);
        if (c == 1) {   /* east corner steps down toward the Hill */
            Tier low[1] = { { 24, 0.82f, 0.36f, 0.0f, 1.3f } };
            buildStand(&m, pp, np, low, 1, SEATS_CROKE, 0.75f, 0, 6, 2);
            buildRoof(&m, pp, np, 12.0f, 21.0f, 15.0f, 16.0f, 0, 0, 0);
        } else {
            buildStand(&m, pp, np, bowl, 3, SEATS_CROKE, 0.72f, 0, 6, 3);
            buildBand(&m, pp, np, 19.9f, 9.9f, 15.5f, (Color){ 60, 78, 100, 255 });
            buildBand(&m, pp, np, 26.9f, 20.7f, 25.0f, (Color){ 60, 78, 100, 255 });
            buildRoof(&m, pp, np, 30.0f, 52.0f, 46.0f, 48.5f, 0, 0, 1);
        }
    }
    addStatic(&m);
    /* west (Canal) end: same bowl section */
    np = pathLine(pp, 4096, (Vector3){ -ex, 0, HW + 4.0f }, (Vector3){ -ex, 0, fz + rc }, (Vector3){ -1, 0, 0 }, 1.2f);
    buildStand(&m, pp, np, bowl, 3, SEATS_CROKE, 0.7f, 0, 12, 4);
    buildBand(&m, pp, np, 19.9f, 9.9f, 15.5f, (Color){ 60, 78, 100, 255 });
    buildBand(&m, pp, np, 26.9f, 20.7f, 25.0f, (Color){ 60, 78, 100, 255 });
    buildRoof(&m, pp, np, 30.0f, 52.0f, 46.0f, 48.5f, 0, 0, 1);
    addStatic(&m);
    /* Hill 16: open terrace, standing, packed */
    {
        Tier hill[1] = { { 34, 0.56f, 0.30f, 0.0f, 1.0f } };
        np = pathLine(pp, 4096, (Vector3){ ex, 0, fz + rc }, (Vector3){ ex, 0, HW + 6.0f }, (Vector3){ 1, 0, 0 }, 1.2f);
        buildStand(&m, pp, np, hill, 1, SEATS_HILL, 0.9f, 1, 15, 5);
        /* back wall + big screen in the corner */
        buildBand(&m, pp, np, 19.1f, 0.0f, 12.0f, (Color){ 120, 118, 112, 255 });
        mbBox(&m, (Vector3){ ex + 14, 13, -38 }, (Vector3){ ex + 15, 22, -22 }, (Color){ 25, 25, 30, 255 });
        mbBox(&m, (Vector3){ ex + 14.6f, 0, -31 }, (Vector3){ ex + 15.2f, 13, -29 }, (Color){ 90, 90, 95, 255 });
        addStatic(&m);
    }
    /* near side: county covered stand (yellow/blue seats) and open terraces */
    {
        float nz = HW + 9.0f;
        Tier cs[1] = { { 22, 0.80f, 0.40f, 0.0f, 1.4f } };
        np = pathLine(pp, 4096, (Vector3){ -46, 0, nz }, (Vector3){ 46, 0, nz }, (Vector3){ 0, 0, 1 }, 1.2f);
        buildStand(&m, pp, np, cs, 1, SEATS_COUNTY, 0.62f, 0, 14, 6);
        buildRoof(&m, pp, np, -1.0f, 19.5f, 13.5f, 14.8f, 13, 0.4f, 0);
        addStatic(&m);
        Tier tr[1] = { { 11, 0.60f, 0.26f, 0.0f, 0.6f } };
        np = pathLine(pp, 4096, (Vector3){ -ex - 2, 0, nz }, (Vector3){ -47, 0, nz }, (Vector3){ 0, 0, 1 }, 1.2f);
        buildStand(&m, pp, np, tr, 1, SEATS_TERRACE, 0.45f, 1, 0, 7);
        np = pathLine(pp, 4096, (Vector3){ 47, 0, nz }, (Vector3){ ex + 2, 0, nz }, (Vector3){ 0, 0, 1 }, 1.2f);
        buildStand(&m, pp, np, tr, 1, SEATS_TERRACE, 0.45f, 1, 0, 8);
        /* terrace cover (low roof on posts) over the eastern terrace, like the county ground */
        buildRoof(&m, pp, np, 0.5f, 8.0f, 5.6f, 6.4f, 8, 0.7f, 0);
        addStatic(&m);
    }
    buildPerimeter(&m);
    buildPosts(&m);
    addStatic(&m);
    buildBackdrop(&m);
    addStatic(&m);
    RL_FREE(pp);
}

static void loadShadowMap(void)
{
    shadowRT.id = rlLoadFramebuffer();
    shadowRT.texture.width = SHADOW_RES; shadowRT.texture.height = SHADOW_RES;
    if (shadowRT.id > 0) {
        rlEnableFramebuffer(shadowRT.id);
        shadowRT.depth.id = rlLoadTextureDepth(SHADOW_RES, SHADOW_RES, false);
        shadowRT.depth.width = SHADOW_RES; shadowRT.depth.height = SHADOW_RES;
        shadowRT.depth.format = 19; shadowRT.depth.mipmaps = 1;
        rlFramebufferAttach(shadowRT.id, shadowRT.depth.id, RL_ATTACHMENT_DEPTH, RL_ATTACHMENT_TEXTURE2D, 0);
        if (!rlFramebufferComplete(shadowRT.id)) { TraceLog(LOG_WARNING, "GAME: shadow map FBO incomplete"); shadowRT.id = 0; }
        rlDisableFramebuffer();
    }
}

/* The stadium is static, so its shadow map is rendered once. */
static void renderShadowMap(void)
{
    if (!shadowRT.id) return;
    Camera3D lc = { 0 };
    lc.target = (Vector3){ 0, 0, 0 };
    lc.position = Vector3Scale(sunDir, -400.0f);
    lc.up = (Vector3){ 0, 1, 0 };
    lc.projection = CAMERA_ORTHOGRAPHIC;
    lc.fovy = 330.0f;
    Shader def = { rlGetShaderIdDefault(), rlGetShaderLocsDefault() };
    BeginTextureMode(shadowRT);
    ClearBackground(WHITE);
    rlClearScreenBuffers();
    BeginMode3D(lc);
    Matrix v = rlGetMatrixModelview(), p = rlGetMatrixProjection();
    rlDisableBackfaceCulling();
    for (int i = 0; i < staticCount - 1; i++) {       /* not the backdrop */
        Shader keep = staticModels[i].materials[0].shader;
        staticModels[i].materials[0].shader = def;
        DrawModel(staticModels[i], (Vector3){ 0, 0, 0 }, 1.0f, WHITE);
        staticModels[i].materials[0].shader = keep;
    }
    rlEnableBackfaceCulling();
    EndMode3D();
    EndTextureMode();
    lightVP = MatrixMultiply(v, p);
}

static void stadiumInit(void)
{
    sunDir = Vector3Normalize((Vector3){ -0.42f, -0.74f, -0.52f });   /* sun behind the broadcast camera */
    litShader = LoadShaderFromMemory(LIT_VS, LIT_FS);
    haveLit = litShader.id > 0 && litShader.id != rlGetShaderIdDefault();
    if (haveLit) {
        flatShader = LoadShaderFromMemory(FLAT_VS, FLAT_FS);
#if RAYLIB_VERSION_MAJOR < 6
        skinShader = LoadShaderFromMemory(SKIN_VS, LIT_FS);
        flatSkinShader = LoadShaderFromMemory(FLAT_SKIN_VS, FLAT_FS);
        gpuSkinAvailable = skinShader.id > 0 && skinShader.id != rlGetShaderIdDefault() && skinShader.locs[SHADER_LOC_BONE_MATRICES] >= 0 &&
                           flatSkinShader.id > 0 && flatSkinShader.id != rlGetShaderIdDefault();
#endif
        gpuSkin = gpuSkinAvailable && !forceCpuSkin;
        TraceLog(LOG_INFO, "GAME: character skinning on the %s (GPU path %s)", gpuSkin ? "GPU" : "CPU", gpuSkinAvailable ? "available" : "unavailable");
        for (int k = 0; k < (gpuSkinAvailable ? 2 : 1); k++) {
            Shader *sh = k ? &skinShader : &litShader;
            LitLocs *L = &litLocs[k];
            L->view = sh->locs[SHADER_LOC_VECTOR_VIEW] = GetShaderLocation(*sh, "viewPos");
            L->lightVP = GetShaderLocation(*sh, "lightVP");
            L->shadowMap = GetShaderLocation(*sh, "shadowMap");
            L->useShadow = GetShaderLocation(*sh, "useShadow");
            L->time = GetShaderLocation(*sh, "uTime");
            L->excite = GetShaderLocation(*sh, "uExcite");
            Vector3 sun = { 0.98f, 0.93f, 0.82f }, sky = { 0.50f, 0.56f, 0.66f }, gnd = { 0.30f, 0.32f, 0.26f }, haze = { 0.70f, 0.78f, 0.86f };
            SetShaderValue(*sh, GetShaderLocation(*sh, "lightDir"), &sunDir, SHADER_UNIFORM_VEC3);
            SetShaderValue(*sh, GetShaderLocation(*sh, "sunColor"), &sun, SHADER_UNIFORM_VEC3);
            SetShaderValue(*sh, GetShaderLocation(*sh, "skyColor"), &sky, SHADER_UNIFORM_VEC3);
            SetShaderValue(*sh, GetShaderLocation(*sh, "groundColor"), &gnd, SHADER_UNIFORM_VEC3);
            SetShaderValue(*sh, GetShaderLocation(*sh, "hazeColor"), &haze, SHADER_UNIFORM_VEC3);
            float texel = 1.0f / SHADOW_RES;
            SetShaderValue(*sh, GetShaderLocation(*sh, "shadowTexel"), &texel, SHADER_UNIFORM_FLOAT);
        }
    } else TraceLog(LOG_WARNING, "GAME: lit shader failed, using unlit fallback");

    double t0 = GetTime();
    pitchTex = makePitchTexture();
    apronTex = makeNoiseGrass(256, 256, (Color){ 52, 110, 44, 255 }, 0.92f);
    skyTex = makeSkyTexture();
    pitchModel = planeModel(GAME_PITCH_LENGTH + 2 * PITCH_TEX_MARGIN, GAME_PITCH_WIDTH + 2 * PITCH_TEX_MARGIN, 0.0f, 1.0f, pitchTex);
    apronModel = planeModel(2 * HL + 60, 2 * HW + 60, -0.02f, 24.0f, apronTex);
    {
        Texture2D white = { rlGetTextureIdDefault(), 1, 1, 1, PIXELFORMAT_UNCOMPRESSED_R8G8B8A8 };
        groundModel = planeModel(4000, 4000, -0.06f, 1.0f, white);
        groundModel.materials[0].maps[MATERIAL_MAP_DIFFUSE].color = (Color){ 88, 112, 80, 255 };
    }
    {
        Mesh sm = GenMeshSphere(1900.0f, 24, 32);
        skyModel = LoadModelFromMesh(sm);
        skyModel.materials[0].maps[MATERIAL_MAP_DIFFUSE].texture = skyTex;
    }
    {
        Mesh bm = GenMeshSphere(BALL_R, 12, 16);
        ballModel = LoadModelFromMesh(bm);
        if (haveLit) ballModel.materials[0].shader = litShader;
    }
    buildStadium();
    TraceLog(LOG_INFO, "GAME: stadium %d static meshes, %ld vertices", staticCount, staticVerts);
    if (haveLit) { loadShadowMap(); renderShadowMap(); }
    int verts = 0;
    for (int i = 0; i < staticCount; i++) verts += staticModels[i].meshes[0].vertexCount;
    TraceLog(LOG_INFO, "GAME: stadium built: %d meshes, %d vertices, %.2fs", staticCount, verts, GetTime() - t0);
    haveStadium = 1;
}

/* per-frame uniforms + bind the shadow map on its own texture slot */
static void lightingBegin(Camera3D c, float time)
{
    if (!haveLit) return;
    int use = shadowRT.id > 0 ? gfxQuality : 0;      /* Low: no shadow map, Medium: 1 tap, High: 3x3 PCF */
    for (int k = 0; k < (gpuSkinAvailable ? 2 : 1); k++) {
        Shader sh = k ? skinShader : litShader;
        LitLocs *L = &litLocs[k];
        SetShaderValue(sh, L->view, &c.position, SHADER_UNIFORM_VEC3);
        SetShaderValue(sh, L->time, &time, SHADER_UNIFORM_FLOAT);
        SetShaderValue(sh, L->excite, &crowdExcite, SHADER_UNIFORM_FLOAT);
        SetShaderValue(sh, L->useShadow, &use, SHADER_UNIFORM_INT);
        if (use) {
            SetShaderValueMatrix(sh, L->lightVP, lightVP);
            int slot = SHADOW_SLOT;
            rlEnableShader(sh.id);
            rlSetUniform(L->shadowMap, &slot, SHADER_UNIFORM_INT, 1);
        }
    }
    if (use) {
        rlActiveTextureSlot(SHADOW_SLOT);
        rlEnableTexture(shadowRT.depth.id);
        rlActiveTextureSlot(0);
    }
}

static void drawSky(Camera3D c)
{
    rlDisableBackfaceCulling();
    rlDisableDepthMask();
    DrawModel(skyModel, c.position, 1.0f, WHITE);
    rlEnableDepthMask();
    rlEnableBackfaceCulling();
}

static void drawStadium(void)
{
    DrawModel(groundModel, (Vector3){ 0, 0, 0 }, 1.0f, WHITE);
    DrawModel(apronModel, (Vector3){ 0, 0, 0 }, 1.0f, WHITE);
    DrawModel(pitchModel, (Vector3){ 0, 0, 0 }, 1.0f, WHITE);
    rlDisableBackfaceCulling();      /* thin roofs/boards are seen from both sides */
    for (int i = 0; i < staticCount; i++) DrawModel(staticModels[i], (Vector3){ 0, 0, 0 }, 1.0f, WHITE);
    rlEnableBackfaceCulling();
    /* nets (thin lines, unlit) */
    Color net = { 255, 255, 255, 90 };
    for (int e = 0; e < 2; e++) {
        float x = e ? HL : -HL, s = e ? 1.0f : -1.0f, hw = GAME_GOAL_WIDTH * 0.5f, cb = GAME_CROSSBAR_HEIGHT;
        for (float z = -hw; z <= hw + 0.01f; z += 0.3f) DrawLine3D((Vector3){ x, cb, z }, (Vector3){ x + s * 2.0f, 0, z }, net);
        for (float h = 0; h <= cb + 0.01f; h += 0.3f) {
            float bx = x + s * 2.0f * (1 - h / cb);
            DrawLine3D((Vector3){ bx, h, -hw }, (Vector3){ bx, h, hw }, net);
            DrawLine3D((Vector3){ x, h, -hw }, (Vector3){ bx, h, -hw }, net);
            DrawLine3D((Vector3){ x, h, hw }, (Vector3){ bx, h, hw }, net);
        }
    }
}

/* Planar projected shadow of the currently posed skinned model onto the grass.
 * Depth-tested at one height so overlapping limbs never double-darken. */
static void drawPlanarShadow(Model *mo, Vector3 pos, float yawDeg)
{
    if (!haveLit || gfxQuality == 0) {      /* Low: soft blob */
        DrawCylinder((Vector3){ pos.x, 0.02f, pos.z }, 0.45f, 0.45f, 0.004f, 14, (Color){ 0, 0, 0, 95 });
        DrawCylinder((Vector3){ pos.x, 0.021f, pos.z }, 0.30f, 0.30f, 0.004f, 14, (Color){ 0, 0, 0, 60 });
        return;
    }
    const float h = 0.03f;
    float lx = sunDir.x / sunDir.y, lz = sunDir.z / sunDir.y;
    Matrix S = { 1, -lx, 0, lx * h,
                 0, 0, 0, h,
                 0, -lz, 1, lz * h,
                 0, 0, 0, 1 };
    Matrix T = MatrixMultiply(MatrixMultiply(MatrixRotateY(yawDeg * DEG2RAD), MatrixTranslate(pos.x, pos.y, pos.z)), S);
    Shader keep = mo->materials[mo->meshMaterial[0]].shader;
    Color kc = mo->materials[mo->meshMaterial[0]].maps[MATERIAL_MAP_DIFFUSE].color;
    mo->materials[mo->meshMaterial[0]].shader = gpuSkin ? flatSkinShader : flatShader;
    mo->materials[mo->meshMaterial[0]].maps[MATERIAL_MAP_DIFFUSE].color = (Color){ 8, 18, 6, 150 };
    T = MatrixMultiply(mo->transform, T);
    rlDrawRenderBatchActive();
    rlDisableBackfaceCulling();
    /* stencil: each shadow pixel is darkened once, however many limbs/players overlap */
    glEnable(GL_STENCIL_TEST);
    glStencilFunc(GL_NOTEQUAL, 1, 0xFF);
    glStencilOp(GL_KEEP, GL_KEEP, GL_REPLACE);
    rlDisableDepthMask();
    for (int i = 0; i < mo->meshCount; i++) DrawMesh(mo->meshes[i], mo->materials[mo->meshMaterial[0]], T);
    rlEnableDepthMask();
    glDisable(GL_STENCIL_TEST);
    rlEnableBackfaceCulling();
    mo->materials[mo->meshMaterial[0]].shader = keep;
    mo->materials[mo->meshMaterial[0]].maps[MATERIAL_MAP_DIFFUSE].color = kc;
}

static void drawBallLit(Vector3 p)
{
    if (haveLit) DrawModel(ballModel, p, 1.0f, (Color){ 240, 234, 216, 255 });
    else DrawSphere(p, BALL_R, (Color){ 238, 232, 214, 255 });
    DrawSphereWires(p, BALL_R * 1.01f, 6, 8, (Color){ 120, 110, 90, 90 });
    /* shadow along the sun direction */
    float k = (p.y - 0.02f) / -sunDir.y;
    Vector3 s = { p.x + sunDir.x * k, 0.03f, p.z + sunDir.z * k };
    DrawCylinder(s, BALL_R * 0.9f, BALL_R * 0.9f, 0.004f, 10, (Color){ 0, 0, 0, 80 });
}

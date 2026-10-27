/* util.c : small helpers, mesh builder and lit immediate-mode primitives */
#include "common.h"

float Approach(float v, float target, float step)
{
    if (v < target) { v += step; if (v > target) v = target; }
    else if (v > target) { v -= step; if (v < target) v = target; }
    return v;
}

float WrapAngle(float a)
{
    while (a > PI) a -= 2.0f*PI;
    while (a < -PI) a += 2.0f*PI;
    return a;
}

float LerpAngle(float a, float b, float t)
{
    return a + WrapAngle(b - a)*t;
}

float RandF(float lo, float hi)
{
    return lo + (hi - lo)*((float)rand()/(float)RAND_MAX);
}

Color ColorScale(Color c, float s)
{
    float r = c.r*s, g = c.g*s, b = c.b*s;
    return (Color){ (unsigned char)(r > 255 ? 255 : r), (unsigned char)(g > 255 ? 255 : g),
                    (unsigned char)(b > 255 ? 255 : b), c.a };
}

Color ColorMix(Color a, Color b, float t)
{
    return (Color){ (unsigned char)(a.r + (b.r - a.r)*t), (unsigned char)(a.g + (b.g - a.g)*t),
                    (unsigned char)(a.b + (b.b - a.b)*t), (unsigned char)(a.a + (b.a - a.a)*t) };
}

Color HueColor(float h, float s, float v)
{
    h = fmodf(h, 360.0f); if (h < 0) h += 360.0f;
    return ColorFromHSV(h, s, v);
}

void DrawTextOutlined(const char *text, int x, int y, int size, Color col)
{
    int o = size/10; if (o < 2) o = 2;
    Color sh = (Color){ 0, 0, 0, col.a };
    DrawText(text, x - o, y, size, sh);
    DrawText(text, x + o, y, size, sh);
    DrawText(text, x, y - o, size, sh);
    DrawText(text, x, y + o, size, sh);
    DrawText(text, x + o, y + o, size, sh);
    DrawText(text, x, y, size, col);
}

void DrawTextCentered(const char *text, int cx, int y, int size, Color col)
{
    int w = MeasureText(text, size);
    DrawTextOutlined(text, cx - w/2, y, size, col);
}

const char *OrdinalSuffix(int place)
{
    if (place == 1) return "st";
    if (place == 2) return "nd";
    if (place == 3) return "rd";
    return "th";
}

const char *FormatTime(float t)
{
    if (t < 0) t = 0;
    int m = (int)(t/60.0f);
    float s = t - m*60.0f;
    int si = (int)s;
    int cs = (int)((s - si)*100.0f);
    return TextFormat("%d'%02d\"%02d", m, si, cs);
}

/* ------------------------------------------------------------------ */
/* Mesh builder: accumulates non-indexed triangles with baked lighting */
/* ------------------------------------------------------------------ */
void MB_Init(MeshBuilder *mb) { memset(mb, 0, sizeof(*mb)); }

void MB_Free(MeshBuilder *mb)
{
    free(mb->v); free(mb->t); free(mb->n); free(mb->c);
    memset(mb, 0, sizeof(*mb));
}

static void MB_Grow(MeshBuilder *mb, int add)
{
    if (mb->count + add <= mb->cap) return;
    int nc = mb->cap ? mb->cap*2 : 4096;
    while (nc < mb->count + add) nc *= 2;
    mb->v = (float *)realloc(mb->v, (size_t)nc*3*sizeof(float));
    mb->t = (float *)realloc(mb->t, (size_t)nc*2*sizeof(float));
    mb->n = (float *)realloc(mb->n, (size_t)nc*3*sizeof(float));
    mb->c = (unsigned char *)realloc(mb->c, (size_t)nc*4);
    mb->cap = nc;
}

static void MB_Vertex(MeshBuilder *mb, Vector3 p, Vector2 uv, Vector3 n, Color c)
{
    MB_Grow(mb, 1);
    int i = mb->count++;
    mb->v[i*3+0] = p.x; mb->v[i*3+1] = p.y; mb->v[i*3+2] = p.z;
    mb->t[i*2+0] = uv.x; mb->t[i*2+1] = uv.y;
    mb->n[i*3+0] = n.x; mb->n[i*3+1] = n.y; mb->n[i*3+2] = n.z;
    mb->c[i*4+0] = c.r; mb->c[i*4+1] = c.g; mb->c[i*4+2] = c.b; mb->c[i*4+3] = c.a;
}

Color MB_Shade(Color c, Vector3 n)
{
    float d = Vector3DotProduct(n, G.sunDir);
    if (d < 0) d = 0;
    float sky = 0.5f + 0.5f*n.y;               /* hemisphere fill */
    float s = G.ambient*(0.75f + 0.25f*sky) + (1.0f - G.ambient)*d;
    if (s > 1.15f) s = 1.15f;
    return ColorScale(c, s);
}

void MB_TriUV(MeshBuilder *mb, Vector3 p0, Vector3 p1, Vector3 p2, Vector2 u0, Vector2 u1, Vector2 u2,
              Color c0, Color c1, Color c2, Vector3 outRef, bool shade)
{
    Vector3 n = Vector3CrossProduct(Vector3Subtract(p1, p0), Vector3Subtract(p2, p0));
    float len = Vector3Length(n);
    if (len < 1e-8f) return;
    n = Vector3Scale(n, 1.0f/len);
    Vector3 ctr = Vector3Scale(Vector3Add(Vector3Add(p0, p1), p2), 1.0f/3.0f);
    if (Vector3DotProduct(n, Vector3Subtract(ctr, outRef)) < 0) {
        /* flip winding so the front face points away from outRef (CCW) */
        Vector3 tp = p1; p1 = p2; p2 = tp;
        Vector2 tu = u1; u1 = u2; u2 = tu;
        Color tc = c1; c1 = c2; c2 = tc;
        n = Vector3Negate(n);
    }
    if (shade) { c0 = MB_Shade(c0, n); c1 = MB_Shade(c1, n); c2 = MB_Shade(c2, n); }
    MB_Vertex(mb, p0, u0, n, c0);
    MB_Vertex(mb, p1, u1, n, c1);
    MB_Vertex(mb, p2, u2, n, c2);
}

void MB_Tri(MeshBuilder *mb, Vector3 p0, Vector3 p1, Vector3 p2, Color c, Vector3 outRef)
{
    Vector2 z = { 0.5f, 0.5f };
    MB_TriUV(mb, p0, p1, p2, z, z, z, c, c, c, outRef, true);
}

void MB_Quad(MeshBuilder *mb, Vector3 p0, Vector3 p1, Vector3 p2, Vector3 p3, Color c, Vector3 outRef)
{
    MB_Tri(mb, p0, p1, p2, c, outRef);
    MB_Tri(mb, p0, p2, p3, c, outRef);
}

void MB_QuadUV(MeshBuilder *mb, Vector3 p0, Vector3 p1, Vector3 p2, Vector3 p3,
               Vector2 u0, Vector2 u1, Vector2 u2, Vector2 u3, Color c, Vector3 outRef, bool shade)
{
    MB_TriUV(mb, p0, p1, p2, u0, u1, u2, c, c, c, outRef, shade);
    MB_TriUV(mb, p0, p2, p3, u0, u2, u3, c, c, c, outRef, shade);
}

void MB_Box(MeshBuilder *mb, Vector3 center, Vector3 size, float yaw, Color c)
{
    Vector3 h = Vector3Scale(size, 0.5f);
    float cs = cosf(yaw), sn = sinf(yaw);
    Vector3 p[8];
    for (int i = 0; i < 8; i++) {
        float x = (i & 1) ? h.x : -h.x;
        float y = (i & 2) ? h.y : -h.y;
        float z = (i & 4) ? h.z : -h.z;
        p[i] = (Vector3){ center.x + x*cs + z*sn, center.y + y, center.z - x*sn + z*cs };
    }
    MB_Quad(mb, p[0], p[1], p[3], p[2], c, center); /* -z */
    MB_Quad(mb, p[4], p[5], p[7], p[6], c, center); /* +z */
    MB_Quad(mb, p[0], p[4], p[6], p[2], c, center); /* -x */
    MB_Quad(mb, p[1], p[5], p[7], p[3], c, center); /* +x */
    MB_Quad(mb, p[2], p[3], p[7], p[6], c, center); /* +y */
    MB_Quad(mb, p[0], p[1], p[5], p[4], c, center); /* -y */
}

void MB_Cylinder(MeshBuilder *mb, Vector3 base, float rBottom, float rTop, float h, int sides, Color c)
{
    Vector3 ctr = { base.x, base.y + h*0.5f, base.z };
    Vector3 top = { base.x, base.y + h, base.z };
    for (int i = 0; i < sides; i++) {
        float a0 = 2*PI*i/sides, a1 = 2*PI*(i + 1)/sides;
        Vector3 b0 = { base.x + cosf(a0)*rBottom, base.y, base.z + sinf(a0)*rBottom };
        Vector3 b1 = { base.x + cosf(a1)*rBottom, base.y, base.z + sinf(a1)*rBottom };
        Vector3 t0 = { base.x + cosf(a0)*rTop, base.y + h, base.z + sinf(a0)*rTop };
        Vector3 t1 = { base.x + cosf(a1)*rTop, base.y + h, base.z + sinf(a1)*rTop };
        if (rTop > 0.001f) {
            MB_Quad(mb, b0, b1, t1, t0, c, ctr);
            MB_Tri(mb, top, t0, t1, c, ctr);
        } else {
            MB_Tri(mb, b0, b1, top, c, ctr);
        }
        if (rBottom > 0.001f) MB_Tri(mb, base, b0, b1, c, ctr);
    }
}

void MB_Sphere(MeshBuilder *mb, Vector3 c, Vector3 r, int rings, int slices, Color col)
{
    for (int i = 0; i < rings; i++) {
        float la0 = PI*((float)i/rings - 0.5f), la1 = PI*((float)(i + 1)/rings - 0.5f);
        for (int j = 0; j < slices; j++) {
            float lo0 = 2*PI*j/slices, lo1 = 2*PI*(j + 1)/slices;
            Vector3 p00 = { c.x + r.x*cosf(la0)*cosf(lo0), c.y + r.y*sinf(la0), c.z + r.z*cosf(la0)*sinf(lo0) };
            Vector3 p01 = { c.x + r.x*cosf(la0)*cosf(lo1), c.y + r.y*sinf(la0), c.z + r.z*cosf(la0)*sinf(lo1) };
            Vector3 p10 = { c.x + r.x*cosf(la1)*cosf(lo0), c.y + r.y*sinf(la1), c.z + r.z*cosf(la1)*sinf(lo0) };
            Vector3 p11 = { c.x + r.x*cosf(la1)*cosf(lo1), c.y + r.y*sinf(la1), c.z + r.z*cosf(la1)*sinf(lo1) };
            if (i > 0) MB_Tri(mb, p00, p01, p11, col, c);
            if (i < rings - 1) MB_Tri(mb, p00, p11, p10, col, c);
        }
    }
}

/* vertex with smooth (per-vertex) baked lighting */
void MB_VertexLit(MeshBuilder *mb, Vector3 p, Vector2 uv, Vector3 n, Color c)
{
    MB_Vertex(mb, p, uv, n, MB_Shade(c, n));
}

/* smooth-shaded ellipsoid with a vertical colour gradient (bottom -> top) */
void MB_SmoothSphere(MeshBuilder *mb, Vector3 c, Vector3 r, int rings, int slices, Color bottom, Color top, float minLat)
{
    Vector2 uv = { 0.5f, 0.5f };
    for (int i = 0; i < rings; i++) {
        float la0 = minLat + (PI*0.5f - minLat)*((float)i/rings);
        float la1 = minLat + (PI*0.5f - minLat)*((float)(i + 1)/rings);
        Color c0 = ColorMix(bottom, top, (sinf(la0) + 1)*0.5f), c1 = ColorMix(bottom, top, (sinf(la1) + 1)*0.5f);
        for (int j = 0; j < slices; j++) {
            float lo0 = 2*PI*j/slices, lo1 = 2*PI*(j + 1)/slices;
            Vector3 n00 = { cosf(la0)*cosf(lo0), sinf(la0), cosf(la0)*sinf(lo0) };
            Vector3 n01 = { cosf(la0)*cosf(lo1), sinf(la0), cosf(la0)*sinf(lo1) };
            Vector3 n10 = { cosf(la1)*cosf(lo0), sinf(la1), cosf(la1)*sinf(lo0) };
            Vector3 n11 = { cosf(la1)*cosf(lo1), sinf(la1), cosf(la1)*sinf(lo1) };
            Vector3 p00 = { c.x + r.x*n00.x, c.y + r.y*n00.y, c.z + r.z*n00.z };
            Vector3 p01 = { c.x + r.x*n01.x, c.y + r.y*n01.y, c.z + r.z*n01.z };
            Vector3 p10 = { c.x + r.x*n10.x, c.y + r.y*n10.y, c.z + r.z*n10.z };
            Vector3 p11 = { c.x + r.x*n11.x, c.y + r.y*n11.y, c.z + r.z*n11.z };
            /* normals of a squashed ellipsoid */
            Vector3 m00 = Vector3Normalize((Vector3){ n00.x/r.x, n00.y/r.y, n00.z/r.z });
            Vector3 m01 = Vector3Normalize((Vector3){ n01.x/r.x, n01.y/r.y, n01.z/r.z });
            Vector3 m10 = Vector3Normalize((Vector3){ n10.x/r.x, n10.y/r.y, n10.z/r.z });
            Vector3 m11 = Vector3Normalize((Vector3){ n11.x/r.x, n11.y/r.y, n11.z/r.z });
            MB_VertexLit(mb, p00, uv, m00, c0); MB_VertexLit(mb, p11, uv, m11, c1); MB_VertexLit(mb, p01, uv, m01, c0);
            MB_VertexLit(mb, p00, uv, m00, c0); MB_VertexLit(mb, p10, uv, m10, c1); MB_VertexLit(mb, p11, uv, m11, c1);
        }
    }
}

Model MB_BuildModel(MeshBuilder *mb, Texture2D tex, bool fog)
{
    if (mb->count < 3) {
        Vector3 z = { 0, -1000, 0 };
        MB_Tri(mb, z, (Vector3){ 0.01f, -1000, 0 }, (Vector3){ 0, -1000, 0.01f }, BLANK, (Vector3){ 0, -2000, 0 });
    }
    Mesh m = { 0 };
    m.vertexCount = mb->count;
    m.triangleCount = mb->count/3;
    m.vertices = (float *)RL_MALLOC((size_t)mb->count*3*sizeof(float));
    m.texcoords = (float *)RL_MALLOC((size_t)mb->count*2*sizeof(float));
    m.normals = (float *)RL_MALLOC((size_t)mb->count*3*sizeof(float));
    m.colors = (unsigned char *)RL_MALLOC((size_t)mb->count*4);
    memcpy(m.vertices, mb->v, (size_t)mb->count*3*sizeof(float));
    memcpy(m.texcoords, mb->t, (size_t)mb->count*2*sizeof(float));
    memcpy(m.normals, mb->n, (size_t)mb->count*3*sizeof(float));
    memcpy(m.colors, mb->c, (size_t)mb->count*4);
    UploadMesh(&m, false);
    Model model = LoadModelFromMesh(m);
    model.materials[0].maps[MATERIAL_MAP_DIFFUSE].texture = tex;
    if (fog) model.materials[0].shader = G.fogShader;
    return model;
}

/* ------------------------------------------------------------------ */
/* Lit immediate-mode primitives (rlgl batch, current matrix applies)  */
/* While a capture is active they are baked into a MeshBuilder instead */
/* (with a small software matrix stack) so karts become cached models. */
/* ------------------------------------------------------------------ */
static MeshBuilder *gCap = NULL;
static Matrix gCapM, gCapStack[16];
static int gCapSP = 0;
static float gSphereDetail = 1.0f;
static int gRoundSegs = 1;

void LitCaptureBegin(MeshBuilder *mb, float sphereDetail, int roundSegs)
{
    gCap = mb; gCapM = MatrixIdentity(); gCapSP = 0;
    gSphereDetail = sphereDetail; gRoundSegs = roundSegs < 1 ? 1 : roundSegs;
}
void LitCaptureEnd(void) { gCap = NULL; gSphereDetail = 1.0f; gRoundSegs = 1; }
bool LitCapturing(void) { return gCap != NULL; }
void XPush(void) { if (gCap) { if (gCapSP < 16) gCapStack[gCapSP++] = gCapM; } else rlPushMatrix(); }
void XPop(void) { if (gCap) { if (gCapSP > 0) gCapM = gCapStack[--gCapSP]; } else rlPopMatrix(); }
void XTranslate(float x, float y, float z) { if (gCap) gCapM = MatrixMultiply(MatrixTranslate(x, y, z), gCapM); else rlTranslatef(x, y, z); }
void XRotate(float deg, float x, float y, float z) { if (gCap) gCapM = MatrixMultiply(MatrixRotate((Vector3){ x, y, z }, deg*DEG2RAD), gCapM); else rlRotatef(deg, x, y, z); }
void XScale(float x, float y, float z) { if (gCap) gCapM = MatrixMultiply(MatrixScale(x, y, z), gCapM); else rlScalef(x, y, z); }

static void LB(void) { if (!gCap) rlBegin(RL_TRIANGLES); }
static void LE(void) { if (!gCap) rlEnd(); }

static inline void LitVertex(Vector3 p, Vector3 n, Color c)
{
    if (gCap) {
        p = Vector3Transform(p, gCapM);
        Vector3 o0 = { gCapM.m12, gCapM.m13, gCapM.m14 };
        n = Vector3Subtract(Vector3Transform(n, gCapM), o0);
        float l = Vector3Length(n);
        if (l > 1e-6f) n = Vector3Scale(n, 1.0f/l);
    }
    /* soft key light from above/front-left + sky fill + a little rim: reads well from the chase camera */
    float d = n.x*0.32f + n.y*0.80f + n.z*0.50f;
    float s = 0.56f + 0.44f*(d > 0 ? d : 0.0f) + 0.10f*(0.5f + 0.5f*n.y);
    float rim = 1.0f - fabsf(n.z);                 /* edges catch a bit of light */
    s += 0.06f*rim*rim;
    Color o = ColorScale(c, s);
    if (gCap) { MB_Vertex(gCap, p, (Vector2){ 0.5f, 0.5f }, n, o); return; }
    rlColor4ub(o.r, o.g, o.b, o.a);
    rlVertex3f(p.x, p.y, p.z);
}

void DrawLitBox(Vector3 c, Vector3 size, Color col)
{
    float x = size.x*0.5f, y = size.y*0.5f, z = size.z*0.5f;
    LB();
    /* each face: two CCW triangles (seen from outside) */
    struct { Vector3 n; Vector3 a, b, cc, d; } f[6] = {
        { {0,1,0},  {-x, y,-z}, {-x, y, z}, { x, y, z}, { x, y,-z} },
        { {0,-1,0}, {-x,-y,-z}, { x,-y,-z}, { x,-y, z}, {-x,-y, z} },
        { {0,0,1},  {-x,-y, z}, { x,-y, z}, { x, y, z}, {-x, y, z} },
        { {0,0,-1}, {-x,-y,-z}, {-x, y,-z}, { x, y,-z}, { x,-y,-z} },
        { {1,0,0},  { x,-y,-z}, { x, y,-z}, { x, y, z}, { x,-y, z} },
        { {-1,0,0}, {-x,-y,-z}, {-x,-y, z}, {-x, y, z}, {-x, y,-z} },
    };
    for (int i = 0; i < 6; i++) {
        Vector3 a = Vector3Add(c, f[i].a), b = Vector3Add(c, f[i].b), cc = Vector3Add(c, f[i].cc), d = Vector3Add(c, f[i].d);
        LitVertex(a, f[i].n, col); LitVertex(b, f[i].n, col); LitVertex(cc, f[i].n, col);
        LitVertex(a, f[i].n, col); LitVertex(cc, f[i].n, col); LitVertex(d, f[i].n, col);
    }
    LE();
}

void DrawLitSphere(Vector3 c, Vector3 r, Color col, int rings, int slices)
{
    if (gCap) {
        /* automatic LOD: small parts (eyes, gloves, bolts) get far fewer segments */
        float mr = fmaxf(r.x, fmaxf(r.y, r.z));
        float det = gSphereDetail*Clamp(0.35f + mr*1.6f, 0.4f, 1.0f);
        if (det < 1.0f && gSphereDetail > 1.0f) det = fmaxf(det, 1.0f);
        rings = (int)(rings*det + 0.5f); slices = (int)(slices*det + 0.5f);
    }
    else if (G.settings.visualMode == 1) { rings = rings*2; slices = slices*2; }   /* ENHANCED: smoother models */
    if (rings < 3) rings = 3;
    if (slices < 4) slices = 4;
    LB();
    for (int i = 0; i < rings; i++) {
        float la0 = PI*((float)i/rings - 0.5f), la1 = PI*((float)(i + 1)/rings - 0.5f);
        for (int j = 0; j < slices; j++) {
            float lo0 = 2*PI*j/slices, lo1 = 2*PI*(j + 1)/slices;
            Vector3 n00 = { cosf(la0)*cosf(lo0), sinf(la0), cosf(la0)*sinf(lo0) };
            Vector3 n01 = { cosf(la0)*cosf(lo1), sinf(la0), cosf(la0)*sinf(lo1) };
            Vector3 n10 = { cosf(la1)*cosf(lo0), sinf(la1), cosf(la1)*sinf(lo0) };
            Vector3 n11 = { cosf(la1)*cosf(lo1), sinf(la1), cosf(la1)*sinf(lo1) };
            Vector3 p00 = { c.x + r.x*n00.x, c.y + r.y*n00.y, c.z + r.z*n00.z };
            Vector3 p01 = { c.x + r.x*n01.x, c.y + r.y*n01.y, c.z + r.z*n01.z };
            Vector3 p10 = { c.x + r.x*n10.x, c.y + r.y*n10.y, c.z + r.z*n10.z };
            Vector3 p11 = { c.x + r.x*n11.x, c.y + r.y*n11.y, c.z + r.z*n11.z };
            LitVertex(p00, n00, col); LitVertex(p11, n11, col); LitVertex(p01, n01, col);
            LitVertex(p00, n00, col); LitVertex(p10, n10, col); LitVertex(p11, n11, col);
        }
    }
    LE();
}

void DrawLitCylinderX(Vector3 c, float radius, float width, Color col, int sides)
{
    if (gCap) sides = (int)(sides*gSphereDetail + 0.5f);
    float hw = width*0.5f;
    Color hub = ColorScale(col, 1.6f);
    LB();
    for (int i = 0; i < sides; i++) {
        float a0 = 2*PI*i/sides, a1 = 2*PI*(i + 1)/sides;
        Vector3 n0 = { 0, cosf(a0), sinf(a0) }, n1 = { 0, cosf(a1), sinf(a1) };
        Vector3 l0 = { c.x - hw, c.y + n0.y*radius, c.z + n0.z*radius };
        Vector3 l1 = { c.x - hw, c.y + n1.y*radius, c.z + n1.z*radius };
        Vector3 r0 = { c.x + hw, c.y + n0.y*radius, c.z + n0.z*radius };
        Vector3 r1 = { c.x + hw, c.y + n1.y*radius, c.z + n1.z*radius };
        LitVertex(l0, n0, col); LitVertex(l1, n1, col); LitVertex(r1, n1, col);
        LitVertex(l0, n0, col); LitVertex(r1, n1, col); LitVertex(r0, n0, col);
        Vector3 cl = { c.x - hw, c.y, c.z }, cr = { c.x + hw, c.y, c.z };
        Color cap = (i & 1) ? hub : col;
        LitVertex(cl, (Vector3){-1,0,0}, cap); LitVertex(l1, (Vector3){-1,0,0}, cap); LitVertex(l0, (Vector3){-1,0,0}, cap);
        LitVertex(cr, (Vector3){1,0,0}, cap); LitVertex(r0, (Vector3){1,0,0}, cap); LitVertex(r1, (Vector3){1,0,0}, cap);
    }
    LE();
}

/* rounded / chamfered box: 6 inset faces + 12 edge bevels + 8 corner tris */
void DrawLitBevelBox(Vector3 c, Vector3 size, float b, Color col)
{
    float hx = size.x*0.5f, hy = size.y*0.5f, hz = size.z*0.5f;
    if (b > hx*0.9f) b = hx*0.9f;
    if (b > hy*0.9f) b = hy*0.9f;
    if (b > hz*0.9f) b = hz*0.9f;
    float ix = hx - b, iy = hy - b, iz = hz - b;
    #define BP(sx, sy, sz, ax) (Vector3){ c.x + (sx)*((ax) == 0 ? hx : ix), c.y + (sy)*((ax) == 1 ? hy : iy), c.z + (sz)*((ax) == 2 ? hz : iz) }
    LB();
    for (int ax = 0; ax < 3; ax++) for (int sg = -1; sg <= 1; sg += 2) {
        Vector3 n = { ax == 0 ? (float)sg : 0, ax == 1 ? (float)sg : 0, ax == 2 ? (float)sg : 0 };
        Vector3 q[4];
        int k = 0;
        for (int u = -1; u <= 1; u += 2) for (int v = -1; v <= 1; v += 2) {
            int sx = ax == 0 ? sg : u, sy = ax == 1 ? sg : (ax == 0 ? u : v), sz = ax == 2 ? sg : v;
            q[k++] = BP(sx, sy, sz, ax);
        }
        LitVertex(q[0], n, col); LitVertex(q[1], n, col); LitVertex(q[3], n, col);
        LitVertex(q[0], n, col); LitVertex(q[3], n, col); LitVertex(q[2], n, col);
    }
    for (int a1 = 0; a1 < 3; a1++) for (int a2 = a1 + 1; a2 < 3; a2++) {
        int a3 = 3 - a1 - a2;
        for (int s1 = -1; s1 <= 1; s1 += 2) for (int s2 = -1; s2 <= 1; s2 += 2) {
            Vector3 n = { 0, 0, 0 };
            float *nf = (float *)&n; nf[a1] = s1*0.7071f; nf[a2] = s2*0.7071f;
            Vector3 q[4]; int k = 0;
            for (int s3 = -1; s3 <= 1; s3 += 2) for (int which = 0; which < 2; which++) {
                int sg[3]; sg[a1] = s1; sg[a2] = s2; sg[a3] = s3;
                q[k++] = BP(sg[0], sg[1], sg[2], which == 0 ? a1 : a2);
            }
            LitVertex(q[0], n, col); LitVertex(q[1], n, col); LitVertex(q[3], n, col);
            LitVertex(q[0], n, col); LitVertex(q[3], n, col); LitVertex(q[2], n, col);
        }
    }
    for (int sx = -1; sx <= 1; sx += 2) for (int sy = -1; sy <= 1; sy += 2) for (int sz = -1; sz <= 1; sz += 2) {
        Vector3 n = { sx*0.577f, sy*0.577f, sz*0.577f };
        LitVertex(BP(sx, sy, sz, 0), n, col); LitVertex(BP(sx, sy, sz, 1), n, col); LitVertex(BP(sx, sy, sz, 2), n, col);
    }
    #undef BP
    LE();
}

/* Smooth rounded box built from a subdivided cube projected onto a rounded
   shell (seamless, smooth normals). taperX / taperY narrow / lower the +Z end
   (wedge noses). Vertical colour gradient bottom -> top. */
void DrawLitRoundBox(Vector3 c, Vector3 size, float r, float taperX, float taperY, Color top, Color bottom)
{
    float h[3] = { size.x*0.5f, size.y*0.5f, size.z*0.5f };
    float mn = fminf(h[0], fminf(h[1], h[2]));
    if (r > mn*0.98f) r = mn*0.98f;
    if (r < 0.001f) r = 0.001f;
    int S = gCap ? gRoundSegs : (G.settings.visualMode == 1 ? 2 : 1);
    if (gCap) { int sr = (int)ceilf(r*gRoundSegs/0.13f); if (sr < S) S = sr < 1 ? 1 : sr; }   /* small radius -> fewer bevel steps */
    int NP = 2*S + 2;
    float L[3][2*8 + 2];
    for (int a = 0; a < 3; a++) {
        float in = h[a] - r;
        for (int i = 0; i <= S; i++) {
            float th = (PI*0.25f)*(float)(S - i)/S;
            L[a][i] = -(in + r*tanf(th));
        }
        for (int i = 0; i <= S; i++) {
            float th = (PI*0.25f)*(float)i/S;
            L[a][S + 1 + i] = in + r*tanf(th);
        }
    }
    LB();
    for (int ax = 0; ax < 3; ax++) for (int sg = -1; sg <= 1; sg += 2) {
        int a1 = (ax + 1) % 3, a2 = (ax + 2) % 3;
        for (int i = 0; i < NP - 1; i++) for (int j = 0; j < NP - 1; j++) {
            Vector3 P[4], N[4]; Color C[4];
            for (int q = 0; q < 4; q++) {
                int ii = i + ((q == 1 || q == 2) ? 1 : 0), jj = j + ((q >= 2) ? 1 : 0);
                float cube[3];
                cube[ax] = sg*h[ax]; cube[a1] = L[a1][ii]; cube[a2] = L[a2][jj];
                float inner[3], d[3];
                for (int a = 0; a < 3; a++) { float in = h[a] - r; inner[a] = Clamp(cube[a], -in, in); d[a] = cube[a] - inner[a]; }
                float dl = sqrtf(d[0]*d[0] + d[1]*d[1] + d[2]*d[2]);
                if (dl < 1e-6f) { d[0] = d[1] = d[2] = 0; d[ax] = (float)sg; dl = 1; }
                Vector3 n = { d[0]/dl, d[1]/dl, d[2]/dl };
                Vector3 p = { inner[0] + n.x*r, inner[1] + n.y*r, inner[2] + n.z*r };
                float f = Clamp((p.z/h[2] + 1.0f)*0.5f, 0, 1);
                p.x *= 1.0f + (taperX - 1.0f)*f;
                if (p.y > 0) p.y *= 1.0f + (taperY - 1.0f)*f;
                C[q] = ColorMix(bottom, top, Clamp((p.y/h[1] + 1.0f)*0.5f, 0, 1));
                P[q] = Vector3Add(c, p); N[q] = n;
            }
            LitVertex(P[0], N[0], C[0]); LitVertex(P[1], N[1], C[1]); LitVertex(P[2], N[2], C[2]);
            LitVertex(P[0], N[0], C[0]); LitVertex(P[2], N[2], C[2]); LitVertex(P[3], N[3], C[3]);
        }
    }
    LE();
}

static void LitTube(Vector3 a, Vector3 b, float r, Color col, int sides);
/* open tube (no caps) - rims, frames */
void DrawLitTube(Vector3 a, Vector3 b, float r, Color col) { LitTube(a, b, r, col, gCap ? (gSphereDetail > 1.5f ? 7 : 5) : 6); }

/* tube with round ends from a to b */
void DrawLitCapsule(Vector3 a, Vector3 b, float r, Color col)
{
    if (Vector3Distance(a, b) < 1e-5f) { DrawLitSphere(a, (Vector3){ r, r, r }, col, 4, 6); return; }
    int sides = gCap ? (int)(6*gSphereDetail*Clamp(0.4f + r*6.0f, 0.5f, 1.0f) + 0.5f) : (G.settings.visualMode == 1 ? 12 : 6);
    if (sides < 5) sides = 5;
    LitTube(a, b, r, col, sides);
    DrawLitSphere(a, (Vector3){ r, r, r }, col, 2, 4);
    DrawLitSphere(b, (Vector3){ r, r, r }, col, 2, 4);
}

static void LitTube(Vector3 a, Vector3 b, float r, Color col, int sides)
{
    Vector3 d = Vector3Subtract(b, a);
    float len = Vector3Length(d);
    if (len < 1e-5f) return;
    Vector3 ax = Vector3Scale(d, 1.0f/len);
    Vector3 ref = fabsf(ax.y) < 0.9f ? (Vector3){ 0, 1, 0 } : (Vector3){ 1, 0, 0 };
    Vector3 u = Vector3Normalize(Vector3CrossProduct(ax, ref)), v = Vector3CrossProduct(ax, u);
    LB();
    for (int i = 0; i < sides; i++) {
        float a0 = 2*PI*i/sides, a1 = 2*PI*(i + 1)/sides;
        Vector3 n0 = Vector3Add(Vector3Scale(u, cosf(a0)), Vector3Scale(v, sinf(a0)));
        Vector3 n1 = Vector3Add(Vector3Scale(u, cosf(a1)), Vector3Scale(v, sinf(a1)));
        Vector3 p0 = Vector3Add(a, Vector3Scale(n0, r)), p1 = Vector3Add(a, Vector3Scale(n1, r));
        Vector3 q0 = Vector3Add(b, Vector3Scale(n0, r)), q1 = Vector3Add(b, Vector3Scale(n1, r));
        LitVertex(p0, n0, col); LitVertex(p1, n1, col); LitVertex(q1, n1, col);
        LitVertex(p0, n0, col); LitVertex(q1, n1, col); LitVertex(q0, n0, col);
    }
    LE();
}

/* kart wheel around the X axis at the origin: rounded tyre with tread blocks,
   rim and a hub cap */
void DrawLitWheel(float radius, float width, Color tyre, Color rim, Color cap, int sides)
{
    if (gCap) sides = (int)(sides*gSphereDetail + 0.5f);
    float hw = width*0.5f;
    /* tyre profile: (x, radius) */
    float px[8] = { -hw, -hw, -hw*0.86f, -hw*0.45f, hw*0.45f, hw*0.86f, hw, hw };
    float pr[8] = { 0.58f, 0.82f, 0.97f, 1.0f, 1.0f, 0.97f, 0.82f, 0.58f };
    float nx[8] = { -1, -0.9f, -0.55f, -0.1f, 0.1f, 0.55f, 0.9f, 1 };
    Color tread = ColorScale(tyre, 1.55f);
    LB();
    for (int i = 0; i < sides; i++) {
        float a0 = 2*PI*i/sides, a1 = 2*PI*(i + 1)/sides;
        Color tc = (i & 1) ? tyre : tread;
        for (int k = 0; k < 7; k++) {
            Color cc = (k >= 2 && k <= 4) ? tc : tyre;
            Vector3 na0 = Vector3Normalize((Vector3){ nx[k], cosf(a0), sinf(a0) }), na1 = Vector3Normalize((Vector3){ nx[k], cosf(a1), sinf(a1) });
            Vector3 nb0 = Vector3Normalize((Vector3){ nx[k + 1], cosf(a0), sinf(a0) }), nb1 = Vector3Normalize((Vector3){ nx[k + 1], cosf(a1), sinf(a1) });
            Vector3 A0 = { px[k], cosf(a0)*pr[k]*radius, sinf(a0)*pr[k]*radius }, A1 = { px[k], cosf(a1)*pr[k]*radius, sinf(a1)*pr[k]*radius };
            Vector3 B0 = { px[k + 1], cosf(a0)*pr[k + 1]*radius, sinf(a0)*pr[k + 1]*radius }, B1 = { px[k + 1], cosf(a1)*pr[k + 1]*radius, sinf(a1)*pr[k + 1]*radius };
            LitVertex(A0, na0, cc); LitVertex(A1, na1, cc); LitVertex(B1, nb1, cc);
            LitVertex(A0, na0, cc); LitVertex(B1, nb1, cc); LitVertex(B0, nb0, cc);
        }
        /* rim discs + hub cones on both sides */
        for (int sd = -1; sd <= 1; sd += 2) {
            float x = sd*hw*1.0f;
            Vector3 n = { (float)sd, 0, 0 };
            Vector3 r0 = { x, cosf(a0)*0.58f*radius, sinf(a0)*0.58f*radius }, r1 = { x, cosf(a1)*0.58f*radius, sinf(a1)*0.58f*radius };
            Vector3 h0 = { x + sd*0.02f, cosf(a0)*0.3f*radius, sinf(a0)*0.3f*radius }, h1 = { x + sd*0.02f, cosf(a1)*0.3f*radius, sinf(a1)*0.3f*radius };
            Vector3 tip = { x + sd*0.07f, 0, 0 };
            Color rc = (i % 4 == 0) ? ColorScale(rim, 0.75f) : rim;      /* spokes */
            LitVertex(r0, n, rc); LitVertex(r1, n, rc); LitVertex(h1, n, rc);
            LitVertex(r0, n, rc); LitVertex(h1, n, rc); LitVertex(h0, n, rc);
            Vector3 cn0 = Vector3Normalize((Vector3){ (float)sd, cosf(a0)*0.6f, sinf(a0)*0.6f }), cn1 = Vector3Normalize((Vector3){ (float)sd, cosf(a1)*0.6f, sinf(a1)*0.6f });
            LitVertex(h0, cn0, cap); LitVertex(h1, cn1, cap); LitVertex(tip, n, cap);
        }
    }
    LE();
}

void DrawLitCylinderY(Vector3 base, float rBottom, float rTop, float h, Color col, int sides)
{
    if (gCap) sides = (int)(sides*gSphereDetail + 0.5f);
    LB();
    for (int i = 0; i < sides; i++) {
        float a0 = 2*PI*i/sides, a1 = 2*PI*(i + 1)/sides;
        Vector3 n0 = { cosf(a0), 0.3f, sinf(a0) }, n1 = { cosf(a1), 0.3f, sinf(a1) };
        Vector3 b0 = { base.x + cosf(a0)*rBottom, base.y, base.z + sinf(a0)*rBottom };
        Vector3 b1 = { base.x + cosf(a1)*rBottom, base.y, base.z + sinf(a1)*rBottom };
        Vector3 t0 = { base.x + cosf(a0)*rTop, base.y + h, base.z + sinf(a0)*rTop };
        Vector3 t1 = { base.x + cosf(a1)*rTop, base.y + h, base.z + sinf(a1)*rTop };
        Vector3 top = { base.x, base.y + h, base.z };
        LitVertex(b0, n0, col); LitVertex(t1, n1, col); LitVertex(b1, n1, col);
        LitVertex(b0, n0, col); LitVertex(t0, n0, col); LitVertex(t1, n1, col);
        if (rTop > 0.001f) { LitVertex(top, (Vector3){0,1,0}, col); LitVertex(t1, (Vector3){0,1,0}, col); LitVertex(t0, (Vector3){0,1,0}, col); }
    }
    LE();
}

/* surface of revolution around Y: profile (radius[i], y[i]) */
void DrawLitLathe(const float *rad, const float *ys, int n, int sides, Color col)
{
    if (gCap) sides = (int)(sides*gSphereDetail + 0.5f);
    if (sides < 6) sides = 6;
    LB();
    for (int k = 0; k < n - 1; k++) {
        float dr = rad[k + 1] - rad[k], dy = ys[k + 1] - ys[k];
        float l = sqrtf(dr*dr + dy*dy); if (l < 1e-6f) continue;
        float ny = -dr/l, nr = dy/l;               /* outward profile normal */
        for (int i = 0; i < sides; i++) {
            float a0 = 2*PI*i/sides, a1 = 2*PI*(i + 1)/sides;
            Vector3 n0 = { cosf(a0)*nr, ny, sinf(a0)*nr }, n1 = { cosf(a1)*nr, ny, sinf(a1)*nr };
            Vector3 A0 = { cosf(a0)*rad[k], ys[k], sinf(a0)*rad[k] }, A1 = { cosf(a1)*rad[k], ys[k], sinf(a1)*rad[k] };
            Vector3 B0 = { cosf(a0)*rad[k + 1], ys[k + 1], sinf(a0)*rad[k + 1] }, B1 = { cosf(a1)*rad[k + 1], ys[k + 1], sinf(a1)*rad[k + 1] };
            LitVertex(A0, n0, col); LitVertex(A1, n1, col); LitVertex(B1, n1, col);
            LitVertex(A0, n0, col); LitVertex(B1, n1, col); LitVertex(B0, n0, col);
        }
    }
    LE();
}

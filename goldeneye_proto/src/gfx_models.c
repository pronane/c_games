/*
 * gfx_models.c - mesh builder, textured boxes/cylinders, humanoid characters,
 * first-person weapon models. Everything is built in code from primitives.
 */

typedef struct {
    float *v, *t, *n;
    unsigned char *c;
    int count, cap;
} MB;

static void MBReserve(MB *b, int extra)
{
    if (b->count + extra <= b->cap) return;
    int nc = b->cap ? b->cap*2 : 1024;
    while (nc < b->count + extra) nc *= 2;
    b->v = (float *)MemRealloc(b->v, nc*3*sizeof(float));
    b->t = (float *)MemRealloc(b->t, nc*2*sizeof(float));
    b->n = (float *)MemRealloc(b->n, nc*3*sizeof(float));
    b->c = (unsigned char *)MemRealloc(b->c, nc*4);
    b->cap = nc;
}
static void MBVert(MB *b, Vector3 p, float u, float v, Vector3 n, Color col)
{
    MBReserve(b, 1);
    int i = b->count++;
    b->v[i*3] = p.x; b->v[i*3 + 1] = p.y; b->v[i*3 + 2] = p.z;
    b->t[i*2] = u; b->t[i*2 + 1] = v;
    b->n[i*3] = n.x; b->n[i*3 + 1] = n.y; b->n[i*3 + 2] = n.z;
    b->c[i*4] = col.r; b->c[i*4 + 1] = col.g; b->c[i*4 + 2] = col.b; b->c[i*4 + 3] = col.a;
}
/* quad p0..p3 counter-clockwise seen from the front; uv given per corner */
static void MBQuad(MB *b, Vector3 p0, Vector3 p1, Vector3 p2, Vector3 p3, Vector2 t0, Vector2 t1, Vector2 t2, Vector2 t3, Vector3 n, Color col)
{
    MBVert(b, p0, t0.x, t0.y, n, col); MBVert(b, p1, t1.x, t1.y, n, col); MBVert(b, p2, t2.x, t2.y, n, col);
    MBVert(b, p0, t0.x, t0.y, n, col); MBVert(b, p2, t2.x, t2.y, n, col); MBVert(b, p3, t3.x, t3.y, n, col);
}
/* subdivided quad: origin O, axis U (u direction), axis V (up in texture); U x V = normal */
static void MBGrid(MB *b, Vector3 O, Vector3 U, Vector3 V, int nu, int nv, float u0, float u1, float v0, float v1)
{
    Vector3 n = Vector3Normalize(Vector3CrossProduct(U, V));
    for (int j = 0; j < nv; j++) for (int i = 0; i < nu; i++) {
        float a0 = (float)i/nu, a1 = (float)(i + 1)/nu, b0 = (float)j/nv, b1 = (float)(j + 1)/nv;
        Vector3 p0 = Vector3Add(O, Vector3Add(Vector3Scale(U, a0), Vector3Scale(V, b0)));
        Vector3 p1 = Vector3Add(O, Vector3Add(Vector3Scale(U, a1), Vector3Scale(V, b0)));
        Vector3 p2 = Vector3Add(O, Vector3Add(Vector3Scale(U, a1), Vector3Scale(V, b1)));
        Vector3 p3 = Vector3Add(O, Vector3Add(Vector3Scale(U, a0), Vector3Scale(V, b1)));
        float ua = u0 + (u1 - u0)*a0, ub = u0 + (u1 - u0)*a1;
        float va = v0 + (v1 - v0)*b0, vb = v0 + (v1 - v0)*b1;
        MBQuad(b, p0, p1, p2, p3, (Vector2){ ua, va }, (Vector2){ ub, va }, (Vector2){ ub, vb }, (Vector2){ ua, vb }, n, WHITE);
    }
}

/* Box faces: 0 +X front, 1 -X back, 2 +Z, 3 -Z, 4 +Y top, 5 -Y bottom */
static const Vector3 BOX_N[6] = { { 1, 0, 0 }, { -1, 0, 0 }, { 0, 0, 1 }, { 0, 0, -1 }, { 0, 1, 0 }, { 0, -1, 0 } };
static const Vector3 BOX_U[6] = { { 0, 0, -1 }, { 0, 0, 1 }, { 1, 0, 0 }, { -1, 0, 0 }, { 1, 0, 0 }, { 1, 0, 0 } };
static const Vector3 BOX_V[6] = { { 0, 1, 0 }, { 0, 1, 0 }, { 0, 1, 0 }, { 0, 1, 0 }, { 0, 0, -1 }, { 0, 0, 1 } };
static const float BOX_SHADE[6] = { 0.86f, 0.70f, 0.80f, 0.76f, 1.0f, 0.5f };

static float AxisExtent(Vector3 a, Vector3 size) { return fabsf(a.x)*size.x + fabsf(a.y)*size.y + fabsf(a.z)*size.z; }

/*
 * Generic box. uvRect[f] = atlas rect in pixels (atlasW>0) or NULL for world-tiled UVs
 * (tile = world units per texture repeat). xf transforms the box (rotation etc).
 * shade: bake simple directional shading into vertex colours (dynamic objects).
 */
static void MBBox(MB *b, Vector3 center, Vector3 size, Matrix xf, const Rectangle *uvRect, float atlasW, float atlasH, float tile, bool shade, unsigned faceMask)
{
    for (int f = 0; f < 6; f++) {
        if (!(faceMask & (1u << f))) continue;
        Vector3 n = BOX_N[f], U = BOX_U[f], V = BOX_V[f];
        float eu = AxisExtent(U, size), ev = AxisExtent(V, size), en = AxisExtent(n, size);
        Vector3 c = Vector3Add(center, Vector3Scale(n, en*0.5f));
        Vector3 p[4];
        float s[4] = { 0, 1, 1, 0 }, t[4] = { 0, 0, 1, 1 };
        for (int k = 0; k < 4; k++) {
            p[k] = Vector3Add(c, Vector3Add(Vector3Scale(U, (s[k] - 0.5f)*eu), Vector3Scale(V, (t[k] - 0.5f)*ev)));
            p[k] = Vector3Transform(p[k], xf);
        }
        Vector2 uv[4];
        for (int k = 0; k < 4; k++) {
            if (uvRect) {
                Rectangle r = uvRect[f];
                uv[k] = (Vector2){ (r.x + 0.5f + s[k]*(r.width - 1.0f))/atlasW, (r.y + 0.5f + (1 - t[k])*(r.height - 1.0f))/atlasH };
            } else {
                uv[k] = (Vector2){ s[k]*eu/tile, (1 - t[k])*ev/tile };
            }
        }
        Vector3 nw = Vector3Normalize(Vector3Subtract(Vector3Transform(n, xf), Vector3Transform((Vector3){ 0 }, xf)));
        float sh = shade ? BOX_SHADE[f] : 1.0f;
        Color col = { ClampB(255*sh), ClampB(255*sh), ClampB(255*sh), 255 };
        MBQuad(b, p[0], p[1], p[2], p[3], uv[0], uv[1], uv[2], uv[3], nw, col);
    }
}
#define ALLF 0x3Fu

/* cylinder from base along axis; UV u wraps around, v along length */
static void MBCylinder(MB *b, Vector3 base, Vector3 axis, float r, float len, int slices, float vTile, bool caps, bool shade, Matrix xf)
{
    Vector3 a = Vector3Normalize(axis);
    Vector3 ref = fabsf(a.y) < 0.9f ? (Vector3){ 0, 1, 0 } : (Vector3){ 1, 0, 0 };
    Vector3 e1 = Vector3Normalize(Vector3CrossProduct(a, ref));
    Vector3 e2 = Vector3CrossProduct(e1, a);
    Vector3 top = Vector3Add(base, Vector3Scale(a, len));
    for (int i = 0; i < slices; i++) {
        float t0 = (float)i/slices*2*PI, t1 = (float)(i + 1)/slices*2*PI;
        Vector3 d0 = Vector3Add(Vector3Scale(e1, cosf(t0)), Vector3Scale(e2, sinf(t0)));
        Vector3 d1 = Vector3Add(Vector3Scale(e1, cosf(t1)), Vector3Scale(e2, sinf(t1)));
        Vector3 p0 = Vector3Add(base, Vector3Scale(d0, r)), p1 = Vector3Add(base, Vector3Scale(d1, r));
        Vector3 p2 = Vector3Add(top, Vector3Scale(d1, r)), p3 = Vector3Add(top, Vector3Scale(d0, r));
        Vector3 nm = Vector3Normalize(Vector3Add(d0, d1));
        float sh = shade ? 0.62f + 0.38f*Clamp(0.5f + 0.5f*Vector3DotProduct(nm, (Vector3){ 0.3f, 0.9f, 0.3f }), 0, 1) : 1.0f;
        Color col = { ClampB(255*sh), ClampB(255*sh), ClampB(255*sh), 255 };
        /* winding: p0,p1 along +theta at base; ensure outward normal is CCW */
        Vector3 q0 = Vector3Transform(p0, xf), q1 = Vector3Transform(p1, xf), q2 = Vector3Transform(p2, xf), q3 = Vector3Transform(p3, xf);
        Vector3 nn = Vector3Normalize(Vector3Subtract(Vector3Transform(nm, xf), Vector3Transform((Vector3){ 0 }, xf)));
        Vector3 cr = Vector3CrossProduct(Vector3Subtract(q1, q0), Vector3Subtract(q3, q0));
        float u0 = (float)i/slices, u1 = (float)(i + 1)/slices;
        if (Vector3DotProduct(cr, nn) >= 0)
            MBQuad(b, q0, q1, q2, q3, (Vector2){ u0, len/vTile }, (Vector2){ u1, len/vTile }, (Vector2){ u1, 0 }, (Vector2){ u0, 0 }, nn, col);
        else
            MBQuad(b, q1, q0, q3, q2, (Vector2){ u1, len/vTile }, (Vector2){ u0, len/vTile }, (Vector2){ u0, 0 }, (Vector2){ u1, 0 }, nn, col);
        if (caps) {
            Vector3 ends[2] = { base, top };
            for (int e = 0; e < 2; e++) {
                Vector3 cc = Vector3Transform(ends[e], xf);
                Vector3 r0 = Vector3Transform(Vector3Add(ends[e], Vector3Scale(d0, r)), xf), r1 = Vector3Transform(Vector3Add(ends[e], Vector3Scale(d1, r)), xf);
                Vector3 cn = Vector3Normalize(Vector3Subtract(Vector3Transform(e ? a : Vector3Negate(a), xf), Vector3Transform((Vector3){ 0 }, xf)));
                Vector3 crs = Vector3CrossProduct(Vector3Subtract(r0, cc), Vector3Subtract(r1, cc));
                Color cc2 = { ClampB(col.r*0.9f), ClampB(col.g*0.9f), ClampB(col.b*0.9f), 255 };
                Vector2 tc = { 0.5f, 0.5f }, ta = { 0.5f + 0.5f*cosf(t0), 0.5f + 0.5f*sinf(t0) }, tb = { 0.5f + 0.5f*cosf(t1), 0.5f + 0.5f*sinf(t1) };
                if (Vector3DotProduct(crs, cn) >= 0) { MBVert(b, cc, tc.x, tc.y, cn, cc2); MBVert(b, r0, ta.x, ta.y, cn, cc2); MBVert(b, r1, tb.x, tb.y, cn, cc2); }
                else { MBVert(b, cc, tc.x, tc.y, cn, cc2); MBVert(b, r1, tb.x, tb.y, cn, cc2); MBVert(b, r0, ta.x, ta.y, cn, cc2); }
            }
        }
    }
}

static Mesh MBToMesh(MB *b)
{
    Mesh m = { 0 };
    m.vertexCount = b->count;
    m.triangleCount = b->count/3;
    m.vertices = (float *)MemAlloc(b->count*3*sizeof(float)); memcpy(m.vertices, b->v, b->count*3*sizeof(float));
    m.texcoords = (float *)MemAlloc(b->count*2*sizeof(float)); memcpy(m.texcoords, b->t, b->count*2*sizeof(float));
    m.normals = (float *)MemAlloc(b->count*3*sizeof(float)); memcpy(m.normals, b->n, b->count*3*sizeof(float));
    m.colors = (unsigned char *)MemAlloc(b->count*4); memcpy(m.colors, b->c, b->count*4);
    UploadMesh(&m, false);
    return m;
}
static void MBFree(MB *b) { MemFree(b->v); MemFree(b->t); MemFree(b->n); MemFree(b->c); memset(b, 0, sizeof(*b)); }
static Mesh MBFinish(MB *b) { Mesh m = MBToMesh(b); MBFree(b); return m; }

/* ---------------- character parts ---------------- */
static Rectangle Cell(int id) { int x, y; CellRect(id, &x, &y); return (Rectangle){ (float)x, (float)y, 64, 64 }; }
static void Faces6(Rectangle *r, int front, int back, int left, int right, int top, int bottom)
{
    r[0] = Cell(front); r[1] = Cell(back); r[2] = Cell(left); r[3] = Cell(right); r[4] = Cell(top); r[5] = Cell(bottom);
}

typedef enum { CP_TORSO, CP_HIPS, CP_HEAD, CP_HELMET, CP_CAP, CP_BEANIE, CP_UPPERARM, CP_FOREARM, CP_THIGH, CP_SHIN, CP_RIFLE, CP_COUNT } CharPart;
static Mesh charMesh[CP_COUNT];

static void BuildCharacterMeshes(void)
{
    Rectangle r[6];
    Matrix I = MatrixIdentity();
    MB b = { 0 };
    /* torso: pivot at waist, 0.56 tall */
    Faces6(r, AT_TORSOF, AT_TORSOB, AT_TORSOS, AT_TORSOS, AT_TORSOS, AT_TORSOS);
    MBBox(&b, (Vector3){ 0, 0.30f, 0 }, (Vector3){ 0.26f, 0.48f, 0.46f }, I, r, 256, 256, 0, true, ALLF);
    MBBox(&b, (Vector3){ 0, 0.06f, 0 }, (Vector3){ 0.23f, 0.12f, 0.40f }, I, r, 256, 256, 0, true, ALLF);
    Faces6(r, AT_SLEEVE, AT_SLEEVE, AT_SLEEVE, AT_SLEEVE, AT_SLEEVE, AT_SLEEVE);
    MBBox(&b, (Vector3){ 0, 0.50f, 0.20f }, (Vector3){ 0.2f, 0.1f, 0.14f }, I, r, 256, 256, 0, true, ALLF);
    MBBox(&b, (Vector3){ 0, 0.50f, -0.20f }, (Vector3){ 0.2f, 0.1f, 0.14f }, I, r, 256, 256, 0, true, ALLF);
    charMesh[CP_TORSO] = MBFinish(&b);
    Faces6(r, AT_BELT, AT_BELT, AT_BELT, AT_BELT, AT_PANTS, AT_PANTS);
    MBBox(&b, (Vector3){ 0, -0.05f, 0 }, (Vector3){ 0.24f, 0.16f, 0.40f }, I, r, 256, 256, 0, true, ALLF);
    charMesh[CP_HIPS] = MBFinish(&b);
    /* head with neck: pivot at neck base */
    Faces6(r, AT_HAND, AT_HAND, AT_HAND, AT_HAND, AT_HAND, AT_HAND);
    MBBox(&b, (Vector3){ 0, 0.04f, 0 }, (Vector3){ 0.11f, 0.08f, 0.11f }, I, r, 256, 256, 0, true, ALLF);
    Faces6(r, AT_FACE, AT_HEADBACK, AT_HEADSIDE, AT_HEADSIDE, AT_HEADTOP, AT_HAND);
    MBBox(&b, (Vector3){ 0.01f, 0.205f, 0 }, (Vector3){ 0.24f, 0.27f, 0.22f }, I, r, 256, 256, 0, true, ALLF);
    Faces6(r, AT_HAND, AT_HAND, AT_HAND, AT_HAND, AT_HAND, AT_HAND);
    MBBox(&b, (Vector3){ 0.135f, 0.19f, 0 }, (Vector3){ 0.04f, 0.06f, 0.05f }, I, r, 256, 256, 0, true, ALLF); /* nose */
    charMesh[CP_HEAD] = MBFinish(&b);
    Faces6(r, AT_HATSIDE, AT_HATSIDE, AT_HATSIDE, AT_HATSIDE, AT_HATTOP, AT_HATSIDE);
    MBBox(&b, (Vector3){ 0.01f, 0.36f, 0 }, (Vector3){ 0.29f, 0.10f, 0.27f }, I, r, 256, 256, 0, true, ALLF);
    MBBox(&b, (Vector3){ 0.01f, 0.30f, 0 }, (Vector3){ 0.33f, 0.04f, 0.31f }, I, r, 256, 256, 0, true, ALLF);
    MBBox(&b, (Vector3){ 0.0f, 0.42f, 0 }, (Vector3){ 0.22f, 0.04f, 0.2f }, I, r, 256, 256, 0, true, ALLF);
    charMesh[CP_HELMET] = MBFinish(&b);
    MBBox(&b, (Vector3){ 0.0f, 0.36f, 0 }, (Vector3){ 0.27f, 0.09f, 0.25f }, I, r, 256, 256, 0, true, ALLF);
    MBBox(&b, (Vector3){ 0.17f, 0.32f, 0 }, (Vector3){ 0.12f, 0.02f, 0.22f }, I, r, 256, 256, 0, true, ALLF);
    MBBox(&b, (Vector3){ 0.02f, 0.42f, 0 }, (Vector3){ 0.30f, 0.04f, 0.27f }, I, r, 256, 256, 0, true, ALLF);
    charMesh[CP_CAP] = MBFinish(&b);
    MBBox(&b, (Vector3){ 0.0f, 0.35f, 0 }, (Vector3){ 0.26f, 0.09f, 0.24f }, I, r, 256, 256, 0, true, ALLF);
    charMesh[CP_BEANIE] = MBFinish(&b);
    /* arms: pivot at shoulder / elbow, hanging down -Y */
    Faces6(r, AT_SLEEVE, AT_SLEEVE, AT_SLEEVE, AT_SLEEVE, AT_SLEEVE, AT_SLEEVE);
    MBBox(&b, (Vector3){ 0, -0.14f, 0 }, (Vector3){ 0.13f, 0.30f, 0.13f }, I, r, 256, 256, 0, true, ALLF);
    charMesh[CP_UPPERARM] = MBFinish(&b);
    MBBox(&b, (Vector3){ 0, -0.12f, 0 }, (Vector3){ 0.115f, 0.26f, 0.115f }, I, r, 256, 256, 0, true, ALLF);
    Faces6(r, AT_HAND, AT_HAND, AT_HAND, AT_HAND, AT_HAND, AT_HAND);
    MBBox(&b, (Vector3){ 0.01f, -0.30f, 0 }, (Vector3){ 0.10f, 0.11f, 0.06f }, I, r, 256, 256, 0, true, ALLF);
    MBBox(&b, (Vector3){ 0.05f, -0.27f, 0.03f }, (Vector3){ 0.03f, 0.06f, 0.03f }, I, r, 256, 256, 0, true, ALLF);
    charMesh[CP_FOREARM] = MBFinish(&b);
    Faces6(r, AT_PANTS, AT_PANTS, AT_PANTS, AT_PANTS, AT_PANTS, AT_PANTS);
    MBBox(&b, (Vector3){ 0, -0.23f, 0 }, (Vector3){ 0.18f, 0.48f, 0.17f }, I, r, 256, 256, 0, true, ALLF);
    charMesh[CP_THIGH] = MBFinish(&b);
    MBBox(&b, (Vector3){ 0, -0.20f, 0 }, (Vector3){ 0.15f, 0.40f, 0.145f }, I, r, 256, 256, 0, true, ALLF);
    Faces6(r, AT_BOOT, AT_BOOT, AT_BOOT, AT_BOOT, AT_BOOT, AT_BOOT);
    MBBox(&b, (Vector3){ 0.03f, -0.36f, 0 }, (Vector3){ 0.19f, 0.12f, 0.16f }, I, r, 256, 256, 0, true, ALLF);
    MBBox(&b, (Vector3){ 0.05f, -0.475f, 0 }, (Vector3){ 0.29f, 0.11f, 0.16f }, I, r, 256, 256, 0, true, ALLF);
    charMesh[CP_SHIN] = MBFinish(&b);
    /* rifle held by guards (points +X) */
    Faces6(r, AT_GUN, AT_GUN, AT_GUN, AT_GUN, AT_GUN, AT_GUN);
    MBBox(&b, (Vector3){ 0.10f, 0.0f, 0 }, (Vector3){ 0.42f, 0.08f, 0.05f }, I, r, 256, 256, 0, true, ALLF);
    MBBox(&b, (Vector3){ 0.42f, 0.01f, 0 }, (Vector3){ 0.26f, 0.025f, 0.025f }, I, r, 256, 256, 0, true, ALLF);
    MBBox(&b, (Vector3){ 0.12f, -0.11f, 0 }, (Vector3){ 0.06f, 0.16f, 0.035f }, MatrixRotateZ(-0.35f), r, 256, 256, 0, true, ALLF);
    MBBox(&b, (Vector3){ 0.0f, -0.07f, 0 }, (Vector3){ 0.05f, 0.10f, 0.04f }, I, r, 256, 256, 0, true, ALLF);
    Faces6(r, AT_WOOD, AT_WOOD, AT_WOOD, AT_WOOD, AT_WOOD, AT_WOOD);
    MBBox(&b, (Vector3){ -0.21f, -0.03f, 0 }, (Vector3){ 0.24f, 0.09f, 0.045f }, I, r, 256, 256, 0, true, ALLF);
    MBBox(&b, (Vector3){ 0.25f, -0.01f, 0 }, (Vector3){ 0.16f, 0.06f, 0.055f }, I, r, 256, 256, 0, true, ALLF);
    charMesh[CP_RIFLE] = MBFinish(&b);
}

/* ---------------- first-person weapons (local: x right, y up, -z forward) ---------------- */
typedef enum { VM_PISTOL_SLIDE, VM_PISTOL_FRAME, VM_PISTOL_GRIP, VM_SILENCER, VM_RIFLE_METAL, VM_RIFLE_WOOD, VM_RIFLE_GRIP,
               VM_HAND_R, VM_HAND_L, VM_SLEEVE_R, VM_SLEEVE_L, VM_CUFF_R, VM_CUFF_L, VM_COUNT } VmPart;
static Mesh vmMesh[VM_COUNT];

static void BuildWeaponMeshes(void)
{
    Matrix I = MatrixIdentity();
    MB b = { 0 };
    const float T = 0.08f;  /* texture tile size for weapon parts */
    /* PP7-style compact pistol */
    MBBox(&b, (Vector3){ 0, 0.022f, -0.075f }, (Vector3){ 0.030f, 0.032f, 0.165f }, I, NULL, 0, 0, T, true, ALLF);
    for (int k = 0; k < 6; k++) MBBox(&b, (Vector3){ 0, 0.022f, 0.0f - k*0.006f }, (Vector3){ 0.032f, 0.026f, 0.002f }, I, NULL, 0, 0, T, true, ALLF);
    MBBox(&b, (Vector3){ 0, 0.042f, -0.150f }, (Vector3){ 0.006f, 0.008f, 0.006f }, I, NULL, 0, 0, T, true, ALLF);
    MBBox(&b, (Vector3){ 0, 0.041f, 0.000f }, (Vector3){ 0.022f, 0.007f, 0.008f }, I, NULL, 0, 0, T, true, ALLF);
    MBCylinder(&b, (Vector3){ 0, 0.022f, -0.158f }, (Vector3){ 0, 0, -1 }, 0.0075f, 0.004f, 10, 0.05f, true, true, I);
    vmMesh[VM_PISTOL_SLIDE] = MBFinish(&b);
    MBBox(&b, (Vector3){ 0, 0.0f, -0.06f }, (Vector3){ 0.028f, 0.018f, 0.13f }, I, NULL, 0, 0, T, true, ALLF);
    MBBox(&b, (Vector3){ 0, -0.025f, -0.075f }, (Vector3){ 0.008f, 0.004f, 0.05f }, I, NULL, 0, 0, T, true, ALLF);
    MBBox(&b, (Vector3){ 0, -0.016f, -0.098f }, (Vector3){ 0.008f, 0.02f, 0.004f }, I, NULL, 0, 0, T, true, ALLF);
    MBBox(&b, (Vector3){ 0, -0.014f, -0.062f }, (Vector3){ 0.004f, 0.016f, 0.004f }, MatrixRotateX(0.3f), NULL, 0, 0, T, true, ALLF);
    vmMesh[VM_PISTOL_FRAME] = MBFinish(&b);
    MBBox(&b, (Vector3){ 0, -0.055f, 0.005f }, (Vector3){ 0.029f, 0.085f, 0.042f }, MatrixRotateX(0.28f), NULL, 0, 0, 0.03f, true, ALLF);
    vmMesh[VM_PISTOL_GRIP] = MBFinish(&b);
    MBCylinder(&b, (Vector3){ 0, 0.022f, -0.150f }, (Vector3){ 0, 0, -1 }, 0.0145f, 0.135f, 14, 0.08f, true, true, I);
    MBCylinder(&b, (Vector3){ 0, 0.022f, -0.150f }, (Vector3){ 0, 0, -1 }, 0.0155f, 0.012f, 14, 0.08f, false, true, I);
    MBCylinder(&b, (Vector3){ 0, 0.022f, -0.275f }, (Vector3){ 0, 0, -1 }, 0.0155f, 0.010f, 14, 0.08f, false, true, I);
    vmMesh[VM_SILENCER] = MBFinish(&b);
    /* KF7-style assault rifle */
    MBBox(&b, (Vector3){ 0, 0.0f, -0.08f }, (Vector3){ 0.046f, 0.062f, 0.30f }, I, NULL, 0, 0, T, true, ALLF);
    MBBox(&b, (Vector3){ 0, 0.036f, -0.10f }, (Vector3){ 0.036f, 0.014f, 0.24f }, I, NULL, 0, 0, T, true, ALLF);
    MBBox(&b, (Vector3){ 0, 0.060f, -0.36f }, (Vector3){ 0.006f, 0.04f, 0.008f }, I, NULL, 0, 0, T, true, ALLF);
    MBBox(&b, (Vector3){ 0, 0.050f, 0.02f }, (Vector3){ 0.026f, 0.018f, 0.02f }, I, NULL, 0, 0, T, true, ALLF);
    MBCylinder(&b, (Vector3){ 0, 0.012f, -0.23f }, (Vector3){ 0, 0, -1 }, 0.009f, 0.22f, 12, 0.08f, true, true, I);
    MBCylinder(&b, (Vector3){ 0, 0.012f, -0.43f }, (Vector3){ 0, 0, -1 }, 0.013f, 0.04f, 12, 0.08f, true, true, I);
    MBCylinder(&b, (Vector3){ 0, 0.038f, -0.23f }, (Vector3){ 0, 0, -1 }, 0.006f, 0.12f, 8, 0.08f, true, true, I);
    /* curved magazine: three angled segments */
    for (int k = 0; k < 3; k++) {
        Matrix m = MatrixMultiply(MatrixRotateX(-0.15f - k*0.18f), MatrixTranslate(0, -0.05f - k*0.055f, -0.13f - k*0.018f*k));
        MBBox(&b, (Vector3){ 0, 0, 0 }, (Vector3){ 0.032f, 0.062f, 0.05f }, m, NULL, 0, 0, T, true, ALLF);
    }
    MBBox(&b, (Vector3){ 0, -0.040f, -0.05f }, (Vector3){ 0.008f, 0.004f, 0.05f }, I, NULL, 0, 0, T, true, ALLF);
    vmMesh[VM_RIFLE_METAL] = MBFinish(&b);
    MBBox(&b, (Vector3){ 0, -0.002f, -0.31f }, (Vector3){ 0.05f, 0.05f, 0.16f }, I, NULL, 0, 0, 0.1f, true, ALLF);
    MBBox(&b, (Vector3){ 0, -0.03f, 0.16f }, (Vector3){ 0.04f, 0.075f, 0.22f }, MatrixRotateX(0.12f), NULL, 0, 0, 0.1f, true, ALLF);
    vmMesh[VM_RIFLE_WOOD] = MBFinish(&b);
    MBBox(&b, (Vector3){ 0, -0.07f, 0.04f }, (Vector3){ 0.03f, 0.09f, 0.04f }, MatrixRotateX(0.35f), NULL, 0, 0, 0.03f, true, ALLF);
    vmMesh[VM_RIFLE_GRIP] = MBFinish(&b);
    /* right hand wrapped around a grip at the origin */
    MBBox(&b, (Vector3){ 0.004f, -0.055f, 0.022f }, (Vector3){ 0.05f, 0.08f, 0.05f }, MatrixRotateX(0.28f), NULL, 0, 0, 0.05f, true, ALLF);
    for (int k = 0; k < 4; k++) MBBox(&b, (Vector3){ -0.004f, -0.035f - k*0.017f, -0.018f }, (Vector3){ 0.044f, 0.015f, 0.026f }, MatrixRotateX(0.28f), NULL, 0, 0, 0.05f, true, ALLF);
    MBBox(&b, (Vector3){ -0.024f, -0.012f, -0.012f }, (Vector3){ 0.016f, 0.016f, 0.05f }, MatrixRotateX(0.1f), NULL, 0, 0, 0.05f, true, ALLF);
    vmMesh[VM_HAND_R] = MBFinish(&b);
    /* left support hand (palm up under a handguard at origin) */
    MBBox(&b, (Vector3){ -0.01f, -0.04f, 0.0f }, (Vector3){ 0.05f, 0.035f, 0.09f }, I, NULL, 0, 0, 0.05f, true, ALLF);
    for (int k = 0; k < 4; k++) MBBox(&b, (Vector3){ 0.028f, -0.01f, -0.03f + k*0.02f }, (Vector3){ 0.02f, 0.05f, 0.017f }, I, NULL, 0, 0, 0.05f, true, ALLF);
    MBBox(&b, (Vector3){ -0.032f, -0.01f, 0.01f }, (Vector3){ 0.016f, 0.04f, 0.02f }, I, NULL, 0, 0, 0.05f, true, ALLF);
    vmMesh[VM_HAND_L] = MBFinish(&b);
    /* sleeves: long boxes from the wrist back towards the screen edge */
    MBBox(&b, (Vector3){ 0, 0, 0.21f }, (Vector3){ 0.085f, 0.085f, 0.42f }, I, NULL, 0, 0, 0.12f, true, ALLF);
    vmMesh[VM_SLEEVE_R] = MBFinish(&b);
    MBBox(&b, (Vector3){ 0, 0, 0.21f }, (Vector3){ 0.085f, 0.085f, 0.42f }, I, NULL, 0, 0, 0.12f, true, ALLF);
    vmMesh[VM_SLEEVE_L] = MBFinish(&b);
    MBBox(&b, (Vector3){ 0, 0, 0.012f }, (Vector3){ 0.074f, 0.074f, 0.026f }, I, NULL, 0, 0, 0.05f, true, ALLF);
    vmMesh[VM_CUFF_R] = MBFinish(&b);
    MBBox(&b, (Vector3){ 0, 0, 0.012f }, (Vector3){ 0.074f, 0.074f, 0.026f }, I, NULL, 0, 0, 0.05f, true, ALLF);
    vmMesh[VM_CUFF_L] = MBFinish(&b);
}

/* ---------------- pickups / dynamic props ---------------- */
typedef enum { PM_AMMOBOX, PM_VEST, PM_DISK, PM_DOOR, PM_PADLOCK, PM_LAMP, PM_COUNT } PickMeshId;
static Mesh pickMesh[PM_COUNT];

static void BuildMiscMeshes(void)
{
    Matrix I = MatrixIdentity();
    MB b = { 0 };
    Rectangle full[6]; for (int f = 0; f < 6; f++) full[f] = (Rectangle){ 0, 0, 128, 128 };
    MBBox(&b, (Vector3){ 0, 0.14f, 0 }, (Vector3){ 0.42f, 0.28f, 0.26f }, I, full, 128, 128, 0, true, ALLF);
    MBBox(&b, (Vector3){ 0, 0.30f, 0 }, (Vector3){ 0.12f, 0.04f, 0.06f }, I, full, 128, 128, 0, true, ALLF);
    pickMesh[PM_AMMOBOX] = MBFinish(&b);
    MBBox(&b, (Vector3){ 0, 0.3f, 0 }, (Vector3){ 0.12f, 0.5f, 0.42f }, I, full, 128, 128, 0, true, ALLF);
    MBBox(&b, (Vector3){ 0, 0.58f, 0.12f }, (Vector3){ 0.1f, 0.1f, 0.1f }, I, full, 128, 128, 0, true, ALLF);
    MBBox(&b, (Vector3){ 0, 0.58f, -0.12f }, (Vector3){ 0.1f, 0.1f, 0.1f }, I, full, 128, 128, 0, true, ALLF);
    pickMesh[PM_VEST] = MBFinish(&b);
    Rectangle dk[6]; for (int f = 0; f < 6; f++) dk[f] = (Rectangle){ 0, 0, 64, 64 };
    MBBox(&b, (Vector3){ 0, 0, 0 }, (Vector3){ 0.025f, 0.3f, 0.3f }, I, dk, 64, 64, 0, true, ALLF);
    pickMesh[PM_DISK] = MBFinish(&b);
    /* door panel: 2 wide (Z), 3 tall, 0.22 thick (X); door texture on both big faces */
    Rectangle dr[6];
    dr[0] = dr[1] = (Rectangle){ 0, 0, 256, 384 };
    dr[2] = dr[3] = dr[4] = dr[5] = (Rectangle){ 0, 0, 16, 384 };
    MBBox(&b, (Vector3){ 0, 1.5f, 0 }, (Vector3){ 0.22f, 3.0f, 2.0f }, I, dr, 256, 384, 0, false, ALLF);
    pickMesh[PM_DOOR] = MBFinish(&b);
    /* padlock: body + shackle */
    MBBox(&b, (Vector3){ 0, 0, 0 }, (Vector3){ 0.12f, 0.26f, 0.3f }, I, NULL, 0, 0, 0.2f, true, ALLF);
    MBBox(&b, (Vector3){ 0, 0.2f, 0.1f }, (Vector3){ 0.05f, 0.16f, 0.05f }, I, NULL, 0, 0, 0.2f, true, ALLF);
    MBBox(&b, (Vector3){ 0, 0.2f, -0.1f }, (Vector3){ 0.05f, 0.16f, 0.05f }, I, NULL, 0, 0, 0.2f, true, ALLF);
    MBBox(&b, (Vector3){ 0, 0.29f, 0 }, (Vector3){ 0.05f, 0.05f, 0.25f }, I, NULL, 0, 0, 0.2f, true, ALLF);
    pickMesh[PM_PADLOCK] = MBFinish(&b);
    /* ceiling lamp housing (panel face drawn separately) */
    MBBox(&b, (Vector3){ 0, 0, 0 }, (Vector3){ 1.1f, 0.08f, 0.5f }, I, NULL, 0, 0, 0.5f, true, ALLF & ~(1u << 5));
    pickMesh[PM_LAMP] = MBFinish(&b);
}

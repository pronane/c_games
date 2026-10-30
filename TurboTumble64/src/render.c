/* render.c : procedural textures, fog shader, low-res N64 render targets,
 * world drawing, particles, HUD and minimap */
#include "common.h"

static const char *FOG_VS =
    "#version 330\n"
    "in vec3 vertexPosition;\n"
    "in vec2 vertexTexCoord;\n"
    "in vec4 vertexColor;\n"
    "uniform mat4 mvp;\n"
    "uniform vec2 uvOffset;\n"
    "out vec2 fragTexCoord;\n"
    "out vec4 fragColor;\n"
    "out float fogDepth;\n"
    "void main() {\n"
    "    fragTexCoord = vertexTexCoord + uvOffset;\n"
    "    fragColor = vertexColor;\n"
    "    gl_Position = mvp*vec4(vertexPosition, 1.0);\n"
    "    fogDepth = gl_Position.w;\n"
    "}\n";

static const char *FOG_FS =
    "#version 330\n"
    "in vec2 fragTexCoord;\n"
    "in vec4 fragColor;\n"
    "in float fogDepth;\n"
    "uniform sampler2D texture0;\n"
    "uniform vec4 colDiffuse;\n"
    "uniform vec3 fogColor;\n"
    "uniform float fogDensity;\n"
    "uniform float fogStart;\n"
    "uniform float hueShift;\n"
    "out vec4 finalColor;\n"
    "void main() {\n"
    "    vec4 vc = fragColor;\n"
    "    if (hueShift != 0.0) {\n"
    "        const vec3 k = vec3(0.57735);\n"
    "        float ca = cos(hueShift);\n"
    "        vc.rgb = clamp(vc.rgb*ca + cross(k, vc.rgb)*sin(hueShift) + k*dot(k, vc.rgb)*(1.0 - ca), 0.0, 1.0);\n"
    "    }\n"
    "    vec4 c = texture(texture0, fragTexCoord)*colDiffuse*vc;\n"
    "    if (c.a < 0.02) discard;\n"
    "    float lum = dot(c.rgb, vec3(0.299, 0.587, 0.114));\n"
    "    c.rgb = clamp(mix(vec3(lum), c.rgb, 1.16)*1.03, 0.0, 1.0);\n"
    "    float d = max(fogDepth - fogStart, 0.0)*fogDensity;\n"
    "    float f = clamp(1.0 - exp(-d*d), 0.0, 1.0);\n"
    "    finalColor = vec4(mix(c.rgb, fogColor, f), c.a);\n"
    "}\n";

static Texture2D MakeTex(Image img, bool mip)
{
    Texture2D t = LoadTextureFromImage(img);
    if (mip) {
        GenTextureMipmaps(&t);
        SetTextureFilter(t, TEXTURE_FILTER_TRILINEAR);
    } else {
        SetTextureFilter(t, TEXTURE_FILTER_BILINEAR);
    }
    SetTextureWrap(t, TEXTURE_WRAP_REPEAT);
    UnloadImage(img);
    return t;
}

bool RenderDirect(void) { return G.settings.visualMode == 1; }

/* ORIGINAL: trilinear (N64-style soft bilinear, mipmapped so nothing shimmers)
   ENHANCED: trilinear + 8x anisotropic for crisp roads at grazing angles */
void RenderApplyTextureFilters(void)
{
    Texture2D *ts[2 + NUM_TRACKS + NUM_TX];
    int n = 0;
    for (int i = 0; i < NUM_TX; i++) if (i != TX_ITEMBOX && i != TX_CLOUD) ts[n++] = &G.tx[i];
    for (int i = 0; i < NUM_TRACKS; i++) ts[n++] = &G.texGround[i];
    for (int i = 0; i < n; i++) {
        if (!ts[i]->id) continue;
        SetTextureFilter(*ts[i], TEXTURE_FILTER_TRILINEAR);
        rlTextureParameters(ts[i]->id, RL_TEXTURE_FILTER_ANISOTROPIC, G.settings.visualMode == 1 ? 8 : 4);
    }
}

static unsigned int rs = 99;
static int RI(int n) { rs = rs*1103515245u + 12345u; return (int)((rs >> 16) % (unsigned)n); }

static Image NoiseImage(int w, int h, Color base, int amp, int seed)
{
    rs = (unsigned)seed;
    Image img = GenImageColor(w, h, base);
    Color *px = (Color *)img.data;
    /* value noise: coarse + fine */
    int cs = 8;
    int gw = w/cs + 1, gh = h/cs + 1;
    float *grid = (float *)malloc(sizeof(float)*gw*gh);
    for (int i = 0; i < gw*gh; i++) grid[i] = (float)RI(1000)/1000.0f;
    for (int y = 0; y < h; y++) for (int x = 0; x < w; x++) {
        int gx = x/cs, gy = y/cs;
        float fx = (float)(x % cs)/cs, fy = (float)(y % cs)/cs;
        int gx1 = (gx + 1) % (w/cs), gy1 = (gy + 1) % (h/cs);
        float a = grid[gy*gw + gx], b = grid[gy*gw + gx1], c = grid[gy1*gw + gx], d = grid[gy1*gw + gx1];
        float v = (a*(1 - fx) + b*fx)*(1 - fy) + (c*(1 - fx) + d*fx)*fy;
        float n = (v - 0.5f)*amp + (RI(1000)/1000.0f - 0.5f)*amp*0.6f;
        Color o = base;
        int r = o.r + (int)n, g = o.g + (int)n, bb = o.b + (int)n;
        o.r = (unsigned char)Clamp((float)r, 0, 255); o.g = (unsigned char)Clamp((float)g, 0, 255); o.b = (unsigned char)Clamp((float)bb, 0, 255);
        px[y*w + x] = o;
    }
    free(grid);
    return img;
}

static void MakeTextures(void)
{
    G.texWhite = MakeTex(GenImageColor(4, 4, WHITE), false);

    TexturesInit();
    for (int i = 0; i < 0; i++) {
        const TrackDef *d = &TRACK_DEFS[i];
        Image g = NoiseImage(64, 64, d->ground, d->scenery == SCENERY_SNOW ? 16 : 40, 100 + i);
        rs = 555u + (unsigned)i;
        if (d->scenery == SCENERY_MEADOW) {
            for (int k = 0; k < 220; k++) { int x = RI(64), y = RI(64); ImageDrawPixel(&g, x, y, (Color){ 50, 120, 40, 255 }); ImageDrawPixel(&g, x, (y + 1) % 64, (Color){ 60, 135, 45, 255 }); }
            for (int k = 0; k < 40; k++) ImageDrawPixel(&g, RI(64), RI(64), (Color){ 150, 210, 90, 255 });
        } else if (d->scenery == SCENERY_DESERT) {
            Color *px = (Color *)g.data;
            for (int y = 0; y < 64; y++) for (int x = 0; x < 64; x++) {
                float rip = sinf((x + y*0.4f)*0.6f)*10.0f;
                px[y*64 + x] = ColorScale(px[y*64 + x], 1.0f + rip/255.0f);
            }
            for (int k = 0; k < 60; k++) ImageDrawPixel(&g, RI(64), RI(64), (Color){ 170, 120, 70, 255 });
        } else if (d->scenery == SCENERY_BEACH) {
            for (int k = 0; k < 90; k++) ImageDrawPixel(&g, RI(64), RI(64), (Color){ 255, 245, 210, 255 });
            for (int k = 0; k < 40; k++) ImageDrawPixel(&g, RI(64), RI(64), (Color){ 210, 185, 130, 255 });
        } else if (d->scenery == SCENERY_SPOOKY) {
            for (int k = 0; k < 160; k++) { int x = RI(64), y = RI(64); ImageDrawPixel(&g, x, y, (Color){ 50, 60, 45, 255 }); }
            for (int k = 0; k < 30; k++) ImageDrawPixel(&g, RI(64), RI(64), (Color){ 110, 90, 120, 255 });
        } else if (d->scenery == SCENERY_SNOW) {
            for (int k = 0; k < 120; k++) ImageDrawPixel(&g, RI(64), RI(64), (Color){ 200, 215, 240, 255 });
            for (int k = 0; k < 30; k++) ImageDrawPixel(&g, RI(64), RI(64), WHITE);
        } else {
            for (int k = 0; k < 50; k++) ImageDrawPixel(&g, RI(64), RI(64), (Color){ 255, 220, 255, 255 });
        }
        G.texGround[i] = MakeTex(g, true);
    }

    Image q = GenImageColor(32, 32, BLANK);
    for (int ox = -2; ox <= 2; ox++) for (int oy = -2; oy <= 2; oy++)
        ImageDrawText(&q, "?", 9 + ox, 2 + oy, 30, (Color){ 20, 20, 60, 255 });
    ImageDrawText(&q, "?", 9, 2, 30, WHITE);
    G.texQuestion = MakeTex(q, false);

    /* soft round particle */
    Image dot = GenImageColor(32, 32, BLANK);
    for (int y = 0; y < 32; y++) for (int x = 0; x < 32; x++) {
        float dx = (x - 15.5f)/15.5f, dy = (y - 15.5f)/15.5f;
        float d = sqrtf(dx*dx + dy*dy);
        float a = Clamp(1.2f - d*1.2f, 0, 1);
        a = a*a*(3 - 2*a);
        ImageDrawPixel(&dot, x, y, (Color){ 255, 255, 255, (unsigned char)(a*255) });
    }
    G.texDot = MakeTex(dot, false);
    SetTextureWrap(G.texDot, TEXTURE_WRAP_CLAMP);
    RenderApplyTextureFilters();
}

void RenderInit(void)
{
    G.fogShader = LoadShaderFromMemory(FOG_VS, FOG_FS);
    if (G.fogShader.id == 0 || G.fogShader.id == rlGetShaderIdDefault()) TraceLog(LOG_WARNING, "Fog shader failed, using default");
    G.locFogColor = GetShaderLocation(G.fogShader, "fogColor");
    G.locFogDensity = GetShaderLocation(G.fogShader, "fogDensity");
    G.locFogStart = GetShaderLocation(G.fogShader, "fogStart");
    G.locUvOffset = GetShaderLocation(G.fogShader, "uvOffset");
    G.locHueShift = GetShaderLocation(G.fogShader, "hueShift");
    G.sunDir = Vector3Normalize((Vector3){ -0.45f, 0.8f, -0.35f });
    G.ambient = 0.62f;
    MakeTextures();
    rlSetClipPlanes(0.4, 1400.0);
    G.preview = LoadRenderTexture(420, 420);
    SetTextureFilter(G.preview.texture, TEXTURE_FILTER_POINT);
    RenderResize();
}

void RenderResize(void)
{
    int W = GetScreenWidth(), H = GetScreenHeight();
    W = W < 64 ? 64 : W;
    H = H < 64 ? 64 : H;
    int views = (R.numHumans == 2) ? 2 : 1;
    int vh = H/views;
    /* ORIGINAL: N64 hi-res 640x480 internal render with a soft bilinear upscale (default),
       or RETRO ~320x240 with an integer point upscale for purists.
       ENHANCED: rendered straight to the (4x MSAA) back buffer at native res. */
    bool retro = G.settings.pixelMode == 1;
    int w, h, scale;
    if (retro || G.settings.visualMode == 1) {
        int target = views == 2 ? 180 : 240;
        scale = vh/target;
        if (G.settings.visualMode == 1) scale = 1;
        if (scale < 1) scale = 1;
        w = W/scale; h = vh/scale;
    } else {
        int target = views == 2 ? 360 : 480;
        h = vh < target ? vh : target;
        w = (int)((float)W*h/vh + 0.5f);
        scale = 0;      /* 0 = stretch to the view with bilinear filtering */
    }
    if (w == G.viewW && h == G.viewH && scale == G.viewScale && G.view[0].id) return;
    for (int i = 0; i < MAX_HUMANS; i++) if (G.view[i].id) UnloadRenderTexture(G.view[i]);
    for (int i = 0; i < MAX_HUMANS; i++) {
        G.view[i] = LoadRenderTexture(w, h);
        SetTextureFilter(G.view[i].texture, scale == 0 ? TEXTURE_FILTER_BILINEAR : TEXTURE_FILTER_POINT);
    }
    G.viewW = w; G.viewH = h; G.viewScale = scale;
}

void BeginWorld(Camera3D cam, float fov)
{
    cam.fovy = fov;
    BeginMode3D(cam);
    rlDisableBackfaceCulling();
}

void EndWorld(void)
{
    rlDrawRenderBatchActive();
    rlEnableBackfaceCulling();
    EndMode3D();
}

static void SetFog(void)
{
    const TrackDef *d = T.def;
    float fc[3] = { d->fog.r/255.0f, d->fog.g/255.0f, d->fog.b/255.0f };
    /* clear, MK64-like air: light distance haze only */
    float dens = d->fogDensity*0.55f, start = 70.0f;
    if (G.settings.visualMode == 1) { dens = d->fogDensity*0.4f; start = 90.0f; }
    SetShaderValue(G.fogShader, G.locFogColor, fc, SHADER_UNIFORM_VEC3);
    SetShaderValue(G.fogShader, G.locFogDensity, &dens, SHADER_UNIFORM_FLOAT);
    SetShaderValue(G.fogShader, G.locFogStart, &start, SHADER_UNIFORM_FLOAT);
}

static float gViewAspect = 0;
void DrawSkyAndTrack(Camera3D cam)
{
    rlDisableDepthMask();
    rlDisableDepthTest();
    DrawModel(T.mSky, cam.position, 1.0f, WHITE);
    rlDrawRenderBatchActive();
    if (G.settings.visualMode == 1 && T.def->scenery != SCENERY_STADIUM) {
        /* ENHANCED: soft additive glow around the sun (day) or the moon (night) */
        const TrackDef *d = T.def;
        Vector3 dir = d->night ? Vector3Normalize((Vector3){ -300, 330, -330 }) : Vector3Normalize((Vector3){ -0.55f, 0.32f, -0.77f });
        Vector3 c = Vector3Add(cam.position, Vector3Scale(dir, 560.0f));
        Vector3 f = Vector3Normalize(Vector3Subtract(c, cam.position));
        Vector3 r = Vector3Normalize(Vector3CrossProduct(f, (Vector3){ 0, 1, 0 }));
        Vector3 u = Vector3CrossProduct(r, f);
        BeginBlendMode(BLEND_ADDITIVE);
        rlSetTexture(G.texDot.id);
        rlBegin(RL_QUADS);
        for (int L = 0; L < 3; L++) {
            float sz = L == 0 ? 230.0f : L == 1 ? 95.0f : 34.0f;
            Color gc = d->night ? (L == 0 ? (Color){ 60, 55, 90, 255 } : L == 1 ? (Color){ 120, 115, 140, 255 } : (Color){ 0, 0, 0, 255 })
                                : (L == 0 ? (Color){ 90, 75, 45, 255 } : L == 1 ? (Color){ 170, 150, 100, 255 } : (Color){ 255, 250, 225, 255 });
            if (gc.r == 0) continue;
            rlColor4ub(gc.r, gc.g, gc.b, 255);
            Vector3 rr = Vector3Scale(r, sz), uu = Vector3Scale(u, sz);
            Vector3 p0 = Vector3Subtract(Vector3Subtract(c, rr), uu), p1 = Vector3Subtract(Vector3Add(c, rr), uu);
            Vector3 p2 = Vector3Add(Vector3Add(c, rr), uu), p3 = Vector3Add(Vector3Subtract(c, rr), uu);
            rlTexCoord2f(0, 1); rlVertex3f(p0.x, p0.y, p0.z);
            rlTexCoord2f(1, 1); rlVertex3f(p1.x, p1.y, p1.z);
            rlTexCoord2f(1, 0); rlVertex3f(p2.x, p2.y, p2.z);
            rlTexCoord2f(0, 0); rlVertex3f(p3.x, p3.y, p3.z);
        }
        rlEnd();
        rlSetTexture(0);
        rlDrawRenderBatchActive();
        EndBlendMode();
    }
    /* soft clouds + painted panorama (mountains, sea, castles, nebula) */
    DrawModel(T.mClouds, cam.position, 1.0f, WHITE);
    DrawModel(T.mPano, (Vector3){ cam.position.x, cam.position.y, cam.position.z }, 1.0f, WHITE);
    rlDrawRenderBatchActive();
    rlEnableDepthTest();
    rlEnableDepthMask();
    Vector3 o = { 0, 0, 0 };
    DrawModel(T.mGround, o, 1.0f, WHITE);
    if (T.def->rainbowRoad) {   /* colour-cycling rainbow tiles */
        float hs = fmodf(G.time*1.4f, 2*PI) + 0.001f;
        SetShaderValue(G.fogShader, G.locHueShift, &hs, SHADER_UNIFORM_FLOAT);
        DrawModel(T.mRoad, o, 1.0f, WHITE);
        DrawModel(T.mCurb, o, 1.0f, WHITE);
        DrawModel(T.mWalls, o, 1.0f, WHITE);
        rlDrawRenderBatchActive();
        hs = 0;
        SetShaderValue(G.fogShader, G.locHueShift, &hs, SHADER_UNIFORM_FLOAT);
    } else {
        DrawModel(T.mRoad, o, 1.0f, WHITE);
        DrawModel(T.mCurb, o, 1.0f, WHITE);
        DrawModel(T.mWalls, o, 1.0f, WHITE);
    }
    if (T.hasDeco) for (int k = 0; k < 5; k++) DrawModel(T.mDeco[k], o, 1.0f, WHITE);
    float aspect = gViewAspect > 0 ? gViewAspect : 4.0f/3.0f;
    DrawSceneryChunks(cam, aspect);
}

/* water last among the opaque world so it blends over the sea / lake beds */
void DrawWater(void)
{
    if (!T.hasWater) return;
    rlDrawRenderBatchActive();
    float off[2] = { fmodf(G.time*0.035f, 1.0f), fmodf(G.time*0.021f, 1.0f) };
    SetShaderValue(G.fogShader, G.locUvOffset, off, SHADER_UNIFORM_VEC2);
    rlDisableDepthMask();
    DrawModel(T.mWater, (Vector3){ 0, T.tideOffset, 0 }, 1.0f, WHITE);
    /* second, slower layer at a different scale for shimmering waves */
    float off2[2] = { -fmodf(G.time*0.02f, 1.0f) + 0.37f, fmodf(G.time*0.03f, 1.0f) + 0.11f };
    rlDrawRenderBatchActive();
    SetShaderValue(G.fogShader, G.locUvOffset, off2, SHADER_UNIFORM_VEC2);
    DrawModel(T.mWater, (Vector3){ 0, 0.02f + T.tideOffset, 0 }, 1.0f, (Color){ 255, 255, 255, 110 });
    rlDrawRenderBatchActive();
    rlEnableDepthMask();
    off[0] = off[1] = 0;
    SetShaderValue(G.fogShader, G.locUvOffset, off, SHADER_UNIFORM_VEC2);
}

/* ------------------------------------------------------------------ */
/* particles                                                            */
/* ------------------------------------------------------------------ */
void ParticleSpawn(Vector3 p, Vector3 v, Color c, float life, float size, float grav)
{
    ParticleSpawnEx(p, v, c, life, size, grav, false);
}

void ParticleSpawnEx(Vector3 p, Vector3 v, Color c, float life, float size, float grav, bool additive)
{
    if (R.numParts >= MAX_PARTICLES) return;
    Particle *q = &R.parts[R.numParts++];
    q->p = p; q->v = v; q->c = c; q->life = q->maxLife = life; q->size = size*1.25f; q->grav = grav; q->additive = additive;
    if (G.settings.visualMode == 1 && R.numParts < MAX_PARTICLES) {   /* ENHANCED: extra particles */
        Particle *e = &R.parts[R.numParts++];
        *e = *q;
        e->v = (Vector3){ v.x*0.7f + RandF(-1, 1), v.y*0.8f, v.z*0.7f + RandF(-1, 1) };
        e->size = q->size*0.6f; e->life = e->maxLife = life*0.8f;
    }
}

void ParticlesUpdate(float dt)
{
    for (int i = 0; i < R.numParts; ) {
        Particle *q = &R.parts[i];
        q->life -= dt;
        if (q->life <= 0) { R.parts[i] = R.parts[--R.numParts]; continue; }
        q->v.y -= q->grav*dt;
        q->p = Vector3Add(q->p, Vector3Scale(q->v, dt));
        i++;
    }
}

void ParticlesDraw(Camera3D cam)
{
    Vector3 f = Vector3Normalize(Vector3Subtract(cam.target, cam.position));
    Vector3 r = Vector3Normalize(Vector3CrossProduct(f, (Vector3){ 0, 1, 0 }));
    Vector3 u = Vector3CrossProduct(r, f);
    bool enh = G.settings.visualMode == 1;
    rlDrawRenderBatchActive();
    rlDisableDepthMask();
    for (int pass = 0; pass < 2; pass++) {
        if (pass == 1) BeginBlendMode(BLEND_ADDITIVE);
        rlSetTexture(G.texDot.id);
        rlBegin(RL_QUADS);
        for (int i = 0; i < R.numParts; i++) {
            Particle *q = &R.parts[i];
            if ((int)q->additive != pass) continue;
            float lf = q->life/q->maxLife;
            float s = q->size*(0.5f + 0.5f*lf);
            Color c = q->c;
            c.a = (unsigned char)(c.a*Clamp(lf*2.0f, 0, 1));
            if (pass == 1) {
                /* glow: premultiply by alpha so additive sparks fade out cleanly */
                float a = c.a/255.0f;
                c = (Color){ (unsigned char)(c.r*a), (unsigned char)(c.g*a), (unsigned char)(c.b*a), 255 };
                if (enh) s *= 1.15f;
            }
            rlColor4ub(c.r, c.g, c.b, c.a);
            Vector3 rr = Vector3Scale(r, s), uu = Vector3Scale(u, s);
            if (pass == 1 && Vector3LengthSqr(q->v) > 4.0f) {
                /* sparks stretch along their motion (streaks) */
                Vector3 vd = Vector3Normalize(q->v);
                Vector3 sv = Vector3Subtract(vd, Vector3Scale(f, Vector3DotProduct(vd, f)));
                float sl = Vector3Length(sv);
                if (sl > 0.2f) {
                    sv = Vector3Scale(sv, 1.0f/sl);
                    Vector3 pv = Vector3CrossProduct(sv, f);
                    uu = Vector3Scale(sv, s*2.2f); rr = Vector3Scale(pv, s*0.7f);
                }
            }
            Vector3 a = Vector3Subtract(Vector3Subtract(q->p, rr), uu);
            Vector3 b = Vector3Subtract(Vector3Add(q->p, rr), uu);
            Vector3 c2 = Vector3Add(Vector3Add(q->p, rr), uu);
            Vector3 d = Vector3Add(Vector3Subtract(q->p, rr), uu);
            rlTexCoord2f(0, 1); rlVertex3f(a.x, a.y, a.z);
            rlTexCoord2f(1, 1); rlVertex3f(b.x, b.y, b.z);
            rlTexCoord2f(1, 0); rlVertex3f(c2.x, c2.y, c2.z);
            rlTexCoord2f(0, 0); rlVertex3f(d.x, d.y, d.z);
        }
        rlEnd();
        rlSetTexture(0);
        rlDrawRenderBatchActive();
        if (pass == 1) EndBlendMode();
    }
    rlEnableDepthMask();
}

/* soft blob shadow: an ellipse along the kart, two-ring falloff (ENHANCED: smoother) */
static void DrawShadow(const Kart *k)
{
    float h = k->pos.y - k->groundY;
    float a = Clamp(1.0f - h*0.18f, 0.25f, 1.0f);
    float sc = k->scale*(1.0f + Clamp(h*0.08f, 0, 0.4f));
    bool enh = G.settings.visualMode == 1;
    int segs = enh ? 28 : 12;
    float yaw = k->heading + k->visYaw;
    float cs = cosf(yaw), sn = sinf(yaw);
    float rx = 1.05f*sc, rz = 1.6f*sc;
    float y = k->groundY + 0.06f;
    unsigned char a0 = (unsigned char)((enh ? 125 : 115)*a), a1 = (unsigned char)((enh ? 70 : 60)*a);
    rlBegin(RL_TRIANGLES);
    for (int i = 0; i < segs; i++) {
        float t0 = 2*PI*i/segs, t1 = 2*PI*(i + 1)/segs;
        float ix0 = cosf(t0)*rx*0.55f, iz0 = sinf(t0)*rz*0.55f, ix1 = cosf(t1)*rx*0.55f, iz1 = sinf(t1)*rz*0.55f;
        float ox0 = cosf(t0)*rx, oz0 = sinf(t0)*rz, ox1 = cosf(t1)*rx, oz1 = sinf(t1)*rz;
        #define SP(lx, lz) k->pos.x + (lx)*cs + (lz)*sn, y, k->pos.z - (lx)*sn + (lz)*cs
        rlColor4ub(0, 0, 0, a0); rlVertex3f(SP(0, 0));
        rlColor4ub(0, 0, 0, a1); rlVertex3f(SP(ix1, iz1)); rlVertex3f(SP(ix0, iz0));
        rlColor4ub(0, 0, 0, a1); rlVertex3f(SP(ix0, iz0)); rlVertex3f(SP(ix1, iz1));
        rlColor4ub(0, 0, 0, 0); rlVertex3f(SP(ox1, oz1));
        rlColor4ub(0, 0, 0, a1); rlVertex3f(SP(ix0, iz0));
        rlColor4ub(0, 0, 0, 0); rlVertex3f(SP(ox1, oz1)); rlVertex3f(SP(ox0, oz0));
        #undef SP
    }
    rlEnd();
}

#define CLIP_NEAR 0.4
#define CLIP_FAR  1400.0
static int dvx, dvy, dvw, dvh;
static void BeginDirectView(Camera3D cam, Rectangle dst)
{
    rlDrawRenderBatchActive();
    float sx = (float)GetRenderWidth()/GetScreenWidth(), sy = (float)GetRenderHeight()/GetScreenHeight();
    dvx = (int)(dst.x*sx); dvw = (int)(dst.width*sx); dvh = (int)(dst.height*sy);
    dvy = GetRenderHeight() - (int)((dst.y + dst.height)*sy);
    rlEnableScissorTest();
    rlScissor(dvx, dvy, dvw, dvh);
    rlViewport(dvx, dvy, dvw, dvh);
    Color f = T.def->fog;
    rlClearColor(f.r, f.g, f.b, 255);
    rlClearScreenBuffers();
    rlMatrixMode(RL_PROJECTION);
    rlPushMatrix();
    rlLoadIdentity();
    double aspect = (double)dvw/(dvh > 0 ? dvh : 1);
    double top = CLIP_NEAR*tan(cam.fovy*0.5*DEG2RAD), right = top*aspect;
    rlFrustum(-right, right, -top, top, CLIP_NEAR, CLIP_FAR);
    rlMatrixMode(RL_MODELVIEW);
    rlLoadIdentity();
    Matrix mv = MatrixLookAt(cam.position, cam.target, cam.up);
    rlMultMatrixf(MatrixToFloat(mv));
    rlEnableDepthTest();
    rlDisableBackfaceCulling();
}
static void EndDirectView(void)
{
    rlDrawRenderBatchActive();
    rlEnableBackfaceCulling();
    rlMatrixMode(RL_PROJECTION);
    rlPopMatrix();
    rlMatrixMode(RL_MODELVIEW);
    rlLoadIdentity();
    rlDisableDepthTest();
    rlDisableScissorTest();
    rlViewport(0, 0, GetRenderWidth(), GetRenderHeight());
}

void RenderWorldView(int view, Camera3D cam, int focusKart, Rectangle dst)
{
    (void)focusKart;
    bool direct = RenderDirect();
    gViewAspect = dst.height > 0 ? dst.width/dst.height : 4.0f/3.0f;
    G.curCam = cam;
    G.kartSprites = !direct;
    SetFog();
    if (direct) BeginDirectView(cam, dst);
    else {
        BeginTextureMode(G.view[view]);
        ClearBackground(T.def->fog);
        BeginWorld(cam, cam.fovy);
    }
    DrawSkyAndTrack(cam);
    StadiumDrawExtras(cam);
    BeginShaderMode(G.fogShader);
    /* blob shadows */
    rlDrawRenderBatchActive();
    rlDisableDepthMask();
    for (int i = 0; i < R.numKarts; i++) DrawShadow(&R.karts[i]);
    if (R.timeTrial && G.ghostValid) {
        Kart *pk = &R.karts[0];
        Vector3 gp; float gyaw;
        if (GhostPose(R.time - pk->lapStartTime, &gp, &gyaw)) {
            Kart gk = *pk; gk.pos = gp; gk.heading = gyaw; gk.visYaw = 0; gk.groundY = gp.y;
            DrawShadow(&gk);
        }
    }
    rlDrawRenderBatchActive();
    rlEnableDepthMask();
    /* karts */
    for (int i = 0; i < R.numKarts; i++) {
        Kart *k = &R.karts[i];
        if (k->invulnTimer > 0 && k->discoTimer <= 0 && k->spinTimer <= 0 && ((int)(G.time*20) & 1)) continue; /* blink */
        DrawCharacterKart(k->charId, k, G.time + i*1.7f);
        if (k->discoTimer > 0) {
            rlDrawRenderBatchActive();
            rlDisableDepthMask();
            Color c = HueColor(G.time*400.0f, 0.6f, 1.0f); c.a = 90;
            DrawSphereEx(Vector3Add(k->pos, (Vector3){ 0, 1.0f*k->scale, 0 }), 2.0f*k->scale, 6, 8, c);
            rlDrawRenderBatchActive();
            rlEnableDepthMask();
        }
    }
    /* time-trial ghost: translucent replay of the best lap */
    if (R.timeTrial && G.ghostValid && R.phase == RACE_RUNNING) {
        Kart *pk = &R.karts[0];
        Vector3 gp; float gyaw;
        if (GhostPose(R.time - pk->lapStartTime, &gp, &gyaw)) {
            Kart gk; memset(&gk, 0, sizeof gk);
            gk.pos = gp; gk.heading = gyaw; gk.scale = 1; gk.wheelRot = R.time*30.0f; gk.charId = G.ghost.charId;
            float d = Vector3Distance(gp, pk->pos);
            unsigned char al = (unsigned char)(Clamp((d - 1.5f)/4.0f, 0, 1)*150);
            if (al > 8) {
                /* depth pre-pass so only the nearest ghost surface shows, then a glowing additive pass */
                rlDrawRenderBatchActive();
                rlColorMask(false, false, false, false);
                DrawCharacterKartTint(G.ghost.charId, &gk, G.time, (Color){ 255, 255, 255, 254 });
                rlDrawRenderBatchActive();
                rlColorMask(true, true, true, true);
                rlDisableDepthMask();
                BeginBlendMode(BLEND_ADDITIVE);
                DrawCharacterKartTint(G.ghost.charId, &gk, G.time, (Color){ 150, 210, 255, al });
                EndBlendMode();
                rlDrawRenderBatchActive();
                rlEnableDepthMask();
            }
        }
    }
    G.kartSprites = false;
    DrawWater();
    DrawItemsWorld(cam);
    HazardsDraw();
    ParticlesDraw(cam);
    EndShaderMode();
    if (direct) EndDirectView();
    else { EndWorld(); EndTextureMode(); }
}

/* ------------------------------------------------------------------ */
/* HUD                                                                  */
/* ------------------------------------------------------------------ */
static Vector2 MapXform(Vector2 p, Rectangle area, Vector2 mn, Vector2 mx)
{
    float sx = area.width/(mx.x - mn.x), sy = area.height/(mx.y - mn.y);
    float s = fminf(sx, sy);
    float ox = area.x + (area.width - (mx.x - mn.x)*s)*0.5f;
    float oy = area.y + (area.height - (mx.y - mn.y)*s)*0.5f;
    /* x is mirrored so the map matches the camera's left/right */
    return (Vector2){ ox + (mx.x - p.x)*s, oy + (mx.y - p.y)*s };
}

void DrawMinimap(Rectangle area)
{
    Vector2 mn = { T.mapMin.x - 10, T.mapMin.y - 10 }, mx = { T.mapMax.x + 10, T.mapMax.y + 10 };
    for (int pass = 0; pass < 2; pass++) {
        for (int i = 0; i < T.n; i += 3) {
            int j = TrackWrap(&T, i + 3);
            Vector2 a = MapXform((Vector2){ T.s[i].pos.x, T.s[i].pos.z }, area, mn, mx);
            Vector2 b = MapXform((Vector2){ T.s[j].pos.x, T.s[j].pos.z }, area, mn, mx);
            DrawLineEx(a, b, pass == 0 ? 7.0f : 3.0f, pass == 0 ? (Color){ 0, 0, 0, 160 } : (Color){ 240, 240, 240, 230 });
        }
    }
    Vector2 st = MapXform((Vector2){ T.s[0].pos.x, T.s[0].pos.z }, area, mn, mx);
    DrawRectangle((int)st.x - 4, (int)st.y - 4, 8, 8, (Color){ 30, 30, 30, 255 });
    DrawRectangle((int)st.x - 2, (int)st.y - 2, 4, 4, WHITE);
    for (int b = 0; b < R.numBoxes; b += 4) {
        Vector2 p = MapXform((Vector2){ R.boxes[b].pos.x, R.boxes[b].pos.z }, area, mn, mx);
        DrawCircleV(p, 3, (Color){ 255, 220, 80, 200 });
    }
    for (int pass = 0; pass < 2; pass++) {
        for (int i = R.numKarts - 1; i >= 0; i--) {
            Kart *k = &R.karts[i];
            bool hum = k->human >= 0;
            if ((pass == 1) != hum) continue;
            Vector2 p = MapXform((Vector2){ k->pos.x, k->pos.z }, area, mn, mx);
            float r = hum ? 7.0f : 5.0f;
            DrawCircleV(p, r + 2, BLACK);
            DrawCircleV(p, r, CHARACTERS[k->charId].kart);
            if (hum) DrawText(TextFormat("%d", k->human + 1), (int)p.x - 3, (int)p.y - 5, 10, WHITE);
        }
    }
}

void DrawHUD(int view, Rectangle a)
{
    Kart *k = &R.karts[R.humanKart[view]];
    float u = a.height/720.0f;
    if (R.numHumans == 2) u = a.height/400.0f;
    if (u < 0.5f) u = 0.5f;
    int fs = (int)(30*u);

    /* lap counter */
    int lapShown = k->lap + 1; if (lapShown > NUM_LAPS) lapShown = NUM_LAPS;
    DrawTextOutlined("LAP", (int)(a.x + 24*u), (int)(a.y + 18*u), fs, (Color){ 255, 220, 60, 255 });
    DrawTextOutlined(TextFormat("%d/%d", lapShown, NUM_LAPS), (int)(a.x + 24*u + MeasureText("LAP ", fs)), (int)(a.y + 12*u), (int)(fs*1.3f), WHITE);

    /* timer */
    const char *tm = FormatTime(R.time);
    if (k->finished) tm = FormatTime(k->finishTime);
    int tw = MeasureText(tm, fs);
    DrawTextOutlined(tm, (int)(a.x + a.width - tw - 24*u), (int)(a.y + 18*u), fs, WHITE);
    if (R.timeTrial || k->lap > 0) {
        float ll = k->lastLapTime;
        if (ll > 0) {
            const char *lt = TextFormat("LAST %s", FormatTime(ll));
            int lw = MeasureText(lt, fs/2);
            DrawTextOutlined(lt, (int)(a.x + a.width - lw - 24*u), (int)(a.y + 18*u + fs + 4), fs/2, (Color){ 200, 230, 255, 255 });
        }
    }

    /* item slot with a slot-machine style roulette reel */
    float box = 84*u;
    float pop = k->itemFlash > 0 ? 1.0f + 0.25f*sinf(k->itemFlash/0.35f*PI) : 1.0f;
    float bs = box*pop;
    Rectangle ib = { a.x + a.width*0.5f - bs*0.5f, a.y + 12*u + (box - bs)*0.5f, bs, bs };
    DrawRectangleRounded(ib, 0.3f, 6, (Color){ 20, 20, 50, 190 });
    int cx = (int)(ib.x + bs*0.5f), cy = (int)(ib.y + bs*0.5f);
    if (k->roulette > 0) {
        float dur = k->rouletteDur > 0 ? k->rouletteDur : 1.4f;
        float p = Clamp(1.0f - k->roulette/dur, 0, 1);
        const float STEPS = 16.0f;
        float pos = STEPS*(1.0f - powf(1.0f - p, 2.4f));   /* fast spin that decelerates onto the prize */
        int i0 = (int)floorf(pos);
        float fr = pos - i0;
        int jf = (int)k->rouletteFinal - ITEM_PEEL;
        float cell = bs*0.9f;
        BeginScissorMode((int)ib.x + 3, (int)ib.y + 3, (int)ib.width - 6, (int)ib.height - 6);
        for (int d = -1; d <= 1; d++) {
            int idx = i0 + d;
            int j = ((jf + idx - (int)STEPS) % 7 + 7) % 7;
            float oy = (d - fr)*cell;     /* reel scrolls downwards */
            DrawItemIcon((ItemType)(ITEM_PEEL + j), cx, (int)(cy - oy), bs*0.78f);
        }
        EndScissorMode();
        /* motion-blur shading at the top/bottom of the window */
        DrawRectangleGradientV((int)ib.x + 3, (int)ib.y + 3, (int)ib.width - 6, (int)(bs*0.22f), (Color){ 20, 20, 50, 220 }, (Color){ 20, 20, 50, 0 });
        DrawRectangleGradientV((int)ib.x + 3, (int)(ib.y + bs*0.78f - 3), (int)ib.width - 6, (int)(bs*0.22f), (Color){ 20, 20, 50, 0 }, (Color){ 20, 20, 50, 220 });
    } else if (k->item != ITEM_NONE) {
        DrawItemIcon(k->item == ITEM_PEPPER3 && k->itemCount < 3 ? (k->itemCount == 1 ? ITEM_PEPPER : ITEM_PEPPER3) : k->item, cx, cy, bs*0.8f);
        if (k->item == ITEM_PEPPER3) DrawTextOutlined(TextFormat("x%d", k->itemCount), (int)(ib.x + bs - 18*u), (int)(ib.y + bs - 22*u), (int)(18*u), WHITE);
        const char *nm = ITEM_NAMES[k->item];
        DrawTextCentered(nm, cx, (int)(a.y + 12*u + box + 4*u), (int)(14*u), WHITE);
    }
    Color frame = k->roulette > 0 ? HueColor(G.time*600.0f, 0.5f, 1.0f) : (Color){ 255, 255, 255, 230 };
    if (k->itemFlash > 0) frame = (Color){ 255, 240, 120, 255 };
    DrawRectangleRoundedLinesEx(ib, 0.3f, 6, (k->roulette > 0 || k->itemFlash > 0 ? 4.0f : 3.0f)*u, frame);
    if (k->itemFlash > 0) {
        Color fl = { 255, 255, 255, (unsigned char)(160*k->itemFlash/0.35f) };
        DrawRectangleRounded(ib, 0.3f, 6, fl);
    }

    if (R.timeTrial && G.ghostValid && G.ghost.track == T.index) {
        const char *gt = TextFormat("GHOST %s", FormatTime(G.ghost.lapTime));
        DrawTextOutlined(gt, (int)(a.x + 24*u), (int)(a.y + 18*u + fs*1.4f + 6*u), (int)(fs*0.55f), (Color){ 170, 220, 255, 255 });
    }
    /* position */
    if (!R.timeTrial) {
        const char *pos = TextFormat("%d", k->place);
        const char *suf = OrdinalSuffix(k->place);
        Color pc = k->place == 1 ? (Color){ 255, 215, 40, 255 } : k->place == 2 ? (Color){ 210, 220, 235, 255 } :
                   k->place == 3 ? (Color){ 230, 150, 80, 255 } : (Color){ 120, 200, 255, 255 };
        int pfs = (int)(96*u);
        int px = (int)(a.x + 30*u), py = (int)(a.y + a.height - pfs - 30*u);
        DrawTextOutlined(pos, px, py, pfs, pc);
        DrawTextOutlined(suf, px + MeasureText(pos, pfs) + 4, py + pfs/6, pfs/2, pc);
    }
    /* speedometer */
    {
        float kmh = fabsf(k->speed)*3.6f*1.6f;
        const char *sp = TextFormat("%3d km/h", (int)kmh);
        int sw = MeasureText(sp, (int)(20*u));
        int sx = (int)(a.x + a.width - sw - 24*u), sy = (int)(a.y + a.height - 34*u);
        if (R.numHumans == 1) sx = (int)(a.x + a.width*0.5f - sw*0.5f);
        DrawTextOutlined(sp, sx, sy, (int)(20*u), (Color){ 220, 255, 220, 255 });
        if (k->driftState == 2) {
            Color sc = k->sparkLevel == 2 ? (Color){ 255, 150, 30, 255 } : k->sparkLevel == 1 ? (Color){ 60, 160, 255, 255 } : (Color){ 230, 230, 230, 255 };
            DrawRectangle(sx - 2, sy - (int)(12*u) - 2, sw + 4, (int)(6*u) + 4, (Color){ 0, 0, 0, 150 });
            DrawRectangle(sx, sy - (int)(12*u), (int)(sw*Clamp(k->driftCharge/1.9f, 0, 1)), (int)(6*u), sc);
        }
        if (k->turboFlash > 0 && k->human >= 0)
            DrawTextCentered(k->lastTurboLevel == 2 ? "SUPER TURBO!" : "TURBO!", (int)(a.x + a.width*0.5f), (int)(a.y + a.height*0.72f), (int)(26*u),
                             k->lastTurboLevel == 2 ? (Color){ 255, 170, 40, 255 } : (Color){ 110, 190, 255, 255 });
    }

    /* countdown */
    if (R.phase == RACE_COUNTDOWN || (R.phase == RACE_RUNNING && R.time < 1.0f)) {
        const char *txt; Color c;
        float frac;
        if (R.phase == RACE_COUNTDOWN) {
            int n = (int)ceilf(R.countdown);
            if (n < 1) n = 1;
            txt = TextFormat("%d", n);
            c = n == 3 ? (Color){ 255, 70, 70, 255 } : n == 2 ? (Color){ 255, 200, 50, 255 } : (Color){ 255, 255, 120, 255 };
            frac = R.countdown - floorf(R.countdown);
        } else { txt = "GO!"; c = (Color){ 80, 255, 120, 255 }; frac = 1.0f - R.time; }
        int sz = (int)(160*u*(0.8f + 0.4f*frac));
        DrawTextCentered(txt, (int)(a.x + a.width*0.5f), (int)(a.y + a.height*0.33f - sz*0.3f), sz, c);
        /* traffic light */
        if (R.phase == RACE_COUNTDOWN) {
            int n = (int)ceilf(R.countdown);
            float lx = a.x + a.width*0.5f, ly = a.y + a.height*0.16f;
            DrawRectangleRounded((Rectangle){ lx - 70*u, ly - 22*u, 140*u, 44*u }, 0.5f, 6, (Color){ 30, 30, 30, 220 });
            for (int i = 0; i < 3; i++) {
                bool on = (3 - i) >= n;
                Color lc = on ? (i == 2 ? GREEN : (i == 1 ? YELLOW : RED)) : (Color){ 70, 70, 70, 255 };
                DrawCircle((int)(lx - 42*u + i*42*u), (int)ly, 15*u, lc);
            }
        }
    }
    if (R.phase == RACE_INTRO) {
        DrawTextCentered(T.def->name, (int)(a.x + a.width*0.5f), (int)(a.y + a.height*0.62f), (int)(44*u), WHITE);
        DrawTextCentered(T.def->subtitle, (int)(a.x + a.width*0.5f), (int)(a.y + a.height*0.62f + 52*u), (int)(22*u), (Color){ 255, 230, 150, 255 });
    }

    /* banners */
    if (R.bannerTimer[view] > 0) {
        float t = R.bannerTimer[view];
        int sz = (int)(64*u);
        float slide = t > 1.8f ? (2.2f - t)/0.4f : 1.0f;
        int y = (int)(a.y + a.height*0.42f);
        int cx2 = (int)(a.x + a.width*(1.5f - slide));
        Color bc = strncmp(R.banner[view], "FINAL", 5) == 0 ? (Color){ 255, 80, 80, 255 } : (Color){ 255, 230, 60, 255 };
        DrawTextCentered(R.banner[view], cx2 - (int)(a.width*0.0f), y, sz, bc);
    }
    if (k->finished) {
        DrawTextCentered(TextFormat("%d%s PLACE!", k->place, OrdinalSuffix(k->place)), (int)(a.x + a.width*0.5f), (int)(a.y + a.height*0.55f), (int)(50*u), WHITE);
    }
    if (k->shrinkTimer > 0) DrawTextCentered("SHRUNK!", (int)(a.x + a.width*0.5f), (int)(a.y + a.height*0.75f), (int)(26*u), (Color){ 150, 220, 255, 255 });
}

/* ------------------------------------------------------------------ */
/* Mudslide Megadome extras: live jumbotron, flood-light glows,        */
/* twinkling camera flashes in the crowd, neon chase lights            */
/* ------------------------------------------------------------------ */
static bool gJumboPass = false;
static bool gJumboReady = false;

static unsigned int XHash(unsigned int a, unsigned int b)
{
    unsigned int h = a*2654435761u ^ (b + 0x9e3779b9u + (a << 6) + (a >> 2));
    h ^= h >> 15; h *= 2246822519u; h ^= h >> 13; h *= 3266489917u; h ^= h >> 16;
    return h;
}
static float XHashF(unsigned int a, unsigned int b) { return (XHash(a, b) & 0xFFFFFF)/16777216.0f; }

static void GlowQuad(Vector3 c, Vector3 r, Vector3 u, float sz, Color col)
{
    Vector3 rr = Vector3Scale(r, sz), uu = Vector3Scale(u, sz);
    Vector3 p0 = Vector3Subtract(Vector3Subtract(c, rr), uu), p1 = Vector3Subtract(Vector3Add(c, rr), uu);
    Vector3 p2 = Vector3Add(Vector3Add(c, rr), uu), p3 = Vector3Add(Vector3Subtract(c, rr), uu);
    rlColor4ub(col.r, col.g, col.b, 255);
    rlTexCoord2f(0, 1); rlVertex3f(p0.x, p0.y, p0.z);
    rlTexCoord2f(1, 1); rlVertex3f(p1.x, p1.y, p1.z);
    rlTexCoord2f(1, 0); rlVertex3f(p2.x, p2.y, p2.z);
    rlTexCoord2f(0, 0); rlVertex3f(p3.x, p3.y, p3.z);
}

void StadiumDrawExtras(Camera3D cam)
{
    const Track *tr = &T;
    if (!tr->def || tr->def->scenery != SCENERY_STADIUM) return;
    rlDrawRenderBatchActive();
    /* jumbotron screens (not inside the jumbotron's own render) */
    if (!gJumboPass) {
        for (int j = 0; j < tr->numJumbo; j++) {
            Vector3 c = tr->jumboC[j], r = tr->jumboRight[j], u = tr->jumboUp[j];
            Vector3 p0 = Vector3Subtract(Vector3Subtract(c, r), u), p1 = Vector3Subtract(Vector3Add(c, r), u);
            Vector3 p2 = Vector3Add(Vector3Add(c, r), u), p3 = Vector3Add(Vector3Subtract(c, r), u);
            if (gJumboReady) { rlSetTexture(G.jumboRT.texture.id); rlBegin(RL_QUADS); rlColor4ub(235, 235, 245, 255); }
            else { rlSetTexture(G.texWhite.id); rlBegin(RL_QUADS); rlColor4ub(20, 40, 110, 255); }
            /* render textures are stored bottom-up */
            rlTexCoord2f(0, 0); rlVertex3f(p0.x, p0.y, p0.z);
            rlTexCoord2f(1, 0); rlVertex3f(p1.x, p1.y, p1.z);
            rlTexCoord2f(1, 1); rlVertex3f(p2.x, p2.y, p2.z);
            rlTexCoord2f(0, 1); rlVertex3f(p3.x, p3.y, p3.z);
            rlEnd();
            rlSetTexture(0);
        }
        rlDrawRenderBatchActive();
    }
    Vector3 f = Vector3Normalize(Vector3Subtract(cam.target, cam.position));
    Vector3 r = Vector3Normalize(Vector3CrossProduct(f, (Vector3){ 0, 1, 0 }));
    Vector3 u = Vector3CrossProduct(r, f);
    rlDisableDepthMask();
    BeginBlendMode(BLEND_ADDITIVE);
    rlSetTexture(G.texDot.id);
    rlBegin(RL_QUADS);
    /* flood-light glows */
    for (int i = 0; i < tr->numLights; i++) {
        Vector3 c = tr->lights[i];
        float d = Vector3Distance(c, cam.position);
        float k = Clamp(d/120.0f, 0.6f, 2.2f);
        GlowQuad(c, r, u, 6.5f*k, (Color){ 70, 66, 52, 255 });
        GlowQuad(c, r, u, 2.4f*k, (Color){ 210, 205, 180, 255 });
    }
    /* camera flashes: a new random set every 90 ms, each fading inside its slot */
    unsigned int slot = (unsigned int)(G.time/0.09f);
    float ph = fmodf(G.time, 0.09f)/0.09f;
    if (tr->numFlashSpots > 0) for (int pass = 0; pass < 2; pass++) {
        unsigned int sl = slot - (unsigned)pass;
        float fade = pass == 0 ? 1.0f - 0.4f*ph : 0.6f*(1.0f - ph);
        for (int j = 0; j < 14; j++) {
            unsigned int h = XHash(sl, (unsigned)j);
            int q = (int)(h % (unsigned)tr->numFlashSpots);
            float a = XHashF(sl, j + 100u), b = XHashF(sl, j + 200u);
            Vector3 A = tr->flashA[q];
            Vector3 p = Vector3Add(A, Vector3Add(Vector3Scale(Vector3Subtract(tr->flashB[q], A), a), Vector3Scale(Vector3Subtract(tr->flashC[q], A), b)));
            unsigned char v = (unsigned char)(255*fade);
            GlowQuad(p, r, u, 1.5f + 0.6f*XHashF(sl, j + 300u), (Color){ v, v, (unsigned char)(v*0.95f), 255 });
        }
    }
    /* neon sign: chase lights around the frame + a pulsing arrow glow */
    if (tr->hasNeon) {
        Vector3 c = tr->neonC, nr = tr->neonRight, nu = tr->neonUp;
        int per = 40;
        for (int i = 0; i < per; i++) {
            float t = (float)i/per;
            Vector3 p;
            if (t < 0.3f) p = Vector3Add(Vector3Add(c, Vector3Scale(nr, -1 + 2*t/0.3f)), nu);
            else if (t < 0.5f) p = Vector3Add(Vector3Add(c, nr), Vector3Scale(nu, 1 - 2*(t - 0.3f)/0.2f));
            else if (t < 0.8f) p = Vector3Subtract(Vector3Add(c, Vector3Scale(nr, 1 - 2*(t - 0.5f)/0.3f)), nu);
            else p = Vector3Subtract(Vector3Add(c, Vector3Scale(nu, -1 + 2*(t - 0.8f)/0.2f)), nr);
            bool on = ((i + (int)(G.time*12)) % 4) == 0;
            GlowQuad(p, r, u, on ? 0.55f : 0.3f, on ? (Color){ 255, 120, 220, 255 } : (Color){ 90, 30, 70, 255 });
        }
        float pulse = 0.5f + 0.5f*sinf(G.time*6.0f);
        Vector3 ac = Vector3Add(c, Vector3Scale(nr, 0.48f));
        unsigned char pv = (unsigned char)(60 + 90*pulse);
        GlowQuad(ac, r, u, 4.0f, (Color){ pv, (unsigned char)(pv*0.85f), 0, 255 });
    }
    rlEnd();
    rlSetTexture(0);
    rlDrawRenderBatchActive();
    EndBlendMode();
    rlEnableDepthMask();
}

/* Refresh the jumbotron feed: a TV chase-cam on the race leader, every 3rd frame, 320x180. */
void JumbotronUpdate(void)
{
    const Track *tr = &T;
    if (!tr->def || tr->def->scenery != SCENERY_STADIUM || tr->numJumbo == 0 || R.numKarts == 0) return;
    if (!G.jumboRT.id) {
        G.jumboRT = LoadRenderTexture(320, 180);
        SetTextureFilter(G.jumboRT.texture, TEXTURE_FILTER_BILINEAR);
        gJumboReady = false;
    }
    if (gJumboReady && (G.jumboFrame++ % 3) != 0) return;
    int lead = 0;
    for (int i = 0; i < R.numKarts; i++) if (R.karts[i].place == 1) lead = i;
    /* cycle between a chase view and a low trackside "TV" angle every 7 s */
    const Kart *k = &R.karts[lead];
    Vector3 fw = { sinf(k->heading), 0, cosf(k->heading) };
    Vector3 rt = { fw.z, 0, -fw.x };
    int mode = ((int)(G.time/7.0f)) % 2;
    Vector3 want = mode == 0 ? Vector3Add(Vector3Subtract(k->pos, Vector3Scale(fw, 8.0f)), (Vector3){ 0, 3.6f, 0 })
                             : Vector3Add(Vector3Add(k->pos, Vector3Add(Vector3Scale(fw, 10.0f), Vector3Scale(rt, 7.0f))), (Vector3){ 0, 2.0f, 0 });
    Track *mt = (Track *)tr;
    static int lastMode = -1, lastLead = -1;
    if (mode != lastMode || lead != lastLead || Vector3Distance(mt->jumboCamPos, want) > 40) mt->jumboCamPos = want;
    else mt->jumboCamPos = Vector3Lerp(mt->jumboCamPos, want, 0.35f);
    lastMode = mode; lastLead = lead;
    mt->jumboCamTarget = Vector3Add(k->pos, Vector3Add(Vector3Scale(fw, 3.0f), (Vector3){ 0, 1.0f, 0 }));
    Camera3D cam = { 0 };
    cam.position = mt->jumboCamPos; cam.target = mt->jumboCamTarget; cam.up = (Vector3){ 0, 1, 0 };
    cam.fovy = mode == 0 ? 58.0f : 46.0f; cam.projection = CAMERA_PERSPECTIVE;

    Camera3D saveCam = G.curCam;
    bool saveSprites = G.kartSprites;
    float saveAspect = gViewAspect;
    gJumboPass = true;
    gViewAspect = 16.0f/9.0f;
    G.curCam = cam;
    G.kartSprites = !RenderDirect();
    SetFog();
    BeginTextureMode(G.jumboRT);
    ClearBackground(T.def->fog);
    BeginWorld(cam, cam.fovy);
    DrawSkyAndTrack(cam);
    StadiumDrawExtras(cam);
    BeginShaderMode(G.fogShader);
    for (int i = 0; i < R.numKarts; i++) DrawCharacterKart(R.karts[i].charId, &R.karts[i], G.time + i*1.7f);
    DrawItemsWorld(cam);
    ParticlesDraw(cam);
    EndShaderMode();
    EndWorld();
    /* broadcast overlay */
    DrawRectangle(8, 8, 46, 16, (Color){ 0, 0, 0, 160 });
    DrawCircle(18, 16, 4, ((int)(G.time*2) & 1) ? RED : (Color){ 120, 0, 0, 255 });
    DrawText("LIVE", 26, 11, 10, WHITE);
    for (int y = 0; y < 180; y += 3) DrawRectangle(0, y, 320, 1, (Color){ 0, 0, 0, 40 });
    EndTextureMode();
    gJumboPass = false;
    gJumboReady = true;
    G.curCam = saveCam;
    G.kartSprites = saveSprites;
    gViewAspect = saveAspect;
}

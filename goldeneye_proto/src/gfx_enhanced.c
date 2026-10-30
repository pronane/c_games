/*
 * gfx_enhanced.c - "Enhanced" graphics mode (toggle with F2).
 *
 *  - loads skinned / static 3D models listed in assets/models/models.cfg
 *    (GLB / glTF / IQM / OBJ / VOX / M3D through raylib's LoadModel)
 *  - skeletal animation: named clips (idle, walk, run, aim, shoot, reload, death)
 *    matched by name with fallbacks, cross-fades, and an upper-body layer so
 *    guards can aim / fire / reload while walking
 *  - GPU skinning inside the game's lighting shader, so skinned meshes get the
 *    same static + muzzle lights and fog as the level
 *  - enhanced level shading: 2x upscaled detail textures (up to 512), bump
 *    from albedo, specular, light-tinted fog, softer contact shadows, bloom
 *  - every role falls back to the classic procedural look if its model is
 *    missing or fails to load
 *
 * Unity build: included from main.c (after the classic renderer).
 * Pose evaluation is done here (not with UpdateModelAnimation) so that the same
 * code works with raylib 5.5 and 6.x.
 */
#if (RAYLIB_VERSION_MAJOR > 5) || (RAYLIB_VERSION_MAJOR == 5 && RAYLIB_VERSION_MINOR >= 5)
  #define ENH_SUPPORTED 1
#else
  #define ENH_SUPPORTED 0
#endif

#if RAYLIB_VERSION_MAJOR >= 6
  #define MDL_BONECOUNT(m)   ((int)(m).skeleton.boneCount)
  #define MDL_BONES(m)       ((m).skeleton.bones)
  #define MDL_BIND(m)        ((m).skeleton.bindPose)
  #define ANIM_FRAMES(a)     ((a).keyframeCount)
  #define ANIM_POSE(a, f)    ((a).keyframePoses[f])
  #define ANIM_BONES(a)      ((int)(a).boneCount)
  #define ENH_BONE_ATTR      "vertexBoneIndices"
  #define ENH_LOC_BONES      SHADER_LOC_MATRIX_BONETRANSFORMS
  #define ENH_ANIM_FPS       60.0f
#elif ENH_SUPPORTED
  #define MDL_BONECOUNT(m)   ((m).boneCount)
  #define MDL_BONES(m)       ((m).bones)
  #define MDL_BIND(m)        ((m).bindPose)
  #define ANIM_FRAMES(a)     ((a).frameCount)
  #define ANIM_POSE(a, f)    ((a).framePoses[f])
  #define ANIM_BONES(a)      ((a).boneCount)
  #define ENH_BONE_ATTR      "vertexBoneIds"
  #define ENH_LOC_BONES      SHADER_LOC_BONE_MATRICES
  #define ENH_ANIM_FPS       (1000.0f/17.0f)
#endif

#define ENH_MAX_BONES 128

/* ------------------------------------------------------------------ */
/* state shared with main.c                                            */
/* ------------------------------------------------------------------ */
static bool gEnh = false;              /* Enhanced mode on */
static char gToast[128];
static float gToastT = 0;
static int gToastY = 60;
static void Toast(const char *t) { snprintf(gToast, sizeof(gToast), "%s", t); gToastT = 2.6f; }

/* ------------------------------------------------------------------ */
/* roles & manifest                                                    */
/* ------------------------------------------------------------------ */
typedef enum {
    RO_GUARD_SOLDIER, RO_GUARD_CAP, RO_COMMANDO, RO_PLAYER1, RO_PLAYER2,
    RO_WEAPON_PP7, RO_WEAPON_PP7S, RO_WEAPON_KF7, RO_WEAPON_GOLDEN,
    RO_VIEW_PP7, RO_VIEW_PP7S, RO_VIEW_KF7, RO_VIEW_GOLDEN,
    RO_PROP_CRATE, RO_PROP_BARREL, RO_PROP_DESK, RO_PROP_RACK,
    RO_COUNT
} RoleId;
static const char *ROLE_NAMES[RO_COUNT] = {
    "guard_soldier", "guard_cap", "commando", "player1", "player2",
    "weapon_pp7", "weapon_pp7_silenced", "weapon_kf7", "weapon_golden",
    "view_pp7", "view_pp7_silenced", "view_kf7", "view_golden",
    "prop_crate", "prop_barrel", "prop_desk", "prop_rack",
};
typedef enum { CL_IDLE, CL_WALK, CL_RUN, CL_AIM, CL_SHOOT, CL_RELOAD, CL_DEATH, CL_COUNT } ClipId;
static const char *CLIP_KEYS[CL_COUNT] = { "idle", "walk", "run", "aim", "shoot", "reload", "death" };
/* fallback chain when a clip is missing (index into ClipId, -1 = none) */
static const int CLIP_FALLBACK[CL_COUNT] = { -1, CL_IDLE, CL_WALK, CL_IDLE, CL_AIM, CL_AIM, -1 };
static const bool CLIP_LOOPS[CL_COUNT] = { true, true, true, true, false, false, false };

typedef struct {
    /* manifest */
    char file[192], animFile[192];
    float scale;
    float fitHeight;                /* >0: auto-scale so the model is this tall (m) */
    Vector3 rot, offset;            /* degrees, model units after scale */
    char clipName[CL_COUNT][64];
    float clipRate[CL_COUNT];       /* playback speed multiplier */
    char attach[48];                /* weapon socket bone (characters) */
    char upper[48];                 /* first bone of the upper-body layer */
    Vector3 muzzle;                 /* muzzle point in weapon model space (before fix) */
    float fps;                      /* animation sample rate */
    float walkSpeed, runSpeed;      /* world speed (m/s) at clip rate 1 */
    bool configured;
    /* runtime */
    bool tried, ok, skinned;
    Model model;
    ModelAnimation *anims;
    int animCount;
    int clip[CL_COUNT];
    int attachBone, footL, footR, boneCount;
    Matrix fix, invBind[ENH_MAX_BONES];
    unsigned char upperMask[ENH_MAX_BONES];
    int order[ENH_MAX_BONES];       /* parents before children */
    long mtime;
} Asset;
static Asset assets[RO_COUNT];
static int enhLoaded = 0, enhFailed = 0, enhConfigured = 0;

static Shader shSkin, shStatic, shLevelEnh, shClassic;
static bool enhShadersOk = false, levelEnhOk = false;
typedef struct { int ambient, emissive, specK, gloss, bump, sPos, sCol, sCount, fogTint; } EnhLocs;
static EnhLocs lkSkin, lkStatic, lkLevel;
static Texture2D texHi[TX_COUNT];
static bool texHiOk[TX_COUNT];

static char *TrimStr(char *s)
{
    while (*s == ' ' || *s == '\t') s++;
    char *e = s + strlen(s);
    while (e > s && (e[-1] == ' ' || e[-1] == '\t' || e[-1] == '\r' || e[-1] == '\n')) *--e = 0;
    return s;
}
static int RoleByName(const char *n) { for (int i = 0; i < RO_COUNT; i++) if (strcmp(ROLE_NAMES[i], n) == 0) return i; return -1; }

static void AssetDefaults(Asset *a, int role)
{
    memset(a, 0, sizeof(*a));
    a->scale = 1; a->fps = ENH_ANIM_FPS; a->walkSpeed = 1.5f; a->runSpeed = 4.0f;
    for (int c = 0; c < CL_COUNT; c++) { snprintf(a->clipName[c], 64, "%s", CLIP_KEYS[c]); a->clipRate[c] = 1; }
    snprintf(a->attach, sizeof(a->attach), "gun");
    snprintf(a->upper, sizeof(a->upper), "spine");
    if (role <= RO_PLAYER2) a->rot.y = 90;
    if (role >= RO_VIEW_PP7 && role <= RO_VIEW_GOLDEN) a->rot.y = 180;
}

static const char *ModelsDir(void)
{
    static char d[512];
    snprintf(d, sizeof(d), "%sassets/models", GetApplicationDirectory());
    return d;
}

/* models.cfg: INI style.  [role] then key = value lines, # or ; comments */
static void LoadManifest(void)
{
    for (int i = 0; i < RO_COUNT; i++) AssetDefaults(&assets[i], i);
    enhConfigured = 0;
    char path[600]; snprintf(path, sizeof(path), "%s/models.cfg", ModelsDir());
    char *txt = LoadFileText(path);
    if (!txt) { TraceLog(LOG_WARNING, "ENHANCED: %s not found - every role uses the classic look", path); return; }
    Asset *cur = NULL;
    char *line = txt;
    while (line && *line) {
        char *nl = strchr(line, '\n');
        if (nl) *nl = 0;
        char *s = TrimStr(line);
        char *hash = strpbrk(s, "#;"); if (hash) *hash = 0;
        s = TrimStr(s);
        if (*s == '[') {
            char *e = strchr(s, ']'); if (e) *e = 0;
            int r = RoleByName(TrimStr(s + 1));
            cur = r >= 0 ? &assets[r] : NULL;
            if (r < 0) TraceLog(LOG_WARNING, "ENHANCED: unknown role [%s] in models.cfg", s + 1);
        } else if (*s && cur) {
            char *eq = strchr(s, '=');
            if (eq) {
                *eq = 0;
                char *k = TrimStr(s), *v = TrimStr(eq + 1);
                if (!strcmp(k, "file")) { snprintf(cur->file, sizeof(cur->file), "%s", v); if (*v) { cur->configured = true; } }
                else if (!strcmp(k, "anims")) snprintf(cur->animFile, sizeof(cur->animFile), "%s", v);
                else if (!strcmp(k, "scale")) cur->scale = (float)atof(v);
                else if (!strcmp(k, "height")) cur->fitHeight = (float)atof(v);
                else if (!strcmp(k, "rot")) sscanf(v, "%f %f %f", &cur->rot.x, &cur->rot.y, &cur->rot.z);
                else if (!strcmp(k, "offset")) sscanf(v, "%f %f %f", &cur->offset.x, &cur->offset.y, &cur->offset.z);
                else if (!strcmp(k, "muzzle")) sscanf(v, "%f %f %f", &cur->muzzle.x, &cur->muzzle.y, &cur->muzzle.z);
                else if (!strcmp(k, "attach")) snprintf(cur->attach, sizeof(cur->attach), "%s", v);
                else if (!strcmp(k, "upper_body")) snprintf(cur->upper, sizeof(cur->upper), "%s", v);
                else if (!strcmp(k, "fps")) cur->fps = (float)atof(v);
                else if (!strcmp(k, "walk_speed")) cur->walkSpeed = (float)atof(v);
                else if (!strcmp(k, "run_speed")) cur->runSpeed = (float)atof(v);
                else if (!strncmp(k, "clip_", 5) || !strncmp(k, "rate_", 5)) {
                    for (int c = 0; c < CL_COUNT; c++) if (!strcmp(k + 5, CLIP_KEYS[c])) {
                        if (k[0] == 'c') snprintf(cur->clipName[c], 64, "%s", v);
                        else cur->clipRate[c] = (float)atof(v);
                    }
                }
                else TraceLog(LOG_WARNING, "ENHANCED: unknown key '%s' in models.cfg", k);
            }
        }
        line = nl ? nl + 1 : NULL;
    }
    UnloadFileText(txt);
    for (int i = 0; i < RO_COUNT; i++) if (assets[i].configured) enhConfigured++;
}

/* ------------------------------------------------------------------ */
/* shaders                                                             */
/* ------------------------------------------------------------------ */
static const char *ENH_VS =
    "in vec3 vertexPosition; in vec2 vertexTexCoord; in vec3 vertexNormal; in vec4 vertexColor;\n"
    "uniform mat4 mvp; uniform mat4 matModel; uniform mat4 matNormal;\n"
    "#ifdef SKINNED\n"
    "in vec4 " ENH_BONE_ATTR "; in vec4 vertexBoneWeights; uniform mat4 boneMatrices[128];\n"
    "#endif\n"
    "out vec3 fragPosition; out vec2 fragTexCoord; out vec4 fragColor; out vec3 fragNormal;\n"
    "void main() {\n"
    "  vec4 p = vec4(vertexPosition, 1.0); vec4 n = vec4(vertexNormal, 0.0);\n"
    "#ifdef SKINNED\n"
    "  vec4 bi = " ENH_BONE_ATTR "; vec4 w = vertexBoneWeights;\n"
    "  float ws = w.x + w.y + w.z + w.w;\n"
    "  if (ws > 0.001) {\n"
    "    mat4 S = boneMatrices[int(bi.x)]*w.x + boneMatrices[int(bi.y)]*w.y + boneMatrices[int(bi.z)]*w.z + boneMatrices[int(bi.w)]*w.w;\n"
    "    p = S*p/ws; p.w = 1.0; n = S*n;\n"
    "  }\n"
    "#endif\n"
    "  fragPosition = vec3(matModel*p);\n"
    "  fragTexCoord = vertexTexCoord; fragColor = vertexColor;\n"
    "  fragNormal = normalize(mat3(matModel)*n.xyz);\n"
    "  gl_Position = mvp*p;\n"
    "}\n";

/* LEVEL: baked vertex light (fragColor*2) + relief/specular from the nearest static lights.
   MODEL: per-pixel lighting from an ambient term + the static lights that reach the object. */
static const char *ENH_FS =
    "in vec3 fragPosition; in vec2 fragTexCoord; in vec4 fragColor; in vec3 fragNormal;\n"
    "uniform sampler2D texture0; uniform vec4 colDiffuse;\n"
    "uniform vec3 viewPos; uniform vec3 fogColor; uniform float fogDensity; uniform float unlit;\n"
    "uniform vec4 dynPos[4]; uniform vec4 dynCol[4]; uniform int dynCount;\n"
    "uniform vec4 sPos[6]; uniform vec4 sCol[6]; uniform int sCount;\n"
    "uniform vec3 ambient; uniform vec3 emissive; uniform float specK; uniform float gloss; uniform float bump; uniform vec3 fogTint;\n"
    "out vec4 finalColor;\n"
    "float lum(vec3 c) { return dot(c, vec3(0.299, 0.587, 0.114)); }\n"
    "vec3 bumped(vec3 n, vec3 p, vec2 uv) {\n"
    "  vec2 ts = 1.0/vec2(textureSize(texture0, 0));\n"
    "  vec2 fw = max(fwidth(uv), ts);\n"
    "  float h0 = lum(texture(texture0, uv).rgb);\n"
    "  float hx = lum(texture(texture0, uv + vec2(fw.x, 0.0)).rgb);\n"
    "  float hy = lum(texture(texture0, uv + vec2(0.0, fw.y)).rgb);\n"
    "  vec3 dp1 = dFdx(p), dp2 = dFdy(p); vec2 du1 = dFdx(uv), du2 = dFdy(uv);\n"
    "  vec3 dp2p = cross(dp2, n), dp1p = cross(n, dp1);\n"
    "  vec3 T = dp2p*du1.x + dp1p*du2.x; vec3 B = dp2p*du1.y + dp1p*du2.y;\n"
    "  float im = inversesqrt(max(max(dot(T, T), dot(B, B)), 1e-12));\n"
    "  T *= im; B *= im;\n"
    "  vec2 g = vec2(hx - h0, hy - h0)*bump;\n"
    "  return normalize(n - T*g.x - B*g.y);\n"
    "}\n"
    "void main() {\n"
    "  vec4 tx = texture(texture0, fragTexCoord);\n"
    "  if (tx.a*colDiffuse.a < 0.05) discard;\n"
    "  vec3 base = tx.rgb*colDiffuse.rgb;\n"
    "  vec3 n0 = normalize(fragNormal);\n"
    "  vec3 n = bump > 0.0 ? bumped(n0, fragPosition, fragTexCoord) : n0;\n"
    "  vec3 V = normalize(viewPos - fragPosition);\n"
    "  vec3 col;\n"
    "  if (unlit > 0.5) col = base*fragColor.rgb*1.15;\n"
    "  else {\n"
    "    vec3 spec = vec3(0.0);\n"
    "#ifdef LEVEL\n"
    "    vec3 light = fragColor.rgb*2.0;\n"
    "    float lit = clamp(lum(light)*1.4, 0.0, 1.0);\n"
    "#else\n"
    "    vec3 light = ambient*(0.75 + 0.25*n.y);\n"
    "    float lit = 1.0;\n"
    "#endif\n"
    "    for (int i = 0; i < 6; i++) {\n"
    "      if (i >= sCount) break;\n"
    "      vec3 d = sPos[i].xyz - fragPosition; float dist = length(d); vec3 l = d/max(dist, 0.001);\n"
    "      float att = clamp(1.0 - dist/sPos[i].w, 0.0, 1.0); att *= att;\n"
    "#ifdef LEVEL\n"
    "      light += sCol[i].rgb*att*(max(dot(n, l), 0.0) - max(dot(n0, l), 0.0))*0.9*lit;\n"
    "#else\n"
    "      float w = max(dot(n, l), 0.0)*0.85 + 0.15;\n"
    "      light += sCol[i].rgb*att*w*sCol[i].w;\n"
    "#endif\n"
    "      vec3 h = normalize(l + V);\n"
    "      spec += sCol[i].rgb*att*pow(max(dot(n, h), 0.0), gloss)*sCol[i].w;\n"
    "    }\n"
    "    for (int i = 0; i < 4; i++) {\n"
    "      if (i >= dynCount) break;\n"
    "      vec3 d = dynPos[i].xyz - fragPosition; float dist = length(d); vec3 l = d/max(dist, 0.001);\n"
    "      float att = clamp(1.0 - dist/dynPos[i].w, 0.0, 1.0); att *= att;\n"
    "      float ndl = max(dot(n, l), 0.0)*0.75 + 0.25;\n"
    "      light += dynCol[i].rgb*att*ndl;\n"
    "      vec3 h = normalize(l + V);\n"
    "      spec += dynCol[i].rgb*att*pow(max(dot(n, h), 0.0), gloss);\n"
    "    }\n"
    "    col = base*light + spec*specK*lit*(0.35 + 0.65*lum(base) + 0.3*specK);\n"
    "  }\n"
    "  col += base*emissive;\n"
    "  float dist = length(viewPos - fragPosition);\n"
    "  float fd = dist*fogDensity;\n"
    "  float f = 1.0 - exp(-fd*fd);\n"
    "  float hfog = 1.0 + 0.35*clamp(1.0 - fragPosition.y/3.0, 0.0, 1.0);\n"   /* a little denser near the floor */
    "  f = clamp(f*hfog, 0.0, 1.0);\n"
    "  col = mix(col, fogColor + fogTint, f);\n"
    "  finalColor = vec4(col, tx.a*colDiffuse.a*fragColor.a);\n"
    "}\n";

static const char *BLOOM_VS = NULL;   /* default vertex shader */
static const char *BRIGHT_FS =
    "#version 330\n"
    "in vec2 fragTexCoord; in vec4 fragColor; uniform sampler2D texture0; uniform vec2 texel; out vec4 finalColor;\n"
    "void main() {\n"
    "  vec3 c = vec3(0.0);\n"
    "  c += texture(texture0, fragTexCoord + texel*vec2(-1.0, -1.0)).rgb;\n"
    "  c += texture(texture0, fragTexCoord + texel*vec2( 1.0, -1.0)).rgb;\n"
    "  c += texture(texture0, fragTexCoord + texel*vec2(-1.0,  1.0)).rgb;\n"
    "  c += texture(texture0, fragTexCoord + texel*vec2( 1.0,  1.0)).rgb;\n"
    "  c *= 0.25;\n"
    "  float m = dot(c, vec3(0.30, 0.59, 0.11));\n"
    "  finalColor = vec4(c*smoothstep(0.88, 1.0, m)*0.85, 1.0);\n"
    "}\n";
static const char *BLUR_FS =
    "#version 330\n"
    "in vec2 fragTexCoord; in vec4 fragColor; uniform sampler2D texture0; uniform vec2 dir; out vec4 finalColor;\n"
    "void main() {\n"
    "  float w[5] = float[](0.227027, 0.1945946, 0.1216216, 0.054054, 0.016216);\n"
    "  vec3 c = texture(texture0, fragTexCoord).rgb*w[0];\n"
    "  for (int i = 1; i < 5; i++) {\n"
    "    c += texture(texture0, fragTexCoord + dir*float(i)*1.5).rgb*w[i];\n"
    "    c += texture(texture0, fragTexCoord - dir*float(i)*1.5).rgb*w[i];\n"
    "  }\n"
    "  finalColor = vec4(c, 1.0);\n"
    "}\n";

static Shader shBright, shBlur;
static int locTexel, locDir;
static RenderTexture2D rtScene, rtBloomA, rtBloomB;
static int rtW = 0, rtH = 0;
static bool bloomOk = false;

static Shader BuildShader(const char *defines, EnhLocs *lk)
{
    static char vs[8192], fs[12288];
    snprintf(vs, sizeof(vs), "#version 330\n%s%s", defines, ENH_VS);
    snprintf(fs, sizeof(fs), "#version 330\n%s%s", defines, ENH_FS);
    Shader s = LoadShaderFromMemory(vs, fs);
    if (s.id == 0 || s.id == rlGetShaderIdDefault()) { s.id = 0; return s; }
    s.locs[SHADER_LOC_MATRIX_MODEL] = GetShaderLocation(s, "matModel");
    s.locs[SHADER_LOC_MATRIX_NORMAL] = GetShaderLocation(s, "matNormal");
    lk->ambient = GetShaderLocation(s, "ambient");
    lk->emissive = GetShaderLocation(s, "emissive");
    lk->specK = GetShaderLocation(s, "specK");
    lk->gloss = GetShaderLocation(s, "gloss");
    lk->bump = GetShaderLocation(s, "bump");
    lk->sPos = GetShaderLocation(s, "sPos");
    lk->sCol = GetShaderLocation(s, "sCol");
    lk->sCount = GetShaderLocation(s, "sCount");
    lk->fogTint = GetShaderLocation(s, "fogTint");
    Vector3 fc = FOG_RGB;
    SetShaderValue(s, GetShaderLocation(s, "fogColor"), &fc, SHADER_UNIFORM_VEC3);
    float fd = gFogDensity; SetShaderValue(s, GetShaderLocation(s, "fogDensity"), &fd, SHADER_UNIFORM_FLOAT);
    float z = 0; SetShaderValue(s, GetShaderLocation(s, "unlit"), &z, SHADER_UNIFORM_FLOAT);
    Vector3 zero = { 0 };
    SetShaderValue(s, lk->emissive, &zero, SHADER_UNIFORM_VEC3);
    SetShaderValue(s, lk->fogTint, &zero, SHADER_UNIFORM_VEC3);
    float g = 24, k = 0.3f, b = 0;
    SetShaderValue(s, lk->gloss, &g, SHADER_UNIFORM_FLOAT);
    SetShaderValue(s, lk->specK, &k, SHADER_UNIFORM_FLOAT);
    SetShaderValue(s, lk->bump, &b, SHADER_UNIFORM_FLOAT);
    return s;
}

/* switch the level ("gShader") between the classic and the enhanced program */
static void ApplyLevelShader(void)
{
    if (!shaderOk) return;
    Shader s = (gEnh && levelEnhOk) ? shLevelEnh : shClassic;
    gShader = s;
    locViewPos = GetShaderLocation(gShader, "viewPos");
    locFogColor = GetShaderLocation(gShader, "fogColor");
    locFogDensity = GetShaderLocation(gShader, "fogDensity");
    locUnlit = GetShaderLocation(gShader, "unlit");
    locDynPos = GetShaderLocation(gShader, "dynPos");
    locDynCol = GetShaderLocation(gShader, "dynCol");
    locDynCount = GetShaderLocation(gShader, "dynCount");
    SetShaderValue(gShader, locFogColor, &FOG_RGB, SHADER_UNIFORM_VEC3);
    for (int i = 0; i < TX_COUNT; i++) {
        mats[i].shader = gShader;
        mats[i].maps[MATERIAL_MAP_DIFFUSE].texture = (gEnh && texHiOk[i]) ? texHi[i] : tex[i];
    }
}

/* ------------------------------------------------------------------ */
/* 2x detail textures (up to 512) for the level in Enhanced mode        */
/* ------------------------------------------------------------------ */
static bool HiResCandidate(int i)
{
    return (i <= TX_STEEL && i != TX_GLASS) || i == TX_AMMOBOX || i == TX_DISK || i == TX_VEST || i == TX_LIGHTPANEL;
}
static float HashN(int x, int y) { unsigned h = (unsigned)(x*374761393 + y*668265263); h = (h ^ (h >> 13))*1274126177u; return ((h ^ (h >> 16)) & 0xffff)/65535.0f; }
static void BuildHiResTextures(void)
{
    char dir[600]; snprintf(dir, sizeof(dir), "%sassets/textures_hd", GetApplicationDirectory());
    for (int i = 0; i < TX_COUNT; i++) {
        texHiOk[i] = false;
        if (!HiResCandidate(i)) continue;
        char p[700]; snprintf(p, sizeof(p), "%s/%s.png", dir, TEX_NAMES[i]);
        Image img = { 0 };
        if (FileExists(p)) img = LoadImage(p);
        if (img.data == NULL) {
            img = LoadImageFromTexture(tex[i]);
            if (img.data == NULL) continue;
            if (img.format != PIXELFORMAT_UNCOMPRESSED_R8G8B8A8) ImageFormat(&img, PIXELFORMAT_UNCOMPRESSED_R8G8B8A8);
            int w = img.width*2, h = img.height*2;
            while (w > 512 || h > 512) { w /= 2; h /= 2; }
            if (w <= img.width) { UnloadImage(img); continue; }
            ImageResize(&img, w, h);
            /* fine grain detail so the upscale does not look blurry */
            Color *px = (Color *)img.data;
            for (int y = 0; y < h; y++) for (int x = 0; x < w; x++) {
                float n = HashN(x, y)*0.55f + HashN(x/2 + 911, y/2 + 37)*0.45f;
                float k = 0.93f + 0.14f*n;
                Color *c = &px[y*w + x];
                c->r = ClampB(c->r*k); c->g = ClampB(c->g*k); c->b = ClampB(c->b*k);
            }
        } else if (img.format != PIXELFORMAT_UNCOMPRESSED_R8G8B8A8) ImageFormat(&img, PIXELFORMAT_UNCOMPRESSED_R8G8B8A8);
        texHi[i] = LoadTextureFromImage(img);
        UnloadImage(img);
        GenTextureMipmaps(&texHi[i]);
        SetTextureFilter(texHi[i], TEXTURE_FILTER_ANISOTROPIC_8X);
        SetTextureWrap(texHi[i], TEXTURE_WRAP_REPEAT);
        texHiOk[i] = texHi[i].id > 0;
    }
}

/* per-texture specular for the level in Enhanced mode */
static void LevelSpecFor(int t, float *specK, float *gloss, float *bump)
{
    *specK = 0.12f; *gloss = 12; *bump = 1.6f;
    switch (t) {
        case TX_WALL_METAL: case TX_FLOOR_METAL: case TX_STEEL: case TX_DOOR: case TX_DOOR_ARMORY: *specK = 0.65f; *gloss = 40; *bump = 1.2f; break;
        case TX_FLOOR_TILE: case TX_FLOOR_LAB: case TX_WALL_LAB: case TX_HAZARD: *specK = 0.45f; *gloss = 48; *bump = 0.9f; break;
        case TX_FLOOR_WOOD: case TX_WALL_WOOD: case TX_DESK: *specK = 0.25f; *gloss = 20; *bump = 1.2f; break;
        case TX_CEIL_TILE: case TX_CEIL_CONCRETE: *specK = 0.05f; *gloss = 8; *bump = 1.4f; break;
        case TX_CRATE: *specK = 0.08f; *gloss = 10; *bump = 2.0f; break;
        case TX_BARREL: case TX_RACK: *specK = 0.5f; *gloss = 32; *bump = 0.8f; break;
        default: break;
    }
}
static void EnhLevelMaterial(int t)
{
    if (!gEnh || !levelEnhOk) return;
    float k, g, b; LevelSpecFor(t, &k, &g, &b);
    SetShaderValue(shLevelEnh, lkLevel.specK, &k, SHADER_UNIFORM_FLOAT);
    SetShaderValue(shLevelEnh, lkLevel.gloss, &g, SHADER_UNIFORM_FLOAT);
    SetShaderValue(shLevelEnh, lkLevel.bump, &b, SHADER_UNIFORM_FLOAT);
}

/* ------------------------------------------------------------------ */
/* asset loading (per-asset fallback)                                  */
/* ------------------------------------------------------------------ */
#if RAYLIB_VERSION_MAJOR >= 6
  #define MESH_BONEIDX(m) ((m).boneIndices)
#else
  #define MESH_BONEIDX(m) ((m).boneIds)
#endif

static bool StrIEq(const char *a, const char *b) { for (; *a && *b; a++, b++) if (tolower((unsigned char)*a) != tolower((unsigned char)*b)) return false; return *a == *b; }
static bool StrIHas(const char *h, const char *n)
{
    size_t ln = strlen(n);
    if (ln == 0) return false;
    for (; *h; h++) { size_t i = 0; while (i < ln && h[i] && tolower((unsigned char)h[i]) == tolower((unsigned char)n[i])) i++; if (i == ln) return true; }
    return false;
}
static int FindBone(const Asset *a, const char *name)
{
    int n = MDL_BONECOUNT(a->model);
    for (int i = 0; i < n; i++) if (StrIEq(MDL_BONES(a->model)[i].name, name)) return i;
    for (int i = 0; i < n; i++) if (StrIHas(MDL_BONES(a->model)[i].name, name)) return i;
    return -1;
}
static Matrix TrsMatrix(Transform t)
{
    return MatrixMultiply(MatrixMultiply(MatrixScale(t.scale.x, t.scale.y, t.scale.z), QuaternionToMatrix(t.rotation)),
                          MatrixTranslate(t.translation.x, t.translation.y, t.translation.z));
}

static void UnloadAsset(Asset *a)
{
    if (a->ok) {
        if (a->anims) UnloadModelAnimations(a->anims, a->animCount);
        UnloadModel(a->model);
    }
    a->ok = false; a->tried = false; a->anims = NULL; a->animCount = 0;
}

static void LoadAsset(Asset *a, int role)
{
    a->tried = true; a->ok = false;
    if (!a->configured) return;
    char path[1024]; snprintf(path, sizeof(path), "%s/%s", ModelsDir(), a->file);
    if (!FileExists(path)) { TraceLog(LOG_WARNING, "ENHANCED: [%s] %s missing - classic fallback", ROLE_NAMES[role], path); enhFailed++; return; }
    a->model = LoadModel(path);
    if (a->model.meshCount <= 0 || a->model.meshes == NULL) {
        TraceLog(LOG_WARNING, "ENHANCED: [%s] could not load %s - classic fallback", ROLE_NAMES[role], path);
        UnloadModel(a->model); enhFailed++; return;
    }
    a->mtime = GetFileModTime(path);
    a->ok = true;
    a->boneCount = MDL_BONECOUNT(a->model);
    if (a->boneCount > ENH_MAX_BONES) { TraceLog(LOG_WARNING, "ENHANCED: [%s] %d bones (max %d) - animation disabled", ROLE_NAMES[role], a->boneCount, ENH_MAX_BONES); }
    bool hasWeights = false;
    for (int m = 0; m < a->model.meshCount; m++) if (MESH_BONEIDX(a->model.meshes[m]) && a->model.meshes[m].boneWeights) hasWeights = true;
    /* animations: same file, or a separate "anims" file with the same skeleton */
    const char *ap = path; char apath[1024];
    if (a->animFile[0]) { snprintf(apath, sizeof(apath), "%s/%s", ModelsDir(), a->animFile); ap = apath; }
    if (a->boneCount > 0 && a->boneCount <= ENH_MAX_BONES && FileExists(ap)) {
        a->anims = LoadModelAnimations(ap, &a->animCount);
        int good = 0;
        for (int i = 0; i < a->animCount; i++) if (ANIM_BONES(a->anims[i]) == a->boneCount && ANIM_FRAMES(a->anims[i]) > 0) good++;
        if (good == 0 && a->anims) { UnloadModelAnimations(a->anims, a->animCount); a->anims = NULL; a->animCount = 0; }
    }
    a->skinned = hasWeights && a->boneCount > 0 && a->boneCount <= ENH_MAX_BONES && enhShadersOk;
    /* shaders on every material */
    for (int i = 0; i < a->model.materialCount; i++) {
        if (!enhShadersOk) break;
        a->model.materials[i].shader = a->skinned ? shSkin : shStatic;
        Texture2D t = a->model.materials[i].maps[MATERIAL_MAP_DIFFUSE].texture;
        if (t.id > 0 && t.id != rlGetTextureIdDefault()) {
            GenTextureMipmaps(&a->model.materials[i].maps[MATERIAL_MAP_DIFFUSE].texture);
            SetTextureFilter(a->model.materials[i].maps[MATERIAL_MAP_DIFFUSE].texture, TEXTURE_FILTER_TRILINEAR);
        }
    }
    /* clip mapping: exact (case-insensitive) name, then substring, then fallback chain */
    for (int c = 0; c < CL_COUNT; c++) {
        a->clip[c] = -1;
        for (int i = 0; i < a->animCount && a->clip[c] < 0; i++) if (ANIM_BONES(a->anims[i]) == a->boneCount && StrIEq(a->anims[i].name, a->clipName[c])) a->clip[c] = i;
        for (int i = 0; i < a->animCount && a->clip[c] < 0; i++) if (ANIM_BONES(a->anims[i]) == a->boneCount && StrIHas(a->anims[i].name, a->clipName[c])) a->clip[c] = i;
    }
    if (a->clip[CL_IDLE] < 0 && a->animCount > 0) a->clip[CL_IDLE] = 0;
    for (int c = 0; c < CL_COUNT; c++) { int k = c; while (a->clip[c] < 0 && CLIP_FALLBACK[k] >= 0) { k = CLIP_FALLBACK[k]; a->clip[c] = a->clip[k]; } }
    /* bone helpers */
    a->attachBone = a->boneCount ? FindBone(a, a->attach) : -1;
    a->footL = a->boneCount ? FindBone(a, "foot.L") : -1;
    a->footR = a->boneCount ? FindBone(a, "foot.R") : -1;
    if (a->footL < 0 && a->boneCount) a->footL = FindBone(a, "footl");
    if (a->footR < 0 && a->boneCount) a->footR = FindBone(a, "footr");
    int up = a->boneCount ? FindBone(a, a->upper) : -1;
    if (a->boneCount <= ENH_MAX_BONES) {
        int n = a->boneCount, done = 0;
        unsigned char placed[ENH_MAX_BONES] = { 0 };
        while (done < n) {
            int before = done;
            for (int b = 0; b < n; b++) {
                if (placed[b]) continue;
                int p = MDL_BONES(a->model)[b].parent;
                if (p < 0 || p >= n || placed[p]) { a->order[done++] = b; placed[b] = 1; }
            }
            if (done == before) { for (int b = 0; b < n; b++) if (!placed[b]) { a->order[done++] = b; placed[b] = 1; } }
        }
        for (int i = 0; i < n; i++) {
            int b = a->order[i], p = MDL_BONES(a->model)[b].parent;
            a->upperMask[b] = (b == up) || (p >= 0 && p < n && a->upperMask[p]);
            a->invBind[b] = MatrixInvert(TrsMatrix(MDL_BIND(a->model)[b]));
        }
    }
    if (a->fitHeight > 0) {   /* e.g. FBX exported in centimetres: scale to a known height */
        BoundingBox bb = GetModelBoundingBox(a->model);
        Matrix R = MatrixRotateXYZ((Vector3){ a->rot.x*DEG2RAD, a->rot.y*DEG2RAD, a->rot.z*DEG2RAD });
        float lo = 1e30f, hi = -1e30f;
        for (int c = 0; c < 8; c++) {
            Vector3 q = { (c & 1) ? bb.max.x : bb.min.x, (c & 2) ? bb.max.y : bb.min.y, (c & 4) ? bb.max.z : bb.min.z };
            q = Vector3Transform(q, R); lo = fminf(lo, q.y); hi = fmaxf(hi, q.y);
        }
        if (hi - lo > 1e-5f) a->scale = a->fitHeight/(hi - lo);
        TraceLog(LOG_INFO, "ENHANCED: [%s] height %.2f -> scale %.4f", ROLE_NAMES[role], a->fitHeight, a->scale);
    }
    a->fix = MatrixMultiply(MatrixMultiply(MatrixScale(a->scale, a->scale, a->scale),
                            MatrixRotateXYZ((Vector3){ a->rot.x*DEG2RAD, a->rot.y*DEG2RAD, a->rot.z*DEG2RAD })),
                            MatrixTranslate(a->offset.x, a->offset.y, a->offset.z));
    enhLoaded++;
    TraceLog(LOG_INFO, "ENHANCED: [%s] %s: %d meshes, %d bones, %d clips%s", ROLE_NAMES[role], a->file, a->model.meshCount, a->boneCount, a->animCount, a->skinned ? " (GPU skinned)" : "");
}

static void LoadAllAssets(void)
{
    enhLoaded = 0; enhFailed = 0;
    for (int i = 0; i < RO_COUNT; i++) LoadAsset(&assets[i], i);
}
static void UnloadAllAssets(void) { for (int i = 0; i < RO_COUNT; i++) UnloadAsset(&assets[i]); }
static Asset *Use(int role) { if (!gEnh || role < 0 || role >= RO_COUNT) return NULL; Asset *a = &assets[role]; return a->ok ? a : NULL; }

/* ------------------------------------------------------------------ */
/* animation: own pose evaluator (works on raylib 5.5 and 6.x)          */
/* ------------------------------------------------------------------ */
typedef struct { int clip; float t; int prevClip; float prevT; float fade; } AnimLayer;
typedef struct {
    int role;
    AnimLayer base, upper;
    float upperW, lastMuzzle, deathT;
    bool dead;
    Vector3 footW[2]; bool feetOk;
    Vector3 hipW;
} Animator;
#define ANIM_SLOTS (MAX_ENEMIES + 8)
static Animator animChar[ANIM_SLOTS];
static Animator animView[4];
#define XFADE 0.18f

static void LayerSet(AnimLayer *l, int clip, bool restart)
{
    if (clip == l->clip && !restart) return;
    if (l->fade >= 0.5f || l->clip < 0) { l->prevClip = l->clip; l->prevT = l->t; }
    l->clip = clip; l->t = 0; l->fade = (l->prevClip < 0) ? 1.0f : 0.0f;
}
static void LayerAdvance(AnimLayer *l, float dt, float rate, float prevRate)
{
    l->t += dt*rate; l->prevT += dt*prevRate;
    l->fade = fminf(1.0f, l->fade + dt/XFADE);
}
static float ClipDuration(const Asset *a, int animIdx) { if (animIdx < 0) return 0; return (ANIM_FRAMES(a->anims[animIdx]) - 1)/a->fps; }

static Quaternion QNlerpShort(Quaternion a, Quaternion b, float t)
{
    if (a.x*b.x + a.y*b.y + a.z*b.z + a.w*b.w < 0) b = (Quaternion){ -b.x, -b.y, -b.z, -b.w };
    return QuaternionNormalize((Quaternion){ a.x + (b.x - a.x)*t, a.y + (b.y - a.y)*t, a.z + (b.z - a.z)*t, a.w + (b.w - a.w)*t });
}
static Transform TLerp(Transform a, Transform b, float t)
{
    Transform r;
    r.translation = Vector3Lerp(a.translation, b.translation, t);
    r.rotation = QNlerpShort(a.rotation, b.rotation, t);
    r.scale = Vector3Lerp(a.scale, b.scale, t);
    return r;
}
/* sample a clip (model-space keyframes) and convert to parent-local transforms */
static void SampleLocal(const Asset *a, int animIdx, float t, bool loop, Transform *out)
{
    int n = a->boneCount;
    Transform G[ENH_MAX_BONES];
    if (animIdx < 0) { for (int b = 0; b < n; b++) G[b] = MDL_BIND(a->model)[b]; }
    else {
        const ModelAnimation *an = &a->anims[animIdx];
        int fc = ANIM_FRAMES(*an);
        float f = t*a->fps;
        if (fc <= 1) f = 0;
        else if (loop) { f = fmodf(f, (float)(fc - 1)); if (f < 0) f += fc - 1; }
        else f = Clamp(f, 0, (float)(fc - 1));
        int f0 = (int)f, f1 = f0 + 1 < fc ? f0 + 1 : f0;
        float al = f - f0;
        for (int b = 0; b < n; b++) G[b] = TLerp(ANIM_POSE(*an, f0)[b], ANIM_POSE(*an, f1)[b], al);
    }
    for (int b = 0; b < n; b++) {
        int p = MDL_BONES(a->model)[b].parent;
        if (p < 0 || p >= n) { out[b] = G[b]; continue; }
        Quaternion ip = QuaternionInvert(G[p].rotation);
        Vector3 d = Vector3Subtract(G[b].translation, G[p].translation);
        d = Vector3RotateByQuaternion(d, ip);
        Vector3 ps = G[p].scale;
        out[b].translation = (Vector3){ d.x/fmaxf(ps.x, 1e-6f), d.y/fmaxf(ps.y, 1e-6f), d.z/fmaxf(ps.z, 1e-6f) };
        out[b].rotation = QuaternionNormalize(QuaternionMultiply(ip, G[b].rotation));
        out[b].scale = (Vector3){ G[b].scale.x/fmaxf(ps.x, 1e-6f), G[b].scale.y/fmaxf(ps.y, 1e-6f), G[b].scale.z/fmaxf(ps.z, 1e-6f) };
    }
}
static void SampleLayer(const Asset *a, const AnimLayer *l, Transform *out)
{
    SampleLocal(a, l->clip >= 0 ? a->clip[l->clip] : -1, l->t, l->clip >= 0 ? CLIP_LOOPS[l->clip] : true, out);
    if (l->fade < 1.0f && l->prevClip >= 0) {
        Transform P[ENH_MAX_BONES];
        SampleLocal(a, a->clip[l->prevClip], l->prevT, CLIP_LOOPS[l->prevClip], P);
        float w = l->fade*l->fade*(3 - 2*l->fade);
        for (int b = 0; b < a->boneCount; b++) out[b] = TLerp(P[b], out[b], w);
    }
}
/* full evaluation -> bone matrices (bind-space skinning) and global poses */
static void EvalPose(const Asset *a, const Animator *an, Matrix *boneM, Transform *glob)
{
    int n = a->boneCount;
    Transform L[ENH_MAX_BONES];
    SampleLayer(a, &an->base, L);
    if (an->upperW > 0.001f && an->upper.clip >= 0) {
        Transform U[ENH_MAX_BONES];
        SampleLayer(a, &an->upper, U);
        for (int b = 0; b < n; b++) if (a->upperMask[b]) L[b] = TLerp(L[b], U[b], an->upperW);
    }
    for (int i = 0; i < n; i++) {
        int b = a->order[i], p = MDL_BONES(a->model)[b].parent;
        if (p < 0 || p >= n) glob[b] = L[b];
        else {
            Transform P = glob[p];
            Vector3 t = { L[b].translation.x*P.scale.x, L[b].translation.y*P.scale.y, L[b].translation.z*P.scale.z };
            glob[b].translation = Vector3Add(P.translation, Vector3RotateByQuaternion(t, P.rotation));
            glob[b].rotation = QuaternionNormalize(QuaternionMultiply(P.rotation, L[b].rotation));
            glob[b].scale = (Vector3){ P.scale.x*L[b].scale.x, P.scale.y*L[b].scale.y, P.scale.z*L[b].scale.z };
        }
    }
    for (int b = 0; b < n; b++) boneM[b] = MatrixMultiply(a->invBind[b], TrsMatrix(glob[b]));
}

/* ------------------------------------------------------------------ */
/* lighting uniforms for models                                        */
/* ------------------------------------------------------------------ */
static float gLightScale = 1.0f;
static void ModelLights(Shader s, const EnhLocs *lk, Vector3 p, Vector3 extraAmbient, bool cacheable, int *cache, int *cacheN)
{
    float pos[24] = { 0 }, col[24] = { 0 };
    int idx[6], n = 0;
    if (cacheable && cache && *cacheN >= 0) { n = *cacheN; for (int i = 0; i < n; i++) idx[i] = cache[i]; }
    else {
        float best[6];
        for (int i = 0; i < numLights; i++) {
            Light *Lt = &lights[i];
            float d = Vector3Distance(Lt->pos, p);
            if (d > Lt->radius) continue;
            float att = 1 - d/Lt->radius; att *= att;
            float sc = att*(Lt->col.x + Lt->col.y + Lt->col.z);
            if (n == 6 && sc <= best[5]) continue;
            if (!LightVisible(Lt->pos, p)) continue;
            int k = n < 6 ? n++ : 5;
            while (k > 0 && best[k - 1] < sc) { best[k] = best[k - 1]; idx[k] = idx[k - 1]; k--; }
            best[k] = sc; idx[k] = i;
        }
        if (cache) { for (int i = 0; i < n; i++) cache[i] = idx[i]; *cacheN = n; }
    }
    for (int i = 0; i < n; i++) {
        Light *Lt = &lights[idx[i]];
        pos[i*4] = Lt->pos.x; pos[i*4 + 1] = Lt->pos.y; pos[i*4 + 2] = Lt->pos.z; pos[i*4 + 3] = Lt->radius;
        col[i*4] = Lt->col.x*gLightScale; col[i*4 + 1] = Lt->col.y*gLightScale; col[i*4 + 2] = Lt->col.z*gLightScale; col[i*4 + 3] = 1.0f;
    }
    Vector3 amb = Vector3Add(Vector3Scale(AMBIENT, 1.25f), extraAmbient);
    SetShaderValue(s, lk->ambient, &amb, SHADER_UNIFORM_VEC3);
    SetShaderValueV(s, lk->sPos, pos, SHADER_UNIFORM_VEC4, 6);
    SetShaderValueV(s, lk->sCol, col, SHADER_UNIFORM_VEC4, 6);
    SetShaderValue(s, lk->sCount, &n, SHADER_UNIFORM_INT);
}
static void ModelSurface(Shader s, const EnhLocs *lk, float specK, float gloss, float bump)
{
    SetShaderValue(s, lk->specK, &specK, SHADER_UNIFORM_FLOAT);
    SetShaderValue(s, lk->gloss, &gloss, SHADER_UNIFORM_FLOAT);
    SetShaderValue(s, lk->bump, &bump, SHADER_UNIFORM_FLOAT);
}
static void ModelEmissive(Shader s, const EnhLocs *lk, Vector3 e) { SetShaderValue(s, lk->emissive, &e, SHADER_UNIFORM_VEC3); }

/* draw a loaded asset with the given world matrix (bone matrices optional) */
static void DrawAsset(Asset *a, Matrix world, const Matrix *boneM, Color tint)
{
    Matrix M = MatrixMultiply(a->fix, world);
    if (a->skinned && boneM) {
        Shader s = shSkin;
        int loc = s.locs[ENH_LOC_BONES];
#if RAYLIB_VERSION_MAJOR < 6
        for (int m = 0; m < a->model.meshCount; m++) if (a->model.meshes[m].boneMatrices) {
            int bc = a->model.meshes[m].boneCount < a->boneCount ? a->model.meshes[m].boneCount : a->boneCount;
            memcpy(a->model.meshes[m].boneMatrices, boneM, sizeof(Matrix)*bc);
        }
#endif
        if (loc >= 0) { rlEnableShader(s.id); rlSetUniformMatrices(loc, boneM, a->boneCount); }
    } else if (a->skinned) {
        static Matrix ident[ENH_MAX_BONES]; static bool init = false;
        if (!init) { for (int i = 0; i < ENH_MAX_BONES; i++) ident[i] = MatrixIdentity(); init = true; }
        int loc = shSkin.locs[ENH_LOC_BONES];
#if RAYLIB_VERSION_MAJOR < 6
        for (int m = 0; m < a->model.meshCount; m++) if (a->model.meshes[m].boneMatrices) memcpy(a->model.meshes[m].boneMatrices, ident, sizeof(Matrix)*a->model.meshes[m].boneCount);
#endif
        if (loc >= 0) { rlEnableShader(shSkin.id); rlSetUniformMatrices(loc, ident, a->boneCount); }
    }
    for (int m = 0; m < a->model.meshCount; m++) {
        Material *mat = &a->model.materials[a->model.meshMaterial[m]];
        Color keep = mat->maps[MATERIAL_MAP_DIFFUSE].color;
        mat->maps[MATERIAL_MAP_DIFFUSE].color = (Color){ (unsigned char)(keep.r*tint.r/255), (unsigned char)(keep.g*tint.g/255), (unsigned char)(keep.b*tint.b/255), (unsigned char)(keep.a*tint.a/255) };
        DrawMesh(a->model.meshes[m], *mat, M);
        mat->maps[MATERIAL_MAP_DIFFUSE].color = keep;
    }
}

/* ------------------------------------------------------------------ */
/* characters                                                          */
/* ------------------------------------------------------------------ */
static int CharRole(int variant) { return variant >= 0 && variant <= 4 ? RO_GUARD_SOLDIER + variant : RO_GUARD_SOLDIER; }
static int HeldWeaponRole(int weapon, bool silenced)
{
    if (weapon == W_KF7) return RO_WEAPON_KF7;
    if (weapon == W_GOLDEN) return RO_WEAPON_GOLDEN;
    return silenced ? RO_WEAPON_PP7S : RO_WEAPON_PP7;
}

static void AnimReset(Animator *an, int role)
{
    memset(an, 0, sizeof(*an));
    an->role = role;
    an->base.clip = CL_IDLE; an->base.prevClip = -1; an->base.fade = 1;
    an->upper.clip = CL_AIM; an->upper.prevClip = -1; an->upper.fade = 1;
}

/* drive a character animator from gameplay state (called once per frame, not per view) */
static void AnimCharUpdate(Animator *an, const CharDraw *c, float reload01, float dt)
{
    int role = CharRole(c->variant);
    if (an->role != role) AnimReset(an, role);
    Asset *a = &assets[role];
    if (!a->ok || !a->anims) return;
    float rate = 1, prevRate = 1;
    if (c->dead) {
        if (an->base.clip != CL_DEATH) LayerSet(&an->base, CL_DEATH, true);
        an->base.t = c->death*a->clipRate[CL_DEATH];   /* synced to the gameplay death timer */
        an->base.prevT += dt; an->base.fade = fminf(1, an->base.fade + dt/XFADE);
        an->upperW = fmaxf(0, an->upperW - dt*6);
        an->dead = true;
        return;
    }
    if (an->dead) { AnimReset(an, role); }
    float sp = c->speed;
    int want = CL_IDLE;
    if (sp > 0.25f) want = (sp > (a->walkSpeed + a->runSpeed)*0.5f) ? CL_RUN : CL_WALK;
    if (want != an->base.clip) {
        /* keep the foot phase when switching between walk and run */
        float ph = 0;
        if ((an->base.clip == CL_WALK || an->base.clip == CL_RUN) && (want == CL_WALK || want == CL_RUN)) {
            float d = ClipDuration(a, a->clip[an->base.clip]);
            if (d > 0) ph = fmodf(an->base.t, d)/d;
        }
        LayerSet(&an->base, want, false);
        if (ph > 0) an->base.t = ph*ClipDuration(a, a->clip[want]);
    }
    if (want == CL_WALK) rate = Clamp(sp/a->walkSpeed, 0.4f, 1.8f);
    else if (want == CL_RUN) rate = Clamp(sp/a->runSpeed, 0.6f, 1.6f);
    rate *= a->clipRate[want];
    prevRate = rate;
    LayerAdvance(&an->base, dt, rate, prevRate);
    /* upper body: aim / shoot / reload */
    if (c->muzzle > an->lastMuzzle + 0.01f) LayerSet(&an->upper, CL_SHOOT, true);
    an->lastMuzzle = c->muzzle;
    if (reload01 > 0 && reload01 < 1) {
        if (an->upper.clip != CL_RELOAD) LayerSet(&an->upper, CL_RELOAD, true);
        an->upper.t = reload01*ClipDuration(a, a->clip[CL_RELOAD]);
        an->upper.prevT += dt; an->upper.fade = fminf(1, an->upper.fade + dt/XFADE);
    } else {
        if (an->upper.clip == CL_RELOAD) LayerSet(&an->upper, CL_AIM, false);
        if (an->upper.clip == CL_SHOOT && an->upper.t > ClipDuration(a, a->clip[CL_SHOOT])) LayerSet(&an->upper, CL_AIM, false);
        LayerAdvance(&an->upper, dt, a->clipRate[an->upper.clip], 1);
    }
    float target = (reload01 > 0 && reload01 < 1) ? 1.0f : Clamp(c->aim, 0, 1);
    if (an->upper.clip == CL_SHOOT) target = 1;
    an->upperW += (target - an->upperW)*fminf(1, dt*8);
}

static void DrawSoftShadow(Vector3 p, float r, float a) { DrawBlobShadow(p, r, a); }

static void FlashAt(Camera3D cam, Vector3 mp, float size)
{
    rlDrawRenderBatchActive();
    BeginBlendMode(BLEND_ADDITIVE);
    rlDisableDepthMask();
    DrawBillboard(cam, tex[TX_FLASH], mp, size, WHITE);
    DrawBillboard(cam, tex[TX_SOFT], mp, size*2.6f, (Color){ 255, 170, 60, 120 });
    rlDrawRenderBatchActive();
    rlEnableDepthMask();
    EndBlendMode();
}

/* returns false when the role has no model, so the caller draws the classic character */
static bool EnhDrawCharacter(const CharDraw *c, Camera3D cam, int slot, int weapon, bool silenced)
{
    Asset *a = Use(CharRole(c->variant));
    if (!a) return false;
    Animator tmp, *an = (slot >= 0 && slot < ANIM_SLOTS) ? &animChar[slot] : NULL;
    if (!an) { AnimReset(&tmp, CharRole(c->variant)); an = &tmp; }
    Matrix boneM[ENH_MAX_BONES]; Transform glob[ENH_MAX_BONES];
    bool posed = a->anims && a->boneCount > 0;
    if (posed) EvalPose(a, an, boneM, glob);
    Matrix world = MatrixMultiply(MatrixRotateY(-c->yaw), MatrixTranslate(c->pos.x, 0, c->pos.z));
    Vector3 extra = c->flash > 0 ? (Vector3){ 1.4f, 1.3f, 1.2f } : (Vector3){ 0 };
    Shader s = a->skinned ? shSkin : shStatic; const EnhLocs *lk = a->skinned ? &lkSkin : &lkStatic;
    ModelLights(s, lk, (Vector3){ c->pos.x, 1.2f, c->pos.z }, extra, false, NULL, NULL);
    ModelSurface(s, lk, 0.22f, 14, 0.5f);
    DrawAsset(a, world, posed ? boneM : NULL, WHITE);
    Matrix charM = MatrixMultiply(a->fix, world);
    /* feet / hips in world space for the contact shadows */
    an->feetOk = false;
    if (posed) {
        if (a->footL >= 0 && a->footR >= 0) {
            an->footW[0] = Vector3Transform(glob[a->footL].translation, charM);
            an->footW[1] = Vector3Transform(glob[a->footR].translation, charM);
            an->feetOk = true;
        }
        an->hipW = Vector3Transform(glob[a->order[0]].translation, charM);
    } else an->hipW = c->pos;
    /* weapon in the hand */
    if (!c->dead || c->death < 0.35f) {
        int wr = c->golden ? RO_WEAPON_GOLDEN : HeldWeaponRole(weapon, silenced);
        Asset *w = Use(wr);
        if (w && posed && a->attachBone >= 0) {
            int g = a->attachBone;
            Quaternion bq = MDL_BIND(a->model)[g].rotation;
            Matrix sock = MatrixMultiply(MatrixMultiply(QuaternionToMatrix(QuaternionInvert(bq)), TrsMatrix(glob[g])), charM);
            Shader ws = w->skinned ? shSkin : shStatic; const EnhLocs *wl = w->skinned ? &lkSkin : &lkStatic;
            ModelLights(ws, wl, (Vector3){ c->pos.x, 1.2f, c->pos.z }, extra, false, NULL, NULL);
            ModelSurface(ws, wl, c->golden ? 1.1f : 0.7f, c->golden ? 60 : 40, 0.3f);
            if (c->golden) ModelEmissive(ws, wl, (Vector3){ 0.08f, 0.06f, 0.0f });
            DrawAsset(w, sock, NULL, WHITE);
            if (c->golden) ModelEmissive(ws, wl, (Vector3){ 0 });
            if (c->muzzle > 0 && !c->dead) FlashAt(cam, Vector3Transform(w->muzzle, MatrixMultiply(w->fix, sock)), 0.5f);
        } else if (c->muzzle > 0 && !c->dead && posed && a->attachBone >= 0) {
            Matrix sock = MatrixMultiply(TrsMatrix(glob[a->attachBone]), charM);
            FlashAt(cam, Vector3Transform((Vector3){ 0, 0.05f, 0.7f }, sock), 0.5f);
        }
    }
    /* soft contact shadows: a wide body blob plus a small blob under each foot */
    rlDrawRenderBatchActive();
    rlDisableDepthMask();
    BeginBlendMode(BLEND_ALPHA);
    Vector3 hp = { an->hipW.x, 0, an->hipW.z };
    if (c->dead) DrawSoftShadow(hp, 1.05f, 0.42f);
    else {
        DrawSoftShadow(hp, 0.75f, 0.32f);
        if (an->feetOk) for (int k = 0; k < 2; k++) {
            float h = Clamp(an->footW[k].y, 0, 0.5f);
            DrawSoftShadow((Vector3){ an->footW[k].x, 0, an->footW[k].z }, 0.24f + h*0.3f, 0.36f*(1 - h*1.6f));
        }
    }
    EndBlendMode();
    rlDrawRenderBatchActive();
    rlEnableDepthMask();
    return true;
}

/* ------------------------------------------------------------------ */
/* props                                                               */
/* ------------------------------------------------------------------ */
static int PropRole(int type)
{
    switch (type) {
        case PR_CRATE: case PR_CRATESTACK: return RO_PROP_CRATE;
        case PR_BARREL: return RO_PROP_BARREL;
        case PR_DESK: return RO_PROP_DESK;
        case PR_RACK: return RO_PROP_RACK;
        default: return -1;
    }
}
static bool PropTypeEnhanced(int type) { int r = PropRole(type); return r >= 0 && Use(r) != NULL; }
static int propLightCache[MAX_PROPS][7];
static void ResetPropLightCache(void) { for (int i = 0; i < MAX_PROPS; i++) propLightCache[i][6] = -1; }

static void DrawOneProp(Asset *a, int pi, Matrix world)
{
    Prop *p = &props[pi];
    ModelLights(a->skinned ? shSkin : shStatic, a->skinned ? &lkSkin : &lkStatic, (Vector3){ p->pos.x, 1.0f, p->pos.z }, (Vector3){ 0 }, true, propLightCache[pi], &propLightCache[pi][6]);
    DrawAsset(a, world, NULL, WHITE);
}
static void EnhDrawProps(void)
{
    if (!gEnh) return;
    for (int i = 0; i < numProps; i++) {
        Prop *p = &props[i];
        Asset *a = Use(PropRole(p->type));
        if (!a) continue;
        float spec = p->type == PR_BARREL || p->type == PR_RACK ? 0.55f : p->type == PR_DESK ? 0.3f : 0.12f;
        ModelSurface(a->skinned ? shSkin : shStatic, a->skinned ? &lkSkin : &lkStatic, spec, p->type == PR_CRATE || p->type == PR_CRATESTACK ? 10 : 30, 0.9f);
        Matrix base = MatrixMultiply(MatrixRotateY(p->rot), MatrixTranslate(p->pos.x, 0, p->pos.z));
        switch (p->type) {
            case PR_CRATESTACK: {
                DrawOneProp(a, i, MatrixMultiply(MatrixScale(1.2f/1.1f, 1.2f/1.1f, 1.2f/1.1f), base));
                Matrix top = MatrixMultiply(MatrixMultiply(MatrixScale(0.85f/1.1f, 0.85f/1.1f, 0.85f/1.1f), MatrixTranslate(0, 1.2f, 0)),
                                            MatrixMultiply(MatrixRotateY(p->rot + 0.45f), MatrixTranslate(p->pos.x + 0.05f, 0, p->pos.z - 0.04f)));
                DrawOneProp(a, i, top);
            } break;
            case PR_RACK: {
                /* the model's front faces +Z; turn it round when it stands against a wall on the +Z side */
                bool backWall = p->pos.z > (ToTile(p->pos.z) + 0.5f)*TILE;
                DrawOneProp(a, i, backWall ? MatrixMultiply(MatrixRotateY(PI), base) : base);
            } break;
            default: DrawOneProp(a, i, base); break;
        }
    }
}

/* ------------------------------------------------------------------ */
/* pickups (weapon models)                                             */
/* ------------------------------------------------------------------ */
static bool EnhDrawPickupWeapon(int type, Vector3 p, float spin, float hover, float yaw, Vector3 L)
{
    int role = type == PK_GOLDEN ? RO_WEAPON_GOLDEN : type == PK_KF7 ? RO_WEAPON_KF7 : -1;
    Asset *a = Use(role);
    if (!a) return false;
    (void)L;
    Shader s = a->skinned ? shSkin : shStatic; const EnhLocs *lk = a->skinned ? &lkSkin : &lkStatic;
    ModelLights(s, lk, (Vector3){ p.x, 0.8f, p.z }, (Vector3){ 0.12f, 0.12f, 0.12f }, false, NULL, NULL);
    Matrix M;
    if (type == PK_GOLDEN) {
        ModelSurface(s, lk, 1.2f, 64, 0.3f);
        ModelEmissive(s, lk, (Vector3){ 0.22f, 0.16f, 0.04f });
        M = MatrixMultiply(MatrixMultiply(MatrixScale(1.7f, 1.7f, 1.7f), MatrixRotateY(spin)), MatrixTranslate(p.x, hover + 0.30f, p.z));
    } else {
        ModelSurface(s, lk, 0.7f, 40, 0.3f);
        /* lie the rifle on its side on the floor */
        M = MatrixMultiply(MatrixMultiply(MatrixMultiply(MatrixRotateZ(PI*0.5f), MatrixTranslate(0, 0.045f, -0.25f)), MatrixRotateY(yaw)), MatrixTranslate(p.x, 0.0f, p.z));
    }
    DrawAsset(a, M, NULL, WHITE);
    ModelEmissive(s, lk, (Vector3){ 0 });
    return true;
}

/* ------------------------------------------------------------------ */
/* first-person viewmodels                                             */
/* ------------------------------------------------------------------ */
static int ViewRole(const Player *p)
{
    if (p->weapon == W_KF7) return RO_VIEW_KF7;
    if (p->weapon == W_GOLDEN) return RO_VIEW_GOLDEN;
    return PlayerSilenced((Player *)p) ? RO_VIEW_PP7S : RO_VIEW_PP7;
}
static void AnimViewUpdate(int pi, Player *p, float dt)
{
    Animator *an = &animView[pi];
    int role = ViewRole(p);
    if (an->role != role || !an->base.fade) { if (an->role != role) { AnimReset(an, role); an->lastMuzzle = p->muzzle; } }
    Asset *a = &assets[role];
    if (!a->ok || !a->anims) return;
    const WeaponDef *w = &WEAPONS[p->weapon];
    if (p->reloadTimer > 0) {
        if (an->base.clip != CL_RELOAD) LayerSet(&an->base, CL_RELOAD, true);
        an->base.t = Clamp(1.0f - p->reloadTimer/w->reloadTime, 0, 1)*ClipDuration(a, a->clip[CL_RELOAD]);
        an->base.prevT += dt; an->base.fade = fminf(1, an->base.fade + dt/0.1f);
    } else {
        if (p->muzzle > an->lastMuzzle + 0.01f) LayerSet(&an->base, CL_SHOOT, true);
        if (an->base.clip == CL_RELOAD) LayerSet(&an->base, CL_IDLE, false);
        if (an->base.clip == CL_SHOOT && an->base.t > ClipDuration(a, a->clip[CL_SHOOT])) LayerSet(&an->base, CL_IDLE, false);
        float r = an->base.clip == CL_SHOOT ? a->clipRate[CL_SHOOT]*(w->automatic ? 1.3f : 1.0f) : a->clipRate[an->base.clip];
        an->base.t += dt*r; an->base.prevT += dt;
        an->base.fade = fminf(1, an->base.fade + dt/(an->base.clip == CL_SHOOT ? 0.04f : XFADE));
    }
    an->lastMuzzle = p->muzzle;
}

static bool EnhDrawViewModel(Player *p, Camera3D cam, int pi)
{
    if (!p->alive) return true;
    Asset *a = Use(ViewRole(p));
    if (!a) return false;
    rlDrawRenderBatchActive();
    glClear(GL_DEPTH_BUFFER_BIT_);
    Vector3 f = Vector3Normalize(Vector3Subtract(cam.target, cam.position));
    Vector3 r = Vector3Normalize(Vector3CrossProduct(f, (Vector3){ 0, 1, 0 }));
    Vector3 u = Vector3CrossProduct(r, f);
    Vector3 e = cam.position;
    Matrix V = { r.x, u.x, -f.x, e.x,  r.y, u.y, -f.y, e.y,  r.z, u.z, -f.z, e.z,  0, 0, 0, 1 };
    float bx = sinf(p->bob*0.5f)*0.010f*p->moveAmt, by = -fabsf(cosf(p->bob*0.5f))*0.009f*p->moveAmt;
    float low = (1.0f - p->raise); low = low*low;
    float kick = p->kick*p->kick;
    bool rifle = p->weapon == W_KF7;
    Matrix sway = MatrixMultiply(MatrixMultiply(MatrixRotateX(-low*0.6f + kick*(rifle ? 0.015f : 0.04f)), MatrixRotateZ(sinf(p->bob*0.5f)*0.012f*p->moveAmt)),
                                 MatrixTranslate(bx, by - low*0.18f, kick*0.01f));
    Matrix world = MatrixMultiply(sway, V);
    Animator *an = &animView[pi & 3];
    Matrix boneM[ENH_MAX_BONES]; Transform glob[ENH_MAX_BONES];
    bool posed = a->anims && a->boneCount > 0 && an->role == ViewRole(p);
    if (posed) EvalPose(a, an, boneM, glob);
    Shader s = a->skinned ? shSkin : shStatic; const EnhLocs *lk = a->skinned ? &lkSkin : &lkStatic;
    gLightScale = 0.55f;
    ModelLights(s, lk, Vector3Add(e, Vector3Scale(f, 0.4f)), (Vector3){ 0.06f, 0.06f, 0.06f }, false, NULL, NULL);
    gLightScale = 1.0f;
    bool golden = p->weapon == W_GOLDEN;
    ModelSurface(s, lk, golden ? 0.7f : 0.18f, golden ? 48 : 20, 0.4f);
    if (golden) ModelEmissive(s, lk, (Vector3){ 0.05f, 0.04f, 0.0f });
    DrawAsset(a, world, posed ? boneM : NULL, WHITE);
    ModelEmissive(s, lk, (Vector3){ 0 });
    if (p->muzzle > 0) {
        Matrix M = MatrixMultiply(a->fix, world);
        Vector3 mp;
        if (posed && a->attachBone >= 0) {
            int g = a->attachBone;
            Matrix sock = MatrixMultiply(QuaternionToMatrix(QuaternionInvert(MDL_BIND(a->model)[g].rotation)), TrsMatrix(glob[g]));
            mp = Vector3Transform(Vector3Transform(a->muzzle, sock), M);
        } else mp = Vector3Transform(a->muzzle, M);
        bool sil = PlayerSilenced(p);
        float sz = rifle ? 0.10f : sil ? 0.03f : 0.075f;
        Vector3 ax = Vector3Add(Vector3Scale(r, cosf(p->flashRot)), Vector3Scale(u, sinf(p->flashRot)));
        Vector3 ay = Vector3Add(Vector3Scale(r, -sinf(p->flashRot)), Vector3Scale(u, cosf(p->flashRot)));
        rlDrawRenderBatchActive();
        BeginBlendMode(BLEND_ADDITIVE);
        rlDisableDepthMask();
        rlDisableBackfaceCulling();
        rlSetTexture(tex[TX_FLASH].id);
        rlBegin(RL_QUADS);
        for (int k = 0; k < 2; k++) {
            float ss = k ? sz*1.8f : sz;
            Vector3 c0 = Vector3Add(mp, Vector3Scale(Vector3Add(Vector3Negate(ax), Vector3Negate(ay)), ss));
            Vector3 c1 = Vector3Add(mp, Vector3Scale(Vector3Subtract(ax, ay), ss));
            Vector3 c2 = Vector3Add(mp, Vector3Scale(Vector3Add(ax, ay), ss));
            Vector3 c3 = Vector3Add(mp, Vector3Scale(Vector3Subtract(ay, ax), ss));
            rlColor4ub(255, 255, 255, k ? 120 : 255);
            rlTexCoord2f(0, 1); rlVertex3f(c0.x, c0.y, c0.z);
            rlTexCoord2f(1, 1); rlVertex3f(c1.x, c1.y, c1.z);
            rlTexCoord2f(1, 0); rlVertex3f(c2.x, c2.y, c2.z);
            rlTexCoord2f(0, 0); rlVertex3f(c3.x, c3.y, c3.z);
        }
        rlEnd();
        rlSetTexture(0);
        rlDrawRenderBatchActive();
        rlEnableBackfaceCulling();
        rlEnableDepthMask();
        EndBlendMode();
    }
    return true;
}

/* ------------------------------------------------------------------ */
/* per-view uniforms (called from SetupViewLights)                     */
/* ------------------------------------------------------------------ */
static void EnhSetupView(Camera3D cam, const float *pos, const float *col, int n)
{
    if (!enhShadersOk) return;
    Shader all[3] = { shSkin, shStatic, shLevelEnh };
    /* light-tinted fog: the fog picks up a little of the colour of lights near the viewer */
    Vector3 tint = { 0 };
    for (int i = 0; i < numLights; i++) {
        float d = Vector3Distance(lights[i].pos, cam.position);
        if (d > lights[i].radius) continue;
        float att = 1 - d/lights[i].radius; att *= att;
        tint = Vector3Add(tint, Vector3Scale(lights[i].col, att*0.018f));
    }
    for (int i = 0; i < n; i++) tint = Vector3Add(tint, (Vector3){ col[i*4]*0.01f, col[i*4 + 1]*0.01f, col[i*4 + 2]*0.01f });
    tint = Vector3Min(tint, (Vector3){ 0.06f, 0.06f, 0.06f });
    for (int k = 0; k < 3; k++) {
        Shader s = all[k];
        if (s.id == 0) continue;
        if (k == 2 && !(gEnh && levelEnhOk)) continue;
        SetShaderValueV(s, GetShaderLocation(s, "dynPos"), pos, SHADER_UNIFORM_VEC4, 4);
        SetShaderValueV(s, GetShaderLocation(s, "dynCol"), col, SHADER_UNIFORM_VEC4, 4);
        SetShaderValue(s, GetShaderLocation(s, "dynCount"), &n, SHADER_UNIFORM_INT);
        SetShaderValue(s, GetShaderLocation(s, "viewPos"), &cam.position, SHADER_UNIFORM_VEC3);
        EnhLocs *lk = k == 0 ? &lkSkin : k == 1 ? &lkStatic : &lkLevel;
        SetShaderValue(s, lk->fogTint, &tint, SHADER_UNIFORM_VEC3);
    }
    if (gEnh && levelEnhOk) {
        /* the level uses the visible static lights nearest the viewer for relief + specular */
        ModelLights(shLevelEnh, &lkLevel, cam.position, (Vector3){ 0 }, false, NULL, NULL);
    }
}

/* ------------------------------------------------------------------ */
/* bloom (bright-pass + separable blur at quarter resolution)           */
/* ------------------------------------------------------------------ */
static void EnsureBloomTargets(int w, int h)
{
#if RAYLIB_VERSION_MAJOR >= 6
    if (!bloomOk || w != rtW || h != rtH) {
        if (rtW) { UnloadRenderTexture(rtScene); UnloadRenderTexture(rtBloomA); UnloadRenderTexture(rtBloomB); }
        rtScene = LoadRenderTexture(w, h);
        rtBloomA = LoadRenderTexture(w/4, h/4);
        rtBloomB = LoadRenderTexture(w/4, h/4);
        SetTextureFilter(rtScene.texture, TEXTURE_FILTER_BILINEAR);
        SetTextureFilter(rtBloomA.texture, TEXTURE_FILTER_BILINEAR);
        SetTextureFilter(rtBloomB.texture, TEXTURE_FILTER_BILINEAR);
        rtW = w; rtH = h;
        bloomOk = rtScene.id > 0 && rtBloomA.id > 0 && rtBloomB.id > 0 && shBright.id > 0 && shBlur.id > 0;
    }
#else
    (void)w; (void)h; (void)rtScene; (void)rtBloomA; (void)rtBloomB; (void)rtW; (void)rtH; (void)bloomOk;   /* no rlBlitFramebuffer before raylib 6 */
#endif
}
/* call inside BeginDrawing() after the 3D scene, before the HUD */
static void EnhBloom(void)
{
#if RAYLIB_VERSION_MAJOR >= 6
    if (!gEnh) return;
    int w = GetRenderWidth(), h = GetRenderHeight();
    EnsureBloomTargets(w, h);
    if (!bloomOk) return;
    rlDrawRenderBatchActive();
    /* resolve the (multisampled) back buffer into a texture */
    rlBindFramebuffer(RL_READ_FRAMEBUFFER, 0);
    rlBindFramebuffer(RL_DRAW_FRAMEBUFFER, rtScene.id);
    rlBlitFramebuffer(0, 0, w, h, 0, 0, w, h, 0x00004000);
    rlBindFramebuffer(0x8D40, 0);   /* GL_FRAMEBUFFER */
    int bw = w/4, bh = h/4;
    Rectangle src = { 0, 0, (float)w, (float)-h };
    BeginTextureMode(rtBloomA);
    ClearBackground(BLACK);
    BeginShaderMode(shBright);
    float texel[2] = { 1.0f/w, 1.0f/h };
    SetShaderValue(shBright, locTexel, texel, SHADER_UNIFORM_VEC2);
    DrawTexturePro(rtScene.texture, src, (Rectangle){ 0, 0, (float)bw, (float)bh }, (Vector2){ 0 }, 0, WHITE);
    EndShaderMode();
    EndTextureMode();
    for (int pass = 0; pass < 2; pass++) {
        float d1[2] = { 1.0f/bw, 0 }, d2[2] = { 0, 1.0f/bh };
        BeginTextureMode(rtBloomB);
        BeginShaderMode(shBlur);
        SetShaderValue(shBlur, locDir, d1, SHADER_UNIFORM_VEC2);
        DrawTextureRec(rtBloomA.texture, (Rectangle){ 0, 0, (float)bw, (float)-bh }, (Vector2){ 0 }, WHITE);
        EndShaderMode();
        EndTextureMode();
        BeginTextureMode(rtBloomA);
        BeginShaderMode(shBlur);
        SetShaderValue(shBlur, locDir, d2, SHADER_UNIFORM_VEC2);
        DrawTextureRec(rtBloomB.texture, (Rectangle){ 0, 0, (float)bw, (float)-bh }, (Vector2){ 0 }, WHITE);
        EndShaderMode();
        EndTextureMode();
    }
    /* EndTextureMode restored the screen; composite additively */
    BeginBlendMode(BLEND_ADDITIVE);
    DrawTexturePro(rtBloomA.texture, (Rectangle){ 0, 0, (float)bw, (float)-bh }, (Rectangle){ 0, 0, (float)GetScreenWidth(), (float)GetScreenHeight() }, (Vector2){ 0 }, 0, (Color){ 150, 140, 125, 255 });
    EndBlendMode();
#else
    EnsureBloomTargets(0, 0);   /* bloom needs raylib 6.x */
#endif
}

/* ------------------------------------------------------------------ */
/* settings, toggle, init, per-frame update                            */
/* ------------------------------------------------------------------ */
static const char *SettingsPath(void) { static char p[600]; snprintf(p, sizeof(p), "%ssettings.cfg", GetApplicationDirectory()); return p; }
static bool LoadGraphicsSetting(void)
{
    bool enh = true;   /* default: Enhanced */
    if (!FileExists(SettingsPath())) return enh;
    char *t = LoadFileText(SettingsPath());
    if (t) {
        for (char *line = t; line && *line; ) {   /* first non-comment "graphics = ..." line */
            char *nl = strchr(line, '\n'); if (nl) *nl = 0;
            char *l = TrimStr(line);
            if (*l != '#' && *l != ';' && !strncmp(l, "graphics", 8)) {
                char *eq = strchr(l, '=');
                if (eq) { char *v = TrimStr(eq + 1); enh = strncmp(v, "classic", 7) != 0; break; }
            }
            line = nl ? nl + 1 : NULL;
        }
        UnloadFileText(t);
    }
    return enh;
}
static void SaveGraphicsSetting(void)
{
    char buf[256];
    snprintf(buf, sizeof(buf), "# Facility 64 settings (written by the game)\n# graphics = enhanced | classic   (toggle in game with F2)\ngraphics = %s\n", gEnh ? "enhanced" : "classic");
    if (!SaveFileText(SettingsPath(), buf)) TraceLog(LOG_WARNING, "ENHANCED: could not write %s", SettingsPath());
}
static void AnnounceMode(void)
{
    char b[128];
    if (gEnh) {
        int missing = enhConfigured - enhLoaded;
        if (!ENH_SUPPORTED) snprintf(b, sizeof(b), "Graphics: Enhanced unavailable (needs raylib 5.5+)");
        else if (enhLoaded == 0) snprintf(b, sizeof(b), "Graphics: Enhanced (F2) - no models found, classic models");
        else if (missing > 0) snprintf(b, sizeof(b), "Graphics: Enhanced (F2) - %d model%s missing, using classic", missing, missing == 1 ? "" : "s");
        else snprintf(b, sizeof(b), "Graphics: Enhanced (F2)");
    } else snprintf(b, sizeof(b), "Graphics: Classic (F2)");
    Toast(b);
}
static void SetEnhanced(bool on, bool save)
{
    gEnh = on && ENH_SUPPORTED && enhShadersOk;
    ApplyLevelShader();
    for (int i = 0; i < ANIM_SLOTS; i++) animChar[i].role = -1;
    for (int i = 0; i < 4; i++) animView[i].role = -1;
    if (save) SaveGraphicsSetting();
}

static void InitEnhanced(void)
{
    shClassic = gShader;
    for (int i = 0; i < ANIM_SLOTS; i++) animChar[i].role = -1;
    for (int i = 0; i < 4; i++) animView[i].role = -1;
    ResetPropLightCache();
    if (!ENH_SUPPORTED || !shaderOk) { enhShadersOk = false; LoadManifest(); gEnh = false; return; }
    shSkin = BuildShader("#define MODEL\n#define SKINNED\n", &lkSkin);
    shStatic = BuildShader("#define MODEL\n", &lkStatic);
    shLevelEnh = BuildShader("#define LEVEL\n", &lkLevel);
    enhShadersOk = shSkin.id > 0 && shStatic.id > 0;
    levelEnhOk = shLevelEnh.id > 0;
    if (!enhShadersOk) TraceLog(LOG_WARNING, "ENHANCED: model shaders failed to compile - Enhanced mode disabled");
    shBright = LoadShaderFromMemory(BLOOM_VS, BRIGHT_FS);
    shBlur = LoadShaderFromMemory(BLOOM_VS, BLUR_FS);
    locTexel = GetShaderLocation(shBright, "texel");
    locDir = GetShaderLocation(shBlur, "dir");
    BuildHiResTextures();
    LoadManifest();
    LoadAllAssets();
    TraceLog(LOG_INFO, "ENHANCED: %d/%d models loaded (%d failed)", enhLoaded, enhConfigured, enhFailed);
    SetEnhanced(LoadGraphicsSetting(), false);
}

static void EnhReload(void)
{
    if (!ENH_SUPPORTED || !enhShadersOk) { Toast("Enhanced mode unavailable"); return; }
    UnloadAllAssets();
    LoadManifest();
    LoadAllAssets();
    ResetPropLightCache();
    for (int i = 0; i < ANIM_SLOTS; i++) animChar[i].role = -1;
    for (int i = 0; i < 4; i++) animView[i].role = -1;
    char b[128]; snprintf(b, sizeof(b), "Models reloaded: %d/%d (F3)", enhLoaded, enhConfigured);
    Toast(b);
}

static CharDraw EnemyDraw(Enemy *e);
static CharDraw PlayerCharDraw(Player *p);
static void EnhUpdate(float dt)
{
    if (gToastT > 0) gToastT -= dt;
    if (IsKeyPressed(KEY_F2)) { SetEnhanced(!gEnh, true); AnnounceMode(); }
    if (IsKeyPressed(KEY_F3)) EnhReload();
    if (!gEnh) return;
    if (gState != GS_DM) {
        for (int i = 0; i < numEnemies; i++) { CharDraw c = EnemyDraw(&enemies[i]); AnimCharUpdate(&animChar[i], &c, 0, dt); }
    } else {
        for (int i = 0; i < numPlayers && i < 4; i++) {
            CharDraw c = PlayerCharDraw(&players[i]);
            float r01 = players[i].reloadTimer > 0 ? 1.0f - players[i].reloadTimer/WEAPONS[players[i].weapon].reloadTime : 0;
            AnimCharUpdate(&animChar[MAX_ENEMIES + i], &c, r01, dt);
        }
    }
    for (int i = 0; i < numPlayers && i < 4; i++) AnimViewUpdate(i, &players[i], dt);
}

static void DrawToast(void)
{
    if (gToastT <= 0) return;
    float a = Clamp(gToastT/0.4f, 0, 1);
    int fs = 22, w = MeasureText(gToast, fs);
    int x = GetScreenWidth()/2 - w/2, y = gToastY;
    DrawRectangleRounded((Rectangle){ x - 16.0f, y - 8.0f, w + 32.0f, fs + 16.0f }, 0.4f, 6, Fade(BLACK, 0.65f*a));
    DrawRectangleRoundedLinesEx((Rectangle){ x - 16.0f, y - 8.0f, w + 32.0f, fs + 16.0f }, 0.4f, 6, 1.5f, Fade(GOLD, 0.7f*a));
    DrawText(gToast, x, y, fs, Fade((Color){ 255, 230, 160, 255 }, a));
}

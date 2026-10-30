/* characters.c : THE CHARACTER TABLE + how racers are drawn
 *
 * ===== ADDING YOUR OWN CHARACTER =====
 * 1. Add a new entry to CHARACTERS[] below (copy an existing one).
 *    Stats are 1..5. Weight class affects bumping. Colors are RGBA.
 * 2. (optional) Put a 3D model in assets/characters/ and set modelFile,
 *    e.g. "myhero.glb" (obj / gltf / glb / iqm all work). The model replaces
 *    the primitive driver (the kart is still drawn). Model space: ~1.5 units
 *    tall, facing +Z, origin at the seat. If the file is missing the game
 *    falls back to the primitive look automatically.
 * That's it - menus, AI and Grand Prix pick up new entries automatically
 * (up to MAX_CHARACTERS). A race always uses 8 racers.
 */
#include "common.h"

CharacterDef CHARACTERS[MAX_CHARACTERS] = {
    /* name           tagline                                                    class          spd  acc  hnd  mass  body                 accent               kart                 trim                 head        hat              voice  model */
    { "Biscuit",      "A very good boy. Thinks the finish line is a squirrel.",  WEIGHT_MEDIUM, 3.5f, 3.5f, 3.5f, 3.0f, {230,150, 60,255}, {250,245,235,255}, {215, 40, 40,255}, {255,210, 40,255}, HEAD_BEAR,  HAT_FLOPPY_EARS, 1.15f, NULL },
    { "Prof. Wobble", "Brilliant, jiggly, and 92% gelatin.",                     WEIGHT_LIGHT,  2.5f, 5.0f, 4.5f, 1.5f, { 90,220,110,255}, {240,240,255,255}, {245,245,245,255}, { 60,170, 80,255}, HEAD_CUBE,  HAT_GOGGLES,     1.35f, NULL },
    { "Nana Nitro",   "Knits at 200 km/h. Has never once used the brakes.",      WEIGHT_MEDIUM, 3.5f, 3.5f, 3.0f, 3.0f, {150, 90,200,255}, {255,215,180,255}, {120, 50,170,255}, {255,160,220,255}, HEAD_ROUND, HAT_BUN,         1.25f, NULL },
    { "Captain Crumb","Toasted on one side, terrifying on the other.",           WEIGHT_HEAVY,  4.5f, 2.0f, 2.5f, 4.5f, { 70, 50,120,255}, {225,180,110,255}, {130, 80, 40,255}, {230,190, 50,255}, HEAD_TOAST, HAT_PIRATE,      0.80f, NULL },
    { "Zippy",        "Tiny bee-bot. Runs on honey and pure caffeine.",          WEIGHT_LIGHT,  2.5f, 5.0f, 5.0f, 1.0f, { 40, 40, 40,255}, {255,215, 30,255}, {255,200, 20,255}, { 30, 30, 30,255}, HEAD_ROBOT, HAT_ANTENNA,     1.60f, NULL },
    { "Gloop",        "A royal slime. Leaves a trail. Doesn't apologise.",       WEIGHT_LIGHT,  3.0f, 4.5f, 4.0f, 1.5f, {170, 70,220,255}, {255,230, 60,255}, { 30,190,190,255}, {255,255,255,255}, HEAD_BLOB,  HAT_CROWN,       1.45f, NULL },
    { "Big Tony",     "A pasta-loving bear. Will race for meatballs.",           WEIGHT_HEAVY,  5.0f, 1.5f, 2.0f, 5.0f, {140, 90, 50,255}, {255,255,255,255}, { 30,150, 60,255}, {220, 40, 40,255}, HEAD_BEAR,  HAT_CHEF,        0.70f, NULL },
    { "Frostina",     "Yeti princess of the peaks. Melts hearts, never melts.",  WEIGHT_MEDIUM, 3.5f, 3.0f, 4.0f, 3.0f, {235,245,255,255}, {120,190,255,255}, { 80,170,240,255}, {255,255,255,255}, HEAD_YETI,  HAT_HORNS,       1.05f, NULL },
};
int NUM_CHARACTERS = 8;   /* built-in racers; more are appended from assets/characters/ */

/* ------------------------------------------------------------------ */
/* data-driven characters: assets/characters/<folder>/character.ini     */
/* ------------------------------------------------------------------ */
static char *Dup(const char *s) { size_t n = strlen(s) + 1; char *d = (char *)malloc(n); memcpy(d, s, n); return d; }
static char *Trim(char *s) { while (*s == ' ' || *s == '\t') s++; char *e = s + strlen(s); while (e > s && (e[-1] == ' ' || e[-1] == '\t' || e[-1] == '\r' || e[-1] == '\n')) *--e = 0; return s; }
static Color ParseColor(const char *v, Color def)
{
    int r, g, b;
    if (sscanf(v, "%d , %d , %d", &r, &g, &b) == 3 || sscanf(v, "%d,%d,%d", &r, &g, &b) == 3)
        return (Color){ (unsigned char)Clamp((float)r, 0, 255), (unsigned char)Clamp((float)g, 0, 255), (unsigned char)Clamp((float)b, 0, 255), 255 };
    return def;
}

int gMoodChar = -1;
/* v7 real faces: photo-cropped HD face sprites (tools/make_face.py) shown on the front of the 3D head */
static Texture2D FaceTex[MAX_CHARACTERS], FaceWinTex[MAX_CHARACTERS];

static void LoadCharacterFolder(const char *dir)
{
    if (NUM_CHARACTERS >= MAX_CHARACTERS) return;
    const char *ini = TextFormat("%s/character.ini", dir);
    if (!FileExists(ini)) return;
    char *txt = LoadFileText(ini);
    if (!txt) return;
    CharacterDef cd = CHARACTERS[0];               /* sensible defaults */
    cd.name = Dup(GetFileName(dir));
    cd.tagline = "A custom racer.";
    cd.modelFile = NULL;
    cd.head = HEAD_ROUND; cd.hat = HAT_NONE;
    cd.spriteAngles = 1; cd.spriteSize = 1.35f; cd.spriteRows = 1; cd.kartStyle = KART_STYLE_NONE;
    char sprite[256] = "sprite.png", portrait[256] = "", winsprite[256] = "", decal[256] = "", facephoto[256] = "", facephotowin[256] = "";
    cd.quip = NULL; cd.quipStyle = QUIP_NONE; cd.faceX = 0.5f; cd.faceY = 0.3f;
    for (char *line = txt, *next; line && *line; line = next) {
        next = strchr(line, '\n');
        if (next) *next++ = 0;
        char *l = Trim(line);
        if (!*l || *l == ';' || *l == '#' || *l == '[') continue;
        char *eq = strchr(l, '=');
        if (!eq) continue;
        *eq = 0;
        char *k = Trim(l), *v = Trim(eq + 1);
        if (!strcmp(k, "name")) cd.name = Dup(v);
        else if (!strcmp(k, "tagline")) cd.tagline = Dup(v);
        else if (!strcmp(k, "weight")) cd.weight = !strcmp(v, "light") ? WEIGHT_LIGHT : !strcmp(v, "heavy") ? WEIGHT_HEAVY : WEIGHT_MEDIUM;
        else if (!strcmp(k, "speed")) cd.topSpeed = Clamp((float)atof(v), 1, 5);
        else if (!strcmp(k, "accel")) cd.accel = Clamp((float)atof(v), 1, 5);
        else if (!strcmp(k, "handling")) cd.handling = Clamp((float)atof(v), 1, 5);
        else if (!strcmp(k, "mass")) cd.mass = Clamp((float)atof(v), 1, 5);
        else if (!strcmp(k, "kart")) cd.kart = ParseColor(v, cd.kart);
        else if (!strcmp(k, "trim")) cd.trim = ParseColor(v, cd.trim);
        else if (!strcmp(k, "body")) cd.body = ParseColor(v, cd.body);
        else if (!strcmp(k, "accent")) cd.accent = ParseColor(v, cd.accent);
        else if (!strcmp(k, "voice")) cd.voicePitch = Clamp((float)atof(v), 0.5f, 2.0f);
        else if (!strcmp(k, "sprite")) snprintf(sprite, sizeof sprite, "%s", v);
        else if (!strcmp(k, "angles")) cd.spriteAngles = atoi(v) >= 16 ? 16 : atoi(v) >= 8 ? 8 : 1;
        else if (!strcmp(k, "size")) cd.spriteSize = Clamp((float)atof(v), 0.5f, 3.0f);
        else if (!strcmp(k, "seat")) cd.spriteSeat = Clamp((float)atof(v), -0.5f, 0.8f);
        else if (!strcmp(k, "rows")) cd.spriteRows = (int)Clamp((float)atoi(v), 1, 8);
        else if (!strcmp(k, "portrait")) snprintf(portrait, sizeof portrait, "%s", v);
        else if (!strcmp(k, "kartstyle")) cd.kartStyle = !strcmp(v, "rattle") ? KART_STYLE_RATTLE : !strcmp(v, "spa") ? KART_STYLE_SPA : KART_STYLE_NONE;
        else if (!strcmp(k, "quip")) cd.quip = Dup(v);
        else if (!strcmp(k, "quipstyle")) cd.quipStyle = !strcmp(v, "sleepy") ? QUIP_SLEEPY : !strcmp(v, "happy") ? QUIP_HAPPY : QUIP_NONE;
        else if (!strcmp(k, "winsprite")) snprintf(winsprite, sizeof winsprite, "%s", v);
        else if (!strcmp(k, "decal")) snprintf(decal, sizeof decal, "%s", v);
        else if (!strcmp(k, "facephoto")) snprintf(facephoto, sizeof facephoto, "%s", v);
        else if (!strcmp(k, "facephotowin")) snprintf(facephotowin, sizeof facephotowin, "%s", v);
        else if (!strcmp(k, "decalframes")) cd.decalFrames = Clamp(atoi(v), 1, 8);
        else if (!strcmp(k, "face")) { float fx = 0.5f, fy = 0.3f; if (sscanf(v, "%f , %f", &fx, &fy) == 2) { cd.faceX = Clamp(fx, 0, 1); cd.faceY = Clamp(fy, 0, 1); } }
        else if (!strcmp(k, "model3d")) cd.model3d = !strcmp(v, "eabha") ? 1 : !strcmp(v, "qanna") ? 2 : 0;
        else if (!strcmp(k, "model")) cd.modelFile = Dup(TextFormat("%s/%s", GetFileName(dir), v));
    }
    UnloadFileText(txt);
    int id = NUM_CHARACTERS;
    G.charSprite[id] = (Texture2D){ 0 };
    const char *sp = TextFormat("%s/%s", dir, sprite);
    if (cd.model3d) { portrait[0] = 0; winsprite[0] = 0; }      /* 3D drivers: portrait + win card are rendered from the model */
    if (!cd.model3d && FileExists(sp)) {
        G.charSprite[id] = LoadTexture(sp);
        if (G.charSprite[id].id) {
            GenTextureMipmaps(&G.charSprite[id]);
            SetTextureFilter(G.charSprite[id], TEXTURE_FILTER_TRILINEAR);
            SetTextureWrap(G.charSprite[id], TEXTURE_WRAP_CLAMP);
        }
    }
    if (!G.charSprite[id].id && !cd.modelFile && !cd.model3d) { TraceLog(LOG_WARNING, "CHAR: %s has no sprite or model, skipped", dir); return; }
    if (!G.charSprite[id].id) cd.spriteAngles = 0;
    G.charPortrait[id] = (Texture2D){ 0 };
    if (portrait[0]) {
        const char *pp = TextFormat("%s/%s", dir, portrait);
        if (FileExists(pp)) {
            G.charPortrait[id] = LoadTexture(pp);
            if (G.charPortrait[id].id) { GenTextureMipmaps(&G.charPortrait[id]); SetTextureFilter(G.charPortrait[id], TEXTURE_FILTER_TRILINEAR); }
        }
    }
    G.charWin[id] = (Texture2D){ 0 };
    if (winsprite[0]) {
        const char *wp = TextFormat("%s/%s", dir, winsprite);
        if (FileExists(wp)) {
            G.charWin[id] = LoadTexture(wp);
            if (G.charWin[id].id) { GenTextureMipmaps(&G.charWin[id]); SetTextureFilter(G.charWin[id], TEXTURE_FILTER_TRILINEAR); SetTextureWrap(G.charWin[id], TEXTURE_WRAP_CLAMP); }
        }
    }
    G.charDecal[id] = (Texture2D){ 0 };
    if (decal[0]) {
        const char *dp = TextFormat("%s/%s", dir, decal);
        if (FileExists(dp)) {
            G.charDecal[id] = LoadTexture(dp);
            if (G.charDecal[id].id) { GenTextureMipmaps(&G.charDecal[id]); SetTextureFilter(G.charDecal[id], TEXTURE_FILTER_TRILINEAR); SetTextureWrap(G.charDecal[id], TEXTURE_WRAP_CLAMP); }
        }
    }
    FaceTex[id] = FaceWinTex[id] = (Texture2D){ 0 };
    for (int w = 0; w < 2 && cd.model3d; w++) {
        const char *fn = w ? facephotowin : facephoto;
        if (!fn[0]) continue;
        const char *fp = TextFormat("%s/%s", dir, fn);
        if (!FileExists(fp)) continue;
        Texture2D t = LoadTexture(fp);
        if (!t.id) continue;
        GenTextureMipmaps(&t); SetTextureFilter(t, TEXTURE_FILTER_TRILINEAR); SetTextureWrap(t, TEXTURE_WRAP_CLAMP);
        if (w) FaceWinTex[id] = t; else FaceTex[id] = t;
    }
    if (!FaceWinTex[id].id) FaceWinTex[id] = FaceTex[id];
    if (cd.decalFrames < 1) cd.decalFrames = 1;
    if (cd.quip && cd.quipStyle == QUIP_NONE) cd.quipStyle = QUIP_HAPPY;
    /* menu colours from the kart if not given */
    CHARACTERS[id] = cd;
    NUM_CHARACTERS++;
    if (cd.model3d) TraceLog(LOG_INFO, "CHAR: loaded '%s' from %s (built-in 3D model %d, real face %s)", cd.name, dir, cd.model3d, FaceTex[id].id ? "yes" : "no");
    else TraceLog(LOG_INFO, "CHAR: loaded '%s' from %s (%d angle sprite)", cd.name, dir, cd.spriteAngles);
}

static void LoadCustomCharacters(void)
{
    const char *base = "assets/characters";
    if (!DirectoryExists(base)) return;
    FilePathList fl = LoadDirectoryFiles(base);
    /* sorted so the order is stable */
    for (unsigned i = 0; i < fl.count; i++) for (unsigned j = i + 1; j < fl.count; j++)
        if (strcmp(fl.paths[j], fl.paths[i]) < 0) { char *t = fl.paths[i]; fl.paths[i] = fl.paths[j]; fl.paths[j] = t; }
    for (unsigned i = 0; i < fl.count; i++) if (DirectoryExists(fl.paths[i])) LoadCharacterFolder(fl.paths[i]);
    UnloadDirectoryFiles(fl);
}

static void PrebuildModels(void);
static void MakePortraits(void);
static void MakeWinCards(void);
void CharactersInit(void)
{
    LoadCustomCharacters();
    if (NUM_CHARACTERS > MAX_CHARACTERS) NUM_CHARACTERS = MAX_CHARACTERS;
    for (int i = 0; i < NUM_CHARACTERS; i++) {
        G.charModelLoaded[i] = false;
        if (CHARACTERS[i].modelFile) {
            const char *path = TextFormat("assets/characters/%s", CHARACTERS[i].modelFile);
            if (FileExists(path)) {
                G.charModels[i] = LoadModel(path);
                if (G.charModels[i].meshCount > 0) {
                    G.charModelLoaded[i] = true;
                    for (int m = 0; m < G.charModels[i].materialCount; m++)
                        G.charModels[i].materials[m].shader = G.fogShader;
                }
            } else {
                TraceLog(LOG_WARNING, "Character model %s not found, using primitives", path);
            }
        }
    }
    PrebuildModels();
    MakePortraits();
    MakeWinCards();
    if (G.settings.visualMode == 0) CharactersEnsureSprites();
}

/* ------------------------------------------------------------------ */
/* Cached models. Every racer is baked once per visual mode into a few   */
/* static meshes (chassis, torso, head, wheel, steering wheel) so karts  */
/* cost ~8 draw calls each. ORIGINAL = low-poly with soft bevels,        */
/* ENHANCED = many more segments, fully rounded.                          */
/* ------------------------------------------------------------------ */
typedef struct {
    bool ok;
    Model chassis, driver, head, driverWin, headWin;
    bool hasWin;
    bool hasEyes;
    float eyeY, eyeZ, eyeSpread, eyeSize;
    Color lid;
} KartModels;
static KartModels KM[2][MAX_CHARACTERS];
static Model WheelM[2], SWheelM[2], TrophyM[3];
static bool WheelOk[2], TrophyOk[3];

/* recorded by DrawEyes while baking a head (for blinking lids at draw time) */
static bool recEyes; static float recEyeY, recEyeZ, recEyeSpread, recEyeSize;
static Color gLid;
static bool gPhotoFace;      /* set while baking a head that will wear a photo face: skip the drawn features */

static const float HEAD_Y = 1.62f;

static void DrawEyes(float y, float z, float spread, float size, float t)
{
    (void)t;
    Color white = { 252, 252, 252, 255 }, black = { 22, 20, 34, 255 };
    for (int s = -1; s <= 1; s += 2) {
        float x = s*spread;
        DrawLitSphere((Vector3){ x, y, z }, (Vector3){ size, size*1.18f, size*0.62f }, white, 5, 7);
        DrawLitSphere((Vector3){ x*0.97f, y - size*0.06f, z + size*0.42f }, (Vector3){ size*0.56f, size*0.68f, size*0.32f }, black, 4, 6);
        DrawLitSphere((Vector3){ x*0.97f + size*0.2f, y + size*0.28f, z + size*0.62f }, (Vector3){ size*0.2f, size*0.2f, size*0.1f }, white, 3, 4);
    }
    recEyes = true; recEyeY = y; recEyeZ = z; recEyeSpread = spread; recEyeSize = size;
}

static void DrawSmile(float y, float z, float w)
{
    Color dark = { 60, 25, 30, 255 };
    for (int i = -2; i <= 2; i++) {
        float x = i*w/4.0f;
        DrawLitSphere((Vector3){ x, y + 0.012f*i*i, z - 0.004f*i*i }, (Vector3){ 0.032f, 0.026f, 0.022f }, dark, 3, 5);
    }
}

static void DrawCheeks(float y, float z, float spread)
{
    Color blush = { 255, 140, 150, 255 };
    DrawLitSphere((Vector3){ spread, y, z }, (Vector3){ 0.07f, 0.045f, 0.03f }, blush, 3, 5);
    DrawLitSphere((Vector3){ -spread, y, z }, (Vector3){ 0.07f, 0.045f, 0.03f }, blush, 3, 5);
}

static void DrawHead(const CharacterDef *cd, float t, float hit)
{
    Color body = cd->body, acc = cd->accent;
    Color dark = { 30, 25, 30, 255 };
    float hy = HEAD_Y;
    gLid = body;
    switch (cd->head) {
    case HEAD_ROUND:
        gLid = acc;
        DrawLitSphere((Vector3){ 0, hy, 0 }, (Vector3){ 0.44f, 0.44f, 0.42f }, acc, 7, 10);
        DrawLitSphere((Vector3){ 0.43f, hy, -0.02f }, (Vector3){ 0.07f, 0.11f, 0.07f }, ColorScale(acc, 0.92f), 3, 5);
        DrawLitSphere((Vector3){ -0.43f, hy, -0.02f }, (Vector3){ 0.07f, 0.11f, 0.07f }, ColorScale(acc, 0.92f), 3, 5);
        DrawEyes(hy + 0.07f, 0.33f, 0.15f, 0.095f, t);
        DrawLitSphere((Vector3){ 0, hy - 0.06f, 0.43f }, (Vector3){ 0.07f, 0.06f, 0.05f }, ColorScale(acc, 0.88f), 3, 5); /* nose */
        DrawSmile(hy - 0.2f, 0.39f, 0.16f);
        DrawCheeks(hy - 0.1f, 0.36f, 0.25f);
        /* round glasses */
        for (int s = -1; s <= 1; s += 2) {
            Vector3 c = { s*0.15f, hy + 0.07f, 0.41f };
            for (int q = 0; q < 8; q++) {
                float a0 = 2*PI*q/8, a1 = 2*PI*(q + 1)/8;
                DrawLitTube((Vector3){ c.x + cosf(a0)*0.13f, c.y + sinf(a0)*0.13f, c.z }, (Vector3){ c.x + cosf(a1)*0.13f, c.y + sinf(a1)*0.13f, c.z }, 0.018f, (Color){ 210, 175, 60, 255 });
            }
        }
        DrawLitCapsule((Vector3){ -0.03f, hy + 0.09f, 0.44f }, (Vector3){ 0.03f, hy + 0.09f, 0.44f }, 0.016f, (Color){ 210, 175, 60, 255 });
        break;
    case HEAD_CUBE: {
        DrawLitRoundBox((Vector3){ 0, hy, 0 }, (Vector3){ 0.86f, 0.84f, 0.8f }, 0.24f, 1, 1, ColorScale(body, 1.15f), ColorScale(body, 0.82f));
        DrawLitSphere((Vector3){ 0.2f, hy + 0.3f, 0.28f }, (Vector3){ 0.11f, 0.05f, 0.07f }, ColorMix(body, WHITE, 0.6f), 3, 5); /* jelly shine */
        DrawEyes(hy + 0.1f, 0.4f, 0.18f, 0.115f, t);
        DrawSmile(hy - 0.17f, 0.41f, 0.2f);
    } break;
    case HEAD_TOAST:
        gLid = acc;
        DrawLitRoundBox((Vector3){ 0, hy - 0.02f, 0 }, (Vector3){ 1.0f, 0.86f, 0.26f }, 0.1f, 1, 1, (Color){ 165, 105, 50, 255 }, (Color){ 130, 80, 38, 255 });
        DrawLitSphere((Vector3){ -0.24f, hy + 0.36f, 0 }, (Vector3){ 0.3f, 0.2f, 0.13f }, (Color){ 160, 100, 48, 255 }, 5, 7);
        DrawLitSphere((Vector3){ 0.24f, hy + 0.36f, 0 }, (Vector3){ 0.3f, 0.2f, 0.13f }, (Color){ 160, 100, 48, 255 }, 5, 7);
        DrawLitRoundBox((Vector3){ 0, hy - 0.02f, 0.03f }, (Vector3){ 0.86f, 0.76f, 0.24f }, 0.08f, 1, 1, ColorScale(acc, 1.05f), ColorScale(acc, 0.9f));
        DrawLitSphere((Vector3){ -0.22f, hy + 0.33f, 0.03f }, (Vector3){ 0.25f, 0.16f, 0.12f }, acc, 5, 7);
        DrawLitSphere((Vector3){ 0.22f, hy + 0.33f, 0.03f }, (Vector3){ 0.25f, 0.16f, 0.12f }, acc, 5, 7);
        DrawEyes(hy + 0.08f, 0.15f, 0.18f, 0.105f, t);
        DrawLitRoundBox((Vector3){ 0.18f, hy + 0.09f, 0.2f }, (Vector3){ 0.25f, 0.23f, 0.04f }, 0.08f, 1, 1, dark, dark); /* eye patch */
        DrawLitCapsule((Vector3){ -0.44f, hy + 0.2f, 0.17f }, (Vector3){ 0.44f, hy + 0.02f, 0.17f }, 0.018f, dark);
        DrawSmile(hy - 0.2f, 0.17f, 0.22f);
        break;
    case HEAD_BLOB: {
        DrawLitSphere((Vector3){ 0, hy - 0.05f, 0 }, (Vector3){ 0.55f, 0.45f, 0.5f }, body, 7, 10);
        DrawLitSphere((Vector3){ 0.18f, hy + 0.24f, 0.22f }, (Vector3){ 0.13f, 0.07f, 0.09f }, ColorMix(body, WHITE, 0.55f), 3, 5);
        DrawLitSphere((Vector3){ -0.3f, hy - 0.38f, 0.25f }, (Vector3){ 0.12f, 0.1f, 0.12f }, body, 3, 5);  /* drip */
        DrawEyes(hy + 0.08f, 0.38f, 0.17f, 0.125f, t);
        DrawSmile(hy - 0.17f, 0.44f, 0.2f);
    } break;
    case HEAD_BEAR:
        DrawLitSphere((Vector3){ 0, hy, 0 }, (Vector3){ 0.46f, 0.43f, 0.43f }, body, 7, 10);
        DrawLitSphere((Vector3){ 0, hy - 0.1f, 0.34f }, (Vector3){ 0.23f, 0.17f, 0.17f }, acc, 5, 7);
        DrawLitSphere((Vector3){ 0, hy - 0.03f, 0.5f }, (Vector3){ 0.085f, 0.065f, 0.05f }, dark, 3, 5);
        DrawLitSphere((Vector3){ 0.03f, hy - 0.01f, 0.54f }, (Vector3){ 0.025f, 0.02f, 0.01f }, WHITE, 2, 4);
        DrawSmile(hy - 0.18f, 0.49f, 0.13f);
        DrawEyes(hy + 0.1f, 0.33f, 0.16f, 0.09f, t);
        if (cd->hat != HAT_FLOPPY_EARS) {
            for (int s = -1; s <= 1; s += 2) {
                DrawLitSphere((Vector3){ s*0.33f, hy + 0.34f, -0.02f }, (Vector3){ 0.15f, 0.15f, 0.08f }, body, 4, 6);
                DrawLitSphere((Vector3){ s*0.33f, hy + 0.34f, 0.04f }, (Vector3){ 0.09f, 0.09f, 0.04f }, acc, 3, 5);
            }
        }
        break;
    case HEAD_ROBOT:
        gLid = acc;
        DrawLitRoundBox((Vector3){ 0, hy, 0 }, (Vector3){ 0.76f, 0.62f, 0.66f }, 0.17f, 1, 1, ColorScale(acc, 1.08f), ColorScale(acc, 0.85f));
        DrawLitRoundBox((Vector3){ 0, hy + 0.16f, 0 }, (Vector3){ 0.79f, 0.1f, 0.69f }, 0.05f, 1, 1, body, body);
        DrawLitRoundBox((Vector3){ 0, hy - 0.13f, 0 }, (Vector3){ 0.79f, 0.1f, 0.69f }, 0.05f, 1, 1, body, body);
        DrawLitRoundBox((Vector3){ 0, hy + 0.02f, 0.31f }, (Vector3){ 0.58f, 0.22f, 0.06f }, 0.05f, 1, 1, (Color){ 40, 230, 255, 255 }, (Color){ 20, 150, 200, 255 });
        DrawLitSphere((Vector3){ 0.13f, hy + 0.03f, 0.34f }, (Vector3){ 0.06f, 0.07f, 0.03f }, WHITE, 3, 5);
        DrawLitSphere((Vector3){ -0.13f, hy + 0.03f, 0.34f }, (Vector3){ 0.06f, 0.07f, 0.03f }, WHITE, 3, 5);
        break;
    case HEAD_BIRD:
        DrawLitSphere((Vector3){ 0, hy, 0 }, (Vector3){ 0.42f, 0.42f, 0.42f }, body, 7, 10);
        DrawLitCylinderY((Vector3){ 0, hy - 0.05f, 0.4f }, 0.12f, 0.0f, 0.3f, (Color){ 255, 160, 30, 255 }, 6);
        DrawEyes(hy + 0.12f, 0.3f, 0.16f, 0.09f, t);
        break;
    case HEAD_YETI:
        DrawLitSphere((Vector3){ 0, hy, 0 }, (Vector3){ 0.47f, 0.45f, 0.44f }, body, 7, 10);
        DrawLitSphere((Vector3){ 0.3f, hy + 0.15f, -0.1f }, (Vector3){ 0.22f, 0.22f, 0.22f }, body, 5, 7);
        DrawLitSphere((Vector3){ -0.3f, hy + 0.15f, -0.1f }, (Vector3){ 0.22f, 0.22f, 0.22f }, body, 5, 7);
        DrawLitSphere((Vector3){ 0, hy - 0.02f, 0.28f }, (Vector3){ 0.31f, 0.27f, 0.17f }, acc, 5, 7);
        gLid = acc;
        DrawEyes(hy + 0.05f, 0.4f, 0.13f, 0.09f, t);
        DrawSmile(hy - 0.15f, 0.44f, 0.14f);
        DrawCheeks(hy - 0.06f, 0.42f, 0.22f);
        break;
    }
    (void)hit;

    /* hats */
    Color trim = cd->trim;
    switch (cd->hat) {
    case HAT_NONE: break;
    case HAT_BUN:
        DrawLitSphere((Vector3){ 0, hy + 0.27f, -0.05f }, (Vector3){ 0.43f, 0.25f, 0.43f }, (Color){ 205, 205, 215, 255 }, 5, 9);
        DrawLitSphere((Vector3){ 0, hy + 0.5f, -0.2f }, (Vector3){ 0.2f, 0.2f, 0.2f }, (Color){ 215, 215, 225, 255 }, 5, 7);
        DrawLitCapsule((Vector3){ -0.1f, hy + 0.42f, -0.2f }, (Vector3){ 0.18f, hy + 0.72f, -0.22f }, 0.018f, (Color){ 255, 80, 140, 255 });
        break;
    case HAT_PIRATE:
        DrawLitRoundBox((Vector3){ 0, hy + 0.55f, 0 }, (Vector3){ 1.2f, 0.12f, 0.52f }, 0.05f, 1, 1, (Color){ 35, 35, 48, 255 }, (Color){ 20, 20, 28, 255 });
        DrawLitRoundBox((Vector3){ 0, hy + 0.72f, 0 }, (Vector3){ 0.72f, 0.3f, 0.42f }, 0.12f, 1, 1, (Color){ 35, 35, 48, 255 }, (Color){ 25, 25, 35, 255 });
        DrawLitSphere((Vector3){ 0, hy + 0.74f, 0.21f }, (Vector3){ 0.08f, 0.08f, 0.02f }, WHITE, 3, 6);
        DrawLitCapsule((Vector3){ -0.08f, hy + 0.66f, 0.22f }, (Vector3){ 0.08f, hy + 0.62f, 0.22f }, 0.02f, WHITE);
        break;
    case HAT_ANTENNA:
        for (int s = -1; s <= 1; s += 2) {
            DrawLitCapsule((Vector3){ s*0.16f, hy + 0.3f, 0 }, (Vector3){ s*0.22f, hy + 0.68f, 0.02f }, 0.025f, (Color){ 40, 40, 40, 255 });
            DrawLitSphere((Vector3){ s*0.22f, hy + 0.72f, 0.02f }, (Vector3){ 0.085f, 0.085f, 0.085f }, (Color){ 255, 60, 60, 255 }, 4, 6);
        }
        break;
    case HAT_FLOPPY_EARS:
        for (int s = -1; s <= 1; s += 2)
            DrawLitSphere((Vector3){ s*0.42f, hy + 0.02f, -0.04f }, (Vector3){ 0.12f, 0.3f, 0.2f }, ColorScale(cd->body, 0.78f), 5, 7);
        break;
    case HAT_ROUND_EARS:
        DrawLitSphere((Vector3){ 0.32f, hy + 0.38f, 0 }, (Vector3){ 0.14f, 0.14f, 0.08f }, cd->body, 4, 6);
        DrawLitSphere((Vector3){ -0.32f, hy + 0.38f, 0 }, (Vector3){ 0.14f, 0.14f, 0.08f }, cd->body, 4, 6);
        break;
    case HAT_HORNS:
        DrawLitCylinderY((Vector3){ 0.3f, hy + 0.28f, 0 }, 0.09f, 0.0f, 0.42f, cd->accent, 7);
        DrawLitCylinderY((Vector3){ -0.3f, hy + 0.28f, 0 }, 0.09f, 0.0f, 0.42f, cd->accent, 7);
        for (int q = 0; q < 5; q++) {   /* flower */
            float a = q*2*PI/5;
            DrawLitSphere((Vector3){ 0.24f + cosf(a)*0.06f, hy + 0.36f + sinf(a)*0.06f, 0.27f }, (Vector3){ 0.045f, 0.045f, 0.03f }, (Color){ 255, 150, 200, 255 }, 3, 4);
        }
        DrawLitSphere((Vector3){ 0.24f, hy + 0.36f, 0.29f }, (Vector3){ 0.035f, 0.035f, 0.03f }, (Color){ 255, 220, 60, 255 }, 3, 4);
        break;
    case HAT_CROWN:
        DrawLitCylinderY((Vector3){ 0, hy + 0.3f, 0 }, 0.23f, 0.26f, 0.18f, (Color){ 255, 205, 40, 255 }, 10);
        for (int i = 0; i < 5; i++) {
            float a = i*2*PI/5;
            DrawLitCylinderY((Vector3){ cosf(a)*0.22f, hy + 0.47f, sinf(a)*0.22f }, 0.06f, 0.0f, 0.14f, (Color){ 255, 225, 70, 255 }, 5);
            DrawLitSphere((Vector3){ cosf(a + 0.63f)*0.255f, hy + 0.39f, sinf(a + 0.63f)*0.255f }, (Vector3){ 0.035f, 0.035f, 0.035f }, i & 1 ? (Color){ 60, 200, 255, 255 } : (Color){ 255, 60, 90, 255 }, 3, 4);
        }
        break;
    case HAT_PROPELLER:
        DrawLitCylinderY((Vector3){ 0, hy + 0.35f, 0 }, 0.35f, 0.25f, 0.15f, trim, 8);
        break;
    case HAT_GOGGLES:
        DrawLitRoundBox((Vector3){ 0, hy + 0.32f, 0 }, (Vector3){ 0.92f, 0.09f, 0.86f }, 0.04f, 1, 1, (Color){ 70, 70, 80, 255 }, (Color){ 50, 50, 60, 255 });
        for (int s = -1; s <= 1; s += 2) {
            DrawLitCylinderY((Vector3){ s*0.17f, hy + 0.3f, 0.36f }, 0.13f, 0.13f, 0.12f, (Color){ 90, 90, 100, 255 }, 8);
            DrawLitSphere((Vector3){ s*0.17f, hy + 0.37f, 0.4f }, (Vector3){ 0.11f, 0.09f, 0.05f }, (Color){ 130, 230, 255, 255 }, 4, 6);
        }
        break;
    case HAT_CHEF:
        DrawLitCylinderY((Vector3){ 0, hy + 0.28f, 0 }, 0.31f, 0.31f, 0.3f, WHITE, 10);
        DrawLitSphere((Vector3){ 0, hy + 0.68f, 0 }, (Vector3){ 0.42f, 0.25f, 0.42f }, WHITE, 5, 9);
        DrawLitSphere((Vector3){ 0.22f, hy + 0.74f, 0.1f }, (Vector3){ 0.2f, 0.18f, 0.2f }, (Color){ 245, 245, 245, 255 }, 4, 6);
        DrawLitSphere((Vector3){ -0.2f, hy + 0.76f, -0.08f }, (Vector3){ 0.2f, 0.18f, 0.2f }, (Color){ 245, 245, 245, 255 }, 4, 6);
        break;
    }
}

/* torso + arms + gloves (baked) */
static void DrawTorso(const CharacterDef *cd)
{
    DrawLitSphere((Vector3){ 0, 1.0f, -0.15f }, (Vector3){ 0.42f, 0.44f, 0.36f }, cd->body, 6, 9);
    if (cd->head == HEAD_ROBOT) { /* bee stripes */
        DrawLitSphere((Vector3){ 0, 0.94f, -0.15f }, (Vector3){ 0.435f, 0.07f, 0.375f }, cd->accent, 3, 9);
        DrawLitSphere((Vector3){ 0, 1.12f, -0.15f }, (Vector3){ 0.41f, 0.06f, 0.35f }, cd->accent, 3, 9);
    }
    DrawLitSphere((Vector3){ 0, 1.33f, -0.12f }, (Vector3){ 0.28f, 0.07f, 0.24f }, cd->trim, 3, 9);   /* collar */
    for (int s = -1; s <= 1; s += 2) {
        Vector3 sh = { s*0.34f, 1.14f, -0.08f }, el = { s*0.38f, 0.96f, 0.18f }, ha = { s*0.24f, 1.0f, 0.42f };
        DrawLitCapsule(sh, el, 0.09f, cd->body);
        DrawLitCapsule(el, ha, 0.08f, cd->body);
        DrawLitSphere(ha, (Vector3){ 0.11f, 0.11f, 0.11f }, (Color){ 250, 250, 250, 255 }, 4, 6);
    }
}

/* kart chassis (baked) */
static void DrawChassis(const CharacterDef *cd)
{
    Color kc = cd->kart, tc = cd->trim;
    Color dk = ColorScale(kc, 0.55f);
    Color metal = { 165, 170, 180, 255 }, pipe = { 95, 95, 102, 255 }, black = { 32, 32, 38, 255 };
    DrawLitRoundBox((Vector3){ 0, 0.29f, -0.05f }, (Vector3){ 1.28f, 0.1f, 2.05f }, 0.04f, 0.8f, 1, black, black);       /* floor pan */
    DrawLitRoundBox((Vector3){ 0, 0.47f, -0.12f }, (Vector3){ 1.2f, 0.34f, 1.86f }, 0.15f, 0.74f, 0.78f, ColorScale(kc, 1.1f), ColorScale(kc, 0.78f));
    DrawLitRoundBox((Vector3){ 0, 0.4f, 1.0f }, (Vector3){ 0.92f, 0.25f, 0.62f }, 0.11f, 0.72f, 0.66f, ColorScale(tc, 1.08f), ColorScale(tc, 0.8f));
    DrawLitRoundBox((Vector3){ 0, 0.3f, 1.3f }, (Vector3){ 1.12f, 0.17f, 0.2f }, 0.08f, 1, 1, dk, ColorScale(dk, 0.8f));     /* bumper */
    DrawLitSphere((Vector3){ 0, 0.53f, 0.93f }, (Vector3){ 0.17f, 0.02f, 0.17f }, WHITE, 2, 10);                              /* number roundel */
    DrawLitSphere((Vector3){ 0, 0.545f, 0.93f }, (Vector3){ 0.1f, 0.02f, 0.1f }, kc, 2, 8);
    for (int s = -1; s <= 1; s += 2) {
        DrawLitRoundBox((Vector3){ s*0.6f, 0.38f, -0.15f }, (Vector3){ 0.25f, 0.25f, 1.05f }, 0.1f, 1, 0.82f, tc, ColorScale(tc, 0.75f));  /* side pods */
        DrawLitCapsule((Vector3){ s*0.36f, 0.3f, 0.72f }, (Vector3){ s*0.6f, 0.3f, 0.72f }, 0.04f, black);                       /* axle stubs */
        DrawLitCapsule((Vector3){ s*0.36f, 0.33f, -0.75f }, (Vector3){ s*0.6f, 0.36f, -0.75f }, 0.045f, black);
        DrawLitCapsule((Vector3){ s*0.27f, 0.8f, -1.08f }, (Vector3){ s*0.3f, 0.86f, -1.4f }, 0.075f, pipe);                     /* exhausts */
        DrawLitSphere((Vector3){ s*0.3f, 0.86f, -1.47f }, (Vector3){ 0.05f, 0.05f, 0.02f }, black, 3, 6);
        DrawLitCapsule((Vector3){ s*0.42f, 0.82f, -1.12f }, (Vector3){ s*0.42f, 1.12f, -1.26f }, 0.035f, metal);                  /* wing struts */
        DrawLitRoundBox((Vector3){ s*0.73f, 1.1f, -1.27f }, (Vector3){ 0.05f, 0.24f, 0.4f }, 0.02f, 1, 1, kc, dk);                /* end plates */
    }
    DrawLitRoundBox((Vector3){ 0, 0.9f, -0.52f }, (Vector3){ 0.8f, 0.58f, 0.17f }, 0.07f, 1, 1, tc, ColorScale(tc, 0.75f));          /* seat */
    DrawLitRoundBox((Vector3){ 0, 0.7f, -1.0f }, (Vector3){ 0.86f, 0.36f, 0.42f }, 0.1f, 1, 1, metal, ColorScale(metal, 0.7f));     /* engine */
    for (int f = -1; f <= 1; f++)
        DrawLitRoundBox((Vector3){ f*0.22f, 0.9f, -1.0f }, (Vector3){ 0.06f, 0.08f, 0.36f }, 0.02f, 1, 1, ColorScale(metal, 0.85f), ColorScale(metal, 0.85f));
    DrawLitRoundBox((Vector3){ 0, 1.15f, -1.27f }, (Vector3){ 1.45f, 0.07f, 0.36f }, 0.03f, 1, 1, ColorScale(tc, 1.1f), ColorScale(tc, 0.85f)); /* spoiler */
    if (cd->spriteAngles > 0) DrawLitCapsule((Vector3){ 0, 0.55f, 0.8f }, (Vector3){ 0, 0.7f, 0.64f }, 0.035f, black);              /* low column */
    else DrawLitCapsule((Vector3){ 0, 0.6f, 0.72f }, (Vector3){ 0, 0.9f, 0.47f }, 0.04f, black);                                 /* column */
}

/* themed kart decorations for the photo racers */
static void DrawKartDecor(const CharacterDef *cd)
{
    if (cd->kartStyle != KART_STYLE_NONE) {
        /* sign board on the rear wing for the decal banner */
        Color bc = ColorMix(cd->kart, WHITE, 0.25f);
        DrawLitRoundBox((Vector3){ 0, 1.33f, -1.44f }, (Vector3){ 1.5f, 0.34f, 0.05f }, 0.02f, 1, 1, bc, ColorScale(bc, 0.8f));
    }
    if (cd->kartStyle == KART_STYLE_RATTLE) {
        /* pastel polka dots on the side pods */
        Color dots[4] = { {255,255,255,255}, {255,240,140,255}, {170,225,255,255}, {200,255,200,255} };
        for (int s = -1; s <= 1; s += 2)
            for (int d = 0; d < 4; d++)
                DrawLitSphere((Vector3){ s*0.735f, 0.40f + (d & 1)*0.06f, -0.55f + d*0.26f }, (Vector3){ 0.02f, 0.06f, 0.06f }, dots[d], 3, 8);
        /* a giant baby rattle rising behind the seat */
        DrawLitCapsule((Vector3){ -0.66f, 1.1f, -1.25f }, (Vector3){ -0.8f, 1.3f, -1.3f }, 0.045f, (Color){ 255, 250, 235, 255 });
        DrawLitSphere((Vector3){ -0.67f, 1.16f, -1.25f }, (Vector3){ 0.08f, 0.05f, 0.08f }, (Color){ 170, 220, 255, 255 }, 4, 10);
        DrawLitSphere((Vector3){ -0.86f, 1.44f, -1.3f }, (Vector3){ 0.17f, 0.17f, 0.17f }, (Color){ 255, 236, 140, 255 }, 7, 12);
        Color rc[6] = { {255,120,170,255}, {120,200,255,255}, {140,230,140,255}, {255,170,90,255}, {200,150,255,255}, {255,255,255,255} };
        for (int i = 0; i < 10; i++) {
            float a = i*2.399f, z = 1.0f - 2.0f*(i + 0.5f)/10.0f, r = sqrtf(1 - z*z);
            Vector3 d = { cosf(a)*r, z, sinf(a)*r };
            DrawLitSphere(Vector3Add((Vector3){ -0.86f, 1.44f, -1.3f }, Vector3Scale(d, 0.16f)), (Vector3){ 0.05f, 0.05f, 0.05f }, rc[i % 6], 3, 6);
        }
        DrawLitSphere((Vector3){ -0.87f, 1.62f, -1.3f }, (Vector3){ 0.07f, 0.05f, 0.07f }, (Color){ 255, 130, 180, 255 }, 3, 8);
        /* toy fruit on the nose: a strawberry, a green apple and an orange */
        DrawLitSphere((Vector3){ 0.02f, 0.62f, 1.12f }, (Vector3){ 0.13f, 0.12f, 0.13f }, (Color){ 140, 215, 70, 255 }, 5, 10);
        DrawLitCapsule((Vector3){ 0.02f, 0.72f, 1.12f }, (Vector3){ 0.04f, 0.8f, 1.12f }, 0.015f, (Color){ 110, 70, 40, 255 });
        DrawLitSphere((Vector3){ 0.28f, 0.6f, 1.02f }, (Vector3){ 0.12f, 0.12f, 0.12f }, (Color){ 255, 150, 30, 255 }, 5, 10);
    } else if (cd->kartStyle == KART_STYLE_SPA) {
        /* rolled spa towels on the engine deck */
        DrawLitCylinderX((Vector3){ 0, 1.0f, -0.93f }, 0.13f, 0.74f, (Color){ 250, 250, 252, 255 }, 12);
        DrawLitCylinderX((Vector3){ 0, 1.22f, -0.95f }, 0.11f, 0.62f, (Color){ 30, 150, 160, 255 }, 12);
        for (int s = -1; s <= 1; s += 2)
            DrawLitCylinderX((Vector3){ s*0.38f, 1.0f, -0.93f }, 0.1f, 0.02f, (Color){ 200, 205, 215, 255 }, 12);
        /* cucumber slices on the wing end plates */
        for (int s = -1; s <= 1; s += 2) {
            DrawLitCylinderX((Vector3){ s*0.765f, 1.1f, -1.27f }, 0.14f, 0.03f, (Color){ 60, 140, 50, 255 }, 14);
            DrawLitCylinderX((Vector3){ s*0.78f, 1.1f, -1.27f }, 0.115f, 0.01f, (Color){ 200, 235, 150, 255 }, 14);
        }
        /* a rubber duck on the nose */
        Color duck = { 255, 215, 40, 255 };
        DrawLitSphere((Vector3){ 0, 0.64f, 1.04f }, (Vector3){ 0.15f, 0.12f, 0.19f }, duck, 6, 12);
        DrawLitSphere((Vector3){ 0, 0.83f, 1.12f }, (Vector3){ 0.1f, 0.1f, 0.1f }, duck, 6, 12);
        DrawLitSphere((Vector3){ 0, 0.81f, 1.23f }, (Vector3){ 0.05f, 0.025f, 0.05f }, (Color){ 255, 120, 20, 255 }, 3, 8);
        for (int s = -1; s <= 1; s += 2) DrawLitSphere((Vector3){ s*0.045f, 0.87f, 1.2f }, (Vector3){ 0.018f, 0.018f, 0.012f }, (Color){ 20, 20, 25, 255 }, 3, 6);
        DrawLitSphere((Vector3){ 0, 0.7f, 0.88f }, (Vector3){ 0.06f, 0.05f, 0.05f }, duck, 3, 8);   /* tail */
    }
}

/* Qanna's teal towel: a 3D knot at the back of the head and a long terry-cloth tail that
   streams and flaps in the wind (faster and flatter at speed, droops when stopped) */
static void DrawTowelTail(const CharacterDef *cd, const Kart *k, float t, Color tint)
{
    float spd = k ? Clamp(fabsf(k->speed)/22.0f, 0, 1) : 0.35f;
    float top = 0.47f + cd->spriteSeat + cd->spriteSize*0.84f;
    Color teal = ColorTint((Color){ 26, 126, 146, 255 }, tint), tealD = ColorTint((Color){ 20, 108, 128, 255 }, tint);
    teal.a = tealD.a = tint.a;
    bool photo = cd->spriteRows > 1;            /* multi-angle photo: the towel is in every view already */
    if (photo) { top = 0.47f + cd->spriteSeat + cd->spriteSize*0.80f; teal = ColorTint((Color){ 22, 104, 116, 255 }, tint); tealD = ColorTint((Color){ 16, 84, 96, 255 }, tint); teal.a = tealD.a = tint.a; }
    /* knot (twisted bun) behind the head */
    if (tint.a == 255 && !photo) {
        DrawLitSphere((Vector3){ 0, top - 0.02f, -0.38f }, (Vector3){ 0.24f, 0.2f, 0.2f }, teal, 5, 10);
        DrawLitSphere((Vector3){ 0.06f, top + 0.12f, -0.36f }, (Vector3){ 0.15f, 0.13f, 0.14f }, tealD, 4, 8);
    }
    const int N = 10;
    float len = 1.0f + 0.55f*spd;
    Vector3 prev = { 0, top - 0.04f, -0.48f };
    float wPrev = 0.26f;
    rlSetTexture(G.texWhite.id);
    rlBegin(RL_QUADS);
    for (int i = 1; i <= N; i++) {
        float f = (float)i/N;
        float ph = t*(8.0f + 9.0f*spd) - i*0.85f;
        float wave = sinf(ph), wave2 = sinf(ph*0.7f + 1.3f);
        Vector3 p = {
            wave2*0.10f*f*(0.5f + spd),
            top - 0.04f - f*(0.75f - 0.6f*spd) + wave*0.09f*f*(0.3f + spd),
            -0.48f - f*len };
        float w = 0.25f - 0.07f*f;
        float twist = wave*0.12f*f;     /* the cloth rolls a little as it flaps */
        Color c = (i & 1) ? teal : tealD;
        Color c2 = ColorScale(c, 0.85f); c2.a = c.a;
        rlColor4ub(c.r, c.g, c.b, c.a);
        rlTexCoord2f(0.5f, 0.5f);
        rlVertex3f(prev.x - wPrev, prev.y + wPrev*twist, prev.z);
        rlVertex3f(prev.x + wPrev, prev.y - wPrev*twist, prev.z);
        rlColor4ub(c2.r, c2.g, c2.b, c2.a);
        rlVertex3f(p.x + w, p.y - w*twist, p.z);
        rlVertex3f(p.x - w, p.y + w*twist, p.z);
        prev = p; wPrev = w;
    }
    rlEnd();
    /* fringe at the end of the towel */
    rlBegin(RL_LINES);
    for (int q = -3; q <= 3; q++) {
        rlColor4ub(tealD.r, tealD.g, tealD.b, tealD.a);
        rlVertex3f(prev.x + q*wPrev/3.0f, prev.y, prev.z);
        rlVertex3f(prev.x + q*wPrev/3.0f + 0.02f*sinf(t*20 + q), prev.y - 0.04f, prev.z - 0.1f);
    }
    rlEnd();
    rlSetTexture(0);
}

/* Baby Eabha's signature prop: her wooden toy strawberry from the photo (sliced in half like the
   wooden velcro play-food, pale wood showing) on a springy stalk on the nose; it bobs as she drives */
static void DrawToyStrawberry(const Kart *k, float t, Color tint)
{
    float spd = k ? Clamp(fabsf(k->speed)/22.0f, 0, 1) : 0.3f;
    float wob = sinf(t*(6.0f + 6.0f*spd))*(0.06f + 0.1f*spd);
    float hop = k && !k->grounded ? 0.12f : 0.0f;
    rlPushMatrix();
    rlTranslatef(-0.42f, 0.58f, 1.05f);
    /* spring */
    Color sp = ColorTint((Color){ 210, 210, 220, 255 }, tint);
    Vector3 pv = { 0, 0, 0 };
    for (int i = 1; i <= 16; i++) {
        float a = i*1.2f, h = i*(0.028f + hop*0.01f);
        Vector3 p = { cosf(a)*0.05f + wob*h, h, sinf(a)*0.05f };
        DrawLitCapsule(pv, p, 0.012f, sp);
        pv = p;
    }
    rlTranslatef(pv.x, pv.y + 0.18f, pv.z);
    rlRotatef(wob*60.0f, 0, 0, 1);
    rlRotatef(-20.0f, 1, 0, 0);
    Color red = ColorTint((Color){ 225, 30, 45, 255 }, tint), wood = ColorTint((Color){ 240, 214, 165, 255 }, tint);
    Color leaf = ColorTint((Color){ 60, 165, 60, 255 }, tint), seed = ColorTint((Color){ 255, 230, 120, 255 }, tint);
    /* two halves, slightly apart, showing the wooden cut faces */
    for (int s = -1; s <= 1; s += 2) {
        rlPushMatrix();
        rlTranslatef(s*0.035f, 0, 0);
        DrawLitSphere((Vector3){ s*0.0f, 0, 0 }, (Vector3){ 0.2f, 0.25f, 0.2f }, red, 7, 12);
        DrawLitSphere((Vector3){ 0, -0.16f, 0 }, (Vector3){ 0.13f, 0.14f, 0.13f }, red, 5, 10);
        rlPopMatrix();
    }
    DrawLitRoundBox((Vector3){ 0, -0.03f, 0 }, (Vector3){ 0.07f, 0.4f, 0.32f }, 0.03f, 1, 0.6f, wood, ColorScale(wood, 0.85f));
    for (int q = 0; q < 12; q++) {   /* painted seeds */
        float a = q*2.4f, y = 0.15f - (q % 6)*0.06f;
        float r = 0.2f*sqrtf(fmaxf(0.0f, 1.0f - (y/0.26f)*(y/0.26f)));
        DrawLitSphere((Vector3){ cosf(a)*(r + 0.04f), y, sinf(a)*(r + 0.04f) }, (Vector3){ 0.018f, 0.025f, 0.018f }, seed, 2, 5);
    }
    for (int q = 0; q < 6; q++) {   /* leafy top */
        float a = q*PI/3;
        DrawLitSphere((Vector3){ cosf(a)*0.11f, 0.25f, sinf(a)*0.11f }, (Vector3){ 0.1f, 0.025f, 0.05f }, leaf, 3, 6);
    }
    DrawLitCapsule((Vector3){ 0, 0.25f, 0 }, (Vector3){ 0.02f, 0.36f, 0 }, 0.02f, leaf);
    rlPopMatrix();
}

static void DrawSteeringWheelShape(void)
{
    Color c = { 40, 40, 46, 255 };
    for (int q = 0; q < 10; q++) {
        float a0 = 2*PI*q/10, a1 = 2*PI*(q + 1)/10;
        DrawLitTube((Vector3){ cosf(a0)*0.19f, sinf(a0)*0.19f, 0 }, (Vector3){ cosf(a1)*0.19f, sinf(a1)*0.19f, 0 }, 0.032f, c);
    }
    DrawLitCapsule((Vector3){ -0.19f, 0, 0 }, (Vector3){ 0.19f, 0, 0 }, 0.025f, c);
    DrawLitSphere((Vector3){ 0, 0, 0.01f }, (Vector3){ 0.06f, 0.06f, 0.03f }, (Color){ 220, 40, 40, 255 }, 3, 6);
}

/* ------------------------------------------------------------------ */
/* Built-in-code 3D low-poly models for the two photo racers (v7).      */
/* Shapes, colours and proportions were taken from the reference photos */
/* by eye; no photo pixels are used. Everything is baked like the other */
/* racers (driver + head, plus a win-pose driver + win head), so they    */
/* sit in the seat and read correctly from every angle.                  */
/* ------------------------------------------------------------------ */
enum { MODEL3D_NONE = 0, MODEL3D_EABHA, MODEL3D_QANNA };

static Color C8(int r, int g, int b) { return (Color){ (unsigned char)r, (unsigned char)g, (unsigned char)b, 255 }; }
/* ellipsoid rotated (degrees: yaw about Y, then pitch about X, then roll about Z) */
static void Ell(Vector3 c, Vector3 r, float yaw, float pitch, float roll, Color col)
{
    XPush(); XTranslate(c.x, c.y, c.z);
    if (yaw) XRotate(yaw, 0, 1, 0);
    if (pitch) XRotate(pitch, 1, 0, 0);
    if (roll) XRotate(roll, 0, 0, 1);
    DrawLitSphere((Vector3){ 0, 0, 0 }, r, col, 6, 10);
    XPop();
}
/* a point on the front (s=+1) / back (s=-1) surface of an axis-aligned ellipsoid */
static Vector3 OnEll(Vector3 c, Vector3 r, float x, float y, float s, float lift)
{
    float q = 1.0f - (x/r.x)*(x/r.x) - ((y - c.y)/r.y)*((y - c.y)/r.y);
    float z = q > 0 ? r.z*sqrtf(q) : 0;
    return (Vector3){ c.x + x, y, c.z + s*(z + lift) };
}
static float HeadYOf(const CharacterDef *cd) { return cd->model3d == MODEL3D_EABHA ? 1.5f : cd->model3d == MODEL3D_QANNA ? 1.6f : HEAD_Y; }

/* ---------------- Baby Éabha ---------------- */
static const Color EA_SKIN_PHOTO = { 232, 168, 130, 255 }, QA_SKIN_PHOTO = { 232, 172, 150, 255 };
static const Color EA_SKIN = { 246, 214, 198, 255 }, EA_TOP = { 246, 212, 214, 255 }, EA_HAIR = { 176, 132, 92, 255 };
static void EabhaBody(bool win)
{
    Color top = EA_TOP, topD = ColorScale(EA_TOP, 0.9f), skin = EA_SKIN;
    Vector3 tc = { 0, 0.92f, -0.16f }, tr = { 0.34f, 0.36f, 0.3f };
    DrawLitSphere(tc, tr, top, 6, 10);                                           /* sweatshirt */
    DrawLitSphere((Vector3){ 0, 0.66f, -0.14f }, (Vector3){ 0.33f, 0.08f, 0.29f }, topD, 3, 10);   /* waistband */
    /* legs (short, pointing at the pedals) with pink socks */
    for (int s = -1; s <= 1; s += 2) {
        DrawLitCapsule((Vector3){ s*0.14f, 0.7f, -0.08f }, (Vector3){ s*0.15f, 0.74f, 0.32f }, 0.1f, top);
        DrawLitSphere((Vector3){ s*0.15f, 0.72f, 0.44f }, (Vector3){ 0.085f, 0.075f, 0.11f }, C8(255, 170, 200), 4, 7);
    }
    /* bandana bib: cream triangle with dark sprinkles, knotted behind the neck */
    Color bib = C8(247, 236, 216);
    Ell((Vector3){ 0, 1.13f, 0.06f }, (Vector3){ 0.25f, 0.12f, 0.08f }, 0, -12, 0, bib);
    Ell((Vector3){ 0, 1.03f, 0.12f }, (Vector3){ 0.15f, 0.12f, 0.05f }, 0, -14, 0, bib);
    Ell((Vector3){ 0, 0.94f, 0.15f }, (Vector3){ 0.07f, 0.07f, 0.035f }, 0, -14, 0, bib);
    for (int i = 0; i < 9; i++) {
        float x = -0.16f + (i % 5)*0.08f + (i >= 5 ? 0.04f : 0), y = i >= 5 ? 1.04f : 1.12f;
        if (i >= 5 && i > 7) { x = 0; y = 0.97f; }
        DrawLitSphere((Vector3){ x, y, 0.135f + (y < 1.0f ? 0.05f : (i >= 5 ? 0.04f : 0.0f)) + 0.03f }, (Vector3){ 0.012f, 0.016f, 0.008f }, C8(120, 70, 60), 2, 4);
    }
    DrawLitSphere((Vector3){ 0, 1.2f, -0.36f }, (Vector3){ 0.06f, 0.05f, 0.05f }, bib, 3, 6);  /* knot */
    /* chubby arms: hands on the wheel, or both up in a cheer */
    for (int s = -1; s <= 1; s += 2) {
        Vector3 sh = { s*0.3f, 1.1f, -0.14f };
        Vector3 el = win ? (Vector3){ s*0.5f, 1.38f, -0.1f } : (Vector3){ s*0.36f, 0.96f, 0.12f };
        Vector3 ha = win ? (Vector3){ s*0.58f, 1.72f, 0.0f } : (Vector3){ s*0.2f, 0.99f, 0.4f };
        DrawLitSphere(sh, (Vector3){ 0.12f, 0.12f, 0.12f }, top, 4, 7);
        DrawLitCapsule(sh, el, 0.095f, top);
        DrawLitCapsule(el, ha, 0.085f, top);
        DrawLitSphere(Vector3Lerp(el, ha, 0.86f), (Vector3){ 0.095f, 0.095f, 0.095f }, topD, 3, 7);  /* cuff */
        DrawLitSphere(ha, (Vector3){ 0.085f, 0.085f, 0.085f }, skin, 4, 7);
    }
}
static void EabhaHead(bool win)
{
    float hy = 1.5f;
    Color skin = gPhotoFace ? EA_SKIN_PHOTO : EA_SKIN, hair = EA_HAIR;
    gLid = skin;
    DrawLitSphere((Vector3){ 0, 1.27f, -0.08f }, (Vector3){ 0.12f, 0.1f, 0.12f }, skin, 3, 7);    /* neck */
    DrawLitSphere((Vector3){ 0, hy, 0 }, (Vector3){ 0.43f, 0.45f, 0.42f }, skin, 8, 12);           /* big round head */
    DrawLitSphere((Vector3){ 0, hy - 0.14f, 0.04f }, (Vector3){ 0.37f, 0.22f, 0.33f }, skin, 5, 9);  /* chubby cheeks/jaw (clear of the bib) */
    for (int s = -1; s <= 1; s += 2) {
        DrawLitSphere((Vector3){ s*0.42f, hy - 0.02f, -0.02f }, (Vector3){ 0.06f, 0.1f, 0.07f }, ColorScale(skin, 0.95f), 3, 6);
    }
    /* fine light-brown baby hair: a thin cap on top/back with a soft tuft */
    DrawLitSphere((Vector3){ 0, hy + 0.12f, -0.07f }, (Vector3){ 0.44f, 0.37f, 0.41f }, hair, 7, 11);
    DrawLitCapsule((Vector3){ 0.02f, hy + 0.44f, 0.08f }, (Vector3){ 0.1f, hy + 0.5f, 0.18f }, 0.035f, hair);
    DrawLitCapsule((Vector3){ 0.1f, hy + 0.5f, 0.18f }, (Vector3){ 0.06f, hy + 0.46f, 0.25f }, 0.03f, hair);
    if (gPhotoFace) { recEyes = false; return; }   /* the real face sprite supplies eyes, nose, cheeks and mouth */
    /* big blue-grey eyes */
    float ey = hy + 0.02f, ez = 0.355f, es = 0.15f, sz = 0.085f;
    for (int s = -1; s <= 1; s += 2) {
        float x = s*es;
        DrawLitSphere((Vector3){ x, ey, ez }, (Vector3){ sz, sz*1.02f, sz*0.55f }, C8(252, 252, 252), 5, 8);
        if (win) {   /* squeezed shut with joy: happy arcs */
            DrawLitSphere((Vector3){ x, ey + 0.012f, ez + 0.012f }, (Vector3){ sz*1.08f, sz*0.9f, sz*0.6f }, ColorScale(skin, 0.97f), 4, 8);
            DrawLitCapsule((Vector3){ x - 0.06f, ey - 0.015f, ez + 0.052f }, (Vector3){ x, ey + 0.02f, ez + 0.058f }, 0.013f, C8(70, 45, 40));
            DrawLitCapsule((Vector3){ x, ey + 0.02f, ez + 0.058f }, (Vector3){ x + 0.06f, ey - 0.015f, ez + 0.052f }, 0.013f, C8(70, 45, 40));
        } else {
            DrawLitSphere((Vector3){ x*0.98f, ey - 0.005f, ez + 0.03f }, (Vector3){ 0.058f, 0.06f, 0.03f }, C8(104, 138, 166), 4, 8);
            DrawLitSphere((Vector3){ x*0.98f, ey - 0.005f, ez + 0.045f }, (Vector3){ 0.03f, 0.032f, 0.02f }, C8(25, 25, 35), 3, 6);
            DrawLitSphere((Vector3){ x*0.98f + 0.02f, ey + 0.025f, ez + 0.058f }, (Vector3){ 0.014f, 0.014f, 0.008f }, WHITE, 2, 4);
        }
        /* soft, thin brows; raised high when she cheers */
        float by = ey + (win ? 0.13f : 0.11f);
        DrawLitCapsule((Vector3){ x - s*0.075f, by - 0.012f, ez + 0.01f }, (Vector3){ x + s*0.07f, by + 0.004f, ez - 0.01f }, 0.014f, C8(186, 140, 104));
    }
    recEyes = !win; recEyeY = ey; recEyeZ = ez; recEyeSpread = es; recEyeSize = sz;
    DrawLitSphere((Vector3){ 0, hy - 0.08f, 0.42f }, (Vector3){ 0.045f, 0.035f, 0.035f }, ColorScale(skin, 0.94f), 3, 6);  /* button nose */
    for (int s = -1; s <= 1; s += 2)
        DrawLitSphere((Vector3){ s*0.24f, hy - 0.11f, 0.33f }, (Vector3){ 0.08f, 0.05f, 0.03f }, C8(250, 170, 175), 3, 6);   /* rosy cheeks */
    if (win) {   /* "Car!": a big open delighted mouth */
        DrawLitSphere((Vector3){ 0, hy - 0.2f, 0.385f }, (Vector3){ 0.1f, 0.075f, 0.045f }, C8(150, 40, 55), 4, 8);
        DrawLitSphere((Vector3){ 0, hy - 0.235f, 0.41f }, (Vector3){ 0.06f, 0.03f, 0.03f }, C8(245, 120, 140), 3, 6);
        DrawLitSphere((Vector3){ 0, hy - 0.14f, 0.415f }, (Vector3){ 0.07f, 0.014f, 0.02f }, WHITE, 2, 6);   /* two little teeth */
    } else {
        DrawLitSphere((Vector3){ 0, hy - 0.185f, 0.4f }, (Vector3){ 0.06f, 0.024f, 0.03f }, C8(222, 120, 125), 3, 6);
        DrawLitSphere((Vector3){ 0, hy - 0.205f, 0.395f }, (Vector3){ 0.048f, 0.022f, 0.03f }, C8(205, 100, 110), 3, 6);
    }
}

/* ---------------- Towelhead Qanna ---------------- */
static const Color QA_SKIN = { 0xDD, 0xBD, 0xA5, 255 }, QA_TEAL = { 0x1A, 0x5E, 0x63, 255 }, QA_KNIT = { 0xBC, 0xAE, 0x9F, 255 };
static const Color QA_LEG = { 0x15, 0x15, 0x15, 255 }, QA_HAIR = { 62, 42, 32, 255 };
static void QannaBody(bool win)
{
    Color knit = QA_KNIT, rib = ColorScale(QA_KNIT, 0.86f), skin = QA_SKIN;
    /* black leggings + white socks, knees up in the cockpit */
    for (int s = -1; s <= 1; s += 2) {
        DrawLitCapsule((Vector3){ s*0.16f, 0.72f, -0.2f }, (Vector3){ s*0.19f, 0.86f, 0.3f }, 0.105f, QA_LEG);
        DrawLitCapsule((Vector3){ s*0.19f, 0.86f, 0.3f }, (Vector3){ s*0.2f, 0.6f, 0.7f }, 0.09f, QA_LEG);
        DrawLitSphere((Vector3){ s*0.2f, 0.58f, 0.76f }, (Vector3){ 0.085f, 0.08f, 0.12f }, C8(245, 245, 245), 4, 7);
    }
    /* oversized oatmeal jumper, slouched forward (shoulders rounded, chest sunk) */
    Vector3 tc = { 0, 0.98f, -0.2f }, tr = { 0.45f, 0.42f, 0.36f };
    XPush(); XTranslate(0, 0.7f, -0.2f); XRotate(9.0f, 1, 0, 0); XTranslate(0, -0.7f, 0.2f);
    DrawLitSphere(tc, tr, knit, 7, 12);
    DrawLitSphere((Vector3){ 0, 0.66f, -0.2f }, (Vector3){ 0.44f, 0.09f, 0.35f }, rib, 3, 12);    /* ribbed hem band */
    /* vertical rib knit, front and back */
    for (int i = -4; i <= 4; i++) {
        float x = i*0.085f;
        for (int side = -1; side <= 1; side += 2) {
            Vector3 prev = OnEll(tc, tr, x, 0.72f, (float)side, 0.004f);
            for (int q = 1; q <= 4; q++) {
                Vector3 p = OnEll(tc, tr, x, 0.72f + q*0.13f, (float)side, 0.004f);
                DrawLitCapsule(prev, p, 0.011f, rib);
                prev = p;
            }
        }
    }
    /* crew neck */
    DrawLitCylinderY((Vector3){ 0, 1.3f, -0.13f }, 0.19f, 0.15f, 0.08f, rib, 14);
    /* thin silver necklace with a little pendant */
    Color silver = C8(214, 218, 228);
    Vector3 prev = { -0.15f, 1.36f, -0.02f };
    for (int q = 1; q <= 8; q++) {
        float u = q/8.0f, x = -0.15f + 0.3f*u, sag = 1.0f - (2*u - 1)*(2*u - 1);
        Vector3 p = { x, 1.36f - 0.12f*sag, -0.02f + 0.15f*sag };
        DrawLitCapsule(prev, p, 0.008f, silver);
        prev = p;
    }
    DrawLitSphere((Vector3){ 0, 1.2f, 0.14f }, (Vector3){ 0.028f, 0.036f, 0.014f }, silver, 3, 6);
    /* drop shoulders */
    for (int s = -1; s <= 1; s += 2) DrawLitSphere((Vector3){ s*0.4f, 1.08f, -0.16f }, (Vector3){ 0.17f, 0.16f, 0.17f }, knit, 5, 8);
    XPop();
    /* baggy sleeves bunched at the wrists */
    for (int s = -1; s <= 1; s += 2) {
        Vector3 sh = { s*0.43f, 1.06f, -0.08f };
        Vector3 el = win ? (Vector3){ s*0.36f, 0.84f, 0.16f } : (Vector3){ s*0.47f, 0.88f, 0.16f };
        Vector3 wr = win ? (Vector3){ -s*0.18f, 0.98f, 0.2f } : (Vector3){ s*0.26f, 0.98f, 0.36f };   /* win: arms folded */
        DrawLitCapsule(sh, el, 0.13f, knit);
        DrawLitCapsule(el, wr, 0.12f, knit);
        Vector3 d = Vector3Normalize(Vector3Subtract(wr, el));
        for (int b = 0; b < 3; b++) {
            Vector3 p = Vector3Add(wr, Vector3Scale(d, -0.05f - b*0.07f));
            DrawLitSphere(p, (Vector3){ 0.135f - b*0.006f, 0.135f - b*0.006f, 0.135f - b*0.006f }, b == 1 ? rib : knit, 4, 8);
        }
        Vector3 hand = Vector3Add(wr, Vector3Scale(d, 0.08f));
        DrawLitSphere(hand, (Vector3){ 0.07f, 0.065f, 0.08f }, skin, 4, 7);
    }
}
static void QannaHead(bool win)
{
    float hy = 1.6f;
    Color skin = gPhotoFace ? QA_SKIN_PHOTO : QA_SKIN, teal = QA_TEAL, tealD = ColorScale(QA_TEAL, 0.78f), tealL = ColorScale(QA_TEAL, 1.15f);
    gLid = ColorScale(skin, 0.93f);
    /* slouch: whole head pushed forward and tipped down a touch */
    XPush(); XTranslate(0, hy, 0.05f); XRotate(7.0f, 1, 0, 0); XTranslate(0, -hy, 0);
    DrawLitCapsule((Vector3){ 0, 1.3f, -0.1f }, (Vector3){ 0, 1.45f, -0.04f }, 0.11f, skin);      /* neck */
    DrawLitSphere((Vector3){ 0, hy, 0.02f }, (Vector3){ 0.33f, 0.42f, 0.36f }, skin, 8, 12);       /* oval face */
    DrawLitSphere((Vector3){ 0, hy - 0.2f, 0.04f }, (Vector3){ 0.25f, 0.19f, 0.27f }, skin, 5, 9);  /* chin/jaw */
    for (int s = -1; s <= 1; s += 2)
        DrawLitSphere((Vector3){ s*0.32f, hy - 0.02f, 0.0f }, (Vector3){ 0.05f, 0.09f, 0.06f }, ColorScale(skin, 0.95f), 3, 6);
    /* a little dark brown hair escaping at the temples */
    for (int s = -1; s <= 1; s += 2) {
        Ell((Vector3){ s*0.28f, hy + 0.09f, 0.17f }, (Vector3){ 0.06f, 0.11f, 0.07f }, 0, 0, s*-12.0f, QA_HAIR);
        Ell((Vector3){ s*0.17f, hy + 0.2f, 0.29f }, (Vector3){ 0.1f, 0.045f, 0.05f }, 0, 0, s*-18.0f, QA_HAIR);
    }
    /* teal towel turban: big wrap, band over the forehead, twisted knot at the top centre */
    DrawLitSphere((Vector3){ 0, hy + 0.2f, -0.07f }, (Vector3){ 0.42f, 0.37f, 0.44f }, teal, 8, 12);
    Ell((Vector3){ 0, hy + 0.25f, 0.14f }, (Vector3){ 0.39f, 0.15f, 0.27f }, 0, -14, 0, tealL);      /* band across the forehead */
    DrawLitSphere((Vector3){ 0, hy + 0.44f, -0.06f }, (Vector3){ 0.35f, 0.22f, 0.36f }, teal, 6, 11); /* crown */
    Ell((Vector3){ -0.09f, hy + 0.42f, 0.24f }, (Vector3){ 0.17f, 0.075f, 0.09f }, 0, -10, 32, tealD); /* knot lobes */
    Ell((Vector3){ 0.09f, hy + 0.42f, 0.24f }, (Vector3){ 0.17f, 0.075f, 0.09f }, 0, -10, -32, teal);
    DrawLitSphere((Vector3){ 0, hy + 0.37f, 0.31f }, (Vector3){ 0.1f, 0.09f, 0.08f }, tealL, 4, 8);
    /* terry folds */
    for (int i = 0; i < 4; i++) {
        float a = -0.9f + i*0.6f;
        Vector3 p0 = { sinf(a)*0.36f, hy + 0.5f, cosf(a)*0.3f - 0.06f }, p1 = { sinf(a)*0.43f, hy + 0.12f, cosf(a)*0.38f - 0.12f };
        DrawLitCapsule(p0, p1, 0.035f, tealD);
    }
    if (gPhotoFace) { recEyes = false; XPop(); return; }   /* real face sprite supplies the features */
    /* thick dark brows: level and deadpan, or knitted down in a grump when she wins */
    float ey = hy + 0.05f, es = 0.12f, sz = 0.07f;
    for (int s = -1; s <= 1; s += 2) {
        float x = s*es;
        Vector3 c = OnEll((Vector3){ 0, hy, 0.02f }, (Vector3){ 0.33f, 0.42f, 0.36f }, x, ey, 1, 0);
        float ez = c.z - 0.035f;
        DrawLitSphere((Vector3){ x, ey, ez }, (Vector3){ sz, sz*0.62f, sz*0.5f }, C8(248, 246, 242), 4, 8);
        /* irises looking down */
        DrawLitSphere((Vector3){ x*0.98f, ey - 0.018f, ez + 0.026f }, (Vector3){ 0.034f, 0.034f, 0.02f }, C8(96, 72, 52), 3, 6);
        DrawLitSphere((Vector3){ x*0.98f, ey - 0.018f, ez + 0.036f }, (Vector3){ 0.017f, 0.017f, 0.012f }, C8(20, 16, 14), 2, 5);
        /* heavy upper lid (half-closed), heavier still when grumpy-sleepy */
        float ld = win ? 0.004f : 0.026f;
        DrawLitSphere((Vector3){ x, ey + ld, ez + 0.012f }, (Vector3){ sz*1.08f, sz*(win ? 0.58f : 0.42f), sz*0.56f }, ColorScale(skin, 0.93f), 4, 8);
        DrawLitCapsule((Vector3){ x - 0.06f, ey + ld - 0.012f*(win ? 2.0f : 1.0f), ez + 0.045f }, (Vector3){ x + 0.06f, ey + ld - 0.012f*(win ? 2.0f : 1.0f), ez + 0.045f }, 0.006f, C8(70, 50, 45)); /* lash line */
        /* tired shadows */
        DrawLitSphere((Vector3){ x, ey - 0.055f, ez + 0.0f }, (Vector3){ 0.065f, 0.022f, 0.03f }, win ? C8(170, 130, 130) : ColorScale(skin, 0.86f), 3, 6);
        /* brows */
        float inner = win ? -0.045f : 0.0f;
        DrawLitCapsule((Vector3){ x - s*0.075f, ey + 0.095f + inner, ez + 0.03f }, (Vector3){ x + s*0.075f, ey + 0.1f + (win ? 0.015f : 0.0f), ez + 0.012f }, 0.024f, C8(42, 30, 26));
    }
    recEyes = false;   /* lids already half-closed; no blink */
    DrawLitSphere((Vector3){ 0, hy - 0.05f, 0.38f }, (Vector3){ 0.042f, 0.075f, 0.045f }, ColorScale(skin, 0.95f), 3, 6);   /* nose */
    for (int i = 0; i < 7; i++) {   /* freckles */
        float x = (i - 3)*0.045f + (i & 1 ? 0.012f : -0.01f), y = hy - 0.06f + (i % 3)*0.02f;
        if (fabsf(x) < 0.05f) continue;
        Vector3 p = OnEll((Vector3){ 0, hy, 0.02f }, (Vector3){ 0.33f, 0.42f, 0.36f }, x, y, 1, 0.002f);
        DrawLitSphere(p, (Vector3){ 0.008f, 0.008f, 0.004f }, C8(176, 128, 100), 2, 4);
    }
    /* mouth: flat deadpan line, or a sulky frown */
    Color lip = C8(170, 105, 95);
    if (win) {
        DrawLitCapsule((Vector3){ -0.07f, hy - 0.2f, 0.345f }, (Vector3){ -0.025f, hy - 0.175f, 0.36f }, 0.012f, lip);
        DrawLitCapsule((Vector3){ -0.025f, hy - 0.175f, 0.36f }, (Vector3){ 0.025f, hy - 0.175f, 0.36f }, 0.012f, lip);
        DrawLitCapsule((Vector3){ 0.025f, hy - 0.175f, 0.36f }, (Vector3){ 0.07f, hy - 0.2f, 0.345f }, 0.012f, lip);
    } else {
        DrawLitCapsule((Vector3){ -0.065f, hy - 0.185f, 0.35f }, (Vector3){ 0.065f, hy - 0.185f, 0.35f }, 0.013f, lip);
    }
    XPop();
}
/* towel cape: drapes from the back of the turban to mid-back with a straight hem, swaying a little */
static void DrawQannaCape(const Kart *k, float t, Color tint)
{
    float spd = k ? Clamp(fabsf(k->speed)/22.0f, 0, 1) : 0.2f;
    float steer = k ? k->steer : 0.0f;
    Color teal = ColorTint(QA_TEAL, tint), tealD = ColorTint(ColorScale(QA_TEAL, 0.72f), tint);
    teal.a = tealD.a = tint.a;
    const int N = 6;
    float hy = 1.6f;
    rlDrawRenderBatchActive();
    rlDisableBackfaceCulling();
    rlSetTexture(G.texWhite.id);
    rlBegin(RL_QUADS);
    /* 4 columns across; the outer columns wrap forward round the shoulders */
    const float cu[5] = { -1.0f, -0.55f, 0.0f, 0.55f, 1.0f }, cz[5] = { 0.16f, 0.02f, 0.0f, 0.02f, 0.16f };
    Vector3 prev[5];
    for (int c = 0; c < 5; c++) prev[c] = (Vector3){ cu[c]*0.34f, hy + 0.18f, -0.42f + cz[c]*0.6f };
    for (int i = 1; i <= N; i++) {
        float f = (float)i/N;
        float sway = sinf(t*2.3f + f*1.4f)*0.035f*f - steer*0.08f*f;
        float lift = spd*0.22f*f*f + sinf(t*5.0f + f*3.0f)*0.012f*spd;
        float y = hy + 0.18f - f*0.72f + lift*0.3f;
        float z = -0.43f - 0.14f*f - lift;
        float w = 0.34f + 0.1f*f;
        Vector3 cur[5];
        for (int c = 0; c < 5; c++) cur[c] = (Vector3){ cu[c]*w + sway, y, z + cz[c]*(0.6f + 0.6f*f) };
        for (int c = 0; c < 4; c++) {
            Color k0 = ((i + c) & 1) ? teal : tealD, k1 = ((i + c) & 1) ? tealD : teal;
            rlColor4ub(k0.r, k0.g, k0.b, k0.a); rlVertex3f(prev[c].x, prev[c].y, prev[c].z); rlVertex3f(prev[c + 1].x, prev[c + 1].y, prev[c + 1].z);
            rlColor4ub(k1.r, k1.g, k1.b, k1.a); rlVertex3f(cur[c + 1].x, cur[c + 1].y, cur[c + 1].z); rlVertex3f(cur[c].x, cur[c].y, cur[c].z);
        }
        for (int c = 0; c < 5; c++) prev[c] = cur[c];
    }
    rlEnd();
    rlSetTexture(0);
    rlDrawRenderBatchActive();
    rlEnableBackfaceCulling();
}

static void BakeBegin(MeshBuilder *mb, int mode)
{
    MB_Init(mb);
    if (mode == 1) LitCaptureBegin(mb, 2.2f, 3);      /* ENHANCED: round and smooth */
    else LitCaptureBegin(mb, 1.25f, 1);              /* ORIGINAL: low-poly, softly bevelled */
}
static Model BakeEnd(MeshBuilder *mb)
{
    LitCaptureEnd();
    Model m = MB_BuildModel(mb, G.texWhite, true);
    MB_Free(mb);
    return m;
}

static void EnsureWheel(int mode)
{
    if (WheelOk[mode]) return;
    MeshBuilder mb;
    BakeBegin(&mb, mode);
    DrawLitWheel(1.0f, 0.36f, (Color){ 34, 34, 38, 255 }, (Color){ 190, 195, 205, 255 }, (Color){ 240, 200, 60, 255 }, mode == 1 ? 10 : 8);
    WheelM[mode] = BakeEnd(&mb);
    BakeBegin(&mb, mode);
    DrawSteeringWheelShape();
    SWheelM[mode] = BakeEnd(&mb);
    WheelOk[mode] = true;
}

static KartModels *EnsureKart(int mode, int charId)
{
    KartModels *km = &KM[mode][charId];
    if (km->ok) return km;
    const CharacterDef *cd = &CHARACTERS[charId];
    MeshBuilder mb;
    BakeBegin(&mb, mode); DrawChassis(cd); DrawKartDecor(cd); km->chassis = BakeEnd(&mb);
    recEyes = false;
    if (cd->model3d) {
        bool ea = cd->model3d == MODEL3D_EABHA;
        gPhotoFace = FaceTex[charId].id != 0;
        BakeBegin(&mb, mode); if (ea) EabhaBody(true); else QannaBody(true); km->driverWin = BakeEnd(&mb);
        BakeBegin(&mb, mode); if (ea) EabhaHead(true); else QannaHead(true); km->headWin = BakeEnd(&mb);
        recEyes = false;
        BakeBegin(&mb, mode); if (ea) EabhaBody(false); else QannaBody(false); km->driver = BakeEnd(&mb);
        BakeBegin(&mb, mode); if (ea) EabhaHead(false); else QannaHead(false); km->head = BakeEnd(&mb);
        km->hasWin = true;
        gPhotoFace = false;
    } else {
        BakeBegin(&mb, mode); DrawTorso(cd); km->driver = BakeEnd(&mb);
        BakeBegin(&mb, mode); DrawHead(cd, 0.5f, 0); km->head = BakeEnd(&mb);
    }
    km->hasEyes = recEyes; km->eyeY = recEyeY; km->eyeZ = recEyeZ; km->eyeSpread = recEyeSpread; km->eyeSize = recEyeSize;
    km->lid = gLid;
    km->ok = true;
    TraceLog(LOG_DEBUG, "KART MODEL %s mode %d: chassis %d, driver %d, head %d vertices", cd->name, mode, km->chassis.meshes[0].vertexCount, km->driver.meshes[0].vertexCount, km->head.meshes[0].vertexCount);
    return km;
}

/* N64-style pre-rendered racer: pick the sheet frame from the viewing angle and
   draw an upright camera-facing card in the kart's local space.  Between two
   sheet angles the next frame is cross-faded in on top, so turning the camera
   round a photo racer doesn't 'pop' from one view to the next. */
static void SpriteQuad(Texture2D tex, int frame, int cols, int rows, Vector3 bl, Vector3 br, Vector3 tl, Vector3 tr, unsigned char alpha)
{
    float fw = (float)tex.width/cols, fh = (float)tex.height/rows;
    int col = frame % cols, row = frame/cols;
    float u0 = (col*fw + 0.5f)/tex.width, u1 = ((col + 1)*fw - 0.5f)/tex.width;
    float v0 = (row*fh + 0.5f)/tex.height, v1 = ((row + 1)*fh - 0.5f)/tex.height;
    rlSetTexture(tex.id);
    rlBegin(RL_QUADS);
    rlColor4ub(255, 255, 255, alpha);
    rlTexCoord2f(u0, v1); rlVertex3f(bl.x, bl.y, bl.z);
    rlTexCoord2f(u1, v1); rlVertex3f(br.x, br.y, br.z);
    rlTexCoord2f(u1, v0); rlVertex3f(tr.x, tr.y, tr.z);
    rlTexCoord2f(u0, v0); rlVertex3f(tl.x, tl.y, tl.z);
    rlEnd();
    rlSetTexture(0);
}

static void DrawSpriteDriver(int charId, const Kart *k, float t, unsigned char alpha)
{
    const CharacterDef *cd = &CHARACTERS[charId];
    Texture2D tex = G.charSprite[charId];
    Matrix mv = rlGetMatrixModelview();
    Matrix tf = rlGetMatrixTransform();
    Matrix m = MatrixMultiply(tf, mv);
    Vector3 right = { m.m0, m.m4, m.m8 };
    Vector3 toCam = { m.m2, m.m6, m.m10 };
    right.y = 0;
    float rl = Vector3Length(right);
    right = rl > 1e-5f ? Vector3Scale(right, 1.0f/rl) : (Vector3){ 1, 0, 0 };
    Vector3 tc = { toCam.x, 0, toCam.z };
    float tl_ = Vector3Length(tc);
    tc = tl_ > 1e-5f ? Vector3Scale(tc, 1.0f/tl_) : (Vector3){ 0, 0, 1 };
    int n = cd->spriteAngles;
    int frame = 0, frame2 = -1;
    float mix = 0;
    if (n > 1) {
        float a = atan2f(toCam.x, toCam.z);              /* 0 = camera in front of the kart */
        if (a < 0) a += 2*PI;
        float f = a/(2*PI/n);
        int near = ((int)floorf(f + 0.5f)) % n;
        float d = f - floorf(f + 0.5f);                  /* -0.5 .. 0.5 from the nearest view */
        int other = (near + (d >= 0 ? 1 : n - 1)) % n;
        /* fade the neighbour in over the middle of the gap (full at the hand-over point) */
        float x = Clamp((fabsf(d) - 0.30f)/0.20f, 0, 1);
        mix = x*x*(3 - 2*x)*0.9f;
        frame = (n - near) % n;                          /* sheet rotates clockwise */
        frame2 = (n - other) % n;
    }
    int rows = cd->spriteRows > 1 ? cd->spriteRows : 1;
    int cols = (n + rows - 1)/rows;
    bool mood = charId == gMoodChar;
    /* podium winner acting out a victory quip: front-ish views use the edited win.png face */
    if (mood && G.charWin[charId].id && (n <= 1 || frame <= 1 || frame >= n - 1)) {
        tex = G.charWin[charId]; frame = 0; rows = 1; cols = 1; frame2 = -1;
    }
    if (cols < 1) cols = 1;
    float fw = (float)tex.width/cols, fh = (float)tex.height/rows;
    float h = cd->spriteSize, w = h*fw/fh;
    /* alive: a little bob with speed, lean + slide into turns, stretch in the air, squash on landing */
    float spd = k ? Clamp(fabsf(k->speed)/20.0f, 0, 1) : 0;
    float bob = k ? sinf(t*12.0f)*0.025f*spd + (k->grounded ? 0 : 0.04f) : 0.02f*sinf(t*3.0f);
    float steer = k ? k->steer : 0;
    float lean = -steer*0.16f;
    float slide = steer*0.07f;
    float sy = 1.0f, sx = 1.0f;
    if (k) {
        if (!k->grounded) sy += Clamp(k->vy*0.012f, -0.10f, 0.10f);
        sy -= k->squash*0.25f; sx += k->squash*0.18f;
        if (k->spinTimer > 0) sy *= 1.0f + 0.05f*sinf(t*30.0f);
    }
    if (mood && cd->quipStyle == QUIP_HAPPY) {           /* "Car!": happy bounce */
        float b = fabsf(sinf(t*7.0f));
        bob += 0.08f*b; sy *= 1.0f + 0.03f*b; sx *= 1.0f - 0.02f*b;
    } else if (mood && cd->quipStyle == QUIP_SLEEPY) {   /* sleepy, grumpy sway */
        lean += 0.05f*sinf(t*1.3f); sy *= 0.985f;
    } else if (cd->quipStyle == QUIP_SLEEPY && k) {      /* dozing at the wheel */
        lean += 0.02f*sinf(t*1.1f);
    }
    h *= sy; w *= sx;
    Vector3 base = { slide*right.x, 0.47f + cd->spriteSeat + bob, -0.2f + slide*right.z };
    Vector3 up = { lean*right.x, 1, lean*right.z };
    Vector3 bl = Vector3Add(base, Vector3Scale(right, -w*0.5f));
    Vector3 br = Vector3Add(base, Vector3Scale(right, w*0.5f));
    Vector3 tl = Vector3Add(bl, Vector3Scale(up, h)), tr = Vector3Add(br, Vector3Scale(up, h));
    SpriteQuad(tex, frame, cols, rows, bl, br, tl, tr, alpha);
    if (frame2 >= 0 && mix > 0.02f) {
        Vector3 e = Vector3Scale(tc, 0.004f);            /* a hair nearer the camera: no z-fighting */
        SpriteQuad(tex, frame2, cols, rows, Vector3Add(bl, e), Vector3Add(br, e), Vector3Add(tl, e), Vector3Add(tr, e),
                   (unsigned char)(alpha*mix));
    }
}

/* ------------------------------------------------------------------ */
/* Pre-rendered sprite racers (ORIGINAL mode), MK64 style:              */
/* at startup every racer is rendered from the HD (ENHANCED) model into  */
/* a sprite sheet: 24 angles x 3 steering poses, 256px supersampled to   */
/* 128px cells, then given a dark outline and a saturation lift.         */
/* ------------------------------------------------------------------ */
#define SPR_ANG 24
#define SPR_POSE 3
#define SPR_CELL 192
#define SPR_COLS 12
#define SPR_ROWS (SPR_POSE*SPR_ANG/SPR_COLS)
#define SPR_WORLD 4.7f
#define SPR_CY 1.0f
#define SPR_PITCH (15.0f*DEG2RAD)
static Texture2D SprTex[MAX_CHARACTERS];
static bool SprOk[MAX_CHARACTERS];
static int gForceMode = -1;
static void DrawKartBody(int charId, const Kart *k, float t, Color tint);

static void BuildSpriteSheet(int charId)
{
    RenderTexture2D big = LoadRenderTexture(SPR_COLS*SPR_CELL, SPR_ROWS*SPR_CELL);
    RenderTexture2D cell = LoadRenderTexture(SPR_CELL*2, SPR_CELL*2);
    SetTextureFilter(cell.texture, TEXTURE_FILTER_BILINEAR);
    BeginTextureMode(big); ClearBackground(BLANK); EndTextureMode();
    for (int pose = 0; pose < SPR_POSE; pose++) {
        for (int a = 0; a < SPR_ANG; a++) {
            float ang = a*2*PI/SPR_ANG;
            Camera3D c = { 0 };
            c.target = (Vector3){ 0, SPR_CY, 0 };
            Vector3 dir = { sinf(ang)*cosf(SPR_PITCH), sinf(SPR_PITCH), cosf(ang)*cosf(SPR_PITCH) };
            c.position = Vector3Add(c.target, Vector3Scale(dir, 40.0f));
            c.up = (Vector3){ 0, 1, 0 };
            c.fovy = SPR_WORLD;
            c.projection = CAMERA_ORTHOGRAPHIC;
            Kart k;
            memset(&k, 0, sizeof(k));
            k.scale = 1; k.charId = charId;
            k.steer = pose == 0 ? 0.0f : pose == 1 ? 1.0f : -1.0f;
            k.wheelRot = a*0.7f;
            BeginTextureMode(cell);
            ClearBackground(BLANK);
            BeginMode3D(c);
            rlDisableBackfaceCulling();
            gForceMode = 1;
            DrawKartBody(charId, &k, 0.5f, WHITE);
            gForceMode = -1;
            rlDrawRenderBatchActive();
            rlEnableBackfaceCulling();
            EndMode3D();
            EndTextureMode();
            BeginTextureMode(big);
            rlDrawRenderBatchActive();
            rlDisableColorBlend();
            DrawTexturePro(cell.texture, (Rectangle){ 0, 0, (float)cell.texture.width, -(float)cell.texture.height },
                           (Rectangle){ (float)((a % SPR_COLS)*SPR_CELL), (float)((pose*(SPR_ANG/SPR_COLS) + a/SPR_COLS)*SPR_CELL), SPR_CELL, SPR_CELL }, (Vector2){ 0, 0 }, 0, WHITE);
            rlDrawRenderBatchActive();
            rlEnableColorBlend();
            EndTextureMode();
        }
    }
    Image img = LoadImageFromTexture(big.texture);
    ImageFlipVertical(&img);
    ImageFormat(&img, PIXELFORMAT_UNCOMPRESSED_R8G8B8A8);
    int w = img.width, h = img.height;
    Color *px = (Color *)img.data;
    unsigned char *al = (unsigned char *)MemAlloc(w*h);
    for (int i = 0; i < w*h; i++) al[i] = px[i].a;
    for (int y = 0; y < h; y++) for (int x = 0; x < w; x++) {
        Color *p = &px[y*w + x];
        if (al[y*w + x] >= 140) {
            /* un-premultiply edge darkening, lift saturation a touch */
            float r = p->r, g = p->g, b = p->b;
            if (p->a < 255) { float f = 255.0f/p->a; r *= f; g *= f; b *= f; }
            float l = 0.299f*r + 0.587f*g + 0.114f*b;
            r = l + (r - l)*1.08f; g = l + (g - l)*1.08f; b = l + (b - l)*1.08f;
            p->r = (unsigned char)Clamp(r, 0, 255); p->g = (unsigned char)Clamp(g, 0, 255); p->b = (unsigned char)Clamp(b, 0, 255);
            p->a = 255;
            continue;
        }
        /* outline: 1px dark ring, soft second ring */
        int best = 0;
        int cx = x % SPR_CELL, cy = y % SPR_CELL;
        for (int dy = -2; dy <= 2; dy++) for (int dx = -2; dx <= 2; dx++) {
            int nx = cx + dx, ny = cy + dy;
            if (nx < 0 || ny < 0 || nx >= SPR_CELL || ny >= SPR_CELL) continue;
            if (al[(y + dy)*w + x + dx] < 140) continue;
            int d2 = dx*dx + dy*dy;
            int v = d2 <= 2 ? 2 : (d2 <= 5 ? 1 : 0);
            if (v > best) best = v;
        }
        if (best == 2) *p = (Color){ 24, 18, 42, 240 };
        else if (best == 1) *p = (Color){ 24, 18, 42, 90 };
        else *p = (Color){ 24, 18, 42, 0 };
    }
    MemFree(al);
    SprTex[charId] = LoadTextureFromImage(img);
    GenTextureMipmaps(&SprTex[charId]);
    SetTextureFilter(SprTex[charId], TEXTURE_FILTER_TRILINEAR);
    SetTextureWrap(SprTex[charId], TEXTURE_WRAP_CLAMP);
    UnloadImage(img);
    UnloadRenderTexture(cell);
    UnloadRenderTexture(big);
    SprOk[charId] = true;
}

/* square head shots for the character-select grid: built-in racers are rendered from their HD
   model, photo racers use the portrait.png made by tools/make_character.py */
static void MakePortraits(void)
{
    RenderTexture2D rt = LoadRenderTexture(192, 192);
    for (int i = 0; i < NUM_CHARACTERS; i++) {
        if (G.charPortrait[i].id) continue;
        const CharacterDef *cd = &CHARACTERS[i];
        Camera3D c = { 0 };
        float hy = cd->spriteAngles > 0 ? 0.47f + cd->spriteSeat + cd->spriteSize*0.72f : HeadYOf(cd);
        c.position = (Vector3){ 0.9f, hy + 0.35f, 3.3f };
        c.target = (Vector3){ 0, hy - 0.08f, 0 };
        c.up = (Vector3){ 0, 1, 0 };
        c.fovy = 27; c.projection = CAMERA_PERSPECTIVE;
        Kart k; memset(&k, 0, sizeof k); k.scale = 1; k.charId = i; k.grounded = true;
        BeginTextureMode(rt);
        ClearBackground(BLANK);
        BeginMode3D(c);
        rlDisableBackfaceCulling();
        gForceMode = 1;
        DrawKartBody(i, &k, 0.5f, WHITE);
        gForceMode = -1;
        rlDrawRenderBatchActive();
        rlEnableBackfaceCulling();
        EndMode3D();
        EndTextureMode();
        Image img = LoadImageFromTexture(rt.texture);
        ImageFlipVertical(&img);
        G.charPortrait[i] = LoadTextureFromImage(img);
        SetTextureFilter(G.charPortrait[i], TEXTURE_FILTER_BILINEAR);
        UnloadImage(img);
    }
    UnloadRenderTexture(rt);
}

/* win cards for the 3D photo racers: the model rendered in its win pose (arms up / arms folded,
   mood face), so the results screen never shows a photo */
static void MakeWinCards(void)
{
    const int W = 320, H = 400;
    RenderTexture2D rt = LoadRenderTexture(W, H);
    for (int i = 0; i < NUM_CHARACTERS; i++) {
        CharacterDef *cd = &CHARACTERS[i];
        if (!cd->model3d) continue;
        float hy = HeadYOf(cd);
        Camera3D c = { 0 };
        c.position = (Vector3){ 1.25f, hy + 0.25f, 4.4f };
        c.target = (Vector3){ 0.05f, hy - 0.42f, 0 };
        c.up = (Vector3){ 0, 1, 0 };
        c.fovy = 34; c.projection = CAMERA_PERSPECTIVE;
        Kart k; memset(&k, 0, sizeof k); k.scale = 1; k.charId = i; k.grounded = true;
        int keep = gMoodChar; gMoodChar = i;
        BeginTextureMode(rt);
        ClearBackground(BLANK);
        BeginMode3D(c);
        rlDisableBackfaceCulling();
        gForceMode = 1;
        DrawKartBody(i, &k, 0.6f, WHITE);
        gForceMode = -1;
        rlDrawRenderBatchActive();
        rlEnableBackfaceCulling();
        EndMode3D();
        EndTextureMode();
        gMoodChar = keep;
        Vector2 f = GetWorldToScreenEx((Vector3){ 0, hy - 0.02f, 0.35f }, c, W, H);
        cd->faceX = Clamp(f.x/W, 0, 1); cd->faceY = Clamp(f.y/H, 0, 1);
        Image img = LoadImageFromTexture(rt.texture);
        ImageFlipVertical(&img);
        if (G.charWin[i].id) UnloadTexture(G.charWin[i]);
        G.charWin[i] = LoadTextureFromImage(img);
        SetTextureFilter(G.charWin[i], TEXTURE_FILTER_BILINEAR);
        SetTextureWrap(G.charWin[i], TEXTURE_WRAP_CLAMP);
        if (G.autotest) ExportImage(img, TextFormat("%s/wincard_%d.png", G.shotDir[0] ? G.shotDir : ".", i));
        UnloadImage(img);
    }
    UnloadRenderTexture(rt);
}

void CharactersEnsureSprites(void)
{
    double t0 = GetTime();
    int n = 0;
    for (int i = 0; i < NUM_CHARACTERS; i++) {
        if (SprOk[i] || CHARACTERS[i].spriteAngles > 0) continue;
        BuildSpriteSheet(i);
        n++;
    }
    if (n) TraceLog(LOG_INFO, "SPRITES: pre-rendered %d racers (%dx%d sheets) in %.2fs", n, SPR_COLS*SPR_CELL, SPR_ROWS*SPR_CELL, GetTime() - t0);
}

static void DrawKartSprite(int charId, const Kart *k, Color tint)
{
    float s = k->scale, sq = k->squash;
    Vector3 cam = G.curCam.position;
    Vector3 anchor = { k->pos.x, k->pos.y + SPR_CY*s*(1.0f - sq*0.6f), k->pos.z };
    Vector3 toCam = Vector3Subtract(cam, anchor);
    float D = Vector3Length(toCam);
    if (D < 0.01f) return;
    Vector3 v = Vector3Scale(toCam, 1.0f/D);
    float yaw = k->heading + k->visYaw + k->spinAngle;
    float lx = toCam.x*cosf(yaw) - toCam.z*sinf(yaw);
    float lz = toCam.x*sinf(yaw) + toCam.z*cosf(yaw);
    float a = atan2f(lx, lz);
    if (a < 0) a += 2*PI;
    int frame = ((int)floorf(a/(2*PI/SPR_ANG) + 0.5f)) % SPR_ANG;
    float st = k->steer;
    if (k->driftState == 2) st = (float)k->driftDir;
    int pose = st > 0.35f ? 1 : (st < -0.35f ? 2 : 0);
    /* pull the card toward the camera so it doesn't sink into the road, rescale to compensate */
    float shift = 1.7f*s;
    if (shift > D - 0.6f) shift = D - 0.6f;
    if (shift < 0) shift = 0;
    float f = (D - shift)/D;
    Vector3 c = Vector3Add(anchor, Vector3Scale(v, shift));
    Vector3 right = Vector3CrossProduct((Vector3){ 0, 1, 0 }, v);
    float rl = Vector3Length(right);
    if (rl < 1e-4f) right = (Vector3){ 1, 0, 0 }; else right = Vector3Scale(right, 1.0f/rl);
    Vector3 up = Vector3CrossProduct(v, right);
    float hw = SPR_WORLD*0.5f*s*f*(1.0f + sq*0.4f), hh = SPR_WORLD*0.5f*s*f*(1.0f - sq*0.6f);
    Vector3 R = Vector3Scale(right, hw), U = Vector3Scale(up, hh);
    float W = (float)SprTex[charId].width, H = (float)SprTex[charId].height;
    int col = frame % SPR_COLS, row = pose*(SPR_ANG/SPR_COLS) + frame/SPR_COLS;
    float u0 = (col*SPR_CELL + 0.5f)/W, u1 = ((col + 1)*SPR_CELL - 0.5f)/W;
    float v0 = (row*SPR_CELL + 0.5f)/H, v1 = ((row + 1)*SPR_CELL - 0.5f)/H;
    rlSetTexture(SprTex[charId].id);
    rlBegin(RL_QUADS);
    rlColor4ub(tint.r, tint.g, tint.b, tint.a);
    rlNormal3f(v.x, v.y, v.z);
    rlTexCoord2f(u0, v0); rlVertex3f(c.x - R.x + U.x, c.y - R.y + U.y, c.z - R.z + U.z);
    rlTexCoord2f(u0, v1); rlVertex3f(c.x - R.x - U.x, c.y - R.y - U.y, c.z - R.z - U.z);
    rlTexCoord2f(u1, v1); rlVertex3f(c.x + R.x - U.x, c.y + R.y - U.y, c.z + R.z - U.z);
    rlTexCoord2f(u1, v0); rlVertex3f(c.x + R.x + U.x, c.y + R.y + U.y, c.z + R.z + U.z);
    rlEnd();
    rlSetTexture(0);
}

/* textured decal quad: p0 = bottom-left, du = along the text, dv = up */
static void DecalQuad(Vector3 p0, Vector3 du, Vector3 dv, float v0, float v1, Color tint)
{
    rlTexCoord2f(0, v1); rlVertex3f(p0.x, p0.y, p0.z);
    rlTexCoord2f(1, v1); rlVertex3f(p0.x + du.x, p0.y + du.y, p0.z + du.z);
    rlTexCoord2f(1, v0); rlVertex3f(p0.x + du.x + dv.x, p0.y + du.y + dv.y, p0.z + du.z + dv.z);
    rlTexCoord2f(0, v0); rlVertex3f(p0.x + dv.x, p0.y + dv.y, p0.z + dv.z);
}

/* photo-racer kart decals: a big banner on the rear wing (what the chase cam sees) + strips on the side pods */
static void DrawKartDecals(int charId, float t, Color tint)
{
    const CharacterDef *cd = &CHARACTERS[charId];
    Texture2D tex = G.charDecal[charId];
    if (!tex.id) return;
    int nf = cd->decalFrames > 1 ? cd->decalFrames : 1;
    int f = nf > 1 ? ((int)(t*2.6f)) % nf : 0;          /* "I'M ANNOYING" blinks between its two colourways */
    float v0 = (float)f/nf + 0.5f/tex.height, v1 = (float)(f + 1)/nf - 0.5f/tex.height;
    float aspect = (float)tex.width/(tex.height/(float)nf);
    rlDrawRenderBatchActive();
    rlDisableBackfaceCulling();
    rlSetTexture(tex.id);
    rlBegin(RL_QUADS);
    rlColor4ub(tint.r, tint.g, tint.b, tint.a);
    /* rear wing banner (on the board baked by DrawKartDecor); text reads left->right from behind */
    float bw = 1.42f, bh = bw/aspect;
    DecalQuad((Vector3){ bw*0.5f, 1.19f, -1.472f }, (Vector3){ -bw, 0, 0 }, (Vector3){ 0, bh, 0 }, v0, v1, tint);
    /* side pods (outside faces), readable from each side */
    float sw = 0.8f, sh = sw/aspect;
    DecalQuad((Vector3){ 0.735f, 0.3f, 0.38f }, (Vector3){ 0, 0, -sw }, (Vector3){ 0, sh, 0 }, v0, v1, tint);
    DecalQuad((Vector3){ -0.735f, 0.3f, -0.42f }, (Vector3){ 0, 0, sw }, (Vector3){ 0, sh, 0 }, v0, v1, tint);
    rlEnd();
    rlSetTexture(0);
    rlDrawRenderBatchActive();
    rlEnableBackfaceCulling();
}

/* v7 real face: the photo crop laid on the front of the 3D head as a curved patch that hugs the
   head's ellipsoids (orthographic projection along +Z), so it reads as a face from the front,
   foreshortens naturally from the side and is hidden by the hair / towel from behind. */
typedef struct { Vector3 c, r; } FaceEll;
static float FaceFrontZ(const FaceEll *e, int n, float x, float y)
{
    float best = -1e9f;
    for (int i = 0; i < n; i++) {
        float q = 1.0f - (x/e[i].r.x)*(x/e[i].r.x) - ((y - e[i].c.y)/e[i].r.y)*((y - e[i].c.y)/e[i].r.y);
        if (q <= 0) continue;
        float z = e[i].c.z + e[i].r.z*sqrtf(q);
        if (z > best) best = z;
    }
    return best;
}
static void DrawPhotoFace(int charId, bool win, Color tint)
{
    const CharacterDef *cd = &CHARACTERS[charId];
    Texture2D tex = win ? FaceWinTex[charId] : FaceTex[charId];
    if (!tex.id) return;
    FaceEll e[2]; float cy, hw, hh, lift = 0.014f;
    if (cd->model3d == MODEL3D_EABHA) {
        float hy = 1.5f;
        e[0] = (FaceEll){ { 0, hy, 0 }, { 0.43f, 0.45f, 0.42f } };
        e[1] = (FaceEll){ { 0, hy - 0.14f, 0.04f }, { 0.37f, 0.22f, 0.33f } };
        hw = 0.27f; hh = 0.336f; cy = hy - 0.06f;
    } else {
        float hy = 1.6f;
        e[0] = (FaceEll){ { 0, hy, 0.02f }, { 0.33f, 0.42f, 0.36f } };
        e[1] = (FaceEll){ { 0, hy - 0.2f, 0.04f }, { 0.25f, 0.19f, 0.27f } };
        hw = 0.285f; hh = 0.355f; cy = hy - 0.045f;
    }
    const int NX = 10, NY = 12;
    rlDrawRenderBatchActive();
    rlSetTexture(tex.id);
    rlBegin(RL_QUADS);
    rlColor4ub(tint.r, tint.g, tint.b, tint.a);
    for (int j = 0; j < NY; j++) for (int i = 0; i < NX; i++) {
        float us[4] = { (float)i/NX, (float)(i + 1)/NX, (float)(i + 1)/NX, (float)i/NX };
        float vs[4] = { (float)(j + 1)/NY, (float)(j + 1)/NY, (float)j/NY, (float)j/NY };
        for (int c = 0; c < 4; c++) {
            float x = (us[c]*2 - 1)*hw, y = cy + (1 - vs[c]*2)*hh;
            float z = FaceFrontZ(e, 2, x, y);
            if (z < -1e8f) z = e[0].c.z;   /* off the head (transparent corner of the oval) */
            rlTexCoord2f(us[c], vs[c]);
            rlNormal3f(0, 0, 1);
            rlVertex3f(x, y, z + lift);
        }
    }
    rlEnd();
    rlSetTexture(0);
    rlDrawRenderBatchActive();
}

/* Draws kart + driver at the origin facing +Z (caller sets the transform) */
static void DrawKartBody(int charId, const Kart *k, float t, Color tint)
{
    const CharacterDef *cd = &CHARACTERS[charId];
    int mode = gForceMode >= 0 ? gForceMode : (G.settings.visualMode == 1 ? 1 : 0);
    KartModels *km = EnsureKart(mode, charId);
    EnsureWheel(mode);
    float steer = k ? k->steer : 0.0f;
    float wheelRot = k ? k->wheelRot : t*10.0f;
    bool ghost = tint.a < 255;
    Vector3 o = { 0, 0, 0 };

    DrawModel(km->chassis, o, 1.0f, tint);
    /* steering wheel */
    bool photoDriver = cd->spriteAngles > 0 && G.charSprite[charId].id;
    rlPushMatrix();
    if (photoDriver) { rlTranslatef(0, 0.72f, 0.62f); rlRotatef(-40.0f, 1, 0, 0); rlScalef(0.8f, 0.8f, 0.8f); }   /* low wheel: keeps the photo driver's chest visible */
    else rlTranslatef(0, 0.95f, 0.45f);
    if (!photoDriver) rlRotatef(-28.0f, 1, 0, 0);
    rlRotatef(-steer*40.0f, 0, 0, 1);
    DrawModel(SWheelM[mode], o, 1.0f, tint);
    rlPopMatrix();
    /* wheels */
    for (int i = 0; i < 4; i++) {
        float x = (i & 1) ? 0.74f : -0.74f;
        float z = (i & 2) ? 0.72f : -0.75f;
        float r = (i & 2) ? 0.3f : 0.36f;
        rlPushMatrix();
        rlTranslatef(x, r, z);
        if (i & 2) rlRotatef(-steer*22.0f, 0, 1, 0);
        rlRotatef(wheelRot*RAD2DEG, 1, 0, 0);
        rlScalef((i & 2) ? 0.9f : 1.0f, r, r);
        DrawModel(WheelM[mode], o, 1.0f, tint);
        rlPopMatrix();
    }
    if (cd->model3d) {
        if (cd->model3d == MODEL3D_QANNA) DrawQannaCape(k, t, tint);
        if (cd->kartStyle == KART_STYLE_RATTLE) DrawToyStrawberry(k, t, tint);
        DrawKartDecals(charId, t, tint);
    }
    if (cd->spriteAngles > 0 && G.charSprite[charId].id) {
        if (cd->kartStyle == KART_STYLE_SPA) DrawTowelTail(cd, k, t, tint);
        if (cd->kartStyle == KART_STYLE_RATTLE) DrawToyStrawberry(k, t, tint);
        DrawKartDecals(charId, t, tint);
        DrawSpriteDriver(charId, k, t, tint.a);
        return;
    }
    if (G.charModelLoaded[charId]) {
        DrawModel(G.charModels[charId], (Vector3){ 0, 0.6f, -0.15f }, 1.0f, tint);
        return;
    }
    float hit = k ? k->spinTimer : 0.0f;
    rlPushMatrix();
    rlTranslatef(0, 0.6f, 0); rlRotatef(-steer*5.0f, 0, 0, 1); rlTranslatef(0, -0.6f, 0);
    bool winPose = km->hasWin && charId == gMoodChar;
    DrawModel(winPose ? km->driverWin : km->driver, o, 1.0f, tint);
    /* head leans into the turn, wobbles when hit, jelly heads squish */
    rlTranslatef(0, 1.25f, 0);
    rlRotatef(steer*12.0f, 0, 0, 1);
    rlRotatef(hit > 0 ? sinf(t*30)*20.0f : 0.0f, 1, 0, 0);
    rlTranslatef(0, -1.25f, 0);
    if (cd->head == HEAD_CUBE || cd->head == HEAD_BLOB) {
        float w = 1.0f + (cd->head == HEAD_BLOB ? 0.1f : 0.05f)*sinf(t*(cd->head == HEAD_BLOB ? 6.0f : 9.0f));
        rlTranslatef(0, HEAD_Y, 0); rlScalef(w, 1.0f/w, w); rlTranslatef(0, -HEAD_Y, 0);
    }
    if (cd->model3d == MODEL3D_QANNA && k && !winPose) {   /* sleepy head-nod */
        rlTranslatef(0, 1.3f, 0); rlRotatef(2.5f*sinf(t*1.1f), 1, 0, 0); rlTranslatef(0, -1.3f, 0);
    }
    if (cd->model3d == MODEL3D_EABHA && winPose) {   /* "Car!": happy bounce */
        rlTranslatef(0, 0.07f*fabsf(sinf(t*7.0f)), 0);
    }
    DrawModel(winPose ? km->headWin : km->head, o, 1.0f, tint);
    if (cd->model3d && FaceTex[charId].id) {
        rlPushMatrix();
        if (cd->model3d == MODEL3D_QANNA) { rlTranslatef(0, 1.6f, 0.05f); rlRotatef(7.0f, 1, 0, 0); rlTranslatef(0, -1.6f, 0); }
        DrawPhotoFace(charId, winPose, tint);
        rlPopMatrix();
    }
    if (!ghost && !winPose) {
        /* blink: lids close over the eyes for a moment */
        if (km->hasEyes && fmodf(t, 3.7f) < 0.13f) {
            float s = km->eyeSize;
            for (int e = -1; e <= 1; e += 2)
                DrawLitSphere((Vector3){ e*km->eyeSpread, km->eyeY, km->eyeZ + s*0.12f }, (Vector3){ s*1.12f, s*1.25f, s*0.62f }, km->lid, 3, 6);
        }
        if (cd->head == HEAD_ROBOT) {   /* buzzing wings */
            float f = sinf(t*40.0f)*0.08f;
            Color wc = { 200, 240, 255, 255 };
            DrawLitRoundBox((Vector3){ 0.45f, HEAD_Y - 0.4f + f, -0.38f }, (Vector3){ 0.5f, 0.05f, 0.3f }, 0.02f, 1, 1, wc, wc);
            DrawLitRoundBox((Vector3){ -0.45f, HEAD_Y - 0.4f - f, -0.38f }, (Vector3){ 0.5f, 0.05f, 0.3f }, 0.02f, 1, 1, wc, wc);
        }
        if (cd->hat == HAT_PROPELLER) {
            rlPushMatrix(); rlTranslatef(0, HEAD_Y + 0.6f, 0); rlRotatef(t*900.0f, 0, 1, 0);
            DrawLitBox((Vector3){ 0, 0, 0 }, (Vector3){ 0.9f, 0.03f, 0.1f }, RED);
            rlPopMatrix();
        }
    }
    rlPopMatrix();
}

void DrawCharacterKartTint(int charId, const Kart *k, float t, Color tint)
{
    if (G.kartSprites && G.settings.visualMode == 0 && charId >= 0 && charId < MAX_CHARACTERS && SprOk[charId]) {
        DrawKartSprite(charId, k, tint);
        return;
    }
    float s = k->scale;
    float sq = k->squash;
    rlPushMatrix();
    rlTranslatef(k->pos.x, k->pos.y, k->pos.z);
    rlRotatef((k->heading + k->visYaw + k->spinAngle)*RAD2DEG, 0, 1, 0);
    rlRotatef(k->tilt*RAD2DEG, 0, 0, 1);
    rlScalef(s*(1.0f + sq*0.4f), s*(1.0f - sq*0.6f), s*(1.0f + sq*0.2f));
    DrawKartBody(charId, k, t, tint);
    rlPopMatrix();
}

void DrawCharacterKart(int charId, const Kart *k, float t) { DrawCharacterKartTint(charId, k, t, WHITE); }

void DrawCharacterPreview(int charId, float t)
{
    Kart k;
    memset(&k, 0, sizeof(k));
    k.scale = 1.0f;
    k.heading = t*0.8f;
    k.steer = 0.4f*sinf(t*1.3f);
    k.wheelRot = t*6.0f;
    k.charId = charId;
    DrawCharacterKart(charId, &k, t);
}

/* ------------------------------------------------------------------ */
/* cup trophy (gold / silver / bronze), baked at high detail             */
/* ------------------------------------------------------------------ */
void DrawTrophyModel(int tier, float t)
{
    (void)t;
    if (tier < 0) tier = 0;
    if (tier > 2) tier = 2;
    if (!TrophyOk[tier]) {
        Color c = tier == 0 ? (Color){ 255, 200, 45, 255 } : tier == 1 ? (Color){ 215, 222, 238, 255 } : (Color){ 210, 128, 62, 255 };
        Color wood = { 90, 50, 30, 255 };
        MeshBuilder mb;
        MB_Init(&mb);
        LitCaptureBegin(&mb, 2.5f, 3);
        DrawLitRoundBox((Vector3){ 0, 0.25f, 0 }, (Vector3){ 1.3f, 0.5f, 1.3f }, 0.1f, 1, 1, ColorScale(wood, 1.2f), wood);
        DrawLitRoundBox((Vector3){ 0, 0.56f, 0 }, (Vector3){ 1.0f, 0.14f, 1.0f }, 0.05f, 1, 1, c, ColorScale(c, 0.7f));
        float rad[] = { 0.42f, 0.36f, 0.12f, 0.1f, 0.1f, 0.16f, 0.3f, 0.55f, 0.72f, 0.8f, 0.83f, 0.78f, 0.74f };
        float ys[]  = { 0.63f, 0.72f, 0.8f, 0.95f, 1.25f, 1.38f, 1.5f, 1.72f, 2.05f, 2.4f, 2.62f, 2.64f, 2.5f };
        DrawLitLathe(rad, ys, 13, 16, c);
        for (int s = -1; s <= 1; s += 2) {   /* handles */
            Vector3 prev = { s*0.78f, 2.38f, 0 };
            for (int q = 1; q <= 8; q++) {
                float a = PI*0.5f - PI*q/8.0f;
                Vector3 p = { s*(0.78f + 0.36f*cosf(a)), 2.02f + 0.36f*sinf(a), 0 };
                DrawLitCapsule(prev, p, 0.06f, c);
                prev = p;
            }
        }
        DrawLitSphere((Vector3){ 0, 1.6f, 0.36f }, (Vector3){ 0.16f, 0.16f, 0.05f }, tier == 0 ? (Color){ 255, 60, 80, 255 } : (Color){ 60, 150, 255, 255 }, 4, 8);
        LitCaptureEnd();
        TrophyM[tier] = MB_BuildModel(&mb, G.texWhite, false);
        MB_Free(&mb);
        TrophyOk[tier] = true;
    }
    DrawModel(TrophyM[tier], (Vector3){ 0, 0, 0 }, 1.0f, WHITE);
}

static void PrebuildModels(void)
{
    int mode = G.settings.visualMode == 1 ? 1 : 0;
    EnsureWheel(mode);
    for (int i = 0; i < NUM_CHARACTERS; i++) EnsureKart(mode, i);
}

/* ------------------------------------------------------------------ */
/* victory quips: speech bubble + mood effects, drawn in 2D over the    */
/* results card / podium. head = screen position of the face centre,    */
/* s = face size in pixels, t = seconds since the quip started.         */
/* ------------------------------------------------------------------ */
static void QuipStar(Vector2 p, float r, float rot, Color c)
{
    for (int i = 0; i < 4; i++) {
        float a = rot + i*PI*0.5f, b = a + PI*0.25f, d = a - PI*0.25f;
        Vector2 tip = { p.x + cosf(a)*r, p.y + sinf(a)*r };
        Vector2 s1 = { p.x + cosf(b)*r*0.28f, p.y + sinf(b)*r*0.28f }, s2 = { p.x + cosf(d)*r*0.28f, p.y + sinf(d)*r*0.28f };
        DrawTriangle(tip, s2, s1, c);
        DrawTriangle(tip, s1, s2, c);
    }
    DrawCircleV(p, r*0.22f, WHITE);
}

static void QuipOutlinedText(const char *txt, float x, float y, float fs, Color fill, Color edge, float ow)
{
    Font f = GetFontDefault();
    float sp = fs/10.0f;
    for (int i = 0; i < 8; i++) {
        float a = i*PI/4;
        DrawTextEx(f, txt, (Vector2){ x + cosf(a)*ow, y + sinf(a)*ow }, fs, sp, edge);
    }
    DrawTextEx(f, txt, (Vector2){ x, y }, fs, sp, fill);
}

void DrawQuip(int charId, Vector2 head, float s, float t)
{
    if (charId < 0 || charId >= NUM_CHARACTERS) return;
    const CharacterDef *cd = &CHARACTERS[charId];
    if (!cd->quip) return;
    int W = GetScreenWidth(), H = GetScreenHeight();
    Font f = GetFontDefault();
    bool happy = cd->quipStyle != QUIP_SLEEPY;
    /* word-wrap the quip into at most 3 lines of ~15 characters */
    char lines[3][64] = { { 0 } };
    int nl = 0;
    {
        char buf[192]; snprintf(buf, sizeof buf, "%s", cd->quip);
        char *w = strtok(buf, " ");
        while (w && nl < 3) {
            size_t cur = strlen(lines[nl]);
            if (cur && cur + 1 + strlen(w) > 15) { if (nl == 2) break; nl++; cur = 0; }
            if (cur) strncat(lines[nl], " ", 63 - strlen(lines[nl]));
            strncat(lines[nl], w, 63 - strlen(lines[nl]));
            w = strtok(NULL, " ");
        }
        nl++;
    }
    float fs = happy ? s*0.62f : s*0.30f;
    /* entrance: happy pops in with an elastic bounce and keeps hopping; sleepy sags in slowly and grumbles */
    float pop = happy ? 1.0f - expf(-5.0f*t)*cosf(15.0f*t) : 1.0f - expf(-3.0f*t);
    if (pop < 0.05f) pop = 0.05f;
    float hop = happy ? -fabsf(sinf(t*4.2f))*s*0.16f : 0.0f;
    float shake = happy ? 0.0f : sinf(t*37.0f)*s*0.035f*(0.4f + 0.6f*expf(-2.0f*t));
    float sag = happy ? 0.0f : s*0.05f*sinf(t*1.4f);
    fs *= pop;
    float tw = 0, lh = fs*1.12f;
    for (int i = 0; i < nl; i++) { Vector2 m = MeasureTextEx(f, lines[i], fs, fs/10.0f); if (m.x > tw) tw = m.x; }
    float bw = tw + fs*(happy ? 0.9f : 1.1f), bh = lh*nl + fs*(happy ? 0.55f : 0.8f);
    Vector2 c = { head.x + s*0.95f + bw*0.5f + shake, head.y - s*1.05f - bh*0.5f + hop + sag };
    /* keep it on screen */
    if (c.x + bw*0.5f > W - 8) c.x = W - 8 - bw*0.5f;
    if (c.x - bw*0.5f < 8) c.x = 8 + bw*0.5f;
    if (c.y - bh*0.5f < 8) c.y = 8 + bh*0.5f;
    if (c.y + bh*0.5f > H - 8) c.y = H - 8 - bh*0.5f;
    Rectangle br = { c.x - bw*0.5f, c.y - bh*0.5f, bw, bh };
    Color fill = happy ? (Color){ 255, 250, 253, 255 } : (Color){ 222, 222, 238, 255 };
    Color edge = happy ? (Color){ 255, 105, 175, 255 } : (Color){ 62, 44, 84, 255 };
    Color ink = happy ? (Color){ 255, 80, 160, 255 } : (Color){ 58, 40, 70, 255 };
    float ow = fmaxf(2.0f, s*0.045f);
    /* sleepy: slow 'Zzz' drifting up from the head (drawn behind the bubble) */
    if (!happy) {
        for (int i = 0; i < 4; i++) {
            float ph = fmodf(t*0.45f + i*0.25f, 1.0f);
            float zs = s*(0.22f + 0.38f*ph);
            Vector2 zp = { head.x - s*0.3f - ph*s*0.3f + sinf(ph*7.0f + i)*s*0.08f, head.y - s*0.7f - ph*s*1.1f };
            unsigned char a = (unsigned char)(255*fminf(1.0f, ph*6.0f)*fminf(1.0f, (1.0f - ph)*3.0f));
            QuipOutlinedText("Z", zp.x, zp.y, zs, (Color){ 175, 205, 255, a }, (Color){ 40, 40, 90, a }, fmaxf(1.5f, zs*0.07f));
        }
        /* angry steam puffs venting from both sides of the head */
        for (int side = -1; side <= 1; side += 2)
            for (int i = 0; i < 5; i++) {
                float ph = fmodf(t*1.3f + i*0.2f + (side > 0 ? 0.1f : 0), 1.0f);
                Vector2 sp = { head.x + side*(s*0.62f + ph*s*0.55f), head.y - s*0.25f - ph*s*0.6f + sinf(ph*9.0f)*s*0.04f };
                float r = s*(0.07f + 0.16f*ph);
                unsigned char a = (unsigned char)(220*(1.0f - ph));
                DrawCircleV(sp, r*1.12f, (Color){ 120, 120, 135, (unsigned char)(a/2) });
                DrawCircleV(sp, r, (Color){ 245, 245, 250, a });
            }
    }
    /* tail pointing at the speaker's mouth */
    Vector2 tip = { head.x + s*0.42f, head.y - s*0.18f };
    Vector2 b0 = { br.x + bw*0.18f, br.y + bh - 2 }, b1 = { br.x + bw*0.42f, br.y + bh - 2 };
    if (happy) {
        DrawTriangle(b0, tip, b1, edge);
        DrawTriangle(b1, tip, b0, edge);
        Vector2 ti = { tip.x + (b0.x - tip.x)*0.12f + ow*0.6f, tip.y + (b0.y - tip.y)*0.12f - ow };
        Vector2 c0 = { b0.x + ow*1.2f, b0.y - ow }, c1 = { b1.x - ow*1.2f, b1.y - ow };
        DrawTriangle(c0, ti, c1, fill); DrawTriangle(c1, ti, c0, fill);
    } else {
        /* sleepy thought-ish bubble: a trail of little puffs */
        for (int i = 0; i < 3; i++) {
            float q = (i + 1)/4.0f;
            Vector2 p = { tip.x + (b0.x + bw*0.1f - tip.x)*q, tip.y + (b0.y - tip.y)*q };
            float r = s*(0.05f + 0.035f*i);
            DrawCircleV(p, r + ow, edge); DrawCircleV(p, r, fill);
        }
    }
    float rnd = happy ? 0.9f : 0.55f;
    DrawRectangleRounded((Rectangle){ br.x - ow, br.y - ow, bw + 2*ow, bh + 2*ow }, rnd, 12, edge);
    DrawRectangleRounded(br, rnd, 12, fill);
    if (happy) DrawRectangleRounded((Rectangle){ br.x + bw*0.12f, br.y + bh*0.1f, bw*0.5f, bh*0.16f }, 1.0f, 8, (Color){ 255, 255, 255, 200 });   /* glossy highlight */
    else for (int i = 0; i < 3; i++) {   /* grumpy scribble marks on the bubble rim */
        float x = br.x + bw*(0.78f + i*0.06f), y = br.y - ow*1.2f;
        DrawLineEx((Vector2){ x, y }, (Vector2){ x + s*0.05f, y - s*0.12f }, ow, edge);
    }
    for (int i = 0; i < nl; i++) {
        Vector2 m = MeasureTextEx(f, lines[i], fs, fs/10.0f);
        float lx = c.x - m.x*0.5f, ly = c.y - lh*nl*0.5f + i*lh + (lh - fs)*0.5f;
        if (!happy) ly += sinf(t*2.0f + i*1.3f)*s*0.015f;        /* drowsy wobble */
        if (happy) QuipOutlinedText(lines[i], lx, ly, fs, ink, WHITE, ow*0.8f);
        else DrawTextEx(f, lines[i], (Vector2){ lx, ly }, fs, fs/10.0f, ink);
    }
    /* happy: twinkly sparkles around the bubble and the baby */
    if (happy) {
        Color sc[4] = { { 255, 230, 90, 255 }, { 255, 150, 210, 255 }, { 150, 215, 255, 255 }, { 255, 255, 255, 255 } };
        for (int i = 0; i < 10; i++) {
            float a = i*0.628f + t*0.9f*(i & 1 ? 1 : -1);
            Vector2 ctr = i < 6 ? c : head;
            float rr = i < 6 ? fmaxf(bw, bh)*0.62f + s*0.08f*sinf(t*3 + i) : s*0.85f;
            Vector2 p = { ctr.x + cosf(a)*rr*(i < 6 ? 1.0f : 1.1f), ctr.y + sinf(a)*rr*(i < 6 ? 0.75f : 1.0f) };
            float tw2 = 0.5f + 0.5f*sinf(t*7.0f + i*1.7f);
            QuipStar(p, s*(0.08f + 0.1f*tw2)*fminf(1.0f, t*3.0f), t*2.0f + i, sc[i % 4]);
        }
    }
}

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
    { "Biscuit",      "A very good boy. Thinks the finish line is a squirrel.",  WEIGHT_MEDIUM, 3.5f, 3.5f, 3.5f, 3.0f, {230,150, 60,255}, {250,245,235,255}, {215, 40, 40,255}, {255,210, 40,255}, HEAD_BEAR,  HAT_FLOPPY_EARS, 1.15f, NULL, 0, 0 },
    { "Prof. Wobble", "Brilliant, jiggly, and 92% gelatin.",                     WEIGHT_LIGHT,  2.5f, 5.0f, 4.5f, 1.5f, { 90,220,110,255}, {240,240,255,255}, {245,245,245,255}, { 60,170, 80,255}, HEAD_CUBE,  HAT_GOGGLES,     1.35f, NULL, 0, 0 },
    { "Nana Nitro",   "Knits at 200 km/h. Has never once used the brakes.",      WEIGHT_MEDIUM, 3.5f, 3.5f, 3.0f, 3.0f, {150, 90,200,255}, {255,215,180,255}, {120, 50,170,255}, {255,160,220,255}, HEAD_ROUND, HAT_BUN,         1.25f, NULL, 0, 0 },
    { "Captain Crumb","Toasted on one side, terrifying on the other.",           WEIGHT_HEAVY,  4.5f, 2.0f, 2.5f, 4.5f, { 70, 50,120,255}, {225,180,110,255}, {130, 80, 40,255}, {230,190, 50,255}, HEAD_TOAST, HAT_PIRATE,      0.80f, NULL, 0, 0 },
    { "Zippy",        "Tiny bee-bot. Runs on honey and pure caffeine.",          WEIGHT_LIGHT,  2.5f, 5.0f, 5.0f, 1.0f, { 40, 40, 40,255}, {255,215, 30,255}, {255,200, 20,255}, { 30, 30, 30,255}, HEAD_ROBOT, HAT_ANTENNA,     1.60f, NULL, 0, 0 },
    { "Gloop",        "A royal slime. Leaves a trail. Doesn't apologise.",       WEIGHT_LIGHT,  3.0f, 4.5f, 4.0f, 1.5f, {170, 70,220,255}, {255,230, 60,255}, { 30,190,190,255}, {255,255,255,255}, HEAD_BLOB,  HAT_CROWN,       1.45f, NULL, 0, 0 },
    { "Big Tony",     "A pasta-loving bear. Will race for meatballs.",           WEIGHT_HEAVY,  5.0f, 1.5f, 2.0f, 5.0f, {140, 90, 50,255}, {255,255,255,255}, { 30,150, 60,255}, {220, 40, 40,255}, HEAD_BEAR,  HAT_CHEF,        0.70f, NULL, 0, 0 },
    { "Frostina",     "Yeti princess of the peaks. Melts hearts, never melts.",  WEIGHT_MEDIUM, 3.5f, 3.0f, 4.0f, 3.0f, {235,245,255,255}, {120,190,255,255}, { 80,170,240,255}, {255,255,255,255}, HEAD_YETI,  HAT_HORNS,       1.05f, NULL, 0, 0 },
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

static void LoadCharacterFolder(const char *dir)
{
    if (NUM_CHARACTERS >= MAX_CHARACTERS) { TraceLog(LOG_WARNING, "CHAR: %s skipped - the limit is %d racers", dir, MAX_CHARACTERS); return; }
    const char *ini = TextFormat("%s/character.ini", dir);
    if (!FileExists(ini)) return;
    char *txt = LoadFileText(ini);
    if (!txt) return;
    CharacterDef cd = CHARACTERS[0];               /* sensible defaults */
    cd.name = Dup(GetFileName(dir));
    cd.tagline = "A custom racer.";
    cd.modelFile = NULL;
    cd.head = HEAD_ROUND; cd.hat = HAT_NONE;
    cd.spriteAngles = 1; cd.spriteSize = 1.35f;
    char sprite[256] = "sprite.png";
    bool ownTag = false;
    for (char *line = txt, *next; line && *line; line = next) {
        next = strchr(line, '\n');
        if (next) *next++ = 0;
        char *l = Trim(line);
        if (!*l || *l == ';' || *l == '#' || *l == '[') continue;
        char *eq = strchr(l, '=');
        if (!eq) continue;
        *eq = 0;
        char *k = Trim(l), *v = Trim(eq + 1);
        if (!strcmp(k, "name")) { free((char *)cd.name); cd.name = Dup(v); }        /* name is always Dup'd */
        else if (!strcmp(k, "tagline")) { if (ownTag) free((char *)cd.tagline); cd.tagline = Dup(v); ownTag = true; }
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
        else if (!strcmp(k, "model")) { free((char *)cd.modelFile); cd.modelFile = Dup(TextFormat("%s/%s", GetFileName(dir), v)); }
    }
    UnloadFileText(txt);
    int id = NUM_CHARACTERS;
    G.charSprite[id] = (Texture2D){ 0 };
    const char *sp = TextFormat("%s/%s", dir, sprite);
    if (FileExists(sp)) {
        G.charSprite[id] = LoadTexture(sp);
        if (G.charSprite[id].id) {
            GenTextureMipmaps(&G.charSprite[id]);
            SetTextureFilter(G.charSprite[id], TEXTURE_FILTER_TRILINEAR);
            SetTextureWrap(G.charSprite[id], TEXTURE_WRAP_CLAMP);
        }
    }
    if (!G.charSprite[id].id && !cd.modelFile) {
        TraceLog(LOG_WARNING, "CHAR: %s has no sprite or model, skipped", dir);
        free((char *)cd.name);
        if (ownTag) free((char *)cd.tagline);
        return;
    }
    if (!G.charSprite[id].id) cd.spriteAngles = 0;
    /* menu colours from the kart if not given */
    CHARACTERS[id] = cd;
    NUM_CHARACTERS++;
    TraceLog(LOG_INFO, "CHAR: loaded '%s' from %s (%d angle sprite)", cd.name, dir, cd.spriteAngles);
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
}

/* ------------------------------------------------------------------ */
/* Cached models. Every racer is baked once per visual mode into a few   */
/* static meshes (chassis, torso, head, wheel, steering wheel) so karts  */
/* cost ~8 draw calls each. ORIGINAL = low-poly with soft bevels,        */
/* ENHANCED = many more segments, fully rounded.                          */
/* ------------------------------------------------------------------ */
typedef struct {
    bool ok;
    Model chassis, driver, head;
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
    DrawLitCapsule((Vector3){ 0, 0.6f, 0.72f }, (Vector3){ 0, 0.9f, 0.47f }, 0.04f, black);                                      /* column */
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
    BakeBegin(&mb, mode); DrawChassis(cd); km->chassis = BakeEnd(&mb);
    BakeBegin(&mb, mode); DrawTorso(cd); km->driver = BakeEnd(&mb);
    recEyes = false;
    BakeBegin(&mb, mode); DrawHead(cd, 0.5f, 0); km->head = BakeEnd(&mb);
    km->hasEyes = recEyes; km->eyeY = recEyeY; km->eyeZ = recEyeZ; km->eyeSpread = recEyeSpread; km->eyeSize = recEyeSize;
    km->lid = gLid;
    km->ok = true;
    TraceLog(LOG_DEBUG, "KART MODEL %s mode %d: chassis %d, driver %d, head %d vertices", cd->name, mode, km->chassis.meshes[0].vertexCount, km->driver.meshes[0].vertexCount, km->head.meshes[0].vertexCount);
    return km;
}

/* N64-style pre-rendered racer: pick the sheet frame from the viewing angle and
   draw an upright camera-facing card in the kart's local space */
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
    int n = cd->spriteAngles;
    int frame = 0;
    if (n > 1) {
        float a = atan2f(toCam.x, toCam.z);              /* 0 = camera in front of the kart */
        if (a < 0) a += 2*PI;
        frame = ((int)floorf(a/(2*PI/n) + 0.5f)) % n;
        frame = (n - frame) % n;                         /* sheet rotates clockwise */
    }
    float fw = (float)tex.width/n, fh = (float)tex.height;
    float h = cd->spriteSize, w = h*fw/fh;
    float bob = k ? sinf(t*12.0f)*0.02f*Clamp(k->speed/20.0f, 0, 1) : 0;
    float lean = k ? -k->steer*0.12f : 0;
    Vector3 base = { 0, 0.55f + bob, -0.2f };
    Vector3 up = { lean*right.x, 1, lean*right.z };
    Vector3 bl = Vector3Add(base, Vector3Scale(right, -w*0.5f));
    Vector3 br = Vector3Add(base, Vector3Scale(right, w*0.5f));
    Vector3 tl = Vector3Add(bl, Vector3Scale(up, h)), tr = Vector3Add(br, Vector3Scale(up, h));
    float u0 = frame*fw/tex.width, u1 = (frame + 1)*fw/tex.width;
    rlSetTexture(tex.id);
    rlBegin(RL_QUADS);
    rlColor4ub(255, 255, 255, alpha);
    rlTexCoord2f(u0, 1); rlVertex3f(bl.x, bl.y, bl.z);
    rlTexCoord2f(u1, 1); rlVertex3f(br.x, br.y, br.z);
    rlTexCoord2f(u1, 0); rlVertex3f(tr.x, tr.y, tr.z);
    rlTexCoord2f(u0, 0); rlVertex3f(tl.x, tl.y, tl.z);
    rlEnd();
    rlSetTexture(0);
}

/* Draws kart + driver at the origin facing +Z (caller sets the transform) */
static void DrawKartBody(int charId, const Kart *k, float t, Color tint)
{
    const CharacterDef *cd = &CHARACTERS[charId];
    int mode = G.settings.visualMode == 1 ? 1 : 0;
    KartModels *km = EnsureKart(mode, charId);
    EnsureWheel(mode);
    float steer = k ? k->steer : 0.0f;
    float wheelRot = k ? k->wheelRot : t*10.0f;
    bool ghost = tint.a < 255;
    Vector3 o = { 0, 0, 0 };

    DrawModel(km->chassis, o, 1.0f, tint);
    /* steering wheel */
    rlPushMatrix(); rlTranslatef(0, 0.95f, 0.45f); rlRotatef(-28.0f, 1, 0, 0); rlRotatef(-steer*40.0f, 0, 0, 1);
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
    if (cd->spriteAngles > 0 && G.charSprite[charId].id) {
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
    DrawModel(km->driver, o, 1.0f, tint);
    /* head leans into the turn, wobbles when hit, jelly heads squish */
    rlTranslatef(0, 1.25f, 0);
    rlRotatef(steer*12.0f, 0, 0, 1);
    rlRotatef(hit > 0 ? sinf(t*30)*20.0f : 0.0f, 1, 0, 0);
    rlTranslatef(0, -1.25f, 0);
    if (cd->head == HEAD_CUBE || cd->head == HEAD_BLOB) {
        float w = 1.0f + (cd->head == HEAD_BLOB ? 0.1f : 0.05f)*sinf(t*(cd->head == HEAD_BLOB ? 6.0f : 9.0f));
        rlTranslatef(0, HEAD_Y, 0); rlScalef(w, 1.0f/w, w); rlTranslatef(0, -HEAD_Y, 0);
    }
    DrawModel(km->head, o, 1.0f, tint);
    if (!ghost) {
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

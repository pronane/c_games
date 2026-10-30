#include "game.h"
#include "input.h"
#include <time.h>
#include "sim.h"
#include "online.h"

// ------------------------------------------------------------------------------------
// Face-off captions.  Defaults here; assets/captions.cfg (one "folder = caption" per line)
// overrides them without recompiling.  Fighters with no entry show their display name.
// ------------------------------------------------------------------------------------
static const char *DEFAULT_CAPTIONS[][2] = {
    { "char_mike",   "Mike \"The Padeller\"" },
    { "char_daragh", "Flynn 'The Padel' Fidder" },
};
#define CAPTIONS_FILE "assets/captions.cfg"

static void CopyStr(char *dst, size_t n, const char *src) {   // truncating strcpy
    size_t l = strlen(src);
    if (l >= n) l = n - 1;
    memcpy(dst, src, l);
    dst[l] = 0;
}

static void Trim(char *t) {
    char *a = t;
    while (*a == ' ' || *a == '\t') a++;
    memmove(t, a, strlen(a) + 1);
    size_t n = strlen(t);
    while (n && (t[n - 1] == ' ' || t[n - 1] == '\t' || t[n - 1] == '\r' || t[n - 1] == '\n')) t[--n] = 0;
}

static void LoadCaptions(Game *g) {
    snprintf(g->vsTitle, sizeof(g->vsTitle), "PADEL WARS");
    for (int i = 0; i < MAX_CHARACTERS; i++) {
        snprintf(g->captions[i], sizeof(g->captions[i]), "%s", g->characters[i].name);
        for (size_t k = 0; k < sizeof(DEFAULT_CAPTIONS) / sizeof(DEFAULT_CAPTIONS[0]); k++)
            if (strcmp(DEFAULT_CAPTIONS[k][0], g->characters[i].folder) == 0)
                snprintf(g->captions[i], sizeof(g->captions[i]), "%s", DEFAULT_CAPTIONS[k][1]);
    }
    FILE *f = fopen(CAPTIONS_FILE, "r");
    if (!f) return;
    char line[256];
    while (fgets(line, sizeof(line), f)) {
        char *eq = strchr(line, '=');
        if (line[0] == '#' || !eq) continue;
        *eq = 0;
        char key[96], val[160];
        CopyStr(key, sizeof(key), line);
        CopyStr(val, sizeof(val), eq + 1);
        Trim(key); Trim(val);
        if (!key[0]) continue;
        if (strcmp(key, "title") == 0) { CopyStr(g->vsTitle, sizeof(g->vsTitle), val); continue; }
        for (int i = 0; i < MAX_CHARACTERS; i++)
            if (strcmp(key, g->characters[i].folder) == 0 || strcmp(key, g->characters[i].name) == 0)
                CopyStr(g->captions[i], sizeof(g->captions[i]), val);
    }
    fclose(f);
    TraceLog(LOG_INFO, "Loaded %s", CAPTIONS_FILE);
}

// Roster + defaults only (no window needed): used by Game_Init and the headless tools.
void Game_InitCore(Game *g) {
    memset(g, 0, sizeof(Game));

    g->characters[0] = (CharacterDef){ "RA",           "char_egypt",  "assets/stages/egypt.png",  "assets/portraits/ra.png" };
    g->characters[1] = (CharacterDef){ "PAUL",         "char1",       "assets/stages/street.png", "assets/portraits/paul.png" };
    g->characters[2] = (CharacterDef){ "DRAGON",       "char_dragon", "assets/stages/japan.png",  "assets/portraits/dragon.png" };
    g->characters[3] = (CharacterDef){ "FLAME",        "char_flame",  "assets/stages/usa.png",    "assets/portraits/flame.png" };
    g->characters[4] = (CharacterDef){ "DANGEROUS DEC","char_dec",    "assets/stages/street.png", "assets/portraits/dec.png" };
    g->characters[5] = (CharacterDef){ "PADEL MIKE",   "char_mike",   "assets/stages/usa.png",    "assets/portraits/mike.png" };
    g->characters[6] = (CharacterDef){ "DARAGH",       "char_daragh", "assets/stages/japan.png",  "assets/portraits/daragh.png" };

    g->selectP1 = 0;
    g->selectP2 = 2;
    g->p1Ready = false;
    g->p2Ready = false;
    g->mode = MODE_1P_VS_CPU;
    g->screen = SCREEN_SELECT;
    g->gameOver = false;
    g->winner = 0;
    g->roundTimer = 99.0f;
    g->paused = false;
}

void Game_Init(Game *g) {
    Game_InitCore(g);
    for (int i = 0; i < MAX_CHARACTERS; i++) {
        if (FileExists(g->characters[i].stageFile)) {
            g->stages[i] = Gfx_LoadTexture(g->characters[i].stageFile);   // mipmapped, trilinear
            g->stageLoaded[i] = g->stages[i].id != 0;
            // a stage is stretched over the whole screen: on a 1080p / 4K TV anything smaller
            // than the display looks soft
            if (g->stageLoaded[i] && (g->stages[i].width < 1920 || g->stages[i].height < 1080))
                TraceLog(LOG_WARNING, "STAGE %s is only %dx%d - use 1920x1080 (or 3840x2160) for a sharp TV picture",
                         g->characters[i].stageFile, g->stages[i].width, g->stages[i].height);
        }
        // select-screen portrait: assets/portraits/... or, failing that, assets/<folder>/portrait.png
        const char *pf = g->characters[i].portraitFile;
        const char *alt = TextFormat("assets/%s/portrait.png", g->characters[i].folder);
        if (!FileExists(pf) && FileExists(alt)) pf = alt;
        if (FileExists(pf)) {
            g->portraits[i] = Gfx_LoadTexture(pf);
            g->portraitLoaded[i] = g->portraits[i].id != 0;
        }
    }
    LoadCaptions(g);
}

static void FreeFaces(Game *g) {
    for (int k = 0; k < 2; k++) {
        if (g->faceOwned[k] && g->faces[k].id) UnloadTexture(g->faces[k]);
        g->faces[k] = (Texture2D){ 0 };
        g->faceOwned[k] = false;
    }
}

// Head-and-shoulders picture for the face-off:
//   1. assets/<folder>/portrait.png  (written by tools/build_sprites.py from the photo)
//   2. the character's assets/portraits/... picture (select screen portrait)
//   3. cut from the first idle frame: find the top of the figure, take the head + shoulders
static void MakeFace(Game *g, const Player *p, int slot) {
    const CharacterDef *c = &g->characters[p->characterIndex];
    g->faceMirror[slot] = (slot == 1);        // sources face right: P2 is mirrored to face P1
    char path[300];
    snprintf(path, sizeof(path), "assets/%s/portrait.png", c->folder);
    if (FileExists(path)) {
        g->faces[slot] = Gfx_LoadTexture(path);
        if (g->faces[slot].id) { g->faceOwned[slot] = true; return; }
    }
    if (g->portraitLoaded[p->characterIndex]) {
        g->faces[slot] = g->portraits[p->characterIndex];
        g->faceOwned[slot] = false;
        g->faceMirror[slot] = false;          // unknown direction: leave hand-made portraits as they are
        return;
    }
    const SpriteSheet *sh = &p->sheets[STATE_IDLE];
    if (sh->texture.id == 0) return;
    Image img = LoadImageFromTexture(sh->texture);       // premultiplied RGBA (gfx.c)
    if (img.data == NULL) return;
    ImageFormat(&img, PIXELFORMAT_UNCOMPRESSED_R8G8B8A8);
    int fw = (int)sh->frameWidth;
    if (fw > img.width || fw <= 0) fw = img.width;
    Color *px = (Color *)img.data;
    int x0 = fw, x1 = -1, y0 = img.height, y1 = -1;
    for (int y = 0; y < img.height; y++)
        for (int x = 0; x < fw; x++)
            if (px[y * img.width + x].a > 60) {
                if (x < x0) x0 = x;
                if (x > x1) x1 = x;
                if (y < y0) y0 = y;
                if (y > y1) y1 = y;
            }
    if (x1 < 0) { UnloadImage(img); return; }
    int H = y1 - y0 + 1;
    // head column: centre of the opaque pixels in the top 12% of the figure
    double sx = 0; long cnt = 0;
    for (int y = y0; y < y0 + H * 12 / 100; y++)
        for (int x = x0; x <= x1; x++)
            if (px[y * img.width + x].a > 60) { sx += x; cnt++; }
    float cx = cnt ? (float)(sx / cnt) : (x0 + x1) * 0.5f;
    float ch = H * 0.36f, cw = ch * 0.82f;
    Rectangle r = { cx - cw * 0.5f, y0 - H * 0.03f, cw, ch };
    if (r.x < 0) r.x = 0;
    if (r.y < 0) r.y = 0;
    if (r.x + r.width > fw) r.x = fw - r.width;
    if (r.x < 0) { r.x = 0; r.width = (float)fw; }
    if (r.y + r.height > img.height) r.height = img.height - r.y;
    ImageCrop(&img, r);
    Texture2D t = LoadTextureFromImage(img);              // already premultiplied
    UnloadImage(img);
    if (t.id) {
        GenTextureMipmaps(&t);
        SetTextureFilter(t, TEXTURE_FILTER_TRILINEAR);
        g->faces[slot] = t;
        g->faceOwned[slot] = true;
    }
}

#define PREFIGHT_TIME 3.6f

// Everything the simulation needs to start a fight (no faces / stage textures).  gpu=false:
// headless (sprite sizes only) for --sim-test / --replay; the values come out the same.
void Game_BeginFightSim(Game *g, uint32_t seed, bool gpu) {
    Player_Init(&g->player1, 300.0f, GROUND_Y, 1, g->selectP1);
    Player_Init(&g->player2, 980.0f, GROUND_Y, -1, g->selectP2);
    g->player1.noGpu = g->player2.noGpu = !gpu;

    // Load sprites for the chosen characters
    // Works even if many PNGs are missing – placeholders will be used + warnings printed
    Player_LoadSprites(&g->player1, "assets", g->characters);
    Player_LoadSprites(&g->player2, "assets", g->characters);

    memset(g->projectiles, 0, sizeof(g->projectiles));
    g->cpuAttackCooldown = 40;
    g->gameOver = false;
    g->winner = 0;
    g->roundTimer = 99.0f;
    g->paused = false;
    g->pauseNote[0] = 0;
    g->padWaitRelease = true;

    // seeded PRNG for the CPU (the only randomness in the fight)
    g->fightSeed = seed;
    Rng_Seed(&g->rng, seed);
    g->simTick = 0;

    // test aid: EF_TEST_HP2=<n> starts player 2 with n health (quick KO / victory tests)
    if (getenv("EF_TEST_HP2")) g->player2.health = atoi(getenv("EF_TEST_HP2"));

    g->prefightTimer = 0.0f;
    g->screen = SCREEN_PREFIGHT;
}

void Game_StartFightSeeded(Game *g, uint32_t seed) {
    // Unload any previous sprites
    Player_UnloadSprites(&g->player1);
    Player_UnloadSprites(&g->player2);

    Game_BeginFightSim(g, seed, true);
    TraceLog(LOG_INFO, "SIM: fight seed %u, config hash %016llx", (unsigned)seed,
             (unsigned long long)Sim_ConfigHash(g));

    // face-off screen first (also in the CPU modes)
    FreeFaces(g);
    MakeFace(g, &g->player1, 0);
    MakeFace(g, &g->player2, 1);
}

static void StartFight(Game *g) {
    // EF_SEED=<n> fixes the CPU's dice (tests / replays); otherwise a fresh seed per fight.
    // Online play: the server sends the seed (online.c calls Game_StartFightSeeded).
    const char *seedEnv = getenv("EF_SEED");
    uint32_t seed = seedEnv ? (uint32_t)strtoul(seedEnv, NULL, 10)
                            : (uint32_t)time(NULL) ^ (uint32_t)(GetTime() * 1000003.0);
    Game_StartFightSeeded(g, seed);
}

void Game_Unload(Game *g) {
    Player_UnloadSprites(&g->player1);
    Player_UnloadSprites(&g->player2);
    FreeFaces(g);
    for (int i = 0; i < MAX_CHARACTERS; i++) {
        if (g->stageLoaded[i]) UnloadTexture(g->stages[i]);
        if (g->portraitLoaded[i]) UnloadTexture(g->portraits[i]);
    }
}

// CPU opponent.  Walks in, keeps facing the human (Player_Update does the facing),
// attacks with every move it has, blocks some incoming attacks and, for characters with
// a projectile special, zones from range.
static void SimpleCPU(Game *g, Player *cpu, const Player *human) {
    cpu->inputLeft = cpu->inputRight = cpu->inputDown = cpu->inputUp = false;
    cpu->inputPunch = cpu->inputKick = cpu->inputSpecial1 = cpu->inputSpecial2 = false;
    cpu->inputBlock = cpu->inputThrow = cpu->inputTaunt = cpu->inputJumpAttack = false;

    float dx = human->position.x - cpu->position.x;
    float dist = fabsf(dx);

    // react to an attack in progress: block ~45% of the time when it can reach us
    if (Player_IsAttacking(human) && dist < 170.0f && Rng_Range(&g->rng, 0, 99) < 35) {
        cpu->inputBlock = true;
        return;
    }
    if (cpu->state == STATE_BLOCK && Player_IsAttacking(human) && dist < 170.0f) {
        cpu->inputBlock = true;   // keep holding a block that already started
        return;
    }

    if (g->cpuAttackCooldown > 0) g->cpuAttackCooldown--;

    if (dist > 125.0f) {
        // approach (sometimes fire the projectile from range instead)
        if (cpu->projectileKind != PROJ_NONE && dist > 300.0f && g->cpuAttackCooldown == 0 &&
            Rng_Range(&g->rng, 0, 99) < 4) {
            if (Rng_Range(&g->rng, 0, 1)) cpu->inputSpecial1 = true; else cpu->inputSpecial2 = true;
            g->cpuAttackCooldown = 70;
            return;
        }
        if (dx > 0) cpu->inputRight = true; else cpu->inputLeft = true;
        if (dist < 260.0f && g->cpuAttackCooldown == 0 && Rng_Range(&g->rng, 0, 99) < 2) {
            cpu->inputUp = true;               // jump in ...
            g->cpuAttackCooldown = 20;
        }
    } else if (dist < 95.0f && Rng_Range(&g->rng, 0, 99) < 3) {
        if (dx > 0) cpu->inputLeft = true; else cpu->inputRight = true;   // make some room
    } else if (g->cpuAttackCooldown == 0) {
        int r = Rng_Range(&g->rng, 0, 99);
        if      (r < 30) cpu->inputPunch = true;
        else if (r < 55) cpu->inputKick = true;
        else if (r < 67) cpu->inputThrow = true;
        else if (r < 77) cpu->inputSpecial1 = true;
        else if (r < 87) cpu->inputSpecial2 = true;
        else if (r < 92) cpu->inputDown = true;
        else if (r < 95) { if (dx > 0) cpu->inputLeft = true; else cpu->inputRight = true; }
        else             cpu->inputUp = true;
        g->cpuAttackCooldown = Rng_Range(&g->rng, 35, 80);
    }
    // ... and attack in the air
    if (!cpu->onGround && cpu->state == STATE_JUMP && dist < 200.0f && Rng_Range(&g->rng, 0, 99) < 8)
        cpu->inputJumpAttack = true;
    if (Rng_Range(&g->rng, 0, 1500) < 1) cpu->inputTaunt = true;
}

static void HitPlayer(Player *def, int dir, int dmg) {
    def->health -= dmg;
    if (def->health < 0) def->health = 0;
    Player_SetState(def, STATE_HIT);
    def->invincible = true;
    def->invincibleTimer = 0.6f;
    def->velocity.x = dir * 6.0f;
    def->velocity.y = -4.0f;
    def->onGround = false;
}

// Launch the projectile of a ranged special on its middle frame
static void SpawnProjectiles(Game *g, Player *p, int owner) {
    if (p->projectileKind == PROJ_NONE || p->projectileFired) return;
    if (p->state != STATE_SPECIAL1 && p->state != STATE_SPECIAL2) return;
    if (Player_Progress(p) < PROJ_LAUNCH_AT) return;    // same moment for every fighter
    p->projectileFired = true;
    for (int i = 0; i < MAX_PROJECTILES; i++) {
        Projectile *pr = &g->projectiles[i];
        if (pr->active) continue;
        bool low = (p->state == STATE_SPECIAL2);
        pr->active = true;
        pr->owner = owner;
        pr->kind = p->projectileKind;
        pr->variant = low ? 1 : 0;
        if (pr->kind == PROJ_BOOK && low) pr->kind = PROJ_CARD;
        if (pr->kind == PROJ_FIRE_BLUE && !low) pr->kind = PROJ_FIRE;   // Dragon: orange / blue, as in his art
        // special 1 = high shot (duck under it), special 2 = low shot (jump over it)
        pr->pos = (Vector2){ p->position.x + p->facing * 85.0f, p->position.y - (low ? 110.0f : 225.0f) };
        pr->vx = p->facing * (low ? PROJ_SPEED_LOW : PROJ_SPEED_HIGH);
        if (pr->kind == PROJ_BUBBLE) {
            // speech bubble out of Daragh's backside (he is bent over, bum towards the opponent)
            pr->origin = (Vector2){ p->position.x + p->facing * 48.0f, p->position.y - 150.0f };
            pr->pos = (Vector2){ p->position.x + p->facing * 95.0f, p->position.y - (low ? 120.0f : 205.0f) };
        }
        pr->spin = 0.0f;
        pr->age = 0.0f;
        break;
    }
}

static void UpdateProjectiles(Game *g, float dt) {
    for (int i = 0; i < MAX_PROJECTILES; i++) {
        Projectile *pr = &g->projectiles[i];
        if (!pr->active) continue;
        pr->pos.x += pr->vx;
        pr->spin += (pr->kind == PROJ_CARD ? 24.0f : 12.0f) * (pr->vx > 0 ? 1.0f : -1.0f);
        if (pr->kind == PROJ_BUBBLE) pr->origin.x += pr->vx * 0.35f;   // tail stretches, then trails
        pr->age += dt;
        if (pr->pos.x < -60.0f || pr->pos.x > SCREEN_WIDTH + 60.0f || pr->age > 4.0f) { pr->active = false; continue; }
        Player *def = (pr->owner == 1) ? &g->player2 : &g->player1;
        // one hit box size for every projectile (the bubble is drawn bigger, but does not
        // reach further than a ball or a fireball)
        Rectangle box = { pr->pos.x - PROJ_BOX * 0.5f, pr->pos.y - PROJ_BOX * 0.5f, PROJ_BOX, PROJ_BOX };
        if (!def->invincible && CheckCollisionRecs(box, def->hurtbox)) {
            pr->active = false;
            if (def->inputBlock && def->onGround) {
                def->health -= PROJ_CHIP;                // chip damage through a block
                if (def->health < 0) def->health = 0;
            } else {
                HitPlayer(def, pr->vx > 0 ? 1 : -1, PROJ_DAMAGE);
            }
        }
    }
    // two projectiles meeting cancel each other out
    for (int i = 0; i < MAX_PROJECTILES; i++)
        for (int j = i + 1; j < MAX_PROJECTILES; j++) {
            Projectile *a = &g->projectiles[i], *b = &g->projectiles[j];
            if (a->active && b->active && a->owner != b->owner &&
                fabsf(a->pos.x - b->pos.x) < 28.0f && fabsf(a->pos.y - b->pos.y) < 40.0f)
                a->active = b->active = false;
        }
}

// smooth filled ellipse (raylib's DrawEllipse uses 36 segments - visibly polygonal on a TV)
static void FillEllipse(Vector2 c, float rx, float ry, Color col) {
    const int N = 72;
    for (int i = 0; i < N; i++) {
        float a0 = 2 * PI * i / N, a1 = 2 * PI * (i + 1) / N;
        DrawTriangle(c, (Vector2){ c.x + cosf(a1) * rx, c.y + sinf(a1) * ry },
                        (Vector2){ c.x + cosf(a0) * rx, c.y + sinf(a0) * ry }, col);
    }
}

static void FillTri(Vector2 a, Vector2 b, Vector2 c, Color col) {
    // raylib wants counter-clockwise order
    if ((b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x) > 0) { Vector2 t = b; b = c; c = t; }
    DrawTriangle(a, b, c, col);
}

// cartoon speech bubble with a tail pointing back at whoever launched it
static void DrawBubble(const Projectile *pr) {
    float dir = pr->vx > 0 ? 1.0f : -1.0f;
    float grow = fminf(1.0f, 0.25f + pr->age * 3.2f);            // pops out of the backside
    Vector2 c = { pr->pos.x, pr->pos.y + sinf(pr->age * 9.0f) * 3.0f };
    float rx = 66.0f * grow, ry = 40.0f * grow, o = 4.0f;
    // tail: from the back-lower part of the bubble towards the launch point (max 80 px)
    Vector2 to = { pr->origin.x - c.x, pr->origin.y - c.y };
    float len = sqrtf(to.x * to.x + to.y * to.y);
    if (len < 1.0f) { to = (Vector2){ -dir, 0.6f }; len = 1.0f; }
    float L = fminf(len, 80.0f * grow + 20.0f);
    Vector2 tip = { c.x + to.x / len * L, c.y + to.y / len * L };
    Vector2 b1 = { c.x - dir * rx * 0.25f, c.y + ry * 0.70f };
    Vector2 b2 = { c.x - dir * rx * 0.70f, c.y + ry * 0.35f };
    // motion puffs
    for (int k = 1; k <= 3; k++)
        FillEllipse((Vector2){ c.x - dir * (rx + 14.0f * k), c.y - 12.0f + 10.0f * k }, 7.0f - k, 7.0f - k,
                    (Color){ 255, 255, 255, (unsigned char)(170 - 40 * k) });
    // black outline (bubble + tail), then white fill
    FillEllipse(c, rx + o, ry + o, BLACK);
    FillTri((Vector2){ b1.x + dir * o, b1.y + o }, (Vector2){ b2.x - dir * o, b2.y - o },
            (Vector2){ tip.x - to.x / len * o * 1.5f, tip.y - to.y / len * o * 1.5f }, BLACK);
    FillTri(b1, b2, tip, RAYWHITE);
    FillEllipse(c, rx, ry, RAYWHITE);
    const char *txt = pr->variant ? "PADEL!" : "PARP!";
    float fs = (pr->variant ? 34.0f : 40.0f) * grow;
    Gfx_DrawTitle(gTitleFont, txt, (Vector2){ c.x, c.y + 2 }, fs, (Color){ 20, 20, 20, 255 }, BLANK, 0);
}

// fireball (Flame: orange, Dragon: blue) - flickering flame tail + hot core
static void DrawFireball(const Projectile *pr) {
    bool blue = (pr->kind == PROJ_FIRE_BLUE);
    float dir = pr->vx > 0 ? 1.0f : -1.0f;
    float grow = fminf(1.0f, 0.4f + pr->age * 4.0f);
    Vector2 c = pr->pos;
    Color outer = blue ? (Color){ 40, 120, 255, 255 } : (Color){ 255, 70, 10, 255 };
    Color mid   = blue ? (Color){ 90, 200, 255, 255 } : (Color){ 255, 160, 30, 255 };
    Color core  = blue ? (Color){ 225, 250, 255, 255 } : (Color){ 255, 240, 170, 255 };
    BeginBlendMode(BLEND_ADDITIVE);
    for (int k = 7; k >= 1; k--) {        // tail: blobs that shrink and wobble behind the ball
        float t = (float)k / 7.0f;
        float wob = sinf(pr->age * 30.0f + k * 1.7f) * 6.0f * t;
        Vector2 q = { c.x - dir * k * 11.0f * grow, c.y + wob };
        float r = (22.0f - k * 2.2f) * grow;
        Color col = outer; col.a = (unsigned char)(150 * (1.0f - t * 0.8f));
        FillEllipse(q, r * 1.2f, r, col);
    }
    float fl = 1.0f + 0.08f * sinf(pr->age * 47.0f);
    Color o2 = outer; o2.a = 200;
    FillEllipse(c, 30.0f * grow * fl, 24.0f * grow * fl, o2);
    Color m2 = mid; m2.a = 230;
    FillEllipse((Vector2){ c.x + dir * 3.0f, c.y }, 21.0f * grow * fl, 17.0f * grow * fl, m2);
    EndBlendMode();
    FillEllipse((Vector2){ c.x + dir * 6.0f, c.y }, 11.0f * grow, 9.0f * grow, core);
}

static void DrawProjectile(const Projectile *pr) {
    Vector2 c = pr->pos;
    float dir = pr->vx > 0 ? 1.0f : -1.0f;
    if (pr->kind == PROJ_BUBBLE) {
        DrawBubble(pr);
    } else if (pr->kind == PROJ_FIRE || pr->kind == PROJ_FIRE_BLUE) {
        DrawFireball(pr);
    } else if (pr->kind == PROJ_BALL) {
        // motion streaks
        for (int k = 1; k <= 4; k++)
            DrawCircleV((Vector2){ c.x - dir * k * 13.0f, c.y }, 15.0f - k * 2.5f,
                        (Color){ 230, 255, 80, (unsigned char)(150 - k * 32) });
        DrawCircleV(c, 16.0f, (Color){ 120, 150, 20, 255 });      // outline
        DrawCircleV(c, 14.0f, (Color){ 214, 240, 50, 255 });      // felt
        DrawCircleV((Vector2){ c.x - 4, c.y - 5 }, 5.0f, (Color){ 245, 255, 160, 200 });
        // white seam that spins
        float a = pr->spin * DEG2RAD;
        Vector2 prev = {0};
        for (int k = 0; k <= 16; k++) {
            float t = -1.6f + 3.2f * k / 16.0f;
            float sx = 9.0f * sinf(t), sy = 12.0f * t / 1.6f * 0.9f + 3.0f * sinf(2 * t);
            Vector2 q = { c.x + sx * cosf(a) - sy * sinf(a), c.y + sx * sinf(a) + sy * cosf(a) };
            if (k) DrawLineEx(prev, q, 2.0f, RAYWHITE);
            prev = q;
        }
    } else {
        bool card = (pr->kind == PROJ_CARD);
        float w = card ? 34.0f : 40.0f, h = card ? 22.0f : 30.0f;
        Color glow = { 190, 90, 255, 70 };
        for (int k = 1; k <= 3; k++)
            DrawCircleV((Vector2){ c.x - dir * k * 16.0f, c.y }, 20.0f - k * 4.0f, glow);
        DrawCircleV(c, 30.0f, (Color){ 170, 70, 255, 60 });
        Rectangle r = { c.x, c.y, w, h };
        if (card) {
            DrawRectanglePro(r, (Vector2){ w / 2, h / 2 }, pr->spin, (Color){ 245, 235, 255, 255 });
            DrawRectanglePro((Rectangle){ c.x, c.y, w - 6, h - 6 }, (Vector2){ (w - 6) / 2, (h - 6) / 2 },
                             pr->spin, (Color){ 140, 40, 220, 255 });
            DrawCircleV(c, 4.0f, GOLD);
        } else {
            DrawRectanglePro((Rectangle){ c.x, c.y, w + 4, h + 4 }, (Vector2){ (w + 4) / 2, (h + 4) / 2 },
                             pr->spin, (Color){ 60, 10, 100, 255 });                    // cover edge
            DrawRectanglePro(r, (Vector2){ w / 2, h / 2 }, pr->spin, (Color){ 128, 40, 200, 255 });
            DrawRectanglePro((Rectangle){ c.x, c.y, w - 10, 5 }, (Vector2){ (w - 10) / 2, -6 },
                             pr->spin, (Color){ 240, 230, 250, 255 });                 // pages
            DrawRectanglePro((Rectangle){ c.x, c.y, 6, h }, (Vector2){ w / 2, h / 2 },
                             pr->spin, GOLD);                                          // spine
        }
    }
}

static void CheckHits(Game *g) {
    Player *p1 = &g->player1;
    Player *p2 = &g->player2;

    if (p1->attackActive && !p2->invincible && !p2->inputBlock) {
        if (CheckCollisionRecs(p1->hitbox, p2->hurtbox)) HitPlayer(p2, p1->facing, MELEE_DAMAGE);
    }

    if (p2->attackActive && !p1->invincible && !p1->inputBlock) {
        if (CheckCollisionRecs(p2->hitbox, p1->hurtbox)) HitPlayer(p1, p2->facing, MELEE_DAMAGE);
    }

    if (p1->health <= 0 && !g->gameOver) {
        g->gameOver = true;
        g->winner = 2;
        Player_SetState(p2, STATE_VICTORY);
        g->screen = SCREEN_RESULT;
    }
    if (p2->health <= 0 && !g->gameOver) {
        g->gameOver = true;
        g->winner = 1;
        Player_SetState(p1, STATE_VICTORY);
        g->screen = SCREEN_RESULT;
    }
}

static void KeepPlayersApart(Player *p1, Player *p2) {
    float distance = p2->position.x - p1->position.x;
    float minDistance = PLAYER_WIDTH;
    if (fabsf(distance) >= minDistance) return;

    float direction = distance >= 0.0f ? 1.0f : -1.0f;
    float overlap = minDistance - fabsf(distance);
    float p1OldX = p1->position.x;
    float p2OldX = p2->position.x;

    p1->position.x -= direction * overlap * 0.5f;
    p2->position.x += direction * overlap * 0.5f;
    if (p1->position.x < 40.0f) p1->position.x = 40.0f;
    if (p1->position.x > SCREEN_WIDTH - 40.0f) p1->position.x = SCREEN_WIDTH - 40.0f;
    if (p2->position.x < 40.0f) p2->position.x = 40.0f;
    if (p2->position.x > SCREEN_WIDTH - 40.0f) p2->position.x = SCREEN_WIDTH - 40.0f;

    if (fabsf(p2->position.x - p1->position.x) < minDistance) {
        if (direction > 0.0f) {
            if (p1->position.x - 40.0f >= overlap) p1->position.x -= overlap;
            else p2->position.x += overlap;
        } else {
            if (SCREEN_WIDTH - 40.0f - p1->position.x >= overlap) p1->position.x += overlap;
            else p2->position.x -= overlap;
        }
    }

    float p1Shift = p1->position.x - p1OldX;
    float p2Shift = p2->position.x - p2OldX;
    p1->hurtbox = Player_GetHurtbox(p1);
    p2->hurtbox = Player_GetHurtbox(p2);
    if (p1->attackActive) p1->hitbox.x += p1Shift;
    if (p2->attackActive) p2->hitbox.x += p2Shift;
}

// ---------- select-screen helpers ----------
#define SEL_COLS 2
// move a cursor around the fighter grid (SEL_COLS columns), wrapping; never lands on an empty cell
static int GridMove(int sel, int dx, int dy) {
    int rows = (MAX_CHARACTERS + SEL_COLS - 1) / SEL_COLS;
    int c = sel % SEL_COLS, r = sel / SEL_COLS;
    if (dx) c = (c + dx + SEL_COLS) % SEL_COLS;
    if (dy) r = (r + dy + rows) % rows;
    int i = r * SEL_COLS + c;
    if (i >= MAX_CHARACTERS) {
        if (dy && !dx) i = (dy > 0) ? c : MAX_CHARACTERS - 1;  // down past the end: wrap to the top
        else i = r * SEL_COLS;                                  // short last row: stay in column 0
        if (i >= MAX_CHARACTERS) i = MAX_CHARACTERS - 1;
    }
    return i;
}

// two independent cursors only in 1P vs 2P with two controllers plugged in (and online: one each)
static bool SelectDual(const Game *g) {
    if (g->mode == MODE_ONLINE) return true;
    return g->mode == MODE_1P_VS_2P && Pad_ForPlayer(1) != PAD_NONE && Pad_ForPlayer(2) != PAD_NONE;
}

// One fixed 1/60 s step of the fight simulation: pre-fight countdown, the fight itself and the
// result poses.  Inputs come only from in[] - no raylib input, no clock, no rand().
void Game_SimTick(Game *g, const InputBits in[2]) {
    const float dt = SIM_DT;
    if (g->paused) return;
    if (g->screen != SCREEN_PREFIGHT && g->screen != SCREEN_FIGHT && g->screen != SCREEN_RESULT) return;
    g->simTick++;

    // ---------- PRE-FIGHT FACE-OFF ----------
    if (g->screen == SCREEN_PREFIGHT) {
        g->prefightTimer += dt;
        bool skip = g->prefightTimer > 0.35f && ((in[0] | in[1]) & IN_CONFIRM);
        if (skip || g->prefightTimer >= PREFIGHT_TIME) {
            g->screen = SCREEN_FIGHT;
            g->padWaitRelease = true;        // the A / Start that skipped must not jump / pause
        }
        return;
    }

    // ---------- FIGHT ----------
    if (g->screen == SCREEN_FIGHT) {
        // one 16-bit mask per fighter (sampled by input.c, or from the network / a replay)
        Input_ToPlayer(&g->player1, in[0]);
        Input_ToPlayer(&g->player2, in[1]);
        if (g->mode == MODE_1P_VS_CPU)      SimpleCPU(g, &g->player2, &g->player1);
        else if (g->mode == MODE_CPU_VS_1P) SimpleCPU(g, &g->player1, &g->player2);

        g->player1.opponentX = g->player2.position.x;
        g->player2.opponentX = g->player1.position.x;
        Player_Update(&g->player1, dt);
        Player_Update(&g->player2, dt);

        KeepPlayersApart(&g->player1, &g->player2);
        SpawnProjectiles(g, &g->player1, 1);
        SpawnProjectiles(g, &g->player2, 2);
        UpdateProjectiles(g, dt);
        CheckHits(g);

        g->roundTimer -= dt;
        if (g->roundTimer <= 0.0f) {
            g->roundTimer = 0.0f;
            g->gameOver = true;
            if (g->player1.health > g->player2.health) g->winner = 1;
            else if (g->player2.health > g->player1.health) g->winner = 2;
            else g->winner = 0;
            if (g->winner) Player_SetState(g->winner == 1 ? &g->player1 : &g->player2, STATE_VICTORY);
            g->screen = SCREEN_RESULT;
        }
        return;
    }

    // ---------- RESULT: keep animating the winner's pose / the loser landing ----------
    if (g->screen == SCREEN_RESULT) {
        // keep animating: the winner's victory pose (Mike keeps flexing), the loser lands
        Player *pl[2] = { &g->player1, &g->player2 };
        for (int k = 0; k < 2; k++) {
            Player *q = pl[k];
            q->inputLeft = q->inputRight = q->inputDown = q->inputUp = false;
            q->inputPunch = q->inputKick = q->inputSpecial1 = q->inputSpecial2 = false;
            q->inputBlock = q->inputThrow = q->inputTaunt = q->inputJumpAttack = false;
            q->opponentX = 0.0f;
            if (q->onGround) q->velocity.x = 0.0f;
            Player_Update(q, dt);
            q->attackActive = false;
        }
        return;
    }
}

// Per-frame (render-rate) menus: select screen, controller test, leaving the result screen.
// Not part of the deterministic simulation.
void Game_Update(Game *g) {
    if (g->paused) return;

    float dt = GetFrameTime();

    if (g->screen == SCREEN_ONLINE) {
        Online_MenuUpdate(g);
        return;
    }

    // ---------- CHARACTER SELECT ----------
    // One shared cursor (keyboard only / one controller / any CPU mode): it picks the LEFT slot
    // first, then jumps to the RIGHT slot.  With two controllers in 1P vs 2P each player has
    // their own cursor.  See SelectDual() / the README for the full control list.
    if (g->screen == SCREEN_SELECT) {
        g->selTime += dt;
        if (g->startPending) {                 // both READY: one frame of "LOADING" then go
            if (++g->startPending > 2) { g->startPending = 0; StartFight(g); }
            return;
        }
        if (g->mode == MODE_ONLINE) {          // our cursor only; the other side comes from the server
            Online_SelectUpdate(g);
            return;
        }
        if (IsKeyPressed(KEY_F1) || Pad_Pressed(PAD_ANY, PB_BACK)) {   // controller test / controls
            g->screen = SCREEN_PADTEST;
            return;
        }
        int modeStep = 0;
        if (IsKeyPressed(KEY_TAB) || IsKeyPressed(KEY_E) || Pad_Pressed(PAD_ANY, PB_RB)) modeStep = 1;
        else if (IsKeyPressed(KEY_Q) || Pad_Pressed(PAD_ANY, PB_LB)) modeStep = MODE_COUNT - 1;
        if (modeStep) {
            g->mode = (g->mode + modeStep) % MODE_COUNT;
            if (g->mode == MODE_ONLINE) { Online_Enter(g); return; }
            g->p1Ready = false;
            g->p2Ready = false;
            return;
        }

        if (SelectDual(g)) {
            // --- two controllers, 1P vs 2P: a cursor each ---
            int *sel[2] = { &g->selectP1, &g->selectP2 };
            bool *rdy[2] = { &g->p1Ready, &g->p2Ready };
            for (int k = 0; k < 2; k++) {
                int ps = Pad_ForPlayer(k + 1);
                bool kl = k == 0 ? IsKeyPressed(KEY_A) : IsKeyPressed(KEY_LEFT);
                bool kr = k == 0 ? IsKeyPressed(KEY_D) : IsKeyPressed(KEY_RIGHT);
                bool ku = k == 0 ? IsKeyPressed(KEY_W) : IsKeyPressed(KEY_UP);
                bool kd = k == 0 ? IsKeyPressed(KEY_S) : IsKeyPressed(KEY_DOWN);
                bool ok = k == 0 ? (IsKeyPressed(KEY_J) || IsKeyPressed(KEY_ENTER))
                                 : (IsKeyPressed(KEY_Z) || IsKeyPressed(KEY_KP_1) || IsKeyPressed(KEY_KP_ENTER));
                bool back = k == 0 ? IsKeyPressed(KEY_BACKSPACE) : IsKeyPressed(KEY_X);
                ok   |= Pad_Pressed(ps, PB_A) || Pad_Pressed(ps, PB_START);
                back |= Pad_Pressed(ps, PB_B);
                if (*rdy[k]) { if (back) *rdy[k] = false; continue; }
                int dx = (kr || Pad_Repeat(ps, PB_RIGHT)) - (kl || Pad_Repeat(ps, PB_LEFT));
                int dy = (kd || Pad_Repeat(ps, PB_DOWN)) - (ku || Pad_Repeat(ps, PB_UP));
                if (dx || dy) *sel[k] = GridMove(*sel[k], dx, dy);
                if (ok) *rdy[k] = true;
            }
        } else {
            // --- one shared cursor: left slot, then right slot ---
            if (g->p1Ready && g->p2Ready) g->p2Ready = false;     // (can't happen, but be safe)
            int slot = g->p1Ready ? 1 : 0;
            int *sel = slot == 0 ? &g->selectP1 : &g->selectP2;
            bool kl = IsKeyPressed(KEY_A) || IsKeyPressed(KEY_LEFT);
            bool kr = IsKeyPressed(KEY_D) || IsKeyPressed(KEY_RIGHT);
            bool ku = IsKeyPressed(KEY_W) || IsKeyPressed(KEY_UP);
            bool kd = IsKeyPressed(KEY_S) || IsKeyPressed(KEY_DOWN);
            int dx = (kr || Pad_Repeat(PAD_ANY, PB_RIGHT)) - (kl || Pad_Repeat(PAD_ANY, PB_LEFT));
            int dy = (kd || Pad_Repeat(PAD_ANY, PB_DOWN)) - (ku || Pad_Repeat(PAD_ANY, PB_UP));
            bool ok = IsKeyPressed(KEY_ENTER) || IsKeyPressed(KEY_KP_ENTER) || IsKeyPressed(KEY_J) ||
                      IsKeyPressed(KEY_Z) || IsKeyPressed(KEY_SPACE) ||
                      Pad_Pressed(PAD_ANY, PB_A) || Pad_Pressed(PAD_ANY, PB_START);
            bool back = IsKeyPressed(KEY_BACKSPACE) || IsKeyPressed(KEY_X) || Pad_Pressed(PAD_ANY, PB_B);
            if (back) {
                if (g->p1Ready) g->p1Ready = false;          // un-ready the last pick
            } else if (ok) {
                if (slot == 0) {
                    g->p1Ready = true;
                    g->selFlash = g->selTime;                // the cursor jumps to the right slot
                } else {
                    g->p2Ready = true;
                }
            } else if (dx || dy) {
                *sel = GridMove(*sel, dx, dy);
            }
        }

        if (g->p1Ready && g->p2Ready) {
            TraceLog(LOG_INFO, "SELECT: both ready (%s vs %s) -> pre-fight",
                     g->characters[g->selectP1].name, g->characters[g->selectP2].name);
            g->startPending = 1;
        }
        return;
    }

    // ---------- CONTROLLER TEST ----------
    if (g->screen == SCREEN_PADTEST) {
        bool startHeld = false;
        for (int i = 0; i < PAD_MAX; i++) {
            const PadState *p = Pad_Get(i);
            if (p->connected && p->down[PB_START] && p->hold[PB_START] >= 1.0f) startHeld = true;
        }
        if (IsKeyPressed(KEY_F1) || IsKeyPressed(KEY_ESCAPE) || IsKeyPressed(KEY_BACKSPACE) || startHeld) {
            g->screen = SCREEN_SELECT;
            g->p1Ready = g->p2Ready = false;
        }
        return;
    }

    // ---------- RESULT ----------  (the poses keep animating in Game_SimTick)
    if (g->screen == SCREEN_RESULT) {
        if (IsKeyPressed(KEY_R) || IsKeyPressed(KEY_ENTER) ||
            Pad_Pressed(PAD_ANY, PB_A) || Pad_Pressed(PAD_ANY, PB_START)) {
            // Back to select (fighter sprites only: stage / portrait textures stay loaded)
            Player_UnloadSprites(&g->player1);
            Player_UnloadSprites(&g->player2);
            FreeFaces(g);
            g->p1Ready = false;
            g->p2Ready = false;
            g->screen = SCREEN_SELECT;
        }
    }
}

static void DrawHealthBar(float x, float y, float width, float height, int health, bool rightSide) {
    DrawRectangle(x, y, width, height, (Color){40, 40, 40, 255});
    float pct = (float)health / (float)MAX_HEALTH;
    float fillW = width * pct;
    Color col = health > 50 ? GREEN : (health > 25 ? ORANGE : RED);

    if (rightSide) {
        DrawRectangle(x + (width - fillW), y, fillW, height, col);
    } else {
        DrawRectangle(x, y, fillW, height, col);
    }
    DrawRectangleLinesEx((Rectangle){x, y, width, height}, 3, WHITE);
}

static float Clamp01(float v) { return v < 0 ? 0 : (v > 1 ? 1 : v); }
static float EaseOutBack(float t) {
    t = Clamp01(t);
    const float c1 = 1.70158f, c3 = c1 + 1.0f;
    return 1.0f + c3 * powf(t - 1.0f, 3) + c1 * powf(t - 1.0f, 2);
}
static float EaseOutCubic(float t) { t = Clamp01(t); return 1.0f - powf(1.0f - t, 3); }

// one fighter's card: face (cover-fit, premultiplied), frame, caption
// draw a (premultiplied) portrait to cover dst, keeping its aspect ratio (top-biased crop)
static void DrawPortraitFit(Texture2D t, Rectangle dst) {
    float sa = (float)t.width / t.height, da = dst.width / dst.height;
    Rectangle src = { 0, 0, (float)t.width, (float)t.height };
    if (sa > da) { src.width = t.height * da; src.x = (t.width - src.width) * 0.5f; }
    else { src.height = t.width / da; src.y = (t.height - src.height) * 0.25f; }
    BeginBlendMode(BLEND_ALPHA_PREMULTIPLY);
    DrawTexturePro(t, src, dst, (Vector2){ 0, 0 }, 0, WHITE);
    EndBlendMode();
}

static void DrawFaceCard(const Game *g, int slot, float x, float y, float w, float h, Color frame,
                         const char *tag, const char *caption) {
    DrawRectangleRounded((Rectangle){ x - 8, y - 8, w + 16, h + 16 }, 0.06f, 8, (Color){ 0, 0, 0, 160 });
    DrawRectangleGradientV((int)x, (int)y, (int)w, (int)h, (Color){ 40, 44, 70, 255 }, (Color){ 12, 12, 24, 255 });
    Texture2D t = g->faces[slot];
    if (t.id) {
        // cover the card, keep the aspect ratio, crop the overflow (centred, slightly top-biased)
        float sa = (float)t.width / t.height, da = w / h;
        Rectangle src = { 0, 0, (float)t.width, (float)t.height };
        if (sa > da) { src.width = t.height * da; src.x = (t.width - src.width) * 0.5f; }
        else { src.height = t.width / da; src.y = (t.height - src.height) * 0.25f; }
        if (g->faceMirror[slot]) src.width = -src.width;   // raylib flips in place on negative width
        BeginBlendMode(BLEND_ALPHA_PREMULTIPLY);
        DrawTexturePro(t, src, (Rectangle){ x, y, w, h }, (Vector2){ 0, 0 }, 0, WHITE);
        EndBlendMode();
    } else {
        Gfx_DrawTitle(gTitleFont, "?", (Vector2){ x + w / 2, y + h / 2 }, 200, GRAY, BLACK, 4);
    }
    DrawRectangleLinesEx((Rectangle){ x - 3, y - 3, w + 6, h + 6 }, 6, frame);
    UI_DrawText(tag, (int)x + 10, (int)y + 8, 26, frame);
    // caption under the card, shrunk if it is very long
    float fs = 44.0f;
    while (fs > 22.0f && Gfx_MeasureTitle(gUiFont, caption, fs).x > 520.0f) fs -= 2.0f;
    Gfx_DrawTitle(gUiFont, caption, (Vector2){ x + w / 2, y + h + 46 }, fs, RAYWHITE, (Color){ 10, 10, 30, 255 }, 3);
}

// "PADEL WARS" face-off: title zooms in, the two cards slide in, VS slams down
static void DrawPrefight(const Game *g) {
    float t = g->prefightTimer;
    DrawRectangleGradientV(0, 0, SCREEN_WIDTH, SCREEN_HEIGHT, (Color){ 18, 20, 60, 255 }, (Color){ 70, 12, 40, 255 });
    // padel court lines in perspective (slowly scrolling glow)
    Color line = { 255, 255, 255, 40 };
    for (int i = -6; i <= 6; i++)
        DrawLineEx((Vector2){ 640 + i * 60.0f, 330 }, (Vector2){ 640 + i * 260.0f, 720 }, 3, line);
    for (int k = 0; k < 6; k++) {
        float yy = 330 + powf((k + fmodf(t * 0.8f, 1.0f)) / 6.0f, 1.8f) * 390;
        DrawLineEx((Vector2){ 0, yy }, (Vector2){ SCREEN_WIDTH, yy }, 2, line);
    }
    // light burst behind VS
    for (int k = 0; k < 16; k++) {
        float a = k * PI / 8 + t * 0.25f;
        Vector2 c = { 640, 380 };
        FillTri(c, (Vector2){ c.x + cosf(a) * 900, c.y + sinf(a) * 900 },
                (Vector2){ c.x + cosf(a + 0.12f) * 900, c.y + sinf(a + 0.12f) * 900 }, (Color){ 255, 220, 120, 18 });
    }

    // cards slide in from the sides
    float cw = 330, ch = 390, cy = 150;
    float e = EaseOutBack((t - 0.2f) / 0.55f);
    float lx = 120 - (1 - e) * 720, rx = SCREEN_WIDTH - 120 - cw + (1 - e) * 720;
    bool cpu1 = g->mode == MODE_CPU_VS_1P, cpu2 = g->mode == MODE_1P_VS_CPU;
    DrawFaceCard(g, 0, lx, cy, cw, ch, SKYBLUE, cpu1 ? "CPU" : "P1", g->captions[g->player1.characterIndex]);
    DrawFaceCard(g, 1, rx, cy, cw, ch, PINK, cpu2 ? "CPU" : (g->mode == MODE_1P_VS_2P ? "P2" : "P1"),
                 g->captions[g->player2.characterIndex]);

    // title zooms in
    float z = EaseOutBack(t / 0.5f);
    float ts = 118.0f * (0.2f + 0.8f * z);
    unsigned char ta = (unsigned char)(255 * Clamp01(t / 0.25f));
    Gfx_DrawTitle(gTitleFont, g->vsTitle, (Vector2){ 646, 80 }, ts, (Color){ 0, 0, 0, (unsigned char)(ta * 0.6f) }, BLANK, 0);
    Gfx_DrawTitle(gTitleFont, g->vsTitle, (Vector2){ 640, 74 }, ts, (Color){ 255, 214, 0, ta },
                  (Color){ 120, 20, 20, ta }, 5);

    // VS slams in, then pulses
    if (t > 0.75f) {
        float k = EaseOutCubic((t - 0.75f) / 0.3f);
        float vs = 150.0f * (2.6f - 1.6f * k) * (1.0f + 0.04f * sinf(t * 8.0f) * k);
        float shake = (t < 1.1f) ? sinf(t * 90.0f) * 6.0f * (1 - k) : 0.0f;
        Gfx_DrawTitle(gTitleFont, "VS", (Vector2){ 640 + shake, 370 }, vs, (Color){ 230, 30, 30, 255 }, RAYWHITE, 6);
    }

    const char *hint = "Enter / A / Start = skip";
    UI_DrawText(hint, SCREEN_WIDTH / 2 - UI_MeasureText(hint, 20) / 2, 690, 20, (Color){ 200, 200, 210, 200 });
    // quick fade to the fight
    float f = Clamp01((t - (PREFIGHT_TIME - 0.3f)) / 0.3f);
    if (f > 0) DrawRectangle(0, 0, SCREEN_WIDTH, SCREEN_HEIGHT, (Color){ 0, 0, 0, (unsigned char)(255 * f) });
}

// ---------- select screen ----------
static bool SlotIsCpu(const Game *g, int slot) {
    return slot == 0 ? g->mode == MODE_CPU_VS_1P : g->mode == MODE_1P_VS_CPU;
}
static const char *SlotLabel(const Game *g, int slot) {
    if (g->mode == MODE_ONLINE) return slot == Online_MySlot() ? "YOU" : "RIVAL";
    if (SlotIsCpu(g, slot)) return "CPU";
    if (slot == 0) return "P1";
    return g->mode == MODE_CPU_VS_1P ? "P1" : "P2";
}
static Color SlotColor(const Game *g, int slot) {
    if (SlotIsCpu(g, slot)) return (Color){ 255, 150, 40, 255 };
    return slot == 0 ? SKYBLUE : PINK;
}
static void DrawCentered(const char *t, int y, int fs, Color c) {
    DrawText(t, SCREEN_WIDTH / 2 - MeasureText(t, fs) / 2, y, fs, c);
}
static void DrawChip(const char *t, int x, int y, int fs, Color bg, Color fg) {
    int w = MeasureText(t, fs) + 12;
    DrawRectangleRounded((Rectangle){ (float)x, (float)y, (float)w, (float)fs + 6 }, 0.35f, 6, bg);
    DrawText(t, x + 6, y + 3, fs, fg);
}

static void DrawSelect(const Game *g) {
    int bgIdx = g->selectP1;
    if (g->stageLoaded[bgIdx]) {
        DrawTexturePro(g->stages[bgIdx], (Rectangle){0, 0, g->stages[bgIdx].width, g->stages[bgIdx].height},
                       (Rectangle){0, 0, SCREEN_WIDTH, SCREEN_HEIGHT}, (Vector2){0, 0}, 0, WHITE);
        DrawRectangle(0, 0, SCREEN_WIDTH, SCREEN_HEIGHT, (Color){0, 0, 0, 140});
    } else {
        DrawRectangle(0, 0, SCREEN_WIDTH, SCREEN_HEIGHT, (Color){20, 15, 30, 255});
    }
    bool dual = SelectDual(g);
    bool ready[2] = { g->p1Ready, g->p2Ready };
    int sel[2] = { g->selectP1, g->selectP2 };
    int active = dual ? -1 : (g->p1Ready ? 1 : 0);            // shared cursor: which slot it is picking
    float pulse = 0.5f + 0.5f * sinf(g->selTime * 7.0f);

    DrawCentered("EGYPTIAN FIGHTER", 22, 44, GOLD);

    // mode row
    static const char *modes[MODE_COUNT] = { "1P vs CPU", "CPU vs 1P", "1P vs 2P", "ONLINE" };
    int mw = 0;
    for (int m = 0; m < MODE_COUNT; m++) mw += MeasureText(modes[m], 20) + 12 + 14;
    const char *mlab = "MODE:";
    int mx = SCREEN_WIDTH / 2 - (mw + MeasureText(mlab, 20) + 10) / 2;
    DrawText(mlab, mx, 78, 20, LIGHTGRAY);
    mx += MeasureText(mlab, 20) + 10;
    for (int m = 0; m < MODE_COUNT; m++) {
        bool on = (int)g->mode == m;
        DrawChip(modes[m], mx, 75, 20, on ? GOLD : (Color){ 60, 60, 70, 220 }, on ? BLACK : GRAY);
        mx += MeasureText(modes[m], 20) + 12 + 14;
    }
    DrawCentered("change mode: LB / RB on the pad,  Tab or Q / E on the keyboard", 106, 16, GRAY);

    // the prompt
    const char *prompt;
    Color pc;
    if (g->startPending) { prompt = "BOTH READY - GET SET!"; pc = GREEN; }
    else if (dual) { prompt = "P1 and P2: choose your fighters"; pc = GOLD; }
    else if (SlotIsCpu(g, active)) { prompt = "Choose CPU fighter"; pc = SlotColor(g, active); }
    else prompt = TextFormat("%s choose your fighter", SlotLabel(g, active)), pc = SlotColor(g, active);
    int pfs = 34;
    int pw = MeasureText(prompt, pfs);
    DrawRectangle(SCREEN_WIDTH / 2 - pw / 2 - 18, 128, pw + 36, 46, (Color){ 0, 0, 0, 190 });
    DrawRectangleLinesEx((Rectangle){ (float)(SCREEN_WIDTH / 2 - pw / 2 - 18), 128, (float)pw + 36, 46 }, 2,
                         Fade(pc, 0.5f + 0.5f * pulse));
    DrawText(prompt, SCREEN_WIDTH / 2 - pw / 2, 134, pfs, pc);

    // the two slot panels
    for (int k = 0; k < 2; k++) {
        int px = k == 0 ? 40 : 880, py = 190, pw2 = 360, ph = 410;
        Color sc = SlotColor(g, k);
        bool picking = dual ? !ready[k] : (active == k && !g->startPending);
        DrawRectangle(px, py, pw2, ph, (Color){ 0, 0, 0, picking ? 200 : 160 });
        if (ready[k]) DrawRectangleLinesEx((Rectangle){ px, py, pw2, ph }, 4, GREEN);
        else if (picking) {
            float t = 3 + 4 * pulse;
            DrawRectangleLinesEx((Rectangle){ px - t, py - t, pw2 + 2 * t, ph + 2 * t }, 3 + 2 * pulse, sc);
        } else DrawRectangleLinesEx((Rectangle){ px, py, pw2, ph }, 2, (Color){ 90, 90, 100, 255 });

        DrawText(SlotLabel(g, k), px + 20, py + 14, 30, sc);
        if (picking) DrawChip(dual ? "CHOOSING" : "< CHOOSING NOW", px + 90, py + 16, 20, sc, BLACK);
        else if (!ready[k]) DrawText("waiting...", px + 90, py + 20, 20, GRAY);

        Rectangle pr = { px + 20, py + 56, 200, 240 };
        Color tint = (picking || ready[k]) ? WHITE : (Color){ 150, 150, 150, 255 };
        if (g->portraitLoaded[sel[k]]) {
            if (tint.r == 255) DrawPortraitFit(g->portraits[sel[k]], pr);
            else { DrawPortraitFit(g->portraits[sel[k]], pr); DrawRectangleRec(pr, (Color){ 0, 0, 0, 90 }); }
        } else DrawRectangleRec(pr, (Color){ 40, 40, 50, 255 });
        const char *nm = g->characters[sel[k]].name;
        int nfs = 32;
        while (nfs > 18 && MeasureText(nm, nfs) > pw2 - 40) nfs--;
        DrawText(nm, px + 20, py + 308, nfs, sc);
        if (ready[k]) {
            Rectangle badge = { px + 200, py + 230, 140, 54 };
            DrawRectangleRounded(badge, 0.25f, 6, (Color){ 20, 140, 40, 235 });
            DrawRectangleRoundedLinesEx(badge, 0.25f, 6, 3, RAYWHITE);
            DrawText("READY", (int)badge.x + 70 - MeasureText("READY", 32) / 2, (int)badge.y + 11, 32, RAYWHITE);
        }
        // which inputs drive this slot
        const char *by;
        if (g->mode == MODE_ONLINE) by = k == Online_MySlot() ? "Keyboard or any controller" : "Online opponent";
        else if (SlotIsCpu(g, k)) by = "Picked with the same controller";
        else if (dual) by = TextFormat("%s", Pad_Describe(Pad_ForPlayer(k + 1)));
        else by = "Keyboard or any controller";
        DrawText(by, px + 20, py + 352, 16, LIGHTGRAY);
        if (dual && g->mode != MODE_ONLINE) DrawText(k == 0 ? "keys: WASD + J ready, Backspace back" : "keys: arrows + Z ready, X back",
                           px + 20, py + 374, 16, GRAY);
    }

    // fighter grid
    DrawCentered("SELECT FIGHTER", 190, 20, RAYWHITE);
    for (int i = 0; i < MAX_CHARACTERS; i++) {
        int x = 460 + (i % SEL_COLS) * 180;
        int y = 220 + (i / SEL_COLS) * 96;
        DrawRectangle(x, y, 160, 88, (Color){0, 0, 0, 160});
        DrawRectangleLinesEx((Rectangle){x, y, 160, 88}, 2, (Color){ 90, 90, 100, 255 });
        if (g->portraitLoaded[i]) DrawPortraitFit(g->portraits[i], (Rectangle){x + 10, y + 9, 60, 70});
        {   // name: right of the portrait (or centred), wrapped / shrunk to fit the tile
            const char *nm = g->characters[i].name;
            int tx = g->portraitLoaded[i] ? x + 76 : x + 8, tw = g->portraitLoaded[i] ? 78 : 144;
            const char *sp = strchr(nm, ' ');
            if (MeasureText(nm, 18) > tw && sp) {
                char a[48]; int la = (int)(sp - nm); if (la > 47) la = 47;
                memcpy(a, nm, la); a[la] = 0;
                int fs = 17;
                while (fs > 11 && (MeasureText(a, fs) > tw || MeasureText(sp + 1, fs) > tw)) fs--;
                DrawText(a, tx + (tw - MeasureText(a, fs)) / 2, y + 26, fs, RAYWHITE);
                DrawText(sp + 1, tx + (tw - MeasureText(sp + 1, fs)) / 2, y + 28 + fs, fs, RAYWHITE);
            } else {
                int fs = 18;
                while (fs > 11 && MeasureText(nm, fs) > tw) fs--;
                DrawText(nm, tx + (tw - MeasureText(nm, fs)) / 2, y + 44 - fs / 2, fs, RAYWHITE);
            }
        }
    }
    // markers: locked picks (green tag), live cursors (thick pulsing frame + tag)
    for (int k = 0; k < 2; k++) {
        int i = sel[k];
        int x = 460 + (i % SEL_COLS) * 180, y = 220 + (i / SEL_COLS) * 96;
        bool live = dual ? !ready[k] : (active == k && !g->startPending);
        int tagx = k == 0 ? x + 2 : x + 118, tagy = y - 12;
        if (ready[k]) {
            DrawRectangleLinesEx((Rectangle){x, y, 160, 88}, 3, GREEN);
            DrawChip(TextFormat("%s OK", SlotLabel(g, k)), k == 0 ? x + 2 : x + 92, tagy, 14, GREEN, BLACK);
        } else if (live) {
            Color sc = SlotColor(g, k);
            float t = 2 + 3 * pulse;
            float since = g->selTime - g->selFlash;           // grow-in when the cursor arrives
            if (!dual && k == 1 && since < 0.3f) t += (0.3f - since) * 40.0f;
            DrawRectangleLinesEx((Rectangle){x - t, y - t, 160 + 2 * t, 88 + 2 * t}, 4, sc);
            DrawChip(SlotLabel(g, k), tagx, tagy, 16, sc, BLACK);
        }
    }

    const char *padCount = TextFormat("Controllers connected: %d%s", Pad_ConnectedCount(),
                                      g->mode == MODE_1P_VS_2P && !dual ? "  (plug in a 2nd pad for a cursor each)" : "");
    DrawRectangle(0, 618, SCREEN_WIDTH, 30, (Color){0, 0, 0, 170});
    DrawCentered(padCount, 624, 18, Pad_ConnectedCount() ? GREEN : GRAY);
    const char *foot = dual
        ? "Move: D-pad / stick    Pick: A / Start    Back: B    Controls & pad test: Back/Select or F1"
        : "Move: D-pad / stick / arrows / WASD    Pick: A / Start / Enter    Back: B / Backspace    Controls: Back/Select or F1";
    DrawCentered(foot, 664, 18, LIGHTGRAY);
    if (g->startPending) {
        DrawRectangle(0, 300, SCREEN_WIDTH, 90, (Color){ 0, 0, 0, 200 });
        DrawCentered("LOADING FIGHTERS...", 326, 40, GOLD);
    }
    if (g->mode == MODE_ONLINE) Online_DrawStatus(g);
}

void Game_Draw(const Game *g) {
    // Background - stage of P1 character (or solid)
    int stageIdx = (g->screen == SCREEN_FIGHT || g->screen == SCREEN_RESULT) ? g->player1.characterIndex : g->selectP1;
    if (g->stageLoaded[stageIdx]) {
        DrawTexturePro(g->stages[stageIdx],
            (Rectangle){0, 0, g->stages[stageIdx].width, g->stages[stageIdx].height},
            (Rectangle){0, 0, SCREEN_WIDTH, SCREEN_HEIGHT},
            (Vector2){0, 0}, 0, WHITE);
    } else {
        DrawRectangle(0, 0, SCREEN_WIDTH, SCREEN_HEIGHT, (Color){30, 30, 50, 255});
    }

    if (g->screen == SCREEN_ONLINE) {
        Online_DrawMenu(g);
        return;
    }

    // ---------- SELECT SCREEN ----------
    if (g->screen == SCREEN_SELECT) {
        DrawSelect(g);
        return;
    }

    // ---------- PRE-FIGHT FACE-OFF ----------
    if (g->screen == SCREEN_PREFIGHT) {
        DrawPrefight(g);
        if (g->mode == MODE_ONLINE) Online_DrawStatus(g);
        return;
    }

    // ---------- CONTROLLER TEST / CONTROLS ----------
    if (g->screen == SCREEN_PADTEST) {
        DrawRectangle(0, 0, SCREEN_WIDTH, SCREEN_HEIGHT, (Color){12, 12, 24, 255});
        DrawText("CONTROLLER TEST", 40, 24, 36, GOLD);
        DrawText("Press buttons / move sticks.  Back: F1, Esc, or hold Start for 1 second.", 40, 68, 18, LIGHTGRAY);
        for (int i = 0; i < PAD_MAX; i++) {
            const PadState *p = Pad_Get(i);
            int y = 100 + i * 150;
            DrawRectangle(30, y, 800, 140, (Color){0, 0, 0, 200});
            DrawRectangleLinesEx((Rectangle){30, y, 800, 140}, 2, p->connected ? (p->mapped ? GREEN : ORANGE) : DARKGRAY);
            if (!p->connected) { DrawText(TextFormat("Pad %d: not connected", i), 45, y + 10, 20, GRAY); continue; }
            const char *owner = Pad_ForPlayer(1) == i ? "  [P1]" : (Pad_ForPlayer(2) == i ? "  [P2]" : "");
            DrawText(TextFormat("Pad %d: %.50s%s", i, p->name, owner), 45, y + 8, 20, RAYWHITE);
            DrawText(TextFormat("%s   GUID %s", p->mapped ? "MAPPED (Xbox layout)" : "RAW FALLBACK (generic DirectInput layout)", p->guid),
                     45, y + 32, 16, p->mapped ? GREEN : ORANGE);
            char held[256] = "Buttons: ";
            for (int b = 0; b < PB_UP; b++)
                if (p->down[b]) { strncat(held, Pad_ButtonName(b), sizeof(held) - strlen(held) - 2); strcat(held, " "); }
            DrawText(held, 45, y + 54, 18, YELLOW);
            DrawText(TextFormat("L stick %+.2f %+.2f   R stick %+.2f %+.2f   LT %.2f  RT %.2f   dir:%s%s%s%s",
                                p->lx, p->ly, p->rx, p->ry, p->lt, p->rt,
                                p->down[PB_LEFT] ? " L" : "", p->down[PB_RIGHT] ? " R" : "",
                                p->down[PB_UP] ? " U" : "", p->down[PB_DOWN] ? " D" : ""), 45, y + 78, 16, SKYBLUE);
            char raw[256];
            int n = snprintf(raw, sizeof(raw), "Raw buttons down:");
            for (int b = 0; b < p->rawButtonCount && n < 200; b++) if (p->rawButtons[b]) n += snprintf(raw + n, sizeof(raw) - n, " %d", b);
            n += snprintf(raw + n, sizeof(raw) - n, "   axes:");
            for (int a = 0; a < p->rawAxisCount && a < 8 && n < 230; a++) n += snprintf(raw + n, sizeof(raw) - n, " %+.1f", p->rawAxes[a]);
            if (p->rawHatCount > 0) snprintf(raw + n, sizeof(raw) - n, "   hat:%d", p->rawHats[0]);
            DrawText(raw, 45, y + 102, 16, LIGHTGRAY);
        }
        // controls help
        int x = 850, y = 100;
        DrawRectangle(x - 10, y, 425, 600, (Color){0, 0, 0, 200});
        DrawText("PAD CONTROLS (fight)", x, y + 10, 22, GOLD);
        static const char *rows[][2] = {
            { "D-pad / L stick", "Move, Up jump, Down crouch" },
            { "A / Cross", "Jump" },
            { "X / Square", "Punch" },
            { "Y / Triangle", "Kick" },
            { "B / Circle", "Special 1 (Pyramid Blast)" },
            { "LT / L2", "Special 1 (same as B)" },
            { "RT / R2", "Special 2 (Bum Fireball)" },
            { "RB / R1 (hold)", "Block" },
            { "LB / L1", "Throw" },
            { "Back / Select", "Taunt" },
            { "Start", "Pause / resume" },
            { "X or Y in the air", "Jump attack" },
        };
        for (int r = 0; r < (int)(sizeof(rows) / sizeof(rows[0])); r++) {
            DrawText(rows[r][0], x, y + 45 + r * 26, 17, YELLOW);
            DrawText(rows[r][1], x + 160, y + 45 + r * 26, 16, RAYWHITE);
        }
        DrawText("MENUS", x, y + 370, 22, GOLD);
        DrawText("D-pad/stick  move the cursor", x, y + 400, 17, RAYWHITE);
        DrawText("A / Start    pick (then the other side)", x, y + 424, 17, RAYWHITE);
        DrawText("B            undo the last pick", x, y + 448, 17, RAYWHITE);
        DrawText("LB / RB      change mode", x, y + 472, 17, RAYWHITE);
        DrawText("Back         this screen", x, y + 496, 17, RAYWHITE);
        DrawText("Orange = no mapping found: generic", x, y + 530, 16, ORANGE);
        DrawText("layout used.  EasySMX: XInput mode", x, y + 550, 16, ORANGE);
        DrawText("is most reliable (see README).", x, y + 570, 16, ORANGE);
        return;
    }

    // ---------- FIGHT / RESULT ----------
    // Floor
    DrawRectangle(0, GROUND_Y, SCREEN_WIDTH, SCREEN_HEIGHT - GROUND_Y, (Color){60, 50, 40, 255});
    DrawRectangle(0, GROUND_Y, SCREEN_WIDTH, 8, (Color){120, 100, 70, 255});


    // Players
    Player_Draw(&g->player1);
    Player_Draw(&g->player2);
    for (int i = 0; i < MAX_PROJECTILES; i++)
        if (g->projectiles[i].active) DrawProjectile(&g->projectiles[i]);

    // UI
    DrawHealthBar(40, 30, 400, 28, g->player1.health, false);
    DrawHealthBar(SCREEN_WIDTH - 440, 30, 400, 28, g->player2.health, true);

    const char *n1 = g->characters[g->player1.characterIndex].name;
    const char *n2 = g->characters[g->player2.characterIndex].name;
    DrawText(g->mode == MODE_CPU_VS_1P ? TextFormat("CPU: %s", n1) : n1, 50, 65, 20, RAYWHITE);
    const char *r2 = g->mode == MODE_1P_VS_CPU ? TextFormat("CPU: %s", n2) : n2;
    DrawText(r2, SCREEN_WIDTH - 40 - MeasureText(r2, 20), 65, 20, RAYWHITE);

    // Timer
    char timerText[16];
    snprintf(timerText, sizeof(timerText), "%02d", (int)g->roundTimer);
    int tw = MeasureText(timerText, 40);
    DrawText(timerText, SCREEN_WIDTH/2 - tw/2, 25, 40, YELLOW);

    if (g->mode == MODE_ONLINE) Online_DrawStatus(g);

    // Controls reminder
    if (g->mode != MODE_ONLINE) DrawText("P1: WASD+J/K/U/I/L/O/P   P2: Arrows+Z/X/C/V/B/N/M   ESC=Pause   "
             "Pad: X punch  Y kick  A jump  B/LT sp1  RT sp2  RB block  LB throw  Back taunt  Start pause",
             12, SCREEN_HEIGHT - 26, 14, LIGHTGRAY);

    // Result overlay
    if (g->screen == SCREEN_RESULT) {
        DrawRectangle(0, 0, SCREEN_WIDTH, SCREEN_HEIGHT, (Color){0, 0, 0, 60});
        DrawRectangle(0, 110, SCREEN_WIDTH, 120, (Color){0, 0, 0, 170});
        const char *msg = "DRAW";
        if (g->winner == 1) msg = "PLAYER 1 WINS!";
        if (g->winner == 1) msg = (g->mode == MODE_CPU_VS_1P) ? "CPU WINS!" : "PLAYER 1 WINS!";
        if (g->winner == 2) msg = (g->mode == MODE_1P_VS_CPU) ? "CPU WINS!" : "PLAYER 2 WINS!";
        if (g->mode == MODE_ONLINE && g->winner) msg = g->winner - 1 == Online_MySlot() ? "YOU WIN!" : "YOU LOSE";
        Gfx_DrawTitle(gTitleFont, msg, (Vector2){ SCREEN_WIDTH / 2.0f, 155 }, 64, GOLD, (Color){ 90, 20, 10, 255 }, 4);
        const char *back = "Press R / Enter or pad A / Start to return to Character Select";
        DrawText(back, SCREEN_WIDTH/2 - MeasureText(back, 22)/2, 198, 22, RAYWHITE);
    }
}

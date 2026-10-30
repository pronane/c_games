/*
 * spriteforge.h - header-only raylib loader for SpriteForge characters (sprites.cfg)
 *
 *   #define SPRITEFORGE_IMPLEMENTATION     // in exactly ONE .c file, before the include
 *   #include "spriteforge.h"
 *
 *   SF_Character hero = SF_LoadCharacter("assets/dec");      // after InitWindow()
 *   SF_Anim anim = {0};
 *   SF_Play(&anim, SF_FindMove(&hero, "punch"));
 *   ...
 *   SF_Update(&anim, &hero, GetFrameTime());                  // true when a one-shot ends
 *   SF_DrawAnim(&hero, &anim, x, groundY, facingLeft, 1.0f);  // feet land exactly on groundY
 *   ...
 *   SF_Unload(&hero);
 *
 * Coordinates: (x, groundY) is the point between the character's feet.  scale 1.0 draws
 * the character at its built height (sprites.cfg "height", e.g. 480 px); use
 * SF_ScaleForHeight(&hero, 300) to get the scale for a 300 px tall fighter.
 * flip = true mirrors the sprite (sources face RIGHT, so flip = facing left).
 *
 * sprites.cfg format (whitespace separated, '#' starts a comment):
 *   version 1
 *   name dec
 *   frame <w> <h>          cell size of every frame
 *   height <px>            standing character height inside the cell
 *   ground <y>             feet line inside the cell (same for every frame)
 *   anchor_x <x>           body centre inside the cell
 *   move <name> <file> <frames> <w> <h> <fps> <loop 0|1> <row>
 *
 * Needs raylib 4.5+ (tested with 5.5).  C99.  MIT licence.
 */
#ifndef SPRITEFORGE_H
#define SPRITEFORGE_H

#include "raylib.h"
#include <stdbool.h>

#ifndef SF_MAX_MOVES
#define SF_MAX_MOVES 64   /* Sprite Forge Studio: 64 (Gaelic set has 36 moves) */
#endif
#define SF_NAME_LEN 48
#define SF_PATH_LEN 256

typedef struct SF_Move {
    char name[SF_NAME_LEN];
    char file[SF_PATH_LEN];
    int frames, w, h, row;
    float fps;
    bool loop;
    int tex;                     /* index into SF_Character.tex */
} SF_Move;

typedef struct SF_Character {
    bool ok;                     /* false if sprites.cfg was missing or unreadable */
    char name[SF_NAME_LEN];
    char dir[SF_PATH_LEN];
    int frameW, frameH;          /* cell size */
    int height;                  /* standing height in px at scale 1 */
    int ground;                  /* feet line inside the cell */
    int anchorX;                 /* body centre inside the cell */
    int moveCount;
    SF_Move moves[SF_MAX_MOVES];
    int texCount;
    Texture2D tex[SF_MAX_MOVES];
} SF_Character;

typedef struct SF_Anim {
    int move;                    /* move index, -1 = none */
    float time;                  /* seconds since the move started */
    bool done;                   /* one-shot move reached its last frame */
} SF_Anim;

/* standard move names (any extra "move" lines in sprites.cfg also work by name) */
enum { SF_IDLE, SF_WALK, SF_CROUCH, SF_JUMP, SF_PUNCH, SF_KICK, SF_SPECIAL1, SF_SPECIAL2,
       SF_BLOCK, SF_HIT, SF_THROW, SF_JUMPATTACK, SF_TAUNT, SF_VICTORY, SF_STD_MOVES };
extern const char *SF_STD_MOVE_NAMES[SF_STD_MOVES];

SF_Character SF_LoadCharacter(const char *dir);         /* needs an open window (GPU) */
bool SF_ParseConfig(SF_Character *c, const char *text);  /* parse only, no textures */
void SF_Unload(SF_Character *c);
int SF_FindMove(const SF_Character *c, const char *name); /* -1 if not found */
int SF_FrameAt(const SF_Character *c, int move, float time);
float SF_MoveDuration(const SF_Character *c, int move);   /* one pass, seconds */
float SF_ScaleForHeight(const SF_Character *c, float pixels);
void SF_Play(SF_Anim *a, int move);                       /* restarts only if move changes */
void SF_Restart(SF_Anim *a, int move);
bool SF_Update(SF_Anim *a, const SF_Character *c, float dt);
void SF_Draw(const SF_Character *c, int move, float time, float x, float groundY, bool flip, float scale);
void SF_DrawEx(const SF_Character *c, int move, float time, float x, float groundY, bool flip, float scale, Color tint);
void SF_DrawAnim(const SF_Character *c, const SF_Anim *a, float x, float groundY, bool flip, float scale);

#endif /* SPRITEFORGE_H */

/* ===================================================================== implementation */
#ifdef SPRITEFORGE_IMPLEMENTATION
#ifndef SPRITEFORGE_IMPLEMENTED
#define SPRITEFORGE_IMPLEMENTED
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

const char *SF_STD_MOVE_NAMES[SF_STD_MOVES] = {
    "idle", "walk", "crouch", "jump", "punch", "kick", "special1", "special2",
    "block", "hit", "throw", "jumpattack", "taunt", "victory"
};

static void sf__copy(char *dst, const char *src, size_t n) {
    size_t i = 0;
    for (; i + 1 < n && src[i]; i++) dst[i] = src[i];
    dst[i] = 0;
}

bool SF_ParseConfig(SF_Character *c, const char *text) {
    char line[512];
    const char *p = text;
    if (!text) return false;
    while (*p) {
        size_t n = 0;
        while (p[n] && p[n] != '\n') n++;
        size_t m = n < sizeof(line) - 1 ? n : sizeof(line) - 1;
        memcpy(line, p, m); line[m] = 0;
        p += n; if (*p == '\n') p++;
        char *hash = strchr(line, '#'); if (hash) *hash = 0;
        char key[32] = {0};
        if (sscanf(line, "%31s", key) != 1) continue;
        if (!strcmp(key, "name")) sscanf(line, "%*s %47s", c->name);
        else if (!strcmp(key, "frame")) sscanf(line, "%*s %d %d", &c->frameW, &c->frameH);
        else if (!strcmp(key, "height")) sscanf(line, "%*s %d", &c->height);
        else if (!strcmp(key, "ground")) sscanf(line, "%*s %d", &c->ground);
        else if (!strcmp(key, "anchor_x")) sscanf(line, "%*s %d", &c->anchorX);
        else if (!strcmp(key, "move") && c->moveCount < SF_MAX_MOVES) {
            SF_Move mv; memset(&mv, 0, sizeof mv);
            int loop = 1;
            mv.row = 0; mv.fps = 10.0f;
            int got = sscanf(line, "%*s %47s %255s %d %d %d %f %d %d",
                             mv.name, mv.file, &mv.frames, &mv.w, &mv.h, &mv.fps, &loop, &mv.row);
            if (got < 3 || mv.frames <= 0) continue;
            if (got < 5) { mv.w = c->frameW; mv.h = c->frameH; }
            if (mv.fps <= 0) mv.fps = 10.0f;
            mv.loop = loop != 0;
            mv.tex = -1;
            c->moves[c->moveCount++] = mv;
        }
    }
    if (c->frameW <= 0 || c->frameH <= 0 || c->moveCount == 0) return false;
    if (c->ground <= 0) c->ground = c->frameH;
    if (c->anchorX <= 0) c->anchorX = c->frameW / 2;
    if (c->height <= 0) c->height = c->ground;
    return true;
}

SF_Character SF_LoadCharacter(const char *dir) {
    SF_Character c; memset(&c, 0, sizeof c);
    sf__copy(c.dir, dir, sizeof c.dir);
    char *text = LoadFileText(TextFormat("%s/sprites.cfg", dir));
    if (!text) { TraceLog(LOG_WARNING, "SPRITEFORGE: no %s/sprites.cfg", dir); return c; }
    bool ok = SF_ParseConfig(&c, text);
    UnloadFileText(text);
    if (!ok) { TraceLog(LOG_WARNING, "SPRITEFORGE: bad sprites.cfg in %s", dir); return c; }
    for (int i = 0; i < c.moveCount; i++) {
        SF_Move *mv = &c.moves[i];
        for (int j = 0; j < i; j++)                       /* share combined sheets */
            if (!strcmp(c.moves[j].file, mv->file)) { mv->tex = c.moves[j].tex; break; }
        if (mv->tex >= 0) continue;
        Texture2D t = LoadTexture(TextFormat("%s/%s", dir, mv->file));
        if (t.id == 0) { TraceLog(LOG_WARNING, "SPRITEFORGE: missing %s/%s", dir, mv->file); continue; }
        SetTextureFilter(t, TEXTURE_FILTER_BILINEAR);
        c.tex[c.texCount] = t;
        mv->tex = c.texCount++;
    }
    c.ok = true;
    TraceLog(LOG_INFO, "SPRITEFORGE: %s: %d moves, cell %dx%d, ground %d", c.name, c.moveCount, c.frameW, c.frameH, c.ground);
    return c;
}

void SF_Unload(SF_Character *c) {
    for (int i = 0; i < c->texCount; i++) UnloadTexture(c->tex[i]);
    c->texCount = 0; c->ok = false;
}

int SF_FindMove(const SF_Character *c, const char *name) {
    for (int i = 0; i < c->moveCount; i++) if (!strcmp(c->moves[i].name, name)) return i;
    return -1;
}

float SF_MoveDuration(const SF_Character *c, int move) {
    if (move < 0 || move >= c->moveCount) return 0.0f;
    return c->moves[move].frames / c->moves[move].fps;
}

int SF_FrameAt(const SF_Character *c, int move, float time) {
    if (move < 0 || move >= c->moveCount) return 0;
    const SF_Move *mv = &c->moves[move];
    int f = (int)(time * mv->fps);
    if (f < 0) f = 0;
    if (mv->loop) f %= mv->frames;
    else if (f >= mv->frames) f = mv->frames - 1;
    return f;
}

float SF_ScaleForHeight(const SF_Character *c, float pixels) {
    return c->height > 0 ? pixels / (float)c->height : 1.0f;
}

void SF_Play(SF_Anim *a, int move) { if (a->move != move) SF_Restart(a, move); }
void SF_Restart(SF_Anim *a, int move) { a->move = move; a->time = 0.0f; a->done = false; }

bool SF_Update(SF_Anim *a, const SF_Character *c, float dt) {
    if (a->move < 0 || a->move >= c->moveCount) return false;
    a->time += dt;
    const SF_Move *mv = &c->moves[a->move];
    bool was = a->done;
    if (!mv->loop && a->time >= mv->frames / mv->fps) a->done = true;
    return a->done && !was;
}

void SF_DrawEx(const SF_Character *c, int move, float time, float x, float groundY, bool flip, float scale, Color tint) {
    if (move < 0 || move >= c->moveCount) return;
    const SF_Move *mv = &c->moves[move];
    if (mv->tex < 0) return;
    int f = SF_FrameAt(c, move, time);
    Rectangle src = { (float)(f * mv->w), (float)(mv->row * mv->h), (float)mv->w, (float)mv->h };
    if (flip) src.width = -src.width;
    /* anchor (anchorX, ground) of the cell lands on (x, groundY); mirrored when flipped */
    float ax = flip ? (float)(mv->w - c->anchorX) : (float)c->anchorX;
    Rectangle dst = { x - ax * scale, groundY - c->ground * scale, mv->w * scale, mv->h * scale };
    DrawTexturePro(c->tex[mv->tex], src, dst, (Vector2){0, 0}, 0.0f, tint);
}

void SF_Draw(const SF_Character *c, int move, float time, float x, float groundY, bool flip, float scale) {
    SF_DrawEx(c, move, time, x, groundY, flip, scale, WHITE);
}

void SF_DrawAnim(const SF_Character *c, const SF_Anim *a, float x, float groundY, bool flip, float scale) {
    SF_DrawEx(c, a->move, a->time, x, groundY, flip, scale, WHITE);
}
#endif
#endif /* SPRITEFORGE_IMPLEMENTATION */

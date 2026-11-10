/*
 * game_character.h — header-only raylib loader for Sprite Forge game_character.json (v11.5).
 *
 *   #define GAME_CHARACTER_IMPLEMENTATION   // in exactly ONE .c file, before the include
 *   #include "game_character.h"
 *
 *   GC_Character hero = {0};
 *   if (!GC_Load(&hero, "out/hero")) { ... }     // folder that contains game_character.json
 *   int idle = GC_Find(&hero, "idle");
 *   GC_Play(&hero, idle);
 *   GC_Update(&hero, GetFrameTime());
 *   GC_Draw(&hero, x, groundY, false, 1.0f);     // feet land on groundY
 *   GC_Unload(&hero);
 *
 * The file is the engine-neutral manifest (sheet/strip, frames, fps, loop, pivot, ground
 * line, gameplay events, hitboxes / hurtboxes when the build measured them).
 * Events use -1 for "none". Footsteps are a short list.
 * Hitboxes are an ESTIMATE from the sprite silhouette, not authored collision.
 *
 * Needs raylib 4.5+ (tested with 5.5). C99. The JSON reader covers the manifest this
 * project writes (objects, arrays, strings, numbers, true/false/null). It is not a
 * general JSON library.
 */
#ifndef GAME_CHARACTER_H
#define GAME_CHARACTER_H

#include "raylib.h"
#include <stdbool.h>

#ifndef GC_MAX_ANIMS
#define GC_MAX_ANIMS 48
#endif
#define GC_MAX_HITS 48
#define GC_MAX_HURTS 96
#define GC_MAX_STEPS 8
#define GC_NAME 48
#define GC_PATH 260

typedef struct GC_Box {
    int frame;
    int x, y, w, h;
    char part[16];
} GC_Box;

typedef struct GC_Events {
    int hit_start, hit_end;     /* inclusive frame indices, -1 if none */
    int ball_contact;
    int throw_release;
    int shoot;
    int reload;
    int foot_count;
    int footsteps[GC_MAX_STEPS];
} GC_Events;

typedef struct GC_Anim {
    char name[GC_NAME];
    char strip[GC_PATH];
    int frames, w, h, fps, row;
    bool loop;
    int pivot_x, ground_y;
    char source[GC_NAME];
    GC_Events ev;
    int hit_count, hurt_count;
    GC_Box hits[GC_MAX_HITS];
    GC_Box hurts[GC_MAX_HURTS];
    Texture2D tex;
    bool tex_ok;
} GC_Anim;

typedef struct GC_Character {
    bool ok;
    char name[GC_NAME];
    char dir[GC_PATH];
    char pack[GC_NAME];
    char camera[GC_NAME];
    char character_type[GC_NAME];
    int frame_w, frame_h, ground_y, pivot_x, height_px;
    int anim_count;
    int playing;                 /* index, or -1 */
    float time;                  /* seconds into the current animation */
    bool done;                   /* a one-shot reached its last frame */
    GC_Anim anims[GC_MAX_ANIMS];
} GC_Character;

bool GC_Load(GC_Character *c, const char *dir);          /* reads game_character.json + strip PNGs */
void GC_Unload(GC_Character *c);
int GC_Find(const GC_Character *c, const char *name);    /* -1 if missing */
void GC_Play(GC_Character *c, int anim);                 /* restarts */
bool GC_Update(GC_Character *c, float dt);               /* true when a one-shot ends this tick */
int GC_Frame(const GC_Character *c);                     /* current frame index, or -1 */
void GC_Draw(const GC_Character *c, float x, float groundY, bool flip, float scale);
bool GC_HitActive(const GC_Character *c);                /* current frame is inside hit_start..hit_end */
bool GC_Footstep(const GC_Character *c);                 /* current frame is a footstep */

#endif /* GAME_CHARACTER_H */

#ifdef GAME_CHARACTER_IMPLEMENTATION
#ifndef GAME_CHARACTER_IMPLEMENTED
#define GAME_CHARACTER_IMPLEMENTED

#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static const char *gc_ws(const char *p) {
    while (*p && isspace((unsigned char)*p)) p++;
    return p;
}

static const char *gc_skip_string(const char *p) {
    if (*p != '"') return p;
    p++;
    while (*p && *p != '"') {
        if (*p == '\\' && p[1]) p += 2;
        else p++;
    }
    if (*p == '"') p++;
    return p;
}

static const char *gc_skip_container(const char *p, char open, char close) {
    if (*p != open) return p;
    int depth = 1;
    p++;
    while (*p && depth) {
        if (*p == '"') { p = gc_skip_string(p); continue; }
        if (*p == open) depth++;
        else if (*p == close) depth--;
        p++;   /* step past the brace that closed the container too */
    }
    return p;
}

static const char *gc_skip_value(const char *p) {
    p = gc_ws(p);
    if (*p == '"') return gc_skip_string(p);
    if (*p == '{') return gc_skip_container(p, '{', '}');
    if (*p == '[') return gc_skip_container(p, '[', ']');
    if (*p == '-' || (*p >= '0' && *p <= '9')) {
        while (*p && strchr("-0123456789.eE+", *p)) p++;
        return p;
    }
    while (*p && *p != ',' && *p != '}' && *p != ']' && !isspace((unsigned char)*p)) p++;
    return p;
}

static int gc_key(const char **pp, const char *want) {
    const char *p = gc_ws(*pp);
    if (*p != '"') return 0;
    const char *s = p + 1;
    size_t n = strlen(want);
    if (strncmp(s, want, n) != 0 || s[n] != '"') return 0;
    p = s + n + 1;
    p = gc_ws(p);
    if (*p != ':') return 0;
    *pp = gc_ws(p + 1);
    return 1;
}

static int gc_string(const char **pp, char *dst, int n) {
    const char *p = gc_ws(*pp);
    if (*p != '"') return 0;
    p++;
    int i = 0;
    while (*p && *p != '"') {
        char c = *p++;
        if (c == '\\' && *p) {
            char e = *p++;
            c = (e == 'n') ? '\n' : (e == 't') ? '\t' : e;
        }
        if (dst && i + 1 < n) dst[i++] = c;
        else if (!dst) i++;
    }
    if (*p == '"') p++;
    if (dst) dst[i < n ? i : n - 1] = 0;
    *pp = p;
    return 1;
}

static int gc_int(const char **pp, int *out) {
    const char *p = gc_ws(*pp);
    char *end = NULL;
    long v = strtol(p, &end, 10);
    if (end == p) return 0;
    *out = (int)v;
    *pp = end;
    return 1;
}

static int gc_bool(const char **pp, bool *out) {
    const char *p = gc_ws(*pp);
    if (strncmp(p, "true", 4) == 0) { *out = true; *pp = p + 4; return 1; }
    if (strncmp(p, "false", 5) == 0) { *out = false; *pp = p + 5; return 1; }
    return 0;
}

static const char *gc_box4(const char *p, int *b) {
    p = gc_ws(p);
    if (*p != '[') return p;
    p++;
    for (int i = 0; i < 4; i++) {
        int v = 0;
        const char *q = p;
        if (!gc_int(&q, &v)) break;
        b[i] = v;
        p = gc_ws(q);
        if (*p == ',') p++;
    }
    p = gc_ws(p);
    if (*p == ']') p++;
    return p;
}

static void gc_events_init(GC_Events *e) {
    e->hit_start = e->hit_end = e->ball_contact = e->throw_release = e->shoot = e->reload = -1;
    e->foot_count = 0;
    for (int i = 0; i < GC_MAX_STEPS; i++) e->footsteps[i] = -1;
}

static const char *gc_parse_events(const char *p, GC_Events *e) {
    gc_events_init(e);
    p = gc_ws(p);
    if (*p != '{') return gc_skip_value(p);
    p++;
    while (*p) {
        p = gc_ws(p);
        if (*p == '}') { p++; break; }
        if (*p == ',') { p++; continue; }
        int v = 0;
        if (gc_key(&p, "hit_start") && gc_int(&p, &v)) e->hit_start = v;
        else if (gc_key(&p, "hit_end") && gc_int(&p, &v)) e->hit_end = v;
        else if (gc_key(&p, "ball_contact") && gc_int(&p, &v)) e->ball_contact = v;
        else if (gc_key(&p, "throw_release") && gc_int(&p, &v)) e->throw_release = v;
        else if (gc_key(&p, "shoot") && gc_int(&p, &v)) e->shoot = v;
        else if (gc_key(&p, "reload") && gc_int(&p, &v)) e->reload = v;
        else if (gc_key(&p, "footsteps")) {
            p = gc_ws(p);
            if (*p == '[') {
                p++;
                while (*p && *p != ']') {
                    p = gc_ws(p);
                    if (*p == ']') break;
                    if (*p == ',') { p++; continue; }
                    if (gc_int(&p, &v) && e->foot_count < GC_MAX_STEPS) e->footsteps[e->foot_count++] = v;
                    else p = gc_skip_value(p);
                }
                if (*p == ']') p++;
            } else p = gc_skip_value(p);
        } else {
            /* a custom event key from a pack you added — skipped here, still in the JSON for other loaders */
            p = gc_skip_string(gc_ws(p));
            p = gc_ws(p);
            if (*p == ':') p++;
            p = gc_skip_value(p);
        }
    }
    return p;
}

static const char *gc_parse_boxes(const char *p, GC_Box *boxes, int cap, int *count) {
    *count = 0;
    p = gc_ws(p);
    if (*p != '[') return gc_skip_value(p);
    p++;
    while (*p) {
        p = gc_ws(p);
        if (*p == ']') { p++; break; }
        if (*p == ',') { p++; continue; }
        if (*p != '{') { p = gc_skip_value(p); continue; }
        p++;
        GC_Box b; memset(&b, 0, sizeof b);
        int boxv[4] = {0, 0, 0, 0};
        int have = 0;
        while (*p) {
            p = gc_ws(p);
            if (*p == '}') { p++; break; }
            if (*p == ',') { p++; continue; }
            int v = 0;
            if (gc_key(&p, "frame") && gc_int(&p, &v)) b.frame = v;
            else if (gc_key(&p, "part") && gc_string(&p, b.part, (int)sizeof b.part)) {}
            else if (gc_key(&p, "box")) { p = gc_box4(p, boxv); have = 1; }
            else {
                p = gc_skip_string(gc_ws(p));
                p = gc_ws(p);
                if (*p == ':') p++;
                p = gc_skip_value(p);
            }
        }
        if (have && *count < cap) {
            b.x = boxv[0]; b.y = boxv[1]; b.w = boxv[2]; b.h = boxv[3];
            boxes[(*count)++] = b;
        }
    }
    return p;
}

static const char *gc_parse_anim(const char *p, GC_Anim *a) {
    memset(a, 0, sizeof *a);
    gc_events_init(&a->ev);
    a->fps = 12;
    p = gc_ws(p);
    if (*p != '{') return gc_skip_value(p);
    p++;
    while (*p) {
        p = gc_ws(p);
        if (*p == '}') { p++; break; }
        if (*p == ',') { p++; continue; }
        int v = 0;
        bool bv = false;
        if (gc_key(&p, "name")) gc_string(&p, a->name, GC_NAME);
        else if (gc_key(&p, "strip")) gc_string(&p, a->strip, GC_PATH);
        else if (gc_key(&p, "frames") && gc_int(&p, &v)) a->frames = v;
        else if (gc_key(&p, "fps") && gc_int(&p, &v)) a->fps = v;
        else if (gc_key(&p, "w") && gc_int(&p, &v)) a->w = v;
        else if (gc_key(&p, "h") && gc_int(&p, &v)) a->h = v;
        else if (gc_key(&p, "row") && gc_int(&p, &v)) a->row = v;
        else if (gc_key(&p, "loop") && gc_bool(&p, &bv)) a->loop = bv;
        else if (gc_key(&p, "ground_y") && gc_int(&p, &v)) a->ground_y = v;
        else if (gc_key(&p, "source")) gc_string(&p, a->source, GC_NAME);
        else if (gc_key(&p, "pivot")) {
            p = gc_ws(p);
            if (*p == '{') {
                p++;
                while (*p) {
                    p = gc_ws(p);
                    if (*p == '}') { p++; break; }
                    if (*p == ',') { p++; continue; }
                    if (gc_key(&p, "x") && gc_int(&p, &v)) a->pivot_x = v;
                    else if (gc_key(&p, "y") && gc_int(&p, &v)) a->ground_y = v;
                    else {
                        p = gc_skip_string(gc_ws(p));
                        p = gc_ws(p);
                        if (*p == ':') p++;
                        p = gc_skip_value(p);
                    }
                }
            } else p = gc_skip_value(p);
        }
        else if (gc_key(&p, "events")) p = gc_parse_events(p, &a->ev);
        else if (gc_key(&p, "hitboxes")) p = gc_parse_boxes(p, a->hits, GC_MAX_HITS, &a->hit_count);
        else if (gc_key(&p, "hurtboxes")) p = gc_parse_boxes(p, a->hurts, GC_MAX_HURTS, &a->hurt_count);
        else {
            p = gc_skip_string(gc_ws(p));
            p = gc_ws(p);
            if (*p == ':') p++;
            p = gc_skip_value(p);
        }
    }
    if (a->fps <= 0) a->fps = 12;
    return p;
}

bool GC_Load(GC_Character *c, const char *dir) {
    memset(c, 0, sizeof *c);
    c->playing = -1;
    snprintf(c->dir, GC_PATH, "%s", dir ? dir : ".");
    char path[GC_PATH + 32];
    snprintf(path, sizeof path, "%s/game_character.json", c->dir);
    FILE *f = fopen(path, "rb");
    if (!f) return false;
    fseek(f, 0, SEEK_END);
    long n = ftell(f);
    fseek(f, 0, SEEK_SET);
    if (n <= 0 || n > 8 * 1024 * 1024) { fclose(f); return false; }
    char *text = (char *)malloc((size_t)n + 1);
    if (!text) { fclose(f); return false; }
    if (fread(text, 1, (size_t)n, f) != (size_t)n) { free(text); fclose(f); return false; }
    text[n] = 0;
    fclose(f);
    const char *p = text;
    p = gc_ws(p);
    if (*p != '{') { free(text); return false; }
    p++;
    while (*p) {
        p = gc_ws(p);
        if (*p == '}') break;
        if (*p == ',') { p++; continue; }
        int v = 0;
        if (gc_key(&p, "name")) gc_string(&p, c->name, GC_NAME);
        else if (gc_key(&p, "game_pack")) gc_string(&p, c->pack, GC_NAME);
        else if (gc_key(&p, "camera")) gc_string(&p, c->camera, GC_NAME);
        else if (gc_key(&p, "character_type")) gc_string(&p, c->character_type, GC_NAME);
        else if (gc_key(&p, "ground_y") && gc_int(&p, &v)) c->ground_y = v;
        else if (gc_key(&p, "height_px") && gc_int(&p, &v)) c->height_px = v;
        else if (gc_key(&p, "frame")) {
            p = gc_ws(p);
            if (*p == '{') {
                p++;
                while (*p) {
                    p = gc_ws(p);
                    if (*p == '}') { p++; break; }
                    if (*p == ',') { p++; continue; }
                    if (gc_key(&p, "w") && gc_int(&p, &v)) c->frame_w = v;
                    else if (gc_key(&p, "h") && gc_int(&p, &v)) c->frame_h = v;
                    else {
                        p = gc_skip_string(gc_ws(p));
                        p = gc_ws(p);
                        if (*p == ':') p++;
                        p = gc_skip_value(p);
                    }
                }
            } else p = gc_skip_value(p);
        }
        else if (gc_key(&p, "pivot")) {
            p = gc_ws(p);
            if (*p == '{') {
                p++;
                while (*p) {
                    p = gc_ws(p);
                    if (*p == '}') { p++; break; }
                    if (*p == ',') { p++; continue; }
                    if (gc_key(&p, "x") && gc_int(&p, &v)) c->pivot_x = v;
                    else if (gc_key(&p, "y") && gc_int(&p, &v)) { if (!c->ground_y) c->ground_y = v; }
                    else {
                        p = gc_skip_string(gc_ws(p));
                        p = gc_ws(p);
                        if (*p == ':') p++;
                        p = gc_skip_value(p);
                    }
                }
            } else p = gc_skip_value(p);
        }
        else if (gc_key(&p, "animations")) {
            p = gc_ws(p);
            if (*p == '[') {
                p++;
                while (*p) {
                    p = gc_ws(p);
                    if (*p == ']') { p++; break; }
                    if (*p == ',') { p++; continue; }
                    if (c->anim_count >= GC_MAX_ANIMS) { p = gc_skip_value(p); continue; }
                    p = gc_parse_anim(p, &c->anims[c->anim_count]);
                    GC_Anim *a = &c->anims[c->anim_count];
                    if (a->frames > 0 && a->strip[0]) {
                        char full[GC_PATH + GC_PATH];
                        snprintf(full, sizeof full, "%s/%s", c->dir, a->strip);
                        if (FileExists(full)) {
                            a->tex = LoadTexture(full);
                            a->tex_ok = a->tex.id != 0;
                        }
                        if (!a->w) a->w = c->frame_w;
                        if (!a->h) a->h = c->frame_h;
                        if (!a->ground_y) a->ground_y = c->ground_y;
                        if (!a->pivot_x) a->pivot_x = c->pivot_x ? c->pivot_x : a->w / 2;
                        c->anim_count++;
                    }
                }
            } else p = gc_skip_value(p);
        } else {
            p = gc_skip_string(gc_ws(p));
            p = gc_ws(p);
            if (*p == ':') p++;
            p = gc_skip_value(p);
        }
    }
    free(text);
    c->ok = c->anim_count > 0;
    return c->ok;
}

void GC_Unload(GC_Character *c) {
    if (!c) return;
    for (int i = 0; i < c->anim_count; i++) if (c->anims[i].tex_ok) UnloadTexture(c->anims[i].tex);
    c->ok = false;
    c->anim_count = 0;
}

int GC_Find(const GC_Character *c, const char *name) {
    if (!c || !name) return -1;
    for (int i = 0; i < c->anim_count; i++) if (strcmp(c->anims[i].name, name) == 0) return i;
    return -1;
}

void GC_Play(GC_Character *c, int anim) {
    if (!c) return;
    c->playing = anim;
    c->time = 0;
    c->done = false;
}

int GC_Frame(const GC_Character *c) {
    if (!c || c->playing < 0 || c->playing >= c->anim_count) return -1;
    const GC_Anim *a = &c->anims[c->playing];
    if (a->frames <= 0 || a->fps <= 0) return 0;
    int f = (int)(c->time * (float)a->fps);
    if (a->loop) f = f % a->frames;
    else if (f >= a->frames) f = a->frames - 1;
    if (f < 0) f = 0;
    return f;
}

bool GC_Update(GC_Character *c, float dt) {
    if (!c || c->playing < 0 || c->playing >= c->anim_count) return false;
    GC_Anim *a = &c->anims[c->playing];
    if (dt < 0) dt = 0;
    c->time += dt;
    if (!a->loop && a->fps > 0 && c->time >= (float)a->frames / (float)a->fps) {
        c->time = (float)a->frames / (float)a->fps;
        bool edge = !c->done;
        c->done = true;
        return edge;
    }
    return false;
}

void GC_Draw(const GC_Character *c, float x, float groundY, bool flip, float scale) {
    int fi = GC_Frame(c);
    if (fi < 0) return;
    const GC_Anim *a = &c->anims[c->playing];
    if (!a->tex_ok || a->w <= 0 || a->h <= 0) return;
    if (scale <= 0) scale = 1.0f;
    Rectangle src;
    src.y = 0;
    src.height = (float)a->h;
    if (flip) { src.x = (float)((fi + 1) * a->w); src.width = (float)(-a->w); }
    else { src.x = (float)(fi * a->w); src.width = (float)a->w; }
    Rectangle dst;
    dst.x = x - (float)a->pivot_x * scale;
    dst.y = groundY - (float)a->ground_y * scale;
    dst.width = (float)a->w * scale;
    dst.height = (float)a->h * scale;
    DrawTexturePro(a->tex, src, dst, (Vector2){0, 0}, 0, WHITE);
}

bool GC_HitActive(const GC_Character *c) {
    int f = GC_Frame(c);
    if (f < 0) return false;
    const GC_Events *e = &c->anims[c->playing].ev;
    if (e->hit_start < 0) return false;
    int end = e->hit_end >= 0 ? e->hit_end : e->hit_start;
    return f >= e->hit_start && f <= end;
}

bool GC_Footstep(const GC_Character *c) {
    int f = GC_Frame(c);
    if (f < 0) return false;
    const GC_Events *e = &c->anims[c->playing].ev;
    for (int i = 0; i < e->foot_count; i++) if (e->footsteps[i] == f) return true;
    return false;
}

#endif /* GAME_CHARACTER_IMPLEMENTED */
#endif /* GAME_CHARACTER_IMPLEMENTATION */

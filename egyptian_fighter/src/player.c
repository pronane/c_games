#include "player.h"

// Frame counts for each sheet (must match the generated images)
static const int FRAME_COUNTS[STATE_COUNT] = {
    6,  // IDLE
    8,  // WALK
    6,  // CROUCH
    8,  // JUMP
    6,  // PUNCH
    6,  // KICK
    6,  // SPECIAL1  pyramid_blast
    6,  // SPECIAL2  bum_fireball
    6,  // BLOCK
    6,  // HIT
    6,  // THROW
    6,  // JUMP_ATTACK
    6,  // TAUNT
    6   // VICTORY
};

static const char *SHEET_FILES[STATE_COUNT] = {
    "idle.png",
    "walk.png",
    "crouch.png",
    "jump.png",
    "punch.png",
    "kick.png",
    "pyramid_blast.png",
    "bum_fireball.png",
    "block.png",
    "hit.png",
    "throw.png",
    "jump_attack.png",
    "taunt.png",
    "victory.png"
};

static Rectangle GetVisibleBounds(Image image, int xStart, int xEnd) {
    Color *pixels = (Color *)image.data;
    int minX = xEnd;
    int minY = image.height;
    int maxX = xStart - 1;
    int maxY = -1;

    for (int y = 0; y < image.height; y++) {
        for (int x = xStart; x < xEnd; x++) {
            if (pixels[y * image.width + x].a <= 16) continue;
            if (x < minX) minX = x;
            if (x > maxX) maxX = x;
            if (y < minY) minY = y;
            if (y > maxY) maxY = y;
        }
    }

    if (maxX < minX || maxY < minY) {
        return (Rectangle){ (float)xStart, 0.0f, (float)(xEnd - xStart), (float)image.height };
    }

    return (Rectangle){
        (float)minX,
        (float)minY,
        (float)(maxX - minX + 1),
        (float)(maxY - minY + 1)
    };
}

static float GetAnimSpeed(PlayerState state) {
    switch (state) {
        case STATE_IDLE:        return ANIM_SPEED_IDLE;
        case STATE_WALK:        return ANIM_SPEED_WALK;
        case STATE_PUNCH:
        case STATE_KICK:
        case STATE_THROW:       return ANIM_SPEED_ATTACK;
        case STATE_SPECIAL1:
        case STATE_SPECIAL2:    return ANIM_SPEED_SPECIAL;
        case STATE_JUMP:
        case STATE_JUMP_ATTACK: return ANIM_SPEED_JUMP;
        case STATE_HIT:         return ANIM_SPEED_HIT;
        default:                return ANIM_SPEED_OTHER;
    }
}

void Player_Init(Player *p, float startX, float startY, int facing, int characterIndex) {
    memset(p, 0, sizeof(Player));
    p->position = (Vector2){ startX, startY };
    p->velocity = (Vector2){ 0, 0 };
    p->onGround = true;
    p->facing = facing;
    p->characterIndex = characterIndex;
    p->state = STATE_IDLE;
    p->prevState = STATE_IDLE;
    p->currentFrame = 0;
    p->frameTimer = 0.0f;
    p->stateTimer = 0.0f;
    p->health = MAX_HEALTH;
    p->invincible = false;
    p->invincibleTimer = 0.0f;
    p->attackActive = false;
}

static void LoadSpritesLegacy(Player *p, const char *assetsRoot, const CharacterDef *chars) {
    char path[512];
    const char *folder = chars[p->characterIndex].folder;
    float idleAnchorX = 0.5f;
    float idleVisibleHeight = 0.0f;

    for (int i = 0; i < STATE_COUNT; i++) {
        snprintf(path, sizeof(path), "%s/%s/%s", assetsRoot, folder, SHEET_FILES[i]);

        // Try to load the real texture
        Image img = LoadImage(path);
        Rectangle visibleBounds;
        if (img.data != NULL) {
            float frameWidth = (float)img.width / (float)FRAME_COUNTS[i];
            visibleBounds = GetVisibleBounds(img, 0, img.width);
            if (i == STATE_IDLE) {
                Rectangle firstFrameBounds = GetVisibleBounds(img, 0, (int)ceilf(frameWidth));
                idleAnchorX = (firstFrameBounds.x + firstFrameBounds.width * 0.5f) / frameWidth;
                idleVisibleHeight = visibleBounds.height;
            }
            p->sheets[i].texture = Gfx_TextureFromImage(img);   // premultiplied + mipmapped
            UnloadImage(img);
            p->sheets[i].loaded = true;
            TraceLog(LOG_INFO, "Loaded: %s", path);
        } else {
            // Missing asset → create a visible placeholder so the game still runs
            TraceLog(LOG_WARNING, "MISSING ASSET: %s  (using placeholder)", path);

            // Simple colored rectangle with a letter so you can tell which state it is
            Color colors[STATE_COUNT] = {
                SKYBLUE, GREEN, ORANGE, PURPLE, RED, MAROON,
                GOLD, PINK, DARKBLUE, GRAY, BROWN, LIME, VIOLET, BEIGE
            };
            Image placeholder = GenImageColor(256, 512, colors[i % STATE_COUNT]);
            // Draw a big letter in the middle so it's obvious
            ImageDrawText(&placeholder, TextFormat("%d", i), 90, 200, 80, BLACK);
            visibleBounds = (Rectangle){ 0.0f, 0.0f, 256.0f, 512.0f };
            if (i == STATE_IDLE) idleVisibleHeight = visibleBounds.height;
            p->sheets[i].texture = Gfx_TextureFromImage(placeholder);
            UnloadImage(placeholder);
            p->sheets[i].loaded = false;
        }

        p->sheets[i].frameCount = FRAME_COUNTS[i];
        int texW = p->sheets[i].texture.width;
        p->sheets[i].frameWidth  = (float)texW / (float)p->sheets[i].frameCount;
        p->sheets[i].frameHeight = (float)p->sheets[i].texture.height;
        p->sheets[i].visibleBounds = visibleBounds;
        p->sheets[i].grid = false;
        p->sheets[i].shared = false;
        p->sheets[i].frameTime = 0.0f;
        p->sheets[i].loopFrom = -1;
        // legacy anchor: idle body centre, bottom of the visible pixels of the whole strip
        p->sheets[i].originX = p->sheets[i].frameWidth * idleAnchorX;
        p->sheets[i].originY = visibleBounds.y + visibleBounds.height;
    }
    for (int i = 0; i < STATE_COUNT; i++) {
        p->sheets[i].originX = p->sheets[i].frameWidth * idleAnchorX;
    }

    p->spriteAnchorX = idleAnchorX;
    p->spriteScale = idleVisibleHeight > 0.0f ? 300.0f / idleVisibleHeight : 1.0f;
}


// ---------------------------------------------------------------------------------------
// Grid sheets (written by tools/build_sprites.py).  sprites.cfg looks like:
//     cell 368 640          <- every frame is exactly this many pixels
//     baseline 628          <- y of the feet inside a cell
//     stand_height 560      <- upright height in pixels (used for on-screen scale)
//     anim walk walk.png 8 0.085
// Only the listed animations exist; anything else falls back to a similar one so a
// missing sheet never shows a placeholder block or the wrong number of figures.
// ---------------------------------------------------------------------------------------
static int StateFromName(const char *name) {
    static const char *NAMES[STATE_COUNT] = {
        "idle", "walk", "crouch", "jump", "punch", "kick", "pyramid_blast",
        "bum_fireball", "block", "hit", "throw", "jump_attack", "taunt", "victory"
    };
    for (int i = 0; i < STATE_COUNT; i++) if (strcmp(name, NAMES[i]) == 0) return i;
    if (strcmp(name, "special1") == 0) return STATE_SPECIAL1;
    if (strcmp(name, "special2") == 0) return STATE_SPECIAL2;
    return -1;
}

static bool LoadSpritesGrid(Player *p, const char *dir, const char *cfgPath) {
    char *text = LoadFileText(cfgPath);
    if (text == NULL) return false;

    int cellW = 0, cellH = 0, baseline = 0, standH = 0;
    for (char *line = text, *next = NULL; line && *line; line = next) {
        next = strpbrk(line, "\r\n");          // portable line split (no strtok_r on MinGW)
        if (next) { *next++ = 0; while (*next == '\r' || *next == '\n') next++; }
        char key[32] = {0}, name[64] = {0}, file[128] = {0};
        int a = 0, b = 0;
        float ft = 0.0f;
        if (line[0] == '#' || line[0] == 0) continue;
        if (sscanf(line, "%31s", key) != 1) continue;
        if (strcmp(key, "cell") == 0 && sscanf(line, "%*s %d %d", &a, &b) == 2) { cellW = a; cellH = b; }
        else if (strcmp(key, "baseline") == 0 && sscanf(line, "%*s %d", &a) == 1) baseline = a;
        else if (strcmp(key, "stand_height") == 0 && sscanf(line, "%*s %d", &a) == 1) standH = a;
        else if (strcmp(key, "projectile") == 0 && sscanf(line, "%*s %63s", name) == 1) {
            if (strcmp(name, "ball") == 0) p->projectileKind = PROJ_BALL;
            else if (strcmp(name, "book") == 0) p->projectileKind = PROJ_BOOK;
            else if (strcmp(name, "card") == 0) p->projectileKind = PROJ_CARD;
            else if (strcmp(name, "bubble") == 0) p->projectileKind = PROJ_BUBBLE;
            else if (strcmp(name, "fire") == 0) p->projectileKind = PROJ_FIRE;
            else if (strcmp(name, "fire_blue") == 0) p->projectileKind = PROJ_FIRE_BLUE;
        }
        else if (strcmp(key, "loop") == 0 && sscanf(line, "%*s %63s %d", name, &a) == 2) {
            int st = StateFromName(name);       // 'loop victory 2': after the last frame, go on
            if (st >= 0 && p->sheets[st].loaded && a >= 0 && a < p->sheets[st].frameCount)
                p->sheets[st].loopFrom = a;     // from frame 2 (needs the anim line first)
        }
        else if (strcmp(key, "anim") == 0 &&
                 sscanf(line, "%*s %63s %127s %d %f", name, file, &a, &ft) == 4) {
            int st = StateFromName(name);
            if (st < 0 || cellW <= 0) continue;
            char path[768];
            snprintf(path, sizeof(path), "%s/%s", dir, file);
            // full-resolution sheet, premultiplied alpha + mipmaps + trilinear filtering (gfx.c)
            Texture2D tex = Gfx_LoadTexture(path);
            if (tex.id == 0) { TraceLog(LOG_WARNING, "MISSING ASSET: %s", path); continue; }
            int frames = tex.width / cellW;
            if (frames != a) {
                TraceLog(LOG_WARNING, "%s: cfg says %d frames, image holds %d - using %d",
                         path, a, frames, frames);
            }
            if (frames < 1) frames = 1;
            SpriteSheet *sh = &p->sheets[st];
            sh->texture = tex;
            sh->frameCount = frames;
            sh->frameWidth = (float)cellW;
            sh->frameHeight = (float)tex.height;
            sh->visibleBounds = (Rectangle){ 0, 0, (float)cellW, (float)tex.height };
            sh->loaded = true;
            sh->grid = true;
            sh->shared = false;
            sh->frameTime = ft;
            sh->loopFrom = -1;
            sh->originX = cellW * 0.5f;
            sh->originY = (float)baseline;
            TraceLog(LOG_INFO, "Loaded grid sheet: %s (%d x %dpx frames)", path, frames, cellW);
        }
    }
    UnloadFileText(text);
    (void)cellH;

    if (!p->sheets[STATE_IDLE].loaded) {
        TraceLog(LOG_WARNING, "%s has no idle animation - ignoring it", cfgPath);
        for (int i = 0; i < STATE_COUNT; i++)
            if (p->sheets[i].texture.id) UnloadTexture(p->sheets[i].texture);
        memset(p->sheets, 0, sizeof(p->sheets));
        return false;
    }

    // Fallback chains for animations that have no sheet of their own
    static const int FALLBACK[STATE_COUNT][3] = {
        [STATE_IDLE]        = { -1, -1, -1 },
        [STATE_WALK]        = { STATE_IDLE, -1, -1 },
        [STATE_CROUCH]      = { STATE_IDLE, -1, -1 },
        [STATE_JUMP]        = { STATE_IDLE, -1, -1 },
        [STATE_PUNCH]       = { STATE_IDLE, -1, -1 },
        [STATE_KICK]        = { STATE_PUNCH, STATE_IDLE, -1 },
        [STATE_SPECIAL1]    = { STATE_PUNCH, STATE_IDLE, -1 },
        [STATE_SPECIAL2]    = { STATE_KICK, STATE_PUNCH, STATE_IDLE },
        [STATE_BLOCK]       = { STATE_IDLE, -1, -1 },
        [STATE_HIT]         = { STATE_IDLE, -1, -1 },
        [STATE_THROW]       = { STATE_PUNCH, STATE_IDLE, -1 },
        [STATE_JUMP_ATTACK] = { STATE_KICK, STATE_PUNCH, STATE_IDLE },
        [STATE_TAUNT]       = { STATE_VICTORY, STATE_IDLE, -1 },
        [STATE_VICTORY]     = { STATE_IDLE, -1, -1 },
    };
    for (int i = 0; i < STATE_COUNT; i++) {
        if (p->sheets[i].loaded) continue;
        for (int k = 0; k < 3; k++) {
            int f = FALLBACK[i][k];
            if (f >= 0 && p->sheets[f].loaded && !p->sheets[f].shared) {
                p->sheets[i] = p->sheets[f];
                p->sheets[i].shared = true;
                p->sheets[i].loopFrom = -1;
                // borrowed sheets for one-shot states should not run longer than ~0.5 s
                break;
            }
        }
        if (p->sheets[i].texture.id == 0) {   // should not happen (idle always exists)
            p->sheets[i] = p->sheets[STATE_IDLE];
            p->sheets[i].shared = true;
        }
    }

    p->spriteAnchorX = 0.5f;
    p->spriteScale = 300.0f / (float)(standH > 0 ? standH : 560);
    return true;
}

void Player_LoadSprites(Player *p, const char *assetsRoot, const CharacterDef *chars) {
    char dir[512], cfg[600];
    snprintf(dir, sizeof(dir), "%s/%s", assetsRoot, chars[p->characterIndex].folder);
    snprintf(cfg, sizeof(cfg), "%s/sprites.cfg", dir);
    memset(p->sheets, 0, sizeof(p->sheets));
    if (FileExists(cfg) && LoadSpritesGrid(p, dir, cfg)) {
        TraceLog(LOG_INFO, "%s: using grid sprite sheets (sprites.cfg)", dir);
        return;
    }
    LoadSpritesLegacy(p, assetsRoot, chars);
    // original Flame / Dragon sheets (no sprites.cfg): their specials throw a fireball too
    const char *folder = chars[p->characterIndex].folder;
    if (strstr(folder, "flame")) p->projectileKind = PROJ_FIRE;
    else if (strstr(folder, "dragon")) p->projectileKind = PROJ_FIRE_BLUE;
}

void Player_UnloadSprites(Player *p) {
    for (int i = 0; i < STATE_COUNT; i++) {
        if (p->sheets[i].texture.id != 0 && !p->sheets[i].shared) {
            UnloadTexture(p->sheets[i].texture);
        }
        p->sheets[i].texture.id = 0;
    }
}

void Player_SetState(Player *p, PlayerState newState) {
    if (p->state == newState) return;
    p->prevState = p->state;
    p->state = newState;
    static int logStates = -1;          // test aid: EF_LOGSTATE=1 prints every state change
    if (logStates < 0) logStates = getenv("EF_LOGSTATE") != NULL;
    if (logStates) {
        static const char *names[STATE_COUNT] = { "idle", "walk", "crouch", "jump", "punch", "kick", "special1",
            "special2", "block", "hit", "throw", "jump_attack", "taunt", "victory" };
        TraceLog(LOG_INFO, "STATE char%d x=%.0f %s -> %s", p->characterIndex, p->position.x,
                 names[p->prevState], names[newState]);
    }
    p->currentFrame = 0;
    p->frameTimer = 0.0f;
    p->stateTimer = 0.0f;
    p->attackActive = false;
    p->projectileFired = false;
}

bool Player_IsAttacking(const Player *p) {
    return (p->state == STATE_PUNCH ||
            p->state == STATE_KICK ||
            p->state == STATE_SPECIAL1 ||
            p->state == STATE_SPECIAL2 ||
            p->state == STATE_THROW ||
            p->state == STATE_JUMP_ATTACK);
}

bool Player_CanMove(const Player *p) {
    return (p->state == STATE_IDLE ||
            p->state == STATE_WALK ||
            p->state == STATE_CROUCH);
}

Rectangle Player_GetHurtbox(const Player *p) {
    float w = 72.0f;
    float h = (p->state == STATE_CROUCH) ? 170.0f : 280.0f;
    float x = p->position.x - w * 0.5f;
    float y = p->position.y - h;
    return (Rectangle){ x, y, w, h };
}

// fixed total length for attacks and hit-stun (common.h), so a sheet with 4 frames and one
// with 8 frames play out in the same time: no fighter is faster just because of its art
static float MoveTime(PlayerState s) {
    switch (s) {
        case STATE_PUNCH:       return MOVE_TIME_PUNCH;
        case STATE_KICK:        return MOVE_TIME_KICK;
        case STATE_SPECIAL1:
        case STATE_SPECIAL2:    return MOVE_TIME_SPECIAL;
        case STATE_THROW:       return MOVE_TIME_THROW;
        case STATE_JUMP_ATTACK: return MOVE_TIME_JUMP_ATTACK;
        case STATE_HIT:         return MOVE_TIME_HIT;
        default:                return 0.0f;
    }
}

float Player_FrameTime(const Player *p) {
    const SpriteSheet *sh = &p->sheets[p->state];
    float mt = MoveTime(p->state);
    if (mt > 0.0f && sh->frameCount > 0) return mt / (float)sh->frameCount;
    return sh->frameTime > 0.0f ? sh->frameTime : GetAnimSpeed(p->state);
}

float Player_Progress(const Player *p) {
    int n = p->sheets[p->state].frameCount;
    if (n <= 0) return 0.0f;
    float ft = Player_FrameTime(p);
    float sub = ft > 0.0f ? fminf(p->frameTimer / ft, 1.0f) : 0.0f;
    return fminf(1.0f, (p->currentFrame + sub) / (float)n);
}

static void UpdateAnimation(Player *p, float dt) {
    p->frameTimer += dt;
    float speed = Player_FrameTime(p);

    if (p->frameTimer >= speed) {
        p->frameTimer = 0.0f;
        p->currentFrame++;

        int maxFrames = p->sheets[p->state].frameCount;

        // Looping states
        if (p->state == STATE_IDLE || p->state == STATE_WALK ||
            p->state == STATE_CROUCH || p->state == STATE_BLOCK) {
            if (p->currentFrame >= maxFrames) p->currentFrame = 0;
        }
        // One-shot states
        else {
            if (p->currentFrame >= maxFrames) {
                p->currentFrame = maxFrames - 1;

                if (p->state == STATE_HIT) {
                    if (p->health > 0)          // knocked out: stay down on the last hit frame
                        Player_SetState(p, p->onGround ? STATE_IDLE : STATE_JUMP);
                }
                else if (p->state == STATE_JUMP_ATTACK) {
                    if (p->onGround) Player_SetState(p, STATE_IDLE);
                }
                else if (p->state == STATE_VICTORY || p->state == STATE_TAUNT) {
                    // hold the last frame - or keep looping (e.g. Mike's flex: 'loop victory 2')
                    if (p->sheets[p->state].loopFrom >= 0) p->currentFrame = p->sheets[p->state].loopFrom;
                }
                else {
                    if (p->onGround) {
                        Player_SetState(p, p->inputDown ? STATE_CROUCH : STATE_IDLE);
                    } else {
                        Player_SetState(p, STATE_JUMP);
                    }
                }
            }
        }
    }
}

static void UpdatePhysics(Player *p, float dt) {
    if (!p->onGround) {
        p->velocity.y += GRAVITY;
        if (p->velocity.y > MAX_FALL_SPEED) p->velocity.y = MAX_FALL_SPEED;
    }

    p->position.x += p->velocity.x;
    p->position.y += p->velocity.y;

    if (p->position.y >= GROUND_Y) {
        p->position.y = GROUND_Y;
        p->velocity.y = 0.0f;
        p->onGround = true;

        if (p->state == STATE_JUMP || p->state == STATE_JUMP_ATTACK) {
            Player_SetState(p, STATE_IDLE);
        }
    } else {
        p->onGround = false;
    }

    // Screen bounds
    if (p->position.x < 40.0f) p->position.x = 40.0f;
    if (p->position.x > SCREEN_WIDTH - 40.0f) p->position.x = SCREEN_WIDTH - 40.0f;
}

static void HandleInputAndState(Player *p) {
    if (p->invincible) {
        p->invincibleTimer -= GetFrameTime();
        if (p->invincibleTimer <= 0.0f) {
            p->invincible = false;
        }
    }

    bool locked = (p->state == STATE_HIT ||
                   p->state == STATE_VICTORY ||
                   p->state == STATE_THROW ||
                   (Player_IsAttacking(p) && p->currentFrame < p->sheets[p->state].frameCount - 1));

    if (locked) return;

    // Jump
    if (p->inputUp && p->onGround &&
        (p->state == STATE_IDLE || p->state == STATE_WALK || p->state == STATE_CROUCH)) {
        p->velocity.y = JUMP_FORCE;
        p->onGround = false;
        Player_SetState(p, STATE_JUMP);
        return;
    }

    // Jump attack
    if (!p->onGround && p->inputJumpAttack && p->state == STATE_JUMP) {
        Player_SetState(p, STATE_JUMP_ATTACK);
        return;
    }

    // Ground attacks
    if (p->onGround) {
        if (p->opponentX != 0.0f && fabsf(p->opponentX - p->position.x) > 4.0f &&
            (p->inputSpecial1 || p->inputSpecial2 || p->inputThrow || p->inputPunch || p->inputKick))
            p->facing = (p->opponentX > p->position.x) ? 1 : -1;
        // specials are cast standing still (no sliding along the floor if fired mid-walk)
        if (p->inputSpecial2) { p->velocity.x = 0.0f; Player_SetState(p, STATE_SPECIAL2); return; }
        if (p->inputSpecial1) { p->velocity.x = 0.0f; Player_SetState(p, STATE_SPECIAL1); return; }
        if (p->inputThrow)    { Player_SetState(p, STATE_THROW);    return; }
        if (p->inputPunch)    { Player_SetState(p, STATE_PUNCH);    return; }
        if (p->inputKick)     { Player_SetState(p, STATE_KICK);     return; }
        if (p->inputTaunt)    { Player_SetState(p, STATE_TAUNT);    return; }
        if (p->inputBlock)    { Player_SetState(p, STATE_BLOCK);    return; }
    }

    // Movement.  On the ground a fighter always faces the opponent (walking away is a
    // slower back-step), so attacks never go the wrong way.
    if (p->onGround) {
        if (p->opponentX != 0.0f && fabsf(p->opponentX - p->position.x) > 4.0f)
            p->facing = (p->opponentX > p->position.x) ? 1 : -1;
        if (p->inputDown) {
            p->velocity.x = 0.0f;
            Player_SetState(p, STATE_CROUCH);
        }
        else if (p->inputLeft) {
            p->velocity.x = -MOVE_SPEED * (p->facing < 0 ? 1.0f : 0.8f);
            Player_SetState(p, STATE_WALK);
        }
        else if (p->inputRight) {
            p->velocity.x = MOVE_SPEED * (p->facing > 0 ? 1.0f : 0.8f);
            Player_SetState(p, STATE_WALK);
        }
        else {
            p->velocity.x = 0.0f;
            if (p->state == STATE_WALK || p->state == STATE_CROUCH || p->state == STATE_BLOCK) {
                Player_SetState(p, STATE_IDLE);
            }
        }
    } else {
        // Air control
        if (p->inputLeft) {
            p->velocity.x = -MOVE_SPEED * 0.7f;
            p->facing = -1;
        } else if (p->inputRight) {
            p->velocity.x = MOVE_SPEED * 0.7f;
            p->facing = 1;
        }
    }
}

void Player_Update(Player *p, float dt) {
    p->stateTimer += dt;

    HandleInputAndState(p);
    UpdatePhysics(p, dt);
    UpdateAnimation(p, dt);

    // Active attack frames (middle of the animation)
    p->attackActive = false;
    bool rangedSpecial = p->projectileKind != PROJ_NONE &&
                         (p->state == STATE_SPECIAL1 || p->state == STATE_SPECIAL2);
    if (Player_IsAttacking(p) && !rangedSpecial) {   // ranged specials hurt via the projectile
        float t = Player_Progress(p);                 // same window for every fighter
        if (t >= ACTIVE_FROM && t < ACTIVE_TO) p->attackActive = true;
    }

    p->hurtbox = Player_GetHurtbox(p);

    if (p->attackActive) {
        float reach = 60.0f;
        if (p->state == STATE_SPECIAL1 || p->state == STATE_SPECIAL2) reach = 75.0f;
        if (p->state == STATE_KICK || p->state == STATE_JUMP_ATTACK) reach = 70.0f;

        p->hitbox = (Rectangle){
            p->position.x + (p->facing > 0 ? 18.0f : -reach - 18.0f),
            p->position.y - 220.0f,
            reach,
            100.0f
        };
    } else {
        p->hitbox = (Rectangle){0};
    }
}

void Player_Draw(const Player *p) {
    const SpriteSheet *sheet = &p->sheets[p->state];
    if (sheet->texture.id == 0) return;

    int frame = p->currentFrame;
    if (frame >= sheet->frameCount) frame = sheet->frameCount - 1;
    if (frame < 0) frame = 0;

    // Exactly one cell.  A negative width mirrors the cell in place, so the x offset is the
    // same for both facings (the old "+1 frame" offset drew the NEXT cell - or past the end
    // of the strip - whenever a character faced left).
    Rectangle source = {
        frame * sheet->frameWidth,
        0.0f,
        sheet->frameWidth * (p->facing < 0 ? -1.0f : 1.0f),
        sheet->frameHeight
    };

    float scale = p->spriteScale;
    float destW = sheet->frameWidth * scale;
    float destH = sheet->frameHeight * scale;

    float anchorX = sheet->originX;
    if (p->facing < 0) anchorX = sheet->frameWidth - anchorX;
    Vector2 origin = { anchorX * scale, sheet->originY * scale };

    Color tint = WHITE;
    if (p->invincible && ((int)(GetTime() * 10) % 2 == 0)) {
        tint = (Color){ 255, 100, 100, 200 };
    }
    if (!sheet->loaded) tint.a = 180;

    // sheets are premultiplied-alpha textures (gfx.c) -> premultiplied blending
    BeginBlendMode(BLEND_ALPHA_PREMULTIPLY);
    DrawTexturePro(sheet->texture, source,
                   (Rectangle){ p->position.x, p->position.y, destW, destH },
                   origin, 0.0f, Gfx_Premul(tint));
    EndBlendMode();
}

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

void Player_LoadSprites(Player *p, const char *assetsRoot, const CharacterDef *chars) {
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
            p->sheets[i].texture = LoadTextureFromImage(img);
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
            p->sheets[i].texture = LoadTextureFromImage(placeholder);
            UnloadImage(placeholder);
            p->sheets[i].loaded = false;
        }

        p->sheets[i].frameCount = FRAME_COUNTS[i];
        int texW = p->sheets[i].texture.width;
        p->sheets[i].frameWidth  = (float)texW / (float)p->sheets[i].frameCount;
        p->sheets[i].frameHeight = (float)p->sheets[i].texture.height;
        p->sheets[i].visibleBounds = visibleBounds;
    }

    p->spriteAnchorX = idleAnchorX;
    p->spriteScale = idleVisibleHeight > 0.0f ? 300.0f / idleVisibleHeight : 1.0f;
}

void Player_UnloadSprites(Player *p) {
    for (int i = 0; i < STATE_COUNT; i++) {
        if (p->sheets[i].texture.id != 0) {
            UnloadTexture(p->sheets[i].texture);
            p->sheets[i].texture.id = 0;
        }
    }
}

void Player_SetState(Player *p, PlayerState newState) {
    if (p->state == newState) return;
    p->prevState = p->state;
    p->state = newState;
    p->currentFrame = 0;
    p->frameTimer = 0.0f;
    p->stateTimer = 0.0f;
    p->attackActive = false;
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

static void UpdateAnimation(Player *p, float dt) {
    p->frameTimer += dt;
    float speed = GetAnimSpeed(p->state);

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
                    Player_SetState(p, p->onGround ? STATE_IDLE : STATE_JUMP);
                }
                else if (p->state == STATE_JUMP_ATTACK) {
                    if (p->onGround) Player_SetState(p, STATE_IDLE);
                }
                else if (p->state == STATE_VICTORY || p->state == STATE_TAUNT) {
                    // hold last frame
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
        if (p->inputSpecial2) { Player_SetState(p, STATE_SPECIAL2); return; }
        if (p->inputSpecial1) { Player_SetState(p, STATE_SPECIAL1); return; }
        if (p->inputThrow)    { Player_SetState(p, STATE_THROW);    return; }
        if (p->inputPunch)    { Player_SetState(p, STATE_PUNCH);    return; }
        if (p->inputKick)     { Player_SetState(p, STATE_KICK);     return; }
        if (p->inputTaunt)    { Player_SetState(p, STATE_TAUNT);    return; }
        if (p->inputBlock)    { Player_SetState(p, STATE_BLOCK);    return; }
    }

    // Movement
    if (p->onGround) {
        if (p->inputDown) {
            p->velocity.x = 0.0f;
            Player_SetState(p, STATE_CROUCH);
        }
        else if (p->inputLeft) {
            p->velocity.x = -MOVE_SPEED;
            p->facing = -1;
            Player_SetState(p, STATE_WALK);
        }
        else if (p->inputRight) {
            p->velocity.x = MOVE_SPEED;
            p->facing = 1;
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
    if (Player_IsAttacking(p)) {
        int mid = p->sheets[p->state].frameCount / 2;
        if (p->currentFrame >= mid - 1 && p->currentFrame <= mid + 1) {
            p->attackActive = true;
        }
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

    Rectangle source = {
        (p->currentFrame + (p->facing < 0 ? 1 : 0)) * sheet->frameWidth,
        0.0f,
        sheet->frameWidth * (float)p->facing,   // negative width = flip
        sheet->frameHeight
    };

    float scale = p->spriteScale;
    float destW = sheet->frameWidth * scale;
    float destH = sheet->frameHeight * scale;

    float anchorX = sheet->frameWidth * p->spriteAnchorX;
    if (p->facing < 0) anchorX = sheet->frameWidth - anchorX;
    Vector2 origin = {
        anchorX * scale,
        (sheet->visibleBounds.y + sheet->visibleBounds.height) * scale
    };
    Vector2 drawPos = { p->position.x, p->position.y };

    Color tint = WHITE;
    if (p->invincible && ((int)(GetTime() * 10) % 2 == 0)) {
        tint = (Color){ 255, 100, 100, 200 };
    }
    if (!sheet->loaded) tint.a = 180;

    DrawTexturePro(sheet->texture, source,
                   (Rectangle){ drawPos.x, drawPos.y, destW, destH },
                   origin, 0.0f, tint);
}

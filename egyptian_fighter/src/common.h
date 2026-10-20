#ifndef COMMON_H
#define COMMON_H

#include "raylib.h"
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

#define SCREEN_WIDTH  1280
#define SCREEN_HEIGHT 720
#define TARGET_FPS    60

#define GROUND_Y      640.0f
#define PLAYER_WIDTH  80.0f
#define PLAYER_HEIGHT 160.0f

#define ANIM_SPEED_IDLE     0.12f
#define ANIM_SPEED_WALK     0.09f
#define ANIM_SPEED_ATTACK   0.07f
#define ANIM_SPEED_SPECIAL  0.08f
#define ANIM_SPEED_JUMP     0.06f
#define ANIM_SPEED_HIT      0.10f
#define ANIM_SPEED_OTHER    0.10f

#define MOVE_SPEED          4.5f
#define JUMP_FORCE         -14.0f
#define GRAVITY             0.55f
#define MAX_FALL_SPEED     18.0f

#define MAX_HEALTH          100
#define MAX_CHARACTERS      4

typedef enum {
    STATE_IDLE = 0,
    STATE_WALK,
    STATE_CROUCH,
    STATE_JUMP,
    STATE_PUNCH,
    STATE_KICK,
    STATE_SPECIAL1,
    STATE_SPECIAL2,
    STATE_BLOCK,
    STATE_HIT,
    STATE_THROW,
    STATE_JUMP_ATTACK,
    STATE_TAUNT,
    STATE_VICTORY,
    STATE_COUNT
} PlayerState;

typedef struct {
    Texture2D texture;
    int frameCount;
    float frameWidth;
    float frameHeight;
    Rectangle visibleBounds;
    bool loaded;
} SpriteSheet;

typedef struct {
    const char *name;
    const char *folder;
    const char *stageFile;
    const char *portraitFile;
} CharacterDef;

#endif

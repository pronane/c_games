#ifndef COMMON_H
#define COMMON_H

#include "raylib.h"
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include "gfx.h"

// all UI text goes through the sharp TTF font (gfx.c)
#define DrawText    UI_DrawText
#define MeasureText UI_MeasureText

#define SCREEN_WIDTH  1280
#define SCREEN_HEIGHT 720
#define TARGET_FPS    60

// The fight simulation always advances in fixed 1/60 s ticks (main.c accumulator), never by
// the measured frame time, so the same inputs give the same fight on every machine.
#define SIM_HZ        60
#define SIM_DT        (1.0f / 60.0f)          // what the sim adds to its float timers
#define SIM_DT_WALL   (1.0 / 60.0)            // wall-clock length of a tick (accumulator)
#define SIM_MAX_STEPS_PER_FRAME 4     // catch-up limit after a stall (offline play)

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
#define MAX_CHARACTERS      7

// projectile kinds (drawn procedurally by the game - see game.c)
#define PROJ_NONE  0
#define PROJ_BALL  1     // padel ball (Padel Mike, Daragh)
#define PROJ_BOOK  2     // purple book; special 2 throws a purple card (Dangerous Dec)
#define PROJ_CARD  3
#define PROJ_BUBBLE 4    // cartoon speech bubble "PARP!" / "PADEL!" (Daragh)
#define PROJ_FIRE   5    // orange fireball (Flame)
#define PROJ_FIRE_BLUE 6 // blue fireball (Dragon)

// ---- one rule set for every fighter (v4 consistency pass) ---------------------------
// Total length of each attack / reaction in seconds, whatever the number of frames in the
// sheet (frame time = length / frames).  Reference: Flame and Dragon's original timing.
#define MOVE_TIME_PUNCH        0.42f
#define MOVE_TIME_KICK         0.42f
#define MOVE_TIME_SPECIAL      0.48f
#define MOVE_TIME_THROW        0.42f
#define MOVE_TIME_JUMP_ATTACK  0.36f
#define MOVE_TIME_HIT          0.60f   // hit-stun
// an attack hurts from 1/3 to 5/6 of its length; a projectile leaves at 1/2
#define ACTIVE_FROM   (1.0f / 3.0f)
#define ACTIVE_TO     (5.0f / 6.0f)
#define PROJ_LAUNCH_AT 0.5f
#define MELEE_DAMAGE   8
#define PROJ_DAMAGE    10
#define PROJ_CHIP      1
#define PROJ_SPEED_HIGH 9.0f      // special 1 (px per frame at 60 fps)
#define PROJ_SPEED_LOW  10.5f     // special 2
#define PROJ_BOX        36.0f     // projectile hit box (square) - same for every kind
#define MAX_PROJECTILES 8

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
    // Grid mode (assets/<folder>/sprites.cfg present): every frame is one uniform cell,
    // feet on a common baseline, body centred horizontally in the cell.
    bool grid;
    bool shared;          // texture borrowed from another state (fallback) - don't unload
    float frameTime;      // seconds per frame (0 = use the global default)
    float originX;        // anchor inside a frame, in source pixels (feet / body centre)
    float originY;
    int loopFrom;         // one-shot sheet that keeps looping from this frame when it ends
                          // (sprites.cfg 'loop victory 2'); -1 = hold the last frame
} SpriteSheet;

typedef struct {
    const char *name;
    const char *folder;
    const char *stageFile;
    const char *portraitFile;
} CharacterDef;

#endif

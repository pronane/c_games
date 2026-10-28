#ifndef GAELIC_PLAYER_MODEL_H
#define GAELIC_PLAYER_MODEL_H

#include "game.h"
#include "raylib.h"

enum {
    PLAYER_POSE_IDLE,
    PLAYER_POSE_RUN_A,
    PLAYER_POSE_RUN_B,
    PLAYER_POSE_RUN_C,
    PLAYER_POSE_RUN_D,
    PLAYER_POSE_CARRY,
    PLAYER_POSE_CARRY_RUN_A,
    PLAYER_POSE_CARRY_RUN_B,
    PLAYER_POSE_CARRY_RUN_C,
    PLAYER_POSE_CARRY_RUN_D,
    PLAYER_POSE_JUMP,
    PLAYER_POSE_KICK,
    PLAYER_POSE_HANDPASS,
    PLAYER_POSE_FOOT_PICKUP,
    PLAYER_POSE_COUNT,
    PLAYER_MODEL_VARIATIONS = 5
};

typedef struct PlayerModels {
    Model models[GAME_TEAM_COUNT][PLAYER_MODEL_VARIATIONS][PLAYER_POSE_COUNT];
    int valid[GAME_TEAM_COUNT][PLAYER_MODEL_VARIATIONS][PLAYER_POSE_COUNT];
} PlayerModels;

int player_models_init(PlayerModels *players);
void player_models_unload(PlayerModels *players);
void player_models_draw(const PlayerModels *players, const GamePlayer *player,
                        int team, int number, int pose);

#endif

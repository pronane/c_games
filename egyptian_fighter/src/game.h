#ifndef GAME_H
#define GAME_H

#include "player.h"

typedef enum {
    SCREEN_SELECT = 0,
    SCREEN_FIGHT,
    SCREEN_RESULT
} GameScreen;

typedef enum {
    MODE_1P_VS_CPU = 0,
    MODE_CPU_VS_1P,
    MODE_1P_VS_2P
} SelectMode;

typedef struct {
    Player player1;
    Player player2;

    GameScreen screen;
    bool gameOver;
    int winner;
    float roundTimer;
    bool paused;

    CharacterDef characters[MAX_CHARACTERS];

    int selectP1;
    int selectP2;
    bool p1Ready;
    bool p2Ready;
    SelectMode mode;

    Texture2D stages[MAX_CHARACTERS];
    Texture2D portraits[MAX_CHARACTERS];
    bool stageLoaded[MAX_CHARACTERS];
    bool portraitLoaded[MAX_CHARACTERS];
} Game;

void Game_Init(Game *g);
void Game_Update(Game *g);
void Game_Draw(const Game *g);
void Game_Unload(Game *g);

#endif

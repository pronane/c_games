#ifndef GAME_H
#define GAME_H

#include <stdint.h>
#include "player.h"
#include "pad.h"

typedef enum {
    SCREEN_SELECT = 0,
    SCREEN_FIGHT,
    SCREEN_RESULT,
    SCREEN_PADTEST,      // controller test + controls help
    SCREEN_PREFIGHT,     // "PADEL WARS" face-off between select and fight
    SCREEN_ONLINE        // online menu: quick match / create / join (online.c)
} GameScreen;

typedef enum {
    MODE_1P_VS_CPU = 0,
    MODE_CPU_VS_1P,
    MODE_1P_VS_2P,
    MODE_ONLINE,         // two players over the internet (online.c)
    MODE_COUNT
} SelectMode;

typedef struct {
    bool active;
    int kind;            // PROJ_BALL / PROJ_BOOK / PROJ_CARD / PROJ_BUBBLE
    int variant;         // bubble text: 0 = special 1 ("PARP!"), 1 = special 2 ("PADEL!")
    Vector2 origin;      // where it was launched from (the bubble's tail points back there)
    int owner;           // 1 or 2
    Vector2 pos;
    float vx;
    float spin;          // degrees, for drawing
    float age;
} Projectile;

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
    float selTime;         // select screen clock (cursor pulse)
    float selFlash;        // when the shared cursor jumped to the second slot
    int startPending;      // both ready: draw one "loading" frame, then StartFight

    Texture2D stages[MAX_CHARACTERS];
    Texture2D portraits[MAX_CHARACTERS];
    bool stageLoaded[MAX_CHARACTERS];
    bool portraitLoaded[MAX_CHARACTERS];

    Projectile projectiles[MAX_PROJECTILES];
    int cpuAttackCooldown;

    // pre-fight screen
    float prefightTimer;
    Texture2D faces[2];            // head-and-shoulders of P1 / P2 for the face-off
    bool faceOwned[2];             // created for the face-off (unload it afterwards)
    bool faceMirror[2];            // flip so the two fighters look at each other
    char captions[MAX_CHARACTERS][96];   // assets/captions.cfg (default: the fighter's name)
    char vsTitle[64];

    bool padWaitRelease;   // ignore a pad A/Start still held from the select screen
    char pauseNote[128];   // e.g. "P1 controller disconnected"

    uint16_t netPrev[2];   // online: last frame's input bits (press = down now, up before)
} Game;

void Game_Init(Game *g);
void Game_Update(Game *g);
void Game_Draw(const Game *g);
void Game_Unload(Game *g);

// online lockstep (online.c): the fight step is deterministic with a fixed dt and these inputs
void Game_LoadFight(Game *g);                  // load selectP1/P2 sprites, face-off screen
void Game_ResetFight(Game *g);                 // round start state, sprites kept
void Game_FightStep(Game *g, float dt);        // one sim step from the players' input flags
void Game_ApplyBits(Player *p, uint16_t bits, uint16_t prev);
uint32_t Game_Hash(const Game *g);

#endif

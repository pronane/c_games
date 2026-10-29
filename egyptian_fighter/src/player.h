#ifndef PLAYER_H
#define PLAYER_H

#include "common.h"

typedef struct Player {
    // Position & physics
    Vector2 position;
    Vector2 velocity;
    float spriteScale;
    float spriteAnchorX;
    bool onGround;
    int facing;          // 1 = right, -1 = left

    // Animation
    PlayerState state;
    PlayerState prevState;
    int currentFrame;
    float frameTimer;
    float stateTimer;

    // Combat
    int health;
    bool invincible;
    float invincibleTimer;
    bool attackActive;
    Rectangle hitbox;
    Rectangle hurtbox;

    // Which character this player is using (index into Game.characters)
    int characterIndex;

    // Specials that fire a projectile (sprites.cfg 'projectile ball|book'); 0 = melee specials
    int projectileKind;
    bool projectileFired;   // already launched during the current special
    float opponentX;        // set by the game every frame: used to keep facing the opponent

    // Sprite sheets (indexed by PlayerState)
    SpriteSheet sheets[STATE_COUNT];

    // Input flags (set by game each frame)
    bool inputLeft;
    bool inputRight;
    bool inputDown;
    bool inputUp;
    bool inputPunch;
    bool inputKick;
    bool inputSpecial1;
    bool inputSpecial2;
    bool inputBlock;
    bool inputThrow;
    bool inputTaunt;
    bool inputJumpAttack;
} Player;

// Lifecycle
void Player_Init(Player *p, float startX, float startY, int facing, int characterIndex);
void Player_LoadSprites(Player *p, const char *assetsRoot, const CharacterDef *chars);
void Player_UnloadSprites(Player *p);

// Main loop
void Player_Update(Player *p, float dt);
void Player_Draw(const Player *p);

// Helpers
void Player_SetState(Player *p, PlayerState newState);
bool Player_IsAttacking(const Player *p);
bool Player_CanMove(const Player *p);
Rectangle Player_GetHurtbox(const Player *p);
float Player_FrameTime(const Player *p);        // seconds per frame of the current state
float Player_Progress(const Player *p);         // 0..1 through the current one-shot state

#endif // PLAYER_H

#ifndef GOLDENEYE_GAME_H
#define GOLDENEYE_GAME_H

#include <stdbool.h>

#define GAME_GUARD_COUNT 6
#define GAME_WALL_COUNT 8
#define GAME_WEAPON_COUNT 2
#define GAME_SIDEARM 0
#define GAME_CARBINE 1
#define GAME_WORLD_LIMIT 11.4f
#define GAME_CARBINE_X -6.0f
#define GAME_CARBINE_Z 7.0f

typedef struct {
    float x;
    float z;
    float width;
    float depth;
    float height;
} GameWall;

typedef struct {
    float x;
    float z;
    float phase;
    int type;
    int health;
    float attack_cooldown;
    bool active;
} GuardEntity;

typedef struct {
    float position[3];
    float yaw;
    float pitch;
    float health;
    float fire_cooldown;
    float reload_timer;
    float shot_timer;
    float hit_marker_timer;
    float damage_flash_timer;
    float pickup_feedback_timer;
    float match_time;
    int current_weapon;
    int ammo[GAME_WEAPON_COUNT];
    int reserve_ammo[GAME_WEAPON_COUNT];
    bool has_carbine;
    bool aiming;
    bool has_data_core;
    bool mission_complete;
    bool shot_event;
    bool hit_event;
    bool pickup_event;
    bool reload_event;
    GuardEntity guards[GAME_GUARD_COUNT];
} GameState;

typedef struct {
    float move_x;
    float move_y;
    float look_x;
    float look_y;
    bool fire;
    bool interact;
    bool sprint;
    bool aim;
    bool reload;
    bool switch_weapon;
} GameInput;

extern const GameWall GameWalls[GAME_WALL_COUNT];

void GameInit(GameState *game);
void GameUpdate(GameState *game, GameInput input, float delta_time);
int GameActiveGuards(const GameState *game);

#endif

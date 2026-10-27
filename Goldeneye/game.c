#include "game.h"

#include <math.h>
#include <string.h>

#define PLAYER_RADIUS 0.32f
#define CORE_X 7.0f
#define CORE_Z -7.0f
#define EXIT_X 9.0f
#define EXIT_Z -9.0f
#define PI 3.14159265f

static const int WeaponMagazineSize[GAME_WEAPON_COUNT] = {12, 24};
static const int WeaponDamage[GAME_WEAPON_COUNT] = {55, 34};
static const float WeaponFireInterval[GAME_WEAPON_COUNT] = {0.30f, 0.105f};
static const float WeaponRange[GAME_WEAPON_COUNT] = {24.0f, 34.0f};
static const float WeaponReloadDuration[GAME_WEAPON_COUNT] = {0.95f, 1.25f};

const GameWall GameWalls[GAME_WALL_COUNT] = {
    {-4.0f, 3.0f, 0.7f, 7.0f, 3.6f},
    {2.0f, 1.0f, 7.0f, 0.7f, 3.6f},
    {5.0f, -5.0f, 0.7f, 6.0f, 3.6f},
    {-1.0f, -6.0f, 6.0f, 0.7f, 3.6f},
    {-8.0f, -5.0f, 0.7f, 5.0f, 3.6f},
    {-7.0f, 0.0f, 4.0f, 0.7f, 3.6f},
    {8.0f, 3.0f, 0.7f, 5.0f, 3.6f},
    {1.0f, 7.0f, 5.0f, 0.7f, 3.6f}
};

static const float GuardStart[GAME_GUARD_COUNT][2] = {
    {-2.0f, 7.0f}, {4.0f, -1.5f}, {7.0f, -5.0f},
    {-1.5f, -7.8f}, {9.0f, 5.0f}, {-9.0f, 5.0f}
};

static float ClampFloat(float value, float minimum, float maximum)
{
    if (value < minimum) return minimum;
    if (value > maximum) return maximum;
    return value;
}

static float DistanceSquared(float x1, float z1, float x2, float z2)
{
    const float dx = x1 - x2;
    const float dz = z1 - z2;
    return dx * dx + dz * dz;
}

static bool CollidesWithWorld(float x, float z)
{
    for (int i = 0; i < GAME_WALL_COUNT; ++i) {
        const GameWall *wall = &GameWalls[i];
        const float near_x = ClampFloat(x, wall->x - wall->width * 0.5f,
                                        wall->x + wall->width * 0.5f);
        const float near_z = ClampFloat(z, wall->z - wall->depth * 0.5f,
                                        wall->z + wall->depth * 0.5f);
        if (DistanceSquared(x, z, near_x, near_z) < PLAYER_RADIUS * PLAYER_RADIUS) {
            return true;
        }
    }
    return false;
}

static bool RayIntersectsWall(float origin_x, float origin_z, float direction_x,
                              float direction_z, float max_distance,
                              const GameWall *wall)
{
    float near_distance = 0.0f;
    float far_distance = max_distance;
    const float origin[2] = {origin_x, origin_z};
    const float direction[2] = {direction_x, direction_z};
    const float minimum[2] = {wall->x - wall->width * 0.5f,
                              wall->z - wall->depth * 0.5f};
    const float maximum[2] = {wall->x + wall->width * 0.5f,
                              wall->z + wall->depth * 0.5f};

    for (int axis = 0; axis < 2; ++axis) {
        if (fabsf(direction[axis]) < 0.0001f) {
            if (origin[axis] < minimum[axis] || origin[axis] > maximum[axis]) {
                return false;
            }
            continue;
        }

        float first = (minimum[axis] - origin[axis]) / direction[axis];
        float second = (maximum[axis] - origin[axis]) / direction[axis];
        if (first > second) {
            const float swap = first;
            first = second;
            second = swap;
        }
        near_distance = fmaxf(near_distance, first);
        far_distance = fminf(far_distance, second);
        if (near_distance > far_distance) return false;
    }
    return far_distance >= 0.0f && near_distance < max_distance;
}

static bool HasLineOfSight(float from_x, float from_z, float to_x, float to_z)
{
    const float dx = to_x - from_x;
    const float dz = to_z - from_z;
    const float distance = sqrtf(dx * dx + dz * dz);
    if (distance <= 0.001f) return true;

    const float direction_x = dx / distance;
    const float direction_z = dz / distance;
    for (int i = 0; i < GAME_WALL_COUNT; ++i) {
        if (RayIntersectsWall(from_x, from_z, direction_x, direction_z,
                              distance, &GameWalls[i])) {
            return false;
        }
    }
    return true;
}

static float GuardX(const GuardEntity *guard, float time)
{
    return guard->x + sinf(time * 0.5f + guard->phase) * 0.38f;
}

static float GuardZ(const GuardEntity *guard, float time)
{
    return guard->z + cosf(time * 0.42f + guard->phase) * 0.3f;
}

void GameInit(GameState *game)
{
    memset(game, 0, sizeof(*game));
    game->position[0] = -9.0f;
    game->position[1] = 1.65f;
    game->position[2] = 8.5f;
    game->yaw = PI;
    game->health = 100.0f;
    game->current_weapon = GAME_SIDEARM;
    game->ammo[GAME_SIDEARM] = WeaponMagazineSize[GAME_SIDEARM];
    game->reserve_ammo[GAME_SIDEARM] = 48;
    for (int i = 0; i < GAME_GUARD_COUNT; ++i) {
        game->guards[i].x = GuardStart[i][0];
        game->guards[i].z = GuardStart[i][1];
        game->guards[i].phase = 0.9f + (float)i * 0.83f;
        game->guards[i].type = i;
        game->guards[i].health = 100;
        game->guards[i].attack_cooldown = 0.5f + (float)(i % 3) * 0.25f;
        game->guards[i].active = true;
    }
}

static void UpdatePlayer(GameState *game, GameInput input, float dt)
{
    game->yaw += input.look_x;
    game->pitch = ClampFloat(game->pitch + input.look_y, -1.15f, 1.15f);
    game->aiming = input.aim;

    const float forward_x = sinf(game->yaw);
    const float forward_z = cosf(game->yaw);
    const float right_x = cosf(game->yaw);
    const float right_z = -sinf(game->yaw);
    float dx = forward_x * input.move_y + right_x * input.move_x;
    float dz = forward_z * input.move_y + right_z * input.move_x;
    const float length = sqrtf(dx * dx + dz * dz);
    if (length > 0.001f) {
        float speed = input.sprint ? 6.0f : 3.7f;
        if (input.aim) speed *= 0.7f;
        dx *= speed * dt / fmaxf(1.0f, length);
        dz *= speed * dt / fmaxf(1.0f, length);
        const float next_x = ClampFloat(game->position[0] + dx,
                                        -GAME_WORLD_LIMIT, GAME_WORLD_LIMIT);
        const float next_z = ClampFloat(game->position[2] + dz,
                                        -GAME_WORLD_LIMIT, GAME_WORLD_LIMIT);
        if (!CollidesWithWorld(next_x, game->position[2])) game->position[0] = next_x;
        if (!CollidesWithWorld(game->position[0], next_z)) game->position[2] = next_z;
    }
}

static void UpdateGuards(GameState *game, float dt, float time)
{
    for (int i = 0; i < GAME_GUARD_COUNT; ++i) {
        GuardEntity *guard = &game->guards[i];
        if (!guard->active) continue;

        const float gx = GuardX(guard, time);
        const float gz = GuardZ(guard, time);
        const float dx = game->position[0] - gx;
        const float dz = game->position[2] - gz;
        const float distance = sqrtf(dx * dx + dz * dz);
        if (distance < 10.0f && distance > 2.2f) {
            const float step = fminf(0.65f * dt, distance - 2.2f);
            const float next_x = ClampFloat(guard->x + dx / distance * step,
                                            -GAME_WORLD_LIMIT, GAME_WORLD_LIMIT);
            const float next_z = ClampFloat(guard->z + dz / distance * step,
                                            -GAME_WORLD_LIMIT, GAME_WORLD_LIMIT);
            if (!CollidesWithWorld(next_x, guard->z)) guard->x = next_x;
            if (!CollidesWithWorld(guard->x, next_z)) guard->z = next_z;
        }

        guard->attack_cooldown = fmaxf(0.0f, guard->attack_cooldown - dt);
        if (distance < 9.0f && HasLineOfSight(gx, gz, game->position[0],
                                              game->position[2]) &&
            guard->attack_cooldown <= 0.0f) {
            game->health = fmaxf(0.0f, game->health - 7.0f);
            game->damage_flash_timer = 0.18f;
            guard->attack_cooldown = 1.0f;
        }
    }
}

static void FireAtGuards(GameState *game, float time)
{
    const int weapon = game->current_weapon;
    if (game->fire_cooldown > 0.0f || game->reload_timer > 0.0f ||
        game->health <= 0.0f || game->ammo[weapon] <= 0) {
        return;
    }
    game->fire_cooldown = WeaponFireInterval[weapon];
    game->shot_timer = 0.12f;
    game->shot_event = true;
    --game->ammo[weapon];

    const float horizontal = cosf(game->pitch);
    const float direction_x = sinf(game->yaw) * horizontal;
    const float direction_y = sinf(game->pitch);
    const float direction_z = cosf(game->yaw) * horizontal;
    const float horizontal_scale = sqrtf(direction_x * direction_x +
                                         direction_z * direction_z);
    int target = -1;
    float closest_distance = WeaponRange[weapon];

    for (int i = 0; i < GAME_GUARD_COUNT; ++i) {
        const GuardEntity *guard = &game->guards[i];
        if (!guard->active) continue;

        const float tx = GuardX(guard, time) - game->position[0];
        const float ty = 1.42f - game->position[1];
        const float tz = GuardZ(guard, time) - game->position[2];
        const float distance = tx * direction_x + ty * direction_y +
                               tz * direction_z;
        if (distance <= 0.0f || distance >= closest_distance) continue;

        const float miss_x = tx - distance * direction_x;
        const float miss_y = ty - distance * direction_y;
        const float miss_z = tz - distance * direction_z;
        if (miss_x * miss_x + miss_y * miss_y + miss_z * miss_z > 0.42f * 0.42f) {
            continue;
        }

        const float wall_distance = distance * horizontal_scale;
        bool blocked = false;
        for (int wall = 0; wall < GAME_WALL_COUNT; ++wall) {
            if (RayIntersectsWall(game->position[0], game->position[2],
                                  horizontal_scale > 0.001f ?
                                      direction_x / horizontal_scale : 0.0f,
                                  horizontal_scale > 0.001f ?
                                      direction_z / horizontal_scale : 0.0f,
                                  wall_distance, &GameWalls[wall])) {
                blocked = true;
                break;
            }
        }
        if (!blocked) {
            target = i;
            closest_distance = distance;
        }
    }

    if (target >= 0) {
        game->guards[target].health -= WeaponDamage[weapon];
        game->hit_event = true;
        game->hit_marker_timer = 0.16f;
        if (game->guards[target].health <= 0) {
            game->guards[target].active = false;
        }
    }
}

static void StartReload(GameState *game)
{
    const int weapon = game->current_weapon;
    if (game->reload_timer > 0.0f ||
        game->ammo[weapon] >= WeaponMagazineSize[weapon] ||
        game->reserve_ammo[weapon] <= 0) {
        return;
    }
    game->reload_timer = WeaponReloadDuration[weapon];
    game->reload_event = true;
}

static void CompleteReload(GameState *game)
{
    const int weapon = game->current_weapon;
    const int needed = WeaponMagazineSize[weapon] - game->ammo[weapon];
    const int loaded = needed < game->reserve_ammo[weapon] ?
                       needed : game->reserve_ammo[weapon];
    game->ammo[weapon] += loaded;
    game->reserve_ammo[weapon] -= loaded;
}

void GameUpdate(GameState *game, GameInput input, float delta_time)
{
    game->shot_event = false;
    game->hit_event = false;
    game->pickup_event = false;
    game->reload_event = false;

    const float dt = ClampFloat(delta_time, 0.0f, 0.05f);
    game->fire_cooldown = fmaxf(0.0f, game->fire_cooldown - dt);
    game->shot_timer = fmaxf(0.0f, game->shot_timer - dt);
    game->hit_marker_timer = fmaxf(0.0f, game->hit_marker_timer - dt);
    game->damage_flash_timer = fmaxf(0.0f, game->damage_flash_timer - dt);
    game->pickup_feedback_timer = fmaxf(0.0f, game->pickup_feedback_timer - dt);
    if (game->mission_complete || game->health <= 0.0f) return;

    UpdatePlayer(game, input, dt);
    game->match_time += dt;
    UpdateGuards(game, dt, game->match_time);

    if (input.switch_weapon && game->has_carbine && game->reload_timer <= 0.0f) {
        game->current_weapon = game->current_weapon == GAME_SIDEARM ?
                               GAME_CARBINE : GAME_SIDEARM;
    }

    if (input.interact && !game->has_carbine &&
        DistanceSquared(game->position[0], game->position[2],
                        GAME_CARBINE_X, GAME_CARBINE_Z) < 1.8f * 1.8f) {
        game->has_carbine = true;
        game->current_weapon = GAME_CARBINE;
        game->ammo[GAME_CARBINE] = WeaponMagazineSize[GAME_CARBINE];
        game->reserve_ammo[GAME_CARBINE] = 72;
        game->pickup_event = true;
        game->pickup_feedback_timer = 1.5f;
    } else if (input.interact && !game->has_data_core &&
               DistanceSquared(game->position[0], game->position[2],
                               CORE_X, CORE_Z) < 2.1f * 2.1f) {
        game->has_data_core = true;
    } else if (input.interact && game->has_data_core &&
               DistanceSquared(game->position[0], game->position[2],
                               EXIT_X, EXIT_Z) < 2.1f * 2.1f) {
        game->mission_complete = true;
    }

    if (game->reload_timer > 0.0f) {
        game->reload_timer = fmaxf(0.0f, game->reload_timer - dt);
        if (game->reload_timer <= 0.0f) CompleteReload(game);
    } else if (input.reload) {
        StartReload(game);
    }
    if (input.fire) FireAtGuards(game, game->match_time);
}

int GameActiveGuards(const GameState *game)
{
    int active = 0;
    for (int i = 0; i < GAME_GUARD_COUNT; ++i) {
        if (game->guards[i].active) ++active;
    }
    return active;
}

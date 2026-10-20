#include "game.h"

#include <math.h>

#define PLAYER_SPEED 7.0f
#define AI_SPEED 5.5f
#define HIGH_FIELD_RADIUS 2.1f
#define HIGH_FIELD_REACH 4.2f
#define KICKER_PICKUP_GUARD 3.5f
#define CPU_TACKLE_RANGE 2.2f
#define CPU_TACKLE_COMMIT_TIME 0.3f
#define PICKUP_ANIMATION_TIME 0.45f
#define FOOT_PICKUP_RADIUS 1.6f

static const char *TEAM_NAMES[GAME_TEAM_COUNT] = {
    "North Coast", "River County", "Red Valley", "Highland"
};

static const float FORMATION_X[GAME_TEAM_SIZE] = {
    5.0f, 18.0f, 18.0f, 18.0f, 37.0f, 37.0f, 37.0f, 65.0f,
    65.0f, 92.0f, 92.0f, 92.0f, 117.0f, 117.0f, 117.0f
};

static const float FORMATION_Z[GAME_TEAM_SIZE] = {
    42.5f, 17.0f, 42.5f, 68.0f, 9.0f, 42.5f, 76.0f, 32.0f,
    53.0f, 9.0f, 42.5f, 76.0f, 17.0f, 42.5f, 68.0f
};

static float clampf(float value, float low, float high)
{
    if (value < low) return low;
    if (value > high) return high;
    return value;
}

static float distance_squared(float x1, float z1, float x2, float z2)
{
    float dx = x2 - x1;
    float dz = z2 - z1;
    return dx * dx + dz * dz;
}

static float segment_closest_fraction(float x1, float z1, float x2, float z2,
                                      float px, float pz)
{
    float dx = x2 - x1;
    float dz = z2 - z1;
    float length_squared = dx * dx + dz * dz;
    if (length_squared < 0.0001f) return 0.0f;
    return clampf(((px - x1) * dx + (pz - z1) * dz) / length_squared,
                  0.0f, 1.0f);
}

static void ball_landing_position(const GameState *game,
                                 float *landing_x, float *landing_z)
{
    float discriminant = game->ball.velocity_y * game->ball.velocity_y +
        2.0f * GAME_BALL_GRAVITY * fmaxf(game->ball.height - 0.18f, 0.0f);
    float time = (game->ball.velocity_y + sqrtf(discriminant)) /
                 GAME_BALL_GRAVITY;
    if (time < 0.0f) time = 0.0f;
    if (time > 3.0f) time = 3.0f;
    *landing_x = clampf(game->ball.x + game->ball.velocity_x * time,
                        1.0f, GAME_PITCH_LENGTH - 1.0f);
    *landing_z = clampf(game->ball.z + game->ball.velocity_z * time,
                        1.0f, GAME_PITCH_WIDTH - 1.0f);
}

static void set_event(GameState *game, GameEvent event)
{
    game->event = event;
    game->event_time = 2.0f;
}

static void sync_selected_player(GameState *game)
{
    GamePlayer *player = &game->players[0][game->selected_player];
    game->player_x = player->x;
    game->player_z = player->z;
    game->facing_x = player->facing_x;
    game->facing_z = player->facing_z;
    game->has_ball = game->ball_team == 0 &&
                     game->ball_player == game->selected_player;
}

static void reset_positions(GameState *game)
{
    int team;
    int player;
    for (team = 0; team < 2; team++) {
        for (player = 0; player < GAME_TEAM_SIZE; player++) {
            GamePlayer *member = &game->players[team][player];
            member->x = team == 0 ? FORMATION_X[player] :
                                    GAME_PITCH_LENGTH - FORMATION_X[player];
            member->z = FORMATION_Z[player];
            member->facing_x = team == 0 ? 1.0f : -1.0f;
            member->facing_z = 0.0f;
            member->movement = 0.0f;
            member->jump_time = 0.0f;
        }
    }
}

static void reset_ball(GameState *game, int team, int player)
{
    game->ball_team = team;
    game->ball_player = player;
    game->ball.x = GAME_PITCH_LENGTH * 0.5f;
    game->ball.z = GAME_PITCH_WIDTH * 0.5f;
    game->ball.height = 0.25f;
    game->ball.velocity_x = 0.0f;
    game->ball.velocity_z = 0.0f;
    game->ball.velocity_y = 0.0f;
    game->ball.curve = 0.0f;
    game->ball.in_flight = 0;
    game->pickup_delay = 0.0f;
    game->cpu_possession_time = 0.0f;
    game->cpu_tackle_time = 0.0f;
    game->pickup_time = 0.0f;
    game->restart_pending = 0;
    game->kickout_in_progress = 0;
    game->kickout_team = -1;
    game->pickup_team = -1;
    game->pickup_player = -1;
    game->last_release_team = -1;
    game->last_release_player = -1;
}

void game_init(GameState *game)
{
    game->selected_player = 9;
    game->home_team = 0;
    game->away_team = 1;
    game->step_time = 0.0f;
    game->event_time = 0.0f;
    game->pickup_delay = 0.0f;
    game->cpu_possession_time = 0.0f;
    game->steps_carried = 0;
    game->last_was_bounce = 0;
    game->last_touch_team = 0;
    game->restart_pending = 0;
    game->kickout_in_progress = 0;
    game->kickout_team = -1;
    game->points = 0;
    game->goals = 0;
    game->team_goals[0] = 0;
    game->team_goals[1] = 0;
    game->team_points[0] = 0;
    game->team_points[1] = 0;
    game->fouls = 0;
    game->event = GAME_EVENT_NONE;
    reset_positions(game);
    reset_ball(game, 0, game->selected_player);
    sync_selected_player(game);
}

void game_set_teams(GameState *game, int home_team, int away_team, int starting_player)
{
    if (home_team < 0 || home_team >= GAME_TEAM_COUNT) home_team = 0;
    if (away_team < 0 || away_team >= GAME_TEAM_COUNT) away_team = 1;
    if (home_team == away_team) away_team = (home_team + 1) % GAME_TEAM_COUNT;
    if (starting_player < 0 || starting_player >= GAME_TEAM_SIZE) starting_player = 9;

    game_init(game);
    game->home_team = home_team;
    game->away_team = away_team;
    game->selected_player = starting_player;
    reset_ball(game, 0, starting_player);
    sync_selected_player(game);
}

void game_select_player(GameState *game, int player_index)
{
    if (player_index < 0 || player_index >= GAME_TEAM_SIZE) return;
    game->selected_player = player_index;
    sync_selected_player(game);
}

void game_select_next_player(GameState *game, int direction)
{
    int next = game->selected_player + (direction < 0 ? -1 : 1);
    if (next < 0) next = GAME_TEAM_SIZE - 1;
    if (next >= GAME_TEAM_SIZE) next = 0;
    game_select_player(game, next);
}

void game_select_nearest_player(GameState *game)
{
    int player;
    int nearest = game->selected_player;
    float nearest_distance = 1000000.0f;
    int alternate = game->selected_player;
    float alternate_distance = 1000000.0f;
    for (player = 0; player < GAME_TEAM_SIZE; player++) {
        GamePlayer *member = &game->players[0][player];
        float distance = distance_squared(member->x, member->z,
                                          game->ball.x, game->ball.z);
        if (distance < nearest_distance) {
            alternate = nearest;
            alternate_distance = nearest_distance;
            nearest_distance = distance;
            nearest = player;
        } else if (distance < alternate_distance) {
            alternate_distance = distance;
            alternate = player;
        }
    }
    game_select_player(game, nearest != game->selected_player ?
                       nearest : alternate);
}

static void release_ball(GameState *game, float speed, float lift,
                         float curve)
{
    GamePlayer *player = &game->players[0][game->selected_player];
    int is_kickout = game->restart_pending;
    int kickout_team = game->ball_team;
    float aim_x = player->facing_x;
    float aim_z = player->facing_z;
    float aim_length = sqrtf(aim_x * aim_x + aim_z * aim_z);

    if (aim_length < 0.001f) {
        aim_x = 1.0f;
        aim_z = 0.0f;
    } else {
        aim_x /= aim_length;
        aim_z /= aim_length;
    }

    game->ball_team = -1;
    game->ball_player = -1;
    game->steps_carried = 0;
    game->step_time = 0.0f;
    game->ball.x = player->x + aim_x * 0.9f;
    game->ball.z = player->z + aim_z * 0.9f;
    game->ball.height = 1.1f;
    game->ball.velocity_x = aim_x * speed;
    game->ball.velocity_z = aim_z * speed;
    game->ball.velocity_y = lift;
    game->ball.curve = clampf(curve, -1.0f, 1.0f);
    game->ball.in_flight = 1;
    game->pickup_delay = 0.2f;
    game->last_release_team = 0;
    game->last_release_player = game->selected_player;
    game->last_touch_team = 0;
    game->restart_pending = 0;
    game->kickout_in_progress = is_kickout;
    game->kickout_team = is_kickout ? kickout_team : -1;
    sync_selected_player(game);
}

static float kickout_line_x(int restart_team)
{
    return restart_team == 0 ? GAME_KICKOUT_LINE :
                              GAME_PITCH_LENGTH - GAME_KICKOUT_LINE;
}

static void clear_kickout_arc(GameState *game, int kicker_team, int kicker,
                             float arc_x, float arc_z)
{
    int team;
    int player;
    for (team = 0; team < 2; team++) {
        for (player = 0; player < GAME_TEAM_SIZE; player++) {
            GamePlayer *member = &game->players[team][player];
            float dx;
            float dz;
            float distance;
            if (team == kicker_team && player == kicker) continue;
            dx = member->x - arc_x;
            dz = member->z - arc_z;
            distance = sqrtf(dx * dx + dz * dz);
            if (distance < GAME_KICKOUT_ARC_RADIUS) {
                float angle = atan2f(dz, dx);
                float offset = GAME_KICKOUT_ARC_RADIUS + 2.0f;
                member->x = clampf(arc_x + cosf(angle) * offset,
                                   1.0f, GAME_PITCH_LENGTH - 1.0f);
                member->z = clampf(arc_z + sinf(angle) * offset,
                                   1.0f, GAME_PITCH_WIDTH - 1.0f);
            }
        }
    }
}

static void start_kick_in(GameState *game, int restart_team,
                          float restart_x, float restart_z)
{
    int player;
    int kicker = 0;
    float closest_distance = 1000000.0f;
    float kickout_x;
    float kickout_z;

    if (restart_team != 0 && restart_team != 1) restart_team = 0;
    kickout_x = kickout_line_x(restart_team);
    kickout_z = GAME_PITCH_WIDTH * 0.5f;

    if (restart_z <= 1.0f || restart_z >= GAME_PITCH_WIDTH - 1.0f) {
        restart_x = kickout_x;
        restart_z = kickout_z;
    }

    restart_x = clampf(restart_x, 1.0f, GAME_PITCH_LENGTH - 1.0f);
    restart_z = clampf(restart_z, 1.0f, GAME_PITCH_WIDTH - 1.0f);
    for (player = 0; player < GAME_TEAM_SIZE; player++) {
        GamePlayer *member = &game->players[restart_team][player];
        float distance = distance_squared(member->x, member->z,
                                          restart_x, restart_z);
        if (distance < closest_distance) {
            closest_distance = distance;
            kicker = player;
        }
    }

    if (restart_z <= 1.0f || restart_z >= GAME_PITCH_WIDTH - 1.0f) {
        kicker = 0;
        restart_x = kickout_x;
        restart_z = kickout_z;
    }

    clear_kickout_arc(game, restart_team, kicker, kickout_x, kickout_z);
    game->players[restart_team][kicker].x = restart_x;
    game->players[restart_team][kicker].z = restart_z;
    game->players[restart_team][kicker].facing_x = restart_team == 0 ? 1.0f : -1.0f;
    game->players[restart_team][kicker].facing_z = 0.0f;
    game->players[restart_team][kicker].movement = 0.0f;
    game->ball_team = restart_team;
    game->ball_player = kicker;
    game->ball.x = restart_x;
    game->ball.z = restart_z;
    game->ball.height = 1.05f;
    game->ball.velocity_x = 0.0f;
    game->ball.velocity_z = 0.0f;
    game->ball.velocity_y = 0.0f;
    game->ball.curve = 0.0f;
    game->ball.in_flight = 0;
    game->pickup_delay = 0.0f;
    game->last_touch_team = restart_team;
    game->restart_pending = 1;
    game->kickout_in_progress = 0;
    game->kickout_team = -1;
    if (restart_team == 0) game_select_player(game, kicker);
}

static void cpu_kick_in(GameState *game)
{
    const int team = 1;
    int kicker = game->ball_player;
    int player;
    int receiver = -1;
    float target_x;
    float target_z;
    float best_distance = 1000000.0f;
    float dx;
    float dz;
    float length;

    if (kicker < 0 || kicker >= GAME_TEAM_SIZE) return;

    target_x = clampf(game->players[team][kicker].x - 15.0f,
                      1.0f, GAME_PITCH_LENGTH - 1.0f);
    target_z = clampf(game->players[team][kicker].z +
                      (GAME_PITCH_WIDTH * 0.5f -
                       game->players[team][kicker].z) * 0.35f,
                      1.0f, GAME_PITCH_WIDTH - 1.0f);
    for (player = 0; player < GAME_TEAM_SIZE; player++) {
        float distance;
        if (player == kicker) continue;
        distance = distance_squared(game->players[team][player].x,
                                    game->players[team][player].z,
                                    target_x, target_z);
        if (distance < best_distance) {
            best_distance = distance;
            receiver = player;
        }
    }
    if (receiver < 0) return;

    dx = game->players[team][receiver].x - game->players[team][kicker].x;
    dz = game->players[team][receiver].z - game->players[team][kicker].z;
    length = sqrtf(dx * dx + dz * dz);
    if (length < 0.001f) return;

    game->players[team][kicker].facing_x = dx / length;
    game->players[team][kicker].facing_z = dz / length;
    game->ball_team = -1;
    game->ball_player = -1;
    game->ball.x = game->players[team][kicker].x +
                   game->players[team][kicker].facing_x * 0.9f;
    game->ball.z = game->players[team][kicker].z +
                   game->players[team][kicker].facing_z * 0.9f;
    game->ball.height = 1.1f;
    game->ball.velocity_x = game->players[team][kicker].facing_x * 16.0f;
    game->ball.velocity_z = game->players[team][kicker].facing_z * 16.0f;
    game->ball.velocity_y = 4.5f;
    game->ball.curve = 0.0f;
    game->ball.in_flight = 1;
    game->pickup_delay = 0.2f;
    game->last_release_team = team;
    game->last_release_player = kicker;
    game->last_touch_team = team;
    game->restart_pending = 0;
    game->kickout_in_progress = 1;
    game->kickout_team = team;
    set_event(game, GAME_EVENT_KICKED);
}

static void update_cpu_players(GameState *game, float delta_time)
{
    int team;
    int player;
    float target_x = game->ball.x;
    float target_z = game->ball.z;
    if (game->ball_team < 0 && game->ball.in_flight)
        ball_landing_position(game, &target_x, &target_z);

    for (team = 0; team < 2; team++) {
        int closest = -1;
        float closest_distance = 1000000.0f;
        float chase_x = target_x;
        float chase_z = target_z;

        if (game->ball_team >= 0 && game->ball_player >= 0 &&
            game->ball_team != team) {
            const GamePlayer *carrier =
                &game->players[game->ball_team][game->ball_player];
            chase_x = carrier->x;
            chase_z = carrier->z;
        }

        for (player = 0; player < GAME_TEAM_SIZE; player++) {
            GamePlayer *member = &game->players[team][player];
            if (member->jump_time > 0.0f) {
                member->jump_time -= delta_time;
                if (member->jump_time < 0.0f) member->jump_time = 0.0f;
            }
            if (team == 0 && player == game->selected_player) continue;
            member->movement *= 0.2f;
            if (game->pickup_team == team &&
                game->pickup_player == player) {
                member->movement = 0.0f;
                continue;
            }
            if (game->ball_team < 0 && game->ball.in_flight &&
                game->ball.height >= 1.2f && game->ball.height <= 4.8f &&
                distance_squared(member->x, member->z, game->ball.x,
                                 game->ball.z) <= 4.0f * 4.0f) {
                member->jump_time = 0.7f;
            }
            if (game->ball_team != team) {
                float distance = distance_squared(member->x, member->z,
                                                  chase_x, chase_z);
                if (distance < closest_distance) {
                    closest_distance = distance;
                    closest = player;
                }
            }
        }

        if (closest >= 0 && closest_distance > 2.0f * 2.0f) {
            GamePlayer *chaser = &game->players[team][closest];
            float dx = chase_x - chaser->x;
            float dz = chase_z - chaser->z;
            float length = sqrtf(dx * dx + dz * dz);
            if (length > 0.001f) {
                float step = AI_SPEED * delta_time;
                if (step > length - 1.6f) step = length - 1.6f;
                if (step < 0.0f) step = 0.0f;
                chaser->facing_x = dx / length;
                chaser->facing_z = dz / length;
                chaser->x = clampf(chaser->x + chaser->facing_x * step,
                                   1.0f, GAME_PITCH_LENGTH - 1.0f);
                chaser->z = clampf(chaser->z + chaser->facing_z * step,
                                   1.0f, GAME_PITCH_WIDTH - 1.0f);
                chaser->movement = clampf(step / (AI_SPEED * delta_time),
                                          0.0f, 1.0f);
            }
        }
    }

    if (game->ball_team == 0 && game->ball_player >= 0) {
        const GamePlayer *carrier =
            &game->players[0][game->ball_player];
        float nearest_distance = 1000000.0f;
        for (player = 0; player < GAME_TEAM_SIZE; player++) {
            float distance = distance_squared(
                game->players[1][player].x, game->players[1][player].z,
                carrier->x, carrier->z);
            if (distance < nearest_distance) nearest_distance = distance;
        }
        if (nearest_distance <= CPU_TACKLE_RANGE * CPU_TACKLE_RANGE) {
            game->cpu_tackle_time += delta_time;
            if (game->cpu_tackle_time >= CPU_TACKLE_COMMIT_TIME) {
                int tackler = 0;
                nearest_distance = 1000000.0f;
                for (player = 0; player < GAME_TEAM_SIZE; player++) {
                    float distance = distance_squared(
                        game->players[1][player].x,
                        game->players[1][player].z, carrier->x, carrier->z);
                    if (distance < nearest_distance) {
                        nearest_distance = distance;
                        tackler = player;
                    }
                }
                game->ball_team = 1;
                game->ball_player = tackler;
                game->steps_carried = 0;
                game->step_time = 0.0f;
                game->last_was_bounce = 0;
                game->last_touch_team = 1;
                game->cpu_possession_time = 0.0f;
                game->cpu_tackle_time = 0.0f;
                game->ball.velocity_x = 0.0f;
                game->ball.velocity_z = 0.0f;
                game->ball.velocity_y = 0.0f;
                game->ball.curve = 0.0f;
                set_event(game, GAME_EVENT_TACKLE);
            }
        } else {
            game->cpu_tackle_time = 0.0f;
        }
    } else {
        game->cpu_tackle_time = 0.0f;
    }

    if (game->ball_team == 1 && game->ball_player >= 0) {
        static const int support_players[3] = {7, 8, 12};
        int support;
        const GamePlayer *carrier =
            &game->players[1][game->ball_player];
        for (support = 0; support < 3; support++) {
            int index = support_players[support];
            GamePlayer *member = &game->players[1][index];
            float target_x;
            float target_z;
            float dx;
            float dz;
            float length;
            float step;
            if (index == game->ball_player) continue;
            target_x = clampf(carrier->x - 9.0f - (float)support * 6.0f,
                              1.0f, GAME_PITCH_LENGTH - 1.0f);
            target_z = GAME_PITCH_WIDTH * 0.5f +
                (support == 0 ? -13.0f : support == 1 ? 13.0f : 0.0f);
            dx = target_x - member->x;
            dz = target_z - member->z;
            length = sqrtf(dx * dx + dz * dz);
            if (length <= 1.5f) continue;
            step = fminf(2.8f * delta_time, length - 1.5f);
            member->facing_x = dx / length;
            member->facing_z = dz / length;
            member->x = clampf(member->x + member->facing_x * step,
                               1.0f, GAME_PITCH_LENGTH - 1.0f);
            member->z = clampf(member->z + member->facing_z * step,
                               1.0f, GAME_PITCH_WIDTH - 1.0f);
            member->movement = clampf(step / (2.8f * delta_time), 0.0f, 1.0f);
        }
    }
}

static float nearest_defender_distance(const GameState *game, int team,
                                       float x, float z)
{
    int player;
    float nearest = 1000000.0f;
    for (player = 0; player < GAME_TEAM_SIZE; player++) {
        const GamePlayer *member = &game->players[1 - team][player];
        float distance = distance_squared(member->x, member->z, x, z);
        if (distance < nearest) nearest = distance;
    }
    return sqrtf(nearest);
}

static void cpu_release_toward(GameState *game, int player_index,
                               float target_x, float target_z, float speed,
                               float lift, GameEvent event)
{
    GamePlayer *player = &game->players[1][player_index];
    float dx = target_x - player->x;
    float dz = target_z - player->z;
    float length = sqrtf(dx * dx + dz * dz);
    if (length < 0.001f) return;
    player->facing_x = dx / length;
    player->facing_z = dz / length;
    game->ball_team = -1;
    game->ball_player = -1;
    game->ball.x = player->x + player->facing_x * 0.9f;
    game->ball.z = player->z + player->facing_z * 0.9f;
    game->ball.height = 1.1f;
    game->ball.velocity_x = player->facing_x * speed;
    game->ball.velocity_z = player->facing_z * speed;
    game->ball.velocity_y = lift;
    game->ball.curve = 0.0f;
    game->ball.in_flight = 1;
    game->pickup_delay = 0.15f;
    game->last_release_team = 1;
    game->last_release_player = player_index;
    game->last_touch_team = 1;
    game->restart_pending = 0;
    game->kickout_in_progress = 0;
    game->kickout_team = -1;
    game->cpu_possession_time = 0.0f;
    set_event(game, event);
}

static void update_cpu_carrier(GameState *game, float delta_time)
{
    GamePlayer *carrier = &game->players[1][game->ball_player];
    int player;
    int receiver = -1;
    float best_receiver_score = -1000000.0f;
    float goal_distance = carrier->x;
    float goal_offset = fabsf(carrier->z - GAME_PITCH_WIDTH * 0.5f);
    float pressure = nearest_defender_distance(game, 1,
                                               carrier->x, carrier->z);

    if (goal_distance <= 38.0f && goal_offset <= 20.0f) {
        float target_x = 0.0f;
        float target_z = GAME_PITCH_WIDTH * 0.5f;
        float dx = target_x - carrier->x;
        float dz = target_z - carrier->z;
        float length = sqrtf(dx * dx + dz * dz);
        float speed = goal_distance <= 25.0f ? 25.0f : 31.0f;
        if (length > 0.001f) {
            float flight_time = fmaxf(length - 0.9f, 0.5f) / speed;
            float crossing_height = goal_distance <= 25.0f ? 1.8f : 3.5f;
            float lift = (crossing_height - 1.05f +
                          0.5f * GAME_BALL_GRAVITY * flight_time *
                              flight_time) / flight_time;
            cpu_release_toward(game, game->ball_player, target_x, target_z,
                               speed, lift, GAME_EVENT_KICKED);
            return;
        }
    }

    for (player = 0; player < GAME_TEAM_SIZE; player++) {
        GamePlayer *teammate = &game->players[1][player];
        float forward = carrier->x - teammate->x;
        float distance = sqrtf(distance_squared(carrier->x, carrier->z,
                                                teammate->x, teammate->z));
        float space;
        float score;
        if (player == game->ball_player || forward < 3.0f ||
            forward > 38.0f || distance < 5.0f || distance > 42.0f)
            continue;
        space = nearest_defender_distance(game, 1, teammate->x, teammate->z);
        score = forward * 0.7f + space * 0.6f - distance * 0.15f;
        if (score > best_receiver_score) {
            best_receiver_score = score;
            receiver = player;
        }
    }

    if (receiver >= 0 && (pressure < 7.0f ||
                          game->cpu_possession_time > 2.2f)) {
        GamePlayer *target = &game->players[1][receiver];
        float distance = sqrtf(distance_squared(carrier->x, carrier->z,
                                                target->x, target->z));
        cpu_release_toward(game, game->ball_player, target->x, target->z,
                           distance <= 14.0f ? 12.0f : 22.0f,
                           distance <= 14.0f ? 2.4f : 5.2f,
                           distance <= 14.0f ? GAME_EVENT_HANDPASSED :
                                               GAME_EVENT_KICKED);
        return;
    }

    {
        float target_z = GAME_PITCH_WIDTH * 0.5f +
                         (carrier->z - GAME_PITCH_WIDTH * 0.5f) * 0.35f;
        float dx = -carrier->x;
        float dz = target_z - carrier->z;
        float length = sqrtf(dx * dx + dz * dz);
        if (length > 0.001f) {
            float step = 4.2f * delta_time;
            if (step > length) step = length;
            carrier->facing_x = dx / length;
            carrier->facing_z = dz / length;
            carrier->x = clampf(carrier->x + carrier->facing_x * step,
                                1.0f, GAME_PITCH_LENGTH - 1.0f);
            carrier->z = clampf(carrier->z + carrier->facing_z * step,
                                1.0f, GAME_PITCH_WIDTH - 1.0f);
            carrier->movement = step > 0.0f ? 1.0f : 0.0f;
        }
    }
}

static void update_ball(GameState *game, float delta_time, int pickup_input)
{
    float previous_x = game->ball.x;
    float previous_z = game->ball.z;
    float previous_height = game->ball.height;
    float previous_velocity_x = game->ball.velocity_x;
    float previous_velocity_z = game->ball.velocity_z;
    float previous_velocity_y = game->ball.velocity_y;
    int was_in_flight = game->ball.in_flight;

    if (game->pickup_team >= 0 && game->pickup_player >= 0) {
        GamePlayer *picker =
            &game->players[game->pickup_team][game->pickup_player];
        float progress;
        game->pickup_time -= delta_time;
        if (game->pickup_time < 0.0f) game->pickup_time = 0.0f;
        progress = 1.0f - game->pickup_time / PICKUP_ANIMATION_TIME;
        game->ball.x = picker->x + picker->facing_x * 0.45f;
        game->ball.z = picker->z + picker->facing_z * 0.45f;
        game->ball.height = 0.18f + 0.87f * progress;
        if (game->pickup_time == 0.0f) {
            int team = game->pickup_team;
            int player = game->pickup_player;
            game->ball_team = team;
            game->ball_player = player;
            game->ball.x = game->players[team][player].x;
            game->ball.z = game->players[team][player].z;
            game->ball.height = 1.05f;
            game->ball.velocity_x = 0.0f;
            game->ball.velocity_z = 0.0f;
            game->ball.velocity_y = 0.0f;
            game->ball.curve = 0.0f;
            game->last_touch_team = team;
            game->steps_carried = 0;
            game->step_time = 0.0f;
            game->last_was_bounce = 0;
            game->last_release_team = -1;
            game->last_release_player = -1;
            game->pickup_team = -1;
            game->pickup_player = -1;
            set_event(game, GAME_EVENT_PICKUP);
        }
        return;
    }

    if (game->ball_team >= 0 && game->ball_player >= 0) {
        GamePlayer *carrier = &game->players[game->ball_team][game->ball_player];
        game->ball.x = carrier->x;
        game->ball.z = carrier->z;
        game->ball.height = 1.05f;
        return;
    }

    if (was_in_flight && fabsf(game->ball.curve) > 0.001f) {
        float horizontal_speed = sqrtf(
            game->ball.velocity_x * game->ball.velocity_x +
            game->ball.velocity_z * game->ball.velocity_z);
        if (horizontal_speed > 0.001f) {
            float curve_acceleration = game->ball.curve * 6.0f;
            game->ball.velocity_x +=
                -previous_velocity_z / horizontal_speed *
                curve_acceleration * delta_time;
            game->ball.velocity_z +=
                previous_velocity_x / horizontal_speed *
                curve_acceleration * delta_time;
            game->ball.curve *= fmaxf(0.0f, 1.0f - 0.35f * delta_time);
        }
    }
    game->ball.x += (previous_velocity_x + game->ball.velocity_x) *
                    0.5f * delta_time;
    game->ball.z += (previous_velocity_z + game->ball.velocity_z) *
                    0.5f * delta_time;

    if (was_in_flight) {
        float next_height = game->ball.height +
                            game->ball.velocity_y * delta_time -
                            0.5f * GAME_BALL_GRAVITY * delta_time * delta_time;
        if (next_height <= 0.18f) {
            float discriminant = game->ball.velocity_y *
                game->ball.velocity_y +
                2.0f * GAME_BALL_GRAVITY *
                fmaxf(game->ball.height - 0.18f, 0.0f);
            float landing_time = (game->ball.velocity_y +
                                  sqrtf(discriminant)) /
                                 GAME_BALL_GRAVITY;
            float roll_time;
            if (landing_time < 0.0f) landing_time = 0.0f;
            if (landing_time > delta_time) landing_time = delta_time;
            roll_time = delta_time - landing_time;
            {
                float drag = fmaxf(0.0f, 1.0f - 1.8f * roll_time);
                float rolling_time = roll_time * (1.0f + drag) * 0.5f;
                float acceleration_x = (game->ball.velocity_x -
                    previous_velocity_x) / delta_time;
                float acceleration_z = (game->ball.velocity_z -
                    previous_velocity_z) / delta_time;
                game->ball.x = previous_x +
                    previous_velocity_x * landing_time +
                    0.5f * acceleration_x * landing_time * landing_time +
                    game->ball.velocity_x * rolling_time;
                game->ball.z = previous_z +
                    previous_velocity_z * landing_time +
                    0.5f * acceleration_z * landing_time * landing_time +
                    game->ball.velocity_z * rolling_time;
                game->ball.velocity_x *= drag;
                game->ball.velocity_z *= drag;
            }
            game->ball.height = 0.18f;
            game->ball.velocity_y = 0.0f;
            game->ball.in_flight = 0;
            game->ball.curve = 0.0f;
        } else {
            game->ball.height = next_height;
            game->ball.velocity_y -= GAME_BALL_GRAVITY * delta_time;
        }
    } else {
        float drag = 1.0f - 1.8f * delta_time;
        if (drag < 0.0f) drag = 0.0f;
        game->ball.velocity_x *= drag;
        game->ball.velocity_z *= drag;
    }

    if ((previous_x < GAME_PITCH_LENGTH && game->ball.x >= GAME_PITCH_LENGTH) ||
        (previous_x > 0.0f && game->ball.x <= 0.0f)) {
        float goal_x = game->ball.x > previous_x ? GAME_PITCH_LENGTH : 0.0f;
        float fraction = (goal_x - previous_x) / (game->ball.x - previous_x);
        float crossing_z = previous_z + (game->ball.z - previous_z) * fraction;
        float crossing_time = delta_time * fraction;
        float crossing_height = was_in_flight ?
            previous_height + previous_velocity_y * crossing_time -
            0.5f * GAME_BALL_GRAVITY * crossing_time * crossing_time :
            previous_height +
            (game->ball.height - previous_height) * fraction;
        float goal_center = GAME_PITCH_WIDTH * 0.5f;
        int scoring_team = goal_x > GAME_PITCH_LENGTH * 0.5f ? 0 : 1;

        if (fraction >= 0.0f && fraction <= 1.0f &&
            fabsf(crossing_z - goal_center) <= GAME_GOAL_WIDTH * 0.5f &&
            crossing_height <= 8.0f) {
            if (crossing_height <= GAME_CROSSBAR_HEIGHT) {
                game->team_goals[scoring_team]++;
                set_event(game, GAME_EVENT_GOAL);
            } else {
                game->team_points[scoring_team]++;
                set_event(game, GAME_EVENT_POINT);
            }
            game->goals = game->team_goals[0];
            game->points = game->team_points[0];
            reset_positions(game);
            reset_ball(game, 1 - scoring_team, 7);
            if (1 - scoring_team == 0) game->selected_player = 7;
            sync_selected_player(game);
            return;
        }
    }

    if (game->ball.x < 0.0f || game->ball.x > GAME_PITCH_LENGTH ||
        game->ball.z < 0.0f || game->ball.z > GAME_PITCH_WIDTH) {
        float x_fraction = 2.0f;
        float z_fraction = 2.0f;
        float restart_x = game->ball.x;
        float restart_z = game->ball.z;
        int restart_team;

        if (game->ball.x < 0.0f || game->ball.x > GAME_PITCH_LENGTH) {
            float endline = game->ball.x < 0.0f ? 0.0f : GAME_PITCH_LENGTH;
            x_fraction = (endline - previous_x) /
                         (game->ball.x - previous_x);
        }
        if (game->ball.z < 0.0f || game->ball.z > GAME_PITCH_WIDTH) {
            float sideline = game->ball.z < 0.0f ? 0.0f : GAME_PITCH_WIDTH;
            z_fraction = (sideline - previous_z) /
                         (game->ball.z - previous_z);
        }

        if (z_fraction <= x_fraction) {
            restart_x = previous_x + (game->ball.x - previous_x) *
                        z_fraction;
            restart_z = game->ball.z < 0.0f ? 0.0f : GAME_PITCH_WIDTH;
            restart_team = 1 - game->last_touch_team;
        } else {
            restart_x = game->ball.x < 0.0f ? 0.0f : GAME_PITCH_LENGTH;
            restart_z = previous_z + (game->ball.z - previous_z) *
                        x_fraction;
            restart_team = restart_x < GAME_PITCH_LENGTH * 0.5f ? 0 : 1;
        }

        start_kick_in(game, restart_team, restart_x, restart_z);
        set_event(game, GAME_EVENT_BALL_OUT);
        return;
    }

    if (was_in_flight && game->pickup_delay <= 0.0f &&
        (previous_height > 1.0f || game->ball.height > 1.0f)) {
        int team;
        int player;
        int catcher_team = -1;
        int catcher_player = -1;
        float closest = HIGH_FIELD_RADIUS * HIGH_FIELD_RADIUS;
        for (team = 0; team < 2; team++) {
            for (player = 0; player < GAME_TEAM_SIZE; player++) {
                GamePlayer *member = &game->players[team][player];
                float fraction;
                float ball_x;
                float ball_z;
                float ball_height;
                float crossing_time;
                float distance;
                if (member->jump_time <= 0.0f) continue;
                fraction = segment_closest_fraction(previous_x, previous_z,
                    game->ball.x, game->ball.z, member->x, member->z);
                ball_x = previous_x + (game->ball.x - previous_x) * fraction;
                ball_z = previous_z + (game->ball.z - previous_z) * fraction;
                crossing_time = delta_time * fraction;
                ball_height = was_in_flight ?
                    previous_height + previous_velocity_y * crossing_time -
                    0.5f * GAME_BALL_GRAVITY * crossing_time *
                        crossing_time :
                    previous_height +
                    (game->ball.height - previous_height) * fraction;
                distance = distance_squared(member->x, member->z,
                                            ball_x, ball_z);
                if (distance <= closest && ball_height >= 1.0f &&
                    ball_height <= HIGH_FIELD_REACH) {
                    closest = distance;
                    catcher_team = team;
                    catcher_player = player;
                }
            }
        }
        if (catcher_team >= 0) {
            game->ball_team = catcher_team;
            game->ball_player = catcher_player;
            game->ball.x = game->players[catcher_team][catcher_player].x;
            game->ball.z = game->players[catcher_team][catcher_player].z;
            game->ball.height = 1.05f;
            game->ball.velocity_x = 0.0f;
            game->ball.velocity_z = 0.0f;
            game->ball.velocity_y = 0.0f;
            game->ball.in_flight = 0;
            game->ball.curve = 0.0f;
            game->players[catcher_team][catcher_player].jump_time = 0.0f;
            game->last_touch_team = catcher_team;
            game->steps_carried = 0;
            game->last_was_bounce = 0;
            game->step_time = 0.0f;
            game->kickout_in_progress = 0;
            game->kickout_team = -1;
            if (catcher_team == 0)
                game_select_player(game, catcher_player);
            set_event(game, GAME_EVENT_HIGH_FIELD);
            return;
        }
    }

    if (game->kickout_in_progress) {
        float direction = game->kickout_team == 0 ? 1.0f : -1.0f;
        float arc_x = kickout_line_x(game->kickout_team) +
                      direction * GAME_KICKOUT_ARC_RADIUS;
        if ((direction > 0.0f && game->ball.x >= arc_x) ||
            (direction < 0.0f && game->ball.x <= arc_x)) {
            game->kickout_in_progress = 0;
            game->kickout_team = -1;
        } else if (!game->ball.in_flight && game->ball.height <= 0.18f) {
            int team = 1 - game->kickout_team;
            int player;
            int nearest = 0;
            float nearest_distance = 1000000.0f;
            for (player = 0; player < GAME_TEAM_SIZE; player++) {
                GamePlayer *member = &game->players[team][player];
                float distance = distance_squared(member->x, member->z,
                                                  game->ball.x, game->ball.z);
                if (distance < nearest_distance) {
                    nearest_distance = distance;
                    nearest = player;
                }
            }
            game->ball_team = team;
            game->ball_player = nearest;
            game->ball.velocity_x = 0.0f;
            game->ball.velocity_z = 0.0f;
            game->ball.velocity_y = 0.0f;
            game->last_touch_team = team;
            game->kickout_in_progress = 0;
            game->kickout_team = -1;
            set_event(game, GAME_EVENT_SHORT_KICKOUT);
            return;
        }
    }

    if (game->pickup_delay > 0.0f) {
        game->pickup_delay -= delta_time;
        if (game->pickup_delay < 0.0f) game->pickup_delay = 0.0f;
    }

    if (!game->kickout_in_progress && game->pickup_delay == 0.0f &&
        !game->ball.in_flight && game->ball.height <= 0.3f) {
        int team;
        int player;
        int nearest_team = -1;
        int nearest_player = -1;
        float nearest_distance = FOOT_PICKUP_RADIUS * FOOT_PICKUP_RADIUS;

        for (team = 0; team < 2; team++) {
            for (player = 0; player < GAME_TEAM_SIZE; player++) {
                GamePlayer *member = &game->players[team][player];
                float fraction = was_in_flight ? 1.0f :
                    segment_closest_fraction(previous_x, previous_z,
                        game->ball.x, game->ball.z, member->x, member->z);
                float contact_x = previous_x +
                    (game->ball.x - previous_x) * fraction;
                float contact_z = previous_z +
                    (game->ball.z - previous_z) * fraction;
                float distance;
                if (team == 0 && player == game->selected_player &&
                    !pickup_input)
                    continue;
                distance = distance_squared(member->x, member->z,
                                            contact_x, contact_z);
                if (team == game->last_release_team &&
                    player == game->last_release_player &&
                    distance <= KICKER_PICKUP_GUARD *
                                KICKER_PICKUP_GUARD)
                    continue;
                if (distance <= nearest_distance) {
                    nearest_distance = distance;
                    nearest_team = team;
                    nearest_player = player;
                }
            }
        }

        if (nearest_team >= 0) {
            GamePlayer *picker =
                &game->players[nearest_team][nearest_player];
            float fraction = was_in_flight ? 1.0f :
                segment_closest_fraction(previous_x, previous_z,
                    game->ball.x, game->ball.z, picker->x, picker->z);
            float contact_x = previous_x +
                (game->ball.x - previous_x) * fraction;
            float contact_z = previous_z +
                (game->ball.z - previous_z) * fraction;
            float distance = sqrtf(distance_squared(picker->x, picker->z,
                                                    contact_x, contact_z));
            if (distance > 0.001f) {
                picker->facing_x = (contact_x - picker->x) / distance;
                picker->facing_z = (contact_z - picker->z) / distance;
            }
            game->ball.x = contact_x;
            game->ball.z = contact_z;
            game->pickup_team = nearest_team;
            game->pickup_player = nearest_player;
            game->pickup_time = PICKUP_ANIMATION_TIME;
            game->ball.x = picker->x + picker->facing_x * 0.45f;
            game->ball.z = picker->z + picker->facing_z * 0.45f;
            game->ball.height = 0.18f;
            game->ball.in_flight = 0;
            game->ball.velocity_x = 0.0f;
            game->ball.velocity_z = 0.0f;
            game->ball.velocity_y = 0.0f;
            game->ball.curve = 0.0f;
            if (nearest_team == 0)
                game_select_player(game, nearest_player);
        }
    }
}

void game_update(GameState *game, GameInput input, float delta_time)
{
    GamePlayer *controlled;
    float move_length;

    if (delta_time <= 0.0f) return;
    if (delta_time > 0.1f) delta_time = 0.1f;

    sync_selected_player(game);
    controlled = &game->players[0][game->selected_player];
    if (input.high_field && !game->has_ball)
        controlled->jump_time = 0.75f;
    move_length = sqrtf(input.move_x * input.move_x + input.move_z * input.move_z);
    if (move_length > 1.0f) {
        input.move_x /= move_length;
        input.move_z /= move_length;
        move_length = 1.0f;
    }
    if (game->pickup_team == 0 &&
        game->pickup_player == game->selected_player)
        move_length = 0.0f;

    if (move_length > 0.01f) {
        controlled->movement = move_length;
        controlled->facing_x = input.move_x / move_length;
        controlled->facing_z = input.move_z / move_length;
        controlled->x = clampf(controlled->x + controlled->facing_x *
                               PLAYER_SPEED * delta_time,
                               1.0f, GAME_PITCH_LENGTH - 1.0f);
        controlled->z = clampf(controlled->z + controlled->facing_z *
                               PLAYER_SPEED * delta_time,
                               1.0f, GAME_PITCH_WIDTH - 1.0f);

        if (game->has_ball) {
            game->step_time += delta_time;
            while (game->step_time >= 0.7f) {
                game->step_time -= 0.7f;
                game->steps_carried++;
                if (game->steps_carried > 4) {
                    game->ball_team = -1;
                    game->ball_player = -1;
                    game->ball.x = controlled->x;
                    game->ball.z = controlled->z;
                    game->ball.height = 0.25f;
                    game->ball.velocity_x = 0.0f;
                    game->ball.velocity_z = 0.0f;
                    game->ball.velocity_y = 0.0f;
                    game->ball.in_flight = 0;
                    game->pickup_delay = 0.75f;
                    game->fouls++;
                    set_event(game, GAME_EVENT_FOUR_STEPS);
                    break;
                }
            }
        }
    } else {
        controlled->movement *= 0.2f;
    }

    sync_selected_player(game);

    if (game->restart_pending) {
        float arc_x = kickout_line_x(game->ball_team);
        clear_kickout_arc(game, game->ball_team, game->ball_player, arc_x,
                          GAME_PITCH_WIDTH * 0.5f);
    }

    if (game->restart_pending && game->ball_team == 1) {
        cpu_kick_in(game);
    }

    if (game->restart_pending) {
        input.handpass = 0;
        input.solo = 0;
        input.bounce = 0;
    }

    if (game->has_ball) {
        if (input.kick) {
            release_ball(game, 30.0f, 3.0f, input.curve);
            set_event(game, GAME_EVENT_KICKED);
        } else if (input.kick_high) {
            release_ball(game, 20.0f, 9.0f, input.curve);
            set_event(game, GAME_EVENT_KICKED);
        } else if (input.kick_low) {
            release_ball(game, 34.0f, -1.0f, input.curve);
            set_event(game, GAME_EVENT_KICKED);
        } else if (input.kick_long) {
            release_ball(game, 38.0f, 7.0f, input.curve);
            set_event(game, GAME_EVENT_KICKED);
        } else if (input.handpass) {
            release_ball(game, 13.0f, 2.0f, 0.0f);
            set_event(game, GAME_EVENT_HANDPASSED);
        } else if (input.solo) {
            release_ball(game, 4.0f, 0.0f, 0.0f);
            game->ball_team = 0;
            game->ball_player = game->selected_player;
            game->ball.x = controlled->x;
            game->ball.z = controlled->z;
            game->ball.height = 1.05f;
            game->ball.velocity_x = 0.0f;
            game->ball.velocity_z = 0.0f;
            game->ball.velocity_y = 0.0f;
            game->ball.curve = 0.0f;
            game->ball.in_flight = 0;
            game->pickup_delay = 0.0f;
            game->last_release_team = -1;
            game->last_release_player = -1;
            game->last_was_bounce = 0;
            set_event(game, GAME_EVENT_SOLOED);
        } else if (input.bounce) {
            if (game->last_was_bounce) {
                game->fouls++;
                set_event(game, GAME_EVENT_ILLEGAL_BOUNCE);
            } else {
                release_ball(game, 2.5f, 0.0f, 0.0f);
                game->ball_team = 0;
                game->ball_player = game->selected_player;
                game->ball.x = controlled->x;
                game->ball.z = controlled->z;
                game->ball.height = 1.05f;
                game->ball.velocity_x = 0.0f;
                game->ball.velocity_z = 0.0f;
                game->ball.velocity_y = 0.0f;
                game->ball.curve = 0.0f;
                game->ball.in_flight = 0;
                game->pickup_delay = 0.0f;
                game->last_release_team = -1;
                game->last_release_player = -1;
                game->last_was_bounce = 1;
                set_event(game, GAME_EVENT_BOUNCED);
            }
        }
    } else if (input.tackle && game->ball_team == 1 &&
               distance_squared(controlled->x, controlled->z,
                                 game->ball.x, game->ball.z) <= 2.5f * 2.5f) {
        game->ball_team = 0;
        game->ball_player = game->selected_player;
        game->steps_carried = 0;
        game->last_was_bounce = 0;
        game->ball.velocity_x = 0.0f;
        game->ball.velocity_z = 0.0f;
        game->ball.velocity_y = 0.0f;
        game->last_touch_team = 0;
        game->restart_pending = 0;
        set_event(game, GAME_EVENT_TACKLE);
    }

    update_cpu_players(game, delta_time);
    if (game->kickout_in_progress) {
        clear_kickout_arc(game, -1, -1,
                          kickout_line_x(game->kickout_team),
                          GAME_PITCH_WIDTH * 0.5f);
    }

    if (game->ball_team == 1 && game->ball_player >= 0) {
        game->cpu_possession_time += delta_time;
        update_cpu_carrier(game, delta_time);
    } else {
        game->cpu_possession_time = 0.0f;
    }

    update_ball(game, delta_time, input.pickup);
    sync_selected_player(game);

    if (game->event_time > 0.0f) {
        game->event_time -= delta_time;
        if (game->event_time <= 0.0f) game->event = GAME_EVENT_NONE;
    }
}

const char *game_team_name(int team_index)
{
    if (team_index < 0 || team_index >= GAME_TEAM_COUNT) return "Unknown";
    return TEAM_NAMES[team_index];
}

const char *game_player_role(int player_index)
{
    if (player_index == 0) return "Goalkeeper";
    if (player_index <= 3) return "Full back";
    if (player_index <= 6) return "Half back";
    if (player_index <= 8) return "Midfielder";
    if (player_index <= 11) return "Half forward";
    return "Full forward";
}

const char *game_event_text(GameEvent event)
{
    switch (event) {
        case GAME_EVENT_KICKED: return "Kick";
        case GAME_EVENT_HANDPASSED: return "Hand pass";
        case GAME_EVENT_SOLOED: return "Solo";
        case GAME_EVENT_BOUNCED: return "Bounce";
        case GAME_EVENT_ILLEGAL_BOUNCE: return "Foul: no consecutive bounces";
        case GAME_EVENT_FOUR_STEPS: return "Foul: four steps";
        case GAME_EVENT_POINT: return "Point!";
        case GAME_EVENT_GOAL: return "Goal!";
        case GAME_EVENT_BALL_OUT: return "Ball out - restart";
        case GAME_EVENT_TACKLE: return "Clean tackle!";
        case GAME_EVENT_SHORT_KICKOUT: return "Short kick-out - turnover";
        case GAME_EVENT_HIGH_FIELD: return "Great high field!";
        case GAME_EVENT_PICKUP: return "Foot lift!";
        default: return "";
    }
}

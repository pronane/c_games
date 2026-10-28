#include "game.h"

#include <math.h>
#include <string.h>
#include <stddef.h>

#define PLAYER_SPEED 7.0f      /* run with/without ball (m/s) */
#define SPRINT_SPEED 9.0f      /* v3: inter-county sprint ~9 m/s */
#define AI_SPEED 8.2f
#define AI_JOG_SPEED 5.8f
#define CPU_CARRY_SPEED 7.6f
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
        2.0f * GAME_BALL_GRAVITY * fmaxf(game->ball.height - GAME_BALL_REST, 0.0f);
    float time = (game->ball.velocity_y + sqrtf(discriminant)) /
                 GAME_BALL_GRAVITY;
    if (time < 0.0f) time = 0.0f;
    if (time > 3.0f) time = 3.0f;
    *landing_x = clampf(game->ball.x + game->ball.velocity_x * time,
                        1.0f, GAME_PITCH_LENGTH - 1.0f);
    *landing_z = clampf(game->ball.z + game->ball.velocity_z * time,
                        1.0f, GAME_PITCH_WIDTH - 1.0f);
}

static float nearest_defender_distance(const GameState *game, int team,
                                       float x, float z);

static void set_event(GameState *game, GameEvent event)
{
    GameOfficial *ref = &game->referee;
    game->event = event;
    game->event_time = 2.0f;
    switch (event) {
    case GAME_EVENT_FREE: case GAME_EVENT_FOUL_TACKLE: case GAME_EVENT_FOUR_STEPS:
    case GAME_EVENT_ILLEGAL_BOUNCE: case GAME_EVENT_KICKOUT_SHORT:
    case GAME_EVENT_KICKOUT_TOUCHED: case GAME_EVENT_THREE_V_THREE:
    case GAME_EVENT_PENALTY:
        ref->signal = GAME_SIGNAL_FREE; break;
    case GAME_EVENT_POINT: ref->signal = GAME_SIGNAL_POINT; break;
    case GAME_EVENT_TWO_POINT: ref->signal = GAME_SIGNAL_TWO_POINT; break;
    case GAME_EVENT_GOAL: ref->signal = GAME_SIGNAL_GOAL; break;
    case GAME_EVENT_WIDE: ref->signal = GAME_SIGNAL_WIDE; break;
    case GAME_EVENT_THROW_IN: ref->signal = GAME_SIGNAL_THROW; break;
    case GAME_EVENT_BACK_PASS: case GAME_EVENT_DISSENT:
        ref->signal = GAME_SIGNAL_FREE; break;
    case GAME_EVENT_YELLOW_CARD: case GAME_EVENT_BLACK_CARD: case GAME_EVENT_RED_CARD:
    case GAME_EVENT_SECOND_YELLOW: case GAME_EVENT_BLACK_PENALTY:
        game->event_time = 3.0f;
        ref->signal = GAME_SIGNAL_CARD;
        ref->signal_time = game->card_time > 0.0f ? game->card_time : 2.5f;
        ref->signal_dir = game->event_team == 0 ? 1.0f : -1.0f;
        return;
    case GAME_EVENT_ADVANCED_MARK: case GAME_EVENT_KICKOUT_MARK:
        ref->signal = GAME_SIGNAL_MARK; break;
    default: return;
    }
    ref->signal_time = event == GAME_EVENT_THROW_IN ? 0.8f : 1.6f;
    ref->signal_dir = game->event_team == 0 ? 1.0f : -1.0f;
}

void game_select_player(GameState *game, int player_index);

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
            if (game->players[team][player].off) continue;
            GamePlayer *member = &game->players[team][player];
            member->x = team == 0 ? FORMATION_X[player] :
                                    GAME_PITCH_LENGTH - FORMATION_X[player];
            member->z = FORMATION_Z[player];
            member->facing_x = team == 0 ? 1.0f : -1.0f;
            member->facing_z = 0.0f;
            member->movement = 0.0f;
            member->jump_time = 0.0f;
            member->action = GAME_ACT_NONE;
            member->action_time = 0.0f;
            member->action_released = 1;
            member->tackle_cooldown = 0.0f;
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
    game->restart_type = GAME_RESTART_NONE;
    game->restart_time = 0.0f;
    game->prev_ball_team = team;
    game->prev_ball_player = player;
    game->penalty_active = 0;
    game->kick_clean = 0;
    game->kick_no_two = 0;
    game->protect_time = 0.0f;
}

void game_init(GameState *game)
{
    memset(game, 0, sizeof *game);
    game->sin_bin_seconds = 600.0f;
    game->card_team = game->card_player = -1;
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
    game->team_two_pointers[0] = game->team_two_pointers[1] = 0;
    game->keeper_guess = 1;
    game->half = 1;
    game->event_team = 0;
    game->rng = 12345u;
    game->three_v_three_time = 0.0f;
    game->enforce_three_v_three = 0;
    game->ai_support = 0;
    game->assist_target = -1;
    game->referee.x = GAME_PITCH_LENGTH * 0.5f;
    game->referee.z = GAME_PITCH_WIDTH * 0.5f + 12.0f;
    game->referee.facing_x = 0.0f;
    game->referee.facing_z = -1.0f;
    game->referee.movement = 0.0f;
    game->referee.signal = GAME_SIGNAL_NONE;
    game->referee.signal_time = 0.0f;
    game->referee.signal_dir = 1.0f;
    game->on_release = NULL;
    game->user = NULL;
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
    if (game->players[0][player_index].off) return;
    game->selected_player = player_index;
    sync_selected_player(game);
}

void game_select_next_player(GameState *game, int direction)
{
    int next = game->selected_player, tries;
    for (tries = 0; tries < GAME_TEAM_SIZE; tries++) {
        next += direction < 0 ? -1 : 1;
        if (next < 0) next = GAME_TEAM_SIZE - 1;
        if (next >= GAME_TEAM_SIZE) next = 0;
        if (!game->players[0][next].off) break;
    }
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
        if (game->players[0][player].off) continue;
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

/* ------------------------------------------------------------------------
 * Timed actions (ball released on the animation's contact frame)
 * ---------------------------------------------------------------------- */
static float action_contact[GAME_ACT_COUNT];
static float action_duration[GAME_ACT_COUNT];
static const float DEFAULT_DURATION[GAME_ACT_COUNT] = {
    0.0f, 0.75f, 1.0f, 1.2f, 0.8f, 0.35f, 0.4f, 0.45f, 0.45f, 0.4f, 1.2f, 0.7f,
    0.9f, 0.8f, 0.9f, 1.3f
};

void game_set_action_timing(int action, float contact, float duration)
{
    if (action <= GAME_ACT_NONE || action >= GAME_ACT_COUNT) return;
    action_contact[action] = contact;
    action_duration[action] = duration;
}

float game_action_contact(int action)
{
    if (action <= GAME_ACT_NONE || action >= GAME_ACT_COUNT) return 0.0f;
    return action_contact[action];
}

float game_action_duration(int action)
{
    if (action <= GAME_ACT_NONE || action >= GAME_ACT_COUNT) return 0.0f;
    return action_duration[action] > 0.0f ? action_duration[action] :
                                            DEFAULT_DURATION[action];
}

int game_carrier_steps(const GameState *game) { return game->steps_carried; }

static float goal_x_of(int attacking_team)
{
    return attacking_team == 0 ? GAME_PITCH_LENGTH : 0.0f;
}

float game_distance_to_goal(int team, float x, float z)
{
    return sqrtf(distance_squared(x, z, goal_x_of(team), GAME_PITCH_WIDTH * 0.5f));
}

static float frand01(GameState *game)
{
    game->rng = game->rng * 1664525u + 1013904223u;
    return (float)((game->rng >> 8) & 0xFFFFu) / 65535.0f;
}

/* Is (x,z) inside the large rectangle in front of the goal `defending_team` defends? */
static int in_large_rectangle(int defending_team, float x, float z)
{
    float gx = goal_x_of(1 - defending_team);
    return fabsf(x - gx) <= GAME_LARGE_RECT_DEPTH &&
           fabsf(z - GAME_PITCH_WIDTH * 0.5f) <= GAME_LARGE_RECT_HALF;
}

static int is_kick_action(int action)
{
    return action == GAME_ACT_KICK || action == GAME_ACT_FREE_KICK ||
           action == GAME_ACT_KICKOUT || action == GAME_ACT_GROUND_KICK;
}

static void begin_action(GamePlayer *player, int action)
{
    player->action = action;
    player->action_time = 0.0f;
    player->action_released = 1;
}

static void perform_release(GameState *game, int team, int index)
{
    GamePlayer *player = &game->players[team][index];
    int is_restart = game->restart_pending;
    int restart_type = game->restart_type;
    int action = player->action;

    game->ball_team = -1;
    game->ball_player = -1;
    game->steps_carried = 0;
    game->step_time = 0.0f;
    game->ball.x = player->x + player->release_dx * 0.6f;
    game->ball.z = player->z + player->release_dz * 0.6f;
    game->ball.height = action == GAME_ACT_GROUND_KICK ? GAME_BALL_REST + 0.05f : 0.6f;
    /* sideline kicks are struck from outside the line: start the flight on the line */
    game->ball.z = clampf(game->ball.z, 0.05f, GAME_PITCH_WIDTH - 0.05f);
    game->ball.x = clampf(game->ball.x, 0.05f, GAME_PITCH_LENGTH - 0.05f);
    game->ball.velocity_x = player->release_dx * player->release_speed;
    game->ball.velocity_z = player->release_dz * player->release_speed;
    game->ball.velocity_y = player->release_lift;
    game->ball.curve = clampf(player->release_curve, -1.0f, 1.0f);
    game->ball.in_flight = 1;
    game->pickup_delay = 0.2f;
    game->last_release_team = team;
    game->last_release_player = index;
    game->last_touch_team = team;
    game->restart_pending = 0;
    game->restart_type = GAME_RESTART_NONE;
    game->kickout_in_progress = is_restart && (restart_type == GAME_RESTART_KICKOUT ||
                                               restart_type == GAME_RESTART_NONE);
    game->kickout_team = game->kickout_in_progress ? team : -1;
    game->kick_clean = is_kick_action(action) && action != GAME_ACT_KICKOUT;
    game->from_kickout = action == GAME_ACT_KICKOUT;
    game->kick_origin_x = player->x;
    game->kick_origin_z = player->z;
    game->kick_no_two = is_restart && restart_type == GAME_RESTART_FORTY_FIVE;
    game->penalty_active = is_restart && restart_type == GAME_RESTART_PENALTY;
    if (game->penalty_active) {
        GamePlayer *keeper = &game->players[1 - team][0];
        game->keeper_guess = frand01(game) < 0.5f ? -1 : 1;
        begin_action(keeper, GAME_ACT_DIVE);
    }
    if (team == 1) game->cpu_possession_time = 0.0f;
    player->action_released = 1;
    game->event_team = team;
    set_event(game, (GameEvent)player->release_event);
    if (game->on_release) game->on_release(game, team, index, action, game->user);
    sync_selected_player(game);
}

/* Start a kick/hand-pass action; the ball leaves on the contact frame. */
static void queue_release(GameState *game, int team, int index, float dir_x,
                          float dir_z, float speed, float lift, float curve,
                          GameEvent event, int action)
{
    GamePlayer *player = &game->players[team][index];
    float length = sqrtf(dir_x * dir_x + dir_z * dir_z);
    if (length < 0.001f) {
        dir_x = team == 0 ? 1.0f : -1.0f;
        dir_z = 0.0f;
    } else {
        dir_x /= length;
        dir_z /= length;
    }
    player->facing_x = dir_x;
    player->facing_z = dir_z;
    player->release_dx = dir_x;
    player->release_dz = dir_z;
    player->release_speed = speed;
    player->release_lift = lift;
    player->release_curve = curve;
    player->release_event = event;
    player->action = action;
    player->action_time = 0.0f;
    player->action_released = 0;
    if (game_action_contact(action) <= 0.0f) perform_release(game, team, index);
}

static void resolve_strike(GameState *game, int team, int index);

static void update_actions(GameState *game, float delta_time)
{
    int team, index;
    for (team = 0; team < 2; team++) {
        for (index = 0; index < GAME_TEAM_SIZE; index++) {
            if (game->players[team][index].off) continue;
            GamePlayer *player = &game->players[team][index];
            if (player->tackle_cooldown > 0.0f) player->tackle_cooldown -= delta_time;
            if (player->action == GAME_ACT_NONE) continue;
            player->action_time += delta_time;
            if ((player->action == GAME_ACT_HOOK || player->action == GAME_ACT_HEAD_HIT) &&
                !player->action_released) {
                float c = game_action_contact(player->action);
                if (player->action_time >= (c > 0.0f ? c : 0.35f)) {
                    player->action_released = 1;
                    resolve_strike(game, team, index);
                }
                continue;
            }
            if (!player->action_released &&
                player->action_time >= game_action_contact(player->action)) {
                if (game->ball_team == team && game->ball_player == index)
                    perform_release(game, team, index);
                else
                    player->action_released = 1;   /* lost the ball first */
            }
            if (player->action_time >= game_action_duration(player->action))
                player->action = GAME_ACT_NONE;
        }
    }
}

static int player_busy(const GamePlayer *player)
{
    return player->action != GAME_ACT_NONE && player->action != GAME_ACT_SOLO &&
           player->action != GAME_ACT_BOUNCE;
}

/* Lofted trajectory that crosses the goal line at `cross_height`. */
static float lift_for(float distance, float speed, float from_h, float cross_height)
{
    float t = fmaxf(distance, 1.0f) / fmaxf(speed, 1.0f);
    return (cross_height - from_h + 0.5f * GAME_BALL_GRAVITY * t * t) / t;
}

/* ------------------------------------------------------------------------
 * Restarts: kick-outs, frees, sidelines, 45s, penalties, throw-in
 * ---------------------------------------------------------------------- */
static void clear_radius(GameState *game, int kicker_team, int kicker,
                         float cx, float cz, float radius)
{
    int team, player;
    for (team = 0; team < 2; team++) {
        for (player = 0; player < GAME_TEAM_SIZE; player++) {
            if (game->players[team][player].off) continue;
            GamePlayer *member = &game->players[team][player];
            float dx, dz, distance;
            if (team == kicker_team && player == kicker) continue;
            if (game->restart_type == GAME_RESTART_PENALTY && player == 0 &&
                team != kicker_team) continue;        /* keeper stays on the line */
            dx = member->x - cx;
            dz = member->z - cz;
            distance = sqrtf(dx * dx + dz * dz);
            if (distance < radius) {
                float angle = distance > 0.01f ? atan2f(dz, dx) : 0.0f;
                member->x = clampf(cx + cosf(angle) * (radius + 1.0f), 1.0f,
                                   GAME_PITCH_LENGTH - 1.0f);
                member->z = clampf(cz + sinf(angle) * (radius + 1.0f), 1.0f,
                                   GAME_PITCH_WIDTH - 1.0f);
            }
        }
    }
}

static void enforce_penalty_positions(GameState *game)
{
    int kicker_team = game->ball_team;
    float gx = goal_x_of(kicker_team);
    int team, player;
    if (kicker_team < 0) return;
    for (team = 0; team < 2; team++) {
        for (player = 0; player < GAME_TEAM_SIZE; player++) {
            if (game->players[team][player].off) continue;
            GamePlayer *member = &game->players[team][player];
            if (team == kicker_team && player == game->ball_player) continue;
            if (team != kicker_team && player == 0) {
                member->x = gx;          /* goalkeeper on the goal line */
                member->z = GAME_PITCH_WIDTH * 0.5f;
                member->facing_x = kicker_team == 0 ? -1.0f : 1.0f;
                member->facing_z = 0.0f;
                continue;
            }
            if (fabsf(member->x - gx) < 21.0f)  /* outside the 20m line */
                member->x = gx + (kicker_team == 0 ? -21.0f : 21.0f);
        }
    }
}

static void place_restart(GameState *game, int team, int kicker, float x,
                          float z, int restart_type)
{
    GamePlayer *member = &game->players[team][kicker];
    int t, p;
    for (t = 0; t < 2; t++)
        for (p = 0; p < GAME_TEAM_SIZE; p++) {
            if (game->players[t][p].off) continue;
            game->players[t][p].action = GAME_ACT_NONE;
            game->players[t][p].jump_time = 0.0f;
        }
    member->x = x;
    member->z = z;
    member->facing_x = team == 0 ? 1.0f : -1.0f;
    member->facing_z = 0.0f;
    member->movement = 0.0f;
    game->ball_team = team;
    game->ball_player = kicker;
    game->ball.x = x;
    game->ball.z = z;
    game->ball.height = restart_type == GAME_RESTART_PENALTY ? GAME_BALL_REST : 1.05f;
    game->ball.velocity_x = game->ball.velocity_z = game->ball.velocity_y = 0.0f;
    game->ball.curve = 0.0f;
    game->ball.in_flight = 0;
    game->pickup_delay = 0.0f;
    game->pickup_team = game->pickup_player = -1;
    game->last_touch_team = team;
    game->restart_pending = 1;
    game->restart_type = restart_type;
    game->mark_play_on = 0;
    game->from_kickout = 0;
    game->restart_time = 0.0f;
    game->kickout_in_progress = 0;
    game->kickout_team = -1;
    game->penalty_active = 0;
    game->steps_carried = 0;
    game->step_time = 0.0f;
    game->last_was_bounce = 0;
    game->prev_ball_team = team;
    game->prev_ball_player = kicker;
    if (restart_type == GAME_RESTART_PENALTY) enforce_penalty_positions(game);
    clear_radius(game, team, kicker, x, z, GAME_KICKOUT_ARC_RADIUS);
    if (team == 0) game_select_player(game, kicker);
    sync_selected_player(game);
}

static int nearest_player_of(const GameState *game, int team, float x, float z,
                             int skip_keeper)
{
    int player, best = -1;
    float best_distance = 1000000.0f;
    for (player = skip_keeper ? 1 : 0; player < GAME_TEAM_SIZE; player++) {
        if (game->players[team][player].off) continue;
        float d = distance_squared(game->players[team][player].x,
                                   game->players[team][player].z, x, z);
        if (d < best_distance) { best_distance = d; best = player; }
    }
    return best >= 0 ? best : 0;
}

static void start_kickout(GameState *game, int team)
{
    /* 2025/26: kick-out from the 20m line; players 13m away; must pass the 40m arc. */
    float x = team == 0 ? GAME_KICKOUT_LINE : GAME_PITCH_LENGTH - GAME_KICKOUT_LINE;
    game->event_team = team;
    place_restart(game, team, 0, x, GAME_PITCH_WIDTH * 0.5f, GAME_RESTART_KICKOUT);
}

static void award_penalty(GameState *game, int team)
{
    float gx = goal_x_of(team);
    float x = gx + (team == 0 ? -GAME_PENALTY_SPOT : GAME_PENALTY_SPOT);
    int kicker = nearest_player_of(game, team, x, GAME_PITCH_WIDTH * 0.5f, 1);
    game->event_team = team;
    game->restart_type = GAME_RESTART_PENALTY;
    place_restart(game, team, kicker, x, GAME_PITCH_WIDTH * 0.5f, GAME_RESTART_PENALTY);
    set_event(game, GAME_EVENT_PENALTY);
}

/* Free kick to `team` where the foul happened. */
static void award_free(GameState *game, int team, float x, float z, GameEvent event)
{
    int kicker;
    x = clampf(x, 1.0f, GAME_PITCH_LENGTH - 1.0f);
    z = clampf(z, 1.0f, GAME_PITCH_WIDTH - 1.0f);
    kicker = nearest_player_of(game, team, x, z, 1);
    game->fouls++;
    game->event_team = team;
    place_restart(game, team, kicker, x, z, GAME_RESTART_FREE);
    set_event(game, event);
}

static void foul_on_carrier(GameState *game, int fouled_team, float x, float z,
                            GameEvent event)
{
    if (in_large_rectangle(1 - fouled_team, x, z)) award_penalty(game, fouled_team);
    else award_free(game, fouled_team, x, z, event);
}


/* ------------------------------------------------------------------------
 * v3 discipline (GAA Official Guide 2026): cards, sin bin, marks, dissent,
 * goalkeeper back-pass rule.
 * ---------------------------------------------------------------------- */
int game_goal_chance_zone(int attacking_team, float x, float z)
{
    /* Rule 5.41: a goal-scoring opportunity is inside the 20m line but not
     * within 25m of either sideline, or within the 20m semicircle arc. */
    float gx = goal_x_of(attacking_team);
    float ax = gx + (attacking_team == 0 ? -GAME_KICKOUT_LINE : GAME_KICKOUT_LINE);
    if (fabsf(x - gx) <= GAME_KICKOUT_LINE && z >= 25.0f && z <= GAME_PITCH_WIDTH - 25.0f)
        return 1;
    return distance_squared(x, z, ax, GAME_PITCH_WIDTH * 0.5f) <= 13.0f * 13.0f;
}

int game_players_on(const GameState *game, int team)
{
    int i, n = 0;
    for (i = 0; i < GAME_TEAM_SIZE; i++) if (!game->players[team][i].off) n++;
    return n;
}

static void bench_spot(int team, int idx, int off, float *x, float *z)
{
    *x = GAME_PITCH_LENGTH * 0.5f + (team == 0 ? -1.0f : 1.0f) * (7.0f + (float)idx * 0.9f);
    *z = off == 2 ? -6.5f : -3.0f;       /* sin bin beside the far sideline; red: dugout/tunnel */
}

static void issue_card(GameState *game, int team, int idx, int card, int with_penalty)
{
    GamePlayer *p = &game->players[team][idx];
    int second = 0;
    GameEvent ev;
    if (card == GAME_CARD_YELLOW || card == GAME_CARD_BLACK) {
        if (p->yellow || p->black) { second = 1; card = GAME_CARD_RED; }  /* any 2 = red */
        else if (card == GAME_CARD_YELLOW) p->yellow = 1;
        else { p->black = 1; p->off = 1; p->sin_bin = game->sin_bin_seconds; }
    }
    if (card == GAME_CARD_RED) { p->off = 2; p->sin_bin = 0.0f; }
    p->action = GAME_ACT_NONE;
    game->card_type = card;
    game->card_team = team;
    game->card_player = idx;
    game->card_second_yellow = second;
    game->card_time = 3.0f;
    game->cards_given[team][card]++;
    {   /* referee comes in from wherever he was */
        GameOfficial *ref = &game->referee;
        float dx = ref->x - p->x, dz = ref->z - p->z, d = sqrtf(dx * dx + dz * dz);
        if (d > 9.0f) { ref->x = p->x + dx / d * 9.0f; ref->z = p->z + dz / d * 9.0f; }
    }
    ev = second ? GAME_EVENT_SECOND_YELLOW :
         card == GAME_CARD_YELLOW ? GAME_EVENT_YELLOW_CARD :
         card == GAME_CARD_BLACK ? (with_penalty ? GAME_EVENT_BLACK_PENALTY : GAME_EVENT_BLACK_CARD) :
         GAME_EVENT_RED_CARD;
    game->event_team = 1 - team;
    set_event(game, ev);
    if (team == 0 && p->off && idx == game->selected_player) {
        int i, best = -1; float bd = 1e9f;
        for (i = 1; i < GAME_TEAM_SIZE; i++) {
            float d;
            if (game->players[0][i].off) continue;
            d = distance_squared(game->players[0][i].x, game->players[0][i].z, game->ball.x, game->ball.z);
            if (d < bd) { bd = d; best = i; }
        }
        if (best >= 0) game->selected_player = best;
        sync_selected_player(game);
    }
}

/* Dissent at a free (rule 6.4): the free is taken 50m more advantageous, up to the 13m line. */
static void apply_dissent(GameState *game, int team)
{
    GamePlayer *k;
    float dir = team == 0 ? 1.0f : -1.0f, x;
    if (!game->restart_pending || game->ball_team != team || game->ball_player < 0) return;
    k = &game->players[team][game->ball_player];
    x = game->ball.x + dir * 50.0f;
    x = team == 0 ? fminf(x, GAME_PITCH_LENGTH - 13.0f) : fmaxf(x, 13.0f);
    k->x = game->ball.x = x;
    clear_radius(game, team, game->ball_player, game->ball.x, game->ball.z, GAME_KICKOUT_ARC_RADIUS);
    game->event_team = team;
    set_event(game, GAME_EVENT_DISSENT);
    sync_selected_player(game);
}

/* A foul by (off_team, off_idx) on the opposition at (x, z). */
static void commit_foul(GameState *game, int off_team, int off_idx, int victim,
                        int foul, float x, float z)
{
    GamePlayer *o = &game->players[off_team][off_idx];
    int fouled = 1 - off_team, card = GAME_CARD_NONE, pen = 0;
    int keep_action = o->action;
    float keep_time = o->action_time;
    o->fouls_committed++;
    if (off_idx == 0 && foul != GAME_FOUL_STRIKE) foul = GAME_FOUL_TECHNICAL;  /* keepers: free only */
    game->last_foul_type = foul;
    switch (foul) {
    case GAME_FOUL_STRIKE: card = GAME_CARD_RED; break;
    case GAME_FOUL_PULL_DOWN: case GAME_FOUL_TRIP:
        card = GAME_CARD_BLACK;
        if (game_goal_chance_zone(fouled, x, z)) pen = 1;      /* black card + penalty */
        break;
    default:
        if (o->fouls_committed % 3 == 0) card = GAME_CARD_YELLOW;  /* persistent fouling */
        break;
    }
    if (in_large_rectangle(off_team, x, z)) pen = 1;
    if (pen) award_penalty(game, fouled);
    else award_free(game, fouled, x, z, GAME_EVENT_FOUL_TACKLE);
    o->action = keep_action;            /* keep the offender's swing / trip playing */
    o->action_time = keep_time;
    o->action_released = 1;
    if (foul != GAME_FOUL_TECHNICAL && victim >= 0 && victim < GAME_TEAM_SIZE &&
        !game->players[fouled][victim].off)
        begin_action(&game->players[fouled][victim], GAME_ACT_FALL);
    if (card != GAME_CARD_NONE) issue_card(game, off_team, off_idx, card, pen);
    if (!pen && game->dissent_chance > 0.0f && frand01(game) < game->dissent_chance)
        apply_dissent(game, fouled);
}

static int pick_cynical_foul(GameState *game)
{
    float r = frand01(game);
    return r < 0.80f ? GAME_FOUL_TECHNICAL : r < 0.91f ? GAME_FOUL_PULL_DOWN : GAME_FOUL_TRIP;
}

/* Hook / head hit lands on the contact frame: straight red if it connects. */
static void resolve_strike(GameState *game, int team, int index)
{
    GamePlayer *p = &game->players[team][index];
    int other = 1 - team, i, best = -1;
    float bd = 3.0f * 3.0f;
    for (i = 0; i < GAME_TEAM_SIZE; i++) {
        float d;
        if (game->players[other][i].off) continue;
        d = distance_squared(p->x, p->z, game->players[other][i].x, game->players[other][i].z);
        if (d < bd) { bd = d; best = i; }
    }
    if (best < 0) return;                             /* swung at fresh air */
    commit_foul(game, team, index, best, GAME_FOUL_STRIKE,
                game->players[other][best].x, game->players[other][best].z);
}

/* Frontend / test hook: make player off_idx of off_team foul the ball carrier now. */
void game_force_foul(GameState *game, int off_team, int off_idx, int foul)
{
    GamePlayer *o = &game->players[off_team][off_idx];
    int victim = (game->ball_team == 1 - off_team && game->ball_player >= 0) ? game->ball_player : 1;
    GamePlayer *v = &game->players[1 - off_team][victim];
    o->x = v->x - (off_team == 0 ? 0.9f : -0.9f); o->z = v->z;
    commit_foul(game, off_team, off_idx, victim, (GameFoul)foul, v->x, v->z);
}

static void award_mark(GameState *game, int team, int player, GameEvent ev)
{
    GamePlayer *m = &game->players[team][player];
    float x = m->x, gx = goal_x_of(team);
    if (ev == GAME_EVENT_ADVANCED_MARK && fabsf(x - gx) < 13.0f)
        x = gx + (team == 0 ? -13.0f : 13.0f);         /* inside the 13m: from the 13m line */
    game->event_team = team;
    place_restart(game, team, player, x, m->z, GAME_RESTART_FREE);
    game->mark_play_on = 1;
    set_event(game, ev);
}

/* Rule 1.10: the keeper may only receive a pass from a teammate when both are in
 * the large rectangle, or when the keeper is in the opposition half. */
static int back_pass_foul(GameState *game, int team, int player, float x, float z)
{
    float half = GAME_PITCH_LENGTH * 0.5f, gx, fx = x;
    if (player != 0 || game->last_release_team != team || game->last_release_player <= 0) return 0;
    if (game->last_touch_team != team) return 0;
    if (team == 0 ? x > half : x < half) return 0;
    if (in_large_rectangle(team, x, z) &&
        in_large_rectangle(team, game->kick_origin_x, game->kick_origin_z)) return 0;
    gx = goal_x_of(1 - team);                          /* keeper's own goal line */
    if (fabsf(x - gx) < 13.0f) fx = gx + (team == 0 ? 13.0f : -13.0f);
    award_free(game, 1 - team, fx, z, GAME_EVENT_BACK_PASS);
    return 1;
}

/* Sin-bin clocks, players walking off, returning from the sin bin. */
static void update_discipline(GameState *game, float delta_time)
{
    int t, i;
    if (game->card_time > 0.0f) {
        game->card_time -= delta_time;
        if (game->card_time < 0.0f) game->card_time = 0.0f;
    }
    for (t = 0; t < 2; t++)
        for (i = 0; i < GAME_TEAM_SIZE; i++) {
            GamePlayer *p = &game->players[t][i];
            float bx, bz, dx, dz, d;
            if (!p->off) continue;
            if (p->off == 1) {
                p->sin_bin -= delta_time;     /* runs regardless of stoppages */
                if (p->sin_bin <= 0.0f) {
                    p->off = 0;
                    p->sin_bin = 0.0f;
                    p->x = GAME_PITCH_LENGTH * 0.5f + (t == 0 ? -3.0f : 3.0f);
                    p->z = 1.0f;
                    p->facing_x = 0.0f; p->facing_z = 1.0f;
                    p->action = GAME_ACT_NONE;
                    if (game->event_time <= 0.0f) { game->event_team = t; set_event(game, GAME_EVENT_SIN_BIN_OVER); }
                    continue;
                }
            }
            if (game->card_time > 0.0f && t == game->card_team && i == game->card_player) {
                p->movement = 0.0f;           /* stands while the card is shown */
                continue;
            }
            p->action = GAME_ACT_NONE;
            p->jump_time = 0.0f;
            bench_spot(t, i, p->off, &bx, &bz);
            dx = bx - p->x; dz = bz - p->z;
            d = sqrtf(dx * dx + dz * dz);
            if (d < 0.2f) { p->movement = 0.0f; p->facing_x = 0.0f; p->facing_z = 1.0f; continue; }
            p->facing_x = dx / d; p->facing_z = dz / d;
            {
                float step = fminf(4.0f * delta_time, d);
                p->x += p->facing_x * step; p->z += p->facing_z * step;
                p->movement = step / (AI_SPEED * delta_time);
            }
        }
}

void game_start_half(GameState *game, int half)
{
    int team, player;
    float side = half == 1 ? 1.0f : -1.0f;
    reset_positions(game);
    reset_ball(game, -1, -1);
    game->half = half;
    for (team = 0; team < 2; team++) {
        for (player = 0; player < GAME_TEAM_SIZE; player++) {
            if (game->players[team][player].off) continue;
            GamePlayer *member = &game->players[team][player];
            if (member->x > 45.0f && member->x < 70.0f) member->x = 44.0f;
            if (member->x >= 70.0f && member->x < 95.0f) member->x = 96.0f;
        }
        /* 1v1 throw-in: one midfielder each; the other midfielders on opposite sidelines */
        game->players[team][7].x = GAME_PITCH_LENGTH * 0.5f + (team == 0 ? -1.2f : 1.2f);
        game->players[team][7].z = GAME_PITCH_WIDTH * 0.5f;
        game->players[team][8].x = GAME_PITCH_LENGTH * 0.5f + (team == 0 ? -2.0f : 2.0f);
        game->players[team][8].z = (team == 0) == (side > 0) ? 1.0f : GAME_PITCH_WIDTH - 1.0f;
    }
    game->ball_team = -1;
    game->ball_player = -1;
    game->ball.x = GAME_PITCH_LENGTH * 0.5f;
    game->ball.z = GAME_PITCH_WIDTH * 0.5f;
    game->ball.height = 1.9f;
    game->ball.velocity_x = game->ball.velocity_z = 0.0f;
    game->ball.velocity_y = 6.5f;
    game->ball.in_flight = 1;
    game->pickup_delay = 0.4f;
    game->restart_type = GAME_RESTART_THROW_IN;
    game->restart_pending = 0;
    game->prev_ball_team = game->prev_ball_player = -1;
    game->referee.x = GAME_PITCH_LENGTH * 0.5f;
    game->referee.z = GAME_PITCH_WIDTH * 0.5f + 0.9f;
    game->referee.facing_x = 0.0f;
    game->referee.facing_z = -1.0f;
    game->selected_player = 7;
    sync_selected_player(game);
    game->event_team = 0;
    set_event(game, GAME_EVENT_THROW_IN);
}

/* v3.2: is the frontend's pass-assist receiver usable from here? */
static int assist_valid(const GameState *game, const GamePlayer *from, float dmin, float dmax)
{
    int t = game->assist_target;
    if (t < 0 || t >= GAME_TEAM_SIZE || t == game->selected_player) return 0;
    if (game->players[0][t].off) return 0;
    float d = sqrtf(distance_squared(game->players[0][t].x, game->players[0][t].z, from->x, from->z));
    return d >= dmin && d <= dmax;
}

/* Human kick / hand pass from the selected player. */
static void release_ball(GameState *game, float speed, float lift, float curve,
                         GameEvent event, int action, int assist)
{
    GamePlayer *player = &game->players[0][game->selected_player];
    float aim_x = player->facing_x;
    float aim_z = player->facing_z;
    float length = sqrtf(aim_x * aim_x + aim_z * aim_z);
    if (length < 0.001f) { aim_x = 1.0f; aim_z = 0.0f; }
    else { aim_x /= length; aim_z /= length; }

    if (action == GAME_ACT_HANDPASS) {
        int mate, best = -1;
        float best_score = -1000000.0f;
        for (mate = 0; mate < GAME_TEAM_SIZE; mate++) {
            if (game->players[0][mate].off) continue;
            GamePlayer *other = &game->players[0][mate];
            float dx = other->x - player->x, dz = other->z - player->z;
            float d = sqrtf(dx * dx + dz * dz), score;
            if (mate == game->selected_player || mate == 0 || d < 3.0f || d > 22.0f) continue;
            if ((dx * aim_x + dz * aim_z) / d < 0.3f) continue;
            score = (dx * aim_x + dz * aim_z) / d * 10.0f - d * 0.3f +
                    nearest_defender_distance(game, 0, other->x, other->z);
            if (score > best_score) { best_score = score; best = mate; }
        }
        if (assist_valid(game, player, 2.0f, 26.0f)) best = game->assist_target;
        if (best >= 0) {
            GamePlayer *other = &game->players[0][best];
            float dx = other->x - player->x, dz = other->z - player->z;
            float d = sqrtf(dx * dx + dz * dz);
            if (best == game->assist_target) {     /* v3.2: lead the runner */
                float t = d / (9.0f + d * 0.55f);
                float lead = fminf(other->movement * PLAYER_SPEED * t * 0.7f, 3.0f);
                dx += other->facing_x * lead;
                dz += other->facing_z * lead;
                d = sqrtf(dx * dx + dz * dz);
                if (d < 0.5f) d = 0.5f;
            }
            aim_x = dx / d; aim_z = dz / d;
            speed = 9.0f + d * 0.55f;
            lift = lift_for(d, speed, 1.1f, 1.3f);
        }
    } else if (is_kick_action(action) && action != GAME_ACT_GROUND_KICK &&
               assist_valid(game, player, 6.0f, 70.0f)) {
        /* v3.2 kick-pass assist: aim at the receiver's run (power stays the player's) */
        GamePlayer *other = &game->players[0][game->assist_target];
        float t = 2.0f * fmaxf(lift, 1.0f) / GAME_BALL_GRAVITY;
        float lead = fminf(other->movement * PLAYER_SPEED * t * 0.5f, 5.0f);   /* into his path, capped */
        float dx = other->x + other->facing_x * lead - player->x;
        float dz = other->z + other->facing_z * lead - player->z;
        float d = sqrtf(dx * dx + dz * dz);
        if (d > 0.5f) { aim_x = dx / d; aim_z = dz / d; }
    } else if (assist && is_kick_action(action) && action != GAME_ACT_KICKOUT &&
               lift >= 0.0f) {
        /* aim assist toward the posts when roughly facing them */
        float gx = goal_x_of(0), gz = GAME_PITCH_WIDTH * 0.5f;
        float dx = gx - player->x, dz = gz - player->z;
        float d = sqrtf(dx * dx + dz * dz);
        if (d < 60.0f && (dx * aim_x + dz * aim_z) / d > 0.75f) {
            aim_x = aim_x * 0.4f + dx / d * 0.6f;
            aim_z = aim_z * 0.4f + dz / d * 0.6f;
            if (action != GAME_ACT_GROUND_KICK)
                lift = fmaxf(lift, lift_for(d, speed, 1.0f, 4.0f + d * 0.05f));
        }
    }
    queue_release(game, 0, game->selected_player, aim_x, aim_z, speed, lift,
                  curve, event, action);
}

static int restart_kick_action(const GameState *game)
{
    if (!game->restart_pending) return GAME_ACT_KICK;
    if (game->restart_type == GAME_RESTART_KICKOUT ||
        game->restart_type == GAME_RESTART_NONE) return GAME_ACT_KICKOUT;
    if (game->restart_type == GAME_RESTART_PENALTY) return GAME_ACT_GROUND_KICK;
    return GAME_ACT_FREE_KICK;
}

static void cpu_release_toward(GameState *game, int player_index,
                               float target_x, float target_z, float speed,
                               float lift, GameEvent event)
{
    GamePlayer *player = &game->players[1][player_index];
    int action = event == GAME_EVENT_HANDPASSED ? GAME_ACT_HANDPASS :
                 restart_kick_action(game);
    queue_release(game, 1, player_index, target_x - player->x,
                  target_z - player->z, speed, lift, 0.0f, event, action);
    game->cpu_possession_time = 0.0f;
}

/* CPU restart: kick-out past the 40m arc, frees/45s (shoot if in range),
 * sideline kicks, penalties. */
static void cpu_kick_in(GameState *game)
{
    const int team = 1;
    int kicker = game->ball_player;
    GamePlayer *k;
    int player, receiver = -1;
    float best = -1000000.0f;
    if (kicker < 0 || kicker >= GAME_TEAM_SIZE) return;
    k = &game->players[team][kicker];
    if (game->restart_type == GAME_RESTART_PENALTY) {
        float z = GAME_PITCH_WIDTH * 0.5f + (frand01(game) < 0.5f ? -1.0f : 1.0f) *
                  (1.2f + frand01(game) * 1.8f);
        cpu_release_toward(game, kicker, 0.0f, z, 27.0f, 0.9f, GAME_EVENT_KICKED);
        return;
    }
    if (game->restart_type == GAME_RESTART_FREE ||
        game->restart_type == GAME_RESTART_FORTY_FIVE) {
        float d = game_distance_to_goal(team, k->x, k->z);
        float off = fabsf(k->z - GAME_PITCH_WIDTH * 0.5f);
        if (d < 48.0f && off < 24.0f) {
            float speed = 27.0f;
            cpu_release_toward(game, kicker, 0.0f, GAME_PITCH_WIDTH * 0.5f, speed,
                               lift_for(d, speed, 1.0f, 4.5f), GAME_EVENT_KICKED);
            return;
        }
    }
    for (player = 0; player < GAME_TEAM_SIZE; player++) {
        if (game->players[team][player].off) continue;
        GamePlayer *m = &game->players[team][player];
        float forward = k->x - m->x;
        float d = sqrtf(distance_squared(k->x, k->z, m->x, m->z));
        float score;
        if (player == kicker || d < 8.0f || d > 55.0f) continue;
        if (game->restart_type == GAME_RESTART_KICKOUT &&
            game_distance_to_goal(0, m->x, m->z) < GAME_SCORING_ARC + 4.0f)
            continue;                      /* receiver must be beyond the 40m arc */
        score = forward * 0.6f + nearest_defender_distance(game, team, m->x, m->z) * 1.2f -
                d * 0.1f;
        if (score > best) { best = score; receiver = player; }
    }
    if (receiver >= 0) {
        GamePlayer *r = &game->players[team][receiver];
        float d = sqrtf(distance_squared(k->x, k->z, r->x, r->z));
        float speed = 14.0f + d * 0.35f;
        cpu_release_toward(game, kicker, r->x, r->z, speed,
                           lift_for(d, speed, 1.0f, 1.8f), GAME_EVENT_KICKED);
    } else {
        cpu_release_toward(game, kicker, k->x - 50.0f, k->z, 24.0f, 9.0f,
                           GAME_EVENT_KICKED);
    }
}

/* Referee follows play ~12m off the ball and signals decisions. */
static void update_referee(GameState *game, float delta_time)
{
    GameOfficial *ref = &game->referee;
    float tx = game->ball.x - 6.0f * (game->ball.x > GAME_PITCH_LENGTH * 0.5f ? 1.0f : -1.0f);
    float tz = game->ball.z + (game->ball.z < GAME_PITCH_WIDTH * 0.5f ? 11.0f : -11.0f);
    float dx, dz, d;
    if (game->card_time > 0.0f && game->card_team >= 0 && game->card_player >= 0) {
        /* walk up to the offender and hold the card aloft */
        GamePlayer *o = &game->players[game->card_team][game->card_player];
        dx = o->x - ref->x; dz = o->z - ref->z;
        d = sqrtf(dx * dx + dz * dz);
        if (d > 1.7f) {
            float step = fminf(7.5f * delta_time, d - 1.7f);
            ref->x += dx / d * step; ref->z += dz / d * step;
            ref->movement = step / delta_time / 7.0f;
        } else ref->movement = 0.0f;
        if (d > 0.01f) { ref->facing_x = dx / d; ref->facing_z = dz / d; }
        ref->signal = GAME_SIGNAL_CARD;
        ref->signal_time = game->card_time;
        return;
    }
    if (game->restart_type == GAME_RESTART_THROW_IN && game->ball_team < 0 &&
        game->ball.in_flight) { tx = ref->x; tz = ref->z + 1.0f; }
    dx = tx - ref->x; dz = tz - ref->z;
    d = sqrtf(dx * dx + dz * dz);
    if (ref->signal_time > 0.0f) {
        ref->signal_time -= delta_time;
        if (ref->signal_time <= 0.0f) ref->signal = GAME_SIGNAL_NONE;
        ref->movement = 0.0f;
    } else if (d > 1.5f) {
        float step = fminf((d > 8.0f ? 7.0f : 4.0f) * delta_time, d);
        ref->x += dx / d * step;
        ref->z += dz / d * step;
        ref->facing_x = dx / d;
        ref->facing_z = dz / d;
        ref->movement = step / delta_time / 7.0f;
    } else {
        float bx = game->ball.x - ref->x, bz = game->ball.z - ref->z;
        float bl = sqrtf(bx * bx + bz * bz);
        if (bl > 0.1f) { ref->facing_x = bx / bl; ref->facing_z = bz / bl; }
        ref->movement = 0.0f;
    }
}

static void update_formation(GameState *game, float delta_time, const int *chasers);

/* v3.2 (frontend flag ai_support): cheap support runs for the home carrier and
 * goal-side marking by the backs of the defending team.  Positioning only -
 * no rule is touched; players moved here skip the formation drift. */
static int ai_handled[2][GAME_TEAM_SIZE];

static int ai_free(const GameState *game, int team, int player, const int *chasers)
{
    const GamePlayer *m = &game->players[team][player];
    if (m->off || player == 0 || ai_handled[team][player]) return 0;
    if (team == 0 && player == game->selected_player) return 0;
    if (player == chasers[team]) return 0;
    if (game->ball_team == team && game->ball_player == player) return 0;
    if (game->pickup_team == team && game->pickup_player == player) return 0;
    if (player_busy(m)) return 0;
    return 1;
}

static void ai_move_to(GamePlayer *m, int team, int player, float tx, float tz, float delta_time)
{
    float dx, dz, d, step;
    if (player >= 1 && player <= 3) tx = team == 0 ? fminf(tx, 66.0f) : fmaxf(tx, 74.0f);
    if (player >= 12) tx = team == 0 ? fmaxf(tx, 74.0f) : fminf(tx, 66.0f);
    tx = clampf(tx, 1.0f, GAME_PITCH_LENGTH - 1.0f);
    tz = clampf(tz, 1.0f, GAME_PITCH_WIDTH - 1.0f);
    dx = tx - m->x; dz = tz - m->z;
    d = sqrtf(dx * dx + dz * dz);
    if (d < 0.8f) { m->movement *= 0.5f; return; }
    step = fminf((d > 5.0f ? AI_SPEED : AI_JOG_SPEED) * delta_time, d);
    m->facing_x = dx / d; m->facing_z = dz / d;
    m->x += m->facing_x * step;
    m->z += m->facing_z * step;
    m->movement = clampf(step / (AI_SPEED * delta_time), 0.0f, 1.0f);
}

static void update_support_and_marking(GameState *game, float delta_time, const int *chasers)
{
    int team, player, k;
    /* support: the two nearest home players offer a hand-pass option and a run ahead */
    if (game->ball_team == 0 && game->ball_player >= 0) {
        const GamePlayer *c = &game->players[0][game->ball_player];
        float side = c->z < GAME_PITCH_WIDTH * 0.5f ? 1.0f : -1.0f;
        float dir = goal_x_of(0) > GAME_PITCH_LENGTH * 0.5f ? 1.0f : -1.0f;
        for (k = 0; k < 2; k++) {
            int best = -1; float bd = 32.0f * 32.0f;
            for (player = 1; player < GAME_TEAM_SIZE; player++) {
                float d;
                if (!ai_free(game, 0, player, chasers)) continue;
                d = distance_squared(game->players[0][player].x, game->players[0][player].z, c->x, c->z);
                if (d < bd) { bd = d; best = player; }
            }
            if (best < 0) break;
            ai_handled[0][best] = 1;
            if (k == 0) ai_move_to(&game->players[0][best], 0, best, c->x + dir * 3.0f, c->z - side * 7.0f, delta_time);
            else        ai_move_to(&game->players[0][best], 0, best, c->x + dir * 13.0f, c->z + side * 11.0f, delta_time);
        }
    }
    /* marking: backs (1-6) of the defending team pick up the nearest attacker goal-side */
    for (team = 0; team < 2; team++) {
        int att = 1 - team;
        float goal = goal_x_of(att);          /* the goal this team defends */
        int taken[GAME_TEAM_SIZE] = { 0 };
        if (game->ball_team != att) continue;
        for (player = 1; player <= 6; player++) {
            int best = -1; float bd = 26.0f * 26.0f;
            if (!ai_free(game, team, player, chasers)) continue;
            for (k = 1; k < GAME_TEAM_SIZE; k++) {
                const GamePlayer *a = &game->players[att][k];
                float d;
                if (a->off || taken[k] || k == game->ball_player) continue;
                if (fabsf(a->x - goal) > 50.0f) continue;
                d = distance_squared(a->x, a->z, game->players[team][player].x, game->players[team][player].z);
                if (d < bd) { bd = d; best = k; }
            }
            if (best < 0) continue;
            taken[best] = 1;
            ai_handled[team][player] = 1;
            {
                const GamePlayer *a = &game->players[att][best];
                float gx = goal - a->x, gz = GAME_PITCH_WIDTH * 0.5f - a->z;
                float gl = sqrtf(gx * gx + gz * gz);
                if (gl < 0.01f) gl = 0.01f;
                ai_move_to(&game->players[team][player], team, player,
                           a->x + gx / gl * 1.8f, a->z + gz / gl * 1.8f, delta_time);
            }
        }
    }
}

static void update_cpu_players(GameState *game, float delta_time)
{
    int team;
    int player;
    int chasers[2] = { -1, -1 };
    if (game->restart_type == GAME_RESTART_THROW_IN && game->ball_team < 0) {
        /* 1v1 throw-in: only the two midfielders contest; everyone else holds */
        for (team = 0; team < 2; team++) {
            GamePlayer *m = &game->players[team][7];
            if (m->jump_time > 0.0f) m->jump_time -= delta_time;
            if (game->ball.velocity_y < 0.0f && game->ball.height < 3.6f &&
                m->jump_time <= 0.0f &&
                frand01(game) < (team == 0 ? 0.25f : 0.2f))
                m->jump_time = 0.7f;
        }
        return;
    }
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
            if (game->players[team][player].off) continue;
            GamePlayer *member = &game->players[team][player];
            if (member->jump_time > 0.0f) {
                member->jump_time -= delta_time;
                if (member->jump_time < 0.0f) member->jump_time = 0.0f;
            }
            if (team == 0 && player == game->selected_player) continue;
            member->movement *= 0.2f;
            if (player_busy(member) || game->restart_pending) continue;
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

        if (closest >= 0) chasers[team] = closest;
        if (closest >= 0 && closest_distance > 1.2f * 1.2f) {
            GamePlayer *chaser = &game->players[team][closest];
            float dx = chase_x - chaser->x;
            float dz = chase_z - chaser->z;
            float length = sqrtf(dx * dx + dz * dz);
            if (length > 0.001f) {
                float step = AI_SPEED * delta_time;
                if (game->ball_team >= 0 && step > length - 1.0f) step = length - 1.0f;
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
            if (game->players[1][player].off) continue;
            float distance = distance_squared(
                game->players[1][player].x, game->players[1][player].z,
                carrier->x, carrier->z);
            if (distance < nearest_distance) nearest_distance = distance;
        }
        if (nearest_distance <= CPU_TACKLE_RANGE * CPU_TACKLE_RANGE) {
            game->cpu_tackle_time += delta_time;
            if (game->cpu_tackle_time >= CPU_TACKLE_COMMIT_TIME &&
                game->protect_time <= 0.0f && !game->restart_pending &&
                !player_busy(carrier)) {
                int tackler = 0;
                float roll;
                nearest_distance = 1000000.0f;
                for (player = 0; player < GAME_TEAM_SIZE; player++) {
                    if (game->players[1][player].off) continue;
                    float distance = distance_squared(
                        game->players[1][player].x,
                        game->players[1][player].z, carrier->x, carrier->z);
                    if (distance < nearest_distance) {
                        nearest_distance = distance;
                        tackler = player;
                    }
                }
                game->cpu_tackle_time = 0.0f;
                if (game->players[1][tackler].tackle_cooldown > 0.0f) return;
                begin_action(&game->players[1][tackler], GAME_ACT_TACKLE);
                game->players[1][tackler].tackle_cooldown = 0.9f;
                roll = frand01(game);
                if (roll < 0.18f) {
                    int foul = pick_cynical_foul(game);
                    if (foul != GAME_FOUL_TECHNICAL)
                        begin_action(&game->players[1][tackler], GAME_ACT_TRIP);
                    commit_foul(game, 1, tackler, game->ball_player, foul, carrier->x, carrier->z);
                    return;
                }
                if (roll > 0.62f) return;          /* tackle missed */
                game->ball_team = 1;
                game->ball_player = tackler;
                game->steps_carried = 0;
                game->step_time = 0.0f;
                game->last_was_bounce = 0;
                game->last_touch_team = 1;
                game->cpu_possession_time = 0.0f;
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
            step = fminf(AI_JOG_SPEED * delta_time, length - 1.5f);
            member->facing_x = dx / length;
            member->facing_z = dz / length;
            member->x = clampf(member->x + member->facing_x * step,
                               1.0f, GAME_PITCH_LENGTH - 1.0f);
            member->z = clampf(member->z + member->facing_z * step,
                               1.0f, GAME_PITCH_WIDTH - 1.0f);
            member->movement = clampf(step / (AI_JOG_SPEED * delta_time), 0.0f, 1.0f);
        }
    }
    memset(ai_handled, 0, sizeof ai_handled);
    if (game->ai_support && !game->restart_pending) update_support_and_marking(game, delta_time, chasers);
    update_formation(game, delta_time, chasers);
}

/* Everyone not chasing/supporting drifts to a ball-relative formation spot.
 * 3v3 rule: full-backs (1-3) stay in their own half, full-forwards (12-14)
 * stay in the opposition half, so each team always keeps 3 in each half. */
static void update_formation(GameState *game, float delta_time, const int *chasers)
{
    int team, player;
    int possession = game->ball_team >= 0 ? game->ball_team : game->last_touch_team;
    for (team = 0; team < 2; team++) {
        float dir = team == 0 ? 1.0f : -1.0f;
        for (player = 0; player < GAME_TEAM_SIZE; player++) {
            if (game->players[team][player].off) continue;
            GamePlayer *m = &game->players[team][player];
            float hx = team == 0 ? FORMATION_X[player] : GAME_PITCH_LENGTH - FORMATION_X[player];
            float hz = FORMATION_Z[player];
            float tx, tz, dx, dz, d, step;
            if (team == 0 && player == game->selected_player) continue;
            if (ai_handled[team][player]) continue;
            if (player == chasers[team]) continue;
            if (game->ball_team == team && game->ball_player == player) continue;
            if (game->pickup_team == team && game->pickup_player == player) continue;
            if (team == 1 && game->ball_team == 1 &&
                (player == 7 || player == 8 || player == 12)) continue;
            if (player_busy(m)) continue;
            tx = hx + (game->ball.x - GAME_PITCH_LENGTH * 0.5f) * 0.45f +
                 (possession == team ? 9.0f : -5.0f) * dir;
            tz = hz + (game->ball.z - GAME_PITCH_WIDTH * 0.5f) * 0.3f;
            if (player == 0) {
                float gx = team == 0 ? 2.0f : GAME_PITCH_LENGTH - 2.0f;
                tx = gx;
                tz = GAME_PITCH_WIDTH * 0.5f + clampf((game->ball.z - GAME_PITCH_WIDTH * 0.5f) * 0.1f, -2.5f, 2.5f);
            }
            if (player >= 1 && player <= 3)
                tx = team == 0 ? fminf(tx, 66.0f) : fmaxf(tx, 74.0f);
            if (player >= 12)
                tx = team == 0 ? fmaxf(tx, 74.0f) : fminf(tx, 66.0f);
            tx = clampf(tx, 1.0f, GAME_PITCH_LENGTH - 1.0f);
            tz = clampf(tz, 1.0f, GAME_PITCH_WIDTH - 1.0f);
            if (game->restart_pending) {      /* hold position during a restart */
                m->movement = 0.0f;
                continue;
            }
            dx = tx - m->x; dz = tz - m->z;
            d = sqrtf(dx * dx + dz * dz);
            if (d < 1.0f) { m->movement = 0.0f; continue; }
            step = fminf((d > 10.0f ? AI_SPEED : AI_JOG_SPEED) * delta_time, d);
            m->facing_x = dx / d; m->facing_z = dz / d;
            m->x += m->facing_x * step;
            m->z += m->facing_z * step;
            m->movement = clampf(step / (AI_SPEED * delta_time), 0.0f, 1.0f);
        }
    }
}

static float nearest_defender_distance(const GameState *game, int team,
                                       float x, float z)
{
    int player;
    float nearest = 1000000.0f;
    for (player = 0; player < GAME_TEAM_SIZE; player++) {
        if (game->players[1 - team][player].off) continue;
        const GamePlayer *member = &game->players[1 - team][player];
        float distance = distance_squared(member->x, member->z, x, z);
        if (distance < nearest) nearest = distance;
    }
    return sqrtf(nearest);
}

/* Advance the 4-step count for any carrier; returns 1 if over-carried. */
static int count_steps(GameState *game, float distance)
{
    game->step_time += distance;
    while (game->step_time >= GAME_STEP_LENGTH) {
        game->step_time -= GAME_STEP_LENGTH;
        game->steps_carried++;
        if (game->steps_carried > 4) return 1;
    }
    return 0;
}

static void start_solo(GameState *game, GamePlayer *carrier)
{
    begin_action(carrier, GAME_ACT_SOLO);
    game->steps_carried = 0;
    game->step_time = 0.0f;
    game->last_was_bounce = 0;
    set_event(game, GAME_EVENT_SOLOED);
}

static int start_bounce(GameState *game, int team, GamePlayer *carrier)
{
    if (game->last_was_bounce) {     /* only one bounce in a row: free to opposition */
        foul_on_carrier(game, 1 - team, carrier->x, carrier->z, GAME_EVENT_ILLEGAL_BOUNCE);
        return 0;
    }
    begin_action(carrier, GAME_ACT_BOUNCE);
    game->steps_carried = 0;
    game->step_time = 0.0f;
    game->last_was_bounce = 1;
    set_event(game, GAME_EVENT_BOUNCED);
    return 1;
}

static void update_cpu_carrier(GameState *game, float delta_time)
{
    GamePlayer *carrier = &game->players[1][game->ball_player];
    int player;
    int receiver = -1;
    float best_receiver_score = -1000000.0f;
    float goal_distance = game_distance_to_goal(1, carrier->x, carrier->z);
    float goal_offset = fabsf(carrier->z - GAME_PITCH_WIDTH * 0.5f);
    float pressure = nearest_defender_distance(game, 1, carrier->x, carrier->z);
    float t = game->cpu_possession_time;

    if (player_busy(carrier) || game->restart_pending) return;

    if (t > 0.3f && goal_distance <= 36.0f && goal_offset <= 20.0f) {
        int go_for_goal = goal_distance <= 22.0f && goal_offset < 8.0f;
        float speed = go_for_goal ? 28.0f : 26.0f;
        float lift = lift_for(goal_distance, speed, 1.0f, go_for_goal ? 1.4f : 4.0f);
        cpu_release_toward(game, game->ball_player, 0.0f, GAME_PITCH_WIDTH * 0.5f,
                           speed, lift, GAME_EVENT_KICKED);
        return;
    }
    if (t > 0.5f && goal_distance >= GAME_SCORING_ARC + 0.5f && goal_distance < 46.0f &&
        goal_offset < 16.0f && pressure > 4.5f && frand01(game) < delta_time * 1.5f) {
        float speed = 29.0f;   /* two-point attempt from outside the arc */
        cpu_release_toward(game, game->ball_player, 0.0f, GAME_PITCH_WIDTH * 0.5f,
                           speed, lift_for(goal_distance, speed, 1.0f, 4.5f),
                           GAME_EVENT_KICKED);
        return;
    }

    for (player = 0; player < GAME_TEAM_SIZE; player++) {
        if (game->players[1][player].off) continue;
        GamePlayer *teammate = &game->players[1][player];
        float forward = carrier->x - teammate->x;
        float distance = sqrtf(distance_squared(carrier->x, carrier->z,
                                                teammate->x, teammate->z));
        float space;
        float score;
        if (player == game->ball_player || player == 0 || forward < 2.0f ||
            forward > 38.0f || distance < 5.0f || distance > 42.0f)
            continue;
        space = nearest_defender_distance(game, 1, teammate->x, teammate->z);
        score = forward * 0.7f + space * 0.8f - distance * 0.15f;
        if (score > best_receiver_score) {
            best_receiver_score = score;
            receiver = player;
        }
    }

    if (receiver >= 0 && t > 0.25f && (pressure < 4.5f || t > 1.4f)) {
        GamePlayer *target = &game->players[1][receiver];
        float distance = sqrtf(distance_squared(carrier->x, carrier->z,
                                                target->x, target->z));
        int hand = distance <= 13.0f;
        float speed = hand ? 8.0f + distance * 0.6f : 15.0f + distance * 0.3f;
        cpu_release_toward(game, game->ball_player, target->x, target->z, speed,
                           lift_for(distance, speed, 1.1f, hand ? 1.3f : 1.8f),
                           hand ? GAME_EVENT_HANDPASSED : GAME_EVENT_KICKED);
        return;
    }

    {
        float target_z = GAME_PITCH_WIDTH * 0.5f +
                         (carrier->z - GAME_PITCH_WIDTH * 0.5f) * 0.35f;
        float dx = -carrier->x;
        float dz = target_z - carrier->z;
        float length = sqrtf(dx * dx + dz * dz);
        if (length > 0.001f) {
            float step = CPU_CARRY_SPEED * delta_time;
            if (step > length) step = length;
            carrier->facing_x = dx / length;
            carrier->facing_z = dz / length;
            carrier->x = clampf(carrier->x + carrier->facing_x * step,
                                1.0f, GAME_PITCH_LENGTH - 1.0f);
            carrier->z = clampf(carrier->z + carrier->facing_z * step,
                                1.0f, GAME_PITCH_WIDTH - 1.0f);
            carrier->movement = step > 0.0f ? 1.0f : 0.0f;
            /* 4-step rule: bounce, then solo, alternately */
            if (carrier->action == GAME_ACT_NONE && game->steps_carried >= 3) {
                if (!game->last_was_bounce) start_bounce(game, 1, carrier);
                else start_solo(game, carrier);
            }
            if (count_steps(game, step)) {
                award_free(game, 0, carrier->x, carrier->z, GAME_EVENT_FOUR_STEPS);
                return;
            }
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
        game->ball.height = GAME_BALL_REST + 0.87f * progress;
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
        if (next_height <= GAME_BALL_REST) {
            float discriminant = game->ball.velocity_y *
                game->ball.velocity_y +
                2.0f * GAME_BALL_GRAVITY *
                fmaxf(game->ball.height - GAME_BALL_REST, 0.0f);
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
            game->ball.height = GAME_BALL_REST;
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
            crossing_height <= 15.0f) {
            float offset = crossing_z - goal_center;
            game->event_team = scoring_team;
            if (crossing_height <= GAME_CROSSBAR_HEIGHT) {
                if (game->penalty_active &&
                    (offset < 0.0f ? -1 : 1) == game->keeper_guess &&
                    fabsf(offset) < 2.6f && crossing_height < 2.0f &&
                    frand01(game) < 0.7f) {
                    game->penalty_active = 0;      /* keeper guessed right: saved */
                    game->ball.x = goal_x - (goal_x > 1.0f ? 1.0f : -1.0f);
                    game->ball.velocity_x *= -0.25f;
                    game->ball.velocity_z = (float)game->keeper_guess * 4.0f;
                    game->ball.velocity_y = 2.0f;
                    game->kick_clean = 0;
                    game->last_touch_team = 1 - scoring_team;
                    set_event(game, GAME_EVENT_PENALTY_SAVED);
                    return;
                }
                game->team_goals[scoring_team]++;
                set_event(game, GAME_EVENT_GOAL);
            } else if (game->kick_clean && !game->kick_no_two &&
                       game_distance_to_goal(scoring_team, game->kick_origin_x,
                                             game->kick_origin_z) >= GAME_SCORING_ARC) {
                game->team_points[scoring_team] += 2;   /* clean kick from outside the 40m arc */
                game->team_two_pointers[scoring_team]++;
                set_event(game, GAME_EVENT_TWO_POINT);
            } else {
                game->team_points[scoring_team]++;
                set_event(game, GAME_EVENT_POINT);
            }
            game->goals = game->team_goals[0];
            game->points = game->team_points[0];
            {
                GameEvent scored = game->event;
                start_kickout(game, 1 - scoring_team);
                game->event = scored;
            }
            return;
        }
    }

    if (game->ball.x < 0.0f || game->ball.x > GAME_PITCH_LENGTH ||
        game->ball.z < 0.0f || game->ball.z > GAME_PITCH_WIDTH) {
        float x_fraction = 2.0f;
        float z_fraction = 2.0f;
        if (game->ball.x < 0.0f || game->ball.x > GAME_PITCH_LENGTH) {
            float endline = game->ball.x < 0.0f ? 0.0f : GAME_PITCH_LENGTH;
            x_fraction = (endline - previous_x) / (game->ball.x - previous_x);
        }
        if (game->ball.z < 0.0f || game->ball.z > GAME_PITCH_WIDTH) {
            float sideline = game->ball.z < 0.0f ? 0.0f : GAME_PITCH_WIDTH;
            z_fraction = (sideline - previous_z) / (game->ball.z - previous_z);
        }
        game->penalty_active = 0;
        if (z_fraction <= x_fraction) {
            /* sideline kick to the team that did not last touch it, from outside the line */
            int team = 1 - game->last_touch_team;
            float x = clampf(previous_x + (game->ball.x - previous_x) * z_fraction, 1.0f,
                             GAME_PITCH_LENGTH - 1.0f);
            float z = game->ball.z < 0.0f ? -0.6f : GAME_PITCH_WIDTH + 0.6f;
            int kicker = nearest_player_of(game, team, x, z, 1);
            game->event_team = team;
            place_restart(game, team, kicker, x, z, GAME_RESTART_SIDELINE);
            set_event(game, GAME_EVENT_SIDELINE);
        } else {
            int defending = game->ball.x < 0.0f ? 0 : 1;
            if (game->last_touch_team == defending && !game->kickout_in_progress) {
                /* defender put it wide: '45' to the attackers (worth one point) */
                int team = 1 - defending;
                float x = defending == 0 ? 45.0f : GAME_PITCH_LENGTH - 45.0f;
                float z = clampf(previous_z, 10.0f, GAME_PITCH_WIDTH - 10.0f);
                int kicker = nearest_player_of(game, team, x, z, 1);
                game->event_team = team;
                place_restart(game, team, kicker, x, z, GAME_RESTART_FORTY_FIVE);
                set_event(game, GAME_EVENT_FORTY_FIVE);
            } else {
                start_kickout(game, defending);
                game->event_team = defending;
                set_event(game, GAME_EVENT_WIDE);
            }
        }
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
                if (game->players[team][player].off) continue;
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
        if (catcher_team >= 0 && game->kickout_in_progress &&
            catcher_team == game->kickout_team &&
            game_distance_to_goal(1 - catcher_team, game->ball.x, game->ball.z) <
                GAME_SCORING_ARC) {
            /* kick-out played by the kicking team inside the 40m arc: free to opposition */
            award_free(game, 1 - catcher_team, game->ball.x, game->ball.z,
                       GAME_EVENT_KICKOUT_TOUCHED);
            return;
        }
        if (catcher_team >= 0 &&
            back_pass_foul(game, catcher_team, catcher_player,
                           game->players[catcher_team][catcher_player].x,
                           game->players[catcher_team][catcher_player].z))
            return;
        if (catcher_team >= 0) {
            GamePlayer *c = &game->players[catcher_team][catcher_player];
            GameEvent mark = GAME_EVENT_NONE;
            if (game->from_kickout && game->last_release_team >= 0 &&
                fabsf(c->x - goal_x_of(1 - game->last_release_team)) >= 45.0f)
                mark = GAME_EVENT_KICKOUT_MARK;        /* rule 2.12 (i) */
            else if (game->kick_clean && game->last_release_team == catcher_team &&
                     game->last_release_player != catcher_player &&
                     fabsf(game->kick_origin_x - goal_x_of(catcher_team)) >= 45.0f &&
                     fabsf(c->x - goal_x_of(catcher_team)) <= GAME_KICKOUT_LINE)
                mark = GAME_EVENT_ADVANCED_MARK;       /* rule 2.12 (ii) */
            if (mark != GAME_EVENT_NONE) {
                game->kickout_in_progress = 0;
                game->kickout_team = -1;
                award_mark(game, catcher_team, catcher_player, mark);
                begin_action(c, GAME_ACT_CATCH);
                return;
            }
            game->from_kickout = 0;
            begin_action(&game->players[catcher_team][catcher_player], GAME_ACT_CATCH);
            if (game->restart_type == GAME_RESTART_THROW_IN)
                game->restart_type = GAME_RESTART_NONE;
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
        /* 2025/26: the kick-out must travel beyond the kicking team's 40m arc */
        if (game_distance_to_goal(1 - game->kickout_team, game->ball.x, game->ball.z) >=
            GAME_SCORING_ARC) {
            game->kickout_in_progress = 0;
            game->kickout_team = -1;
        } else if (!game->ball.in_flight && game->ball.height <= GAME_BALL_REST + 0.01f) {
            award_free(game, 1 - game->kickout_team, game->ball.x, game->ball.z,
                       GAME_EVENT_KICKOUT_SHORT);
            return;
        }
    }
    if (game->restart_type == GAME_RESTART_THROW_IN && !game->ball.in_flight)
        game->restart_type = GAME_RESTART_NONE;

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
                if (game->players[team][player].off) continue;
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

        if (nearest_team >= 0 &&
            back_pass_foul(game, nearest_team, nearest_player,
                           game->players[nearest_team][nearest_player].x,
                           game->players[nearest_team][nearest_player].z))
            return;
        if (nearest_team >= 0) {
            GamePlayer *picker =
                &game->players[nearest_team][nearest_player];
            game->from_kickout = 0;
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
            begin_action(picker, GAME_ACT_PICKUP);
            game->ball.x = picker->x + picker->facing_x * 0.45f;
            game->ball.z = picker->z + picker->facing_z * 0.45f;
            game->ball.height = GAME_BALL_REST;
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

static void check_three_v_three(GameState *game, float delta_time)
{
    int team, player, violator = -1;
    float half = GAME_PITCH_LENGTH * 0.5f;
    for (team = 0; team < 2 && violator < 0; team++) {
        int own = 0, opp = 0, need_own = 3, need_opp = 3;
        for (player = 1; player < GAME_TEAM_SIZE; player++) {
            if (game->players[team][player].off && player <= 3) need_own--;
            if (game->players[team][player].off && player >= 12) need_opp--;
        }
        for (player = 1; player < GAME_TEAM_SIZE; player++) {
            if (game->players[team][player].off) continue;
            int in_own = team == 0 ? game->players[team][player].x < half
                                   : game->players[team][player].x > half;
            if (in_own) own++; else opp++;
        }
        if (own < need_own || opp < need_opp) violator = team;
    }
    if (violator < 0) { game->three_v_three_time = 0.0f; return; }
    game->three_v_three_time += delta_time;
    if (game->three_v_three_time > 0.75f) {
        float x = violator == 0 ? GAME_KICKOUT_LINE : GAME_PITCH_LENGTH - GAME_KICKOUT_LINE;
        game->three_v_three_time = 0.0f;
        award_free(game, 1 - violator, x, GAME_PITCH_WIDTH * 0.5f, GAME_EVENT_THREE_V_THREE);
    }
}

void game_update(GameState *game, GameInput input, float delta_time)
{
    GamePlayer *controlled;
    float move_length;
    int busy;

    if (delta_time <= 0.0f) return;
    if (delta_time > 0.1f) delta_time = 0.1f;

    /* new carrier: reset the step / bounce counters and the clean-kick flag */
    if (game->ball_team >= 0 && (game->ball_team != game->prev_ball_team ||
                                 game->ball_player != game->prev_ball_player)) {
        game->steps_carried = 0;
        game->step_time = 0.0f;
        game->last_was_bounce = 0;
        game->kick_clean = 0;
        game->penalty_active = 0;
    }
    game->prev_ball_team = game->ball_team;
    game->prev_ball_player = game->ball_player;
    game->assist_target = input.pass_target - 1;
    if (game->protect_time > 0.0f) game->protect_time -= delta_time;
    update_discipline(game, delta_time);
    if (game->restart_pending && game->card_time <= 0.0f) game->restart_time += delta_time;
    if (game->restart_pending && game->card_time > 0.0f) {
        input.kick = input.kick_high = input.kick_low = input.kick_long = 0;
        input.solo = input.handpass = 0;   /* play waits while the referee shows the card */
    }

    update_actions(game, delta_time);
    sync_selected_player(game);
    controlled = &game->players[0][game->selected_player];
    busy = player_busy(controlled);
    if (input.high_field && !game->has_ball && controlled->jump_time <= 0.0f)
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
        float speed = (input.sprint ? SPRINT_SPEED : PLAYER_SPEED) *
                      (game->has_ball ? 0.95f : 1.0f) * (busy ? 0.3f : 1.0f);
        controlled->facing_x = input.move_x / move_length;
        controlled->facing_z = input.move_z / move_length;
        if (game->restart_pending && game->has_ball) {
            controlled->movement = 0.0f;          /* free taker: aim only */
        } else {
            float step = speed * move_length * delta_time;
            controlled->movement = move_length;
            controlled->x = clampf(controlled->x + controlled->facing_x * step,
                                   1.0f, GAME_PITCH_LENGTH - 1.0f);
            controlled->z = clampf(controlled->z + controlled->facing_z * step,
                                   1.0f, GAME_PITCH_WIDTH - 1.0f);
            if (game->has_ball && count_steps(game, step)) {
                sync_selected_player(game);
                award_free(game, 1, controlled->x, controlled->z, GAME_EVENT_FOUR_STEPS);
                return;
            }
        }
    } else {
        controlled->movement *= 0.2f;
    }

    sync_selected_player(game);

    if (game->restart_pending) {
        if (game->restart_type == GAME_RESTART_PENALTY) enforce_penalty_positions(game);
        clear_radius(game, game->ball_team, game->ball_player, game->ball.x,
                     game->ball.z, GAME_KICKOUT_ARC_RADIUS);
    }

    if (game->restart_pending && game->ball_team == 1 && game->restart_time > 0.7f &&
        !player_busy(&game->players[1][game->ball_player])) {
        GamePlayer *k = &game->players[1][game->ball_player];
        if (game->restart_type == GAME_RESTART_FREE && frand01(game) < 0.4f &&
            game_distance_to_goal(1, k->x, k->z) > 45.0f) {
            game->restart_pending = 0;            /* CPU takes a quick solo & go */
            game->restart_type = GAME_RESTART_NONE;
            game->protect_time = 1.0f;
            start_solo(game, k);
            set_event(game, GAME_EVENT_SOLO_AND_GO);
        } else {
            cpu_kick_in(game);
        }
    }

    if (game->restart_pending) {
        int solo_go = game->restart_type == GAME_RESTART_FREE && input.solo &&
                      game->has_ball &&
                      (game->mark_play_on ||
                       controlled->x < GAME_PITCH_LENGTH - GAME_KICKOUT_LINE);
        if (solo_go) {
            game->restart_pending = 0;            /* Solo & Go: toe-tap and play on */
            game->restart_type = GAME_RESTART_NONE;
            game->protect_time = 1.0f;
            start_solo(game, controlled);
            set_event(game, GAME_EVENT_SOLO_AND_GO);
        }
        input.handpass = 0;
        input.solo = 0;
        input.bounce = 0;
        if (game->restart_type == GAME_RESTART_PENALTY) {
            input.kick_high = input.kick_long = 0;
            if (input.kick) { input.kick = 0; input.kick_low = 1; }
        }
    }

    if (game->has_ball && !busy) {
        int action = restart_kick_action(game);
        /* power > 0 comes from the 3D frontend (charge bar + aim assist);
         * power == 0 keeps the original fixed kick values. */
        int fe = input.power > 0.0f;
        float p = clampf(input.power, 0.0f, 1.0f);
        if (input.kick) {
            release_ball(game, fe ? 20.0f + 14.0f * p : 30.0f, fe ? 3.5f + 5.0f * p : 3.0f,
                         input.curve, GAME_EVENT_KICKED, action, fe);
        } else if (input.kick_high) {
            release_ball(game, 20.0f, 9.0f, input.curve, GAME_EVENT_KICKED, action, fe);
        } else if (input.kick_low) {
            release_ball(game, action == GAME_ACT_GROUND_KICK ? 27.0f : fe ? 30.0f : 34.0f,
                         action == GAME_ACT_GROUND_KICK ? 0.9f : fe ? 0.8f : -1.0f,
                         input.curve, GAME_EVENT_KICKED, action, fe);
        } else if (input.kick_long) {
            release_ball(game, fe ? 36.0f : 38.0f, fe ? 8.0f : 7.0f, input.curve,
                         GAME_EVENT_KICKED, action, fe);
        } else if (input.handpass) {
            /* hand pass: struck with the fist / open hand, never thrown */
            release_ball(game, 13.0f, 2.0f, 0.0f, GAME_EVENT_HANDPASSED, GAME_ACT_HANDPASS, fe);
        } else if (input.solo && controlled->action == GAME_ACT_NONE) {
            start_solo(game, controlled);
        } else if (input.bounce && controlled->action == GAME_ACT_NONE) {
            if (!start_bounce(game, 0, controlled)) return;
        }
    } else if (input.tackle && game->ball_team == 1 && !busy &&
               controlled->tackle_cooldown <= 0.0f && game->protect_time <= 0.0f &&
               !game->restart_pending &&
               distance_squared(controlled->x, controlled->z,
                                game->ball.x, game->ball.z) <= 2.5f * 2.5f) {
        float roll = frand01(game);
        begin_action(controlled, GAME_ACT_TACKLE);
        controlled->tackle_cooldown = 0.6f;
        if (roll < 0.2f) {          /* mistimed: foul (sometimes a cynical pull-down / trip) */
            int foul = pick_cynical_foul(game);
            if (foul != GAME_FOUL_TECHNICAL) begin_action(controlled, GAME_ACT_TRIP);
            commit_foul(game, 0, game->selected_player, game->ball_player, foul,
                        game->ball.x, game->ball.z);
            return;
        }
        if (roll < 0.75f) {         /* clean open-hand flick */
            game->ball_team = 0;
            game->ball_player = game->selected_player;
            game->steps_carried = 0;
            game->last_was_bounce = 0;
            game->ball.velocity_x = 0.0f;
            game->ball.velocity_z = 0.0f;
            game->ball.velocity_y = 0.0f;
            game->last_touch_team = 0;
            set_event(game, GAME_EVENT_TACKLE);
        }
    }

    if (input.special && !game->has_ball && !busy && game->selected_player != 0 &&
        !game->restart_pending && controlled->action == GAME_ACT_NONE) {
        /* special move: hook or head hit - lands on the contact frame, straight red */
        begin_action(controlled, frand01(game) < 0.5f ? GAME_ACT_HOOK : GAME_ACT_HEAD_HIT);
        controlled->action_released = 0;
    }

    update_cpu_players(game, delta_time);

    if (game->ball_team == 1 && game->ball_player >= 0) {
        game->cpu_possession_time += delta_time;
        update_cpu_carrier(game, delta_time);
    } else {
        game->cpu_possession_time = 0.0f;
    }

    update_ball(game, delta_time, input.pickup);
    if (game->enforce_three_v_three && !game->restart_pending &&
        game->restart_type != GAME_RESTART_THROW_IN)
        check_three_v_three(game, delta_time);
    update_referee(game, delta_time);
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
        case GAME_EVENT_ILLEGAL_BOUNCE: return "Foul: double bounce - free";
        case GAME_EVENT_FOUR_STEPS: return "Foul: over-carrying (4 steps) - free";
        case GAME_EVENT_POINT: return "Point!";
        case GAME_EVENT_GOAL: return "Goal!";
        case GAME_EVENT_BALL_OUT: return "Ball out - restart";
        case GAME_EVENT_TACKLE: return "Clean tackle!";
        case GAME_EVENT_SHORT_KICKOUT: return "Short kick-out - turnover";
        case GAME_EVENT_HIGH_FIELD: return "Great high field!";
        case GAME_EVENT_PICKUP: return "Toe lift!";
        case GAME_EVENT_TWO_POINT: return "TWO-POINTER! (outside the 40m arc)";
        case GAME_EVENT_WIDE: return "Wide - kick-out";
        case GAME_EVENT_FREE: return "Free kick";
        case GAME_EVENT_FOUL_TACKLE: return "Foul tackle - free kick";
        case GAME_EVENT_SIDELINE: return "Sideline kick";
        case GAME_EVENT_FORTY_FIVE: return "45m free (one point)";
        case GAME_EVENT_KICKOUT: return "Kick-out";
        case GAME_EVENT_KICKOUT_SHORT: return "Kick-out short of the 40m arc - free";
        case GAME_EVENT_KICKOUT_TOUCHED: return "Kick-out played inside the arc - free";
        case GAME_EVENT_PENALTY: return "PENALTY! (11m, off the ground)";
        case GAME_EVENT_PENALTY_SAVED: return "Penalty saved!";
        case GAME_EVENT_THROW_IN: return "Throw-in (1 v 1)";
        case GAME_EVENT_SOLO_AND_GO: return "Solo & Go!";
        case GAME_EVENT_THREE_V_THREE: return "3 v 3 infraction - free";
        case GAME_EVENT_YELLOW_CARD: return "YELLOW CARD - caution";
        case GAME_EVENT_BLACK_CARD: return "BLACK CARD - 10 minutes in the sin bin";
        case GAME_EVENT_RED_CARD: return "RED CARD - sent off!";
        case GAME_EVENT_SECOND_YELLOW: return "Second card - RED, sent off!";
        case GAME_EVENT_BLACK_PENALTY: return "BLACK CARD + PENALTY (goal chance denied)";
        case GAME_EVENT_ADVANCED_MARK: return "ADVANCED MARK! (kick or play on)";
        case GAME_EVENT_KICKOUT_MARK: return "Kick-out mark (kick or play on)";
        case GAME_EVENT_DISSENT: return "Dissent! Free brought forward 50m";
        case GAME_EVENT_BACK_PASS: return "Back pass to the keeper - free";
        case GAME_EVENT_SIN_BIN_OVER: return "Sin bin over - back to 15";
        default: return "";
    }
}

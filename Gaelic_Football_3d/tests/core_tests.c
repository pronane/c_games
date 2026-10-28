#include "game.h"

#include <assert.h>
#include <stdio.h>
#include <math.h>

static void test_initial_state(void)
{
    GameState game;
    game_init(&game);
    assert(game.has_ball);
    assert(game.goals == 0);
    assert(game.points == 0);
    assert(game.home_team != game.away_team);
    assert(game.ball_team == 0);
    assert(game.ball_player == game.selected_player);
    assert(game.players[0][0].x != game.players[0][14].x);
    assert(GAME_PITCH_LENGTH == 140.0f);
    assert(GAME_PITCH_WIDTH == 85.0f);
}

static void test_point_scoring(void)
{
    GameState game;
    GameInput input = {0};
    game_init(&game);
    game.has_ball = 0;
    game.ball_team = -1;
    game.ball_player = -1;
    game.ball.x = GAME_PITCH_LENGTH - 0.1f;
    game.ball.z = GAME_PITCH_WIDTH * 0.5f;
    game.ball.height = 3.0f;
    game.ball.velocity_x = 5.0f;
    game.ball.in_flight = 1;

    game_update(&game, input, 0.05f);

    assert(game.points == 1);
    assert(game.goals == 0);
    assert(game.event == GAME_EVENT_POINT);
}

static void test_goal_scoring(void)
{
    GameState game;
    GameInput input = {0};
    game_init(&game);
    game.has_ball = 0;
    game.ball_team = -1;
    game.ball_player = -1;
    game.ball.x = GAME_PITCH_LENGTH - 0.1f;
    game.ball.z = GAME_PITCH_WIDTH * 0.5f;
    game.ball.height = 1.0f;
    game.ball.velocity_x = 5.0f;
    game.ball.in_flight = 1;

    game_update(&game, input, 0.05f);

    assert(game.goals == 1);
    assert(game.points == 0);
    assert(game.event == GAME_EVENT_GOAL);
}

static void test_four_step_turnover(void)
{
    GameState game;
    GameInput input = {0};
    int i;
    game_init(&game);
    for (i = 0; i < GAME_TEAM_SIZE; i++) {
        game.players[1][i].x = GAME_PITCH_LENGTH - 5.0f;
        game.players[1][i].z = GAME_PITCH_WIDTH - 5.0f;
    }
    input.move_x = 1.0f;

    for (i = 0; i < 40 && game.fouls == 0; i++) game_update(&game, input, 0.1f);

    /* 2025/26 rules: over-carrying gives a free to the opposition */
    assert(!game.has_ball);
    assert(game.fouls == 1);
    assert(game.event == GAME_EVENT_FOUR_STEPS);
    assert(game.ball_team == 1 && game.restart_pending);
}

static void test_player_movement_anim_state(void)
{
    GameState game;
    GameInput input = {0};
    game_init(&game);
    input.move_x = 1.0f;

    game_update(&game, input, 0.05f);
    assert(game.players[0][game.selected_player].movement == 1.0f);

    input.move_x = 0.0f;
    game_update(&game, input, 0.05f);
    assert(game.players[0][game.selected_player].movement < 1.0f);
}

static void test_solo_allows_next_bounce(void)
{
    GameState game;
    GameInput input = {0};
    game_init(&game);
    game.last_was_bounce = 1;
    input.solo = 1;
    game_update(&game, input, 0.05f);
    assert(!game.last_was_bounce);

    input.solo = 0;
    { int k; for (k = 0; k < 6; k++) game_update(&game, input, 0.1f); } /* toe-tap finishes */
    input.bounce = 1;
    game_update(&game, input, 0.05f);
    assert(game.last_was_bounce);
    assert(game.event == GAME_EVENT_BOUNCED);
}

static void test_consecutive_bounce_is_foul(void)
{
    GameState game;
    GameInput input = {0};
    game_init(&game);
    game.last_was_bounce = 1;
    input.bounce = 1;

    game_update(&game, input, 0.05f);

    /* 2025/26 rules: a second consecutive bounce is a free to the opposition */
    assert(!game.has_ball);
    assert(game.ball_team == 1 && game.restart_pending);
    assert(game.fouls == 1);
    assert(game.event == GAME_EVENT_ILLEGAL_BOUNCE);
}

static void test_team_and_player_selection(void)
{
    GameState game;
    game_init(&game);
    game_set_teams(&game, 2, 3, 4);

    assert(game.home_team == 2);
    assert(game.away_team == 3);
    assert(game.selected_player == 4);
    assert(game.ball_player == 4);

    game_select_next_player(&game, 1);
    assert(game.selected_player == 5);
    game_select_next_player(&game, -1);
    assert(game.selected_player == 4);
}

static void test_nearest_player_selection_tracks_the_ball(void)
{
    GameState game;
    game_init(&game);
    game.ball.x = game.players[0][4].x;
    game.ball.z = game.players[0][4].z;

    game_select_nearest_player(&game);

    assert(game.selected_player == 4);
}

static void test_opponent_can_pick_up_a_loose_ball(void)
{
    GameState game;
    GameInput input = {0};
    int opponent_player = 14;
    int frame;
    game_init(&game);
    game.ball_team = -1;
    game.ball_player = -1;
    game.ball.x = game.players[1][opponent_player].x;
    game.ball.z = game.players[1][opponent_player].z;
    game.ball.height = GAME_BALL_REST;
    game.ball.in_flight = 0;
    game.pickup_delay = 0.0f;

    game_update(&game, input, 0.01f);
    assert(game.ball_team == -1);
    assert(game.pickup_team == 1);

    for (frame = 0; frame < 5; frame++)
        game_update(&game, input, 0.1f);
    assert(game.ball_team == 1);
    assert(game.ball_player == opponent_player);
    assert(game.event == GAME_EVENT_PICKUP);
}

static void test_home_player_must_foot_lift_a_ground_ball(void)
{
    GameState game;
    GameInput input = {0};
    int player;
    int frame;
    game_init(&game);
    for (player = 0; player < GAME_TEAM_SIZE; player++) {
        if (player != game.selected_player) {
            game.players[0][player].x = 5.0f;
            game.players[0][player].z = 80.0f;
        }
        game.players[1][player].x = 135.0f;
        game.players[1][player].z = 80.0f;
    }
    game.ball_team = -1;
    game.ball_player = -1;
    game.ball.x = game.players[0][game.selected_player].x;
    game.ball.z = game.players[0][game.selected_player].z;
    game.ball.height = GAME_BALL_REST;
    game.ball.in_flight = 0;
    game.has_ball = 0;

    game_update(&game, input, 0.05f);
    assert(game.ball_team == -1);
    assert(game.pickup_team == -1);

    input.pickup = 1;
    game_update(&game, input, 0.05f);
    assert(game.ball_team == -1);
    assert(game.pickup_team == 0);
    assert(game.pickup_player == game.selected_player);
    assert(game.ball.height >= GAME_BALL_REST && game.ball.height < 1.05f);

    input.pickup = 0;
    for (frame = 0; frame < 5; frame++)
        game_update(&game, input, 0.1f);
    assert(game.ball_team == 0);
    assert(game.ball_player == game.selected_player);
    assert(game.has_ball);
    assert(game.event == GAME_EVENT_PICKUP);
}

static void test_home_ai_performs_ground_foot_pickup(void)
{
    GameState game;
    GameInput input = {0};
    int player;
    game_init(&game);
    for (player = 0; player < GAME_TEAM_SIZE; player++) {
        game.players[0][player].x = 5.0f + (float)player * 4.0f;
        game.players[0][player].z = 80.0f;
        game.players[1][player].x = 135.0f;
        game.players[1][player].z = 80.0f;
    }
    game.ball_team = -1;
    game.ball_player = -1;
    game.ball.x = game.players[0][3].x;
    game.ball.z = game.players[0][3].z;
    game.ball.height = GAME_BALL_REST;
    game.ball.in_flight = 0;
    game.has_ball = 0;

    game_update(&game, input, 0.05f);
    assert(game.pickup_team == 0);
    assert(game.pickup_player == 3);
    assert(game.ball_team == -1);
}

static void test_high_field_catches_a_high_ball(void)
{
    GameState game;
    GameInput input = {0};
    GamePlayer *selected;
    game_init(&game);
    selected = &game.players[0][game.selected_player];
    game.ball_team = -1;
    game.ball_player = -1;
    game.ball.x = selected->x - 1.0f;
    game.ball.z = selected->z;
    game.ball.height = 2.0f;
    game.ball.velocity_x = 10.0f;
    game.ball.velocity_z = 0.0f;
    game.ball.velocity_y = 0.0f;
    game.ball.in_flight = 1;
    input.high_field = 1;

    game_update(&game, input, 0.05f);

    assert(game.ball_team == 0);
    assert(game.ball_player == game.selected_player);
    assert(!game.ball.in_flight);
    assert(game.event == GAME_EVENT_HIGH_FIELD);
}

static void test_cpu_opponent_jumps_for_a_high_ball(void)
{
    GameState game;
    GameInput input = {0};
    int opponent = 14;
    game_init(&game);
    game.ball_team = -1;
    game.ball_player = -1;
    game.ball.x = game.players[1][opponent].x;
    game.ball.z = game.players[1][opponent].z;
    game.ball.height = 2.0f;
    game.ball.velocity_x = 0.0f;
    game.ball.velocity_z = 0.0f;
    game.ball.velocity_y = 0.0f;
    game.ball.in_flight = 1;

    game_update(&game, input, 0.05f);

    assert(game.ball_team == 1);
    assert(game.ball_player == opponent);
    assert(game.event == GAME_EVENT_HIGH_FIELD);
}

static void test_cpu_carrier_looks_for_forward_pass_under_pressure(void)
{
    GameState game;
    GameInput input = {0};
    int i;
    int carrier = 10;
    int receiver = 9;
    game_init(&game);
    for (i = 0; i < GAME_TEAM_SIZE; i++) {
        game.players[0][i].x = 130.0f;
        game.players[0][i].z = 80.0f;
        game.players[1][i].x = 115.0f;
        game.players[1][i].z = 78.0f;
    }
    game.players[1][carrier].x = 80.0f;
    game.players[1][carrier].z = 42.5f;
    game.players[1][receiver].x = 72.0f;
    game.players[1][receiver].z = 42.5f;
    game.players[0][0].x = 81.0f;
    game.players[0][0].z = 42.5f;
    game.ball_team = 1;
    game.ball_player = carrier;
    game.ball.x = game.players[1][carrier].x;
    game.ball.z = game.players[1][carrier].z;
    game.has_ball = 0;

    /* the CPU now takes a short decision time before releasing */
    { int k; for (k = 0; k < 20 && game.ball_team == 1; k++) game_update(&game, input, 0.05f); }

    assert(game.ball_team == -1);
    assert(game.ball.in_flight);
    assert(game.event == GAME_EVENT_HANDPASSED ||
           game.event == GAME_EVENT_KICKED);
    assert(game.last_touch_team == 1);
}

static void test_cpu_takes_goal_opportunity(void)
{
    GameState game;
    GameInput input = {0};
    int carrier = 10;
    int frame;
    game_init(&game);
    for (frame = 0; frame < GAME_TEAM_SIZE; frame++) {
        game.players[0][frame].x = 1.0f;
        game.players[0][frame].z = 1.0f;
        game.players[1][frame].x = 135.0f;
        game.players[1][frame].z = 80.0f;
    }
    game.players[1][carrier].x = 20.0f;
    game.players[1][carrier].z = GAME_PITCH_WIDTH * 0.5f;
    game.ball_team = 1;
    game.ball_player = carrier;
    game.ball.x = game.players[1][carrier].x;
    game.ball.z = game.players[1][carrier].z;
    game.has_ball = 0;

    /* the CPU now takes a short decision time before releasing */
    { int k; for (k = 0; k < 20 && game.ball_team == 1; k++) game_update(&game, input, 0.05f); }

    assert(game.ball_team == -1);
    assert(game.ball.in_flight);
    assert(game.ball.velocity_x < 0.0f);
    assert(game.event == GAME_EVENT_KICKED);
    for (frame = 0; frame < 30 && game.team_goals[1] == 0; frame++)
        game_update(&game, input, 0.05f);
    assert(game.team_goals[1] == 1);
}

static void test_cpu_can_take_a_point_attempt(void)
{
    GameState game;
    GameInput input = {0};
    int carrier = 10;
    int frame;
    game_init(&game);
    for (frame = 0; frame < GAME_TEAM_SIZE; frame++) {
        game.players[0][frame].x = 1.0f;
        game.players[0][frame].z = 1.0f;
        game.players[1][frame].x = 135.0f;
        game.players[1][frame].z = 80.0f;
    }
    game.players[1][carrier].x = 35.0f;
    game.players[1][carrier].z = GAME_PITCH_WIDTH * 0.5f;
    game.ball_team = 1;
    game.ball_player = carrier;
    game.ball.x = game.players[1][carrier].x;
    game.ball.z = game.players[1][carrier].z;
    game.has_ball = 0;

    for (frame = 0; frame < 35 && game.team_points[1] == 0 &&
         game.team_goals[1] == 0; frame++)
        game_update(&game, input, 0.05f);

    assert(game.team_points[1] == 1);
    assert(game.team_goals[1] == 0);
}

static void test_tackle_wins_possession(void)
{
    GameState game;
    GameInput input = {0};
    game_init(&game);
    game.ball_team = 1;
    game.ball_player = 0;
    game.ball.x = game.players[0][game.selected_player].x;
    game.ball.z = game.players[0][game.selected_player].z;
    input.tackle = 1;

    game_update(&game, input, 0.05f);

    assert(game.ball_team == 0);
    assert(game.ball_player == game.selected_player);
    assert(game.has_ball);
    assert(game.event == GAME_EVENT_TACKLE);
}

static void test_cpu_tackles_home_carrier_after_closing_down(void)
{
    GameState game;
    GameInput input = {0};
    int frame;
    int tackler = 4;
    game_init(&game);
    game.players[0][game.selected_player].x = 70.0f;
    game.players[0][game.selected_player].z = 42.5f;
    for (frame = 0; frame < GAME_TEAM_SIZE; frame++) {
        game.players[1][frame].x = GAME_PITCH_LENGTH - 5.0f;
        game.players[1][frame].z = GAME_PITCH_WIDTH - 5.0f;
    }
    game.players[1][tackler].x = 71.0f;
    game.players[1][tackler].z = 42.5f;
    game.ball_team = 0;
    game.ball_player = game.selected_player;
    game.ball.x = game.players[0][game.selected_player].x;
    game.ball.z = game.players[0][game.selected_player].z;
    game.has_ball = 1;

    for (frame = 0; frame < 10 && game.ball_team == 0; frame++)
        game_update(&game, input, 0.05f);

    assert(game.ball_team == 1);
    assert(game.ball_player == tackler);
    assert(game.event == GAME_EVENT_TACKLE);
}

static void test_kick_curve_changes_ball_lateral_path(void)
{
    GameState left;
    GameState right;
    GameInput input = {0};
    int team;
    int player;
    int frame;

    game_init(&left);
    right = left;
    for (team = 0; team < 2; team++) {
        for (player = 0; player < GAME_TEAM_SIZE; player++) {
            left.players[team][player].x = team == 0 ? 5.0f : 135.0f;
            left.players[team][player].z = team == 0 ? 5.0f : 80.0f;
            right.players[team][player] = left.players[team][player];
        }
    }
    left.ball_team = -1;
    left.ball_player = -1;
    left.ball.x = 70.0f;
    left.ball.z = 42.5f;
    left.ball.height = 8.0f;
    left.ball.velocity_x = 25.0f;
    left.ball.velocity_y = 5.0f;
    left.ball.curve = -1.0f;
    left.ball.in_flight = 1;
    left.pickup_delay = 2.0f;
    right = left;
    right.ball.curve = 1.0f;

    for (frame = 0; frame < 10; frame++) {
        game_update(&left, input, 0.05f);
        game_update(&right, input, 0.05f);
    }

    assert(left.ball.z < 42.5f);
    assert(right.ball.z > 42.5f);
}

static void test_kicker_does_not_immediately_reclaim_own_kick(void)
{
    GameState game;
    GameInput input = {0};
    int player;
    int frame;
    game_init(&game);
    for (player = 0; player < GAME_TEAM_SIZE; player++) {
        if (player != game.selected_player) {
            game.players[0][player].x = 5.0f;
            game.players[0][player].z = 80.0f;
        }
        game.players[1][player].x = 135.0f;
        game.players[1][player].z = 80.0f;
    }
    input.kick = 1;
    game_update(&game, input, 0.01f);
    input.kick = 0;

    for (frame = 0; frame < 8; frame++)
        game_update(&game, input, 0.05f);

    assert(game.ball_team == -1);
    assert(game.last_release_team == 0);
}

static void test_kick_types_have_distinct_trajectories(void)
{
    GameState game;
    GameInput input = {0};

    game_init(&game);
    input.kick = 1;
    game_update(&game, input, 0.01f);
    assert(game.ball.in_flight);
    assert(game.ball.velocity_x > 29.0f && game.ball.velocity_x < 31.0f);
    assert(game.ball.velocity_y > 2.8f && game.ball.velocity_y < 3.0f);

    game_init(&game);
    input = (GameInput){0};
    input.kick_high = 1;
    game_update(&game, input, 0.01f);
    assert(game.ball.in_flight);
    assert(game.ball.velocity_x > 19.0f && game.ball.velocity_x < 21.0f);
    assert(game.ball.velocity_y > 8.8f && game.ball.velocity_y < 9.0f);

    game_init(&game);
    input = (GameInput){0};
    input.kick_low = 1;
    game_update(&game, input, 0.01f);
    assert(game.ball.in_flight);
    assert(game.ball.velocity_x > 33.0f && game.ball.velocity_x < 35.0f);
    assert(game.ball.velocity_y < -0.9f && game.ball.velocity_y > -1.1f);

    game_init(&game);
    input = (GameInput){0};
    input.kick_long = 1;
    game_update(&game, input, 0.01f);
    assert(game.ball.in_flight);
    assert(game.ball.velocity_x > 37.0f && game.ball.velocity_x < 39.0f);
    assert(game.ball.velocity_y > 6.8f && game.ball.velocity_y < 7.0f);
}

static void test_kickout_must_clear_arc_before_pickup(void)
{
    GameState game;
    GameInput input = {0};
    float arc_x = GAME_KICKOUT_LINE;
    float arc_z = GAME_PITCH_WIDTH * 0.5f;
    int team;
    int player;
    int i;
    int kick_type;

    for (kick_type = 0; kick_type < 4; kick_type++) {
        game_init(&game);
        game.players[0][game.selected_player].x = arc_x;
        game.players[0][game.selected_player].z = arc_z;
        game.ball_team = 0;
        game.ball_player = game.selected_player;
        game.ball.x = arc_x;
        game.ball.z = arc_z;
        game.restart_pending = 1;
        input = (GameInput){0};
        if (kick_type == 0) input.kick = 1;
        else if (kick_type == 1) input.kick_high = 1;
        else if (kick_type == 2) input.kick_low = 1;
        else input.kick_long = 1;

        game_update(&game, input, 0.05f);

        assert(game.kickout_in_progress);
        assert(game.ball_team == -1);
        assert(game.ball.x < arc_x + GAME_KICKOUT_ARC_RADIUS);
        if (kick_type == 0) {
            for (team = 0; team < 2; team++) {
                for (player = 0; player < GAME_TEAM_SIZE; player++) {
                    float dx = game.players[team][player].x - arc_x;
                    float dz = game.players[team][player].z - arc_z;
                    if (team == 0 && player == game.selected_player) continue;
                    assert(dx * dx + dz * dz >=
                           GAME_KICKOUT_ARC_RADIUS * GAME_KICKOUT_ARC_RADIUS);
                }
            }
        }

        input = (GameInput){0};
        for (i = 0; i < 40 && game.kickout_in_progress; i++) {
            game_update(&game, input, 0.05f);
        }
        /* 2025/26: the kick-out must pass the 40m arc, else free to the opposition */
        assert(!game.kickout_in_progress);
        assert(game.ball.x >= GAME_SCORING_ARC || game.event == GAME_EVENT_KICKOUT_SHORT ||
               game.ball_team == 1 /* opposition may intercept inside the arc */);
    }
}

static void test_sideline_out_awards_opponent_kick_in(void)
{
    GameState game;
    GameInput input = {0};
    game_init(&game);
    game.ball_team = -1;
    game.ball_player = -1;
    game.ball.x = 70.0f;
    game.ball.z = 0.1f;
    game.ball.height = 0.5f;
    game.ball.velocity_z = -5.0f;
    game.ball.in_flight = 1;
    game.last_touch_team = 0;

    game_update(&game, input, 0.05f);

    /* sideline kick, taken from outside the line where the ball went out */
    assert(game.event == GAME_EVENT_SIDELINE);
    assert(game.ball_team == 1);
    assert(game.ball_player >= 0 && game.ball_player < GAME_TEAM_SIZE);
    assert(game.restart_pending);
    assert(game.ball.z < 0.0f);
    assert(game.ball.x > 69.0f && game.ball.x < 71.0f);

    { int k; for (k = 0; k < 30 && game.ball_team == 1; k++) game_update(&game, input, 0.05f); }

    assert(game.event == GAME_EVENT_KICKED);
    assert(game.ball_team == -1);
    assert(game.ball.in_flight);
    assert(!game.restart_pending);
    assert(game.last_touch_team == 1);
}

static void test_opponent_kick_in_awarded_to_home_team(void)
{
    GameState game;
    GameInput input = {0};
    game_init(&game);
    game.ball_team = -1;
    game.ball_player = -1;
    game.ball.x = 70.0f;
    game.ball.z = GAME_PITCH_WIDTH - 0.1f;
    game.ball.height = 0.5f;
    game.ball.velocity_z = 5.0f;
    game.ball.in_flight = 1;
    game.last_touch_team = 1;

    game_update(&game, input, 0.05f);
    assert(game.event == GAME_EVENT_SIDELINE);
    assert(game.ball_team == 0);
    assert(game.restart_pending);
    assert(game.ball.z > GAME_PITCH_WIDTH);
    assert(game.ball.x > 69.0f && game.ball.x < 71.0f);

    input.kick = 1;
    game_update(&game, input, 0.05f);
    assert(game.ball_team == -1);
    assert(game.ball.in_flight);
    assert(!game.restart_pending);
    assert(game.last_touch_team == 0);
}

static void test_non_scoring_endline_awards_defender(void)
{
    GameState game;
    GameInput input = {0};
    game_init(&game);
    game.ball_team = -1;
    game.ball_player = -1;
    game.ball.x = 0.1f;
    game.ball.z = 10.0f;
    game.ball.height = 0.5f;
    game.ball.velocity_x = -5.0f;
    game.ball.in_flight = 1;
    game.last_touch_team = 1;            /* attacker put it wide */

    game_update(&game, input, 0.05f);

    /* wide: kick-out by the goalkeeper from the 20m line */
    assert(game.event == GAME_EVENT_WIDE);
    assert(game.ball_team == 0);
    assert(game.ball_player == 0);
    assert(game.restart_pending);
    assert(game.ball.x > GAME_KICKOUT_LINE - 0.5f && game.ball.x < GAME_KICKOUT_LINE + 0.5f);

    /* defender put it wide: 45 to the attackers */
    game_init(&game);
    game.ball_team = -1;
    game.ball_player = -1;
    game.ball.x = 0.1f;
    game.ball.z = 10.0f;
    game.ball.height = 0.5f;
    game.ball.velocity_x = -5.0f;
    game.ball.in_flight = 1;
    game.last_touch_team = 0;
    game_update(&game, input, 0.05f);
    assert(game.event == GAME_EVENT_FORTY_FIVE);
    assert(game.ball_team == 1);
    assert(game.ball.x > 44.0f && game.ball.x < 46.0f);
}

static void test_restart_player_stays_inside_pitch_bounds(void)
{
    GameState game;
    GameInput input = {0};
    int i;

    game_init(&game);
    game.ball_team = -1;
    game.ball_player = -1;
    game.ball.x = 91.0f;
    game.ball.z = 0.1f;
    game.ball.height = 0.5f;
    game.ball.velocity_z = -5.0f;
    game.ball.velocity_x = 0.0f;
    game.ball.in_flight = 1;
    game.last_touch_team = 1;

    game_update(&game, input, 0.05f);

    assert(game.event == GAME_EVENT_SIDELINE);
    assert(game.ball_team == 0);
    assert(game.restart_pending);
    assert(game.players[0][game.ball_player].x >= 1.0f &&
           game.players[0][game.ball_player].x <= GAME_PITCH_LENGTH - 1.0f);
    assert(game.players[0][game.ball_player].z >= -1.0f &&
           game.players[0][game.ball_player].z <= GAME_PITCH_WIDTH + 1.0f);

    for (i = 0; i < 4; i++) {
        game_update(&game, input, 0.05f);
    }

    /* the sideline taker waits just outside the line and does not drift */
    assert(game.players[0][game.ball_player].z >= -1.0f &&
           game.players[0][game.ball_player].z <= GAME_PITCH_WIDTH + 1.0f);
}


/* ---- v3 discipline ---- */
static void setup_carrier_near_selected(GameState *game, float x, float z)
{
    GamePlayer *me = &game->players[0][game->selected_player];
    GamePlayer *c = &game->players[1][5];
    me->x = x - 1.5f; me->z = z;
    c->x = x; c->z = z;
    game->ball_team = 1; game->ball_player = 5;
    game->ball.x = x; game->ball.z = z; game->ball.in_flight = 0;
    game->restart_pending = 0; game->restart_type = GAME_RESTART_NONE;
    game->prev_ball_team = 1; game->prev_ball_player = 5;
}

static void test_strike_is_a_straight_red(void)
{
    GameState game;
    GameInput input = {0};
    int i, offender;
    game_init(&game);
    offender = game.selected_player;
    setup_carrier_near_selected(&game, 60.0f, 40.0f);
    input.special = 1;
    game_update(&game, input, 1.0f / 60.0f);
    input.special = 0;
    for (i = 0; i < 40; i++) game_update(&game, input, 1.0f / 60.0f);
    assert(game.players[0][offender].off == 2);
    assert(game.card_type == GAME_CARD_RED);
    assert(game.restart_pending && game.ball_team == 1);
    assert(game_players_on(&game, 0) == 14);
    assert(game.selected_player != offender);
}

static void test_dissent_moves_free_fifty_metres(void)
{
    GameState game;
    GameInput input = {0};
    int i;
    game_init(&game);
    game.dissent_chance = 1.0f;
    setup_carrier_near_selected(&game, 60.0f, 40.0f);
    input.special = 1;
    game_update(&game, input, 1.0f / 60.0f);
    input.special = 0;
    for (i = 0; i < 40; i++) game_update(&game, input, 1.0f / 60.0f);
    assert(game.ball_team == 1 && game.restart_pending);
    assert(fabsf(game.ball.x - 13.0f) < 0.5f);        /* 60 - 50 = 10, capped at the 13m line */
}

/* Find an rng seed whose mistimed tackle is cynical (black card). */
static int black_card_tackle(GameState *game, float x, float z, int preset_yellow)
{
    unsigned int seed;
    for (seed = 1; seed < 20000; seed++) {
        GameInput input = {0};
        game_init(game);
        game->rng = seed;
        game->players[0][game->selected_player].yellow = preset_yellow;
        setup_carrier_near_selected(game, x, z);
        input.tackle = 1;
        game_update(game, input, 1.0f / 60.0f);
        if (game->card_type == GAME_CARD_BLACK || game->card_second_yellow) return 1;
    }
    return 0;
}

static void test_black_card_sin_bin(void)
{
    GameState game;
    GameInput input = {0};
    int offender, t;
    assert(black_card_tackle(&game, 70.0f, 40.0f, 0));
    offender = game.card_player;
    assert(game.card_team == 0);
    assert(game.players[0][offender].off == 1);
    assert(game.players[0][offender].sin_bin > 599.0f);
    assert(game.event == GAME_EVENT_BLACK_CARD);
    assert(game_players_on(&game, 0) == 14);
    for (t = 0; t < 601 * 10; t++) game_update(&game, input, 0.1f);
    assert(game.players[0][offender].off == 0);
    assert(game_players_on(&game, 0) == 15);
}

static void test_black_card_denying_goal_chance_gives_penalty(void)
{
    GameState game;
    /* team 1 attacks x = 0: inside the 20m line, central, outside the large rectangle */
    assert(black_card_tackle(&game, 17.0f, 42.5f, 0));
    assert(game.card_type == GAME_CARD_BLACK);
    assert(game.event == GAME_EVENT_BLACK_PENALTY);
    assert(game.restart_type == GAME_RESTART_PENALTY);
    assert(game.ball_team == 1);
}

static void test_yellow_then_black_is_red(void)
{
    GameState game;
    assert(black_card_tackle(&game, 70.0f, 40.0f, 1));
    assert(game.card_type == GAME_CARD_RED && game.card_second_yellow);
    assert(game.players[0][game.card_player].off == 2);
    assert(game.event == GAME_EVENT_SECOND_YELLOW);
}

static void test_advanced_mark(void)
{
    GameState game;
    GameInput input = {0};
    GamePlayer *me;
    game_init(&game);
    me = &game.players[0][game.selected_player];
    me->x = 125.0f; me->z = 42.0f;
    game.ball_team = -1; game.ball_player = -1;
    game.ball.x = 124.0f; game.ball.z = 42.0f; game.ball.height = 2.0f;
    game.ball.velocity_x = 10.0f; game.ball.velocity_z = 0.0f; game.ball.velocity_y = 0.0f;
    game.ball.in_flight = 1;
    game.kick_clean = 1; game.kick_origin_x = 90.0f; game.kick_origin_z = 42.0f;
    game.last_release_team = 0; game.last_release_player = 4; game.last_touch_team = 0;
    input.high_field = 1;
    game_update(&game, input, 0.05f);
    assert(game.event == GAME_EVENT_ADVANCED_MARK);
    assert(game.restart_pending && game.restart_type == GAME_RESTART_FREE);
    assert(game.ball_team == 0 && game.mark_play_on);
}

static void test_back_pass_to_keeper_is_a_free(void)
{
    GameState game;
    GameInput input = {0};
    GamePlayer *k;
    game_init(&game);
    k = &game.players[0][0];
    k->x = 30.0f; k->z = 42.5f; k->jump_time = 0.7f;
    game.ball_team = -1; game.ball_player = -1;
    game.ball.x = 29.0f; game.ball.z = 42.5f; game.ball.height = 2.0f;
    game.ball.velocity_x = 10.0f; game.ball.velocity_z = 0.0f; game.ball.velocity_y = 0.0f;
    game.ball.in_flight = 1;
    game.kick_clean = 0; game.kick_origin_x = 45.0f; game.kick_origin_z = 42.5f;
    game.last_release_team = 0; game.last_release_player = 5; game.last_touch_team = 0;
    game_update(&game, input, 0.05f);
    assert(game.event == GAME_EVENT_BACK_PASS);
    assert(game.ball_team == 1 && game.restart_pending);
}

static void test_goal_chance_zone(void)
{
    assert(game_goal_chance_zone(0, 125.0f, 42.5f));
    assert(!game_goal_chance_zone(0, 125.0f, 10.0f));     /* within 25m of the sideline */
    assert(game_goal_chance_zone(0, 110.0f, 42.5f));      /* inside the 20m semicircle */
    assert(!game_goal_chance_zone(0, 100.0f, 42.5f));
    assert(game_goal_chance_zone(1, 15.0f, 40.0f));
}

int main(void)
{
    test_initial_state();
    test_point_scoring();
    test_goal_scoring();
    test_four_step_turnover();
    test_player_movement_anim_state();
    test_solo_allows_next_bounce();
    test_consecutive_bounce_is_foul();
    test_team_and_player_selection();
    test_nearest_player_selection_tracks_the_ball();
    test_opponent_can_pick_up_a_loose_ball();
    test_home_player_must_foot_lift_a_ground_ball();
    test_home_ai_performs_ground_foot_pickup();
    test_high_field_catches_a_high_ball();
    test_cpu_opponent_jumps_for_a_high_ball();
    test_cpu_carrier_looks_for_forward_pass_under_pressure();
    test_cpu_takes_goal_opportunity();
    test_cpu_can_take_a_point_attempt();
    test_tackle_wins_possession();
    test_cpu_tackles_home_carrier_after_closing_down();
    test_kick_curve_changes_ball_lateral_path();
    test_kicker_does_not_immediately_reclaim_own_kick();
    test_kick_types_have_distinct_trajectories();
    test_kickout_must_clear_arc_before_pickup();
    test_sideline_out_awards_opponent_kick_in();
    test_opponent_kick_in_awarded_to_home_team();
    test_non_scoring_endline_awards_defender();
    test_restart_player_stays_inside_pitch_bounds();
    test_strike_is_a_straight_red();
    test_dissent_moves_free_fifty_metres();
    test_black_card_sin_bin();
    test_black_card_denying_goal_chance_gives_penalty();
    test_yellow_then_black_is_red();
    test_advanced_mark();
    test_back_pass_to_keeper_is_a_free();
    test_goal_chance_zone();
    puts("Core game tests passed.");
    return 0;
}

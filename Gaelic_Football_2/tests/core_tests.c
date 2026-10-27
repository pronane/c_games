#include "game.h"

#include <assert.h>
#include <stdio.h>

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

    for (i = 0; i < 40; i++) game_update(&game, input, 0.1f);

    assert(!game.has_ball);
    assert(game.fouls == 1);
    assert(game.event == GAME_EVENT_FOUR_STEPS);
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

    assert(game.has_ball);
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
    game.ball.height = 0.18f;
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
    game.ball.height = 0.18f;
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
    assert(game.ball.height >= 0.18f && game.ball.height < 1.05f);

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
    game.ball.height = 0.18f;
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

    game_update(&game, input, 0.05f);

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

    game_update(&game, input, 0.05f);

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
        assert(!game.kickout_in_progress);
        assert(game.ball.x >= arc_x + GAME_KICKOUT_ARC_RADIUS);
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

    assert(game.event == GAME_EVENT_BALL_OUT);
    assert(game.ball_team == 1);
    assert(game.ball_player >= 0 && game.ball_player < GAME_TEAM_SIZE);
    assert(game.restart_pending);
    assert(game.ball.z > GAME_PITCH_WIDTH * 0.5f - 1.0f &&
           game.ball.z < GAME_PITCH_WIDTH * 0.5f + 1.0f);
    assert(game.ball.x > GAME_PITCH_LENGTH - 25.0f &&
           game.ball.x < GAME_PITCH_LENGTH - 15.0f);

    game_update(&game, input, 0.05f);

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
    assert(game.event == GAME_EVENT_BALL_OUT);
    assert(game.ball_team == 0);
    assert(game.restart_pending);
    assert(game.ball.z > GAME_PITCH_WIDTH * 0.5f - 1.0f &&
           game.ball.z < GAME_PITCH_WIDTH * 0.5f + 1.0f);
    assert(game.ball.x > 15.0f && game.ball.x < 25.0f);

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
    game.last_touch_team = 0;

    game_update(&game, input, 0.05f);

    assert(game.event == GAME_EVENT_BALL_OUT);
    assert(game.ball_team == 0);
    assert(game.restart_pending);
    assert(game.ball.x > 0.0f && game.ball.x < 2.0f);
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

    assert(game.event == GAME_EVENT_BALL_OUT);
    assert(game.ball_team == 0);
    assert(game.restart_pending);
    assert(game.players[0][game.ball_player].x >= 1.0f &&
           game.players[0][game.ball_player].x <= GAME_PITCH_LENGTH - 1.0f);
    assert(game.players[0][game.ball_player].z >= 1.0f &&
           game.players[0][game.ball_player].z <= GAME_PITCH_WIDTH - 1.0f);

    for (i = 0; i < 4; i++) {
        game_update(&game, input, 0.05f);
    }

    assert(game.players[0][game.ball_player].z >= 1.0f &&
           game.players[0][game.ball_player].z <= GAME_PITCH_WIDTH - 1.0f);
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
    puts("Core game tests passed.");
    return 0;
}

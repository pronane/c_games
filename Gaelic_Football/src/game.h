#ifndef GAELIC_GAME_H
#define GAELIC_GAME_H

#define GAME_PITCH_LENGTH 140.0f
#define GAME_PITCH_WIDTH 85.0f
#define GAME_GOAL_WIDTH 6.5f
#define GAME_CROSSBAR_HEIGHT 2.5f
#define GAME_KICKOUT_LINE 20.0f
#define GAME_KICKOUT_ARC_RADIUS 12.0f
#define GAME_BALL_GRAVITY 9.8f
#define GAME_TEAM_SIZE 15
#define GAME_TEAM_COUNT 4

typedef enum GameEvent {
    GAME_EVENT_NONE,
    GAME_EVENT_KICKED,
    GAME_EVENT_HANDPASSED,
    GAME_EVENT_SOLOED,
    GAME_EVENT_BOUNCED,
    GAME_EVENT_ILLEGAL_BOUNCE,
    GAME_EVENT_FOUR_STEPS,
    GAME_EVENT_POINT,
    GAME_EVENT_GOAL,
    GAME_EVENT_BALL_OUT,
    GAME_EVENT_TACKLE,
    GAME_EVENT_SHORT_KICKOUT,
    GAME_EVENT_HIGH_FIELD,
    GAME_EVENT_PICKUP
} GameEvent;

typedef struct GameInput {
    float move_x;
    float move_z;
    int kick;
    int kick_high;
    int kick_low;
    int kick_long;
    int high_field;
    int pickup;
    int handpass;
    int solo;
    int bounce;
    int tackle;
    float curve;
} GameInput;

typedef struct GamePlayer {
    float x;
    float z;
    float facing_x;
    float facing_z;
    float movement;
    float jump_time;
} GamePlayer;

typedef struct GameBall {
    float x;
    float z;
    float height;
    float velocity_x;
    float velocity_z;
    float velocity_y;
    float curve;
    int in_flight;
} GameBall;

typedef struct GameState {
    GamePlayer players[2][GAME_TEAM_SIZE];
    int selected_player;
    int home_team;
    int away_team;
    int ball_team;
    int ball_player;
    int team_goals[2];
    int team_points[2];
    float player_x;
    float player_z;
    float facing_x;
    float facing_z;
    float step_time;
    float event_time;
    float pickup_delay;
    float cpu_possession_time;
    float cpu_tackle_time;
    float pickup_time;
    int steps_carried;
    int has_ball;
    int last_was_bounce;
    int last_touch_team;
    int restart_pending;
    int kickout_in_progress;
    int kickout_team;
    int pickup_team;
    int pickup_player;
    int last_release_team;
    int last_release_player;
    int points;
    int goals;
    int fouls;
    GameEvent event;
    GameBall ball;
} GameState;

void game_init(GameState *game);
void game_set_teams(GameState *game, int home_team, int away_team, int starting_player);
void game_select_player(GameState *game, int player_index);
void game_select_next_player(GameState *game, int direction);
void game_select_nearest_player(GameState *game);
void game_update(GameState *game, GameInput input, float delta_time);
const char *game_event_text(GameEvent event);
const char *game_team_name(int team_index);
const char *game_player_role(int player_index);

#endif

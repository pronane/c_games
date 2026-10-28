#ifndef GAELIC_GAME_H
#define GAELIC_GAME_H

#define GAME_PITCH_LENGTH 140.0f
#define GAME_PITCH_WIDTH 85.0f
#define GAME_GOAL_WIDTH 6.5f
#define GAME_CROSSBAR_HEIGHT 2.5f
#define GAME_KICKOUT_LINE 20.0f
#define GAME_KICKOUT_ARC_RADIUS 13.0f   /* players must be 13m from a kick-out / free */
#define GAME_SCORING_ARC 40.0f          /* 2025/26 rules: 40m arc (2 points, kick-outs must pass it) */
#define GAME_LARGE_RECT_DEPTH 13.0f
#define GAME_LARGE_RECT_HALF 9.5f
#define GAME_PENALTY_SPOT 11.0f
#define GAME_BALL_REST 0.11f            /* size-5 ball, ~22cm diameter: centre height when on ground */
#define GAME_STEP_LENGTH 1.9f           /* metres per running step for the 4-step rule */
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
    GAME_EVENT_PICKUP,
    GAME_EVENT_TWO_POINT,
    GAME_EVENT_WIDE,
    GAME_EVENT_FREE,
    GAME_EVENT_FOUL_TACKLE,
    GAME_EVENT_SIDELINE,
    GAME_EVENT_FORTY_FIVE,
    GAME_EVENT_KICKOUT,
    GAME_EVENT_KICKOUT_SHORT,
    GAME_EVENT_KICKOUT_TOUCHED,
    GAME_EVENT_PENALTY,
    GAME_EVENT_PENALTY_SAVED,
    GAME_EVENT_THROW_IN,
    GAME_EVENT_SOLO_AND_GO,
    GAME_EVENT_THREE_V_THREE,
    /* --- v3: discipline and marks --- */
    GAME_EVENT_YELLOW_CARD,
    GAME_EVENT_BLACK_CARD,
    GAME_EVENT_RED_CARD,
    GAME_EVENT_SECOND_YELLOW,
    GAME_EVENT_BLACK_PENALTY,     /* cynical foul denied a goal chance: black + penalty */
    GAME_EVENT_ADVANCED_MARK,
    GAME_EVENT_KICKOUT_MARK,
    GAME_EVENT_DISSENT,           /* free brought forward 50m */
    GAME_EVENT_BACK_PASS,
    GAME_EVENT_SIN_BIN_OVER,
    GAME_EVENT_COUNT
} GameEvent;

/* Timed player actions: the renderer plays the matching clip and the ball is
 * released on the clip's contact frame (see game_set_action_timing). */
typedef enum GameAction {
    GAME_ACT_NONE,
    GAME_ACT_KICK,          /* drop punt in play (running kick)          */
    GAME_ACT_FREE_KICK,     /* deliberate drop punt: frees, 45s, sideline */
    GAME_ACT_KICKOUT,       /* goalkeeper kick-out                        */
    GAME_ACT_GROUND_KICK,   /* penalty: struck off the ground             */
    GAME_ACT_HANDPASS,
    GAME_ACT_SOLO,
    GAME_ACT_BOUNCE,
    GAME_ACT_PICKUP,
    GAME_ACT_TACKLE,
    GAME_ACT_DIVE,
    GAME_ACT_CATCH,
    GAME_ACT_HOOK,          /* special move: swinging punch - straight red   */
    GAME_ACT_HEAD_HIT,      /* special move: head butt - straight red        */
    GAME_ACT_TRIP,          /* cynical trip / pull-down (black card)         */
    GAME_ACT_FALL,          /* fouled player knocked to the ground           */
    GAME_ACT_COUNT
} GameAction;

typedef enum GameRestart {
    GAME_RESTART_NONE,
    GAME_RESTART_KICKOUT,
    GAME_RESTART_FREE,
    GAME_RESTART_SIDELINE,
    GAME_RESTART_FORTY_FIVE,
    GAME_RESTART_PENALTY,
    GAME_RESTART_THROW_IN
} GameRestart;

typedef enum GameSignal {
    GAME_SIGNAL_NONE, GAME_SIGNAL_FREE, GAME_SIGNAL_POINT, GAME_SIGNAL_TWO_POINT,
    GAME_SIGNAL_GOAL, GAME_SIGNAL_WIDE, GAME_SIGNAL_THROW, GAME_SIGNAL_CARD,
    GAME_SIGNAL_MARK
} GameSignal;

typedef enum GameCard { GAME_CARD_NONE, GAME_CARD_YELLOW, GAME_CARD_BLACK, GAME_CARD_RED } GameCard;

typedef enum GameFoul {
    GAME_FOUL_NONE,
    GAME_FOUL_TECHNICAL,    /* hold / push / mistimed tackle: free (3rd = yellow) */
    GAME_FOUL_PULL_DOWN,    /* cynical (rule 5.41): black card                   */
    GAME_FOUL_TRIP,         /* cynical (rule 5.41): black card                   */
    GAME_FOUL_STRIKE        /* hook / head hit: red card, sent off                */
} GameFoul;

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
    int sprint;
    float power;            /* 0..1 kick power (charge) */
    int special;            /* hook / head hit on the carrier (straight red!) */
    int pass_target;        /* v3.2 pass assist: teammate index + 1 (0 = engine picks) */
} GameInput;

typedef struct GamePlayer {
    float x;
    float z;
    float facing_x;
    float facing_z;
    float movement;
    float jump_time;
    int action;             /* GameAction */
    float action_time;
    int action_released;
    float release_dx, release_dz, release_speed, release_lift, release_curve;
    int release_event;
    float tackle_cooldown;
    /* --- v3 discipline --- */
    int yellow, black;      /* cards received */
    int off;                /* 0 on the pitch, 1 sin bin, 2 sent off */
    float sin_bin;          /* real seconds left in the sin bin */
    int fouls_committed;
} GamePlayer;

typedef struct GameOfficial {
    float x, z, facing_x, facing_z, movement;
    int signal;             /* GameSignal */
    float signal_time;
    float signal_dir;       /* +1 / -1 direction of a free */
} GameOfficial;

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
    /* --- 2025/26 rules additions --- */
    int team_two_pointers[2];
    int restart_type;       /* GameRestart while restart_pending */
    float restart_time;
    int kick_clean;         /* ball kicked and untouched since: eligible for 2 pts */
    float kick_origin_x, kick_origin_z;
    int kick_no_two;        /* 45s are worth one point */
    int prev_ball_team, prev_ball_player;
    float protect_time;     /* solo & go: 4m protection */
    int penalty_active, keeper_guess;
    int half;
    int event_team;         /* team the last event favours */
    unsigned int rng;
    float three_v_three_time;
    int enforce_three_v_three;  /* set by the match frontend (off in unit tests) */
    GameOfficial referee;
    /* --- v3: cards, marks, dissent --- */
    int card_type, card_team, card_player, card_second_yellow;  /* card being shown */
    float card_time;        /* referee showing a card: play held until 0 */
    float sin_bin_seconds;  /* real seconds a black card lasts (600 = 10 min) */
    float dissent_chance;   /* per foul free; 0 in unit tests */
    int last_foul_type;     /* GameFoul */
    int from_kickout;       /* ball in flight straight from a kick-out */
    int mark_play_on;       /* free came from a mark: may play on (solo & go) */
    int cards_given[2][4];  /* per team, per GameCard */
    /* --- v3.2 gameplay assists (set by the 3D frontend; off in unit tests) --- */
    int ai_support;         /* AI support runs for the carrier + goal-side marking */
    int assist_target;      /* this frame's pass-assist receiver, -1 none */
    void (*on_release)(struct GameState *game, int team, int player, int action, void *user);
    void *user;
} GameState;

void game_init(GameState *game);
void game_start_half(GameState *game, int half);
void game_set_action_timing(int action, float contact, float duration);
float game_action_duration(int action);
float game_action_contact(int action);
int game_carrier_steps(const GameState *game);
float game_distance_to_goal(int team, float x, float z);
void game_set_teams(GameState *game, int home_team, int away_team, int starting_player);
void game_select_player(GameState *game, int player_index);
void game_select_next_player(GameState *game, int direction);
void game_select_nearest_player(GameState *game);
void game_update(GameState *game, GameInput input, float delta_time);
const char *game_event_text(GameEvent event);
int game_players_on(const GameState *game, int team);
void game_force_foul(GameState *game, int off_team, int off_idx, int foul);  /* scripted scenes */
int game_goal_chance_zone(int attacking_team, float x, float z);
const char *game_team_name(int team_index);
const char *game_player_role(int player_index);

#endif

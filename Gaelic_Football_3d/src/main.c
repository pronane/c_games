/*  Sunday League: Gaelic Football - 3D raylib frontend (raylib 5.5 or 6.x)
 *
 *  Gameplay and rules live in game.c / game.h (the original rules engine,
 *  extended for the 2025/26 rules). This file renders that state with the
 *  skinned GLB players, drives the animation state machine (with cross-fades),
 *  attaches the ball to hand/foot bones and releases kicks on contact frames.
 */
#include "raylib.h"
#include "raymath.h"
#include "game.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>
#if defined(_WIN32)
#define WIN32_LEAN_AND_MEAN
#endif
#include "glmin.h"

/* ---- raylib 5.5 / 6.x compatibility ------------------------------------ */
#if RAYLIB_VERSION_MAJOR >= 6
#define ANIM_FRAMES(a) ((a).keyframeCount)
#define ANIM_POSES(a) ((a).keyframePoses)
#define MODEL_BONES(m) ((m).skeleton.bones)
#define MODEL_BONECOUNT(m) ((m).skeleton.boneCount)
#define ANIM_UPDATE(m, a, f) UpdateModelAnimation((m), (a), (float)(f))
#else
#define ANIM_FRAMES(a) ((a).frameCount)
#define ANIM_POSES(a) ((a).framePoses)
#define MODEL_BONES(m) ((m).bones)
#define MODEL_BONECOUNT(m) ((m).boneCount)
#define ANIM_UPDATE(m, a, f) UpdateModelAnimation((m), (a), (int)(f))
#endif

#define PLAYER_GLB "assets/models/gaelic_player.glb"
#define HL (GAME_PITCH_LENGTH * 0.5f)
#define HW (GAME_PITCH_WIDTH * 0.5f)
#define ANIM_FPS 60.0f
#define HALF_SECONDS 300.0f          /* real seconds per half, shown as 35 min */
#define BALL_R GAME_BALL_REST        /* 0.11 m radius: size-5 ball, ~70 cm round */
#define MAX_BONES 64
#define BLEND_TIME 0.15f
#define SIN_BIN_REAL (600.0f * HALF_SECONDS / 2100.0f)   /* 10 match minutes in real seconds */

/* ---- clips ------------------------------------------------------------- */
enum { C_RUN, C_DROP_KICK, C_CATCH, C_IDLE, C_KICK_RUN, C_HAND_PASS, C_KICK_OUT,
       C_SOLO, C_DIVE_ROLL, C_KEEPER_READY, C_DIVE_HIGH, C_GET_UP, C_RUN_BALL,
       C_DIVE_SAVE, C_PICKUP,
       /* v3 clips */
       C_KICK_PLACE, C_HOOK, C_HEAD_HIT, C_HIT_REACT, C_KNOCKED_DOWN, C_TRIP, C_STUMBLE,
       C_PUSHED, C_TACKLE_REACH, C_CELEBRATE, C_JOG, C_SIDESTEP, C_TOE_LIFT, C_SOLO_LEFT,
       C_KEEPER_HIGH_CATCH, C_KEEPER_SCOOP, C_KEEPER_IDLE, C_COUNT };
static const char *CLIP_NAMES[C_COUNT] = {
    "run", "drop_kick", "catch", "idle", "kick_run", "hand_pass", "kick_out", "solo",
    "dive_roll", "keeper_ready", "dive_high", "get_up", "run_ball", "dive_save", "pickup",
    "kick_place", "hook", "head_hit", "hit_react", "knocked_down", "trip", "stumble",
    "pushed", "tackle_reach", "celebrate_jump", "jog", "sidestep", "toe_lift", "solo_left",
    "keeper_high_catch", "keeper_scoop", "keeper_idle"
};

/* How each game action is played: clip, segment [start,end] (clip seconds),
 * playback rate. Contact frame is detected from the bones at load time. */
/* contactBy: 0 none, 1 kicking foot (frame of peak foot speed = true contact),
 * 2 hand (peak height, passes), 3 hand reach (hook), 4 head reach (head hit) */
typedef struct { int clip; float start, end, rate; int contactBy; } ActionClip;
static ActionClip ACTION_CLIPS[GAME_ACT_COUNT] = {
    [GAME_ACT_NONE]        = { C_IDLE, 0, 0, 1, 0 },
    [GAME_ACT_KICK]        = { C_KICK_RUN, 0.10f, 1.05f, 1.60f, 1 },
    [GAME_ACT_FREE_KICK]   = { C_KICK_PLACE, 0.05f, 1.55f, 1.30f, 1 },   /* plant, swing, follow-through */
    [GAME_ACT_KICKOUT]     = { C_KICK_OUT, 5.00f, 7.20f, 1.45f, 1 },
    [GAME_ACT_GROUND_KICK] = { C_KICK_PLACE, 0.05f, 1.55f, 1.35f, 1 },
    [GAME_ACT_HANDPASS]    = { C_HAND_PASS, 0.05f, 0.85f, 2.00f, 2 },
    [GAME_ACT_SOLO]        = { C_SOLO, 0.00f, 0.50f, 1.45f, 1 },
    [GAME_ACT_BOUNCE]      = { C_RUN_BALL, 0.00f, 0.79f, 2.10f, 0 },
    [GAME_ACT_PICKUP]      = { C_TOE_LIFT, 0.00f, 0.62f, 1.40f, 0 },     /* toe-lift (keepers: scoop) */
    [GAME_ACT_TACKLE]      = { C_TACKLE_REACH, 0.45f, 1.15f, 1.55f, 0 }, /* block / shoulder / push */
    [GAME_ACT_DIVE]        = { C_DIVE_SAVE, 0.30f, 1.80f, 1.40f, 0 },
    [GAME_ACT_CATCH]       = { C_CATCH, 0.90f, 1.60f, 1.50f, 0 },
    [GAME_ACT_HOOK]        = { C_HOOK, 0.00f, 1.29f, 1.25f, 3 },
    [GAME_ACT_HEAD_HIT]    = { C_HEAD_HIT, 0.00f, 0.92f, 1.10f, 4 },
    [GAME_ACT_TRIP]        = { C_TRIP, 0.00f, 0.90f, 1.00f, 0 },
    [GAME_ACT_FALL]        = { C_KNOCKED_DOWN, 0.00f, 1.50f, 1.15f, 0 },
};

static Model model;
static ModelAnimation *anims;
static int animCount;
static int clipIdx[C_COUNT];
static int boneFootL = -1, boneFootR = -1, boneHandL = -1, boneHandR = -1, boneHead = -1;
static int actionFoot[GAME_ACT_COUNT];      /* bone index of the kicking foot */
static float actionContactClip[GAME_ACT_COUNT];
static Vector3 actionContactPos[GAME_ACT_COUNT];   /* model-space contact bone position */
static int bonePelvis = -1;
static int haveModel;
enum { KIT_HOME, KIT_AWAY, KIT_GK_HOME, KIT_GK_AWAY, KIT_REF, KIT_UMP, KIT_COUNT };
static const char *KIT_FILES[KIT_COUNT] = { "home", "away", "gk_home", "gk_away", "referee", "umpire" };
static Texture2D kits[KIT_COUNT];
static ModelAnimation scratch;
static Transform scratchPose[MAX_BONES];
static Transform *scratchPosePtr[1];

/* ---- per-character animation state (cross-fade) -------------------------- */
typedef struct {
    int clip; float t;             /* current clip + clip time (s) */
    int prevClip; float prevT;
    float blend;                   /* 0..1, 1 = fully current */
    Transform pose[MAX_BONES];     /* last rendered pose (model space) */
    float lastX, lastZ, speed;     /* measured ground speed */
    int lastAction; float runPhase;
} AnimState;

#define N_CHAR (2 * GAME_TEAM_SIZE + 5)   /* players, referee, 4 umpires */
static AnimState as[N_CHAR];

static GameState game;
static int camMode = 0;
static const char *CAM_NAMES[] = { "Broadcast (side)", "TV close (side)", "Chase", "Behind goal", "Tactical", "Player close-up" };
#define CAM_COUNT 6
static int autoSolo = 1;
static float charge = -1.0f;
static int chargeLow = 0;
static int paused = 0;
static float clockT = 0.0f;
static int fullTime = 0;
static int demo = 0;
static int releaseFlash = 0;     /* frames since the last release (for screenshots) */
static int lastReleaseAction = 0;
static int celebTeam = -1, celebIdx = -1; static float celebT = 0;
static int showControls = 0;
static int forceCpuSkin = 0;
static int cmdDemo = 0;          /* --demo: CPU plays the human team in matches */
static int training = 0;         /* training mode (free play, keeper only) */
static int trainPoints = 0, trainGoals = 0, trainShots = 0, trainWides = 0;
/* profiling (F3) */
static double tSkin, tUpdate, tWorld, tHud, tSwap, tFrame;
static double pSkin, pUpdate, pWorld, pHud, pSwap, pFrame;  /* smoothed, ms */
static int showPerf = 0;
static int benchSkip = 0;        /* --bench-skip N: 1 stadium, 2 characters (profiling) */
static int skinnedThisFrame = 0;

static Vector3 W(float x, float y, float z) { return (Vector3){ x - HL, y, z - HW }; }

#include "stadium.c"
#include "sfx.c"
#include "pad.c"

/* ------------------------------------------------------------------------ */
static int findBone(const char *name)
{
    for (int i = 0; i < MODEL_BONECOUNT(model); i++)
        if (strcmp(MODEL_BONES(model)[i].name, name) == 0) return i;
    return -1;
}

static Transform *clipPose(int clip, float t)
{
    ModelAnimation *a = &anims[clipIdx[clip]];
    int n = ANIM_FRAMES(*a);
    int f = (int)(t * ANIM_FPS);
    if (f < 0) f = 0;
    if (f >= n) f = n - 1;
    return ANIM_POSES(*a)[f];
}

static float clipLen(int clip) { return (float)ANIM_FRAMES(anims[clipIdx[clip]]) / ANIM_FPS; }

/* Find the contact moment inside an action's segment from the bones:
 * kicks - the frame where the kicking foot moves fastest (true contact),
 * passes - the hand's highest point, hook - hand furthest from the pelvis,
 * head hit - head furthest forward. */
static void detectContacts(void)
{
    const float df = 1.0f / ANIM_FPS;
    for (int a = 1; a < GAME_ACT_COUNT; a++) {
        ActionClip *ac = &ACTION_CLIPS[a];
        float best = -1.0f, bestT = ac->start;
        int bestBone = boneFootR;
        if (!ac->contactBy) continue;
        for (float t = ac->start; t <= ac->end - df; t += df) {
            Transform *p = clipPose(ac->clip, t), *q = clipPose(ac->clip, t + df);
            int cands[2];
            if (ac->contactBy == 1) { cands[0] = boneFootL; cands[1] = boneFootR; }
            else if (ac->contactBy == 4) { cands[0] = cands[1] = boneHead; }
            else { cands[0] = boneHandL; cands[1] = boneHandR; }
            for (int k = 0; k < 2; k++) {
                Vector3 b = p[cands[k]].translation, pel = p[bonePelvis].translation;
                float v;
                if (ac->contactBy == 1) v = Vector3Distance(b, q[cands[k]].translation) / df;
                else if (ac->contactBy == 2) v = b.y;
                else v = sqrtf((b.x - pel.x) * (b.x - pel.x) + (b.z - pel.z) * (b.z - pel.z));
                if (v > best) { best = v; bestT = t; bestBone = cands[k]; }
            }
        }
        actionContactClip[a] = ac->contactBy == 2 ? bestT - 2.0f / ANIM_FPS : bestT;
        actionFoot[a] = bestBone;
        actionContactPos[a] = clipPose(ac->clip, actionContactClip[a])[bestBone].translation;
        game_set_action_timing(a, (actionContactClip[a] - ac->start) / ac->rate,
                               (ac->end - ac->start) / ac->rate);
        TraceLog(LOG_INFO, "GAME: action %d clip '%s' contact at %.2fs (bone %s, metric %.2f)", a,
                 CLIP_NAMES[ac->clip], actionContactClip[a], MODEL_BONES(model)[bestBone].name, best);
    }
    for (int a = 1; a < GAME_ACT_COUNT; a++) {
        ActionClip *ac = &ACTION_CLIPS[a];
        if (!ac->contactBy) game_set_action_timing(a, 0.0f, (ac->end - ac->start) / ac->rate);
    }
}

/* ---- choose clip for a player from the game state ---------------------- */
static void desiredClip(int team, int idx, const GamePlayer *p, AnimState *s, float dt, int *clip, float *t)
{
    int carrying = game.ball_team == team && game.ball_player == idx;
    int keeper = idx == 0;
    if (p->action != GAME_ACT_NONE) {
        ActionClip *ac = &ACTION_CLIPS[p->action];
        *clip = ac->clip;
        if (p->action == GAME_ACT_PICKUP && keeper) *clip = C_PICKUP;    /* keeper scoops it up */
        if (p->action == GAME_ACT_PICKUP && keeper) { *t = fminf(0.25f + p->action_time * 2.2f, 1.25f); return; }
        *t = fminf(ac->start + p->action_time * ac->rate, ac->end);
        return;
    }
    if (p->jump_time > 0.0f) {                  /* high fielding: leap, arms extended */
        *clip = C_CATCH;
        *t = 0.35f + (0.75f - p->jump_time) * 1.15f;
        return;
    }
    if (celebT > 0 && team == celebTeam && idx == celebIdx && !carrying) {
        *clip = C_CELEBRATE; *t = fminf(2.6f - celebT, clipLen(C_CELEBRATE) - 0.02f);
        return;
    }
    if (s->speed > 0.6f) {
        if (carrying) {
            *clip = C_RUN_BALL;
            s->runPhase += dt * fminf(s->speed / 3.1f, 2.5f);
            *t = fmodf(s->runPhase, clipLen(C_RUN_BALL));
        } else if (s->speed < 3.4f) {
            *clip = C_JOG;
            s->runPhase += dt * Clamp(s->speed / 2.6f, 0.6f, 1.5f);
            *t = fmodf(s->runPhase, clipLen(C_JOG));
        } else {
            *clip = C_RUN;
            s->runPhase += dt * Clamp(s->speed / 4.6f, 0.7f, 2.0f);
            *t = fmodf(s->runPhase, clipLen(C_RUN));
        }
        return;
    }
    s->runPhase += dt;
    if (carrying) { *clip = C_KEEPER_READY; *t = 0.0f; return; }   /* ball cradled out front */
    *clip = keeper ? C_KEEPER_IDLE : C_IDLE;
    *t = fmodf(s->runPhase, clipLen(*clip));
}

/* Blend and upload the pose for one character, keeping a copy for bone queries. */
static void poseCharacter(AnimState *s, int clip, float t, float dt)
{
    int nb = MODEL_BONECOUNT(model);
    if (clip != s->clip) {
        s->prevClip = s->clip; s->prevT = s->t; s->blend = 0.0f;
        s->clip = clip;
    }
    s->t = t;
    if (s->blend < 1.0f) s->blend = fminf(1.0f, s->blend + dt / BLEND_TIME);
    Transform *cur = clipPose(clip, t);
    if (s->blend < 1.0f && s->prevClip >= 0) {
        Transform *prev = clipPose(s->prevClip, s->prevT);
        float w = s->blend * s->blend * (3.0f - 2.0f * s->blend);
        for (int b = 0; b < nb; b++) {
            scratchPose[b].translation = Vector3Lerp(prev[b].translation, cur[b].translation, w);
            scratchPose[b].rotation = QuaternionSlerp(prev[b].rotation, cur[b].rotation, w);
            scratchPose[b].scale = Vector3Lerp(prev[b].scale, cur[b].scale, w);
        }
    } else {
        memcpy(scratchPose, cur, sizeof(Transform) * nb);
    }
    memcpy(s->pose, scratchPose, sizeof(Transform) * nb);
    double t0 = GetTime();
#if RAYLIB_VERSION_MAJOR < 6
    if (gpuSkin) UpdateModelAnimationBones(model, scratch, 0);   /* 52 matrices; vertices skinned on the GPU */
    else
#endif
    ANIM_UPDATE(model, scratch, 0);                               /* CPU skinning + VBO re-upload */
    tSkin += GetTime() - t0;
    skinnedThisFrame++;
}

static float yawOf(float fx, float fz) { return (fx * fx + fz * fz < 1e-4f) ? 0.0f : atan2f(fx, fz); }

/* World position of a bone in a character's last pose. */
static Vector3 boneWorld(const AnimState *s, int bone, float x, float z, float yaw)
{
    Vector3 p = Vector3RotateByAxisAngle(s->pose[bone].translation, (Vector3){ 0, 1, 0 }, yaw);
    return Vector3Add(W(x, 0, z), p);
}

static void drawCharacter(AnimState *s, float x, float z, float yaw, int kit, float dt, int clip, float t)
{
    if (!haveModel) {
        DrawCapsule(W(x, 0.3f, z), W(x, 1.5f, z), 0.3f, 8, 4, kit == KIT_HOME ? BLUE : RED);
        return;
    }
    poseCharacter(s, clip, t, dt);
    model.materials[model.meshMaterial[0]].maps[MATERIAL_MAP_DIFFUSE].texture = kits[kit];
    DrawModelEx(model, W(x, 0, z), (Vector3){ 0, 1, 0 }, yaw * RAD2DEG, (Vector3){ 1, 1, 1 }, WHITE);
    if (haveLit) drawPlanarShadow(&model, W(x, 0, z), yaw * RAD2DEG);
    else DrawCylinder(W(x, 0.01f, z), 0.42f, 0.42f, 0.005f, 12, (Color){ 0, 0, 0, 70 });
}

/* ---- ball ---------------------------------------------------------------- */
static Vector3 ballDrawPos;

static Vector3 handsMid(const AnimState *s, const GamePlayer *p)
{
    float yaw = yawOf(p->facing_x, p->facing_z);
    Vector3 l = boneWorld(s, boneHandL, p->x, p->z, yaw), r = boneWorld(s, boneHandR, p->x, p->z, yaw);
    Vector3 m = Vector3Lerp(l, r, 0.5f);
    Vector3 f = { sinf(yaw), 0, cosf(yaw) };
    return Vector3Add(m, Vector3Scale(f, 0.06f));
}

static Vector3 carriedBall(int team, int idx)
{
    const GamePlayer *p = &game.players[team][idx];
    const AnimState *s = &as[team * GAME_TEAM_SIZE + idx];
    float yaw = yawOf(p->facing_x, p->facing_z);
    Vector3 f = { sinf(yaw), 0, cosf(yaw) };
    Vector3 hands = handsMid(s, p);
    Vector3 handR = Vector3Add(boneWorld(s, boneHandR, p->x, p->z, yaw), Vector3Add(Vector3Scale(f, 0.05f), (Vector3){ 0, 0.06f, 0 }));
    Vector3 hold = s->clip == C_RUN_BALL ? handR : hands;      /* one-arm carry when running */
    float u;
    switch (p->action) {
    case GAME_ACT_SOLO: {          /* drop to the foot, toe-tap back to the hands */
        float d = game_action_duration(GAME_ACT_SOLO);
        Vector3 foot = boneWorld(s, actionFoot[GAME_ACT_SOLO], p->x, p->z, yaw);
        foot = Vector3Add(foot, Vector3Add(Vector3Scale(f, 0.12f), (Vector3){ 0, BALL_R, 0 }));
        u = p->action_time / d;
        if (u < 0.45f) return Vector3Lerp(hands, foot, u / 0.45f);
        if (u < 0.55f) return foot;
        return Vector3Lerp(foot, hands, (u - 0.55f) / 0.45f);
    }
    case GAME_ACT_BOUNCE: {        /* thrown down just ahead, returns to the chest */
        float d = game_action_duration(GAME_ACT_BOUNCE);
        Vector3 ground = Vector3Add(W(p->x, BALL_R, p->z), Vector3Scale(f, 0.9f));
        u = p->action_time / d;
        if (u < 0.4f) return Vector3Lerp(hold, ground, (u / 0.4f) * (u / 0.4f));
        return Vector3Lerp(ground, hands, sqrtf((u - 0.4f) / 0.6f));
    }
    case GAME_ACT_FREE_KICK: case GAME_ACT_KICKOUT: case GAME_ACT_GROUND_KICK: {
        /* placed ball: sits where the kicking foot meets it on the contact frame */
        Vector3 c = Vector3RotateByAxisAngle(actionContactPos[p->action], (Vector3){ 0, 1, 0 }, yaw);
        return Vector3Add(W(p->x, BALL_R, p->z), (Vector3){ c.x + f.x * 0.08f, 0, c.z + f.z * 0.08f });
    }
    case GAME_ACT_KICK: {
        /* drop punt: held, then dropped from the hands onto the kicking foot */
        ActionClip *ac = &ACTION_CLIPS[p->action];
        float contact = (actionContactClip[p->action] - ac->start) / ac->rate;
        float dropT = 0.22f;
        Vector3 foot = Vector3Add(boneWorld(s, actionFoot[p->action], p->x, p->z, yaw), Vector3Add(Vector3Scale(f, 0.1f), (Vector3){ 0, 0.08f, 0 }));
        if (p->action_time < contact - dropT) return hands;
        u = Clamp((p->action_time - (contact - dropT)) / dropT, 0.0f, 1.0f);
        return Vector3Lerp(hands, foot, u * u);
    }
    case GAME_ACT_HANDPASS:
        return Vector3Add(boneWorld(s, boneHandL, p->x, p->z, yaw), Vector3Scale(f, 0.08f));
    default:
        return hold;
    }
}

/* Called by the rules engine on the contact frame: start the flight from the bone. */
static void onRelease(GameState *g, int team, int idx, int action, void *user)
{
    (void)user;
    GamePlayer *p = &g->players[team][idx];
    AnimState *s = &as[team * GAME_TEAM_SIZE + idx];
    float yaw = yawOf(p->facing_x, p->facing_z);
    Vector3 f = { sinf(yaw), 0, cosf(yaw) };
    Vector3 at;
    if (!haveModel) return;
    if (action == GAME_ACT_HANDPASS) at = boneWorld(s, boneHandR, p->x, p->z, yaw);
    else if (action == GAME_ACT_FREE_KICK || action == GAME_ACT_KICKOUT || action == GAME_ACT_GROUND_KICK) at = carriedBall(team, idx);
    else at = Vector3Add(boneWorld(s, actionFoot[action] >= 0 ? actionFoot[action] : boneFootR, p->x, p->z, yaw), Vector3Scale(f, 0.15f));
    g->ball.x = at.x + HL;
    g->ball.z = at.z + HW;
    g->ball.height = fmaxf(at.y, BALL_R);
    releaseFlash = 0;
    lastReleaseAction = action;
    sfxPlay(action == GAME_ACT_HANDPASS ? SND_HANDPASS : SND_KICK, action == GAME_ACT_HANDPASS ? 0.5f : 0.8f);
    if (getenv("GF_DEBUG")) fprintf(stderr, "release t%d p%d act %d restart %d\n", team, idx, action, g->restart_type);
}

/* ---- pitch overlays (restart helpers; the markings are baked into the grass) ---- */
static void drawArc(float gx, float r, float maxDeg, float width, Color c)
{
    float s = gx < HL ? 1.0f : -1.0f;
    for (float a = -maxDeg; a < maxDeg; a += 2.0f) {
        float a0 = a * DEG2RAD, a1 = (a + 2.0f) * DEG2RAD;
        Vector3 p0 = W(gx + s * r * cosf(a0), 0.03f, HW + r * sinf(a0));
        Vector3 p1 = W(gx + s * r * cosf(a1), 0.03f, HW + r * sinf(a1));
        DrawCylinderEx(p0, p1, width, width, 3, c);
    }
}

/* ---- officials --------------------------------------------------------- */
static Color cardColor(int c) { return c == GAME_CARD_YELLOW ? (Color){ 250, 215, 20, 255 } : c == GAME_CARD_RED ? (Color){ 220, 20, 30, 255 } : (Color){ 15, 15, 15, 255 }; }

static void drawOfficials(float dt)
{
    GameOfficial *r = &game.referee;
    AnimState *rs = &as[2 * GAME_TEAM_SIZE];
    float ryaw = yawOf(r->facing_x, r->facing_z);
    int clip = C_IDLE; float t = fmodf(GetTime(), clipLen(C_IDLE));
    int showingCard = r->signal == GAME_SIGNAL_CARD && game.card_time > 0.0f;
    rs->speed = Lerp(rs->speed, r->movement * 7.0f, 0.2f);
    if (showingCard && rs->speed < 1.0f) {
        clip = C_CATCH; t = 0.75f;                                   /* card held high */
    } else if (r->signal == GAME_SIGNAL_POINT || r->signal == GAME_SIGNAL_TWO_POINT || r->signal == GAME_SIGNAL_GOAL ||
               r->signal == GAME_SIGNAL_THROW || r->signal == GAME_SIGNAL_MARK) {
        clip = C_CATCH; t = 0.75f;                                   /* arm(s) raised */
    } else if (r->signal == GAME_SIGNAL_FREE || r->signal == GAME_SIGNAL_WIDE) {
        clip = C_HAND_PASS; t = 0.40f;                               /* arms out toward the free */
        ryaw = r->signal_dir > 0 ? PI / 2 : -PI / 2;
    } else if (rs->speed > 0.6f) {
        clip = rs->speed < 3.4f ? C_JOG : C_RUN;
        rs->runPhase += dt * Clamp(rs->speed / (clip == C_JOG ? 2.6f : 4.6f), 0.6f, 1.8f);
        t = fmodf(rs->runPhase, clipLen(clip));
    }
    drawCharacter(rs, r->x, r->z, ryaw, KIT_REF, dt, clip, t);
    if (showingCard && haveModel) {
        Vector3 h = boneWorld(rs, boneHandR, r->x, r->z, ryaw);
        Vector3 c = Vector3Add(h, (Vector3){ 0, 0.12f, 0 });
        Vector3 f = { sinf(ryaw), 0, cosf(ryaw) };
        DrawCube(Vector3Add(c, Vector3Scale(f, 0.03f)), 0.075f + fabsf(f.z) * 0.02f, 0.11f, 0.075f + fabsf(f.x) * 0.02f, cardColor(game.card_type));
    }

    /* umpires in white coats beside each post; flags after a score at their end */
    for (int u = 0; u < 4; u++) {
        int end = u / 2;                 /* 0: x=0 goal (home defends), 1: x=140 */
        float gx = end ? GAME_PITCH_LENGTH + 0.8f : -0.8f;
        float z = HW + (u % 2 ? 1 : -1) * (GAME_GOAL_WIDTH * 0.5f + 1.3f);
        float yaw = end ? -PI / 2 : PI / 2;
        AnimState *us = &as[2 * GAME_TEAM_SIZE + 1 + u];
        int scoredHere = game.event_time > 0.0f &&
            (game.event == GAME_EVENT_POINT || game.event == GAME_EVENT_TWO_POINT || game.event == GAME_EVENT_GOAL) &&
            ((game.event_team == 0) == (end == 1));
        Color flag = game.event == GAME_EVENT_GOAL ? GREEN : game.event == GAME_EVENT_TWO_POINT ? ORANGE : RAYWHITE;
        int wave = scoredHere && (game.event != GAME_EVENT_GOAL || u % 2 == 0);
        drawCharacter(us, gx, z, yaw, KIT_UMP, dt, wave ? C_CATCH : C_IDLE, wave ? 0.70f + 0.06f * sinf((float)GetTime() * 9) : fmodf((float)GetTime() + u, clipLen(C_IDLE)));
        if (haveModel) {
            Vector3 h = boneWorld(us, boneHandR, gx, z, yaw);
            Vector3 top = Vector3Add(h, wave ? (Vector3){ 0, 0.9f, 0 } : (Vector3){ 0, -0.6f, 0.0f });
            DrawCylinderEx(h, top, 0.015f, 0.015f, 4, DARKBROWN);
            if (wave) {
                Vector3 c = Vector3Add(top, (Vector3){ 0, -0.2f, 0.25f * sinf((float)GetTime() * 9) });
                DrawCube(c, 0.04f, 0.35f, 0.5f, flag);
            }
        }
    }
}

/* ---- input ----------------------------------------------------------------- */
/* Screen-relative stick/keys -> pitch direction for the current camera. */
static Vector2 camRelative(float fwd, float right)
{
    switch (camMode) {
    case 2: return (Vector2){ fwd, right };                     /* chase: forward = +x */
    case 3: { float s = game.ball.x > HL ? -1.0f : 1.0f; return (Vector2){ fwd * s, right * s }; }
    default: {   /* side cameras look toward -z, rotated by the right-stick orbit */
        float c = cosf(camOrbit), sn = sinf(camOrbit);
        return (Vector2){ right * c - fwd * sn, -right * sn - fwd * c };
    }
    }
}

static void aimAtGoal(GamePlayer *p)
{
    float gx = GAME_PITCH_LENGTH, dx = gx - p->x, dz = HW - p->z, d = sqrtf(dx * dx + dz * dz);
    if (d > 0.01f) { p->facing_x = dx / d; p->facing_z = dz / d; game.facing_x = p->facing_x; game.facing_z = p->facing_z; }
}

/* ---- v3.2: player switching, pass assist, movement feel -------------------- */
static float switchHold = 0;      /* after a manual switch the auto-switch waits */
static float switchCool = 9;      /* time since the last auto switch */
static float switchFlash = 0;     /* ring pulse after any switch */
static int lastBT = -2, lastBP = -2, lastFlight = -1;
static float manualT = 9; static int manualStep = 0;
static int assistHand = -1, assistKick = -1;    /* shown as rings */
static Vector2 mvSmooth = { 0, 0 }; static int mvSel = -1; static float sprintRamp = 0;
static int autoSwitchOn = 1;
static int passIntent = -1; static float passIntentT = 9;   /* the assisted pass's receiver */

static void landingPoint(float *x, float *z, float *t)
{
    float vy = game.ball.velocity_y, h = fmaxf(game.ball.height - GAME_BALL_REST, 0.0f);
    float tt = (vy + sqrtf(vy * vy + 2.0f * GAME_BALL_GRAVITY * h)) / GAME_BALL_GRAVITY;
    tt = Clamp(tt, 0.0f, 3.0f);
    *x = Clamp(game.ball.x + game.ball.velocity_x * tt, 1.0f, GAME_PITCH_LENGTH - 1.0f);
    *z = Clamp(game.ball.z + game.ball.velocity_z * tt, 1.0f, GAME_PITCH_WIDTH - 1.0f);
    if (t) *t = tt;
}
/* where a dropping ball comes down to catching height (~2 m); the landing spot if it never gets that high */
static void catchPoint(float *x, float *z, float *t)
{
    float vy = game.ball.velocity_y, h = game.ball.height - 2.0f, disc = vy * vy + 2.0f * GAME_BALL_GRAVITY * h;
    if (disc < 0.0f || (game.ball.height < 2.0f && vy < 0.0f)) { landingPoint(x, z, t); return; }
    float tt = Clamp((vy + sqrtf(disc)) / GAME_BALL_GRAVITY, 0.0f, 3.0f);
    *x = Clamp(game.ball.x + game.ball.velocity_x * tt, 1.0f, GAME_PITCH_LENGTH - 1.0f);
    *z = Clamp(game.ball.z + game.ball.velocity_z * tt, 1.0f, GAME_PITCH_WIDTH - 1.0f);
    if (t) *t = tt;
}
/* where play is: the carrier (either team), the landing spot of a ball in the air, or the ball */
static void playPoint(float *x, float *z)
{
    if (game.ball_team >= 0 && game.ball_player >= 0) {
        GamePlayer *c = &game.players[game.ball_team][game.ball_player];
        *x = c->x; *z = c->z;
    } else if (game.ball.in_flight) landingPoint(x, z, NULL);
    else { *x = game.ball.x; *z = game.ball.z; }
}
static float distTo(int i, float x, float z) { GamePlayer *p = &game.players[0][i]; return sqrtf((p->x - x) * (p->x - x) + (p->z - z) * (p->z - z)); }
static void doSelect(int i)
{
    if (i < 0 || i == game.selected_player || game.players[0][i].off) return;
    game_select_player(&game, i);
    switchFlash = 0.7f;
}
/* the best home player for where play is: goal-side of an opposing carrier, or first to a loose / dropping ball */
static int bestSwitchTarget(float *outScore)
{
    float tx, tz, tl = 0;
    playPoint(&tx, &tz);
    if (game.ball_team < 0 && game.ball.in_flight) catchPoint(&tx, &tz, &tl);
    const float ownGoal = 0.0f;           /* home always defends x = 0 (attacks +x) */
    int justKicked = game.ball_team < 0 && game.ball.in_flight && game.last_release_team == 0;
    int best = -1; float bs = 1e9f;
    for (int i = 0; i < GAME_TEAM_SIZE; i++) {
        GamePlayer *p = &game.players[0][i];
        if (p->off) continue;
        if (i == 0 && fabsf(tx - ownGoal) > 22.0f) continue;               /* keeper only near his goal */
        if (justKicked && i == game.last_release_player) continue;          /* not the kicker */
        float s;
        if (game.ball_team == 1) {           /* a point 2 m goal-side of the carrier */
            float gx = ownGoal - tx, gz = HW - tz, gl = fmaxf(0.01f, sqrtf(gx * gx + gz * gz));
            float px = tx + gx / gl * 2.0f, pz = tz + gz / gl * 2.0f;
            s = distTo(i, px, pz);
            if ((p->x - tx) * gx + (p->z - tz) * gz < 0) s += 4.0f;            /* beaten (wrong side): less useful */
        } else {
            s = distTo(i, tx, tz) / 9.0f - tl;                         /* seconds late to the ball */
            s = fmaxf(s, 0.0f) * 9.0f + distTo(i, tx, tz) * 0.15f;
        }
        if (s < bs) { bs = s; best = i; }
    }
    if (outScore) *outScore = bs;
    return best;
}
static float switchScoreOf(int i)
{
    /* the same score as bestSwitchTarget for one player (for hysteresis) */
    float keep = 0; int b = bestSwitchTarget(&keep);
    if (b == i) return keep;
    GamePlayer *p = &game.players[0][i];
    if (p->off) return 1e9f;
    float tx, tz, tl = 0; playPoint(&tx, &tz);
    if (game.ball_team < 0 && game.ball.in_flight) catchPoint(&tx, &tz, &tl);
    if (game.ball_team == 1) return distTo(i, tx, tz) + 2.0f;
    return fmaxf(distTo(i, tx, tz) / 9.0f - tl, 0.0f) * 9.0f + distTo(i, tx, tz) * 0.15f;
}
/* FIFA-style auto switching: instant to your carrier; on a turnover or a new
 * opposing carrier, to the defender best placed; for a loose or dropping ball,
 * to whoever gets there first.  A manual switch (L1/Tab) holds for 2 s. */
static void autoSwitch(float dt)
{
    switchHold -= dt; switchCool += dt; manualT += dt; passIntentT += dt;
    int bt = game.ball_team, bp = game.ball_player, fl = game.ball.in_flight;
    int changed = bt != lastBT || bp != lastBP || fl != lastFlight;
    lastBT = bt; lastBP = bp; lastFlight = fl;
    if (!autoSwitchOn || game.card_time > 0) return;
    if (bt == 0 && bp >= 0) { if (bp != game.selected_player) doSelect(bp); return; }
    if (game.restart_pending && bt != 1) return;
    if (bt >= 0 && passIntentT > 1.0f) passIntent = -1;
    if (bt < 0 && fl && game.last_release_team == 0 && passIntent >= 0 && passIntentT < 3.0f && !game.players[0][passIntent].off) {
        if (passIntent != game.selected_player) { doSelect(passIntent); switchCool = 0; }   /* you become the intended receiver */
        return;
    }
    if (switchHold > 0) return;
    float bs; int cand = bestSwitchTarget(&bs);
    if (cand < 0 || cand == game.selected_player) return;
    if (game.pickup_team == 0 && game.pickup_player == game.selected_player) return;
    if (game.players[0][game.selected_player].action == GAME_ACT_TACKLE) return;
    float cur = switchScoreOf(game.selected_player);
    float margin = bt == 1 ? 5.0f : 3.0f;
    if (changed || (switchCool > 0.8f && cur - bs > margin)) { doSelect(cand); switchCool = 0; }
}
/* L1 / Tab: nearest to play, pressing again quickly walks through the next nearest */
static void manualSwitch(void)
{
    if (game.has_ball) return;
    float tx, tz; playPoint(&tx, &tz);
    int order[GAME_TEAM_SIZE], n = 0;
    for (int i = 1; i < GAME_TEAM_SIZE; i++) if (!game.players[0][i].off) order[n++] = i;
    for (int a = 1; a < n; a++) for (int b = a; b > 0 && distTo(order[b], tx, tz) < distTo(order[b - 1], tx, tz); b--) { int t = order[b]; order[b] = order[b - 1]; order[b - 1] = t; }
    if (n == 0) return;
    static int snap[GAME_TEAM_SIZE], snapN = 0;      /* quick repeat presses walk a fixed list */
    if (manualT < 1.2f && snapN > 0) manualStep++;
    else { memcpy(snap, order, sizeof order); snapN = n < 4 ? n : 4; manualStep = order[0] == game.selected_player ? 1 : 0; }
    int pick = snap[manualStep % snapN];
    if (pick == game.selected_player) pick = snap[++manualStep % snapN];
    doSelect(pick);
    manualT = 0; switchHold = 2.0f;
}

/* pass assist: the best team-mate in the aim direction (stick, or facing) */
static int assistTarget(int kick, float ax, float az)
{
    GamePlayer *me = &game.players[0][game.selected_player];
    float l = sqrtf(ax * ax + az * az);
    if (l < 1e-3f) return -1;
    ax /= l; az /= l;
    int best = -1; float bs = -1e9f;
    for (int m = 1; m < GAME_TEAM_SIZE; m++) {
        GamePlayer *o = &game.players[0][m];
        if (o->off || m == game.selected_player) continue;
        float dx = o->x - me->x, dz = o->z - me->z, d = sqrtf(dx * dx + dz * dz);
        if (kick ? (d < 10.0f || d > 55.0f) : (d < 2.5f || d > 22.0f)) continue;
        float c = (dx * ax + dz * az) / d;
        if (c < (kick ? 0.9f : 0.5f)) continue;
        float nd = 1e9f;
        for (int k = 0; k < GAME_TEAM_SIZE; k++) {
            GamePlayer *e = &game.players[1][k];
            if (e->off) continue;
            nd = fminf(nd, sqrtf((e->x - o->x) * (e->x - o->x) + (e->z - o->z) * (e->z - o->z)));
        }
        float s = c * 14.0f - d * (kick ? 0.06f : 0.22f) + fminf(nd, 8.0f) * 0.45f;
        if (s > bs) { bs = s; best = m; }
    }
    return best;
}
/* kick power that carries the ball about d metres (engine: speed 20+14p, lift 3.5+5p) */
static float powerForDistance(float d)
{
    float lo = 0, hi = 1;
    for (int i = 0; i < 20; i++) {
        float p = (lo + hi) * 0.5f, sp = 20 + 14 * p, li = 3.5f + 5 * p;
        if (sp * (2.0f * li / GAME_BALL_GRAVITY) < d) lo = p; else hi = p;
    }
    return (lo + hi) * 0.5f;
}
static float wrapAngle(float a) { while (a > PI) a -= 2 * PI; while (a < -PI) a += 2 * PI; return a; }
/* acceleration / turning curve: quick to start, a plant before a hard cut, slower turns at speed */
static Vector2 smoothMove(Vector2 cur, Vector2 tgt, float dt)
{
    float tl = sqrtf(tgt.x * tgt.x + tgt.y * tgt.y), cl = sqrtf(cur.x * cur.x + cur.y * cur.y);
    if (tl < 0.05f) {
        cl = fmaxf(0.0f, cl - dt * 7.0f);
        return cl > 0.0f ? Vector2Scale(Vector2Normalize(cur), cl) : (Vector2){ 0, 0 };
    }
    if (cl < 0.08f) return Vector2Scale(Vector2Normalize(tgt), fminf(tl, cl + dt * 5.0f));
    float ca = atan2f(cur.y, cur.x), ta = atan2f(tgt.y, tgt.x), da = wrapAngle(ta - ca);
    float rate = Lerp(16.0f, 6.5f, Clamp(cl, 0, 1));                    /* rad/s */
    if (fabsf(da) > 2.3f && cl > 0.45f) cl -= dt * 6.0f;                  /* plant and turn */
    else {
        ca += Clamp(da, -rate * dt, rate * dt);
        cl += Clamp(tl - cl, -dt * 6.0f, dt * 3.5f);
    }
    return (Vector2){ cosf(ca) * cl, sinf(ca) * cl };
}

static GameInput readInput(float dt)
{
    GameInput in = { 0 };
    float fwd = 0, right = 0;
    if (IsKeyDown(KEY_W) || IsKeyDown(KEY_UP)) fwd += 1;
    if (IsKeyDown(KEY_S) || IsKeyDown(KEY_DOWN)) fwd -= 1;
    if (IsKeyDown(KEY_A) || IsKeyDown(KEY_LEFT)) right -= 1;
    if (IsKeyDown(KEY_D) || IsKeyDown(KEY_RIGHT)) right += 1;
    fwd -= padAxis(GAMEPAD_AXIS_LEFT_Y);
    right += padAxis(GAMEPAD_AXIS_LEFT_X);
    float len = sqrtf(fwd * fwd + right * right);
    if (len > 1.0f) { fwd /= len; right /= len; }
    Vector2 m = camRelative(fwd, right);
    Vector2 raw = m;                                   /* the stick as pushed (aim) */
    in.sprint = IsKeyDown(KEY_LEFT_SHIFT) || IsKeyDown(KEY_RIGHT_SHIFT) || padDown(GAMEPAD_BUTTON_RIGHT_TRIGGER_1);
    /* right stick: orbit / zoom the camera; drifts back to the auto framing when let go */
    {
        static float camIdle = 0;
        float rx = padAxis(GAMEPAD_AXIS_RIGHT_X), ry = padAxis(GAMEPAD_AXIS_RIGHT_Y);
        camOrbit = Clamp(camOrbit + rx * dt * 1.4f, -1.2f, 1.2f);
        camZoom = Clamp(camZoom + ry * dt * 0.9f, 0.55f, 1.7f);
        if (IsKeyDown(KEY_Z)) { camOrbit -= dt; rx = 1; }
        if (IsKeyDown(KEY_X)) { camOrbit += dt; rx = 1; }
        camIdle = (rx != 0 || ry != 0) ? 0 : camIdle + dt;
        if (camIdle > 3.0f) { camOrbit = Lerp(camOrbit, 0, fminf(1, dt * 0.8f)); camZoom = Lerp(camZoom, 1, fminf(1, dt * 0.8f)); }
    }
    if (padPressed(GAMEPAD_BUTTON_RIGHT_THUMB) || IsKeyPressed(KEY_V)) { camOrbit = 0; camZoom = 1; }
    int l2 = padDown(GAMEPAD_BUTTON_LEFT_TRIGGER_2);
    int yPress = padPressed(GAMEPAD_BUTTON_RIGHT_FACE_UP);
    GamePlayer *me = &game.players[0][game.selected_player];
    float rawLen = sqrtf(raw.x * raw.x + raw.y * raw.y);
    int aimedGoal = 0;
    float aimX = rawLen > 0.3f ? raw.x : me->facing_x, aimZ = rawLen > 0.3f ? raw.y : me->facing_z;

    /* without the ball: pickup magnetism, first touch, catching and running onto a dropping ball */
    if (!game.has_ball && game.ball_team < 0 && !game.restart_pending) {
        float bx = game.ball.x - me->x, bz = game.ball.z - me->z, bd = sqrtf(bx * bx + bz * bz);
        if (!game.ball.in_flight && game.ball.height <= 0.4f && bd < 7.0f && bd > 0.05f) {
            Vector2 toBall = { bx / bd, bz / bd };
            if (bd < 3.0f) in.pickup = 1;                               /* toe-lift when it is at your feet */
            if (rawLen < 0.2f) m = Vector2Scale(toBall, bd > 1.2f ? 1.0f : 0.5f);
            else if (Vector2DotProduct(Vector2Scale(raw, 1.0f / rawLen), toBall) > 0.6f)
                m = Vector2Scale(Vector2Normalize(Vector2Lerp(Vector2Scale(raw, 1.0f / rawLen), toBall, bd < 3.0f ? 0.9f : 0.6f)), rawLen);
        } else if (game.ball.in_flight) {
            float lx, lz, lt; catchPoint(&lx, &lz, &lt);
            float dx = lx - me->x, dz = lz - me->z, dl = sqrtf(dx * dx + dz * dz);
            if (rawLen < 0.2f && dl > 0.8f && dl < 30.0f && !(game.last_release_team == 0 && game.last_release_player == game.selected_player)) {
                m = (Vector2){ dx / dl, dz / dl };
                if (dl > 8.0f) in.sprint = 1;
            }
            float hx = game.ball.x - me->x, hz = game.ball.z - me->z;
            if (sqrtf(hx * hx + hz * hz) < 3.2f && game.ball.height > 1.0f && game.ball.height < 4.6f && (game.ball.velocity_y < 0 || game.ball.height < 2.6f))
                in.high_field = 1;                                       /* catch assist */
        }
    }
    /* acceleration / turning curve (the free taker aims with the raw stick) */
    if (mvSel != game.selected_player) { mvSel = game.selected_player; mvSmooth = (Vector2){ me->facing_x * me->movement, me->facing_z * me->movement }; sprintRamp = me->movement > 0.8f ? 1.0f : 0.0f; }
    if (game.restart_pending && game.has_ball) mvSmooth = m;
    else mvSmooth = smoothMove(mvSmooth, m, dt);
    in.move_x = mvSmooth.x; in.move_z = mvSmooth.y;
    {
        float ml = Vector2Length(mvSmooth);
        sprintRamp = Clamp(sprintRamp + ((in.sprint && ml > 0.3f) ? dt * 2.2f : -dt * 4.0f), 0, 1);
        if (in.sprint) { float k = (7.0f + 2.0f * sprintRamp) / 9.0f; in.move_x *= k; in.move_z *= k; }
    }
    /* pass-assist rings: hand pass (cyan) and, while the kick charges, the kick pass (orange) */
    assistHand = game.has_ball ? assistTarget(0, aimX, aimZ) : -1;
    assistKick = game.has_ball ? assistTarget(1, aimX, aimZ) : -1;
    if (assistKick >= 0) {      /* a stick pointed at the posts in range means a shot, not a pass */
        float gx = GAME_PITCH_LENGTH - me->x, gz = HW - me->z, gd = sqrtf(gx * gx + gz * gz);
        GamePlayer *o = &game.players[0][assistKick];
        float al = fmaxf(1e-3f, sqrtf(aimX * aimX + aimZ * aimZ));
        float cg = (gx * aimX + gz * aimZ) / (gd * al), co = ((o->x - me->x) * aimX + (o->z - me->z) * aimZ) / (al * sqrtf((o->x - me->x) * (o->x - me->x) + (o->z - me->z) * (o->z - me->z)));
        if (gd < 45.0f && cg > co) assistKick = -1;
    }
    if (game.restart_type == GAME_RESTART_PENALTY && game.restart_pending) assistHand = assistKick = -1;
    if (game.has_ball) {
        /* X / SPACE: hold to charge, release to kick (power = hold time) */
        if (IsKeyPressed(KEY_SPACE) || padPressed(GAMEPAD_BUTTON_RIGHT_FACE_LEFT)) { charge = 0; chargeLow = 0; }
        if (IsKeyPressed(KEY_F)) { charge = 0; chargeLow = 1; }
        if (charge >= 0) charge = fminf(1.0f, charge + dt * 1.5f);
        if (charge >= 0 && (IsKeyReleased(KEY_SPACE) || IsKeyReleased(KEY_F) || padReleased(GAMEPAD_BUTTON_RIGHT_FACE_LEFT))) {
            if (chargeLow) in.kick_low = 1; else in.kick = 1;
            in.power = fmaxf(charge, 0.05f);
            if (assistKick >= 0 && !chargeLow) {      /* kick-pass assist: aim at the runner, power nudged to the distance */
                GamePlayer *o = &game.players[0][assistKick];
                float d = distTo(assistKick, me->x, me->z) + fminf(o->movement * 7.0f * 0.6f, 4.0f);
                in.pass_target = assistKick + 1; passIntent = assistKick; passIntentT = 0;
                /* assisted: the distance sets most of the power, a longer hold still adds a little */
                in.power = Clamp(powerForDistance(d + 2.0f) * 0.85f + in.power * 0.15f, 0.05f, 1.0f);
            }
            charge = -1;
        }
        /* Y / G: shoot - aim at the posts, power from the distance; low and driven when close */
        if (IsKeyPressed(KEY_G) || (yPress && !l2)) {
            float d = game_distance_to_goal(0, me->x, me->z);
            aimAtGoal(me); aimedGoal = 1;
            if (d < 21.0f && fabsf(me->z - HW) < 12.0f && !game.restart_pending) in.kick_low = 1; else in.kick = 1;
            in.power = Clamp(d / 46.0f, 0.45f, 1.0f);
            charge = -1;
        }
        /* R2 / L: power kick - full-power long kick; aimed at goal it is a two-point attempt */
        if ((IsKeyPressed(KEY_L) || padPressed(GAMEPAD_BUTTON_RIGHT_TRIGGER_2)) && !in.kick && !in.kick_low) {
            if (game_distance_to_goal(0, me->x, me->z) < 52.0f) { aimAtGoal(me); aimedGoal = 1; }
            in.kick = 1; in.power = 1.0f; charge = -1;
        }
        in.handpass = IsKeyPressed(KEY_E) || padPressed(GAMEPAD_BUTTON_RIGHT_FACE_DOWN);
        if (in.handpass && assistHand >= 0) { in.pass_target = assistHand + 1; passIntent = assistHand; passIntentT = 0; }
        /* the engine turns the player to the move direction before the strike:
         * make that the aim (goal / raw stick), not the smoothed run */
        if (in.kick || in.kick_low || in.handpass) {
            float ml = fmaxf(Vector2Length((Vector2){ in.move_x, in.move_z }), 0.02f);
            if (aimedGoal) { in.move_x = me->facing_x * ml; in.move_z = me->facing_z * ml; }
            else if (rawLen > 0.3f) { in.move_x = raw.x / rawLen * ml; in.move_z = raw.y / rawLen * ml; }
        }
        in.solo = IsKeyPressed(KEY_R);
        in.bounce = IsKeyPressed(KEY_B);
        if (padPressed(GAMEPAD_BUTTON_RIGHT_FACE_RIGHT)) {     /* B: legal one of bounce / solo */
            if (game.restart_pending) in.solo = 1;
            else if (!game.last_was_bounce) in.bounce = 1; else in.solo = 1;
        }
    } else {
        charge = -1;
        in.tackle = IsKeyPressed(KEY_SPACE) || IsKeyPressed(KEY_K) || padPressed(GAMEPAD_BUTTON_LEFT_TRIGGER_2);
        in.pickup = in.pickup || IsKeyDown(KEY_E) || IsKeyDown(KEY_SPACE) || IsKeyDown(KEY_F) || padDown(GAMEPAD_BUTTON_RIGHT_FACE_DOWN);
        in.high_field = in.high_field || IsKeyPressed(KEY_J) || padPressed(GAMEPAD_BUTTON_RIGHT_FACE_LEFT);
        /* special move: H, or L2 + Y on the pad (deliberately a two-button combo) */
        in.special = IsKeyPressed(KEY_H) || (l2 && yPress);
        if (in.special) in.tackle = 0;
    }
    if (IsKeyPressed(KEY_Q) || IsKeyPressed(KEY_TAB) || padPressed(GAMEPAD_BUTTON_LEFT_TRIGGER_1)) manualSwitch();
    return in;
}

/* Demo / attract-mode brain for the home player (also used for screenshots). */
static GameInput demoInput(void)
{
    GameInput in = { 0 };
    GamePlayer *p = &game.players[0][game.selected_player];
    if (game.has_ball) {
        float d = game_distance_to_goal(0, p->x, p->z);
        if (game.restart_pending) {
            if (game.restart_time > 1.0f) { in.kick = 1; in.power = 0.8f; in.move_x = 1; }
            return in;
        }
        in.move_x = 1.0f; in.move_z = (HW - p->z) * 0.03f; in.sprint = 1;
        if (d < 34.0f && fabsf(p->z - HW) < 18.0f) { aimAtGoal(p); in.kick = 1; in.power = Clamp(d / 46.0f, 0.5f, 0.9f); }
        else {
            float press = 1e9f;
            for (int i = 0; i < GAME_TEAM_SIZE; i++) {
                float dx = game.players[1][i].x - p->x, dz = game.players[1][i].z - p->z;
                press = fminf(press, sqrtf(dx * dx + dz * dz));
            }
            if (press < 3.0f && GetRandomValue(0, 100) < 8) in.handpass = 1;
        }
    } else {
        float dx = game.ball.x - p->x, dz = game.ball.z - p->z;
        float l = sqrtf(dx * dx + dz * dz);
        if (l > 1.0f) { in.move_x = dx / l; in.move_z = dz / l; in.sprint = l > 6; }
        in.pickup = 1;
        in.tackle = l < 2.0f && game.ball_team == 1 && GetRandomValue(0, 100) < 5;
        in.high_field = game.ball.in_flight && game.ball.velocity_y < 0.0f && game.ball.height > 1.6f && game.ball.height < 3.8f && l < 2.5f;
        if (l > 15.0f && GetRandomValue(0, 100) < 3) game_select_nearest_player(&game);
    }
    return in;
}

/* auto toe-tap / bounce for the human when the 4th step is near (toggle T) */
static void applyAssist(GameInput *in)
{
    GamePlayer *p = &game.players[0][game.selected_player];
    if (!autoSolo || !game.has_ball || game.restart_pending || p->action != GAME_ACT_NONE) return;
    if ((in->move_x != 0 || in->move_z != 0) && game_carrier_steps(&game) >= 3 && !in->kick && !in->kick_low && !in->handpass) {
        if (!game.last_was_bounce) in->bounce = 1; else in->solo = 1;
    }
}

/* ---- camera ---------------------------------------------------------------- */
static Camera3D cam;
static Vector3 camFocus;
static int camOverride = 0;       /* 1 wide stadium orbit, 2 referee/card close-up */
static float camOverrideT = 0;

/* v3.2 framing: how wide the shot should be (0 tight .. 1 wide) and where play is.
 * Follows the carrier of either team, leads a ball in the air toward where it
 * will land, widens for long kicks, kick-outs and restarts, tightens for
 * close contests (as the original prototype camera did, plus spread). */
static float camOpen = 0.3f;
static Vector3 camFocusVel;
static float framingTarget(Vector3 *focus)
{
    float open = 0.22f;
    Vector3 b = W(game.ball.x, 0, game.ball.z), f = b;
    if (game.ball_team >= 0 && game.ball_player >= 0) {
        GamePlayer *c = &game.players[game.ball_team][game.ball_player];
        f = W(c->x + c->facing_x * c->movement * 4.0f, 0, c->z + c->facing_z * c->movement * 3.0f);
        open += c->movement > 0.9f ? 0.08f : 0.0f;
    } else if (game.ball.in_flight) {
        float lx, lz; landingPoint(&lx, &lz, NULL);
        Vector3 l = W(lx, 0, lz);
        float fd = Vector3Distance(b, l);
        f = Vector3Lerp(b, l, 0.45f);
        open += Clamp((fd - 10.0f) / 45.0f, 0, 1) * 0.75f + Clamp(game.ball.height / 25.0f, 0, 0.3f);
    }
    /* spread of the nearest players around play */
    float near[4] = { 1e9f, 1e9f, 1e9f, 1e9f };
    for (int t = 0; t < 2; t++) for (int i = 0; i < GAME_TEAM_SIZE; i++) {
        GamePlayer *p = &game.players[t][i];
        if (p->off || (t == game.ball_team && i == game.ball_player)) continue;
        float d = Vector3Distance(W(p->x, 0, p->z), f);
        for (int k = 0; k < 4; k++) if (d < near[k]) { for (int j = 3; j > k; j--) near[j] = near[j - 1]; near[k] = d; break; }
    }
    float spread = (near[0] + near[1] + near[2] + near[3]) * 0.25f;
    open += Clamp((spread - 5.0f) / 25.0f, 0, 0.3f);
    if (game.restart_pending) {
        if (game.restart_type == GAME_RESTART_KICKOUT) open = fmaxf(open, 0.85f);
        else if (game.restart_type == GAME_RESTART_PENALTY) open = fminf(open, 0.3f);
        else open = fmaxf(open, 0.5f);
    }
    if (game.kickout_in_progress || game.from_kickout) open = fmaxf(open, 0.8f);
    /* keep your player in the picture when he is close to play */
    GamePlayer *h = &game.players[0][game.selected_player];
    Vector3 hp = W(h->x, 0, h->z);
    float hd = Vector3Distance(hp, f);
    if (hd < 28.0f) { f = Vector3Lerp(f, hp, 0.15f); open += Clamp((hd - 10.0f) / 60.0f, 0, 0.2f); }
    *focus = f;
    return Clamp(open, 0, 1);
}
static Vector3 smoothDamp3(Vector3 cur, Vector3 tgt, Vector3 *vel, float smoothTime, float dt)
{
    float omega = 2.0f / smoothTime, x = omega * dt, e = 1.0f / (1.0f + x + 0.48f * x * x + 0.235f * x * x * x);
    Vector3 ch = Vector3Subtract(cur, tgt);
    Vector3 tmp = Vector3Scale(Vector3Add(*vel, Vector3Scale(ch, omega)), dt);
    *vel = Vector3Scale(Vector3Subtract(*vel, Vector3Scale(tmp, omega)), e);
    return Vector3Add(tgt, Vector3Scale(Vector3Add(ch, tmp), e));
}

static void updateCamera(float dt)
{
    Vector3 b = W(game.ball.x, 0, game.ball.z);
    GamePlayer *h = &game.players[0][game.selected_player];
    Vector3 hp = W(h->x, 0, h->z);
    Vector3 focus;
    float openT = framingTarget(&focus);
    if (camMode == 2 || camMode == 5) focus = Vector3Lerp(b, hp, 0.8f);
    if (camMode == 3) focus = b;
    camOpen += (openT - camOpen) * fminf(1.0f, dt * (openT > camOpen ? 1.6f : 0.9f));
    if (dt > 0.0f) camFocus = smoothDamp3(camFocus, focus, &camFocusVel, game.ball.in_flight ? 0.45f : 0.6f, dt);
    float o = camOpen;
    Vector3 pos, tgt = camFocus;
    float snap = dt * 4.0f;
    cam.fovy = 40;
    camOverrideT += dt;
    if (camOverride == 1) {
        float a = 0.35f + camOverrideT * 0.12f;
        pos = (Vector3){ sinf(a) * 150.0f, 62.0f, cosf(a) * 120.0f }; tgt = (Vector3){ 0, 4, 0 }; cam.fovy = 50; snap = 1.0f;
    } else if (camOverride == 2) {
        Vector3 r = W(game.referee.x, 0, game.referee.z);
        Vector3 ob = r;
        if (game.card_team >= 0 && game.card_player >= 0) ob = W(game.players[game.card_team][game.card_player].x, 0, game.players[game.card_team][game.card_player].z);
        Vector3 mid = Vector3Lerp(r, ob, 0.5f);
        pos = (Vector3){ mid.x + 2.5f, 2.6f, mid.z + 7.5f }; tgt = (Vector3){ mid.x, 1.3f, mid.z }; cam.fovy = 38; snap = 1.0f;
    } else {
        switch (camMode) {
        case 0:   /* broadcast: dynamic zoom - close for contests, wide for long kicks / kick-outs */
            pos = (Vector3){ camFocus.x, 9.0f + 18.0f * o, camFocus.z * 0.35f + 22.0f + 36.0f * o };
            tgt.z = camFocus.z * 0.6f; tgt.y = 0.5f + game.ball.height * o * 0.15f; cam.fovy = 38.0f + 8.0f * o; break;
        case 1:   /* TV close */
            pos = (Vector3){ camFocus.x, 4.0f + 7.0f * o, camFocus.z + 9.0f + 14.0f * o }; tgt.y = 1.0f; cam.fovy = 36.0f + 6.0f * o; break;
        case 5: pos = (Vector3){ hp.x + 1.5f, 1.9f, hp.z + 5.2f }; tgt = (Vector3){ hp.x, 1.0f, hp.z }; cam.fovy = 38; break;
        case 2: pos = (Vector3){ hp.x - 8.0f, 3.6f, hp.z }; tgt = (Vector3){ hp.x + 6.0f, 1.2f, hp.z }; break;
        case 3: { float s = b.x > 0 ? 1.0f : -1.0f; pos = (Vector3){ s * (HL + 9.0f), 4.5f, 0.0f }; tgt = (Vector3){ b.x, 1.2f, b.z * 0.8f }; cam.fovy = 45; } break;
        default: pos = (Vector3){ camFocus.x, 55.0f + 30.0f * o, camFocus.z + 22.0f }; cam.fovy = 45; break;
        }
        /* right stick orbit / zoom around the look-at point */
        Vector3 off = Vector3Subtract(pos, tgt);
        if (camMode != 2 && camMode != 3) off = Vector3RotateByAxisAngle(off, (Vector3){ 0, 1, 0 }, camOrbit);
        pos = Vector3Add(tgt, Vector3Scale(off, camZoom));
    }
    cam.position = Vector3Lerp(cam.position, pos, fminf(1.0f, snap));
    cam.target = tgt;
}

/* Broadcast shot list for the 20 s attract demo. */
static const char *introCamera(float t, float dt)
{
    Vector3 b = W(game.ball.x, 0, game.ball.z);
    camFocus = Vector3Lerp(camFocus, b, fminf(1.0f, dt * 2.5f));
    if (t < 5.0f) {                       /* sweeping aerial of the bowl */
        float a = -0.9f + t * 0.16f;
        cam.position = (Vector3){ sinf(a) * 165.0f, 70.0f - t * 4.0f, cosf(a) * 130.0f };
        cam.target = (Vector3){ 0, 6, -8 }; cam.fovy = 48;
        return "AERIAL";
    } else if (t < 9.0f) {                /* main broadcast camera */
        cam.position = Vector3Lerp(cam.position, (Vector3){ camFocus.x, 15.0f, camFocus.z * 0.35f + 30.0f }, t < 5.05f ? 1.0f : fminf(1.0f, dt * 3));
        cam.target = (Vector3){ camFocus.x, 0, camFocus.z * 0.6f }; cam.fovy = 40;
        return "BROADCAST";
    } else if (t < 13.0f) {               /* low behind-the-goal at the Hill end */
        cam.position = (Vector3){ HL + 10.0f, 3.2f, 6.0f - (t - 9.0f) * 2.0f };
        cam.target = (Vector3){ b.x * 0.6f + 10, 1.5f, b.z * 0.7f }; cam.fovy = 44;
        return "HILL 16 END";
    } else if (t < 16.5f) {               /* tight tracking on the ball */
        cam.position = Vector3Lerp(cam.position, (Vector3){ camFocus.x - 3, 3.0f, camFocus.z + 9.0f }, t < 13.05f ? 1.0f : fminf(1.0f, dt * 3));
        cam.target = (Vector3){ camFocus.x, 1.1f, camFocus.z }; cam.fovy = 34;
        return "TRACKING";
    }
    float a = (t - 16.5f) * 0.25f;        /* rising crane over the far stand */
    cam.position = (Vector3){ -40.0f + (t - 16.5f) * 12.0f, 9.0f + (t - 16.5f) * 9.0f, 52.0f - a * 20 };
    cam.target = (Vector3){ 0, 10, -60 }; cam.fovy = 52;
    return "CRANE";
}

/* ---- HUD --------------------------------------------------------------------- */
static void drawCardIcon(int x, int y, int c, float s)
{
    DrawRectangle(x, y, (int)(10 * s), (int)(14 * s), cardColor(c));
    DrawRectangleLines(x, y, (int)(10 * s), (int)(14 * s), (Color){ 255, 255, 255, 120 });
}

static void drawTeamDiscipline(int team, int x, int y)
{
    int cx = x;
    for (int c = GAME_CARD_YELLOW; c <= GAME_CARD_RED; c++)
        for (int k = 0; k < game.cards_given[team][c] && k < 4; k++) { drawCardIcon(cx, y, c, 1.0f); cx += 13; }
    int on = game_players_on(&game, team);
    if (on < GAME_TEAM_SIZE) DrawText(TextFormat("%d men", on), cx + 6, y, 16, ORANGE);
}

static void drawSinBins(int sw)
{
    int y = 82;
    for (int t = 0; t < 2; t++)
        for (int i = 0; i < GAME_TEAM_SIZE; i++) {
            GamePlayer *p = &game.players[t][i];
            if (p->off != 1) continue;
            float gameSecs = p->sin_bin * (2100.0f / HALF_SECONDS);   /* real -> match seconds */
            int m = (int)(gameSecs / 60), s = (int)gameSecs % 60;
            DrawRectangle(sw - 230, y, 220, 26, (Color){ 0, 0, 0, 170 });
            DrawRectangle(sw - 226, y + 4, 12, 18, t ? (Color){ 200, 20, 40, 255 } : (Color){ 40, 70, 200, 255 });
            drawCardIcon(sw - 208, y + 5, GAME_CARD_BLACK, 1.15f);
            DrawText(TextFormat("#%d SIN BIN  %d:%02d", i + 1, m, s), sw - 190, y + 4, 18, RAYWHITE);
            float frac = p->sin_bin / fmaxf(1.0f, game.sin_bin_seconds);
            DrawRectangle(sw - 226, y + 23, (int)(212 * frac), 3, ORANGE);
            y += 30;
        }
}

/* ---- controller test screen (Controls menu / F1 / Back) -------------------- */
static void padButtonGlyph(int x, int y, int r, const char *label, Color on, int b)
{
    int down = padDown(b);
    DrawCircle(x, y, (float)r + (down ? 3 : 0), down ? on : (Color){ on.r / 3, on.g / 3, on.b / 3, 255 });
    if (down) DrawCircleLines(x, y, (float)r + 6, RAYWHITE);
    DrawText(label, x - MeasureText(label, 18) / 2, y - 9, 18, down ? BLACK : RAYWHITE);
}

static void padBumper(int x, int y, int w, int h, const char *label, int b, float analog)
{
    int down = padDown(b);
    Color base = (Color){ 80, 85, 98, 255 }, lit = (Color){ 255, 200, 40, 255 };
    DrawRectangleRounded((Rectangle){ (float)x, (float)y, (float)w, (float)h }, 0.5f, 8, down ? lit : base);
    if (analog > -1.5f) {               /* trigger travel bar */
        float k = Clamp((analog + 1.0f) * 0.5f, 0, 1);
        DrawRectangle(x + 6, y + h - 6, (int)((w - 12) * k), 3, down ? BLACK : ORANGE);
    }
    DrawText(label, x + w / 2 - MeasureText(label, 16) / 2, y + h / 2 - 9, 16, down ? BLACK : RAYWHITE);
}

static void padStick(int cx, int cy, float ax, float ay, int click, const char *label)
{
    DrawCircle(cx, cy, 40, (Color){ 25, 26, 32, 255 });
    DrawCircleLines(cx, cy, 40, GRAY);
    DrawCircleLines(cx, cy, 40 * PAD_DEADZONE, (Color){ 90, 90, 90, 255 });
    float m = sqrtf(ax * ax + ay * ay);
    Color c = m > PAD_DEADZONE ? LIME : (Color){ 150, 150, 160, 255 };
    DrawLine(cx, cy, cx + (int)(ax * 32), cy + (int)(ay * 32), Fade(c, 0.6f));
    DrawCircle(cx + (int)(ax * 32), cy + (int)(ay * 32), click ? 15 : 12, click ? GOLD : c);
    DrawText(TextFormat("%s %+.2f %+.2f", label, ax, ay), cx - 62, cy + 46, 14, LIGHTGRAY);
}

static void drawControls(int sw, int sh)
{
    int w = 1000, h = 560, x = sw / 2 - w / 2, y = sh / 2 - h / 2;
    if (x < 0) x = 0;
    if (y < 0) y = 0;
    DrawRectangle(x, y, w, h, (Color){ 10, 16, 30, 240 });
    DrawRectangleLines(x, y, w, h, (Color){ 120, 160, 220, 255 });
    DrawText("CONTROLLER TEST & CONTROLS", x + 20, y + 14, 28, GOLD);
    DrawText(padStatusText(), x + 20, y + 48, 18, padId >= 0 ? (pad.mapped || pad.simulated ? LIME : ORANGE) : (Color){ 255, 110, 90, 255 });
    if (padId >= 0) DrawText(TextFormat("slot %d   GUID %s   mappings: %s", padId, pad.guid, padMappingsLoaded > 0 ? "gamecontrollerdb loaded" : "not loaded"), x + 20, y + 70, 14, GRAY);
    else DrawText("EasySMX: X-mode (XInput) or D-mode both work. Try another USB port, then check the pad's mode LED.", x + 20, y + 70, 14, GRAY);

    /* live pad diagram */
    int px = x + 30, py = y + 110;
    padBumper(px + 20, py, 120, 30, "L2", GAMEPAD_BUTTON_LEFT_TRIGGER_2, pad.axis[GAMEPAD_AXIS_LEFT_TRIGGER]);
    padBumper(px + 300, py, 120, 30, "R2", GAMEPAD_BUTTON_RIGHT_TRIGGER_2, pad.axis[GAMEPAD_AXIS_RIGHT_TRIGGER]);
    padBumper(px + 20, py + 36, 120, 26, "L1", GAMEPAD_BUTTON_LEFT_TRIGGER_1, -2);
    padBumper(px + 300, py + 36, 120, 26, "R1", GAMEPAD_BUTTON_RIGHT_TRIGGER_1, -2);
    DrawRectangleRounded((Rectangle){ (float)px, (float)py + 68, 440, 210 }, 0.45f, 12, (Color){ 55, 60, 72, 255 });
    padStick(px + 95, py + 128, pad.axis[0], pad.axis[1], padDown(GAMEPAD_BUTTON_LEFT_THUMB), "L");
    padStick(px + 290, py + 210, pad.axis[2], pad.axis[3], padDown(GAMEPAD_BUTTON_RIGHT_THUMB), "R");
    {   /* d-pad */
        int dx = px + 150, dy = py + 210;
        struct { int b, ox, oy; } d[4] = { { GAMEPAD_BUTTON_LEFT_FACE_UP, 0, -22 }, { GAMEPAD_BUTTON_LEFT_FACE_DOWN, 0, 22 },
                                           { GAMEPAD_BUTTON_LEFT_FACE_LEFT, -22, 0 }, { GAMEPAD_BUTTON_LEFT_FACE_RIGHT, 22, 0 } };
        DrawRectangle(dx - 8, dy - 8, 16, 16, (Color){ 30, 30, 36, 255 });
        for (int i = 0; i < 4; i++) {
            Vector2 c = { (float)(dx + d[i].ox), (float)(dy + d[i].oy) };
            int on = padDown(d[i].b);
            DrawRectangle((int)c.x - 11, (int)c.y - 11, 22, 22, on ? GOLD : (Color){ 30, 30, 36, 255 });
            Vector2 dir = { (float)d[i].ox / 22.0f, (float)d[i].oy / 22.0f }, perp = { -dir.y, dir.x };
            Vector2 tip = { c.x + dir.x * 7, c.y + dir.y * 7 }, b1 = { c.x - dir.x * 5 + perp.x * 6, c.y - dir.y * 5 + perp.y * 6 }, b2 = { c.x - dir.x * 5 - perp.x * 6, c.y - dir.y * 5 - perp.y * 6 };
            DrawTriangle(tip, b2, b1, on ? BLACK : GRAY);
            DrawTriangle(tip, b1, b2, on ? BLACK : GRAY);
        }
    }
    padButtonGlyph(px + 360, py + 160, 16, "A", (Color){ 60, 200, 70, 255 }, GAMEPAD_BUTTON_RIGHT_FACE_DOWN);
    padButtonGlyph(px + 394, py + 126, 16, "B", (Color){ 230, 60, 60, 255 }, GAMEPAD_BUTTON_RIGHT_FACE_RIGHT);
    padButtonGlyph(px + 326, py + 126, 16, "X", (Color){ 60, 120, 240, 255 }, GAMEPAD_BUTTON_RIGHT_FACE_LEFT);
    padButtonGlyph(px + 360, py + 92, 16, "Y", (Color){ 240, 200, 40, 255 }, GAMEPAD_BUTTON_RIGHT_FACE_UP);
    padBumper(px + 165, py + 100, 52, 22, "Back", GAMEPAD_BUTTON_MIDDLE_LEFT, -2);
    padBumper(px + 228, py + 100, 52, 22, "Start", GAMEPAD_BUTTON_MIDDLE_RIGHT, -2);

    /* raw values for unmapped pads */
    int ry = py + 290;
    DrawText("RAW (for debugging)", px, ry, 16, SKYBLUE);
    char line[256]; int n = 0;
    n += snprintf(line + n, sizeof line - n, "axes:");
    for (int i = 0; i < pad.nRawAxes && n < 200; i++) n += snprintf(line + n, sizeof line - n, " %d:%+.2f", i, pad.rawAxes[i]);
    if (!pad.nRawAxes) n += snprintf(line + n, sizeof line - n, " -");
    DrawText(line, px, ry + 20, 14, RAYWHITE);
    n = snprintf(line, sizeof line, "raw buttons down:");
    int any = 0;
    for (int i = 0; i < pad.nRawBtns && n < 200; i++) if (pad.rawBtns[i]) { n += snprintf(line + n, sizeof line - n, " b%d", i); any = 1; }
    for (int i = 0; i < pad.nRawHats && n < 200; i++) if (pad.rawHats[i]) { n += snprintf(line + n, sizeof line - n, " hat%d=%d", i, pad.rawHats[i]); any = 1; }
    if (!any) snprintf(line + n, sizeof line - n, " none");
    DrawText(line, px, ry + 38, 14, RAYWHITE);
    static const char *BN[PAD_BTNS] = { "?", "Up", "Right", "Down", "Left", "Y", "B", "A", "X", "L1", "L2", "R1", "R2", "Back", "Guide", "Start", "L3", "R3" };
    n = snprintf(line, sizeof line, "mapped buttons down:");
    any = 0;
    for (int b = 1; b < PAD_BTNS; b++) if (padDown(b)) { n += snprintf(line + n, sizeof line - n, " %s", BN[b]); any = 1; }
    if (!any) snprintf(line + n, sizeof line - n, " none");
    DrawText(line, px, ry + 56, 14, LIME);
    DrawText(TextFormat("triggers: L %+.2f  R %+.2f   (an axis above 0.5 = pressed)", pad.axis[4], pad.axis[5]), px, ry + 74, 14, RAYWHITE);

    /* mapping lists */
    const char *padLines[] = {
        "PAD", "A  hand pass  |  no ball: pick up", "B  solo / bounce (legal one)", "X  kick - hold for power", "    no ball: jump / high catch",
        "Y  shoot at the posts", "R2 power kick / 2-point try", "L2 tackle / shoulder", "L2+Y hook/head hit = RED", "L1 switch   R1 sprint",
        "R stick camera, R3 reset", "Start pause   Back this screen", "D-pad cameras / menus" };
    for (int i = 0; i < 13; i++) DrawText(padLines[i], x + 490, y + 110 + i * 19, i == 0 ? 18 : 15, i == 0 ? GOLD : RAYWHITE);
    const char *keys[] = {
        "KEYBOARD", "WASD / arrows  move", "Shift  sprint", "Space (hold)  kick / tackle", "F  low / ground shot", "G  shoot at goal",
        "L  power kick", "E  hand pass / pick up", "R / B  solo / bounce", "J  jump to field", "H  hook (RED!)", "Q / Tab  switch player",
        "C, 1-6  cameras", "Z / X, V  orbit, reset", "T  auto-solo", "P  pause   F2 quality", "F3  FPS / profiler" };
    for (int i = 0; i < 17; i++) DrawText(keys[i], x + 760, y + 110 + i * 19, i == 0 ? 18 : 15, i == 0 ? GOLD : RAYWHITE);
    DrawText("Press F1 / Back / Esc to close", x + w - 300, y + h - 26, 16, GRAY);
}

static void drawCommentary(int sw, int sh)
{
    (void)sw;
    for (int i = 0; i < COMM_LINES; i++) {
        if (commAge[i] > 7.0f || !commLine[i][0]) continue;
        float a = Clamp(7.0f - commAge[i], 0, 1) * (i == 0 ? 1.0f : 0.7f);
        int y = sh - 120 - i * 26;
        int w = MeasureText(commLine[i], 19);
        DrawRectangle(12, y - 3, w + 16, 25, Fade(BLACK, 0.55f * a));
        DrawText(commLine[i], 20, y, 19, Fade(i == 0 ? RAYWHITE : LIGHTGRAY, a));
    }
}

static int passTarget(void);
static const char *SURNAMES[2][GAME_TEAM_SIZE];
static void drawTrainingHUD(int sw, int sh);

static void drawHUD(int sw, int sh)
{
    char a[32], b[32];
    snprintf(a, sizeof a, "%d-%02d (%d)", game.team_goals[0], game.team_points[0], game.team_goals[0] * 3 + game.team_points[0]);
    snprintf(b, sizeof b, "%d-%02d (%d)", game.team_goals[1], game.team_points[1], game.team_goals[1] * 3 + game.team_points[1]);
    DrawRectangle(10, 10, 640, 66, (Color){ 0, 0, 0, 170 });
    DrawRectangle(18, 20, 14, 20, (Color){ 40, 70, 200, 255 });
    DrawText(TextFormat("%-12s %s", game_team_name(game.home_team), a), 40, 20, 22, RAYWHITE);
    DrawRectangle(18, 46, 14, 20, (Color){ 200, 20, 40, 255 });
    DrawText(TextFormat("%-12s %s", game_team_name(game.away_team), b), 40, 46, 22, RAYWHITE);
    if (!training) { drawTeamDiscipline(0, 330, 23); drawTeamDiscipline(1, 330, 49); }
    int mins = (int)(clockT / HALF_SECONDS * 35.0f) + (game.half == 2 ? 35 : 0);
    DrawText(TextFormat("%s %02d'", game.half == 1 ? "1st" : "2nd", mins), 560, 32, 20, YELLOW);
    if (!training) drawSinBins(sw);
    if (!demo) {   /* controlled player */
        int sp = game.selected_player;
        const char *nm = TextFormat("#%d %s  -  %s", sp + 1, SURNAMES[0][sp], game_player_role(sp));
        int w = MeasureText(nm, 20);
        DrawRectangle(660, 10, w + 46, 30, (Color){ 0, 0, 0, 170 });
        DrawCircle(676, 25, 8, (Color){ 255, 220, 0, 255 });
        DrawText(nm, 692, 15, 20, (Color){ 255, 230, 120, 255 });
        if (game.has_ball) { int t = passTarget(); if (t >= 0) DrawText(TextFormat("hand pass -> #%d %s", t + 1, SURNAMES[0][t]), 662, 44, 16, (Color){ 120, 235, 255, 255 }); }
        /* v3.2: your player is off screen -> an arrow at the edge pointing to him */
        GamePlayer *me = &game.players[0][sp];
        Vector3 wp = W(me->x, 1.0f, me->z);
        Vector3 fw = Vector3Normalize(Vector3Subtract(cam.target, cam.position));
        Vector2 s = GetWorldToScreenEx(wp, cam, sw, sh);
        int behind = Vector3DotProduct(Vector3Subtract(wp, cam.position), fw) < 0;
        if (behind || s.x < 0 || s.y < 0 || s.x > sw || s.y > sh) {
            Vector2 cc = { sw * 0.5f, sh * 0.5f }, d = Vector2Subtract(s, cc);
            if (behind) d = Vector2Scale(d, -1);
            float k = fminf((sw * 0.5f - 40) / fmaxf(fabsf(d.x), 1e-3f), (sh * 0.5f - 40) / fmaxf(fabsf(d.y), 1e-3f));
            Vector2 e = Vector2Add(cc, Vector2Scale(d, k)), n = Vector2Normalize(d), q = { -n.y, n.x };
            DrawTriangle(Vector2Add(e, Vector2Scale(n, 22)), Vector2Add(e, Vector2Scale(q, -12)), Vector2Add(e, Vector2Scale(q, 12)), (Color){ 255, 220, 0, 255 });
            DrawTriangle(Vector2Add(e, Vector2Scale(n, 22)), Vector2Add(e, Vector2Scale(q, 12)), Vector2Add(e, Vector2Scale(q, -12)), (Color){ 255, 220, 0, 255 });
            DrawText(TextFormat("%d", sp + 1), (int)(e.x - n.x * 26) - 8, (int)(e.y - n.y * 26) - 9, 18, (Color){ 255, 230, 120, 255 });
        }
    }

    /* carrier status: steps and bounce legality */
    if (game.has_ball) {
        int st = game_carrier_steps(&game);
        DrawRectangle(10, 82, 300, 30, (Color){ 0, 0, 0, 150 });
        DrawText("steps", 18, 89, 18, RAYWHITE);
        for (int i = 0; i < 4; i++) DrawRectangle(80 + i * 20, 90, 14, 14, i < st ? (st >= 4 ? RED : ORANGE) : DARKGRAY);
        DrawText(game.last_was_bounce ? "next: SOLO (R/B)" : "bounce ok (B)", 170, 89, 18, game.last_was_bounce ? ORANGE : LIME);
    }
    if (game.restart_pending && game.card_time <= 0.0f) {
        const char *r = game.restart_type == GAME_RESTART_KICKOUT ? "KICK-OUT: must pass the 40m arc" :
                        game.restart_type == GAME_RESTART_FREE ? (game.mark_play_on ? "MARK: kick the free or play on (R / B)" : "FREE KICK  (R = Solo & Go)") :
                        game.restart_type == GAME_RESTART_SIDELINE ? "SIDELINE KICK" :
                        game.restart_type == GAME_RESTART_FORTY_FIVE ? "45m FREE (1 point)" :
                        game.restart_type == GAME_RESTART_PENALTY ? "PENALTY: aim, F / Y shoot" : "RESTART";
        int w = MeasureText(r, 24);
        DrawRectangle(sw / 2 - w / 2 - 10, 84, w + 20, 34, (Color){ 0, 0, 0, 160 });
        DrawText(r, sw / 2 - w / 2, 90, 24, game.ball_team == 0 ? SKYBLUE : PINK);
    }
    /* referee showing a card: big card + who */
    if (game.card_time > 0.0f && game.card_team >= 0) {
        float k = Clamp((3.0f - game.card_time) * 4.0f, 0, 1);
        int cw = (int)(70 * k), ch = (int)(100 * k), cx = sw / 2 - 210, cy = 128;
        DrawRectangle(cx + 4, cy + 4, cw, ch, Fade(BLACK, 0.5f));
        DrawRectangle(cx, cy, cw, ch, cardColor(game.card_type));
        DrawRectangleLines(cx, cy, cw, ch, RAYWHITE);
        const char *what = game.card_type == GAME_CARD_YELLOW ? "YELLOW CARD" : game.card_type == GAME_CARD_BLACK ? "BLACK CARD - 10 MIN SIN BIN" :
                           game.card_second_yellow ? "SECOND CARD - RED, SENT OFF" : "RED CARD - SENT OFF";
        DrawText(what, cx + 90, cy + 16, 28, cardColor(game.card_type).r > 100 || game.card_type == GAME_CARD_BLACK ? RAYWHITE : RAYWHITE);
        DrawText(TextFormat("%s  #%d  %s", game_team_name(game.card_team ? game.away_team : game.home_team), game.card_player + 1, game_player_role(game.card_player)),
                 cx + 90, cy + 52, 20, LIGHTGRAY);
        if (game.card_type != GAME_CARD_YELLOW) DrawText(TextFormat("%s down to %d", game_team_name(game.card_team ? game.away_team : game.home_team), game_players_on(&game, game.card_team)), cx + 90, cy + 78, 18, ORANGE);
    }
    if (charge >= 0) {
        DrawRectangle(sw / 2 - 100, sh - 60, 200, 18, (Color){ 0, 0, 0, 160 });
        DrawRectangle(sw / 2 - 100, sh - 60, (int)(200 * charge), 18, chargeLow ? ORANGE : GOLD);
        DrawText(chargeLow ? "LOW / GROUND SHOT" : "KICK (drop punt)", sw / 2 - 100, sh - 82, 18, RAYWHITE);
    }
    const char *ev = fullTime ? "FULL TIME  (Enter / Start: new match)" : game_event_text(game.event);
    if (((game.event_time > 0 && ev[0]) || fullTime) && game.card_time <= 0.0f) {
        int w = MeasureText(ev, 34);
        DrawText(ev, sw / 2 - w / 2 + 2, sh / 4 + 2, 34, BLACK);
        DrawText(ev, sw / 2 - w / 2, sh / 4, 34, fullTime ? GOLD : RAYWHITE);
    }
    drawCommentary(sw, sh);
    DrawText(TextFormat("Cam %d: %s   Auto-solo: %s   Gfx: %s", camMode + 1, CAM_NAMES[camMode], autoSolo ? "on" : "off", QUALITY_NAMES[gfxQuality]), sw - 520, sh - 46, 16, RAYWHITE);
    if (training) return;
    if (padId >= 0)
        DrawText("PAD: A hand pass/pick up  B solo/bounce  X kick (hold)  Y shoot  R2 power kick  L2 tackle  L1 switch  R1 sprint  Back test screen",
                 10, sh - 22, 15, RAYWHITE);
    else
        DrawText("WASD move  Shift sprint  SPACE kick(hold)/tackle  G shoot  E hand pass  R solo  B bounce  J jump  H hook (red!)  Q switch  F1 controls",
                 10, sh - 22, 15, RAYWHITE);
}

/* ---- per-frame render of everything ---------------------------------------- */
/* cheap view-cone test (sphere vs the camera's frustum cone) */
static int inView(Vector3 p, float r)
{
    Vector3 f = Vector3Normalize(Vector3Subtract(cam.target, cam.position)), d = Vector3Subtract(p, cam.position);
    float dist = Vector3Length(d);
    if (dist < r + 0.5f) return 1;
    float aspect = (float)GetRenderWidth() / (float)(GetRenderHeight() > 0 ? GetRenderHeight() : 1);
    float halfV = cam.fovy * DEG2RAD * 0.5f, halfH = atanf(tanf(halfV) * aspect);
    float halfDiag = atanf(sqrtf(tanf(halfV) * tanf(halfV) + tanf(halfH) * tanf(halfH)));
    float ang = acosf(Clamp(Vector3DotProduct(f, d) / dist, -1, 1));
    return ang < halfDiag + asinf(fminf(1.0f, r / dist)) + 0.05f;
}

/* ---- who am I? selection ring, head marker and pass-target ring ------------- */
static int showMarkers = 0;
static const char *SURNAMES[2][GAME_TEAM_SIZE] = {
    { "Gallagher", "Doherty", "McGee", "Boyle", "Sweeney", "Bonner", "O'Donnell", "McHugh", "Gildea", "McFadden", "Brennan", "Kelly", "Mulreany", "Breslin", "Coyle" },
    { "Walsh", "Murphy", "Ryan", "Byrne", "O'Brien", "Kavanagh", "Dunne", "Nolan", "Doyle", "Keane", "Brady", "Lynch", "Quinn", "Fitzgerald", "Moran" } };

static int passTarget(void)
{
    return game.has_ball ? assistHand : -1;      /* v3.2: stick-direction pass assist */
}

static void groundRing(Vector3 c, float r0, float r1, Color col)
{
    const int N = 40;
    rlBegin(RL_TRIANGLES);
    rlColor4ub(col.r, col.g, col.b, col.a);
    for (int k = 0; k < N; k++) {
        float a0 = (float)k / N * 2 * PI, a1 = (float)(k + 1) / N * 2 * PI;
        Vector3 i0 = { c.x + cosf(a0) * r0, c.y, c.z + sinf(a0) * r0 }, o0 = { c.x + cosf(a0) * r1, c.y, c.z + sinf(a0) * r1 };
        Vector3 i1 = { c.x + cosf(a1) * r0, c.y, c.z + sinf(a1) * r0 }, o1 = { c.x + cosf(a1) * r1, c.y, c.z + sinf(a1) * r1 };
        rlVertex3f(i0.x, i0.y, i0.z); rlVertex3f(o1.x, o1.y, o1.z); rlVertex3f(o0.x, o0.y, o0.z);
        rlVertex3f(i0.x, i0.y, i0.z); rlVertex3f(i1.x, i1.y, i1.z); rlVertex3f(o1.x, o1.y, o1.z);
    }
    rlEnd();
}

static void drawSelectionMarkers(void)
{
    GamePlayer *me = &game.players[0][game.selected_player];
    if (me->off) return;
    float pulse = 0.5f + 0.5f * sinf((float)GetTime() * 6.0f);
    Vector3 c = W(me->x, 0.05f, me->z);
    rlDisableBackfaceCulling();
    groundRing(c, 0.62f, 0.86f, (Color){ 255, 220, 0, 235 });
    groundRing(c, 0.86f, 0.98f + 0.08f * pulse, (Color){ 20, 20, 20, 150 });
    /* facing tick on the ring */
    Vector3 f = { me->facing_x, 0, me->facing_z };
    if (Vector3Length(f) > 0.01f) {
        f = Vector3Normalize(f);
        Vector3 tip = Vector3Add(c, Vector3Scale(f, 1.35f)), base = Vector3Add(c, Vector3Scale(f, 0.95f)), side = { -f.z * 0.28f, 0, f.x * 0.28f };
        DrawTriangle3D(tip, Vector3Add(base, side), Vector3Subtract(base, side), (Color){ 255, 220, 0, 235 });
    }
    /* marker above the head: a downward arrow that bobs */
    Vector3 hd = W(me->x, 2.35f + 0.08f * pulse, me->z);
    if (haveModel && boneHead >= 0) {
        AnimState *s = &as[game.selected_player];
        hd = boneWorld(s, boneHead, me->x, me->z, yawOf(me->facing_x, me->facing_z));
        hd.y += 0.42f + 0.06f * pulse;
    }
    DrawCylinderEx(Vector3Add(hd, (Vector3){ 0, 0.42f, 0 }), hd, 0.17f, 0.0f, 4, (Color){ 255, 220, 0, 255 });
    DrawCylinderWiresEx(Vector3Add(hd, (Vector3){ 0, 0.42f, 0 }), hd, 0.17f, 0.0f, 4, (Color){ 90, 60, 0, 255 });
    /* switch flash: a wide ring that closes in on the new player */
    if (switchFlash > 0) {
        float k = switchFlash / 0.7f;
        groundRing(c, 0.9f + 2.2f * k, 1.05f + 2.4f * k, Fade((Color){ 255, 220, 0, 255 }, 0.9f * k));
    }
    /* pass targets: hand pass (cyan); kick pass while the kick charges (orange) */
    int t = passTarget();
    if (t >= 0 && charge < 0) {
        GamePlayer *o = &game.players[0][t];
        groundRing(W(o->x, 0.05f, o->z), 0.55f, 0.72f + 0.05f * pulse, (Color){ 80, 230, 255, 220 });
    }
    if (game.has_ball && charge >= 0 && !chargeLow && assistKick >= 0) {
        GamePlayer *o = &game.players[0][assistKick];
        groundRing(W(o->x, 0.05f, o->z), 0.6f, 0.85f + 0.06f * pulse, (Color){ 255, 150, 30, 230 });
    }
    rlEnableBackfaceCulling();
}

static int hiddenOff(int team, int i)
{
    GamePlayer *p = &game.players[team][i];
    if (p->off != 2) return 0;
    float bx = GAME_PITCH_LENGTH * 0.5f + (team == 0 ? -1.0f : 1.0f) * (7.0f + (float)i * 0.9f);
    return fabsf(p->x - bx) < 0.8f && fabsf(p->z - (-6.5f)) < 0.8f;   /* reached the tunnel */
}

static void drawWorld(float dt)
{
    drawSky(cam);
    lightingBegin(cam, (float)GetTime());
    if (!(benchSkip & 1)) drawStadium();
    if (game.restart_pending && game.restart_type == GAME_RESTART_KICKOUT) {
        float gx = game.ball_team == 0 ? 0.0f : GAME_PITCH_LENGTH;
        drawArc(gx, GAME_SCORING_ARC, 90.0f, 0.12f, YELLOW);        /* highlight the 40m arc */
        DrawCircle3D(W(game.ball.x, 0.04f, game.ball.z), GAME_KICKOUT_ARC_RADIUS, (Vector3){ 1, 0, 0 }, 90, GOLD);
    }
    if (game.restart_pending && game.restart_type != GAME_RESTART_KICKOUT)
        DrawCircle3D(W(game.ball.x, 0.04f, game.ball.z), GAME_KICKOUT_ARC_RADIUS, (Vector3){ 1, 0, 0 }, 90, (Color){ 255, 255, 255, 120 });

    for (int team = 0; team < 2; team++)
        for (int i = 0; i < GAME_TEAM_SIZE; i++) {
            GamePlayer *p = &game.players[team][i];
            AnimState *s = &as[team * GAME_TEAM_SIZE + i];
            float dx = p->x - s->lastX, dz = p->z - s->lastZ;
            float sp = dt > 0 ? sqrtf(dx * dx + dz * dz) / dt : 0;
            if (sp > 15.0f) sp = 0;          /* teleport (restart) */
            s->speed = Lerp(s->speed, sp, 0.25f);
            s->lastX = p->x; s->lastZ = p->z;
            if (hiddenOff(team, i) || (benchSkip & 2)) continue;
            float yaw = yawOf(p->facing_x, p->facing_z);
            if (p->off && s->speed > 0.6f && (dx * dx + dz * dz) > 1e-6f) yaw = yawOf(dx, dz);
            if (p->action == GAME_ACT_DIVE) yaw += (float)game.keeper_guess * PI / 2 * (team == 0 ? 1.0f : -1.0f);
            int clip; float t;
            desiredClip(team, i, p, s, dt, &clip, &t);
            int kit = i == 0 ? (team ? KIT_GK_AWAY : KIT_GK_HOME) : (team ? KIT_AWAY : KIT_HOME);
            Vector3 at = W(p->x, 0, p->z);
            if (Vector3Distance(at, cam.target) > 95.0f && camMode != 4 && !camOverride) { s->clip = clip; continue; }
            if (!inView(Vector3Add(at, (Vector3){ 0, 1.0f, 0 }), 1.6f)) { s->clip = clip; continue; }   /* off-screen: skip pose + draw */
            drawCharacter(s, p->x, p->z, yaw, kit, dt, clip, t);
        }
    drawOfficials(dt);
    if (showMarkers) drawSelectionMarkers();

    /* ball: in the carrier's hands / on the foot, otherwise physics position */
    if (game.ball_team >= 0 && game.ball_player >= 0 && haveModel)
        ballDrawPos = carriedBall(game.ball_team, game.ball_player);
    else
        ballDrawPos = W(game.ball.x, fmaxf(game.ball.height, BALL_R), game.ball.z);
    drawBallLit(ballDrawPos);
}

/* ---- match events -> sound + commentary --------------------------------------- */
static const char *teamName(int t) { return game_team_name(t == 0 ? game.home_team : game.away_team); }

static void onGameEvent(GameEvent ev)
{
    if (training) {
        if (ev == GAME_EVENT_POINT) trainPoints++, trainShots++;
        else if (ev == GAME_EVENT_TWO_POINT) trainPoints += 2, trainShots++;
        else if (ev == GAME_EVENT_GOAL) trainGoals++, trainShots++;
        else if (ev == GAME_EVENT_WIDE || ev == GAME_EVENT_PENALTY_SAVED) trainWides++, trainShots++;
    }
    int t = game.event_team >= 0 ? game.event_team : 0;
    int kt = game.last_release_team >= 0 ? game.last_release_team : t, kp = game.last_release_player;
    if ((ev == GAME_EVENT_POINT || ev == GAME_EVENT_TWO_POINT || ev == GAME_EVENT_GOAL) && game.last_release_team >= 0) t = kt;   /* event_team is the kick-out side */
    const char *T = teamName(t), *O = teamName(1 - t);
    switch (ev) {
    case GAME_EVENT_POINT: {
        const char *o[] = { "%s split the posts - a lovely point from #%d.", "Over the bar! #%d with the point for %s.", "Point for %s, and the Hill is on its feet." };
        int k = GetRandomValue(0, 2);
        if (k == 0) commentarySay(ev, o[0], T, kp + 1); else if (k == 1) commentarySay(ev, o[1], kp + 1, T); else commentarySay(ev, o[2], T);
        sfxPlay(SND_CHEER, 0.9f); crowdSurge(0.6f, 3.0f);
        celebTeam = kt; celebIdx = kp; celebT = 2.6f;
        break; }
    case GAME_EVENT_TWO_POINT:
        commentarySay(ev, "From outside the arc! Two points for %s - what a strike from #%d!", T, kp + 1);
        sfxPlay(SND_ROAR, 1.0f); crowdSurge(0.8f, 4.0f); celebTeam = kt; celebIdx = kp; celebT = 2.6f;
        break;
    case GAME_EVENT_GOAL:
        commentarySay(ev, "GOAL! %s have the green flag waving - #%d buries it!", T, kp + 1);
        sfxPlay(SND_ROAR, 1.2f); crowdSurge(1.0f, 5.0f); celebTeam = kt; celebIdx = kp; celebT = 2.6f;
        break;
    case GAME_EVENT_WIDE: commentarySay(ev, "Wide. %s will be disappointed with that one.", O); sfxPlay(SND_GROAN, 0.7f); break;
    case GAME_EVENT_FREE: case GAME_EVENT_FOUL_TACKLE:
        commentarySay(ev, "The referee blows for a free to %s.", T); sfxPlay(SND_WHISTLE, 0.8f); break;
    case GAME_EVENT_FOUR_STEPS: case GAME_EVENT_ILLEGAL_BOUNCE:
        commentarySay(ev, "Overcarried - too many steps, free out to %s.", T); sfxPlay(SND_WHISTLE, 0.8f); break;
    case GAME_EVENT_YELLOW_CARD:
        commentarySay(ev, "Yellow card. #%d of %s goes in the book.", game.card_player + 1, teamName(game.card_team));
        sfxPlay(SND_WHISTLE, 0.8f); sfxPlay(SND_OOH, 0.5f); break;
    case GAME_EVENT_BLACK_CARD:
        commentarySay(ev, "Black card! Cynical from #%d - ten minutes in the bin, %s down to %d.", game.card_player + 1, teamName(game.card_team), game_players_on(&game, game.card_team));
        sfxPlay(SND_WHISTLE, 0.9f); sfxPlay(SND_OOH, 0.8f); crowdSurge(0.5f, 2.0f); break;
    case GAME_EVENT_BLACK_PENALTY:
        commentarySay(ev, "Black card AND a penalty - that pull-down denied a clear goal chance!");
        sfxPlay(SND_WHISTLE, 0.9f); sfxPlay(SND_ROAR, 0.7f); crowdSurge(0.7f, 3.0f); break;
    case GAME_EVENT_RED_CARD: case GAME_EVENT_SECOND_YELLOW:
        commentarySay(ev, ev == GAME_EVENT_RED_CARD ? "Red card! #%d of %s is sent off - you cannot do that." : "That's a second card for #%d of %s - he's off.",
                      game.card_player + 1, teamName(game.card_team));
        sfxPlay(SND_WHISTLE_DOUBLE, 1.0f); sfxPlay(SND_ROAR, 0.6f); crowdSurge(0.7f, 3.0f); break;
    case GAME_EVENT_SIN_BIN_OVER: commentarySay(ev, "The sin bin is over - %s back to full strength.", T); break;
    case GAME_EVENT_ADVANCED_MARK: commentarySay(ev, "Clean catch inside the twenty - advanced mark to %s.", T); sfxPlay(SND_WHISTLE, 0.6f); break;
    case GAME_EVENT_KICKOUT_MARK: commentarySay(ev, "Caught clean from the kick-out - that's a mark for %s.", T); sfxPlay(SND_WHISTLE, 0.6f); break;
    case GAME_EVENT_DISSENT: commentarySay(ev, "Dissent! The free is brought forward fifty metres."); sfxPlay(SND_WHISTLE_DOUBLE, 0.8f); sfxPlay(SND_OOH, 0.6f); break;
    case GAME_EVENT_BACK_PASS: commentarySay(ev, "Back-pass to the keeper - that's a free to %s.", T); sfxPlay(SND_WHISTLE, 0.8f); break;
    case GAME_EVENT_PENALTY: commentarySay(ev, "Penalty to %s!", T); sfxPlay(SND_WHISTLE_DOUBLE, 0.9f); crowdSurge(0.7f, 4.0f); break;
    case GAME_EVENT_PENALTY_SAVED: commentarySay(ev, "Saved! The keeper guesses right!"); sfxPlay(SND_ROAR, 0.8f); crowdSurge(0.8f, 3.0f); break;
    case GAME_EVENT_HIGH_FIELD: commentarySay(ev, "Great high fielding by %s.", T); sfxPlay(SND_CHEER, 0.4f); break;
    case GAME_EVENT_TACKLE: commentarySay(ev, "Turnover! %s win it back with a great tackle.", T); sfxPlay(SND_THUD, 0.6f); sfxPlay(SND_CHEER, 0.3f); break;
    case GAME_EVENT_KICKOUT: commentarySay(ev, "Kick-out for %s.", T); break;
    case GAME_EVENT_FORTY_FIVE: commentarySay(ev, "Off a defender - 45 to %s.", T); sfxPlay(SND_WHISTLE, 0.6f); break;
    case GAME_EVENT_SIDELINE: commentarySay(ev, "Out over the sideline, %s ball.", T); break;
    case GAME_EVENT_THROW_IN: commentarySay(ev, "The referee throws it in and we're under way!"); sfxPlay(SND_WHISTLE, 0.9f); crowdSurge(0.5f, 2.0f); break;
    case GAME_EVENT_SOLO_AND_GO: commentarySay(ev, "Quick free taken - solo and go by %s.", T); break;
    case GAME_EVENT_THREE_V_THREE: commentarySay(ev, "Three-versus-three breached - free to %s.", T); sfxPlay(SND_WHISTLE, 0.7f); break;
    default: break;
    }
}

/* ---- scripted verification run (--screenshots) ------------------------------ */
static void scenarioCarry(int team, int idx, float x, float z)
{
    GamePlayer *p = &game.players[team][idx];
    game.restart_pending = 0; game.restart_type = GAME_RESTART_NONE;
    game.card_time = 0;
    p->x = x; p->z = z; p->facing_x = team == 0 ? 1.0f : -1.0f; p->facing_z = 0;
    game.ball_team = team; game.ball_player = idx; game.ball.in_flight = 0;
    game.kickout_in_progress = 0;
    if (team == 0) game_select_player(&game, idx);
    for (int t = 0; t < 2; t++) for (int i = 0; i < GAME_TEAM_SIZE; i++) {
        GamePlayer *q = &game.players[t][i];
        q->action = GAME_ACT_NONE;
        if (!(t == team && i == idx) && fabsf(q->x - x) < 9 && fabsf(q->z - z) < 9) q->z += 12;
    }
}

static void newMatch(void)
{
    game_init(&game);
    game.enforce_three_v_three = 1;
    training = 0;
    game.ai_support = 1;                  /* v3.2 support runs + marking */
    game.on_release = onRelease;
    game.sin_bin_seconds = SIN_BIN_REAL;
    game.dissent_chance = 0.05f;
    game_start_half(&game, 1);
    clockT = 0; fullTime = 0; celebT = 0;
    for (int i = 0; i < 2 * GAME_TEAM_SIZE; i++) { as[i].lastX = game.players[i / GAME_TEAM_SIZE][i % GAME_TEAM_SIZE].x; as[i].lastZ = game.players[i / GAME_TEAM_SIZE][i % GAME_TEAM_SIZE].z; }
}

/* ---- training: you, two team-mates to pass to, and their keeper ---------- */
#define TRAIN_ME 10
static float trainResetT = 0;
static void trainingPlace(void)
{
    scenarioCarry(0, TRAIN_ME, 100.0f, HW);
    game.players[0][8].x = 108; game.players[0][8].z = HW - 14;    /* wide left  */
    game.players[0][12].x = 112; game.players[0][12].z = HW + 12;  /* wide right */
    GamePlayer *k = &game.players[1][0]; k->x = GAME_PITCH_LENGTH - 1.5f; k->z = HW;
    trainResetT = 0;
}
static void newTraining(void)
{
    newMatch();
    training = 1;
    game.enforce_three_v_three = 0;
    trainPoints = trainGoals = trainShots = trainWides = 0;
    for (int t = 0; t < 2; t++)
        for (int i = 0; i < GAME_TEAM_SIZE; i++) {
            int keep = t == 0 ? (i == TRAIN_ME || i == 8 || i == 12) : (i == 0);
            if (keep) continue;
            GamePlayer *p = &game.players[t][i];
            p->off = 2; p->sin_bin = 0;
            p->x = GAME_PITCH_LENGTH * 0.5f + (t == 0 ? -1.0f : 1.0f) * (7.0f + (float)i * 0.9f);
            p->z = -6.5f;
        }
    for (int i = 0; i < 2 * GAME_TEAM_SIZE; i++) { as[i].lastX = game.players[i / GAME_TEAM_SIZE][i % GAME_TEAM_SIZE].x; as[i].lastZ = game.players[i / GAME_TEAM_SIZE][i % GAME_TEAM_SIZE].z; }
    trainingPlace();
    camMode = 2;
}
static void trainingTick(float dt)
{
    /* ball dead, scored, out, with the keeper, or loose for a while -> back to you */
    int lost = game.restart_pending || game.ball_team == 1 || game.card_time > 0;
    int loose = game.ball_team < 0 && !game.ball.in_flight;
    if (lost || loose) trainResetT += dt; else trainResetT = 0;
    if ((lost && trainResetT > 1.6f) || (loose && trainResetT > 5.0f)) {
        GamePlayer *me = &game.players[0][TRAIN_ME];
        float x = Clamp(me->x, 60.0f, GAME_PITCH_LENGTH - 25.0f), z = Clamp(me->z, 8.0f, GAME_PITCH_WIDTH - 8.0f);
        if (game.restart_pending || game.ball_team == 1) { x = 100.0f; z = HW; }
        trainingPlace();
        me->x = x; me->z = z;
    }
    game_select_player(&game, TRAIN_ME);
}
static void drawTrainingHUD(int sw, int sh)
{
    int ty = 66;
    DrawRectangle(sw - 330, ty, 320, 112, (Color){ 0, 0, 0, 170 });
    DrawText("TRAINING", sw - 318, ty + 6, 24, GOLD);
    DrawText(TextFormat("Points %d   Goals %d", trainPoints, trainGoals), sw - 318, ty + 36, 20, RAYWHITE);
    DrawText(TextFormat("Shots %d   Wides/saved %d", trainShots, trainWides), sw - 318, ty + 60, 18, LIGHTGRAY);
    DrawText("Esc: menu   Back/F1: controller test", sw - 318, ty + 86, 15, GRAY);
    int pd = padId >= 0;
    const char *with[] = { pd ? "B" : "R/B", "solo / bounce", pd ? "A" : "E", "hand pass (cyan ring)", pd ? "X hold" : "Space hold", "kick: release for power",
                           pd ? "Y" : "G", "shoot at the posts", pd ? "R2" : "L", "power kick", pd ? "R1" : "Shift", "sprint" };
    const char *without[] = { pd ? "A" : "E/F", "pick up the ball", pd ? "X" : "J", "jump / high catch", pd ? "L1" : "Q", "switch player", pd ? "L-stick" : "WASD", "move" };
    int y = sh - 60 - 6 * 22, px = sw - 340;
    DrawRectangle(px, y - 34, 330, 6 * 22 + 40, (Color){ 0, 0, 0, 160 });
    DrawText(game.has_ball ? "WITH THE BALL" : "WITHOUT THE BALL", px + 10, y - 28, 18, SKYBLUE);
    const char **L = game.has_ball ? with : without;
    int n = game.has_ball ? 6 : 4;
    for (int i = 0; i < n; i++) {
        int bw = MeasureText(L[i * 2], 16) + 14;
        DrawRectangleRounded((Rectangle){ (float)px + 10, (float)(y + i * 22), (float)bw, 19 }, 0.4f, 6, (Color){ 230, 230, 235, 255 });
        DrawText(L[i * 2], px + 17, y + i * 22 + 2, 16, BLACK);
        DrawText(L[i * 2 + 1], px + 20 + bw, y + i * 22 + 2, 16, RAYWHITE);
    }
}

enum { ST_INTRO, ST_MENU, ST_PLAY };
#define INTRO_SECONDS 20.0f

static void drawTitle(int sw, int sh, float t, const char *shot)
{
    float a = Clamp(t * 0.8f, 0, 1);
    if (t < 1.0f) DrawRectangle(0, 0, sw, sh, Fade(BLACK, 1.0f - t));
    DrawRectangle(0, sh - 150, sw, 110, Fade(BLACK, 0.45f * a));
    DrawText("SUNDAY LEAGUE", 60, sh - 142, 56, Fade(GOLD, a));
    DrawText("GAELIC FOOTBALL", 64, sh - 86, 34, Fade(RAYWHITE, a));
    DrawText(TextFormat("%s  v  %s   -   live from HQ", game_team_name(game.home_team), game_team_name(game.away_team)), 470, sh - 78, 20, Fade(LIGHTGRAY, a));
    if (((int)(t * 2)) % 2 == 0) DrawText("Press ENTER / START / A", sw - 330, sh - 132, 22, Fade(RAYWHITE, a));
    DrawRectangle(sw - 150, 16, 134, 26, Fade((Color){ 200, 20, 30, 255 }, 0.9f));
    DrawText(TextFormat("LIVE  %s", shot), sw - 142, 21, 16, RAYWHITE);
}

static int menuSel = 0;
#define MENU_N 5
static void drawMenu(int sw, int sh)
{
    const char *items[MENU_N] = { "PLAY MATCH", "TRAINING", "CONTROLLER TEST", TextFormat("GRAPHICS: %s", QUALITY_NAMES[gfxQuality]), "QUIT" };
    DrawRectangle(0, 0, sw, sh, Fade(BLACK, 0.35f));
    DrawText("SUNDAY LEAGUE", sw / 2 - MeasureText("SUNDAY LEAGUE", 64) / 2, 70, 64, GOLD);
    DrawText("GAELIC FOOTBALL", sw / 2 - MeasureText("GAELIC FOOTBALL", 36) / 2, 140, 36, RAYWHITE);
    for (int i = 0; i < MENU_N; i++) {
        int w = MeasureText(items[i], 32), y = 220 + i * 54;
        if (i == menuSel) DrawRectangle(sw / 2 - 190, y - 8, 380, 46, Fade((Color){ 30, 66, 150, 255 }, 0.9f));
        DrawText(items[i], sw / 2 - w / 2, y, 32, i == menuSel ? GOLD : RAYWHITE);
    }
    const char *st = padStatusText();
    DrawText(st, sw / 2 - MeasureText(st, 18) / 2, 500, 18, padId >= 0 ? LIME : (Color){ 255, 140, 110, 255 });
    const char *hint = menuSel == 3 ? "Left/Right or A to change. Low = fastest. Try Medium/High if F3 shows 60 fps." :
                       "Up/Down or D-pad, Enter / A to select.  F2 graphics  F3 FPS";
    DrawText(hint, sw / 2 - MeasureText(hint, 18) / 2, 528, 18, GRAY);
}

/* ---- settings / quality -------------------------------------------------------- */
static void loadSettings(void)
{
    gfxQuality = 0;
    char *t = FileExists("settings.txt") ? LoadFileText("settings.txt") : NULL;
    if (t) {
        const char *q = strstr(t, "quality="); if (q) gfxQuality = Clamp(atoi(q + 8), 0, 2);
        if (strstr(t, "skin=cpu")) forceCpuSkin = 1;
        UnloadFileText(t);
    }
}
static void saveSettings(void) { SaveFileText("settings.txt", (char *)TextFormat("quality=%d\nskin=%s\n", gfxQuality, forceCpuSkin ? "cpu" : "gpu")); }
/* F4: switch character skinning GPU <-> CPU at runtime (whichever is faster on this PC) */
static void setSkinMode(int gpu, int save)
{
    if (!haveModel || !haveLit) return;
    if (gpu && !gpuSkinAvailable) { commentarySay(0, "GPU skinning is not available here"); return; }
    gpuSkin = gpu; forceCpuSkin = !gpu;
    for (int m = 0; m < model.materialCount; m++) model.materials[m].shader = gpuSkin ? skinShader : litShader;
    if (gpuSkin)   /* the CPU path wrote posed vertices into the VBOs: restore the bind pose */
        for (int i = 0; i < model.meshCount; i++) {
            Mesh *me = &model.meshes[i];
            rlUpdateVertexBuffer(me->vboId[0], me->vertices, me->vertexCount * 3 * sizeof(float), 0);
            if (me->normals) rlUpdateVertexBuffer(me->vboId[2], me->normals, me->vertexCount * 3 * sizeof(float), 0);
        }
    if (save) saveSettings();
    commentarySay(0, "Character skinning: %s (F4 to switch, F3 to compare FPS)", gpuSkin ? "GPU" : "CPU");
}
static void setQuality(int q, int save)
{
    gfxQuality = ((q % 3) + 3) % 3;
    if (save) saveSettings();
    commentarySay(0, "Graphics: %s%s", QUALITY_NAMES[gfxQuality], gfxQuality == 2 ? " (MSAA takes effect on restart)" : "");
}

static void drawPerf(int sw)
{
    int x = sw - 300, y = 186;
    DrawRectangle(x, y, 290, 176, (Color){ 0, 0, 0, 190 });
    int fps = GetFPS();
    DrawText(TextFormat("%d FPS  (%.1f ms)", fps, pFrame), x + 10, y + 8, 24, fps >= 55 ? LIME : fps >= 30 ? YELLOW : RED);
    DrawText(TextFormat("quality %s (F2)  skinning %s (F4)", QUALITY_NAMES[gfxQuality], gpuSkin ? "GPU" : "CPU"), x + 10, y + 38, 15, RAYWHITE);
    DrawText(TextFormat("game update  %5.2f ms", pUpdate), x + 10, y + 60, 15, LIGHTGRAY);
    DrawText(TextFormat("skin/pose    %5.2f ms  (%d chars)", pSkin, skinnedThisFrame), x + 10, y + 78, 15, LIGHTGRAY);
    DrawText(TextFormat("3D submit    %5.2f ms", pWorld), x + 10, y + 96, 15, LIGHTGRAY);
    DrawText(TextFormat("HUD          %5.2f ms", pHud), x + 10, y + 114, 15, LIGHTGRAY);
    DrawText(TextFormat("GPU+swap     %5.2f ms", pSwap), x + 10, y + 132, 15, LIGHTGRAY);
    DrawText(TextFormat("%dx%d   F3 hide", GetRenderWidth(), GetRenderHeight()), x + 10, y + 152, 14, GRAY);
}

/* ---- --shots31: scripted v3.1 checks with a simulated pad ------------------- */
static void simPad(int on)
{
    pad.simulated = on; pad.id = on ? 0 : -1; padId = pad.id; pad.mapped = 1;
    snprintf(pad.name, sizeof pad.name, "EasySMX Controller");
    snprintf(pad.guid, sizeof pad.guid, "03000000bc2000000091000000000000");
    memset(pad.btn, 0, sizeof pad.btn); memset(pad.axis, 0, sizeof pad.axis);
    pad.axis[4] = pad.axis[5] = -1;
}
static void simButtons(const int *b, int n) { memset(pad.btn, 0, sizeof pad.btn); for (int i = 0; i < n; i++) pad.btn[b[i]] = 1; }
static void shotScript31(int frame, int *state, float *stateT, int *introDemo)
{
    static const char *pending = NULL; static int pendingAt = -1;
    static GameEvent lastLogged = GAME_EVENT_NONE; static float lastT = -1;
    #define SHOT(name) do { pending = name; pendingAt = frame + 2; } while (0)
    if (frame == pendingAt && pending) { TakeScreenshot(pending); TraceLog(LOG_WARNING, "SHOTS31: %s", pending); pending = NULL; }
    if (game.event != GAME_EVENT_NONE && (game.event != lastLogged || game.event_time > lastT + 0.05f)) {
        TraceLog(LOG_WARNING, "SHOTS31: frame %d event %d (%s) team %d", frame, game.event, game_event_text(game.event), game.event_team);
    }
    lastLogged = game.event; lastT = game.event_time;
    if (frame == 2) { *state = ST_MENU; *stateT = 0; *introDemo = 1; gfxQuality = 0; simPad(1); }
    if (frame == 40) SHOT("v31_01_menu.png");
    if (frame == 50) {               /* controller test screen with live simulated input */
        showControls = 1;
        int b[] = { GAMEPAD_BUTTON_RIGHT_FACE_DOWN, GAMEPAD_BUTTON_LEFT_TRIGGER_1, GAMEPAD_BUTTON_LEFT_FACE_UP, GAMEPAD_BUTTON_MIDDLE_RIGHT };
        simButtons(b, 4);
        pad.axis[0] = 0.72f; pad.axis[1] = -0.55f; pad.axis[2] = -0.35f; pad.axis[3] = 0.10f; pad.axis[4] = -1.0f; pad.axis[5] = 0.86f;
        pad.btn[GAMEPAD_BUTTON_RIGHT_TRIGGER_2] = 1;
        pad.nRawAxes = 6; pad.nRawBtns = 12; pad.nRawHats = 1;
        float ra[6] = { 0.72f, -0.55f, -0.35f, 0.10f, -1.0f, 0.86f }; memcpy(pad.rawAxes, ra, sizeof ra);
        memset(pad.rawBtns, 0, sizeof pad.rawBtns); pad.rawBtns[2] = pad.rawBtns[4] = pad.rawBtns[7] = pad.rawBtns[9] = 1; pad.rawHats[0] = 1;
    }
    if (frame == 60) SHOT("v31_02_controller_test.png");
    if (frame == 70) { showControls = 0; simButtons(NULL, 0); memset(pad.axis, 0, sizeof pad.axis); pad.axis[4] = pad.axis[5] = -1; pad.nRawAxes = pad.nRawBtns = pad.nRawHats = 0; }
    /* training, driven only by the simulated pad */
    if (frame == 80) { newTraining(); demo = 0; *state = ST_PLAY; *introDemo = 0; gfxQuality = 1; }
    if (frame > 80 && frame < 300) pad.axis[1] = -0.8f;                     /* run forward */
    if (frame == 120) { int b[] = { GAMEPAD_BUTTON_RIGHT_FACE_RIGHT }; simButtons(b, 1); TraceLog(LOG_WARNING, "SHOTS31: press B (expect bounce)"); }
    if (frame == 122) simButtons(NULL, 0);
    if (frame == 150) SHOT("v31_03_training_ring_prompts.png");
    if (frame == 190) { int b[] = { GAMEPAD_BUTTON_RIGHT_FACE_RIGHT }; simButtons(b, 1); TraceLog(LOG_WARNING, "SHOTS31: press B (expect solo)"); }
    if (frame == 192) simButtons(NULL, 0);
    if (frame == 230) { int b[] = { GAMEPAD_BUTTON_RIGHT_FACE_DOWN }; simButtons(b, 1); TraceLog(LOG_WARNING, "SHOTS31: press A (expect hand pass)"); }
    if (frame == 232) simButtons(NULL, 0);
    if (frame == 300) { trainingPlace(); pad.axis[1] = 0; }
    if (frame == 320) { int b[] = { GAMEPAD_BUTTON_RIGHT_FACE_LEFT }; simButtons(b, 1); TraceLog(LOG_WARNING, "SHOTS31: hold X (charge)"); }
    if (frame == 345) SHOT("v31_04_training_kick_charge.png");
    if (frame == 360) { simButtons(NULL, 0); TraceLog(LOG_WARNING, "SHOTS31: release X after %.2f s (expect kick)", 40 / 60.0f); }
    if (frame == 460) { trainingPlace(); int b[] = { GAMEPAD_BUTTON_RIGHT_TRIGGER_2 }; simButtons(b, 1); pad.axis[5] = 0.9f; TraceLog(LOG_WARNING, "SHOTS31: R2 axis 0.9 (expect power kick)"); }
    if (frame == 462) { simButtons(NULL, 0); pad.axis[5] = -1; }
    if (frame == 560) { trainingPlace(); int b[] = { GAMEPAD_BUTTON_RIGHT_FACE_UP }; simButtons(b, 1); TraceLog(LOG_WARNING, "SHOTS31: press Y (expect shot at posts)"); }
    if (frame == 562) simButtons(NULL, 0);
    if (frame == 660) TraceLog(LOG_WARNING, "SHOTS31: training tally points %d goals %d shots %d wides %d", trainPoints, trainGoals, trainShots, trainWides);
    /* match: ring + F3 overlay on Medium */
    if (frame == 670) { newMatch(); demo = 0; camMode = 1; showPerf = 1; gfxQuality = 1; scenarioCarry(0, 9, 80, 38); }
    if (frame > 670 && frame < 760) pad.axis[0] = 0.5f; else if (frame >= 760) pad.axis[0] = 0;
    if (frame == 740) SHOT("v31_05_match_ring_f3_medium.png");
    if (frame == 750) { camMode = 0; }
    if (frame == 790) SHOT("v31_06_broadcast_ring.png");
    if (frame == 800) { showPerf = 0; camMode = 5; scenarioCarry(0, 9, 80, 38); gfxQuality = 2; }
    if (frame == 830) SHOT("v31_07_shadows_high.png");
    if (frame == 840) { gfxQuality = 1; setSkinMode(0, 0); }
    if (frame == 860) SHOT("v31_08_shadows_medium.png");
    if (frame == 870) { gfxQuality = 0; setSkinMode(1, 0); }
    if (frame == 890) SHOT("v31_09_shadows_low_blob.png");
    if (frame == 900) { simPad(0); showControls = 1; }
    if (frame == 910) SHOT("v31_10_controller_test_no_pad.png");
    if (frame > 920) CloseWindow(), exit(0);
    #undef SHOT
}

/* ---- --shots32: scripted v3.2 checks (camera framing, switching, assists) --- */
static void shotScript32(int frame, int *state, float *stateT, int *introDemo)
{
    static const char *pending = NULL; static int pendingAt = -1;
    static GameEvent lastLogged = GAME_EVENT_NONE; static float lastT = -1;
    static int lastSel = -1, lastBTl = -9, lastBPl = -9;
    #define SHOT(name) do { pending = name; pendingAt = frame + 2; } while (0)
    #define LOG(...) TraceLog(LOG_WARNING, "SHOTS32: " __VA_ARGS__)
    (void)stateT;
    if (frame == pendingAt && pending) { TakeScreenshot(pending); LOG("%s  (camOpen %.2f fovy %.1f camDist %.1f)", pending, camOpen, cam.fovy, Vector3Distance(cam.position, cam.target)); pending = NULL; }
    if (game.event != GAME_EVENT_NONE && (game.event != lastLogged || game.event_time > lastT + 0.05f))
        LOG("frame %d event %d (%s) team %d", frame, game.event, game_event_text(game.event), game.event_team);
    lastLogged = game.event; lastT = game.event_time;
    if (*state == ST_PLAY && (game.selected_player != lastSel || game.ball_team != lastBTl || game.ball_player != lastBPl)) {
        LOG("frame %d ball team %d player %d flight %d | you control #%d", frame, game.ball_team, game.ball_player, game.ball.in_flight, game.selected_player + 1);
        lastSel = game.selected_player; lastBTl = game.ball_team; lastBPl = game.ball_player;
    }
    if (frame == 2) { newMatch(); *state = ST_PLAY; *introDemo = 0; demo = 0; gfxQuality = 0; simPad(1); camMode = 0; }
    /* 1. carrier in a tight contest: close framing */
    if (frame == 10) { scenarioCarry(0, 9, 80, 38); game.players[1][7].x = 82.5f; game.players[1][7].z = 39; game.players[1][8].x = 81; game.players[1][8].z = 35.5f; }
    if (frame > 10 && frame < 70) pad.axis[0] = 0.25f;
    if (frame == 68) SHOT("v32_01_cam_tight_contest.png");
    /* 2. hand-pass assist: stick toward a team-mate, cyan ring, A */
    if (frame == 72) { scenarioCarry(0, 9, 70, 40); pad.axis[0] = 0;
                       game.players[0][10].x = 78; game.players[0][10].z = 33; game.players[0][11].x = 80; game.players[0][11].z = 50; }
    if (frame > 72 && frame < 112) { pad.axis[0] = 0.7f; pad.axis[1] = -0.55f; }   /* up-right on the stick = toward +x, away from camera */
    if (frame == 104) { SHOT("v32_02_handpass_assist_ring.png"); LOG("hand-pass assist target #%d (kick target #%d)", assistHand + 1, assistKick + 1); }
    if (frame == 110) { int b[] = { GAMEPAD_BUTTON_RIGHT_FACE_DOWN }; simButtons(b, 1); LOG("press A: hand pass"); }
    if (frame == 112) { simButtons(NULL, 0); pad.axis[0] = pad.axis[1] = 0; }
    if (frame == 170) LOG("after hand pass: ball team %d player %d, you control #%d", game.ball_team, game.ball_player, game.selected_player + 1);
    /* 3. long kick pass: hold X toward a forward, ball in the air -> camera widens, control goes to the receiver */
    if (frame == 180) { scenarioCarry(0, 8, 50, 42); game.players[0][13].x = 92; game.players[0][13].z = 40;
                        for (int i = 0; i < GAME_TEAM_SIZE; i++) if (fabsf(game.players[1][i].x - 92) < 6 && fabsf(game.players[1][i].z - 40) < 6) game.players[1][i].z += 10; }
    if (frame > 180 && frame < 250) pad.axis[0] = 0.8f; else if (frame == 250) pad.axis[0] = 0;
    if (frame == 200) { int b[] = { GAMEPAD_BUTTON_RIGHT_FACE_LEFT }; simButtons(b, 1); LOG("hold X (kick pass)"); }
    if (frame == 222) { SHOT("v32_03_kick_charge_target.png"); LOG("kick assist target #%d", assistKick + 1); }
    if (frame == 230) { simButtons(NULL, 0); LOG("release X"); }
    if (frame == 268) SHOT("v32_04_cam_long_kick_wide.png");
    if (frame == 330) LOG("after kick pass: ball team %d player %d, you control #%d", game.ball_team, game.ball_player, game.selected_player + 1);
    /* 4. turnover: the opposition has it, you are far away -> instant switch to the best defender + ring */
    if (frame == 340) { scenarioCarry(0, 13, 120, 30); }
    if (frame == 350) { scenarioCarry(1, 10, 55, 50); LOG("turnover: away #11 carries at 55,50"); }
    if (frame == 392) SHOT("v32_05_turnover_switch_ring.png");
    if (frame == 404) SHOT("v32_06_defending_marking.png");
    /* 5. L1 walks through the nearest players */
    if (frame == 410 || frame == 420) { int b[] = { GAMEPAD_BUTTON_LEFT_TRIGGER_1 }; simButtons(b, 1); }
    if (frame == 412 || frame == 422) { simButtons(NULL, 0); LOG("L1 -> you control #%d", game.selected_player + 1); }
    if (frame == 424) SHOT("v32_07_manual_switch_L1.png");
    /* 6. loose ball near you: pickup magnetism with no stick input */
    if (frame == 440) { scenarioCarry(0, 7, 70, 40); game.ball_team = -1; game.ball_player = -1; game.ball.x = 74; game.ball.z = 41; game.ball.height = GAME_BALL_REST; game.ball.in_flight = 0;
                        game.ball.velocity_x = game.ball.velocity_z = game.ball.velocity_y = 0; game.pickup_delay = 0; game.last_release_team = -1; LOG("loose ball 4 m away, stick idle"); }
    if (frame == 520) LOG("magnetism: ball team %d player %d (you #%d)", game.ball_team, game.ball_player, game.selected_player + 1);
    /* 7. opposition kick goes wide -> kick-out: wide framing, taker selected */
    if (frame == 530) { scenarioCarry(1, 12, 12, 20); game.ball_team = -1; game.ball_player = -1; game.ball.x = 6; game.ball.z = 20; game.ball.height = 3;
                        game.ball.in_flight = 1; game.ball.velocity_x = -18; game.ball.velocity_z = 0; game.ball.velocity_y = 3; game.last_touch_team = 1; game.last_release_team = 1; }
    if (frame == 600) SHOT("v32_08_kickout_wide.png");
    if (frame == 610) { pad.axis[0] = 0.6f; pad.axis[1] = -0.6f; int b[] = { GAMEPAD_BUTTON_RIGHT_FACE_LEFT }; simButtons(b, 1); }
    if (frame == 630) LOG("kick-out: taker #%d, kick assist target #%d", game.selected_player + 1, assistKick + 1);
    if (frame == 640) { simButtons(NULL, 0); pad.axis[0] = pad.axis[1] = 0; }
    if (frame == 670) SHOT("v32_09_kickout_flight.png");
    /* 8. TV close cam in open play for comparison */
    if (frame == 760) { camMode = 1; scenarioCarry(0, 10, 90, 30); }
    if (frame > 760 && frame < 820) pad.axis[0] = 0.7f; else if (frame == 820) pad.axis[0] = 0;
    if (frame == 815) SHOT("v32_10_tvclose_dynamic.png");
    if (frame > 830) CloseWindow(), exit(0);
    #undef SHOT
    #undef LOG
}

int main(int argc, char **argv)
{
    int shots = 0, skipIntro = 0, bench = 0, cliQuality = -1, shots31 = 0, startTraining = 0;
    const char *recordPath = NULL;
    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--screenshots") == 0) shots = 1;
        else if (strcmp(argv[i], "--demo") == 0) cmdDemo = demo = 1, skipIntro = 1;
        else if (strcmp(argv[i], "--cpu-skin") == 0) forceCpuSkin = 1;
        else if (strcmp(argv[i], "--bench-skip") == 0 && i + 1 < argc) benchSkip = atoi(argv[++i]);
        else if (strcmp(argv[i], "--bench") == 0) bench = i + 1 < argc && argv[i + 1][0] != '-' ? atoi(argv[++i]) : 600, skipIntro = 1;
        else if (strcmp(argv[i], "--quality") == 0 && i + 1 < argc) cliQuality = atoi(argv[++i]);
        else if (strcmp(argv[i], "--shots31") == 0) shots31 = 1, skipIntro = 1;
        else if (strcmp(argv[i], "--shots32") == 0) shots31 = 2, skipIntro = 1;
        else if (strcmp(argv[i], "--training") == 0) startTraining = 1, skipIntro = 1;
        else if (strcmp(argv[i], "--no-intro") == 0) skipIntro = 1;
        else if (strcmp(argv[i], "--record-intro") == 0 && i + 1 < argc) recordPath = argv[++i];
    }
    if (recordPath) SetTraceLogLevel(LOG_WARNING);
    ChangeDirectory(GetApplicationDirectory());
    loadSettings();
    if (cliQuality >= 0) gfxQuality = cliQuality % 3;
    unsigned int flags = FLAG_WINDOW_RESIZABLE;
    if (!bench && !shots && !shots31 && !recordPath) flags |= FLAG_VSYNC_HINT;
    if (gfxQuality == 2) flags |= FLAG_MSAA_4X_HINT;
    SetConfigFlags(flags);
    InitWindow(1280, 720, "Sunday League: Gaelic Football");
    SetExitKey(KEY_NULL);
    ChangeDirectory(GetApplicationDirectory());
    SetTargetFPS(bench ? 0 : 60);
    padLoadMappings();
    SetRandomSeed(7);
    rlSetClipPlanes(0.3, 2600.0);

    for (int i = 0; i < C_COUNT; i++) clipIdx[i] = -1;
    if (FileExists(PLAYER_GLB)) {
        model = LoadModel(PLAYER_GLB);
        anims = LoadModelAnimations(PLAYER_GLB, &animCount);
        for (int i = 0; i < animCount; i++)
            for (int k = 0; k < C_COUNT; k++)
                if (strcmp(anims[i].name, CLIP_NAMES[k]) == 0 && IsModelAnimationValid(model, anims[i])) clipIdx[k] = i;
        haveModel = model.meshCount > 0 && MODEL_BONECOUNT(model) <= MAX_BONES;
        for (int k = 0; k < C_COUNT; k++) if (clipIdx[k] < 0) { haveModel = 0; TraceLog(LOG_WARNING, "GAME: clip '%s' missing", CLIP_NAMES[k]); }
    }
    stadiumInit();
    if (haveModel) {
        boneFootL = findBone("foot_l"); boneFootR = findBone("foot_r");
        boneHandL = findBone("hand_l"); boneHandR = findBone("hand_r"); boneHead = findBone("head");
        bonePelvis = findBone("pelvis"); if (bonePelvis < 0) bonePelvis = 0;
        scratch = anims[clipIdx[C_IDLE]];
        scratchPosePtr[0] = scratchPose;
#if RAYLIB_VERSION_MAJOR >= 6
        scratch.keyframeCount = 1; scratch.keyframePoses = scratchPosePtr;
#else
        scratch.frameCount = 1; scratch.framePoses = scratchPosePtr;
#endif
        detectContacts();
        if (haveLit) for (int m = 0; m < model.materialCount; m++) model.materials[m].shader = gpuSkin ? skinShader : litShader;
        TraceLog(LOG_INFO, "GAME: %d clips loaded, %d bones", C_COUNT, MODEL_BONECOUNT(model));
    }
    for (int k = 0; k < KIT_COUNT; k++) {
        kits[k] = LoadTexture(TextFormat("assets/textures/kit_%s.png", KIT_FILES[k]));
        GenTextureMipmaps(&kits[k]); SetTextureFilter(kits[k], TEXTURE_FILTER_TRILINEAR);
    }
    for (int i = 0; i < N_CHAR; i++) { as[i].clip = C_IDLE; as[i].prevClip = -1; as[i].blend = 1; }
    sfxInit(recordPath == NULL);

    newMatch();
    cam.up = (Vector3){ 0, 1, 0 }; cam.fovy = 40; cam.projection = CAMERA_PERSPECTIVE;
    cam.position = (Vector3){ 0, 15, 30 };
    int state = skipIntro ? ST_PLAY : ST_INTRO;
    float stateT = 0;
    int introDemo = 1;                         /* AI v AI during intro and menu */
    if (state == ST_PLAY) introDemo = 0;
    if (bench) { demo = 1; camMode = 0; }
    if (startTraining) newTraining();
    double benchT0 = 0, benchSum[6] = { 0 }; int benchN = 0;

    FILE *rec = NULL, *recWav = NULL;
    long wavSamples = 0;
    if (recordPath) {
        rec = fopen(recordPath, "wb");
        recWav = fopen(TextFormat("%s.wav", recordPath), "wb");
        if (recWav) { unsigned char hdr[44] = { 0 }; fwrite(hdr, 1, 44, recWav); }
    }
    GameEvent lastEv = GAME_EVENT_NONE; float lastEvTime = 0;
    int frame = 0;
    int quit = 0;
    while (!WindowShouldClose() && !quit) {
        double frameStart = GetTime();
        float dt = (shots || shots31 || rec || bench) ? (rec ? 1.0f / 30.0f : 1.0f / 60.0f) : fminf(GetFrameTime(), 1.0f / 30.0f);
        tSkin = tUpdate = tWorld = tHud = tSwap = 0; skinnedThisFrame = 0;
        frame++;
        releaseFlash++;
        stateT += dt;
        padUpdate();
        if (shots31 == 1) shotScript31(frame, &state, &stateT, &introDemo);
        if (shots31 == 2) shotScript32(frame, &state, &stateT, &introDemo);
        int confirm = IsKeyPressed(KEY_ENTER) || IsKeyPressed(KEY_KP_ENTER) || padAnyConfirm();
        if (IsKeyPressed(KEY_F1) || padPressed(GAMEPAD_BUTTON_MIDDLE_LEFT)) showControls = !showControls;
        if (showControls && (IsKeyPressed(KEY_ESCAPE) || padPressed(GAMEPAD_BUTTON_RIGHT_FACE_RIGHT))) showControls = 0;
        if (IsKeyPressed(KEY_F2)) setQuality(gfxQuality + 1, 1);
        if (IsKeyPressed(KEY_F3)) showPerf = !showPerf;
        if (IsKeyPressed(KEY_F4)) setSkinMode(!gpuSkin, 1);

        if (state == ST_INTRO && (stateT >= INTRO_SECONDS || (confirm && !rec))) {
            if (rec) break;
            state = ST_MENU; stateT = 0; confirm = 0;
        }
        if (state == ST_MENU) {
            static float stickHeld = 0;
            float sy = padAxis(GAMEPAD_AXIS_LEFT_Y), sx = padAxis(GAMEPAD_AXIS_LEFT_X);
            int stickUp = 0, stickDown = 0, stickL = 0, stickR = 0;
            if (fabsf(sy) > 0.6f || fabsf(sx) > 0.6f) { if (stickHeld <= 0) { stickUp = sy < -0.6f; stickDown = sy > 0.6f; stickL = sx < -0.6f; stickR = sx > 0.6f; stickHeld = 0.28f; } else stickHeld -= dt; }
            else stickHeld = 0;
            if (!showControls) {
                if (IsKeyPressed(KEY_UP) || IsKeyPressed(KEY_W) || padPressed(GAMEPAD_BUTTON_LEFT_FACE_UP) || stickUp) menuSel = (menuSel + MENU_N - 1) % MENU_N;
                if (IsKeyPressed(KEY_DOWN) || IsKeyPressed(KEY_S) || padPressed(GAMEPAD_BUTTON_LEFT_FACE_DOWN) || stickDown) menuSel = (menuSel + 1) % MENU_N;
                if (menuSel == 3 && (IsKeyPressed(KEY_LEFT) || IsKeyPressed(KEY_A) || padPressed(GAMEPAD_BUTTON_LEFT_FACE_LEFT) || stickL)) setQuality(gfxQuality - 1, 1);
                if (menuSel == 3 && (IsKeyPressed(KEY_RIGHT) || IsKeyPressed(KEY_D) || padPressed(GAMEPAD_BUTTON_LEFT_FACE_RIGHT) || stickR)) setQuality(gfxQuality + 1, 1);
            }
            if (confirm && !showControls) {
                if (menuSel == 0) { newMatch(); demo = cmdDemo; state = ST_PLAY; introDemo = 0; camMode = 0; stateT = 0; commentarySay(0, "Welcome to HQ - %s against %s, and the ball is in.", teamName(0), teamName(1)); }
                else if (menuSel == 1) { newTraining(); demo = 0; state = ST_PLAY; introDemo = 0; stateT = 0; commentarySay(0, "Training: solo, bounce, hand pass and kick at will. The ball comes back to you."); }
                else if (menuSel == 2) showControls = 1;
                else if (menuSel == 3) setQuality(gfxQuality + 1, 1);
                else quit = 1;
                confirm = 0;
            }
        }
        if (state == ST_PLAY) {
            if (IsKeyPressed(KEY_C)) camMode = (camMode + 1) % CAM_COUNT;
            if (padPressed(GAMEPAD_BUTTON_LEFT_FACE_UP)) camMode = (camMode + 1) % CAM_COUNT;
            if (padPressed(GAMEPAD_BUTTON_LEFT_FACE_DOWN)) camMode = (camMode + CAM_COUNT - 1) % CAM_COUNT;
            for (int k = 0; k < CAM_COUNT; k++) if (IsKeyPressed(KEY_ONE + k)) camMode = k;
            if (IsKeyPressed(KEY_T)) autoSolo = !autoSolo;
            if (IsKeyPressed(KEY_P) || (padPressed(GAMEPAD_BUTTON_MIDDLE_RIGHT) && !fullTime)) paused = !paused;
            if (confirm && fullTime) newMatch();
            if (IsKeyPressed(KEY_ESCAPE) && !showControls) { state = ST_MENU; introDemo = 1; stateT = 0; paused = 0; if (training) newMatch(); }
        }

        /* scripted scenes for headless verification */
        if (shots) {
            static int shotAt = -1; static const char *shotName = NULL;
            static int gotHook = 0, gotFree = 0, gotKick = 0;
            if (frame == 90) { shotAt = frame; shotName = "v3_01_intro_title.png"; }
            if (frame == 560) { shotAt = frame; shotName = "v3_02_intro_hill_end.png"; }
            if (frame == 640) { state = ST_MENU; stateT = 0; }
            if (frame == 680) { shotAt = frame; shotName = "v3_03_menu.png"; }
            if (frame == 700) { newMatch(); state = ST_PLAY; introDemo = 0; demo = 1; camMode = 0; }
            if (frame == 1000) { shotAt = frame; shotName = "v3_04_broadcast_stadium.png"; }
            if (frame == 1010) { camOverride = 1; camOverrideT = 0; }
            if (frame == 1060) { shotAt = frame; shotName = "v3_05_stadium_wide.png"; }
            if (frame == 1070) { camOverride = 0; camMode = 3; }
            if (frame == 1130) { shotAt = frame; shotName = "v3_06_behind_goal.png"; }
            if (frame == 1140) { scenarioCarry(0, 10, 75, 30); camMode = 5; }
            if (frame == 1185) { shotAt = frame; shotName = "v3_07_lighting_shadows.png"; }
            if (frame == 1200) {          /* special move: hook on the carrier -> straight red */
                scenarioCarry(1, 5, 82, 40); demo = 0;
                game_select_player(&game, 9);
                game.players[0][9].x = 80.4f; game.players[0][9].z = 40.0f; game.players[0][9].facing_x = 1; game.players[0][9].facing_z = 0;
                camMode = 1;
            }
            if (frame == 1202) { GameInput sp = { 0 }; sp.special = 1; game_update(&game, sp, 1.0f / 60.0f); }
            if (!gotHook && frame > 1202 && frame < 1300 && game.card_time > 0 && game.card_type == GAME_CARD_RED) { gotHook = 1; TakeScreenshot("v3_08_hook_contact_red.png"); camOverride = 2; camOverrideT = 0; }
            if (frame == 1330) { shotAt = frame; shotName = "v3_09_red_card_shown.png"; }
            if (frame == 1400) {          /* cynical pull-down -> black card + sin bin */
                camOverride = 0; demo = 1;
                scenarioCarry(1, 6, 60, 30);
                game_force_foul(&game, 0, 4, GAME_FOUL_PULL_DOWN);
                camOverride = 2; camOverrideT = 0;
            }
            if (frame == 1480) { shotAt = frame; shotName = "v3_10_black_card_shown.png"; }
            if (frame == 1500) { camOverride = 0; camMode = 0; }
            if (frame == 1700) { shotAt = frame; shotName = "v3_11_sin_bin_hud.png"; }
            if (frame == 1710) showControls = 1;
            if (frame == 1720) { shotAt = frame; shotName = "v3_12_controller_overlay.png"; }
            if (frame == 1730) showControls = 0;
            if (frame == 1740) {          /* free kick off the ground: place kick */
                scenarioCarry(0, 11, 98, 36);
                game_force_foul(&game, 1, 6, GAME_FOUL_TECHNICAL);
                camMode = 1; demo = 1;
            }
            if (!gotFree && frame > 1740 && frame < 2100 && releaseFlash == 1 && lastReleaseAction == GAME_ACT_FREE_KICK) { gotFree = 1; shotAt = frame - 1; shotName = "v3_13_free_kick_place_contact.png"; }
            if (frame == 2120) { scenarioCarry(0, 13, 95, 40); camMode = 1; }
            if (frame == 2122) { GameInput k = { 0 }; k.kick = 1; k.power = 0.8f; game_update(&game, k, 1.0f / 60.0f); }
            if (!gotKick && frame > 2122 && frame < 2200 && releaseFlash == 1) { gotKick = 1; shotAt = frame - 1; shotName = "v3_14_kick_contact.png"; }
            if (frame == shotAt + 1 && shotName) { TakeScreenshot(shotName); shotName = NULL; }
            if (frame > 2260) break;
        }

        int frozen = showControls && state == ST_PLAY && !shots && !shots31;   /* the test screen pauses play */
        if (!paused && !fullTime && !frozen) {
            GameInput in;
            int ai = state != ST_PLAY || introDemo || demo;
            in = ai ? demoInput() : readInput(dt);
            if (state == ST_PLAY && !ai && !shots) applyAssist(&in);
            double u0 = GetTime();
            game_update(&game, in, dt);
            if (state == ST_PLAY && !ai && !training) autoSwitch(dt);
            else { lastBT = game.ball_team; lastBP = game.ball_player; lastFlight = game.ball.in_flight; }
            if (switchFlash > 0) switchFlash -= dt;
            if (training) trainingTick(dt);
            tUpdate = GetTime() - u0;
            if (!training) clockT += dt;
            if (clockT >= HALF_SECONDS) {
                clockT = 0;
                if (game.half == 1) { game_start_half(&game, 2); sfxPlay(SND_WHISTLE_LONG, 1.0f); commentarySay(0, "Half-time whistle... and we're back for the second half."); }
                else { fullTime = 1; sfxPlay(SND_WHISTLE_LONG, 1.0f); commentarySay(0, "Full time! %s %d-%02d, %s %d-%02d.", teamName(0), game.team_goals[0], game.team_points[0], teamName(1), game.team_goals[1], game.team_points[1]); }
            }
            if (state == ST_MENU && !shots && stateT > 60.0f) { newMatch(); stateT = 0; }   /* keep the attract loop fresh */
        }
        {
            static double lastFire = -9; static GameEvent lastFired = GAME_EVENT_NONE;
            if (game.event != GAME_EVENT_NONE && (game.event != lastEv || game.event_time > lastEvTime + 0.05f) &&
                !(game.event == lastFired && GetTime() - lastFire < 1.5 && !shots && !rec)) {
                onGameEvent(game.event); lastFire = GetTime(); lastFired = game.event;
            }
        }
        lastEv = game.event; lastEvTime = game.event_time;
        if (celebT > 0) celebT -= dt;
        for (int i = 0; i < COMM_LINES; i++) commAge[i] += dt;
        /* crowd: tension builds near goal */
        {
            float dGoal = fminf(game.ball.x, GAME_PITCH_LENGTH - game.ball.x);
            float base = 0.22f + (dGoal < 30.0f ? (30.0f - dGoal) / 30.0f * 0.25f : 0.0f);
            if (crowdHold <= 0) crowdTarget = base;
            crowdExcite = Lerp(crowdExcite, crowdHold > 0 ? crowdTarget : base * 0.5f, fminf(1.0f, dt * 2.0f));
        }
        sfxUpdate(dt);
        if (recWav) {
            static float buf[4096];
            int n = SFX_RATE / 30;
            sfxMix(buf, n, dt);
            for (int i = 0; i < n; i++) { short v = (short)(Clamp(buf[i], -1, 1) * 32000); fwrite(&v, 2, 1, recWav); }
            wavSamples += n;
        }

        const char *shot = NULL;
        if (state == ST_INTRO) shot = introCamera(stateT, dt);
        else if (state == ST_MENU) { float a = stateT * 0.05f; cam.position = (Vector3){ sinf(a) * 120.0f, 45.0f, cosf(a) * 95.0f }; cam.target = (Vector3){ 0, 3, 0 }; cam.fovy = 50; }
        else updateCamera(dt);

        BeginDrawing();
        ClearBackground((Color){ 150, 185, 220, 255 });
        glClearStencil(0); glClear(GL_STENCIL_BUFFER_BIT);
        BeginMode3D(cam);
        showMarkers = state == ST_PLAY && !introDemo && !demo;
        double w0 = GetTime();
        drawWorld(paused || frozen ? 0.0f : dt);
        EndMode3D();
        tWorld = GetTime() - w0 - tSkin;
        double h0 = GetTime();
        int sw = GetScreenWidth(), sh = GetScreenHeight();
        if (state == ST_INTRO) drawTitle(sw, sh, stateT, shot);
        else if (state == ST_MENU) drawMenu(sw, sh);
        else { drawHUD(sw, sh); if (training) drawTrainingHUD(sw, sh); }
        if (showControls) drawControls(sw, sh);
        if (paused && state == ST_PLAY) DrawText("PAUSED", sw / 2 - MeasureText("PAUSED", 48) / 2, sh / 2 - 24, 48, GOLD);
        if (showPerf) drawPerf(sw);
        tHud = GetTime() - h0;
        double s0 = GetTime();
        EndDrawing();
        tSwap = GetTime() - s0;
        tFrame = GetTime() - frameStart;
        {
            float k = 0.08f;
            pSkin += (tSkin * 1000 - pSkin) * k; pUpdate += (tUpdate * 1000 - pUpdate) * k; pWorld += (tWorld * 1000 - pWorld) * k;
            pHud += (tHud * 1000 - pHud) * k; pSwap += (tSwap * 1000 - pSwap) * k; pFrame += (tFrame * 1000 - pFrame) * k;
        }
        if (bench) {
            if (frame == 60) benchT0 = GetTime();
            if (frame > 60) {
                benchSum[0] += tFrame; benchSum[1] += tUpdate; benchSum[2] += tSkin; benchSum[3] += tWorld; benchSum[4] += tSwap; benchSum[5] += skinnedThisFrame; benchN++;
            }
            if (frame >= 60 + bench) {
                double el = GetTime() - benchT0;
                printf("BENCH quality=%s skin=%s frames=%d avg_fps=%.1f frame=%.2fms update=%.2f skin=%.2f world=%.2f gpu+swap=%.2f chars=%.1f\n",
                       QUALITY_NAMES[gfxQuality], gpuSkin ? "GPU" : "CPU", benchN, benchN / el, benchSum[0] / benchN * 1000, benchSum[1] / benchN * 1000,
                       benchSum[2] / benchN * 1000, benchSum[3] / benchN * 1000, benchSum[4] / benchN * 1000, benchSum[5] / benchN);
                fflush(stdout);
                break;
            }
        }
        if (rec) {
            int rw = GetRenderWidth(), rh = GetRenderHeight();
            if (frame == 1) TraceLog(LOG_WARNING, "GAME: recording %dx%d", rw, rh);
            unsigned char *px = rlReadScreenPixels(rw, rh);
            fwrite(px, 1, (size_t)rw * rh * 4, rec);
            RL_FREE(px);
        }
    }
    if (rec) fclose(rec);
    if (recWav) {   /* finish the WAV header */
        unsigned int dataBytes = (unsigned int)(wavSamples * 2), riff = 36 + dataBytes, fmtLen = 16, rate = SFX_RATE, byteRate = SFX_RATE * 2;
        unsigned short pcm = 1, ch = 1, align = 2, bits = 16;
        fseek(recWav, 0, SEEK_SET);
        fwrite("RIFF", 1, 4, recWav); fwrite(&riff, 4, 1, recWav); fwrite("WAVEfmt ", 1, 8, recWav);
        fwrite(&fmtLen, 4, 1, recWav); fwrite(&pcm, 2, 1, recWav); fwrite(&ch, 2, 1, recWav); fwrite(&rate, 4, 1, recWav);
        fwrite(&byteRate, 4, 1, recWav); fwrite(&align, 2, 1, recWav); fwrite(&bits, 2, 1, recWav);
        fwrite("data", 1, 4, recWav); fwrite(&dataBytes, 4, 1, recWav);
        fclose(recWav);
    }
    sfxShutdown();
    if (anims) UnloadModelAnimations(anims, animCount);
    if (haveModel) UnloadModel(model);
    for (int k = 0; k < KIT_COUNT; k++) UnloadTexture(kits[k]);
    CloseWindow();
    return 0;
}

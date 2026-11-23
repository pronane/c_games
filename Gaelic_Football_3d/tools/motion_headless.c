/* Headless asset bake and integration check. Include the game frontend so this
 * tool exercises the very same static extraction/validation code; unused draw
 * code is never called. This currently requires raylib 5.5, whose loaded
 * ModelAnimation exposes its skeleton without a GPU context. */
#define main gaelic_frontend_main
#include "../src/main.c"
#undef main
#include <time.h>

#if RAYLIB_VERSION_MAJOR >= 6
int main(void)
{
    fprintf(stderr, "Headless baker requires raylib 5.5 (raylib 6 animations do not expose bone names).\n");
    return 2;
}
#else
static MMDatabase referenceGait;
static AMDatabase referenceActions;
static int releaseCount;
static void count_release(const GameState *g, int team, int player, int action, void *user)
{ (void)g; (void)team; (void)player; (void)action; (void)user; ++releaseCount; }

static int same_rows(const AMDatabase *a, const AMDatabase *b)
{
    if (a->count != b->count || a->ready != b->ready) return 0;
    for (int i = 0; i < a->count; ++i) {
        const AMRow *x = &a->rows[i], *y = &b->rows[i];
        if (x->clip != y->clip || x->category != y->category || x->ball != y->ball ||
            x->action != y->action || x->time != y->time ||
            memcmp(x->feature, y->feature, sizeof x->feature)) return 0;
    }
    return 1;
}

static int load_model_animation(const char *path)
{
    playerGlb = path;
    anims = LoadModelAnimations(path, &animCount);
    if (!anims || animCount <= 0 || !anims[0].bones || anims[0].boneCount <= 0 || anims[0].boneCount > MAX_BONES) return 0;
    model.bones = anims[0].bones; model.boneCount = anims[0].boneCount;
    for (int k = 0; k < C_COUNT; ++k) clipIdx[k] = -1;
    for (int i = 0; i < animCount; ++i) {
        if (anims[i].boneCount != model.boneCount || !anims[i].bones || !anims[i].framePoses || anims[i].frameCount < 2) return 0;
        for (int b = 0; b < model.boneCount; ++b)
            if (strcmp(anims[i].bones[b].name, model.bones[b].name) || anims[i].bones[b].parent != model.bones[b].parent) return 0;
        for (int k = 0; k < C_COUNT; ++k) if (!strcmp(anims[i].name, CLIP_NAMES[k])) {
            if (clipIdx[k] >= 0) return 0;
            clipIdx[k] = i;
        }
    }
    for (int k = 0; k < C_COUNT; ++k) if (clipIdx[k] < 0) return 0;
    boneFootL = findBone("foot_l"); boneFootR = findBone("foot_r");
    boneHandL = findBone("hand_l"); boneHandR = findBone("hand_r"); boneHead = findBone("head");
    bonePelvis = findBone("pelvis");
    if (boneFootL < 0 || boneFootR < 0 || boneHandL < 0 || boneHandR < 0 || boneHead < 0 || bonePelvis < 0) return 0;
    haveModel = 1;
    return 1;
}

/* Run a normal input through two identical rules states, only one of which
 * drives the presentation matcher. No rendered poses or graphics are involved. */
static int validate_action(int act, float dt)
{
    GameState with, without; GameInput input = {0}; AnimState slot = {0};
    int who, matched = 0, saw = 0; float observedContact = -1, expected;
    game_init(&with); with.enforce_three_v_three = 0; who = with.ball_player;
    for (int i = 0; i < GAME_TEAM_SIZE; ++i) { with.players[1][i].x = 130; with.players[1][i].z = 75; }
    without = with; with.on_release = count_release; releaseCount = 0;
    slot.clip = C_RUN_BALL; slot.t = .2f;
    expected = game_action_contact(act);
    for (int i = 0; i < 50; ++i) {
        int clip; float t;
        memset(&input, 0, sizeof input);
        if (i == 0) { input.solo = act == GAME_ACT_SOLO; input.handpass = act == GAME_ACT_HANDPASS; }
        game_update(&with, input, dt); game_update(&without, input, dt);
        GamePlayer *p = &with.players[0][who];
        clip = p->action == act ? ACTION_CLIPS[act].clip : C_RUN_BALL;
        t = p->action == act ? ACTION_CLIPS[act].start + p->action_time * ACTION_CLIPS[act].rate : 0;
        matchAction(&slot, p, with.ball_team == 0 && with.ball_player == who, &clip, &t);
        if (p->action == act) saw = 1;
        if (slot.matchedAction.active) {
            float atContact;
            matched = 1;
            if (!ga_action_time(&slot.matchedAction, expected, &atContact) || fabsf(atContact - actionMeta[act].contact) > 1e-5f) return 0;
            observedContact = atContact;
        }
        slot.clip = clip; slot.t = t;
        if (with.ball.x != without.ball.x || with.ball.z != without.ball.z || with.ball.height != without.ball.height ||
            with.ball.velocity_x != without.ball.velocity_x || with.ball.velocity_z != without.ball.velocity_z ||
            with.ball.velocity_y != without.ball.velocity_y || with.ball_team != without.ball_team ||
            with.steps_carried != without.steps_carried || with.event != without.event) return 0;
    }
    printf("action=%s dt=%.4f saw=%d matched=%d deadline=%.4f clip_contact=%.4f releases=%d\n",
           act == GAME_ACT_HANDPASS ? "handpass" : "solo", dt, saw, matched, expected, observedContact, releaseCount);
    return saw && matched && (act == GAME_ACT_HANDPASS ? releaseCount == 1 : releaseCount == 0);
}

static int validate_interruption(void)
{
    GameState g; GameInput input = {0}; AnimState slot = {0}; int who, clip; float t;
    game_init(&g); g.enforce_three_v_three = 0; who = g.ball_player;
    for (int i = 0; i < GAME_TEAM_SIZE; ++i) { g.players[1][i].x = 130; g.players[1][i].z = 75; }
    g.on_release = count_release; releaseCount = 0; slot.clip = C_RUN_BALL; slot.t = .2f;
    input.handpass = 1; game_update(&g, input, 1.f/60.f);
    clip = C_HAND_PASS; t = ACTION_CLIPS[GAME_ACT_HANDPASS].start;
    matchAction(&slot, &g.players[0][who], 1, &clip, &t);
    if (!slot.matchedAction.active) return 0;
    g.ball_team = -1; g.ball_player = -1; g.ball.in_flight = 1;
    g.ball.x = 5; g.ball.z = 5; g.ball.height = 5;
    memset(&input, 0, sizeof input);
    for (int i = 0; i < 20; ++i) {
        game_update(&g, input, 1.f/60.f);
        clip = C_HAND_PASS; t = 0;
        matchAction(&slot, &g.players[0][who], 0, &clip, &t);
    }
    printf("interrupted_handpass active=%d releases=%d\n", slot.matchedAction.active, releaseCount);
    return !slot.matchedAction.active && releaseCount == 0;
}

/* An action first observed after its deadline (e.g. off screen) must not
 * start a new match or overwrite the old selector's time. */
static int validate_late_observation(void)
{
    AnimState slot = {0}; GamePlayer p = {0};
    float time = .42f; int clip = C_HAND_PASS;
    slot.clip = C_RUN_BALL; slot.t = .2f;
    p.action = GAME_ACT_HANDPASS; p.action_time = game_action_contact(p.action) + .01f;
    matchAction(&slot, &p, 1, &clip, &time);
    printf("late_observation active=%d fallback=%d\n", slot.matchedAction.active, clip == C_HAND_PASS && time == .42f);
    return !slot.matchedAction.active && clip == C_HAND_PASS && time == .42f;
}

/* Exercise the real model through the same old-schema fallback as the game. */
static int validate_old_cache_fallback(const char *cache)
{
    FILE *f = fopen(cache, "r+b");
    if (!f) return 0;
    if (fseek(f, 8, SEEK_SET) || fputc(1, f) == EOF) { fclose(f); return 0; }
    if (fclose(f)) return 0;
    buildMotionDatabase(cache);
    if (actionCacheLoaded || !motionReady) return 0;
    buildActionDatabase();
    if (!actionReady || !same_rows(&motionDb, &referenceGait) || !same_rows(&actionDb, &referenceActions)) return 0;
    if (!mm_cache_save(cache, playerGlb, MOTION_RAYLIB_VERSION, &motionDb, &actionDb)) return 0;
    printf("old_cache=fallback_to_model_ok\n"); return 1;
}

/* An unblended model-space foot-position proxy, not visual foot sliding or IK. */
static double foot_error(const float a[8], const float b[8])
{
    double sum = 0;
    for (int i = 0; i < 4; ++i) { double d = (double)a[i]-b[i]; sum += d*d; }
    return sqrt(sum);
}
static int compare_entry_poses(int action)
{
    GAActionMeta *m = &actionMeta[action]; int samples = 0, worse = 0;
    double before = 0, after = 0; int n = ANIM_FRAMES(*animFor(C_RUN_BALL)) - 1;
    for (int f = 0; f < n; f += 3) {
        float source[8], legacy[8], selected[8]; GAActionState state; double x, y;
        if (!motionFeatures(C_RUN_BALL, f, source) ||
            !motionFeatures(m->clip, (int)(m->start * ANIM_FPS), legacy)) return 0;
        if (ga_action_begin(&state, &actionDb, m, 0, game_action_contact(action), source, legacy)) {
            if (!motionFeatures(m->clip, (int)(state.entry * ANIM_FPS + .5f), selected)) return 0;
        } else memcpy(selected, legacy, sizeof selected);
        x = foot_error(source, legacy); y = foot_error(source, selected);
        before += x; after += y; samples++; if (y > x + 1e-5) worse++;
    }
    if (!samples) return 0;
    printf("entry_proxy=%s samples=%d legacy_mean_m=%.4f matched_mean_m=%.4f worse=%d (unblended_foot_positions_only)\n",
           action == GAME_ACT_HANDPASS ? "handpass" : "solo", samples, before/samples, after/samples, worse);
    return worse == 0;
}

/* Worst-case microbenchmark: all 30 players perform an action-entry search AND
 * a gait-entry search each iteration. It does not include game/renderer work. */
static int benchmark_search(void)
{
    enum { PLAYERS = 30, ITERATIONS = 1200 }; float feet[8], fallback[2][8]; int gaitHits = 0, selected = 0;
    clock_t start; double ms;
    if (!motionFeatures(C_RUN_BALL, 5, feet) ||
        !motionFeatures(actionMeta[GAME_ACT_SOLO].clip, (int)(actionMeta[GAME_ACT_SOLO].start*ANIM_FPS), fallback[0]) ||
        !motionFeatures(actionMeta[GAME_ACT_HANDPASS].clip, (int)(actionMeta[GAME_ACT_HANDPASS].start*ANIM_FPS), fallback[1])) return 0;
    start = clock();
    for (int step = 0; step < ITERATIONS; ++step) for (int i = 0; i < PLAYERS; ++i) {
        int kind = i & 1, action = kind ? GAME_ACT_HANDPASS : GAME_ACT_SOLO; GAActionState state;
        selected += ga_action_begin(&state, &actionDb, &actionMeta[action], 0, game_action_contact(action), feet, fallback[kind]);
        gaitHits += mm_search(&motionDb, C_JOG, feet) >= 0;
    }
    ms = (double)(clock() - start) * 1000.0 / CLOCKS_PER_SEC;
    printf("synthetic_search=30_gait_plus_30_guarded_action iterations=%d ms_per_iteration=%.4f gait_hits=%d action_selected=%d\n",
           ITERATIONS, ms / ITERATIONS, gaitHits, selected);
    return gaitHits == ITERATIONS * PLAYERS && selected > 0;
}

int main(int argc, char **argv)
{
    const char *asset, *cache;
    if (argc != 3) { fprintf(stderr, "Usage: motion_headless MODEL.glb OUTPUT.gfmotion\n"); return 2; }
    asset = argv[1]; cache = argv[2];
    { size_t len = strlen(asset); if (len < 4 || strcmp(asset + len - 4, ".glb")) {
        fprintf(stderr, "Only self-contained .glb models are supported.\n"); return 2;
    } }
    if (!load_model_animation(asset)) { fprintf(stderr, "Invalid or unsupported model animations: %s\n", asset); return 1; }
    detectContacts(); initActionMetadata(); buildMotionDatabase(NULL); buildActionDatabase();
    if (!motionReady || !actionReady || !actionMeta[GAME_ACT_SOLO].action || !actionMeta[GAME_ACT_HANDPASS].action) {
        fprintf(stderr, "Could not bake gait and both action databases\n"); return 1;
    }
    referenceGait = motionDb; referenceActions = actionDb;
    if (!mm_cache_save(cache, asset, MOTION_RAYLIB_VERSION, &motionDb, &actionDb)) {
        fprintf(stderr, "Could not write cache: %s\n", cache); return 1;
    }
    buildMotionDatabase(cache);
    if (!actionCacheLoaded || !motionCacheMatchesModel() || !same_rows(&motionDb, &referenceGait) ||
        !same_rows(&actionDb, &referenceActions)) { fprintf(stderr, "Cache round trip failed\n"); return 1; }
    printf("model=%s bones=%d clips=%d gait_rows=%d action_rows=%d cache_roundtrip=ok\n",
           asset, model.boneCount, animCount, motionDb.count, actionDb.count);
    if (!validate_old_cache_fallback(cache) || !validate_late_observation() ||
        !validate_action(GAME_ACT_HANDPASS, 1.f/60.f) || !validate_action(GAME_ACT_HANDPASS, 1.f/30.f) ||
        !validate_action(GAME_ACT_SOLO, 1.f/60.f) || !validate_action(GAME_ACT_SOLO, 1.f/30.f) ||
        !validate_interruption() || !compare_entry_poses(GAME_ACT_HANDPASS) ||
        !compare_entry_poses(GAME_ACT_SOLO) || !benchmark_search()) {
        fprintf(stderr, "Action integration check failed\n"); return 1;
    }
    UnloadModelAnimations(anims, animCount);
    puts("Headless motion checks passed (no rendering or visual validation).");
    return 0;
}
#endif

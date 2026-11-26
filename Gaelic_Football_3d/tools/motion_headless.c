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

/* Mirror the draw loop's off-screen branch: choose and match first, but skip
 * pose generation. Also test an actor not observed at all until after release. */
static int validate_offscreen_release(float dt, int first_observed_late)
{
    GameState g; GameInput input = {0}; AnimState slot = {0};
    int who, saw_match = 0, saw_followthrough = 0, saw_release = 0;
    game_init(&g); g.enforce_three_v_three = 0; who = g.ball_player;
    for (int i = 0; i < GAME_TEAM_SIZE; ++i) { g.players[1][i].x = 130; g.players[1][i].z = 75; }
    g.on_release = count_release; releaseCount = 0;
    slot.clip = C_RUN_BALL; slot.t = .2f;
    for (int step = 0; step < 50; ++step) {
        int clip; float t; GamePlayer *p;
        memset(&input, 0, sizeof input); input.handpass = step == 0;
        game_update(&g, input, dt); p = &g.players[0][who];
        if (releaseCount) saw_release = 1;
        if (first_observed_late && !saw_release) continue;
        clip = p->action == GAME_ACT_HANDPASS ? ACTION_CLIPS[p->action].clip : C_RUN_BALL;
        t = p->action == GAME_ACT_HANDPASS ? fminf(ACTION_CLIPS[p->action].start + p->action_time * ACTION_CLIPS[p->action].rate, ACTION_CLIPS[p->action].end) : 0;
        matchAction(&slot, p, g.ball_team == 0 && g.ball_player == who, &clip, &t);
        if (slot.matchedAction.active) {
            saw_match = 1;
            if (saw_release) saw_followthrough = 1;
            if (first_observed_late) return 0;
        }
        /* Culling stores animation clock without updating rendered bone poses. */
        slot.clip = clip; slot.t = t;
    }
    printf("offscreen_handpass dt=%.4f first_observed_late=%d matched=%d followthrough=%d releases=%d\n",
           dt, first_observed_late, saw_match, saw_followthrough, releaseCount);
    return releaseCount == 1 && (first_observed_late ? !saw_match : saw_match && saw_followthrough);
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

/* Check real clip poses after the same presentation-only leg adjustments used
 * by the renderer. This detects a backwards model-space knee and segment-length
 * violations, not whether the skinned mesh looks natural on screen. */
static int validate_leg_ik(void)
{
    const int clips[] = {C_JOG, C_RUN, C_RUN_BALL};
    boneThighL = findBone("thigh_l"); boneThighR = findBone("thigh_r");
    boneCalfL = findBone("calf_l"); boneCalfR = findBone("calf_r");
    boneToeL = findBone("ball_l"); boneToeR = findBone("ball_r");
    if (boneThighL < 0 || boneThighR < 0 || boneCalfL < 0 || boneCalfR < 0) return 0;
    game_init(&game); game.players[0][9].action = GAME_ACT_NONE;
    for (int c = 0; c < 3; ++c) {
        ModelAnimation *a = animFor(clips[c]); AnimState *s = &as[9];
        int n = ANIM_FRAMES(*a)-1, backward = 0, bad_length = 0, straight = 0, authoredStraight = 0, count = 0;
        memset(s, 0, sizeof *s); s->speed = 5; s->strideScale = 2.35f;
        for (int f = 0; f < 2*n; ++f) {
            float lengths[2][2]; int wasStraight[2];
            sampleClip(clips[c], (f % n) / ANIM_FPS, s->pose);
            s->lastX += .06f;
            for (int side = 0; side < 2; ++side) {
                int h = side ? boneThighR : boneThighL, k = side ? boneCalfR : boneCalfL, b = side ? boneFootR : boneFootL;
                lengths[side][0] = Vector3Distance(s->pose[h].translation, s->pose[k].translation);
                lengths[side][1] = Vector3Distance(s->pose[k].translation, s->pose[b].translation);
                wasStraight[side] = Vector3Distance(s->pose[h].translation, s->pose[b].translation) >
                    (lengths[side][0] + lengths[side][1]) * (GA_LEG_MAX_REACH + .001f);
                authoredStraight += wasStraight[side];
            }
            lengthenStride(s); plantFeet(s, 1.f/30.f);
            for (int side = 0; side < 2; ++side) {
                int h = side ? boneThighR : boneThighL, k = side ? boneCalfR : boneCalfL, b = side ? boneFootR : boneFootL;
                Vector3 hip = s->pose[h].translation, knee = s->pose[k].translation, foot = s->pose[b].translation;
                Vector3 d = Vector3Normalize(Vector3Subtract(foot, hip));
                Vector3 v = Vector3Subtract(knee, hip);
                Vector3 pole = Vector3Subtract(v, Vector3Scale(d, Vector3DotProduct(v, d)));
                if (!finite3(knee) || !finite3(foot) || pole.z < -0.005f) backward++;
                if (!wasStraight[side] && Vector3Distance(hip, foot) >
                    (lengths[side][0] + lengths[side][1]) * (GA_LEG_MAX_REACH + .001f)) straight++;
                if (fabsf(Vector3Distance(hip, knee)-lengths[side][0]) > .002f ||
                    fabsf(Vector3Distance(knee, foot)-lengths[side][1]) > .002f) bad_length++;
                count++;
            }
        }
        printf("leg_ik clip=%s samples=%d backward=%d bad_length=%d newly_overextended=%d authored_overextended=%d\n", CLIP_NAMES[clips[c]], count, backward, bad_length, straight, authoredStraight);
        if (backward || bad_length || straight) return 0;
    }
    return 1;
}

/* Validate the experimental assist on actual skeletons and verify that the
 * opt-out, ball carrying and actions are strict no-ops. This measures bones,
 * not rendered hand skin or perceived realism. */
static int validate_jog_arm_assist(void)
{
    AnimState *s = &as[9]; Transform base[MAX_BONES]; float gain[2], beforeMin[2], beforeMax[2], afterMin[2], afterMax[2], beforeMean[2] = {0,0};
    int n = ANIM_FRAMES(*animFor(C_JOG))-1, changed = 0;
    boneArmUL = findBone("upperarm_l"); boneArmUR = findBone("upperarm_r");
    boneArmLL = findBone("lowerarm_l"); boneArmLR = findBone("lowerarm_r");
    if (boneArmUL < 0 || boneArmUR < 0 || boneArmLL < 0 || boneArmLR < 0 || n < 8) return 0;
    detectJogArmProfile(); gain[0] = jogArmGain[0]; gain[1] = jogArmGain[1];
    for (int side=0; side<2; ++side) { beforeMin[side] = afterMin[side] = 1e9f; beforeMax[side] = afterMax[side] = -1e9f; }
    game_init(&game); game.ball_team = -1; game.ball_player = -1;
    game.players[0][9].action = GAME_ACT_NONE; game.players[0][9].jump_time = 0;
    memset(s, 0, sizeof *s); s->speed = 3; s->prevClip = C_JOG; s->clip = C_JOG; s->blend = 1;
    for (int f=0; f<n; ++f) {
        int arms[2]={boneArmUL,boneArmUR}, elbows[2]={boneArmLL,boneArmLR}, hands[2]={boneHandL,boneHandR};
        sampleClip(C_JOG, f/ANIM_FPS, s->pose); memcpy(base, s->pose, sizeof(Transform)*(size_t)model.boneCount);
        jogArmAssist = 1; assistJogArms(s, C_JOG);
        for (int side=0; side<2; ++side) {
            float old = base[hands[side]].translation.z-base[arms[side]].translation.z;
            float now = s->pose[hands[side]].translation.z-s->pose[arms[side]].translation.z;
            beforeMean[side] += old / n;
            beforeMin[side] = fminf(beforeMin[side],old); beforeMax[side] = fmaxf(beforeMax[side],old);
            afterMin[side] = fminf(afterMin[side],now); afterMax[side] = fmaxf(afterMax[side],now);
            if (fabsf(Vector3Distance(base[arms[side]].translation,base[elbows[side]].translation) - Vector3Distance(s->pose[arms[side]].translation,s->pose[elbows[side]].translation)) > .0001f ||
                fabsf(Vector3Distance(base[elbows[side]].translation,base[hands[side]].translation) - Vector3Distance(s->pose[elbows[side]].translation,s->pose[hands[side]].translation)) > .0001f) return 0;
        }
        for (int b=0; b<model.boneCount; ++b) if (!boneUnder(b,boneArmUL) && !boneUnder(b,boneArmUR) && memcmp(&base[b],&s->pose[b],sizeof(Transform))) return 0;
        if (Vector3Distance(base[boneHandL].translation,s->pose[boneHandL].translation) > .00001f ||
            Vector3Distance(base[boneHandR].translation,s->pose[boneHandR].translation) > .00001f) changed++;
    }
    printf("jog_arm_profile gain=%.3f,%.3f wrist_forward_mean=%.3f,%.3f range_before=%.3f,%.3f after=%.3f,%.3f changed_frames=%d (bone_proxy_only)\n",
           gain[0],gain[1],beforeMean[0],beforeMean[1],beforeMax[0]-beforeMin[0],beforeMax[1]-beforeMin[1],afterMax[0]-afterMin[0],afterMax[1]-afterMin[1],changed);
    if ((gain[0] > .01f || gain[1] > .01f) && !changed) return 0;
    /* Force a nonzero profile so guard coverage also works for strong clips. */
    jogArmGain[0] = jogArmGain[1] = 1; jogLegCentre[0] = jogLegCentre[1] = 0; jogLegRadius[0] = jogLegRadius[1] = .1f;
    sampleClip(C_JOG, .15f, s->pose); memcpy(base, s->pose, sizeof(Transform)*(size_t)model.boneCount);
    jogArmAssist = 0; assistJogArms(s,C_JOG); if (memcmp(base,s->pose,sizeof(Transform)*(size_t)model.boneCount)) return 0;
    jogArmAssist = 1; game.ball_team = 0; game.ball_player = 9; assistJogArms(s,C_JOG);
    if (memcmp(base,s->pose,sizeof(Transform)*(size_t)model.boneCount)) return 0;
    game.ball_team = -1; game.players[0][9].action = GAME_ACT_HANDPASS; assistJogArms(s,C_JOG);
    if (memcmp(base,s->pose,sizeof(Transform)*(size_t)model.boneCount)) return 0;
    game.players[0][9].action = GAME_ACT_NONE; game.players[0][9].jump_time = .2f; assistJogArms(s,C_JOG);
    if (memcmp(base,s->pose,sizeof(Transform)*(size_t)model.boneCount)) return 0;
    game.players[0][9].jump_time = 0; s->prevClip = C_RUN; s->blend = 1; assistJogArms(s,C_RUN);
    if (memcmp(base,s->pose,sizeof(Transform)*(size_t)model.boneCount)) return 0;
    jogArmAssist = 0; detectJogArmProfile();
    puts("jog_arm_guards=ok"); return 1;
}

/* Hand-joint geometry proxies use the portable angle primitive. They cannot
 * measure skin or decide whether a reference is anatomically natural. */
static int hand_geometry(const Transform *pose, int side, float *bend, float *spread)
{
    static const char *names[4] = {"index", "middle", "ring", "pinky"};
    float dirs[4][3], total = 0;
    for (int i=0; i<4; ++i) {
        int ids[3]; char name[32]; float a[3], b[3], angle;
        for (int j=0; j<3; ++j) {
            snprintf(name, sizeof name, "%s_%02d_%c", names[i], j+1, side ? 'r' : 'l');
            ids[j] = findBone(name); if (ids[j] < 0) return 0;
        }
        Vector3 x=pose[ids[0]].translation, y=pose[ids[1]].translation, z=pose[ids[2]].translation;
        a[0]=y.x-x.x; a[1]=y.y-x.y; a[2]=y.z-x.z;
        b[0]=z.x-y.x; b[1]=z.y-y.y; b[2]=z.z-y.z;
        for (int k=0;k<3;++k) dirs[i][k]=a[k]+b[k];
        if (!am_direction_angle(a,b,&angle)) return 0;
        total += angle;
    }
    if (!am_direction_angle(dirs[0],dirs[3],spread)) return 0;
    *bend=total/4; return 1;
}

static int validate_jog_hand_relax(void)
{
    AnimState *s = &as[9]; Transform original[MAX_BONES]; int eligible = 0, changed = 0;
    int n = ANIM_FRAMES(*animFor(C_JOG))-1;
    double beforeBend[2]={0}, afterBend[2]={0}, beforeSpread[2]={0}, afterSpread[2]={0};
    int geometrySamples=0;
    detectJogHandProfile();
    for (int b=0; b<model.boneCount; ++b) if (jogFingerGain[b] > .01f) eligible++;
    game_init(&game); game.ball_team = -1; game.ball_player = -1;
    game.players[0][9].action = GAME_ACT_NONE; game.players[0][9].jump_time = 0;
    memset(s,0,sizeof *s); s->speed=3; s->clip=C_JOG; s->prevClip=C_JOG; s->blend=1;
    jogHandRelax=1;
    for (int f=0; f<n; f+=3) {
        sampleClip(C_JOG, f/ANIM_FPS, s->pose); memcpy(original,s->pose,sizeof(Transform)*(size_t)model.boneCount);
        relaxJogHands(s,C_JOG,1.f/60.f);
        for (int side=0;side<2;++side) {
            float a,b,c,d;
            if (!hand_geometry(original,side,&a,&b) || !hand_geometry(s->pose,side,&c,&d)) return 0;
            beforeBend[side]+=a; beforeSpread[side]+=b; afterBend[side]+=c; afterSpread[side]+=d;
        }
        ++geometrySamples;
        for (int b=0; b<model.boneCount; ++b) {
            int parent = boneChild(b), isFinger = b != boneHandL && b != boneHandR && (boneUnder(b,boneHandL)||boneUnder(b,boneHandR));
            if (!isFinger) { if (memcmp(&original[b],&s->pose[b],sizeof(Transform))) return 0; continue; }
            if (parent < 0) return 0;
            { Quaternion a=QuaternionNormalize(QuaternionMultiply(QuaternionInvert(original[parent].rotation),original[b].rotation));
              Quaternion z=QuaternionNormalize(QuaternionMultiply(QuaternionInvert(s->pose[parent].rotation),s->pose[b].rotation));
              float dot=fabsf(a.x*z.x+a.y*z.y+a.z*z.z+a.w*z.w);
              float angle=2*acosf(Clamp(dot,0,1));
              if (!finite3(s->pose[b].translation) || angle > .251f ||
                  fabsf(Vector3Distance(original[parent].translation,original[b].translation)-Vector3Distance(s->pose[parent].translation,s->pose[b].translation)) > .0001f) return 0;
              if (angle > .001f) changed++;
            }
        }
    }
    printf("jog_hand_profile eligible_joints=%d changed_samples=%d (bone_proxy_only)\n",eligible,changed);
    for (int side=0;side<2;++side) {
        float rb, rs; Transform reference[MAX_BONES];
        sampleClip(C_IDLE,.2f,reference);
        if (!hand_geometry(reference,side,&rb,&rs)) return 0;
        printf("jog_hand_geometry side=%c bend_deg=%.1f->%.1f idle_ref=%.1f spread_deg=%.1f->%.1f idle_ref=%.1f (joint_proxy_only)\n",
               side?'r':'l', beforeBend[side]/geometrySamples*RAD2DEG, afterBend[side]/geometrySamples*RAD2DEG, rb*RAD2DEG,
               beforeSpread[side]/geometrySamples*RAD2DEG, afterSpread[side]/geometrySamples*RAD2DEG, rs*RAD2DEG);
    }
    if (eligible && !changed) return 0;
    sampleClip(C_JOG,.15f,s->pose); memcpy(original,s->pose,sizeof(Transform)*(size_t)model.boneCount);
    jogHandRelax=0; relaxJogHands(s,C_JOG,1.f/60.f); if (memcmp(original,s->pose,sizeof(Transform)*(size_t)model.boneCount)) return 0;
    jogHandRelax=1; game.ball_team=0; game.ball_player=9; relaxJogHands(s,C_JOG,1.f/60.f);
    if (memcmp(original,s->pose,sizeof(Transform)*(size_t)model.boneCount)) return 0;
    game.ball_team=-1; game.players[0][9].action=GAME_ACT_HANDPASS; relaxJogHands(s,C_JOG,1.f/60.f);
    if (memcmp(original,s->pose,sizeof(Transform)*(size_t)model.boneCount)) return 0;
    game.players[0][9].action=GAME_ACT_NONE; game.players[0][9].jump_time=.1f; relaxJogHands(s,C_JOG,1.f/60.f);
    if (memcmp(original,s->pose,sizeof(Transform)*(size_t)model.boneCount)) return 0;
    game.players[0][9].jump_time=0; s->prevClip=C_RUN; s->blend=1; relaxJogHands(s,C_RUN,1.f/60.f);
    if (memcmp(original,s->pose,sizeof(Transform)*(size_t)model.boneCount)) return 0;
    s->prevClip=C_RUN; s->blend=0; relaxJogHands(s,C_JOG,1.f/60.f);
    if (memcmp(original,s->pose,sizeof(Transform)*(size_t)model.boneCount)) return 0;
    s->prevClip=C_JOG; s->blend=1; relaxJogHands(s,C_RUN,1.f/60.f);
    if (memcmp(original,s->pose,sizeof(Transform)*(size_t)model.boneCount)) return 0;
    jogHandRelax=0; puts("jog_hand_guards=ok"); return 1;
}

/* The stronger pose is a separately opted-in experiment, with the same
 * exclusions and a larger but still bounded local joint correction. */
static int validate_extra_hand_relax(int mode)
{
    AnimState *s=&as[9]; Transform before[MAX_BONES]; int changed=0;
    detectJogHandProfile(); game_init(&game); game.ball_team=-1; game.ball_player=-1;
    game.players[0][9].action=GAME_ACT_NONE; game.players[0][9].jump_time=0;
    memset(s,0,sizeof *s); s->speed=3; s->clip=C_JOG; s->prevClip=C_JOG; s->blend=1;
    jogHandRelax=mode;
    for (int f=0;f<ANIM_FRAMES(*animFor(C_JOG))-1;f+=3) {
        sampleClip(C_JOG,f/ANIM_FPS,s->pose); memcpy(before,s->pose,sizeof(Transform)*(size_t)model.boneCount);
        relaxJogHands(s,C_JOG,1.f/60.f);
        for (int b=0;b<model.boneCount;++b) {
            int parent=boneChild(b), finger=b!=boneHandL && b!=boneHandR && (boneUnder(b,boneHandL)||boneUnder(b,boneHandR));
            if (!finger) { if (memcmp(&before[b],&s->pose[b],sizeof(Transform))) return 0; continue; }
            if (parent<0) return 0;
            Quaternion a=QuaternionNormalize(QuaternionMultiply(QuaternionInvert(before[parent].rotation),before[b].rotation));
            Quaternion z=QuaternionNormalize(QuaternionMultiply(QuaternionInvert(s->pose[parent].rotation),s->pose[b].rotation));
            float dot=fabsf(a.x*z.x+a.y*z.y+a.z*z.z+a.w*z.w), angle=2*acosf(Clamp(dot,0,1));
            if (!finite3(s->pose[b].translation) || angle>(mode == 2 ? .501f : mode == 4 ? .351f : .251f) ||
                fabsf(Vector3Distance(before[parent].translation,before[b].translation)-Vector3Distance(s->pose[parent].translation,s->pose[b].translation))>.0001f) return 0;
            if (angle>.001f) ++changed;
        }
    }
    sampleClip(C_JOG,.15f,s->pose); memcpy(before,s->pose,sizeof(Transform)*(size_t)model.boneCount);
    game.ball_team=0; game.ball_player=9; relaxJogHands(s,C_JOG,1.f/60.f);
    if (memcmp(before,s->pose,sizeof(Transform)*(size_t)model.boneCount)) return 0;
    game.ball_team=-1; game.players[0][9].action=GAME_ACT_HANDPASS; relaxJogHands(s,C_JOG,1.f/60.f);
    if (memcmp(before,s->pose,sizeof(Transform)*(size_t)model.boneCount)) return 0;
    game.players[0][9].action=GAME_ACT_NONE; game.players[0][9].jump_time=.1f; relaxJogHands(s,C_JOG,1.f/60.f);
    if (memcmp(before,s->pose,sizeof(Transform)*(size_t)model.boneCount)) return 0;
    game.players[0][9].jump_time=0; s->prevClip=C_RUN; s->blend=0; relaxJogHands(s,C_JOG,1.f/60.f);
    if (memcmp(before,s->pose,sizeof(Transform)*(size_t)model.boneCount)) return 0;
    { int mirrored=0; for (int b=0;b<model.boneCount;++b) mirrored+=jogFingerMirrorValid[b]!=0;
      printf("jog_hand_extra mode=%d changed_samples=%d mirrored_right=%d guards=ok (bone_proxy_only)\n",mode,changed,mirrored); }
    jogHandRelax=0; return 1;
}

static int validate_jog_stride_ramp(void)
{
    const float speeds[] = {2.0f, 2.2f, 2.2001f, 2.7f, 3.2f, 3.5f};
    float scale[6]; int clip; float t; AnimState slot = {0};
    GamePlayer p = {0};
    game_init(&game); game.ball_team = -1; game.ball_player = -1;
    for (int i = 0; i < 6; ++i) {
        slot.speed = speeds[i]; desiredClip(0, 9, &p, &slot, 1.f/60, &clip, &t);
        if (clip != C_JOG || !isfinite(slot.strideScale)) return 0;
        scale[i] = slot.strideScale;
    }
    printf("jog_stride_ramp %.4f %.4f %.4f %.4f %.4f %.4f\n",
           scale[0], scale[1], scale[2], scale[3], scale[4], scale[5]);
    return scale[0] == 1.0f && scale[1] == 1.0f && fabsf(scale[2]-scale[1]) < .0001f &&
           scale[3] > scale[2] && scale[4] > scale[3] && scale[5] >= scale[4] &&
           scale[5] <= strideLimit(speeds[5]) + .0001f;
}

/* Drive the actual presentation gait at constant world velocity. The ankle
 * proxy measures horizontal world displacement while the unadjusted clip is
 * low, not sole/mesh contact or proof of rendered foot planting. */
static int report_jog_ground_proxy(float dt, float speed)
{
    AnimState *s = &as[9]; GamePlayer *p; Transform raw[MAX_BONES];
    double rawDist = 0, scaledDist = 0, adjustedDist = 0, activeDist = 0;
    float prevRaw[2] = {0}, prevScaled[2] = {0}, prevAdjusted[2] = {0}, prevY[2] = {0};
    int count = 0, active = 0, clip = -1; float t = 0;
    AMContactDrift drift[2];
    am_contact_drift_reset(&drift[0]); am_contact_drift_reset(&drift[1]);
    game_init(&game); game.ball_team = -1; game.ball_player = -1;
    p = &game.players[0][9]; p->action = GAME_ACT_NONE; p->jump_time = 0;
    memset(s, 0, sizeof *s); s->speed = speed;
    for (int step = 0; step < (int)(5.0f/dt); ++step) {
        float rawWorld[2], scaledWorld[2], adjustedWorld[2];
        desiredClip(0, 9, p, s, dt, &clip, &t);
        if (clip != C_JOG) return 0;
        s->lastZ += speed * dt;
        sampleClip(clip, t, raw);
        memcpy(s->pose, raw, (size_t)model.boneCount * sizeof(Transform));
        lengthenStride(s);
        scaledWorld[0] = s->lastZ + s->pose[boneFootL].translation.z;
        scaledWorld[1] = s->lastZ + s->pose[boneFootR].translation.z;
        plantFeet(s, dt);
        for (int side = 0; side < 2; ++side) {
            int f = side ? boneFootR : boneFootL;
            rawWorld[side] = s->lastZ + raw[f].translation.z;
            adjustedWorld[side] = s->lastZ + s->pose[f].translation.z;
            if (!isfinite(adjustedWorld[side])) return 0;
            am_contact_drift_sample(&drift[side], s->pose[f].translation.x, adjustedWorld[side], dt,
                                    step > (int)(1.0f/dt) && raw[f].translation.y <= .11f);
            if (step > (int)(1.0f/dt) && raw[f].translation.y <= .11f && prevY[side] <= .11f) {
                rawDist += fabs(rawWorld[side] - prevRaw[side]);
                scaledDist += fabs(scaledWorld[side] - prevScaled[side]);
                adjustedDist += fabs(adjustedWorld[side] - prevAdjusted[side]);
                count++;
                if (s->plantOn[side] && s->plantWeight[side] > .5f) {
                    activeDist += fabs(adjustedWorld[side] - prevAdjusted[side]); active++;
                }
            }
            prevRaw[side] = rawWorld[side]; prevScaled[side] = scaledWorld[side]; prevAdjusted[side] = adjustedWorld[side];
            prevY[side] = raw[f].translation.y;
        }
    }
    printf("jog_ground_proxy dt=%.4f speed=%.1f samples=%d raw_mps=%.3f scaled_mps=%.3f adjusted_mps=%.3f planted_samples=%d planted_mps=%.3f (ankle_proxy_only)\n",
           dt, speed, count, count ? rawDist/(count*dt) : 0, count ? scaledDist/(count*dt) : 0, count ? adjustedDist/(count*dt) : 0,
           active, active ? activeDist/(active*dt) : 0);
    printf("shared_contact_drift dt=%.4f speed=%.1f samples=%lu mean_mps=%.3f (low_ankle_proxy_2d)\n",
           dt, speed, drift[0].intervals + drift[1].intervals,
           (drift[0].seconds + drift[1].seconds) > 0 ?
           (drift[0].distance + drift[1].distance)/(drift[0].seconds + drift[1].seconds) : 0);
    return count > 0 && drift[0].intervals + drift[1].intervals > 0;
}

/* Exercise the plant's attack and release with a fixed real-model pose and
 * fixed position, so render step size is the only variable. */
static int validate_plant_envelope(void)
{
    ModelAnimation *a = animFor(C_JOG); int f, n = ANIM_FRAMES(*a)-1;
    float values[2][2];
    for (f = 0; f < n; ++f) {
        Transform *p = ANIM_POSES(*a)[f]; Vector3 hip = p[boneThighL].translation, knee = p[boneCalfL].translation;
        Vector3 target = p[boneFootL].translation; float length = Vector3Distance(hip, knee) + Vector3Distance(knee, target);
        if (target.y > .11f) continue;
        target.y = .08f;
        if (Vector3Distance(hip, target) < length * GA_LEG_MAX_REACH) break;
    }
    if (f == n) return 0;
    for (int rate = 0; rate < 2; ++rate) {
        AnimState *s = &as[9]; int hz = rate ? 60 : 30;
        memset(s, 0, sizeof *s); s->speed = 2;
        for (int step = 0; step < hz/5; ++step) {
            memcpy(s->pose, ANIM_POSES(*a)[f], model.boneCount*sizeof(Transform));
            plantOne(s, 0, boneThighL, boneCalfL, boneFootL, boneToeL, 1.f/hz);
        }
        if (!s->plantOn[0]) return 0;
        values[rate][0] = s->plantWeight[0];
        for (int step = 0; step < hz/5; ++step) {
            memcpy(s->pose, ANIM_POSES(*a)[f], model.boneCount*sizeof(Transform));
            s->pose[boneFootL].translation.y = .3f;
            plantOne(s, 0, boneThighL, boneCalfL, boneFootL, boneToeL, 1.f/hz);
        }
        values[rate][1] = s->plantWeight[0];
        if (s->plantOn[0] || values[rate][0] <= values[rate][1]) return 0;
    }
    printf("plant_envelope attack_30=%.4f attack_60=%.4f release_30=%.4f release_60=%.4f\n", values[0][0], values[1][0], values[0][1], values[1][1]);
    return fabsf(values[0][0] - values[1][0]) < 1e-5f && fabsf(values[0][1] - values[1][1]) < 1e-5f;
}

static int validate_torso_and_grip(void)
{
    const int clips[] = {C_IDLE, C_JOG, C_RUN, C_RUN_BALL};
    AnimState *s = &as[9]; int changed = 0;
    boneSpine = findBone("spine_03"); boneSpine1 = findBone("spine_01");
    boneArmUL = findBone("upperarm_l"); boneArmUR = findBone("upperarm_r");
    boneArmLL = findBone("lowerarm_l"); boneArmLR = findBone("lowerarm_r");
    boneMidL = findBone("middle_01_l"); boneMidR = findBone("middle_01_r");
    if (boneSpine < 0 || boneSpine1 < 0 || boneArmUL < 0 || boneArmUR < 0 || boneArmLL < 0 || boneArmLR < 0) return 0;
    /* The loader does not expose mesh bind poses headlessly; a valid rotation
     * suffices to test positions, not actual hand mesh collision. */
    model.bindPose = ANIM_POSES(anims[0])[0];
    game_init(&game); game.ball_team = 0; game.ball_player = 9;
    game.players[0][9].action = GAME_ACT_NONE;
    for (int c = 0; c < 4; ++c) {
        ModelAnimation *a = animFor(clips[c]); int n = ANIM_FRAMES(*a)-1;
        for (int f = 0; f < n; f += 3) {
            float before, after; Vector3 hip, head, ball;
            memset(s, 0, sizeof *s); s->speed = clips[c] == C_IDLE ? 0 : clips[c] == C_JOG ? 3 : 7;
            memcpy(s->pose, ANIM_POSES(*a)[f], model.boneCount*sizeof(Transform));
            hip = s->pose[bonePelvis].translation; head = s->pose[boneHead].translation;
            before = head.z - hip.z; balanceTorso(s, clips[c]);
            after = s->pose[boneHead].translation.z - s->pose[bonePelvis].translation.z;
            if (!finite3(s->pose[boneHead].translation) || after > before + 1e-5f ||
                Vector3Distance(hip, s->pose[bonePelvis].translation) > 1e-6f) return 0;
            if (after < before - .001f) changed++;
            cradleBall(s, clips[c]);
            if (!s->cradleValid) return 0;
            s->poseValid = 1; s->yawInit = 1;
            ball = carriedBall(0, 9);
            ball = Vector3Subtract(ball, W(game.players[0][9].x, 0, game.players[0][9].z));
            if (Vector3Distance(ball, s->cradleCenter) > 1e-5f) return 0;
            for (int side = 0; side < 2; ++side) {
                const int left[] = {22, 23, 25, 24, 26}, right[] = {27, 28, 30, 29, 31};
                const int *fingers = side ? right : left;
                int wrist = side ? boneHandR : boneHandL;
                if (s->speed < 5.9f || side) {
                    if (!finite3(s->pose[wrist].translation) || Vector3Distance(s->pose[wrist].translation, ball) < BALL_R - .001f) return 0;
                    for (int finger = 0; finger < 5; ++finger) {
                        int b = fingers[finger];
                        float d1 = gripSegmentDistance(ball, s->pose[b].translation, s->pose[b+10].translation);
                        float d2 = gripSegmentDistance(ball, s->pose[b+10].translation, s->pose[b+20].translation);
                        if (fminf(d1, d2) < BALL_R + ballClear + .011f) return 0;
                    }
                }
            }
        }
    }
    printf("torso_and_grip corrected=%d centre_consistent=1 (bone_proxy_only)\n", changed);
    return changed > 0;
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

static int validate_jog_playback(void)
{
    ModelAnimation *a = animFor(C_JOG); int n = ANIM_FRAMES(*a)-1;
    Transform *sample = malloc(sizeof(Transform) * (size_t)model.boneCount);
    float feature[MM_DIMS]; int ok = sample != NULL;
    if (!ok || n < 8) { free(sample); return 0; }
    for (int f = 0; f < n && ok; ++f) {
        int source = reverseJog ? (n-f)%n : f;
        sampleClip(C_JOG, f/ANIM_FPS, sample);
        if (!motionFeatures(C_JOG, f, feature) ||
            fabsf(sample[boneFootL].translation.z - ANIM_POSES(*a)[source][boneFootL].translation.z) > .001f ||
            fabsf(feature[1] - sample[boneFootL].translation.z) > .001f) ok = 0;
    }
    free(sample);
    printf("jog_playback_feature_alignment=%s\n", ok ? "ok" : "failed");
    return ok;
}

/* Check the refactored raylib 5.5 blend against its original per-bone
 * interpolation formula, including both the blend and fully-current paths. */
static int validate_pose_blend(void)
{
    AnimState slot = {0}; Transform a[MAX_BONES], b[MAX_BONES];
    slot.prevClip = C_IDLE; slot.prevT = .2f;
    sampleClip(C_JOG, .15f, a); sampleClip(C_IDLE, slot.prevT, b);
    for (int k = 0; k <= 4; ++k) {
        float w = k / 4.f;
        slot.blend = k == 4 ? 1.f : .5f;
        sampleBlendedPose(&slot, C_JOG, .15f, w);
        for (int i = 0; i < model.boneCount; ++i) {
            Transform want = a[i];
            if (slot.blend < 1) {
                want.translation = Vector3Lerp(b[i].translation, a[i].translation, w);
                want.rotation = QuaternionSlerp(b[i].rotation, a[i].rotation, w);
                want.scale = Vector3Lerp(b[i].scale, a[i].scale, w);
            }
            if (Vector3Distance(want.translation, slot.pose[i].translation) > 1e-6f ||
                Vector3Distance(want.scale, slot.pose[i].scale) > 1e-6f ||
                fabsf(want.rotation.x-slot.pose[i].rotation.x) > 1e-6f ||
                fabsf(want.rotation.y-slot.pose[i].rotation.y) > 1e-6f ||
                fabsf(want.rotation.z-slot.pose[i].rotation.z) > 1e-6f ||
                fabsf(want.rotation.w-slot.pose[i].rotation.w) > 1e-6f) return 0;
        }
    }
    puts("pose_blend_equivalence=ok"); return 1;
}

static int validate_locomotion_transition(void)
{
    AnimState a = {0}, b = {0}, action = {0}, bounce = {0};
    a.prevClip = b.prevClip = C_JOG; a.speed = b.speed = 3; a.prevT = b.prevT = .1f;
    a.blend = b.blend = .5f;
    for (int i = 0; i < 6; ++i) advancePreviousLocomotion(&a, C_RUN, 1.f/30);
    for (int i = 0; i < 12; ++i) advancePreviousLocomotion(&b, C_RUN, 1.f/60);
    action = bounce = a; action.prevT = bounce.prevT = .1f; bounce.useBounce = 1;
    advancePreviousLocomotion(&action, C_KICK_PLACE, 1.f/30);
    advancePreviousLocomotion(&bounce, C_RUN, 1.f/30);
    printf("locomotion_transition outgoing_30=%.4f outgoing_60=%.4f action_unchanged=%d bounce_unchanged=%d\n",
           a.prevT, b.prevT, action.prevT == .1f, bounce.prevT == .1f);
    return fabsf(a.prevT - b.prevT) < .0001f && fabsf(a.prevT - .1f) > .01f &&
           action.prevT == .1f && bounce.prevT == .1f;
}

/* Pose-space diagnostics, not a substitute for rendered mesh or gameplay
 * validation. Pelvis-relative measurements remove vertical body bob. */
static int report_jog_motion(void)
{
    int n = ANIM_FRAMES(*animFor(C_JOG)) - 1, count = 0;
    double handMin[2] = {1e9, 1e9}, handMax[2] = {-1e9, -1e9};
    double low[2] = {1e9, 1e9}, sum = 0, products = 0, aa = 0, bb = 0;
    double hand[2][2048], foot[2][2048], height[2][2048], mean[2] = {0, 0};
    Transform pose[MAX_BONES];
    if (n < 8 || n > 2048) return 0;
    for (int i = 0; i < n; ++i) {
        sampleClip(C_JOG, i / ANIM_FPS, pose);
        for (int side = 0; side < 2; ++side) {
            int f = side ? boneFootR : boneFootL, h = side ? boneHandR : boneHandL;
            foot[side][i] = pose[f].translation.z - pose[bonePelvis].translation.z;
            height[side][i] = pose[f].translation.y;
            hand[side][i] = pose[h].translation.z - pose[bonePelvis].translation.z;
            if (!isfinite(foot[side][i]) || !isfinite(height[side][i]) || !isfinite(hand[side][i])) return 0;
            low[side] = fmin(low[side], height[side][i]);
            handMin[side] = fmin(handMin[side], hand[side][i]);
            handMax[side] = fmax(handMax[side], hand[side][i]);
            mean[side] += hand[side][i] / n;
        }
    }
    for (int i = 0; i < n; ++i) {
        int j = (i + 1) % n;
        double x = hand[0][i]-mean[0], y = hand[1][i]-mean[1];
        products += x*y; aa += x*x; bb += y*y;
        for (int side = 0; side < 2; ++side)
            if (height[side][i] <= low[side]+.06 && height[side][j] <= low[side]+.06) {
                sum += (foot[side][j]-foot[side][i])*ANIM_FPS; ++count;
            }
    }
    printf("jog_pose_metrics low_foot_velocity_mps=%.3f low_samples=%d hand_range_m=%.3f,%.3f hand_correlation=%.3f (clip_pose_only)\n",
           count ? sum/count : 0, count, handMax[0]-handMin[0], handMax[1]-handMin[1],
           aa > 1e-10 && bb > 1e-10 ? products/sqrt(aa*bb) : 0);
    return count > 0;
}

/* Export paired global poses for the exact same sample before and after the
 * gameplay presentation's stride/plant IK. This is a constant-speed straight
 * path after a one-second warmup, not a recording of a rendered match. */
static void write_json_string(FILE *f, const char *s)
{
    fputc('"', f);
    for (; *s; ++s) {
        unsigned char c = (unsigned char)*s;
        if (c == '"' || c == '\\') { fputc('\\', f); fputc(c, f); }
        else if (c < 32) fprintf(f, "\\u%04x", c);
        else fputc(c, f);
    }
    fputc('"', f);
}
static int write_pose(FILE *f, Transform *pose, int n)
{
    fputc('[', f);
    for (int b = 0; b < n; ++b) {
        Transform p = pose[b];
        float v[10] = {p.translation.x, p.translation.y, p.translation.z,
                       p.rotation.x, p.rotation.y, p.rotation.z, p.rotation.w,
                       p.scale.x, p.scale.y, p.scale.z};
        if (b) fputc(',', f);
        fputc('[', f);
        for (int k = 0; k < 10; ++k) {
            if (!isfinite(v[k])) return 0;
            fprintf(f, "%s%.9g", k ? "," : "", v[k]);
        }
        fputc(']', f);
    }
    fputc(']', f); return !ferror(f);
}
static int export_jog_poses(const char *asset, const char *out, float speed, int fps, int apply_ik)
{
    FILE *f; AnimState *s = &as[9]; GamePlayer *p; int clip; float t;
    Transform raw[MAX_BONES];
    if (!isfinite(speed) || speed < .7f || speed >= 4.6f || (fps != 30 && fps != 60) || !strcmp(asset, out)) return 0;
    if (!load_model_animation(asset)) return 0;
    detectJogDirection();
    boneThighL = findBone("thigh_l"); boneThighR = findBone("thigh_r");
    boneCalfL = findBone("calf_l"); boneCalfR = findBone("calf_r");
    boneToeL = findBone("ball_l"); boneToeR = findBone("ball_r");
    if (boneThighL < 0 || boneThighR < 0 || boneCalfL < 0 || boneCalfR < 0) return 0;
    f = fopen(out, "wb"); if (!f) return 0;
    game_init(&game); game.ball_team = -1; game.ball_player = -1;
    p = &game.players[0][9]; p->action = GAME_ACT_NONE; p->jump_time = 0;
    memset(s, 0, sizeof *s); s->speed = speed;
    fprintf(f, "{\"format\":1,\"fps\":%d,\"speed_mps\":%.9g,\"warmup_seconds\":1,\"ik\":%s,\"bones\":[", fps, speed, apply_ik ? "true" : "false");
    for (int b = 0; b < model.boneCount; ++b) { if (b) fputc(',', f); write_json_string(f, model.bones[b].name); }
    fputs("],\"frames\":[", f);
    for (int step = 0; step < fps*4; ++step) {
        desiredClip(0, 9, p, s, 1.f/fps, &clip, &t);
        if (clip != C_JOG) { fclose(f); return 0; }
        s->lastZ += speed/fps;
        sampleClip(clip, t, raw);
        memcpy(s->pose, raw, sizeof(Transform)*(size_t)model.boneCount);
        if (apply_ik) { lengthenStride(s); plantFeet(s, 1.f/fps); }
        if (step < fps) continue;
        if (step > fps) fputc(',', f);
        fprintf(f, "{\"clip_time\":%.9g,\"raw\":", t);
        if (!write_pose(f, raw, model.boneCount)) { fclose(f); return 0; }
        fputs(",\"adjusted\":", f);
        if (!write_pose(f, s->pose, model.boneCount)) { fclose(f); return 0; }
        fputc('}', f);
    }
    fputs("]}\n", f);
    if (fclose(f)) return 0;
    UnloadModelAnimations(anims, animCount);
    return 1;
}

/* Paired raw and hand-corrected global poses, with no arm or leg IK.
 * Explicit experiment mode; no simulation or ball action is changed. */
static int export_hand_poses(const char *asset, const char *out, int mode, int fps)
{
    FILE *f; AnimState *s = &as[9]; Transform raw[MAX_BONES];
    if ((mode < 0 || mode > 4) || (fps != 30 && fps != 60) || !strcmp(asset,out)) return 0;
    if (!load_model_animation(asset)) return 0;
    detectJogDirection(); detectJogHandProfile();
    game_init(&game); game.ball_team = -1; game.ball_player = -1;
    memset(s,0,sizeof *s); s->speed=3; s->clip=C_JOG; s->prevClip=C_JOG; s->blend=1;
    jogHandRelax=mode; s->handRelaxEnvelope=1; /* steady-state mesh comparison */
    f=fopen(out,"wb"); if (!f) return 0;
    fprintf(f,"{\"format\":1,\"fps\":%d,\"mode\":%d,\"bones\":[",fps,mode);
    for (int b=0;b<model.boneCount;++b) { if (b) fputc(',',f); write_json_string(f,model.bones[b].name); }
    fputs("],\"frames\":[",f);
    for (int i=0;i<fps;++i) {
        float time=clipLen(C_JOG)*(float)i/fps;
        sampleClip(C_JOG,time,raw); memcpy(s->pose,raw,sizeof(Transform)*(size_t)model.boneCount);
        relaxJogHands(s,C_JOG,1.f/60.f);
        if (i) fputc(',',f);
        fprintf(f,"{\"clip_time\":%.9g,\"raw\":",time);
        if (!write_pose(f,raw,model.boneCount)) { fclose(f); return 0; }
        fputs(",\"adjusted\":",f);
        if (!write_pose(f,s->pose,model.boneCount)) { fclose(f); return 0; }
        fputc('}',f);
    }
    fputs("]}\n",f); if (fclose(f)) return 0;
    UnloadModelAnimations(anims,animCount); return 1;
}

/* Deliberately scripted presentation transitions and guard switches. Uses
 * the same pose blend and correction functions as raylib 5.5 rendering, but
 * is not a live match or a simulation input test. */
static int export_hand_transition(const char *asset, const char *out, int fps)
{
    static const char *state[] = {"idle","jog-in","run","jog-before-carry","carry","jog-before-jump","jump","jog-before-handpass","handpass","jog-before-solo","solo","jog-return"};
    static const int clips[] = {C_IDLE,C_JOG,C_RUN,C_JOG,C_RUN_BALL,C_JOG,C_JOG,C_JOG,C_HAND_PASS,C_JOG,C_SOLO,C_JOG};
    AnimState *s=&as[9]; GamePlayer *p; Transform raw[MAX_BONES]; Quaternion previous[MAX_BONES];
    float boundary[12]={0}, interior[12]={0}; int tested[12]={0}, noops[12]={0}, have_previous=0;
    FILE *f;
    if ((fps!=30 && fps!=60) || !strcmp(asset,out) || !load_model_animation(asset)) return 0;
    detectJogDirection(); detectJogHandProfile(); game_init(&game); game.ball_team=-1; game.ball_player=-1;
    p=&game.players[0][9]; memset(s,0,sizeof *s); s->speed=3; s->clip=C_IDLE; s->prevClip=C_IDLE; s->blend=1;
    jogHandRelax=4; poseFar=0; f=fopen(out,"wb"); if (!f) return 0;
    fprintf(f,"{\"format\":1,\"mode\":4,\"fps\":%d,\"scenario\":\"scripted-hand-transition\",\"bones\":[",fps);
    for (int b=0;b<model.boneCount;++b) { if (b) fputc(',',f); write_json_string(f,model.bones[b].name); }
    fputs("],\"frames\":[",f);
    for (int step=0;step<12*fps;++step) {
        int phase=step/fps, clip=clips[phase]; float t=fmodf((float)step/fps,clipLen(clip)), w, maxstep=0;
        int guarded=(phase==4||phase==6||phase==8||phase==10);
        game.ball_team=phase==4?0:-1; game.ball_player=phase==4?9:-1;
        p->jump_time=phase==6?.2f:0;
        p->action=phase==8?GAME_ACT_HANDPASS:phase==10?GAME_ACT_SOLO:GAME_ACT_NONE;
        w=updatePoseBlend(s,clip,t,1.f/fps); sampleBlendedPose(s,clip,t,w);
        memcpy(raw,s->pose,sizeof(Transform)*(size_t)model.boneCount);
        relaxJogHands(s,clip,1.f/fps);
        if (guarded && memcmp(raw,s->pose,sizeof(Transform)*(size_t)model.boneCount)) { fclose(f); return 0; }
        if (guarded) ++noops[phase];
        for (int b=0;b<model.boneCount;++b) {
            int parent=boneChild(b); Quaternion a,z,delta; float now[4],old[4],angle;
            if (parent<0 || b==boneHandL || b==boneHandR || (!boneUnder(b,boneHandL) && !boneUnder(b,boneHandR))) continue;
            a=QuaternionNormalize(QuaternionMultiply(QuaternionInvert(raw[parent].rotation),raw[b].rotation));
            z=QuaternionNormalize(QuaternionMultiply(QuaternionInvert(s->pose[parent].rotation),s->pose[b].rotation));
            delta=QuaternionNormalize(QuaternionMultiply(QuaternionInvert(a),z));
            now[0]=delta.x; now[1]=delta.y; now[2]=delta.z; now[3]=delta.w;
            if (have_previous) {
                old[0]=previous[b].x; old[1]=previous[b].y; old[2]=previous[b].z; old[3]=previous[b].w;
                if (!am_rotation_distance(now,old,&angle)) { fclose(f); return 0; }
                if (angle>maxstep) maxstep=angle;
            }
            previous[b]=delta;
        }
        have_previous=1; ++tested[phase];
        if (step%fps==0) boundary[phase]=maxstep; else if (maxstep>interior[phase]) interior[phase]=maxstep;
        if (step%fps==fps/2) {
            if (phase) fputc(',',f);
            fputs("{\"state\":",f); write_json_string(f,state[phase]);
            fputs(",\"raw\":",f); if (!write_pose(f,raw,model.boneCount)) { fclose(f); return 0; }
            fputs(",\"adjusted\":",f); if (!write_pose(f,s->pose,model.boneCount)) { fclose(f); return 0; }
            fputc('}',f);
        }
    }
    fputs("]}\n",f); if (fclose(f)) return 0;
    for (int phase=0;phase<12;++phase) {
        printf("hand_transition fps=%d state=%s frames=%d guarded_noops=%d boundary_delta_deg=%.3f max_internal_delta_deg=%.3f (local_correction_only)\n",
               fps,state[phase],tested[phase],noops[phase],boundary[phase]*RAD2DEG,interior[phase]*RAD2DEG);
        if (tested[phase]!=fps || ((phase==4||phase==6||phase==8||phase==10) && noops[phase]!=fps)) return 0;
    }
    UnloadModelAnimations(anims,animCount); return 1;
}

/* Scripted ball-carry/action samples with the frontend's torso and cradle
 * implementation. Bind rotations are supplied by a GLB-verified exporter. */
static int export_grip_poses(const char *asset, const char *out, const char *bindpath, float clearance, Vector3 sprintOffset, float follow, int replant)
{
    static Transform bind[MAX_BONES];
    static const struct { const char *name; int clip,action; float speed,phase; } cases[]={
        {"stand",C_IDLE,GAME_ACT_NONE,0,.25f},{"jog-a",C_RUN_BALL,GAME_ACT_NONE,3,.2f},
        {"jog-b",C_RUN_BALL,GAME_ACT_NONE,3,.7f},{"sprint-a",C_RUN_BALL,GAME_ACT_NONE,7,.2f},
        {"sprint-b",C_RUN_BALL,GAME_ACT_NONE,7,.7f},{"solo-hold",C_SOLO,GAME_ACT_SOLO,3,.1f},
        {"solo-release",C_SOLO,GAME_ACT_SOLO,3,.45f},{"solo-return",C_SOLO,GAME_ACT_SOLO,3,.72f},
        {"solo-held",C_SOLO,GAME_ACT_SOLO,3,.95f},{"handpass",C_HAND_PASS,GAME_ACT_HANDPASS,3,.3f},
        {"catch",C_CATCH,GAME_ACT_CATCH,3,.8f},{"pickup",C_PICKUP,GAME_ACT_PICKUP,3,.8f}};
    static const char *finger_names[]={"index_01_l","middle_01_l","ring_01_l","pinky_01_l","thumb_01_l",
                                       "index_01_r","middle_01_r","ring_01_r","pinky_01_r","thumb_01_r"};
    static const int expected[]={22,23,25,24,26,27,28,30,29,31};
    AnimState *s=&as[9]; GamePlayer *p; FILE *f,*bf; char name[128],extra[8];
    if (!strcmp(asset,out) || !strcmp(bindpath,out) || !load_model_animation(asset)) return 0;
    bf=fopen(bindpath,"r"); if (!bf) return 0;
    for (int b=0;b<model.boneCount;++b) {
        Quaternion q;
        if (fscanf(bf,"%127s %f %f %f %f",name,&q.x,&q.y,&q.z,&q.w)!=5 || strcmp(name,model.bones[b].name) ||
            !isfinite(q.x)||!isfinite(q.y)||!isfinite(q.z)||!isfinite(q.w) || QuaternionLength(q)<.99f || QuaternionLength(q)>1.01f) { fclose(bf); return 0; }
        bind[b].rotation=QuaternionNormalize(q); bind[b].scale=(Vector3){1,1,1};
    }
    if (fscanf(bf,"%7s",extra)==1) { fclose(bf); return 0; } fclose(bf);
    for (int k=0;k<10;++k) {
        char joint[32];
        if (findBone(finger_names[k])!=expected[k]) return 0;
        for (int j=2;j<=3;++j) {
            const char *suffix=strstr(finger_names[k],"_01_"); size_t prefix;
            if (!suffix) return 0;
            prefix=(size_t)(suffix-finger_names[k]);
            if (snprintf(joint,sizeof joint,"%.*s_%02d_%c",(int)prefix,finger_names[k],j,finger_names[k][strlen(finger_names[k])-1]) >= (int)sizeof joint ||
                findBone(joint)!=expected[k]+10*(j-1)) return 0;
        }
    }
    model.bindPose=bind; boneSpine=findBone("spine_03"); boneSpine1=findBone("spine_01");
    boneArmUL=findBone("upperarm_l"); boneArmUR=findBone("upperarm_r");
    boneArmLL=findBone("lowerarm_l"); boneArmLR=findBone("lowerarm_r");
    boneMidL=findBone("middle_01_l"); boneMidR=findBone("middle_01_r");
    if (boneSpine<0 || boneSpine1<0 || boneArmUL<0 || boneArmUR<0 || boneArmLL<0 || boneArmLR<0 || boneMidL<0 || boneMidR<0) return 0;
    loadGrip(asset);
    if (clearance>0) { if (!isfinite(clearance) || clearance<.012f || clearance>.06f) return 0; ballClear=clearance; }
    detectJogDirection(); detectJogHandProfile(); game_init(&game);
    game.ball_team=0; game.ball_player=9; p=&game.players[0][9];
    f=fopen(out,"wb"); if (!f) return 0;
    fprintf(f,"{\"format\":1,\"mode\":4,\"scenario\":\"scripted-grip\",\"clearance_m\":%.9g,\"bones\":[",ballClear);
    for (int b=0;b<model.boneCount;++b) { if (b) fputc(',',f); write_json_string(f,model.bones[b].name); }
    fputs("],\"frames\":[",f);
    for (int k=0;k<(int)(sizeof cases/sizeof cases[0]);++k) {
        Transform raw[MAX_BONES], input[MAX_BONES]; Vector3 center={0}; int hasCenter, cradleValid; float cw;
        memset(s,0,sizeof *s); s->speed=cases[k].speed; s->clip=cases[k].clip; s->prevClip=cases[k].clip; s->blend=1; s->handRelaxEnvelope=1;
        p->action=cases[k].action; p->action_time=cases[k].phase*game_action_duration(p->action); p->jump_time=0;
        sampleClip(cases[k].clip,clipLen(cases[k].clip)*cases[k].phase,s->pose);
        balanceTorso(s,cases[k].clip); memcpy(input,s->pose,sizeof(Transform)*(size_t)model.boneCount);
        jogHandRelax=0; relaxJogHands(s,cases[k].clip,1.f/30); diagnosticGrip(s,cases[k].clip,sprintOffset, cases[k].action==GAME_ACT_NONE && cases[k].speed>=5.96f ? follow : 0, replant);
        cw=cradleWeight(s); cradleValid=s->cradleValid;
        hasCenter=cradleValid && cases[k].action==GAME_ACT_NONE; if (hasCenter) center=s->cradleCenter;
        memcpy(raw,s->pose,sizeof(Transform)*(size_t)model.boneCount);
        memcpy(s->pose,input,sizeof(Transform)*(size_t)model.boneCount); s->handRelaxEnvelope=1; jogHandRelax=4;
        relaxJogHands(s,cases[k].clip,1.f/30); diagnosticGrip(s,cases[k].clip,sprintOffset, cases[k].action==GAME_ACT_NONE && cases[k].speed>=5.96f ? follow : 0, replant);
        if (memcmp(raw,s->pose,sizeof(Transform)*(size_t)model.boneCount) || cradleValid!=s->cradleValid ||
            (hasCenter && Vector3Distance(center,s->cradleCenter)>1e-6f)) { fclose(f); return 0; }
        if (k) fputc(',',f);
        fputs("{\"state\":",f); write_json_string(f,cases[k].name);
        fprintf(f,",\"cradle_weight\":%.9g,\"ball_radius\":%.9g,\"ball_center\":",cw,(float)BALL_R);
        if (hasCenter) fprintf(f,"[%.9g,%.9g,%.9g]",center.x,center.y,center.z); else fputs("null",f);
        fputs(",\"raw\":",f); if (!write_pose(f,raw,model.boneCount)) { fclose(f); return 0; }
        fputs(",\"adjusted\":",f); if (!write_pose(f,s->pose,model.boneCount)) { fclose(f); return 0; }
        fputc('}',f);
    }
    fputs("]}\n",f); if (fclose(f)) return 0;
    puts("grip_pose cases=12 exact_guard_noops=12 (scripted_cpu_pose_only)");
    UnloadModelAnimations(anims,animCount); return 1;
}

/* Synthetic moving player: one second warm-up then a one-second turn,
 * straight jog, sprint, jog and stop. Uses the renderer's matching and
 * raylib 5.5 blend helpers; no draw calls or simulation physics. */
static int export_turn_poses(const char *asset, const char *out, int fps, int apply_ik)
{
    FILE *f; AnimState *s = &as[9]; GamePlayer *p; float dt = 1.f/fps, face = 0;
    Transform raw[MAX_BONES];
    if ((fps != 30 && fps != 60) || !strcmp(asset, out) || !load_model_animation(asset)) return 0;
    detectJogDirection(); buildMotionDatabase(NULL);
    boneThighL = findBone("thigh_l"); boneThighR = findBone("thigh_r");
    boneCalfL = findBone("calf_l"); boneCalfR = findBone("calf_r");
    boneToeL = findBone("ball_l"); boneToeR = findBone("ball_r");
    boneSpine = findBone("spine_03"); boneSpine1 = findBone("spine_01");
    if (!motionReady || boneThighL < 0 || boneThighR < 0 || boneCalfL < 0 || boneCalfR < 0) return 0;
    f = fopen(out, "wb"); if (!f) return 0;
    game_init(&game); game.ball_team = -1; game.ball_player = -1;
    p = &game.players[0][9]; p->action = GAME_ACT_NONE; p->jump_time = 0;
    memset(s, 0, sizeof *s); s->speed = 3.0f; s->clip = C_JOG; s->prevClip = C_JOG;
    s->blend = 1.0f; s->yawInit = 1; poseFar = 0;
    fprintf(f, "{\"format\":1,\"fps\":%d,\"warmup_seconds\":1,\"ik\":%s,\"scenario\":\"turn-transition\",\"bones\":[", fps, apply_ik ? "true" : "false");
    for (int b = 0; b < model.boneCount; ++b) { if (b) fputc(',', f); write_json_string(f, model.bones[b].name); }
    fputs("],\"frames\":[", f);
    for (int step = 0; step < fps*6; ++step) {
        float now = (float)step/fps, targetSpeed, err, maxw, t, w; int clip;
        targetSpeed = now < 2.5f ? 3.0f : now < 3.5f ? 5.2f : now < 4.5f ? 3.0f : 0.0f;
        if (now >= 1.0f && now < 2.0f) face += 3.0f*dt;
        p->x += sinf(face)*targetSpeed*dt; p->z += cosf(face)*targetSpeed*dt;
        s->prevSpeed = s->speed; s->speed = Lerp(s->speed, targetSpeed, .35f);
        s->accel = (s->speed - s->prevSpeed)/dt; s->lastX = p->x; s->lastZ = p->z;
        s->turnRate = fabsf(wrapAngle(face - s->faceYaw))/dt; s->faceYaw = face;
        err = wrapAngle(face - s->bodyYaw); maxw = (s->turnRate > 2 ? 4.f : 7.5f)*dt;
        s->bodyYaw += Clamp(err, -maxw, maxw); err = wrapAngle(face - s->bodyYaw);
        if (err > .45f) s->bodyYaw = face-.45f;
        if (err < -.45f) s->bodyYaw = face+.45f;
        desiredClip(0, 9, p, s, dt, &clip, &t);
        matchGaitTransition(s, clip, &t);
        w = updatePoseBlend(s, clip, t, dt);
        sampleBlendedPose(s, clip, t, w);
        balanceTorso(s, clip);
        memcpy(raw, s->pose, sizeof(Transform)*(size_t)model.boneCount);
        if (apply_ik) { lengthenStride(s); plantFeet(s, dt); }
        coordinateTurn(s);
        { Transform after[MAX_BONES];
          memcpy(after, s->pose, sizeof(Transform)*(size_t)model.boneCount);
          memcpy(s->pose, raw, sizeof(Transform)*(size_t)model.boneCount);
          coordinateTurn(s);
          memcpy(raw, s->pose, sizeof(Transform)*(size_t)model.boneCount);
          memcpy(s->pose, after, sizeof(Transform)*(size_t)model.boneCount);
        }
        if (step < fps) continue;
        if (step > fps) fputc(',', f);
        fprintf(f, "{\"clip\":"); write_json_string(f, CLIP_NAMES[clip]);
        fprintf(f, ",\"blend\":%.9g,\"turn_rate\":%.9g,\"raw\":", s->blend, s->turnRate);
        if (!write_pose(f, raw, model.boneCount)) { fclose(f); return 0; }
        fputs(",\"adjusted\":", f);
        if (!write_pose(f, s->pose, model.boneCount)) { fclose(f); return 0; }
        fputc('}', f);
    }
    fputs("]}\n", f); if (fclose(f)) return 0;
    UnloadModelAnimations(anims, animCount); return 1;
}

int main(int argc, char **argv)
{
    const char *asset, *cache;
    if ((argc==5 || argc==6 || argc==9 || argc==10 || argc==11) && !strcmp(argv[1],"--export-grip-poses")) {
        float clearance=0, follow=0; Vector3 offset={0}; char *end=NULL; int replant=0;
        if (argc>=6) { clearance=strtof(argv[5],&end); if (end==argv[5] || *end || !isfinite(clearance) || clearance<.012f || clearance>.06f) { fprintf(stderr,"Invalid grip clearance\n"); return 1; } }
        if (argc>=9) {
            float *components[]={&offset.x,&offset.y,&offset.z};
            for (int i=0;i<3;++i) {
                *components[i]=strtof(argv[6+i],&end);
                if (end==argv[6+i] || *end || !isfinite(*components[i]) || fabsf(*components[i])>.20f) { fprintf(stderr,"Invalid sprint offset\n"); return 1; }
            }
        }
        if (argc>=10) {
            follow=strtof(argv[9],&end);
            if (end==argv[9] || *end || !isfinite(follow) || follow<0 || follow>1) { fprintf(stderr,"Invalid finger follow\n"); return 1; }
        }
        if (argc==11) {
            if (strcmp(argv[10],"0") && strcmp(argv[10],"1")) { fprintf(stderr,"Invalid finger replant\n"); return 1; }
            replant=argv[10][0]=='1';
            if (replant && follow<=0) { fprintf(stderr,"Finger replant requires follow\n"); return 1; }
        }
        if (!export_grip_poses(argv[2],argv[3],argv[4],clearance,offset,follow,replant)) { fprintf(stderr,"Grip pose export failed\n"); return 1; }
        return 0;
    }
    if (argc == 5 && !strcmp(argv[1], "--export-hand-transition")) {
        char *end; long fps=strtol(argv[4],&end,10);
        if (*end || (fps!=30 && fps!=60) || !export_hand_transition(argv[2],argv[3],(int)fps)) {
            fprintf(stderr,"Hand transition export failed\n"); return 1;
        }
        return 0;
    }
    if (argc == 6 && !strcmp(argv[1], "--export-hand-poses")) {
        char *endMode, *endFps; long mode=strtol(argv[4],&endMode,10), fps=strtol(argv[5],&endFps,10);
        if (*endMode || *endFps || mode < 0 || mode > 4 || (fps != 30 && fps != 60) ||
            !export_hand_poses(argv[2],argv[3],(int)mode,(int)fps)) {
            fprintf(stderr,"Hand pose export failed\n"); return 1;
        }
        return 0;
    }
    if ((argc == 5 || argc == 6) && !strcmp(argv[1], "--export-turn-poses")) {
        char *end; long fps = strtol(argv[4], &end, 10);
        if (*end || (fps != 30 && fps != 60) || (argc == 6 && strcmp(argv[5], "--no-ik")) ||
            !export_turn_poses(argv[2], argv[3], (int)fps, argc == 5)) {
            fprintf(stderr, "Turn pose export failed\n"); return 1;
        }
        return 0;
    }
    if (argc == 6 || argc == 7) {
        if (!strcmp(argv[1], "--export-jog-poses") &&
            (argc == 6 || !strcmp(argv[6], "--no-ik"))) {
            char *endSpeed, *endFps;
            float speed = strtof(argv[4], &endSpeed); long fps = strtol(argv[5], &endFps, 10);
            if (*endSpeed || *endFps || (fps != 30 && fps != 60) ||
                !export_jog_poses(argv[2], argv[3], speed, (int)fps, argc == 6)) {
                fprintf(stderr, "Jog pose export failed\n"); return 1;
            }
            return 0;
        }
    }
    if (argc != 3) { fprintf(stderr, "Usage: motion_headless MODEL.glb OUTPUT.gfmotion\n"); return 2; }
    asset = argv[1]; cache = argv[2];
    { size_t len = strlen(asset); if (len < 4 || strcmp(asset + len - 4, ".glb")) {
        fprintf(stderr, "Only self-contained .glb models are supported.\n"); return 2;
    } }
    if (!load_model_animation(asset)) { fprintf(stderr, "Invalid or unsupported model animations: %s\n", asset); return 1; }
    detectContacts(); detectJogDirection();
    printf("jog_playback=%s\n", reverseJog ? "reversed" : "authored");
    initActionMetadata(); buildMotionDatabase(NULL); buildActionDatabase();
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
    if (!validate_jog_playback() || !validate_pose_blend() || !validate_locomotion_transition() || !report_jog_motion() || !validate_old_cache_fallback(cache) || !validate_late_observation() ||
        !validate_offscreen_release(1.f/60.f, 0) || !validate_offscreen_release(1.f/30.f, 0) ||
        !validate_offscreen_release(1.f/60.f, 1) || !validate_offscreen_release(1.f/30.f, 1) ||
        !validate_action(GAME_ACT_HANDPASS, 1.f/60.f) || !validate_action(GAME_ACT_HANDPASS, 1.f/30.f) ||
        !validate_action(GAME_ACT_SOLO, 1.f/60.f) || !validate_action(GAME_ACT_SOLO, 1.f/30.f) ||
        !validate_interruption() || !validate_leg_ik() || !validate_jog_arm_assist() || !validate_jog_hand_relax() || !validate_extra_hand_relax(2) || !validate_extra_hand_relax(3) || !validate_extra_hand_relax(4) || !validate_jog_stride_ramp() || !report_jog_ground_proxy(1.f/30, 2.0f) || !report_jog_ground_proxy(1.f/60, 2.0f) || !report_jog_ground_proxy(1.f/30, 3.5f) || !report_jog_ground_proxy(1.f/60, 3.5f) || !validate_plant_envelope() || !validate_torso_and_grip() || !compare_entry_poses(GAME_ACT_HANDPASS) ||
        !compare_entry_poses(GAME_ACT_SOLO) || !benchmark_search()) {
        fprintf(stderr, "Action integration check failed\n"); return 1;
    }
    UnloadModelAnimations(anims, animCount);
    puts("Headless motion checks passed (no rendering or visual validation).");
    return 0;
}
#endif

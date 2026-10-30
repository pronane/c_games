/* race.c : race setup, countdown, laps, ranking, cameras, results */
#include "common.h"

static const int GP_POINTS[8] = { 9, 6, 3, 1, 0, 0, 0, 0 };
static int attractFocus = 0;
static float attractTimer = 0;

/* ------------------------------------------------------------------ */
/* Time-trial ghost: the best lap is recorded at 20 Hz and replayed as a */
/* translucent kart on every following lap. Saved per track.            */
/* ------------------------------------------------------------------ */
static const char *GhostFile(int track) { return TextFormat("ghost_track%d.dat", track + 1); }

void GhostLoad(int track)
{
    if (G.ghostValid && G.ghost.track == track) return;
    G.ghostValid = false;
    if (G.autotest) return;                       /* tests always start without a ghost */
    int size = 0;
    unsigned char *d = LoadFileData(GhostFile(track), &size);
    if (!d) return;
    if (size == (int)sizeof(G.ghost) && ((int *)d)[0] == track) {
        memcpy(&G.ghost, d, sizeof(G.ghost));
        if (G.ghost.n > 10 && G.ghost.n <= GHOST_MAX && G.ghost.charId >= 0 && G.ghost.charId < NUM_CHARACTERS) G.ghostValid = true;
    }
    UnloadFileData(d);
}

static void GhostRecord(void)
{
    Kart *k = &R.karts[0];
    float lt = R.time - k->lapStartTime;
    int want = (int)(lt*GHOST_HZ);
    while (G.ghostRec.n <= want && G.ghostRec.n < GHOST_MAX) {
        int i = G.ghostRec.n++;
        G.ghostRec.x[i] = k->pos.x; G.ghostRec.y[i] = k->pos.y; G.ghostRec.z[i] = k->pos.z;
        G.ghostRec.yaw[i] = k->heading + k->visYaw;
    }
}

static void GhostLapDone(float lapTime)
{
    Kart *k = &R.karts[0];
    if (G.ghostRec.n > 10 && G.ghostRec.n < GHOST_MAX && (!G.ghostValid || G.ghost.track != T.index || lapTime < G.ghost.lapTime)) {
        G.ghostRec.track = T.index; G.ghostRec.charId = k->charId; G.ghostRec.lapTime = lapTime;
        memcpy(&G.ghost, &G.ghostRec, sizeof(G.ghost));
        G.ghostValid = true;
        if (!G.autotest) SaveFileData(GhostFile(T.index), &G.ghost, (int)sizeof(G.ghost));
        if (G.autotest) ALog("GHOST: new best lap %s recorded (%d samples) on %s", FormatTime(lapTime), G.ghost.n, T.def->name);
        if (k->human >= 0) { strcpy(R.banner[k->human], "NEW BEST LAP!"); R.bannerTimer[k->human] = 2.2f; }
    }
    G.ghostRec.n = 0;
}

bool GhostPose(float lapT, Vector3 *pos, float *yaw)
{
    if (!G.ghostValid || G.ghost.track != T.index || lapT < 0 || lapT > G.ghost.lapTime) return false;
    float f = lapT*GHOST_HZ;
    int i0 = (int)f;
    if (i0 >= G.ghost.n - 1) i0 = G.ghost.n - 2;
    if (i0 < 0) i0 = 0;
    float a = Clamp(f - i0, 0, 1);
    int i1 = i0 + 1;
    pos->x = Lerp(G.ghost.x[i0], G.ghost.x[i1], a);
    pos->y = Lerp(G.ghost.y[i0], G.ghost.y[i1], a);
    pos->z = Lerp(G.ghost.z[i0], G.ghost.z[i1], a);
    *yaw = LerpAngle(G.ghost.yaw[i0], G.ghost.yaw[i1], a);
    return true;
}

void RaceStart(int trackIndex, bool attract)
{
    TrackBuild(&T, trackIndex);
    memset(&R, 0, sizeof(R));
    SimSeed(G.mode == MODE_ONLINE && !attract ? G.netSeed : (uint32_t)rand()*2654435761u + 1u);
    R.attract = attract;
    R.timeTrial = (!attract && G.mode == MODE_TT);
    R.numHumans = attract ? 0 : ((G.mode == MODE_VS || G.mode == MODE_ONLINE) ? 2 : 1);
    R.netInputs = !attract && G.mode == MODE_ONLINE;
    if (G.autotest && !attract && G.mode != MODE_VS) R.numHumans = 1;

    int chars[MAX_RACERS], humanOf[MAX_RACERS];
    int n = 0;
    if (R.timeTrial) {
        chars[0] = G.humanChar[0]; humanOf[0] = 0; n = 1;
    } else if (G.mode == MODE_GP && !attract) {
        for (int i = 0; i < MAX_RACERS; i++) { chars[i] = G.gpChars[i]; humanOf[i] = (i == 0) ? 0 : -1; }
        n = MAX_RACERS;
    } else {
        bool used[MAX_CHARACTERS] = { 0 };
        for (int h = 0; h < R.numHumans; h++) { chars[n] = G.humanChar[h]; humanOf[n] = h; used[G.humanChar[h]] = true; n++; }
        int pool[MAX_CHARACTERS], pn = 0;
        for (int c = 0; c < NUM_CHARACTERS; c++) if (!used[c]) pool[pn++] = c;
        for (int i = pn - 1; i > 0; i--) { int j = (int)(SimRand() % (uint32_t)(i + 1)); int t = pool[i]; pool[i] = pool[j]; pool[j] = t; }
        for (int i = 0; n < MAX_RACERS && i < pn; i++) { chars[n] = pool[i]; humanOf[n] = -1; n++; }
        while (n < MAX_RACERS) { chars[n] = (int)(SimRand() % NUM_CHARACTERS); humanOf[n] = -1; n++; }
    }
    R.numKarts = n;

    /* grid: best GP points at the front, humans at the back on equal points */
    int order[MAX_RACERS];
    for (int i = 0; i < n; i++) order[i] = i;
    for (int i = 0; i < n; i++) for (int j = i + 1; j < n; j++) {
        int a = order[i], b = order[j];
        int pa = (G.mode == MODE_GP && !attract) ? G.gpPoints[a] : 0;
        int pb = (G.mode == MODE_GP && !attract) ? G.gpPoints[b] : 0;
        bool swap = pb > pa || (pb == pa && humanOf[a] >= 0 && humanOf[b] < 0);
        if (swap) { order[i] = b; order[j] = a; }
    }
    for (int g = 0; g < n; g++) {
        int i = order[g];
        int slot = R.timeTrial ? 0 : g;
        KartInit(&R.karts[i], chars[i], humanOf[i], slot);
        if (humanOf[i] >= 0) {
            R.humanKart[humanOf[i]] = i;
            if (G.autotest) R.karts[i].autopilot = true;
        }
    }
    if (R.timeTrial) { R.karts[0].item = ITEM_PEPPER3; R.karts[0].itemCount = 3; GhostLoad(trackIndex); G.ghostRec.n = 0; }

    ItemsReset();
    RaceComputePlaces();
    R.phase = attract ? RACE_RUNNING : RACE_INTRO;
    R.phaseTime = 0;
    R.countdown = 3.0f;
    R.lastBeep = 4;
    for (int h = 0; h < MAX_HUMANS; h++) {
        int ki = R.humanKart[h];
        Kart *k = &R.karts[ki];
        R.camYaw[h] = k->heading;
        R.camFov[h] = 60;
        R.cam[h].up = (Vector3){ 0, 1, 0 };
        R.cam[h].projection = CAMERA_PERSPECTIVE;
        R.cam[h].fovy = 60;
        R.cam[h].position = Vector3Add(k->pos, (Vector3){ -sinf(k->heading)*6, 3, -cosf(k->heading)*6 });
        R.cam[h].target = k->pos;
    }
    attractFocus = 0; attractTimer = 0;
    RenderResize();
    if (!attract) MusicPlay(trackIndex);
    MusicSetTempo(1.0f);
}

void RaceComputePlaces(void)
{
    int idx[MAX_RACERS];
    for (int i = 0; i < R.numKarts; i++) idx[i] = i;
    for (int i = 0; i < R.numKarts; i++) for (int j = i + 1; j < R.numKarts; j++) {
        Kart *a = &R.karts[idx[i]], *b = &R.karts[idx[j]];
        bool swap;
        if (a->finished && b->finished) swap = b->finishTime < a->finishTime;
        else if (a->finished != b->finished) swap = b->finished;
        else swap = b->progress > a->progress;
        if (swap) { int t = idx[i]; idx[i] = idx[j]; idx[j] = t; }
    }
    for (int i = 0; i < R.numKarts; i++) R.karts[idx[i]].place = i + 1;
}

int RaceKartAhead(int idx)
{
    int p = R.karts[idx].place;
    if (p <= 1) return -1;
    for (int i = 0; i < R.numKarts; i++) if (R.karts[i].place == p - 1) return i;
    return -1;
}

static void Banner(int h, const char *txt)
{
    strncpy(R.banner[h], txt, 31);
    R.banner[h][31] = 0;
    R.bannerTimer[h] = 2.2f;
}

static bool Quiet(void) { return G.autotest && G.autoSpeed > 1; }

void RaceOnLap(int idx)
{
    Kart *k = &R.karts[idx];
    k->lap++;
    float lt = R.time - k->lapStartTime;
    k->lastLapTime = lt;
    if (k->bestLap <= 0 || lt < k->bestLap) k->bestLap = lt;
    if (R.timeTrial && idx == 0 && !R.attract) GhostLapDone(lt);
    k->lapStartTime = R.time;
    if (R.attract) return;
    if (k->lap >= NUM_LAPS && !k->finished) {
        k->finished = true;
        k->finishTime = R.time;
        R.finishOrder[R.numFinished++] = idx;
        RaceComputePlaces();
        if (k->human >= 0) {
            k->autopilot = true;
            Banner(k->human, "FINISH!");
            if (!Quiet()) { PlaySfx(SFX_FINISH, 0.9f, 1.0f); if (k->place <= 3) PlayVoice(k->charId, 2); }
        }
        return;
    }
    if (k->human >= 0) {
        if (k->lap == NUM_LAPS - 1) {
            Banner(k->human, "FINAL LAP!");
            if (!Quiet()) PlaySfx(SFX_FINALLAP, 0.9f, 1.0f);
            if (!R.finalLapMusic) { R.finalLapMusic = true; MusicSetTempo(1.1f); }
        } else {
            Banner(k->human, TextFormat("LAP %d", k->lap + 1));
            if (!Quiet()) PlaySfx(SFX_LAP, 0.8f, 1.0f);
        }
    }
}

static void UpdateChaseCam(int h, float dt)
{
    Kart *k = &R.karts[R.humanKart[h]];
    Camera3D *c = &R.cam[h];
    float targetYaw = k->heading + k->visYaw*0.3f;
    R.camYaw[h] = LerpAngle(R.camYaw[h], targetYaw, Clamp(1.0f - expf(-5.5f*dt), 0, 1));
    float dist = 6.4f, height = 2.7f;
    float yaw = R.camYaw[h];
    if (R.phase == RACE_INTRO) {
        float t = Clamp(R.phaseTime/2.6f, 0, 1);
        float e = 1.0f - (1.0f - t)*(1.0f - t);
        yaw += PI*(1.0f - e);
        dist += 10.0f*(1.0f - e);
        height += 7.0f*(1.0f - e);
    }
    Vector3 back = { sinf(yaw), 0, cosf(yaw) };
    Vector3 want = { k->pos.x - back.x*dist, k->pos.y + height, k->pos.z - back.z*dist };
    float sy = Clamp(1.0f - expf(-9.0f*dt), 0, 1);
    float sxz = R.phase == RACE_INTRO ? 1.0f : Clamp(1.0f - expf(-25.0f*dt), 0, 1);
    c->position.x = Lerp(c->position.x, want.x, sxz);
    c->position.z = Lerp(c->position.z, want.z, sxz);
    c->position.y = Lerp(c->position.y, want.y, sy);
    int s; float lat, al, gy;
    TrackLocate(&T, c->position, k->seg, &s, &lat, &al, &gy);
    if (k->onShortcut || gy > k->groundY + 4.0f) gy = k->groundY;
    if (c->position.y < gy + 1.2f) c->position.y = gy + 1.2f;
    c->target = (Vector3){ k->pos.x + back.x*3.0f, k->pos.y + 1.3f, k->pos.z + back.z*3.0f };
    if (R.shake[h] > 0) {
        R.shake[h] -= dt;
        float s2 = R.shake[h]*0.6f;
        c->target.x += RandF(-s2, s2); c->target.y += RandF(-s2, s2);
    }
    float fovT = 62.0f + (k->boostTimer > 0 ? 10.0f : 0.0f) + Clamp(k->speed/KartTopSpeed(k), 0, 1.3f)*4.0f + (k->turboFlash > 0 ? 8.0f : 0.0f);
    R.camFov[h] = Approach(R.camFov[h], fovT, (k->turboFlash > 0 ? 90.0f : 40.0f)*dt);
    c->fovy = R.camFov[h];
}

static void UpdateAttractCamera(float dt)
{
    attractTimer -= dt;
    if (attractTimer <= 0) {
        attractTimer = 9.0f;
        attractFocus = rand() % R.numKarts;
    }
    Kart *k = &R.karts[attractFocus];
    Camera3D *c = &R.cam[0];
    float yaw = k->heading + 0.6f*sinf(G.time*0.25f);
    R.camYaw[0] = LerpAngle(R.camYaw[0], yaw, Clamp(2.0f*dt, 0, 1));
    Vector3 back = { sinf(R.camYaw[0]), 0, cosf(R.camYaw[0]) };
    Vector3 want = { k->pos.x - back.x*9.0f, k->pos.y + 4.0f, k->pos.z - back.z*9.0f };
    c->position = Vector3Lerp(c->position, want, Clamp(4.0f*dt, 0, 1));
    if (Vector3Distance(c->position, want) > 40) c->position = want;
    c->target = Vector3Add(k->pos, (Vector3){ 0, 1.2f, 0 });
    c->up = (Vector3){ 0, 1, 0 };
    c->fovy = 58;
    c->projection = CAMERA_PERSPECTIVE;
}

/* Online buttons -> KartInput. Bits 0-4: steer -15..15 (+16), 5 accel, 6 brake, 7 hop, 8 item.
   Presses come from the previous step's bits, which are part of the sim state. */
static void NetKartInput(int h, KartInput *in)
{
    uint16_t b = R.netBits[h], p = R.netPrev[h];
    memset(in, 0, sizeof(*in));
    in->steer = Clamp(((int)(b & 31) - 16)/15.0f, -1, 1);
    bool accel = b & (1 << 5), brake = b & (1 << 6), hop = b & (1 << 7), item = b & (1 << 8);
    in->accel = accel;
    in->brake = brake && !accel;
    in->back = brake;
    in->hop = hop;
    in->hopPressed = hop && !(p & (1 << 7));
    in->item = item;
    in->itemPressed = item && !(p & (1 << 8));
}

void RaceUpdate(float dt)
{
    R.simFrames++;
    R.phaseTime += dt;
    if (R.phase == RACE_INTRO && R.phaseTime > 2.6f) {
        R.phase = RACE_COUNTDOWN; R.phaseTime = 0; R.countdown = 3.0f; R.lastBeep = 4;
    }
    if (R.phase == RACE_COUNTDOWN) {
        R.countdown -= dt;
        int c = (int)ceilf(R.countdown);
        if (c < R.lastBeep && c >= 1) { R.lastBeep = c; if (!Quiet()) PlaySfx(SFX_BEEP_LOW, 0.8f, 1.0f); }
        if (R.countdown <= 0) {
            R.phase = RACE_RUNNING; R.phaseTime = 0; R.time = 0;
            if (!Quiet()) PlaySfx(SFX_BEEP_HIGH, 0.9f, 1.0f);
            for (int i = 0; i < R.numKarts; i++) {
                Kart *k = &R.karts[i];
                k->lapStartTime = 0;
                if (k->human >= 0 && !k->autopilot) {
                    /* rocket start: hit the gas just as "1" shows (0.3s - 1.0s before GO) */
                    if (k->startBoostWindow > 0.3f && k->startBoostWindow < 1.0f) { k->boostTimer = 1.0f; k->boostPower = 0.35f; k->statBoosts++; if (!Quiet()) PlaySfx(SFX_BOOST, 0.8f, 1.0f); }
                    else if (k->startBoostWindow >= 1.6f) { k->spinTimer = 0.8f; }
                } else if (k->human < 0 && SimRand() % 3 == 0) {
                    k->boostTimer = 0.8f; k->boostPower = 0.3f;
                }
            }
        }
    }
    if (R.phase == RACE_RUNNING || R.phase == RACE_DONE) R.time += dt;

    /* drive */
    for (int i = 0; i < R.numKarts; i++) {
        Kart *k = &R.karts[i];
        KartInput in;
        if (k->human >= 0 && !k->autopilot) {
            if (R.netInputs) NetKartInput(k->human, &in);
            else InputRead(k->human, &in);
        }
        else KartAIInput(i, &in, dt);
        if (R.phase == RACE_COUNTDOWN && in.accel && k->startBoostWindow < 0) k->startBoostWindow = R.countdown;
        if (in.itemPressed && (R.phase == RACE_RUNNING || R.phase == RACE_DONE || R.attract)) ItemUse(i);
        KartUpdate(i, &in, dt);
    }
    if (R.netInputs) for (int h = 0; h < MAX_HUMANS; h++) R.netPrev[h] = R.netBits[h];
    if (R.timeTrial && R.phase == RACE_RUNNING && !R.karts[0].finished) GhostRecord();
    KartsCollide();
    ItemsUpdate(dt);
    ItemBoxesUpdate(dt);
    ParticlesUpdate(dt);
    RaceComputePlaces();

    if (R.attract) { UpdateAttractCamera(dt); return; }
    for (int h = 0; h < R.numHumans; h++) {
        UpdateChaseCam(h, dt);
        if (R.bannerTimer[h] > 0) R.bannerTimer[h] -= dt;
        Kart *k = &R.karts[R.humanKart[h]];
        if (!Quiet() && (G.netView < 0 || h == G.netView)) {
            EngineSet(h, k->speed/KartTopSpeed(k) + (k->boostTimer > 0 ? 0.25f : 0), G.screen == SCR_RACE ? 0.16f : 0.05f);
            DriftLoop(h, k->driftState == 2 && k->grounded, k->sparkLevel);
        }
    }

    bool allHumansDone = R.numHumans > 0;
    for (int h = 0; h < R.numHumans; h++) if (!R.karts[R.humanKart[h]].finished) allHumansDone = false;
    if (allHumansDone && R.phase == RACE_RUNNING) { R.phase = RACE_DONE; R.doneTimer = 0; }
    if (R.phase == RACE_DONE) R.doneTimer += dt;
}

/* final classification: unfinished karts get an estimated time */
void RaceEnd(void)
{
    for (int i = 0; i < R.numKarts; i++) {
        Kart *k = &R.karts[i];
        if (!k->finished) {
            float remaining = (float)(NUM_LAPS*T.n) - k->progress;
            if (remaining < 0) remaining = 0;
            k->finishTime = R.time + remaining*T.spacing/(KartTopSpeed(k)*0.85f) + 0.5f + i*0.01f;
            k->finished = true;
        }
    }
    RaceComputePlaces();
    if (G.mode == MODE_GP && !R.attract) {
        for (int i = 0; i < R.numKarts; i++) {
            G.gpLastPoints[i] = GP_POINTS[R.karts[i].place - 1];
            G.gpLastPlace[i] = R.karts[i].place;
            G.gpPoints[i] += G.gpLastPoints[i];
        }
    }
    if (R.timeTrial) {
        Kart *k = &R.karts[0];
        float best = G.bestTimes[T.index];
        if (best <= 0 || k->finishTime < best) { G.bestTimes[T.index] = k->finishTime; SaveSettings(); }
    }
}

void RaceDraw(void)
{
    int W = GetScreenWidth(), H = GetScreenHeight();
    int views = R.attract ? 1 : (R.numHumans == 2 && G.netView < 0 ? 2 : 1);
    int vh = H/views;
    int hv0 = G.netView >= 0 ? G.netView : 0;     /* online: the one human this window plays */
    if (RenderDirect()) {
        ClearBackground(BLACK);
        for (int v = 0; v < views; v++)
            RenderWorldView(v, R.cam[hv0 + v], R.attract ? attractFocus : R.humanKart[hv0 + v], (Rectangle){ 0, (float)(v*vh), (float)W, (float)vh });
    } else {
    for (int v = 0; v < views; v++) {
        RenderWorldView(v, R.cam[hv0 + v], R.attract ? attractFocus : R.humanKart[hv0 + v], (Rectangle){ 0, (float)(v*vh), (float)W, (float)vh });
    }
    ClearBackground(BLACK);
    }
    for (int v = 0; v < views && !RenderDirect(); v++) {
        int dw = G.viewW*G.viewScale, dh = G.viewH*G.viewScale;
        float ox = (float)((W - dw)/2), oy = (float)(v*vh + (vh - dh)/2);
        /* opaque blit: translucent things (ghost, smoke) must not punch alpha holes into the view */
        rlDrawRenderBatchActive(); rlDisableColorBlend();
        DrawTexturePro(G.view[v].texture, (Rectangle){ 0, 0, (float)G.viewW, -(float)G.viewH },
                       (Rectangle){ ox, oy, (float)dw, (float)dh }, (Vector2){ 0, 0 }, 0, WHITE);
        rlDrawRenderBatchActive(); rlEnableColorBlend();
    }
    if (RenderDirect()) {
        /* ENHANCED "bloom-ish" lift: a faint additive sky glow over the upper part of each view */
        BeginBlendMode(BLEND_ADDITIVE);
        Color top = T.def->night ? (Color){ 40, 30, 60, 255 } : (Color){ 46, 42, 34, 255 };
        for (int v = 0; v < views; v++) DrawRectangleGradientV(0, v*vh, W, (int)(vh*0.55f), top, (Color){ 0, 0, 0, 255 });
        EndBlendMode();
    }
    if (views == 2) DrawRectangle(0, vh - 2, W, 4, BLACK);
    if (R.attract) return;
    for (int v = 0; v < views; v++) DrawHUD(hv0 + v, (Rectangle){ 0, (float)(v*vh), (float)W, (float)vh });
    float ms = fminf(W, H)*(views == 2 ? 0.26f : 0.24f);
    Rectangle mr = views == 2 ? (Rectangle){ W - ms - 16, H*0.5f - ms*0.5f, ms, ms } : (Rectangle){ W - ms - 20, H - ms - 50, ms, ms };
    DrawMinimap(mr);
}

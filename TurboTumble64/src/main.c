#include <ctype.h>
/*  TURBO TUMBLE 64
 *  An original N64-era style kart racer in C + raylib.
 *  Everything (models, textures, tracks, music, sound) is generated in code.
 *
 *  main.c : window, main loop, and the --autotest harness
 */
#include "common.h"
#include <time.h>
#include <stdarg.h>

Game G;
Race R;
Track T;


/* ------------------------------------------------------------------ */
/* automated test (--autotest): drives the real game loop with the CPU  */
/* at the wheel of player 1, races every track, logs pass/fail          */
/* ------------------------------------------------------------------ */
typedef struct {
    int stage;          /* 0 title, 1 char select, 2 track select, 3.. races, then VS, then done */
    int frames;
    int race;
    int frontStage, frontFrames;
    bool shotCountdown, shotA, shotB, shotC, shotRes, shotSc, shotBump, shotDrift, shotDrift2, shotRoul, shotGhost;
    int miniTurbos;
    bool ttGhostSeen;
    double raceRealStart;
    long raceFrames;
    int resultsFrames;
    FILE *log;
    int failures;
    double fpsSum; int fpsCount;
    double perfStart; long perfFrames; int perfDone;
    float worstFrame;
} AutoTest;
static AutoTest AT;
static bool quipsOnly = false;
static int gForcePlayer = -1;   /* forced-win test: this racer is the player */
static int tourTrack = 0;        /* --tour N: scripted start / landmark / hazard shots of a v7 course */
static bool stadiumTour = false; /* --stadium: scripted v7 shots of Mudslide Megadome */   /* --quips: only the forced-win victory quip cases */
static bool pendingShot = false;
static char pendingShotName[320];

static void Shot(const char *name)
{
    snprintf(pendingShotName, sizeof pendingShotName, "%s/%s%s", G.shotDir, G.shotPrefix, name);
    pendingShot = true;
}

void ALog(const char *fmt, ...)
{
    char buf[1024];
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(buf, sizeof buf, fmt, ap);
    va_end(ap);
    printf("[AUTOTEST] %s\n", buf);
    fflush(stdout);
    if (AT.log) { fprintf(AT.log, "%s\n", buf); fflush(AT.log); }
}

static int FindCharPrefix(const char *prefix)
{
    for (int i = 0; i < NUM_CHARACTERS; i++) if (!strncmp(CHARACTERS[i].name, prefix, strlen(prefix))) return i;
    return -1;
}

static void AutotestBeginRace(int r)
{
    G.mode = MODE_GP;
    G.numHumans = 1;
    /* photo / data-driven racers take turns as the player: race 2 Baby Eabha, race 4 Towelhead Qanna,
       race 6 Mango Mo (looked up by folder order, i.e. after the 8 built-ins) */
    int eabha = FindCharPrefix("Baby"), qanna = FindCharPrefix("Towelhead"), mango = FindCharPrefix("Mango");
    int pick = r == 1 ? eabha : r == 3 ? qanna : r == 5 ? mango : -1;
    if (gForcePlayer >= 0) pick = gForcePlayer;
    G.humanChar[0] = pick >= 0 ? pick : (r*3 + 1) % 8;
    /* fill the grid: data-driven racers first (so they also race as CPUs), then the built-ins */
    int n = 0;
    G.gpChars[n++] = G.humanChar[0];
    for (int c = 8; c < NUM_CHARACTERS && n < MAX_RACERS; c++) if (c != G.humanChar[0]) G.gpChars[n++] = c;
    for (int c = 0; c < 8 && c < NUM_CHARACTERS && n < MAX_RACERS; c++) if (c != G.humanChar[0]) G.gpChars[n++] = c;
    if (r == 0 || G.autoOnly > 0) { memset(G.gpPoints, 0, sizeof(G.gpPoints)); memset(G.gpLastPoints, 0, sizeof(G.gpLastPoints)); }
    G.gpRace = r;
    G.gpCup = -1;                 /* autotest GP = every course in index order */
    RaceStart(r, false);
    GoToScreen(SCR_RACE);
    AT.frontStage = 0; G.autoFrontCam = 0;
    AT.shotCountdown = AT.shotA = AT.shotB = AT.shotC = AT.shotRes = AT.shotSc = AT.shotBump = AT.shotDrift = AT.shotDrift2 = AT.shotRoul = false;
    AT.raceRealStart = GetTime();
    AT.raceFrames = 0;
    AT.resultsFrames = 0;
    ALog("---- Race %d: %s  (player = %s, %d samples, lap length %.0f) ----", r + 1, T.def->name,
         CHARACTERS[G.humanChar[0]].name, T.n, T.length);
}

static void AutotestReportRace(void)
{
    Kart *pk = &R.karts[R.humanKart[0]];
    int got = 0, used = 0, hits = 0, bumps = 0, boosts = 0, realFinish = 0;
    bool nan = false;
    for (int i = 0; i < R.numKarts; i++) {
        Kart *k = &R.karts[i];
        got += k->statItemsGot; used += k->statItemsUsed; hits += k->statHits; bumps += k->statBumps; boosts += k->statBoosts;
        if (k->lap >= NUM_LAPS) realFinish++;
        if (isnan(k->pos.x) || isnan(k->pos.y) || isnan(k->pos.z)) nan = true;
    }
    double real = GetTime() - AT.raceRealStart;
    double fps = AT.raceFrames/(real > 0 ? real : 1);
    AT.fpsSum += fps; AT.fpsCount++;
    ALog("player %s: laps=%d place=%d time=%s bestLap=%s items got=%d used=%d hits=%d wallBumps=%d boosts=%d",
         CHARACTERS[pk->charId].name, pk->lap, pk->place, FormatTime(pk->finishTime), FormatTime(pk->bestLap),
         pk->statItemsGot, pk->statItemsUsed, pk->statHits, pk->statBumps, pk->statBoosts);
    ALog("all racers: items got=%d used=%d hits=%d boosts=%d, %d/%d crossed the line for real, sim race time %.1fs",
         got, used, hits, boosts, realFinish, R.numKarts, R.time);
    for (int p = 1; p <= R.numKarts; p++)
        for (int i = 0; i < R.numKarts; i++) if (R.karts[i].place == p)
            ALog("   %d. %-13s %s%s", p, CHARACTERS[R.karts[i].charId].name, FormatTime(R.karts[i].finishTime), R.karts[i].human >= 0 ? "  <- P1" : "");
    ALog("render loop: %ld frames in %.1fs real (%.0f fps with %dx sim steps/frame)", AT.raceFrames, real, fps, G.autoSpeed);
    int scAll = 0, cpuSc = 0, jumps = 0, bumpAirs = 0;
    for (int i = 0; i < R.numKarts; i++) { scAll += R.karts[i].shortcutsTaken; if (R.karts[i].human < 0) cpuSc += R.karts[i].shortcutsTaken; jumps += R.karts[i].statJumps; bumpAirs += R.karts[i].statBumpAirs; }
    ALog("terrain: shortcut taken by P1 %d time(s), by CPUs %d time(s); landing boosts %d; mogul lift-offs %d (P1 %d)",
         pk->shortcutsTaken, cpuSc, jumps, bumpAirs, pk->statBumpAirs);
    if (T.def->followTerrain) {
        int hz = 0, rs = 0, cpuLaps = 0;
        for (int i = 0; i < R.numKarts; i++) { hz += R.karts[i].statHazardHits; rs += R.karts[i].statRescues; if (R.karts[i].human < 0 && R.karts[i].lap >= NUM_LAPS) cpuLaps++; }
        ALog("course: hazard hits %d (P1 %d), drone rescues %d (P1 %d), CPUs that completed all %d laps: %d/%d", hz, pk->statHazardHits, rs, pk->statRescues, NUM_LAPS, cpuLaps, R.numKarts - 1);
    }
    int mtB = 0, mtO = 0;
    for (int i = 0; i < R.numKarts; i++) { mtB += R.karts[i].statMiniTurbos[1]; mtO += R.karts[i].statMiniTurbos[2]; }
    AT.miniTurbos += mtB + mtO;
    ALog("drift: P1 mini-turbos blue=%d orange=%d; all racers blue=%d orange=%d", pk->statMiniTurbos[1], pk->statMiniTurbos[2], mtB, mtO);
    if (mtB + mtO == 0) ALog("  FAIL: nobody fired a mini-turbo");
    bool scOk = pk->shortcutsTaken >= 1;
    bool bumpOk = T.def->numBumps == 0 || pk->statBumpAirs > 0;
    bool lapOk = pk->lap == NUM_LAPS;
    if (!scOk) ALog("  FAIL: player autopilot did not complete the shortcut");
    if (!bumpOk) ALog("  FAIL: no airtime off the moguls");
    if (!lapOk) ALog("  FAIL: lap count %d != %d", pk->lap, NUM_LAPS);
    (void)scAll;
    bool ok = lapOk && scOk && bumpOk && (mtB + mtO) > 0 && got > 0 && used > 0 && hits > 0 && !nan && realFinish >= 4;
    ALog("RESULT race %d: %s", AT.race + 1, ok ? "PASS" : "FAIL");
    if (!ok) AT.failures++;
}

/* lap/checkpoint logic: teleport a kart along scripted paths and check the lap counter */
static void Teleport(int idx, Vector3 p)
{
    Kart *k = &R.karts[idx];
    k->pos = p; k->speed = 0; k->vy = 0; k->grounded = true;
    KartInput in; memset(&in, 0, sizeof in);
    KartUpdate(idx, &in, SIM_DT);
}
static void CheckpointTest(int track)
{
    RaceStart(track, false);
    R.phase = RACE_RUNNING;
    int idx = R.humanKart[0];
    Kart *k = &R.karts[idx];
    int n = T.n, s0 = TrackWrap(&T, k->seg);
    int startLap = k->lap;
    bool ok = true;
    /* 1. drive past the line, reverse 80 samples back over it, then forward again: must be lap 0 still, then 1 after a real lap */
    for (int s = s0 - n; s <= 20; s += 2) Teleport(idx, TrackPoint(&T, s, 0));
    for (int i = 0; i < 40; i++) Teleport(idx, TrackPoint(&T, 20 - i*2, 0));
    for (int i = 0; i < 40; i++) Teleport(idx, TrackPoint(&T, -60 + i*2, 0));
    int lapA = k->lap;
    ALog("CHECKPOINT %s: reversed over the line and back -> lap %d (expect %d)", T.def->name, lapA, startLap);
    if (lapA != startLap) ok = false;
    /* 2. a full lap that uses the shortcut: forward to the entry, along the shortcut, out and round to the line */
    for (int s = 20; s < T.scA; s += 2) Teleport(idx, TrackPoint(&T, s, 0));
    for (int i = 0; i < T.scN; i++) Teleport(idx, T.sc[i].pos);
    bool wasOn = k->shortcutsTaken > 0;
    for (int s = T.scB; s < n + 20; s += 2) Teleport(idx, TrackPoint(&T, s, 0));
    ALog("CHECKPOINT %s: lap via shortcut -> lap %d (expect %d), shortcut registered=%s", T.def->name, k->lap, startLap + 1, wasOn ? "yes" : "no");
    if (k->lap != startLap + 1 || !wasOn) ok = false;
    /* 3. shortcut in reverse must not count as progress */
    int segBefore = k->segCount;
    for (int s = 20; s > T.scB - n; s -= 2) Teleport(idx, TrackPoint(&T, s, 0));
    for (int i = T.scN - 1; i >= 0; i--) Teleport(idx, T.sc[i].pos);
    for (int s = T.scA; s < T.scA + 10; s += 2) Teleport(idx, TrackPoint(&T, s, 0));
    ALog("CHECKPOINT %s: drove the lap backwards through the shortcut -> lap %d, progress change %d samples (must be negative)", T.def->name, k->lap, k->segCount - segBefore);
    if (k->lap != startLap + 1 || k->segCount >= segBefore) ok = false;
    ALog("RESULT checkpoint %s: %s", T.def->name, ok ? "PASS" : "FAIL");
    if (!ok) AT.failures++;
}

/* returns number of simulation steps to run this frame */
static int AutotestFrame(void)
{
    AT.frames++;
    switch (AT.stage) {
    case 10: { /* --preview: quick look at every track */
        char nm[64];
        if (AT.frames == 1) AutotestBeginRace(AT.race);
        if (G.screen == SCR_RACE && R.phase == RACE_RUNNING && R.time > 9.0f && !AT.shotB) { snprintf(nm, sizeof nm, "pv_track%d_race.png", AT.race + 1); Shot(nm); AT.shotB = true; AT.frames = 1000; }
        if (AT.frames == 1003) {
            Kart *k = &R.karts[R.humanKart[0]];
            int i = T.scN/3;
            k->pos = T.sc[i].pos; k->heading = k->moveYaw = atan2f(T.sc[0].fwd.x, T.sc[0].fwd.z);
            k->onShortcut = true; k->scIdx = i; k->speed = 20;
        }
        if (AT.frames == 1040) { snprintf(nm, sizeof nm, "pv_track%d_shortcut.png", AT.race + 1); Shot(nm); }
        if (AT.frames == 1045) { AT.race++; AT.frames = 0; AT.shotB = false; if (AT.race >= NUM_TRACKS) AT.stage = 99; }
        return AT.frames > 1000 ? 1 : G.autoSpeed;
    }
    case 12: { /* --stadium: scripted tour of Mudslide Megadome for the v7 screenshots */
        static int step = 0, hold = 0;
        static bool doneTour = false;
        const char *names[8] = { "stadium_01_start_banner.png", "stadium_02_moguls.png", "stadium_03_overpass_jump.png", "stadium_04_jumbotron.png",
                                 "stadium_05_crowd_lights.png", "stadium_06_overview.png", "stadium_07_neon_sign.png", "stadium_08_bridge_side.png" };
        if (AT.frames == 1) { AutotestBeginRace(STADIUM_TRACK); step = 0; hold = 0; doneTour = false; G.autoCamOn = false; }
        if (G.screen != SCR_RACE) return 1;
        Kart *pk = &R.karts[R.humanKart[0]];
        int n = T.n;
        int kick = 0;
        for (int i = 0; i < n; i++) if (T.s[i].ramp && T.s[i].pos.y > 3) { kick = i; break; }
        Vector3 fw = { sinf(pk->heading), 0, cosf(pk->heading) }, rt = { fw.z, 0, -fw.x };
        Camera3D c = { 0 }; c.up = (Vector3){ 0, 1, 0 }; c.projection = CAMERA_PERSPECTIVE; c.fovy = 60;
        bool ready = false;
        switch (step) {
        case 0:   /* behind the grid during the countdown, looking at the TURBO TUMBLE 64 truss */
            if (R.phase == RACE_COUNTDOWN && R.countdown < 2.2f) {
                const TrackSample *a = &T.s[TrackWrap(&T, -22)], *b = &T.s[TrackWrap(&T, 6)];
                c.position = Vector3Add(a->pos, (Vector3){ 0, 5.5f, 0 }); c.target = Vector3Add(b->pos, (Vector3){ 0, 4.0f, 0 }); c.fovy = 62;
                ready = true;
            } break;
        case 1:   /* high chase over the moguls */
            if (R.phase == RACE_RUNNING && T.s[pk->seg].bump && pk->lap == 0 && T.s[TrackWrap(&T, pk->seg - 30)].bump) {
                c.position = Vector3Add(Vector3Subtract(pk->pos, Vector3Scale(fw, 13)), (Vector3){ 0, 6.5f, 0 }); c.target = Vector3Add(pk->pos, Vector3Add(Vector3Scale(fw, 8), (Vector3){ 0, 0, 0 }));
                ready = true;
            } break;
        case 2:   /* airborne off the big kicker, over the lower straight */
            if (R.phase == RACE_RUNNING && !pk->grounded && pk->seg > kick + 6 && pk->seg < kick + 40 && pk->airTime > 0.3f) {
                c.position = Vector3Add(Vector3Add(pk->pos, Vector3Add(Vector3Scale(rt, 4), Vector3Scale(fw, -13))), (Vector3){ 0, 5.0f, 0 }); c.target = Vector3Add(pk->pos, Vector3Add(Vector3Scale(fw, 10), (Vector3){ 0, -3.0f, 0 }));
                c.fovy = 55; ready = true;
            } break;
        case 3:   /* the north jumbotron from the infield */
            if (R.phase == RACE_RUNNING && R.time > 30.0f && T.numJumbo > 0) {
                Vector3 j = T.jumboC[0];
                c.position = (Vector3){ j.x + 25, 9, j.z + 85 }; c.target = (Vector3){ j.x, j.y - 6, j.z }; c.fovy = 55;
                ready = true;
            } break;
        case 4:   /* crowd, flood-lights and flashes from the track */
            if (R.phase == RACE_RUNNING && R.time > 33.0f) {
                c.position = (Vector3){ T.mapMax.x - 10, 3.0f, (T.mapMin.y + T.mapMax.y)*0.5f + 30 }; c.target = (Vector3){ T.mapMax.x + STADIUM_MARGIN + 15, 24, (T.mapMin.y + T.mapMax.y)*0.5f - 30 }; c.fovy = 65;
                ready = true;
            } break;
        case 5: { /* overview */
            if (R.phase == RACE_RUNNING && R.time > 36.0f) {
                Vector3 m = { (T.mapMin.x + T.mapMax.x)*0.5f, 0, (T.mapMin.y + T.mapMax.y)*0.5f };
                c.position = (Vector3){ m.x - 40, 150, T.mapMax.y + 150 }; c.target = (Vector3){ m.x, 0, m.z - 10 }; c.fovy = 62;
                ready = true;
            } } break;
        case 6:   /* lap 2: neon sign over the ramp approach */
            if (R.phase == RACE_RUNNING && pk->lap >= 1 && T.hasNeon) {
                int g = TrackWrap(&T, kick - 18);
                if (abs(pk->seg - (g - 14)) < 3) {
                    c.position = Vector3Add(Vector3Subtract(pk->pos, Vector3Scale(fw, 9)), (Vector3){ 0, 3.6f, 0 }); c.target = Vector3Add(T.neonC, (Vector3){ 0, -2.0f, 0 }); c.fovy = 60;
                    ready = true;
                }
            } break;
        case 7: { /* bridge / overpass from the lower straight */
            if (R.phase == RACE_RUNNING && R.time > 5.0f) {
                int bi = -1, lo = -1;
                for (int i = 0; i < n && bi < 0; i++) if (T.s[i].bridge) bi = i + 6;
                if (bi >= 0) {
                    float best = 1e9f;
                    for (int i = 0; i < n; i++) { if (T.s[i].pos.y > 1) continue; float d = Vector3Distance(T.s[i].pos, T.s[bi].pos); if (d < best && abs(i - bi) > 60) { best = d; lo = i; } }
                    const TrackSample *L = &T.s[TrackWrap(&T, lo - 14)];
                    c.position = Vector3Add(L->pos, (Vector3){ 0, 2.2f, 0 }); c.target = Vector3Add(T.s[bi].pos, (Vector3){ 0, -1.0f, 0 }); c.fovy = 62;
                    ready = true;
                }
            } } break;
        default:
            if (!doneTour) { doneTour = true; G.autoCamOn = false; ALog("STADIUM TOUR: done (%d lamps, %d jumbotrons, neon %s)", T.numLights, T.numJumbo, T.hasNeon ? "yes" : "no"); AT.stage = 99; }
            return 1;
        }
        if (ready) {
            G.autoCam = c; G.autoCamOn = true;
            if (++hold == 4) { Shot(names[step]); }
            if (hold >= 6) { hold = 0; step++; G.autoCamOn = false; }
            return step == 2 || step == 1 ? 1 : 0;     /* freeze (0 sim steps) except during the motion shots */
        }
        if (step == 7 && R.time > 5.0f) { step = 8; }
        if (R.time > 300.0f) { ALog("STADIUM TOUR: timed out at step %d", step); step = 99; }
        return (step == 1 || step == 2) ? 2 : G.autoSpeed;
    }

    case 13: { /* --tour N: start grid, landmark, hazard, shortcut shots of one v7 course */
        static int step = 0, hold = 0;
        static float stepT0 = -1;
        char nm[96];
        const char *what[5] = { "start", "landmark", "hazard", "shortcut", "action" };
        if (AT.frames == 1) { AutotestBeginRace(AT.race); step = 0; hold = 0; stepT0 = -1; G.autoCamOn = false; }
        if (G.screen != SCR_RACE) return 1;
        Kart *pk = &R.karts[R.humanKart[0]];
        Vector3 fw = { sinf(pk->heading), 0, cosf(pk->heading) }, rt = { -fw.z, 0, fw.x };
        Camera3D c = { 0 }; c.up = (Vector3){ 0, 1, 0 }; c.projection = CAMERA_PERSPECTIVE; c.fovy = 60;
        bool ready = false, gameCam = false;
        Vector3 hp; int hs;
        switch (step) {
        case 0:   /* behind the grid, start gate and banner */
            if (R.phase == RACE_COUNTDOWN && R.countdown < 2.2f) {
                const TrackSample *a = &T.s[TrackWrap(&T, -20)], *b = &T.s[TrackWrap(&T, 8)];
                c.position = Vector3Add(a->pos, (Vector3){ 0, 4.5f, 0 }); c.target = Vector3Add(b->pos, (Vector3){ 0, 3.0f, 0 }); c.fovy = 62;
                ready = true;
            } break;
        case 1:   /* landmark seen from the nearest bit of road */
            if (R.phase == RACE_RUNNING && R.time > 6.0f) {
                Vector3 L; bool have = false;
                if (T.hasLandmark) { L = T.landmark; L.y += T.landmarkH; have = true; }
                else if (HazardFocus(0, &L, &hs)) { L.y += 1.5f; have = true; }
                if (!have) { step++; break; }
                int best = 0; float bd = 1e9f;
                for (int i = 0; i < T.n; i++) { float d = Vector3Distance(T.s[i].pos, L); if (d < bd && d > 25) { bd = d; best = i; } }
                Vector3 from = T.s[best].pos, dir = Vector3Normalize(Vector3Subtract(L, from));
                c.position = Vector3Add(Vector3Subtract(from, Vector3Scale((Vector3){ dir.x, 0, dir.z }, 10)), (Vector3){ 0, 4.0f, 0 });
                c.target = L; c.fovy = 55;
                ready = true;
            } break;
        case 2:   /* a hazard doing its thing (raised mole, crab, monkey) or the steamboat */
            if (R.phase == RACE_RUNNING && R.time > 8.0f) {
                bool got = HazardFocus(1, &hp, &hs);
                if (!got && T.def->hazard == HZ_NONE) { step++; break; }
                if (!got) break;
                const TrackSample *s = &T.s[TrackWrap(&T, hs - (T.def->hazard == HZ_MONKEYS ? 5 : 7))];
                float side = T.def->hazard == HZ_MONKEYS ? ((Vector3DotProduct(Vector3Subtract(hp, s->pos), s->right) > 0) ? 2.5f : -2.5f) : -2.5f;
                c.position = Vector3Add(Vector3Add(s->pos, Vector3Scale(s->right, side)), (Vector3){ 0, T.def->hazard == HZ_MONKEYS ? 2.0f : 2.6f, 0 });
                c.target = Vector3Add(hp, (Vector3){ 0, 0.6f, 0 }); c.fovy = 52;
                ready = true;
            } break;
        case 3:   /* P1 on the secret shortcut (normal game camera) */
            if (R.phase == RACE_RUNNING && pk->onShortcut && pk->scIdx > T.scN/3) { gameCam = true; ready = true; }
            break;
        case 4:   /* jump / splash / tide action: airborne P1, else a racing shot at 60 s */
            if (stepT0 < 0) stepT0 = R.time;
            if (R.phase == RACE_RUNNING && ((!pk->grounded && pk->airTime > 0.35f) || R.time > stepT0 + 70.0f)) {
                if (!pk->grounded) { c.position = Vector3Add(Vector3Add(pk->pos, Vector3Add(Vector3Scale(rt, 5), Vector3Scale(fw, -10))), (Vector3){ 0, 3.0f, 0 }); c.target = Vector3Add(pk->pos, Vector3Scale(fw, 6)); c.fovy = 58; }
                else gameCam = true;
                ready = true;
            } break;
        default:
            ALog("TOUR %s: done (%d hazard spots, %d cows, boat %s, landmark %s)", T.def->name, T.numHazSpots, T.numCows, T.boatN ? "yes" : "no", T.hasLandmark ? "yes" : "no");
            AT.stage = 99;
            return 1;
        }
        if (ready) {
            if (!gameCam) { G.autoCam = c; G.autoCamOn = true; }
            if (++hold == 4) { snprintf(nm, sizeof nm, "track%d_%d_%s.png", AT.race + 1, step + 1, what[step]); Shot(nm); }
            if (hold >= 6) { hold = 0; step++; G.autoCamOn = false; }
            return (step == 3 || step == 4) ? 1 : 0;
        }
        if (R.time > 200.0f || R.phase == RACE_DONE) { ALog("TOUR: skipped step %d (%s)", step, what[step < 5 ? step : 4]); step++; }
        return (step >= 3) ? 2 : G.autoSpeed;
    }
    case 0: /* title */
        if (G.previewOnly) { AT.stage = 10; AT.frames = 0; AT.race = 0; return 1; }
        if (quipsOnly) { AT.stage = 6; AT.frames = 0; AT.race = 0; return 1; }
        if (stadiumTour) { AT.stage = 12; AT.frames = 0; AT.race = STADIUM_TRACK; return 1; }
        if (tourTrack > 0) { AT.stage = 13; AT.frames = 0; AT.race = tourTrack - 1; return 1; }
        if (AT.frames == 2) { RaceStart(0, true); GoToScreen(SCR_TITLE); }
        if (AT.frames == 90) Shot("01_title.png");
        if (AT.frames == 95) { G.mode = MODE_GP; G.numHumans = 1; G.charCursor[0] = 2; G.charLocked[0] = false; GoToScreen(SCR_CHAR); AT.stage = 1; AT.frames = 0; }
        return 1;
    case 1:
        if (AT.frames == 1) { int e = FindCharPrefix("Baby"); if (e >= 0) G.charCursor[0] = e; }
        if (AT.frames == 30) Shot("02_character_select.png");
        if (AT.frames == 31) { int q = FindCharPrefix("Towelhead"); if (q >= 0) G.charCursor[0] = q; }
        if (AT.frames == 60) Shot("02b_character_select.png");
        if (AT.frames == 65) { G.mode = MODE_TT; GoToScreen(SCR_TRACK); G.menuSel = 8; AT.stage = 2; AT.frames = 0; }
        return 1;
    case 2:
        if (AT.frames == 30) Shot("03_track_select.png");
        if (AT.frames == 32) { G.mode = MODE_GP; GoToScreen(SCR_TRACK); G.menuSel = 0; }
        if (AT.frames == 40) Shot("03b_cup_select.png");
        if (AT.frames == 45) { G.mode = MODE_GP; GoToScreen(SCR_OPTIONS); AT.stage = 3; AT.frames = 0; }
        return 1;
    case 3:
        if (AT.frames == 20) Shot("04_options.png");
        if (AT.frames == 25) { AT.stage = 4; AT.race = G.autoOnly > 0 ? G.autoOnly - 1 : 0; AT.frames = 0; AutotestBeginRace(AT.race); }
        return 1;
    case 4: { /* races */
        AT.raceFrames++;
        char nm[64];
        if (G.screen == SCR_RACE) {
            if (R.phase == RACE_INTRO && R.phaseTime > 1.0f && !AT.shotCountdown) { snprintf(nm, sizeof nm, "race%d_%d_intro.png", AT.race + 1, 0); Shot(nm); AT.shotCountdown = true; }
            if (R.phase == RACE_COUNTDOWN && R.countdown < 1.5f && !AT.shotA) { snprintf(nm, sizeof nm, "race%d_%d_countdown.png", AT.race + 1, 1); Shot(nm); AT.shotA = true; }
            if (R.phase == RACE_RUNNING && R.time > 12.0f && !AT.shotB) { snprintf(nm, sizeof nm, "race%d_%d_racing.png", AT.race + 1, 2); Shot(nm); AT.shotB = true; }
            if (R.phase == RACE_RUNNING && R.time > 22.0f && AT.frontStage == 0) { G.autoFrontCam = 1; AT.frontStage = 1; AT.frontFrames = 0; }
            else if (AT.frontStage == 1 && ++AT.frontFrames == 3) { snprintf(nm, sizeof nm, "race%d_closeup.png", AT.race + 1); Shot(nm); AT.frontStage = 2; AT.frontFrames = 0; }
            else if (AT.frontStage == 2 && ++AT.frontFrames == 3) { G.autoFrontCam = 2; AT.frontStage = 3; AT.frontFrames = 0; }
            else if (AT.frontStage == 3 && ++AT.frontFrames == 3) { snprintf(nm, sizeof nm, "race%d_closeup_rear.png", AT.race + 1); Shot(nm); AT.frontStage = 4; AT.frontFrames = 0; }
            else if (AT.frontStage == 4 && ++AT.frontFrames == 3) { G.autoFrontCam = 0; AT.frontStage = 5; }
            if (R.phase == RACE_RUNNING && R.time > 50.0f && !AT.shotC) { snprintf(nm, sizeof nm, "race%d_%d_racing.png", AT.race + 1, 3); Shot(nm); AT.shotC = true; }
            {
                Kart *pk = &R.karts[R.humanKart[0]];
                if (pk->onShortcut && pk->scIdx > T.scN/3 && !AT.shotSc) { snprintf(nm, sizeof nm, "race%d_shortcut.png", AT.race + 1); Shot(nm); AT.shotSc = true; }
                if (!pk->grounded && pk->airTime > 0.12f && T.s[pk->seg].bump && !AT.shotBump) { snprintf(nm, sizeof nm, "race%d_bumps_airborne.png", AT.race + 1); Shot(nm); AT.shotBump = true; }
                if (pk->driftState == 2 && pk->grounded && pk->sparkLevel == 1 && pk->driftCharge > 0.95f && !AT.shotDrift && R.time > 4.0f) { snprintf(nm, sizeof nm, "race%d_drift_blue.png", AT.race + 1); Shot(nm); AT.shotDrift = true; }
                if (pk->driftState == 2 && pk->grounded && pk->sparkLevel == 2 && !AT.shotDrift2 && R.time > 4.0f) { snprintf(nm, sizeof nm, "race%d_drift_orange.png", AT.race + 1); Shot(nm); AT.shotDrift2 = true; }
                if (pk->roulette > 0 && pk->rouletteDur > 0 && pk->roulette < pk->rouletteDur*0.6f && pk->roulette > pk->rouletteDur*0.3f && !AT.shotRoul) { snprintf(nm, sizeof nm, "race%d_item_roulette.png", AT.race + 1); Shot(nm); AT.shotRoul = true; }
            }
            if (R.time > 420.0f) { ALog("TIMEOUT: race did not finish in 420s of sim time"); RaceEnd(); GoToScreen(SCR_RESULTS); }
            /* real-time perf sample on the first race: run 1 step/frame for a while */
            if ((AT.race == 0 || T.def->scenery == SCENERY_STADIUM || T.def->followTerrain) && R.phase == RACE_RUNNING && R.time > 20.0f && AT.perfDone != AT.race + 1) {
                if (AT.perfFrames == 0) AT.perfStart = GetTime();
                AT.perfFrames++;
                if (AT.perfFrames == 600) {
                    double t = GetTime() - AT.perfStart;
                    ALog("PERF %s: 600 frames at 1 sim step/frame took %.2fs => %.1f fps average (uncapped, software GL under Xvfb)", T.def->name, t, 600.0/t);
                    ALog("PERF %s: worst frame %.1f ms", T.def->name, AT.worstFrame*1000.0f);
                    AT.perfDone = AT.race + 1; AT.perfFrames = 0; AT.worstFrame = 0;
                }
                return 1;
            }
        } else if (G.screen == SCR_RESULTS) {
            AT.resultsFrames++;
            if (AT.resultsFrames == 1) AutotestReportRace();
            if (AT.resultsFrames == 40) { snprintf(nm, sizeof nm, "race%d_%d_results.png", AT.race + 1, 4); Shot(nm); }
            if (AT.resultsFrames == 45) {
                if (G.autoOnly > 0 && G.autoOnly != NUM_TRACKS) { AT.stage = 99; }
                else if (AT.race == 0 || AT.race == NUM_TRACKS - 1) { GoToScreen(SCR_STANDINGS); }
                else { AT.race++; AutotestBeginRace(AT.race); }
            }
            return 1;
        } else if (G.screen == SCR_STANDINGS) {
            AT.resultsFrames++;
            if (AT.resultsFrames == 80) Shot(AT.race == 0 ? "race1_5_standings.png" : "final_standings.png");
            if (AT.resultsFrames == 85) {
                if (AT.race == NUM_TRACKS - 1) {
                    int best = 0;
                    for (int i = 1; i < R.numKarts; i++) if (G.gpPoints[i] > G.gpPoints[best]) best = i;
                    int myPts = G.gpPoints[R.humanKart[0]], rank = 1;
                    for (int i = 0; i < R.numKarts; i++) if (G.gpPoints[i] > myPts) rank++;
                    ALog("CUP: final standings - champion %s with %d pts; P1 %d pts (rank %d)", CHARACTERS[R.karts[best].charId].name, G.gpPoints[best], myPts, rank);
                    GoToScreen(SCR_TROPHY);
                } else { AT.race++; AutotestBeginRace(AT.race); }
            }
            return 1;
        } else if (G.screen == SCR_TROPHY) {
            AT.resultsFrames++;
            if (AT.resultsFrames == 85 + 200) Shot("cup_trophy_ceremony.png");
            if (AT.resultsFrames == 85 + 205) { ALog("RESULT cup ceremony: PASS (trophy screen rendered)"); AT.stage = 7; AT.frames = 0; }
            return 1;
        }
        return G.autoSpeed;
    }
    case 7: { /* time trial with best-lap ghost */
        if (AT.frames == 1) {
            G.mode = MODE_TT; G.numHumans = 1; G.humanChar[0] = 0; G.ghostValid = false;
            G.trackIndex = G.autoOnly > 0 ? G.autoOnly - 1 : 0;
            if (G.autoOnly > 0) CheckpointTest(G.trackIndex);
            RaceStart(G.trackIndex, false); GoToScreen(SCR_RACE);
            AT.shotGhost = false; AT.ttGhostSeen = false; AT.resultsFrames = 0;
            ALog("---- Time Trial on %s (ghost test) ----", T.def->name);
        }
        if (G.screen == SCR_RACE) {
            Kart *pk = &R.karts[0];
            Vector3 gp; float gy;
            if (G.ghostValid && GhostPose(R.time - pk->lapStartTime, &gp, &gy)) {
                float d = Vector3Distance(gp, pk->pos);
                Vector3 fw = { sinf(pk->heading), 0, cosf(pk->heading) };
                float ahead = (gp.x - pk->pos.x)*fw.x + (gp.z - pk->pos.z)*fw.z;
                if (d > 1.5f) AT.ttGhostSeen = true;
                if (!AT.shotGhost && pk->lap == 2 && R.bannerTimer[0] <= 0 && ahead > 4.0f && ahead < 16.0f && d < 18.0f) { Shot("tt_ghost.png"); AT.shotGhost = true; ALog("GHOST: visible %.1f m ahead of the player on lap %d", ahead, pk->lap + 1); }
            }
            if (R.time > 400.0f) { ALog("TIMEOUT in time trial"); RaceEnd(); GoToScreen(SCR_RESULTS); }
            return G.autoSpeed;
        }
        if (G.screen == SCR_RESULTS) {
            AT.resultsFrames++;
            if (AT.resultsFrames == 40) Shot("tt_results.png");
            if (AT.resultsFrames == 45) {
                Kart *pk = &R.karts[0];
                bool ok = pk->lap == NUM_LAPS && G.ghostValid && G.ghost.n > 100 && AT.ttGhostSeen;
                ALog("TT: laps=%d time=%s bestLap=%s ghost=%s (%d samples, lap %s), ghost replayed=%s", pk->lap, FormatTime(pk->finishTime), FormatTime(pk->bestLap),
                     G.ghostValid ? "yes" : "no", G.ghost.n, FormatTime(G.ghost.lapTime), AT.ttGhostSeen ? "yes" : "no");
                ALog("RESULT time trial ghost: %s", ok ? "PASS" : "FAIL");
                if (!ok) AT.failures++;
                AT.stage = G.autoOnly > 0 ? 99 : 5; AT.frames = 0;
            }
            return 1;
        }
        return 1;
    }
    case 5: /* 2-player split screen */
        if (AT.frames == 1) {
            for (int tk = 0; tk < NUM_TRACKS; tk++) CheckpointTest(tk);
            G.mode = MODE_VS; G.numHumans = 2; G.humanChar[0] = 2; G.humanChar[1] = 5; G.trackIndex = 2;
            RaceStart(2, false); GoToScreen(SCR_RACE);
            ALog("---- VS split-screen test on %s ----", T.def->name);
        }
        if (G.screen == SCR_RACE && R.time > 25.0f && AT.frames < 100000) {
            Shot("vs_splitscreen.png");
            bool moving = R.karts[R.humanKart[0]].progress > 50 && R.karts[R.humanKart[1]].progress > 50;
            ALog("VS: P1 progress %.0f, P2 progress %.0f samples after 25s => %s", R.karts[R.humanKart[0]].progress, R.karts[R.humanKart[1]].progress, moving ? "PASS" : "FAIL");
            if (!moving) AT.failures++;
            AT.frames = 100000;
        }
        if (AT.frames == 100003) { G.paused = true; G.pauseSel = 0; }
        if (AT.frames == 100010) Shot("vs_pause_menu.png");
        if (AT.frames == 100015) { AT.stage = 6; AT.race = 0; AT.frames = 0; }
        return G.paused ? 0 : G.autoSpeed;
    case 6: { /* forced wins: each photo racer wins a race and the cup, to show the victory quips */
        int who = FindCharPrefix(AT.race == 0 ? "Baby" : "Towelhead");
        const char *slug = AT.race == 0 ? "eabha" : "qanna";
        char nm[64];
        if (who < 0) { AT.race++; AT.frames = 0; if (AT.race >= 2) AT.stage = 99; return 1; }
        if (AT.frames == 1) {
            gForcePlayer = who;                          /* she drives the new stadium track */
            AutotestBeginRace(STADIUM_TRACK);
            gForcePlayer = -1;
            ALog("---- Forced win: %s ----", CHARACTERS[who].name);
        }
        if (AT.frames == 200) {   /* ~3 s of racing, then everyone "finishes" with her first */
            for (int i = 0; i < R.numKarts; i++) { Kart *k = &R.karts[i]; k->finished = true; k->lap = NUM_LAPS; k->finishTime = (k->charId == who ? 100.0f : 103.0f + i); }
            memset(G.gpPoints, 0, sizeof(G.gpPoints));
            RaceEnd(); GoToScreen(SCR_RESULTS); AT.resultsFrames = 0;
        }
        if (G.screen == SCR_RESULTS) {
            AT.resultsFrames++;
            if (AT.resultsFrames == 30) { snprintf(nm, sizeof nm, "win_%s_results_pop.png", slug); Shot(nm); }
            if (AT.resultsFrames == 80) { snprintf(nm, sizeof nm, "win_%s_results.png", slug); Shot(nm); }
            if (AT.resultsFrames == 82) {
                bool ok = gMoodChar == who && R.karts[R.humanKart[0]].place == 1;
                ALog("RESULT forced win %s (race results quip \"%s\"): %s", CHARACTERS[who].name, CHARACTERS[who].quip ? CHARACTERS[who].quip : "-", ok ? "PASS" : "FAIL");
                if (!ok) AT.failures++;
                for (int i = 0; i < R.numKarts; i++) G.gpPoints[i] = R.karts[i].charId == who ? 54 : 40 - i*3;
                GoToScreen(SCR_TROPHY); AT.resultsFrames = 0;
            }
            return 1;
        }
        if (G.screen == SCR_TROPHY) {
            AT.resultsFrames++;
            if (AT.resultsFrames == 150) { snprintf(nm, sizeof nm, "win_%s_ceremony.png", slug); Shot(nm); }
            if (AT.resultsFrames == 152) {
                bool ok = gMoodChar == who;
                ALog("RESULT forced win %s (cup ceremony quip): %s", CHARACTERS[who].name, ok ? "PASS" : "FAIL");
                if (!ok) AT.failures++;
                AT.race++; AT.frames = 0;
                if (AT.race >= 2) AT.stage = 99;
            }
            return 1;
        }
        return G.autoSpeed;
    }
    default:
        ALog("==== SUMMARY: %s (%d failure%s). Average loop fps during races: %.0f ====", AT.failures ? "FAIL" : "PASS",
             AT.failures, AT.failures == 1 ? "" : "s", AT.fpsCount ? AT.fpsSum/AT.fpsCount : 0.0);
        G.quit = true;
        return 0;
    }
}

/* --gallery: close-up of every racer (both 3/4 front and rear) for model review */
static bool gallery = false;
static bool padCheck = false;
static void Gallery(void)
{
    RenderTexture2D rt = LoadRenderTexture(1280, 720);
    for (int pass = 0; pass < 2; pass++) {
        BeginTextureMode(rt);
        ClearBackground((Color){ 120, 170, 230, 255 });
        int cols = 5;
        for (int i = 0; i < NUM_CHARACTERS; i++) {
            int cx = i % cols, cy = i/cols;
            int rowsN = (NUM_CHARACTERS + cols - 1)/cols;
            int cw = 1280/cols, chh = 720/(rowsN < 2 ? 2 : rowsN);
            rlViewport(cx*cw, 720 - (cy + 1)*chh, cw, chh);
            Camera3D cam = { 0 };
            float a = pass == 0 ? 0.65f : 2.6f;
            cam.position = (Vector3){ sinf(a)*4.2f, 2.2f, cosf(a)*4.2f };
            cam.target = (Vector3){ 0, 0.85f, 0 }; cam.up = (Vector3){ 0, 1, 0 }; cam.fovy = 45; cam.projection = CAMERA_PERSPECTIVE;
            rlMatrixMode(RL_PROJECTION); rlPushMatrix(); rlLoadIdentity();
            double top = 0.1*tan(45*0.5*DEG2RAD), right = top*(double)cw/chh;
            rlFrustum(-right, right, -top, top, 0.1, 100.0);
            rlMatrixMode(RL_MODELVIEW); rlLoadIdentity();
            rlMultMatrixf(MatrixToFloat(MatrixLookAt(cam.position, cam.target, cam.up)));
            rlEnableDepthTest(); rlDisableBackfaceCulling();
            Kart k; memset(&k, 0, sizeof k); k.scale = 1; k.charId = i; k.steer = 0.3f; k.wheelRot = 0.3f;
            DrawCharacterKart(i, &k, 1.0f);
            rlDrawRenderBatchActive();
            rlMatrixMode(RL_PROJECTION); rlPopMatrix(); rlMatrixMode(RL_MODELVIEW); rlLoadIdentity();
        }
        rlViewport(0, 0, 1280, 720);
        EndTextureMode();
        Image img = LoadImageFromTexture(rt.texture);
        ImageFlipVertical(&img);
        ExportImage(img, TextFormat("%s/%sgallery_%s.png", G.shotDir, G.shotPrefix, pass == 0 ? "front" : "rear"));
        UnloadImage(img);
    }
    /* 3D close-ups of the built-in-code photo racers: front, side, rear chase (decals), face */
    for (int i = 0; i < NUM_CHARACTERS; i++) {
        bool photo = CHARACTERS[i].spriteAngles > 1 && G.charWin[i].id;      /* multi-angle photo / spec racers */
        if (!CHARACTERS[i].model3d && !photo) continue;
        char slug[64]; int sl = 0;
        for (const unsigned char *c = (const unsigned char *)CHARACTERS[i].name; *c && sl < 60; c++)
            if (isalnum(*c)) slug[sl++] = (char)tolower(*c);
            else if (*c == 0xC3 && c[1] >= 0x80 && c[1] <= 0xBF) { slug[sl++] = "aaaaaaaceeeeiiiidnooooo_ouuuuyps"[(c[1] & 0x1F)]; c++; }  /* Latin-1 accents */
            else if (*c == ' ' && sl && slug[sl - 1] != '_') slug[sl++] = '_';
        slug[sl] = 0;
        const char *views[8] = { "front", "side", "rear_chase", "face", "win_pose", "back", "side_left", "front_left" };
        int nv = photo ? 8 : 5;
        for (int v = 0; v < nv; v++) {
            BeginTextureMode(rt);
            ClearBackground((Color){ 34, 38, 62, 255 });
            DrawRectangleGradientV(0, 0, 1280, 720, (Color){ 70, 110, 170, 255 }, (Color){ 24, 26, 44, 255 });
            Camera3D cam = { 0 };
            float hy = CHARACTERS[i].model3d == 1 ? 1.5f : CHARACTERS[i].model3d == 2 ? 1.6f
                     : 0.47f + CHARACTERS[i].spriteSeat + CHARACTERS[i].spriteSize*0.78f;
            switch (v) {
            case 0: cam.position = (Vector3){ 1.5f, 1.9f, 3.6f }; cam.target = (Vector3){ 0, 1.0f, 0 }; cam.fovy = 42; break;
            case 1: cam.position = (Vector3){ 4.2f, 1.6f, 0.2f }; cam.target = (Vector3){ 0, 1.0f, -0.1f }; cam.fovy = 42; break;
            case 2: cam.position = (Vector3){ 0.5f, 2.3f, -4.6f }; cam.target = (Vector3){ 0, 1.1f, 0 }; cam.fovy = 42; break;
            case 3: cam.position = (Vector3){ 0.45f, hy + 0.15f, 2.2f }; cam.target = (Vector3){ 0, hy - 0.02f, 0 }; cam.fovy = 26; break;
            case 5: cam.position = (Vector3){ 0, 1.6f, -4.2f }; cam.target = (Vector3){ 0, 1.0f, 0 }; cam.fovy = 42; break;
            case 6: cam.position = (Vector3){ -4.2f, 1.6f, 0.2f }; cam.target = (Vector3){ 0, 1.0f, -0.1f }; cam.fovy = 42; break;
            case 7: cam.position = (Vector3){ -2.9f, 1.7f, 2.9f }; cam.target = (Vector3){ 0, 1.0f, 0 }; cam.fovy = 42; break;
            default: cam.position = (Vector3){ 1.3f, 2.1f, 3.8f }; cam.target = (Vector3){ 0, 1.15f, 0 }; cam.fovy = 40; break;
            }
            cam.up = (Vector3){ 0, 1, 0 }; cam.projection = CAMERA_PERSPECTIVE;
            int keep = gMoodChar; if (v == 4) gMoodChar = i;
            BeginMode3D(cam);
            rlDisableBackfaceCulling();
            Kart k; memset(&k, 0, sizeof k); k.scale = 1; k.charId = i; k.steer = v == 4 ? 0 : 0.15f; k.wheelRot = 0.3f; k.speed = v == 2 ? 18.0f : 6.0f; k.grounded = true;
            DrawCharacterKart(i, &k, 1.3f);
            rlDrawRenderBatchActive();
            rlEnableBackfaceCulling();
            EndMode3D();
            gMoodChar = keep;
            EndTextureMode();
            Image img = LoadImageFromTexture(rt.texture);
            ImageFlipVertical(&img);
            ExportImage(img, TextFormat("%s/%schar_%s_%s.png", G.shotDir, G.shotPrefix, slug, views[v]));
            UnloadImage(img);
        }
    }
    UnloadRenderTexture(rt);
}

static int autoRetro = 0;
int main(int argc, char **argv)
{
    memset(&G, 0, sizeof(G));
    G.autoSpeed = 4;
    strcpy(G.shotDir, "screenshots");
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--autotest")) G.autotest = true;
        else if (!strcmp(argv[i], "--enhanced")) G.autoVisual = 1;
        else if (!strcmp(argv[i], "--retro")) autoRetro = 1;
        else if (!strcmp(argv[i], "--quips")) { G.autotest = true; quipsOnly = true; }
        else if (!strcmp(argv[i], "--stadium")) { G.autotest = true; stadiumTour = true; }
        else if (!strcmp(argv[i], "--tour") && i + 1 < argc) { G.autotest = true; tourTrack = atoi(argv[++i]); }
        else if (!strcmp(argv[i], "--only") && i + 1 < argc) G.autoOnly = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--preview")) { G.autotest = true; G.previewOnly = true; }
        else if (!strcmp(argv[i], "--padcheck")) { G.autotest = true; padCheck = true; }
        else if (!strcmp(argv[i], "--gallery")) { G.autotest = true; gallery = true; }
        else if (!strcmp(argv[i], "--speed") && i + 1 < argc) G.autoSpeed = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--prefix") && i + 1 < argc) { strncpy(G.shotPrefix, argv[++i], sizeof(G.shotPrefix) - 1); }
        else if (!strcmp(argv[i], "--shots") && i + 1 < argc) { strncpy(G.shotDir, argv[++i], sizeof(G.shotDir) - 1); }
    }
    if (G.autoSpeed < 1) G.autoSpeed = 1;
    srand((unsigned)time(NULL));
    if (G.autotest) srand(12345);

    unsigned int flags = FLAG_WINDOW_RESIZABLE | FLAG_MSAA_4X_HINT;
    if (!G.autotest) flags |= FLAG_VSYNC_HINT;
    SetConfigFlags(flags);
    SetTraceLogLevel(G.autotest ? LOG_INFO : LOG_WARNING);
    InitWindow(1280, 720, GAME_TITLE);
    SetWindowMinSize(640, 360);
    SetExitKey(KEY_NULL);
    ChangeDirectory(GetApplicationDirectory());
    if (!DirectoryExists("assets") && DirectoryExists("../assets")) ChangeDirectory("..");   /* prebuilt\TurboTumble64.exe run in place */
    SetTargetFPS(G.autotest ? 0 : 60);
    InputDefaultBinds(0); InputDefaultBinds(1);
    LoadSettings();
    if (G.autotest) { G.settings.visualMode = G.autoVisual; G.settings.pixelMode = autoRetro; G.settings.padMode = 0; }
    InputInit2();
    if (padCheck) { int f = InputSelfTest(); CloseWindow(); return f ? 1 : 0; }

    if (G.autotest) {
        MakeDirectory(G.shotDir);
        AT.log = fopen(TextFormat("%s/autotest_log.txt", G.shotDir), "w");
        ALog("Turbo Tumble 64 autotest  (raylib %s, GL renderer active)", RAYLIB_VERSION);
    }

    RenderInit();
    CharactersInit();
    AudioInit();
    if (gallery) { MakeDirectory(G.shotDir); Gallery(); CloseWindow(); return 0; }
    RaceStart(0, true);
    GoToScreen(SCR_TITLE);

    while (!WindowShouldClose() && !G.quit) {
        if (IsWindowResized()) RenderResize();
        if (IsKeyPressed(KEY_F11) || ((IsKeyDown(KEY_LEFT_ALT) || IsKeyDown(KEY_RIGHT_ALT)) && IsKeyPressed(KEY_ENTER))) { ToggleBorderlessWindowed(); RenderResize(); }
        if (IsKeyPressed(KEY_F2)) { G.settings.visualMode = 1 - G.settings.visualMode; RenderApplyTextureFilters(); RenderResize(); if (G.settings.visualMode == 0) CharactersEnsureSprites(); if (T.loaded) { T.loaded = true; TrackBuild(&T, T.index); } SaveSettings(); }

        float frameDt = GetFrameTime();
        if (frameDt > AT.worstFrame && G.autotest && AT.perfFrames > 0 && !AT.perfDone) AT.worstFrame = frameDt;
        int steps; float sub;
        if (G.autotest) {
            steps = AutotestFrame();
            sub = SIM_DT;
        } else {
            float dt = frameDt > 0.05f ? 0.05f : frameDt;
            steps = (int)ceilf(dt/SIM_DT - 0.01f);
            if (steps < 1) steps = 1;
            sub = dt/steps;
        }
        InputUpdate(frameDt);
        if (!G.autotest) MenusUpdate(frameDt);
        else {
            G.screenTime += steps*sub;
            /* the autotest still uses the real end-of-race flow */
            int unfin = 0; for (int q = 0; q < R.numKarts; q++) if (!R.karts[q].finished) unfin++;
            if (G.screen == SCR_RACE && R.phase == RACE_DONE && R.doneTimer > 4.5f && (unfin <= R.numKarts - 5 || R.doneTimer > 12.0f + T.length/120.0f)) { RaceEnd(); GoToScreen(SCR_RESULTS); }   /* longer grace on long laps */
        }
        if (G.quit) break;
        bool simulate = !(G.screen == SCR_RACE && G.paused);
        if (simulate) for (int s = 0; s < steps; s++) { RaceUpdate(sub); G.time += sub; }
        AudioUpdate();

        BeginDrawing();
        MenusDraw();
        InputDrawToast();
        if (G.settings.showFps) DrawFPS(10, 10);
        if (pendingShot) {
            rlDrawRenderBatchActive();
            Image img = LoadImageFromScreen();
            ExportImage(img, pendingShotName);
            UnloadImage(img);
            if (G.autotest) ALog("screenshot: %s", pendingShotName);
            pendingShot = false;
        }
        EndDrawing();
    }

    int code = (G.autotest && AT.failures) ? 1 : 0;
    if (AT.log) fclose(AT.log);
    TrackUnload(&T);
    AudioShutdown();
    CloseWindow();
    return code;
}

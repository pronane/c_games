// sim.c - hashes, fixed-step accumulator, record / replay and the headless --sim-test.
// Nothing in here opens a window: --sim-test and --replay run on a server or in CI.
#include "sim.h"
#include <inttypes.h>

// ------------------------------------------------------------------------------ hash --
typedef struct { uint64_t h; } Fnv;
static void HBytes(Fnv *f, const void *p, size_t n) {
    const unsigned char *b = (const unsigned char *)p;
    for (size_t i = 0; i < n; i++) { f->h ^= b[i]; f->h *= 0x100000001B3ull; }
}
static void HU32(Fnv *f, uint32_t v) { unsigned char b[4] = { v, v >> 8, v >> 16, v >> 24 }; HBytes(f, b, 4); }
static void HI(Fnv *f, int v)        { HU32(f, (uint32_t)v); }
static void HB(Fnv *f, bool v)       { HU32(f, v ? 1u : 0u); }
static void HF(Fnv *f, float v)      { uint32_t u; memcpy(&u, &v, 4); HU32(f, u); }   // exact bits
static void HV(Fnv *f, Vector2 v)    { HF(f, v.x); HF(f, v.y); }
static void HR(Fnv *f, Rectangle r)  { HF(f, r.x); HF(f, r.y); HF(f, r.width); HF(f, r.height); }
static Fnv FnvNew(void) { Fnv f = { 0xCBF29CE484222325ull }; return f; }

static void HashPlayer(Fnv *f, const Player *p) {
    HV(f, p->position); HV(f, p->velocity);
    HB(f, p->onGround); HI(f, p->facing);
    HI(f, p->state); HI(f, p->prevState); HI(f, p->currentFrame);
    HF(f, p->frameTimer); HF(f, p->stateTimer);
    HI(f, p->health); HB(f, p->invincible); HF(f, p->invincibleTimer);
    HB(f, p->attackActive); HR(f, p->hitbox); HR(f, p->hurtbox);
    HI(f, p->characterIndex); HI(f, p->projectileKind); HB(f, p->projectileFired);
    HF(f, p->opponentX);
    HU32(f, Input_FromPlayer(p));
}

uint64_t Sim_Hash(const Game *g) {
    Fnv f = FnvNew();
    HU32(&f, g->simTick);
    HI(&f, g->screen); HI(&f, g->mode);
    HB(&f, g->gameOver); HI(&f, g->winner);
    HF(&f, g->roundTimer); HF(&f, g->prefightTimer);
    HI(&f, g->cpuAttackCooldown); HU32(&f, g->rng.s);
    HashPlayer(&f, &g->player1);
    HashPlayer(&f, &g->player2);
    for (int i = 0; i < MAX_PROJECTILES; i++) {
        const Projectile *pr = &g->projectiles[i];
        HB(&f, pr->active);
        if (!pr->active) continue;        // dead slots may hold stale values that no longer matter
        HI(&f, pr->kind); HI(&f, pr->variant); HV(&f, pr->origin); HI(&f, pr->owner);
        HV(&f, pr->pos); HF(&f, pr->vx); HF(&f, pr->spin); HF(&f, pr->age);
    }
    return f.h;
}

uint64_t Sim_PlayerConfigHash(const Player *p) {
    Fnv f = FnvNew();
    HI(&f, p->characterIndex);
    HI(&f, p->projectileKind);
    for (int i = 0; i < STATE_COUNT; i++) {
        HI(&f, p->sheets[i].frameCount);
        HF(&f, p->sheets[i].frameTime);
        HI(&f, p->sheets[i].loopFrom);
    }
    return f.h;
}

static uint64_t RulesHash(void) {
    Fnv f = FnvNew();
    const float fl[] = { SIM_DT, GROUND_Y, PLAYER_WIDTH, PLAYER_HEIGHT, ANIM_SPEED_IDLE, ANIM_SPEED_WALK,
        ANIM_SPEED_ATTACK, ANIM_SPEED_SPECIAL, ANIM_SPEED_JUMP, ANIM_SPEED_HIT, ANIM_SPEED_OTHER,
        MOVE_SPEED, JUMP_FORCE, GRAVITY, MAX_FALL_SPEED, MOVE_TIME_PUNCH, MOVE_TIME_KICK,
        MOVE_TIME_SPECIAL, MOVE_TIME_THROW, MOVE_TIME_JUMP_ATTACK, MOVE_TIME_HIT, ACTIVE_FROM,
        ACTIVE_TO, PROJ_LAUNCH_AT, PROJ_SPEED_HIGH, PROJ_SPEED_LOW, PROJ_BOX };
    for (size_t i = 0; i < sizeof(fl) / sizeof(fl[0]); i++) HF(&f, fl[i]);
    const int in[] = { SCREEN_WIDTH, SCREEN_HEIGHT, MAX_HEALTH, MELEE_DAMAGE, PROJ_DAMAGE, PROJ_CHIP,
        MAX_PROJECTILES, STATE_COUNT, MAX_CHARACTERS, SIM_VERSION };
    for (size_t i = 0; i < sizeof(in) / sizeof(in[0]); i++) HI(&f, in[i]);
    return f.h;
}

uint64_t Sim_ConfigHash(const Game *g) {
    Fnv f = FnvNew();
    uint64_t a = RulesHash(), b = Sim_PlayerConfigHash(&g->player1), c = Sim_PlayerConfigHash(&g->player2);
    HBytes(&f, &a, 8); HBytes(&f, &b, 8); HBytes(&f, &c, 8);
    return f.h;
}

// ----------------------------------------------------------------------- fixed step --
int Sim_StepsForFrame(double *accum, double frameDt) {
    // Frame times within 1.5 ms of 1/60 count as exactly one tick, so a 60 Hz display runs one
    // tick per frame (as the game always did); a stall runs at most SIM_MAX_STEPS_PER_FRAME.
    if (fabs(frameDt - SIM_DT_WALL) < 0.0015) frameDt = SIM_DT_WALL;
    if (frameDt > 0.25 || frameDt < 0.0) frameDt = SIM_DT_WALL;     // window drag / load stall
    *accum += frameDt;
    int steps = 0;
    while (*accum + 1e-9 >= SIM_DT_WALL && steps < SIM_MAX_STEPS_PER_FRAME) { *accum -= SIM_DT_WALL; steps++; }
    if (*accum >= SIM_DT_WALL) *accum = 0.0;                         // drop what can't be caught up
    if (*accum < 0.0) *accum = 0.0;
    return steps;
}

// ------------------------------------------------------------------- record / replay --
void Rec_Init(SimRecorder *r, const char *path) {
    memset(r, 0, sizeof(*r));
    snprintf(r->path, sizeof(r->path), "%s", path);
}

void Rec_FightStart(SimRecorder *r, const Game *g) {
    if (!r->path[0]) return;
    if (r->f) Rec_FightEnd(r, g);
    r->fights++;
    char name[440];
    if (r->fights == 1) snprintf(name, sizeof(name), "%s", r->path);
    else snprintf(name, sizeof(name), "%s.%d", r->path, r->fights);
    r->f = fopen(name, "w");
    if (!r->f) { TraceLog(LOG_WARNING, "REPLAY: cannot write %s", name); return; }
    r->active = true;
    fprintf(r->f, "EFREC 2 sim %d\n", SIM_VERSION);
    fprintf(r->f, "seed %u mode %d p1 %d p2 %d hp1 %d hp2 %d config %016" PRIx64 "\n",
            (unsigned)g->fightSeed, (int)g->mode, g->player1.characterIndex, g->player2.characterIndex,
            g->player1.health, g->player2.health, Sim_ConfigHash(g));
    fprintf(r->f, "h %u %016" PRIx64 "\n", (unsigned)g->simTick, Sim_Hash(g));
    TraceLog(LOG_INFO, "REPLAY: recording fight to %s", name);
}

void Rec_Tick(SimRecorder *r, const Game *g, const InputBits in[2]) {
    if (!r->active || !r->f) return;
    fprintf(r->f, "t %u %x %x\n", (unsigned)g->simTick, in[0], in[1]);
    if (g->simTick % SIM_HASH_EVERY == 0) fprintf(r->f, "h %u %016" PRIx64 "\n", (unsigned)g->simTick, Sim_Hash(g));
}

void Rec_FightEnd(SimRecorder *r, const Game *g) {
    if (!r->f) return;
    fprintf(r->f, "end %u %016" PRIx64 "\n", (unsigned)g->simTick, Sim_Hash(g));
    fclose(r->f);
    r->f = NULL;
    r->active = false;
}

// headless fight set-up (sprite sizes only)
static void SetupHeadless(Game *g, int mode, int c1, int c2, uint32_t seed) {
    Game_InitCore(g);
    g->mode = (SelectMode)mode;
    g->selectP1 = c1;
    g->selectP2 = c2;
    Game_BeginFightSim(g, seed, false);
}

int Sim_Replay(const char *path, bool verbose) {
    FILE *f = fopen(path, "r");
    if (!f) { printf("replay: cannot open %s\n", path); return 2; }
    char line[256];
    unsigned seed = 0; int mode = 0, c1 = 0, c2 = 0, hp1 = MAX_HEALTH, hp2 = MAX_HEALTH;
    uint64_t cfg = 0;
    int ver = 0;
    if (!fgets(line, sizeof(line), f) || sscanf(line, "EFREC 2 sim %d", &ver) != 1) {
        printf("replay: %s was recorded before sim versions existed (EFREC 1) or is not a recording - "
               "it cannot be replayed by this build\n", path);
        fclose(f); return 2;
    }
    if (ver != SIM_VERSION) {
        printf("replay: %s was recorded with sim version %d, this build is version %d - not replayable\n",
               path, ver, SIM_VERSION);
        fclose(f); return 2;
    }
    if (!fgets(line, sizeof(line), f) ||
        sscanf(line, "seed %u mode %d p1 %d p2 %d hp1 %d hp2 %d config %" SCNx64,
               &seed, &mode, &c1, &c2, &hp1, &hp2, &cfg) != 7) {
        printf("replay: %s has a bad header\n", path); fclose(f); return 2;
    }
    static Game g;
    SetupHeadless(&g, mode, c1, c2, seed);
    g.player1.health = hp1; g.player2.health = hp2;
    uint64_t myCfg = Sim_ConfigHash(&g);
    int bad = 0, checks = 0;
    if (myCfg != cfg) {
        printf("replay: CONFIG MISMATCH recorded %016" PRIx64 " here %016" PRIx64
               " (different sprites.cfg / sheets / rules) - result will not match\n", cfg, myCfg);
        bad++;
    }
    while (fgets(line, sizeof(line), f)) {
        unsigned t; unsigned a, b; uint64_t h;
        if (sscanf(line, "t %u %x %x", &t, &a, &b) == 3) {
            InputBits in[2] = { (InputBits)a, (InputBits)b };
            Game_SimTick(&g, in);
            if (g.simTick != t) { printf("replay: tick %u, expected %u\n", g.simTick, t); bad++; break; }
        } else if (sscanf(line, "h %u %" SCNx64, &t, &h) == 2 || sscanf(line, "end %u %" SCNx64, &t, &h) == 2) {
            checks++;
            uint64_t mine = Sim_Hash(&g);
            if (t != g.simTick || mine != h) {
                if (bad < 5) printf("replay: DESYNC at tick %u: recorded %016" PRIx64 " replayed %016" PRIx64 "\n", t, h, mine);
                bad++;
            }
        }
    }
    fclose(f);
    printf("replay %s: seed %u mode %d %s vs %s, %u ticks, %d hash checks, %s (P1 hp %d, P2 hp %d, winner %d)\n",
           path, seed, mode, g.characters[c1].name, g.characters[c2].name, (unsigned)g.simTick, checks,
           bad ? "FAIL" : "PASS", g.player1.health, g.player2.health, g.winner);
    (void)verbose;
    Player_UnloadSprites(&g.player1); Player_UnloadSprites(&g.player2);
    return bad ? 1 : 0;
}

// ------------------------------------------------------------------------ sim test --
// A scripted "human" (deterministic in the tick number only) for each non-CPU slot.
typedef struct { SimRng r; InputBits hold; int left; bool attacks; } Script;
static InputBits ScriptStep(Script *s) {
    InputBits out;
    bool fresh = false;
    if (s->left <= 0) {
        int r = Rng_Range(&s->r, 0, 99);
        InputBits h = 0;
        if (r < 30) h |= IN_RIGHT;
        else if (r < 50) h |= IN_LEFT;
        else if (r < 58) h |= IN_DOWN;
        else if (r < 66) h |= IN_UP | (Rng_Range(&s->r, 0, 1) ? IN_RIGHT : IN_LEFT);
        else if (r < 74) h |= IN_BLOCK;
        if (s->attacks) {
            static const InputBits AT[6] = { IN_PUNCH, IN_KICK, IN_SP1, IN_SP2, IN_THROW, IN_TAUNT };
            int a = Rng_Range(&s->r, 0, 9);
            if (a < 6) h |= AT[a];
            if (a < 2) h |= IN_JATK;
        }
        s->hold = h; s->left = Rng_Range(&s->r, 4, 30); fresh = true;
    }
    out = s->hold & IN_HELD_MASK;
    if (fresh) out |= s->hold & IN_PRESS_MASK;
    s->left--;
    return out;
}

// expect: final hash on x86-64 gcc -ffp-contract=off for SIM_VERSION 2.  Another platform or compiler
// that gets a different value is not lockstep-compatible with it (see README "Determinism").
typedef struct { const char *name; int mode, c1, c2; uint32_t seed; bool attacks; int skipAt; uint64_t expect; } Scenario;

#define MAX_TICKS (99 * 60 + 400)
#define MAX_CHECKS (MAX_TICKS / SIM_HASH_EVERY + 4)
typedef struct { int n; uint64_t h[MAX_CHECKS]; uint32_t ticks; uint64_t final; int hp1, hp2, winner; } RunResult;

// make the per-tick input stream once, exactly as a lockstep server would deliver it
static int MakeInputs(const Scenario *sc, InputBits (*in)[2]) {
    Script s1 = { 0 }, s2 = { 0 };
    Rng_Seed(&s1.r, sc->seed * 3u + 1u); Rng_Seed(&s2.r, sc->seed * 7u + 5u);
    s1.attacks = s2.attacks = sc->attacks;
    for (int t = 0; t < MAX_TICKS; t++) {
        in[t][0] = ScriptStep(&s1);
        in[t][1] = ScriptStep(&s2);
        if (t + 1 == sc->skipAt) in[t][0] |= IN_CONFIRM;
        else in[t][0] &= (InputBits)~IN_CONFIRM;
    }
    return MAX_TICKS;
}

// batch: ticks per "frame" (0 = random 0..4 per frame, with pause frames in between)
static void RunOnce(const Game *start, InputBits (*in)[2], int batch, uint32_t flipTick, RunResult *res) {
    int human = start->mode == MODE_CPU_VS_1P ? 1 : 0;
    static Game g;
    g = *start;                                  // snapshot copy = a fresh fight
    memset(res, 0, sizeof(*res));
    SimRng fr; Rng_Seed(&fr, 99);
    int t = 0, resultTicks = 0, frame = 0;
    while (t < MAX_TICKS && resultTicks < 120) {
        int k = batch ? batch : Rng_Range(&fr, 0, 4);
        frame++;
        if (frame % 37 == 0) {                   // a paused frame: the sim must not move
            g.paused = true;
            InputBits junk[2] = { 0xFFFF, 0xFFFF };
            Game_SimTick(&g, junk);
            g.paused = false;
        }
        for (int i = 0; i < k && t < MAX_TICKS && resultTicks < 120; i++, t++) {
            InputBits b[2] = { in[t][0], in[t][1] };
            if (flipTick && (uint32_t)t >= flipTick && (uint32_t)t < flipTick + 60) b[human] ^= IN_RIGHT | IN_LEFT;
            Game_SimTick(&g, b);
            if (g.simTick % SIM_HASH_EVERY == 0 && res->n < MAX_CHECKS) res->h[res->n++] = Sim_Hash(&g);
            if (g.screen == SCREEN_RESULT) resultTicks++;
        }
    }
    res->ticks = g.simTick; res->final = Sim_Hash(&g);
    res->hp1 = g.player1.health; res->hp2 = g.player2.health; res->winner = g.winner;
}

static bool SameRun(const RunResult *a, const RunResult *b, int *firstDiff) {
    *firstDiff = -1;
    int n = a->n < b->n ? a->n : b->n;
    for (int i = 0; i < n; i++) if (a->h[i] != b->h[i]) { *firstDiff = i; return false; }
    if (a->n != b->n || a->ticks != b->ticks || a->final != b->final) { *firstDiff = n; return false; }
    return true;
}

static int TestAccumulator(void) {
    int fails = 0;
    double acc = 0; int total = 0, bad = 0;
    for (int i = 0; i < 6000; i++) {            // 60 Hz with +-1 ms vsync jitter: always 1 tick
        double dt = SIM_DT + ((i * 7919) % 21 - 10) * 0.0001;
        int n = Sim_StepsForFrame(&acc, dt); total += n; if (n != 1) bad++;
    }
    printf("  accumulator 60 Hz +-1 ms jitter : %d frames -> %d ticks, %d frames not 1 tick  %s\n",
           6000, total, bad, bad ? "FAIL" : "ok");
    fails += bad != 0;
    acc = 0; total = 0;
    for (int i = 0; i < 1200; i++) total += Sim_StepsForFrame(&acc, 1.0 / 120.0);
    printf("  accumulator 120 Hz              : 1200 frames -> %d ticks (expect 600)  %s\n", total, total == 600 ? "ok" : "FAIL");
    fails += total != 600;
    acc = 0; total = 0;
    for (int i = 0; i < 600; i++) total += Sim_StepsForFrame(&acc, 1.0 / 30.0);
    printf("  accumulator 30 Hz               : 600 frames -> %d ticks (expect 1200)  %s\n", total, total == 1200 ? "ok" : "FAIL");
    fails += total != 1200;
    acc = 0; total = Sim_StepsForFrame(&acc, 3.0 / 60.0);
    printf("  accumulator one 3/60 s frame    : %d ticks (expect 3)  %s\n", total, total == 3 ? "ok" : "FAIL");
    fails += total != 3;
    return fails;
}

// SIM_VERSION 2 rules, each from a standing start face to face (P1 left, P2 right, in reach).
typedef struct { int hp1, hp2, winner; GameScreen screen; } RuleOut;
static RuleOut RuleFight(InputBits p1Hold, InputBits p1Press, InputBits p2Hold, InputBits p2Press,
                         int hp1, int hp2) {
    static Game g;
    SetupHeadless(&g, MODE_1P_VS_2P, 5, 5, 1u);        // mirror match: same timings on both sides
    g.screen = SCREEN_FIGHT;
    g.player1.position.x = 600.0f;
    g.player2.position.x = 690.0f;
    g.player1.health = hp1;
    g.player2.health = hp2;
    for (int t = 0; t < 90 && g.screen == SCREEN_FIGHT; t++) {
        InputBits in[2] = { p1Hold, p2Hold };
        if (t == 10) { in[0] |= p1Press; in[1] |= p2Press; }
        Game_SimTick(&g, in);
    }
    RuleOut o = { g.player1.health, g.player2.health, g.winner, g.screen };
    Player_UnloadSprites(&g.player1); Player_UnloadSprites(&g.player2);
    return o;
}

static int TestRules(void) {
    int fails = 0;
    RuleOut open_  = RuleFight(0, IN_PUNCH, 0, 0, 100, 100);
    RuleOut block  = RuleFight(0, IN_PUNCH, IN_BLOCK, 0, 100, 100);
    RuleOut thrown = RuleFight(0, IN_THROW, IN_BLOCK, 0, 100, 100);
    RuleOut busy   = RuleFight(0, IN_PUNCH, IN_BLOCK, IN_KICK, 100, 100);   // block held while attacking
    RuleOut dko    = RuleFight(0, IN_PUNCH, 0, IN_PUNCH, MELEE_DAMAGE, MELEE_DAMAGE);
    struct { const char *what; bool ok; } r[] = {
        { "punch hits an open fighter            ", open_.hp2 < 100 },
        { "standing block from the front stops it ", block.hp2 == 100 },
        { "a throw beats a block                  ", thrown.hp2 < 100 },
        { "holding block while attacking: no block", busy.hp2 < 100 },
        { "double KO is a draw                    ", dko.screen == SCREEN_RESULT && dko.winner == 0 &&
                                                     dko.hp1 == 0 && dko.hp2 == 0 },
    };
    printf("\ncombat rules (sim version %d):\n", SIM_VERSION);
    for (size_t i = 0; i < sizeof(r) / sizeof(r[0]); i++) {
        printf("  %s: %s\n", r[i].what, r[i].ok ? "ok" : "FAIL");
        if (!r[i].ok) fails++;
    }
    return fails;
}

int Sim_RunTests(int argc, char **argv) {
    (void)argc; (void)argv;
    static const Scenario SC[] = {
        { "1P vs CPU   MIKE vs DARAGH ", MODE_1P_VS_CPU, 5, 6, 1234u, true,  0,  0xb5ff8d849a868bcbull },
        { "CPU vs 1P   DEC vs DRAGON  ", MODE_CPU_VS_1P, 4, 2, 99u,   true,  40, 0xeb5ca790adb40ba9ull },
        { "1P vs 2P    RA vs FLAME    ", MODE_1P_VS_2P,  0, 3, 7u,    true,  30, 0xc5342812f2a56f7cull },
        { "1P vs 2P    PAUL vs MIKE (no attacks: time-out)", MODE_1P_VS_2P, 1, 5, 5u, false, 0, 0x0ce736c967cd17acull },
    };
    static InputBits in[MAX_TICKS][2];
    static Game start;
    static RunResult A, B, C, D, E, F;
    int fails = 0;
    printf("=== Padel Wars deterministic sim test (headless, no window) ===\n");
    printf("tick %.9f s, hash checkpoint every %d ticks\n", SIM_DT, SIM_HASH_EVERY);
    fails += TestAccumulator();
    fails += TestRules();

    for (size_t s = 0; s < sizeof(SC) / sizeof(SC[0]); s++) {
        const Scenario *sc = &SC[s];
        SetupHeadless(&start, sc->mode, sc->c1, sc->c2, sc->seed);
        MakeInputs(sc, in);
        RunOnce(&start, in, 1, 0, &A);
        RunOnce(&start, in, 1, 0, &B);
        RunOnce(&start, in, 3, 0, &C);
        RunOnce(&start, in, 0, 0, &D);
        int d1, d2, d3;
        bool ab = SameRun(&A, &B, &d1), ac = SameRun(&A, &C, &d2), ad = SameRun(&A, &D, &d3);
        // sensitivity: a changed input must change the hash from (about) that tick on
        RunOnce(&start, in, 1, 500, &E);
        int de; bool ae = SameRun(&A, &E, &de);
        bool cpu = sc->mode != MODE_1P_VS_2P, seedOk = true;
        if (cpu) {                               // another CPU seed must play differently
            static Game other;
            SetupHeadless(&other, sc->mode, sc->c1, sc->c2, sc->seed + 1);
            RunOnce(&other, in, 1, 0, &F);
            int df; seedOk = !SameRun(&A, &F, &df);
            Player_UnloadSprites(&other.player1); Player_UnloadSprites(&other.player2);
        }
        bool known = A.final == sc->expect;
        bool pass = ab && ac && ad && !ae && seedOk && known;
        printf("\n[%s] %s\n", pass ? "PASS" : "FAIL", sc->name);
        printf("  config hash %016" PRIx64 "  seed %u  %u ticks (%.1f s)  P1 hp %d  P2 hp %d  winner %d\n",
               Sim_ConfigHash(&start), (unsigned)sc->seed, (unsigned)A.ticks, A.ticks * SIM_DT_WALL, A.hp1, A.hp2, A.winner);
        printf("  run 1 vs run 2 (1 tick/frame)        : %s (%d checkpoints)\n", ab ? "identical" : "DIFFERENT", A.n);
        printf("  1 tick/frame vs 3 ticks/frame        : %s\n", ac ? "identical" : "DIFFERENT");
        printf("  1 tick/frame vs random 0-4 + pauses  : %s\n", ad ? "identical" : "DIFFERENT");
        printf("  human L/R flipped for ticks 500-559  : %s (first differing checkpoint: tick %d)\n",
               ae ? "NOT DETECTED" : "detected", (de + 1) * SIM_HASH_EVERY);
        if (cpu) printf("  CPU seed+1                           : %s\n", seedOk ? "plays differently" : "SAME (RNG unused?)");
        printf("  final hash %016" PRIx64 "  expected %016" PRIx64 " %s\n", A.final, sc->expect,
               known ? "(match)" : "(MISMATCH: different sim version, compiler or platform)");
        if (!pass) fails++;

        if (s == 0) {                            // record the same fight through the recorder, replay it
            const char *rp = "sim_test_replay.efrec";
            SimRecorder rec; Rec_Init(&rec, rp);
            static Game g; g = start;
            Rec_FightStart(&rec, &g);
            int resultTicks = 0;
            for (int t = 0; t < MAX_TICKS && resultTicks < 120; t++) {
                Game_SimTick(&g, in[t]);
                Rec_Tick(&rec, &g, in[t]);
                if (g.screen == SCREEN_RESULT) resultTicks++;
            }
            Rec_FightEnd(&rec, &g);
            int rr = Sim_Replay(rp, false);
            printf("  record -> replay round trip          : %s\n", rr == 0 ? "PASS" : "FAIL");
            if (rr) fails++;
        }
        Player_UnloadSprites(&start.player1); Player_UnloadSprites(&start.player2);
    }
    printf("\nper-fighter config hashes (gameplay values from sprites.cfg + sheet sizes):\n");
    for (int c = 0; c < MAX_CHARACTERS; c++) {
        static Game g;
        SetupHeadless(&g, MODE_1P_VS_2P, c, c, 1);
        printf("  %-14s %016" PRIx64 "  projectile %d\n", g.characters[c].name, Sim_PlayerConfigHash(&g.player1), g.player1.projectileKind);
        Player_UnloadSprites(&g.player1); Player_UnloadSprites(&g.player2);
    }
    printf("\nSIM TEST: %s\n", fails ? "FAIL" : "PASS");
    return fails ? 1 : 0;
}

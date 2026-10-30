// Two C clients in one process against the real relay (run via test_netplay.sh).
//   1. create + join + pick + ready + loaded -> both get the same seed/delay
//   2. 600 lockstep frames of a toy sim with random inputs: hashes must match
//   3. client B's socket drops at frame 200; B rejoins, replays, and both finish
//      frame 600 with the same hash
#include "netplay.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

typedef struct { uint32_t rng, x[2], hp[2]; int frames; } Toy;

static void toy_reset(Toy *t, uint32_t seed) { memset(t, 0, sizeof(*t)); t->rng = seed ? seed : 1; t->hp[0] = t->hp[1] = 1000; }
static void toy_step(Toy *t, const uint16_t in[2])
{
    for (int s = 0; s < 2; s++) {
        t->x[s] += (in[s] & 1) ? 3 : 0;
        if (in[s] & 2) t->hp[s ^ 1] -= Np_Rand(&t->rng) % 3;
    }
    t->frames++;
}
static uint32_t toy_hash(const Toy *t) { return Np_HashBytes(NP_HASH_INIT, t, sizeof(*t)); }

typedef struct { Netplay *np; Toy sim; uint32_t inRng; bool started, dropped; const char *name; } Client;

#ifdef _WIN32
#include <windows.h>
static void sleep_ms(int ms) { Sleep((DWORD)ms); }
#else
static void sleep_ms(int ms) { struct timespec ts = { 0, ms * 1000000L }; nanosleep(&ts, NULL); }
#endif

static int fails;
#define CHECK(c, ...) do { if (!(c)) { fails++; printf("FAIL: " __VA_ARGS__); printf("\n"); } } while (0)

static void pump(Client *c, int target)
{
    Np_Poll(c->np);
    NpEvent ev;
    while (Np_NextEvent(c->np, &ev)) {
        if (ev.type == NP_EV_COUNTDOWN) Np_Loaded(c->np);
        if (ev.type == NP_EV_START) {
            toy_reset(&c->sim, ev.seed);
            c->started = true;
            printf("%s start seed=%u delay=%d slot=%d resume=%d picks=%s/%s\n", c->name, ev.seed, ev.delay,
                   ev.slot, ev.resumeFrame, ev.picks[0], ev.picks[1]);
        }
        if (ev.type == NP_EV_MATCH_END) { printf("%s match end: %s\n", c->name, ev.text); fails++; }
        if (ev.type == NP_EV_PEER_HOLD) printf("%s peer hold %d ms\n", c->name, ev.holdMs);
        if (ev.type == NP_EV_PEER_BACK) printf("%s peer back\n", c->name);
        if (ev.type == NP_EV_ERROR) printf("%s error: %s\n", c->name, ev.text);
    }
    if (!Np_InMatch(c->np)) return;
    int n = Np_StepsDue(c->np);
    for (int i = 0; i < n && Np_State(c->np)->frame < target; i++) {
        uint16_t in[2];
        Np_SetLocalInput(c->np, (uint16_t)(Np_Rand(&c->inRng) & 3));
        if (!Np_FrameInputs(c->np, in)) break;
        toy_step(&c->sim, in);
        Np_FrameDone(c->np, toy_hash(&c->sim));
    }
}

int main(int argc, char **argv)
{
    const char *url = argc > 1 ? argv[1] : "ws://127.0.0.1:3000/egyptian";
    const int target = 600, dropAt = 200;
    Client a = { Np_New(url, "test-a"), {0}, 11, false, false, "A" };
    Client b = { Np_New(url, "test-b"), {0}, 22, false, false, "B" };

    Np_Create(a.np);
    for (int i = 0; i < 400 && !Np_State(a.np)->room[0]; i++) { pump(&a, 0); pump(&b, 0); sleep_ms(5); }
    CHECK(Np_State(a.np)->room[0], "A got no room");
    printf("room %s\n", Np_State(a.np)->room);
    Np_Join(b.np, Np_State(a.np)->room);
    Np_Pick(a.np, "2");
    Np_Pick(b.np, "5");
    Np_Ready(a.np, true);
    Np_Ready(b.np, true);

    time_t until = time(NULL) + 30;
    while (time(NULL) < until) {
        pump(&a, target);
        pump(&b, target);
        if (!b.dropped && Np_State(b.np)->frame >= dropAt) {
            b.dropped = true;
            printf("dropping B at frame %d\n", Np_State(b.np)->frame);
            Np_DebugDrop(b.np);
        }
        if (Np_State(a.np)->frame >= target && Np_State(b.np)->frame >= target) break;
        sleep_ms(2);
    }
    CHECK(a.started && b.started, "match did not start");
    CHECK(b.dropped, "B never dropped");
    CHECK(Np_State(a.np)->frame == target && Np_State(b.np)->frame == target,
          "frames %d/%d", Np_State(a.np)->frame, Np_State(b.np)->frame);
    uint32_t ha = toy_hash(&a.sim), hb = toy_hash(&b.sim);
    CHECK(ha == hb, "hash %u != %u", ha, hb);
    printf("A frame %d hash %u | B frame %d hash %u | delay %d rtt %.1f\n",
           Np_State(a.np)->frame, ha, Np_State(b.np)->frame, hb, Np_State(a.np)->delay, Np_State(a.np)->rttMs);
    Np_Free(a.np);
    Np_Free(b.np);
    printf(fails ? "FAILED (%d)\n" : "PASS netplay C client\n", fails);
    return fails ? 1 : 0;
}

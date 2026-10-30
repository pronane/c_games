// netplay - C client for the c_games two-player lockstep relay
// (shared/netplay/server, the same protocol HD Fighter's browser client speaks).
//
// The game owns the simulation. This library owns the room, the clock and
// the inputs:
//
//   Netplay *np = Np_New("wss://host/egyptian", userId);
//   Np_Create(np) / Np_Join(np, "K7Q2M") / Np_Quick(np);
//   Np_Pick(np, "3");  Np_Ready(np, true);
//
//   every render frame:
//     Np_Poll(np);
//     while (Np_NextEvent(np, &ev)) ...        // NP_EV_COUNTDOWN: load, then Np_Loaded(np)
//                                               // NP_EV_START: reset the sim with ev.seed / ev.picks
//     if (Np_InMatch(np)) {
//         int n = Np_StepsDue(np);              // 0..2 at 60 Hz (more while catching up after a rejoin)
//         for (int i = 0; i < n; i++) {
//             uint16_t in[2];
//             Np_SetLocalInput(np, myBits);     // this frame's local buttons, sent `delay` frames ahead
//             if (!Np_FrameInputs(np, in)) break;   // still waiting for the other player
//             Sim_Step(in[0], in[1]);
//             Np_FrameDone(np, Sim_Hash());     // hashes are compared every 30 frames
//         }
//     }
//
// The sim must be deterministic: a fixed 1/60 s step, randomness only from
// ev.seed, and no reads of the keyboard, GetFrameTime() or rand() inside it.
#ifndef NETPLAY_H
#define NETPLAY_H

#include <stdbool.h>
#include <stdint.h>

#define NP_HASH_EVERY 30
#define NP_MAX_FRAMES (60 * 60 * 8)   // 8 minutes of inputs per match

typedef struct Netplay Netplay;

typedef enum {
    NP_OFFLINE = 0,     // not connected (or gave up)
    NP_CONNECTING,      // socket opening / server waking up
    NP_IDLE,            // connected, not in a room
    NP_QUEUED,          // quick play: waiting for an opponent
    NP_LOBBY,           // in a room: pick + ready
    NP_COUNTDOWN,       // both ready: load, then Np_Loaded
    NP_PLAYING,         // match running
} NpPhase;

typedef enum {
    NP_EV_NONE = 0,
    NP_EV_ROOM,         // entered a room (created / joined / matched): room, slot
    NP_EV_LOBBY,        // picks / ready / occupancy changed
    NP_EV_COUNTDOWN,    // load the picks now, then call Np_Loaded
    NP_EV_START,        // reset the sim: seed, picks, delay; resumeFrame > 0 after a rejoin
    NP_EV_CANCEL,       // countdown cancelled (text = reason)
    NP_EV_PEER_LEFT,    // opponent left the room (text)
    NP_EV_PEER_HOLD,    // opponent dropped mid-match; the match waits (holdMs)
    NP_EV_PEER_BACK,    // opponent rejoined
    NP_EV_MATCH_END,    // match stopped early: forfeit (winner >= 0), desync or lost connection (text)
    NP_EV_ERROR,        // server said no (text), e.g. "Room not found"
    NP_EV_DISCONNECT,   // socket lost; reconnecting if we were in a room
} NpEventType;

typedef struct {
    NpEventType type;
    int slot;              // our slot 0/1
    int winner;            // NP_EV_MATCH_END: 0/1 for a forfeit, -1 otherwise
    uint32_t seed;
    int delay;
    int resumeFrame;       // NP_EV_START after a rejoin: frames to catch up (Np_StepsDue runs fast)
    int holdMs;
    char room[8];
    char picks[2][33];
    char text[128];
} NpEvent;

typedef struct {
    NpPhase phase;
    int slot;                // -1 until in a room
    char room[8];
    char picks[2][33];
    bool ready[2];
    bool occupied[2];
    int delay;
    float rttMs, jitterMs;
    int frame;               // next sim frame to run
    bool waiting;            // the last Np_FrameInputs had no input from the other player
    bool slow;               // waiting for the other player for over a second
    bool peerHeld;           // opponent dropped; match paused
    int holdLeftMs;
    char status[128];        // human-readable line for the UI ("Waking the server...")
} NpState;

Netplay *Np_New(const char *url, const char *userId);   // userId: stable per game window
void Np_Free(Netplay *np);

void Np_Poll(Netplay *np);                    // call once per render frame
bool Np_NextEvent(Netplay *np, NpEvent *ev);
const NpState *Np_State(const Netplay *np);

void Np_Create(Netplay *np);
void Np_Join(Netplay *np, const char *code);
void Np_Quick(Netplay *np);
void Np_Pick(Netplay *np, const char *pick);
void Np_Ready(Netplay *np, bool ready);
void Np_Loaded(Netplay *np);
void Np_Leave(Netplay *np);                   // leave the room (ends a running match for both)

bool Np_InMatch(const Netplay *np);
int  Np_StepsDue(Netplay *np);
bool Np_SetLocalInput(Netplay *np, uint16_t bits);   // false: that frame already has input
bool Np_FrameInputs(Netplay *np, uint16_t out[2]);
void Np_FrameDone(Netplay *np, uint32_t hash);
void Np_MatchOver(Netplay *np);               // the sim decided the result; stop stepping

// testing: drop the socket as if the network failed (reconnects and resumes)
void Np_DebugDrop(Netplay *np);

// small helpers games use for their own hashes and seeded RNG
static inline uint32_t Np_HashBytes(uint32_t h, const void *data, int len)
{
    const unsigned char *p = (const unsigned char *)data;
    for (int i = 0; i < len; i++) { h ^= p[i]; h *= 16777619u; }
    return h;
}
#define NP_HASH_INIT 2166136261u

static inline uint32_t Np_Rand(uint32_t *state)   // xorshift32; state must not be 0
{
    uint32_t x = *state;
    x ^= x << 13; x ^= x >> 17; x ^= x << 5;
    return *state = x;
}

#endif

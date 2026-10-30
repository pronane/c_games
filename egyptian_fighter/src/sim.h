// sim.h - deterministic fight simulation helpers: state hash, config hash, fixed-step
// accumulator, input record / replay and the headless --sim-test.
#ifndef EF_SIM_H
#define EF_SIM_H

#include <stdint.h>
#include <stdio.h>
#include "game.h"

#define SIM_HASH_EVERY 30            // checkpoint hash interval in ticks (0.5 s)

// FNV-1a 64 over every simulation field, one by one (never the raw struct: padding and
// textures).  Render-only data (textures, faces, select screen, pause overlay) is excluded.
uint64_t Sim_Hash(const Game *g);

// Hash of everything gameplay depends on that comes from data files rather than code:
// per fighter the loaded frame counts / frame times / loop points of every animation and the
// projectile kind (sprites.cfg + the sheet image widths), plus the rule constants in common.h.
// Two machines must agree on this before a netplay fight starts.
uint64_t Sim_PlayerConfigHash(const Player *p);
uint64_t Sim_ConfigHash(const Game *g);

// Fixed-step accumulator: how many SIM_DT ticks to run for a frame of frameDt seconds.
int Sim_StepsForFrame(double *accum, double frameDt);

// ---- input recording (one file per fight) ----
typedef struct {
    char path[400];
    FILE *f;
    int fights;
    bool active;
} SimRecorder;
void Rec_Init(SimRecorder *r, const char *path);
void Rec_FightStart(SimRecorder *r, const Game *g);          // call right after a fight is set up
void Rec_Tick(SimRecorder *r, const Game *g, const InputBits in[2]);   // after Game_SimTick
void Rec_FightEnd(SimRecorder *r, const Game *g);
int  Sim_Replay(const char *path, bool verbose);             // headless; 0 = all hashes match
int  Sim_RunTests(int argc, char **argv);                    // --sim-test; 0 = PASS

#endif

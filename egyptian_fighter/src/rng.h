// rng.h - tiny deterministic PRNG for the fight simulation (xorshift32 + splitmix seeding).
// Same seed -> same sequence on every compiler / OS / wasm.  Lives in the Game state so it can
// be hashed, saved and replayed.  Never use rand() or raylib's GetRandomValue() in the sim.
#ifndef EF_RNG_H
#define EF_RNG_H
#include <stdint.h>

typedef struct { uint32_t s; } SimRng;

static inline void Rng_Seed(SimRng *r, uint32_t seed) {
    uint32_t z = seed + 0x9E3779B9u;                 // splitmix32 step, so seed 0/1/2 differ a lot
    z = (z ^ (z >> 16)) * 0x85EBCA6Bu;
    z = (z ^ (z >> 13)) * 0xC2B2AE35u;
    z ^= z >> 16;
    r->s = z ? z : 0x6D2B79F5u;                     // xorshift state must not be 0
}
static inline uint32_t Rng_Next(SimRng *r) {
    uint32_t x = r->s;
    x ^= x << 13; x ^= x >> 17; x ^= x << 5;
    return r->s = x;
}
// inclusive range, like raylib's GetRandomValue(min, max)
static inline int Rng_Range(SimRng *r, int min, int max) {
    if (max < min) { int t = min; min = max; max = t; }
    uint32_t span = (uint32_t)(max - min) + 1u;
    return min + (int)(Rng_Next(r) % span);
}
#endif

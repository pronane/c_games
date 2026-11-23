#ifndef GAELIC_RELEASE_VISUAL_H
#define GAELIC_RELEASE_VISUAL_H
/* Presentation-only correction; caller retains its simulation vector untouched. */
typedef struct { float offset[3], remaining, duration; } GAReleaseVisual;
void ga_visual_reset(GAReleaseVisual *s);
int ga_visual_start(GAReleaseVisual *s, const float launch[3], const float contact[3], float duration, float max_distance);
void ga_visual_position(GAReleaseVisual *s, const float simulated[3], float dt, int in_flight, float out[3]);
#endif

#include "release_visual.h"
#include <math.h>
#include <string.h>
void ga_visual_reset(GAReleaseVisual *s) { if (s) memset(s, 0, sizeof(*s)); }
int ga_visual_start(GAReleaseVisual *s, const float launch[3], const float contact[3], float duration, float max_distance)
{
    float d[3]; double length = 0; int i;
    if (!s) return 0;
    ga_visual_reset(s);
    if (!launch || !contact || !isfinite(duration) || duration <= 0 || !isfinite(max_distance) || max_distance <= 0) return 0;
    for (i = 0; i < 3; ++i) {
        if (!isfinite(launch[i]) || !isfinite(contact[i])) return 0;
        d[i] = contact[i] - launch[i]; length += (double)d[i]*d[i];
    }
    if (length > (double)max_distance*max_distance) return 0;
    memcpy(s->offset, d, sizeof d); s->duration = s->remaining = duration; return 1;
}
void ga_visual_position(GAReleaseVisual *s, const float simulated[3], float dt, int in_flight, float out[3])
{
    int i; float w = 0;
    if (!simulated || !out) return;
    if (s && !in_flight) ga_visual_reset(s);
    if (s && s->remaining > 0 && s->duration > 0) w = s->remaining / s->duration;
    for (i = 0; i < 3; ++i) out[i] = simulated[i] + (s ? s->offset[i]*w : 0);
    if (s && isfinite(dt) && dt > 0 && s->remaining > 0) {
        s->remaining -= dt;
        if (s->remaining <= 0) ga_visual_reset(s);
    }
}

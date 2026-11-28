#include "release_visual.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
int main(void)
{
    GAReleaseVisual state = {0};
    const float ball[3] = {10, 1, 5}, hand[3] = {10.5f, 1.1f, 5}; float out[3], far[3] = {99, 1, 5};
    assert(ga_visual_start(&state, ball, hand, .15f, 1.5f));
    ga_visual_position(&state, ball, .05f, 1, out);
    assert(fabsf(out[0]-hand[0]) < 1e-5f && ball[0] == 10); /* never alters simulation */
    ga_visual_position(&state, ball, .05f, 1, out);
    assert(out[0] > ball[0] && out[0] < hand[0]);
    ga_visual_position(&state, ball, .2f, 1, out);
    ga_visual_position(&state, ball, 0, 1, out); assert(out[0] == ball[0]);
    assert(ga_visual_start(&state, ball, hand, .15f, 1.5f));
    ga_visual_position(&state, ball, .05f, 0, out); assert(out[0] == ball[0] && !state.remaining);
    assert(!ga_visual_start(&state, ball, far, .15f, 1.5f));
    assert(!ga_visual_start(&state, ball, hand, 0, 1.5f));
    puts("release visual tests passed"); return 0;
}

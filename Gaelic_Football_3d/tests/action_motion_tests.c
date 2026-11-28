#include "action_motion.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>

static AMDatabase db;
static int near(float a, float b) { return fabsf(a-b) < .00001f; }
int main(void)
{
    GAActionMeta pass = {5, 7, GA_LIMB_HAND_R, 0, 1, .6f, 1};
    GAActionMeta solo = {6, 8, GA_LIMB_FOOT_L, 0, 1, .6f, 1};
    GAActionState state;
    float feet[8] = {0}, t, previous = -1;
    ga_action_db_init(&db);
    feet[0] = 0; assert(ga_action_add(&db, &pass, 0, feet));
    feet[0] = .5f; assert(ga_action_add(&db, &pass, .3f, feet));
    feet[0] = 1; assert(ga_action_add(&db, &solo, .3f, feet));
    assert(!ga_action_add(&db, &pass, .6f, feet)); /* no entries at/after contact */
    assert(am_finalize(&db));
    feet[0] = .5f;
    assert(ga_action_begin(&state, &db, &pass, 0, .3f, feet, NULL));
    assert(near(state.entry, .3f) && state.clip == pass.clip && state.action == pass.action);
    for (int i = 0; i <= 10; ++i) {
        assert(ga_action_time(&state, i * .1f, &t) && t >= previous); previous = t;
    }
    assert(ga_action_time(&state, .3f, &t) && near(t, pass.contact));
    assert(ga_action_time(&state, .5f, &t) && near(t, .8f));
    assert(ga_action_time(&state, 2, &t) && near(t, 1));
    /* Starting after a skipped frame still hits the same absolute deadline. */
    assert(ga_action_begin(&state, &db, &pass, .15f, .6f, feet, NULL));
    assert(ga_action_time(&state, .6f, &t) && near(t, pass.contact));
    assert(!ga_action_time(&state, .1f, &t));
    assert(!ga_action_begin(&state, &db, &pass, .55f, .6f, feet, NULL) && !state.active);
    assert(!ga_action_begin(&state, &db, &pass, .6f, .6f, feet, NULL));
    pass.limb = GA_LIMB_HAND_L;
    assert(!ga_action_begin(&state, &db, &pass, 0, .6f, feet, NULL)); /* incompatible limb */
    pass.limb = GA_LIMB_HAND_R; pass.clip = 999;
    assert(!ga_action_begin(&state, &db, &pass, 0, .6f, feet, NULL)); /* no compatible clip */
    /* A candidate that is worse than the old entry cannot replace it. */
    { float fallback[8] = {.5f};
      assert(!ga_action_begin(&state, &db, &solo, 0, .6f, feet, fallback));
      fallback[0] = 2;
      assert(ga_action_begin(&state, &db, &solo, 0, .6f, feet, fallback)); }
    feet[0] = 1;
    assert(ga_action_begin(&state, &db, &solo, 0, .6f, feet, NULL));
    assert(state.action == solo.action && state.clip == solo.clip);
    assert(ga_action_time(&state, .6f, &t) && near(t, solo.contact));
    puts("action motion tests passed"); return 0;
}

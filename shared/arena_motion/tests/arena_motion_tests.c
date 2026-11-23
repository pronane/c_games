#include "../arena_motion.h"
#include <assert.h>
#include <math.h>
#include <float.h>
#include <stdio.h>
#include <string.h>

static AMDatabase db;
static int near(float a, float b) { return fabsf(a-b) < 1e-5f; }

static void features(void)
{
    float f[AM_DIMENSIONS], foot[8] = {1, 2, 3, 4, 5, 6, 7, 8};
    assert(am_build_features(f, foot, 0, 2, 0, 0, 2, 0, AM_NO_CONTACT));
    assert(f[0] == 1 && f[7] == 8 && f[9] == 2);
    assert(near(f[12], .4f) && near(f[14], .8f) && near(f[16], 1.2f));
    assert(near(f[17], 0) && near(f[18], 1) && near(f[23], AM_NO_CONTACT));
    assert(am_build_features(f, foot, 0, 0, 0, 0, 0, 1, .3f));
    assert(near(f[17], sinf(.2f)) && near(f[18], cosf(.2f)) && near(f[23], .3f));
    foot[1] = NAN;
    assert(!am_build_features(f, foot, 0, 0, 0, 0, 0, 0, 1));
    foot[1] = 2;
    assert(!am_build_features(f, foot, 0, 0, 0, 0, 0, 0, -1));
}

static void matching(void)
{
    float foot[8] = {0}; AMRow r; AMQuery q; int i;
    am_init(&db); memset(&r, 0, sizeof(r));
    r.clip = 10; r.category = 1; r.ball = 1; r.action = 1;
    assert(am_build_features(r.feature, foot, 0, 1, 0, 0, 1, 0, .3f));
    assert(am_add(&db, &r));
    r.clip = 11; r.action = 2;
    assert(am_build_features(r.feature, foot, 0, 5, 0, 0, 5, 0, .1f));
    assert(am_add(&db, &r));
    r.clip = 12; r.ball = 2;
    assert(am_add(&db, &r)); /* identical motion but incompatible ball */
    assert(am_finalize(&db));
    am_query_init(&q); q.category = 1; q.ball = 1; q.action = 2;
    assert(am_build_features(q.feature, foot, 0, 5, 0, 0, 5, 0, .1f));
    assert(am_search(&db, &q) == 1);
    q.ball = 2; assert(am_search(&db, &q) == 2);
    q.action = 1; assert(am_search(&db, &q) == -1);
    q.action = AM_ANY; q.ball = 1; q.clip = 10;
    assert(am_search(&db, &q) == 0); /* explicit clip always wins */
    q.clip = AM_ANY;
    assert(am_search(&db, &q) == 1); /* trajectory/contact decide */
    q.feature[0] = NAN; assert(am_search(&db, &q) == -1);
    q.feature[0] = 0;
    r.clip = 13; assert(am_add(&db, &r));
    assert(am_search(&db, &q) == -1); /* mutation invalidates normalization */
    assert(am_finalize(&db));
    for (i = db.count; i < AM_MAX_ROWS; ++i) assert(am_add(&db, &r));
    assert(!am_add(&db, &r));
    r.action = AM_ANY; assert(!am_add(&db, &r));
}

static void timing(void)
{
    float t = -1;
    assert(am_action_time(0, .4f, .1f, .5f, 1, 1, &t) && near(t, .1f));
    assert(am_action_time(.2f, .4f, .1f, .5f, 1, 1, &t) && near(t, .3f));
    assert(am_action_time(.4f, .4f, .1f, .5f, 1, 1, &t) && near(t, .5f));
    assert(am_action_time(.6f, .4f, .1f, .5f, 1, 1, &t) && near(t, .7f));
    assert(am_action_time(2, .4f, .1f, .5f, 1, 1, &t) && near(t, 1));
    assert(am_action_time(FLT_MAX, FLT_MIN, .1f, .5f, FLT_MAX, 1, &t) && near(t, 1));
    assert(!am_action_time(0, 0, .1f, .5f, 1, 1, &t));
    assert(!am_action_time(0, 1, .6f, .5f, 1, 1, &t));
    assert(!am_action_time(0, 1, .1f, .5f, 1, .4f, &t));
}
static void smoothing(void)
{
    float x = 0, y = 0;
    for (int i = 0; i < 30; ++i) x = am_smooth(x, 1, 1.f/30.f, .08f);
    for (int i = 0; i < 60; ++i) y = am_smooth(y, 1, 1.f/60.f, .08f);
    assert(near(x, y) && x >= 0 && x <= 1);
    x = am_smooth(0, 1, .05f, .08f);
    y = am_smooth(am_smooth(0, 1, .02f, .08f), 1, .03f, .08f);
    assert(near(x, y));
    assert(am_smooth(.3f, 1, -1, .1f) == .3f);
    assert(am_smooth(.3f, 1, 1, 0) == .3f);
    assert(am_smooth(.3f, NAN, 1, 1) == .3f);
    assert(isfinite(am_smooth(FLT_MAX, -FLT_MAX, FLT_MAX, FLT_MIN)));
}
int main(void) { features(); matching(); timing(); smoothing(); puts("arena motion tests passed"); return 0; }

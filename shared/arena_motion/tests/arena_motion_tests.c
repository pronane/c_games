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
static void gait_direction(void)
{
    /* A low foot travels toward the back in a forward-time gait, then swings
     * forwards while high; reverse the sequence to make a backwards gait. */
    float forward[16] = {0, .3f, 0, .2f, 0, .1f, 0, 0, 0, -.1f, .2f, -.2f, .2f, 0, .2f, .2f};
    float backward[16];
    for (int i = 0; i < 8; ++i) { backward[2*i] = forward[2*(7-i)]; backward[2*i+1] = forward[2*(7-i)+1]; }
    assert(am_gait_reverse(forward, forward, 8) == 0);
    assert(am_gait_reverse(backward, backward, 8) == 1);
    assert(am_gait_reverse(forward, forward, 7) == -1);
    assert(am_gait_reverse(NULL, forward, 8) == -1);
    forward[1] = NAN; assert(am_gait_reverse(forward, forward, 8) == -1);
}
static void loop_advance(void)
{
    float a = .1f, b = .1f;
    for (int i = 0; i < 30; ++i) a = am_loop_advance(a, 1.f/30, 1.2f, .8f);
    for (int i = 0; i < 60; ++i) b = am_loop_advance(b, 1.f/60, 1.2f, .8f);
    assert(fabsf(a-b) < .0001f);
    assert(fabsf(a-.5f) < .0001f);
    assert(am_loop_advance(.2f, -1, 1, 1) == .2f);
    assert(am_loop_advance(.2f, 1, 1, 0) == .2f);
}
static void correction_ramp(void)
{
    assert(am_smoothstep(-1) == 0 && am_smoothstep(2) == 1);
    assert(am_smoothstep(NAN) == 0);
    assert(fabsf(am_smoothstep(.5f)-.5f) < .00001f);
    assert(am_smoothstep(.25f) < am_smoothstep(.75f));
}
static void arm_profile(void)
{
    float arm[12], leg[12], centre, radius, gain;
    for (int i = 0; i < 12; ++i) { leg[i] = sinf(i * 6.2831853f/12); arm[i] = .05f*leg[i]; }
    gain = am_arm_swing_profile(arm, leg, 12, &centre, &radius);
    assert(gain > .9f && fabsf(centre) < .0001f && radius > .9f);
    for (int i = 0; i < 12; ++i) arm[i] = .2f*leg[i];
    assert(am_arm_swing_profile(arm, leg, 12, &centre, &radius) == 0);
    for (int i = 0; i < 12; ++i) arm[i] = -.05f*leg[i];
    assert(am_arm_swing_profile(arm, leg, 12, &centre, &radius) == 0);
    arm[0] = NAN;
    assert(am_arm_swing_profile(arm, leg, 12, &centre, &radius) == 0);
    assert(am_arm_swing_profile(NULL, leg, 12, &centre, &radius) == 0);
}
static void still_rotation(void)
{
    float q[48] = {0};
    for (int i=0;i<12;i++) q[4*i+3] = (i%2) ? -1.f : 1.f;
    assert(am_rotation_stillness(q, 12) > .99f);
    q[4] = sinf(.15f); q[7] = cosf(.15f);
    assert(am_rotation_stillness(q, 12) == 0);
    q[0] = NAN; assert(am_rotation_stillness(q, 12) == 0);
    assert(fabsf(am_bounded_rotation_weight(.5f,.2f,1)-.4f) < 1e-6f);
    assert(am_bounded_rotation_weight(0,.2f,1) == 0);
    assert(am_bounded_rotation_weight(.5f,.2f,NAN) == 0);
}
static void contact_drift(void)
{
    AMContactDrift a, b;
    am_contact_drift_reset(&a); am_contact_drift_reset(&b);
    for (int i = 0; i <= 30; ++i) am_contact_drift_sample(&a, 3.f*i/30, 4.f*i/30, 1.f/30, 1);
    for (int i = 0; i <= 60; ++i) am_contact_drift_sample(&b, 3.f*i/60, 4.f*i/60, 1.f/60, 1);
    assert(a.intervals == 30 && b.intervals == 60);
    assert(fabs(a.distance/a.seconds - 5) < .0001 && fabs(b.distance/b.seconds - 5) < .0001);
    am_contact_drift_sample(&a, 100, 100, .1f, 0);
    am_contact_drift_sample(&a, 200, 200, .1f, 1); /* no swing-to-contact interval */
    assert(a.intervals == 30);
    am_contact_drift_sample(&a, NAN, 0, .1f, 1);
    am_contact_drift_sample(&a, 0, 0, .1f, 1); /* invalid sample breaks continuity */
    assert(a.intervals == 30);
    am_contact_drift_sample(&a, 0, 0, 0, 1);
    am_contact_drift_sample(&a, 0, 0, .1f, 1);
    assert(a.intervals == 30);
    am_contact_drift_reset(&a); assert(a.intervals == 0 && a.seconds == 0 && a.distance == 0);
    am_contact_drift_sample(NULL, 0, 0, 1, 1); am_contact_drift_reset(NULL);
}
static void direction_angle(void)
{
    float x[3] = {1,0,0}, y[3] = {0,1,0}, z[3] = {0,0,0}, angle = 7;
    assert(am_direction_angle(x,y,&angle) && fabsf(angle-1.5707963f) < 1e-6f);
    assert(am_direction_angle(x,x,&angle) && angle == 0);
    assert(!am_direction_angle(x,z,&angle) && angle == 0);
    y[1] = NAN; assert(!am_direction_angle(x,y,&angle));
    assert(!am_direction_angle(NULL,x,&angle)); assert(!am_direction_angle(x,x,NULL));
}
static void mirrored_rotation(void)
{
    float q[4]={.2f,.3f,.4f,.5f}, a[4], b[4], zero[4]={0};
    assert(am_mirror_rotation_x(q,a)); assert(a[0]>0 && a[1]<0 && a[2]<0 && a[3]>0);
    assert(am_mirror_rotation_x(a,b));
    for (int i=0;i<4;++i) assert(fabsf(b[i]-q[i]/sqrtf(.54f))<.00001f);
    assert(am_mirror_rotation_x(a,a));
    assert(!am_mirror_rotation_x(zero,a)); q[0]=NAN; assert(!am_mirror_rotation_x(q,a));
    assert(!am_mirror_rotation_x(NULL,a)); assert(!am_mirror_rotation_x(b,NULL));
}
static void local_rotation(void)
{
    float q[4]={0,0,0,1}, axis[3]={2,0,0}, out[4], zero[3]={0};
    assert(am_rotation_compose_local(q,axis,1,out));
    assert(fabsf(out[0]-sinf(.5f))<1e-6f && fabsf(out[3]-cosf(.5f))<1e-6f);
    assert(am_rotation_compose_local(out,axis,-1,out) && fabsf(out[0])<1e-6f && fabsf(out[3]-1)<1e-6f);
    assert(!am_rotation_compose_local(q,zero,1,out)); assert(!am_rotation_compose_local(q,axis,NAN,out));
    assert(!am_rotation_compose_local(NULL,axis,1,out));
}
static void rotation_distance(void)
{
    float a[4]={0,0,0,1}, b[4]={0,0,0,-1}, c[4]={sinf(.25f),0,0,cosf(.25f)}, z[4]={0};
    float angle=7;
    assert(am_rotation_distance(a,b,&angle) && angle<1e-6f);
    assert(am_rotation_distance(a,c,&angle) && fabsf(angle-.5f)<1e-6f);
    assert(!am_rotation_distance(a,z,&angle) && fabsf(angle-.5f)<1e-6f);
    assert(!am_rotation_distance(NULL,c,&angle)); c[0]=NAN; assert(!am_rotation_distance(a,c,&angle));
}
static void guarded_fade(void)
{
    float a=0,b=0;
    for (int i=0;i<3;i++) a=am_guarded_fade(a,1,1.f/30,.2f);
    for (int i=0;i<6;i++) b=am_guarded_fade(b,1,1.f/60,.2f);
    assert(fabsf(a-b)<1e-6f && fabsf(a-.5f)<1e-6f);
    assert(am_guarded_fade(1,0,1.f/60,.2f)==0);
    assert(am_guarded_fade(1,1,-1,.2f)==0);
    assert(am_guarded_fade(NAN,1,1,.2f)==0);
    assert(am_guarded_fade(0,1,1,0)==0);
    assert(am_guarded_fade(0,1,1,.2f)==1);
}
int main(void) { features(); matching(); timing(); smoothing(); gait_direction(); loop_advance(); correction_ramp(); arm_profile(); still_rotation(); contact_drift(); direction_angle(); mirrored_rotation(); local_rotation(); rotation_distance(); guarded_fade(); puts("arena motion tests passed"); return 0; }

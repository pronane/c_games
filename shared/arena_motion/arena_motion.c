#include "arena_motion.h"
#include <float.h>
#include <math.h>
#include <string.h>

void am_init(AMDatabase *db)
{
    int i;
    if (!db) return;
    memset(db, 0, sizeof(*db));
    for (i = 0; i < AM_DIMENSIONS; ++i) db->weight[i] = 1.0f;
    for (i = 4; i < 8; ++i) db->weight[i] = 1.3f;
    db->weight[8] = db->weight[9] = .8f; db->weight[10] = .7f;
    for (i = 11; i < 17; ++i) db->weight[i] = 1.5f;
    for (i = 17; i < 23; ++i) db->weight[i] = 1.2f;
    db->weight[23] = 12.0f;
}

int am_add(AMDatabase *db, const AMRow *row)
{
    int i;
    if (!db || !row || db->count < 0 || db->count >= AM_MAX_ROWS || row->clip < 0 || row->category < 0 ||
        row->ball < 0 || row->action < 0 || !isfinite(row->time) || row->time < 0) return 0;
    for (i = 0; i < AM_DIMENSIONS; ++i) if (!isfinite(row->feature[i])) return 0;
    db->rows[db->count++] = *row; db->ready = 0;
    return 1;
}

int am_finalize(AMDatabase *db)
{
    int i, j;
    if (!db || db->count <= 0 || db->count > AM_MAX_ROWS) return 0;
    db->ready = 0;
    for (j = 0; j < AM_DIMENSIONS; ++j) {
        double mean = 0, variance = 0, floor = j < 4 ? .05 : .2;
        if (!isfinite(db->weight[j]) || db->weight[j] < 0) return 0;
        for (i = 0; i < db->count; ++i) mean += db->rows[i].feature[j];
        mean /= db->count;
        for (i = 0; i < db->count; ++i) {
            double d = db->rows[i].feature[j] - mean; variance += d*d;
        }
        db->scale[j] = (float)fmax(sqrt(variance / db->count), floor);
        if (!isfinite(db->scale[j])) return 0;
    }
    db->ready = 1; return 1;
}

void am_query_init(AMQuery *query)
{
    if (!query) return;
    memset(query, 0, sizeof(*query));
    query->clip = query->category = query->ball = query->action = AM_ANY;
}

int am_search_if(const AMDatabase *db, const AMQuery *q, AMRowPredicate predicate, void *context)
{
    int i, j, best = -1; double best_cost = DBL_MAX;
    if (!db || !q || !db->ready || db->count <= 0 || db->count > AM_MAX_ROWS) return -1;
    for (j = 0; j < AM_DIMENSIONS; ++j)
        if (!isfinite(q->feature[j]) || !isfinite(db->scale[j]) || db->scale[j] <= 0 ||
            !isfinite(db->weight[j]) || db->weight[j] < 0) return -1;
    for (i = 0; i < db->count; ++i) {
        const AMRow *r = &db->rows[i]; double cost = 0;
        if ((q->clip != AM_ANY && q->clip != r->clip) ||
            (q->category != AM_ANY && q->category != r->category) ||
            (q->ball != AM_ANY && q->ball != r->ball) ||
            (q->action != AM_ANY && q->action != r->action) ||
            (predicate && !predicate(r, context))) continue;
        for (j = 0; j < AM_DIMENSIONS; ++j) {
            double d = ((double)q->feature[j] - r->feature[j]) / db->scale[j];
            cost += db->weight[j] * d * d;
        }
        if (cost < best_cost) { best_cost = cost; best = i; }
    }
    return best;
}

int am_search(const AMDatabase *db, const AMQuery *q)
{
    return am_search_if(db, q, NULL, NULL);
}

int am_build_features(float out[AM_DIMENSIONS], const float foot[8],
                      float vx, float vz, float yaw_rate,
                      float desired_vx, float desired_vz, float desired_yaw_rate,
                      float time_to_contact)
{
    const float times[3] = {.2f, .4f, .6f}; int i;
    float values[7] = {vx, vz, yaw_rate, desired_vx, desired_vz, desired_yaw_rate, time_to_contact};
    if (!out || !foot) return 0;
    for (i = 0; i < 8; ++i) if (!isfinite(foot[i])) return 0;
    for (i = 0; i < 7; ++i) if (!isfinite(values[i])) return 0;
    if (time_to_contact < 0) return 0;
    memcpy(out, foot, 8 * sizeof(float)); out[8] = vx; out[9] = vz; out[10] = yaw_rate;
    for (i = 0; i < 3; ++i) {
        float t = times[i], gain = (1.0f - expf(-4.0f * t)) * .25f;
        float yaw = desired_yaw_rate * t;
        out[11 + i*2] = desired_vx*t + (vx-desired_vx)*gain;
        out[12 + i*2] = desired_vz*t + (vz-desired_vz)*gain;
        out[17 + i*2] = sinf(yaw); out[18 + i*2] = cosf(yaw);
    }
    out[23] = fminf(time_to_contact, AM_NO_CONTACT);
    for (i = 0; i < AM_DIMENSIONS; ++i) if (!isfinite(out[i])) return 0;
    return 1;
}

int am_action_time(float elapsed, float deadline, float entry, float contact,
                   float rate_after, float clip_end, float *clip_time)
{
    double t;
    if (!clip_time || !isfinite(elapsed) || !isfinite(deadline) || !isfinite(entry) ||
        !isfinite(contact) || !isfinite(rate_after) || !isfinite(clip_end) ||
        elapsed < 0 || deadline <= 0 || entry < 0 || contact < entry ||
        clip_end < contact || rate_after < 0) return 0;
    t = elapsed < deadline ? (double)entry + ((double)contact-entry) * ((double)elapsed/deadline)
                           : (double)contact + ((double)elapsed-deadline)*rate_after;
    *clip_time = (float)fmin(t, clip_end);
    return isfinite(*clip_time);
}

float am_smooth(float current, float target, float dt, float response)
{
    double result, blend;
    if (!isfinite(current) || !isfinite(target) || !isfinite(dt) || !isfinite(response) || dt < 0 || response <= 0) return current;
    blend = -expm1(-(double)dt / response);
    result = (double)current + ((double)target - current) * blend;
    return (float)result;
}

int am_gait_reverse(const float *left, const float *right, int frames)
{
    float low[2] = {FLT_MAX, FLT_MAX}; double sum = 0; int count = 0;
    const float *feet[2] = {left, right};
    if (!left || !right || frames < 8 || frames > 1000000) return -1;
    for (int s = 0; s < 2; ++s) for (int i = 0; i < frames; ++i) {
        float y = feet[s][2*i], z = feet[s][2*i+1];
        if (!isfinite(y) || !isfinite(z)) return -1;
        if (y < low[s]) low[s] = y;
    }
    for (int s = 0; s < 2; ++s) for (int i = 0; i < frames; ++i) {
        int j = (i+1) % frames;
        float y0 = feet[s][2*i], y1 = feet[s][2*j];
        if (y0 <= low[s]+.06f && y1 <= low[s]+.06f) {
            sum += (double)feet[s][2*j+1] - feet[s][2*i+1];
            count++;
        }
    }
    if (count < 6 || fabs(sum / count) < .005) return -1;
    return sum > 0 ? 1 : 0;
}

float am_loop_advance(float time, float dt, float rate, float length)
{
    double t;
    if (!isfinite(time) || !isfinite(dt) || !isfinite(rate) || !isfinite(length) ||
        dt < 0 || rate < 0 || length <= 0) return time;
    t = fmod((double)time + (double)dt * rate, (double)length);
    if (t < 0) t += length;
    return (float)t;
}

float am_smoothstep(float x)
{
    if (!isfinite(x) || x <= 0.0f) return 0.0f;
    if (x >= 1.0f) return 1.0f;
    return x*x*(3.0f - 2.0f*x);
}

float am_arm_swing_profile(const float *arm, const float *leg, int n, float *centre, float *radius)
{
    double ma = 0, ml = 0, aa = 0, ll = 0, al = 0;
    float amin = FLT_MAX, amax = -FLT_MAX, lmin = FLT_MAX, lmax = -FLT_MAX;
    if (!arm || !leg || !centre || !radius || n < 8 || n > 1000000) return 0;
    for (int i = 0; i < n; ++i) {
        if (!isfinite(arm[i]) || !isfinite(leg[i])) return 0;
        if (arm[i] < amin) amin = arm[i];
        if (arm[i] > amax) amax = arm[i];
        if (leg[i] < lmin) lmin = leg[i];
        if (leg[i] > lmax) lmax = leg[i];
        ma += arm[i]; ml += leg[i];
    }
    ma /= n; ml /= n;
    for (int i = 0; i < n; ++i) {
        double a = arm[i]-ma, l = leg[i]-ml;
        aa += a*a; ll += l*l; al += a*l;
    }
    if (amax-amin < .06f || lmax-lmin < .12f || aa < 1e-8 || ll < 1e-8 || al/sqrt(aa*ll) < .5) return 0;
    *centre = (float)ml; *radius = fmaxf((lmax-lmin)*.5f, .06f);
    return am_smoothstep((.23f - (amax-amin))/.12f);
}

float am_rotation_stillness(const float *samples, int n)
{
    double reference[4], norm = 0, largest = 0;
    if (!samples || n < 8 || n > 1000000) return 0;
    for (int k = 0; k < 4; ++k) { if (!isfinite(samples[k])) return 0; norm += (double)samples[k]*samples[k]; }
    if (norm < 1e-12) return 0;
    norm = sqrt(norm); for (int k = 0; k < 4; ++k) reference[k] = samples[k]/norm;
    for (int i = 0; i < n; ++i) {
        double d = 0, len = 0;
        for (int k = 0; k < 4; ++k) {
            double v = samples[4*i+k]; if (!isfinite(v)) return 0;
            len += v*v; d += reference[k]*v;
        }
        if (len < 1e-12) return 0;
        d = fmin(1.0, fabs(d/sqrt(len)));
        { double angle = 2*acos(d); if (angle > largest) largest = angle; }
    }
    return am_smoothstep((float)((.08-largest)/.04));
}
float am_bounded_rotation_weight(float angle, float limit, float blend)
{
    if (!isfinite(angle) || !isfinite(limit) || !isfinite(blend) || angle <= 0 || limit <= 0 || blend <= 0) return 0;
    if (blend > 1) blend = 1;
    return blend * fminf(1, limit/angle);
}

void am_contact_drift_reset(AMContactDrift *drift)
{
    if (drift) { drift->distance = 0; drift->seconds = 0; drift->intervals = 0;
        drift->previous_x = drift->previous_z = 0; drift->previous_contact = 0; }
}

void am_contact_drift_sample(AMContactDrift *drift, float x, float z, float dt, int contact)
{
    if (!drift) return;
    if (!isfinite(x) || !isfinite(z) || !isfinite(dt) || dt <= 0) {
        drift->previous_contact = 0; return;
    }
    if (contact && drift->previous_contact) {
        double dx = (double)x - drift->previous_x, dz = (double)z - drift->previous_z;
        drift->distance += hypot(dx, dz); drift->seconds += dt; ++drift->intervals;
    }
    drift->previous_x = x; drift->previous_z = z; drift->previous_contact = !!contact;
}

int am_direction_angle(const float a[3], const float b[3], float *out)
{
    double aa = 0, bb = 0, ab = 0;
    if (!a || !b || !out) return 0;
    for (int i = 0; i < 3; ++i) {
        if (!isfinite(a[i]) || !isfinite(b[i])) return 0;
        aa += (double)a[i]*a[i]; bb += (double)b[i]*b[i]; ab += (double)a[i]*b[i];
    }
    if (aa < 1e-16 || bb < 1e-16) return 0;
    *out = (float)acos(fmax(-1.0, fmin(1.0, ab/(sqrt(aa)*sqrt(bb)))));
    return 1;
}

int am_mirror_rotation_x(const float input[4], float out[4])
{
    double norm=0; float q[4];
    if (!input || !out) return 0;
    for (int i=0;i<4;++i) { if (!isfinite(input[i])) return 0; norm+=(double)input[i]*input[i]; }
    if (norm<1e-12) return 0;
    norm=sqrt(norm); q[0]=(float)(input[0]/norm); q[1]=(float)(-input[1]/norm);
    q[2]=(float)(-input[2]/norm); q[3]=(float)(input[3]/norm);
    for (int i=0;i<4;++i) out[i]=q[i];
    return 1;
}

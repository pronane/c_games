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

int am_search(const AMDatabase *db, const AMQuery *q)
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
            (q->action != AM_ANY && q->action != r->action)) continue;
        for (j = 0; j < AM_DIMENSIONS; ++j) {
            double d = ((double)q->feature[j] - r->feature[j]) / db->scale[j];
            cost += db->weight[j] * d * d;
        }
        if (cost < best_cost) { best_cost = cost; best = i; }
    }
    return best;
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

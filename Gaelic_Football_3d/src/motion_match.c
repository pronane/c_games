#include "motion_match.h"
#include <math.h>
#include <string.h>
#include <float.h>

void mm_init(MMDatabase *db) { memset(db, 0, sizeof(*db)); }

int mm_add(MMDatabase *db, int clip, float time, const float feature[MM_DIMS])
{
    int i; MMRow *row;
    if (!db || !feature || db->count < 0 || db->count >= MM_MAX_ROWS || clip < 0 || !isfinite(time) || time < 0) return 0;
    for (i = 0; i < MM_DIMS; ++i) if (!isfinite(feature[i])) return 0;
    row = &db->rows[db->count++]; row->clip = clip; row->time = time;
    memcpy(row->feature, feature, sizeof(row->feature));
    return 1;
}

int mm_finalize(MMDatabase *db)
{
    int i, j;
    if (!db || db->count <= 0 || db->count > MM_MAX_ROWS) return 0;
    for (j = 0; j < MM_DIMS; ++j) {
        double mean = 0, variance = 0;
        for (i = 0; i < db->count; ++i) mean += db->rows[i].feature[j];
        mean /= db->count;
        for (i = 0; i < db->count; ++i) {
            double d = db->rows[i].feature[j] - mean; variance += d*d;
        }
        /* Avoid amplifying numerical noise in nearly constant dimensions. */
        db->scale[j] = (float)fmax(sqrt(variance / db->count), j < 4 ? 0.05 : 0.2);
    }
    return 1;
}

int mm_search(const MMDatabase *db, int target_clip, const float feature[MM_DIMS])
{
    int i, j, best = -1; double best_cost = DBL_MAX;
    if (!db || !feature || target_clip < 0 || db->count <= 0 || db->count > MM_MAX_ROWS) return -1;
    for (j = 0; j < MM_DIMS; ++j)
        if (!isfinite(feature[j]) || !isfinite(db->scale[j]) || db->scale[j] <= 0) return -1;
    for (i = 0; i < db->count; ++i) {
        double cost = 0;
        if (db->rows[i].clip != target_clip) continue;
        for (j = 0; j < MM_DIMS; ++j) {
            double d = (feature[j] - db->rows[i].feature[j]) / db->scale[j];
            cost += (j < 4 ? 1.0 : 1.3) * d * d;
        }
        if (cost < best_cost) { best_cost = cost; best = i; }
    }
    return best;
}

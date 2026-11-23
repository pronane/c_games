#include "motion_match.h"
#include <string.h>

void mm_init(MMDatabase *db)
{
    int i;
    am_init(db);
    /* The loaded Gaelic GLB is in-place: it has no authentic trajectory data. */
    if (db) for (i = MM_DIMS; i < AM_DIMENSIONS; ++i) db->weight[i] = 0;
}
int mm_add(MMDatabase *db, int clip, float time, const float feature[MM_DIMS])
{
    AMRow row;
    if (!feature) return 0;
    memset(&row, 0, sizeof(row)); row.clip = clip; row.time = time;
    memcpy(row.feature, feature, MM_DIMS * sizeof(float));
    return am_add(db, &row);
}
int mm_finalize(MMDatabase *db) { return am_finalize(db); }
int mm_search(const MMDatabase *db, int clip, const float feature[MM_DIMS])
{
    AMQuery query;
    if (!feature || clip < 0) return -1;
    am_query_init(&query); query.clip = clip;
    memcpy(query.feature, feature, MM_DIMS * sizeof(float));
    return am_search(db, &query);
}

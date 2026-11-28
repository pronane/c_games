#ifndef GAELIC_MOTION_MATCH_H
#define GAELIC_MOTION_MATCH_H

/* Gaelic adapter preserving the original 8-dimensional gait matcher. */
#include "../../shared/arena_motion/arena_motion.h"
#define MM_DIMS 8
#define MM_MAX_ROWS AM_MAX_ROWS
typedef AMDatabase MMDatabase;
void mm_init(MMDatabase *db);
int mm_add(MMDatabase *db, int clip, float time, const float feature[MM_DIMS]);
int mm_finalize(MMDatabase *db);
int mm_search(const MMDatabase *db, int target_clip, const float feature[MM_DIMS]);
#endif

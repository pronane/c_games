#ifndef GAELIC_MOTION_MATCH_H
#define GAELIC_MOTION_MATCH_H

/* Presentation-only exact pose matching. Features are left/right foot XZ
 * position and velocity in model space, sampled from the actual loaded rig. */
#define MM_DIMS 8
#define MM_MAX_ROWS 4096

typedef struct {
    int clip;
    float time;
    float feature[MM_DIMS];
} MMRow;

typedef struct {
    MMRow rows[MM_MAX_ROWS];
    int count;
    float scale[MM_DIMS];
} MMDatabase;

void mm_init(MMDatabase *db);
int mm_add(MMDatabase *db, int clip, float time, const float feature[MM_DIMS]);
int mm_finalize(MMDatabase *db);
/* Only rows for target_clip are legal. Returns row index, or -1 on failure.
 * Equal costs resolve in insertion order, deterministically. */
int mm_search(const MMDatabase *db, int target_clip, const float feature[MM_DIMS]);
#endif

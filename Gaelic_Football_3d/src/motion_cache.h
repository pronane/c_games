#ifndef GAELIC_MOTION_CACHE_H
#define GAELIC_MOTION_CACHE_H
#include "motion_match.h"
#include "action_motion.h"
/* Versioned, bounded gait and action cache. model_path is hashed, not embedded. On failure
 * load clears db; caller must rebuild or disable matching. Not a security format. */
int mm_cache_save(const char *path, const char *model_path, unsigned raylib_version, const MMDatabase *db, const AMDatabase *actions);
int mm_cache_load(const char *path, const char *model_path, unsigned raylib_version, MMDatabase *db, AMDatabase *actions);
#endif

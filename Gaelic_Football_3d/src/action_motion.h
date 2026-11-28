#ifndef GAELIC_ACTION_MOTION_H
#define GAELIC_ACTION_MOTION_H
#include "../../shared/arena_motion/arena_motion.h"

/* Presentation-only action entries. Limb tags are not bone indices. */
enum { GA_LIMB_FOOT_L = 1, GA_LIMB_FOOT_R, GA_LIMB_HAND_L, GA_LIMB_HAND_R };
enum { GA_BALL_CARRIED = 1 };
typedef struct {
    int action, clip, limb;
    float start, end, contact, rate;
} GAActionMeta;
typedef struct {
    int active, action, clip;
    float started, deadline, entry, contact, end, rate;
} GAActionState;

void ga_action_db_init(AMDatabase *db);
int ga_action_add(AMDatabase *db, const GAActionMeta *meta, float time, const float feet[8]);
/* Choose once when observed; only compatible action, limb, and ball rows whose
 * playback is within [0.5, 1.8] times authored speed are eligible. When
 * fallback_feet is non-NULL, never pick a row with worse XZ foot position
 * error than the current selector; return 0 if no acceptable row exists. */
int ga_action_begin(GAActionState *state, const AMDatabase *db, const GAActionMeta *meta,
                    float elapsed, float deadline, const float feet[8], const float fallback_feet[8]);
int ga_action_time(const GAActionState *state, float elapsed, float *time);
#endif

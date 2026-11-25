#ifndef ARENA_MOTION_H
#define ARENA_MOTION_H

/* Engine- and sport-independent motion matching. Coordinates are supplied by
 * the caller in its own consistent facing-root XZ basis, metres and seconds. */
#define AM_DIMENSIONS 24
#define AM_MAX_ROWS 4096
#define AM_ANY (-1)
#define AM_NO_CONTACT 1.5f

typedef struct {
    int clip, category, ball, action;
    float time;
    float feature[AM_DIMENSIONS];
} AMRow;

typedef struct {
    AMRow rows[AM_MAX_ROWS];
    int count, ready;
    float scale[AM_DIMENSIONS], weight[AM_DIMENSIONS];
} AMDatabase;

typedef struct {
    int clip, category, ball, action; /* AM_ANY disables a filter */
    float feature[AM_DIMENSIONS];
} AMQuery;

void am_init(AMDatabase *db);
int am_add(AMDatabase *db, const AMRow *row);
int am_finalize(AMDatabase *db);
/* Returns an index or -1; equal costs resolve in insertion order. All specified
 * filters are hard constraints. No game simulation or renderer state is touched. */
int am_search(const AMDatabase *db, const AMQuery *query);
/* Optional pure predicate for additional candidate constraints, e.g. an
 * action whose remaining wind-up fits an authoritative deadline. */
typedef int (*AMRowPredicate)(const AMRow *row, void *context);
int am_search_if(const AMDatabase *db, const AMQuery *query, AMRowPredicate predicate, void *context);
void am_query_init(AMQuery *query);
/* Foot positions/velocities in the first 8 values; root velocity, yaw rate,
 * damped-pursuit future positions/facings, then time to contact. */
int am_build_features(float out[AM_DIMENSIONS], const float foot[8],
                      float vx, float vz, float yaw_rate,
                      float desired_vx, float desired_vz, float desired_yaw_rate,
                      float time_to_contact);
/* Map a simulation action clock to a clip time while preserving its contact
 * deadline. After contact the original rate resumes. Returns 0 for invalid input. */
int am_action_time(float elapsed, float deadline, float entry, float contact,
                   float rate_after, float clip_end, float *clip_time);
/* Infer which time direction moves low feet backwards relative to a forward
 * travelling root. Samples are cyclic [height, forward] pairs, in metres.
 * Return -1 for ambiguous/invalid, 0 for forward time, 1 for reverse time.
 * Use only on a clip known to represent forward locomotion. */
int am_gait_reverse(const float *left, const float *right, int frames);
/* Profile a weak but coordinated arm swing relative to the opposite leg.
 * Input samples are forward offsets in metres. Returns a 0..1 assist gain;
 * ambiguous, uncoordinated and already-strong motion returns zero. On success
 * writes the leg mean and normalization radius. */
float am_arm_swing_profile(const float *arm, const float *leg, int n, float *centre, float *radius);
/* Advance a looping animation clock in seconds. Invalid inputs leave it unchanged. */
float am_loop_advance(float time, float dt, float rate, float length);
/* Clamped cubic easing for smoothly introducing a bounded correction. */
float am_smoothstep(float x);
/* Frame-rate-independent exponential approach. dt and response are seconds;
 * invalid inputs, negative dt or nonpositive response leave current unchanged. */
float am_smooth(float current, float target, float dt, float response);
#endif

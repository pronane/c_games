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
#endif

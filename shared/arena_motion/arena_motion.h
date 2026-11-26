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
/* Profile relative local joint quaternions (xyzw, four floats per sample).
 * Returns 0..1 when motion is nearly static, zero for moving/invalid data. */
float am_rotation_stillness(const float *samples, int n);
/* Blend fraction that limits a proposed angular correction in radians. */
float am_bounded_rotation_weight(float angle, float limit, float blend);
/* Angle in radians between finite 3D directions. Returns 0 for null,
 * nonfinite or near-zero vectors, leaving out unchanged on failure. Useful
 * for bone-segment diagnostics; it does not infer anatomy or contact. */
int am_direction_angle(const float a[3], const float b[3], float *out);
/* Reflect a local xyzw rotation across the coordinate system's X plane.
 * Caller must establish that the left/right local bases actually mirror.
 * Returns 0 on invalid input, leaving out unchanged; in-place is supported. */
int am_mirror_rotation_x(const float input[4], float out[4]);
/* Compose a local axis-angle offset after an xyzw rotation. Normalizes both
 * inputs, rejects degenerate/nonfinite values, allows in-place output. The
 * caller owns anatomical axes, limits and collision checks. */
int am_rotation_compose_local(const float rotation[4], const float axis[3], float radians, float out[4]);
/* Accumulate horizontal world-space drift while the caller's contact proxy is
 * true in consecutive samples. One independent instance per foot and stream.
 * Distance / seconds is mean path speed, not a sole-contact detector. Invalid
 * samples break continuity. Initialize/reset with am_contact_drift_reset. */
typedef struct {
    double distance, seconds;
    float previous_x, previous_z;
    unsigned long intervals;
    int previous_contact;
} AMContactDrift;
void am_contact_drift_reset(AMContactDrift *drift);
void am_contact_drift_sample(AMContactDrift *drift, float x, float z, float dt, int contact);

/* Advance a looping animation clock in seconds. Invalid inputs leave it unchanged. */
float am_loop_advance(float time, float dt, float rate, float length);
/* Clamped cubic easing for smoothly introducing a bounded correction. */
float am_smoothstep(float x);
/* Frame-rate-independent exponential approach. dt and response are seconds;
 * invalid inputs, negative dt or nonpositive response leave current unchanged. */
float am_smooth(float current, float target, float dt, float response);
#endif

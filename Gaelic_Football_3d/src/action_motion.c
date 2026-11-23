#include "action_motion.h"
#include <math.h>
#include <string.h>

static int valid_meta(const GAActionMeta *m)
{
    return m && m->action > 0 && m->clip >= 0 && m->limb >= GA_LIMB_FOOT_L && m->limb <= GA_LIMB_HAND_R &&
        isfinite(m->start) && isfinite(m->end) && isfinite(m->contact) && isfinite(m->rate) &&
        m->start >= 0 && m->contact > m->start && m->end >= m->contact && m->rate > 0;
}
void ga_action_db_init(AMDatabase *db)
{
    int i;
    am_init(db);
    if (!db) return;
    for (i = 8; i < 23; ++i) db->weight[i] = 0;
    db->weight[23] = 2.0f;
}
int ga_action_add(AMDatabase *db, const GAActionMeta *m, float time, const float feet[8])
{
    AMRow r;
    if (!db || !valid_meta(m) || !feet || !isfinite(time) || time < m->start || time >= m->contact) return 0;
    memset(&r, 0, sizeof r);
    r.clip = m->clip; r.category = m->limb; r.ball = GA_BALL_CARRIED; r.action = m->action; r.time = time;
    memcpy(r.feature, feet, 8*sizeof(float)); r.feature[23] = m->contact - time;
    return am_add(db, &r);
}
typedef struct { const GAActionMeta *meta; float remaining; } CandidateContext;
static int viable(const AMRow *row, void *user)
{
    CandidateContext *c = (CandidateContext *)user;
    float windup = c->meta->contact - row->time;
    float speed = windup / c->remaining;
    return row->time >= c->meta->start && windup >= .015f && isfinite(speed) &&
           speed >= c->meta->rate * .5f && speed <= c->meta->rate * 1.8f;
}
int ga_action_begin(GAActionState *s, const AMDatabase *db, const GAActionMeta *m,
                    float elapsed, float deadline, const float feet[8])
{
    AMQuery q; CandidateContext ctx; int row;
    if (!s) return 0;
    memset(s, 0, sizeof(*s));
    if (!db || !feet || !valid_meta(m) || !isfinite(elapsed) || !isfinite(deadline) ||
        elapsed < 0 || deadline - elapsed < .13f) return 0;
    am_query_init(&q); q.action = m->action; q.clip = m->clip; q.category = m->limb; q.ball = GA_BALL_CARRIED;
    memcpy(q.feature, feet, 8*sizeof(float)); q.feature[23] = (deadline - elapsed) * m->rate;
    ctx.meta = m; ctx.remaining = deadline - elapsed;
    row = am_search_if(db, &q, viable, &ctx);
    if (row < 0) return 0;
    s->active = 1; s->action = m->action; s->clip = m->clip; s->started = elapsed;
    s->deadline = deadline; s->entry = db->rows[row].time; s->contact = m->contact;
    s->end = m->end; s->rate = m->rate;
    return 1;
}
int ga_action_time(const GAActionState *s, float elapsed, float *time)
{
    if (!s || !s->active || !isfinite(elapsed) || elapsed < s->started) return 0;
    return am_action_time(elapsed - s->started, s->deadline - s->started,
                          s->entry, s->contact, s->rate, s->end, time);
}

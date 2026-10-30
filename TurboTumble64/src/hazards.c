/* hazards.c : v7 course hazards and moving extras
 *   - Canopy River Parkway: coconut-throwing monkeys hiding in the deep grass, a whistling paddle steamboat
 *   - Shellby Shores: sideways-scuttling crabs, the rising and falling tide
 *   - Clover Creek Farm: moles that pop up and bump karts, mooing cows
 *   - every v7 course: "Rotor Rescue" drone that fishes karts out of rivers, the sea and gorges */
#include "common.h"

#define MAX_NUTS 10
typedef struct { bool active; Vector3 p, v; float t; } Coconut;

static float hzTime;
static float spotCd[24], spotPhase[24], spotAnim[24];
static Coconut nuts[MAX_NUTS];
static Vector3 rescueFrom[MAX_RACERS];
static float boatS, boatDir = 1, boatLen, whistleCd, mooCd, splashCd[MAX_RACERS];

static float SStep(float a, float b, float x) { float t = Clamp((x - a)/(b - a), 0, 1); return t*t*(3 - 2*t); }
static bool Quiet(void) { return G.autotest && G.autoSpeed > 1; }
static float HumanDist(Vector3 p)
{
    float best = 1e9f;
    for (int h = 0; h < R.numHumans; h++) { float d = Vector3Distance(p, R.karts[R.humanKart[h]].pos); if (d < best) best = d; }
    return best;
}
static void Sfx3D(SfxId id, Vector3 p, float range, float vol, float pitch)
{
    if (Quiet() || R.numHumans == 0) return;
    float d = HumanDist(p);
    if (d < range) PlaySfx(id, vol*(1.0f - d/range), pitch);
}

static Vector3 SpotPos(int i) { return (Vector3){ T.hazSpot[i].x, 0, T.hazSpot[i].z }; }

void HazardsReset(void)
{
    hzTime = 0;
    memset(nuts, 0, sizeof nuts);
    memset(spotCd, 0, sizeof spotCd);
    memset(spotAnim, 0, sizeof spotAnim);
    T.numHazSpots = 0;
    T.tideOffset = 0;
    whistleCd = 4; mooCd = 3;
    for (int i = 0; i < MAX_RACERS; i++) splashCd[i] = 0;
    const TrackDef *d = T.def;
    if (!d->followTerrain) { T.boatN = 0; return; }
    int step = d->hazard == HZ_MOLES ? 11 : d->hazard == HZ_CRABS ? 26 : 16;
    int side = 1;
    for (int i = 0; i < T.n && T.numHazSpots < 24; i++) {
        const TrackSample *s = &T.s[i];
        if (!(s->zone & ZN_HAZARD) || d->hazard == HZ_NONE) continue;
        if (i % step) continue;
        int k = T.numHazSpots;
        float hw = s->width*0.5f;
        Vector3 p;
        if (d->hazard == HZ_MONKEYS) {
            int sd = (s->zone & ZN_OPEN_L) ? 1 : side; side = -side;
            float off = s->edge[sd > 0 ? 1 : 0] + 1.5f;
            p = Vector3Add(s->pos, Vector3Scale(s->right, sd*off));
            p.y = TerrainY(&T, p.x, p.z);
            T.hazLat[k] = sd*off;
        } else {
            float lat = d->hazard == HZ_CRABS ? 0 : RandF(-(hw - 2.0f), hw - 2.0f);
            if (d->hazard == HZ_MOLES && (T.numHazSpots & 1)) lat = -lat*0.5f;
            p = Vector3Add(s->pos, Vector3Scale(s->right, lat));
            p.y = s->pos.y;
            T.hazLat[k] = d->hazard == HZ_CRABS ? hw*0.85f : lat;
        }
        T.hazSpot[k] = (Vector3){ p.x, (float)i, p.z };
        spotPhase[k] = RandF(0, 6.28f);
        T.numHazSpots++;
    }
    /* steamboat route: the river polyline inside the play area */
    T.boatN = 0;
    if (d->scenery == SCENERY_JUNGLE && d->numRiver > 4) {
        for (int i = 2; i < d->numRiver - 2 && T.boatN < 32; i++) T.boatPath[T.boatN++] = (Vector3){ d->river[i][0], T.waterY, d->river[i][1] };
        boatLen = 0;
        for (int i = 0; i + 1 < T.boatN; i++) boatLen += Vector3Distance(T.boatPath[i], T.boatPath[i + 1]);
        boatS = boatLen*0.35f; boatDir = 1;
    }
}

static Vector3 BoatPose(float s, float *yaw)
{
    float acc = 0;
    for (int i = 0; i + 1 < T.boatN; i++) {
        float L = Vector3Distance(T.boatPath[i], T.boatPath[i + 1]);
        if (s <= acc + L || i + 2 == T.boatN) {
            float t = Clamp((s - acc)/(L > 0 ? L : 1), 0, 1);
            Vector3 a = T.boatPath[i], b = T.boatPath[i + 1];
            *yaw = atan2f(b.x - a.x, b.z - a.z);
            return Vector3Lerp(a, b, t);
        }
        acc += L;
    }
    *yaw = 0;
    return T.boatN ? T.boatPath[0] : (Vector3){ 0 };
}

/* mole height 0..1 over its 3.5 s cycle: hidden 2.0, rise 0.25, up 1.0, sink 0.25 */
static float MoleUp(int i)
{
    float c = fmodf(hzTime + spotPhase[i]*0.557f, 3.5f);
    if (c < 2.0f) return 0;
    if (c < 2.25f) return (c - 2.0f)/0.25f;
    if (c < 3.25f) return 1;
    return 1.0f - (c - 3.25f)/0.25f;
}
static float CrabLat(int i)
{
    return T.hazLat[i]*sinf(hzTime*0.75f + spotPhase[i]);
}
static Vector3 CrabPos(int i)
{
    int seg = (int)T.hazSpot[i].y;
    Vector3 p = TrackPoint(&T, seg, CrabLat(i));
    p.y = T.s[seg].pos.y;
    return p;
}

/* screenshot-tour helper: 0 = the steamboat, 1 = a hazard that is showing right now (raised mole, crab, monkey) */
bool HazardFocus(int which, Vector3 *p, int *seg)
{
    if (which == 0) {
        if (T.boatN < 2) return false;
        float yaw; *p = BoatPose(boatS, &yaw); *seg = 0;
        return true;
    }
    for (int i = 0; i < T.numHazSpots; i++) {
        int sg = (int)T.hazSpot[i].y;
        if (T.def->hazard == HZ_MOLES && MoleUp(i) < 0.97f) continue;
        if (T.def->hazard == HZ_MOLES && hzTime < 4) continue;
        if (T.def->hazard == HZ_MONKEYS && (i < 2 || spotAnim[i] < 0.25f || spotAnim[i] > 0.45f)) continue;
        *p = T.def->hazard == HZ_CRABS ? CrabPos(i) : SpotPos(i);
        if (T.def->hazard != HZ_CRABS) p->y = T.def->hazard == HZ_MONKEYS ? TerrainY(&T, p->x, p->z) : T.s[sg].pos.y;
        *seg = sg;
        return true;
    }
    return false;
}

void HazardStartRescue(int idx, int seg, float lat)
{
    Kart *k = &R.karts[idx];
    if (k->rescueT > 0) return;
    k->rescueT = 2.2f;
    k->rescueSeg = TrackWrap(&T, seg);
    k->rescueLat = lat;
    rescueFrom[idx] = k->pos;
    k->speed = 0; k->vy = 0; k->boostTimer = 0; k->driftState = 0; k->driftCharge = 0; k->sparkLevel = 0; k->spinTimer = 0; k->spinAngle = 0;
    k->statRescues++;
    if (G.autotest) ALog("RESCUE: kart %d (%s) fished out at sample %d (%s)", idx, CHARACTERS[k->charId].name, seg, (T.s[TrackWrap(&T, seg)].zone & ZN_GAP) ? "gorge" : "water");
    if (!Quiet()) {
        if (k->human >= 0) { PlaySfx(SFX_SPLASH, 0.9f, 1.0f); PlaySfx(SFX_RESCUE, 0.7f, 1.0f); }
        else Sfx3D(SFX_SPLASH, k->pos, 50, 0.8f, 1.0f);
    }
    for (int q = 0; q < 16; q++)
        ParticleSpawn(Vector3Add(k->pos, (Vector3){ RandF(-1, 1), 0.3f, RandF(-1, 1) }), (Vector3){ RandF(-4, 4), RandF(4, 9), RandF(-4, 4) }, (Color){ 220, 240, 255, 230 }, 0.7f, 0.35f, 18);
}

/* returns true while the drone carries the kart back (KartUpdate skips its physics) */
bool HazardRescueUpdate(int idx, float dt)
{
    Kart *k = &R.karts[idx];
    if (k->rescueT <= 0) return false;
    k->rescueT -= dt;
    float t = 2.2f - k->rescueT;
    Vector3 to = TrackPoint(&T, k->rescueSeg, k->rescueLat);
    to.y = T.s[k->rescueSeg].pos.y;
    Vector3 from = rescueFrom[idx];
    if (t < 0.6f) k->pos = Vector3Add(from, (Vector3){ 0, t*3.0f, 0 });
    else if (t < 1.6f) {
        float u = SStep(0, 1, (t - 0.6f)/1.0f);
        Vector3 a = Vector3Add(from, (Vector3){ 0, 1.8f, 0 }), b = Vector3Add(to, (Vector3){ 0, 4.0f, 0 });
        k->pos = Vector3Lerp(a, b, u);
        k->pos.y += sinf(u*PI)*5.0f;
        k->heading = LerpAngle(k->heading, atan2f(T.s[k->rescueSeg].fwd.x, T.s[k->rescueSeg].fwd.z), Clamp(4*dt, 0, 1));
    } else k->pos = Vector3Add(to, (Vector3){ 0, 4.0f*Clamp(k->rescueT/0.6f, 0, 1), 0 });
    k->speed = 0; k->vy = 0;
    if (k->rescueT <= 0) {
        k->rescueT = 0;
        k->pos = to;
        k->heading = k->moveYaw = atan2f(T.s[k->rescueSeg].fwd.x, T.s[k->rescueSeg].fwd.z);
        k->grounded = true; k->airTime = 0;
        int dd = k->rescueSeg - k->seg;
        if (dd > T.n/2) dd -= T.n;
        if (dd < -T.n/2) dd += T.n;
        k->segCount += dd;
        k->seg = k->rescueSeg; k->lat = k->rescueLat; k->along = 0;
        k->progress = (float)k->segCount;
        k->invulnTimer = 1.2f;
        k->stuckTimer = 0;
        k->onShortcut = false;
    }
    return true;
}

float HazardKartSpeedMul(int idx)
{
    Kart *k = &R.karts[idx];
    if (!T.def->followTerrain || !k->grounded) return 1.0f;
    const TrackSample *s = &T.s[k->seg];
    if (!(s->zone & ZN_TIDE) || !T.hasWater) return 1.0f;
    float depth = T.waterY + T.tideOffset - k->pos.y;
    if (depth <= 0) return 1.0f;
    if (k->speed > 8 && R.simFrames % 3 == 0)
        ParticleSpawn(Vector3Add(k->pos, (Vector3){ RandF(-0.8f, 0.8f), 0.1f, RandF(-0.8f, 0.8f) }), (Vector3){ RandF(-3, 3), RandF(2, 4), RandF(-3, 3) }, (Color){ 225, 245, 255, 220 }, 0.45f, 0.3f, 14);
    if (splashCd[idx] <= 0 && k->human >= 0) { splashCd[idx] = 1.5f; if (!Quiet()) PlaySfx(SFX_SPLASH, 0.35f, 1.3f); }
    return 1.0f - Clamp(depth*1.6f, 0, 0.42f);
}

float HazardAvoidLane(int idx, float laneGoal)
{
    Kart *k = &R.karts[idx];
    if (!T.def->followTerrain || T.numHazSpots == 0) return laneGoal;
    HazardType hz = T.def->hazard;
    if (hz != HZ_MOLES && hz != HZ_CRABS) return laneGoal;
    if (k->aiSkill < 0.965f) return laneGoal;          /* the less careful CPUs just plough on */
    for (int i = 0; i < T.numHazSpots; i++) {
        int ds = TrackWrap(&T, (int)T.hazSpot[i].y - k->seg);
        if (ds < 2 || ds > 14) continue;
        float hl = hz == HZ_CRABS ? CrabLat(i) : T.hazLat[i];
        if (hz == HZ_MOLES && MoleUp(i) <= 0 && fmodf(hzTime + spotPhase[i]*0.557f, 3.5f) < 1.4f) continue;
        if (fabsf(hl - laneGoal) < 2.6f) laneGoal = hl > laneGoal ? hl - 3.2f : hl + 3.2f;
    }
    float hw = TrackHalfWidth(&T, k->seg);
    return Clamp(laneGoal, -hw + 1.5f, hw - 1.5f);
}

void HazardsUpdate(float dt)
{
    hzTime += dt;
    const TrackDef *d = T.def;
    if (!d->followTerrain) return;
    for (int i = 0; i < MAX_RACERS; i++) if (splashCd[i] > 0) splashCd[i] -= dt;
    if (d->tideAmp > 0) T.tideOffset = d->tideAmp*sinf(hzTime*2*PI/(d->tidePeriod > 0 ? d->tidePeriod : 12));
    bool racing = R.phase == RACE_RUNNING || R.phase == RACE_DONE || R.attract;

    /* falls: gorge, river, lake or sea */
    for (int i = 0; i < R.numKarts; i++) {
        Kart *k = &R.karts[i];
        if (k->rescueT > 0 || k->onShortcut) continue;
        const TrackSample *s = &T.s[k->seg];
        if ((s->zone & ZN_GAP) && k->pos.y < s->pos.y - 2.5f) {
            int b = k->seg; for (int q = 0; q < 60 && (T.s[TrackWrap(&T, b)].zone & (ZN_GAP | ZN_BOOSTFLOOR)); q++) b--;
            HazardStartRescue(i, b - 4, 0);
            continue;
        }
        if (T.hasWater && k->pos.y < T.waterY + T.tideOffset - 0.7f && fabsf(k->lat) > s->width*0.5f + 0.5f) {
            float hw = s->width*0.5f;
            HazardStartRescue(i, k->seg, Clamp(k->lat, -hw*0.4f, hw*0.4f));
        }
    }

    switch (d->hazard) {
    default: break;
    case HZ_MOLES:
        for (int m = 0; m < T.numHazSpots; m++) {
            float up = MoleUp(m);
            if (up > 0.05f && spotAnim[m] <= 0.05f) Sfx3D(SFX_POP, SpotPos(m), 40, 0.5f, RandF(0.9f, 1.2f));
            spotAnim[m] = up;
            if (up < 0.5f || !racing) continue;
            Vector3 mp = SpotPos(m);
            for (int i = 0; i < R.numKarts; i++) {
                Kart *k = &R.karts[i];
                if (k->rescueT > 0 || k->invulnTimer > 0 || !k->grounded) continue;
                float dx = k->pos.x - mp.x, dz = k->pos.z - mp.z;
                if (dx*dx + dz*dz > 1.7f*1.7f) continue;
                k->vy = 6.5f; k->grounded = false; k->airTime = 0; k->pos.y += 0.05f;
                k->speed *= 0.55f; k->invulnTimer = 1.0f; k->squash = 0.4f;
                k->driftState = 0; k->driftCharge = 0; k->sparkLevel = 0;
                k->statHazardHits++;
                if (k->human >= 0 && !Quiet()) PlaySfx(SFX_POP, 0.9f, 0.8f);
                for (int q = 0; q < 10; q++) ParticleSpawn(Vector3Add(mp, (Vector3){ 0, 0.6f, 0 }), (Vector3){ RandF(-4, 4), RandF(3, 7), RandF(-4, 4) }, (Color){ 140, 100, 60, 255 }, 0.6f, 0.35f, 16);
            }
        }
        break;
    case HZ_CRABS:
        if (!racing) break;
        for (int c = 0; c < T.numHazSpots; c++) {
            Vector3 cp = CrabPos(c);
            for (int i = 0; i < R.numKarts; i++) {
                Kart *k = &R.karts[i];
                if (k->rescueT > 0 || k->invulnTimer > 0 || k->spinTimer > 0 || !k->grounded) continue;
                float dx = k->pos.x - cp.x, dz = k->pos.z - cp.z;
                if (dx*dx + dz*dz > 1.6f*1.6f) continue;
                KartHit(i, false);
                k->statHazardHits++;
            }
        }
        break;
    case HZ_MONKEYS:
        for (int m = 0; m < T.numHazSpots; m++) {
            if (spotCd[m] > 0) spotCd[m] -= dt;
            if (spotAnim[m] > 0) spotAnim[m] -= dt;
            if (spotCd[m] > 0 || !racing) continue;
            Vector3 mp = SpotPos(m); mp.y = TerrainY(&T, mp.x, mp.z);
            for (int i = 0; i < R.numKarts; i++) {
                Kart *k = &R.karts[i];
                if (k->rescueT > 0) continue;
                float dist = Vector3Distance(k->pos, mp);
                if (dist > 18 || dist < 4) continue;
                /* aim where the kart will be, with a monkey-sized error */
                float ft = 0.95f;
                Vector3 vel = { sinf(k->moveYaw)*k->speed, 0, cosf(k->moveYaw)*k->speed };
                Vector3 aim = Vector3Add(k->pos, Vector3Scale(vel, ft));
                aim.x += RandF(-2.4f, 2.4f); aim.z += RandF(-2.4f, 2.4f);
                Vector3 from = Vector3Add(mp, (Vector3){ 0, 2.2f, 0 });
                for (int q = 0; q < MAX_NUTS; q++) if (!nuts[q].active) {
                    Coconut *n = &nuts[q];
                    n->active = true; n->p = from; n->t = 0;
                    n->v = (Vector3){ (aim.x - from.x)/ft, (k->pos.y + 0.6f - from.y + 0.5f*24.0f*ft*ft)/ft, (aim.z - from.z)/ft };
                    break;
                }
                spotCd[m] = RandF(2.6f, 4.0f); spotAnim[m] = 0.6f;
                Sfx3D(SFX_MONKEY, mp, 45, 0.7f, RandF(0.9f, 1.15f));
                break;
            }
        }
        for (int q = 0; q < MAX_NUTS; q++) {
            Coconut *n = &nuts[q];
            if (!n->active) continue;
            n->t += dt;
            n->v.y -= 24.0f*dt;
            n->p = Vector3Add(n->p, Vector3Scale(n->v, dt));
            bool done = n->t > 2.5f;
            for (int i = 0; i < R.numKarts && !done; i++) {
                Kart *k = &R.karts[i];
                if (k->rescueT > 0) continue;
                Vector3 c = Vector3Add(k->pos, (Vector3){ 0, 0.7f, 0 });
                if (Vector3Distance(c, n->p) < 1.45f) {
                    if (k->invulnTimer <= 0 && k->spinTimer <= 0) { KartHit(i, false); k->statHazardHits++; }
                    done = true;
                }
            }
            if (!done && n->v.y < 0) {
                int sg; float lat, al, gy;
                TrackLocate(&T, n->p, -1, &sg, &lat, &al, &gy);
                float ground = fabsf(lat) < T.s[sg].width*0.5f + 1 ? gy : TerrainY(&T, n->p.x, n->p.z);
                if (n->p.y < ground + 0.2f) done = true;
            }
            if (done) {
                n->active = false;
                for (int p = 0; p < 8; p++) ParticleSpawn(n->p, (Vector3){ RandF(-4, 4), RandF(2, 6), RandF(-4, 4) }, p & 1 ? (Color){ 110, 70, 40, 255 } : (Color){ 245, 240, 230, 255 }, 0.6f, 0.25f, 16);
            }
        }
        break;
    }

    /* steamboat */
    if (T.boatN > 1) {
        boatS += boatDir*5.5f*dt;
        if (boatS > boatLen - 10) { boatS = boatLen - 10; boatDir = -1; }
        if (boatS < 10) { boatS = 10; boatDir = 1; }
        float yaw; Vector3 bp = BoatPose(boatS, &yaw);
        whistleCd -= dt;
        if (whistleCd <= 0 && R.numHumans > 0 && HumanDist(bp) < 80) {
            whistleCd = RandF(8, 12);
            Sfx3D(SFX_WHISTLE, bp, 110, 0.9f, 1.0f);
            for (int q = 0; q < 10; q++) ParticleSpawn(Vector3Add(bp, (Vector3){ 0, 9.5f, 0 }), (Vector3){ RandF(-1, 1), RandF(4, 7), RandF(-1, 1) }, (Color){ 250, 250, 250, 200 }, 1.2f, 0.9f, -2);
        }
        if (R.simFrames % 10 == 0) for (int st = -1; st <= 1; st += 2) {
            Vector3 sp = { bp.x + cosf(yaw)*st*1.3f + sinf(yaw)*3.0f, bp.y + 8.5f, bp.z - sinf(yaw)*st*1.3f + cosf(yaw)*3.0f };
            ParticleSpawn(sp, (Vector3){ RandF(-0.5f, 0.5f), RandF(2, 3), RandF(-0.5f, 0.5f) }, (Color){ 90, 90, 95, 170 }, 1.4f, 0.8f, -1);
        }
    }
    /* cows */
    if (T.numCows > 0 && R.numHumans > 0) {
        mooCd -= dt;
        if (mooCd <= 0) {
            int best = -1; float bd = 1e9f;
            for (int c = 0; c < T.numCows; c++) { float dd = HumanDist(T.cows[c]); if (dd < bd) { bd = dd; best = c; } }
            if (best >= 0 && bd < 40) { Sfx3D(SFX_MOO, T.cows[best], 55, 1.0f, RandF(0.85f, 1.1f)); mooCd = RandF(5, 9); }
            else mooCd = 1.0f;
        }
    }
}

/* ---------------------------------------------------------------- */
/* drawing (immediate mode, inside the fog shader)                   */
/* ---------------------------------------------------------------- */
static void Push(Vector3 p, float yawRad) { rlPushMatrix(); rlTranslatef(p.x, p.y, p.z); rlRotatef(yawRad*RAD2DEG, 0, 1, 0); }
static void Pop(void) { rlPopMatrix(); }

static void DrawMole(Vector3 p, float up, float yaw)
{
    Push(p, yaw);
    DrawSphereEx((Vector3){ 0, 0.05f, 0 }, 1.0f, 4, 8, (Color){ 120, 84, 52, 255 });          /* dirt mound */
    DrawCylinder((Vector3){ 0, 0.06f, 0 }, 0.75f, 0.75f, 0.06f, 10, (Color){ 40, 26, 16, 255 });      /* hole */
    if (up > 0.02f) {
        float y = -0.9f + up*1.7f;
        DrawSphereEx((Vector3){ 0, y, 0 }, 0.72f, 6, 10, (Color){ 96, 74, 70, 255 });
        DrawSphereEx((Vector3){ 0, y + 0.55f, 0.2f }, 0.5f, 6, 10, (Color){ 112, 88, 82, 255 });
        DrawSphereEx((Vector3){ 0, y + 0.5f, 0.66f }, 0.16f, 4, 6, (Color){ 255, 140, 160, 255 });   /* nose */
        DrawSphereEx((Vector3){ 0.2f, y + 0.72f, 0.56f }, 0.08f, 4, 6, BLACK);
        DrawSphereEx((Vector3){ -0.2f, y + 0.72f, 0.56f }, 0.08f, 4, 6, BLACK);
        DrawCube((Vector3){ 0, y + 0.95f, 0.15f }, 0.9f, 0.18f, 0.9f, (Color){ 255, 200, 40, 255 });  /* little hard hat */
        DrawSphereEx((Vector3){ 0, y + 1.0f, 0.12f }, 0.36f, 4, 8, (Color){ 255, 210, 50, 255 });
        for (int s = -1; s <= 1; s += 2) DrawSphereEx((Vector3){ s*0.55f, y + 0.25f, 0.4f }, 0.2f, 4, 6, (Color){ 255, 190, 190, 255 });   /* paws */
    }
    Pop();
}
static void DrawCrab(Vector3 p, float yaw, float t)
{
    Push(p, yaw);
    float bob = fabsf(sinf(t*10))*0.08f;
    Color red = { 232, 70, 44, 255 }, dark = { 180, 44, 30, 255 };
    DrawSphereEx((Vector3){ 0, 0.55f + bob, 0 }, 0.75f, 6, 10, red);
    DrawCube((Vector3){ 0, 0.4f + bob, 0 }, 1.5f, 0.3f, 1.0f, dark);
    for (int s = -1; s <= 1; s += 2) {
        DrawCylinderEx((Vector3){ s*0.25f, 0.9f + bob, 0.35f }, (Vector3){ s*0.3f, 1.45f + bob, 0.45f }, 0.06f, 0.06f, 4, dark);
        DrawSphereEx((Vector3){ s*0.3f, 1.5f + bob, 0.45f }, 0.16f, 4, 6, WHITE);
        DrawSphereEx((Vector3){ s*0.3f, 1.52f + bob, 0.58f }, 0.07f, 4, 6, BLACK);
        float sn = sinf(t*6 + s)*0.15f;
        DrawSphereEx((Vector3){ s*1.05f, 0.8f + bob + sn, 0.7f }, 0.36f, 5, 8, red);                /* claws */
        DrawCube((Vector3){ s*1.05f, 1.05f + bob + sn, 0.95f }, 0.16f, 0.4f, 0.3f, dark);
        for (int l = 0; l < 3; l++) {
            float z = -0.35f + l*0.3f, w = sinf(t*14 + l*2 + s)*0.15f;
            DrawCylinderEx((Vector3){ s*0.6f, 0.45f + bob, z }, (Vector3){ s*1.1f, 0.05f, z + w }, 0.06f, 0.05f, 4, dark);
        }
    }
    Pop();
}
static void DrawMonkey(Vector3 p, float yaw, float throwA, float t)
{
    Push(p, yaw);
    rlScalef(1.25f, 1.25f, 1.25f);
    float pop = throwA > 0 ? sinf(Clamp(throwA/0.6f, 0, 1)*PI)*1.2f : sinf(t*2.0f)*0.1f;
    Color fur = { 120, 76, 42, 255 }, face = { 236, 196, 150, 255 };
    float y = 0.5f + pop;
    DrawSphereEx((Vector3){ 0, y + 0.5f, 0 }, 0.6f, 6, 10, fur);
    DrawSphereEx((Vector3){ 0, y + 1.35f, 0 }, 0.48f, 6, 10, fur);
    DrawSphereEx((Vector3){ 0, y + 1.3f, 0.32f }, 0.3f, 5, 8, face);
    for (int s = -1; s <= 1; s += 2) {
        DrawSphereEx((Vector3){ s*0.48f, y + 1.45f, 0 }, 0.18f, 4, 6, face);                         /* ears */
        DrawSphereEx((Vector3){ s*0.13f, y + 1.45f, 0.52f }, 0.07f, 4, 6, BLACK);
        float arm = (s > 0 && throwA > 0) ? 1.0f : 0.0f;
        DrawCylinderEx((Vector3){ s*0.5f, y + 0.9f, 0 }, (Vector3){ s*0.75f, y + 0.3f + arm*1.6f, 0.2f + arm*0.3f }, 0.13f, 0.11f, 5, fur);
    }
    DrawCylinderEx((Vector3){ 0, y + 0.2f, -0.5f }, (Vector3){ 0, y + 1.3f, -1.1f }, 0.09f, 0.06f, 4, fur);   /* tail */
    Pop();
}
static void DrawSteamboat(Vector3 p, float yaw, float t)
{
    Push(p, yaw);
    Color white = { 246, 244, 236, 255 }, red = { 200, 46, 40, 255 };
    DrawCube((Vector3){ 0, 0.6f, 0 }, 5.0f, 1.6f, 14.0f, white);
    DrawCube((Vector3){ 0, 0.0f, 0 }, 5.1f, 0.5f, 14.1f, red);
    DrawCube((Vector3){ 0, 1.5f, 7.6f }, 3.0f, 0.2f, 1.6f, white);
    DrawCube((Vector3){ 0, 2.5f, 0.5f }, 4.0f, 2.0f, 8.0f, (Color){ 250, 236, 200, 255 });
    DrawCube((Vector3){ 0, 3.6f, 0.5f }, 4.6f, 0.25f, 8.8f, red);
    DrawCube((Vector3){ 0, 4.6f, 1.5f }, 2.6f, 1.8f, 3.4f, white);
    DrawCube((Vector3){ 0, 5.6f, 1.5f }, 3.0f, 0.2f, 3.8f, red);
    for (int k = 0; k < 4; k++) DrawCube((Vector3){ 2.02f, 2.6f, -2.2f + k*1.6f }, 0.05f, 0.8f, 0.9f, (Color){ 110, 190, 240, 255 });
    for (int k = 0; k < 4; k++) DrawCube((Vector3){ -2.02f, 2.6f, -2.2f + k*1.6f }, 0.05f, 0.8f, 0.9f, (Color){ 110, 190, 240, 255 });
    for (int s = -1; s <= 1; s += 2) {
        DrawCylinder((Vector3){ s*1.3f, 3.7f, 3.0f }, 0.45f, 0.55f, 4.6f, 8, (Color){ 40, 40, 44, 255 });
        DrawCylinder((Vector3){ s*1.3f, 8.2f, 3.0f }, 0.7f, 0.5f, 0.4f, 8, (Color){ 230, 190, 60, 255 });
    }
    /* stern paddle wheel */
    rlPushMatrix();
    rlTranslatef(0, 1.6f, -8.2f);
    rlRotatef(t*120.0f, 1, 0, 0);
    for (int k = 0; k < 6; k++) {
        rlPushMatrix(); rlRotatef(k*30.0f, 1, 0, 0);
        DrawCube((Vector3){ 0, 0, 0 }, 4.2f, 3.6f, 0.25f, red);
        rlPopMatrix();
    }
    rlPopMatrix();
    DrawCylinderEx((Vector3){ -2.2f, 1.6f, -8.2f }, (Vector3){ 2.2f, 1.6f, -8.2f }, 0.3f, 0.3f, 6, (Color){ 60, 60, 60, 255 });
    Pop();
}
static void DrawDrone(Vector3 p, float t)
{
    Push(p, t*0.7f);
    DrawCube((Vector3){ 0, 0, 0 }, 1.4f, 0.5f, 1.4f, (Color){ 255, 205, 40, 255 });
    DrawSphereEx((Vector3){ 0, 0.3f, 0 }, 0.45f, 5, 8, (Color){ 220, 40, 40, 255 });
    DrawSphereEx((Vector3){ 0, 0.35f, 0.38f }, 0.2f, 4, 6, (Color){ 140, 220, 255, 255 });
    for (int a = 0; a < 4; a++) {
        float an = a*PI*0.5f + PI*0.25f;
        Vector3 arm = { cosf(an)*1.3f, 0.1f, sinf(an)*1.3f };
        DrawCylinderEx((Vector3){ 0, 0.1f, 0 }, arm, 0.07f, 0.07f, 4, (Color){ 60, 60, 70, 255 });
        rlPushMatrix(); rlTranslatef(arm.x, 0.3f, arm.z); rlRotatef(t*1500.0f + a*45, 0, 1, 0);
        DrawCube((Vector3){ 0, 0, 0 }, 1.5f, 0.04f, 0.18f, (Color){ 230, 230, 235, 200 });
        rlPopMatrix();
    }
    Pop();
}

void HazardsDraw(void)
{
    const TrackDef *d = T.def;
    if (!d->followTerrain) return;
    Vector3 cam = G.curCam.position;
    for (int i = 0; i < T.numHazSpots; i++) {
        Vector3 p = SpotPos(i);
        if (Vector3Distance(p, cam) > 160) continue;
        int seg = (int)T.hazSpot[i].y;
        float yaw = atan2f(T.s[seg].fwd.x, T.s[seg].fwd.z);
        if (d->hazard == HZ_MOLES) { p.y = T.s[seg].pos.y; DrawMole(p, MoleUp(i), yaw + PI); }
        else if (d->hazard == HZ_CRABS) { Vector3 c = CrabPos(i); DrawCrab(c, yaw + PI*0.5f, hzTime + i); }
        else if (d->hazard == HZ_MONKEYS) {
            p.y = TerrainY(&T, p.x, p.z) - 0.3f;
            float face = atan2f(T.s[seg].pos.x - p.x, T.s[seg].pos.z - p.z);
            DrawMonkey(p, face, spotAnim[i], hzTime + i);
        }
    }
    for (int q = 0; q < MAX_NUTS; q++) if (nuts[q].active) {
        DrawSphereEx(nuts[q].p, 0.42f, 5, 8, (Color){ 120, 78, 44, 255 });
        DrawSphereEx(Vector3Add(nuts[q].p, (Vector3){ 0.12f, 0.22f, 0.2f }), 0.12f, 3, 5, (Color){ 70, 46, 26, 255 });
    }
    if (T.boatN > 1) { float yaw; Vector3 bp = BoatPose(boatS, &yaw); if (boatDir < 0) yaw += PI; bp.y += 0.1f + sinf(hzTime*1.3f)*0.08f; DrawSteamboat(bp, yaw, hzTime); }
    for (int i = 0; i < R.numKarts; i++) {
        Kart *k = &R.karts[i];
        if (k->rescueT <= 0) continue;
        float t = 2.2f - k->rescueT;
        Vector3 dp = Vector3Add(k->pos, (Vector3){ 0, 3.6f + (t < 0.4f ? (0.4f - t)*14.0f : 0) + (k->rescueT < 0.3f ? (0.3f - k->rescueT)*20.0f : 0), 0 });
        DrawDrone(dp, hzTime);
        DrawCylinderEx(Vector3Add(dp, (Vector3){ 0, -0.2f, 0 }), Vector3Add(k->pos, (Vector3){ 0, 1.6f, 0 }), 0.04f, 0.04f, 3, (Color){ 40, 40, 40, 255 });
    }
}

void HazardsUnloadModels(void) { }

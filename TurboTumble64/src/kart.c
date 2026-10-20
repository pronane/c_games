/* kart.c : arcade kart physics (accel, steering, hop + drift + mini-turbo,
 * off-road, walls, jumps) and the CPU driver logic (waypoints, rubber-banding,
 * drifting, item use). */
#include "common.h"

void RaceOnLap(int idx);   /* race.c */

static const float CC_SPEED[3] = { 0.80f, 1.0f, 1.12f };

#define HOP_VELOCITY   5.2f
#define GRAVITY        30.0f
#define BLUE_CHARGE    0.85f
#define ORANGE_CHARGE  1.9f

float KartTopSpeed(const Kart *k)
{
    const CharacterDef *cd = &CHARACTERS[k->charId];
    return (25.5f + cd->topSpeed*1.15f)*CC_SPEED[G.settings.cc];
}

static bool NearHuman(Vector3 p, float range, float *vol)
{
    float best = 1e9f;
    for (int h = 0; h < R.numHumans; h++) {
        float d = Vector3Distance(p, R.karts[R.humanKart[h]].pos);
        if (d < best) best = d;
    }
    if (R.attract) best = Vector3Distance(p, R.cam[0].target);
    if (best > range) return false;
    *vol = 1.0f - best/range;
    return true;
}

static void KartSfx(const Kart *k, SfxId id, float vol, float pitch)
{
    float v;
    if (G.autotest && G.autoSpeed > 1) return;
    if (k->human >= 0 && !R.attract) { PlaySfx(id, vol, pitch); return; }
    if (NearHuman(k->pos, 45.0f, &v)) PlaySfx(id, vol*v*0.8f, pitch);
}

void KartInit(Kart *k, int charId, int human, int gridSlot)
{
    memset(k, 0, sizeof(*k));
    k->charId = charId;
    k->human = human;
    k->autopilot = (human < 0);
    k->scale = 1.0f;
    int row = gridSlot/2, col = gridSlot % 2;
    float back = 6.0f + row*6.0f + col*3.0f;
    int sb = (int)(back/T.spacing);
    int seg = TrackWrap(&T, -sb);
    float lat = (col == 0 ? -1.0f : 1.0f)*T.s[seg].width*0.22f;
    k->pos = TrackPoint(&T, seg, lat);
    k->heading = k->moveYaw = atan2f(T.s[seg].fwd.x, T.s[seg].fwd.z);
    k->seg = seg;
    k->segCount = seg - T.n;
    k->progress = (float)k->segCount;
    k->lat = lat;
    k->grounded = true;
    k->groundY = k->pos.y;
    k->aiLane = k->aiLaneTarget = lat;
    k->aiSkill = RandF(0.955f, 1.0f);
    k->aiLaneTimer = RandF(1, 3);
    k->startBoostWindow = -1;
    k->bestLap = 0;
}

static void Boost(Kart *k, float time, float power)
{
    if (k->boostTimer < time) k->boostTimer = time;
    if (k->boostPower < power || k->boostTimer <= 0) k->boostPower = power;
    k->statBoosts++;
    KartSfx(k, SFX_BOOST, 0.8f, 1.0f);
}

void KartHit(int idx, bool bigHit)
{
    Kart *k = &R.karts[idx];
    if (k->invulnTimer > 0 || k->discoTimer > 0) return;
    k->spinTimer = bigHit ? 1.5f : 1.0f;
    k->speed *= bigHit ? 0.25f : 0.45f;
    if (bigHit && k->grounded) { k->vy = 7.0f; k->grounded = false; }
    k->invulnTimer = k->spinTimer + 0.6f;
    k->driftState = 0; k->driftCharge = 0; k->sparkLevel = 0;
    k->boostTimer = 0;
    k->statHits++;
    KartSfx(k, bigHit ? SFX_HIT : SFX_SPIN, 0.9f, 1.0f);
    if (k->human >= 0 && !(G.autotest && G.autoSpeed > 1)) PlayVoice(k->charId, 1);
    for (int i = 0; i < 14; i++)
        ParticleSpawn(Vector3Add(k->pos, (Vector3){ 0, 1.2f, 0 }), (Vector3){ RandF(-6, 6), RandF(3, 9), RandF(-6, 6) },
                      (Color){ 255, 230, 60, 255 }, 0.7f, 0.35f, 18.0f);
    if (k->human >= 0) R.shake[k->human] = 0.5f;
}

static float RubberBand(const Kart *k)
{
    if (k->human >= 0 || R.numHumans == 0) return 1.0f;
    float best = -1e9f;
    for (int h = 0; h < R.numHumans; h++) {
        const Kart *hk = &R.karts[R.humanKart[h]];
        if (hk->progress > best) best = hk->progress;
    }
    float diff = (k->progress - best)/(float)T.n;   /* laps ahead (+) or behind (-) */
    float f = 1.0f - Clamp(diff/0.14f, -1.0f, 1.0f)*0.085f;
    if (diff < -0.3f) f += 0.05f;
    return f*k->aiSkill;
}

void KartUpdate(int idx, const KartInput *in, float dt)
{
    Kart *k = &R.karts[idx];
    const CharacterDef *cd = &CHARACTERS[k->charId];
    float top = KartTopSpeed(k);
    float acc = 8.0f + cd->accel*3.4f;
    float turn = 1.82f + cd->handling*0.15f;
    float grip = T.def->grip;
    bool canDrive = (R.phase == RACE_RUNNING || R.phase == RACE_DONE || R.attract);

    /* timers */
    if (k->bumpCooldown > 0) k->bumpCooldown -= dt;
    if (k->invulnTimer > 0) k->invulnTimer -= dt;
    if (k->discoTimer > 0) k->discoTimer -= dt;
    if (k->shrinkTimer > 0) k->shrinkTimer -= dt;
    if (k->boostTimer > 0) { k->boostTimer -= dt; if (k->boostTimer <= 0) k->boostPower = 0; }
    if (k->turboFlash > 0) k->turboFlash -= dt;
    if (k->itemFlash > 0) k->itemFlash -= dt;
    k->scale = Approach(k->scale, k->shrinkTimer > 0 ? 0.5f : 1.0f, 2.5f*dt);
    k->squash = Approach(k->squash, 0, 2.5f*dt);

    if (k->autopilot && k->human < 0) top *= RubberBand(k);
    if (k->autopilot && k->human >= 0) top *= 0.97f;    /* autopilot after finishing / autotest */
    if (G.autotest && R.timeTrial && k->lap == 2) top *= 0.9f;   /* test harness only: let the ghost pull ahead for the screenshot */

    float hw = TrackHalfWidth(&T, k->seg);
    bool offroad = k->onShortcut ? !T.def->scIsRoad : fabsf(k->lat) > hw + 1.0f;
    k->offroad = offroad ? 1.0f : 0.0f;
    float speedMul = 1.0f;
    if (offroad && k->boostTimer <= 0 && k->discoTimer <= 0) speedMul *= k->onShortcut ? 0.72f : 0.52f;   /* shortcut trail = packed dirt */
    if (k->shrinkTimer > 0) speedMul *= 0.72f;
    if (k->discoTimer > 0) speedMul *= 1.12f;
    if (k->boostTimer > 0) speedMul *= 1.0f + k->boostPower;
    float topNow = top*speedMul;

    if (k->spinTimer > 0) {
        k->spinTimer -= dt;
        k->spinAngle += dt*(k->spinTimer > 0.4f ? 15.0f : 8.0f);
        k->speed = Approach(k->speed, 0, 22.0f*dt);
        k->steer = Approach(k->steer, 0, 5*dt);
        if (k->spinTimer <= 0) { k->spinAngle = 0; }
    } else if (!canDrive) {
        k->speed = 0;
        k->steer = Approach(k->steer, in->steer, 7*dt);
    } else {
        /* throttle */
        if (k->boostTimer > 0) {
            k->speed = Approach(k->speed, topNow, 60.0f*dt);
        } else if (in->accel) {
            if (k->speed < topNow) {
                float a = acc*(1.25f - 0.9f*Clamp(k->speed/top, 0, 1));
                if (k->speed < 0) a = 30.0f;
                k->speed += a*dt;
                if (k->speed > topNow) k->speed = topNow;
            } else {
                k->speed = Approach(k->speed, topNow, 20.0f*dt);
            }
        } else if (in->brake) {
            if (k->speed > 0.5f) k->speed -= 34.0f*dt;
            else k->speed = Approach(k->speed, -9.0f, 14.0f*dt);
        } else {
            k->speed = Approach(k->speed, 0, 8.0f*dt);
            if (k->speed > topNow) k->speed = Approach(k->speed, topNow, 20.0f*dt);
        }

        /* steering */
        /* snappy: the stick is followed within ~80 ms, full lock is reached quickly at any speed */
        k->steer = Approach(k->steer, in->steer, 12.0f*dt);
        float sf = Clamp(fabsf(k->speed)/7.0f, 0, 1);
        float hiDamp = 1.0f - 0.12f*Clamp(k->speed/top, 0, 1);
        float yawRate;
        if (k->driftState == 2) {
            float s = k->steer*k->driftDir;            /* + = steering into the drift */
            yawRate = k->driftDir*turn*(0.7f + 0.5f*s);       /* counter-steer opens the drift right up, steering in tightens it */
            float charge = 0.75f + 0.9f*fmaxf(s, 0.0f);
            /* wiggle bonus: flicking the stick back and forth charges faster (like the classic) */
            float sg = in->steer > 0.3f ? 1.0f : (in->steer < -0.3f ? -1.0f : 0.0f);
            if (sg != 0 && sg != k->lastSteerSign) { k->driftCharge += 0.18f; k->lastSteerSign = sg; }
            k->driftCharge += charge*dt;
            int lvl = k->driftCharge >= ORANGE_CHARGE ? 2 : (k->driftCharge >= BLUE_CHARGE ? 1 : 0);
            if (lvl > k->sparkLevel) KartSfx(k, SFX_SPARK, 0.6f, lvl == 2 ? 1.3f : 1.0f);
            k->sparkLevel = lvl;
            k->visYaw = Approach(k->visYaw, k->driftDir*(-0.46f - 0.14f*s), 5.0f*dt);
        } else {
            yawRate = k->steer*turn*sf*hiDamp*(k->speed < 0 ? -1.0f : 1.0f);
            k->visYaw = Approach(k->visYaw, 0, 3.0f*dt);
        }
        if (!k->grounded) yawRate *= 0.6f;
        if (k->human >= 0) yawRate *= 1.0f;
        k->heading = WrapAngle(k->heading - yawRate*dt);

        /* hop / drift state machine */
        if (in->hopPressed && k->grounded && k->driftState == 0) {
            k->vy = HOP_VELOCITY;
            k->grounded = false;
            k->pos.y += 0.02f;
            k->driftState = 1;
            KartSfx(k, SFX_HOP, 0.4f, 1.0f);
        }
        if (k->driftState == 2) {
            if (!in->hop || k->speed < 8.0f) {
                /* mini-turbo: blue = short kick, orange = long strong one */
                if (k->sparkLevel >= 1 && k->grounded) {
                    bool big = k->sparkLevel == 2;
                    Boost(k, big ? 1.3f : 0.75f, big ? 0.42f : 0.32f);
                    k->speed += big ? 4.0f : 2.5f;
                    k->turboFlash = big ? 0.45f : 0.3f;
                    k->lastTurboLevel = k->sparkLevel;
                    k->statMiniTurbos[k->sparkLevel]++;
                    if (k->human >= 0) R.shake[k->human] = fmaxf(R.shake[k->human], big ? 0.18f : 0.1f);
                    float ch = cosf(k->heading), sh = sinf(k->heading);
                    Color fc = big ? (Color){ 255, 150, 40, 255 } : (Color){ 90, 170, 255, 255 };
                    for (int q = 0; q < (big ? 16 : 10); q++) {
                        float sx = (q & 1) ? 0.3f : -0.3f;
                        Vector3 ep = { k->pos.x + sx*ch - 1.45f*sh, k->pos.y + 0.86f, k->pos.z - sx*sh - 1.45f*ch };
                        ParticleSpawnEx(ep, (Vector3){ -sh*RandF(6, 12) + RandF(-2, 2), RandF(0, 3), -ch*RandF(6, 12) + RandF(-2, 2) }, fc, RandF(0.2f, 0.35f), RandF(0.25f, 0.4f), -3, true);
                    }
                }
                if (k->sparkLevel == 2 && k->human >= 0 && !(G.autotest && G.autoSpeed > 1)) PlayVoice(k->charId, 0);
                k->driftState = 0; k->driftCharge = 0; k->sparkLevel = 0;
            }
        }
    }

    /* grip: velocity direction lags the heading (more on ice / when drifting) */
    float g = grip*grip*(k->driftState == 2 ? 9.0f : 14.0f);
    if (!k->grounded) g *= 0.3f;
    if (k->driftState != 2) g *= 1.2f;   /* tighter normal grip: the kart goes where it points */
    k->moveYaw = LerpAngle(k->moveYaw, k->heading, Clamp(g*dt, 0, 1));

    /* integrate */
    Vector3 dir = { sinf(k->moveYaw), 0, cosf(k->moveYaw) };
    Vector3 oldPos = k->pos;
    k->pos.x += dir.x*k->speed*dt;
    k->pos.z += dir.z*k->speed*dt;
    if (k->driftState == 2) {
        Vector3 rv = { -cosf(k->heading), 0, sinf(k->heading) };
        float slide = -k->driftDir*k->speed*0.07f*dt;
        k->pos.x += rv.x*slide; k->pos.z += rv.z*slide;
    }

    int seg; float lat, along, gy;
    TrackLocate(&T, k->pos, k->seg, &seg, &lat, &along, &gy);
    float lim = TrackWallLimit(&T, seg, lat) + (1.0f - k->scale)*0.5f;
    bool mainOk = fabsf(lat) <= lim;
    int sIdx; float sLat, sAl, sGy;
    bool inSc = TrackShortcutLocate(&T, k->pos, &sIdx, &sLat, &sAl, &sGy);
    bool wasSc = k->onShortcut;
    bool useSc = false;            /* resolve against the shortcut corridor */
    if (mainOk) {
        k->onShortcut = false;
    } else if (inSc) {
        k->onShortcut = true;
    } else if (k->onShortcut && T.scN > 1) {
        useSc = true;              /* hit the shortcut's fence: clamp to it */
    }
    if (k->onShortcut || useSc) {
        if (useSc) {
            float sl = T.scHalf - 0.6f;
            float sgn = sLat > 0 ? 1.0f : -1.0f;
            if (fabsf(sLat) > sl) {
                Vector3 n = Vector3Scale(T.sc[sIdx].right, sgn);
                float push = fabsf(sLat) - sl;
                k->pos.x -= n.x*push; k->pos.z -= n.z*push;
                float impact = dir.x*n.x + dir.z*n.z;
                if (impact > 0 && k->speed > 0) {
                    Vector3 nd = { dir.x - n.x*impact*1.5f, 0, dir.z - n.z*impact*1.5f };
                    k->moveYaw = atan2f(nd.x, nd.z);
                    k->heading = LerpAngle(k->heading, k->moveYaw, 0.5f);
                    k->speed *= 1.0f - 0.5f*impact;
                    if (impact > 0.2f && k->bumpCooldown <= 0) { k->bumpCooldown = 0.35f; k->statBumps++; KartSfx(k, SFX_BUMP, 0.6f, 1.1f); }
                }
            }
            /* past either end cap: nudge back */
            if (sIdx == 0 && sAl <= 0) { k->pos = Vector3Add(k->pos, Vector3Scale(T.sc[0].fwd, 0.2f)); }
            if (sIdx >= T.scN - 2 && sAl >= 1) { k->pos = Vector3Add(k->pos, Vector3Scale(T.sc[0].fwd, -0.2f)); }
            TrackShortcutLocate(&T, k->pos, &sIdx, &sLat, &sAl, &sGy);
            k->onShortcut = true;
        }
        gy = sGy;
        k->scIdx = sIdx;
        seg = TrackShortcutMainSeg(&T, sIdx, sAl);
        along = 0;
        lat = sLat;
    }
    if (wasSc && !k->onShortcut && k->scIdx > T.scN*2/3) {
        k->shortcutsTaken++;
        if (G.autotest) ALog("SHORTCUT: kart %d (%s) completed the shortcut (lap %d)", idx, CHARACTERS[k->charId].name, k->lap + 1);
    }

    /* walls */
    if (!k->onShortcut && fabsf(lat) > lim) {
        float sgn = lat > 0 ? 1.0f : -1.0f;
        Vector3 r = T.s[seg].right;
        Vector3 n = Vector3Scale(r, sgn);
        float push = fabsf(lat) - lim;
        k->pos.x -= n.x*push; k->pos.z -= n.z*push;
        lat = sgn*lim;
        float impact = dir.x*n.x + dir.z*n.z;
        if (impact > 0 && k->speed > 0) {
            Vector3 nd = { dir.x - n.x*impact*1.5f, 0, dir.z - n.z*impact*1.5f };
            float ny = atan2f(nd.x, nd.z);
            k->moveYaw = ny;
            k->heading = LerpAngle(k->heading, ny, 0.5f);
            k->speed *= 1.0f - 0.55f*impact;
            if (impact > 0.2f && k->bumpCooldown <= 0) {
                k->bumpCooldown = 0.35f;
                k->statBumps++;
                KartSfx(k, SFX_BUMP, 0.5f + impact*0.5f, 1.0f);
                for (int i = 0; i < 6; i++)
                    ParticleSpawn(Vector3Add(k->pos, Vector3Add(Vector3Scale(n, 0.9f), (Vector3){ 0, 0.6f, 0 })),
                                  (Vector3){ RandF(-3, 3), RandF(2, 5), RandF(-3, 3) }, (Color){ 255, 240, 160, 255 }, 0.35f, 0.25f, 12);
                if (k->human >= 0) R.shake[k->human] = 0.25f*impact;
            }
        }
    }

    /* vertical: follow the road, fly off ramps */
    k->groundY = gy;
    if (!k->grounded) {
        k->vy -= GRAVITY*dt;
        k->pos.y += k->vy*dt;
        k->airTime += dt;
        if (k->pos.y <= gy) {
            if (k->vy < -7.0f) k->squash = Clamp(-k->vy*0.03f, 0, 0.5f);
            /* landing a real jump (bump / ramp, not a drift hop) gives a tiny boost */
            if (k->airTime > 0.42f && k->spinTimer <= 0 && canDrive) {
                Boost(k, 0.3f, 0.14f);
                k->statJumps++;
                for (int i = 0; i < 8; i++)
                    ParticleSpawn((Vector3){ k->pos.x + RandF(-1, 1), gy + 0.2f, k->pos.z + RandF(-1, 1) },
                                  (Vector3){ RandF(-4, 4), RandF(1, 3), RandF(-4, 4) }, (Color){ 240, 230, 200, 220 }, 0.4f, 0.35f, 6);
            }
            k->airTime = 0;
            k->pos.y = gy;
            k->vy = 0;
            k->grounded = true;
            if (k->driftState == 1) {
                if (in->hop && fabsf(in->steer) > 0.25f && k->speed > 11.0f && canDrive && k->spinTimer <= 0) {
                    k->driftState = 2;
                    k->driftDir = in->steer > 0 ? 1 : -1;
                    k->driftCharge = 0;
                    k->sparkLevel = 0;
                    k->lastSteerSign = (float)k->driftDir;
                } else {
                    k->driftState = 0;
                }
            }
        }
    } else {
        float dy = gy - k->pos.y;
        float newVy = dy/dt;
        /* lift off when the ground falls away faster than gravity could pull us down
           (ramp lips and mogul crests), otherwise stick to the surface */
        if (dy < -0.3f || (k->vy - newVy > GRAVITY*dt*1.15f && k->vy > 1.0f)) {
            k->grounded = false;
            k->airTime = 0;
            if (k->vy < 0) k->vy = 0;
            if (!k->onShortcut && T.s[seg].bump) k->statBumpAirs++;
        } else {
            k->vy = Clamp(newVy, -20.0f, 14.0f);
            k->pos.y = gy;
        }
    }
    (void)oldPos;

    /* lap progress */
    int d = seg - k->seg;
    if (d > T.n/2) d -= T.n;
    if (d < -T.n/2) d += T.n;
    if (d > 24) d = 24;            /* checkpoint guard: no teleport-skips */
    if (d < -24) d = -24;
    k->segCount += d;
    k->seg = seg;
    k->lat = lat;
    k->along = along;
    k->progress = k->segCount + along;
    while (k->segCount >= (k->lap + 1)*T.n && k->lap < 99) RaceOnLap(idx);

    /* stuck recovery */
    if (k->autopilot && canDrive && k->spinTimer <= 0) {
        if (fabsf(k->speed) < 2.5f) k->stuckTimer += dt; else k->stuckTimer = Approach(k->stuckTimer, 0, dt);
        if (k->stuckTimer > 3.5f) {
            int ns = TrackWrap(&T, seg + 2);
            k->pos = TrackPoint(&T, ns, 0);
            k->heading = k->moveYaw = atan2f(T.s[ns].fwd.x, T.s[ns].fwd.z);
            k->speed = 5; k->stuckTimer = 0;
            k->seg = ns; k->segCount += 2; k->onShortcut = false;
        }
    }

    /* visuals */
    k->wheelRot += k->speed*dt/0.34f;
    float tiltT = -k->steer*0.07f*Clamp(k->speed/top, 0, 1) + (k->driftState == 2 ? -k->driftDir*0.08f : 0);
    k->tilt = Approach(k->tilt, tiltT, 1.2f*dt);

    /* particles */
    float fwdx = sinf(k->heading), fwdz = cosf(k->heading);
    Vector3 rearL = { k->pos.x - fwdx*1.0f - cosf(k->heading)*0.75f*k->scale, k->pos.y + 0.2f, k->pos.z - fwdz*1.0f + sinf(k->heading)*0.75f*k->scale };
    if (k->driftState == 2 && k->grounded) {
        /* drift sparks from both rear tyres: white -> BLUE -> ORANGE as the mini-turbo charges */
        float vy = k->heading + k->visYaw, ch = cosf(vy), sh = sinf(vy);
        float hx = 0.74f*k->scale, bz = -0.95f*k->scale;
        int lvl = k->sparkLevel;
        Color sc = lvl == 2 ? (Color){ 255, 140, 25, 255 } : (Color){ 60, 150, 255, 255 };
        Color core = lvl == 2 ? (Color){ 255, 220, 120, 255 } : (Color){ 170, 220, 255, 255 };
        for (int w = -1; w <= 1; w += 2) {
            Vector3 wp = { k->pos.x + w*hx*ch + bz*sh, k->pos.y + 0.1f, k->pos.z - w*hx*sh + bz*ch };
            Vector3 out = { w*ch*2.0f, 0, -w*sh*2.0f };
            if (lvl == 0) {
                if (R.simFrames % 2 == 0)
                    ParticleSpawnEx(wp, (Vector3){ -sh*RandF(2, 5) + out.x*RandF(0, 1), RandF(1, 3), -ch*RandF(2, 5) + out.z*RandF(0, 1) }, (Color){ 255, 245, 200, 230 }, RandF(0.1f, 0.18f), 0.1f, 18, true);
                if (R.simFrames % 4 == 0)
                    ParticleSpawn(wp, (Vector3){ -sh*2 + RandF(-1, 1), RandF(0.5f, 1.5f), -ch*2 + RandF(-1, 1) }, (Color){ 235, 235, 235, 150 }, 0.35f, 0.28f, -1);
            } else {
                for (int q = 0; q < (lvl == 2 ? 3 : 2); q++)
                    ParticleSpawnEx(wp, (Vector3){ -sh*RandF(3, 8) + out.x*RandF(-0.5f, 1.5f), RandF(2, 6), -ch*RandF(3, 8) + out.z*RandF(-0.5f, 1.5f) },
                                    sc, RandF(0.16f, 0.3f), RandF(0.12f, 0.2f), 22, true);
                ParticleSpawnEx(wp, (Vector3){ 0, 0, 0 }, core, 0.05f, lvl == 2 ? 0.55f : 0.45f, 0, true);
            }
        }
    }
    if (k->boostTimer > 0) {
        /* exhaust flames (bigger right after a mini-turbo) */
        float ch = cosf(k->heading), sh = sinf(k->heading);
        float big = k->turboFlash > 0 ? 1.7f : 1.0f;
        for (int e = -1; e <= 1; e += 2) {
            if (R.simFrames % 2 && big < 1.5f) continue;
            float sx = e*0.3f*k->scale;
            Vector3 ep = { k->pos.x + sx*ch - 1.5f*k->scale*sh, k->pos.y + 0.86f*k->scale, k->pos.z - sx*sh - 1.5f*k->scale*ch };
            Color fc = (R.simFrames % 3) ? (Color){ 255, 200, 50, 255 } : (Color){ 255, 90, 30, 255 };
            if (k->turboFlash > 0 && k->lastTurboLevel == 1 && (R.simFrames & 1)) fc = (Color){ 90, 170, 255, 255 };
            ParticleSpawnEx(ep, (Vector3){ -sh*7 + RandF(-1, 1), RandF(0, 1.5f), -ch*7 + RandF(-1, 1) }, fc, RandF(0.12f, 0.2f), 0.32f*big, -2, true);
        }
    }
    if (offroad && k->speed > 6 && k->grounded && R.simFrames % 3 == 0) {
        SceneryType sc = T.def->scenery;
        Color dc = sc == SCENERY_SNOW ? (Color){ 250, 250, 255, 220 } : (sc == SCENERY_DESERT || sc == SCENERY_BEACH) ? (Color){ 230, 200, 140, 220 } :
                   sc == SCENERY_SPOOKY ? (Color){ 90, 95, 80, 220 } : (Color){ 110, 170, 70, 220 };
        ParticleSpawn(rearL, (Vector3){ RandF(-1.5f, 1.5f), RandF(1, 3), RandF(-1.5f, 1.5f) }, dc, 0.45f, 0.4f, 8);
    }
    if (k->discoTimer > 0 && R.simFrames % 2 == 0) {
        ParticleSpawn(Vector3Add(k->pos, (Vector3){ RandF(-1, 1), RandF(0.5f, 2), RandF(-1, 1) }), (Vector3){ 0, 2, 0 },
                      HueColor((float)(R.simFrames*13 % 360), 0.7f, 1.0f), 0.5f, 0.3f, 0);
    }
}

void KartsCollide(void)
{
    for (int a = 0; a < R.numKarts; a++) {
        for (int b = a + 1; b < R.numKarts; b++) {
            Kart *ka = &R.karts[a], *kb = &R.karts[b];
            float dx = kb->pos.x - ka->pos.x, dz = kb->pos.z - ka->pos.z;
            float r = 0.95f*(ka->scale + kb->scale);
            float d2 = dx*dx + dz*dz;
            if (d2 > r*r || fabsf(ka->pos.y - kb->pos.y) > 1.6f) continue;
            float d = sqrtf(d2); if (d < 0.001f) { d = 0.001f; dx = 0.001f; }
            /* disco ball and squish interactions */
            if (ka->discoTimer > 0 && kb->discoTimer <= 0) { KartHit(b, true); continue; }
            if (kb->discoTimer > 0 && ka->discoTimer <= 0) { KartHit(a, true); continue; }
            if (ka->shrinkTimer > 0 && kb->shrinkTimer <= 0 && ka->invulnTimer <= 0) { KartHit(a, false); ka->squash = 1.0f; KartSfx(ka, SFX_SQUISH, 0.8f, 1); continue; }
            if (kb->shrinkTimer > 0 && ka->shrinkTimer <= 0 && kb->invulnTimer <= 0) { KartHit(b, false); kb->squash = 1.0f; KartSfx(kb, SFX_SQUISH, 0.8f, 1); continue; }
            float ma = CHARACTERS[ka->charId].mass*ka->scale, mb = CHARACTERS[kb->charId].mass*kb->scale;
            float pa = mb/(ma + mb);
            float pen = r - d;
            float nx = dx/d, nz = dz/d;
            ka->pos.x -= nx*pen*pa*1.1f; ka->pos.z -= nz*pen*pa*1.1f;
            kb->pos.x += nx*pen*(1 - pa)*1.1f; kb->pos.z += nz*pen*(1 - pa)*1.1f;
            ka->speed *= 1.0f - 0.08f*pa;
            kb->speed *= 1.0f - 0.08f*(1 - pa);
            if ((ka->human >= 0 || kb->human >= 0) && ka->bumpCooldown <= 0 && kb->bumpCooldown <= 0) {
                ka->bumpCooldown = kb->bumpCooldown = 0.4f;
                KartSfx(ka->human >= 0 ? ka : kb, SFX_BUMP, 0.6f, 1.2f);
            }
        }
    }
}

/* ------------------------------------------------------------------ */
/* CPU driver                                                           */
/* ------------------------------------------------------------------ */
static float CurvAhead(int seg, int from, int count)
{
    float c = 0;
    for (int i = from; i < from + count; i++) c += T.s[TrackWrap(&T, seg + i)].curv;
    return c/count;
}

void KartAIInput(int idx, KartInput *in, float dt)
{
    Kart *k = &R.karts[idx];
    memset(in, 0, sizeof(*in));
    float hw = TrackHalfWidth(&T, k->seg);

    /* lane choice: wander a little, cut to the inside of bends */
    k->aiLaneTimer -= dt;
    if (k->aiLaneTimer <= 0) {
        k->aiLaneTimer = RandF(2, 5);
        k->aiLaneTarget = RandF(-0.45f, 0.45f)*hw;
    }
    float look = 9.0f + fabsf(k->speed)*0.5f;
    int ahead = (int)(look/T.spacing);
    float cAhead = CurvAhead(k->seg, ahead/2, ahead + 6);
    float inside = -Clamp(cAhead*55.0f, -1, 1)*hw*0.45f;
    float laneGoal = Clamp(k->aiLaneTarget*0.5f + inside, -hw + 2.0f, hw - 2.0f);

    /* dodge peels lying on the line */
    for (int p = 0; p < MAX_PROJECTILES; p++) {
        Projectile *pr = &R.proj[p];
        if (!pr->active || pr->type != ITEM_PEEL) continue;
        int ds = TrackWrap(&T, pr->seg - k->seg);
        if (ds > 2 && ds < ahead + 10) {
            int s2; float plat, pal, pgy;
            TrackLocate(&T, pr->pos, pr->seg, &s2, &plat, &pal, &pgy);
            if (fabsf(plat - laneGoal) < 3.0f) laneGoal = plat > 0 ? plat - 4.0f : plat + 4.0f;
        }
    }
    /* secret shortcut: skilled CPUs (or anyone holding a boost) sometimes go for it */
    bool scApproach = false;
    if (T.scN > 1 && !k->onShortcut) {
        int toA = TrackWrap(&T, T.scA - k->seg);
        if (toA >= 44 && toA < 48 && !k->aiScDecided) {
            k->aiScDecided = true;
            bool boosty = k->item == ITEM_PEPPER || k->item == ITEM_PEPPER3 || k->item == ITEM_DISCO;
            float pr = T.def->scIsRoad ? 0.45f : (boosty ? 0.6f : 0.0f);
            if (k->aiSkill < 0.975f) pr *= 0.3f;
            if (k->human < 0) k->aiTakeShortcut = RandF(0, 1) < pr;
            if (k->human >= 0 && G.autotest) { k->aiTakeShortcut = (k->lap == 1); ALog("AI: P1 approaching shortcut on lap %d -> %s", k->lap + 1, k->aiTakeShortcut ? "take it" : "skip"); }
        }
        if (toA > 60 && toA < T.n - 20) k->aiScDecided = false;
        int passed = TrackWrap(&T, k->seg - T.scA);
        if (toA > T.n/2 && passed > 40) k->aiTakeShortcut = false;
        if (k->aiTakeShortcut && passed <= 40) scApproach = true;     /* just past the gap: follow the trail */
        if (k->aiTakeShortcut && toA < 44) {
            scApproach = true;
            float hwA = TrackHalfWidth(&T, T.scA);
            laneGoal = T.def->scSide*hwA*0.55f;
        }
    }
    k->aiLane = Approach(k->aiLane, laneGoal, (scApproach ? 10.0f : 6.0f)*dt);
    Vector3 target = TrackPoint(&T, k->seg + ahead, k->aiLane);
    if (scApproach && !k->onShortcut) {
        int toA2 = TrackWrap(&T, T.scA - k->seg), passed2 = TrackWrap(&T, k->seg - T.scA);
        if (toA2 < ahead + 2 || passed2 <= 40) {
            int si; float sl, sa, sg;
            TrackShortcutLocate(&T, k->pos, &si, &sl, &sa, &sg);
            if (toA2 < ahead + 2 && toA2 > 0) si = 0;
            int ti = si + (int)(look/2.0f) + 2;
            target = T.sc[ti < T.scN ? ti : T.scN - 1].pos;
        }
    }
    if (k->onShortcut) {
        int sa = k->scIdx + (int)(look/2.0f) + 1;
        if (sa < T.scN) target = T.sc[sa].pos;
        else target = TrackPoint(&T, T.scB + (sa - T.scN) + 4, T.def->scSide*TrackHalfWidth(&T, T.scB)*0.2f);
        k->aiTakeShortcut = false;
        scApproach = true;
    }
    float want = atan2f(target.x - k->pos.x, target.z - k->pos.z);
    float diff = WrapAngle(want - k->heading);
    float steer = Clamp(-diff*3.0f, -1, 1);

    in->accel = true;
    if (fabsf(diff) > 1.6f && k->speed > 6) { in->accel = false; in->brake = true; }
    if (k->stuckTimer > 1.5f) { in->accel = false; in->brake = true; steer = -steer; }

    /* drifting through long bends */
    float top = KartTopSpeed(k);
    float cNear = CurvAhead(k->seg, 2, ahead + 4);
    if (k->aiDriftTimer > 0) k->aiDriftTimer -= dt;
    if (k->driftState == 0) {
        if (!scApproach && fabsf(cNear) > 1.0f/60.0f && k->speed > top*0.7f && k->aiDriftTimer <= 0 && fabsf(steer) > 0.3f && k->grounded) {
            in->hop = in->hopPressed = true;
            k->aiDriftTimer = 1.0f;
        }
    } else if (k->driftState == 1) {
        in->hop = true;
        steer = steer > 0 ? fmaxf(steer, 0.6f) : fminf(steer, -0.6f);
    } else {
        /* hold while the bend continues the same way and we're not about to hit the wall */
        bool sameWay = cNear*k->driftDir < -1.0f/400.0f;    /* the bend still turns the way we're drifting */
        float edge = fabsf(k->lat)/(hw + 1.0f);
        bool keep = sameWay && fabsf(cNear) > 1.0f/110.0f && edge < 0.92f;
        /* commit to a drift until the blue spark unless the wall is close or the bend clearly flips */
        float commit = k->human >= 0 ? ORANGE_CHARGE + 0.05f : BLUE_CHARGE + 0.12f;   /* autopilot P1 goes for orange */
        if (k->driftCharge < commit && edge < 0.93f && cNear*k->driftDir < 0.0f) keep = true;
        if (k->driftCharge > ORANGE_CHARGE + 0.1f) keep = false;
        in->hop = keep;
        if (keep && (k->lat*k->driftDir < -hw*0.4f)) steer = 0; /* drifting out wide: ease off */
    }
    in->steer = steer;
    k->aiSteerAvg = Lerp(k->aiSteerAvg, steer, Clamp(3.0f*dt, 0, 1));

    /* items */
    if (k->item != ITEM_NONE && k->roulette <= 0 && (R.phase == RACE_RUNNING || R.attract)) {
        k->aiItemDelay -= dt;
        if (k->aiItemDelay <= 0) {
            bool use = false;
            int aheadK = RaceKartAhead(idx);
            switch (k->item) {
            case ITEM_PEEL: {
                for (int o = 0; o < R.numKarts; o++) {
                    if (o == idx) continue;
                    float dp = k->progress - R.karts[o].progress;
                    if (dp > 2 && dp < 14) use = true;
                }
                if (k->aiItemDelay < -6) use = true;
            } break;
            case ITEM_MELON:
                if (aheadK >= 0) {
                    float dp = R.karts[aheadK].progress - k->progress;
                    float lt = fabsf(R.karts[aheadK].lat - k->lat);
                    if (dp > 2 && dp < 25 && lt < 3) use = true;
                }
                if (k->aiItemDelay < -8) use = true;
                break;
            case ITEM_TOMATO:
                if (aheadK >= 0 && R.karts[aheadK].progress - k->progress < 80) use = true;
                if (k->aiItemDelay < -10) use = true;
                break;
            case ITEM_PEPPER: case ITEM_PEPPER3:
                if (k->onShortcut && !T.def->scIsRoad) { use = true; break; }
                if (k->aiTakeShortcut) break;
                if (fabsf(cNear) < 1.0f/120.0f && !k->offroad) use = true;
                if (k->offroad && k->speed < top*0.6f) use = true;
                if (k->aiItemDelay < -5) use = true;
                break;
            case ITEM_DISCO: case ITEM_KAZOO:
                use = true; break;
            default: break;
            }
            if (use) { in->item = in->itemPressed = true; k->aiItemDelay = RandF(0.6f, 2.0f); }
        }
    }
}

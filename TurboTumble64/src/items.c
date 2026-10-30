/* items.c : item boxes, the roulette, and the seven original items */
#include "common.h"
static void DrawItemCube(float h, float t, int b);

const char *ITEM_NAMES[ITEM_COUNT] = {
    "", "Slippy Peel", "Bouncy Melon", "Homing Tomato", "Hot Pepper", "Triple Pepper", "Disco Ball", "Thunder Kazoo"
};

/* odds by race position (1st..8th): peel, melon, tomato, pepper, pepper3, disco, kazoo */
static const int ODDS[8][7] = {
    { 45, 35, 10, 10,  0,  0,  0 },
    { 25, 30, 25, 15,  5,  0,  0 },
    { 15, 25, 30, 20,  8,  2,  0 },
    { 10, 20, 30, 20, 12,  6,  2 },
    {  5, 15, 30, 20, 15, 10,  5 },
    {  0, 10, 25, 20, 20, 15, 10 },
    {  0,  5, 20, 20, 25, 20, 10 },
    {  0,  0, 15, 20, 25, 25, 15 },
};

static void ItemSfx(Vector3 p, SfxId id, float vol)
{
    if (G.autotest && G.autoSpeed > 1) return;
    float best = 1e9f;
    for (int h = 0; h < R.numHumans; h++) {
        float d = Vector3Distance(p, R.karts[R.humanKart[h]].pos);
        if (d < best) best = d;
    }
    if (R.attract) return;
    if (best < 50) PlaySfx(id, vol*(1.0f - best/50.0f), 1.0f);
}

ItemType ItemRoll(int place, int numKarts)
{
    int row = place - 1;
    if (numKarts < 8 && numKarts > 1) row = (int)((float)(place - 1)/(numKarts - 1)*7.0f + 0.5f);
    row = row < 0 ? 0 : (row > 7 ? 7 : row);
    int total = 0;
    for (int i = 0; i < 7; i++) total += ODDS[row][i];
    int r = rand() % total;
    for (int i = 0; i < 7; i++) { if (r < ODDS[row][i]) return (ItemType)(ITEM_PEEL + i); r -= ODDS[row][i]; }
    return ITEM_PEEL;
}

void ItemsReset(void)
{
    memset(R.proj, 0, sizeof(R.proj));
    R.numBoxes = 0;
    const TrackDef *d = T.def;
    for (int r = 0; r < d->numBoxRows; r++) {
        int seg = (int)(d->boxRows[r]*T.n);
        float hw = TrackHalfWidth(&T, seg);
        for (int i = 0; i < 4 && R.numBoxes < MAX_ITEM_BOXES; i++) {
            float lat = (-0.6f + 0.4f*i)*hw;
            ItemBox *b = &R.boxes[R.numBoxes++];
            b->pos = TrackPoint(&T, seg, lat);
            b->pos.y += 1.3f;
            b->active = true;
            b->respawn = 0;
        }
    }
}

static Projectile *NewProjectile(void)
{
    for (int i = 0; i < MAX_PROJECTILES; i++) if (!R.proj[i].active) return &R.proj[i];
    /* recycle the oldest peel */
    float best = 1e9f; int bi = 0;
    for (int i = 0; i < MAX_PROJECTILES; i++) if (R.proj[i].life < best) { best = R.proj[i].life; bi = i; }
    return &R.proj[bi];
}

void ItemUse(int idx)
{
    Kart *k = &R.karts[idx];
    if (k->item == ITEM_NONE || k->roulette > 0 || k->spinTimer > 0) return;
    ItemType it = k->item;
    Vector3 fwd = { sinf(k->heading), 0, cosf(k->heading) };
    bool backwards = false;
    k->statItemsUsed++;
    switch (it) {
    case ITEM_PEEL: {
        Projectile *p = NewProjectile();
        memset(p, 0, sizeof(*p));
        p->active = true; p->type = ITEM_PEEL; p->owner = idx;
        p->pos = Vector3Subtract(k->pos, Vector3Scale(fwd, 2.6f));
        p->seg = k->seg; p->life = 60.0f; p->armTime = 0.5f;
        int s; float lat, al, gy;
        TrackLocate(&T, p->pos, p->seg, &s, &lat, &al, &gy);
        p->seg = s; p->pos.y = k->onShortcut ? k->groundY : gy;
        p->yaw = k->heading;
        ItemSfx(k->pos, SFX_PEEL, 0.8f);
    } break;
    case ITEM_MELON:
    case ITEM_TOMATO: {
        Projectile *p = NewProjectile();
        memset(p, 0, sizeof(*p));
        p->active = true; p->type = it; p->owner = idx;
        Vector3 d = backwards ? Vector3Negate(fwd) : fwd;
        p->pos = Vector3Add(k->pos, Vector3Scale(d, 2.4f));
        p->pos.y += 0.6f;
        p->yaw = atan2f(d.x, d.z);
        p->speed = (it == ITEM_MELON ? 50.0f : 44.0f)*(G.settings.cc == 0 ? 0.85f : 1.0f);
        p->life = it == ITEM_MELON ? 9.0f : 12.0f;
        p->seg = k->seg;
        p->armTime = 0.4f;
        p->target = (it == ITEM_TOMATO) ? RaceKartAhead(idx) : -1;
        ItemSfx(k->pos, SFX_THROW, 0.8f);
    } break;
    case ITEM_PEPPER:
    case ITEM_PEPPER3:
        if (k->boostTimer < 1.3f) k->boostTimer = 1.3f;
        k->boostPower = 0.42f;
        k->statBoosts++;
        ItemSfx(k->pos, SFX_BOOST, 1.0f);
        if (k->human >= 0 && !(G.autotest && G.autoSpeed > 1)) PlayVoice(k->charId, 0);
        break;
    case ITEM_DISCO:
        k->discoTimer = 7.5f;
        k->invulnTimer = 7.5f;
        k->spinTimer = 0;
        ItemSfx(k->pos, SFX_DISCO, 1.0f);
        if (k->human >= 0 && !(G.autotest && G.autoSpeed > 1)) PlayVoice(k->charId, 2);
        break;
    case ITEM_KAZOO:
        for (int o = 0; o < R.numKarts; o++) {
            if (o == idx) continue;
            Kart *ko = &R.karts[o];
            if (ko->discoTimer > 0) continue;
            ko->shrinkTimer = 4.0f + (float)(R.numKarts - ko->place)*0.35f;
            ko->spinTimer = fmaxf(ko->spinTimer, 0.6f);
            ko->speed *= 0.6f;
            ko->driftState = 0;
            ko->item = ITEM_NONE; ko->itemCount = 0; ko->roulette = 0;
            ko->statHits++;
        }
        if (!(G.autotest && G.autoSpeed > 1) && !R.attract) PlaySfx(SFX_KAZOO, 1.0f, 1.0f);
        break;
    default: break;
    }
    k->itemCount--;
    if (k->itemCount <= 0) { k->item = ITEM_NONE; k->itemCount = 0; }
}

static bool HitKart(Projectile *p, int ki, bool big)
{
    Kart *k = &R.karts[ki];
    if (k->discoTimer > 0) { p->active = false; return true; }
    if (k->invulnTimer > 0) return false;
    KartHit(ki, big);
    p->active = false;
    return true;
}

void ItemsUpdate(float dt)
{
    /* roulette */
    for (int i = 0; i < R.numKarts; i++) {
        Kart *k = &R.karts[i];
        if (k->roulette > 0) {
            k->roulette -= dt;
            if (k->roulette <= 0) {
                k->roulette = 0;
                k->item = k->rouletteFinal;
                k->itemFlash = 0.35f;
                k->itemCount = (k->item == ITEM_PEPPER3) ? 3 : 1;
                k->aiItemDelay = RandF(0.8f, 4.0f);
                if (k->human >= 0 && !(G.autotest && G.autoSpeed > 1)) PlaySfx(SFX_ITEMGET, 0.8f, 1.0f);
            }
        }
    }

    for (int i = 0; i < MAX_PROJECTILES; i++) {
        Projectile *p = &R.proj[i];
        if (!p->active) continue;
        p->life -= dt;
        if (p->armTime > 0) p->armTime -= dt;
        if (p->life <= 0) { p->active = false; continue; }

        if (p->type == ITEM_MELON || p->type == ITEM_TOMATO) {
            if (p->type == ITEM_TOMATO) {
                Vector3 aim;
                if (p->target >= 0 && !R.karts[p->target].finished) {
                    aim = R.karts[p->target].pos;
                    /* until close, follow the track so we don't cut through walls */
                    if (Vector3Distance(aim, p->pos) > 22.0f) aim = TrackPoint(&T, p->seg + 8, R.karts[p->target].lat*0.5f);
                } else {
                    aim = TrackPoint(&T, p->seg + 8, 0);
                }
                float want = atan2f(aim.x - p->pos.x, aim.z - p->pos.z);
                float diff = WrapAngle(want - p->yaw);
                p->yaw += Clamp(diff, -4.0f*dt, 4.0f*dt);
            }
            Vector3 d = { sinf(p->yaw), 0, cosf(p->yaw) };
            p->pos.x += d.x*p->speed*dt;
            p->pos.z += d.z*p->speed*dt;
            int s; float lat, al, gy;
            TrackLocate(&T, p->pos, p->seg, &s, &lat, &al, &gy);
            int si; float slat, sal, sgy;
            bool pSc = fabsf(lat) > TrackWallLimit(&T, s, lat) && TrackShortcutLocate(&T, p->pos, &si, &slat, &sal, &sgy);
            if (pSc) { gy = sgy; s = TrackShortcutMainSeg(&T, si, sal); }
            p->seg = s;
            p->pos.y = Lerp(p->pos.y, gy + 0.6f, Clamp(12*dt, 0, 1));
            float lim = TrackWallLimit(&T, s, lat) + 0.4f;
            if (!pSc && fabsf(lat) > lim) {
                Vector3 n = Vector3Scale(T.s[s].right, lat > 0 ? 1.0f : -1.0f);
                float push = fabsf(lat) - lim;
                p->pos.x -= n.x*push; p->pos.z -= n.z*push;
                if (p->type == ITEM_MELON) {
                    float dn = d.x*n.x + d.z*n.z;
                    if (dn > 0) {
                        d.x -= 2*dn*n.x; d.z -= 2*dn*n.z;
                        p->yaw = atan2f(d.x, d.z);
                        p->bounces++;
                        ItemSfx(p->pos, SFX_BUMP, 0.4f);
                        if (p->bounces > 7) p->active = false;
                    }
                }
            }
            if (!p->active) continue;
            /* hit karts */
            for (int k = 0; k < R.numKarts; k++) {
                if (k == p->owner && p->armTime > 0) continue;
                Kart *kk = &R.karts[k];
                float r = 1.6f*kk->scale + 0.4f;
                if (Vector3DistanceSqr(kk->pos, p->pos) < r*r + 1.0f) {
                    if (HitKart(p, k, true)) {
                        for (int q = 0; q < 10; q++)
                            ParticleSpawn(p->pos, (Vector3){ RandF(-6, 6), RandF(2, 8), RandF(-6, 6) },
                                          p->type == ITEM_MELON ? (Color){ 60, 200, 60, 255 } : (Color){ 230, 40, 30, 255 }, 0.6f, 0.4f, 20);
                        break;
                    }
                }
            }
            if (!p->active) continue;
            /* hit other projectiles */
            for (int j = 0; j < MAX_PROJECTILES; j++) {
                if (j == i || !R.proj[j].active) continue;
                if (Vector3DistanceSqr(R.proj[j].pos, p->pos) < 2.2f*2.2f) {
                    R.proj[j].active = false; p->active = false;
                    ItemSfx(p->pos, SFX_HIT, 0.5f);
                    for (int q = 0; q < 8; q++) ParticleSpawn(p->pos, (Vector3){ RandF(-5, 5), RandF(2, 7), RandF(-5, 5) }, YELLOW, 0.5f, 0.3f, 18);
                    break;
                }
            }
        } else if (p->type == ITEM_PEEL) {
            for (int k = 0; k < R.numKarts; k++) {
                if (k == p->owner && p->armTime > 0) continue;
                Kart *kk = &R.karts[k];
                if (!kk->grounded && kk->pos.y > p->pos.y + 1.0f) continue;
                float r = 1.3f*kk->scale + 0.5f;
                if (Vector3DistanceSqr(kk->pos, p->pos) < r*r) {
                    if (HitKart(p, k, false)) break;
                }
            }
        }
    }
}

void ItemBoxesUpdate(float dt)
{
    for (int b = 0; b < R.numBoxes; b++) {
        ItemBox *box = &R.boxes[b];
        if (!box->active) {
            box->respawn -= dt;
            if (box->respawn <= 0) box->active = true;
            continue;
        }
        for (int i = 0; i < R.numKarts; i++) {
            Kart *k = &R.karts[i];
            Vector3 c = { k->pos.x, k->pos.y + 1.0f, k->pos.z };
            float r = 2.2f*k->scale + 0.3f;
            if (Vector3DistanceSqr(c, box->pos) < r*r) {
                box->active = false;
                box->respawn = 3.0f;
                for (int q = 0; q < 16; q++)
                    ParticleSpawn(box->pos, (Vector3){ RandF(-6, 6), RandF(1, 8), RandF(-6, 6) }, HueColor(q*22.5f, 0.7f, 1.0f), 0.6f, 0.35f, 15);
                if (k->human >= 0 && !(G.autotest && G.autoSpeed > 1)) PlaySfx(SFX_BOXBREAK, 0.6f, 1.0f);
                if (k->item == ITEM_NONE && k->roulette <= 0 && !R.timeTrial) {
                    k->roulette = k->human >= 0 && !k->autopilot ? 1.4f : 1.0f;
                    k->rouletteDur = k->roulette;
                    k->rouletteFinal = ItemRoll(k->place > 0 ? k->place : R.numKarts, R.numKarts);
                    k->statItemsGot++;
                    if (k->human >= 0 && !(G.autotest && G.autoSpeed > 1)) PlaySfx(SFX_ROULETTE, 0.55f, 1.0f);
                }
                break;
            }
        }
    }
}

/* ------------------------------------------------------------------ */
/* drawing                                                              */
/* ------------------------------------------------------------------ */
static void DrawPeel3D(Vector3 p, float yaw)
{
    rlPushMatrix();
    rlTranslatef(p.x, p.y, p.z);
    rlRotatef(yaw*RAD2DEG, 0, 1, 0);
    Color y = { 255, 220, 40, 255 };
    for (int i = 0; i < 4; i++) {
        float a = i*PI*0.5f + PI*0.25f;
        rlPushMatrix();
        rlRotatef(a*RAD2DEG, 0, 1, 0);
        rlRotatef(-35, 1, 0, 0);
        DrawLitBox((Vector3){ 0, 0.15f, 0.35f }, (Vector3){ 0.35f, 0.12f, 0.8f }, y);
        rlPopMatrix();
    }
    DrawLitSphere((Vector3){ 0, 0.3f, 0 }, (Vector3){ 0.3f, 0.3f, 0.3f }, (Color){ 250, 245, 200, 255 }, 3, 6);
    DrawLitBox((Vector3){ 0, 0.6f, 0 }, (Vector3){ 0.12f, 0.25f, 0.12f }, (Color){ 110, 80, 30, 255 });
    rlPopMatrix();
}

static void DrawMelon3D(Vector3 p, float spin)
{
    rlPushMatrix();
    rlTranslatef(p.x, p.y, p.z);
    rlRotatef(spin*RAD2DEG, 0, 1, 0);
    DrawLitSphere((Vector3){ 0, 0, 0 }, (Vector3){ 0.65f, 0.6f, 0.65f }, (Color){ 60, 170, 60, 255 }, 5, 8);
    for (int i = 0; i < 3; i++) {
        rlPushMatrix(); rlRotatef(i*60.0f, 0, 1, 0);
        DrawLitBox((Vector3){ 0, 0, 0 }, (Vector3){ 0.12f, 1.22f, 1.32f }, (Color){ 25, 90, 30, 255 });
        rlPopMatrix();
    }
    rlPopMatrix();
}

static void DrawTomato3D(Vector3 p, float spin)
{
    rlPushMatrix();
    rlTranslatef(p.x, p.y + 0.05f*sinf(spin*3), p.z);
    rlRotatef(spin*RAD2DEG, 0, 1, 0);
    DrawLitSphere((Vector3){ 0, 0, 0 }, (Vector3){ 0.65f, 0.55f, 0.65f }, (Color){ 230, 40, 30, 255 }, 5, 8);
    for (int i = 0; i < 5; i++) {
        rlPushMatrix(); rlRotatef(i*72.0f, 0, 1, 0);
        DrawLitBox((Vector3){ 0, 0.55f, 0.2f }, (Vector3){ 0.12f, 0.06f, 0.45f }, (Color){ 40, 160, 40, 255 });
        rlPopMatrix();
    }
    DrawLitBox((Vector3){ 0, 0.68f, 0 }, (Vector3){ 0.08f, 0.25f, 0.08f }, (Color){ 40, 140, 40, 255 });
    /* angry eyes */
    DrawLitBox((Vector3){ 0.2f, 0.15f, 0.58f }, (Vector3){ 0.14f, 0.16f, 0.06f }, WHITE);
    DrawLitBox((Vector3){ -0.2f, 0.15f, 0.58f }, (Vector3){ 0.14f, 0.16f, 0.06f }, WHITE);
    DrawLitBox((Vector3){ 0.2f, 0.13f, 0.61f }, (Vector3){ 0.07f, 0.09f, 0.04f }, BLACK);
    DrawLitBox((Vector3){ -0.2f, 0.13f, 0.61f }, (Vector3){ 0.07f, 0.09f, 0.04f }, BLACK);
    rlPopMatrix();
}

void DrawItemsWorld(Camera3D cam)
{
    float t = G.time;
    for (int i = 0; i < MAX_PROJECTILES; i++) {
        Projectile *p = &R.proj[i];
        if (!p->active) continue;
        if (p->type == ITEM_PEEL) DrawPeel3D(p->pos, p->yaw);
        else if (p->type == ITEM_MELON) DrawMelon3D(p->pos, t*8.0f);
        else if (p->type == ITEM_TOMATO) DrawTomato3D(p->pos, p->yaw);
    }
    /* item boxes: translucent rainbow cubes with a "?" inside */
    rlDrawRenderBatchActive();
    rlDisableDepthMask();
    for (int b = 0; b < R.numBoxes; b++) {
        ItemBox *box = &R.boxes[b];
        float grow = box->active ? 1.0f : 0.0f;
        if (!box->active && box->respawn < 0.4f) grow = 1.0f - box->respawn/0.4f;
        if (grow <= 0.01f) continue;
        Vector3 p = box->pos;
        p.y += 0.25f*sinf(t*2.0f + b);
        DrawBillboard(cam, G.texQuestion, p, 0.8f*grow, WHITE);
        rlPushMatrix();
        rlTranslatef(p.x, p.y, p.z);
        rlRotatef(t*90.0f + b*20.0f, 0, 1, 0);
        rlRotatef(35, 1, 0, 1);
        DrawItemCube(0.8f*grow, t, b);
        rlPopMatrix();
    }
    rlDrawRenderBatchActive();
    rlEnableDepthMask();
}

/* rainbow-shimmering translucent cube, every face textured with a bright "?" panel */
static void DrawItemCube(float h, float t, int b)
{
    static const signed char C[8][3] = { {-1,-1,-1},{1,-1,-1},{1,1,-1},{-1,1,-1},{-1,-1,1},{1,-1,1},{1,1,1},{-1,1,1} };
    static const unsigned char F[6][4] = { {4,5,6,7},{1,0,3,2},{5,1,2,6},{0,4,7,3},{7,6,2,3},{0,1,5,4} };
    static const float UV[4][2] = { {0,1},{1,1},{1,0},{0,0} };
    Color vc[8];
    for (int i = 0; i < 8; i++) {
        vc[i] = HueColor(t*150.0f + b*40.0f + i*47.0f, 0.6f, 1.0f);
        vc[i].a = 175;
    }
    rlSetTexture(G.tx[TX_ITEMBOX].id);
    rlBegin(RL_QUADS);
    for (int f = 0; f < 6; f++) for (int k = 0; k < 4; k++) {
        int i = F[f][k];
        rlColor4ub(vc[i].r, vc[i].g, vc[i].b, vc[i].a);
        rlTexCoord2f(UV[k][0], UV[k][1]);
        rlVertex3f(C[i][0]*h, C[i][1]*h, C[i][2]*h);
    }
    rlEnd();
    rlSetTexture(0);
}

/* 2D HUD icons */
void DrawItemIcon(ItemType it, int cx, int cy, float s)
{
    switch (it) {
    case ITEM_NONE: break;
    case ITEM_PEEL:
        DrawRing((Vector2){ (float)cx + s*0.15f, (float)cy - s*0.1f }, s*0.22f, s*0.38f, 100, 260, 12, (Color){ 255, 220, 40, 255 });
        DrawRectangle(cx - (int)(s*0.05f), cy - (int)(s*0.45f), (int)(s*0.1f), (int)(s*0.15f), BROWN);
        DrawTriangle((Vector2){ cx - s*0.2f, cy + s*0.1f }, (Vector2){ cx - s*0.35f, cy + s*0.4f }, (Vector2){ cx - s*0.05f, cy + s*0.25f }, (Color){ 255, 230, 80, 255 });
        DrawTriangle((Vector2){ cx + s*0.2f, cy + s*0.1f }, (Vector2){ cx + s*0.05f, cy + s*0.25f }, (Vector2){ cx + s*0.35f, cy + s*0.4f }, (Color){ 255, 230, 80, 255 });
        break;
    case ITEM_MELON:
        DrawCircle(cx, cy, s*0.38f, (Color){ 60, 170, 60, 255 });
        for (int i = -1; i <= 1; i++) DrawRectangle(cx + (int)(i*s*0.18f) - 2, cy - (int)(s*0.34f), 4, (int)(s*0.68f), (Color){ 25, 90, 30, 255 });
        DrawCircle(cx - (int)(s*0.12f), cy - (int)(s*0.15f), s*0.08f, (Color){ 160, 230, 160, 255 });
        break;
    case ITEM_TOMATO:
        DrawCircle(cx, cy + (int)(s*0.05f), s*0.38f, (Color){ 230, 40, 30, 255 });
        DrawPoly((Vector2){ (float)cx, cy - s*0.28f }, 5, s*0.16f, G.time*30, (Color){ 40, 160, 40, 255 });
        DrawCircle(cx - (int)(s*0.13f), cy, s*0.07f, WHITE);
        DrawCircle(cx + (int)(s*0.13f), cy, s*0.07f, WHITE);
        DrawCircle(cx - (int)(s*0.12f), cy + 1, s*0.035f, BLACK);
        DrawCircle(cx + (int)(s*0.12f), cy + 1, s*0.035f, BLACK);
        break;
    case ITEM_PEPPER:
    case ITEM_PEPPER3: {
        int n = it == ITEM_PEPPER3 ? 3 : 1;
        for (int i = 0; i < n; i++) {
            float ox = n == 1 ? 0 : (i - 1)*s*0.25f;
            float sc = n == 1 ? 1.0f : 0.7f;
            DrawEllipse(cx + (int)ox, cy + (int)(s*0.05f), s*0.14f*sc, s*0.36f*sc, (Color){ 230, 30, 20, 255 });
            DrawRectangle(cx + (int)ox - 2, cy - (int)(s*0.42f*sc), 4, (int)(s*0.14f*sc), (Color){ 40, 150, 40, 255 });
            DrawEllipse(cx + (int)ox - (int)(s*0.05f), cy - (int)(s*0.1f*sc), s*0.03f, s*0.12f*sc, (Color){ 255, 160, 140, 255 });
        }
    } break;
    case ITEM_DISCO:
        DrawCircle(cx, cy, s*0.38f, (Color){ 200, 200, 215, 255 });
        for (int gx = -2; gx <= 2; gx++) for (int gy = -2; gy <= 2; gy++) {
            if (gx*gx + gy*gy > 5) continue;
            Color c = HueColor(G.time*200.0f + (gx + gy)*50.0f, 0.5f, 1.0f);
            DrawRectangle(cx + (int)(gx*s*0.13f) - (int)(s*0.05f), cy + (int)(gy*s*0.13f) - (int)(s*0.05f), (int)(s*0.1f), (int)(s*0.1f), c);
        }
        DrawRectangle(cx - 1, cy - (int)(s*0.48f), 2, (int)(s*0.1f), GRAY);
        break;
    case ITEM_KAZOO:
        DrawTriangle((Vector2){ cx - s*0.4f, cy - s*0.08f }, (Vector2){ cx - s*0.4f, cy + s*0.08f }, (Vector2){ cx + s*0.3f, cy + s*0.2f }, (Color){ 255, 200, 40, 255 });
        DrawTriangle((Vector2){ cx - s*0.4f, cy - s*0.08f }, (Vector2){ cx + s*0.3f, cy + s*0.2f }, (Vector2){ cx + s*0.3f, cy - s*0.2f }, (Color){ 255, 200, 40, 255 });
        DrawCircle(cx, cy - (int)(s*0.12f), s*0.08f, (Color){ 200, 140, 20, 255 });
        DrawLineEx((Vector2){ cx + s*0.35f, cy - s*0.35f }, (Vector2){ cx + s*0.2f, cy - s*0.05f }, 3, (Color){ 120, 220, 255, 255 });
        DrawLineEx((Vector2){ cx + s*0.2f, cy - s*0.05f }, (Vector2){ cx + s*0.42f, cy + s*0.05f }, 3, (Color){ 120, 220, 255, 255 });
        DrawLineEx((Vector2){ cx + s*0.42f, cy + s*0.05f }, (Vector2){ cx + s*0.28f, cy + s*0.38f }, 3, (Color){ 120, 220, 255, 255 });
        break;
    default: break;
    }
}

/* menu.c : input mapping, title / mode / options / character / track select,
 * pause, results and Grand Prix standings screens */
#include "common.h"
#include "online.h"

/* ------------------------------------------------------------------ */
/* settings                                                             */
/* ------------------------------------------------------------------ */
#define CFG_FILE "turbotumble64.cfg"
#define TRACK_CUP_NAME "~ TURBO TUMBLE CUP ~"
void SaveSettings(void)
{
    FILE *f = fopen(CFG_FILE, "w");
    if (!f) return;
    fprintf(f, "visual %d\ncc %d\nmusic %.2f\nsfx %.2f\nfps %d\npadmode %d\n", G.settings.visualMode, G.settings.cc, G.settings.musicVol, G.settings.sfxVol, G.settings.showFps ? 1 : 0, G.settings.padMode);
    for (int s = 0; s < 2; s++) for (int a = 0; a < NUM_PAD_ACTIONS; a++) for (int k = 0; k < 2; k++)
        fprintf(f, "bind%d_%d_%d %d\n", s, a, k, gBinds[s][a][k].kind*100 + gBinds[s][a][k].code);
    for (int i = 0; i < NUM_TRACKS; i++) fprintf(f, "best%d %.3f\n", i, G.bestTimes[i]);
    fclose(f);
}

void LoadSettings(void)
{
    G.settings.pixelMode = 0; G.settings.visualMode = 0; G.settings.padMode = 0; G.settings.cc = 1; G.settings.musicVol = 0.55f; G.settings.sfxVol = 0.8f; G.settings.showFps = false;
    FILE *f = fopen(CFG_FILE, "r");
    if (!f) return;
    char key[32]; float v;
    while (fscanf(f, "%31s %f", key, &v) == 2) {
        if (!strcmp(key, "visual")) G.settings.visualMode = (int)Clamp(v, 0, 1);
        else if (!strcmp(key, "padmode")) G.settings.padMode = (int)Clamp(v, 0, 2);
        else if (!strncmp(key, "bind", 4)) {
            int s, a, k;
            if (sscanf(key + 4, "%d_%d_%d", &s, &a, &k) == 3 && s >= 0 && s < 2 && a >= 0 && a < NUM_PAD_ACTIONS && k >= 0 && k < 2) {
                int iv = (int)v;
                gBinds[s][a][k] = (PadBind){ (signed char)(iv/100), (signed char)(iv % 100) };
            }
        }
        else if (!strcmp(key, "cc")) G.settings.cc = (int)Clamp(v, 0, 2);
        else if (!strcmp(key, "music")) G.settings.musicVol = Clamp(v, 0, 1);
        else if (!strcmp(key, "sfx")) G.settings.sfxVol = Clamp(v, 0, 1);
        else if (!strcmp(key, "fps")) G.settings.showFps = v > 0.5f;
        else if (!strncmp(key, "best", 4)) { int i = atoi(key + 4); if (i >= 0 && i < NUM_TRACKS) G.bestTimes[i] = v; }
    }
    fclose(f);
}

/* ------------------------------------------------------------------ */
/* screen flow                                                          */
/* ------------------------------------------------------------------ */
void GoToScreen(Screen s)
{
    G.screen = s;
    G.screenTime = 0;
    G.menuSel = 0;
    G.paused = false;
    G.remapAction = -1;
    if (s == SCR_TITLE || s == SCR_MODE || s == SCR_OPTIONS || s == SCR_CHAR || s == SCR_TRACK || s == SCR_CONTROLS) {
        if (!R.attract) RaceStart(rand() % NUM_TRACKS, true);
        MusicPlay(MUSIC_TITLE);
        for (int h = 0; h < MAX_HUMANS; h++) { EngineSet(h, 0, 0); DriftLoop(h, false, 0); }
    }
    if (s == SCR_RESULTS || s == SCR_STANDINGS || s == SCR_TROPHY) {
        MusicPlay(MUSIC_RESULTS);
        for (int h = 0; h < MAX_HUMANS; h++) { EngineSet(h, 0, 0.03f); DriftLoop(h, false, 0); }
    }
}

static void StartCup(void)
{
    bool used[MAX_CHARACTERS] = { 0 };
    G.gpChars[0] = G.humanChar[0]; used[G.humanChar[0]] = true;
    int n = 1;
    int pool[MAX_CHARACTERS], pn = 0;
    for (int c = 0; c < NUM_CHARACTERS; c++) if (!used[c]) pool[pn++] = c;
    for (int i = pn - 1; i > 0; i--) { int j = rand() % (i + 1); int t = pool[i]; pool[i] = pool[j]; pool[j] = t; }
    for (int i = 0; i < pn && n < MAX_RACERS; i++) G.gpChars[n++] = pool[i];
    while (n < MAX_RACERS) G.gpChars[n++] = rand() % NUM_CHARACTERS;
    memset(G.gpPoints, 0, sizeof(G.gpPoints));
    G.gpRace = 0;
    RaceStart(0, false);
    GoToScreen(SCR_RACE);
}

static void Move(int *sel, int n, int d) { *sel = (*sel + d + n) % n; PlaySfx(SFX_MENU_MOVE, 0.5f, 1.0f); }

void MenusUpdate(float dt)
{
    G.screenTime += dt;
    switch (G.screen) {
    case SCR_TITLE:
        if (G.screenTime > 0.3f && (MenuOk() || IsKeyPressed(KEY_ENTER))) { PlaySfx(SFX_MENU_OK, 0.7f, 1); GoToScreen(SCR_MODE); }
        else if (IsKeyPressed(KEY_ESCAPE)) G.quit = true;
        break;
    case SCR_MODE:
        if (MenuUp()) Move(&G.menuSel, 6, -1);
        if (MenuDown()) Move(&G.menuSel, 6, 1);
        if (MenuBack()) { PlaySfx(SFX_MENU_BACK, 0.7f, 1); GoToScreen(SCR_TITLE); break; }
        if (MenuOk()) {
            PlaySfx(SFX_MENU_OK, 0.7f, 1);
            int s = G.menuSel;
            if (s == 3) { OnlineEnter(); break; }
            if (s == 4) { GoToScreen(SCR_OPTIONS); break; }
            if (s == 5) { G.quit = true; break; }
            G.mode = s == 0 ? MODE_GP : (s == 1 ? MODE_TT : MODE_VS);
            G.numHumans = G.mode == MODE_VS ? 2 : 1;
            G.charLocked[0] = G.charLocked[1] = false;
            G.charCursor[0] = 0; G.charCursor[1] = 1 % NUM_CHARACTERS;
            GoToScreen(SCR_CHAR);
        }
        break;
    case SCR_OPTIONS: {
        if (MenuUp()) Move(&G.menuSel, 8, -1);
        if (MenuDown()) Move(&G.menuSel, 8, 1);
        int d = MenuLeft() ? -1 : (MenuRight() ? 1 : 0);
        if (d) {
            PlaySfx(SFX_MENU_MOVE, 0.5f, 1.2f);
            switch (G.menuSel) {
            case 0: G.settings.cc = (G.settings.cc + d + 3) % 3; break;
            case 1: G.settings.visualMode = 1 - G.settings.visualMode; RenderApplyTextureFilters(); RenderResize(); if (T.loaded) { T.loaded = true; TrackBuild(&T, T.index); } break;
            case 2: G.settings.musicVol = Clamp(G.settings.musicVol + d*0.1f, 0, 1); break;
            case 3: G.settings.sfxVol = Clamp(G.settings.sfxVol + d*0.1f, 0, 1); break;
            case 4: G.settings.showFps = !G.settings.showFps; break;
            case 5: G.settings.padMode = (G.settings.padMode + d + 3) % 3; break;
            }
        }
        if (MenuOk() && G.menuSel == 6) { PlaySfx(SFX_MENU_OK, 0.7f, 1); GoToScreen(SCR_CONTROLS); break; }
        if (MenuBack() || (MenuOk() && G.menuSel == 7)) { SaveSettings(); PlaySfx(SFX_MENU_BACK, 0.7f, 1); GoToScreen(SCR_MODE); G.menuSel = 4; }
    } break;
    case SCR_CONTROLS: {
        /* rows: 0..4 actions, 5 reset defaults, 6 back */
        if (G.remapAction >= 0) {
            PadBind b;
            if (IsKeyPressed(KEY_ESCAPE) || G.screenTime > 6.0f) { G.remapAction = -1; PlaySfx(SFX_MENU_BACK, 0.7f, 1); break; }
            if (InputCapture(&b)) {
                InputSetBind(PadPlayerUsesRaw(0) ? 1 : 0, G.remapAction, b);
                G.remapAction = -1; G.screenTime = 0; SaveSettings(); PlaySfx(SFX_MENU_OK, 0.7f, 1.2f);
            }
            break;
        }
        if (MenuUp()) Move(&G.menuSel, 7, -1);
        if (MenuDown()) Move(&G.menuSel, 7, 1);
        if (MenuOk() && G.screenTime > 0.25f) {
            if (G.menuSel < NUM_PAD_ACTIONS) {
                if (PadPlayerName(0)) { G.remapAction = G.menuSel; G.screenTime = 0; InputCaptureBegin(); PlaySfx(SFX_MENU_OK, 0.7f, 1); }
                else PlaySfx(SFX_MENU_BACK, 0.7f, 1);
            } else if (G.menuSel == 5) { InputDefaultBinds(PadPlayerUsesRaw(0) ? 1 : 0); SaveSettings(); PlaySfx(SFX_MENU_OK, 0.7f, 1); }
            else { SaveSettings(); PlaySfx(SFX_MENU_BACK, 0.7f, 1); GoToScreen(SCR_OPTIONS); G.menuSel = 6; }
        } else if (MenuBack() && G.screenTime > 0.25f) { SaveSettings(); PlaySfx(SFX_MENU_BACK, 0.7f, 1); GoToScreen(SCR_OPTIONS); G.menuSel = 6; }
    } break;
    case SCR_CHAR: {
        int cols = 4;
        for (int p = 0; p < G.numHumans; p++) {
            if (!G.charLocked[p]) {
                int c = G.charCursor[p];
                if (PlayerLeft(p)) { c = (c - 1 + NUM_CHARACTERS) % NUM_CHARACTERS; PlaySfx(SFX_MENU_MOVE, 0.5f, 1); }
                if (PlayerRight(p)) { c = (c + 1) % NUM_CHARACTERS; PlaySfx(SFX_MENU_MOVE, 0.5f, 1); }
                if (PlayerUp(p)) { c = (c - cols + NUM_CHARACTERS) % NUM_CHARACTERS; PlaySfx(SFX_MENU_MOVE, 0.5f, 1); }
                if (PlayerDown(p)) { c = (c + cols) % NUM_CHARACTERS; PlaySfx(SFX_MENU_MOVE, 0.5f, 1); }
                G.charCursor[p] = c;
                if (PlayerOk(p) && G.screenTime > 0.2f) {
                    bool taken = (G.numHumans == 2 && G.charLocked[1 - p] && G.charCursor[1 - p] == c);
                    if (!taken) { G.charLocked[p] = true; G.humanChar[p] = c; PlaySfx(SFX_MENU_OK, 0.7f, 1); PlayVoice(c, 0); }
                    else PlaySfx(SFX_MENU_BACK, 0.7f, 1);
                }
                if (PlayerBack(p) && G.screenTime > 0.2f) {
                    PlaySfx(SFX_MENU_BACK, 0.7f, 1);
                    GoToScreen(G.mode == MODE_ONLINE ? SCR_ONLINE : SCR_MODE);
                    return;
                }
            } else if (PlayerBack(p)) { G.charLocked[p] = false; PlaySfx(SFX_MENU_BACK, 0.7f, 1); }
        }
        bool all = true;
        for (int p = 0; p < G.numHumans; p++) if (!G.charLocked[p]) all = false;
        if (all) {
            if (G.mode == MODE_GP) StartCup();
            else { GoToScreen(SCR_TRACK); G.menuSel = G.trackIndex; }
        }
    } break;
    case SCR_TRACK:
        if (MenuLeft()) Move(&G.menuSel, NUM_TRACKS, -1);
        if (MenuRight()) Move(&G.menuSel, NUM_TRACKS, 1);
        if (MenuUp() || MenuDown()) Move(&G.menuSel, NUM_TRACKS, 3);
        if (MenuBack()) { G.charLocked[0] = G.charLocked[1] = false; PlaySfx(SFX_MENU_BACK, 0.7f, 1); GoToScreen(SCR_CHAR); break; }
        if (MenuOk() && G.screenTime > 0.2f) {
            PlaySfx(SFX_MENU_OK, 0.7f, 1);
            G.trackIndex = G.menuSel;
            if (G.mode == MODE_ONLINE) { OnlineSubmitPick(); GoToScreen(SCR_ONLINE); break; }
            RaceStart(G.trackIndex, false);
            GoToScreen(SCR_RACE);
        }
        break;
    case SCR_ONLINE:
        OnlineMenuUpdate();
        break;
    case SCR_RACE:
        if (G.mode == MODE_ONLINE) {         /* no pause or skipping: the race is shared */
            if (OnlineRaceOver()) { RaceEnd(); GoToScreen(SCR_RESULTS); }
            break;
        }
        if (G.paused) {
            if (MenuUp()) Move(&G.pauseSel, 3, -1);
            if (MenuDown()) Move(&G.pauseSel, 3, 1);
            if (IsKeyPressed(KEY_P) || (MenuOk() && G.pauseSel == 0)) { G.paused = false; break; }
            if (MenuOk() && G.pauseSel == 1) {
                if (G.mode == MODE_GP) RaceStart(G.gpRace, false);
                else RaceStart(G.trackIndex, false);
                G.paused = false;
                break;
            }
            if (MenuOk() && G.pauseSel == 2) { G.paused = false; RaceStart(rand() % NUM_TRACKS, true); GoToScreen(SCR_TITLE); break; }
            if (IsKeyPressed(KEY_ESCAPE)) G.paused = false;
            break;
        }
        if (PausePressed() && R.phase != RACE_DONE) { G.paused = true; G.pauseSel = 0; PlaySfx(SFX_MENU_OK, 0.6f, 0.8f); for (int h = 0; h < MAX_HUMANS; h++) { EngineSet(h, 0, 0); DriftLoop(h, false, 0); } break; }
        if (R.phase == RACE_INTRO && R.phaseTime > 0.5f && MenuOk()) R.phaseTime = 2.6f;
        if (R.phase == RACE_DONE && (R.doneTimer > 4.5f || (R.doneTimer > 1.0f && MenuOk()))) {
            RaceEnd();
            GoToScreen(SCR_RESULTS);
        }
        break;
    case SCR_RESULTS:
        if (G.mode == MODE_ONLINE) {
            if (MenuOk() && G.screenTime > 0.6f) { PlaySfx(SFX_MENU_OK, 0.7f, 1); OnlineBackToLobby(); }
        } else if (G.mode == MODE_GP) {
            if (MenuOk() && G.screenTime > 0.6f) { PlaySfx(SFX_MENU_OK, 0.7f, 1); GoToScreen(SCR_STANDINGS); }
        } else {
            if (MenuUp()) Move(&G.menuSel, 3, -1);
            if (MenuDown()) Move(&G.menuSel, 3, 1);
            if (MenuOk() && G.screenTime > 0.6f) {
                PlaySfx(SFX_MENU_OK, 0.7f, 1);
                if (G.menuSel == 0) { RaceStart(G.trackIndex, false); GoToScreen(SCR_RACE); }
                else if (G.menuSel == 1) { RaceStart(G.trackIndex, true); GoToScreen(SCR_TRACK); G.menuSel = G.trackIndex; }
                else { RaceStart(rand() % NUM_TRACKS, true); GoToScreen(SCR_TITLE); }
            }
        }
        break;
    case SCR_STANDINGS:
        if (MenuOk() && G.screenTime > 0.6f) {
            PlaySfx(SFX_MENU_OK, 0.7f, 1);
            if (G.gpRace < NUM_TRACKS - 1) { G.gpRace++; RaceStart(G.gpRace, false); GoToScreen(SCR_RACE); }
            else { PlaySfx(SFX_FINISH, 0.9f, 1.0f); GoToScreen(SCR_TROPHY); }
        }
        break;
    case SCR_TROPHY:
        if (MenuOk() && G.screenTime > 1.5f) { PlaySfx(SFX_MENU_OK, 0.7f, 1); RaceStart(rand() % NUM_TRACKS, true); GoToScreen(SCR_TITLE); }
        break;
    }
}

/* ------------------------------------------------------------------ */
/* drawing                                                              */
/* ------------------------------------------------------------------ */
static float U(void) { return GetScreenHeight()/720.0f; }

static void Panel(Rectangle r, Color c)
{
    DrawRectangleRounded(r, 0.08f, 6, c);
    DrawRectangleRoundedLinesEx(r, 0.08f, 6, 3, (Color){ 255, 255, 255, 200 });
}

static void DrawLogo(int cx, int y, int size)
{
    const char *t = GAME_TITLE;
    int total = MeasureText(t, size) + (int)strlen(t)*2;
    int x = cx - total/2;
    for (int i = 0; t[i]; i++) {
        char ch[2] = { t[i], 0 };
        float bob = sinf(G.time*4.0f + i*0.45f)*size*0.08f;
        Color c = HueColor(i*24.0f + G.time*60.0f, 0.75f, 1.0f);
        if (t[i] == '6' || t[i] == '4') c = (Color){ 255, 255, 255, 255 };
        DrawTextOutlined(ch, x, y + (int)bob, size, c);
        x += MeasureText(ch, size) + 2 + size/12;
    }
}

static void RenderPreview(int charId)
{
    BeginTextureMode(G.preview);
    ClearBackground(BLANK);
    Camera3D cam = { 0 };
    cam.position = (Vector3){ 3.4f, 2.6f, 4.4f };
    cam.target = (Vector3){ 0, 0.9f, 0 };
    cam.up = (Vector3){ 0, 1, 0 };
    cam.fovy = 40;
    cam.projection = CAMERA_PERSPECTIVE;
    BeginMode3D(cam);
    rlDisableBackfaceCulling();
    DrawCylinder((Vector3){ 0, -0.12f, 0 }, 2.4f, 2.4f, 0.12f, 16, (Color){ 60, 60, 90, 255 });
    DrawCylinder((Vector3){ 0, -0.13f, 0 }, 2.6f, 2.6f, 0.1f, 16, (Color){ 255, 220, 80, 255 });
    DrawCharacterPreview(charId, G.time);
    rlDrawRenderBatchActive();
    rlEnableBackfaceCulling();
    EndMode3D();
    EndTextureMode();
}

static void StatBar(const char *label, float v, int x, int y, float u, Color c)
{
    DrawTextOutlined(label, x, y, (int)(18*u), WHITE);
    for (int i = 0; i < 5; i++) {
        Rectangle r = { x + 110*u + i*26*u, (float)y, 22*u, 16*u };
        bool on = v >= i + 0.75f;
        bool half = !on && v >= i + 0.25f;
        DrawRectangleRec(r, (Color){ 30, 30, 40, 220 });
        if (on) DrawRectangleRec(r, c);
        else if (half) DrawRectangle((int)r.x, (int)r.y, (int)(r.width/2), (int)r.height, c);
    }
}

static const char *WeightName(WeightClass w) { return w == WEIGHT_LIGHT ? "LIGHT" : (w == WEIGHT_MEDIUM ? "MEDIUM" : "HEAVY"); }

static void DrawCharSelect(void)
{
    int W = GetScreenWidth(), H = GetScreenHeight();
    float u = U();
    DrawTextCentered(G.numHumans == 2 ? "CHOOSE YOUR RACERS" : "CHOOSE YOUR RACER", W/2, (int)(18*u), (int)(46*u), (Color){ 255, 230, 80, 255 });
    int cols = 4, rows = (NUM_CHARACTERS + cols - 1)/cols;
    float cw = 190*u, ch = 70*u;
    float gx = W*0.5f - cols*cw*0.5f, gy = H - rows*(ch + 10*u) - 70*u;
    for (int i = 0; i < NUM_CHARACTERS; i++) {
        const CharacterDef *cd = &CHARACTERS[i];
        Rectangle r = { gx + (i % cols)*cw + 5*u, gy + (i/cols)*(ch + 10*u), cw - 10*u, ch };
        DrawRectangleRounded(r, 0.2f, 6, ColorScale(cd->kart, 0.55f));
        DrawRectangleRounded((Rectangle){ r.x + 6*u, r.y + 6*u, 16*u, r.height - 12*u }, 0.4f, 4, cd->body);
        DrawTextOutlined(cd->name, (int)(r.x + 30*u), (int)(r.y + 10*u), (int)(22*u), WHITE);
        DrawTextOutlined(WeightName(cd->weight), (int)(r.x + 30*u), (int)(r.y + 40*u), (int)(16*u), (Color){ 220, 220, 220, 255 });
        for (int p = 0; p < G.numHumans; p++) {
            if (G.charCursor[p] != i) continue;
            Color pc = p == 0 ? (Color){ 255, 60, 60, 255 } : (Color){ 60, 140, 255, 255 };
            float pulse = 2 + 2*sinf(G.time*8);
            DrawRectangleRoundedLinesEx((Rectangle){ r.x - pulse - p*4, r.y - pulse - p*4, r.width + 2*pulse + p*8, r.height + 2*pulse + p*8 }, 0.2f, 6, 4*u, pc);
            DrawTextOutlined(TextFormat("P%d%s", p + 1, G.charLocked[p] ? " OK!" : ""), (int)(r.x + r.width - 62*u), (int)(r.y + 40*u), (int)(16*u), pc);
        }
    }
    /* preview panels */
    for (int p = 0; p < G.numHumans; p++) {
        int c = G.charCursor[p];
        const CharacterDef *cd = &CHARACTERS[c];
        float pw = 300*u, ph = 300*u;
        float px = G.numHumans == 2 ? (p == 0 ? W*0.25f - pw*0.5f - 60*u : W*0.75f - pw*0.5f - 60*u) : W*0.5f - pw - 60*u;
        float py = 80*u;
        RenderPreview(c);
        DrawTexturePro(G.preview.texture, (Rectangle){ 0, 0, 420, -420 }, (Rectangle){ px, py, pw, ph }, (Vector2){ 0, 0 }, 0, WHITE);
        float sx = G.numHumans == 2 ? px + pw - 40*u : W*0.5f + 10*u;
        float sy = py + 30*u;
        if (G.numHumans == 2) { sx = px + 40*u; sy = py + ph - 10*u; }
        DrawTextOutlined(cd->name, (int)sx, (int)sy, (int)(36*u), cd->body.r + cd->body.g + cd->body.b < 200 ? cd->accent : cd->body);
        DrawTextOutlined(TextFormat("%s CLASS", WeightName(cd->weight)), (int)sx, (int)(sy + 42*u), (int)(18*u), (Color){ 255, 230, 150, 255 });
        if (G.numHumans == 1) {
            StatBar("SPEED", cd->topSpeed, (int)sx, (int)(sy + 80*u), u, (Color){ 255, 90, 90, 255 });
            StatBar("ACCEL", cd->accel, (int)sx, (int)(sy + 106*u), u, (Color){ 90, 255, 120, 255 });
            StatBar("HANDLING", cd->handling, (int)sx, (int)(sy + 132*u), u, (Color){ 90, 170, 255, 255 });
            StatBar("WEIGHT", cd->mass, (int)sx, (int)(sy + 158*u), u, (Color){ 255, 200, 80, 255 });
            DrawTextOutlined(TextFormat("\"%s\"", cd->tagline), (int)sx, (int)(sy + 196*u), (int)(16*u), (Color){ 230, 230, 255, 255 });
        }
    }
    const char *hint = G.numHumans == 2 ? "P1: WASD + SPACE (Q back)    P2: ARROWS + ENTER (BACKSPACE back)" : "ARROWS / WASD to choose   ENTER to confirm   ESC back";
    DrawTextCentered(hint, W/2, (int)(H - 40*u), (int)(18*u), WHITE);
}

static void DrawTrackCard(int i, Rectangle r, bool sel)
{
    const TrackDef *d = &TRACK_DEFS[i];
    float u = U();
    DrawRectangleRounded(r, 0.1f, 6, ColorMix(d->skyTop, BLACK, 0.3f));
    DrawRectangleRounded((Rectangle){ r.x + 6, r.y + r.height*0.55f, r.width - 12, r.height*0.45f - 6 }, 0.1f, 6, ColorMix(d->ground, BLACK, 0.35f));
    if (sel) DrawRectangleRoundedLinesEx(r, 0.1f, 6, 5*u, (Color){ 255, 230, 60, 255 });
    else DrawRectangleRoundedLinesEx(r, 0.1f, 6, 2*u, (Color){ 255, 255, 255, 160 });
    Vector2 pts[128]; int n = 0;
    TrackOutline(i, pts, 128, &n);
    Vector2 mn = { 1e9f, 1e9f }, mx = { -1e9f, -1e9f };
    for (int k = 0; k < n; k++) { mn.x = fminf(mn.x, pts[k].x); mn.y = fminf(mn.y, pts[k].y); mx.x = fmaxf(mx.x, pts[k].x); mx.y = fmaxf(mx.y, pts[k].y); }
    Rectangle area = { r.x + 20*u, r.y + 20*u, r.width - 40*u, r.height*0.62f };
    float s = fminf(area.width/(mx.x - mn.x), area.height/(mx.y - mn.y));
    float ox = area.x + (area.width - (mx.x - mn.x)*s)*0.5f, oy = area.y + (area.height - (mx.y - mn.y)*s)*0.5f;
    for (int pass = 0; pass < 2; pass++) {
        for (int k = 0; k < n; k++) {
            Vector2 a = pts[k], b = pts[(k + 1) % n];
            Vector2 A = { ox + (mx.x - a.x)*s, oy + (mx.y - a.y)*s }, B = { ox + (mx.x - b.x)*s, oy + (mx.y - b.y)*s };
            Color c = pass ? (d->rainbowRoad ? HueColor(k*10.0f + G.time*100, 0.6f, 1) : WHITE) : BLACK;
            DrawLineEx(A, B, pass ? 4*u : 9*u, c);
        }
    }
    DrawTextOutlined(d->name, (int)(r.x + 12*u), (int)(r.y + r.height - 56*u), (int)(22*u), WHITE);
    if (d->numBumps > 0) DrawTextOutlined("BUMPY!", (int)(r.x + r.width - 80*u), (int)(r.y + 10*u), (int)(14*u), (Color){ 255, 160, 80, 255 });
    DrawTextOutlined("+ shortcut", (int)(r.x + 12*u), (int)(r.y + 10*u), (int)(14*u), (Color){ 160, 255, 200, 255 });
    if (G.mode == MODE_TT && G.bestTimes[i] > 0)
        DrawTextOutlined(TextFormat("BEST %s", FormatTime(G.bestTimes[i])), (int)(r.x + 12*u), (int)(r.y + r.height - 24*u), (int)(14*u), (Color){ 120, 255, 160, 255 });
}

static void DrawResults(void)
{
    int W = GetScreenWidth();
    float u = U();
    Rectangle p = { W*0.5f - 330*u, 60*u, 660*u, 560*u };
    Panel(p, (Color){ 10, 10, 40, 210 });
    DrawTextCentered(R.timeTrial ? "TIME TRIAL" : "RACE RESULTS", W/2, (int)(78*u), (int)(40*u), (Color){ 255, 230, 60, 255 });
    DrawTextCentered(T.def->name, W/2, (int)(124*u), (int)(20*u), WHITE);
    int order[MAX_RACERS] = { 0 };
    for (int i = 0; i < R.numKarts; i++) order[R.karts[i].place - 1] = i;
    static const int pts[8] = { 9, 6, 3, 1, 0, 0, 0, 0 };
    for (int r = 0; r < R.numKarts; r++) {
        Kart *k = &R.karts[order[r]];
        const CharacterDef *cd = &CHARACTERS[k->charId];
        float y = 160*u + r*48*u;
        float appear = Clamp(G.screenTime*6.0f - r, 0, 1);
        float x = p.x + 30*u + (1.0f - appear)*400*u;
        Color rc = k->human >= 0 ? (Color){ 255, 255, 140, 255 } : WHITE;
        if (k->human >= 0) DrawRectangle((int)(p.x + 12*u), (int)(y - 4*u), (int)(p.width - 24*u), (int)(40*u), (Color){ 255, 255, 255, 40 });
        DrawTextOutlined(TextFormat("%d%s", r + 1, OrdinalSuffix(r + 1)), (int)x, (int)y, (int)(30*u), rc);
        DrawRectangle((int)(x + 80*u), (int)(y + 2*u), (int)(26*u), (int)(26*u), cd->kart);
        DrawRectangle((int)(x + 86*u), (int)(y + 8*u), (int)(14*u), (int)(14*u), cd->body);
        DrawTextOutlined(TextFormat("%s%s", cd->name, k->human >= 0 ? TextFormat(" (P%d)", k->human + 1) : ""), (int)(x + 120*u), (int)y, (int)(26*u), rc);
        DrawTextOutlined(FormatTime(k->finishTime), (int)(x + 400*u), (int)y, (int)(26*u), rc);
        if (G.mode == MODE_GP) DrawTextOutlined(TextFormat("+%d", pts[r]), (int)(x + 560*u), (int)y, (int)(26*u), (Color){ 120, 255, 140, 255 });
    }
    if (R.timeTrial) {
        Kart *k = &R.karts[0];
        DrawTextCentered(TextFormat("BEST LAP %s", FormatTime(k->bestLap)), W/2, (int)(240*u), (int)(26*u), (Color){ 160, 220, 255, 255 });
        DrawTextCentered(TextFormat("RECORD %s", FormatTime(G.bestTimes[T.index])), W/2, (int)(280*u), (int)(26*u), (Color){ 120, 255, 160, 255 });
    }
    if (G.mode == MODE_ONLINE) {
        DrawTextCentered("PRESS ENTER - back to the online room", W/2, (int)(p.y + p.height + 14*u), (int)(24*u), ((int)(G.time*2) & 1) ? WHITE : (Color){ 255, 230, 60, 255 });
    } else if (G.mode != MODE_GP) {
        const char *opts[3] = { "RACE AGAIN", "CHANGE TRACK", "MAIN MENU" };
        for (int i = 0; i < 3; i++) {
            Color c = i == G.menuSel ? (Color){ 255, 230, 60, 255 } : WHITE;
            DrawTextOutlined(opts[i], (int)(W*0.5f - 380*u + i*270*u), (int)(p.y + p.height + 14*u), (int)(26*u), c);
        }
    } else {
        DrawTextCentered("PRESS ENTER", W/2, (int)(p.y + p.height + 14*u), (int)(24*u), ((int)(G.time*2) & 1) ? WHITE : (Color){ 255, 230, 60, 255 });
    }
}

static void DrawTrophy(int cx, int cy, float s, Color c)
{
    DrawRectangle(cx - (int)(s*0.35f), cy + (int)(s*0.55f), (int)(s*0.7f), (int)(s*0.15f), ColorScale(c, 0.6f));
    DrawRectangle(cx - (int)(s*0.08f), cy + (int)(s*0.25f), (int)(s*0.16f), (int)(s*0.32f), ColorScale(c, 0.8f));
    DrawCircleSector((Vector2){ (float)cx, (float)cy - s*0.1f }, s*0.42f, 0, 180, 16, c);
    DrawRectangle(cx - (int)(s*0.42f), cy - (int)(s*0.45f), (int)(s*0.84f), (int)(s*0.36f), c);
    DrawRing((Vector2){ cx - s*0.42f, cy - s*0.2f }, s*0.12f, s*0.19f, 90, 270, 12, c);
    DrawRing((Vector2){ cx + s*0.42f, cy - s*0.2f }, s*0.12f, s*0.19f, -90, 90, 12, c);
    DrawRectangle(cx - (int)(s*0.3f), cy - (int)(s*0.4f), (int)(s*0.08f), (int)(s*0.4f), ColorScale(c, 1.3f));
}

static void DrawStandings(void)
{
    int W = GetScreenWidth();
    float u = U();
    bool final = G.gpRace >= NUM_TRACKS - 1;
    Rectangle p = { W*0.5f - 330*u, 60*u, 660*u, 560*u };
    Panel(p, (Color){ 10, 10, 40, 210 });
    DrawTextCentered(final ? "FINAL CUP STANDINGS" : TextFormat("CUP STANDINGS  (RACE %d/%d)", G.gpRace + 1, NUM_TRACKS), W/2, (int)(78*u), (int)(34*u), (Color){ 255, 230, 60, 255 });
    DrawTextOutlined("LAST RACE", (int)(p.x + 262*u), (int)(118*u), (int)(12*u), (Color){ 190, 190, 220, 255 });
    int order[MAX_RACERS] = { 0 };
    for (int i = 0; i < R.numKarts; i++) order[i] = i;
    for (int i = 0; i < R.numKarts; i++) for (int j = i + 1; j < R.numKarts; j++)
        if (G.gpPoints[order[j]] > G.gpPoints[order[i]]) { int t = order[i]; order[i] = order[j]; order[j] = t; }
    int maxPts = G.gpPoints[order[0]] > 0 ? G.gpPoints[order[0]] : 1;
    for (int r = 0; r < R.numKarts; r++) {
        int i = order[r];
        Kart *k = &R.karts[i];
        const CharacterDef *cd = &CHARACTERS[k->charId];
        float y = 140*u + r*50*u;
        Color rc = k->human >= 0 ? (Color){ 255, 255, 140, 255 } : WHITE;
        DrawTextOutlined(TextFormat("%d", r + 1), (int)(p.x + 26*u), (int)y, (int)(28*u), rc);
        DrawTextOutlined(cd->name, (int)(p.x + 66*u), (int)y, (int)(24*u), rc);
        float bw = 210*u*G.gpPoints[i]/maxPts*Clamp(G.screenTime*1.5f, 0, 1);
        DrawRectangle((int)(p.x + 330*u), (int)(y + 2*u), (int)bw, (int)(24*u), cd->kart);
        DrawTextOutlined(TextFormat("%d", G.gpPoints[i]), (int)(p.x + 338*u + bw), (int)y, (int)(24*u), rc);
        if (G.gpLastPoints[i] > 0 && G.screenTime < 6.0f) {
            float pulse = 0.5f + 0.5f*sinf(G.time*8.0f);
            DrawTextOutlined(TextFormat("+%d", G.gpLastPoints[i]), (int)(p.x + 384*u + bw), (int)y, (int)(22*u), ColorMix((Color){ 120, 255, 140, 255 }, WHITE, pulse*0.4f));
        }
        if (G.gpLastPlace[i] > 0)
            DrawTextOutlined(TextFormat("%d%s", G.gpLastPlace[i], OrdinalSuffix(G.gpLastPlace[i])), (int)(p.x + 278*u), (int)(y + 5*u), (int)(16*u), (Color){ 190, 190, 220, 255 });
    }
    if (final) {
        int champ = order[0];
        const CharacterDef *cd = &CHARACTERS[R.karts[champ].charId];
        int myRank = 0;
        for (int r = 0; r < R.numKarts; r++) if (R.karts[order[r]].human >= 0) myRank = r + 1;
        Color tc = myRank == 1 ? (Color){ 255, 210, 40, 255 } : myRank == 2 ? (Color){ 210, 215, 230, 255 } : myRank == 3 ? (Color){ 210, 140, 70, 255 } : (Color){ 120, 120, 140, 255 };
        DrawTrophy((int)(p.x + p.width + 110*u), (int)(240*u), 150*u, tc);
        DrawTextCentered(TextFormat("CHAMPION: %s!", cd->name), W/2, (int)(p.y + p.height - 50*u), (int)(32*u), HueColor(G.time*200, 0.6f, 1));
        DrawTextCentered("PRESS ENTER FOR THE TROPHY CEREMONY", W/2, (int)(p.y + p.height + 14*u), (int)(24*u), ((int)(G.time*2) & 1) ? WHITE : tc);
    } else {
        DrawTextCentered(TextFormat("NEXT: %s  -  PRESS ENTER", TRACK_DEFS[G.gpRace + 1].name), W/2, (int)(p.y + p.height + 14*u), (int)(24*u), ((int)(G.time*2) & 1) ? WHITE : (Color){ 255, 230, 60, 255 });
    }
}

/* ------------------------------------------------------------------ */
/* Cup ceremony: podium with the top three, a spinning 3D trophy and     */
/* confetti. Rendered like the race (low-res RT in ORIGINAL).            */
/* ------------------------------------------------------------------ */
static unsigned HashU(unsigned x) { x ^= x >> 16; x *= 0x7feb352du; x ^= x >> 15; x *= 0x846ca68bu; x ^= x >> 16; return x; }
static float HashF(unsigned x) { return (HashU(x) & 0xffffff)/16777216.0f; }

static void CupOrder(int *order)
{
    for (int i = 0; i < R.numKarts; i++) order[i] = i;
    for (int i = 0; i < R.numKarts; i++) for (int j = i + 1; j < R.numKarts; j++)
        if (G.gpPoints[order[j]] > G.gpPoints[order[i]]) { int t = order[i]; order[i] = order[j]; order[j] = t; }
}

static void DrawTrophyScene(void)
{
    int order[MAX_RACERS];
    CupOrder(order);
    int myRank = 0;
    for (int r = 0; r < R.numKarts; r++) if (R.karts[order[r]].human >= 0) myRank = r + 1;
    float t = G.screenTime;
    Camera3D cam = { 0 };
    float orbit = 0.25f*sinf(t*0.35f);
    cam.position = (Vector3){ sinf(orbit)*14.0f, 4.6f + 0.6f*sinf(t*0.5f), cosf(orbit)*14.0f };
    cam.target = (Vector3){ 0.8f, 2.0f, 0 };
    cam.up = (Vector3){ 0, 1, 0 }; cam.fovy = 48; cam.projection = CAMERA_PERSPECTIVE;
    BeginMode3D(cam);
    rlDisableBackfaceCulling();
    /* stage */
    DrawCylinder((Vector3){ 0, -0.2f, 0 }, 13.0f, 13.0f, 0.2f, 48, (Color){ 120, 25, 40, 255 });
    DrawCylinder((Vector3){ 0, -0.19f, 0 }, 9.0f, 9.0f, 0.2f, 48, (Color){ 160, 35, 50, 255 });
    float podH[3] = { 1.7f, 1.15f, 0.75f }, podX[3] = { -1.6f, -5.0f, 1.8f };
    Color podC[3] = { { 255, 205, 50, 255 }, { 200, 205, 220, 255 }, { 205, 125, 60, 255 } };
    for (int r = 0; r < 3 && r < R.numKarts; r++) {
        DrawLitRoundBox((Vector3){ podX[r], podH[r]*0.5f, 0 }, (Vector3){ 3.2f, podH[r], 3.0f }, 0.15f, 1, 1, podC[r], ColorScale(podC[r], 0.6f));
        Kart k; memset(&k, 0, sizeof k);
        k.scale = 1; k.charId = R.karts[order[r]].charId;
        k.pos = (Vector3){ podX[r], podH[r], 0.1f };
        k.heading = 0.25f*sinf(t*0.8f + r);
        k.steer = 0.3f*sinf(t*2.0f + r);
        k.squash = r == 0 ? 0.12f*fmaxf(0, sinf(t*6.0f)) : 0;
        k.pos.y += r == 0 ? 0.25f*fmaxf(0, sinf(t*3.0f)) : 0;      /* the winner hops for joy */
        DrawCharacterKart(k.charId, &k, G.time + r);
    }
    /* the trophy */
    int tier = myRank >= 1 && myRank <= 3 ? myRank - 1 : 0;
    rlPushMatrix();
    rlTranslatef(5.6f, 0.4f + 0.15f*sinf(t*2.0f), 1.0f);
    rlRotatef(t*50.0f, 0, 1, 0);
    rlScalef(1.6f, 1.6f, 1.6f);
    DrawTrophyModel(tier, t);
    rlPopMatrix();
    rlDrawRenderBatchActive();
    /* light sparkles around the cup */
    BeginBlendMode(BLEND_ADDITIVE);
    for (int i = 0; i < 14; i++) {
        float a = t*1.5f + i*0.45f, rr = 1.6f + 0.4f*sinf(t*3 + i);
        Vector3 sp = { 5.6f + cosf(a)*rr, 2.2f + 1.6f*sinf(a*0.7f + i), 1.0f + sinf(a)*rr };
        float sz = 0.12f + 0.08f*sinf(t*9 + i);
        DrawCube(sp, sz, sz, sz, (Color){ 255, 240, 160, 200 });
    }
    rlDrawRenderBatchActive();
    EndBlendMode();
    rlEnableBackfaceCulling();
    EndMode3D();
}

static void DrawTrophyScreen(void)
{
    int W = GetScreenWidth(), H = GetScreenHeight();
    float u = U();
    int order[MAX_RACERS];
    CupOrder(order);
    int myRank = 0;
    for (int r = 0; r < R.numKarts; r++) if (R.karts[order[r]].human >= 0) myRank = r + 1;
    bool direct = RenderDirect();
    if (direct) {
        ClearBackground((Color){ 30, 20, 80, 255 });
        DrawRectangleGradientV(0, 0, W, H, (Color){ 30, 20, 80, 255 }, (Color){ 230, 120, 170, 255 });
        rlDrawRenderBatchActive();
        DrawTrophyScene();
    } else {
        BeginTextureMode(G.view[0]);
        ClearBackground((Color){ 30, 20, 80, 255 });
        DrawRectangleGradientV(0, 0, G.viewW, G.viewH, (Color){ 30, 20, 80, 255 }, (Color){ 230, 120, 170, 255 });
        rlDrawRenderBatchActive();
        DrawTrophyScene();
        EndTextureMode();
        ClearBackground(BLACK);
        int dw = G.viewW*G.viewScale, dh = G.viewH*G.viewScale;
        rlDrawRenderBatchActive(); rlDisableColorBlend();
        DrawTexturePro(G.view[0].texture, (Rectangle){ 0, 0, (float)G.viewW, -(float)G.viewH }, (Rectangle){ (float)(W - dw)/2, (float)(H - dh)/2, (float)dw, (float)dh }, (Vector2){ 0, 0 }, 0, WHITE);
        rlDrawRenderBatchActive(); rlEnableColorBlend();
    }
    /* confetti */
    float t = G.screenTime;
    for (int i = 0; i < 160; i++) {
        float sp = 60 + HashF(i*3 + 1)*120;
        float x = HashF(i*3 + 2)*W + sinf(t*1.7f + i)*25*u;
        float y = fmodf(t*sp*u + HashF(i*3 + 3)*(H + 40), (float)H + 40) - 20;
        Color c = HueColor(HashF(i*7)*360.0f, 0.7f, 1.0f);
        DrawRectanglePro((Rectangle){ x, y, 9*u, 5*u }, (Vector2){ 4.5f*u, 2.5f*u }, t*200.0f*(HashF(i) - 0.5f) + i*30, c);
    }
    const char *title = myRank == 1 ? "GOLD CUP!" : myRank == 2 ? "SILVER CUP!" : myRank == 3 ? "BRONZE CUP!" : "CUP COMPLETE";
    Color tc = myRank == 1 ? (Color){ 255, 215, 50, 255 } : myRank == 2 ? (Color){ 220, 225, 240, 255 } : myRank == 3 ? (Color){ 230, 150, 80, 255 } : WHITE;
    float sc = 1.0f + 0.06f*sinf(G.time*4.0f);
    DrawTextCentered(title, W/2, (int)(28*u), (int)(72*u*sc), tc);
    DrawTextCentered(TRACK_CUP_NAME, W/2, (int)(110*u), (int)(24*u), WHITE);
    for (int r = 0; r < 3 && r < R.numKarts; r++) {
        const CharacterDef *cd = &CHARACTERS[R.karts[order[r]].charId];
        Color c = R.karts[order[r]].human >= 0 ? (Color){ 255, 255, 140, 255 } : WHITE;
        DrawTextOutlined(TextFormat("%d%s  %-13s %3d pts", r + 1, OrdinalSuffix(r + 1), cd->name, G.gpPoints[order[r]]), (int)(40*u), (int)(H - 150*u + r*34*u), (int)(26*u), c);
    }
    if (myRank > 3) DrawTextOutlined(TextFormat("You finished %d%s overall - so close!", myRank, OrdinalSuffix(myRank)), (int)(40*u), (int)(H - 190*u), (int)(22*u), WHITE);
    if (G.screenTime > 1.5f) DrawTextCentered("PRESS ENTER", (int)(W*0.78f), (int)(H - 60*u), (int)(26*u), ((int)(G.time*2) & 1) ? WHITE : tc);
}

void MenusDraw(void)
{
    int W = GetScreenWidth(), H = GetScreenHeight();
    float u = U();
    if (G.screen == SCR_TROPHY) { DrawTrophyScreen(); return; }
    RaceDraw();
    if (G.screen == SCR_RACE) {
        if (G.mode == MODE_ONLINE) OnlineDrawRaceStatus();
        if (G.paused) {
            DrawRectangle(0, 0, W, H, (Color){ 0, 0, 0, 140 });
            DrawTextCentered("PAUSED", W/2, (int)(H*0.28f), (int)(64*u), (Color){ 255, 230, 60, 255 });
            const char *opts[3] = { "RESUME", "RESTART", "QUIT TO TITLE" };
            for (int i = 0; i < 3; i++)
                DrawTextCentered(opts[i], W/2, (int)(H*0.42f + i*50*u), (int)(34*u), i == G.pauseSel ? (Color){ 255, 230, 60, 255 } : WHITE);
        }
        return;
    }
    if (G.screen == SCR_RESULTS) { DrawRectangle(0, 0, W, H, (Color){ 0, 0, 0, 90 }); DrawResults(); return; }
    if (G.screen == SCR_STANDINGS) { DrawRectangle(0, 0, W, H, (Color){ 0, 0, 0, 90 }); DrawStandings(); return; }

    if (G.screen == SCR_ONLINE) { OnlineDraw(); return; }
    DrawRectangle(0, 0, W, H, (Color){ 0, 0, 20, G.screen == SCR_TITLE ? 60 : 150 });
    switch (G.screen) {
    case SCR_TITLE: {
        DrawLogo(W/2, (int)(70*u), (int)(92*u));
        DrawTextCentered("an original kart racer", W/2, (int)(180*u), (int)(24*u), (Color){ 255, 240, 200, 255 });
        if ((int)(G.time*2.0f) % 2 == 0) DrawTextCentered("PRESS ENTER / START", W/2, (int)(250*u), (int)(36*u), WHITE);
        Rectangle cp = { W*0.5f - 360*u, 320*u, 720*u, 330*u };
        Panel(cp, (Color){ 0, 0, 30, 190 });
        DrawTextCentered("CONTROLS", W/2, (int)(cp.y + 12*u), (int)(26*u), (Color){ 255, 220, 60, 255 });
        const char *lines[] = {
            "Accelerate ......... W / UP / X          (pad A)",
            "Brake / Reverse .... S / DOWN / Z        (pad B / X)",
            "Steer .............. A D / LEFT RIGHT    (stick / d-pad)",
            "Hop + Drift ........ SPACE / SHIFT / C   (pad RB / RT)",
            "Use item ........... E / CTRL / V        (pad LB / LT / Y)",
            "Pause .............. ESC / P             (pad START)",
            "Hold drift + steer for BLUE then ORANGE sparks, release to boost!",
            "F2: toggle N64 pixel look     F11: fullscreen",
        };
        for (int i = 0; i < 8; i++)
            DrawTextOutlined(lines[i], (int)(cp.x + 30*u), (int)(cp.y + 52*u + i*33*u), (int)(18*u), i >= 6 ? (Color){ 160, 230, 255, 255 } : WHITE);
        DrawText("All graphics, music and sounds generated in code.  v" GAME_VERSION, (int)(10*u), H - (int)(22*u), (int)(14*u), (Color){ 220, 220, 220, 200 });
    } break;
    case SCR_MODE: {
        DrawLogo(W/2, (int)(50*u), (int)(60*u));
        const char *opts[6] = { "GRAND PRIX", "TIME TRIAL", "VS  (2 PLAYERS)", "ONLINE VS", "OPTIONS", "QUIT" };
        const char *desc[6] = { "Race all 4 tracks for the Tumble Cup. Points: 9-6-3-1.",
                                "Just you, the clock and three hot peppers.",
                                "Split-screen showdown with 6 CPU rivals.",
                                "Race a friend over the internet: quick match or a room code.",
                                "Engine class, display style, volume.", "See you next time!" };
        for (int i = 0; i < 6; i++) {
            bool s = i == G.menuSel;
            Rectangle r = { W*0.5f - 240*u, 160*u + i*74*u, 480*u, 60*u };
            DrawRectangleRounded(r, 0.3f, 6, s ? (Color){ 230, 60, 60, 230 } : (Color){ 30, 30, 70, 210 });
            if (s) DrawRectangleRoundedLinesEx(r, 0.3f, 6, 4*u, (Color){ 255, 230, 60, 255 });
            DrawTextCentered(opts[i], W/2, (int)(r.y + 12*u), (int)(36*u), WHITE);
        }
        DrawTextCentered(desc[G.menuSel], W/2, (int)(H - 60*u), (int)(22*u), (Color){ 255, 240, 200, 255 });
        DrawTextCentered(TextFormat("Engine class: %dcc", G.settings.cc == 0 ? 50 : G.settings.cc == 1 ? 100 : 150), W/2, (int)(H - 30*u), (int)(18*u), (Color){ 180, 220, 255, 255 });
    } break;
    case SCR_OPTIONS: {
        DrawTextCentered("OPTIONS", W/2, (int)(50*u), (int)(56*u), (Color){ 255, 230, 60, 255 });
        const char *disp[2] = { "ORIGINAL (N64 320x240)", "ENHANCED (HD + 4x MSAA)" };
        const char *padm[3] = { "AUTO", "STANDARD (XInput / SDL db)", "RAW (DirectInput)" };
        const char *labels[8] = { "Engine class", "Visual mode", "Music volume", "SFX volume", "Show FPS", "Pad mode", "Controller setup...", "Back" };
        static char vb[8][64];
        snprintf(vb[0], 64, "< %dcc >", G.settings.cc == 0 ? 50 : G.settings.cc == 1 ? 100 : 150);
        snprintf(vb[1], 64, "< %s >", disp[G.settings.visualMode]);
        snprintf(vb[2], 64, "< %d%% >", (int)(G.settings.musicVol*100 + 0.5f));
        snprintf(vb[3], 64, "< %d%% >", (int)(G.settings.sfxVol*100 + 0.5f));
        snprintf(vb[4], 64, "< %s >", G.settings.showFps ? "ON" : "OFF");
        snprintf(vb[5], 64, "< %s >", padm[G.settings.padMode]);
        vb[6][0] = vb[7][0] = 0;
        for (int i = 0; i < 8; i++) {
            Color c = i == G.menuSel ? (Color){ 255, 230, 60, 255 } : WHITE;
            DrawTextOutlined(labels[i], (int)(W*0.5f - 400*u), (int)(140*u + i*54*u), (int)(30*u), c);
            DrawTextOutlined(vb[i], (int)(W*0.5f - 20*u), (int)(140*u + i*54*u), (int)(28*u), c);
        }
        const char *pn = PadPlayerName(0);
        const char *pn2 = PadPlayerName(1);
        DrawTextCentered(pn ? TextFormat("Controller 1: %s%s", pn, PadPlayerUsesRaw(0) ? "" : "  (standard gamepad)") : "Controller 1: none detected - plug in a pad any time",
                         W/2, (int)(H - 110*u), (int)(22*u), pn ? (Color){ 140, 255, 140, 255 } : (Color){ 255, 180, 120, 255 });
        if (pn2) DrawTextCentered(TextFormat("Controller 2: %s", pn2), W/2, (int)(H - 82*u), (int)(22*u), (Color){ 140, 255, 140, 255 });
        DrawTextCentered("UP / DOWN select   LEFT / RIGHT change   F2 toggles visual mode in game   ESC back", W/2, (int)(H - 45*u), (int)(20*u), WHITE);
    } break;
    case SCR_CONTROLS: {
        DrawTextCentered("CONTROLLER SETUP", W/2, (int)(40*u), (int)(52*u), (Color){ 255, 230, 60, 255 });
        const char *pn = PadPlayerName(0);
        int set = PadPlayerUsesRaw(0) ? 1 : 0;
        DrawTextCentered(pn ? TextFormat("%s  -  %s bindings", pn, set ? "raw / DirectInput" : "standard gamepad") : "No controller detected (keyboard always works)",
                         W/2, (int)(110*u), (int)(24*u), pn ? (Color){ 140, 255, 140, 255 } : (Color){ 255, 180, 120, 255 });
        for (int i = 0; i < 7; i++) {
            Color c = i == G.menuSel ? (Color){ 255, 230, 60, 255 } : WHITE;
            int y = (int)(170*u + i*52*u);
            if (i < NUM_PAD_ACTIONS) {
                DrawTextOutlined(PadActionName(i), (int)(W*0.5f - 400*u), y, (int)(28*u), c);
                const char *bt;
                if (G.remapAction == i) bt = ((int)(G.time*3) & 1) ? "press a button..." : "";
                else {
                    const char *b0 = BindName(gBinds[set][i][0]);
                    bt = gBinds[set][i][1].kind ? TextFormat("%s  /  %s", b0, BindName(gBinds[set][i][1])) : b0;
                }
                DrawTextOutlined(bt, (int)(W*0.5f + 40*u), y, (int)(26*u), c);
            } else {
                DrawTextOutlined(i == 5 ? "Reset to N64-style defaults" : "Back", (int)(W*0.5f - 400*u), y, (int)(28*u), c);
            }
        }
        DrawTextCentered("Steering: left stick or D-pad.  Select an action and press ENTER / A, then press the new button.", W/2, (int)(H - 80*u), (int)(20*u), WHITE);
        DrawTextCentered("EasySMX pad not responding? Hold its HOME/mode button to switch to X-input mode, or set Pad mode to RAW.", W/2, (int)(H - 50*u), (int)(20*u), (Color){ 255, 220, 150, 255 });
    } break;
    case SCR_CHAR: DrawCharSelect(); break;
    case SCR_TRACK: {
        DrawTextCentered("CHOOSE A TRACK", W/2, (int)(24*u), (int)(46*u), (Color){ 255, 230, 60, 255 });
        float cw = 330*u, chh = 225*u;
        float x0 = W*0.5f - 1.5f*cw - 15*u;
        for (int i = 0; i < NUM_TRACKS; i++) {
            int col = i % 3, row = i/3;
            Rectangle r = { x0 + col*(cw + 15*u), 85*u + row*(chh + 18*u) + (i == G.menuSel ? -6*u : 0), cw, chh };
            DrawTrackCard(i, r, i == G.menuSel);
        }
        {
            const TrackDef *sd = &TRACK_DEFS[G.menuSel];
            DrawTextCentered(TextFormat("%s  -  %s", sd->name, sd->subtitle), W/2, (int)(H - 112*u), (int)(22*u), WHITE);
            DrawTextCentered(TextFormat("SECRET: %s", sd->scHint), W/2, (int)(H - 82*u), (int)(19*u), (Color){ 255, 215, 120, 255 });
        }
        DrawTextCentered("LEFT / RIGHT to choose   ENTER to race   ESC back", W/2, (int)(H - 50*u), (int)(20*u), WHITE);
    } break;
    default: break;
    }
}

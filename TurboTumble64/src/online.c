/* ONLINE VS: two players race over the shared c_games relay (shared/netplay).
   Both machines run the whole race (both humans + the CPU karts) in lockstep at
   SIM_DT with the same inputs and seed; each window shows only its own kart. */
#include "common.h"
#include "online.h"
#include "../../shared/netplay/c/netplay.h"

#include <stdint.h>
#include <time.h>

#define DEFAULT_SERVER "ws://localhost:3000/turbo"
#define DONE_HOLD 4.5f   /* seconds after both humans finish, then results (same frame on both) */

static struct {
    Netplay *np;
    char url[256];
    char userId[40];
    int menu;            /* 0 quick 1 create 2 join 3 back */
    bool typing;
    char code[8];
    char note[128];
    float noteT;
    int savedCc;
    uint16_t latch;
    bool raceOver;
    /* test hooks: TT_ONLINE=quick|create|join:CODE, TT_ONLINE_PICK=c:t:cc, TT_ONLINE_BOT, TT_ONLINE_QUIT_AT */
    bool autoPick;
    int autoQuitAt;
    uint32_t botRng;
} O;

static void Note(const char *s) { snprintf(O.note, sizeof O.note, "%s", s); O.noteT = 6.0f; }

static void ReadCfg(void)
{
    if (!FileExists("netplay.cfg")) return;
    char *text = LoadFileText("netplay.cfg");
    if (!text) return;
    for (char *line = strtok(text, "\r\n"); line; line = strtok(NULL, "\r\n")) {
        while (*line == ' ') line++;
        if (strncmp(line, "server", 6) != 0) continue;
        char *v = strchr(line, '=');
        if (!v) continue;
        v++;
        while (*v == ' ') v++;
        if (*v) snprintf(O.url, sizeof O.url, "%s", v);
    }
    UnloadFileText(text);
}

void OnlineConfigure(int argc, char **argv)
{
    snprintf(O.url, sizeof O.url, "%s", DEFAULT_SERVER);
    ReadCfg();
    if (getenv("TT_SERVER")) snprintf(O.url, sizeof O.url, "%s", getenv("TT_SERVER"));
    for (int i = 1; i + 1 < argc; i++) if (strcmp(argv[i], "--server") == 0) snprintf(O.url, sizeof O.url, "%s", argv[i + 1]);
    int local;
    uint32_t mix = (uint32_t)time(NULL) ^ (uint32_t)clock()*2654435761u ^ (uint32_t)(uintptr_t)&local;
    snprintf(O.userId, sizeof O.userId, "tt-%08x%04x", (unsigned)mix, (unsigned)(rand() & 0xffff));
    G.netView = -1;
}

bool OnlineActive(void) { return O.np != NULL; }

void OnlineEnter(void)
{
    if (!O.url[0]) OnlineConfigure(0, NULL);
    if (!O.np) O.np = Np_New(O.url, O.userId);
    G.mode = MODE_ONLINE;
    G.numHumans = 1;          /* menus: one cursor (this window's player) */
    G.netView = -1;
    O.typing = false;
    O.menu = 0;
    O.savedCc = G.settings.cc;
    GoToScreen(SCR_ONLINE);
}

static void LeaveOnline(void)
{
    if (O.np) Np_Free(O.np);
    O.np = NULL;
    G.netView = -1;
    G.settings.cc = O.savedCc;
    G.mode = MODE_VS;
    RaceStart(rand() % NUM_TRACKS, true);
    GoToScreen(SCR_MODE);
    G.menuSel = 3;
}

void OnlineShutdown(void)
{
    if (O.np) Np_Free(O.np);
    O.np = NULL;
}

/* pick = "<character>:<track>:<cc>"; slot 0's track and engine class are raced */
static bool ParsePick(const char *p, int *ch, int *track, int *cc)
{
    if (!p || !p[0]) return false;
    int a = -1, b = 0, c = 1;
    if (sscanf(p, "%d:%d:%d", &a, &b, &c) < 1) return false;
    if (a < 0 || a >= NUM_CHARACTERS) return false;
    *ch = a;
    if (track) *track = (b >= 0 && b < NUM_TRACKS) ? b : 0;
    if (cc) *cc = (c >= 0 && c <= 2) ? c : 1;
    return true;
}

void OnlineSubmitPick(void)
{
    if (!O.np) return;
    Np_Pick(O.np, TextFormat("%d:%d:%d", G.humanChar[0], G.trackIndex, G.settings.cc));
    Np_Ready(O.np, true);
    Note("Ready - waiting for your opponent");
}

void OnlineBackToLobby(void)
{
    G.netView = -1;
    G.settings.cc = O.savedCc;
    G.numHumans = 1;
    RaceStart(rand() % NUM_TRACKS, true);
    GoToScreen(SCR_ONLINE);
}

/* ------------------------------------------------------------------ */
/* Server events                                                       */
/* ------------------------------------------------------------------ */
void OnlinePoll(float dt)
{
    if (O.noteT > 0) O.noteT -= dt;
    if (!O.np) return;
    Np_Poll(O.np);
    NpEvent ev;
    while (Np_NextEvent(O.np, &ev)) {
        switch (ev.type) {
        case NP_EV_ROOM:
            Note(TextFormat("Room %s - share the code with your friend", ev.room));
            if (O.autoPick) {
                const char *p = getenv("TT_ONLINE_PICK");
                int ch = ev.slot == 0 ? 0 : 1, tr = 0, cc = 1;
                if (p) ParsePick(p, &ch, &tr, &cc);
                G.humanChar[0] = ch; G.trackIndex = tr; G.settings.cc = cc;
                OnlineSubmitPick();
            }
            break;
        case NP_EV_COUNTDOWN:
            Np_Loaded(O.np);       /* the track is built when the race starts */
            Note("Both ready - starting");
            break;
        case NP_EV_START: {
            int c0 = 0, c1 = 1, track = 0, cc = 1, t1, cc1;
            ParsePick(ev.picks[0], &c0, &track, &cc);
            ParsePick(ev.picks[1], &c1, &t1, &cc1);
            G.mode = MODE_ONLINE;
            G.humanChar[0] = c0;
            G.humanChar[1] = c1;
            G.trackIndex = track;
            G.settings.cc = cc;
            G.netSeed = ev.seed;
            G.netView = ev.slot;
            G.paused = false;
            RaceStart(track, false);
            O.latch = 0;
            O.raceOver = false;
            GoToScreen(SCR_RACE);
            if (ev.resumeFrame > 0) Note("Rejoined - catching up");
            TraceLog(LOG_INFO, "ONLINE: start seed %u delay %d slot %d track %d resume %d", ev.seed, ev.delay, ev.slot, track, ev.resumeFrame);
        } break;
        case NP_EV_CANCEL:
            Note(TextFormat("Start cancelled (%s)", ev.text));
            if (G.screen != SCR_CHAR && G.screen != SCR_TRACK) GoToScreen(SCR_ONLINE);
            break;
        case NP_EV_PEER_LEFT:
        case NP_EV_MATCH_END:
            Note(ev.text[0] ? ev.text : "Match over");
            if (G.screen == SCR_RACE) OnlineBackToLobby();
            break;
        case NP_EV_PEER_HOLD: Note("Opponent lost connection - waiting for them"); break;
        case NP_EV_PEER_BACK: Note("Opponent is back"); break;
        case NP_EV_ERROR:
        case NP_EV_DISCONNECT: Note(ev.text); break;
        default: break;
        }
    }
}

/* ------------------------------------------------------------------ */
/* Lockstep race                                                       */
/* ------------------------------------------------------------------ */
static uint16_t LocalBits(void)
{
    KartInput in;
    int nh = R.numHumans;
    R.numHumans = 1;             /* InputRead's solo layout: every key set and every pad */
    InputRead(0, &in);
    R.numHumans = nh;
    int q = (int)lroundf(Clamp(in.steer, -1, 1)*15.0f) + 16;
    uint16_t b = (uint16_t)(q & 31);
    if (in.accel) b |= 1 << 5;
    if (in.back) b |= 1 << 6;
    if (in.hop) b |= 1 << 7;
    if (in.item) b |= 1 << 8;
    if (in.hopPressed) O.latch |= 1 << 7;     /* a tap shorter than a frame still counts */
    if (in.itemPressed) O.latch |= 1 << 8;
    return b;
}

static uint16_t BotBits(void)
{
    uint32_t r = Np_Rand(&O.botRng);
    uint16_t b = (uint16_t)(16 + (int)(r % 13) - 6);
    b |= 1 << 5;
    if ((r >> 8 & 63) == 0) b |= 1 << 7;
    if ((r >> 14 & 31) == 0) b |= 1 << 8;
    return b;
}

#define HF(h, v) ((h) = Np_HashBytes((h), &(v), (int)sizeof(v)))
static uint32_t RaceHash(void)
{
    uint32_t h = NP_HASH_INIT;
    for (int i = 0; i < R.numKarts; i++) {
        const Kart *k = &R.karts[i];
        HF(h, k->pos); HF(h, k->vy); HF(h, k->heading); HF(h, k->speed); HF(h, k->steer);
        HF(h, k->seg); HF(h, k->segCount); HF(h, k->lap); HF(h, k->finished); HF(h, k->place);
        HF(h, k->item); HF(h, k->itemCount); HF(h, k->boostTimer); HF(h, k->spinTimer);
        HF(h, k->driftState); HF(h, k->driftCharge); HF(h, k->charId);
    }
    for (int i = 0; i < MAX_PROJECTILES; i++) {
        const Projectile *p = &R.proj[i];
        if (!p->active) continue;
        HF(h, i); HF(h, p->type); HF(h, p->pos);
    }
    HF(h, R.time); HF(h, R.phase); HF(h, R.numFinished);
    return h;
}

static void QuitForTest(void)
{
    printf("ONLINE_RESULT frame %d hash %u phase %d time %.3f\n", Np_State(O.np)->frame, RaceHash(), (int)R.phase, R.time);
    fflush(stdout);
    exit(0);
}

/* Replaces the free-running RaceUpdate loop while an online race is on screen. */
void OnlineRaceSteps(void)
{
    if (!O.np || !Np_InMatch(O.np) || O.raceOver) return;
    uint16_t held = O.botRng ? BotBits() : LocalBits();
    int n = Np_StepsDue(O.np);
    for (int i = 0; i < n; i++) {
        if (Np_SetLocalInput(O.np, (uint16_t)(held | O.latch))) O.latch = 0;
        uint16_t in[2];
        if (!Np_FrameInputs(O.np, in)) break;
        R.netBits[0] = in[0];
        R.netBits[1] = in[1];
        RaceUpdate(SIM_DT);
        G.time += SIM_DT;
        Np_FrameDone(O.np, RaceHash());
        int f = Np_State(O.np)->frame;
        if (f % 600 == 0) TraceLog(LOG_INFO, "ONLINE: frame %d hash %u", f, RaceHash());
        if (O.autoQuitAt && f >= O.autoQuitAt) QuitForTest();
        if (R.phase == RACE_DONE && R.doneTimer > DONE_HOLD) {   /* the same frame on both machines */
            O.raceOver = true;
            Np_MatchOver(O.np);
            if (O.autoQuitAt) QuitForTest();
            break;
        }
    }
}

bool OnlineRaceOver(void) { return O.raceOver; }

/* ------------------------------------------------------------------ */
/* Online menu / lobby screen                                          */
/* ------------------------------------------------------------------ */
void OnlineMenuUpdate(void)
{
    if (!O.np) { OnlineEnter(); return; }
    const NpState *st = Np_State(O.np);
    if (st->room[0]) {                     /* in a room: choose racer + track, or leave */
        if (MenuBack()) { Np_Leave(O.np); Note("Left the room"); return; }
        bool myReady = st->slot >= 0 && st->ready[st->slot];
        if (MenuOk() && G.screenTime > 0.3f) {
            if (myReady) { Np_Ready(O.np, false); return; }
            G.numHumans = 1;
            G.charLocked[0] = false;
            G.charCursor[0] = G.humanChar[0];
            GoToScreen(SCR_CHAR);
        }
        return;
    }
    if (O.typing) {
        int c;
        while ((c = GetCharPressed()) != 0) {
            if (c >= 'a' && c <= 'z') c -= 32;
            int n = (int)strlen(O.code);
            if (((c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9')) && n < 5) { O.code[n] = (char)c; O.code[n + 1] = 0; }
        }
        if (IsKeyPressed(KEY_BACKSPACE) && O.code[0]) O.code[strlen(O.code) - 1] = 0;
        if (IsKeyPressed(KEY_ESCAPE)) O.typing = false;
        if (IsKeyPressed(KEY_ENTER) && strlen(O.code) == 5) { Np_Join(O.np, O.code); O.typing = false; Note(TextFormat("Joining %s...", O.code)); }
        return;
    }
    if (MenuUp()) O.menu = (O.menu + 3) % 4;
    if (MenuDown()) O.menu = (O.menu + 1) % 4;
    if (MenuBack() || (MenuOk() && O.menu == 3)) { LeaveOnline(); return; }
    if (!MenuOk() || G.screenTime < 0.2f) return;
    if (O.menu == 0) { Np_Quick(O.np); Note("Looking for an opponent..."); }
    if (O.menu == 1) { Np_Create(O.np); Note("Creating a room..."); }
    if (O.menu == 2) { O.typing = true; O.code[0] = 0; while (GetCharPressed()) {} }
}

void OnlineDraw(void)
{
    int W = GetScreenWidth(), H = GetScreenHeight();
    float u = H/720.0f;
    DrawRectangle(0, 0, W, H, (Color){ 0, 0, 20, 170 });
    DrawTextCentered("ONLINE VS", W/2, (int)(40*u), (int)(60*u), (Color){ 255, 230, 60, 255 });
    if (!O.np) return;
    const NpState *st = Np_State(O.np);
    DrawTextCentered(TextFormat("Server: %s", O.url), W/2, (int)(110*u), (int)(16*u), (Color){ 180, 180, 200, 255 });
    DrawTextCentered(st->status, W/2, (int)(134*u), (int)(22*u), st->phase == NP_OFFLINE ? (Color){ 255, 90, 90, 255 } : (Color){ 160, 230, 255, 255 });
    if (st->room[0]) {
        DrawTextCentered(TextFormat("ROOM  %s", st->room), W/2, (int)(190*u), (int)(64*u), WHITE);
        for (int s = 0; s < 2; s++) {
            int ch = 0, tr = 0, cc = 1;
            bool has = ParsePick(st->picks[s], &ch, &tr, &cc);
            const char *who = s == st->slot ? "YOU" : "RIVAL";
            const char *what = !st->occupied[s] ? "(empty - share the code)"
                             : has ? TextFormat("%s%s", CHARACTERS[ch].name, s == 0 ? TextFormat("  on %s", TRACK_DEFS[tr].name) : "")
                                   : "choosing...";
            Color c = st->ready[s] ? (Color){ 120, 255, 140, 255 } : WHITE;
            DrawTextCentered(TextFormat("%s:  %s%s", who, what, st->ready[s] ? "   READY" : ""), W/2, (int)((300 + s*50)*u), (int)(28*u), c);
        }
        bool myReady = st->slot >= 0 && st->ready[st->slot];
        DrawTextCentered(myReady ? "ENTER: un-ready     ESC: leave room" : "ENTER: choose racer and track     ESC: leave room",
                         W/2, (int)(450*u), (int)(22*u), (Color){ 255, 240, 200, 255 });
        DrawTextCentered("The first player's track and engine class are raced.", W/2, (int)(490*u), (int)(18*u), (Color){ 180, 200, 220, 255 });
    } else {
        static const char *items[4] = { "QUICK MATCH", "CREATE PRIVATE ROOM", "JOIN ROOM WITH CODE", "BACK" };
        for (int i = 0; i < 4; i++) {
            bool s = i == O.menu;
            Rectangle r = { W*0.5f - 260*u, (190 + i*80)*u, 520*u, 64*u };
            DrawRectangleRounded(r, 0.3f, 6, s ? (Color){ 230, 60, 60, 230 } : (Color){ 30, 30, 70, 210 });
            const char *label = (i == 2 && O.typing) ? TextFormat("CODE: %s_", O.code) : items[i];
            DrawTextCentered(label, W/2, (int)(r.y + 14*u), (int)(34*u), WHITE);
        }
        DrawTextCentered(O.typing ? "Type the 5-character code, ENTER to join, ESC to cancel" : "UP / DOWN, ENTER to choose, ESC back",
                         W/2, (int)(530*u), (int)(20*u), (Color){ 255, 240, 200, 255 });
    }
    if (O.noteT > 0) DrawTextCentered(O.note, W/2, (int)(H - 80*u), (int)(22*u), (Color){ 255, 170, 60, 255 });
    DrawTextCentered("Both players need the same server (netplay.cfg, --server or TT_SERVER).", W/2, (int)(H - 40*u), (int)(16*u), (Color){ 160, 160, 180, 255 });
}

void OnlineDrawRaceStatus(void)
{
    if (!O.np) return;
    const NpState *st = Np_State(O.np);
    int W = GetScreenWidth(), H = GetScreenHeight();
    float u = H/720.0f;
    const char *line = NULL;
    Color c = (Color){ 255, 170, 60, 255 };
    if (st->peerHeld) line = st->status;
    else if (st->slow) line = "Connection slow";
    else if (O.noteT > 0) line = O.note;
    if (line) DrawTextCentered(line, W/2, (int)(H*0.30f), (int)(30*u), c);
    DrawText(TextFormat("ONLINE %s  ping %d ms  delay %d", st->room, (int)st->rttMs, st->delay), (int)(10*u), (int)(H - 22*u), (int)(14*u), (Color){ 200, 220, 255, 200 });
}

/* test hook: TT_ONLINE=quick|create|join:CODE goes straight into a room and readies */
void OnlineAutoStart(void)
{
    const char *mode = getenv("TT_ONLINE");
    if (!mode) return;
    OnlineEnter();
    O.autoPick = true;
    if (getenv("TT_ONLINE_BOT")) O.botRng = (uint32_t)atoi(getenv("TT_ONLINE_BOT")) | 1u;
    if (getenv("TT_ONLINE_QUIT_AT")) O.autoQuitAt = atoi(getenv("TT_ONLINE_QUIT_AT"));
    if (strcmp(mode, "create") == 0) Np_Create(O.np);
    else if (strncmp(mode, "join:", 5) == 0) Np_Join(O.np, mode + 5);
    else Np_Quick(O.np);
}

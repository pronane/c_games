// Online versus: menu, lobby and the lockstep fight loop (see online.h).
#include "online.h"

#include <stdint.h>
#include <stdlib.h>
#include <time.h>

#define DEFAULT_SERVER "ws://localhost:3000/egyptian"

static struct {
    Netplay *np;
    char url[256];
    char userId[40];
    int menu;              // 0 quick match, 1 create room, 2 join room, 3 back
    bool typing;           // entering a room code
    char code[8];
    char note[128];
    double noteAt;
    uint16_t latch;        // buttons tapped since the last sampled sim frame
    // test hooks (EF_ONLINE=quick|create|join:CODE, EF_ONLINE_PICK, EF_ONLINE_BOT, EF_ONLINE_QUIT_AT)
    bool autoPick;
    int autoQuitAt;
    uint32_t botRng;
} O;

static void Note(const char *msg)
{
    snprintf(O.note, sizeof(O.note), "%s", msg);
    O.noteAt = GetTime();
}

static void ReadCfg(void)
{
    const char *path = FileExists("netplay.cfg") ? "netplay.cfg" : "assets/netplay.cfg";
    if (!FileExists(path)) return;
    char *text = LoadFileText(path);
    if (!text) return;
    for (char *line = strtok(text, "\r\n"); line; line = strtok(NULL, "\r\n")) {
        while (*line == ' ') line++;
        if (strncmp(line, "server", 6) != 0) continue;
        char *v = strchr(line, '=');
        if (!v) continue;
        v++;
        while (*v == ' ') v++;
        if (*v) snprintf(O.url, sizeof(O.url), "%s", v);
    }
    UnloadFileText(text);
}

void Online_Configure(int argc, char **argv)
{
    snprintf(O.url, sizeof(O.url), "%s", DEFAULT_SERVER);
    ReadCfg();
    if (getenv("EF_SERVER")) snprintf(O.url, sizeof(O.url), "%s", getenv("EF_SERVER"));
    for (int i = 1; i + 1 < argc; i++)
        if (strcmp(argv[i], "--server") == 0) snprintf(O.url, sizeof(O.url), "%s", argv[i + 1]);
    // unique per window: two copies started in the same second must not share an id
    int local;
    uint32_t mix = (uint32_t)time(NULL) ^ (uint32_t)clock() * 2654435761u ^ (uint32_t)(uintptr_t)&local;
    snprintf(O.userId, sizeof(O.userId), "ef-%08x%04x", (unsigned)mix, (unsigned)GetRandomValue(0, 0xffff));
    O.menu = 0;
}

bool Online_Active(void) { return O.np != NULL; }
int Online_MySlot(void) { return O.np ? Np_State(O.np)->slot : -1; }

void Online_Enter(Game *g)
{
    if (!O.url[0]) Online_Configure(0, NULL);
    if (!O.np) O.np = Np_New(O.url, O.userId);
    g->mode = MODE_ONLINE;
    g->screen = SCREEN_ONLINE;
    g->p1Ready = g->p2Ready = false;
    O.typing = false;
}

static void LeaveOnline(Game *g)
{
    Online_Shutdown();
    g->mode = MODE_1P_VS_CPU;
    g->screen = SCREEN_SELECT;
    g->p1Ready = g->p2Ready = false;
}

void Online_Shutdown(void)
{
    if (O.np) Np_Free(O.np);
    O.np = NULL;
}

static int PickIndex(const char *pick)
{
    if (!pick || !pick[0]) return -1;
    int i = atoi(pick);
    return i >= 0 && i < MAX_CHARACTERS ? i : -1;
}

// ---------------------------------------------------------------------------
//  Events from the server
// ---------------------------------------------------------------------------
void Online_Poll(Game *g)
{
    if (!O.np) return;
    Np_Poll(O.np);
    NpEvent ev;
    while (Np_NextEvent(O.np, &ev)) {
        switch (ev.type) {
        case NP_EV_ROOM:
            g->screen = SCREEN_SELECT;
            g->p1Ready = g->p2Ready = false;
            Note(TextFormat("Room %s - you are the %s fighter. Share the code!", ev.room, ev.slot == 0 ? "left" : "right"));
            if (O.autoPick) {
                const char *p = getenv("EF_ONLINE_PICK");
                int i = PickIndex(p);
                if (i < 0) i = ev.slot == 0 ? 0 : 2;
                if (ev.slot == 0) g->selectP1 = i; else g->selectP2 = i;
                Np_Pick(O.np, TextFormat("%d", i));
                Np_Ready(O.np, true);
            }
            break;
        case NP_EV_COUNTDOWN: {
            int a = PickIndex(ev.picks[0]), b = PickIndex(ev.picks[1]);
            if (a >= 0) g->selectP1 = a;
            if (b >= 0) g->selectP2 = b;
            Game_LoadFight(g);                  // sprites + face-off screen
            Np_Loaded(O.np);
            Note("Get ready!");
            break;
        }
        case NP_EV_START: {
            int a = PickIndex(ev.picks[0]), b = PickIndex(ev.picks[1]);
            bool loaded = g->player1.sheets[0].texture.id && g->player1.characterIndex == a &&
                          g->player2.characterIndex == b;
            if (!loaded) {                      // a rejoin after a restart: load first
                if (a >= 0) g->selectP1 = a;
                if (b >= 0) g->selectP2 = b;
                Game_LoadFight(g);
            }
            Game_ResetFight(g);
            g->screen = ev.resumeFrame > 0 ? SCREEN_FIGHT : SCREEN_PREFIGHT;
            O.latch = 0;
            if (ev.resumeFrame > 0) Note("Rejoined - catching up");
            TraceLog(LOG_INFO, "ONLINE: start seed %u delay %d slot %d resume %d", ev.seed, ev.delay, ev.slot, ev.resumeFrame);
            break;
        }
        case NP_EV_CANCEL:
            g->screen = SCREEN_SELECT;
            g->p1Ready = g->p2Ready = false;
            Note(TextFormat("Start cancelled (%s)", ev.text));
            break;
        case NP_EV_PEER_LEFT:
            if (g->screen == SCREEN_FIGHT || g->screen == SCREEN_PREFIGHT) {
                g->gameOver = true;
                g->winner = Online_MySlot() + 1;
                g->screen = SCREEN_RESULT;
            }
            g->p1Ready = g->p2Ready = false;
            Note("Opponent left the room - waiting for a new one");
            break;
        case NP_EV_PEER_HOLD:
            Note("Opponent lost connection - waiting for them to come back");
            break;
        case NP_EV_PEER_BACK:
            Note("Opponent is back");
            break;
        case NP_EV_MATCH_END:
            if (g->screen == SCREEN_FIGHT || g->screen == SCREEN_PREFIGHT) {
                g->gameOver = true;
                g->winner = ev.winner >= 0 ? ev.winner + 1 : 0;
                g->screen = SCREEN_RESULT;
            }
            Note(ev.text);
            break;
        case NP_EV_ERROR:
        case NP_EV_DISCONNECT:
            Note(ev.text);
            break;
        default:
            break;
        }
    }
}

// ---------------------------------------------------------------------------
//  Online menu
// ---------------------------------------------------------------------------
void Online_MenuUpdate(Game *g)
{
    if (!O.np) { Online_Enter(g); return; }
    if (O.typing) {
        int c;
        while ((c = GetCharPressed()) != 0) {
            if (c >= 'a' && c <= 'z') c -= 32;
            int n = (int)strlen(O.code);
            if (((c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9')) && n < 5) { O.code[n] = (char)c; O.code[n + 1] = 0; }
        }
        if (IsKeyPressed(KEY_BACKSPACE) && O.code[0]) O.code[strlen(O.code) - 1] = 0;
        if (IsKeyPressed(KEY_ESCAPE) || Pad_Pressed(PAD_ANY, PB_B)) O.typing = false;
        if ((IsKeyPressed(KEY_ENTER) || IsKeyPressed(KEY_KP_ENTER)) && strlen(O.code) == 5) {
            Np_Join(O.np, O.code);
            O.typing = false;
            Note(TextFormat("Joining %s...", O.code));
        }
        return;
    }
    if (IsKeyPressed(KEY_UP) || IsKeyPressed(KEY_W) || Pad_Repeat(PAD_ANY, PB_UP)) O.menu = (O.menu + 3) % 4;
    if (IsKeyPressed(KEY_DOWN) || IsKeyPressed(KEY_S) || Pad_Repeat(PAD_ANY, PB_DOWN)) O.menu = (O.menu + 1) % 4;
    bool ok = IsKeyPressed(KEY_ENTER) || IsKeyPressed(KEY_KP_ENTER) || IsKeyPressed(KEY_SPACE) ||
              IsKeyPressed(KEY_J) || Pad_Pressed(PAD_ANY, PB_A) || Pad_Pressed(PAD_ANY, PB_START);
    bool back = IsKeyPressed(KEY_ESCAPE) || IsKeyPressed(KEY_BACKSPACE) || Pad_Pressed(PAD_ANY, PB_B);
    if (back || (ok && O.menu == 3)) { LeaveOnline(g); return; }
    if (!ok) return;
    if (O.menu == 0) { Np_Quick(O.np); Note("Looking for an opponent..."); }
    if (O.menu == 1) { Np_Create(O.np); Note("Creating a room..."); }
    if (O.menu == 2) { O.typing = true; O.code[0] = 0; while (GetCharPressed()) {} }
}

// ---------------------------------------------------------------------------
//  Lobby: our cursor only, the other side mirrors the server
// ---------------------------------------------------------------------------
static int GridStep(int sel, int dx, int dy)
{
    const int cols = 2, rows = (MAX_CHARACTERS + cols - 1) / cols;
    int c = sel % cols, r = sel / cols;
    c = (c + dx + cols) % cols;
    r = (r + dy + rows) % rows;
    int i = r * cols + c;
    return i < MAX_CHARACTERS ? i : MAX_CHARACTERS - 1;
}

void Online_SelectUpdate(Game *g)
{
    g->selTime += GetFrameTime();
    const NpState *st = Np_State(O.np);
    int me = st->slot;
    if (me < 0) { g->screen = SCREEN_ONLINE; return; }
    int *mine = me == 0 ? &g->selectP1 : &g->selectP2;
    int *theirs = me == 0 ? &g->selectP2 : &g->selectP1;
    int other = PickIndex(st->picks[me ^ 1]);
    if (other >= 0) *theirs = other;
    g->p1Ready = st->ready[0] && st->occupied[0];
    g->p2Ready = st->ready[1] && st->occupied[1];
    bool myReady = me == 0 ? g->p1Ready : g->p2Ready;

    if (IsKeyPressed(KEY_ESCAPE)) {
        Np_Leave(O.np);
        g->screen = SCREEN_ONLINE;
        Note("Left the room");
        return;
    }
    bool ok = IsKeyPressed(KEY_ENTER) || IsKeyPressed(KEY_KP_ENTER) || IsKeyPressed(KEY_J) ||
              IsKeyPressed(KEY_SPACE) || Pad_Pressed(PAD_ANY, PB_A) || Pad_Pressed(PAD_ANY, PB_START);
    bool back = IsKeyPressed(KEY_BACKSPACE) || IsKeyPressed(KEY_X) || Pad_Pressed(PAD_ANY, PB_B);
    if (myReady) {
        if (back) Np_Ready(O.np, false);
        return;
    }
    int dx = (IsKeyPressed(KEY_D) || IsKeyPressed(KEY_RIGHT) || Pad_Repeat(PAD_ANY, PB_RIGHT)) -
             (IsKeyPressed(KEY_A) || IsKeyPressed(KEY_LEFT) || Pad_Repeat(PAD_ANY, PB_LEFT));
    int dy = (IsKeyPressed(KEY_S) || IsKeyPressed(KEY_DOWN) || Pad_Repeat(PAD_ANY, PB_DOWN)) -
             (IsKeyPressed(KEY_W) || IsKeyPressed(KEY_UP) || Pad_Repeat(PAD_ANY, PB_UP));
    if (dx || dy) *mine = GridStep(*mine, dx, dy);
    if (ok) {
        Np_Pick(O.np, TextFormat("%d", *mine));
        Np_Ready(O.np, true);
        if (me == 0) g->p1Ready = true; else g->p2Ready = true;
        if (!st->occupied[me ^ 1]) Note(TextFormat("Ready - waiting for an opponent (room %s)", st->room));
    }
}

// ---------------------------------------------------------------------------
//  Fight: sample local buttons, step in lockstep
// ---------------------------------------------------------------------------
enum { B_LEFT, B_RIGHT, B_UP, B_DOWN, B_PUNCH, B_KICK, B_SP1, B_SP2, B_BLOCK, B_THROW, B_TAUNT };

static uint16_t HeldBits(void)
{
    uint16_t b = 0;
    if (IsKeyDown(KEY_A) || IsKeyDown(KEY_LEFT) || Pad_Down(PAD_ANY, PB_LEFT)) b |= 1 << B_LEFT;
    if (IsKeyDown(KEY_D) || IsKeyDown(KEY_RIGHT) || Pad_Down(PAD_ANY, PB_RIGHT)) b |= 1 << B_RIGHT;
    if (IsKeyDown(KEY_W) || IsKeyDown(KEY_UP) || Pad_Down(PAD_ANY, PB_UP) || Pad_Down(PAD_ANY, PB_A)) b |= 1 << B_UP;
    if (IsKeyDown(KEY_S) || IsKeyDown(KEY_DOWN) || Pad_Down(PAD_ANY, PB_DOWN)) b |= 1 << B_DOWN;
    if (IsKeyDown(KEY_J) || Pad_Down(PAD_ANY, PB_X)) b |= 1 << B_PUNCH;
    if (IsKeyDown(KEY_K) || Pad_Down(PAD_ANY, PB_Y)) b |= 1 << B_KICK;
    if (IsKeyDown(KEY_U) || Pad_Down(PAD_ANY, PB_B) || Pad_Down(PAD_ANY, PB_LT)) b |= 1 << B_SP1;
    if (IsKeyDown(KEY_I) || Pad_Down(PAD_ANY, PB_RT)) b |= 1 << B_SP2;
    if (IsKeyDown(KEY_L) || Pad_Down(PAD_ANY, PB_RB)) b |= 1 << B_BLOCK;
    if (IsKeyDown(KEY_O) || Pad_Down(PAD_ANY, PB_LB)) b |= 1 << B_THROW;
    if (IsKeyDown(KEY_P) || Pad_Down(PAD_ANY, PB_BACK)) b |= 1 << B_TAUNT;
    return b;
}

// A tap shorter than one render frame still reaches the sim as one frame "down".
static uint16_t TappedBits(void)
{
    uint16_t b = 0;
    if (IsKeyPressed(KEY_J) || Pad_Pressed(PAD_ANY, PB_X)) b |= 1 << B_PUNCH;
    if (IsKeyPressed(KEY_K) || Pad_Pressed(PAD_ANY, PB_Y)) b |= 1 << B_KICK;
    if (IsKeyPressed(KEY_U) || Pad_Pressed(PAD_ANY, PB_B) || Pad_Pressed(PAD_ANY, PB_LT)) b |= 1 << B_SP1;
    if (IsKeyPressed(KEY_I) || Pad_Pressed(PAD_ANY, PB_RT)) b |= 1 << B_SP2;
    if (IsKeyPressed(KEY_O) || Pad_Pressed(PAD_ANY, PB_LB)) b |= 1 << B_THROW;
    if (IsKeyPressed(KEY_P) || Pad_Pressed(PAD_ANY, PB_BACK)) b |= 1 << B_TAUNT;
    if (IsKeyPressed(KEY_W) || IsKeyPressed(KEY_UP) || Pad_Pressed(PAD_ANY, PB_A)) b |= 1 << B_UP;
    return b;
}

static uint16_t BotBits(void)
{
    // test bot: walk toward the middle, jab, block, jump now and then
    uint32_t r = Np_Rand(&O.botRng);
    uint16_t b = (uint16_t)((r >> 3) & ((1 << B_LEFT) | (1 << B_RIGHT)));
    if ((r & 15) == 0) b |= 1 << B_PUNCH;
    if ((r & 31) == 1) b |= 1 << B_KICK;
    if ((r & 63) == 2) b |= 1 << B_SP1;
    if ((r & 127) == 3) b |= 1 << B_UP;
    if ((r >> 8 & 7) == 0) b |= 1 << B_BLOCK;
    return b;
}

void Online_FightUpdate(Game *g)
{
    if (!O.np || !Np_InMatch(O.np)) return;
    O.latch |= TappedBits();
    int n = Np_StepsDue(O.np);
    for (int i = 0; i < n; i++) {
        uint16_t local = O.botRng ? BotBits() : (uint16_t)(HeldBits() | O.latch);
        if (Np_SetLocalInput(O.np, local)) O.latch = 0;
        uint16_t in[2];
        if (!Np_FrameInputs(O.np, in)) break;
        if (g->screen == SCREEN_PREFIGHT) g->screen = SCREEN_FIGHT;   // the clock reached frame 0
        Game_ApplyBits(&g->player1, in[0], g->netPrev[0]);
        Game_ApplyBits(&g->player2, in[1], g->netPrev[1]);
        g->netPrev[0] = in[0];
        g->netPrev[1] = in[1];
        Game_FightStep(g, 1.0f / 60.0f);
        uint32_t h = Game_Hash(g);
        Np_FrameDone(O.np, h);
        int f = Np_State(O.np)->frame;
        if (f % 300 == 0) TraceLog(LOG_INFO, "ONLINE: frame %d hash %u", f, h);
        if (O.autoQuitAt && f >= O.autoQuitAt) {
            printf("ONLINE_RESULT frame %d hash %u hp %d %d\n", f, h, g->player1.health, g->player2.health);
            fflush(stdout);
            exit(0);
        }
        if (g->screen != SCREEN_FIGHT) {        // KO or time: both machines reach it on the same frame
            Np_MatchOver(O.np);
            if (O.autoQuitAt) {
                printf("ONLINE_RESULT frame %d hash %u hp %d %d\n", f, h, g->player1.health, g->player2.health);
                fflush(stdout);
                exit(0);
            }
            break;
        }
    }
}

// ---------------------------------------------------------------------------
//  Drawing
// ---------------------------------------------------------------------------
static void Centered(const char *t, int y, int fs, Color c)
{
    DrawText(t, SCREEN_WIDTH / 2 - MeasureText(t, fs) / 2, y, fs, c);
}

void Online_DrawMenu(const Game *g)
{
    (void)g;
    DrawRectangle(0, 0, SCREEN_WIDTH, SCREEN_HEIGHT, (Color){ 12, 10, 24, 235 });
    Centered("ONLINE VERSUS", 70, 54, GOLD);
    const NpState *st = O.np ? Np_State(O.np) : NULL;
    Centered(TextFormat("Server: %s", O.url), 140, 18, GRAY);
    if (st) Centered(st->status, 166, 22, st->phase == NP_OFFLINE ? RED : SKYBLUE);

    static const char *items[4] = { "QUICK MATCH", "CREATE PRIVATE ROOM", "JOIN ROOM WITH CODE", "BACK" };
    for (int i = 0; i < 4; i++) {
        int y = 240 + i * 74;
        bool on = O.menu == i;
        Rectangle r = { SCREEN_WIDTH / 2.0f - 260, (float)y, 520, 58 };
        DrawRectangleRounded(r, 0.3f, 6, on ? (Color){ 230, 180, 40, 240 } : (Color){ 40, 40, 60, 220 });
        const char *label = items[i];
        if (i == 2 && O.typing) label = TextFormat("CODE: %s_", O.code);
        Centered(label, y + 14, 30, on ? BLACK : RAYWHITE);
    }
    if (O.typing) Centered("Type the 5-character code, Enter to join, Esc to cancel", 560, 20, LIGHTGRAY);
    else Centered("Up / Down to choose, Enter or A to select, Esc or B to go back", 560, 20, LIGHTGRAY);
    if (O.note[0] && GetTime() - O.noteAt < 8.0) Centered(O.note, 600, 22, ORANGE);
    Centered("Your friend runs the same game with the same server (netplay.cfg or --server).", 660, 16, GRAY);
}

void Online_DrawStatus(const Game *g)
{
    if (!O.np) return;
    const NpState *st = Np_State(O.np);
    const char *line;
    Color c = SKYBLUE;
    if (g->screen == SCREEN_FIGHT || g->screen == SCREEN_PREFIGHT) {
        if (st->peerHeld) { line = st->status; c = ORANGE; }
        else if (st->slow) { line = "Connection slow"; c = ORANGE; }
        else line = TextFormat("Online  room %s  delay %d frames  ping %d ms", st->room, st->delay, (int)st->rttMs);
        if (g->screen == SCREEN_PREFIGHT && Np_InMatch(O.np)) Centered("GET READY", SCREEN_HEIGHT / 2 + 120, 40, GOLD);
    } else {
        line = st->room[0] ? TextFormat("ROOM %s   %s", st->room, st->occupied[st->slot ^ 1] ? "opponent here" : "waiting for an opponent - share the code")
                           : st->status;
    }
    int w = MeasureText(line, 18);
    DrawRectangle(SCREEN_WIDTH / 2 - w / 2 - 10, 92, w + 20, 26, (Color){ 0, 0, 0, 190 });
    DrawText(line, SCREEN_WIDTH / 2 - w / 2, 96, 18, c);
    if (O.note[0] && GetTime() - O.noteAt < 6.0) {
        int nw = MeasureText(O.note, 20);
        DrawRectangle(SCREEN_WIDTH / 2 - nw / 2 - 10, SCREEN_HEIGHT - 90, nw + 20, 30, (Color){ 0, 0, 0, 200 });
        DrawText(O.note, SCREEN_WIDTH / 2 - nw / 2, SCREEN_HEIGHT - 85, 20, ORANGE);
    }
    if (g->screen == SCREEN_SELECT)
        Centered("Esc: leave room    Backspace / B: un-ready", 690, 16, GRAY);
}

// test hooks: EF_ONLINE=quick|create|join:CODE goes straight online
void Online_AutoStart(Game *g)
{
    const char *mode = getenv("EF_ONLINE");
    if (!mode) return;
    Online_Enter(g);
    O.autoPick = true;
    if (getenv("EF_ONLINE_BOT")) O.botRng = (uint32_t)atoi(getenv("EF_ONLINE_BOT")) | 1u;
    if (getenv("EF_ONLINE_QUIT_AT")) O.autoQuitAt = atoi(getenv("EF_ONLINE_QUIT_AT"));
    if (strcmp(mode, "create") == 0) Np_Create(O.np);
    else if (strncmp(mode, "join:", 5) == 0) Np_Join(O.np, mode + 5);
    else Np_Quick(O.np);
}

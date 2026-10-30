/*
 * input_pad.c - controller support for FACILITY 64 (unity build: #included from main.c)
 *
 *  - up to 4 gamepads (raylib ids 0-3) via raylib/GLFW; on Windows GLFW reads XInput pads directly
 *  - per-player device assignment, join-in lobby, auto-assign, hot-plug toasts, pause on disconnect
 *  - two control styles (modern dual-stick, classic "1.2"-style: stick looks, right stick walks)
 *  - radial deadzone, response curve, sensitivity, invert Y, trigger threshold, aim acceleration
 *  - controls.cfg next to the exe, "press a button" remap, options + controller debug screens
 *  - rumble: XInput (Windows, loaded at runtime from xinput1_4/1_3/9_1_0.dll); unsupported elsewhere
 *  - --pad-script FILE: simulated pads driven by a script (testing without hardware)
 *
 * Button names are the generic Xbox-style labels (A/B/X/Y/LB/RB/LT/RT/BACK/START/LS/RS).
 */

#define PADB_COUNT 18                  /* raylib GamepadButton values 0..17 */
#define PAD_AXES 6

#define B_DUP    GAMEPAD_BUTTON_LEFT_FACE_UP
#define B_DRIGHT GAMEPAD_BUTTON_LEFT_FACE_RIGHT
#define B_DDOWN  GAMEPAD_BUTTON_LEFT_FACE_DOWN
#define B_DLEFT  GAMEPAD_BUTTON_LEFT_FACE_LEFT
#define B_Y      GAMEPAD_BUTTON_RIGHT_FACE_UP
#define B_B      GAMEPAD_BUTTON_RIGHT_FACE_RIGHT
#define B_A      GAMEPAD_BUTTON_RIGHT_FACE_DOWN
#define B_X      GAMEPAD_BUTTON_RIGHT_FACE_LEFT
#define B_LB     GAMEPAD_BUTTON_LEFT_TRIGGER_1
#define B_LT     GAMEPAD_BUTTON_LEFT_TRIGGER_2
#define B_RB     GAMEPAD_BUTTON_RIGHT_TRIGGER_1
#define B_RT     GAMEPAD_BUTTON_RIGHT_TRIGGER_2
#define B_BACK   GAMEPAD_BUTTON_MIDDLE_LEFT
#define B_GUIDE  GAMEPAD_BUTTON_MIDDLE
#define B_START  GAMEPAD_BUTTON_MIDDLE_RIGHT
#define B_LS     GAMEPAD_BUTTON_LEFT_THUMB
#define B_RS     GAMEPAD_BUTTON_RIGHT_THUMB

static const char *BTN_NAME[PADB_COUNT] = {
    "NONE", "D-UP", "D-RIGHT", "D-DOWN", "D-LEFT", "Y", "B", "A", "X",
    "LB", "LT", "RB", "RT", "BACK", "GUIDE", "START", "LS", "RS"
};
/* bounded string copy (no truncation warnings) */
static void CopyStr(char *dst, size_t n, const char *src)
{
    size_t l = strlen(src);
    if (l >= n) l = n - 1;
    memcpy(dst, src, l); dst[l] = 0;
}

/* simple word-wrapped text */
static int DrawTextBoxed(const char *t, int x, int y, int maxW, int fs, Color c)
{
    char line[256] = "", test[256];
    int ly = y;
    const char *q = t;
    while (*q) {
        while (*q == ' ') q++;
        const char *w0 = q;
        while (*q && *q != ' ') q++;
        size_t wl = (size_t)(q - w0), ll = strlen(line);
        if (!wl) break;
        if (ll + wl + 2 >= sizeof(test)) break;
        memcpy(test, line, ll);
        if (ll) test[ll++] = ' ';
        memcpy(test + ll, w0, wl); test[ll + wl] = 0;
        if (MeasureText(test, fs) > maxW && line[0]) {
            DrawText(line, x, ly, fs, c); ly += fs + 4;
            memcpy(line, w0, wl); line[wl] = 0;
        } else memcpy(line, test, ll + wl + 1);
    }
    if (line[0]) { DrawText(line, x, ly, fs, c); ly += fs + 4; }
    return ly - y;
}

static const char *AXIS_NAME[PAD_AXES] = { "LX", "LY", "RX", "RY", "LT", "RT" };

typedef enum { ACT_FIRE, ACT_AIM, ACT_RELOAD, ACT_NEXTWPN, ACT_USE, ACT_SILENCER, ACT_PAUSE, ACT_COUNT } PadAction;
static const char *ACT_LABEL[ACT_COUNT] = { "FIRE", "AIM (slow look + zoom)", "RELOAD", "NEXT WEAPON", "USE / OPEN DOOR", "SILENCER (mission)", "PAUSE / WATCH" };
static const char *ACT_KEY[ACT_COUNT] = { "fire", "aim", "reload", "next_weapon", "use", "silencer", "pause" };

typedef enum { STYLE_MODERN, STYLE_CLASSIC, STYLE_COUNT } ControlStyle;
static const char *STYLE_NAME[STYLE_COUNT] = { "MODERN DUAL-STICK", "CLASSIC 1.2-STYLE" };
static const char *STYLE_DESC[STYLE_COUNT] = {
    "Left stick walks + strafes, right stick looks.",
    "Left stick turns + looks (like the old single stick); right stick / D-pad walk + strafe digitally."
};
static const char *STYLE_KEY[STYLE_COUNT] = { "modern", "classic" };

static const int DEFAULT_MAP[STYLE_COUNT][ACT_COUNT] = {
    /*            FIRE  AIM   RELOAD NEXT  USE  SILENCER PAUSE */
    /* modern  */ { B_RT, B_LT, B_X,   B_Y,  B_A, B_B,     B_START },
    /* classic */ { B_RT, B_RB, B_A,   B_B,  B_A, B_Y,     B_START },  /* trigger fires, shoulder aims, one action button, B swaps */
};

typedef struct {
    int style;
    float deadzone, sens, trigger;
    bool invertY, aimAccel, vibration, autoJoin;
    int map[STYLE_COUNT][ACT_COUNT];
} ControlConfig;
static ControlConfig gCtl;

static void CtlDefaults(void)
{
    gCtl.style = STYLE_MODERN;
    gCtl.deadzone = 0.18f; gCtl.sens = 1.0f; gCtl.trigger = 0.35f;
    gCtl.invertY = false; gCtl.aimAccel = true; gCtl.vibration = true; gCtl.autoJoin = false;
    memcpy(gCtl.map, DEFAULT_MAP, sizeof(gCtl.map));
}

/* ------------------------------------------------------------------ */
/* pad state (real or simulated)                                       */
/* ------------------------------------------------------------------ */
typedef struct {
    bool avail, wasAvail;
    char name[64];
    int axisCount;
    float axis[PAD_AXES];
    bool cur[PADB_COUNT], prev[PADB_COUNT];
    bool trigSeen[2];
    float accelT, rumbleT, idleT;
    int rumbles;               /* rumble requests (debug screen / tests) */
} PadState;
static PadState gPad[MAX_PLAYERS];

typedef struct { bool on; char name[64]; float axis[PAD_AXES]; bool btn[PADB_COUNT]; } PadSim;
static PadSim gPadSim[MAX_PLAYERS];
static bool gPadSimActive = false;     /* simulated pads replace the real ones (tests / --pad-script) */

static int gSlotPad[MAX_PLAYERS] = { -1, -1, -1, -1 };   /* pad id per player slot */
static bool gSlotJoined[MAX_PLAYERS] = { true, false, false, false };
static bool gSlotPadActive[MAX_PLAYERS];                 /* last input of the player came from a pad (prompts) */
static int gKb2Slot = -1;              /* deathmatch: a second keyboard player on the arrow keys */
static int gDmPlayers = 2;
static int gPadLostSlot = -1;          /* paused because this player's pad was unplugged */
static bool gUiPadMode = false;        /* last menu input came from a pad: show pad prompts */
static bool gQuitRequested = false;
static float gOverT = 0;            /* time on the mission-end / winner screen */
static char gShotPending[256];

static bool PlayerUsesPad(const Player *p) { int i = (int)(p - players); return i >= 0 && i < MAX_PLAYERS && gSlotPadActive[i]; }
static bool PadDown(int pad, int b) { return pad >= 0 && pad < MAX_PLAYERS && b > 0 && b < PADB_COUNT && gPad[pad].cur[b]; }
static bool PadPressed(int pad, int b) { return PadDown(pad, b) && !gPad[pad].prev[b]; }
static bool ActDown(int pad, PadAction a) { return PadDown(pad, gCtl.map[gCtl.style][a]); }
static bool ActPressed(int pad, PadAction a) { return PadPressed(pad, gCtl.map[gCtl.style][a]); }
static const char *ActBtn(PadAction a) { return BTN_NAME[gCtl.map[gCtl.style][a]]; }
static float PadTrigger(int pad, int t) { return Clamp((gPad[pad].axis[4 + t] + 1.0f)*0.5f, 0, 1); }   /* 0..1 */
static int PadSlotOf(int pad) { for (int s = 0; s < MAX_PLAYERS; s++) if (gSlotJoined[s] && gSlotPad[s] == pad) return s; return -1; }

static Vector2 RadialDeadzone(Vector2 v, float dz)
{
    float m = sqrtf(v.x*v.x + v.y*v.y);
    if (m <= dz || m < 1e-6f) return (Vector2){ 0, 0 };
    float k = (fminf(m, 1.0f) - dz)/(1.0f - dz);
    return (Vector2){ v.x/m*k, v.y/m*k };
}
static Vector2 PadStick(int pad, int ax) { return RadialDeadzone((Vector2){ gPad[pad].axis[ax], gPad[pad].axis[ax + 1] }, gCtl.deadzone); }

/* ------------------------------------------------------------------ */
/* rumble                                                              */
/* ------------------------------------------------------------------ */
#if defined(_WIN32)
typedef struct { unsigned short left, right; } XiVibration;
typedef struct { unsigned short buttons; unsigned char lt, rt; short lx, ly, rx, ry; } XiGamepad;
typedef struct { unsigned long packet; XiGamepad pad; } XiState;
typedef unsigned long (__stdcall *XiSetStateFn)(unsigned long, XiVibration *);
typedef unsigned long (__stdcall *XiGetStateFn)(unsigned long, XiState *);
__declspec(dllimport) void *__stdcall LoadLibraryA(const char *name);
__declspec(dllimport) void *__stdcall GetProcAddress(void *module, const char *name);
static XiSetStateFn xiSetState = NULL;
static XiGetStateFn xiGetState = NULL;
static void RumbleInit(void)
{
    const char *dlls[3] = { "xinput1_4.dll", "xinput1_3.dll", "xinput9_1_0.dll" };
    for (int i = 0; i < 3 && !xiSetState; i++) {
        void *m = LoadLibraryA(dlls[i]);
        if (!m) continue;
        union { void *p; XiSetStateFn f; } us; us.p = GetProcAddress(m, "XInputSetState");
        union { void *p; XiGetStateFn f; } ug; ug.p = GetProcAddress(m, "XInputGetState");
        if (us.p && ug.p) { xiSetState = us.f; xiGetState = ug.f; TraceLog(LOG_INFO, "PAD: rumble via %s", dlls[i]); }
    }
}
static bool RumbleSupported(void) { return xiSetState != NULL; }
/* GLFW does not expose which XInput slot a joystick uses; GLFW opens XInput pads first, in
   slot order, so the k-th XInput-named raylib pad is matched to the k-th connected XInput slot. */
static int XInputIndexFor(int pad)
{
    if (!xiGetState || !gPad[pad].avail) return -1;
    const char *n = gPad[pad].name;
    if (!strstr(n, "Xbox") && !strstr(n, "XInput")) return -1;
    int rank = 0;
    for (int j = 0; j < pad; j++)
        if (gPad[j].avail && (strstr(gPad[j].name, "Xbox") || strstr(gPad[j].name, "XInput"))) rank++;
    for (unsigned long u = 0; u < 4; u++) {
        XiState st; memset(&st, 0, sizeof(st));
        if (xiGetState(u, &st) == 0) { if (rank == 0) return (int)u; rank--; }
    }
    return -1;
}
static void RumbleSet(int pad, float lo, float hi)
{
    int u = XInputIndexFor(pad);
    if (u < 0) return;
    XiVibration v = { (unsigned short)(Clamp(lo, 0, 1)*65535), (unsigned short)(Clamp(hi, 0, 1)*65535) };
    xiSetState((unsigned long)u, &v);
}
static const char *RumbleBackend(void) { return xiSetState ? "XInput rumble (Windows)" : "no XInput DLL found"; }
#else
static void RumbleInit(void) { }
static bool RumbleSupported(void) { return false; }
static void RumbleSet(int pad, float lo, float hi) { (void)pad; (void)lo; (void)hi; }
static const char *RumbleBackend(void) { return "not supported on this platform (raylib's GLFW backend has no rumble; Windows uses XInput)"; }
#endif

static void PadRumble(int pad, float lo, float hi, float dur)
{
    if (!gCtl.vibration || pad < 0 || pad >= MAX_PLAYERS || !gPad[pad].avail) return;
    gPad[pad].rumbles++;
    if (dur > gPad[pad].rumbleT) gPad[pad].rumbleT = dur;
    RumbleSet(pad, lo, hi);
}
static void PadRumbleSlot(int slot, float lo, float hi, float dur)
{
    if (slot < 0 || slot >= MAX_PLAYERS) return;
    if (gState != GS_MISSION && gState != GS_DM) return;
    PadRumble(gSlotPad[slot], lo, hi, dur);
}
static void RumbleStopAll(void)
{
    for (int i = 0; i < MAX_PLAYERS; i++) if (gPad[i].rumbleT > 0) { gPad[i].rumbleT = 0; RumbleSet(i, 0, 0); }
}

/* ------------------------------------------------------------------ */
/* controls.cfg                                                        */
/* ------------------------------------------------------------------ */
static const char *ControlsPath(void) { static char p[600]; snprintf(p, sizeof(p), "%scontrols.cfg", GetApplicationDirectory()); return p; }
static int ButtonFromName(const char *s)
{
    for (int b = 1; b < PADB_COUNT; b++) if (strcmp(s, BTN_NAME[b]) == 0) return b;
    return 0;
}
static void SaveControls(void)
{
    FILE *f = fopen(ControlsPath(), "w");
    if (!f) { TraceLog(LOG_WARNING, "PAD: could not write %s", ControlsPath()); return; }
    fprintf(f, "# FACILITY 64 controller settings (written by the game; edit freely)\n");
    fprintf(f, "# buttons: A B X Y LB RB LT RT BACK START LS RS D-UP D-DOWN D-LEFT D-RIGHT NONE\n");
    fprintf(f, "style = %s\n", STYLE_KEY[gCtl.style]);
    fprintf(f, "deadzone = %.2f\n", gCtl.deadzone);
    fprintf(f, "sensitivity = %.2f\n", gCtl.sens);
    fprintf(f, "trigger_threshold = %.2f\n", gCtl.trigger);
    fprintf(f, "invert_y = %d\n", gCtl.invertY);
    fprintf(f, "aim_acceleration = %d\n", gCtl.aimAccel);
    fprintf(f, "vibration = %d\n", gCtl.vibration);
    fprintf(f, "pad_assign = %s\n", gCtl.autoJoin ? "auto" : "join");
    for (int s = 0; s < STYLE_COUNT; s++)
        for (int a = 0; a < ACT_COUNT; a++) fprintf(f, "%s.%s = %s\n", STYLE_KEY[s], ACT_KEY[a], BTN_NAME[gCtl.map[s][a]]);
    fclose(f);
}
static void LoadControls(void)
{
    CtlDefaults();
    FILE *f = fopen(ControlsPath(), "r");
    if (!f) return;
    char line[256];
    while (fgets(line, sizeof(line), f)) {
        char key[96], val[96];
        if (line[0] == '#' || line[0] == ';') continue;
        if (sscanf(line, " %95[^= \t] = %95s", key, val) != 2) continue;
        float v = (float)atof(val);
        if (strcmp(key, "style") == 0) gCtl.style = strcmp(val, "classic") == 0 ? STYLE_CLASSIC : STYLE_MODERN;
        else if (strcmp(key, "deadzone") == 0) gCtl.deadzone = Clamp(v, 0.0f, 0.6f);
        else if (strcmp(key, "sensitivity") == 0) gCtl.sens = Clamp(v, 0.2f, 3.0f);
        else if (strcmp(key, "trigger_threshold") == 0) gCtl.trigger = Clamp(v, 0.05f, 0.95f);
        else if (strcmp(key, "invert_y") == 0) gCtl.invertY = v != 0;
        else if (strcmp(key, "aim_acceleration") == 0) gCtl.aimAccel = v != 0;
        else if (strcmp(key, "vibration") == 0) gCtl.vibration = v != 0;
        else if (strcmp(key, "pad_assign") == 0) gCtl.autoJoin = strcmp(val, "auto") == 0;
        else {
            for (int s = 0; s < STYLE_COUNT; s++) for (int a = 0; a < ACT_COUNT; a++) {
                char k[64]; snprintf(k, sizeof(k), "%s.%s", STYLE_KEY[s], ACT_KEY[a]);
                if (strcmp(key, k) == 0) gCtl.map[s][a] = strcmp(val, "NONE") == 0 ? 0 : (ButtonFromName(val) ? ButtonFromName(val) : gCtl.map[s][a]);
            }
        }
    }
    fclose(f);
}

/* ------------------------------------------------------------------ */
/* simulated pads: --pad-script FILE                                   */
/*   lines: TIME PAD COMMAND [ARGS]   (PAD 0-3, or - for global)        */
/*   connect NAME | disconnect | down BTN | up BTN | tap BTN |          */
/*   axis LX|LY|RX|RY|LT|RT VALUE | shot FILE.png | quit                */
/* ------------------------------------------------------------------ */
typedef struct { float t; int pad; char cmd[16]; char arg[160]; float val; bool done; } PadEvent;
#define MAX_PAD_EVENTS 512
static PadEvent gPadEv[MAX_PAD_EVENTS];
static int gPadEvN = 0;
static float gPadScriptT = 0;

static void PadScriptAdd(float t, int pad, const char *cmd, const char *arg, float val)
{
    if (gPadEvN >= MAX_PAD_EVENTS) return;
    PadEvent *e = &gPadEv[gPadEvN++];
    memset(e, 0, sizeof(*e));
    e->t = t; e->pad = pad; e->val = val;
    snprintf(e->cmd, sizeof(e->cmd), "%s", cmd);
    snprintf(e->arg, sizeof(e->arg), "%s", arg);
}
static bool LoadPadScript(const char *path)
{
    FILE *f = fopen(path, "r");
    if (!f) { TraceLog(LOG_WARNING, "PAD: cannot open pad script %s", path); return false; }
    char line[256];
    while (fgets(line, sizeof(line), f)) {
        float t; char ps[8], cmd[16], rest[160] = "";
        if (line[0] == '#' || sscanf(line, " %f %7s %15s %159[^\r\n]", &t, ps, cmd, rest) < 3) continue;
        int pad = ps[0] == '-' ? -1 : atoi(ps);
        float val = 0; char arg[160] = "";
        if (strcmp(cmd, "axis") == 0) sscanf(rest, "%159s %f", arg, &val);
        else snprintf(arg, sizeof(arg), "%s", rest);
        PadScriptAdd(t, pad, cmd, arg, val);
    }
    fclose(f);
    gPadSimActive = true;
    TraceLog(LOG_INFO, "PAD: loaded %d scripted pad events from %s (simulated pads replace real ones)", gPadEvN, path);
    return true;
}
static void PadScriptStep(float dt)
{
    if (!gPadEvN) return;
    gPadScriptT += dt;
    int n = gPadEvN;
    for (int i = 0; i < n; i++) {
        PadEvent *e = &gPadEv[i];
        if (e->done || e->t > gPadScriptT) continue;
        e->done = true;
        PadSim *s = (e->pad >= 0 && e->pad < MAX_PLAYERS) ? &gPadSim[e->pad] : NULL;
        if (strcmp(e->cmd, "quit") == 0) gQuitRequested = true;
        else if (strcmp(e->cmd, "shot") == 0) snprintf(gShotPending, sizeof(gShotPending), "%s", e->arg);
        else if (!s) continue;
        else if (strcmp(e->cmd, "connect") == 0) {
            memset(s, 0, sizeof(*s)); s->on = true; s->axis[4] = s->axis[5] = -1.0f;
            CopyStr(s->name, sizeof(s->name), e->arg[0] ? e->arg : "Simulated Xbox 360 Controller");
        }
        else if (strcmp(e->cmd, "disconnect") == 0) s->on = false;
        else if (strcmp(e->cmd, "axis") == 0) {
            for (int a = 0; a < PAD_AXES; a++) if (strcmp(e->arg, AXIS_NAME[a]) == 0) s->axis[a] = a >= 4 ? e->val*2.0f - 1.0f : e->val;
        } else {
            int b = ButtonFromName(e->arg);
            if (strcmp(e->cmd, "down") == 0) s->btn[b] = true;
            else if (strcmp(e->cmd, "up") == 0) s->btn[b] = false;
            else if (strcmp(e->cmd, "tap") == 0) { s->btn[b] = true; PadScriptAdd(gPadScriptT + 0.12f, e->pad, "up", e->arg, 0); }
        }
    }
}

/* ------------------------------------------------------------------ */
/* polling, hot-plug                                                   */
/* ------------------------------------------------------------------ */
static void PadOnConnect(int pad);
static void PadOnDisconnect(int pad);

static bool KbMouseActivity(void)
{
    for (int k = 32; k < 349; k++) if (IsKeyPressed(k)) return true;
    if (IsMouseButtonPressed(MOUSE_BUTTON_LEFT) || IsMouseButtonPressed(MOUSE_BUTTON_RIGHT)) return true;
    Vector2 md = GetMouseDelta();
    return fabsf(md.x) + fabsf(md.y) > 6.0f;
}

static bool PadActivity(int pad)
{
    PadState *s = &gPad[pad];
    if (!s->avail) return false;
    for (int b = 1; b < PADB_COUNT; b++) if (s->cur[b] && !s->prev[b]) return true;
    for (int a = 0; a < 4; a++) if (fabsf(s->axis[a]) > 0.5f) return true;
    return false;
}

static void PadPoll(float dt)
{
    PadScriptStep(dt);
    for (int i = 0; i < MAX_PLAYERS; i++) {
        PadState *s = &gPad[i];
        s->wasAvail = s->avail;
        memcpy(s->prev, s->cur, sizeof(s->cur));
        bool rawLT = false, rawRT = false;
        if (gPadSimActive) {
            PadSim *m = &gPadSim[i];
            s->avail = m->on;
            if (s->avail) {
                snprintf(s->name, sizeof(s->name), "%s", m->name);
                s->axisCount = PAD_AXES;
                memcpy(s->axis, m->axis, sizeof(s->axis));
                memcpy(s->cur, m->btn, sizeof(s->cur));
            }
        } else {
            s->avail = IsGamepadAvailable(i);
            if (s->avail) {
                const char *n = GetGamepadName(i);
                snprintf(s->name, sizeof(s->name), "%s", (n && n[0]) ? n : "Gamepad");
                s->axisCount = GetGamepadAxisCount(i);
                for (int a = 0; a < PAD_AXES; a++) s->axis[a] = a < s->axisCount ? GetGamepadAxisMovement(i, a) : (a >= 4 ? -1.0f : 0.0f);
                for (int b = 1; b < PADB_COUNT; b++) s->cur[b] = IsGamepadButtonDown(i, b);
                rawLT = s->cur[B_LT]; rawRT = s->cur[B_RT];
            }
        }
        if (!s->avail) {
            memset(s->cur, 0, sizeof(s->cur));
            for (int a = 0; a < PAD_AXES; a++) s->axis[a] = a >= 4 ? -1.0f : 0.0f;
            s->trigSeen[0] = s->trigSeen[1] = false;
        } else {
            /* analog triggers -> digital with our own threshold. Some drivers report 0 (= half pressed)
               until the trigger is first touched, so a trigger only counts once it has been seen at rest. */
            for (int t = 0; t < 2; t++) {
                int b = t ? B_RT : B_LT;
                if (s->axisCount > 4 + t) {
                    if (s->axis[4 + t] < -0.8f) s->trigSeen[t] = true;
                    s->cur[b] = s->trigSeen[t] && PadTrigger(i, t) > gCtl.trigger;
                } else s->cur[b] = t ? rawRT : rawLT;
            }
        }
        if (s->rumbleT > 0) { s->rumbleT -= dt; if (s->rumbleT <= 0) { s->rumbleT = 0; RumbleSet(i, 0, 0); } }
        if (s->avail && !s->wasAvail) PadOnConnect(i);
        if (!s->avail && s->wasAvail) PadOnDisconnect(i);
        if (PadActivity(i)) {
            s->idleT = 0; gUiPadMode = true;
            int sl = PadSlotOf(i);
            if (sl >= 0) gSlotPadActive[sl] = true;
        } else s->idleT += dt;
    }
    if (KbMouseActivity()) { gUiPadMode = false; gSlotPadActive[0] = false; }
}

/* ------------------------------------------------------------------ */
/* menu input: keyboard + every pad, with key repeat                   */
/* ------------------------------------------------------------------ */
typedef struct { int dx, dy; bool ok, back, start; int src; } UiIn;
static float gNavT[4], gNavRep[4];

static UiIn UiPoll(float dt)
{
    UiIn u = { 0 };
    u.src = -1;
    bool held[4] = {
        IsKeyDown(KEY_UP) || IsKeyDown(KEY_W), IsKeyDown(KEY_DOWN) || IsKeyDown(KEY_S),
        IsKeyDown(KEY_LEFT) || IsKeyDown(KEY_A), IsKeyDown(KEY_RIGHT) || IsKeyDown(KEY_D)
    };
    for (int p = 0; p < MAX_PLAYERS; p++) {
        if (!gPad[p].avail) continue;
        float lx = gPad[p].axis[0], ly = gPad[p].axis[1];
        if (PadDown(p, B_DUP) || ly < -0.6f) held[0] = true;
        if (PadDown(p, B_DDOWN) || ly > 0.6f) held[1] = true;
        if (PadDown(p, B_DLEFT) || lx < -0.6f) held[2] = true;
        if (PadDown(p, B_DRIGHT) || lx > 0.6f) held[3] = true;
        if (PadPressed(p, B_A)) { u.ok = true; u.src = p; }
        if (PadPressed(p, B_B)) { u.back = true; u.src = p; }
        if (PadPressed(p, B_START)) { u.start = true; u.src = p; }
    }
    for (int d = 0; d < 4; d++) {
        bool fire = false;
        if (held[d]) {
            if (gNavT[d] == 0) fire = true;
            gNavT[d] += dt;
            if (gNavT[d] > 0.4f) { gNavRep[d] += dt; if (gNavRep[d] > 0.09f) { gNavRep[d] = 0; fire = true; } }
        } else gNavT[d] = gNavRep[d] = 0;
        if (fire) { if (d == 0) u.dy--; else if (d == 1) u.dy++; else if (d == 2) u.dx--; else u.dx++; }
    }
    if (IsKeyPressed(KEY_ENTER) || IsKeyPressed(KEY_KP_ENTER) || IsKeyPressed(KEY_SPACE)) u.ok = true;
    if (IsKeyPressed(KEY_ESCAPE) || IsKeyPressed(KEY_BACKSPACE)) u.back = true;
    return u;
}

/* prompt helpers: pad names when a pad was used last, keyboard otherwise */
static const char *Pr(const char *pad, const char *key) { return gUiPadMode ? pad : key; }

/* ------------------------------------------------------------------ */
/* per-player game input                                               */
/* ------------------------------------------------------------------ */
static void ReadPadInput(int pad, PlayerInput *in, float dt)
{
    if (pad < 0 || pad >= MAX_PLAYERS || !gPad[pad].avail) return;
    PadState *s = &gPad[pad];
    Vector2 L = PadStick(pad, 0), R = PadStick(pad, 2), mv, lk;
    if (gCtl.style == STYLE_CLASSIC) {
        lk = L;
        /* the right stick behaves like four digital walk/strafe buttons */
        mv.x = R.x > 0.35f ? 1.0f : R.x < -0.35f ? -1.0f : 0.0f;
        mv.y = R.y > 0.35f ? 1.0f : R.y < -0.35f ? -1.0f : 0.0f;
        if (PadDown(pad, B_DUP)) mv.y = -1;
        if (PadDown(pad, B_DDOWN)) mv.y = 1;
        if (PadDown(pad, B_DLEFT)) mv.x = -1;
        if (PadDown(pad, B_DRIGHT)) mv.x = 1;
    } else { mv = L; lk = R; }
    in->move -= mv.y;
    in->strafe += mv.x;
    float m = sqrtf(lk.x*lk.x + lk.y*lk.y);
    if (m > 1e-5f) { float c = powf(fminf(m, 1.0f), 1.7f)/m; lk.x *= c; lk.y *= c; }   /* fine aim near centre */
    bool aim = ActDown(pad, ACT_AIM);
    float accel = 1.0f;
    if (gCtl.aimAccel && fabsf(lk.x) > 0.8f) { s->accelT += dt; accel = 1.0f + Clamp((s->accelT - 0.2f)/0.5f, 0, 1); }
    else s->accelT = 0;
    float turnRate = 3.0f*gCtl.sens*accel, pitchRate = 1.9f*gCtl.sens;
    if (aim) { turnRate *= 0.4f; pitchRate *= 0.4f; }
    in->turn += lk.x*turnRate*dt;
    in->look += (gCtl.invertY ? lk.y : -lk.y)*pitchRate*dt;
    in->aim = in->aim || aim;
    in->fire = in->fire || ActDown(pad, ACT_FIRE);
    in->firePressed = in->firePressed || ActPressed(pad, ACT_FIRE);
    in->reload = in->reload || ActPressed(pad, ACT_RELOAD);
    in->nextWeapon = in->nextWeapon || ActPressed(pad, ACT_NEXTWPN);
    in->use = in->use || ActPressed(pad, ACT_USE);
    in->silencer = in->silencer || ActPressed(pad, ACT_SILENCER);
}

static PlayerInput ReadSlotInput(int slot, bool dm, float dt)
{
    PlayerInput in = { 0 };
    in.selectWeapon = -1;
    if (slot == 0) in = ReadInputP1(dm, dt);
    else if (slot == gKb2Slot) in = ReadInputP2(dt);
    ReadPadInput(gSlotPad[slot], &in, dt);
    return in;
}

static bool AnyPausePressed(void)
{
    for (int s = 0; s < numPlayers; s++) {
        int p = gSlotPad[s];
        if (p >= 0 && (ActPressed(p, ACT_PAUSE) || PadPressed(p, B_BACK))) return true;
    }
    return false;
}

/* mission: player 1 picks up whichever pad is used if it has none (or its pad is gone) */
static void MissionAutoAssign(void)
{
    int cur = gSlotPad[0];
    if (cur >= 0 && gPad[cur].avail) return;
    if (gPadLostSlot == 0) return;   /* handled by the pause screen */
    for (int p = 0; p < MAX_PLAYERS; p++)
        if (gPad[p].avail && PadActivity(p)) { gSlotPad[0] = p; gSlotPadActive[0] = true; break; }
}

/* ------------------------------------------------------------------ */
/* join-in lobby for deathmatch                                        */
/* ------------------------------------------------------------------ */
static void StartDeathmatch(void);
static void StartMission(void);
static void StartTitle(void);

static int LobbyCount(void) { int n = 0; for (int s = 0; s < MAX_PLAYERS; s++) n += gSlotJoined[s]; return n; }
static int LobbyFree(void) { for (int s = 1; s < MAX_PLAYERS; s++) if (!gSlotJoined[s]) return s; return -1; }
static void LobbyCompact(void)
{
    for (int s = 1; s < MAX_PLAYERS; s++) {
        if (gSlotJoined[s]) continue;
        for (int t = s + 1; t < MAX_PLAYERS; t++) if (gSlotJoined[t]) {
            gSlotJoined[s] = true; gSlotPad[s] = gSlotPad[t]; if (gKb2Slot == t) gKb2Slot = s;
            gSlotJoined[t] = false; gSlotPad[t] = -1;
            break;
        }
    }
}
static void LobbyJoinPad(int pad)
{
    if (PadSlotOf(pad) >= 0) return;
    char b[96];
    int s = (gCtl.autoJoin && gSlotPad[0] < 0) ? 0 : LobbyFree();
    if (s < 0) { Toast("LOBBY FULL (4 PLAYERS)"); return; }
    gSlotJoined[s] = true; gSlotPad[s] = pad;
    snprintf(b, sizeof(b), "PLAYER %d JOINED (CONTROLLER %d)", s + 1, pad + 1); Toast(b);
}
static void LobbyLeave(int s)
{
    if (s <= 0) return;
    gSlotJoined[s] = false; gSlotPad[s] = -1; if (gKb2Slot == s) gKb2Slot = -1;
    LobbyCompact();
}
static void ResetSlots(void)
{
    for (int s = 0; s < MAX_PLAYERS; s++) { gSlotPad[s] = -1; gSlotJoined[s] = s == 0; gSlotPadActive[s] = false; }
    gKb2Slot = -1; gPadLostSlot = -1;
}
static void OpenLobby(int src)
{
    gState = GS_LOBBY;
    ResetSlots();
    if (src >= 0) { gSlotPad[0] = src; gSlotPadActive[0] = true; }
    if (gCtl.autoJoin) for (int p = 0; p < MAX_PLAYERS; p++) if (gPad[p].avail) LobbyJoinPad(p);
}
static void LobbyStart(void)
{
    if (LobbyCount() < 2) {
        int s = LobbyFree();
        gSlotJoined[s] = true; gKb2Slot = s;
        Toast("PLAYER 2 ADDED ON THE KEYBOARD (ARROW KEYS)");
    }
    gDmPlayers = LobbyCount();
    StartDeathmatch();
}
static void UpdateLobby(UiIn u)
{
    for (int p = 0; p < MAX_PLAYERS; p++) {
        if (!gPad[p].avail) continue;
        int sl = PadSlotOf(p);
        if (sl < 0) {
            if (PadPressed(p, B_A) || PadPressed(p, B_START)) LobbyJoinPad(p);
            else if (PadPressed(p, B_BACK)) { gSlotPad[0] = p; Toast("CONTROLLER NOW SHARES PLAYER 1 WITH THE KEYBOARD"); }
            continue;
        }
        if (PadPressed(p, B_START)) { LobbyStart(); return; }
        if (PadPressed(p, B_B)) {
            if (sl == 0) { StartTitle(); return; }
            LobbyLeave(sl);
            Toast("PLAYER LEFT");
        } else if (PadPressed(p, B_BACK) && sl != 0) {
            LobbyLeave(sl);
            gSlotPad[0] = p; Toast("CONTROLLER NOW SHARES PLAYER 1 WITH THE KEYBOARD");
        }
    }
    if (IsKeyPressed(KEY_K)) {
        if (gKb2Slot >= 0) LobbyLeave(gKb2Slot);
        else { int s = LobbyFree(); if (s > 0) { gSlotJoined[s] = true; gKb2Slot = s; } }
    }
    if (IsKeyPressed(KEY_ENTER) || IsKeyPressed(KEY_KP_ENTER) || IsKeyPressed(KEY_SPACE)) { LobbyStart(); return; }
    if (IsKeyPressed(KEY_ESCAPE)) StartTitle();
    (void)u;
}

static void PadOnConnect(int pad)
{
    char b[128];
    snprintf(b, sizeof(b), "CONTROLLER %d CONNECTED: %s", pad + 1, gPad[pad].name); Toast(b);
    TraceLog(LOG_INFO, "PAD: %d connected: %s (%d axes)", pad, gPad[pad].name, gPad[pad].axisCount);
    int sl = PadSlotOf(pad);
    if (sl >= 0 && gPadLostSlot == sl) {
        gPadLostSlot = -1;
        snprintf(b, sizeof(b), "PLAYER %d CONTROLLER RECONNECTED - PRESS START TO RESUME", sl + 1); Toast(b);
        return;
    }
    if (sl < 0 && gCtl.autoJoin) {
        if (gState == GS_LOBBY) LobbyJoinPad(pad);
        else if ((gState == GS_MISSION || gState == GS_TITLE) && (gSlotPad[0] < 0 || !gPad[gSlotPad[0]].avail)) gSlotPad[0] = pad;
    }
}
static void PadOnDisconnect(int pad)
{
    char b[128];
    int sl = PadSlotOf(pad);
    gPad[pad].rumbleT = 0;
    if (sl >= 0 && (gState == GS_MISSION || gState == GS_DM) && sl < numPlayers) {
        bool over = (gState == GS_MISSION && gMissionResult != 0) || (gState == GS_DM && gDmWinner >= 0);
        if (!over && (gState == GS_DM || gSlotPadActive[sl])) {
            gPaused = true; gPadLostSlot = sl;
            snprintf(b, sizeof(b), "PLAYER %d CONTROLLER DISCONNECTED - PAUSED", sl + 1); Toast(b);
            return;
        }
    }
    if (gState == GS_LOBBY && sl > 0) { LobbyLeave(sl); }
    else if (gState == GS_LOBBY && sl == 0) gSlotPad[0] = -1;
    snprintf(b, sizeof(b), "CONTROLLER %d DISCONNECTED", pad + 1); Toast(b);
}

/* while paused for a lost pad: any unassigned pad can take over that player */
static void PadTakeOver(void)
{
    if (gPadLostSlot < 0) return;
    for (int p = 0; p < MAX_PLAYERS; p++) {
        if (!gPad[p].avail || PadSlotOf(p) >= 0) continue;
        if (PadPressed(p, B_A) || PadPressed(p, B_START)) {
            char b[96];
            gSlotPad[gPadLostSlot] = p;
            snprintf(b, sizeof(b), "CONTROLLER %d NOW CONTROLS PLAYER %d", p + 1, gPadLostSlot + 1); Toast(b);
            gPadLostSlot = -1;
            return;
        }
    }
}

/* ------------------------------------------------------------------ */
/* options / remap / debug screens                                     */
/* ------------------------------------------------------------------ */
typedef enum { UI_NONE, UI_OPTIONS, UI_REMAP, UI_DEBUG } UiScreen;
static UiScreen gUi = UI_NONE;
static int gOptSel = 0, gRemapSel = 0, gTitleSel = 0, gWatchSel = 0;
static bool gRemapListen = false, gRemapArmed = false;
static float gRemapT = 0, gDebugBackT = 0;
static int gRemapStyle = 0;

enum { OPT_STYLE, OPT_SENS, OPT_DEADZONE, OPT_INVERT, OPT_ACCEL, OPT_TRIGGER, OPT_VIBRATION, OPT_ASSIGN,
       OPT_REMAP, OPT_DEBUG, OPT_RESET, OPT_BACK, OPT_COUNT };

static void OpenOptions(void) { gUi = UI_OPTIONS; gOptSel = 0; }
static void CloseOptions(void) { SaveControls(); gUi = UI_NONE; Toast("CONTROLLER SETTINGS SAVED TO controls.cfg"); }

static void UpdateOptions(UiIn u)
{
    gOptSel = (gOptSel + u.dy + OPT_COUNT) % OPT_COUNT;
    int dx = u.dx;
    bool ok = u.ok || u.start;
    switch (gOptSel) {
        case OPT_STYLE: if (dx || ok) gCtl.style = (gCtl.style + 1) % STYLE_COUNT; break;
        case OPT_SENS: gCtl.sens = Clamp(roundf((gCtl.sens + dx*0.1f)*10)/10, 0.2f, 3.0f); break;
        case OPT_DEADZONE: gCtl.deadzone = Clamp(roundf((gCtl.deadzone + dx*0.01f)*100)/100, 0.05f, 0.45f); break;
        case OPT_INVERT: if (dx || ok) gCtl.invertY = !gCtl.invertY; break;
        case OPT_ACCEL: if (dx || ok) gCtl.aimAccel = !gCtl.aimAccel; break;
        case OPT_TRIGGER: gCtl.trigger = Clamp(roundf((gCtl.trigger + dx*0.05f)*100)/100, 0.10f, 0.90f); break;
        case OPT_VIBRATION:
            if (dx || ok) {
                gCtl.vibration = !gCtl.vibration;
                if (gCtl.vibration) for (int p = 0; p < MAX_PLAYERS; p++) PadRumble(p, 0.4f, 0.6f, 0.25f);
                if (!RumbleSupported()) Toast("VIBRATION IS NOT SUPPORTED ON THIS PLATFORM");
            }
            break;
        case OPT_ASSIGN: if (dx || ok) gCtl.autoJoin = !gCtl.autoJoin; break;
        case OPT_REMAP: if (ok) { gUi = UI_REMAP; gRemapSel = 0; gRemapListen = false; gRemapStyle = gCtl.style; } break;
        case OPT_DEBUG: if (ok) { gUi = UI_DEBUG; gDebugBackT = 0; } break;
        case OPT_RESET: if (ok) { CtlDefaults(); Toast("CONTROLLER SETTINGS RESET TO DEFAULTS"); } break;
        case OPT_BACK: if (ok) { CloseOptions(); return; } break;
    }
    if (u.back) CloseOptions();
}

static void UpdateRemap(UiIn u, float dt)
{
    const int rows = ACT_COUNT + 2;
    if (gRemapListen) {
        gRemapT += dt;
        bool anyDown = false;
        for (int p = 0; p < MAX_PLAYERS; p++) for (int b = 1; b < PADB_COUNT; b++) if (gPad[p].cur[b]) anyDown = true;
        if (!gRemapArmed) { if (!anyDown) gRemapArmed = true; }
        else {
            for (int p = 0; p < MAX_PLAYERS; p++) for (int b = 1; b < PADB_COUNT; b++) {
                if (b == B_GUIDE || !PadPressed(p, b)) continue;
                gCtl.map[gRemapStyle][gRemapSel] = b;
                char t[96]; snprintf(t, sizeof(t), "%s = %s", ACT_LABEL[gRemapSel], BTN_NAME[b]); Toast(t);
                gRemapListen = false;
                for (int q = 0; q < MAX_PLAYERS; q++) memcpy(gPad[q].prev, gPad[q].cur, sizeof(gPad[q].cur)); /* swallow */
                return;
            }
        }
        if (IsKeyPressed(KEY_ESCAPE) || IsKeyPressed(KEY_BACKSPACE) || gRemapT > 6.0f) { gRemapListen = false; Toast("REMAP CANCELLED"); }
        return;
    }
    gRemapSel = (gRemapSel + u.dy + rows) % rows;
    if (u.dx) gRemapStyle = (gRemapStyle + 1) % STYLE_COUNT;
    if (u.ok) {
        if (gRemapSel < ACT_COUNT) { gRemapListen = true; gRemapArmed = false; gRemapT = 0; }
        else if (gRemapSel == ACT_COUNT) { memcpy(gCtl.map[gRemapStyle], DEFAULT_MAP[gRemapStyle], sizeof(gCtl.map[0])); Toast("DEFAULT BUTTONS RESTORED"); }
        else { gUi = UI_OPTIONS; return; }
    }
    if (u.back) gUi = UI_OPTIONS;
}

static void UpdateDebug(float dt)
{
    bool bHeld = false;
    for (int p = 0; p < MAX_PLAYERS; p++) {
        if (PadDown(p, B_B)) bHeld = true;
        if (PadDown(p, B_LB) && PadDown(p, B_RB) && gPad[p].rumbleT <= 0) PadRumble(p, 0.6f, 0.9f, 0.5f);
    }
    gDebugBackT = bHeld ? gDebugBackT + dt : 0;
    if (gDebugBackT > 1.0f || IsKeyPressed(KEY_ESCAPE) || IsKeyPressed(KEY_BACKSPACE)) { gUi = UI_OPTIONS; gDebugBackT = 0; }
}

/* returns true while a screen owns the input */
static bool UpdateUiScreens(UiIn u, float dt)
{
    switch (gUi) {
        case UI_OPTIONS: UpdateOptions(u); return true;
        case UI_REMAP: UpdateRemap(u, dt); return true;
        case UI_DEBUG: UpdateDebug(dt); return true;
        default: return false;
    }
}

/* ---------------- drawing ---------------- */
static void UiPanel(Rectangle r, const char *title)
{
    DrawRectangle(0, 0, GetScreenWidth(), GetScreenHeight(), Fade(BLACK, 0.7f));
    DrawRectangleRounded(r, 0.04f, 8, Fade((Color){ 14, 20, 24, 255 }, 0.985f));
    DrawRectangleRoundedLinesEx(r, 0.04f, 8, 2, Fade(GOLD, 0.7f));
    DrawText(title, (int)r.x + 28, (int)r.y + 18, 30, GOLD);
}
static void UiRow(int x, int y, int w, bool sel, const char *label, const char *val, Color vc)
{
    if (sel) {
        DrawRectangle(x - 10, y - 5, w + 20, 30, Fade(GOLD, 0.18f));
        DrawRectangle(x - 10, y - 5, 4, 30, GOLD);
    }
    DrawText(label, x, y, 20, sel ? RAYWHITE : (Color){ 190, 195, 200, 255 });
    if (val) {
        char b[96];
        snprintf(b, sizeof(b), sel ? "<  %s  >" : "%s", val);
        DrawText(b, x + w - MeasureText(b, 20), y, 20, vc);
    }
}
static void UiFooter(Rectangle r, const char *t)
{
    DrawText(t, (int)(r.x + r.width/2 - MeasureText(t, 18)/2), (int)(r.y + r.height - 34), 18, SKYBLUE);
}

/* the active pad for live previews: the most recently used one */
static int ActivePreviewPad(void)
{
    int best = -1; float bt = 1e9f;
    for (int p = 0; p < MAX_PLAYERS; p++) if (gPad[p].avail && gPad[p].idleT < bt) { bt = gPad[p].idleT; best = p; }
    return best;
}

static void DrawStickPreview(int cx, int cy, int r, int pad, int ax, const char *label)
{
    DrawCircle(cx, cy, (float)r, (Color){ 30, 36, 40, 255 });
    DrawCircleLines(cx, cy, (float)r, GRAY);
    DrawCircle(cx, cy, r*gCtl.deadzone, Fade(RED, 0.35f));
    DrawText(label, cx - MeasureText(label, 16)/2, cy + r + 6, 16, LIGHTGRAY);
    if (pad < 0) return;
    Vector2 raw = { gPad[pad].axis[ax], gPad[pad].axis[ax + 1] };
    Vector2 o = RadialDeadzone(raw, gCtl.deadzone);
    DrawCircle(cx + (int)(raw.x*r), cy + (int)(raw.y*r), 5, LIGHTGRAY);
    DrawCircle(cx + (int)(o.x*r), cy + (int)(o.y*r), 4, (Color){ 120, 255, 140, 255 });
}

static void DrawOptions(void)
{
    Rectangle r = { 120, 50, 1040, 620 };
    UiPanel(r, "OPTIONS: CONTROLLER");
    char v[OPT_COUNT][64];
    snprintf(v[OPT_STYLE], 64, "%s", STYLE_NAME[gCtl.style]);
    snprintf(v[OPT_SENS], 64, "%.1f", gCtl.sens);
    snprintf(v[OPT_DEADZONE], 64, "%.2f", gCtl.deadzone);
    snprintf(v[OPT_INVERT], 64, "%s", gCtl.invertY ? "ON" : "OFF");
    snprintf(v[OPT_ACCEL], 64, "%s", gCtl.aimAccel ? "ON" : "OFF");
    snprintf(v[OPT_TRIGGER], 64, "%.0f%%", gCtl.trigger*100);
    snprintf(v[OPT_VIBRATION], 64, "%s%s", gCtl.vibration ? "ON" : "OFF", RumbleSupported() ? "" : " (UNSUPPORTED)");
    snprintf(v[OPT_ASSIGN], 64, "%s", gCtl.autoJoin ? "AUTO (CONNECTION ORDER)" : "PRESS A / START TO JOIN");
    const char *lab[OPT_COUNT] = { "Control style", "Look sensitivity", "Stick deadzone (radial)", "Invert look Y", "Aim acceleration",
                                   "Trigger threshold", "Vibration", "Deathmatch pad assignment", "Remap buttons...",
                                   "Controller debug...", "Reset to defaults", "Back (save)" };
    int x = (int)r.x + 40, y = (int)r.y + 76, w = 600;
    for (int i = 0; i < OPT_COUNT; i++) {
        bool hasVal = i < OPT_REMAP;
        UiRow(x, y, w, gOptSel == i, lab[i], hasVal ? v[i] : NULL, i == OPT_VIBRATION && !RumbleSupported() ? ORANGE : (Color){ 140, 230, 160, 255 });
        y += i == OPT_ASSIGN || i == OPT_DEBUG ? 44 : 36;
    }
    /* right column: style + layout + live deadzone */
    int rx = (int)r.x + 700, ry = (int)r.y + 76;
    DrawText(STYLE_NAME[gCtl.style], rx, ry, 20, GOLD); ry += 28;
    ry += DrawTextBoxed(STYLE_DESC[gCtl.style], rx, ry, 300, 16, LIGHTGRAY) + 6;
    for (int a = 0; a < ACT_COUNT; a++) {
        DrawText(ACT_LABEL[a], rx, ry, 16, (Color){ 190, 195, 200, 255 });
        DrawText(ActBtn((PadAction)a), rx + 300 - MeasureText(ActBtn((PadAction)a), 16), ry, 16, (Color){ 140, 230, 160, 255 });
        ry += 21;
    }
    int pad = ActivePreviewPad();
    DrawStickPreview(rx + 70, ry + 70, 52, pad, 0, "LEFT STICK");
    DrawStickPreview(rx + 230, ry + 70, 52, pad, 2, "RIGHT STICK");
    DrawText(pad >= 0 ? "grey: raw   green: after deadzone" : "no controller connected", rx, ry + 150, 14, GRAY);
    if (gOptSel == OPT_VIBRATION && !RumbleSupported())
        DrawTextBoxed(TextFormat("Note: vibration %s.", RumbleBackend()), x, (int)(r.y + r.height - 80), 640, 16, ORANGE);
    UiFooter(r, gUiPadMode ? "D-PAD/STICK: select + change    A: choose    B: back (saves)"
                           : "ARROWS/WS: select   LEFT/RIGHT: change   ENTER: choose   ESC: back (saves)");
}

static void DrawRemap(void)
{
    Rectangle r = { 200, 70, 880, 580 };
    UiPanel(r, "REMAP BUTTONS");
    char t[128];
    snprintf(t, sizeof(t), "Layout:  < %s >   (LEFT/RIGHT to switch)", STYLE_NAME[gRemapStyle]);
    DrawText(t, (int)r.x + 30, (int)r.y + 62, 18, LIGHTGRAY);
    int x = (int)r.x + 50, y = (int)r.y + 110, w = 760;
    for (int a = 0; a < ACT_COUNT; a++) {
        int b = gCtl.map[gRemapStyle][a];
        bool shared = false;
        for (int o = 0; o < ACT_COUNT; o++) if (o != a && b && gCtl.map[gRemapStyle][o] == b) shared = true;
        snprintf(t, sizeof(t), "%s%s", BTN_NAME[b], shared ? "  (shared)" : "");
        bool listen = gRemapListen && gRemapSel == a;
        UiRow(x, y, w, gRemapSel == a, ACT_LABEL[a], listen ? "PRESS A BUTTON..." : t,
              listen ? (Color){ 255, (unsigned char)(180 + 70*sinf(gTime*10)), 80, 255 } : (Color){ 140, 230, 160, 255 });
        y += 38;
    }
    y += 10;
    UiRow(x, y, w, gRemapSel == ACT_COUNT, "Reset this layout to defaults", NULL, WHITE); y += 38;
    UiRow(x, y, w, gRemapSel == ACT_COUNT + 1, "Back", NULL, WHITE);
    if (gRemapListen) {
        Rectangle m = { r.x + 190, r.y + 200, 500, 150 };
        DrawRectangleRounded(m, 0.1f, 6, Fade(BLACK, 0.9f));
        DrawRectangleRoundedLinesEx(m, 0.1f, 6, 2, ORANGE);
        snprintf(t, sizeof(t), "PRESS A BUTTON FOR  %s", ACT_LABEL[gRemapSel]);
        DrawText(t, (int)(m.x + m.width/2 - MeasureText(t, 20)/2), (int)m.y + 30, 20, RAYWHITE);
        const char *s = gRemapArmed ? "any button, trigger or stick click on any controller" : "release all buttons...";
        DrawText(s, (int)(m.x + m.width/2 - MeasureText(s, 16)/2), (int)m.y + 70, 16, LIGHTGRAY);
        snprintf(t, sizeof(t), "ESC or wait %.0fs to cancel", fmaxf(0, 6.0f - gRemapT));
        DrawText(t, (int)(m.x + m.width/2 - MeasureText(t, 16)/2), (int)m.y + 104, 16, GRAY);
    }
    UiFooter(r, gUiPadMode ? "A: remap selected   B: back" : "ENTER: remap selected   ESC: back");
}

static void DrawDebug(void)
{
    int W = GetScreenWidth(), H = GetScreenHeight();
    DrawRectangle(0, 0, W, H, Fade((Color){ 8, 10, 12, 255 }, 0.96f));
    DrawText("CONTROLLER DEBUG", 30, 18, 30, GOLD);
    char t[200];
    snprintf(t, sizeof(t), "%s   |   rumble: %s   |   hold LB+RB to test rumble   |   hold B (1s) or ESC to go back",
             gPadSimActive ? "SIMULATED PADS (--pad-script)" : "raylib/GLFW gamepads", RumbleSupported() ? "XInput" : "unsupported");
    DrawText(t, 30, 56, 16, LIGHTGRAY);
    for (int p = 0; p < MAX_PLAYERS; p++) {
        int px = 30 + (p % 2)*615, py = 86 + (p/2)*312, pw = 600, ph = 300;
        PadState *s = &gPad[p];
        DrawRectangleRounded((Rectangle){ (float)px, (float)py, (float)pw, (float)ph }, 0.04f, 6, s->avail ? (Color){ 20, 30, 34, 255 } : (Color){ 18, 18, 20, 255 });
        DrawRectangleRoundedLinesEx((Rectangle){ (float)px, (float)py, (float)pw, (float)ph }, 0.04f, 6, 1.5f, s->avail ? Fade(GOLD, 0.6f) : DARKGRAY);
        int sl = PadSlotOf(p);
        snprintf(t, sizeof(t), "PAD %d  %s", p, s->avail ? "CONNECTED" : "not connected");
        DrawText(t, px + 14, py + 10, 20, s->avail ? (Color){ 120, 255, 140, 255 } : GRAY);
        if (!s->avail) continue;
        snprintf(t, sizeof(t), "%s", s->name);
        DrawText(t, px + 14, py + 36, 16, RAYWHITE);
        snprintf(t, sizeof(t), "axes %d   player slot %s   rumble requests %d%s", s->axisCount, sl >= 0 ? TextFormat("P%d", sl + 1) : "-", s->rumbles, s->rumbleT > 0 ? "  [RUMBLING]" : "");
        DrawText(t, px + 14, py + 56, 14, LIGHTGRAY);
        for (int a = 0; a < PAD_AXES; a++) {
            int ay = py + 82 + a*22;
            float v = s->axis[a];
            DrawText(AXIS_NAME[a], px + 14, ay, 16, LIGHTGRAY);
            DrawRectangle(px + 50, ay + 2, 200, 12, (Color){ 40, 44, 50, 255 });
            DrawRectangle(px + 150, ay, 1, 16, GRAY);
            int bx = (int)(px + 150 + Clamp(v, -1, 1)*100);
            DrawRectangle(bx < px + 150 ? bx : px + 150, ay + 2, abs(bx - (px + 150)), 12, a >= 4 ? ORANGE : SKYBLUE);
            DrawText(TextFormat("%+.2f", v), px + 258, ay, 16, RAYWHITE);
        }
        DrawStickPreview(px + 380, py + 140, 40, p, 0, "L");
        DrawStickPreview(px + 500, py + 140, 40, p, 2, "R");
        for (int b = 1; b < PADB_COUNT; b++) {
            int col = (b - 1) % 9, row = (b - 1)/9;
            int bx = px + 14 + col*64, by = py + 222 + row*34;
            bool on = s->cur[b];
            DrawRectangleRounded((Rectangle){ (float)bx, (float)by, 58, 26 }, 0.3f, 4, on ? (Color){ 230, 190, 60, 255 } : (Color){ 44, 48, 54, 255 });
            DrawText(BTN_NAME[b], bx + 29 - MeasureText(BTN_NAME[b], 14)/2, by + 6, 14, on ? BLACK : LIGHTGRAY);
        }
    }
    if (gDebugBackT > 0) DrawRectangle(0, H - 6, (int)(W*gDebugBackT), 6, GOLD);
}

static void DrawUiScreens(void)
{
    if (gUi == UI_OPTIONS) DrawOptions();
    else if (gUi == UI_REMAP) DrawRemap();
    else if (gUi == UI_DEBUG) DrawDebug();
}

static void InitPads(void)
{
    LoadControls();
    RumbleInit();
    const char *db = TextFormat("%sgamecontrollerdb.txt", GetApplicationDirectory());
    if (FileExists(db)) {
        char *txt = LoadFileText(db);
        if (txt) { int n = SetGamepadMappings(txt); TraceLog(LOG_INFO, "PAD: gamecontrollerdb.txt loaded (%d)", n); UnloadFileText(txt); }
    }
}

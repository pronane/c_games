/* input.c : keyboard + gamepad input with an N64-style default layout,
 * SDL gamepad database, hot-plugging, raw-joystick fallback and remapping.
 *
 *   N64          modern pad (Xbox names)        keyboard
 *   A  accel     A (bottom face)                W / Up / X
 *   B  brake     X (left face) or B (right)     S / Down / Z
 *   R  hop/drift RB  (RT also works)            Space / Shift / C
 *   Z  item      LT  (LB also works)            E / Ctrl / V
 *   Start pause  Start / Menu                   Esc / P
 */
#include "common.h"
#include "padraw.h"

static const char *ACTION_NAMES[NUM_PAD_ACTIONS] = { "Accelerate (A)", "Brake / reverse (B)", "Hop / drift (R)", "Use item (Z)", "Pause (Start)" };
const char *PadActionName(int a) { return ACTION_NAMES[a]; }

PadBind gBinds[2][NUM_PAD_ACTIONS][2];
static int gPadDbLoaded[2];

void InputDefaultBinds(int set)
{
    memset(gBinds[set], 0, sizeof gBinds[set]);
    if (set == 0) {
        gBinds[0][PA_ACCEL][0] = (PadBind){ BIND_STD_BUTTON, GAMEPAD_BUTTON_RIGHT_FACE_DOWN };
        gBinds[0][PA_BRAKE][0] = (PadBind){ BIND_STD_BUTTON, GAMEPAD_BUTTON_RIGHT_FACE_LEFT };
        gBinds[0][PA_BRAKE][1] = (PadBind){ BIND_STD_BUTTON, GAMEPAD_BUTTON_RIGHT_FACE_RIGHT };
        gBinds[0][PA_HOP][0]   = (PadBind){ BIND_STD_BUTTON, GAMEPAD_BUTTON_RIGHT_TRIGGER_1 };
        gBinds[0][PA_HOP][1]   = (PadBind){ BIND_STD_AXIS, GAMEPAD_AXIS_RIGHT_TRIGGER };
        gBinds[0][PA_ITEM][0]  = (PadBind){ BIND_STD_AXIS, GAMEPAD_AXIS_LEFT_TRIGGER };
        gBinds[0][PA_ITEM][1]  = (PadBind){ BIND_STD_BUTTON, GAMEPAD_BUTTON_LEFT_TRIGGER_1 };
        gBinds[0][PA_PAUSE][0] = (PadBind){ BIND_STD_BUTTON, GAMEPAD_BUTTON_MIDDLE_RIGHT };
    } else {
        /* generic DirectInput pad (EasySMX "D-input" mode and most cheap USB pads):
           0 = Y/triangle, 1 = B/circle, 2 = A/cross, 3 = X/square, 4 LB, 5 RB, 6 LT, 7 RT, 8 select, 9 start */
        gBinds[1][PA_ACCEL][0] = (PadBind){ BIND_RAW_BUTTON, 2 };
        gBinds[1][PA_BRAKE][0] = (PadBind){ BIND_RAW_BUTTON, 3 };
        gBinds[1][PA_BRAKE][1] = (PadBind){ BIND_RAW_BUTTON, 1 };
        gBinds[1][PA_HOP][0]   = (PadBind){ BIND_RAW_BUTTON, 5 };
        gBinds[1][PA_HOP][1]   = (PadBind){ BIND_RAW_BUTTON, 7 };
        gBinds[1][PA_ITEM][0]  = (PadBind){ BIND_RAW_BUTTON, 6 };
        gBinds[1][PA_ITEM][1]  = (PadBind){ BIND_RAW_BUTTON, 4 };
        gBinds[1][PA_PAUSE][0] = (PadBind){ BIND_RAW_BUTTON, 9 };
    }
}

/* ------------------------------------------------------------------ */
/* virtual pads: one per player, fed by a raylib gamepad or a raw one   */
/* ------------------------------------------------------------------ */
typedef struct {
    bool present, raw;
    float sx, sy;                       /* steering stick incl. d-pad */
    bool down[NUM_PAD_ACTIONS], prev[NUM_PAD_ACTIONS];
    bool ok, okPrev, back, backPrev;
    int dir[2], dirPrev[2];
    char name[80];
} VPad;
static VPad vp[MAX_HUMANS];
static bool stdActive[4];               /* raylib pad ever produced input */
static int rawPresses[RAWPAD_MAX];      /* raw button presses seen */
static unsigned int rawPrevButtons[RAWPAD_MAX];
static bool prevAvail[4]; static int prevRaw = 0;
static char toast[96]; static float toastT;

static float Dz(float v) { const float dz = 0.12f; if (fabsf(v) < dz) return 0; return (v - (v > 0 ? dz : -dz))/(1 - dz); }

bool PadPlayerUsesRaw(int p) { return vp[p].raw; }
const char *PadPlayerName(int p) { return vp[p].present ? vp[p].name : NULL; }

static bool BindDownStd(int pad, PadBind b)
{
    if (b.kind == BIND_STD_BUTTON) return IsGamepadButtonDown(pad, b.code);
    if (b.kind == BIND_STD_AXIS) return GetGamepadAxisMovement(pad, b.code) > 0.3f;
    return false;
}
static bool BindDownRaw(const RawPadState *s, PadBind b)
{
    if (b.kind == BIND_RAW_BUTTON) return b.code >= 0 && b.code < 32 && (s->buttons >> b.code) & 1u;
    if (b.kind == BIND_RAW_AXIS_POS) return b.code < RAWPAD_MAX_AXES && s->axes[b.code] > 0.5f;
    if (b.kind == BIND_RAW_AXIS_NEG) return b.code < RAWPAD_MAX_AXES && s->axes[b.code] < -0.5f;
    return false;
}

/* which raylib pad / raw pad does player p use? */
static int StdPadFor(int p) { return IsGamepadAvailable(p) ? p : -1; }

/* call after LoadSettings (bindings come from the config file) */
void InputInit2(void)
{
    /* up-to-date SDL_GameControllerDB, then our extra EasySMX file (a GUID there replaces the main one) */
    const char *paths[][2] = { { "assets/gamecontrollerdb.txt", "gamecontrollerdb.txt" },
                               { "assets/gamecontrollerdb_easysmx.txt", "gamecontrollerdb_easysmx.txt" } };
    for (int f = 0; f < 2; f++)
        for (int i = 0; i < 2; i++) {
            if (!FileExists(paths[f][i])) continue;
            char *db = LoadFileText(paths[f][i]);
            if (db) {
                int r = SetGamepadMappings(db);
                gPadDbLoaded[f] = r;
                TraceLog(LOG_INFO, "INPUT: loaded %s (result %d)", paths[f][i], r);
                UnloadFileText(db);
            }
            break;
        }
}

/* --padcheck: mapping files load, the remap rules hold, and the raw fallback reads binds */
int InputSelfTest(void)
{
    int fail = 0;
    #define CHECK(c, msg) do { if (c) printf("PADCHECK ok   %s\n", msg); else { printf("PADCHECK FAIL %s\n", msg); fail++; } } while (0)
    CHECK(gPadDbLoaded[0] == 1, "main gamecontrollerdb.txt accepted");
    CHECK(gPadDbLoaded[1] == 1, "gamecontrollerdb_easysmx.txt accepted");
    PadBind saved[2][NUM_PAD_ACTIONS][2]; memcpy(saved, gBinds, sizeof saved);
    for (int set = 0; set < 2; set++) {
        InputDefaultBinds(set);
        PadBind accel = gBinds[set][PA_ACCEL][0];
        CHECK(accel.kind != BIND_NONE, set ? "raw default: accelerate bound" : "std default: accelerate bound");
        InputSetBind(set, PA_ITEM, accel);           /* move accel's button onto item */
        bool moved = gBinds[set][PA_ITEM][0].kind == accel.kind && gBinds[set][PA_ITEM][0].code == accel.code;
        bool cleared = !(gBinds[set][PA_ACCEL][0].kind == accel.kind && gBinds[set][PA_ACCEL][0].code == accel.code);
        CHECK(moved && cleared, set ? "raw remap: button moves, old action loses it" : "std remap: button moves, old action loses it");
        /* config round trip uses kind*100+code */
        for (int a = 0; a < NUM_PAD_ACTIONS; a++) for (int k = 0; k < 2; k++) {
            PadBind b = gBinds[set][a][k]; int iv = b.kind*100 + b.code;
            PadBind r = { (signed char)(iv/100), (signed char)(iv % 100) };
            if (r.kind != b.kind || r.code != b.code) { fail++; printf("PADCHECK FAIL cfg round trip set %d action %d\n", set, a); }
        }
    }
    /* raw fallback: a fake DirectInput pad pressing button 2 (A/cross) accelerates with the default layout */
    InputDefaultBinds(1);
    RawPadState rs; memset(&rs, 0, sizeof rs); rs.buttons = 1u << 2; rs.nAxes = 4;
    CHECK(BindDownRaw(&rs, gBinds[1][PA_ACCEL][0]), "raw fallback: button 3 (A/cross) = accelerate");
    rs.buttons = 0; rs.axes[3] = 0.9f;
    CHECK(BindDownRaw(&rs, (PadBind){ BIND_RAW_AXIS_POS, 3 }) && !BindDownRaw(&rs, (PadBind){ BIND_RAW_AXIS_NEG, 3 }), "raw fallback: analogue trigger axis bind");
    memcpy(gBinds, saved, sizeof saved);
    printf("PADCHECK %s (%d failures)\n", fail ? "FAILED" : "PASSED", fail);
    #undef CHECK
    return fail;
}

static void Toast(const char *s) { snprintf(toast, sizeof toast, "%s", s); toastT = 3.5f; }

void InputUpdate(float dt)
{
    RawPadPoll(GetTime());
    if (toastT > 0) toastT -= dt;
    /* hot-plug notices */
    for (int i = 0; i < 4; i++) {
        bool a = IsGamepadAvailable(i);
        if (a != prevAvail[i]) {
            Toast(TextFormat(a ? "Controller %d connected: %s" : "Controller %d disconnected", i + 1, a ? GetGamepadName(i) : ""));
            if (!a) stdActive[i] = false;
        }
        prevAvail[i] = a;
        if (a && !stdActive[i]) {
            for (int b = 1; b <= GAMEPAD_BUTTON_RIGHT_THUMB && !stdActive[i]; b++) if (IsGamepadButtonDown(i, b)) stdActive[i] = true;
            if (fabsf(GetGamepadAxisMovement(i, GAMEPAD_AXIS_LEFT_X)) > 0.5f || fabsf(GetGamepadAxisMovement(i, GAMEPAD_AXIS_LEFT_Y)) > 0.5f) stdActive[i] = true;
        }
    }
    int rc = RawPadCount();
    if (rc != prevRaw && !IsGamepadAvailable(0) && rc > prevRaw) Toast("USB controller detected (raw / DirectInput mode)");
    prevRaw = rc;

    for (int p = 0; p < MAX_HUMANS; p++) {
        VPad *v = &vp[p];
        memcpy(v->prev, v->down, sizeof v->prev);
        v->okPrev = v->ok; v->backPrev = v->back;
        v->dirPrev[0] = v->dir[0]; v->dirPrev[1] = v->dir[1];
        memset(v->down, 0, sizeof v->down);
        v->ok = v->back = false; v->sx = v->sy = 0; v->present = false;

        RawPadState rs; bool haveRaw = RawPadGet(p, &rs) != 0;
        if (haveRaw) {
            unsigned int nb = rs.buttons & ~rawPrevButtons[p];
            for (int b = 0; b < 32; b++) if ((nb >> b) & 1u) rawPresses[p]++;
            rawPrevButtons[p] = rs.buttons;
        }
        int sp = StdPadFor(p);
        /* mode: 0 auto, 1 force standard, 2 force raw */
        bool useRaw;
        if (G.settings.padMode == 2) useRaw = haveRaw;
        else if (G.settings.padMode == 1) useRaw = false;
        else useRaw = haveRaw && (sp < 0 || (!stdActive[sp] && rawPresses[p] >= 2));
        v->raw = useRaw;
        if (!useRaw && sp >= 0) {
            v->present = true;
            snprintf(v->name, sizeof v->name, "%s", GetGamepadName(sp));
            float ax = GetGamepadAxisMovement(sp, GAMEPAD_AXIS_LEFT_X), ay = GetGamepadAxisMovement(sp, GAMEPAD_AXIS_LEFT_Y);
            v->sx = Dz(ax); v->sy = Dz(ay);
            if (IsGamepadButtonDown(sp, GAMEPAD_BUTTON_LEFT_FACE_LEFT)) v->sx = -1;
            if (IsGamepadButtonDown(sp, GAMEPAD_BUTTON_LEFT_FACE_RIGHT)) v->sx = 1;
            if (IsGamepadButtonDown(sp, GAMEPAD_BUTTON_LEFT_FACE_UP)) v->sy = -1;
            if (IsGamepadButtonDown(sp, GAMEPAD_BUTTON_LEFT_FACE_DOWN)) v->sy = 1;
            for (int a = 0; a < NUM_PAD_ACTIONS; a++)
                for (int s = 0; s < 2; s++) if (BindDownStd(sp, gBinds[0][a][s])) v->down[a] = true;
            v->ok = IsGamepadButtonDown(sp, GAMEPAD_BUTTON_RIGHT_FACE_DOWN) || IsGamepadButtonDown(sp, GAMEPAD_BUTTON_MIDDLE_RIGHT);
            v->back = IsGamepadButtonDown(sp, GAMEPAD_BUTTON_RIGHT_FACE_RIGHT);
        } else if (useRaw) {
            v->present = true;
            snprintf(v->name, sizeof v->name, "%s [raw]", rs.name);
            v->sx = Dz(rs.axes[0]); v->sy = Dz(rs.axes[1]);
            if (rs.pov >= 0) {
                float r = rs.pov*DEG2RAD;
                if (sinf(r) > 0.5f) v->sx = 1; else if (sinf(r) < -0.5f) v->sx = -1;
                if (cosf(r) > 0.5f) v->sy = -1; else if (cosf(r) < -0.5f) v->sy = 1;
            }
            for (int a = 0; a < NUM_PAD_ACTIONS; a++)
                for (int s = 0; s < 2; s++) if (BindDownRaw(&rs, gBinds[1][a][s])) v->down[a] = true;
            v->ok = BindDownRaw(&rs, gBinds[1][PA_ACCEL][0]) || v->down[PA_PAUSE];
            v->back = BindDownRaw(&rs, gBinds[1][PA_BRAKE][1]) || BindDownRaw(&rs, gBinds[1][PA_BRAKE][0]);
        }
        v->dir[0] = v->sx > 0.55f ? 1 : (v->sx < -0.55f ? -1 : 0);
        v->dir[1] = v->sy > 0.55f ? 1 : (v->sy < -0.55f ? -1 : 0);
    }
}

void InputDrawToast(void)
{
    if (toastT <= 0) return;
    int w = GetScreenWidth(), h = GetScreenHeight();
    int fs = h/30 < 14 ? 14 : h/30;
    int tw = MeasureText(toast, fs);
    float a = Clamp(toastT, 0, 1);
    DrawRectangle(w/2 - tw/2 - 14, h - fs*3, tw + 28, fs + 12, Fade(BLACK, 0.7f*a));
    DrawText(toast, w/2 - tw/2, h - fs*3 + 6, fs, Fade(WHITE, a));
}

static bool VEdge(int p, int axis, int d) { return vp[p].dir[axis] == d && vp[p].dirPrev[axis] != d; }
static bool VOk(int p) { return vp[p].ok && !vp[p].okPrev; }
static bool VBack(int p) { return vp[p].back && !vp[p].backPrev; }
static bool VPause(int p) { return vp[p].down[PA_PAUSE] && !vp[p].prev[PA_PAUSE]; }
static bool AnyV(bool (*f)(int)) { for (int p = 0; p < MAX_HUMANS; p++) if (f(p)) return true; return false; }
static bool AnyEdge(int axis, int d) { for (int p = 0; p < MAX_HUMANS; p++) if (VEdge(p, axis, d)) return true; return false; }

bool MenuUp(void)    { return IsKeyPressed(KEY_UP) || IsKeyPressed(KEY_W) || AnyEdge(1, -1); }
bool MenuDown(void)  { return IsKeyPressed(KEY_DOWN) || IsKeyPressed(KEY_S) || AnyEdge(1, 1); }
bool MenuLeft(void)  { return IsKeyPressed(KEY_LEFT) || IsKeyPressed(KEY_A) || AnyEdge(0, -1); }
bool MenuRight(void) { return IsKeyPressed(KEY_RIGHT) || IsKeyPressed(KEY_D) || AnyEdge(0, 1); }
bool MenuOk(void)    { return IsKeyPressed(KEY_ENTER) || IsKeyPressed(KEY_SPACE) || IsKeyPressed(KEY_KP_ENTER) || AnyV(VOk); }
bool MenuBack(void)  { return IsKeyPressed(KEY_ESCAPE) || IsKeyPressed(KEY_BACKSPACE) || AnyV(VBack); }
bool PausePressed(void) { return IsKeyPressed(KEY_ESCAPE) || IsKeyPressed(KEY_P) || AnyV(VPause); }

static bool TwoP(void) { return G.numHumans == 2; }
bool PlayerLeft(int p)  { if (!TwoP()) return MenuLeft();  return (p == 0 ? IsKeyPressed(KEY_A) : IsKeyPressed(KEY_LEFT)) || VEdge(p, 0, -1); }
bool PlayerRight(int p) { if (!TwoP()) return MenuRight(); return (p == 0 ? IsKeyPressed(KEY_D) : IsKeyPressed(KEY_RIGHT)) || VEdge(p, 0, 1); }
bool PlayerUp(int p)    { if (!TwoP()) return MenuUp();    return (p == 0 ? IsKeyPressed(KEY_W) : IsKeyPressed(KEY_UP)) || VEdge(p, 1, -1); }
bool PlayerDown(int p)  { if (!TwoP()) return MenuDown();  return (p == 0 ? IsKeyPressed(KEY_S) : IsKeyPressed(KEY_DOWN)) || VEdge(p, 1, 1); }
bool PlayerOk(int p)    { if (!TwoP()) return MenuOk();    return (p == 0 ? (IsKeyPressed(KEY_SPACE) || IsKeyPressed(KEY_E)) : (IsKeyPressed(KEY_ENTER) || IsKeyPressed(KEY_RIGHT_CONTROL))) || VOk(p); }
bool PlayerBack(int p)  { if (!TwoP()) return MenuBack();  return (p == 0 ? (IsKeyPressed(KEY_Q) || IsKeyPressed(KEY_ESCAPE)) : IsKeyPressed(KEY_BACKSPACE)) || VBack(p); }

void InputRead(int p, KartInput *in)
{
    static bool prevHop[MAX_HUMANS], prevItem[MAX_HUMANS];
    memset(in, 0, sizeof(*in));
    bool solo = R.numHumans <= 1;
    float steer = 0;
    bool accel = false, brake = false, hop = false, item = false;
    if (solo || p == 0) {
        if (IsKeyDown(KEY_A)) steer -= 1;
        if (IsKeyDown(KEY_D)) steer += 1;
        accel |= IsKeyDown(KEY_W);
        brake |= IsKeyDown(KEY_S);
        hop |= IsKeyDown(KEY_SPACE) || IsKeyDown(KEY_LEFT_SHIFT);
        item |= IsKeyDown(KEY_E) || IsKeyDown(KEY_LEFT_CONTROL);
    }
    if (solo || p == 1) {
        if (IsKeyDown(KEY_LEFT)) steer -= 1;
        if (IsKeyDown(KEY_RIGHT)) steer += 1;
        accel |= IsKeyDown(KEY_UP);
        brake |= IsKeyDown(KEY_DOWN);
        hop |= IsKeyDown(KEY_RIGHT_SHIFT) || IsKeyDown(KEY_SLASH);
        item |= IsKeyDown(KEY_RIGHT_CONTROL) || IsKeyDown(KEY_ENTER) || IsKeyDown(KEY_PERIOD);
    }
    if (solo) {
        accel |= IsKeyDown(KEY_X);
        brake |= IsKeyDown(KEY_Z);
        hop |= IsKeyDown(KEY_C);
        item |= IsKeyDown(KEY_V);
    }
    int pads = solo ? MAX_HUMANS : 1;
    for (int q = 0; q < pads; q++) {
        VPad *v = &vp[solo ? q : p];
        if (!v->present) continue;
        steer += v->sx;
        accel |= v->down[PA_ACCEL];
        brake |= v->down[PA_BRAKE];
        hop |= v->down[PA_HOP];
        item |= v->down[PA_ITEM];
    }
    in->steer = Clamp(steer, -1, 1);
    in->accel = accel;
    in->brake = brake && !accel;
    in->back = brake;
    in->hop = hop;
    in->hopPressed = hop && !prevHop[p];
    prevHop[p] = hop;
    in->item = item;
    in->itemPressed = item && !prevItem[p];
    prevItem[p] = item;
}

/* ------------------------------------------------------------------ */
/* remapping                                                            */
/* ------------------------------------------------------------------ */
static const char *StdButtonName(int b)
{
    switch (b) {
    case GAMEPAD_BUTTON_LEFT_FACE_UP: return "D-pad Up";     case GAMEPAD_BUTTON_LEFT_FACE_RIGHT: return "D-pad Right";
    case GAMEPAD_BUTTON_LEFT_FACE_DOWN: return "D-pad Down"; case GAMEPAD_BUTTON_LEFT_FACE_LEFT: return "D-pad Left";
    case GAMEPAD_BUTTON_RIGHT_FACE_UP: return "Y";           case GAMEPAD_BUTTON_RIGHT_FACE_RIGHT: return "B";
    case GAMEPAD_BUTTON_RIGHT_FACE_DOWN: return "A";         case GAMEPAD_BUTTON_RIGHT_FACE_LEFT: return "X";
    case GAMEPAD_BUTTON_LEFT_TRIGGER_1: return "LB";         case GAMEPAD_BUTTON_LEFT_TRIGGER_2: return "LT";
    case GAMEPAD_BUTTON_RIGHT_TRIGGER_1: return "RB";        case GAMEPAD_BUTTON_RIGHT_TRIGGER_2: return "RT";
    case GAMEPAD_BUTTON_MIDDLE_LEFT: return "Back/Select";   case GAMEPAD_BUTTON_MIDDLE: return "Guide";
    case GAMEPAD_BUTTON_MIDDLE_RIGHT: return "Start";         case GAMEPAD_BUTTON_LEFT_THUMB: return "L3";
    case GAMEPAD_BUTTON_RIGHT_THUMB: return "R3";            default: return "?";
    }
}
const char *BindName(PadBind b)
{
    switch (b.kind) {
    case BIND_STD_BUTTON: return StdButtonName(b.code);
    case BIND_STD_AXIS: return b.code == GAMEPAD_AXIS_LEFT_TRIGGER ? "LT (axis)" : b.code == GAMEPAD_AXIS_RIGHT_TRIGGER ? "RT (axis)" : TextFormat("Axis %d", b.code);
    case BIND_RAW_BUTTON: return TextFormat("Button %d", b.code + 1);
    case BIND_RAW_AXIS_POS: return TextFormat("Axis %d +", b.code + 1);
    case BIND_RAW_AXIS_NEG: return TextFormat("Axis %d -", b.code + 1);
    default: return "-";
    }
}

/* capture: returns true when a new binding was detected for player 1's pad */
static float rawRest[RAWPAD_MAX_AXES]; static bool capArmed;
void InputCaptureBegin(void)
{
    RawPadState rs;
    if (RawPadGet(0, &rs)) memcpy(rawRest, rs.axes, sizeof rawRest);
    capArmed = false;
}
bool InputCapture(PadBind *out)
{
    /* wait until everything is released first */
    if (!capArmed) {
        bool any = false;
        for (int a = 0; a < NUM_PAD_ACTIONS; a++) if (vp[0].down[a]) any = true;
        if (vp[0].ok || vp[0].back) any = true;
        if (!any) capArmed = true;
        return false;
    }
    if (vp[0].raw) {
        RawPadState rs;
        if (!RawPadGet(0, &rs)) return false;
        for (int b = 0; b < 32; b++) if ((rs.buttons >> b) & 1u) { *out = (PadBind){ BIND_RAW_BUTTON, (signed char)b }; return true; }
        for (int a = 2; a < rs.nAxes && a < RAWPAD_MAX_AXES; a++) {   /* skip the steering stick */
            float d = rs.axes[a] - rawRest[a];
            if (d > 0.7f) { *out = (PadBind){ BIND_RAW_AXIS_POS, (signed char)a }; return true; }
            if (d < -0.7f) { *out = (PadBind){ BIND_RAW_AXIS_NEG, (signed char)a }; return true; }
        }
        return false;
    }
    int sp = StdPadFor(0);
    if (sp < 0) return false;
    for (int b = GAMEPAD_BUTTON_RIGHT_FACE_UP; b <= GAMEPAD_BUTTON_RIGHT_THUMB; b++)
        if (IsGamepadButtonPressed(sp, b) && b != GAMEPAD_BUTTON_LEFT_TRIGGER_2 && b != GAMEPAD_BUTTON_RIGHT_TRIGGER_2) {
            *out = (PadBind){ BIND_STD_BUTTON, (signed char)b }; return true;
        }
    if (GetGamepadAxisMovement(sp, GAMEPAD_AXIS_LEFT_TRIGGER) > 0.5f) { *out = (PadBind){ BIND_STD_AXIS, GAMEPAD_AXIS_LEFT_TRIGGER }; return true; }
    if (GetGamepadAxisMovement(sp, GAMEPAD_AXIS_RIGHT_TRIGGER) > 0.5f) { *out = (PadBind){ BIND_STD_AXIS, GAMEPAD_AXIS_RIGHT_TRIGGER }; return true; }
    return false;
}
void InputSetBind(int set, int action, PadBind b)
{
    /* remove it from any other action so one button never does two things */
    for (int a = 0; a < NUM_PAD_ACTIONS; a++) for (int s = 0; s < 2; s++)
        if (gBinds[set][a][s].kind == b.kind && gBinds[set][a][s].code == b.code) gBinds[set][a][s].kind = BIND_NONE;
    gBinds[set][action][0] = b;
    gBinds[set][action][1].kind = BIND_NONE;
}

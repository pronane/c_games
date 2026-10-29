// Gamepad layer - see pad.h
#include "pad.h"
#include "raylib.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

#ifndef EF_NO_RAW_PAD
// GLFW is part of raylib's desktop build (bundled, or the external glfw3 lib
// on MSYS2).  We only need these few joystick calls for the raw fallback.
int glfwJoystickPresent(int jid);
int glfwJoystickIsGamepad(int jid);
const float *glfwGetJoystickAxes(int jid, int *count);
const unsigned char *glfwGetJoystickButtons(int jid, int *count);
const unsigned char *glfwGetJoystickHats(int jid, int *count);
const char *glfwGetJoystickGUID(int jid);
#endif

#define STICK_DEADZONE_X 0.35f   // left/right
#define STICK_DEADZONE_Y 0.50f   // up (jump) / down (crouch): a bit larger so walking never jumps
#define REPEAT_DELAY     0.40f
#define REPEAT_RATE      0.14f

// ---------------------------------------------------------------------------
// Built-in SDL_GameControllerDB mappings (mdqinc/SDL_GameControllerDB).
// The full Windows + Linux database ships as assets/gamecontrollerdb.txt and is
// loaded too; these lines are embedded so EasySMX pads work even without it.
// ---------------------------------------------------------------------------
static const char *EMBEDDED_MAPPINGS =
    // EasySMX in DirectInput / "PC" mode (Windows)
    "03000000bc2000000091000000000000,EasySMX Controller,a:b2,b:b1,back:b8,dpdown:h0.4,dpleft:h0.8,dpright:h0.2,dpup:h0.1,leftshoulder:b4,leftstick:b10,lefttrigger:b6,leftx:a0,lefty:a1,rightshoulder:b5,rightstick:b11,righttrigger:b7,rightx:a2,righty:a3,start:b9,x:b3,y:b0,platform:Windows,\n"
    // EasySMX (Linux)
    "03000000c11100000191000011010000,EasySMX,a:b2,b:b1,back:b8,dpdown:h0.4,dpleft:h0.8,dpright:h0.2,dpup:h0.1,leftshoulder:b4,leftstick:b10,lefttrigger:b6,leftx:a0,lefty:a1,rightshoulder:b5,rightstick:b11,righttrigger:b7,rightx:a2,righty:a3,start:b9,x:b3,y:b0,platform:Linux,\n"
    "03000000242f00009100000000010000,EasySMX ESM-9101,a:b0,b:b1,back:b6,dpdown:h0.4,dpleft:h0.8,dpright:h0.2,dpup:h0.1,guide:b8,leftshoulder:b4,leftstick:b9,lefttrigger:a2,leftx:a0,lefty:a1,rightshoulder:b5,rightstick:b10,righttrigger:a5,rightx:a3,righty:a4,start:b7,x:b2,y:b3,platform:Linux,\n"
    // generic "PC/USB" pads that share the classic DirectInput layout (Windows)
    "030000008f0e00000300000000000000,PS3 Controller,a:b2,b:b1,back:b8,dpdown:h0.4,dpleft:h0.8,dpright:h0.2,dpup:h0.1,leftshoulder:b4,leftstick:b10,lefttrigger:b6,leftx:a0,lefty:a1,rightshoulder:b5,rightstick:b11,righttrigger:b7,rightx:a2,righty:a5,start:b9,x:b3,y:b0,platform:Windows,\n"
    // ShanWan: the DB line uses split-axis modifiers GLFW can't parse; simplified to lefty:a1
    "03000000632500002705000000000000,ShanWan Gamepad,a:b0,b:b1,back:b10,dpdown:h0.4,dpleft:h0.8,dpright:h0.2,dpup:h0.1,leftshoulder:b6,leftstick:b13,lefttrigger:b8,leftx:a0,lefty:a1,rightshoulder:b7,rightstick:b14,righttrigger:b9,start:b11,x:b3,y:b4,platform:Windows,\n";

static PadState pads[PAD_MAX];
static int slot[2] = { PAD_NONE, PAD_NONE };   // pad index used by player 1 / player 2
static int lostPlayer = 0;
static const char *fakeDir = NULL;              // EF_FAKEPAD_DIR test hook

static const char *BUTTON_NAMES[PB_COUNT] = {
    "A", "B", "X", "Y", "LB", "RB", "LT", "RT", "Back", "Start", "Guide", "LS", "RS",
    "DUp", "DDown", "DLeft", "DRight", "Up", "Down", "Left", "Right"
};
const char *Pad_ButtonName(PadButton b) { return (b >= 0 && b < PB_COUNT) ? BUTTON_NAMES[b] : "?"; }

static void LoadMappingFile(const char *path)
{
    if (!FileExists(path)) return;
    char *txt = LoadFileText(path);
    if (!txt) return;
    int ok = SetGamepadMappings(txt);
    TraceLog(LOG_INFO, "PAD: loaded controller mappings from %s (result %d)", path, ok);
    UnloadFileText(txt);
}

void Pad_Init(void)
{
    memset(pads, 0, sizeof(pads));
    slot[0] = slot[1] = PAD_NONE;
    LoadMappingFile("assets/gamecontrollerdb.txt");        // full SDL_GameControllerDB (Win + Linux)
    SetGamepadMappings(EMBEDDED_MAPPINGS);                 // EasySMX + generic pads
    LoadMappingFile("assets/gamecontrollerdb_user.txt");   // your own lines override everything
    fakeDir = getenv("EF_FAKEPAD_DIR");
    if (fakeDir && !fakeDir[0]) fakeDir = NULL;
    if (fakeDir) TraceLog(LOG_WARNING, "PAD: test hook active, fake pads from %s", fakeDir);
    Pad_Update();
    for (int i = 0; i < PAD_MAX; i++)
        if (pads[i].connected)
            TraceLog(LOG_INFO, "PAD %d: \"%s\" guid %s -> %s", i, pads[i].name, pads[i].guid,
                     pads[i].mapped ? "mapped (Xbox layout)" : "RAW fallback (generic DirectInput layout)");
}

// Generic DirectInput layout used by EasySMX "PC" mode, DragonRise / Twin USB /
// ShanWan and most cheap USB pads: 0=Y(Triangle) 1=B(Circle) 2=A(Cross) 3=X(Square)
// 4=LB 5=RB 6=LT 7=RT 8=Back/Select 9=Start 10=LS 11=RS, hat 0 = D-pad, axes 0/1 = left stick.
static void ApplyRawLayout(PadState *p)
{
    static const int btn[][2] = {
        { PB_Y, 0 }, { PB_B, 1 }, { PB_A, 2 }, { PB_X, 3 }, { PB_LB, 4 }, { PB_RB, 5 },
        { PB_LT, 6 }, { PB_RT, 7 }, { PB_BACK, 8 }, { PB_START, 9 }, { PB_LSTICK, 10 }, { PB_RSTICK, 11 },
        { PB_GUIDE, 12 }
    };
    for (unsigned i = 0; i < sizeof(btn) / sizeof(btn[0]); i++)
        if (btn[i][1] < p->rawButtonCount) p->down[btn[i][0]] = p->rawButtons[btn[i][1]] != 0;
    if (p->rawHatCount > 0) {
        unsigned char h = p->rawHats[0];
        p->down[PB_DPAD_UP]    = (h & 1) != 0;
        p->down[PB_DPAD_RIGHT] = (h & 2) != 0;
        p->down[PB_DPAD_DOWN]  = (h & 4) != 0;
        p->down[PB_DPAD_LEFT]  = (h & 8) != 0;
    }
    p->lx = p->rawAxisCount > 0 ? p->rawAxes[0] : 0.0f;
    p->ly = p->rawAxisCount > 1 ? p->rawAxes[1] : 0.0f;
    p->rx = p->rawAxisCount > 2 ? p->rawAxes[2] : 0.0f;
    p->ry = p->rawAxisCount > 3 ? p->rawAxes[3] : 0.0f;
    p->lt = p->down[PB_LT] ? 1.0f : 0.0f;
    p->rt = p->down[PB_RT] ? 1.0f : 0.0f;
}

static void ReadMapped(int i, PadState *p)
{
    static const int map[][2] = {
        { PB_A, GAMEPAD_BUTTON_RIGHT_FACE_DOWN }, { PB_B, GAMEPAD_BUTTON_RIGHT_FACE_RIGHT },
        { PB_X, GAMEPAD_BUTTON_RIGHT_FACE_LEFT }, { PB_Y, GAMEPAD_BUTTON_RIGHT_FACE_UP },
        { PB_LB, GAMEPAD_BUTTON_LEFT_TRIGGER_1 }, { PB_RB, GAMEPAD_BUTTON_RIGHT_TRIGGER_1 },
        { PB_LT, GAMEPAD_BUTTON_LEFT_TRIGGER_2 }, { PB_RT, GAMEPAD_BUTTON_RIGHT_TRIGGER_2 },
        { PB_BACK, GAMEPAD_BUTTON_MIDDLE_LEFT }, { PB_START, GAMEPAD_BUTTON_MIDDLE_RIGHT },
        { PB_GUIDE, GAMEPAD_BUTTON_MIDDLE }, { PB_LSTICK, GAMEPAD_BUTTON_LEFT_THUMB },
        { PB_RSTICK, GAMEPAD_BUTTON_RIGHT_THUMB },
        { PB_DPAD_UP, GAMEPAD_BUTTON_LEFT_FACE_UP }, { PB_DPAD_DOWN, GAMEPAD_BUTTON_LEFT_FACE_DOWN },
        { PB_DPAD_LEFT, GAMEPAD_BUTTON_LEFT_FACE_LEFT }, { PB_DPAD_RIGHT, GAMEPAD_BUTTON_LEFT_FACE_RIGHT },
    };
    for (unsigned k = 0; k < sizeof(map) / sizeof(map[0]); k++)
        p->down[map[k][0]] = IsGamepadButtonDown(i, map[k][1]);
    int axes = GetGamepadAxisCount(i);
    p->lx = axes > 0 ? GetGamepadAxisMovement(i, GAMEPAD_AXIS_LEFT_X) : 0.0f;
    p->ly = axes > 1 ? GetGamepadAxisMovement(i, GAMEPAD_AXIS_LEFT_Y) : 0.0f;
    p->rx = axes > 2 ? GetGamepadAxisMovement(i, GAMEPAD_AXIS_RIGHT_X) : 0.0f;
    p->ry = axes > 3 ? GetGamepadAxisMovement(i, GAMEPAD_AXIS_RIGHT_Y) : 0.0f;
    p->lt = axes > 4 ? (GetGamepadAxisMovement(i, GAMEPAD_AXIS_LEFT_TRIGGER) + 1.0f) * 0.5f : 0.0f;
    p->rt = axes > 5 ? (GetGamepadAxisMovement(i, GAMEPAD_AXIS_RIGHT_TRIGGER) + 1.0f) * 0.5f : 0.0f;
}

#ifndef EF_NO_RAW_PAD
static void ReadRaw(int i, PadState *p)
{
    int n = 0;
    const unsigned char *b = glfwGetJoystickButtons(i, &n);
    if (!b) n = 0;
    if (n > 32) n = 32;
    p->rawButtonCount = n;
    for (int k = 0; k < n; k++) p->rawButtons[k] = b[k];
    n = 0;
    const float *a = glfwGetJoystickAxes(i, &n);
    if (!a) n = 0;
    if (n > 16) n = 16;
    p->rawAxisCount = n;
    for (int k = 0; k < n; k++) p->rawAxes[k] = a[k];
    n = 0;
    const unsigned char *h = glfwGetJoystickHats(i, &n);
    if (!h) n = 0;
    if (n > 4) n = 4;
    p->rawHatCount = n;
    for (int k = 0; k < n; k++) p->rawHats[k] = h[k];
}
#endif

// small reentrant tokenizer (strtok_r is not portable to MinGW -std=c99)
static char *NextTok(char **s, const char *delims)
{
    char *p = *s;
    if (!p) return NULL;
    p += strspn(p, delims);
    if (!*p) { *s = NULL; return NULL; }
    char *e = p + strcspn(p, delims);
    if (*e) { *e = 0; *s = e + 1; } else *s = NULL;
    return p;
}

// ---- test hook: EF_FAKEPAD_DIR/padN files ------------------------------------
//   mapped name=Xbox_360_Controller down=A,X lx=0 ly=0
//   raw    name=EasySMX_PC_mode buttons=2,9 axes=0,0 hat=1
// (file missing = pad unplugged).  Raw fakes go through the same fallback layout.
static bool ReadFake(int i, PadState *p)
{
    char path[512];
    snprintf(path, sizeof(path), "%s/pad%d", fakeDir, i);
    FILE *f = fopen(path, "r");
    if (!f) return false;
    char line[512] = { 0 };
    if (!fgets(line, sizeof(line), f)) line[0] = 0;
    fclose(f);
    p->connected = true; p->fake = true;
    p->mapped = strncmp(line, "raw", 3) != 0;
    strcpy(p->guid, "fake");
    snprintf(p->name, sizeof(p->name), "%s", p->mapped ? "Fake Xbox pad" : "Fake DirectInput pad");
    char *save = line;
    for (char *tok = NextTok(&save, " \t\r\n"); tok; tok = NextTok(&save, " \t\r\n")) {
        char *eq = strchr(tok, '=');
        if (!eq) continue;
        *eq = 0;
        const char *key = tok, *val = eq + 1;
        if (!strcmp(key, "name")) {
            snprintf(p->name, sizeof(p->name), "%s", val);
            for (char *c = p->name; *c; c++) if (*c == '_') *c = ' ';
        } else if (!strcmp(key, "down")) {
            char buf[256]; snprintf(buf, sizeof(buf), "%s", val);
            char *s2 = buf;
            for (char *b = NextTok(&s2, ","); b; b = NextTok(&s2, ","))
                for (int k = 0; k < PB_UP; k++) if (!strcmp(b, BUTTON_NAMES[k])) p->down[k] = true;
        } else if (!strcmp(key, "buttons")) {
            char buf[256]; snprintf(buf, sizeof(buf), "%s", val);
            char *s2 = buf;
            p->rawButtonCount = 13;
            for (char *b = NextTok(&s2, ","); b; b = NextTok(&s2, ",")) {
                int k = atoi(b);
                if (k >= 0 && k < 32) { p->rawButtons[k] = 1; if (k >= p->rawButtonCount) p->rawButtonCount = k + 1; }
            }
        } else if (!strcmp(key, "axes")) {
            char buf[256]; snprintf(buf, sizeof(buf), "%s", val);
            char *s2 = buf; int k = 0;
            for (char *b = NextTok(&s2, ","); b && k < 16; b = NextTok(&s2, ",")) p->rawAxes[k++] = (float)atof(b);
            p->rawAxisCount = k;
        } else if (!strcmp(key, "hat")) {
            p->rawHatCount = 1; p->rawHats[0] = (unsigned char)atoi(val);
        } else if (!strcmp(key, "lx")) p->lx = (float)atof(val);
        else if (!strcmp(key, "ly")) p->ly = (float)atof(val);
    }
    if (!p->mapped) { if (p->rawHatCount == 0) p->rawHatCount = 1; ApplyRawLayout(p); }
    return true;
}

void Pad_Update(void)
{
    float dt = GetFrameTime();
    lostPlayer = 0;
    for (int i = 0; i < PAD_MAX; i++) {
        PadState *p = &pads[i];
        bool wasConnected = p->connected;
        memcpy(p->prev, p->down, sizeof(p->down));
        memset(p->down, 0, sizeof(p->down));
        p->lx = p->ly = p->rx = p->ry = p->lt = p->rt = 0.0f;
        p->rawButtonCount = p->rawAxisCount = p->rawHatCount = 0;
        memset(p->rawButtons, 0, sizeof(p->rawButtons));
        memset(p->rawAxes, 0, sizeof(p->rawAxes));
        memset(p->rawHats, 0, sizeof(p->rawHats));
        p->connected = false; p->fake = false;

        if (fakeDir && ReadFake(i, p)) {
            // fake pad state filled in
        } else if (IsGamepadAvailable(i)) {
            p->connected = true;
            const char *nm = GetGamepadName(i);
            snprintf(p->name, sizeof(p->name), "%s", (nm && nm[0]) ? nm : "Unknown controller");
#ifndef EF_NO_RAW_PAD
            const char *guid = glfwGetJoystickGUID(i);
            snprintf(p->guid, sizeof(p->guid), "%s", guid ? guid : "?");
            p->mapped = glfwJoystickIsGamepad(i) != 0;
            ReadRaw(i, p);
#else
            strcpy(p->guid, "?");
            p->mapped = true;
#endif
            if (p->mapped) ReadMapped(i, p);
            else ApplyRawLayout(p);
        } else {
            p->name[0] = 0; p->guid[0] = 0; p->mapped = false;
        }

        if (p->connected) {
            // virtual directions = D-pad OR left stick
            p->down[PB_LEFT]  = p->down[PB_DPAD_LEFT]  || p->lx < -STICK_DEADZONE_X;
            p->down[PB_RIGHT] = p->down[PB_DPAD_RIGHT] || p->lx >  STICK_DEADZONE_X;
            p->down[PB_UP]    = p->down[PB_DPAD_UP]    || p->ly < -STICK_DEADZONE_Y;
            p->down[PB_DOWN]  = p->down[PB_DPAD_DOWN]  || p->ly >  STICK_DEADZONE_Y;
        }
        if (!wasConnected && p->connected) {
            memset(p->prev, 0, sizeof(p->prev));
            TraceLog(LOG_INFO, "PAD %d connected: \"%s\" (%s)", i, p->name, p->mapped ? "mapped" : "raw fallback");
        }
        if (wasConnected && !p->connected) {
            memset(p->prev, 0, sizeof(p->prev));
            TraceLog(LOG_INFO, "PAD %d disconnected", i);
        }
        for (int k = 0; k < PB_COUNT; k++) p->hold[k] = p->down[k] ? p->hold[k] + dt : 0.0f;
    }

    // sticky player slots: pad 0 -> P1, pad 1 -> P2; a re-plugged pad fills the free slot
    for (int s = 0; s < 2; s++)
        if (slot[s] != PAD_NONE && !pads[slot[s]].connected) { slot[s] = PAD_NONE; lostPlayer = s + 1; }
    for (int i = 0; i < PAD_MAX; i++) {
        if (!pads[i].connected || slot[0] == i || slot[1] == i) continue;
        if (slot[0] == PAD_NONE) slot[0] = i;
        else if (slot[1] == PAD_NONE) slot[1] = i;
    }
}

const PadState *Pad_Get(int pad) { return (pad >= 0 && pad < PAD_MAX) ? &pads[pad] : NULL; }
int Pad_ForPlayer(int player) { return (player == 1 || player == 2) ? slot[player - 1] : PAD_NONE; }
int Pad_LostPlayer(void) { return lostPlayer; }

int Pad_ConnectedCount(void)
{
    int n = 0;
    for (int i = 0; i < PAD_MAX; i++) if (pads[i].connected) n++;
    return n;
}

static bool Check(int sel, PadButton b, int kind)
{
    if (b < 0 || b >= PB_COUNT) return false;
    int from = sel, to = sel;
    if (sel == PAD_ANY) { from = 0; to = PAD_MAX - 1; }
    else if (sel < 0 || sel >= PAD_MAX) return false;
    for (int i = from; i <= to; i++) {
        const PadState *p = &pads[i];
        if (!p->connected) continue;
        if (kind == 0 && p->down[b]) return true;
        if (kind >= 1 && p->down[b] && !p->prev[b]) return true;
        if (kind == 2 && p->down[b] && p->hold[b] > REPEAT_DELAY &&
            fmodf(p->hold[b] - REPEAT_DELAY, REPEAT_RATE) < GetFrameTime()) return true;
    }
    return false;
}
bool Pad_Down(int sel, PadButton b)    { return Check(sel, b, 0); }
bool Pad_Pressed(int sel, PadButton b) { return Check(sel, b, 1); }
bool Pad_Repeat(int sel, PadButton b)  { return Check(sel, b, 2); }

const char *Pad_Describe(int sel)
{
    static char buf[2][200];
    static int which = 0;
    which ^= 1;
    char *out = buf[which];
    if (sel == PAD_ANY) {
        int n = 0, first = -1;
        for (int i = 0; i < PAD_MAX; i++) if (pads[i].connected) { if (first < 0) first = i; n++; }
        if (n == 0) snprintf(out, 200, "no controller");
        else if (n == 1) snprintf(out, 200, "%.60s (pad %d)", pads[first].name, first);
        else snprintf(out, 200, "%.48s (pad %d) + %d more", pads[first].name, first, n - 1);
    } else if (sel >= 0 && sel < PAD_MAX && pads[sel].connected) {
        snprintf(out, 200, "%.60s (pad %d)", pads[sel].name, sel);
    } else snprintf(out, 200, "no controller");
    return out;
}

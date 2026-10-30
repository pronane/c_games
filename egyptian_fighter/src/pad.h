#ifndef PAD_H
#define PAD_H
// ---------------------------------------------------------------------------
//  Gamepad layer: USB / XInput / DirectInput pads (Xbox, EasySMX, generic USB)
//
//  * Mapped pads (XInput, or anything with an SDL_GameControllerDB mapping)
//    are read through raylib's gamepad API (Xbox layout).
//  * Pads that are connected but have NO mapping (cheap DirectInput pads) are
//    read raw through GLFW with a generic "PC / DirectInput" layout, so they
//    still work.  Build with -DEF_NO_RAW_PAD to disable that path.
//  * Hot-plug safe: everything is re-checked every frame.
// ---------------------------------------------------------------------------
#include <stdbool.h>

#define PAD_MAX      4      // raylib MAX_GAMEPADS
#define PAD_ANY      100    // "any connected pad" selector (CPU modes)
#define PAD_NONE     (-1)

typedef enum {
    PB_A = 0, PB_B, PB_X, PB_Y,          // Xbox face buttons (Cross, Circle, Square, Triangle)
    PB_LB, PB_RB, PB_LT, PB_RT,
    PB_BACK, PB_START, PB_GUIDE, PB_LSTICK, PB_RSTICK,
    PB_DPAD_UP, PB_DPAD_DOWN, PB_DPAD_LEFT, PB_DPAD_RIGHT,
    PB_UP, PB_DOWN, PB_LEFT, PB_RIGHT,   // virtual: D-pad OR left stick
    PB_COUNT
} PadButton;

typedef struct {
    bool connected;
    bool mapped;          // true = Xbox layout via mapping, false = raw fallback
    bool fake;            // injected by the test hook
    char name[128];
    char guid[40];
    bool down[PB_COUNT];
    bool prev[PB_COUNT];
    float hold[PB_COUNT]; // seconds held (menu auto-repeat)
    float lx, ly, rx, ry, lt, rt;
    int rawButtonCount, rawAxisCount, rawHatCount;
    unsigned char rawButtons[32];
    float rawAxes[16];
    unsigned char rawHats[4];
} PadState;

void Pad_Init(void);                     // after InitWindow(): loads controller mappings
void Pad_Update(void);                   // once per frame (even while paused)

const PadState *Pad_Get(int pad);        // pad 0..3 (NULL if out of range)
int  Pad_ForPlayer(int player);          // 1 or 2 -> pad index or PAD_NONE (sticky slots)
int  Pad_ConnectedCount(void);
const char *Pad_ButtonName(PadButton b);

// sel: 0..3 = that pad, PAD_ANY = any connected pad, PAD_NONE = nothing
bool Pad_Down(int sel, PadButton b);
bool Pad_Pressed(int sel, PadButton b);
bool Pad_Repeat(int sel, PadButton b);   // pressed + auto-repeat while held (menus)

// set when a pad that belonged to a player slot was unplugged this frame (1 or 2), else 0
int  Pad_LostPlayer(void);
const char *Pad_Describe(int sel);       // "EasySMX ... (pad 0)" / "no controller"

#endif

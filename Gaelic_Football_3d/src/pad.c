/*  pad.c - gamepad support. #included from main.c.
 *
 *  Works with XInput pads (EasySMX in X-mode, Xbox, etc.) and with DirectInput
 *  pads (EasySMX in D-mode/PC mode, generic USB pads) through the bundled SDL
 *  assets/input/gamecontrollerdb.txt, loaded with SetGamepadMappings() at start.
 *  A joystick that is present but still has no mapping is read raw with the
 *  common DirectInput layout (the EasySMX D-mode one) so it still plays.
 *  All four slots are scanned every frame; the first connected pad is used.
 *  The keyboard keeps working; the two are merged every frame.
 *
 *  Left stick  move              Right stick  camera orbit / zoom
 *  A           hand pass         B            solo / bounce (auto picks legal one)
 *  X (hold)    kick, hold = power   Y         shoot (auto power, low when close)
 *  R1          sprint            R2           power kick / two-point attempt
 *  L1          switch player     L2           tackle / shoulder
 *  L2 + Y      hook / head hit (special - a straight RED card)
 *  Without the ball: A = toe-lift pick-up, X = jump to field a high ball.
 *  Start       pause / skip intro / confirm    Back   controller test screen
 *  D-pad       menu navigation, d-pad up/down cycles cameras in play
 */
#define PAD_DEADZONE 0.22f
#define PAD_BTNS 18                 /* raylib GamepadButton enum 0..17 */

/* GLFW joystick API (inside libraylib.a for static builds, glfw3.dll for MSYS2):
 * used only to read pads that have no mapping and to show raw values. */
int glfwJoystickPresent(int jid);
int glfwJoystickIsGamepad(int jid);
const char *glfwGetJoystickName(int jid);
const char *glfwGetJoystickGUID(int jid);
const float *glfwGetJoystickAxes(int jid, int *count);
const unsigned char *glfwGetJoystickButtons(int jid, int *count);
const unsigned char *glfwGetJoystickHats(int jid, int *count);

typedef struct {
    int id;                          /* slot 0-3, -1 = none */
    int mapped;                      /* 1 = SDL/GLFW mapping, 0 = raw fallback layout */
    int simulated;                   /* scripted input for screenshots/tests */
    char name[96], guid[40];
    float axis[6];                   /* LX LY RX RY LT RT (raw, triggers -1..1) */
    int axisLive[4];                 /* v3.2: a stick axis counts once it has been seen centred */
    unsigned char btn[PAD_BTNS], prev[PAD_BTNS];
    int nRawAxes, nRawBtns, nRawHats;
    float rawAxes[16];
    unsigned char rawBtns[32], rawHats[4];
} PadState;

static PadState pad = { .id = -1 };
static int padId = -1;               /* mirror of pad.id for older code */
static float camOrbit = 0.0f, camZoom = 1.0f;
static int padMappingsLoaded = 0;

static void padLoadMappings(void)
{
    const char *paths[] = { "assets/input/gamecontrollerdb.txt", "gamecontrollerdb.txt" };
    for (int i = 0; i < 2; i++) {
        if (!FileExists(paths[i])) continue;
        char *db = LoadFileText(paths[i]);
        if (!db) continue;
        int r = SetGamepadMappings(db);
        UnloadFileText(db);
        padMappingsLoaded = r > 0 ? 1 : -1;
        TraceLog(LOG_INFO, "GAME: gamepad mappings %s (%s)", r > 0 ? "loaded" : "FAILED", paths[i]);
        return;
    }
    TraceLog(LOG_WARNING, "GAME: gamecontrollerdb.txt not found");
}

/* Fill pad.btn/axis for this frame. Call once per frame. */
static void padUpdate(void)
{
    memcpy(pad.prev, pad.btn, sizeof pad.btn);
    if (pad.simulated) { padId = pad.id; return; }    /* the script writes btn/axis itself */
    int id = -1;
    if (pad.id >= 0 && glfwJoystickPresent(pad.id)) id = pad.id;
    for (int i = 0; i < 4 && id < 0; i++) if (glfwJoystickPresent(i)) id = i;
    if (id != pad.id) {
        pad.id = id;
        memset(pad.prev, 0, sizeof pad.prev);
        memset(pad.axisLive, 0, sizeof pad.axisLive);
        if (id >= 0) {
            const char *n = glfwGetJoystickName(id), *g = glfwGetJoystickGUID(id);
            snprintf(pad.name, sizeof pad.name, "%s", n ? n : "Gamepad");
            snprintf(pad.guid, sizeof pad.guid, "%s", g ? g : "?");
            TraceLog(LOG_INFO, "GAME: gamepad slot %d: %s [%s] %s", id, pad.name, pad.guid,
                     glfwJoystickIsGamepad(id) ? "mapped" : "NO MAPPING - using generic DirectInput layout");
        }
    }
    padId = id;
    memset(pad.btn, 0, sizeof pad.btn);
    memset(pad.axis, 0, sizeof pad.axis);
    pad.axis[4] = pad.axis[5] = -1.0f;
    pad.nRawAxes = pad.nRawBtns = pad.nRawHats = 0;
    if (id < 0) return;

    const float *ra = glfwGetJoystickAxes(id, &pad.nRawAxes);
    const unsigned char *rb = glfwGetJoystickButtons(id, &pad.nRawBtns);
    const unsigned char *rh = glfwGetJoystickHats(id, &pad.nRawHats);
    if (pad.nRawAxes > 16) pad.nRawAxes = 16;
    if (pad.nRawBtns > 32) pad.nRawBtns = 32;
    if (pad.nRawHats > 4) pad.nRawHats = 4;
    if (ra) memcpy(pad.rawAxes, ra, sizeof(float) * pad.nRawAxes);
    if (rb) memcpy(pad.rawBtns, rb, pad.nRawBtns);
    if (rh) memcpy(pad.rawHats, rh, pad.nRawHats);

    pad.mapped = glfwJoystickIsGamepad(id);
    if (pad.mapped) {
        for (int b = 1; b < PAD_BTNS; b++) pad.btn[b] = IsGamepadButtonDown(id, b);
        for (int a = 0; a < 6; a++) pad.axis[a] = GetGamepadAxisMovement(id, a);
    } else {
        /* generic DirectInput layout (EasySMX D-mode / most USB pads):
         * b0 Y, b1 B, b2 A, b3 X, b4 L1, b5 R1, b6 L2, b7 R2, b8 Back, b9 Start, b10 L3, b11 R3,
         * a0/a1 left stick, a2/a3 right stick, hat 0 = d-pad */
        static const int map[12] = { GAMEPAD_BUTTON_RIGHT_FACE_UP, GAMEPAD_BUTTON_RIGHT_FACE_RIGHT, GAMEPAD_BUTTON_RIGHT_FACE_DOWN,
            GAMEPAD_BUTTON_RIGHT_FACE_LEFT, GAMEPAD_BUTTON_LEFT_TRIGGER_1, GAMEPAD_BUTTON_RIGHT_TRIGGER_1, GAMEPAD_BUTTON_LEFT_TRIGGER_2,
            GAMEPAD_BUTTON_RIGHT_TRIGGER_2, GAMEPAD_BUTTON_MIDDLE_LEFT, GAMEPAD_BUTTON_MIDDLE_RIGHT, GAMEPAD_BUTTON_LEFT_THUMB, GAMEPAD_BUTTON_RIGHT_THUMB };
        for (int i = 0; i < 12 && i < pad.nRawBtns; i++) if (rb[i]) pad.btn[map[i]] = 1;
        for (int a = 0; a < 4 && a < pad.nRawAxes; a++) pad.axis[a] = ra[a];
        if (pad.nRawHats > 0) {
            unsigned char h = rh[0];
            if (h & 1) pad.btn[GAMEPAD_BUTTON_LEFT_FACE_UP] = 1;
            if (h & 2) pad.btn[GAMEPAD_BUTTON_LEFT_FACE_RIGHT] = 1;
            if (h & 4) pad.btn[GAMEPAD_BUTTON_LEFT_FACE_DOWN] = 1;
            if (h & 8) pad.btn[GAMEPAD_BUTTON_LEFT_FACE_LEFT] = 1;
        }
        pad.axis[4] = pad.btn[GAMEPAD_BUTTON_LEFT_TRIGGER_2] ? 1.0f : -1.0f;
        pad.axis[5] = pad.btn[GAMEPAD_BUTTON_RIGHT_TRIGGER_2] ? 1.0f : -1.0f;
    }
    /* v3.2: a 'stick' axis that rests at the end stop (a trigger or throttle on
     * some DirectInput pads) used to drag the camera zoom/orbit to its limit -
     * ignore each stick axis until it has been seen near the centre once. */
    for (int a = 0; a < 4; a++) {
        if (!pad.axisLive[a] && fabsf(pad.axis[a]) < 0.4f) pad.axisLive[a] = 1;
        if (!pad.axisLive[a]) pad.axis[a] = 0.0f;
    }
    /* triggers may be axes only: an axis above 0.5 counts as the button */
    if (pad.axis[GAMEPAD_AXIS_LEFT_TRIGGER] > 0.5f) pad.btn[GAMEPAD_BUTTON_LEFT_TRIGGER_2] = 1;
    if (pad.axis[GAMEPAD_AXIS_RIGHT_TRIGGER] > 0.5f) pad.btn[GAMEPAD_BUTTON_RIGHT_TRIGGER_2] = 1;
}



static float padAxis(int axis)
{
    if (padId < 0) return 0.0f;
    float v = pad.axis[axis];
    if (axis <= GAMEPAD_AXIS_RIGHT_Y) {               /* radial deadzone per stick */
        int ox = axis & ~1, oy = ox + 1;
        float x = pad.axis[ox], y = pad.axis[oy], m = sqrtf(x * x + y * y);
        if (m < PAD_DEADZONE) return 0.0f;
        float k = fminf(1.0f, (m - PAD_DEADZONE) / (1.0f - PAD_DEADZONE)) / m;
        return v * k;
    }
    return v;
}

static int padDown(int b) { return padId >= 0 && pad.btn[b]; }
static int padPressed(int b) { return padId >= 0 && pad.btn[b] && !pad.prev[b]; }
static int padReleased(int b) { return padId >= 0 && !pad.btn[b] && pad.prev[b]; }


static int padAnyConfirm(void)
{
    return padPressed(GAMEPAD_BUTTON_MIDDLE_RIGHT) || padPressed(GAMEPAD_BUTTON_RIGHT_FACE_DOWN);
}

static const char *padStatusText(void)
{
    static char buf[200];
    if (padId < 0) return "No controller detected - plug in a pad (XInput or DirectInput)";
    snprintf(buf, sizeof buf, "Controller: %s%s", pad.name, pad.simulated ? " (simulated)" : pad.mapped ? "" : "  [no mapping - generic layout]");
    return buf;
}

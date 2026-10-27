/* padraw.c : raw joystick access used as a fallback for pads that the
 * SDL-style gamepad database does not recognise (e.g. EasySMX or other
 * generic USB pads in DirectInput / "D-input" mode).
 *  - Windows: the classic winmm joystick API (works for DirectInput and
 *    XInput devices, no extra libraries: we already link -lwinmm)
 *  - Linux:   /dev/input/js*
 * This file deliberately does NOT include raylib.h (windows.h clashes). */
#include "padraw.h"
#include <string.h>
#include <stdio.h>

typedef struct {
    int present;
    int id;
    char name[64];
    int nAxes, nButtons;
    float axes[RAWPAD_MAX_AXES];
    unsigned int buttons;
    int pov;            /* -1 centred, else degrees */
#ifdef _WIN32
    unsigned int amin[6], amax[6];
#else
    int fd;
#endif
} RawPad;

static RawPad pads[RAWPAD_MAX];
static int padCount;
static double lastScan = -100;

#ifdef _WIN32
#include <windows.h>
#include <mmsystem.h>

static void Scan(void)
{
    RawPad old[RAWPAD_MAX];
    memcpy(old, pads, sizeof old);
    padCount = 0;
    memset(pads, 0, sizeof pads);
    UINT n = joyGetNumDevs();
    if (n > 16) n = 16;
    for (UINT id = 0; id < n && padCount < RAWPAD_MAX; id++) {
        JOYINFOEX ji; memset(&ji, 0, sizeof ji);
        ji.dwSize = sizeof ji; ji.dwFlags = JOY_RETURNALL;
        if (joyGetPosEx(id, &ji) != JOYERR_NOERROR) continue;
        JOYCAPSA caps; memset(&caps, 0, sizeof caps);
        if (joyGetDevCapsA(id, &caps, sizeof caps) != JOYERR_NOERROR) continue;
        RawPad *p = &pads[padCount++];
        p->present = 1; p->id = (int)id;
        snprintf(p->name, sizeof p->name, "%s", caps.szPname[0] ? caps.szPname : "USB gamepad");
        p->nAxes = (int)caps.wNumAxes; if (p->nAxes > 6) p->nAxes = 6; if (p->nAxes < 2) p->nAxes = 2;
        p->nButtons = (int)caps.wNumButtons; if (p->nButtons > 32) p->nButtons = 32;
        unsigned int mn[6] = { caps.wXmin, caps.wYmin, caps.wZmin, caps.wRmin, caps.wUmin, caps.wVmin };
        unsigned int mx[6] = { caps.wXmax, caps.wYmax, caps.wZmax, caps.wRmax, caps.wUmax, caps.wVmax };
        for (int a = 0; a < 6; a++) { p->amin[a] = mn[a]; p->amax[a] = mx[a] > mn[a] ? mx[a] : mn[a] + 65535; }
    }
    (void)old;
}

static void Read(RawPad *p)
{
    JOYINFOEX ji; memset(&ji, 0, sizeof ji);
    ji.dwSize = sizeof ji; ji.dwFlags = JOY_RETURNALL;
    if (joyGetPosEx((UINT)p->id, &ji) != JOYERR_NOERROR) { p->present = 0; return; }
    DWORD raw[6] = { ji.dwXpos, ji.dwYpos, ji.dwZpos, ji.dwRpos, ji.dwUpos, ji.dwVpos };
    for (int a = 0; a < 6; a++) {
        float r = (float)(p->amax[a] - p->amin[a]);
        p->axes[a] = r > 0 ? (((float)raw[a] - (float)p->amin[a])/r)*2.0f - 1.0f : 0.0f;
    }
    p->buttons = (unsigned int)ji.dwButtons;
    p->pov = (ji.dwPOV == 0xFFFF || ji.dwPOV == JOY_POVCENTERED) ? -1 : (int)(ji.dwPOV/100);
}
#elif defined(__linux__)
#include <fcntl.h>
#include <unistd.h>
#include <linux/joystick.h>
#include <sys/ioctl.h>
#include <errno.h>
static int errno_is_gone(void) { return errno == ENODEV; }

static int openFds[RAWPAD_MAX] = { -1, -1, -1, -1 };

static void Scan(void)
{
    /* keep already-open devices, look for new ones */
    for (int i = 0; i < RAWPAD_MAX; i++) {
        if (openFds[i] >= 0) continue;
        char path[32]; snprintf(path, sizeof path, "/dev/input/js%d", i);
        int fd = open(path, O_RDONLY | O_NONBLOCK);
        if (fd < 0) continue;
        openFds[i] = fd;
        RawPad *p = &pads[i];
        memset(p, 0, sizeof *p);
        p->present = 1; p->id = i; p->fd = fd; p->pov = -1;
        char nm[64] = "USB gamepad"; ioctl(fd, JSIOCGNAME(sizeof nm), nm); nm[63] = 0;
        snprintf(p->name, sizeof p->name, "%s", nm);
        unsigned char na = 2, nb = 12; ioctl(fd, JSIOCGAXES, &na); ioctl(fd, JSIOCGBUTTONS, &nb);
        p->nAxes = na > RAWPAD_MAX_AXES ? RAWPAD_MAX_AXES : na; p->nButtons = nb > 32 ? 32 : nb;
    }
    padCount = 0;
    for (int i = 0; i < RAWPAD_MAX; i++) if (pads[i].present) padCount = i + 1;
}

static void Read(RawPad *p)
{
    struct js_event e;
    for (;;) {
        ssize_t r = read(p->fd, &e, sizeof e);
        if (r != (ssize_t)sizeof e) {
            if (r < 0 && errno_is_gone()) { close(p->fd); openFds[p->id] = -1; p->present = 0; }
            break;
        }
        int t = e.type & ~JS_EVENT_INIT;
        if (t == JS_EVENT_BUTTON && e.number < 32) {
            if (e.value) p->buttons |= 1u << e.number; else p->buttons &= ~(1u << e.number);
        } else if (t == JS_EVENT_AXIS && e.number < RAWPAD_MAX_AXES) {
            p->axes[e.number] = e.value/32767.0f;
        }
    }
}
#else
static void Scan(void) { padCount = 0; }
static void Read(RawPad *p) { (void)p; }
#endif

void RawPadPoll(double now)
{
    if (now - lastScan > 2.0) { lastScan = now; Scan(); }
    for (int i = 0; i < padCount; i++) if (pads[i].present) Read(&pads[i]);
}

int RawPadCount(void)
{
    int c = 0;
    for (int i = 0; i < padCount; i++) if (pads[i].present) c++;
    return c;
}

/* n-th present pad */
static RawPad *Nth(int n)
{
    for (int i = 0; i < padCount; i++) if (pads[i].present) { if (n == 0) return &pads[i]; n--; }
    return NULL;
}

int RawPadGet(int n, RawPadState *out)
{
    RawPad *p = Nth(n);
    memset(out, 0, sizeof *out);
    out->pov = -1;
    if (!p) return 0;
    memcpy(out->axes, p->axes, sizeof out->axes);
    out->nAxes = p->nAxes; out->nButtons = p->nButtons;
    out->buttons = p->buttons; out->pov = p->pov;
    snprintf(out->name, sizeof out->name, "%s", p->name);
    return 1;
}

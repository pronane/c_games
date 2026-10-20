#ifndef PADRAW_H
#define PADRAW_H
#define RAWPAD_MAX 4
#define RAWPAD_MAX_AXES 8
typedef struct {
    float axes[RAWPAD_MAX_AXES];   /* -1..1 */
    int nAxes, nButtons;
    unsigned int buttons;          /* bit i = button i */
    int pov;                       /* hat in degrees, -1 = centred */
    char name[64];
} RawPadState;
void RawPadPoll(double now);
int RawPadCount(void);
int RawPadGet(int n, RawPadState *out);
#endif

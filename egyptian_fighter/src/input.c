// input.c - sampling layer: raylib keyboard + pads -> InputBits.  Nothing here is simulation.
#include "input.h"
#include "game.h"
#include "pad.h"

InputBits Input_KeysP1(void) {
    InputBits b = 0;
    if (IsKeyDown(KEY_A) || IsKeyDown(KEY_LEFT))  b |= IN_LEFT;
    if (IsKeyDown(KEY_D) || IsKeyDown(KEY_RIGHT)) b |= IN_RIGHT;
    if (IsKeyDown(KEY_S) || IsKeyDown(KEY_DOWN))  b |= IN_DOWN;
    if (IsKeyDown(KEY_W) || IsKeyDown(KEY_UP))    b |= IN_UP;
    if (IsKeyDown(KEY_L))     b |= IN_BLOCK;
    if (IsKeyPressed(KEY_J))  b |= IN_PUNCH;
    if (IsKeyPressed(KEY_K))  b |= IN_KICK;
    if (IsKeyPressed(KEY_U))  b |= IN_SP1;
    if (IsKeyPressed(KEY_I))  b |= IN_SP2;
    if (IsKeyPressed(KEY_O))  b |= IN_THROW;
    if (IsKeyPressed(KEY_P))  b |= IN_TAUNT;
    if (IsKeyPressed(KEY_J) || IsKeyPressed(KEY_K)) b |= IN_JATK;
    return b;
}

InputBits Input_KeysP2(void) {
    InputBits b = 0;
    if (IsKeyDown(KEY_LEFT))  b |= IN_LEFT;
    if (IsKeyDown(KEY_RIGHT)) b |= IN_RIGHT;
    if (IsKeyDown(KEY_DOWN))  b |= IN_DOWN;
    if (IsKeyDown(KEY_UP))    b |= IN_UP;
    if (IsKeyDown(KEY_KP_3) || IsKeyDown(KEY_B))       b |= IN_BLOCK;
    if (IsKeyPressed(KEY_KP_1) || IsKeyPressed(KEY_Z)) b |= IN_PUNCH;
    if (IsKeyPressed(KEY_KP_2) || IsKeyPressed(KEY_X)) b |= IN_KICK;
    if (IsKeyPressed(KEY_KP_4) || IsKeyPressed(KEY_C)) b |= IN_SP1;
    if (IsKeyPressed(KEY_KP_5) || IsKeyPressed(KEY_V)) b |= IN_SP2;
    if (IsKeyPressed(KEY_KP_6) || IsKeyPressed(KEY_N)) b |= IN_THROW;
    if (IsKeyPressed(KEY_KP_7) || IsKeyPressed(KEY_M)) b |= IN_TAUNT;
    if (IsKeyPressed(KEY_KP_1) || IsKeyPressed(KEY_KP_2) ||
        IsKeyPressed(KEY_Z) || IsKeyPressed(KEY_X))    b |= IN_JATK;
    return b;
}

// Gamepad, OR-ed on top of the keyboard.  sel = pad index or PAD_ANY.
//   D-pad / left stick = move, up = jump, down = crouch   A = jump
//   X = punch  Y = kick  B or LT = special 1  RT = special 2
//   RB = block (hold)  LB = throw  Back/Select = taunt  (Start = pause, handled in main.c)
InputBits Input_Pad(int sel, bool ignoreA) {
    if (sel == PAD_NONE) return 0;
    InputBits b = 0;
    bool aHeld = Pad_Down(sel, PB_A) && !ignoreA;
    if (Pad_Down(sel, PB_LEFT))  b |= IN_LEFT;
    if (Pad_Down(sel, PB_RIGHT)) b |= IN_RIGHT;
    if (Pad_Down(sel, PB_DOWN))  b |= IN_DOWN;
    if (Pad_Down(sel, PB_UP) || aHeld) b |= IN_UP;
    if (Pad_Down(sel, PB_RB))    b |= IN_BLOCK;
    if (Pad_Pressed(sel, PB_X))  b |= IN_PUNCH;
    if (Pad_Pressed(sel, PB_Y))  b |= IN_KICK;
    if (Pad_Pressed(sel, PB_B) || Pad_Pressed(sel, PB_LT)) b |= IN_SP1;
    if (Pad_Pressed(sel, PB_RT)) b |= IN_SP2;
    if (Pad_Pressed(sel, PB_LB)) b |= IN_THROW;
    if (Pad_Pressed(sel, PB_BACK)) b |= IN_TAUNT;
    if (Pad_Pressed(sel, PB_X) || Pad_Pressed(sel, PB_Y)) b |= IN_JATK;
    return b;
}

static InputBits Confirm(void) {
    return (IsKeyPressed(KEY_ENTER) || IsKeyPressed(KEY_KP_ENTER) || IsKeyPressed(KEY_SPACE) ||
            Pad_Pressed(PAD_ANY, PB_A) || Pad_Pressed(PAD_ANY, PB_START)) ? IN_CONFIRM : 0;
}

void Input_SampleFight(Game *g, InputBits out[2]) {
    if (g->screen == SCREEN_FIGHT && g->padWaitRelease &&
        !Pad_Down(PAD_ANY, PB_A) && !Pad_Down(PAD_ANY, PB_START))
        g->padWaitRelease = false;
    bool w = g->padWaitRelease;
    out[0] = out[1] = 0;
    if (g->mode == MODE_1P_VS_CPU) {
        out[0] = Input_KeysP1() | Input_Pad(PAD_ANY, w);
    } else if (g->mode == MODE_CPU_VS_1P) {
        // the human is on the right: accept the P1 keys (WASD...) and the P2 keys
        out[1] = Input_KeysP1() | Input_KeysP2() | Input_Pad(PAD_ANY, w);
    } else {
        out[0] = Input_KeysP1() | Input_Pad(Pad_ForPlayer(1), w);
        out[1] = Input_KeysP2() | Input_Pad(Pad_ForPlayer(2), w);
    }
    out[0] |= Confirm();     // either side may skip the face-off; the sim ORs both
}

void Input_ToPlayer(Player *p, InputBits b) {
    p->inputLeft       = (b & IN_LEFT)  != 0;
    p->inputRight      = (b & IN_RIGHT) != 0;
    p->inputDown       = (b & IN_DOWN)  != 0;
    p->inputUp         = (b & IN_UP)    != 0;
    p->inputBlock      = (b & IN_BLOCK) != 0;
    p->inputPunch      = (b & IN_PUNCH) != 0;
    p->inputKick       = (b & IN_KICK)  != 0;
    p->inputSpecial1   = (b & IN_SP1)   != 0;
    p->inputSpecial2   = (b & IN_SP2)   != 0;
    p->inputThrow      = (b & IN_THROW) != 0;
    p->inputTaunt      = (b & IN_TAUNT) != 0;
    p->inputJumpAttack = (b & IN_JATK)  != 0;
}

InputBits Input_FromPlayer(const Player *p) {
    InputBits b = 0;
    if (p->inputLeft)       b |= IN_LEFT;
    if (p->inputRight)      b |= IN_RIGHT;
    if (p->inputDown)       b |= IN_DOWN;
    if (p->inputUp)         b |= IN_UP;
    if (p->inputBlock)      b |= IN_BLOCK;
    if (p->inputPunch)      b |= IN_PUNCH;
    if (p->inputKick)       b |= IN_KICK;
    if (p->inputSpecial1)   b |= IN_SP1;
    if (p->inputSpecial2)   b |= IN_SP2;
    if (p->inputThrow)      b |= IN_THROW;
    if (p->inputTaunt)      b |= IN_TAUNT;
    if (p->inputJumpAttack) b |= IN_JATK;
    return b;
}

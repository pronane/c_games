// input.h - per-player fight input as a 16-bit mask (the only thing lockstep netplay sends).
//
// The fight simulation never reads raylib / the keyboard / pads directly.  Each 1/60 s tick it
// receives one InputBits per player.  Bits 0-4 are "held" buttons; bits 5-12 are "pressed this
// tick" events (edge-detected by the sampling layer, exactly like raylib IsKeyPressed /
// Pad_Pressed did before, so local play behaves identically).
#ifndef EF_INPUT_H
#define EF_INPUT_H

#include <stdint.h>
#include "player.h"

typedef uint16_t InputBits;

enum {
    // held
    IN_LEFT    = 1 << 0,
    IN_RIGHT   = 1 << 1,
    IN_DOWN    = 1 << 2,
    IN_UP      = 1 << 3,     // jump (keys, d-pad up / stick up, pad A)
    IN_BLOCK   = 1 << 4,
    // pressed this tick
    IN_PUNCH   = 1 << 5,
    IN_KICK    = 1 << 6,
    IN_SP1     = 1 << 7,
    IN_SP2     = 1 << 8,
    IN_THROW   = 1 << 9,
    IN_TAUNT   = 1 << 10,
    IN_JATK    = 1 << 11,    // jump attack (punch or kick pressed; the CPU sets it on its own)
    IN_CONFIRM = 1 << 12,    // Enter / Space / pad A / Start: skips the pre-fight face-off
};
#define IN_HELD_MASK  ((InputBits)0x001F)
#define IN_PRESS_MASK ((InputBits)0x1FE0)

struct Game;

// Sampling layer (outside the sim): keyboard + USB / EasySMX pads -> bits for both fighters,
// for the current mode.  A CPU-controlled slot gets 0 (the sim drives it).  Also drops a pad A
// still held from the select screen (Game.padWaitRelease, a local-input filter - not sim state).
void Input_SampleFight(struct Game *g, InputBits out[2]);

InputBits Input_KeysP1(void);                 // WASD/arrows + J K U I L O P
InputBits Input_KeysP2(void);                 // arrows + numpad / Z X C V B N M
InputBits Input_Pad(int sel, bool ignoreA);   // one pad or PAD_ANY

// bits <-> the Player's input flags (what player.c consumes)
void      Input_ToPlayer(Player *p, InputBits b);
InputBits Input_FromPlayer(const Player *p);

#endif

#ifndef ONLINE_H
#define ONLINE_H
// Online versus over the shared c_games relay (shared/netplay). The fight runs in
// lockstep: both machines step Game_FightStep at a fixed 1/60 s with the same inputs.
#include "game.h"
#include "../../shared/netplay/c/netplay.h"

void Online_Configure(int argc, char **argv);   // --server ws(s)://host/egyptian, EF_SERVER, netplay.cfg
void Online_Enter(Game *g);          // switch to the online menu (connects in the background)
void Online_Poll(Game *g);           // once per frame, also while paused / loading
bool Online_Active(void);
int  Online_MySlot(void);            // 0 = left fighter, 1 = right fighter, -1 = not in a room

void Online_MenuUpdate(Game *g);     // SCREEN_ONLINE
void Online_SelectUpdate(Game *g);   // SCREEN_SELECT with MODE_ONLINE
void Online_FightUpdate(Game *g);    // SCREEN_PREFIGHT / SCREEN_FIGHT with MODE_ONLINE
void Online_DrawMenu(const Game *g);
void Online_DrawStatus(const Game *g);
void Online_Shutdown(void);
void Online_AutoStart(Game *g);      // test hook: EF_ONLINE=quick|create|join:CODE

#endif

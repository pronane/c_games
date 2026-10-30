/* ONLINE VS over the shared c_games relay (online.c, shared/netplay). */
#ifndef TT64_ONLINE_H
#define TT64_ONLINE_H
#include <stdbool.h>

void OnlineConfigure(int argc, char **argv);   /* --server ws(s)://host/turbo, TT_SERVER, netplay.cfg */
void OnlineAutoStart(void);                    /* test hook: TT_ONLINE=quick|create|join:CODE */
void OnlineEnter(void);                        /* mode menu -> online menu */
void OnlinePoll(float dt);                     /* once per frame */
bool OnlineActive(void);
void OnlineMenuUpdate(void);                   /* SCR_ONLINE */
void OnlineDraw(void);
void OnlineSubmitPick(void);                   /* racer + track chosen: pick and ready */
void OnlineRaceSteps(void);                    /* lockstep RaceUpdate while racing */
bool OnlineRaceOver(void);
void OnlineDrawRaceStatus(void);
void OnlineBackToLobby(void);
void OnlineShutdown(void);

#endif

#include "game.h"

#include <raylib.h>

void GameInit(void)
{
}

void GameUpdate(float delta_time)
{
    (void)delta_time;
}

void GameDraw(void)
{
    ClearBackground((Color){ 24, 28, 36, 255 });
    DrawText("New Raylib Game", 40, 40, 32, RAYWHITE);
    DrawText("Replace this prototype with your original game.", 40, 88, 20, LIGHTGRAY);
}

void GameShutdown(void)
{
}

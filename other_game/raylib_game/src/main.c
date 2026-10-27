#include "game.h"

#include <raylib.h>

int main(void)
{
    InitWindow(1280, 720, "New Raylib Game");
    SetTargetFPS(60);

    GameInit();

    while (!WindowShouldClose()) {
        GameUpdate(GetFrameTime());

        BeginDrawing();
        GameDraw();
        EndDrawing();
    }

    GameShutdown();
    CloseWindow();
    return 0;
}

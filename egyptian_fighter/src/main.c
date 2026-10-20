#include "game.h"

int main(void)
{
    SetConfigFlags(FLAG_MSAA_4X_HINT | FLAG_VSYNC_HINT);

    InitWindow(SCREEN_WIDTH, SCREEN_HEIGHT, "Egyptian Fighter - Character Select + Versus");
    SetTargetFPS(TARGET_FPS);
    SetExitKey(KEY_NULL); // we handle ESC ourselves

    Game game;
    Game_Init(&game);

    // Important note printed once at startup
    TraceLog(LOG_INFO, "=================================================");
    TraceLog(LOG_INFO, " Egyptian Fighter");
    TraceLog(LOG_INFO, " Missing PNG files will show colored placeholders");
    TraceLog(LOG_INFO, " and print WARNING messages here in the console.");
    TraceLog(LOG_INFO, " The game will still run perfectly without them.");
    TraceLog(LOG_INFO, "=================================================");

    while (!WindowShouldClose())
    {
        // Pause only during fight
        if (IsKeyPressed(KEY_ESCAPE) && game.screen == SCREEN_FIGHT) {
            game.paused = !game.paused;
        }

        if (!game.paused) {
            Game_Update(&game);
        }

        BeginDrawing();
            ClearBackground(BLACK);
            Game_Draw(&game);

            if (game.paused) {
                DrawRectangle(0, 0, SCREEN_WIDTH, SCREEN_HEIGHT, (Color){0,0,0,150});
                const char *pauseMsg = "PAUSED - Press ESC to resume";
                int pw = MeasureText(pauseMsg, 30);
                DrawText(pauseMsg, SCREEN_WIDTH/2 - pw/2, SCREEN_HEIGHT/2 - 15, 30, WHITE);
            }
        EndDrawing();
    }

    Game_Unload(&game);
    CloseWindow();
    return 0;
}

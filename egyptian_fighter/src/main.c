#include "game.h"
#include "pad.h"

int RunDemo(int charIndex, const char *outDir);   // demo.c

int main(int argc, char **argv)
{
    // Test mode: egyptian_fighter --demo <charIndex 0-6> [outDir]
    if (argc >= 3 && strcmp(argv[1], "--demo") == 0) {
        InitWindow(SCREEN_WIDTH, SCREEN_HEIGHT, "Egyptian Fighter - animation demo");
        SetTargetFPS(argc >= 4 ? 0 : TARGET_FPS);
        int r = RunDemo(atoi(argv[2]), argc >= 4 ? argv[3] : NULL);
        CloseWindow();
        return r;
    }

    // 4x MSAA, vsync, resizable window.  The game is laid out in 1280x720 but drawn at the
    // window's real resolution (gfx.c), so a 1080p / 4K TV gets a native-resolution picture.
    SetConfigFlags(FLAG_MSAA_4X_HINT | FLAG_VSYNC_HINT | FLAG_WINDOW_RESIZABLE);

    InitWindow(SCREEN_WIDTH, SCREEN_HEIGHT, "Egyptian Fighter - Character Select + Versus");
    SetWindowMinSize(640, 360);
    SetTargetFPS(TARGET_FPS);
    SetExitKey(KEY_NULL); // we handle ESC ourselves
    Gfx_ApplyStartupWindowMode(argc, argv);   // --fullscreen / --windowed / settings.cfg
    Gfx_LoadFonts();

    Pad_Init();            // controller mappings (EasySMX, generic USB pads) - after InitWindow

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
        Pad_Update();          // hot-plug safe: re-checks every pad each frame

        // a controller that belonged to a player was unplugged mid-fight -> pause
        int lost = Pad_LostPlayer();
        if (lost && game.screen == SCREEN_FIGHT) {
            game.paused = true;
            snprintf(game.pauseNote, sizeof(game.pauseNote),
                     "Controller for P%d disconnected - plug it back in (or use the keyboard)", lost);
        }

        // Pause only during fight: ESC or Start on any controller
        if (game.screen == SCREEN_FIGHT && (IsKeyPressed(KEY_ESCAPE) || Pad_Pressed(PAD_ANY, PB_START))) {
            game.paused = !game.paused;
            if (!game.paused) game.pauseNote[0] = 0;
        }

        // F11 or Alt+Enter = borderless fullscreen at the display's native resolution
        bool toggled = Gfx_HandleFullscreenKeys();

        if (!game.paused && !toggled) {      // (the Enter of Alt+Enter is not a menu press)
            Game_Update(&game);
        }

        BeginDrawing();
            ClearBackground(BLACK);           // letterbox bars
            Gfx_BeginView();
            Game_Draw(&game);

            if (game.paused) {
                DrawRectangle(0, 0, SCREEN_WIDTH, SCREEN_HEIGHT, (Color){0,0,0,150});
                const char *pauseMsg = "PAUSED - Press ESC or Start to resume";
                int pw = MeasureText(pauseMsg, 30);
                DrawText(pauseMsg, SCREEN_WIDTH/2 - pw/2, SCREEN_HEIGHT/2 - 15, 30, WHITE);
                if (game.pauseNote[0]) {
                    int nw = MeasureText(game.pauseNote, 22);
                    DrawText(game.pauseNote, SCREEN_WIDTH/2 - nw/2, SCREEN_HEIGHT/2 + 30, 22, ORANGE);
                }
            }
            Gfx_EndView();
        EndDrawing();
    }

    Game_Unload(&game);
    Gfx_UnloadFonts();
    CloseWindow();
    return 0;
}

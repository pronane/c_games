#include "game.h"
#include "pad.h"
#include "sim.h"
#include "online.h"

int RunDemo(int charIndex, const char *outDir);   // demo.c

int main(int argc, char **argv)
{
    // Headless determinism tools (no window):  --sim-test   |   --replay <file.efrec>
    if (argc >= 2 && strcmp(argv[1], "--sim-test") == 0) {
        SetTraceLogLevel(LOG_WARNING);
        return Sim_RunTests(argc, argv);
    }
    if (argc >= 3 && strcmp(argv[1], "--replay") == 0) {
        SetTraceLogLevel(LOG_WARNING);
        return Sim_Replay(argv[2], true);
    }
    // --record <file>: write every fight's per-tick inputs + checkpoint hashes (file, file.2, ...)
    SimRecorder recorder;
    Rec_Init(&recorder, "");
    for (int i = 1; i + 1 < argc; i++) if (strcmp(argv[i], "--record") == 0) Rec_Init(&recorder, argv[i + 1]);

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
    Online_Configure(argc, argv);   // server for the ONLINE mode: --server / EF_SERVER / netplay.cfg
    Online_AutoStart(&game);

    // Important note printed once at startup
    TraceLog(LOG_INFO, "=================================================");
    TraceLog(LOG_INFO, " Egyptian Fighter");
    TraceLog(LOG_INFO, " Missing PNG files will show colored placeholders");
    TraceLog(LOG_INFO, " and print WARNING messages here in the console.");
    TraceLog(LOG_INFO, " The game will still run perfectly without them.");
    TraceLog(LOG_INFO, "=================================================");

    double simAccum = 0.0;                 // unsimulated time (seconds), < 1 tick normally
    InputBits pendingPress[2] = { 0, 0 };  // "pressed" bits waiting for the next tick

    while (!WindowShouldClose())
    {
        Pad_Update();          // hot-plug safe: re-checks every pad each frame
        Online_Poll(&game);    // online mode: server messages (an online fight never pauses)
        bool online = game.mode == MODE_ONLINE;

        // a controller that belonged to a player was unplugged mid-fight -> pause
        int lost = Pad_LostPlayer();
        if (lost && game.screen == SCREEN_FIGHT && !online) {
            game.paused = true;
            snprintf(game.pauseNote, sizeof(game.pauseNote),
                     "Controller for P%d disconnected - plug it back in (or use the keyboard)", lost);
        }

        // Pause only during fight: ESC or Start on any controller
        if (game.screen == SCREEN_FIGHT && !online && (IsKeyPressed(KEY_ESCAPE) || Pad_Pressed(PAD_ANY, PB_START))) {
            game.paused = !game.paused;
            if (!game.paused) game.pauseNote[0] = 0;
        }

        // F11 or Alt+Enter = borderless fullscreen at the display's native resolution
        bool toggled = Gfx_HandleFullscreenKeys();

        bool onlineFight = online && (game.screen == SCREEN_PREFIGHT || game.screen == SCREEN_FIGHT ||
                                      game.screen == SCREEN_RESULT);
        if (onlineFight) {
            // lockstep: ticks run when both players' inputs are in (online.c), never paused
            Online_FightUpdate(&game);
            if (!toggled) Game_Update(&game);
            simAccum = 0.0;
            pendingPress[0] = pendingPress[1] = 0;
        } else if (!game.paused && !toggled) {      // (the Enter of Alt+Enter is not a menu press)
            // 1) sample keyboard + pads into one 16-bit mask per fighter (input.c)
            InputBits in[2];
            Input_SampleFight(&game, in);
            pendingPress[0] |= in[0] & IN_PRESS_MASK;   // a tap is never lost on a 0-tick frame
            pendingPress[1] |= in[1] & IN_PRESS_MASK;

            // 2) fixed 1/60 s simulation steps (accumulator, sim.c)
            int steps = Sim_StepsForFrame(&simAccum, GetFrameTime());
            for (int i = 0; i < steps; i++) {
                InputBits tick[2] = { (InputBits)((in[0] & IN_HELD_MASK) | pendingPress[0]),
                                      (InputBits)((in[1] & IN_HELD_MASK) | pendingPress[1]) };
                pendingPress[0] = pendingPress[1] = 0;      // presses go to the first tick only
                Game_SimTick(&game, tick);
                Rec_Tick(&recorder, &game, tick);
            }

            // 3) menus (select screen, leaving the result screen) - once per rendered frame
            Game_Update(&game);
            if (recorder.path[0]) {
                if (!recorder.active && game.screen == SCREEN_PREFIGHT && game.simTick == 0)
                    Rec_FightStart(&recorder, &game);
                else if (recorder.active && game.screen == SCREEN_SELECT)
                    Rec_FightEnd(&recorder, &game);
            }
        } else {
            // paused or fullscreen toggled: the simulation simply does not step; no time
            // is banked and no tap carries over, so pausing can never change a fight
            simAccum = 0.0;
            pendingPress[0] = pendingPress[1] = 0;
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

    Rec_FightEnd(&recorder, &game);
    Online_Shutdown();
    Game_Unload(&game);
    Gfx_UnloadFonts();
    CloseWindow();
    return 0;
}

/*
 * Tiny player for game_character.json.
 *   example <character_dir> [--shots preview.png] [--seconds 0.4]
 * --shots draws the current move (idle if the manifest has it) and exits.
 * That is what the headless check runs under Xvfb.
 *
 * Keys, if you run it in a window: LEFT/RIGHT change move, SPACE pauses nothing,
 * ESC quits. Feet sit on the red line.
 */
#define GAME_CHARACTER_IMPLEMENTATION
#include "game_character.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define W 640
#define H 480

static void shot(const char *path) {
    Image img = LoadImageFromScreen();
    ExportImage(img, path);
    UnloadImage(img);
}

int main(int argc, char **argv) {
    const char *dir = NULL;
    const char *shots = NULL;
    float seconds = 0.35f;
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--shots") && i + 1 < argc) shots = argv[++i];
        else if (!strcmp(argv[i], "--seconds") && i + 1 < argc) seconds = (float)atof(argv[++i]);
        else if (!dir) dir = argv[i];
    }
    if (!dir) {
        fprintf(stderr, "usage: example <character_dir> [--shots preview.png] [--seconds 0.4]\n");
        return 2;
    }
    SetConfigFlags(FLAG_MSAA_4X_HINT);
    InitWindow(W, H, "Sprite Forge game character");
    SetTargetFPS(60);
    GC_Character hero;
    if (!GC_Load(&hero, dir)) {
        fprintf(stderr, "could not load %s/game_character.json\n", dir);
        CloseWindow();
        return 1;
    }
    int idle = GC_Find(&hero, "idle");
    if (idle < 0) idle = 0;
    GC_Play(&hero, idle);
    /* step a fixed clock so a headless run does not depend on the real frame time */
    int ticks = (int)(seconds * 60.0f);
    if (ticks < 1) ticks = 1;
    for (int i = 0; i < ticks; i++) GC_Update(&hero, 1.0f / 60.0f);

    float groundY = H - 48.0f;
    BeginDrawing();
    ClearBackground((Color){28, 30, 38, 255});
    DrawRectangle(0, (int)groundY, W, H - (int)groundY, (Color){52, 58, 70, 255});
    DrawLineEx((Vector2){0, groundY}, (Vector2){W, groundY}, 2, RED);
    float scale = 2.0f;
    if (hero.anims[hero.playing].h > 0)
        scale = 280.0f / (float)hero.anims[hero.playing].h;
    GC_Draw(&hero, W * 0.5f, groundY, false, scale);
    const GC_Anim *a = &hero.anims[hero.playing];
    DrawText(TextFormat("%s / %s  frame %d/%d  %s  pack %s",
                        hero.name, a->name, GC_Frame(&hero) + 1, a->frames,
                        a->loop ? "loop" : "once", hero.pack[0] ? hero.pack : "-"),
             16, 16, 20, RAYWHITE);
    DrawText(TextFormat("source %s   camera %s", a->source, hero.camera), 16, 42, 18, LIGHTGRAY);
    if (GC_HitActive(&hero)) DrawText("HIT", 16, 70, 22, RED);
    if (GC_Footstep(&hero)) DrawText("STEP", 80, 70, 22, SKYBLUE);
    EndDrawing();

    if (shots) {
        shot(shots);
        printf("shot %s  move %s frame %d events hit %d..%d ball %d\n",
               shots, a->name, GC_Frame(&hero), a->ev.hit_start, a->ev.hit_end, a->ev.ball_contact);
        GC_Unload(&hero);
        CloseWindow();
        return 0;
    }
    while (!WindowShouldClose()) {
        float dt = GetFrameTime();
        if (IsKeyPressed(KEY_RIGHT)) GC_Play(&hero, (hero.playing + 1) % hero.anim_count);
        if (IsKeyPressed(KEY_LEFT)) GC_Play(&hero, (hero.playing + hero.anim_count - 1) % hero.anim_count);
        GC_Update(&hero, dt);
        BeginDrawing();
        ClearBackground((Color){28, 30, 38, 255});
        DrawRectangle(0, (int)groundY, W, H - (int)groundY, (Color){52, 58, 70, 255});
        DrawLineEx((Vector2){0, groundY}, (Vector2){W, groundY}, 2, RED);
        GC_Draw(&hero, W * 0.5f, groundY, false, scale);
        DrawText(TextFormat("%s / %s   LEFT RIGHT change move   ESC quit", hero.name, hero.anims[hero.playing].name),
                 16, 16, 20, RAYWHITE);
        EndDrawing();
    }
    GC_Unload(&hero);
    CloseWindow();
    return 0;
}

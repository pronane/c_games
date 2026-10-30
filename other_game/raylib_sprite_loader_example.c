/*
 * Raylib Sprite / Atlas Loader – companion to Console Asset Pipeline
 * -----------------------------------------------------------------
 * Loads the master PNG + JSON produced by console_asset_pipeline.py
 * and plays any animation state by name.
 *
 * Build (example):
 *   gcc raylib_sprite_loader_example.c -lraylib -lm -o sprite_player
 *
 * Dependencies: raylib + a tiny JSON parser (cJSON recommended) or
 * the hard-coded fallback shown below for zero-extra-deps testing.
 */

#include "raylib.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define MAX_ACTIONS   32
#define MAX_FRAMES    16

typedef struct {
    int x, y, w, h;
} FrameBounds;

typedef struct {
    char name[48];
    FrameBounds frames[MAX_FRAMES];
    int frameCount;
} AnimationState;

/* ---------- Minimal hard-coded fallback (matches Python SNES demo) ---------- */
void LoadHardcodedDemo(AnimationState *anims, int *count)
{
    /* Row 0 – idle */
    strcpy(anims[0].name, "idle");
    anims[0].frameCount = 4;
    for (int i = 0; i < 4; i++)
        anims[0].frames[i] = (FrameBounds){ i * 64, 0 * 64, 64, 64 };

    /* Row 1 – walk */
    strcpy(anims[1].name, "walk");
    anims[1].frameCount = 4;
    for (int i = 0; i < 4; i++)
        anims[1].frames[i] = (FrameBounds){ i * 64, 1 * 64, 64, 64 };

    /* Row 2 – run */
    strcpy(anims[2].name, "run");
    anims[2].frameCount = 4;
    for (int i = 0; i < 4; i++)
        anims[2].frames[i] = (FrameBounds){ i * 64, 2 * 64, 64, 64 };

    /* Row 3 – punch */
    strcpy(anims[3].name, "punch");
    anims[3].frameCount = 4;
    for (int i = 0; i < 4; i++)
        anims[3].frames[i] = (FrameBounds){ i * 64, 3 * 64, 64, 64 };

    *count = 4;
}

int main(void)
{
    const int screenWidth  = 960;
    const int screenHeight = 640;
    InitWindow(screenWidth, screenHeight, "Console Asset Pipeline – Runtime Player");

    /* Change this path to the PNG your Python tool just wrote */
    Texture2D sheet = LoadTexture("pipeline_output/hero_character_snes___genesis_sheet.png");
    if (sheet.id == 0) {
        /* Fallback for first-run testing */
        TraceLog(LOG_WARNING, "Sheet not found – using blank texture. Generate assets first.");
    }

    AnimationState animations[MAX_ACTIONS];
    int animCount = 0;
    LoadHardcodedDemo(animations, &animCount);

    int currentAnim  = 1;   /* start on walk */
    int currentFrame = 0;
    float timer      = 0.0f;
    float frameTime  = 0.12f;

    SetTargetFPS(60);

    while (!WindowShouldClose())
    {
        timer += GetFrameTime();
        if (timer >= frameTime) {
            timer = 0.0f;
            currentFrame = (currentFrame + 1) % animations[currentAnim].frameCount;
        }

        /* Hotkeys 1-4 switch states */
        if (IsKeyPressed(KEY_ONE))   currentAnim = 0;
        if (IsKeyPressed(KEY_TWO))   currentAnim = 1;
        if (IsKeyPressed(KEY_THREE)) currentAnim = 2;
        if (IsKeyPressed(KEY_FOUR))  currentAnim = 3;

        FrameBounds b = animations[currentAnim].frames[currentFrame];
        Rectangle src = { (float)b.x, (float)b.y, (float)b.w, (float)b.h };
        Rectangle dst = { screenWidth/2.0f - 128, screenHeight/2.0f - 128, 256, 256 };

        BeginDrawing();
            ClearBackground((Color){30, 30, 40, 255});

            DrawText("CONSOLE ASSET PIPELINE  –  RUNTIME", 20, 20, 22, RAYWHITE);
            DrawText("1 = Idle   2 = Walk   3 = Run   4 = Punch", 20, 50, 16, LIGHTGRAY);
            DrawText(TextFormat("State: %s   Frame: %d",
                     animations[currentAnim].name, currentFrame), 20, 80, 18, SKYBLUE);

            if (sheet.id != 0)
                DrawTexturePro(sheet, src, dst, (Vector2){0,0}, 0.0f, WHITE);
            else
                DrawRectangleRec(dst, DARKGRAY);

            DrawRectangleLinesEx(dst, 2, YELLOW);
        EndDrawing();
    }

    UnloadTexture(sheet);
    CloseWindow();
    return 0;
}

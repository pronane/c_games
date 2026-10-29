/* Sprite Forge Studio v7 - raylib viewer for the separate animation files written by
 *     python forge.py anim-export ...      or      python forge.py build ... --anim-export
 *
 *   anim_viewer <anim_dir> [move ...] [--screenshot out.png] [--frames N] [--scale S]
 *
 * Loads <anim_dir>/character_base.glb with LoadModel() and every <anim_dir>/anim_<move>.glb with
 * LoadModelAnimations(), checks IsModelAnimationValid() and plays the moves one after another (SPACE / RIGHT = next).
 * Builds against raylib 5.5 and 6.0 (MSYS2 UCRT64 on Windows, gcc on Linux) - see Makefile / build.bat.
 */
#include "raylib.h"
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

#if defined(RAYLIB_VERSION_MAJOR) && (RAYLIB_VERSION_MAJOR >= 6)
  #define ANIM_FRAMES(a) ((a).keyframeCount)
  #define ANIM_UPDATE(m, a, f) UpdateModelAnimation((m), (a), (float)(f))
  #define MODEL_BONES(m) ((m).skeleton.boneCount)
#else
  #define MODEL_BONES(m) ((m).boneCount)
  #define ANIM_FRAMES(a) ((a).frameCount)
  #define ANIM_UPDATE(m, a, f) UpdateModelAnimation((m), (a), (f))
#endif

#define MAXMOVES 64

int main(int argc, char **argv)
{
    const char *dir = "anim";
    const char *shot = NULL;
    const char *moves[MAXMOVES]; int nm = 0;
    int maxFrames = 0; float scale = 1.0f;
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--screenshot") && i + 1 < argc) shot = argv[++i];
        else if (!strcmp(argv[i], "--frames") && i + 1 < argc) maxFrames = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--scale") && i + 1 < argc) scale = (float)atof(argv[++i]);
        else if (i == 1) dir = argv[i];
        else if (nm < MAXMOVES) moves[nm++] = argv[i];
    }
    if (nm == 0) { moves[nm++] = "idle"; moves[nm++] = "walk"; }

    SetConfigFlags(FLAG_MSAA_4X_HINT);
    InitWindow(800, 600, "Sprite Forge v7 - separate animation files in raylib " RAYLIB_VERSION);
    SetTargetFPS(60);

    Model model = LoadModel(TextFormat("%s/character_base.glb", dir));
    printf("SFS base: meshes=%d materials=%d bones=%d\n", model.meshCount, model.materialCount, MODEL_BONES(model));

    ModelAnimation *anims[MAXMOVES] = {0}; int counts[MAXMOVES] = {0}; int ok = 0;
    for (int i = 0; i < nm; i++) {
        anims[i] = LoadModelAnimations(TextFormat("%s/anim_%s.glb", dir, moves[i]), &counts[i]);
        int valid = (counts[i] > 0) && IsModelAnimationValid(model, anims[i][0]);
        printf("SFS anim %s: clips=%d frames=%d bones=%d valid=%d\n", moves[i], counts[i],
               counts[i] ? ANIM_FRAMES(anims[i][0]) : 0, counts[i] ? anims[i][0].boneCount : 0, valid);
        ok += valid;
    }

    Camera3D cam = { 0 };
    cam.position = (Vector3){ 2.2f, 1.5f, 3.2f };
    cam.target = (Vector3){ 0.0f, 0.9f, 0.0f };
    cam.up = (Vector3){ 0.0f, 1.0f, 0.0f };
    cam.fovy = 40.0f; cam.projection = CAMERA_PERSPECTIVE;

    int cur = 0, frame = 0, n = 0;
    while (!WindowShouldClose()) {
        if (IsKeyPressed(KEY_SPACE) || IsKeyPressed(KEY_RIGHT)) { cur = (cur + 1) % nm; frame = 0; }
        if (counts[cur] > 0) {
            int fc = ANIM_FRAMES(anims[cur][0]);
            if (fc > 0) { frame = (frame + 1) % fc; ANIM_UPDATE(model, anims[cur][0], frame); }
        }
        BeginDrawing();
        ClearBackground((Color){ 40, 44, 52, 255 });
        BeginMode3D(cam);
        DrawGrid(10, 0.5f);
        DrawModel(model, (Vector3){ 0, 0, 0 }, scale, WHITE);
        EndMode3D();
        DrawText(TextFormat("move: %s  frame %d   (%d/%d anim files valid)", moves[cur], frame, ok, nm), 10, 10, 20, RAYWHITE);
        DrawText("SPACE = next move", 10, 36, 16, LIGHTGRAY);
        EndDrawing();
        n++;
        if (maxFrames && n == maxFrames) {
            if (shot) TakeScreenshot(shot);
            break;
        }
        if (maxFrames && n == maxFrames / 2 && nm > 1) { cur = (cur + 1) % nm; frame = 0; }
    }
    for (int i = 0; i < nm; i++) if (counts[i]) UnloadModelAnimations(anims[i], counts[i]);
    UnloadModel(model);
    CloseWindow();
    return ok == nm ? 0 : 2;
}

// Dev tool: renders every clip of a GLB as a strip of 6 poses (3/4 view) into clipview_N.png
#include "raylib.h"
#include "raymath.h"
#include <stdio.h>
#include <stdlib.h>
int main(int argc, char **argv)
{
    const char *path = argc > 1 ? argv[1] : "assets/models/gaelic_player.glb";
    int rowsPer = 4, cols = argc > 2 ? atoi(argv[2]) : 7;
    SetConfigFlags(FLAG_WINDOW_HIDDEN);
    InitWindow(1400, 1100, "clipview");
    Model m = LoadModel(path);
    int n = 0; ModelAnimation *a = LoadModelAnimations(path, &n);
    Camera3D cam = { 0 };
    Vector3 dir = Vector3Normalize((Vector3){ 1.0f, 0.35f, 0.6f });
    cam.target = (Vector3){ 0, 0, 0 }; cam.position = Vector3Scale(dir, 50); cam.up = (Vector3){ 0, 1, 0 };
    cam.fovy = 2.75f * rowsPer; cam.projection = CAMERA_ORTHOGRAPHIC;
    Vector3 right = Vector3Normalize(Vector3CrossProduct((Vector3){0,1,0}, dir)); right = Vector3Negate(right);
    Vector3 up = Vector3Normalize(Vector3CrossProduct(dir, right)); up = Vector3Negate(up);
    for (int page = 0; page * rowsPer < n; page++) {
        BeginDrawing(); ClearBackground(RAYWHITE);
        BeginMode3D(cam);
        for (int r = 0; r < rowsPer && page * rowsPer + r < n; r++) {
            ModelAnimation *an = &a[page * rowsPer + r];
            for (int c = 0; c < cols; c++) {
                int f = (int)((an->frameCount - 1) * c / (float)(cols - 1));
                UpdateModelAnimation(m, *an, f);
                Vector3 p = Vector3Add(Vector3Scale(right, (c - (cols - 1) / 2.0f) * 1.6f), Vector3Scale(up, ((rowsPer - 1) / 2.0f - r) * 2.75f - 1.0f));
                DrawModel(m, p, 1.0f, WHITE);
                DrawLine3D(Vector3Add(p, (Vector3){-0.5f,0,0}), Vector3Add(p, (Vector3){0.5f,0,0}), GRAY);
                DrawLine3D(p, Vector3Add(p, (Vector3){0,0,0.6f}), RED);   // +Z = model forward
            }
        }
        EndMode3D();
        for (int r = 0; r < rowsPer && page * rowsPer + r < n; r++) {
            ModelAnimation *an = &a[page * rowsPer + r];
            DrawText(TextFormat("%s  %.2fs", an->name, an->frameCount / 60.0f), 10, 10 + r * 1100 / rowsPer, 22, BLACK);
        }
        EndDrawing();
        BeginDrawing(); EndDrawing();
        TakeScreenshot(TextFormat("clipview_%d.png", page));
    }
    CloseWindow();
    return 0;
}

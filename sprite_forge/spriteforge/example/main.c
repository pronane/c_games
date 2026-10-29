/*
 * SpriteForge example viewer.
 *   example.exe [characterDir] [secondCharacterDir] [--shots outDir]
 * Keys: LEFT/RIGHT walk, DOWN crouch, UP jump, 1-9 0 Q W E R = moves, F flip,
 *       +/- size, SPACE next move, TAB = move strip view, ESC quit
 * --shots: renders preview PNGs of every move (all frames on the ground line) and a
 *          two-fighter scene into outDir, then exits (used by the automated test).
 */
#define SPRITEFORGE_IMPLEMENTATION
#include "spriteforge.h"
#include <stdio.h>
#include <string.h>

#define W 1280
#define H 720

static void DrawGround(float y) {
    DrawRectangle(0, (int)y, W, H - (int)y, (Color){52, 58, 70, 255});
    DrawLineEx((Vector2){0, y}, (Vector2){W, y}, 2, RED);
}

/* every frame of one move side by side, feet on the same ground line */
static void DrawMoveStrip(const SF_Character *c, int move, float groundY) {
    const SF_Move *mv = &c->moves[move];
    float scale = SF_ScaleForHeight(c, 300);
    float cw = mv->w * scale;
    float total = cw * mv->frames;
    if (total > W - 40) { scale *= (W - 40) / total; cw = mv->w * scale; total = cw * mv->frames; }
    float x0 = (W - total) / 2 + cw / 2;
    DrawGround(groundY);
    for (int i = 0; i < mv->frames; i++) {
        float x = x0 + i * cw;
        DrawRectangleLines((int)(x - cw / 2), (int)(groundY - c->ground * scale), (int)cw, (int)(mv->h * scale), (Color){90, 100, 120, 255});
        SF_Draw(c, move, (i + 0.5f) / mv->fps, x, groundY, false, scale);
        DrawLine((int)x, (int)(groundY - 8), (int)x, (int)(groundY + 8), SKYBLUE);
    }
    DrawText(TextFormat("%s / %s  frames %d  fps %.0f  %s", c->name, mv->name, mv->frames, mv->fps,
                        mv->loop ? "loop" : "once"), 20, 20, 28, RAYWHITE);
    DrawText("red = ground line from sprites.cfg, blue tick = anchor x", 20, 56, 20, LIGHTGRAY);
}

static void Shot(const char *dir, const char *name) {
    Image img = LoadImageFromScreen();
    ExportImage(img, TextFormat("%s/%s.png", dir, name));
    UnloadImage(img);
}

int main(int argc, char **argv) {
    const char *dirA = NULL, *dirB = NULL, *shots = NULL;
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--shots") && i + 1 < argc) shots = argv[++i];
        else if (!dirA) dirA = argv[i];
        else if (!dirB) dirB = argv[i];
    }
    if (!dirA) dirA = "assets/dec";
    SetConfigFlags(FLAG_MSAA_4X_HINT | FLAG_VSYNC_HINT);
    InitWindow(W, H, "SpriteForge example");
    SetTargetFPS(60);
    SF_Character a = SF_LoadCharacter(dirA);
    SF_Character b = dirB ? SF_LoadCharacter(dirB) : a;
    if (!a.ok) {
        while (!WindowShouldClose() && !shots) {
            BeginDrawing(); ClearBackground(BLACK);
            DrawText(TextFormat("could not load %s/sprites.cfg - run tools/spriteforge.py first", dirA), 20, 20, 20, RED);
            EndDrawing();
        }
        CloseWindow();
        return 1;
    }
    float groundY = H - 90;

    if (shots) {                                   /* automated preview capture */
        MakeDirectory(shots);
        for (int m = 0; m < a.moveCount; m++) {
            BeginDrawing(); ClearBackground((Color){28, 30, 38, 255});
            DrawMoveStrip(&a, m, groundY);
            EndDrawing();
            Shot(shots, TextFormat("move_%02d_%s", m, a.moves[m].name));
        }
        int pairs[4][2] = {{SF_IDLE, SF_IDLE}, {SF_PUNCH, SF_BLOCK}, {SF_KICK, SF_HIT}, {SF_SPECIAL1, SF_JUMP}};
        for (int s = 0; s < 4; s++) {
            int ma = SF_FindMove(&a, SF_STD_MOVE_NAMES[pairs[s][0]]);
            int mb = SF_FindMove(&b, SF_STD_MOVE_NAMES[pairs[s][1]]);
            BeginDrawing(); ClearBackground((Color){28, 30, 38, 255});
            DrawGround(groundY);
            float sa = SF_ScaleForHeight(&a, 360), sb = SF_ScaleForHeight(&b, 360);
            SF_Draw(&a, ma, 2.5f / a.moves[ma].fps, W * 0.36f, groundY, false, sa);
            SF_Draw(&b, mb, 2.5f / b.moves[mb].fps, W * 0.64f, groundY, true, sb);
            DrawText(TextFormat("scene %d: %s (%s) vs %s (%s, flipped)", s, a.name, a.moves[ma].name,
                                b.name, b.moves[mb].name), 20, 20, 24, RAYWHITE);
            EndDrawing();
            Shot(shots, TextFormat("scene_%d", s));
        }
        SF_Unload(&a); if (dirB) SF_Unload(&b);
        CloseWindow();
        return 0;
    }

    SF_Anim anim = {0}; SF_Restart(&anim, SF_FindMove(&a, "idle"));
    float x = W / 2.0f, height = 360; bool flip = false, strip = false;
    int hotkeys[] = {KEY_ONE, KEY_TWO, KEY_THREE, KEY_FOUR, KEY_FIVE, KEY_SIX, KEY_SEVEN, KEY_EIGHT,
                     KEY_NINE, KEY_ZERO, KEY_Q, KEY_W, KEY_E, KEY_R};
    while (!WindowShouldClose()) {
        float dt = GetFrameTime();
        int idle = SF_FindMove(&a, "idle");
        for (int k = 0; k < 14 && k < a.moveCount; k++) if (IsKeyPressed(hotkeys[k])) SF_Restart(&anim, k);
        if (IsKeyPressed(KEY_SPACE)) SF_Restart(&anim, (anim.move + 1) % a.moveCount);
        if (IsKeyPressed(KEY_F)) flip = !flip;
        if (IsKeyPressed(KEY_TAB)) strip = !strip;
        if (IsKeyDown(KEY_EQUAL) || IsKeyDown(KEY_KP_ADD)) height += 200 * dt;
        if (IsKeyDown(KEY_MINUS) || IsKeyDown(KEY_KP_SUBTRACT)) height -= 200 * dt;
        bool busy = !a.moves[anim.move].loop && !anim.done;
        if (!busy || anim.move == SF_FindMove(&a, "walk") || anim.move == idle) {
            if (IsKeyDown(KEY_RIGHT)) { x += 220 * dt; flip = false; SF_Play(&anim, SF_FindMove(&a, "walk")); }
            else if (IsKeyDown(KEY_LEFT)) { x -= 220 * dt; flip = true; SF_Play(&anim, SF_FindMove(&a, "walk")); }
            else if (IsKeyDown(KEY_DOWN)) SF_Play(&anim, SF_FindMove(&a, "crouch"));
            else if (IsKeyPressed(KEY_UP)) SF_Restart(&anim, SF_FindMove(&a, "jump"));
            else if (anim.move == SF_FindMove(&a, "walk")) SF_Play(&anim, idle);
        }
        if (SF_Update(&anim, &a, dt) && anim.move != SF_FindMove(&a, "crouch") && anim.move != SF_FindMove(&a, "block"))
            SF_Restart(&anim, idle);                  /* one-shot finished -> back to idle */
        if (!IsKeyDown(KEY_DOWN) && anim.move == SF_FindMove(&a, "crouch") && anim.done) SF_Restart(&anim, idle);

        BeginDrawing();
        ClearBackground((Color){28, 30, 38, 255});
        if (strip) DrawMoveStrip(&a, anim.move, groundY);
        else {
            DrawGround(groundY);
            SF_DrawAnim(&a, &anim, x, groundY, flip, SF_ScaleForHeight(&a, height));
            DrawText(TextFormat("%s: %s  frame %d/%d", a.name, a.moves[anim.move].name,
                                SF_FrameAt(&a, anim.move, anim.time) + 1, a.moves[anim.move].frames), 20, 20, 24, RAYWHITE);
            DrawText("arrows move/crouch/jump  1-0,Q,W,E,R moves  SPACE next  F flip  +/- size  TAB frames", 20, 52, 18, LIGHTGRAY);
        }
        EndDrawing();
    }
    SF_Unload(&a); if (dirB) SF_Unload(&b);
    CloseWindow();
    return 0;
}

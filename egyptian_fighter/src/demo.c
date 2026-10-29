// demo.c - scripted animation test.  Run:  egyptian_fighter --demo <charIndex> [outDir]
// Plays idle / walk / block / punch / kick / jump / crouch / throw / hit for one character
// (one copy facing right, one facing left) and saves every 3rd frame as PNG to outDir, so
// sprite sheets can be checked without playing.  Without outDir it just runs on screen.
#include "game.h"

typedef struct { const char *name; float seconds; } DemoSeg;

static void ClearInputs(Player *p) {
    p->inputLeft = p->inputRight = p->inputDown = p->inputUp = false;
    p->inputPunch = p->inputKick = p->inputSpecial1 = p->inputSpecial2 = false;
    p->inputBlock = p->inputThrow = p->inputTaunt = p->inputJumpAttack = false;
}

int RunDemo(int charIndex, const char *outDir) {
    Game g;
    Game_Init(&g);                      // character table + stages
    if (charIndex < 0 || charIndex >= MAX_CHARACTERS) charIndex = 0;

    Player pl[2];
    Player_Init(&pl[0], 420.0f, GROUND_Y, 1, charIndex);
    Player_Init(&pl[1], 860.0f, GROUND_Y, -1, charIndex);
    Player_LoadSprites(&pl[0], "assets", g.characters);
    Player_LoadSprites(&pl[1], "assets", g.characters);

    const DemoSeg segs[] = {
        { "idle", 1.7f }, { "walk", 1.6f }, { "block", 1.2f }, { "punch", 1.0f },
        { "kick", 1.0f }, { "jump", 1.5f }, { "crouch", 1.0f }, { "throw", 1.1f },
        { "hit", 1.0f },
    };
    const int nSegs = sizeof(segs) / sizeof(segs[0]);
    const float dt = 1.0f / 60.0f;

    for (int s = 0; s < nSegs && !WindowShouldClose(); s++) {
        for (int i = 0; i < 2; i++) {       // reset position/state, keep the loaded sheets
            SpriteSheet keep[STATE_COUNT];
            float sc = pl[i].spriteScale, ax = pl[i].spriteAnchorX;
            memcpy(keep, pl[i].sheets, sizeof(keep));
            Player_Init(&pl[i], i ? 860.0f : 420.0f, GROUND_Y, i ? -1 : 1, charIndex);
            memcpy(pl[i].sheets, keep, sizeof(keep));
            pl[i].spriteScale = sc; pl[i].spriteAnchorX = ax;
        }
        if (strcmp(segs[s].name, "hit") == 0) {
            Player_SetState(&pl[0], STATE_HIT); Player_SetState(&pl[1], STATE_HIT);
        }

        int nFrames = (int)(segs[s].seconds / dt);
        for (int f = 0; f < nFrames && !WindowShouldClose(); f++) {
            for (int i = 0; i < 2; i++) {
                Player *q = &pl[i];
                ClearInputs(q);
                const char *n = segs[s].name;
                bool first = (f == 0);
                if (!strcmp(n, "walk")) { if (i == 0) q->inputRight = true; else q->inputLeft = true; }
                else if (!strcmp(n, "block"))  q->inputBlock = true;
                else if (!strcmp(n, "punch"))  q->inputPunch = first;
                else if (!strcmp(n, "kick"))   q->inputKick = first;
                else if (!strcmp(n, "jump"))   q->inputUp = first;
                else if (!strcmp(n, "crouch")) q->inputDown = true;
                else if (!strcmp(n, "throw"))  q->inputThrow = first;
                Player_Update(q, dt);
                if (!strcmp(n, "hit")) { q->velocity.x = 0; q->invincible = false; }
            }

            BeginDrawing();
            ClearBackground((Color){ 40, 44, 52, 255 });
            if (g.stageLoaded[charIndex]) {
                Texture2D t = g.stages[charIndex];
                DrawTexturePro(t, (Rectangle){ 0, 0, (float)t.width, (float)t.height },
                               (Rectangle){ 0, 0, SCREEN_WIDTH, SCREEN_HEIGHT }, (Vector2){ 0 }, 0, WHITE);
            } else {
                DrawRectangleGradientV(0, 0, SCREEN_WIDTH, (int)GROUND_Y, (Color){ 90, 110, 140, 255 }, (Color){ 170, 160, 140, 255 });
                DrawRectangle(0, (int)GROUND_Y, SCREEN_WIDTH, SCREEN_HEIGHT - (int)GROUND_Y, (Color){ 120, 100, 80, 255 });
            }
            DrawLine(0, (int)GROUND_Y, SCREEN_WIDTH, (int)GROUND_Y, RED);
            Player_Draw(&pl[0]);
            Player_Draw(&pl[1]);
            const SpriteSheet *sh = &pl[0].sheets[pl[0].state];
            DrawRectangle(0, 0, SCREEN_WIDTH, 34, (Color){ 0, 0, 0, 160 });
            DrawText(TextFormat("%s  |  %s  |  frame %d/%d  |  cell %dpx  |  %s",
                                g.characters[charIndex].name, segs[s].name,
                                pl[0].currentFrame + 1, sh->frameCount, (int)sh->frameWidth,
                                sh->grid ? "grid sheet" : "legacy sheet"),
                     12, 8, 20, RAYWHITE);
            EndDrawing();

            if (outDir && (f % 3) == 0) {
                Image shot = LoadImageFromScreen();
                ExportImage(shot, TextFormat("%s/%s_%03d.png", outDir, segs[s].name, f / 3));
                UnloadImage(shot);
            }
        }
    }
    Player_UnloadSprites(&pl[0]);
    Player_UnloadSprites(&pl[1]);
    Game_Unload(&g);
    return 0;
}

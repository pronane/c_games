#include "game.h"

void Game_Init(Game *g) {
    memset(g, 0, sizeof(Game));

    g->characters[0] = (CharacterDef){ "RA",     "char_egypt",  "assets/stages/egypt.png",  "assets/portraits/ra.png" };
    g->characters[1] = (CharacterDef){ "PAUL",   "char1",       "assets/stages/street.png", "assets/portraits/paul.png" };
    g->characters[2] = (CharacterDef){ "DRAGON", "char_dragon", "assets/stages/japan.png",  "assets/portraits/dragon.png" };
    g->characters[3] = (CharacterDef){ "FLAME",  "char_flame",  "assets/stages/usa.png",    "assets/portraits/flame.png" };

    g->selectP1 = 0;
    g->selectP2 = 2;
    g->p1Ready = false;
    g->p2Ready = false;
    g->mode = MODE_1P_VS_CPU;
    g->screen = SCREEN_SELECT;
    g->gameOver = false;
    g->winner = 0;
    g->roundTimer = 99.0f;
    g->paused = false;

    for (int i = 0; i < MAX_CHARACTERS; i++) {
        if (FileExists(g->characters[i].stageFile)) {
            g->stages[i] = LoadTexture(g->characters[i].stageFile);
            g->stageLoaded[i] = true;
        }
        if (FileExists(g->characters[i].portraitFile)) {
            g->portraits[i] = LoadTexture(g->characters[i].portraitFile);
            g->portraitLoaded[i] = true;
        }
    }
}

static void StartFight(Game *g) {
    // Unload any previous sprites
    Player_UnloadSprites(&g->player1);
    Player_UnloadSprites(&g->player2);

    Player_Init(&g->player1, 300.0f, GROUND_Y, 1, g->selectP1);
    Player_Init(&g->player2, 980.0f, GROUND_Y, -1, g->selectP2);

    // Load sprites for the chosen characters
    // Works even if many PNGs are missing – placeholders will be used + warnings printed
    Player_LoadSprites(&g->player1, "assets", g->characters);
    Player_LoadSprites(&g->player2, "assets", g->characters);

    g->gameOver = false;
    g->winner = 0;
    g->roundTimer = 99.0f;
    g->paused = false;
    g->screen = SCREEN_FIGHT;
}

void Game_Unload(Game *g) {
    Player_UnloadSprites(&g->player1);
    Player_UnloadSprites(&g->player2);
    for (int i = 0; i < MAX_CHARACTERS; i++) {
        if (g->stageLoaded[i]) UnloadTexture(g->stages[i]);
        if (g->portraitLoaded[i]) UnloadTexture(g->portraits[i]);
    }
}

static void ReadInputP1(Player *p) {
    p->inputLeft = p->inputRight = p->inputDown = p->inputUp = false;
    p->inputPunch = p->inputKick = p->inputSpecial1 = p->inputSpecial2 = false;
    p->inputBlock = p->inputThrow = p->inputTaunt = p->inputJumpAttack = false;

    p->inputLeft        = IsKeyDown(KEY_A) || IsKeyDown(KEY_LEFT);
    p->inputRight       = IsKeyDown(KEY_D) || IsKeyDown(KEY_RIGHT);
    p->inputDown        = IsKeyDown(KEY_S) || IsKeyDown(KEY_DOWN);
    p->inputUp          = IsKeyDown(KEY_W) || IsKeyDown(KEY_UP);

    p->inputPunch       = IsKeyPressed(KEY_J);
    p->inputKick        = IsKeyPressed(KEY_K);
    p->inputSpecial1    = IsKeyPressed(KEY_U);
    p->inputSpecial2    = IsKeyPressed(KEY_I);
    p->inputBlock       = IsKeyDown(KEY_L);
    p->inputThrow       = IsKeyPressed(KEY_O);
    p->inputTaunt       = IsKeyPressed(KEY_P);
    p->inputJumpAttack  = IsKeyPressed(KEY_J) || IsKeyPressed(KEY_K);
}

static void ReadInputP2(Player *p) {
    // Second player on the right side of the keyboard
    p->inputLeft = p->inputRight = p->inputDown = p->inputUp = false;
    p->inputPunch = p->inputKick = p->inputSpecial1 = p->inputSpecial2 = false;
    p->inputBlock = p->inputThrow = p->inputTaunt = p->inputJumpAttack = false;

    p->inputLeft        = IsKeyDown(KEY_LEFT);
    p->inputRight       = IsKeyDown(KEY_RIGHT);
    p->inputDown        = IsKeyDown(KEY_DOWN);
    p->inputUp          = IsKeyDown(KEY_UP);

    // Numpad style or alternative keys
    p->inputPunch       = IsKeyPressed(KEY_KP_1) || IsKeyPressed(KEY_Z);
    p->inputKick        = IsKeyPressed(KEY_KP_2) || IsKeyPressed(KEY_X);
    p->inputSpecial1    = IsKeyPressed(KEY_KP_4) || IsKeyPressed(KEY_C);
    p->inputSpecial2    = IsKeyPressed(KEY_KP_5) || IsKeyPressed(KEY_V);
    p->inputBlock       = IsKeyDown(KEY_KP_3) || IsKeyDown(KEY_B);
    p->inputThrow       = IsKeyPressed(KEY_KP_6) || IsKeyPressed(KEY_N);
    p->inputTaunt       = IsKeyPressed(KEY_KP_7) || IsKeyPressed(KEY_M);
    p->inputJumpAttack  = IsKeyPressed(KEY_KP_1) || IsKeyPressed(KEY_KP_2) ||
                          IsKeyPressed(KEY_Z) || IsKeyPressed(KEY_X);
}

static void SimpleCPU(Player *cpu, const Player *human) {
    cpu->inputLeft = cpu->inputRight = cpu->inputDown = cpu->inputUp = false;
    cpu->inputPunch = cpu->inputKick = cpu->inputSpecial1 = cpu->inputSpecial2 = false;
    cpu->inputBlock = cpu->inputThrow = cpu->inputTaunt = cpu->inputJumpAttack = false;

    float dx = human->position.x - cpu->position.x;

    if (dx > 0) cpu->facing = 1;
    else        cpu->facing = -1;

    if (fabsf(dx) > 220.0f) {
        if (dx > 0) cpu->inputRight = true;
        else        cpu->inputLeft = true;
    } else if (fabsf(dx) < 120.0f) {
        if (GetRandomValue(0, 100) < 40) {
            cpu->inputBlock = true;
        } else {
            if (dx > 0) cpu->inputLeft = true;
            else        cpu->inputRight = true;
        }
    }

    if (fabsf(dx) < 180.0f && GetRandomValue(0, 100) < 3) {
        int r = GetRandomValue(0, 5);
        if (r == 0) cpu->inputPunch = true;
        else if (r == 1) cpu->inputKick = true;
        else if (r == 2) cpu->inputSpecial1 = true;
        else if (r == 3) cpu->inputSpecial2 = true;
        else if (r == 4) cpu->inputThrow = true;
    }

    if (GetRandomValue(0, 200) < 1) {
        cpu->inputUp = true;
    }
}

static void CheckHits(Game *g) {
    Player *p1 = &g->player1;
    Player *p2 = &g->player2;

    if (p1->attackActive && !p2->invincible && !p2->inputBlock) {
        if (CheckCollisionRecs(p1->hitbox, p2->hurtbox)) {
            p2->health -= 8;
            if (p2->health < 0) p2->health = 0;
            Player_SetState(p2, STATE_HIT);
            p2->invincible = true;
            p2->invincibleTimer = 0.6f;
            p2->velocity.x = p1->facing * 6.0f;
            p2->velocity.y = -4.0f;
            p2->onGround = false;
        }
    }

    if (p2->attackActive && !p1->invincible && !p1->inputBlock) {
        if (CheckCollisionRecs(p2->hitbox, p1->hurtbox)) {
            p1->health -= 8;
            if (p1->health < 0) p1->health = 0;
            Player_SetState(p1, STATE_HIT);
            p1->invincible = true;
            p1->invincibleTimer = 0.6f;
            p1->velocity.x = p2->facing * 6.0f;
            p1->velocity.y = -4.0f;
            p1->onGround = false;
        }
    }

    if (p1->health <= 0 && !g->gameOver) {
        g->gameOver = true;
        g->winner = 2;
        Player_SetState(p2, STATE_VICTORY);
        g->screen = SCREEN_RESULT;
    }
    if (p2->health <= 0 && !g->gameOver) {
        g->gameOver = true;
        g->winner = 1;
        Player_SetState(p1, STATE_VICTORY);
        g->screen = SCREEN_RESULT;
    }
}

static void KeepPlayersApart(Player *p1, Player *p2) {
    float distance = p2->position.x - p1->position.x;
    float minDistance = PLAYER_WIDTH;
    if (fabsf(distance) >= minDistance) return;

    float direction = distance >= 0.0f ? 1.0f : -1.0f;
    float overlap = minDistance - fabsf(distance);
    float p1OldX = p1->position.x;
    float p2OldX = p2->position.x;

    p1->position.x -= direction * overlap * 0.5f;
    p2->position.x += direction * overlap * 0.5f;
    if (p1->position.x < 40.0f) p1->position.x = 40.0f;
    if (p1->position.x > SCREEN_WIDTH - 40.0f) p1->position.x = SCREEN_WIDTH - 40.0f;
    if (p2->position.x < 40.0f) p2->position.x = 40.0f;
    if (p2->position.x > SCREEN_WIDTH - 40.0f) p2->position.x = SCREEN_WIDTH - 40.0f;

    if (fabsf(p2->position.x - p1->position.x) < minDistance) {
        if (direction > 0.0f) {
            if (p1->position.x - 40.0f >= overlap) p1->position.x -= overlap;
            else p2->position.x += overlap;
        } else {
            if (SCREEN_WIDTH - 40.0f - p1->position.x >= overlap) p1->position.x += overlap;
            else p2->position.x -= overlap;
        }
    }

    float p1Shift = p1->position.x - p1OldX;
    float p2Shift = p2->position.x - p2OldX;
    p1->hurtbox = Player_GetHurtbox(p1);
    p2->hurtbox = Player_GetHurtbox(p2);
    if (p1->attackActive) p1->hitbox.x += p1Shift;
    if (p2->attackActive) p2->hitbox.x += p2Shift;
}

void Game_Update(Game *g) {
    if (g->paused) return;

    float dt = GetFrameTime();

    // ---------- CHARACTER SELECT ----------
    if (g->screen == SCREEN_SELECT) {
        if (IsKeyPressed(KEY_TAB)) {
            g->mode = (g->mode + 1) % 3;
            g->p1Ready = false;
            g->p2Ready = false;
        }

        bool p1Human = (g->mode == MODE_1P_VS_CPU || g->mode == MODE_1P_VS_2P);
        bool p2Human = (g->mode == MODE_CPU_VS_1P || g->mode == MODE_1P_VS_2P);

        if (p1Human) {
            if (IsKeyPressed(KEY_A) || IsKeyPressed(KEY_LEFT)) {
                g->selectP1 = (g->selectP1 - 1 + MAX_CHARACTERS) % MAX_CHARACTERS;
                g->p1Ready = false;
            }
            if (IsKeyPressed(KEY_D) || IsKeyPressed(KEY_RIGHT)) {
                g->selectP1 = (g->selectP1 + 1) % MAX_CHARACTERS;
                g->p1Ready = false;
            }
            if (IsKeyPressed(KEY_J) || IsKeyPressed(KEY_ENTER)) g->p1Ready = true;
        } else {
            g->p1Ready = true;
        }

        if (p2Human) {
            if (IsKeyPressed(KEY_LEFT)) {
                g->selectP2 = (g->selectP2 - 1 + MAX_CHARACTERS) % MAX_CHARACTERS;
                g->p2Ready = false;
            }
            if (IsKeyPressed(KEY_RIGHT)) {
                g->selectP2 = (g->selectP2 + 1) % MAX_CHARACTERS;
                g->p2Ready = false;
            }
            if (IsKeyPressed(KEY_KP_1) || IsKeyPressed(KEY_Z)) g->p2Ready = true;
        } else {
            g->p2Ready = true;
        }

        if (g->p1Ready && g->p2Ready) StartFight(g);
        return;
    }

    // ---------- FIGHT ----------
    if (g->screen == SCREEN_FIGHT) {
        ReadInputP1(&g->player1);

        if (g->mode != MODE_1P_VS_2P) {
            SimpleCPU(&g->player2, &g->player1);
        } else {
            ReadInputP2(&g->player2);
        }

        Player_Update(&g->player1, dt);
        Player_Update(&g->player2, dt);

        KeepPlayersApart(&g->player1, &g->player2);
        CheckHits(g);

        g->roundTimer -= dt;
        if (g->roundTimer <= 0.0f) {
            g->roundTimer = 0.0f;
            g->gameOver = true;
            if (g->player1.health > g->player2.health) g->winner = 1;
            else if (g->player2.health > g->player1.health) g->winner = 2;
            else g->winner = 0;
            g->screen = SCREEN_RESULT;
        }
        return;
    }

    // ---------- RESULT ----------
    if (g->screen == SCREEN_RESULT) {
        if (IsKeyPressed(KEY_R) || IsKeyPressed(KEY_ENTER)) {
            // Back to select
            Game_Unload(g);
            g->p1Ready = false;
            g->p2Ready = false;
            g->screen = SCREEN_SELECT;
        }
    }
}

static void DrawHealthBar(float x, float y, float width, float height, int health, bool rightSide) {
    DrawRectangle(x, y, width, height, (Color){40, 40, 40, 255});
    float pct = (float)health / (float)MAX_HEALTH;
    float fillW = width * pct;
    Color col = health > 50 ? GREEN : (health > 25 ? ORANGE : RED);

    if (rightSide) {
        DrawRectangle(x + (width - fillW), y, fillW, height, col);
    } else {
        DrawRectangle(x, y, fillW, height, col);
    }
    DrawRectangleLinesEx((Rectangle){x, y, width, height}, 3, WHITE);
}

void Game_Draw(const Game *g) {
    // Background - stage of P1 character (or solid)
    int stageIdx = (g->screen == SCREEN_FIGHT || g->screen == SCREEN_RESULT) ? g->player1.characterIndex : g->selectP1;
    if (g->stageLoaded[stageIdx]) {
        DrawTexturePro(g->stages[stageIdx],
            (Rectangle){0, 0, g->stages[stageIdx].width, g->stages[stageIdx].height},
            (Rectangle){0, 0, SCREEN_WIDTH, SCREEN_HEIGHT},
            (Vector2){0, 0}, 0, WHITE);
    } else {
        DrawRectangle(0, 0, SCREEN_WIDTH, SCREEN_HEIGHT, (Color){30, 30, 50, 255});
    }

    // ---------- SELECT SCREEN ----------
    if (g->screen == SCREEN_SELECT) {
        if (g->stageLoaded[g->selectP1]) {
            DrawTexturePro(g->stages[g->selectP1],
                (Rectangle){0, 0, g->stages[g->selectP1].width, g->stages[g->selectP1].height},
                (Rectangle){0, 0, SCREEN_WIDTH, SCREEN_HEIGHT},
                (Vector2){0, 0}, 0, WHITE);
            DrawRectangle(0, 0, SCREEN_WIDTH, SCREEN_HEIGHT, (Color){0, 0, 0, 140});
        } else {
            DrawRectangle(0, 0, SCREEN_WIDTH, SCREEN_HEIGHT, (Color){20, 15, 30, 255});
        }

        DrawText("EGYPTIAN FIGHTER", SCREEN_WIDTH/2 - MeasureText("EGYPTIAN FIGHTER", 46)/2, 40, 46, GOLD);

        const char *modeText = "1P vs CPU";
        if (g->mode == MODE_CPU_VS_1P) modeText = "CPU vs 1P";
        if (g->mode == MODE_1P_VS_2P)  modeText = "1P vs 2P";
        DrawText(TextFormat("Mode: %s   (TAB)", modeText),
                 SCREEN_WIDTH/2 - 140, 100, 22, YELLOW);

        DrawRectangle(40, 160, 360, 420, (Color){0, 0, 0, 180});
        DrawRectangleLinesEx((Rectangle){40, 160, 360, 420}, 3, g->p1Ready ? GREEN : YELLOW);
        DrawText((g->mode == MODE_CPU_VS_1P) ? "CPU" : "1P", 60, 175, 24, RAYWHITE);
        if (g->portraitLoaded[g->selectP1]) {
            DrawTexturePro(g->portraits[g->selectP1],
                (Rectangle){0, 0, g->portraits[g->selectP1].width, g->portraits[g->selectP1].height},
                (Rectangle){60, 210, 160, 200}, (Vector2){0, 0}, 0, WHITE);
        }
        DrawText(g->characters[g->selectP1].name, 60, 430, 32, SKYBLUE);
        if (g->mode != MODE_CPU_VS_1P) {
            DrawText("A/D = Change", 60, 480, 16, LIGHTGRAY);
            DrawText("J/Enter = Ready", 60, 505, 16, LIGHTGRAY);
        }
        if (g->p1Ready) DrawText("READY", 60, 540, 28, GREEN);

        DrawRectangle(880, 160, 360, 420, (Color){0, 0, 0, 180});
        DrawRectangleLinesEx((Rectangle){880, 160, 360, 420}, 3, g->p2Ready ? GREEN : YELLOW);
        DrawText((g->mode == MODE_1P_VS_CPU) ? "CPU" : "2P", 900, 175, 24, RAYWHITE);
        if (g->portraitLoaded[g->selectP2]) {
            DrawTexturePro(g->portraits[g->selectP2],
                (Rectangle){0, 0, g->portraits[g->selectP2].width, g->portraits[g->selectP2].height},
                (Rectangle){900, 210, 160, 200}, (Vector2){0, 0}, 0, WHITE);
        }
        DrawText(g->characters[g->selectP2].name, 900, 430, 32, PINK);
        if (g->mode != MODE_1P_VS_CPU) {
            DrawText("Left/Right = Change", 900, 480, 16, LIGHTGRAY);
            DrawText("Z = Ready", 900, 505, 16, LIGHTGRAY);
        }
        if (g->p2Ready) DrawText("READY", 900, 540, 28, GREEN);

        DrawText("SELECT FIGHTER", SCREEN_WIDTH/2 - MeasureText("SELECT FIGHTER", 20)/2, 200, 20, RAYWHITE);
        for (int i = 0; i < MAX_CHARACTERS; i++) {
            int x = 460 + (i % 2) * 180;
            int y = 250 + (i / 2) * 140;
            Color border = GRAY;
            if (i == g->selectP1) border = SKYBLUE;
            if (i == g->selectP2) border = PINK;
            if (i == g->selectP1 && i == g->selectP2) border = GOLD;
            DrawRectangle(x, y, 160, 120, (Color){0, 0, 0, 160});
            DrawRectangleLinesEx((Rectangle){x, y, 160, 120}, 3, border);
            if (g->portraitLoaded[i]) {
                DrawTexturePro(g->portraits[i],
                    (Rectangle){0, 0, g->portraits[i].width, g->portraits[i].height},
                    (Rectangle){x + 10, y + 8, 60, 70}, (Vector2){0, 0}, 0, WHITE);
            }
            DrawText(g->characters[i].name, x + 75, y + 45, 18, RAYWHITE);
        }

        DrawText("Both ready = Fight starts", SCREEN_WIDTH/2 - 120, 650, 18, LIGHTGRAY);
        return;
    }

    // ---------- FIGHT / RESULT ----------
    // Floor
    DrawRectangle(0, GROUND_Y, SCREEN_WIDTH, SCREEN_HEIGHT - GROUND_Y, (Color){60, 50, 40, 255});
    DrawRectangle(0, GROUND_Y, SCREEN_WIDTH, 8, (Color){120, 100, 70, 255});


    // Players
    Player_Draw(&g->player1);
    Player_Draw(&g->player2);

    // UI
    DrawHealthBar(40, 30, 400, 28, g->player1.health, false);
    DrawHealthBar(SCREEN_WIDTH - 440, 30, 400, 28, g->player2.health, true);

    DrawText(g->characters[g->player1.characterIndex].name, 50, 65, 20, RAYWHITE);
    DrawText((g->mode != MODE_1P_VS_2P) ? "CPU" : g->characters[g->player2.characterIndex].name, 
             SCREEN_WIDTH - 150, 65, 20, RAYWHITE);

    // Timer
    char timerText[16];
    snprintf(timerText, sizeof(timerText), "%02d", (int)g->roundTimer);
    int tw = MeasureText(timerText, 40);
    DrawText(timerText, SCREEN_WIDTH/2 - tw/2, 25, 40, YELLOW);

    // Controls reminder
    DrawText("P1: WASD+J/K/U/I/L/O/P    P2: Arrows+Z/X/C/V/B/N/M    ESC=Pause", 
             20, SCREEN_HEIGHT - 30, 16, LIGHTGRAY);

    // Result overlay
    if (g->screen == SCREEN_RESULT) {
        DrawRectangle(0, 0, SCREEN_WIDTH, SCREEN_HEIGHT, (Color){0, 0, 0, 180});
        const char *msg = "DRAW";
        if (g->winner == 1) msg = "PLAYER 1 WINS!";
        if (g->winner == 2) msg = (g->mode != MODE_1P_VS_2P) ? "CPU WINS!" : "PLAYER 2 WINS!";
        int mw = MeasureText(msg, 50);
        DrawText(msg, SCREEN_WIDTH/2 - mw/2, SCREEN_HEIGHT/2 - 40, 50, GOLD);
        DrawText("Press R or Enter to return to Character Select", 
                 SCREEN_WIDTH/2 - 260, SCREEN_HEIGHT/2 + 30, 22, RAYWHITE);
    }
}

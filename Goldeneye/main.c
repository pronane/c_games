#include "game.h"

#include <math.h>

#if defined(PLATFORM_RAYLIB)
#include "raylib.h"
#include "rlgl.h"
#elif defined(PLATFORM_N64)
#include <libdragon.h>
#include <GL/gl.h>
#else
#error "Define PLATFORM_RAYLIB or PLATFORM_N64."
#endif

#define WINDOW_WIDTH 1280
#define WINDOW_HEIGHT 720
#define GH_PI 3.14159265f

#if defined(PLATFORM_RAYLIB)

static const char *WeaponAssetPaths[GAME_WEAPON_COUNT] = {
    "assets/weapons/ion_sidearm.png",
    "assets/weapons/pulse_carbine.png"
};

static const char *SoundAssetPaths[4] = {
    "assets/audio/sidearm.wav",
    "assets/audio/carbine.wav",
    "assets/audio/pickup.wav",
    "assets/audio/reload.wav"
};

static void DrawRockPeak(float x, float z, float width, float height,
                         Color dark_rock, Color ice)
{
    const float half = width * 0.5f;
    const Vector3 top = {x, height, z};
    const Vector3 left = {x - half, 0.0f, z + half * 0.45f};
    const Vector3 front = {x, 0.0f, z - half};
    const Vector3 right = {x + half, 0.0f, z + half * 0.45f};
    const Vector3 back = {x, 0.0f, z + half};

    DrawTriangle3D(left, front, top, dark_rock);
    DrawTriangle3D(front, right, top, dark_rock);
    DrawTriangle3D(right, back, top, dark_rock);
    DrawTriangle3D(back, left, top, dark_rock);

    const Vector3 cap = {x, height * 0.82f, z};
    DrawTriangle3D(left, cap, front, ice);
    DrawTriangle3D(front, cap, right, ice);
}

static void DrawSnowboundSkyline(void)
{
    const Color deep_rock = (Color){37, 49, 59, 255};
    const Color lit_rock = (Color){56, 71, 81, 255};
    const Color glacier = (Color){127, 150, 157, 255};
    const Color snow = (Color){186, 201, 201, 255};
    const float skyline[][4] = {
        {-22.0f, -30.0f, 15.0f, 19.0f}, {-7.0f, -34.0f, 18.0f, 24.0f},
        {11.0f, -32.0f, 20.0f, 21.0f}, {28.0f, -28.0f, 17.0f, 16.0f},
        {34.0f, -8.0f, 18.0f, 18.0f}, {33.0f, 15.0f, 21.0f, 23.0f},
        {20.0f, 31.0f, 17.0f, 16.0f}, {2.0f, 35.0f, 22.0f, 25.0f},
        {-18.0f, 32.0f, 19.0f, 20.0f}, {-34.0f, 17.0f, 16.0f, 15.0f},
        {-36.0f, -4.0f, 20.0f, 22.0f}, {-34.0f, -22.0f, 16.0f, 17.0f}
    };

    for (int i = 0; i < (int)(sizeof(skyline) / sizeof(skyline[0])); ++i) {
        const Color rock = i % 2 == 0 ? deep_rock : lit_rock;
        const Color ice = i % 2 == 0 ? glacier : snow;
        DrawRockPeak(skyline[i][0], skyline[i][1], skyline[i][2],
                     skyline[i][3], rock, ice);
    }
}

static void DrawHarbor(const GameState *game, bool enhanced)
{
    const Color concrete = (Color){65, 75, 77, 255};
    const Color concrete_light = (Color){100, 110, 108, 255};
    const Color trim = (Color){43, 55, 59, 255};
    const Color deck = (Color){48, 53, 53, 255};
    DrawPlane((Vector3){0.0f, -0.3f, 0.0f}, (Vector2){96.0f, 96.0f},
              (Color){128, 144, 148, 255});
    DrawSnowboundSkyline();
    DrawCube((Vector3){0.0f, -0.02f, 0.0f}, 24.0f, 0.14f, 24.0f, deck);

    for (int i = 0; i < 7; ++i) {
        const float offset = -9.0f + (float)i * 3.0f;
        DrawCube((Vector3){offset, 0.056f, 0.0f}, 0.055f, 0.012f, 22.5f,
                 (Color){66, 72, 71, 255});
        DrawCube((Vector3){0.0f, 0.055f, offset}, 22.5f, 0.012f, 0.055f,
                 (Color){66, 72, 71, 255});
    }
    for (int i = 0; i < 20; ++i) {
        const float x = -10.0f + (float)((i * 13) % 20);
        const float z = -10.0f + (float)((i * 7) % 20);
        DrawCube((Vector3){x, 0.057f, z}, 0.045f, 0.012f, 0.55f,
                 (Color){92, 99, 96, 255});
    }

    for (int i = 0; i < GAME_WALL_COUNT; ++i) {
        const GameWall *wall = &GameWalls[i];
        DrawCube((Vector3){wall->x, wall->height * 0.5f, wall->z},
                 wall->width, wall->height, wall->depth, concrete);
        DrawCube((Vector3){wall->x, wall->height - 0.12f, wall->z},
                 wall->width + 0.06f, 0.16f, wall->depth + 0.06f, concrete_light);
        DrawCube((Vector3){wall->x, 0.24f, wall->z},
                 wall->width + 0.08f, 0.28f, wall->depth + 0.08f, trim);
    }

    DrawCube((Vector3){0.0f, 2.0f, -11.65f}, 24.0f, 4.0f, 0.5f, concrete);
    DrawCube((Vector3){0.0f, 1.82f, 11.65f}, 24.0f, 3.64f, 0.5f, concrete);
    DrawCube((Vector3){-11.65f, 1.82f, 0.0f}, 0.5f, 3.64f, 24.0f, concrete);
    DrawCube((Vector3){11.65f, 1.82f, 0.0f}, 0.5f, 3.64f, 24.0f, concrete);

    DrawCube((Vector3){-6.9f, 2.05f, -10.15f}, 8.2f, 4.1f, 2.65f,
             (Color){72, 81, 82, 255});
    DrawCube((Vector3){-6.9f, 4.16f, -10.15f}, 8.5f, 0.18f, 2.9f,
             (Color){105, 115, 113, 255});
    DrawCube((Vector3){-6.9f, 3.3f, -8.79f}, 7.7f, 0.34f, 0.08f, trim);
    for (int i = 0; i < 5; ++i) {
        const float x = -10.0f + (float)i * 1.55f;
        DrawCube((Vector3){x, 2.62f, -8.73f}, 1.12f, 0.36f, 0.05f,
                 (Color){79, 111, 119, 255});
        DrawCube((Vector3){x, 2.67f, -8.68f}, 0.8f, 0.1f, 0.03f,
                 (Color){161, 187, 187, 255});
    }
    DrawCube((Vector3){-6.7f, 1.0f, -8.76f}, 1.2f, 2.0f, 0.12f,
             (Color){43, 52, 54, 255});
    DrawCube((Vector3){-6.22f, 1.0f, -8.67f}, 0.04f, 0.11f, 0.05f,
             (Color){218, 173, 93, 255});
    for (int i = 0; i < 5; ++i) {
        const float x = -10.1f + (float)i * 1.6f;
        DrawCube((Vector3){x, 1.15f, -11.46f}, 0.66f, 0.18f, 0.06f,
                 (Color){120, 137, 138, 255});
        DrawCube((Vector3){x, 0.82f, -11.46f}, 0.12f, 0.48f, 0.08f,
                 trim);
    }

    const float tower_positions[][2] = {
        {-12.8f, -12.8f}, {12.8f, -12.8f},
        {-12.8f, 12.8f}, {12.8f, 12.8f}
    };
    for (int i = 0; i < 4; ++i) {
        const float x = tower_positions[i][0];
        const float z = tower_positions[i][1];
        DrawCube((Vector3){x, 2.45f, z}, 1.5f, 4.9f, 1.5f,
                 (Color){61, 70, 72, 255});
        DrawCube((Vector3){x, 5.0f, z}, 2.0f, 0.3f, 2.0f, trim);
        DrawCube((Vector3){x, 5.32f, z}, 1.25f, 0.42f, 1.25f,
                 (Color){82, 96, 98, 255});
        DrawCube((Vector3){x, 5.35f, z + 0.66f}, 0.85f, 0.12f, 0.08f,
                 (Color){193, 203, 194, 255});
        DrawCube((Vector3){x, 4.4f, z + 0.77f}, 0.55f, 0.08f, 0.03f,
                 (Color){218, 171, 92, 255});
    }

    for (int i = 0; i < 4; ++i) {
        const float x = -9.8f + (float)i * 2.2f;
        const float z = -3.0f + (float)(i % 2) * 1.1f;
        const Color crate_color = i % 2 == 0 ? (Color){95, 91, 76, 255} :
                                                (Color){76, 85, 81, 255};
        DrawCube((Vector3){x, 0.68f, z}, 1.65f, 1.3f, 1.4f, crate_color);
        DrawCubeWires((Vector3){x, 0.68f, z}, 1.67f, 1.32f, 1.42f, trim);
        DrawCube((Vector3){x, 0.68f, z - 0.72f}, 0.08f, 1.1f, 0.025f,
                 concrete_light);
        DrawCube((Vector3){x - 0.72f, 0.68f, z}, 0.025f, 1.1f, 0.08f,
                 concrete_light);
    }

    DrawCube((Vector3){7.0f, 0.34f, -7.0f}, 1.0f, 0.68f, 1.0f,
             game->has_data_core ? (Color){55, 78, 80, 255} : (Color){47, 219, 204, 255});
    DrawCubeWires((Vector3){7.0f, 0.34f, -7.0f}, 1.06f, 0.72f, 1.06f,
                  (Color){140, 238, 227, 255});
    if (!game->has_carbine) {
        const float pickup_y = 0.58f + sinf(game->match_time * 2.0f) * 0.06f;
        DrawCube((Vector3){GAME_CARBINE_X, pickup_y, GAME_CARBINE_Z},
                 0.84f, 0.16f, 0.3f, (Color){66, 97, 103, 255});
        DrawCube((Vector3){GAME_CARBINE_X + 0.2f, pickup_y + 0.04f,
                           GAME_CARBINE_Z - 0.02f},
                 0.5f, 0.1f, 0.16f, (Color){120, 154, 153, 255});
        DrawCubeWires((Vector3){GAME_CARBINE_X, pickup_y, GAME_CARBINE_Z},
                      0.86f, 0.18f, 0.32f, (Color){90, 217, 204, 255});
    }
    DrawCylinder((Vector3){9.0f, 0.03f, -9.0f}, 1.15f, 1.15f, 0.06f,
                 enhanced ? 32 : 12,
                 game->has_data_core ? (Color){41, 190, 124, 255} :
                                       (Color){70, 103, 108, 255});

    for (int i = 0; i < 6; ++i) {
        const float x = -9.0f + (float)i * 3.6f;
        const Color light = (i % 2 == 0) ? (Color){62, 210, 208, 255} :
                                           (Color){231, 163, 86, 255};
        DrawCube((Vector3){x, 2.5f, -10.9f}, 0.12f, 2.4f, 0.12f, trim);
        DrawCube((Vector3){x, 3.75f, -10.9f}, 0.62f, 0.16f, 0.62f, light);
    }
}

static Vector3 GuardPoint(Vector3 origin, Vector3 right, Vector3 forward,
                          float side, float vertical, float depth)
{
    return (Vector3){origin.x + right.x * side + forward.x * depth,
                     origin.y + vertical,
                     origin.z + right.z * side + forward.z * depth};
}

static void DrawEllipsoid(Vector3 position, float radius_x, float radius_y,
                          float radius_z, Color color)
{
    rlPushMatrix();
    rlTranslatef(position.x, position.y, position.z);
    rlScalef(radius_x, radius_y, radius_z);
    DrawSphere((Vector3){0.0f, 0.0f, 0.0f}, 1.0f, color);
    rlPopMatrix();
}

static void DrawLimb(Vector3 start, Vector3 end, float radius_start,
                     float radius_end, Color color)
{
    DrawCylinderEx(start, end, radius_start, radius_end, 10, color);
    DrawSphere(start, radius_start, color);
    DrawSphere(end, radius_end, color);
}

static void DrawGuard(const GuardEntity *guard, float time,
                      float player_x, float player_z)
{
    const float x = guard->x + sinf(time * 0.5f + guard->phase) * 0.38f;
    const float z = guard->z + cosf(time * 0.42f + guard->phase) * 0.3f;
    const float dx = player_x - x;
    const float dz = player_z - z;
    const float distance = sqrtf(dx * dx + dz * dz);
    const float yaw = distance > 0.001f ? atan2f(dx, dz) : 0.0f;
    const Vector3 root = {x, 0.0f, z};
    const Vector3 forward = {sinf(yaw), 0.0f, cosf(yaw)};
    const Vector3 right = {cosf(yaw), 0.0f, -sinf(yaw)};
    const float stride = sinf(time * 4.7f + guard->phase) * 0.13f;
    const Color uniforms[] = {
        {69, 83, 75, 255}, {65, 78, 84, 255}, {88, 87, 68, 255},
        {65, 70, 77, 255}, {78, 88, 79, 255}, {82, 74, 65, 255}
    };
    const Color skin_tones[] = {
        {197, 155, 122, 255}, {164, 119, 91, 255}, {213, 175, 145, 255},
        {143, 103, 82, 255}, {185, 136, 103, 255}, {204, 163, 132, 255}
    };
    const Color uniform = uniforms[guard->type % 6];
    const Color skin = skin_tones[guard->type % 6];
    const Color cloth_shadow = (Color){34, 41, 41, 255};
    const Color armor = guard->type == 3 ? (Color){74, 83, 84, 255} :
                                           (Color){47, 57, 57, 255};
    const Color metal = (Color){125, 134, 128, 255};

    for (int side = -1; side <= 1; side += 2) {
        const float leg_stride = side * stride;
        const Vector3 hip = GuardPoint(root, right, forward, side * 0.14f,
                                       0.86f, 0.0f);
        const Vector3 knee = GuardPoint(root, right, forward, side * 0.16f,
                                        0.48f, leg_stride);
        const Vector3 ankle = GuardPoint(root, right, forward, side * 0.16f,
                                         0.14f, leg_stride * 1.4f);
        DrawLimb(hip, knee, 0.135f, 0.105f, uniform);
        DrawLimb(knee, ankle, 0.105f, 0.08f, cloth_shadow);
        DrawEllipsoid(GuardPoint(ankle, right, forward, 0.0f, -0.055f,
                                 0.09f + leg_stride),
                      0.12f, 0.075f, 0.21f, (Color){30, 35, 36, 255});

        const Vector3 shoulder = GuardPoint(root, right, forward, side * 0.32f,
                                            1.43f, 0.0f);
        const Vector3 elbow = GuardPoint(root, right, forward, side * 0.38f,
                                         1.2f, 0.08f);
        const Vector3 wrist = GuardPoint(root, right, forward, side * 0.17f,
                                         1.04f, 0.22f);
        DrawEllipsoid(shoulder, 0.14f, 0.17f, 0.145f, uniform);
        DrawLimb(shoulder, elbow, 0.105f, 0.085f, uniform);
        DrawLimb(elbow, wrist, 0.085f, 0.07f, uniform);
        DrawEllipsoid(GuardPoint(wrist, right, forward, 0.0f, -0.015f, 0.025f),
                      0.07f, 0.075f, 0.08f, cloth_shadow);
    }

    DrawEllipsoid(GuardPoint(root, right, forward, 0.0f, 1.18f, 0.0f),
                  0.31f, 0.37f, 0.205f, uniform);
    DrawEllipsoid(GuardPoint(root, right, forward, 0.0f, 1.18f, 0.145f),
                  0.235f, 0.29f, 0.085f, armor);
    DrawEllipsoid(GuardPoint(root, right, forward, 0.0f, 0.91f, 0.03f),
                  0.285f, 0.105f, 0.205f, cloth_shadow);
    DrawEllipsoid(GuardPoint(root, right, forward, 0.0f, 0.925f, 0.18f),
                  0.032f, 0.05f, 0.02f, metal);

    for (int side = -1; side <= 1; side += 2) {
        DrawEllipsoid(GuardPoint(root, right, forward, side * 0.19f, 1.21f, 0.21f),
                      0.07f, 0.095f, 0.045f, cloth_shadow);
    }
    DrawLimb(GuardPoint(root, right, forward, -0.045f, 1.34f, 0.205f),
             GuardPoint(root, right, forward, 0.05f, 1.47f, 0.21f),
             0.042f, 0.048f, cloth_shadow);
    DrawLimb(GuardPoint(root, right, forward, 0.045f, 1.34f, 0.205f),
             GuardPoint(root, right, forward, -0.05f, 1.47f, 0.21f),
             0.042f, 0.048f, cloth_shadow);

    DrawEllipsoid(GuardPoint(root, right, forward, 0.0f, 1.57f, 0.0f),
                  0.105f, 0.115f, 0.105f, skin);
    DrawEllipsoid(GuardPoint(root, right, forward, 0.0f, 1.76f, 0.015f),
                  0.15f, 0.19f, 0.145f, skin);
    for (int side = -1; side <= 1; side += 2) {
        DrawEllipsoid(GuardPoint(root, right, forward, side * 0.147f, 1.76f, 0.005f),
                      0.032f, 0.057f, 0.04f, skin);
        DrawEllipsoid(GuardPoint(root, right, forward, side * 0.058f, 1.785f, 0.128f),
                      0.016f, 0.015f, 0.012f, (Color){48, 43, 39, 255});
    }
    DrawEllipsoid(GuardPoint(root, right, forward, 0.0f, 1.728f, 0.145f),
                  0.025f, 0.033f, 0.026f, skin);
    DrawEllipsoid(GuardPoint(root, right, forward, 0.0f, 1.681f, 0.145f),
                  0.035f, 0.009f, 0.012f, (Color){91, 62, 54, 255});
    DrawEllipsoid(GuardPoint(root, right, forward, 0.0f, 1.91f, 0.005f),
                  0.15f, guard->type % 2 == 0 ? 0.065f : 0.045f,
                  0.15f, guard->type == 1 || guard->type == 4 ?
                  (Color){65, 73, 68, 255} : cloth_shadow);
    if (guard->type == 3 || guard->type == 5) {
        DrawEllipsoid(GuardPoint(root, right, forward, 0.0f, 1.965f, -0.005f),
                      0.17f, 0.075f, 0.16f, (Color){65, 75, 77, 255});
    }

    const Vector3 weapon_start = GuardPoint(root, right, forward, -0.12f, 1.12f, 0.3f);
    const Vector3 weapon_end = GuardPoint(root, right, forward, 0.34f, 1.2f, 0.25f);
    DrawCylinderEx(weapon_start, weapon_end, 0.043f, 0.04f, 8, cloth_shadow);
    DrawCylinderEx(weapon_end, GuardPoint(root, right, forward, 0.37f, 1.2f, 0.52f),
                   0.027f, 0.022f, 8, metal);
    DrawLimb(GuardPoint(root, right, forward, 0.0f, 1.1f, 0.3f),
             GuardPoint(root, right, forward, 0.12f, 1.04f, 0.34f),
             0.045f, 0.04f, (Color){44, 46, 43, 255});
}

static void DrawWeapon(const GameState *game,
                       const Texture2D weapons[GAME_WEAPON_COUNT], Texture2D arms,
                       int width, int height, bool enhanced)
{
    const Texture2D weapon = weapons[game->current_weapon];
    const float aim_scale = game->aiming ? 0.82f : 1.0f;
    const float weapon_width = fminf(enhanced ? 405.0f : 155.0f,
                                    fminf((float)width * 0.38f, (float)height * 0.56f)) *
                               aim_scale;
    const float weapon_height = weapon_width;
    const float recoil = game->shot_timer * 24.0f;
    const Rectangle destination = {
        game->aiming ? (float)width * 0.5f - weapon_width * 0.45f :
                       (float)width - weapon_width - 8.0f,
        game->aiming ? (float)height * 0.5f - weapon_height * 0.45f :
                       (float)height - weapon_height + (enhanced ? 34.0f : 14.0f) +
                           recoil,
        weapon_width, weapon_height
    };
    DrawTexturePro(arms, (Rectangle){0.0f, 0.0f, (float)arms.width,
                   (float)arms.height}, destination, (Vector2){0.0f, 0.0f}, 0.0f, WHITE);
    DrawTexturePro(weapon, (Rectangle){0.0f, 0.0f, (float)weapon.width,
                   (float)weapon.height}, destination, (Vector2){0.0f, 0.0f}, 0.0f, WHITE);
    if (game->shot_timer > 0.0f) {
        const float flash = game->shot_timer / 0.12f;
        DrawCircle((int)(destination.x + weapon_width * 0.94f),
                   (int)(destination.y + weapon_height * 0.34f),
                   enhanced ? 13.0f * flash : 5.0f * flash,
                   Fade((Color){255, 207, 117, 255}, flash));
    }
}

static void DrawHud(const GameState *game,
                    const Texture2D weapons[GAME_WEAPON_COUNT], Texture2D arms,
                    int width, int height, bool enhanced)
{
    const int font = enhanced ? 18 : 9;
    const int panel_width = enhanced ? 450 : 225;
    const int panel_height = enhanced ? 145 : 73;
    DrawRectangle(16, 16, panel_width, panel_height, Fade((Color){5, 12, 17, 255}, 0.86f));
    DrawRectangle(16, 16, 4, panel_height, (Color){65, 217, 203, 255});
    DrawText("GLASS HARBOR  //  OPERATION 01", 30, 24, font,
             (Color){104, 222, 214, 255});
    DrawText(game->has_data_core ? "OBJECTIVE: REACH EXTRACTION" :
                                  "OBJECTIVE: RECOVER DATA CORE",
             30, enhanced ? 51 : 40, font - 2, RAYWHITE);
    DrawText(TextFormat("HOSTILES  %02d", GameActiveGuards(game)),
             30, enhanced ? 78 : 51, font - 2, (Color){240, 184, 108, 255});
    const char *weapon_name = game->current_weapon == GAME_CARBINE ?
                              "PULSE CARBINE" : "FIELD SIDEARM";
    DrawText(TextFormat("%s   %02d / %02d", weapon_name,
                        game->ammo[game->current_weapon],
                        game->reserve_ammo[game->current_weapon]),
             30, enhanced ? 105 : 60, font - 2, RAYWHITE);
    if (game->reload_timer > 0.0f) {
        DrawText("RELOADING", enhanced ? 333 : 166, enhanced ? 105 : 60,
                 font - 2, (Color){240, 184, 108, 255});
    }

    const int health_x = enhanced ? 24 : 12;
    const int health_y = height - (enhanced ? 43 : 23);
    const int bar_width = enhanced ? 245 : 104;
    DrawRectangle(health_x, health_y, bar_width, enhanced ? 16 : 8,
                  Fade((Color){10, 14, 18, 255}, 0.88f));
    DrawRectangle(health_x, health_y, (int)((float)bar_width * game->health / 100.0f),
                  enhanced ? 16 : 8, game->health > 30.0f ?
                  (Color){70, 212, 156, 255} : (Color){229, 69, 61, 255});
    DrawText(TextFormat("HEALTH %03d", (int)game->health), health_x,
             health_y - (enhanced ? 24 : 13), font - 2, RAYWHITE);

    const int center_x = width / 2;
    const int center_y = height / 2;
    const int base_reticle = enhanced ? 10 : 4;
    const int reticle = base_reticle + (int)(game->shot_timer * (enhanced ? 60.0f : 20.0f));
    const int gap = game->aiming ? (enhanced ? 2 : 1) : (enhanced ? 3 : 2);
    const Color reticle_color = game->hit_marker_timer > 0.0f ?
                                (Color){105, 232, 165, 255} : RAYWHITE;
    DrawLine(center_x - reticle, center_y, center_x - gap, center_y, reticle_color);
    DrawLine(center_x + gap, center_y, center_x + reticle, center_y, reticle_color);
    DrawLine(center_x, center_y - reticle, center_x, center_y - gap, reticle_color);
    DrawLine(center_x, center_y + gap, center_x, center_y + reticle, reticle_color);
    if (game->hit_marker_timer > 0.0f) {
        const int hit_size = enhanced ? 7 : 3;
        DrawLine(center_x - hit_size, center_y - hit_size,
                 center_x - 2, center_y - 2, reticle_color);
        DrawLine(center_x + 2, center_y + 2,
                 center_x + hit_size, center_y + hit_size, reticle_color);
        DrawLine(center_x - hit_size, center_y + hit_size,
                 center_x - 2, center_y + 2, reticle_color);
        DrawLine(center_x + 2, center_y - 2,
                 center_x + hit_size, center_y - hit_size, reticle_color);
    }
    DrawWeapon(game, weapons, arms, width, height, enhanced);

    if (enhanced) {
        DrawText("WASD MOVE  RMB AIM  LMB FIRE  R RELOAD  Q SWITCH  E USE  F2 MODE",
                 145, height - 31, 16, (Color){222, 229, 224, 255});
    } else {
        DrawText("WASD MOVE RMB AIM LMB FIRE R LOAD Q SWAP E USE",
                 20, height - 13, 8, RAYWHITE);
    }

    if (game->damage_flash_timer > 0.0f) {
        DrawRectangle(0, 0, width, height,
                      Fade((Color){210, 40, 35, 255}, game->damage_flash_timer * 0.55f));
    }

    if (game->health <= 0.0f || game->mission_complete) {
        const char *message = game->health <= 0.0f ? "MISSION FAILED" :
                                                     "DATA SECURED  /  MISSION COMPLETE";
        DrawRectangle(0, height / 2 - 38, width, 76, Fade(BLACK, 0.84f));
        DrawText(message, width / 2 - MeasureText(message, enhanced ? 26 : 13) / 2,
                 height / 2 - (enhanced ? 13 : 7), enhanced ? 26 : 13,
                 game->mission_complete ? (Color){105, 232, 207, 255} : RED);
    }
}

static void DrawGame(const GameState *game,
                     const Texture2D weapons[GAME_WEAPON_COUNT], Texture2D arms,
                     int width, int height, bool enhanced)
{
    ClearBackground((Color){22, 35, 47, 255});
    const float horizontal = cosf(game->pitch);
    const Vector3 direction = {sinf(game->yaw) * horizontal, sinf(game->pitch),
                               cosf(game->yaw) * horizontal};
    Camera3D camera = {0};
    camera.position = (Vector3){game->position[0], game->position[1], game->position[2]};
    camera.target = (Vector3){camera.position.x + direction.x,
                              camera.position.y + direction.y,
                              camera.position.z + direction.z};
    camera.up = (Vector3){0.0f, 1.0f, 0.0f};
    camera.fovy = game->aiming ? 52.0f : (enhanced ? 72.0f : 75.0f);
    camera.projection = CAMERA_PERSPECTIVE;

    BeginMode3D(camera);
    DrawHarbor(game, enhanced);
    for (int i = 0; i < GAME_GUARD_COUNT; ++i) {
        const GuardEntity *guard = &game->guards[i];
        if (!guard->active) continue;
        DrawGuard(guard, game->match_time, game->position[0], game->position[2]);
    }
    EndMode3D();
    DrawHud(game, weapons, arms, width, height, enhanced);

    const float pickup_dx = game->position[0] - GAME_CARBINE_X;
    const float pickup_dz = game->position[2] - GAME_CARBINE_Z;
    const float pickup_distance = pickup_dx * pickup_dx + pickup_dz * pickup_dz;
    const float objective_x = game->has_data_core ? 9.0f : 7.0f;
    const float objective_z = game->has_data_core ? -9.0f : -7.0f;
    const float objective_dx = game->position[0] - objective_x;
    const float objective_dz = game->position[2] - objective_z;
    const float objective_distance = objective_dx * objective_dx +
                                     objective_dz * objective_dz;
    if (game->pickup_feedback_timer > 0.0f) {
        const char *message = "PULSE CARBINE ACQUIRED";
        DrawText(message, width / 2 - MeasureText(message, enhanced ? 20 : 10) / 2,
                 height - (enhanced ? 112 : 60), enhanced ? 20 : 10,
                 Fade((Color){102, 228, 217, 255},
                      fminf(1.0f, game->pickup_feedback_timer)));
    }
    if (!game->has_carbine && pickup_distance < 1.8f * 1.8f) {
        const char *prompt = "PRESS E TO TAKE PULSE CARBINE";
        DrawText(prompt, width / 2 - MeasureText(prompt, enhanced ? 20 : 10) / 2,
                 height - (enhanced ? 78 : 42), enhanced ? 20 : 10,
                 (Color){102, 228, 217, 255});
    } else if (!game->mission_complete && objective_distance < 2.1f * 2.1f) {
        const char *prompt = game->has_data_core ? "PRESS E TO EXTRACT" :
                                                  "PRESS E TO RECOVER CORE";
        DrawText(prompt, width / 2 - MeasureText(prompt, enhanced ? 20 : 10) / 2,
                 height - (enhanced ? 78 : 42), enhanced ? 20 : 10,
                 (Color){102, 228, 217, 255});
    }
}

int main(void)
{
    SetConfigFlags(FLAG_MSAA_4X_HINT);
    InitWindow(WINDOW_WIDTH, WINDOW_HEIGHT, "Glass Harbor");
    SetTargetFPS(60);
    RenderTexture2D legacy_canvas = LoadRenderTexture(320, 240);
    if (legacy_canvas.id == 0) {
        TraceLog(LOG_ERROR, "Could not create the 320x240 legacy render target.");
        CloseWindow();
        return 1;
    }
    SetTextureFilter(legacy_canvas.texture, TEXTURE_FILTER_POINT);

    Texture2D weapons[GAME_WEAPON_COUNT] = {0};
    Texture2D arms = {0};
    Sound sounds[4] = {0};
    bool sound_loaded[4] = {false, false, false, false};
    InitAudioDevice();
    const bool audio_ready = IsAudioDeviceReady();
    if (!audio_ready) {
        TraceLog(LOG_WARNING, "Audio is unavailable; continuing without sound effects.");
    } else {
        for (int i = 0; i < 4; ++i) {
            sounds[i] = LoadSound(SoundAssetPaths[i]);
            sound_loaded[i] = sounds[i].frameCount > 0;
            if (!sound_loaded[i]) {
                TraceLog(LOG_WARNING, "Could not load sound effect: %s", SoundAssetPaths[i]);
            }
        }
    }

    bool assets_ok = true;
    for (int i = 0; i < GAME_WEAPON_COUNT; ++i) {
        weapons[i] = LoadTexture(WeaponAssetPaths[i]);
        if (weapons[i].id == 0) {
            TraceLog(LOG_ERROR, "Could not load weapon sprite: %s", WeaponAssetPaths[i]);
            assets_ok = false;
        } else {
            SetTextureFilter(weapons[i], TEXTURE_FILTER_BILINEAR);
        }
    }
    arms = LoadTexture("assets/characters/field_agent_arms.png");
    if (arms.id == 0) {
        TraceLog(LOG_ERROR, "Could not load first-person arm sprite.");
        assets_ok = false;
    }
    if (!assets_ok) {
        for (int i = 0; i < GAME_WEAPON_COUNT; ++i) {
            if (weapons[i].id != 0) UnloadTexture(weapons[i]);
        }
        if (arms.id != 0) UnloadTexture(arms);
        for (int i = 0; i < 4; ++i) {
            if (sound_loaded[i]) UnloadSound(sounds[i]);
        }
        if (audio_ready) CloseAudioDevice();
        UnloadRenderTexture(legacy_canvas);
        CloseWindow();
        return 1;
    }

    GameState game;
    GameInit(&game);
    bool enhanced = true;
    DisableCursor();
    while (!WindowShouldClose()) {
        if (IsKeyPressed(KEY_F2)) enhanced = !enhanced;
        GameInput input = {0};
        input.move_x = (float)((IsKeyDown(KEY_D) ? 1 : 0) - (IsKeyDown(KEY_A) ? 1 : 0));
        input.move_y = (float)((IsKeyDown(KEY_W) ? 1 : 0) - (IsKeyDown(KEY_S) ? 1 : 0));
        const Vector2 mouse = GetMouseDelta();
        input.aim = IsMouseButtonDown(MOUSE_BUTTON_RIGHT);
        const float sensitivity = input.aim ? 0.0014f : 0.0025f;
        input.look_x = mouse.x * sensitivity;
        input.look_y = -mouse.y * sensitivity;
        input.fire = IsMouseButtonDown(MOUSE_BUTTON_LEFT) || IsKeyDown(KEY_SPACE);
        input.interact = IsKeyPressed(KEY_E);
        input.sprint = IsKeyDown(KEY_LEFT_SHIFT);
        input.reload = IsKeyPressed(KEY_R);
        input.switch_weapon = IsKeyPressed(KEY_Q);
        GameUpdate(&game, input, GetFrameTime());

        if (game.shot_event && sound_loaded[game.current_weapon]) {
            PlaySound(sounds[game.current_weapon]);
        }
        if (game.pickup_event && sound_loaded[2]) PlaySound(sounds[2]);
        if (game.reload_event && sound_loaded[3]) PlaySound(sounds[3]);

        if (enhanced) {
            BeginDrawing();
            DrawGame(&game, weapons, arms,
                     GetScreenWidth(), GetScreenHeight(), true);
            EndDrawing();
        } else {
            BeginTextureMode(legacy_canvas);
            DrawGame(&game, weapons, arms, 320, 240, false);
            EndTextureMode();

            const float scale = fminf((float)GetScreenWidth() / 320.0f,
                                      (float)GetScreenHeight() / 240.0f);
            const float output_width = 320.0f * scale;
            const float output_height = 240.0f * scale;
            BeginDrawing();
            ClearBackground(BLACK);
            DrawTexturePro(legacy_canvas.texture,
                           (Rectangle){0.0f, 0.0f, 320.0f, -240.0f},
                           (Rectangle){((float)GetScreenWidth() - output_width) * 0.5f,
                                       ((float)GetScreenHeight() - output_height) * 0.5f,
                                       output_width, output_height},
                           (Vector2){0.0f, 0.0f}, 0.0f, WHITE);
            EndDrawing();
        }
    }

    EnableCursor();
    for (int i = 0; i < GAME_WEAPON_COUNT; ++i) UnloadTexture(weapons[i]);
    UnloadTexture(arms);
    for (int i = 0; i < 4; ++i) {
        if (sound_loaded[i]) UnloadSound(sounds[i]);
    }
    if (audio_ready) CloseAudioDevice();
    UnloadRenderTexture(legacy_canvas);
    CloseWindow();
    return 0;
}

#elif defined(PLATFORM_N64)

static void N64Color(float red, float green, float blue)
{
    glColor3f(red, green, blue);
}

static void N64Box(float x, float y, float z, float width, float height, float depth,
                   float red, float green, float blue)
{
    const float x0 = x - width * 0.5f, x1 = x + width * 0.5f;
    const float y0 = y - height * 0.5f, y1 = y + height * 0.5f;
    const float z0 = z - depth * 0.5f, z1 = z + depth * 0.5f;
    N64Color(red, green, blue);
    glBegin(GL_QUADS);
    glVertex3f(x0,y0,z0); glVertex3f(x1,y0,z0); glVertex3f(x1,y1,z0); glVertex3f(x0,y1,z0);
    glVertex3f(x0,y0,z1); glVertex3f(x0,y1,z1); glVertex3f(x1,y1,z1); glVertex3f(x1,y0,z1);
    glVertex3f(x0,y0,z0); glVertex3f(x0,y1,z0); glVertex3f(x0,y1,z1); glVertex3f(x0,y0,z1);
    glVertex3f(x1,y0,z0); glVertex3f(x1,y0,z1); glVertex3f(x1,y1,z1); glVertex3f(x1,y1,z0);
    glVertex3f(x0,y1,z0); glVertex3f(x1,y1,z0); glVertex3f(x1,y1,z1); glVertex3f(x0,y1,z1);
    glVertex3f(x0,y0,z0); glVertex3f(x0,y0,z1); glVertex3f(x1,y0,z1); glVertex3f(x1,y0,z0);
    glEnd();
}

static void N64DrawScene(const GameState *game)
{
    const float horizontal = cosf(game->pitch);
    const float forward_x = sinf(game->yaw) * horizontal;
    const float forward_y = sinf(game->pitch);
    const float forward_z = cosf(game->yaw) * horizontal;
    const float eye_x = game->position[0], eye_y = game->position[1], eye_z = game->position[2];
    glMatrixMode(GL_PROJECTION);
    glLoadIdentity();
    glFrustum(-0.58, 0.58, -0.435, 0.435, 1.0, 45.0);
    glMatrixMode(GL_MODELVIEW);
    glLoadIdentity();
    glRotatef(-game->yaw * 180.0f / GH_PI, 0.0f, 1.0f, 0.0f);
    glRotatef(-game->pitch * 180.0f / GH_PI, 1.0f, 0.0f, 0.0f);
    glTranslatef(-eye_x, -eye_y, -eye_z);
    glClearColor(0.07f, 0.14f, 0.17f, 1.0f);
    glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT);
    glEnable(GL_DEPTH_TEST);
    N64Box(0.0f, -0.15f, 0.0f, 24.0f, 0.3f, 24.0f, 0.18f, 0.23f, 0.22f);
    for (int i = 0; i < GAME_WALL_COUNT; ++i) {
        const GameWall *wall = &GameWalls[i];
        N64Box(wall->x, wall->height * 0.5f, wall->z, wall->width, wall->height,
               wall->depth, 0.28f, 0.34f, 0.36f);
    }
    for (int i = 0; i < GAME_GUARD_COUNT; ++i) {
        const GuardEntity *guard = &game->guards[i];
        if (!guard->active) continue;
        N64Box(guard->x, 1.0f, guard->z, 0.62f, 1.4f, 0.38f,
               guard->type % 2 ? 0.48f : 0.18f, 0.2f, 0.17f);
        N64Box(guard->x, 1.88f, guard->z, 0.34f, 0.34f, 0.34f,
               0.68f, 0.48f, 0.36f);
    }
    if (!game->has_data_core) {
        N64Box(7.0f, 0.38f, -7.0f, 0.75f, 0.75f, 0.75f, 0.15f, 0.8f, 0.76f);
    }
    N64Box(9.0f, 0.04f, -9.0f, 1.4f, 0.08f, 1.4f,
           game->has_data_core ? 0.16f : 0.32f, 0.7f, 0.45f);
    if (!game->has_carbine) {
        N64Box(GAME_CARBINE_X, 0.58f, GAME_CARBINE_Z, 0.9f, 0.18f, 0.3f,
               0.3f, 0.72f, 0.68f);
    }

    glPushMatrix();
    glLoadIdentity();
    if (game->current_weapon == GAME_CARBINE) {
        N64Box(0.42f, -0.34f, -1.15f, 0.2f, 0.16f, 0.78f,
               0.3f, 0.38f, 0.4f);
        N64Box(0.42f, -0.46f, -1.02f, 0.15f, 0.28f, 0.18f,
               0.18f, 0.21f, 0.2f);
    } else {
        N64Box(0.4f, -0.36f, -1.05f, 0.2f, 0.15f, 0.48f,
               0.34f, 0.4f, 0.42f);
    }
    glPopMatrix();
}

static void N64Hud(const GameState *game)
{
    glDisable(GL_DEPTH_TEST);
    glMatrixMode(GL_PROJECTION);
    glPushMatrix();
    glLoadIdentity();
    glOrtho(0.0, 320.0, 240.0, 0.0, -1.0, 1.0);
    glMatrixMode(GL_MODELVIEW);
    glPushMatrix();
    glLoadIdentity();
    N64Color(0.9f, 0.94f, 0.9f);
    glBegin(GL_LINES);
    glVertex2f(153.0f, 120.0f); glVertex2f(158.0f, 120.0f);
    glVertex2f(162.0f, 120.0f); glVertex2f(167.0f, 120.0f);
    glVertex2f(160.0f, 113.0f); glVertex2f(160.0f, 117.0f);
    glVertex2f(160.0f, 123.0f); glVertex2f(160.0f, 127.0f);
    glEnd();
    N64Color(0.12f, 0.84f, 0.63f);
    glBegin(GL_QUADS);
    glVertex2f(12.0f, 222.0f); glVertex2f(112.0f, 222.0f);
    glVertex2f(112.0f, 230.0f); glVertex2f(12.0f, 230.0f);
    glVertex2f(12.0f, 222.0f); glVertex2f(12.0f + game->health, 222.0f);
    glVertex2f(12.0f + game->health, 230.0f); glVertex2f(12.0f, 230.0f);
    glEnd();
    const int magazine_size = game->current_weapon == GAME_CARBINE ? 24 : 12;
    const int ammo_width = game->ammo[game->current_weapon] * 100 / magazine_size;
    N64Color(game->current_weapon == GAME_CARBINE ? 0.35f : 0.85f,
             game->current_weapon == GAME_CARBINE ? 0.8f : 0.67f, 0.55f);
    glBegin(GL_QUADS);
    glVertex2f(208.0f, 222.0f); glVertex2f(308.0f, 222.0f);
    glVertex2f(308.0f, 230.0f); glVertex2f(208.0f, 230.0f);
    glVertex2f(208.0f, 222.0f); glVertex2f(208.0f + (float)ammo_width, 222.0f);
    glVertex2f(208.0f + (float)ammo_width, 230.0f); glVertex2f(208.0f, 230.0f);
    glEnd();
    glPopMatrix();
    glMatrixMode(GL_PROJECTION);
    glPopMatrix();
    glMatrixMode(GL_MODELVIEW);
    glEnable(GL_DEPTH_TEST);
}

int main(void)
{
    dfs_init(DFS_DEFAULT_LOCATION);
    display_init(RESOLUTION_320x240, DEPTH_16_BPP, 2, GAMMA_NONE, ANTIALIAS_RESAMPLE);
    gl_init();
    joypad_init();
    GameState game;
    GameInit(&game);
    for (;;) {
        joypad_poll();
        const joypad_buttons_t buttons = joypad_get_buttons(JOYPAD_PORT_1);
        const joypad_buttons_t pressed = joypad_get_buttons_pressed(JOYPAD_PORT_1);
        const int stick_x = joypad_get_axis(JOYPAD_PORT_1, JOYPAD_AXIS_STICK_X);
        const int stick_y = joypad_get_axis(JOYPAD_PORT_1, JOYPAD_AXIS_STICK_Y);
        GameInput input = {0};
        input.move_x = (float)stick_x / 85.0f;
        input.move_y = (float)stick_y / 85.0f;
        input.look_x = ((buttons.c_right ? 1.0f : 0.0f) -
                        (buttons.c_left ? 1.0f : 0.0f)) * 0.035f;
        input.look_y = ((buttons.c_up ? 1.0f : 0.0f) -
                        (buttons.c_down ? 1.0f : 0.0f)) * 0.025f;
        input.fire = pressed.a;
        input.interact = pressed.b;
        input.sprint = buttons.z;
        input.aim = buttons.l;
        input.reload = pressed.l;
        input.switch_weapon = pressed.r;
        GameUpdate(&game, input, 1.0f / 60.0f);
        surface_t *display = display_lock();
        if (display) {
            rdpq_attach(display, NULL);
            gl_context_begin();
            N64DrawScene(&game);
            N64Hud(&game);
            gl_context_end();
            rdpq_detach_show();
        }
    }
    return 0;
}

#endif

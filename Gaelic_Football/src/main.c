#include "game.h"

#include "audio.h"
#include "player_model.h"
#include "raylib.h"
#include "rlgl.h"

#include <math.h>

#if !defined(PLATFORM_RAYLIB)
#error "Compile main.c with the PLATFORM_RAYLIB frontend."
#endif

#define SCREEN_WIDTH 1280
#define SCREEN_HEIGHT 720
#define VIRTUAL_WIDTH 960
#define VIRTUAL_HEIGHT 540
#define FRAME_SCALE 2
#define FRAME_WIDTH (VIRTUAL_WIDTH * FRAME_SCALE)
#define FRAME_HEIGHT (VIRTUAL_HEIGHT * FRAME_SCALE)
#define AUTHENTIC_WIDTH 320
#define AUTHENTIC_HEIGHT 240
#define STAND_FAN_ROWS 4
#define STAND_FAN_COLUMNS 20

static const Color PITCH_GREEN = {34, 99, 43, 255};
static const Color LINE_WHITE = {235, 238, 220, 255};
static const Color BALL_BROWN = {145, 74, 35, 255};
static const Color TEAM_COLORS[GAME_TEAM_COUNT] = {
    {45, 102, 205, 255},
    {194, 47, 42, 255},
    {35, 137, 74, 255},
    {232, 190, 42, 255}
};
static PlayerModels player_models;
static RenderTexture2D authentic_frame;
static Texture2D grass_texture;
static Model grass_model;
static int authentic_view;
static int grass_model_valid;
static int render_width = FRAME_WIDTH;
static int render_height = FRAME_HEIGHT;
static const char *const AUTHENTIC_PLAYER_NAMES[GAME_TEAM_SIZE] = {
    "O KELLY", "D MURPHY", "A BYRNE", "C WALSH", "R DOYLE",
    "T RYAN", "J NOLAN", "E CONNOLLY", "P KAVANAGH", "M KEANE",
    "S OBRIEN", "F LYNCH", "B POWER", "N ROCHE", "L HAYES"
};
static const Color CROWD_COLORS[8] = {
    {225, 225, 208, 255}, {205, 55, 48, 255}, {48, 104, 214, 255},
    {223, 183, 56, 255}, {58, 157, 85, 255}, {220, 119, 47, 255},
    {126, 73, 170, 255}, {49, 53, 64, 255}
};

static Vector2 screen_to_virtual(Vector2 point)
{
    int output_width = authentic_view ? AUTHENTIC_WIDTH : VIRTUAL_WIDTH;
    int output_height = authentic_view ? AUTHENTIC_HEIGHT : VIRTUAL_HEIGHT;
    float scale = fminf((float)GetScreenWidth() / (float)output_width,
                        (float)GetScreenHeight() / (float)output_height);
    float offset_x = ((float)GetScreenWidth() - (float)output_width * scale) * 0.5f;
    float offset_y = ((float)GetScreenHeight() - (float)output_height * scale) * 0.5f;
    Vector2 virtual_point = {
        (point.x - offset_x) / scale * (float)VIRTUAL_WIDTH /
            (float)output_width,
        (point.y - offset_y) / scale * (float)VIRTUAL_HEIGHT /
            (float)output_height
    };
    return virtual_point;
}

static void draw_retro_text(const char *text, int x, int y, int size, Color color)
{
    DrawText(text, x + 2, y + 2, size, (Color){10, 16, 22, 210});
    DrawText(text, x, y, size, color);
}

static void draw_frame_to_screen(RenderTexture2D frame, int width, int height)
{
    float scale = fminf((float)GetScreenWidth() / (float)width,
                        (float)GetScreenHeight() / (float)height);
    Rectangle source = {0.0f, 0.0f, (float)width, -(float)height};
    Rectangle destination = {
        ((float)GetScreenWidth() - (float)width * scale) * 0.5f,
        ((float)GetScreenHeight() - (float)height * scale) * 0.5f,
        (float)width * scale,
        (float)height * scale
    };
    DrawTexturePro(frame.texture, source, destination, (Vector2){0.0f, 0.0f},
                   0.0f, WHITE);
}

static void draw_authentic_hud(const GameState *game, float elapsed,
                               int menu_active, int home_team, int away_team,
                               int starting_player, int show_touch_controls)
{
    const Color panel = {12, 16, 22, 238};
    int selected_opponent = 0;
    int i;

    DrawRectangle(8, 8, 120, 22, panel);
    DrawRectangle(8, 8, 3, 22, TEAM_COLORS[game->home_team]);
    DrawRectangle(125, 8, 3, 22, TEAM_COLORS[game->away_team]);
    DrawRectangle(16, 12, 13, 11, TEAM_COLORS[game->home_team]);
    DrawRectangle(107, 12, 13, 11, TEAM_COLORS[game->away_team]);
    DrawText(TextFormat("%d-%02d", game->team_goals[0], game->team_points[0]),
             33, 13, 10, (Color){255, 236, 182, 255});
    DrawText("-", 72, 13, 10, (Color){215, 221, 213, 255});
    DrawText(TextFormat("%d-%02d", game->team_goals[1], game->team_points[1]),
             81, 13, 10, (Color){255, 236, 182, 255});

    DrawCircle(290, 20, 14, (Color){10, 20, 30, 235});
    DrawCircle(290, 20, 11, (Color){36, 178, 69, 255});
    DrawCircleLines(290, 20, 14, (Color){238, 216, 95, 255});
    DrawText("1ST", 279, 16, 9, RAYWHITE);
    DrawRectangle(240, 10, 36, 19, panel);
    DrawText(TextFormat("%02d:%02d", (int)(elapsed * 3.0f) / 60,
                        (int)(elapsed * 3.0f) % 60),
             244, 15, 8, RAYWHITE);

    if (!menu_active) {
        float nearest = 1000000.0f;
        for (i = 0; i < GAME_TEAM_SIZE; i++) {
            const GamePlayer *opponent = &game->players[1][i];
            float dx = opponent->x - game->ball.x;
            float dz = opponent->z - game->ball.z;
            float distance = dx * dx + dz * dz;
            if (distance < nearest) {
                nearest = distance;
                selected_opponent = i;
            }
        }
        DrawRectangle(7, 207, 96, 27, panel);
        DrawRectangle(7, 207, 3, 27, TEAM_COLORS[game->home_team]);
        DrawRectangle(217, 207, 96, 27, panel);
        DrawRectangle(310, 207, 3, 27, TEAM_COLORS[game->away_team]);
        DrawRectangle(8, 208, 95, 2, (Color){115, 119, 120, 255});
        DrawRectangle(217, 208, 95, 2, (Color){115, 119, 120, 255});
        DrawText(TextFormat("%s %02d", game_player_role(game->selected_player),
                            game->selected_player + 1),
                 14, 211, 8, (Color){237, 195, 65, 255});
        DrawText(AUTHENTIC_PLAYER_NAMES[game->selected_player], 14, 222, 9,
                 RAYWHITE);
        DrawText(TextFormat("%s %02d", game_player_role(selected_opponent),
                            selected_opponent + 1),
                 224, 211, 8, (Color){237, 195, 65, 255});
        DrawText(AUTHENTIC_PLAYER_NAMES[selected_opponent], 224, 222, 9,
                 RAYWHITE);
        DrawRectangle(130, 200, 60, 36, (Color){9, 19, 16, 245});
        DrawRectangleLines(130, 200, 60, 36, (Color){218, 222, 209, 255});
        DrawLine(160, 202, 160, 234, (Color){218, 222, 209, 210});
        for (i = 0; i < GAME_TEAM_SIZE; i++) {
            int team;
            for (team = 0; team < 2; team++) {
                const GamePlayer *member = &game->players[team][i];
                int px = 132 + (int)(member->x / GAME_PITCH_LENGTH * 56.0f);
                int py = 202 + (int)(member->z / GAME_PITCH_WIDTH * 32.0f);
                DrawPixel(px, py, TEAM_COLORS[team == 0 ?
                                               game->home_team : game->away_team]);
            }
        }
        DrawPixel(132 + (int)(game->ball.x / GAME_PITCH_LENGTH * 56.0f),
                  202 + (int)(game->ball.z / GAME_PITCH_WIDTH * 32.0f), GOLD);
        if (show_touch_controls) {
            DrawCircleLines(30, 180, 22, (Color){235, 238, 220, 180});
            DrawCircleLines(304, 180, 12, (Color){235, 238, 220, 200});
            DrawCircleLines(279, 180, 12, (Color){235, 238, 220, 200});
            DrawCircleLines(264, 180, 12, (Color){235, 238, 220, 200});
            DrawCircleLines(249, 180, 12, (Color){235, 238, 220, 200});
            DrawCircleLines(304, 142, 12, (Color){235, 238, 220, 200});
            DrawCircleLines(279, 142, 12, (Color){235, 238, 220, 200});
        }
    } else {
        DrawRectangle(38, 61, AUTHENTIC_WIDTH - 76, 117,
                      (Color){7, 14, 20, 228});
        DrawRectangle(38, 61, AUTHENTIC_WIDTH - 76, 2,
                      (Color){230, 183, 54, 255});
        DrawText("SUNDAY LEAGUE", 89, 69, 17, RAYWHITE);
        DrawText("ISS-STYLE MATCH", 94, 92, 10,
                 (Color){255, 220, 93, 255});
        DrawText(TextFormat("<  HOME  %s  >", game_team_name(home_team)),
                 53, 114, 9, RAYWHITE);
        DrawText(TextFormat("<  AWAY  %s  >", game_team_name(away_team)),
                 53, 130, 9, RAYWHITE);
        DrawText(TextFormat("PLAYER  %02d  %s", starting_player + 1,
                            game_player_role(starting_player)),
                 53, 145, 8, (Color){255, 220, 93, 255});
        DrawText("ENTER TO KICK OFF", 89, 163, 8, RAYWHITE);
    }
}

static void present_frame(RenderTexture2D frame, int width, int height)
{
    SetTextureFilter(frame.texture, authentic_view ?
                     TEXTURE_FILTER_POINT : TEXTURE_FILTER_BILINEAR);
    draw_frame_to_screen(frame, width, height);
}

static unsigned int pitch_noise(unsigned int x, unsigned int y)
{
    unsigned int value = x * 374761393u + y * 668265263u + 0x9e3779b9u;
    value = (value ^ (value >> 13)) * 1274126177u;
    return value ^ (value >> 16);
}

static int stadium_assets_init(void)
{
    const int texture_width = 2048;
    const int texture_height = 1024;
    Image image = GenImageColor(texture_width, texture_height, PITCH_GREEN);
    Color *pixels;
    Mesh mesh;
    int x;
    int z;

    if (image.data == NULL) {
        TraceLog(LOG_ERROR, "Could not allocate the procedural pitch texture.");
        return 0;
    }
    pixels = (Color *)image.data;
    for (z = 0; z < texture_height; z++) {
        float pitch_z = (float)z * GAME_PITCH_WIDTH /
                        (float)texture_height;
        int mowing_lane = (int)(pitch_z / 8.5f);
        int mowing_tone = mowing_lane % 2 == 0 ? 5 : -5;
        for (x = 0; x < texture_width; x++) {
            unsigned int coarse = pitch_noise((unsigned int)x >> 3,
                                              (unsigned int)z >> 3);
            unsigned int fine = pitch_noise((unsigned int)x,
                                            (unsigned int)z);
            int variation = (int)(coarse % 5u) - 2 +
                            (int)(fine % 3u) - 1;
            int green = 99 + mowing_tone + variation;
            Color *pixel = &pixels[z * texture_width + x];
            pixel->r = (unsigned char)(34 + variation / 3);
            pixel->g = (unsigned char)green;
            pixel->b = (unsigned char)(43 + variation / 3);
            pixel->a = 255;
        }
    }
    grass_texture = LoadTextureFromImage(image);
    UnloadImage(image);
    if (grass_texture.id == 0) {
        TraceLog(LOG_ERROR, "Could not upload the procedural pitch texture.");
        return 0;
    }
    SetTextureWrap(grass_texture, TEXTURE_WRAP_REPEAT);

    mesh = GenMeshPlane(GAME_PITCH_LENGTH, GAME_PITCH_WIDTH, 1, 1);
    if (mesh.texcoords == NULL) {
        TraceLog(LOG_ERROR, "Could not generate the textured pitch mesh.");
        UnloadMesh(mesh);
        UnloadTexture(grass_texture);
        grass_texture = (Texture2D){0};
        return 0;
    }
    UploadMesh(&mesh, false);
    grass_model = LoadModelFromMesh(mesh);
    if (!IsModelValid(grass_model)) {
        TraceLog(LOG_ERROR, "Could not create the textured pitch model.");
        UnloadTexture(grass_texture);
        grass_texture = (Texture2D){0};
        return 0;
    }
    grass_model.materials[0].maps[MATERIAL_MAP_DIFFUSE].texture = grass_texture;
    grass_model_valid = 1;
    return 1;
}

static Vector3 world_point(float x, float height, float z)
{
    Vector3 point = {x, height, z};
    return point;
}

static void draw_segment(float x1, float z1, float x2, float z2)
{
    DrawLine3D(world_point(x1, 0.035f, z1), world_point(x2, 0.035f, z2), LINE_WHITE);
}

static void draw_circle_line(float center_x, float center_z, float radius, int segments)
{
    int i;
    for (i = 0; i < segments; i++) {
        float a0 = (float)i * 6.2831853f / (float)segments;
        float a1 = (float)(i + 1) * 6.2831853f / (float)segments;
        draw_segment(center_x + cosf(a0) * radius, center_z + sinf(a0) * radius,
                     center_x + cosf(a1) * radius, center_z + sinf(a1) * radius);
    }
}

static void draw_pitch(void)
{
    float length = GAME_PITCH_LENGTH;
    float width = GAME_PITCH_WIDTH;
    float center_z = width * 0.5f;
    float goal_x[2] = {0.0f, length};
    int i;

    if (grass_model_valid) {
        DrawModel(grass_model, world_point(length * 0.5f, 0.0f, center_z),
                  1.0f, WHITE);
    } else {
        DrawCube(world_point(length * 0.5f, -0.28f, center_z),
                 length, 0.55f, width, PITCH_GREEN);
    }
    if (!authentic_view) {
        DrawCube(world_point(length * 0.5f, 0.35f, -3.2f),
                 length + 8.0f, 0.7f, 1.4f, (Color){76, 78, 82, 255});
        DrawCube(world_point(length * 0.5f, 0.35f, width + 3.2f),
                 length + 8.0f, 0.7f, 1.4f, (Color){76, 78, 82, 255});
    }
    draw_segment(0.0f, 0.0f, length, 0.0f);
    draw_segment(length, 0.0f, length, width);
    draw_segment(length, width, 0.0f, width);
    draw_segment(0.0f, width, 0.0f, 0.0f);
    draw_segment(length * 0.5f, 0.0f, length * 0.5f, width);
    draw_circle_line(length * 0.5f, center_z, 3.75f, 40);

    for (i = 0; i < 2; i++) {
        float direction = i == 0 ? 1.0f : -1.0f;
        float x13 = goal_x[i] + direction * 13.0f;
        float x20 = goal_x[i] + direction * 20.0f;
        float x45 = goal_x[i] + direction * 45.0f;
        draw_segment(x13, 0.0f, x13, width);
        draw_segment(x20, 0.0f, x20, width);
        draw_segment(x45, 0.0f, x45, width);
    }
}

static Color crowd_color(int row, int column)
{
    int index = (column * 3 + row * 5 + (column / 4)) % 8;
    return CROWD_COLORS[index];
}

static void draw_crowd_fan(float x, float y, float z, int row, int column)
{
    Color shirt = crowd_color(row, column);
    Color skin = (column % 3 == 0) ? (Color){211, 165, 122, 255} :
                                     (Color){232, 192, 153, 255};

    DrawCube(world_point(x, y + 0.55f, z), 0.86f, 0.85f, 0.55f, shirt);
    DrawSphere(world_point(x, y + 1.17f, z), 0.27f, skin);
    if ((row + column) % 5 == 0) {
        float cheer = sinf((float)column * 1.7f + (float)row * 2.1f);
        DrawCylinderEx(world_point(x - 0.36f, y + 0.8f, z),
                       world_point(x - 0.48f, y + 1.0f + cheer * 0.2f, z),
                       0.075f, 0.055f, 5, shirt);
        DrawCylinderEx(world_point(x + 0.36f, y + 0.8f, z),
                       world_point(x + 0.48f, y + 1.0f - cheer * 0.2f, z),
                       0.075f, 0.055f, 5, shirt);
    }
}

static void draw_side_stand(int far_side)
{
    int row;
    int column;
    float center_z = far_side ? GAME_PITCH_WIDTH + 14.0f : -14.0f;
    float direction = far_side ? 1.0f : -1.0f;

    DrawCube(world_point(GAME_PITCH_LENGTH * 0.5f, 4.7f, center_z),
             GAME_PITCH_LENGTH + 18.0f, 9.4f, 24.0f,
             (Color){73, 78, 87, 255});
    for (row = 0; row < STAND_FAN_ROWS; row++) {
        float fan_z = far_side ? GAME_PITCH_WIDTH + 6.0f + row * 2.6f :
                                 -6.0f - row * 2.6f;
        float fan_y = 1.8f + row * 1.35f;
        float seat_z = fan_z + direction * 1.25f;
        DrawCube(world_point(GAME_PITCH_LENGTH * 0.5f, fan_y, seat_z),
                 GAME_PITCH_LENGTH + 8.0f, 0.3f, 1.8f,
                 (row % 2) ? (Color){50, 56, 68, 255} :
                             (Color){60, 65, 76, 255});
        for (column = 0; column < STAND_FAN_COLUMNS; column++) {
            float fan_x = 3.0f + (float)column *
                          (GAME_PITCH_LENGTH - 6.0f) /
                          (float)(STAND_FAN_COLUMNS - 1);
            draw_crowd_fan(fan_x, fan_y + 0.2f, fan_z, row, column);
        }
    }

    for (column = 0; column < 6; column++) {
        float support_x = (float)column * GAME_PITCH_LENGTH / 5.0f;
        DrawCube(world_point(support_x, 7.0f, center_z + direction * 5.0f),
                 0.8f, 14.0f, 0.8f, (Color){96, 101, 108, 255});
    }
    DrawCube(world_point(GAME_PITCH_LENGTH * 0.5f, 13.0f,
                         center_z + direction * 8.5f),
             GAME_PITCH_LENGTH + 18.0f, 0.8f, 7.0f,
             (Color){52, 58, 71, 255});
    DrawCube(world_point(GAME_PITCH_LENGTH * 0.5f, 10.3f,
                         center_z + direction * 8.7f),
             GAME_PITCH_LENGTH + 8.0f, 0.6f, 0.7f,
             (Color){210, 44, 45, 255});
}

static void draw_end_stand(int far_end)
{
    int row;
    int column;
    float center_x = far_end ? GAME_PITCH_LENGTH + 13.0f : -13.0f;

    DrawCube(world_point(center_x, 4.3f, GAME_PITCH_WIDTH * 0.5f),
             23.0f, 8.6f, GAME_PITCH_WIDTH + 16.0f,
             (Color){68, 73, 83, 255});
    for (row = 0; row < 3; row++) {
        float fan_x = far_end ? GAME_PITCH_LENGTH + 5.0f + row * 2.8f :
                                -5.0f - row * 2.8f;
        float fan_y = 1.5f + row * 1.35f;
        for (column = 0; column < 12; column++) {
            float fan_z = 3.0f + (float)column *
                          (GAME_PITCH_WIDTH - 6.0f) / 11.0f;
            draw_crowd_fan(fan_x, fan_y, fan_z, row + 1, column + far_end * 4);
        }
    }
}

static void draw_ad_boards(void)
{
    int panel;
    for (panel = 0; panel < 35; panel++) {
        float x = (float)panel * 4.0f + 2.0f;
        Color color = (panel % 3 == 0) ? (Color){221, 190, 63, 255} :
                      (panel % 3 == 1) ? (Color){205, 53, 48, 255} :
                                         (Color){39, 92, 171, 255};
        DrawCube(world_point(x, 0.58f, -1.25f), 3.9f, 1.1f, 0.35f, color);
        DrawCube(world_point(x, 0.58f, GAME_PITCH_WIDTH + 1.25f),
                 3.9f, 1.1f, 0.35f, color);
    }
}

static void draw_authentic_stands(void)
{
    int panel;
    float length = GAME_PITCH_LENGTH;

    DrawCube(world_point(length * 0.5f, 3.1f, -4.2f),
             length + 20.0f, 6.2f, 5.0f, (Color){46, 49, 54, 255});
    DrawCube(world_point(length * 0.5f, 6.1f, -5.5f),
             length + 20.0f, 0.42f, 4.0f, (Color){71, 74, 78, 255});
    for (panel = 0; panel < 35; panel++) {
        float x = (float)panel * 4.0f + 2.0f;
        Color board = panel % 4 == 0 ? (Color){205, 37, 32, 255} :
                      panel % 4 == 1 ? (Color){232, 220, 181, 255} :
                      panel % 4 == 2 ? (Color){29, 74, 145, 255} :
                                       (Color){33, 36, 40, 255};
        DrawCube(world_point(x, 0.65f, -0.7f), 3.85f, 1.3f, 0.35f, board);
    }
    DrawCube(world_point(length * 0.5f, 4.8f, -1.5f),
             length + 10.0f, 0.18f, 0.3f, (Color){190, 35, 32, 255});
}

static void draw_floodlights(void)
{
    int end;
    int side;
    for (end = 0; end < 2; end++) {
        for (side = 0; side < 2; side++) {
            float x = end ? GAME_PITCH_LENGTH + 18.0f : -18.0f;
            float z = side ? GAME_PITCH_WIDTH + 25.0f : -25.0f;
            float sign_x = end ? -1.0f : 1.0f;
            int lamp;
            DrawCylinder(world_point(x, 10.0f, z), 0.42f, 0.24f, 20.0f,
                         6, (Color){104, 111, 115, 255});
            DrawCube(world_point(x + sign_x * 1.2f, 20.0f, z),
                     5.0f, 1.0f, 1.0f, (Color){95, 105, 112, 255});
            for (lamp = 0; lamp < 5; lamp++) {
                DrawCube(world_point(x + sign_x * (lamp - 2) * 0.75f, 19.9f,
                                     z + (side ? -0.35f : 0.35f)),
                         0.42f, 0.32f, 0.18f, (Color){255, 241, 180, 255});
            }
        }
    }
}

static void draw_stadium(void)
{
    int cloud;
    static const float cloud_positions[6][3] = {
        {-25.0f, 33.0f, 25.0f}, {18.0f, 36.0f, -34.0f},
        {70.0f, 34.0f, 130.0f}, {132.0f, 38.0f, -38.0f},
        {176.0f, 32.0f, 72.0f}, {58.0f, 39.0f, 98.0f}
    };

    DrawCube(world_point(GAME_PITCH_LENGTH * 0.5f, -0.8f,
                         GAME_PITCH_WIDTH * 0.5f),
             GAME_PITCH_LENGTH + 56.0f, 1.2f, GAME_PITCH_WIDTH + 58.0f,
             (Color){48, 53, 61, 255});
    DrawCylinder(world_point(-25.0f, 20.0f, 42.0f), 0.2f, 28.0f,
                 40.0f, 5, (Color){118, 156, 175, 255});
    DrawCylinder(world_point(165.0f, 22.0f, 43.0f), 0.2f, 36.0f,
                 45.0f, 5, (Color){130, 166, 180, 255});
    DrawCylinder(world_point(68.0f, 17.0f, -48.0f), 0.2f, 31.0f,
                 34.0f, 5, (Color){104, 151, 169, 255});
    DrawCylinder(world_point(73.0f, 19.0f, 133.0f), 0.2f, 38.0f,
                 38.0f, 5, (Color){121, 157, 171, 255});
    draw_side_stand(0);
    draw_side_stand(1);
    draw_end_stand(0);
    draw_end_stand(1);
    draw_ad_boards();
    draw_floodlights();
    for (cloud = 0; cloud < 6; cloud++) {
        Vector3 position = world_point(cloud_positions[cloud][0],
                                       cloud_positions[cloud][1],
                                       cloud_positions[cloud][2]);
        Color cloud_color = (Color){239, 248, 255, 255};
        DrawSphere(position, 5.5f, cloud_color);
        DrawSphere(world_point(position.x + 5.0f, position.y + 1.1f,
                               position.z), 4.2f, cloud_color);
        DrawSphere(world_point(position.x - 4.6f, position.y + 0.3f,
                               position.z), 3.8f, cloud_color);
    }
}

static void draw_goal(float x, float center_z, float direction)
{
    float half_width = GAME_GOAL_WIDTH * 0.5f;
    float back_x = x + direction * 3.0f;
    float post_height = 8.0f;
    Color post_color = {225, 225, 210, 255};
    int i;

    DrawLine3D(world_point(x, 0.0f, center_z - half_width),
               world_point(x, post_height, center_z - half_width), post_color);
    DrawLine3D(world_point(x, 0.0f, center_z + half_width),
               world_point(x, post_height, center_z + half_width), post_color);
    DrawLine3D(world_point(x, GAME_CROSSBAR_HEIGHT, center_z - half_width),
               world_point(x, GAME_CROSSBAR_HEIGHT, center_z + half_width), post_color);
    DrawLine3D(world_point(x, 0.0f, center_z - half_width),
               world_point(back_x, 0.0f, center_z - half_width), post_color);
    DrawLine3D(world_point(x, GAME_CROSSBAR_HEIGHT, center_z - half_width),
               world_point(back_x, GAME_CROSSBAR_HEIGHT, center_z - half_width), post_color);
    DrawLine3D(world_point(back_x, 0.0f, center_z - half_width),
               world_point(back_x, GAME_CROSSBAR_HEIGHT, center_z - half_width), post_color);
    DrawLine3D(world_point(x, 0.0f, center_z + half_width),
               world_point(back_x, 0.0f, center_z + half_width), post_color);
    DrawLine3D(world_point(x, GAME_CROSSBAR_HEIGHT, center_z + half_width),
               world_point(back_x, GAME_CROSSBAR_HEIGHT, center_z + half_width), post_color);
    DrawLine3D(world_point(back_x, 0.0f, center_z + half_width),
               world_point(back_x, GAME_CROSSBAR_HEIGHT, center_z + half_width), post_color);
    DrawLine3D(world_point(back_x, 0.0f, center_z - half_width),
               world_point(back_x, 0.0f, center_z + half_width), post_color);
    DrawLine3D(world_point(back_x, GAME_CROSSBAR_HEIGHT, center_z - half_width),
               world_point(back_x, GAME_CROSSBAR_HEIGHT, center_z + half_width), post_color);
    for (i = 1; i < 6; i++) {
        float z = center_z - half_width + (float)i * GAME_GOAL_WIDTH / 6.0f;
        DrawLine3D(world_point(x + direction * 0.6f, 0.25f, z),
                   world_point(back_x, GAME_CROSSBAR_HEIGHT, z),
                   (Color){205, 211, 199, 220});
    }
    for (i = 1; i < 4; i++) {
        float y = (float)i * GAME_CROSSBAR_HEIGHT / 4.0f;
        DrawLine3D(world_point(x + direction * 0.2f, y, center_z - half_width),
                   world_point(back_x, y, center_z + half_width),
                   (Color){205, 211, 199, 220});
    }
}

static Vector3 player_point(const GamePlayer *player, float forward,
                            float side, float height)
{
    float right_x = -player->facing_z;
    float right_z = player->facing_x;
    return world_point(player->x + player->facing_x * forward + right_x * side,
                       height,
                       player->z + player->facing_z * forward + right_z * side);
}

static void draw_player(const GamePlayer *player, int team, int is_away,
                        int number, int selected, int ring_visible, int carrying,
                        int contesting_high_ball, int foot_pickup, int kicking,
                        int handpassing, float animation_time)
{
    int pose = PLAYER_POSE_IDLE;

    if (contesting_high_ball) {
        pose = PLAYER_POSE_JUMP;
    } else if (foot_pickup) {
        pose = PLAYER_POSE_FOOT_PICKUP;
    } else if (kicking) {
        pose = PLAYER_POSE_KICK;
    } else if (handpassing) {
        pose = PLAYER_POSE_HANDPASS;
    } else if (carrying) {
        if (player->movement > 0.12f) {
            float cycle = fmodf(animation_time * 2.2f +
                                (float)number * 0.11f, 1.0f);
            int gait = (int)(cycle * 4.0f);
            pose = PLAYER_POSE_CARRY_RUN_A + gait;
        } else {
            pose = PLAYER_POSE_CARRY;
        }
    } else if (player->movement > 0.12f) {
        float cycle = fmodf(animation_time * 2.2f +
                            (float)number * 0.11f, 1.0f);
        pose = PLAYER_POSE_RUN_A + (int)(cycle * 4.0f);
    }

    if ((authentic_view && ring_visible) || selected) {
        float pulse = 0.66f + (selected ?
            0.04f * sinf(animation_time * 4.0f) : 0.0f);
        Color selection_color = selected ?
            (Color){31, 78, 240, 235} :
            is_away ? (Color){225, 34, 30, 205} :
                      (Color){30, 79, 235, 200};
        DrawCylinder(world_point(player->x, 0.075f, player->z),
                     pulse, pulse - 0.12f, 0.055f, 16,
                     selection_color);
    } else {
        DrawCylinder(world_point(player->x, 0.065f, player->z),
                     0.43f, 0.34f, 0.055f, 12, (Color){28, 46, 29, 105});
    }

    player_models_draw(&player_models, player, team, number, pose);

    if (carrying) {
        Vector3 ball_position = player_point(player, 0.45f, 0.0f, 1.15f);
        DrawSphere(ball_position, 0.22f, BALL_BROWN);
    }
}

static int point_in_circle(Vector2 point, Vector2 center, float radius)
{
    float dx = point.x - center.x;
    float dy = point.y - center.y;
    return dx * dx + dy * dy <= radius * radius;
}

static GameInput read_input(int *player_switch)
{
    static int kick_was_down;
    static int handpass_was_down;
    static int solo_was_down;
    static int bounce_was_down;
    static int tackle_was_down;
    static int switch_was_down;
    static int field_was_down;
    static int pickup_was_down;
    GameInput input = {0};
    int touch_count = GetTouchPointCount();
    int kick_down = 0;
    int handpass_down = 0;
    int solo_down = 0;
    int bounce_down = 0;
    int tackle_down = 0;
    int switch_down = 0;
    int field_down = 0;
    int pickup_down = 0;
    int i;
    int height = VIRTUAL_HEIGHT;
    int width = VIRTUAL_WIDTH;

    input.move_x = (float)(IsKeyDown(KEY_W) || IsKeyDown(KEY_UP)) -
                   (float)(IsKeyDown(KEY_S) || IsKeyDown(KEY_DOWN));
    input.move_z = (float)(IsKeyDown(KEY_D) || IsKeyDown(KEY_RIGHT)) -
                   (float)(IsKeyDown(KEY_A) || IsKeyDown(KEY_LEFT));
    input.curve = (float)IsKeyDown(KEY_RIGHT_BRACKET) -
                  (float)IsKeyDown(KEY_LEFT_BRACKET);
    input.kick = IsKeyPressed(KEY_SPACE);
    input.kick_high = IsKeyPressed(KEY_G);
    input.kick_low = IsKeyPressed(KEY_C);
    input.kick_long = IsKeyPressed(KEY_X);
    input.high_field = IsKeyPressed(KEY_J);
    input.pickup = IsKeyPressed(KEY_P);
    input.handpass = IsKeyPressed(KEY_E);
    input.solo = IsKeyPressed(KEY_Q);
    input.bounce = IsKeyPressed(KEY_R);
    input.tackle = IsKeyPressed(KEY_F);

    for (i = 0; i < touch_count; i++) {
        Vector2 touch = screen_to_virtual(GetTouchPosition(i));
        if (authentic_view) touch.x -= (VIRTUAL_WIDTH - 720.0f) * 0.5f;
        Vector2 stick = {90.0f, (float)height - 135.0f};
        if (point_in_circle(touch, stick, 66.0f)) {
            input.move_x = -(touch.y - stick.y) / 50.0f;
            input.move_z = (touch.x - stick.x) / 50.0f;
            input.curve = input.move_z;
        }
        kick_down |= point_in_circle(touch,
            (Vector2){(float)width - 48.0f, (float)height - 135.0f}, 34.0f);
        handpass_down |= point_in_circle(touch,
            (Vector2){(float)width - 123.0f, (float)height - 135.0f}, 31.0f);
        solo_down |= point_in_circle(touch,
            (Vector2){(float)width - 198.0f, (float)height - 135.0f}, 29.0f);
        bounce_down |= point_in_circle(touch,
            (Vector2){(float)width - 273.0f, (float)height - 135.0f}, 29.0f);
        tackle_down |= point_in_circle(touch,
            (Vector2){(float)width - 123.0f, (float)height - 220.0f}, 29.0f);
        field_down |= point_in_circle(touch,
            (Vector2){(float)width - 198.0f, (float)height - 220.0f}, 29.0f);
        pickup_down |= point_in_circle(touch,
            (Vector2){(float)width - 273.0f, (float)height - 220.0f}, 29.0f);
        switch_down |= point_in_circle(touch,
            (Vector2){(float)width - 48.0f, (float)height - 220.0f}, 29.0f);
    }

    input.kick |= kick_down && !kick_was_down;
    input.handpass |= handpass_down && !handpass_was_down;
    input.solo |= solo_down && !solo_was_down;
    input.bounce |= bounce_down && !bounce_was_down;
    input.tackle |= tackle_down && !tackle_was_down;
    input.high_field |= field_down && !field_was_down;
    input.pickup |= pickup_down && !pickup_was_down;
    *player_switch = switch_down && !switch_was_down;
    kick_was_down = kick_down;
    handpass_was_down = handpass_down;
    solo_was_down = solo_down;
    bounce_was_down = bounce_down;
    tackle_was_down = tackle_down;
    field_was_down = field_down;
    pickup_was_down = pickup_down;
    switch_was_down = switch_down;
    return input;
}

static void draw_touch_controls(void)
{
    int width = VIRTUAL_WIDTH;
    int height = VIRTUAL_HEIGHT;
    DrawCircleLines(90, height - 135, 58, (Color){235, 238, 220, 150});
    DrawCircleLines(width - 48, height - 135, 34, (Color){235, 238, 220, 180});
    DrawCircleLines(width - 123, height - 135, 31, (Color){235, 238, 220, 180});
    DrawCircleLines(width - 198, height - 135, 29, (Color){235, 238, 220, 180});
    DrawCircleLines(width - 273, height - 135, 29, (Color){235, 238, 220, 180});
    DrawCircleLines(width - 48, height - 220, 29, (Color){235, 238, 220, 180});
    DrawCircleLines(width - 123, height - 220, 29, (Color){235, 238, 220, 180});
    DrawCircleLines(width - 198, height - 220, 29, (Color){235, 238, 220, 180});
    DrawCircleLines(width - 273, height - 220, 29, (Color){235, 238, 220, 180});
    DrawText("NEXT", width - 65, height - 224, 10, RAYWHITE);
    DrawText("TACKLE", width - 145, height - 224, 9, RAYWHITE);
    DrawText("FIELD", width - 216, height - 224, 9, RAYWHITE);
    DrawText("LIFT", width - 287, height - 224, 9, RAYWHITE);
    DrawText("KICK", width - 63, height - 139, 10, RAYWHITE);
    DrawText("HAND", width - 139, height - 139, 9, RAYWHITE);
    DrawText("SOLO", width - 213, height - 139, 9, RAYWHITE);
    DrawText("BOUNCE", width - 300, height - 139, 8, RAYWHITE);
}

static void cycle_team(int *team, int direction, int other_team)
{
    *team = (*team + direction + GAME_TEAM_COUNT) % GAME_TEAM_COUNT;
    if (*team == other_team)
        *team = (*team + direction + GAME_TEAM_COUNT) % GAME_TEAM_COUNT;
}

static void update_team_select_touch(int *home_team, int *away_team,
                                    int *starting_player, int x, int y)
{
    int width = VIRTUAL_WIDTH;
    int center_x = width / 2;
    int list_x = center_x - 110;
    int list_y = 211;

    if (y >= 100 && y <= 177 && x >= center_x - 450 && x <= center_x - 60) {
        cycle_team(home_team, x < center_x - 255 ? -1 : 1, *away_team);
    } else if (y >= 100 && y <= 177 && x >= center_x + 60 && x <= center_x + 450) {
        cycle_team(away_team, x < center_x + 255 ? -1 : 1, *home_team);
    } else if (y >= list_y && y < list_y + 8 * 29) {
        int column = x >= list_x + 260 ? 1 : 0;
        int row = (y - list_y) / 29;
        int player = row + (column == 1 ? 8 : 0);
        if (x >= list_x + column * 260 &&
            x <= list_x + column * 260 + 240 && player < GAME_TEAM_SIZE)
            *starting_player = player;
    }
}

static void draw_team_select(int home_team, int away_team, int player_number)
{
    int width = VIRTUAL_WIDTH;
    int height = VIRTUAL_HEIGHT;
    int i;
    int list_x = width / 2 - 110;
    int list_y = 211;

    DrawRectangle(0, 0, width, height, (Color){0, 0, 0, 62});
    DrawRectangle(0, 0, width, 88, (Color){8, 19, 25, 225});
    DrawRectangle(0, 87, width, 3, (Color){230, 183, 54, 255});
    draw_retro_text("SUNDAY LEAGUE", width / 2 - 177, 7, 35,
                    (Color){242, 239, 216, 255});
    draw_retro_text("GAELIC FOOTBALL  |  MATCH DAY", width / 2 - 165, 50, 16,
                    (Color){235, 193, 64, 255});

    DrawRectangle(width / 2 - 450, 100, 390, 77, (Color){18, 31, 37, 235});
    DrawRectangle(width / 2 + 60, 100, 390, 77, (Color){18, 31, 37, 235});
    DrawRectangle(width / 2 - 450, 100, 10, 77, TEAM_COLORS[home_team]);
    DrawRectangle(width / 2 + 440, 100, 10, 77, TEAM_COLORS[away_team]);
    DrawText("HOME TEAM  [LEFT / RIGHT]  TAP TO CHANGE", width / 2 - 425, 107, 12, (Color){190, 199, 188, 255});
    draw_retro_text(game_team_name(home_team), width / 2 - 425, 131, 22, RAYWHITE);
    DrawText("AWAY TEAM  [A / D]  TAP TO CHANGE", width / 2 + 85, 107, 12, (Color){190, 199, 188, 255});
    draw_retro_text(game_team_name(away_team), width / 2 + 85, 131, 22, RAYWHITE);

    DrawText("PICK YOUR STARTING PLAYER  [UP / DOWN]  OR TAP A POSITION",
             list_x - 218, 185, 14, (Color){255, 220, 93, 255});
    for (i = 0; i < GAME_TEAM_SIZE; i++) {
        int column = i < 8 ? 0 : 1;
        int row = column == 0 ? i : i - 8;
        int x = list_x + column * 260;
        int y = list_y + row * 29;
        Color color = i == player_number ? (Color){219, 167, 43, 255} :
                                           (Color){30, 48, 42, 255};
        DrawRectangle(x, y, 240, 26, color);
        DrawText(TextFormat("%02d  %-14s", i + 1, game_player_role(i)),
                 x + 10, y + 5, 14, i == player_number ? BLACK : RAYWHITE);
    }

    DrawRectangle(0, height - 57, width, 57, (Color){8, 19, 25, 235});
    DrawRectangle(0, height - 57, width, 2, (Color){230, 183, 54, 255});
    DrawText("ENTER / TAP HERE  START MATCH     TAB  NEXT PLAYER     ESC  QUIT",
             width / 2 - 340, height - 34, 14, RAYWHITE);
}

static void draw_minimap(const GameState *game)
{
    int x = VIRTUAL_WIDTH / 2 - 86;
    int y = VIRTUAL_HEIGHT - 91;
    int width = 172;
    int height = 72;
    int team;
    int player;

    DrawRectangle(x - 5, y - 5, width + 10, height + 10, (Color){0, 0, 0, 155});
    DrawRectangle(x, y, width, height, (Color){37, 113, 55, 230});
    DrawRectangleLines(x, y, width, height, RAYWHITE);
    DrawLine(x + width / 2, y, x + width / 2, y + height, (Color){235, 238, 220, 170});
    for (team = 0; team < 2; team++) {
        int color_index = team == 0 ? game->home_team : game->away_team;
        for (player = 0; player < GAME_TEAM_SIZE; player++) {
            const GamePlayer *member = &game->players[team][player];
            int px = x + (int)(member->x / GAME_PITCH_LENGTH * width);
            int pz = y + (int)(member->z / GAME_PITCH_WIDTH * height);
            DrawCircle(px, pz, team == 0 && player == game->selected_player ? 3 : 2,
                       TEAM_COLORS[color_index]);
        }
    }
    DrawCircle(x + (int)(game->ball.x / GAME_PITCH_LENGTH * width),
               y + (int)(game->ball.z / GAME_PITCH_WIDTH * height), 3, GOLD);
}

static void draw_player_numbers(const GameState *game, const Camera3D *camera)
{
    int team;
    int player;
    for (team = 0; team < 2; team++) {
        for (player = 0; player < GAME_TEAM_SIZE; player++) {
            const GamePlayer *member = &game->players[team][player];
            if (team != 0 || player != game->selected_player) continue;
            Vector2 screen = GetWorldToScreen(
                world_point(member->x, 2.36f, member->z), *camera);
            if (screen.x >= 0 && screen.x < render_width &&
                screen.y >= 0 && screen.y < render_height) {
                DrawText(TextFormat("%d", player + 1),
                         (int)screen.x - (authentic_view ? 2 : 10),
                         (int)screen.y - (authentic_view ? 3 : 14),
                         authentic_view ? 5 : 24,
                         (Color){255, 224, 94, 255});
            }
        }
    }
}

static const char *player_name(int player)
{
    static const char *names[GAME_TEAM_SIZE] = {
        "O. KELLY", "D. MURPHY", "A. BYRNE", "C. WALSH", "R. DOYLE",
        "T. RYAN", "J. NOLAN", "E. CONNOLLY", "P. KAVANAGH", "M. KEANE",
        "S. O'BRIEN", "F. LYNCH", "B. POWER", "N. ROCHE", "L. HAYES"
    };
    if (player < 0 || player >= GAME_TEAM_SIZE) return "SUBSTITUTE";
    return names[player];
}

static int nearest_opponent(const GameState *game)
{
    int player;
    int nearest = 0;
    float best_distance = 1000000.0f;
    for (player = 0; player < GAME_TEAM_SIZE; player++) {
        const GamePlayer *opponent = &game->players[1][player];
        float dx = opponent->x - game->ball.x;
        float dz = opponent->z - game->ball.z;
        float distance = dx * dx + dz * dz;
        if (distance < best_distance) {
            best_distance = distance;
            nearest = player;
        }
    }
    return nearest;
}

static void draw_player_card(int x, int y, int team, int player,
                             const char *side)
{
    Color team_color = TEAM_COLORS[team];
    const int width = 208;
    const int height = 58;
    DrawRectangle(x, y, width, height, (Color){8, 16, 23, 232});
    DrawRectangle(x, y, 7, height, team_color);
    DrawRectangleLines(x, y, width, height, (Color){206, 214, 206, 190});
    DrawText(TextFormat("%s  |  %s  |  #%02d", side,
                        game_player_role(player), player + 1),
             x + 18, y + 7, 12, (Color){208, 215, 205, 255});
    draw_retro_text(player_name(player), x + 18, y + 27, 17, RAYWHITE);
}

static void draw_options_screen(void)
{
    int x = GetScreenWidth() / 2 - 335;
    int y = 30;
    int width = 670;
    int height = 500;
    int line_y = y + 72;

    DrawRectangle(0, 0, GetScreenWidth(), GetScreenHeight(),
                  (Color){8, 12, 18, 210});
    DrawRectangle(x, y, width, height, (Color){17, 26, 31, 240});
    DrawRectangleLines(x, y, width, height, (Color){249, 216, 93, 255});
    draw_retro_text("OPTIONS & MATCH RULES", x + 24, y + 18, 26,
                    (Color){255, 230, 150, 255});

    DrawText("TACKLE", x + 28, line_y, 16, (Color){253, 203, 79, 255});
    DrawText("F / touch button. Win possession when close to the carrier.",
             x + 200, line_y, 16, RAYWHITE);
    line_y += 27;

    DrawText("HIGH FIELD", x + 28, line_y, 16, (Color){253, 203, 79, 255});
    DrawText("J / touch FIELD while the ball is high to jump and catch.",
             x + 200, line_y, 16, RAYWHITE);
    line_y += 27;

    DrawText("FOOT PICKUP", x + 28, line_y, 16, (Color){253, 203, 79, 255});
    DrawText("P / touch LIFT near a grounded ball; crouch, hook and lift it.",
             x + 200, line_y, 16, RAYWHITE);
    line_y += 27;

    DrawText("HAND PASS", x + 28, line_y, 16, (Color){253, 203, 79, 255});
    DrawText("E. Quick short pass in the direction you are facing.",
             x + 200, line_y, 16, RAYWHITE);
    line_y += 27;

    DrawText("STANDARD", x + 28, line_y, 15, (Color){253, 203, 79, 255});
    DrawText("Space: balanced kick.", x + 200, line_y, 15, RAYWHITE);
    line_y += 27;

    DrawText("HIGH LOB", x + 28, line_y, 15, (Color){253, 203, 79, 255});
    DrawText("G: high flight, for a high ball.", x + 200, line_y, 15, RAYWHITE);
    line_y += 25;

    DrawText("LOW DRIVE", x + 28, line_y, 15, (Color){253, 203, 79, 255});
    DrawText("C: fast, low trajectory.", x + 200, line_y, 15, RAYWHITE);
    line_y += 25;

    DrawText("LONG CLEAR", x + 28, line_y, 15, (Color){253, 203, 79, 255});
    DrawText("X: powerful, long and high.", x + 200, line_y, 15, RAYWHITE);
    line_y += 28;

    DrawText("SWITCH PLAYER", x + 28, line_y, 15, (Color){253, 203, 79, 255});
    DrawText("Tab/NEXT: nearest teammate; Shift+Tab: previous player.",
             x + 200, line_y, 15, RAYWHITE);
    line_y += 25;

    DrawText("KICK CURL", x + 28, line_y, 15, (Color){253, 203, 79, 255});
    DrawText("[ / ] while kicking; N64: lean stick across the pitch.",
             x + 200, line_y, 15, RAYWHITE);
    line_y += 28;

    DrawText("KICK-OUT RULE", x + 28, line_y, 18, (Color){255, 226, 116, 255});
    DrawText("Sideline restart: goalkeeper kicks from the central 20-yard line.",
             x + 28, line_y + 27, 15, RAYWHITE);
    DrawText("The kick must clear the arc; other players stay outside it.",
             x + 28, line_y + 48, 15, RAYWHITE);
    DrawText("Press H or O to close this help screen.",
             x + 28, y + height - 30, 16, (Color){255, 223, 98, 255});
}

static void draw_match_hud(const GameState *game, float elapsed,
                           int show_touch_controls)
{
    int seconds = (int)(elapsed * 3.0f);
    int minutes = seconds / 60;
    int remainder = seconds % 60;
    int center = VIRTUAL_WIDTH / 2;
    int panel_width = 276;
    int panel_x = center - panel_width / 2;
    int opponent = nearest_opponent(game);

    DrawRectangle(panel_x, 3, panel_width, 47, (Color){8, 17, 25, 238});
    DrawRectangle(panel_x, 3, panel_width, 2, (Color){226, 185, 65, 255});
    DrawRectangleLines(panel_x, 3, panel_width, 47, (Color){151, 161, 156, 210});
    draw_retro_text(game_team_name(game->home_team), panel_x + 10, 9, 13,
                    (Color){230, 237, 229, 255});
    DrawText("VS", center - 10, 10, 12, (Color){211, 183, 84, 255});
    draw_retro_text(game_team_name(game->away_team), panel_x + 155, 9, 13,
                    (Color){230, 237, 229, 255});
    DrawText(TextFormat("%d-%02d", game->team_goals[0], game->team_points[0]),
             panel_x + 12, 27, 17, (Color){255, 231, 167, 255});
    DrawText(TextFormat("%d-%02d", game->team_goals[1], game->team_points[1]),
             panel_x + 157, 27, 17, (Color){255, 231, 167, 255});

    DrawRectangle(VIRTUAL_WIDTH - 105, 3, 105, 49, (Color){8, 17, 25, 232});
    DrawRectangle(VIRTUAL_WIDTH - 105, 3, 5, 49, TEAM_COLORS[game->away_team]);
    DrawText("MATCH", VIRTUAL_WIDTH - 91, 8, 11, (Color){212, 219, 213, 255});
    draw_retro_text(TextFormat("%02d:%02d", minutes, remainder),
                    VIRTUAL_WIDTH - 91, 23, 19, RAYWHITE);

    if (game->event != GAME_EVENT_NONE) {
        int text_width = MeasureText(game_event_text(game->event), 17);
        int x = center - text_width / 2 - 13;
        DrawRectangle(x, 62, text_width + 26, 27, (Color){8, 17, 25, 224});
        DrawRectangleLines(x, 62, text_width + 26, 27,
                           (Color){255, 214, 92, 220});
        draw_retro_text(game_event_text(game->event), x + 13, 67, 17,
                        (Color){255, 227, 124, 255});
    }

    draw_player_card(12, VIRTUAL_HEIGHT - 76, game->home_team,
                     game->selected_player, "HOME");
    draw_player_card(VIRTUAL_WIDTH - 220, VIRTUAL_HEIGHT - 76, game->away_team,
                     opponent, "AWAY");
    draw_minimap(game);

    if (show_touch_controls) {
        draw_touch_controls();
    }
}

static void draw_menu_backdrop(const GameState *game, float animation_time)
{
    Camera3D preview = {0};
    int team;
    int player;
    if (authentic_view) {
        preview.position = world_point(GAME_PITCH_LENGTH * 0.5f + 23.0f,
                                       29.0f, GAME_PITCH_WIDTH * 0.5f + 28.0f);
    } else {
        preview.position = world_point(GAME_PITCH_LENGTH * 0.5f + 37.0f,
                                       68.0f, 132.0f);
    }
    preview.target = world_point(GAME_PITCH_LENGTH * 0.5f, 0.0f,
                                 GAME_PITCH_WIDTH * 0.5f);
    preview.up = world_point(0.0f, 1.0f, 0.0f);
    preview.fovy = authentic_view ? 40.0f : 55.0f;
    preview.projection = CAMERA_PERSPECTIVE;
    ClearBackground((Color){128, 195, 226, 255});
    BeginMode3D(preview);
    if (authentic_view) draw_authentic_stands();
    else draw_stadium();
    draw_pitch();
    draw_goal(0.0f, GAME_PITCH_WIDTH * 0.5f, -1.0f);
    draw_goal(GAME_PITCH_LENGTH, GAME_PITCH_WIDTH * 0.5f, 1.0f);
    for (team = 0; team < 2; team++) {
        int kit = team == 0 ? game->home_team : game->away_team;
        for (player = 0; player < GAME_TEAM_SIZE; player++) {
            draw_player(&game->players[team][player], kit, team == 1,
                        player + 1, 0, 0, 0, 0, 0, 0, 0, animation_time);
        }
    }
    EndMode3D();
}

int main(void)
{
    GameState game;
    GameAudio audio = {0};
    Camera3D camera = {0};
    RenderTexture2D frame = {0};
    int menu_active = 1;
    int tactical_view = 0;
    int home_team = 0;
    int away_team = 1;
    int starting_player = 9;
    float camera_yaw = 0.55f;
    float camera_openness = 0.0f;
    float animation_time = 0.0f;
    float match_elapsed = 0.0f;
    int menu_touch_was_down = 0;
    int camera_ready = 0;
    int show_touch_controls = 0;
    int show_help = 0;

    game_init(&game);
    SetConfigFlags(FLAG_MSAA_4X_HINT | FLAG_WINDOW_RESIZABLE);
    InitWindow(SCREEN_WIDTH, SCREEN_HEIGHT, "Sunday League - Match Day");
    if (!IsWindowReady()) {
        TraceLog(LOG_ERROR, "Could not create the game window.");
        return 1;
    }
    if (!stadium_assets_init()) {
        TraceLog(LOG_WARNING, "Using the fallback untextured pitch.");
    }
    if (!player_models_init(&player_models)) {
        if (grass_model_valid) UnloadModel(grass_model);
        CloseWindow();
        return 1;
    }
    frame = LoadRenderTexture(FRAME_WIDTH, FRAME_HEIGHT);
    if (!IsRenderTextureValid(frame)) {
        TraceLog(LOG_ERROR, "Could not create the enhanced game render target.");
        player_models_unload(&player_models);
        if (grass_model_valid) UnloadModel(grass_model);
        CloseWindow();
        return 1;
    }
    authentic_frame = LoadRenderTexture(AUTHENTIC_WIDTH, AUTHENTIC_HEIGHT);
    if (!IsRenderTextureValid(authentic_frame)) {
        TraceLog(LOG_ERROR, "Could not create the 320x240 presentation target.");
        UnloadRenderTexture(frame);
        player_models_unload(&player_models);
        if (grass_model_valid) UnloadModel(grass_model);
        CloseWindow();
        return 1;
    }
    SetTextureFilter(frame.texture, TEXTURE_FILTER_BILINEAR);
    SetTextureFilter(authentic_frame.texture, TEXTURE_FILTER_POINT);
    SetTargetFPS(60);

    camera.up = world_point(0.0f, 1.0f, 0.0f);
    camera.fovy = 43.0f;
    camera.projection = CAMERA_PERSPECTIVE;

    while (!WindowShouldClose()) {
        RenderTexture2D active_frame;
        float delta_time = GetFrameTime();
        if (delta_time > 0.1f) delta_time = 0.1f;
        animation_time += delta_time;
        if (IsKeyPressed(KEY_F2)) {
            authentic_view = !authentic_view;
            render_width = authentic_view ? AUTHENTIC_WIDTH : FRAME_WIDTH;
            render_height = authentic_view ? AUTHENTIC_HEIGHT : FRAME_HEIGHT;
            camera_ready = 0;
        }
        if (!menu_active && (IsKeyPressed(KEY_H) || IsKeyPressed(KEY_O)))
            show_help = !show_help;
        active_frame = authentic_view ? authentic_frame : frame;

        if (menu_active) {
            int touch_count = GetTouchPointCount();
            int touch_down = touch_count > 0;
            int pointer_pressed = (touch_down && !menu_touch_was_down) ||
                                  IsMouseButtonPressed(MOUSE_BUTTON_LEFT);
            int start_touch = 0;
            if (touch_down) show_touch_controls = 1;
            if (IsKeyPressed(KEY_LEFT)) cycle_team(&home_team, -1, away_team);
            if (IsKeyPressed(KEY_RIGHT)) cycle_team(&home_team, 1, away_team);
            if (IsKeyPressed(KEY_A)) cycle_team(&away_team, -1, home_team);
            if (IsKeyPressed(KEY_D)) cycle_team(&away_team, 1, home_team);
            if (IsKeyPressed(KEY_UP)) starting_player =
                (starting_player + GAME_TEAM_SIZE - 1) % GAME_TEAM_SIZE;
            if (IsKeyPressed(KEY_DOWN)) starting_player =
                (starting_player + 1) % GAME_TEAM_SIZE;
            if (IsKeyPressed(KEY_TAB)) starting_player =
                (starting_player + 1) % GAME_TEAM_SIZE;
            if (pointer_pressed) {
                Vector2 pointer = touch_down ? GetTouchPosition(0) : GetMousePosition();
                Vector2 touch = screen_to_virtual(pointer);
                if (authentic_view) {
                    int menu_x = (int)(touch.x / 3.0f);
                    int menu_y = (int)(touch.y / 2.25f);
                    if (menu_y >= 108 && menu_y <= 124) {
                        cycle_team(&home_team, menu_x < AUTHENTIC_WIDTH / 2 ?
                                   -1 : 1, away_team);
                    } else if (menu_y >= 125 && menu_y <= 140) {
                        cycle_team(&away_team, menu_x < AUTHENTIC_WIDTH / 2 ?
                                   -1 : 1, home_team);
                    } else if (menu_y >= 141 && menu_y <= 157) {
                        starting_player = (starting_player + 1) % GAME_TEAM_SIZE;
                    }
                    start_touch = menu_y >= 158;
                } else {
                    update_team_select_touch(&home_team, &away_team,
                                             &starting_player,
                                             (int)touch.x, (int)touch.y);
                    start_touch = touch.y >= VIRTUAL_HEIGHT - 57;
                }
            }
            menu_touch_was_down = touch_down;
            game_set_teams(&game, home_team, away_team, starting_player);
            if (IsKeyPressed(KEY_ENTER) || start_touch) {
                game_set_teams(&game, home_team, away_team, starting_player);
                game_audio_init(&audio);
                menu_active = 0;
            }

            BeginDrawing();
            BeginTextureMode(active_frame);
            draw_menu_backdrop(&game, animation_time);
            if (authentic_view) {
                draw_authentic_hud(&game, match_elapsed, 1, home_team, away_team,
                                   starting_player, show_touch_controls);
            } else {
                rlPushMatrix();
                rlScalef((float)FRAME_SCALE, (float)FRAME_SCALE, 1.0f);
                draw_team_select(home_team, away_team, starting_player);
                rlPopMatrix();
            }
            EndTextureMode();
            present_frame(active_frame, render_width, render_height);
            EndDrawing();
            continue;
        }

        if (IsKeyPressed(KEY_V)) tactical_view = !tactical_view;
        if (IsKeyPressed(KEY_COMMA)) camera_yaw -= 0.18f;
        if (IsKeyPressed(KEY_PERIOD)) camera_yaw += 0.18f;

        if (!show_help) {
            int player_switch = 0;
            GameInput input = read_input(&player_switch);
            if (GetTouchPointCount() > 0) show_touch_controls = 1;
            if (IsKeyPressed(KEY_TAB)) {
                if (IsKeyDown(KEY_LEFT_SHIFT) ||
                    IsKeyDown(KEY_RIGHT_SHIFT))
                    game_select_next_player(&game, -1);
                else
                    game_select_nearest_player(&game);
            }
            if (player_switch) game_select_next_player(&game, 1);
            game_update(&game, input, delta_time);
            match_elapsed += delta_time;
            game_audio_update(&audio, game.event);
        }

        {
            float direction = game.ball_team == 1 ? -1.0f : 1.0f;
            float focus_x = game.ball.x * 0.7f + game.player_x * 0.3f;
            float focus_z = game.ball.z * 0.7f + game.player_z * 0.3f;
            float landing_x = game.ball.x;
            float landing_z = game.ball.z;
            float flight_distance = 0.0f;
            float target_openness = 0.0f;
            float orbit = camera_yaw;
            Vector3 target;
            Vector3 position;
            float blend = 1.0f - expf(-delta_time * 4.0f);

            if (game.ball.in_flight) {
                float discriminant = game.ball.velocity_y *
                    game.ball.velocity_y +
                    2.0f * GAME_BALL_GRAVITY * game.ball.height;
                float flight_time = (game.ball.velocity_y +
                    sqrtf(discriminant)) / GAME_BALL_GRAVITY;

                landing_x += game.ball.velocity_x * flight_time;
                landing_z += game.ball.velocity_z * flight_time;
                if (landing_x < 0.0f) landing_x = 0.0f;
                if (landing_x > GAME_PITCH_LENGTH)
                    landing_x = GAME_PITCH_LENGTH;
                if (landing_z < 0.0f) landing_z = 0.0f;
                if (landing_z > GAME_PITCH_WIDTH)
                    landing_z = GAME_PITCH_WIDTH;

                flight_distance = sqrtf(
                    (landing_x - game.ball.x) * (landing_x - game.ball.x) +
                    (landing_z - game.ball.z) * (landing_z - game.ball.z));
                target_openness = fminf(
                    fmaxf((flight_distance - 10.0f) / 50.0f, 0.0f), 1.0f);
                focus_x += (landing_x - game.ball.x) * 0.45f;
                focus_z += (landing_z - game.ball.z) * 0.45f;
            }
            camera_openness += (target_openness - camera_openness) *
                               (1.0f - expf(-delta_time * 2.5f));
            target = world_point(focus_x + direction * 5.0f,
                                 0.6f + game.ball.height *
                                     camera_openness * 0.16f,
                                 focus_z);
            if (authentic_view) {
                float trailing = 13.0f + camera_openness * 12.0f;
                float sideline = 9.0f + camera_openness * 7.0f;
                position = world_point(
                    focus_x - direction * cosf(orbit) * trailing,
                    8.0f + camera_openness * 8.0f,
                    focus_z + sinf(orbit) * sideline);
                camera.fovy = 37.0f + camera_openness * 13.0f;
            } else if (tactical_view) {
                position = world_point(focus_x - direction * cosf(orbit) * 88.0f,
                                        78.0f,
                                        focus_z + sinf(orbit) * 95.0f);
                camera.fovy = 47.0f;
            } else {
                float trailing = 13.0f + camera_openness * 12.0f;
                float sideline = 9.0f + camera_openness * 7.0f;
                position = world_point(
                    focus_x - direction * cosf(orbit) * trailing,
                    8.0f + camera_openness * 8.0f,
                    focus_z + sinf(orbit) * sideline);
                camera.fovy = 37.0f + camera_openness * 13.0f;
            }
            if (!camera_ready) {
                camera.position = position;
                camera.target = target;
                camera_ready = 1;
            } else {
                camera.position.x += (position.x - camera.position.x) * blend;
                camera.position.y += (position.y - camera.position.y) * blend;
                camera.position.z += (position.z - camera.position.z) * blend;
                camera.target.x += (target.x - camera.target.x) * blend;
                camera.target.y += (target.y - camera.target.y) * blend;
                camera.target.z += (target.z - camera.target.z) * blend;
            }
        }

        BeginDrawing();
        BeginTextureMode(active_frame);
        ClearBackground(authentic_view ? (Color){57, 75, 79, 255} :
                                          (Color){128, 195, 226, 255});
        BeginMode3D(camera);
        if (authentic_view) draw_authentic_stands();
        else draw_stadium();
        draw_pitch();
        draw_goal(0.0f, GAME_PITCH_WIDTH * 0.5f, -1.0f);
        draw_goal(GAME_PITCH_LENGTH, GAME_PITCH_WIDTH * 0.5f, 1.0f);
        {
            int team;
            int player;
            for (team = 0; team < 2; team++) {
                int kit = team == 0 ? game.home_team : game.away_team;
                for (player = 0; player < GAME_TEAM_SIZE; player++) {
                    const GamePlayer *member = &game.players[team][player];
                    float dx = member->x - game.ball.x;
                    float dz = member->z - game.ball.z;
                    int carrying = game.ball_team == team &&
                                   game.ball_player == player;
                    int contesting_high_ball = member->jump_time > 0.0f;
                    int foot_pickup = game.pickup_team == team &&
                                      game.pickup_player == player;
                    int action_pose = team == 0 &&
                        player == game.selected_player &&
                        game.event_time > 1.55f;
                    int kicking = action_pose &&
                        game.event == GAME_EVENT_KICKED;
                    int handpassing = action_pose &&
                        game.event == GAME_EVENT_HANDPASSED;
                    draw_player(member, kit, team == 1, player + 1,
                                team == 0 && player == game.selected_player,
                                dx * dx + dz * dz < 1600.0f, carrying,
                                contesting_high_ball, foot_pickup, kicking,
                                handpassing,
                                animation_time);
                }
            }
        }
        if (game.ball_team < 0) {
            DrawCylinder(world_point(game.ball.x, 0.035f, game.ball.z),
                         0.55f + fminf(game.ball.height, 6.0f) * 0.08f,
                         0.55f + fminf(game.ball.height, 6.0f) * 0.08f,
                         0.025f, 12, (Color){20, 25, 17, 105});
            if (game.ball.in_flight) {
                float discriminant = game.ball.velocity_y *
                    game.ball.velocity_y +
                    2.0f * GAME_BALL_GRAVITY *
                        fmaxf(game.ball.height - 0.18f, 0.0f);
                float flight_time = (game.ball.velocity_y +
                    sqrtf(discriminant)) / GAME_BALL_GRAVITY;
                float landing_x = fminf(GAME_PITCH_LENGTH, fmaxf(0.0f,
                    game.ball.x + game.ball.velocity_x * flight_time));
                float landing_z = fminf(GAME_PITCH_WIDTH, fmaxf(0.0f,
                    game.ball.z + game.ball.velocity_z * flight_time));
                DrawCircle3D(world_point(landing_x, 0.055f, landing_z),
                             0.85f, (Vector3){1.0f, 0.0f, 0.0f}, 90.0f,
                             (Color){255, 229, 112, 150});
            }
            DrawSphere(world_point(game.ball.x, game.ball.height, game.ball.z),
                       0.3f, BALL_BROWN);
        }
        EndMode3D();
        if (authentic_view) {
            draw_authentic_hud(&game, match_elapsed, 0, home_team, away_team,
                               starting_player, show_touch_controls);
        } else {
            draw_player_numbers(&game, &camera);
            rlPushMatrix();
            rlScalef((float)FRAME_SCALE, (float)FRAME_SCALE, 1.0f);
            draw_match_hud(&game, match_elapsed, show_touch_controls);
            rlPopMatrix();
        }
        EndTextureMode();
        present_frame(active_frame, render_width, render_height);
        if (show_help) draw_options_screen();
        EndDrawing();
    }

    game_audio_shutdown(&audio);
    player_models_unload(&player_models);
    UnloadRenderTexture(frame);
    UnloadRenderTexture(authentic_frame);
    if (grass_model_valid) UnloadModel(grass_model);
    CloseWindow();
    return 0;
}

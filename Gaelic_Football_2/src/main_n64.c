#include "game.h"

#include <libdragon.h>
#include <math.h>
#include <stdio.h>

#if !defined(PLATFORM_N64)
#error "Compile main_n64.c with the PLATFORM_N64 frontend."
#endif

#define N64_PI 3.14159265358979323846f
#define N64_FRAME_TIME (1.0f / 60.0f)
#define N64_FOCAL_LENGTH 300.0f

typedef struct Point3 {
    float x;
    float y;
    float z;
} Point3;

typedef struct Point2 {
    float x;
    float y;
    float depth;
} Point2;

typedef struct PlayerOrder {
    int team;
    int player;
    float depth;
} PlayerOrder;

static Point3 camera_position;
static Point3 camera_right;
static Point3 camera_up;
static Point3 camera_forward;
static const color_t team_colors[GAME_TEAM_COUNT] = {
    RGBA32(45, 102, 205, 255), RGBA32(194, 47, 42, 255),
    RGBA32(35, 137, 74, 255), RGBA32(232, 190, 42, 255)
};
static const color_t away_colors[GAME_TEAM_COUNT] = {
    RGBA32(240, 240, 235, 255), RGBA32(240, 240, 235, 255),
    RGBA32(240, 240, 235, 255), RGBA32(35, 50, 125, 255)
};
static const char *const team_short_names[GAME_TEAM_COUNT] = {
    "N COAST", "RIVER", "RED VAL", "HIGHLAND"
};
static const char *const player_names[GAME_TEAM_SIZE] = {
    "O KELLY", "D MURPHY", "A BYRNE", "C WALSH", "R DOYLE",
    "T RYAN", "J NOLAN", "E CONNOLLY", "P KAVANAGH", "M KEANE",
    "S OBRIEN", "F LYNCH", "B POWER", "N ROCHE", "L HAYES"
};
static const unsigned char font5x3[36][5] = {
    {7, 5, 5, 5, 7}, {2, 6, 2, 2, 7}, {7, 1, 7, 4, 7},
    {7, 1, 7, 1, 7}, {5, 5, 7, 1, 1}, {7, 4, 7, 1, 7},
    {7, 4, 7, 5, 7}, {7, 1, 1, 2, 2}, {7, 5, 7, 5, 7},
    {7, 5, 7, 1, 7},
    {2, 5, 7, 5, 5}, {6, 5, 6, 5, 6}, {3, 4, 4, 4, 3},
    {6, 5, 5, 5, 6}, {7, 4, 6, 4, 7}, {7, 4, 6, 4, 4},
    {3, 4, 5, 5, 3}, {5, 5, 7, 5, 5}, {7, 2, 2, 2, 7},
    {1, 1, 1, 5, 2}, {5, 5, 6, 5, 5}, {4, 4, 4, 4, 7},
    {5, 7, 7, 5, 5}, {5, 7, 7, 7, 5}, {2, 5, 5, 5, 2},
    {6, 5, 6, 4, 4}, {2, 5, 5, 7, 3}, {6, 5, 6, 5, 5},
    {3, 4, 2, 1, 6}, {7, 2, 2, 2, 2}, {5, 5, 5, 5, 7},
    {5, 5, 5, 5, 2}, {5, 5, 7, 7, 5}, {5, 5, 2, 5, 5},
    {5, 5, 2, 2, 2}, {7, 1, 2, 4, 7}
};

static Point3 point3(float x, float y, float z)
{
    Point3 point = {x, y, z};
    return point;
}

static Point3 add3(Point3 a, Point3 b)
{
    return point3(a.x + b.x, a.y + b.y, a.z + b.z);
}

static Point3 subtract3(Point3 a, Point3 b)
{
    return point3(a.x - b.x, a.y - b.y, a.z - b.z);
}

static Point3 scale3(Point3 value, float scale)
{
    return point3(value.x * scale, value.y * scale, value.z * scale);
}

static float dot3(Point3 a, Point3 b)
{
    return a.x * b.x + a.y * b.y + a.z * b.z;
}

static Point3 cross3(Point3 a, Point3 b)
{
    return point3(a.y * b.z - a.z * b.y,
                  a.z * b.x - a.x * b.z,
                  a.x * b.y - a.y * b.x);
}

static Point3 normalize3(Point3 value)
{
    float length = sqrtf(dot3(value, value));
    if (length < 0.0001f) return point3(0.0f, 1.0f, 0.0f);
    return scale3(value, 1.0f / length);
}

static Point2 project(Point3 point)
{
    Point3 relative = subtract3(point, camera_position);
    float depth = dot3(relative, camera_forward);
    float camera_depth = depth;
    Point2 result;
    float focal;

    if (depth < 1.0f) depth = 1.0f;
    focal = N64_FOCAL_LENGTH / depth;
    result.x = 160.0f + dot3(relative, camera_right) * focal;
    result.y = 120.0f - dot3(relative, camera_up) * focal;
    result.depth = camera_depth;
    return result;
}

static int inside_screen_edge(Point2 point, int edge)
{
    if (edge == 0) return point.x >= 0.0f;
    if (edge == 1) return point.x <= 320.0f;
    if (edge == 2) return point.y >= 0.0f;
    return point.y <= 240.0f;
}

static Point2 screen_edge_intersection(Point2 start, Point2 end, int edge)
{
    Point2 result;
    float boundary = edge == 0 ? 0.0f :
                     edge == 1 ? 320.0f :
                     edge == 2 ? 0.0f : 240.0f;
    float amount;
    if (edge < 2) {
        float delta = end.x - start.x;
        amount = delta == 0.0f ? 0.0f : (boundary - start.x) / delta;
    } else {
        float delta = end.y - start.y;
        amount = delta == 0.0f ? 0.0f : (boundary - start.y) / delta;
    }
    result.x = start.x + (end.x - start.x) * amount;
    result.y = start.y + (end.y - start.y) * amount;
    result.depth = start.depth + (end.depth - start.depth) * amount;
    return result;
}

static int clip_screen_polygon(const Point2 *input, int input_count,
                               Point2 *output, int edge)
{
    int output_count = 0;
    int i;
    Point2 previous;
    int previous_inside;

    if (input_count == 0) return 0;
    previous = input[input_count - 1];
    previous_inside = inside_screen_edge(previous, edge);
    for (i = 0; i < input_count; i++) {
        Point2 current = input[i];
        int current_inside = inside_screen_edge(current, edge);
        if (current_inside != previous_inside) {
            output[output_count++] =
                screen_edge_intersection(previous, current, edge);
        }
        if (current_inside) output[output_count++] = current;
        previous = current;
        previous_inside = current_inside;
    }
    return output_count;
}

static void draw_screen_triangle(Point2 a, Point2 b, Point2 c, color_t color)
{
    Point2 first[12];
    Point2 second[12];
    int count = 3;
    int edge;
    first[0] = a;
    first[1] = b;
    first[2] = c;
    for (edge = 0; edge < 4; edge++) {
        Point2 *input = edge % 2 == 0 ? first : second;
        Point2 *output = edge % 2 == 0 ? second : first;
        count = clip_screen_polygon(input, count, output, edge);
        if (count < 3) return;
    }
    for (edge = 1; edge < count - 1; edge++) {
        float va[2] = {first[0].x, first[0].y};
        float vb[2] = {first[edge].x, first[edge].y};
        float vc[2] = {first[edge + 1].x, first[edge + 1].y};
        rdpq_set_prim_color(color);
        rdpq_triangle(&TRIFMT_FILL, va, vb, vc);
    }
}

static void draw_world_triangle(Point3 a, Point3 b, Point3 c, color_t color)
{
    draw_screen_triangle(project(a), project(b), project(c), color);
}

static void draw_world_quad(Point3 a, Point3 b, Point3 c, Point3 d,
                            color_t color)
{
    draw_world_triangle(a, b, c, color);
    draw_world_triangle(a, c, d, color);
}

static void draw_ground_line(float x0, float z0, float x1, float z1,
                             float width, color_t color)
{
    float dx = x1 - x0;
    float dz = z1 - z0;
    float length = sqrtf(dx * dx + dz * dz);
    float ox;
    float oz;
    if (length < 0.001f) return;
    ox = -dz * width / (2.0f * length);
    oz = dx * width / (2.0f * length);
    draw_world_quad(point3(x0 + ox, 0.035f, z0 + oz),
                    point3(x1 + ox, 0.035f, z1 + oz),
                    point3(x1 - ox, 0.035f, z1 - oz),
                    point3(x0 - ox, 0.035f, z0 - oz), color);
}

static void update_camera(const GameState *game)
{
    float focus_x = game->ball.x * 0.68f + game->player_x * 0.32f;
    float focus_z = game->ball.z * 0.68f + game->player_z * 0.32f;
    Point3 target = point3(focus_x + 8.0f, 0.0f, focus_z);
    Point3 world_up = point3(0.0f, 1.0f, 0.0f);
    camera_position = point3(focus_x - 18.0f, 24.0f, focus_z + 25.0f);
    camera_forward = normalize3(subtract3(target, camera_position));
    camera_right = normalize3(cross3(camera_forward, world_up));
    camera_up = normalize3(cross3(camera_right, camera_forward));
}

static void draw_pitch(void)
{
    float length = GAME_PITCH_LENGTH;
    float width = GAME_PITCH_WIDTH;
    int i;

    draw_world_quad(point3(0.0f, 0.0f, 0.0f),
                    point3(length, 0.0f, 0.0f),
                    point3(length, 0.0f, width),
                    point3(0.0f, 0.0f, width),
                    RGBA32(37, 111, 51, 255));
    for (i = 0; i < 32; i++) {
        int row;
        for (row = 0; row < 20; row++) {
            float x0 = (float)i * length / 32.0f;
            float x1 = (float)(i + 1) * length / 32.0f;
            float z0 = (float)row * width / 20.0f;
            float z1 = (float)(row + 1) * width / 20.0f;
            Point2 center = project(point3((x0 + x1) * 0.5f, 0.02f,
                                            (z0 + z1) * 0.5f));
            unsigned int pattern = (unsigned int)i * 73856093u ^
                                   (unsigned int)row * 19349663u;
            int variation = (int)(pattern & 7u);
            color_t grass;
            if (center.depth < 1.0f || center.x < -8.0f ||
                center.x > 328.0f || center.y < -8.0f ||
                center.y > 248.0f) continue;
            grass = (pattern & 8u) ?
                RGBA32(38 + variation, 111 + variation, 50 + variation, 255) :
                RGBA32(35 + variation, 106 + variation, 47 + variation, 255);
            draw_world_quad(point3(x0, 0.02f, z0),
                            point3(x1, 0.02f, z0),
                            point3(x1, 0.02f, z1),
                            point3(x0, 0.02f, z1), grass);
        }
    }
    for (i = 0; i < 14; i += 2) {
        float x = (float)i * 10.0f;
        draw_world_quad(point3(x, 0.012f, 0.0f),
                        point3(x + 10.0f, 0.012f, 0.0f),
                        point3(x + 10.0f, 0.012f, width),
                        point3(x, 0.012f, width),
                        RGBA32(47, 126, 58, 255));
    }

    draw_ground_line(0.0f, 0.0f, length, 0.0f, 0.55f,
                     RGBA32(228, 231, 211, 255));
    draw_ground_line(length, 0.0f, length, width, 0.55f,
                     RGBA32(228, 231, 211, 255));
    draw_ground_line(length, width, 0.0f, width, 0.55f,
                     RGBA32(228, 231, 211, 255));
    draw_ground_line(0.0f, width, 0.0f, 0.0f, 0.55f,
                     RGBA32(228, 231, 211, 255));
    draw_ground_line(length * 0.5f, 0.0f, length * 0.5f, width, 0.38f,
                     RGBA32(228, 231, 211, 255));
    for (i = 0; i < 24; i++) {
        float a0 = (float)i * 2.0f * N64_PI / 24.0f;
        float a1 = (float)(i + 1) * 2.0f * N64_PI / 24.0f;
        float cx = length * 0.5f;
        float cz = width * 0.5f;
        draw_ground_line(cx + cosf(a0) * 9.15f, cz + sinf(a0) * 9.15f,
                         cx + cosf(a1) * 9.15f, cz + sinf(a1) * 9.15f,
                         0.38f, RGBA32(228, 231, 211, 255));
    }
    for (i = 0; i < 2; i++) {
        float x = i == 0 ? 13.0f : length - 13.0f;
        float other_x = i == 0 ? length - 13.0f : 13.0f;
        draw_ground_line(x, 0.0f, x, width, 0.35f,
                         RGBA32(228, 231, 211, 255));
        draw_ground_line(other_x, 0.0f, other_x, width, 0.35f,
                         RGBA32(228, 231, 211, 255));
    }

    draw_world_quad(point3(0.0f, 0.0f, -0.5f),
                    point3(length, 0.0f, -0.5f),
                    point3(length, 3.5f, -0.5f),
                    point3(0.0f, 3.5f, -0.5f),
                    RGBA32(42, 42, 47, 255));
    for (i = 0; i < 35; i++) {
        float x0 = (float)i * length / 35.0f;
        float x1 = (float)(i + 1) * length / 35.0f;
        color_t board = i % 4 == 0 ? RGBA32(208, 36, 32, 255) :
                        i % 4 == 1 ? RGBA32(229, 218, 188, 255) :
                        i % 4 == 2 ? RGBA32(32, 75, 143, 255) :
                                     RGBA32(32, 35, 40, 255);
        draw_world_quad(point3(x0, 0.0f, -0.15f),
                        point3(x1, 0.0f, -0.15f),
                        point3(x1, 1.05f, -0.15f),
                        point3(x0, 1.05f, -0.15f), board);
    }
}

static Point3 player_point(const GamePlayer *player, float side, float height,
                           float forward)
{
    Point3 facing = point3(player->facing_x, 0.0f, player->facing_z);
    Point3 right = point3(-player->facing_z, 0.0f, player->facing_x);
    Point3 base = point3(player->x, 0.0f, player->z);
    return add3(add3(base, scale3(right, side)),
                add3(point3(0.0f, height, 0.0f), scale3(facing, forward)));
}

static void draw_limb(const GamePlayer *player, Point3 start, Point3 end,
                      float width, color_t color)
{
    Point3 right = point3(-player->facing_z, 0.0f, player->facing_x);
    Point3 offset = scale3(right, width * 0.5f);
    draw_world_quad(add3(start, offset), add3(end, offset),
                    subtract3(end, offset), subtract3(start, offset), color);
}

static void draw_player_ring(const GamePlayer *player, int away, int selected)
{
    int segments = selected ? 12 : 8;
    int i;
    color_t color = selected ? RGBA32(35, 90, 255, 255) :
                    away ? RGBA32(235, 35, 35, 245) :
                           RGBA32(31, 79, 239, 245);
    for (i = 0; i < segments; i++) {
        float a0 = (float)i * 2.0f * N64_PI / (float)segments;
        float a1 = (float)(i + 1) * 2.0f * N64_PI / (float)segments;
        draw_ground_line(player->x + cosf(a0) * 0.72f,
                         player->z + sinf(a0) * 0.72f,
                         player->x + cosf(a1) * 0.72f,
                         player->z + sinf(a1) * 0.72f,
                         0.17f, color);
    }
}

static void draw_player(const GamePlayer *player, int team, int number,
                        int away, int selected, int carrying,
                        int foot_pickup, float animation_time)
{
    Point2 screen_position = project(point3(player->x, 0.9f, player->z));
    float stride = player->movement > 0.1f ?
                   sinf(animation_time * 11.0f + (float)number) * 0.18f : 0.0f;
    color_t shirt = team_colors[team];
    color_t shorts = away_colors[team];
    Point3 left_hip = player_point(player, -0.13f, 0.77f, 0.0f);
    Point3 right_hip = player_point(player, 0.13f, 0.77f, 0.0f);
    Point3 left_knee = player_point(player, -0.14f, 0.43f, stride);
    Point3 right_knee = player_point(player, 0.14f, 0.43f, -stride);
    Point3 left_foot = player_point(player, -0.14f, 0.08f, stride * 1.5f);
    Point3 right_foot = player_point(player, 0.14f, 0.08f, -stride * 1.5f);
    Point3 left_shoulder = player_point(player, -0.30f, 1.38f, 0.0f);
    Point3 right_shoulder = player_point(player, 0.30f, 1.38f, 0.0f);
    Point3 left_elbow = player_point(player, -0.38f, 1.08f, stride * 0.35f);
    Point3 right_elbow = player_point(player, 0.38f, 1.08f, -stride * 0.35f);
    Point3 left_hand = player_point(player, -0.40f, 0.91f, 0.0f);
    Point3 right_hand = player_point(player, 0.40f, 0.91f, 0.0f);

    if (foot_pickup) {
        left_knee = player_point(player, -0.14f, 0.38f, 0.08f);
        right_knee = player_point(player, 0.14f, 0.38f, 0.18f);
        left_foot = player_point(player, -0.14f, 0.07f, 0.04f);
        right_foot = player_point(player, 0.14f, 0.10f, 0.58f);
        left_elbow = player_point(player, -0.38f, 0.91f, 0.34f);
        right_elbow = player_point(player, 0.38f, 0.91f, 0.34f);
        left_hand = player_point(player, -0.27f, 0.70f, 0.52f);
        right_hand = player_point(player, 0.27f, 0.70f, 0.52f);
    }

    if (screen_position.depth < 1.0f || screen_position.x < -24.0f ||
        screen_position.x > 344.0f || screen_position.y < -28.0f ||
        screen_position.y > 268.0f) return;

    draw_player_ring(player, away, selected);
    draw_limb(player, left_hip, left_knee, 0.21f, shorts);
    draw_limb(player, right_hip, right_knee, 0.21f, shorts);
    draw_limb(player, left_knee, left_foot, 0.12f, RGBA32(238, 236, 223, 255));
    draw_limb(player, right_knee, right_foot, 0.12f, RGBA32(238, 236, 223, 255));
    draw_limb(player, left_shoulder, left_elbow, 0.15f, shirt);
    draw_limb(player, right_shoulder, right_elbow, 0.15f, shirt);
    draw_limb(player, left_elbow, left_hand, 0.10f, RGBA32(205, 154, 117, 255));
    draw_limb(player, right_elbow, right_hand, 0.10f, RGBA32(205, 154, 117, 255));

    draw_world_quad(player_point(player, -0.28f, 0.88f, -0.15f),
                    player_point(player, 0.28f, 0.88f, -0.15f),
                    player_point(player, 0.28f, 1.46f, -0.15f),
                    player_point(player, -0.28f, 1.46f, -0.15f), shirt);
    draw_world_quad(player_point(player, -0.28f, 0.88f, 0.15f),
                    player_point(player, 0.28f, 0.88f, 0.15f),
                    player_point(player, 0.28f, 1.46f, 0.15f),
                    player_point(player, -0.28f, 1.46f, 0.15f),
                    RGBA32(30, 65, 156, 255));
    draw_world_quad(player_point(player, -0.28f, 1.46f, -0.15f),
                    player_point(player, 0.28f, 1.46f, -0.15f),
                    player_point(player, 0.28f, 1.46f, 0.15f),
                    player_point(player, -0.28f, 1.46f, 0.15f),
                    RGBA32(245, 240, 225, 255));

    {
        Point3 top = player_point(player, 0.0f, 1.82f, 0.0f);
        Point3 left = player_point(player, -0.17f, 1.61f, 0.0f);
        Point3 right = player_point(player, 0.17f, 1.61f, 0.0f);
        Point3 front = player_point(player, 0.0f, 1.63f, 0.19f);
        Point3 back = player_point(player, 0.0f, 1.63f, -0.19f);
        color_t skin = RGBA32(213, 166, 129, 255);
        draw_world_triangle(top, left, front, skin);
        draw_world_triangle(top, front, right, skin);
        draw_world_triangle(top, right, back, skin);
        draw_world_triangle(top, back, left, skin);
        draw_world_triangle(left, front, back, skin);
        draw_world_triangle(front, right, back, skin);
    }
    if (carrying) {
        Point3 ball = player_point(player, 0.0f, 1.05f, 0.48f);
        Point3 top = add3(ball, point3(0.0f, 0.2f, 0.0f));
        Point3 low = add3(ball, point3(0.0f, -0.2f, 0.0f));
        Point3 left = add3(ball, point3(-0.15f, 0.0f, 0.0f));
        Point3 right = add3(ball, point3(0.15f, 0.0f, 0.0f));
        Point3 front = add3(ball, point3(0.0f, 0.0f, 0.13f));
        Point3 back = add3(ball, point3(0.0f, 0.0f, -0.13f));
        color_t brown = RGBA32(157, 79, 40, 255);
        draw_world_triangle(top, left, front, brown);
        draw_world_triangle(top, front, right, brown);
        draw_world_triangle(low, front, left, brown);
        draw_world_triangle(low, right, front, brown);
        draw_world_triangle(top, back, left, RGBA32(191, 111, 61, 255));
        draw_world_triangle(top, right, back, RGBA32(191, 111, 61, 255));
    }
}

static float player_depth(const GamePlayer *player)
{
    Point3 relative = subtract3(point3(player->x, 0.0f, player->z),
                                camera_position);
    return dot3(relative, camera_forward);
}

static void sort_players(PlayerOrder order[GAME_TEAM_SIZE * 2],
                         const GameState *game)
{
    int count = 0;
    int team;
    int player;
    for (team = 0; team < 2; team++) {
        for (player = 0; player < GAME_TEAM_SIZE; player++) {
            int index = count++;
            order[index].team = team;
            order[index].player = player;
            order[index].depth = player_depth(&game->players[team][player]);
            while (index > 0 && order[index].depth > order[index - 1].depth) {
                PlayerOrder swap = order[index];
                order[index] = order[index - 1];
                order[index - 1] = swap;
                index--;
            }
        }
    }
}

static int glyph_index(char character)
{
    if (character >= '0' && character <= '9') return character - '0';
    if (character >= 'A' && character <= 'Z') return 10 + character - 'A';
    if (character >= 'a' && character <= 'z') return 10 + character - 'a';
    return -1;
}

static void draw_screen_rectangle(int x, int y, int width, int height,
                                  color_t color)
{
    if (width <= 0 || height <= 0 || x >= 320 || y >= 240 ||
        x + width <= 0 || y + height <= 0) return;
    if (x < 0) {
        width += x;
        x = 0;
    }
    if (y < 0) {
        height += y;
        y = 0;
    }
    if (x + width > 320) width = 320 - x;
    if (y + height > 240) height = 240 - y;
    if (width <= 0 || height <= 0) return;
    rdpq_set_prim_color(color);
    rdpq_fill_rectangle(x, y, x + width, y + height);
}

static void draw_text(const char *text, int x, int y, int scale, color_t color)
{
    while (*text) {
        int glyph = glyph_index(*text);
        int row;
        if (*text == ' ') {
            x += 4 * scale;
        } else if (*text == '-') {
            draw_screen_rectangle(x, y + 2 * scale, 3 * scale, scale, color);
            x += 4 * scale;
        } else if (*text == ':') {
            draw_screen_rectangle(x + scale, y + scale, scale, scale, color);
            draw_screen_rectangle(x + scale, y + 3 * scale, scale, scale, color);
            x += 4 * scale;
        } else if (glyph >= 0) {
            for (row = 0; row < 5; row++) {
                int column;
                column = 0;
                while (column < 3) {
                    int start;
                    while (column < 3 &&
                           !(font5x3[glyph][row] & (1u << (2 - column))))
                        column++;
                    start = column;
                    while (column < 3 &&
                           (font5x3[glyph][row] & (1u << (2 - column))))
                        column++;
                    if (column > start) {
                        draw_screen_rectangle(x + start * scale,
                                              y + row * scale,
                                              (column - start) * scale,
                                              scale, color);
                    }
                }
            }
            x += 4 * scale;
        } else {
            x += 4 * scale;
        }
        text++;
    }
}

static void draw_screen_circle(int center_x, int center_y, int radius,
                               color_t color)
{
    int i;
    Point2 center = {(float)center_x, (float)center_y, 1.0f};
    for (i = 0; i < 16; i++) {
        float a0 = (float)i * 2.0f * N64_PI / 16.0f;
        float a1 = (float)(i + 1) * 2.0f * N64_PI / 16.0f;
        Point2 first = {
            (float)center_x + cosf(a0) * (float)radius,
            (float)center_y + sinf(a0) * (float)radius, 1.0f
        };
        Point2 second = {
            (float)center_x + cosf(a1) * (float)radius,
            (float)center_y + sinf(a1) * (float)radius, 1.0f
        };
        draw_screen_triangle(center, first, second, color);
    }
}

static const char *role_abbreviation(int player)
{
    if (player == 0) return "GK";
    if (player <= 3) return "FB";
    if (player <= 6) return "HB";
    if (player <= 8) return "MF";
    if (player <= 11) return "HF";
    return "FF";
}

static void draw_minimap(const GameState *game)
{
    int x = 130;
    int y = 198;
    int team;
    int player;
    draw_screen_rectangle(x - 2, y - 2, 62, 39, RGBA32(4, 10, 13, 245));
    draw_screen_rectangle(x, y, 58, 35, RGBA32(38, 105, 49, 255));
    draw_screen_rectangle(x + 28, y + 1, 1, 33,
                          RGBA32(225, 228, 212, 210));
    for (team = 0; team < 2; team++) {
        int kit = team == 0 ? game->home_team : game->away_team;
        for (player = 0; player < GAME_TEAM_SIZE; player++) {
            const GamePlayer *member = &game->players[team][player];
            int px = x + (int)(member->x / GAME_PITCH_LENGTH * 57.0f);
            int py = y + (int)(member->z / GAME_PITCH_WIDTH * 34.0f);
            draw_screen_rectangle(px, py, 2, 2, team_colors[kit]);
        }
    }
    draw_screen_rectangle(x + (int)(game->ball.x / GAME_PITCH_LENGTH * 57.0f),
                          y + (int)(game->ball.z / GAME_PITCH_WIDTH * 34.0f),
                          2, 2, RGBA32(255, 220, 82, 255));
}

static void draw_hud(const GameState *game, int frame)
{
    char score_home[8];
    char score_away[8];
    int seconds = frame / 180;
    int opponent = 0;
    float closest = 1000000.0f;
    int i;

    for (i = 0; i < GAME_TEAM_SIZE; i++) {
        float dx = game->players[1][i].x - game->ball.x;
        float dz = game->players[1][i].z - game->ball.z;
        float distance = dx * dx + dz * dz;
        if (distance < closest) {
            closest = distance;
            opponent = i;
        }
    }
    snprintf(score_home, sizeof(score_home), "%d-%02d", game->team_goals[0],
             game->team_points[0]);
    snprintf(score_away, sizeof(score_away), "%d-%02d", game->team_goals[1],
             game->team_points[1]);

    draw_screen_rectangle(5, 6, 140, 28, RGBA32(8, 12, 18, 240));
    draw_screen_rectangle(5, 6, 3, 28, team_colors[game->home_team]);
    draw_screen_rectangle(142, 6, 3, 28, team_colors[game->away_team]);
    draw_screen_rectangle(11, 10, 3, 17, team_colors[game->home_team]);
    draw_screen_rectangle(76, 10, 3, 17, team_colors[game->away_team]);
    draw_text(team_short_names[game->home_team], 18, 9, 1,
              RGBA32(226, 230, 220, 255));
    draw_text(score_home, 18, 20, 1, RGBA32(255, 232, 169, 255));
    draw_text(team_short_names[game->away_team], 83, 9, 1,
              RGBA32(226, 230, 220, 255));
    draw_text(score_away, 83, 20, 1, RGBA32(255, 232, 169, 255));
    draw_screen_rectangle(225, 9, 42, 20, RGBA32(8, 12, 18, 230));
    {
        char timer[8];
        snprintf(timer, sizeof(timer), "%02d:%02d", (seconds / 60) % 100,
                 seconds % 60);
        draw_text(timer, 229, 16, 1, RGBA32(255, 255, 245, 255));
    }

    draw_screen_circle(294, 18, 14, RGBA32(9, 19, 27, 245));
    draw_screen_circle(294, 18, 11, RGBA32(39, 181, 71, 255));
    draw_screen_circle(294, 18, 7, RGBA32(22, 56, 85, 255));
    draw_text("1ST", 286, 16, 1, RGBA32(255, 255, 244, 255));

    draw_screen_rectangle(4, 209, 101, 27, RGBA32(8, 11, 16, 242));
    draw_screen_rectangle(215, 209, 101, 27, RGBA32(8, 11, 16, 242));
    draw_screen_rectangle(4, 209, 3, 27, team_colors[game->home_team]);
    draw_screen_rectangle(313, 209, 3, 27, team_colors[game->away_team]);
    draw_screen_rectangle(7, 210, 98, 2, RGBA32(106, 112, 117, 255));
    draw_screen_rectangle(215, 210, 98, 2, RGBA32(106, 112, 117, 255));
    {
        char selected[4];
        char away[4];
        snprintf(selected, sizeof(selected), "%02d", game->selected_player + 1);
        snprintf(away, sizeof(away), "%02d", opponent + 1);
        draw_text(role_abbreviation(game->selected_player), 11, 213, 1,
                  RGBA32(232, 185, 59, 255));
        draw_text(selected, 23, 213, 1, RGBA32(255, 239, 195, 255));
        draw_text(player_names[game->selected_player], 11, 223, 1,
                  RGBA32(246, 246, 236, 255));
        draw_text(role_abbreviation(opponent), 222, 213, 1,
                  RGBA32(232, 185, 59, 255));
        draw_text(away, 234, 213, 1, RGBA32(255, 239, 195, 255));
        draw_text(player_names[opponent], 222, 223, 1,
                  RGBA32(246, 246, 236, 255));
    }
    draw_minimap(game);
}

static void draw_goal(float x, float direction)
{
    float center_z = GAME_PITCH_WIDTH * 0.5f;
    float half_width = GAME_GOAL_WIDTH * 0.5f;
    color_t white = RGBA32(235, 235, 220, 255);
    draw_ground_line(x, center_z - half_width, x, center_z + half_width,
                     0.25f, white);
    draw_world_quad(point3(x, 0.0f, center_z - half_width),
                    point3(x, GAME_CROSSBAR_HEIGHT, center_z - half_width),
                    point3(x + direction * 3.0f, GAME_CROSSBAR_HEIGHT,
                           center_z - half_width),
                    point3(x + direction * 3.0f, 0.0f,
                           center_z - half_width), white);
    draw_world_quad(point3(x, 0.0f, center_z + half_width),
                    point3(x, GAME_CROSSBAR_HEIGHT, center_z + half_width),
                    point3(x + direction * 3.0f, GAME_CROSSBAR_HEIGHT,
                           center_z + half_width),
                    point3(x + direction * 3.0f, 0.0f,
                           center_z + half_width), white);
    draw_world_quad(point3(x, GAME_CROSSBAR_HEIGHT, center_z - half_width),
                    point3(x, GAME_CROSSBAR_HEIGHT, center_z + half_width),
                    point3(x + direction * 3.0f, GAME_CROSSBAR_HEIGHT,
                           center_z + half_width),
                    point3(x + direction * 3.0f, GAME_CROSSBAR_HEIGHT,
                           center_z - half_width), white);
}

static void render_frame(const GameState *game, int frame, float animation_time)
{
    PlayerOrder order[GAME_TEAM_SIZE * 2];
    int i;
    update_camera(game);
    sort_players(order, game);

    rdpq_attach(display_get(), NULL);
    rdpq_set_mode_standard();
    rdpq_mode_combiner(RDPQ_COMBINER_FLAT);
    rdpq_clear(RGBA32(129, 192, 221, 255));
    draw_pitch();
    draw_goal(0.0f, -1.0f);
    draw_goal(GAME_PITCH_LENGTH, 1.0f);
    for (i = 0; i < GAME_TEAM_SIZE * 2; i++) {
        int team = order[i].team;
        int player = order[i].player;
        int carrying = game->ball_team == team && game->ball_player == player;
        int foot_pickup = game->pickup_team == team &&
                          game->pickup_player == player;
        draw_player(&game->players[team][player],
                    team == 0 ? game->home_team : game->away_team,
                    player + 1, team == 1,
                    team == 0 && player == game->selected_player,
                    carrying, foot_pickup, animation_time);
    }
    if (game->ball_team < 0) {
        Point3 ball = point3(game->ball.x, game->ball.height, game->ball.z);
        draw_world_triangle(add3(ball, point3(0.0f, 0.3f, 0.0f)),
                            add3(ball, point3(-0.22f, 0.0f, 0.0f)),
                            add3(ball, point3(0.22f, 0.0f, 0.0f)),
                            RGBA32(167, 85, 42, 255));
        draw_world_triangle(add3(ball, point3(0.0f, 0.3f, 0.0f)),
                            add3(ball, point3(0.0f, 0.0f, -0.2f)),
                            add3(ball, point3(0.0f, 0.0f, 0.2f)),
                            RGBA32(205, 128, 68, 255));
    }
    draw_hud(game, frame);
    rdpq_detach_show();
}

int main(void)
{
    GameState game;
    int frame = 0;

    game_init(&game);
    display_init(RESOLUTION_320x240, DEPTH_16_BPP, 2, GAMMA_NONE,
                 ANTIALIAS_RESAMPLE);
    rdpq_init();
    joypad_init();

    while (1) {
        joypad_inputs_t controller;
        joypad_buttons_t pressed;
        GameInput input = {0};
        float move_x;
        float move_z;

        joypad_poll();
        controller = joypad_get_inputs(JOYPAD_PORT_1);
        pressed = joypad_get_buttons_pressed(JOYPAD_PORT_1);
        move_x = (float)controller.stick_y / 85.0f;
        move_z = (float)controller.stick_x / 85.0f;
        if (move_x > 1.0f) move_x = 1.0f;
        if (move_x < -1.0f) move_x = -1.0f;
        if (move_z > 1.0f) move_z = 1.0f;
        if (move_z < -1.0f) move_z = -1.0f;
        input.move_x = move_x;
        input.move_z = move_z;
        input.curve = move_z;
        input.kick = pressed.a;
        input.high_field = pressed.c_left;
        input.pickup = pressed.c_right;
        input.handpass = pressed.b;
        input.tackle = pressed.z;
        input.solo = pressed.c_up;
        input.bounce = pressed.c_down;
        if (pressed.l) game_select_next_player(&game, -1);
        if (pressed.r) game_select_next_player(&game, 1);
        game_update(&game, input, N64_FRAME_TIME);
        render_frame(&game, frame, (float)frame * N64_FRAME_TIME);
        frame++;
    }

    return 0;
}

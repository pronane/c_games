#include "player_model.h"

#include <math.h>
#include <stdlib.h>
#include <string.h>

#define MODEL_PI 3.14159265358979323846f
#define PLAYER_MODEL_MAX_TRIANGLES 10000
#define PLAYER_MODEL_ELLIPSOID_RINGS 8
#define PLAYER_MODEL_RADIAL_SEGMENTS 16

typedef struct MeshBuilder {
    float *vertices;
    float *normals;
    unsigned char *colors;
    int vertex_count;
    int capacity;
    int failed;
} MeshBuilder;

typedef struct TorsoRing {
    float y;
    float radius_x;
    float radius_z;
} TorsoRing;

static const Color TEAM_SHIRTS[GAME_TEAM_COUNT] = {
    {45, 102, 205, 255}, {194, 47, 42, 255},
    {35, 137, 74, 255}, {232, 190, 42, 255}
};
static const Color TEAM_SHORTS[GAME_TEAM_COUNT] = {
    {225, 228, 235, 255}, {238, 235, 220, 255},
    {238, 236, 223, 255}, {38, 55, 130, 255}
};
static const Color SKIN_TONES[PLAYER_MODEL_VARIATIONS] = {
    {235, 194, 159, 255}, {214, 158, 116, 255},
    {177, 119, 83, 255}, {130, 85, 61, 255},
    {91, 62, 49, 255}
};
static const Color HAIR_TONES[PLAYER_MODEL_VARIATIONS] = {
    {104, 67, 42, 255}, {48, 42, 37, 255}, {122, 78, 48, 255},
    {37, 33, 30, 255}, {81, 57, 45, 255}
};
static const float BUILD_WIDTHS[PLAYER_MODEL_VARIATIONS] = {
    0.93f, 1.0f, 1.07f, 0.97f, 1.02f
};
static const float BUILD_HEIGHTS[PLAYER_MODEL_VARIATIONS] = {
    0.97f, 1.02f, 0.98f, 1.045f, 0.95f
};

static Vector3 vector_add(Vector3 a, Vector3 b)
{
    Vector3 result = {a.x + b.x, a.y + b.y, a.z + b.z};
    return result;
}

static Vector3 vector_subtract(Vector3 a, Vector3 b)
{
    Vector3 result = {a.x - b.x, a.y - b.y, a.z - b.z};
    return result;
}

static Vector3 vector_scale(Vector3 value, float scale)
{
    Vector3 result = {value.x * scale, value.y * scale, value.z * scale};
    return result;
}

static float vector_dot(Vector3 a, Vector3 b)
{
    return a.x * b.x + a.y * b.y + a.z * b.z;
}

static Vector3 vector_cross(Vector3 a, Vector3 b)
{
    Vector3 result = {
        a.y * b.z - a.z * b.y,
        a.z * b.x - a.x * b.z,
        a.x * b.y - a.y * b.x
    };
    return result;
}

static Vector3 vector_normalize(Vector3 value)
{
    float length = sqrtf(vector_dot(value, value));
    if (length < 0.0001f) {
        Vector3 up = {0.0f, 1.0f, 0.0f};
        return up;
    }
    return vector_scale(value, 1.0f / length);
}

static int builder_reserve(MeshBuilder *builder, int extra_vertices)
{
    int needed = builder->vertex_count + extra_vertices;
    int capacity = builder->capacity;
    float *vertices;
    float *normals;
    unsigned char *colors;

    if (builder->failed) return 0;
    if (needed <= capacity) return 1;
    while (capacity < needed) capacity *= 2;
    vertices = (float *)realloc(builder->vertices,
                                (size_t)capacity * 3U * sizeof(float));
    if (vertices == NULL) {
        builder->failed = 1;
        return 0;
    }
    builder->vertices = vertices;
    normals = (float *)realloc(builder->normals,
                               (size_t)capacity * 3U * sizeof(float));
    if (normals == NULL) {
        builder->failed = 1;
        return 0;
    }
    builder->normals = normals;
    colors = (unsigned char *)realloc(builder->colors,
                                      (size_t)capacity * 4U);
    if (colors == NULL) {
        builder->failed = 1;
        return 0;
    }
    builder->colors = colors;
    builder->capacity = capacity;
    return 1;
}

static Color shade_color(Color color, Vector3 normal)
{
    float light = 0.70f + 0.20f * fmaxf(normal.y, 0.0f) +
                  0.10f * fmaxf(normal.z, 0.0f);
    Color shaded = {
        (unsigned char)fminf((float)color.r * light, 255.0f),
        (unsigned char)fminf((float)color.g * light, 255.0f),
        (unsigned char)fminf((float)color.b * light, 255.0f),
        color.a
    };
    return shaded;
}

static void builder_vertex(MeshBuilder *builder, Vector3 position,
                           Vector3 normal, Color color)
{
    int vertex;
    Color shaded;

    if (!builder_reserve(builder, 1)) return;
    vertex = builder->vertex_count++;
    normal = vector_normalize(normal);
    shaded = shade_color(color, normal);
    builder->vertices[vertex * 3] = position.x;
    builder->vertices[vertex * 3 + 1] = position.y;
    builder->vertices[vertex * 3 + 2] = position.z;
    builder->normals[vertex * 3] = normal.x;
    builder->normals[vertex * 3 + 1] = normal.y;
    builder->normals[vertex * 3 + 2] = normal.z;
    builder->colors[vertex * 4] = shaded.r;
    builder->colors[vertex * 4 + 1] = shaded.g;
    builder->colors[vertex * 4 + 2] = shaded.b;
    builder->colors[vertex * 4 + 3] = shaded.a;
}

static void builder_triangle(MeshBuilder *builder,
                             Vector3 a, Vector3 normal_a,
                             Vector3 b, Vector3 normal_b,
                             Vector3 c, Vector3 normal_c, Color color)
{
    if (builder->vertex_count / 3 >= PLAYER_MODEL_MAX_TRIANGLES) {
        builder->failed = 1;
        return;
    }
    builder_vertex(builder, a, normal_a, color);
    builder_vertex(builder, b, normal_b, color);
    builder_vertex(builder, c, normal_c, color);
}

static Vector3 ellipsoid_point(Vector3 center, Vector3 radius,
                               float latitude, float longitude)
{
    Vector3 point = {
        center.x + radius.x * sinf(latitude) * cosf(longitude),
        center.y + radius.y * cosf(latitude),
        center.z + radius.z * sinf(latitude) * sinf(longitude)
    };
    return point;
}

static Vector3 ellipsoid_normal(Vector3 radius, float latitude,
                                float longitude)
{
    Vector3 normal = {
        sinf(latitude) * cosf(longitude) / radius.x,
        cosf(latitude) / radius.y,
        sinf(latitude) * sinf(longitude) / radius.z
    };
    return vector_normalize(normal);
}

static void add_ellipsoid(MeshBuilder *builder, Vector3 center, Vector3 radius,
                          Color color, int rings, int slices)
{
    int ring;
    int slice;
    if (rings > PLAYER_MODEL_ELLIPSOID_RINGS)
        rings = PLAYER_MODEL_ELLIPSOID_RINGS;
    if (slices > PLAYER_MODEL_RADIAL_SEGMENTS)
        slices = PLAYER_MODEL_RADIAL_SEGMENTS;
    for (ring = 0; ring < rings; ring++) {
        float lat0 = (float)ring * MODEL_PI / (float)rings;
        float lat1 = (float)(ring + 1) * MODEL_PI / (float)rings;
        for (slice = 0; slice < slices; slice++) {
            float lon0 = (float)slice * 2.0f * MODEL_PI / (float)slices;
            float lon1 = (float)(slice + 1) * 2.0f * MODEL_PI / (float)slices;
            Vector3 p00 = ellipsoid_point(center, radius, lat0, lon0);
            Vector3 p01 = ellipsoid_point(center, radius, lat0, lon1);
            Vector3 p10 = ellipsoid_point(center, radius, lat1, lon0);
            Vector3 p11 = ellipsoid_point(center, radius, lat1, lon1);
            Vector3 n00 = ellipsoid_normal(radius, lat0, lon0);
            Vector3 n01 = ellipsoid_normal(radius, lat0, lon1);
            Vector3 n10 = ellipsoid_normal(radius, lat1, lon0);
            Vector3 n11 = ellipsoid_normal(radius, lat1, lon1);
            builder_triangle(builder, p00, n00, p11, n11, p10, n10, color);
            builder_triangle(builder, p00, n00, p01, n01, p11, n11, color);
        }
    }
}

static void add_cylinder_between(MeshBuilder *builder, Vector3 start,
                                 Vector3 end, float start_radius,
                                 float end_radius, Color color, int slices)
{
    Vector3 axis = vector_normalize(vector_subtract(end, start));
    Vector3 reference = fabsf(axis.y) > 0.92f ?
                        (Vector3){0.0f, 0.0f, 1.0f} :
                        (Vector3){0.0f, 1.0f, 0.0f};
    Vector3 u = vector_normalize(vector_cross(axis, reference));
    Vector3 v = vector_normalize(vector_cross(axis, u));
    Vector3 extended_start = vector_subtract(
        start, vector_scale(axis, start_radius * 0.55f));
    Vector3 extended_end = vector_add(
        end, vector_scale(axis, end_radius * 0.55f));
    int slice;

    if (slices > PLAYER_MODEL_RADIAL_SEGMENTS)
        slices = PLAYER_MODEL_RADIAL_SEGMENTS;
    for (slice = 0; slice < slices; slice++) {
        float a0 = (float)slice * 2.0f * MODEL_PI / (float)slices;
        float a1 = (float)(slice + 1) * 2.0f * MODEL_PI / (float)slices;
        Vector3 radial0 = vector_add(vector_scale(u, cosf(a0)),
                                     vector_scale(v, sinf(a0)));
        Vector3 radial1 = vector_add(vector_scale(u, cosf(a1)),
                                     vector_scale(v, sinf(a1)));
        Vector3 p00 = vector_add(extended_start,
                                 vector_scale(radial0, start_radius));
        Vector3 p01 = vector_add(extended_start,
                                 vector_scale(radial1, start_radius));
        Vector3 p10 = vector_add(extended_end,
                                 vector_scale(radial0, end_radius));
        Vector3 p11 = vector_add(extended_end,
                                 vector_scale(radial1, end_radius));
        builder_triangle(builder, p00, radial0, p01, radial1, p11, radial1, color);
        builder_triangle(builder, p00, radial0, p11, radial1, p10, radial0, color);
    }
}

static Vector3 foot_pickup_point(Vector3 point, int foot_pickup)
{
    if (foot_pickup) {
        float height_from_hips = point.y - 0.9f;
        point.y = 0.9f + height_from_hips * 0.72f;
        point.z += height_from_hips * 0.72f;
    }
    return point;
}

static void add_torso(MeshBuilder *builder, Color shirt, int foot_pickup)
{
    const TorsoRing rings[] = {
        {0.91f, 0.21f, 0.145f}, {1.00f, 0.275f, 0.17f},
        {1.13f, 0.305f, 0.185f}, {1.30f, 0.325f, 0.19f},
        {1.41f, 0.32f, 0.18f}, {1.48f, 0.27f, 0.16f},
        {1.52f, 0.18f, 0.125f}
    };
    int ring;
    int slice;
    const int slices = PLAYER_MODEL_RADIAL_SEGMENTS;

    for (ring = 0; ring < (int)(sizeof(rings) / sizeof(rings[0])) - 1; ring++) {
        for (slice = 0; slice < slices; slice++) {
            float a0 = (float)slice * 2.0f * MODEL_PI / (float)slices;
            float a1 = (float)(slice + 1) * 2.0f * MODEL_PI / (float)slices;
            Vector3 p00 = {rings[ring].radius_x * cosf(a0), rings[ring].y,
                           rings[ring].radius_z * sinf(a0)};
            Vector3 p01 = {rings[ring].radius_x * cosf(a1), rings[ring].y,
                           rings[ring].radius_z * sinf(a1)};
            Vector3 p10 = {rings[ring + 1].radius_x * cosf(a0),
                           rings[ring + 1].y,
                           rings[ring + 1].radius_z * sinf(a0)};
            Vector3 p11 = {rings[ring + 1].radius_x * cosf(a1),
                           rings[ring + 1].y,
                           rings[ring + 1].radius_z * sinf(a1)};
            float slope0 =
                (rings[ring + 1].radius_x - rings[ring].radius_x) /
                (rings[ring + 1].y - rings[ring].y);
            float slope1 = slope0;
            Vector3 n0 = vector_normalize((Vector3){
                cosf(a0), -slope0, sinf(a0)
            });
            Vector3 n1 = vector_normalize((Vector3){
                cosf(a1), -slope1, sinf(a1)
            });
            p00 = foot_pickup_point(p00, foot_pickup);
            p01 = foot_pickup_point(p01, foot_pickup);
            p10 = foot_pickup_point(p10, foot_pickup);
            p11 = foot_pickup_point(p11, foot_pickup);
            builder_triangle(builder, p00, n0, p01, n1, p11, n1, shirt);
            builder_triangle(builder, p00, n0, p11, n1, p10, n0, shirt);
        }
    }
}

static void add_face(MeshBuilder *builder, int variation, int foot_pickup)
{
    Color skin = SKIN_TONES[variation];
    Color hair = HAIR_TONES[variation];
    Color eye_white = {236, 231, 214, 255};
    Color iris = {81, 124, 111, 255};
    Color pupil = {35, 31, 28, 255};
    Color mouth = {111, 54, 49, 255};
    int side;

    add_ellipsoid(builder, foot_pickup_point((Vector3){0.0f, 1.79f, 0.0f},
                                             foot_pickup),
                  (Vector3){0.132f, 0.176f, 0.132f}, skin, 8, 16);
    add_ellipsoid(builder, foot_pickup_point((Vector3){0.0f, 1.925f, -0.025f},
                                             foot_pickup),
                  (Vector3){0.134f, 0.055f, 0.132f}, hair, 6, 16);
    for (side = -1; side <= 1; side += 2) {
        float x = (float)side;
        add_ellipsoid(builder, foot_pickup_point(
                          (Vector3){x * 0.133f, 1.79f, 0.0f}, foot_pickup),
                      (Vector3){0.022f, 0.043f, 0.026f}, skin, 6, 10);
        add_ellipsoid(builder, foot_pickup_point(
                          (Vector3){x * 0.047f, 1.824f, 0.122f},
                          foot_pickup),
                      (Vector3){0.023f, 0.014f, 0.012f},
                      eye_white, 6, 10);
        add_ellipsoid(builder, foot_pickup_point(
                          (Vector3){x * 0.046f, 1.824f, 0.133f},
                          foot_pickup),
                      (Vector3){0.010f, 0.010f, 0.006f},
                      iris, 6, 9);
        add_ellipsoid(builder, foot_pickup_point(
                          (Vector3){x * 0.046f, 1.824f, 0.138f},
                          foot_pickup),
                      (Vector3){0.005f, 0.007f, 0.003f},
                      pupil, 5, 8);
        add_cylinder_between(builder,
            foot_pickup_point((Vector3){x * 0.07f, 1.846f, 0.117f},
                              foot_pickup),
            foot_pickup_point((Vector3){x * 0.026f, 1.849f, 0.126f},
                              foot_pickup),
            0.007f, 0.008f, hair, 6);
    }
    add_cylinder_between(builder,
                         foot_pickup_point((Vector3){0.0f, 1.827f, 0.116f},
                                           foot_pickup),
                         foot_pickup_point((Vector3){0.0f, 1.784f, 0.151f},
                                           foot_pickup),
                         0.014f, 0.018f, skin, 8);
    add_ellipsoid(builder,
                  foot_pickup_point((Vector3){0.0f, 1.781f, 0.152f},
                                    foot_pickup),
                  (Vector3){0.021f, 0.014f, 0.014f}, skin, 6, 10);
    add_cylinder_between(builder,
                         foot_pickup_point((Vector3){-0.027f, 1.735f, 0.128f},
                                           foot_pickup),
                         foot_pickup_point((Vector3){0.027f, 1.735f, 0.128f},
                                           foot_pickup),
                         0.006f, 0.006f, mouth, 6);
}

static void add_player_body(MeshBuilder *builder, int team, int variation,
                            int pose)
{
    Color shirt = TEAM_SHIRTS[team];
    Color shorts = TEAM_SHORTS[team];
    Color skin = SKIN_TONES[variation];
    Color sock = {231, 230, 220, 255};
    Color boot = {36, 38, 43, 255};
    Color stripe = {239, 232, 208, 255};
    int running = (pose >= PLAYER_POSE_RUN_A &&
                   pose <= PLAYER_POSE_RUN_D) ||
                  (pose >= PLAYER_POSE_CARRY_RUN_A &&
                   pose <= PLAYER_POSE_CARRY_RUN_D);
    int jumping = pose == PLAYER_POSE_JUMP;
    int kicking = pose == PLAYER_POSE_KICK;
    int handpassing = pose == PLAYER_POSE_HANDPASS;
    int foot_pickup = pose == PLAYER_POSE_FOOT_PICKUP;
    int carrying = pose == PLAYER_POSE_CARRY ||
                   (pose >= PLAYER_POSE_CARRY_RUN_A &&
                    pose <= PLAYER_POSE_CARRY_RUN_D);
    int gait_index = carrying ? pose - PLAYER_POSE_CARRY_RUN_A :
                     pose - PLAYER_POSE_RUN_A;
    float gait_phase = running ?
        (float)gait_index * MODEL_PI * 0.5f : 0.0f;
    int side;

    add_torso(builder, shirt, foot_pickup);
    add_ellipsoid(builder, foot_pickup_point((Vector3){0.0f, 1.55f, 0.0f},
                                             foot_pickup),
                  (Vector3){0.09f, 0.115f, 0.09f}, skin, 7, 12);
    add_ellipsoid(builder, (Vector3){0.0f, 1.0f, 0.0f},
                  (Vector3){0.285f, 0.155f, 0.175f}, shorts, 7, 12);

    add_face(builder, variation, foot_pickup);

    for (side = -1; side <= 1; side += 2) {
        float phase = gait_phase + (side > 0 ? MODEL_PI : 0.0f);
        float leg_swing = running ? sinf(phase) * 0.38f : 0.0f;
        float foot_lift = running ? fmaxf(cosf(phase), 0.0f) * 0.13f : 0.0f;
        float hip_z = -leg_swing * 0.30f;
        float knee_z = leg_swing * 0.72f;
        float ankle_z = leg_swing * 1.3f;
        Vector3 hip = {(float)side * 0.15f, 0.84f, hip_z};
        Vector3 knee = {(float)side * 0.17f, 0.43f, knee_z};
        Vector3 ankle = {
            (float)side * 0.17f, 0.12f + foot_lift, ankle_z
        };
        Vector3 foot = {
            (float)side * 0.17f, 0.075f + foot_lift, ankle_z + 0.09f
        };
        if (jumping) {
            knee = (Vector3){(float)side * 0.19f, 0.55f,
                             0.12f + (float)side * 0.035f};
            ankle = (Vector3){(float)side * 0.18f, 0.40f, -0.09f};
            foot = (Vector3){(float)side * 0.18f, 0.35f, -0.23f};
        } else if (foot_pickup && side > 0) {
            knee = (Vector3){0.18f, 0.38f, 0.18f};
            ankle = (Vector3){0.18f, 0.14f, 0.43f};
            foot = (Vector3){0.18f, 0.10f, 0.59f};
        } else if (foot_pickup) {
            knee = (Vector3){-0.17f, 0.37f, 0.06f};
            ankle = (Vector3){-0.17f, 0.08f, -0.02f};
            foot = (Vector3){-0.17f, 0.06f, 0.04f};
        } else if (kicking && side > 0) {
            knee = (Vector3){0.19f, 0.58f, 0.20f};
            ankle = (Vector3){0.18f, 0.31f, 0.67f};
            foot = (Vector3){0.18f, 0.29f, 0.92f};
        }
        add_cylinder_between(builder, hip, knee, 0.135f, 0.105f, shorts, 8);
        add_cylinder_between(builder, knee, ankle, 0.083f, 0.065f, sock, 8);
        add_ellipsoid(builder, foot, (Vector3){0.105f, 0.065f, 0.17f},
                      boot, 6, 9);
    }

    for (side = -1; side <= 1; side += 2) {
        Vector3 shoulder = {(float)side * 0.30f, 1.43f, 0.0f};
        Vector3 elbow;
        Vector3 wrist;
        float arm_swing = running ?
            -sinf(gait_phase + (side < 0 ? MODEL_PI : 0.0f)) * 0.22f :
            0.0f;
        if (foot_pickup) {
            elbow = (Vector3){(float)side * 0.39f, 0.93f, 0.35f};
            wrist = (Vector3){(float)side * 0.29f, 0.76f, 0.55f};
        } else if (kicking) {
            elbow = side > 0 ? (Vector3){0.52f, 1.44f, 0.08f} :
                                (Vector3){-0.52f, 1.36f, -0.18f};
            wrist = side > 0 ? (Vector3){0.65f, 1.51f, 0.34f} :
                                (Vector3){-0.63f, 1.27f, -0.42f};
        } else if (handpassing) {
            elbow = side > 0 ? (Vector3){0.35f, 1.29f, 0.30f} :
                                (Vector3){-0.43f, 1.48f, -0.14f};
            wrist = side > 0 ? (Vector3){0.28f, 1.18f, 0.57f} :
                                (Vector3){-0.62f, 1.52f, 0.10f};
        } else if (carrying) {
            elbow = (Vector3){
                (float)side * 0.32f, 1.23f, 0.18f + arm_swing * 0.30f
            };
            wrist = (Vector3){
                (float)side * 0.20f, 1.11f, 0.40f + arm_swing * 0.22f
            };
        } else if (jumping) {
            elbow = (Vector3){(float)side * 0.37f, 1.72f, 0.04f};
            wrist = (Vector3){(float)side * 0.28f, 2.02f, 0.16f};
        } else {
            elbow = (Vector3){
                (float)side * 0.42f, 1.20f, arm_swing
            };
            wrist = (Vector3){
                (float)side * 0.39f, 0.97f, -arm_swing * 0.68f
            };
        }
        add_cylinder_between(builder, shoulder, elbow, 0.115f, 0.09f, shirt, 8);
        {
            Vector3 sleeve_start = vector_add(
                shoulder,
                vector_scale(vector_subtract(elbow, shoulder), 0.76f));
            Vector3 sleeve_end = vector_add(
                shoulder,
                vector_scale(vector_subtract(elbow, shoulder), 0.86f));
            add_cylinder_between(builder, sleeve_start, sleeve_end,
                                 0.095f, 0.092f, stripe, 10);
        }
        add_cylinder_between(builder, elbow, wrist, 0.073f, 0.058f, skin, 8);
        add_ellipsoid(builder, wrist, (Vector3){0.055f, 0.034f, 0.07f},
                      skin, 5, 8);
        {
            int finger;
            for (finger = 0; finger < 4; finger++) {
                float spread = ((float)finger - 1.5f) * 0.022f;
                Vector3 finger_start = {
                    wrist.x + spread, wrist.y - 0.012f, wrist.z + 0.035f
                };
                Vector3 finger_end = {
                    wrist.x + spread * 1.35f, wrist.y - 0.022f,
                    wrist.z + 0.092f - fabsf(spread) * 0.35f
                };
                add_cylinder_between(builder, finger_start, finger_end,
                                     0.010f, 0.007f, skin, 6);
            }
            add_cylinder_between(builder,
                (Vector3){wrist.x + (float)side * 0.038f, wrist.y - 0.005f,
                          wrist.z + 0.012f},
                (Vector3){wrist.x + (float)side * 0.064f, wrist.y - 0.017f,
                          wrist.z + 0.045f},
                0.012f, 0.008f, skin, 6);
        }
    }
}

static Model build_player_model(int team, int variation, int pose)
{
    MeshBuilder builder = {0};
    Mesh mesh = {0};
    Model model = {0};
    float width = BUILD_WIDTHS[variation];
    float height = BUILD_HEIGHTS[variation];
    int vertex;

    builder.capacity = 2048;
    builder.vertices = (float *)malloc((size_t)builder.capacity * 3U *
                                       sizeof(float));
    builder.normals = (float *)malloc((size_t)builder.capacity * 3U *
                                      sizeof(float));
    builder.colors = (unsigned char *)malloc((size_t)builder.capacity * 4U);
    if (builder.vertices == NULL || builder.normals == NULL ||
        builder.colors == NULL) {
        builder.failed = 1;
    } else {
        add_player_body(&builder, team, variation, pose);
        for (vertex = 0; vertex < builder.vertex_count; vertex++) {
            Vector3 normal = {
                builder.normals[vertex * 3] / width,
                builder.normals[vertex * 3 + 1] / height,
                builder.normals[vertex * 3 + 2] / width
            };
            float normal_length = sqrtf(vector_dot(normal, normal));
            builder.vertices[vertex * 3] *= width;
            builder.vertices[vertex * 3 + 1] *= height;
            builder.vertices[vertex * 3 + 2] *= width;
            if (pose == PLAYER_POSE_JUMP) {
                builder.vertices[vertex * 3 + 1] += 0.30f;
            }
            if (normal_length > 0.0001f) {
                normal = vector_scale(normal, 1.0f / normal_length);
                builder.normals[vertex * 3] = normal.x;
                builder.normals[vertex * 3 + 1] = normal.y;
                builder.normals[vertex * 3 + 2] = normal.z;
            }
        }
    }

    if (!builder.failed && builder.vertex_count > 0) {
        mesh.vertexCount = builder.vertex_count;
        mesh.triangleCount = builder.vertex_count / 3;
        mesh.vertices = builder.vertices;
        mesh.normals = builder.normals;
        mesh.colors = builder.colors;
        UploadMesh(&mesh, false);
        model = LoadModelFromMesh(mesh);
        if (!IsModelValid(model)) {
            UnloadModel(model);
            model = (Model){0};
        } else {
            builder.vertices = NULL;
            builder.normals = NULL;
            builder.colors = NULL;
        }
    }

    free(builder.vertices);
    free(builder.normals);
    free(builder.colors);
    return model;
}

int player_models_init(PlayerModels *players)
{
    int team;
    int variation;
    int pose;
    memset(players, 0, sizeof(*players));
    for (team = 0; team < GAME_TEAM_COUNT; team++) {
        for (variation = 0; variation < PLAYER_MODEL_VARIATIONS; variation++) {
            for (pose = 0; pose < PLAYER_POSE_COUNT; pose++) {
                players->models[team][variation][pose] =
                    build_player_model(team, variation, pose);
                if (!IsModelValid(players->models[team][variation][pose])) {
                    TraceLog(LOG_ERROR, "Could not build a 3D footballer model.");
                    player_models_unload(players);
                    return 0;
                }
                players->valid[team][variation][pose] = 1;
            }
        }
    }
    return 1;
}

void player_models_unload(PlayerModels *players)
{
    int team;
    int variation;
    int pose;
    for (team = 0; team < GAME_TEAM_COUNT; team++) {
        for (variation = 0; variation < PLAYER_MODEL_VARIATIONS; variation++) {
            for (pose = 0; pose < PLAYER_POSE_COUNT; pose++) {
                if (players->valid[team][variation][pose]) {
                    UnloadModel(players->models[team][variation][pose]);
                    players->valid[team][variation][pose] = 0;
                }
            }
        }
    }
}

void player_models_draw(const PlayerModels *players, const GamePlayer *player,
                        int team, int number, int pose)
{
    int variation = (number - 1) % PLAYER_MODEL_VARIATIONS;
    float facing_x = player->facing_x;
    float facing_z = player->facing_z;
    float angle;
    Vector3 position = {player->x, 0.0f, player->z};
    Vector3 rotation_axis = {0.0f, 1.0f, 0.0f};
    Vector3 scale = {0.96f, 0.96f, 0.96f};

    if (team < 0 || team >= GAME_TEAM_COUNT ||
        pose < 0 || pose >= PLAYER_POSE_COUNT) return;
    if (facing_x * facing_x + facing_z * facing_z < 0.0001f) {
        facing_x = 1.0f;
        facing_z = 0.0f;
    }
    angle = atan2f(facing_x, facing_z) * (180.0f / MODEL_PI);
    DrawModelEx(players->models[team][variation][pose], position,
                rotation_axis, angle, scale, WHITE);
}

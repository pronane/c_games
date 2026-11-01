// Dev tool: renders a player GLB with the game's own lit + GPU-skinning shaders (copied from src/stadium.c) into
// comparison sheets: turntable, close-ups, wireframe, animation strips, all six kits.  Also times the load.
//   ./modelview <player.glb> <kit_dir> <out_prefix> [label]
// build: gcc -std=c99 -O2 tools/modelview.c -I$RAYLIB/src -L$RAYLIB/src -lraylib -lGL -lm -lpthread -ldl -lrt -lX11
#include "raylib.h"
#include "raymath.h"
#include "rlgl.h"
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

static const char *LIT_FS =
"#version 330\n"
"in vec3 fragPosition; in vec2 fragTexCoord; in vec4 fragColor; in vec3 fragNormal;\n"
"uniform sampler2D texture0; uniform vec4 colDiffuse;\n"
"uniform vec3 lightDir; uniform vec3 sunColor; uniform vec3 skyColor; uniform vec3 groundColor;\n"
"uniform vec3 viewPos; uniform int wire;\n"
"out vec4 finalColor;\n"
"void main(){\n"
"  if (wire == 1) { finalColor = vec4(0.08,0.09,0.12,1.0); return; }\n"
"  vec4 tex = texture(texture0, fragTexCoord)*colDiffuse*fragColor;\n"
"  if (tex.a < 0.02) discard;\n"
"  vec3 n = normalize(fragNormal); if (!gl_FrontFacing) n = -n;\n"
"  float ndl = max(dot(n,-lightDir), 0.0);\n"
"  vec3 amb = mix(groundColor, skyColor, n.y*0.5 + 0.5);\n"
"  vec3 v = normalize(viewPos - fragPosition);\n"
"  float rim = pow(1.0 - max(dot(n, v), 0.0), 3.0)*0.12;\n"
"  vec3 col = tex.rgb*(amb + sunColor*ndl) + rim*skyColor*tex.rgb;\n"
"  finalColor = vec4(col, tex.a);\n"
"}\n";
static const char *SKIN_VS =
"#version 330\n"
"in vec3 vertexPosition; in vec2 vertexTexCoord; in vec3 vertexNormal; in vec4 vertexColor;\n"
"in vec4 vertexBoneIds; in vec4 vertexBoneWeights;\n"
"#define MAX_BONE_NUM 64\n"
"uniform mat4 boneMatrices[MAX_BONE_NUM];\n"
"uniform mat4 mvp; uniform mat4 matModel; uniform mat4 matNormal;\n"
"out vec3 fragPosition; out vec2 fragTexCoord; out vec4 fragColor; out vec3 fragNormal;\n"
"void main(){\n"
"  mat4 sk = vertexBoneWeights.x*boneMatrices[int(vertexBoneIds.x)] + vertexBoneWeights.y*boneMatrices[int(vertexBoneIds.y)]\n"
"          + vertexBoneWeights.z*boneMatrices[int(vertexBoneIds.z)] + vertexBoneWeights.w*boneMatrices[int(vertexBoneIds.w)];\n"
"  vec4 p = sk*vec4(vertexPosition,1.0);\n"
"  fragPosition = vec3(matModel*p); fragTexCoord = vertexTexCoord; fragColor = vertexColor;\n"
"  fragNormal = normalize(vec3(matNormal*vec4(mat3(sk)*vertexNormal,0.0)));\n"
"  gl_Position = mvp*p;\n"
"}\n";

static Model model; static ModelAnimation *anims; static int animCount; static Shader sh; static int locView, locWire;
static Texture2D kits[6];
static int partVariant[512], partRole[512], nParts = 0, nVariants = 1, curVariant = 0;   /* .parts sidecar (squad GLBs) */
enum { R_BODY, R_KIT, R_HAIR, R_BROWS, R_LASHES, R_EYES };
static void loadParts(const char *glb)
{
    char path[600]; snprintf(path, sizeof path, "%.*s.parts", (int)(strlen(glb) - 4), glb);
    FILE *f = fopen(path, "r"); if (!f) return;
    char line[256]; int i, v; char role[32];
    while (fgets(line, sizeof line, f)) {
        if (line[0] == '#' || sscanf(line, "%d %d %31s", &i, &v, role) != 3 || i < 0 || i >= 512) continue;
        partVariant[i] = v; if (v + 1 > nVariants) nVariants = v + 1;
        partRole[i] = !strcmp(role, "kit") ? R_KIT : !strcmp(role, "hair") ? R_HAIR : !strcmp(role, "brows") ? R_BROWS :
                      !strcmp(role, "lashes") ? R_LASHES : !strcmp(role, "eyes") ? R_EYES : R_BODY;
        if (i + 1 > nParts) nParts = i + 1;
    }
    fclose(f);
} static const char *KITS[6] = { "home", "away", "gk_home", "gk_away", "referee", "umpire" };

static int findAnim(const char *n) { for (int i = 0; i < animCount; i++) if (!strcmp(anims[i].name, n)) return i; return -1; }
static int findBone(const char *n) { for (int i = 0; i < model.boneCount; i++) if (!strcmp(model.bones[i].name, n)) return i; return 0; }
static Vector3 boneAt(const char *clip, float frac, const char *bone)    /* model-space bone position in a pose */
{
    int a = findAnim(clip); if (a < 0) return (Vector3){ 0, 1.5f, 0 };
    int f = (int)(frac * (anims[a].frameCount - 1));
    return anims[a].framePoses[f][findBone(bone)].translation;
}

static void pose(int a, float frac)
{
    if (a < 0) return;
    int f = (int)(frac * (anims[a].frameCount - 1));
    UpdateModelAnimationBones(model, anims[a], f);
}

static void drawAt(Camera3D cam, Vector3 p, float yaw, int kit, int wire)
{
    SetShaderValue(sh, locView, &cam.position, SHADER_UNIFORM_VEC3);
    int w = wire; SetShaderValue(sh, locWire, &w, SHADER_UNIFORM_INT);
    if (wire) rlEnableWireMode();
    if (nParts) {                                   /* squad GLB: only this variant's meshes, kit on the garments */
        Matrix m = MatrixMultiply(MatrixRotateY(yaw * DEG2RAD), MatrixTranslate(p.x, p.y, p.z));
        for (int i = 0; i < model.meshCount && i < nParts; i++) {
            if (partVariant[i] != curVariant) continue;
            Material mat = model.materials[model.meshMaterial[i]];
            if (partRole[i] == R_KIT) mat.maps[MATERIAL_MAP_DIFFUSE].texture = kits[kit];
            DrawMesh(model.meshes[i], mat, MatrixMultiply(m, model.transform));
        }
    } else {
        model.materials[model.meshMaterial[0]].maps[MATERIAL_MAP_DIFFUSE].texture = kits[kit];
        DrawModelEx(model, p, (Vector3){ 0, 1, 0 }, yaw, (Vector3){ 1, 1, 1 }, WHITE);
    }
    if (wire) rlDisableWireMode();
}

static Camera3D camLook(Vector3 target, float yawDeg, float pitchDeg, float dist, float fovy)
{
    Camera3D c = { 0 };
    float y = yawDeg * DEG2RAD, p = pitchDeg * DEG2RAD;
    c.target = target;
    c.position = Vector3Add(target, (Vector3){ sinf(y) * cosf(p) * dist, sinf(p) * dist, cosf(y) * cosf(p) * dist });
    c.up = (Vector3){ 0, 1, 0 }; c.fovy = fovy; c.projection = CAMERA_PERSPECTIVE;
    return c;
}

static void ground(Vector3 p) { DrawCylinder((Vector3){ p.x, 0.001f, p.z }, 0.42f, 0.42f, 0.002f, 24, (Color){ 0, 0, 0, 60 }); }

static void sheet(const char *path, const char *label, int cols, int rows, int cw, int ch, void (*cell)(int i, int cw, int ch))
{
    RenderTexture2D rt = LoadRenderTexture(cols * cw, rows * ch + 30);
    BeginTextureMode(rt);
    ClearBackground(getenv("MV_BG") ? (Color){ 255, 0, 255, 255 } : (Color){ 92, 132, 76, 255 });
    for (int i = 0; i < cols * rows; i++) {
        rlViewport((i % cols) * cw, (rows - 1 - i / cols) * ch, cw, ch);
        cell(i, cw, ch);
    }
    rlViewport(0, 0, cols * cw, rows * ch + 30);
    EndTextureMode();
    Image im = LoadImageFromTexture(rt.texture); ImageFlipVertical(&im);
    ImageDrawRectangle(&im, 0, 0, cols * cw, 30, (Color){ 20, 22, 28, 255 });
    ImageDrawText(&im, label, 8, 5, 20, RAYWHITE);
    ExportImage(im, path); UnloadImage(im); UnloadRenderTexture(rt);
}

static int gCw, gCh;
static void begin3D(Camera3D c, int cw, int ch)
{
    rlDrawRenderBatchActive();
    rlMatrixMode(RL_PROJECTION); rlLoadIdentity();
    double top = 0.05 * tan(c.fovy * 0.5 * DEG2RAD), right = top * (double)cw / ch;
    rlFrustum(-right, right, -top, top, 0.05, 100.0);
    rlMatrixMode(RL_MODELVIEW); rlLoadIdentity();
    Matrix v = MatrixLookAt(c.position, c.target, c.up); rlMultMatrixf(MatrixToFloat(v));
    rlEnableDepthTest();
}
static void end3D(void) { rlDrawRenderBatchActive(); rlMatrixMode(RL_PROJECTION); rlLoadIdentity(); rlMatrixMode(RL_MODELVIEW); rlLoadIdentity(); }

static void cellTurn(int i, int cw, int ch)      /* 8 views, idle */
{
    Camera3D c = camLook((Vector3){ 0, 0.95f, 0 }, 25 + i * 45.0f, 8, 3.3f, 36);
    pose(findAnim("idle"), 0.0f);
    begin3D(c, cw, ch); ground((Vector3){ 0 }); drawAt(c, (Vector3){ 0 }, 0, 0, 0); end3D();
}
static void cellClose(int i, int cw, int ch)     /* face 3/4, front, profile, back of head */
{
    float yaws[4] = { 30, 0, 90, 180 };
    Vector3 h = boneAt("idle", 0.0f, "head"); h.y += 0.07f; h.z += 0.03f;
    Camera3D c = camLook(h, yaws[i], 4, 0.85f, 30);
    pose(findAnim("idle"), 0.0f);
    begin3D(c, cw, ch); drawAt(c, (Vector3){ 0 }, 0, 0, 0); end3D();
}
static void cellWire(int i, int cw, int ch)      /* full body + head, wire over shaded */
{
    Vector3 h = boneAt("idle", 0.0f, "head"); h.y += 0.07f; h.z += 0.03f;
    Camera3D c = i == 0 ? camLook((Vector3){ 0, 0.95f, 0 }, 30, 8, 3.2f, 36) : camLook(h, 30, 4, 0.85f, 30);
    if (i == 2) c = camLook(boneAt("idle", 0.0f, "hand_l"), 60, 20, 0.6f, 30);
    if (i == 3) c = camLook(Vector3Add(boneAt("idle", 0.0f, "foot_l"), (Vector3){ 0, 0.0f, 0.05f }), 70, 15, 0.8f, 30);
    pose(findAnim("idle"), 0.0f);
    begin3D(c, cw, ch);
    drawAt(c, (Vector3){ 0 }, 0, 0, 0);
    rlSetLineWidth(1.0f); drawAt(c, (Vector3){ 0 }, 0, 0, 1);
    end3D();
}
static const char *CLIPS[8] = { "run", "drop_kick", "catch", "solo", "hand_pass", "dive_save", "celebrate_jump", "knocked_down" };
static void cellAnim(int i, int cw, int ch)      /* 8 clips x 6 frames */
{
    int clip = i / 6, k = i % 6;
    Camera3D c = camLook((Vector3){ 0, 0.9f, 0 }, 35, 10, 3.6f, 38);
    pose(findAnim(CLIPS[clip]), k / 5.0f);
    begin3D(c, cw, ch); ground((Vector3){ 0 }); drawAt(c, (Vector3){ 0 }, 0, 0, 0); end3D();
}
static const char *CLOSE_CLIPS[4] = { "catch", "drop_kick", "hand_pass", "dive_save" };
static const float CLOSE_T[4] = { 0.45f, 0.42f, 0.4f, 0.5f };
static void cellDeform(int i, int cw, int ch)    /* joint close-ups mid-move: shoulder, elbow, hip, knee */
{
    int a = findAnim(CLOSE_CLIPS[i]);
    pose(a, CLOSE_T[i]);
    Camera3D c = camLook((Vector3){ 0, 1.0f, 0.1f }, 50 + i * 25, 12, 1.9f, 34);
    begin3D(c, cw, ch); drawAt(c, (Vector3){ 0 }, 0, 0, 0); end3D();
}
static void cellFace(int i, int cw, int ch)
{
    curVariant = i % nVariants;
    pose(findAnim("idle"), 0.0f);
    Vector3 h = boneAt("idle", 0.0f, "head"); h.y += 0.075f; h.z += 0.03f;
    float fd = getenv("MV_FACE_DIST") ? (float)atof(getenv("MV_FACE_DIST")) : 0.62f;
    float fy = getenv("MV_FACE_YAW") ? (float)atof(getenv("MV_FACE_YAW")) : 25.0f;
    float fp = getenv("MV_FACE_PITCH") ? (float)atof(getenv("MV_FACE_PITCH")) : 4.0f;
    h.y += getenv("MV_FACE_DY") ? (float)atof(getenv("MV_FACE_DY")) : 0.0f;
    Camera3D c = camLook(h, fy, fp, fd, 30);
    begin3D(c, cw, ch); drawAt(c, (Vector3){ 0 }, 0, 0, 0); end3D();
}
static void cellSquad(int i, int cw, int ch)     /* every look: face close-up row + full body row */
{
    curVariant = i % nVariants;
    pose(findAnim("idle"), 0.0f);
    if (i < nVariants) {
        Vector3 h = boneAt("idle", 0.0f, "head"); h.y += 0.07f; h.z += 0.03f;
        Camera3D c = camLook(h, 25, 4, 0.75f, 30);
        begin3D(c, cw, ch); drawAt(c, (Vector3){ 0 }, 0, 0, 0); end3D();
    } else {
        Camera3D c = camLook((Vector3){ 0, 0.95f, 0 }, 25, 8, 3.0f, 36);
        begin3D(c, cw, ch); ground((Vector3){ 0 }); drawAt(c, (Vector3){ 0 }, 0, (i / nVariants) % 2 ? 1 : 0, 0); end3D();
    }
    curVariant = 0;
}
static void cellKits(int i, int cw, int ch)
{
    Camera3D c = camLook((Vector3){ 0, 0.95f, 0 }, 25, 8, 3.2f, 36);
    pose(findAnim("idle"), 0.3f);
    begin3D(c, cw, ch); ground((Vector3){ 0 }); drawAt(c, (Vector3){ 0 }, 0, i, 0); end3D();
}

int main(int argc, char **argv)
{
    if (argc < 4) { printf("usage: modelview player.glb kit_dir out_prefix [label]\n"); return 1; }
    const char *label = argc > 4 ? argv[4] : argv[1];
    SetTraceLogLevel(LOG_WARNING);
    SetConfigFlags(FLAG_WINDOW_HIDDEN | FLAG_MSAA_4X_HINT);
    InitWindow(640, 480, "modelview");
    double t0 = GetTime();
    model = LoadModel(argv[1]);
    loadParts(argv[1]);
    if (getenv("MV_VARIANT")) curVariant = atoi(getenv("MV_VARIANT"));
    anims = LoadModelAnimations(argv[1], &animCount);
    double tLoad = GetTime() - t0;
    int valid = 0; for (int i = 0; i < animCount; i++) valid += IsModelAnimationValid(model, anims[i]);
    int verts = 0, tris = 0; for (int m = 0; m < model.meshCount; m++) { verts += model.meshes[m].vertexCount; tris += model.meshes[m].triangleCount; }
    printf("LOAD %s: %.3f s, %d meshes, %d verts, %d tris, %d bones, %d/%d clips valid\n", argv[1], tLoad, model.meshCount, verts, tris,
           model.boneCount, valid, animCount);
    sh = LoadShaderFromMemory(SKIN_VS, LIT_FS);
    locView = GetShaderLocation(sh, "viewPos"); locWire = GetShaderLocation(sh, "wire");
    Vector3 sun = Vector3Normalize((Vector3){ -0.42f, -0.74f, -0.52f }), sc = { 0.98f, 0.93f, 0.82f }, sky = { 0.50f, 0.56f, 0.66f }, gnd = { 0.30f, 0.32f, 0.26f };
    SetShaderValue(sh, GetShaderLocation(sh, "lightDir"), &sun, SHADER_UNIFORM_VEC3);
    SetShaderValue(sh, GetShaderLocation(sh, "sunColor"), &sc, SHADER_UNIFORM_VEC3);
    SetShaderValue(sh, GetShaderLocation(sh, "skyColor"), &sky, SHADER_UNIFORM_VEC3);
    SetShaderValue(sh, GetShaderLocation(sh, "groundColor"), &gnd, SHADER_UNIFORM_VEC3);
    for (int m = 0; m < model.materialCount; m++) model.materials[m].shader = sh;
    for (int k = 0; k < 6; k++) {
        kits[k] = LoadTexture(TextFormat("%s/kit_%s.png", argv[2], KITS[k]));
        GenTextureMipmaps(&kits[k]); SetTextureFilter(kits[k], TEXTURE_FILTER_TRILINEAR);
    }
    // the eye mesh of the shipped model keeps its own texture
    for (int m = 1; m < model.meshCount; m++) if (model.meshMaterial[m] == model.meshMaterial[0]) model.meshMaterial[m] = model.meshMaterial[0];
    char p[512];
    snprintf(p, sizeof p, "%s_turntable.png", argv[3]); sheet(p, TextFormat("%s - turntable (idle)", label), 8, 1, 240, 420, cellTurn);
    snprintf(p, sizeof p, "%s_closeup.png", argv[3]); sheet(p, TextFormat("%s - head and face", label), 4, 1, 320, 360, cellClose);
    snprintf(p, sizeof p, "%s_wire.png", argv[3]); sheet(p, TextFormat("%s - wireframe: %d tris, %d verts", label, tris, verts), 4, 1, 360, 420, cellWire);
    snprintf(p, sizeof p, "%s_anims.png", argv[3]); sheet(p, TextFormat("%s - run, drop kick, catch, solo, hand pass, dive save, celebrate, knocked down", label), 6, 8, 200, 250, cellAnim);
    snprintf(p, sizeof p, "%s_deform.png", argv[3]); sheet(p, TextFormat("%s - joints mid-move: catch, drop kick, hand pass, dive", label), 4, 1, 360, 420, cellDeform);
    if (nParts && getenv("MV_FACES")) {          /* one big face per look (for Blender comparisons) */
        snprintf(p, sizeof p, "%s_faces.png", argv[3]); sheet(p, TextFormat("%s - faces", label), nVariants, 1, 420, 420, cellFace);
    }
    if (nParts) { snprintf(p, sizeof p, "%s_squad.png", argv[3]); sheet(p, TextFormat("%s - %d looks (home and away kit)", label, nVariants), nVariants, 2, 220, 300, cellSquad); }
    snprintf(p, sizeof p, "%s_kits.png", argv[3]); sheet(p, TextFormat("%s - kits", label), 6, 1, 240, 420, cellKits);
    CloseWindow();
    return 0;
}

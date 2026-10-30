/*******************************************************************************************
 *  Image → 3D Mesh  +  Classic Console Sprite Generator
 *
 *  Modes:
 *    1. 3D Extruded Model  (with live preview + Run Bob/Lean animation)
 *    2. Sprite / Pixel Art for NES, SNES, Mega Drive, N64, PS1, Dreamcast, GameCube, PS2
 *
 *  Dependencies: raylib + raygui.h
 *******************************************************************************************/

#include "raylib.h"
#include "raymath.h"

#define RAYGUI_IMPLEMENTATION
#include "raygui.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <stdbool.h>

//----------------------------------------------------------------------------------
// Limits
//----------------------------------------------------------------------------------
#define MAX_VERTS   500000
#define MAX_INDICES 1500000
#define MAX_PATH    512
#define MAX_STATUS  256

//----------------------------------------------------------------------------------
// Types
//----------------------------------------------------------------------------------
typedef struct { float x, y, z; } Vec3;
typedef struct { float u, v; } Vec2;

typedef struct {
    Vec3 *pos;
    Vec3 *norm;
    Vec2 *uv;
    unsigned int *indices;
    int vertCount;
    int indexCount;
} MeshData;

typedef enum {
    MODE_3D_MODEL = 0,
    MODE_SPRITE
} GenMode;

typedef enum {
    PLAT_NES = 0,
    PLAT_SNES,
    PLAT_MEGADRIVE,
    PLAT_N64,
    PLAT_PS1,
    PLAT_DREAMCAST,
    PLAT_GAMECUBE,
    PLAT_PS2,
    PLAT_COUNT
} Platform;

typedef struct {
    const char *name;
    int         targetSize;
    int         maxColors;
    bool        nearestNeighbor;
    float       contrastBoost;
} PlatformPreset;

//----------------------------------------------------------------------------------
// Platform presets
//----------------------------------------------------------------------------------
static const PlatformPreset presets[PLAT_COUNT] = {
    { "NES",        64,   16,  true,  1.15f },
    { "SNES",       128,  64,  true,  1.10f },
    { "Mega Drive", 128,  64,  true,  1.12f },
    { "N64",        256, 256,  true,  1.05f },
    { "PS1",        256, 256,  true,  1.08f },
    { "Dreamcast",  384, 512,  false, 1.02f },
    { "GameCube",   384, 512,  false, 1.00f },
    { "PS2",        512, 1024, false, 1.00f }
};

static const char *platformNames[PLAT_COUNT] = {
    "NES", "SNES", "Mega Drive", "N64", "PS1", "Dreamcast", "GameCube", "PS2"
};

//----------------------------------------------------------------------------------
// Globals
//----------------------------------------------------------------------------------
static float g_depth = 0.12f;
static int   g_step  = 3;

//----------------------------------------------------------------------------------
// Color quantizer
//----------------------------------------------------------------------------------
static Image QuantizeImage(Image src, int maxColors, float contrast)
{
    Image img = ImageCopy(src);
    if (img.data == NULL) return img;

    if (img.format != PIXELFORMAT_UNCOMPRESSED_R8G8B8A8)
        ImageFormat(&img, PIXELFORMAT_UNCOMPRESSED_R8G8B8A8);

    unsigned char *pixels = (unsigned char *)img.data;
    int total = img.width * img.height;
    int channels = 4;

    if (contrast != 1.0f) {
        for (int i = 0; i < total; i++) {
            int idx = i * channels;
            for (int c = 0; c < 3; c++) {
                float v = pixels[idx + c] / 255.0f;
                v = (v - 0.5f) * contrast + 0.5f;
                pixels[idx + c] = (unsigned char)(v < 0.0f ? 0 : (v > 1.0f ? 255 : (int)(v * 255.0f)));
            }
        }
    }

    int bits = (maxColors <= 16) ? 2 : (maxColors <= 64) ? 3 : (maxColors <= 256) ? 4 : 5;
    int mask = (0xFF << (8 - bits)) & 0xFF;

    for (int i = 0; i < total; i++) {
        int idx = i * channels;
        if (pixels[idx + 3] < 16) {
            pixels[idx] = pixels[idx+1] = pixels[idx+2] = 0;
            pixels[idx+3] = 0;
            continue;
        }
        for (int c = 0; c < 3; c++) {
            unsigned char v = pixels[idx + c] & mask;
            pixels[idx + c] = (unsigned char)(v | (v >> bits));
        }
    }
    return img;
}

//----------------------------------------------------------------------------------
// Sprite generation
//----------------------------------------------------------------------------------
static Image GenerateSprite(const Image *src, Platform plat)
{
    if (!src || !src->data) return (Image){0};

    const PlatformPreset *p = &presets[plat];
    float aspect = (float)src->width / (float)src->height;

    int dstW, dstH;
    if (src->width >= src->height) {
        dstW = p->targetSize;
        dstH = (int)(p->targetSize / aspect + 0.5f);
    } else {
        dstH = p->targetSize;
        dstW = (int)(p->targetSize * aspect + 0.5f);
    }
    if (dstW < 8) dstW = 8;
    if (dstH < 8) dstH = 8;

    Image work = ImageCopy(*src);
    if (p->nearestNeighbor) ImageResizeNN(&work, dstW, dstH);
    else                    ImageResize(&work, dstW, dstH);

    Image result = QuantizeImage(work, p->maxColors, p->contrastBoost);
    UnloadImage(work);
    return result;
}

//----------------------------------------------------------------------------------
// 3D Mesh building
//----------------------------------------------------------------------------------
static inline bool IsSolidPixel(const Image *img, int x, int y)
{
    if (x < 0 || x >= img->width || y < 0 || y >= img->height) return false;
    Color c = GetImageColor(*img, x, y);
    if (c.a < 128) return false;
    return ((c.r + c.g + c.b) / 3) > 35;
}

static int AddVertex(MeshData *m, float x, float y, float z,
                     float nx, float ny, float nz, float u, float v)
{
    if (m->vertCount >= MAX_VERTS) return -1;
    int i = m->vertCount++;
    m->pos[i]  = (Vec3){x, y, z};
    m->norm[i] = (Vec3){nx, ny, nz};
    m->uv[i]   = (Vec2){u, v};
    return i;
}

static void AddQuad(MeshData *m, int a, int b, int c, int d)
{
    if (m->indexCount + 6 > MAX_INDICES) return;
    m->indices[m->indexCount++] = (unsigned int)a;
    m->indices[m->indexCount++] = (unsigned int)b;
    m->indices[m->indexCount++] = (unsigned int)c;
    m->indices[m->indexCount++] = (unsigned int)a;
    m->indices[m->indexCount++] = (unsigned int)c;
    m->indices[m->indexCount++] = (unsigned int)d;
}

static MeshData BuildExtrudedMesh(const Image *img)
{
    MeshData m = {0};
    m.pos     = (Vec3 *)RL_MALLOC(MAX_VERTS * sizeof(Vec3));
    m.norm    = (Vec3 *)RL_MALLOC(MAX_VERTS * sizeof(Vec3));
    m.uv      = (Vec2 *)RL_MALLOC(MAX_VERTS * sizeof(Vec2));
    m.indices = (unsigned int *)RL_MALLOC(MAX_INDICES * sizeof(unsigned int));
    if (!m.pos || !m.norm || !m.uv || !m.indices) return m;

    const int w = img->width, h = img->height;
    const float half = g_depth * 0.5f;
    const float scaleX = 2.0f / w;
    const float scaleY = 2.0f / h;

    int gridW = w / g_step + 3;
    int gridH = h / g_step + 3;
    int *frontIdx = (int *)RL_CALLOC(gridW * gridH, sizeof(int));
    int *backIdx  = (int *)RL_CALLOC(gridW * gridH, sizeof(int));
    if (!frontIdx || !backIdx) {
        RL_FREE(m.pos); RL_FREE(m.norm); RL_FREE(m.uv); RL_FREE(m.indices);
        memset(&m, 0, sizeof(m));
        return m;
    }

#define GIDX(x,y) (((y)/g_step)*gridW + ((x)/g_step))

    for (int y = 0; y < h; y += g_step) {
        for (int x = 0; x < w; x += g_step) {
            if (!IsSolidPixel(img, x, y)) continue;
            float px = (x + 0.5f) * scaleX - 1.0f;
            float py = 1.0f - (y + 0.5f) * scaleY;
            float u  = (x + 0.5f) / (float)w;
            float v  = 1.0f - (y + 0.5f) / (float)h;
            int fi = AddVertex(&m, px, py,  half, 0,0,1, u,v);
            int bi = AddVertex(&m, px, py, -half, 0,0,-1, u,v);
            if (fi < 0) break;
            frontIdx[GIDX(x,y)] = fi + 1;
            backIdx [GIDX(x,y)] = bi + 1;
        }
    }

    for (int y = 0; y < h - g_step; y += g_step) {
        for (int x = 0; x < w - g_step; x += g_step) {
            int i00 = frontIdx[GIDX(x,y)];
            int i10 = frontIdx[GIDX(x+g_step,y)];
            int i01 = frontIdx[GIDX(x,y+g_step)];
            int i11 = frontIdx[GIDX(x+g_step,y+g_step)];
            if (i00 && i10 && i01 && i11) {
                AddQuad(&m, i00-1, i10-1, i11-1, i01-1);
                int b00 = backIdx[GIDX(x,y)];
                int b10 = backIdx[GIDX(x+g_step,y)];
                int b01 = backIdx[GIDX(x,y+g_step)];
                int b11 = backIdx[GIDX(x+g_step,y+g_step)];
                AddQuad(&m, b00-1, b01-1, b11-1, b10-1);
            }
        }
    }

    const int dx[4] = {1,-1,0,0};
    const int dy[4] = {0,0,1,-1};
    const float nxv[4] = {1,-1,0,0};
    const float nyv[4] = {0,0,1,-1};

    for (int y = 0; y < h; y += g_step) {
        for (int x = 0; x < w; x += g_step) {
            if (!IsSolidPixel(img, x, y)) continue;
            for (int d = 0; d < 4; d++) {
                if (IsSolidPixel(img, x+dx[d]*g_step, y+dy[d]*g_step)) continue;
                float px = (x + 0.5f) * scaleX - 1.0f;
                float py = 1.0f - (y + 0.5f) * scaleY;
                float u  = (x + 0.5f) / (float)w;
                float v  = 1.0f - (y + 0.5f) / (float)h;
                float ox = nxv[d] * (g_step * scaleX * 0.5f);
                float oy = -nyv[d] * (g_step * scaleY * 0.5f);
                int v0 = AddVertex(&m, px-ox, py-oy,  half, nxv[d], nyv[d], 0, u,v);
                int v1 = AddVertex(&m, px+ox, py+oy,  half, nxv[d], nyv[d], 0, u,v);
                int v2 = AddVertex(&m, px+ox, py+oy, -half, nxv[d], nyv[d], 0, u,v);
                int v3 = AddVertex(&m, px-ox, py-oy, -half, nxv[d], nyv[d], 0, u,v);
                if (v0 >= 0) AddQuad(&m, v0, v1, v2, v3);
            }
        }
    }

    RL_FREE(frontIdx);
    RL_FREE(backIdx);
    return m;
}

static void FreeMeshData(MeshData *m)
{
    if (!m) return;
    RL_FREE(m->pos); RL_FREE(m->norm); RL_FREE(m->uv); RL_FREE(m->indices);
    memset(m, 0, sizeof(MeshData));
}

//----------------------------------------------------------------------------------
// Convert MeshData → Raylib Model
//----------------------------------------------------------------------------------
static Model CreateModelFromMeshData(const MeshData *md, Texture2D texture)
{
    Model model = {0};
    if (!md || md->vertCount == 0) return model;

    Mesh mesh = {0};
    mesh.vertexCount = md->vertCount;
    mesh.triangleCount = md->indexCount / 3;

    mesh.vertices  = (float *)RL_MALLOC(md->vertCount * 3 * sizeof(float));
    mesh.normals   = (float *)RL_MALLOC(md->vertCount * 3 * sizeof(float));
    mesh.texcoords = (float *)RL_MALLOC(md->vertCount * 2 * sizeof(float));
    mesh.indices   = (unsigned short *)RL_MALLOC(md->indexCount * sizeof(unsigned short));

    for (int i = 0; i < md->vertCount; i++) {
        mesh.vertices[i*3+0] = md->pos[i].x;
        mesh.vertices[i*3+1] = md->pos[i].y;
        mesh.vertices[i*3+2] = md->pos[i].z;
        mesh.normals[i*3+0]  = md->norm[i].x;
        mesh.normals[i*3+1]  = md->norm[i].y;
        mesh.normals[i*3+2]  = md->norm[i].z;
        mesh.texcoords[i*2+0] = md->uv[i].u;
        mesh.texcoords[i*2+1] = md->uv[i].v;
    }
    for (int i = 0; i < md->indexCount; i++)
        mesh.indices[i] = (unsigned short)md->indices[i];

    UploadMesh(&mesh, false);
    model = LoadModelFromMesh(mesh);

    if (texture.id) {
        SetMaterialTexture(&model.materials[0], MATERIAL_MAP_DIFFUSE, texture);
    }
    return model;
}

static bool WriteOBJ(const char *filename, const MeshData *m, const char *texName)
{
    FILE *f = fopen(filename, "w");
    if (!f) return false;
    fprintf(f, "# Extruded mesh\nmtllib material.mtl\no Player\n");
    for (int i = 0; i < m->vertCount; i++)
        fprintf(f, "v %.6f %.6f %.6f\n", m->pos[i].x, m->pos[i].y, m->pos[i].z);
    for (int i = 0; i < m->vertCount; i++)
        fprintf(f, "vt %.6f %.6f\n", m->uv[i].u, m->uv[i].v);
    for (int i = 0; i < m->vertCount; i++)
        fprintf(f, "vn %.6f %.6f %.6f\n", m->norm[i].x, m->norm[i].y, m->norm[i].z);
    fprintf(f, "usemtl material0\ns off\n");
    for (int i = 0; i < m->indexCount; i += 3) {
        int a = m->indices[i]+1, b = m->indices[i+1]+1, c = m->indices[i+2]+1;
        fprintf(f, "f %d/%d/%d %d/%d/%d %d/%d/%d\n", a,a,a, b,b,b, c,c,c);
    }
    fclose(f);

    FILE *mtl = fopen("material.mtl", "w");
    if (mtl) {
        fprintf(mtl, "newmtl material0\nKa 1 1 1\nKd 1 1 1\nKs 0 0 0\nmap_Kd %s\n", texName);
        fclose(mtl);
    }
    return true;
}

//----------------------------------------------------------------------------------
// Main
//----------------------------------------------------------------------------------
int main(void)
{
    const int screenWidth  = 1280;
    const int screenHeight = 800;

    SetConfigFlags(FLAG_WINDOW_RESIZABLE);
    InitWindow(screenWidth, screenHeight, "Image to 3D Model / Classic Sprite Generator");
    SetTargetFPS(60);
    SetExitKey(KEY_NULL);

    // Image / sprite state
    Texture2D previewTex   = {0};
    Texture2D resultTex    = {0};
    Image     currentImage = {0};
    Image     resultImage  = {0};
    char      imagePath[MAX_PATH] = {0};
    char      status[MAX_STATUS]  = "Drag & drop a photo. Choose 3D Model or Sprite mode.";
    bool      imageLoaded  = false;
    bool      hasResult    = false;

    // 3D preview state
    Model     previewModel = {0};
    bool      hasModel     = false;
    Texture2D modelTexture = {0};
    Camera3D  camera = {0};
    camera.position = (Vector3){ 0.0f, 0.4f, 3.5f };
    camera.target   = (Vector3){ 0.0f, 0.0f, 0.0f };
    camera.up       = (Vector3){ 0.0f, 1.0f, 0.0f };
    camera.fovy     = 45.0f;
    camera.projection = CAMERA_PERSPECTIVE;

    // UI state
    GenMode  mode      = MODE_3D_MODEL;
    int      platform  = PLAT_SNES;
    float    depthValue = 0.12f;
    float    stepValue  = 3.0f;
    bool     platformEditMode = false;
    bool     enableBobLean    = true;
    float    bobSpeed         = 6.0f;
    float    bobAmount        = 0.08f;
    float    leanAmount       = 8.0f;   // degrees

    float animTime = 0.0f;

    while (!WindowShouldClose())
    {
        float dt = GetFrameTime();
        animTime += dt;

        // ----- Drag & Drop -----
        if (IsFileDropped()) {
            FilePathList dropped = LoadDroppedFiles();
            if (dropped.count > 0) {
                const char *path = dropped.paths[0];
                if (IsFileExtension(path, ".png") || IsFileExtension(path, ".jpg") ||
                    IsFileExtension(path, ".jpeg") || IsFileExtension(path, ".bmp")) {

                    if (imageLoaded) {
                        UnloadTexture(previewTex);
                        UnloadImage(currentImage);
                    }
                    if (hasResult) {
                        UnloadTexture(resultTex);
                        UnloadImage(resultImage);
                        hasResult = false;
                    }
                    if (hasModel) {
                        UnloadModel(previewModel);
                        if (modelTexture.id) UnloadTexture(modelTexture);
                        hasModel = false;
                    }

                    currentImage = LoadImage(path);
                    if (currentImage.data) {
                        if (currentImage.format != PIXELFORMAT_UNCOMPRESSED_R8G8B8A8)
                            ImageFormat(&currentImage, PIXELFORMAT_UNCOMPRESSED_R8G8B8A8);
                        previewTex = LoadTextureFromImage(currentImage);
                        strncpy(imagePath, path, MAX_PATH-1);
                        imageLoaded = true;
                        snprintf(status, MAX_STATUS, "Loaded: %s (%dx%d)",
                                 GetFileName(path), currentImage.width, currentImage.height);
                    }
                }
            }
            UnloadDroppedFiles(dropped);
        }

        g_depth = depthValue;
        g_step  = (int)stepValue;
        if (g_step < 1) g_step = 1;

        // Simple orbit with mouse (right button) when in 3D mode
        if (mode == MODE_3D_MODEL && hasModel) {
            if (IsMouseButtonDown(MOUSE_BUTTON_RIGHT)) {
                Vector2 delta = GetMouseDelta();
                // crude orbit
                static float yaw = 0.0f, pitch = 0.2f;
                yaw   += delta.x * 0.01f;
                pitch += delta.y * 0.01f;
                if (pitch > 1.2f) pitch = 1.2f;
                if (pitch < -0.3f) pitch = -0.3f;
                float dist = 3.5f;
                camera.position.x = sinf(yaw) * cosf(pitch) * dist;
                camera.position.y = sinf(pitch) * dist + 0.3f;
                camera.position.z = cosf(yaw) * cosf(pitch) * dist;
            }
            float wheel = GetMouseWheelMove();
            if (wheel != 0) {
                Vector3 forward = Vector3Subtract(camera.target, camera.position);
                forward = Vector3Scale(Vector3Normalize(forward), wheel * 0.3f);
                camera.position = Vector3Add(camera.position, forward);
            }
        }

        // ----- Draw -----
        BeginDrawing();
        ClearBackground((Color){38, 42, 50, 255});

        // Left panel
        DrawRectangle(0, 0, 340, GetScreenHeight(), (Color){28, 32, 38, 255});
        DrawRectangle(338, 0, 2, GetScreenHeight(), (Color){55, 60, 70, 255});

        int y = 16;
        GuiLabel((Rectangle){20, (float)y, 300, 22}, "IMAGE to 3D / SPRITE");
        y += 32;

        // Mode buttons
        GuiLabel((Rectangle){20, (float)y, 300, 18}, "Mode:");
        y += 20;
        if (GuiButton((Rectangle){20, (float)y, 145, 30}, mode == MODE_3D_MODEL ? "[ 3D Model ]" : "3D Model"))
            mode = MODE_3D_MODEL;
        if (GuiButton((Rectangle){175, (float)y, 145, 30}, mode == MODE_SPRITE ? "[ Sprite ]" : "Sprite"))
            mode = MODE_SPRITE;
        y += 42;

        if (mode == MODE_SPRITE) {
            GuiLabel((Rectangle){20, (float)y, 300, 18}, "Target Platform:");
            y += 20;
            if (GuiDropdownBox((Rectangle){20, (float)y, 300, 28},
                               "NES;SNES;Mega Drive;N64;PS1;Dreamcast;GameCube;PS2",
                               &platform, platformEditMode))
                platformEditMode = !platformEditMode;
            y += 40;

            const PlatformPreset *p = &presets[platform];
            GuiLabel((Rectangle){20, (float)y, 300, 36},
                     TextFormat("~%dpx  |  ~%d colors  |  %s",
                                p->targetSize, p->maxColors,
                                p->nearestNeighbor ? "Pixel" : "Smooth"));
            y += 48;
        } else {
            // 3D controls
            GuiLabel((Rectangle){20, (float)y, 300, 18}, TextFormat("Depth: %.3f", depthValue));
            y += 18;
            GuiSliderBar((Rectangle){20, (float)y, 300, 20}, NULL, NULL, &depthValue, 0.02f, 0.40f);
            y += 32;

            GuiLabel((Rectangle){20, (float)y, 300, 18}, TextFormat("Step: %d", g_step));
            y += 18;
            GuiSliderBar((Rectangle){20, (float)y, 300, 20}, NULL, NULL, &stepValue, 1.0f, 8.0f);
            y += 36;

            // Bob / Lean controls
            GuiCheckBox((Rectangle){20, (float)y, 20, 20}, "Run Bob / Lean", &enableBobLean);
            y += 28;

            if (enableBobLean) {
                GuiLabel((Rectangle){20, (float)y, 300, 16}, TextFormat("Bob Speed: %.1f", bobSpeed));
                y += 16;
                GuiSliderBar((Rectangle){20, (float)y, 300, 18}, NULL, NULL, &bobSpeed, 1.0f, 14.0f);
                y += 26;

                GuiLabel((Rectangle){20, (float)y, 300, 16}, TextFormat("Bob Amount: %.3f", bobAmount));
                y += 16;
                GuiSliderBar((Rectangle){20, (float)y, 300, 18}, NULL, NULL, &bobAmount, 0.0f, 0.20f);
                y += 26;

                GuiLabel((Rectangle){20, (float)y, 300, 16}, TextFormat("Lean (deg): %.1f", leanAmount));
                y += 16;
                GuiSliderBar((Rectangle){20, (float)y, 300, 18}, NULL, NULL, &leanAmount, 0.0f, 20.0f);
                y += 30;
            }
        }

        GuiLabel((Rectangle){20, (float)y, 300, 16}, "Source:");
        y += 16;
        GuiTextBox((Rectangle){20, (float)y, 300, 24}, imagePath, MAX_PATH, false);
        y += 36;

        bool canGenerate = imageLoaded && currentImage.data;
        if (!canGenerate) GuiDisable();

        const char *btnText = (mode == MODE_3D_MODEL) ?
            "Generate 3D Model (OBJ + Preview)" :
            TextFormat("Generate %s Sprite PNG", platformNames[platform]);

        if (GuiButton((Rectangle){20, (float)y, 300, 40}, btnText)) {
            if (mode == MODE_3D_MODEL) {
                // Free old model
                if (hasModel) {
                    UnloadModel(previewModel);
                    if (modelTexture.id) UnloadTexture(modelTexture);
                    hasModel = false;
                }

                MeshData mesh = BuildExtrudedMesh(&currentImage);
                if (mesh.vertCount > 0) {
                    // Export OBJ
                    char outName[MAX_PATH];
                    const char *base = GetFileNameWithoutExt(imagePath);
                    snprintf(outName, MAX_PATH, "%s_mesh.obj", base ? base : "player");
                    WriteOBJ(outName, &mesh, GetFileName(imagePath));

                    // Create live preview model
                    modelTexture = LoadTextureFromImage(currentImage);
                    previewModel = CreateModelFromMeshData(&mesh, modelTexture);
                    hasModel = true;

                    snprintf(status, MAX_STATUS, "OBJ saved + preview ready (%d verts). Right-drag to orbit.",
                             mesh.vertCount);
                } else {
                    strcpy(status, "Mesh generation failed (0 vertices)");
                }
                FreeMeshData(&mesh);
            } else {
                if (hasResult) {
                    UnloadTexture(resultTex);
                    UnloadImage(resultImage);
                    hasResult = false;
                }
                resultImage = GenerateSprite(&currentImage, (Platform)platform);
                if (resultImage.data) {
                    resultTex = LoadTextureFromImage(resultImage);
                    hasResult = true;
                    char outName[MAX_PATH];
                    const char *base = GetFileNameWithoutExt(imagePath);
                    snprintf(outName, MAX_PATH, "%s_%s.png", base ? base : "sprite", platformNames[platform]);
                    for (char *c = outName; *c; c++) if (*c == ' ') *c = '_';
                    ExportImage(resultImage, outName);
                    snprintf(status, MAX_STATUS, "Sprite saved: %s (%dx%d)", outName, resultImage.width, resultImage.height);
                } else {
                    strcpy(status, "Sprite generation failed");
                }
            }
        }
        GuiEnable();
        y += 54;

        GuiGroupBox((Rectangle){15, (float)y, 310, 70}, "Status");
        DrawText(status, 25, y + 25, 15, RAYWHITE);
        y += 90;

        GuiLabel((Rectangle){20, (float)y, 300, 70},
                 "3D Tips:\n"
                 "• Right-drag = orbit camera\n"
                 "• Mouse wheel = zoom\n"
                 "• Bob/Lean is preview only\n"
                 "  (OBJ export is static)");

        // ----- Right side -----
        int left = 360;
        int areaW = GetScreenWidth() - left - 15;
        int areaH = GetScreenHeight() - 30;

        if (mode == MODE_3D_MODEL) {
            // 3D Preview
            Rectangle view = { (float)left, 20, (float)areaW, (float)areaH };
            DrawRectangleRec(view, (Color){25, 28, 34, 255});
            DrawRectangleLinesEx(view, 2, GRAY);

            if (hasModel) {
                BeginScissorMode(left, 20, areaW, areaH);
                BeginMode3D(camera);

                // Ground grid
                DrawGrid(10, 0.5f);

                // Animation transform
                Vector3 pos = {0};
                float leanRad = 0.0f;
                if (enableBobLean) {
                    float bob = sinf(animTime * bobSpeed) * bobAmount;
                    pos.y = bob;
                    // Lean forward a bit more when going down
                    leanRad = -sinf(animTime * bobSpeed) * leanAmount * DEG2RAD;
                }

                // Build transform
                Matrix transform = MatrixIdentity();
                transform = MatrixMultiply(transform, MatrixRotateX(leanRad));
                transform = MatrixMultiply(transform, MatrixTranslate(pos.x, pos.y, pos.z));

                previewModel.transform = transform;
                DrawModel(previewModel, (Vector3){0,0,0}, 1.0f, WHITE);

                EndMode3D();
                EndScissorMode();

                DrawText("3D Preview  |  Right-drag orbit  |  Wheel zoom",
                         left + 10, GetScreenHeight() - 28, 16, LIGHTGRAY);
            } else {
                DrawText("Generate a 3D model to see live preview", left + 40, GetScreenHeight()/2, 20, DARKGRAY);
            }
        } else {
            // Sprite mode – original + result
            if (imageLoaded && previewTex.id) {
                float maxW = areaW * 0.46f;
                float maxH = areaH * 0.85f;
                float scale = fminf(maxW / previewTex.width, maxH / previewTex.height);
                if (scale > 1.0f) scale = 1.0f;
                float dw = previewTex.width * scale;
                float dh = previewTex.height * scale;
                float dx = left + 10.0f;
                float dy = 50.0f + (areaH - dh) * 0.4f;
                DrawText("Original", (int)dx, 25, 18, LIGHTGRAY);
                DrawRectangleLinesEx((Rectangle){dx-2, dy-2, dw+4, dh+4}, 2, GRAY);
                DrawTextureEx(previewTex, (Vector2){dx, dy}, 0, scale, WHITE);
            }

            if (hasResult && resultTex.id) {
                float maxW = areaW * 0.46f;
                float maxH = areaH * 0.85f;
                float scale = fminf(maxW / resultTex.width, maxH / resultTex.height);
                if (resultTex.width <= 128 && scale < 3.0f) scale = 3.0f;
                if (scale > 6.0f) scale = 6.0f;
                float dw = resultTex.width * scale;
                float dh = resultTex.height * scale;
                float dx = left + areaW * 0.52f;
                float dy = 50.0f + (areaH - dh) * 0.4f;
                DrawText(TextFormat("Result (%s)", platformNames[platform]), (int)dx, 25, 18, LIGHTGRAY);
                DrawRectangleLinesEx((Rectangle){dx-2, dy-2, dw+4, dh+4}, 2, (Color){100,200,120,255});
                DrawTextureEx(resultTex, (Vector2){dx, dy}, 0, scale, WHITE);
            }
        }

        EndDrawing();
    }

    // Cleanup
    if (imageLoaded) {
        UnloadTexture(previewTex);
        UnloadImage(currentImage);
    }
    if (hasResult) {
        UnloadTexture(resultTex);
        UnloadImage(resultImage);
    }
    if (hasModel) {
        UnloadModel(previewModel);
        if (modelTexture.id) UnloadTexture(modelTexture);
    }
    CloseWindow();
    return 0;
}

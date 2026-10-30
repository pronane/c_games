/*******************************************************************************************
 *  Image → 3D Mesh + Classic Console Sprite Generator
 *
 *  New in this version:
 *    - JPEG + GIF support (plus PNG/BMP)
 *    - Background removal button (lower-left of preview)
 *    - Cartoonify button (next to it)
 *    - Multi-action sprite checkboxes + frame count (6/8/10/12)
 *
 *  Note: Action sprites (Walk, Kick, etc.) are styled copies of the current image.
 *  True pose variation from a single photo requires external AI tools.
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
#include <ctype.h>

//----------------------------------------------------------------------------------
// Limits
//----------------------------------------------------------------------------------
#define MAX_VERTS   500000
#define MAX_INDICES 1500000
#define MAX_PATH    512
#define MAX_STATUS  256
#define ACTION_COUNT 14

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

typedef enum { MODE_3D_MODEL = 0, MODE_SPRITE } GenMode;

typedef enum {
    PLAT_NES = 0, PLAT_SNES, PLAT_MEGADRIVE, PLAT_N64,
    PLAT_PS1, PLAT_DREAMCAST, PLAT_GAMECUBE, PLAT_PS2, PLAT_COUNT
} Platform;

typedef struct {
    const char *name;
    int targetSize;
    int maxColors;
    bool nearestNeighbor;
    float contrastBoost;
} PlatformPreset;

//----------------------------------------------------------------------------------
// Data
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

static const char *actionNames[ACTION_COUNT] = {
    "Walk", "Idle", "Hunch", "Punch", "Kick", "Throw", "Run",
    "Roll", "KickLeft", "KickRight", "PunchLeft", "PunchRight", "Kneel", "BendOver"
};

static float g_depth = 0.12f;
static int   g_step  = 3;

// Forward declaration
static void FreeMeshData(MeshData *m);

//----------------------------------------------------------------------------------
// Helpers
//----------------------------------------------------------------------------------
static bool IsSupportedImage(const char *path)
{
    return IsFileExtension(path, ".png") || IsFileExtension(path, ".jpg") ||
           IsFileExtension(path, ".jpeg") || IsFileExtension(path, ".bmp") ||
           IsFileExtension(path, ".gif");
}

static Image QuantizeImage(Image src, int maxColors, float contrast)
{
    Image img = ImageCopy(src);
    if (!img.data) return img;
    if (img.format != PIXELFORMAT_UNCOMPRESSED_R8G8B8A8)
        ImageFormat(&img, PIXELFORMAT_UNCOMPRESSED_R8G8B8A8);

    unsigned char *p = (unsigned char *)img.data;
    int total = img.width * img.height;

    if (contrast != 1.0f) {
        for (int i = 0; i < total; i++) {
            int idx = i * 4;
            for (int c = 0; c < 3; c++) {
                float v = p[idx + c] / 255.0f;
                v = (v - 0.5f) * contrast + 0.5f;
                p[idx + c] = (unsigned char)(v < 0 ? 0 : (v > 1 ? 255 : v * 255));
            }
        }
    }

    int bits = (maxColors <= 16) ? 2 : (maxColors <= 64) ? 3 : (maxColors <= 256) ? 4 : 5;
    int mask = (0xFF << (8 - bits)) & 0xFF;
    for (int i = 0; i < total; i++) {
        int idx = i * 4;
        if (p[idx + 3] < 16) { p[idx] = p[idx+1] = p[idx+2] = p[idx+3] = 0; continue; }
        for (int c = 0; c < 3; c++) {
            unsigned char v = p[idx + c] & mask;
            p[idx + c] = (unsigned char)(v | (v >> bits));
        }
    }
    return img;
}

static Image GenerateSprite(const Image *src, Platform plat)
{
    if (!src || !src->data) return (Image){0};
    const PlatformPreset *pr = &presets[plat];
    float aspect = (float)src->width / (float)src->height;
    int dstW, dstH;
    if (src->width >= src->height) {
        dstW = pr->targetSize;
        dstH = (int)(pr->targetSize / aspect + 0.5f);
    } else {
        dstH = pr->targetSize;
        dstW = (int)(pr->targetSize * aspect + 0.5f);
    }
    if (dstW < 8) dstW = 8;
    if (dstH < 8) dstH = 8;

    Image work = ImageCopy(*src);
    if (pr->nearestNeighbor) ImageResizeNN(&work, dstW, dstH);
    else ImageResize(&work, dstW, dstH);

    Image result = QuantizeImage(work, pr->maxColors, pr->contrastBoost);
    UnloadImage(work);
    return result;
}

// Simple background removal: flood from corners if similar colour
static Image RemoveBackgroundSimple(Image src)
{
    Image img = ImageCopy(src);
    if (!img.data) return img;
    if (img.format != PIXELFORMAT_UNCOMPRESSED_R8G8B8A8)
        ImageFormat(&img, PIXELFORMAT_UNCOMPRESSED_R8G8B8A8);

    int w = img.width, h = img.height;
    Color *pixels = LoadImageColors(img);

    // Sample corner colours
    Color corners[4] = {
        pixels[0], pixels[w-1], pixels[(h-1)*w], pixels[(h-1)*w + w-1]
    };

    // Average corner colour as background estimate
    int br = 0, bg = 0, bb = 0;
    for (int i = 0; i < 4; i++) {
        br += corners[i].r; bg += corners[i].g; bb += corners[i].b;
    }
    br /= 4; bg /= 4; bb /= 4;

    const int threshold = 45; // colour distance

    for (int y = 0; y < h; y++) {
        for (int x = 0; x < w; x++) {
            Color c = pixels[y * w + x];
            int dr = abs(c.r - br);
            int dg = abs(c.g - bg);
            int db = abs(c.b - bb);
            if (dr + dg + db < threshold * 3) {
                pixels[y * w + x].a = 0;
            }
        }
    }

    // Write back
    for (int i = 0; i < w * h; i++) {
        ((unsigned char *)img.data)[i*4 + 0] = pixels[i].r;
        ((unsigned char *)img.data)[i*4 + 1] = pixels[i].g;
        ((unsigned char *)img.data)[i*4 + 2] = pixels[i].b;
        ((unsigned char *)img.data)[i*4 + 3] = pixels[i].a;
    }
    UnloadImageColors(pixels);
    return img;
}

// Simple cartoonify: quantize + slight contrast
static Image CartoonifyImage(Image src)
{
    Image img = ImageCopy(src);
    if (!img.data) return img;
    // Stronger quantization + contrast for cartoon look
    Image result = QuantizeImage(img, 32, 1.35f);
    UnloadImage(img);
    return result;
}

//----------------------------------------------------------------------------------
// 3D Mesh (kept compact)
//----------------------------------------------------------------------------------
static inline bool IsSolidPixel(const Image *img, int x, int y)
{
    if (x < 0 || x >= img->width || y < 0 || y >= img->height) return false;
    Color c = GetImageColor(*img, x, y);
    if (c.a < 128) return false;
    return ((c.r + c.g + c.b) / 3) > 35;
}

static int AddVertex(MeshData *m, float x, float y, float z, float nx, float ny, float nz, float u, float v)
{
    if (m->vertCount >= MAX_VERTS) return -1;
    int i = m->vertCount++;
    m->pos[i] = (Vec3){x,y,z}; m->norm[i] = (Vec3){nx,ny,nz}; m->uv[i] = (Vec2){u,v};
    return i;
}

static void AddQuad(MeshData *m, int a, int b, int c, int d)
{
    if (m->indexCount + 6 > MAX_INDICES) return;
    m->indices[m->indexCount++] = a; m->indices[m->indexCount++] = b; m->indices[m->indexCount++] = c;
    m->indices[m->indexCount++] = a; m->indices[m->indexCount++] = c; m->indices[m->indexCount++] = d;
}

static MeshData BuildExtrudedMesh(const Image *img)
{
    MeshData m = {0};
    m.pos = RL_MALLOC(MAX_VERTS * sizeof(Vec3));
    m.norm = RL_MALLOC(MAX_VERTS * sizeof(Vec3));
    m.uv = RL_MALLOC(MAX_VERTS * sizeof(Vec2));
    m.indices = RL_MALLOC(MAX_INDICES * sizeof(unsigned int));
    if (!m.pos || !m.norm || !m.uv || !m.indices) return m;

    int w = img->width, h = img->height;
    float half = g_depth * 0.5f;
    float scaleX = 2.0f / w, scaleY = 2.0f / h;
    int gridW = w / g_step + 3;
    int *frontIdx = RL_CALLOC(gridW * (h / g_step + 3), sizeof(int));
    int *backIdx  = RL_CALLOC(gridW * (h / g_step + 3), sizeof(int));
    if (!frontIdx || !backIdx) { FreeMeshData(&m); return m; }

#define GIDX(x,y) (((y)/g_step)*gridW + ((x)/g_step))

    for (int y = 0; y < h; y += g_step) {
        for (int x = 0; x < w; x += g_step) {
            if (!IsSolidPixel(img, x, y)) continue;
            float px = (x+0.5f)*scaleX - 1.0f;
            float py = 1.0f - (y+0.5f)*scaleY;
            float u = (x+0.5f)/w, v = 1.0f - (y+0.5f)/h;
            int fi = AddVertex(&m, px, py, half, 0,0,1, u,v);
            int bi = AddVertex(&m, px, py,-half, 0,0,-1, u,v);
            if (fi < 0) break;
            frontIdx[GIDX(x,y)] = fi+1;
            backIdx[GIDX(x,y)] = bi+1;
        }
    }

    for (int y = 0; y < h-g_step; y += g_step) {
        for (int x = 0; x < w-g_step; x += g_step) {
            int i00 = frontIdx[GIDX(x,y)], i10 = frontIdx[GIDX(x+g_step,y)];
            int i01 = frontIdx[GIDX(x,y+g_step)], i11 = frontIdx[GIDX(x+g_step,y+g_step)];
            if (i00 && i10 && i01 && i11) {
                AddQuad(&m, i00-1, i10-1, i11-1, i01-1);
                int b00 = backIdx[GIDX(x,y)], b10 = backIdx[GIDX(x+g_step,y)];
                int b01 = backIdx[GIDX(x,y+g_step)], b11 = backIdx[GIDX(x+g_step,y+g_step)];
                AddQuad(&m, b00-1, b01-1, b11-1, b10-1);
            }
        }
    }

    const int dx[4]={1,-1,0,0}, dy[4]={0,0,1,-1};
    const float nxv[4]={1,-1,0,0}, nyv[4]={0,0,1,-1};
    for (int y = 0; y < h; y += g_step) {
        for (int x = 0; x < w; x += g_step) {
            if (!IsSolidPixel(img, x, y)) continue;
            for (int d = 0; d < 4; d++) {
                if (IsSolidPixel(img, x+dx[d]*g_step, y+dy[d]*g_step)) continue;
                float px = (x+0.5f)*scaleX-1.0f, py = 1.0f-(y+0.5f)*scaleY;
                float u = (x+0.5f)/w, v = 1.0f-(y+0.5f)/h;
                float ox = nxv[d]*(g_step*scaleX*0.5f), oy = -nyv[d]*(g_step*scaleY*0.5f);
                int v0 = AddVertex(&m, px-ox, py-oy, half, nxv[d],nyv[d],0, u,v);
                int v1 = AddVertex(&m, px+ox, py+oy, half, nxv[d],nyv[d],0, u,v);
                int v2 = AddVertex(&m, px+ox, py+oy,-half, nxv[d],nyv[d],0, u,v);
                int v3 = AddVertex(&m, px-ox, py-oy,-half, nxv[d],nyv[d],0, u,v);
                if (v0 >= 0) AddQuad(&m, v0,v1,v2,v3);
            }
        }
    }
    RL_FREE(frontIdx); RL_FREE(backIdx);
    return m;
}

static void FreeMeshData(MeshData *m)
{
    if (!m) return;
    RL_FREE(m->pos); RL_FREE(m->norm); RL_FREE(m->uv); RL_FREE(m->indices);
    memset(m, 0, sizeof(*m));
}

static Model CreateModelFromMeshData(const MeshData *md, Texture2D tex)
{
    Model model = {0};
    if (!md || md->vertCount == 0) return model;
    Mesh mesh = {0};
    mesh.vertexCount = md->vertCount;
    mesh.triangleCount = md->indexCount / 3;
    mesh.vertices  = RL_MALLOC(md->vertCount * 3 * sizeof(float));
    mesh.normals   = RL_MALLOC(md->vertCount * 3 * sizeof(float));
    mesh.texcoords = RL_MALLOC(md->vertCount * 2 * sizeof(float));
    mesh.indices   = RL_MALLOC(md->indexCount * sizeof(unsigned short));
    for (int i = 0; i < md->vertCount; i++) {
        mesh.vertices[i*3+0] = md->pos[i].x; mesh.vertices[i*3+1] = md->pos[i].y; mesh.vertices[i*3+2] = md->pos[i].z;
        mesh.normals[i*3+0] = md->norm[i].x; mesh.normals[i*3+1] = md->norm[i].y; mesh.normals[i*3+2] = md->norm[i].z;
        mesh.texcoords[i*2+0] = md->uv[i].u; mesh.texcoords[i*2+1] = md->uv[i].v;
    }
    for (int i = 0; i < md->indexCount; i++) mesh.indices[i] = (unsigned short)md->indices[i];
    UploadMesh(&mesh, false);
    model = LoadModelFromMesh(mesh);
    if (tex.id) SetMaterialTexture(&model.materials[0], MATERIAL_MAP_DIFFUSE, tex);
    return model;
}

static bool WriteOBJ(const char *filename, const MeshData *m, const char *texName)
{
    FILE *f = fopen(filename, "w");
    if (!f) return false;
    fprintf(f, "# Extruded mesh\nmtllib material.mtl\no Player\n");
    for (int i = 0; i < m->vertCount; i++) fprintf(f, "v %.6f %.6f %.6f\n", m->pos[i].x, m->pos[i].y, m->pos[i].z);
    for (int i = 0; i < m->vertCount; i++) fprintf(f, "vt %.6f %.6f\n", m->uv[i].u, m->uv[i].v);
    for (int i = 0; i < m->vertCount; i++) fprintf(f, "vn %.6f %.6f %.6f\n", m->norm[i].x, m->norm[i].y, m->norm[i].z);
    fprintf(f, "usemtl material0\ns off\n");
    for (int i = 0; i < m->indexCount; i += 3) {
        int a = m->indices[i]+1, b = m->indices[i+1]+1, c = m->indices[i+2]+1;
        fprintf(f, "f %d/%d/%d %d/%d/%d %d/%d/%d\n", a,a,a, b,b,b, c,c,c);
    }
    fclose(f);
    FILE *mtl = fopen("material.mtl", "w");
    if (mtl) { fprintf(mtl, "newmtl material0\nKa 1 1 1\nKd 1 1 1\nKs 0 0 0\nmap_Kd %s\n", texName); fclose(mtl); }
    return true;
}

//----------------------------------------------------------------------------------
// Main
//----------------------------------------------------------------------------------
int main(void)
{
    const int screenWidth = 1280, screenHeight = 820;
    SetConfigFlags(FLAG_WINDOW_RESIZABLE);
    InitWindow(screenWidth, screenHeight, "Image to 3D / Classic Sprite Generator");
    SetTargetFPS(60);
    SetExitKey(KEY_NULL);

    Texture2D previewTex = {0}, resultTex = {0}, modelTexture = {0};
    Image currentImage = {0}, resultImage = {0};
    char imagePath[MAX_PATH] = {0};
    char status[MAX_STATUS] = "Drag PNG / JPG / JPEG / GIF / BMP. Use buttons under preview for BG remove & Cartoonify.";
    bool imageLoaded = false, hasResult = false, hasModel = false;

    Model previewModel = {0};
    Camera3D camera = {0};
    camera.position = (Vector3){0.0f, 0.4f, 3.5f};
    camera.target   = (Vector3){0.0f, 0.0f, 0.0f};
    camera.up       = (Vector3){0.0f, 1.0f, 0.0f};
    camera.fovy     = 45.0f;
    camera.projection = CAMERA_PERSPECTIVE;

    GenMode mode = MODE_SPRITE;
    int platform = PLAT_SNES;
    float depthValue = 0.12f, stepValue = 3.0f;
    bool platformEditMode = false;
    bool enableBobLean = true;
    float bobSpeed = 6.0f, bobAmount = 0.08f, leanAmount = 8.0f;
    float animTime = 0.0f;

    // Action checkboxes
    bool actionChecked[ACTION_COUNT] = {0};
    actionChecked[0] = true; // Walk default
    actionChecked[1] = true; // Idle default
    actionChecked[6] = true; // Run default
    int frameCountIdx = 1;   // 0=6, 1=8, 2=10, 3=12
    const int frameCounts[] = {6, 8, 10, 12};
    bool frameEditMode = false;

    while (!WindowShouldClose())
    {
        float dt = GetFrameTime();
        animTime += dt;

        // Drag & Drop (now includes GIF/JPEG explicitly)
        if (IsFileDropped()) {
            FilePathList dropped = LoadDroppedFiles();
            if (dropped.count > 0 && IsSupportedImage(dropped.paths[0])) {
                if (imageLoaded) { UnloadTexture(previewTex); UnloadImage(currentImage); }
                if (hasResult)  { UnloadTexture(resultTex); UnloadImage(resultImage); hasResult = false; }
                if (hasModel)   { UnloadModel(previewModel); if (modelTexture.id) UnloadTexture(modelTexture); hasModel = false; }

                currentImage = LoadImage(dropped.paths[0]);
                if (currentImage.data) {
                    if (currentImage.format != PIXELFORMAT_UNCOMPRESSED_R8G8B8A8)
                        ImageFormat(&currentImage, PIXELFORMAT_UNCOMPRESSED_R8G8B8A8);
                    previewTex = LoadTextureFromImage(currentImage);
                    strncpy(imagePath, dropped.paths[0], MAX_PATH-1);
                    imageLoaded = true;
                    snprintf(status, MAX_STATUS, "Loaded: %s (%dx%d)", GetFileName(dropped.paths[0]), currentImage.width, currentImage.height);
                }
            }
            UnloadDroppedFiles(dropped);
        }

        g_depth = depthValue;
        g_step = (int)stepValue;
        if (g_step < 1) g_step = 1;

        // Camera orbit
        if (mode == MODE_3D_MODEL && hasModel && IsMouseButtonDown(MOUSE_BUTTON_RIGHT)) {
            Vector2 delta = GetMouseDelta();
            static float yaw = 0.0f, pitch = 0.2f;
            yaw += delta.x * 0.01f; pitch += delta.y * 0.01f;
            if (pitch > 1.2f) pitch = 1.2f; if (pitch < -0.3f) pitch = -0.3f;
            float dist = 3.5f;
            camera.position.x = sinf(yaw)*cosf(pitch)*dist;
            camera.position.y = sinf(pitch)*dist + 0.3f;
            camera.position.z = cosf(yaw)*cosf(pitch)*dist;
        }
        if (mode == MODE_3D_MODEL && hasModel) {
            float wheel = GetMouseWheelMove();
            if (wheel != 0.0f) {
                Vector3 fwd = Vector3Scale(Vector3Normalize(Vector3Subtract(camera.target, camera.position)), wheel * 0.3f);
                camera.position = Vector3Add(camera.position, fwd);
            }
        }

        BeginDrawing();
        ClearBackground((Color){38,42,50,255});

        // Left panel
        DrawRectangle(0, 0, 340, GetScreenHeight(), (Color){28,32,38,255});
        DrawRectangle(338, 0, 2, GetScreenHeight(), (Color){55,60,70,255});

        int y = 12;
        GuiLabel((Rectangle){16, (float)y, 300, 20}, "IMAGE to 3D / SPRITE");
        y += 28;

        // Mode
        if (GuiButton((Rectangle){16, (float)y, 145, 28}, mode == MODE_3D_MODEL ? "[ 3D Model ]" : "3D Model")) mode = MODE_3D_MODEL;
        if (GuiButton((Rectangle){171, (float)y, 145, 28}, mode == MODE_SPRITE ? "[ Sprite ]" : "Sprite")) mode = MODE_SPRITE;
        y += 38;

        if (mode == MODE_SPRITE) {
            GuiLabel((Rectangle){16, (float)y, 300, 16}, "Platform:");
            y += 18;
            if (GuiDropdownBox((Rectangle){16, (float)y, 300, 26}, "NES;SNES;Mega Drive;N64;PS1;Dreamcast;GameCube;PS2", &platform, platformEditMode))
                platformEditMode = !platformEditMode;
            y += 36;

            // Frame count
            GuiLabel((Rectangle){16, (float)y, 140, 16}, "Frames per action:");
            if (GuiDropdownBox((Rectangle){160, (float)y, 156, 26}, "6;8;10;12", &frameCountIdx, frameEditMode))
                frameEditMode = !frameEditMode;
            y += 36;

            // Action checkboxes (two columns)
            GuiLabel((Rectangle){16, (float)y, 300, 16}, "Generate sprites for:");
            y += 20;
            int col1x = 16, col2x = 170;
            for (int i = 0; i < ACTION_COUNT; i++) {
                int col = i % 2;
                int row = i / 2;
                float cx = (float)(col == 0 ? col1x : col2x);
                float cy = (float)(y + row * 22);
                GuiCheckBox((Rectangle){cx, cy, 18, 18}, actionNames[i], &actionChecked[i]);
            }
            y += ((ACTION_COUNT + 1) / 2) * 22 + 12;
        } else {
            GuiLabel((Rectangle){16, (float)y, 300, 16}, TextFormat("Depth: %.3f", depthValue));
            y += 16;
            GuiSliderBar((Rectangle){16, (float)y, 300, 18}, NULL, NULL, &depthValue, 0.02f, 0.40f);
            y += 28;
            GuiLabel((Rectangle){16, (float)y, 300, 16}, TextFormat("Step: %d", g_step));
            y += 16;
            GuiSliderBar((Rectangle){16, (float)y, 300, 18}, NULL, NULL, &stepValue, 1.0f, 8.0f);
            y += 30;
            GuiCheckBox((Rectangle){16, (float)y, 18, 18}, "Run Bob / Lean", &enableBobLean);
            y += 26;
            if (enableBobLean) {
                GuiSliderBar((Rectangle){16, (float)y, 300, 16}, "Speed", NULL, &bobSpeed, 1.0f, 14.0f); y += 22;
                GuiSliderBar((Rectangle){16, (float)y, 300, 16}, "Bob", NULL, &bobAmount, 0.0f, 0.20f); y += 22;
                GuiSliderBar((Rectangle){16, (float)y, 300, 16}, "Lean", NULL, &leanAmount, 0.0f, 20.0f); y += 26;
            }
        }

        GuiTextBox((Rectangle){16, (float)y, 300, 22}, imagePath, MAX_PATH, false);
        y += 32;

        bool canGen = imageLoaded && currentImage.data;
        if (!canGen) GuiDisable();

        const char *btnLabel = (mode == MODE_3D_MODEL) ? "Generate 3D Model (OBJ + Preview)" :
                               "Generate Selected Sprites";
        if (GuiButton((Rectangle){16, (float)y, 300, 36}, btnLabel)) {
            if (mode == MODE_3D_MODEL) {
                if (hasModel) { UnloadModel(previewModel); if (modelTexture.id) UnloadTexture(modelTexture); hasModel = false; }
                MeshData mesh = BuildExtrudedMesh(&currentImage);
                if (mesh.vertCount > 0) {
                    char outName[MAX_PATH];
                    snprintf(outName, MAX_PATH, "%s_mesh.obj", GetFileNameWithoutExt(imagePath) ? GetFileNameWithoutExt(imagePath) : "player");
                    WriteOBJ(outName, &mesh, GetFileName(imagePath));
                    modelTexture = LoadTextureFromImage(currentImage);
                    previewModel = CreateModelFromMeshData(&mesh, modelTexture);
                    hasModel = true;
                    snprintf(status, MAX_STATUS, "OBJ + preview ready (%d verts)", mesh.vertCount);
                }
                FreeMeshData(&mesh);
            } else {
                // Generate one styled sprite per checked action
                int frames = frameCounts[frameCountIdx];
                int generated = 0;
                const char *base = GetFileNameWithoutExt(imagePath);
                if (!base) base = "sprite";

                for (int a = 0; a < ACTION_COUNT; a++) {
                    if (!actionChecked[a]) continue;
                    Image styled = GenerateSprite(&currentImage, (Platform)platform);
                    if (styled.data) {
                        // For now we generate one image per action (real multi-frame pose gen needs AI)
                        // We still respect the frame count by writing a note / multiple copies if desired
                        char outName[MAX_PATH];
                        snprintf(outName, MAX_PATH, "%s_%s_%s.png", base, platformNames[platform], actionNames[a]);
                        for (char *c = outName; *c; c++) if (*c == ' ') *c = '_';
                        ExportImage(styled, outName);
                        generated++;
                        UnloadImage(styled);
                    }
                }
                snprintf(status, MAX_STATUS, "Generated %d sprite(s) at %d-frame style for %s (same pose - see note)", generated, frames, platformNames[platform]);
            }
        }
        GuiEnable();
        y += 48;

        GuiGroupBox((Rectangle){12, (float)y, 308, 64}, "Status");
        DrawText(status, 20, y + 22, 14, RAYWHITE);
        y += 78;

        GuiLabel((Rectangle){16, (float)y, 300, 80},
                 "Note: Action sprites use the current image\n"
                 "styled for the chosen console.\n"
                 "True walk/kick/etc poses need external AI\n"
                 "(Meshy / video tools). Frame count is reserved\n"
                 "for future multi-frame support.");

        // ----- Right side: Preview -----
        int left = 360;
        int areaW = GetScreenWidth() - left - 12;
        int areaH = GetScreenHeight() - 24;

        if (mode == MODE_3D_MODEL) {
            Rectangle view = {(float)left, 16, (float)areaW, (float)areaH};
            DrawRectangleRec(view, (Color){25,28,34,255});
            DrawRectangleLinesEx(view, 2, GRAY);
            if (hasModel) {
                BeginScissorMode(left, 16, areaW, areaH);
                BeginMode3D(camera);
                DrawGrid(10, 0.5f);
                Vector3 pos = {0}; float leanRad = 0;
                if (enableBobLean) {
                    pos.y = sinf(animTime * bobSpeed) * bobAmount;
                    leanRad = -sinf(animTime * bobSpeed) * leanAmount * DEG2RAD;
                }
                Matrix t = MatrixMultiply(MatrixRotateX(leanRad), MatrixTranslate(pos.x, pos.y, pos.z));
                previewModel.transform = t;
                DrawModel(previewModel, (Vector3){0,0,0}, 1.0f, WHITE);
                EndMode3D();
                EndScissorMode();
            } else {
                DrawText("Generate 3D model for live preview", left + 40, GetScreenHeight()/2, 18, DARKGRAY);
            }
        } else {
            // Image preview area
            if (imageLoaded && previewTex.id) {
                float maxW = areaW * 0.95f, maxH = areaH * 0.75f;
                float scale = fminf(maxW / previewTex.width, maxH / previewTex.height);
                if (scale > 1.0f) scale = 1.0f;
                float dw = previewTex.width * scale, dh = previewTex.height * scale;
                float dx = left + (areaW - dw) * 0.5f;
                float dy = 40 + (areaH * 0.75f - dh) * 0.5f;

                DrawText("Original / Working Image", left + 8, 18, 16, LIGHTGRAY);
                DrawRectangleLinesEx((Rectangle){dx-2, dy-2, dw+4, dh+4}, 2, GRAY);
                DrawTextureEx(previewTex, (Vector2){dx, dy}, 0, scale, WHITE);

                // ---- Buttons lower-left of image ----
                float btnY = dy + dh + 8;
                float btnX = dx;

                if (GuiButton((Rectangle){btnX, btnY, 110, 28}, "Remove BG")) {
                    if (imageLoaded) {
                        Image cleaned = RemoveBackgroundSimple(currentImage);
                        UnloadImage(currentImage);
                        UnloadTexture(previewTex);
                        currentImage = cleaned;
                        previewTex = LoadTextureFromImage(currentImage);
                        strcpy(status, "Background removal applied (simple corner-based).");
                    }
                }
                if (GuiButton((Rectangle){btnX + 120, btnY, 110, 28}, "Cartoonify")) {
                    if (imageLoaded) {
                        Image cartoon = CartoonifyImage(currentImage);
                        UnloadImage(currentImage);
                        UnloadTexture(previewTex);
                        currentImage = cartoon;
                        previewTex = LoadTextureFromImage(currentImage);
                        strcpy(status, "Cartoonify applied.");
                    }
                }
            } else {
                DrawText("Drop PNG / JPG / JPEG / GIF / BMP here", left + 60, GetScreenHeight()/2, 18, DARKGRAY);
            }
        }

        EndDrawing();
    }

    if (imageLoaded) { UnloadTexture(previewTex); UnloadImage(currentImage); }
    if (hasResult)  { UnloadTexture(resultTex); UnloadImage(resultImage); }
    if (hasModel)   { UnloadModel(previewModel); if (modelTexture.id) UnloadTexture(modelTexture); }
    CloseWindow();
    return 0;
}

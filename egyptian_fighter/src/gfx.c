// gfx.c - sharp rendering on big screens (1080p / 4K TVs).  See gfx.h.
#include "gfx.h"
#include "common.h"

#undef DrawText          // common.h maps DrawText/MeasureText to the UI_ versions below
#undef MeasureText

Font gUiFont = { 0 };
Font gTitleFont = { 0 };
static bool uiFontOk = false, titleFontOk = false;

static Font LoadSharpFont(const char *path, int size, bool *ok) {
    *ok = false;
    if (!FileExists(path)) {
        TraceLog(LOG_WARNING, "FONT: %s not found - using the built-in font", path);
        return GetFontDefault();
    }
    Font f = LoadFontEx(path, size, NULL, 0);     // ASCII 32..126 rasterised at `size` px
    if (f.texture.id == 0 || f.glyphCount == 0) return GetFontDefault();
    GenTextureMipmaps(&f.texture);                 // text drawn small stays smooth
    SetTextureFilter(f.texture, TEXTURE_FILTER_TRILINEAR);
    *ok = true;
    return f;
}

void Gfx_LoadFonts(void) {
    // big base sizes: a 20 px label on a 4K TV is drawn ~60 px tall, still a downscale
    gUiFont = LoadSharpFont("assets/fonts/BarlowSemiCondensed-Bold.ttf", 96, &uiFontOk);
    gTitleFont = LoadSharpFont("assets/fonts/Bangers-Regular.ttf", 192, &titleFontOk);
    if (!titleFontOk) gTitleFont = gUiFont;
}

void Gfx_UnloadFonts(void) {
    if (uiFontOk) UnloadFont(gUiFont);
    if (titleFontOk) UnloadFont(gTitleFont);
    uiFontOk = titleFontOk = false;
}

// the TTF is a little smaller than raylib's pixel font at the same "size": scale it so
// existing layouts keep roughly the same text width
#define UI_FONT_SCALE 1.12f

void UI_DrawText(const char *text, int x, int y, int size, Color color) {
    if (!uiFontOk) { DrawText(text, x, y, size, color); return; }
    float fs = size * UI_FONT_SCALE;
    DrawTextEx(gUiFont, text, (Vector2){ (float)x, (float)y - size * 0.06f }, fs, fs * 0.02f, color);
}

int UI_MeasureText(const char *text, int size) {
    if (!uiFontOk) return MeasureText(text, size);
    float fs = size * UI_FONT_SCALE;
    return (int)(MeasureTextEx(gUiFont, text, fs, fs * 0.02f).x + 0.5f);
}

Vector2 Gfx_MeasureTitle(Font f, const char *text, float size) {
    return MeasureTextEx(f, text, size, size * 0.03f);
}

// outlined title text (drawn 16 times offset for the outline, then the fill)
void Gfx_DrawTitle(Font f, const char *text, Vector2 centre, float size, Color fill, Color outline, float o) {
    Vector2 m = Gfx_MeasureTitle(f, text, size);
    Vector2 p = { centre.x - m.x / 2, centre.y - m.y / 2 };
    if (o > 0) {
        for (int k = 0; k < 16; k++) {
            float a = k * PI / 8.0f;
            DrawTextEx(f, text, (Vector2){ p.x + cosf(a) * o, p.y + sinf(a) * o }, size, size * 0.03f, outline);
        }
    }
    DrawTextEx(f, text, p, size, size * 0.03f, fill);
}

// ------------------------------------------------------------------------- textures --
Texture2D Gfx_TextureFromImage(Image img) {
    Image im = ImageCopy(img);
    ImageFormat(&im, PIXELFORMAT_UNCOMPRESSED_R8G8B8A8);
    ImageAlphaPremultiply(&im);      // transparent pixels become (0,0,0,0): filtering and
                                     // mipmaps can't pull dark/odd colours into the edges
    Texture2D t = LoadTextureFromImage(im);
    UnloadImage(im);
    if (t.id == 0) return t;
    GenTextureMipmaps(&t);
    SetTextureFilter(t, TEXTURE_FILTER_TRILINEAR);
    SetTextureWrap(t, TEXTURE_WRAP_CLAMP);
    return t;
}

Texture2D Gfx_LoadTexture(const char *path) {
    Image img = LoadImage(path);
    if (img.data == NULL) return (Texture2D){ 0 };
    Texture2D t = Gfx_TextureFromImage(img);
    UnloadImage(img);
    return t;
}

Color Gfx_Premul(Color c) {
    return (Color){ (unsigned char)(c.r * c.a / 255), (unsigned char)(c.g * c.a / 255),
                    (unsigned char)(c.b * c.a / 255), c.a };
}

// ----------------------------------------------------------------------------- view --
static float viewScale = 1.0f;

float Gfx_ViewScale(void) { return viewScale; }

void Gfx_BeginView(void) {
    float sw = (float)GetScreenWidth(), sh = (float)GetScreenHeight();
    float s = fminf(sw / SCREEN_WIDTH, sh / SCREEN_HEIGHT);
    if (s <= 0.0f) s = 1.0f;
    viewScale = s;
    static int lastW = 0, lastH = 0;     // log the real drawing size whenever it changes
    if ((int)sw != lastW || (int)sh != lastH) {
        lastW = (int)sw; lastH = (int)sh;
        TraceLog(LOG_INFO, "DISPLAY: drawing at %dx%d (game scale %.2f)", lastW, lastH, s);
    }
    float vw = SCREEN_WIDTH * s, vh = SCREEN_HEIGHT * s;
    float ox = floorf((sw - vw) * 0.5f), oy = floorf((sh - vh) * 0.5f);
    BeginScissorMode((int)ox, (int)oy, (int)ceilf(vw), (int)ceilf(vh));   // letterbox bars stay black
    Camera2D cam = { 0 };
    cam.offset = (Vector2){ ox, oy };
    cam.zoom = s;
    BeginMode2D(cam);
}

void Gfx_EndView(void) {
    EndMode2D();
    EndScissorMode();
}

// --------------------------------------------------------------------- fullscreen --
#define SETTINGS_FILE "settings.cfg"

static void SaveFullscreenSetting(bool on) {
    FILE *f = fopen(SETTINGS_FILE, "w");
    if (!f) return;
    fprintf(f, "# written by the game - F11 / Alt+Enter toggles fullscreen\nfullscreen %d\n", on ? 1 : 0);
    fclose(f);
}

static int LoadFullscreenSetting(void) {
    FILE *f = fopen(SETTINGS_FILE, "r");
    if (!f) return -1;
    char line[128];
    int v = -1;
    while (fgets(line, sizeof(line), f)) {
        int x;
        if (sscanf(line, " fullscreen %d", &x) == 1) v = x ? 1 : 0;
    }
    fclose(f);
    return v;
}

bool Gfx_IsFullscreen(void) { return IsWindowState(FLAG_BORDERLESS_WINDOWED_MODE); }

static void SetFullscreen(bool on) {
    if (on == Gfx_IsFullscreen()) return;
    ToggleBorderlessWindowed();       // borderless window at the monitor's native resolution
    TraceLog(LOG_INFO, "DISPLAY: switching to %s (monitor %dx%d)", on ? "fullscreen" : "windowed",
             GetMonitorWidth(GetCurrentMonitor()),
             GetMonitorHeight(GetCurrentMonitor()));
}

void Gfx_ApplyStartupWindowMode(int argc, char **argv) {
    int want = LoadFullscreenSetting();
    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--fullscreen") == 0) want = 1;
        else if (strcmp(argv[i], "--windowed") == 0) want = 0;
    }
    if (want == 1) SetFullscreen(true);
}

bool Gfx_HandleFullscreenKeys(void) {
    bool alt = IsKeyDown(KEY_LEFT_ALT) || IsKeyDown(KEY_RIGHT_ALT);
    if (IsKeyPressed(KEY_F11) || (alt && (IsKeyPressed(KEY_ENTER) || IsKeyPressed(KEY_KP_ENTER)))) {
        SetFullscreen(!Gfx_IsFullscreen());
        SaveFullscreenSetting(Gfx_IsFullscreen());
        return true;
    }
    return false;
}

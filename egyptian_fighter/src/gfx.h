#ifndef GFX_H
#define GFX_H
// Big-screen / TV friendly rendering helpers (see gfx.c)
//  * the game is laid out in a fixed 1280x720 "virtual" space, but drawn through a 2D camera
//    at the window's real resolution (1080p / 4K) - sprites, fonts and shapes are rasterised
//    at native resolution, not upscaled from a small render target
//  * sprite textures: premultiplied alpha + mipmaps + trilinear filtering (no dark fringes,
//    no shimmering when a big sheet is drawn small)
//  * TTF fonts loaded large (sharp text at any size)
//  * borderless fullscreen (F11 / Alt+Enter / --fullscreen), remembered in settings.cfg
#include "raylib.h"
#include <stdbool.h>

// fonts
extern Font gUiFont;      // assets/fonts/BarlowSemiCondensed-Bold.ttf (falls back to raylib's font)
extern Font gTitleFont;   // assets/fonts/Bangers-Regular.ttf
void Gfx_LoadFonts(void);
void Gfx_UnloadFonts(void);
void UI_DrawText(const char *text, int x, int y, int size, Color color);
int  UI_MeasureText(const char *text, int size);
void Gfx_DrawTitle(Font f, const char *text, Vector2 centre, float size, Color fill, Color outline, float outlinePx);
Vector2 Gfx_MeasureTitle(Font f, const char *text, float size);

// textures: premultiplied alpha, mipmapped, trilinear.  Draw them inside
// BeginBlendMode(BLEND_ALPHA_PREMULTIPLY) with a Gfx_Premul()-ed tint.
Texture2D Gfx_TextureFromImage(Image img);      // does not unload img
Texture2D Gfx_LoadTexture(const char *path);
Color Gfx_Premul(Color c);

// view: 1280x720 virtual space -> window (letterboxed, aspect kept)
void Gfx_BeginView(void);
void Gfx_EndView(void);
float Gfx_ViewScale(void);

// window / fullscreen
void Gfx_ApplyStartupWindowMode(int argc, char **argv);   // after InitWindow
bool Gfx_HandleFullscreenKeys(void);                       // F11 / Alt+Enter; true = toggled
bool Gfx_IsFullscreen(void);

#endif

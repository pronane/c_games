#ifndef GRAPHICS_H
#define GRAPHICS_H

#include "raylib.h"
#include "raymath.h"

// Unified N64 Display Dimensions
#define N64_SCREEN_WIDTH 320
#define N64_SCREEN_HEIGHT 240
#define N64_ASPECT_RATIO (4.0f / 3.0f)

typedef enum VideoMode {
    VIDEO_MODE_AUTHENTIC_N64 = 0,
    VIDEO_MODE_ENHANCED_3D
} VideoMode;

// Player data model completely isolated from the native rendering libraries
typedef struct GaelicPlayer {
    Vector3 position;
    Vector3 velocity;
    float rotationAngle;
    int teamID;
    int playerNumber;
    bool isRunning;
    int animationFrame;
} GaelicPlayer;

// Structure to hold both asset variants to prevent system bottlenecks
typedef struct UnifiedAsset {
    Model highPolyMesh;            // Used in Enhanced 3D Mode
    Texture2D hdTexture;           // 2048x2048 HD Skin
    Texture2D n64SpriteSheet;      // 32x32 per frame 8-way low-res matrix
    Rectangle spriteFrameBounds;   // active cell coordinates inside sheet
} UnifiedAsset;

#endif // GRAPHICS_H

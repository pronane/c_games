/*  Turbo Tumble 64 - an original N64-era style kart racer
 *  Written in C99 with raylib 5.x
 *
 *  common.h : shared types, globals and module interfaces
 */
#ifndef TT64_COMMON_H
#define TT64_COMMON_H

#include "raylib.h"
#include "raymath.h"
#include "rlgl.h"
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

#define GAME_TITLE      "TURBO TUMBLE 64"
#define GAME_VERSION    "1.0"

#define MAX_RACERS          8
#define NUM_LAPS            3
#define SIM_DT              (1.0f/60.0f)
#define MAX_HUMANS          2
#define MAX_TRACK_SAMPLES   2048
#define MAX_ITEM_BOXES      48
#define MAX_PROJECTILES     64
#define MAX_PARTICLES       4096
#define GHOST_MAX           4800   /* 20 Hz samples: 4 minutes of lap */
#define GHOST_HZ            20.0f
#define NUM_TRACKS          6
#define MUSIC_TITLE         NUM_TRACKS
#define MUSIC_RESULTS       (NUM_TRACKS + 1)
#define MAX_CHARACTERS      32

/* ------------------------------------------------------------------ */
/* Items                                                               */
/* ------------------------------------------------------------------ */
typedef enum {
    ITEM_NONE = 0,
    ITEM_PEEL,       /* Slippy Peel      - dropped behind, spins karts            */
    ITEM_MELON,      /* Bouncy Melon     - fired straight, bounces off walls      */
    ITEM_TOMATO,     /* Homing Tomato    - seeks the racer ahead of you           */
    ITEM_PEPPER,     /* Hot Pepper       - short speed boost                      */
    ITEM_PEPPER3,    /* Triple Pepper    - three boosts                           */
    ITEM_DISCO,      /* Disco Ball       - invincible + faster for a while        */
    ITEM_KAZOO,      /* Thunder Kazoo    - shrinks every other racer              */
    ITEM_COUNT
} ItemType;
extern const char *ITEM_NAMES[ITEM_COUNT];

/* ------------------------------------------------------------------ */
/* Characters (table lives in characters.c)                            */
/* ------------------------------------------------------------------ */
typedef enum { WEIGHT_LIGHT = 0, WEIGHT_MEDIUM, WEIGHT_HEAVY } WeightClass;
typedef enum { HEAD_ROUND = 0, HEAD_CUBE, HEAD_TOAST, HEAD_BLOB, HEAD_BEAR, HEAD_ROBOT, HEAD_BIRD, HEAD_YETI } HeadShape;
typedef enum { HAT_NONE = 0, HAT_BUN, HAT_PIRATE, HAT_ANTENNA, HAT_FLOPPY_EARS, HAT_ROUND_EARS,
               HAT_HORNS, HAT_CROWN, HAT_PROPELLER, HAT_GOGGLES, HAT_CHEF } HatType;

typedef struct CharacterDef {
    const char *name;
    const char *tagline;      /* personality blurb shown on the select screen */
    WeightClass weight;
    float topSpeed;           /* 1..5 */
    float accel;              /* 1..5 */
    float handling;           /* 1..5 */
    float mass;               /* 1..5 (collisions) */
    Color body, accent, kart, trim;
    HeadShape head;
    HatType hat;
    float voicePitch;         /* pitch of the little "woo-hoo" chirps */
    const char *modelFile;    /* optional model in assets/characters/ (NULL = primitives) */
    /* data-driven characters (assets/characters/<name>/character.ini) */
    int spriteAngles;         /* 0 = not a sprite character, 1 = single billboard, 8/16 = sheet */
    float spriteSize;         /* driver height in world units */
} CharacterDef;

extern CharacterDef CHARACTERS[MAX_CHARACTERS];
extern int NUM_CHARACTERS;

/* ------------------------------------------------------------------ */
/* Tracks                                                              */
/* ------------------------------------------------------------------ */
typedef enum { SCENERY_MEADOW = 0, SCENERY_DESERT, SCENERY_SNOW, SCENERY_STARLIGHT, SCENERY_BEACH, SCENERY_SPOOKY } SceneryType;

#define MAX_CTRL_PTS 40
typedef struct TrackDef {
    const char *name;
    const char *subtitle;
    int numPts;
    float pts[MAX_CTRL_PTS][4];       /* x, z, height, road width */
    SceneryType scenery;
    Color skyTop, skyBottom, fog;
    Color ground, road, rumbleA, rumbleB, wallA, wallB;
    float fogDensity;
    float grip;                        /* 1 = normal, lower = icy */
    bool night;
    bool rainbowRoad;
    bool noGround;                     /* void under the track */
    float wallHeight;
    int numRamps;
    float ramps[4][2];                 /* start fraction, length (units) */
    int numBoxRows;
    float boxRows[6];                  /* fractions along the lap */
    int musicSeed;
    float bpm;
    int musicKey;                      /* midi root note */
    int musicScale;                    /* 0 major, 1 minor, 2 mixolydian, 3 dorian */
    /* secret shortcut: leaves the road at scFrom, rejoins at scTo (fractions), on side scSide (+1 right, -1 left) */
    float scFrom, scTo;
    int scSide;
    bool scIsRoad;                     /* true = paved (no off-road slowdown) */
    const char *scHint;
    /* bumpy road sections (moguls): fraction ranges */
    int numBumps;
    float bumps[3][2];
    float bumpAmp, bumpPeriod;
    Color groundFar;                   /* ground colour far from the road (gradient), alpha 0 = none */
    float farStart, farEnd;
} TrackDef;

extern const TrackDef TRACK_DEFS[NUM_TRACKS];

typedef struct TrackSample {
    Vector3 pos;      /* centre line (y = road height) */
    Vector3 fwd;      /* horizontal unit forward */
    Vector3 right;    /* horizontal unit right   */
    float width;
    float curv;       /* signed curvature (1/units), + = turning left */
    float dist;       /* distance from start */
    float edge[2];    /* outer edge of the off-road strip (wall line), [0]=left [1]=right */
    bool ramp;
    bool bump;
} TrackSample;

typedef struct Track {
    const TrackDef *def;
    int index;
    int n;
    TrackSample s[MAX_TRACK_SAMPLES];
    float length;
    float spacing;
    float shoulder;   /* off-road width beyond the rumble strip */
    float groundY;
    Model mRoad, mGround, mWalls, mScenery, mSky;
    bool loaded;
    int builtVisual;   /* visual mode the meshes were built for */
    /* shortcut corridor */
    int scN;
    TrackSample sc[256];
    int scA, scB;      /* main-track samples where it leaves / rejoins */
    float scHalf;
    Vector2 mapMin, mapMax;
} Track;

/* ------------------------------------------------------------------ */
/* Karts                                                               */
/* ------------------------------------------------------------------ */
typedef struct KartInput {
    float steer;          /* -1 left .. +1 right */
    bool accel, brake;
    bool hop, hopPressed;
    bool item, itemPressed;
    bool back;            /* hold to throw items backwards */
} KartInput;

typedef struct Kart {
    int charId;
    int human;            /* -1 = CPU, else player index 0/1 */
    bool autopilot;       /* CPU drives (also used for humans after finishing / autotest) */
    Vector3 pos;
    float vy;
    bool grounded;
    float heading, moveYaw, speed;
    float steer;          /* smoothed steering */
    float visYaw;         /* visual drift yaw offset */
    float tilt;
    int seg;
    float lat, along;
    int segCount;         /* accumulated samples travelled (lap progress) */
    float progress;
    int lap;              /* completed laps */
    bool finished;
    float finishTime;
    int place;
    float lapStartTime, lastLapTime, bestLap;
    /* drift */
    int driftState;       /* 0 none, 1 hop, 2 drifting */
    int driftDir;
    float driftCharge;
    int sparkLevel;
    float lastSteerSign;
    /* effects */
    float boostTimer, boostPower;
    float spinTimer, spinAngle;
    float discoTimer, shrinkTimer, scale;
    float invulnTimer;
    float squash;
    float offroad;
    float bumpCooldown;
    float startBoostWindow;
    int startPressFrame;
    /* items */
    ItemType item;
    int itemCount;
    float roulette, rouletteDur;
    ItemType rouletteFinal;
    float itemFlash;      /* HUD pop when the roulette lands */
    float turboFlash;     /* mini-turbo kick (flames + camera punch) */
    int lastTurboLevel;
    int statMiniTurbos[3];
    /* AI */
    float aiLane, aiLaneTarget, aiLaneTimer;
    float aiItemDelay;
    float aiSkill;
    float stuckTimer;
    float aiDriftTimer;
    float aiSteerAvg;
    /* stats */
    int statItemsGot, statItemsUsed, statHits, statBumps, statBoosts;
    float wheelRot;
    float engineVol;
    /* terrain / shortcut */
    bool onShortcut;
    int scIdx;
    float groundY;
    float airTime;
    bool aiTakeShortcut;
    bool aiScDecided;
    bool dbgInSc;
    int shortcutsTaken;
    int statJumps;
    int statBumpAirs;
} Kart;

/* ------------------------------------------------------------------ */
/* Items in the world                                                  */
/* ------------------------------------------------------------------ */
typedef struct ItemBox { Vector3 pos; float respawn; bool active; } ItemBox;

typedef struct Projectile {
    bool active;
    ItemType type;
    Vector3 pos;
    float yaw, speed, vy;
    float life;
    int owner, target;
    int seg;
    int bounces;
    float armTime;        /* can't hit the owner until this reaches 0 */
} Projectile;

typedef struct Particle {
    Vector3 p, v;
    Color c;
    float life, maxLife, size;
    float grav;
    bool additive;        /* glowing sparks / flames */
} Particle;

/* ------------------------------------------------------------------ */
/* Race                                                                */
/* ------------------------------------------------------------------ */
typedef enum { RACE_INTRO = 0, RACE_COUNTDOWN, RACE_RUNNING, RACE_DONE } RacePhase;

typedef struct Race {
    int numKarts;
    Kart karts[MAX_RACERS];
    int humanKart[MAX_HUMANS];
    int numHumans;
    RacePhase phase;
    float phaseTime;
    float time;            /* race clock (starts at GO) */
    float countdown;
    int lastBeep;
    float doneTimer;
    int finishOrder[MAX_RACERS];
    int numFinished;
    ItemBox boxes[MAX_ITEM_BOXES];
    int numBoxes;
    Projectile proj[MAX_PROJECTILES];
    Particle parts[MAX_PARTICLES];
    int numParts;
    bool timeTrial;
    bool attract;          /* title screen demo race */
    Camera3D cam[MAX_HUMANS];
    float camYaw[MAX_HUMANS];
    float camFov[MAX_HUMANS];
    float bannerTimer[MAX_HUMANS];
    char banner[MAX_HUMANS][32];
    bool finalLapMusic;
    float shake[MAX_HUMANS];
    long simFrames;
} Race;

/* ------------------------------------------------------------------ */
/* Game / menus                                                        */
/* ------------------------------------------------------------------ */
typedef enum { MODE_GP = 0, MODE_TT, MODE_VS } GameMode;
typedef enum { SCR_TITLE = 0, SCR_MODE, SCR_OPTIONS, SCR_CHAR, SCR_TRACK, SCR_RACE, SCR_RESULTS, SCR_STANDINGS, SCR_CONTROLS, SCR_TROPHY } Screen;

/* gamepad actions + bindings (input.c) */
typedef enum { PA_ACCEL = 0, PA_BRAKE, PA_HOP, PA_ITEM, PA_PAUSE, NUM_PAD_ACTIONS } PadAction;
typedef enum { BIND_NONE = 0, BIND_STD_BUTTON, BIND_STD_AXIS, BIND_RAW_BUTTON, BIND_RAW_AXIS_POS, BIND_RAW_AXIS_NEG } BindKind;
typedef struct PadBind { signed char kind, code; } PadBind;
extern PadBind gBinds[2][NUM_PAD_ACTIONS][2];   /* [0] standard gamepads, [1] raw/DirectInput pads */

typedef struct Settings {
    int pixelMode;      /* 0 = chunky N64 (1/3 res), 1 = crisp (1/2 res), 2 = full resolution */
    int cc;             /* 0 = 50cc, 1 = 100cc, 2 = 150cc */
    float musicVol, sfxVol;
    bool showFps;
    int padMode;        /* 0 auto, 1 standard (XInput/SDL db), 2 raw DirectInput */
    int visualMode;     /* 0 ORIGINAL (320x240 N64 look), 1 ENHANCED */
} Settings;

typedef struct Game {
    Screen screen;
    GameMode mode;
    Settings settings;
    int numHumans;
    int humanChar[MAX_HUMANS];
    int trackIndex;
    int gpRace;
    int gpChars[MAX_RACERS];     /* character per kart slot during a cup */
    int gpPoints[MAX_RACERS];
    int gpLastPoints[MAX_RACERS];   /* points scored in the last race (standings "+N") */
    int gpLastPlace[MAX_RACERS];
    int menuSel, menuSel2;
    int charCursor[MAX_HUMANS];
    bool charLocked[MAX_HUMANS];
    bool paused;
    int pauseSel;
    float screenTime;
    float time;
    bool quit;
    /* rendering */
    Shader fogShader;
    int locFogColor, locFogDensity, locFogStart;
    Texture2D texRoad, texGround[NUM_TRACKS], texWhite, texQuestion, texDot;
    RenderTexture2D view[MAX_HUMANS];
    int viewW, viewH, viewScale;
    RenderTexture2D preview;
    Vector3 sunDir;
    float ambient;
    Model charModels[MAX_CHARACTERS];
    bool charModelLoaded[MAX_CHARACTERS];
    Texture2D charSprite[MAX_CHARACTERS];
    /* time trial records */
    float bestTimes[NUM_TRACKS];
    /* time trial ghost (best lap) */
    struct { int track, charId, n; float lapTime; float x[GHOST_MAX], y[GHOST_MAX], z[GHOST_MAX], yaw[GHOST_MAX]; } ghost, ghostRec;
    bool ghostValid;
    float ghostRecTimer;
    /* automated test */
    bool autotest;
    int autoSpeed;
    char shotDir[256];
    char shotPrefix[32];
    int remapAction;
    int autoVisual;
    bool previewOnly;
    int autoOnly;
} Game;

extern Game G;
extern Race R;
extern Track T;

/* ---------------- util ---------------- */
float Approach(float v, float target, float step);
float WrapAngle(float a);
float LerpAngle(float a, float b, float t);
float RandF(float lo, float hi);
Color ColorScale(Color c, float s);
Color ColorMix(Color a, Color b, float t);
Color HueColor(float h, float s, float v);
void DrawTextOutlined(const char *text, int x, int y, int size, Color col);
void DrawTextCentered(const char *text, int cx, int y, int size, Color col);
const char *OrdinalSuffix(int place);
const char *FormatTime(float t);

/* ---------------- mesh builder ---------------- */
typedef struct MeshBuilder { float *v, *t, *n; unsigned char *c; int count, cap; } MeshBuilder;
void MB_Init(MeshBuilder *mb);
void MB_Free(MeshBuilder *mb);
Color MB_Shade(Color c, Vector3 n);
void MB_TriUV(MeshBuilder *mb, Vector3 p0, Vector3 p1, Vector3 p2, Vector2 u0, Vector2 u1, Vector2 u2,
              Color c0, Color c1, Color c2, Vector3 outRef, bool shade);
void MB_Tri(MeshBuilder *mb, Vector3 p0, Vector3 p1, Vector3 p2, Color c, Vector3 outRef);
void MB_Quad(MeshBuilder *mb, Vector3 p0, Vector3 p1, Vector3 p2, Vector3 p3, Color c, Vector3 outRef);
void MB_QuadUV(MeshBuilder *mb, Vector3 p0, Vector3 p1, Vector3 p2, Vector3 p3,
               Vector2 u0, Vector2 u1, Vector2 u2, Vector2 u3, Color c, Vector3 outRef, bool shade);
void MB_Box(MeshBuilder *mb, Vector3 center, Vector3 size, float yaw, Color c);
void MB_Cylinder(MeshBuilder *mb, Vector3 base, float rBottom, float rTop, float h, int sides, Color c);
void MB_Sphere(MeshBuilder *mb, Vector3 c, Vector3 radius, int rings, int slices, Color col);
Model MB_BuildModel(MeshBuilder *mb, Texture2D tex, bool fog);
void MB_VertexLit(MeshBuilder *mb, Vector3 p, Vector2 uv, Vector3 n, Color c);
void MB_SmoothSphere(MeshBuilder *mb, Vector3 c, Vector3 r, int rings, int slices, Color bottom, Color top, float minLat);

/* immediate-mode lit primitives (used for karts / items) */
void DrawLitBox(Vector3 c, Vector3 size, Color col);
void DrawLitSphere(Vector3 c, Vector3 r, Color col, int rings, int slices);
void DrawLitCylinderX(Vector3 c, float radius, float width, Color col, int sides);
void DrawLitCylinderY(Vector3 base, float rBottom, float rTop, float h, Color col, int sides);
void DrawLitBevelBox(Vector3 c, Vector3 size, float bevel, Color col);
void DrawLitRoundBox(Vector3 c, Vector3 size, float r, float taperX, float taperY, Color top, Color bottom);
void DrawLitCapsule(Vector3 a, Vector3 b, float r, Color col);
void DrawLitTube(Vector3 a, Vector3 b, float r, Color col);
void DrawLitLathe(const float *rad, const float *ys, int n, int sides, Color col);
void DrawLitWheel(float radius, float width, Color tyre, Color rim, Color cap, int sides);
/* bake lit primitives into a mesh instead of drawing (cached kart / driver models) */
void LitCaptureBegin(MeshBuilder *mb, float sphereDetail, int roundSegs);
void LitCaptureEnd(void);
bool LitCapturing(void);
void XPush(void); void XPop(void);
void XTranslate(float x, float y, float z);
void XRotate(float deg, float x, float y, float z);
void XScale(float x, float y, float z);

/* ---------------- characters ---------------- */
void CharactersInit(void);
void DrawCharacterKart(int charId, const Kart *k, float t);
void DrawCharacterKartTint(int charId, const Kart *k, float t, Color tint);   /* tint.a < 255 = ghost */
void DrawTrophyModel(int tier, float t);   /* 0 gold 1 silver 2 bronze */
void DrawCharacterPreview(int charId, float t);

/* ---------------- tracks ---------------- */
void TrackBuild(Track *tr, int index);
void TrackUnload(Track *tr);
void TrackLocate(const Track *tr, Vector3 p, int hint, int *seg, float *lat, float *along, float *groundY);
float TrackHalfWidth(const Track *tr, int seg);
float TrackWallLimit(const Track *tr, int seg, float lat);
Vector3 TrackPoint(const Track *tr, int seg, float lat);
int TrackWrap(const Track *tr, int i);
void TrackOutline(int index, Vector2 *out, int maxPts, int *count);
void ALog(const char *fmt, ...);   /* main.c: autotest log */
bool TrackShortcutLocate(const Track *tr, Vector3 p, int *idx, float *lat, float *along, float *groundY);
int TrackShortcutMainSeg(const Track *tr, int idx, float along);

/* ---------------- karts / AI ---------------- */
void KartInit(Kart *k, int charId, int human, int gridSlot);
void KartUpdate(int idx, const KartInput *in, float dt);
void KartAIInput(int idx, KartInput *in, float dt);
void KartsCollide(void);
void KartHit(int idx, bool bigHit);
float KartTopSpeed(const Kart *k);

/* ---------------- items ---------------- */
void ItemsReset(void);
void ItemsUpdate(float dt);
void ItemUse(int kartIdx);
void ItemBoxesUpdate(float dt);
ItemType ItemRoll(int place, int numKarts);
void DrawItemsWorld(Camera3D cam);
void DrawItemIcon(ItemType it, int cx, int cy, float size);

/* ---------------- particles ---------------- */
void ParticleSpawn(Vector3 p, Vector3 v, Color c, float life, float size, float grav);
void ParticleSpawnEx(Vector3 p, Vector3 v, Color c, float life, float size, float grav, bool additive);
void ParticlesUpdate(float dt);
void ParticlesDraw(Camera3D cam);

/* ---------------- audio ---------------- */
typedef enum {
    SFX_BEEP_LOW = 0, SFX_BEEP_HIGH, SFX_DRIFT, SFX_BOOST, SFX_ROULETTE, SFX_ITEMGET, SFX_THROW,
    SFX_HIT, SFX_BUMP, SFX_SPIN, SFX_LAP, SFX_FINALLAP, SFX_FINISH, SFX_MENU_MOVE, SFX_MENU_OK,
    SFX_MENU_BACK, SFX_PEEL, SFX_DISCO, SFX_KAZOO, SFX_HOP, SFX_SPARK, SFX_BOXBREAK, SFX_SQUISH,
    SFX_COUNT
} SfxId;
void AudioInit(void);
void AudioShutdown(void);
void AudioUpdate(void);
void PlaySfx(SfxId id, float vol, float pitch);
void PlayVoice(int charId, int kind);        /* 0 = woohoo, 1 = ouch, 2 = yay */
void MusicPlay(int song);                      /* 0..NUM_TRACKS-1 tracks, MUSIC_TITLE, MUSIC_RESULTS, -1 stop */
void MusicSetTempo(float rate);
void EngineSet(int player, float speedNorm, float vol);
void DriftLoop(int player, bool on, int sparkLevel);

/* ---------------- race ---------------- */
void RaceStart(int trackIndex, bool attract);
void RaceUpdate(float dt);
void RaceDraw(void);
void RaceEnd(void);
void GhostLoad(int track);
bool GhostPose(float lapT, Vector3 *pos, float *yaw);
void RaceComputePlaces(void);
int  RaceKartAhead(int idx);

/* ---------------- render ---------------- */
void RenderInit(void);
void RenderResize(void);
void RenderWorldView(int view, Camera3D cam, int focusKart, Rectangle dst);
void RenderApplyTextureFilters(void);
bool RenderDirect(void);
void DrawHUD(int view, Rectangle area);
void DrawMinimap(Rectangle area);
void BeginWorld(Camera3D cam, float fov);
void EndWorld(void);
void DrawSkyAndTrack(Camera3D cam);

/* ---------------- menus ---------------- */
void MenusUpdate(float dt);
void MenusDraw(void);
void GoToScreen(Screen s);
void InputRead(int player, KartInput *in);
void InputInit2(void);
void InputUpdate(float dt);
void InputDrawToast(void);
void InputDefaultBinds(int set);
const char *PadActionName(int a);
const char *BindName(PadBind b);
const char *PadPlayerName(int p);
bool PadPlayerUsesRaw(int p);
void InputCaptureBegin(void);
bool InputCapture(PadBind *out);
void InputSetBind(int set, int action, PadBind b);
bool PlayerUp(int p); bool PlayerDown(int p);
bool MenuUp(void); bool MenuDown(void); bool MenuLeft(void); bool MenuRight(void);
bool MenuOk(void); bool MenuBack(void); bool PausePressed(void);
bool PlayerOk(int p); bool PlayerBack(int p); bool PlayerLeft(int p); bool PlayerRight(int p);
void SaveSettings(void);
void LoadSettings(void);

#endif
